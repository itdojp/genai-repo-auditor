from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any, List

from .common import json_type_name, validate_generated_at, validate_schema
from .context import ValidationContext


RUN_MANIFEST_PATH = Path("run-manifest.json")
ARTIFACT_RETENTIONS = {"latest", "supporting", "archive"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest_artifact_path(
    run_dir: Path,
    value: Any,
    field_path: str,
    errors: List[str],
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_path}: path must be a non-empty string")
        return None
    rel = Path(value)
    windows_rel = PureWindowsPath(value)
    if rel.is_absolute() or windows_rel.drive or windows_rel.root:
        errors.append(f"{field_path}: artifact path must be relative to the run directory")
        return None
    if ".." in rel.parts:
        errors.append(f"{field_path}: artifact path must not contain '..'")
        return None
    current = run_dir
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            errors.append(f"{field_path}: artifact path must not contain symlink components: {rel.as_posix()}")
            return None
    target = run_dir / rel
    if not target.exists():
        errors.append(f"{field_path}: manifest artifact not found: {rel.as_posix()}")
        return None
    return target


def validate_run_manifest(context: ValidationContext) -> bool:
    run_dir = context.run_dir
    errors = context.errors
    manifest_path = run_dir / RUN_MANIFEST_PATH
    if not manifest_path.exists():
        return False
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"run-manifest.json invalid JSON: {exc}")
        return True
    if not isinstance(manifest_data, dict):
        errors.append(f"run_manifest: expected type object, got {json_type_name(manifest_data)}")
        return True
    validate_schema(manifest_data, context.schema("run-manifest.schema.json"), "run_manifest", errors)
    validate_generated_at(manifest_data.get("generated_at"), "run_manifest.generated_at", errors)

    artifacts = manifest_data.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("run_manifest.artifacts: artifacts must be a list")
        artifacts = []
    artifact_by_path: dict[str, dict[str, Any]] = {}
    retention_counts: dict[str, int] = {name: 0 for name in ARTIFACT_RETENTIONS}
    retention_counts["unknown"] = 0
    for index, artifact in enumerate(artifacts):
        path = f"run_manifest.artifacts[{index}]"
        if not isinstance(artifact, dict):
            errors.append(f"{path}: artifact must be an object")
            continue
        artifact_path = artifact.get("path")
        artifact_path_text = str(artifact_path or "")
        if artifact_path_text in artifact_by_path:
            errors.append(f"{path}.path: duplicate manifest artifact path {artifact_path_text}")
        if artifact_path_text:
            artifact_by_path[artifact_path_text] = artifact
        retention = artifact.get("retention")
        if retention not in ARTIFACT_RETENTIONS:
            errors.append(f"{path}.retention: invalid retention {retention!r}")
            retention_counts["unknown"] += 1
        else:
            retention_counts[str(retention)] = retention_counts.get(str(retention), 0) + 1
        target = validate_manifest_artifact_path(run_dir, artifact_path, f"{path}.path", errors)
        if target is None:
            continue
        expected_kind = "dir" if target.is_dir() else "file"
        if artifact.get("kind") != expected_kind:
            errors.append(f"{path}.kind: expected {expected_kind} for {artifact_path_text}")
        if target.is_file():
            size_bytes = artifact.get("size_bytes")
            if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes != target.stat().st_size:
                errors.append(f"{path}.size_bytes: value does not match file size for {artifact_path_text}")
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                errors.append(f"{path}.sha256: file artifacts must include lowercase SHA-256")
            elif digest != sha256_file(target):
                errors.append(f"{path}.sha256: value does not match file digest for {artifact_path_text}")

    retention_summary = (
        manifest_data.get("artifact_retention")
        if isinstance(manifest_data.get("artifact_retention"), dict)
        else {}
    )
    latest_paths = retention_summary.get("latest_status_artifacts")
    supporting_paths = retention_summary.get("supporting_artifacts")
    archive_paths = retention_summary.get("archive_artifacts")
    execution = manifest_data.get("execution") if isinstance(manifest_data.get("execution"), dict) else {}
    completed_manifest = execution.get("phase") == "completed"
    if not isinstance(latest_paths, list) or (completed_manifest and not latest_paths):
        errors.append("run_manifest.artifact_retention.latest_status_artifacts: must be a non-empty list for completed manifests")
        latest_paths = []
    if not isinstance(supporting_paths, list):
        errors.append("run_manifest.artifact_retention.supporting_artifacts: must be a list")
        supporting_paths = []
    if not isinstance(archive_paths, list):
        errors.append("run_manifest.artifact_retention.archive_artifacts: must be a list")
        archive_paths = []

    latest_set = {str(path) for path in latest_paths if isinstance(path, str)}
    supporting_set = {str(path) for path in supporting_paths if isinstance(path, str)}
    archive_set = {str(path) for path in archive_paths if isinstance(path, str)}
    for left_name, left_set, right_name, right_set in [
        ("latest", latest_set, "supporting", supporting_set),
        ("latest", latest_set, "archive", archive_set),
        ("supporting", supporting_set, "archive", archive_set),
    ]:
        overlap = sorted(left_set & right_set)
        if overlap:
            errors.append(
                f"run_manifest.artifact_retention: {left_name} and {right_name} artifacts overlap: {', '.join(overlap)}"
            )
    for path in sorted(latest_set):
        artifact = artifact_by_path.get(path)
        if artifact is None:
            errors.append(f"run_manifest.artifact_retention.latest_status_artifacts: path is not listed in artifacts: {path}")
        elif artifact.get("retention") != "latest":
            errors.append(f"run_manifest.artifact_retention.latest_status_artifacts: {path} must have retention 'latest'")
    for path in sorted(supporting_set):
        artifact = artifact_by_path.get(path)
        if artifact is None:
            errors.append(f"run_manifest.artifact_retention.supporting_artifacts: path is not listed in artifacts: {path}")
        elif artifact.get("retention") != "supporting":
            errors.append(f"run_manifest.artifact_retention.supporting_artifacts: {path} must have retention 'supporting'")
    for path in sorted(archive_set):
        artifact = artifact_by_path.get(path)
        if artifact is None:
            errors.append(f"run_manifest.artifact_retention.archive_artifacts: path is not listed in artifacts: {path}")
        elif artifact.get("retention") != "archive":
            errors.append(f"run_manifest.artifact_retention.archive_artifacts: {path} must have retention 'archive'")
    summary_sets = {
        "latest": ("latest_status_artifacts", latest_set),
        "supporting": ("supporting_artifacts", supporting_set),
        "archive": ("archive_artifacts", archive_set),
    }
    for path, artifact in sorted(artifact_by_path.items()):
        retention = artifact.get("retention")
        if retention in summary_sets and path not in summary_sets[retention][1]:
            field_name = summary_sets[retention][0]
            errors.append(f"run_manifest.artifact_retention.{field_name}: missing {retention} artifact from summary: {path}")
    by_retention = (
        retention_summary.get("by_retention")
        if isinstance(retention_summary.get("by_retention"), dict)
        else {}
    )
    for key in ["latest", "supporting", "archive"]:
        if by_retention.get(key) != retention_counts.get(key, 0):
            errors.append(f"run_manifest.artifact_retention.by_retention.{key}: value does not match artifact list")
    return True

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gralib import load_context

MAX_POSTURE_ARTIFACT_BYTES = 5 * 1024 * 1024


def _reports_dir(run_dir: Path) -> Path:
    try:
        ctx = load_context(run_dir)
    except Exception:  # noqa: BLE001 - index/store posture discovery is optional
        ctx = {}
    return run_dir / ctx.get("reports_dir", "reports")


def _run_relative(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_load_json(path: Path) -> tuple[Any, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except Exception as exc:  # noqa: BLE001 - optional artifacts should not break indexing
        return {"parse_error": f"{type(exc).__name__}: {exc}"}, "invalid_json"


def _int_value(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def _list_count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    return len(value) if isinstance(value, list) else 0


def _artifact_item_count(artifact_type: str, data: Any) -> int:
    if not isinstance(data, dict):
        return 0
    if artifact_type == "run_manifest":
        return _list_count(data, "artifacts")
    if artifact_type == "agent_surface":
        return _list_count(data, "agent_surfaces")
    if artifact_type == "supply_chain_posture":
        return _list_count(data, "checks")
    if artifact_type == "provenance_posture":
        return _list_count(data, "workflows")
    if artifact_type == "dependencies":
        return _int_value(data.get("component_count"), _list_count(data, "components"))
    return 0


def _artifact_status(data: Any, error_status: str) -> str:
    if error_status:
        return error_status
    if isinstance(data, dict) and data.get("status"):
        return str(data.get("status"))
    if isinstance(data, dict):
        return "present"
    return "non_object"


def _has_symlink_or_parent_traversal(run_dir: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(run_dir)
    except ValueError:
        return True
    current = run_dir
    for part in relative.parts:
        if part == "..":
            return True
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _is_regular_artifact_file(run_dir: Path, path: Path) -> bool:
    try:
        if _has_symlink_or_parent_traversal(run_dir, path):
            return False
        stat_result = path.stat()
        return path.is_file() and stat_result.st_size <= MAX_POSTURE_ARTIFACT_BYTES
    except OSError:
        return False


def _artifact_candidates(run_dir: Path) -> list[tuple[str, Path]]:
    reports = _reports_dir(run_dir)
    candidates: list[tuple[str, Path]] = []
    # Older planning material referenced reports/run-manifest.json. Keep it as a
    # fallback, but prefer the current gra-audit root run-manifest.json path.
    for manifest_path in [run_dir / "run-manifest.json", reports / "run-manifest.json"]:
        if _is_regular_artifact_file(run_dir, manifest_path):
            candidates.append(("run_manifest", manifest_path))
            break
    candidates.extend(
        [
            ("agent_surface", reports / "agent-surface.json"),
            ("supply_chain_posture", reports / "supply-chain-posture.json"),
            ("provenance_posture", reports / "provenance-posture.json"),
            ("dependencies", reports / "dependencies.json"),
        ]
    )
    unique: list[tuple[str, Path]] = []
    seen: set[tuple[str, str]] = set()
    for artifact_type, path in candidates:
        key = (artifact_type, path.absolute().as_posix())
        if key in seen:
            continue
        seen.add(key)
        unique.append((artifact_type, path))
    return unique


def load_posture_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    """Return optional posture artifacts present in a run directory.

    Missing artifacts are intentionally ignored. Malformed JSON is represented as
    an invalid artifact record instead of failing the whole store/index workflow,
    because these artifacts are optional operational evidence.
    """

    artifacts: list[dict[str, Any]] = []
    for artifact_type, path in _artifact_candidates(run_dir):
        if not _is_regular_artifact_file(run_dir, path):
            continue
        data, error_status = _safe_load_json(path)
        artifacts.append(
            {
                "artifact_type": artifact_type,
                "path": _run_relative(run_dir, path),
                "status": _artifact_status(data, error_status),
                "item_count": _artifact_item_count(artifact_type, data),
                "generated_at": data.get("generated_at") if isinstance(data, dict) else None,
                "data": data,
            }
        )
    return sorted(artifacts, key=lambda item: (str(item.get("artifact_type")), str(item.get("path"))))


def posture_index_summary(run_dir: Path) -> dict[str, Any]:
    artifacts = load_posture_artifacts(run_dir)
    statuses: dict[str, str] = {}
    summary: dict[str, Any] = {
        "posture_artifact_count": len(artifacts),
        "run_manifest_artifact_count": 0,
        "agent_surface_count": 0,
        "scorecard_check_count": 0,
        "provenance_workflow_count": 0,
        "dependency_component_count": 0,
        "dependency_vulnerability_count": 0,
        "statuses": statuses,
    }

    for artifact in artifacts:
        artifact_type = str(artifact.get("artifact_type") or "")
        data = artifact.get("data")
        statuses[artifact_type] = str(artifact.get("status") or "")
        if artifact_type == "run_manifest":
            summary["run_manifest_artifact_count"] = max(
                _int_value(summary.get("run_manifest_artifact_count")),
                _int_value(artifact.get("item_count")),
            )
        elif artifact_type == "agent_surface":
            summary["agent_surface_count"] = max(
                _int_value(summary.get("agent_surface_count")),
                _int_value(artifact.get("item_count")),
            )
        elif artifact_type == "supply_chain_posture":
            summary["scorecard_check_count"] = max(
                _int_value(summary.get("scorecard_check_count")),
                _int_value(artifact.get("item_count")),
            )
        elif artifact_type == "provenance_posture":
            summary["provenance_workflow_count"] = max(
                _int_value(summary.get("provenance_workflow_count")),
                _int_value(artifact.get("item_count")),
            )
        elif artifact_type == "dependencies" and isinstance(data, dict):
            summary["dependency_component_count"] = _int_value(
                data.get("component_count"),
                _int_value(artifact.get("item_count")),
            )
            summary["dependency_vulnerability_count"] = _int_value(
                data.get("vulnerability_count"),
                _list_count(data, "vulnerabilities"),
            )
    return summary

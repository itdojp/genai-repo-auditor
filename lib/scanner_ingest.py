from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dependency_posture import (
    append_dependency_posture_targets,
    should_ingest_dependencies,
    write_dependency_artifacts,
)
from gralib import load_context, load_json, utc_now
from run_events import reports_dir
from scanner_normalize import normalize_scanner_file
from scorecard_posture import append_scorecard_posture_targets, write_scorecard_posture_artifacts


SCORECARD_TOOLS = {"scorecard", "openssf-scorecard", "ossf-scorecard"}


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(temporary, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("scanner ingest temporary path must be a regular file")
        data = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError("scanner ingest write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise OSError("scanner ingest destination must be a regular non-symlink file")
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


@dataclass(frozen=True)
class ScannerIngestPlan:
    run_dir: Path
    source: Path
    tool: str
    safe_tool: str
    format: str
    digest: str
    destination: Path
    normalized_path: Path
    index_path: Path
    output_paths: tuple[Path, ...]
    managed_source: bool


@dataclass(frozen=True)
class ScannerIngestResult:
    entry: dict[str, Any]
    normalized: dict[str, Any]
    output_paths: tuple[Path, ...]
    added_scorecard_targets: tuple[dict[str, Any], ...]
    added_dependency_targets: tuple[dict[str, Any], ...]


def safe_tool_name(tool: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in tool.lower())


def _resolved_format(source: Path, requested_format: str) -> str:
    if requested_format != "auto":
        return requested_format
    suffix = source.suffix.lower().lstrip(".")
    return suffix or "unknown"


def build_scanner_ingest_plan(
    run_dir: Path,
    *,
    tool: str,
    source: Path,
    requested_format: str = "auto",
    managed_source: bool = False,
) -> ScannerIngestPlan:
    run_dir = run_dir.resolve()
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    safe_tool = safe_tool_name(tool)
    if not safe_tool:
        safe_tool = "unknown-tool"
    fmt = _resolved_format(source, requested_format)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    reports = reports_dir(run_dir)
    destination_dir = reports / "scanner-results"
    if managed_source:
        raw_root = destination_dir / "raw"
        try:
            source.relative_to(raw_root.resolve(strict=False))
        except ValueError as exc:
            raise ValueError("managed scanner source must be under scanner-results/raw") from exc
        destination = source
        normalized_path = destination_dir / "normalized" / f"{safe_tool}-leads.json"
    else:
        destination = destination_dir / f"{safe_tool}-{digest}.{fmt}"
        normalized_path = destination_dir / "normalized" / f"{safe_tool}-{digest}-leads.json"
    index_path = destination_dir / "scanner-index.json"
    outputs = [destination, normalized_path, index_path]
    if safe_tool in SCORECARD_TOOLS:
        outputs.extend(
            [reports / "supply-chain-posture.json", reports / "supply-chain-posture.md", reports / "targets.json"]
        )
    if should_ingest_dependencies(safe_tool=safe_tool, fmt=fmt):
        outputs.extend([reports / "dependencies.json", reports / "DEPENDENCY_RISK.md", reports / "targets.json"])
    return ScannerIngestPlan(
        run_dir=run_dir,
        source=source,
        tool=tool,
        safe_tool=safe_tool,
        format=fmt,
        digest=digest,
        destination=destination,
        normalized_path=normalized_path,
        index_path=index_path,
        output_paths=tuple(dict.fromkeys(outputs)),
        managed_source=managed_source,
    )


def managed_scanner_output_paths(run_dir: Path, *, tool: str) -> tuple[Path, ...]:
    """Return deterministic outputs that can be preflighted before execution."""

    safe_tool = safe_tool_name(tool) or "unknown-tool"
    reports = reports_dir(run_dir.resolve())
    scanner_results = reports / "scanner-results"
    outputs = [
        scanner_results / "raw" / f"{safe_tool}.json",
        scanner_results / "normalized" / f"{safe_tool}-leads.json",
        scanner_results / "scanner-index.json",
    ]
    if should_ingest_dependencies(safe_tool=safe_tool, fmt="cyclonedx" if safe_tool == "syft" else "json"):
        outputs.extend([reports / "dependencies.json", reports / "DEPENDENCY_RISK.md", reports / "targets.json"])
    return tuple(dict.fromkeys(outputs))


def ingest_scanner_file(plan: ScannerIngestPlan, *, note: str = "") -> ScannerIngestResult:
    plan.index_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = plan.index_path.with_name(f".{plan.index_path.name}.lock")
    deadline = time.monotonic() + 10.0
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise TimeoutError("timed out waiting for scanner ingestion lock") from exc
            time.sleep(0.01)
    try:
        return _ingest_scanner_file_unlocked(plan, note=note)
    finally:
        try:
            os.rmdir(lock_path)
        except FileNotFoundError:
            pass


def _ingest_scanner_file_unlocked(plan: ScannerIngestPlan, *, note: str) -> ScannerIngestResult:
    plan.destination.parent.mkdir(parents=True, exist_ok=True)
    if not plan.managed_source:
        shutil.copy2(plan.source, plan.destination)

    raw_result_ref = str(plan.destination.relative_to(plan.run_dir))
    plan.normalized_path.parent.mkdir(parents=True, exist_ok=True)
    if plan.managed_source and (plan.normalized_path.exists() or plan.normalized_path.is_symlink()):
        raise FileExistsError("managed normalized scanner output already exists")
    normalized = normalize_scanner_file(tool=plan.tool, raw_path=plan.destination, raw_result_ref=raw_result_ref)
    _atomic_write_json(plan.normalized_path, normalized)

    ctx = load_context(plan.run_dir)
    data = load_json(plan.index_path, None)
    if not data:
        data = {
            "run_id": ctx.get("run_id", plan.run_dir.name),
            "repo": ctx.get("repo", ""),
            "generated_at": utc_now(),
            "results": [],
        }
    entry = {
        "tool": plan.tool,
        "path": raw_result_ref,
        "format": plan.format,
        "imported_at": utc_now(),
        "sha256": plan.digest,
        "raw_bytes": normalized.get("raw_bytes", 0),
        "normalized_path": str(plan.normalized_path.relative_to(plan.run_dir)),
        "normalized_leads_count": len(normalized.get("leads") or []),
        "normalization": normalized.get("normalization") or {},
        "note": note,
    }
    data.setdefault("results", []).append(entry)
    _atomic_write_json(plan.index_path, data)

    output_paths = [plan.destination, plan.normalized_path, plan.index_path]
    added_scorecard_targets: list[dict[str, Any]] = []
    if plan.safe_tool in SCORECARD_TOOLS:
        write_scorecard_posture_artifacts(
            run_dir=plan.run_dir,
            raw_path=plan.destination,
            raw_result_ref=raw_result_ref,
        )
        reports = reports_dir(plan.run_dir)
        output_paths.extend([reports / "supply-chain-posture.json", reports / "supply-chain-posture.md"])
        added_scorecard_targets = append_scorecard_posture_targets(plan.run_dir)
        if added_scorecard_targets:
            output_paths.append(reports / "targets.json")

    added_dependency_targets: list[dict[str, Any]] = []
    if should_ingest_dependencies(safe_tool=plan.safe_tool, fmt=plan.format):
        dependency_data = write_dependency_artifacts(
            run_dir=plan.run_dir,
            raw_path=plan.destination,
            raw_result_ref=raw_result_ref,
            tool=plan.tool,
            requested_format=plan.format,
        )
        if dependency_data is not None:
            reports = reports_dir(plan.run_dir)
            output_paths.extend([reports / "dependencies.json", reports / "DEPENDENCY_RISK.md"])
            added_dependency_targets = append_dependency_posture_targets(plan.run_dir)
            if added_dependency_targets:
                output_paths.append(reports / "targets.json")

    return ScannerIngestResult(
        entry=entry,
        normalized=normalized,
        output_paths=tuple(dict.fromkeys(output_paths)),
        added_scorecard_targets=tuple(added_scorecard_targets),
        added_dependency_targets=tuple(added_dependency_targets),
    )

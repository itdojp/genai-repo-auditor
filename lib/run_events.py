from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


COMMAND_EVENTS_REL_PATH = Path("reports") / "command-events.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_context(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "context.json"
    if not path.exists():
        return {"run_id": run_dir.name, "reports_dir": "reports"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"run_id": run_dir.name, "reports_dir": "reports"}
    if not isinstance(data, dict):
        return {"run_id": run_dir.name, "reports_dir": "reports"}
    data.setdefault("run_id", run_dir.name)
    data.setdefault("reports_dir", "reports")
    return data


def reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    raw = Path(str(ctx.get("reports_dir") or "reports"))
    if raw.is_absolute() or ".." in raw.parts:
        raise OSError(f"reports_dir must be a relative path under the run directory: {raw.as_posix()}")
    current = run_dir
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise OSError(f"reports_dir must not contain symlink components: {raw.as_posix()}")
    return run_dir / raw


def command_events_path(run_dir: Path) -> Path:
    return reports_dir(run_dir) / "command-events.jsonl"


def rel_to_run(run_dir: Path, path: Path | str) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(run_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def start_command_event() -> tuple[str, float]:
    return utc_now(), time.perf_counter()


def append_command_event(
    run_dir: Path,
    *,
    command: str,
    phase: str,
    started_at: str,
    started_perf: float,
    exit_code: int,
    target_id: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    artifact_paths: Iterable[Path | str] | None = None,
) -> Path:
    ctx = load_context(run_dir)
    ended_at = utc_now()
    duration_ms = max(0, int(round((time.perf_counter() - started_perf) * 1000)))
    artifacts = [rel_to_run(run_dir, path) for path in (artifact_paths or [])]
    event = {
        "schema_version": "1",
        "run_id": str(ctx.get("run_id") or run_dir.name),
        "repo": str(ctx.get("repo") or ""),
        "command": command,
        "phase": phase,
        "target_id": target_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "exit_code": int(exit_code),
        "model": model,
        "effort": effort,
        "artifact_paths": artifacts,
        "source": "genai-repo-auditor",
    }
    path = command_events_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def load_command_events(run_dir: Path) -> list[dict[str, Any]]:
    path = command_events_path(run_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError(f"{path}:{line_number}: command event must be a JSON object")
        records.append(data)
    return records

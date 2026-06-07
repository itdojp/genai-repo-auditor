from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUN_STATE_REL_PATH = Path("reports") / "run-state.json"
ACTIVE = "active"
PAUSED = "paused"
BLOCKED = "blocked"
STATUSES = {ACTIVE, PAUSED, BLOCKED}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def reports_dir(run_dir: Path) -> Path:
    context = load_json(run_dir / "context.json", {}) or {}
    raw = Path(str(context.get("reports_dir") or "reports"))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError(f"reports_dir must be a relative path under the run directory: {raw}")
    current = run_dir
    for part in raw.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"reports_dir must not contain symlink components: {raw}")
    return run_dir / raw


def run_state_path(run_dir: Path) -> Path:
    return reports_dir(run_dir) / "run-state.json"


def run_metadata(run_dir: Path) -> dict[str, Any]:
    context = load_json(run_dir / "context.json", {}) or {}
    findings = load_json(reports_dir(run_dir) / "findings.json", {}) or {}
    targets = load_json(reports_dir(run_dir) / "targets.json", {}) or {}
    return {
        "run_id": str(findings.get("run_id") or targets.get("run_id") or context.get("run_id") or run_dir.name),
        "repo": str(findings.get("repo") or targets.get("repo") or context.get("repo") or ""),
        "commit": str(findings.get("commit") or targets.get("commit") or context.get("commit") or ""),
    }


def empty_state(run_dir: Path) -> dict[str, Any]:
    metadata = run_metadata(run_dir)
    return {
        "schema_version": "1",
        "run_id": metadata["run_id"],
        "repo": metadata["repo"],
        "commit": metadata["commit"],
        "generated_at": utc_now(),
        "source": "gra-run-state",
        "status": ACTIVE,
        "pause_reason": None,
        "resume_target": None,
        "resume_condition": None,
        "paused_at": None,
        "paused_by": None,
        "final_reconcile": None,
        "block_reason": None,
        "blocked_at": None,
        "blocked_by": None,
        "resumed_at": None,
        "resumed_by": None,
    }


def load_run_state(run_dir: Path) -> dict[str, Any]:
    path = run_state_path(run_dir)
    if not path.exists():
        return empty_state(run_dir)
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("run state must be a JSON object")
    if str(state.get("status") or "") not in STATUSES:
        raise ValueError(f"run state has invalid status: {state.get('status')!r}")
    return state


def write_run_state(run_dir: Path, state: dict[str, Any]) -> Path:
    metadata = run_metadata(run_dir)
    state = dict(state)
    state.update(
        {
            "schema_version": "1",
            "run_id": metadata["run_id"],
            "repo": metadata["repo"],
            "commit": metadata["commit"],
            "generated_at": utc_now(),
            "source": "gra-run-state",
        }
    )
    path = run_state_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def pause_run(
    run_dir: Path,
    *,
    reason: str,
    resume_target: str | None = None,
    resume_condition: str | None = None,
    paused_by: str | None = None,
    final_reconcile: str | None = None,
) -> dict[str, Any]:
    state = empty_state(run_dir)
    state.update(
        {
            "status": PAUSED,
            "pause_reason": reason,
            "resume_target": resume_target,
            "resume_condition": resume_condition,
            "paused_at": utc_now(),
            "paused_by": paused_by,
            "final_reconcile": final_reconcile,
        }
    )
    return state


def block_run(run_dir: Path, *, reason: str, blocked_by: str | None = None) -> dict[str, Any]:
    state = empty_state(run_dir)
    state.update(
        {
            "status": BLOCKED,
            "block_reason": reason,
            "blocked_at": utc_now(),
            "blocked_by": blocked_by,
        }
    )
    return state


def clear_pause(run_dir: Path, *, resumed_by: str | None = None) -> dict[str, Any]:
    state = empty_state(run_dir)
    state.update({"status": ACTIVE, "resumed_at": utc_now(), "resumed_by": resumed_by})
    return state


def is_paused(run_dir: Path) -> bool:
    try:
        return str(load_run_state(run_dir).get("status") or "") == PAUSED
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def pause_summary(state: dict[str, Any]) -> str:
    lines = [f"Run state: {state.get('status') or ACTIVE}"]
    if state.get("pause_reason"):
        lines.append(f"Pause reason: {state.get('pause_reason')}")
    if state.get("resume_target"):
        lines.append(f"Resume target: {state.get('resume_target')}")
    if state.get("resume_condition"):
        lines.append(f"Resume condition: {state.get('resume_condition')}")
    if state.get("paused_at"):
        lines.append(f"Paused at: {state.get('paused_at')}")
    if state.get("paused_by"):
        lines.append(f"Paused by: {state.get('paused_by')}")
    if state.get("final_reconcile"):
        lines.append(f"Previous final reconcile: {state.get('final_reconcile')}")
    if state.get("block_reason"):
        lines.append(f"Block reason: {state.get('block_reason')}")
    return "\n".join(lines)


def paused_error(run_dir: Path, *, action: str) -> str | None:
    try:
        state = load_run_state(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        try:
            state_path = run_state_path(run_dir)
        except (OSError, ValueError, json.JSONDecodeError):
            state_path = run_dir / RUN_STATE_REL_PATH
        return (
            f"Refusing to start {action} because run state could not be read safely: {exc}.\n"
            f"Fix or remove {state_path} after confirming whether the run is paused."
        )
    if str(state.get("status") or "") != PAUSED:
        return None
    return (
        f"Refusing to start {action} because this audit run is paused.\n"
        f"{pause_summary(state)}\n"
        "Only read-only status checks should run while paused. Use `gra-run-state --run RUN_DIR --resume` "
        "to inspect the resume plan, then `gra-run-state --run RUN_DIR --clear-pause` when ready."
    )

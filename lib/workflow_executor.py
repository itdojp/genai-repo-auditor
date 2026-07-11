from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from report_safety import iter_secret_findings
from gralib import load_context, utc_now
from run_state import ACTIVE, BLOCKED, PAUSED, load_run_state, run_state_path
from workflow_execution import WorkflowExecutionReportError, write_workflow_execution
from workflow_orchestrator import _safe_rel


CHECKPOINT_SCHEMA_VERSION = "1"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
TERMINAL_SUCCESS = {"succeeded", "external_prerequisite", "skipped_by_scope"}
STAGE_STATUSES = {
    "pending", "running", "succeeded", "failed", "blocked_dependency",
    "external_prerequisite", "skipped_by_scope", "out_of_range",
}
WORKFLOW_STATUSES = {"running", "paused", "blocked", "succeeded"}


class WorkflowExecutionError(RuntimeError):
    pass


class RunStateGateError(WorkflowExecutionError):
    def __init__(self, message: str, *, status: str = "invalid") -> None:
        super().__init__(message)
        self.status = status


Runner = Callable[[list[str], Path], int]


def plan_fingerprint(plan: dict[str, Any]) -> str:
    stable = {key: value for key, value in plan.items() if key != "generated_at"}
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reports_path(run_dir: Path, plan: dict[str, Any]) -> Path:
    reports_ref = _safe_rel(plan.get("reports_dir"), "workflow_plan.reports_dir")
    current = run_dir
    for part in PurePosixPath(reports_ref).parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowExecutionError("workflow checkpoint reports_dir must not contain symlink components")
    return run_dir / reports_ref


def checkpoint_path(run_dir: Path, plan: dict[str, Any]) -> Path:
    return _reports_path(run_dir, plan) / "workflow-checkpoint.json"


def _safe_artifact(run_dir: Path, ref: str, *, required: bool = True) -> Path | None:
    rel = _safe_rel(ref, "workflow artifact ref")
    current = run_dir
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowExecutionError(f"workflow artifact must not contain symlink components: {rel}")
    path = run_dir / rel
    if not path.exists():
        if required:
            raise WorkflowExecutionError(f"workflow artifact is missing: {rel}")
        return None
    try:
        path.resolve(strict=True).relative_to(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise WorkflowExecutionError(f"workflow artifact must remain under the run directory: {rel}") from exc
    if not path.is_file():
        raise WorkflowExecutionError(f"workflow artifact must be a regular file: {rel}")
    return path


def artifact_stamp(run_dir: Path, ref: str) -> dict[str, Any]:
    path = _safe_artifact(run_dir, ref)
    assert path is not None
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise WorkflowExecutionError(f"workflow artifact must remain a regular file: {ref}")
        size = metadata.st_size
        if size > MAX_ARTIFACT_BYTES:
            raise WorkflowExecutionError(f"workflow artifact exceeds {MAX_ARTIFACT_BYTES} bytes: {ref}")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
    finally:
        os.close(fd)
    return {"path": ref, "size": size, "sha256": digest.hexdigest()}


def _validate_stamp(run_dir: Path, stamp: Any) -> None:
    if not isinstance(stamp, dict) or set(stamp) != {"path", "size", "sha256"}:
        raise WorkflowExecutionError("workflow checkpoint contains an invalid artifact stamp")
    current = artifact_stamp(run_dir, str(stamp.get("path") or ""))
    if current != stamp:
        raise WorkflowExecutionError(f"workflow artifact is stale or mismatched: {stamp.get('path')}")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise WorkflowExecutionError("workflow checkpoint temporary path is not a regular file")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise WorkflowExecutionError("workflow checkpoint write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise WorkflowExecutionError("workflow checkpoint destination must be a regular non-symlink file")
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _write_checkpoint(
    run_dir: Path,
    path: Path,
    checkpoint: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    checkpoint["generated_at"] = _utc_now()
    if list(iter_secret_findings(checkpoint, field_path="workflow_checkpoint")):
        raise WorkflowExecutionError("workflow checkpoint contains secret-like values")
    _atomic_write(path, checkpoint)
    try:
        write_workflow_execution(run_dir, checkpoint, plan)
    except (OSError, ValueError, WorkflowExecutionReportError) as exc:
        raise WorkflowExecutionError(f"workflow execution report write failed: {exc}") from exc


def _utc_now() -> str:
    return utc_now()


def resume_skip_set(run_dir: Path) -> list[str]:
    """Read only the bounded skip selection needed to reconstruct a resume plan."""

    run_dir = run_dir.resolve(strict=True)
    context_path = run_dir / "context.json"
    if not context_path.is_file() or context_path.is_symlink():
        raise WorkflowExecutionError("run must contain a regular non-symlink context.json")
    context = load_context(run_dir)
    reports_ref = _safe_rel(context.get("reports_dir") or "reports", "reports_dir")
    path = _reports_path(run_dir, {"reports_dir": reports_ref}) / "workflow-checkpoint.json"
    if not path.is_file() or path.is_symlink():
        raise WorkflowExecutionError("workflow checkpoint is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowExecutionError("workflow checkpoint must contain valid UTF-8 JSON") from exc
    skips = value.get("requested_skips") if isinstance(value, dict) else None
    if (
        not isinstance(skips, list)
        or not all(isinstance(item, str) for item in skips)
        or len(skips) != len(set(skips))
    ):
        raise WorkflowExecutionError("workflow checkpoint skip selection is invalid")
    return list(skips)


def _run_state_gate(run_dir: Path) -> None:
    try:
        state_path = run_state_path(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RunStateGateError(f"run state path could not be resolved safely: {exc}") from exc
    if state_path.is_symlink():
        raise RunStateGateError("run state must not be a symlink")
    try:
        state = load_run_state(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RunStateGateError(f"run state could not be read safely: {exc}") from exc
    status = str(state.get("status") or "")
    if status == PAUSED:
        raise RunStateGateError(
            "run is paused; inspect and clear the pause with gra-run-state before execution",
            status="paused",
        )
    if status == BLOCKED:
        raise RunStateGateError(
            "run is blocked; an operator must update run state before execution",
            status="blocked",
        )
    if status != ACTIVE:
        raise RunStateGateError(f"run state is unsupported: {status}")


def ensure_run_state_active(run_dir: Path) -> None:
    _run_state_gate(run_dir.resolve(strict=True))


def _stage_record(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": stage["id"],
        "status": "skipped_by_scope" if stage["status"] == "skipped_by_scope" else "pending",
        "attempt": 0,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "error_category": None,
        "output_artifacts": [],
    }


def _file_sha256(path: Path, *, label: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise WorkflowExecutionError(f"{label} must be a regular non-symlink file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARTIFACT_BYTES:
            raise WorkflowExecutionError(f"{label} must be a bounded regular file")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(fd)


def _command_implementations(lab_root: Path, plan: dict[str, Any]) -> list[dict[str, str]]:
    names = sorted({str(stage["command"][0]) for stage in plan["stages"]})
    implementations: list[dict[str, str]] = []
    for name in names:
        script = lab_root / "bin" / name
        implementations.append({"command": name, "sha256": _file_sha256(script, label=f"approved command {name}")})
    return implementations


def _new_checkpoint(
    plan: dict[str, Any], *, from_stage: str | None, until_stage: str | None
) -> tuple[dict[str, Any], list[str]]:
    stages = plan["stages"]
    by_id = {stage["id"]: stage for stage in stages}
    executable = [stage["id"] for stage in stages if stage["status"] != "skipped_by_scope"]
    if not executable:
        raise WorkflowExecutionError("workflow has no executable stages")
    start = from_stage or executable[0]
    end = until_stage or executable[-1]
    if start not in executable or end not in executable:
        raise WorkflowExecutionError("--from and --until must identify non-skipped workflow stages")
    dependencies = {stage["id"]: list(stage["depends_on"]) for stage in stages}

    def ancestors(stage_id: str) -> set[str]:
        result: set[str] = set()
        pending = list(dependencies[stage_id])
        while pending:
            item = pending.pop()
            if item not in result:
                result.add(item)
                pending.extend(dependencies[item])
        return result

    def descendants(stage_id: str) -> set[str]:
        result: set[str] = set()
        pending = [stage_id]
        while pending:
            parent = pending.pop()
            for child, child_dependencies in dependencies.items():
                if parent in child_dependencies and child not in result:
                    result.add(child)
                    pending.append(child)
        return result

    if from_stage and until_stage:
        if end != start and end not in descendants(start):
            raise WorkflowExecutionError("--until must be the same stage or a descendant of --from")
        selected_set = ({start} | descendants(start)).intersection({end} | ancestors(end))
    elif from_stage:
        selected_set = {start} | descendants(start)
    elif until_stage:
        selected_set = {end} | ancestors(end)
    else:
        selected_set = set(executable)
    selected_set.intersection_update(executable)
    selected = [stage_id for stage_id in executable if stage_id in selected_set]
    selected_set = set(selected)
    records = [_stage_record(stage) for stage in stages]
    record_by_id = {record["id"]: record for record in records}
    prerequisite_ids = set().union(*(ancestors(stage_id) for stage_id in selected)) - selected_set
    continuation_ids = descendants(end).intersection(executable) - selected_set if until_stage else set()
    for stage_id in executable:
        if stage_id in prerequisite_ids:
            record_by_id[stage_id]["status"] = "external_prerequisite"
        elif stage_id not in selected_set and stage_id not in continuation_ids:
            record_by_id[stage_id]["status"] = "out_of_range"
    for stage_id in selected:
        missing = [dep for dep in by_id[stage_id]["depends_on"] if dep not in selected_set and record_by_id[dep]["status"] != "external_prerequisite"]
        if missing:
            raise WorkflowExecutionError(f"stage {stage_id} has an unavailable dependency: {missing[0]}")
    checkpoint = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "run_id": plan["run_id"],
        "repo": plan["repo"],
        "generated_at": _utc_now(),
        "source": "gra-run-checkpoint",
        "profile": plan["profile"],
        "profile_version": plan["profile_version"],
        "definition_sha256": plan["definition_sha256"],
        "plan_fingerprint": plan_fingerprint(plan),
        "reports_dir": plan["reports_dir"],
        "status": "running",
        "requested_from": from_stage,
        "requested_until": until_stage,
        "requested_skips": [stage["id"] for stage in stages if stage["status"] == "skipped_by_scope"],
        "resume_stage": selected[0],
        "command_implementations": [],
        "external_input_artifacts": [],
        "stages": records,
    }
    return checkpoint, selected


def _load_checkpoint(run_dir: Path, plan: dict[str, Any], lab_root: Path) -> dict[str, Any]:
    path = checkpoint_path(run_dir, plan)
    if not path.is_file() or path.is_symlink():
        raise WorkflowExecutionError("workflow checkpoint is missing or unsafe")
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowExecutionError("workflow checkpoint must contain valid UTF-8 JSON") from exc
    if not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise WorkflowExecutionError("workflow checkpoint schema_version is unsupported")
    expected = {
        "run_id": plan["run_id"],
        "repo": plan["repo"],
        "profile": plan["profile"],
        "profile_version": plan["profile_version"],
        "definition_sha256": plan["definition_sha256"],
        "plan_fingerprint": plan_fingerprint(plan),
        "reports_dir": plan["reports_dir"],
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise WorkflowExecutionError("workflow checkpoint does not match the current run/profile/plan")
    if checkpoint.get("status") not in WORKFLOW_STATUSES or not isinstance(checkpoint.get("stages"), list):
        raise WorkflowExecutionError("workflow checkpoint status or stages are invalid")
    if checkpoint.get("command_implementations") != _command_implementations(lab_root, plan):
        raise WorkflowExecutionError("workflow checkpoint command implementation is stale or mismatched")
    plan_ids = [stage["id"] for stage in plan["stages"]]
    records = checkpoint["stages"]
    if [record.get("id") for record in records if isinstance(record, dict)] != plan_ids:
        raise WorkflowExecutionError("workflow checkpoint stage set/order does not match the plan")
    for record in records:
        if set(record) != {"id", "status", "attempt", "started_at", "ended_at", "exit_code", "error_category", "output_artifacts"}:
            raise WorkflowExecutionError("workflow checkpoint stage fields are invalid")
        if record["status"] not in STAGE_STATUSES or not isinstance(record["attempt"], int) or record["attempt"] < 0:
            raise WorkflowExecutionError("workflow checkpoint stage status/attempt is invalid")
        if not isinstance(record["output_artifacts"], list):
            raise WorkflowExecutionError("workflow checkpoint output artifacts are invalid")
        if record["status"] == "succeeded":
            expected_outputs = next(stage["outputs"] for stage in plan["stages"] if stage["id"] == record["id"])
            if [stamp.get("path") for stamp in record["output_artifacts"] if isinstance(stamp, dict)] != expected_outputs:
                raise WorkflowExecutionError(
                    f"workflow checkpoint output stamps do not match declared outputs: {record['id']}"
                )
            for stamp in record["output_artifacts"]:
                _validate_stamp(run_dir, stamp)
    external = checkpoint.get("external_input_artifacts")
    if not isinstance(external, list):
        raise WorkflowExecutionError("workflow checkpoint external inputs are invalid")
    for stamp in external:
        _validate_stamp(run_dir, stamp)
    if checkpoint["status"] == "succeeded":
        raise WorkflowExecutionError("workflow checkpoint is already complete")
    resume_stage = checkpoint.get("resume_stage")
    if resume_stage not in plan_ids:
        raise WorkflowExecutionError("workflow checkpoint resume stage is invalid")
    seen_resume = False
    for record in records:
        if record["id"] == resume_stage:
            seen_resume = True
        if seen_resume and record["status"] in {"failed", "blocked_dependency", "running"}:
            record.update({"status": "pending", "started_at": None, "ended_at": None, "exit_code": None, "error_category": None, "output_artifacts": []})
    checkpoint["status"] = "running"
    return checkpoint


def preflight_resume_checkpoint(run_dir: Path, plan: dict[str, Any], lab_root: Path) -> None:
    """Validate a resume checkpoint and its artifact stamps without writing state."""

    _load_checkpoint(run_dir.resolve(strict=True), plan, lab_root)


def _external_prerequisite_stamps(run_dir: Path, plan: dict[str, Any], checkpoint: dict[str, Any], selected: list[str]) -> list[dict[str, Any]]:
    selected_set = set(selected)
    output_producers = {output: stage["id"] for stage in plan["stages"] for output in stage["outputs"]}
    refs: set[str] = set()
    for stage in plan["stages"]:
        if stage["id"] not in selected_set:
            continue
        for required in stage["required_inputs"]:
            producer = output_producers.get(required)
            if producer and producer not in selected_set:
                refs.add(required)
    return [artifact_stamp(run_dir, ref) for ref in sorted(refs)]


def _reject_existing_outputs(run_dir: Path, plan: dict[str, Any], selected: list[str]) -> None:
    selected_set = set(selected)
    for stage in plan["stages"]:
        if stage["id"] not in selected_set:
            continue
        for ref in stage["outputs"]:
            if _safe_artifact(run_dir, ref, required=False) is not None:
                raise WorkflowExecutionError(
                    f"declared workflow output already exists: {ref}; use a fresh run or a supervised later --from range"
                )


def _default_runner(argv: list[str], cwd: Path) -> int:
    script = Path(argv[0])
    command = [sys.executable, str(script), *argv[1:]] if script.read_bytes().startswith(b"#!/usr/bin/env python3") else argv
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _command_argv(lab_root: Path, stage: dict[str, Any]) -> list[str]:
    command_name, *arguments = stage["command"]
    script = lab_root / "bin" / command_name
    if not script.is_file() or script.is_symlink():
        raise WorkflowExecutionError(f"approved workflow command is unavailable: {command_name}")
    return [str(script), *arguments]


def execute_workflow(
    run_dir: Path,
    plan: dict[str, Any],
    *,
    lab_root: Path,
    resume: bool = False,
    from_stage: str | None = None,
    until_stage: str | None = None,
    runner: Runner | None = None,
) -> tuple[dict[str, Any], int]:
    run_dir = run_dir.resolve(strict=True)
    _run_state_gate(run_dir)
    path = checkpoint_path(run_dir, plan)
    reports = path.parent
    reports.mkdir(parents=True, exist_ok=True)
    lock = reports / ".workflow-execution.lock"
    try:
        os.mkdir(lock, 0o700)
    except FileExistsError as exc:
        raise WorkflowExecutionError("another workflow execution is active or requires operator lock recovery") from exc
    try:
        if resume:
            if from_stage or until_stage:
                raise WorkflowExecutionError("--resume cannot override the checkpoint range")
            checkpoint = _load_checkpoint(run_dir, plan, lab_root)
            selected = [record["id"] for record in checkpoint["stages"] if record["status"] in {"pending", "failed", "blocked_dependency", "running"}]
            _reject_existing_outputs(run_dir, plan, selected)
        else:
            if path.exists() or path.is_symlink():
                raise WorkflowExecutionError("workflow checkpoint already exists; use --resume or a fresh run")
            checkpoint, selected = _new_checkpoint(plan, from_stage=from_stage, until_stage=until_stage)
            checkpoint["command_implementations"] = _command_implementations(lab_root, plan)
            _reject_existing_outputs(run_dir, plan, selected)
            checkpoint["external_input_artifacts"] = _external_prerequisite_stamps(run_dir, plan, checkpoint, selected)
        by_plan = {stage["id"]: stage for stage in plan["stages"]}
        records = {record["id"]: record for record in checkpoint["stages"]}
        run_stage = runner or _default_runner
        _write_checkpoint(run_dir, path, checkpoint, plan)
        for stage in plan["stages"]:
            stage_id = stage["id"]
            record = records[stage_id]
            if record["status"] != "pending" or stage_id not in selected:
                continue
            try:
                _run_state_gate(run_dir)
            except RunStateGateError as exc:
                gate_status = exc.status if exc.status in {"paused", "blocked"} else "blocked"
                checkpoint.update({"status": gate_status, "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, 5 if exc.status in {"paused", "blocked"} else 2
            if checkpoint["command_implementations"] != _command_implementations(lab_root, plan):
                checkpoint.update({"status": "blocked", "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, 2
            unsatisfied = [dep for dep in stage["depends_on"] if records[dep]["status"] not in TERMINAL_SUCCESS]
            if unsatisfied:
                record["status"] = "blocked_dependency"
                checkpoint.update({"status": "blocked", "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, 2
            for dependency in stage["depends_on"]:
                if records[dependency]["status"] == "succeeded":
                    try:
                        for stamp in records[dependency]["output_artifacts"]:
                            _validate_stamp(run_dir, stamp)
                    except WorkflowExecutionError:
                        checkpoint.update({"status": "blocked", "resume_stage": stage_id})
                        _write_checkpoint(run_dir, path, checkpoint, plan)
                        return checkpoint, 2
            record.update({"status": "running", "attempt": record["attempt"] + 1, "started_at": _utc_now(), "ended_at": None, "exit_code": None, "error_category": None, "output_artifacts": []})
            checkpoint["resume_stage"] = stage_id
            _write_checkpoint(run_dir, path, checkpoint, plan)
            try:
                exit_code = int(run_stage(_command_argv(lab_root, stage), run_dir))
            except KeyboardInterrupt:
                record.update({"status": "pending", "ended_at": _utc_now(), "exit_code": 130, "error_category": "interrupted"})
                checkpoint.update({"status": "paused", "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, 130
            record.update({"ended_at": _utc_now(), "exit_code": exit_code})
            if exit_code != 0:
                record.update({"status": "failed", "error_category": "stage_exit"})
                for later in checkpoint["stages"]:
                    if later["status"] == "pending" and stage_id in by_plan[later["id"]]["depends_on"]:
                        later["status"] = "blocked_dependency"
                checkpoint.update({"status": "blocked", "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, exit_code if 0 < exit_code < 126 else 1
            try:
                record["output_artifacts"] = [artifact_stamp(run_dir, ref) for ref in stage["outputs"]]
            except WorkflowExecutionError:
                record.update({"status": "failed", "exit_code": 1, "error_category": "missing_or_unsafe_output"})
                checkpoint.update({"status": "blocked", "resume_stage": stage_id})
                _write_checkpoint(run_dir, path, checkpoint, plan)
                return checkpoint, 2
            record["status"] = "succeeded"
            record["error_category"] = None
            next_pending = next(
                (item["id"] for item in checkpoint["stages"] if item["status"] in {"pending", "blocked_dependency", "failed", "running"}),
                None,
            )
            checkpoint["resume_stage"] = next_pending
            _write_checkpoint(run_dir, path, checkpoint, plan)
        remaining = [record["id"] for record in checkpoint["stages"] if record["status"] in {"pending", "blocked_dependency", "failed", "running"}]
        if remaining:
            checkpoint.update({"status": "paused", "resume_stage": remaining[0]})
        else:
            checkpoint.update({"status": "succeeded", "resume_stage": None})
        _write_checkpoint(run_dir, path, checkpoint, plan)
        return checkpoint, 0
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.rmdir(lock)

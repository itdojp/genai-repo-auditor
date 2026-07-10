from __future__ import annotations

import json
import os
import re
import stat
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

COMMAND_EVENTS_REL_PATH = Path("reports") / "command-events.jsonl"
SOURCE = "genai-repo-auditor"
SCHEMA_VERSION = "2"

# Keep this list broad enough for the all-stage event contract. Individual
# instrumentation is added incrementally, but the v2 reader/schema should not
# need to change for every new producer.
COMMAND_EVENT_COMMANDS = [
    "gra-adversarial-validate",
    "gra-agent-check",
    "gra-audit",
    "gra-batch",
    "gra-benchmark",
    "gra-chains",
    "gra-dashboard",
    "gra-doctor",
    "gra-efficacy-benchmark",
    "gra-evidence-graph",
    "gra-gapfill",
    "gra-import-findings",
    "gra-index",
    "gra-ingest",
    "gra-issues",
    "gra-metrics",
    "gra-no-findings",
    "gra-novelty",
    "gra-proofs",
    "gra-recon",
    "gra-remediate",
    "gra-research",
    "gra-run",
    "gra-run-state",
    "gra-sandbox-check",
    "gra-sarif",
    "gra-scan",
    "gra-scanner-triage",
    "gra-store",
    "gra-targets",
    "gra-taxonomy-preflight",
    "gra-trace",
    "gra-validate-report",
    "gra-variant",
    "gra-workflow-profile",
    "gra-worktree-check",
]
COMMAND_EVENT_PHASES = [
    "adversarial-validate",
    "apply-plan",
    "audit",
    "benchmark",
    "chain",
    "check",
    "dashboard",
    "dry-run",
    "evidence-graph",
    "exec",
    "execute",
    "gapfill",
    "generate",
    "goal",
    "import",
    "ingest",
    "list",
    "mark",
    "metrics",
    "patch-validate",
    "plan",
    "prepare",
    "preview",
    "proof",
    "recon",
    "remediate",
    "resume",
    "run-state",
    "sarif",
    "scan",
    "scanner-triage",
    "show",
    "store",
    "target-generation",
    "trace",
    "validate",
    "verify-plan",
]
COMMAND_EVENT_STATUSES = ["succeeded", "failed", "blocked", "skipped", "warning"]
EVENT_WRITE_FAILURE_MODES = ["block", "warn"]

_ALLOWED_EVENT_KEYS = {
    "schema_version",
    "event_id",
    "run_id",
    "repo",
    "command",
    "phase",
    "subject_id",
    "target_id",
    "started_at",
    "ended_at",
    "duration_ms",
    "exit_code",
    "status",
    "attempt",
    "retry_of",
    "worker_profile",
    "model",
    "effort",
    "sandbox_profile",
    "network_allowed",
    "prompt_hash",
    "input_artifact_refs",
    "output_artifact_refs",
    "artifact_paths",
    "redaction_count",
    "error_category",
    "source",
}
_FORBIDDEN_KEY_NAMES = {
    "authorization",
    "body_text",
    "chain_of_thought",
    "credential",
    "credentials",
    "env",
    "environment",
    "evidence",
    "finding_evidence",
    "issue_body",
    "issue_body_text",
    "patch",
    "patch_content",
    "private_reasoning",
    "proof_payload",
    "prompt",
    "raw_body",
    "raw_evidence",
    "raw_prompt",
    "raw_reasoning",
    "secret",
    "secrets",
    "token",
}
_SECRET_VALUE_RE = re.compile(
    r"(?:"
    r"ghp_[A-Za-z0-9_]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"
    r")"
)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:/@+=-]{0,127}$")
_EVENT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PROMPT_HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_ERROR_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class EventValidationError(ValueError):
    """Raised when an event would violate the public-safe event contract."""


class EventWriteError(RuntimeError):
    """Raised when a blocking event write fails."""


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


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "_").replace(" ", "_")


def _reject_secret_like_value(value: str, field_path: str) -> None:
    if _SECRET_VALUE_RE.search(value):
        raise EventValidationError(f"{field_path}: secret-like value is not allowed in command events")


def _validate_json_safe(value: Any, field_path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            normalized = _normalize_key(key_text)
            if normalized in _FORBIDDEN_KEY_NAMES:
                raise EventValidationError(f"{field_path}.{key_text}: field is explicitly forbidden in command events")
            if normalized not in _ALLOWED_EVENT_KEYS:
                raise EventValidationError(f"{field_path}.{key_text}: field is not allowed in command events")
            if key_text != normalized:
                raise EventValidationError(f"{field_path}.{key_text}: field name must use canonical snake_case")
            _validate_json_safe(child, f"{field_path}.{key_text}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_json_safe(child, f"{field_path}[{index}]")
    elif isinstance(value, str):
        _reject_secret_like_value(value, field_path)
    elif value is None or isinstance(value, (bool, int, float)):
        return
    else:
        raise EventValidationError(f"{field_path}: value must be JSON-serializable")


def _validate_safe_id(value: Any, field_path: str, *, allow_none: bool = True) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"{field_path}: must be a non-empty string")
    _reject_secret_like_value(value, field_path)
    if not _SAFE_ID_RE.fullmatch(value):
        raise EventValidationError(f"{field_path}: contains unsupported characters")


def validate_command_event_payload(event: Mapping[str, Any]) -> None:
    """Validate one event without echoing event values in diagnostics.

    The writer calls this before serialization and report validation calls it for
    records loaded from disk. It intentionally rejects arbitrary fields so raw
    prompts, environments, issue bodies, proofs, patches, and evidence cannot be
    smuggled into command-events.jsonl.
    """

    if not isinstance(event, Mapping):
        raise EventValidationError("event: must be an object")
    _validate_json_safe(dict(event), "event")

    schema_version = event.get("schema_version")
    if schema_version not in {"1", "2"}:
        raise EventValidationError("event.schema_version: must be '1' or '2'")
    command = event.get("command")
    if command not in COMMAND_EVENT_COMMANDS:
        raise EventValidationError("event.command: command is not part of the command-event contract")
    phase = event.get("phase")
    if phase not in COMMAND_EVENT_PHASES:
        raise EventValidationError("event.phase: phase is not part of the command-event contract")

    for key in ["run_id", "command", "phase", "source"]:
        if key in event:
            _validate_safe_id(event.get(key), f"event.{key}", allow_none=False)
    if "repo" in event and event.get("repo") not in {None, ""}:
        _validate_safe_id(event.get("repo"), "event.repo", allow_none=False)
    for key in ["target_id", "subject_id", "worker_profile", "model", "effort", "sandbox_profile", "retry_of"]:
        if key in event:
            _validate_safe_id(event.get(key), f"event.{key}", allow_none=True)

    if event.get("source") != SOURCE:
        raise EventValidationError("event.source: must be genai-repo-auditor")
    if not isinstance(event.get("duration_ms"), int) or isinstance(event.get("duration_ms"), bool) or event.get("duration_ms") < 0:
        raise EventValidationError("event.duration_ms: must be a non-negative integer")
    if not isinstance(event.get("exit_code"), int) or isinstance(event.get("exit_code"), bool):
        raise EventValidationError("event.exit_code: must be an integer")

    for key in ["artifact_paths", "input_artifact_refs", "output_artifact_refs"]:
        if key in event and event.get(key) is not None:
            values = event.get(key)
            if not isinstance(values, list) or not all(isinstance(item, str) and item.strip() for item in values):
                raise EventValidationError(f"event.{key}: must be a list of non-empty strings")

    if schema_version == "2":
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not _EVENT_ID_RE.fullmatch(event_id):
            raise EventValidationError("event.event_id: must be a UUID string")
        status = event.get("status")
        if status not in COMMAND_EVENT_STATUSES:
            raise EventValidationError("event.status: invalid status")
        attempt = event.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise EventValidationError("event.attempt: must be an integer >= 1")
        retry_of = event.get("retry_of")
        if retry_of is not None and (not isinstance(retry_of, str) or not _EVENT_ID_RE.fullmatch(retry_of)):
            raise EventValidationError("event.retry_of: must be null or a UUID string")
        network_allowed = event.get("network_allowed")
        if network_allowed is not None and not isinstance(network_allowed, bool):
            raise EventValidationError("event.network_allowed: must be boolean or null")
        redaction_count = event.get("redaction_count")
        if redaction_count is not None and (
            not isinstance(redaction_count, int) or isinstance(redaction_count, bool) or redaction_count < 0
        ):
            raise EventValidationError("event.redaction_count: must be a non-negative integer or null")
        prompt_hash = event.get("prompt_hash")
        if prompt_hash is not None and (not isinstance(prompt_hash, str) or not _PROMPT_HASH_RE.fullmatch(prompt_hash)):
            raise EventValidationError("event.prompt_hash: must be a sha256 hex digest")
        error_category = event.get("error_category")
        if error_category is not None and (not isinstance(error_category, str) or not _ERROR_CATEGORY_RE.fullmatch(error_category)):
            raise EventValidationError("event.error_category: invalid error category")


def _safe_run_relative_ref(run_dir: Path, value: Path | str, field_path: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve(strict=False).relative_to(run_dir.resolve(strict=False))
        except (OSError, ValueError) as exc:
            raise EventValidationError(f"{field_path}: artifact path must stay under the run directory") from exc
    else:
        rel = candidate
    if not rel.parts:
        raise EventValidationError(f"{field_path}: artifact path must be non-empty")
    if rel.is_absolute() or ".." in rel.parts:
        raise EventValidationError(f"{field_path}: artifact path must be relative and must not contain '..'")
    current = run_dir
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise EventValidationError(f"{field_path}: artifact path must not contain symlink components")
    ref = rel.as_posix()
    _reject_secret_like_value(ref, field_path)
    return ref


def _safe_run_relative_refs(run_dir: Path, values: Iterable[Path | str] | None, field_name: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values or []):
        ref = _safe_run_relative_ref(run_dir, value, f"event.{field_name}[{index}]")
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def start_command_event() -> tuple[str, float]:
    return utc_now(), time.perf_counter()


def _status_from_exit(exit_code: int) -> str:
    return "succeeded" if int(exit_code) == 0 else "failed"


def build_command_event(
    run_dir: Path,
    *,
    command: str,
    phase: str,
    started_at: str,
    started_perf: float,
    exit_code: int,
    target_id: str | None = None,
    subject_id: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    artifact_paths: Iterable[Path | str] | None = None,
    input_artifact_paths: Iterable[Path | str] | None = None,
    output_artifact_paths: Iterable[Path | str] | None = None,
    status: str | None = None,
    attempt: int = 1,
    retry_of: str | None = None,
    worker_profile: str | None = None,
    sandbox_profile: str | None = None,
    network_allowed: bool | None = None,
    prompt_hash: str | None = None,
    redaction_count: int | None = None,
    error_category: str | None = None,
) -> dict[str, Any]:
    ctx = load_context(run_dir)
    ended_at = utc_now()
    duration_ms = max(0, int(round((time.perf_counter() - started_perf) * 1000)))
    output_refs = _safe_run_relative_refs(
        run_dir,
        output_artifact_paths if output_artifact_paths is not None else artifact_paths,
        "output_artifact_refs",
    )
    input_refs = _safe_run_relative_refs(run_dir, input_artifact_paths, "input_artifact_refs")
    event = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "run_id": str(ctx.get("run_id") or run_dir.name),
        "repo": str(ctx.get("repo") or ""),
        "command": command,
        "phase": phase,
        "subject_id": subject_id or target_id,
        "target_id": target_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "exit_code": int(exit_code),
        "status": status or _status_from_exit(exit_code),
        "attempt": int(attempt),
        "retry_of": retry_of,
        "worker_profile": worker_profile,
        "model": model,
        "effort": effort,
        "sandbox_profile": sandbox_profile,
        "network_allowed": network_allowed,
        "prompt_hash": prompt_hash,
        "input_artifact_refs": input_refs,
        "output_artifact_refs": output_refs,
        # Backward-compatible alias for v1 readers and metrics.
        "artifact_paths": output_refs,
        "redaction_count": redaction_count,
        "error_category": error_category,
        "source": SOURCE,
    }
    validate_command_event_payload(event)
    return event




def _acquire_event_append_lock(path: Path, *, timeout_seconds: float = 10.0) -> Path:
    lock_path = path.with_name(f".{path.name}.lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.mkdir(lock_path, 0o700)
            return lock_path
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise EventWriteError(f"timed out waiting for command event append lock: {lock_path}") from exc
            time.sleep(0.01)

def _atomic_append_jsonl(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = _acquire_event_append_lock(path)
    try:
        try:
            if stat.S_ISLNK(path.lstat().st_mode):
                raise EventWriteError(f"command event path must not be a symlink: {path}")
        except FileNotFoundError:
            # The event file does not exist yet; it will be created below.
            pass
        line = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            mode = os.fstat(fd).st_mode
            if not stat.S_ISREG(mode):
                raise EventWriteError(f"command event path must be a regular file: {path}")
            offset = 0
            while offset < len(data):
                written = os.write(fd, data[offset:])
                if written <= 0:
                    raise EventWriteError("command event write made no progress")
                offset += written
        finally:
            os.close(fd)
    finally:
        try:
            os.rmdir(lock_path)
        except FileNotFoundError:
            # The lock was already removed during error handling; there is no cleanup left.
            pass


def append_command_event(
    run_dir: Path,
    *,
    command: str,
    phase: str,
    started_at: str,
    started_perf: float,
    exit_code: int,
    target_id: str | None = None,
    subject_id: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    artifact_paths: Iterable[Path | str] | None = None,
    input_artifact_paths: Iterable[Path | str] | None = None,
    output_artifact_paths: Iterable[Path | str] | None = None,
    status: str | None = None,
    attempt: int = 1,
    retry_of: str | None = None,
    worker_profile: str | None = None,
    sandbox_profile: str | None = None,
    network_allowed: bool | None = None,
    prompt_hash: str | None = None,
    redaction_count: int | None = None,
    error_category: str | None = None,
    failure_mode: str = "block",
) -> Path | None:
    """Append a sanitized v2 command event.

    `failure_mode="block"` is the default for command-completion events: a
    malformed or unwritable observability record fails closed instead of letting
    the command report success with missing auditability. `failure_mode="warn"`
    is reserved for future non-critical status producers; it emits a warning to
    stderr and returns None.
    """

    if failure_mode not in EVENT_WRITE_FAILURE_MODES:
        raise EventWriteError(f"unsupported event write failure mode: {failure_mode}")
    try:
        event = build_command_event(
            run_dir,
            command=command,
            phase=phase,
            target_id=target_id,
            subject_id=subject_id,
            started_at=started_at,
            started_perf=started_perf,
            exit_code=exit_code,
            model=model,
            effort=effort,
            artifact_paths=artifact_paths,
            input_artifact_paths=input_artifact_paths,
            output_artifact_paths=output_artifact_paths,
            status=status,
            attempt=attempt,
            retry_of=retry_of,
            worker_profile=worker_profile,
            sandbox_profile=sandbox_profile,
            network_allowed=network_allowed,
            prompt_hash=prompt_hash,
            redaction_count=redaction_count,
            error_category=error_category,
        )
        path = command_events_path(run_dir)
        _atomic_append_jsonl(path, event)
        return path
    except Exception as exc:  # noqa: BLE001 - deliberately controls write-failure semantics.
        if failure_mode == "warn":
            print(f"WARNING: command event was not written: {exc}", file=sys.stderr)
            return None
        raise EventWriteError(f"command event write failed: {exc}") from exc


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

from __future__ import annotations

import hashlib
import contextlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from gralib import load_context, utc_now
from report_safety import iter_secret_findings


SCHEMA_VERSION = "1"
MAX_STAGES = 64
SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
SAFE_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9_./{}:=+-]{1,128}$")
COMMAND_CONTRACTS = {
    ("gra-recon", "--run", "{run}"),
    ("gra-targets", "--run", "{run}", "--generate"),
}
FORBIDDEN_ARGUMENTS = {
    "--allow-public", "--apply", "--apply-plan", "--execute", "--network", "--publish",
}
SENSITIVE_ARGUMENT_NAMES = ("auth", "credential", "password", "secret", "token")
DEFINITION_KEYS = {"schema_version", "profile", "profile_version", "description", "stages"}
STAGE_KEYS = {
    "id", "command", "depends_on", "required_inputs", "outputs", "skippable",
    "skip_reason", "network_allowed", "mutation",
}


class WorkflowPlanError(RuntimeError):
    pass


def _safe_rel(value: Any, field: str) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or "\x00" in text
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
        or path.is_absolute()
        or PureWindowsPath(text).is_absolute()
        or any(part in {"", ".", ".."} for part in text.split("/"))
        or len(text) > 240
    ):
        raise WorkflowPlanError(f"{field} must be a safe run-relative path")
    return text


def _reports_dir(run_dir: Path, context: dict[str, Any]) -> Path:
    rel = _safe_rel(context.get("reports_dir") or "reports", "reports_dir")
    current = run_dir
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowPlanError("reports_dir must not contain symlink components")
    reports = run_dir / rel
    target_rel = _safe_rel(context.get("target_repo_dir") or "repo", "target_repo_dir")
    reports_resolved = reports.resolve(strict=False)
    target_resolved = (run_dir / target_rel).resolve(strict=False)
    if (
        reports_resolved == target_resolved
        or reports_resolved in target_resolved.parents
        or target_resolved in reports_resolved.parents
    ):
        raise WorkflowPlanError("reports_dir and target_repo_dir must not overlap")
    return reports


def profile_path(root: Path, profile: str) -> Path:
    if not SAFE_ID_RE.fullmatch(profile):
        raise WorkflowPlanError("profile id is invalid")
    path = root / "templates" / "workflows" / f"{profile}.json"
    if not path.is_file() or path.is_symlink():
        raise WorkflowPlanError(f"unknown workflow profile: {profile}")
    return path


def load_profile(root: Path, profile: str) -> tuple[dict[str, Any], Path, str]:
    path = profile_path(root, profile)
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowPlanError("workflow profile must contain valid UTF-8 JSON") from exc
    validate_profile(value)
    if value["profile"] != profile:
        raise WorkflowPlanError("workflow profile id does not match its resource name")
    return value, path, hashlib.sha256(raw).hexdigest()


def validate_profile(value: Any) -> list[str]:
    if not isinstance(value, dict) or set(value) != DEFINITION_KEYS:
        raise WorkflowPlanError("workflow profile fields do not match the versioned contract")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise WorkflowPlanError("workflow profile schema_version is unsupported")
    if not SAFE_ID_RE.fullmatch(str(value.get("profile") or "")):
        raise WorkflowPlanError("workflow profile id is invalid")
    if not SAFE_VERSION_RE.fullmatch(str(value.get("profile_version") or "")):
        raise WorkflowPlanError("workflow profile version must use semantic x.y.z form")
    if not isinstance(value.get("description"), str) or not value["description"].strip() or len(value["description"]) > 240:
        raise WorkflowPlanError("workflow profile description must be a bounded non-empty string")
    stages = value.get("stages")
    if not isinstance(stages, list) or not stages or len(stages) > MAX_STAGES:
        raise WorkflowPlanError(f"workflow profile must contain 1..{MAX_STAGES} stages")
    stage_ids: set[str] = set()
    outputs: dict[str, str] = {}
    for index, stage in enumerate(stages):
        field = f"stages[{index}]"
        if not isinstance(stage, dict) or set(stage) != STAGE_KEYS:
            raise WorkflowPlanError(f"{field} fields do not match the stage contract")
        stage_id = str(stage.get("id") or "")
        if not SAFE_ID_RE.fullmatch(stage_id) or stage_id in stage_ids:
            raise WorkflowPlanError(f"{field}.id is invalid or duplicated")
        stage_ids.add(stage_id)
        command = stage.get("command")
        if (
            not isinstance(command, list)
            or not command
            or len(command) > 32
            or not all(isinstance(item, str) and SAFE_ARG_RE.fullmatch(item) for item in command)
        ):
            raise WorkflowPlanError(f"{field}.command must be a non-empty argv array")
        if tuple(command) not in COMMAND_CONTRACTS:
            raise WorkflowPlanError(f"{field}.command does not match an approved planning-stage argv contract")
        for argument in command[1:]:
            scrubbed = argument.replace("{run}", "").replace("{reports_dir}", "").replace("{target_repo_dir}", "")
            if "{" in scrubbed or "}" in scrubbed:
                raise WorkflowPlanError(f"{field}.command contains an unknown placeholder")
            name, _, argument_value = argument.partition("=")
            if any(marker in name.lower() for marker in SENSITIVE_ARGUMENT_NAMES):
                raise WorkflowPlanError(f"{field}.command contains a credential-like argument")
            if argument_value:
                value_path = PurePosixPath(argument_value)
                if value_path.is_absolute() or ".." in value_path.parts:
                    raise WorkflowPlanError(f"{field}.command contains an unsafe path argument")
        if any(
            item in FORBIDDEN_ARGUMENTS
            or any(item.startswith(f"{forbidden}=") for forbidden in FORBIDDEN_ARGUMENTS)
            for item in command[1:]
        ):
            raise WorkflowPlanError(f"{field}.command contains a prohibited mutation/network argument")
        if stage.get("network_allowed") is not False or stage.get("mutation") != "local-artifacts-only":
            raise WorkflowPlanError(f"{field} must remain offline and local-artifacts-only")
        for key in ("depends_on", "required_inputs", "outputs"):
            items = stage.get(key)
            if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                raise WorkflowPlanError(f"{field}.{key} must be a list of strings")
            if len(items) != len(set(items)):
                raise WorkflowPlanError(f"{field}.{key} must be a unique list")
            if key == "depends_on":
                if any(not SAFE_ID_RE.fullmatch(item) for item in items):
                    raise WorkflowPlanError(f"{field}.depends_on must contain valid stage ids")
            else:
                for item_index, item in enumerate(items):
                    _safe_rel(item, f"{field}.{key}[{item_index}]")
            if key == "outputs" and any(not str(item).startswith("{reports_dir}/") for item in items):
                raise WorkflowPlanError(f"{field}.outputs must stay under the configured reports_dir")
        if not isinstance(stage.get("skippable"), bool):
            raise WorkflowPlanError(f"{field}.skippable must be boolean")
        if stage["skippable"] and (
            not isinstance(stage.get("skip_reason"), str)
            or not stage["skip_reason"].strip()
            or len(stage["skip_reason"]) > 240
        ):
            raise WorkflowPlanError(f"{field}.skip_reason is required for scoped skips")
        if not stage["skippable"] and stage.get("skip_reason") is not None:
            raise WorkflowPlanError(f"{field}.skip_reason must be null when the stage is not skippable")
        for output in stage["outputs"]:
            if output in outputs:
                raise WorkflowPlanError(f"output {output} is produced by multiple stages")
            outputs[output] = stage_id
    by_id = {stage["id"]: stage for stage in stages}
    for stage in stages:
        for dependency in stage["depends_on"]:
            if dependency not in by_id or dependency == stage["id"]:
                raise WorkflowPlanError(f"stage {stage['id']} has an unknown or self dependency")
    order: list[str] = []
    state: dict[str, int] = {}
    def visit(stage_id: str) -> None:
        if state.get(stage_id) == 1:
            raise WorkflowPlanError("workflow profile dependency graph contains a cycle")
        if state.get(stage_id) == 2:
            return
        state[stage_id] = 1
        for dependency in by_id[stage_id]["depends_on"]:
            visit(dependency)
        state[stage_id] = 2
        order.append(stage_id)
    for stage in stages:
        visit(stage["id"])
    return order


def _dependency_ancestors(by_id: dict[str, dict[str, Any]], stage_id: str) -> set[str]:
    result: set[str] = set()
    pending = list(by_id[stage_id]["depends_on"])
    while pending:
        dependency = pending.pop()
        if dependency in result:
            continue
        result.add(dependency)
        pending.extend(by_id[dependency]["depends_on"])
    return result


def _existing_input(run_dir: Path, rel: str, *, require_dir: bool = False) -> bool:
    candidate = run_dir / rel
    current = run_dir
    for part in PurePosixPath(rel).parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowPlanError("workflow required input must not contain symlink components")
    if not candidate.exists():
        return False
    try:
        candidate.resolve(strict=True).relative_to(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise WorkflowPlanError("workflow required input must stay under the run directory") from exc
    if require_dir and not candidate.is_dir():
        raise WorkflowPlanError("workflow required input must be a directory")
    return True


def _expand_path(value: str, context: dict[str, Any]) -> str:
    replacements = {
        "{reports_dir}": _safe_rel(context.get("reports_dir") or "reports", "reports_dir"),
        "{target_repo_dir}": _safe_rel(context.get("target_repo_dir") or "repo", "target_repo_dir"),
    }
    result = value
    for marker, replacement in replacements.items():
        result = result.replace(marker, replacement)
    if "{" in result or "}" in result:
        raise WorkflowPlanError("workflow artifact path contains an unknown placeholder")
    return _safe_rel(result, "workflow artifact path")


def _expand_argument(value: str, context: dict[str, Any]) -> str:
    result = value.replace("{run}", ".")
    result = result.replace("{reports_dir}", _safe_rel(context.get("reports_dir") or "reports", "reports_dir"))
    result = result.replace("{target_repo_dir}", _safe_rel(context.get("target_repo_dir") or "repo", "target_repo_dir"))
    if "{" in result or "}" in result or not SAFE_ARG_RE.fullmatch(result):
        raise WorkflowPlanError("workflow command contains an unsafe placeholder or argument")
    return result


def build_plan(run_dir: Path, definition: dict[str, Any], *, definition_ref: str, digest: str, skips: list[str]) -> dict[str, Any]:
    run_dir = run_dir.resolve(strict=True)
    context_path = run_dir / "context.json"
    if not context_path.is_file() or context_path.is_symlink():
        raise WorkflowPlanError("run must contain a regular non-symlink context.json")
    context = load_context(run_dir)
    validated_reports = _reports_dir(run_dir, context)
    reports_ref = validated_reports.relative_to(run_dir).as_posix()
    target_repo_ref = _safe_rel(context.get("target_repo_dir") or "repo", "target_repo_dir")
    order = validate_profile(definition)
    by_id = {stage["id"]: stage for stage in definition["stages"]}
    skip_set = set(skips)
    if len(skip_set) != len(skips) or not skip_set.issubset(by_id):
        raise WorkflowPlanError("skip list contains a duplicate or unknown stage")
    for stage_id in skip_set:
        if not by_id[stage_id]["skippable"]:
            raise WorkflowPlanError(f"stage {stage_id} is not skippable")
    for stage_id in order:
        if stage_id in skip_set:
            continue
        blocked = sorted(_dependency_ancestors(by_id, stage_id).intersection(skip_set))
        if blocked:
            raise WorkflowPlanError(f"stage {stage_id} depends on skipped stage {blocked[0]}")
    expanded_outputs = {
        _expand_path(output, context): stage["id"]
        for stage in definition["stages"] for output in stage["outputs"]
        if stage["id"] not in skip_set
    }
    planned: list[dict[str, Any]] = []
    for stage_id in order:
        stage = by_id[stage_id]
        inputs = [_expand_path(item, context) for item in stage["required_inputs"]]
        if stage_id not in skip_set:
            for required in inputs:
                producer = expanded_outputs.get(required)
                if producer is None and not _existing_input(run_dir, required, require_dir=(required == target_repo_ref)):
                    raise WorkflowPlanError(f"stage {stage_id} has unsatisfied required input: {required}")
                if producer is not None and producer not in _dependency_ancestors(by_id, stage_id):
                    raise WorkflowPlanError(f"stage {stage_id} required input is not provided by a dependency")
        command = [_expand_argument(item, context) for item in stage["command"]]
        planned.append({
            "id": stage_id,
            "status": "skipped_by_scope" if stage_id in skip_set else "planned",
            "depends_on": list(stage["depends_on"]),
            "required_inputs": inputs,
            "outputs": [_expand_path(item, context) for item in stage["outputs"]],
            "command": command,
            "skip_reason": stage["skip_reason"] if stage_id in skip_set else None,
            "network_allowed": False,
            "mutation": "local-artifacts-only",
        })
    plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(context.get("run_id") or run_dir.name),
        "repo": str(context.get("repo") or ""),
        "generated_at": utc_now(),
        "source": "gra-run-plan",
        "profile": definition["profile"],
        "profile_version": definition["profile_version"],
        "definition_ref": definition_ref,
        "definition_sha256": digest,
        "reports_dir": reports_ref,
        "mode": "plan",
        "safety": {"commands_executed": False, "network_allowed": False, "github_mutation_allowed": False, "raw_payloads_copied": False},
        "summary": {"stage_count": len(planned), "planned_count": sum(x["status"] == "planned" for x in planned), "skipped_by_scope_count": len(skip_set)},
        "stages": planned,
    }
    if list(iter_secret_findings(plan, field_path="workflow_plan")):
        raise WorkflowPlanError("workflow plan contains secret-like values")
    return plan


def render_markdown(plan: dict[str, Any]) -> str:
    lines = ["# Workflow Plan", "", "Planning only: no stage command was executed.", "", f"- Profile: `{plan['profile']}` `{plan['profile_version']}`", f"- Stages: {plan['summary']['stage_count']}", "", "| Stage | Status | Dependencies | Command |", "|---|---|---|---|"]
    for stage in plan["stages"]:
        argv = " ".join(stage["command"])
        lines.append(f"| {stage['id']} | {stage['status']} | {', '.join(stage['depends_on']) or '-'} | `{argv}` |")
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise WorkflowPlanError("workflow plan temporary path is not a regular file")
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise WorkflowPlanError("workflow plan write made no progress")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise WorkflowPlanError("workflow plan destination must be a regular non-symlink file")
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def write_plan(run_dir: Path, plan: dict[str, Any]) -> tuple[Path, Path]:
    run_dir = run_dir.resolve(strict=True)
    reports_ref = _safe_rel(plan.get("reports_dir"), "workflow_plan.reports_dir")
    reports = run_dir / reports_ref
    current = run_dir
    for part in PurePosixPath(reports_ref).parts:
        current = current / part
        if current.is_symlink():
            raise WorkflowPlanError("workflow plan reports_dir must not contain symlink components")
    json_path, markdown_path = reports / "workflow-plan.json", reports / "WORKFLOW_PLAN.md"
    reports.mkdir(parents=True, exist_ok=True)
    lock = reports / ".workflow-plan.lock"
    deadline = time.monotonic() + 10.0
    while True:
        try:
            os.mkdir(lock, 0o700)
            break
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise WorkflowPlanError("timed out waiting for workflow plan lock") from exc
            time.sleep(0.01)
    try:
        _atomic_write(json_path, (json.dumps(plan, indent=2, sort_keys=True) + "\n").encode())
        _atomic_write(markdown_path, render_markdown(plan).encode())
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.rmdir(lock)
    return json_path, markdown_path

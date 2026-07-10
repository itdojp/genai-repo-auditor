from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sandbox_profiles import PROFILE_IDS

SCHEMA_VERSION = "1"
NETWORK_POLICIES = ("disabled", "explicit-allow")
RESULT_CLASSIFICATIONS = ("scanner-leads", "posture-evidence", "sbom-data")
PLANNING_SANDBOX_PROFILES = ("container", "gvisor", "vm")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SAFE_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")
_SAFE_METADATA_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:/@+=-]{0,127}$")
_SECRET_VALUE_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)"
)
_UNSAFE_ARGUMENT_RE = re.compile(r"[\x00-\x1f;&|`$<>]")
_PLACEHOLDERS = ("{target}", "{output}")
_MAX_CONTEXT_BYTES = 1_000_000


class ScannerAdapterError(RuntimeError):
    """Raised when a scanner adapter or plan violates the safe planning contract."""


@dataclass(frozen=True)
class ScannerAdapter:
    id: str
    display_name: str
    executable: str
    version_args: tuple[str, ...]
    supported_operating_systems: tuple[str, ...]
    network_required: bool
    approved_sandbox_profiles: tuple[str, ...]
    argument_template: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int
    max_results: int
    output_format: str
    ingest_tool: str
    result_classification: str
    secret_handling: str
    exit_semantics: tuple[tuple[str, str], ...]


ADAPTERS: dict[str, ScannerAdapter] = {
    "gitleaks": ScannerAdapter(
        id="gitleaks",
        display_name="Gitleaks directory scan",
        executable="gitleaks",
        version_args=("version",),
        supported_operating_systems=("linux", "darwin", "windows"),
        network_required=False,
        approved_sandbox_profiles=("container", "gvisor", "vm"),
        argument_template=(
            "dir",
            "{target}",
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--exit-code",
            "10",
            "--report-format",
            "json",
            "--report-path",
            "{output}",
        ),
        timeout_seconds=300,
        max_output_bytes=10_000_000,
        max_results=1_000,
        output_format="json",
        ingest_tool="gitleaks",
        result_classification="scanner-leads",
        secret_handling="full tool redaction plus gra-ingest normalization redaction",
        exit_semantics=(("0", "completed-no-leads"), ("10", "completed-with-leads"), ("other", "scanner-failure")),
    ),
    "syft": ScannerAdapter(
        id="syft",
        display_name="Syft filesystem SBOM",
        executable="syft",
        version_args=("version",),
        supported_operating_systems=("linux", "darwin", "windows"),
        network_required=False,
        approved_sandbox_profiles=("container", "gvisor", "vm"),
        argument_template=("{target}", "-o", "cyclonedx-json={output}"),
        timeout_seconds=300,
        max_output_bytes=25_000_000,
        max_results=10_000,
        output_format="cyclonedx",
        ingest_tool="syft",
        result_classification="sbom-data",
        secret_handling="gra-ingest normalization and bounded dependency posture summaries",
        exit_semantics=(("0", "completed"), ("other", "scanner-failure")),
    ),
}


def current_operating_system() -> str:
    value = platform.system().lower()
    return "windows" if value.startswith("win") else value


def _validate_argument_token(token: str) -> None:
    if not token or _UNSAFE_ARGUMENT_RE.search(token):
        raise ScannerAdapterError("adapter command arguments must be non-empty shell-free tokens")
    scrubbed = token
    for placeholder in _PLACEHOLDERS:
        scrubbed = scrubbed.replace(placeholder, "")
    if "{" in scrubbed or "}" in scrubbed:
        raise ScannerAdapterError("adapter command argument contains an unknown placeholder")


def _validate_safe_metadata(value: object, *, field: str) -> str:
    text = str(value or "")
    if not _SAFE_METADATA_RE.fullmatch(text):
        raise ScannerAdapterError(f"{field} contains unsupported characters")
    if _SECRET_VALUE_RE.search(text):
        raise ScannerAdapterError(f"{field} must not contain secret-like values")
    return text


def validate_adapter(adapter: ScannerAdapter) -> None:
    if not _SAFE_ID_RE.fullmatch(adapter.id):
        raise ScannerAdapterError("adapter id is invalid")
    if not _SAFE_EXECUTABLE_RE.fullmatch(adapter.executable):
        raise ScannerAdapterError("adapter executable must be a bare executable name")
    if not adapter.display_name.strip():
        raise ScannerAdapterError("adapter display name must not be empty")
    if not adapter.version_args:
        raise ScannerAdapterError("adapter version check must use an argument array")
    for token in (*adapter.version_args, *adapter.argument_template):
        _validate_argument_token(token)
    if "{target}" not in " ".join(adapter.argument_template):
        raise ScannerAdapterError("adapter command must declare a target placeholder")
    if "{output}" not in " ".join(adapter.argument_template):
        raise ScannerAdapterError("adapter command must declare an output placeholder")
    if not adapter.supported_operating_systems or not set(adapter.supported_operating_systems).issubset(
        {"linux", "darwin", "windows"}
    ):
        raise ScannerAdapterError("adapter must declare at least one supported operating system")
    if not adapter.approved_sandbox_profiles or not set(adapter.approved_sandbox_profiles).issubset(
        PLANNING_SANDBOX_PROFILES
    ):
        raise ScannerAdapterError("adapter must use planning-safe sandbox profiles")
    if adapter.result_classification not in RESULT_CLASSIFICATIONS:
        raise ScannerAdapterError("adapter result classification is invalid")
    if min(adapter.timeout_seconds, adapter.max_output_bytes, adapter.max_results) <= 0:
        raise ScannerAdapterError("adapter limits must be positive")
    if not all(value.strip() for value in (adapter.output_format, adapter.ingest_tool, adapter.secret_handling)):
        raise ScannerAdapterError("adapter output, ingest, and secret-handling metadata must not be empty")
    if not adapter.exit_semantics:
        raise ScannerAdapterError("adapter exit semantics must not be empty")


for _adapter in ADAPTERS.values():
    validate_adapter(_adapter)


def adapter_by_id(adapter_id: str) -> ScannerAdapter:
    try:
        return ADAPTERS[adapter_id]
    except KeyError as exc:
        raise ScannerAdapterError(f"unknown scanner adapter: {adapter_id}") from exc


def _reject_symlink_components(path: Path, *, field: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ScannerAdapterError(f"{field} must not contain symlink components")


def validate_run_directory(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ScannerAdapterError(f"run directory does not exist: {run_dir}")
    _reject_symlink_components(run_dir, field="run directory")
    return run_dir


def _load_safe_context(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "context.json"
    if path.is_symlink() or not path.is_file():
        raise ScannerAdapterError("context.json must be a regular non-symlink file under the run directory")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ScannerAdapterError("unable to open context.json safely") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ScannerAdapterError("context.json must be a regular non-symlink file under the run directory")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_CONTEXT_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > _MAX_CONTEXT_BYTES:
        raise ScannerAdapterError("context.json exceeds the planning size limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScannerAdapterError("context.json must contain valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ScannerAdapterError("context.json must contain a JSON object")
    data.setdefault("run_id", run_dir.name)
    data.setdefault("target_repo_dir", "repo")
    data.setdefault("reports_dir", "reports")
    return data


def _safe_run_relative_path(run_dir: Path, value: object, *, field: str, require_directory: bool) -> tuple[Path, str]:
    raw = Path(str(value or ""))
    if not raw.parts or ".." in raw.parts:
        raise ScannerAdapterError(f"{field} must be a non-empty path under the run directory")
    if raw.is_absolute():
        try:
            lexical_relative = raw.relative_to(run_dir.absolute())
        except ValueError as exc:
            raise ScannerAdapterError(f"{field} must stay under the run directory") from exc
        candidate = raw
    else:
        lexical_relative = raw
        candidate = run_dir / raw
    if any(part.startswith("-") for part in lexical_relative.parts):
        raise ScannerAdapterError(f"{field} must not contain leading-dash path components")
    run_root = run_dir.resolve(strict=False)
    try:
        candidate.resolve(strict=False).relative_to(run_root)
    except (OSError, ValueError) as exc:
        raise ScannerAdapterError(f"{field} must stay under the run directory") from exc
    current = run_dir
    for part in lexical_relative.parts:
        current = current / part
        if current.is_symlink():
            raise ScannerAdapterError(f"{field} must not contain symlink components")
    if require_directory and candidate.exists() and not candidate.is_dir():
        raise ScannerAdapterError(f"{field} must be a directory")
    relative_text = lexical_relative.as_posix()
    if _SECRET_VALUE_RE.search(relative_text):
        raise ScannerAdapterError(f"{field} must not contain secret-like values")
    return candidate, relative_text


def _adapter_contract(adapter: ScannerAdapter, *, path_env: str | None = None) -> dict[str, Any]:
    validate_adapter(adapter)
    operating_system = current_operating_system()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": adapter.id,
        "display_name": adapter.display_name,
        "executable": adapter.executable,
        "version_check": [adapter.executable, *adapter.version_args],
        "command_template": [adapter.executable, *adapter.argument_template],
        "supported_operating_systems": list(adapter.supported_operating_systems),
        "network_required": adapter.network_required,
        "approved_sandbox_profiles": list(adapter.approved_sandbox_profiles),
        "target_access": "read-only",
        "read_path_templates": ["<target_repo_dir>"],
        "write_path_templates": [f"<reports_dir>/scanner-results/raw/{adapter.id}.json"],
        "output_format": adapter.output_format,
        "ingest_tool": adapter.ingest_tool,
        "result_classification": adapter.result_classification,
        "secret_handling": adapter.secret_handling,
        "timeout_seconds": adapter.timeout_seconds,
        "max_output_bytes": adapter.max_output_bytes,
        "max_results": adapter.max_results,
        "exit_semantics": {code: meaning for code, meaning in adapter.exit_semantics},
        "readiness": {
            "operating_system": operating_system,
            "operating_system_supported": operating_system in adapter.supported_operating_systems,
            "executable_available": shutil.which(adapter.executable, path=path_env) is not None,
            "version_check_executed": False,
        },
    }


def list_adapters(*, path_env: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "list",
        "scanner_executed": False,
        "network_accessed": False,
        "adapters": [_adapter_contract(ADAPTERS[key], path_env=path_env) for key in sorted(ADAPTERS)],
    }


def _render_argument(token: str, *, target: str, output: str) -> str:
    return token.replace("{target}", target).replace("{output}", output)


def build_scan_plan(
    run_dir: Path,
    *,
    adapter_id: str,
    sandbox_profile: str,
    network_policy: str = "disabled",
    path_env: str | None = None,
) -> dict[str, Any]:
    run_dir = validate_run_directory(run_dir)
    if sandbox_profile not in PROFILE_IDS:
        raise ScannerAdapterError(f"unknown sandbox profile: {sandbox_profile}")
    if network_policy not in NETWORK_POLICIES:
        raise ScannerAdapterError(f"unknown network policy: {network_policy}")
    adapter = adapter_by_id(adapter_id)
    if sandbox_profile not in adapter.approved_sandbox_profiles:
        raise ScannerAdapterError(f"adapter {adapter.id} is not approved for sandbox profile {sandbox_profile}")
    if adapter.network_required and network_policy != "explicit-allow":
        raise ScannerAdapterError(f"adapter {adapter.id} requires explicit network approval")
    if not adapter.network_required and network_policy != "disabled":
        raise ScannerAdapterError(f"adapter {adapter.id} does not declare network access")

    context = _load_safe_context(run_dir)
    run_id = _validate_safe_metadata(context.get("run_id") or run_dir.name, field="run_id")
    target_value = context.get("repo_dir") or context.get("target_repo_dir") or "repo"
    target_path, target_ref = _safe_run_relative_path(
        run_dir,
        target_value,
        field="target repository path",
        require_directory=True,
    )
    reports_value = context.get("reports_dir") or "reports"
    _reports_path, reports_ref = _safe_run_relative_path(
        run_dir,
        reports_value,
        field="reports directory",
        require_directory=True,
    )
    output_ref = f"{reports_ref}/scanner-results/raw/{adapter.id}.json"
    _safe_run_relative_path(run_dir, output_ref, field="raw scanner output path", require_directory=False)
    command = [
        adapter.executable,
        *(
            _render_argument(token, target=target_ref, output=output_ref)
            for token in adapter.argument_template
        ),
    ]
    for token in command:
        _validate_argument_token(token)

    contract = _adapter_contract(adapter, path_env=path_env)
    readiness = contract["readiness"]
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "plan",
        "scanner_executed": False,
        "network_accessed": False,
        "run_id": run_id,
        "adapter": contract,
        "sandbox_profile": sandbox_profile,
        "network_policy": network_policy,
        "planning_readiness": {
            "operating_system_supported": readiness["operating_system_supported"],
            "executable_available": readiness["executable_available"],
            "target_exists": target_path.is_dir(),
            "sandbox_profile_selected": sandbox_profile,
            "sandbox_readiness_executed": False,
        },
        "working_directory": ".",
        "command": command,
        "command_display": shlex.join(command),
        "read_paths": [target_ref],
        "write_paths": [output_ref],
        "raw_output_path": output_ref,
        "ingest": {
            "tool": adapter.ingest_tool,
            "format": adapter.output_format,
            "source_path": output_ref,
        },
    }


def planning_environment_path() -> str | None:
    return os.environ.get("PATH")

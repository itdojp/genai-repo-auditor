from __future__ import annotations

import json
import os
import platform
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

from gralib import write_run_artifact_json
from platform_support import detect_environment
from sandbox_profiles import PROFILE_IDS, detect_visible_credential_env
from scanner_adapters import (
    NETWORK_POLICIES,
    ScannerAdapterError,
    adapter_by_id,
    resolve_scan_layout,
    scan_layout_safety,
    validate_run_directory,
)


SCHEMA_VERSION = "1"
EXECUTION_PROFILES = ("container", "gvisor")
READINESS_STATES = ("ready", "blocked", "experimental", "unsupported")
REASON_CODES = (
    "runtime_missing",
    "runtime_remote",
    "runtime_unavailable",
    "image_not_configured",
    "image_not_digest_pinned",
    "image_not_local",
    "platform_unsupported",
    "sandbox_unsupported",
    "gvisor_missing",
    "target_unsafe",
    "reports_path_unsafe",
    "output_path_unsafe",
    "staging_path_unsafe",
    "path_overlap",
    "resource_limits_unavailable",
    "credential_environment_present",
    "network_policy_unsupported",
    "ready",
)
CONTAINER_IMAGES = {
    "gitleaks": "ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f",
    "syft": "ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb",
}
CONTAINER_TOOL_VERSIONS = {
    "gitleaks": "8.30.1",
    "syft": "1.46.0",
}
REMOTE_RUNTIME_ENV_NAMES = ("CONTAINER_HOST", "DOCKER_CONTEXT", "DOCKER_HOST", "PODMAN_HOST")
_IMAGE_RE = re.compile(r"^[a-z0-9.-]+/[a-z0-9./-]+@sha256:[a-f0-9]{64}$")
_SAFE_IMAGE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9./:@_-]{0,255}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SAFE_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")
_SAFE_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_MAX_REPORT_BYTES = 256 * 1024

_NEXT_STEPS = {
    "runtime_missing": "Install an approved local Docker or Podman runtime during the setup phase.",
    "runtime_remote": "Unset remote container runtime configuration and use an approved local-only endpoint.",
    "runtime_unavailable": "Repair the approved local container runtime before scanner execution.",
    "image_not_configured": "Configure a reviewed immutable scanner image for this adapter.",
    "image_not_digest_pinned": "Replace the scanner image reference with an exact sha256 digest pin.",
    "image_not_local": "Pre-pull the reviewed digest-pinned image during the approved setup phase.",
    "platform_unsupported": "Use a platform listed as supported by the scanner execution support matrix.",
    "sandbox_unsupported": "Select the container or gvisor scanner execution profile supported on this platform.",
    "gvisor_missing": "Install and approve local runsc before using the gvisor profile.",
    "target_unsafe": "Use an existing non-symlink target directory contained by the run directory.",
    "reports_path_unsafe": "Use a non-symlink reports directory contained by the run directory.",
    "output_path_unsafe": "Use a fresh run with an unused non-symlink raw scanner output path.",
    "staging_path_unsafe": "Remove or replace the unsafe scanner staging path during the setup phase.",
    "path_overlap": "Separate the target repository and reports directories before execution.",
    "resource_limits_unavailable": "Use a supported local runtime/profile that enforces the bounded scanner limits.",
    "credential_environment_present": "Remove credential-like environment variables before scanner execution.",
    "network_policy_unsupported": "Use the disabled network policy for offline scanner execution.",
}


class ScannerReadinessError(ScannerAdapterError):
    """Raised when scanner readiness cannot be evaluated or consumed safely."""


def safe_runtime_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    allowed_names = {
        "HOME",
        "LANG",
        "LOGNAME",
        "PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "WINDIR",
        "XDG_RUNTIME_DIR",
    }
    return {key: value for key, value in env.items() if key.upper() in allowed_names or key.upper().startswith("LC_")}


def docker_endpoint(env: dict[str, str]) -> str:
    if os.name == "nt":
        return "npipe:////./pipe/docker_engine"
    candidates: list[Path] = []
    xdg = env.get("XDG_RUNTIME_DIR")
    if xdg:
        candidates.append(Path(xdg) / "docker.sock")
    home = Path.home()
    candidates.extend((home / ".docker" / "run" / "docker.sock", Path("/var/run/docker.sock")))
    for candidate in candidates:
        try:
            if stat.S_ISSOCK(candidate.stat().st_mode):
                return f"unix://{candidate}"
        except OSError:
            continue
    return "unix:///var/run/docker.sock"


def runtime_candidates(path_env: str | None, env: dict[str, str]) -> list[tuple[list[str], str]]:
    candidates: list[tuple[list[str], str]] = []
    docker = shutil.which("docker", path=path_env)
    if docker:
        candidates.append(([docker, "--host", docker_endpoint(env)], "docker"))
    podman = shutil.which("podman", path=path_env)
    if podman and platform.system().lower() == "linux":
        candidates.append(([podman, "--remote=false"], "podman"))
    return candidates


def _remote_runtime_environment(env: dict[str, str]) -> list[str]:
    normalized = {str(name).upper(): value for name, value in env.items()}
    present: list[str] = []
    for name in REMOTE_RUNTIME_ENV_NAMES:
        value = str(normalized.get(name) or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if name == "DOCKER_CONTEXT" and lowered in {"default", "desktop-linux"}:
            continue
        if lowered.startswith(("unix://", "npipe://")):
            continue
        present.append(name)
    return present


def _probe_command(command: list[str], *, env: dict[str, str], timeout: int = 10) -> int | None:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.returncode


def select_local_runtime_with_image(
    *,
    image: str,
    path_env: str | None,
    source_env: dict[str, str],
    candidates: list[tuple[list[str], str]] | None = None,
) -> tuple[list[str], str]:
    remote_names = _remote_runtime_environment(source_env)
    if remote_names:
        raise ScannerReadinessError("runtime_remote")
    candidates = runtime_candidates(path_env, source_env) if candidates is None else candidates
    if not candidates:
        raise ScannerReadinessError("runtime_missing")
    safe_env = safe_runtime_environment(source_env)
    healthy: list[tuple[list[str], str]] = []
    for prefix, runtime in candidates:
        if _probe_command([*prefix, "version"], env=safe_env) == 0:
            healthy.append((prefix, runtime))
    if not healthy:
        raise ScannerReadinessError("runtime_unavailable")
    for prefix, runtime in healthy:
        if _probe_command([*prefix, "image", "inspect", image], env=safe_env, timeout=20) == 0:
            return prefix, runtime
    raise ScannerReadinessError("image_not_local")


def _add_reason(reasons: list[str], code: str) -> None:
    if code not in REASON_CODES:
        raise ScannerReadinessError(f"unknown scanner readiness reason code: {code}")
    if code not in reasons:
        reasons.append(code)


def _evaluate_scanner_readiness(
    run_dir: Path,
    *,
    adapter_id: str,
    sandbox_profile: str,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], tuple[list[str], str] | None]:
    safe_run_dir = validate_run_directory(run_dir).absolute()
    adapter = adapter_by_id(adapter_id)
    source_env = dict(os.environ if env is None else env)
    execution_environment = detect_environment()
    reasons: list[str] = []

    platform_level = {
        "linux": "supported",
        "wsl2": "supported",
        "macos": "experimental",
        "native-windows": "experimental",
    }.get(execution_environment, "unsupported")
    if platform_level == "unsupported":
        _add_reason(reasons, "platform_unsupported")

    if sandbox_profile not in EXECUTION_PROFILES:
        _add_reason(reasons, "sandbox_unsupported")
    elif sandbox_profile not in adapter.approved_sandbox_profiles:
        _add_reason(reasons, "sandbox_unsupported")
    elif sandbox_profile == "gvisor" and execution_environment not in {"linux", "wsl2"}:
        _add_reason(reasons, "sandbox_unsupported")

    if network_policy != "disabled" or adapter.network_required:
        _add_reason(reasons, "network_policy_unsupported")

    image = CONTAINER_IMAGES.get(adapter.id)
    image_configured = bool(image)
    image_digest_pinned = bool(image and _IMAGE_RE.fullmatch(image))
    if not image_configured:
        _add_reason(reasons, "image_not_configured")
    elif not image_digest_pinned:
        _add_reason(reasons, "image_not_digest_pinned")

    path_safety = scan_layout_safety(safe_run_dir, adapter_id=adapter.id)
    target_safe = path_safety["target_safe"]
    reports_safe = path_safety["reports_safe"]
    output_safe = path_safety["output_safe"]
    staging_safe = path_safety["staging_safe"]
    paths_overlap = path_safety["overlap"]
    if not target_safe:
        _add_reason(reasons, "target_unsafe")
    if not reports_safe:
        _add_reason(reasons, "reports_path_unsafe")
    if not output_safe:
        _add_reason(reasons, "output_path_unsafe")
    if not staging_safe:
        _add_reason(reasons, "staging_path_unsafe")
    if paths_overlap:
        _add_reason(reasons, "path_overlap")

    credential_names = sorted(detect_visible_credential_env(source_env))
    if credential_names:
        _add_reason(reasons, "credential_environment_present")
    remote_runtime_names = _remote_runtime_environment(source_env)
    if remote_runtime_names:
        _add_reason(reasons, "runtime_remote")

    candidates = runtime_candidates(path_env, source_env)
    runtime_candidates_found = bool(candidates)
    runtime_probe_executed = False
    runtime_healthy = False
    selected_runtime: str | None = None
    selected_prefix: list[str] | None = None
    image_local = False
    if (
        image_digest_pinned
        and platform_level != "unsupported"
        and sandbox_profile in EXECUTION_PROFILES
        and "sandbox_unsupported" not in reasons
        and not remote_runtime_names
        and not credential_names
        and network_policy == "disabled"
        and target_safe
        and reports_safe
        and output_safe
        and staging_safe
        and not paths_overlap
    ):
        runtime_probe_executed = bool(candidates)
        try:
            selected_prefix, selected_runtime = select_local_runtime_with_image(
                image=str(image),
                path_env=path_env,
                source_env=source_env,
                candidates=candidates,
            )
            runtime_healthy = True
            image_local = True
        except ScannerReadinessError as exc:
            reason = str(exc)
            runtime_healthy = reason == "image_not_local"
            _add_reason(reasons, reason)
    elif not runtime_candidates_found:
        _add_reason(reasons, "runtime_missing")

    gvisor_available = shutil.which("runsc", path=path_env) is not None
    if sandbox_profile == "gvisor" and not gvisor_available:
        _add_reason(reasons, "gvisor_missing")

    execution_controls_configured = sandbox_profile in EXECUTION_PROFILES and not (
        sandbox_profile == "gvisor" and execution_environment not in {"linux", "wsl2"}
    )
    resource_limits_configured = execution_controls_configured
    if not resource_limits_configured:
        _add_reason(reasons, "resource_limits_unavailable")

    if platform_level == "unsupported":
        state = "unsupported"
    elif reasons:
        state = "blocked"
    elif platform_level == "experimental":
        state = "experimental"
    else:
        state = "ready"
    ordered_reasons = [code for code in REASON_CODES if code in reasons]
    if not ordered_reasons:
        ordered_reasons = ["ready"]

    report = {
        "schema_version": SCHEMA_VERSION,
        "mode": "readiness",
        "scanner_executed": False,
        "network_accessed": False,
        "adapter_id": adapter.id,
        "sandbox_profile": sandbox_profile,
        "network_policy": network_policy,
        "state": state,
        "reason_codes": ordered_reasons,
        "next_steps": [_NEXT_STEPS[code] for code in ordered_reasons if code in _NEXT_STEPS],
        "platform": {
            "environment": execution_environment,
            "support": platform_level,
        },
        "adapter": {
            "execution_source": "container",
            "executable": adapter.executable,
            "host_executable_required": False,
            "host_executable_available": shutil.which(adapter.executable, path=path_env) is not None,
        },
        "runtime": {
            "required": True,
            "candidate_available": runtime_candidates_found,
            "healthy_available": runtime_healthy,
            "selected": selected_runtime,
            "local_only": not remote_runtime_names,
            "remote_environment_names": remote_runtime_names,
            "probe_executed": runtime_probe_executed,
        },
        "image": {
            "configured": image_configured,
            "digest_pinned": image_digest_pinned,
            "reference": image,
            "local_available": image_local,
        },
        "paths": {
            "target_safe": target_safe,
            "reports_safe": reports_safe,
            "output_safe": output_safe,
            "staging_safe": staging_safe,
            "overlap": paths_overlap,
        },
        "sandbox": {
            "network_disabled": network_policy == "disabled",
            "target_read_only": execution_controls_configured,
            "root_filesystem_read_only": execution_controls_configured,
            "capabilities_dropped": execution_controls_configured,
            "resource_limits_configured": resource_limits_configured,
            "gvisor_available": gvisor_available,
        },
        "credentials": {
            "environment_present": bool(credential_names),
            "environment_names": credential_names,
            "values_exposed": False,
        },
        "probes": {
            "runtime_probe_executed": runtime_probe_executed,
            "scanner_executed": False,
            "version_check_executed": runtime_probe_executed,
            "image_pulled": False,
            "remote_runtime_contacted": False,
        },
    }
    validate_scanner_readiness_report(report)
    selection = (selected_prefix, selected_runtime) if selected_prefix is not None and selected_runtime else None
    return report, selection


def evaluate_scanner_readiness(
    run_dir: Path,
    *,
    adapter_id: str,
    sandbox_profile: str,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    report, _selection = _evaluate_scanner_readiness(
        run_dir,
        adapter_id=adapter_id,
        sandbox_profile=sandbox_profile,
        network_policy=network_policy,
        path_env=path_env,
        env=env,
    )
    return report


def evaluate_scanner_readiness_for_execution(
    run_dir: Path,
    *,
    adapter_id: str,
    sandbox_profile: str,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], tuple[list[str], str] | None]:
    """Return the public report and its in-memory local runtime selection."""

    return _evaluate_scanner_readiness(
        run_dir,
        adapter_id=adapter_id,
        sandbox_profile=sandbox_profile,
        network_policy=network_policy,
        path_env=path_env,
        env=env,
    )


def validate_scanner_readiness_report(report: Any) -> None:
    if not isinstance(report, dict):
        raise ScannerReadinessError("scanner readiness report must be an object")
    expected = {
        "schema_version",
        "mode",
        "scanner_executed",
        "network_accessed",
        "adapter_id",
        "sandbox_profile",
        "network_policy",
        "state",
        "reason_codes",
        "next_steps",
        "platform",
        "adapter",
        "runtime",
        "image",
        "paths",
        "sandbox",
        "credentials",
        "probes",
    }
    if set(report) != expected:
        raise ScannerReadinessError("scanner readiness report fields are invalid")
    if report.get("schema_version") != SCHEMA_VERSION or report.get("mode") != "readiness":
        raise ScannerReadinessError("scanner readiness report version or mode is invalid")
    if report.get("scanner_executed") is not False or report.get("network_accessed") is not False:
        raise ScannerReadinessError("scanner readiness report must remain non-executing and offline")
    if not _SAFE_ID_RE.fullmatch(str(report.get("adapter_id") or "")):
        raise ScannerReadinessError("scanner readiness adapter_id is invalid")
    try:
        expected_adapter = adapter_by_id(str(report["adapter_id"]))
    except ScannerAdapterError as exc:
        raise ScannerReadinessError("scanner readiness adapter_id is not approved") from exc
    if report.get("sandbox_profile") not in PROFILE_IDS:
        raise ScannerReadinessError("scanner readiness sandbox_profile is invalid")
    if report.get("network_policy") not in NETWORK_POLICIES:
        raise ScannerReadinessError("scanner readiness network_policy is invalid")
    if report.get("state") not in READINESS_STATES:
        raise ScannerReadinessError("scanner readiness state is invalid")
    reasons = report.get("reason_codes")
    if not isinstance(reasons, list) or not reasons or len(reasons) > len(REASON_CODES):
        raise ScannerReadinessError("scanner readiness reason_codes are invalid")
    if len(set(reasons)) != len(reasons) or any(code not in REASON_CODES for code in reasons):
        raise ScannerReadinessError("scanner readiness reason_codes are invalid")
    if report.get("state") in {"ready", "experimental"} and reasons != ["ready"]:
        raise ScannerReadinessError("ready scanner readiness reports must use only the ready reason code")
    if report.get("state") in {"blocked", "unsupported"} and "ready" in reasons:
        raise ScannerReadinessError("blocked scanner readiness reports must not use the ready reason code")
    if reasons != [code for code in REASON_CODES if code in reasons]:
        raise ScannerReadinessError("scanner readiness reason_codes are not in canonical order")
    next_steps = report.get("next_steps")
    if not isinstance(next_steps, list) or len(next_steps) > len(REASON_CODES):
        raise ScannerReadinessError("scanner readiness next_steps are invalid")
    if any(not isinstance(item, str) or not item or len(item) > 256 for item in next_steps):
        raise ScannerReadinessError("scanner readiness next_steps are invalid")
    expected_steps = [_NEXT_STEPS[code] for code in reasons if code in _NEXT_STEPS]
    if next_steps != expected_steps:
        raise ScannerReadinessError("scanner readiness next_steps do not match reason_codes")

    platform_report = _closed_object(report.get("platform"), {"environment", "support"}, "platform")
    if platform_report.get("environment") not in {
        "linux",
        "wsl2",
        "wsl-unknown",
        "macos",
        "native-windows",
        "unsupported",
    }:
        raise ScannerReadinessError("scanner readiness platform.environment is invalid")
    if platform_report.get("support") not in {"supported", "experimental", "unsupported"}:
        raise ScannerReadinessError("scanner readiness platform.support is invalid")
    expected_platform_support = {
        "linux": "supported",
        "wsl2": "supported",
        "macos": "experimental",
        "native-windows": "experimental",
    }.get(str(platform_report["environment"]), "unsupported")
    if platform_report["support"] != expected_platform_support:
        raise ScannerReadinessError("scanner readiness platform support state is inconsistent")

    adapter_report = _closed_object(
        report.get("adapter"),
        {"execution_source", "executable", "host_executable_required", "host_executable_available"},
        "adapter",
    )
    if adapter_report.get("execution_source") != "container":
        raise ScannerReadinessError("scanner readiness adapter.execution_source is invalid")
    if not _SAFE_EXECUTABLE_RE.fullmatch(str(adapter_report.get("executable") or "")):
        raise ScannerReadinessError("scanner readiness adapter.executable is invalid")
    if adapter_report["executable"] != expected_adapter.executable:
        raise ScannerReadinessError("scanner readiness adapter.executable does not match the approved adapter")
    _require_booleans(adapter_report, {"host_executable_required", "host_executable_available"}, "adapter")
    if adapter_report["host_executable_required"] is not False:
        raise ScannerReadinessError("scanner readiness host executable must remain optional for container execution")

    runtime_report = _closed_object(
        report.get("runtime"),
        {
            "required",
            "candidate_available",
            "healthy_available",
            "selected",
            "local_only",
            "remote_environment_names",
            "probe_executed",
        },
        "runtime",
    )
    _require_booleans(
        runtime_report,
        {"required", "candidate_available", "healthy_available", "local_only", "probe_executed"},
        "runtime",
    )
    if runtime_report["required"] is not True or runtime_report.get("selected") not in {None, "docker", "podman"}:
        raise ScannerReadinessError("scanner readiness runtime selection is invalid")
    _validate_env_names(runtime_report.get("remote_environment_names"), "runtime.remote_environment_names")
    if runtime_report["local_only"] != (not runtime_report["remote_environment_names"]):
        raise ScannerReadinessError("scanner readiness runtime local-only state is inconsistent")
    if runtime_report["healthy_available"] and not runtime_report["candidate_available"]:
        raise ScannerReadinessError("scanner readiness healthy runtime requires a runtime candidate")
    if runtime_report["probe_executed"] and not runtime_report["candidate_available"]:
        raise ScannerReadinessError("scanner readiness runtime probe requires a runtime candidate")

    image_report = _closed_object(
        report.get("image"),
        {"configured", "digest_pinned", "reference", "local_available"},
        "image",
    )
    _require_booleans(image_report, {"configured", "digest_pinned", "local_available"}, "image")
    image_reference = image_report.get("reference")
    if image_reference is not None and (
        not isinstance(image_reference, str)
        or len(image_reference) > 256
        or not _SAFE_IMAGE_REF_RE.fullmatch(image_reference)
    ):
        raise ScannerReadinessError("scanner readiness image.reference is invalid")
    if image_report["digest_pinned"] != bool(image_reference and _IMAGE_RE.fullmatch(image_reference)):
        raise ScannerReadinessError("scanner readiness image digest state is inconsistent")
    if image_report["configured"] != bool(image_reference):
        raise ScannerReadinessError("scanner readiness image configured state is inconsistent")
    if image_reference != CONTAINER_IMAGES.get(expected_adapter.id):
        raise ScannerReadinessError("scanner readiness image reference does not match the approved adapter")
    if image_report["local_available"] and not image_report["digest_pinned"]:
        raise ScannerReadinessError("scanner readiness local image must be digest-pinned")

    paths_report = _closed_object(
        report.get("paths"),
        {"target_safe", "reports_safe", "output_safe", "staging_safe", "overlap"},
        "paths",
    )
    _require_booleans(paths_report, set(paths_report), "paths")

    sandbox_report = _closed_object(
        report.get("sandbox"),
        {
            "network_disabled",
            "target_read_only",
            "root_filesystem_read_only",
            "capabilities_dropped",
            "resource_limits_configured",
            "gvisor_available",
        },
        "sandbox",
    )
    _require_booleans(sandbox_report, set(sandbox_report), "sandbox")
    controls_expected = report["sandbox_profile"] in EXECUTION_PROFILES and not (
        report["sandbox_profile"] == "gvisor"
        and platform_report["environment"] not in {"linux", "wsl2"}
    )
    for control in (
        "target_read_only",
        "root_filesystem_read_only",
        "capabilities_dropped",
        "resource_limits_configured",
    ):
        if sandbox_report[control] != controls_expected:
            raise ScannerReadinessError(f"scanner readiness sandbox.{control} state is inconsistent")
    if sandbox_report["network_disabled"] != (report["network_policy"] == "disabled"):
        raise ScannerReadinessError("scanner readiness sandbox network state is inconsistent")
    if report["state"] in {"ready", "experimental"}:
        for invariant in (
            "network_disabled",
            "target_read_only",
            "root_filesystem_read_only",
            "capabilities_dropped",
            "resource_limits_configured",
        ):
            if sandbox_report[invariant] is not True:
                raise ScannerReadinessError(f"scanner readiness sandbox.{invariant} must remain enabled")

    credentials_report = _closed_object(
        report.get("credentials"),
        {"environment_present", "environment_names", "values_exposed"},
        "credentials",
    )
    _require_booleans(credentials_report, {"environment_present", "values_exposed"}, "credentials")
    _validate_env_names(credentials_report.get("environment_names"), "credentials.environment_names")
    if credentials_report["environment_present"] != bool(credentials_report["environment_names"]):
        raise ScannerReadinessError("scanner readiness credential environment state is inconsistent")
    if credentials_report["values_exposed"] is not False:
        raise ScannerReadinessError("scanner readiness must not expose credential values")

    probes_report = _closed_object(
        report.get("probes"),
        {
            "runtime_probe_executed",
            "scanner_executed",
            "version_check_executed",
            "image_pulled",
            "remote_runtime_contacted",
        },
        "probes",
    )
    _require_booleans(probes_report, set(probes_report), "probes")
    if any(probes_report[name] for name in ("scanner_executed", "image_pulled", "remote_runtime_contacted")):
        raise ScannerReadinessError("scanner readiness probes must remain offline and non-executing")
    if probes_report["runtime_probe_executed"] != runtime_report["probe_executed"]:
        raise ScannerReadinessError("scanner readiness runtime probe state is inconsistent")
    if probes_report["version_check_executed"] != runtime_report["probe_executed"]:
        raise ScannerReadinessError("scanner readiness version probe state is inconsistent")
    expected_flags = {
        "platform_unsupported": platform_report["support"] == "unsupported",
        "sandbox_unsupported": not controls_expected,
        "gvisor_missing": report["sandbox_profile"] == "gvisor" and not sandbox_report["gvisor_available"],
        "target_unsafe": not paths_report["target_safe"],
        "reports_path_unsafe": not paths_report["reports_safe"],
        "output_path_unsafe": not paths_report["output_safe"],
        "staging_path_unsafe": not paths_report["staging_safe"],
        "path_overlap": paths_report["overlap"],
        "resource_limits_unavailable": not sandbox_report["resource_limits_configured"],
        "credential_environment_present": credentials_report["environment_present"],
        "network_policy_unsupported": not sandbox_report["network_disabled"],
        "runtime_remote": not runtime_report["local_only"],
        "runtime_missing": not runtime_report["candidate_available"],
        "runtime_unavailable": (
            runtime_report["probe_executed"]
            and runtime_report["candidate_available"]
            and not runtime_report["healthy_available"]
        ),
        "image_not_local": (
            runtime_report["probe_executed"]
            and runtime_report["healthy_available"]
            and not image_report["local_available"]
        ),
        "image_not_configured": not image_report["configured"],
        "image_not_digest_pinned": image_report["configured"] and not image_report["digest_pinned"],
    }
    for reason, expected_flag in expected_flags.items():
        if (reason in reasons) != expected_flag:
            raise ScannerReadinessError(f"scanner readiness {reason} state is inconsistent")
    if (runtime_report["selected"] is not None) != image_report["local_available"]:
        raise ScannerReadinessError("scanner readiness selected runtime and local image state are inconsistent")
    if image_report["local_available"] and not runtime_report["healthy_available"]:
        raise ScannerReadinessError("scanner readiness local image requires a healthy runtime")
    if report["state"] in {"ready", "experimental"}:
        if (
            runtime_report["selected"] is None
            or not runtime_report["candidate_available"]
            or not runtime_report["probe_executed"]
            or not runtime_report["local_only"]
            or not image_report["local_available"]
            or not paths_report["target_safe"]
            or not paths_report["reports_safe"]
            or not paths_report["output_safe"]
            or not paths_report["staging_safe"]
            or paths_report["overlap"]
            or credentials_report["environment_present"]
        ):
            raise ScannerReadinessError("ready scanner readiness report contains a blocked execution dimension")
    if report["state"] == "unsupported" and platform_report["support"] != "unsupported":
        raise ScannerReadinessError("unsupported scanner readiness state requires an unsupported platform")
    if report["state"] == "experimental" and platform_report["support"] != "experimental":
        raise ScannerReadinessError("experimental scanner readiness state requires an experimental platform")
    if report["state"] == "ready" and platform_report["support"] != "supported":
        raise ScannerReadinessError("ready scanner readiness state requires a supported platform")
    if len(json.dumps(report, ensure_ascii=False).encode("utf-8")) > _MAX_REPORT_BYTES:
        raise ScannerReadinessError("scanner readiness report exceeds the size limit")


def _closed_object(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ScannerReadinessError(f"scanner readiness {name} fields are invalid")
    return value


def _require_booleans(value: dict[str, Any], fields: set[str], name: str) -> None:
    if any(type(value.get(field)) is not bool for field in fields):
        raise ScannerReadinessError(f"scanner readiness {name} boolean fields are invalid")


def _validate_env_names(value: Any, name: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) > 64
        or len(set(value)) != len(value)
        or value != sorted(value)
        or any(not isinstance(item, str) or not _SAFE_ENV_NAME_RE.fullmatch(item) for item in value)
    ):
        raise ScannerReadinessError(f"scanner readiness {name} is invalid")


def scanner_readiness_path(run_dir: Path, adapter_id: str) -> Path:
    adapter = adapter_by_id(adapter_id)
    layout = resolve_scan_layout(validate_run_directory(run_dir), adapter_id=adapter.id)
    reports = layout["reports_path"]
    return reports / "scanner-readiness" / f"{adapter.id}.json"


def scanner_readiness_persistence_safe(run_dir: Path, report: dict[str, Any]) -> bool:
    """Return whether a report can be persisted without touching target/unsafe paths."""

    validate_scanner_readiness_report(report)
    try:
        safety = scan_layout_safety(
            validate_run_directory(run_dir),
            adapter_id=str(report["adapter_id"]),
        )
        # Re-resolve the canonical layout so repo_dir/target_repo_dir ambiguity
        # cannot be hidden behind independent boolean path checks.
        resolve_scan_layout(run_dir, adapter_id=str(report["adapter_id"]))
    except (OSError, ScannerAdapterError):
        return False
    return bool(safety["target_safe"] and safety["reports_safe"] and not safety["overlap"])


def write_scanner_readiness_report(run_dir: Path, report: dict[str, Any]) -> Path:
    validate_scanner_readiness_report(report)
    if not scanner_readiness_persistence_safe(run_dir, report):
        raise ScannerReadinessError("scanner readiness report persistence is unsafe")
    path = scanner_readiness_path(run_dir, str(report["adapter_id"]))
    write_run_artifact_json(validate_run_directory(run_dir), path, report)
    return path


def load_scanner_readiness_report(
    run_dir: Path,
    adapter_id: str,
    *,
    sandbox_profile: str | None = None,
    network_policy: str | None = None,
) -> dict[str, Any] | None:
    path = scanner_readiness_path(run_dir, adapter_id)
    if not path.exists() and not path.is_symlink():
        return None
    report = read_scanner_readiness_report(path)
    if report.get("adapter_id") != adapter_id:
        raise ScannerReadinessError("scanner readiness report adapter_id does not match its path")
    if sandbox_profile is not None and report.get("sandbox_profile") != sandbox_profile:
        return None
    if network_policy is not None and report.get("network_policy") != network_policy:
        return None
    return report


def read_scanner_readiness_report(path: Path) -> dict[str, Any]:
    """Read one bounded report without following a final or managed-parent symlink."""

    path = Path(path)
    if path.parent.is_symlink():
        raise ScannerReadinessError("scanner readiness report directory must be a non-symlink directory")
    if path.is_symlink() or not path.is_file():
        raise ScannerReadinessError("scanner readiness report must be a regular non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ScannerReadinessError("scanner readiness report must be a regular non-symlink file")
        if opened.st_size > _MAX_REPORT_BYTES:
            raise ScannerReadinessError("scanner readiness report exceeds the size limit")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            raw = handle.read(_MAX_REPORT_BYTES + 1)
        if len(raw) > _MAX_REPORT_BYTES:
            raise ScannerReadinessError("scanner readiness report exceeds the size limit")
        report = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScannerReadinessError("scanner readiness report must contain valid UTF-8 JSON") from exc
    finally:
        if fd is not None:
            os.close(fd)
    validate_scanner_readiness_report(report)
    return report


def scanner_readiness_summary(report: dict[str, Any] | None) -> dict[str, Any]:
    if report is None:
        return {"checked": False, "state": "not_checked", "reason_codes": []}
    validate_scanner_readiness_report(report)
    return {
        "checked": True,
        "state": report["state"],
        "reason_codes": list(report["reason_codes"]),
    }

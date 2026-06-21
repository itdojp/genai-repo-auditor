from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROFILE_IDS = ("source-only", "local-test", "container", "gvisor", "vm")
NETWORK_POLICIES = ("disabled", "explicit-allow")
CREDENTIAL_ENV_NAMES = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_CLIENT_SECRET",
    "GCP_SERVICE_ACCOUNT_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)
CREDENTIAL_RELATIVE_PATHS = (
    ".env",
    ".env.local",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".aws/credentials",
    ".config/gcloud/application_default_credentials.json",
    ".ssh/id_rsa",
    ".ssh/id_ed25519",
)


class SandboxProfileError(RuntimeError):
    """Raised when an executable workflow is not allowed by sandbox readiness."""


@dataclass(frozen=True)
class SandboxProfile:
    id: str
    display_name: str
    description: str
    executes_target_code: bool
    requires_container_runtime: bool = False
    requires_gvisor: bool = False
    requires_vm: bool = False


PROFILES: dict[str, SandboxProfile] = {
    "source-only": SandboxProfile(
        id="source-only",
        display_name="Source-only review",
        description="Report-only source review. Does not execute target code.",
        executes_target_code=False,
    ),
    "local-test": SandboxProfile(
        id="local-test",
        display_name="Local test workspace",
        description="Future executable local validation profile. Requires explicit readiness review before target code execution.",
        executes_target_code=True,
    ),
    "container": SandboxProfile(
        id="container",
        display_name="Container runtime",
        description="Future executable validation profile that requires Docker or Podman.",
        executes_target_code=True,
        requires_container_runtime=True,
    ),
    "gvisor": SandboxProfile(
        id="gvisor",
        display_name="gVisor container sandbox",
        description="Future executable validation profile that requires a container runtime and runsc/gVisor.",
        executes_target_code=True,
        requires_container_runtime=True,
        requires_gvisor=True,
    ),
    "vm": SandboxProfile(
        id="vm",
        display_name="Virtual machine sandbox",
        description="Future executable validation profile for isolated VM execution. Orchestration is not implemented yet.",
        executes_target_code=True,
        requires_vm=True,
    ),
}


def utc_now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_context(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "context.json"
    if not path.exists():
        return {"run_id": run_dir.name, "target_repo_dir": "repo", "reports_dir": "reports"}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SandboxProfileError(f"context.json must be a JSON object: {path}")
    data.setdefault("run_id", run_dir.name)
    data.setdefault("target_repo_dir", "repo")
    data.setdefault("reports_dir", "reports")
    return data


def reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    reports = str(ctx.get("reports_dir") or "reports")
    if reports.startswith("/") or ".." in Path(reports).parts:
        raise SandboxProfileError(f"unsafe reports_dir in context.json: {reports}")
    return run_dir / reports


def target_repo_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    if ctx.get("repo_dir"):
        path = Path(str(ctx["repo_dir"]))
        if not path.is_absolute() and not path.exists():
            path = run_dir / path
        return path
    else:
        return run_dir / str(ctx.get("target_repo_dir") or "repo")


def profile_by_id(profile_id: str) -> SandboxProfile:
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise SandboxProfileError(f"unknown sandbox profile: {profile_id}") from exc


def check_record(check_id: str, status: str, severity: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or {},
    }


def git_clean_status(repo_dir: Path) -> dict[str, Any]:
    if not (repo_dir / ".git").exists():
        return {"available": False, "clean": None, "changed_paths": [], "message": "target repository is not a Git worktree"}
    cp = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--porcelain=v1", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        return {"available": False, "clean": None, "changed_paths": [], "message": cp.stderr.strip() or "git status failed"}
    changed = [line[3:] for line in cp.stdout.splitlines() if line.strip()]
    return {"available": True, "clean": not changed, "changed_paths": changed[:20], "message": "clean" if not changed else "changes present"}


def detect_credential_paths(repo_dir: Path) -> list[str]:
    findings: list[str] = []
    for relative in CREDENTIAL_RELATIVE_PATHS:
        path = repo_dir / relative
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if exists:
            findings.append(relative)
    return findings


def detect_visible_credential_env(env: dict[str, str] | None = None) -> list[str]:
    source = env if env is not None else os.environ
    return [name for name in CREDENTIAL_ENV_NAMES if source.get(name)]


def find_container_runtime(path_env: str | None = None) -> dict[str, Any]:
    docker = shutil.which("docker", path=path_env)
    podman = shutil.which("podman", path=path_env)
    runtime = podman or docker
    return {
        "available": runtime is not None,
        "runtime": "podman" if podman else ("docker" if docker else None),
        "path": runtime,
    }


def find_gvisor(path_env: str | None = None) -> dict[str, Any]:
    runsc = shutil.which("runsc", path=path_env)
    return {"available": runsc is not None, "path": runsc}


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for check in checks if check["status"] == "pass"),
        "warnings": sum(1 for check in checks if check["status"] == "warn"),
        "errors": sum(1 for check in checks if check["status"] == "fail"),
        "info": sum(1 for check in checks if check["status"] == "info"),
    }


def overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "blocked"
    if any(check["status"] == "warn" for check in checks):
        return "warning"
    return "ready"


def evaluate_sandbox_readiness(
    *,
    run_dir: Path,
    profile_id: str,
    executable_workflow: bool | None = None,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    if network_policy not in NETWORK_POLICIES:
        raise SandboxProfileError(f"network_policy must be one of: {', '.join(NETWORK_POLICIES)}")
    profile = profile_by_id(profile_id)
    executable_requested = profile.executes_target_code if executable_workflow is None else executable_workflow
    checks: list[dict[str, Any]] = []

    if run_dir.exists() and run_dir.is_dir():
        checks.append(check_record("run-directory", "pass", "required", "run directory exists", {"path": str(run_dir)}))
    else:
        checks.append(check_record("run-directory", "fail", "required", "run directory does not exist", {"path": str(run_dir)}))

    repo_dir = target_repo_dir(run_dir)
    repo_status = git_clean_status(repo_dir)
    if profile.id == "source-only":
        checks.append(
            check_record(
                "workspace-cleanliness",
                "info" if repo_status["clean"] is None else ("pass" if repo_status["clean"] else "warn"),
                "advisory",
                "workspace cleanliness recorded for source-only workflow",
                {"repo_dir": str(repo_dir), **repo_status},
            )
        )
    elif repo_status["clean"] is True:
        checks.append(check_record("workspace-cleanliness", "pass", "required", "target repository worktree is clean", {"repo_dir": str(repo_dir)}))
    elif repo_status["clean"] is False:
        checks.append(
            check_record(
                "workspace-cleanliness",
                "warn" if profile.id == "local-test" else "fail",
                "required",
                "target repository has local changes; freeze or copy to a disposable workspace before executable validation",
                {"repo_dir": str(repo_dir), "changed_paths": repo_status["changed_paths"]},
            )
        )
    else:
        checks.append(check_record("workspace-cleanliness", "warn", "advisory", repo_status["message"], {"repo_dir": str(repo_dir)}))

    checks.append(
        check_record(
            "network-policy",
            "pass",
            "required",
            f"network policy is explicit: {network_policy}",
            {"network_policy": network_policy},
        )
    )

    runtime = find_container_runtime(path_env)
    if profile.requires_container_runtime:
        checks.append(
            check_record(
                "container-runtime",
                "pass" if runtime["available"] else "fail",
                "required",
                "container runtime is available" if runtime["available"] else "container profile requires Docker or Podman, but neither was found on PATH",
                runtime,
            )
        )
    else:
        checks.append(
            check_record(
                "container-runtime",
                "info",
                "advisory",
                "container runtime is not required for this profile",
                runtime,
            )
        )

    gvisor = find_gvisor(path_env)
    if profile.requires_gvisor:
        checks.append(
            check_record(
                "gvisor-runtime",
                "pass" if gvisor["available"] else "fail",
                "required",
                "gVisor runsc is available" if gvisor["available"] else "gvisor profile requires runsc, but it was not found on PATH",
                gvisor,
            )
        )

    if profile.requires_vm:
        checks.append(
            check_record(
                "vm-orchestration",
                "fail",
                "required",
                "vm sandbox profile contract exists, but VM orchestration is not implemented in this release",
                {},
            )
        )

    credential_paths = detect_credential_paths(repo_dir)
    credential_env = detect_visible_credential_env(env)
    credential_status = "pass" if not credential_paths and not credential_env else ("warn" if profile.id in {"source-only", "local-test"} else "fail")
    checks.append(
        check_record(
            "credential-exposure",
            credential_status,
            "required" if profile.executes_target_code else "advisory",
            "no common credential paths or environment secret names detected" if credential_status == "pass" else "credential material may be visible; remove mounts/environment before executable validation",
            {"credential_paths": credential_paths, "credential_environment_names": credential_env},
        )
    )

    if executable_requested and not profile.executes_target_code:
        checks.append(
            check_record(
                "executable-profile-approval",
                "fail",
                "required",
                "executable workflow requested with source-only profile; choose an approved executable sandbox profile",
                {"requested_profile": profile.id},
            )
        )
    elif executable_requested:
        checks.append(
            check_record(
                "executable-profile-approval",
                "pass",
                "required",
                f"executable workflow is explicitly associated with profile {profile.id}",
                {"requested_profile": profile.id},
            )
        )
    else:
        checks.append(
            check_record(
                "executable-profile-approval",
                "pass",
                "required",
                "no executable target-code workflow requested",
                {"requested_profile": profile.id},
            )
        )

    summary = summarize_checks(checks)
    status = overall_status(checks)
    ctx = load_context(run_dir)
    return {
        "schema_version": "1",
        "generated_at": utc_now(),
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "run_dir": str(run_dir),
        "profile": {
            "id": profile.id,
            "display_name": profile.display_name,
            "description": profile.description,
            "executes_target_code": profile.executes_target_code,
        },
        "executable_workflow_requested": executable_requested,
        "network_policy": network_policy,
        "status": status,
        "summary": summary,
        "checks": checks,
    }


def render_readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sandbox Readiness",
        "",
        f"- Run: `{report.get('run_id', '')}`",
        f"- Repository: `{report.get('repo', '')}`",
        f"- Profile: `{report.get('profile', {}).get('id', '')}` ({report.get('profile', {}).get('display_name', '')})",
        f"- Status: `{report.get('status', '')}`",
        f"- Network policy: `{report.get('network_policy', '')}`",
        "",
        "## Summary",
        "",
    ]
    summary = report.get("summary", {})
    lines.extend(
        [
            f"- Passed: {summary.get('passed', 0)}",
            f"- Warnings: {summary.get('warnings', 0)}",
            f"- Errors: {summary.get('errors', 0)}",
            f"- Info: {summary.get('info', 0)}",
            "",
            "## Checks",
            "",
            "| Check | Status | Severity | Message |",
            "|---|---|---|---|",
        ]
    )
    for check in report.get("checks", []):
        message = str(check.get("message", "")).replace("|", "\\|")
        lines.append(f"| `{check.get('id', '')}` | `{check.get('status', '')}` | `{check.get('severity', '')}` | {message} |")
    lines.extend(
        [
            "",
            "## Phase guidance",
            "",
            "- Setup phase: install optional runtimes and prepare disposable workspaces, but do not execute target code yet.",
            "- Freeze phase: capture the exact run, target repository state, network policy, and credential exposure state.",
            "- Validation phase: execute target code only after an executable sandbox profile is ready and approved.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_readiness_report(run_dir: Path, report: dict[str, Any], out_json: Path | None = None, out_md: Path | None = None) -> tuple[Path, Path]:
    out_json = out_json or (reports_dir(run_dir) / "sandbox-readiness.json")
    out_md = out_md or (reports_dir(run_dir) / "SANDBOX_READINESS.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_md.write_text(render_readiness_markdown(report), encoding="utf-8")
    return out_json, out_md


def enforce_sandbox_profile(
    *,
    run_dir: Path,
    profile_id: str,
    executable_workflow: bool = True,
    network_policy: str = "disabled",
    path_env: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    report = evaluate_sandbox_readiness(
        run_dir=run_dir,
        profile_id=profile_id,
        executable_workflow=executable_workflow,
        network_policy=network_policy,
        path_env=path_env,
        env=env,
    )
    if report["status"] == "blocked":
        failures = [check["message"] for check in report["checks"] if check["status"] == "fail"]
        raise SandboxProfileError("sandbox profile is not ready: " + "; ".join(failures))
    return report

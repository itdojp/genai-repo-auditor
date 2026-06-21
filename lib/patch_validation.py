from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from gralib import load_context, load_findings, load_json, slug, utc_now, write_json
from sandbox_profiles import SandboxProfileError, evaluate_sandbox_readiness, target_repo_dir

REMEDIATION_DIR = Path("reports") / "remediation"
REMEDIATION_JSON = REMEDIATION_DIR / "remediation-candidates.json"
PATCH_VALIDATION_JSON = "patch-validation.json"
PATCH_VALIDATION_MD = "patch-validation.md"
WORKSPACE_ROOT = Path(".patch-validation-workspaces")
BUILD_TEST_STATUSES = {"passed", "failed", "not-run"}
SAFE_PROOF_STATUSES = {"passed", "failed", "not-applicable", "not-run"}
ADVERSARIAL_STATUSES = {"passed", "failed", "needs-human-review", "not-run"}
DIFF_SCOPE_STATUSES = {"bounded", "too-broad", "needs-human-review"}
FINAL_STATUSES = {"validated", "failed", "needs-human-review"}
SHELL_METACHARS_RE = re.compile(r"[;&|`$<>\n\r]")
NETWORK_ACTIVITY_RE = re.compile(
    r"(https?://|urllib|urlopen|requests|websocket|socket|fetch|axios|http\.server|ftplib|telnetlib)",
    re.IGNORECASE,
)
DENIED_EXECUTABLES = {
    "apt",
    "apt-get",
    "bash",
    "brew",
    "cmd",
    "curl",
    "docker",
    "fish",
    "gh",
    "git",
    "nc",
    "ncat",
    "npm",
    "npx",
    "pip",
    "pip3",
    "pnpm",
    "podman",
    "powershell",
    "pwsh",
    "scp",
    "sh",
    "ssh",
    "sudo",
    "su",
    "telnet",
    "wget",
    "yarn",
    "zsh",
}
DENIED_TOKENS = {"install", "publish", "push", "upload", "deploy"}
CREDENTIAL_ENV_NAMES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_CLIENT_SECRET",
    "GCP_SERVICE_ACCOUNT_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
}


class PatchValidationError(RuntimeError):
    """Raised when patch validation cannot be prepared safely."""


def safe_subject_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    if not segment:
        return "finding"
    if segment in {".", ".."}:
        return slug(value)
    return segment


def check_record(check_id: str, status: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": check_id, "status": status, "message": message, "details": details or {}}


def relative_to_run(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(run_dir.resolve(strict=False)).as_posix()
    except ValueError:
        return path.name


def contained_run_path(run_dir: Path, value: str, *, field: str) -> Path:
    rel = Path(value)
    if rel.is_absolute():
        raise PatchValidationError(f"{field} must be relative to the run directory")
    if ".." in rel.parts:
        raise PatchValidationError(f"{field} must not contain '..'")
    candidate = (run_dir / rel).resolve(strict=False)
    root = run_dir.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PatchValidationError(f"{field} must stay under the run directory") from exc
    return run_dir / rel


def load_remediation_candidates(run_dir: Path) -> list[dict[str, Any]]:
    data = load_json(run_dir / REMEDIATION_JSON, {}) or {}
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        raise PatchValidationError(f"remediation candidates not found: {run_dir / REMEDIATION_JSON}")
    return [item for item in candidates if isinstance(item, dict)]


def finding_ids_for_all_critical_high(run_dir: Path) -> set[str]:
    selected: set[str] = set()
    for finding in load_findings(run_dir):
        if not isinstance(finding, dict):
            continue
        if finding.get("severity") in {"Critical", "High"} and finding.get("status") in {"Confirmed", "Probable", "Potential"}:
            finding_id = str(finding.get("id") or "").strip()
            if finding_id:
                selected.add(finding_id)
    return selected


def select_candidates(run_dir: Path, *, finding_id: str | None = None, all_critical_high: bool = False) -> list[dict[str, Any]]:
    candidates = load_remediation_candidates(run_dir)
    if finding_id:
        selected_ids = {finding_id}
    elif all_critical_high:
        selected_ids = finding_ids_for_all_critical_high(run_dir)
    else:
        raise PatchValidationError("either finding_id or all_critical_high is required")
    selected = [candidate for candidate in candidates if str(candidate.get("finding_id") or "") in selected_ids]
    if not selected:
        raise PatchValidationError("no remediation candidates matched the selected finding(s)")
    return selected


def strip_diff_prefix(value: str) -> str | None:
    value = value.strip()
    if not value or value == "/dev/null":
        return None
    if value.startswith("a/") or value.startswith("b/"):
        value = value[2:]
    return value


def parse_diff_paths(patch_text: str) -> set[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                for raw in parts[2:4]:
                    path = strip_diff_prefix(raw)
                    if path:
                        paths.add(path)
        elif line.startswith("--- ") or line.startswith("+++ "):
            raw = line[4:].split("\t", 1)[0].strip()
            path = strip_diff_prefix(raw)
            if path:
                paths.add(path)
    return paths


def path_is_under(path: str, root: str) -> bool:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        return False
    root_path = Path(root)
    return rel == root_path or root_path in rel.parents


def diff_scope_status(*, diff_paths: set[str], declared_files: Iterable[Any], target_prefix: str, max_changed_paths: int) -> tuple[str, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    declared = {str(item) for item in declared_files if isinstance(item, str) and item.strip()}
    if not diff_paths:
        checks.append(check_record("diff-paths", "fail", "patch diff did not expose changed file paths"))
        return "needs-human-review", checks
    unsafe = sorted(path for path in diff_paths if not path_is_under(path, target_prefix))
    if unsafe:
        checks.append(check_record("diff-paths", "fail", "patch modifies paths outside the target repository prefix", {"paths": unsafe}))
        return "too-broad", checks
    if len(diff_paths) > max_changed_paths:
        checks.append(check_record("diff-size", "fail", "patch changes more files than the bounded review threshold", {"changed_paths": len(diff_paths), "max_changed_paths": max_changed_paths}))
        return "too-broad", checks
    if declared and not diff_paths.issubset(declared):
        checks.append(check_record("diff-declared-files", "warn", "patch changes files not listed in candidate files_touched", {"diff_paths": sorted(diff_paths), "files_touched": sorted(declared)}))
        return "needs-human-review", checks
    checks.append(check_record("diff-scope", "pass", "patch scope is bounded to declared target repository paths", {"paths": sorted(diff_paths)}))
    return "bounded", checks


def parse_operator_command(raw: str) -> list[str]:
    command = raw.strip()
    if not command:
        raise PatchValidationError("validation command must not be empty")
    if SHELL_METACHARS_RE.search(command):
        raise PatchValidationError("validation command contains shell metacharacters; provide argv-style commands only")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise PatchValidationError(f"validation command could not be parsed: {exc}") from exc
    if not argv:
        raise PatchValidationError("validation command must not be empty")
    exe = Path(argv[0]).name.lower()
    if exe in DENIED_EXECUTABLES:
        raise PatchValidationError(f"validation command executable is not allowed by default: {argv[0]}")
    lowered = {token.lower() for token in argv[1:]}
    if lowered & DENIED_TOKENS:
        raise PatchValidationError("validation command includes an unsafe install/publish/deploy token")
    joined_args = " ".join(argv[1:])
    if NETWORK_ACTIVITY_RE.search(joined_args):
        raise PatchValidationError("validation command includes network-capable arguments and is not allowed by default")
    return argv


def validation_environment(workspace: Path) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONUNBUFFERED": "1",
        "NO_COLOR": "1",
        "HOME": str(workspace / ".home"),
    }
    (workspace / ".home").mkdir(parents=True, exist_ok=True)
    for name in CREDENTIAL_ENV_NAMES:
        env.pop(name, None)
    return env


def run_commands(
    *,
    kind: str,
    raw_commands: list[str],
    workspace: Path,
    timeout: int,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if not raw_commands:
        return "not-run", [], [check_record(f"{kind}-commands", "info", f"no {kind} commands configured")]
    commands_run: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    overall = "passed"
    for index, raw in enumerate(raw_commands, start=1):
        try:
            argv = parse_operator_command(raw)
        except PatchValidationError as exc:
            commands_run.append({"kind": kind, "argv": [raw], "status": "rejected", "exit_code": None, "cwd": "validation_workspace"})
            checks.append(check_record(f"{kind}-command-{index}", "fail", str(exc)))
            overall = "failed"
            continue
        cp = subprocess.run(
            argv,
            cwd=workspace,
            env=validation_environment(workspace),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        status = "passed" if cp.returncode == 0 else "failed"
        if status == "failed":
            overall = "failed"
        commands_run.append({"kind": kind, "argv": argv, "status": status, "exit_code": cp.returncode, "cwd": "validation_workspace"})
        checks.append(
            check_record(
                f"{kind}-command-{index}",
                "pass" if status == "passed" else "fail",
                f"{kind} command {'passed' if status == 'passed' else 'failed'}",
                {"argv": argv, "exit_code": cp.returncode},
            )
        )
    return overall, commands_run, checks


def load_proof_status(run_dir: Path, finding_id: str) -> str:
    proof_data = load_json(run_dir / "reports" / "proofs.json", {}) or {}
    proofs = proof_data.get("proofs") if isinstance(proof_data, dict) else None
    if not isinstance(proofs, list):
        return "not-applicable"
    matching = [item for item in proofs if isinstance(item, dict) and str(item.get("finding_id") or "") == finding_id]
    if not matching:
        return "not-applicable"
    if any(item.get("status") == "failed" for item in matching):
        return "failed"
    if all(item.get("status") == "confirmed" for item in matching):
        return "passed"
    return "not-run"


def final_status(report: dict[str, Any]) -> str:
    if report["patch_applied"] is not True:
        return "failed"
    if report["diff_scope_status"] != "bounded":
        return "needs-human-review" if report["diff_scope_status"] == "needs-human-review" else "failed"
    for key in ["build_status", "test_status", "safe_proof_replay_status", "adversarial_review_status"]:
        value = report.get(key)
        if value == "failed":
            return "failed"
        if value == "needs-human-review":
            return "needs-human-review"
    return "validated"


def render_patch_validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Patch Validation",
        "",
        "Local/private validation result for a draft remediation candidate. This report does not publish or apply patches to the original checkout.",
        "",
        f"- Patch ID: `{report.get('patch_id', '')}`",
        f"- Finding ID: `{report.get('finding_id', '')}`",
        f"- Sandbox profile: `{report.get('sandbox_profile', '')}`",
        f"- Final status: `{report.get('final_status', '')}`",
        f"- Patch applied in disposable workspace: `{report.get('patch_applied', False)}`",
        "",
        "## Ladder status",
        "",
        "| Step | Status |",
        "|---|---|",
        f"| Build | `{report.get('build_status', '')}` |",
        f"| Tests | `{report.get('test_status', '')}` |",
        f"| Safe proof replay | `{report.get('safe_proof_replay_status', '')}` |",
        f"| Adversarial review | `{report.get('adversarial_review_status', '')}` |",
        f"| Diff scope | `{report.get('diff_scope_status', '')}` |",
        "",
        "## Checks",
        "",
        "| Check | Status | Message |",
        "|---|---|---|",
    ]
    for check in report.get("checks") or []:
        if not isinstance(check, dict):
            continue
        message = str(check.get("message", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{check.get('id', '')}` | `{check.get('status', '')}` | {message} |")
    limitations = report.get("limitations") if isinstance(report.get("limitations"), list) else []
    if limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in limitations)
    return "\n".join(lines) + "\n"


def write_validation_report(run_dir: Path, candidate: dict[str, Any], report: dict[str, Any]) -> tuple[Path, Path]:
    finding_id = str(candidate.get("finding_id") or "SEC-UNKNOWN")
    candidate_dir = run_dir / REMEDIATION_DIR / safe_subject_segment(finding_id)
    out_json = candidate_dir / PATCH_VALIDATION_JSON
    out_md = candidate_dir / PATCH_VALIDATION_MD
    write_json(out_json, report)
    out_md.write_text(render_patch_validation_markdown(report), encoding="utf-8")
    return out_json, out_md


def validate_patch_candidate(
    *,
    run_dir: Path,
    candidate: dict[str, Any],
    sandbox_profile: str,
    build_commands: list[str],
    test_commands: list[str],
    command_timeout: int = 60,
    max_changed_paths: int = 20,
) -> tuple[dict[str, Any], Path, Path]:
    ctx = load_context(run_dir)
    finding_id = str(candidate.get("finding_id") or "SEC-UNKNOWN")
    patch_id = str(candidate.get("id") or "PATCH-UNKNOWN")
    patch_file_value = str(candidate.get("patch_file") or "")
    checks: list[dict[str, Any]] = []
    commands_run: list[dict[str, Any]] = []
    patch_applied = False
    diff_status = "needs-human-review"
    build_status = "not-run"
    test_status = "not-run"
    proof_status = load_proof_status(run_dir, finding_id)
    adversarial_status = "not-run"
    workspace_rel = WORKSPACE_ROOT / f"{safe_subject_segment(finding_id)}-{slug(patch_id)}"
    workspace = run_dir / workspace_rel
    limitations = [
        "Validation runs in a disposable local workspace and does not modify the original target checkout.",
        "Network access is not configured by this workflow.",
        "Human review is still required before applying or publishing any patch.",
    ]

    try:
        sandbox_report = evaluate_sandbox_readiness(
            run_dir=run_dir,
            profile_id=sandbox_profile,
            executable_workflow=True,
            network_policy="disabled",
            path_env=os.environ.get("PATH"),
            env=os.environ,
        )
        checks.append(
            check_record(
                "sandbox-readiness",
                "pass" if sandbox_report.get("status") == "ready" else "fail",
                f"sandbox profile status: {sandbox_report.get('status')}",
                {"profile": sandbox_profile, "summary": sandbox_report.get("summary", {})},
            )
        )
        if sandbox_report.get("status") != "ready":
            raise PatchValidationError("sandbox profile is not ready for executable patch validation")

        patch_path = contained_run_path(run_dir, patch_file_value, field="patch_file")
        if not patch_path.exists() or not patch_path.is_file():
            raise PatchValidationError(f"patch file not found: {patch_file_value}")
        patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
        target_repo = target_repo_dir(run_dir)
        if not target_repo.exists() or not target_repo.is_dir():
            raise PatchValidationError(f"target repository does not exist: {relative_to_run(run_dir, target_repo)}")
        try:
            target_prefix = target_repo.resolve(strict=False).relative_to(run_dir.resolve(strict=False)).as_posix()
        except ValueError as exc:
            raise PatchValidationError("target repository must stay under run directory") from exc

        diff_paths = parse_diff_paths(patch_text)
        diff_status, diff_checks = diff_scope_status(
            diff_paths=diff_paths,
            declared_files=candidate.get("files_touched") if isinstance(candidate.get("files_touched"), list) else [],
            target_prefix=target_prefix,
            max_changed_paths=max_changed_paths,
        )
        checks.extend(diff_checks)
        if diff_status != "bounded":
            raise PatchValidationError("patch diff scope is not bounded")

        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        workspace_target = workspace / target_prefix
        workspace_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target_repo, workspace_target, symlinks=True)
        init_cp = subprocess.run(
            ["git", "-C", str(workspace), "init"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=command_timeout,
        )
        if init_cp.returncode != 0:
            checks.append(check_record("disposable-workspace-git", "fail", "failed to initialize disposable workspace git context", {"exit_code": init_cp.returncode}))
            raise PatchValidationError("failed to initialize disposable workspace git context")
        checks.append(check_record("disposable-workspace", "pass", "target repository copied to disposable workspace", {"workspace": workspace_rel.as_posix(), "target_repo": target_prefix}))

        check_cp = subprocess.run(
            ["git", "-C", str(workspace), "apply", "--check", str(patch_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=command_timeout,
        )
        if check_cp.returncode != 0:
            checks.append(check_record("patch-apply-check", "fail", "patch failed git apply --check", {"exit_code": check_cp.returncode}))
            raise PatchValidationError("patch failed git apply --check")
        apply_cp = subprocess.run(
            ["git", "-C", str(workspace), "apply", str(patch_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=command_timeout,
        )
        if apply_cp.returncode != 0:
            checks.append(check_record("patch-apply", "fail", "patch failed to apply in disposable workspace", {"exit_code": apply_cp.returncode}))
            raise PatchValidationError("patch failed to apply in disposable workspace")
        patch_applied = True
        checks.append(check_record("patch-apply", "pass", "patch applied in disposable workspace"))

        build_status, build_commands_run, build_checks = run_commands(kind="build", raw_commands=build_commands, workspace=workspace, timeout=command_timeout)
        test_status, test_commands_run, test_checks = run_commands(kind="test", raw_commands=test_commands, workspace=workspace, timeout=command_timeout)
        commands_run.extend(build_commands_run)
        commands_run.extend(test_commands_run)
        checks.extend(build_checks)
        checks.extend(test_checks)
    except (OSError, subprocess.TimeoutExpired, SandboxProfileError, PatchValidationError) as exc:
        checks.append(check_record("validation-error", "fail", str(exc)))
    finally:
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

    report: dict[str, Any] = {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "patch_id": patch_id,
        "finding_id": finding_id,
        "sandbox_profile": sandbox_profile,
        "network_allowed": False,
        "patch_file": patch_file_value,
        "candidate_file": REMEDIATION_JSON.as_posix(),
        "validation_workspace": {"path": workspace_rel.as_posix(), "disposed": True},
        "patch_applied": patch_applied,
        "build_status": build_status,
        "test_status": test_status,
        "safe_proof_replay_status": proof_status,
        "adversarial_review_status": adversarial_status,
        "diff_scope_status": diff_status,
        "final_status": "failed",
        "checks": checks,
        "commands_run": commands_run,
        "limitations": limitations,
    }
    report["final_status"] = final_status(report)
    out_json, out_md = write_validation_report(run_dir, candidate, report)
    return report, out_json, out_md


def validate_selected_patches(
    *,
    run_dir: Path,
    finding_id: str | None,
    all_critical_high: bool,
    sandbox_profile: str,
    build_commands: list[str],
    test_commands: list[str],
    command_timeout: int = 60,
    max_changed_paths: int = 20,
) -> list[tuple[dict[str, Any], Path, Path]]:
    selected = select_candidates(run_dir, finding_id=finding_id, all_critical_high=all_critical_high)
    results: list[tuple[dict[str, Any], Path, Path]] = []
    for candidate in selected:
        results.append(
            validate_patch_candidate(
                run_dir=run_dir,
                candidate=candidate,
                sandbox_profile=sandbox_profile,
                build_commands=build_commands,
                test_commands=test_commands,
                command_timeout=command_timeout,
                max_changed_paths=max_changed_paths,
            )
        )
    return results

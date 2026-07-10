from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .resources import resource_root
from .version import package_version


def slug_from_repo(repo: str) -> str:
    result = repo.removeprefix("https://github.com/").removeprefix("http://github.com/")
    if result.endswith(".git"):
        result = result[:-4]
    return result.replace("/", "__").replace(":", "__")


def default_run_id() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{os.getpid()}-{random.SystemRandom().randrange(10000, 99999)}"


def require_commands(names: Sequence[str]) -> int:
    for name in names:
        if shutil.which(name) is None:
            print(f"Missing required command: {name}", file=sys.stderr)
            return 1
    return 0


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_audit_resources(lab_root: Path, run_dir: Path, report_dir: Path) -> None:
    copy_if_exists(lab_root / "prompts" / "AGENTS.audit.md", run_dir / "AGENTS.md")
    reports_root = lab_root / "templates" / "reports"
    if reports_root.is_dir():
        for schema in sorted(reports_root.glob("*.schema.json")):
            copy_if_exists(schema, run_dir / schema.name)

    taxonomies = lab_root / "templates" / "taxonomies"
    if taxonomies.is_dir():
        out_dir = run_dir / "templates" / "taxonomies"
        out_dir.mkdir(parents=True, exist_ok=True)
        for taxonomy in sorted(taxonomies.glob("*.json")):
            shutil.copy2(taxonomy, out_dir / taxonomy.name)
    copy_if_exists(lab_root / "templates" / "taxonomy-aliases.json", run_dir / "templates" / "taxonomy-aliases.json")

    for relative in (
        "issue-drafts",
        "duplicate-decisions",
        "scanner-results",
        "target-research",
        "variant-analysis",
        "proofs",
        "traces",
    ):
        (report_dir / relative).mkdir(parents=True, exist_ok=True)


def run_checked(args: Sequence[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(list(args), env=env, check=True)


def render_template(lab_root: Path, template: Path, out: Path, env: dict[str, str]) -> None:
    run_checked([sys.executable, str(lab_root / "lib" / "render_template.py"), str(template), str(out)], env=env)


def render_prompts(lab_root: Path, run_dir: Path, env: dict[str, str]) -> tuple[Path, Path]:
    exec_prompt = run_dir / "prompt.exec.md"
    goal_prompt = run_dir / "prompt.goal.md"
    render_template(lab_root, lab_root / "prompts" / "exec" / "full-audit.prompt.md", exec_prompt, env)
    render_template(lab_root, lab_root / "prompts" / "goal" / "full-audit.goal.md", goal_prompt, env)

    exec_dir = run_dir / "prompts" / "exec"
    goal_dir = run_dir / "prompts" / "goal"
    exec_dir.mkdir(parents=True, exist_ok=True)
    goal_dir.mkdir(parents=True, exist_ok=True)
    for template in sorted((lab_root / "prompts" / "exec").glob("*.prompt.md")):
        render_template(lab_root, template, exec_dir / template.name, env)
    for template in sorted((lab_root / "prompts" / "goal").glob("*.goal.md")):
        render_template(lab_root, template, goal_dir / template.name, env)
    return exec_prompt, goal_prompt


def write_run_manifest(
    lab_root: Path,
    run_dir: Path,
    *,
    mode: str,
    model: str,
    effort: str,
    depth: str,
    network_allowed: bool,
    codex_json: bool,
    allow_invalid_report: bool,
    execution_phase: str,
    codex_status: str = "",
    validation_status: str = "",
    final_status: str = "",
) -> None:
    run_checked(
        [
            sys.executable,
            str(lab_root / "lib" / "run_manifest.py"),
            "--lab-root",
            str(lab_root),
            "--run-dir",
            str(run_dir),
            "--command-name",
            "gra-audit",
            "--mode",
            mode,
            "--model",
            model,
            "--effort",
            effort,
            "--depth",
            depth,
            "--network-allowed",
            bool_text(network_allowed),
            "--codex-json",
            bool_text(codex_json),
            "--allow-invalid-report",
            bool_text(allow_invalid_report),
            "--execution-phase",
            execution_phase,
            "--codex-status",
            codex_status,
            "--validation-status",
            validation_status,
            "--final-status",
            final_status,
        ]
    )


def run_packaged_command(lab_root: Path, command: str, args: Sequence[str], *, stdout) -> int:
    command_path = lab_root / "bin" / command
    proc = subprocess.run([sys.executable, str(command_path), *args], stdout=stdout, stderr=subprocess.STDOUT, text=True, check=False)
    return proc.returncode


def numeric_or_one(value: str) -> int:
    return int(value) if value.isdigit() else 1


def make_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Run a GenAI Repo Auditor repository audit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  gra-audit --repo acme/api --mode exec\n  gra-audit --repo acme/api --mode goal --model gpt-5.5 --effort xhigh",
    )
    parser.add_argument("--repo", help="GitHub repository to audit. Required.")
    parser.add_argument("--branch", help="Branch or ref to clone. Optional.")
    parser.add_argument("--mode", choices=["exec", "goal", "prepare"], default="exec", help="Default: exec")
    parser.add_argument("--model", default=os.environ.get("GRA_MODEL") or os.environ.get("CODEX_MODEL") or "gpt-5.5", help="Default: gpt-5.5")
    parser.add_argument("--effort", default=os.environ.get("GRA_REASONING_EFFORT") or os.environ.get("CODEX_REASONING_EFFORT") or "xhigh", help="Default: xhigh")
    parser.add_argument("--depth", default="1", help="Clone depth. Default: 1")
    parser.add_argument("--run-id", help="Override run id. Default: UTC timestamp + pid + random")
    parser.add_argument("--runs-dir", help="Override runs directory for this invocation")
    parser.add_argument("--codex-json", action="store_true", default=True, help="Use codex exec --json and save event stream to codex-events.jsonl. Default: enabled")
    parser.add_argument("--network", action="store_true", help="Allow Codex sandbox network access. Default: disabled")
    parser.add_argument("--no-lock", action="store_true", help="Disable same-repo lock. Not recommended.")
    parser.add_argument("--allow-invalid-report", action="store_true", help="Do not fail when findings.json is missing or report validation fails. Not recommended for CI or batch automation.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = "gra-audit") -> int:
    lab_root = resource_root(honor_env_override=False)
    parser = make_parser(prog)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.repo:
        print("--repo is required", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 2

    missing_status = require_commands(("git", "gh", "codex"))
    if missing_status:
        return missing_status

    runs_dir = Path(args.runs_dir or os.environ.get("GENAI_REPO_AUDITOR_RUNS_DIR") or lab_root / "runs").expanduser().resolve()
    run_id = args.run_id or default_run_id()
    repo_slug = slug_from_repo(args.repo)
    run_dir = runs_dir / repo_slug / run_id
    repo_dir = run_dir / "repo"
    report_dir = run_dir / "reports"
    target_repo_dir = "repo"
    reports_dir = "reports"

    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "prompts").mkdir(parents=True, exist_ok=True)

    lock_path: Path | None = None
    try:
        if not args.no_lock:
            lock_dir = runs_dir / ".locks"
            lock_dir.mkdir(parents=True, exist_ok=True)
            candidate_lock_path = lock_dir / f"{repo_slug}.lockdir"
            try:
                candidate_lock_path.mkdir()
            except FileExistsError:
                print(f"Another audit appears to be running for {args.repo}. Lock: {candidate_lock_path}", file=sys.stderr)
                return 12
            lock_path = candidate_lock_path

        print(f"Run directory: {run_dir}")
        print(f"Cloning {args.repo} ...")
        clone_args = ["gh", "repo", "clone", args.repo, str(repo_dir), "--"]
        if args.branch:
            clone_args.extend(["--branch", args.branch])
        clone_args.extend(["--depth", str(args.depth)])
        run_checked(clone_args)

        commit = subprocess.check_output(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True).strip()
        branch_actual = subprocess.run(["git", "-C", str(repo_dir), "branch", "--show-current"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False).stdout.strip()
        branch = args.branch or branch_actual
        visibility = "UNKNOWN"
        vis = subprocess.run(["gh", "repo", "view", args.repo, "--json", "visibility", "--jq", ".visibility"], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if vis.returncode == 0 and vis.stdout.strip():
            visibility = vis.stdout.strip()

        copy_audit_resources(lab_root, run_dir, report_dir)
        context = {
            "run_id": run_id,
            "repo": args.repo,
            "repo_slug": repo_slug,
            "branch": branch,
            "commit": commit,
            "visibility": visibility,
            "run_dir": str(run_dir),
            "repo_dir": str(repo_dir),
            "target_repo_dir": target_repo_dir,
            "reports_dir": reports_dir,
            "network_allowed": bool(args.network),
        }
        (run_dir / "context.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")

        template_env = os.environ.copy()
        template_env.update({
            "RUN_ID": run_id,
            "REPO": args.repo,
            "REPO_SLUG": repo_slug,
            "BRANCH": branch,
            "COMMIT": commit,
            "VISIBILITY": visibility,
            "RUN_DIR": str(run_dir),
            "REPO_DIR": str(repo_dir),
            "TARGET_REPO_DIR": target_repo_dir,
            "REPORTS_DIR": reports_dir,
        })
        exec_prompt, goal_prompt = render_prompts(lab_root, run_dir, template_env)
        network_value = bool_text(bool(args.network))

        if args.mode == "prepare":
            write_run_manifest(
                lab_root,
                run_dir,
                mode=args.mode,
                model=args.model,
                effort=args.effort,
                depth=str(args.depth),
                network_allowed=bool(args.network),
                codex_json=bool(args.codex_json),
                allow_invalid_report=bool(args.allow_invalid_report),
                execution_phase="prepared",
            )
            print(
                f"""
Prepared audit run directory without executing Codex.

Audit run directory:
  {run_dir}

Target repository:
  {repo_dir}

Rendered prompts:
  {run_dir / 'prompts'}

Suggested staged agentic workflow:
  gra-recon --run "{run_dir}" --model "{args.model}" --effort "{args.effort}"
  gra-targets --run "{run_dir}" --generate --model "{args.model}" --effort "{args.effort}"
  gra-targets --run "{run_dir}" --list
  gra-research --run "{run_dir}" --target TGT-001 --model "{args.model}" --effort "{args.effort}"
  gra-validate-report --run "{run_dir}"
  gra-dashboard --run "{run_dir}"

For a supervised deep dive, use:
  gra-research --run "{run_dir}" --target TGT-001 --mode goal --model "{args.model}" --effort "{args.effort}"
""".rstrip()
            )
            return 0

        if args.mode == "goal":
            write_run_manifest(
                lab_root,
                run_dir,
                mode=args.mode,
                model=args.model,
                effort=args.effort,
                depth=str(args.depth),
                network_allowed=bool(args.network),
                codex_json=bool(args.codex_json),
                allow_invalid_report=bool(args.allow_invalid_report),
                execution_phase="goal-prepared",
            )
            print(
                f"""
Prepared interactive /goal run.

Audit run directory:
  {run_dir}

Target repository:
  {repo_dir}

Goal prompt:
  {goal_prompt}

Additional rendered prompts:
  {run_dir / 'prompts'}

Start Codex from the audit run directory:
  codex --cd "{run_dir}" --skip-git-repo-check --model "{args.model}" --enable goals --sandbox workspace-write --ask-for-approval on-request -c 'model_reasoning_effort="{args.effort}"' -c 'web_search="disabled"' -c 'sandbox_workspace_write.network_access={network_value}'

Then paste the contents of:
  {goal_prompt}

When Codex finishes, validate with:
  gra-validate-report --run "{run_dir}"

Then inspect:
  {report_dir / 'FINDINGS.md'}
  {report_dir / 'findings.json'}
""".rstrip()
            )
            return 0

        print("Running Codex non-interactively from run directory...")
        codex_args = [
            "codex",
            "exec",
            "--cd",
            str(run_dir),
            "--skip-git-repo-check",
            "--model",
            args.model,
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--output-last-message",
            str(run_dir / "codex-final.md"),
            "-c",
            'approval_policy="never"',
            "-c",
            f'model_reasoning_effort="{args.effort}"',
            "-c",
            'web_search="disabled"',
            "-c",
            f'sandbox_workspace_write.network_access={network_value}',
        ]
        if args.codex_json:
            with exec_prompt.open("rb") as stdin, (run_dir / "codex-events.jsonl").open("wb") as stdout, (run_dir / "codex-stderr.txt").open("wb") as stderr:
                codex_proc = subprocess.run([*codex_args, "--json", "-"], stdin=stdin, stdout=stdout, stderr=stderr, check=False)
                codex_status = codex_proc.returncode
        else:
            with exec_prompt.open("rb") as stdin, (run_dir / "codex-transcript.txt").open("wb") as transcript:
                codex_proc = subprocess.Popen([*codex_args, "-"], stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                assert codex_proc.stdout is not None
                for chunk in iter(lambda: codex_proc.stdout.read(8192), b""):
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    transcript.write(chunk)
                codex_status = codex_proc.wait()

        taxonomy_preflight_status = "not-run"
        if (report_dir / "findings.json").is_file() or (report_dir / "targets.json").is_file():
            with (run_dir / "taxonomy-preflight.txt").open("w", encoding="utf-8") as stdout:
                taxonomy_preflight_status = str(run_packaged_command(lab_root, "gra-taxonomy-preflight", ["--run", str(run_dir), "--fix"], stdout=stdout))

        if (report_dir / "findings.json").is_file():
            with (run_dir / "report-validation.txt").open("w", encoding="utf-8") as stdout:
                validation_status = str(run_packaged_command(lab_root, "gra-validate-report", ["--run", str(run_dir)], stdout=stdout))
        else:
            validation_status = "missing-findings-json"

        final_status = str(codex_status)
        if codex_status == 0 and taxonomy_preflight_status not in {"0", "not-run"}:
            final_status = "0" if args.allow_invalid_report else str(numeric_or_one(taxonomy_preflight_status))
        if codex_status == 0 and validation_status != "0":
            final_status = "0" if args.allow_invalid_report else str(numeric_or_one(validation_status))

        (run_dir / "run-summary.txt").write_text(
            "\n".join(
                [
                    f"run_id={run_id}",
                    f"repo={args.repo}",
                    f"branch={branch}",
                    f"commit={commit}",
                    f"visibility={visibility}",
                    f"mode={args.mode}",
                    f"model={args.model}",
                    f"effort={args.effort}",
                    f"codex_status={codex_status}",
                    f"validation_status={validation_status}",
                    f"taxonomy_preflight_status={taxonomy_preflight_status}",
                    f"allow_invalid_report={int(bool(args.allow_invalid_report))}",
                    f"final_status={final_status}",
                    f"repo_dir={repo_dir}",
                    f"reports_dir={report_dir}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        write_run_manifest(
            lab_root,
            run_dir,
            mode=args.mode,
            model=args.model,
            effort=args.effort,
            depth=str(args.depth),
            network_allowed=bool(args.network),
            codex_json=bool(args.codex_json),
            allow_invalid_report=bool(args.allow_invalid_report),
            execution_phase="completed",
            codex_status=str(codex_status),
            validation_status=validation_status,
            final_status=final_status,
        )

        print(f"\nRun complete. Codex status: {codex_status}")
        print(f"Reports: {report_dir}")
        print(f"Taxonomy preflight: {taxonomy_preflight_status}")
        print(f"Validation: {validation_status}")
        if taxonomy_preflight_status not in {"0", "not-run"}:
            print(f"Taxonomy preflight failed. See: {run_dir / 'taxonomy-preflight.txt'}", file=sys.stderr)
        if not (report_dir / "findings.json").is_file():
            print("Warning: findings.json was not produced. Inspect codex output and rerun if needed.", file=sys.stderr)
            print(f"Missing report path: {report_dir / 'findings.json'}", file=sys.stderr)
        elif validation_status != "0":
            print(f"Report validation failed. See: {run_dir / 'report-validation.txt'}", file=sys.stderr)
        if codex_status == 0 and validation_status != "0":
            if args.allow_invalid_report:
                print("Continuing despite invalid or missing report because --allow-invalid-report was set.", file=sys.stderr)
            else:
                print("Failing audit because Codex succeeded but report validation did not pass. Use --allow-invalid-report only when this is intentional.", file=sys.stderr)
        elif codex_status == 0 and taxonomy_preflight_status not in {"0", "not-run"}:
            if args.allow_invalid_report:
                print("Continuing despite taxonomy preflight errors because --allow-invalid-report was set.", file=sys.stderr)
            else:
                print("Failing audit because Codex succeeded but taxonomy preflight did not pass.", file=sys.stderr)
        print(f"Final status: {final_status}")
        return int(final_status)
    finally:
        if lock_path is not None:
            try:
                lock_path.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())

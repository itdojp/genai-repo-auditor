from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .resources import resource_root
from .version import package_version


def default_batch_id() -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"batch-{stamp}-{os.getpid()}-{os.urandom(2).hex()}"


def safe_name(repo: str) -> str:
    return repo.replace("/", "__").replace(":", "__")


def make_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="Run GenAI Repo Auditor over a repository list")
    parser.add_argument("--repo-list", help="File containing OWNER/REPO lines. Required.")
    parser.add_argument("--mode", choices=["exec", "goal"], default="exec", help="Default: exec")
    parser.add_argument("--model", default=os.environ.get("GRA_MODEL") or os.environ.get("CODEX_MODEL") or "gpt-5.5", help="Default: gpt-5.5")
    parser.add_argument("--effort", default=os.environ.get("GRA_REASONING_EFFORT") or os.environ.get("CODEX_REASONING_EFFORT") or "xhigh", help="Default: xhigh")
    parser.add_argument("--depth", default="1", help="Default: 1")
    parser.add_argument("--concurrency", type=int, default=1, help="Default: 1. Recommended: 1 initially, 2 after validation.")
    parser.add_argument("--runs-dir", help="Override runs directory")
    parser.add_argument("--batch-id", help="Override batch id")
    parser.add_argument("--codex-json", action="store_true", help="Pass through to gra-audit")
    parser.add_argument("--network", action="store_true", help="Pass through to gra-audit. Usually not recommended.")
    parser.add_argument("--allow-failures", action="store_true", help="Continue and exit 0 even when one or more audits fail.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed audit. Requires --concurrency 1.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    return parser


def load_repos(path: Path) -> list[str]:
    repos = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        repos.append(stripped)
    return repos


AUDIT_CLI_BOOTSTRAP = (
    "import sys; "
    "sys.path.insert(0, sys.argv.pop(1)); "
    "from genai_repo_auditor.audit_cli import main; "
    "raise SystemExit(main(sys.argv[1:]))"
)


def run_one(repo: str, *, log_dir: Path, runs_dir: Path, mode: str, model: str, effort: str, depth: str, extra_args: Sequence[str]) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{safe_name(repo)}.log"
    package_parent = str(Path(__file__).resolve().parent.parent)
    cmd = [
        sys.executable,
        "-I",
        "-c",
        AUDIT_CLI_BOOTSTRAP,
        package_parent,
        "--repo",
        repo,
        "--mode",
        mode,
        "--model",
        model,
        "--effort",
        effort,
        "--depth",
        depth,
        "--runs-dir",
        str(runs_dir),
        *extra_args,
    ]
    with log.open("w", encoding="utf-8") as handle:
        handle.write(f"=== audit start: {repo} ===\n")
        handle.write(dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z") + "\n")
        handle.flush()
        proc = subprocess.run(cmd, stdout=handle, stderr=subprocess.STDOUT, text=True, check=False)
        status = proc.returncode
        handle.write(f"=== audit done: {repo} status={status} ===\n")
        handle.write(dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z") + "\n")
    return status


def result_summary(batch: dict[str, object], repos: Sequence[str], log_dir: Path) -> dict[str, object]:
    results = []
    for repo in repos:
        log_path = log_dir / f"{safe_name(repo)}.log"
        attempted = log_path.exists()
        text = log_path.read_text(encoding="utf-8", errors="replace") if attempted else ""
        status_match = re.search(rf"^=== audit done: {re.escape(repo)} status=([0-9]+) ===$", text, re.MULTILINE)
        run_dir_match = re.search(r"^Run directory: (.+)$", text, re.MULTILINE)
        status = int(status_match.group(1)) if status_match else None
        results.append(
            {
                "repo": repo,
                "status": status,
                "status_text": "not-run" if not attempted else ("unknown" if status is None else ("success" if status == 0 else "failed")),
                "run_dir": run_dir_match.group(1) if run_dir_match else "",
                "log_path": str(log_path),
            }
        )
    failed = [r for r in results if r["status"] not in (0, None) or (r["status"] is None and r["status_text"] != "not-run")]
    succeeded = [r for r in results if r["status"] == 0]
    not_run = [r for r in results if r["status_text"] == "not-run"]
    return {
        **batch,
        "completed": len(succeeded) + len(failed),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "not_run": len(not_run),
        "results": results,
    }


def print_results(summary: dict[str, object], results_path: Path) -> None:
    results = list(summary.get("results") or [])
    succeeded = int(summary.get("succeeded") or 0)
    failed = int(summary.get("failed") or 0)
    not_run = int(summary.get("not_run") or 0)
    print("")
    print("Batch results:")
    print(f"{'REPO':<40} {'STATUS':<10} LOG")
    for item in results:
        assert isinstance(item, dict)
        status = item["status_text"] if item.get("status") is None else str(item.get("status"))
        print(f"{str(item.get('repo')):<40} {status:<10} {item.get('log_path')}")
    print(f"Successes: {succeeded}")
    print(f"Failures: {failed}")
    if not_run:
        print(f"Not run: {not_run}")
    print(f"Wrote {results_path}")


def main(argv: Sequence[str] | None = None, *, prog: str = "gra-batch") -> int:
    lab_root = resource_root(honor_env_override=False)
    parser = make_parser(prog)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.repo_list or not Path(args.repo_list).is_file():
        print("--repo-list FILE is required", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 2
    if args.concurrency < 1:
        print("--concurrency must be a positive integer", file=sys.stderr)
        return 2
    if args.fail_fast and args.concurrency != 1:
        print("--fail-fast requires --concurrency 1", file=sys.stderr)
        return 2

    runs_dir = Path(args.runs_dir or os.environ.get("GENAI_REPO_AUDITOR_RUNS_DIR") or lab_root / "runs").expanduser().resolve()
    batch_id = args.batch_id or default_batch_id()
    batch_dir = runs_dir / "_batches" / batch_id
    log_dir = batch_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    repos = load_repos(Path(args.repo_list))
    repos_file = batch_dir / "repos.normalized.txt"
    repos_file.write_text("".join(f"{repo}\n" for repo in repos), encoding="utf-8")

    batch = {
        "batch_id": batch_id,
        "repo_list": args.repo_list,
        "count": len(repos),
        "mode": args.mode,
        "model": args.model,
        "effort": args.effort,
        "depth": args.depth,
        "concurrency": args.concurrency,
        "allow_failures": bool(args.allow_failures),
        "fail_fast": bool(args.fail_fast),
        "runs_dir": str(runs_dir),
    }
    (batch_dir / "batch.json").write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")

    print(f"Batch: {batch_id}")
    print(f"Repos: {len(repos)}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Allow failures: {int(bool(args.allow_failures))}")
    print(f"Fail fast: {int(bool(args.fail_fast))}")
    print(f"Logs: {log_dir}")

    extra_args: list[str] = []
    if args.codex_json:
        extra_args.append("--codex-json")
    if args.network:
        extra_args.append("--network")

    batch_status = 0
    if args.concurrency == 1:
        for repo in repos:
            status = run_one(repo, log_dir=log_dir, runs_dir=runs_dir, mode=args.mode, model=args.model, effort=args.effort, depth=args.depth, extra_args=extra_args)
            if status != 0:
                batch_status = 1
                if args.fail_fast:
                    print(f"Fail-fast stopping after failed audit: {repo}", file=sys.stderr)
                    break
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(run_one, repo, log_dir=log_dir, runs_dir=runs_dir, mode=args.mode, model=args.model, effort=args.effort, depth=args.depth, extra_args=extra_args)
                for repo in repos
            ]
            for future in concurrent.futures.as_completed(futures):
                if future.result() != 0:
                    batch_status = 1

    results_path = batch_dir / "batch-results.json"
    summary = result_summary(batch, repos, log_dir)
    results_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed_count = int(summary.get("failed") or 0)
    (batch_dir / "failed-count.txt").write_text(str(failed_count), encoding="utf-8")
    print_results(summary, results_path)
    print(f"Batch complete. Logs: {log_dir}")
    print(f"Batch results: {results_path}")

    if failed_count > 0 and not args.allow_failures:
        return 1
    if batch_status != 0 and not args.allow_failures:
        return batch_status
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from version import auditor_version


MANIFEST_FILENAME = "run-manifest.json"
SCHEMA_FILENAME = "run-manifest.schema.json"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def rel_to_run(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def artifact_entry(run_dir: Path, rel_path: str, *, kind: str | None = None) -> dict[str, Any] | None:
    path = run_dir / rel_path
    if not path.exists():
        return None
    if kind is None:
        kind = "dir" if path.is_dir() else "file"
    entry: dict[str, Any] = {"path": rel_path, "kind": kind}
    if path.is_file():
        entry["size_bytes"] = path.stat().st_size
    return entry


def reports_artifact(run_dir: Path, rel_path: str = "") -> str:
    ctx = load_json(run_dir / "context.json", {}) or {}
    reports = manifest_relative_path(run_dir, ctx.get("reports_dir"), "reports")
    if not rel_path:
        return reports
    return (Path(reports) / rel_path).as_posix()


def collect_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    candidates = [
        ("context.json", "file"),
        # Omit run-manifest.json from its own artifact list to avoid
        # self-referential size metadata that can never be fully stable.
        ("findings.schema.json", "file"),
        ("targets.schema.json", "file"),
        ("scanner-index.schema.json", "file"),
        ("validation.schema.json", "file"),
        ("chains.schema.json", "file"),
        ("proofs.schema.json", "file"),
        ("traces.schema.json", "file"),
        ("metrics.schema.json", "file"),
        (SCHEMA_FILENAME, "file"),
        ("prompt.exec.md", "file"),
        ("prompt.goal.md", "file"),
        (reports_artifact(run_dir), "dir"),
        (reports_artifact(run_dir, "findings.json"), "file"),
        (reports_artifact(run_dir, "FINDINGS.md"), "file"),
        (reports_artifact(run_dir, "targets.json"), "file"),
        (reports_artifact(run_dir, "COVERAGE.md"), "file"),
        (reports_artifact(run_dir, "gapfill-targets.json"), "file"),
        (reports_artifact(run_dir, "validation.json"), "file"),
        (reports_artifact(run_dir, "VALIDATION.md"), "file"),
        (reports_artifact(run_dir, "chains.json"), "file"),
        (reports_artifact(run_dir, "ATTACK_CHAINS.md"), "file"),
        (reports_artifact(run_dir, "proofs.json"), "file"),
        (reports_artifact(run_dir, "PROOFS.md"), "file"),
        (reports_artifact(run_dir, "proofs"), "dir"),
        (reports_artifact(run_dir, "traces.json"), "file"),
        (reports_artifact(run_dir, "TRACE.md"), "file"),
        (reports_artifact(run_dir, "traces"), "dir"),
        (reports_artifact(run_dir, "metrics.json"), "file"),
        (reports_artifact(run_dir, "METRICS.md"), "file"),
        (reports_artifact(run_dir, "issue-ledger.json"), "file"),
        (reports_artifact(run_dir, "run-state.json"), "file"),
        (reports_artifact(run_dir, "scanner-results/scanner-index.json"), "file"),
        (reports_artifact(run_dir, "dashboard.html"), "file"),
        (reports_artifact(run_dir, "findings.sarif"), "file"),
        (reports_artifact(run_dir, "issue-drafts"), "dir"),
        (reports_artifact(run_dir, "scanner-results"), "dir"),
        (reports_artifact(run_dir, "target-research"), "dir"),
        (reports_artifact(run_dir, "variant-analysis"), "dir"),
        ("codex-events.jsonl", "file"),
        ("codex-final.md", "file"),
        ("codex-stderr.txt", "file"),
        ("codex-transcript.txt", "file"),
        ("report-validation.txt", "file"),
        ("run-summary.txt", "file"),
    ]
    entries: list[dict[str, Any]] = []
    for rel_path, kind in candidates:
        entry = artifact_entry(run_dir, rel_path, kind=kind)
        if entry is not None:
            entries.append(entry)

    prompts_dir = run_dir / "prompts"
    if prompts_dir.exists():
        for prompt in sorted(prompts_dir.rglob("*.md")):
            if prompt.is_file():
                entries.append({
                    "path": rel_to_run(run_dir, prompt),
                    "kind": "file",
                    "size_bytes": prompt.stat().st_size,
                })
    return entries


def collect_schemas(run_dir: Path) -> list[dict[str, str]]:
    schemas = []
    for name in [
        "findings.schema.json",
        "targets.schema.json",
        "scanner-index.schema.json",
        "validation.schema.json",
        "chains.schema.json",
        "proofs.schema.json",
        "traces.schema.json",
        "metrics.schema.json",
        "issue-ledger.schema.json",
        "run-state.schema.json",
        SCHEMA_FILENAME,
    ]:
        path = run_dir / name
        if path.exists():
            schemas.append({"name": name, "path": name})
    return schemas


def none_if_empty(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def manifest_relative_path(run_dir: Path, value: Any, default: str) -> str:
    text = str(value or default)
    path = Path(text)
    if path.is_absolute():
        try:
            text = path.relative_to(run_dir).as_posix()
        except ValueError:
            return default
    else:
        text = path.as_posix()
    if text in {"", "."}:
        return default
    if text == ".." or text.startswith("../"):
        return default
    return text


def build_manifest(
    *,
    lab_root: Path,
    run_dir: Path,
    command_name: str,
    mode: str,
    model: str,
    effort: str,
    depth: str,
    network_allowed: bool,
    codex_json: bool,
    allow_invalid_report: bool,
    execution_phase: str,
    codex_status: str | None = None,
    validation_status: str | None = None,
    final_status: str | None = None,
) -> dict[str, Any]:
    context = load_json(run_dir / "context.json", {}) or {}
    return {
        "schema_version": "1",
        "generated_at": utc_now(),
        "generated_by": {
            "name": "genai-repo-auditor",
            "version": auditor_version(lab_root),
        },
        "run": {
            "run_id": context.get("run_id") or run_dir.name,
            "repo": context.get("repo", ""),
            "repo_slug": context.get("repo_slug", ""),
            "branch": context.get("branch", ""),
            "commit": context.get("commit", ""),
            "visibility": context.get("visibility", "UNKNOWN"),
        },
        "command": {
            "name": command_name,
            "mode": mode,
            "model": model,
            "effort": effort,
            "clone_depth": depth,
            "network_allowed": network_allowed,
            "codex_json": codex_json,
            "allow_invalid_report": allow_invalid_report,
        },
        "paths": {
            "run_dir": ".",
            "target_repo_dir": manifest_relative_path(run_dir, context.get("target_repo_dir"), "repo"),
            "reports_dir": manifest_relative_path(run_dir, context.get("reports_dir"), "reports"),
        },
        "schemas": collect_schemas(run_dir),
        "artifacts": collect_artifacts(run_dir),
        "execution": {
            "phase": execution_phase,
            "codex_status": none_if_empty(codex_status),
            "validation_status": none_if_empty(validation_status),
            "final_status": none_if_empty(final_status),
        },
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write GenAI Repo Auditor run manifest metadata")
    parser.add_argument("--lab-root", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--command-name", default="gra-audit")
    parser.add_argument("--mode", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--depth", required=True)
    parser.add_argument("--network-allowed", required=True)
    parser.add_argument("--codex-json", required=True)
    parser.add_argument("--allow-invalid-report", required=True)
    parser.add_argument("--execution-phase", required=True)
    parser.add_argument("--codex-status")
    parser.add_argument("--validation-status")
    parser.add_argument("--final-status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lab_root = Path(args.lab_root).resolve()
    run_dir = Path(args.run_dir).resolve()
    manifest = build_manifest(
        lab_root=lab_root,
        run_dir=run_dir,
        command_name=args.command_name,
        mode=args.mode,
        model=args.model,
        effort=args.effort,
        depth=args.depth,
        network_allowed=parse_bool(args.network_allowed),
        codex_json=parse_bool(args.codex_json),
        allow_invalid_report=parse_bool(args.allow_invalid_report),
        execution_phase=args.execution_phase,
        codex_status=args.codex_status,
        validation_status=args.validation_status,
        final_status=args.final_status,
    )
    write_manifest(run_dir / MANIFEST_FILENAME, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

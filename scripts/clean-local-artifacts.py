#!/usr/bin/env python3
"""Safely list or remove local GenAI Repo Auditor artifacts."""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CleanupSafetyError(ValueError):
    """Raised when a cleanup path is unsafe."""


@dataclass(frozen=True)
class Candidate:
    kind: str
    path: Path


def display_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_under_repo(value: str, label: str) -> Path:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else REPO_ROOT / raw
    absolute = candidate.absolute()
    root = REPO_ROOT.resolve()
    if absolute == root:
        raise CleanupSafetyError(f"{label} must not be the repository root")
    if not absolute.is_relative_to(root):
        raise CleanupSafetyError(f"{label} must stay under repository root: {root}")
    relative = absolute.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CleanupSafetyError(f"{label} must not contain symlink components: {display_path(current)}")
    resolved = absolute.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise CleanupSafetyError(f"{label} must stay under repository root after resolving symlinks: {root}")
    return resolved


def validate_existing_dir(path: Path, label: str) -> bool:
    if path.is_symlink():
        raise CleanupSafetyError(f"{label} must not be a symlink: {display_path(path)}")
    if not path.exists():
        return False
    if not path.is_dir():
        raise CleanupSafetyError(f"{label} must be a directory: {display_path(path)}")
    return True


def ensure_child_safe(base: Path, path: Path, label: str) -> None:
    if path.is_symlink():
        raise CleanupSafetyError(f"{label} candidate must not be a symlink: {display_path(path)}")
    try:
        path.resolve(strict=False).relative_to(base)
    except ValueError as exc:
        raise CleanupSafetyError(f"{label} candidate escapes base directory: {display_path(path)}") from exc


def collect_run_candidates(runs_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    if not validate_existing_dir(runs_dir, "runs-dir"):
        return candidates

    for child in sorted(runs_dir.iterdir()):
        ensure_child_safe(runs_dir, child, "runs-dir")
        if child.name == ".locks":
            continue
        if child.is_file() and child.suffix in {".sqlite", ".sqlite3"}:
            candidates.append(Candidate("file", child))
            continue
        if not child.is_dir():
            continue
        for run in sorted(child.iterdir()):
            ensure_child_safe(runs_dir, run, "runs-dir")
            if run.is_dir():
                candidates.append(Candidate("dir", run))
            elif run.is_file() and run.suffix in {".sqlite", ".sqlite3"}:
                candidates.append(Candidate("file", run))
    return candidates


def collect_batches_candidates(batches_dir: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    if not validate_existing_dir(batches_dir, "batches-dir"):
        return candidates

    for child in sorted(batches_dir.iterdir()):
        ensure_child_safe(batches_dir, child, "batches-dir")
        if child.is_dir():
            candidates.append(Candidate("dir", child))
        elif child.is_file():
            candidates.append(Candidate("file", child))
    return candidates


def remove_candidate(candidate: Candidate) -> None:
    if candidate.kind == "dir":
        shutil.rmtree(candidate.path)
    elif candidate.kind == "file":
        candidate.path.unlink()
    else:
        raise CleanupSafetyError(f"unknown candidate kind: {candidate.kind}")


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    deduped: list[Candidate] = []
    seen: set[Path] = set()
    for candidate in candidates:
        key = candidate.path.resolve(strict=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or remove local GenAI Repo Auditor run, batch, and store artifacts.",
    )
    parser.add_argument("--runs-dir", default="runs", help="Runs directory under this repository. Default: runs")
    parser.add_argument("--batches-dir", default="batches", help="Legacy batches directory under this repository. Default: batches")
    parser.add_argument("--skip-batches", action="store_true", help="Do not include the legacy batches directory")
    parser.add_argument("--apply", action="store_true", help="Actually remove listed artifacts. Default is dry-run")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        runs_dir = resolve_under_repo(args.runs_dir, "runs-dir")
        candidates = collect_run_candidates(runs_dir)
        if not args.skip_batches:
            batches_dir = resolve_under_repo(args.batches_dir, "batches-dir")
            candidates.extend(collect_batches_candidates(batches_dir))
        candidates = deduplicate_candidates(candidates)
    except CleanupSafetyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not candidates:
        print("No local artifacts found.")
        return 0

    if args.apply:
        print("Removing local artifacts:")
    else:
        print("DRY RUN: would remove local artifacts:")
    for candidate in candidates:
        print(f"- {candidate.kind}: {display_path(candidate.path)}")

    if not args.apply:
        print("\nNo files were removed. Re-run with --apply after reviewing the list.")
        return 0

    removed = 0
    failures: list[tuple[Candidate, str]] = []
    for candidate in candidates:
        try:
            remove_candidate(candidate)
            removed += 1
        except OSError as exc:
            failures.append((candidate, str(exc)))
    if failures:
        for candidate, message in failures:
            print(f"ERROR: failed to remove {candidate.kind}: {display_path(candidate.path)}: {message}", file=sys.stderr)
        print(f"\nRemoved {removed} artifact(s); {len(failures)} removal(s) failed.")
        return 1
    print(f"\nRemoved {removed} artifact(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

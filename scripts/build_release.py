#!/usr/bin/env python3
"""Validate and build reproducible GenAI Repo Auditor release artifacts.

Dry-run validation is the default. Artifact creation is explicit and only
accepts a committed Git object so that the resulting archives are independent
of untracked or modified working-tree content.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


PROJECT_NAME = "genai-repo-auditor"
PROJECT_DISPLAY_NAME = "GenAI Repo Auditor"
REPOSITORY_URL = "https://github.com/itdojp/genai-repo-auditor"
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGELOG_HEADING_RE = re.compile(r"^## v(?P<version>\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$")


class ReleaseError(RuntimeError):
    """Raised when release inputs or outputs fail a safety check."""


@dataclass(frozen=True)
class SourceSnapshot:
    version: str
    changelog_section: str
    commit: str
    tracked_files: tuple[str, ...]
    buildable: bool

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    @property
    def archive_prefix(self) -> str:
        return f"{PROJECT_NAME}-{self.tag}"


def run_git(repo_root: Path, *args: str, binary: bool = False) -> str | bytes:
    command = ["git", "-C", str(repo_root), *args]
    completed = subprocess.run(command, check=False, capture_output=True)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseError(f"git command failed ({' '.join(args)}): {stderr}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict")


def extract_changelog_section(changelog: str, version: str) -> str:
    lines = changelog.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if (match := CHANGELOG_HEADING_RE.match(line)) and match.group("version") == version
        ),
        None,
    )
    if start is None:
        raise ReleaseError(f"CHANGELOG.md is missing a dated v{version} section")
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    section = "\n".join(lines[start:end]).strip() + "\n"
    if not any(line.startswith("- ") for line in section.splitlines()[1:]):
        raise ReleaseError(f"CHANGELOG.md v{version} section has no release entries")
    return section


def _validate_ref(ref: str) -> None:
    if not ref or ref.startswith("-") or any(char in ref for char in ("\x00", "\n", "\r")):
        raise ReleaseError(f"unsafe source ref: {ref!r}")


def load_snapshot(repo_root: Path, source_ref: str) -> SourceSnapshot:
    repo_root = repo_root.resolve()
    if source_ref == "WORKTREE":
        version = (repo_root / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()
        changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
        tracked_raw = run_git(repo_root, "ls-files", "-z", binary=True)
        assert isinstance(tracked_raw, bytes)
        tracked_files = tuple(item.decode("utf-8") for item in tracked_raw.split(b"\0") if item)
        commit_raw = run_git(repo_root, "rev-parse", "HEAD")
        assert isinstance(commit_raw, str)
        commit = commit_raw.strip()
        buildable = False
    else:
        _validate_ref(source_ref)
        commit_raw = run_git(repo_root, "rev-parse", "--verify", f"{source_ref}^{{commit}}")
        assert isinstance(commit_raw, str)
        commit = commit_raw.strip()
        version_raw = run_git(repo_root, "show", f"{commit}:VERSION")
        changelog_raw = run_git(repo_root, "show", f"{commit}:CHANGELOG.md")
        tracked_raw = run_git(repo_root, "ls-tree", "-r", "--name-only", "-z", commit, binary=True)
        assert isinstance(version_raw, str)
        assert isinstance(changelog_raw, str)
        assert isinstance(tracked_raw, bytes)
        version = version_raw.splitlines()[0].strip()
        changelog = changelog_raw
        tracked_files = tuple(item.decode("utf-8") for item in tracked_raw.split(b"\0") if item)
        buildable = True

    if not VERSION_RE.fullmatch(version):
        raise ReleaseError(f"VERSION is not a canonical SemVer value: {version!r}")
    changelog_section = extract_changelog_section(changelog, version)
    return SourceSnapshot(
        version=version,
        changelog_section=changelog_section,
        commit=commit,
        tracked_files=tracked_files,
        buildable=buildable,
    )


def is_forbidden_release_path(raw_path: str) -> bool:
    """Return whether a tracked path is forbidden from release archives."""

    path = PurePosixPath(raw_path)
    parts = path.parts
    if not parts or path.is_absolute() or ".." in parts:
        return True

    # Versioned synthetic fixtures are reviewed source inputs for the test
    # suite, not outputs copied from an operator audit run.
    if len(parts) >= 2 and parts[:2] == ("tests", "fixtures"):
        return False

    forbidden_roots = {
        ".codex-local",
        ".test-tmp",
        "audits",
        "batches",
        "locks",
        "reports",
        "repos",
        "runs",
        "worktrees",
        "dist",
    }
    if parts[0] in forbidden_roots:
        return True

    forbidden_segments = {
        "duplicate-decisions",
        "issue-drafts",
        "remediation-workspaces",
        "scanner-results",
        "target-research",
    }
    if any(part in forbidden_segments for part in parts):
        return True

    forbidden_names = {
        "agent-events.jsonl",
        "agent-final.md",
        "checkov.json",
        "codeql-results.sarif",
        "codex-events.jsonl",
        "codex-final.md",
        "codex-stderr.txt",
        "codex-transcript.txt",
        "gitleaks.json",
        "semgrep.json",
        "trivy.json",
    }
    if path.name in forbidden_names:
        return True
    return path.suffix.lower() in {".sarif", ".sqlite", ".sqlite3"}


def forbidden_release_paths(paths: Iterable[str]) -> list[str]:
    return sorted(path for path in paths if is_forbidden_release_path(path))


def validate_snapshot(snapshot: SourceSnapshot) -> None:
    forbidden = forbidden_release_paths(snapshot.tracked_files)
    if forbidden:
        rendered = "\n".join(f"  - {path}" for path in forbidden)
        raise ReleaseError(f"tracked local/private artifacts are forbidden from releases:\n{rendered}")
    required = {"VERSION", "CHANGELOG.md", "LICENSE", "README.md", "MANIFEST.md"}
    missing = sorted(required.difference(snapshot.tracked_files))
    if missing:
        raise ReleaseError(f"release source is missing required files: {', '.join(missing)}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def release_asset_names(snapshot: SourceSnapshot) -> list[str]:
    stem = snapshot.archive_prefix
    return [
        f"{stem}.tar.gz",
        f"{stem}.zip",
        f"{stem}.cdx.json",
        "release-manifest.json",
        "SHA256SUMS",
    ]


def resolve_output_dir(output_dir: Path) -> Path:
    lexical_output = output_dir if output_dir.is_absolute() else Path.cwd() / output_dir
    for candidate in (lexical_output, *lexical_output.parents):
        if candidate.is_symlink():
            raise ReleaseError(f"release output path must not contain symlinks: {candidate}")
    return lexical_output.resolve()


def build_release(repo_root: Path, snapshot: SourceSnapshot, output_dir: Path) -> list[Path]:
    if not snapshot.buildable:
        raise ReleaseError("artifact creation requires a committed Git source ref, not WORKTREE")

    repo_root = repo_root.resolve()
    output_dir = resolve_output_dir(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReleaseError(f"release output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{snapshot.archive_prefix}/"
    tar_bytes = run_git(repo_root, "archive", "--format=tar", f"--prefix={prefix}", snapshot.commit, binary=True)
    zip_bytes = run_git(repo_root, "archive", "--format=zip", f"--prefix={prefix}", snapshot.commit, binary=True)
    assert isinstance(tar_bytes, bytes)
    assert isinstance(zip_bytes, bytes)

    tar_path = output_dir / f"{snapshot.archive_prefix}.tar.gz"
    with tar_path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
            gzip_handle.write(tar_bytes)

    zip_path = output_dir / f"{snapshot.archive_prefix}.zip"
    zip_path.write_bytes(zip_bytes)

    sbom_path = output_dir / f"{snapshot.archive_prefix}.cdx.json"
    sbom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "metadata": {
            "component": {
                "bom-ref": f"pkg:github/itdojp/{PROJECT_NAME}@{snapshot.version}",
                "externalReferences": [{"type": "vcs", "url": REPOSITORY_URL}],
                "group": "itdojp",
                "licenses": [{"license": {"id": "Apache-2.0"}}],
                "name": PROJECT_NAME,
                "properties": [
                    {"name": "org.opencontainers.image.revision", "value": snapshot.commit},
                    {"name": "org.opencontainers.image.source", "value": REPOSITORY_URL},
                ],
                "purl": f"pkg:github/itdojp/{PROJECT_NAME}@{snapshot.version}",
                "type": "application",
                "version": snapshot.version,
            }
        },
        "specVersion": "1.6",
        "version": 1,
    }
    _write_json(sbom_path, sbom)

    primary_assets = [tar_path, zip_path, sbom_path]
    manifest_path = output_dir / "release-manifest.json"
    manifest = {
        "artifacts": [
            {"name": path.name, "sha256": sha256_file(path), "size": path.stat().st_size}
            for path in primary_assets
        ],
        "project": PROJECT_DISPLAY_NAME,
        "schema_version": 1,
        "source_commit": snapshot.commit,
        "tag": snapshot.tag,
        "version": snapshot.version,
    }
    _write_json(manifest_path, manifest)

    checksum_inputs = [*primary_assets, manifest_path]
    checksums_path = output_dir / "SHA256SUMS"
    checksums_path.write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in sorted(checksum_inputs, key=lambda item: item.name)),
        encoding="utf-8",
    )

    notes_path = output_dir / "RELEASE_NOTES.md"
    notes_path.write_text(snapshot.changelog_section, encoding="utf-8")
    return [*primary_assets, manifest_path, checksums_path, notes_path]


def verify_checksums(output_dir: Path) -> None:
    output_dir = resolve_output_dir(output_dir)
    checksum_path = output_dir / "SHA256SUMS"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        raise ReleaseError(f"missing checksum file: {checksum_path}")
    for line_number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match:
            raise ReleaseError(f"invalid SHA256SUMS entry at line {line_number}")
        expected, name = match.groups()
        path = output_dir / name
        if not path.is_file() or path.is_symlink():
            raise ReleaseError(f"checksum target is missing or unsafe: {name}")
        actual = sha256_file(path)
        if actual != expected:
            raise ReleaseError(f"checksum mismatch: {name}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="validate and print the release plan without writing artifacts (default)")
    mode.add_argument("--build", action="store_true", help="build reproducible release artifacts from a committed Git ref")
    mode.add_argument("--verify", action="store_true", help="verify an existing output directory using SHA256SUMS")
    parser.add_argument(
        "--source-ref",
        help="Git ref to validate/build; defaults to WORKTREE for dry-run and HEAD for --build",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("dist"), help="artifact output directory (default: dist)")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1], help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        if args.verify:
            verified_output = resolve_output_dir(args.output_dir)
            verify_checksums(verified_output)
            print(json.dumps({"output_dir": str(verified_output), "status": "verified"}, sort_keys=True))
            return 0

        source_ref = args.source_ref or ("HEAD" if args.build else "WORKTREE")
        snapshot = load_snapshot(repo_root, source_ref)
        validate_snapshot(snapshot)
        result: dict[str, object] = {
            "assets": release_asset_names(snapshot),
            "mode": "build" if args.build else "dry-run",
            "source_commit": snapshot.commit,
            "source_ref": source_ref,
            "status": "validated",
            "tag": snapshot.tag,
            "tracked_file_count": len(snapshot.tracked_files),
            "version": snapshot.version,
        }
        if args.build:
            built = build_release(repo_root, snapshot, args.output_dir)
            verified_output = resolve_output_dir(args.output_dir)
            verify_checksums(verified_output)
            result["files"] = [path.name for path in built]
            result["output_dir"] = str(verified_output)
            result["status"] = "built-and-verified"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ReleaseError) as exc:
        print(f"release error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

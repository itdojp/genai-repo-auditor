#!/usr/bin/env python3
"""Validate PyPI wheel/sdist metadata, resources, and exclusion boundaries."""

from __future__ import annotations

import argparse
import configparser
import email
import re
import stat
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


PROJECT_NAME = "genai-repo-auditor"
PRIVATE_ROOTS = {
    ".codex-local",
    ".test-tmp",
    "audits",
    "batches",
    "build",
    "dist",
    "holdout",
    "locks",
    "private-holdout",
    "repos",
    "reports",
    "runs",
    "tests",
    "worktrees",
}
PRIVATE_FILENAMES = {
    "agent-events.jsonl",
    "agent-final.md",
    "codex-events.jsonl",
    "codex-final.md",
    "codex-stderr.txt",
    "codex-transcript.txt",
    "holdout-aggregate.json",
    "holdout-metadata.json",
}
PRIVATE_SUFFIXES = {".sarif", ".sqlite", ".sqlite3"}


class DistributionValidationError(RuntimeError):
    """Raised when a built Python distribution violates the release contract."""


@dataclass(frozen=True)
class Archive:
    path: Path
    files: dict[str, bytes]


def _safe_member_name(name: str) -> str:
    if "\\" in name:
        raise DistributionValidationError(f"archive member uses a backslash: {name}")
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts:
        raise DistributionValidationError(f"archive member is not safely relative: {name}")
    normalized = path.as_posix().rstrip("/")
    if not normalized or normalized == ".":
        raise DistributionValidationError(f"archive member is empty after normalization: {name}")
    return normalized


def load_wheel(path: Path) -> Archive:
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = _safe_member_name(info.filename)
            if info.is_dir():
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise DistributionValidationError(f"wheel member must not be a symlink: {name}")
            if name in files:
                raise DistributionValidationError(f"wheel has duplicate member: {name}")
            files[name] = archive.read(info)
    return Archive(path=path, files=files)


def load_sdist(path: Path) -> Archive:
    files: dict[str, bytes] = {}
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive.getmembers():
            name = _safe_member_name(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise DistributionValidationError(
                    f"sdist member must be a regular file, not a link or device: {name}"
                )
            if name in files:
                raise DistributionValidationError(f"sdist has duplicate member: {name}")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise DistributionValidationError(f"could not read sdist member: {name}")
            files[name] = extracted.read()
    return Archive(path=path, files=files)


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _canonical_specifier(value: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip() for part in value.split(",") if part.strip()))


def _metadata(archive: Archive, suffix: str) -> tuple[str, object]:
    matches = [(name, body) for name, body in archive.files.items() if name.endswith(suffix)]
    if len(matches) != 1:
        raise DistributionValidationError(
            f"{archive.path.name} must contain exactly one {suffix}, found {len(matches)}"
        )
    name, body = matches[0]
    return name, email.message_from_bytes(body)


def _project_config(repo_root: Path) -> tuple[dict[str, object], str]:
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    python_match = re.search(r'^requires-python\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    scripts_match = re.search(
        r"^\[project\.scripts\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if python_match is None or scripts_match is None:
        raise DistributionValidationError("pyproject.toml is missing requires-python or project.scripts")
    scripts = dict(
        re.findall(
            r'^([a-z0-9][a-z0-9-]*)\s*=\s*"([^"]+)"\s*$',
            scripts_match.group("body"),
            re.MULTILINE,
        )
    )
    if not scripts:
        raise DistributionValidationError("pyproject.toml project.scripts is empty")
    project: dict[str, object] = {
        "requires-python": python_match.group(1),
        "scripts": scripts,
    }
    version = (repo_root / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()
    return project, version


def validate_metadata(archive: Archive, metadata_suffix: str, repo_root: Path) -> None:
    _name, metadata = _metadata(archive, metadata_suffix)
    project, version = _project_config(repo_root)
    expected_python = project["requires-python"]
    if _canonical_name(metadata["Name"] or "") != PROJECT_NAME:
        raise DistributionValidationError(f"unexpected distribution name in {archive.path.name}")
    if metadata["Version"] != version:
        raise DistributionValidationError(
            f"distribution version {metadata['Version']!r} does not match VERSION {version!r}"
        )
    if _canonical_specifier(metadata["Requires-Python"] or "") != _canonical_specifier(expected_python):
        raise DistributionValidationError(
            f"Requires-Python {metadata['Requires-Python']!r} does not match pyproject {expected_python!r}"
        )
    if metadata["License-Expression"] != "Apache-2.0":
        raise DistributionValidationError("distribution must declare Apache-2.0 License-Expression")
    content_type = metadata["Description-Content-Type"] or ""
    if not content_type.lower().startswith("text/markdown"):
        raise DistributionValidationError("README metadata must use text/markdown content type")
    urls = metadata.get_all("Project-URL", [])
    labels = {entry.split(",", 1)[0].strip() for entry in urls if "," in entry}
    required_labels = {"Homepage", "Repository", "Issues", "Changelog", "Documentation"}
    missing = sorted(required_labels - labels)
    if missing:
        raise DistributionValidationError(f"missing Project-URL labels: {', '.join(missing)}")


def _runtime_resources(repo_root: Path) -> set[str]:
    expected = {"VERSION", "templates/taxonomy-aliases.json"}
    patterns = (
        "bin/gra-*",
        "lib/**/*.py",
        "prompts/**/*.md",
        "templates/agent-workers/*",
        "templates/dogfood/*",
        "templates/reports/*",
        "templates/taxonomies/*.json",
        "templates/workflows/*.json",
        "benchmarks/corpus/**/*",
    )
    for pattern in patterns:
        expected.update(
            path.relative_to(repo_root).as_posix()
            for path in repo_root.glob(pattern)
            if path.is_file()
        )
    return expected


def _reject_private_paths(relative_paths: set[str], archive_name: str) -> None:
    violations: list[str] = []
    for name in sorted(relative_paths):
        parts = PurePosixPath(name).parts
        if not parts:
            continue
        lowered = [part.lower() for part in parts]
        filename = lowered[-1]
        private_components = [
            index
            for index, part in enumerate(lowered)
            if part in PRIVATE_ROOTS
            and not (part == "reports" and index > 0 and lowered[index - 1] == "templates")
        ]
        if private_components:
            violations.append(name)
        elif filename in PRIVATE_FILENAMES or Path(filename).suffix in PRIVATE_SUFFIXES:
            violations.append(name)
        elif "scanner-results" in lowered or "issue-drafts" in lowered:
            violations.append(name)
    if violations:
        raise DistributionValidationError(
            f"{archive_name} contains private/local artifact paths: {', '.join(violations[:10])}"
        )


def validate_wheel(archive: Archive, repo_root: Path) -> None:
    validate_metadata(archive, ".dist-info/METADATA", repo_root)
    _reject_private_paths(set(archive.files), archive.path.name)
    entry_name, entry_body = next(
        (
            (name, body)
            for name, body in archive.files.items()
            if name.endswith(".dist-info/entry_points.txt")
        ),
        ("", b""),
    )
    if not entry_name:
        raise DistributionValidationError("wheel is missing dist-info/entry_points.txt")
    parser = configparser.ConfigParser()
    parser.read_string(entry_body.decode("utf-8"))
    actual_commands = set(parser["console_scripts"] if parser.has_section("console_scripts") else ())
    project, _version = _project_config(repo_root)
    expected_commands = set(project["scripts"])
    if actual_commands != expected_commands:
        raise DistributionValidationError("wheel console scripts do not match pyproject.toml")

    data_prefixes = {
        name.split("/share/genai-repo-auditor/", 1)[0] + "/share/genai-repo-auditor/"
        for name in archive.files
        if "/share/genai-repo-auditor/" in name
    }
    if len(data_prefixes) != 1:
        raise DistributionValidationError("wheel must contain one packaged resource root")
    prefix = next(iter(data_prefixes))
    actual_resources = {name[len(prefix) :] for name in archive.files if name.startswith(prefix)}
    missing = sorted(_runtime_resources(repo_root) - actual_resources)
    if missing:
        raise DistributionValidationError(f"wheel is missing runtime resources: {', '.join(missing[:10])}")


def validate_sdist(archive: Archive, repo_root: Path) -> None:
    validate_metadata(archive, "/PKG-INFO", repo_root)
    roots = {PurePosixPath(name).parts[0] for name in archive.files}
    if len(roots) != 1:
        raise DistributionValidationError("sdist must contain exactly one top-level directory")
    root = next(iter(roots))
    relative = {name[len(root) + 1 :] for name in archive.files if name.startswith(root + "/")}
    required_build_inputs = {
        "LICENSE",
        "MANIFEST.in",
        "NOTICE",
        "PKG-INFO",
        "README.md",
        "VERSION",
        "pyproject.toml",
        "src/genai_repo_auditor/__init__.py",
    }
    missing = sorted((required_build_inputs | _runtime_resources(repo_root)) - relative)
    if missing:
        raise DistributionValidationError(f"sdist is missing required files: {', '.join(missing[:10])}")
    _reject_private_paths(relative, archive.path.name)


def validate_dist_dir(dist_dir: Path, repo_root: Path) -> tuple[Path, Path]:
    lexical_dist = dist_dir if dist_dir.is_absolute() else Path.cwd() / dist_dir
    if any(candidate.is_symlink() for candidate in (lexical_dist, *lexical_dist.parents)):
        raise DistributionValidationError(f"distribution directory path must not contain symlinks: {dist_dir}")
    if not lexical_dist.is_dir():
        raise DistributionValidationError(f"distribution directory must be a real directory: {dist_dir}")
    entries = sorted(lexical_dist.iterdir())
    wheels = [path for path in entries if path.name.endswith(".whl")]
    sdists = [path for path in entries if path.name.endswith(".tar.gz")]
    expected_entries = {*wheels, *sdists}
    unexpected = sorted(
        path.name
        for path in entries
        if path not in expected_entries or path.is_symlink() or not path.is_file()
    )
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        raise DistributionValidationError(
            "distribution directory must contain exactly one wheel and one sdist"
            + (f"; unexpected: {', '.join(unexpected)}" if unexpected else "")
        )
    wheel, sdist = wheels[0], sdists[0]
    _project, version = _project_config(repo_root)
    expected_wheel = f"genai_repo_auditor-{version}-py3-none-any.whl"
    expected_sdist = f"genai_repo_auditor-{version}.tar.gz"
    if wheel.name != expected_wheel or sdist.name != expected_sdist:
        raise DistributionValidationError(
            f"distribution filenames must be {expected_wheel} and {expected_sdist}"
        )
    validate_wheel(load_wheel(wheel), repo_root)
    validate_sdist(load_sdist(sdist), repo_root)
    return wheel, sdist


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True, help="Directory containing one wheel and one sdist")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        wheel, sdist = validate_dist_dir(args.dist_dir, repo_root)
    except (DistributionValidationError, OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"python distribution validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"validated Python distributions: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

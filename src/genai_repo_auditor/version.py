from __future__ import annotations

from importlib import metadata
from pathlib import Path

DISTRIBUTION_NAME = "genai-repo-auditor"


def _source_root() -> Path | None:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        source_package = parent / "src" / "genai_repo_auditor"
        try:
            module_path.relative_to(source_package)
        except ValueError:
            continue
        if (parent / "VERSION").is_file() and (parent / "prompts").is_dir() and (parent / "templates").is_dir():
            return parent
    return None


def _source_version() -> str | None:
    root = _source_root()
    if root is None:
        return None
    lines = (root / "VERSION").read_text(encoding="utf-8").splitlines()
    value = lines[0].strip() if lines else ""
    return value or None


def package_version() -> str:
    """Return source-checkout version metadata or the installed distribution version."""

    source_version = _source_version()
    if source_version is not None:
        return source_version
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"

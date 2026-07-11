from __future__ import annotations

import os
import sysconfig
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Iterable

from .version import DISTRIBUTION_NAME

RESOURCE_DIR_NAME = DISTRIBUTION_NAME
ENV_RESOURCE_ROOT = "GENAI_REPO_AUDITOR_RESOURCE_ROOT"


class ResourceDiscoveryError(RuntimeError):
    """Raised when packaged GenAI Repo Auditor resources cannot be located."""


def _looks_like_resource_root(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "prompts" / "AGENTS.audit.md").is_file()
        and (path / "templates" / "reports" / "findings.schema.json").is_file()
        and (path / "templates" / "taxonomies" / "owasp-llm-2025.json").is_file()
        and (path / "templates" / "agent-workers" / "codex-cli.json").is_file()
        and (path / "benchmarks" / "corpus" / "core.json").is_file()
        and (path / "benchmarks" / "corpus" / "case.schema.json").is_file()
        and (path / "benchmarks" / "corpus" / "corpus.schema.json").is_file()
        and (path / "benchmarks" / "corpus" / "cases").is_dir()
    )


def _source_root() -> Path | None:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        source_package = parent / "src" / "genai_repo_auditor"
        try:
            module_path.relative_to(source_package)
        except ValueError:
            continue
        if (parent / "VERSION").is_file() and _looks_like_resource_root(parent):
            return parent
    return None


def _distribution_resource_roots() -> Iterable[Path]:
    try:
        dist = metadata.distribution(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return []
    roots: list[Path] = []
    for file in dist.files or []:
        located = Path(dist.locate_file(file))
        for candidate in (located if located.is_dir() else located.parent, *located.parents):
            if candidate.name == RESOURCE_DIR_NAME and _looks_like_resource_root(candidate):
                roots.append(candidate.resolve())
                break
    return roots


def resource_root(*, honor_env_override: bool = True) -> Path:
    """Return the root directory that owns packaged prompts and templates.

    Source checkouts resolve to the repository root. Installed wheels resolve to
    the distribution data directory (for example, ``share/genai-repo-auditor``)
    and therefore do not depend on the original checkout path.  Console-script
    adapters that execute bundled code disable ``honor_env_override`` so a local
    resource-root override cannot redirect executable helpers.
    """

    override = os.environ.get(ENV_RESOURCE_ROOT)
    if honor_env_override and override:
        candidate = Path(override).expanduser().resolve()
        if _looks_like_resource_root(candidate):
            return candidate
        raise ResourceDiscoveryError(f"{ENV_RESOURCE_ROOT} does not point to packaged resources: {candidate}")

    source_root = _source_root()
    if source_root is not None:
        return source_root

    for candidate in _distribution_resource_roots():
        return candidate

    data_candidate = Path(sysconfig.get_path("data")) / "share" / RESOURCE_DIR_NAME
    if _looks_like_resource_root(data_candidate):
        return data_candidate.resolve()

    raise ResourceDiscoveryError("could not locate GenAI Repo Auditor prompts/templates resources")


def _validate_relative_parts(parts: tuple[str, ...]) -> PurePosixPath:
    if not parts:
        raise ValueError("resource path requires at least one component")
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part or ":" in part:
            raise ValueError(f"resource path must use safe relative path components: {part!r}")
    path = PurePosixPath(*parts)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"resource path must be relative and contained: {path}")
    return path


def resource_path(*parts: str, must_exist: bool = True) -> Path:
    """Return a safe filesystem path under :func:`resource_root`."""

    relative = _validate_relative_parts(parts)
    path = resource_root().joinpath(*relative.parts)
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def prompt_path(*parts: str, must_exist: bool = True) -> Path:
    return resource_path("prompts", *parts, must_exist=must_exist)


def template_path(*parts: str, must_exist: bool = True) -> Path:
    return resource_path("templates", *parts, must_exist=must_exist)


def report_schema_path(name: str) -> Path:
    if not name.endswith(".schema.json"):
        raise ValueError("report schema names must end with .schema.json")
    return template_path("reports", name)


def taxonomy_path(name: str) -> Path:
    if not name.endswith(".json"):
        raise ValueError("taxonomy names must end with .json")
    return template_path("taxonomies", name)


def agent_worker_profile_path(name: str) -> Path:
    return template_path("agent-workers", name)


def efficacy_corpus_path(*parts: str, must_exist: bool = True) -> Path:
    return resource_path("benchmarks", "corpus", *parts, must_exist=must_exist)


def read_resource_text(*parts: str, encoding: str = "utf-8") -> str:
    return resource_path(*parts).read_text(encoding=encoding)

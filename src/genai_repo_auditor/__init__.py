from __future__ import annotations

from .resources import (
    ResourceDiscoveryError,
    agent_worker_profile_path,
    efficacy_corpus_path,
    prompt_path,
    read_resource_text,
    report_schema_path,
    resource_path,
    resource_root,
    taxonomy_path,
    template_path,
)
from .version import DISTRIBUTION_NAME, package_version

__all__ = [
    "DISTRIBUTION_NAME",
    "ResourceDiscoveryError",
    "__version__",
    "agent_worker_profile_path",
    "efficacy_corpus_path",
    "package_version",
    "prompt_path",
    "read_resource_text",
    "report_schema_path",
    "resource_path",
    "resource_root",
    "taxonomy_path",
    "template_path",
]

__version__ = package_version()

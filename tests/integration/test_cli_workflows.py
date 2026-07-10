from __future__ import annotations

import importlib
import unittest
from functools import lru_cache

_FEATURE_MODULES = [
    ("test_audit_research_workflows", "AuditResearchWorkflowTests"),
    ("test_remediation_workflows", "RemediationWorkflowTests"),
    ("test_metrics_workflows", "MetricsWorkflowTests"),
    ("test_worker_profile_workflows", "WorkerProfileWorkflowTests"),
    ("test_validation_workflows", "ValidationWorkflowTests"),
    ("test_publication_workflows", "PublicationWorkflowTests"),
    ("test_scanner_store_workflows", "ScannerStoreWorkflowTests"),
    ("test_batch_workflows", "BatchWorkflowTests"),
]


def _import_feature_module(module_name: str):
    package = __package__ or "tests.integration"
    try:
        return importlib.import_module(f"{package}.{module_name}")
    except ModuleNotFoundError:
        return importlib.import_module(module_name)


@lru_cache(maxsize=1)
def _legacy_cli_workflow_tests() -> type[unittest.TestCase]:
    bases = tuple(getattr(_import_feature_module(module_name), class_name) for module_name, class_name in _FEATURE_MODULES)
    return type(
        "CliWorkflowTests",
        bases,
        {
            "__module__": __name__,
            "__doc__": "Backward-compatible alias for the split integration workflow suites.",
        },
    )


def __getattr__(name: str):
    if name == "CliWorkflowTests":
        return _legacy_cli_workflow_tests()
    raise AttributeError(name)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    """Preserve direct module runs without duplicating discovery.

    `python3 -m unittest tests.integration.test_cli_workflows` loads every split
    feature suite. `unittest discover` receives an empty suite here so the real
    feature modules are discovered exactly once.
    """
    if pattern is not None:
        return unittest.TestSuite()
    suite = unittest.TestSuite()
    for module_name, _class_name in _FEATURE_MODULES:
        suite.addTests(loader.loadTestsFromModule(_import_feature_module(module_name)))
    return suite

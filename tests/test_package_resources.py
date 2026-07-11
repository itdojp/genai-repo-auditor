from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from genai_repo_auditor import (  # noqa: E402
    ResourceDiscoveryError,
    __version__,
    agent_worker_profile_path,
    package_version,
    prompt_path,
    read_resource_text,
    report_schema_path,
    resource_path,
    resource_root,
    taxonomy_path,
)
from genai_repo_auditor import resources as gra_resources  # noqa: E402
from genai_repo_auditor import version as gra_version  # noqa: E402


def pyproject_data_file_destinations(text: str) -> set[str]:
    lines = text.splitlines()
    try:
        start = lines.index("[tool.setuptools.data-files]") + 1
    except ValueError as exc:
        raise AssertionError("pyproject.toml is missing [tool.setuptools.data-files]") from exc
    destinations: set[str] = set()
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("["):
            break
        if stripped.startswith('"') and '" =' in stripped:
            destinations.add(stripped.split('" =', 1)[0].strip('"'))
    return destinations


class PackageResourceTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def write_minimal_resource_root(self, root: Path, marker: str) -> None:
        (root / "prompts").mkdir(parents=True, exist_ok=True)
        (root / "prompts" / "AGENTS.audit.md").write_text(marker, encoding="utf-8")
        (root / "templates" / "reports").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "reports" / "findings.schema.json").write_text("{}", encoding="utf-8")
        (root / "templates" / "taxonomies").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "taxonomies" / "owasp-llm-2025.json").write_text("{}", encoding="utf-8")
        (root / "templates" / "agent-workers").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "agent-workers" / "codex-cli.json").write_text("{}", encoding="utf-8")

    def test_package_version_matches_canonical_version_file(self) -> None:
        expected = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").splitlines()[0].strip()
        self.assertEqual(expected, package_version())
        self.assertEqual(expected, __version__)

    def test_package_version_prefers_source_checkout_metadata_when_loaded_from_src_package(self) -> None:
        source_root = self.work_dir / "source-root"
        source_root.mkdir()
        (source_root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        self.write_minimal_resource_root(source_root, "source prompt")
        source_package = source_root / "src" / "genai_repo_auditor"
        source_package.mkdir(parents=True)
        fake_module = source_package / "version.py"
        fake_module.write_text("# marker\n", encoding="utf-8")

        original_file = gra_version.__file__
        original_metadata_version = gra_version.metadata.version
        try:
            gra_version.__file__ = str(fake_module)
            gra_version.metadata.version = lambda _name: "0.4.0"
            self.assertEqual(source_root.resolve(), gra_version._source_root())
            self.assertEqual("9.9.9", gra_version.package_version())
        finally:
            gra_version.__file__ = original_file
            gra_version.metadata.version = original_metadata_version

    def test_source_tree_resource_discovery_finds_required_resource_families(self) -> None:
        self.assertEqual(REPO_ROOT, resource_root())
        self.assertEqual(REPO_ROOT / "prompts" / "AGENTS.audit.md", prompt_path("AGENTS.audit.md"))
        self.assertEqual(
            REPO_ROOT / "prompts" / "exec" / "full-audit.prompt.md",
            prompt_path("exec", "full-audit.prompt.md"),
        )
        self.assertEqual(
            REPO_ROOT / "templates" / "reports" / "findings.schema.json",
            report_schema_path("findings.schema.json"),
        )
        self.assertEqual(
            REPO_ROOT / "templates" / "taxonomies" / "owasp-llm-2025.json",
            taxonomy_path("owasp-llm-2025.json"),
        )
        self.assertEqual(
            REPO_ROOT / "templates" / "agent-workers" / "codex-cli.json",
            agent_worker_profile_path("codex-cli.json"),
        )
        self.assertIn("severity", read_resource_text("templates", "reports", "findings.schema.json"))

    def test_resource_path_rejects_absolute_and_traversal_components(self) -> None:
        with self.assertRaisesRegex(ValueError, "safe relative path components"):
            resource_path("/etc/passwd")
        with self.assertRaisesRegex(ValueError, "safe relative path components"):
            resource_path("templates", "..", "VERSION")
        with self.assertRaisesRegex(ValueError, "safe relative path components"):
            resource_path("templates\\reports")
        with self.assertRaisesRegex(ValueError, "safe relative path components"):
            resource_path("C:\\Windows")
        with self.assertRaisesRegex(ValueError, "schema names"):
            report_schema_path("findings.json")
        with self.assertRaisesRegex(ValueError, "taxonomy names"):
            taxonomy_path("taxonomy.txt")

    def test_resource_root_environment_override_must_contain_packaged_resources(self) -> None:
        original = os.environ.get(gra_resources.ENV_RESOURCE_ROOT)
        try:
            os.environ[gra_resources.ENV_RESOURCE_ROOT] = str(REPO_ROOT / "templates")
            with self.assertRaises(ResourceDiscoveryError):
                resource_root()
        finally:
            if original is None:
                os.environ.pop(gra_resources.ENV_RESOURCE_ROOT, None)
            else:
                os.environ[gra_resources.ENV_RESOURCE_ROOT] = original

    def test_installed_distribution_resources_are_not_hijacked_by_ancestor_checkout_layout(self) -> None:
        fake_ancestor = self.work_dir / "fake-ancestor"
        fake_ancestor.mkdir()
        (fake_ancestor / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        self.write_minimal_resource_root(fake_ancestor, "fake ancestor prompt")
        fake_installed_share = self.work_dir / "venv" / "share" / "genai-repo-auditor"
        self.write_minimal_resource_root(fake_installed_share, "installed prompt")

        original_file = gra_resources.__file__
        original_distribution_roots = gra_resources._distribution_resource_roots
        try:
            gra_resources.__file__ = str(
                fake_ancestor / "venv" / "lib" / "python3.12" / "site-packages" / "genai_repo_auditor" / "resources.py"
            )
            gra_resources._distribution_resource_roots = lambda: [fake_installed_share]
            self.assertIsNone(gra_resources._source_root())
            self.assertEqual(fake_installed_share.resolve(), resource_root())
            self.assertEqual("installed prompt", prompt_path("AGENTS.audit.md").read_text(encoding="utf-8"))
        finally:
            gra_resources.__file__ = original_file
            gra_resources._distribution_resource_roots = original_distribution_roots

    def test_source_root_requires_module_to_be_loaded_from_src_package(self) -> None:
        source_root = self.work_dir / "source-root"
        source_root.mkdir()
        (source_root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        self.write_minimal_resource_root(source_root, "source prompt")
        source_package = source_root / "src" / "genai_repo_auditor"
        source_package.mkdir(parents=True)
        fake_module = source_package / "resources.py"
        fake_module.write_text("# marker\n", encoding="utf-8")

        original_file = gra_resources.__file__
        try:
            gra_resources.__file__ = str(fake_module)
            self.assertEqual(source_root.resolve(), gra_resources._source_root())
        finally:
            gra_resources.__file__ = original_file

    def test_pyproject_declares_src_package_and_resource_data_without_local_artifacts(self) -> None:
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('package-dir = { "" = "src" }', pyproject)
        self.assertIn('packages = ["genai_repo_auditor"]', pyproject)
        self.assertIn('version = { file = "VERSION" }', pyproject)
        self.assertIn('license = "Apache-2.0"', pyproject)
        self.assertIn('license-files = ["LICENSE", "NOTICE"]', pyproject)
        self.assertIn("setuptools>=77", pyproject)

        data_files = pyproject_data_file_destinations(pyproject)
        expected_destinations = {
            "share/genai-repo-auditor",
            "share/genai-repo-auditor/bin",
            "share/genai-repo-auditor/lib",
            "share/genai-repo-auditor/lib/publication",
            "share/genai-repo-auditor/lib/validators",
            "share/genai-repo-auditor/prompts",
            "share/genai-repo-auditor/prompts/codex",
            "share/genai-repo-auditor/prompts/exec",
            "share/genai-repo-auditor/prompts/goal",
            "share/genai-repo-auditor/prompts/issue",
            "share/genai-repo-auditor/templates",
            "share/genai-repo-auditor/templates/agent-workers",
            "share/genai-repo-auditor/templates/dogfood",
            "share/genai-repo-auditor/templates/reports",
            "share/genai-repo-auditor/templates/taxonomies",
            "share/genai-repo-auditor/templates/workflows",
        }
        self.assertEqual(expected_destinations, data_files)
        serialized = pyproject
        forbidden_terms = [
            ".codex-local",
            ".test-tmp",
            "audits/",
            "batches/",
            "build/",
            "dist/",
            "locks/",
            "repos/",
            "runs/",
            "worktrees/",
            ".egg-info",
            "scanner-results",
            "issue-drafts",
            ".sqlite",
            ".sarif",
            "codex-final",
            "codex-events",
        ]
        self.assertEqual([], [term for term in forbidden_terms if term in serialized])

    def test_sdist_manifest_prunes_local_and_generated_artifact_roots(self) -> None:
        manifest = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        for directive in [
            "recursive-include bin gra-*",
            "recursive-include lib *.py",
            "prune .codex-local",
            "prune .test-tmp",
            "prune audits",
            "prune batches",
            "prune build",
            "prune dist",
            "prune locks",
            "prune repos",
            "prune reports",
            "prune runs",
            "prune src/genai_repo_auditor.egg-info",
            "prune worktrees",
            "global-exclude __pycache__ *.py[cod] *.sqlite *.sqlite3 *.sarif",
            "global-exclude codex-events.jsonl codex-final.md codex-stderr.txt codex-transcript.txt",
            "global-exclude agent-events.jsonl agent-final.md",
            "global-exclude semgrep.json gitleaks.json trivy.json checkov.json codeql-results.sarif",
        ]:
            self.assertIn(directive, manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)

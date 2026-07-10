from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import build_release


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = REPO_ROOT / "VERSION"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_PROCESS = REPO_ROOT / "docs" / "RELEASE_PROCESS.md"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
RELEASE_SCRIPT = REPO_ROOT / "scripts" / "build_release.py"


def project_version() -> str:
    return VERSION.read_text(encoding="utf-8").splitlines()[0].strip()


def changelog_section(version: str) -> str:
    return build_release.extract_changelog_section(CHANGELOG.read_text(encoding="utf-8"), version)


class ReleaseMetadataTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        try:
            self.tmp_parent.rmdir()
        except OSError:
            pass

    def test_version_uses_documented_semver_without_tag_prefix(self) -> None:
        version = project_version()
        self.assertRegex(version, r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertFalse(version.startswith("v"), "VERSION must not include the tag prefix")

    def test_changelog_has_matching_current_version_section(self) -> None:
        version = project_version()
        section = changelog_section(version)
        self.assertRegex(section.splitlines()[0], rf"^## v{re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$")
        entries = [line for line in section.splitlines()[1:] if line.startswith("- ")]
        self.assertTrue(entries, f"CHANGELOG.md section for v{version} must contain release notes")

    def test_v040_notes_cover_required_user_visible_changes_and_boundaries(self) -> None:
        text = changelog_section("0.4.0").lower()
        required_terms = {
            "worker": "AI worker profiles",
            "gra-agent-check": "agent readiness command",
            "sandbox": "sandbox profiles",
            "gra-sandbox-check": "sandbox readiness command",
            "remediation": "remediation candidates",
            "patch-validation": "patch validation",
            "novelty": "novelty ledger",
            "multi-vote": "multi-vote validation",
            "metrics": "metrics",
            "benchmark": "workflow benchmark",
            "evidence graph": "evidence graph",
            "external finding import": "external import",
            "no-findings": "explicit no-findings",
            "recon-only": "recon-only profile",
            "dogfood": "dogfood materials",
            "local-first": "local-first boundary",
            "defensive-only": "defensive-only boundary",
        }
        missing = [description for term, description in required_terms.items() if term not in text]
        self.assertEqual([], missing)

    def test_release_process_links_canonical_metadata_and_uses_v_tag_convention(self) -> None:
        text = RELEASE_PROCESS.read_text(encoding="utf-8")
        self.assertIn("[`VERSION`](../VERSION)", text)
        self.assertIn("[`CHANGELOG.md`](../CHANGELOG.md)", text)
        self.assertRegex(text, r"VERSION=\d+\.\d+\.\d+")
        self.assertRegex(text, r"tag `v\d+\.\d+\.\d+`")
        self.assertIn('test "v$VERSION_VALUE" = "vX.Y.Z"', text)
        self.assertIn('git tag -a "v$VERSION_VALUE"', text)
        self.assertIn("-f publish=false", text)
        self.assertIn("-f publish=true", text)
        self.assertIn("gh attestation verify", text)

    def test_release_dry_run_is_non_mutating_and_machine_readable(self) -> None:
        output_dir = self.work_dir / "must-not-exist"
        completed = subprocess.run(
            [
                sys.executable,
                str(RELEASE_SCRIPT),
                "--dry-run",
                "--output-dir",
                str(output_dir),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("dry-run", payload["mode"])
        self.assertEqual("validated", payload["status"])
        self.assertEqual(project_version(), payload["version"])
        self.assertIn(f"genai-repo-auditor-v{project_version()}.tar.gz", payload["assets"])
        self.assertFalse(output_dir.exists())

    def test_release_builder_rejects_local_private_and_generated_paths(self) -> None:
        forbidden = {
            ".codex-local/session.json",
            "audits/private-run/reports/findings.json",
            "batches/results.json",
            "dist/release.zip",
            "reports/findings.json",
            "runs/owner__repo/run/repo/app.py",
            "nested/scanner-results/raw.json",
            "nested/issue-drafts/SEC-001.md",
            "private.sqlite",
            "scan.sarif",
            "codex-transcript.txt",
        }
        self.assertEqual(sorted(forbidden), build_release.forbidden_release_paths(forbidden))
        allowed = {
            ".github/workflows/release.yml",
            "templates/reports/findings.schema.json",
            "tests/fixtures/advanced-workflow-run/reports/findings.json",
            "tests/fixtures/advanced-workflow-run/reports/scanner-results/fixture.json",
            "docs/REPORT_CONTRACT.md",
        }
        self.assertEqual([], build_release.forbidden_release_paths(allowed))

    def _create_release_fixture_repository(self) -> Path:
        repo = self.work_dir / "fixture-repo"
        repo.mkdir()
        (repo / "VERSION").write_text("9.8.7\n", encoding="utf-8")
        (repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## v9.8.7 - 2026-07-10\n\n- Fixture release.\n",
            encoding="utf-8",
        )
        (repo / "LICENSE").write_text("fixture license\n", encoding="utf-8")
        (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        (repo / "MANIFEST.md").write_text("# Fixture manifest\n", encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Release Fixture"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "-c", "commit.gpgsign=false", "commit", "-m", "fixture"],
            check=True,
            capture_output=True,
        )
        return repo

    def test_release_build_is_reproducible_and_checksum_verified(self) -> None:
        repo = self._create_release_fixture_repository()
        snapshot = build_release.load_snapshot(repo, "HEAD")
        build_release.validate_snapshot(snapshot)
        first = self.work_dir / "first"
        second = self.work_dir / "second"
        build_release.build_release(repo, snapshot, first)
        build_release.build_release(repo, snapshot, second)
        build_release.verify_checksums(first)
        build_release.verify_checksums(second)

        first_files = {path.name: path.read_bytes() for path in first.iterdir() if path.is_file()}
        second_files = {path.name: path.read_bytes() for path in second.iterdir() if path.is_file()}
        self.assertEqual(first_files, second_files)

        sbom = json.loads((first / "genai-repo-auditor-v9.8.7.cdx.json").read_text(encoding="utf-8"))
        self.assertEqual("CycloneDX", sbom["bomFormat"])
        self.assertEqual("1.6", sbom["specVersion"])
        self.assertEqual("9.8.7", sbom["metadata"]["component"]["version"])
        self.assertNotIn("timestamp", sbom["metadata"])

    def test_release_build_rejects_symlinked_output_directory(self) -> None:
        repo = self._create_release_fixture_repository()
        snapshot = build_release.load_snapshot(repo, "HEAD")
        real_output = self.work_dir / "real-output"
        real_output.mkdir()
        linked_output = self.work_dir / "linked-output"
        linked_output.symlink_to(real_output, target_is_directory=True)
        with self.assertRaisesRegex(build_release.ReleaseError, "must not contain symlinks"):
            build_release.build_release(repo, snapshot, linked_output)

    def test_release_workflow_separates_read_only_build_from_explicit_publication(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:", text)
        self.assertNotRegex(text, re.compile(r"^  push:", re.MULTILINE))
        self.assertRegex(text, re.compile(r"^permissions: \{\}$", re.MULTILINE))
        self.assertIn("  build-candidate:", text)
        self.assertIn("      contents: read", text)
        self.assertIn("  publish:\n    if: ${{ inputs.publish }}", text)
        self.assertIn("    environment: release", text)
        self.assertIn("      attestations: write", text)
        self.assertIn("      contents: write", text)
        self.assertIn("      id-token: write", text)
        self.assertEqual(
            2,
            text.count("uses: actions/attest@a1948c3f048ba23858d222213b7c278aabede763 # v4.1.1"),
        )
        self.assertRegex(text, r"uses: actions/checkout@[0-9a-f]{40} # v7\.0\.0")
        self.assertRegex(text, r"uses: actions/upload-artifact@[0-9a-f]{40} # v7\.0\.1")
        self.assertRegex(text, r"uses: actions/download-artifact@[0-9a-f]{40} # v8\.0\.1")
        self.assertIn("dist/release-manifest.json", text)
        self.assertIn("dist/SHA256SUMS", text)
        self.assertIn("sbom-path: dist/genai-repo-auditor-${{ inputs.release_ref }}.cdx.json", text)
        self.assertIn('test "$(git cat-file -t "$RELEASE_REF")" = "tag"', text)
        self.assertIn("gh release create", text)
        self.assertIn("--verify-tag", text)
        self.assertNotIn("git tag -a", text)
        self.assertNotIn("git push", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

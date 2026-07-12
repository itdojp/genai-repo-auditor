from __future__ import annotations

import contextlib
import io
import re
import shutil
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import validate_python_distribution as validator
from tests.test_workflow_hardening import job_block, job_permissions, workflow_triggers


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-pypi.yml"
DOC = REPO_ROOT / "docs" / "PYPI_DISTRIBUTION.md"
BUILD_REQUIREMENTS_IN = REPO_ROOT / ".github" / "requirements" / "publish-build.in"
BUILD_REQUIREMENTS_LOCK = REPO_ROOT / ".github" / "requirements" / "publish-build.txt"
PROJECT, CURRENT_VERSION = validator._project_config(REPO_ROOT)
REQUIRES_PYTHON = PROJECT["requires-python"]


def metadata(version: str = CURRENT_VERSION) -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        "Name: genai-repo-auditor\n"
        f"Version: {version}\n"
        f"Requires-Python: {REQUIRES_PYTHON}\n"
        "License-Expression: Apache-2.0\n"
        "Description-Content-Type: text/markdown\n"
        "Project-URL: Homepage, https://example.invalid/home\n"
        "Project-URL: Repository, https://example.invalid/repo\n"
        "Project-URL: Issues, https://example.invalid/issues\n"
        "Project-URL: Documentation, https://example.invalid/docs\n"
        "Project-URL: Changelog, https://example.invalid/changelog\n"
        "\n# Fixture\n"
    ).encode()


class PythonDistributionValidatorTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.parent = parent
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))
        self.dist = self.work / "dist"
        self.dist.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.parent.rmdir()

    def _entry_points(self) -> bytes:
        project, _version = validator._project_config(REPO_ROOT)
        lines = ["[console_scripts]"]
        lines.extend(f"{name} = {target}" for name, target in sorted(project["scripts"].items()))
        return ("\n".join(lines) + "\n").encode()

    def _wheel_files(self) -> dict[str, bytes]:
        prefix = f"genai_repo_auditor-{CURRENT_VERSION}.data/data/share/genai-repo-auditor/"
        files = {prefix + name: b"fixture\n" for name in validator._runtime_resources(REPO_ROOT)}
        files.update(
            {
                "genai_repo_auditor/__init__.py": b"",
                f"genai_repo_auditor-{CURRENT_VERSION}.dist-info/METADATA": metadata(),
                f"genai_repo_auditor-{CURRENT_VERSION}.dist-info/entry_points.txt": self._entry_points(),
            }
        )
        return files

    def _sdist_files(self) -> dict[str, bytes]:
        root = f"genai_repo_auditor-{CURRENT_VERSION}/"
        required = {
            "LICENSE",
            "MANIFEST.in",
            "NOTICE",
            "README.md",
            "VERSION",
            "pyproject.toml",
            "src/genai_repo_auditor/__init__.py",
            *validator._runtime_resources(REPO_ROOT),
        }
        files = {root + name: b"fixture\n" for name in required}
        files[root + "PKG-INFO"] = metadata()
        return files

    def _write_wheel(self, files: dict[str, bytes] | None = None) -> Path:
        path = self.dist / f"genai_repo_auditor-{CURRENT_VERSION}-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            for name, body in (files or self._wheel_files()).items():
                archive.writestr(name, body)
        return path

    def _write_sdist(self, files: dict[str, bytes] | None = None) -> Path:
        path = self.dist / f"genai_repo_auditor-{CURRENT_VERSION}.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, body in (files or self._sdist_files()).items():
                info = tarfile.TarInfo(name)
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        return path

    def test_validates_complete_wheel_and_sdist(self) -> None:
        wheel = self._write_wheel()
        sdist = self._write_sdist()
        self.assertEqual((wheel, sdist), validator.validate_dist_dir(self.dist, REPO_ROOT))

    def test_rejects_missing_runtime_resource(self) -> None:
        files = self._wheel_files()
        missing = next(name for name in files if name.endswith("/templates/workflows/recon-only.json"))
        del files[missing]
        self._write_wheel(files)
        self._write_sdist()
        with self.assertRaisesRegex(validator.DistributionValidationError, "missing runtime resources"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_private_sdist_root(self) -> None:
        files = self._sdist_files()
        files[f"genai_repo_auditor-{CURRENT_VERSION}/runs/private/reports/output.json"] = b"{}"
        self._write_wheel()
        self._write_sdist(files)
        with self.assertRaisesRegex(validator.DistributionValidationError, "private/local artifact paths"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_private_wheel_path_outside_resource_root(self) -> None:
        files = self._wheel_files()
        files["payload/data/runs/private/output.json"] = b"{}"
        self._write_wheel(files)
        self._write_sdist()
        with self.assertRaisesRegex(validator.DistributionValidationError, "private/local artifact paths"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_metadata_version_mismatch(self) -> None:
        files = self._wheel_files()
        files[f"genai_repo_auditor-{CURRENT_VERSION}.dist-info/METADATA"] = metadata("9.9.9")
        self._write_wheel(files)
        self._write_sdist()
        with self.assertRaisesRegex(validator.DistributionValidationError, "does not match VERSION"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_entry_points_from_an_additional_dist_info_tree(self) -> None:
        files = self._wheel_files()
        files["unexpected-1.0.dist-info/entry_points.txt"] = self._entry_points()
        self._write_wheel(files)
        self._write_sdist()
        with self.assertRaisesRegex(validator.DistributionValidationError, "exactly one entry_points"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_console_script_target_mismatch(self) -> None:
        files = self._wheel_files()
        entry_name = next(name for name in files if name.endswith(".dist-info/entry_points.txt"))
        files[entry_name] = files[entry_name].replace(
            b"genai_repo_auditor.cli:gra_audit",
            b"genai_repo_auditor.cli:gra_run",
            1,
        )
        self._write_wheel(files)
        self._write_sdist()
        with self.assertRaisesRegex(validator.DistributionValidationError, "console scripts"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_zip_traversal(self) -> None:
        self._write_sdist()
        path = self.dist / f"genai_repo_auditor-{CURRENT_VERSION}-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../outside", b"unsafe")
        with self.assertRaisesRegex(validator.DistributionValidationError, "not safely relative"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_wheel_symlink(self) -> None:
        self._write_sdist()
        path = self.dist / f"genai_repo_auditor-{CURRENT_VERSION}-py3-none-any.whl"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("genai_repo_auditor/link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "../outside")
        with self.assertRaisesRegex(validator.DistributionValidationError, "must not be a symlink"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_sdist_symlink(self) -> None:
        self._write_wheel()
        path = self.dist / f"genai_repo_auditor-{CURRENT_VERSION}.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            link = tarfile.TarInfo(f"genai_repo_auditor-{CURRENT_VERSION}/link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../outside"
            archive.addfile(link)
        with self.assertRaisesRegex(validator.DistributionValidationError, "regular file"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_cli_rejects_symlinked_distribution_directory(self) -> None:
        self._write_wheel()
        self._write_sdist()
        symlink = self.work / "dist-link"
        symlink.symlink_to(self.dist, target_is_directory=True)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = validator.main(["--dist-dir", str(symlink)])
        self.assertEqual(1, result)
        self.assertIn("must not contain symlinks", stderr.getvalue())

    def test_rejects_symlinked_distribution_artifact(self) -> None:
        wheel = self._write_wheel()
        self._write_sdist()
        real_wheel = self.work / "real.whl"
        wheel.replace(real_wheel)
        wheel.symlink_to(real_wheel)
        with self.assertRaisesRegex(validator.DistributionValidationError, "unexpected"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)

    def test_rejects_unexpected_directory_in_distribution_directory(self) -> None:
        self._write_wheel()
        self._write_sdist()
        (self.dist / "extra").mkdir()
        with self.assertRaisesRegex(validator.DistributionValidationError, "unexpected: extra"):
            validator.validate_dist_dir(self.dist, REPO_ROOT)


class PyPIWorkflowAndDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")
        cls.build = job_block(cls.workflow, "build-candidate")
        cls.testpypi = job_block(cls.workflow, "publish-testpypi")
        cls.pypi = job_block(cls.workflow, "publish-pypi")

    def test_workflow_is_manual_tag_bound_and_oidc_only(self) -> None:
        self.assertEqual({"workflow_dispatch"}, workflow_triggers(self.workflow))
        self.assertIn("permissions: {}", self.workflow)
        self.assertEqual({"contents": "read"}, job_permissions(self.workflow, "build-candidate"))
        expected_publish_permissions = {
            "actions": "read",
            "contents": "read",
            "id-token": "write",
        }
        self.assertEqual(expected_publish_permissions, job_permissions(self.workflow, "publish-testpypi"))
        self.assertEqual(expected_publish_permissions, job_permissions(self.workflow, "publish-pypi"))
        self.assertIn('test "$RELEASE_REF" = "v$version"', self.build)
        self.assertIn('test "$(git cat-file -t "$RELEASE_REF")" = "tag"', self.build)
        self.assertIn("git merge-base --is-ancestor HEAD origin/main", self.build)
        self.assertIn("gh release download", self.build)
        self.assertNotIn("git tag ", self.workflow)
        self.assertNotIn("git push", self.workflow)

    def test_workflow_builds_validates_and_smokes_both_artifacts(self) -> None:
        required = [
            "--require-hashes",
            "-r .github/requirements/publish-build.txt",
            "--no-cache-dir",
            "python -m build --no-isolation --outdir pypi-candidate/packages",
            "python -m twine check --strict pypi-candidate/packages/*",
            "python scripts/validate_python_distribution.py",
            "for artifact in pypi-candidate/packages/*.whl pypi-candidate/packages/*.tar.gz",
            '--find-links "$RUNNER_TEMP/pypi-build-wheelhouse"',
            "--no-index --no-build-isolation --no-deps",
            "gra-workflow-profile",
            "gra-efficacy-benchmark",
            "gra-doctor",
        ]
        missing = [term for term in required if term not in self.build]
        self.assertEqual([], missing)
        self.assertNotIn("cache: pip", self.build)

    def test_build_tool_lock_has_exact_direct_pins_and_hashes_for_every_requirement(self) -> None:
        self.assertEqual(
            ["build==1.5.1", "setuptools==83.0.0", "twine==6.2.0", "wheel==0.47.0"],
            BUILD_REQUIREMENTS_IN.read_text(encoding="utf-8").splitlines(),
        )
        lock = BUILD_REQUIREMENTS_LOCK.read_text(encoding="utf-8")
        self.assertNotIn("WARNING", lock)
        self.assertNotIn("--index-url", lock)
        for requirement in re.findall(r"(?m)^([a-zA-Z0-9_.-]+==[^ \\]+) \\\n", lock):
            block = lock.split(requirement + " \\\n", 1)[1].split("\n#", 1)[0]
            self.assertIn("--hash=sha256:", block, requirement)
        for direct in BUILD_REQUIREMENTS_IN.read_text(encoding="utf-8").splitlines():
            self.assertIn(direct + " \\\n", lock)

    def test_production_requires_exact_verified_github_release_assets(self) -> None:
        required = [
            "python scripts/build_release.py --verify",
            'actual = {path.name for path in release_dir.iterdir()}',
            "set(checksums) != expected_primary",
            'item.get("sha256") != checksums[item["name"]]',
            'manifest.get("tag") != os.environ["RELEASE_REF"]',
            'manifest.get("source_commit") != os.environ["RELEASE_COMMIT"]',
            "GITHUB_RELEASE_MANIFEST.json",
            "GITHUB_RELEASE_SHA256SUMS",
        ]
        self.assertEqual([], [term for term in required if term not in self.build])
        self.assertIn('manifest.get("tag") != os.environ["RELEASE_REF"]', self.pypi)
        self.assertIn('manifest.get("source_commit") != os.environ["GITHUB_SHA"]', self.pypi)
        self.assertIn('gh release download "$RELEASE_REF" --dir "$live_release"', self.pypi)
        self.assertIn('cmp "$live_release/release-manifest.json"', self.pypi)
        self.assertIn('cmp "$live_release/SHA256SUMS"', self.pypi)
        self.assertIn("retention-days: 7", self.build)

    def test_publish_jobs_use_fixed_environments_and_pinned_actions(self) -> None:
        self.assertIn("    environment: testpypi", self.testpypi)
        self.assertIn("    environment: pypi", self.pypi)
        self.assertEqual(
            2,
            self.workflow.count(
                "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0"
            ),
        )
        for action in (
            "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0",
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6.3.0",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
        ):
            self.assertIn(action, self.workflow)
        forbidden = ["PYPI_API_TOKEN", "api-token:", "password:", "skip-existing"]
        self.assertEqual([], [term for term in forbidden if term in self.workflow])

    def test_publish_jobs_fail_before_oidc_without_environment_marker(self) -> None:
        for block, destination in ((self.testpypi, "testpypi"), (self.pypi, "pypi")):
            marker = "PYPI_TRUSTED_PUBLISHING_APPROVED"
            self.assertIn(f'run: test "$APPROVAL" = "{destination}"', block)
            self.assertLess(block.index(marker), block.index("actions/download-artifact@"))
            self.assertLess(block.index(marker), block.index("pypa/gh-action-pypi-publish@"))
            required_api_controls = [
                f'"repos/$GITHUB_REPOSITORY/environments/$ENVIRONMENT_NAME"',
                "required_reviewers",
                "prevent_self_review",
                "custom_branch_policies",
                'entries[0].get("name") != "v*"',
            ]
            self.assertEqual([], [term for term in required_api_controls if term not in block])

    def test_docs_record_readiness_threats_and_human_external_steps(self) -> None:
        required = [
            "availability and ownership",
            "unknown",
            "Pending publishers do not reserve",
            "TestPyPI first",
            "Threat model",
            "Human-controlled external setup",
            "workflow: `publish-pypi.yml`",
            "environment: `testpypi`",
            "environment `pypi`",
            "PYPI_TRUSTED_PUBLISHING_APPROVED",
            "repository or organization scope",
            "read-only GitHub API",
            "self-review prevention",
            "`v*` tag pattern",
            "hash-locked",
            "GitHub Release asset set",
            "No `PYPI_API_TOKEN`",
            "Do not add an unverified PyPI URL",
            "does not replace",
        ]
        missing = [term for term in required if term.lower() not in self.doc.lower()]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)

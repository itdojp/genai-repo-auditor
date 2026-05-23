from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
sys.path.insert(0, str(REPO_ROOT / "lib"))
from provenance_posture import append_provenance_posture_targets, write_provenance_posture_artifacts  # noqa: E402


class ProvenancePostureTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def copy_run(self) -> Path:
        run_dir = self.work_dir / "run"
        shutil.copytree(FIXTURES / "minimal-run", run_dir)
        (run_dir / "repo").mkdir()
        return run_dir

    def write_workflow(self, run_dir: Path, name: str, text: str) -> Path:
        workflows = run_dir / "repo" / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        path = workflows / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_no_release_workflows_are_reported_not_applicable(self) -> None:
        run_dir = self.copy_run()
        self.write_workflow(
            run_dir,
            "ci.yml",
            "name: ci\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python -m unittest\n",
        )

        data = write_provenance_posture_artifacts(run_dir)
        self.assertEqual("not_applicable", data["status"])
        self.assertTrue((run_dir / "reports" / "PROVENANCE_POSTURE.md").exists())
        self.assertEqual([], append_provenance_posture_targets(run_dir))

    def test_release_workflow_without_attestation_gets_posture_target(self) -> None:
        run_dir = self.copy_run()
        self.write_workflow(
            run_dir,
            "release.yml",
            "name: release\n"
            "on:\n"
            "  release:\n"
            "    types: [published]\n"
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: make release && tar czf dist/app.tar.gz dist/app\n"
            "      - uses: softprops/action-gh-release@v2\n"
            "        with:\n"
            "          files: dist/app.tar.gz\n",
        )

        data = write_provenance_posture_artifacts(run_dir)
        self.assertEqual("needs_review", data["status"])
        workflow = data["workflows"][0]
        self.assertEqual(["release", "binary_or_archive"], workflow["categories"])
        self.assertFalse(workflow["has_attestation"])
        self.assertIn("id-token: expected write, observed missing", workflow["permission_gaps"])
        self.assertIn({"name": "Supply Chain Posture", "id": "SC-ARTIFACT-ATTESTATION", "label": "Artifact Attestation"}, workflow["taxonomies"])

        added = append_provenance_posture_targets(run_dir)
        self.assertEqual(["TGT-PROVENANCE-001"], [target["id"] for target in added])
        self.assertEqual("repo/.github/workflows/release.yml", added[0]["scope"])
        cp = subprocess.run(
            [str(REPO_ROOT / "bin" / "gra-validate-report"), "--run", str(run_dir)],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")

    def test_container_workflow_with_attestation_and_permissions_is_recognized(self) -> None:
        run_dir = self.copy_run()
        self.write_workflow(
            run_dir,
            "container.yml",
            "name: container\n"
            "on: [push]\n"
            "permissions:\n"
            "  id-token: write\n"
            "  contents: read\n"
            "  attestations: write\n"
            "  packages: write\n"
            "jobs:\n"
            "  image:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - uses: docker/build-push-action@v6\n"
            "        id: build\n"
            "        with:\n"
            "          push: true\n"
            "      - uses: actions/attest@v4\n"
            "        with:\n"
            "          subject-name: ghcr.io/example/demo\n"
            "          subject-digest: ${{ steps.build.outputs.digest }}\n"
            "          push-to-registry: true\n",
        )

        data = write_provenance_posture_artifacts(run_dir)
        self.assertEqual("attested", data["status"])
        workflow = data["workflows"][0]
        self.assertIn("container", workflow["categories"])
        self.assertTrue(workflow["has_attestation"])
        self.assertEqual([], workflow["permission_gaps"])
        self.assertEqual([], append_provenance_posture_targets(run_dir))

    def test_sbom_attestation_is_detected(self) -> None:
        run_dir = self.copy_run()
        self.write_workflow(
            run_dir,
            "sbom.yml",
            "name: release-sbom\n"
            "on: [push]\n"
            "permissions:\n"
            "  id-token: write\n"
            "  contents: read\n"
            "  attestations: write\n"
            "jobs:\n"
            "  release:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: syft packages dir:. -o spdx-json=sbom.spdx.json\n"
            "      - run: zip dist/app.zip app\n"
            "      - uses: actions/attest@v4\n"
            "        with:\n"
            "          subject-path: dist/app.zip\n"
            "          sbom-path: sbom.spdx.json\n",
        )

        data = write_provenance_posture_artifacts(run_dir)
        workflow = data["workflows"][0]
        self.assertTrue(workflow["has_sbom_generation"])
        self.assertTrue(workflow["has_sbom_attestation"])
        self.assertTrue(workflow["has_attestation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

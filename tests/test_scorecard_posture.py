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
from scorecard_posture import append_scorecard_posture_targets, write_scorecard_posture_artifacts  # noqa: E402


class ScorecardPostureTests(unittest.TestCase):
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
        return run_dir

    def test_scorecard_posture_redacts_tokens_and_appends_targets(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "scorecard-fixture.json"
        shutil.copy2(FIXTURES / "scorecard" / "scorecard.json", raw_path)

        data = write_scorecard_posture_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/scorecard-fixture.json",
        )

        self.assertEqual("needs_review", data["status"])
        self.assertEqual(4.2, data["overall_score"])
        self.assertEqual(0, data["findings_created"])
        checks_by_name = {check["name"]: check for check in data["checks"]}
        self.assertEqual(
            {"Dangerous-Workflow", "Token-Permissions", "Pinned-Dependencies", "SAST", "Security-Policy"},
            set(checks_by_name),
        )
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", serialized)
        self.assertNotIn("sk_live_123456789abcdef", serialized)
        self.assertNotIn("-----BEGIN PRIVATE KEY-----abc-----END PRIVATE KEY-----", serialized)
        self.assertIn("ghp_", serialized)
        self.assertIn("<REDACTED:private-key>", serialized)
        self.assertTrue(checks_by_name["Dangerous-Workflow"]["target_recommended"])
        self.assertTrue(checks_by_name["Token-Permissions"]["target_recommended"])
        self.assertFalse(checks_by_name["Pinned-Dependencies"]["target_recommended"])
        self.assertTrue(checks_by_name["SAST"]["target_recommended"])
        self.assertFalse(checks_by_name["Security-Policy"]["target_recommended"])

        markdown = (run_dir / "reports" / "supply-chain-posture.md").read_text(encoding="utf-8")
        self.assertIn("OpenSSF Scorecard supply-chain posture", markdown)
        self.assertIn("Dangerous-Workflow", markdown)
        self.assertIn("Documentation/remediation link", markdown)
        self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz123456", markdown)
        self.assertNotIn("sk_live_123456789abcdef", markdown)
        self.assertNotIn("-----BEGIN PRIVATE KEY-----abc-----END PRIVATE KEY-----", markdown)
        self.assertIn("&lt;REDACTED:private-key&gt;", markdown)

        added = append_scorecard_posture_targets(run_dir)
        self.assertEqual(3, len(added))
        self.assertEqual(["TGT-SCORECARD-001", "TGT-SCORECARD-002", "TGT-SCORECARD-003"], [target["id"] for target in added])
        self.assertEqual({"critical", "high", "medium"}, {target["risk"] for target in added})
        self.assertEqual([], append_scorecard_posture_targets(run_dir))
        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))["targets"]
        scopes = {target["scope"] for target in targets}
        self.assertIn("OpenSSF Scorecard: Dangerous-Workflow", scopes)
        self.assertIn("OpenSSF Scorecard: Token-Permissions", scopes)
        self.assertIn("OpenSSF Scorecard: SAST", scopes)

    def test_out_of_range_score_is_treated_as_unknown(self) -> None:
        run_dir = self.copy_run()
        raw_dir = run_dir / "reports" / "scanner-results"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "scorecard-out-of-range.json"
        raw_path.write_text(
            json.dumps(
                {
                    "score": 100,
                    "checks": [
                        {
                            "name": "Dangerous-Workflow",
                            "score": 100,
                            "reason": "out-of-range fixture",
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        data = write_scorecard_posture_artifacts(
            run_dir=run_dir,
            raw_path=raw_path,
            raw_result_ref="reports/scanner-results/scorecard-out-of-range.json",
        )

        self.assertIsNone(data["overall_score"])
        self.assertIsNone(data["checks"][0]["score"])
        self.assertEqual("unknown", data["checks"][0]["score_display"])
        self.assertEqual("informational", data["checks"][0]["risk"])
        self.assertFalse(data["checks"][0]["target_recommended"])

    def test_gra_ingest_scorecard_writes_posture_targets_and_dashboard(self) -> None:
        run_dir = self.copy_run()
        scorecard_path = FIXTURES / "scorecard" / "scorecard.json"

        ingest = subprocess.run(
            [
                sys.executable,
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "scorecard",
                "--file",
                scorecard_path,
                "--format",
                "json",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, ingest.returncode, f"stdout:\n{ingest.stdout}\nstderr:\n{ingest.stderr}")
        self.assertIn("supply-chain-posture.json", ingest.stdout)
        self.assertIn("scorecard-posture target", ingest.stdout)
        self.assertTrue((run_dir / "reports" / "supply-chain-posture.json").exists())
        self.assertTrue((run_dir / "reports" / "supply-chain-posture.md").exists())

        scanner_index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        self.assertEqual("scorecard", scanner_index["results"][0]["tool"])
        posture = json.loads((run_dir / "reports" / "supply-chain-posture.json").read_text(encoding="utf-8"))
        self.assertTrue(posture["source"]["raw_result_ref"].startswith("reports/scanner-results/"))
        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))["targets"]
        self.assertTrue(any(str(target.get("id", "")).startswith("TGT-SCORECARD-") for target in targets))

        validation = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, validation.returncode, f"stdout:\n{validation.stdout}\nstderr:\n{validation.stderr}")
        self.assertIn("Scanner index: validated", validation.stdout)

        dashboard_path = run_dir / "reports" / "dashboard.html"
        dashboard = subprocess.run(
            [sys.executable, REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir, "--out", dashboard_path],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, dashboard.returncode, f"stdout:\n{dashboard.stdout}\nstderr:\n{dashboard.stderr}")
        dashboard_html = dashboard_path.read_text(encoding="utf-8")
        self.assertIn("Supply-chain posture", dashboard_html)
        self.assertIn("Dangerous-Workflow", dashboard_html)
        self.assertIn("OpenSSF Scorecard", dashboard_html)


if __name__ == "__main__":
    unittest.main(verbosity=2)

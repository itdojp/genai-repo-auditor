from __future__ import annotations

import json
import contextlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "minimal-run"


class NoveltyLedgerTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def copy_run(self, name: str) -> Path:
        run_dir = self.work_dir / name
        shutil.copytree(FIXTURE, run_dir)
        return run_dir

    def run_cmd(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *(str(arg) for arg in args)],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

    def read_ledger(self, run_dir: Path) -> dict:
        return json.loads((run_dir / "reports" / "known-findings.json").read_text(encoding="utf-8"))

    def write_findings(self, run_dir: Path, data: dict) -> None:
        (run_dir / "reports" / "findings.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def test_rerunning_same_fixture_marks_duplicate_and_suppresses_issue_plan(self) -> None:
        run_dir = self.copy_run("run")
        first = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", run_dir)
        self.assertEqual(first.returncode, 0, first.stderr)
        first_ledger = self.read_ledger(run_dir)
        self.assertEqual("new", first_ledger["findings"][0]["novelty_status"])
        self.assertTrue(first_ledger["findings"][0]["issue_recommended"])

        second = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", run_dir)
        self.assertEqual(second.returncode, 0, second.stderr)
        second_ledger = self.read_ledger(run_dir)
        self.assertEqual("duplicate", second_ledger["findings"][0]["novelty_status"])
        self.assertFalse(second_ledger["findings"][0]["issue_recommended"])

        plan = self.run_cmd(REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        issue_plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        self.assertEqual([], issue_plan["selected_findings"])
        issue_ledger = json.loads((run_dir / "reports" / "issue-ledger.json").read_text(encoding="utf-8"))
        self.assertEqual("not-selected", issue_ledger["findings"][0]["publication_status"])
        self.assertEqual(
            "novelty status duplicate suppresses publication",
            issue_ledger["findings"][0]["selection_reason"],
        )

        validate = self.run_cmd(REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir)
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("Known findings novelty ledger: validated", validate.stdout)

        dashboard = self.run_cmd(REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir)
        self.assertEqual(dashboard.returncode, 0, dashboard.stderr)
        dashboard_html = (run_dir / "reports" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("Known findings / novelty", dashboard_html)
        self.assertIn("Duplicate", dashboard_html)

    def test_same_root_cause_with_stronger_evidence_is_better_example(self) -> None:
        prior_run = self.copy_run("prior")
        first = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", prior_run)
        self.assertEqual(first.returncode, 0, first.stderr)
        prior_ledger = prior_run / "reports" / "known-findings.json"

        current_run = self.copy_run("current")
        findings_path = current_run / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        finding = data["findings"][0]
        finding["fingerprint"] = "fedcba9876543210fedcba98"
        finding["evidence"] = finding["evidence"] + " Additional deterministic stack trace and unit-test evidence."
        self.write_findings(current_run, data)

        current = self.run_cmd(
            REPO_ROOT / "bin" / "gra-novelty",
            "--run",
            current_run,
            "--prior-ledger",
            prior_ledger,
        )
        self.assertEqual(current.returncode, 0, current.stderr)
        ledger = self.read_ledger(current_run)
        self.assertEqual("better-example", ledger["findings"][0]["novelty_status"])
        self.assertTrue(ledger["findings"][0]["issue_recommended"])
        self.assertIn("root_cause", ledger["findings"][0]["match"]["reasons"])

    def test_root_cause_only_match_needs_human_review_not_duplicate(self) -> None:
        prior_run = self.copy_run("prior")
        first = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", prior_run)
        self.assertEqual(first.returncode, 0, first.stderr)
        prior_ledger = prior_run / "reports" / "known-findings.json"

        current_run = self.copy_run("current")
        findings_path = current_run / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        finding = data["findings"][0]
        finding["fingerprint"] = "111122223333444455556666"
        finding["affected_locations"] = [{"file": "other.py", "line": 10, "end_line": 10}]
        finding["entry_point"] = "other.entry"
        finding["trust_boundary"] = "different boundary"
        finding["source_to_sink"] = "other input -> other sink"
        self.write_findings(current_run, data)

        current = self.run_cmd(
            REPO_ROOT / "bin" / "gra-novelty",
            "--run",
            current_run,
            "--prior-ledger",
            prior_ledger,
        )
        self.assertEqual(current.returncode, 0, current.stderr)
        ledger = self.read_ledger(current_run)
        self.assertEqual("needs-human-review", ledger["findings"][0]["novelty_status"])
        self.assertTrue(ledger["findings"][0]["issue_recommended"])
        self.assertEqual(["root_cause"], ledger["findings"][0]["match"]["reasons"])

    def test_stale_novelty_fingerprint_does_not_suppress_issue_plan(self) -> None:
        run_dir = self.copy_run("run")
        created = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", run_dir)
        self.assertEqual(created.returncode, 0, created.stderr)
        repeated = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", run_dir)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        ledger = self.read_ledger(run_dir)
        self.assertEqual("duplicate", ledger["findings"][0]["novelty_status"])

        findings_path = run_dir / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        data["findings"][0]["fingerprint"] = "999988887777666655554444"
        self.write_findings(run_dir, data)

        plan = self.run_cmd(REPO_ROOT / "bin" / "gra-issues", "--run", run_dir, "--plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        issue_plan = json.loads((run_dir / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(["SEC-001"], [entry["id"] for entry in issue_plan["selected_findings"]])
        self.assertEqual("stale-ignored", issue_plan["selected_findings"][0]["novelty"]["status"])

    def test_accepted_risk_is_not_republished_unless_evidence_changes(self) -> None:
        accepted_run = self.copy_run("accepted")
        accepted = self.run_cmd(
            REPO_ROOT / "bin" / "gra-novelty",
            "--run",
            accepted_run,
            "--accepted-risk",
            "SEC-001",
            "--accepted-risk-reason",
            "fixture risk accepted locally",
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        accepted_ledger = accepted_run / "reports" / "known-findings.json"

        same_run = self.copy_run("same")
        same = self.run_cmd(
            REPO_ROOT / "bin" / "gra-novelty",
            "--run",
            same_run,
            "--prior-ledger",
            accepted_ledger,
        )
        self.assertEqual(same.returncode, 0, same.stderr)
        same_ledger = self.read_ledger(same_run)
        self.assertEqual("accepted-risk", same_ledger["findings"][0]["novelty_status"])
        self.assertFalse(same_ledger["findings"][0]["issue_recommended"])
        plan = self.run_cmd(REPO_ROOT / "bin" / "gra-issues", "--run", same_run, "--plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        issue_plan = json.loads((same_run / "reports" / "issue-publication-plan.json").read_text(encoding="utf-8"))
        self.assertEqual([], issue_plan["selected_findings"])

        changed_run = self.copy_run("changed")
        data = json.loads((changed_run / "reports" / "findings.json").read_text(encoding="utf-8"))
        data["findings"][0]["impact"] = data["findings"][0]["impact"] + " Impact changed for regression review."
        self.write_findings(changed_run, data)
        changed = self.run_cmd(
            REPO_ROOT / "bin" / "gra-novelty",
            "--run",
            changed_run,
            "--prior-ledger",
            accepted_ledger,
        )
        self.assertEqual(changed.returncode, 0, changed.stderr)
        changed_ledger = self.read_ledger(changed_run)
        self.assertEqual("regression", changed_ledger["findings"][0]["novelty_status"])
        self.assertTrue(changed_ledger["findings"][0]["issue_recommended"])

    def test_ledger_does_not_copy_raw_evidence_root_cause_or_impact(self) -> None:
        run_dir = self.copy_run("run")
        created = self.run_cmd(REPO_ROOT / "bin" / "gra-novelty", "--run", run_dir)
        self.assertEqual(created.returncode, 0, created.stderr)
        ledger_text = (run_dir / "reports" / "known-findings.json").read_text(encoding="utf-8")
        findings_text = (run_dir / "reports" / "findings.json").read_text(encoding="utf-8")
        findings = json.loads(findings_text)["findings"][0]
        self.assertNotIn(findings["evidence"], ledger_text)
        self.assertNotIn(findings["root_cause"], ledger_text)
        self.assertNotIn(findings["impact"], ledger_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

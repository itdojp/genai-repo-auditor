from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOGFOOD_TEMPLATES = REPO_ROOT / "templates" / "dogfood"
DOGFOOD_DOCS = REPO_ROOT / "docs"


class DogfoodTemplateTests(unittest.TestCase):
    maxDiff = None

    def test_json_templates_are_valid_and_placeholder_only(self) -> None:
        for path in sorted(DOGFOOD_TEMPLATES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rendered = json.dumps(data, sort_keys=True)
            forbidden = ["SECRET", "TOKEN", "PRIVATE KEY", "BEGIN RSA", "password="]
            self.assertFalse(
                any(term.lower() in rendered.lower() for term in forbidden),
                f"{path.relative_to(REPO_ROOT)} should not contain secret-like placeholders",
            )

    def test_public_safe_report_template_excludes_private_artifact_bodies(self) -> None:
        text = (DOGFOOD_TEMPLATES / "public-safe-report-template.md").read_text(encoding="utf-8").lower()
        required_cautions = [
            "private findings",
            "raw evidence",
            "attack-chain details",
            "proof payloads",
            "scanner raw",
            "codex transcripts",
            "remediation diffs",
        ]
        missing = [term for term in required_cautions if term not in text]
        self.assertEqual([], missing)


    def test_dry_run_issue_record_does_not_claim_publication_plan(self) -> None:
        record = json.loads((DOGFOOD_TEMPLATES / "run-record.example.json").read_text(encoding="utf-8"))
        commands = {entry["name"]: entry for entry in record["commands"]}
        dry_run_refs = set(commands["gra-issues --dry-run"]["artifact_refs"])
        plan_refs = set(commands["gra-issues --plan"]["artifact_refs"])
        self.assertNotIn("reports/issue-publication-plan.json", dry_run_refs)
        self.assertIn("reports/issue-publication-plan.json", plan_refs)

    def test_campaign_ledger_records_publication_and_retention_status(self) -> None:
        ledger = json.loads((DOGFOOD_TEMPLATES / "campaign-ledger.example.json").read_text(encoding="utf-8"))
        self.assertIn("runs", ledger)
        self.assertGreaterEqual(len(ledger["runs"]), 2)
        for run in ledger["runs"]:
            self.assertIn(run["publication_status"], {"private", "sanitized-public", "not-approved"})
            self.assertIn(run["retention_decision"], {"delete-after-review", "retain-local", "secure-archive"})
            self.assertIn("artifact_refs", run)
            self.assertNotIn("artifact_contents", run)

    def test_reporting_guide_keeps_internal_summaries_outside_git(self) -> None:
        reporting = (DOGFOOD_DOCS / "DOGFOOD_REPORTING.md").read_text(encoding="utf-8")
        self.assertIn(".codex-local/dogfood/", reporting)
        self.assertIn("outside Git by", reporting)
        self.assertNotIn("docs/dogfood/*_SUMMARY.md", reporting)


if __name__ == "__main__":
    unittest.main(verbosity=2)

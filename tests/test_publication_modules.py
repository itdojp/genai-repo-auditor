from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from publication.planning import (  # noqa: E402
    build_publication_plan,
    plan_entry_key,
    verify_plan_against_findings,
)
from publication.policy import (  # noqa: E402
    advanced_validation_errors,
    finding_selection_decision,
    finding_selection_reason,
    matching_novelty_entry,
    normalize_labels,
    novelty_summary,
    plan_visibility,
    select_findings,
    should_include,
)
from publication.rendering import render_body, sha256_text, stable_fingerprint  # noqa: E402
from report_safety import ReportSafetyError  # noqa: E402


def advanced_artifacts() -> dict[str, object]:
    return {
        "chains_present": True,
        "chains": [{"id": "CHAIN-1", "findings": ["SEC-001"]}],
        "chain_errors": [],
        "proofs_present": True,
        "proofs": [{"id": "PROOF-1", "finding_id": "SEC-001"}],
        "proof_errors": [],
        "validations_present": True,
        "validations": [
            {
                "id": "VAL-1",
                "subject_type": "finding",
                "subject_id": "SEC-001",
                "decision": "confirm",
                "recommended_severity": "High",
                "recommended_confidence": "High",
                "component": "auth",
                "owner_hint": "security-team",
                "owner_source": "CODEOWNERS",
            }
        ],
        "validation_errors": [],
        "remediation_present": True,
        "remediation_candidates": [
            {
                "id": "PATCH-1",
                "finding_id": "SEC-001",
                "status": "draft",
                "patch_file": "reports/remediation/SEC-001.patch",
                "requires_human_review": True,
            }
        ],
        "remediation_errors": [],
        "patch_validations_present": True,
        "patch_validations": [
            {
                "finding_id": "SEC-001",
                "patch_id": "PATCH-1",
                "report_file": "reports/remediation/SEC-001/patch-validation.json",
                "final_status": "needs-human-review",
                "patch_applied": True,
                "diff_scope_status": "changed",
                "sandbox_profile": "offline",
            }
        ],
        "patch_validation_errors": [],
    }


class PublicationModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.drafts = self.run_dir / "reports" / "issue-drafts"
        self.drafts.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.run_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def finding(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "id": "SEC-001",
            "title": "Authorization bypass",
            "issue_title": "[Security][High] Authorization bypass",
            "severity": "High",
            "confidence": "High",
            "status": "Confirmed",
            "category": "Access Control",
            "issue_recommended": True,
            "fingerprint": "fp-sec-001",
            "public_disclosure_risk": "Reviewed",
            "chain_membership": ["CHAIN-1"],
            "affected_locations": [{"file": "src/app.py", "line": 10}],
            "entry_point": "POST /admin",
            "trust_boundary": "anonymous-to-admin",
            "call_path": "router -> handler",
            "root_cause": "Missing authorization check.",
            "evidence": "Safe summarized evidence.",
            "impact": "Unauthorized state change.",
            "minimal_remediation": "Authorize the handler.",
            "regression_test_idea": "Unauthenticated request is rejected.",
        }
        data.update(overrides)
        return data

    def write_draft(self, text: str = "# Draft\n\nReviewed remediation summary.\n") -> str:
        path = self.drafts / "SEC-001.md"
        path.write_text(text, encoding="utf-8")
        return "reports/issue-drafts/SEC-001.md"

    def test_policy_selection_labels_visibility_and_reasons_are_pure(self) -> None:
        statuses = {"Confirmed", "Probable"}

        self.assertTrue(should_include(self.finding(), "High", statuses))
        self.assertFalse(should_include(self.finding(severity="Medium"), "High", statuses))
        self.assertFalse(should_include(self.finding(status="Potential"), "High", statuses))
        self.assertFalse(should_include(self.finding(issue_recommended=False), "High", statuses))
        self.assertEqual("severity below High", finding_selection_reason(self.finding(severity="Medium"), "High", statuses))
        self.assertEqual(
            "status Potential not selected",
            finding_selection_reason(self.finding(status="Potential"), "High", statuses),
        )
        self.assertEqual("issue_recommended=false", finding_selection_reason(self.finding(issue_recommended=False), "High", statuses))

        labels = normalize_labels(self.finding(labels=["custom-label", "security", "  "]))
        self.assertEqual(
            ["security", "genai-audit", "severity-high", "status-confirmed", "category-access-control", "custom-label"],
            labels,
        )
        self.assertEqual("PRIVATE", plan_visibility({"visibility": "private"}, {}))
        self.assertEqual("UNKNOWN", plan_visibility({}, {}))

    def test_plan_binds_issue_body_content_without_copying_body_into_plan(self) -> None:
        issue_body_file = self.write_draft()
        finding = self.finding(issue_body_file=issue_body_file)

        plan, bodies = build_publication_plan(
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            visibility="PRIVATE",
            findings=[finding],
            run_dir=self.run_dir,
            generated_at="2026-07-10T00:00:00Z",
            advanced_artifacts=advanced_artifacts(),
            novelty_entries={"unrelated": {"finding_id": "unrelated"}},
        )

        entry = plan["selected_findings"][0]
        body = bodies[plan_entry_key(entry)]
        self.assertIn("genai-repo-auditor:fingerprint=fp-sec-001", body)
        self.assertEqual(sha256_text(body), entry["issue_body_sha256"])
        self.assertEqual("reports/issue-drafts/SEC-001.md", entry["issue_body_file"])
        self.assertNotIn("Reviewed remediation summary", str(entry))
        self.assertEqual({"component": "auth", "owner_hint": "security-team", "owner_source": "CODEOWNERS"}, entry["owner_routing"])
        self.assertEqual(
            ["SEC-001: remediation candidate PATCH-1 patch validation status is needs-human-review"],
            advanced_validation_errors([entry]),
        )

        selected, verified_bodies, errors = verify_plan_against_findings(
            plan=plan,
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            current_findings=[finding],
            run_dir=self.run_dir,
            advanced_artifacts=advanced_artifacts(),
            novelty_entries={"unrelated": {"finding_id": "unrelated"}},
        )
        self.assertEqual([], errors)
        self.assertEqual([entry], selected)
        self.assertEqual(body, verified_bodies[plan_entry_key(entry)])

        (self.drafts / "SEC-001.md").write_text("# Draft\n\nChanged reviewed summary.\n", encoding="utf-8")
        _selected, _bodies, drift_errors = verify_plan_against_findings(
            plan=plan,
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            current_findings=[finding],
            run_dir=self.run_dir,
            advanced_artifacts=advanced_artifacts(),
            novelty_entries={"unrelated": {"finding_id": "unrelated"}},
        )
        self.assertIn("SEC-001: issue_body_sha256 changed after plan creation", drift_errors)

    def test_planning_accepts_explicit_empty_pure_inputs_without_artifact_reads(self) -> None:
        missing_run_dir = self.run_dir / "missing-run-dir"
        plan, bodies = build_publication_plan(
            repo="owner/repo",
            run_id="run-1",
            commit="abc123",
            visibility="PRIVATE",
            findings=[self.finding(issue_body_file=None)],
            run_dir=missing_run_dir,
            generated_at="2026-07-10T00:00:00Z",
            advanced_artifacts={},
            novelty_entries={},
        )

        entry = plan["selected_findings"][0]
        body = bodies[plan_entry_key(entry)]
        self.assertIn("genai-repo-auditor:fingerprint=fp-sec-001", body)
        self.assertEqual("not-run", entry["novelty"]["status"])
        self.assertIn("High/Critical issue-recommended finding lacks related adversarial validation", entry["advanced_validation"]["warnings"])

    def test_novelty_matching_suppression_requires_current_fingerprint(self) -> None:
        finding = self.finding(fingerprint="fp-current")
        stale = self.finding(fingerprint="fp-stale")
        novelty_entries = {
            "SEC-001": {
                "finding_id": "SEC-001",
                "fingerprint": "fp-current",
                "novelty_status": "duplicate",
                "issue_recommended": False,
                "match": {"previous_fingerprint": "fp-prior", "reasons": ["fingerprint"]},
            }
        }

        self.assertIs(matching_novelty_entry("owner/repo", finding, novelty_entries), novelty_entries["SEC-001"])
        current_summary = novelty_summary("owner/repo", finding, novelty_entries)
        self.assertEqual("duplicate", current_summary["status"])
        self.assertTrue(current_summary["suppresses_publication"])
        self.assertEqual(["fingerprint"], current_summary["match_reasons"])
        self.assertEqual(
            (False, "novelty status duplicate suppresses publication"),
            finding_selection_decision(
                finding,
                "High",
                {"Confirmed", "Probable"},
                repo="owner/repo",
                novelty_entries=novelty_entries,
            ),
        )
        self.assertEqual(
            "novelty status duplicate suppresses publication",
            finding_selection_reason(
                finding,
                "High",
                {"Confirmed", "Probable"},
                repo="owner/repo",
                novelty_entries=novelty_entries,
            ),
        )
        self.assertEqual(
            [],
            select_findings(
                repo="owner/repo",
                findings=[finding],
                min_severity="High",
                statuses={"Confirmed", "Probable"},
                novelty_entries=novelty_entries,
            ),
        )

        self.assertIsNone(matching_novelty_entry("owner/repo", stale, novelty_entries))
        stale_summary = novelty_summary("owner/repo", stale, novelty_entries)
        self.assertEqual("stale-ignored", stale_summary["status"])
        self.assertFalse(stale_summary["suppresses_publication"])

    def test_render_body_rejects_unsafe_issue_body_paths_without_reading_body(self) -> None:
        outside = self.run_dir / "reports" / "issue-drafts" / "unsafe.txt"
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("sensitive issue body text that must not be surfaced\n", encoding="utf-8")
        finding = self.finding(issue_body_file="reports/issue-drafts/unsafe.txt")

        with self.assertRaisesRegex(ReportSafetyError, r"must be a \.md file") as raised:
            render_body("owner/repo", "run-1", "abc123", finding, stable_fingerprint("owner/repo", finding), self.run_dir)
        self.assertNotIn("sensitive issue body text", str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

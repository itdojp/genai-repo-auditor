from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))
from issue_dry_run_summary import build_summary, validate_summary  # noqa: E402


class IssueDryRunSummaryTests(unittest.TestCase):
    def valid_summary(self):
        return build_summary(
            repo="example/demo",
            run_id="run-1",
            commit="0" * 40,
            selection_source="current-findings",
            visibility="PRIVATE",
            visibility_source="run-artifact",
            base_counts={
                "total_candidates": 5,
                "selected": 2,
                "filtered_by_severity_or_status": 1,
                "issue_recommendation_suppressed": 1,
                "novelty_suppressed": 1,
            },
            duplicate_suppressed=1,
            advanced_validation_blocked=0,
            public_visibility_blocked=0,
            would_create=1,
            warnings=2,
        )

    def test_valid_summary_preserves_dry_run_invariants(self) -> None:
        summary = self.valid_summary()
        self.assertEqual([], validate_summary(summary))
        self.assertEqual(0, summary["counts"]["issues_created"])
        self.assertFalse(summary["github_duplicate_search_performed"])
        self.assertFalse(summary["github_visibility_lookup_performed"])
        self.assertFalse(summary["safety"]["github_mutation_performed"])
        self.assertFalse(summary["safety"]["publication_plan_written"])

    def test_validator_rejects_unknown_negative_and_inconsistent_counts(self) -> None:
        unknown = copy.deepcopy(self.valid_summary())
        unknown["unexpected"] = True
        self.assertTrue(validate_summary(unknown))

        negative = copy.deepcopy(self.valid_summary())
        negative["counts"]["would_create"] = -1
        self.assertIn(
            "counts.would_create must be a bounded non-negative integer",
            validate_summary(negative),
        )

        inconsistent = copy.deepcopy(self.valid_summary())
        inconsistent["counts"]["selected"] = 3
        errors = validate_summary(inconsistent)
        self.assertIn("selection counters do not partition total_candidates", errors)
        self.assertIn("publication counters do not partition selected", errors)

        created = copy.deepcopy(self.valid_summary())
        created["counts"]["issues_created"] = 1
        self.assertIn("issues_created must be zero in dry-run mode", validate_summary(created))

        invalid_metadata = copy.deepcopy(self.valid_summary())
        invalid_metadata["visibility_source"] = "github-online"
        invalid_metadata["generated_at"] = "not-a-timestamp"
        metadata_errors = validate_summary(invalid_metadata)
        self.assertIn("visibility_source is unsupported", metadata_errors)
        self.assertIn("generated_at must be an ISO-8601 timestamp", metadata_errors)


if __name__ == "__main__":
    unittest.main()

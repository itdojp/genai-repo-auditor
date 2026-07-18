from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from target_queue import (  # noqa: E402
    BUDGETED_TARGET_SOURCES,
    TargetBudgets,
    TargetQueueError,
    apply_target_queue_policy,
    preserve_target_queue_membership,
    refresh_target_queue_after_semantic_normalization,
    validate_target_queue_artifact,
)
from gralib import target_ids_with_lineage  # noqa: E402


def target(
    target_id: str,
    *,
    priority: int = 50,
    risk: str = "medium",
    sink: str = "database",
    scope: str = "shared authz scope",
) -> dict:
    prefixes = {
        "TGT-AGENT-": "agent_surface",
        "TGT-PROVENANCE-": "provenance",
        "TGT-SCORECARD-": "scorecard",
        "TGT-DEPENDENCY-": "dependency",
        "TGT-SCANNER-": "scanner",
        "TGT-GAPFILL-": "gapfill",
    }
    return {
        "id": target_id,
        "queue_source": next((source for prefix, source in prefixes.items() if target_id.startswith(prefix)), "model_generated"),
        "category": "Authz",
        "title": f"opaque {target_id}",
        "risk": risk,
        "priority": priority,
        "status": "queued",
        "scope": scope,
        "entry_points": ["src/api.py"],
        "trust_boundaries": ["user -> API"],
        "sinks": [sink],
        "attack_class": "Authz",
        "security_invariants": ["tenant isolation"],
        "attacker_model": "authenticated user",
        "review_questions": ["Is authorization enforced?"],
        "candidate_files": ["src/api.py"],
        "recommended_mode": "exec",
        "taxonomies": [{"name": "Test", "id": "AUTHZ-1", "label": "Authorization"}],
    }


def budgets(total: int = 20, source: int = 10) -> TargetBudgets:
    return TargetBudgets(total=total, by_source={name: source for name in BUDGETED_TARGET_SOURCES})


class TargetQueueTests(unittest.TestCase):
    def test_cross_source_overlap_merges_and_retains_lineage(self) -> None:
        items = [target("TGT-001", priority=60), target("TGT-AGENT-001", priority=90, risk="high")]
        active, deferred, summary = apply_target_queue_policy(items, budgets=budgets())
        self.assertEqual([], deferred)
        self.assertEqual(1, len(active))
        self.assertEqual("TGT-AGENT-001", active[0]["id"])
        self.assertEqual("high", active[0]["risk"])
        self.assertEqual(90, active[0]["priority"])
        self.assertEqual(
            [("model_generated", "TGT-001"), ("agent_surface", "TGT-AGENT-001")],
            [(item["source"], item["target_id"]) for item in active[0]["source_lineage"]],
        )
        self.assertEqual(1, summary["merged"])
        self.assertEqual({"active", "merged"}, {item["action"] for item in summary["decisions"]})

    def test_non_overlap_and_repeat_are_deterministic(self) -> None:
        items = [target("TGT-002", sink="filesystem"), target("TGT-001", sink="database")]
        first = apply_target_queue_policy(items, budgets=budgets())
        second = apply_target_queue_policy(copy.deepcopy(items), budgets=budgets())
        self.assertEqual(
            json.dumps(first, sort_keys=True, separators=(",", ":")),
            json.dumps(second, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(2, len(first[0]))

    def test_total_and_source_budgets_defer_with_explicit_high_risk_reason(self) -> None:
        items = [
            target("TGT-AGENT-001", priority=100, risk="critical", sink="one"),
            target("TGT-AGENT-002", priority=99, risk="high", sink="two"),
            target("TGT-002", priority=10, sink="three"),
        ]
        active, deferred, summary = apply_target_queue_policy(items, budgets=budgets(total=2, source=1))
        self.assertEqual(2, len(active))
        self.assertEqual(1, len(deferred))
        self.assertEqual("TGT-AGENT-002", deferred[0]["id"])
        decision = next(item for item in summary["decisions"] if item["target_id"] == "TGT-AGENT-002")
        self.assertEqual("source_budget_exhausted_high_risk", decision["reason"])
        self.assertEqual(1, summary["high_risk_deferred"])

    def test_strict_preserves_first_seen_selection(self) -> None:
        items = [target("TGT-001", priority=1, sink="one"), target("TGT-002", priority=100, risk="critical", sink="two")]
        active, deferred, _ = apply_target_queue_policy(items, budgets=budgets(total=1), policy="strict")
        self.assertEqual(["TGT-001"], [item["id"] for item in active])
        self.assertEqual(["TGT-002"], [item["id"] for item in deferred])

    def test_invalid_configuration_and_input_fail_closed(self) -> None:
        with self.assertRaises(TargetQueueError):
            apply_target_queue_policy([], budgets=budgets(total=0))
        with self.assertRaises(TargetQueueError):
            apply_target_queue_policy([], budgets=TargetBudgets(total=1, by_source={"model_generated": 1}))
        with self.assertRaises(TargetQueueError):
            apply_target_queue_policy([], budgets=budgets(), policy="opaque")
        oversized = target("TGT-001")
        oversized["candidate_files"] = ["x" * 4097]
        with self.assertRaises(TargetQueueError):
            apply_target_queue_policy([oversized], budgets=budgets())
        malformed = target("TGT-001")
        malformed["priority"] = "100"
        with self.assertRaises(TargetQueueError):
            apply_target_queue_policy([malformed], budgets=budgets())

    def test_input_is_not_mutated(self) -> None:
        items = [target("TGT-001"), target("TGT-SCANNER-001")]
        before = copy.deepcopy(items)
        apply_target_queue_policy(items, budgets=budgets())
        self.assertEqual(before, items)

    def test_id_prefix_cannot_spoof_source_or_bypass_budget(self) -> None:
        fake_gapfill = target("TGT-GAPFILL-001", priority=1, sink="fake", scope="fake scope")
        fake_gapfill.pop("queue_source")
        legitimate = target("TGT-001", priority=100, risk="critical", sink="legit", scope="legit scope")

        active, deferred, summary = apply_target_queue_policy(
            [fake_gapfill, legitimate], budgets=budgets(total=1, source=1)
        )

        self.assertEqual(["TGT-001"], [item["id"] for item in active])
        self.assertEqual(["TGT-GAPFILL-001"], [item["id"] for item in deferred])
        self.assertEqual("model_generated", deferred[0]["queue_source"])
        decision = next(item for item in summary["decisions"] if item["target_id"] == "TGT-GAPFILL-001")
        self.assertEqual("model_generated", decision["source"])
        self.assertEqual(0, summary["by_source"]["gapfill"]["generated"])

    def test_trusted_source_wins_canonical_prose_and_scope_prevents_false_merge(self) -> None:
        model = target("TGT-001", priority=100, risk="critical", scope="shared component")
        model["title"] = "attacker-controlled canonical title"
        trusted = target("TGT-AGENT-001", priority=20, risk="medium", scope="shared component")
        trusted["title"] = "Trusted agent surface title"

        active, _, summary = apply_target_queue_policy([model, trusted], budgets=budgets())

        self.assertEqual(1, len(active))
        self.assertEqual("TGT-AGENT-001", active[0]["id"])
        self.assertEqual("Trusted agent surface title", active[0]["title"])
        self.assertEqual("critical", active[0]["risk"])
        self.assertEqual(1, summary["merged"])

        other_scope = target("TGT-AGENT-002", scope="different component")
        separated, _, separated_summary = apply_target_queue_policy([model, other_scope], budgets=budgets())
        self.assertEqual(2, len(separated))
        self.assertEqual(0, separated_summary["merged"])

    def test_status_refresh_preserves_wave_until_explicit_rebalance(self) -> None:
        first = apply_target_queue_policy(
            [
                target("TGT-001", priority=100, scope="one"),
                target("TGT-002", priority=90, scope="two"),
                target("TGT-003", priority=80, scope="three"),
            ],
            budgets=budgets(total=1),
        )
        first[0][0]["status"] = "reviewed"

        active, deferred, summary = preserve_target_queue_membership(
            first[0], first[1], summary=first[2]
        )

        self.assertEqual(["TGT-001"], [item["id"] for item in active])
        self.assertEqual(["TGT-002", "TGT-003"], [item["id"] for item in deferred])
        self.assertEqual(1, summary["active"])
        self.assertEqual(2, summary["deferred_by_budget"])
        self.assertEqual([], validate_target_queue_artifact({"targets": active, "deferred_targets": deferred, "queue_summary": summary}))

        with self.assertRaisesRegex(TargetQueueError, "deferred target cannot enter the active queue"):
            preserve_target_queue_membership([*active, deferred[0]], deferred[1:], summary=summary)

        rebalanced = apply_target_queue_policy([*active, *deferred], budgets=budgets(total=1))
        self.assertEqual(["TGT-002", "TGT-001"], [item["id"] for item in rebalanced[0]])
        self.assertEqual(["TGT-003"], [item["id"] for item in rebalanced[1]])

    def test_post_selection_append_is_retained_until_rebalance(self) -> None:
        active, deferred, summary = apply_target_queue_policy(
            [target("TGT-001", scope="one")], budgets=budgets(total=1)
        )
        appended = target("TGT-SCANNER-001", priority=100, risk="critical", scope="scanner")

        refreshed = preserve_target_queue_membership([*active, appended], deferred, summary=summary)

        self.assertEqual(1, refreshed[2]["active"])
        self.assertEqual(1, refreshed[2]["retained_outside_budget"])
        decision = next(item for item in refreshed[2]["decisions"] if item["target_id"] == "TGT-SCANNER-001")
        self.assertEqual(("retained", "added_after_selection"), (decision["action"], decision["reason"]))
        self.assertEqual([], validate_target_queue_artifact({"targets": refreshed[0], "deferred_targets": refreshed[1], "queue_summary": refreshed[2]}))

    def test_nonqueued_and_gapfill_targets_are_retained_outside_seed_budgets(self) -> None:
        reviewed = target("TGT-001", priority=1, sink="reviewed")
        reviewed["status"] = "reviewed"
        gapfill = target("TGT-GAPFILL-001", priority=2, sink="gapfill")
        queued = target("TGT-002", priority=100, risk="critical", sink="queued")
        active, deferred, summary = apply_target_queue_policy(
            [reviewed, gapfill, queued],
            budgets=budgets(total=1, source=1),
        )
        self.assertEqual([], deferred)
        self.assertEqual(["TGT-002", "TGT-001", "TGT-GAPFILL-001"], [item["id"] for item in active])
        self.assertEqual(1, summary["active"])
        self.assertEqual(2, summary["retained_outside_budget"])
        decisions = {item["target_id"]: item for item in summary["decisions"]}
        self.assertEqual("status_retained", decisions["TGT-001"]["reason"])
        self.assertEqual("workflow_target_retained", decisions["TGT-GAPFILL-001"]["reason"])
        self.assertEqual("gapfill", decisions["TGT-GAPFILL-001"]["source"])

    def test_rebalance_preserves_merged_lineage_decisions(self) -> None:
        first = apply_target_queue_policy(
            [target("TGT-001"), target("TGT-AGENT-001", priority=90, risk="high")],
            budgets=budgets(total=1),
        )
        second = apply_target_queue_policy([*first[0], *first[1]], budgets=budgets(total=2))
        self.assertEqual(2, second[2]["generated"])
        self.assertEqual(1, second[2]["merged"])
        self.assertEqual(
            {"active", "merged"},
            {item["action"] for item in second[2]["decisions"]},
        )
        self.assertEqual(
            {"TGT-001", "TGT-AGENT-001"},
            target_ids_with_lineage(second[0]),
        )

    def test_semantic_normalization_refreshes_or_regroups_a_valid_queue(self) -> None:
        selected = target("TGT-001", priority=100, scope="selected")
        active, deferred, summary = apply_target_queue_policy([selected], budgets=budgets(total=1))
        active[0]["status"] = "reviewed"
        active, deferred, summary = preserve_target_queue_membership(active, deferred, summary=summary)
        active[0]["taxonomies"] = [{"name": "Test", "id": "AUTHZ-2", "label": "Normalized"}]

        refreshed = refresh_target_queue_after_semantic_normalization(
            {"targets": active, "deferred_targets": deferred, "queue_summary": summary}
        )

        self.assertEqual("reviewed", refreshed["targets"][0]["status"])
        self.assertEqual(1, refreshed["queue_summary"]["active"])
        self.assertEqual([], validate_target_queue_artifact(refreshed))

        first = target("TGT-001", scope="shared")
        first["taxonomies"] = [{"name": "Test", "id": "AUTHZ-1", "label": "One"}]
        second = target("TGT-002", scope="shared")
        second["taxonomies"] = [{"name": "Test", "id": "AUTHZ-2", "label": "Two"}]
        active, deferred, summary = apply_target_queue_policy([first, second], budgets=budgets(total=2))
        artifact = {"targets": active, "deferred_targets": deferred, "queue_summary": summary}
        for item in artifact["targets"]:
            item["taxonomies"] = [{"name": "Test", "id": "AUTHZ-3", "label": "Canonical"}]

        regrouped = refresh_target_queue_after_semantic_normalization(artifact)

        self.assertEqual(1, len(regrouped["targets"]))
        self.assertEqual(1, regrouped["queue_summary"]["merged"])
        self.assertEqual({"TGT-001", "TGT-002"}, target_ids_with_lineage(regrouped["targets"]))
        self.assertEqual([], validate_target_queue_artifact(regrouped))

        reviewed = target("TGT-001", priority=100, scope="shared")
        reviewed["taxonomies"] = [{"name": "Test", "id": "AUTHZ-1", "label": "One"}]
        waiting = target("TGT-002", priority=90, scope="shared")
        waiting["taxonomies"] = [{"name": "Test", "id": "AUTHZ-2", "label": "Two"}]
        active, deferred, summary = apply_target_queue_policy([reviewed, waiting], budgets=budgets(total=1))
        active[0]["status"] = "reviewed"
        active, deferred, summary = preserve_target_queue_membership(active, deferred, summary=summary)
        converged = {"targets": active, "deferred_targets": deferred, "queue_summary": summary}
        for item in [*converged["targets"], *converged["deferred_targets"]]:
            item["taxonomies"] = [{"name": "Test", "id": "AUTHZ-3", "label": "Canonical"}]

        regrouped_reviewed = refresh_target_queue_after_semantic_normalization(converged)

        self.assertEqual(1, len(regrouped_reviewed["targets"]))
        self.assertEqual([], regrouped_reviewed["deferred_targets"])
        self.assertEqual("reviewed", regrouped_reviewed["targets"][0]["status"])
        self.assertEqual([], validate_target_queue_artifact(regrouped_reviewed))

    def test_queue_artifact_validation_rejects_count_path_and_open_payload_drift(self) -> None:
        active, deferred, summary = apply_target_queue_policy(
            [target("TGT-001", sink="one"), target("TGT-002", sink="two")],
            budgets=budgets(total=1),
        )
        artifact = {"targets": active, "deferred_targets": deferred, "queue_summary": summary}
        self.assertEqual([], validate_target_queue_artifact(artifact))

        count_drift = copy.deepcopy(artifact)
        count_drift["queue_summary"]["active"] = 2
        self.assertTrue(validate_target_queue_artifact(count_drift))
        unsafe_ref = copy.deepcopy(artifact)
        unsafe_ref["targets"][0]["source_lineage"][0]["evidence_refs"] = ["../private.txt"]
        self.assertTrue(validate_target_queue_artifact(unsafe_ref))
        wrong_source_ref = copy.deepcopy(artifact)
        wrong_source_ref["targets"][0]["source_lineage"][0]["evidence_refs"] = ["reports/agent-surface.json"]
        self.assertTrue(validate_target_queue_artifact(wrong_source_ref))
        malformed_ref = copy.deepcopy(artifact)
        malformed_ref["targets"][0]["source_lineage"][0]["evidence_refs"] = [{"raw": "opaque"}]
        self.assertTrue(validate_target_queue_artifact(malformed_ref))
        malformed_source_count = copy.deepcopy(artifact)
        malformed_source_count["queue_summary"]["by_source"]["model_generated"]["active"] = "one"
        self.assertTrue(validate_target_queue_artifact(malformed_source_count))
        open_decision = copy.deepcopy(artifact)
        open_decision["queue_summary"]["decisions"][0]["raw_evidence"] = "must-not-copy"
        self.assertTrue(validate_target_queue_artifact(open_decision))
        reason_drift = copy.deepcopy(artifact)
        reason_drift["queue_summary"]["decisions"][0]["reason"] = "total_budget_exhausted"
        self.assertTrue(validate_target_queue_artifact(reason_drift))

        promoted = copy.deepcopy(artifact)
        illicit = promoted["deferred_targets"].pop()
        promoted["targets"].append(illicit)
        decision = next(
            item for item in promoted["queue_summary"]["decisions"] if item["target_id"] == illicit["id"]
        )
        decision.update({"action": "retained", "reason": "added_after_selection"})
        promoted["queue_summary"]["retained_outside_budget"] = 1
        promoted["queue_summary"]["deferred_by_budget"] = 0
        promoted["queue_summary"]["by_source"][illicit["queue_source"]]["deferred"] = 0
        promoted["queue_summary"]["by_source"][illicit["queue_source"]]["retained"] = 1
        promotion_errors = validate_target_queue_artifact(promoted)
        self.assertTrue(any("selection_input_ids" in error for error in promotion_errors), promotion_errors)


if __name__ == "__main__":
    unittest.main()

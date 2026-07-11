from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from workflow_orchestrator import WorkflowPlanError, build_plan, load_profile, validate_profile, write_plan  # noqa: E402
from validators.common import load_schema, validate_schema  # noqa: E402


class WorkflowOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))
        self.run = self.work / "run"
        shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "minimal-run", self.run)
        (self.run / "repo").mkdir()
        self.definition, self.path, self.digest = load_profile(REPO_ROOT, "recon-only")

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    def plan(self, definition=None, skips=None):
        return build_plan(
            self.run,
            definition or self.definition,
            definition_ref="templates/workflows/recon-only.json",
            digest=self.digest,
            skips=skips or [],
        )

    def test_profile_has_deterministic_dependency_order_and_public_safe_plan(self) -> None:
        plan = self.plan()
        self.assertEqual(["recon", "targets"], [stage["id"] for stage in plan["stages"]])
        self.assertFalse(plan["safety"]["commands_executed"])
        self.assertFalse(plan["safety"]["github_mutation_allowed"])
        self.assertNotIn(str(self.run), json.dumps(plan))
        definition_errors: list[str] = []
        validate_schema(
            self.definition,
            json.loads((REPO_ROOT / "templates" / "workflows" / "workflow-definition.schema.json").read_text()),
            "workflow_definition",
            definition_errors,
        )
        plan_errors: list[str] = []
        validate_schema(plan, load_schema(REPO_ROOT, "workflow-plan.schema.json"), "workflow_plan", plan_errors)
        self.assertEqual([], definition_errors)
        self.assertEqual([], plan_errors)

    def test_unknown_dependency_and_cycle_fail_closed(self) -> None:
        unknown = copy.deepcopy(self.definition)
        unknown["stages"][1]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(WorkflowPlanError, "unknown or self"):
            validate_profile(unknown)
        cyclic = copy.deepcopy(self.definition)
        cyclic["stages"][0]["depends_on"] = ["targets"]
        with self.assertRaisesRegex(WorkflowPlanError, "cycle"):
            validate_profile(cyclic)

    def test_non_string_stage_lists_fail_closed_without_type_error(self) -> None:
        for key, item in (
            ("depends_on", ["nested"]),
            ("required_inputs", {"nested": "value"}),
            ("outputs", ["nested"]),
        ):
            definition = copy.deepcopy(self.definition)
            definition["stages"][0][key] = [item]
            with self.subTest(key=key), self.assertRaisesRegex(WorkflowPlanError, "list of strings"):
                validate_profile(definition)

    def test_network_github_mutation_and_unknown_commands_fail_closed(self) -> None:
        for mutation in ("network", "command", "argument", "credential", "path"):
            definition = copy.deepcopy(self.definition)
            if mutation == "network":
                definition["stages"][0]["network_allowed"] = True
            elif mutation == "command":
                definition["stages"][0]["command"][0] = "gra-issues"
            else:
                definition["stages"][0]["command"].append(
                    "--network" if mutation == "argument" else
                    "--token=example" if mutation == "credential" else
                    "--out=../../outside"
                )
            with self.subTest(mutation=mutation), self.assertRaises(WorkflowPlanError):
                validate_profile(definition)
        split_path = copy.deepcopy(self.definition)
        split_path["stages"][0]["command"] = ["gra-recon", "--run", "../../outside"]
        with self.assertRaisesRegex(WorkflowPlanError, "argv contract"):
            validate_profile(split_path)

    def test_unsatisfied_input_and_invalid_skips_fail_closed(self) -> None:
        (self.run / "repo").rmdir()
        with self.assertRaisesRegex(WorkflowPlanError, "unsatisfied required input"):
            self.plan()
        (self.run / "repo").mkdir()
        with self.assertRaisesRegex(WorkflowPlanError, "not skippable"):
            self.plan(skips=["recon"])
        with self.assertRaisesRegex(WorkflowPlanError, "unknown stage"):
            self.plan(skips=["unknown"])

    def test_scoped_leaf_skip_is_explicit(self) -> None:
        plan = self.plan(skips=["targets"])
        target = plan["stages"][1]
        self.assertEqual("skipped_by_scope", target["status"])
        self.assertTrue(target["skip_reason"])
        self.assertEqual(1, plan["summary"]["skipped_by_scope_count"])

    def test_write_path_remains_bound_to_validated_context(self) -> None:
        plan = self.plan()
        context_path = self.run / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "changed-after-build"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")

        json_path, markdown_path = write_plan(self.run, plan)

        self.assertEqual(self.run / "reports" / "workflow-plan.json", json_path)
        self.assertEqual(self.run / "reports" / "WORKFLOW_PLAN.md", markdown_path)
        self.assertFalse((self.run / "changed-after-build").exists())

    def test_reports_dir_with_spaces_matches_plan_schema(self) -> None:
        context_path = self.run / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "custom reports"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")

        plan = self.plan()
        errors: list[str] = []
        validate_schema(plan, load_schema(REPO_ROOT, "workflow-plan.schema.json"), "workflow_plan", errors)

        self.assertEqual("custom reports", plan["reports_dir"])
        self.assertEqual([], errors)

    def test_reports_dir_control_character_fails_closed(self) -> None:
        context_path = self.run / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "reports\nunsafe"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(WorkflowPlanError, "safe run-relative path"):
            self.plan()


if __name__ == "__main__":
    unittest.main(verbosity=2)

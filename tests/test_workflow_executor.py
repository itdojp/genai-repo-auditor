from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from run_state import block_run, pause_run, write_run_state  # noqa: E402
from validators.common import load_schema, validate_schema  # noqa: E402
from workflow_executor import WorkflowExecutionError, execute_workflow, resume_skip_set  # noqa: E402
from workflow_orchestrator import build_plan, load_profile  # noqa: E402


class WorkflowExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))
        self.run = self.work / "run"
        shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "minimal-run", self.run)
        (self.run / "repo").mkdir()
        (self.run / "reports" / "targets.json").unlink(missing_ok=True)
        self.lab_root = self.work / "lab"
        (self.lab_root / "bin").mkdir(parents=True)
        for command in ("gra-recon", "gra-targets"):
            shutil.copy2(REPO_ROOT / "bin" / command, self.lab_root / "bin" / command)
        definition, path, digest = load_profile(REPO_ROOT, "recon-only")
        self.plan = build_plan(
            self.run,
            definition,
            definition_ref=path.relative_to(REPO_ROOT).as_posix(),
            digest=digest,
            skips=[],
        )
        self.calls: list[str] = []
        self.fail_targets = False

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    def runner(self, argv: list[str], cwd: Path) -> int:
        command = Path(argv[0]).name
        self.calls.append(command)
        reports = cwd / "reports"
        reports.mkdir(exist_ok=True)
        if command == "gra-recon":
            for name in ("AUDIT_SUMMARY.md", "THREAT_MODEL.md", "ATTACK_SURFACE.md"):
                (reports / name).write_text(f"# {name}\n", encoding="utf-8")
            for name in ("agent-surface.json", "provenance-posture.json"):
                (reports / name).write_text("{}\n", encoding="utf-8")
            return 0
        if self.fail_targets:
            return 7
        (reports / "targets.json").write_text('{"targets": []}\n', encoding="utf-8")
        return 0

    def execute(self, **kwargs):
        return execute_workflow(self.run, self.plan, lab_root=self.lab_root, runner=self.runner, **kwargs)

    def assert_checkpoint_schema(self, checkpoint: dict) -> None:
        schema = load_schema(REPO_ROOT, "workflow-checkpoint.schema.json")
        errors: list[str] = []
        validate_schema(checkpoint, schema, "workflow_checkpoint", errors)
        for stage in checkpoint["stages"]:
            validate_schema(stage, schema["$defs"]["stage"], "workflow_checkpoint.stage", errors)
            for artifact in stage["output_artifacts"]:
                validate_schema(artifact, schema["$defs"]["artifact"], "workflow_checkpoint.artifact", errors)
        self.assertEqual([], errors)

    def test_dependency_order_success_and_sanitized_checkpoint(self) -> None:
        checkpoint, exit_code = self.execute()

        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-recon", "gra-targets"], self.calls)
        self.assertEqual("succeeded", checkpoint["status"])
        self.assertIsNone(checkpoint["resume_stage"])
        self.assertNotIn(str(self.run), json.dumps(checkpoint))
        self.assertNotIn("argv", json.dumps(checkpoint))
        self.assert_checkpoint_schema(checkpoint)
        self.assertEqual(["gra-recon", "gra-targets"], [item["command"] for item in checkpoint["command_implementations"]])

    def test_failure_blocks_then_resume_retries_only_failed_stage(self) -> None:
        self.fail_targets = True
        checkpoint, exit_code = self.execute()
        self.assertEqual(7, exit_code)
        self.assertEqual("blocked", checkpoint["status"])
        self.assertEqual("targets", checkpoint["resume_stage"])
        self.assertEqual(["gra-recon", "gra-targets"], self.calls)

        self.calls.clear()
        self.fail_targets = False
        checkpoint, exit_code = self.execute(resume=True)

        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-targets"], self.calls)
        self.assertEqual("succeeded", checkpoint["status"])
        self.assertEqual(1, checkpoint["stages"][0]["attempt"])
        self.assertEqual(2, checkpoint["stages"][1]["attempt"])

    def test_resume_rejects_stale_successful_output(self) -> None:
        self.fail_targets = True
        self.execute()
        (self.run / "reports" / "ATTACK_SURFACE.md").write_text("changed\n", encoding="utf-8")

        with self.assertRaisesRegex(WorkflowExecutionError, "stale or mismatched"):
            self.execute(resume=True)

    def test_resume_rejects_stale_posture_input_consumed_by_targets(self) -> None:
        self.execute(until_stage="recon")
        (self.run / "reports" / "agent-surface.json").write_text('{"changed": true}\n', encoding="utf-8")

        with self.assertRaisesRegex(WorkflowExecutionError, "stale or mismatched"):
            self.execute(resume=True)

    def test_resume_rejects_missing_declared_output_stamp(self) -> None:
        self.execute(until_stage="recon")
        checkpoint_path = self.run / "reports" / "workflow-checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["stages"][0]["output_artifacts"].pop()
        checkpoint_path.write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(WorkflowExecutionError, "do not match declared outputs"):
            self.execute(resume=True)

    def test_resume_rejects_changed_command_implementation(self) -> None:
        self.execute(until_stage="recon")
        with (self.lab_root / "bin" / "gra-targets").open("a", encoding="utf-8") as handle:
            handle.write("\n# changed\n")

        with self.assertRaisesRegex(WorkflowExecutionError, "implementation is stale"):
            self.execute(resume=True)

    def test_resume_rejects_output_injected_for_pending_stage(self) -> None:
        self.execute(until_stage="recon")
        (self.run / "reports" / "targets.json").write_text('{"stale": true}\n', encoding="utf-8")
        self.calls.clear()

        with self.assertRaisesRegex(WorkflowExecutionError, "output already exists"):
            self.execute(resume=True)
        self.assertEqual([], self.calls)

    def test_until_pauses_at_exact_resume_stage(self) -> None:
        checkpoint, exit_code = self.execute(until_stage="recon")
        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-recon"], self.calls)
        self.assertEqual("paused", checkpoint["status"])
        self.assertEqual("targets", checkpoint["resume_stage"])

        self.calls.clear()
        checkpoint, exit_code = self.execute(resume=True)
        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-targets"], self.calls)
        self.assertEqual("succeeded", checkpoint["status"])

    def test_from_requires_and_records_external_prerequisite(self) -> None:
        reports = self.run / "reports"
        reports.mkdir(exist_ok=True)
        (reports / "ATTACK_SURFACE.md").write_text("existing\n", encoding="utf-8")
        (reports / "agent-surface.json").write_text("{}\n", encoding="utf-8")
        (reports / "provenance-posture.json").write_text("{}\n", encoding="utf-8")

        checkpoint, exit_code = self.execute(from_stage="targets")

        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-targets"], self.calls)
        self.assertEqual("external_prerequisite", checkpoint["stages"][0]["status"])
        self.assertEqual(
            [
                "reports/ATTACK_SURFACE.md",
                "reports/agent-surface.json",
                "reports/provenance-posture.json",
            ],
            [x["path"] for x in checkpoint["external_input_artifacts"]],
        )

    def test_from_rejects_missing_external_prerequisite(self) -> None:
        with self.assertRaisesRegex(WorkflowExecutionError, "artifact is missing"):
            self.execute(from_stage="targets")
        self.assertEqual([], self.calls)

    def test_pause_and_blocked_run_states_fail_before_stage_execution(self) -> None:
        for state in (
            pause_run(self.run, reason="operator pause"),
            block_run(self.run, reason="operator block"),
        ):
            write_run_state(self.run, state)
            with self.subTest(status=state["status"]), self.assertRaisesRegex(WorkflowExecutionError, state["status"]):
                self.execute()
            self.assertEqual([], self.calls)
            (self.run / "reports" / "run-state.json").unlink()

    def test_interruption_writes_resumable_checkpoint(self) -> None:
        def interrupted(_argv: list[str], _cwd: Path) -> int:
            raise KeyboardInterrupt

        checkpoint, exit_code = execute_workflow(
            self.run, self.plan, lab_root=self.lab_root, runner=interrupted
        )

        self.assertEqual(130, exit_code)
        self.assertEqual("paused", checkpoint["status"])
        self.assertEqual("recon", checkpoint["resume_stage"])
        self.assertEqual("interrupted", checkpoint["stages"][0]["error_category"])

    def test_existing_checkpoint_requires_resume(self) -> None:
        self.execute(until_stage="recon")
        self.assertEqual([], resume_skip_set(self.run))
        with self.assertRaisesRegex(WorkflowExecutionError, "already exists"):
            self.execute()

    def test_existing_declared_output_rejects_new_execution(self) -> None:
        (self.run / "reports" / "targets.json").write_text('{"stale": true}\n', encoding="utf-8")

        with self.assertRaisesRegex(WorkflowExecutionError, "output already exists"):
            self.execute()
        self.assertEqual([], self.calls)

    def test_symlink_run_state_fails_closed(self) -> None:
        reports = self.run / "reports"
        reports.mkdir(exist_ok=True)
        outside = self.work / "state.json"
        outside.write_text('{"status": "active"}\n', encoding="utf-8")
        (reports / "run-state.json").symlink_to(outside)

        with self.assertRaisesRegex(WorkflowExecutionError, "must not be a symlink"):
            self.execute()
        self.assertEqual([], self.calls)

    def test_pause_between_stages_stops_before_dependent(self) -> None:
        def pause_after_recon(argv: list[str], cwd: Path) -> int:
            result = self.runner(argv, cwd)
            if Path(argv[0]).name == "gra-recon":
                write_run_state(self.run, pause_run(self.run, reason="operator pause"))
            return result

        checkpoint, exit_code = execute_workflow(
            self.run, self.plan, lab_root=self.lab_root, runner=pause_after_recon
        )

        self.assertEqual(5, exit_code)
        self.assertEqual(["gra-recon"], self.calls)
        self.assertEqual("paused", checkpoint["status"])
        self.assertEqual("targets", checkpoint["resume_stage"])

    def test_from_uses_dependency_closure_not_topological_slice(self) -> None:
        branched = dict(self.plan)
        branched["profile"] = "branched"
        branched["definition_sha256"] = "a" * 64
        branched["stages"] = [
            {
                **self.plan["stages"][0],
                "id": "a",
                "depends_on": [],
                "required_inputs": ["context.json", "repo"],
                "outputs": ["reports/a.md"],
            },
            {
                **self.plan["stages"][1],
                "id": "b",
                "depends_on": ["a"],
                "required_inputs": ["context.json", "reports/a.md"],
                "outputs": ["reports/b.json"],
            },
            {
                **self.plan["stages"][0],
                "id": "c",
                "depends_on": ["a"],
                "required_inputs": ["context.json", "reports/a.md"],
                "outputs": ["reports/c.md"],
            },
        ]
        (self.run / "reports" / "a.md").write_text("external prerequisite\n", encoding="utf-8")
        calls: list[str] = []

        def range_runner(argv: list[str], cwd: Path) -> int:
            calls.append(Path(argv[0]).name)
            (cwd / "reports" / "b.json").write_text("{}\n", encoding="utf-8")
            return 0

        checkpoint, exit_code = execute_workflow(
            self.run,
            branched,
            lab_root=self.lab_root,
            from_stage="b",
            runner=range_runner,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-targets"], calls)
        self.assertEqual(
            {"a": "external_prerequisite", "b": "succeeded", "c": "out_of_range"},
            {stage["id"]: stage["status"] for stage in checkpoint["stages"]},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

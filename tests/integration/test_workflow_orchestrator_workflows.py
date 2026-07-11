from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403

from workflow_executor import execute_workflow  # noqa: E402
from workflow_orchestrator import build_plan, load_profile  # noqa: E402


class WorkflowOrchestratorWorkflowTests(CliWorkflowTestCase):
    def test_default_plan_writes_public_safe_artifacts_without_execution(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        sentinel = self.work_dir / "stage-invocations"
        for command in ("gra-recon", "gra-targets", "gh", "codex"):
            path = self.mock_bin / command
            path.write_text(f"#!/bin/sh\necho {command} >> {sentinel}\nexit 97\n", encoding="utf-8")
            path.chmod(0o755)

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-run", "--run", run_dir, "--profile", "recon-only"], check=True)

        self.assertIn("no stages executed", cp.stdout)
        self.assertFalse(sentinel.exists())
        plan = json.loads((run_dir / "reports" / "workflow-plan.json").read_text(encoding="utf-8"))
        self.assertEqual("plan", plan["mode"])
        self.assertEqual(["recon", "targets"], [stage["id"] for stage in plan["stages"]])
        self.assertFalse(plan["safety"]["commands_executed"])
        self.assertNotIn(str(run_dir), json.dumps(plan))
        self.assertTrue((run_dir / "reports" / "WORKFLOW_PLAN.md").is_file())
        events = self.read_command_events(run_dir)
        self.assertEqual(1, len(events))
        self.assert_public_command_event(events[0], command="gra-run", phase="plan")
        self.assertEqual(["context.json"], events[0]["input_artifact_refs"])
        self.assertEqual(
            ["reports/workflow-plan.json", "reports/WORKFLOW_PLAN.md"],
            events[0]["output_artifact_refs"],
        )

    def test_publication_ready_execution_reports_status_and_command_event(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()

        cp = self.run_cmd([
            REPO_ROOT / "bin" / "gra-run",
            "--run", run_dir,
            "--profile", "publication-ready",
            "--execute",
        ], check=True)

        self.assertIn("Workflow execution: succeeded", cp.stdout)
        report = json.loads((run_dir / "reports" / "workflow-execution.json").read_text(encoding="utf-8"))
        self.assertEqual("succeeded", report["status"])
        self.assertEqual(5, report["summary"]["by_status"]["succeeded"])
        self.assertEqual(0, report["summary"]["absent_stage_count"])
        self.assertFalse(report["resume"]["available"])
        self.assertFalse(report["safety"]["issue_publication_included"])

        run_event = self.read_command_events(run_dir)[-1]
        self.assert_public_command_event(run_event, command="gra-run", phase="execute")
        self.assertEqual(
            [
                "reports/workflow-plan.json",
                "reports/WORKFLOW_PLAN.md",
                "reports/workflow-checkpoint.json",
                "reports/workflow-execution.json",
                "reports/WORKFLOW_EXECUTION.md",
            ],
            run_event["output_artifact_refs"],
        )

        # Reporting stages observe the execution report as it existed while each
        # stage was running. Refresh them after gra-run completes to consume the
        # terminal workflow status and the gra-run completion event.
        self.run_cmd([REPO_ROOT / "bin" / "gra-metrics", "--run", run_dir], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-evidence-graph", "--run", run_dir], check=True)
        validation = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir], check=True)
        self.assertIn("Workflow execution: validated", validation.stdout)
        metrics = json.loads((run_dir / "reports" / "metrics.json").read_text(encoding="utf-8"))
        graph = json.loads((run_dir / "reports" / "evidence-graph.json").read_text(encoding="utf-8"))
        self.assertEqual("succeeded", metrics["summary"]["workflow_execution"]["status"])
        self.assertEqual("succeeded", graph["summary"]["workflow_execution"]["status"])

    def test_custom_reports_dir_and_scoped_skip_are_respected(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "artifacts"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")

        self.run_cmd([REPO_ROOT / "bin" / "gra-run", "--run", run_dir, "--profile", "recon-only", "--skip", "targets"], check=True)

        plan = json.loads((run_dir / "artifacts" / "workflow-plan.json").read_text(encoding="utf-8"))
        self.assertEqual("skipped_by_scope", plan["stages"][1]["status"])
        self.assertEqual(
            [
                "artifacts/ATTACK_SURFACE.md",
                "artifacts/agent-surface.json",
                "artifacts/provenance-posture.json",
            ],
            plan["stages"][1]["required_inputs"][1:],
        )
        self.assertFalse((run_dir / "reports" / "workflow-plan.json").exists())

    def test_reports_dir_under_target_is_rejected_before_plan_writes(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "repo/reports"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")

        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-run", "--run", run_dir, "--profile", "recon-only"])

        self.assertEqual(2, cp.returncode)
        self.assertIn("must not overlap", cp.stderr)
        self.assertFalse((run_dir / "repo" / "reports").exists())

    def test_paused_or_blocked_execution_does_not_write_plan(self) -> None:
        for status in ("paused", "blocked"):
            with self.subTest(status=status):
                run_dir = self.copy_fixture_run("minimal-run")
                (run_dir / "repo").mkdir()
                reports = run_dir / "reports"
                (reports / "workflow-plan.json").unlink(missing_ok=True)
                (reports / "run-state.json").write_text(json.dumps({"status": status}) + "\n", encoding="utf-8")

                cp = self.run_cmd([
                    REPO_ROOT / "bin" / "gra-run",
                    "--run", run_dir,
                    "--profile", "recon-only",
                    "--execute",
                ])

                self.assertEqual(2, cp.returncode)
                self.assertIn(status, cp.stderr)
                self.assertFalse((reports / "workflow-plan.json").exists())

    def test_invalid_resume_checkpoint_does_not_overwrite_plan_or_record_stale_outputs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        self.run_cmd([
            REPO_ROOT / "bin" / "gra-run",
            "--run", run_dir,
            "--profile", "recon-only",
        ], check=True)
        definition, path, digest = load_profile(REPO_ROOT, "recon-only")
        plan = build_plan(
            run_dir,
            definition,
            definition_ref=path.relative_to(REPO_ROOT).as_posix(),
            digest=digest,
            skips=[],
        )

        def runner(argv: list[str], cwd: Path) -> int:
            stage = next(item for item in plan["stages"] if item["command"][0] == Path(argv[0]).name)
            for ref in stage["outputs"]:
                output = cwd / ref
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("{}\n" if output.suffix == ".json" else "# fixture\n", encoding="utf-8")
            return 0

        checkpoint, exit_code = execute_workflow(
            run_dir,
            plan,
            lab_root=REPO_ROOT,
            until_stage="recon",
            runner=runner,
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("paused", checkpoint["status"])
        plan_path = run_dir / "reports" / "workflow-plan.json"
        original_plan = plan_path.read_bytes()
        original_event_count = len(self.read_command_events(run_dir))
        checkpoint_path = run_dir / "reports" / "workflow-checkpoint.json"
        corrupted = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        corrupted["requested_skips"] = ["targets"]
        checkpoint_path.write_text(json.dumps(corrupted, indent=2) + "\n", encoding="utf-8")

        result = self.run_cmd([
            REPO_ROOT / "bin" / "gra-run",
            "--run", run_dir,
            "--profile", "recon-only",
            "--resume",
        ])

        self.assertEqual(2, result.returncode)
        self.assertIn("does not match the current run/profile/plan", result.stderr)
        self.assertEqual(original_plan, plan_path.read_bytes())
        self.assertEqual(original_event_count, len(self.read_command_events(run_dir)))

    def test_valid_resume_emits_terminal_workflow_report_and_resume_event(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        self.run_cmd([
            REPO_ROOT / "bin" / "gra-run",
            "--run", run_dir,
            "--profile", "publication-ready",
        ], check=True)
        definition, path, digest = load_profile(REPO_ROOT, "publication-ready")
        plan = build_plan(
            run_dir,
            definition,
            definition_ref=path.relative_to(REPO_ROOT).as_posix(),
            digest=digest,
            skips=[],
        )
        checkpoint, exit_code = execute_workflow(
            run_dir,
            plan,
            lab_root=REPO_ROOT,
            until_stage="report-validation",
            runner=lambda _argv, _cwd: 0,
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("paused", checkpoint["status"])
        self.assertEqual("metrics", checkpoint["resume_stage"])

        result = self.run_cmd([
            REPO_ROOT / "bin" / "gra-run",
            "--run", run_dir,
            "--profile", "publication-ready",
            "--resume",
        ], check=True)

        self.assertIn("Workflow execution: succeeded", result.stdout)
        report = json.loads((run_dir / "reports" / "workflow-execution.json").read_text(encoding="utf-8"))
        self.assertEqual("succeeded", report["status"])
        self.assertFalse(report["resume"]["available"])
        event = self.read_command_events(run_dir)[-1]
        self.assert_public_command_event(event, command="gra-run", phase="resume")
        self.assertEqual(
            ["context.json", "reports/workflow-plan.json", "reports/workflow-checkpoint.json"],
            event["input_artifact_refs"],
        )
        self.assertEqual(
            [
                "reports/workflow-checkpoint.json",
                "reports/workflow-execution.json",
                "reports/WORKFLOW_EXECUTION.md",
            ],
            event["output_artifact_refs"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

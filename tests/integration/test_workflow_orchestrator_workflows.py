from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


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
        self.assertEqual(["artifacts/ATTACK_SURFACE.md"], plan["stages"][1]["required_inputs"][1:])
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403

sys.path.insert(0, str(REPO_ROOT / "lib"))
from workflow_executor import execute_workflow  # noqa: E402
from workflow_orchestrator import build_plan, load_profile  # noqa: E402
from run_state import clear_pause, pause_run, write_run_state  # noqa: E402
from validators.common import validate_schema  # noqa: E402


EXPECTED = {
    "recon-only": ["recon", "targets"],
    "supply-chain": ["recon", "syft-plan", "targets"],
    "appsec-deep": ["recon", "gitleaks-plan", "targets", "chains", "proofs", "adversarial-validation"],
    "publication-ready": ["report-validation", "metrics", "evidence-graph", "dashboard", "sarif"],
    "full": ["recon", "syft-plan", "gitleaks-plan", "targets", "chains", "proofs", "adversarial-validation", "report-validation", "metrics", "evidence-graph", "dashboard", "sarif"],
}
EXPECTED_DEPENDENCIES = {
    "recon-only": {"recon": [], "targets": ["recon"]},
    "supply-chain": {"recon": [], "syft-plan": ["recon"], "targets": ["recon"]},
    "appsec-deep": {"recon": [], "gitleaks-plan": ["recon"], "targets": ["recon"], "chains": ["targets"], "proofs": ["chains"], "adversarial-validation": ["proofs"]},
    "publication-ready": {"report-validation": [], "metrics": ["report-validation"], "evidence-graph": ["metrics"], "dashboard": ["evidence-graph"], "sarif": ["report-validation"]},
    "full": {"recon": [], "syft-plan": ["recon"], "gitleaks-plan": ["recon"], "targets": ["recon"], "chains": ["targets"], "proofs": ["chains"], "adversarial-validation": ["proofs"], "report-validation": ["adversarial-validation"], "metrics": ["report-validation"], "evidence-graph": ["metrics"], "dashboard": ["evidence-graph"], "sarif": ["report-validation"]},
}


class BuiltinWorkflowProfileTests(CliWorkflowTestCase):
    @staticmethod
    def use_custom_reports_dir(run_dir: Path, name: str = "artifacts") -> Path:
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = name
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        reports = run_dir / name
        reports.parent.mkdir(parents=True, exist_ok=True)
        (run_dir / "reports").rename(reports)
        return reports

    def prepare(self, profile: str):
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        definition, path, digest = load_profile(REPO_ROOT, profile)
        if any(any(output.endswith("/targets.json") for output in stage["outputs"]) for stage in definition["stages"]):
            (run_dir / "reports" / "targets.json").unlink(missing_ok=True)
        plan = build_plan(run_dir, definition, definition_ref=path.relative_to(REPO_ROOT).as_posix(), digest=digest, skips=[])
        command_root = self.work_dir / f"commands-{profile}"
        (command_root / "bin").mkdir(parents=True)
        for command in sorted({stage["command"][0] for stage in plan["stages"]}):
            shutil.copy2(REPO_ROOT / "bin" / command, command_root / "bin" / command)
        return run_dir, plan, command_root

    @staticmethod
    def write_stage_outputs(stage: dict, cwd: Path) -> None:
        for output in stage["outputs"]:
            path = cwd / output
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")

    def test_all_profiles_have_expected_order_and_offline_safe_commands(self) -> None:
        forbidden = {"gra-issues", "gra-remediate", "gh", "gitleaks", "syft", "gra-release"}
        schema = json.loads((REPO_ROOT / "templates" / "workflows" / "workflow-definition.schema.json").read_text(encoding="utf-8"))
        for profile, expected in EXPECTED.items():
            with self.subTest(profile=profile):
                _run_dir, plan, _command_root = self.prepare(profile)
                definition = json.loads((REPO_ROOT / "templates" / "workflows" / f"{profile}.json").read_text(encoding="utf-8"))
                schema_errors: list[str] = []
                validate_schema(definition, schema, f"workflow.{profile}", schema_errors)
                self.assertEqual([], schema_errors)
                self.assertEqual(expected, [stage["id"] for stage in plan["stages"]])
                self.assertEqual(EXPECTED_DEPENDENCIES[profile], {stage["id"]: stage["depends_on"] for stage in plan["stages"]})
                self.assertTrue(all(stage["network_allowed"] is False for stage in plan["stages"]))
                self.assertTrue(all(stage["mutation"] == "local-artifacts-only" for stage in plan["stages"]))
                commands = [stage["command"] for stage in plan["stages"]]
                self.assertTrue(forbidden.isdisjoint({argv[0] for argv in commands}))
                arguments = [argument for argv in commands for argument in argv[1:]]
                dangerous_arguments = {
                    "--allow-public",
                    "--apply",
                    "--apply-plan",
                    "--execute",
                    "--network",
                    "--publish",
                }
                self.assertTrue(
                    dangerous_arguments.isdisjoint(arguments)
                )

    def test_profiles_execute_with_deterministic_offline_fixture_runner(self) -> None:
        for profile in EXPECTED:
            with self.subTest(profile=profile):
                run_dir, plan, command_root = self.prepare(profile)
                calls: list[str] = []
                stages_by_command: dict[str, list[dict]] = {}
                for item in plan["stages"]:
                    stages_by_command.setdefault(item["command"][0], []).append(item)
                command_indexes = {command: 0 for command in stages_by_command}

                def runner(argv: list[str], cwd: Path) -> int:
                    command = Path(argv[0]).name
                    calls.append(command)
                    stage = stages_by_command[command][command_indexes[command]]
                    command_indexes[command] += 1
                    self.write_stage_outputs(stage, cwd)
                    return 0

                checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=runner)
                self.assertEqual(0, exit_code)
                self.assertEqual("succeeded", checkpoint["status"])
                self.assertNotIn("gra-issues", calls)

    def test_supply_chain_scoped_skip_stays_distinct(self) -> None:
        run_dir, _plan, command_root = self.prepare("supply-chain")
        definition, path, digest = load_profile(REPO_ROOT, "supply-chain")
        plan = build_plan(run_dir, definition, definition_ref=path.relative_to(REPO_ROOT).as_posix(), digest=digest, skips=["syft-plan"])
        calls: list[str] = []

        def runner(argv: list[str], cwd: Path) -> int:
            calls.append(Path(argv[0]).name)
            stage = next(item for item in plan["stages"] if item["command"][0] == Path(argv[0]).name)
            self.write_stage_outputs(stage, cwd)
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=runner)
        self.assertEqual(0, exit_code)
        self.assertEqual("skipped_by_scope", next(x for x in checkpoint["stages"] if x["id"] == "syft-plan")["status"])
        self.assertNotIn("gra-scan", calls)

    def test_recon_only_scoped_skip_is_not_missing_or_failed(self) -> None:
        run_dir, _plan, command_root = self.prepare("recon-only")
        definition, path, digest = load_profile(REPO_ROOT, "recon-only")
        plan = build_plan(run_dir, definition, definition_ref=path.relative_to(REPO_ROOT).as_posix(), digest=digest, skips=["targets"])

        def runner(_argv: list[str], cwd: Path) -> int:
            self.write_stage_outputs(plan["stages"][0], cwd)
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=runner)
        target = next(item for item in checkpoint["stages"] if item["id"] == "targets")
        self.assertEqual(0, exit_code)
        self.assertEqual("skipped_by_scope", target["status"])
        self.assertIsNone(target["error_category"])

    def test_dependency_failure_then_recovery_resumes_without_successful_stages(self) -> None:
        run_dir, plan, command_root = self.prepare("appsec-deep")
        stage_by_command = {stage["command"][0]: stage for stage in plan["stages"]}
        first_calls: list[str] = []

        def fail_chains(argv: list[str], cwd: Path) -> int:
            command = Path(argv[0]).name
            first_calls.append(command)
            if command == "gra-chains":
                return 9
            self.write_stage_outputs(stage_by_command[command], cwd)
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=fail_chains)
        self.assertEqual(9, exit_code)
        self.assertEqual("blocked", checkpoint["status"])
        self.assertEqual("chains", checkpoint["resume_stage"])

        resumed_calls: list[str] = []

        def recover(argv: list[str], cwd: Path) -> int:
            command = Path(argv[0]).name
            resumed_calls.append(command)
            self.write_stage_outputs(stage_by_command[command], cwd)
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=recover, resume=True)
        self.assertEqual(0, exit_code)
        self.assertEqual("succeeded", checkpoint["status"])
        self.assertEqual(["gra-chains", "gra-proofs", "gra-adversarial-validate"], resumed_calls)

    def test_interruption_and_operator_pause_have_exact_resume_points(self) -> None:
        run_dir, plan, command_root = self.prepare("supply-chain")

        def interrupt(_argv: list[str], _cwd: Path) -> int:
            raise KeyboardInterrupt

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=interrupt)
        self.assertEqual(130, exit_code)
        self.assertEqual("recon", checkpoint["resume_stage"])
        (run_dir / "reports" / "workflow-checkpoint.json").unlink()

        calls: list[str] = []
        stages = {stage["command"][0]: stage for stage in plan["stages"]}

        def pause_after_recon(argv: list[str], cwd: Path) -> int:
            command = Path(argv[0]).name
            calls.append(command)
            self.write_stage_outputs(stages[command], cwd)
            if command == "gra-recon":
                write_run_state(run_dir, pause_run(run_dir, reason="fixture pause"))
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=pause_after_recon)
        self.assertEqual(5, exit_code)
        self.assertEqual("syft-plan", checkpoint["resume_stage"])
        self.assertEqual(["gra-recon"], calls)

        write_run_state(run_dir, clear_pause(run_dir, resumed_by="fixture"))
        resumed: list[str] = []

        def resume(argv: list[str], cwd: Path) -> int:
            command = Path(argv[0]).name
            resumed.append(command)
            self.write_stage_outputs(stages[command], cwd)
            return 0

        checkpoint, exit_code = execute_workflow(run_dir, plan, lab_root=command_root, runner=resume, resume=True)
        self.assertEqual(0, exit_code)
        self.assertEqual(["gra-scan", "gra-targets"], resumed)

    def test_real_no_subject_commands_write_empty_contracts_without_codex(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"] = []
        findings_path.write_text(json.dumps(findings) + "\n", encoding="utf-8")
        env, codex_log = self.env_with_codex_log()

        proofs = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-proofs", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )
        validation = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-adversarial-validate", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )

        self.assertIn("No matching findings", proofs.stdout)
        self.assertIn("No matching findings", validation.stdout)
        self.assertEqual([], self.read_codex_calls(codex_log))
        self.assertEqual([], json.loads((run_dir / "reports" / "proofs.json").read_text())["proofs"])
        self.assertEqual([], json.loads((run_dir / "reports" / "validation.json").read_text())["validations"])
        self.assertTrue((run_dir / "reports" / "PROOFS.md").is_file())
        self.assertTrue((run_dir / "reports" / "VALIDATION.md").is_file())

    def test_real_profile_commands_and_validation_honor_custom_reports_dir(self) -> None:
        chain_run = self.copy_fixture_run("minimal-run")
        chain_reports = self.use_custom_reports_dir(chain_run)
        chain_findings_path = chain_reports / "findings.json"
        chain_findings = json.loads(chain_findings_path.read_text(encoding="utf-8"))
        chain_findings["findings"][0]["issue_body_file"] = "artifacts/issue-drafts/SEC-001.md"
        chain_findings_path.write_text(json.dumps(chain_findings) + "\n", encoding="utf-8")
        chain_env, _chain_codex_log = self.env_with_codex_log(
            GRA_MOCK_FIXTURE_DIR=str(FIXTURES / "chain-output")
        )
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-chains", "--run", chain_run],
            env=chain_env,
            check=True,
        )
        self.assertTrue((chain_reports / "chains.json").is_file())
        self.assertTrue((chain_reports / "ATTACK_CHAINS.md").is_file())
        self.assertIn(
            "artifacts/chains.json",
            (chain_run / "prompts" / "exec" / "synthesize-chains.prompt.md").read_text(encoding="utf-8"),
        )
        chain_validation = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", chain_run],
            check=True,
        )
        self.assertIn("Chains: validated", chain_validation.stdout)
        self.assertFalse((chain_run / "reports").exists())

        run_dir = self.copy_fixture_run("minimal-run")
        reports = self.use_custom_reports_dir(run_dir)
        findings_path = reports / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        findings["findings"] = []
        findings_path.write_text(json.dumps(findings) + "\n", encoding="utf-8")
        env, codex_log = self.env_with_codex_log()

        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-proofs", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )
        self.run_cmd(
            [REPO_ROOT / "bin" / "gra-adversarial-validate", "--run", run_dir, "--all-critical-high"],
            env=env,
            check=True,
        )
        validation = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir],
            check=True,
        )

        self.assertEqual([], self.read_codex_calls(codex_log))
        self.assertEqual([], json.loads((reports / "proofs.json").read_text())["proofs"])
        self.assertEqual([], json.loads((reports / "validation.json").read_text())["validations"])
        self.assertTrue((reports / "PROOFS.md").is_file())
        self.assertTrue((reports / "VALIDATION.md").is_file())
        self.assertTrue((reports / "command-events.jsonl").is_file())
        self.assertIn(f"OK: {findings_path}", validation.stdout)
        self.assertFalse((run_dir / "reports").exists())

    def test_direct_profile_commands_reject_leaf_output_symlinks(self) -> None:
        cases = [
            ("gra-chains", [], "chains.json"),
            ("gra-proofs", ["--all-critical-high"], "proofs.json"),
            ("gra-adversarial-validate", ["--all-critical-high"], "validation.json"),
        ]
        for command, arguments, output_name in cases:
            with self.subTest(command=command):
                run_dir = self.copy_fixture_run("minimal-run")
                reports = self.use_custom_reports_dir(run_dir)
                if arguments:
                    findings_path = reports / "findings.json"
                    findings = json.loads(findings_path.read_text(encoding="utf-8"))
                    findings["findings"] = []
                    findings_path.write_text(json.dumps(findings) + "\n", encoding="utf-8")
                outside = self.work_dir / f"outside-{command}.json"
                outside.write_text("unchanged\n", encoding="utf-8")
                (reports / output_name).symlink_to(outside)
                env, codex_log = self.env_with_codex_log()

                result = self.run_cmd(
                    [REPO_ROOT / "bin" / command, "--run", run_dir, *arguments],
                    env=env,
                )

                self.assertEqual(2, result.returncode)
                self.assertIn("regular non-symlink file", result.stderr)
                self.assertEqual("unchanged\n", outside.read_text(encoding="utf-8"))
                self.assertEqual([], self.read_codex_calls(codex_log))

    def test_validate_report_handles_invalid_and_nested_custom_reports_dirs(self) -> None:
        unsafe_run = self.copy_fixture_run("minimal-run")
        unsafe_context_path = unsafe_run / "context.json"
        unsafe_context = json.loads(unsafe_context_path.read_text(encoding="utf-8"))
        unsafe_context["reports_dir"] = "../outside"
        unsafe_context_path.write_text(json.dumps(unsafe_context) + "\n", encoding="utf-8")

        unsafe = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--run", unsafe_run],
        )

        self.assertEqual(2, unsafe.returncode)
        self.assertIn("reports_dir must be a relative path", unsafe.stderr)
        self.assertNotIn("Traceback", unsafe.stderr)

        nested_run = self.copy_fixture_run("minimal-run")
        nested_reports = self.use_custom_reports_dir(nested_run, "artifacts/deep")
        nested_findings_path = nested_reports / "findings.json"
        nested_findings = json.loads(nested_findings_path.read_text(encoding="utf-8"))
        nested_findings["findings"][0]["issue_body_file"] = "artifacts/deep/issue-drafts/SEC-001.md"
        nested_findings_path.write_text(json.dumps(nested_findings) + "\n", encoding="utf-8")

        nested = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-validate-report", "--findings", nested_findings_path],
            check=True,
        )

        self.assertIn(f"OK: {nested_findings_path}", nested.stdout)

    def test_direct_profile_command_rejects_target_reports_overlap(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        (run_dir / "repo").mkdir()
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context.update({"target_repo_dir": "repo", "reports_dir": "repo"})
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        env, codex_log = self.env_with_codex_log()

        result = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-proofs", "--run", run_dir, "--all-critical-high"],
            env=env,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("reports_dir and target_repo_dir must not overlap", result.stderr)
        self.assertEqual([], list((run_dir / "repo").iterdir()))
        self.assertEqual([], self.read_codex_calls(codex_log))


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class ScannerRunnerWorkflowTests(CliWorkflowTestCase):
    def write_scanner_probe(self, name: str, marker: Path) -> None:
        path = self.mock_bin / name
        path.write_text(
            "#!/bin/sh\n"
            f"printf executed > {marker}\n"
            "exit 99\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_list_and_default_plan_never_execute_scanner_binaries(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        marker = self.work_dir / "scanner-executed"
        self.write_scanner_probe("gitleaks", marker)
        self.write_scanner_probe("syft", marker)

        cp_list = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--list", "--json"], check=True)
        listing = json.loads(cp_list.stdout)
        self.assertEqual(["gitleaks", "syft"], [item["id"] for item in listing["adapters"]])
        self.assertTrue(all(item["readiness"]["executable_available"] for item in listing["adapters"]))
        self.assertTrue(all(not item["readiness"]["version_check_executed"] for item in listing["adapters"]))

        cp_plan = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "gitleaks", "--json"],
            check=True,
        )
        plan = json.loads(cp_plan.stdout)
        self.assertEqual("plan", plan["mode"])
        self.assertFalse(plan["scanner_executed"])
        self.assertFalse(plan["network_accessed"])
        self.assertEqual("container", plan["sandbox_profile"])
        self.assertEqual("disabled", plan["network_policy"])
        self.assertEqual("gitleaks", plan["command"][0])
        self.assertEqual("repo", plan["read_paths"][0])
        self.assertEqual("reports/scanner-results/raw/gitleaks.json", plan["raw_output_path"])
        self.assertFalse(marker.exists(), "list/plan must not execute scanner or version commands")
        self.assertFalse((run_dir / "reports" / "scanner-results" / "raw").exists())
        self.assertEqual([], self.read_command_events(run_dir))

    def test_syft_plan_is_exact_argument_array_and_declares_ingest_contract(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-scan",
                "--run",
                run_dir,
                "--tool",
                "syft",
                "--plan",
                "--sandbox-profile",
                "gvisor",
                "--json",
            ],
            check=True,
        )
        plan = json.loads(cp.stdout)
        self.assertEqual(
            ["syft", "repo", "-o", "cyclonedx-json=reports/scanner-results/raw/syft.json"],
            plan["command"],
        )
        self.assertEqual("sbom-data", plan["adapter"]["result_classification"])
        self.assertEqual(
            {"tool": "syft", "format": "cyclonedx", "source_path": "reports/scanner-results/raw/syft.json"},
            plan["ingest"],
        )

    def test_planning_rejects_unknown_tools_unsafe_paths_and_network(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp_unknown = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "unknown"])
        self.assertEqual(2, cp_unknown.returncode)
        self.assertIn("unknown scanner adapter", cp_unknown.stderr)

        cp_network = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-scan",
                "--run",
                run_dir,
                "--tool",
                "gitleaks",
                "--network-policy",
                "explicit-allow",
            ]
        )
        self.assertEqual(2, cp_network.returncode)
        self.assertIn("does not declare network access", cp_network.stderr)

        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["reports_dir"] = "../outside"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        cp_path = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "syft"])
        self.assertEqual(2, cp_path.returncode)
        self.assertIn("reports directory", cp_path.stderr)
        self.assertFalse((run_dir.parent / "outside").exists())

        context["reports_dir"] = "reports"
        context["target_repo_dir"] = "--config=outside"
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
        cp_dash_path = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "gitleaks"])
        self.assertEqual(2, cp_dash_path.returncode)
        self.assertIn("leading-dash path components", cp_dash_path.stderr)

    def test_list_requires_existing_run_and_rejects_tool_combination(self) -> None:
        cp_missing = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", self.work_dir / "missing", "--list"])
        self.assertEqual(2, cp_missing.returncode)
        self.assertIn("run directory does not exist", cp_missing.stderr)

        run_dir = self.copy_fixture_run("minimal-run")
        cp_combined = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--list", "--tool", "gitleaks"]
        )
        self.assertEqual(2, cp_combined.returncode)
        self.assertIn("--tool cannot be used with --list", cp_combined.stderr)

        cp_list_network = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--list", "--network-policy", "explicit-allow"]
        )
        self.assertEqual(2, cp_list_network.returncode)
        self.assertIn("cannot enable network for --list", cp_list_network.stderr)

    def test_cli_rejects_symlinked_run_and_context(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        run_link = self.work_dir / "run-link"
        try:
            run_link.symlink_to(run_dir, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink not available: {exc}")

        cp_run = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_link, "--tool", "gitleaks"])
        self.assertEqual(2, cp_run.returncode)
        self.assertIn("run directory must not contain symlink components", cp_run.stderr)

        outside_context = self.work_dir / "outside-context.json"
        outside_context.write_text('{"run_id":"outside"}\n', encoding="utf-8")
        context_path = run_dir / "context.json"
        context_path.unlink()
        context_path.symlink_to(outside_context)
        cp_context = self.run_cmd([REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "syft"])
        self.assertEqual(2, cp_context.returncode)
        self.assertIn("context.json must be a regular non-symlink file", cp_context.stderr)

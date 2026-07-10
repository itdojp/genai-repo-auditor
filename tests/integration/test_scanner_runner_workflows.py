from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403

import dataclasses
from unittest import mock

from scanner_adapters import ADAPTERS
from scanner_runner import execute_scan


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

    def write_container_runtime(self, *, mode: str = "success", runtime_log: Path | None = None) -> Path:
        path = self.mock_bin / "docker"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, pathlib, sys, time\n"
            "args = sys.argv[1:]\n"
            "mode = " + repr(mode) + "\n"
            "runtime_log = " + repr(str(runtime_log) if runtime_log else "") + "\n"
            "if 'image' in args and 'inspect' in args:\n"
            "    raise SystemExit(1 if mode == 'missing-image' else 0)\n"
            "if 'rm' in args and '-f' in args:\n"
            "    raise SystemExit(0)\n"
            "if 'run' not in args:\n"
            "    raise SystemExit(98)\n"
            "mounts = [args[i + 1] for i, value in enumerate(args[:-1]) if value == '--mount']\n"
            "output_mount = next(value for value in mounts if 'dst=/output' in value)\n"
            "output_dir = pathlib.Path(next(part[4:] for part in output_mount.split(',') if part.startswith('src=')))\n"
            "image = next(value for value in args if '@sha256:' in value)\n"
            "adapter = 'gitleaks' if '/gitleaks/' in image else 'syft'\n"
            "if runtime_log:\n"
            "    pathlib.Path(runtime_log).write_text(json.dumps({'args': args, 'secret_visible': bool(os.environ.get('GH_TOKEN'))}))\n"
            "if mode == 'timeout':\n"
            "    time.sleep(5)\n"
            "if mode == 'nonzero':\n"
            "    raise SystemExit(7)\n"
            "if mode == 'oversized-log':\n"
            "    sys.stdout.write('x' * 1000001)\n"
            "output = output_dir / f'{adapter}.json'\n"
            "if mode == 'symlink-output':\n"
            "    output.symlink_to('/etc/passwd')\n"
            "elif mode == 'oversized':\n"
            "    output.write_bytes(b'[' + b' ' * 10000001 + b']')\n"
            "elif mode == 'too-many-results':\n"
            "    output.write_text(json.dumps([{}] * 1001))\n"
            "elif mode == 'invalid-output':\n"
            "    output.write_text('not-json')\n"
            "elif adapter == 'gitleaks':\n"
            "    output.write_text(('[{}]' if mode == 'leads' else '[]') + '\\n')\n"
            "else:\n"
            "    output.write_text(json.dumps({'bomFormat': 'CycloneDX', 'components': []}) + '\\n')\n"
            "raise SystemExit(10 if mode == 'leads' else (1 if mode == 'partial-error' else 0))\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        podman = self.mock_bin / "podman"
        podman.write_bytes(path.read_bytes())
        podman.chmod(0o755)
        return path

    def execute_scanner(self, run_dir: Path, tool: str, *, mode: str = "success") -> subprocess.CompletedProcess[str]:
        (run_dir / "repo").mkdir(exist_ok=True)
        runtime_log = self.work_dir / f"{tool}-{mode}-runtime.json"
        self.write_container_runtime(mode=mode, runtime_log=runtime_log)
        env = self.env.copy()
        env["GH_TOKEN"] = "must-not-reach-runtime"
        return self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-scan",
                "--run",
                run_dir,
                "--tool",
                tool,
                "--execute",
                "--sandbox-profile",
                "container",
                "--json",
            ],
            env=env,
        )

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

    def test_execute_offline_adapters_in_read_only_container(self) -> None:
        for tool in ("gitleaks", "syft"):
            with self.subTest(tool=tool):
                run_dir = self.copy_fixture_run("minimal-run")
                cp = self.execute_scanner(run_dir, tool)
                self.assertEqual(0, cp.returncode, cp.stderr)
                result = json.loads(cp.stdout)
                self.assertEqual("execute", result["mode"])
                self.assertTrue(result["scanner_executed"])
                self.assertFalse(result["network_accessed"])
                self.assertEqual("review-only", result["finding_status"])
                raw = run_dir / result["raw_output_path"]
                self.assertTrue(raw.is_file())
                runtime = json.loads((self.work_dir / f"{tool}-success-runtime.json").read_text(encoding="utf-8"))
                self.assertIn("--network=none", runtime["args"])
                self.assertIn("--read-only", runtime["args"])
                self.assertIn("--pull=never", runtime["args"])
                self.assertNotIn("--user", runtime["args"])
                self.assertIn("/tmp:rw,noexec,nosuid,nodev,size=67108864", runtime["args"])
                self.assertTrue(any("dst=/target,readonly" in value for value in runtime["args"]))
                self.assertTrue(any("@sha256:" in value for value in runtime["args"]))
                self.assertFalse(runtime["secret_visible"])

    def test_execute_fails_closed_for_missing_image_nonzero_and_unsafe_output(self) -> None:
        for mode in ("missing-image", "nonzero", "partial-error", "symlink-output", "too-many-results", "invalid-output"):
            with self.subTest(mode=mode):
                run_dir = self.copy_fixture_run("minimal-run")
                cp = self.execute_scanner(run_dir, "gitleaks", mode=mode)
                self.assertNotEqual(0, cp.returncode)
                self.assertFalse((run_dir / "reports" / "scanner-results" / "raw" / "gitleaks.json").exists())
                if cp.returncode == 1:
                    result = json.loads(cp.stdout)
                    self.assertIsNone(result["raw_output_path"])

    def test_gitleaks_findings_exit_is_successful_review_only_evidence(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.execute_scanner(run_dir, "gitleaks", mode="leads")
        self.assertEqual(0, cp.returncode, cp.stderr)
        result = json.loads(cp.stdout)
        self.assertEqual("completed-with-leads", result["status"])
        self.assertEqual(10, result["exit_code"])
        self.assertEqual(1, result["result_count"])
        self.assertEqual("review-only", result["finding_status"])

    def test_execute_enforces_timeout_and_output_limit(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.write_container_runtime(mode="timeout")
        (run_dir / "repo").mkdir()
        env = self.env.copy()
        with mock.patch.dict(ADAPTERS, {"gitleaks": dataclasses.replace(ADAPTERS["gitleaks"], timeout_seconds=1)}):
            timeout_result = execute_scan(
                run_dir,
                adapter_id="gitleaks",
                sandbox_profile="container",
                path_env=env["PATH"],
                env=env,
            )
        self.assertEqual("timeout", timeout_result["status"])
        self.assertIsNone(timeout_result["raw_output_path"])

        run_dir = self.copy_fixture_run("minimal-run")
        cp_oversized = self.execute_scanner(run_dir, "gitleaks", mode="oversized")
        self.assertEqual(1, cp_oversized.returncode, cp_oversized.stderr)
        self.assertEqual("output-limit-exceeded", json.loads(cp_oversized.stdout)["status"])

        run_dir = self.copy_fixture_run("minimal-run")
        cp_log = self.execute_scanner(run_dir, "gitleaks", mode="oversized-log")
        self.assertEqual(1, cp_log.returncode, cp_log.stderr)
        self.assertEqual("log-limit-exceeded", json.loads(cp_log.stdout)["status"])

    def test_execute_rejects_network_and_non_enforced_profiles(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        self.write_container_runtime()
        cp_network = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-scan",
                "--run",
                run_dir,
                "--tool",
                "gitleaks",
                "--execute",
                "--network-policy",
                "explicit-allow",
            ]
        )
        self.assertEqual(2, cp_network.returncode)
        self.assertIn("offline-only", cp_network.stderr)
        cp_vm = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-scan",
                "--run",
                run_dir,
                "--tool",
                "syft",
                "--execute",
                "--sandbox-profile",
                "vm",
            ]
        )
        self.assertEqual(2, cp_vm.returncode)
        self.assertIn("container or gvisor", cp_vm.stderr)

    def test_execute_rejects_overlapping_target_and_reports_paths(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        context_path = run_dir / "context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        (run_dir / "repo").mkdir()
        context["reports_dir"] = "repo/reports"
        context_path.write_text(json.dumps(context) + "\n", encoding="utf-8")
        self.write_container_runtime()
        cp = self.run_cmd(
            [REPO_ROOT / "bin" / "gra-scan", "--run", run_dir, "--tool", "gitleaks", "--execute"]
        )
        self.assertEqual(2, cp.returncode)
        self.assertIn("must not overlap", cp.stderr)

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

from __future__ import annotations

try:
    from .support import *  # noqa: F401,F403
except ImportError:
    from support import *  # noqa: F401,F403


class BatchWorkflowTests(CliWorkflowTestCase):
    def test_gra_batch_runs_multiple_repositories_with_mock_commands(self) -> None:
        repo_list = self.work_dir / "repos.txt"
        repo_list.write_text("example/one\n# comment\n\nexample/two\n", encoding="utf-8")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                repo_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-ok",
                "--concurrency",
                "1",
            ],
            check=True,
        )
        self.assertIn("Batch complete", cp.stdout)
        batch_dir = self.runs_dir / "_batches" / "batch-ok"
        self.assertTrue((batch_dir / "logs" / "example__one.log").exists())
        self.assertTrue((batch_dir / "logs" / "example__two.log").exists())
        self.assertEqual(json.loads((batch_dir / "batch.json").read_text(encoding="utf-8"))["count"], 2)
        results = json.loads((batch_dir / "batch-results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["succeeded"], 2)
        self.assertEqual(results["failed"], 0)
        self.assertEqual([item["status"] for item in results["results"]], [0, 0])

    def test_gra_batch_exits_nonzero_and_records_failures_by_default(self) -> None:
        repo_list = self.work_dir / "repos-fail.txt"
        repo_list.write_text("example/ok\nexample/clone-fail\n", encoding="utf-8")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                repo_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-fail",
                "--concurrency",
                "1",
            ]
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("Failures: 1", cp.stdout)
        batch_dir = self.runs_dir / "_batches" / "batch-fail"
        results = json.loads((batch_dir / "batch-results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["succeeded"], 1)
        self.assertEqual(results["failed"], 1)
        by_repo = {item["repo"]: item for item in results["results"]}
        self.assertEqual(by_repo["example/ok"]["status"], 0)
        self.assertEqual(by_repo["example/clone-fail"]["status"], 1)

        cp_concurrent = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                repo_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-fail-concurrent",
                "--concurrency",
                "2",
            ]
        )
        self.assertNotEqual(cp_concurrent.returncode, 0)
        concurrent_results = json.loads((self.runs_dir / "_batches" / "batch-fail-concurrent" / "batch-results.json").read_text(encoding="utf-8"))
        self.assertEqual(concurrent_results["succeeded"], 1)
        self.assertEqual(concurrent_results["failed"], 1)

    def test_gra_batch_concurrent_continues_after_status_255(self) -> None:
        repo_list = self.work_dir / "repos-status-255.txt"
        repo_list.write_text("example/one\nexample/two\nexample/three\n", encoding="utf-8")
        env = self.env.copy()
        env["GRA_MOCK_CODEX_MODE"] = "fail"
        env["GRA_MOCK_CODEX_STATUS"] = "255"
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                repo_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-status-255",
                "--concurrency",
                "2",
            ],
            env=env,
        )
        self.assertNotEqual(cp.returncode, 0)
        results = json.loads((self.runs_dir / "_batches" / "batch-status-255" / "batch-results.json").read_text(encoding="utf-8"))
        self.assertEqual(results["failed"], 3)
        self.assertEqual([item["status"] for item in results["results"]], [255, 255, 255])

    def test_gra_batch_allow_failures_and_fail_fast_modes(self) -> None:
        repo_list = self.work_dir / "repos-allow.txt"
        repo_list.write_text("example/ok\nexample/clone-fail\n", encoding="utf-8")
        cp_allowed = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                repo_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-allow",
                "--allow-failures",
            ],
            check=True,
        )
        self.assertIn("Failures: 1", cp_allowed.stdout)
        allow_results = json.loads((self.runs_dir / "_batches" / "batch-allow" / "batch-results.json").read_text(encoding="utf-8"))
        self.assertTrue(allow_results["allow_failures"])
        self.assertEqual(allow_results["failed"], 1)

        fail_fast_list = self.work_dir / "repos-fail-fast.txt"
        fail_fast_list.write_text("example/clone-fail\nexample/not-run\n", encoding="utf-8")
        cp_fail_fast = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-batch",
                "--repo-list",
                fail_fast_list,
                "--mode",
                "exec",
                "--runs-dir",
                self.runs_dir,
                "--batch-id",
                "batch-fail-fast",
                "--fail-fast",
            ]
        )
        self.assertNotEqual(cp_fail_fast.returncode, 0)
        self.assertIn("Fail-fast stopping after failed audit", cp_fail_fast.stderr)
        fail_fast_results = json.loads((self.runs_dir / "_batches" / "batch-fail-fast" / "batch-results.json").read_text(encoding="utf-8"))
        self.assertTrue(fail_fast_results["fail_fast"])
        self.assertEqual(fail_fast_results["failed"], 1)
        self.assertEqual(fail_fast_results["not_run"], 1)
        self.assertEqual(fail_fast_results["results"][1]["status_text"], "not-run")

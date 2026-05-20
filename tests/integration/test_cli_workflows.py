from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import List, Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
FIXTURE_FINGERPRINT = "0123456789abcdef01234567"
sys.path.insert(0, str(REPO_ROOT / "lib"))
from gralib import env_from_context  # noqa: E402


class CliWorkflowTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))
        self.runs_dir = self.work_dir / "runs"
        self.mock_bin = self.work_dir / "bin"
        self.mock_bin.mkdir()
        self.fixture_counter = 0
        self._write_mock_gh()
        self._write_mock_codex()
        self.env = os.environ.copy()
        self.env.update(
            {
                "PATH": f"{self.mock_bin}{os.pathsep}{self.env.get('PATH', '')}",
                "GENAI_REPO_AUDITOR_RUNS_DIR": str(self.runs_dir),
                "GRA_MOCK_FIXTURE_DIR": str(FIXTURES / "minimal-run"),
                "PYTHONUNBUFFERED": "1",
            }
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        try:
            self.tmp_parent.rmdir()
        except OSError:
            pass

    def run_cmd(
        self,
        args: List[Union[str, Path]],
        *,
        env: Optional[dict] = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        cmd = [str(arg) for arg in args]
        cp = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env if env is not None else self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
        if check and cp.returncode != 0:
            self.fail(
                "command failed\n"
                f"cmd: {' '.join(cmd)}\n"
                f"exit: {cp.returncode}\n"
                f"stdout:\n{cp.stdout}\n"
                f"stderr:\n{cp.stderr}"
            )
        return cp

    def copy_fixture_run(self, fixture_name: str = "minimal-run") -> Path:
        self.fixture_counter += 1
        dst = self.work_dir / f"{fixture_name}-{self.fixture_counter}"
        shutil.copytree(FIXTURES / fixture_name, dst)
        return dst

    def env_with_gh_log(self, **overrides: str) -> tuple[dict, Path]:
        log_path = self.work_dir / f"gh-calls-{self.fixture_counter + 1}.jsonl"
        env = self.env.copy()
        env["GRA_MOCK_GH_LOG"] = str(log_path)
        env.update(overrides)
        return env, log_path

    def env_with_codex_log(self, **overrides: str) -> tuple[dict, Path]:
        log_path = self.work_dir / f"codex-calls-{self.fixture_counter + 1}.jsonl"
        env = self.env.copy()
        env["GRA_MOCK_CODEX_LOG"] = str(log_path)
        env.update(overrides)
        return env, log_path

    def read_jsonl_calls(self, log_path: Path) -> list[list[str]]:
        if not log_path.exists():
            return []
        return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def read_gh_calls(self, log_path: Path) -> list[list[str]]:
        return self.read_jsonl_calls(log_path)

    def read_codex_calls(self, log_path: Path) -> list[list[str]]:
        return self.read_jsonl_calls(log_path)

    def target_by_id(self, run_dir: Path, target_id: str) -> dict:
        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))["targets"]
        for target in targets:
            if target.get("id") == target_id:
                return target
        raise AssertionError(f"target {target_id!r} not found: {targets!r}")

    def assert_gh_called(self, calls: list[list[str]], prefix: list[str]) -> None:
        if not any(call[: len(prefix)] == prefix for call in calls):
            self.fail(f"expected gh call prefix {prefix!r}; observed calls: {calls!r}")

    def assert_gh_not_called(self, calls: list[list[str]], prefix: list[str]) -> None:
        if any(call[: len(prefix)] == prefix for call in calls):
            self.fail(f"unexpected gh call prefix {prefix!r}; observed calls: {calls!r}")

    def _write_executable(self, name: str, content: str) -> None:
        path = self.mock_bin / name
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _write_mock_gh(self) -> None:
        self._write_executable(
            "gh",
            r'''
            #!/usr/bin/env python3
            from __future__ import annotations

            import json
            import os
            import subprocess
            import sys
            from pathlib import Path

            DEVNULL = subprocess.DEVNULL

            def record_call(args) -> None:
                log_path = os.environ.get("GRA_MOCK_GH_LOG")
                if not log_path:
                    return
                path = Path(log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(args) + "\n")

            def init_repo(dest: Path, repo: str) -> None:
                dest.mkdir(parents=True, exist_ok=True)
                if (dest / ".git").exists():
                    return
                subprocess.run(["git", "init", str(dest)], check=True, stdout=DEVNULL, stderr=DEVNULL)
                subprocess.run(["git", "-C", str(dest), "checkout", "-b", "main"], check=True, stdout=DEVNULL, stderr=DEVNULL)
                subprocess.run(["git", "-C", str(dest), "config", "user.email", "fixture@example.invalid"], check=True)
                subprocess.run(["git", "-C", str(dest), "config", "user.name", "Fixture User"], check=True)
                subprocess.run(["git", "-C", str(dest), "config", "commit.gpgsign", "false"], check=True)
                (dest / "README.md").write_text(f"# {repo}\n", encoding="utf-8")
                (dest / "app.py").write_text("print('fixture')\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(dest), "add", "README.md", "app.py"], check=True, stdout=DEVNULL, stderr=DEVNULL)
                subprocess.run(["git", "-C", str(dest), "-c", "commit.gpgsign=false", "commit", "-m", "init"], check=True, stdout=DEVNULL)

            def main() -> int:
                args = sys.argv[1:]
                record_call(args)
                if len(args) >= 4 and args[:2] == ["repo", "clone"]:
                    repo = args[2]
                    dest = Path(args[3])
                    if "clone-fail" in repo:
                        print(f"mock clone failure for {repo}", file=sys.stderr)
                        return 1
                    init_repo(dest, repo)
                    return 0
                if len(args) >= 3 and args[:2] == ["repo", "view"]:
                    print(os.environ.get("GRA_MOCK_GH_VISIBILITY", "PRIVATE"))
                    return 0
                if len(args) >= 2 and args[:2] == ["issue", "list"]:
                    existing_url = os.environ.get("GRA_MOCK_EXISTING_ISSUE_URL", "")
                    if "--jq" in args:
                        print(existing_url)
                    else:
                        if existing_url:
                            print(json.dumps([{"url": existing_url}]))
                        else:
                            print("[]")
                    return 0
                if len(args) >= 2 and args[:2] == ["issue", "create"]:
                    print(os.environ.get("GRA_MOCK_ISSUE_URL", "https://github.example.invalid/example/demo/issues/1"))
                    return 0
                if len(args) >= 2 and args[:2] == ["label", "create"]:
                    return 0
                print(f"mock gh: unsupported arguments: {args}", file=sys.stderr)
                return 2

            if __name__ == "__main__":
                raise SystemExit(main())
            ''',
        )

    def _write_mock_codex(self) -> None:
        self._write_executable(
            "codex",
            r'''
            #!/usr/bin/env python3
            from __future__ import annotations

            import json
            import os
            import shutil
            import sys
            from pathlib import Path

            def record_call(args) -> None:
                log_path = os.environ.get("GRA_MOCK_CODEX_LOG")
                if not log_path:
                    return
                path = Path(log_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(args) + "\n")

            def arg_value(args, name):
                if name not in args:
                    return None
                idx = args.index(name)
                if idx + 1 >= len(args):
                    return None
                return args[idx + 1]

            def load_json(path: Path, default):
                if not path.exists():
                    return default
                return json.loads(path.read_text(encoding="utf-8"))

            def write_json(path: Path, data) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            def copy_fixture_reports(run_dir: Path, fixture_dir: Path) -> None:
                ctx = load_json(run_dir / "context.json", {})
                reports = run_dir / "reports"
                reports.mkdir(parents=True, exist_ok=True)
                findings = load_json(fixture_dir / "reports" / "findings.json", {})
                findings.update(
                    {
                        "run_id": ctx.get("run_id", run_dir.name),
                        "repo": ctx.get("repo", findings.get("repo", "")),
                        "commit": ctx.get("commit", findings.get("commit", "")),
                    }
                )
                write_json(reports / "findings.json", findings)
                targets_src = fixture_dir / "reports" / "targets.json"
                if targets_src.exists():
                    targets = load_json(targets_src, {})
                    targets.update(
                        {
                            "run_id": ctx.get("run_id", run_dir.name),
                            "repo": ctx.get("repo", targets.get("repo", "")),
                            "branch": ctx.get("branch", targets.get("branch", "")),
                            "commit": ctx.get("commit", targets.get("commit", "")),
                        }
                    )
                    write_json(reports / "targets.json", targets)
                drafts_src = fixture_dir / "reports" / "issue-drafts"
                if drafts_src.exists():
                    drafts_dest = reports / "issue-drafts"
                    drafts_dest.mkdir(parents=True, exist_ok=True)
                    for src in drafts_src.iterdir():
                        if src.is_file():
                            shutil.copy2(src, drafts_dest / src.name)
                (reports / "FINDINGS.md").write_text("# Fixture findings\n", encoding="utf-8")

            def main() -> int:
                args = sys.argv[1:]
                record_call(args)
                run_dir = Path(arg_value(args, "--cd") or os.getcwd())
                output_last = Path(arg_value(args, "--output-last-message") or (run_dir / "codex-final.md"))
                fixture_dir = Path(os.environ.get("GRA_MOCK_FIXTURE_DIR", ""))
                mode = os.environ.get("GRA_MOCK_CODEX_MODE", "success")

                output_last.parent.mkdir(parents=True, exist_ok=True)
                output_last.write_text(f"mock codex mode={mode}\n", encoding="utf-8")

                if mode == "fail":
                    print(json.dumps({"event": "mock", "status": "failed"}))
                    return int(os.environ.get("GRA_MOCK_CODEX_STATUS", "42"))
                if mode == "missing-findings":
                    print(json.dumps({"event": "mock", "status": "ok", "run_dir": str(run_dir)}))
                    return 0

                if fixture_dir.exists():
                    copy_fixture_reports(run_dir, fixture_dir)
                print(json.dumps({"event": "mock", "status": "ok", "run_dir": str(run_dir)}))
                return 0

            if __name__ == "__main__":
                raise SystemExit(main())
            ''',
        )

    def test_gra_audit_prepare_creates_run_context_and_prompts(self) -> None:
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-audit",
                "--repo",
                "example/demo",
                "--mode",
                "prepare",
                "--run-id",
                "prepare-run",
                "--runs-dir",
                self.runs_dir,
                "--no-lock",
            ],
            check=True,
        )
        run_dir = self.runs_dir / "example__demo" / "prepare-run"
        self.assertIn("Prepared audit run directory", cp.stdout)
        self.assertTrue((run_dir / "context.json").exists())
        self.assertTrue((run_dir / "prompts" / "exec" / "full-audit.prompt.md").exists())
        self.assertTrue((run_dir / "reports" / "issue-drafts").is_dir())
        ctx = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
        self.assertEqual(ctx["repo"], "example/demo")
        self.assertEqual(ctx["repo_slug"], "example__demo")
        self.assertEqual(ctx["visibility"], "PRIVATE")

    def test_render_template_uses_allowlist_and_rejects_unknown_or_secret_placeholders(self) -> None:
        template = self.work_dir / "template.md"
        out = self.work_dir / "out.md"
        env = {
            "RUN_ID": "run-1",
            "REPO": "example/demo",
            "GRA_TEMPLATE_CUSTOM_VALUE": "controlled",
            "OPENAI_API_KEY": "fixture-value",
        }

        template.write_text("run={{RUN_ID}}\nrepo={{REPO}}\ncustom={{CUSTOM_VALUE}}\n", encoding="utf-8")
        cp = self.run_cmd([sys.executable, REPO_ROOT / "lib" / "render_template.py", template, out], env=env, check=True)
        self.assertEqual(cp.stderr, "")
        self.assertEqual(out.read_text(encoding="utf-8"), "run=run-1\nrepo=example/demo\ncustom=controlled\n")
        self.assertNotIn("fixture-value", out.read_text(encoding="utf-8"))

        out.unlink()
        template.write_text("unknown={{UNKNOWN_PLACEHOLDER}}\n", encoding="utf-8")
        cp_unknown = self.run_cmd([sys.executable, REPO_ROOT / "lib" / "render_template.py", template, out], env=env)
        self.assertEqual(cp_unknown.returncode, 2)
        self.assertIn("unknown template placeholder: UNKNOWN_PLACEHOLDER", cp_unknown.stderr)
        self.assertFalse(out.exists())

        template.write_text("secret={{OPENAI_API_KEY}}\n", encoding="utf-8")
        cp_secret = self.run_cmd([sys.executable, REPO_ROOT / "lib" / "render_template.py", template, out], env=env)
        self.assertEqual(cp_secret.returncode, 2)
        self.assertIn("denied template placeholder: OPENAI_API_KEY", cp_secret.stderr)
        self.assertFalse(out.exists())

        controlled_secret_env = {"GRA_TEMPLATE_API_KEY": "fixture-value"}
        template.write_text("secret={{API_KEY}}\n", encoding="utf-8")
        cp_controlled_secret = self.run_cmd(
            [sys.executable, REPO_ROOT / "lib" / "render_template.py", template, out],
            env=controlled_secret_env,
        )
        self.assertEqual(cp_controlled_secret.returncode, 2)
        self.assertIn("denied controlled template placeholder: API_KEY", cp_controlled_secret.stderr)
        self.assertFalse(out.exists())

    def test_env_from_context_is_minimal_and_rejects_secret_like_extra_keys(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        original = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "fixture-value"
        try:
            env = env_from_context(run_dir, {"TARGET_ID": "TGT-001"})
        finally:
            if original is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original

        self.assertEqual(env["RUN_ID"], "fixture-run")
        self.assertEqual(env["TARGET_ID"], "TGT-001")
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("PATH", env)

        with self.assertRaisesRegex(ValueError, "denied template environment key: OPENAI_API_KEY"):
            env_from_context(run_dir, {"OPENAI_API_KEY": "fixture-value"})

    def test_gra_audit_exec_with_mock_codex_validates_reports(self) -> None:
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-audit",
                "--repo",
                "example/demo",
                "--mode",
                "exec",
                "--run-id",
                "exec-run",
                "--runs-dir",
                self.runs_dir,
                "--no-lock",
            ],
            check=True,
        )
        run_dir = self.runs_dir / "example__demo" / "exec-run"
        self.assertIn("Run complete. Codex status: 0", cp.stdout)
        self.assertTrue((run_dir / "reports" / "findings.json").exists())
        self.assertIn("OK:", (run_dir / "report-validation.txt").read_text(encoding="utf-8"))
        summary = (run_dir / "run-summary.txt").read_text(encoding="utf-8")
        self.assertIn("codex_status=0", summary)
        self.assertIn("validation_status=0", summary)
        self.assertIn("final_status=0", summary)

    def test_gra_audit_exec_fails_when_mock_codex_writes_invalid_findings(self) -> None:
        env = self.env.copy()
        env["GRA_MOCK_FIXTURE_DIR"] = str(FIXTURES / "invalid-findings-run")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-audit",
                "--repo",
                "example/demo",
                "--mode",
                "exec",
                "--run-id",
                "invalid-report-run",
                "--runs-dir",
                self.runs_dir,
                "--no-lock",
            ],
            env=env,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("Report validation failed", cp.stderr)
        run_dir = self.runs_dir / "example__demo" / "invalid-report-run"
        self.assertIn("invalid severity", (run_dir / "report-validation.txt").read_text(encoding="utf-8"))
        summary = (run_dir / "run-summary.txt").read_text(encoding="utf-8")
        self.assertIn("codex_status=0", summary)
        self.assertRegex(summary, r"validation_status=[1-9][0-9]*")
        self.assertRegex(summary, r"final_status=[1-9][0-9]*")

    def test_gra_audit_exec_fails_when_findings_missing_unless_allowed(self) -> None:
        env = self.env.copy()
        env["GRA_MOCK_CODEX_MODE"] = "missing-findings"
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-audit",
                "--repo",
                "example/demo",
                "--mode",
                "exec",
                "--run-id",
                "missing-report-run",
                "--runs-dir",
                self.runs_dir,
                "--no-lock",
            ],
            env=env,
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("findings.json was not produced", cp.stderr)
        run_dir = self.runs_dir / "example__demo" / "missing-report-run"
        summary = (run_dir / "run-summary.txt").read_text(encoding="utf-8")
        self.assertIn("validation_status=missing-findings-json", summary)
        self.assertIn("final_status=1", summary)

        cp_allowed = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-audit",
                "--repo",
                "example/demo",
                "--mode",
                "exec",
                "--run-id",
                "missing-report-allowed-run",
                "--runs-dir",
                self.runs_dir,
                "--no-lock",
                "--allow-invalid-report",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Final status: 0", cp_allowed.stdout)
        allowed_run_dir = self.runs_dir / "example__demo" / "missing-report-allowed-run"
        allowed_summary = (allowed_run_dir / "run-summary.txt").read_text(encoding="utf-8")
        self.assertIn("allow_invalid_report=1", allowed_summary)
        self.assertIn("final_status=0", allowed_summary)

    def test_gra_recon_exec_renders_prompt_and_writes_codex_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-recon",
                "--run",
                run_dir,
                "--model",
                "gpt-fixture",
                "--effort",
                "medium",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex recon for example/demo", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        prompt = run_dir / "prompts" / "exec" / "recon.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("Run ID: fixture-run", prompt_text)
        self.assertIn("Repository: example/demo", prompt_text)
        self.assertIn("Reports directory: reports/", prompt_text)
        self.assertNotIn("{{", prompt_text)

        final_path = run_dir / "codex-recon-final.md"
        events_path = run_dir / "codex-recon-events.jsonl"
        stderr_path = run_dir / "codex-recon-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())

        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(calls[0][:2], ["exec", "--cd"])
        self.assertIn(str(run_dir.resolve()), calls[0])
        self.assertIn(str(final_path), calls[0])
        self.assertIn('model_reasoning_effort="medium"', calls[0])
        self.assertIn("sandbox_workspace_write.network_access=false", calls[0])

    def test_gra_research_exec_marks_target_reviewed_and_writes_codex_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-research",
                "--run",
                run_dir,
                "--target",
                "TGT-001",
                "--mode",
                "exec",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex target research for TGT-001", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        target_json = run_dir / "reports" / "target-research" / "TGT-001.target.json"
        self.assertEqual(json.loads(target_json.read_text(encoding="utf-8"))["id"], "TGT-001")
        prompt = run_dir / "prompts" / "exec" / "research-TGT-001.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("Target ID: TGT-001", prompt_text)
        self.assertIn("Target file: reports/target-research/TGT-001.target.json", prompt_text)
        self.assertNotIn("{{", prompt_text)

        self.assertEqual(self.target_by_id(run_dir, "TGT-001")["status"], "reviewed")
        final_path = run_dir / "codex-research-TGT-001-final.md"
        events_path = run_dir / "codex-research-TGT-001-events.jsonl"
        stderr_path = run_dir / "codex-research-TGT-001-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())

        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])

    def test_gra_research_exec_failure_marks_target_needs_human_review(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log(
            GRA_MOCK_CODEX_MODE="fail",
            GRA_MOCK_CODEX_STATUS="42",
        )
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-research",
                "--run",
                run_dir,
                "--target",
                "TGT-001",
                "--mode",
                "exec",
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 42, cp.stderr)
        self.assertIn("Codex status: 42", cp.stdout)
        target = self.target_by_id(run_dir, "TGT-001")
        self.assertEqual(target["status"], "needs_human_review")
        self.assertNotEqual(target["status"], "reviewed")
        self.assertEqual(
            (run_dir / "codex-research-TGT-001-final.md").read_text(encoding="utf-8"),
            "mock codex mode=fail\n",
        )
        self.assertIn(
            '"status": "failed"',
            (run_dir / "codex-research-TGT-001-events.jsonl").read_text(encoding="utf-8"),
        )
        self.assertEqual(len(self.read_codex_calls(codex_log)), 1)

    def test_gra_research_goal_prepares_prompt_without_codex_exec(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-research",
                "--run",
                run_dir,
                "--target",
                "TGT-001",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal target research run.", cp.stdout)
        prompt = run_dir / "prompts" / "goal" / "research-TGT-001.goal.md"
        self.assertTrue(prompt.exists())
        self.assertTrue(prompt.read_text(encoding="utf-8").startswith("/goal "))
        self.assertEqual(self.target_by_id(run_dir, "TGT-001")["status"], "queued")
        self.assertEqual(self.read_codex_calls(codex_log), [])
        self.assertFalse((run_dir / "codex-research-TGT-001-final.md").exists())

    def test_gra_variant_exec_renders_seed_and_writes_codex_artifacts(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-variant",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--mode",
                "exec",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Running Codex variant analysis from SEC-001", cp.stdout)
        self.assertIn("Codex status: 0", cp.stdout)

        source = run_dir / "reports" / "variant-analysis" / "SEC-001.source.json"
        self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["id"], "SEC-001")
        prompt = run_dir / "prompts" / "exec" / "variant-SEC-001.prompt.md"
        prompt_text = prompt.read_text(encoding="utf-8")
        self.assertIn("Variant source: reports/variant-analysis/SEC-001.source.json", prompt_text)
        self.assertIn("Seed finding or source ID: SEC-001", prompt_text)
        self.assertNotIn("{{", prompt_text)

        final_path = run_dir / "codex-variant-SEC-001-final.md"
        events_path = run_dir / "codex-variant-SEC-001-events.jsonl"
        stderr_path = run_dir / "codex-variant-SEC-001-stderr.txt"
        self.assertEqual(final_path.read_text(encoding="utf-8"), "mock codex mode=success\n")
        self.assertIn('"status": "ok"', events_path.read_text(encoding="utf-8"))
        self.assertTrue(stderr_path.exists())
        calls = self.read_codex_calls(codex_log)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn(str(final_path), calls[0])

    def test_gra_variant_goal_prepares_prompt_without_codex_exec(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, codex_log = self.env_with_codex_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-variant",
                "--run",
                run_dir,
                "--finding",
                "SEC-001",
                "--mode",
                "goal",
            ],
            env=env,
            check=True,
        )
        self.assertIn("Prepared supervised /goal variant-analysis run.", cp.stdout)
        prompt = run_dir / "prompts" / "goal" / "variant-SEC-001.goal.md"
        self.assertTrue(prompt.exists())
        self.assertTrue(prompt.read_text(encoding="utf-8").startswith("/goal "))
        self.assertEqual(self.read_codex_calls(codex_log), [])
        self.assertFalse((run_dir / "codex-variant-SEC-001-final.md").exists())

    def test_validate_report_accepts_valid_fixture_and_rejects_invalid_fixtures(self) -> None:
        valid_run = self.copy_fixture_run("minimal-run")
        cp_valid = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", valid_run])
        self.assertEqual(cp_valid.returncode, 0, cp_valid.stderr)
        self.assertIn("Findings: 1", cp_valid.stdout)

        invalid_findings_run = self.copy_fixture_run("invalid-findings-run")
        cp_invalid_findings = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_findings_run])
        self.assertNotEqual(cp_invalid_findings.returncode, 0)
        self.assertIn("invalid severity", cp_invalid_findings.stderr)
        self.assertIn("issue_recommended must be boolean", cp_invalid_findings.stderr)

        invalid_targets_run = self.copy_fixture_run("invalid-targets-run")
        cp_invalid_targets = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", invalid_targets_run])
        self.assertNotEqual(cp_invalid_targets.returncode, 0)
        self.assertIn("target id must match", cp_invalid_targets.stderr)
        self.assertIn("priority must be integer", cp_invalid_targets.stderr)

        empty_run = self.copy_fixture_run("minimal-run")
        empty_findings_path = empty_run / "reports" / "findings.json"
        empty_findings = json.loads(empty_findings_path.read_text(encoding="utf-8"))
        empty_findings["findings"] = []
        empty_findings_path.write_text(json.dumps(empty_findings, indent=2) + "\n", encoding="utf-8")
        cp_empty = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", empty_run])
        self.assertEqual(cp_empty.returncode, 0, cp_empty.stderr)
        self.assertIn("Findings: 0", cp_empty.stdout)

    def test_validate_report_rejects_safety_invalid_fields(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        findings_path = run_dir / "reports" / "findings.json"
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        finding = data["findings"][0]
        finding["fingerprint"] = "fingerprint-001"
        finding["generated_at"] = "not-a-date"
        finding["affected_locations"][0]["file"] = "../secret.py"
        finding["affected_locations"][0]["line"] = 0
        finding["issue_body_file"] = "../../secret.md"
        finding.pop("public_disclosure_risk", None)
        data["generated_at"] = "not-a-date"
        data["evidence_secret_probe"] = "AKIA" + "ABCDEFGHIJKLMNOP"
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("findings.generated_at", cp.stderr)
        self.assertIn("fingerprint must not be a placeholder", cp.stderr)
        self.assertIn("affected_locations[0].file", cp.stderr)
        self.assertIn("line must be a positive integer", cp.stderr)
        self.assertIn("issue_body_file must not contain", cp.stderr)
        self.assertIn("public_disclosure_risk", cp.stderr)
        self.assertIn("obvious unredacted full secret value", cp.stderr)

    def test_validate_report_rejects_symlink_issue_body(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        draft_path = run_dir / "reports" / "issue-drafts" / "SEC-001.md"
        draft_path.unlink()
        outside = self.work_dir / "outside.md"
        outside.write_text("outside content\n", encoding="utf-8")
        draft_path.symlink_to(outside)
        cp = self.run_cmd([REPO_ROOT / "bin" / "gra-validate-report", "--run", run_dir])
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("issue_body_file must not be a symlink", cp.stderr)

    def test_gra_issues_dry_run_and_apply_use_safe_fixture_issue_body(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("DRY RUN: would create issue for SEC-001", cp.stdout)
        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["created"][0]["id"], "SEC-001")
        self.assertEqual(result["created"][0]["fingerprint"], FIXTURE_FINGERPRINT)

        apply_run = self.copy_fixture_run("minimal-run")
        cp_apply = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                apply_run,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            check=True,
        )
        self.assertIn("CREATED SEC-001", cp_apply.stdout)

    def test_gra_issues_apply_refuses_public_repo_without_allow_public(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, log_path = self.env_with_gh_log(GRA_MOCK_GH_VISIBILITY="PUBLIC")
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
        )
        self.assertEqual(cp.returncode, 3, cp.stderr)
        self.assertIn("Refusing to create security issues", cp.stderr)
        self.assertIn("visibility=PUBLIC", cp.stderr)
        self.assertIn("Use --allow-public only when disclosure policy permits", cp.stderr)
        self.assertFalse((run_dir / "issues-created.json").exists())

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_not_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_allow_public_apply_creates_issue_with_safe_fixture(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        issue_url = "https://github.example.invalid/example/demo/issues/41"
        env, log_path = self.env_with_gh_log(
            GRA_MOCK_GH_VISIBILITY="PUBLIC",
            GRA_MOCK_ISSUE_URL=issue_url,
        )
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--allow-public",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )
        self.assertIn(f"CREATED SEC-001: {issue_url}", cp.stdout)

        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["visibility"], "PUBLIC")
        self.assertEqual(result["created"], [
            {
                "id": "SEC-001",
                "url": issue_url,
                "title": "[Security][High] Fixture command injection finding",
                "fingerprint": FIXTURE_FINGERPRINT,
            }
        ])
        self.assertEqual(result["skipped"], [])

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "list"])
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_duplicate_fingerprint_skips_issue_creation(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        existing_url = "https://github.example.invalid/example/demo/issues/7"
        env, log_path = self.env_with_gh_log(GRA_MOCK_EXISTING_ISSUE_URL=existing_url)
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )
        self.assertIn(f"SKIP duplicate SEC-001: {existing_url}", cp.stdout)

        result = json.loads((run_dir / "issues-created.json").read_text(encoding="utf-8"))
        self.assertEqual(result["created"], [])
        self.assertEqual(result["skipped"], [
            {
                "id": "SEC-001",
                "reason": "duplicate",
                "url": existing_url,
                "fingerprint": FIXTURE_FINGERPRINT,
            }
        ])

        calls = self.read_gh_calls(log_path)
        self.assert_gh_called(calls, ["repo", "view"])
        self.assert_gh_called(calls, ["issue", "list"])
        self.assert_gh_not_called(calls, ["issue", "create"])

    def test_gra_issues_create_labels_uses_mocked_gh_label_updates(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        env, log_path = self.env_with_gh_log()
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--apply",
                "--create-labels",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ],
            env=env,
            check=True,
        )
        self.assertIn("CREATED SEC-001", cp.stdout)

        calls = self.read_gh_calls(log_path)
        label_names = [
            call[2]
            for call in calls
            if len(call) >= 3 and call[:2] == ["label", "create"]
        ]
        self.assertIn("security", label_names)
        self.assertIn("genai-audit", label_names)
        self.assertIn("severity-high", label_names)
        self.assertIn("status-confirmed", label_names)
        self.assertIn("category-command-injection", label_names)
        self.assertIn("test-fixture", label_names)
        self.assertTrue(
            all("--force" in call for call in calls if len(call) >= 3 and call[:2] == ["label", "create"]),
            f"label create calls must update existing labels with --force: {calls!r}",
        )
        self.assert_gh_called(calls, ["issue", "create"])

    def test_gra_issues_rejects_unsafe_issue_body_file_in_dry_run_and_apply(self) -> None:
        dry_run_dir = self.copy_fixture_run("minimal-run")
        dry_findings_path = dry_run_dir / "reports" / "findings.json"
        dry_data = json.loads(dry_findings_path.read_text(encoding="utf-8"))
        dry_data["findings"][0]["issue_body_file"] = "../../secret.md"
        dry_findings_path.write_text(json.dumps(dry_data, indent=2) + "\n", encoding="utf-8")
        cp_dry = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                dry_run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp_dry.returncode, 0)
        self.assertIn("issue_body_file must not contain", cp_dry.stderr)

        apply_run = self.copy_fixture_run("minimal-run")
        apply_findings_path = apply_run / "reports" / "findings.json"
        apply_data = json.loads(apply_findings_path.read_text(encoding="utf-8"))
        apply_data["findings"][0]["issue_body_file"] = "/etc/passwd"
        apply_findings_path.write_text(json.dumps(apply_data, indent=2) + "\n", encoding="utf-8")
        cp_apply = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                apply_run,
                "--apply",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp_apply.returncode, 0)
        self.assertIn("issue_body_file must be relative under reports/issue-drafts", cp_apply.stderr)

    def test_gra_issues_rejects_symlinked_reports_parent(self) -> None:
        run_dir = self.work_dir / "symlink-parent-run"
        run_dir.mkdir()
        outside_reports = self.work_dir / "outside-reports"
        shutil.copytree(FIXTURES / "minimal-run" / "reports", outside_reports)
        (run_dir / "reports").symlink_to(outside_reports, target_is_directory=True)
        cp = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-issues",
                "--run",
                run_dir,
                "--dry-run",
                "--min-severity",
                "Low",
                "--statuses",
                "Confirmed",
            ]
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("issue_body_file must not be a symlink", cp.stderr)

    def test_gra_targets_list_show_and_mark(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        cp_list = self.run_cmd([REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--list"], check=True)
        self.assertIn("TGT-001", cp_list.stdout)
        cp_show = self.run_cmd([REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--show", "TGT-001"], check=True)
        self.assertEqual(json.loads(cp_show.stdout)["id"], "TGT-001")
        cp_mark = self.run_cmd([REPO_ROOT / "bin" / "gra-targets", "--run", run_dir, "--mark", "TGT-001", "reviewed"], check=True)
        self.assertIn("updated TGT-001 -> reviewed", cp_mark.stdout)
        targets = json.loads((run_dir / "reports" / "targets.json").read_text(encoding="utf-8"))["targets"]
        self.assertEqual(targets[0]["status"], "reviewed")

    def test_ingest_scanner_triage_dashboard_sarif_and_store(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        scanner_file = self.work_dir / "semgrep.json"
        scanner_file.write_text('{"results": [{"check_id": "fixture.rule"}]}\n', encoding="utf-8")

        cp_ingest = self.run_cmd(
            [
                REPO_ROOT / "bin" / "gra-ingest",
                "--run",
                run_dir,
                "--tool",
                "semgrep",
                "--file",
                scanner_file,
                "--format",
                "json",
                "--note",
                "fixture",
            ],
            check=True,
        )
        self.assertIn("Ingested", cp_ingest.stdout)
        index_path = run_dir / "reports" / "scanner-results" / "scanner-index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(index["results"][0]["tool"], "semgrep")
        normalized_path = run_dir / index["results"][0]["normalized_path"]
        self.assertTrue(normalized_path.exists())
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        self.assertEqual(index["results"][0]["normalized_leads_count"], len(normalized["leads"]))

        cp_triage = self.run_cmd([REPO_ROOT / "bin" / "gra-scanner-triage", "--run", run_dir], check=True)
        self.assertIn("Codex status: 0", cp_triage.stdout)
        triage_prompt = run_dir / "prompts" / "exec" / "scanner-triage.prompt.md"
        self.assertIn("reports/scanner-results/scanner-index.json", triage_prompt.read_text(encoding="utf-8"))
        self.assertIn("Normalized lead files", triage_prompt.read_text(encoding="utf-8"))

        cp_dashboard = self.run_cmd([REPO_ROOT / "bin" / "gra-dashboard", "--run", run_dir], check=True)
        self.assertIn("dashboard.html", cp_dashboard.stdout)
        self.assertTrue((run_dir / "reports" / "dashboard.html").exists())

        cp_sarif = self.run_cmd([REPO_ROOT / "bin" / "gra-sarif", "--run", run_dir], check=True)
        self.assertIn("findings.sarif", cp_sarif.stdout)
        sarif = json.loads((run_dir / "reports" / "findings.sarif").read_text(encoding="utf-8"))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["ruleId"], "SEC-001")

        db_path = self.work_dir / "audit.sqlite"
        cp_store = self.run_cmd([REPO_ROOT / "bin" / "gra-store", "--run", run_dir, "--db", db_path], check=True)
        self.assertIn("Imported run", cp_store.stdout)
        with sqlite3.connect(db_path) as conn:
            count = conn.execute("select count(*) from findings").fetchone()[0]
        self.assertEqual(count, 1)

    def test_gra_ingest_normalizes_and_redacts_secret_scanner_outputs(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        stripe_secret = "sk_live_1234567890abcdef"
        aws_secret = "AKIA" + "ABCDEFGHIJKLMNOP"
        gitleaks_file = self.work_dir / "gitleaks.json"
        gitleaks_file.write_text(
            json.dumps(
                [
                    {
                        "RuleID": "generic-api-key",
                        "Description": "Stripe key",
                        "File": "src/config.ts",
                        "StartLine": 42,
                        "Secret": stripe_secret,
                    }
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        trufflehog_file = self.work_dir / "trufflehog.json"
        trufflehog_file.write_text(
            json.dumps(
                {
                    "DetectorName": "AWS",
                    "Raw": aws_secret,
                    "SourceMetadata": {"Data": {"Git": {"file": "settings.py", "line": 7}}},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "gitleaks", "--file", gitleaks_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "trufflehog", "--file", trufflehog_file], check=True)

        index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        self.assertEqual(len(index["results"]), 2)
        index_text = json.dumps(index)
        self.assertNotIn(stripe_secret, index_text)
        self.assertNotIn(aws_secret, index_text)
        for entry in index["results"]:
            normalized_path = run_dir / entry["normalized_path"]
            normalized_text = normalized_path.read_text(encoding="utf-8")
            self.assertNotIn(stripe_secret, normalized_text)
            self.assertNotIn(aws_secret, normalized_text)
            normalized = json.loads(normalized_text)
            self.assertGreaterEqual(entry["normalized_leads_count"], 1)
            self.assertEqual(normalized["leads"][0]["raw_result_ref"], entry["path"])
        all_normalized = "\n".join((run_dir / entry["normalized_path"]).read_text(encoding="utf-8") for entry in index["results"])
        self.assertIn("sk_live_...cdef", all_normalized)
        self.assertIn("AKIA...MNOP", all_normalized)

    def test_gra_ingest_handles_generic_secret_large_json_and_sarif_locations(self) -> None:
        run_dir = self.copy_fixture_run("minimal-run")
        generic_secret = "correcthorsebatterystaple"
        aws_secret_access_key = "wJalrXUtnFEMI/" + "K7MDENG/bPxRfiCY" + "1234567890"
        temp_aws_id = "ASIA" + "ABCDEFGHIJKLMNOP"
        generic_file = self.work_dir / "generic-secret.json"
        generic_file.write_text(json.dumps([{"RuleID": "generic-password", "File": "config.env", "StartLine": 3, "Raw": generic_secret}]) + "\n", encoding="utf-8")

        large_file = self.work_dir / "large-semgrep.json"
        large_file.write_text(
            json.dumps(
                {
                    "results": [
                        {"check_id": f"rule-{i}", "path": f"src/file{i}.py", "start": {"line": i + 1}, "extra": {"message": "x" * 25000}}
                        for i in range(3)
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )

        sarif_file = self.work_dir / "codeql.sarif"
        sarif_file.write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "results": [
                                {
                                    "ruleId": "py/test-rule",
                                    "level": "warning",
                                    "message": {"text": "example"},
                                    "locations": [
                                        {
                                            "physicalLocation": {
                                                "artifactLocation": {"uri": "src/main.py"},
                                                "region": {"startLine": 12},
                                            }
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
            )
            + "\n",
            encoding="utf-8",
        )
        jsonl_file = self.work_dir / "trufflehog.jsonl"
        jsonl_file.write_text(
            "\n".join(
                [
                    json.dumps({"DetectorName": "generic", "Raw": generic_secret, "SourceMetadata": {"Data": {"Git": {"file": "a.env", "line": 1}}}}),
                    json.dumps({"DetectorName": "aws-secret", "Raw": aws_secret_access_key, "SourceMetadata": {"Data": {"Git": {"file": "b.env", "line": 2}}}}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        private_key_file = self.work_dir / "private-key.txt"
        private_key_file.write_text("-----BEGIN PRIVATE KEY-----\nABCDEF1234567890\n", encoding="utf-8")
        temp_aws_file = self.work_dir / "temp-aws.json"
        temp_aws_file.write_text(json.dumps([{"RuleID": "temp-aws", "File": "aws.env", "StartLine": 4, "Secret": temp_aws_id}]) + "\n", encoding="utf-8")

        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "custom", "--file", generic_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "semgrep", "--file", large_file], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "codeql", "--file", sarif_file, "--format", "sarif"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "trufflehog", "--file", jsonl_file, "--format", "jsonl"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "privatekey", "--file", private_key_file, "--format", "text"], check=True)
        self.run_cmd([REPO_ROOT / "bin" / "gra-ingest", "--run", run_dir, "--tool", "gitleaks", "--file", temp_aws_file], check=True)

        index = json.loads((run_dir / "reports" / "scanner-results" / "scanner-index.json").read_text(encoding="utf-8"))
        by_tool = {entry["tool"]: json.loads((run_dir / entry["normalized_path"]).read_text(encoding="utf-8")) for entry in index["results"]}
        all_text = "\n".join(json.dumps(value) for value in by_tool.values())
        self.assertNotIn(generic_secret, all_text)
        self.assertNotIn(aws_secret_access_key, all_text)
        self.assertNotIn(temp_aws_id, all_text)
        self.assertNotIn("ABCDEF1234567890", all_text)
        self.assertIn("<REDACTED:scanner-secret>", all_text)
        self.assertIn("<REDACTED:private-key>", all_text)
        self.assertIn("ASIA...MNOP", all_text)
        self.assertEqual(len(by_tool["semgrep"]["leads"]), 3)
        self.assertEqual(by_tool["semgrep"]["leads"][0]["line"], 1)
        self.assertFalse(by_tool["semgrep"]["normalization"]["parse_error"])
        self.assertEqual(len(by_tool["trufflehog"]["leads"]), 2)
        sarif_lead = by_tool["codeql"]["leads"][0]
        self.assertEqual(sarif_lead["path"], "src/main.py")
        self.assertEqual(sarif_lead["line"], 12)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

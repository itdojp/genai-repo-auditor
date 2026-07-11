from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def extract_block(text: str, header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line == header:
            base_indent = len(line) - len(line.lstrip(" "))
            body = []
            for child in lines[index + 1:]:
                if child.strip():
                    child_indent = len(child) - len(child.lstrip(" "))
                    if child_indent <= base_indent:
                        break
                body.append(child)
            return "\n".join(body)
    raise AssertionError(f"missing structured block header: {header}")


def parse_mapping(block: str, indent: int) -> dict[str, str]:
    prefix = " " * indent
    result = {}
    for line in block.splitlines():
        if not line.startswith(prefix) or line.startswith(prefix + " "):
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        value = value.strip()
        if value:
            result[key] = value
    return result


def parse_keys(block: str, indent: int) -> set[str]:
    prefix = " " * indent
    result = set()
    for line in block.splitlines():
        if not line.startswith(prefix) or line.startswith(prefix + " "):
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _value = stripped.split(":", 1)
        result.add(key)
    return result


def workflow_triggers(workflow: str) -> set[str]:
    return parse_keys(extract_block(workflow, "on:"), 2)


def parse_list_items(block: str, indent: int) -> list[str]:
    prefix = " " * indent + "- "
    result = []
    for line in block.splitlines():
        if line.startswith(prefix):
            result.append(line[len(prefix):].strip())
    return result


def push_branches(workflow: str) -> list[str]:
    push = extract_block(extract_block(workflow, "on:"), "  push:")
    inline_branches = parse_mapping(push, 4).get("branches")
    if inline_branches:
        return [item.strip() for item in inline_branches.removeprefix("[").removesuffix("]").split(",") if item.strip()]
    branches_block = extract_block(push, "    branches:")
    branches = parse_list_items(branches_block, 6)
    if not branches:
        raise AssertionError("missing push.branches trigger")
    return branches


def schedule_block(workflow: str) -> str:
    return extract_block(extract_block(workflow, "on:"), "  schedule:")


def cron_entries(workflow: str) -> list[str]:
    result = []
    for line in schedule_block(workflow).splitlines():
        stripped = line.strip()
        if not stripped.startswith("- cron:"):
            continue
        value = stripped.split(":", 1)[1].strip().strip("'\"")
        if value:
            result.append(value)
    return result


def job_block(workflow: str, job_name: str) -> str:
    return extract_block(extract_block(workflow, "jobs:"), f"  {job_name}:")


def job_permissions(workflow: str, job_name: str) -> dict[str, str]:
    return parse_mapping(extract_block(job_block(workflow, job_name), "    permissions:"), 6)


def checkout_step(job: str) -> str:
    lines = job.splitlines()
    checkout_uses = re.compile(r"^-?\s*uses: actions/checkout@v[0-9]+$")
    for index, line in enumerate(lines):
        if checkout_uses.match(line.strip()):
            start = index
            while start > 0 and not lines[start].startswith("      - "):
                start -= 1
            end = index + 1
            while end < len(lines):
                if lines[end].startswith("      - "):
                    break
                end += 1
            return "\n".join(lines[start:end])
    raise AssertionError("missing actions/checkout step")


class WorkflowHardeningTests(unittest.TestCase):
    def assert_top_level_permissions_disabled(self, text: str) -> None:
        self.assertRegex(text, re.compile(r"^permissions: \{\}$", re.MULTILINE))

    def assert_checkout_does_not_persist_credentials(self, job: str) -> None:
        step = checkout_step(job)
        self.assertIn("        with:", step)
        self.assertIn("          persist-credentials: false", step)

    def assert_required_workflow_triggers(self, text: str) -> None:
        required = {"pull_request", "push", "schedule", "workflow_dispatch"}
        self.assertTrue(required.issubset(workflow_triggers(text)))
        self.assertEqual(["main"], push_branches(text))
        self.assertTrue(cron_entries(text), "missing schedule cron trigger")

    def test_lint_workflow_uses_explicit_read_only_permissions(self) -> None:
        text = (WORKFLOWS / "lint.yml").read_text(encoding="utf-8")
        self.assertEqual({"contents": "read"}, parse_mapping(extract_block(text, "permissions:"), 2))
        lint = job_block(text, "lint")
        self.assertEqual({"contents": "read"}, job_permissions(text, "lint"))
        self.assert_checkout_does_not_persist_credentials(lint)
        self.assertIn("files += list(Path('src').rglob('*.py'))", lint)
        self.assertIn("- name: Build Python package metadata", lint)
        self.assertIn("          python3 -m pip install --upgrade build", lint)
        self.assertIn('          python3 -m build --outdir "$RUNNER_TEMP/gra-dist"', lint)
        self.assertIn('          python3 -m venv "$RUNNER_TEMP/gra-package-venv"', lint)
        self.assertIn('          "$RUNNER_TEMP/gra-package-venv/bin/python" -m pip install --no-index --find-links "$RUNNER_TEMP/gra-dist" genai-repo-auditor', lint)
        self.assertIn('          assert "share/genai-repo-auditor" in str(root), root', lint)
        self.assertIn('          assert Path(gra.resource_path("VERSION")).is_file()', lint)
        self.assertIn('          assert Path(gra.resource_path("bin", "gra-validate-report")).is_file()', lint)
        self.assertIn('          assert Path(gra.resource_path("lib", "version.py")).is_file()', lint)
        self.assertIn('          assert Path(gra.prompt_path("exec", "full-audit.prompt.md")).is_file()', lint)
        self.assertIn('          assert Path(gra.report_schema_path("findings.schema.json")).is_file()', lint)
        self.assertIn('          assert Path(gra.report_schema_path("efficacy-comparison.schema.json")).is_file()', lint)
        self.assertIn('          assert Path(gra.report_schema_path("efficacy-worker-response.schema.json")).is_file()', lint)
        self.assertIn('          assert Path(gra.taxonomy_path("owasp-llm-2025.json")).is_file()', lint)
        self.assertIn('          assert Path(gra.agent_worker_profile_path("codex-cli.json")).is_file()', lint)
        self.assertIn('          assert Path(gra.efficacy_corpus_path("core.json")).is_file()', lint)
        self.assertIn('          sys.path.insert(0, str(root / "lib"))', lint)
        self.assertIn('          from efficacy_corpus import load_corpus', lint)
        self.assertIn('          assert len(load_corpus(root)["cases"]) >= 8', lint)
        self.assertIn('          from genai_repo_auditor.cli import COMMANDS', lint)
        self.assertIn('          test "$count" = "36"', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/$command" --help >/dev/null)', lint)
        self.assertIn('          test "$output" = "$command $version"', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/gra-agent-check" --list --json >/dev/null)', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/gra-efficacy-benchmark" --out-json "$RUNNER_TEMP/gra-efficacy.json" --out-md "$RUNNER_TEMP/gra-efficacy.md" >/dev/null)', lint)
        self.assertIn('          test -s "$RUNNER_TEMP/gra-efficacy.json"', lint)
        self.assertIn('          test -s "$RUNNER_TEMP/gra-efficacy.md"', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/gra-efficacy-benchmark" --compare --out-json "$RUNNER_TEMP/gra-efficacy-comparison.json" --out-md "$RUNNER_TEMP/gra-efficacy-comparison.md" >/dev/null)', lint)
        self.assertIn('          test -s "$RUNNER_TEMP/gra-efficacy-comparison.json"', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/gra-doctor" --json --runs-dir "$RUNNER_TEMP/gra-doctor-runs" >/dev/null)', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && "$RUNNER_TEMP/gra-package-venv/bin/gra-validate-report" --run "$RUNNER_TEMP/gra-minimal-run" >/dev/null)', lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && PATH="$mock_bin:$PATH" "$RUNNER_TEMP/gra-package-venv/bin/gra-audit" --repo acme/api --mode prepare --runs-dir "$RUNNER_TEMP/gra-installed-runs" --run-id installed-prepare >/dev/null)', lint)
        self.assertIn('          test -f "$RUNNER_TEMP/gra-installed-runs/acme__api/installed-prepare/run-manifest.json"', lint)
        self.assertIn("          printf 'acme/api\\n' > \"$RUNNER_TEMP/gra-package-repos.txt\"", lint)
        self.assertIn('          (cd "$RUNNER_TEMP" && PATH="$mock_bin:$PATH" "$RUNNER_TEMP/gra-package-venv/bin/gra-batch" --repo-list "$RUNNER_TEMP/gra-package-repos.txt" --mode goal --runs-dir "$RUNNER_TEMP/gra-installed-batch-runs" --batch-id installed-batch >/dev/null)', lint)
        self.assertIn('          test -f "$RUNNER_TEMP/gra-installed-batch-runs/_batches/installed-batch/batch-results.json"', lint)
        self.assertIn("          rm -rf build src/*.egg-info", lint)
        self.assertIn("- name: Run local install smoke validation", lint)
        self.assertIn("        run: |\n          scripts/validate-install-smoke.sh", lint)
        self.assertIn("test -x scripts/validate-install-smoke.sh", lint)
        install_smoke = (REPO_ROOT / "scripts" / "validate-install-smoke.sh").read_text(encoding="utf-8")
        self.assertIn("gra-doctor --help >/dev/null", install_smoke)

    def test_install_matrix_workflow_exercises_supported_package_installs(self) -> None:
        text = (WORKFLOWS / "install-matrix.yml").read_text(encoding="utf-8")
        self.assertEqual({"contents": "read"}, parse_mapping(extract_block(text, "permissions:"), 2))
        self.assertEqual({"pull_request", "push", "workflow_dispatch"}, workflow_triggers(text))
        self.assertEqual(["main"], push_branches(text))
        package_install = job_block(text, "package-install")
        self.assertEqual({"contents": "read"}, job_permissions(text, "package-install"))
        self.assert_checkout_does_not_persist_credentials(package_install)
        self.assertIn("os: [ubuntu-latest, macos-latest, windows-latest]", package_install)
        self.assertIn('python-version: ["3.10", "3.11", "3.12"]', package_install)
        self.assertIn("actions/setup-python@v6", package_install)
        self.assertIn("python -m build --wheel --outdir $dist", package_install)
        self.assertIn("if ($IsWindows)", package_install)
        self.assertIn('Join-Path $venv "Scripts/python.exe"', package_install)
        self.assertIn('Join-Path $venv "bin/python"', package_install)
        self.assertIn('$env:PATH = "$bin$([System.IO.Path]::PathSeparator)$mockBin$([System.IO.Path]::PathSeparator)$env:PATH"', package_install)
        self.assertIn("$mockBuilder = @'", package_install)
        self.assertIn("print(chr(10).join(COMMANDS))", package_install)
        self.assertIn("assert len(COMMANDS) == 36, COMMANDS", package_install)
        self.assertIn('assert Path(gra.resource_path("VERSION")).is_file()', package_install)
        self.assertIn('assert Path(gra.resource_path("bin", "gra-doctor")).is_file()', package_install)
        self.assertIn('assert Path(gra.resource_path("lib", "agent_worker.py")).is_file()', package_install)
        self.assertIn('assert Path(gra.prompt_path("exec", "full-audit.prompt.md")).is_file()', package_install)
        self.assertIn('assert Path(gra.report_schema_path("findings.schema.json")).is_file()', package_install)
        self.assertIn('assert Path(gra.report_schema_path("efficacy-comparison.schema.json")).is_file()', package_install)
        self.assertIn('assert Path(gra.report_schema_path("efficacy-worker-response.schema.json")).is_file()', package_install)
        self.assertIn('assert Path(gra.taxonomy_path("owasp-llm-2025.json")).is_file()', package_install)
        self.assertIn('assert Path(gra.agent_worker_profile_path("codex-cli.json")).is_file()', package_install)
        self.assertIn('assert Path(gra.efficacy_corpus_path("core.json")).is_file()', package_install)
        self.assertIn('sys.path.insert(0, str(gra.resource_root() / "lib"))', package_install)
        self.assertIn('from efficacy_corpus import load_corpus', package_install)
        self.assertIn('assert len(load_corpus(gra.resource_root())["cases"]) >= 8', package_install)
        self.assertIn('if ($commands.Count -ne 36)', package_install)
        self.assertIn("foreach ($command in $commands)", package_install)
        self.assertIn("& $command --help", package_install)
        self.assertIn("& $command --version", package_install)
        self.assertIn("gra-doctor --json --runs-dir $runs", package_install)
        self.assertIn("gra-agent-check --list --json", package_install)
        self.assertIn("if ($IsWindows)", package_install)
        self.assertIn("gra-efficacy-benchmark --list", package_install)
        self.assertIn("gra-efficacy-benchmark --list-configurations", package_install)
        self.assertIn("gra-efficacy-benchmark --out-json $efficacyJson --out-md $efficacyMarkdown", package_install)
        self.assertIn("gra-efficacy-benchmark --compare --out-json $efficacyComparisonJson --out-md $efficacyComparisonMarkdown", package_install)
        self.assertIn('throw "missing installed efficacy benchmark outputs"', package_install)
        self.assertIn('throw "missing installed efficacy comparison outputs"', package_install)
        self.assertIn("gra-validate-report --run $fixture", package_install)
        self.assertIn("if (-not $IsWindows)", package_install)
        self.assertIn("gra-audit --repo acme/api --mode prepare --runs-dir $auditRuns --run-id installed-prepare", package_install)
        self.assertIn('Join-Path $auditRuns "acme__api/installed-prepare/run-manifest.json"', package_install)
        self.assertIn("gra-batch --repo-list $repoList --mode goal --runs-dir $batchRuns --batch-id installed-batch", package_install)
        self.assertIn('Join-Path $batchRuns "_batches/installed-batch/batch-results.json"', package_install)
        self.assertIn("unexpected gh invocation", package_install)
        self.assertIn("unexpected git invocation", package_install)
        self.assertIn("codex mock should not be executed", package_install)
        self.assertIn("python -m pipx install . --force --python", package_install)
        self.assertIn('for bin_dir in "${PIPX_BIN_DIR:-}" "$HOME/.local/bin" /opt/pipx_bin', package_install)
        self.assertIn("gra-pipx-doctor-runs", package_install)

    def test_trigger_helpers_accept_valid_yaml_variants(self) -> None:
        workflow = "\n".join(
            [
                "on:",
                "  pull_request:",
                "  merge_group:",
                "  push:",
                "    branches:",
                "      - main",
                "  schedule:",
                "    - cron: '23 3 * * 1'",
                "  workflow_dispatch:",
                "jobs:",
            ]
        )
        self.assert_required_workflow_triggers(workflow)

    def test_codeql_workflow_scans_python_and_github_actions(self) -> None:
        text = (WORKFLOWS / "codeql.yml").read_text(encoding="utf-8")
        self.assert_required_workflow_triggers(text)
        self.assert_top_level_permissions_disabled(text)
        analyze = job_block(text, "analyze")
        self.assertEqual(
            {"actions": "read", "contents": "read", "security-events": "write"},
            job_permissions(text, "analyze"),
        )
        self.assert_checkout_does_not_persist_credentials(analyze)
        languages = extract_block(analyze, "        language:")
        self.assertIn("          - python", languages)
        self.assertIn("          - actions", languages)
        self.assertIn("uses: github/codeql-action/init@v4", analyze)
        self.assertIn("uses: github/codeql-action/analyze@v4", analyze)

    def test_self_validation_workflow_prepares_and_executes_offline_fixture_run(self) -> None:
        text = (WORKFLOWS / "self-validation.yml").read_text(encoding="utf-8")
        self.assert_required_workflow_triggers(text)
        self.assert_top_level_permissions_disabled(text)
        prepare = job_block(text, "prepare-fixture")
        self.assertEqual({"contents": "read"}, job_permissions(text, "prepare-fixture"))
        self.assert_checkout_does_not_persist_credentials(prepare)
        self.assertIn("--repo fixture/self-validation", prepare)
        self.assertIn("--mode prepare", prepare)
        self.assertIn('ctx["network_allowed"] is False', prepare)
        self.assertIn("offline codex mock should not run in prepare mode", prepare)
        self.assertIn("--ask-for-approval is not supported for codex exec", prepare)
        self.assertIn("Execute an offline fixture audit run", prepare)
        self.assertIn("GRA_SELF_VALIDATION_ALLOW_CODEX_EXEC=1", prepare)
        self.assertIn("--mode exec", prepare)
        self.assertIn("--run-id self-validation-exec", prepare)
        self.assertIn('^final_status=0$', prepare)
        self.assertIn('^validation_status=0$', prepare)
        self.assertIn('bin/gra-validate-report --run "$run_dir"', prepare)
        self.assertIn('run_dir.is_relative_to(runner_temp)', prepare)
        self.assertIn('Path(summary["reports_dir"]).resolve().is_relative_to(runner_temp)', prepare)
        self.assertNotIn("${{ runner.temp }}", prepare)


if __name__ == "__main__":
    unittest.main(verbosity=2)

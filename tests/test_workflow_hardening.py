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
        self.assertIn("- name: Run local install smoke validation", lint)
        self.assertIn("        run: |\n          scripts/validate-install-smoke.sh", lint)
        self.assertIn("test -x scripts/validate-install-smoke.sh", lint)

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

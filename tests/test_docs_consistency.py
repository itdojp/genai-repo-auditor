from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
GRA_COMMAND_RE = re.compile(r"(?<![A-Za-z0-9_/-])(gra-[A-Za-z0-9_-]+)\b")
PROMPT_PATH_RE = re.compile(r"(?<![A-Za-z0-9_/-])(prompts/(?:exec|goal)/[A-Za-z0-9_.-]+(?:\.prompt|\.goal)\.md)")
STALE_PROMPT_PATH_RE = re.compile(r"(?<![A-Za-z0-9_/-])(prompts/(?!exec/|goal/)[A-Za-z0-9_.-]+(?:\.prompt|\.goal)\.md)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def markdown_anchor(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[`*_~]", "", text).strip().lower()
    text = re.sub(r"[^\w\s\-\u3040-\u30ff\u3400-\u9fff]", "", text)
    return re.sub(r"[\s\-]+", "-", text).strip("-")


def anchors_for(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING_RE.match(line)
        if match:
            anchors.add(markdown_anchor(match.group(2)))
    return anchors


def local_markdown_links(path: Path) -> list[tuple[str, Path, str]]:
    links: list[tuple[str, Path, str]] = []
    for raw in MARKDOWN_LINK_RE.findall(path.read_text(encoding="utf-8")):
        parsed = urlparse(raw)
        if parsed.scheme or parsed.netloc or raw.startswith("mailto:"):
            continue
        target, _sep, anchor = raw.partition("#")
        if not target and anchor:
            target_path = path
        else:
            target_path = (path.parent / unquote(target)).resolve()
        links.append((raw, target_path, unquote(anchor)))
    return links


class DocsConsistencyTests(unittest.TestCase):
    maxDiff = None

    def test_internal_markdown_links_point_to_existing_files_and_anchors(self) -> None:
        failures = []
        for path in DOC_FILES:
            for raw, target_path, anchor in local_markdown_links(path):
                try:
                    target_path.relative_to(REPO_ROOT)
                except ValueError:
                    failures.append(f"{path.relative_to(REPO_ROOT)}: link escapes repository: {raw}")
                    continue
                if not target_path.exists():
                    failures.append(f"{path.relative_to(REPO_ROOT)}: missing link target: {raw}")
                    continue
                if anchor and target_path.suffix.lower() == ".md" and anchor not in anchors_for(target_path):
                    failures.append(f"{path.relative_to(REPO_ROOT)}: missing anchor #{anchor} in {target_path.relative_to(REPO_ROOT)}")
        self.assertEqual([], failures)

    def test_documented_gra_commands_exist_under_bin(self) -> None:
        known = {path.name for path in (REPO_ROOT / "bin").glob("gra-*") if path.is_file()}
        failures = []
        for path in DOC_FILES:
            refs = sorted(set(GRA_COMMAND_RE.findall(path.read_text(encoding="utf-8"))))
            unknown = [ref for ref in refs if ref not in known]
            if unknown:
                failures.append(f"{path.relative_to(REPO_ROOT)}: unknown gra-* commands: {', '.join(unknown)}")
        self.assertEqual([], failures)

    def test_documented_prompt_paths_match_rendered_prompt_layout(self) -> None:
        failures = []
        for path in DOC_FILES:
            text = path.read_text(encoding="utf-8")
            stale_refs = sorted(set(STALE_PROMPT_PATH_RE.findall(text)))
            if stale_refs:
                failures.append(
                    f"{path.relative_to(REPO_ROOT)}: prompt refs must include prompts/exec or prompts/goal: {', '.join(stale_refs)}"
                )
            for ref in sorted(set(PROMPT_PATH_RE.findall(text))):
                if not (REPO_ROOT / ref).exists():
                    failures.append(f"{path.relative_to(REPO_ROOT)}: missing documented prompt template: {ref}")

        library_text = (REPO_ROOT / "docs" / "GOAL_PROMPT_LIBRARY.md").read_text(encoding="utf-8")
        missing_goal_prompts = [
            f"prompts/goal/{path.name}"
            for path in sorted((REPO_ROOT / "prompts" / "goal").glob("*.goal.md"))
            if f"prompts/goal/{path.name}" not in library_text
        ]
        if missing_goal_prompts:
            failures.append(f"docs/GOAL_PROMPT_LIBRARY.md: missing goal prompt docs: {', '.join(missing_goal_prompts)}")
        self.assertEqual([], failures)

    def test_readme_links_to_key_documentation(self) -> None:
        readme = REPO_ROOT / "README.md"
        linked_targets = {
            str(target.relative_to(REPO_ROOT))
            for _raw, target, _anchor in local_markdown_links(readme)
            if target.exists() and target.is_file()
        }
        required = {
            "docs/COMMAND_REFERENCE.md",
            "docs/LOCAL_INSTALL_AND_AUDIT.md",
            "docs/OPERATING_MODEL.md",
            "docs/CUSTOMER_AUDIT_RUNBOOK.md",
            "docs/DISCLOSURE_AND_PUBLICATION_POLICY.md",
            "docs/REMEDIATION_WORKFLOW.md",
            "docs/ADVANCED_WORKFLOW_DECISION_TABLE.md",
            "docs/SECURITY_MODEL.md",
            "docs/SCANNER_INTEGRATION.md",
            "docs/ISSUE_WORKFLOW.md",
        }
        self.assertTrue(required.issubset(linked_targets), f"missing README doc links: {sorted(required - linked_targets)}")

    def test_dangerous_access_terms_are_documented_as_non_default(self) -> None:
        caution_terms = ["do not", "not recommended", "avoid", "never", "forbidden", "禁止", "使わない", "通常使わない", "デフォルト", "基本"]
        failures = []
        for path in DOC_FILES:
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "danger-full-access" not in line:
                    continue
                window = "\n".join(lines[max(0, index - 4): index + 5]).lower()
                if not any(term.lower() in window for term in caution_terms):
                    failures.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}: danger-full-access lacks nearby caution")
        self.assertEqual([], failures)

    def test_public_issue_disclosure_flags_have_nearby_caution(self) -> None:
        caution_terms = [
            "blocked",
            "denied",
            "refuses",
            "only when",
            "approved",
            "human review",
            "policy permits",
            "intentional",
            "default",
            "拒否",
            "意図的",
            "承認",
            "確認",
            "デフォルト",
            "場合だけ",
        ]
        failures = []
        for path in DOC_FILES:
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if "--allow-public" not in line:
                    continue
                window = "\n".join(lines[max(0, index - 6): index + 7]).lower()
                if not any(term.lower() in window for term in caution_terms):
                    failures.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}: --allow-public lacks nearby disclosure caution")
        self.assertEqual([], failures)

    def test_normal_workflow_flowcharts_use_consecutive_step_numbers(self) -> None:
        failures = []
        for relative in ("docs/NORMAL_WORKFLOW.md", "docs/NORMAL_OPERATION.md"):
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            match = re.search(r"## 全体フロー\s+```text\n(?P<body>.*?)\n```", text, re.DOTALL)
            if not match:
                failures.append(f"{relative}: missing 全体フロー text block")
                continue
            step_numbers = [
                int(step.group(1))
                for step in re.finditer(r"^\s*(\d+)\.\s+", match.group("body"), re.MULTILINE)
            ]
            expected = list(range(1, len(step_numbers) + 1))
            if step_numbers != expected:
                failures.append(f"{relative}: expected consecutive step numbers {expected}, got {step_numbers}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main(verbosity=2)

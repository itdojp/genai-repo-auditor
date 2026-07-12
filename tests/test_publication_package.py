from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = REPO_ROOT / "docs" / "public"
ARTICLE = PUBLIC_DIR / "TECHNICAL_ARTICLE_DRAFT.md"
CLAIMS = PUBLIC_DIR / "ARTICLE_CLAIM_SOURCES.md"
RUNBOOK = PUBLIC_DIR / "RECORDED_DEMO_RUNBOOK.md"
SHOT_LIST = PUBLIC_DIR / "DEMO_SHOT_LIST.md"
REVIEW = PUBLIC_DIR / "DEMO_PUBLICATION_REVIEW.md"
PUBLICATION_FILES = (ARTICLE, CLAIMS, RUNBOOK, SHOT_LIST, REVIEW)


def bash_blocks(markdown: str) -> str:
    return "\n".join(re.findall(r"```bash\r?\n(.*?)```", markdown, re.DOTALL))


class PublicationPackageTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        missing = [
            str(path.relative_to(REPO_ROOT))
            for path in PUBLICATION_FILES
            if not path.is_file()
        ]
        if missing:
            raise AssertionError(
                "required publication documents are missing: " + ", ".join(missing)
            )
        cls.article = ARTICLE.read_text(encoding="utf-8")
        cls.claims = CLAIMS.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.shot_list = SHOT_LIST.read_text(encoding="utf-8")
        cls.review = REVIEW.read_text(encoding="utf-8")
        cls.combined = "\n".join(
            (cls.article, cls.claims, cls.runbook, cls.shot_list, cls.review)
        )

    def test_article_claims_are_complete_and_linked_to_source_map(self) -> None:
        article_ids = re.findall(
            r"\[A(\d{2})\]\(ARTICLE_CLAIM_SOURCES\.md\)", self.article
        )
        claim_ids = re.findall(r"^\| A(\d{2}) \|", self.claims, re.MULTILINE)
        expected = [f"{index:02d}" for index in range(1, 21)]
        self.assertEqual(expected, sorted(set(article_ids)))
        self.assertEqual(expected, sorted(set(claim_ids)))

        rows = [line for line in self.claims.splitlines() if re.match(r"\| A\d{2} \|", line)]
        self.assertEqual(20, len(rows))
        for row in rows:
            self.assertGreaterEqual(
                len(re.findall(r"\[[^]]+\]\([^)]+\.md(?:#[^)]+)?\)", row)),
                2,
                row,
            )
            self.assertEqual(7, row.count("|"), row)

    def test_article_covers_required_roles_workflow_and_evidence_boundaries(self) -> None:
        required = [
            "control plane",
            "compatible ai workers",
            "deterministic scanners",
            "human reviewer",
            "plan-review-execute-resume",
            "adversarial validation",
            "defensive chain reasoning",
            "safe proof planning",
            "remediation candidates",
            "deterministic public synthetic results",
            "private holdout",
            "operational counts",
            "production recall",
            "human review",
            "### deterministic synthetic regression",
            "### workflow-health benchmark",
            "### operational dogfood",
            "## measured limitations and next steps",
        ]
        article_lower = self.article.lower()
        missing = [term for term in required if term not in article_lower]
        self.assertEqual([], missing)

    def test_all_repository_markdown_links_resolve(self) -> None:
        failures: list[str] = []
        for path in PUBLICATION_FILES:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                file_part = target.split("#", 1)[0]
                if not file_part or "://" in file_part or file_part.startswith("mailto:"):
                    continue
                resolved = (path.parent / file_part).resolve()
                if not resolved.is_file() or REPO_ROOT not in resolved.parents:
                    failures.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
        self.assertEqual([], failures)

    def test_demo_is_bounded_to_public_inputs_and_dry_run(self) -> None:
        required = [
            "8-12 minute",
            "public synthetic",
            "repository-owned minimal fixture",
            "gra-issues --dry-run",
            "human-only",
            "redaction",
            "stop conditions",
        ]
        demo = "\n".join((self.runbook, self.shot_list, self.review)).lower()
        missing = [term for term in required if term not in demo]
        self.assertEqual([], missing)

        commands = bash_blocks(self.runbook)
        forbidden_commands = [
            "gra-run --execute",
            "gra-issues --plan",
            "gra-issues --apply",
            "--apply-plan",
            "--allow-public",
            "--create-labels",
            "gh issue",
            "gh pr",
            "curl ",
        ]
        present = [term for term in forbidden_commands if term in commands]
        self.assertEqual([], present)
        self.assertRegex(
            commands,
            r"gra-issues --run \.demo-public/minimal-run --dry-run\s*>\s*"
            r"\.demo-public/private-dry-run\.log",
        )
        self.assertIn("bin/gra-run \\", commands)
        self.assertIn("--profile recon-only", commands)
        self.assertIn("--json > \"$DEMO_DIR/workflow-plan.json\"", commands)
        efficacy_commands = [
            block
            for block in re.findall(r"```bash\r?\n(.*?)```", self.runbook, re.DOTALL)
            if "bin/gra-efficacy-benchmark" in block
        ]
        self.assertEqual(2, len(efficacy_commands))
        self.assertTrue(all(">/dev/null" in block for block in efficacy_commands))
        self.assertIn("plan/review gate", self.runbook)
        self.assertIn("same-profile `--resume`", self.runbook)

    def test_demo_scratch_is_ignored_cwd_guarded_and_cleaned(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".demo-public/", gitignore.splitlines())
        commands = bash_blocks(self.runbook)
        self.assertIn('test "$(git rev-parse --show-toplevel)" = "$PWD"', commands)
        self.assertIn("rm -rf -- \"$DEMO_DIR\"", commands)
        self.assertIn("trap 'rm -rf -- \"$DEMO_DIR\"' EXIT", commands)
        self.assertIn("no demo-generated file is staged or retained", self.review)

    def test_publication_stays_human_controlled_and_urls_are_unset(self) -> None:
        required = [
            "uploading the video is a separate human action",
            "external posting is blocked",
            "external publication url",
            "approved yet",
            "readme update",
        ]
        combined_lower = self.combined.lower()
        missing = [term for term in required if term not in combined_lower]
        self.assertEqual([], missing)
        self.assertNotRegex(self.combined, r"https?://")

    def test_public_package_has_no_private_identifiers_or_secret_material(self) -> None:
        forbidden = [
            ".codex-local",
            "/home/",
            "C:\\Users\\",
            "target-research",
            "-----BEGIN",
            "ghp_",
            "github_pat_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden if term.lower() in self.combined.lower()]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\bTGT-(?:AGENT-|PROVENANCE-)?\d+\b", self.combined))
        self.assertIsNone(re.search(r"\bSEC-\d+\b", self.combined))

    def test_sensitive_artifacts_are_only_named_as_prohibited_display(self) -> None:
        required_guardrails = [
            "do not show the raw json file on screen",
            "do not open `reports/findings.json`",
            "do not show the terminal log",
            "raw dry-run terminal output stays off-screen",
        ]
        combined_lower = self.combined.lower()
        missing = [term for term in required_guardrails if term not in combined_lower]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main(verbosity=2)

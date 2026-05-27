from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "MANIFEST.md"
FENCED_SECTION_RE = re.compile(r"^## (?P<title>.+?)\n\n```text\n(?P<body>.*?)\n```", re.MULTILINE | re.DOTALL)


def manifest_sections() -> dict[str, set[str]]:
    text = MANIFEST.read_text(encoding="utf-8")
    sections: dict[str, set[str]] = {}
    for match in FENCED_SECTION_RE.finditer(text):
        sections[match.group("title")] = {
            line.strip()
            for line in match.group("body").splitlines()
            if line.strip()
        }
    return sections


def relative_files(*parts: str, pattern: str = "*") -> set[str]:
    base = REPO_ROOT.joinpath(*parts)
    return {path.relative_to(REPO_ROOT).as_posix() for path in sorted(base.rglob(pattern)) if path.is_file()}


class ManifestTests(unittest.TestCase):
    maxDiff = None

    def assert_manifest_section(self, section: str, expected: set[str]) -> None:
        sections = manifest_sections()
        self.assertIn(section, sections, f"MANIFEST.md is missing ## {section}")
        self.assertEqual(expected, sections[section], f"MANIFEST.md ## {section} is stale")

    def test_manifest_lists_all_gra_commands(self) -> None:
        expected = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in sorted((REPO_ROOT / "bin").glob("gra-*"))
            if path.is_file()
        }
        self.assert_manifest_section("Commands", expected)

    def test_manifest_lists_prompt_surface(self) -> None:
        self.assert_manifest_section("Prompts", relative_files("prompts", pattern="*.md"))

    def test_manifest_lists_report_templates_and_taxonomies(self) -> None:
        self.assert_manifest_section("Report schemas and templates", relative_files("templates", "reports"))
        self.assert_manifest_section("Taxonomies", relative_files("templates", "taxonomies"))

    def test_manifest_lists_public_documentation(self) -> None:
        expected = {
            path.relative_to(REPO_ROOT).as_posix()
            for path in sorted(REPO_ROOT.glob("*.md"))
            if path.is_file()
        }
        expected.update(relative_files("docs", pattern="*.md"))
        self.assert_manifest_section("Documentation", expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)

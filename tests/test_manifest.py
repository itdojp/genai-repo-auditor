from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "MANIFEST.md"


def is_fence(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("```") and stripped.count("`") >= 3


def manifest_sections() -> dict[str, set[str]]:
    lines = MANIFEST.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    sections: dict[str, set[str]] = {}
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line.startswith("## "):
            index += 1
            continue
        title = line[3:].strip()
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines) or not is_fence(lines[index]):
            continue
        index += 1
        body: list[str] = []
        while index < len(lines) and not is_fence(lines[index]):
            if lines[index].strip():
                body.append(lines[index].strip())
            index += 1
        sections[title] = set(body)
        index += 1
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

    def test_manifest_lists_release_tooling(self) -> None:
        self.assert_manifest_section(
            "Release tooling",
            {".github/workflows/release.yml", "scripts/build_release.py"},
        )

    def test_manifest_lists_packaging_metadata(self) -> None:
        self.assert_manifest_section(
            "Packaging",
            {
                "MANIFEST.in",
                "pyproject.toml",
                "src/genai_repo_auditor/__init__.py",
                "src/genai_repo_auditor/audit_cli.py",
                "src/genai_repo_auditor/batch_cli.py",
                "src/genai_repo_auditor/cli.py",
                "src/genai_repo_auditor/resources.py",
                "src/genai_repo_auditor/version.py",
            },
        )

    def test_manifest_lists_prompt_surface(self) -> None:
        self.assert_manifest_section("Prompts", relative_files("prompts", pattern="*.md"))

    def test_manifest_lists_report_templates_and_taxonomies(self) -> None:
        self.assert_manifest_section("Report schemas and templates", relative_files("templates", "reports"))
        expected_taxonomies = relative_files("templates", "taxonomies")
        expected_taxonomies.add("templates/taxonomy-aliases.json")
        self.assert_manifest_section("Taxonomies", expected_taxonomies)

    def test_manifest_lists_dogfood_templates(self) -> None:
        self.assert_manifest_section("Dogfood templates", relative_files("templates", "dogfood"))

    def test_manifest_lists_agent_worker_profiles(self) -> None:
        self.assert_manifest_section("Agent worker profiles", relative_files("templates", "agent-workers"))

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

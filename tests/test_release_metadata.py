from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION = REPO_ROOT / "VERSION"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
RELEASE_PROCESS = REPO_ROOT / "docs" / "RELEASE_PROCESS.md"


def project_version() -> str:
    return VERSION.read_text(encoding="utf-8").splitlines()[0].strip()


def changelog_section(version: str) -> str:
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    heading_re = re.compile(rf"^## v{re.escape(version)}(?: - \d{{4}}-\d{{2}}-\d{{2}})?$")
    start = next((index for index, line in enumerate(lines) if heading_re.match(line)), None)
    if start is None:
        raise AssertionError(f"missing changelog section: ## v{version}")
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip() + "\n"


def extract_release_notes_python_snippet() -> str:
    text = RELEASE_PROCESS.read_text(encoding="utf-8")
    match = re.search(
        r"VERSION_VALUE=\"\$VERSION_VALUE\" RELEASE_NOTES=\"\$RELEASE_NOTES\" python3 - <<'PY'\n"
        r"(?P<code>.*?)\n"
        r"PY\n",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("missing documented release notes extraction Python snippet")
    return match.group("code")


class ReleaseMetadataTests(unittest.TestCase):
    maxDiff = None

    def test_version_uses_documented_semver_without_tag_prefix(self) -> None:
        version = project_version()
        self.assertRegex(version, r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertFalse(version.startswith("v"), "VERSION must not include the tag prefix")

    def test_changelog_has_matching_current_version_section(self) -> None:
        version = project_version()
        section = changelog_section(version)
        self.assertRegex(section.splitlines()[0], rf"^## v{re.escape(version)}(?: - \d{{4}}-\d{{2}}-\d{{2}})?$")
        entries = [line for line in section.splitlines()[1:] if line.startswith("- ")]
        self.assertTrue(entries, f"CHANGELOG.md section for v{version} must contain release notes")

    def test_release_process_links_canonical_metadata_and_uses_v_tag_convention(self) -> None:
        text = RELEASE_PROCESS.read_text(encoding="utf-8")
        self.assertIn("[`VERSION`](../VERSION)", text)
        self.assertIn("[`CHANGELOG.md`](../CHANGELOG.md)", text)
        self.assertRegex(text, r"VERSION=\d+\.\d+\.\d+")
        self.assertRegex(text, r"tag `v\d+\.\d+\.\d+`")
        self.assertIn('test "v$VERSION_VALUE" = "vX.Y.Z"', text)
        self.assertIn('git tag -a "v$VERSION_VALUE"', text)
        self.assertIn('gh release create "v$VERSION_VALUE"', text)

    def test_documented_release_notes_extraction_snippet_is_valid_and_matches_changelog(self) -> None:
        version = project_version()
        code = extract_release_notes_python_snippet()
        compile(code, str(RELEASE_PROCESS), "exec")

        notes = changelog_section(version)
        self.assertTrue(notes.startswith(f"## v{version}"))
        self.assertTrue(notes.endswith("\n"))
        self.assertNotIn("\n## ", notes.rstrip("\n"), "release notes extraction should stop before the next section")


if __name__ == "__main__":
    unittest.main(verbosity=2)

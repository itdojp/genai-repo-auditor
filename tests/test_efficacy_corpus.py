from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from efficacy_corpus import EfficacyCorpusError, load_corpus  # noqa: E402
import efficacy_corpus  # noqa: E402


class EfficacyCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        parent = REPO_ROOT / ".test-tmp"
        parent.mkdir(exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)
        with contextlib.suppress(OSError):
            (REPO_ROOT / ".test-tmp").rmdir()

    def copy_corpus(self, name: str = "lab") -> Path:
        root = self.work / name
        shutil.copytree(REPO_ROOT / "benchmarks", root / "benchmarks")
        return root

    @staticmethod
    def write_json(path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def refresh_manifest_digest(self, lab_root: Path, manifest_path: Path) -> None:
        corpus_path = lab_root / "benchmarks" / "corpus" / "core.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        relative = manifest_path.relative_to(corpus_path.parent).as_posix()
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        next(entry for entry in corpus["cases"] if entry["manifest"] == relative)["manifest_sha256"] = digest
        self.write_json(corpus_path, corpus)

    def test_core_corpus_is_stable_public_safe_and_reviewable(self) -> None:
        first = load_corpus(REPO_ROOT)
        second = load_corpus(REPO_ROOT)

        self.assertEqual(first, second)
        corpus = first["corpus"]
        cases = first["cases"]
        self.assertRegex(corpus["corpus_version"], r"^1\.0\.0\+sha256\.[a-f0-9]{64}$")
        self.assertEqual("core", corpus["default_suite"])
        self.assertEqual(sorted(case["case_id"] for case in cases), [case["case_id"] for case in cases])
        self.assertEqual(
            {"positive": 5, "negative_control": 3},
            dict(Counter(case["classification"] for case in cases)),
        )
        self.assertGreaterEqual(len({case["category"] for case in cases}), 3)
        for case in cases:
            self.assertRegex(case["case_version"], r"^1\.0\.0\+sha256\.[a-f0-9]{64}$")
            self.assertTrue(case["public_safe"])
            self.assertTrue(case["fixture"]["non_deployable"])
            self.assertFalse(case["fixture"]["network_required"])
            self.assertEqual([], case["fixture"]["external_hosts"])
            self.assertFalse(case["fixture"]["credentials_included"])
            self.assertFalse(case["fixture"]["weaponized_payloads_included"])
            self.assertIn("issue-publication", case["stage_expectations"]["prohibited"])
            if case["classification"] == "positive":
                self.assertEqual(1, len(case["ground_truth"]["positive_findings"]))
                self.assertEqual([], case["ground_truth"]["negative_controls"])
            else:
                self.assertEqual([], case["ground_truth"]["positive_findings"])
                self.assertEqual(1, len(case["ground_truth"]["negative_controls"]))

    def test_closed_case_contract_rejects_unlisted_payload_fields(self) -> None:
        lab_root = self.copy_corpus()
        manifest_path = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "authz-001" / "case.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["details"] = "uncontracted payload"
        manifest["ground_truth"]["details"] = "nested uncontracted payload"
        self.write_json(manifest_path, manifest)
        self.refresh_manifest_digest(lab_root, manifest_path)

        with self.assertRaisesRegex(EfficacyCorpusError, "closed corpus contract") as raised:
            load_corpus(lab_root)
        self.assertNotIn("uncontracted payload", str(raised.exception))

    def test_fixture_digest_network_marker_and_symlink_checks_fail_closed(self) -> None:
        lab_root = self.copy_corpus("lab-symlink")
        case_root = lab_root / "benchmarks" / "corpus" / "cases" / "ai-agent-mcp" / "tool-control-001"
        fixture_path = case_root / "agent-config.json"
        manifest_path = case_root / "case.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["documentation"] = "https://invalid.example/fixture"
        self.write_json(fixture_path, fixture)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["fixture"]["files"][0]["sha256"] = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        self.write_json(manifest_path, manifest)
        self.refresh_manifest_digest(lab_root, manifest_path)

        with self.assertRaisesRegex(EfficacyCorpusError, "prohibited live-network"):
            load_corpus(lab_root)

        lab_root = self.copy_corpus()
        case_root = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "path-001"
        fixture_path = case_root / "file_helper.py"
        outside = self.work / "outside-fixture.py"
        outside.write_bytes(fixture_path.read_bytes())
        fixture_path.unlink()
        fixture_path.symlink_to(outside)

        with self.assertRaisesRegex(EfficacyCorpusError, "symlink"):
            load_corpus(lab_root)

    def test_duplicate_fixture_paths_are_rejected(self) -> None:
        lab_root = self.copy_corpus()
        manifest_path = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "authz-001" / "case.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        duplicate = dict(manifest["fixture"]["files"][0])
        duplicate["sha256"] = "0" * 64
        manifest["fixture"]["files"].append(duplicate)
        self.write_json(manifest_path, manifest)
        self.refresh_manifest_digest(lab_root, manifest_path)

        with self.assertRaisesRegex(EfficacyCorpusError, "fixture file paths must be unique"):
            load_corpus(lab_root)

    def test_content_changes_require_case_and_corpus_version_changes(self) -> None:
        lab_root = self.copy_corpus()
        case_root = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "path-001"
        fixture_path = case_root / "file_helper.py"
        manifest_path = case_root / "case.json"
        fixture_path.write_text(
            fixture_path.read_text(encoding="utf-8") + "# defensive fixture note\n",
            encoding="utf-8",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["fixture"]["files"][0]["sha256"] = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        self.write_json(manifest_path, manifest)
        self.refresh_manifest_digest(lab_root, manifest_path)

        with self.assertRaisesRegex(EfficacyCorpusError, "case version does not match"):
            load_corpus(lab_root)

        lab_root = self.copy_corpus("lab-corpus-version")
        corpus_path = lab_root / "benchmarks" / "corpus" / "core.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        corpus["description"] += " Defensive review note."
        self.write_json(corpus_path, corpus)
        with self.assertRaisesRegex(EfficacyCorpusError, "corpus version does not match"):
            load_corpus(lab_root)

    def test_repository_policy_pins_corpus_text_to_lf(self) -> None:
        attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("benchmarks/corpus/** text eol=lf", attributes)
        for path in (REPO_ROOT / "benchmarks" / "corpus").rglob("*"):
            if path.is_file():
                self.assertNotIn(b"\r\n", path.read_bytes(), path)

    def test_case_manifest_and_corpus_index_reject_public_safety_markers(self) -> None:
        lab_root = self.copy_corpus()
        manifest_path = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "authz-001" / "case.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["description"] += " See https://example.invalid/fixture."
        escaped_manifest = json.dumps(manifest, indent=2, sort_keys=True).replace("https://", r"https:\/\/") + "\n"
        manifest_path.write_text(escaped_manifest, encoding="utf-8")
        with self.assertRaisesRegex(EfficacyCorpusError, "case manifest contains a prohibited"):
            load_corpus(lab_root)

        lab_root = self.copy_corpus("lab-index-marker")
        corpus_path = lab_root / "benchmarks" / "corpus" / "core.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        corpus["description"] += " https://example.invalid/private/repository"
        escaped_corpus = json.dumps(corpus, indent=2, sort_keys=True).replace("https://", r"https:\/\/") + "\n"
        corpus_path.write_text(escaped_corpus, encoding="utf-8")
        with self.assertRaisesRegex(EfficacyCorpusError, "corpus index contains a prohibited"):
            load_corpus(lab_root)

        lab_root = self.copy_corpus("lab-json-fixture-marker")
        case_root = lab_root / "benchmarks" / "corpus" / "cases" / "ai-agent-mcp" / "tool-control-001"
        fixture_path = case_root / "agent-config.json"
        manifest_path = case_root / "case.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixture["documentation"] = "https://example.invalid/private/fixture"
        escaped_fixture = json.dumps(fixture, indent=2, sort_keys=True).replace("https://", r"https:\/\/") + "\n"
        fixture_path.write_text(escaped_fixture, encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["fixture"]["files"][0]["sha256"] = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        self.write_json(manifest_path, manifest)
        self.refresh_manifest_digest(lab_root, manifest_path)
        with self.assertRaisesRegex(EfficacyCorpusError, "fixture file contains a prohibited"):
            load_corpus(lab_root)

    def test_schema_rejects_unsupported_keywords(self) -> None:
        lab_root = self.copy_corpus()
        schema_path = lab_root / "benchmarks" / "corpus" / "case.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["allOf"] = [{"properties": {"description": {"pattern": "never-match"}}}]
        self.write_json(schema_path, schema)
        with self.assertRaisesRegex(EfficacyCorpusError, "unsupported schema keywords"):
            load_corpus(lab_root)

    @unittest.skipUnless(efficacy_corpus.OPEN_SUPPORTS_DIR_FD, "requires openat-style dir_fd support")
    def test_directory_handle_read_resists_ancestor_symlink_swap(self) -> None:
        lab_root = self.copy_corpus()
        case_root = lab_root / "benchmarks" / "corpus" / "cases" / "python-web" / "path-001"
        original_root = case_root.with_name("path-001-original")
        outside_root = self.work / "outside-case"
        outside_root.mkdir()
        (outside_root / "file_helper.py").write_text(
            "# https://example.invalid/outside\n",
            encoding="utf-8",
        )
        real_open = efficacy_corpus.os.open
        swapped = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if path == "file_helper.py" and dir_fd is not None and not swapped:
                case_root.rename(original_root)
                case_root.symlink_to(outside_root, target_is_directory=True)
                swapped = True
            if dir_fd is None:
                return real_open(path, flags, mode)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with unittest.mock.patch.object(efficacy_corpus.os, "open", side_effect=racing_open):
            loaded = load_corpus(lab_root)
        self.assertTrue(swapped)
        self.assertEqual(8, len(loaded["cases"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import contextlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "lib"))

from scanner_normalize import normalize_scanner_file, redact_sensitive_field, redact_text  # noqa: E402


class ScannerNormalizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_parent = REPO_ROOT / ".test-tmp"
        self.tmp_parent.mkdir(exist_ok=True)
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"{self._testMethodName}-", dir=self.tmp_parent))

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            self.tmp_parent.rmdir()

    def write_json(self, name: str, data) -> Path:
        path = self.work_dir / name
        path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        return path

    def normalize(self, tool: str, path: Path):
        return normalize_scanner_file(tool=tool, raw_path=path, raw_result_ref=f"reports/scanner-results/{path.name}")

    def test_redacts_sensitive_fields_and_extracts_json_leads(self) -> None:
        stripe_secret = "sk_live_1234567890abcdef"
        aws_id = "AKIAABCDEFGHIJKLMNOP"
        path = self.write_json(
            "gitleaks.json",
            [
                {"RuleID": "stripe-key", "File": "config.env", "StartLine": 7, "Secret": stripe_secret},
                {"DetectorName": "aws", "SourceMetadata": {"Data": {"Git": {"file": "aws.env", "line": 3}}}, "Raw": aws_id},
            ],
        )
        normalized = self.normalize("gitleaks", path)
        self.assertEqual(normalized["format"], "json")
        self.assertFalse(normalized["normalization"]["parse_error"])
        self.assertEqual(len(normalized["leads"]), 2)
        self.assertEqual(normalized["leads"][0]["path"], "config.env")
        self.assertEqual(normalized["leads"][0]["line"], 7)
        self.assertEqual(normalized["leads"][1]["path"], "aws.env")
        self.assertEqual(normalized["leads"][1]["line"], 3)
        text = json.dumps(normalized)
        self.assertNotIn(stripe_secret, text)
        self.assertNotIn(aws_id, text)
        self.assertIn("sk_live_...cdef", text)
        self.assertIn("AKIA...MNOP", text)

    def test_normalizes_semgrep_and_sarif_locations(self) -> None:
        semgrep = self.write_json(
            "semgrep.json",
            {
                "results": [
                    {
                        "check_id": "python.lang.security.fixture",
                        "path": "src/app.py",
                        "start": {"line": 42},
                        "extra": {"message": "tainted input reaches sink"},
                    }
                ]
            },
        )
        semgrep_normalized = self.normalize("semgrep", semgrep)
        semgrep_lead = semgrep_normalized["leads"][0]
        self.assertEqual(semgrep_lead["rule_id"], "python.lang.security.fixture")
        self.assertEqual(semgrep_lead["severity"], "unknown")
        self.assertEqual(semgrep_lead["path"], "src/app.py")
        self.assertEqual(semgrep_lead["line"], 42)
        self.assertIn("tainted input", semgrep_lead["redacted_evidence"])

        sarif = self.write_json(
            "codeql.sarif",
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
            },
        )
        sarif_lead = self.normalize("codeql", sarif)["leads"][0]
        self.assertEqual(sarif_lead["rule_id"], "py/test-rule")
        self.assertEqual(sarif_lead["severity"], "warning")
        self.assertEqual(sarif_lead["path"], "src/main.py")
        self.assertEqual(sarif_lead["line"], 12)

    def test_normalizes_jsonl_ndjson_and_generic_text_fallback(self) -> None:
        secret = "correcthorsebatterystaple"
        ndjson = self.work_dir / "trufflehog.ndjson"
        ndjson.write_text(
            "\n".join(
                [
                    json.dumps({"DetectorName": "generic", "Raw": secret, "SourceMetadata": {"Data": {"Git": {"file": "a.env", "line": 1}}}}),
                    json.dumps({"DetectorName": "aws", "Raw": "ASIAABCDEFGHIJKLMNOP", "SourceMetadata": {"Data": {"Git": {"file": "b.env", "line": 2}}}}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        normalized = self.normalize("trufflehog", ndjson)
        self.assertEqual(normalized["format"], "ndjson")
        self.assertFalse(normalized["normalization"]["parse_error"])
        self.assertEqual(len(normalized["leads"]), 2)
        self.assertEqual(normalized["leads"][0]["redacted_evidence"], "<REDACTED:scanner-secret>")
        self.assertIn("ASIA...MNOP", json.dumps(normalized))
        self.assertNotIn(secret, json.dumps(normalized))

        private_key_text = "before\n-----BEGIN PRIVATE KEY-----\nABCDEF1234567890\nafter\n"
        text_path = self.work_dir / "scanner.txt"
        text_path.write_text(private_key_text, encoding="utf-8")
        text_normalized = self.normalize("custom", text_path)
        self.assertEqual(text_normalized["leads"][0]["rule_id"], "unparsed-text")
        self.assertTrue(text_normalized["normalization"]["parse_error"])
        self.assertIn("<REDACTED:private-key>", text_normalized["leads"][0]["redacted_evidence"])
        self.assertNotIn("ABCDEF1234567890", json.dumps(text_normalized))

    def test_redaction_helpers_mask_known_secret_shapes(self) -> None:
        self.assertEqual(redact_sensitive_field("not-a-pattern"), "<REDACTED:scanner-secret>")
        self.assertIn("ghp_...7890", redact_text("token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"))
        self.assertIn("<REDACTED:private-key>", redact_text("-----BEGIN PRIVATE KEY-----\nABC"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

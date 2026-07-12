from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation"
REPORT = EVALUATION_DIR / "PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md"
MATRIX = EVALUATION_DIR / "CLAIM_EVIDENCE_MATRIX.md"
REPRODUCTION = EVALUATION_DIR / "EVALUATION_REPRODUCTION.md"
SOURCE_COMMIT = "960dd1de42c129a524acbb2437f3a4406024bda9"
CORPUS_VERSION = (
    "1.1.0+sha256."
    "33c20915076017869a6b99e0552be59f40aa05d701b61e4572d4d449a4fa6146"
)


class EvaluationDocsTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.report = REPORT.read_text(encoding="utf-8")
        self.matrix = MATRIX.read_text(encoding="utf-8")
        self.reproduction = REPRODUCTION.read_text(encoding="utf-8")
        self.dogfood_summary = (
            REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md"
        ).read_text(encoding="utf-8")
        self.combined = "\n".join((self.report, self.matrix, self.reproduction))

    def test_required_evaluation_documents_exist_and_are_linked(self) -> None:
        for path in (REPORT, MATRIX, REPRODUCTION):
            self.assertTrue(path.is_file(), path.relative_to(REPO_ROOT))
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md", readme)
        for filename in (
            "CLAIM_EVIDENCE_MATRIX.md",
            "EVALUATION_REPRODUCTION.md",
        ):
            self.assertIn(filename, self.report)

    def test_report_separates_evidence_layers_and_absence(self) -> None:
        required = [
            "deterministic results from the public synthetic corpus",
            "aggregate-only private holdout results",
            "public-safe operational counts",
            "No approved private holdout aggregate exists",
            "No worker profile, model, effort, or Codex CLI version is reported",
            "Scanner version checks",
            "execution were also not performed",
            "Missing scanner",
            "evidence is not a clean scan",
            "zero published target",
            "does not mean zero vulnerabilities",
        ]
        missing = [term for term in required if term.lower() not in self.report.lower()]
        self.assertEqual([], missing)

    def test_report_records_exact_public_synthetic_rows(self) -> None:
        required = [
            SOURCE_COMMIT,
            CORPUS_VERSION,
            "genai-repo-auditor-synthetic-core",
            "synthetic-reference-rules-v2",
            "reference-review-all-signals-v1",
            "reference-review-high-severity-gate-v1",
            "fixture-reference-review",
            "high-severity-review-gate",
            "| TP / FP / FN / TN | 10 / 0 / 0 / 10 |",
            "| Precision | 1.000000 |",
            "| Recall | 1.000000 |",
            "| F1 | 1.000000 |",
            "| Severity agreement | 10 / 10 (1.000000) |",
            "| Target coverage | 20 / 20 (1.000000) |",
            "| Human-review-required cases | 10 |",
            "7 / 0 / 3 / 10",
            "0.700000",
            "0.823529",
        ]
        missing = [term for term in required if term not in self.report]
        self.assertEqual([], missing)
        self.assertIn(
            "synthetic regression results",
            self.report.lower(),
        )
        self.assertIn(
            "not product-wide precision",
            self.report.lower(),
        )

    def test_report_records_only_approved_dogfood_aggregates(self) -> None:
        required = [
            "| Targets generated / selected / deep-researched | 47 / 3 / 3 |",
            "| Candidate findings after human review | 4 Medium |",
            "| Status after human review | 1 Confirmed / 3 Probable |",
            "| Downgraded or invalidated | 0 |",
            "| Scanner adapters planned / executed | 2 / 0 |",
            "| Workflow interruptions / checkpoint resumes | 1 / 1 |",
            "| Approximate hands-on operator review time | 45 minutes |",
            "| Workflow benchmark gates | 7 passed / 0 warnings / 0 failed |",
            "| Evidence graph | 55 nodes / 18 edges |",
            "| Issue dry-run would-create / warnings / published | 0 / 0 / 0 |",
        ]
        missing = [term for term in required if term not in self.report]
        self.assertEqual([], missing)
        source_required = [
            "| Targets generated | 47 |",
            "| Targets selected | 3 |",
            "| Targets deep-researched | 3 |",
            "| Targets left queued | 44 |",
            "| Candidate findings after human review | 4 |",
            "| Candidate severity distribution | 4 Medium |",
            "| Candidate status distribution | 1 Confirmed / 3 Probable |",
            "| Downgraded or invalidated after human review | 0 |",
            "| Critical or High candidates | 0 |",
            "| Scanner adapters planned | 2 |",
            "| Scanner adapters executed | 0 |",
            "| Authorized scanner/external artifacts ingested | 0 |",
            "| Normalized scanner leads triaged | 0 |",
            "| Benchmark gates | 7 passed / 0 warnings / 0 failed |",
            "| Evidence graph | 55 nodes / 18 edges |",
            "| Issue dry-run would-create count | 0 |",
            "| Issue dry-run warning count | 0 |",
            "| Audit-derived GitHub Issues published | 0 |",
            "One interruption and one",
            "checkpoint resume were recorded",
            "45 minutes",
        ]
        missing_source = [
            term for term in source_required if term not in self.dogfood_summary
        ]
        self.assertEqual([], missing_source)
        self.assertNotIn("Needs-human-review decisions after review", self.report)
        self.assertNotIn("patch validation | 0", self.report.lower())
        self.assertIn("does not publish a\npatch-validation count", self.report)

    def test_claim_matrix_records_wording_guardrails_and_approvers(self) -> None:
        for claim_id in range(1, 11):
            self.assertIn(f"CLM-{claim_id:03d}", self.matrix)
        required = [
            "Exact permitted wording",
            "Evidence",
            "Determinism",
            "Limitation / uncertainty",
            "Prohibited stronger wording",
            "Required approvers",
            "Security/disclosure reviewer",
            "maintainer",
            "production-wide precision",
            "guaranteed vulnerability discovery",
            "model, provider, scanner",
            "Pending",
            "Approved only when the merge review history",
            "Approved by accepting the merge",
        ]
        missing = [term for term in required if term.lower() not in self.matrix.lower()]
        self.assertEqual([], missing)

    def test_reproduction_is_fixed_offline_and_worker_free(self) -> None:
        required = [
            f"git checkout {SOURCE_COMMIT}",
            'test "$(cat VERSION)" = "0.4.0"',
            "bin/gra-efficacy-benchmark",
            "--compare",
            "cmp .test-tmp/public-evaluation/public-a.json",
            'report["safety"]["network_accessed"] is False',
            'report["safety"]["model_channel_used"] is False',
            'report["claim_guardrails"]["product_capability_claim_allowed"] is False',
            "Do not rerun a real-repository audit",
            "No worker/model or scanner execution row is included",
        ]
        missing = [term for term in required if term not in self.reproduction]
        self.assertEqual([], missing)
        self.assertNotIn("--worker", self.reproduction)
        self.assertNotIn("--network", self.reproduction)

    def test_public_docs_exclude_private_and_target_specific_material(self) -> None:
        forbidden = [
            ".codex-local",
            "/home/",
            "C:\\",
            "reports/findings.json",
            "reports/target-research",
            "packages/backend/",
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden if term.lower() in self.combined.lower()]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\bTGT-(?:AGENT-|PROVENANCE-)?\d+\b", self.combined))
        self.assertIsNone(re.search(r"\bSEC-\d+\b", self.combined))
        hashes = set(re.findall(r"\b[0-9a-f]{40}\b", self.combined, re.IGNORECASE))
        self.assertEqual({SOURCE_COMMIT}, hashes)

    def test_corpus_version_matches_public_manifest(self) -> None:
        corpus = json.loads(
            (REPO_ROOT / "benchmarks" / "corpus" / "core.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(CORPUS_VERSION, corpus["corpus_version"])
        self.assertEqual("genai-repo-auditor-synthetic-core", corpus["corpus_id"])
        self.assertEqual(20, len(corpus["cases"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

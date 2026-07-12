from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOGFOOD_TEMPLATES = REPO_ROOT / "templates" / "dogfood"
DOGFOOD_DOCS = REPO_ROOT / "docs"


class DogfoodTemplateTests(unittest.TestCase):
    maxDiff = None

    def test_json_templates_are_valid_and_placeholder_only(self) -> None:
        for path in sorted(DOGFOOD_TEMPLATES.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            rendered = json.dumps(data, sort_keys=True)
            forbidden = ["SECRET", "TOKEN", "PRIVATE KEY", "BEGIN RSA", "password="]
            self.assertFalse(
                any(term.lower() in rendered.lower() for term in forbidden),
                f"{path.relative_to(REPO_ROOT)} should not contain secret-like placeholders",
            )

    def test_public_safe_report_template_excludes_private_artifact_bodies(self) -> None:
        text = (DOGFOOD_TEMPLATES / "public-safe-report-template.md").read_text(encoding="utf-8").lower()
        required_cautions = [
            "private findings",
            "raw evidence",
            "attack-chain details",
            "proof payloads",
            "scanner raw",
            "codex transcripts",
            "remediation diffs",
        ]
        missing = [term for term in required_cautions if term not in text]
        self.assertEqual([], missing)

    def test_dry_run_issue_record_does_not_claim_publication_plan(self) -> None:
        record = json.loads((DOGFOOD_TEMPLATES / "run-record.example.json").read_text(encoding="utf-8"))
        commands = {entry["name"]: entry for entry in record["commands"]}
        dry_run_refs = set(commands["gra-issues --dry-run"]["artifact_refs"])
        plan_refs = set(commands["gra-issues --plan"]["artifact_refs"])
        self.assertNotIn("reports/issue-publication-plan.json", dry_run_refs)
        self.assertIn("reports/issue-publication-plan.json", plan_refs)

    def test_campaign_ledger_records_publication_and_retention_status(self) -> None:
        ledger = json.loads((DOGFOOD_TEMPLATES / "campaign-ledger.example.json").read_text(encoding="utf-8"))
        self.assertIn("runs", ledger)
        self.assertGreaterEqual(len(ledger["runs"]), 2)
        for run in ledger["runs"]:
            self.assertIn(run["publication_status"], {"private", "sanitized-public", "not-approved"})
            self.assertIn(run["retention_decision"], {"delete-after-review", "retain-local", "secure-archive"})
            self.assertIn("artifact_refs", run)
            self.assertNotIn("artifact_contents", run)

    def test_self_dogfood_summary_is_public_safe(self) -> None:
        summary = (REPO_ROOT / "docs" / "dogfood" / "SELF_DOGFOOD_SUMMARY.md").read_text(encoding="utf-8")
        required = [
            "public-safe summary",
            "excludes private finding bodies",
            "gra-issues --dry-run",
            "No Issues were created",
            "| Target commit | `",
        ]
        missing = [term for term in required if term not in summary]
        self.assertEqual([], missing)
        self.assertRegex(summary, r"\| Target commit \| `[0-9a-f]{40}` \|")
        forbidden = [
            "-----BEGIN",
            "ghp_",
            "xoxb-",
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "reports/chains.json",
            "reports/proofs.json",
            "reports/traces.json",
        ]
        leaked = [term for term in forbidden if term in summary]
        self.assertEqual([], leaked)

    def test_reporting_guide_keeps_internal_summaries_outside_git(self) -> None:
        reporting = (DOGFOOD_DOCS / "DOGFOOD_REPORTING.md").read_text(encoding="utf-8")
        self.assertIn(".codex-local/dogfood/", reporting)
        self.assertIn("outside Git by", reporting)
        self.assertNotIn("docs/dogfood/*_SUMMARY.md", reporting)

    def test_self_dogfood_backlog_is_structured_and_sanitized(self) -> None:
        backlog = (REPO_ROOT / "docs" / "dogfood" / "SELF_DOGFOOD_BACKLOG.md").read_text(encoding="utf-8")
        required_columns = [
            "| ID | Priority | Category | Severity | Impact | Proposed fix | Affected command/docs | Should become GitHub Issue? |",
            "| Category | Severity | Impact from this run | Proposed fix / disposition | Affected command/docs | Should become GitHub Issue? |",
        ]
        missing_columns = [column for column in required_columns if column not in backlog]
        self.assertEqual([], missing_columns)
        required_categories = [
            "usability",
            "target granularity",
            "false positive control",
            "metrics / benchmark",
            "evidence graph",
            "issue publication safety",
            "remediation / patch validation",
            "sandbox readiness",
            "scanner / external import",
            "docs / runbooks",
            "performance / cost",
        ]
        missing_categories = [category for category in required_categories if category not in backlog]
        self.assertEqual([], missing_categories)
        required_items = [
            "SDFB-001",
            "Make reconnaissance-only validation easier".lower(),
            "SDFB-002",
            "clarify `gra-issues --dry-run`",
            "Deferred",
            "private findings",
            "scanner raw output",
        ]
        backlog_lower = backlog.lower()
        missing_items = [item for item in required_items if item.lower() not in backlog_lower]
        self.assertEqual([], missing_items)
        forbidden = [
            "-----BEGIN",
            "ghp_",
            "xoxb-",
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "reports/chains.json",
            "reports/proofs.json",
            "reports/traces.json",
        ]
        leaked = [term for term in forbidden if term in backlog]
        self.assertEqual([], leaked)

    def test_public_recognition_materials_are_complete_and_public_safe(self) -> None:
        docs = {
            "launch": REPO_ROOT / "docs" / "dogfood" / "PUBLIC_LAUNCH_CHECKLIST.md",
            "blog": REPO_ROOT / "docs" / "dogfood" / "BLOG_OUTLINE_AI_APPSEC_HARNESS.md",
            "demo": REPO_ROOT / "docs" / "dogfood" / "DEMO_SCRIPT.md",
            "positioning": REPO_ROOT / "docs" / "dogfood" / "README_POSITIONING_NOTES.md",
        }
        for path in docs.values():
            self.assertTrue(path.exists(), f"missing {path.relative_to(REPO_ROOT)}")

        contents = {name: path.read_text(encoding="utf-8") for name, path in docs.items()}
        combined = "\n".join(contents.values())
        combined_lower = combined.lower()

        required_by_doc = {
            "launch": [
                "Public launch checklist",
                "Launch readiness gates",
                "Claim review checklist",
                "Disclosure boundary",
                "local-first",
                "vendor-neutral AppSec audit harness",
                "controlled GitHub Issue publication",
                "Stop conditions",
            ],
            "blog": [
                "Blog outline",
                "local-first AI AppSec audit harness",
                "Thesis",
                "Self-dogfood evidence",
                "ITDO_ERP4 business-application evidence",
                "Safety and disclosure model",
                "Claims table",
                "Editorial guardrails",
            ],
            "demo": [
                "Public demo script",
                "Demo goal",
                "Recommended safe path",
                "Optional live workflow narration",
                "Five-minute demo agenda",
                "Redaction and display rules",
                "Stop conditions",
            ],
            "positioning": [
                "README positioning notes",
                "Recommended conservative claim",
                "Proof points from dogfood",
                "Wording to prefer",
                "Wording to avoid",
                "Claim-to-evidence mapping",
                "Editorial approval checklist",
            ],
        }
        for name, required_terms in required_by_doc.items():
            doc_lower = contents[name].lower()
            missing = [term for term in required_terms if term.lower() not in doc_lower]
            self.assertEqual([], missing, name)

        required_links = [
            "PUBLIC_SELF_DOGFOOD_CASE_STUDY.md",
            "PUBLIC_ITDO_ERP4_CASE_STUDY.md",
            "DISCLOSURE_AND_PUBLICATION_POLICY.md",
            "DOGFOOD_REPORTING.md",
        ]
        missing_links = [term for term in required_links if term not in combined]
        self.assertEqual([], missing_links)

        forbidden_markers = [
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "raw scanner output",
            "remediation diffs",
            "exact exploitability steps",
            "mythos replacement",
            "zero-day finder",
            "fully autonomous security auditor",
            "automatic exploit generator",
            "automatic patcher",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden_markers if term.lower() in combined_lower]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", combined, re.IGNORECASE))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", combined))

    def test_public_itdo_erp4_case_study_is_public_safe(self) -> None:
        case_study = (REPO_ROOT / "docs" / "dogfood" / "PUBLIC_ITDO_ERP4_CASE_STUDY.md").read_text(encoding="utf-8")
        required_terms = [
            "Public ITDO_ERP4 AppSec dogfood case study",
            "initial dogfood pass",
            "preserves its historical",
            "two sets of values must not be combined",
            "Why ITDO_ERP4 is a realistic AppSec target",
            "Selected scope",
            "Architecture / workflow diagram",
            "Workflow stages that were useful",
            "target queue",
            "scanner ingestion",
            "Adversarial validation",
            "Chain synthesis",
            "Safe proof artifacts",
            "Metrics and benchmark",
            "Evidence graph",
            "Issue publication planning",
            "Sanitized metrics categories",
            "Targets generated",
            "First-wave candidates considered",
            "Targets deep-researched in this pass",
            "Confirmed findings approved for public Issue publication",
            "Issue dry-run would-create Issue count",
            "No GitHub Issues were created from audit output",
            "How private details stayed out of public output",
            "Business value demonstrated",
            "local-first",
            "vendor-neutral AI agent harness",
            "evidence validation",
            "Controlled GitHub Issue publication",
        ]
        case_study_lower = case_study.lower()
        missing = [term for term in required_terms if term.lower() not in case_study_lower]
        self.assertEqual([], missing)
        self.assertRegex(case_study, r"\| Targets generated \| [0-9]+ \|")
        self.assertRegex(case_study, r"\| Benchmark status \| [0-9]+ gates passed\. \|")
        self.assertRegex(case_study, r"\| Evidence graph summary \| [0-9]+ nodes / [0-9]+ edges\. \|")
        self.assertRegex(case_study, r"\| Issue dry-run would-create Issue count \| [0-9]+ \|")
        forbidden = [
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "raw scanner output",
            "remediation diffs",
            "exact exploitability steps",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden if term.lower() in case_study_lower]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", case_study))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", case_study))

    def test_itdo_erp4_second_dogfood_summary_is_aggregate_only(self) -> None:
        summary = (
            REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md"
        ).read_text(encoding="utf-8")
        required_terms = [
            "public-safe aggregate summary",
            "Targets selected | 3",
            "Targets deep-researched | 3",
            "Scanner adapters planned | 2",
            "Scanner adapters executed | 0",
            "Issue dry-run would-create count | 0",
            "Classify resumable provider failures",
            "Reduce deterministic target-queue noise",
            "Expose explicit dry-run counts",
            "Prevent stale aggregate metrics",
            "Report scanner prerequisite absence uniformly",
            "only campaign result proposed for Git",
            "approval is determined",
            "pull-request review",
            "requires separate human approval",
        ]
        summary_lower = summary.lower()
        missing = [term for term in required_terms if term.lower() not in summary_lower]
        self.assertEqual([], missing)

        forbidden = [
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "reports/findings.json",
            "reports/target-research",
            "packages/backend/",
            "exact exploitability steps",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden if term.lower() in summary_lower]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", summary))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", summary))

    def test_public_self_dogfood_case_study_is_public_safe(self) -> None:
        case_study = (REPO_ROOT / "docs" / "dogfood" / "PUBLIC_SELF_DOGFOOD_CASE_STUDY.md").read_text(encoding="utf-8")
        required_terms = [
            "Public self-dogfood case study",
            "Architecture / workflow diagram",
            "Why self-dogfood was run",
            "Workflow stages exercised",
            "Sanitized metrics categories",
            "What validation and issue planning prevented",
            "Product improvements identified",
            "local-first",
            "vendor-neutral",
            "AI agent harness",
            "Evidence validation",
            "Controlled GitHub Issue publication",
            "No Issues were created",
            "Benchmark gates passed",
            "Agent-surface review leads",
            "review leads, not confirmed vulnerabilities",
        ]
        case_study_lower = case_study.lower()
        missing = [term for term in required_terms if term.lower() not in case_study_lower]
        self.assertEqual([], missing)
        forbidden = [
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "raw scanner output",
            "remediation patch details",
            "exact exploitability steps",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        leaked = [term for term in forbidden if term.lower() in case_study_lower]
        self.assertEqual([], leaked)

    def test_internal_effectiveness_report_template_is_structured_and_sanitized(self) -> None:
        template = (REPO_ROOT / "docs" / "dogfood" / "INTERNAL_EFFECTIVENESS_REPORT_TEMPLATE.md").read_text(encoding="utf-8")
        required_terms = [
            "Internal dogfood effectiveness report template",
            "self-dogfood run and the ITDO_ERP4 dogfood run",
            "Executive summary",
            "Scope and authorization",
            "Repositories reviewed",
            "Workflow steps executed",
            "Metrics summary",
            "Benchmark summary",
            "Evidence graph summary",
            "Findings funnel",
            "Remediation candidate summary",
            "Human review burden",
            "Lessons learned",
            "Product improvement backlog",
            "Public-safe material candidates",
            "Target queue",
            "Adversarial validation",
            "Chain synthesis",
            "Issue publication planning",
            "Issue dry-run would-create Issue count",
            "Public product-improvement Issues",
            "internal/private by default",
        ]
        missing = [term for term in required_terms if term not in template]
        self.assertEqual([], missing)
        forbidden = [
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "raw scanner output",
            "remediation diffs",
            "-----BEGIN",
            "ghp_",
            "xoxb-",
        ]
        template_lower = template.lower()
        leaked = [term for term in forbidden if term.lower() in template_lower]
        self.assertEqual([], leaked)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", template))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", template))

    def test_itdo_erp4_planning_docs_are_complete_and_public_safe(self) -> None:
        docs = {
            "scope": REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_SCOPE.md",
            "targets": REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_TARGET_SELECTION.md",
            "boundaries": REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_REPORTING_BOUNDARIES.md",
            "summary_template": REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_INTERNAL_SUMMARY_TEMPLATE.md",
            "scanner_evidence": REPO_ROOT / "docs" / "dogfood" / "ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md",
        }
        for path in docs.values():
            self.assertTrue(path.exists(), f"missing {path.relative_to(REPO_ROOT)}")

        scope = docs["scope"].read_text(encoding="utf-8")
        targets = docs["targets"].read_text(encoding="utf-8")
        boundaries = docs["boundaries"].read_text(encoding="utf-8")
        summary_template = docs["summary_template"].read_text(encoding="utf-8")
        scanner_evidence = docs["scanner_evidence"].read_text(encoding="utf-8")
        combined = "\n".join([scope, targets, boundaries, summary_template, scanner_evidence])

        required_scope_terms = [
            "planning material only",
            "itdojp/ITDO_ERP4",
            "RBAC and visibility boundaries",
            "Agent-First write guardrails",
            "CI, supply-chain, and secret-detection posture",
            "gra-audit --repo itdojp/ITDO_ERP4 --mode prepare",
            "gra-issues --run \"$RUN\" --dry-run",
        ]
        missing_scope = [term for term in required_scope_terms if term not in scope]
        self.assertEqual([], missing_scope)

        required_target_terms = [
            "ERP4-SCOPE-01",
            "ERP4-SCOPE-02",
            "ERP4-SCOPE-03",
            "RBAC and user/project visibility",
            "Financial state transitions",
            "CI, secret scanning, supply chain, and SBOM",
            "Select at most six".lower(),
        ]
        targets_lower = targets.lower()
        missing_targets = [term for term in required_target_terms if term.lower() not in targets_lower]
        self.assertEqual([], missing_targets)

        required_boundary_terms = [
            "GitHub Security Advisories",
            "Public GitHub Issues are not the first reporting channel",
            "gra-issues --dry-run",
            "Artifact handling matrix",
            "GenAI Repo Auditor product friction",
            "Local retention or cleanup decision is recorded",
        ]
        missing_boundaries = [term for term in required_boundary_terms if term not in boundaries]
        self.assertEqual([], missing_boundaries)

        required_template_terms = [
            "Copy this template to a local or restricted location",
            "Findings funnel counts",
            "Issue dry-run created Issues",
            "Product-improvement observations",
            "--allow-public",
            "Do not include",
        ]
        missing_template = [term for term in required_template_terms if term not in summary_template]
        self.assertEqual([], missing_template)
        self.assertIn("runs/itdojp__ITDO_ERP4/RUN_ID", summary_template)

        required_scanner_terms = [
            "ITDO_ERP4 scanner and supply-chain evidence summary",
            "No authorized current-run scanner artifacts were available",
            "CodeQL SARIF",
            "npm audit JSON",
            "not a native dependency-posture input",
            "CycloneDX SBOM",
            "Trivy JSON",
            "Grype JSON",
            "OpenSSF Scorecard JSON",
            "Scanner raw outputs remain local/private",
            "Normalized scanner leads are review leads",
            "not automatically confirmed findings",
            "gra-ingest --run \"$RUN\" --tool codeql",
            "gra-scanner-triage --run \"$RUN\"",
            "gra-targets --run \"$RUN\" --generate",
            "Metrics/evidence graph update",
            "Issue dry-run would-create Issue count",
            "never publishes GitHub Issues",
            "separate explicit approval",
        ]
        missing_scanner = [term for term in required_scanner_terms if term not in scanner_evidence]
        self.assertEqual([], missing_scanner)

        sensitive_refs = [
            ".codex-local/tmp/",
            ".log",
            "issue-publication-plan.json",
        ]
        leaked_sensitive_refs = [term for term in sensitive_refs if term in combined]
        self.assertEqual([], leaked_sensitive_refs)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", summary_template))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", summary_template))
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", scanner_evidence))
        self.assertIsNone(re.search(r"\b20\d{6}T\d{6}[+-]\d{4}\b", scanner_evidence))

        forbidden = [
            "-----BEGIN",
            "ghp_",
            "xoxb-",
            "ATTACK_CHAINS.md",
            "PROOFS.md",
            "TRACE.md",
            "reports/chains.json",
            "reports/proofs.json",
            "reports/traces.json",
        ]
        leaked = [term for term in forbidden if term in combined]
        self.assertEqual([], leaked)


if __name__ == "__main__":
    unittest.main(verbosity=2)

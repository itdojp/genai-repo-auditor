# Changelog

## v0.2.0 - 2026-05-24

Release readiness and advanced posture workflow update.

- Added consistent `--version` reporting across all `gra-*` commands and release metadata consistency tests.
- Added local install smoke validation, ShellCheck validation, CodeQL hardening, and offline self-validation coverage for prepare and minimal exec-mode audit paths.
- Added staged workflow integration tests for recon, target generation, target research, and variant analysis command paths.
- Added immutable GitHub Issue publication plans with plan/apply verification, public-disclosure safeguards, and duplicate prevention coverage.
- Added controlled taxonomy profiles for OWASP LLM, AI Agent, MCP, CWE, and supply-chain risk metadata.
- Added AI agent and MCP surface discovery with deterministic posture artifacts and generated target queue entries.
- Added adversarial prompt-injection fixtures to regression-test untrusted repository content boundaries.
- Added release provenance posture checks for workflows, attestations, container/build metadata, and generated provenance review targets.
- Added OpenSSF Scorecard ingestion with deterministic supply-chain posture reports, dashboard summaries, and review targets.
- Added SBOM and dependency graph ingestion for CycloneDX, SPDX/GitHub Dependency Graph, Syft, and Trivy SBOM exports, including `dependencies.json` and `DEPENDENCY_RISK.md` artifacts.
- Added local artifact cleanup guidance and a guarded cleanup helper for run directories, batch artifacts, and SQLite stores.
- Added Japanese core workflow documentation and expanded command, report contract, scanner, security, and release process documentation.
- Preserved local-first safety boundaries: scanner, Scorecard, SBOM, dependency, provenance, and agent/MCP posture records remain evidence until reviewed and are not automatically confirmed findings.

## v0.1.0

Initial public import candidate.

- Renamed the project to GenAI Repo Auditor.
- Adopted vendor-neutral `gra-*` command names.
- Added local-first defensive repository audit workflow.
- Added staged workflow: `prepare -> recon -> targets -> research -> validation -> variant analysis -> scanner triage -> reporting -> issue creation`.
- Added target queue support with `reports/targets.json` and `templates/reports/targets.schema.json`.
- Added scanner result ingestion and AI-assisted scanner triage prompts.
- Added variant analysis prompts in exec and `/goal` modes.
- Added local dashboard, SARIF conversion, and SQLite store.
- Added public OSS metadata: README, Apache-2.0 license, SECURITY.md, CONTRIBUTING.md, TRADEMARKS.md, CODEOWNERS, issue templates, and lint workflow.
- Preserved defensive-only policy: no exploit generation, no external DAST by default, no production probing, and no autonomous remediation.

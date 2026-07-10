# Changelog

## v0.4.0 - 2026-07-10

Release-readiness, controlled remediation, observability, and public-safe dogfood workflow update.

- Added vendor-neutral AI worker profiles, worker readiness reporting with `gra-agent-check`, and explicit model/effort/worker metadata boundaries.
- Added sandbox profiles and `gra-sandbox-check` so executable validation can fail closed on filesystem, network, runtime, and target-isolation requirements.
- Added the non-executing `gra-scan` adapter registry and safe planning contract for approved offline-capable Gitleaks and Syft workflows.
- Added bounded remediation candidates with `gra-remediate`, disposable worktree enforcement, and a patch-validation ladder that keeps generated changes local until reviewed.
- Added the known-findings novelty ledger and multi-vote adversarial validation routing to distinguish new, duplicate, downgraded, invalidated, and human-review-required results.
- Added structured command events, run-state pause/resume/blocked handling, canonical Issue publication and duplicate-decision ledgers, taxonomy preflight normalization, gapfill metrics, and artifact-retention manifest hygiene.
- Added public-safe metrics summaries, workflow-health benchmark gates, evidence graph reporting, and external finding import without promoting imported or scanner evidence directly to confirmed findings.
- Added explicit no-findings reporting and a recon-only workflow profile so intentionally scoped omissions remain distinct from failures or missing evidence.
- Added operator and customer runbooks, a self-dogfood campaign, an ITDO_ERP4 dogfood campaign plan, internal reporting templates, public-safe case studies, and conservative launch/demo materials.
- Hardened advanced validation and publication-plan binding, trace reachability safety, worktree separation checks, safe proof command records, target review-depth serialization, and Codex execution configuration.
- Added reproducible source archives, SHA-256 checksums, a CycloneDX source SBOM, guarded GitHub Release creation, and GitHub build-provenance/SBOM attestations through an explicit human-dispatched release workflow.
- Preserved local-first and defensive-only boundaries: release archives exclude local audit runs, scanner output, target clones, SQLite stores, transcripts, findings, proof artifacts, remediation patches, Issue drafts, credentials, and private security data.

## v0.3.0 - 2026-05-27

Advanced chain, validation, proof, coverage, and reachability workflow update.

- Added structured target quality gates and finding assessment dimensions for bug existence, attacker reachability, boundary crossing, impact, chain membership, and assessment notes.
- Added independent adversarial validation with `gra-adversarial-validate`, `reports/validation.json`, `reports/VALIDATION.md`, and `templates/reports/validation.schema.json`.
- Added defensive chain synthesis with `gra-chains`, `reports/chains.json`, `reports/ATTACK_CHAINS.md`, and `templates/reports/chains.schema.json`.
- Added safe local proof artifacts with `gra-proofs`, `reports/proofs.json`, `reports/PROOFS.md`, and `templates/reports/proofs.schema.json` while preserving defensive-only, local-first boundaries.
- Added target coverage metadata and gapfill requeue support with `gra-gapfill`, `reports/COVERAGE.md`, and `reports/gapfill-targets.json`.
- Added experimental/P3 cross-repo trace reachability with `gra-trace`, `reports/traces.json`, `reports/TRACE.md`, and `templates/reports/traces.schema.json`; reachability evidence remains distinct from exploit proof.
- Expanded report validation, dashboard, SARIF, run-manifest, command reference, report contract, normal/staged/issue workflow, security model, and Japanese operator documentation for the advanced workflow.
- Updated `MANIFEST.md` to cover the current command, prompt, schema/template, taxonomy, and public documentation surface, with regression tests to prevent manifest drift.
- Preserved safety constraints: no generated audit artifacts, scanner outputs, cloned repositories, credentials, secrets, private findings, exploit payloads, or production probing are included in the release metadata.

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

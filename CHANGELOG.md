# Changelog

## v0.5.0 - 2026-07-12

Workflow orchestration, cross-platform packaging, and security-efficacy evaluation update.

- Added Python package metadata, installed `gra-*` console scripts, resource discovery, and a Linux/macOS/Windows Python 3.10-3.12 install matrix with installed prepare, workflow execute/failure/resume, and efficacy-validation smoke coverage.
- Added TestPyPI-first OIDC trusted-publishing readiness with exact tag/version/main/GitHub-Release binding, hash-locked build tooling, fail-closed protected-environment markers, wheel/sdist validation and independent install smoke tests, no long-lived PyPI token, and explicit human account/project activation; Python package metadata now fails closed outside the tested Python 3.10-3.12 window.
- Added `gra-doctor` platform, filesystem-safety, runtime, and credential-source-name diagnostics, plus explicit native Windows, WSL2, Linux, macOS, PowerShell, container, and gVisor support boundaries.
- Added `gra-run` declarative workflow profiles with non-executing plans, explicit bounded execution, dependency-aware stage ranges/skips, immutable command fingerprints, safe checkpoints, exact resume, and local-only execution summaries.
- Added workflow execution and expanded v2 command-event reporting so metrics and evidence graphs distinguish succeeded, failed, externally blocked, scoped-out, and resumed work without copying prompts, findings, evidence, credentials, or private reasoning.
- Added safe offline scanner adapter planning and explicit container/gVisor execution with digest-pinned pre-pulled images, disabled network access, read-only targets, bounded resources/output, redacted ingestion, and aggregate scanner-run reporting; scanner results remain review leads.
- Added the versioned 20-case public synthetic efficacy corpus with ten positive/control pairs across seven categories, content-bound integrity, closed schemas, package-resource validation, and public-safety checks.
- Added deterministic `gra-efficacy-benchmark` scoring for TP/FP/FN/TN, precision, recall, F1, severity agreement, target coverage, and human-review counts without changing workflow-health `gra-benchmark` semantics.
- Added fixed-input efficacy configuration comparison with recorded stage differences and an explicit opt-in isolated worker-backed row; deterministic and non-deterministic results remain distinct and model/provider superiority claims remain prohibited.
- Added a validation-only private holdout protocol and `gra-efficacy-holdout` aggregate validator that never loads private fixtures and keeps private corpus, prompt, transcript, raw response, and adjudication material outside releases.
- Expanded the primary onboarding path around a shared runs directory, `gra-doctor`, `gra-audit --mode prepare`, and reviewed `gra-run` plan/execute/resume operation while preserving supervised individual commands.
- Added a second authorized ITDO_ERP4 dogfood aggregate and a public efficacy/operations report with source-bound synthetic results, explicit holdout/scanner/worker absence states, reproducible commands, and a claim-evidence approval matrix; no target-specific findings or private artifacts are included.
- Modularized report validation and Issue-publication policy/ledger helpers while preserving CLI contracts, closed schemas, fail-closed path handling, dry-run publication controls, and local-first release exclusions.
- Added closed, sanitized `gra-issues --dry-run` summaries at `reports/issue-dry-run-summary.json` and `reports/ISSUE_DRY_RUN_SUMMARY.md`, with selection/publication count partitions, declared offline visibility, no GitHub lookup or mutation, no immutable-plan write, advanced-validation and local-ledger duplicate classification, and direct metrics/dashboard/benchmark consumption.
- Added bounded run-relative dependency fingerprints for derived reports, explicit `fresh` / `stale` / `missing_dependency` / `not_applicable` status, opt-in `gra-validate-report --check-freshness`, safe regeneration guidance, publication-plan freshness blocking, and a SQLite import marker that excludes database paths.
- Migration and compatibility: use one workflow profile per checkpoint; review every plan before execution; native Windows execution remains bounded by documented platform support; scanner execution requires an approved local runtime and pre-pulled immutable image; worker-backed efficacy comparison remains explicit, optional, and non-deterministic.
- Preserved human-controlled release and disclosure boundaries: this preparation changes release metadata only, creates no tag or GitHub Release, and does not include audit runs, target clones, scanner output, findings, transcripts, holdout records, proof/remediation artifacts, Issue drafts, credentials, or private security data.

## v0.4.0 - 2026-07-10

Release-readiness, controlled remediation, observability, and public-safe dogfood workflow update.

- Added vendor-neutral AI worker profiles, worker readiness reporting with `gra-agent-check`, and explicit model/effort/worker metadata boundaries.
- Added sandbox profiles and `gra-sandbox-check` so executable validation can fail closed on filesystem, network, runtime, and target-isolation requirements.
- Added the non-executing `gra-scan` adapter registry and safe planning contract for approved offline-capable Gitleaks and Syft workflows.
- Added explicit offline `gra-scan --execute` with digest-pinned pre-pulled images, enforced local container isolation, bounded output/results/time, and review-only raw artifacts.
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

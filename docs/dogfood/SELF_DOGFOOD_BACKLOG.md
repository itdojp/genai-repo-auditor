# Self-dogfood product-improvement backlog

This backlog converts the public-safe self-dogfood observations in
[`SELF_DOGFOOD_SUMMARY.md`](SELF_DOGFOOD_SUMMARY.md) into product-oriented work
items for `genai-repo-auditor`. It is planning material, not a target-repository
finding report.

The backlog intentionally excludes private finding details, raw evidence,
chain/proof/trace details, scanner raw output, Codex transcripts, issue draft
text, dashboard content, remediation diffs, credentials, and local run artifacts.
It relies only on the sanitized observations already approved for this public
repository document.

## Source observations used

| Source observation | Backlog interpretation |
|---|---|
| A reconnaissance-only run did not naturally produce `reports/findings.json`. | Operators need an explicit, safe way to record a no-confirmed-finding run before validation, metrics, benchmark, evidence graph, dashboard, or issue dry-run stages. |
| `gra-issues --dry-run` completed safely with zero created Issues and zero warnings. | Dry-run remains safe, but the output wording should make clear which artifacts are previews and which are immutable publication plans. |
| Metrics and benchmark commands worked after an empty findings artifact existed. | A compact summary would reduce manual extraction for dogfood reports and release notes. |
| The evidence graph was sparse because deeper stages were intentionally skipped. | A recon-only profile should mark skipped advanced artifacts as intentional rather than unexplained absence. |

## Prioritization policy

| Priority | Meaning |
|---|---|
| P1 | Medium-severity product friction observed directly in the run; should become a GitHub Issue. |
| P2 | Low-severity improvement observed directly in the run; create an Issue when it aligns with the current release plan. |
| Deferred | The category was not exercised or had no actionable evidence in this bounded run. Do not create an Issue from this run alone. |

## Actionable backlog items

| ID | Priority | Category | Severity | Impact | Proposed fix | Affected command/docs | Should become GitHub Issue? |
|---|---|---|---|---|---|---|---|
| SDFB-001 | P1 | usability | Medium | Operators must know how to represent a safe no-confirmed-finding run. Without a clear path, validation and reporting stages require manual creation of an empty findings artifact. | Add a documented helper or command mode that writes an explicit empty findings artifact with a required rationale, target metadata, and no finding bodies. Include a runbook step for recon-only evaluations. | `gra-recon`, `gra-validate-report`, `gra-metrics`, `gra-benchmark`, `docs/DOGFOOD_RUNBOOK.md`, `docs/COMMAND_REFERENCE.md` | Yes |
| SDFB-002 | P1 | issue publication safety | Medium | The dry-run output can be mistaken for an immutable publication plan, which can confuse human approval workflows even when no Issues are created. | Rename or annotate dry-run preview fields so operators can distinguish preview output from `--plan` output; add an explicit boolean such as `plan_written=false` to the dry-run ledger. | `gra-issues`, `docs/ISSUE_WORKFLOW.md`, `docs/DOGFOOD_REPORTING.md` | Yes |
| SDFB-003 | P2 | metrics / benchmark | Low | Dogfood summaries currently require manual extraction of headline counts from richer metrics and benchmark artifacts. This increases reporting effort and consistency risk. | Add or document a stable compact `summary` object for counts commonly used in dogfood reports, including confirmed findings, publication warnings, evidence graph size, and benchmark gate totals. | `gra-metrics`, `gra-benchmark`, `docs/METRICS.md`, `docs/BENCHMARKING.md` | Consider |
| SDFB-004 | P2 | evidence graph | Low | Recon-only dogfood runs intentionally skip target research and advanced evidence stages, so sparse evidence-graph output can look incomplete rather than intentionally scoped. | Add a documented recon-only dogfood profile that records intentionally skipped stages in metrics, benchmark, and evidence graph summaries without treating them as failures. | `gra-benchmark`, `gra-evidence-graph`, `docs/EVIDENCE_GRAPH.md`, `docs/DOGFOOD_RUNBOOK.md`, `docs/ADVANCED_WORKFLOW_DECISION_TABLE.md` | Consider |

## Deferred category notes

These categories are part of the dogfood backlog taxonomy, but the self-dogfood
run did not produce actionable evidence for them. They should remain deferred
until a future run exercises the relevant stage or records a concrete failure.

| Category | Severity | Impact from this run | Proposed fix / disposition | Affected command/docs | Should become GitHub Issue? |
|---|---|---|---|---|---|
| target granularity | Deferred | Target generation and target research were intentionally not executed, so the run produced no evidence about target size, prioritization quality, or target queue usability. | Revisit after a scoped run exercises `gra-targets` and at least one bounded target-research cycle. | `gra-targets`, `gra-research`, `docs/TARGET_QUEUE.md` | No |
| false positive control | Deferred | No confirmed or candidate findings were generated, and adversarial validation was not exercised. | Revisit after a run with reviewed findings and validation votes. | `gra-adversarial-validate`, `docs/ADVERSARIAL_VALIDATION.md` | No |
| remediation / patch validation | Deferred | Remediation was intentionally out of scope; no candidate patch or validation result exists. | Revisit only after owner-approved remediation planning is executed on a validated finding. | `gra-remediate`, `docs/REMEDIATION_WORKFLOW.md` | No |
| sandbox readiness | Deferred | The model-backed reconnaissance path completed with network disabled, and no sandbox failure was recorded in the sanitized summary. | Keep existing sandbox guidance; open a follow-up only if a future run records a concrete preflight or execution failure. | `gra-agent-check`, `docs/SANDBOX_PROFILES.md`, `docs/STAGED_AGENTIC_WORKFLOW.md` | No |
| scanner / external import | Deferred | Scanner import and external finding ingestion were intentionally not run. | Revisit after a run imports bounded, redacted scanner leads. | `gra-ingest`, `gra-scanner-triage`, `gra-import-findings`, `docs/SCANNER_INTEGRATION.md`, `docs/EXTERNAL_FINDING_IMPORT.md` | No |
| docs / runbooks | Deferred | The actionable documentation updates are already represented by SDFB-001, SDFB-002, and SDFB-004. No separate runbook-only defect was observed. | Track documentation updates as part of the actionable items rather than opening a duplicate standalone Issue. | `docs/DOGFOOD_RUNBOOK.md`, `docs/DOGFOOD_REPORTING.md`, `docs/COMMAND_REFERENCE.md` | No |
| performance / cost | Deferred | The public-safe summary did not include duration, token, or cost measurements. | Do not infer cost or performance work from this run. Add measurement requirements to a future run if needed. | `gra-metrics`, `docs/METRICS.md` | No |

## Issue recommendation order

1. SDFB-001: make reconnaissance-only validation easier.
2. SDFB-002: clarify `gra-issues --dry-run` preview versus publication-plan wording.
3. SDFB-003: add or document a compact top-level metrics summary.
4. SDFB-004: add a recon-only dogfood profile for intentionally skipped advanced stages.

Recommend creating only the first two Issues in the next backlog-publication
step unless the release owner decides to include low-severity reporting
ergonomics in the same planning cycle.

## Safety and publication boundary

- This document is public-safe because it contains workflow observations,
  product backlog categories, and command/doc references only.
- It does not claim that the target repository has vulnerabilities.
- It does not publish private findings, evidence, issue drafts, scanner output,
  transcripts, dashboards, or remediation artifacts.
- Any future Issue created from this backlog should quote the relevant backlog
  item only, not local run artifacts.

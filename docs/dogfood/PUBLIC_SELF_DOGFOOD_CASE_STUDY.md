# Public self-dogfood case study: GenAI Repo Auditor reviewing itself

This public-safe case study explains how `genai-repo-auditor` was used to review
`itdojp/genai-repo-auditor` itself. It is written for README, blog, or release
planning audiences that need to understand the workflow without receiving local
audit artifacts or vulnerability details.

Source material is limited to [`SELF_DOGFOOD_SUMMARY.md`](SELF_DOGFOOD_SUMMARY.md),
[`SELF_DOGFOOD_BACKLOG.md`](SELF_DOGFOOD_BACKLOG.md),
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md),
[`../OPERATING_MODEL.md`](../OPERATING_MODEL.md),
[`../WORKFLOW_OVERVIEW.md`](../WORKFLOW_OVERVIEW.md), and
[`../ADVANCED_WORKFLOW_DECISION_TABLE.md`](../ADVANCED_WORKFLOW_DECISION_TABLE.md).

## Public-safe boundary

This document uses workflow narrative, bounded counts, and product lessons only.
It does not include finding bodies, local evidence records, target code excerpts,
advanced chain/proof/trace contents, scanner records, patch content, transcripts,
secrets, or step-by-step exploit instructions.

## Why self-dogfood was run

The project is a local-first, vendor-neutral, GenAI-assisted repository security
auditor. Self-dogfood was run to validate that the tool's own operating model is
understandable, repeatable, and safe before using it as evidence for other
repositories.

The run asked three product questions:

1. Can the AI agent harness create useful local reconnaissance artifacts without
   sending audit reports to a central service?
2. Can evidence validation, metrics, benchmark, evidence graph, dashboard, and
   controlled GitHub Issue publication stages operate on a no-confirmed-finding
   run?
3. Which product improvements become visible when operators try the workflow on
   the project itself?

## Architecture / workflow diagram

```text
authorized repository
  -> local run directory under runs/
  -> shallow target clone and rendered prompts
  -> AI agent harness with network disabled for this run
  -> local reconnaissance and posture reports
  -> explicit empty findings artifact for no-confirmed-finding evaluation
  -> validation / metrics / benchmark / evidence graph / dashboard
  -> issue dry-run preview only
  -> sanitized product backlog and public-safe case study
```

The important boundary is that generated run artifacts stay local. Public output
is derived from reviewed counts and workflow observations, not from raw local
reports.

## Workflow stages exercised

| Stage | Status | Public-safe outcome |
|---|---|---|
| `gra-audit --mode prepare` | Completed | Created an isolated local run directory and target clone. |
| `gra-recon` | Completed | Produced local reconnaissance and posture artifact categories. |
| Explicit empty findings artifact | Added locally | Represented a no-confirmed-finding evaluation without inventing findings. |
| `gra-validate-report` | Passed | Confirmed report contract compatibility for the bounded run. |
| `gra-metrics` | Completed | Produced count-oriented metrics for reporting. |
| `gra-benchmark` | Passed | Reported available dogfood quality gates as passing. |
| `gra-evidence-graph` | Completed | Generated a sparse graph appropriate for the intentionally bounded scope. |
| `gra-dashboard` | Completed | Rendered a local dashboard; dashboard content was not published. |
| `gra-issues --dry-run` | Completed | Previewed publication behavior; No Issues were created. |

## Sanitized metrics categories

| Category | Public-safe count/status | Interpretation |
|---|---:|---|
| Confirmed findings in public summary | 0 | The run was a workflow/product evaluation, not a finding disclosure. |
| Issue-recommended findings | 0 | No finding moved toward publication. |
| Issue dry-run created Issues | 0 | Dry-run remained a preview and did not publish. |
| Issue-publication warnings | 0 | The empty-finding run did not surface publication warnings. |
| Benchmark gates passed | 7 | Quality gates were useful as a quick health signal. |
| Benchmark warnings | 0 | No benchmark warnings were recorded in the sanitized summary. |
| Benchmark failures | 0 | No benchmark failures were recorded in the sanitized summary. |
| Evidence graph nodes | 1 | Sparse graph reflected the bounded, no-confirmed-finding scope. |
| Evidence graph edges | 0 | No multi-artifact finding relationships were present. |
| Agent-surface review leads | 110 | Review leads, not confirmed vulnerabilities. |
| High-risk agent-surface review leads | 66 | Prioritization signal only; review leads, not confirmed vulnerabilities. |
| Medium-risk agent-surface review leads | 44 | Prioritization signal only. |

The metrics were useful because they separated product-health signals from
security disclosure decisions. Counts could be shared after review; local report
contents stayed private.

## What validation and issue planning prevented

The self-dogfood run showed that publication can remain controlled even when
multiple report artifacts exist locally:

- `gra-validate-report` required a structured findings artifact before later
  reporting stages could be evaluated.
- The explicit empty findings artifact made the no-confirmed-finding state clear
  instead of relying on missing files.
- `gra-issues --dry-run` exercised publication-preview logic without creating
  GitHub Issues.
- The disclosure policy kept public wording focused on workflow behavior and
  product improvements.

Adversarial validation and chain synthesis were not needed for this bounded run
because no Critical/High candidate finding was advanced. The case study therefore
describes those stages as available safeguards for future high-impact cases, not
as results from this self-dogfood pass.

## Product improvements identified

The run produced product feedback rather than target-repository findings:

| Improvement | Severity | Why it matters | Follow-up route |
|---|---|---|---|
| Make reconnaissance-only validation easier | Medium | Operators need a first-class way to record no-confirmed-finding evaluations. | Product Issue candidate. |
| Clarify `gra-issues --dry-run` wording | Medium | Operators must distinguish preview artifacts from immutable publication plans. | Product Issue candidate. |
| Add a compact metrics summary | Low | Public-safe reports need stable headline counts without manual extraction. | Product backlog candidate. |
| Add a recon-only dogfood profile | Low | Intentionally skipped advanced stages should be marked as scoped, not missing. | Product backlog candidate. |

These follow-ups are about `genai-repo-auditor` usability and reporting. They do
not claim vulnerabilities in the reviewed repository.

## Product positioning demonstrated

| Positioning point | Demonstrated by |
|---|---|
| Local-first | Run artifacts, cloned repository content, transcripts, dashboards, and reports stayed under local `runs/` storage. |
| Vendor-neutral | The project documentation and command names remain model-provider neutral while supporting compatible AI coding agents. |
| AI agent harness | Model-backed reconnaissance ran through the local harness with network disabled for this run. |
| Evidence validation | Validation, metrics, benchmark, and evidence graph stages operated on structured local artifacts. |
| Controlled GitHub Issue publication | Only `gra-issues --dry-run` was used; no Issues were created from audit output. |

## How to reuse this case study

Use this document when explaining the project externally:

1. Link it from README, release notes, or a blog draft as a public-safe example.
2. Pair it with [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md) for reporting
   boundaries and [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)
   for publication approval rules.
3. Quote only the workflow diagram, stage table, sanitized metrics categories,
   and product-improvement table.
4. Keep local run artifacts and any future finding-specific details out of public
   material unless a separate disclosure process approves the exact text.

## Summary

The self-dogfood run demonstrated that GenAI Repo Auditor can exercise an
AI-assisted repository-audit workflow while preserving local-first boundaries,
structured evidence validation, and controlled GitHub Issue publication. The most
valuable output was not a vulnerability disclosure; it was a set of concrete
product improvements that make future dogfood and customer runs easier to review
safely.

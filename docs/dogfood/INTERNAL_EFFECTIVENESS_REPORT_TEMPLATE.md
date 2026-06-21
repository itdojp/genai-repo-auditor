# Internal dogfood effectiveness report template

Copy this template to a local or restricted location such as
`.codex-local/dogfood/INTERNAL_EFFECTIVENESS_REPORT-RUN_SET.md` before filling
it with concrete dogfood-run details. Do not commit a filled report unless a
human reviewer has approved the exact public-safe text.

This template compares the self-dogfood run and the ITDO_ERP4 dogfood run with
counts and sanitized workflow outcomes only. It is internal/private by default
and is intentionally safe to commit because it contains placeholders, reporting
instructions, and count fields rather than target evidence.

Use with [`SELF_DOGFOOD_SUMMARY.md`](SELF_DOGFOOD_SUMMARY.md),
[`SELF_DOGFOOD_BACKLOG.md`](SELF_DOGFOOD_BACKLOG.md),
[`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md),
[`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md),
[`ITDO_ERP4_INTERNAL_SUMMARY_TEMPLATE.md`](ITDO_ERP4_INTERNAL_SUMMARY_TEMPLATE.md),
[`ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md`](ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md),
[`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md),
and [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Public-safe boundary

The filled report remains internal/private by default. Public-safe excerpts may
be created only after human review confirms the excerpt is limited to workflow
narrative, bounded counts, and product-improvement observations.

Do not include:

```text
- private findings or finding bodies
- scanner record bodies or dependency inventory details
- chain, proof, trace, or remediation details
- target code snippets, request bodies, response bodies, or exploit narratives
- generated issue body text, dashboards, local stores, transcripts, or event streams
- secrets, tokens, keys, cookies, credentials, environment files, or session data
```

## Executive summary

| Field | Self-dogfood | ITDO_ERP4 dogfood | Comparative note |
|---|---|---|---|
| Primary objective | `SELF_OBJECTIVE` | `ERP4_OBJECTIVE` | `COMPARATIVE_NOTE` |
| Run classification | `self / product` | `target / AppSec` | `COMPARATIVE_NOTE` |
| Overall outcome | `completed / partial / blocked` | `completed / partial / blocked` | `COMPARATIVE_NOTE` |
| Confirmed findings in report | `N` | `N` | Counts only; no finding bodies. |
| Product-improvement follow-ups | `N` | `N` | Link to sanitized backlog IDs only. |
| Publication status | `private / restricted / public-safe excerpt approved` | `private / restricted / public-safe excerpt approved` | `COMPARATIVE_NOTE` |

Decision summary:

```text
INTERNAL_DECISION_SUMMARY
```

## Scope and authorization

| Item | Self-dogfood | ITDO_ERP4 dogfood |
|---|---|---|
| Target repository | `itdojp/genai-repo-auditor` | `itdojp/ITDO_ERP4` |
| Scope source | `SELF_DOGFOOD_SUMMARY.md` | `ITDO_ERP4_SCOPE.md` |
| Target-selection source | `SELF_DOGFOOD_BACKLOG.md` or `not applicable` | `ITDO_ERP4_TARGET_SELECTION.md` |
| Scanner evidence source | `not run / ingested / not available` | `ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md` |
| Authorization reference | `APPROVAL_REFERENCE` | `APPROVAL_REFERENCE` |
| Retention decision | `delete-after-review / retain-local / secure-archive` | `delete-after-review / retain-local / secure-archive` |
| Disclosure decision | `none / private-first / public-safe excerpt approved` | `none / private-first / public-safe excerpt approved` |

Record only approval identifiers and decisions. Keep detailed approval records in
the approved internal system, not in this repository.

## Repositories reviewed

| Repository | Role in comparison | Public-safe description | Private-detail boundary |
|---|---|---|---|
| `itdojp/genai-repo-auditor` | Product self-dogfood baseline | Exercises the auditor against its own workflow and reporting surfaces. | Use public-safe summary counts only. |
| `itdojp/ITDO_ERP4` | External target dogfood | Exercises scoped AppSec planning, target selection, and scanner evidence handling. | Keep target findings and local evidence private. |

## Workflow steps executed

| Stage | Self-dogfood status | ITDO_ERP4 status | Effectiveness signal | Public-safe output |
|---|---|---|---|---|
| Prepare / run setup | `not run / passed / failed / interrupted` | `not run / passed / failed / interrupted` | Run isolation and repeatability | status only |
| Reconnaissance | `not run / passed / failed / interrupted` | `not run / passed / failed / interrupted` | Scope discovery and artifact generation | artifact categories only |
| Target queue | `not run / generated / narrowed` | `not run / generated / narrowed` | Target queue value for prioritization | target counts only |
| Target research | `not run / bounded / broad` | `not run / bounded / broad` | Review depth and operator focus | selected target count only |
| Scanner/posture ingest | `not run / ingested / not available` | `not run / ingested / not available` | Evidence-provider integration | tool names and lead counts only |
| Validation | `not run / passed / failed` | `not run / passed / failed` | Contract and safety gate quality | status and count only |
| Adversarial validation | `not run / skipped / passed / split` | `not run / skipped / passed / split` | Challenge quality for high-impact candidates | vote/decision counts only |
| Chain synthesis | `not run / skipped / generated` | `not run / skipped / generated` | Cross-finding context and remediation planning | count and status only |
| Metrics | `not run / passed / failed` | `not run / passed / failed` | Reporting consistency and trend input | aggregate counts only |
| Benchmark | `not run / passed / failed` | `not run / passed / failed` | Quality-gate summary | gate counts only |
| Evidence graph | `not run / passed / failed` | `not run / passed / failed` | Evidence connectivity and auditability | node/edge counts only |
| Issue publication planning | `not run / dry-run / plan / applied` | `not run / dry-run / plan / applied` | Publication safety and reviewer burden | preview/plan status only |

## Metrics summary

| Metric | Self-dogfood | ITDO_ERP4 dogfood | Interpretation |
|---|---:|---:|---|
| Generated target count | `N` | `N` | Target queue breadth. |
| Selected target count | `N` | `N` | Operator narrowing burden. |
| Researched target count | `N` | `N` | Deep-review coverage. |
| Scanner/posture lead count | `N` | `N` | Evidence-provider signal volume. |
| Candidate finding count | `N` | `N` | Funnel input; not publication approval. |
| Confirmed finding count | `N` | `N` | Validated results only. |
| Product-improvement observation count | `N` | `N` | Auditor improvement signal. |
| Issue dry-run would-create Issue count | `N` | `N` | Preview count only; no publication by dry-run. |
| Issue dry-run warning count | `N` | `N` | Publication-safety friction. |

## Benchmark summary

| Benchmark area | Self-dogfood | ITDO_ERP4 dogfood | Follow-up |
|---|---:|---:|---|
| Gates passed | `N` | `N` | `FOLLOW_UP` |
| Gates warned | `N` | `N` | `FOLLOW_UP` |
| Gates failed | `N` | `N` | `FOLLOW_UP` |
| Missing optional stages intentionally skipped | `N` | `N` | `FOLLOW_UP` |

Use this section to compare quality-gate outcomes. Do not paste benchmark report
bodies or local file paths.

## Evidence graph summary

| Graph metric | Self-dogfood | ITDO_ERP4 dogfood | Effectiveness interpretation |
|---|---:|---:|---|
| Nodes | `N` | `N` | `INTERPRETATION` |
| Edges | `N` | `N` | `INTERPRETATION` |
| Connected finding clusters | `N` | `N` | `INTERPRETATION` |
| Orphan evidence nodes | `N` | `N` | `INTERPRETATION` |

Evidence graph value should be described as auditability and traceability of
review decisions, not as proof of exploitability.

## Findings funnel

| Funnel stage | Self-dogfood | ITDO_ERP4 dogfood | Notes |
|---|---:|---:|---|
| Candidates | `N` | `N` | Funnel input only. |
| Validated | `N` | `N` | Human/model validation accepted. |
| Downgraded | `N` | `N` | Lower impact after validation. |
| Invalidated | `N` | `N` | Removed from finding path. |
| Needs human review | `N` | `N` | Requires reviewer decision. |
| Issue-recommended | `N` | `N` | Still requires publication approval. |
| Issue-suppressed | `N` | `N` | Suppressed by policy, duplicate, or insufficient evidence. |

Do not include finding titles or descriptions unless the exact text has been
approved for the report audience.

## Remediation candidate summary

| Remediation signal | Self-dogfood | ITDO_ERP4 dogfood | Notes |
|---|---:|---:|---|
| Candidate remediation items | `N` | `N` | Count only. |
| Validation passed | `N` | `N` | Count only. |
| Validation failed | `N` | `N` | Count only. |
| Deferred to target repository | `N` | `N` | Use handoff IDs only. |

Keep remediation content and patch material out of this report unless a separate
remediation workflow approves sharing.

## Human review burden

| Review activity | Self-dogfood | ITDO_ERP4 dogfood | Burden signal |
|---|---:|---:|---|
| Target narrowing decisions | `N` | `N` | `LOW / MEDIUM / HIGH` |
| Validation decisions | `N` | `N` | `LOW / MEDIUM / HIGH` |
| Publication review decisions | `N` | `N` | `LOW / MEDIUM / HIGH` |
| Manual artifact safety checks | `N` | `N` | `LOW / MEDIUM / HIGH` |
| Approximate operator touchpoints | `N` | `N` | `LOW / MEDIUM / HIGH` |

Use this section to compare workflow cost and review load. Do not include token
usage, transcripts, or private reviewer notes unless approved for the audience.

## Lessons learned

| Lesson ID | Scope | Lesson | Evidence type | Follow-up |
|---|---|---|---|---|
| `LESSON-001` | `self / ITDO_ERP4 / both` | `SANITIZED_LESSON` | `count / status / workflow observation` | `FOLLOW_UP` |
| `LESSON-002` | `self / ITDO_ERP4 / both` | `SANITIZED_LESSON` | `count / status / workflow observation` | `FOLLOW_UP` |

Keep lessons product- or workflow-oriented unless target owners approve a
restricted target-specific report.

## Product improvement backlog

| Follow-up ID | Priority | Source run | Category | Product impact | Proposed owner | Public Issue candidate? |
|---|---|---|---|---|---|---|
| `SDFB-001` | `P1 / P2 / Deferred` | `self` | `CATEGORY` | `IMPACT` | `OWNER` | `yes / no / later` |
| `ERP4-DFB-001` | `P1 / P2 / Deferred` | `ITDO_ERP4` | `CATEGORY` | `IMPACT` | `OWNER` | `yes / no / later` |

Public product-improvement Issues may be created only when the text can be
explained without target evidence. Target-repository findings follow the target
repository disclosure process, not this backlog table.

## Public-safe material candidates

| Candidate | Audience | Allowed content | Required approval |
|---|---|---|---|
| Dogfood workflow case study | Public | Stages exercised, counts, and product lessons | Maintainer approval of exact text |
| Release note | Public | Product improvements and test coverage | Release owner approval |
| Internal customer handoff | Restricted | Counts and reviewed finding references | Customer/repository owner approval |
| Product roadmap update | Public or internal | Sanitized follow-up IDs and priorities | Product owner approval |

## Value assessment by workflow component

| Component | Value signal to compare | Failure mode to watch | Follow-up if weak |
|---|---|---|---|
| Target queue | Finds high-value review areas and bounds operator effort. | Too many broad targets or missed in-scope areas. | Improve target taxonomy, narrowing rules, or queue summaries. |
| Adversarial validation | Challenges high-impact candidates before publication. | Unresolved splits, downgrades, or unsupported conclusions. | Strengthen validation policy and reviewer prompts. |
| Chain synthesis | Helps understand multi-step context for remediation planning. | Reads as disclosure detail rather than internal context. | Keep output private and summarize only counts/status. |
| Metrics | Creates repeatable comparisons across runs. | Counts require manual extraction or are inconsistent. | Add compact summary fields and report tests. |
| Evidence graph | Shows decision traceability across artifacts. | Sparse or orphan-heavy graph in intentionally bounded runs. | Record skipped stages and graph interpretation guidance. |
| Issue publication planning | Separates preview, immutable plan, and publication actions. | Dry-run wording or warnings confuse approval flow. | Clarify preview terms and require approval gates. |

## Approval and retention checklist

Before sharing or publishing any filled report, confirm:

```text
- Audience, tracker, and approver are recorded.
- Counts are bounded and do not reveal private target context.
- Internal-only sections are removed from any public excerpt.
- Scanner, dependency, chain, proof, trace, remediation, dashboard, and transcript content is omitted.
- Issue publication planning is described as preview or approved plan only, not as automatic publication.
- Retention decision and cleanup owner are recorded.
```

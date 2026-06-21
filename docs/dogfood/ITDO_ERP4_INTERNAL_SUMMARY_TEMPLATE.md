# ITDO_ERP4 internal dogfood summary template

Copy this template to a local or restricted location such as
`.codex-local/dogfood/ITDO_ERP4_INTERNAL_SUMMARY-RUN_ID.md` before filling it
with concrete run details. Do not commit the filled summary unless a human
reviewer has approved the exact public-safe text.

Use with [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md),
[`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md),
[`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md),
[`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md), and
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Public-safe boundary

This template is safe to commit because it contains placeholders and reporting
instructions only. A filled summary may contain sensitive target context even
when it uses bounded counts. Keep filled summaries local/private by default.

Do not include:

```text
- private findings or finding bodies
- raw evidence, scanner records, or generated issue body text
- chain, proof, trace, or remediation details
- target code snippets copied from local analysis
- Codex transcripts, event streams, stderr, or final messages
- dashboards, SARIF files, SQLite stores, or local run artifacts
- secrets, tokens, keys, cookies, credentials, environment files, or session data
```

## Run metadata

| Field | Value |
|---|---|
| Campaign ID | `DOGFOOD_CAMPAIGN_ID` |
| Target repository | `itdojp/ITDO_ERP4` |
| Target branch | `main` or selected branch |
| Target commit | `TARGET_COMMIT_SHA` |
| Run ID | `RUN_ID` |
| Operator | `OPERATOR_OR_TEAM` |
| Scope approval | `APPROVAL_REFERENCE` |
| Retention decision | `delete-after-review`, `retain-local`, or `secure-archive` |
| Publication decision | `private`, `restricted-internal`, or `approved-public-safe` |

## Scope executed

- Scope source: `docs/dogfood/ITDO_ERP4_SCOPE.md`
- Target selection source: `docs/dogfood/ITDO_ERP4_TARGET_SELECTION.md`
- Reporting boundary source: `docs/dogfood/ITDO_ERP4_REPORTING_BOUNDARIES.md`
- Excluded areas:
  - `EXCLUDED_AREA_1`
  - `EXCLUDED_AREA_2`
- Stop conditions encountered:
  - `none` or `STOP_CONDITION_WITH_DECISION`

## Command status

| Stage | Status | Local artifact category | Public-safe note |
|---|---|---|---|
| `gra-audit --mode prepare` | `not started / passed / failed / interrupted` | run context and target clone | `SUMMARY_ONLY` |
| `gra-recon` | `not started / passed / failed / interrupted` | reconnaissance reports | `SUMMARY_ONLY` |
| `gra-targets --generate` | `not started / passed / failed / interrupted` | target queue | `TARGET_COUNT_ONLY` |
| human target narrowing | `not started / completed` | local selection memo | `SELECTED_TARGET_IDS_ONLY` |
| `gra-research` | `not started / passed / failed / interrupted` | target research reports | `COUNTS_ONLY` |
| `gra-adversarial-validate` | `not started / passed / failed / skipped` | validation report | `DECISION_COUNTS_ONLY` |
| `gra-chains` / `gra-proofs` / `gra-trace` | `not started / passed / failed / skipped` | advanced evidence | `PRIVATE_ONLY` |
| `gra-metrics` | `not started / passed / failed` | metrics | `COUNTS_ONLY` |
| `gra-benchmark` | `not started / passed / failed` | benchmark | `GATE_COUNTS_ONLY` |
| `gra-evidence-graph` | `not started / passed / failed` | evidence graph | `NODE_EDGE_COUNTS_ONLY` |
| `gra-dashboard` | `not started / passed / failed` | local dashboard | `DO_NOT_SHARE_DASHBOARD` |
| `gra-validate-report` | `not started / passed / failed` | validation result | `STATUS_ONLY` |
| `gra-issues --dry-run` | `not started / passed / failed` | issue preview/ledger | `CREATED_AND_WARNING_COUNTS_ONLY` |

## Target queue summary

| Metric | Value |
|---|---:|
| Generated target count | `N` |
| Selected first-wave target count | `N` |
| Deep-researched target count | `N` |
| Deferred target count | `N` |

Selected targets, if approved for internal summary:

| Target ID | Mapped scope area | Why selected | Publication boundary |
|---|---|---|---|
| `TGT-XXX` | `ERP4-SCOPE-XX` | `bounded reason` | `private by default` |

Do not include target research excerpts, code snippets, raw evidence, or local
artifact paths beyond high-level categories.

## Findings funnel counts

| Funnel stage | Count |
|---|---:|
| Candidate findings generated | `N` |
| Confirmed findings | `N` |
| Probable findings | `N` |
| Potential findings | `N` |
| Invalidated findings | `N` |
| Needs human review | `N` |
| Issue-recommended findings | `N` |
| Public-safe findings approved for publication | `N` |

If any count is non-zero, keep the detailed finding bodies local/private and
route through the approval process in `ITDO_ERP4_REPORTING_BOUNDARIES.md`.

## Validation and quality-gate counts

| Area | Count/status |
|---|---:|
| Adversarial validation votes | `N` |
| Validation downgrades | `N` |
| Validation invalidations | `N` |
| Benchmark gates passed | `N` |
| Benchmark warnings | `N` |
| Benchmark failures | `N` |
| Evidence graph nodes | `N` |
| Evidence graph edges | `N` |
| Issue dry-run created Issues | `N` |
| Issue dry-run warnings | `N` |

## Product-improvement observations

Use this section only for GenAI Repo Auditor product feedback that can be shared
without target evidence.

| Observation | Severity | Impact | Proposed follow-up | Should become Issue? |
|---|---|---|---|---|
| `PRODUCT_OBSERVATION` | `Low / Medium / High` | `operator impact` | `follow-up` | `Yes / No / Consider` |

## Retention and cleanup

- Local run directory: `runs/itdojp__ITDO_ERP4/RUN_ID`
- Cleanup command reviewed: `yes / no`
- Cleanup applied: `yes / no`
- Retention owner: `OWNER`
- Retention end date or review date: `DATE`
- Secure archive reference, if any: `REFERENCE`

## Publication decision

| Output | Decision | Approver | Notes |
|---|---|---|---|
| Internal detailed report | `private / restricted` | `APPROVER` | `notes` |
| Internal sanitized summary | `local / restricted / approved` | `APPROVER` | `notes` |
| Public GitHub Issues | `none / private-first / approved` | `APPROVER` | `notes` |
| Public-safe case study | `not approved / approved` | `APPROVER` | `notes` |

Before any publication step, confirm:

```text
- Exact tracker and audience are approved.
- Security-impacting public-repository findings use SECURITY.md first.
- Issue body text has been reviewed and hashed in the local plan.
- `--allow-public` is not used unless explicitly approved.
- Local artifacts are retained or deleted according to policy.
```

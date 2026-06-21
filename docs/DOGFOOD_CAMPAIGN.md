# Dogfood campaign ledger

This document defines a repeatable dogfood campaign structure for evaluating
GenAI Repo Auditor on authorized repositories. It is a planning and bookkeeping
surface only; it does not contain generated audit artifacts or private findings.

The initial campaign targets are:

- `itdojp/genai-repo-auditor` for self-dogfood of the audit harness;
- `itdojp/ITDO_ERP4` for a scoped application-security dogfood run.

Use this document with [`DOGFOOD_RUNBOOK.md`](DOGFOOD_RUNBOOK.md),
[`DOGFOOD_REPORTING.md`](DOGFOOD_REPORTING.md),
[`OPERATING_MODEL.md`](OPERATING_MODEL.md), and
[`DISCLOSURE_AND_PUBLICATION_POLICY.md`](DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Goals

Dogfood campaigns should answer product and operating questions without turning
private security work into public disclosure:

- Can the workflow run end-to-end on authorized repositories?
- Are target queues, validation, metrics, benchmarks, evidence graphs, and issue
  publication plans useful to operators?
- Are false positives, weak findings, unsafe proof material, and public Issue
  drafts suppressed before publication?
- Which product improvements should become follow-up Issues?
- Which public-safe summaries are suitable for README, blog, or demo use?

## Campaign ledger location

Keep the active campaign ledger outside Git unless a human reviewer has confirmed
that every field is public-safe. Recommended local path:

```text
.codex-local/dogfood/campaign-ledger.json
```

Use [`templates/dogfood/campaign-ledger.example.json`](../templates/dogfood/campaign-ledger.example.json)
as the starting structure. The example is safe to commit because it contains only
placeholder values.

Do not copy generated run directories, scanner outputs, Codex transcripts,
dashboards, SQLite stores, SARIF files, issue drafts, attack-chain summaries,
proof artifacts, trace artifacts, or remediation patches into the committed
ledger. Keep those under the local run directory and follow
[`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md) when the retention window
ends.

## Campaign states

| State | Meaning | Allowed public content |
|---|---|---|
| `planned` | Scope and authorization are being prepared. | Target names, intended workflow, missing prerequisites. |
| `running` | Local audit or dry-run execution is in progress. | High-level status only. |
| `reviewed` | Human review has checked metrics, validation, and publication boundaries. | Counts and workflow observations if sanitized. |
| `follow-up-created` | Product backlog or remediation routing has been created. | Backlog item titles without private evidence. |
| `published-sanitized` | Public-safe case study or launch material has been approved. | Approved public summary only. |

Publication defaults to `private` or `not-approved`. Use `sanitized-public` only
after reviewing the exact text against
[`DISCLOSURE_AND_PUBLICATION_POLICY.md`](DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Required ledger fields

Each run record should include at least:

- `campaign_id`: stable campaign identifier such as `dogfood-202606`;
- `target_repo`: authorized `OWNER/REPO` target;
- `run_id`: local run identifier or `not-executed` when recording a dry-run plan;
- `scope`: one of `self-dogfood`, `itdo-erp4-scoped`, `itdo-erp4-scanner`,
  `internal-report`, or `public-report`;
- `authorized_by`: human approver or approval record reference;
- `run_mode`: `prepare`, `exec`, `staged`, `goal`, or `not-executed`;
- `artifact_refs`: relative paths to expected local artifacts, not embedded
  artifact contents. Record `reports/issue-publication-plan.json` only for
  runs where `gra-issues --plan` was actually executed;
- `review_status`: campaign state from the table above;
- `publication_status`: `private`, `sanitized-public`, or `not-approved`;
- `retention_decision`: `delete-after-review`, `retain-local`, or
  `secure-archive`;
- `follow_ups`: product or documentation follow-up items that do not disclose
  private findings.

## Per-run record

Use [`templates/dogfood/run-record.example.json`](../templates/dogfood/run-record.example.json)
for a single run entry. Store concrete run records locally, for example:

```text
.codex-local/dogfood/runs/RUN_ID.json
```

A run record can include validation evidence such as command names and pass/fail
status, but it should not embed raw logs. Keep full logs local and summarize only
bounded counts or status.

## Follow-up Issue rules

Create product-improvement Issues when an observation is:

1. actionable without revealing private target details;
2. about GenAI Repo Auditor behavior, documentation, validation, workflow UX,
   metrics, benchmark quality, evidence graph clarity, remediation gating,
   sandbox readiness, scanner ingestion, or publication safety;
3. reproducible with a public fixture, sanitized transcript, or synthetic
   example; and
4. reviewed so it does not include private findings, proof details, raw scanner
   output, or customer context.

Do not create public Issues for target-repository vulnerabilities from dogfood
runs unless the disclosure path explicitly approves the exact public text. For
security-impacting public repositories, prefer private disclosure first.

## Campaign closeout checklist

Before marking a campaign `published-sanitized`:

```text
- Authorization and scope records are complete.
- Local-only artifacts were reviewed and retained or deleted according to policy.
- Metrics and benchmark summaries are counts-only and public-safe.
- Evidence graph, proof, chain, trace, and remediation details remain private.
- Product-improvement backlog items are sanitized and actionable.
- Public case studies and launch materials cite only approved summaries.
- No generated audit artifact is staged for Git commit.
```

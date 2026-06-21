# Public-safe dogfood report: TITLE

> This template is for approved public summaries. It must not include private findings, raw evidence, attack-chain details, proof payloads, scanner raw
> output, Codex transcripts, issue drafts, remediation diffs, credentials, or
> customer-sensitive context.

## Summary

- Campaign: `dogfood-YYYYMM`
- Target: `OWNER/REPO` or approved target category
- Run status: `completed | partially completed | not executed`
- Publication status: `sanitized-public` after human approval

## Why this dogfood run was performed

Describe the product or operating question being evaluated. Keep the claim
conservative and evidence-backed.

## Workflow stages exercised

| Stage | Status | Public-safe note |
|---|---|---|
| prepare / recon | `completed | skipped` | Scope and setup only. |
| target queue | `completed | skipped` | Counts only. |
| validation | `completed | skipped` | Pass/fail summary only. |
| metrics | `completed | skipped` | Categories and counts only. |
| benchmark | `completed | skipped` | Quality gate status only. |
| evidence graph | `completed | skipped` | High-level graph usefulness only. |
| issue dry-run | `completed | skipped` | Warning counts only; no issue body text. |

## Sanitized outcomes

Use bounded, approved summaries such as:

```text
- Targets reviewed: COUNT_OR_NOT_PUBLISHED
- Candidate findings reviewed: COUNT_OR_NOT_PUBLISHED
- Candidates downgraded or invalidated: COUNT_OR_NOT_PUBLISHED
- Issue-publication warnings: COUNT_OR_NOT_PUBLISHED
- Product-improvement follow-ups: COUNT_OR_NOT_PUBLISHED
```

Do not include finding titles, affected paths, proof details, attack chains,
scanner records, remediation diffs, or private repository context.

## Product observations

Summarize operator workflow, documentation gaps, validation friction, metrics or
benchmark usefulness, evidence graph clarity, and publication-safety behavior.

## Safety and disclosure controls

Explain how the run remained local-first and disclosure-safe:

- generated run artifacts stayed local;
- issue publication used dry-run or plan review only;
- public output was reviewed against disclosure policy;
- cleanup or retention was recorded.

## Follow-up material

Link only to approved public documentation, public-safe case studies, or sanitized
product backlog items.

# Dogfood reporting guide

This guide defines public-safe and internal reporting outputs for dogfood
campaigns. It exists to prevent private audit artifacts from being copied into
GitHub Issues, pull requests, README updates, blog posts, or launch material.

## Report tiers

| Tier | Audience | Typical artifact | Content boundary |
|---|---|---|---|
| Local/private | Operator and approved reviewers | `runs/OWNER__REPO/RUN_ID/reports/*` | Full local context; never committed by default. |
| Internal sanitized | Project maintainers / customer contacts | `docs/dogfood/*_SUMMARY.md` when approved | Counts, workflow observations, product backlog, no private details. |
| Public-safe | README, blog, demo, public case study | [`templates/dogfood/public-safe-report-template.md`](../templates/dogfood/public-safe-report-template.md) | Approved narrative, bounded metrics categories, no vulnerability details. |

If a report cannot satisfy the public-safe boundary, keep it local/private and
commit only a template or placeholder.

## Allowed public-safe content

Public-safe dogfood reports may include:

- target repository name when approved;
- run date or campaign month;
- workflow stages exercised;
- artifact types generated, such as metrics, benchmark, evidence graph,
  dashboard, validation, and issue dry-run;
- counts by status after human review;
- issue-publication warning counts;
- operator UX observations;
- product-improvement backlog categories;
- disclosure and cleanup decisions.

Use bounded counts and categories. Do not include path-level evidence, code
snippets, exploitability details, scanner records, or private target context.

## Prohibited report content

Do not publish or commit:

```text
- private findings or finding bodies
- attack-chain details or ATTACK_CHAINS.md excerpts
- proof details, proof payloads, or PROOFS.md excerpts
- trace details or TRACE.md excerpts
- remediation patch diffs or generated patch files
- raw scanner output or normalized scanner lead bodies
- Codex transcripts, event streams, stderr, or final messages
- issue drafts before explicit approval
- dashboards, SARIF files, SQLite stores, or raw metrics bundles
- secrets, tokens, keys, cookies, credentials, customer identifiers, or private evidence
```

## Internal dogfood summary structure

Internal summaries should still be sanitized by default:

```text
# Summary
- Campaign and target
- Authorization and scope
- Workflow stages executed
- Validation and benchmark status
- Evidence graph and metrics summary
- Findings funnel counts
- Issue-publication planning outcome
- Product-improvement follow-ups
- Retention and cleanup decision
```

Use `not executed`, `skipped`, or `not available` when a stage was not run. Do
not infer results from missing artifacts.

## Public-safe case study structure

Start from the public-safe template and keep claims conservative:

```text
# Public-safe dogfood case study
- Why this dogfood run was performed
- What local-first workflow was exercised
- What artifact categories were generated
- What validation gates were useful
- What product improvements were identified
- How private details were kept out of public output
```

Avoid claims such as fully autonomous auditing, zero-day discovery, exploit
generation, automatic patching, or equivalence to managed frontier-model security
products.

## Review checklist before committing a report

```text
- The report links to disclosure and cleanup policy.
- All metrics are counts or categories, not raw evidence.
- All findings, chains, proofs, traces, scanner leads, and remediation diffs are omitted.
- The report does not include generated run paths beyond illustrative placeholders.
- Public repository wording has human approval when required.
- The report can be read without access to local/private artifacts.
```

If any item fails, keep the report local and commit only a template.

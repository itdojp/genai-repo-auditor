# ITDO_ERP4 dogfood reporting boundaries

This document defines what may be recorded, shared, or published after a scoped
ITDO_ERP4 dogfood run. It exists to keep target-repository findings, local
evidence, and generated audit artifacts out of public planning documents unless
an explicit disclosure process approves the exact text.

Use it with [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md),
[`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md),
[`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md),
[`../LOCAL_ARTIFACT_CLEANUP.md`](../LOCAL_ARTIFACT_CLEANUP.md), and
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Default disclosure position

- Audit artifacts are local/private by default.
- Security-impacting findings for the public ITDO_ERP4 repository should use the
  repository's `SECURITY.md` path, starting with GitHub Security Advisories when
  available.
- Public GitHub Issues are not the first reporting channel for sensitive
  vulnerabilities.
- `gra-issues --dry-run` is allowed for preview and warning counts only; it does
  not authorize publication.
- `gra-issues --plan`, `gra-issues --apply-plan`, `gra-issues --apply`, and
  `--allow-public` require human approval of the exact text and tracker target.

## Artifact handling matrix

| Artifact or content | Default location | Can be committed here? | Notes |
|---|---|---|---|
| Scope and target-selection plan | `docs/dogfood/` | Yes | Planning only; no findings or evidence. |
| Local run directory and target clone | `runs/itdojp__ITDO_ERP4/RUN_ID/` | No | Treat as private, even for a public target repo. |
| Recon, target queue, research notes, findings, validation, metrics, benchmark, evidence graph, dashboard, SARIF, store, and issue previews | Local run directory | No | Summarize only bounded counts and workflow status after review. |
| Scanner inputs and normalized scanner leads | Local run directory | No | Ingest only when pre-existing outputs are authorized. |
| Codex event streams, stderr, final messages, and transcripts | Local run directory | No | Do not paste into PRs, Issues, or public summaries. |
| Issue drafts and publication plans | Local run directory | No by default | May be applied only after exact body hash/text review and approval. |
| Remediation candidates and patch validation output | Local run directory | No by default | Separate remediation work belongs in the target repo after owner approval. |
| Internal sanitized run summary | `.codex-local/dogfood/` or restricted tracker | No by default | Use counts, target IDs, status, and decisions; no raw evidence. |
| Public-safe case study | Approved public document | Only after review | Use workflow narrative and bounded counts; no vulnerability detail. |

## Allowed public-safe summary fields

A public-safe ITDO_ERP4 dogfood summary may include:

- target repository name and approved target commit;
- run date, run mode, and workflow stages exercised;
- target queue count, selected target count, and skipped target count;
- validation, benchmark, evidence graph, dashboard, and issue dry-run status;
- counts by severity/status after human review, only if approved;
- issue-publication warning counts;
- product-improvement observations about GenAI Repo Auditor;
- retention and cleanup decision.

Keep all values bounded. Do not include path-level evidence, code snippets,
request/response bodies, exploitability narratives, scanner records, secrets,
private issue text, or customer/private business context.

## Private or restricted content

Keep the following local/private unless a human reviewer approves a specific
restricted channel and exact wording:

```text
- private findings or finding bodies
- raw evidence and raw scanner output
- chain, proof, trace, and remediation details
- generated issue body text before approval
- target code snippets copied from local analysis
- credentials, cookies, tokens, keys, session data, or environment files
- production, staging, customer, or employee-specific data
- dashboards, SARIF files, SQLite stores, and transcripts
```

## Issue-routing rules

| Situation | Default route |
|---|---|
| GenAI Repo Auditor product friction discovered during dogfood | Public product-improvement Issue in `itdojp/genai-repo-auditor` if sanitized. |
| ITDO_ERP4 non-security hygiene observation | ITDO_ERP4 Issue only after confirming it contains no sensitive detail. |
| ITDO_ERP4 security-impacting candidate | Private report through SECURITY.md / GitHub Security Advisories first. |
| Customer/private context or sensitive operational detail | Restricted tracker or private handoff; do not use a public Issue. |
| Unvalidated scanner/import lead | Keep as review lead; do not publish as a finding. |

## Review checklist before any publication step

```text
- The exact tracker and audience are approved.
- The target commit and selected targets are recorded locally.
- `gra-validate-report` passed for the run.
- Critical/High candidates have human review and adversarial validation.
- Issue dry-run warnings are zero or explicitly accepted.
- The text omits private findings, raw evidence, scanner output, transcripts, and remediation diffs.
- Public repository security findings follow SECURITY.md first.
- Local retention or cleanup decision is recorded.
```

If any item fails, stop at internal review and do not publish.

## Cleanup and retention

After review, run cleanup from the GenAI Repo Auditor repository root and keep
evidence only through an approved secure process:

```bash
python3 scripts/clean-local-artifacts.py
# Review dry-run output first.
python3 scripts/clean-local-artifacts.py --apply
```

When artifacts must be retained, record the retention owner, retention period,
storage location, and deletion criteria outside public Git.

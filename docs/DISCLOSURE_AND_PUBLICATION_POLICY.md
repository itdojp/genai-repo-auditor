# Disclosure and publication policy

This policy defines when audit output may become a GitHub Issue, customer
handoff, advisory input, or public disclosure. It is intentionally conservative:
local audit artifacts are private by default, and Issue creation requires human
approval.

## Default position

- Audit execution does not create Issues.
- `gra-issues --plan` is the preferred review artifact.
- `gra-issues --apply` and `gra-issues --apply-plan` are publication actions and
  require human approval.
- Public repository Issue creation is blocked by default.
- `--allow-public` is allowed only when policy permits and the exact public text
  has been approved by the repository owner, maintainer, customer disclosure
  contact, or delegated security reviewer.

## Publication decision matrix

| Context | Default action | Required before Issue creation |
|---|---|---|
| Internal private repository | Private Issue or internal tracker after review | Repository owner/AppSec approval and issue body hash review |
| Customer private repository | Customer handoff first | Written customer approval and agreed tracker location |
| OSS public repository with possible security impact | Private disclosure first | Maintainer security policy review and disclosure approval |
| Public repository with non-security hygiene finding | Public Issue only if harmless | Human review that confirms no vulnerability or sensitive detail is exposed |
| Imported external finding | Review lead only | Local validation, revised metadata, and approved issue draft |

## What not to publish

Never publish these materials directly:

```text
- full secret values, tokens, keys, cookies, credentials, or session data
- raw private repository evidence
- customer names or identifiers without approval
- issue drafts that have not been approved
- scanner lead bodies or raw scanner exports
- Codex transcripts or event streams
- ATTACK_CHAINS.md copied wholesale
- PROOFS.md or proof payloads copied wholesale
- TRACE.md or trace artifacts copied wholesale
- remediation patch diffs unless a separate remediation workflow approves sharing
- exploit payloads, weaponized steps, or live probing instructions
- generated runs, dashboards, SQLite stores, SARIF files, or raw metrics bundles
```

Use bounded summaries: finding ID, severity, confidence, affected component,
validated status, safe reproduction limitations, remediation direction, and
remaining uncertainty.

## Human approval checklist

Before applying a publication plan, confirm:

```text
- The repository, branch, commit, and run ID are correct.
- Finding severity, confidence, and status have been reviewed.
- For Critical/High findings, advanced validation is present or the gap is accepted.
- Adversarial validation has not returned `downgrade`, `invalidate`, or an unresolved split unless explicit approval accepts that uncertainty.
- Safe local proof artifacts are present when required, or marked not applicable with rationale.
- Chain synthesis is summarized only as remediation/disclosure context.
- gra-trace, if present, is described as experimental/P3 reachability evidence.
- Issue body hashes in issue-publication-plan.json match the reviewed drafts.
- No forbidden content appears in the Issue body.
- Public disclosure approval is recorded when the target repository is public.
```

## Publication workflow

Generate and review an immutable plan:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Review these local files:

```text
reports/issue-publication-plan.json
reports/issue-ledger.json
reports/issue-drafts/*.md
reports/validation.json
reports/VALIDATION.md
reports/proofs.json
reports/PROOFS.md
reports/chains.json
reports/ATTACK_CHAINS.md
reports/traces.json
reports/TRACE.md
reports/remediation/*/patch-validation.json
```

Apply only after approval:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

For public repositories, the default is denial. Add `--allow-public` only after
approval and after confirming the public Issue body contains no secrets, private
customer data, raw exploit details, or local-only artifacts:

```bash
# Approved public disclosure only; default is denial.
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels \
  --allow-public
```

## Private disclosure flow for OSS security issues

When a public repository appears to contain a security issue:

1. Check the repository's `SECURITY.md` and preferred private reporting channel.
2. Prepare a bounded report without raw exploit payloads or secrets.
3. Share privately through the approved channel.
4. Wait for maintainer acknowledgement or follow the stated disclosure timeline.
5. Create a public Issue only after maintainer approval or after the approved
   disclosure policy permits publication.

Do not use public Issues as the first report for sensitive vulnerabilities.

## Customer disclosure flow

For customer audits:

1. Deliver the reviewed handoff package from [`CUSTOMER_AUDIT_RUNBOOK.md`](CUSTOMER_AUDIT_RUNBOOK.md).
2. Ask the customer to choose: internal tracker, private GitHub Issues, delayed
   publication, or no Issue creation.
3. Record the customer's approval and disclosure constraints.
4. Apply the exact reviewed plan only in the approved tracker.
5. Clean local artifacts according to retention requirements.

## Duplicate and known-finding handling

Use novelty and issue ledger artifacts to avoid repeated publication:

```bash
gra-novelty --run runs/OWNER__REPO/RUN_ID --ledger runs/known-findings.json
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
```

A duplicate or accepted-risk classification is not a publication approval. It is
an input to human review.

## Emergency escalation

Escalate before publication when any of the following are true:

- suspected active exploitation;
- exposed credential or secret;
- customer data or regulated data could be involved;
- public repository with unclear maintainer disclosure policy;
- adversarial validation split or downgrade conflicts with operator assessment;
- remediation requires coordinated release timing.

Escalation should use private channels. Do not add details to public Issues while
approval is pending.

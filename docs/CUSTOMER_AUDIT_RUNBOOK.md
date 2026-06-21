# Customer audit runbook

This runbook describes how to operate GenAI Repo Auditor for a customer-facing
managed audit. It assumes written authorization and a named customer contact.
Do not use it for repositories where authorization is incomplete.

## Intake checklist

Record the following before cloning or preparing a run:

```text
- Customer or business owner:
- Authorized repository URL(s):
- Branch and commit or release tag:
- Audit objective and excluded areas:
- Allowed scanners and versions:
- Network access approval: no by default
- Disclosure contact and escalation path:
- Customer handoff deadline:
- Retention period and deletion requirement:
- Whether GitHub Issues may be created: no by default
- Whether public disclosure is allowed: no by default
```

Use placeholders such as `CUSTOMER`, `OWNER/REPO`, and `RUN_ID` in local notes.
Do not put customer names, private findings, tokens, or proprietary details in
repository documentation, PRs, or public Issues.

## Prepare the run

```bash
gra-audit --repo OWNER/REPO --mode prepare --model gpt-5.5 --effort xhigh
gra-run-state --run runs/OWNER__REPO/RUN_ID --status
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Confirm that the cloned repository, prompts, context, and reports are under the
approved local workspace. If the repository is private, treat every generated
artifact as customer confidential.

## Normal customer audit sequence

```bash
gra-recon --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --generate --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --list
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode exec --model gpt-5.5 --effort xhigh
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

Run additional targets only when they are inside the authorized scope. If the
customer asks for a pause, record it:

```bash
gra-run-state --run runs/OWNER__REPO/RUN_ID --pause \
  --reason "customer-requested pause" \
  --resume-target TGT-002 \
  --resume-condition "customer confirms target scope" \
  --final-reconcile "handoff pending"
```

## Staged customer audit sequence

Use the staged path for higher-risk repositories or when the customer expects
coverage and validation evidence.

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-gapfill --run runs/OWNER__REPO/RUN_ID --list
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-GAPFILL-001 --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Do not send raw `reports/` output as the customer deliverable. Use it to prepare
a reviewed summary.

## Advanced customer validation

Require additional validation for Critical/High findings that could affect
external users, shared libraries, authentication, authorization, secrets,
payment, tenant isolation, or supply chain controls.

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Use `gra-trace` only for an explicitly approved shared-library producer/consumer
question. It is experimental/P3 reachability evidence and must not be presented
as exploit proof.

```bash
gra-trace \
  --producer-run runs/OWNER__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/OWNER__consumer/RUN_ID \
  --mode exec
```

## Customer handoff format

Prepare a reviewed handoff package with bounded content only:

```text
1. Scope and authorization summary
2. Repository, branch, commit, and run ID
3. Executive summary of confirmed/probable findings
4. Finding table: ID, title, severity, confidence, affected component, status
5. Validation summary: adversarial decision, proof status, chain status, trace status when applicable
6. Remediation guidance summary without raw patch payloads unless separately approved
7. Known limitations and needs-human-review items
8. Retention and deletion statement
9. Disclosure decision and next approval step
```

Do not include:

- raw finding evidence copied from private code;
- issue draft body text that has not been approved;
- `ATTACK_CHAINS.md` or `PROOFS.md` copied wholesale;
- trace artifacts copied wholesale;
- scanner lead bodies;
- secret values, tokens, private keys, cookies, credentials, or session data;
- customer names in public repository artifacts;
- exploit payloads or live probing instructions.

## Issue creation for customers

Customer-facing Issue creation is opt-in. Prefer the plan workflow and require
customer or repository-owner approval of exact content:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
# Human review: issue-publication-plan.json, issue body hashes, issue drafts, validation summaries.
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

For public repositories, `--allow-public` must remain off unless the customer or
maintainer has approved public disclosure and policy permits the exact wording.
When it is approved, run `gra-issues --apply-plan ... --allow-public` only after
checking that no secrets, private evidence, exploit steps, or customer-identifying
information are present.

## Closure and cleanup

1. Confirm the customer received the approved handoff.
2. Record whether Issues were created, deferred, or explicitly rejected.
3. Pause or close the run state with a final reconcile note.
4. Run cleanup dry-run, then apply cleanup when retention expires.

```bash
gra-run-state --run runs/OWNER__REPO/RUN_ID --pause \
  --reason "customer handoff complete" \
  --resume-condition "new customer authorization" \
  --final-reconcile "handoff delivered; no public artifacts retained"
python3 scripts/clean-local-artifacts.py
python3 scripts/clean-local-artifacts.py --apply
```

See [`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md) for retention and
cleanup safeguards.

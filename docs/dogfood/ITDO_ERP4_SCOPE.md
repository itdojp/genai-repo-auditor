# ITDO_ERP4 dogfood scope and threat-model inputs

This document defines the public-safe planning scope for a scoped GenAI Repo
Auditor dogfood run against `itdojp/ITDO_ERP4`. It is planning material only: no
audit has been run by this document, no findings are asserted, and no private
evidence is included.

Use it with [`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md),
[`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md),
[`../DOGFOOD_RUNBOOK.md`](../DOGFOOD_RUNBOOK.md), and
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Planning inputs reviewed

The scope below is derived from public/authorized ITDO_ERP4 documentation only.
It intentionally does not infer vulnerabilities from file names, test gaps, or
runbook text.

| Input | Planning relevance |
|---|---|
| `README.md` | Repository purpose, target stack, manual PoC flow, quality and ops entry points. |
| `docs/quality/quality-gates.md` | CI jobs, blocking gates, security-audit, secret-scan, SBOM, CodeQL, E2E posture. |
| `docs/quality/test-gaps.md` | A/B/C test priorities and current coverage for RBAC, Agent-First, approval, expense, migration, backup/restore, and attachments. |
| `docs/manual/manual-test-checklist.md` | Manual backend/API and frontend flows, Agent-First guardrail checks, expense state transitions, evidence, and audit-log checks. |
| `docs/security/security-baseline.md` | Assets, expected threats, baseline controls, DAST/SAST posture, secret scanning, and residual issues. |
| `docs/security/risk-register.md` | P0/P1 risks for auth mode, RBAC/ABAC, malware attachments, secrets, audit logs, and dependencies. |
| `docs/security/supply-chain.md` | Dependabot, npm audit, SBOM, dependency alert monitoring, and provenance posture. |
| `docs/requirements/action-policy-high-risk-apis.md` | High-risk mutating API catalog and ActionPolicy templates. |
| `docs/manual/agent-write-guardrails-guide.md` | Agent write guardrails, approval/evidence requirements, fallback reports, and audit replay checks. |
| `docs/manual/role-permissions.md` | Role model and visibility boundaries for self, admin, management, HR, project, and chat scopes. |
| `docs/manual/expense-workflow-guide.md` and `docs/manual/approval-operations.md` | Expense, approval, settlement, reason, evidence, QA checklist, and audit-log workflows. |
| `docs/ops/antivirus.md`, `docs/ops/backup-restore.md`, and `docs/ops/index.md` | Attachment AV, fail-closed behavior, backup/restore, DR, incident, secrets, and operations runbooks. |
| `SECURITY.md` | Private reporting route for security-impacting findings. |

## Authorization and operating assumptions

- Target repository: `itdojp/ITDO_ERP4`.
- Scope type: scoped application-security dogfood planning.
- Run mode: staged; prepare and recon first, then target queue narrowing before
  deep research.
- Target branch and commit: pin at `gra-audit --mode prepare` time and record in
  the local run ledger.
- Network posture: no production, staging, or external host scans. Repository
  analysis and local artifact generation only.
- Scanner posture: ingest scanner outputs only if they already exist and are
  explicitly authorized; do not start external scans from this plan.
- Publication posture: no GitHub Issues are created from audit output by
  default. Use `gra-issues --dry-run` only until human review approves a plan.

## In-scope application-security areas

| Area | Why it is in scope | Examples of review questions |
|---|---|---|
| RBAC and visibility boundaries | ITDO_ERP4 documents self-only, admin/mgmt, HR, project-member, and chat ACL boundaries; the risk register flags RBAC/ABAC as P0. | Are self-vs-admin and project-scope checks consistently applied? Are user-supplied IDs ignored or constrained where required? |
| Approval and state transitions | Approval, expense, invoice, purchase order, vendor invoice, leave, and time operations include guarded transitions, reasons, evidence, and audit logs. | Are invalid transitions rejected? Are reason/evidence requirements enforced before irreversible operations? |
| Expense, invoice, purchase, vendor invoice, and timesheet flows | These workflows represent financial, labor, and operational integrity risk. | Are submit, approve, reject, send, mark-paid, unmark-paid, edit, and link/unlink operations constrained by state, role, and ownership? |
| Agent-First write guardrails | Documentation describes ActionPolicy presets, approval/evidence gates, AgentRun replay, and fallback-readiness reports. | Can an agent-mediated draft or write path bypass policy, approval, evidence, reason, or audit replay requirements? |
| CI, supply-chain, and secret-detection posture | The repository documents blocking CI gates, npm audit, SBOM generation, secret scanning, CodeQL, and Dependabot monitoring. | Are documented gates aligned with workflows and test expectations? Are high/critical dependency and secret failures blocking where intended? |
| Attachments, storage, and AV paths | Security baseline and ops docs identify attachment malware and storage exposure as material risks. | Are upload paths, AV provider modes, fail-closed behavior, size limits, and attachment metadata handled consistently? |
| Backup/restore and operational readiness | Ops docs include backup/restore, DR, secrets/access, incident response, and release evidence. | Are backup/restore commands, destructive restore confirmations, evidence records, and secrets handling documented consistently? |

## Out of scope for this dogfood run

Do not perform or infer any of the following from this planning issue:

- production, staging, DAST, live endpoint, or external host scanning;
- credential access, token extraction, secret rotation, or account testing;
- exploit payload generation or weaponized proof construction;
- public vulnerability disclosure or public Issue creation for sensitive findings;
- remediation patch generation or PR creation in `itdojp/ITDO_ERP4`;
- broad architecture refactoring or quality work unrelated to AppSec scope;
- claims that a documented test gap is a vulnerability without repository review.

## Reporting tiers

| Tier | Location | Content boundary |
|---|---|---|
| Internal detailed | Local run directory under `runs/itdojp__ITDO_ERP4/RUN_ID/` | Full local evidence and candidate findings; private by default. |
| Internal sanitized | Local `.codex-local/dogfood/` memo or restricted tracker | Counts, target queue decisions, validation status, and follow-up routing without private evidence. |
| Public-safe | Committed planning docs or approved case study | Scope, commands, artifact categories, and bounded counts only; no vulnerability details. |

Follow the detailed boundary rules in
[`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md).

## Staged execution sequence

Run this sequence only after a human has approved the scope, target commit, and
retention decision:

```bash
gra-audit --repo itdojp/ITDO_ERP4 --mode prepare --model gpt-5.5 --effort xhigh

RUN=runs/itdojp__ITDO_ERP4/RUN_ID

gra-recon --run "$RUN" --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --generate --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --list

# Human review narrows target queue before deep research.
gra-research --run "$RUN" --target TGT-SELECTED --model gpt-5.5 --effort xhigh
gra-validate-report --run "$RUN"

# Add advanced stages only for reviewed, in-scope Critical/High candidates.
gra-adversarial-validate --run "$RUN" --all-critical-high --votes 3 --policy human-review-on-split
gra-chains --run "$RUN"
gra-proofs --run "$RUN" --all-critical-high

gra-metrics --run "$RUN"
gra-benchmark --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-dashboard --run "$RUN"
gra-validate-report --run "$RUN"
gra-issues --run "$RUN" --dry-run
```

`gra-issues --dry-run` is a preview, not approval to publish. Use
`gra-issues --plan` only after reviewing the preview, and use publication actions
only after the exact text has been approved through the disclosure process.

## Stop conditions

Stop and request human review if any of these occur:

- the target commit, authorization, or data-retention decision is unclear;
- a target requires production/staging access or external scanning;
- a candidate finding depends on private evidence, raw scanner output, proof,
  chain, trace, or remediation detail that cannot be safely summarized;
- validation downgrades, invalidates, or splits on a high-impact candidate;
- issue-publication dry-run generates warnings;
- public wording would require `--allow-public`; this is denied by default and
  may be used only after explicit disclosure approval, otherwise use SECURITY.md
  private reporting.

# ITDO_ERP4 dogfood target-selection plan

This document turns the scope in [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md) into
criteria for selecting a bounded target queue. It is not a finding list and does
not claim that any ITDO_ERP4 component is vulnerable.

## Selection principles

Prioritize targets that satisfy at least one of these conditions:

1. The area protects money movement, labor records, personal data, HR data,
   attachments, secrets, or audit evidence.
2. The ITDO_ERP4 docs classify the area as P0/P1 risk, A-priority test coverage,
   or a partial/no-automation gap.
3. The operation is irreversible or externally visible, such as send, approve,
   mark-paid, dispatch, retry, export, or destructive restore.
4. The workflow depends on multiple controls in sequence: role, ownership,
   project scope, state, reason, approval, evidence, policy, and audit log.
5. The result can be reviewed locally without production/staging access and
   without publishing private evidence.

De-prioritize targets that require live services, broad performance profiling,
large migrations, or policy decisions that cannot be evaluated from the local
repository and public/authorized documentation.

## First-wave target map

| Selection ID | Priority | Area | Source rationale | Primary review objective | Suggested target focus |
|---|---|---|---|---|---|
| ERP4-SCOPE-01 | P0 | RBAC and user/project visibility | Risk register lists RBAC/ABAC as P0; role docs define self, project, admin/mgmt, HR, and chat boundaries; test gaps track RBAC and self-only cases. | Check whether user-controlled IDs, project membership, and role boundaries are consistently enforced. | Expense/time/wellbeing/project/member/invoice list and detail paths that distinguish self, project member, admin/mgmt, exec, and HR. |
| ERP4-SCOPE-02 | P0 | Agent-First ActionPolicy, approval, evidence, and audit replay | ActionPolicy high-risk API docs and Agent Write guide describe phase2/phase3 presets, required actions, evidence gates, fallback reports, and AgentRun inspection. | Check whether agent-mediated draft/write paths can bypass policy, reason, approval, evidence, or audit replay requirements. | Draft APIs, send paths, approval action, fallback-readiness scripts, and AgentRun/audit-log records. |
| ERP4-SCOPE-03 | P0 | Financial state transitions | Expense and approval docs describe receipt, budget escalation, QA checklist, mark-paid/unmark-paid, reason, and audit-log requirements. | Check invalid transition rejection, reason enforcement, settlement controls, and owner/admin boundaries. | Expense submit/approve/reject/mark-paid/unmark-paid and state-transition retrieval. |
| ERP4-SCOPE-04 | P0 | Invoice, purchase order, and vendor invoice irreversible operations | High-risk API catalog lists invoice, purchase order, vendor invoice submit/send/approve/link/update operations; manual checklist covers PO/VI flows. | Check send/approve/link/unlink/update paths for state, role, evidence, and audit consistency. | Invoice send/mark-paid, purchase-order send, vendor-invoice submit/update/link/unlink. |
| ERP4-SCOPE-05 | P1 | Timesheet, leave, and wellbeing boundaries | Test gaps and manual checklist document self-only time entries, leave conflicts, HR-only wellbeing access, and labor/HR data sensitivity. | Check personal-data boundaries and state conflicts without using production data. | Time entry submit/edit, leave submit/approve/conflict, wellbeing entry and analytics access. |
| ERP4-SCOPE-06 | P1 | Attachment, storage, and AV behavior | Security baseline and ops AV runbook identify attachment malware, storage exposure, size limits, provider modes, and fail-closed expectations. | Check upload metadata, access controls, AV mode handling, failure behavior, and public exposure assumptions. | Chat attachments, expense attachments, AV configuration, storage path controls, and related audit events. |
| ERP4-SCOPE-07 | P1 | CI, secret scanning, supply chain, and SBOM | Quality gates and supply-chain docs define blocking CI, npm audit high/critical gate, secret-scan, CodeQL, SBOM, and Dependabot monitoring. | Check whether documented security gates match workflow behavior and evidence expectations. | `.github/workflows/*`, Dependabot config, secret scan scripts, SBOM export scripts, dependency watch docs. |
| ERP4-SCOPE-08 | P2 | Backup/restore, DR, secrets, and operations readiness | Ops index and backup/restore runbook document destructive restore confirmations, backup evidence, secrets/access, incident response, and release evidence. | Check that destructive commands, evidence records, secrets, and restore validation are guarded and reproducible. | Backup/restore helpers, DR templates, secrets/access docs, release backup evidence templates. |
| ERP4-SCOPE-09 | P2 | Audit-log completeness and evidence export | Approval operations, Agent Write guide, and security baseline require audit logs and evidence packs for review and replay. | Check whether critical actions emit enough bounded evidence for later review without leaking sensitive data. | Audit-log route/docs, evidence-pack export/archive, AgentRun drilldown, required event lists. |

## Target narrowing rules

After `gra-targets --list`, select at most six first-wave deep-review targets:

1. Include ERP4-SCOPE-01 and ERP4-SCOPE-02 unless the generated target queue
   lacks corresponding code paths.
2. Include at least one financial state-transition target from ERP4-SCOPE-03 or
   ERP4-SCOPE-04.
3. Include one CI/supply-chain target if workflow and script files are present in
   the prepared run clone.
4. Include attachments/AV only if the relevant implementation and configuration
   paths are present locally.
5. Include backup/restore only as documentation/script review unless a local,
   disposable restore fixture is explicitly approved.
6. Defer any target that requires production data, staging credentials, live
   services, or external scanning.

## Selection record template

Record target decisions in the local campaign ledger or local memo, not in this
repository:

```text
Target ID from gra-targets:
Mapped selection ID: ERP4-SCOPE-XX
Target title:
Why selected:
Why safe to review locally:
Excluded sub-scope:
Expected validation gates:
Publication boundary: private by default
```

Do not paste raw findings, code excerpts, scanner records, generated issue
bodies, or transcripts into the selection record.

## Expected validation by target type

| Target type | Minimum validation before any issue plan | Additional validation when Critical/High |
|---|---|---|
| RBAC / IDOR / ownership | `gra-validate-report`, human review of role/scope rationale | `gra-adversarial-validate --all-critical-high --votes 3 --policy human-review-on-split` |
| Approval / state transition | Validation plus review of state preconditions and audit-log expectations | Adversarial validation; safe local proof only if it is read-only or uses disposable fixtures. |
| Agent-First / ActionPolicy | Validation plus review of reason, approval, evidence, and AgentRun replay paths | Adversarial validation; chain/proof stages only for private handoff quality. |
| CI / supply chain | Validation plus workflow/script consistency review | Scanner/import review only from authorized existing outputs. |
| Attachments / AV / storage | Validation plus configuration and failure-mode review | Adversarial validation; no malware sample execution unless explicitly approved in a disposable local setup. |
| Backup/restore / ops | Documentation/script review and destructive-command guard review | No restore execution unless a disposable local database fixture and restore approval exist. |

## Pause and resume guidance

If target selection produces too many candidates, pause before deep review:

```bash
gra-run-state --run "$RUN" --pause \
  --reason "target queue requires human narrowing" \
  --resume-target TGT-SELECTED \
  --resume-condition "scope owner selects bounded first wave"
```

Resume only after the operator confirms selected targets and excluded sub-scope.

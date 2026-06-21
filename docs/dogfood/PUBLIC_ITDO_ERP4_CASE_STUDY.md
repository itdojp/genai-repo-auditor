# Public ITDO_ERP4 AppSec dogfood case study

This public-safe case study explains how GenAI Repo Auditor was applied to the
`itdojp/ITDO_ERP4` repository as a realistic application-security dogfood target.
It is written for README, blog, and stakeholder review use. It does not disclose
private findings, raw evidence, scanner records, target code excerpts,
exploitability narratives, remediation content, credentials, or local run
artifacts.

Use this with the planning and reporting references:

- [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md)
- [`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md)
- [`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md)
- [`ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md`](ITDO_ERP4_SCANNER_EVIDENCE_SUMMARY.md)
- [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)
- [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md)

## Why ITDO_ERP4 is a realistic AppSec target

ITDO_ERP4 represents the kind of business application where repository-level
security review must balance technical risk, operational safety, and disclosure
control. Its public/authorized documentation describes areas that are common in
enterprise systems:

| Business area | AppSec relevance |
|---|---|
| Role and project visibility | User, HR, management, project-member, and self-service boundaries require consistent authorization checks. |
| Approval and financial workflows | Expense, invoice, purchase, vendor, and settlement paths involve state transitions, reasons, evidence, and auditability. |
| Agent-mediated writes | ActionPolicy and Agent-First guardrails create a need to review approval, evidence, fallback, and audit replay paths. |
| Attachments and storage | Uploaded evidence and documents require controlled access, malware-handling posture, and failure-mode clarity. |
| CI and supply chain | Dependency, SBOM, secret-detection, CodeQL, and workflow gates influence release confidence. |
| Operations readiness | Backup/restore, incident, secrets/access, and release evidence determine whether security findings can be handled safely. |

The dogfood run therefore tested whether the auditor could keep a complex review
bounded: enough structure for useful AppSec decisions, but without public
exposure of target-specific details.

## Selected scope

The approved public-safe scope was local repository analysis only. The campaign
used staged execution: prepare and recon first, target queue generation second,
human narrowing third, and bounded deep research only after the target scope was
reviewed.

In scope:

- RBAC and visibility boundaries;
- approval, expense, invoice, purchase order, vendor invoice, timesheet, leave,
  and wellbeing workflow controls;
- Agent-First ActionPolicy and evidence requirements;
- CI, secret-detection, dependency, SBOM, and supply-chain posture;
- attachment, storage, AV, backup/restore, and audit-log readiness;
- publication planning with dry-run counts only.

Out of scope:

- production, staging, DAST, live endpoint, or external host scanning;
- credential access, account testing, token extraction, or secret rotation;
- public vulnerability disclosure from generated output;
- remediation work in `itdojp/ITDO_ERP4`;
- any public narrative that depends on target evidence, scanner records, or
  exploit steps.

## Architecture / workflow diagram

```text
Authorized target repo and docs
  -> gra-audit --mode prepare
  -> recon and target queue generation
  -> human scope narrowing
  -> bounded target research
  -> validation and deterministic reports
  -> metrics / benchmark / evidence graph
  -> issue publication dry-run
  -> public-safe case study and product feedback
```

Private by default:

```text
local run directory
  -> target clone
  -> recon and research notes
  -> findings and validation artifacts
  -> scanner records and normalized leads
  -> dashboard, store, transcripts, issue previews, and remediation candidates
```

The public document is a derivative summary. It carries workflow and bounded
count signals only.

## Workflow stages that were useful

| Stage | Public-safe result | Decision value |
|---|---|---|
| Target queue | 44 queued targets were generated; six first-wave candidates were selected for operator consideration; one bounded target was researched in this pass. | The queue made broad AppSec scope manageable and reviewable before deep analysis. |
| Scanner ingestion | No authorized current-run scanner artifacts were available for this pass. | The campaign recorded the absence explicitly instead of inventing scanner evidence. |
| Adversarial validation | No Critical/High candidate was advanced to the public case study. | The stage remains a safeguard for future high-impact private review rather than a public claim. |
| Chain synthesis | Not published and not needed for a public case study result. | The harness can support private relationship analysis without making that analysis public. |
| Safe proof artifacts | Not published and not needed for this bounded public summary. | Proof-oriented work remains gated behind local-only and human-review controls. |
| Metrics and benchmark | Benchmark gates passed: 7. | Quality gates gave an operator-readable signal that deterministic stages completed. |
| Evidence graph | Graph summary: 45 nodes and 0 edges for this bounded pass. | Aggregate graph counts helped distinguish workflow coverage from disclosure content. |
| Issue publication planning | `gra-issues --dry-run` reported a would-create Issue count of 0 and warning count of 0. No GitHub Issues were created from audit output. | Dry-run planning verified the publication path without publishing target details. |

These counts are intentionally narrow. They do not claim absence of all risk in
ITDO_ERP4, and they do not replace target-owner review.

## Sanitized metrics categories

| Category | Public-safe value |
|---|---|
| Target repository | `itdojp/ITDO_ERP4` |
| Target commit | Recorded locally; omitted from this public case study. |
| Run mode | Staged local repository review. |
| Targets generated | 44 |
| First-wave candidates considered | 6 |
| Targets deep-researched in this pass | 1 |
| Confirmed findings approved for public Issue publication | 0 |
| Scanner leads triaged | 0, because no authorized current-run scanner artifacts were ingested. |
| Benchmark status | 7 gates passed. |
| Evidence graph summary | 45 nodes / 0 edges. |
| Issue dry-run would-create Issue count | 0 |
| Issue dry-run warning count | 0 |
| Remediation candidates published | 0 |

Only aggregate counts are used. The local artifacts that support those counts are
not part of this repository.

## Decisions the harness helped make

The main value was not a public finding. It was disciplined decision support:

1. **Scope narrowing before deep review.** The target queue converted a broad ERP
   surface into a bounded first wave, reducing the chance of unfocused review.
2. **Evidence separation.** Public planning docs, internal summaries, local run
   artifacts, and target-repository reports had different handling rules.
3. **Scanner discipline.** Missing scanner evidence was treated as an explicit
   state, and scanner leads would remain review leads until validated.
4. **Disclosure routing.** Target-repository security-impacting candidates would
   go through `SECURITY.md` or GitHub Security Advisories first, not public
   Issues by default.
5. **Product-feedback routing.** GenAI Repo Auditor usability observations could
   become public product-improvement Issues when sanitized.
6. **Publication gating.** Dry-run issue planning gave counts and warnings
   without publishing any target-specific body text.

## How private details stayed out of public output

The campaign followed the reporting boundaries from
[`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md):

- local run directories, target clones, reports, dashboards, stores, transcripts,
  scanner records, and issue previews stayed outside Git;
- target-specific evidence and code excerpts were not copied into this case
  study;
- scanner information was summarized only as availability and count state;
- remediation candidates were not published;
- exact publication text would require human approval before any tracker action;
- sensitive target-repository security candidates would use private reporting
  first.

## Business value demonstrated

| Value | Demonstrated by |
|---|---|
| Local-first AppSec review | Analysis was organized around local run artifacts and explicit retention/cleanup decisions. |
| Business workflow awareness | Target selection prioritized authorization, approvals, financial state, agent-mediated actions, attachments, and operations. |
| Vendor-neutral AI agent harness | The workflow uses `gra-*` commands and compatible local agents without binding the public method to one model vendor. |
| Evidence validation | Validation, metrics, benchmark, and evidence graph stages created structured review checkpoints. |
| Controlled GitHub Issue publication | `gra-issues --dry-run` was used for preview counts only; no Issues were created from audit output. |
| Safer public communication | This case study explains process and aggregate outcomes without vulnerability details. |

## How to reuse this case study

Use this document when explaining a customer or internal dogfood workflow:

1. Start from scope and reporting-boundary documents before running analysis.
2. Publish only aggregate counts that have been reviewed for disclosure safety.
3. Keep target-specific security candidates on the target repository's private
   reporting path until the owner approves different handling.
4. Convert auditor usability friction into separate `genai-repo-auditor` product
   Issues when the text is sanitized.
5. Treat this case study as a public communication artifact, not as evidence that
   the target repository has or lacks any specific vulnerability.

## Summary

The ITDO_ERP4 AppSec dogfood pass showed that GenAI Repo Auditor can support a
realistic ERP-style repository review while keeping public output controlled. The
workflow generated a manageable target queue, recorded scanner-evidence
availability honestly, validated deterministic reporting stages, and exercised
issue-publication planning without creating public Issues from audit output. The
result is a reusable public-safe narrative for business stakeholders and a safer
handoff model for future private findings.

# ITDO_ERP4 second dogfood: public-safe aggregate summary

This document records the reviewed, count-oriented outcome of the second
authorized GenAI Repo Auditor dogfood campaign against `itdojp/ITDO_ERP4`. It
does not include target code paths, finding titles or bodies, evidence,
exploitability analysis, scanner output, remediation advice, local paths, or
generated run artifacts.

The first-pass narrative remains in
[`PUBLIC_ITDO_ERP4_CASE_STUDY.md`](PUBLIC_ITDO_ERP4_CASE_STUDY.md). Scope and
publication controls are defined by:

- [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md);
- [`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md);
- [`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md);
- [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md); and
- [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Authorization and boundaries

The campaign used a clean, read-only target snapshot and an isolated local run.
It performed repository analysis only. It did not modify ITDO_ERP4, access a
live environment, use credentials, scan an external host, pull a scanner image,
or publish an audit-derived GitHub Issue.

All recon, target, research, findings, scanner-plan, metrics, evidence-graph,
dashboard, transcript, and Issue-preview artifacts remain local and outside
Git. The target commit is recorded locally and intentionally omitted here.

## Executed workflow

The reviewed workflow was:

1. prepare an isolated run and verify local platform boundaries;
2. plan and execute the `recon-only` declarative profile;
3. resume its failed target-generation checkpoint after a temporary provider
   usage limit, without repeating successful recon;
4. review the generated queue and select exactly three bounded targets: one
   authorization/user boundary, one financial state-transition boundary, and
   one agent-mediated authorization/audit boundary;
5. deep-research those three targets sequentially with network access disabled;
6. independently review every candidate against source context;
7. generate validation, metrics, benchmark, evidence graph, and local dashboard
   artifacts; and
8. run Issue publication in dry-run mode only.

The final workflow execution status was `succeeded`. One interruption and one
checkpoint resume were recorded. Approximate hands-on operator review time was
45 minutes, excluding model execution waits.

## Aggregate results

| Measure | Reviewed public-safe value |
|---|---:|
| Targets generated | 47 |
| Targets selected | 3 |
| Targets deep-researched | 3 |
| Targets left queued | 44 |
| Candidate findings after human review | 4 |
| Candidate severity distribution | 4 Medium |
| Candidate status distribution | 1 Confirmed / 3 Probable |
| Downgraded or invalidated after human review | 0 |
| Critical or High candidates | 0 |
| Scanner adapters planned | 2 |
| Scanner adapters executed | 0 |
| Authorized scanner/external artifacts ingested | 0 |
| Normalized scanner leads triaged | 0 |
| Benchmark gates | 7 passed / 0 warnings / 0 failed |
| Evidence graph | 55 nodes / 18 edges |
| Issue dry-run would-create count | 0 |
| Issue dry-run warning count | 0 |
| Audit-derived GitHub Issues published | 0 |

These counts do not claim complete coverage or absence of additional risk. The
candidate status counts are disclosure-reviewed aggregate signals, not public
finding descriptions or authorization to publish target-repository Issues.

## Scanner and external evidence decision

Gitleaks and Syft plans were generated and reviewed. Both plans preserved
read-only target access, bounded local output, disabled network access, and
review-only classification. Execution was not attempted because neither an
approved local scanner executable nor an approved pre-pulled digest-pinned
scanner image was available. No image pull or network fallback was used.

The authorized snapshot contained no current-run CodeQL SARIF, CycloneDX/SBOM,
npm-audit, Trivy, Grype, or Scorecard result artifact eligible for ingestion.
Scanner triage therefore remained not executed rather than treating missing
evidence as a clean result. Future scanner evidence must remain a review lead
until repository context and reachability are checked.

## Validation and bounded omissions

Report validation, metrics generation, benchmark evaluation, evidence-graph
generation, local dashboard generation, and Issue dry-run completed
successfully. Metrics were refreshed after downstream report generation so the
aggregate summary includes benchmark and evidence-graph status.

Adversarial validation was not executed because the approved advanced-stage
gate applied only to Critical or High candidates and this campaign produced
none. Chain, proof, and remediation generation were likewise not required for
this bounded pass. These omissions are recorded decisions, not successful
security checks.

An independent source-level review retained the generated severity and status
for all four candidates. One candidate had low assessed false-positive risk;
three remained dependent on operational configuration or lifecycle context.
Those private distinctions and their evidence are intentionally excluded from
this public document.

## Product feedback

The target-specific candidates remain private. The following sanitized items
concern GenAI Repo Auditor itself and are suitable for product backlog review:

1. **Classify resumable provider failures.** A provider usage limit appeared as
   a generic stage exit. A bounded error category and retry-after field would
   make checkpoint decisions easier to automate and audit.
2. **Reduce deterministic target-queue noise.** Agent-surface and provenance
   seeds materially expanded the queue, including low-value or overlapping
   entries. Deduplication and a configurable seed budget would reduce operator
   review cost without suppressing broad recon.
3. **Expose explicit dry-run counts.** The machine-readable dry-run result should
   directly report would-create, filtered, and warning counts instead of
   requiring interpretation of a preview ledger.
4. **Prevent stale aggregate metrics.** Metrics generated before benchmark or
   evidence-graph output do not automatically include those artifacts. The
   workflow or documentation should make final refresh ordering explicit or
   detect stale dependencies.
5. **Report scanner prerequisite absence uniformly.** Plans should provide one
   bounded readiness summary covering runtime, immutable image availability,
   local executable availability, and the exact reason execution remains
   blocked, without running a scanner or pulling an image.

These observations are product-level workflow feedback. They do not describe
the ITDO_ERP4 candidates and must not be combined with private audit evidence in
a public Issue.

## Retention and publication decision

The local campaign record and generated artifacts remain retained under the
workspace's private local-state area for authorized follow-up. This aggregate
summary is the only campaign result proposed for Git in this change; publication
approval is determined through the pull-request review. Any future
target-repository report must follow the target owner's private disclosure path
and requires separate human approval.

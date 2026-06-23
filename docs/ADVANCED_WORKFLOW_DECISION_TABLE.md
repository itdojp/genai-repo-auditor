# Advanced workflow decision table

Use this table to decide when to run advanced GenAI Repo Auditor stages. The
default is conservative: run only the stages needed for the audit objective,
repository risk, and publication decision.

## Stage decision table

| Stage | Run when | Required before public Issue? | Key outputs | Do not use for |
|---|---|---|---|---|
| Gapfill (`gra-gapfill`) | Target coverage is shallow, high-risk files were skipped, or unresolved questions remain | Recommended for Critical/High findings with incomplete coverage | `COVERAGE.md`, `gapfill-targets.json` | Broadening into a new full audit |
| Chain synthesis (`gra-chains`) | Multiple findings, trust boundaries, or dependency paths may combine into higher impact | Required when public wording relies on composed impact | `chains.json`, `ATTACK_CHAINS.md` | Exploit chaining or public payload details |
| Safe local proofs (`gra-proofs`) | A finding needs benign local validation evidence | Required for high-impact claims unless not applicable with rationale | `proofs.json`, `PROOFS.md`, `proofs/` | Live exploitation, network probing, credential access |
| Adversarial validation (`gra-adversarial-validate`) | Critical/High finding, scanner/imported lead, chain, or public/customer handoff | Mandatory for Critical/High Issue publication | `validation.json`, `VALIDATION.md` | Creating new findings |
| Multi-vote validation | A finding is high impact, disputed, or customer/public facing | Recommended; use `human-review-on-split` | `votes[]`, aggregate decision | Treating split votes as approval |
| Strict issue plan (`--require-advanced-validation`) | Publication requires proof that advanced evidence was reviewed | Recommended for customer/public Critical/High Issues | `issue-publication-plan.json` | Bypassing human approval |
| Trace reachability (`gra-trace`) | Shared-library producer finding needs a specific consumer reachability check | Only with explicit approval; P3/experimental evidence | `traces.json`, `TRACE.md` | Claiming exploit proof or broad ecosystem scanning |
| Remediation candidates (`gra-remediate`) | Owner/customer approved draft fix planning for validated findings | Not required for publication; useful for handoff | `remediation-candidates.json`, patch validation reports | Autonomous patching or PR creation |
| Workflow profile (`gra-workflow-profile`) | A bounded run intentionally stops before advanced stages | Recommended for recon-only dogfood summaries | `workflow-profile.json`, `WORKFLOW_PROFILE.md` | Treating skipped stages as reviewed or risk-free |
| Metrics and benchmark | Release readiness, workflow tuning, or dogfood quality gates | Recommended for process improvement, not finding proof | `metrics.json`, `benchmark.json` | Replacing security review |
| Evidence graph | Handoff needs artifact lineage across findings, validation, remediation, and publication plans | Recommended for complex customer/internal handoff | `evidence-graph.json` | Publishing raw local artifact relationships |

## Scenario recommendations

### Internal audit

```text
Minimum: recon -> targets -> research -> validate-report -> dashboard
Add gapfill: high-risk area has shallow coverage
Add adversarial validation: any Critical/High finding before Issue planning
Add proofs/chains: claim depends on reachability, boundary crossing, or composed impact
Add remediation: owner approved draft fix planning
For recon-only dogfood: record gra-workflow-profile --profile recon-only before metrics/benchmark/evidence graph
```

### Customer audit

```text
Minimum: normal workflow plus validation report and dashboard
Recommended: gapfill, adversarial validation, metrics, benchmark, evidence graph
Required before customer-facing Critical/High handoff: adversarial validation and human review
Use --require-advanced-validation before Issue creation
Use gra-trace only for explicitly approved producer/consumer scope
```

### OSS public repository

```text
Default: private disclosure first
Required before public Issue: maintainer/security-policy approval and reviewed plan
Use --allow-public only after approval
Use chains/proofs/adversarial validation to improve private report quality, not to publish exploit detail
Do not publish trace, proof, chain, or scanner artifacts wholesale
```

## Copy-paste advanced sequence

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-GAPFILL-001 --mode exec
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

Run only the stages that are authorized and relevant. Do not run `gra-issues
--apply-plan` until the exact plan and issue body hashes have been reviewed.

## Decision rules

- If severity is Critical/High and status is Confirmed/Probable, run
  adversarial validation before any Issue plan is applied.
- If exploitability depends on multiple findings or trust-boundary composition,
  run chain synthesis but keep outputs private.
- If a finding needs evidence beyond static review, require safe local proof or
  mark the gap as `needs-human-review`.
- If validation returns `downgrade`, `invalidate`, or `needs-human-review`, do
  not publish until metadata and wording are revised or the residual uncertainty
  is explicitly accepted.
- If public disclosure is possible, use the strict issue plan and disclosure
  policy.
- If trace evidence is requested, confirm producer and consumer scope first and
  describe results as reachability evidence only.
- If remediation candidates exist, patch validation status must be reviewed
  before using them as handoff evidence.

## Related docs

- [`OPERATING_MODEL.md`](OPERATING_MODEL.md)
- [`CUSTOMER_AUDIT_RUNBOOK.md`](CUSTOMER_AUDIT_RUNBOOK.md)
- [`DISCLOSURE_AND_PUBLICATION_POLICY.md`](DISCLOSURE_AND_PUBLICATION_POLICY.md)
- [`REMEDIATION_WORKFLOW.md`](REMEDIATION_WORKFLOW.md)
- [`ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md)
- [`ATTACK_CHAINS.md`](ATTACK_CHAINS.md)
- [`SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md)
- [`TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md)

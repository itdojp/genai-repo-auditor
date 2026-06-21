# Evidence graph

`gra-evidence-graph` creates a local artifact map across the advanced audit
workflow. It helps reviewers answer which local artifacts support, challenge,
invalidate, or publish each finding without copying raw evidence payloads into a
new report.

## Command

```bash
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

The command writes:

```text
reports/evidence-graph.json
reports/EVIDENCE_GRAPH.md
```

`gra-validate-report` validates the graph shape when
`reports/evidence-graph.json` exists. `gra-dashboard` links and summarizes the
graph when present.

## Inputs

The graph is generated from local run artifacts only:

- `reports/findings.json`
- `reports/targets.json`
- `reports/scanner-results/scanner-index.json`
- `reports/chains.json`
- `reports/proofs.json`
- `reports/validation.json`
- `reports/traces.json`
- `reports/remediation/remediation-candidates.json`
- `reports/remediation/**/patch-validation.json`
- `reports/issue-publication-plan.json`
- `reports/metrics.json`

Only `findings.json` is expected for a useful graph. All other inputs are
optional; missing optional artifacts are recorded under
`summary.missing_optional_artifacts` rather than causing the command to fail.

## Node and edge model

Node types:

- `target`
- `scanner_lead`
- `finding`
- `chain`
- `proof`
- `validation`
- `trace`
- `remediation_candidate`
- `patch_validation`
- `issue_plan_entry`
- `metric`

Edge types:

- `supports`
- `challenges`
- `invalidates`
- `validated_by`
- `member_of`
- `depends_on`
- `publication_candidate`
- `produced`
- `not_applicable`

The graph keeps run-relative artifact references such as
`reports/findings.json#/findings/0`. High/Critical issue-recommended findings
are summarized with counts for inbound supporting and challenging evidence so a
reviewer can identify where evidence is strong, incomplete, or disputed.

## Safety constraints

The evidence graph is local/private by default. It stores bounded metadata only:

- finding IDs, titles, severity, status, and artifact pointers
- validation decisions and missing-evidence challenge links
- chain/proof/trace/remediation/Issue-plan IDs and status
- aggregate node/edge counts

It must not copy raw finding evidence, root cause text, impact text, remediation
text, proof payloads, full Issue bodies, or secret values. The validator rejects
forbidden raw-payload field names, secret-like values, unsafe artifact paths,
unknown node references, duplicate node/edge identifiers, and inconsistent
summary counts.

## Recommended placement in the workflow

Run the graph after advanced validation artifacts have been generated and before
final Issue publication review:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

Review `reports/EVIDENCE_GRAPH.md` and the dashboard before publishing Issues.
The graph is a review aid; it does not replace human confirmation for public
disclosure or maintainer-facing remediation work.

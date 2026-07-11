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
<reports_dir>/evidence-graph.json
<reports_dir>/EVIDENCE_GRAPH.md
```

`gra-validate-report` validates the graph shape when
`<reports_dir>/evidence-graph.json` exists. `gra-dashboard` links and
summarizes the graph when present. After the graph files are written,
`gra-evidence-graph` appends one v2 `evidence-graph` completion event to
`<reports_dir>/command-events.jsonl`; that event becomes visible on the
next `gra-metrics` execution, after which a later `gra-dashboard` run
can display the updated metrics.

## Inputs

The graph is generated from local run artifacts only:

- `<reports_dir>/findings.json`
- `<reports_dir>/targets.json`
- `<reports_dir>/scanner-results/scanner-index.json`
- `<reports_dir>/scanner-runs.json`
- `<reports_dir>/chains.json`
- `<reports_dir>/proofs.json`
- `<reports_dir>/validation.json`
- `<reports_dir>/traces.json`
- `<reports_dir>/remediation/remediation-candidates.json`
- `<reports_dir>/remediation/**/patch-validation.json`
- `<reports_dir>/issue-publication-plan.json`
- `<reports_dir>/metrics.json`
- `<reports_dir>/workflow-profile.json`

Only `findings.json` is expected for a useful graph. All other inputs are
optional; missing optional artifacts are recorded under
`summary.missing_optional_artifacts` rather than causing the command to fail.
The command resolves `<reports_dir>` from `context.json` and rejects unsafe
custom report paths.

## Node and edge model

Node types:

- `target`
- `scanner_run`
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
- `workflow_profile`
- `workflow_stage`

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
`<reports_dir>/findings.json#/findings/0`. High/Critical issue-recommended findings
are summarized with counts for inbound supporting and challenging evidence so a
reviewer can identify where evidence is strong, incomplete, or disputed.

## Safety constraints

The evidence graph is local/private by default. It stores bounded metadata only:

- finding IDs, titles, severity, status, and artifact pointers
- validation decisions and missing-evidence challenge links
- chain/proof/trace/remediation/Issue-plan IDs and status
- workflow-profile and stage IDs, status, and scoped-skip counts
- scanner adapter/status, bounded execution duration/counts, and links to
  normalized review-only lead artifacts
- aggregate node/edge counts

It must not copy raw finding evidence, root cause text, impact text, remediation
text, proof payloads, full Issue bodies, or secret values. The validator rejects
forbidden raw-payload field names, secret-like values, unsafe artifact paths,
unknown node references, duplicate node/edge identifiers, and inconsistent
summary counts. Successful completion-event writes are blocking; if the graph is
already failing after preflight, any follow-up event-write failure is degraded
to a warning so the original non-zero exit is preserved. Malformed input and
output write failures after preflight return `2`, emit a sanitized failed
`evidence-graph` event, and list only graph files that were actually written.

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

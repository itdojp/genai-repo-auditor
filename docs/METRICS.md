# Advanced workflow metrics

`gra-metrics` generates local-only aggregate metrics for one audit run. The goal
is to help operators assess whether advanced workflow stages are improving audit
quality, not merely increasing artifact volume.

Outputs:

```text
reports/metrics.json
reports/METRICS.md
```

Generate metrics after validation, chain synthesis, safe proofs, gapfill,
optional trace reachability, adversarial validation, and optional Issue plan or
Issue ledger creation:

```bash
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

## What is counted

Metrics are computed from local report artifacts only:

- finding counts by severity and status
- issue-recommended finding count
- adversarial validation decisions and downgrade/invalidate rate
- chain counts by status and severity
- proof counts by type and status
- gapfill current-run candidates/generated/reused counts and cumulative generated/reviewed queue counts
- trace reachability counts
- issue publication plan selected findings and warning counts
- issue ledger tracked, published, status, and drift-warning counts
- duplicate decision total, exact-match count, candidate Issue references, and decision buckets
- command event counts, execution durations, failures, reruns, and validation retries
- taxonomy normalization counts by target when normalization logs can be mapped to target IDs
- run artifact counts, manifest retention buckets, latest-status artifact count,
  archive artifact count, and manifest hygiene warning count
- run duration when present in local manifest metadata

Missing optional artifacts are represented with `artifact_present: false` and
zero counts. This allows early runs and partial staged workflows to produce a
stable metrics file.

Unexpected dimension values are bucketed as `Unknown`, `unknown`, or
`Not assessed` rather than copied verbatim. This keeps malformed local artifacts
from leaking raw report text or secret-like values through metric labels.

## Public-safe compact summary

`metrics.json` includes a top-level `summary` object for dogfood reports,
release notes, and public-safe case-study drafts. It contains only count fields
and simple status flags:

- `findings_total`, `findings_by_severity`, `findings_by_status`, and
  `issue_recommended_findings`
- `issue_publication_warning_count`,
  `issue_ledger_published_findings`, and
  `issue_ledger_drift_warning_count`
- `evidence_graph.artifact_present`, `node_count`, and `edge_count`
- `benchmark.artifact_present`, `overall_status`, gate totals, warnings, and
  failures when `reports/benchmark.json` is present
- `scanner.artifact_present`, `result_count`, and
  `normalized_leads_count` when scanner index artifacts are present
- `workflow_profile.artifact_present`, `profile`,
  `skipped_by_scope_count`, and status counts when
  `reports/workflow-profile.json` is present
- `no_findings.recorded`, `source_stage`, and `recon_only` for explicit
  no-confirmed-finding records

These fields are designed for external reuse only after human review confirms
that the repository name, timing, and aggregate counts are approved for the
target audience. Do not copy detailed metrics sections, finding bodies, raw
evidence, scanner leads, issue drafts, proof payloads, traces, dashboards, or
local paths into public material.

## Observability metrics

Instrumented workflow commands append structured JSONL command events to
`reports/command-events.jsonl`. Producers cover the audit entry point, recon,
target queue operations, target research, gapfill, variant analysis, chain
synthesis, safe proofs, adversarial validation, remediation, trace reachability,
and report validation. `gra-metrics` accepts both Issue #116 version `1` records
and the version `2` event contract. Version `2` adds unique `event_id` values,
retry/attempt metadata, bounded input/output artifact references,
worker/model/effort metadata when available, sandbox/network policy fields, and
sanitized error categories. `gra-metrics` turns those events into an
`observability` section with:

- command counts by command, phase, and exit code
- one sanitized duration record per command event
- failures by target ID, with run-level validation failures grouped under
  `__run__`
- reruns by target ID, computed from repeated command/phase execution for the
  same target
- validation retry counts from repeated `gra-validate-report` executions
- taxonomy normalization totals and per-target counts from
  `reports/taxonomy-normalizations.jsonl`

Command-event records are intentionally summary-only. They must not contain raw
prompts, environment variables, credentials, finding evidence, Issue bodies,
proof payloads, scanner bodies, private reasoning, or remediation patch
content. Command-completion event writes are blocking by default so operators
do not receive a successful command exit with missing execution evidence; any
warning-only event producer must be explicitly documented as non-critical.

`gra-dashboard` renders the longest target executions and the highest retry /
rerun targets from the same metrics artifact.

## Gapfill current versus cumulative metrics

Gapfill metrics intentionally separate the most recent `gra-gapfill --generate`
artifact from the cumulative target queue:

- `gapfill.current_run.candidate_count`: source targets selected in the current
  `gapfill-targets.json`
- `gapfill.current_run.generated_target_count`: generated or reused gapfill
  targets for those current candidates
- `gapfill.current_run.new_target_count` and `reused_target_count`: whether
  the current generate pass created new target IDs or reused existing
  source-target requeues
- `gapfill.cumulative.generated_target_count`: all `TGT-GAPFILL-*` / gapfill
  category targets currently present in `reports/targets.json`
- `gapfill.cumulative.reviewed_target_count` and `targets_by_status`: cumulative
  queue progress

The legacy `gapfill.targets_generated`, `gapfill.targets_reviewed`, and
`gapfill.targets_by_status` fields remain as cumulative aliases for older
consumers.

## Artifact retention metrics

When `run-manifest.json` is present, `gra-metrics` derives aggregate retention
counts without copying artifact content:

- `artifacts.manifest_by_retention`: counts for `latest`, `supporting`,
  `archive`, and `unknown` manifest entries
- `artifacts.latest_status_artifact_count`: artifacts listed in
  `artifact_retention.latest_status_artifacts`, the canonical handoff set for
  current run status
- `artifacts.archive_artifact_count`: artifacts listed in
  `artifact_retention.archive_artifacts`, retained for reproducibility but not
  active validation targets by themselves
- `artifacts.manifest_hygiene_warnings`: count of manifest consistency issues
  detectable from metrics input, such as missing summary paths, invalid
  retention values, or an archive artifact also listed as latest

`gra-dashboard` renders these counts in metric cards and an Artifact retention
table so operators can distinguish latest status artifacts from archive logs.
Run `gra-validate-report --run RUN_DIR` for the stricter manifest hygiene gate,
including path containment, file size, SHA-256 digest, and retention summary
count checks.

## Benchmarking with metrics

`gra-benchmark` consumes `reports/metrics.json` when present and uses in-memory fallback counts when it is absent. Use the benchmark after metrics generation for release or dogfood comparisons:

```bash
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
```

The benchmark records quality gates such as report validation status, adversarial downgrade/invalidate rate, chain count bounds, unsafe proof rejection count, Issue plan warnings, and publication-safety status without copying raw evidence. Its metrics summary also carries workflow-profile scoped-skip counts when present.

## Safety boundary

`gra-metrics` intentionally produces counts only. It does not copy raw finding
evidence, root causes, issue body text, proof evidence, trace evidence, scanner
lead bodies, or secret values into `metrics.json` or `METRICS.md`.

Keep metrics local unless repository names, finding counts, severity
aggregates, or workflow maturity data are approved for sharing.

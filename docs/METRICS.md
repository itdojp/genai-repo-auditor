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
- target-queue generated, active, retained-outside-budget, merged, deferred-by-budget, high-risk-deferred, and by-source reduction counts
- trace reachability counts
- issue publication plan selected findings and warning counts
- issue ledger tracked, published, status, and drift-warning counts
- duplicate decision total, exact-match count, candidate Issue references, and decision buckets
- scanner execution counts by status/adapter, total and maximum duration,
  result/normalized-lead counts, and redaction counts from `scanner-runs.json`
- declarative workflow execution status, stage durations, failures, scoped
  skips, blocked dependencies, explicit absence reasons, resume state, bounded
  provider-failure class/attempt counts, active failure counts, recovered-stage
  counts, retryable failure counts, and resume recommendations from
  `workflow-execution.json`
- command event counts, status/duration summaries, failures, reruns, retries,
  execution-configuration coverage, artifact-reference production counts,
  stage-group counts, and producer coverage
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


## Target queue budget and deduplication metrics

When `reports/targets.json` contains a deterministic `queue_summary`,
`gra-metrics` validates it against the closed queue contract and then reports:

- `target_queue.generated`: total source-lineage seed records considered
- `target_queue.active`: recorded selected review-wave size; target status
  updates do not rewrite this count until an explicit rebalance
- `target_queue.retained_outside_budget`: queued gapfill targets plus non-queued
  target history retained outside seed budgets
- `target_queue.merged`: cross-source overlaps collapsed into canonical targets
- `target_queue.deferred_by_budget`: currently deferred queued seeds
- `target_queue.high_risk_deferred`: deferred targets whose `risk` is
  `critical` or `high`
- `target_queue.by_source`: generated/active/retained/merged/deferred counts
  for every closed source (`model_generated`, `agent_surface`, `provenance`,
  `scorecard`, `dependency`, `scanner`, and `gapfill`)

If the queue summary is absent, the artifact remains readable for backward
compatibility. In that legacy mode `target_queue.available` is `false`,
`target_queue.active` falls back to the current `targets[]` length, and the
budget/dedup counters remain zero until `gra-targets --generate` or
`gra-targets --rebalance` writes the deterministic queue summary.

This lets operators distinguish the selected review wave from historical or
post-selection retained work and verify that high-risk deferred targets remain
visible rather than silently dropped. Use target status counts, rather than
`target_queue.active` alone, to measure unfinished work inside the selected
wave.

## Public-safe compact summary

`metrics.json` includes a top-level `summary` object for dogfood reports,
release notes, and public-safe case-study drafts. It always sets
`summary.public_safe` to `true` and contains only count fields and simple
status flags:

- `findings_total`, `findings_by_severity`, `findings_by_status`, and
  `issue_recommended_findings`
- `issue_publication_warning_count`,
  `issue_ledger_published_findings`, and
  `issue_ledger_drift_warning_count`
- `evidence_graph.artifact_present`, `node_count`, and `edge_count`
- `benchmark.artifact_present`, `overall_status`, gate totals, warnings, and
  failures when `reports/benchmark.json` is present
- `scanner.artifact_present`, `result_count`, and
  `normalized_leads_count` when scanner index artifacts are present, plus
  scanner-run presence, execution/status counts, bounded duration, and
  redaction counts when `scanner-runs.json` is present
- `workflow_profile.artifact_present`, `profile`,
  `skipped_by_scope_count`, and status counts when
  `reports/workflow-profile.json` is present
- `workflow_execution.artifact_present`, terminal/current status, profile,
  stage and duration counts, failed/scoped-skip/blocked stage IDs, absence
  reasons, resume stage, provider-failure totals and class counts, retryable and
  resume-recommended totals, active/recovered counts, and affected/recovered
  stage IDs when
  `reports/workflow-execution.json` is present;
  an absent optional report is represented by
  `absence_reason: workflow_execution_not_recorded`
- `no_findings.recorded`, `source_stage`, and `recon_only` for explicit
  no-confirmed-finding records

The compact public-safe summary intentionally excludes target-queue
`decisions[]`, `queue_fingerprint`, `source_lineage`, deferred target titles,
and other operator-only queue detail. Use the full local metrics artifact,
evidence graph, or dashboard when queue-budget triage detail is required.

These fields are designed for external reuse only after human review confirms
that the repository name, timing, and aggregate counts are approved for the
target audience. Do not copy detailed metrics sections, finding bodies, raw
evidence, scanner leads, issue drafts, proof payloads, traces, dashboards, or
local paths into public material.

## Observability metrics

Instrumented workflow commands append structured JSONL command events to
`<reports_dir>/command-events.jsonl`, where `<reports_dir>` comes from
`context.json` and defaults to `reports/`. Producers cover the audit entry
point, recon, target queue operations, target research, gapfill, variant
analysis, chain synthesis, safe proofs, adversarial validation, remediation,
trace reachability, scanner execution/ingestion, external finding import,
scanner triage, Issue publication preview/planning, declarative workflow
plan/execution/resume, report validation, metrics generation,
dogfood benchmarking, evidence-graph generation, dashboard rendering, SARIF
export, and SQLite store import. `gra-metrics` accepts both Issue #116 version
`1` records and the version `2` event contract. Version `2` adds unique
`event_id` values, explicit `status`, retry/attempt metadata, bounded
input/output artifact references, worker/model/effort metadata when available,
sandbox/network policy fields, and sanitized error categories. `gra-metrics`
turns those events into an `observability` section with:

- command counts by command, phase, exit code, and status
- one sanitized duration record per command event plus
  `duration_summary.total_ms`, `average_ms`, and `maximum_ms`
- `slow_subjects`, the longest-duration subject/command/phase records
- failures by target ID and subject ID, with run-level validation or reporting
  failures grouped under `__run__`
- reruns by target ID and subject ID, computed from repeated command/phase
  execution for the same target or subject
- explicit retry counts from `attempt > 1` or `retry_of`, plus per-subject
  retry buckets
- validation retry counts from repeated `gra-validate-report` executions
- execution-configuration coverage for worker profile, model, effort, sandbox
  profile, and network policy metadata
- artifact-reference production counts for total input/output refs and output
  refs by command
- stage-group coverage for scanner phases, remediation phases, and Issue
  publication phases
- producer coverage with expected producer count, observed count, observed and
  not-observed command lists, and coverage percentage
- taxonomy normalization totals and per-target counts from
  `reports/taxonomy-normalizations.jsonl`

Command-event records are intentionally summary-only. They must not contain raw
prompts, environment variables, credentials, finding evidence, Issue bodies,
proof payloads, scanner bodies, private reasoning, or remediation patch
content. When a reporting or persistence command writes outside the run
directory via `--out`, `--out-json`, `--out-md`, or `--db`, the external path
is intentionally omitted from `output_artifact_refs`; only run-contained
artifact references are recorded. Failed reporting events retain only output
files that actually exist, so planned but unwritten outputs do not inflate
artifact-production metrics. Successful command-completion event writes are
blocking by default so operators do not receive a successful command exit with
missing execution evidence. The six reporting/persistence producers preserve
an already non-zero exit by downgrading any follow-up failure-event write to a
warning.

Because `gra-metrics` writes `metrics.json` / `METRICS.md` before appending its
own completion event, the current metrics artifact does not count that
invocation's `gra-metrics` event. The same post-write completion policy applies
to `gra-benchmark`, `gra-evidence-graph`, `gra-dashboard`, `gra-sarif`, and
`gra-store`; their new events become visible on the next `gra-metrics`
execution, after which a later `gra-dashboard` run can display the
updated metrics.

The same sequencing applies when a `publication-ready` or `full` `gra-run`
profile invokes reporting commands as stages. Those stages observe the
in-progress workflow report. Rerun `gra-metrics` after terminal `gra-run`
completion to consume the final workflow status and the `gra-run` completion
event, then regenerate the evidence graph or dashboard as needed.

`gra-dashboard` renders the longest target executions, producer coverage,
execution-configuration coverage, workflow stage-group counts, artifact
retention, and the highest retry / rerun targets from the same metrics
artifact. It also renders provider-failure totals and closed class counts. These
counts are guidance for an explicit operator-controlled resume; they do not
guarantee a successful retry and do not trigger sleep, retry, network, or
credential behavior. Historical totals remain after a successful explicit
resume, while active and recovered counts distinguish current blockage from a
completed recovery.

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
consumers. Because gapfill targets are retained outside seed budgets, these
cumulative counts remain visible even when the active seed wave is capped.

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
lead bodies, provider response/stderr text, prompts, headers, identifiers, or
secret values into `metrics.json` or `METRICS.md`.

Keep metrics local unless repository names, finding counts, severity
aggregates, or workflow maturity data are approved for sharing.

# Reporting, Metrics, Benchmarks, SARIF, Dashboard, and SQLite Store

Validate reports:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

`gra-validate-report` always validates the structure of optional
`reports/report-freshness.json` and `reports/store-import-state.json` when they
exist. Add `--check-freshness` only when `stale` or `missing_dependency` tracked
derived reports should fail validation; structural validation alone does not
regenerate reports, publish Issues, or modify the SQLite database.

Each `gra-audit` run writes `run-manifest.json` at the run root. The manifest
contains bounded provenance metadata such as auditor version, command mode,
repository ref, network setting, schema filenames, generated artifact paths,
retention categories, and file size / SHA-256 digests. It does not contain
environment variables, credentials, raw scanner contents, or full finding
evidence. Paths in the manifest are run-relative; the artifact list intentionally
omits `run-manifest.json` itself to avoid unstable self-referential size
metadata. Treat it as support metadata; it is not a substitute for human review
of `<reports_dir>/findings.json`, issue drafts, or scanner leads. Reporting
commands resolve `<reports_dir>` from `context.json` and default to `reports/`.

The manifest separates `latest` status artifacts from `supporting` files and
`archive` reproducibility artifacts. `artifact_retention.latest_status_artifacts`
is the canonical handoff set for current run status. `archive_artifacts` keeps
prompts, transcripts, target research, variant analysis, scanner-result trees,
and similar logs discoverable with digests even when they are not active
validation targets. `gra-metrics` and `gra-dashboard` surface these retention
counts so operators can distinguish current handoff artifacts from retained
reproducibility logs. When a manifest snapshot is regenerated after declarative
workflow execution, `workflow-execution.json` and `WORKFLOW_EXECUTION.md` are
classified as latest-status artifacts.

Generate local novelty classification, metrics, dogfood benchmark gates, evidence graph, and dashboard:

```bash
gra-novelty --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
open runs/OWNER__REPO/RUN_ID/reports/dashboard.html
```

Each of `gra-metrics`, `gra-benchmark`, `gra-evidence-graph`, `gra-dashboard`,
`gra-sarif`, and `gra-store` appends one command-events v2 completion record to
`<reports_dir>/command-events.jsonl` after its primary output has been written.
That post-write policy means the current metrics, benchmark, evidence graph,
dashboard, SARIF export, or store import does not observe its own completion
event; the new event becomes visible on the next `gra-metrics`
execution, after which a later `gra-dashboard` run can display the
updated metrics. These reporting/persistence commands use non-reserving
event preflight, so a safety check does not leave behind a new empty
`command-events.jsonl` file when no log existed yet. Preflight validates the
planned event payload and context-derived identifiers before report output or
SQLite mutation, and its empty-file cleanup is serialized with concurrent
appenders by the command-event lock.

When `--out`, `--out-json`, `--out-md`, or `--db` points outside the run
directory, the external destination is intentionally omitted from event
`output_artifact_refs`. Event metadata keeps only run-contained refs such as
`context.json`, `<reports_dir>/metrics.json`, or `<reports_dir>/scanner-results/`.

## Derived report freshness

`reports/report-freshness.json` is the schema v1 sidecar for tracked default
derived reports. It records run-relative bounded fingerprints for the catalog
managed by `gra-sarif`, `gra-issues --plan`, `gra-store`, `gra-metrics`,
`gra-benchmark`, `gra-evidence-graph`, and `gra-dashboard`. `gra-metrics`,
`gra-benchmark`, `gra-evidence-graph`, and the default
`reports/issue-publication-plan.json` embed a public-safe `report_freshness`
generation-time snapshot copied from that sidecar. It is intentionally static;
the authoritative current state is `gra-validate-report --check-freshness` or a
fresh `assess_freshness` call. Tracked producer command events include
`report-freshness.json` in `output_artifact_refs` when they update it. `gra-store` also writes
`reports/store-import-state.json` with `database_location_recorded=false`; the
marker intentionally does not store the `--db` path.

The recommended regeneration order is fixed and intentionally repeats metrics
and dashboard so later reports can observe newly written peer artifacts and the
latest command-events state:

```text
gra-sarif --run <run_dir>
gra-issues --run <run_dir> --plan
gra-store --run <run_dir> --db <local_db_path>
gra-metrics --run <run_dir>
gra-evidence-graph --run <run_dir>
gra-dashboard --run <run_dir>
gra-benchmark --run <run_dir>
gra-metrics --run <run_dir>
gra-dashboard --run <run_dir>
```

Source reports are fingerprinted in `content` mode with SHA-256 and bounded
size checks, while peer derived reports and `command-events.jsonl` may use
`presence` mode to avoid non-converging cycles. `workflow-execution.json` is a
content dependency for both metrics and evidence graph, so rerun the reporting
sequence after terminal `gra-run` completion when workflow state changed.
Custom reports written outside the default catalog via alternate `--out`,
`--out-json`, or `--out-md` destinations remain intentionally untracked. An
external `--db` file is likewise never fingerprinted or named; the run-local
`store-import-state.json` marker remains the tracked store output.
Legacy structural validation remains compatible, but publication apply is
stricter: a missing sidecar or missing tracked default-plan record fails closed
and requires default-plan regeneration plus human review.

The metrics report summarizes findings, validation decisions,
downgrade/invalidate rate, chains, proofs, gapfill, traces, Issue plan warnings,
Issue ledger publication states, artifact counts, manifest retention buckets,
manifest hygiene warning counts, run duration when local metadata is
available, and command-event observability aggregates for status, duration,
failure, retry, execution configuration, artifact-ref production, workflow
stage groups, producer coverage, and bounded declarative workflow execution
status/duration/failure/skip/block/resume summaries. An absent optional
`workflow-execution.json` is represented explicitly rather than treated as a
successful execution. It intentionally omits raw finding
evidence, issue body text, proof evidence, trace evidence, scanner lead bodies,
and secret values.

The benchmark report scores local v0.4 quality gates from `metrics.json` when present and falls back to in-memory bounded counts when metrics are absent. It records validation status, obvious-secret scan count, adversarial downgrade/invalidate rate, chain bounds, unsafe proof rejection count, Issue plan warnings, and publication-safety status without copying raw evidence. When the benchmark already exits non-zero because a gate failed or a reporting error occurred, any follow-up completion-event write failure is downgraded to a warning so the original benchmark exit code is preserved.

The evidence graph links findings to supporting and challenging local artifacts
such as targets, chains, proofs, validation, traces, remediation candidates,
patch validation, Issue plans, workflow execution stages, and metrics. It
records bounded metadata and
run-relative artifact references only; it does not copy raw evidence,
remediation text, proof payloads, Issue bodies, or secrets. Like metrics and
benchmarking, a successful graph write is fail-closed, but an already failing
graph run preserves its non-zero exit even if the follow-up completion-event
append also fails.

The dashboard summarizes findings, target status, taxonomy mappings, known-finding
novelty status when `reports/known-findings.json` exists, dogfood benchmark gate status when `reports/benchmark.json` exists, evidence graph
coverage when `reports/evidence-graph.json` exists, advanced workflow metrics
when `reports/metrics.json` exists, imported external finding status when
`reports/imported-findings.json` exists, artifact retention status, derived
report freshness for the default tracked catalog when available, OpenSSF
Scorecard supply-chain posture when `reports/supply-chain-posture.json` exists,
dependency risk posture when `reports/dependencies.json` exists, the scanner
result index, slow command subjects, execution-configuration coverage, and
workflow stage-group counts.

Generate SARIF:

```bash
gra-sarif --run runs/OWNER__REPO/RUN_ID
```

Import to SQLite:

```bash
gra-store --run runs/OWNER__REPO/RUN_ID
sqlite3 runs/security-audit.sqlite '.tables'
```

The SQLite store is intended for local tracking across many runs. It also writes
`reports/store-import-state.json`, a bounded local marker that records imported
row counts and `database_location_recorded=false` without storing the SQLite
path used for `--db`. The SQLite store records:

- runs
- targets
- findings
- scanner results
- created issues from `reports/issue-ledger.json` when present, otherwise the
  legacy `issues-created.json` result
- optional posture artifacts

`gra-store` creates a backwards-compatible `posture_artifacts` table when it is
not already present. Each row is keyed by `run_id`, artifact type, and
run-relative path. Re-importing the same run replaces that run's posture rows so
removed optional artifacts do not remain as stale records. The table currently
tracks:

- `run_manifest` from `run-manifest.json` at the run root; the legacy/planning
  path `reports/run-manifest.json` is also accepted when present.
- `agent_surface` from `reports/agent-surface.json`.
- `supply_chain_posture` from `reports/supply-chain-posture.json`.
- `provenance_posture` from `reports/provenance-posture.json`.
- `dependencies` from `reports/dependencies.json`.

The artifact payload is retained as JSON in `data_json`, with query-friendly
columns for `status`, `item_count`, and `generated_at`. `item_count` is the
artifact's most useful local cardinality: manifest artifacts, agent surfaces,
Scorecard checks, provenance workflows, or dependency components depending on
the artifact type. Missing optional artifacts are skipped. Malformed optional
artifact JSON is recorded with status `invalid_json` rather than aborting the
entire import.

Build an index across a runs directory:

```bash
gra-index --runs-dir runs
```

`gra-index` writes `index.json` and `index.md`. In addition to finding severity
and status counts, each indexed run includes posture summary fields such as
`posture_artifact_count`, `agent_surface_count`, `scorecard_check_count`,
`provenance_workflow_count`, `dependency_component_count`, and
`dependency_vulnerability_count` when the optional artifacts are present.

GitHub Issue creation remains a separate, explicit step after human review. Run `gra-novelty` before `gra-issues --plan` when recurring audit dedupe or accepted-risk suppression should affect publication selection.

Successful completion-event writes for all six reporting/persistence producers
are blocking, so those commands do not report success with missing execution
evidence. When a reporting operation already has a non-zero result, its failed
completion event is attempted with warning-only append semantics so the
original exit code is preserved. Dashboard, SARIF, and store post-preflight
failures return `2`; store event metadata is fully preflighted before SQLite is
opened.

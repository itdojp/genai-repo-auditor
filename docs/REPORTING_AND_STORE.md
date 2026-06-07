# Reporting, Metrics, SARIF, Dashboard, and SQLite Store

Validate reports:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Each `gra-audit` run writes `run-manifest.json` at the run root. The manifest
contains bounded provenance metadata such as auditor version, command mode,
repository ref, network setting, schema filenames, and generated artifact paths.
It does not contain environment variables, credentials, raw scanner contents, or
full finding evidence. Paths in the manifest are run-relative; the artifact list
intentionally omits `run-manifest.json` itself to avoid unstable self-referential
size metadata. Treat it as support metadata; it is not a substitute for human
review of `reports/findings.json`, issue drafts, or scanner leads.

Generate local metrics and dashboard:

```bash
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
open runs/OWNER__REPO/RUN_ID/reports/dashboard.html
```

The metrics report summarizes findings, validation decisions,
downgrade/invalidate rate, chains, proofs, gapfill, traces, Issue plan warnings,
Issue ledger publication states, artifact counts, and run duration when local metadata is available. It
intentionally omits raw finding evidence, issue body text, proof evidence, trace
evidence, scanner lead bodies, and secret values.

The dashboard summarizes findings, target status, taxonomy mappings, advanced
workflow metrics when `reports/metrics.json` exists, OpenSSF Scorecard
supply-chain posture when `reports/supply-chain-posture.json` exists, dependency
risk posture when `reports/dependencies.json` exists, and the scanner result
index.

Generate SARIF:

```bash
gra-sarif --run runs/OWNER__REPO/RUN_ID
```

Import to SQLite:

```bash
gra-store --run runs/OWNER__REPO/RUN_ID
sqlite3 runs/security-audit.sqlite '.tables'
```

The SQLite store is intended for local tracking across many runs. It records:

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

GitHub Issue creation remains a separate, explicit step after human review.

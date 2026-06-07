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
- gapfill targets recommended, generated, and reviewed
- trace reachability counts
- issue publication plan selected findings and warning counts
- issue ledger tracked, published, status, and drift-warning counts
- duplicate decision total, exact-match count, candidate Issue references, and decision buckets
- command event counts, execution durations, failures, reruns, and validation retries
- taxonomy normalization counts by target when normalization logs can be mapped to target IDs
- run artifact counts
- run duration when present in local manifest metadata

Missing optional artifacts are represented with `artifact_present: false` and
zero counts. This allows early runs and partial staged workflows to produce a
stable metrics file.

Unexpected dimension values are bucketed as `Unknown`, `unknown`, or
`Not assessed` rather than copied verbatim. This keeps malformed local artifacts
from leaking raw report text or secret-like values through metric labels.

## Observability metrics

`gra-research`, `gra-gapfill`, and `gra-validate-report` append structured
JSONL command events to `reports/command-events.jsonl`. `gra-metrics` turns
those events into an `observability` section with:

- command counts by command, phase, and exit code
- one sanitized duration record per command event
- failures by target ID, with run-level validation failures grouped under
  `__run__`
- reruns by target ID, computed from repeated command/phase execution for the
  same target
- validation retry counts from repeated `gra-validate-report` executions
- taxonomy normalization totals and per-target counts from
  `reports/taxonomy-normalizations.jsonl`

`gra-dashboard` renders the longest target executions and the highest retry /
rerun targets from the same metrics artifact.

## Safety boundary

`gra-metrics` intentionally produces counts only. It does not copy raw finding
evidence, root causes, issue body text, proof evidence, trace evidence, scanner
lead bodies, or secret values into `metrics.json` or `METRICS.md`.

Keep metrics local unless repository names, finding counts, severity
aggregates, or workflow maturity data are approved for sharing.

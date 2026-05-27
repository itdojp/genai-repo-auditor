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
optional trace reachability, adversarial validation, and optional Issue plan
creation:

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
- run artifact counts
- run duration when present in local manifest metadata

Missing optional artifacts are represented with `artifact_present: false` and
zero counts. This allows early runs and partial staged workflows to produce a
stable metrics file.

Unexpected dimension values are bucketed as `Unknown`, `unknown`, or
`Not assessed` rather than copied verbatim. This keeps malformed local artifacts
from leaking raw report text or secret-like values through metric labels.

## Safety boundary

`gra-metrics` intentionally produces counts only. It does not copy raw finding
evidence, root causes, issue body text, proof evidence, trace evidence, scanner
lead bodies, or secret values into `metrics.json` or `METRICS.md`.

Keep metrics local unless repository names, finding counts, severity
aggregates, or workflow maturity data are approved for sharing.

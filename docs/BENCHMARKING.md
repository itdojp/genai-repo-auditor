# Dogfood benchmarking

`gra-benchmark` generates local v0.4 quality gates for a GenAI Repo Auditor run.
It is intended for dogfooding the advanced workflow before releases and before
turning audit output into follow-up work.

Outputs:

```text
<reports_dir>/benchmark.json
<reports_dir>/BENCHMARK.md
```

The benchmark is local-only. It does not call Codex, does not contact external
networks, and does not run `gra-issues --apply`. It records bounded counts,
rates, status values, and run-relative artifact paths only. It intentionally
excludes raw finding evidence, issue body text, proof payloads, scanner lead
bodies, and secret values. The command appends one v2 `benchmark` completion
event to `<reports_dir>/command-events.jsonl` after the benchmark files are
written. That completion event becomes visible on the next
`gra-metrics` execution, after which a later `gra-dashboard` run can
display the updated metrics.

## Quick fixture run

Run the built-in advanced fixture without network access:

```bash
gra-benchmark --fixture advanced
```

By default this copies the fixture under an ignored local path similar to:

```text
runs/benchmark-fixtures/advanced-YYYYMMDDTHHMMSSZ-PID/
```

Use `--out-run` when you need a deterministic location for local comparison:

```bash
gra-benchmark --fixture advanced --out-run runs/benchmark-fixtures/advanced-current
```

The fixture path is a copied run directory. Remove it when it is no longer
needed, or use the cleanup guidance in [`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md).

## Benchmark an existing run

After a normal or staged audit, validate and summarize the run:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

`gra-benchmark` consumes `<reports_dir>/metrics.json` when it exists. If
metrics are absent, it computes the same evidence-light counts in memory and
records `metrics.source: computed-fallback` in `benchmark.json`. Use that
fallback for ad-hoc review, then run `gra-metrics` before comparing trends
across runs.

## Gates

The initial v0.4 gate set is intentionally conservative:

| Gate | Failure or warning condition | Typical follow-up |
|---|---|---|
| Report validation | `gra-validate-report` exits non-zero | Fix schema, taxonomy, path-safety, or artifact contract errors. |
| Secret scan | Obvious full secret patterns appear in generated report artifacts | Redact or remove the local artifact before sharing output. |
| Adversarial downgrade/invalidate rate | Always recorded from metrics or fallback counts | Use trends to decide whether validation is reducing false positives. |
| Chain count bound | Chain count exceeds `--max-chains` | Triage noisy chain synthesis or reduce scope. |
| Proof unsafe rejection count | Unsafe proof or patch-validation command metadata is observed | Replace with safer local, read-only validation commands. |
| Issue plan warning count | Issue plan warnings are non-zero | Resolve warnings before any publication step. |
| Public Issue apply | Existing public publication ledger entries are detected | Confirm human approval and disclosure sign-off. |

Warnings produce `overall_status: needs-review` but keep the command exit status
at `0`. Failed gates produce `overall_status: failed` and exit status `1`.
`benchmark.json` also includes a compact `summary` object with
`overall_status`, gate count, passed gates, warnings, and failures. When
`<reports_dir>/benchmark.json` is present, `gra-metrics` copies those gate totals
into `metrics.summary.benchmark` so dogfood reports do not need to scrape
`BENCHMARK.md` tables manually. The benchmark metrics summary also carries the
workflow profile name and `workflow_skipped_by_scope_count` when
`<reports_dir>/workflow-profile.json` is present. Successful completion-event
writes are blocking; when the benchmark is already returning `1` or `2`, any
follow-up event-write failure is downgraded to a warning so the original exit
code is preserved. External `--out-json` / `--out-md` destinations outside the
run directory are intentionally omitted from event artifact refs.

Tune the chain bound for a specific dogfood run:

```bash
gra-benchmark --run runs/OWNER__REPO/RUN_ID --max-chains 10
```

## Creating follow-up issues from results

Use `reports/BENCHMARK.md` as the local triage summary. Create follow-up issues
only from the bounded gate names, counts, and local artifact paths, not from raw
evidence. A safe follow-up issue should include:

```text
Title: Reduce noisy chain synthesis in v0.4 dogfood benchmark

Observed local gate:
- Gate: Chain count is bounded
- Status: fail
- Value: 42
- Threshold: 25
- Run: OWNER/REPO RUN_ID

Requested change:
- Investigate chain synthesis prompt or dedupe behavior.
- Add a regression fixture that keeps chain count under the agreed bound.

Do not include:
- raw finding evidence
- issue draft body text
- proof payloads
- scanner lead bodies
- secret values
```

Keep the full `benchmark.json`, `metrics.json`, dashboard, scanner outputs, and
audit run artifacts local unless sharing has been explicitly approved.

## Release use

For release readiness, run at least:

```bash
gra-benchmark --fixture advanced
gra-benchmark --run runs/OWNER__REPO/RUN_ID
```

A release should not rely on a benchmark result alone. Treat it as one input
alongside tests, CI, CodeQL, documentation review, and human security review.

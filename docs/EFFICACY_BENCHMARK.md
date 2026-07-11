# Deterministic security efficacy benchmark

`gra-efficacy-benchmark` runs the versioned synthetic corpus with an offline,
deterministic reference detector and writes bounded scoring reports. It tests
the corpus loader, runner selection, score calculation, and report contract.

This command is intentionally separate from
[`gra-benchmark`](BENCHMARKING.md):

- `gra-efficacy-benchmark` scores synthetic security ground truth;
- `gra-benchmark` evaluates workflow health and publication-safety gates for an
  audit run.

Neither command replaces human security review. The reference detector is a
runner/scoring smoke baseline, not a product-efficacy claim.

## Safety boundary

Fixture mode uses only packaged, non-deployable synthetic files. It does not:

- contact a network or GitHub;
- invoke a model, worker, scanner, shell command, or repository audit;
- publish an Issue or modify a target repository;
- copy fixture source, raw evidence, or finding bodies into its reports.

The command fails closed when the corpus integrity contract, selected case,
report schema, or output path is invalid. Output parents and files must not be
symlinks. Report writes require Python/OS support for directory-relative file
operations and fail closed before creating an output when that support is not
available. `--list`, `--help`, and `--version` remain available on platforms
without that support. Reports are limited to 1,000,000 bytes each.

The current public corpus has 20 cases arranged as ten positive/control pairs
across seven security categories. The deterministic reference detector matches
explicit policy fields and small auditable code properties; it does not branch
on case IDs, directories, or fixture filenames. This breadth improves regression
coverage only and does not change the claim boundary below.

## List cases and suites

List the default `core` suite:

```bash
gra-efficacy-benchmark --list
```

List a category suite:

```bash
gra-efficacy-benchmark --list --suite appsec
```

Available suites are declared by the corpus and currently include `core`,
`agentic`, `appsec`, `automation`, and `supply-chain`. Select individual cases
by repeating `--case`; case selection and suite selection are mutually
exclusive:

```bash
gra-efficacy-benchmark --list \
  --case python-web/authz-001 \
  --case python-web/authz-control-001
```

## Run the deterministic fixture benchmark

Run all cases in the default suite:

```bash
gra-efficacy-benchmark
```

Default outputs:

```text
reports/efficacy-benchmark.json
reports/EFFICACY_BENCHMARK.md
```

Use explicit destinations for a disposable comparison run:

```bash
gra-efficacy-benchmark \
  --out-json .test-tmp/efficacy/first.json \
  --out-md .test-tmp/efficacy/first.md
```

The JSON report conforms to
`templates/reports/efficacy-benchmark.schema.json`. It contains only bounded
case identifiers, classifications, outcomes, counts, rates, coverage/review
flags, corpus versions, detector identity, and explicit safety/limitation
metadata.

## Metrics

The aggregate report records:

| Metric | Meaning |
|---|---|
| True positive (TP) | An expected vulnerability class was predicted for a positive case. |
| False positive (FP) | A predicted class did not match an expected finding, including any prediction on a negative control. |
| False negative (FN) | An expected vulnerability class was not predicted. |
| True negative (TN) | A negative control produced no predictions. |
| Precision | `TP / (TP + FP)`; `null` when the denominator is zero. |
| Recall | `TP / (TP + FN)`; `null` when the denominator is zero. |
| F1 | Harmonic mean of precision and recall; `null` when either input is not applicable. |
| Severity agreement | Matched predictions whose severity is within the ground-truth range. |
| Target coverage | Selected cases whose declared fixture was inspected. |
| Human-review count | Cases requiring review because a signal was found or the reference rule was unsupported. |

Matching uses the bounded `vulnerability_class` identifier. It does not compare
or emit exploitability narratives, raw fixture snippets, affected locations,
or remediation text.

## Determinism check

For a fixed checkout, corpus version, command version, selection, and output
format, repeated fixture runs must produce byte-identical JSON and Markdown.
The report deliberately contains no clock time, duration, hostname, absolute
fixture path, process ID, or random run identifier.

```bash
mkdir -p .test-tmp/efficacy
gra-efficacy-benchmark --out-json .test-tmp/efficacy/a.json --out-md .test-tmp/efficacy/a.md
gra-efficacy-benchmark --out-json .test-tmp/efficacy/b.json --out-md .test-tmp/efficacy/b.md
cmp .test-tmp/efficacy/a.json .test-tmp/efficacy/b.json
cmp .test-tmp/efficacy/a.md .test-tmp/efficacy/b.md
```

## Interpretation and failure handling

A perfect synthetic score establishes only that the pinned reference rules and
runner agree with the pinned fixtures. It does not establish production recall,
precision, severity accuracy, model quality, or support for a language or
framework. Do not publish benchmark-derived findings automatically.

Exit status `0` means listing or report generation succeeded. Status `2` means
usage, corpus validation, selection, schema validation, or output safety failed.
On failure, inspect stderr, correct the local contract or destination, and rerun.
Do not bypass integrity, symlink, or missing-dirfd failures. On native Windows
CPython where the required directory-relative operations are unavailable, use
`--list` and run report generation in WSL2/Linux/macOS. The same boundary
applies to deterministic comparison and optional worker mode because both must
publish the final report pair safely. See
[`WINDOWS_WSL_SUPPORT.md`](WINDOWS_WSL_SUPPORT.md).

The corpus structure and case-maintenance procedure are documented in
[`EFFICACY_BENCHMARK_CORPUS.md`](EFFICACY_BENCHMARK_CORPUS.md).

## Compare configurations

List and run the deterministic comparison configurations:

```bash
gra-efficacy-benchmark --list-configurations
gra-efficacy-benchmark --compare
```

Comparison mode writes `reports/efficacy-comparison.json` and
`reports/EFFICACY_COMPARISON.md` by default. It identifies every configuration
and case, records aggregate scores and bounded case outcomes, and encodes claim
and publication guardrails. The default comparison is byte-stable and does not
invoke a worker.

Worker-assisted comparison requires explicit `--worker` and an existing local
`--worker-dir` below the current working directory. The directory must not be a
symlink or the current directory itself and should be ignored by version
control. Worker mode requires Codex CLI 0.135.0 or newer. It uses the built-in
worker profile with read-only sandbox and
sandbox network disabled. It also uses an ephemeral session and ignores user
configuration and project/user rules. The configured model/control-plane
channel is still used. Worker artifacts remain local in that directory and the
worker row is non-deterministic. Read-only sandboxing is not a confidentiality
boundary for every host-readable file; use separate host isolation when needed.

Complete methodology and publication rules are in
[`EFFICACY_CLAIMS_AND_PUBLICATION.md`](EFFICACY_CLAIMS_AND_PUBLICATION.md).
Private holdout material must not be added to this packaged corpus or passed to
this public-corpus command. Use the separate aggregate-only validation protocol
in [`PRIVATE_HOLDOUT_PROTOCOL.md`](PRIVATE_HOLDOUT_PROTOCOL.md).

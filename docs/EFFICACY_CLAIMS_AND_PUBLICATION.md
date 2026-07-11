# Efficacy comparison, claims, and publication policy

This policy governs results from `gra-efficacy-benchmark --compare`, including
optional worker-assisted runs. The synthetic corpus is a regression instrument,
not representative production evaluation data.

## Methodology

A valid deterministic comparison holds these inputs fixed:

- repository checkout and command version;
- corpus ID, content-bound corpus version, suite, and exact case IDs;
- report schema and selected configuration IDs;
- output format.

The default comparison runs two deterministic reference-review workflow
configurations over the same cases:

| Configuration | Purpose |
|---|---|
| `reference-review-all-signals-v1` | Run fixture reference review and retain every supported synthetic signal. |
| `reference-review-high-severity-gate-v1` | Run the same review, then retain only High/Critical signals at a review gate. |

The report records each configuration ID, all selected case IDs, aggregate
TP/FP/FN/TN and rates, bounded per-case outcomes, and deltas from the first
configuration. It excludes fixture text, evidence narratives, locations,
remediation text, exploit steps, worker prompts, transcripts, and credentials.

Each report row records its `workflow_stage_ids`, making the configured stage
difference explicit. These reference workflows are intentionally simple
runner/scoring controls; they are not aliases for scanner-only, AI-only, or
full production-harness execution.
A score difference demonstrates that the comparison machinery detects a pinned
configuration difference. It does not establish that either configuration is a
production security-review strategy.

## Optional worker-assisted comparison

Worker execution is disabled unless all of `--compare`, `--worker`, and
`--worker-dir` are supplied. The initial supported worker is the built-in
`codex-cli` profile. The command:

- sends only public-safe synthetic fixture input through the configured model
  channel;
- uses approval `never`, a read-only sandbox, disabled web search, and sandbox
  network access `false`;
- uses an ephemeral session, ignores user configuration and project/user rules,
  and supplies the closed worker response schema to Codex CLI;
- does not expose a flag that enables sandbox network access;
- resolves the exact `codex` command from the operator's trusted `PATH` once,
  rejects a modified built-in profile executable name, and passes a reduced
  environment that omits common unrelated repository/cloud credentials;
- requires a closed bounded JSON response and discards narrative fields from
  the comparison report;
- monitors event, stderr, and response sizes while the process runs and stops a
  worker that crosses a configured limit;
- retains prompt, event, response, and stderr artifacts only in the explicitly
  selected local worker directory. The generated response schema is retained
  there as well.

The worker row is marked `deterministic: false` and identifies its profile and
model, effort, and Codex CLI version. Worker mode requires Codex CLI 0.135.0 or
newer because its isolated execution contract depends on `--ephemeral`,
`--ignore-user-config`, `--ignore-rules`, and `--output-schema`. The worker
command performs this version gate; `gra-agent-check` separately reports only
whether the profile executable exists. Do not compare worker results across
different models, efforts, prompts, command versions, or corpus versions as if
only one variable changed.

The model service/control-plane channel is necessarily used in worker mode. The
safety field `external_network_beyond_model_channel_enabled: false` records the
launcher configuration: the subprocess sandbox is not granted separate network
access, user configuration is ignored, and web search is disabled. It does not
claim that worker mode is offline or that network activity was independently
observed.

The launcher supplies only the selected fixtures, but a Codex read-only sandbox
is not an operating-system confidentiality boundary for every host-readable
file. The prompt prohibits commands and unrelated reads; this is an instruction,
not proof of non-access. Use a dedicated host or separately administered
container when the host contains material the worker must not be able to read.
Treat the selected `codex` executable and the model service as trusted
dependencies. Model authentication and proxy variables needed by Codex may
still be present in the reduced worker environment; unrelated variables such as
GitHub and cloud-provider tokens are not forwarded.

## Unsupported claims

The following claims are prohibited from this corpus alone:

- product-wide vulnerability recall, precision, or false-positive rate;
- support or superiority for a language, framework, vulnerability class,
  worker, model, provider, or workflow;
- guaranteed discovery, complete coverage, production readiness, or release
  safety;
- comparative model superiority or statistically significant improvement;
- validation of a finding in a real repository.

Reports encode `product_capability_claim_allowed: false` and
`production_performance_claim_allowed: false`. These are policy controls, not
optional annotations.

Permitted internal wording is narrow: for example, "configuration A produced
five true positives on corpus version X for the listed case IDs." Always name
the corpus version, configuration IDs, case IDs or suite, command version, and
whether a worker/model channel was used.

## Publication and disclosure

Comparison reports and worker artifacts are local by default. A report may be
shared only after a human verifies that it contains no private repository
material, credentials, raw worker transcript, unsupported claim, or misleading
production implication.

Benchmark output never authorizes publication of a security finding or GitHub
Issue. A real-repository finding still requires repository-specific evidence,
adversarial validation, disclosure review, and the normal Issue publication
workflow. Synthetic case IDs must not be presented as affected production
assets.

Before approved aggregate publication:

1. verify the closed report schema and safety flags;
2. record corpus/command/configuration/model versions;
3. distinguish deterministic reference rows from non-deterministic worker rows;
4. state the small synthetic-corpus limitation near every score table;
5. remove local paths and do not attach worker artifacts;
6. obtain security/disclosure owner approval.

## Required regression check

CI runs the deterministic comparison only. It must not invoke a worker, model,
GitHub operation, or network helper. For a local verification:

```bash
gra-efficacy-benchmark --list-configurations
gra-efficacy-benchmark --compare \
  --out-json .test-tmp/efficacy-comparison.json \
  --out-md .test-tmp/EFFICACY_COMPARISON.md
```

Run worker-assisted comparison only as an explicitly approved, supervised local
operation. `--worker-dir` must be an existing non-symlink directory below the
command's current working directory, must not equal that directory, and should
be ignored by version control (for example `.test-tmp/efficacy-worker`).

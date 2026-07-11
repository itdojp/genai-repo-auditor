# Command Reference

This reference covers the current `bin/gra-*` command surface for GenAI Repo Auditor.
Commands are grouped by workflow phase so operators can choose the smallest command needed for a run.

All examples use placeholder repositories and local run paths. Do not paste real vulnerability details, full secrets, or private findings into public issues, documentation, logs, or support requests.

## General conventions

- Run commands from a checked-out `genai-repo-auditor` repository with `bin/` on `PATH`, call commands through `./bin/<command>`, or use installed package console scripts after building/installing the Python package.
- Every current `gra-*` command supports `--help` and `--version`. `--version` prints the command name and the canonical repository `VERSION` value without running an audit or invoking `gh`, `codex`, or other workflow tools.
- Release archives preserve that canonical `VERSION` file. Release preparation and integrity verification are separate from the `gra-*` command surface and are documented in [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).
- Most commands operate on a run directory such as `runs/OWNER__REPO/RUN_ID`.
- `--network` enables network access inside the Codex sandbox for commands that call Codex. It is disabled by default and should remain disabled unless an approved workflow requires it.
- `--model` defaults to `gpt-5.5` and `--effort` defaults to `xhigh` for Codex-driven commands. Command-line `--model` / `--effort` options are the portable override mechanism across Codex-driven commands.
- Non-interactive `codex exec` invocations set approval behavior through `-c 'approval_policy="never"'` rather than the interactive-only `--ask-for-approval` flag, preserving compatibility with `codex-cli 0.135.0`.
- Codex-driven commands derive the default executable name from the built-in `codex-cli` worker profile while preserving the tested `codex exec` argument construction in `lib/gralib.py`. `gra-agent-check` can list profiles and check whether the required local worker executable is available without running the worker. `gra-doctor` combines those local readiness checks with redacted package, Git/GitHub CLI availability, opt-in authentication-state probes, sandbox-runtime, and writable-run-directory diagnostics.
- Executable target-code validation should be gated by an explicit sandbox profile. `gra-sandbox-check` records readiness for `source-only`, `local-test`, `container`, `gvisor`, and `vm` profiles without executing target code.
- Environment-variable model/effort defaults are limited to `gra-audit` and `gra-batch`, whether invoked from source-checkout wrappers or installed package console scripts. They read `GRA_MODEL`, `CODEX_MODEL`, `GRA_REASONING_EFFORT`, and `CODEX_REASONING_EFFORT`. Staged Python commands such as `gra-recon`, `gra-targets`, `gra-research`, `gra-gapfill`, `gra-variant`, `gra-chains`, `gra-proofs`, `gra-trace`, `gra-no-findings`, `gra-workflow-profile`, `gra-metrics`, `gra-benchmark`, `gra-evidence-graph`, `gra-import-findings`, `gra-adversarial-validate`, and `gra-scanner-triage` ignore those environment variables and require explicit CLI options.
- Python commands use `argparse`; missing required arguments or invalid choices normally exit with status `2`.
- Generated audit artifacts, cloned target repositories, scanner raw outputs, issue drafts, and local stores should remain local and should not be committed.

## Workflow map

| Phase | Commands | Typical output |
|---|---|---|
| Install readiness diagnostics | `gra-doctor`, `gra-agent-check` | Redacted local readiness report, package resource checks, worker profile and executable availability diagnostics |
| Prepare / full audit | `gra-audit` | Run directory, cloned target, rendered prompts, Codex output, reports |
| Batch operation | `gra-batch` | Batch metadata, per-repository logs, `batch-results.json` |
| Target queue | `gra-targets` | `reports/targets.json`, target queue updates |
| Run state / pause guard | `gra-run-state` | `reports/run-state.json`, pause/resume/block status |
| Sandbox readiness | `gra-sandbox-check` | `reports/sandbox-readiness.json`, `reports/SANDBOX_READINESS.md` |
| Worktree separation check | `gra-worktree-check` | Final worktree report classifying in-scope and unrelated changes |
| Target coverage gapfill | `gra-gapfill` | `reports/COVERAGE.md`, `reports/gapfill-targets.json`, bounded gapfill target research |
| Research / recon / variant analysis | `gra-recon`, `gra-research`, `gra-variant` | Recon notes, target research, findings updates, variant reports |
| Adversarial validation | `gra-adversarial-validate` | Bounded validation prompt, subject seed JSON, `reports/validation.json`, `reports/VALIDATION.md` |
| Chain synthesis | `gra-chains` | Defensive chain prompt, `reports/chains.json`, `reports/ATTACK_CHAINS.md` |
| Safe local proofs | `gra-proofs` | Benign proof prompt, subject seed JSON, `reports/proofs.json`, `reports/PROOFS.md`, `reports/proofs/` |
| Remediation candidates | `gra-remediate` | Draft-only remediation prompt, subject seed JSON, `reports/remediation/remediation-candidates.json`, local patch drafts |
| Cross-repo trace reachability | `gra-trace` | Experimental/P3 trace prompt, subject seed JSON, `reports/traces.json`, `reports/TRACE.md` |
| Scanner planning/execution / external finding import | `gra-scan`, `gra-ingest`, `gra-import-findings`, `gra-scanner-triage` | Non-executing adapter inventory/plans, explicit bounded offline scanner execution, raw scanner copies, redacted normalized leads, scanner index, review-only imported finding artifacts, Scorecard posture artifacts, dependency posture artifacts, triage output |
| Validation | `gra-no-findings`, `gra-workflow-profile`, `gra-taxonomy-preflight`, `gra-validate-report` | Explicit no-confirmed-finding artifact, workflow scope profile, controlled taxonomy preflight, report contract validation result |
| Reporting / persistence | `gra-metrics`, `gra-benchmark`, `gra-evidence-graph`, `gra-dashboard`, `gra-sarif`, `gra-store`, `gra-index` | Local metrics, dogfood benchmark gates, evidence graph, HTML dashboard, SARIF, SQLite store, run index |
| Issue workflow | `gra-issues` | Dry-run previews, canonical issue ledger, duplicate decision records, ledger verification, or GitHub Issues after human review |

## `gra-agent-check`

| Field | Details |
|---|---|
| Purpose | List local AI worker adapter profiles and verify that a selected profile's required executable is present on `PATH` without executing the worker. |
| Workflow category | Install readiness diagnostics. |
| Required inputs | One action: `--list` or `--profile PROFILE_ID`. Built-in profiles are loaded from `templates/agent-workers/`. |
| Key options | `--list`, `--profile PROFILE_ID`, `--json`, and `--profiles-dir DIR` for tests or local profile experiments. |
| Generated outputs | Text table or JSON profile summaries for `--list`; text or JSON availability diagnostics for `--profile`. No audit run artifacts are written. |
| Exit status behavior | `0` for successful listing or for a selected profile whose required executable is present; `1` when the selected profile is valid but its executable is missing; `2` for unknown profile IDs, invalid profile files, or usage errors. |
| Security / disclosure cautions | The command performs local profile validation and `PATH` resolution only. It does not execute worker CLIs, call vendor SDKs, contact managed services, or enable network access. Non-Codex profiles are experimental examples until separately tested. |
| Related docs | [`docs/AGENT_WORKERS.md`](AGENT_WORKERS.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-agent-check --list
gra-agent-check --profile codex-cli
gra-agent-check --profile codex-cli --json
```

## `gra-doctor`

| Field | Details |
|---|---|
| Purpose | Run redacted local readiness diagnostics for an installed or source-checkout GenAI Repo Auditor environment before an audit. |
| Workflow category | Install readiness diagnostics. |
| Required inputs | None. Use `--runs-dir DIR` to select the run-directory root that should be probed for local write readiness. |
| Key options | `--json`, `--runs-dir DIR`, `--worker-profile PROFILE_ID`, `--probe-external-tools`, and `--strict`. |
| Generated outputs | Text or JSON diagnostics on stdout. The run-directory probe creates and removes one temporary local file under `--runs-dir`. No audit run, cloned target repository, report, issue draft, or GitHub mutation is created. |
| Exit status behavior | `0` by default, including warning/error diagnostics for missing optional local tools; with `--strict`, exits `1` when required readiness checks report errors. Usage errors exit with argparse status `2`. |
| Security / disclosure cautions | The default command does not execute the configured worker, run audits, clone audited repositories, create reports or issues, execute `git`/`gh`, mutate GitHub state, or print credential values. By default it only resolves `git`/`gh` paths. `--probe-external-tools` executes trusted `git --version`, `gh --version`, and `gh auth status --hostname github.com`; use it only after confirming `PATH` points to expected local binaries. Probe output is reduced/redacted, credential-like environment variables are not passed to probe subprocesses, and `gh auth status` stdout/stderr is discarded. Paths are redacted for the user's home directory and secret-like path segments. |
| Related docs | [`docs/LOCAL_INSTALL_AND_AUDIT.md`](LOCAL_INSTALL_AND_AUDIT.md), [`docs/AGENT_WORKERS.md`](AGENT_WORKERS.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-doctor
gra-doctor --json --runs-dir "$HOME/.local/state/genai-repo-auditor/runs"
gra-doctor --probe-external-tools --json
gra-doctor --worker-profile codex-cli --strict
```

## `gra-sandbox-check`

| Field | Details |
|---|---|
| Purpose | Evaluate sandbox profile readiness before future workflows execute target repository code, candidate patches, proof helpers, or remediation validation commands. |
| Workflow category | Sandbox readiness. |
| Required inputs | `--run RUN_DIR --profile PROFILE`, where `PROFILE` is one of `source-only`, `local-test`, `container`, `gvisor`, or `vm`. |
| Key options | `--network-policy disabled\|explicit-allow`, `--executable-workflow`, `--json`, `--out-json PATH`, and `--out-md PATH`. |
| Generated outputs | `reports/sandbox-readiness.json` and `reports/SANDBOX_READINESS.md` by default. The reports include bounded readiness metadata and never secret values. |
| Exit status behavior | `0` when the selected profile is ready or warning-only; `1` when required readiness checks block executable validation; `2` for invalid profile, missing run/context problems, unsafe report paths, or usage errors. |
| Security / disclosure cautions | This command does not execute target code, run Docker/Podman, contact external services, or read secret values. It records only common credential path names and environment variable names when they appear visible. Missing Docker/Podman does not block `source-only` workflows, but `container`/`gvisor` profiles fail closed when required runtimes are unavailable. |
| Related docs | [`docs/SANDBOX_PROFILES.md`](SANDBOX_PROFILES.md), [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile source-only
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile local-test --json
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile container
```

Profiles other than `source-only` are executable profiles and fail closed by
default when required readiness checks are unavailable. Use
`--executable-workflow` only when a higher-level command needs to explicitly
assert that target-code execution is being requested.

## `gra-audit`

| Field | Details |
|---|---|
| Purpose | Clone an authorized GitHub repository, create an isolated audit run, render prompts, and either run a full non-interactive audit or prepare a supervised workflow. |
| Workflow category | Prepare / exec / validation entry point. |
| Required inputs | `--repo OWNER/REPO`. The host must have `git`, `gh`, `codex`, and `python3` available. |
| Key options | `--branch REF`, `--mode exec\|goal\|prepare`, `--model MODEL`, `--effort EFFORT`, `--depth N`, `--run-id ID`, `--runs-dir DIR`, `--codex-json`, `--network`, `--no-lock`, `--allow-invalid-report`. |
| Generated outputs | `context.json`, `run-manifest.json`, cloned `repo/`, `reports/`, rendered `prompt.exec.md` / `prompt.goal.md`, `prompts/`, copied schemas and taxonomy templates, Codex event/output files, `taxonomy-preflight.txt`, `report-validation.txt`, `run-summary.txt`, and a structured command event appended to `<reports_dir>/command-events.jsonl`. The run manifest classifies artifacts as `latest`, `supporting`, or `archive` and records SHA-256 digests for file artifacts. |
| Exit status behavior | `0` for successful prepare/goal setup or successful exec with valid report; `2` for usage errors; `1` for missing required local commands or missing/invalid reports when Codex itself succeeds; `12` for lock contention; in exec mode Codex, taxonomy preflight, or validation status can be propagated. |
| Security / disclosure cautions | Use only on repositories you are authorized to audit. Keep generated reports local. `run-manifest.json` is bounded, run-relative metadata for support diagnostics; it must not be treated as a substitute for reviewing findings or issue drafts, and `archive` retention does not make transcripts or scanner leads safe to publish. Use `--network` and `--allow-invalid-report` only with explicit operational justification. Do not disable locks for concurrent same-repository audits unless you can isolate output paths safely. |
| Related docs | [`docs/LOCAL_INSTALL_AND_AUDIT.md`](LOCAL_INSTALL_AND_AUDIT.md), [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md), [`docs/GOAL_DEEP_DIVE_WORKFLOW.md`](GOAL_DEEP_DIVE_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-audit --repo OWNER/REPO --mode exec --model gpt-5.5 --effort xhigh
```

Prepare without running Codex:

```bash
gra-audit --repo OWNER/REPO --mode prepare --runs-dir runs
```

## `gra-batch`

| Field | Details |
|---|---|
| Purpose | Run `gra-audit` against multiple repositories from a text file and aggregate per-repository results. |
| Workflow category | Batch operation. |
| Required inputs | `--repo-list FILE`, where non-empty non-comment lines contain `OWNER/REPO` values. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--depth N`, `--concurrency N`, `--runs-dir DIR`, `--batch-id ID`, `--codex-json`, `--network`, `--allow-failures`, `--fail-fast`. |
| Generated outputs | `runs/_batches/BATCH_ID/batch.json`, normalized repo list, per-repository logs under `logs/`, `batch-results.json`, and `failed-count.txt`. Each repository audit also writes its normal run artifacts. |
| Exit status behavior | `0` when all attempted audits succeed, or when failures are allowed with `--allow-failures`; `1` when one or more audits fail by default; `2` for usage errors such as missing repo list, invalid concurrency, or `--fail-fast` with concurrency greater than 1. |
| Security / disclosure cautions | Start with `--concurrency 1`. Keep Issue creation outside the batch run and perform it sequentially after human review. Avoid `--network` unless approved for every target in the batch. |
| Related docs | [`docs/MULTI_REPO.md`](MULTI_REPO.md), [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md). |

Example:

```bash
gra-batch --repo-list examples/repos.txt.example --concurrency 1 --mode exec
```

## `gra-targets`

| Field | Details |
|---|---|
| Purpose | Generate and manage the target queue for staged audits, including optional bounded-research quality fields such as attack class, attacker model, invariants, `max_files`, expected output, and chain relevance. |
| Workflow category | Target workflow. |
| Required inputs | `--run RUN_DIR` and exactly one action: `--generate`, `--list`, `--show TGT-ID`, or `--mark TGT-ID STATUS`. |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. `--mark` accepts `queued`, `in_progress`, `reviewed`, `skipped`, or `needs_human_review`. |
| Generated outputs | All actions append a structured command event to `<reports_dir>/command-events.jsonl`. For `--generate`: `prompts/exec/generate-targets.prompt.md`, `codex-targets-events.jsonl`, `codex-targets-stderr.txt`, `codex-targets-final.md`, `taxonomy-preflight-targets.txt`, optional `reports/taxonomy-normalizations.jsonl`, and the expected `reports/targets.json`. Targets can include optional `coverage` metadata for review depth, reviewed/skipped files, commands, unresolved questions, and gapfill recommendation. If `reports/agent-surface.json` exists, high-risk AI agent / MCP surfaces are appended as `TGT-AGENT-NNN` targets. If `reports/provenance-posture.json` exists, release provenance posture recommendations are appended as `TGT-PROVENANCE-NNN` targets. If `reports/supply-chain-posture.json` exists, low-scoring OpenSSF Scorecard posture checks with `target_recommended: true` are appended as `TGT-SCORECARD-NNN` targets. If `reports/dependencies.json` exists, high-signal dependency vulnerability records with dependency paths are appended as `TGT-DEPENDENCY-NNN` targets. For `--mark`: updated target status in `reports/targets.json`. `--list` and `--show` also write to stdout. |
| Exit status behavior | `0` for successful list/show/mark/generate; `1` when Codex completes but `reports/targets.json` is missing after generation; `2` for missing context, unknown target, or invalid target status. Codex execution status is returned for generation failures; taxonomy preflight status is returned when deterministic normalization cannot resolve taxonomy errors. |
| Security / disclosure cautions | Target queues are local planning artifacts. Review generated scope before using it to drive deeper research. Avoid network access unless the audit plan explicitly requires it. |
| Related docs | [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/AGENT_SURFACE_DISCOVERY.md`](AGENT_SURFACE_DISCOVERY.md), [`docs/PROVENANCE_POSTURE.md`](PROVENANCE_POSTURE.md), [`docs/SCORECARD_INGESTION.md`](SCORECARD_INGESTION.md), [`docs/DEPENDENCY_INGESTION.md`](DEPENDENCY_INGESTION.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Examples:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate
gra-targets --run runs/OWNER__REPO/RUN_ID --list
gra-targets --run runs/OWNER__REPO/RUN_ID --mark TGT-001 reviewed
```

## `gra-run-state`

| Field | Details |
|---|---|
| Purpose | Record and inspect run-level operational state so an intentional pause is distinct from a true blocked/impasse state. |
| Workflow category | Run state / pause guard. |
| Required inputs | `--run RUN_DIR` and exactly one action: `--status`, `--pause`, `--resume`, `--clear-pause`, or `--block`. |
| Key options | `--reason TEXT` for `--pause` / `--block`, `--resume-target TGT-ID`, `--resume-condition TEXT`, `--paused-by NAME`, `--blocked-by NAME`, `--resumed-by NAME`, `--final-reconcile TEXT`, and `--json`. |
| Generated outputs | `reports/run-state.json` for write actions. `--status` and `--resume` are read-only and print the current status, pause reason, resume target, resume condition, operator metadata, previous final reconcile summary when present, and the next gapfill targets from `reports/gapfill-targets.json` when available. |
| Exit status behavior | `0` for successful status/pause/resume/clear/block actions; `2` for missing context, malformed state, or missing required reason; `3` when `--clear-pause` is requested for a run that is not paused. |
| Security / disclosure cautions | A paused run is an operational stop, not a finding or vulnerability state. While `reports/run-state.json` has `status: "paused"`, deep-review commands such as `gra-research`, `gra-gapfill --generate`, `gra-gapfill --target`, and `gra-targets --generate/--mark` refuse to start. Use `--status` or `--resume` for read-only checks, then clear the pause only after the resume condition is satisfied. |
| Related docs | [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md). |

Examples:

```bash
gra-run-state --run runs/OWNER__REPO/RUN_ID --pause \
  --reason "maintenance window" \
  --resume-target TGT-AGENT-234 \
  --resume-condition "auditor update merged and post-merge CI passed" \
  --final-reconcile "published known findings: 52; unpublished Medium+: 0"
gra-run-state --run runs/OWNER__REPO/RUN_ID --status
gra-run-state --run runs/OWNER__REPO/RUN_ID --resume
gra-run-state --run runs/OWNER__REPO/RUN_ID --clear-pause --resumed-by maintainer
```


## `gra-worktree-check`

| Field | Details |
|---|---|
| Purpose | Classify Git worktree changes for auditor maintenance, audit artifact update, or target-remediation separation before commit or handoff. |
| Workflow category | Operations / worktree hygiene. |
| Required inputs | `--purpose TEXT`. `--repo PATH` defaults to the current directory. |
| Key options | Repeat `--allowed-prefix PREFIX` for paths that are intentionally in scope; rename/copy records are in scope only when both current and original paths stay within allowed prefixes; `--out-md OUT` writes a Markdown final-check report; `--json` prints machine-readable output. |
| Generated outputs | Console Markdown or JSON, plus optional Markdown report containing active worktree purpose, branch/head, allowed prefixes, in-scope changes, unrelated changes, and a task-ledger snippet. |
| Exit status behavior | `0` when all changes are in scope; `1` when unrelated changes are present; `2` when the repository cannot be inspected. |
| Security / disclosure cautions | This command only classifies local Git status. It does not make generated audit artifacts safe to commit. Keep `runs/`, `batches/`, scanner raw output, target repository source, credentials, and secrets out of auditor maintenance PRs unless explicitly curated and redacted. |
| Related docs | [`docs/WORKTREE_SEPARATION.md`](WORKTREE_SEPARATION.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md). |

```bash
gra-worktree-check --repo worktrees/genai-repo-auditor/issue-121-worktree-separation \
  --purpose auditor-maintenance \
  --allowed-prefix bin \
  --allowed-prefix lib \
  --allowed-prefix docs \
  --allowed-prefix tests \
  --out-md .codex-local/tmp/worktree-final-check.md
```

## `gra-recon`

| Field | Details |
|---|---|
| Purpose | Run the reconnaissance phase for a prepared audit run by first detecting AI agent / MCP surfaces and release provenance posture locally, then rendering and executing the recon prompt. |
| Workflow category | Research / recon workflow. |
| Required inputs | `--run RUN_DIR` with an existing `context.json`. |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | When AI agent or MCP surfaces are found: `reports/agent-surface.json` and `reports/AGENT_SURFACE.md`. Always writes release provenance posture artifacts `reports/provenance-posture.json` and `reports/PROVENANCE_POSTURE.md`, renders `prompts/exec/recon.prompt.md`, writes Codex event/output files such as `codex-recon-events.jsonl`, `codex-recon-stderr.txt`, and `codex-recon-final.md`, and appends a structured command event to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | Returns the Codex execution status; `0` indicates Codex completed successfully. `argparse` returns `2` for usage errors. |
| Security / disclosure cautions | Recon is still a defensive local code review phase. Do not expand scope beyond the cloned repository and approved inputs. |
| Related docs | [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/AGENT_SURFACE_DISCOVERY.md`](AGENT_SURFACE_DISCOVERY.md), [`docs/PROVENANCE_POSTURE.md`](PROVENANCE_POSTURE.md), [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-recon --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

## `gra-research`

| Field | Details |
|---|---|
| Purpose | Research one target from `reports/targets.json` in exec mode or prepare a supervised `/goal` deep dive for that target. |
| Workflow category | Research workflow. |
| Required inputs | `--run RUN_DIR --target TGT-ID`. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Target seed JSON under `reports/target-research/`, rendered target prompt, Codex event/output files, `taxonomy-preflight-TGT-ID.txt`, a structured command event appended to `<reports_dir>/command-events.jsonl`, optional `reports/taxonomy-normalizations.jsonl`, optional `reports/coverage-normalizations.jsonl` / `reports/AUDIT_LOG.md` entries for `coverage.review_depth` aliases, expected target research report under `reports/target-research/TGT-ID.md`, and possible updates to `reports/findings.json`. Exec mode marks the target `in_progress` before execution and `reviewed` or `needs_human_review` after execution. |
| Exit status behavior | `0` for successful goal preparation or successful Codex exec plus taxonomy preflight; `2` when the requested target is not found; exec mode returns Codex execution status or taxonomy preflight status when normalization cannot resolve taxonomy errors. |
| Security / disclosure cautions | Treat target research as analysis, not exploitation. Keep evidence minimal and avoid reconstructing secret values in outputs. |
| Related docs | [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md), [`docs/GOAL_DEEP_DIVE_WORKFLOW.md`](GOAL_DEEP_DIVE_WORKFLOW.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md). |

Examples:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode exec
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal
```

## `gra-gapfill`

| Field | Details |
|---|---|
| Purpose | Summarize target coverage and requeue high-risk targets whose `coverage` metadata shows shallow, incomplete, or explicitly recommended follow-up review. |
| Workflow category | Target coverage workflow. |
| Required inputs | `--run RUN_DIR` and exactly one action: `--list`, `--generate`, or `--target TGT-ID`. |
| Key options | `--mode exec\|goal` for `--target`, `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | `--list` prints candidates. All actions append a structured command event to `<reports_dir>/command-events.jsonl`. `--generate` writes `reports/COVERAGE.md`, `reports/gapfill-targets.json`, one plan per source target under `reports/target-research/TGT-XXX-gapfill.md`, appends deterministic `TGT-GAPFILL-NNN` targets to `reports/targets.json` without duplicating existing source-target requeues, separates `current_run` from `cumulative` gapfill counts, records source-target reason / generated-target status / relationship fields, emits prioritized `next_targets`, and may write `reports/coverage-normalizations.jsonl` / `reports/AUDIT_LOG.md` entries when review-depth aliases are normalized. `--target` renders `prompts/exec/gapfill-<TGT-ID>.prompt.md` or `prompts/goal/gapfill-<TGT-ID>.goal.md`, writes a seed JSON under `reports/target-research/`, and in exec mode writes Codex event/output files. |
| Exit status behavior | `0` for successful list/generate/goal setup or successful exec; `2` for missing context or unknown target; exec mode returns Codex execution status. |
| Security / disclosure cautions | Gapfill is bounded local review. It must not broaden into a full audit, modify the target repository, install dependencies, contact live services, or generate exploit instructions. |
| Related docs | [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --list
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-004 --mode exec
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-004 --mode goal
```

## `gra-variant`

| Field | Details |
|---|---|
| Purpose | Run variant analysis from an existing finding or a supplied root-cause note. |
| Workflow category | Variant workflow. |
| Required inputs | `--run RUN_DIR` and exactly one source: `--finding FINDING_ID` or `--source-file FILE`. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Finding/source seed material under `reports/variant-analysis/`, rendered variant prompt, Codex event/output files, the expected variant analysis report under `reports/variant-analysis/`, and a structured command event appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` for successful goal preparation or successful Codex exec; `2` when the requested finding or source file is missing; exec mode returns Codex execution status. |
| Security / disclosure cautions | Variant analysis should look for related defensive findings only. Do not generate exploit instructions or disclose full secret values. |
| Related docs | [`docs/VARIANT_ANALYSIS.md`](VARIANT_ANALYSIS.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode exec
gra-variant --run runs/OWNER__REPO/RUN_ID --source-file notes/root-cause.md --mode goal
```

## `gra-adversarial-validate`

| Field | Details |
|---|---|
| Purpose | Run an independent validation pass that attempts to disprove, downgrade, confirm, or mark existing findings or chains as `needs-human-review` without creating new findings. |
| Workflow category | Adversarial validation workflow. |
| Required inputs | `--run RUN_DIR` and exactly one selector: `--finding SEC-ID`, `--all-critical-high`, or `--chain CHAIN-ID`. Finding selectors require `reports/findings.json`; chain selectors require `reports/chains.json`. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--votes N`, `--policy human-review-on-split\|precision-biased\|recall-biased`, `--network`. `--votes 1` preserves the single-pass behavior. `--all-critical-high` selects Critical / High findings whose status is `Confirmed`, `Probable`, or `Potential`. |
| Generated outputs | Subject seed JSON under `reports/adversarial-validation/`, rendered adversarial validation prompt, Codex event/output files in exec mode, expected validation outputs `reports/validation.json` and `reports/VALIDATION.md`, and a structured command event appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` for successful goal preparation, successful Codex exec, or no matching `--all-critical-high` subjects; `2` when a requested finding or chain is missing; exec mode returns Codex execution status. |
| Security / disclosure cautions | This stage must not create new findings, broaden into a full audit, modify the target repository, or run live exploitation. Use it to challenge attacker control, reachability, trust-boundary crossing, mitigations, framework guarantees, middleware ordering, configuration assumptions, test-fixture versus production behavior, and overstated impact before issue publication. |
| Related docs | [`docs/ADVERSARIAL_VALIDATION.md`](ADVERSARIAL_VALIDATION.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md). |

Examples:

```bash
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --chain CHAIN-001 --mode goal
```

## `gra-chains`

| Field | Details |
|---|---|
| Purpose | Synthesize defensive attack or reachability chains from existing findings, targets, scanner refs, and validation notes without generating exploit payloads or weaponized steps. |
| Workflow category | Chain synthesis workflow. |
| Required inputs | `--run RUN_DIR`. The command uses existing local artifacts such as `reports/findings.json`, optional `reports/targets.json`, optional scanner index, and optional validation output. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Rendered chain synthesis prompt, Codex event/output files in exec mode, expected chain artifacts `reports/chains.json` and `reports/ATTACK_CHAINS.md`, and a structured command event appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` for successful goal preparation or successful Codex exec; exec mode returns Codex execution status. |
| Security / disclosure cautions | Defensive reasoning only. The prompt forbids working exploits, exploit payloads, weaponized steps, live exploitation instructions, production/staging probing, credential access, target repository modifications, and new finding creation. `ATTACK_CHAINS.md` is non-public by default. |
| Related docs | [`docs/ATTACK_CHAINS.md`](ATTACK_CHAINS.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md). |

Examples:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-chains --run runs/OWNER__REPO/RUN_ID --mode goal
```

## `gra-proofs`

| Field | Details |
|---|---|
| Purpose | Generate safe local proof artifacts for existing findings using benign validation methods such as static traces, unit-test plans, local regression plans, parser-only inputs, config checks, or mocked local behavior. |
| Workflow category | Safe local proof workflow. |
| Required inputs | `--run RUN_DIR` and exactly one selector: `--finding SEC-ID` or `--all-critical-high`. Selectors require `reports/findings.json`. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. `--all-critical-high` selects Critical / High findings whose status is `Confirmed`, `Probable`, or `Potential`. |
| Generated outputs | Subject seed JSON under `reports/proofs/`, rendered proof prompt, Codex event/output files in exec mode, expected proof artifacts `reports/proofs.json`, `reports/PROOFS.md`, safe supporting files under `reports/proofs/`, and a structured command event appended to `<reports_dir>/command-events.jsonl`. `reports/proofs.json` records executed proof commands as structured `argv` plus safety metadata rather than shell strings. |
| Exit status behavior | `0` for successful goal preparation, successful Codex exec, or no matching `--all-critical-high` subjects; `2` when a requested finding or `findings.json` is missing; exec mode returns Codex execution status. |
| Security / disclosure cautions | Local/private by default. The prompt forbids working exploit scripts, exploit code, weaponized payloads, credential extraction, auth-bypass execution against live services, network scanning, production/staging probing, dependency installation, target repository modification, and new finding creation. Do not publish proof artifacts wholesale. |
| Related docs | [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

## `gra-remediate`

| Field | Details |
|---|---|
| Purpose | Generate local/private, draft-only remediation candidate artifacts for existing findings without applying patches or publishing changes; optionally validate existing draft patches in a disposable workspace. |
| Workflow category | Remediation candidate workflow. |
| Required inputs | `--run RUN_DIR` and exactly one selector: `--finding SEC-ID` or `--all-critical-high`. Selectors require `reports/findings.json`. |
| Key options | `--mode exec\|goal`, `--model MODEL`, and `--effort EFFORT` for candidate generation. Use `--validate`, `--sandbox-profile local-test`, `--build-command CMD`, `--test-command CMD`, `--command-timeout SECONDS`, and `--max-changed-paths N` for patch validation. Local-test validation runs only Python commands by default, checks sandbox readiness, and injects a Python no-network / denied-executable guard in the disposable workspace. Network access is intentionally not exposed for this command. `--all-critical-high` selects Critical / High findings whose status is `Confirmed`, `Probable`, or `Potential`. |
| Generated outputs | Subject seed JSON under `reports/remediation/`, rendered remediation prompt, Codex event/output files in exec mode, `reports/remediation/remediation-candidates.json`, `reports/remediation/REMEDIATION_CANDIDATES.md`, draft patch/notes files under `reports/remediation/<FINDING-ID>/`, validation reports `reports/remediation/<FINDING-ID>/patch-validation.json` / `.md` when `--validate` is used, and a structured command event appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` for successful goal preparation, successful Codex exec, no matching `--all-critical-high` subjects, or patch validation without failed candidates; `1` when patch validation records a failed candidate; `2` when required inputs are missing or validation cannot be prepared safely; exec mode returns Codex execution status. |
| Security / disclosure cautions | Draft-only and local/private by default. Generation mode must not apply patches, modify the target checkout, push branches, create pull requests, create GitHub Issues, install dependencies, access the network, execute target code, or include exploit payloads. Validation mode applies patches only to a disposable copy under the run directory, never to the original `repo/`, rejects unsafe install/publish/network command patterns and non-Python host commands by default, records command events with `best-effort-host-python-guard` and `network_allowed=null` rather than claiming the selected readiness profile is the execution sandbox or OS-level network enforcement, and marks all-command-skipped runs as `needs-human-review`. Public Issue plans may mention candidate and validation status but must not embed full diffs. |
| Related docs | [`docs/REMEDIATION_CANDIDATES.md`](REMEDIATION_CANDIDATES.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SANDBOX_PROFILES.md`](SANDBOX_PROFILES.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode exec
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --validate --sandbox-profile local-test --build-command "python3 -m py_compile repo/app.py" --test-command "python3 -m py_compile repo/app.py"
```

## `gra-trace`

| Field | Details |
|---|---|
| Purpose | Trace whether an existing producer finding, such as a shared-library flaw, is reachable from attacker-controlled entry points in a consumer repository. This feature is experimental/P3. |
| Workflow category | Cross-repo trace reachability workflow. |
| Required inputs | `--producer-run PRODUCER_RUN_DIR --finding SEC-ID` and either `--consumer-run CONSUMER_RUN_DIR` under the producer run for `exec` / `goal` mode or `--consumer-repo OWNER/REPO` for `prepare` mode. |
| Key options | `--mode prepare\|exec\|goal`, `--branch REF`, `--depth N` for prepare-mode clone, `--model MODEL`, `--effort EFFORT`. `--network` is intentionally unavailable; Codex network access is always disabled for trace execution. |
| Generated outputs | Subject seed JSON under the producer run's `reports/traces/`, rendered trace prompt, Codex event/output files in exec mode, expected trace artifacts `reports/traces.json` and `reports/TRACE.md` under the producer run, and a structured command event appended to the producer run's `<reports_dir>/command-events.jsonl`. `prepare` mode also creates `trace-consumers/OWNER__repo/` under the producer run and renders a supervised goal prompt. |
| Exit status behavior | `0` for successful prepare/goal setup or successful Codex exec; `2` for missing producer context, missing finding, invalid mode/source combination, missing consumer context, path traversal/symlink safety failures, or clone/setup failures; exec mode returns Codex execution status. |
| Security / disclosure cautions | Trace results are reachability evidence, not exploit proof. The prompt forbids external scanning, production/staging probing, exploit payloads, credential access, dependency installation, and producer/consumer repository modification. Only prepare mode performs an explicit GitHub clone, validates the producer finding before cloning, and records `network_allowed=true` in its command event to reflect clone capability. Trace subjects, prompts, Codex event files, `traces.json`, and `TRACE.md` must remain under the producer run directory; unsafe `context.json` paths, external consumer runs, and symlinked runs are rejected. Keep `TRACE.md` and `traces.json` local/private until human review. |
| Related docs | [`docs/TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md), [`docs/MULTI_REPO.md`](MULTI_REPO.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-repo ORG/consumer-api --mode prepare
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/ORG__shared-lib/RUN_ID/trace-consumers/ORG__consumer-api --mode exec
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/ORG__shared-lib/RUN_ID/trace-consumers/ORG__consumer-api --mode goal
```

## `gra-scan`

| Field | Details |
|---|---|
| Purpose | List versioned local scanner adapters, produce an exact sanitized plan, and explicitly run approved offline Gitleaks/Syft adapters in a bounded container sandbox. |
| Workflow category | Scanner planning and local execution workflow. |
| Required inputs | `--run RUN_DIR`; plan/execute also require `--tool gitleaks\|syft`. |
| Key options | `--list` lists adapters. `--plan` is optional because planning is the default. `--execute` is required to run a scanner. `--sandbox-profile container\|gvisor` selects an enforced execution boundary; `vm` remains plan-only. `--network-policy disabled` is mandatory for execution. `--json` prints the machine-readable result. |
| Generated outputs | List/plan write standard output only. Successful execute writes one bounded local raw JSON file under `<reports_dir>/scanner-results/raw/`, a redacted normalized artifact under `<reports_dir>/scanner-results/normalized/`, updates the scanner index and applicable dependency posture artifacts, and writes bounded `<reports_dir>/scanner-runs.json` / `SCANNER_RUNS.md`. Execute attempts that pass run/tool/report preflight append a sanitized `gra-scan` command event. Failed/staging scanner output is removed. |
| Exit status behavior | `0` for a valid list/plan or successful bounded execution; `1` for scanner exit, timeout, output/result limit, or unsafe generated output; parser/preflight `2` for missing tools/images, invalid combinations, unsafe paths, unsupported profiles, or network allowance. |
| Security / disclosure cautions | List/plan remain non-executing. Execute uses a digest-pinned pre-pulled image, local Docker/Podman, `--pull=never`, `--network=none`, a read-only target mount/root filesystem, dropped capabilities, resource limits, and a dedicated output mount. Remote runtime environment variables and credential-like environment values are not passed. Raw output stays local; normalized leads and scanner-run summaries remain review-only and never auto-create findings. DAST, endpoint probing, external-host scanning, brute force, credentials, and production/staging access remain prohibited. |
| Related docs | [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/SANDBOX_PROFILES.md`](SANDBOX_PROFILES.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Examples:

```bash
gra-scan --run runs/OWNER__REPO/RUN_ID --list
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks
gra-scan --run runs/OWNER__REPO/RUN_ID --tool syft --plan --sandbox-profile container --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --execute --sandbox-profile container --json
```

## `gra-ingest`

| Field | Details |
|---|---|
| Purpose | Copy scanner output into a run, normalize leads, redact sensitive values, update the scanner index, and produce deterministic posture artifacts for OpenSSF Scorecard JSON, SBOM/dependency graph JSON, and supported dependency vulnerability JSON. |
| Workflow category | Scanner workflow. |
| Required inputs | `--run RUN_DIR --tool TOOL --file FILE`. |
| Key options | `--format FORMAT` (`auto` by default), `--note NOTE`. Use `--tool scorecard` for OpenSSF Scorecard JSON posture ingestion, or `--tool sbom` / `syft` / dependency formats with `--format cyclonedx`, `spdx`, `syft`, or `auto` for SBOM/dependency graph ingestion. Trivy SBOM exports are ingested when the format is CycloneDX or SPDX. Trivy and Grype vulnerability JSON are ingested with `--tool trivy --format json` or `--tool grype --format json`. |
| Generated outputs | Raw scanner result copy under `<reports_dir>/scanner-results/`, normalized lead JSON under `<reports_dir>/scanner-results/normalized/`, `<reports_dir>/scanner-results/scanner-index.json`, and a sanitized `ingest` command event in `<reports_dir>/command-events.jsonl`. With `--tool scorecard` / `openssf-scorecard` / `ossf-scorecard`, also writes `<reports_dir>/supply-chain-posture.json`, `<reports_dir>/supply-chain-posture.md`, and may append deterministic `TGT-SCORECARD-NNN` targets to `<reports_dir>/targets.json`. With `--tool sbom` or dependency formats, also writes `<reports_dir>/dependencies.json`, `<reports_dir>/DEPENDENCY_RISK.md`, and may append deterministic `TGT-DEPENDENCY-NNN` targets to `<reports_dir>/targets.json`. |
| Exit status behavior | `0` for successful ingest; `2` when the source file is missing. JSON/context or filesystem failures surface as non-zero Python errors. |
| Security / disclosure cautions | Scanner output is untrusted input. The command writes redacted normalized leads and redacted posture summaries, but raw scanner copies can still contain sensitive data; keep them local and do not commit them. Scorecard and dependency posture do not automatically create findings. SBOMs can reveal internal package choices and versions. |
| Related docs | [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/SCORECARD_INGESTION.md`](SCORECARD_INGESTION.md), [`docs/DEPENDENCY_INGESTION.md`](DEPENDENCY_INGESTION.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Example:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file scanner-output.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool syft --file syft.json --format syft
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool grype --file grype.json --format json
```

## `gra-import-findings`

| Field | Details |
|---|---|
| Purpose | Normalize a conservative vendor-neutral external finding JSON contract from managed AI tools, deterministic scanners, or internal review systems into local review artifacts. |
| Workflow category | External finding import. |
| Required inputs | `--run RUN_DIR --file FILE`. The file must contain a JSON object with `source` and a `findings` array. |
| Key options | `--append-findings` explicitly appends valid normalized records to `reports/findings.json`; default mode is review-only and does not mutate findings. |
| Generated outputs | `<reports_dir>/imported-findings.json`, `<reports_dir>/IMPORTED_FINDINGS.md`, and a sanitized `import` command event in `<reports_dir>/command-events.jsonl`. With `--append-findings`, valid non-duplicate records are also appended to `<reports_dir>/findings.json` with `external_source` metadata and `issue_recommended=false`. |
| Exit status behavior | `0` for successful parsing and artifact generation, even when some per-record leads are rejected and retained with reasons; `2` for missing files, malformed top-level JSON, unsupported `source`, unsafe `reports_dir`, or invalid append preconditions. |
| Security / disclosure cautions | The command does not call vendor APIs and does not support proprietary exports without fixtures/tests. Evidence and remediation strings are bounded and redacted. Source file absolute paths are not stored. Appended findings remain review-gated and do not bypass `gra-issues` publication rules. |
| Related docs | [`docs/EXTERNAL_FINDING_IMPORT.md`](EXTERNAL_FINDING_IMPORT.md), [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json --append-findings
```

## `gra-scanner-triage`

| Field | Details |
|---|---|
| Purpose | Ask Codex to triage imported scanner leads in repository context. |
| Workflow category | Scanner workflow. |
| Required inputs | `--run RUN_DIR` with `<reports_dir>/scanner-results/scanner-index.json` already present (`reports/` by default, or the run's configured `reports_dir`). |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Rendered `prompts/exec/scanner-triage.prompt.md`, Codex event/output files, triage output expected under the run's reports, and a sanitized `scanner-triage` command event in `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when Codex succeeds; `2` when scanner index is missing; otherwise returns Codex execution status. |
| Security / disclosure cautions | Treat scanner results as leads, not confirmed findings. Triage should read normalized redacted leads by default and should not quote or reconstruct full secrets. |
| Related docs | [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

## `gra-no-findings`

| Field | Details |
|---|---|
| Purpose | Write an explicit schema-valid empty `reports/findings.json` for a reviewed no-confirmed-finding or reconnaissance-only run. |
| Workflow category | Validation / reporting setup. |
| Required inputs | `--run RUN_DIR --rationale TEXT`. The run directory must contain `context.json`. |
| Key options | `--source-stage recon\|target-queue\|scanner-triage\|manual-review\|validation\|other`, optional `--reviewer TEXT`, and `--force` to overwrite an existing `findings.json` after review. |
| Generated outputs | `reports/findings.json` with an empty `findings` array plus a top-level `no_findings` record containing rationale, source stage, target metadata, and safety flags; `reports/NO_FINDINGS.md` as a local operator-readable decision record. |
| Exit status behavior | `0` when the empty findings record is written; `2` for missing context, empty rationale, unsafe context paths, existing `findings.json` without `--force`, or invalid options. |
| Security / disclosure cautions | This command does not claim the repository is vulnerability-free. It records only that the bounded run has no confirmed findings at the selected stage. It creates no issue bodies, no GitHub Issues, no scanner output, and no remediation content. Review the rationale before reusing counts in public material. |
| Related docs | [`docs/DOGFOOD_RUNBOOK.md`](DOGFOOD_RUNBOOK.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/METRICS.md`](METRICS.md), [`docs/BENCHMARKING.md`](BENCHMARKING.md). |

Examples:

```bash
gra-no-findings --run runs/OWNER__REPO/RUN_ID \
  --source-stage recon \
  --rationale "Reconnaissance completed and no candidate findings were advanced in this bounded pass."
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run --min-severity Low \
  --statuses Confirmed,Probable,Potential,Informational
```

## `gra-workflow-profile`

| Field | Details |
|---|---|
| Purpose | Record an explicit workflow scope profile so intentionally skipped advanced stages are distinct from missing outputs or command failures. |
| Workflow category | Validation / reporting setup. |
| Required inputs | `--run RUN_DIR --profile recon-only --rationale TEXT`. The run directory must contain `context.json`. |
| Key options | Optional `--reviewer TEXT`, and `--force` to overwrite an existing `workflow-profile.json` after review. |
| Generated outputs | `reports/workflow-profile.json` and `reports/WORKFLOW_PROFILE.md`. The recon-only profile marks reconnaissance and target generation as completed and advanced stages such as target research, scanner triage, adversarial validation, chain synthesis, safe proofs, trace reachability, remediation, dashboard generation, and Issue publication as `skipped_by_scope`. |
| Exit status behavior | `0` when the workflow profile is written; `2` for missing context, empty rationale, unsafe context paths, existing profile without `--force`, or invalid options. |
| Security / disclosure cautions | The profile records stage intent and aggregate status only. It does not create findings, issue bodies, GitHub Issues, scanner output, proofs, traces, remediation content, or dashboards. Treat `skipped_by_scope` as an operator scope decision, not proof that the skipped stage has no risk. |
| Related docs | [`docs/DOGFOOD_RUNBOOK.md`](DOGFOOD_RUNBOOK.md), [`docs/DOGFOOD_REPORTING.md`](DOGFOOD_REPORTING.md), [`docs/METRICS.md`](METRICS.md), [`docs/BENCHMARKING.md`](BENCHMARKING.md), [`docs/EVIDENCE_GRAPH.md`](EVIDENCE_GRAPH.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Examples:

```bash
gra-workflow-profile --run runs/OWNER__REPO/RUN_ID \
  --profile recon-only \
  --rationale "Reconnaissance completed and advanced validation stages are intentionally out of scope."
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
```

## `gra-taxonomy-preflight`

| Field | Details |
|---|---|
| Purpose | Check controlled taxonomy references in `reports/findings.json` and `reports/targets.json`, propose configured replacements, and optionally apply deterministic aliases and canonical labels before report validation. |
| Workflow category | Validation workflow. |
| Required inputs | One of `--run RUN_DIR` or `--findings PATH`. Use `--targets PATH` with `--findings` when target taxonomy references should also be checked. |
| Key options | `--fix` applies deterministic mappings and canonical label corrections; `--log PATH` overrides the default JSONL change log path. |
| Generated outputs | Console preflight result. With `--fix --run`, applied changes are appended to `reports/taxonomy-normalizations.jsonl` with timestamp, artifact path, field path, before/after reference, and reason. |
| Exit status behavior | `0` when no unresolved taxonomy errors remain; `1` for invalid JSON, unresolved taxonomy errors, or preflight-only mode when deterministic normalizations are available but `--fix` was not supplied; parser error status `2` for missing required source arguments. |
| Security / disclosure cautions | The command edits only local audit artifacts when `--fix` is supplied. Review the JSONL change log before publishing findings or issue drafts. |
| Related docs | [`docs/TAXONOMIES.md`](TAXONOMIES.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-taxonomy-preflight --findings reports/findings.json --targets reports/targets.json --fix --log reports/taxonomy-normalizations.jsonl
```

## `gra-validate-report`

| Field | Details |
|---|---|
| Purpose | Validate `findings.json`, optional `targets.json`, optional chain reports, optional proof artifacts, optional remediation and patch-validation artifacts, optional known-finding novelty ledger, optional cross-repo trace artifacts, optional adversarial validation output, optional evidence graph output, optional scanner index artifacts, optional dependency artifacts, optional issue ledger, optional duplicate decision records, optional run state, optional command event records, optional run manifest artifact retention and digest hygiene, controlled taxonomy names/IDs/labels, issue body references, schema-required fields, finding assessment enums, target-quality bounds, safety constraints, timestamps, fingerprints, affected locations, and obvious secret disclosure risks. |
| Workflow category | Validation workflow. |
| Required inputs | One of `--run RUN_DIR` or `--findings PATH`. |
| Key options | `--run RUN_DIR`, `--findings PATH`. |
| Generated outputs | Console validation result, including `Run manifest: validated` when `run-manifest.json` passes hygiene checks, and a structured command event appended to `<reports_dir>/command-events.jsonl`. When called by `gra-audit`, output is commonly captured in `run-summary.txt` and `report-validation.txt`. |
| Exit status behavior | `0` when validation passes; `1` for invalid JSON or validation errors; parser error status `2` when neither `--run` nor `--findings` is supplied. |
| Security / disclosure cautions | Validation reduces risk but is not a substitute for human review. Check findings and issue drafts before sharing outside the approved audience. |
| Related docs | [`docs/TAXONOMIES.md`](TAXONOMIES.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-validate-report --findings runs/OWNER__REPO/RUN_ID/reports/findings.json
```

## `gra-metrics`

| Field | Details |
|---|---|
| Purpose | Generate local advanced workflow metrics from one run without copying raw evidence or secrets. |
| Workflow category | Reporting workflow. |
| Required inputs | `--run RUN_DIR` (`<reports_dir>` defaults to `reports/` and follows `context.json` when customized). |
| Key options | `--out-json OUT` and `--out-md OUT` to override the default `<reports_dir>/metrics.json` and `<reports_dir>/METRICS.md`. |
| Generated outputs | `<reports_dir>/metrics.json` and `<reports_dir>/METRICS.md` with counts for findings, adversarial validation decisions, downgrade/invalidate rate, chains, proofs, gapfill current/cumulative queue state, traces, issue publication plan warnings, workflow-profile scoped skips, duplicate decisions, command-event status/duration/failure/retry/config/artifact/stage/producer-coverage aggregates, taxonomy normalizations, artifact counts, manifest retention buckets, manifest hygiene warning counts, and run duration when available. After those files are written, one v2 `metrics` completion event is appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when metrics are written. Parser status `2` covers usage errors; unsafe `reports_dir` or unreadable local artifacts also return `2`. Successful completion-event writes are blocking; if metrics generation is already failing, the follow-up event write is warning-only so the original non-zero exit is preserved. |
| Security / disclosure cautions | Metrics are generated from local report artifacts only and intentionally omit raw finding evidence, issue body text, proof evidence, trace evidence, scanner lead bodies, and secret values. External `--out-json` / `--out-md` destinations outside the run directory are intentionally omitted from event artifact refs. The current metrics artifact does not include its own `gra-metrics` completion event; that self-observation appears on the next `gra-metrics` execution; a later `gra-dashboard` run can then display the updated metrics. Keep metrics local unless aggregate repository risk information is approved for sharing. |
| Related docs | [`docs/METRICS.md`](METRICS.md), [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-metrics --run runs/OWNER__REPO/RUN_ID
```

## `gra-benchmark`

| Field | Details |
|---|---|
| Purpose | Generate local v0.4 dogfood benchmark quality gates for an existing run or a built-in fixture without copying raw evidence. |
| Workflow category | Reporting / quality-gate workflow. |
| Required inputs | Either `--run RUN_DIR` for an existing run or `--fixture minimal\|advanced` to copy a built-in local fixture into an ignored `runs/benchmark-fixtures/` directory. Existing-run mode resolves `<reports_dir>` from `context.json` when present. |
| Key options | `--out-run DIR` for fixture destination, `--max-chains N` to tune the chain-count bound, `--out-json OUT`, `--out-md OUT`, and `--skip-validation` for diagnostic runs that should not execute `gra-validate-report`. |
| Generated outputs | `<reports_dir>/benchmark.json` and `<reports_dir>/BENCHMARK.md` by default, with bounded metric summaries, workflow-profile scoped-skip counts, gate statuses, and follow-up actions. The benchmark consumes `<reports_dir>/metrics.json` when present and computes in-memory fallback counts when it is absent. After those files are written, one v2 `benchmark` completion event is appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when no quality gate fails, even if warning gates need human review; `1` when one or more gates fail; parser/status `2` for usage errors, missing runs, unsafe report paths, invalid fixtures, or unreadable local artifacts. Successful completion-event writes are blocking; if the benchmark is already returning `1` or `2`, any follow-up event-write failure is downgraded to a warning so the original exit code is preserved. |
| Security / disclosure cautions | The benchmark is local-only, does not call Codex, does not contact external networks, and never calls `gra-issues --apply`. It records counts, rates, and local artifact paths only; raw finding evidence, issue bodies, proof payloads, scanner lead bodies, and secret values are excluded. External `--out-json` / `--out-md` destinations outside the run directory are intentionally omitted from event artifact refs, and the current benchmark invocation's completion event becomes visible only after the next `gra-metrics` execution; a later `gra-dashboard` run can then display the updated metrics. |
| Related docs | [`docs/BENCHMARKING.md`](BENCHMARKING.md), [`docs/METRICS.md`](METRICS.md), [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-benchmark --fixture advanced
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID --max-chains 10
```

## `gra-evidence-graph`

| Field | Details |
|---|---|
| Purpose | Generate a local graph that links findings to supporting and challenging artifacts across targets, scanner leads, chains, safe proofs, adversarial validation, traces, remediation candidates, patch validation, Issue publication plans, workflow profiles, and metrics. |
| Workflow category | Reporting / evidence handoff workflow. |
| Required inputs | `--run RUN_DIR` with `<reports_dir>/findings.json` (`reports/` by default, or the run's configured `reports_dir`); all other artifacts are optional and missing optional artifacts are recorded in the graph summary instead of causing failure. |
| Key options | `--run RUN_DIR`. |
| Generated outputs | `<reports_dir>/evidence-graph.json` and `<reports_dir>/EVIDENCE_GRAPH.md` with bounded node/edge summaries, workflow-profile scoped-skip status, artifact references, high/Critical issue-recommended coverage counts, and missing optional artifact metadata. After those files are written, one v2 `evidence-graph` completion event is appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when the graph is written; parser status `2` for usage errors. Successful completion-event writes are blocking; if graph generation is already failing after preflight, any follow-up event-write failure is downgraded to a warning so the original non-zero exit is preserved. |
| Security / disclosure cautions | The graph is local-only and intentionally avoids raw finding evidence, root cause text, remediation text, proof payloads, issue bodies, and secret values. The current graph invocation's completion event becomes visible only after the next `gra-metrics` execution; a later `gra-dashboard` run can then display the updated metrics. Keep it local unless repository-risk metadata sharing is approved. |
| Related docs | [`docs/EVIDENCE_GRAPH.md`](EVIDENCE_GRAPH.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
```

## `gra-novelty`

| Field | Details |
|---|---|
| Purpose | Classify current findings against local known-finding records so recurring audits can distinguish new findings, duplicates, better examples, accepted risks, regressions, invalid known findings, and cases needing human review. |
| Workflow category | Reporting / local dedupe workflow. |
| Required inputs | `--run RUN_DIR` with `reports/findings.json`. |
| Key options | `--prior-ledger PATH` to compare against one or more previous `known-findings.json` files, `--accepted-risk FINDING_ID` to mark a current finding as locally accepted risk, and `--accepted-risk-reason TEXT` for a local-only reason. |
| Generated outputs | `reports/known-findings.json` and `reports/NOVELTY.md`. The JSON stores fingerprints, bounded hash summaries, novelty status, match reasons, and local issue recommendation state without copying raw evidence, root cause text, impact text, remediation text, regression-test text, or issue bodies. |
| Exit status behavior | `0` when the novelty ledger and Markdown summary are written; `2` when `findings.json` is missing or usage is invalid. |
| Security / disclosure cautions | The ledger is local-only and avoids raw evidence, but it still contains repository/finding metadata and accepted-risk reasons. Keep it local unless disclosure has been approved. Do not put secrets or private evidence in accepted-risk reasons. |
| Related docs | [`docs/NOVELTY_LEDGER.md`](NOVELTY_LEDGER.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Examples:

```bash
gra-novelty --run runs/OWNER__REPO/RUN_ID
gra-novelty --run runs/OWNER__REPO/NEW_RUN --prior-ledger runs/OWNER__REPO/OLD_RUN/reports/known-findings.json
gra-novelty --run runs/OWNER__REPO/RUN_ID --accepted-risk SEC-001 --accepted-risk-reason "accepted by local risk owner"
```

## `gra-dashboard`

| Field | Details |
|---|---|
| Purpose | Generate a local HTML dashboard summarizing a run's findings, structured finding assessment dimensions, target queue, gapfill current/cumulative queue state, remediation candidates, known-finding novelty status, dogfood benchmark gates, evidence graph, advanced workflow metrics, artifact retention, and observability when present, Scorecard supply-chain posture, dependency risk posture, and scanner result index. |
| Workflow category | Reporting workflow. |
| Required inputs | `--run RUN_DIR` (`<reports_dir>` defaults to `reports/` and follows `context.json` when customized). |
| Key options | `--out OUT` to override the default `<reports_dir>/dashboard.html`. |
| Generated outputs | HTML dashboard file with links to `metrics.json` / `METRICS.md`, `benchmark.json` / `BENCHMARK.md`, `evidence-graph.json` / `EVIDENCE_GRAPH.md`, `imported-findings.json` / `IMPORTED_FINDINGS.md`, and `known-findings.json` / `NOVELTY.md` when those artifacts exist, including current source-to-gapfill relationships, prioritized next gapfill targets, remediation candidate summary, imported finding counts, benchmark gate status, evidence graph node/edge counts, novelty status counts, latest/archive artifact retention counts, manifest hygiene warnings, slow command subjects, execution-configuration coverage, workflow stage-group counts, and high retry / rerun targets from observability metrics. After the HTML file is written, one v2 `dashboard` completion event is appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when the dashboard and completion event are written; parser status `2` for usage errors. A post-preflight input, output, or completion-event failure returns `2` and attempts a warning-only failed `dashboard` event so the original failure remains visible. An unsafe or unwritable event target fails during preflight before dashboard output is written. |
| Security / disclosure cautions | The dashboard can contain finding titles, locations, and evidence. External `--out` destinations outside the run directory are intentionally omitted from event artifact refs, and the current dashboard invocation's completion event becomes visible only after the next `gra-metrics` execution; a later `gra-dashboard` run can then display the updated metrics. Keep it local unless disclosure has been approved. |
| Related docs | [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

## `gra-sarif`

| Field | Details |
|---|---|
| Purpose | Convert `reports/findings.json` to SARIF 2.1.0 for local review or compatible tooling, including structured assessment properties when present. |
| Workflow category | Reporting workflow. |
| Required inputs | `--run RUN_DIR` with `<reports_dir>/findings.json` (`reports/` by default, or the run's configured `reports_dir`). |
| Key options | `--out OUT` to override the default `<reports_dir>/findings.sarif`. |
| Generated outputs | SARIF JSON file plus one v2 `sarif` completion event appended to `<reports_dir>/command-events.jsonl` after the SARIF file is written. |
| Exit status behavior | `0` when SARIF and its completion event are written; parser status `2` for usage errors. A post-preflight input, output, or completion-event failure returns `2` and attempts a warning-only failed `sarif` event. An unsafe or unwritable event target fails during preflight before SARIF is written. |
| Security / disclosure cautions | SARIF may include evidence, file paths, and finding metadata. External `--out` destinations outside the run directory are intentionally omitted from event artifact refs, and the current SARIF export is observed only after a later `gra-metrics` execution; a subsequent `gra-dashboard` run can then display the updated metrics. Do not upload it to third-party systems unless approved for the target repository. |
| Related docs | [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-sarif --run runs/OWNER__REPO/RUN_ID --out runs/OWNER__REPO/RUN_ID/reports/findings.sarif
```

## `gra-store`

| Field | Details |
|---|---|
| Purpose | Import run metadata, targets, findings, scanner results, created issue records, and optional posture artifacts into a local SQLite database. |
| Workflow category | Reporting / persistence workflow. |
| Required inputs | `--run RUN_DIR` (`<reports_dir>` defaults to `reports/` and follows `context.json` when customized). |
| Key options | `--db DB` to override the default `<lab>/runs/security-audit.sqlite`. |
| Generated outputs | SQLite database with `runs`, `targets`, `findings`, `scanner_results`, `issues`, and `posture_artifacts` tables. `posture_artifacts` records run manifests, agent-surface discovery, Scorecard posture, provenance posture, and dependency posture when those artifacts exist. After the import completes, one v2 `store` completion event is appended to `<reports_dir>/command-events.jsonl`. |
| Exit status behavior | `0` when import and its completion event complete; parser status `2` for usage errors. A post-preflight SQLite, filesystem, or completion-event failure returns `2` and attempts a warning-only failed `store` event. Full event metadata is validated before database mutation, and an unsafe, unwritable, or invalid event fails preflight before SQLite is opened. |
| Security / disclosure cautions | The SQLite store can aggregate sensitive audit data across repositories. External `--db` destinations outside the run directory are intentionally omitted from event artifact refs, and the current import is observed only after a later `gra-metrics` execution; a subsequent `gra-dashboard` run can then display the updated metrics. Keep it local, restrict access, and avoid committing it. |
| Related docs | [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-store --run runs/OWNER__REPO/RUN_ID --db runs/security-audit.sqlite
```

## `gra-index`

| Field | Details |
|---|---|
| Purpose | Build a lightweight index across audit runs by scanning for `reports/findings.json` and summarizing optional posture artifacts when present. |
| Workflow category | Reporting / index workflow. |
| Required inputs | Existing runs directory. Defaults to `runs`. |
| Key options | `--runs-dir RUNS_DIR`. |
| Generated outputs | `index.json` and `index.md` in the selected runs directory. Each run includes finding counts plus posture summary fields for artifact count, agent surfaces, Scorecard checks, provenance workflows, dependency components, and dependency vulnerabilities. |
| Exit status behavior | `0` when index files are written. The selected runs directory must exist and be writable. |
| Security / disclosure cautions | The generated index summarizes findings, posture counts, and run paths. Keep it local if repository names, run paths, finding counts, or dependency vulnerability counts are sensitive. |
| Related docs | [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md). |

Example:

```bash
gra-index --runs-dir runs
```

## `gra-issues`

| Field | Details |
|---|---|
| Purpose | Create GitHub Issues from reviewed findings, preview what would be created in dry-run mode, or bind approval to an immutable publication plan. |
| Workflow category | Issue workflow. |
| Required inputs | `--run RUN_DIR`. The target repository is read from `findings.json` or `context.json`, or overridden with `--repo OWNER/REPO`. The `gh` CLI must be authenticated for apply mode. |
| Key options | `--repo OWNER/REPO`, `--min-severity Critical\|High\|Medium\|Low\|Informational`, `--statuses LIST`, `--dry-run`, `--plan`, `--apply`, `--apply-plan PLAN`, `--replan`, `--verify-ledger`, `--require-advanced-validation`, `--allow-public`, `--create-labels`, `--assignee ASSIGNEE`, `--max-issues N`. |
| Generated outputs | Preview text in dry-run mode, `reports/issue-publication-plan.json` in plan mode, canonical `reports/issue-ledger.json` for all modes that evaluate findings, `reports/duplicate-decisions/*.json` before dry-run/apply publication decisions, GitHub Issues in apply mode, `issues-created.json` under the run directory, and one sanitized command event in `<reports_dir>/command-events.jsonl`. Event phases distinguish `preview`, `plan`, `verify-plan`, `verify-ledger`, `apply-plan`, and direct `execute` modes. `issues-created.json` records `plan_written`, `plan_verified`, `publication_plan_status`, and `plan_sha256` when `--apply-plan` is used. |
| Exit status behavior | `0` for successful dry-run, plan creation, ledger verification, or issue creation; `2` for missing repo metadata, invalid plans/ledgers, incompatible issue-workflow options, or unsafe issue body references; `3` when apply mode refuses public or unknown repository visibility without `--allow-public`; `4` when selected findings exceed `--max-issues`, an immutable publication plan no longer matches current findings/drafts/advanced evidence, `--verify-ledger` detects GitHub inventory drift or missing duplicate decision records, or `--require-advanced-validation` finds missing required evidence or blocking validation decisions; `gh` command failures return non-zero. |
| Security / disclosure cautions | Default behavior is dry-run. Dry-run is an unapproved preview: it does not write `reports/issue-publication-plan.json`, sets `plan_written=false`, and may print target-specific titles, fingerprints, and issue body hashes. Do not show unsanitized dry-run output in public demos. Command events record only bounded phase/status and run-relative artifact references; they never contain Issue body text. Event path and artifact references are preflighted before GitHub mutation so an unsafe or unwritable event target blocks publication before side effects. Apply mode refuses public or unknown repositories unless `--allow-public` is explicitly provided. Prefer `--plan` followed by reviewed `--apply-plan` when approval must be bound to exact Issue titles, labels, fingerprints, body hashes, chain membership, and advanced-validation evidence state. `reports/known-findings.json`, when present, suppresses `duplicate`, `accepted-risk`, and `invalid-known` findings from default publication selection. `reports/issue-ledger.json` is the local source of truth for publication state and is checked before creating duplicate Issues on re-run. `reports/duplicate-decisions/*.json` records whether a selected finding was treated as `new`, `exact-duplicate`, `variant`, or `related-not-duplicate` before issue creation/skipping. Human review is required before creating issues, especially for security-sensitive findings and issue body drafts. `ATTACK_CHAINS.md` contents are non-public by default and are not copied into generated Issue bodies. |
| Related docs | [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-issues --run runs/OWNER__REPO/RUN_ID --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json --create-labels
gra-issues --run runs/OWNER__REPO/RUN_ID --verify-ledger
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

## Related command aliases and docs

The repository currently has no alternate executable aliases for `gra-*` commands. For end-to-end flows, start with:

- [`docs/LOCAL_INSTALL_AND_AUDIT.md`](LOCAL_INSTALL_AND_AUDIT.md) for first-run setup.
- [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md) for single-repository `exec` mode.
- [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md) for staged recon, target, and research workflows.
- [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md) for scanner ingestion and triage.
- [`docs/TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md) for experimental/P3 cross-repo trace reachability.
- [`docs/METRICS.md`](METRICS.md) for local advanced workflow metrics.
- [`docs/BENCHMARKING.md`](BENCHMARKING.md) for v0.4 dogfood quality gates.
- [`docs/AGENT_SURFACE_DISCOVERY.md`](AGENT_SURFACE_DISCOVERY.md) for AI agent and MCP surface discovery.
- [`docs/PROVENANCE_POSTURE.md`](PROVENANCE_POSTURE.md) for artifact attestation and release provenance posture.
- [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md) for reviewed GitHub Issue creation.
- [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md) for dashboard, SARIF, SQLite, and indexing.

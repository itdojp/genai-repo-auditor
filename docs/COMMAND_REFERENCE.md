# Command Reference

This reference covers the current `bin/gra-*` command surface for GenAI Repo Auditor.
Commands are grouped by workflow phase so operators can choose the smallest command needed for a run.

All examples use placeholder repositories and local run paths. Do not paste real vulnerability details, full secrets, or private findings into public issues, documentation, logs, or support requests.

## General conventions

- Run commands from a checked-out `genai-repo-auditor` repository with `bin/` on `PATH`, or call commands through `./bin/<command>`.
- Every current `gra-*` command supports `--help` and `--version`. `--version` prints the command name and the canonical repository `VERSION` value without running an audit or invoking `gh`, `codex`, or other workflow tools.
- Most commands operate on a run directory such as `runs/OWNER__REPO/RUN_ID`.
- `--network` enables network access inside the Codex sandbox for commands that call Codex. It is disabled by default and should remain disabled unless an approved workflow requires it.
- `--model` defaults to `gpt-5.5` and `--effort` defaults to `xhigh` for Codex-driven commands. Command-line `--model` / `--effort` options are the portable override mechanism across Codex-driven commands.
- Non-interactive `codex exec` invocations set approval behavior through `-c 'approval_policy="never"'` rather than the interactive-only `--ask-for-approval` flag, preserving compatibility with `codex-cli 0.135.0`.
- Codex-driven commands derive the default executable name from the built-in `codex-cli` worker profile while preserving the tested `codex exec` argument construction in `lib/gralib.py`. `gra-agent-check` can list profiles and check whether the required local worker executable is available without running the worker.
- Environment-variable defaults are limited to the Bash wrappers: `gra-audit` and `gra-batch` read `GRA_MODEL`, `CODEX_MODEL`, `GRA_REASONING_EFFORT`, and `CODEX_REASONING_EFFORT`. Staged Python commands such as `gra-recon`, `gra-targets`, `gra-research`, `gra-gapfill`, `gra-variant`, `gra-chains`, `gra-proofs`, `gra-trace`, `gra-metrics`, `gra-adversarial-validate`, and `gra-scanner-triage` ignore those environment variables and require explicit CLI options.
- Python commands use `argparse`; missing required arguments or invalid choices normally exit with status `2`.
- Generated audit artifacts, cloned target repositories, scanner raw outputs, issue drafts, and local stores should remain local and should not be committed.

## Workflow map

| Phase | Commands | Typical output |
|---|---|---|
| Worker profile diagnostics | `gra-agent-check` | Built-in and example worker profile list, executable availability diagnostics |
| Prepare / full audit | `gra-audit` | Run directory, cloned target, rendered prompts, Codex output, reports |
| Batch operation | `gra-batch` | Batch metadata, per-repository logs, `batch-results.json` |
| Target queue | `gra-targets` | `reports/targets.json`, target queue updates |
| Run state / pause guard | `gra-run-state` | `reports/run-state.json`, pause/resume/block status |
| Worktree separation check | `gra-worktree-check` | Final worktree report classifying in-scope and unrelated changes |
| Target coverage gapfill | `gra-gapfill` | `reports/COVERAGE.md`, `reports/gapfill-targets.json`, bounded gapfill target research |
| Research / recon / variant analysis | `gra-recon`, `gra-research`, `gra-variant` | Recon notes, target research, findings updates, variant reports |
| Adversarial validation | `gra-adversarial-validate` | Bounded validation prompt, subject seed JSON, `reports/validation.json`, `reports/VALIDATION.md` |
| Chain synthesis | `gra-chains` | Defensive chain prompt, `reports/chains.json`, `reports/ATTACK_CHAINS.md` |
| Safe local proofs | `gra-proofs` | Benign proof prompt, subject seed JSON, `reports/proofs.json`, `reports/PROOFS.md`, `reports/proofs/` |
| Cross-repo trace reachability | `gra-trace` | Experimental/P3 trace prompt, subject seed JSON, `reports/traces.json`, `reports/TRACE.md` |
| Scanner triage | `gra-ingest`, `gra-scanner-triage` | Raw scanner copies, redacted normalized leads, scanner index, Scorecard posture artifacts, dependency posture artifacts, triage output |
| Validation | `gra-taxonomy-preflight`, `gra-validate-report` | Controlled taxonomy preflight, report contract validation result |
| Reporting / persistence | `gra-metrics`, `gra-dashboard`, `gra-sarif`, `gra-store`, `gra-index` | Local metrics, HTML dashboard, SARIF, SQLite store, run index |
| Issue workflow | `gra-issues` | Dry-run previews, canonical issue ledger, duplicate decision records, ledger verification, or GitHub Issues after human review |

## `gra-agent-check`

| Field | Details |
|---|---|
| Purpose | List local AI worker adapter profiles and verify that a selected profile's required executable is present on `PATH` without executing the worker. |
| Workflow category | Worker profile diagnostics. |
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

## `gra-audit`

| Field | Details |
|---|---|
| Purpose | Clone an authorized GitHub repository, create an isolated audit run, render prompts, and either run a full non-interactive audit or prepare a supervised workflow. |
| Workflow category | Prepare / exec / validation entry point. |
| Required inputs | `--repo OWNER/REPO`. The host must have `git`, `gh`, `codex`, and `python3` available. |
| Key options | `--branch REF`, `--mode exec\|goal\|prepare`, `--model MODEL`, `--effort EFFORT`, `--depth N`, `--run-id ID`, `--runs-dir DIR`, `--codex-json`, `--network`, `--no-lock`, `--allow-invalid-report`. |
| Generated outputs | `context.json`, `run-manifest.json`, cloned `repo/`, `reports/`, rendered `prompt.exec.md` / `prompt.goal.md`, `prompts/`, copied schemas and taxonomy templates, Codex event/output files, `taxonomy-preflight.txt`, `report-validation.txt`, and `run-summary.txt`. The run manifest classifies artifacts as `latest`, `supporting`, or `archive` and records SHA-256 digests for file artifacts. |
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
| Generated outputs | For `--generate`: `prompts/exec/generate-targets.prompt.md`, `codex-targets-events.jsonl`, `codex-targets-stderr.txt`, `codex-targets-final.md`, `taxonomy-preflight-targets.txt`, optional `reports/taxonomy-normalizations.jsonl`, and the expected `reports/targets.json`. Targets can include optional `coverage` metadata for review depth, reviewed/skipped files, commands, unresolved questions, and gapfill recommendation. If `reports/agent-surface.json` exists, high-risk AI agent / MCP surfaces are appended as `TGT-AGENT-NNN` targets. If `reports/provenance-posture.json` exists, release provenance posture recommendations are appended as `TGT-PROVENANCE-NNN` targets. If `reports/supply-chain-posture.json` exists, low-scoring OpenSSF Scorecard posture checks with `target_recommended: true` are appended as `TGT-SCORECARD-NNN` targets. If `reports/dependencies.json` exists, high-signal dependency vulnerability records with dependency paths are appended as `TGT-DEPENDENCY-NNN` targets. For `--mark`: updated target status in `reports/targets.json`. `--list` and `--show` write to stdout only. |
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
| Generated outputs | When AI agent or MCP surfaces are found: `reports/agent-surface.json` and `reports/AGENT_SURFACE.md`. Always writes release provenance posture artifacts `reports/provenance-posture.json` and `reports/PROVENANCE_POSTURE.md`, renders `prompts/exec/recon.prompt.md`, and writes Codex event/output files such as `codex-recon-events.jsonl`, `codex-recon-stderr.txt`, and `codex-recon-final.md`. |
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
| Generated outputs | Target seed JSON under `reports/target-research/`, rendered target prompt, Codex event/output files, `taxonomy-preflight-TGT-ID.txt`, a structured command event appended to `reports/command-events.jsonl`, optional `reports/taxonomy-normalizations.jsonl`, optional `reports/coverage-normalizations.jsonl` / `reports/AUDIT_LOG.md` entries for `coverage.review_depth` aliases, expected target research report under `reports/target-research/TGT-ID.md`, and possible updates to `reports/findings.json`. Exec mode marks the target `in_progress` before execution and `reviewed` or `needs_human_review` after execution. |
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
| Generated outputs | `--list` prints candidates. All actions append a structured command event to `reports/command-events.jsonl`. `--generate` writes `reports/COVERAGE.md`, `reports/gapfill-targets.json`, one plan per source target under `reports/target-research/TGT-XXX-gapfill.md`, appends deterministic `TGT-GAPFILL-NNN` targets to `reports/targets.json` without duplicating existing source-target requeues, separates `current_run` from `cumulative` gapfill counts, records source-target reason / generated-target status / relationship fields, emits prioritized `next_targets`, and may write `reports/coverage-normalizations.jsonl` / `reports/AUDIT_LOG.md` entries when review-depth aliases are normalized. `--target` renders `prompts/exec/gapfill-<TGT-ID>.prompt.md` or `prompts/goal/gapfill-<TGT-ID>.goal.md`, writes a seed JSON under `reports/target-research/`, and in exec mode writes Codex event/output files. |
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
| Generated outputs | Finding/source seed material under `reports/variant-analysis/`, rendered variant prompt, Codex event/output files, and the expected variant analysis report under `reports/variant-analysis/`. |
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
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. `--all-critical-high` selects Critical / High findings whose status is `Confirmed`, `Probable`, or `Potential`. |
| Generated outputs | Subject seed JSON under `reports/adversarial-validation/`, rendered adversarial validation prompt, Codex event/output files in exec mode, and expected validation outputs `reports/validation.json` and `reports/VALIDATION.md`. |
| Exit status behavior | `0` for successful goal preparation, successful Codex exec, or no matching `--all-critical-high` subjects; `2` when a requested finding or chain is missing; exec mode returns Codex execution status. |
| Security / disclosure cautions | This stage must not create new findings, broaden into a full audit, modify the target repository, or run live exploitation. Use it to challenge attacker control, reachability, trust-boundary crossing, mitigations, framework guarantees, middleware ordering, configuration assumptions, test-fixture versus production behavior, and overstated impact before issue publication. |
| Related docs | [`docs/ADVERSARIAL_VALIDATION.md`](ADVERSARIAL_VALIDATION.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md). |

Examples:

```bash
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --chain CHAIN-001 --mode goal
```

## `gra-chains`

| Field | Details |
|---|---|
| Purpose | Synthesize defensive attack or reachability chains from existing findings, targets, scanner refs, and validation notes without generating exploit payloads or weaponized steps. |
| Workflow category | Chain synthesis workflow. |
| Required inputs | `--run RUN_DIR`. The command uses existing local artifacts such as `reports/findings.json`, optional `reports/targets.json`, optional scanner index, and optional validation output. |
| Key options | `--mode exec\|goal`, `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Rendered chain synthesis prompt, Codex event/output files in exec mode, and expected chain artifacts `reports/chains.json` and `reports/ATTACK_CHAINS.md`. |
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
| Generated outputs | Subject seed JSON under `reports/proofs/`, rendered proof prompt, Codex event/output files in exec mode, and expected proof artifacts `reports/proofs.json`, `reports/PROOFS.md`, and safe supporting files under `reports/proofs/`. `reports/proofs.json` records executed proof commands as structured `argv` plus safety metadata rather than shell strings. |
| Exit status behavior | `0` for successful goal preparation, successful Codex exec, or no matching `--all-critical-high` subjects; `2` when a requested finding or `findings.json` is missing; exec mode returns Codex execution status. |
| Security / disclosure cautions | Local/private by default. The prompt forbids working exploit scripts, exploit code, weaponized payloads, credential extraction, auth-bypass execution against live services, network scanning, production/staging probing, dependency installation, target repository modification, and new finding creation. Do not publish proof artifacts wholesale. |
| Related docs | [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

## `gra-trace`

| Field | Details |
|---|---|
| Purpose | Trace whether an existing producer finding, such as a shared-library flaw, is reachable from attacker-controlled entry points in a consumer repository. This feature is experimental/P3. |
| Workflow category | Cross-repo trace reachability workflow. |
| Required inputs | `--producer-run PRODUCER_RUN_DIR --finding SEC-ID` and either `--consumer-run CONSUMER_RUN_DIR` for `exec` / `goal` mode or `--consumer-repo OWNER/REPO` for `prepare` mode. |
| Key options | `--mode prepare\|exec\|goal`, `--branch REF`, `--depth N` for prepare-mode clone, `--model MODEL`, `--effort EFFORT`. `--network` is intentionally unavailable; Codex network access is always disabled for trace execution. |
| Generated outputs | Subject seed JSON under the producer run's `reports/traces/`, rendered trace prompt, Codex event/output files in exec mode, and expected trace artifacts `reports/traces.json` and `reports/TRACE.md` under the producer run. `prepare` mode also creates `trace-consumers/OWNER__repo/` under the producer run and renders a supervised goal prompt. |
| Exit status behavior | `0` for successful prepare/goal setup or successful Codex exec; `2` for missing producer context, missing finding, invalid mode/source combination, missing consumer context, path traversal/symlink safety failures, or clone/setup failures; exec mode returns Codex execution status. |
| Security / disclosure cautions | Trace results are reachability evidence, not exploit proof. The prompt forbids external scanning, production/staging probing, exploit payloads, credential access, dependency installation, and producer/consumer repository modification. Only prepare mode performs an explicit GitHub clone, and it validates the producer finding before cloning. Trace subjects, prompts, Codex event files, `traces.json`, and `TRACE.md` must remain under the producer run directory; unsafe `context.json` paths and symlinked runs are rejected. Keep `TRACE.md` and `traces.json` local/private until human review. |
| Related docs | [`docs/TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md), [`docs/MULTI_REPO.md`](MULTI_REPO.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-repo ORG/consumer-api --mode prepare
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/ORG__consumer-api/RUN_ID --mode exec
gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/ORG__consumer-api/RUN_ID --mode goal
```

## `gra-ingest`

| Field | Details |
|---|---|
| Purpose | Copy scanner output into a run, normalize leads, redact sensitive values, update the scanner index, and produce deterministic posture artifacts for OpenSSF Scorecard JSON, SBOM/dependency graph JSON, and supported dependency vulnerability JSON. |
| Workflow category | Scanner workflow. |
| Required inputs | `--run RUN_DIR --tool TOOL --file FILE`. |
| Key options | `--format FORMAT` (`auto` by default), `--note NOTE`. Use `--tool scorecard` for OpenSSF Scorecard JSON posture ingestion, or `--tool sbom` / `syft` / dependency formats with `--format cyclonedx`, `spdx`, `syft`, or `auto` for SBOM/dependency graph ingestion. Trivy SBOM exports are ingested when the format is CycloneDX or SPDX. Trivy and Grype vulnerability JSON are ingested with `--tool trivy --format json` or `--tool grype --format json`. |
| Generated outputs | Raw scanner result copy under `reports/scanner-results/`, normalized lead JSON under `reports/scanner-results/normalized/`, and `reports/scanner-results/scanner-index.json`. With `--tool scorecard` / `openssf-scorecard` / `ossf-scorecard`, also writes `reports/supply-chain-posture.json`, `reports/supply-chain-posture.md`, and may append deterministic `TGT-SCORECARD-NNN` targets to `reports/targets.json`. With `--tool sbom` or dependency formats, also writes `reports/dependencies.json`, `reports/DEPENDENCY_RISK.md`, and may append deterministic `TGT-DEPENDENCY-NNN` targets to `reports/targets.json`. |
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

## `gra-scanner-triage`

| Field | Details |
|---|---|
| Purpose | Ask Codex to triage imported scanner leads in repository context. |
| Workflow category | Scanner workflow. |
| Required inputs | `--run RUN_DIR` with `reports/scanner-results/scanner-index.json` already present. |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Rendered `prompts/exec/scanner-triage.prompt.md`, Codex event/output files, and triage output expected under the run's reports. |
| Exit status behavior | `0` when Codex succeeds; `2` when scanner index is missing; otherwise returns Codex execution status. |
| Security / disclosure cautions | Treat scanner results as leads, not confirmed findings. Triage should read normalized redacted leads by default and should not quote or reconstruct full secrets. |
| Related docs | [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
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
| Purpose | Validate `findings.json`, optional `targets.json`, optional chain reports, optional proof artifacts, optional cross-repo trace artifacts, optional adversarial validation output, optional scanner index artifacts, optional dependency artifacts, optional issue ledger, optional duplicate decision records, optional run state, optional command event records, optional run manifest artifact retention and digest hygiene, controlled taxonomy names/IDs/labels, issue body references, schema-required fields, finding assessment enums, target-quality bounds, safety constraints, timestamps, fingerprints, affected locations, and obvious secret disclosure risks. |
| Workflow category | Validation workflow. |
| Required inputs | One of `--run RUN_DIR` or `--findings PATH`. |
| Key options | `--run RUN_DIR`, `--findings PATH`. |
| Generated outputs | Console validation result, including `Run manifest: validated` when `run-manifest.json` passes hygiene checks, and a structured command event appended to `reports/command-events.jsonl`. When called by `gra-audit`, output is commonly captured in `run-summary.txt` and `report-validation.txt`. |
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
| Required inputs | `--run RUN_DIR`. |
| Key options | `--out-json OUT` and `--out-md OUT` to override the default `reports/metrics.json` and `reports/METRICS.md`. |
| Generated outputs | `reports/metrics.json` and `reports/METRICS.md` with counts for findings, adversarial validation decisions, downgrade/invalidate rate, chains, proofs, gapfill current/cumulative queue state, traces, issue publication plan warnings, duplicate decisions, command-event durations, failures, reruns, validation retries, taxonomy normalizations, artifact counts, manifest retention buckets, manifest hygiene warning counts, and run duration when available. |
| Exit status behavior | `0` when metrics are written; parser status `2` for usage errors; unsafe `reports_dir` or unreadable local artifacts return `2`. |
| Security / disclosure cautions | Metrics are generated from local report artifacts only and intentionally omit raw finding evidence, issue body text, proof evidence, trace evidence, scanner lead bodies, and secret values. Keep metrics local unless aggregate repository risk information is approved for sharing. |
| Related docs | [`docs/METRICS.md`](METRICS.md), [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Example:

```bash
gra-metrics --run runs/OWNER__REPO/RUN_ID
```

## `gra-dashboard`

| Field | Details |
|---|---|
| Purpose | Generate a local HTML dashboard summarizing a run's findings, structured finding assessment dimensions, target queue, gapfill current/cumulative queue state, advanced workflow metrics, artifact retention, and observability when present, Scorecard supply-chain posture, dependency risk posture, and scanner result index. |
| Workflow category | Reporting workflow. |
| Required inputs | `--run RUN_DIR`. |
| Key options | `--out OUT` to override the default `reports/dashboard.html`. |
| Generated outputs | HTML dashboard file with links to `metrics.json` and `METRICS.md` when `gra-metrics` has been run, including current source-to-gapfill relationships, prioritized next gapfill targets, latest/archive artifact retention counts, manifest hygiene warnings, longest command durations, and high retry / rerun targets from observability metrics. |
| Exit status behavior | `0` when the dashboard is written; parser status `2` for usage errors. Unexpected unreadable input or write failures surface as non-zero Python errors. |
| Security / disclosure cautions | The dashboard can contain finding titles, locations, and evidence. Keep it local unless disclosure has been approved. |
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
| Required inputs | `--run RUN_DIR`. |
| Key options | `--out OUT` to override the default `reports/findings.sarif`. |
| Generated outputs | SARIF JSON file. |
| Exit status behavior | `0` when SARIF is written; parser status `2` for usage errors. Unexpected input or write failures surface as non-zero Python errors. |
| Security / disclosure cautions | SARIF may include evidence, file paths, and finding metadata. Do not upload it to third-party systems unless approved for the target repository. |
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
| Required inputs | `--run RUN_DIR`. |
| Key options | `--db DB` to override the default `<lab>/runs/security-audit.sqlite`. |
| Generated outputs | SQLite database with `runs`, `targets`, `findings`, `scanner_results`, `issues`, and `posture_artifacts` tables. `posture_artifacts` records run manifests, agent-surface discovery, Scorecard posture, provenance posture, and dependency posture when those artifacts exist. |
| Exit status behavior | `0` when import completes; parser status `2` for usage errors. SQLite or filesystem failures surface as non-zero Python errors. |
| Security / disclosure cautions | The SQLite store can aggregate sensitive audit data across repositories. Keep it local, restrict access, and avoid committing it. |
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
| Generated outputs | Preview text in dry-run mode, `reports/issue-publication-plan.json` in plan mode, canonical `reports/issue-ledger.json` for all modes that evaluate findings, `reports/duplicate-decisions/*.json` before dry-run/apply publication decisions, GitHub Issues in apply mode, and `issues-created.json` under the run directory. `issues-created.json` records `plan_sha256` when `--apply-plan` is used. |
| Exit status behavior | `0` for successful dry-run, plan creation, ledger verification, or issue creation; `2` for missing repo metadata, invalid plans/ledgers, incompatible issue-workflow options, or unsafe issue body references; `3` when apply mode refuses public or unknown repository visibility without `--allow-public`; `4` when selected findings exceed `--max-issues`, an immutable publication plan no longer matches current findings/drafts/advanced evidence, `--verify-ledger` detects GitHub inventory drift or missing duplicate decision records, or `--require-advanced-validation` finds missing required evidence or blocking validation decisions; `gh` command failures return non-zero. |
| Security / disclosure cautions | Default behavior is dry-run. Apply mode refuses public or unknown repositories unless `--allow-public` is explicitly provided. Prefer `--plan` followed by reviewed `--apply-plan` when approval must be bound to exact Issue titles, labels, fingerprints, body hashes, chain membership, and advanced-validation evidence state. `reports/issue-ledger.json` is the local source of truth for publication state and is checked before creating duplicate Issues on re-run. `reports/duplicate-decisions/*.json` records whether a selected finding was treated as `new`, `exact-duplicate`, `variant`, or `related-not-duplicate` before issue creation/skipping. Human review is required before creating issues, especially for security-sensitive findings and issue body drafts. `ATTACK_CHAINS.md` contents are non-public by default and are not copied into generated Issue bodies. |
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
- [`docs/AGENT_SURFACE_DISCOVERY.md`](AGENT_SURFACE_DISCOVERY.md) for AI agent and MCP surface discovery.
- [`docs/PROVENANCE_POSTURE.md`](PROVENANCE_POSTURE.md) for artifact attestation and release provenance posture.
- [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md) for reviewed GitHub Issue creation.
- [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md) for dashboard, SARIF, SQLite, and indexing.

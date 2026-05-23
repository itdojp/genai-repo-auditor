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
- Environment-variable defaults are limited to the Bash wrappers: `gra-audit` and `gra-batch` read `GRA_MODEL`, `CODEX_MODEL`, `GRA_REASONING_EFFORT`, and `CODEX_REASONING_EFFORT`. Staged Python commands such as `gra-recon`, `gra-targets`, `gra-research`, `gra-variant`, and `gra-scanner-triage` ignore those environment variables and require explicit CLI options.
- Python commands use `argparse`; missing required arguments or invalid choices normally exit with status `2`.
- Generated audit artifacts, cloned target repositories, scanner raw outputs, issue drafts, and local stores should remain local and should not be committed.

## Workflow map

| Phase | Commands | Typical output |
|---|---|---|
| Prepare / full audit | `gra-audit` | Run directory, cloned target, rendered prompts, Codex output, reports |
| Batch operation | `gra-batch` | Batch metadata, per-repository logs, `batch-results.json` |
| Target queue | `gra-targets` | `reports/targets.json`, target queue updates |
| Research / recon / variant analysis | `gra-recon`, `gra-research`, `gra-variant` | Recon notes, target research, findings updates, variant reports |
| Scanner triage | `gra-ingest`, `gra-scanner-triage` | Raw scanner copies, redacted normalized leads, scanner index, triage output |
| Validation | `gra-validate-report` | Report contract validation result |
| Reporting / persistence | `gra-dashboard`, `gra-sarif`, `gra-store`, `gra-index` | HTML dashboard, SARIF, SQLite store, run index |
| Issue workflow | `gra-issues` | Dry-run previews or GitHub Issues after human review |

## `gra-audit`

| Field | Details |
|---|---|
| Purpose | Clone an authorized GitHub repository, create an isolated audit run, render prompts, and either run a full non-interactive audit or prepare a supervised workflow. |
| Workflow category | Prepare / exec / validation entry point. |
| Required inputs | `--repo OWNER/REPO`. The host must have `git`, `gh`, `codex`, and `python3` available. |
| Key options | `--branch REF`, `--mode exec\|goal\|prepare`, `--model MODEL`, `--effort EFFORT`, `--depth N`, `--run-id ID`, `--runs-dir DIR`, `--codex-json`, `--network`, `--no-lock`, `--allow-invalid-report`. |
| Generated outputs | `context.json`, `run-manifest.json`, cloned `repo/`, `reports/`, rendered `prompt.exec.md` / `prompt.goal.md`, `prompts/`, copied schemas, Codex event/output files, `report-validation.txt`, and `run-summary.txt`. |
| Exit status behavior | `0` for successful prepare/goal setup or successful exec with valid report; `2` for usage errors; `1` for missing required local commands or missing/invalid reports when Codex itself succeeds; `12` for lock contention; in exec mode Codex or validation status can be propagated. |
| Security / disclosure cautions | Use only on repositories you are authorized to audit. Keep generated reports local. `run-manifest.json` is bounded, run-relative metadata for support diagnostics; it must not be treated as a substitute for reviewing findings or issue drafts. Use `--network` and `--allow-invalid-report` only with explicit operational justification. Do not disable locks for concurrent same-repository audits unless you can isolate output paths safely. |
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
| Purpose | Generate and manage the target queue for staged audits. |
| Workflow category | Target workflow. |
| Required inputs | `--run RUN_DIR` and exactly one action: `--generate`, `--list`, `--show TGT-ID`, or `--mark TGT-ID STATUS`. |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. `--mark` accepts `queued`, `in_progress`, `reviewed`, `skipped`, or `needs_human_review`. |
| Generated outputs | For `--generate`: `prompts/exec/generate-targets.prompt.md`, `codex-targets-events.jsonl`, `codex-targets-stderr.txt`, `codex-targets-final.md`, and the expected `reports/targets.json`. For `--mark`: updated target status in `reports/targets.json`. `--list` and `--show` write to stdout only. |
| Exit status behavior | `0` for successful list/show/mark/generate; `1` when Codex completes but `reports/targets.json` is missing after generation; `2` for missing context, unknown target, or invalid target status. Codex execution status is returned for generation failures. |
| Security / disclosure cautions | Target queues are local planning artifacts. Review generated scope before using it to drive deeper research. Avoid network access unless the audit plan explicitly requires it. |
| Related docs | [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Examples:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate
gra-targets --run runs/OWNER__REPO/RUN_ID --list
gra-targets --run runs/OWNER__REPO/RUN_ID --mark TGT-001 reviewed
```

## `gra-recon`

| Field | Details |
|---|---|
| Purpose | Run the reconnaissance phase for a prepared audit run by rendering and executing the recon prompt. |
| Workflow category | Research / recon workflow. |
| Required inputs | `--run RUN_DIR` with an existing `context.json`. |
| Key options | `--model MODEL`, `--effort EFFORT`, `--network`. |
| Generated outputs | Rendered `prompts/exec/recon.prompt.md`, Codex event/output files such as `codex-recon-events.jsonl`, `codex-recon-stderr.txt`, and `codex-recon-final.md`. |
| Exit status behavior | Returns the Codex execution status; `0` indicates Codex completed successfully. `argparse` returns `2` for usage errors. |
| Security / disclosure cautions | Recon is still a defensive local code review phase. Do not expand scope beyond the cloned repository and approved inputs. |
| Related docs | [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md), [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

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
| Generated outputs | Target seed JSON under `reports/target-research/`, rendered target prompt, Codex event/output files, expected target research report under `reports/target-research/TGT-ID.md`, and possible updates to `reports/findings.json`. Exec mode marks the target `in_progress` before execution and `reviewed` or `needs_human_review` after execution. |
| Exit status behavior | `0` for successful goal preparation or successful Codex exec; `2` when the requested target is not found; exec mode returns Codex execution status. |
| Security / disclosure cautions | Treat target research as analysis, not exploitation. Keep evidence minimal and avoid reconstructing secret values in outputs. |
| Related docs | [`docs/TARGET_QUEUE.md`](TARGET_QUEUE.md), [`docs/GOAL_DEEP_DIVE_WORKFLOW.md`](GOAL_DEEP_DIVE_WORKFLOW.md), [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md). |

Examples:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode exec
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal
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

## `gra-ingest`

| Field | Details |
|---|---|
| Purpose | Copy scanner output into a run, normalize leads, redact sensitive values, and update the scanner index. |
| Workflow category | Scanner workflow. |
| Required inputs | `--run RUN_DIR --tool TOOL --file FILE`. |
| Key options | `--format FORMAT` (`auto` by default), `--note NOTE`. |
| Generated outputs | Raw scanner result copy under `reports/scanner-results/`, normalized lead JSON under `reports/scanner-results/normalized/`, and `reports/scanner-results/scanner-index.json`. |
| Exit status behavior | `0` for successful ingest; `2` when the source file is missing. JSON/context or filesystem failures surface as non-zero Python errors. |
| Security / disclosure cautions | Scanner output is untrusted input. The command writes redacted normalized leads, but raw scanner copies can still contain sensitive data; keep them local and do not commit them. |
| Related docs | [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md). |

Example:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file scanner-output.json --format json
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

## `gra-validate-report`

| Field | Details |
|---|---|
| Purpose | Validate `findings.json`, optional `targets.json`, issue body references, schema-required fields, safety constraints, timestamps, fingerprints, affected locations, and obvious secret disclosure risks. |
| Workflow category | Validation workflow. |
| Required inputs | One of `--run RUN_DIR` or `--findings PATH`. |
| Key options | `--run RUN_DIR`, `--findings PATH`. |
| Generated outputs | Console validation result. When called by `gra-audit`, output is commonly captured in `run-summary.txt` and `report-validation.txt`. |
| Exit status behavior | `0` when validation passes; `1` for invalid JSON or validation errors; parser error status `2` when neither `--run` nor `--findings` is supplied. |
| Security / disclosure cautions | Validation reduces risk but is not a substitute for human review. Check findings and issue drafts before sharing outside the approved audience. |
| Related docs | [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-validate-report --findings runs/OWNER__REPO/RUN_ID/reports/findings.json
```

## `gra-dashboard`

| Field | Details |
|---|---|
| Purpose | Generate a local HTML dashboard summarizing a run's findings, target queue, and scanner result index. |
| Workflow category | Reporting workflow. |
| Required inputs | `--run RUN_DIR`. |
| Key options | `--out OUT` to override the default `reports/dashboard.html`. |
| Generated outputs | HTML dashboard file. |
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
| Purpose | Convert `reports/findings.json` to SARIF 2.1.0 for local review or compatible tooling. |
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
| Purpose | Import run metadata, targets, findings, scanner results, and created issue records into a local SQLite database. |
| Workflow category | Reporting / persistence workflow. |
| Required inputs | `--run RUN_DIR`. |
| Key options | `--db DB` to override the default `<lab>/runs/security-audit.sqlite`. |
| Generated outputs | SQLite database with `runs`, `targets`, `findings`, `scanner_results`, and `issues` tables. |
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
| Purpose | Build a lightweight index across audit runs by scanning for `reports/findings.json`. |
| Workflow category | Reporting / index workflow. |
| Required inputs | Existing runs directory. Defaults to `runs`. |
| Key options | `--runs-dir RUNS_DIR`. |
| Generated outputs | `index.json` and `index.md` in the selected runs directory. |
| Exit status behavior | `0` when index files are written. The selected runs directory must exist and be writable. |
| Security / disclosure cautions | The generated index summarizes findings and run paths. Keep it local if repository names, run paths, or finding counts are sensitive. |
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
| Key options | `--repo OWNER/REPO`, `--min-severity Critical\|High\|Medium\|Low\|Informational`, `--statuses LIST`, `--dry-run`, `--plan`, `--apply`, `--apply-plan PLAN`, `--replan`, `--allow-public`, `--create-labels`, `--assignee ASSIGNEE`, `--max-issues N`. |
| Generated outputs | Preview text in dry-run mode, `reports/issue-publication-plan.json` in plan mode, GitHub Issues in apply mode, and `issues-created.json` under the run directory. `issues-created.json` records `plan_sha256` when `--apply-plan` is used. |
| Exit status behavior | `0` for successful dry-run, plan creation, or issue creation; `2` for missing repo metadata, invalid plans, or unsafe issue body references; `3` when apply mode refuses public or unknown repository visibility without `--allow-public`; `4` when selected findings exceed `--max-issues` or an immutable publication plan no longer matches current findings/drafts; `gh` command failures return non-zero. |
| Security / disclosure cautions | Default behavior is dry-run. Apply mode refuses public or unknown repositories unless `--allow-public` is explicitly provided. Prefer `--plan` followed by reviewed `--apply-plan` when approval must be bound to exact Issue titles, labels, fingerprints, and body hashes. Human review is required before creating issues, especially for security-sensitive findings and issue body drafts. |
| Related docs | [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md). |

Examples:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
gra-issues --run runs/OWNER__REPO/RUN_ID --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json --create-labels
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

## Related command aliases and docs

The repository currently has no alternate executable aliases for `gra-*` commands. For end-to-end flows, start with:

- [`docs/LOCAL_INSTALL_AND_AUDIT.md`](LOCAL_INSTALL_AND_AUDIT.md) for first-run setup.
- [`docs/NORMAL_WORKFLOW.md`](NORMAL_WORKFLOW.md) for single-repository `exec` mode.
- [`docs/STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md) for staged recon, target, and research workflows.
- [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md) for scanner ingestion and triage.
- [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md) for reviewed GitHub Issue creation.
- [`docs/REPORTING_AND_STORE.md`](REPORTING_AND_STORE.md) for dashboard, SARIF, SQLite, and indexing.

# GenAI Repo Auditor

Local-first GenAI-assisted repository security auditor with threat modeling, target queues, validation, scanner triage, SARIF output, SQLite persistence, and GitHub Issue workflows.

GenAI Repo Auditor helps security teams review authorized source repositories without sending audit reports to a central service. It creates an isolated run directory, clones a target GitHub repository into that run, asks a compatible AI coding agent to perform defensive analysis, and writes structured local reports.

This project is defensive-only. It does not perform external scanning, live exploitation, credential access, production probing, or weaponized exploit generation.

This project is not affiliated with OpenAI, Anthropic, GitHub, or any other AI model or platform vendor. Product names are used only to identify compatibility.

## Compatibility

The current implementation is designed to run with OpenAI Codex CLI where available. The project name, command names, and documentation avoid vendor branding so the workflow can be adapted to other local or CLI-based AI coding agents that support:

- non-interactive execution
- workspace sandboxing
- local repository analysis
- structured report output
- long-running supervised goals

## Workflow

```text
prepare
  -> recon
  -> target queue
  -> target research
  -> validation
  -> variant analysis
  -> scanner triage
  -> dashboard / SARIF / SQLite store
  -> human review
  -> GitHub Issue
```

## Requirements

Required:

```text
git
gh
codex
python3
```

Recommended:

```text
rg
jq
flock
sqlite3
```

## Setup

```bash
git clone https://github.com/itdojp/genai-repo-auditor.git
cd genai-repo-auditor
chmod +x bin/*
export PATH="$PWD/bin:$PATH"

gh auth status
codex --help >/dev/null
python3 --version
```

For a fresh local install and first `OWNER/REPO` audit, see:

- `docs/LOCAL_INSTALL_AND_AUDIT.md` (English)
- `docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md` (Japanese)

## Quick start: full audit

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

A run directory is created under `runs/`:

```text
runs/OWNER__REPO/RUN_ID/
  repo/                # target repository; untrusted input
  reports/             # local audit reports
  prompts/             # rendered prompts
  prompt.exec.md
  prompt.goal.md
  codex-events.jsonl
  codex-final.md
```

Validate and render reports:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-sarif --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID
```

Create GitHub Issues only after human review:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

Public repository Issue creation is denied by default. Use `--allow-public` only when public disclosure is intentional and approved.

## Staged audit for large repositories

For large or high-value repositories, prefer the staged workflow.

Prepare a run:

```bash
gra-audit --repo OWNER/REPO --mode prepare --model gpt-5.5 --effort xhigh
```

Run recon:

```bash
gra-recon --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Generate target queue:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --list
```

Research one target:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --model gpt-5.5 --effort xhigh
```

Supervised deep dive with `/goal`:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal --model gpt-5.5 --effort xhigh
```

Variant analysis:

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --model gpt-5.5 --effort xhigh
```

## Scanner integration

GenAI Repo Auditor does not run external scanners by default. It ingests scanner output and lets the AI agent triage leads in repository context.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Scanner results are leads, not findings. A lead is promoted only after reachability, trust boundary impact, mitigation status, and evidence are reviewed.

## Multiple repositories

```bash
cp examples/repos.txt.example repos.txt
# edit repos.txt
gra-batch \
  --repo-list repos.txt \
  --concurrency 1 \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

Start with `--concurrency 1`. If parallelizing, use low concurrency and keep Issue creation sequential.
Batch runs write `runs/_batches/BATCH_ID/batch-results.json` and exit non-zero by default
when one or more repository audits fail. Use `--allow-failures` only when this is intentional;
use `--fail-fast` with `--concurrency 1` when CI should stop at the first failed repository.

## Commands

For detailed options, outputs, exit status behavior, and safety cautions, see [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md).

| Command | Purpose |
|---|---|
| `gra-audit` | Clone a repo, create a run, execute full audit, prepare goal mode |
| `gra-recon` | Generate inventory, threat model, and attack surface |
| `gra-targets` | Generate, list, show, and update target queue |
| `gra-research` | Research one target with exec or supervised goal mode |
| `gra-variant` | Find variants based on a finding or root cause |
| `gra-ingest` | Ingest scanner outputs |
| `gra-scanner-triage` | Triage scanner leads in repository context |
| `gra-validate-report` | Validate `findings.json`, `targets.json`, and report contract |
| `gra-dashboard` | Generate local HTML dashboard |
| `gra-sarif` | Generate SARIF output |
| `gra-store` | Import run data into SQLite |
| `gra-issues` | Create GitHub Issues from reviewed findings |
| `gra-batch` | Audit multiple repositories sequentially or with low concurrency |
| `gra-index` | Build an index across runs |

## Safety boundaries

Do not use this project for:

- unauthorized repository or system assessment
- production, staging, or external host scanning
- live exploitation
- brute force attempts
- credential access or credential rotation
- full secret value disclosure
- weaponized exploit generation
- autonomous patching without human review
- combining audit, remediation, and Issue creation in one unattended run

## Documentation

- [`docs/LOCAL_INSTALL_AND_AUDIT.md`](docs/LOCAL_INSTALL_AND_AUDIT.md)
- [`docs/COMMAND_REFERENCE.md`](docs/COMMAND_REFERENCE.md)
- Japanese docs index: [`docs/ja/README.md`](docs/ja/README.md)
  - [`docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md`](docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md)
  - [`docs/ja/USAGE.ja.md`](docs/ja/USAGE.ja.md)
  - [`docs/ja/ISSUE_WORKFLOW.ja.md`](docs/ja/ISSUE_WORKFLOW.ja.md)
  - [`docs/ja/SCANNER_INTEGRATION.ja.md`](docs/ja/SCANNER_INTEGRATION.ja.md)
  - [`docs/ja/SECURITY_MODEL.ja.md`](docs/ja/SECURITY_MODEL.ja.md)
- [`docs/WORKFLOW_OVERVIEW.md`](docs/WORKFLOW_OVERVIEW.md)
- [`docs/NORMAL_WORKFLOW.md`](docs/NORMAL_WORKFLOW.md)
- [`docs/GOAL_DEEP_DIVE.md`](docs/GOAL_DEEP_DIVE.md)
- [`docs/STAGED_AGENTIC_WORKFLOW.md`](docs/STAGED_AGENTIC_WORKFLOW.md)
- [`docs/TARGET_QUEUE.md`](docs/TARGET_QUEUE.md)
- [`docs/VARIANT_ANALYSIS.md`](docs/VARIANT_ANALYSIS.md)
- [`docs/SCANNER_INTEGRATION.md`](docs/SCANNER_INTEGRATION.md)
- [`docs/ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md)
- [`docs/REPORTING_AND_STORE.md`](docs/REPORTING_AND_STORE.md)
- [`docs/REPORT_CONTRACT.md`](docs/REPORT_CONTRACT.md)
- [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)
- [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
- [`docs/CODEX_WORK_INSTRUCTIONS.md`](docs/CODEX_WORK_INSTRUCTIONS.md)

## License

Apache License 2.0. See `LICENSE`.

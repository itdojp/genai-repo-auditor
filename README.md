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
  -> chain synthesis / safe local proofs / adversarial validation
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
gra-audit --version
```

For a fresh local install and first `OWNER/REPO` audit, see:

- `docs/LOCAL_INSTALL_AND_AUDIT.md` (English)
- `docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md` (Japanese)
- `docs/LOCAL_ARTIFACT_CLEANUP.md` for local retention and cleanup guidance

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
  templates/           # copied taxonomy profiles and aliases for the run
  prompt.exec.md
  prompt.goal.md
  codex-events.jsonl
  codex-final.md
```

Validate, synthesize defensive chain context, and render reports:

```bash
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__REPO/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-sarif --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID
```

Create GitHub Issues only after human review:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__REPO/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
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

Defensive chain synthesis, optional cross-repo trace reachability, and adversarial validation before Issue publication:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high --model gpt-5.5 --effort xhigh
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__REPO/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec --model gpt-5.5 --effort xhigh
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --model gpt-5.5 --effort xhigh
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

`gra-trace` is experimental/P3. It records cross-repo reachability evidence for
shared-library or producer findings; it is not exploit proof and must remain
local/private until reviewed.

## Scanner integration

GenAI Repo Auditor does not run external scanners by default. It ingests scanner output and lets the AI agent triage leads in repository context.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool grype --file grype.json --format json
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Scanner results are leads, not findings. A lead is promoted only after reachability, trust boundary impact, mitigation status, and evidence are reviewed.

OpenSSF Scorecard JSON ingestion additionally writes deterministic supply-chain
posture artifacts and can append bounded `TGT-SCORECARD-NNN` review targets for
low-scoring checks.
SBOM and dependency graph ingestion writes `reports/dependencies.json` and
`reports/DEPENDENCY_RISK.md` for local dependency posture review. High-signal
direct Critical/High vulnerability records and transitive high-severity records
with dependency paths can append bounded `TGT-DEPENDENCY-NNN` review targets;
they remain posture evidence until repository reachability is confirmed.
Trivy and Grype vulnerability JSON can also add dependency vulnerability evidence
and link records to existing SBOM-derived components when package identifiers
match.

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
| `gra-gapfill` | Requeue high-risk targets with incomplete coverage |
| `gra-variant` | Find variants based on a finding or root cause |
| `gra-adversarial-validate` | Independently challenge existing findings or chains before publication |
| `gra-chains` | Synthesize defensive attack-chain reports from existing audit evidence |
| `gra-proofs` | Generate safe local proof artifacts for existing findings |
| `gra-trace` | Trace experimental/P3 cross-repo reachability for shared-library findings |
| `gra-metrics` | Generate local advanced workflow metrics without raw evidence |
| `gra-ingest` | Ingest scanner outputs |
| `gra-scanner-triage` | Triage scanner leads in repository context |
| `gra-taxonomy-preflight` | Preflight and normalize controlled taxonomy references |
| `gra-validate-report` | Validate `findings.json`, `targets.json`, chain, proof, trace, validation output, and report contract |
| `gra-dashboard` | Generate local HTML dashboard with metrics links when present |
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
- [`docs/ADVERSARIAL_VALIDATION.md`](docs/ADVERSARIAL_VALIDATION.md)
- [`docs/ATTACK_CHAINS.md`](docs/ATTACK_CHAINS.md)
- [`docs/SAFE_LOCAL_PROOFS.md`](docs/SAFE_LOCAL_PROOFS.md)
- [`docs/TRACE_REACHABILITY.md`](docs/TRACE_REACHABILITY.md)
- [`docs/METRICS.md`](docs/METRICS.md)
- [`docs/SCANNER_INTEGRATION.md`](docs/SCANNER_INTEGRATION.md)
- [`docs/SCORECARD_INGESTION.md`](docs/SCORECARD_INGESTION.md)
- [`docs/DEPENDENCY_INGESTION.md`](docs/DEPENDENCY_INGESTION.md)
- [`docs/ISSUE_WORKFLOW.md`](docs/ISSUE_WORKFLOW.md)
- [`docs/REPORTING_AND_STORE.md`](docs/REPORTING_AND_STORE.md)
- [`docs/REPORT_CONTRACT.md`](docs/REPORT_CONTRACT.md)
- [`docs/TAXONOMIES.md`](docs/TAXONOMIES.md)
- [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md)
- [`docs/ADVERSARIAL_FIXTURES.md`](docs/ADVERSARIAL_FIXTURES.md)
- [`docs/AGENT_SURFACE_DISCOVERY.md`](docs/AGENT_SURFACE_DISCOVERY.md)
- [`docs/PROVENANCE_POSTURE.md`](docs/PROVENANCE_POSTURE.md)
- [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
- [`docs/CODEX_WORK_INSTRUCTIONS.md`](docs/CODEX_WORK_INSTRUCTIONS.md)

## License

Apache License 2.0. See `LICENSE`.

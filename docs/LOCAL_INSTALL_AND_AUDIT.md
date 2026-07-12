# Local install and first GitHub repository audit

This guide shows how to install GenAI Repo Auditor into a local user directory and run an audit by specifying a GitHub repository as `OWNER/REPO`.

For the Japanese version, see [`docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md`](ja/LOCAL_INSTALL_AND_AUDIT.ja.md).

## Scope and safety

Use this workflow only for repositories you are authorized to review. GenAI Repo Auditor is defensive-only: it clones source code locally, runs a compatible AI coding-agent workflow in a local run directory, and writes local reports. It does not perform live exploitation, external host scanning, brute force, credential access, or automatic remediation.

Public GitHub Issue creation for vulnerabilities is a separate, opt-in step and must be performed only after human review.

## Prerequisites

Required commands:

```text
git
gh
codex
python3
```

Recommended commands:

```text
shellcheck
rg
jq
flock
sqlite3
```

Notes:

- `gh` must be authenticated to GitHub and must have access to the target repository.
- The current implementation invokes `codex exec` for non-interactive audits. Install and configure a compatible `codex` CLI before running `--mode exec` or `--mode goal` workflows. Exec-mode commands set approvals with `-c 'approval_policy="never"'`, which is compatible with `codex-cli 0.135.0`; interactive `/goal` instructions may still use the top-level `codex --ask-for-approval` flag.
- `shellcheck` is required only for project validation, not for running an audit.
- If you audit private repositories, ensure the authenticated `gh` account can clone and inspect them.

## Install locally

Choose one of the installation modes below.

| Mode | When to use it | Command style |
|---|---|---|
| Source checkout | You want editable repository files, local scripts, and development validation commands. | `git clone`, `PATH=$GRA_HOME/bin:$PATH` |
| `pipx` | You want isolated user-level console scripts from a checkout or release archive. | `pipx install .` |
| `uv tool` | You use `uv` for isolated tool installs. | `uv tool install .` |
| Virtual environment | You need deterministic CI or locked-down workstation setup without `pipx`/`uv`. | `python -m venv`, `pip install .` |

The packaging install matrix is exercised in CI on Ubuntu, macOS, and Windows
with Python 3.10, 3.11, and 3.12. Platform support varies by workflow; read the
[`Windows, WSL2, and PowerShell support matrix`](WINDOWS_WSL_SUPPORT.md) before
using native Windows execution or container-backed scanners. The source-checkout
wrappers remain the preferred development workflow; packaged console scripts
are the preferred operator workflow when you do not need to edit repository
files.

PyPI publication is not yet an approved installation source. Repository-side
trusted-publishing controls are documented in
[`PYPI_DISTRIBUTION.md`](PYPI_DISTRIBUTION.md), but the project name, ownership,
and public package URL remain human-verified external state. Until that document
records an approved URL through a later reviewed change, install from a reviewed
checkout or GitHub release archive as shown below.

### Source checkout install

Choose a user-owned install directory. This example uses `$HOME/.local/opt`. Keep `GRA_HOME` set when following the examples so run paths are absolute and do not depend on your current directory.

```bash
mkdir -p "$HOME/.local/opt"
export GRA_HOME="$HOME/.local/opt/genai-repo-auditor"
git clone https://github.com/itdojp/genai-repo-auditor.git "$GRA_HOME"
cd "$GRA_HOME"
chmod +x bin/* scripts/*.sh
```

Add the command directory to your shell path for the current session:

```bash
export GRA_HOME="$HOME/.local/opt/genai-repo-auditor"
export PATH="$GRA_HOME/bin:$PATH"
```

To make the path persistent for future shells, add both `export GRA_HOME=...` and `export PATH=...` lines to your shell startup file, such as `~/.profile`, `~/.bashrc`, or `~/.zshrc`.

### `pipx` install

From a checked-out repository or unpacked release archive:

```bash
cd genai-repo-auditor
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install . --force
```

On Windows PowerShell:

```powershell
cd genai-repo-auditor
py -m pip install --user pipx
py -m pipx ensurepath
py -m pipx install . --force
```

Open a new shell if `ensurepath` updated your `PATH`.

### `uv tool` install

From a checked-out repository or unpacked release archive:

```bash
cd genai-repo-auditor
uv tool install .
```

On Windows PowerShell:

```powershell
cd genai-repo-auditor
uv tool install .
```

Reinstall from the updated checkout or release archive when you need to update the installed console scripts.

### Virtual environment install

macOS/Linux:

```bash
cd genai-repo-auditor
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Windows PowerShell:

```powershell
cd genai-repo-auditor
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

## Verify the installation

From any directory, verify that the commands resolve:

```bash
gra-audit --help
gra-doctor --help
gra-validate-report --help
gra-audit --version
```

The version output should match the repository [`VERSION`](../VERSION) file and does not run an audit.

For a deterministic local install smoke check that does not require `gh`,
`codex`, network access, or a real target repository, run:

```bash
"$GRA_HOME/scripts/validate-install-smoke.sh"
```

For packaged installs, run the redacted readiness diagnostic instead:

```bash
gra-doctor --json --runs-dir "$HOME/.local/state/genai-repo-auditor/runs"
```

On Windows PowerShell:

```powershell
gra-doctor --json --runs-dir "$env:LOCALAPPDATA\genai-repo-auditor\runs"
```

`gra-doctor` checks Python version, platform support, Git/GitHub CLI availability,
the configured worker executable, optional sandbox runtimes, a writable run
directory, packaged resources, and the installed GenAI Repo Auditor version. It
reports only the names of present `GH_TOKEN` / `GITHUB_TOKEN` variables and
their precedence, never their values. By default it does not execute `git`,
`gh`, audits, workers, clone repositories, or modify GitHub state. The
run-directory check only creates and removes a temporary local probe file under
`--runs-dir`. Add `--strict` when CI should fail on required readiness errors.

After confirming that `PATH` resolves `git` and `gh` to trusted local binaries, use the opt-in external probe to include tool versions and GitHub authentication state. The probe does not pass credential-like environment variables to child processes, discards `gh auth status` output, and records only redacted diagnostics.

```bash
gra-doctor --probe-external-tools --json --runs-dir "$HOME/.local/state/genai-repo-auditor/runs"
```

On Windows PowerShell:

```powershell
gra-doctor --probe-external-tools --json --runs-dir "$env:LOCALAPPDATA\genai-repo-auditor\runs"
```

Verify required external tools:

```bash
git --version
gh --version
python3 --version
codex --help >/dev/null
```

Verify GitHub authentication and target repository access:

```bash
gh auth status
gh repo view OWNER/REPO --json nameWithOwner,visibility,defaultBranchRef
```

Replace `OWNER/REPO` with the GitHub repository you are authorized to audit, for example `my-org/my-service`.

## Recommended first audit: declarative plan and execution

Start with `prepare` mode. It clones the authorized target and renders run
context without executing the configured agent worker.

```bash
RUNS_DIR="$GRA_HOME/runs"
gra-doctor --json --runs-dir "$RUNS_DIR"
gra-audit \
  --repo OWNER/REPO \
  --mode prepare \
  --run-id first-audit \
  --runs-dir "$RUNS_DIR"
RUN_DIR="$RUNS_DIR/OWNER__REPO/first-audit"
```

Review the generated context, then create a `recon-only` workflow plan. Planning
is the default and does not execute a stage.

```bash
cat "$RUN_DIR/context.json"
gra-run --run "$RUN_DIR" --profile recon-only
cat "$RUN_DIR/reports/WORKFLOW_PLAN.md"
```

After reviewing the exact stage order and sanitized commands, execute a bounded
range and inspect its checkpoint report. Resume then continues the same plan
without repeating the successful reconnaissance stage.

```bash
gra-run --run "$RUN_DIR" --profile recon-only --execute --until recon
cat "$RUN_DIR/reports/WORKFLOW_EXECUTION.md"
gra-run --run "$RUN_DIR" --profile recon-only --resume
gra-targets --run "$RUN_DIR" --list
```

The machine-readable checkpoint is
`$RUN_DIR/reports/workflow-checkpoint.json`. A failed or interrupted execution
uses the same inspection-and-`--resume` sequence. Do not start a different
profile on that checkpoint: one workflow execution selects one profile and an
existing checkpoint requires `--resume`.

The `appsec-deep`, `publication-ready`, and `full` profiles require existing
inputs such as `reports/findings.json`. Select them only for a compatible fresh
run or a supervised `--from` range with all prerequisite artifacts. They are
not follow-on profiles to run sequentially after `recon-only` in the same run.

For a reporting profile, refresh terminal reports after successful completion
so the final workflow state and completion event are included:

```bash
gra-metrics --run "$RUN_DIR"
gra-evidence-graph --run "$RUN_DIR"
gra-validate-report --run "$RUN_DIR"
```

Built-in profiles are offline and local-artifacts-only. Scanner stages use
`gra-scan --plan`, not scanner execution. Issue publication, remediation,
release publication, GitHub mutation, and network-enabling actions remain
outside unattended profiles.

## Advanced supervised commands

After the target queue is reviewed, individual commands remain available for
operator-selected target research and other deep dives. These commands may
invoke the configured worker and are not an automatic continuation of
`gra-run`:

```bash
gra-research --run "$RUN_DIR" --target TGT-001
gra-gapfill --run "$RUN_DIR" --generate
gra-chains --run "$RUN_DIR"
gra-proofs --run "$RUN_DIR" --all-critical-high
gra-adversarial-validate --run "$RUN_DIR" --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run "$RUN_DIR"
gra-dashboard --run "$RUN_DIR"
gra-sarif --run "$RUN_DIR"
gra-store --run "$RUN_DIR"
```

Treat all AI output as review input. Validate `reports/findings.json`, evidence,
and Issue drafts before any publication decision.

## Review the results

The primary workflow artifacts are:

```text
$GRA_HOME/runs/OWNER__REPO/RUN_ID/
  context.json
  repo/                         # cloned target; treat as untrusted input
  reports/
    workflow-plan.json
    WORKFLOW_PLAN.md
    workflow-checkpoint.json
    workflow-execution.json
    WORKFLOW_EXECUTION.md
    targets.json
    findings.json               # present only after finding-producing work
    issue-drafts/
```

Inspect the plan and execution report first. When findings exist, review
`reports/FINDINGS.md`, `reports/findings.json`, chain/proof/validation outputs,
and `reports/issue-drafts/` before taking action.

## Optional GitHub Issue workflow

Always start with a dry run:

```bash
gra-issues --run "$RUN_DIR" --dry-run
```

Create issues only after the findings are verified and disclosure is approved:

```bash
gra-issues --run "$RUN_DIR" --apply --create-labels
```

Public repository Issue creation is blocked by default. Use `--allow-public` only when public disclosure is intentional and approved.

## Update the local install

```bash
cd "$GRA_HOME"
git pull --ff-only
chmod +x bin/* scripts/*.sh
```

## Troubleshooting

| Symptom | Check | Typical fix |
|---|---|---|
| `Missing required command: gh` | `gh --version` | Install GitHub CLI and retry. |
| `gh repo clone` fails | `gh auth status`; `gh repo view OWNER/REPO` | Authenticate with `gh auth login` or use an account with repository access. |
| Stored GitHub CLI auth is valid but `gh` still fails | Inspect only the names `GH_TOKEN` / `GITHUB_TOKEN`; run `gra-doctor --probe-external-tools --json` | Remove an unintended stale variable without printing it; `GH_TOKEN` precedes `GITHUB_TOKEN`, and both precede stored auth. |
| `Missing required command: codex` | `codex --help` | Install and configure a compatible Codex CLI. |
| Native Windows efficacy report generation exits `2` | `gra-efficacy-benchmark --list`; inspect `platform_support` from `gra-doctor --json` | Keep list/inspection on Windows and run report generation in WSL2/Linux/macOS. Do not bypass dirfd safeguards. |
| Native Windows scanner execution is unavailable | Docker Desktop Linux-container mode and local named pipe | Use WSL2 for supported Docker/Podman operation; native Windows execution is experimental. |
| No reports are produced | `codex-final.md`; `codex-stderr.txt` | Inspect the run directory for model, auth, or sandbox errors. |
| Report validation fails | `report-validation.txt`; `reports/findings.json` | Fix or regenerate invalid report data before creating issues. |
| Another audit is already running | `runs/.locks/` | Wait for the current audit or use `--no-lock` only when you are sure no conflicting run exists. |

## Local artifact policy

Do not commit audit outputs or cloned target repositories. The project `.gitignore` excludes local artifacts such as `runs/`, `batches/`, `*.sqlite`, scanner outputs, and Codex transcripts.

For retention guidance and a dry-run-first cleanup helper, see [`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md).

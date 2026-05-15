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
- The current implementation invokes `codex exec` for non-interactive audits. Install and configure a compatible `codex` CLI before running `--mode exec` or `--mode goal` workflows.
- `shellcheck` is required only for project validation, not for running an audit.
- If you audit private repositories, ensure the authenticated `gh` account can clone and inspect them.

## Install locally

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

## Verify the installation

From any directory, verify that the commands resolve:

```bash
gra-audit --help
gra-validate-report --help
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

## Recommended first smoke test

Before running a full AI audit, use `prepare` mode. It clones the target repository and renders prompts, but does not execute Codex.

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode prepare \
  --run-id first-prepare
```

Expected output includes an absolute audit run directory. Unless `--runs-dir` is supplied, the default location is under the install root:

```text
$GRA_HOME/runs/OWNER__REPO/first-prepare/
```

Inspect the generated context with the absolute path:

```bash
RUN_DIR="$GRA_HOME/runs/OWNER__REPO/first-prepare"
cat "$RUN_DIR/context.json"
ls "$RUN_DIR/prompts/"
```

If the target repository clones successfully and the run directory is created, proceed to a full audit.

## Run a full audit

Run a non-interactive audit with the default model and reasoning effort configured by the project:

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec
```

Or set model and effort explicitly:

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

To audit a specific branch or ref:

```bash
gra-audit \
  --repo OWNER/REPO \
  --branch main \
  --mode exec
```

By default, output is written under the install root, not the caller's current directory:

```text
$GRA_HOME/runs/OWNER__REPO/RUN_ID/
```

Where `RUN_ID` is a UTC timestamp plus process identifiers unless `--run-id` is provided. Use the exact absolute run directory printed by `gra-audit` in follow-up commands.

## Review the results

After the audit completes, locate the run directory printed by `gra-audit`. The key files are:

```text
$GRA_HOME/runs/OWNER__REPO/RUN_ID/
  context.json
  repo/                 # cloned target repository; treat as untrusted input
  reports/
    AUDIT_SUMMARY.md
    FINDINGS.md
    findings.json
    issue-drafts/
  codex-final.md
  codex-events.jsonl
  report-validation.txt
```

Run validation manually if needed:

```bash
RUN_DIR="$GRA_HOME/runs/OWNER__REPO/RUN_ID"  # replace RUN_ID with the actual value printed by gra-audit
gra-validate-report --run "$RUN_DIR"
```

Generate optional local outputs:

```bash
gra-dashboard --run "$RUN_DIR"
gra-sarif --run "$RUN_DIR"
gra-store --run "$RUN_DIR"
```

Review `reports/FINDINGS.md`, `reports/findings.json`, and `reports/issue-drafts/` before taking action. Treat AI output as analysis that requires human verification.

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
| `Missing required command: codex` | `codex --help` | Install and configure a compatible Codex CLI. |
| No reports are produced | `codex-final.md`; `codex-stderr.txt` | Inspect the run directory for model, auth, or sandbox errors. |
| Report validation fails | `report-validation.txt`; `reports/findings.json` | Fix or regenerate invalid report data before creating issues. |
| Another audit is already running | `runs/.locks/` | Wait for the current audit or use `--no-lock` only when you are sure no conflicting run exists. |

## Local artifact policy

Do not commit audit outputs or cloned target repositories. The project `.gitignore` excludes local artifacts such as `runs/`, `batches/`, `*.sqlite`, scanner outputs, and Codex transcripts.

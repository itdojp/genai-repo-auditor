# Worktree separation for maintenance and audit artifacts

GenAI Repo Auditor work should keep auditor maintenance changes separate from
local audit artifacts and target-repository updates. This reduces the risk of
committing generated reports, scanner output, or unrelated local edits while an
audit is in progress.

## Standard workspace layout

Use a workspace-root layout and keep all repositories, worktrees, and local
agent state under that root:

```text
/workspace/genai-repo-auditor/
  repos/
    genai-repo-auditor/                 # primary checkout; do not mix audit artifacts here
    TARGET_REPO/                        # optional managed target checkout
  worktrees/
    genai-repo-auditor/
      issue-121-worktree-separation/    # auditor maintenance worktree
    TARGET_REPO/
      audit-artifact-update/            # target/audit artifact worktree when needed
  runs/                                 # local audit runs; never commit wholesale
  batches/                              # local batch audit artifacts
  .codex-local/
    TASK_LEDGER.md                      # active plan, purpose, evidence, next step
    WORKDIR_POLICY.md                   # local workspace policy, not committed
```

Recommended purpose labels:

- `auditor-maintenance`: changes to `bin/`, `lib/`, `templates/`, `prompts/`,
  `docs/`, `tests/`, `scripts/`, workflow files, or repository metadata.
- `audit-artifact-update`: local run output, report fixtures, redacted test
  fixtures, or generated artifacts that are intentionally curated for tests.
- `target-remediation`: changes to a target repository under a separate target
  repository worktree. Do not mix this with auditor maintenance.

## Task ledger entry

Record the active worktree purpose before changing files. A minimal task-ledger
entry should include:

```markdown
- Active worktree: `worktrees/genai-repo-auditor/issue-121-worktree-separation`
- Purpose: `auditor-maintenance`
- Branch/ref: `codex/issue-121-worktree-separation`
- Allowed prefixes: `bin/`, `lib/`, `docs/`, `tests/`, `templates/`, `prompts/`
- Explicitly out of scope: `runs/`, `batches/`, scanner raw outputs, target repo source
```

For audit artifact updates, use a different worktree and record the exact local
artifact paths that are intentionally in scope. Generated real audit findings,
scanner raw output, API keys, tokens, and secrets must remain local-only.

## Final check

Run `gra-worktree-check` before committing or before final handoff to classify
current changes. For auditor maintenance:

```bash
bin/gra-worktree-check \
  --repo worktrees/genai-repo-auditor/issue-121-worktree-separation \
  --purpose auditor-maintenance \
  --allowed-prefix bin \
  --allowed-prefix lib \
  --allowed-prefix docs \
  --allowed-prefix tests \
  --allowed-prefix templates \
  --allowed-prefix prompts \
  --out-md .codex-local/tmp/worktree-final-check.md
```

The report contains:

- active worktree purpose and branch/head
- allowed prefixes used for the check
- in-scope changes
- unrelated changes
- a task-ledger snippet for evidence tracking

`gra-worktree-check` exits with status `1` when unrelated changes are present so
maintainers can decide whether to move them to the correct worktree, leave them
uncommitted, or explicitly expand the allowed-prefix list.

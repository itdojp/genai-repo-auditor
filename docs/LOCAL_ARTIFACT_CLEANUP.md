# Local artifact cleanup

GenAI Repo Auditor is local-first. Audit runs, cloned target repositories, scanner outputs, Codex transcripts, issue drafts, SARIF files, dashboards, and SQLite stores can contain sensitive security context. Keep them out of Git and remove them when the operational retention period ends.

## What may be retained locally

Common local artifacts include:

- `runs/OWNER__REPO/RUN_ID/`
  - cloned target repository under `repo/`
  - generated prompts under `prompts/`
  - Codex event streams, stderr, and final messages
  - reports, issue drafts, dashboards, SARIF files, and scanner leads
- `runs/_batches/BATCH_ID/`
  - batch input normalization, logs, per-repository status, and result summaries
- `runs/security-audit.sqlite`
  - locally stored finding snapshots
- `batches/`
  - legacy or operator-created batch scratch artifacts
- raw scanner files such as `semgrep.json`, `gitleaks.json`, `trivy.json`, and `codeql-results.sarif`

Treat all of these as sensitive unless a human reviewer has confirmed that they contain no private repository context, credentials, vulnerability details, or disclosure-sensitive evidence.

## Retention guidance

- Define a short local retention window before starting a recurring audit process.
- Keep artifacts only as long as they are needed for validation, remediation tracking, or approved reporting.
- Archive externally only through an approved secure process; do not copy local audit runs into Git.
- Review GitHub Issue drafts before publication and delete rejected drafts with the containing run.
- Prefer deleting whole run directories after the findings have been validated, exported, or intentionally stored.
- Rotate or remove SQLite stores if they contain obsolete findings for repositories that no longer need active tracking.

## Dry-run cleanup command

Use the cleanup helper from the repository root. It defaults to dry-run and prints the exact local artifacts it would remove:

```bash
python3 scripts/clean-local-artifacts.py
```

Example output:

```text
DRY RUN: would remove local artifacts:
- dir: runs/OWNER__REPO/RUN_ID
- dir: runs/_batches/BATCH_ID
- file: runs/security-audit.sqlite

No files were removed. Re-run with --apply after reviewing the list.
```

The helper intentionally scopes cleanup to directories under the current repository root:

- `--runs-dir` defaults to `runs`
- `--batches-dir` defaults to `batches`
- `--skip-batches` excludes the legacy `batches/` directory
- `--apply` performs deletion after the dry-run list has been reviewed

## Apply cleanup

After reviewing the dry-run output:

```bash
python3 scripts/clean-local-artifacts.py --apply
```

To clean a non-default runs directory that is still under this repository:

```bash
python3 scripts/clean-local-artifacts.py --runs-dir .test-tmp/example-runs --skip-batches
```

## Safety properties

The helper is deliberately conservative:

- dry-run is the default;
- repository root itself is never a valid cleanup target;
- cleanup roots must stay under the current repository root;
- symlinked cleanup roots and symlinked candidates are refused;
- active lock files under `runs/.locks/` are not removed;
- deletion never follows symlinks;
- missing `runs/` or `batches/` directories produce `No local artifacts found.`

If your operational runs directory is outside this repository, do not bypass these guards. Review and remove those artifacts with your organization-approved secure cleanup process.

## Scanner outputs and transcripts outside runs

The cleanup helper removes run directories, batch directories, and SQLite stores under `runs/`. If you keep raw scanner outputs or Codex transcripts elsewhere, review them manually before deletion. The project `.gitignore` excludes common names, but ignored files can still contain sensitive data and should not be treated as harmless.

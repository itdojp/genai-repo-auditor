# Remediation workflow

This runbook explains how to move from validated findings to remediation
planning with GenAI Repo Auditor. It covers draft remediation candidates and
local patch validation only; it does not authorize autonomous patching, pushing,
PR creation, releases, or production changes.

## Remediation principles

- Findings must be reviewed before remediation work starts.
- Remediation candidates are drafts and require human review.
- Generated diffs remain local unless explicitly approved for sharing.
- Validation uses disposable local workspaces and bounded commands.
- Issue creation and remediation publication are separate approval steps.

See [`REMEDIATION_CANDIDATES.md`](REMEDIATION_CANDIDATES.md) for the report
contract and [`SANDBOX_PROFILES.md`](SANDBOX_PROFILES.md) for executable sandbox
profiles.

## When remediation candidates are allowed

Allow `gra-remediate` when all conditions are true:

```text
- The finding is in scope and has a reviewed severity/confidence/status.
- The repository owner or customer contact allows remediation planning.
- The target repository is a local clone under the run directory.
- The operator can review candidate diffs before any external sharing.
- No dependency installation, network access, credential access, or live service probing is required.
```

Do not generate remediation candidates for out-of-scope repositories, findings
that are only scanner leads, or issues that require product/security policy
decisions before code changes.

## Candidate generation

Generate draft candidates for selected findings:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Expected local outputs:

```text
reports/remediation/SEC-001/remediation-candidates.json
reports/remediation/SEC-001/PATCH-001.diff
reports/remediation/SEC-001/PATCH-001.md
```

Candidate generation must not apply patches to the original target checkout and
must not create PRs.

## Human review of candidates

Before validation, review:

```text
- finding ID and fingerprint
- files_touched list
- whether the candidate is minimal and understandable
- whether the diff is bounded to repository files
- whether the candidate avoids secrets, exploit payloads, generated code blobs, and unrelated refactors
- whether the candidate has an explicit limitation note
```

Reject or rewrite candidates that are broad, speculative, or not tied to a
validated finding.

## Patch validation ladder

Use `--validate` only with operator-supplied safe local Python commands. The
patch is applied to a disposable workspace, not the original `repo/` checkout.

```bash
gra-remediate \
  --run runs/OWNER__REPO/RUN_ID \
  --finding SEC-001 \
  --validate \
  --sandbox-profile local-test \
  --build-command "python3 -m py_compile repo/app.py" \
  --test-command "python3 -m py_compile repo/app.py"
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Replace `repo/app.py` with project-specific safe local paths. If no bounded local
build/test command exists, do not invent one. Leave the candidate as
`needs-human-review` and document the limitation.

## Validation outcomes

| Outcome | Meaning | Operator action |
|---|---|---|
| `validated` | Patch applied in disposable workspace and supplied build/test commands passed | Human may consider sharing remediation summary or opening a separate remediation PR outside this audit workflow |
| `needs-human-review` | Patch may apply, but validation is incomplete or no command was supplied | Do not claim the fix is validated; route to owner review |
| `failed` | Patch did not apply or a supplied command failed | Do not publish as a recommended fix without revision |
| `rejected` | Scope, command, or safety checks rejected the candidate | Revise or discard the candidate |

`gra-issues --plan --require-advanced-validation` treats failed or
needs-human-review patch validation as a blocker/warning for publication.

## Customer or owner handoff

Share only bounded remediation guidance unless the recipient explicitly approved
receiving patch diffs:

```text
- Finding ID and title
- Affected component
- Remediation objective
- Candidate status and validation status
- Files touched summary
- Commands used for local validation
- Limitations and required owner decisions
```

Do not include raw private code, full local proof payloads, chain details, or
unapproved patch diffs in public Issues.

## What remediation workflow must not do

```text
- Push branches or tags
- Open pull requests
- Create GitHub Issues
- Apply patches to the original target checkout
- Install dependencies
- Access external networks
- Probe production or staging systems
- Extract or rotate credentials
- Generate exploit payloads
- Hide validation failures
```

If remediation needs a PR, perform that in a separate repository-specific change
workflow after owner approval. Keep the audit run as evidence and planning
material, not as an autonomous patching system.

## Cleanup

Remediation artifacts can contain sensitive code context. Include them in the
run retention window and cleanup process:

```bash
python3 scripts/clean-local-artifacts.py
python3 scripts/clean-local-artifacts.py --apply
```

See [`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md).

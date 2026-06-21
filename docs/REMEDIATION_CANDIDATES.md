# Remediation Candidates

Remediation candidates are local/private, draft-only patch proposals for existing findings. They are intended to help an operator or maintainer review a minimal remediation direction before any separate implementation workflow applies changes.

`gra-remediate` does not apply patches, modify the audited target checkout, push branches, open pull requests, create GitHub Issues, install dependencies, access the network, or execute target code.

## Workflow phases

1. **Selection phase**: choose one finding with `--finding SEC-001` or all Critical/High findings in Confirmed, Probable, or Potential status with `--all-critical-high`.
2. **Draft phase**: create subject seed JSON and a remediation prompt. In `exec` mode, Codex may write draft artifacts under `reports/remediation/`.
3. **Patch validation phase**: optionally run the draft patch through a conservative local validation ladder in a disposable workspace.
4. **Review phase**: a human reviews the patch, validation report, notes, limitations, and expected validation plan. Applying or publishing the patch remains out of scope for this command.

## Command examples

Prepare a supervised goal prompt:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

Run the draft generation prompt in non-interactive exec mode:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode exec
```

Prepare candidates for all Critical/High findings that are not invalidated:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
```

Validate an existing candidate patch in a disposable local workspace:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --validate \
  --sandbox-profile local-test \
  --build-command "python3 -m py_compile repo/app.py" \
  --test-command "python3 -m unittest discover -s repo/tests"
```

## Artifacts

The workflow writes local artifacts under `reports/remediation/`:

```text
reports/remediation/remediation-candidates.json
reports/remediation/REMEDIATION_CANDIDATES.md
reports/remediation/SEC-001/subject.json
reports/remediation/SEC-001/patch.diff
reports/remediation/SEC-001/notes.md
reports/remediation/SEC-001/patch-validation.json
reports/remediation/SEC-001/patch-validation.md
```

`remediation-candidates.json` is the machine-readable handoff. Each candidate remains draft-only:

```json
{
  "id": "PATCH-001",
  "finding_id": "SEC-001",
  "status": "draft",
  "safe_by_design": true,
  "patch_file": "reports/remediation/SEC-001/patch.diff",
  "summary": "Use a fixed allowlist before processing untrusted input.",
  "files_touched": ["repo/app.py"],
  "expected_validation": ["targeted tests", "safe proof replay"],
  "limitations": ["patch was not applied or executed"],
  "requires_human_review": true
}
```

The Markdown summary is for local review. Issue publication plans may record that a candidate exists, but must not embed the full diff.

## Candidate contract validation

When remediation artifacts exist, validate them with:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Validation checks that:

- every candidate references an existing finding;
- candidate IDs use the `PATCH-001` style;
- status is always `draft`;
- `safe_by_design` and `requires_human_review` are both `true`;
- patch, notes, and subject paths stay under `reports/remediation/`;
- patch files use `.diff` and are regular files;
- `files_touched` are relative repository paths.

## Patch validation ladder

`gra-remediate --validate` validates existing draft patches, not new findings. It:

1. checks sandbox readiness with an executable sandbox profile such as `local-test`;
2. copies the target checkout to a disposable workspace under the run directory;
3. reviews the patch diff paths against the target repository prefix and the candidate `files_touched` list, rejecting VCS metadata paths such as `repo/.git/`;
4. applies the patch to the disposable copy only;
5. runs explicitly supplied Python build and targeted test commands with an injected Python no-network guard;
6. records safe proof replay and adversarial review status as not applicable / not run unless an explicit replay stage is added in a later workflow;
7. removes the disposable workspace and writes `patch-validation.json` plus `patch-validation.md`.

The patch validation report includes:

```json
{
  "patch_id": "PATCH-001",
  "finding_id": "SEC-001",
  "sandbox_profile": "local-test",
  "patch_applied": true,
  "build_status": "passed",
  "test_status": "passed",
  "safe_proof_replay_status": "not-applicable",
  "adversarial_review_status": "not-run",
  "diff_scope_status": "bounded",
  "final_status": "validated"
}
```

Validation returns exit status `1` when a candidate fails the ladder and still writes a local report with the failure reason. If either a build command or a test command is not configured, the patch can apply successfully but the final status remains `needs-human-review` rather than `validated`. `gra-issues --plan --require-advanced-validation` accounts for patch validation status when present, including failed or needs-human-review validation as a blocking warning.

## Safety boundaries

- Draft patch only.
- Do not apply the patch to the original target checkout in place.
- Do not push, open pull requests, create issues, releases, or tags.
- Do not install dependencies or access the network.
- Do not execute target code, tests, proof helpers, or the candidate patch during candidate generation.
- Execute build/test commands only in the `--validate` stage, only in the disposable workspace, and only when the operator supplies bounded Python commands.
- Do not include exploit payloads, weaponized instructions, credential extraction, or live-service probing.
- Prefer minimal diffs and explicit limitations.

## Related docs

- [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md)
- [`docs/REPORT_CONTRACT.md`](REPORT_CONTRACT.md)
- [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md)
- [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md)
- [`docs/SANDBOX_PROFILES.md`](SANDBOX_PROFILES.md)

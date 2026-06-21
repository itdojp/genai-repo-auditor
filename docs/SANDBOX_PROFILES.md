# Sandbox Profiles

Sandbox profiles describe the runtime boundary expected before any workflow executes target repository code, candidate patches, generated proof helpers, or future remediation validation commands.

Source review and report generation remain local-first and source-only. They do not require Docker, Podman, gVisor, or a VM. Executable validation is different: it must be tied to an explicit profile and fail closed when the profile is not ready.

## Profiles

| Profile | Executes target code | Current status | Intended use |
|---|---:|---|---|
| `source-only` | No | Supported | Recon, target planning, report validation, issue planning, and other read-only/source-only workflows. |
| `local-test` | Yes | Diagnostic contract | Future local disposable workspace test runs. Does not require Docker/Podman, but reports readiness warnings. |
| `container` | Yes | Diagnostic contract | Future containerized build/test validation. Requires Docker or Podman. |
| `gvisor` | Yes | Diagnostic contract | Future hardened container profile. Requires Docker/Podman plus `runsc`. |
| `vm` | Yes | Contract only | Future VM isolation. VM orchestration is not implemented in this release. |

## Phase separation

Use the profiles across three phases:

1. **Setup phase**: install optional runtimes, prepare disposable workspaces, and decide whether network access is disabled or explicitly allowed. Do not execute target code during setup.
2. **Freeze phase**: record the run directory, target repository state, selected sandbox profile, network policy, and credential exposure checks in `reports/sandbox-readiness.json`.
3. **Validation phase**: execute target code only after an executable profile is ready and approved by the operator.

The default network policy is `disabled`. If an executable validation workflow later needs network access, that workflow must make the policy explicit and document the approval reason. This issue does not add network execution.

## Readiness command

Check source-only readiness for report-only workflows:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile source-only
```

Check a future local executable profile:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile local-test
```

Check a future container profile and fail closed when Docker/Podman is unavailable:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile container --executable-workflow
```

The command writes:

```text
reports/sandbox-readiness.json
reports/SANDBOX_READINESS.md
```

The JSON report records bounded metadata only: profile id, run id, repository name, network policy, readiness status, and check summaries. It must not include secret values. Credential checks record only common credential path names or environment variable names when they appear visible.

## Shared helper

Future executable workflows can call `lib/sandbox_profiles.py`:

```python
from sandbox_profiles import enforce_sandbox_profile

enforce_sandbox_profile(
    run_dir=run_dir,
    profile_id="container",
    executable_workflow=True,
    network_policy="disabled",
)
```

`enforce_sandbox_profile` raises `SandboxProfileError` when required checks fail. This gives future remediation candidate or validation-ladder commands a single fail-closed gate without executing target code in this release.

## Safety boundaries

- Do not run target code under `source-only`.
- Do not mount credentials into executable validation workspaces.
- Do not allow network access unless the workflow explicitly records and approves that policy.
- Treat generated readiness reports as local operational artifacts.
- Missing Docker/Podman must not block source-only review, report generation, or issue planning.

## Related docs

- [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md)
- [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md)
- [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md)
- [`docs/TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md)

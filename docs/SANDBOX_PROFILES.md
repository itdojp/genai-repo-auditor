# Sandbox Profiles

Sandbox profiles describe the runtime boundary expected before any workflow executes target repository code, candidate patches, generated proof helpers, or remediation validation commands.

Source review and report generation remain local-first and source-only. They do not require Docker, Podman, gVisor, or a VM. Executable validation is different: it must be tied to an explicit profile and fail closed when the profile is not ready.

## Profiles

| Profile | Executes target code | Current status | Intended use |
|---|---:|---|---|
| `source-only` | No | Supported | Recon, target planning, report validation, issue planning, and other read-only/source-only workflows. |
| `local-test` | Yes | Diagnostic contract | Local disposable workspace patch validation and test runs. Does not require Docker/Podman, but reports readiness warnings. |
| `container` | Yes | Scanner execution supported; target-code validation diagnostic | Bounded offline `gra-scan --execute`; future containerized build/test validation. Requires local Docker or Podman. |
| `gvisor` | Yes | Scanner execution supported when configured; target-code validation diagnostic | Bounded offline `gra-scan --execute` with `runsc`; future hardened build/test validation. |
| `vm` | Yes | Contract only | Future VM isolation. VM orchestration is not implemented in this release. |

Platform runtime selection is narrower than profile availability. Native
Windows container execution is experimental and uses local Docker Desktop with
Linux containers; native Podman and gVisor are unsupported. WSL2 follows the
Linux boundary and supports local Docker/Podman, with gVisor only when `runsc`
is configured. macOS execution selects local Docker. See
[`WINDOWS_WSL_SUPPORT.md`](WINDOWS_WSL_SUPPORT.md).

The generic sandbox profile report and scanner execution readiness report are
separate contracts. `gra-sandbox-check` describes whether a profile is suitable
for a broader executable workflow and does not run Docker/Podman. `gra-scan
--readiness` is the explicit scanner gate: it verifies the current run layout,
offline policy, credential/remote-runtime environment, local runtime health, and
presence of the exact digest-pinned scanner image. A successful generic
`sandbox-readiness.json` does not substitute for scanner readiness, and a saved
scanner readiness report does not authorize arbitrary target-code execution.
Run-layout checks also require an unused, non-symlink raw output path and a
staging path that is absent or a non-symlink directory. They inspect path
metadata only, not target, output, or staging content.

## Phase separation

Use the profiles across three phases:

1. **Setup phase**: install optional runtimes, prepare disposable workspaces,
   and decide whether network access is disabled or explicitly allowed. For an
   approved scanner, a human reviews the exact SHA-256 image digest and performs
   the network-enabled `docker pull IMAGE@sha256:...` or `podman pull
   IMAGE@sha256:...` here. Do not execute target code, use a mutable tag, or
   automate the pull as a readiness/execution fallback.
2. **Freeze phase**: disable setup network access, remove remote-runtime and
   credential-like environment variables, and record the run directory, target
   repository state, selected profile, network policy, and credential exposure
   checks in `reports/sandbox-readiness.json`. For scanner execution, also run
   `gra-scan --readiness`; it writes
   `<reports_dir>/scanner-readiness/<adapter_id>.json` without pulling/running a
   scanner or inspecting target content.
3. **Validation phase**: execute target code only after the applicable
   executable profile and current scanner readiness gate are ready and approved
   by the operator. `gra-scan --execute` re-evaluates readiness rather than
   trusting a potentially stale saved report.

The default network policy is `disabled`. If an executable validation workflow later needs network access, that workflow must make the policy explicit and document the approval reason. This issue does not add network execution.

## Readiness command

Check source-only readiness for report-only workflows:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile source-only
```

Check a local executable profile:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile local-test
```

Check container-profile readiness and fail closed when Docker/Podman is unavailable:

```bash
gra-sandbox-check --run runs/OWNER__REPO/RUN_ID --profile container
```

Profiles other than `source-only` are executable profiles, so they fail closed
by default when required readiness checks are unavailable. Use
`--executable-workflow` when a higher-level command wants to explicitly assert
that target-code execution is being requested; using it with `source-only`
intentionally fails.

The command writes:

```text
reports/sandbox-readiness.json
reports/SANDBOX_READINESS.md
```

The JSON report records bounded metadata only: profile id, run id, repository name, network policy, readiness status, and check summaries. It must not include secret values. Credential checks record only common credential path names or environment variable names when they appear visible.

### Scanner-specific readiness

After the separately approved human pull, check one adapter and execution
profile explicitly:

```bash
gra-scan --run runs/OWNER__REPO/RUN_ID \
  --tool gitleaks \
  --readiness \
  --sandbox-profile container \
  --network-policy disabled \
  --json
```

This command may run only bounded local runtime `version` and digest-pinned
`image inspect` probes. Each probe has a timeout, consumes only its return code,
and discards stdout/stderr. It does not run a scanner/container, pull an image,
access the network, or inspect target file content. Remote endpoint
configuration and the configured credential-like environment names block the
gate. The report contains no absolute local paths, endpoint/environment values,
or daemon output. Its `paths` group exposes only safety booleans, including
`output_safe` and `staging_safe`; failures use `output_path_unsafe` or
`staging_path_unsafe` and suppress runtime probes. Its runtime group separately
records whether a candidate was found and, as `healthy_available`, whether any
bounded version probe succeeded; this does not mean the image is local. See
[`SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md) for the complete
state/reason/exit-code contract and exact release image digests.

Scanner readiness can diagnose every declared profile/network choice without
executing it. Only `container`/`gvisor` with network policy `disabled` can pass;
`source-only`, `local-test`, `vm`, or `explicit-allow` produce bounded blocked
reports and suppress runtime probes. Linux and confirmed WSL2 are supported with
local Docker/Podman; native Windows and macOS local-Docker paths are
experimental; `gvisor` requires `runsc` on Linux/WSL2. WSL1, unconfirmed WSL,
remote runtimes, native-Windows Podman, and gVisor outside Linux/WSL2 cannot pass.

The saved report is reused as bounded metadata only: plan copies its
state/reasons without probing only when the requested sandbox profile and
network policy exactly match the report; otherwise plan reports `not_checked`.
Execute re-evaluates the current gate. `gra-doctor` can call the same evaluator
in memory only with `--scanner-run`, `--scanner-tool`, and
`--probe-external-tools`, and metrics/dashboard aggregate state/reason counts
without copying report paths, values, runtime output, or target content.

## Shared helper

Executable workflows, including patch validation, can call `lib/sandbox_profiles.py`:

```python
from sandbox_profiles import enforce_sandbox_profile

enforce_sandbox_profile(
    run_dir=run_dir,
    profile_id="container",
    executable_workflow=True,
    network_policy="disabled",
)
```

`enforce_sandbox_profile` raises `SandboxProfileError` when required checks fail. Patch validation uses the same readiness contract before applying candidate patches in a disposable workspace.

## Safety boundaries

- Do not run target code under `source-only`.
- Do not mount credentials into executable validation workspaces.
- Remove configured credential-like environment variables before scanner
  readiness/execution; name-only reporting is not approval to pass them through.
- Do not allow network access unless the workflow explicitly records and approves that policy.
- Do not pull scanner images during readiness or execution. Pull the reviewed
  digest explicitly during the human-controlled setup phase.
- Treat generated readiness reports as local operational artifacts.
- Missing Docker/Podman must not block source-only review, report generation, or issue planning.

## Related docs

- [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md)
- [`docs/SAFE_LOCAL_PROOFS.md`](SAFE_LOCAL_PROOFS.md)
- [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md)
- [`docs/TRACE_REACHABILITY.md`](TRACE_REACHABILITY.md)

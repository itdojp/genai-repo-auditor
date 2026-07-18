# Windows, WSL2, and PowerShell support

This document defines the tested execution boundary for native Windows,
WSL2, Linux, and macOS. “Supported” means the repository has an implementation
and an applicable automated test. It does not imply that every external worker,
container runtime, filesystem, or credential store is supported.

Do not weaken path containment, symlink rejection, atomic publication, sandbox,
network, or disclosure controls to make an unsupported operation run. Use WSL2
when native Windows cannot preserve a required POSIX safety primitive.

## Support matrix

| Workflow | Native Windows | WSL2 | Linux | macOS |
|---|---|---|---|---|
| Wheel / virtual-environment install and packaged resources | Supported; Windows/Python 3.10–3.12 install matrix | Linux boundary | Supported; Python 3.10–3.12 | Supported; Python 3.10–3.12 |
| `pipx` install | Experimental installer path; CI smoke is Linux-only | Linux boundary | Supported and CI-smoked | Experimental installer path; not separately CI-smoked |
| `uv tool` install | Experimental installer path; not CI-smoked | Experimental; not CI-smoked | Experimental; not CI-smoked | Experimental; not CI-smoked |
| `gra-doctor` and resource discovery | Supported and CI-tested | Supported as Linux; WSL is detected | Supported and CI-tested | Supported and CI-tested |
| `gra-audit --mode prepare` | Supported and CI-tested with PowerShell paths | Supported as Linux | Supported and CI-tested | Supported and CI-tested |
| `gra-run` plan / execute / bounded range / failure / resume | Orchestration is supported and CI-tested with an offline worker fixture | Supported as Linux | Supported and CI-tested | Supported and CI-tested |
| `gra-efficacy-benchmark --list` / `--list-configurations` | Supported | Supported | Supported | Supported |
| Deterministic efficacy report / comparison generation | Inspection only; fails closed before output because required dirfd operations are unavailable in CPython | Supported in the WSL filesystem | Supported | Supported |
| Optional efficacy worker comparison | Not supported because safe final report publication is unavailable; use WSL2 | Supported subject to the configured compatible worker and host isolation | Supported subject to worker prerequisites | Supported subject to worker prerequisites |
| `gra-scan --plan` | Supported and CI-tested; no scanner runs | Supported | Supported | Supported |
| `gra-scan --readiness --sandbox-profile container` | Experimental local Docker Desktop/Linux-container path; bounded local named-pipe probes only | Linux implementation boundary with local Docker/Podman; no dedicated WSL2 runtime CI | Supported local Docker/Podman boundary with mocked-runtime safety tests | Experimental local Docker path; no real-runtime CI |
| `gra-scan --execute --sandbox-profile container` | Experimental: local Docker Desktop with Linux containers only; no CI container execution | Linux implementation boundary; no dedicated WSL2 or real-container CI | Supported with mocked-runtime safety tests; real containers are not started in CI | Experimental local Docker path; no real-container CI |
| `gra-scan --execute --sandbox-profile gvisor` | Not supported | Supported only when Linux `runsc` is configured | Supported only when `runsc` is configured | Not supported |

The native-Windows `gra-run` test exercises installed console scripts,
PowerShell path handling, plan output, `--until recon`, checkpoint inspection,
resume without repeating successful stages, a target-stage failure, and recovery
from that checkpoint. It uses deterministic mocked repository and worker
commands and does not perform an audit or access a network. A real worker-backed
stage additionally depends on the selected worker's native-Windows support.

GitHub-hosted CI does not provide a dedicated WSL2 runner. WSL2 claims are the
Linux implementation boundary plus explicit environment detection; they are
not evidence of a separate WSL2 end-to-end run. Scanner CI uses deterministic
runtime mocks and never starts or pulls a real scanner container on any OS.

WSL2 is treated as Linux, not as native Windows. Keep repositories, run
directories, worker directories, and scanner staging under the WSL filesystem
(for example `~/work`), rather than `/mnt/c`, to avoid cross-filesystem
permission, symlink, case-sensitivity, and atomic-operation differences.
WSL1 is not in the tested support matrix. If `gra-doctor` reports
`wsl-unknown`, verify or upgrade the distribution to WSL2 before relying on the
Linux support boundary.

## PowerShell installation and paths

Use normal PowerShell argument arrays and quoted variables. Do not copy Bash
`export`, command substitution, or line-continuation syntax into PowerShell.

```powershell
$GraHome = Join-Path $HOME ".local\opt\genai-repo-auditor"
$RunsDir = Join-Path $HOME ".local\state\genai-repo-auditor\runs"

gra-doctor --json --runs-dir $RunsDir
gra-audit --repo OWNER/REPO --mode prepare --run-id first-audit --runs-dir $RunsDir
$RunDir = Join-Path $RunsDir "OWNER__REPO\first-audit"
gra-run --run $RunDir --profile recon-only
```

`pipx`, `uv tool`, and virtual-environment examples are in
[`LOCAL_INSTALL_AND_AUDIT.md`](LOCAL_INSTALL_AND_AUDIT.md). Confirm that the
selected tool's script directory is on `PATH` before diagnosing a missing
`gra-*` command.

## GitHub CLI authentication and token precedence

For `github.com`, GitHub CLI evaluates `GH_TOKEN` before `GITHUB_TOKEN`; either
environment variable takes precedence over stored credentials. This order is
defined by the [GitHub CLI environment manual](https://cli.github.com/manual/gh_help_environment).
A stale variable can therefore make `gh auth status` or repository access fail
even when the Windows credential store or another keyring contains valid auth.

Inspect names and authentication state without printing token values:

```powershell
Get-ChildItem Env:GH_TOKEN,Env:GITHUB_TOKEN -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty Name
gh auth status --hostname github.com
gra-doctor --probe-external-tools --json --runs-dir $RunsDir
```

`gra-doctor` reports only the present variable names and the effective name. It
never emits values. Its active `gh auth status` probe removes credential-like
environment variables so that stored authentication can be checked separately;
normal `gh` commands still apply the documented environment precedence.

If a variable is stale and is not intentionally supplied by CI, clear it in the
current PowerShell process and recheck. Do not echo it first.

```powershell
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh auth status --hostname github.com
```

## Efficacy benchmark boundary

Native Windows may list cases and configurations but report generation exits
with status `2` before creating either report:

```powershell
gra-efficacy-benchmark --list
gra-efficacy-benchmark --list-configurations
gra-efficacy-benchmark --out-json .test-tmp\efficacy.json --out-md .test-tmp\EFFICACY.md
```

The final command reports that safe writes require dirfd support and recommends
WSL2/Linux/macOS. Do not bypass this check or replace it with a weaker
check-then-write implementation.

## Container scanner boundary

Planning is non-executing on every supported OS:

```powershell
gra-scan --run $RunDir --tool gitleaks --plan --sandbox-profile container --json
```

Image retrieval is a separate human-controlled setup phase. After reviewing the
adapter and exact release digest, authorize registry network access and pull the
immutable reference explicitly. For PowerShell and local Docker Desktop:

```powershell
$GitleaksImage = "ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
$SyftImage = "ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb"

# Human-approved, network-enabled setup phase only.
docker pull $GitleaksImage
docker pull $SyftImage
```

Do not replace the digest with a mutable tag, or automate a pull from readiness
or execution. After setup, disable registry/network access and remove unintended
remote-runtime or credential-like variables from the current process without
printing their values. Then run the scanner-specific gate:

```powershell
gra-scan --run $RunDir --tool gitleaks --readiness --sandbox-profile container --network-policy disabled --json
```

Readiness does not execute a scanner/container, pull an image, access the
network, or inspect target file content. It checks bounded run/path metadata and
may run only a local runtime `version` probe and digest-pinned `image inspect`,
with timeouts and discarded stdin/stdout/stderr. Its report is written to
`<reports_dir>/scanner-readiness/gitleaks.json`; it contains no runtime/scanner
absolute path, target/report absolute path, remote endpoint/environment value,
or daemon output. Remote-like `CONTAINER_HOST`, `DOCKER_CONTEXT`, `DOCKER_HOST`,
or `PODMAN_HOST` values and configured credential-like environment names block
readiness. Only their names, never their values, can appear in the report.
Path metadata also checks that the expected raw output is unused/non-symlinked
and staging is absent or a non-symlink directory; it never reads their content.
The report exposes only `output_safe`/`staging_safe` booleans and uses
`output_path_unsafe`/`staging_path_unsafe` on failure. Runtime
`healthy_available` means at least one bounded version probe succeeded; it does
not imply that the digest-pinned image is local.

`gra-scan --readiness` exits `0` for `ready`/`experimental`, `1` for
`blocked`/`unsupported`, and `2` for usage/evaluation/report failures. Native
Windows and macOS can reach only `experimental` when all checks pass; Linux and
confirmed WSL2 can reach `ready`. Unconfirmed WSL and other platforms are
`unsupported`. A later plan reuses the saved state/reason summary without
probing only when the requested sandbox profile and network policy exactly
match the report; a mismatch is `not_checked`. Execute re-evaluates the current
contract and does not trust a stale report.

Execution is always explicit, offline, and requires the digest-pinned image to
be present from the separately approved setup phase. The command keeps
`--network=none`, read-only target/root mounts, dropped capabilities, resource
limits, and bounded outputs.

- **Native Windows:** Docker Desktop must use Linux containers and expose the
  local named-pipe endpoint. Both readiness and execution are experimental and
  are not exercised with a real runtime/container in CI. Native Podman and
  gVisor execution are not supported.
- **WSL2:** use Docker Desktop WSL integration or a local Linux Docker/Podman
  runtime. Remote daemon environment variables are rejected. Keep bind-mounted
  paths in the WSL filesystem.
- **Linux:** local Docker or Podman is supported; gVisor additionally requires
  `runsc`.
- **macOS:** the local Docker path is experimental and not exercised with a
  real container in CI. Podman and gVisor are not selected by the current
  executor.

No platform support level permits external-host scanning, live service probes,
credential use, image pulls during execution, or network-enabled scanner runs.

## Diagnostics

Run the default non-executing check first:

```powershell
gra-doctor --json --runs-dir $RunsDir
```

The `platform_support` section reports the detected environment, dirfd report
write capability, and feature statuses. Add `--probe-external-tools` only after
confirming that `git` and `gh` on `PATH` are trusted. The probe does not execute
the configured worker, run an audit, inspect token values, or start a container.

To include the same bounded scanner readiness contract in doctor output, pass
the run/tool pair and the dedicated scanner-runtime probe opt-in:

```powershell
gra-doctor --json --probe-scanner-runtime `
  --scanner-run $RunDir `
  --scanner-tool gitleaks `
  --scanner-sandbox-profile container
```

The scanner result appears under `checks.scanner_execution_readiness`; doctor
does not write `<reports_dir>/scanner-readiness/`. The scanner-specific evaluator
retains the no-run/no-pull/no-network/no-target-content boundary.
`--probe-scanner-runtime` is mutually exclusive with `--probe-external-tools`:
the scanner-only route does not run `git`, `gh`, `gh auth`, or the configured
worker, and its only external commands are timeout-bounded local Docker/Podman
`version` and digest-pinned `image inspect` probes. Without `--strict`, doctor
exits `0` even when scanner readiness is blocked; `--strict` exits `1` for an
overall error, and invalid/missing option combinations exit `2`.

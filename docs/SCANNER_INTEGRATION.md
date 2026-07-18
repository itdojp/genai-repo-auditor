# Scanner Integration

## Safe local scanner planning and execution

`gra-scan` provides a versioned, static registry for approved local scanner
adapters. Its `--list` and default `--plan` modes are non-executing:
they do not run scanners or version commands, read target contents, access the
network, create output directories, or ingest results. Planning inspects only
run context and path metadata needed for containment and symlink checks.

```bash
gra-scan --run runs/OWNER__REPO/RUN_ID --list
gra-scan --run runs/OWNER__REPO/RUN_ID --list --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks
gra-scan --run runs/OWNER__REPO/RUN_ID --tool syft --plan --sandbox-profile container --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --readiness --sandbox-profile container --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --execute --sandbox-profile container --json
```

The initial offline-capable definitions are:

- `gitleaks`: read-only directory secret scanning, JSON lead output, full tool
  redaction, and later `gra-ingest --tool gitleaks` normalization;
- `syft`: read-only filesystem SBOM generation in CycloneDX JSON and later
  `gra-ingest --tool syft --format cyclonedx` dependency posture ingestion.

Each machine-readable adapter contract declares its bare executable and version
argument array, supported operating systems, network requirement, approved
sandbox profiles, read/write paths, immutable argument template, timeout and
output/result limits, ingest format, secret handling, exit semantics, and
whether the output is scanner leads, posture evidence, or SBOM data. Planning
reports binary presence but never executes the version check. The schema is
[`templates/reports/scanner-adapter.schema.json`](../templates/reports/scanner-adapter.schema.json).
Machine-readable plans use
[`templates/reports/scanner-plan.schema.json`](../templates/reports/scanner-plan.schema.json).

### Scanner execution readiness

`--readiness` is an explicit, bounded pre-execution check. It requires an
existing run and `--tool gitleaks|syft`. All declared profile choices
(`source-only`, `local-test`, `container`, `gvisor`, and `vm`) and network
choices (`disabled` and `explicit-allow`) can be evaluated so an unsafe request
produces a bounded diagnostic report rather than executing anything. Only
`container` or `gvisor` with `--network-policy disabled` can reach `ready` or
`experimental`; other declared choices are `blocked` and do not run runtime
probes. When the canonical target and reports paths are safe, distinct, and
unambiguous, the command writes the latest report for that adapter to the
configured reports directory:

```text
<reports_dir>/scanner-readiness/<adapter_id>.json
```

With the default run layout, the paths are
`reports/scanner-readiness/gitleaks.json` and
`reports/scanner-readiness/syft.json`. The closed JSON contract is
[`templates/reports/scanner-readiness.schema.json`](../templates/reports/scanner-readiness.schema.json).
One latest report is retained per approved adapter; readiness does not append a
command event. If `repo_dir` and `target_repo_dir` disagree, either path is
unsafe, or target/reports overlap, the bounded blocked report is printed but is
not persisted anywhere under the run.

Readiness does **not** execute a scanner or container, pull an image, access the
network, or inspect files in the target repository. It reads bounded run context
and path metadata only to verify containment, directory/symlink safety, and
target/report separation. It also verifies that the expected raw output path is
unused and not symlinked, and that the staging path is either absent or a real
directory rather than a symlink. These checks do not enumerate or read target,
output, or staging content. After those checks, and only when the platform,
profile, immutable image configuration, and local-endpoint policy permit it,
readiness may execute the following trusted local runtime probes:

- one `version` command for each Docker/Podman runtime candidate, with a
  10-second timeout; and
- one `image inspect <digest-pinned-image>` command for each healthy candidate
  until the image is found, with a 20-second timeout.

Docker is forced to a discovered local Unix socket or the native-Windows local
named pipe. Podman is eligible only on Linux-family hosts and is invoked with
`--remote=false`. Probe stdin is closed, stdout/stderr are discarded, and only a
return code is consumed. No daemon URL, daemon output, runtime/scanner absolute
path, target/report absolute path, remote endpoint value, or environment value
is copied into the report. The report may contain only bare tool/runtime names,
the reviewed image digest reference, fixed next-step text, and the names—not
values—of rejected environment variables.

Remote-like values in `CONTAINER_HOST`, `DOCKER_CONTEXT`, `DOCKER_HOST`, or
`PODMAN_HOST` block readiness with `runtime_remote`; no runtime probe is made in
that case. `DOCKER_CONTEXT=default`, `DOCKER_CONTEXT=desktop-linux`, and explicit
`unix://` or `npipe://` local endpoints are not classified as remote. The
configured credential environment names block readiness with
`credential_environment_present`. Detection is case-insensitive and covers the
documented provider names plus bounded credential-name suffixes such as
`*_TOKEN`, `*_SECRET`, `*_PASSWORD`, `*_API_KEY`, `*_ACCESS_KEY`,
`*_AUTH_CONFIG`, and `*_AUTH_FILE`. This includes common session, registry, and
package-manager credentials such as `AWS_SESSION_TOKEN`, `DOCKER_AUTH_CONFIG`,
`REGISTRY_AUTH_FILE`, `NPM_TOKEN`, and `PYPI_API_TOKEN`. Their values are never
read into the report or passed to probes, and their presence suppresses the
runtime `version`/`image inspect` probes. The final state remains blocked.

The top-level readiness state has the following meaning:

| State | Meaning | `gra-scan --readiness` exit |
|---|---|---:|
| `ready` | All required checks passed on Linux or confirmed WSL2. | `0` |
| `experimental` | All required checks passed on native Windows or macOS, whose container path is experimental. `reason_codes` is still `["ready"]`. | `0` |
| `blocked` | The platform is recognized, but one or more blocking reasons remain. | `1` |
| `unsupported` | The environment is outside the execution support matrix, including unconfirmed `wsl-unknown`. | `1` |

An unknown argparse choice, missing/unsafe run root, unknown adapter, or a
context/path/report failure that prevents a bounded report exits `2`. Declared
but non-executable profile/network choices instead write a blocked report and
exit `1`. Reason codes in a valid report are unique and emitted in the following
canonical order:

| Reason code | Meaning |
|---|---|
| `runtime_missing` | Neither approved local Docker nor eligible local Podman is on `PATH`. |
| `runtime_remote` | Remote runtime configuration is present; only a local endpoint is allowed. |
| `runtime_unavailable` | A candidate exists, but its bounded `version` probe did not succeed. |
| `image_not_configured` | The adapter has no reviewed immutable execution image. |
| `image_not_digest_pinned` | The image is not pinned to an exact lowercase SHA-256 digest. |
| `image_not_local` | No healthy local runtime can inspect the pinned image; readiness never pulls it. |
| `platform_unsupported` | The detected platform is outside the supported/experimental execution matrix. |
| `sandbox_unsupported` | The requested execution profile is not approved for the adapter/platform. |
| `gvisor_missing` | `gvisor` was selected but `runsc` is not on `PATH`. |
| `target_unsafe` | The target is missing, not a directory, symlinked, or outside the safe run layout. |
| `reports_path_unsafe` | The configured reports directory is missing, not a directory, symlinked, or outside the safe run layout. |
| `output_path_unsafe` | The expected raw scanner output path is already present, symlinked, or cannot be represented safely. Start with a fresh run and an unused non-symlink output path. |
| `staging_path_unsafe` | The scanner staging path is symlinked, is an existing non-directory, or cannot be represented safely. Remove or replace it during setup. |
| `path_overlap` | Target and reports directories overlap. |
| `resource_limits_unavailable` | The selected profile cannot provide the required bounded scanner limits. |
| `credential_environment_present` | A configured credential-like environment variable is present. |
| `network_policy_unsupported` | The scanner contract is not strictly offline. |
| `ready` | No blocking reason remains; this is the only reason for `ready` or `experimental`. |

The `paths` object exposes only `target_safe`, `reports_safe`, `output_safe`,
`staging_safe`, and `overlap` booleans. An unsafe output or staging result blocks
readiness and suppresses runtime probes. In `runtime`, `candidate_available`
means an approved runtime executable was found, while `healthy_available` means
at least one bounded runtime `version` probe succeeded. A healthy runtime can
still yield `image_not_local`; `selected` is set only when that runtime also
successfully inspects the digest-pinned local image.

### Human-controlled image setup

Image retrieval is a separate, network-enabled setup phase. A human operator
must review the adapter and exact digest, authorize registry access, and run the
pull explicitly. Do not put `docker pull` or `podman pull` into readiness,
planning, execution, or an automated fallback. For this release:

```bash
GITLEAKS_IMAGE='ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f'
SYFT_IMAGE='ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb'

# Choose the approved local runtime. This is the only network-enabled phase.
docker pull "$GITLEAKS_IMAGE"
docker pull "$SYFT_IMAGE"
# Or, on Linux/WSL2 with an approved local Podman installation:
# podman pull "$GITLEAKS_IMAGE"
# podman pull "$SYFT_IMAGE"
```

After the pull completes, disable setup network access, unset remote-runtime and
credential-like environment variables, and run `gra-scan --readiness`. Do not
replace the digest with a tag such as `latest`, and do not treat a successful
pull as readiness approval.

### Contract reuse

- A later default/`--plan` invocation loads the adapter's persisted readiness
  report only when its sandbox profile and network policy exactly match the
  plan, then copies only `checked`, `state`, and `reason_codes` into
  `execution_readiness`. A mismatch is reported as `not_checked`; plan does not
  rerun probes. A plan remains non-executing, and its summary may be stale.
- `--execute` does not trust the persisted report. It re-evaluates the same
  current readiness contract before container startup and proceeds only for
  `ready` or `experimental`, then retains `--pull=never` and `--network=none`.
- `gra-doctor --scanner-run RUN --scanner-tool TOOL
  --scanner-sandbox-profile container --probe-scanner-runtime` invokes the same
  scanner readiness evaluator in memory and places it under
  `checks.scanner_execution_readiness`; doctor does not write the per-run
  readiness artifact. `--scanner-run` and `--scanner-tool` are a pair, and the
  scanner route requires the explicit `--probe-scanner-runtime` opt-in. This
  dedicated route is mutually exclusive with `--probe-external-tools`, so it
  does not run doctor's separate `git --version`, `gh --version`, or `gh auth
  status` probes. Its only external commands are the same timeout-bounded local
  Docker/Podman `version` and digest-pinned `image inspect` probes used by the
  scanner evaluator.
- `gra-metrics` validates saved readiness reports and aggregates only report
  presence/count plus counts by adapter, state, and reason. `gra-dashboard`
  reuses `metrics.json` to show report count and state/reason tables. Neither
  surface copies paths, environment values, image/runtime command output, or
  target content.

Plans reject unknown adapters, source-only/local-test execution profiles, path
traversal, symlinked run paths, undeclared network access, and arbitrary shell
arguments. All planned paths are run-relative. A valid plan is not execution
approval. `--execute` is explicit and supports only the enforced `container` and
`gvisor` profiles. Execution uses local Docker or Podman, a read-only target bind
mount, a dedicated output mount, a read-only container root, dropped
capabilities, `no-new-privileges`, bounded CPU/memory/PIDs, and `--network=none`.
It never pulls an image. The operator must pre-pull the immutable image digest
during a separately authorized setup phase.

Platform boundaries are explicit: planning is supported on native Windows,
WSL2, Linux, and macOS. Readiness/execution is supported with local Docker or
Podman on Linux and confirmed WSL2. Native Windows is experimental and requires
local Docker Desktop in Linux-container mode through the local named pipe;
native Podman is not selected. macOS is experimental and selects local Docker.
The `gvisor` profile is Linux/WSL2-only when `runsc` is configured. WSL1,
unconfirmed `wsl-unknown`, and other platforms are unsupported. Remote daemon
environment configuration remains rejected. See
[`WINDOWS_WSL_SUPPORT.md`](WINDOWS_WSL_SUPPORT.md).

On an enforcing SELinux host, execution uses `label=disable` instead of
recursively relabeling the audited target. This preserves target filesystem
metadata; isolation continues to rely on the read-only target/root mounts,
dropped capabilities, default seccomp, `no-new-privileges`, resource limits,
and disabled network.

Execution rejects remote runtime environment configuration, missing runtimes or
images, configured credential-like environment variables, unsupported profiles,
any network allowance, existing/symlinked output,
timeouts, oversized output/logs, excess result counts, unexpected files, and
scanner failures. A timed-out container is force-removed. Successful raw JSON is
atomically moved to `reports/scanner-results/raw/`; timeout, SIGTERM/SIGHUP,
keyboard interruption, and failed output trigger container/staging cleanup.
Successful output is then routed through the same normalization, redaction,
scanner-index, and dependency-posture boundaries used by `gra-ingest`. The raw
artifact remains local; downstream triage uses the bounded normalized artifact
under `reports/scanner-results/normalized/`. The result remains `review-only`
and is never a confirmed or issue-recommended finding.

Each explicit execution that passes run/tool/report preflight also appends a sanitized `gra-scan` command event and
updates the following bounded reports:

```text
reports/scanner-runs.json
reports/SCANNER_RUNS.md
```

These reports contain adapter/version, immutable image digest, aggregate
status, timing, result/normalized-lead counts, and redaction counts. They do not
contain raw scanner bodies, secrets, or raw-output paths. A failed scanner run
is recorded as failed and is never interpreted as a clean scan. The JSON
contract is
[`templates/reports/scanner-runs.schema.json`](../templates/reports/scanner-runs.schema.json).
To preserve immutable evidence references, an adapter may complete successfully
only once per run directory. Use a fresh run directory for a repeat execution;
do not delete and reuse historical raw or normalized artifact paths.

Approved scope is local repository SAST/SCA/secret scanning and SBOM generation.
DAST, live endpoint probing, external-host scanning, brute force, credential
use, and production/staging access remain prohibited.

## Ingest existing scanner output

The lab can ingest scanner outputs and ask Codex to triage them in repository context.

Supported by convention:

```text
semgrep
gitleaks
trivy
grype
checkov
codeql
scorecard
sbom
custom
```

The ingest command does not run scanners. It copies existing scanner output into the run directory
and creates a bounded, redacted normalized lead file for triage.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
```

Ingested files are indexed under `reports/scanner-results/scanner-index.json`.
Each index entry keeps the raw local artifact path in `path` and a redacted lead
artifact in `normalized_path`, for example:

```json
{
  "tool": "gitleaks",
  "path": "reports/scanner-results/gitleaks-<hash>.json",
  "normalized_path": "reports/scanner-results/normalized/gitleaks-<hash>-leads.json",
  "normalized_leads_count": 1
}
```

Normalized leads use bounded evidence and secret redaction:

```json
{
  "tool": "gitleaks",
  "rule_id": "generic-api-key",
  "severity": "high",
  "path": "src/config.ts",
  "line": 42,
  "redacted_evidence": "sk_live_...abcd",
  "fingerprint": "...",
  "raw_result_ref": "reports/scanner-results/gitleaks-<hash>.json"
}
```

Raw scanner outputs remain local artifacts. Prompts and triage should use
`normalized_path` by default and must not quote or reconstruct full secrets.

## OpenSSF Scorecard posture ingestion

OpenSSF Scorecard is handled as scanner ingestion plus deterministic
supply-chain posture reporting. Run Scorecard externally in an authorized
environment, for example:

```bash
scorecard --repo=github.com/OWNER/REPO --format=json --show-details > scorecard.json
```

Then import the JSON result:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
```

In addition to the scanner index and normalized leads, this writes:

```text
reports/supply-chain-posture.json
reports/supply-chain-posture.md
```

Low-scoring mapped checks can append deterministic `TGT-SCORECARD-NNN` target
queue entries. Scorecard posture entries are leads, not confirmed findings. See
[`docs/SCORECARD_INGESTION.md`](SCORECARD_INGESTION.md) for the full workflow.

## SBOM and dependency graph posture ingestion

SBOM/dependency graph JSON is handled as scanner ingestion plus deterministic
dependency risk reporting. Supported inputs include CycloneDX JSON, SPDX 2.3
JSON, GitHub Dependency Graph SBOM export JSON, Trivy SBOM exports in CycloneDX
or SPDX form, best-effort Syft native JSON, and Trivy/Grype vulnerability JSON
that can be linked to dependency components when identifiers match.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file sbom.spdx.json --format spdx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool syft --file syft.json --format syft
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy-cyclonedx.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool grype --file grype.json --format json
```

In addition to the scanner index and normalized leads, this writes:

```text
reports/dependencies.json
reports/DEPENDENCY_RISK.md
```

Dependency vulnerability records are evidence, not confirmed findings. License
data is included for posture context and does not create security Issues by
default. High-signal dependency vulnerabilities with dependency paths can append
deterministic `TGT-DEPENDENCY-NNN` queue entries for review, but those entries
remain posture targets until reachability is confirmed. See
[`docs/DEPENDENCY_INGESTION.md`](DEPENDENCY_INGESTION.md) for the full workflow
and privacy considerations.

When `scanner-index.json` is present, validate it before triage:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

This validates the index schema, raw artifact paths, normalized artifact paths,
and normalized lead counts before scanner leads are used by downstream triage or
reporting commands.

Then triage:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID
```

Rules:

- Scanner output is treated as leads, not as confirmed findings.
- Codex must confirm reachability, trust-boundary impact, and mitigation status before promoting a lead to a finding.
- Normalized leads are capped and redacted. Valid JSON and JSONL/NDJSON inputs are parsed
  before lead limits are applied; unparsed text inputs are sampled with explicit
  `normalization` limits in the normalized lead artifact.
- DAST and Nuclei-style external scans are intentionally not built in. Use only in explicitly authorized, isolated environments.

## External finding import

Use `gra-import-findings` when a managed AI security tool, deterministic scanner,
or internal review system already produced finding-like records and you want to
normalize them into GenAI Repo Auditor without binding the project to a vendor:

```bash
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json
```

This writes:

```text
reports/imported-findings.json
reports/IMPORTED_FINDINGS.md
```

Default mode is review-only and does not modify `reports/findings.json`.
Invalid per-record input is retained under `rejected_findings` with reasons,
rather than silently dropped. Use append mode only when you explicitly want to
add normalized records to `findings.json`:

```bash
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json --append-findings
```

Appended imports carry `external_source` metadata and are still review-gated:
`issue_recommended=false`, `issue_body_file=""`, and assessment dimensions are
`Not assessed` until a human reviewer validates the finding. See
[`docs/EXTERNAL_FINDING_IMPORT.md`](EXTERNAL_FINDING_IMPORT.md) for the full
generic JSON contract and safety rules.

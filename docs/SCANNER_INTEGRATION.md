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

Plans reject unknown adapters, source-only/local-test execution profiles, path
traversal, symlinked run paths, undeclared network access, and arbitrary shell
arguments. All planned paths are run-relative. A valid plan is not execution
approval. `--execute` is explicit and supports only the enforced `container` and
`gvisor` profiles. Execution uses local Docker or Podman, a read-only target bind
mount, a dedicated output mount, a read-only container root, dropped
capabilities, `no-new-privileges`, bounded CPU/memory/PIDs, and `--network=none`.
It never pulls an image. The operator must pre-pull the immutable image digest
during a separately authorized setup phase.

On an enforcing SELinux host, execution uses `label=disable` instead of
recursively relabeling the audited target. This preserves target filesystem
metadata; isolation continues to rely on the read-only target/root mounts,
dropped capabilities, default seccomp, `no-new-privileges`, resource limits,
and disabled network.

The execution images are pinned by multi-platform digest:

- Gitleaks: `ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`;
- Syft: `ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb`.

Execution rejects remote runtime environment configuration, missing runtimes or
images, unsupported profiles, any network allowance, existing/symlinked output,
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

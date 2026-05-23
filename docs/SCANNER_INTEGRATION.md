# Scanner Integration

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
or SPDX form, and best-effort Syft native JSON.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file sbom.spdx.json --format spdx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool syft --file syft.json --format syft
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy-cyclonedx.json --format cyclonedx
```

In addition to the scanner index and normalized leads, this writes:

```text
reports/dependencies.json
reports/DEPENDENCY_RISK.md
```

Dependency vulnerability records are evidence, not confirmed findings. License
data is included for posture context and does not create security Issues by
default. See [`docs/DEPENDENCY_INGESTION.md`](DEPENDENCY_INGESTION.md) for the
full workflow and privacy considerations.

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

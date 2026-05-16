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
custom
```

The ingest command does not run scanners. It copies existing scanner output into the run directory
and creates a bounded, redacted normalized lead file for triage.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
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

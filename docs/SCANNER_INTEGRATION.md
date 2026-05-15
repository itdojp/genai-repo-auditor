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

The ingest command does not run scanners. It copies existing scanner output into the run directory.

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
```

Then triage:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID
```

Rules:

- Scanner output is treated as leads, not as confirmed findings.
- Codex must confirm reachability, trust-boundary impact, and mitigation status before promoting a lead to a finding.
- DAST and Nuclei-style external scans are intentionally not built in. Use only in explicitly authorized, isolated environments.

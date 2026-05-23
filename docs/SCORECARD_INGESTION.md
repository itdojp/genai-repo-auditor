# OpenSSF Scorecard ingestion

GenAI Repo Auditor can ingest OpenSSF Scorecard JSON as supply-chain posture
evidence. The ingest path does not run Scorecard. Run Scorecard separately in an
authorized environment, then import the JSON result into an existing audit run.

Official Scorecard documentation describes the command line interface, JSON
format output via `--format=json`, and detailed check output via `--show-details`:

- https://github.com/ossf/scorecard
- https://github.com/ossf/scorecard/blob/main/docs/checks.md

## Run Scorecard externally

For a GitHub repository, authenticate Scorecard according to the upstream
Scorecard documentation and keep tokens out of shell history and committed files.
Then create a JSON artifact:

```bash
scorecard --repo=github.com/OWNER/REPO --format=json --show-details > scorecard.json
```

Scorecard output may include repository metadata, check details, and workflow
context. Treat the raw JSON as local scanner output and do not commit it.

## Ingest the JSON result

Import the result into a prepared GenAI Repo Auditor run:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
```

The command still creates the normal scanner artifacts:

```text
reports/scanner-results/<tool>-<hash>.json
reports/scanner-results/normalized/<tool>-<hash>-leads.json
reports/scanner-results/scanner-index.json
```

When `--tool scorecard` (or `openssf-scorecard` / `ossf-scorecard`) is used, it
also writes deterministic posture artifacts:

```text
reports/supply-chain-posture.json
reports/supply-chain-posture.md
```

The posture JSON includes:

- overall Scorecard score when present
- each parsed check name, score, Scorecard risk, assessed risk, reason, details,
  documentation/remediation link, and remediation text
- `target_recommended: true` for low-scoring checks that warrant bounded follow-up
- `findings_created: 0`, because Scorecard posture does not automatically prove a
  concrete repository vulnerability

## Target queue integration

Low-scoring Scorecard checks can generate target-queue entries. Examples:

| Scorecard check | Target category | Supply-chain taxonomy |
|---|---|---|
| `Dangerous-Workflow` | CI/CD Security | `SC-DANGEROUS-WORKFLOW` |
| `Token-Permissions` | GitHub Actions Permissions | `SC-CICD-TOKEN-PERMISSIONS` |
| `Pinned-Dependencies` | Supply Chain Hardening | `SC-PINNED-DEPENDENCIES` |
| `Branch-Protection` | Repository Governance | `SC-BRANCH-PROTECTION` |
| `Code-Review` | Repository Governance | `SC-CODE-REVIEW` |
| `Dependency-Update-Tool` | Dependency Maintenance | `SC-DEPENDENCY-UPDATE` |
| `Security-Policy` | Disclosure Governance | `SC-SECURITY-POLICY` |
| `SAST` | Static Analysis Coverage | `SC-SAST` |
| `Signed-Releases` | Release Integrity | `SC-SIGNED-RELEASES` |

`gra-ingest --tool scorecard` appends deterministic `TGT-SCORECARD-NNN` entries
when the posture report recommends them. `gra-targets --generate` also appends
those targets after AI-generated target creation if `reports/supply-chain-posture.json`
already exists.

## Dashboard integration

`gra-dashboard` displays a supply-chain posture section with the Scorecard
status, overall score, risk distribution, check scores, reasons, remediation
text, and target recommendation flags.

```bash
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

## Safety notes

- Raw Scorecard JSON remains a local scanner artifact. Do not commit it.
- The deterministic posture artifacts redact common token and secret patterns in
  reasons/details before writing Markdown or JSON posture summaries.
- Treat Scorecard checks as posture leads. Promote a finding only after repository
  context confirms a concrete, actionable issue with file/line evidence.

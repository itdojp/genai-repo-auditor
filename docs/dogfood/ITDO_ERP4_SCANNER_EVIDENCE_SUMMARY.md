# ITDO_ERP4 scanner and supply-chain evidence summary

This document is a public-safe scanner evidence handling summary and acquisition
plan for the scoped ITDO_ERP4 dogfood campaign. It does not contain scanner raw
output, normalized scanner leads, dependency records, target repository code,
finding bodies, or private vulnerability details.

Use it with [`ITDO_ERP4_SCOPE.md`](ITDO_ERP4_SCOPE.md),
[`ITDO_ERP4_TARGET_SELECTION.md`](ITDO_ERP4_TARGET_SELECTION.md),
[`ITDO_ERP4_REPORTING_BOUNDARIES.md`](ITDO_ERP4_REPORTING_BOUNDARIES.md),
[`../SCANNER_INTEGRATION.md`](../SCANNER_INTEGRATION.md),
[`../SCORECARD_INGESTION.md`](../SCORECARD_INGESTION.md),
[`../DEPENDENCY_INGESTION.md`](../DEPENDENCY_INGESTION.md),
[`../EXTERNAL_FINDING_IMPORT.md`](../EXTERNAL_FINDING_IMPORT.md),
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md),
and [`../LOCAL_ARTIFACT_CLEANUP.md`](../LOCAL_ARTIFACT_CLEANUP.md).

## Public-safe boundary

Scanner raw outputs remain local/private. This document may be committed because
it records only the artifact availability decision, safe ingestion sequence,
expected count fields, and publication guardrails.

Do not include:

```text
- raw scanner output or normalized scanner lead bodies
- dependency inventory records, package versions, or private package names
- source snippets, request bodies, response bodies, or exploit narratives
- secret values, token fragments, cookies, credentials, or environment files
- generated issue drafts, dashboards, SARIF files, SQLite stores, or transcripts
- remediation patches or private handoff text
```

Normalized scanner leads are review leads and not automatically confirmed findings.
A lead can become a finding only after repository context, reachability,
impact, and remediation direction are reviewed through the normal validation and
disclosure process.

## Current artifact availability

No authorized current-run scanner artifacts were available to ingest during this
implementation pass. The scoped dogfood execution completed prepare/recon/target
selection and one bounded research target, but scanner/posture artifacts were not
present in the current run directory. Legacy local audit outputs were not reused
because they were outside the approved current-run scope.

| Evidence source | Availability in this pass | Handling decision |
|---|---|---|
| CodeQL SARIF | Not available | Acquire from an authorized local or GitHub Actions source before ingest. |
| npm audit JSON | Not available | Generate or export in an authorized local dependency environment before ingest. |
| CycloneDX SBOM | Not available | Generate with the target repository's approved SBOM workflow before ingest. |
| Trivy JSON | Not available | Use only if produced from an approved local filesystem/container context. |
| Grype JSON | Not available | Use only if produced from an approved local SBOM or filesystem context. |
| OpenSSF Scorecard JSON | Not available | Prefer an already authorized artifact; any new external Scorecard run requires separate explicit approval for repository access and token handling. |
| Secret-scan output | Not available | Ingest only redacted or safely bounded output; never publish raw matches. |
| GitHub Actions artifacts | Not downloaded | Download only approved artifacts, then keep them in the local run directory. |

## Acquisition and ingest plan

Use placeholders until the operator records the approved run directory and local
artifact directory. Keep raw inputs outside Git and copy them into the run only
through `gra-ingest`.

```bash
RUN=runs/itdojp__ITDO_ERP4/RUN_ID
ARTIFACT_DIR=LOCAL_RESTRICTED_SCANNER_DIR

# Import existing scanner/posture outputs only after authorization is recorded.
gra-ingest --run "$RUN" --tool codeql --file "$ARTIFACT_DIR/codeql.sarif" --format sarif
gra-ingest --run "$RUN" --tool sbom --file "$ARTIFACT_DIR/bom.json" --format cyclonedx
gra-ingest --run "$RUN" --tool trivy --file "$ARTIFACT_DIR/trivy.json" --format json
gra-ingest --run "$RUN" --tool grype --file "$ARTIFACT_DIR/grype.json" --format json
gra-ingest --run "$RUN" --tool scorecard --file "$ARTIFACT_DIR/scorecard.json" --format json

# Triage and deterministic follow-up. Do not publish leads from these commands.
gra-scanner-triage --run "$RUN" --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --generate --model gpt-5.5 --effort xhigh
gra-metrics --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-validate-report --run "$RUN"
gra-issues --run "$RUN" --dry-run
```

Use the target-selection rules in `ITDO_ERP4_TARGET_SELECTION.md` after target
regeneration. Scanner-derived target entries should be prioritized only when the
lead is relevant to the approved ITDO_ERP4 scope and can be reviewed locally.

## Expected local artifacts after ingest

These paths are local run artifacts and must not be committed:

| Artifact category | Expected local output | Public-safe summary field |
|---|---|---|
| Scanner index | `reports/scanner-results/scanner-index.json` | scanner index entry count |
| Normalized leads | `reports/scanner-results/normalized/` | lead count by tool and severity |
| Dependency posture | `reports/dependencies.json` and dependency summary | component/vulnerability counts only |
| Scorecard posture | `reports/supply-chain-posture.json` and posture summary | check count and risk distribution only |
| Target queue updates | `reports/targets.json` | generated target count and selected target IDs only |
| Metrics/evidence graph update | metrics and evidence graph reports | aggregate counts and graph node/edge counts only |
| Issue dry-run | issue preview and ledger artifacts | Issue dry-run would-create Issue count and warning counts only |

If scanner ingestion produces zero leads, record that as an explicit count rather
than omitting the scanner stage. If ingestion fails, record the tool, status, and
bounded error category locally; do not paste raw tool output into this repository.

## Public-safe summary template

Copy this section to a local or restricted summary before filling in concrete
counts. Commit only after a human reviewer approves the exact public-safe text.

| Field | Value |
|---|---|
| Target repository | `itdojp/ITDO_ERP4` |
| Run ID | `RUN_ID` |
| Scanner evidence status | `not available / ingested / partially ingested / failed` |
| Authorization reference | `APPROVAL_REFERENCE` |
| Raw artifact retention decision | `delete-after-review / retain-local / secure-archive` |
| Public publication decision | `none / private-first / approved-public-safe` |

| Evidence source | Ingested? | Public-safe count field | Notes |
|---|---|---:|---|
| CodeQL SARIF | `yes / no / not available` | `N` | lead count only |
| npm audit JSON | `yes / no / not available` | `N` | dependency vulnerability count only |
| CycloneDX SBOM | `yes / no / not available` | `N` | component count only |
| Trivy JSON | `yes / no / not available` | `N` | vulnerability lead count only |
| Grype JSON | `yes / no / not available` | `N` | vulnerability lead count only |
| OpenSSF Scorecard JSON | `yes / no / not available` | `N` | low-scoring check count only |
| Secret-scan output | `yes / no / not available` | `N` | redacted lead count only |
| GitHub Actions artifacts | `yes / no / not available` | `N` | artifact count only |

| Follow-up stage | Status/count |
|---|---:|
| Scanner triage status | `not run / passed / failed / skipped` |
| Scanner-derived target count | `N` |
| Dependency-derived target count | `N` |
| Scorecard-derived target count | `N` |
| Metrics/evidence graph update | `not run / passed / failed` |
| Evidence graph nodes | `N` |
| Evidence graph edges | `N` |
| Confirmed findings from scanner leads | `N` |
| Issue dry-run would-create Issue count | `N` |
| Issue dry-run warnings | `N` |

## Publication and routing rules

- Keep raw scanner outputs, normalized leads, dependency posture, Scorecard
  posture, dashboards, and issue previews local/private by default.
- Treat scanner leads as input to human review, not as confirmed findings.
- Route GenAI Repo Auditor workflow friction to `itdojp/genai-repo-auditor` only
  when the observation can be explained without target evidence.
- Route ITDO_ERP4 security-impacting candidates through the target repository's
  private disclosure path before any public Issue.
- Use `gra-issues --dry-run` for counts and warning review only. Do not use
  publication actions or `--allow-public` without explicit approval of the exact
  text and destination.

## Stop conditions

Stop scanner ingestion or publication planning when any of these occur:

- scanner artifact authorization, provenance, or retention is unclear;
- a scanner output contains unredacted secrets or private operational context;
- a dependency or posture artifact reveals private package names or internal
  architecture that cannot be summarized safely;
- a scanner-derived target requires production, staging, or external host access;
- `gra-validate-report` fails or issue dry-run warnings are non-zero without
  explicit acceptance;
- a public summary would need scanner record bodies or vulnerability detail to be
  understandable.

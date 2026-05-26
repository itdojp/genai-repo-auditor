# staged agentic Defensive Workflow

This lab uses an staged agentic-inspired structure, but it is deliberately defensive.
It does not include exploit generation, external DAST, production probing, or autonomous fix application.

## Pipeline

```text
prepare
  -> recon
  -> targets
  -> research target(s)
  -> validate findings
  -> variant analysis
  -> scanner triage
  -> dashboard / SARIF / SQLite store
  -> human review
  -> GitHub Issues
```

## Prepare

```bash
gra-audit --repo OWNER/REPO --mode prepare --model gpt-5.5 --effort xhigh
```

This clones the target repository into a run directory and renders prompts, but does not start Codex analysis.

## Recon

```bash
gra-recon --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Outputs:

```text
reports/AUDIT_SUMMARY.md
reports/THREAT_MODEL.md
reports/ATTACK_SURFACE.md
reports/AUDIT_LOG.md
```

## Target queue

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --list
```

Outputs:

```text
reports/targets.json
```

Targets are bounded review units. They prevent a large repository audit from becoming an uncontrolled, broad sweep.
For high-signal vulnerability research, each target should state the attack
class, attacker model, security invariants, entry points, sinks, `max_files`
inspection bound, expected output, and chain relevance when known. Keep
`max_files` within 1..20 and prefer smaller 4..8 file reviews for normal target
research. See [Target Queue](TARGET_QUEUE.md) for examples of good and bad
target granularity.

## Research one target

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --model gpt-5.5 --effort xhigh
```

For supervised `/goal` deep dive:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal --model gpt-5.5 --effort xhigh
```

Outputs:

```text
reports/target-research/TGT-001.md
reports/FINDINGS.md
reports/findings.json
reports/issue-drafts/SEC-XXX.md
```

## Variant analysis

Use a confirmed or probable finding as a seed to find structurally similar bugs.

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --model gpt-5.5 --effort xhigh
```

For supervised `/goal` variant analysis:

```bash
gra-variant --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal --model gpt-5.5 --effort xhigh
```

Outputs:

```text
reports/variant-analysis/SEC-001.md
reports/FINDINGS.md
reports/findings.json
```

## Scanner ingestion and triage

Ingest scanner output:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool gitleaks --file gitleaks.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
```

Ask Codex to triage scanner leads:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Scanner results are leads. They are not automatically treated as findings.

## Reporting

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-sarif --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID
```

Outputs:

```text
reports/dashboard.html
reports/findings.sarif
runs/security-audit.sqlite
```

## Offline staged regression fixture

The normal Python integration suite includes an offline staged workflow fixture:

```bash
python3 -m unittest tests.integration.test_cli_workflows.CliWorkflowTests.test_offline_staged_posture_workflow_fixture -v
```

The fixture uses a mocked `gh` clone, mocked `codex exec`, and local Scorecard /
SBOM JSON fixtures. It exercises prepare, recon, target generation, Scorecard
and dependency ingestion, validation, dashboard, SARIF, SQLite store, and run
index generation without real GitHub, Codex, scanner, network, or external
repository access. It asserts that posture-derived targets are generated and
that run artifact references remain run-relative.

## Issue creation

Always review reports manually before creating GitHub Issues.

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

Public repositories are blocked by default. Use `--allow-public` only when disclosure policy permits.

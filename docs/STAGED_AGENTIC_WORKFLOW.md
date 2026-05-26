# staged agentic Defensive Workflow

This lab uses an staged agentic-inspired structure, but it is deliberately defensive.
It does not include exploit generation, external DAST, production probing, or autonomous fix application.

## Pipeline

```text
prepare
  -> recon
  -> targets
  -> research target(s)
  -> coverage gapfill
  -> validate findings
  -> synthesize defensive chains
  -> generate safe local proofs
  -> optional cross-repo trace reachability
  -> adversarial validation
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

Target research should update the target's optional `coverage` metadata in
`reports/targets.json`, including review depth, reviewed/skipped files,
commands, unresolved questions, and whether bounded gapfill is recommended.

## Coverage gapfill

After normal research or supervised `/goal` target review, use `gra-gapfill` to
avoid leaving high-risk areas shallowly reviewed.

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --list
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
```

Outputs:

```text
reports/COVERAGE.md
reports/gapfill-targets.json
reports/target-research/TGT-XXX-gapfill.md
```

`--generate` appends deterministic `TGT-GAPFILL-NNN` queue entries for source
targets whose `coverage` metadata has `gapfill_recommended: true`, shallow
Critical/High review depth, or unresolved high-risk questions. It reuses
existing gapfill targets for the same source target on repeated runs.

Run one bounded gapfill:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode exec --model gpt-5.5 --effort xhigh
```

For a supervised `/goal` gapfill:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal --model gpt-5.5 --effort xhigh
```

Gapfill is not a new broad audit. It must focus on skipped files and unresolved
questions from the source target, stay within `max_files`, avoid network access
unless explicitly approved, and never modify the target repository.

## Adversarial validation

Before Issue publication, run an independent pass that challenges existing
findings or chains. This stage does not create new findings; it records whether
selected subjects should be confirmed, downgraded, invalidated, or marked
`needs-human-review`.

```bash
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --model gpt-5.5 --effort xhigh
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

For a single finding or a supervised chain review:

```bash
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --chain CHAIN-001 --mode goal
```

Outputs:

```text
reports/adversarial-validation/<selection>.subjects.json
reports/validation.json
reports/VALIDATION.md
```

Review `VALIDATION.md` before `gra-issues --plan`. Downgraded, invalidated, or
`needs-human-review` subjects should not be published as confirmed
exploitability without explicit human review and revised issue wording.

## Defensive chain synthesis

Use `gra-chains` to connect existing findings, targets, scanner refs, and
validation notes into possible defensive reachability or impact chains. This
stage is for prioritization and safe validation planning; it does not create
new findings and must not generate exploit payloads or weaponized steps.

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

For supervised review:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID --mode goal
```

Outputs:

```text
reports/chains.json
reports/ATTACK_CHAINS.md
```

`ATTACK_CHAINS.md` is non-public by default. Use it to prioritize remediation
and decide where additional adversarial validation is needed before Issue
publication.

## Safe local proofs

Use `gra-proofs` to create local/private proof artifacts for existing findings.
This stage is for benign validation only. It can record static traces,
unit-test plans, local regression plans, parser-only local input descriptions,
config checks, or mocked local behavior; it must not generate exploit code,
install dependencies, modify the target repository, contact live services, or
scan networks.

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high --model gpt-5.5 --effort xhigh
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

For a single finding or supervised review:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

Outputs:

```text
reports/proofs/<selection>.subjects.json
reports/proofs.json
reports/PROOFS.md
reports/proofs/
```

`PROOFS.md` and files under `reports/proofs/` are local/private by default.
Use them to refine validation status and Issue wording; do not copy them
wholesale into public Issues.

## Cross-repo trace reachability

Use `gra-trace` when a producer finding, such as a shared-library flaw, may be
consumed by another repository. This stage is experimental/P3 and records
reachability evidence only; it is not exploit proof.

Prepare a consumer workspace when a consumer run does not already exist:

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-repo ORG/consumer-api \
  --mode prepare
```

Trace against an existing consumer run:

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__consumer-api/RUN_ID \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
gra-validate-report --run runs/ORG__shared-lib/RUN_ID
```

Outputs:

```text
reports/traces/<selection>.subjects.json
reports/traces.json
reports/TRACE.md
```

Trace review must stay local-first: no external scanning, no production or
staging probing, no exploit payloads, no credential access, no dependency
installation, and no producer/consumer repository modification.

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

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

## Pause and resume run state

Use `gra-run-state` when an audit is intentionally paused for operational
reasons such as maintainer updates, release windows, or handoff. This records a
`paused` state rather than overloading `blocked`, which is reserved for a true
impasse.

```bash
gra-run-state --run runs/OWNER__REPO/RUN_ID --pause \
  --reason "maintainer update window" \
  --resume-target TGT-AGENT-234 \
  --resume-condition "main branch updated and post-merge CI passed" \
  --final-reconcile "published known findings: 52; unpublished Medium+: 0"
gra-run-state --run runs/OWNER__REPO/RUN_ID --status
gra-run-state --run runs/OWNER__REPO/RUN_ID --resume
```

When `reports/gapfill-targets.json` is present, `--status` and `--resume` also
print prioritized next gapfill targets so final reconcile handoffs can resume
bounded coverage work in order.

While paused, use only read-only status checks. Deep-review starts and target
queue mutations are guarded: `gra-research`, `gra-gapfill --generate`,
`gra-gapfill --target`, `gra-targets --generate`, and `gra-targets --mark`
refuse to proceed until the pause is cleared.

## Declarative workflow execution and checkpoints

`gra-run` plans by default. Use `--execute` only after reviewing the generated
stage order. Execution uses the profile's exact approved local argv, never adds
network or publication flags, and stops dependents after a failed stage.

```bash
gra-run --run runs/OWNER__REPO/RUN_ID --profile recon-only
gra-run --run runs/OWNER__REPO/RUN_ID --profile recon-only --execute --until recon
gra-run --run runs/OWNER__REPO/RUN_ID --profile recon-only --resume
```

The checkpoint is `<reports_dir>/workflow-checkpoint.json`. Resume verifies the
run, profile, plan fingerprint, and hashes of successful outputs before it runs
the exact resume stage. Successful stages are not repeated. Use `--from` only
for a supervised range with the required prior-stage artifacts already present;
those external prerequisites are hashed into the checkpoint. A new execution
also rejects declared outputs that already exist, avoiding accidental reuse of
stale stage results. A paused or
blocked `gra-run-state` prevents both new execution and resume.

Ranges follow DAG dependency closure rather than incidental topological list
positions. `--from X` includes `X` and its descendants; `--until Y` includes
`Y` and its ancestors. With both options, `Y` must be `X` or a descendant and
only stages on their dependency path closure are selected. Unrelated sibling
stages are recorded as `out_of_range` and are not executed on resume.

Built-in profiles keep Issue publication outside unattended execution:

| Profile | Approved scope |
|---|---|
| `recon-only` | Reconnaissance and optional target generation. |
| `supply-chain` | Reconnaissance, optional offline Syft planning, and target generation. |
| `appsec-deep` | Reconnaissance, optional offline Gitleaks planning, target generation, chains, safe proofs, and adversarial validation over existing findings. |
| `publication-ready` | Local report validation, metrics, evidence graph, dashboard, and SARIF generation over existing findings. |
| `full` | The combined approved local stages from the profiles above. |

The scanner stages call `gra-scan --plan`; they do not pass scanner
`--execute`. No profile contains `gra-issues`, remediation, release, GitHub,
network-enabling, or publication flags. Publishing Issues remains a separate
human-reviewed command after workflow completion.

Reconnaissance and deep-analysis commands can invoke the configured local
agent worker and retain their existing local prompt/event/stderr artifacts.
The orchestrator does not copy those raw artifacts into its checkpoint and
does not add `--network`; the worker sandbox is configured with network access
disabled. These local transcripts remain subject to the existing run-artifact
retention and non-public handling rules.

Direct chain, proof, and adversarial-validation commands resolve outputs under
the configured `reports_dir`, reject pre-existing symlink output components,
and atomically replace only regular run-local destination files.

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
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split --model gpt-5.5 --effort xhigh
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
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
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
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

## Remediation candidates

Use `gra-remediate` to create local/private, draft-only candidate patches for
human review. This stage does not apply patches, modify the target checkout,
push branches, open PRs, create issues, install dependencies, access the
network, or execute target code.

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
```

Outputs stay under `reports/remediation/` and are validated by
`gra-validate-report`.

After a candidate patch exists, run the patch validation ladder in a disposable
workspace. This applies the patch only to a copied checkout, runs only bounded
Python validation commands by default with a Python no-network guard, and
records build/test/proof/adversarial-review status without publishing anything:

```bash
gra-remediate --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --validate \
  --sandbox-profile local-test \
  --build-command "python3 -m py_compile repo/app.py" \
  --test-command "python3 -m py_compile repo/app.py"
```

The validation report is written to
`reports/remediation/<FINDING-ID>/patch-validation.json` and
`patch-validation.md`. A validated report is still a local handoff artifact; a
human must review the diff before applying it in a separate remediation
workflow.

## Cross-repo trace reachability

Use `gra-trace` when a producer finding, such as a shared-library flaw, may be
consumed by another repository. This stage is experimental/P3 and records
reachability evidence only; it is not exploit proof.

Prepare a consumer workspace under the producer run:

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-repo ORG/consumer-api \
  --mode prepare
```

Trace against the prepared consumer run. External consumer runs are rejected so
producer trace artifacts do not persist absolute paths outside the producer run
boundary:

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__shared-lib/RUN_ID/trace-consumers/ORG__consumer-api \
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
gra-import-findings --run runs/OWNER__REPO/RUN_ID --file external-findings.json
```

Ask Codex to triage scanner leads:

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
```

Scanner results and imported external finding records are leads. They are not
automatically treated as publishable findings. `gra-import-findings` is
review-only by default; append mode is explicit and imported findings remain
`issue_recommended=false` until human review updates the finding metadata.

## Reporting

```bash
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-sarif --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID
```

Outputs:

```text
reports/metrics.json
reports/METRICS.md
reports/benchmark.json
reports/BENCHMARK.md
reports/evidence-graph.json
reports/EVIDENCE_GRAPH.md
reports/imported-findings.json
reports/IMPORTED_FINDINGS.md
reports/dashboard.html
reports/findings.sarif
runs/security-audit.sqlite
```

`run-manifest.json` at the run root records the canonical latest-status
handoff artifacts, supporting files, and archive reproducibility artifacts with
run-relative paths and file digests. `gra-validate-report` enforces manifest
hygiene when the manifest is present. `gra-metrics`, `gra-benchmark`, `gra-evidence-graph`, and
`gra-dashboard` surface latest/archive retention counts, benchmark gates, graph evidence links,
and manifest hygiene warnings without copying artifact contents.

## Offline staged regression fixture

The normal Python integration suite includes an offline staged workflow fixture:

```bash
python3 -m unittest tests.integration.test_audit_research_workflows.AuditResearchWorkflowTests.test_offline_staged_posture_workflow_fixture -v
```

The fixture uses a mocked `gh` clone, mocked `codex exec`, and local Scorecard /
SBOM JSON fixtures. It exercises prepare, recon, target generation, Scorecard
and dependency ingestion, validation, dashboard, SARIF, SQLite store, and run
index generation without real GitHub, Codex, scanner, network, or external
repository access. It asserts that posture-derived targets are generated and
that run artifact references remain run-relative.

The suite also includes an advanced local-only chain / proof / adversarial
validation regression fixture:

```bash
python3 -m unittest tests.integration.test_remediation_workflows.RemediationWorkflowTests.test_advanced_chain_proof_validation_workflow_fixture -v
```

Input run artifacts live under `tests/fixtures/advanced-workflow-run/`. They
include synthetic findings, bounded targets with coverage metadata, issue draft
placeholders, a tracked raw scanner artifact at
`reports/scanner-results/advanced-semgrep.json`, and a normalized scanner lead.
Mocked Codex outputs live under `tests/fixtures/advanced-workflow-output/` and
cover `chains.json`, `ATTACK_CHAINS.md`, `proofs.json`, `PROOFS.md`, safe proof
support files, `validation.json`, and `VALIDATION.md`.

The regression exercises `gra-chains`, `gra-proofs --all-critical-high`,
`gra-adversarial-validate --all-critical-high`, `gra-validate-report`,
`gra-dashboard`, and `gra-sarif` without exploit payloads, external services,
or real audit data. These fixture artifacts are synthetic and not publishable
as audit evidence.

## Issue creation

Always review reports manually before creating GitHub Issues.

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

Public repositories are blocked by default. Use `--allow-public` only when disclosure policy permits.

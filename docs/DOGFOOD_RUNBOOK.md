# Dogfood execution runbook

This runbook describes how to execute dogfood campaigns for GenAI Repo Auditor in
a local-first, disclosure-safe way. It intentionally separates execution from
publication: running an audit does not create GitHub Issues, PRs, releases, or
public reports.

Use it with [`DOGFOOD_CAMPAIGN.md`](DOGFOOD_CAMPAIGN.md),
[`DOGFOOD_REPORTING.md`](DOGFOOD_REPORTING.md), and
[`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md).

## Preflight checklist

Record the following in the local campaign ledger before running commands:

```text
- Target repository and commit are authorized.
- Operator and approver are identified.
- Scope is self-dogfood or ITDO_ERP4 scoped dogfood.
- Public/private reporting boundary is documented.
- Network access and scanner import permissions are documented.
- Retention decision is selected.
- No generated run artifact will be committed.
```

If any answer is missing, stop before `gra-audit`.

## Self-dogfood path

Use this path to evaluate the harness on `itdojp/genai-repo-auditor` itself. The
primary objective is product feedback: workflow reliability, safety boundaries,
operator UX, and report quality.

```bash
gra-audit --repo itdojp/genai-repo-auditor --mode prepare --model gpt-5.5 --effort xhigh

RUN=runs/itdojp__genai-repo-auditor/RUN_ID

gra-recon --run "$RUN" --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --generate --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --list

# Recon-only stop path:
# If the bounded pass intentionally stops here with no confirmed findings, run
# gra-workflow-profile, gra-no-findings, and the deterministic reporting
# commands in a separate terminal/session, then stop. Do not run these stop-path
# commands before the deeper path.
# gra-workflow-profile --run "$RUN" \
#   --profile recon-only \
#   --rationale "Bounded reconnaissance completed; advanced stages are intentionally out of scope."
# gra-no-findings --run "$RUN" \
#   --source-stage recon \
#   --rationale "Bounded reconnaissance completed; no candidate findings were advanced for this pass."
# gra-validate-report --run "$RUN"
# gra-metrics --run "$RUN"
# gra-benchmark --run "$RUN"
# gra-evidence-graph --run "$RUN"
# gra-issues --run "$RUN" --dry-run

# Deeper review path:
gra-gapfill --run "$RUN" --generate
gra-adversarial-validate --run "$RUN" --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run "$RUN"
gra-metrics --run "$RUN"
gra-benchmark --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-dashboard --run "$RUN"
gra-issues --run "$RUN" --dry-run
# Optional immutable approval artifact after reviewing the dry-run preview.
gra-issues --run "$RUN" --plan --require-advanced-validation
```

Review findings locally. If the run exposes product friction rather than target
security issues, convert sanitized observations into product-improvement backlog
items. Do not publish self-dogfood findings without the same disclosure review
required for any public repository.

## ITDO_ERP4 scoped AppSec path

Use this path only after scope and target-selection documents have been prepared
for `itdojp/ITDO_ERP4`. The initial scope should stay bounded to high-value
application-security areas such as RBAC, approval state transitions, expense,
invoice, timesheet, Agent-First evidence, CI/security posture, and storage or AV
paths when present.

```bash
gra-audit --repo itdojp/ITDO_ERP4 --mode prepare --model gpt-5.5 --effort xhigh

RUN=runs/itdojp__ITDO_ERP4/RUN_ID

gra-recon --run "$RUN" --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --generate --model gpt-5.5 --effort xhigh
gra-targets --run "$RUN" --list

# Human review narrows targets before deep research.
gra-research --run "$RUN" --target TGT-001 --model gpt-5.5 --effort xhigh
gra-adversarial-validate --run "$RUN" --all-critical-high --votes 3 --policy human-review-on-split
gra-chains --run "$RUN"
gra-proofs --run "$RUN" --all-critical-high
gra-metrics --run "$RUN"
gra-benchmark --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-dashboard --run "$RUN"
gra-validate-report --run "$RUN"
gra-issues --run "$RUN" --dry-run
```

`gra-issues --dry-run` is an operator preview tool. It does not write
`reports/issue-publication-plan.json`. Use `gra-issues --plan` only after
reviewing the preview and when an immutable approval artifact is needed. Neither
command is approval to publish. Dry-run output may include target-specific Issue
titles, fingerprints, and issue body hashes; use approved counts or sanitized
fixtures for public demos. Use
[`DISCLOSURE_AND_PUBLICATION_POLICY.md`](DISCLOSURE_AND_PUBLICATION_POLICY.md)
before any `gra-issues --apply` workflow.

## Scanner and external evidence path

GenAI Repo Auditor does not run external scanners by default. If scanner outputs
are already available and authorized, ingest them as evidence leads:

```bash
gra-ingest --run "$RUN" --tool codeql --file codeql.sarif --format sarif
gra-ingest --run "$RUN" --tool sbom --file bom.json --format cyclonedx
gra-ingest --run "$RUN" --tool trivy --file trivy.json --format json
gra-ingest --run "$RUN" --tool grype --file grype.json --format json
gra-ingest --run "$RUN" --tool scorecard --file scorecard.json --format json
gra-scanner-triage --run "$RUN" --model gpt-5.5 --effort xhigh
gra-metrics --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-validate-report --run "$RUN"
```

Scanner output remains local/private. Normalized scanner leads are not confirmed
findings until repository context and reachability are reviewed.

## Run record update

After each major stage, update the local run record with command status and
artifact references only:

```json
{
  "name": "gra-metrics",
  "status": "passed",
  "artifact_refs": [
    "reports/metrics.json"
  ],
  "public_safe_summary": "counts-only summary after review"
}
```

For Issue review, keep preview and immutable plan records separate:

```json
{
  "name": "gra-issues --dry-run",
  "status": "passed",
  "artifact_refs": [
    "issues-created.json",
    "reports/issue-ledger.json"
  ],
  "public_safe_summary": "preview and warning counts only after review"
}
```

```json
{
  "name": "gra-issues --plan",
  "status": "passed",
  "artifact_refs": [
    "reports/issue-publication-plan.json",
    "reports/issue-ledger.json"
  ],
  "public_safe_summary": "immutable plan metadata only after human review"
}
```

Do not paste raw logs, transcripts, scanner records, evidence snippets, attack
chains, proof payloads, or remediation diffs into the ledger.

## Stop conditions

Stop and request human review when any of these occur:

- authorization or scope is unclear;
- a command would require network or scanner activity not previously approved;
- a potential Critical/High finding depends on proof, chain, trace, or private
  evidence details;
- adversarial validation returns `downgrade`, `invalidate`, or unresolved split;
- issue-publication planning generates warnings;
- public wording would require `--allow-public`;
- generated artifacts are about to be copied into Git.

## Cleanup

At the end of each run:

```bash
python3 scripts/clean-local-artifacts.py
# Review output, then apply only after approval.
python3 scripts/clean-local-artifacts.py --apply
```

If artifacts are retained, record the retention decision in the local campaign
ledger and store them only through an approved secure process.

### Recon-only / no-confirmed-finding runs

When a dogfood pass intentionally stops after reconnaissance or human scope
review and no finding is confirmed, do not create `reports/findings.json` or a
stage-status record by hand. Use `gra-workflow-profile --profile recon-only` to
record that advanced stages are intentionally `skipped_by_scope`, then use
`gra-no-findings` to write a schema-valid empty findings artifact with a
required rationale and target metadata:

```bash
gra-workflow-profile --run "$RUN" \
  --profile recon-only \
  --rationale "Bounded reconnaissance completed; advanced stages are intentionally out of scope."
gra-no-findings --run "$RUN" \
  --source-stage recon \
  --rationale "Bounded reconnaissance completed; no candidate findings were advanced for this pass."
gra-validate-report --run "$RUN"
gra-metrics --run "$RUN"
gra-benchmark --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-issues --run "$RUN" --dry-run --min-severity Low \
  --statuses Confirmed,Probable,Potential,Informational
```

The generated artifact records a `no_findings` decision and an empty `findings`
array. It does not assert that the repository has no vulnerabilities; it only
records the reviewed state of this bounded run. The generated workflow profile
records `skipped_by_scope` stage status so `gra-metrics`, `gra-benchmark`, and
`gra-evidence-graph` can distinguish scoped skips from missing outputs or
command failures.

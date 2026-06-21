# Issue workflow

## Principles

Issue creation is not part of an audit run. Create GitHub Issues with
`gra-issues` only after a human has reviewed `findings.json` and
`issue-drafts/*.md`.

## default selection

By default, only the following findings are selected for Issue publication:

```text
severity: Critical / High
status: Confirmed / Probable
issue_recommended: true
```

Before publication, also review the optional structured assessment fields in
`findings.json`: `bug_existence`, `attacker_reachability`,
`boundary_crossing`, `impact_assessment`, and `assessment_notes`. A finding may
have a real code defect while reachability, boundary crossing, or impact is
only Potential or Not assessed. In those cases, the Issue draft should avoid
claiming confirmed exploitability and should explain the remaining validation
gap.

Findings appended by `gra-import-findings --append-findings` include
`external_source` metadata but are created with `issue_recommended=false` and no
`issue_body_file`. Treat them as review leads until a human validates the
finding locally, revises the assessment/publication fields, and prepares an
Issue draft. Importing an external finding must not bypass the normal
Critical/High, Confirmed/Probable, and `issue_recommended=true` selection
criteria.

For Critical / High candidates, run or review the independent adversarial
validation stage before publication:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
# Add project-specific Python build/test commands; otherwise final_status remains needs-human-review.
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --validate --sandbox-profile local-test --build-command "python3 -m py_compile repo/app.py" --test-command "python3 -m py_compile repo/app.py"
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Then inspect `reports/COVERAGE.md`, `reports/gapfill-targets.json`,
`reports/ATTACK_CHAINS.md`, `reports/proofs.json`,
`reports/PROOFS.md`, optional `reports/traces.json`, optional
`reports/TRACE.md`, optional
`reports/remediation/<FINDING-ID>/patch-validation.json`,
`reports/validation.json`, and `reports/VALIDATION.md`.
High-risk targets with shallow coverage or unresolved gapfill recommendations
should be reviewed before claiming complete coverage in public Issue wording.
`downgrade`, `invalidate`, and `needs-human-review` decisions should block direct
publication until the finding metadata and issue draft have been revised or a
human reviewer explicitly accepts the residual uncertainty. The validation stage
must not create new findings; it only records decisions about existing findings
or chains. `ATTACK_CHAINS.md` is non-public by default and should be used for
remediation prioritization and disclosure planning, not copied wholesale into
public Issues. Proof artifacts are also local/private by default; use them to
refine Issue wording, not as public exploit evidence. Cross-repo trace artifacts
are experimental/P3 reachability evidence, not exploit proof; do not publish
them wholesale or use them to claim confirmed exploitability without human
review.

For multi-vote validation, inspect both the aggregate decision and the `votes`
array. `human-review-on-split` intentionally converts split vote outcomes into
`needs-human-review`; do not publish those findings until the split is resolved
or explicitly accepted by the operator.

## dry-run

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
```

If a finding uses `issue_body_file`, the path must be a relative `.md` file under
`reports/issue-drafts/`. `gra-issues` rejects absolute paths, `..` traversal,
symlinks, non-Markdown files, and oversized drafts before dry-run or apply
output is produced.

Dry-run output includes the default immutable publication plan path and the
SHA-256 hash of each issue body. Use those hashes to confirm exactly which
content is being reviewed.
It also writes `reports/issue-ledger.json`, a canonical local ledger that tracks
each finding's publication state (`not-selected`, `pending`, `dry-run`,
`published`, or `duplicate`), fingerprint, title, labels, body hash, source plan,
and GitHub Issue URL/number when available.
Dry-run and apply flows also write machine-readable duplicate decision records
under `reports/duplicate-decisions/`. Each record captures the finding ID,
fingerprint, candidate Issue numbers, exact-match status, variant markers,
root-cause and source-to-sink fingerprints, the final duplicate decision, and
the rationale reviewed before Issue creation.

## immutable publication plan

For high-impact or externally visible Issue creation, prefer the two-step plan
workflow. The plan is deterministic for a given `findings.json` and issue draft
set; it does not create GitHub Issues.

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
```

This writes:

```text
runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json
runs/OWNER__REPO/RUN_ID/reports/issue-ledger.json
```

The plan records the selected finding IDs, fingerprints, titles, labels, issue
body files, issue body SHA-256 hashes, public disclosure risk, run ID, repo,
commit, `chain_membership`, optional advisory `owner_routing`, and an
`advanced_validation` summary. The advanced
summary records whether related `reports/chains.json` records exist, whether
related adversarial validation records exist, whether safe local proof artifacts
exist or are explicitly not applicable, and any warnings that should be reviewed
before publication. Review the plan, referenced issue drafts, any
`reports/ATTACK_CHAINS.md` chain implications, any `reports/PROOFS.md` proof
limitations, and any `reports/VALIDATION.md` decisions before publishing.
When `owner_routing` is present, use it to route review or remediation; it is an
advisory hint derived from manual metadata, CODEOWNERS, or path heuristics, not
an authorization decision.

Warnings do not block publication by default. Operators that require advanced
evidence before publication can add:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
```

This stricter mode exits non-zero when a selected High/Critical finding lacks
the expected chain, proof, or adversarial-validation evidence, when related
validation decisions are `downgrade`, `invalidate`, or `needs-human-review`, or
when present remediation patch validation reports are `failed` /
`needs-human-review`.
Issue bodies do not include `ATTACK_CHAINS.md` contents; summarize only
reviewed remediation or disclosure implications in public text.

After review, apply the exact plan:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

`--apply-plan` recomputes issue body hashes and advanced-validation summaries,
verifies finding fingerprints, checks that selected findings still exist, and
rejects changed titles, labels, issue bodies, public disclosure risk, chain
membership, or advanced evidence state before it calls `gh issue create`.
When the plan is stale, rerun `--plan` and review the refreshed file before
applying. `--apply-plan ... --replan` refreshes the plan and exits without
publishing. The ledger is refreshed during `--plan` and `--replan` so operators
can distinguish pending, not-selected, and already-published findings from one
JSON artifact.

## apply

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply
```

Direct `--apply` remains available for already-reviewed private workflows, but
the plan workflow is recommended when approval must be bound to exact Issue
content.

## labels

Use `--create-labels` to create or update the common labels before publication.

## known-finding novelty filtering

Run `gra-novelty --run runs/OWNER__REPO/RUN_ID` before issue planning when the
run should be compared against local known-finding history. If
`reports/known-findings.json` exists, `gra-issues` excludes findings classified
as `duplicate`, `accepted-risk`, or `invalid-known` from default publication
selection. Findings classified as `better-example` or `regression` remain
eligible when they satisfy the normal severity/status filters.

The novelty ledger is local-only and stores hashes rather than raw evidence,
root-cause text, impact text, or issue bodies. Accepted-risk reasons are also
local-only, but operators must still avoid secrets or sensitive evidence in the
reason text.

## evidence graph review

Run `gra-evidence-graph --run runs/OWNER__REPO/RUN_ID` after advanced
validation and issue planning artifacts exist when reviewers need a single local
view of supporting/challenging evidence. The graph links findings to targets,
chains, proofs, validation, traces, remediation candidates, patch validation,
Issue plan entries, and metrics using bounded artifact references only; it does
not replace human review before publication.

## duplicate prevention

Issue bodies include a hidden marker:

```markdown
<!-- genai-repo-auditor:fingerprint=<fingerprint> -->
```

If an existing open Issue has the same fingerprint, `gra-issues` avoids creating
a duplicate.
`reports/issue-ledger.json` is checked before the GitHub fingerprint search.
When the ledger already records a published Issue for the same finding ID and
fingerprint, `gra-issues --apply` / `--apply-plan` skips creation even if the
current `gh issue list` search cannot find the marker. This makes re-running the
same publication command idempotent.
If a ledger has exactly one published entry for the same finding ID but the
current fingerprint has changed, `gra-issues` also skips creation and records
fingerprint drift in the ledger instead of opening a second Issue for the same
finding.
Before `gra-issues` creates or skips an Issue in apply mode, it writes
`reports/duplicate-decisions/<finding_id>.json` (or a fingerprint-suffixed file
when duplicate finding IDs would collide). The record distinguishes
`exact-duplicate`, `variant`, `related-not-duplicate`, and `new` decisions so
operators can audit why publication did or did not proceed.

To compare the ledger with the current open GitHub Issue inventory, run:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --verify-ledger
```

This command does not publish. It exits non-zero when a published ledger entry no
longer has a matching open Issue by fingerprint marker, when GitHub returns a
different Issue URL, or when a published/duplicate ledger entry lacks a matching
duplicate decision record. This lets final reconciliation detect both GitHub
inventory drift and missing publication-decision evidence.

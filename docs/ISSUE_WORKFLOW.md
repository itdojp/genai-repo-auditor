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
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-repo OWNER/consumer --mode prepare
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__shared-lib/RUN_ID/trace-consumers/OWNER__consumer --mode exec
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
`<reports_dir>/issue-drafts/` (default: `reports/issue-drafts/`). `gra-issues` rejects absolute paths, `..` traversal,
symlinks, non-Markdown files, and oversized drafts before dry-run or apply
output is produced.

Dry-run output is a preview only. It does not write
`reports/issue-publication-plan.json`, it does not create GitHub Issues, and it
sets `plan_written=false` plus `publication_plan_status=not-written-preview` in
`issues-created.json` and `reports/issue-ledger.json`. The preview prints the
path that would be used if the operator later promotes the same selection with
`--plan`, along with each issue body SHA-256 hash. Use those hashes to confirm
which candidate content is being reviewed, but treat the dry-run output as
unapproved preview material rather than an immutable publication record.
It also writes `reports/issue-ledger.json`, a canonical local ledger that tracks
each finding's publication state (`not-selected`, `pending`, `dry-run`,
`published`, or `duplicate`), fingerprint, title, labels, body hash, source plan,
and GitHub Issue URL/number when available.
Dry-run and apply flows also write machine-readable duplicate decision records
under `reports/duplicate-decisions/`. Each record captures the finding ID,
fingerprint, candidate Issue numbers, exact-match status, variant markers,
root-cause and source-to-sink fingerprints, the final duplicate decision, and
the rationale reviewed before Issue creation.

### machine-readable local summary

Each successful dry-run also writes the paired local artifacts:

```text
<reports_dir>/issue-dry-run-summary.json
<reports_dir>/ISSUE_DRY_RUN_SUMMARY.md
```

The JSON schema is closed and the Markdown is a sanitized aggregate: neither
contains a finding title, body, path, fingerprint, labels, or raw GitHub
response. It records `selection_source` as `current-findings` or
`verified-publication-plan`, plus the declared `visibility`. That visibility is
read from the run artifact, or from the verified plan for `--apply-plan ...
--dry-run`; it is **not** an online GitHub visibility lookup. Accordingly,
`github_visibility_lookup_performed` and
`github_duplicate_search_performed` are always `false`. Dry-run performs no
GitHub lookup or mutation and writes no immutable publication plan; the summary
also fixes `safety.github_mutation_performed=false`,
`safety.publication_plan_written=false`, and `counts.issues_created=0`.
`reports_dir` is read from the validated run context and defaults to `reports`;
findings, plans, ledgers, duplicate decisions, summary artifacts, and command
events remain under that same configured directory.

`would_create` means that a candidate reaches the local preview after applying
the declared visibility. It is not publication approval and does not attest to
the repository's current GitHub visibility. Apply mode performs the
authoritative online visibility check and can still refuse publication if the
local declaration is stale or incorrect.

The summary uses two disjoint count partitions. The all-finding selection
partition is:

```text
total_candidates = selected
                 + filtered_by_severity_or_status
                 + issue_recommendation_suppressed
                 + novelty_suppressed
```

The selected-candidate publication partition is:

```text
selected = duplicate_suppressed
         + advanced_validation_blocked
         + public_visibility_blocked
         + would_create
```

`filtered_by_severity_or_status` covers the configured severity/status filter;
`issue_recommendation_suppressed` covers `issue_recommended=false`; and
`novelty_suppressed` covers the local novelty-ledger classifications
`duplicate`, `accepted-risk`, and `invalid-known`. These three counters classify
all candidate findings before publication selection. `duplicate_suppressed` is
separate: it records a selected candidate matched by the existing local issue
ledger, not an online GitHub search. `advanced_validation_blocked` is non-zero
only when `--require-advanced-validation` blocks a selected candidate; the
command exits `4` after writing the summary when this strict mode finds such
blocks. `public_visibility_blocked` records a candidate rejected because the
declared visibility is `PUBLIC` or `UNKNOWN` without `--allow-public`, matching
apply mode's fail-closed visibility classes. `warnings` is an aggregate count
and is intentionally outside both partitions.

For `selection_source=verified-publication-plan`, the candidate universe is the
frozen plan entries rather than the original pre-plan finding set. Therefore
`total_candidates=selected` and the three pre-selection suppression counters
are zero; the second partition still classifies every verified plan entry.

Run `gra-metrics --run <run_dir>` after dry-run to consume the JSON directly.
The resulting `metrics.json` exposes `issue_dry_run` and explicitly reports an
absent/not-run artifact with `artifact_present=false` and zero counters.
`gra-dashboard` displays the resulting would-create and local suppression
counts; `gra-benchmark` consumes the same metrics fields for its workflow-health
summary. These consumers do not re-query GitHub or reinterpret finding content.

Validate both artifacts with the normal report validator, after regenerating
metrics when those downstream views are required:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID --check-freshness
```

The first validation checks that the JSON and Markdown summary are present
together when either exists, validates the closed schema and count invariants,
and rejects unsafe or oversized artifact paths. The final freshness check is
needed only when verifying the derived metrics/dashboard/benchmark catalog.

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
before publication. When the plan is written to the default tracked path
`reports/issue-publication-plan.json`, it also embeds a bounded
`report_freshness` generation-time snapshot. The live sidecar assessment, not
that static snapshot, is authoritative when the plan is applied. Review the
plan, referenced issue drafts, any
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
membership, or advanced evidence state before it calls `gh issue create`. When
the run has a tracked default plan record, its live `stale` and
`missing_dependency` freshness states are publication safety gates for every
supplied plan path, including a copied plan: apply is refused until the operator reruns
`gra-issues --run <run_dir> --plan` and performs another human review. When the
plan is stale, rerun `--plan` and review the refreshed file before applying.
`--apply-plan ... --replan` refreshes the plan and exits without publishing. The
ledger is refreshed during `--plan` and `--replan` so operators can distinguish
pending, not-selected, and already-published findings from one JSON artifact.
Replan accepts only the default tracked plan path; a custom-path replan fails
before writing and instructs the operator to regenerate the default plan.
Legacy report validation remains `not_applicable`, but `--apply-plan` fails
closed when the default tracked plan record or sidecar is absent. Regenerate the
default plan, review it, and then apply that plan or a reviewed copy. This is the
publication migration path for legacy and custom-plan workflows; normal
plan-content verification also remains mandatory.

## apply

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply
```

Direct `--apply` remains available for already-reviewed private workflows, but
the plan workflow is recommended when approval must be bound to exact Issue
content. Direct apply does not write an issue-publication plan; its
`issues-created.json` record uses `plan_written=false` and
`publication_plan_status=not-written-direct-apply`.

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

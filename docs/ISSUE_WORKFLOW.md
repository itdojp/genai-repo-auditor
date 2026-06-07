# Issue workflow

## 原則

Issue作成は監査runの一部ではありません。`findings.json` と `issue-drafts/*.md` を人間が確認した後に、`gra-issues` で作成します。

## default selection

既定では以下だけをIssue化します。

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

For Critical / High candidates, run or review the independent adversarial
validation stage before publication:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Then inspect `reports/COVERAGE.md`, `reports/gapfill-targets.json`,
`reports/ATTACK_CHAINS.md`, `reports/proofs.json`,
`reports/PROOFS.md`, optional `reports/traces.json`, optional
`reports/TRACE.md`, `reports/validation.json`, and `reports/VALIDATION.md`.
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
```

The plan records the selected finding IDs, fingerprints, titles, labels, issue
body files, issue body SHA-256 hashes, public disclosure risk, run ID, repo,
commit, `chain_membership`, and an `advanced_validation` summary. The advanced
summary records whether related `reports/chains.json` records exist, whether
related adversarial validation records exist, whether safe local proof artifacts
exist or are explicitly not applicable, and any warnings that should be reviewed
before publication. Review the plan, referenced issue drafts, any
`reports/ATTACK_CHAINS.md` chain implications, any `reports/PROOFS.md` proof
limitations, and any `reports/VALIDATION.md` decisions before publishing.

Warnings do not block publication by default. Operators that require advanced
evidence before publication can add:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
```

This stricter mode exits non-zero when a selected High/Critical finding lacks
the expected chain, proof, or adversarial-validation evidence, or when related
validation decisions are `downgrade`, `invalidate`, or `needs-human-review`.
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
publishing.

## apply

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply
```

Direct `--apply` remains available for already-reviewed private workflows, but
the plan workflow is recommended when approval must be bound to exact Issue
content.

## labels

`--create-labels` を指定すると、共通ラベルを作成または更新します。

## duplicate prevention

Issue本文には hidden marker を入れます。

```markdown
<!-- genai-repo-auditor:fingerprint=<fingerprint> -->
```

既存open Issueに同じ fingerprint がある場合は新規作成を避けます。

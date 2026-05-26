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
body files, issue body SHA-256 hashes, public disclosure risk, run ID, repo, and
commit. Review the plan and referenced issue drafts before publishing.

After review, apply the exact plan:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

`--apply-plan` recomputes issue body hashes, verifies finding fingerprints,
checks that selected findings still exist, and rejects changed titles, labels,
issue bodies, or public disclosure risk before it calls `gh issue create`.
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

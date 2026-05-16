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

## dry-run

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
```

If a finding uses `issue_body_file`, the path must be a relative `.md` file under
`reports/issue-drafts/`. `gra-issues` rejects absolute paths, `..` traversal,
symlinks, non-Markdown files, and oversized drafts before dry-run or apply
output is produced.

## apply

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply
```

## labels

`--create-labels` を指定すると、共通ラベルを作成または更新します。

## duplicate prevention

Issue本文には hidden marker を入れます。

```markdown
<!-- genai-repo-auditor:fingerprint=<fingerprint> -->
```

既存open Issueに同じ fingerprint がある場合は新規作成を避けます。

# GitHub Issue 作成ワークフロー

英語版は [`docs/ISSUE_WORKFLOW.md`](../ISSUE_WORKFLOW.md) を参照してください。この文書では、日本語運用者向けに安全な Issue 作成手順をまとめます。

## 原則

- Issue 作成は `gra-audit` の一部ではありません。
- `reports/findings.json` と `reports/issue-drafts/*.md` を人間が確認した後にだけ実行します。
- secret、credential、未検証の攻撃手順、過度に詳細な exploit 情報を GitHub Issue に出さないでください。
- public repository では公開開示になります。組織ポリシー、修正状況、関係者承認を確認してください。

## 既定の選択条件

`gra-issues` は既定で以下の finding だけを対象にします。

```text
severity: Critical / High
status: Confirmed / Probable
issue_recommended: true
```

条件を満たしていても、自動的に公開してよいという意味ではありません。evidence、impact、remediation、public disclosure risk を人間が確認してください。

## dry-run

最初は必ず dry-run を実行します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
```

`issue_body_file` を使う finding では、参照先は `reports/issue-drafts/` 配下の相対 `.md` file である必要があります。`gra-issues` は絶対 path、`..` traversal、symlink、non-Markdown file、過大な draft を拒否します。

## apply

Issue 本文、label、重複有無、公開可否を確認した後だけ apply します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

public repository への Issue 作成はデフォルトで拒否されます。公開が意図され、承認済みの場合だけ `--allow-public` を指定します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels --allow-public
```

## duplicate prevention

Issue 本文には hidden marker を入れます。

```markdown
<!-- genai-repo-auditor:fingerprint=<fingerprint> -->
```

既存 open Issue に同じ fingerprint がある場合は新規作成を避けます。fingerprint が placeholder、短すぎる値、重複値の場合は、Issue 化前に finding を修正してください。

## 作成前チェックリスト

- `gra-validate-report --run RUN_DIR` が成功している。
- `reports/findings.json` の severity、status、confidence、public disclosure risk が妥当である。
- `reports/issue-drafts/*.md` に secret の全文、token、credential、実 exploit 手順が含まれていない。
- scanner 由来の情報は repository context で到達可能性と影響を確認済みである。
- public repository の場合、`--allow-public` を使う根拠と承認が明確である。

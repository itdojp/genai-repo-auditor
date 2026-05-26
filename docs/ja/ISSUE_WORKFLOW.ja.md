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

Critical / High 候補は、公開前に独立した adversarial validation も実行または確認します。

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# shared-library / producer finding の consumer 到達可能性を確認する場合だけ:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

`reports/COVERAGE.md` と `reports/gapfill-targets.json` で high-risk target
に shallow coverage や unresolved gapfill recommendation が残っていないか
確認してください。

`reports/ATTACK_CHAINS.md` は non-public by default の内部資料です。
chain implications を remediation priority と disclosure planning に使い、
public Issue にそのまま貼り付けないでください。`reports/PROOFS.md` と
`reports/proofs/` は local/private by default の safe local proof artifact です。
proof limitations を Issue 文言に反映し、公開 exploit evidence として扱わないで
ください。`reports/traces.json` と `reports/TRACE.md` は experimental/P3 の
cross-repo reachability evidence であり exploit proof ではありません。
trace limitations を Issue 文言に反映し、confirmed exploitability として
扱う前に人間が確認してください。`reports/VALIDATION.md` と
`reports/validation.json` の `downgrade`、`invalidate`、`needs-human-review` は、
直接公開を止めるシグナルとして扱います。
finding metadata と Issue draft を修正するか、残る不確実性を人間が明示的に
受け入れるまで、confirmed exploitability として扱わないでください。

## dry-run

最初は必ず dry-run を実行します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
```

`issue_body_file` を使う finding では、参照先は `reports/issue-drafts/` 配下の相対 `.md` file である必要があります。`gra-issues` は絶対 path、`..` traversal、symlink、non-Markdown file、過大な draft を拒否します。

dry-run は既定の immutable publication plan path と、各 Issue body の
SHA-256 hash も表示します。承認対象の本文がどれかを確認するために
hash を利用してください。

## immutable publication plan

外部に見える Issue 作成や high-impact な公開操作では、二段階の plan
workflow を推奨します。plan は同じ `findings.json` と issue draft set
に対して deterministic であり、GitHub Issue は作成しません。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan
```

生成先:

```text
runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json
```

plan には selected finding ID、fingerprint、title、label、issue body
file、issue body SHA-256 hash、public disclosure risk、run ID、repo、
commit が記録されます。公開前に plan、参照される issue draft、
`reports/ATTACK_CHAINS.md`、`reports/PROOFS.md`、`reports/VALIDATION.md` を確認します。

承認後、同じ plan を apply します。

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

`--apply-plan` は Issue body hash、fingerprint、selected finding の存在、
title、label、public disclosure risk を再計算・検証し、plan 作成後に
変更された内容の公開を拒否します。plan が古くなった場合は `--plan` で
作り直し、再レビューしてから apply してください。`--apply-plan ... --replan`
は plan を更新して終了し、Issue は作成しません。

## apply

Issue 本文、label、重複有無、公開可否を確認した後だけ apply します。

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

private workflow で既に人間レビュー済みの場合は direct `--apply` も利用できます。
ただし、承認を exact Issue content に結び付ける必要がある場合は plan workflow
を使用してください。

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
- `reports/ATTACK_CHAINS.md` は non-public by default として扱い、Issue 本文にそのまま含めない。
- `reports/PROOFS.md` と `reports/proofs/` は local/private by default として扱い、Issue 本文にそのまま含めない。
- `reports/VALIDATION.md` の downgrade / invalidate / needs-human-review を確認し、必要な修正または明示承認が済んでいる。
- `reports/issue-drafts/*.md` に secret の全文、token、credential、実 exploit 手順が含まれていない。
- scanner 由来の情報は repository context で到達可能性と影響を確認済みである。
- public repository の場合、`--allow-public` を使う根拠と承認が明確である。

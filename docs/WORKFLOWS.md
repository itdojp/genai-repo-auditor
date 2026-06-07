# 通常使用と `/goal` 深掘りの使い分け

## 結論

通常運用は `codex exec` を使います。`/goal` は、通常監査で出た重要findingや特定カテゴリを深く検証するための supervised deep dive として使います。

| 観点 | 通常使用: `codex exec` | 深掘り: `/goal` |
|---|---|---|
| 主目的 | 一次監査、複数repo、定期実行 | 単一repo・単一finding・単一カテゴリの精査 |
| 実行形態 | 非対話 | 対話・監督あり |
| 推奨対象 | すべてのrepo | 重要repo、Critical/High候補、Needs human review |
| 成果物 | reports一式、findings.json、issue drafts | 通常成果物に加え、validation強化、deep-dives/*.md |
| 同時実行 | repo分離すれば限定的に可能 | 原則しない |
| Issue作成 | 監査後に別コマンド | goal後に別コマンド |
| 修正 | 別PR・別run | 同じgoalに混ぜない |

## 判断フロー

```text
新規repoまたは定期監査
  ↓
gra-audit --mode exec
  ↓
taxonomy preflight と findings.json を検証
  ↓
Critical / High が十分に裏付けられている?
  ├─ Yes → dry-run後にIssue化
  └─ No  → /goal deep dive
             ↓
           status/confidence更新
             ↓
           Issue化または棄却
```

## 使うコマンド

通常使用:

```bash
gra-audit --repo OWNER/REPO --mode exec --model gpt-5.5 --effort xhigh
```

深掘り:

```bash
gra-audit --repo OWNER/REPO --mode goal --model gpt-5.5 --effort xhigh
```

複数repo:

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec
```

Issue化:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

## 参照ドキュメント

- 通常使用: `docs/NORMAL_WORKFLOW.md`
- `/goal` 深掘り: `docs/GOAL_DEEP_DIVE_WORKFLOW.md`
- 複数repo: `docs/MULTI_REPO.md`
- Issue化: `docs/ISSUE_WORKFLOW.md`
- レポート契約: `docs/REPORT_CONTRACT.md`
- セキュリティモデル: `docs/SECURITY_MODEL.md`

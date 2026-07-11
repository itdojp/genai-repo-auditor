# 通常使用と `/goal` 深掘りの使い分け

## 結論

通常運用は `gra-audit --mode prepare` と宣言的 `gra-run` を使います。plan を確認してから
`--execute` し、必要時は同じ checkpoint を `--resume` します。個別 `gra-*` command と `/goal` は、重要 finding や特定カテゴリを深く検証する supervised deep dive
として使います。

| 観点 | 通常使用: `gra-run` | 深掘り: 個別 command / `/goal` |
|---|---|---|
| 主目的 | 一次監査、複数repo、定期実行 | 単一repo・単一finding・単一カテゴリの精査 |
| 実行形態 | 非対話 | 対話・監督あり |
| 推奨対象 | すべてのrepo | 重要repo、Critical/High候補、Needs human review |
| 成果物 | workflow plan/checkpoint、recon、target queue | findings、validation、deep-dives/*.md |
| 同時実行 | repo分離すれば限定的に可能 | 原則しない |
| Issue作成 | 監査後に別コマンド | goal後に別コマンド |
| 修正 | 別PR・別run | 同じgoalに混ぜない |

## 判断フロー

```text
新規repoまたは定期監査
  ↓
gra-doctor → gra-audit --mode prepare
  ↓
gra-run planning → 人間が plan を確認
  ↓
gra-run --execute / --resume
  ↓
target queue を確認し、選択 target を supervised command で調査
  ↓
findings.json を検証
  ↓
必要に応じて gra-gapfill で shallow coverage を requeue
  ↓
gra-chains で defensive chain を整理
  ↓
Critical / High は safe local proof artifact を生成
  ↓
共有 library / producer finding は必要に応じて gra-trace で consumer 到達可能性を確認
  ↓
Critical / High は adversarial validation で反証・降格余地を確認
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
RUNS_DIR="$PWD/runs"
gra-doctor --json --runs-dir "$RUNS_DIR"
gra-audit --repo OWNER/REPO --mode prepare --run-id first-audit --runs-dir "$RUNS_DIR"
RUN_DIR="$RUNS_DIR/OWNER__REPO/first-audit"
gra-run --run "$RUN_DIR" --profile recon-only
cat "$RUN_DIR/reports/WORKFLOW_PLAN.md"
gra-run --run "$RUN_DIR" --profile recon-only --execute --until recon
cat "$RUN_DIR/reports/WORKFLOW_EXECUTION.md"
gra-run --run "$RUN_DIR" --profile recon-only --resume
```

planning は非実行です。`--resume` は成功済み stage を繰り返しません。既存 checkpoint
は profile 切り替えには使えません。scanner execution、Issue 公開、remediation、
release、network 有効化は unattended profile の対象外です。

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
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-repo OWNER/consumer --mode prepare
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__shared-lib/RUN_ID/trace-consumers/OWNER__consumer --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-issues --run runs/OWNER__REPO/RUN_ID --dry-run
gra-issues --run runs/OWNER__REPO/RUN_ID --apply --create-labels
```

## 参照ドキュメント

- 通常使用: `docs/NORMAL_WORKFLOW.md`
- `/goal` 深掘り: `docs/GOAL_DEEP_DIVE_WORKFLOW.md`
- 複数repo: `docs/MULTI_REPO.md`
- Issue化: `docs/ISSUE_WORKFLOW.md`
- Target coverage / gapfill: `docs/TARGET_QUEUE.md`
- Defensive chain synthesis: `docs/ATTACK_CHAINS.md`
- Safe local proofs: `docs/SAFE_LOCAL_PROOFS.md`
- Cross-repo trace reachability: `docs/TRACE_REACHABILITY.md`
- Adversarial validation: `docs/ADVERSARIAL_VALIDATION.md`
- レポート契約: `docs/REPORT_CONTRACT.md`
- セキュリティモデル: `docs/SECURITY_MODEL.md`

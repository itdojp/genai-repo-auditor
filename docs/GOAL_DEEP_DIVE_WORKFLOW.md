# `/goal` 深掘りワークフロー

このドキュメントは、通常の `codex exec` 監査結果を起点に、Codex CLI の `/goal` を使って単一リポジトリまたは単一findingを深掘りする方法を定義します。

`/goal` は、長時間にわたり一つの目的に向かって作業させるための対話型ワークフローです。複数repoのバッチ処理には使わず、重要repoや高優先度findingの深掘りに限定します。

## `/goal` を使うべきケース

```text
- Critical / High 候補の真偽を詰めたい
- 認可・テナント分離・セッション処理の call path が長い
- CI/CD / GitHub Actions / supply chain の攻撃経路を精査したい
- 通常監査で Needs human review になったfindingを検証したい
- 監査対象が大規模で、checkpointごとに人間が監督したい
- 一次監査ではなく、特定カテゴリの専門レビューをしたい
```

使うべきでないケース:

```text
- 複数repoを機械的に監査したい
- Issueを自動で大量作成したい
- 修正まで無人で実行したい
- スコープが曖昧なまま「全部見て」と依頼したい
```

## 全体フロー

```text
1. 通常監査を exec で実行
   ↓
2. FINDINGS.md / findings.json を人間が確認
   ↓
3. 深掘り対象を決める
      - repo全体
      - 特定カテゴリ
      - 特定finding
   ↓
4. gra-audit --mode goal で run を準備
   ↓
5. Codex TUI を起動
   ↓
6. prompt.goal.md または deep-dive prompt を貼る
   ↓
7. /goal で状態確認しながら監督
   ↓
8. 必要に応じて /goal pause / resume / clear
   ↓
9. reports/ を検証し、chain / validation artifact を確認
   ↓
10. Issue化または修正計画へ進む
```

## 1. まず通常監査を実行する

深掘りは一次監査の後に行うのが基本です。

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

確認:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
less runs/OWNER__REPO/RUN_ID/reports/FINDINGS.md
```

## 2. 深掘り対象を選ぶ

代表的な対象:

```text
A. repo全体の深掘り
   - 初回監査が浅かった
   - 大規模repoで attack surface を再構築したい

B. 特定カテゴリの深掘り
   - Authorization
   - Tenant Isolation
   - CI/CD
   - Supply Chain
   - Secrets / Logging

C. 特定findingの深掘り
   - SEC-001 が本当に exploitable か確認したい
   - status を Potential から Confirmed / Invalid に確定したい
```

## 3. `/goal` 用 run を準備する

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode goal \
  --model gpt-5.5 \
  --effort xhigh
```

出力されるもの:

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md
  context.json
  findings.schema.json
  targets.schema.json
  validation.schema.json
  chains.schema.json
  proofs.schema.json
  repo/
  reports/
  prompt.goal.md
  prompts/
    goal/
      full-audit.goal.md
      validate-findings.goal.md
      deep-dive-finding.goal.md
      deep-dive-category.goal.md
      research-target.goal.md
      gapfill-target.goal.md
      variant-analysis.goal.md
      synthesize-chains.goal.md
      safe-proof.goal.md
      trace-reachability.goal.md
      adversarial-validate.goal.md
```

`gra-audit --mode goal` は Codex を実行せず、run directory と `/goal` プロンプトを準備するだけです。

## 4. Codex TUI を起動する

表示されたコマンドを使います。基本形:

```bash
codex \
  --cd runs/OWNER__REPO/RUN_ID \
  --skip-git-repo-check \
  --model gpt-5.5 \
  --enable goals \
  --sandbox workspace-write \
  --ask-for-approval on-request \
  -c 'model_reasoning_effort="xhigh"' \
  -c 'web_search="disabled"' \
  -c 'sandbox_workspace_write.network_access=false'
```

重要:

- Codex の cwd は `RUN_ID/` です。
- 対象repoの root では起動しません。
- これにより、対象repo内の `AGENTS.md` を監査制御指示として自動採用しにくくします。
- `repo/` は監査対象であり、基本的に read-only 扱いです。

## 5. repo全体の深掘り

Codex TUI に `prompt.goal.md` の中身を貼ります。

```bash
cat runs/OWNER__REPO/RUN_ID/prompt.goal.md
```

この goal は以下を要求します。

```text
- inventory
- threat model
- attack surface map
- category-by-category review
- Critical / High の安全な検証
- reports/FINDINGS.md
- reports/findings.json
- reports/COVERAGE.md
- reports/ATTACK_CHAINS.md
- reports/PROOFS.md
- reports/TRACE.md (cross-repo trace を実行した場合)
- reports/VALIDATION.md
- reports/issue-drafts/*.md
- reports/AUDIT_LOG.md
```

## 6. 特定findingの深掘り

通常監査後、たとえば `SEC-003` を検証する場合です。

```bash
mkdir -p .codex-local/tmp/goal-prompts
cp runs/OWNER__REPO/RUN_ID/prompts/goal/deep-dive-finding.goal.md .codex-local/tmp/goal-prompts/deep-dive-sec-003.goal.md
```

`.codex-local/tmp/goal-prompts/deep-dive-sec-003.goal.md` のプレースホルダを編集します。

```text
TARGET_FINDING_ID: SEC-003
TARGET_QUESTION: is this authorization bypass reachable for a non-admin authenticated user?
```

Codex TUI に編集済みプロンプトを貼ります。

深掘り結果として期待する更新:

```text
reports/deep-dives/SEC-003.md
reports/FINDINGS.md
reports/findings.json
reports/issue-drafts/SEC-003.md
reports/AUDIT_LOG.md
```

採用基準:

```text
- call path が明確
- entry point が明確
- trust boundary が明確
- 既存middleware / policy / framework protectionを確認済み
- status が Confirmed / Probable / Potential / Invalid / Needs human review に再分類されている
```

## 7. 特定カテゴリの深掘り

例: テナント分離を深掘りする場合。

```bash
mkdir -p .codex-local/tmp/goal-prompts
cp runs/OWNER__REPO/RUN_ID/prompts/goal/deep-dive-category.goal.md .codex-local/tmp/goal-prompts/deep-dive-tenant.goal.md
```

編集:

```text
TARGET_CATEGORY: Tenant Isolation
TARGET_SCOPE: API routes, data access layer, repository/query modules, background jobs that read or mutate tenant-scoped data
```

Codex TUI に貼ります。

カテゴリ別深掘りでは、以下を強制します。

```text
- security invariants の定義
- entry point / trust boundary / state transition / sensitive sink の整理
- 具体的な call path 追跡
- 既存findingとの重複排除
- findings.json の strict JSON 維持
```

## 8. `/goal` 実行中の操作

現在の goal を確認:

```text
/goal
```

一時停止:

```text
/goal pause
```

再開:

```text
/goal resume
```

終了または方向転換:

```text
/goal clear
```

途中で確認すべき観点:

```text
- repo/ 配下が変更されていないか
- reports/AUDIT_LOG.md に進捗とコマンドが残っているか
- Critical / High が十分な証拠なしに断定されていないか
- reports/COVERAGE.md
- reports/ATTACK_CHAINS.md が non-public by default として扱われているか
- reports/PROOFS.md が local/private by default として扱われているか
- reports/VALIDATION.md の downgrade / invalidate / needs-human-review が反映されているか
- secret 値が全文出力されていないか
- public repo で disclosure risk が考慮されているか
```

ローカル確認例:

```bash
git -C runs/OWNER__REPO/RUN_ID/repo status --short
sed -n '1,200p' runs/OWNER__REPO/RUN_ID/reports/AUDIT_LOG.md
```

## 9. 深掘り後の検証

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode goal
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

必要なら、検証専用goalを実行します。

```bash
cat runs/OWNER__REPO/RUN_ID/prompts/goal/validate-findings.goal.md
```

この goal は Critical / High の false positive を減らすために使います。

## 10. Issue化

深掘りで status / confidence / issue_recommended が更新され、
`ATTACK_CHAINS.md`、`PROOFS.md`、`VALIDATION.md` のレビュー結果が
Issue draft に反映された後に dry-run します。

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --dry-run
```

問題なければ:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply \
  --create-labels
```

## 11. 深掘り用の停止条件

`/goal` は必ず停止条件を持たせます。

良い停止条件:

```text
- 対象findingの status が Confirmed / Probable / Potential / Invalid / Needs human review のいずれかに確定
- findings.json が strict JSON のまま
- issue draft が最終判断と一致
- repo/ 配下が未変更
- AUDIT_LOG.md にコマンド、判断、未解決点が記録済み
```

悪い停止条件:

```text
- できるだけ深く調べる
- 可能な限り脆弱性を探す
- 全部直す
- Issueも作る
```

## 12. 深掘りから修正へ進む場合

このラボの標準方針では、監査・検証・Issue作成・修正を同じ goal に混ぜません。

推奨:

```text
1. /goal で深掘り
2. findings.json を検証
3. GitHub Issue 作成
4. 担当者または別PRで修正
5. 修正後に別 run で再監査または validate
```

修正まで Codex にさせる場合でも、別ブランチ・別run・別プロンプトに分けます。

## 13. 実務上の運用ルール

```text
- /goal は単一repo・単一テーマに限定する
- 同時に複数の /goal を走らせない
- goal中にIssue作成しない
- goal中にrepo/ を編集しない
- goal中にネットワークを許可しない
- pause/resume を使って人間が節目で確認する
- Critical / High は必ず validation status を更新する
```

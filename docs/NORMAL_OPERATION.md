# 通常使用ワークフロー: `codex exec` による汎用セキュリティ監査

このワークフローは、複数リポジトリを継続的に監査し、ローカルにレポートを残し、必要なものだけ GitHub Issue 化するための標準運用です。

通常使用では `/goal` は使いません。`codex exec` で非対話実行し、run ごとの成果物を機械的に保存します。

## 目的

- GitHub リポジトリを実行時に指定して監査する。
- 対象リポジトリには監査テンプレートを常設しない。
- 監査結果は `runs/<OWNER__REPO>/<RUN_ID>/reports/` に保存する。
- GitHub Issue 作成は監査完了後の明示ステップに分ける。
- public repository への脆弱性情報公開をデフォルトで防ぐ。

## 全体フロー

```text
1. repo指定
   ↓
2. gra-audit が run directory を作成
   ↓
3. 対象repoを runs/.../repo/ に clone
   ↓
4. Codexを run directory で codex exec 実行
   ↓
5. reports/ に監査レポートと findings.json を生成
   ↓
6. gra-taxonomy-preflight と gra-validate-report で taxonomy とレポート契約を検証
   ↓
7. 必要に応じて gra-gapfill で shallow coverage を requeue
   ↓
8. gra-chains で既存 evidence の defensive chain を整理
   ↓
9. Critical / High は gra-proofs で safe local proof artifact を生成
   ↓
10. 必要に応じて gra-trace で cross-repo reachability を確認
   ↓
11. Critical / High は gra-adversarial-validate で反証・降格余地を確認
   ↓
12. 人間が FINDINGS.md / COVERAGE.md / ATTACK_CHAINS.md / PROOFS.md / TRACE.md / VALIDATION.md / issue-drafts を確認
   ↓
13. gra-issues --dry-run
   ↓
14. gra-issues --apply
   ↓
15. GitHub Issue 上で修正PR・期限・担当者を管理
```

## セットアップ

```bash
cd genai-repo-auditor
chmod +x bin/*
export PATH="$PWD/bin:$PATH"

gh auth status
codex --help >/dev/null
python3 --version
```

推奨依存:

```text
git
gh
codex
python3
rg
jq
flock
```

## 単一リポジトリ監査

最小実行:

```bash
gra-audit --repo OWNER/REPO --mode exec
```

GPT-5.5 / xhigh を明示:

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

特定ブランチまたは ref:

```bash
gra-audit \
  --repo OWNER/REPO \
  --branch main \
  --mode exec
```

## 実行ディレクトリ構成

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md                 # 監査ランナー側の制御指示
  context.json              # repo / commit / branch / visibility
  findings.schema.json      # findings.json の契約
  targets.schema.json       # targets.json の契約
  validation.schema.json    # validation.json の契約
  chains.schema.json        # chains.json の契約
  proofs.schema.json        # proofs.json の契約
  repo/                     # clone された対象repo。原則 read-only 扱い
  reports/
    AUDIT_SUMMARY.md
    THREAT_MODEL.md
    ATTACK_SURFACE.md
    FINDINGS.md
    findings.json
    ATTACK_CHAINS.md
    chains.json
    PROOFS.md
    proofs.json
    proofs/
    VALIDATION.md
    validation.json
    AUDIT_LOG.md
    issue-drafts/
      SEC-001.md
  prompt.exec.md
  prompt.goal.md
  codex-events.jsonl
  codex-stderr.txt
  codex-final.md
  report-validation.txt
  run-summary.txt
```

重要点:

- Codex の作業ディレクトリは `RUN_ID/` です。
- 対象repoは `repo/` 配下にあります。
- Codex が書き込んでよいのは `reports/` 配下のみです。
- `repo/AGENTS.md` は対象repo由来の untrusted input として扱います。

## レポート検証

監査後に自動でも実行されますが、手動でも確認できます。

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

検証対象:

- `reports/findings.json` が strict JSON であること
- 必須キーが存在すること
- severity / confidence / status が許可値であること
- fingerprint が空でないこと
- Issue 推奨 finding に issue draft が存在すること
- chain output がある場合は既存 finding / target / scanner ref を参照していること
- target coverage metadata がある場合は review_depth、files_reviewed/skipped、
  unresolved_questions、gapfill_recommended が妥当であること
- proof output がある場合は既存 finding を参照し、safe_by_design が true であること
- trace output がある場合は producer finding、consumer entry point、sink、limitations が妥当であり、exploit proof と誤認しないこと
- adversarial validation output がある場合は subject、decision、evidence list が妥当であること

## レポート確認

人間が最低限確認するファイル:

```text
reports/AUDIT_SUMMARY.md
reports/FINDINGS.md
reports/findings.json
reports/COVERAGE.md
reports/ATTACK_CHAINS.md
reports/PROOFS.md
reports/VALIDATION.md
reports/issue-drafts/*.md
report-validation.txt
codex-final.md
```

採用基準:

```text
- Critical / High は file:line, entry point, trust boundary, call path が必須
- Confirmed / Probable 以外は原則 Issue 化しない
- `ATTACK_CHAINS.md` は non-public by default として扱い、public Issue にそのまま貼らない
- `PROOFS.md` は local/private by default として扱い、public Issue にそのまま貼らない
- `VALIDATION.md` の downgrade / invalidate / needs-human-review は公開前に修正または明示承認する
- `COVERAGE.md` と `gapfill-targets.json` で high-risk target の shallow
  review や unresolved question が残っていないか確認する
- Generic hardening advice は Issue 化しない
- public repo では public_disclosure_risk を確認する
- secret 値が全文出力されていないことを確認する
```

## Adversarial validation

Critical / High の Issue 候補は、公開前に独立した反証・降格チェックを行います。

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/OWNER__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/OWNER__consumer/RUN_ID --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

`gra-chains` は既存 finding / target / scanner ref を防御的に接続し、
`ATTACK_CHAINS.md` を non-public by default の内部資料として出力します。
このステージは exploit payload や weaponized step を生成してはいけません。

`gra-proofs` は既存 finding に対して safe local proof artifact を生成します。
これは local/private by default の検証補助資料であり、working exploit、
credential extraction、live service probing、dependency installation、
target repo modification を含めてはいけません。

`gra-trace` は experimental/P3 の cross-repo reachability stage です。
`reports/traces.json` と `reports/TRACE.md` は reachability evidence であり
exploit proof ではありません。external scanning、production/staging probing、
exploit payload、credential access、dependency installation、producer/consumer
repo modification は禁止です。

Adversarial validation は新しい finding を作りません。`reports/VALIDATION.md` の
`downgrade`、`invalidate`、`needs-human-review` は、Issue draft と
`findings.json` を見直す根拠として扱います。

## Issue 作成

まず dry-run:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --dry-run
```

実作成:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply \
  --create-labels
```

既定では以下だけが対象です。

```text
severity: Critical / High
status: Confirmed / Probable
issue_recommended: true
```

Medium 以上も起票する場合:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply \
  --min-severity Medium
```

public repo への Issue 作成はデフォルトで拒否されます。意図的に公開する場合だけ:

```bash
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply \
  --allow-public
```

## 複数リポジトリ監査

`repos.txt`:

```text
ORG/repo-a
ORG/repo-b
ORG/repo-c
```

逐次実行:

```bash
gra-batch \
  --repo-list repos.txt \
  --concurrency 1 \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

並列実行は最初から使わないでください。運用が安定してから `--concurrency 2` 程度に抑えます。

```bash
gra-batch \
  --repo-list repos.txt \
  --concurrency 2 \
  --mode exec
```

同一repoの同時監査は lock で防ぎます。`--no-lock` は通常使いません。

## run index

複数runのサマリを作ります。

```bash
gra-index --runs-dir runs
```

出力:

```text
runs/index.json
runs/index.md
```

## 通常使用での判断基準

通常使用で十分なケース:

- 新規repoの一次セキュリティ監査
- 複数repoの横断監査
- 定期監査
- findings.json と Issue draft を安定的に生成したい
- 人間レビュー後に Issue 化したい

`/goal` 深掘りに切り替えるべきケース:

- Critical / High 候補が出たが証拠が弱い
- 認可・テナント分離など call path が長い
- CI/CD や supply chain の攻撃経路を深く確認したい
- false positive かどうか判断が難しい
- 特定findingの修正方針まで詰めたい

## 禁止パターン

```text
- 監査とIssue作成を同じCodex runに混ぜる
- 監査と修正を同じCodex runに混ぜる
- public repo で無確認の脆弱性Issueを作る
- ネットワークアクセスをデフォルトで許可する
- danger-full-access を通常監査で使う
- 同一repoに複数Codexを同時に走らせる
```

# 使い方: 主要運用ワークフロー

この文書は、GenAI Repo Auditor を使う日本語運用者向けの概要です。詳細なオプション、成果物、exit status は英語版 [`docs/COMMAND_REFERENCE.md`](../COMMAND_REFERENCE.md) を参照してください。

## 基本方針

- 監査対象 repository は `repo/` 配下に clone される untrusted input として扱います。
- 監査成果物、clone された対象 repository、scanner output、API key、token、secret、実 repository の未検証 finding は commit しないでください。
- `--mode exec` は非対話実行です。既定では Codex sandbox の network access は無効です。
- GitHub Issue 作成は監査とは独立した opt-in 手順です。必ず dry-run と人間の確認を先に行います。

## install -> plan -> review -> execute -> resume

初回導入は [`LOCAL_INSTALL_AND_AUDIT.ja.md`](LOCAL_INSTALL_AND_AUDIT.ja.md) に沿ってください。
readiness 確認後、`prepare` mode で run を生成します。worker はまだ実行されません。

```bash
RUNS_DIR="$HOME/.local/state/genai-repo-auditor/runs"
gra-doctor --json --runs-dir "$RUNS_DIR"
gra-audit --repo OWNER/REPO --mode prepare --run-id first-audit --runs-dir "$RUNS_DIR"
RUN_DIR="$RUNS_DIR/OWNER__REPO/first-audit"
```

planning は stage を実行しません。plan を確認してから reconnaissance までの限定範囲を
実行し、execution report を確認して同じ checkpoint を resume します。

```bash
gra-run --run "$RUN_DIR" --profile recon-only
cat "$RUN_DIR/reports/WORKFLOW_PLAN.md"
gra-run --run "$RUN_DIR" --profile recon-only --execute --until recon
cat "$RUN_DIR/reports/WORKFLOW_EXECUTION.md"
gra-run --run "$RUN_DIR" --profile recon-only --resume
gra-targets --run "$RUN_DIR" --list
```

`--resume` は成功済み stage を再実行しません。1 checkpoint は 1 profile に対応します。
別 profile を同じ checkpoint 上で順次実行しないでください。`appsec-deep`、
`publication-ready`、`full` は required input がそろった workflow checkpoint が存在しない互換性のある run、または
supervised `--from` range で選択します。

target queue の確認後は、`gra-research` などの個別 command または `/goal` を supervised
path として使用します。`gra-targets --generate` は active wave と
deferred wave を含む決定的 queue を `reports/targets.json` に書き込みます。
既定値は total budget 20、budgeted seed source ごとに 10、policy は
`risk-weighted` です。`gra-research`、`gra-targets --show`、
`gra-targets --list` は active seed と予算外保持レコードを含む `targets[]` だけを扱うため、deferred target を
調査する前に `gra-targets --rebalance` で昇格させてください。queued gapfill
と非 `queued` の履歴 target は seed budget の外側で保持されます。reporting
profile の完了後は次を再生成します。

```bash
gra-metrics --run "$RUN_DIR"
gra-evidence-graph --run "$RUN_DIR"
gra-validate-report --run "$RUN_DIR"
```

`gra-targets --rebalance` は既存の `reports/targets.json` だけを読み、model や
network call を行わずに queue budget / dedup を再計算します。たとえば
scanner target の昇格は次のように実行します。

`gra-targets --mark` / `gra-research` の status 更新だけでは queue を再選択せず、deferred target を暗黙昇格しません。新しい review wave は `--rebalance` を明示したときだけ選択されます。`queue_summary.selection_input_ids` は直近の明示的選択時に存在した target ID の基準集合を保持し、deferred ID を後追加 target として再分類する不整合を拒否します。source は producer-written `queue_source` で固定し、model-controlled ID prefix は信頼しません。marker のない legacy target は移行時に `model_generated` として扱います。

```bash
gra-targets --run "$RUN_DIR" --rebalance \
  --target-budget 30 \
  --max-scanner-targets 12 \
  --budget-policy risk-weighted
```

`gra-research --mode goal` の準備時には、生成済み seed / prompt が参照する ID を
後続 rebalance から保護するため、対象 status が `in_progress` に更新されます。
準備した review を中止する場合は、`gra-targets --mark` で status を明示的に戻してください。

scanner stage は計画のみです。Issue 公開、remediation、release、GitHub mutation、network
有効化は unattended profile の対象外です。Issue dry-run も、finding、evidence、Issue
draft が生成・検証された後に別途実行します。

```bash
gra-issues --run "$RUN_DIR" --dry-run
```

実際の Issue 作成は公開可否を人間が承認した後だけ実行してください。public repository
への作成はデフォルトで拒否され、承認済みの場合だけ `--allow-public` を併用します。

## 監査 run の一時停止と再開

本体更新や handoff のために監査を意図的に止める場合は、`blocked` ではなく
`paused` state を記録します。

```bash
gra-run-state --run "$RUN_DIR" --pause \
  --reason "maintainer update window" \
  --resume-target TGT-AGENT-234 \
  --resume-condition "main branch updated and post-merge CI passed" \
  --final-reconcile "published known findings: 52; unpublished Medium+: 0"
gra-run-state --run "$RUN_DIR" --status
gra-run-state --run "$RUN_DIR" --resume
```

paused 中は read-only status check のみに制限してください。`gra-research`、
`gra-gapfill --generate`、`gra-gapfill --target`、`gra-targets --generate`、
`gra-targets --mark` は paused state を検出すると開始を拒否します。

## 宣言的 workflow の実行と再開

`gra-run` はデフォルトでは計画のみを生成します。計画を確認した後、明示的な
`--execute` でのみ、profile で承認されたローカル command を依存順に実行します。
組み込み profile は `recon-only`、`supply-chain`、`appsec-deep`、
`publication-ready`、`full` です。scanner stage は計画のみであり、外部 scanner
を実行しません。Issue 公開は全 profile の対象外です。

```bash
gra-run --run "$RUN_DIR" --profile recon-only
gra-run --run "$RUN_DIR" --profile recon-only --execute --until recon
gra-run --run "$RUN_DIR" --profile recon-only --resume
```

再開用の実行状態は `<reports_dir>/workflow-checkpoint.json` に保存されます。
各 checkpoint 更新時に、確認用の `<reports_dir>/workflow-execution.json` と
`<reports_dir>/WORKFLOW_EXECUTION.md` も更新されます。確認用 report には stage の
status・duration・失敗分類・scoped skip・blocked dependency・未実行理由・resume
stage だけを記録し、raw prompt、finding/evidence 本文、credential、private reasoning、
Issue 公開内容は複製しません。`--resume` は
run/profile/plan と成功済み出力の SHA-256 を照合し、成功済み stage を再実行せず、
記録済み resume stage から再開します。run state が `paused` または `blocked` の
場合は実行を拒否します。orchestrator は network flag や Issue/release/remediation
publication command を暗黙に追加しません。resume は既存 plan/checkpoint の完全性を
plan 更新前に検証し、plan 自体は書き換えず、checkpoint と execution report だけを
更新します。

`--until` による範囲実行、stage failure、interruption の場合も、未実行 stage を
黙って除外せず、`range_continuation`、`blocked_by_dependency`、`interrupted` などの
限定された理由を execution report に残します。reporting stage を含む profile では、
terminal status と `gra-run` completion event を反映するため、完了後に次の順序で
再生成してください。

```bash
gra-metrics --run "$RUN_DIR"
gra-evidence-graph --run "$RUN_DIR"
gra-validate-report --run "$RUN_DIR"
```

`gra-targets --rebalance` は既存の `reports/targets.json` だけを読み、model や
network call を行わずに queue budget / dedup を再計算します。たとえば
scanner target の昇格は次のように実行します。

```bash
gra-targets --run "$RUN_DIR" --rebalance \
  --target-budget 30 \
  --max-scanner-targets 12 \
  --budget-policy risk-weighted
```

workflow 成功は Issue 公開承認を意味しません。Issue 公開は引き続き人手で
review した別 command として扱います。

## 主要成果物

```text
runs/OWNER__REPO/RUN_ID/
  context.json
  repo/                       # 監査対象 repository。untrusted input
  prompts/
  reports/
    findings.json             # validation / issue workflow の入力
    FINDINGS.md
    COVERAGE.md               # target coverage / gapfill の summary
    gapfill-targets.json      # gapfill requeue の機械可読出力
    targets.json              # active/deferred queue、queue_summary、source lineage
    chains.json               # defensive chain synthesis の機械可読出力
    ATTACK_CHAINS.md          # non-public by default の chain summary
    proofs.json               # safe local proof artifact の機械可読出力
    PROOFS.md                 # local/private by default の proof summary
    proofs/                   # benign proof support files
    traces.json               # cross-repo trace reachability の機械可読出力
    TRACE.md                  # reachability evidence。exploit proof ではない
    validation.json           # adversarial validation の機械可読出力
    VALIDATION.md             # Issue 作成前に確認する検証サマリ
    run-state.json            # paused/resume/blocked の run-level state
    workflow-plan.json        # gra-run の実行前計画
    WORKFLOW_PLAN.md
    workflow-checkpoint.json  # resume integrity 用の実行 checkpoint
    workflow-execution.json   # bounded な実行 status/duration/absence reason
    WORKFLOW_EXECUTION.md
    issue-drafts/             # Issue 本文候補。人間が確認する
    scanner-results/          # 任意で取り込んだ scanner output
  codex-final.md
  codex-events.jsonl
  report-validation.txt
  run-summary.txt
```

`run-summary.txt` には `codex_status`、`target_queue_status`、`validation_status`、`final_status` が記録されます。exec output に `targets.json` がある場合、`target_queue_status` は model source binding と既定 deterministic rebalance の結果です。CI や batch automation では `final_status=0` を成功条件として扱ってください。

## 複数 repository の監査

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec
```

1 件以上失敗した場合、既定では batch 全体も non-zero exit になります。失敗を許容する場合のみ `--allow-failures` を使います。

## workflow DAG の計画

`gra-run` は既定で planning-only です。version 固定の profile resource、dependency
order、required input、scoped skip を検証し、stage command は実行しません。

```bash
gra-run --run "$RUN_DIR" --profile recon-only
gra-run --run "$RUN_DIR" --profile recon-only --skip targets --json
```

`<reports_dir>/workflow-plan.json` と `WORKFLOW_PLAN.md` には sanitized argv と
run-relative artifact ref のみを記録します。network、GitHub Issue mutation、release、
raw prompt/finding/evidence/credential は plan に含めません。デフォルトは計画のみで、
明示的な `--execute` または `--resume` の場合だけ stage を実行し、checkpoint と
execution report を更新します。

## scanner output の取り込み

実行前に、non-executing な adapter list/plan で command、sandbox、network、path、
output limit を確認できます。

```bash
gra-scan --run "$RUN_DIR" --list
gra-scan --run "$RUN_DIR" --tool gitleaks --plan
gra-scan --run "$RUN_DIR" --tool gitleaks --execute --sandbox-profile container --json
```

list/plan は scanner を実行しません。`--execute` は事前取得した digest 固定 image を
network 無効・read-only target mount の local container で明示実行し、成功した raw
JSON を run directory に保持します。成功時は normalized lead、scanner index、
`scanner-runs.json` / `SCANNER_RUNS.md`、sanitized command event も自動生成します。
raw output と normalized lead は未確認の `review-only` evidence です。外部 scanner
output を手動取り込みする場合は `gra-ingest` を使用し、確認には triage stage を使用します。

```bash
gra-ingest --run "$RUN_DIR" --tool semgrep --file semgrep.json --format json
gra-scanner-triage --run "$RUN_DIR"
```

scanner output は未確認の lead です。secret 値の全文引用や再構成は禁止です。詳細は [`SCANNER_INTEGRATION.ja.md`](SCANNER_INTEGRATION.ja.md) を参照してください。

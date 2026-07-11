# 使い方: 主要運用ワークフロー

この文書は、GenAI Repo Auditor を使う日本語運用者向けの概要です。詳細なオプション、成果物、exit status は英語版 [`docs/COMMAND_REFERENCE.md`](../COMMAND_REFERENCE.md) を参照してください。

## 基本方針

- 監査対象 repository は `repo/` 配下に clone される untrusted input として扱います。
- 監査成果物、clone された対象 repository、scanner output、API key、token、secret、実 repository の未検証 finding は commit しないでください。
- `--mode exec` は非対話実行です。既定では Codex sandbox の network access は無効です。
- GitHub Issue 作成は監査とは独立した opt-in 手順です。必ず dry-run と人間の確認を先に行います。

## install -> first audit -> validation -> issue dry-run

初回導入は [`LOCAL_INSTALL_AND_AUDIT.ja.md`](LOCAL_INSTALL_AND_AUDIT.ja.md) に沿ってください。概要は以下です。

```bash
export GRA_HOME="$HOME/.local/opt/genai-repo-auditor"
git clone https://github.com/itdojp/genai-repo-auditor.git "$GRA_HOME"
export PATH="$GRA_HOME/bin:$PATH"
```

対象 repository へアクセスできることを確認します。

```bash
gh auth status
gh repo view OWNER/REPO --json nameWithOwner,visibility,defaultBranchRef
```

最初は `prepare` mode で clone と prompt 生成だけを確認します。Codex は実行されません。

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode prepare \
  --run-id first-prepare
```

full audit は `exec` mode で実行します。

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

`gra-audit` が表示した run directory を `RUN_DIR` として扱います。

```bash
RUN_DIR="$GRA_HOME/runs/OWNER__REPO/RUN_ID"
gra-validate-report --run "$RUN_DIR"
gra-gapfill --run "$RUN_DIR" --generate
gra-chains --run "$RUN_DIR"
gra-proofs --run "$RUN_DIR" --all-critical-high
# shared-library / producer finding の consumer 到達可能性を確認する場合:
# gra-trace --producer-run "$RUN_DIR" --finding SEC-001 --consumer-repo OWNER/consumer --mode prepare
# gra-trace --producer-run "$RUN_DIR" --finding SEC-001 --consumer-run "$RUN_DIR/trace-consumers/OWNER__consumer" --mode exec
gra-adversarial-validate --run "$RUN_DIR" --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run "$RUN_DIR"
gra-issues --run "$RUN_DIR" --dry-run
```

Issue 作成は、finding、evidence、non-public by default の
`reports/COVERAGE.md`、`reports/gapfill-targets.json`、
`reports/ATTACK_CHAINS.md`、local/private by default の
`reports/PROOFS.md`、experimental/P3 の reachability evidence である
`reports/TRACE.md`、`reports/VALIDATION.md`、
`reports/issue-drafts/*.md`、公開可否を人間が確認した後だけ実行します。

```bash
gra-issues --run "$RUN_DIR" --apply --create-labels
```

public repository への Issue 作成はデフォルトで拒否されます。公開が意図され、組織ポリシー上承認済みの場合だけ `--allow-public` を併用してください。

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

実行状態は `<reports_dir>/workflow-checkpoint.json` に保存されます。`--resume` は
run/profile/plan と成功済み出力の SHA-256 を照合し、成功済み stage を再実行せず、
記録済み resume stage から再開します。run state が `paused` または `blocked` の
場合は実行を拒否します。orchestrator は network flag や Issue/release/remediation
publication command を暗黙に追加しません。

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
    issue-drafts/             # Issue 本文候補。人間が確認する
    scanner-results/          # 任意で取り込んだ scanner output
  codex-final.md
  codex-events.jsonl
  report-validation.txt
  run-summary.txt
```

`run-summary.txt` には `codex_status`、`validation_status`、`final_status` が記録されます。CI や batch automation では `final_status=0` を成功条件として扱ってください。

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
raw prompt/finding/evidence/credential は plan に含めません。workflow execution と
resume/checkpoint は後続フェーズの機能であり、この planning command では実行されません。

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

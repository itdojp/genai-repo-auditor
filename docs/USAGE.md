# Usage

この文書は主要ワークフローの概要です。全 `gra-*` コマンドの詳細オプション、成果物、exit status、注意事項は [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md) を参照してください。

## 通常使用: 宣言的 workflow による単一 repo 監査

初回は readiness を確認し、`prepare` で run を作成してから、既定の planning-only
`gra-run` で実行計画を確認します。

```bash
RUNS_DIR="$PWD/runs"
gra-doctor --json --runs-dir "$RUNS_DIR"
gra-audit --repo OWNER/REPO --mode prepare --run-id first-audit --runs-dir "$RUNS_DIR"
RUN_DIR="$RUNS_DIR/OWNER__REPO/first-audit"
gra-run --run "$RUN_DIR" --profile recon-only
cat "$RUN_DIR/reports/WORKFLOW_PLAN.md"
```

確認後に限定範囲を実行し、同じ checkpoint を resume します。成功済み stage は
再実行されません。

```bash
gra-run --run "$RUN_DIR" --profile recon-only --execute --until recon
cat "$RUN_DIR/reports/WORKFLOW_EXECUTION.md"
gra-run --run "$RUN_DIR" --profile recon-only --resume
gra-targets --run "$RUN_DIR" --list
```

`gra-run` の plan は command を実行しません。`--execute` / `--resume` だけが profile
内の offline / local-artifacts-only command を実行します。1 checkpoint は 1 profile
に対応し、別 profile へ切り替える用途には使えません。`appsec-deep`、
`publication-ready`、`full` は `findings.json` などの required input が存在する workflow checkpoint が存在しない互換性のある run、または supervised `--from` range で選択します。

scanner stage は `gra-scan --plan` のみです。Issue 公開、remediation、release、network
有効化は profile 外にあり、個別 command と人間の承認が必要です。target research や
project-specific validation には、後述の個別 command または `/goal` を supervised path
として使用します。

reporting profile の terminal completion 後は、最終 execution state を反映します。

```bash
gra-metrics --run "$RUN_DIR"
gra-evidence-graph --run "$RUN_DIR"
gra-validate-report --run "$RUN_DIR"
```

## 通常使用の成果物

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md
  context.json
  findings.schema.json
  targets.schema.json
  validation.schema.json
  chains.schema.json
  proofs.schema.json
  traces.schema.json
  templates/taxonomies/
  templates/taxonomy-aliases.json
  repo/
  reports/
  prompt.exec.md
  prompt.goal.md
  prompts/
  codex-events.jsonl
  codex-final.md
  taxonomy-preflight.txt
  report-validation.txt
```

詳細: `docs/NORMAL_WORKFLOW.md`

## `/goal` 深掘りモード

```bash
gra-audit --repo OWNER/REPO --mode goal --model gpt-5.5 --effort xhigh
```

このコマンドは Codex を実行せず、run directory と `/goal` 用promptを準備します。

表示された `codex` コマンドで run directory を開き、以下のいずれかを貼ります。

```text
prompt.goal.md                              # repo全体の深掘り
prompts/goal/validate-findings.goal.md      # Critical/High finding の検証
prompts/goal/deep-dive-finding.goal.md      # 単一findingの深掘り
prompts/goal/deep-dive-category.goal.md     # 単一カテゴリの深掘り
prompts/goal/research-target.goal.md        # 単一targetの調査
prompts/goal/gapfill-target.goal.md         # target coverage gapfill
prompts/goal/variant-analysis.goal.md       # variant analysis
prompts/goal/synthesize-chains.goal.md      # defensive chain synthesis
prompts/goal/safe-proof.goal.md             # safe local proof artifact
prompts/goal/trace-reachability.goal.md     # cross-repo trace reachability
prompts/goal/adversarial-validate.goal.md   # finding / chain の反証・降格確認
```

詳細: `docs/GOAL_DEEP_DIVE_WORKFLOW.md`

## 複数repo

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec
```

`gra-batch` は各 repo の結果を `runs/_batches/BATCH_ID/batch-results.json` に集約します。
1 件以上失敗した場合は既定で non-zero exit します。

```text
--allow-failures           失敗があっても batch を成功扱いにする
--fail-fast                最初の失敗で停止する（--concurrency 1 のみ）
```

`repos.txt`:

```text
ORG/repo-a
ORG/repo-b
# comments are ignored
ORG/repo-c
```

## Issue作成

```bash
gra-chains --run runs/ORG__repo-a/RUN_ID
gra-gapfill --run runs/ORG__repo-a/RUN_ID --generate
gra-proofs --run runs/ORG__repo-a/RUN_ID --all-critical-high
# Optional for shared-library / producer findings:
# gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-repo ORG/repo-a --mode prepare
# gra-trace --producer-run runs/ORG__shared-lib/RUN_ID --finding SEC-001 --consumer-run runs/ORG__shared-lib/RUN_ID/trace-consumers/ORG__repo-a --mode exec
gra-adversarial-validate --run runs/ORG__repo-a/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/ORG__repo-a/RUN_ID --fix
gra-validate-report --run runs/ORG__repo-a/RUN_ID
gra-issues --run runs/ORG__repo-a/RUN_ID --dry-run
gra-issues --run runs/ORG__repo-a/RUN_ID --apply --create-labels
```

既定では `Critical` / `High` かつ `Confirmed` / `Probable` のみ作成します。
Issue 作成前に non-public by default の `reports/ATTACK_CHAINS.md` と
local/private by default の `reports/PROOFS.md`、`reports/TRACE.md`、
`reports/VALIDATION.md` を確認し、chain implications、safe proof
limitations、trace reachability limitations、`downgrade`、
`invalidate`、`needs-human-review` の subject を finding または Issue draft に反映します。

## cross-repo trace reachability

producer repository の finding が consumer repository から到達可能かを確認する
場合は、`gra-trace` を使います。この機能は experimental/P3 であり、
`reports/traces.json` と `reports/TRACE.md` は reachability evidence であって
exploit proof ではありません。

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-repo ORG/consumer-api \
  --mode prepare
```

prepare mode で producer run 配下に作成された consumer run を指定して exec /
goal mode を実行します。外部 consumer run は producer artifact に絶対パスを
持ち込まないため拒否されます。

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__shared-lib/RUN_ID/trace-consumers/ORG__consumer-api \
  --mode exec
```

No external scanning、no production/staging probing、no exploit payloads、
no credential access、no dependency installation、no producer/consumer repo
modification を維持してください。

## target coverage gapfill

通常の `gra-research` または `/goal` での単一 target 調査後、`coverage`
metadata に浅い review、skip した file、未解決 question が残っている場合は
gapfill を実行します。

```bash
gra-gapfill --run runs/ORG__repo-a/RUN_ID --list
gra-gapfill --run runs/ORG__repo-a/RUN_ID --generate
gra-gapfill --run runs/ORG__repo-a/RUN_ID --target TGT-001 --mode goal
```

`--generate` は `reports/COVERAGE.md`、`reports/gapfill-targets.json`、
`reports/target-research/TGT-XXX-gapfill.md` を生成し、`TGT-GAPFILL-NNN`
を target queue に追加します。gapfill は bounded review であり、target
repository modification、dependency installation、live service access、
exploit instruction を含めてはいけません。

## run pause / resume state

本体更新、maintainer handoff、release window などで audit run を意図的に
止める場合は、`blocked` ではなく `paused` state を記録します。

```bash
gra-run-state --run runs/ORG__repo-a/RUN_ID --pause \
  --reason "maintainer update window" \
  --resume-target TGT-AGENT-234 \
  --resume-condition "main branch updated and post-merge CI passed" \
  --final-reconcile "published known findings: 52; unpublished Medium+: 0"
gra-run-state --run runs/ORG__repo-a/RUN_ID --status
gra-run-state --run runs/ORG__repo-a/RUN_ID --resume
```

paused 中は read-only status check のみに制限してください。`gra-research`、
`gra-gapfill --generate`、`gra-gapfill --target`、`gra-targets --generate`、
`gra-targets --mark` は paused state を検出すると開始を拒否します。

## run index

```bash
gra-index --runs-dir runs
```

`runs/index.json` と `runs/index.md` が生成されます。

# Usage

この文書は主要ワークフローの概要です。全 `gra-*` コマンドの詳細オプション、成果物、exit status、注意事項は [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md) を参照してください。

## 通常使用: 単一repo監査

```bash
gra-audit --repo OWNER/REPO --mode exec --model gpt-5.5 --effort xhigh
```

主なオプション:

```text
--repo OWNER/REPO          対象repo。必須
--branch REF               branch/ref指定
--mode exec|goal           既定: exec
--model MODEL              既定: gpt-5.5
--effort EFFORT            既定: xhigh
--depth N                  既定: 1
--run-id ID                run IDを明示
--runs-dir DIR             run保存先
--codex-json               codex exec のJSON event出力を保存
--network                  Codex sandbox内ネットワークを許可。通常は使わない
--no-lock                  同一repo lockを無効化。通常は使わない
--allow-invalid-report     findings.json 不在または validation failure でも成功扱いにする。
                           CI / batch automation では通常使わない
```

`--mode exec` は、Codex が成功しても `reports/findings.json` が不在、または
`gra-validate-report` が失敗した場合は既定で non-zero exit します。
`run-summary.txt` には `codex_status`、`validation_status`、`final_status` が記録されます。

## 通常使用の成果物

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md
  context.json
  findings.schema.json
  targets.schema.json
  validation.schema.json
  chains.schema.json
  repo/
  reports/
  prompt.exec.md
  prompt.goal.md
  prompts/
  codex-events.jsonl
  codex-final.md
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
prompts/goal/variant-analysis.goal.md       # variant analysis
prompts/goal/synthesize-chains.goal.md      # defensive chain synthesis
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
gra-adversarial-validate --run runs/ORG__repo-a/RUN_ID --all-critical-high
gra-validate-report --run runs/ORG__repo-a/RUN_ID
gra-issues --run runs/ORG__repo-a/RUN_ID --dry-run
gra-issues --run runs/ORG__repo-a/RUN_ID --apply --create-labels
```

既定では `Critical` / `High` かつ `Confirmed` / `Probable` のみ作成します。
Issue 作成前に non-public by default の `reports/ATTACK_CHAINS.md` と
`reports/VALIDATION.md` を確認し、chain implications と `downgrade`、
`invalidate`、`needs-human-review` の subject を finding または Issue draft に
反映します。

## run index

```bash
gra-index --runs-dir runs
```

`runs/index.json` と `runs/index.md` が生成されます。

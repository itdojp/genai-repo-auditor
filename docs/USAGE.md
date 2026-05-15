# Usage

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
```

## 通常使用の成果物

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md
  context.json
  findings.schema.json
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
prompts/validate-findings.goal.md           # Critical/High finding の検証
prompts/deep-dive-finding.goal.md           # 単一findingの深掘り
prompts/deep-dive-category.goal.md          # 単一カテゴリの深掘り
```

詳細: `docs/GOAL_DEEP_DIVE_WORKFLOW.md`

## 複数repo

```bash
gra-batch --repo-list repos.txt --concurrency 1 --mode exec
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
gra-issues --run runs/ORG__repo-a/RUN_ID --dry-run
gra-issues --run runs/ORG__repo-a/RUN_ID --apply --create-labels
```

既定では `Critical` / `High` かつ `Confirmed` / `Probable` のみ作成します。

## run index

```bash
gra-index --runs-dir runs
```

`runs/index.json` と `runs/index.md` が生成されます。

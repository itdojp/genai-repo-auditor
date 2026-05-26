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
gra-adversarial-validate --run "$RUN_DIR" --all-critical-high
gra-validate-report --run "$RUN_DIR"
gra-issues --run "$RUN_DIR" --dry-run
```

Issue 作成は、finding、evidence、non-public by default の
`reports/COVERAGE.md`、`reports/gapfill-targets.json`、
`reports/ATTACK_CHAINS.md`、local/private by default の
`reports/PROOFS.md`、`reports/VALIDATION.md`、
`reports/issue-drafts/*.md`、公開可否を人間が確認した後だけ実行します。

```bash
gra-issues --run "$RUN_DIR" --apply --create-labels
```

public repository への Issue 作成はデフォルトで拒否されます。公開が意図され、組織ポリシー上承認済みの場合だけ `--allow-public` を併用してください。

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
    validation.json           # adversarial validation の機械可読出力
    VALIDATION.md             # Issue 作成前に確認する検証サマリ
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

## scanner output の取り込み

GenAI Repo Auditor は scanner を実行しません。別途取得済みの scanner output を run directory に取り込み、redacted normalized lead として triage します。

```bash
gra-ingest --run "$RUN_DIR" --tool semgrep --file semgrep.json --format json
gra-scanner-triage --run "$RUN_DIR"
```

scanner output は未確認の lead です。secret 値の全文引用や再構成は禁止です。詳細は [`SCANNER_INTEGRATION.ja.md`](SCANNER_INTEGRATION.ja.md) を参照してください。

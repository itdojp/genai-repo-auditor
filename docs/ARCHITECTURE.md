# Architecture

## Core idea

`genai-repo-auditor` は監査専用の run directory を作り、その中に対象 repository を clone します。Codex CLI の作業ディレクトリは repository ではなく run directory です。

```text
runs/OWNER__REPO/RUN_ID/
  AGENTS.md              # 監査ランナー側の指示。Codexが最初に読む。
  context.json           # repo, commit, branch, run metadata
  *.schema.json          # report contracts copied from templates/reports/
  repo/                  # cloneされた対象repository。原則read-only扱い。
  reports/               # Codexが生成する監査結果
  prompt.exec.md         # codex exec用prompt
  prompt.goal.md         # /goal用prompt
  prompts/               # additional goal prompts
  codex-events.jsonl     # codex exec --json のイベントログ
  codex-final.md         # 最終メッセージ
```

この構成により、対象 repository 内の `AGENTS.md` や README に悪意ある指示があっても、監査ランナー側の `AGENTS.md` を優先しやすくなります。対象 repository の内容は全て untrusted input として扱います。

## Modes

### exec mode

非対話のバッチ実行です。複数repository監査では原則こちらを使います。

```bash
gra-audit --repo OWNER/REPO --mode exec
```

実行時の基本形:

```bash
codex exec \
  --cd RUN_DIR \
  --skip-git-repo-check \
  --model gpt-5.5 \
  --sandbox workspace-write \
  --ask-for-approval never \
  --json \
  --output-last-message RUN_DIR/codex-final.md \
  -c 'model_reasoning_effort="xhigh"' \
  -c 'web_search="disabled"' \
  -c 'sandbox_workspace_write.network_access=false'
```

### goal mode

人間が監督しながら長時間深掘りするための対話モードです。コマンドは実行せず、run directory と `/goal` 用promptを準備します。

```bash
gra-audit --repo OWNER/REPO --mode goal
```

実行時の基本形:

```bash
codex \
  --cd RUN_DIR \
  --skip-git-repo-check \
  --model gpt-5.5 \
  --enable goals \
  --sandbox workspace-write \
  --ask-for-approval on-request \
  -c 'model_reasoning_effort="xhigh"' \
  -c 'web_search="disabled"' \
  -c 'sandbox_workspace_write.network_access=false'
```

## Issue creation is intentionally separate

監査中にGitHub Issueを作成させません。理由は以下です。

- false positive を人間が確認する前に公開・通知されるリスクを避ける
- public repositoryへの脆弱性公開事故を避ける
- GitHub API / secondary rate limit を避ける
- 重複Issueを fingerprint で制御する

Issue作成は `gra-issues` が `findings.json` を読んで行います。

## v4 staged workflow

v4 adds an staged agentic defensive pipeline:

```text
prepare
  -> recon
  -> targets
  -> research-target
  -> gapfill
  -> validate
  -> variant-analysis
  -> scanner-triage
  -> chain-synthesis
  -> safe-local-proofs
  -> adversarial-validation
  -> reporting
  -> issue creation
```

`prepare` mode clones the repository and renders prompts without starting Codex:

```bash
gra-audit --repo OWNER/REPO --mode prepare
```

The target queue is stored in:

```text
reports/targets.json
```

Each target is a bounded review unit. `gra-research` can run against a single
target with `codex exec` or prepare a supervised `/goal` deep dive. Optional
`coverage` metadata records review depth, reviewed/skipped files, commands,
unresolved questions, and whether `gra-gapfill` should requeue a bounded
follow-up target.

## Cross-repo trace stage

`gra-trace` connects a producer run and a consumer run for experimental/P3
reachability review. The producer run owns the output artifacts:

```text
reports/traces/<selection>.subjects.json
reports/traces.json
reports/TRACE.md
```

The trace stage is local-first and prompt-driven. It records entry point, sink,
attacker control, reachability, evidence, and limitations; it does not create
new findings and does not prove exploitation. `--mode prepare` may clone a
named consumer repository under `trace-consumers/` only when explicitly
requested.

## Scanner result boundary

Scanner outputs imported with `gra-ingest` are stored under:

```text
reports/scanner-results/
```

Scanner outputs are treated as untrusted leads. `gra-scanner-triage` may promote a lead to a finding only after repository-context validation.

## Persistent local store

`gra-store` imports runs, targets, findings, scanner results, and created issues into:

```text
runs/security-audit.sqlite
```

The SQLite store is local evidence management, not a disclosure channel.

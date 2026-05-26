# セキュリティモデル

英語版は [`docs/SECURITY_MODEL.md`](../SECURITY_MODEL.md) を参照してください。この文書では、GenAI Repo Auditor の主要な trust boundary と安全制御を日本語で説明します。

## trust boundaries

```text
operator-controlled lab files
  AGENTS.md
  context.json
  *.schema.json
  prompts/
  ↓
target repository under repo/
  untrusted input
  ↓
reports/
  local audit artifacts
```

Codex の作業ディレクトリは run directory です。対象 repository は `repo/` 配下に clone され、untrusted input として扱います。対象 repository 内の `AGENTS.md`、README、docs、workflow、test、fixture、commit message は監査対象の情報源であり、監査ランナー側の instruction を上書きしません。

## 実行時 controls

- 基本は `workspace-write` sandbox を使います。
- network access は既定で無効です。
- `danger-full-access` は通常使わないでください。
- `goal` mode は `on-request` approval で人間が監督します。
- `exec` mode は非対話実行のため `never` approval とし、network access を無効にします。
- 監査中に Issue / PR / push を自動実行しません。

## secrets handling

- secret 値の全文出力は禁止です。
- 疑わしい secret は type、path、line、redacted evidence だけを記録します。
- credential rotation、GitHub Secrets 操作、cloud secrets 操作は対象外です。
- scanner output や Codex transcript を public Issue に貼り付ける前に、secret-like value が redacted されていることを確認してください。

## template rendering

Prompt template rendering は、process environment 全体ではなく明示 allowlist を使います。`RUN_ID`、`REPO`、`BRANCH`、`COMMIT`、`TARGET_REPO_DIR`、`REPORTS_DIR` などの run context placeholder が使えます。追加値は operator-controlled な `GRA_TEMPLATE_<PLACEHOLDER_NAME>` として渡します。

`TOKEN`、`SECRET`、`KEY`、`PASSWORD`、`COOKIE`、`SESSION`、`CREDENTIAL` を含む placeholder は拒否されます。これにより、`OPENAI_API_KEY` のような環境変数が prompt や監査成果物へ誤って展開されることを防ぎます。

## public repository handling

public repository への GitHub Issue 作成はデフォルトで拒否されます。脆弱性情報を公開 Issue として出す場合は、内容を人間が確認し、組織ポリシー上承認済みの場合だけ `--allow-public` を指定してください。

## chain / validation artifact

`reports/COVERAGE.md`、`reports/gapfill-targets.json`、
`reports/chains.json`、`reports/ATTACK_CHAINS.md`、`reports/validation.json`、
`reports/VALIDATION.md`、`reports/proofs.json`、`reports/PROOFS.md`、
`reports/proofs/` はローカルレビュー用 artifact です。coverage / gapfill
artifact、`ATTACK_CHAINS.md`、proof artifact は、複数の弱点や検証手順を内部向けに整理し得るため、
non-public by default として扱います。修正優先度、Issue 文言の調整、
追加レビュー要否の判断に使い、public Issue や advisory に全文を貼り付けないでください。

Gapfill は incomplete target coverage の bounded local follow-up です。
full audit に広げたり、target repository modification、dependency
installation、live service access、exploit instruction を含めたりしてはいけません。

Defensive chain synthesis は既存 finding、target、scanner ref、validation note
だけを接続します。exploit payload、weaponized step、live probing instruction、
新規 finding を生成してはいけません。

Safe local proof generation は static trace、unit-test plan、local regression
plan、parser-only input、config check、mocked local behavior などの benign
local artifact に限定します。live service への auth bypass 実行、credential
extraction、dependency installation、network scanning、production/staging probing、
target repository modification、exploit code の生成は禁止です。

## scanner outputs

取り込んだ scanner output は confirmed finding ではなく lead です。repository context、到達可能性、trust boundary、mitigation、safe validation を確認してから finding に昇格します。raw scanner output は local artifact として扱い、secret の全文引用や再構成を避けてください。

## 意図的に除外している能力

既定では以下を行いません。

- exploit generation
- exploit chaining
- autonomous remediation
- external DAST / Nuclei-style scans
- production or staging probing
- credential rotation
- automatic public disclosure

防御的検証は、static call-path review、既存 test、local unit test、benign local
input を使って行います。Defensive chain synthesis は non-public な remediation
planning に限定し、safe proof artifact は local/private な validation aid に
限定します。Exploit chaining と exploit proof generation は対象外のままです。

## repository CI hardening

この repository 自身の GitHub Actions workflows も security boundary の一部です。workflow は least-privilege の `permissions:` を明示し、validation job は read-only `contents`、CodeQL upload のみ `security-events: write` を使用します。

CodeQL は Python source と GitHub Actions workflow definitions を解析します。Dependabot は GitHub Actions update を週次で監視します。scheduled self-validation workflow は mocked `gh` / `codex` を使い、外部 target repository や Codex network access に依存せず、`gra-audit --mode prepare` と最小の `gra-audit --mode exec` path を検証します。

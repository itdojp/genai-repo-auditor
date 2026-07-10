# ローカルインストールと最初の GitHub リポジトリ監査

このガイドでは、GenAI Repo Auditor をローカルのユーザーディレクトリにインストールし、GitHub リポジトリを `OWNER/REPO` 形式で指定して監査を実行する手順を説明します。

英語版は [`docs/LOCAL_INSTALL_AND_AUDIT.md`](../LOCAL_INSTALL_AND_AUDIT.md) を参照してください。

## 適用範囲と安全上の前提

このワークフローは、監査権限を持つリポジトリに対してのみ使用してください。GenAI Repo Auditor は防御目的専用です。対象ソースコードをローカルに clone し、互換性のある AI coding agent workflow をローカルの run directory で実行し、ローカルレポートを書き出します。

live exploitation、外部ホストスキャン、brute force、credential access、自動修正は行いません。

脆弱性に関する GitHub Issue 作成は、監査後の独立した opt-in 手順です。必ず人間が内容を確認してから実行してください。

## 前提コマンド

必須:

```text
git
gh
codex
python3
```

推奨:

```text
shellcheck
rg
jq
flock
sqlite3
```

補足:

- `gh` は GitHub 認証済みで、対象リポジトリへアクセスできる必要があります。
- 現在の実装は、非対話監査で `codex exec` を呼び出します。`--mode exec` または `--mode goal` を使う前に、互換性のある `codex` CLI をインストールして設定してください。exec mode では `-c 'approval_policy="never"'` で approval を設定し、`codex-cli 0.135.0` と互換性のない `codex exec --ask-for-approval` は使いません。対話型 `/goal` の案内では top-level `codex --ask-for-approval` を使う場合があります。
- `shellcheck` はプロジェクト検証用です。監査実行そのものには必須ではありません。
- private repository を監査する場合、認証済みの `gh` account が clone / 参照できることを確認してください。

## ローカルインストール

以下のいずれかの方式を選択してください。

| 方式 | 用途 | コマンド形式 |
|---|---|---|
| Source checkout | リポジトリを編集し、local scripts や開発用 validation を実行する場合。 | `git clone`, `PATH=$GRA_HOME/bin:$PATH` |
| `pipx` | checkout または release archive から、分離された user-level console scripts として使う場合。 | `pipx install .` |
| `uv tool` | `uv` で isolated tool install を管理する場合。 | `uv tool install .` |
| Virtual environment | `pipx` / `uv` を使わない CI や制約のある workstation で固定的に使う場合。 | `python -m venv`, `pip install .` |

package install matrix は、Ubuntu、macOS、Windows と Python 3.10、3.11、3.12 の組み合わせで CI 検証します。開発用途では source checkout wrapper、編集を伴わない運用用途では packaged console scripts を推奨します。

### Source checkout install

ユーザーが書き込めるインストール先を決めます。この例では `$HOME/.local/opt` を使います。以降の例で current directory に依存しないよう、`GRA_HOME` を設定して絶対パスで扱います。

```bash
mkdir -p "$HOME/.local/opt"
export GRA_HOME="$HOME/.local/opt/genai-repo-auditor"
git clone https://github.com/itdojp/genai-repo-auditor.git "$GRA_HOME"
cd "$GRA_HOME"
chmod +x bin/* scripts/*.sh
```

現在の shell session で `gra-*` コマンドを使えるようにします。

```bash
export GRA_HOME="$HOME/.local/opt/genai-repo-auditor"
export PATH="$GRA_HOME/bin:$PATH"
```

今後の shell でも有効にする場合は、`export GRA_HOME=...` と `export PATH=...` の両方を `~/.profile`、`~/.bashrc`、`~/.zshrc` などに追加してください。

### `pipx` install

checkout 済み repository または展開済み release archive から実行します。

```bash
cd genai-repo-auditor
python3 -m pip install --user pipx
python3 -m pipx ensurepath
python3 -m pipx install . --force
```

Windows PowerShell:

```powershell
cd genai-repo-auditor
py -m pip install --user pipx
py -m pipx ensurepath
py -m pipx install . --force
```

`ensurepath` が `PATH` を更新した場合は、新しい shell を開いてください。

### `uv tool` install

checkout 済み repository または展開済み release archive から実行します。

```bash
cd genai-repo-auditor
uv tool install .
```

Windows PowerShell:

```powershell
cd genai-repo-auditor
uv tool install .
```

更新時は、更新済み checkout または release archive から再インストールしてください。

### Virtual environment install

macOS/Linux:

```bash
cd genai-repo-auditor
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
```

Windows PowerShell:

```powershell
cd genai-repo-auditor
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

## インストール確認

任意のディレクトリから、コマンドが解決できることを確認します。

```bash
gra-audit --help
gra-doctor --help
gra-validate-report --help
gra-audit --version
```

バージョン出力は repository の [`VERSION`](../../VERSION) file と一致し、audit は実行しません。

`gh`、`codex`、network access、実在の target repository を必要としない deterministic な local install smoke check は、次のコマンドで実行できます。

```bash
"$GRA_HOME/scripts/validate-install-smoke.sh"
```

packaged install の場合は、資格情報を出力しない readiness diagnostic を実行します。

```bash
gra-doctor --json --runs-dir "$HOME/.local/state/genai-repo-auditor/runs"
```

Windows PowerShell:

```powershell
gra-doctor --json --runs-dir "$env:LOCALAPPDATA\genai-repo-auditor\runs"
```

`gra-doctor` は Python version、Git/GitHub CLI の有無、設定済み worker executable、任意の sandbox runtime、書き込み可能な run directory、packaged resources、GenAI Repo Auditor の version を確認します。既定では `git`、`gh`、audit、worker、repository clone は実行せず、GitHub state の変更や credential value の出力も行いません。run directory の確認では、`--runs-dir` 配下に一時 probe file を作成して削除します。CI で必須 readiness error を失敗として扱う場合は `--strict` を追加してください。

`PATH` 上の `git` と `gh` が信頼できる local binary であることを確認した後、外部ツールの version と GitHub 認証状態を含める場合は opt-in probe を使います。この probe は credential-like environment variables を child process に渡さず、`gh auth status` の出力を破棄し、redacted diagnostics だけを記録します。

```bash
gra-doctor --probe-external-tools --json --runs-dir "$HOME/.local/state/genai-repo-auditor/runs"
```

Windows PowerShell:

```powershell
gra-doctor --probe-external-tools --json --runs-dir "$env:LOCALAPPDATA\genai-repo-auditor\runs"
```

外部ツールを確認します。

```bash
git --version
gh --version
python3 --version
codex --help >/dev/null
```

GitHub 認証と対象リポジトリへのアクセスを確認します。

```bash
gh auth status
gh repo view OWNER/REPO --json nameWithOwner,visibility,defaultBranchRef
```

`OWNER/REPO` は、監査権限のある GitHub リポジトリに置き換えてください。例: `my-org/my-service`。

## 推奨される最初の smoke test

full AI audit の前に `prepare` mode を使うことを推奨します。`prepare` mode は対象リポジトリを clone し、prompt を生成しますが、Codex は実行しません。

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode prepare \
  --run-id first-prepare
```

絶対パスの audit run directory が表示されます。`--runs-dir` を指定しない場合、既定の保存先はインストール root 配下です。

```text
$GRA_HOME/runs/OWNER__REPO/first-prepare/
```

生成された context を絶対パスで確認します。

```bash
RUN_DIR="$GRA_HOME/runs/OWNER__REPO/first-prepare"
cat "$RUN_DIR/context.json"
ls "$RUN_DIR/prompts/"
```

対象リポジトリの clone と run directory 作成が成功したら、full audit に進みます。

## full audit の実行

プロジェクト既定の model / reasoning effort で非対話監査を実行します。

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec
```

model と effort を明示する場合:

```bash
gra-audit \
  --repo OWNER/REPO \
  --mode exec \
  --model gpt-5.5 \
  --effort xhigh
```

特定 branch または ref を監査する場合:

```bash
gra-audit \
  --repo OWNER/REPO \
  --branch main \
  --mode exec
```

既定では、出力はコマンド実行時の current directory ではなく、インストール root 配下に保存されます。

```text
$GRA_HOME/runs/OWNER__REPO/RUN_ID/
```

`RUN_ID` は、`--run-id` を指定しない限り UTC timestamp と process identifier から生成されます。後続コマンドでは、`gra-audit` が表示した絶対パスを使ってください。

## 結果確認

`gra-audit` が表示した run directory を確認してください。主要ファイルは以下です。

```text
$GRA_HOME/runs/OWNER__REPO/RUN_ID/
  context.json
  repo/                 # clone された対象リポジトリ。untrusted input として扱う
  reports/
    AUDIT_SUMMARY.md
    FINDINGS.md
    findings.json
    issue-drafts/
  codex-final.md
  codex-events.jsonl
  report-validation.txt
```

必要に応じて手動で検証します。

```bash
RUN_DIR="$GRA_HOME/runs/OWNER__REPO/RUN_ID"  # RUN_ID は gra-audit が表示した実際の値に置き換える
gra-validate-report --run "$RUN_DIR"
```

任意のローカル成果物を生成します。

```bash
gra-gapfill --run "$RUN_DIR" --generate
gra-chains --run "$RUN_DIR"
gra-proofs --run "$RUN_DIR" --all-critical-high
# shared-library / producer finding の consumer 到達可能性を確認する場合:
# gra-trace --producer-run "$RUN_DIR" --finding SEC-001 --consumer-repo OWNER/consumer --mode prepare
# gra-trace --producer-run "$RUN_DIR" --finding SEC-001 --consumer-run "$RUN_DIR/trace-consumers/OWNER__consumer" --mode exec
gra-adversarial-validate --run "$RUN_DIR" --all-critical-high --votes 3 --policy human-review-on-split
gra-validate-report --run "$RUN_DIR"
gra-dashboard --run "$RUN_DIR"
gra-sarif --run "$RUN_DIR"
gra-store --run "$RUN_DIR"
```

対応前に `reports/FINDINGS.md`、`reports/findings.json`、`reports/COVERAGE.md`、
`reports/gapfill-targets.json`、`reports/ATTACK_CHAINS.md`、
`reports/PROOFS.md`、`reports/TRACE.md`、`reports/VALIDATION.md`、`reports/issue-drafts/` を確認して
ください。AI 出力は人間による検証が必要な分析結果として扱います。

## 任意の GitHub Issue workflow

最初は必ず dry-run を実行します。

```bash
gra-issues --run "$RUN_DIR" --dry-run
```

finding を検証し、開示が承認された場合のみ Issue を作成します。

```bash
gra-issues --run "$RUN_DIR" --apply --create-labels
```

public repository への Issue 作成は既定で拒否されます。公開が意図され、承認済みの場合だけ `--allow-public` を使ってください。

## ローカルインストールの更新

```bash
cd "$GRA_HOME"
git pull --ff-only
chmod +x bin/* scripts/*.sh
```

## トラブルシューティング

| 症状 | 確認 | 代表的な対応 |
|---|---|---|
| `Missing required command: gh` | `gh --version` | GitHub CLI をインストールして再実行する。 |
| `gh repo clone` が失敗する | `gh auth status`; `gh repo view OWNER/REPO` | `gh auth login` で認証する、または対象 repo にアクセスできる account を使う。 |
| `Missing required command: codex` | `codex --help` | 互換性のある Codex CLI をインストール・設定する。 |
| レポートが生成されない | `codex-final.md`; `codex-stderr.txt` | run directory 内で model、認証、sandbox エラーを確認する。 |
| レポート検証が失敗する | `report-validation.txt`; `reports/findings.json` | Issue 作成前に invalid report data を修正または再生成する。 |
| 既に別の監査が実行中と表示される | `runs/.locks/` | 既存監査の終了を待つ。競合がないと確信できる場合のみ `--no-lock` を使う。 |

## ローカル成果物の扱い

監査結果や clone された対象リポジトリを commit しないでください。プロジェクトの `.gitignore` は、`runs/`、`batches/`、`*.sqlite`、scanner output、Codex transcript などのローカル成果物を除外します。

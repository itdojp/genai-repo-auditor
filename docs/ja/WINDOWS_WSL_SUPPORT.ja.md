# Windows、WSL2、PowerShell のサポート境界

この文書は native Windows、WSL2、Linux、macOS の tested execution boundary を
定義します。安全な path containment、symlink rejection、atomic publication、sandbox、
network、disclosure control を弱めて native Windows で実行してはいけません。POSIX の
安全機能が必要な場合は WSL2 を使用します。

## サポートマトリクス

| workflow | native Windows | WSL2 | Linux | macOS |
|---|---|---|---|---|
| wheel / virtual environment / resource discovery | Python 3.10–3.12 で CI 検証済み | Linux boundary | CI 検証済み | CI 検証済み |
| `pipx` | installer path は experimental。CI smoke は Linux のみ | Linux boundary | 対応・CI smoke 済み | experimental、未 smoke |
| `uv tool` | experimental、未 smoke | experimental、未 smoke | experimental、未 smoke | experimental、未 smoke |
| `gra-doctor` | 対応・CI 検証済み | Linux と同じ。WSL を検出 | 対応 | 対応 |
| `gra-audit --mode prepare` | PowerShell path で CI 検証済み | Linux と同じ | 対応 | 対応 |
| `gra-run` plan / execute / range / failure / resume | offline fixture で orchestration を CI 検証済み | Linux と同じ | 対応 | 対応 |
| efficacy の list | 対応 | 対応 | 対応 | 対応 |
| efficacy report / comparison generation | inspection のみ。dirfd 不足時に成果物生成前に fail closed | WSL filesystem で対応 | 対応 | 対応 |
| efficacy worker comparison | 未対応。WSL2 を使用 | worker prerequisite を満たす場合に対応 | 対応 | 対応 |
| `gra-scan --plan` | 対応・CI 検証済み | 対応 | 対応 | 対応 |
| container scanner execution | Docker Desktop の Linux container のみ experimental | Linux implementation boundary。専用 WSL2 / real-container CI なし | mock runtime safety test で対応。real container CI なし | local Docker path は experimental |
| gVisor scanner execution | 未対応 | Linux `runsc` 設定時のみ | `runsc` 設定時のみ | 未対応 |

native Windows の `gra-run` CI は installed console script、PowerShell path、plan、
`--until recon`、checkpoint、成功済み stage を繰り返さない resume、target stage failure、
recovery を offline mock で確認します。実 worker stage の対応可否は worker 自体の
native-Windows support にも依存します。

GitHub-hosted CI に専用 WSL2 runner はありません。WSL2 の記載は Linux implementation
boundary と environment detection に基づき、専用 end-to-end run の証拠ではありません。
scanner CI は runtime mock を使い、いずれの OS でも image pull や real container 起動を
行いません。

WSL2 は Linux boundary として扱います。repository、run directory、worker directory、
scanner staging は `/mnt/c` ではなく `~/work` など WSL filesystem 配下に置いてください。
WSL1 は tested support matrix の対象外です。`gra-doctor` が `wsl-unknown` を返す場合は、
Linux boundary を前提にする前に WSL2 であることを確認するか upgrade してください。

## PowerShell と GitHub CLI

```powershell
$RunsDir = Join-Path $HOME ".local\state\genai-repo-auditor\runs"
gra-doctor --json --runs-dir $RunsDir
gra-audit --repo OWNER/REPO --mode prepare --run-id first-audit --runs-dir $RunsDir
$RunDir = Join-Path $RunsDir "OWNER__REPO\first-audit"
gra-run --run $RunDir --profile recon-only
```

GitHub CLI は `GH_TOKEN`、`GITHUB_TOKEN` の順で評価し、環境変数は保存済み credential
より優先されます。根拠は [GitHub CLI environment manual](https://cli.github.com/manual/gh_help_environment)
です。token value は出力せず、name と auth status だけを確認します。

```powershell
Get-ChildItem Env:GH_TOKEN,Env:GITHUB_TOKEN -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty Name
gh auth status --hostname github.com
gra-doctor --probe-external-tools --json --runs-dir $RunsDir
```

`gra-doctor` は present name と effective name だけを記録します。active probe から
credential-like environment variable を除外して保存済み auth を別途確認しますが、通常の
`gh` command は環境変数 precedence を適用します。意図しない stale variable は value を
表示せずに現在の process から削除します。

```powershell
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
gh auth status --hostname github.com
```

## efficacy と scanner

native Windows の efficacy report generation は status `2` で fail closed し、WSL2、
Linux、macOS を案内します。`--list` / `--list-configurations` は使用できます。dirfd check
を迂回してはいけません。

scanner planning は全 supported OS で non-executing です。native Windows の実行は
Docker Desktop の Linux container のみ experimental です。WSL2 では Docker Desktop
WSL integration または local Linux Docker/Podman を使い、path を WSL filesystem に
置きます。実行時の `--network=none`、read-only mount、capability drop、resource limit、
digest pin を維持します。remote daemon、image pull、external-host scan、live probe、
credential use、network-enabled scan は許可されません。

詳細と PowerShell install 例は [`LOCAL_INSTALL_AND_AUDIT.ja.md`](LOCAL_INSTALL_AND_AUDIT.ja.md)、
英語版の canonical matrix は [`../WINDOWS_WSL_SUPPORT.md`](../WINDOWS_WSL_SUPPORT.md) を参照してください。

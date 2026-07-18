# Windows、WSL2、PowerShell のサポート境界

この文書は native Windows、WSL2、Linux、macOS の tested execution boundary を
定義します。ここで supported とは、repository に実装と該当する automated test がある
ことを意味し、すべての external worker、container runtime、filesystem、credential store
の対応を意味しません。安全な path containment、symlink rejection、atomic publication、sandbox、
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
| `gra-scan --readiness --sandbox-profile container` | local Docker Desktop/Linux container path は experimental。local named-pipe の bounded probe のみ | local Docker/Podman の Linux implementation boundary。専用 WSL2 runtime CI なし | local Docker/Podman boundary を mock runtime safety test で検証 | local Docker path は experimental。real-runtime CI なし |
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

## efficacy

native Windows の efficacy report generation は status `2` で fail closed し、WSL2、
Linux、macOS を案内します。`--list` / `--list-configurations` は使用できます。dirfd check
を迂回してはいけません。

## scanner readiness/execution

scanner planning は全 supported OS で non-executing です。image 取得は、人が管理する
別の network-enabled setup phase で行います。operator が adapter と完全な release
digest を review し、registry access を承認してから immutable reference を明示的に
pull します。PowerShell と local Docker Desktop の例は次のとおりです。

```powershell
$GitleaksImage = "ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
$SyftImage = "ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb"

# 人が承認した network-enabled setup phase だけで実行する。
docker pull $GitleaksImage
docker pull $SyftImage
```

digest を mutable tag に置き換えたり、readiness/execute から pull を自動 fallback したり
してはいけません。setup 後に registry/network access を無効化し、意図しない
remote-runtime/credential-like environment variable を value を表示せず現在の process
から除外してから、scanner-specific gate を実行します。

```powershell
gra-scan --run $RunDir --tool gitleaks --readiness --sandbox-profile container --network-policy disabled --json
```

readiness は scanner/container の実行、image pull、network access、target file content
inspection を行いません。bounded run/path metadata を確認し、timeout 付き local runtime
`version` と digest 固定済み `image inspect` だけを実行できます。stdin/stdout/stderr は
破棄します。report は `<reports_dir>/scanner-readiness/gitleaks.json` に書き、
runtime/scanner の絶対 path、target/report の絶対 path、remote endpoint/environment
value、daemon output を含めません。remote-like な `CONTAINER_HOST`、
`DOCKER_CONTEXT`、`DOCKER_HOST`、`PODMAN_HOST` と、設定済み credential-like
environment name は readiness を block します。report に含められるのは name だけで、
value は含めません。
path metadata では、想定 raw output が未使用かつ non-symlink であること、および staging が
存在しないか non-symlink directory であることも確認し、content は読みません。report が
公開するのは `output_safe` / `staging_safe` boolean だけで、失敗時は
`output_path_unsafe` / `staging_path_unsafe` を使います。runtime の
`healthy_available` は少なくとも 1 件の bounded version probe が成功したことを表し、
digest 固定済み image が local にあることまでは意味しません。

`gra-scan --readiness` は `ready` / `experimental` で `0`、`blocked` /
`unsupported` で `1`、usage/evaluation/report failure で `2` です。native Windows と
macOS は全 check 成功時も `experimental`、Linux と確認済み WSL2 は `ready` です。
未確認 WSL とその他 platform は `unsupported` です。後続 plan は requested sandbox
profile と network policy が report と完全一致する場合だけ、保存済み state/reason summary
を probe なしで再利用します。不一致時は `not_checked` です。execute は stale report を
信頼せず current contract を再評価します。

- **native Windows:** readiness/execution とも Docker Desktop Linux-container mode と
  local named pipe だけが experimental です。native Podman/gVisor は未対応です。
- **WSL2:** Docker Desktop WSL integration または local Linux Docker/Podman を使い、
  bind mount path を WSL filesystem に置きます。remote daemon environment は拒否します。
- **Linux:** local Docker/Podman を supported とし、gVisor は `runsc` も必要です。
- **macOS:** local Docker path だけが experimental です。current executor は
  Podman/gVisor を選択しません。

execution では `--pull=never`、`--network=none`、read-only target/root mount、
capability drop、resource limit、digest pin を維持します。どの platform support level
でも remote daemon、readiness/execute 中の image pull、external-host scan、live probe、
credential use、network-enabled scan は許可されません。

## diagnostics

default の non-executing check を先に実行します。

```powershell
gra-doctor --json --runs-dir $RunsDir
```

同じ bounded scanner readiness contract を doctor output に含める場合は、run/tool pair
と scanner runtime 専用の明示的 probe opt-in を指定します。

```powershell
gra-doctor --json --probe-scanner-runtime `
  --scanner-run $RunDir `
  --scanner-tool gitleaks `
  --scanner-sandbox-profile container
```

scanner result は `checks.scanner_execution_readiness` に入り、doctor は
`<reports_dir>/scanner-readiness/` を書きません。scanner evaluator は no-run/no-pull/
no-network/no-target-content boundary を維持します。`--probe-scanner-runtime` は
`--probe-external-tools` と同時指定できません。scanner-only route は `git`、`gh`、
`gh auth`、設定済み worker を実行せず、外部 command は timeout-bounded local
Docker/Podman `version` と digest 固定済み `image inspect` だけです。
`--strict` なしでは scanner readiness が blocked でも doctor は `0`、`--strict` では
overall error が `1`、無効/不足 option combination は `2` です。

詳細と PowerShell install 例は [`LOCAL_INSTALL_AND_AUDIT.ja.md`](LOCAL_INSTALL_AND_AUDIT.ja.md)、
英語版の canonical matrix は [`../WINDOWS_WSL_SUPPORT.md`](../WINDOWS_WSL_SUPPORT.md) を参照してください。

# Scanner integration

英語版は [`docs/SCANNER_INTEGRATION.md`](../SCANNER_INTEGRATION.md) を参照してください。この文書では、承認済み local scanner の planning/readiness/execution と、既存 scanner output を GenAI Repo Auditor の run directory に取り込む際の日本語運用指針をまとめます。

## local scanner の安全な計画と実行

`gra-scan` は、承認対象の local scanner adapter を列挙し、実行予定の
argument array を確認するための command です。現在の `--list` と既定の
`--plan` は scanner や version command を実行せず、target content を読み取らず、
network access や output directory の作成も行いません。containment と symlink
check に必要な run context と path metadata のみ確認します。

```bash
gra-scan --run runs/OWNER__REPO/RUN_ID --list
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks
gra-scan --run runs/OWNER__REPO/RUN_ID --tool syft --plan --sandbox-profile container --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --readiness --sandbox-profile container --json
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --execute --sandbox-profile container --json
```

初期 adapter は offline-capable な `gitleaks` と `syft` です。plan は executable
の有無、対応 OS、network 要否、sandbox profile、read/write path、timeout、
output/result 上限、ingest format、secret handling、exit semantics を machine-readable
に示しますが、sandbox readiness の承認や scanner 実行を意味しません。

### scanner execution readiness

`--readiness` は明示的かつ bounded な事前確認です。既存 run と
`--tool gitleaks|syft` が必要です。宣言済み profile choice（`source-only`、
`local-test`、`container`、`gvisor`、`vm`）と network choice（`disabled`、
`explicit-allow`）をすべて診断できるため、unsafe request は何も実行せず bounded
report になります。`ready` / `experimental` に到達できるのは `container` または
`gvisor` かつ `--network-policy disabled` だけです。それ以外の宣言済み choice は
runtime probe を行わず `blocked` になります。canonical target と reports path が安全、
非重複、かつ曖昧でない場合に限り、command は adapter ごとの最新 report を設定済み
reports directory に書きます。

```text
<reports_dir>/scanner-readiness/<adapter_id>.json
```

既定 path は `reports/scanner-readiness/gitleaks.json` と
`reports/scanner-readiness/syft.json` です。closed JSON contract は
[`templates/reports/scanner-readiness.schema.json`](../../templates/reports/scanner-readiness.schema.json)
です。承認済み adapter ごとに最新 1 report を保持し、readiness 自体は command event
を追記しません。`repo_dir` と `target_repo_dir` が不一致、いずれかの path が unsafe、
または target/reports が overlap する場合、bounded blocked report は stdout に出しますが、
run 配下へは保存しません。

readiness は scanner/container の実行、image pull、network access、target repository
内 file の content inspection を行いません。containment、directory/symlink safety、
target/reports 分離を確認するため、bounded な run context と path metadata だけを読みます。
さらに、想定 raw output path が未使用かつ symlink でないこと、staging path が存在しないか
symlink ではない実 directory であることを確認します。target/output/staging content の列挙や
読み取りは行いません。platform、profile、immutable image 設定、local endpoint policy が
許可する場合に限り、信頼済み local runtime に次の probe を実行できます。

- 各 Docker/Podman candidate に対する `version` command。timeout は 10 秒。
- healthy candidate ごとの `image inspect <digest-pinned-image>`。image が見つかるまで
  確認し、各 timeout は 20 秒。

Docker endpoint は検出済み local Unix socket または native Windows の local named
pipe に固定します。Podman は Linux-family host だけで候補となり、`--remote=false` を
指定します。stdin は閉じ、stdout/stderr は破棄し、return code だけを使用します。
report には daemon URL/output、runtime/scanner の絶対 path、target/reports の絶対 path、
remote endpoint value、環境変数 value を含めません。記録可能なのは bare tool/runtime
name、review 済み image digest reference、固定 next step、拒否した環境変数の name だけ
です。

`CONTAINER_HOST`、`DOCKER_CONTEXT`、`DOCKER_HOST`、`PODMAN_HOST` に remote-like
value がある場合は `runtime_remote` で block し、runtime probe は実行しません。
`DOCKER_CONTEXT=default`、`DOCKER_CONTEXT=desktop-linux`、明示的な local
`unix://` / `npipe://` endpoint は remote と分類しません。設定済み credential-like
environment name が存在する場合は `credential_environment_present` で block します。
検出は大文字小文字を区別せず、documented provider name に加えて `*_TOKEN`、
`*_SECRET`、`*_PASSWORD`、`*_API_KEY`、`*_ACCESS_KEY`、`*_AUTH_CONFIG`、
`*_AUTH_FILE` などの bounded suffix を対象にします。したがって
`AWS_SESSION_TOKEN`、`DOCKER_AUTH_CONFIG`、`REGISTRY_AUTH_FILE`、`NPM_TOKEN`、
`PYPI_API_TOKEN` などの session/registry/package-manager credential も対象です。
これらの value は report に取り込まず、probe にも渡しません。name が存在する場合は
runtime `version` / `image inspect` probe 自体を省略し、最終 state は `blocked` です。

state と `gra-scan --readiness` の exit code は次のとおりです。

| state | 意味 | exit |
|---|---|---:|
| `ready` | Linux または確認済み WSL2 で必須 check がすべて成功。 | `0` |
| `experimental` | native Windows または macOS で必須 check がすべて成功。container path は experimental で、`reason_codes` は `["ready"]` のまま。 | `0` |
| `blocked` | 認識済み platform だが blocking reason が 1 件以上残る。 | `1` |
| `unsupported` | 未確認の `wsl-unknown` を含め、execution support matrix の対象外。 | `1` |

unknown argparse choice、missing/unsafe run root、unknown adapter、または bounded report
生成を妨げる context/path/report failure は `2` です。宣言済みだが non-executable な
profile/network choice は blocked report を書いて `1` になります。有効な report の
reason code は重複せず、次の canonical order で出力されます。

| reason code | 意味 |
|---|---|
| `runtime_missing` | 承認済み local Docker または対象となる local Podman が `PATH` にない。 |
| `runtime_remote` | remote runtime 設定が存在する。local endpoint だけを許可する。 |
| `runtime_unavailable` | candidate はあるが bounded `version` probe が成功しない。 |
| `image_not_configured` | adapter に review 済み immutable image がない。 |
| `image_not_digest_pinned` | image が lowercase SHA-256 digest に完全固定されていない。 |
| `image_not_local` | healthy local runtime が固定 image を inspect できない。readiness は pull しない。 |
| `platform_unsupported` | platform が supported/experimental execution matrix の対象外。 |
| `sandbox_unsupported` | profile が adapter/platform で承認されていない。 |
| `gvisor_missing` | `gvisor` 選択時に `runsc` が `PATH` にない。 |
| `target_unsafe` | target が存在しない、directory でない、symlink、または safe run layout 外。 |
| `reports_path_unsafe` | reports directory が存在しない、directory でない、symlink、または safe run layout 外。 |
| `output_path_unsafe` | 想定 raw scanner output path が既に存在する、symlink、または安全に表現できない。fresh run と未使用の non-symlink output path を使う。 |
| `staging_path_unsafe` | scanner staging path が symlink、既存の non-directory、または安全に表現できない。setup phase で削除または置換する。 |
| `path_overlap` | target directory と reports directory が重複する。 |
| `resource_limits_unavailable` | profile が必須の bounded scanner limit を提供できない。 |
| `credential_environment_present` | 設定済み credential-like environment variable が存在する。 |
| `network_policy_unsupported` | scanner contract が strict offline ではない。 |
| `ready` | blocking reason がない。`ready` / `experimental` ではこの 1 code だけ。 |

`paths` object が公開するのは `target_safe`、`reports_safe`、`output_safe`、
`staging_safe`、`overlap` の boolean だけです。output または staging が unsafe の場合は
readiness を block し、runtime probe を省略します。`runtime.candidate_available` は承認済み
runtime executable が見つかったこと、`runtime.healthy_available` は少なくとも 1 件の
bounded runtime `version` probe が成功したことを表します。healthy runtime でも image が
local にない場合は `image_not_local` となり、`selected` はその runtime が digest 固定済み
local image の inspect にも成功した場合だけ設定されます。

### 人が管理する image setup

image 取得は、readiness とは別の network-enabled setup phase です。人間の operator が
adapter と完全な digest を review し、registry access を承認してから pull を明示実行します。
`docker pull` / `podman pull` を readiness、plan、execute、または自動 fallback に組み込んでは
いけません。この release の固定値は次のとおりです。

```bash
GITLEAKS_IMAGE='ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f'
SYFT_IMAGE='ghcr.io/anchore/syft@sha256:473a60e3a58e29aca3aedb3e99e787bb4ef273917e44d10fcbea4330a07320bb'

# 承認済み local runtime を 1 つ選ぶ。この setup phase だけが network-enabled。
docker pull "$GITLEAKS_IMAGE"
docker pull "$SYFT_IMAGE"
# Linux/WSL2 で承認済み local Podman を使う場合:
# podman pull "$GITLEAKS_IMAGE"
# podman pull "$SYFT_IMAGE"
```

pull 後は setup 用 network access を無効化し、remote-runtime/credential-like environment
variable を unset してから `gra-scan --readiness` を実行します。digest を `latest` などの
tag に置き換えず、pull 成功だけを readiness approval とみなさないでください。

### contract の再利用

- 後続の既定/`--plan` は sandbox profile と network policy が plan と完全一致する同一
  adapter の保存済み readiness report だけを load し、`checked`、`state`、
  `reason_codes` を `execution_readiness` にコピーします。不一致は `not_checked` です。
  probe は再実行しません。plan は non-executing で、summary は stale の可能性があります。
- `--execute` は保存済み report を信頼せず、container start 前に同じ current readiness
  contract を再評価します。`ready` / `experimental` だけを許可し、その後も
  `--pull=never` / `--network=none` を維持します。
- `gra-doctor --scanner-run RUN --scanner-tool TOOL --scanner-sandbox-profile container
  --probe-scanner-runtime` は同じ evaluator を memory 上で呼び、
  `checks.scanner_execution_readiness` に格納します。doctor は run の readiness artifact を
  書きません。`--scanner-run` / `--scanner-tool` は pair で、scanner route には
  `--probe-scanner-runtime` の明示 opt-in が必要です。この専用 route は
  `--probe-external-tools` と同時指定できないため、doctor の別契約である
  `git --version`、`gh --version`、`gh auth status` を実行しません。外部 command は
  scanner evaluator が使う timeout-bounded local Docker/Podman `version` と digest 固定済み
  `image inspect` だけです。
- `gra-metrics` は保存済み readiness report を検証し、artifact presence/count と adapter、
  state、reason 別 count だけを集計します。`gra-dashboard` は `metrics.json` を再利用して
  report count と state/reason table を表示します。いずれも path、environment value、
  image/runtime command output、target content をコピーしません。

path traversal、symlink、未宣言の network access、任意 shell string は拒否します。
対象範囲は local repository の SAST/SCA/secret scan と SBOM generation です。
DAST、live endpoint probing、external-host scan、brute force、credential use、
production/staging access は禁止です。

`--execute` は明示指定が必要で、実行 profile は `container` または `gvisor`
に限定されます。local Docker/Podman の digest 固定済み image を
`--pull=never`、`--network=none`、read-only target mount/root filesystem、
capability drop、resource limit 付きで起動します。image pull は実行時に行わず、
別途承認した setup phase で operator が事前取得します。remote runtime 設定、
credential-like environment variable、network allowance、未取得 image、timeout、output/result 上限超過、symlink または
unexpected output、scanner failure は fail-closed です。成功時のみ raw JSON を
`reports/scanner-results/raw/` に移動します。この raw result は `review-only` であり、
confirmed finding や Issue 推奨には自動昇格しません。成功した output は自動的に
`gra-ingest` と共通の normalization/redaction/indexing boundary を通り、
`reports/scanner-results/normalized/` の bounded lead と scanner index に反映されます。

platform boundary は [`WINDOWS_WSL_SUPPORT.ja.md`](WINDOWS_WSL_SUPPORT.ja.md) を参照して
ください。planning は native Windows、WSL2、Linux、macOS で対応します。
readiness/execution は Linux と確認済み WSL2 の local Docker/Podman で supported です。
native Windows は Docker Desktop Linux-container mode と local named pipe だけが
experimental で、native Podman は選択しません。macOS は local Docker のみ
experimental です。gVisor は `runsc` を設定した Linux/WSL2 のみです。WSL1、
未確認の `wsl-unknown`、その他 platform は unsupported です。

run/tool/report preflight を通過した各 `--execute` は sanitized `gra-scan` command event を追記し、次の public-safe な
実行 metadata report を更新します。

```text
reports/scanner-runs.json
reports/SCANNER_RUNS.md
```

これらには adapter/version、image digest、status、duration、result/normalized lead
count、redaction count のみを記録し、raw scanner body、secret 値、raw output path は
含めません。scanner failure は failed として記録され、clean scan として扱われません。
evidence reference の不変性を保つため、同一 adapter の成功実行は 1 run directory
につき 1 回です。再実行には新しい run directory を使用し、過去の raw/normalized
artifact path を削除して再利用しないでください。

## 既存 scanner output の取り込み

`gra-ingest` 自体は scanner を実行しません。Semgrep、Gitleaks、Trivy、Grype、Checkov、CodeQL などで取得済みの local output をコピーし、triage 用の normalized lead を生成します。

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool semgrep --file semgrep.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool codeql --file codeql.sarif --format sarif
```

取り込まれた file は `reports/scanner-results/scanner-index.json` に記録されます。raw artifact は local に保持され、triage では `normalized_path` の redacted lead を優先して使用します。

```json
{
  "tool": "gitleaks",
  "path": "reports/scanner-results/gitleaks-<hash>.json",
  "normalized_path": "reports/scanner-results/normalized/gitleaks-<hash>-leads.json",
  "normalized_leads_count": 1
}
```

## trust boundary

scanner output は untrusted input です。以下を前提に扱います。

- scanner result は confirmed finding ではなく lead である。
- path、line、rule id、message は誤検知や過大検知を含む可能性がある。
- raw output には secret、token、内部 URL、private path などが含まれる可能性がある。
- prompt、Issue、PR、public report で secret 値を全文引用または再構成してはいけない。

## redacted normalized leads

normalized lead は evidence を bounded にし、secret-like value を redacted form にします。

```json
{
  "tool": "gitleaks",
  "rule_id": "generic-api-key",
  "severity": "high",
  "path": "src/config.ts",
  "line": 42,
  "redacted_evidence": "sk_live_...abcd",
  "fingerprint": "...",
  "raw_result_ref": "reports/scanner-results/gitleaks-<hash>.json"
}
```

raw scanner output は local artifact として扱います。必要最小限の context だけを normalized lead から参照し、secret の全文を prompt や Issue draft に含めないでください。

## triage

```bash
gra-scanner-triage --run runs/OWNER__REPO/RUN_ID
```

triage では、以下を確認してから finding に昇格します。

- repository context における到達可能性。
- trust boundary を越える入力かどうか。
- sink への実際の流れと前処理。
- 既存 mitigation、validation、test coverage。
- public disclosure に適した抽象度と redaction。

DAST や Nuclei 型の外部 scan は組み込み対象外です。明示的に許可された隔離環境以外では実行しないでください。

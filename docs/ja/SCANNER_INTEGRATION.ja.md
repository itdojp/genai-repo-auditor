# Scanner integration

英語版は [`docs/SCANNER_INTEGRATION.md`](../SCANNER_INTEGRATION.md) を参照してください。この文書では、既存 scanner output を GenAI Repo Auditor の run directory に取り込む際の日本語運用指針をまとめます。

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
gra-scan --run runs/OWNER__REPO/RUN_ID --tool gitleaks --execute --sandbox-profile container --json
```

初期 adapter は offline-capable な `gitleaks` と `syft` です。plan は executable
の有無、対応 OS、network 要否、sandbox profile、read/write path、timeout、
output/result 上限、ingest format、secret handling、exit semantics を machine-readable
に示しますが、sandbox readiness の承認や scanner 実行を意味しません。

path traversal、symlink、未宣言の network access、任意 shell string は拒否します。
対象範囲は local repository の SAST/SCA/secret scan と SBOM generation です。
DAST、live endpoint probing、external-host scan、brute force、credential use、
production/staging access は禁止です。

`--execute` は明示指定が必要で、実行 profile は `container` または `gvisor`
に限定されます。local Docker/Podman の digest 固定済み image を
`--pull=never`、`--network=none`、read-only target mount/root filesystem、
capability drop、resource limit 付きで起動します。image pull は実行時に行わず、
別途承認した setup phase で operator が事前取得します。remote runtime 設定、
network allowance、未取得 image、timeout、output/result 上限超過、symlink または
unexpected output、scanner failure は fail-closed です。成功時のみ raw JSON を
`reports/scanner-results/raw/` に移動します。この raw result は `review-only` であり、
confirmed finding や Issue 推奨には自動昇格しません。

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

# Scanner integration

英語版は [`docs/SCANNER_INTEGRATION.md`](../SCANNER_INTEGRATION.md) を参照してください。この文書では、既存 scanner output を GenAI Repo Auditor の run directory に取り込む際の日本語運用指針をまとめます。

## 前提

`gra-ingest` は scanner を実行しません。Semgrep、Gitleaks、Trivy、Grype、Checkov、CodeQL などで取得済みの local output をコピーし、triage 用の normalized lead を生成します。

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

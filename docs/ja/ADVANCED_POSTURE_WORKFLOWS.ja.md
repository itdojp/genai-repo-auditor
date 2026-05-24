# 高度な posture workflow

この文書は、GenAI Repo Auditor の高度な posture workflow を日本語で運用するための要約です。英語版の [`docs/`](../) 配下が canonical な技術仕様です。日本語版と英語版の詳細が異なる場合は、英語版を優先してください。

GenAI Repo Auditor は local-first / defensive-only の監査補助ツールです。ここで扱う posture artifact は、確認すべきレビュー材料であり、自動的に confirmed finding や公開可能な脆弱性情報になるものではありません。

## 共通の安全境界

- 監査対象 repository のファイル、workflow、`AGENTS.md`、prompt、scanner output、SBOM は untrusted input として扱います。
- Raw scanner output、Scorecard JSON、SBOM、Trivy / Grype JSON、Codex transcript、issue draft、SQLite store はローカルに保持し、Git に commit しません。
- `gra-ingest` は既存のローカル artifact を取り込むだけです。Scorecard、SBOM 生成、Trivy、Grype、外部 advisory service の実行や照会は行いません。
- Posture target は bounded review item です。実際の finding 化、Issue 公開、公開 repository での開示は人間の確認後に行います。
- ネットワークアクセスが必要な検証（例: `gh attestation verify`、Scorecard 実行、SBOM export）は、権限のある環境で別途実行し、生成した JSON だけをローカル run に取り込みます。

## 推奨 staged workflow

代表的な staged workflow は次の順序です。

```bash
gra-audit --repo OWNER/REPO --mode prepare
gra-recon --run runs/OWNER__REPO/RUN_ID
gra-targets --run runs/OWNER__REPO/RUN_ID --generate
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-sarif --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID
gra-index --runs-dir runs
```

この staged workflow は、広範な一括監査を避け、recon、target queue、scanner / SBOM evidence、validation、reporting を分けて確認するための運用単位です。

CI では offline fixture でこの流れを回帰確認しています。詳細は英語版 [`STAGED_AGENTIC_WORKFLOW.md`](../STAGED_AGENTIC_WORKFLOW.md) を参照してください。

## AI agent / MCP surface discovery

`gra-recon` は Codex recon の前に、監査対象 repository 内の AI agent / MCP surface をローカルで決定的に検出します。対象コードは実行しません。

主な出力:

```text
reports/agent-surface.json
reports/AGENT_SURFACE.md
```

検出対象の例:

- `.mcp.json`、`.vscode/mcp.json`、`.cursor/mcp.json` などの MCP 設定。
- `AGENTS.md`、`.github/copilot-instructions.md`、`CLAUDE.md`、`GEMINI.md` などの repository-local agent instruction。
- OpenAI、Anthropic、Gemini、Azure AI、OpenRouter などの AI SDK 利用箇所。
- tool / function-call / MCP server 定義のヒント。
- prompt template、system / developer instruction template、memory / vector store のヒント。

`gra-targets --generate` は高リスク surface を `TGT-AGENT-NNN` として target queue に追加します。これは review lead であり、confirmed finding ではありません。詳細は英語版 [`AGENT_SURFACE_DISCOVERY.md`](../AGENT_SURFACE_DISCOVERY.md) を参照してください。

## Taxonomy profiles

Findings と targets は任意の `taxonomies` 配列で、管理された分類 ID を持てます。これは severity、confidence、status、risk、priority、人間の review を置き換えるものではありません。

主な profile:

- OWASP LLM Top 10 2025
- OWASP AI Agent Security
- MCP Security
- Supply Chain Posture
- CWE Subset

`gra-validate-report` は、`taxonomies` が存在する場合に name / id / label を検証します。`gra-dashboard` と `gra-sarif` は taxonomy を集計・出力します。詳細と profile 追加手順は英語版 [`TAXONOMIES.md`](../TAXONOMIES.md) を参照してください。

## Release provenance posture

`gra-recon` は `.github/workflows/*.yml` / `.yaml` をローカルで読み取り、release、package、container、binary artifact の公開 workflow と attestation posture を確認します。GitHub や package registry への照会は行いません。

主な出力:

```text
reports/provenance-posture.json
reports/PROVENANCE_POSTURE.md
```

`gra-targets --generate` は、review が必要な公開 workflow を `TGT-PROVENANCE-NNN` として target queue に追加します。

分類の意味:

- `attested`: workflow に attestation signal と必要権限がある。
- `needs_review`: artifact 公開に対して attestation、SBOM attestation、または期待権限が不足している可能性がある。
- `not_applicable`: 該当する公開 workflow がない。

この確認は workflow 設定上の posture review です。実際に公開済み artifact に attestation が存在することは検証しません。詳細は英語版 [`PROVENANCE_POSTURE.md`](../PROVENANCE_POSTURE.md) を参照してください。

## OpenSSF Scorecard ingestion

Scorecard は GenAI Repo Auditor が実行するのではなく、権限のある環境で別途実行して JSON を保存します。

例:

```bash
scorecard --repo=github.com/OWNER/REPO --format=json --show-details > scorecard.json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool scorecard --file scorecard.json --format json
```

`gra-ingest --tool scorecard` は通常の scanner artifact に加え、次を出力します。

```text
reports/supply-chain-posture.json
reports/supply-chain-posture.md
```

低スコアの check は `TGT-SCORECARD-NNN` として target queue に追加されることがあります。ただし、Scorecard の低スコアは supply-chain posture evidence であり、自動的に confirmed finding にはなりません。Raw Scorecard JSON は workflow context や repository metadata を含む可能性があるため、ローカルに保持し commit しないでください。詳細は英語版 [`SCORECARD_INGESTION.md`](../SCORECARD_INGESTION.md) を参照してください。

## SBOM / dependency ingestion

SBOM や dependency graph は、権限のある環境で生成または export した JSON をローカル run に取り込みます。GenAI Repo Auditor は SBOM 生成や外部 vulnerability service の照会を行いません。

例:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file sbom.spdx.json --format spdx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool grype --file grype.json --format json
```

主な出力:

```text
reports/dependencies.json
reports/DEPENDENCY_RISK.md
```

サポートされる入力は CycloneDX JSON、SPDX 2.3 JSON、GitHub Dependency Graph SBOM export、Syft native JSON、Trivy SBOM JSON、Trivy vulnerability JSON、Grype vulnerability JSON です。Trivy / Grype の vulnerability JSON は、既存の SBOM-derived component に package URL や name/version/ecosystem で関連付けられます。関連付けできない場合も evidence は保持しますが、dangling component link は作りません。

Dependency ingestion は CI と operator workstation での実行を想定して境界値を持ちます。入力 JSON は 20 MiB まで、normalized component / vulnerability はそれぞれ最大 1,000 件、dependency relationship edge は最大 5,000 件、graph path expansion は最大 10,000 step、dependency path は 5 件・深さ 12 node までです。上限を超えた場合、`reports/dependencies.json` の `limits` と summary で output truncation を確認し、完全な inventory が必要な場合は raw SBOM / scanner artifact をローカルで確認してください。

高シグナルな Critical / High vulnerability evidence は `TGT-DEPENDENCY-NNN` として target queue に追加されることがあります。これは dependency reachability と manifest context を確認するための review item です。詳細は英語版 [`DEPENDENCY_INGESTION.md`](../DEPENDENCY_INGESTION.md) を参照してください。

## Reporting, store, index

Posture artifact は dashboard、SQLite store、run index にも反映されます。

```bash
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-store --run runs/OWNER__REPO/RUN_ID --db runs/security-audit.sqlite
gra-index --runs-dir runs
```

`gra-store` は optional posture artifact を `posture_artifacts` table に保存します。`gra-index` は agent surface 数、Scorecard check 数、provenance workflow 数、dependency component / vulnerability 数などを summary として出力します。SQLite store と index は複数 repository の監査情報を集約するため、ローカルに保持し、権限のない共有や commit を避けてください。詳細は英語版 [`REPORTING_AND_STORE.md`](../REPORTING_AND_STORE.md) を参照してください。

## Release readiness operator notes

Release 作業では、監査 run、scanner output、SBOM、SQLite store、issue draft、private finding、token、credential を release artifact や GitHub Release notes に含めません。

Release PR では、少なくとも次を確認します。

- `VERSION` と `CHANGELOG.md` の更新が release 用途として妥当であること。
- README / docs link が壊れていないこと。
- CLI、schema、report contract、workflow の変更に対応する document があること。
- local validation と GitHub Actions が green であること。

詳細な手順は英語版 [`RELEASE_PROCESS.md`](../RELEASE_PROCESS.md) を参照してください。

## Local artifact retention and cleanup

高度な posture workflow では、run directory、cloned target repository、scanner output、SBOM、Codex transcript、dashboard、SARIF、SQLite store が増えます。これらは監査対象 repository の情報や disclosure-sensitive evidence を含み得ます。

保持期間を決め、不要になった artifact は dry-run で確認してから削除してください。

```bash
python3 scripts/clean-local-artifacts.py
python3 scripts/clean-local-artifacts.py --apply
```

Cleanup helper は repository root 配下に scope を制限し、dry-run を default にします。詳細は英語版 [`LOCAL_ARTIFACT_CLEANUP.md`](../LOCAL_ARTIFACT_CLEANUP.md) を参照してください。

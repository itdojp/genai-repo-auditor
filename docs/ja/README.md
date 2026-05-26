# 日本語ドキュメント索引

このディレクトリには、GenAI Repo Auditor の主要運用ワークフローを日本語で説明する文書を配置しています。英語版の canonical documentation と矛盾しない範囲で、運用者が安全に監査、検証、Issue 作成を行うための要点をまとめています。

## 最初に読む文書

1. [`LOCAL_INSTALL_AND_AUDIT.ja.md`](LOCAL_INSTALL_AND_AUDIT.ja.md)
   ローカルインストール、最初の `prepare` / `exec` audit、結果確認、Issue dry-run までの導入手順です。
2. [`USAGE.ja.md`](USAGE.ja.md)
   日常運用で使う主要コマンドと、install -> first audit -> validation -> issue dry-run の流れです。
3. [`SECURITY_MODEL.ja.md`](SECURITY_MODEL.ja.md)
   trust boundary、secret handling、public disclosure、scanner output の扱いを説明します。

## ワークフロー別ドキュメント

- [`ISSUE_WORKFLOW.ja.md`](ISSUE_WORKFLOW.ja.md): GitHub Issue 作成前の確認、dry-run、apply、公開 repository での開示制御。
- [`SCANNER_INTEGRATION.ja.md`](SCANNER_INTEGRATION.ja.md): 既存 scanner output の取り込み、正規化、redaction、triage の前提。
- [`ADVANCED_POSTURE_WORKFLOWS.ja.md`](ADVANCED_POSTURE_WORKFLOWS.ja.md): AI agent / MCP surface、taxonomy、provenance、Scorecard、SBOM / dependency、release readiness の高度な posture workflow。
- [`CODEX_WORK_INSTRUCTIONS.ja.md`](CODEX_WORK_INSTRUCTIONS.ja.md): Codex CLI でこの repository を保守するための作業指示。

Defensive chain synthesis の詳細は英語版 [`docs/ATTACK_CHAINS.md`](../ATTACK_CHAINS.md) を canonical source として参照してください。
Safe local proof artifact の詳細は英語版 [`docs/SAFE_LOCAL_PROOFS.md`](../SAFE_LOCAL_PROOFS.md) を canonical source として参照してください。

## 英語版ドキュメント

英語版は repository root の [`README.md`](../../README.md) と [`docs/`](../) 配下を参照してください。日本語版が未整備の詳細トピックは、英語版を canonical source として扱ってください。

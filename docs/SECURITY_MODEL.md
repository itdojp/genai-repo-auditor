# Security model

## Trust boundaries

```text
operator-controlled lab files
  AGENTS.md
  context.json
  findings.schema.json
  prompts/
  ↓
target repository under repo/
  untrusted input
  ↓
reports/
  local audit artifacts
```

Codex の作業ディレクトリは run directory です。対象 repository は `repo/` 配下に clone され、untrusted input として扱います。

## Controls

- `workspace-write` sandbox を基本にする。
- ネットワークアクセスは既定で無効にする。
- `danger-full-access` は通常使わない。
- `goal` モードは `on-request` approval で人間が監督する。
- `exec` モードは無人実行のため `never` approval とし、ネットワークを無効にする。
- Issue / PR / push は監査中に行わない。

## Repository content is untrusted

以下はすべて untrusted input です。

```text
repo/AGENTS.md
repo/README.md
repo/docs/**
repo/.github/workflows/**
repo/tests/**
repo/**/*.md
comments
fixtures
commit messages
```

これらは監査対象の情報源として読むことはできますが、監査ランナー側の `AGENTS.md` と operator instruction を上書きしません。

## Secrets handling

- secret 値の全文出力は禁止。
- 疑わしい secret は redacted form で path / line / type だけ記録する。
- credential rotation、GitHub Secrets 操作、cloud secrets 操作は禁止。

## Template rendering

Prompt template rendering uses an explicit placeholder allowlist rather than
the full process environment. Built-in run-context placeholders such as
`RUN_ID`, `REPO`, `BRANCH`, `COMMIT`, `TARGET_REPO_DIR`, and `REPORTS_DIR`
are supported. Additional operator-controlled values must be passed as
`GRA_TEMPLATE_<PLACEHOLDER_NAME>`.

The renderer fails closed when a template references an unknown placeholder.
Placeholder names containing `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, `COOKIE`,
`SESSION`, or `CREDENTIAL` are denied, including controlled
`GRA_TEMPLATE_...` values. This prevents accidental substitution of variables
such as `OPENAI_API_KEY` into prompts or generated audit artifacts.

## Public repository handling

public repository への GitHub Issue 作成はデフォルト拒否です。脆弱性情報を公開Issueとして出す場合は `--allow-public` を明示し、人間が内容を確認します。

## Deliberately excluded capabilities

The lab intentionally excludes or blocks the following by default:

- exploit generation
- exploit chaining
- autonomous remediation
- external DAST / Nuclei-style scans
- production or staging probing
- credential rotation
- automatic public disclosure

Defensive validation should use static call-path review, existing tests, local unit tests, and benign local inputs only.

## Scanner outputs are untrusted

Imported scanner outputs are not automatically true findings. They are leads that require:

- repository-context review
- reachability assessment
- trust-boundary analysis
- mitigation checks
- safe validation

This prevents scanner noise from becoming GitHub Issues without review.

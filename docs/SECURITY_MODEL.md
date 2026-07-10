# Security model

## Trust boundaries

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

## Chain and validation artifacts

`reports/COVERAGE.md`, `reports/gapfill-targets.json`, `reports/chains.json`,
`reports/ATTACK_CHAINS.md`, `reports/validation.json`,
`reports/VALIDATION.md`, `reports/proofs.json`, `reports/PROOFS.md`,
`reports/proofs/`, `reports/traces.json`, and `reports/TRACE.md` are local
review artifacts. Coverage/gapfill artifacts, `ATTACK_CHAINS.md`, trace
artifacts, and proof
artifacts are non-public by default because they may connect weaknesses or
describe validation steps that should remain internal. Use these artifacts to
prioritize fixes, revise issue wording, or require additional review; do not
publish them wholesale to public Issues or advisories.

Gapfill is bounded local follow-up for incomplete target coverage. It must not
broaden into a full audit, modify the target repository, install dependencies,
contact live services, or generate exploit instructions.

Defensive chain synthesis is limited to existing findings, targets, scanner
refs, and validation notes. It must not produce exploit payloads, weaponized
steps, live probing instructions, or new findings.

Safe local proof generation is limited to benign local artifacts such as static
traces, unit-test plans, local regression plans, parser-only inputs, config
checks, or mocked local behavior. It must not run live-service auth bypasses,
extract credentials, install dependencies, scan networks, probe production or
staging systems, modify the target repository, or produce exploit code.

Cross-repo trace reachability is experimental/P3 and limited to local static
evidence for an existing producer finding and a specific consumer repository.
Trace results are reachability evidence, not exploit proof. `gra-trace` must not
run external scanning, probe production or staging systems, generate exploit
payloads, access credentials, install dependencies, or modify producer or
consumer repositories. Only explicit `gra-trace --mode prepare` may perform a
GitHub clone of the named consumer repository.

## Deliberately excluded capabilities

The lab intentionally excludes or blocks the following by default:

- exploit generation
- exploit chaining
- autonomous remediation
- external DAST / Nuclei-style scans
- production or staging probing
- credential rotation
- automatic public disclosure

Defensive validation should use static call-path review, existing tests, local
unit tests, and benign local inputs only. Defensive chain synthesis is allowed
only as non-public remediation planning; safe proof artifacts and cross-repo
trace artifacts are allowed only as local/private validation aids. Exploit
chaining and exploit proof generation remain out of scope.

## Scanner outputs are untrusted

Imported scanner outputs are not automatically true findings. They are leads that require:

- repository-context review
- reachability assessment
- trust-boundary analysis
- mitigation checks
- safe validation

This prevents scanner noise from becoming GitHub Issues without review.

Explicit local scanner execution is limited to registered offline Gitleaks and
Syft adapters in digest-pinned, pre-pulled container images. `gra-scan
--execute` denies network, mounts the target read-only, exposes only a dedicated
output directory, applies runtime/resource bounds, and discards failed output.
It does not execute target code, accept arbitrary scanner arguments, pull
images, scan hosts/services, or promote output beyond review-only evidence.

## Repository CI hardening

The repository's own GitHub Actions workflows are part of the security
boundary. Workflows use explicit least-privilege `permissions:` blocks, with
read-only `contents` access for validation jobs and `security-events: write`
only for CodeQL code scanning result upload.

CodeQL runs for Python source and GitHub Actions workflow definitions.
Dependabot monitors GitHub Actions updates weekly. The scheduled
self-validation workflow prepares an offline fixture audit run and exercises a
minimal `gra-audit --mode exec` path with mocked `gh` and `codex` commands.
This verifies the primary non-interactive path without contacting a target
repository or enabling Codex network access.

## Release supply-chain boundary

Source release archives are generated from a committed Git object rather than
the mutable working tree. The release builder rejects tracked local audit
artifacts, target clones, scanner output, Issue drafts, proof/remediation
artifacts, transcripts, SQLite/SARIF output, and local agent state. It produces
SHA-256 checksums and a bounded CycloneDX source SBOM.

The guarded release workflow separates read-only candidate construction from a
conditional publication job. Publication requires an existing annotated
version tag, grants `id-token: write`, `attestations: write`, and
`contents: write` only to that job, creates GitHub artifact attestations, and
never creates or moves tags. Release publication remains an explicit maintainer
action. See [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).

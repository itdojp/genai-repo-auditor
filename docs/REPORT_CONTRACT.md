# Report contract

監査 run は `reports/` に以下のような成果物を持ちます。`AUDIT_*` /
`FINDINGS.md` / `findings.json` は Codex による監査出力であり、
`PROVENANCE_POSTURE.md` / `provenance-posture.json` は `gra-recon` が
決定的に生成する補助 posture artifact です。

```text
reports/
  AUDIT_SUMMARY.md
  THREAT_MODEL.md
  ATTACK_SURFACE.md
  PROVENANCE_POSTURE.md
  provenance-posture.json
  FINDINGS.md
  findings.json
  AUDIT_LOG.md
  issue-drafts/
    SEC-001.md
```

## findings.json

`findings.json` は Issue 作成の唯一の機械可読入力です。Markdownではなくstrict JSONです。

重要フィールド:

```text
run_id
repo
commit
generated_at
findings[].id
findings[].fingerprint
findings[].severity
findings[].confidence
findings[].status
findings[].affected_locations
findings[].entry_point
findings[].trust_boundary
findings[].source_to_sink
findings[].evidence
findings[].minimal_remediation
findings[].issue_title
findings[].issue_body_file
findings[].issue_recommended
findings[].public_disclosure_risk
findings[].labels
```

## validation and safety constraints

`gra-validate-report` validates `findings.json`, optional `targets.json`, and
optional scanner index artifacts against the bundled JSON schemas using the
Python standard library. It also applies local safety rules before downstream
tools can use report-controlled paths.

`provenance-posture.json` is a local posture artifact produced by `gra-recon`;
it is advisory input for target generation and is not treated as a finding
contract.

Important constraints:

- `generated_at` must be parseable ISO-8601.
- `targets[].id` must match `TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}` and
  `priority` must be 0–100.
- `findings[].affected_locations[].file` must be a relative target-repo path.
- `line` and `end_line` must be positive integers when present.
- `public_disclosure_risk` is required when `issue_recommended` is true.
- fingerprints must be non-empty and non-placeholder.
- obvious unredacted full secret values are rejected. Redacted or clearly marked
  example values should use markers such as `REDACTED`, `EXAMPLE`, or
  `PLACEHOLDER`.
- If `reports/scanner-results/scanner-index.json` exists, scanner artifact paths
  must remain under `reports/scanner-results/`, normalized lead artifacts must be
  `.json` files under `reports/scanner-results/normalized/`, and
  `normalized_leads_count`, `raw_bytes`, and `normalization` metadata must match
  the referenced normalized artifact.

`issue_body_file`, when present, must point to a regular `.md` file under
`reports/issue-drafts/`, for example:

```text
reports/issue-drafts/SEC-001.md
```

Absolute paths, `..` traversal, symlinks, non-Markdown files, and oversized
issue body files are rejected. If `issue_body_file` is empty, `gra-issues` can
render a body from structured finding fields instead of reading a draft file.

## finding quality bar

Critical / High finding は以下を満たす必要があります。

- concrete file:line
- entry point
- trust boundary
- call path or source-to-sink
- impact
- evidence
- validation status
- minimal remediation
- regression test idea

満たせないものは `Potential` または `Needs human review` に落とします。

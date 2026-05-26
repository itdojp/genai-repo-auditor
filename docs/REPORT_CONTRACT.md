# Report contract

監査 run は `reports/` に以下のような成果物を持ちます。`AUDIT_*` /
`FINDINGS.md` / `findings.json` は Codex による監査出力であり、
`PROVENANCE_POSTURE.md` / `provenance-posture.json` は `gra-recon` が
決定的に生成する補助 posture artifact です。`supply-chain-posture.md` /
`supply-chain-posture.json` は `gra-ingest --tool scorecard` が OpenSSF
Scorecard JSON から決定的に生成する補助 posture artifact です。
`DEPENDENCY_RISK.md` / `dependencies.json` は `gra-ingest --tool sbom` が
SBOM / dependency graph JSON から決定的に生成する補助 dependency posture
artifact です。

```text
reports/
  AUDIT_SUMMARY.md
  THREAT_MODEL.md
  ATTACK_SURFACE.md
  PROVENANCE_POSTURE.md
  provenance-posture.json
  supply-chain-posture.md
  supply-chain-posture.json
  DEPENDENCY_RISK.md
  dependencies.json
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

`supply-chain-posture.json` is a local posture artifact produced by
`gra-ingest --tool scorecard`; it is advisory input for target generation and is
not treated as a finding contract. Deterministic Scorecard ingestion records
`findings_created: 0` and appends target-queue entries only for bounded
follow-up checks.

`dependencies.json` is a local dependency posture artifact produced by
`gra-ingest --tool sbom` or compatible dependency formats. It is advisory input
for dependency risk review and is not treated as a finding contract.

Important constraints:

- `generated_at` must be parseable ISO-8601.
- `targets[].id` must match `TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}` and
  `priority` must be 0–100.
- Optional target quality fields are validated when present:
  `security_invariants` must be a string list, `max_files` must be an integer
  from 1 to 20, `expected_output` must be
  `finding-or-no-finding-with-coverage`, and `chain_relevance` must be `none`,
  `possible-link`, or `candidate-chain-step`.
- `findings[].affected_locations[].file` must be a relative target-repo path.
- `line` and `end_line` must be positive integers when present.
- `public_disclosure_risk` is required when `issue_recommended` is true.
- Optional finding assessment dimensions must use the approved values
  `Confirmed`, `Probable`, `Potential`, `Invalid`, or `Not assessed`.
  `bug_existence` records whether the code defect exists,
  `attacker_reachability` records whether attacker-controlled input can reach
  it, `boundary_crossing` records whether a security boundary is crossed, and
  `impact_assessment` records whether impact is confirmed or only plausible.
  `assessment_notes` should explain each dimension. These fields inform Issue
  recommendation: public Issues should avoid overstating reachability,
  boundary-crossing, or impact when those dimensions are only Potential or Not
  assessed.
- fingerprints must be non-empty and non-placeholder.
- obvious unredacted full secret values are rejected. Redacted or clearly marked
  example values should use markers such as `REDACTED`, `EXAMPLE`, or
  `PLACEHOLDER`.
- If `reports/scanner-results/scanner-index.json` exists, scanner artifact paths
  must remain under `reports/scanner-results/`, normalized lead artifacts must be
  `.json` files under `reports/scanner-results/normalized/`, and
  `normalized_leads_count`, `raw_bytes`, and `normalization` metadata must match
  the referenced normalized artifact.
- If `reports/supply-chain-posture.json` exists, its Scorecard check reasons and
  details must be treated as posture leads. Promote them to findings only after
  repository context confirms concrete file/line evidence and impact.
- If `reports/dependencies.json` exists, it must match
  `templates/reports/dependencies.schema.json`; component and vulnerability
  counts must match array lengths; component IDs must be unique; vulnerability
  component references must resolve to normalized components; dependency paths
  must be lists of non-empty strings.

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

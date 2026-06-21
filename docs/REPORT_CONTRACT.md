# Report contract

監査 run は `reports/` に以下のような成果物を持ちます。`AUDIT_*` /
`FINDINGS.md` / `findings.json` は Codex による監査出力であり、
`PROVENANCE_POSTURE.md` / `provenance-posture.json` は `gra-recon` が
決定的に生成する補助 posture artifact です。`supply-chain-posture.md` /
`supply-chain-posture.json` は `gra-ingest --tool scorecard` が OpenSSF
Scorecard JSON から決定的に生成する補助 posture artifact です。
`DEPENDENCY_RISK.md` / `dependencies.json` は `gra-ingest --tool sbom` が
SBOM / dependency graph JSON から決定的に生成する補助 dependency posture
artifact です。`VALIDATION.md` / `validation.json` は
`gra-adversarial-validate` が既存 finding / chain を反証・降格・確認・
human-review 判定する独立 validation artifact です。`ATTACK_CHAINS.md` /
`chains.json` は `gra-chains` が既存 finding / target / scanner ref を
防御的に接続する chain synthesis artifact です。`PROOFS.md` /
`proofs.json` / `proofs/` は `gra-proofs` が既存 finding に対して生成する
safe local proof artifact です。`TRACE.md` / `traces.json` は `gra-trace`
が producer finding と consumer repository の reachability を整理する
experimental/P3 cross-repo trace artifact です。`METRICS.md` /
`metrics.json` は `gra-metrics` が local report artifacts だけから生成する
advanced workflow metrics artifact です。`known-findings.json` / `NOVELTY.md`
は `gra-novelty` が recurring audit の重複・accepted-risk・regression
分類をローカルに記録する novelty artifact です。`issue-ledger.json` は
`gra-issues` が生成・更新する canonical finding-to-Issue publication ledger
です。`run-state.json` は `gra-run-state` が生成・更新する run-level pause /
resume / blocked state artifact です。`command-events.jsonl` は target
research、gapfill、report validation の実行時間・終了コード・関連 artifact
を記録する structured observability artifact です。The run root also contains
`run-manifest.json`, which is the bounded, run-relative artifact inventory for
handoff and support diagnostics. It records each manifest artifact's retention
category and, for files, size plus SHA-256 digest.

```text
run-manifest.json
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
  ATTACK_CHAINS.md
  chains.json
  PROOFS.md
  proofs.json
  proofs/
    SEC-001-test-plan.md
  remediation/
    remediation-candidates.json
    REMEDIATION_CANDIDATES.md
    SEC-001/
      subject.json
      patch.diff
      notes.md
  TRACE.md
  traces.json
  traces/
    sec-001-org-consumer.subjects.json
  METRICS.md
  metrics.json
  NOVELTY.md
  known-findings.json
  issue-publication-plan.json
  issue-ledger.json
  duplicate-decisions/
    SEC-001.json
  run-state.json
  command-events.jsonl
  VALIDATION.md
  validation.json
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

`gra-validate-report` validates `findings.json`, optional `targets.json`,
optional chain synthesis output, optional proof artifacts, optional adversarial
validation output, optional cross-repo trace output, optional metrics output,
optional known-finding novelty ledger output, optional issue ledger output, optional command event output, optional run
manifest output, optional scanner index artifacts, and optional dependency/posture
artifacts against the bundled JSON schemas using the Python standard library. It also
applies local safety rules before downstream tools can use report-controlled
paths.

For controlled taxonomy references, run `gra-taxonomy-preflight --run RUN --fix`
before validation. The preflight command applies deterministic aliases from
`templates/taxonomy-aliases.json`, fixes canonical labels from
`templates/taxonomies/*.json`, and logs applied before/after changes to
`reports/taxonomy-normalizations.jsonl`.

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

`validation.json` is a local adversarial validation artifact produced by
`gra-adversarial-validate`. It records decisions about existing findings or
chains only; it must not introduce new findings and is not an Issue publication
source by itself.

`chains.json` is a local defensive chain synthesis artifact produced by
`gra-chains`. It records how existing findings, targets, or scanner refs may
compose into a plausible reachability or impact chain. It must not include
working exploits, exploit payloads, weaponized steps, or live probing
instructions. `ATTACK_CHAINS.md` is non-public by default.

`proofs.json` is a local/private safe proof artifact produced by `gra-proofs`.
It records benign validation artifacts for existing findings only. It must not
include exploit scripts, credential extraction, auth-bypass execution against
live services, network scanning, production/staging probing, dependency
installation, target repository modification, or weaponized payloads.

`traces.json` is a local/private experimental/P3 cross-repo reachability
artifact produced by `gra-trace`. It records whether a producer finding appears
reachable from attacker-controlled consumer entry points. It is reachability
evidence, not exploit proof, and must not include exploit payloads, production
or staging probing, external scanning, credential access, dependency
installation, or producer/consumer repository modification.

`metrics.json` is a local-only aggregate metrics artifact produced by
`gra-metrics`. It records counts and rates for findings, adversarial validation
decisions, chains, proofs, gapfill, traces, Issue publication plan warnings,
Issue ledger publication states, duplicate decision counts, artifact counts,
and run duration when local metadata is available. It must not copy raw finding evidence, issue body text,
proof evidence, trace evidence, scanner lead bodies, or secret values.

`issue-ledger.json` is a local publication ledger produced by `gra-issues`.
It records each finding's publication state, fingerprint, title, labels, body
hash, source plan, plan hash, GitHub Issue URL/number, state, published time,
and drift warnings when current findings or GitHub inventory no longer match
the ledger. It is the canonical local source for idempotent Issue publication;
`issues-created.json` remains a per-command result artifact for backward
compatibility.

`reports/duplicate-decisions/*.json` are local publication-decision records
produced by `gra-issues` before dry-run or apply output is written for a
selected finding. They record candidate Issue numbers, exact-match status,
variant markers, root-cause and source-to-sink fingerprints, the final decision
(`new`, `exact-duplicate`, `variant`, or `related-not-duplicate`), rationale,
and `checked_at`. Published or duplicate ledger entries must have a matching
duplicate decision record during ledger verification.

`run-state.json` is a local operational state artifact produced by
`gra-run-state`. It distinguishes `paused` from `blocked`: `paused` means an
intentional temporary stop with a resume target/condition, while `blocked`
means an impasse that needs external input or state change. Paused runs should
only perform read-only status checks until the pause is cleared.

`command-events.jsonl` is a local structured observability artifact appended by
`gra-research`, `gra-gapfill`, and `gra-validate-report`. Each line is one JSON
object with `target_id`, `command`, `phase`, `started_at`, `ended_at`,
`duration_ms`, `exit_code`, `model`, `effort`, and `artifact_paths`.
`gra-metrics` uses these events to report per-execution durations, failures,
reruns, validation retries, and target-level normalization counts.

`run-manifest.json` is a run-root support artifact produced by `gra-audit`.
Its `artifacts[]` entries use run-relative paths and include `kind`,
`retention`, and file `size_bytes` / `sha256` metadata when applicable. The
retention categories are:

- `latest`: canonical handoff artifacts needed to understand the latest run
  status, such as `run-summary.txt`, `report-validation.txt`, `findings.json`,
  `targets.json`, `metrics.json`, `issue-ledger.json`, `run-state.json`, and
  `dashboard.html` when present.
- `supporting`: bounded schemas and state files that support validation and
  troubleshooting but are not the primary status handoff.
- `archive`: prompts, transcripts, raw Codex event logs, target research,
  variant analysis, and scanner-result subtrees retained for reproducibility.
  Archive artifacts are retained and digest-tracked, but they are not treated as
  active report validation targets by themselves.

The `artifact_retention` summary lists latest, supporting, and archive artifact
paths in one place so operators can distinguish canonical current status from
reproducibility archives.

Important constraints:

- `generated_at` must be parseable ISO-8601.
- `targets[].id` must match `TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}` and
  `priority` must be 0–100.
- Optional target quality fields are validated when present:
  `security_invariants` must be a string list, `max_files` must be an integer
  from 1 to 20, `expected_output` must be
  `finding-or-no-finding-with-coverage`, and `chain_relevance` must be `none`,
  `possible-link`, or `candidate-chain-step`.
- Optional `targets[].coverage` metadata is validated when present:
  `review_depth` must be `none`, `shallow`, `medium`, or `deep`; reviewed,
  skipped, command, and unresolved-question fields must be string lists;
  `gapfill_recommended` must be boolean; and `gapfill_reason` must be a string.
  `write_targets()` applies write-time guardrails for this field: known aliases
  such as `bounded-deep` are serialized as `deep`, and unknown values are
  rejected before `reports/targets.json` is overwritten.
  `gra-gapfill --generate` uses this metadata to write `reports/COVERAGE.md`,
  `reports/gapfill-targets.json`, and bounded `TGT-GAPFILL-NNN` follow-up
  targets without treating coverage gaps as findings.
  `reports/gapfill-targets.json` separates `current_run` counts from
  `cumulative` queue counts, records each candidate's source target, reason,
  generated/reused gapfill target status, duplicate/variant relationship marker
  when present, and prioritized `next_targets` for final reconcile.
- Optional `run-state.json` is validated when present. `status` must be
  `active`, `paused`, or `blocked`; `pause_reason` is required for `paused`;
  `block_reason` is required for `blocked`; and `paused_at`, `blocked_at`, and
  `resumed_at` must be parseable ISO-8601 timestamps when present.
- Optional `reports/command-events.jsonl` records are validated when present.
  Each line must match `templates/reports/command-event.schema.json`, use a
  known command/phase, keep artifact paths relative to the run directory, and
  use non-negative durations with `ended_at` not earlier than `started_at`.
- Optional `run-manifest.json` is validated when present. Artifact paths must be
  relative to the run directory, must not traverse through `..` or symlink
  components, and must exist with the declared `kind`. File artifacts must have
  matching `size_bytes` and lowercase SHA-256 digest values. Completed
  manifests must have a non-empty latest-status artifact list. Latest/archive
  summary paths must be present in `artifacts[]`, must use the corresponding
  retention category, must not overlap, and `by_retention` counts must match the
  artifact list.
- Optional `reports/duplicate-decisions/*.json` records are validated when
  present. If `reports/issue-ledger.json` has `published` or `duplicate`
  entries, a matching duplicate decision record is required for each
  finding/fingerprint pair.
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
- `findings[].chain_membership` is an optional list of defensive chain IDs that
  connect the finding to a separately documented attack-chain hypothesis. Each
  value must match `CHAIN-NNN` or longer numeric forms such as `CHAIN-0001`.
  Chain membership is advisory context for validation and prioritization; it
  does not prove exploitability and must not replace the assessment dimensions
  above.
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
- If `reports/validation.json` exists, it must match
  `templates/reports/validation.schema.json`. Each validation ID must match
  `VAL-NNN`, `subject_type` must be `finding` or `chain`, `decision` must be
  `confirm`, `downgrade`, `invalidate`, or `needs-human-review`, finding
  subjects must reference existing `reports/findings.json` IDs, and chain
  subjects must reference existing `reports/chains.json` IDs. Evidence,
  missing-evidence, and safe-step fields must be string lists.
- If `reports/chains.json` exists, it must match
  `templates/reports/chains.schema.json`. Each chain ID must match `CHAIN-NNN`,
  severity/confidence/status values must be approved, chain IDs must be unique,
  list fields must contain strings, and every chain must reference at least one
  existing finding, target, or scanner ref. Finding references must exist in
  `reports/findings.json`; target references must exist in `reports/targets.json`;
  scanner refs must exist in `reports/scanner-results/scanner-index.json`.
- If `reports/proofs.json` exists, it must match
  `templates/reports/proofs.schema.json`. Each proof ID must match
  `PROOF-NNN`, `finding_id` must reference an existing finding,
  `proof_type` must be an approved safe local proof type, `status` must be
  `confirmed`, `failed`, `not-run`, or `needs-human-review`,
  `safe_by_design` must be `true`, proof file references must stay under
  `reports/proofs/`, and command records must be structured objects with
  `argv`, `read_only`, `writes`, `network`, `requires_credentials`, and
  `cwd_scope`. Free-form shell strings are rejected. Safe proof commands are
  limited to read-only `rg`, bounded `sed -n START,ENDp FILE` excerpts, and exactly `python -m json.tool FILE`
  JSON reads with `read_only: true`, `writes: []`, `network: false`, and
  `requires_credentials: false`.
- If `reports/traces.json` exists, it must match
  `templates/reports/traces.schema.json`. Each trace ID must match `TRACE-NNN`,
  `finding_id` must reference an existing producer finding, producer/consumer
  repo values, sink, and evidence must be non-empty strings, `entry_points` and
  `limitations` must be string lists, `attacker_control` and `reachable` must
  use `Confirmed`, `Probable`, `Potential`, `Invalid`, or `Not assessed`, and
  `status` must be `Confirmed`, `Probable`, `Potential`, `Invalid`, or
  `Needs human review`.
- If `reports/metrics.json` exists, it must match
  `templates/reports/metrics.schema.json`, use
  `source: local-report-artifacts`, set `safety.local_artifacts_only` to `true`,
  and set
  `safety.raw_evidence_copied` / `safety.secrets_copied` to `false`. Metrics
  output must stay aggregate-only and avoid raw evidence fields. Its
  `observability` section may include sanitized command names, phases, target
  IDs, durations, exit codes, retry counts, failure counts, and taxonomy
  normalization counts, and its `artifacts` section may include manifest
  retention counts and hygiene warning counts, but it must not copy raw evidence
  or command transcripts.

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

## adversarial validation output

`reports/validation.json` は、既存 finding または chain に対する独立した
検証結果です。代表的な用途は、Issue 化前に attacker control、reachability、
trust boundary、mitigation、framework guarantee、middleware ordering、
configuration assumption、test fixture と production behavior の差分、impact
過大評価の有無を確認することです。

`downgrade`、`invalidate`、`needs-human-review` が記録された subject は、
Issue 公開前に `findings.json` と issue draft を人間が見直してください。
この artifact は finding の新規作成や自動修正指示のためのものではありません。

## defensive chain output

`reports/chains.json` と `reports/ATTACK_CHAINS.md` は、複数の既存 evidence
を防御的に接続して remediation priority と safe validation plan を整理する
ための artifact です。`ATTACK_CHAINS.md` は non-public by default として扱い、
public Issue や advisory にそのまま貼り付けないでください。

Chain synthesis は exploit generation ではありません。working exploit、
payload、weaponized step、production/staging probing、credential access を
含めてはいけません。

## safe local proof output

`reports/proofs.json`、`reports/PROOFS.md`、`reports/proofs/` は、既存
finding を benign local evidence で確認・失敗・未実行・human-review 判定する
ための artifact です。local/private by default として扱い、public Issue や
advisory にそのまま貼り付けないでください。

Safe proof は exploit generation ではありません。working exploit script、
exploit code、weaponized payload、credential extraction、live service への
auth bypass 実行、network scanning、production/staging probing、dependency
installation、target repository modification を含めてはいけません。
`commands_run` は shell string ではなく `argv` と safety metadata
（`read_only`、`writes`、`network`、`requires_credentials`、`cwd_scope`）
を持つ structured command object として記録します。validator は read-only
`rg`、bounded `sed -n START,ENDp FILE`、exact `python -m json.tool FILE` JSON read 以外を拒否し、
network/credential/write metadata が safe proof と矛盾する場合も拒否します。

## remediation candidate output

`reports/remediation/remediation-candidates.json`,
`reports/remediation/REMEDIATION_CANDIDATES.md`, and files under
`reports/remediation/<FINDING-ID>/` are local/private, draft-only remediation
handoff artifacts. They describe candidate patch directions for existing
findings, but the auditor does not apply those patches, push branches, open
pull requests, create GitHub Issues, install dependencies, access the network,
or execute target code in this stage.

Every candidate must reference an existing finding, use an ID such as
`PATCH-001`, keep `status` set to `draft`, set `safe_by_design: true`, and set
`requires_human_review: true`. `patch_file`, optional `notes_file`, and
optional `subject_file` must stay under `reports/remediation/`; patch files use
`.diff`. `files_touched` are repository-relative paths such as `repo/app.py`.

Issue publication plans may record whether a remediation candidate exists and
may include bounded candidate metadata such as ID, status, patch path, and
human-review requirement. They must not embed the full patch diff.

## patch validation output

`reports/remediation/<FINDING-ID>/patch-validation.json` and
`reports/remediation/<FINDING-ID>/patch-validation.md` are local/private
validation results for draft remediation candidates. The validator applies the
candidate patch only to a disposable copy of the target checkout under the run
directory and removes that workspace after the ladder finishes.

Every patch validation report must reference an existing remediation candidate
and finding, keep `network_allowed: false`, record the selected executable
`sandbox_profile`, and include the ladder fields:

- `patch_applied`
- `build_status`
- `test_status`
- `safe_proof_replay_status`
- `adversarial_review_status`
- `diff_scope_status`
- `final_status`

`final_status: validated` means the mechanical local ladder passed; it does not
remove the draft-only, human-review requirement. Reports must not treat
pre-patch proof artifacts as proof replay against patched code; replay remains
`not-run` unless a later workflow explicitly executes it in the disposable
workspace. Failed or needs-human-review validation results are included in
`gra-issues --plan` metadata and are treated as blocking warnings when
`--require-advanced-validation` is used.

## cross-repo trace reachability output

`reports/traces.json` と `reports/TRACE.md` は、shared library など producer
repository の既存 finding が consumer repository の attacker-controlled
entry point から到達可能かを静的 evidence で整理するための artifact です。
experimental/P3 として扱い、reachability evidence であって exploit proof
ではありません。

`Confirmed` や `Probable` の trace であっても、public Issue 公開前には
producer finding、consumer call path、limitations、proof / validation
artifact を人間が確認してください。`Potential` や `Needs human review` は
追加調査や maintainer confirmation が必要であることを意味します。


## known-findings.json / NOVELTY.md

`gra-novelty` writes `reports/known-findings.json` and `reports/NOVELTY.md`.
The JSON artifact is validated when present. It must use `source` =
`local-report-artifacts`, set safety flags to indicate no raw evidence or secrets
were copied, and keep one record per current finding. Each record stores the
current finding ID/fingerprint, novelty status, publication recommendation,
match reasons, accepted-risk state, and 24-character hash summaries for root
cause, source-to-sink, evidence, impact, affected locations, entry point, trust
boundary, and chain membership.

Allowed novelty statuses are `new`, `duplicate`, `better-example`,
`accepted-risk`, `regression`, `invalid-known`, and `needs-human-review`.
`duplicate`, `accepted-risk`, and `invalid-known` records must set
`issue_recommended=false`; `accepted-risk` records must also set
`accepted_risk.active=true`.

The validator rejects obvious secret-like values and raw finding payload fields
such as `evidence`, `root_cause`, `impact`, remediation text, regression-test
ideas, and issue body text outside the bounded hash map.

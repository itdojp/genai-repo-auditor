# Target Queue

`reports/targets.json` is the queue of bounded security research units.

A target should be smaller than a repository audit and larger than a single file grep. Good targets include:

- tenant-scoped API authorization
- webhook authenticity and replay handling
- file upload parser and path traversal paths
- GitHub Actions `pull_request_target` and token-permission risks
- low-scoring OpenSSF Scorecard checks such as `Dangerous-Workflow`,
  `Token-Permissions`, or `SAST`
- vulnerable direct dependencies or high-severity transitive dependencies from
  normalized SBOM/dependency graph artifacts
- admin API privilege boundaries
- outbound URL fetchers and SSRF-relevant paths

## Target quality fields

Targets can carry optional quality-gate metadata that keeps Codex CLI research
bounded and reviewable:

- `attack_class`: the suspected class, such as `Authz`, `IDOR`, `SSRF`,
  `Webhook`, `CI/CD`, `Secrets`, or `Supply Chain`.
- `security_invariants`: one or more concrete invariants that must hold, for
  example "tenant-scoped reads must filter by the session tenant".
- `attacker_model`: the actor whose control should be considered, such as
  `unauthenticated`, `authenticated-user`, `tenant-user`, `pr-author`, or
  `external-webhook`.
- `max_files`: the intended inspection bound. It must be an integer from 1 to
  20; normal target research should usually stay between 4 and 8 files.
- `expected_output`: use `finding-or-no-finding-with-coverage` so a completed
  target records either a candidate finding or explicit no-finding coverage
  notes.
- `chain_relevance`: `none`, `possible-link`, or `candidate-chain-step`.
- `coverage`: optional ledger metadata recorded by `gra-research` or a
  supervised `/goal` review. It can include:
  - `review_depth`: `none`, `shallow`, `medium`, or `deep`
  - `files_reviewed`
  - `files_skipped`
  - `commands_run`
  - `unresolved_questions`
  - `gapfill_recommended`
  - `gapfill_reason`

`write_targets()` enforces `coverage.review_depth` at serialization time.
Configured aliases such as `bounded-deep`, `bounded_deep`, and `bounded deep`
are written as `deep`; any other enum value is rejected before
`reports/targets.json` is overwritten. Alias normalizations are recorded in
`reports/coverage-normalizations.jsonl` and appended to `reports/AUDIT_LOG.md`.

Good target:

```text
Review tenant isolation for repo/src/routes/projects.ts getProject/updateProject.
Invariant: every project read/write must filter by tenant_id derived from session.
Attacker model: authenticated tenant user.
Sinks: ProjectRepository.findById, ProjectRepository.update.
Max files: 6.
Expected output: finding-or-no-finding-with-coverage.
```

Avoid targets such as "Review auth and authorization". Split broad targets by
entry point, trust boundary, invariant, and sink before handing them to
`gra-research` or a supervised `/goal`.

Generate targets:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --generate
```

Deterministic posture helpers can append bounded target IDs after target
generation. Examples include `TGT-AGENT-NNN` for agent-surface discovery,
`TGT-PROVENANCE-NNN` for release provenance posture, and `TGT-SCORECARD-NNN`
for OpenSSF Scorecard supply-chain posture. When `reports/dependencies.json`
exists, high-signal dependency vulnerability records with dependency paths can
append `TGT-DEPENDENCY-NNN` entries. These entries are review targets only; they
do not confirm dependency vulnerabilities as findings.

## Deterministic seed budgets and cross-source deduplication

After `gra-targets --generate` writes model output and posture-derived seeds, it
runs the local deterministic queue policy. Re-run the same policy later with:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --rebalance
```

`--rebalance` reads the existing `reports/targets.json`, recomputes the active
wave, deferred overflow, and bounded queue summary, and writes the result back
in place. It does not call Codex, does not render a new prompt, and does not
enable network access.

Changing a target status with `gra-targets --mark` or `gra-research` does not
implicitly rebalance the queue and does not promote a deferred target. The
recorded active-wave decision remains stable until the operator runs
`--rebalance`; this keeps prepared target IDs and review-wave explanations
stable. A seed appended after a wave was selected is recorded as
`retained`/`added_after_selection` until that explicit rebalance.

`gra-taxonomy-preflight --fix` is an explicit deterministic semantic edit. For
a managed queue it refreshes target and decision fingerprints while preserving
the existing wave when grouping is unchanged. If canonical taxonomy
normalization makes previously distinct queued targets equivalent, it reapplies
the stored policy and budgets so merged lineage and membership remain valid.

### Default budgets and policies

The default queue policy is:

- total active seed budget: `20`
- per-source seed budget for each budgeted source: `10`
- default policy: `risk-weighted`

Budgeted seed sources are the closed set:

- `model_generated`
- `agent_surface`
- `provenance`
- `scorecard`
- `dependency`
- `scanner`

`gapfill` is intentionally excluded from seed budgets. Queued gapfill targets
and any non-queued target history (`in_progress`, `reviewed`, `skipped`, or
`needs_human_review`) are retained outside the active seed budget instead of
being silently deferred.

`risk-weighted` sorts merged queued seeds by risk, then priority, trusted
producer source, then target ID. `strict` preserves first-seen queued order
after deterministic deduplication. Both policies are stable for identical
inputs.

### Budget controls

`gra-targets` accepts the following queue-budget controls:

```text
--target-budget
--max-agent-surface-targets
--max-provenance-targets
--max-scorecard-targets
--max-dependency-targets
--max-scanner-targets
--max-model-generated-targets
--budget-policy strict|risk-weighted
```

The accepted range for each numeric budget is `1..1000`. Invalid values or
unknown budgeted sources fail closed.

### Active, deferred, retained, and merged targets

A budgeted queue artifact contains three related views:

- `targets[]`: selected active queued seeds plus gapfill and non-queued history
  retained outside the seed budget
- `deferred_targets[]`: queued seeds that were deferred by the total or
  per-source budget
- `queue_summary`: bounded counters and machine-readable decisions

`queue_summary` includes:

- `generated`: total seed/source lineage records considered
- `active`: targets selected into the recorded active review wave (excluding
  records counted by `retained_outside_budget`); a later status change does not
  rewrite this historical selection count
- `retained_outside_budget`: queued gapfill targets, non-queued target history
  present when a wave is selected, and seeds appended after selection
- `merged`: contributing source targets collapsed into canonical active or
  deferred targets
- `deferred_by_budget`: targets currently in `deferred_targets[]`
- `high_risk_deferred`: deferred targets whose `risk` is `critical` or `high`
- `by_source`: generated/active/retained/merged/deferred counts for every
  closed source
- `selection_input_ids`: bounded target IDs present at the last explicit queue
  selection; post-selection appends remain outside this baseline
- `decisions[]`: one record per original target ID describing whether it became
  `active`, `deferred`, `retained`, or `merged`

Deferred targets are intentionally visible rather than dropped. High-risk
budget pressure is called out both in `high_risk_deferred` and in per-target
`decisions[].reason` values such as `source_budget_exhausted_high_risk` or
`total_budget_exhausted_high_risk`.

### Structured fingerprints and source lineage

Cross-source deduplication uses a deterministic `queue_fingerprint` derived from
bounded normalized structured fields:

- `attack_class` (or `category` when `attack_class` is absent)
- `attacker_model`
- normalized scope/component/workflow identity, used only alongside the
  structured security fields above
- taxonomy IDs
- trust boundaries
- entry points
- sinks
- security invariants
- candidate files

Free-form title and notes prose are never used as a dedup key. Scope is a
bounded identity discriminator only when structured security signals are also
present; scope text alone cannot merge targets.
If a target has no structured overlap signal beyond its category, the
fingerprint falls back to the target ID so that weak free-form similarity does
not merge unrelated work.

Merged canonical targets retain `source_lineage[]` entries for every
contributing source target. Each lineage item uses the closed source set and a
closed evidence-reference set:

- `model_generated` -> `prompts/exec/generate-targets.prompt.md`
- `agent_surface` -> `reports/agent-surface.json`
- `provenance` -> `reports/provenance-posture.json`
- `scorecard` -> `reports/supply-chain-posture.json`
- `dependency` -> `reports/dependencies.json`
- `scanner` -> `reports/scanner-results/scanner-index.json`
- `gapfill` -> `reports/gapfill-targets.json`

This preserves merge provenance without copying raw finding evidence, scanner
bodies, or free-form reasoning into the queue artifact.

Every policy-managed target also receives a closed `queue_source` marker from
its producer. Queue provenance is never inferred from a target ID prefix:
model-generated content can choose an ID such as `TGT-GAPFILL-999`, but it is
still budgeted as `model_generated`. Deterministic producers write their own
markers, and trusted producer targets take precedence over model prose when a
cross-source merge chooses the canonical target; merged risk and priority
still preserve the strongest contributing values.

### Researching deferred targets

`gra-research`, `gra-targets --show`, and `gra-targets --list` read only the
retained `targets[]` array and never search `deferred_targets[]`. A deferred target must be promoted into the active
wave with `gra-targets --rebalance` before it can be researched through the
normal target workflow.

For example:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --rebalance \
  --target-budget 30 \
  --max-scanner-targets 12 \
  --budget-policy risk-weighted
gra-targets --run runs/OWNER__REPO/RUN_ID --show TGT-SCANNER-004
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-SCANNER-004
```

### Legacy compatibility and migration

Older `targets.json` files that contain only `targets[]` remain readable.
`gra-targets`, `gra-research`, and `gra-metrics` continue to accept them, with
queue-budget metrics marked unavailable until a deterministic queue summary is
written. `gra-targets --rebalance` migrates the existing artifact in place by
adding `deferred_targets[]` and `queue_summary`; non-queued/history IDs remain
directly addressable, while deduplicated queued contributor IDs remain recorded
in `source_lineage[]` and `decisions[]`. `gra-targets --generate` also writes the
new contract, but it first runs the normal model-backed target-generation path.
Because legacy artifacts do not contain producer-bound `queue_source`
markers, unmarked legacy targets are conservatively classified as
`model_generated` during migration. Re-run deterministic posture/scanner
producers when exact historical by-source attribution is required.

Policy-managed `targets.json` reads are capped at 16 MiB and reject leaf
symlinks and non-regular files. Queue writes use a same-directory no-follow
temporary file and atomic replacement so a failed write does not partially
replace the prior queue.

List active targets:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --list
```

`--list` shows `targets[]` (the selected active seed wave plus retained
non-seed/history records). Inspect `deferred_targets[]`, the
queue summary, or the dashboard/metrics artifacts when you need deferred-budget
visibility.

Show one active target:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --show TGT-001
```

Deferred targets are not shown until a later `gra-targets --rebalance` promotes
them into the active wave.

Preparing `gra-research --mode goal` changes that target to `in_progress`.
This reserves its ID before the operator starts the supervised goal so a later
status write cannot implicitly promote another deferred seed. The target keeps
its recorded active-wave decision until a later explicit rebalance, where its
non-queued status keeps it outside new seed competition. If the prepared review
is intentionally abandoned, reset the status explicitly with
`gra-targets --mark`.

Mark status manually:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --mark TGT-001 skipped
```

Allowed statuses:

```text
queued
in_progress
reviewed
skipped
needs_human_review
```

Research a target:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001
```

Deep research with `/goal`:

```bash
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal
```

## Coverage ledger and gapfill

After normal target research or supervised `/goal` review, record the target
coverage in `reports/targets.json`. A reviewed target should state whether it
reached the expected `finding-or-no-finding-with-coverage` outcome. If it did
not, keep the review bounded and mark a gapfill instead of expanding into a
broad audit.

Example coverage metadata:

```json
{
  "coverage": {
    "review_depth": "shallow",
    "files_reviewed": ["repo/src/auth.ts"],
    "files_skipped": ["repo/src/legacy_auth.ts"],
    "commands_run": [],
    "unresolved_questions": ["Could not determine middleware ordering for admin routes"],
    "gapfill_recommended": true,
    "gapfill_reason": "High-risk authz surface only partially reviewed"
  }
}
```

List candidates:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --list
```

Generate the local coverage ledger and deterministic follow-up targets:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
```

Outputs:

```text
reports/COVERAGE.md
reports/gapfill-targets.json
reports/target-research/TGT-XXX-gapfill.md
```

The generated queue entries use `TGT-GAPFILL-NNN` IDs and preserve the source
target as `source_target_id`. Re-running `--generate` reuses existing gapfill
targets for the same source target instead of duplicating them. Queued gapfill
targets are retained outside the seed-budget competition on later
`gra-targets --rebalance` runs.

`gapfill-targets.json` separates the current generate pass from cumulative
queue progress:

- `current_run.candidate_count` and `current_run.generated_target_count` describe
  the current artifact only.
- `current_run.new_target_count` and `current_run.reused_target_count` show
  whether this pass created new `TGT-GAPFILL-NNN` IDs or reused existing
  source-target requeues.
- `cumulative.generated_target_count`, `cumulative.reviewed_target_count`, and
  `cumulative.targets_by_status` describe all gapfill targets currently present
  in `reports/targets.json`.
- `candidates[]` links each source target to its generated/reused gapfill
  target, reason, target status, and relationship (`new`, `reused`, `variant`,
  or `duplicate`).
- `next_targets[]` lists queued/in-progress gapfill targets in priority order
  for final reconcile and resume planning.

Run a single gapfill in exec mode:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode exec
```

Prepare a supervised `/goal` gapfill:

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-001 --mode goal
```

Gapfill remains defensive and local-only: do not modify the target repository,
install dependencies, contact live services, or generate exploit instructions.

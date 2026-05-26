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

List targets:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --list
```

Show one target:

```bash
gra-targets --run runs/OWNER__REPO/RUN_ID --show TGT-001
```

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
targets for the same source target instead of duplicating them.

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

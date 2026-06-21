# Self-dogfood summary for genai-repo-auditor

This is a public-safe summary of a controlled self-dogfood run against
`itdojp/genai-repo-auditor`. It contains workflow status, counts, and product
observations only. It intentionally excludes private finding bodies, raw
evidence, attack-chain details, proof payloads, scanner raw output, Codex
transcripts, issue draft text, dashboard content, remediation diffs, credentials,
and local run artifacts.

For campaign and disclosure rules, see [`../DOGFOOD_CAMPAIGN.md`](../DOGFOOD_CAMPAIGN.md),
[`../DOGFOOD_RUNBOOK.md`](../DOGFOOD_RUNBOOK.md),
[`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md), and
[`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Run metadata

| Field | Value |
|---|---|
| Run date | 2026-06-21 JST |
| Target repository | `itdojp/genai-repo-auditor` |
| Target branch | `main` |
| Target commit | `0abeafc133f405d370d84628b33f0bfc902a18ba` |
| Run ID | `issue155-self-dogfood-20260621T192736+0900` |
| Codex CLI observed | `codex-cli 0.141.0` |
| Network for agent run | disabled |
| Publication action | none; `gra-issues --dry-run` only |

The local run directory and all generated reports remain ignored local artifacts
under `runs/`. They are not part of this commit.

## Workflow stages exercised

| Stage | Status | Public-safe observation |
|---|---|---|
| `gra-audit --mode prepare` | completed | Created an isolated run directory and shallow target clone. |
| `gra-recon` | completed | Produced reconnaissance, threat-model, attack-surface, audit-log, agent-surface, and provenance-posture artifacts. |
| `reports/findings.json` | synthesized locally for this evaluation | Empty findings file records that no findings were confirmed during the reconnaissance pass. |
| `gra-validate-report` | passed | Initial and final validation passed for the local run. |
| `gra-metrics` | completed | Generated counts-only metrics from local report artifacts. |
| `gra-benchmark` | passed | Benchmark reported all quality gates passing for the available artifacts. |
| `gra-evidence-graph` | completed | Generated a graph over available local evidence. |
| `gra-dashboard` | completed | Rendered a local dashboard; dashboard content is not included here. |
| `gra-issues --dry-run` | completed | No Issues were created; warning count was zero. |

## Sanitized metrics

| Metric | Count / status |
|---|---:|
| Confirmed findings included in this summary | 0 |
| Candidate findings published | 0 |
| Issue-recommended findings | 0 |
| Issue dry-run created Issues | 0 |
| Issue-publication warnings | 0 |
| Adversarial validations present | 0 |
| Chains present | 0 |
| Proofs present | 0 |
| Traces present | 0 |
| Evidence graph nodes | 1 |
| Evidence graph edges | 0 |
| Benchmark gates passed | 7 |
| Benchmark warnings | 0 |
| Benchmark failures | 0 |
| Agent-surface review leads | 110 |
| Agent-surface high-risk review leads | 66 |
| Agent-surface medium-risk review leads | 44 |
| Provenance posture | `not_applicable` |

The agent-surface counts are review leads for the AI-agent harness surface. They
are not confirmed vulnerabilities and are not sufficient for publication without
separate triage and human review.

## Artifact categories generated locally

The run generated these artifact categories locally:

- run context and copied schemas;
- rendered prompts;
- target repository clone;
- reconnaissance Markdown reports;
- agent-surface and provenance-posture JSON/Markdown;
- empty findings report for validation of the no-confirmed-finding pass;
- metrics and benchmark reports;
- evidence graph;
- dashboard HTML;
- issue dry-run ledger and preview metadata;
- Codex event stream and final message for the recon phase.

Only this sanitized summary is committed. Generated artifacts, transcripts,
dashboards, issue ledgers, and local report files remain private local outputs.

## Operator UX observations

1. `gra-audit --mode prepare` gave a clear staged command sequence and created a
   usable run directory without invoking the model.
2. `gra-recon` successfully exercised the model-backed reconnaissance path with
   network disabled and preserved `repo/` unchanged.
3. A reconnaissance-only run does not naturally produce `reports/findings.json`;
   an operator must either run deeper finding generation or create an explicit
   empty findings artifact before validation/metrics/benchmark commands can be
   exercised as a no-confirmed-finding evaluation.
4. `gra-metrics`, `gra-benchmark`, `gra-evidence-graph`, `gra-dashboard`, and
   `gra-issues --dry-run` can operate safely on a no-confirmed-finding run after
   `findings.json` exists.
5. `gra-issues --dry-run` created no GitHub Issues and produced zero publication
   warnings for the empty-finding run.
6. The benchmark result was useful as a quick quality gate, but the evidence
   graph was necessarily sparse because target queue, chains, proofs,
   adversarial validation, traces, scanner imports, and remediation artifacts
   were intentionally not generated in this bounded pass.

## Product-improvement candidates for backlog triage

These are product observations, not target-repository findings:

| Candidate | Severity | Impact | Proposed fix | Area | Should become Issue? |
|---|---|---|---|---|---|
| Make reconnaissance-only validation easier | Medium | Operators need to know how to represent a safe no-confirmed-finding run. | Add a documented helper or command mode that writes an explicit empty findings artifact with rationale. | `gra-recon`, `gra-validate-report`, docs | Yes |
| Clarify `gra-issues --dry-run` output wording | Medium | The dry-run output prints a plan path even though `issue-publication-plan.json` is only written by `--plan`; this can confuse approval workflows. | Adjust output labels or add an explicit `plan_written=false` field in `issues-created.json`. | `gra-issues` | Yes |
| Add a compact top-level metrics summary | Low | `metrics.json` is rich, but consumers need a compact summary block for reports. | Add or document a stable `summary` object for counts used in dogfood reports. | `gra-metrics` | Consider |
| Add a recon-only dogfood profile | Low | Bounded self-dogfood runs intentionally skip target research, chains, proofs, traces, and remediation. | Add a documented profile that marks these as intentionally skipped rather than merely missing optional artifacts. | docs, benchmark, evidence graph | Consider |

Deferred: running deep target research, chain synthesis, proof generation,
adversarial validation, and remediation candidate generation for this public
self-dogfood run. Those stages can be exercised later with explicit target
selection and human review.

## Disclosure and retention decision

- Public disclosure status: this summary is public-safe by construction, but it
  does not publish findings.
- Retention decision: local run artifacts should remain local only and be
  deleted or archived according to [`../LOCAL_ARTIFACT_CLEANUP.md`](../LOCAL_ARTIFACT_CLEANUP.md).
- GitHub Issue creation: no target findings were published; `gra-issues` was run
  only with `--dry-run`.

# Adversarial validation workflow

`gra-adversarial-validate` runs an independent validation pass against existing
findings or documented attack-chain hypotheses. The stage is deliberately
separate from discovery: it tries to disprove, downgrade, confirm, or mark
selected subjects as `needs-human-review` before issue publication or broader
reporting.

## When to use it

Use this step after `reports/findings.json` exists and before publishing GitHub
Issues for high-impact results.

Typical triggers:

- Critical / High findings where reachability, trust-boundary crossing, or impact
  may be overstated.
- Findings promoted from scanner, dependency, or posture leads.
- Findings linked to chain hypotheses through `chain_membership`.
- Chain hypotheses produced by `gra-chains` in `reports/chains.json`.
- Safe local proof limitations or `needs-human-review` proof outcomes from
  `gra-proofs` in `reports/proofs.json`.
- Any finding that will be shared outside the immediate audit team.

This stage must not create new findings. If the validator notices unrelated risk,
record it outside this stage for a separate authorized audit target.

## Commands

Validate one finding in non-interactive `codex exec` mode:

```bash
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --finding SEC-001
```

Validate all Critical / High findings whose status is `Confirmed`, `Probable`, or
`Potential`:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high
```

Request three independent validation votes and route split outcomes to a human:

```bash
gra-adversarial-validate \
  --run runs/OWNER__REPO/RUN_ID \
  --all-critical-high \
  --votes 3 \
  --policy human-review-on-split
```

Prepare a supervised `/goal` run for an attack-chain hypothesis:

```bash
gra-adversarial-validate \
  --run runs/OWNER__REPO/RUN_ID \
  --chain CHAIN-001 \
  --mode goal
```

`--network` is disabled by default and is not recommended for this workflow.
Validation should rely on local static evidence, generated reports, and benign
local reasoning.

`--votes 1` is the default and preserves the historical single-pass behavior.
For `--votes N` in exec mode, the command runs `N` bounded Codex exec passes and
aggregates concise vote summaries into `reports/validation.json`. Supported
aggregation policies are:

| Policy | Behavior |
|---|---|
| `human-review-on-split` | Any split decision across votes becomes `needs-human-review`. This is the default for multi-vote work. |
| `precision-biased` | Ties favor false-positive reduction: `invalidate`, then `downgrade`, then `needs-human-review`, then `confirm`. |
| `recall-biased` | Ties favor issue retention: `confirm`, then `downgrade`, then `needs-human-review`, then `invalidate`. |

Vote outputs must contain short summaries only. Do not store chain-of-thought,
hidden reasoning, raw private reasoning, scratchpads, or internal deliberation.

## Inputs

Required run artifacts:

```text
reports/findings.json
```

Optional chain validation input:

```text
reports/chains.json
reports/proofs.json
reports/PROOFS.md
repo/.github/CODEOWNERS
repo/CODEOWNERS
repo/docs/CODEOWNERS
```

The command writes a bounded subject file under:

```text
reports/adversarial-validation/<selection>.subjects.json
```

The rendered prompt reads only the selected subject records, existing report
artifacts, and relevant local repository files.

## Outputs

The validator writes:

```text
reports/validation.json
reports/VALIDATION.md
```

`validation.json` contains run metadata and one decision record per selected
subject:

```json
{
  "run_id": "RUN_ID",
  "repo": "OWNER/REPO",
  "generated_at": "2026-05-26T00:00:00Z",
  "validations": [
    {
      "id": "VAL-001",
      "subject_type": "finding",
      "subject_id": "SEC-001",
      "decision": "downgrade",
      "original_severity": "High",
      "recommended_severity": "Medium",
      "original_confidence": "High",
      "recommended_confidence": "Medium",
      "reasoning_summary": "Reachability is not proven by local evidence.",
      "evidence_checked": ["reports/findings.json", "repo/app.py"],
      "missing_evidence": ["production middleware order"],
      "safe_validation_steps": ["static call-path review"],
      "component": "auth",
      "owner_hint": "@team/appsec",
      "owner_source": "CODEOWNERS"
    }
  ]
}
```

For multi-vote runs, the same validation record also contains the aggregate
policy and per-vote summaries:

```json
{
  "requested_votes": 3,
  "vote_policy": "human-review-on-split",
  "validations": [
    {
      "id": "VAL-001",
      "decision": "needs-human-review",
      "vote_count": 3,
      "vote_policy": "human-review-on-split",
      "votes": [
        {
          "vote_id": "VOTE-001",
          "decision": "confirm",
          "recommended_severity": "High",
          "recommended_confidence": "High",
          "reasoning_summary": "Short defensive vote summary.",
          "evidence_checked": ["reports/findings.json"],
          "missing_evidence": [],
          "safe_validation_steps": ["static call-path review"]
        }
      ]
    }
  ]
}
```

Allowed decisions:

| Decision | Meaning |
|---|---|
| `confirm` | Existing severity and confidence are supported by the checked evidence. |
| `downgrade` | A bug or concern may remain, but severity or confidence should be reduced. |
| `invalidate` | The selected subject is not supported by the checked evidence. |
| `needs-human-review` | Evidence is incomplete or ambiguous and requires human follow-up. |

Owner routing is advisory. When the selected finding has affected paths, the
command derives a `component` from the path and uses CODEOWNERS when available to
populate `owner_hint` and `owner_source`. Existing manual fields on a finding
take precedence. `gra-issues --plan` copies available owner routing metadata into
the issue publication plan so operators can route publication or remediation to
the right team before creating GitHub Issues.

## Required checks

For each selected subject, challenge:

- attacker control
- reachability
- trust-boundary crossing
- existing mitigations
- framework guarantees
- middleware ordering
- configuration assumptions
- test fixture versus production behavior
- whether impact or issue wording is overstated

Recommendations belong in `reports/validation.json` and `reports/VALIDATION.md`.
Do not edit `reports/findings.json` inside this validation stage unless a human
operator separately decides to revise findings after reviewing the validation
output.

## Validation and publication

Run the report validator after adversarial validation:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

When `reports/validation.json` exists, `gra-validate-report` validates its JSON
schema, timestamps, decision values, subject references, vote counts and
policies, owner-source values, evidence lists, and the absence of private
reasoning fields. A valid result prints `Adversarial validations: validated`.

Before `gra-issues --plan`, review `reports/VALIDATION.md`. Downgraded,
invalidated, or `needs-human-review` subjects should either be revised in
`findings.json`, excluded from publication, or explicitly explained in the issue
draft so the issue does not overstate exploitability.

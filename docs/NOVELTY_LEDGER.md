# Known findings and novelty ledger

`gra-novelty` classifies the current `reports/findings.json` against local
known-finding records. It is intended for recurring audits where repeated
findings should not create duplicate publication work.

The workflow is local-only. It does not query GitHub, does not publish Issues,
and does not copy raw finding evidence, root cause text, impact text, or issue
bodies into the ledger.

## Outputs

```text
reports/known-findings.json
reports/NOVELTY.md
```

`known-findings.json` stores finding IDs, fingerprints, bounded hash summaries,
novelty status, match reasons, and local publication recommendations. It stores
hashes for root cause, source-to-sink, evidence, impact, affected locations,
entry point, trust boundary, and chain membership.

`NOVELTY.md` is a local operator summary of the same classifications.

## Statuses

| Status | Meaning | Default publication behavior |
|---|---|---|
| `new` | No prior local known-finding match was found. | Keep the original finding recommendation. |
| `duplicate` | The current finding matches a prior fingerprint or unchanged root-cause context. | Suppressed by `gra-issues` by default. |
| `better-example` | The root cause matches a prior finding, but current evidence or impact is stronger. | Eligible for publication/review. |
| `accepted-risk` | A prior local accepted-risk decision still applies. | Suppressed by `gra-issues` by default. |
| `regression` | A prior accepted risk has changed evidence, impact, or assessed strength. | Eligible for publication/review. |
| `invalid-known` | Reserved for local known-invalid records. | Suppressed by `gra-issues` by default. |
| `needs-human-review` | Reserved for ambiguous ledger states. | Requires operator review. |

## Basic use

Run novelty classification after `findings.json` exists:

```bash
gra-novelty --run runs/OWNER__REPO/RUN_ID
```

Re-running the same command against the same run uses the existing
`reports/known-findings.json` as the prior ledger. Exact fingerprint matches are
classified as `duplicate`.

Root-cause text alone is not enough to suppress a finding. If the root-cause hash
matches but no contextual hash also matches, `gra-novelty` classifies the record
as `needs-human-review` so separate findings that share a generic root-cause
phrase are not collapsed automatically.

To compare a new run against a previous run:

```bash
gra-novelty \
  --run runs/OWNER__REPO/NEW_RUN \
  --prior-ledger runs/OWNER__REPO/OLD_RUN/reports/known-findings.json
```

Multiple `--prior-ledger` values may be supplied for local multi-run history.

## Accepted risks

To record a local accepted-risk decision for the current run:

```bash
gra-novelty \
  --run runs/OWNER__REPO/RUN_ID \
  --accepted-risk SEC-001 \
  --accepted-risk-reason "accepted by local risk owner"
```

The reason is local-only, but it is still written to `known-findings.json`; do
not include secrets, private evidence, or sensitive business context. Accepted
risks are not exported or recommended for Issue publication by default.

If a later run has changed evidence, impact, source-to-sink, affected location,
entry point, trust boundary, chain membership, severity, confidence, or finding
status for the accepted risk, the finding is classified as `regression` instead
of `accepted-risk`.

## Issue planning integration

`gra-issues --plan`, dry-run, and apply flows read
`reports/known-findings.json` when it exists. Findings classified as
`duplicate`, `accepted-risk`, or `invalid-known` are excluded from the default
publication selection. Findings classified as `better-example` or `regression`
remain eligible when they otherwise satisfy severity/status filters.

`gra-issues` applies suppression only when the novelty record fingerprint matches
the current finding fingerprint. If `findings.json` changed after
`gra-novelty` ran, the stale novelty record is ignored for publication
suppression and the plan marks the novelty status as `stale-ignored`.

Run the recommended sequence:

```bash
gra-novelty --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
```

## Validation and safety

`gra-validate-report` validates `known-findings.json` when present. Validation
checks include:

- schema shape and timestamp format;
- current finding ID and fingerprint reconciliation;
- novelty status enums and summary count consistency;
- suppressed publication states have `issue_recommended=false`;
- accepted-risk records have `accepted_risk.active=true`;
- hash fields are 24-character lowercase hex summaries;
- obvious secret-like values are rejected;
- raw evidence, root cause, impact, remediation, regression-test, and issue-body
  fields are not copied into the ledger.

The HTML dashboard summarizes novelty status counts and per-finding novelty
states when the ledger exists.

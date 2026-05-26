# Defensive attack-chain synthesis

`gra-chains` synthesizes defensive attack or reachability chains from existing
audit evidence. It is a prioritization and validation aid, not an exploit
builder.

## Safety stance

`reports/ATTACK_CHAINS.md` is non-public by default. Treat it as internal audit
material because it can connect multiple weaknesses into a higher-impact path.
Do not publish it directly to GitHub Issues or external advisories without
explicit disclosure approval.

The workflow must not produce:

- working exploits
- exploit payloads
- weaponized steps
- live exploitation instructions
- production or staging probing instructions
- credential access steps

## Command

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
```

For supervised review:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID --mode goal
```

`--network` is disabled by default and is not recommended. Chain synthesis should
use local findings, target queues, scanner indexes, validation notes, and safe
static reasoning.

## Inputs

Typical inputs are existing local artifacts:

```text
reports/findings.json
reports/targets.json
reports/scanner-results/scanner-index.json
reports/validation.json
```

Every chain must reference at least one existing finding, target, or scanner
reference. The stage must not create new findings.

## Outputs

```text
reports/chains.json
reports/ATTACK_CHAINS.md
```

`chains.json` records defensive chain fields including entry point, trust
boundaries, attacker-controlled steps, required conditions, broken security
invariants, impact composition, safe validation plan, and remediation priorities.

Allowed chain status values:

```text
Confirmed / Probable / Potential / Invalid / Needs human review
```

Use `Potential` or `Needs human review` when reachability, middleware ordering,
configuration, or impact composition is not fully proven.

## Validation

Run:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

When `reports/chains.json` exists, the validator checks the schema, timestamp,
chain IDs, severity/confidence/status values, list fields, duplicate chain IDs,
and references to existing findings, targets, or scanner refs. A valid result
prints `Chains: validated`.

## Issue publication

Do not copy `ATTACK_CHAINS.md` wholesale into public issues. Use it to adjust
remediation order and to decide whether individual finding issues need more
cautious wording, additional validation, or coordinated disclosure handling.

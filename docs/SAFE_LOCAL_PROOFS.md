# Safe local proof artifacts

`gra-proofs` generates local/private proof artifacts for existing findings. The
workflow helps determine whether a finding can be validated with benign local
evidence, without creating exploit deliverables.

## Safety stance

Proof artifacts are local/private by default. Use them for internal validation,
issue wording, and remediation prioritization. Do not publish `PROOFS.md`,
`proofs.json`, or supporting files wholesale to public Issues or advisories.

Allowed proof artifact types:

- static call-path trace
- benign unit test plan
- local regression test plan
- parser-only local input description
- local config validation
- mocked local service behavior

Forbidden output and actions:

- working exploit scripts
- exploit code
- weaponized payloads
- credential extraction
- auth bypass execution against live services
- network scanning
- production or staging probing
- dependency installation or upgrades
- target repository modification

## Command

For one finding:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001
```

For all Critical / High findings with `Confirmed`, `Probable`, or `Potential`
status:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
```

For supervised review:

```bash
gra-proofs --run runs/OWNER__REPO/RUN_ID --finding SEC-001 --mode goal
```

`--network` is disabled by default and is not recommended. If proof execution
would require network access, credentials, dependency installation, a live
service, or target repository modification, record `not-run` plus a safe local
regression plan instead.

## Inputs

Typical inputs are existing local artifacts:

```text
reports/findings.json
reports/validation.json
reports/chains.json
reports/proofs/<selection>.subjects.json
```

`gra-proofs` does not create new findings. Every proof must reference an
existing finding ID.

## Outputs

```text
reports/proofs.json
reports/PROOFS.md
reports/proofs/
```

`proofs.json` records `proof_type`, `status`, `safe_by_design`, referenced proof
files, structured commands run, evidence, and limitations. Every proof must set
`safe_by_design` to `true`.

`commands_run` is an array of structured command objects, not shell strings:

```json
{
  "argv": ["rg", "--line-number", "SEC-001", "repo/app.py"],
  "read_only": true,
  "writes": [],
  "network": false,
  "requires_credentials": false,
  "cwd_scope": "target_repo",
  "description": "Read-only local source inspection"
}
```

Use `commands_run: []` when no command was executed. The validator accepts only
read-only local inspection records for safe proof commands:

- `rg` without `--pre` / `--pre-glob`
- bounded `sed -n START,ENDp FILE` excerpts only
- exactly `python` / `python3 -m json.tool FILE` for read-only JSON inspection

Free-form shell command strings are rejected, and command metadata must be
consistent: `read_only: true`, `writes: []`, `network: false`, and
`requires_credentials: false`.

Allowed proof status values:

```text
confirmed / failed / not-run / needs-human-review
```

Use `not-run` or `needs-human-review` when validation would require unsafe
execution, dependency installation, credentials, live services, or broader
scope.

## Validation

Run:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

When `reports/proofs.json` exists, the validator checks its schema, timestamp,
proof IDs, finding references, allowed proof types, allowed status values,
`safe_by_design: true`, proof file paths under `reports/proofs/`, string-list
fields, structured proof command allowlists, and command safety metadata. A
valid result prints `Proofs: validated`.

## Issue publication

Do not copy proof artifacts wholesale into public issues. Use them to decide
whether issue wording should say confirmed, failed, not run, or needs human
review. If a proof cannot be run safely, document the limitation rather than
expanding scope or producing exploit code.

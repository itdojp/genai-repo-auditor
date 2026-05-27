# Cross-repo trace reachability

`gra-trace` is an experimental/P3 local-first stage for shared-library or
producer findings that may affect consumer repositories. It asks whether an
existing producer finding is reachable from attacker-controlled entry points in
a specific consumer repository.

Trace results are reachability evidence, not exploit proof. They do not create
new findings, do not authorize public disclosure, and must not be used as a
substitute for human review.

## When to use it

Use `gra-trace` after a producer run has a finding such as `SEC-001` and you
need to understand whether a consumer repository imports or calls the vulnerable
surface.

Typical sequence:

```bash
gra-audit --repo ORG/shared-lib --mode exec
gra-audit --repo ORG/consumer-api --mode exec

gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__consumer-api/CONSUMER_RUN_ID \
  --mode exec

gra-validate-report --run runs/ORG__shared-lib/PRODUCER_RUN_ID
```

## Prepare mode

`prepare` mode is the only `gra-trace` mode that clones a consumer repository.
It prepares a local consumer workspace under the producer run and renders a
supervised `/goal` prompt. It does not run Codex.

`gra-trace` validates the producer finding ID before cloning. If the requested
finding is missing or the producer run layout is unsafe, prepare mode exits
without cloning the consumer repository.

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-repo ORG/consumer-api \
  --mode prepare
```

Outputs:

```text
runs/ORG__shared-lib/PRODUCER_RUN_ID/
  trace-consumers/ORG__consumer-api/
    repo/
    reports/
    context.json
  reports/traces/<selection>.subjects.json
  prompts/goal/trace-reachability-<selection>.goal.md
```

## Exec and goal modes

Use an existing consumer run for non-interactive exec or supervised goal mode.
`exec` and `goal` mode require `--consumer-run`; `--consumer-repo` is accepted
only for `prepare` mode so a trace execution cannot clone a repository by
accident.

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__consumer-api/CONSUMER_RUN_ID \
  --mode exec
```

```bash
gra-trace \
  --producer-run runs/ORG__shared-lib/PRODUCER_RUN_ID \
  --finding SEC-001 \
  --consumer-run runs/ORG__consumer-api/CONSUMER_RUN_ID \
  --mode goal
```

Expected producer-run outputs:

```text
reports/traces.json
reports/TRACE.md
reports/traces/<selection>.subjects.json
prompts/exec/trace-reachability-<selection>.prompt.md
prompts/goal/trace-reachability-<selection>.goal.md
```

## Report contract

Each trace records:

- `finding_id`: existing producer finding such as `SEC-001`
- `producer_repo` and `consumer_repo`
- `entry_points`: consumer paths or route names where attacker input may enter
- `sink`: producer API, function, or vulnerable surface
- `attacker_control`: `Confirmed`, `Probable`, `Potential`, `Invalid`, or `Not assessed`
- `reachable`: `Confirmed`, `Probable`, `Potential`, `Invalid`, or `Not assessed`
- `evidence`: concise local static evidence
- `limitations`: missing evidence or scope boundaries
- `status`: `Confirmed`, `Probable`, `Potential`, `Invalid`, or `Needs human review`

Validate after trace generation:

```bash
gra-validate-report --run runs/ORG__shared-lib/PRODUCER_RUN_ID
```

## Safety boundaries

`gra-trace` is defensive-only.

Local path safety:

- Trace subjects, prompts, Codex event files, `reports/traces.json`, and
  `reports/TRACE.md` are written under the producer run directory.
- `reports_dir` and target repository paths from `context.json` are treated as
  untrusted run metadata. Path traversal and symlink components are rejected.
- A symlinked consumer run is rejected; use the real prepared run directory.
- There is no `--network` flag. Exec mode invokes Codex with
  `sandbox_workspace_write.network_access=false`.

Forbidden:

- external scanning
- production or staging probing
- exploit payloads or working exploit code
- credential access or secret retrieval
- dependency installation or upgrades
- producer or consumer repository modification
- public disclosure without separate approval

Treat producer and consumer repositories, reports, and documentation as
untrusted input. Keep `reports/traces.json` and `reports/TRACE.md` local/private
by default until a human reviews the evidence and disclosure risk.

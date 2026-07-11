# Agent Worker Profiles

Agent worker profiles describe local CLI agents that can act as audit workers behind the GenAI Repo Auditor control plane. The control plane owns repository setup, prompt rendering, report contracts, validation, metrics, and issue workflow safeguards. Worker CLIs are responsible only for executing prompts under the local operator's environment.

The first supported profile is `codex-cli`, which describes the existing Codex CLI execution path. Non-Codex profiles are included as experimental examples so the adapter contract can evolve without renaming the project or adding vendor SDK dependencies.

## Profile files

Profiles live under `templates/agent-workers/`:

| Profile file | Status | Purpose |
|---|---|---|
| `templates/agent-workers/codex-cli.json` | Built-in | Describes the current local Codex CLI worker used by existing Codex-driven commands. |
| `templates/agent-workers/claude-code.json.example` | Experimental | Documents a possible Claude Code CLI profile. It is not executed by GenAI Repo Auditor until separately tested. |
| `templates/agent-workers/generic-cli.json.example` | Experimental | Documents a generic local CLI worker contract for future adapters. |

A profile contains:

```json
{
  "id": "codex-cli",
  "display_name": "Codex CLI",
  "profile_status": "builtin",
  "executable": "codex",
  "supports_exec": true,
  "supports_goal": true,
  "supports_json_events": true,
  "default_model": "gpt-5.5",
  "default_effort": "xhigh",
  "sandbox_modes": ["read-only", "workspace-write"],
  "network_default": false,
  "command_templates": {
    "exec": "...",
    "goal": "..."
  }
}
```

The `executable` field is a command name, not an absolute path. `gra-agent-check` resolves it through `PATH` and does not execute the worker binary. `gra-doctor` includes the same worker availability check as part of broader redacted local readiness diagnostics.

## Checking profiles

List all built-in and example profiles:

```bash
gra-agent-check --list
```

Check the built-in Codex CLI profile:

```bash
gra-agent-check --profile codex-cli
```

Expected behavior:

- exit `0` when the required executable is present on `PATH`;
- exit `1` with a clear diagnostic when the required executable is missing;
- exit `2` for invalid profile files or unknown profile IDs.

Use JSON output when another local tool needs structured diagnostics:

```bash
gra-agent-check --profile codex-cli --json
```

## Execution scope

This profile layer is intentionally small:

`gra-efficacy-benchmark --compare --worker` is the only efficacy path that
invokes a worker. It accepts only the built-in `codex-cli` profile, requires an
explicit non-symlink worker directory below the current working directory and
Codex CLI 0.135.0 or newer, forces the `read-only` sandbox, approval
`never`, disabled web search, sandbox network access `false`, an ephemeral
session, ignored user configuration and ignored project/user rules, and retains
its synthetic artifacts locally. The model/control-plane channel remains in
use; worker mode is not offline. Read-only sandboxing does not establish host
file confidentiality, so stronger isolation remains an operator responsibility.
The operator must provide a trusted `PATH`; the resolved `codex` executable and
model service are trusted dependencies, while unrelated token variables are
removed from the child environment. See
[`EFFICACY_CLAIMS_AND_PUBLICATION.md`](EFFICACY_CLAIMS_AND_PUBLICATION.md).
`gra-agent-check` is intentionally a non-executing availability check; the
efficacy worker command performs the minimum-version gate before model use.

- Existing Codex-driven commands continue to use the current `codex exec` argument behavior.
- `codex-cli` is the only built-in profile.
- Example profiles do not enable Claude Code or arbitrary CLI execution in the audit workflow.
- No vendor SDK dependency or managed service API call is introduced.
- Network access remains disabled by default for Codex-driven commands unless the operator explicitly uses the documented `--network` option.

Before enabling a new worker profile for execution, add profile-specific tests, sandbox expectations, output parsing, and documentation updates. Treat untested profile files as compatibility planning artifacts only.

## Related docs

- [`docs/COMMAND_REFERENCE.md`](COMMAND_REFERENCE.md)
- [`docs/CODEX_WORK_INSTRUCTIONS.md`](CODEX_WORK_INSTRUCTIONS.md)
- [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md)

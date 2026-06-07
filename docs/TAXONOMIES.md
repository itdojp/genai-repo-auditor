# Taxonomy profiles

GenAI Repo Auditor supports optional controlled taxonomy mappings for findings
and targets. These mappings are advisory classification metadata; they do not
replace severity, confidence, status, risk, priority, or human review.

Machine-readable profiles live under `templates/taxonomies/`:

| File | Taxonomy name | Purpose |
|---|---|---|
| `owasp-llm-2025.json` | `OWASP LLM Top 10 2025` | LLM application risks such as prompt injection and excessive agency. |
| `owasp-ai-agent.json` | `OWASP AI Agent Security` | Agent autonomy, high-impact action, tool permission, memory/context, and monitoring risks. |
| `mcp-security.json` | `MCP Security` | Model Context Protocol risks such as token passthrough, confused deputy, SSRF, and scope minimization. |
| `supply-chain.json` | `Supply Chain Posture` | CI/CD, dependency, release, and governance posture categories. |
| `cwe-subset.json` | `CWE Subset` | A bounded CWE subset useful for SARIF and common source-code findings. |

Deterministic aliases and replacement suggestions live in
`templates/taxonomy-aliases.json`. The alias file is intentionally separate
from profile files so the controlled profile list remains bounded while known
operator normalizations can evolve.

## Finding and target shape

Use the optional `taxonomies` array on findings or targets:

```json
{
  "taxonomies": [
    {
      "name": "OWASP LLM Top 10 2025",
      "id": "LLM01",
      "label": "Prompt Injection"
    },
    {
      "name": "CWE Subset",
      "id": "CWE-78",
      "label": "OS Command Injection"
    }
  ]
}
```

`gra-validate-report` validates taxonomy names, IDs, and labels when this field
is present. Existing `cwe` and `owasp` arrays remain backward compatible and are
not treated as controlled fields.

## Preflight and normalization

Run `gra-taxonomy-preflight` before validating or publishing audit artifacts:

```bash
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
```

Without `--fix`, the command reports validation errors and deterministic
normalizations that would be applied. With `--fix`, it updates
`reports/findings.json` and `reports/targets.json` in place for configured
`mode: "auto"` mappings and canonical label corrections. Applied changes are
logged to `reports/taxonomy-normalizations.jsonl` with the before/after
reference, artifact path, field path, and reason.

Current automatic normalizations include:

- taxonomy name alias `CWE` -> `CWE Subset` when the ID is present in the
  bundled CWE profile
- configured broad access-control mapping `CWE-284` -> `CWE-862`
- canonical label corrections, for example `CWE-94` -> `Code Injection`

Context-sensitive mappings such as `CWE-73`, `CWE-116`, `CWE-266`, `CWE-345`,
and `CWE-639` are suggestion-only by default. The operator or reviewing agent
must choose the controlled taxonomy ID that matches the source-to-sink evidence.

`gra-audit`, `gra-targets --generate`, and `gra-research --mode exec` run
taxonomy preflight with `--fix` after Codex output and before validation or
status finalization. Supervised goal-mode runs should execute the command before
copying draft findings into central report artifacts.

## Adding or changing profiles

1. Add or update a JSON file under `templates/taxonomies/`.
2. Keep `schema_version`, `name`, `version`, `source_url`, and `entries` present.
3. Use stable IDs and labels. Do not rename IDs without a compatibility reason.
4. Add tests for valid and invalid IDs.
5. Add alias or replacement behavior to `templates/taxonomy-aliases.json` only
   when the mapping is deterministic enough to automate or useful enough to
   present as a suggestion.
6. Update prompts or docs only when new taxonomy families should be suggested to agents.

## Outputs

- `gra-dashboard` groups findings and targets by taxonomy name and ID.
- `gra-sarif` carries taxonomy references in SARIF properties and maps CWE IDs
  into rule properties when available.
- Prompts ask agents to use controlled taxonomy IDs instead of ad hoc labels.

## Sources and version notes

The bundled taxonomy files intentionally contain a bounded subset that is useful
for repository auditing. Review upstream sources before expanding the lists:

- OWASP Top 10 for Large Language Model Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- OWASP AI Agent Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html
- MCP Security Best Practices: https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices
- CWE: https://cwe.mitre.org/

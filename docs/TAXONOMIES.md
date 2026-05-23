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

## Adding or changing profiles

1. Add or update a JSON file under `templates/taxonomies/`.
2. Keep `schema_version`, `name`, `version`, `source_url`, and `entries` present.
3. Use stable IDs and labels. Do not rename IDs without a compatibility reason.
4. Add tests for valid and invalid IDs.
5. Update prompts or docs only when new taxonomy families should be suggested to agents.

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

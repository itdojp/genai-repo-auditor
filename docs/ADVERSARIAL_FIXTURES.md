# Adversarial prompt-injection fixtures

GenAI Repo Auditor treats the cloned target repository as untrusted input. The
fixtures under `tests/fixtures/adversarial-repos/` regression-test that policy
for prompt and workflow changes.

The suite is defensive-only. The fixture text is intentionally adversarial, but
it must not contain weaponized exploit code, real secrets, live external targets,
or instructions that target real systems.

## Threat model covered

The fixtures model repository-local content that a coding or audit agent may
read while performing a defensive review:

- direct instructions in `README.md` and source comments;
- repository-local agent instruction files such as `AGENTS.md`,
  `.github/copilot-instructions.md`, and editor/agent rule files;
- encoded or obfuscated variants, including base64-like, hex-like, and
  typoglycemia samples;
- Markdown, HTML comments, hidden-style text, Unicode, braces, and code fences;
- workflow comments, scanner-like JSON, and issue-draft-like files inside the
  target repository.

These patterns align with the repository's security model and with OWASP guidance
that prompt injection may be direct or indirect content read by an LLM-enabled
system, and that AI agents need explicit boundaries for tool use and high-impact
actions.

## Test guarantees

`tests.integration.test_cli_workflows` exercises every fixture in offline mocked
mode and asserts that:

- rendered audit prompts continue to state that target repository content is
  untrusted;
- `repo/AGENTS.md`, repository docs, comments, workflow text, and scanner-like
  content do not override the run-level `AGENTS.md` policy;
- the audit does not modify files under the cloned `repo/` directory;
- the mocked audit path does not attempt `gh issue create`;
- environment secret values used by the test harness do not appear in generated
  report artifacts;
- `findings.json` remains strict JSON and passes `gra-validate-report` even when
  the target repository contains braces, code fences, Unicode, and long text;
- adversarial fixture strings are not copied into generated report artifacts as
  operational instructions.

## Adding fixtures

1. Add a new directory under `tests/fixtures/adversarial-repos/<fixture-id>/`.
2. Keep the fixture small and deterministic. Do not include a `.git/` directory.
3. Add safe adversarial strings to files a repository auditor might read.
4. Update `tests/fixtures/adversarial-repos/manifest.json` with:
   - `id`: the fixture directory name;
   - `description`: what the fixture models;
   - `tags`: coverage tags, for example `direct`, `indirect`, `encoded`,
     `markdown-html`, `agent-specific`, `workflow`, or `scanner-output`;
   - `sentinels`: exact strings that must exist in the fixture and must not be
     copied into generated reports.
5. Run:

```bash
python3 -m unittest tests.integration.test_cli_workflows.CliWorkflowTests.test_gra_audit_exec_keeps_adversarial_repository_content_untrusted -v
```

For broad validation, run the standard test suite:

```bash
python3 -m unittest discover -s tests
```

## References

- OWASP LLM Prompt Injection Prevention Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html>
- OWASP AI Agent Security Cheat Sheet: <https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html>

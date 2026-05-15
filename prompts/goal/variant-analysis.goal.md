/goal Perform supervised defensive variant analysis from the supplied seed root cause and update local reports.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Variant source: {{VARIANT_SOURCE}}
- Seed finding or source ID: {{FINDING_ID}}

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- {{VARIANT_SOURCE}}
- {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json if present
- {{REPORTS_DIR}}/THREAT_MODEL.md and {{REPORTS_DIR}}/ATTACK_SURFACE.md if present

Objective:
Find structurally similar instances of the same security root cause in this repository. Do not produce exploit code and do not modify target repository files.

Allowed changes:
- Create/update files only under {{REPORTS_DIR}}/
- Do not modify files under {{TARGET_REPO_DIR}}/

Forbidden actions:
- No external network requests
- No production or staging access
- No live exploitation
- No scanning of external hosts
- No dependency installation or upgrades
- No destructive commands
- No credential or GitHub Secrets operations
- No weaponized exploit code
- No full secret output

Work method:
- Extract the root-cause pattern from the seed.
- Search for equivalent trust-boundary, authorization, validation, sink, parser, workflow, or business-logic failures.
- Reject candidates that are not reachable or are mitigated.
- Use safe static call-path validation or benign local tests only.
- Keep {{REPORTS_DIR}}/AUDIT_LOG.md updated.

Required outputs:
- {{REPORTS_DIR}}/variant-analysis/{{FINDING_ID}}.md
- Updates to {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json only if variants are discovered
- Issue drafts for issue_recommended findings

Stop condition:
- variant-analysis report exists
- variants are deduplicated and schema-compatible
- no files under {{TARGET_REPO_DIR}}/ were modified

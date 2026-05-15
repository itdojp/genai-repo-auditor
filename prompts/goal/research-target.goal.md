/goal Perform a supervised defensive deep dive for one security target and update local reports.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Target ID: {{TARGET_ID}}
- Target category: {{TARGET_CATEGORY}}
- Target file: {{TARGET_FILE}}

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- {{TARGET_FILE}}
- {{REPORTS_DIR}}/THREAT_MODEL.md if present
- {{REPORTS_DIR}}/ATTACK_SURFACE.md if present
- {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json if present
- relevant target repository files only for this target

Objective:
Research exactly this target and determine whether actionable security findings exist. Do not broaden into a full repository audit.

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
- Work in checkpoints and keep {{REPORTS_DIR}}/AUDIT_LOG.md updated.
- Identify entry points, trust boundaries, invariants, and sensitive sinks.
- Trace source-to-sink paths.
- Check existing mitigations before reporting.
- Use scanner results only as leads.
- Use safe local validation only.
- If evidence is insufficient, downgrade, mark Needs human review, or omit.

Required outputs:
- {{REPORTS_DIR}}/target-research/{{TARGET_ID}}.md
- Updates to {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json only if findings are discovered
- Issue drafts for issue_recommended findings
- Updated {{REPORTS_DIR}}/AUDIT_LOG.md

Stop condition:
- target research report exists
- any new findings are schema-compatible and deduplicated
- Critical/High findings have file:line evidence and plausible call paths or are downgraded
- no files under {{TARGET_REPO_DIR}}/ were modified

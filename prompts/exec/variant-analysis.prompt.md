You are running in an audit run directory for an authorized defensive source-code security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Branch/ref: {{BRANCH}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Variant source: {{VARIANT_SOURCE}}
- Seed finding or source ID: {{FINDING_ID}}

Primary objective:
Perform defensive variant analysis. Use the seed root cause to find structurally similar issues in the same repository. Do not modify target repository files.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- {{VARIANT_SOURCE}}
- {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json if present
- {{REPORTS_DIR}}/THREAT_MODEL.md and {{REPORTS_DIR}}/ATTACK_SURFACE.md if present
- Relevant repository files under {{TARGET_REPO_DIR}}/

Forbidden actions:
- No external network requests
- No production or staging access
- No live exploitation
- No scanning of external hosts
- No dependency installation or upgrades
- No destructive commands
- No weaponized exploit code
- No full secret output
- No modifications under {{TARGET_REPO_DIR}}/

Method:
- Extract the root-cause pattern from the seed finding or source note.
- Identify code patterns that share the same trust-boundary failure, missing validation, missing authorization invariant, unsafe sink, unsafe parser, unsafe workflow trigger, or equivalent logic error.
- Search structurally, not just by identical string or API name.
- For each candidate, determine whether the same security invariant is violated.
- Reject candidates that are mitigated by middleware, policy, framework behavior, safe configuration, or non-reachable code paths.
- Do not produce exploit payloads. Use static call-path reasoning and safe local validation only.

Required outputs:
1. Create or update {{REPORTS_DIR}}/variant-analysis/{{FINDING_ID}}.md with:
   - seed root cause
   - variant search strategy
   - files and patterns inspected
   - confirmed variants
   - rejected variants with rationale
   - unresolved questions

2. If variants are found, update {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json.
   - Preserve existing findings.
   - Set variant_of to {{FINDING_ID}}.
   - Deduplicate by root cause, affected path, and trust boundary.
   - Create issue drafts for issue_recommended findings.

3. Update {{REPORTS_DIR}}/AUDIT_LOG.md.

Stop condition:
- {{REPORTS_DIR}}/variant-analysis/{{FINDING_ID}}.md exists.
- Existing central findings are preserved.
- Any variants are represented consistently in FINDINGS.md and findings.json.
- No files under {{TARGET_REPO_DIR}}/ have been modified.

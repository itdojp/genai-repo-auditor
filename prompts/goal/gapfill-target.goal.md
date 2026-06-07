/goal Perform a supervised bounded gapfill review for one target coverage gap.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Source target ID: {{TARGET_ID}}
- Gapfill seed file: {{GAPFILL_TARGET_FILE}}
- Gapfill output: {{GAPFILL_OUTPUT_MD}}
- Coverage ledger: {{GAPFILL_COVERAGE_FILE}}

Objective:
Close or explicitly document the remaining coverage gap for this single target. Do not broaden into a full repository audit.

Allowed changes:
- Create/update files only under {{REPORTS_DIR}}/
- Do not modify files under {{TARGET_REPO_DIR}}/

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- targets.schema.json
- {{GAPFILL_TARGET_FILE}}
- {{GAPFILL_COVERAGE_FILE}} if present
- {{REPORTS_DIR}}/target-research/{{TARGET_ID}}.md if present
- relevant target repository files only for this gapfill

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
- Focus on `files_skipped`, `unresolved_questions`, and `gapfill_reason` from the seed file.
- Respect the source target's `max_files` value if present.
- Prefer skipped files and unresolved questions over re-reading already reviewed files.
- If evidence remains insufficient within the bound, record `needs-human-review` or leave `gapfill_recommended: true` with a clear reason.
- Use safe local validation only.

Required outputs:
- {{GAPFILL_OUTPUT_MD}}
- Optional updates to {{REPORTS_DIR}}/targets.json coverage metadata
- Updates to {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json only if findings are discovered
- Issue drafts for issue_recommended findings
- Updated {{REPORTS_DIR}}/AUDIT_LOG.md
- Controlled taxonomy references must use templates/taxonomies/ IDs and labels
  and be preflighted against templates/taxonomy-aliases.json before central
  report artifacts are finalized.

Stop condition:
- gapfill report exists
- target coverage metadata states whether the gap is closed, partially closed, or still needs human review
- any new findings are schema-compatible and deduplicated
- no files under {{TARGET_REPO_DIR}}/ were modified

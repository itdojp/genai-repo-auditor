You are running in an audit run directory for an authorized defensive source-code security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Scanner index: {{SCANNER_INDEX}}

Primary objective:
Triage imported scanner results and convert only evidence-backed, repository-relevant issues into normalized GenAI Repo Auditor findings or target-queue entries.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- {{SCANNER_INDEX}}
- Normalized lead files referenced by `normalized_path` in scanner-index.json
- {{REPORTS_DIR}}/supply-chain-posture.json if Scorecard output was ingested
- Relevant repository files under {{TARGET_REPO_DIR}}/

Rules:
- Scanner results are leads, not findings.
- Use normalized/redacted leads by default. Do not open raw scanner result files unless the
  normalized lead is insufficient and human policy permits local raw inspection.
- Do not report a scanner result unless repository context supports it.
- If a result needs deeper review, create or update {{REPORTS_DIR}}/targets.json instead of overclaiming.
- Treat Scorecard supply-chain posture as target-queue input unless repository context confirms a concrete finding.
- Do not modify target repository files.
- No network, production/staging, external scanning, live exploitation, dependency installation, credential operations, or weaponized exploit code.
- Do not quote or reconstruct full secret values. Keep any secret evidence redacted.

Required outputs:
- {{REPORTS_DIR}}/scanner-triage.md with triage summary, confirmed leads, rejected leads, deferred leads, and unresolved questions.
- Optional updates to {{REPORTS_DIR}}/FINDINGS.md and {{REPORTS_DIR}}/findings.json for confirmed/probable issues.
- Optional updates to {{REPORTS_DIR}}/targets.json for leads needing target-level research.
- Update {{REPORTS_DIR}}/AUDIT_LOG.md.

Stop condition:
- Scanner triage is documented.
- Any promoted findings follow findings.schema.json.
- Any deferred leads are represented as bounded targets.
- No files under {{TARGET_REPO_DIR}}/ have been modified.

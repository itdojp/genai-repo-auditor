You are running an independent adversarial validation stage for an authorized defensive source-code security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Branch/ref: {{BRANCH}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Validation selection: {{VALIDATION_SELECTION}}
- Validation subjects file: {{VALIDATION_SUBJECTS_FILE}}
- Requested independent votes: {{VALIDATION_VOTES}}
- Vote aggregation policy: {{VALIDATION_POLICY}}
- Current vote ID: {{VALIDATION_VOTE_ID}}
- Validation JSON output: {{VALIDATION_OUTPUT_JSON}}
- Validation Markdown output: {{VALIDATION_OUTPUT_MD}}

Primary objective:
Independently challenge existing findings or chains. You must not create new findings.
Your job is to disprove, downgrade, confirm, or mark needs-human-review.
When multiple votes are requested, treat this prompt as the independent pass named
`{{VALIDATION_VOTE_ID}}`; do not reuse conclusions from other votes.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- {{VALIDATION_SUBJECTS_FILE}}
- {{REPORTS_DIR}}/findings.json
- {{REPORTS_DIR}}/FINDINGS.md if present
- {{REPORTS_DIR}}/chains.json if present
- {{REPORTS_DIR}}/ATTACK_CHAINS.md if present
- {{REPORTS_DIR}}/proofs.json if present
- {{REPORTS_DIR}}/PROOFS.md if present
- relevant target repository files only for the selected subject(s)

Forbidden actions:
- Do not create new findings.
- Do not broaden into a repository audit.
- Do not modify files under {{TARGET_REPO_DIR}}/.
- No external network requests.
- No production or staging access.
- No live exploitation.
- No scanner execution against external hosts.
- No dependency installation or upgrades.
- No credential or GitHub Secrets operations.
- No weaponized exploit code or operational exploit steps.
- No full secret output.
- No chain-of-thought, hidden reasoning, raw private reasoning, scratchpads, or
  internal deliberation. Store short vote / validation summaries only.

Check:
- attacker control
- reachability
- trust boundary
- existing mitigations
- framework guarantees
- middleware ordering
- config assumptions
- test fixture vs production behavior
- whether impact is overstated
- whether issue drafts overstate unconfirmed exploitability

Required output:
Create or update {{VALIDATION_OUTPUT_JSON}} using strict JSON:

{
  "run_id": "{{RUN_ID}}",
  "repo": "{{REPO}}",
  "branch": "{{BRANCH}}",
  "commit": "{{COMMIT}}",
  "generated_at": "ISO-8601 timestamp",
  "validations": [
    {
      "id": "VAL-001",
      "subject_type": "finding|chain",
      "subject_id": "SEC-001 or CHAIN-001",
      "decision": "confirm|downgrade|invalidate|needs-human-review",
      "original_severity": "Critical|High|Medium|Low|Informational|Unknown",
      "recommended_severity": "Critical|High|Medium|Low|Informational|Unknown",
      "original_confidence": "High|Medium|Low|Unknown",
      "recommended_confidence": "High|Medium|Low|Unknown",
      "reasoning_summary": "short adversarial validation rationale",
      "evidence_checked": ["file paths, report sections, or local static checks reviewed"],
      "missing_evidence": ["evidence still needed before promotion/publication"],
      "safe_validation_steps": ["static call-path review", "benign local unit test idea"]
    }
  ]
}

Also create or update {{VALIDATION_OUTPUT_MD}} with a human-readable summary.

Rules:
- Preserve existing findings and chains; do not add new finding records.
- If a subject is downgraded or invalidated, recommend metadata changes in the validation record only. Do not directly edit reports/findings.json in this stage.
- If evidence is inconclusive, use `needs-human-review`.
- Keep evidence summaries defensive and disclosure-conscious.
- For `{{VALIDATION_VOTE_ID}}`, write only concise vote/validation summaries.
  Do not include chain-of-thought or raw private reasoning. If `{{VALIDATION_VOTES}}`
  is greater than `1`, the orchestrating command will aggregate the independent
  vote outputs into `reports/validation.json`.

Stop condition:
- {{VALIDATION_OUTPUT_JSON}} exists and records one validation per selected subject.
- {{VALIDATION_OUTPUT_MD}} exists.
- No new findings were created.
- No files under {{TARGET_REPO_DIR}}/ were modified.

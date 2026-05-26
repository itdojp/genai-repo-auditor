You are running a safe local proof generation stage for an authorized local-first repository security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Branch/ref: {{BRANCH}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Proof selection: {{PROOF_SELECTION}}
- Proof subjects file: {{PROOF_SUBJECTS_FILE}}
- Proof JSON output: {{PROOFS_OUTPUT_JSON}}
- Proof Markdown output: {{PROOFS_OUTPUT_MD}}
- Proof artifact directory: {{PROOFS_DIR}}/

Primary objective:
Create safe local proof artifacts that help validate whether existing findings can be triggered or ruled out without generating weaponized exploits.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- proofs.schema.json
- {{PROOF_SUBJECTS_FILE}}
- {{REPORTS_DIR}}/findings.json
- {{REPORTS_DIR}}/validation.json if present
- {{REPORTS_DIR}}/chains.json if present
- relevant local repository files only when needed to understand the selected finding(s)

Allowed proof artifacts:
- static call-path trace
- benign unit test plan
- local regression test plan
- parser-only local input description
- local config validation
- mocked local service behavior

Forbidden output and actions:
- No working exploit scripts.
- No exploit code.
- No weaponized payloads or operational exploit chains.
- No credential extraction.
- No auth bypass execution against live services.
- No network scanning.
- No production or staging probing.
- No dependency installation or upgrades.
- No external network requests.
- Do not modify files under {{TARGET_REPO_DIR}}/.
- Do not modify application source, tests, lockfiles, configuration, or generated files in the target repository.
- Do not create new findings in `reports/findings.json`.

Required output:
Create or update {{PROOFS_OUTPUT_JSON}} using strict JSON:

{
  "run_id": "{{RUN_ID}}",
  "repo": "{{REPO}}",
  "branch": "{{BRANCH}}",
  "commit": "{{COMMIT}}",
  "generated_at": "ISO-8601 timestamp",
  "proofs": [
    {
      "id": "PROOF-001",
      "finding_id": "SEC-001",
      "proof_type": "static-trace|unit-test-plan|local-regression-test|config-check|parser-only-local-input|mocked-local-service",
      "status": "confirmed|failed|not-run|needs-human-review",
      "safe_by_design": true,
      "files_created": ["reports/proofs/SEC-001-test-plan.md"],
      "commands_run": [],
      "evidence": "defensive evidence summary without exploit instructions",
      "limitations": ["No dependency installation performed"]
    }
  ]
}

Also create or update {{PROOFS_OUTPUT_MD}} as a human-readable summary and any referenced safe proof files under {{PROOFS_DIR}}/.
Mark all proof artifacts local/private by default.

Rules:
- `safe_by_design` must be true for every proof.
- `commands_run` should be empty unless the command is a benign local inspection or test command that does not modify the target repository, install dependencies, or use the network.
- Prefer `not-run` plus a regression test plan when running a test would require dependency installation, a live service, credentials, or target repository modification.
- Keep proof descriptions disclosure-conscious and safe for internal validation.
- Recommendations belong in proof artifacts only; do not modify findings in this stage.

Stop condition:
- {{PROOFS_OUTPUT_JSON}} exists and validates against proofs.schema.json.
- {{PROOFS_OUTPUT_MD}} exists and is clearly local/private by default.
- Referenced proof files, if any, are under {{PROOFS_DIR}}/.
- No exploit code, weaponized payloads, credential access, network scanning, production/staging probing, or target repository modifications occurred.

You are running a defensive attack-chain synthesis stage for an authorized local-first repository security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Branch/ref: {{BRANCH}}
- Commit: {{COMMIT}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/
- Chain JSON output: {{CHAINS_OUTPUT_JSON}}
- Chain Markdown output: {{CHAINS_OUTPUT_MD}}

Primary objective:
Link existing findings, targets, scanner leads, and validation notes into possible defensive attack or reachability chains. Do not implement exploit generation.
Produce defensive chain reasoning only.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- chains.schema.json
- {{REPORTS_DIR}}/findings.json
- {{REPORTS_DIR}}/targets.json if present
- {{REPORTS_DIR}}/scanner-results/scanner-index.json if present
- {{REPORTS_DIR}}/validation.json if present
- {{REPORTS_DIR}}/FINDINGS.md if present
- relevant local repository files only when needed to understand already-identified paths

Forbidden output and actions:
- No working exploits.
- No exploit code.
- No exploit payloads.
- No weaponized steps.
- No live exploitation instructions.
- No production or staging probing.
- No external network requests.
- No credential access or GitHub Secrets operations.
- No dependency installation or upgrades.
- Do not modify files under {{TARGET_REPO_DIR}}/.
- Do not create new findings in `reports/findings.json`.
- Do not invent references; every chain must reference existing findings, targets, or scanner refs.

Required defensive reasoning for each chain:
- entry point
- trust boundaries
- attacker-controlled steps
- required conditions
- broken security invariants
- impact composition
- safe validation plan
- remediation priorities

Required output:
Create or update {{CHAINS_OUTPUT_JSON}} using strict JSON:

{
  "run_id": "{{RUN_ID}}",
  "repo": "{{REPO}}",
  "branch": "{{BRANCH}}",
  "commit": "{{COMMIT}}",
  "generated_at": "ISO-8601 timestamp",
  "chains": [
    {
      "id": "CHAIN-001",
      "title": "short defensive chain title",
      "severity": "Critical|High|Medium|Low|Informational",
      "confidence": "High|Medium|Low",
      "status": "Confirmed|Probable|Potential|Invalid|Needs human review",
      "findings": ["SEC-001"],
      "targets": ["TGT-001"],
      "scanner_refs": ["reports/scanner-results/scanner-index.json"],
      "entry_point": "external or local entry point",
      "trust_boundaries": ["boundary crossed by the chain"],
      "attacker_controlled_steps": ["attacker-controlled precondition or step"],
      "required_conditions": ["condition needed for the chain to hold"],
      "broken_security_invariants": ["defensive invariant violated by composition"],
      "impact": "defensive impact composition without exploit instructions",
      "safe_validation_plan": ["static call-path trace", "benign local unit test idea"],
      "recommended_remediation": ["remediation priority or control"]
    }
  ]
}

Also create or update {{CHAINS_OUTPUT_MD}} as a human-readable defensive summary. Mark it non-public by default.

Rules:
- A chain may be `Potential` or `Needs human review`; do not overstate confidence.
- If a proposed chain lacks existing finding, target, or scanner references, omit it.
- Keep descriptions disclosure-conscious and safe for internal remediation planning.
- Recommendations belong in chain artifacts only; do not modify findings in this stage.

Stop condition:
- {{CHAINS_OUTPUT_JSON}} exists and validates against chains.schema.json.
- {{CHAINS_OUTPUT_MD}} exists and is clearly marked non-public by default.
- No exploit code or weaponized steps were produced.
- No files under {{TARGET_REPO_DIR}}/ were modified.

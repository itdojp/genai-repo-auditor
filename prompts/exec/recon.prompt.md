You are running in an audit run directory for an authorized defensive source-code security audit.

Run context:
- Run ID: {{RUN_ID}}
- Repository: {{REPO}}
- Branch/ref: {{BRANCH}}
- Commit: {{COMMIT}}
- Visibility: {{VISIBILITY}}
- Target repository directory: {{TARGET_REPO_DIR}}/
- Reports directory: {{REPORTS_DIR}}/

Primary objective:
Perform reconnaissance only: repository inventory, threat model, and attack surface map. Do not produce vulnerability findings unless an obvious critical exposure is encountered; if so, record it as a candidate note, not a confirmed finding.

Read first:
- AGENTS.md
- context.json
- {{TARGET_REPO_DIR}}/README and architecture docs if present
- package manifests and lockfiles
- Dockerfiles, container files, IaC files if present
- .github/workflows if present
- reports/agent-surface.json if present; treat it as deterministic review leads for AI agent and MCP surfaces
- reports/provenance-posture.json if present; treat it as deterministic release provenance and attestation posture leads
- source tree and route definitions
- auth/session modules, persistence layer, webhooks, background jobs, CLI/admin scripts, file upload/import/parser paths

Forbidden actions:
- No external network requests
- No production or staging access
- No live exploitation
- No scanning of external hosts
- No dependency installation or upgrades
- No destructive commands
- No credential rotation or secrets operations
- No weaponized exploit code
- No modifications under {{TARGET_REPO_DIR}}/

Required outputs:
1. {{REPORTS_DIR}}/AUDIT_SUMMARY.md
   - repository overview
   - detected languages/frameworks
   - build/test/lint commands if inferable
   - major application components
   - major unknowns

2. {{REPORTS_DIR}}/THREAT_MODEL.md
   - assets
   - actors
   - entry points
   - untrusted inputs
   - trust boundaries
   - authentication and authorization assumptions
   - tenant/account isolation assumptions
   - sensitive data flows
   - privileged operations
   - risky components

3. {{REPORTS_DIR}}/ATTACK_SURFACE.md
   - public routes
   - admin routes
   - auth/session/token paths
   - webhook handlers
   - file upload/import/parser paths
   - outbound URL fetchers
   - background jobs and queue consumers
   - CLI/admin scripts
   - database access layer
   - secrets/logging/error reporting paths
   - CI/CD workflows
   - release provenance, artifact attestation, package publishing, container publishing, and SBOM attestation posture
   - AI agent, MCP, prompt-template, tool-definition, and model-provider surfaces
   - container/IaC surfaces
   - dependency/build surfaces

4. {{REPORTS_DIR}}/AUDIT_LOG.md
   - commands run
   - files inspected at a high level
   - assumptions
   - skipped areas
   - unresolved questions

Stop condition:
- Required recon files exist.
- No files under {{TARGET_REPO_DIR}}/ have been modified.
- The next recommended command is included at the end of AUDIT_LOG.md.

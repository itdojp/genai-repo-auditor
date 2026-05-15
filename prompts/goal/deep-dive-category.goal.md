/goal Deeply review one security category in the target repository and update local reports without modifying target repository files.

Operator must replace these placeholders before use:
- TARGET_CATEGORY: Authentication | Authorization | Tenant Isolation | Injection | SSRF | CI/CD | Supply Chain | Secrets | Logging | Container/IaC | Business Logic
- TARGET_SCOPE: concrete paths, modules, services, workflows, or routes to prioritize

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- reports/THREAT_MODEL.md if present
- reports/ATTACK_SURFACE.md if present
- reports/FINDINGS.md if present
- reports/findings.json if present
- relevant source files under repo/

Primary objective:
Perform a focused deep-dive review of TARGET_CATEGORY over TARGET_SCOPE and update the local security report set with evidence-backed findings only.

Allowed changes:
- Update reports/FINDINGS.md
- Update reports/findings.json
- Update reports/AUDIT_LOG.md
- Update reports/ATTACK_SURFACE.md and reports/THREAT_MODEL.md if the model is incomplete
- Create reports/deep-dives/TARGET_CATEGORY.md
- Create or update reports/issue-drafts/SEC-XXX.md for issue_recommended findings

Forbidden actions:
- Do not modify files under repo/
- No external network requests
- No live exploitation
- No production or staging access
- No dependency installation
- No git push, PR, or Issue creation
- No weaponized exploit code or step-by-step exploit instructions
- No full secret output

Deep-dive method:
1. Inventory TARGET_SCOPE.
2. Define the relevant security invariants.
3. Map entry points, trust boundaries, state transitions, and sensitive sinks.
4. Trace concrete code paths.
5. Look for bypasses, missing checks, confused deputy cases, unsafe defaults, and framework-specific pitfalls.
6. Validate candidate findings using local static evidence and benign local tests only where appropriate.
7. Deduplicate with existing findings.
8. Update findings with severity, confidence, status, validation evidence, and issue recommendation.
9. Record limitations and unresolved questions.

Stop condition:
- TARGET_CATEGORY review has a documented coverage summary.
- New or updated findings are evidence-backed and deduplicated.
- findings.json remains strict JSON.
- No files under repo/ have been modified.

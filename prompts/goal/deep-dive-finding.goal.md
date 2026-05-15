/goal Deeply validate one existing security finding without modifying target repository files.

Operator must replace these placeholders before use:
- TARGET_FINDING_ID: SEC-XXX
- TARGET_QUESTION: what must be resolved, for example "is this actually exploitable across tenant boundary?"

Read first:
- AGENTS.md
- context.json
- reports/FINDINGS.md
- reports/findings.json
- reports/AUDIT_LOG.md
- affected source files under repo/

Primary objective:
For TARGET_FINDING_ID, determine whether the finding is Confirmed, Probable, Potential, Invalid, or Needs human review. Resolve TARGET_QUESTION using concrete local evidence.

Allowed changes:
- Update reports/FINDINGS.md
- Update reports/findings.json
- Update reports/AUDIT_LOG.md
- Update the corresponding reports/issue-drafts/SEC-XXX.md
- Optionally create reports/deep-dives/SEC-XXX.md

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
1. Restate the finding and the exact question being resolved.
2. Identify the entry point and all callers.
3. Trace the source-to-sink path or prove no viable path exists.
4. Identify all validators, authn/authz checks, tenant filters, framework protections, and sanitizers on the path.
5. Check relevant tests and configuration.
6. Decide whether the issue is exploitable, mitigated, configuration-dependent, unreachable, or insufficiently evidenced.
7. Update severity, confidence, status, validation_status, and issue recommendation.
8. Record commands and reasoning in reports/AUDIT_LOG.md and reports/deep-dives/SEC-XXX.md.

Stop condition:
- TARGET_FINDING_ID has a final validation decision or clearly states the missing evidence.
- reports/findings.json remains strict JSON.
- issue draft is aligned with the final decision.
- No files under repo/ have been modified.

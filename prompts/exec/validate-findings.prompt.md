You are validating an existing local GenAI Repo Auditor report.

Read:
- AGENTS.md
- context.json
- reports/FINDINGS.md
- reports/findings.json
- affected files under repo/ for Critical and High findings

Primary objective:
Reduce false positives in Critical and High findings using safe local evidence only. Do not modify target repository files.

Allowed changes:
- Update reports/FINDINGS.md
- Update reports/findings.json
- Update reports/AUDIT_LOG.md
- Update relevant issue drafts under reports/issue-drafts/

Forbidden:
- No external network requests
- No live exploitation
- No weaponized payloads
- No dependency installation
- No full secret output
- No modification under repo/
- No git push, PR, or Issue creation

For each Critical and High finding:
- Re-read the affected code path.
- Verify entry point, trust boundary, call path, and mitigation status.
- Check existing validators, middleware, framework protections, and policy enforcement.
- Mark as Confirmed, Probable, Potential, Invalid, or Needs human review.
- Downgrade severity/confidence if evidence is weak.
- If invalid, explain why.

Stop condition:
- All Critical and High findings have updated validation status.
- findings.json remains strict JSON.
- issue drafts reflect the updated status.
- No files under repo/ have been modified.

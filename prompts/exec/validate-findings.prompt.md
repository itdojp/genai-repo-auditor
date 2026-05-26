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
- Separately assess bug existence, attacker reachability, boundary crossing, and impact.
- Check existing validators, middleware, framework protections, and policy enforcement.
- Mark as Confirmed, Probable, Potential, Invalid, or Needs human review.
- Set `bug_existence`, `attacker_reachability`, `boundary_crossing`, and
  `impact_assessment` to Confirmed, Probable, Potential, Invalid, or Not assessed.
- Update `assessment_notes` with concise evidence for each dimension.
- Downgrade severity/confidence if evidence is weak.
- If invalid, explain why.

Stop condition:
- All Critical and High findings have updated validation status.
- All Critical and High findings have structured exploitability assessment fields or explicit `Not assessed` values with notes.
- findings.json remains strict JSON.
- issue drafts reflect the updated status.
- No files under repo/ have been modified.

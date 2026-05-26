/goal Validate the Critical and High findings in reports/findings.json using only safe local evidence, without modifying target repository files.

Read first:
- AGENTS.md
- context.json
- findings.schema.json
- reports/FINDINGS.md
- reports/findings.json
- reports/AUDIT_LOG.md
- affected source files under repo/

Primary objective:
Reduce false positives and improve evidence quality for the highest-priority findings.

Allowed changes:
- Update reports/FINDINGS.md
- Update reports/findings.json
- Update reports/AUDIT_LOG.md
- Update reports/issue-drafts/*.md

Forbidden actions:
- Do not modify files under repo/
- No external network requests
- No live exploitation
- No production or staging access
- No scanning of external hosts
- No dependency installation
- No credential rotation
- No GitHub Secrets operations
- No git push, PR, or Issue creation
- No weaponized exploit code or step-by-step exploit instructions
- No full secret output

For each Critical or High finding:
- Re-read the affected code path.
- Verify the entry point.
- Verify the trust boundary.
- Verify the source-to-sink or call path.
- Separately assess bug existence, attacker reachability, boundary crossing,
  and impact. A code bug can exist even when reachability or impact remains
  unproven.
- Check whether validators, middleware, access policies, framework protections, or configuration mitigate the issue.
- Use safe local static evidence or benign tests only when useful and local.
- Mark the finding as Confirmed, Probable, Potential, Invalid, or Needs human review.
- Set `bug_existence`, `attacker_reachability`, `boundary_crossing`, and
  `impact_assessment` to Confirmed, Probable, Potential, Invalid, or Not
  assessed, with concise `assessment_notes`.
- Downgrade severity/confidence if evidence is weak.
- If invalid, move it to an Invalid or Rejected section with rationale.
- Update issue drafts so they do not publish unvalidated claims.

Stop condition:
- All Critical and High findings have updated validation status.
- All Critical and High findings have structured assessment fields or explicit
  Not assessed values with notes.
- findings.json remains strict JSON.
- FINDINGS.md and findings.json are consistent.
- Invalid findings are separated with rationale.
- No files under repo/ have been modified.

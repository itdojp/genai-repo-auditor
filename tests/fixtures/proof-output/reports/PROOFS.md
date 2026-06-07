# Safe Local Proofs

Local/private by default. Benign validation artifacts only.

| ID | Finding | Type | Status | Safe by design | Evidence |
|---|---|---|---|---|---|
| PROOF-001 | SEC-001 | unit-test-plan | not-run | true | Fixture proof plan. |

Commands for PROOF-001:
- `rg --line-number SEC-001 repo/app.py` (read_only=True, network=False, requires_credentials=False, cwd_scope=target_repo)
- `sed -n 1,80p repo/app.py` (read_only=True, network=False, requires_credentials=False, cwd_scope=target_repo)
- `python3 -m json.tool reports/findings.json` (read_only=True, network=False, requires_credentials=False, cwd_scope=run)

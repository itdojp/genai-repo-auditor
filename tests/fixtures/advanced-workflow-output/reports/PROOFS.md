# Fixture safe local proofs

Safe proof artifacts use benign local plans only and contain no weaponized payloads.

Commands for PROOF-101:
- `rg --line-number upload repo/src/routes.ts` (read_only=True, network=False, requires_credentials=False, cwd_scope=target_repo)

Commands for PROOF-102:
- `python3 -m json.tool reports/chains.json` (read_only=True, network=False, requires_credentials=False, cwd_scope=run)

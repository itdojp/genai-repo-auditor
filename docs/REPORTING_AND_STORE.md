# Reporting, SARIF, Dashboard, and SQLite Store

Validate reports:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Generate local dashboard:

```bash
gra-dashboard --run runs/OWNER__REPO/RUN_ID
open runs/OWNER__REPO/RUN_ID/reports/dashboard.html
```

Generate SARIF:

```bash
gra-sarif --run runs/OWNER__REPO/RUN_ID
```

Import to SQLite:

```bash
gra-store --run runs/OWNER__REPO/RUN_ID
sqlite3 runs/security-audit.sqlite '.tables'
```

The SQLite store is intended for local tracking across many runs. It records:

- runs
- targets
- findings
- scanner results
- created issues

GitHub Issue creation remains a separate, explicit step after human review.

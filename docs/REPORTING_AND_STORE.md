# Reporting, SARIF, Dashboard, and SQLite Store

Validate reports:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Each `gra-audit` run writes `run-manifest.json` at the run root. The manifest
contains bounded provenance metadata such as auditor version, command mode,
repository ref, network setting, schema filenames, and generated artifact paths.
It does not contain environment variables, credentials, raw scanner contents, or
full finding evidence. Paths in the manifest are run-relative; the artifact list
intentionally omits `run-manifest.json` itself to avoid unstable self-referential
size metadata. Treat it as support metadata; it is not a substitute for human
review of `reports/findings.json`, issue drafts, or scanner leads.

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

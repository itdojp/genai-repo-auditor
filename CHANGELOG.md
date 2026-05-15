# Changelog

## v0.1.0

Initial public import candidate.

- Renamed the project to GenAI Repo Auditor.
- Adopted vendor-neutral `gra-*` command names.
- Added local-first defensive repository audit workflow.
- Added staged workflow: `prepare -> recon -> targets -> research -> validation -> variant analysis -> scanner triage -> reporting -> issue creation`.
- Added target queue support with `reports/targets.json` and `templates/reports/targets.schema.json`.
- Added scanner result ingestion and AI-assisted scanner triage prompts.
- Added variant analysis prompts in exec and `/goal` modes.
- Added local dashboard, SARIF conversion, and SQLite store.
- Added public OSS metadata: README, Apache-2.0 license, SECURITY.md, CONTRIBUTING.md, TRADEMARKS.md, CODEOWNERS, issue templates, and lint workflow.
- Preserved defensive-only policy: no exploit generation, no external DAST by default, no production probing, and no autonomous remediation.

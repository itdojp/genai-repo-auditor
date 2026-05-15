# GenAI Repo Auditor Manifest

## Core commands

```text
bin/gra-audit
bin/gra-batch
bin/gra-index
bin/gra-issues
bin/gra-validate-report
```

## Staged agentic workflow commands

```text
bin/gra-recon
bin/gra-targets
bin/gra-research
bin/gra-variant
bin/gra-ingest
bin/gra-scanner-triage
bin/gra-dashboard
bin/gra-sarif
bin/gra-store
```

## Prompts

```text
prompts/AGENTS.audit.md
prompts/codex/bootstrap-import.goal.md
prompts/codex/first-quality-pass.goal.md
prompts/exec/full-audit.prompt.md
prompts/exec/recon.prompt.md
prompts/exec/generate-targets.prompt.md
prompts/exec/research-target.prompt.md
prompts/exec/variant-analysis.prompt.md
prompts/exec/scanner-triage.prompt.md
prompts/exec/validate-findings.prompt.md
prompts/goal/full-audit.goal.md
prompts/goal/research-target.goal.md
prompts/goal/variant-analysis.goal.md
prompts/goal/deep-dive-category.goal.md
prompts/goal/deep-dive-finding.goal.md
prompts/goal/validate-findings.goal.md
prompts/issue/issue-policy.md
```

## Schemas and templates

```text
templates/reports/findings.schema.json
templates/reports/targets.schema.json
templates/reports/scanner-index.schema.json
templates/reports/AUDIT_SUMMARY.md
templates/reports/FINDINGS.md
templates/reports/ISSUE_BODY.md
```

## Documentation

```text
README.md
AGENTS.md
SECURITY.md
CONTRIBUTING.md
TRADEMARKS.md
docs/GITHUB_BOOTSTRAP.md
docs/LOCAL_INSTALL_AND_AUDIT.md
docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md
docs/CODEX_WORK_INSTRUCTIONS.md
docs/ja/CODEX_WORK_INSTRUCTIONS.ja.md
docs/STAGED_AGENTIC_WORKFLOW.md
docs/TARGET_QUEUE.md
docs/VARIANT_ANALYSIS.md
docs/SCANNER_INTEGRATION.md
docs/REPORTING_AND_STORE.md
docs/WORKFLOWS.md
docs/NORMAL_OPERATION.md
docs/NORMAL_WORKFLOW.md
docs/GOAL_DEEP_DIVE.md
docs/GOAL_DEEP_DIVE_WORKFLOW.md
docs/GOAL_PROMPT_LIBRARY.md
docs/ARCHITECTURE.md
docs/USAGE.md
docs/MULTI_REPO.md
docs/SECURITY_MODEL.md
docs/REPORT_CONTRACT.md
docs/ISSUE_WORKFLOW.md
```

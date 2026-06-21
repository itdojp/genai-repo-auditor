# GenAI Repo Auditor Manifest

This manifest lists repository-owned commands, prompts, schemas/templates,
agent worker profiles, taxonomies, and public documentation surfaces that should
be kept in sync with workflow changes.

## Commands

```text
bin/gra-adversarial-validate
bin/gra-agent-check
bin/gra-audit
bin/gra-batch
bin/gra-benchmark
bin/gra-chains
bin/gra-dashboard
bin/gra-evidence-graph
bin/gra-gapfill
bin/gra-index
bin/gra-import-findings
bin/gra-ingest
bin/gra-issues
bin/gra-metrics
bin/gra-novelty
bin/gra-proofs
bin/gra-recon
bin/gra-remediate
bin/gra-research
bin/gra-run-state
bin/gra-sandbox-check
bin/gra-sarif
bin/gra-scanner-triage
bin/gra-store
bin/gra-targets
bin/gra-taxonomy-preflight
bin/gra-trace
bin/gra-validate-report
bin/gra-variant
bin/gra-worktree-check
```

## Prompts

```text
prompts/AGENTS.audit.md
prompts/codex/bootstrap-import.goal.md
prompts/codex/first-quality-pass.goal.md
prompts/exec/adversarial-validate.prompt.md
prompts/exec/full-audit.prompt.md
prompts/exec/gapfill-target.prompt.md
prompts/exec/generate-targets.prompt.md
prompts/exec/recon.prompt.md
prompts/exec/remediate.prompt.md
prompts/exec/research-target.prompt.md
prompts/exec/safe-proof.prompt.md
prompts/exec/scanner-triage.prompt.md
prompts/exec/synthesize-chains.prompt.md
prompts/exec/trace-reachability.prompt.md
prompts/exec/validate-findings.prompt.md
prompts/exec/variant-analysis.prompt.md
prompts/goal/adversarial-validate.goal.md
prompts/goal/deep-dive-category.goal.md
prompts/goal/deep-dive-finding.goal.md
prompts/goal/full-audit.goal.md
prompts/goal/gapfill-target.goal.md
prompts/goal/research-target.goal.md
prompts/goal/remediate.goal.md
prompts/goal/safe-proof.goal.md
prompts/goal/synthesize-chains.goal.md
prompts/goal/trace-reachability.goal.md
prompts/goal/validate-findings.goal.md
prompts/goal/variant-analysis.goal.md
prompts/issue/issue-policy.md
```

## Report schemas and templates

```text
templates/reports/AUDIT_SUMMARY.md
templates/reports/FINDINGS.md
templates/reports/ISSUE_BODY.md
templates/reports/benchmark.schema.json
templates/reports/chains.schema.json
templates/reports/command-event.schema.json
templates/reports/dependencies.schema.json
templates/reports/duplicate-decision.schema.json
templates/reports/evidence-graph.schema.json
templates/reports/imported-findings.schema.json
templates/reports/findings.schema.json
templates/reports/issue-ledger.schema.json
templates/reports/metrics.schema.json
templates/reports/novelty.schema.json
templates/reports/patch-validation.schema.json
templates/reports/proofs.schema.json
templates/reports/remediation-candidates.schema.json
templates/reports/run-manifest.schema.json
templates/reports/run-state.schema.json
templates/reports/scanner-index.schema.json
templates/reports/targets.schema.json
templates/reports/traces.schema.json
templates/reports/validation.schema.json
```

## Agent worker profiles

```text
templates/agent-workers/claude-code.json.example
templates/agent-workers/codex-cli.json
templates/agent-workers/generic-cli.json.example
```

## Taxonomies

```text
templates/taxonomy-aliases.json
templates/taxonomies/cwe-subset.json
templates/taxonomies/mcp-security.json
templates/taxonomies/owasp-ai-agent.json
templates/taxonomies/owasp-llm-2025.json
templates/taxonomies/supply-chain.json
```

## Documentation

```text
AGENTS.md
CHANGELOG.md
CODE_OF_CONDUCT.md
CONTRIBUTING.md
MANIFEST.md
README.md
SECURITY.md
TRADEMARKS.md
docs/ADVERSARIAL_FIXTURES.md
docs/ADVERSARIAL_VALIDATION.md
docs/ADVANCED_WORKFLOW_DECISION_TABLE.md
docs/AGENT_SURFACE_DISCOVERY.md
docs/AGENT_WORKERS.md
docs/ARCHITECTURE.md
docs/ATTACK_CHAINS.md
docs/BENCHMARKING.md
docs/CODEX_WORK_INSTRUCTIONS.md
docs/COMMAND_REFERENCE.md
docs/CUSTOMER_AUDIT_RUNBOOK.md
docs/DEPENDENCY_INGESTION.md
docs/DISCLOSURE_AND_PUBLICATION_POLICY.md
docs/EVIDENCE_GRAPH.md
docs/EXTERNAL_FINDING_IMPORT.md
docs/GITHUB_BOOTSTRAP.md
docs/GOAL_DEEP_DIVE.md
docs/GOAL_DEEP_DIVE_WORKFLOW.md
docs/GOAL_PROMPT_LIBRARY.md
docs/ISSUE_WORKFLOW.md
docs/LOCAL_ARTIFACT_CLEANUP.md
docs/LOCAL_INSTALL_AND_AUDIT.md
docs/METRICS.md
docs/MULTI_REPO.md
docs/NORMAL_OPERATION.md
docs/NORMAL_WORKFLOW.md
docs/NOVELTY_LEDGER.md
docs/OPERATING_MODEL.md
docs/PROVENANCE_POSTURE.md
docs/RELEASE_PROCESS.md
docs/REMEDIATION_CANDIDATES.md
docs/REMEDIATION_WORKFLOW.md
docs/REPORTING_AND_STORE.md
docs/REPORT_CONTRACT.md
docs/SAFE_LOCAL_PROOFS.md
docs/SANDBOX_PROFILES.md
docs/SCANNER_INTEGRATION.md
docs/SCORECARD_INGESTION.md
docs/SECURITY_MODEL.md
docs/STAGED_AGENTIC_WORKFLOW.md
docs/TARGET_QUEUE.md
docs/TAXONOMIES.md
docs/TRACE_REACHABILITY.md
docs/USAGE.md
docs/VARIANT_ANALYSIS.md
docs/WORKFLOWS.md
docs/WORKFLOW_OVERVIEW.md
docs/WORKTREE_SEPARATION.md
docs/ja/ADVANCED_POSTURE_WORKFLOWS.ja.md
docs/ja/CODEX_WORK_INSTRUCTIONS.ja.md
docs/ja/ISSUE_WORKFLOW.ja.md
docs/ja/LOCAL_INSTALL_AND_AUDIT.ja.md
docs/ja/README.md
docs/ja/SCANNER_INTEGRATION.ja.md
docs/ja/SECURITY_MODEL.ja.md
docs/ja/USAGE.ja.md
```

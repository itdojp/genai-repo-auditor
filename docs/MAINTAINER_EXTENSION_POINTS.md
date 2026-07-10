# Maintainer Extension Points

This guide documents the supported extension points for maintainers who add report validators, publication rules, or GitHub publication behavior. The project remains local-first and defensive-only; new extension points must preserve existing CLI and report contracts unless a migration is explicitly planned.

## Integration test layout

Shared integration test fixtures and command mocks live in [`tests/integration/support.py`](../tests/integration/support.py). Feature suites are split by workflow area so maintainers can run a narrow suite while preserving full discovery coverage:

| Area | Test module | Typical scope |
| --- | --- | --- |
| Audit, target queue, research | [`tests/integration/test_audit_research_workflows.py`](../tests/integration/test_audit_research_workflows.py) | `gra-audit`, `gra-recon`, `gra-targets`, `gra-research`, gapfill, variants |
| Batch | [`tests/integration/test_batch_workflows.py`](../tests/integration/test_batch_workflows.py) | `gra-batch` aggregation and failure modes |
| Metrics and evidence reporting | [`tests/integration/test_metrics_workflows.py`](../tests/integration/test_metrics_workflows.py) | `gra-metrics`, `gra-benchmark`, `gra-evidence-graph` |
| Publication | [`tests/integration/test_publication_workflows.py`](../tests/integration/test_publication_workflows.py) | `gra-issues`, issue ledger, publication-plan safety |
| Remediation and validation agents | [`tests/integration/test_remediation_workflows.py`](../tests/integration/test_remediation_workflows.py) | adversarial validation, chains, proofs, remediation candidates |
| Scanner/store/import | [`tests/integration/test_scanner_store_workflows.py`](../tests/integration/test_scanner_store_workflows.py) | scanner ingestion, SQLite store, external finding import |
| Report validation | [`tests/integration/test_validation_workflows.py`](../tests/integration/test_validation_workflows.py) | `gra-validate-report` contract and safety checks |
| Worker profile and trace | [`tests/integration/test_worker_profile_workflows.py`](../tests/integration/test_worker_profile_workflows.py) | run state, no-findings, trace reachability, workflow profile |

The legacy module [`tests/integration/test_cli_workflows.py`](../tests/integration/test_cli_workflows.py) is now a compatibility aggregator. Direct runs still load every feature suite:

```bash
python3 -m unittest tests.integration.test_cli_workflows
```

During `unittest discover`, the aggregator returns an empty suite to avoid duplicate execution. Use either full discovery or a feature module during development:

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.integration.test_publication_workflows -v
python3 -m unittest tests.integration.test_validation_workflows -v
```

When adding integration coverage:

1. Put reusable fixtures, mock command writers, and assertion helpers in `support.py` only when at least two feature modules need them.
2. Put workflow-specific assertions in the feature module that owns the workflow.
3. Keep generated run directories under `.test-tmp/` through `CliWorkflowTestCase.setUp()`.
4. Do not commit generated runs, target repositories, scanner outputs, transcripts, credentials, or local audit artifacts.

## Packaging and resource discovery

Package metadata is declared in [`pyproject.toml`](../pyproject.toml), with
source files under [`src/genai_repo_auditor/`](../src/genai_repo_auditor/).
The package intentionally has no runtime third-party dependencies. The
declared build backend installs all public `gra-*` console scripts and packages
the legacy `bin/` command surface, `lib/` helper modules, prompt families, and
template resource families under `share/genai-repo-auditor/` so installed code
can locate them without relying on a source checkout.

Use the canonical resource API for new package-aware code:

```python
from genai_repo_auditor import prompt_path, report_schema_path, resource_root

root = resource_root()
prompt = prompt_path("exec", "full-audit.prompt.md")
findings_schema = report_schema_path("findings.schema.json")
```

Compatibility invariants:

- Source-checkout commands under `bin/` must continue to work while packaging
  support is introduced incrementally.
- Every current `bin/gra-*` command must have a matching `[project.scripts]`
  entry point in `pyproject.toml` and a callable in
  `genai_repo_auditor.cli.COMMANDS`.
- Packaged resources must include `VERSION`, `bin/`, `lib/`, prompts, report
  schemas/templates, taxonomies, and agent worker profiles.
- Console-script wrappers must preserve public command names in `--help` and
  `--version` output, including when executed outside the source checkout.
- Console-script wrappers that execute bundled code must ignore
  `GENAI_REPO_AUDITOR_RESOURCE_ROOT` for executable helper discovery; that
  override is for data resource lookup only.
- Package builds must not include local runs, cloned repositories, scanner
  output, stores, credentials, Codex transcripts, or agent-local artifacts.

## Adding a report validator

Report validation is registry-driven. Core registry entry points are:

- [`lib/validators/registry.py`](../lib/validators/registry.py) for validator ordering and registry construction.
- [`lib/validators/context.py`](../lib/validators/context.py) for shared validation context.
- [`lib/validators/findings.py`](../lib/validators/findings.py), [`lib/validators/targets.py`](../lib/validators/targets.py), [`lib/validators/scanner.py`](../lib/validators/scanner.py), [`lib/validators/run_manifest.py`](../lib/validators/run_manifest.py), and [`lib/validators/advanced.py`](../lib/validators/advanced.py) for concrete artifact validators.
- [`bin/gra-validate-report`](../bin/gra-validate-report) for CLI orchestration and exit-code mapping.

Recommended sequence:

1. Add the validator as a small function that accepts `ValidationContext` and returns deterministic diagnostics.
2. Register it in the relevant registry factory in dependency order. Validators that depend on other artifacts must run after those artifacts are loaded or checked.
3. Add schema or contract tests in `tests/test_report_contracts.py` or focused registry tests in `tests/test_validator_registry.py`.
4. Add an integration test to `tests/integration/test_validation_workflows.py` only when CLI wiring, artifact discovery, or safety boundaries are involved.
5. Run the narrow suite first, then full discovery.

Compatibility invariants:

- Missing or malformed required artifacts must fail closed with controlled diagnostics.
- Validators must not follow symlinks out of the run directory.
- Validators must not copy raw secret values, full issue bodies, or untrusted repository content into diagnostics.
- Existing report schema versions and CLI exit semantics must remain compatible unless a migration is explicitly documented.

## Adding a publication rule

Publication selection, rendering, plan binding, ledger persistence, and GitHub operations are intentionally separated:

- [`lib/publication/policy.py`](../lib/publication/policy.py) owns severity/status filtering, labels, title normalization, visibility planning, advanced validation summaries, remediation summaries, novelty summaries, and selection reasons.
- [`lib/publication/rendering.py`](../lib/publication/rendering.py) owns safe issue-body rendering and fingerprint/body hashing helpers.
- [`lib/publication/planning.py`](../lib/publication/planning.py) owns immutable publication-plan construction and verification against current findings and issue drafts.
- [`lib/publication/plan_store.py`](../lib/publication/plan_store.py) owns plan path, JSON validation, writing, and SHA-256 binding.
- [`lib/publication/ledger.py`](../lib/publication/ledger.py) owns canonical issue-ledger snapshots and duplicate-decision persistence.
- [`lib/publication/github.py`](../lib/publication/github.py) owns the injectable `GitHubClient` boundary and `gh` CLI implementation.
- [`bin/gra-issues`](../bin/gra-issues) should remain CLI orchestration: argument parsing, mode selection, guard enforcement, and exit-code handling.

Recommended sequence:

1. Add pure policy or rendering behavior before changing CLI orchestration.
2. Add focused tests in `tests/test_publication_modules.py` or `tests/test_publication_state.py` for pure selection, plan, ledger, duplicate, or GitHub-client behavior.
3. Add integration coverage in `tests/integration/test_publication_workflows.py` when the rule affects dry-run, plan, apply-plan, duplicate suppression, public-repository guards, or ledger verification.
4. Preserve `gra-issues --dry-run` and `--plan` as non-publishing paths. Mocked or injected clients must prove no GitHub mutation occurs in preview or plan-verification modes.

Compatibility invariants:

- Public repository publication remains denied unless `--allow-public` is explicit.
- `--apply-plan` must bind to the reviewed issue body, fingerprint, advanced-validation state, novelty state, and plan SHA-256.
- Duplicate suppression must remain idempotent through both GitHub fingerprint search and the issue ledger.
- Temporary issue-body files must be scoped to the run directory and cleaned up; `GhCliClient.create_issue()` is fail-closed when no `body_tmp_dir` is supplied.
- Publication plans and issue ledgers must not embed raw issue bodies, raw evidence, full secrets, or untrusted target content.

## Validation before opening a PR

For validator or publication extension work, run the narrow suite plus the required broad checks:

```bash
python3 -m unittest tests.integration.test_validation_workflows -v
python3 -m unittest tests.integration.test_publication_workflows -v
python3 -m unittest discover -s tests
scripts/validate-shellcheck.sh
scripts/validate-install-smoke.sh
git diff --check
```

If the change touches release packaging or install behavior, also run:

```bash
python3 scripts/build_release.py --dry-run
```

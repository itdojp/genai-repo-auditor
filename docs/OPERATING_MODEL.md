# Operating model

This document defines the operator model for running GenAI Repo Auditor as an
internal or managed audit workflow. It is operational guidance only; it does not
add new detection capability.

## Scenario matrix

| Scenario | Typical owner | Repository visibility | Publication default | Required approval |
|---|---|---|---|---|
| Internal audit | Product/AppSec team | Private or internal | Internal tracker or private GitHub Issues | Repository owner or delegated AppSec approver |
| Customer audit | Service operator and customer contact | Customer-provided private/internal repository | Customer handoff first; no public Issue by default | Written customer authorization and disclosure contact |
| OSS public repository | Maintainer or approved security reporter | Public repository | Private disclosure first when security impact is plausible | Maintainer/security policy approval before any public Issue |

All scenarios are local-first. Generated runs, cloned target repositories,
scanner outputs, transcripts, dashboards, SARIF files, SQLite stores, issue
plans, proof artifacts, trace artifacts, and draft remediation patches are local
operator artifacts unless a human explicitly approves sharing.

## Roles and responsibilities

- **Request owner** confirms scope, authorization, target repository, branch,
  commit, and disclosure constraints.
- **Audit operator** runs the tool, keeps artifacts local, records validation
  evidence, and prepares handoff material.
- **Security reviewer** approves finding severity, reachability, proof limits,
  adversarial validation outcomes, and Issue/publication wording.
- **Repository owner or customer contact** approves remediation routing and any
  Issue, PR, advisory, or public disclosure action.
- **Release owner** confirms that documentation, report contracts, and local
  artifacts are excluded from release assets. See [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).

One person can hold multiple roles in a small project, but the Issue creation
approval step must still be explicit and recorded outside the generated audit
artifacts.

## Authorization checklist

Before cloning or auditing a repository, record answers to these questions in the
operator's approved tracking system:

```text
- Who requested the audit?
- Which repository, branch, and commit are in scope?
- Is the repository private, internal, or public?
- Is the audit internal, customer-facing, or OSS/public?
- Are third-party dependencies, submodules, generated code, or vendored code in scope?
- Is network access allowed? Default: no.
- Are scanner imports allowed? Which tools and versions?
- Are safe local proof artifacts allowed?
- Are remediation candidates allowed?
- Are GitHub Issues allowed? Private only or public with additional approval?
- Who approves customer handoff and disclosure wording?
- What retention period applies to local artifacts?
```

If authorization is incomplete, stop before running `gra-audit`.

## Data classification

Treat the following as sensitive by default:

- target repository source code and metadata;
- `runs/OWNER__REPO/RUN_ID/` contents;
- `reports/findings.json`, issue drafts, publication plans, validation reports,
  chain synthesis, proof artifacts, trace artifacts, remediation candidates, and
  imported external findings;
- raw scanner outputs and normalized scanner leads;
- Codex event streams, transcripts, stderr, and final messages;
- dashboards, SARIF, SQLite stores, benchmark outputs, and metrics.

Do not publish or paste raw evidence, issue body drafts, proof payloads, chain
summaries, trace results, scanner lead bodies, secret values, tokens, cookies,
private keys, credentials, customer names, or private repository details unless
an approved disclosure process explicitly permits the exact content.

## Standard local setup

Use a dedicated workspace and keep runs under the repository root or an approved
local workspace. Do not place scratch clones or run artifacts under `/tmp`.

```bash
git clone https://github.com/itdojp/genai-repo-auditor.git genai-repo-auditor
cd genai-repo-auditor
python3 -m unittest tests.test_docs_consistency -v
scripts/validate-install-smoke.sh
```

For cleanup and retention, follow [`LOCAL_ARTIFACT_CLEANUP.md`](LOCAL_ARTIFACT_CLEANUP.md).

## Normal workflow sequence

Use this path for a small internal or customer-approved audit where target scope
is already known.

```bash
gra-audit --repo OWNER/REPO --mode prepare --model gpt-5.5 --effort xhigh
gra-recon --run runs/OWNER__REPO/RUN_ID --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --generate --model gpt-5.5 --effort xhigh
gra-targets --run runs/OWNER__REPO/RUN_ID --list
gra-research --run runs/OWNER__REPO/RUN_ID --target TGT-001 --model gpt-5.5 --effort xhigh
gra-validate-report --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
```

Review `reports/findings.json`, `reports/FINDINGS.md`, issue drafts, and the
dashboard locally. Do not create Issues during the audit run.

## Staged workflow sequence

Use this path when the audit needs coverage tracking, validation gates, or
handoff evidence.

```bash
gra-gapfill --run runs/OWNER__REPO/RUN_ID --generate
gra-gapfill --run runs/OWNER__REPO/RUN_ID --target TGT-GAPFILL-001 --mode exec
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-taxonomy-preflight --run runs/OWNER__REPO/RUN_ID --fix
gra-metrics --run runs/OWNER__REPO/RUN_ID
gra-benchmark --run runs/OWNER__REPO/RUN_ID
gra-evidence-graph --run runs/OWNER__REPO/RUN_ID
gra-dashboard --run runs/OWNER__REPO/RUN_ID
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Use [`STAGED_AGENTIC_WORKFLOW.md`](STAGED_AGENTIC_WORKFLOW.md) for detailed stage
behavior and [`ADVANCED_WORKFLOW_DECISION_TABLE.md`](ADVANCED_WORKFLOW_DECISION_TABLE.md)
for when to require each advanced stage.

## Advanced validation before Issue creation

For selected Critical/High findings, prefer the immutable publication plan and
advanced validation gate:

```bash
gra-chains --run runs/OWNER__REPO/RUN_ID
gra-proofs --run runs/OWNER__REPO/RUN_ID --all-critical-high
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --mode goal
gra-remediate --run runs/OWNER__REPO/RUN_ID --all-critical-high --validate --sandbox-profile local-test --build-command "python3 -m py_compile repo/app.py" --test-command "python3 -m py_compile repo/app.py"
gra-adversarial-validate --run runs/OWNER__REPO/RUN_ID --all-critical-high --votes 3 --policy human-review-on-split
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

Replace `repo/app.py` with project-specific safe local Python commands. If no
safe local command exists, leave patch validation as `needs-human-review` rather
than claiming validation.

## Publication guardrails

Issue creation is always a separate human-approved step. Review the exact issue
body hashes from the publication plan before applying it:

```bash
gra-issues --run runs/OWNER__REPO/RUN_ID --plan --require-advanced-validation
gra-issues \
  --run runs/OWNER__REPO/RUN_ID \
  --apply-plan runs/OWNER__REPO/RUN_ID/reports/issue-publication-plan.json \
  --create-labels
```

For public repositories, public Issue creation is blocked by default. Use
`--allow-public` only when policy permits, the repository owner or disclosure
contact has approved public wording, and the operator has confirmed that the
Issue body contains no secrets, private evidence, exploit payloads, or customer
information. See [`DISCLOSURE_AND_PUBLICATION_POLICY.md`](DISCLOSURE_AND_PUBLICATION_POLICY.md).

## Pause, handoff, and retention

Use run state when work stops for maintainer updates, customer review, or a
release window:

```bash
gra-run-state --run runs/OWNER__REPO/RUN_ID --pause \
  --reason "customer review window" \
  --resume-target TGT-001 \
  --resume-condition "customer approves next validation pass" \
  --final-reconcile "no public Issue created; local handoff prepared"
gra-run-state --run runs/OWNER__REPO/RUN_ID --status
```

At handoff or closure:

1. Export only the approved summary format.
2. Confirm no local-only artifacts are attached to public Issues.
3. Run cleanup dry-run and get approval for deletion.
4. Apply cleanup after the retention window.

```bash
python3 scripts/clean-local-artifacts.py
python3 scripts/clean-local-artifacts.py --apply
```

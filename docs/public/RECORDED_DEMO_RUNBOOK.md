# Recorded demo runbook

## Purpose

Record an 8-12 minute public-safe demo of GenAI Repo Auditor using only:

- merged public documentation;
- the public synthetic efficacy corpus; and
- the repository-owned minimal fixture copied by `gra-benchmark --fixture minimal`.

This runbook is for recording only. It does not authorize external posting,
external upload, or GitHub write actions. Any external publication decision is
human-only and must pass the review checklist in
[`DEMO_PUBLICATION_REVIEW.md`](DEMO_PUBLICATION_REVIEW.md).

## Source boundary

Narration and on-screen claims must stay within these merged public documents:

- [`../dogfood/DEMO_SCRIPT.md`](../dogfood/DEMO_SCRIPT.md)
- [`../dogfood/PUBLIC_LAUNCH_CHECKLIST.md`](../dogfood/PUBLIC_LAUNCH_CHECKLIST.md)
- [`../dogfood/PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`](../dogfood/PUBLIC_SELF_DOGFOOD_CASE_STUDY.md)
- [`../dogfood/PUBLIC_ITDO_ERP4_CASE_STUDY.md`](../dogfood/PUBLIC_ITDO_ERP4_CASE_STUDY.md)
- [`../dogfood/README_POSITIONING_NOTES.md`](../dogfood/README_POSITIONING_NOTES.md)
- [`../evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md`](../evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md)
- [`../evaluation/EVALUATION_REPRODUCTION.md`](../evaluation/EVALUATION_REPRODUCTION.md)
- [`../evaluation/CLAIM_EVIDENCE_MATRIX.md`](../evaluation/CLAIM_EVIDENCE_MATRIX.md)
- [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)
- [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md)
- [`../LOCAL_INSTALL_AND_AUDIT.md`](../LOCAL_INSTALL_AND_AUDIT.md)
- [`../../SECURITY.md`](../../SECURITY.md)

Do not add claims from private notes, local artifacts, unpublished issue drafts,
or live target-repository output.

## Non-goals

The recording must not show or imply:

- private findings or target-specific findings;
- target code, target paths, or raw scanner output;
- prompts, transcripts, proof artifacts, chain artifacts, remediation artifacts,
  or issue draft bodies;
- credentials, token names, shell history, local absolute paths, or run IDs;
- model-superiority, scanner-superiority, or production-performance claims;
- external posting, upload, tracker mutation, or GitHub write behavior.

## Operator setup before recording

1. Record from a clean repository checkout of the merged branch.
2. Use a terminal crop or window layout that hides:
   - shell prompt with username or hostname;
   - current working directory;
   - browser profile indicators;
   - notification popups;
   - clipboard managers and password tools.
3. Keep microphone notes separate from the terminal.
4. Prepare a local scratch directory inside the repository, for example
   `.demo-public/`.
5. Do not enable `gra-doctor --probe-external-tools` on camera.
6. Do not run `gh auth status`, `gra-audit --mode exec`, `gra-run --execute`,
   scanner execution, `gra-issues --plan`, `gra-issues --apply`, or any upload
   workflow.
7. This is a merged-source-checkout demo, not an installation demo. Complete
   the packaged installation smoke test separately before recording; do not
   imply that running `bin/gra-*` validates a published package.

## Demo structure

| Segment | Target time | Demo material |
|---|---:|---|
| Safety frame | 1 min | README positioning and disclosure boundary |
| Local readiness | 1 min | `gra-doctor` redacted summary only |
| Public synthetic benchmark | 3 min | deterministic corpus summary and fixed comparison |
| Repository-owned minimal fixture | 2 min | local benchmark summary |
| Declarative workflow control | 1-2 min | sanitized `gra-run` plan plus documented execute/resume boundary |
| Publication control | 1-2 min | `gra-issues --dry-run` executed off-screen, counts shown from a sanitized summary |
| Close | 1 min | public-safe boundary, human review, human-only publication |

## Recording commands

Run all commands from the repository root.

### 1. Create a local demo workspace

```bash
test "$(git rev-parse --show-toplevel)" = "$PWD" || {
  printf '%s\n' 'Run this demo only from the repository root.' >&2
  exit 1
}
DEMO_DIR=.demo-public
rm -rf -- "$DEMO_DIR"
mkdir -p -- "$DEMO_DIR"
trap 'rm -rf -- "$DEMO_DIR"' EXIT
```

This ignored directory stays local and is not publication material. Keep the
same shell session open so that the exit trap removes it. After recording,
confirm that `.demo-public/` no longer exists; if the shell terminated before
the trap was installed, return to the repository root and remove it manually.

### 2. Show the local-first boundary and supported wording

Recommended on-screen files:

- `README.md`
- `docs/dogfood/README_POSITIONING_NOTES.md`
- `docs/evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md`

Narration points that stay within the merged public wording:

- GenAI Repo Auditor is a local-first, vendor-neutral AppSec audit harness.
- Public evidence is limited to deterministic synthetic results and reviewed
  aggregate documentation.
- Human review remains required before any publication action.

### 3. Run `gra-doctor` and show only a sanitized summary

Generate the JSON output locally:

```bash
bin/gra-doctor --json --runs-dir .demo-public/runs > .demo-public/gra-doctor.json
```

Show only selected status fields:

```bash
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('.demo-public/gra-doctor.json').read_text())
checks = report['checks']
print('overall_status:', report['overall_status'])
print('external_tool_probes_enabled:', report['external_tool_probes_enabled'])
for key in ('python', 'git', 'gh', 'worker', 'run_directory', 'packaged_resources'):
    print(f'{key}:', checks[key]['status'])
PY
```

Do not show the raw JSON file on screen. The full output includes local
environment details that are not needed for a public recording.

An `overall_status` of `warning` is acceptable for this offline recording only
when the operator has reviewed the raw report off camera and confirmed that
every warning belongs to an unused optional integration, such as GitHub account
readiness. An unexplained warning is a stop condition; do not describe it as a
successful readiness check.

### 4. Run the public synthetic benchmark

Generate the public synthetic report:

```bash
bin/gra-efficacy-benchmark \
  --out-json .demo-public/public-benchmark.json \
  --out-md .demo-public/public-benchmark.md \
  >/dev/null
```

Show only the aggregate summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('.demo-public/public-benchmark.json').read_text())
counts = report['scores']['counts']
rates = report['scores']['rates']
print('mode:', report['mode'])
print('corpus:', report['corpus']['corpus_id'])
print('suite:', report['corpus']['selection']['suite'])
print('selected_cases:', report['execution']['selected_case_count'])
print('tp_fp_fn_tn:', counts['true_positives'], counts['false_positives'], counts['false_negatives'], counts['true_negatives'])
print('precision_recall_f1:', rates['precision'], rates['recall'], rates['f1'])
print('network_github_model:', report['safety']['network_accessed'], report['safety']['github_accessed'], report['safety']['model_channel_used'])
print('issue_publication_performed:', report['safety']['issue_publication_performed'])
PY
```

Optional comparison segment:

```bash
bin/gra-efficacy-benchmark \
  --compare \
  --out-json .demo-public/public-comparison.json \
  --out-md .demo-public/public-comparison.md \
  >/dev/null
```

```bash
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('.demo-public/public-comparison.json').read_text())
rows = {row['configuration_id']: row for row in report['configurations']}
for config_id in ('reference-review-all-signals-v1', 'reference-review-high-severity-gate-v1'):
    row = rows[config_id]
    counts = row['scores']['counts']
    print(config_id)
    print('  stages:', ', '.join(row['workflow_stage_ids']))
    print('  tp_fp_fn_tn:', counts['true_positives'], counts['false_positives'], counts['false_negatives'], counts['true_negatives'])
print('claim_guardrails:', report['claim_guardrails'])
PY
```

Narrate the limit explicitly: these are deterministic synthetic results for the
named corpus and configuration only. They are not production performance claims.

### 5. Run the repository-owned minimal fixture benchmark

Create the tiny local fixture run:

```bash
bin/gra-benchmark --fixture minimal --out-run .demo-public/minimal-run >/dev/null
```

Show only a bounded summary:

```bash
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('.demo-public/minimal-run/reports/benchmark.json').read_text())
summary = report['summary']
metrics = report['metrics']['summary']
print('overall_status:', summary['overall_status'])
print('gates_passed_warning_failed:', summary['passed'], summary['warnings'], summary['failed'])
print('findings_total:', metrics['findings_total'])
print('issue_recommended_findings:', metrics['issue_recommended_findings'])
print('adversarial_validation_total:', metrics['adversarial_validation_total'])
print('chain_count:', metrics['chain_count'])
print('proof_count:', metrics['proof_count'])
print('issue_plan_warning_count:', metrics['issue_plan_warning_count'])
print('workflow_skipped_by_scope_count:', metrics['workflow_skipped_by_scope_count'])
PY
```

Do not open `reports/findings.json`, `reports/issue-drafts/`, or any other raw
fixture artifact during the recording.

### 6. Show the declarative `gra-run` control boundary

Add a repository-owned inert input to the copied fixture, then generate a plan
without executing it:

```bash
mkdir -p -- "$DEMO_DIR/minimal-run/repo"
cat > "$DEMO_DIR/minimal-run/repo/README.md" <<'EOF'
# Public demo fixture

Repository-owned inert input for a workflow-planning demonstration.
EOF
bin/gra-run \
  --run "$DEMO_DIR/minimal-run" \
  --profile recon-only \
  --json > "$DEMO_DIR/workflow-plan.json"
```

Show only plan metadata and the fail-closed safety fields:

```bash
python3 - <<'PY'
import json
from pathlib import Path
plan = json.loads(Path('.demo-public/workflow-plan.json').read_text())
print('mode:', plan['mode'])
print('profile:', plan['profile'])
print('stage_count:', plan['summary']['stage_count'])
print('commands_executed:', plan['safety']['commands_executed'])
print('network_allowed:', plan['safety']['network_allowed'])
print('github_mutation_allowed:', plan['safety']['github_mutation_allowed'])
for stage in plan['stages']:
    print('stage:', stage['id'], stage['status'], stage['mutation'])
PY
```

Use
[`STAGED_AGENTIC_WORKFLOW.md`](../STAGED_AGENTIC_WORKFLOW.md#declarative-workflow-execution-and-checkpoints)
to explain the reviewed `--execute` and same-profile `--resume` path, and the
[second dogfood aggregate](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md#executed-workflow)
as public evidence of one checkpoint resume. Do not execute either mode during
this recording: execution can produce model-backed or target-derived local
artifacts, whereas this public-safe segment demonstrates the plan/review gate.
A plan does not validate findings or authorize publication.

### 7. Run `gra-issues --dry-run` off-screen and show counts only

The merged public docs already state that dry-run output can contain preview
metadata that is unsuitable for public display. Keep the command output out of
frame and redirect it to a local file:

```bash
bin/gra-issues --run .demo-public/minimal-run --dry-run > .demo-public/private-dry-run.log
```

Show only a sanitized count summary derived from the generated preview files:

```bash
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('.demo-public/minimal-run/issues-created.json').read_text())
ledger = json.loads(Path('.demo-public/minimal-run/reports/issue-ledger.json').read_text())
print('dry_run:', report['dry_run'])
print('preview_only:', report['preview_only'])
print('publication_plan_status:', report['publication_plan_status'])
print('created_count:', len(report['created']))
print('skipped_count:', len(report['skipped']))
print('ledger_warning_count:', len(ledger['warnings']))
PY
```

Do not show the terminal log, issue draft files, ledger body hashes, preview
plan paths, fingerprints, or titles.

### 8. Close with the publication boundary

Close on these public-safe points:

- synthetic benchmark output is deterministic and bounded;
- the repository-owned tiny fixture demonstrates local reporting mechanics only;
- issue publication remains an explicit, human-reviewed gate;
- external posting, upload, and GitHub write are outside this runbook and are
  human-only decisions.

## Redaction rules during editing

Apply these rules before exporting the recording:

- crop out terminal chrome that reveals usernames, hostnames, tabs, or local
  paths;
- mute or trim any spoken reference to a local file path, run ID, or hidden
  artifact name;
- blur or cut any frame that reveals credential prompts, browser profile names,
  notification contents, or clipboard previews;
- remove any frame that exposes issue draft text, hashes, fingerprints, or raw
  dry-run output.

## Stop conditions

Stop recording immediately if any of the following appears on screen or in
narration:

- a local absolute path, run ID, username, hostname, or credential indicator;
- target-specific finding text, code, path, fingerprint, or issue title;
- raw scanner output, prompt content, transcript content, proof content, chain
  content, or remediation detail;
- an external upload dialog, browser share flow, GitHub write flow, or tracker
  mutation step;
- a claim that is not supported by the merged public documents listed above.

If a stop condition occurs, discard that take, clear the local scratch output,
and restart from the previous safe segment.

Before closing the recording session, exit the demo shell and confirm that the
exit trap removed `.demo-public/`. Do not stage or retain any demo scratch file.

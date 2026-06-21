# Public demo script for GenAI Repo Auditor dogfood materials

This demo script is for public or semi-public walkthroughs of the dogfood
campaign. It is designed to demonstrate the harness safely without exposing local
run artifacts, target findings, scanner records, credentials, or issue body text.

## Demo goal

Show that GenAI Repo Auditor is a local-first, vendor-neutral AppSec audit
harness that helps operators organize AI-assisted review, deterministic scanner
inputs, validation, metrics, evidence graph summaries, human review, and
controlled GitHub Issue publication for authorized repositories.

## Required setup

Before a live demo:

1. Select an operator-owned or explicitly authorized repository.
2. Confirm that the demo will not access production, staging, or external hosts.
3. Create a fresh workspace and record the artifact retention decision outside
   public Git.
4. Decide whether the demo is live, recorded, or documentation-only.
5. Prepare sanitized screenshots from the public case studies if local output
   should not be shown.
6. Verify `gh auth status`, `codex --help`, and `python3 --version` privately;
   do not display account tokens or environment files.

If any setup item is unclear, use documentation-only mode.

## Recommended safe path

Use a narrative demo built from public docs and help output:

```bash
gra-audit --help
gra-targets --help
gra-validate-report --help
gra-issues --help
python3 -m unittest tests.test_docs_consistency tests.test_manifest tests.test_dogfood_templates -v
```

Then show these public files rather than local run content:

- [`PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`](PUBLIC_SELF_DOGFOOD_CASE_STUDY.md)
- [`PUBLIC_ITDO_ERP4_CASE_STUDY.md`](PUBLIC_ITDO_ERP4_CASE_STUDY.md)
- [`README_POSITIONING_NOTES.md`](README_POSITIONING_NOTES.md)
- [`PUBLIC_LAUNCH_CHECKLIST.md`](PUBLIC_LAUNCH_CHECKLIST.md)

## Optional live workflow narration

Use this only for an authorized disposable or operator-owned repository. Replace
`OWNER/REPO` before the demo and keep the run directory private.

```bash
gra-audit --repo OWNER/REPO --mode prepare --model MODEL --effort EFFORT
RUN=runs/OWNER__REPO/RUN_ID

gra-recon --run "$RUN" --model MODEL --effort EFFORT
gra-targets --run "$RUN" --generate --model MODEL --effort EFFORT
gra-targets --run "$RUN" --list

# Stop here for public demos unless a reviewer approves the selected target.
gra-validate-report --run "$RUN"
gra-metrics --run "$RUN"
gra-benchmark --run "$RUN"
gra-evidence-graph --run "$RUN"
gra-issues --run "$RUN" --dry-run
```

Narration points:

- `prepare` creates local workspace boundaries.
- `recon` and `target queue` organize the review before deep analysis.
- `validate`, `metrics`, `benchmark`, and `evidence graph` are deterministic
  checkpoints.
- `gra-issues --dry-run` previews publication status and warning counts only.
- `gra-issues --apply` is not part of a public demo.

## Five-minute demo agenda

| Time | Segment | Script |
|---:|---|---|
| 0:00 | Positioning | “This is a local-first AppSec audit harness for authorized repositories, not a managed security service.” |
| 0:45 | Workflow | Show the text workflow from `README.md` and explain local artifact handling. |
| 1:30 | Self-dogfood | Open the public self-dogfood case study and point to sanitized metrics. |
| 2:15 | ITDO_ERP4 dogfood | Open the public business-application case study and explain scope narrowing. |
| 3:00 | Safety boundary | Show disclosure policy and dry-run issue planning language. |
| 4:00 | Validation | Run or show the docs/manifest/dogfood test command. |
| 4:45 | Close | Point to setup docs and explain that target-specific security candidates use private reporting first. |

## Speaker notes

Say:

- “AI output is review input; humans approve publication.”
- “Scanner evidence is ingested only when authorized.”
- “The case studies show aggregate counts and workflow decisions, not target
  vulnerability detail.”
- “Public GitHub Issues are controlled by policy and dry-run review.”

Do not say:

- the harness replaces expert review;
- findings are automatically publishable;
- proof-oriented artifacts are public demo content;
- generated remediation is ready without target maintainer review;
- public repositories are safe to disclose into by default.

## Redaction and display rules

During the demo, do not display:

- local run directories or target clones;
- report bodies, scanner records, normalized lead bodies, dashboards, stores,
  transcripts, or issue previews;
- account names beyond what is already public and necessary;
- shell history, environment files, configuration files, tokens, cookies, or
  private keys;
- target commit hashes or local run identifiers unless a reviewer approves them.

## Stop conditions

Stop the demo if:

- a command prints local evidence or target code unexpectedly;
- a viewer asks for proof details or target-specific finding content;
- `gra-issues --dry-run` reports warnings that have not been reviewed;
- a live repository authorization or retention decision becomes unclear;
- an output would require disclosure approval before showing it publicly.

# Demo shot list

## Recording target

- Format: terminal-first recorded walkthrough
- Runtime: 8-12 minutes
- Inputs: merged public docs, public synthetic corpus, repository-owned minimal fixture
- Excluded actions: external posting, external upload, GitHub write, live target-repository audit

## Shot schedule

| Shot | Duration | Screen content | Command or file | Narration focus | Redaction note | Stop condition |
|---:|---:|---|---|---|---|---|
| 1 | 0:00-0:45 | README headline and public positioning notes | `README.md`, `docs/dogfood/README_POSITIONING_NOTES.md` | Local-first, vendor-neutral, authorized repositories, human review boundary | Hide browser profile, tab sync, local folder tree | Any unsupported marketing or model-superiority wording appears |
| 2 | 0:45-1:30 | Demo boundary and disclosure policy | `docs/dogfood/DEMO_SCRIPT.md`, `docs/DISCLOSURE_AND_PUBLICATION_POLICY.md` | Public-safe boundary, no target findings, no GitHub write in the demo | Do not scroll into non-public notes or editor sidebars | Any mention of private findings, proofs, or disclosure-sensitive detail |
| 3 | 1:30-2:15 | Local readiness summary | `bin/gra-doctor --json` followed by the sanitized Python summary | Redacted readiness check without external probes | Do not show raw JSON, local paths, or environment names | Raw doctor output or prompt line reveals path or account context |
| 4 | 2:15-4:15 | Synthetic benchmark summary | `bin/gra-efficacy-benchmark` with generator stdout redirected, then sanitized summary script | Deterministic public corpus, offline execution, bounded evidence | Show sanitized counts only; generator stdout includes local output paths | Any local path appears or narration treats the result as production recall or model superiority |
| 5 | 4:15-5:45 | Fixed comparison summary | `bin/gra-efficacy-benchmark --compare` with generator stdout redirected, then sanitized summary script | One pinned stage difference, human review still required | Keep generator output off-screen and show summary text only | Any local path appears or narration claims a configuration is broadly superior |
| 6 | 5:45-7:00 | Repository-owned tiny fixture benchmark | `bin/gra-benchmark --fixture minimal --out-run .demo-public/minimal-run` and sanitized summary script | Local report mechanics and benchmark gates without target disclosure | Do not open `findings.json`, issue drafts, or raw report directories | Any finding body, path, or draft content appears |
| 7 | 7:00-8:15 | Declarative workflow plan | `bin/gra-run --run .demo-public/minimal-run --profile recon-only --json` and sanitized plan summary | Plan/review gate, no execution; explain documented execute and same-profile resume boundary | Show only stage IDs, status, mutation class, and safety booleans | Any command executes a workflow stage or any raw local artifact becomes visible |
| 8 | 8:15-9:15 | Publication control summary | `bin/gra-issues --run .demo-public/minimal-run --dry-run > .demo-public/private-dry-run.log` and sanitized counts from JSON | Dry-run preview only, no publication plan, no apply, no GitHub write | Raw dry-run terminal output stays off-screen | Any path, fingerprint, title, hash, or draft body becomes visible |
| 9 | 9:15-10:00 | Public evidence references and close | `docs/evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md`, `docs/evaluation/CLAIM_EVIDENCE_MATRIX.md`, `docs/public/DEMO_PUBLICATION_REVIEW.md` | Evidence source list, publication checklist, human-only external posting | Keep view on headings and approved summary language | Any external link or upload workflow is shown |

## Per-shot technical notes

### Shot 1: positioning

Use the short README-compatible wording from the public positioning notes. Do not
invent stronger capability claims.

### Shot 2: disclosure boundary

State that public material excludes findings, code excerpts, scanner records,
prompts, transcripts, proof content, chain content, remediation detail,
credentials, local paths, and run IDs.

### Shot 3: redacted doctor output

Show only status keys and status values. The raw file is not a public artifact.

### Shot 4: synthetic benchmark

Keep the frame tight on the aggregate summary. If the terminal scrolls through
case-level rows, trim or crop that section unless the rows are intentionally part
of the approved script.

### Shot 5: fixed comparison

Say that the comparison demonstrates a recorded stage delta on the public
synthetic corpus. Do not say that one configuration is better for production.

### Shot 6: tiny fixture benchmark

Explain that the minimal fixture is repository-owned and used to demonstrate
local reporting mechanics. Do not treat it as a real target or as external
security evidence.

### Shot 7: declarative workflow control

Show planning only. Explain that the normal operator path reviews the plan before
explicit execution and resumes the same profile checkpoint after an interruption.
Use merged public documentation for execute/resume evidence; do not execute those
modes in the recording.

### Shot 8: dry-run publication control

Keep the actual dry-run command output private. Show only the derived counts.
State explicitly that external posting and GitHub write remain human-only.

### Shot 9: close

End with the review boundary: merged public docs are the only source for public
claims, and any external release step happens after a separate human review.

## Capture settings

- Use a large terminal font so the sanitized summary fills the frame.
- Use a narrow terminal width to avoid side panes and path spillover.
- Disable desktop notifications and auto-complete popups.
- Record a second audio track or speaker notes separately if needed.

## Editing rules

- Hard-cut any frame that exposes a local path, hash, fingerprint, draft title,
  or hidden file tree.
- Replace unsafe frames with a static shot of the approved public docs.
- Do not insert overlays that add new claims beyond the merged public docs.
- Do not add external logos or vendor-comparison graphics.

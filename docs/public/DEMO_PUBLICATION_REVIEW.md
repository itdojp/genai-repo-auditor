# Demo publication review checklist

Use this checklist before any human posts, uploads, embeds, or links the
recorded demo outside the local workstation.

## Review scope

This checklist covers:

- disclosure safety;
- credentials and environment leakage;
- path and run-identifier leakage;
- screenshot and video-frame review;
- claim control;
- external-link control; and
- confirmation that all external publication steps are human-only.

## 1. Disclosure review

Confirm all of the following:

- [ ] Every claim is supported by merged public docs only.
- [ ] The recording uses only public synthetic results and the repository-owned
      minimal fixture.
- [ ] No target-specific finding, code excerpt, path, fingerprint, title,
      commit-specific target detail, or issue draft body is visible or spoken.
- [ ] No raw scanner output, normalized scanner lead body, prompt, transcript,
      proof artifact, chain artifact, or remediation artifact is visible or
      spoken.
- [ ] No statement implies that zero published Issues means zero
      vulnerabilities.
- [ ] No statement implies autonomous disclosure approval.

## 2. Credentials and environment review

Confirm all of the following:

- [ ] No token, secret, cookie, credential, private key, or session artifact is
      visible.
- [ ] No credential-like environment variable name is visible.
- [ ] No browser profile name, account switcher, or sync identity is visible.
- [ ] No terminal prompt reveals username, hostname, or organization-internal
      machine name.
- [ ] No shell history, clipboard manager, password manager, or notification
      popup appears in any frame.

## 3. Path and local artifact review

Confirm all of the following:

- [ ] No local absolute path appears in the terminal, editor, player, or file
      browser.
- [ ] No run ID appears.
- [ ] No unpublished artifact filename is shown when that filename reveals a
      private workflow detail.
- [ ] No file tree view exposes hidden scratch directories, private notes, or
      temporary logs.
- [ ] The visible commands use relative demo paths such as `.demo-public/` only
      when needed.
- [ ] The ignored `.demo-public/` scratch directory was removed after recording
      and no demo-generated file is staged or retained.

## 4. Screenshot and frame review

Confirm all of the following:

- [ ] Each frame is cropped tightly enough that only approved content is shown.
- [ ] The recording does not show raw `gra-doctor` JSON.
- [ ] The recording does not show raw `gra-issues --dry-run` terminal output.
- [ ] The recording does not show `reports/findings.json`, `reports/issue-drafts/`,
      or other raw fixture artifacts.
- [ ] Any case-level synthetic output shown on screen is intentional, readable,
      and consistent with the public benchmark docs.
- [ ] Unsafe frames were removed rather than blurred when removal was possible.

## 5. Claim review

Use this table when reviewing narration, captions, overlays, and post text.

| Claim type | Allowed form | Primary source |
|---|---|---|
| Product description | Local-first, vendor-neutral AppSec audit harness for authorized repositories | `docs/dogfood/README_POSITIONING_NOTES.md` |
| Synthetic benchmark claim | Fixed public synthetic inputs produced deterministic, byte-stable results for the named source and corpus versions | `docs/evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md`, `docs/evaluation/EVALUATION_REPRODUCTION.md`, `docs/evaluation/CLAIM_EVIDENCE_MATRIX.md` |
| Comparison claim | The fixed comparison demonstrates a pinned stage difference on the public synthetic corpus | `docs/evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md`, `docs/evaluation/CLAIM_EVIDENCE_MATRIX.md` |
| Publication control claim | Issue publication is a human-reviewed gate; the demo uses dry-run only | `docs/dogfood/DEMO_SCRIPT.md`, `docs/DISCLOSURE_AND_PUBLICATION_POLICY.md` |
| Operational claim | Public dogfood materials use reviewed aggregate documentation and keep private artifacts outside Git | `docs/dogfood/PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`, `docs/dogfood/PUBLIC_ITDO_ERP4_CASE_STUDY.md`, `docs/DOGFOOD_REPORTING.md` |

Reject the recording if any caption or narration adds one of these unsupported
claims:

- production recall, production precision, or production readiness;
- model superiority, provider superiority, scanner superiority, or product
  equivalence to another offering;
- automatic vulnerability publication;
- automatic remediation approval;
- absence of vulnerabilities in any real repository.

## 6. External-link review

Confirm all of the following:

- [ ] Every link in the video description, companion post, or slide deck points
      to repository-owned public material only.
- [ ] Links resolve to merged public docs, the public repository root, or other
      approved public repository pages.
- [ ] No link points to private trackers, unpublished PRs, temporary artifacts,
      personal cloud storage, or local files.
- [ ] No link text promises stronger capability claims than the linked source
      supports.
- [ ] If a source commit or release is linked, the linked object is already
      public.

## 7. Human-only publication control

Confirm all of the following:

- [ ] Uploading the video is a separate human action.
- [ ] Posting the video description or companion text is a separate human action.
- [ ] Any GitHub release note, README update, social post, or community post is
      reviewed separately from the recording edit.
- [ ] No command in the recording performs GitHub write, issue creation, label
      mutation, or external upload.
- [ ] `gra-issues` is used in `--dry-run` mode only.
- [ ] `gra-run` is shown in plan mode only; execute and resume behavior is
      explained from merged public documentation rather than run on camera.
- [ ] `--plan`, `--apply`, `--apply-plan`, `--allow-public`, and
      `--create-labels` are absent from the recorded flow.
- [ ] If any review artifact mentions `--allow-public`, the nearby text states
      that public disclosure is denied by default and requires separate human
      approval before any public repository action.

## 8. Redaction and stop-condition confirmation

Confirm all of the following:

- [ ] A reviewer checked the final export frame by frame for local paths,
      credentials, target details, hashes, and fingerprints.
- [ ] Unsafe takes were discarded rather than patched with speculative editing.
- [ ] The final cut includes an explicit statement that external posting and
      disclosure decisions are human-only.
- [ ] The final cut includes an explicit statement that public claims are based
      on merged public docs only.
- [ ] The team knows who is authorized to approve external publication.

## Approval record

Complete this section before posting externally.

| Item | Reviewer | Decision | Notes |
|---|---|---|---|
| Disclosure review |  |  |  |
| Credential/path review |  |  |  |
| Screenshot/frame review |  |  |  |
| Claim review |  |  |  |
| External-link review |  |  |  |
| Human-only publication confirmation |  |  |  |

External posting is blocked until every row above has an explicit human decision.

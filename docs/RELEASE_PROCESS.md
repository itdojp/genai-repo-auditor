# Release process

This document defines the release, versioning, changelog, artifact, attestation,
and GitHub Release process for GenAI Repo Auditor.

## Scope and publication boundary

A release is a tagged snapshot of public repository content. It is not an audit
run. Release inputs and assets must not contain generated audit artifacts,
cloned targets, scanner output, credentials, tokens, private findings, proof
artifacts, remediation patches, Issue drafts, transcripts, or unapproved
disclosure content.

The canonical version is stored in [`VERSION`](../VERSION), while release notes
come from the matching section of [`CHANGELOG.md`](../CHANGELOG.md). The guarded
workflow is [`.github/workflows/release.yml`](../.github/workflows/release.yml),
and reproducible local artifact construction is implemented by
[`scripts/build_release.py`](../scripts/build_release.py).

The workflow never creates or moves a tag. A maintainer must review and merge
the release PR, confirm `main` CI, create and push the annotated tag, and then
explicitly dispatch publication.

## Versioning policy

Tags and GitHub Releases use the canonical version with a leading `v`, for
example `VERSION=0.5.0` and tag `v0.5.0`.

Until the project reaches `1.0.0`, use a conservative SemVer-style policy:

- `0.MINOR.0`: user-visible workflow changes, CLI option changes, report
  contract changes, or documentation sets that materially change operator
  guidance.
- `0.MINOR.PATCH`: bug fixes, documentation corrections, test-only changes, CI
  hardening, and release-process corrections that do not change user-facing
  contracts.
- `1.0.0` and later: follow SemVer expectations for `MAJOR.MINOR.PATCH`.

Do not update `VERSION` opportunistically in ordinary feature PRs. Update it in
a dedicated release-preparation PR.

## Changelog policy

Update `CHANGELOG.md` in the same release PR that changes `VERSION`. Each
section uses this format:

```markdown
## vX.Y.Z - YYYY-MM-DD

- Added ...
- Changed ...
- Fixed ...
- Security ...
```

Summarize user-visible behavior, operational impact, security posture, and
migration requirements. Do not copy private findings or sensitive audit detail
into release notes.

## Release artifacts

`scripts/build_release.py --build` creates the following files from a committed
Git object:

```text
genai-repo-auditor-vX.Y.Z.tar.gz
genai-repo-auditor-vX.Y.Z.zip
genai-repo-auditor-vX.Y.Z.cdx.json
release-manifest.json
SHA256SUMS
RELEASE_NOTES.md
```

The tar and ZIP archives are generated with `git archive`, so only tracked
files in the selected commit are included. The gzip header uses a fixed
timestamp. `release-manifest.json` binds artifact digests to the exact source
commit, and `SHA256SUMS` covers the archives, CycloneDX SBOM, and release
manifest. `RELEASE_NOTES.md` is workflow input derived from the reviewed
changelog section; it is not uploaded as a separate release asset.

The CycloneDX file describes this source distribution and its source revision.
The current source tree has no mandatory third-party Python package dependency,
so it does not invent dependency components. It is not an SBOM for audited
targets, optional scanners, AI workers, containers, or operator environments.

The release builder rejects tracked paths associated with local runs, target
clones, scanner results, Issue drafts, transcripts, SQLite/SARIF output,
remediation workspaces, and local agent state. Artifact creation rejects
`WORKTREE`; it requires a committed Git ref.

Repository-owned synthetic inputs under `tests/fixtures/` remain in the source
archives because they are required to reproduce the test suite. They are
public, non-production fixtures reviewed in Git, not artifacts copied from an
operator run.

## Release PR checklist

Create a dedicated branch from current `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c release/vX.Y.Z
```

In the release PR:

- update `VERSION` and add the matching dated `CHANGELOG.md` section;
- run the non-mutating release input check;
- confirm README, MANIFEST, command reference, report contract, and security
  model are consistent with the release boundary;
- confirm [`SECURITY.md`](../SECURITY.md),
  [`SECURITY_MODEL.md`](SECURITY_MODEL.md),
  [`ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), and
  [`SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md) are current;
- request maintainer and configured automated review;
- merge only after local validation and GitHub Actions are green.

Dry-run validation is the default and writes no artifacts:

```bash
python3 scripts/build_release.py --dry-run
```

After committing the release changes, verify deterministic artifact generation
without committing the generated files:

```bash
rm -rf .codex-local/tmp/release-a .codex-local/tmp/release-b
python3 scripts/build_release.py \
  --build --source-ref HEAD --output-dir .codex-local/tmp/release-a
python3 scripts/build_release.py \
  --build --source-ref HEAD --output-dir .codex-local/tmp/release-b
diff -ru .codex-local/tmp/release-a .codex-local/tmp/release-b
python3 scripts/build_release.py \
  --verify --output-dir .codex-local/tmp/release-a
```

Generated candidates belong under ignored `dist/` or `.codex-local/tmp/`
paths and must not be committed.

The frozen v0.5.0 source identity, deterministic candidate checksums, and exact
human publication gate are recorded in
[`releases/V0_5_0_PUBLICATION_HANDOFF.md`](releases/V0_5_0_PUBLICATION_HANDOFF.md).

## Required validation before tagging

Run the repository checks from the release commit:

```bash
for f in bin/gra-*; do
  if head -n 1 "$f" | grep -q 'bash'; then
    bash -n "$f"
  fi
done
```

```bash
python3 - <<'PY'
import py_compile
from pathlib import Path
for base in ['lib', 'bin', 'tests', 'scripts']:
    for path in sorted(Path(base).rglob('*.py')):
        py_compile.compile(str(path), doraise=True)
for path in sorted(Path('bin').glob('gra-*')):
    if path.is_file() and path.read_text(encoding='utf-8', errors='ignore').startswith('#!/usr/bin/env python3'):
        py_compile.compile(str(path), doraise=True)
print('py_compile ok')
PY
```

```bash
scripts/validate-install-smoke.sh
scripts/validate-shellcheck.sh
ruby -e 'require "yaml"; Dir[".github/workflows/*.yml"].each { |f| YAML.load_file(f); puts "ok #{f}" }'
python3 -m unittest discover -s tests
python3 scripts/build_release.py --dry-run
git diff --check
```

Before tagging, confirm the merged `main` commit has successful GitHub Actions
runs for `lint`, `self-validation`, and `codeql`.

## Workflow dry run

The `release` workflow defaults to validation only. This creates a short-lived
workflow artifact for maintainer inspection but does not create a tag,
attestation, or GitHub Release:

```bash
gh workflow run release.yml \
  --ref main \
  -f publish=false
```

Inspect the run and downloaded candidate before tagging:

```bash
gh run list --workflow release.yml --limit 5
gh run watch RUN_ID
gh run download RUN_ID --name release-candidate-RUN_ID \
  --dir .codex-local/tmp/release-candidate
python3 scripts/build_release.py \
  --verify --output-dir .codex-local/tmp/release-candidate
```

## Tagging

After the release PR is merged and `main` is green, tag the exact release
commit. The workflow requires an annotated tag and verifies that its commit is
an ancestor of `origin/main`.

```bash
git switch main
git pull --ff-only origin main
VERSION_VALUE="$(cat VERSION)"
test "v$VERSION_VALUE" = "vX.Y.Z"
git tag -a "v$VERSION_VALUE" -m "Release v$VERSION_VALUE"
git push origin "v$VERSION_VALUE"
```

Do not tag an unpushed commit or reuse/move an existing release tag.

## Attested GitHub Release publication

Publication is a separate explicit dispatch. Dispatch the workflow itself from
the existing release tag and set `publish=true`:

```bash
VERSION_VALUE="$(cat VERSION)"
gh workflow run release.yml \
  --ref "v$VERSION_VALUE" \
  -f publish=true
```

The elevated `publish` job runs only after the read-only candidate build job.
It requires the workflow dispatch ref itself to be an annotated version tag on
`main`, binds the downloaded manifest to that exact commit/tag, rebuilds from
the checked-out tag, and requires a byte-for-byte match with the candidate.
This also regenerates release notes from the checked-out `CHANGELOG.md` before
publication. It then creates a GitHub/Sigstore build-provenance attestation for
the release artifact set, creates a CycloneDX SBOM attestation for both source
archives, and runs `gh release create --verify-tag`. The job does not create,
move, or force-push tags. Configure protection/review requirements for the
`release` GitHub environment when repository policy requires a second human
approval.

GitHub documents that `actions/attest` requires `id-token: write` and
`attestations: write`; the workflow grants those permissions only to the
conditional publication job. Artifact attestations are available for public
repositories on current GitHub plans.

The release workflow pins third-party action execution to reviewed commit SHAs;
the adjacent version comments are maintained through reviewed dependency
updates.

## PyPI as an additional distribution channel

PyPI does not replace the source archives, checksums, SBOM, GitHub attestations,
or GitHub Release review above. The repository-side OIDC workflow, readiness
decision, archive validation, TestPyPI-first rollout, and human account setup
are defined in [`PYPI_DISTRIBUTION.md`](PYPI_DISTRIBUTION.md).

Production PyPI upload uses the same exact annotated `v$VERSION` tag and is
blocked until the matching GitHub Release's exact asset set, checksums, manifest
tag, and source commit are verified and then rechecked against live release
assets immediately before publication. TestPyPI may be used first to validate
package metadata and installed behavior, but it also requires the same
annotated tag and a separately protected `testpypi` environment. The production
job uses the protected `pypi` environment. Each environment must contain its
exact environment-scoped readiness marker only after required reviewers,
self-review prevention, and the single `v*` tag deployment policy are configured;
the workflow verifies these controls through the read-only GitHub API.
Both publishers must be configured externally for the exact repository,
workflow filename, and environment; no long-lived PyPI token is permitted.

The PyPI workflow can validate package candidates without upload from `main`:

```bash
gh workflow run publish-pypi.yml \
  --ref main \
  -f publish=false \
  -f index=testpypi
```

Upload remains a later explicit human action from the release tag. Do not add a
PyPI package URL or index install command to README until ownership, metadata,
the first upload, and installed smoke checks are approved.

References:

- [Using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations)
- [`actions/attest`](https://github.com/actions/attest)

## Consumer verification

Download the release assets into an otherwise empty directory, then verify the
checksum list:

```bash
sha256sum -c SHA256SUMS
```

Verify GitHub attestations against this repository identity:

```bash
gh attestation verify genai-repo-auditor-vX.Y.Z.tar.gz \
  --repo itdojp/genai-repo-auditor
gh attestation verify genai-repo-auditor-vX.Y.Z.zip \
  --repo itdojp/genai-repo-auditor
```

Checksum verification detects asset corruption or substitution relative to the
downloaded checksum list. Attestation verification additionally binds artifact
digests to the GitHub workflow identity. Consumers must still review release
notes and use an appropriate trust policy.

## Security and disclosure review

Before publication, confirm:

- no secrets, credentials, private findings, or unapproved disclosure content
  are present in the release diff or notes;
- no real `runs/`, `batches/`, `reports/`, `audits/`, scanner output, target
  clones, SQLite stores, transcripts, proof artifacts, or remediation patches
  are tracked;
- public language remains consistent with `--allow-public` safeguards and the
  [disclosure policy](DISCLOSURE_AND_PUBLICATION_POLICY.md);
- any security fix with disclosure impact has an approved disclosure plan.

If a security fix cannot yet be disclosed, coordinate privately and use
appropriately bounded changelog language until disclosure is approved.

## Hotfixes and failed releases

For a hotfix, create a release branch from current `main`, include only the
minimal fix and release metadata, run the same checks, and publish through the
same guarded workflow. Do not bypass review or CI unless maintainers explicitly
approve and document the exception.

If a tag or GitHub Release is incorrect:

1. stop further promotion;
2. record the operational problem without exposing private data;
3. prefer a follow-up patch release over rewriting public history;
4. if deletion is unavoidable, document the approver and reason.

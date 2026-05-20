# Release process

This document defines the release, versioning, changelog, and GitHub Release process for GenAI Repo Auditor.

## Scope

A release publishes a tagged snapshot of the repository for external users. It is not an audit run, and it must not include generated audit artifacts, cloned target repositories, scanner output, credentials, tokens, private findings, or public disclosure content that has not been approved.

## Versioning policy

The canonical version is stored in [`VERSION`](../VERSION). Tags and GitHub Releases use the same version with a leading `v`, for example `VERSION=0.1.0` and tag `v0.1.0`.

Until the project reaches `1.0.0`, use a conservative SemVer-style policy:

- `0.MINOR.0`: user-visible workflow changes, CLI option changes, report contract changes, or documentation sets that materially change operator guidance.
- `0.MINOR.PATCH`: bug fixes, documentation corrections, test-only changes, CI hardening, and release-process corrections that do not change user-facing contracts.
- `1.0.0` and later: follow SemVer expectations for `MAJOR.MINOR.PATCH`.

Do not update `VERSION` opportunistically in ordinary feature PRs. Update it in a dedicated release PR, or in a clearly identified release-preparation PR.

## Changelog policy

[`CHANGELOG.md`](../CHANGELOG.md) is updated in the same release PR that changes `VERSION`.

Each release section should use this format:

```markdown
## vX.Y.Z - YYYY-MM-DD

- Added ...
- Changed ...
- Fixed ...
- Security ...
```

Changelog entries should describe user-visible behavior, operational impact, security posture changes, and migration notes. Avoid copying commit logs verbatim. Do not include sensitive audit details or private vulnerability information.

## Release PR checklist

Create a release branch from current `main`.

```bash
git switch main
git pull --ff-only origin main
git switch -c release/vX.Y.Z
```

In the release PR:

- Update `VERSION`.
- Update `CHANGELOG.md` with the release date and concise notes.
- Confirm README and docs links are still correct.
- Confirm security-sensitive docs are current: [`SECURITY.md`](../SECURITY.md), [`docs/SECURITY_MODEL.md`](SECURITY_MODEL.md), [`docs/ISSUE_WORKFLOW.md`](ISSUE_WORKFLOW.md), and [`docs/SCANNER_INTEGRATION.md`](SCANNER_INTEGRATION.md).
- Confirm any CLI, schema, report contract, or workflow changes have matching documentation.
- Request maintainer review and any configured automated code review.
- Merge only after local validation and GitHub Actions are green.

## Required validation before tagging

Run these local checks from the repository root before opening or merging the release PR:

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
for base in ['lib', 'bin', 'tests']:
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
git diff --check
```

Before tagging, confirm the merged `main` commit has successful GitHub Actions runs for:

- `lint`
- `self-validation`
- `codeql`

## Tagging

After the release PR is merged and `main` is green, tag the exact release commit.

```bash
git switch main
git pull --ff-only origin main
VERSION_VALUE="$(cat VERSION)"
test "v$VERSION_VALUE" = "vX.Y.Z"
git tag -a "v$VERSION_VALUE" -m "Release v$VERSION_VALUE"
git push origin "v$VERSION_VALUE"
```

Use annotated tags for releases. Do not tag a local commit that has not been pushed to `origin/main`.

## GitHub Release creation

Create the GitHub Release from the pushed tag. Use the corresponding `CHANGELOG.md` section as the release notes. The notes file is a local scratch artifact and must be created before `gh release create`.

```bash
VERSION_VALUE="$(cat VERSION)"
mkdir -p .codex-local/tmp
RELEASE_NOTES=".codex-local/tmp/release-notes-v$VERSION_VALUE.md"
VERSION_VALUE="$VERSION_VALUE" RELEASE_NOTES="$RELEASE_NOTES" python3 - <<'PY'
import os
from pathlib import Path

version = os.environ["VERSION_VALUE"]
output = Path(os.environ["RELEASE_NOTES"])
heading = f"## v{version}"
lines = Path("CHANGELOG.md").read_text(encoding="utf-8").splitlines()
start = next((i for i, line in enumerate(lines) if line.startswith(heading)), None)
if start is None:
    raise SystemExit(f"missing changelog section: {heading}")
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
notes = "\n".join(lines[start:end]).strip() + "\n"
output.write_text(notes, encoding="utf-8")
PY
test -s "$RELEASE_NOTES"
```

Then create the GitHub Release.

```bash
gh release create "v$VERSION_VALUE" \
  --repo itdojp/genai-repo-auditor \
  --title "v$VERSION_VALUE" \
  --notes-file "$RELEASE_NOTES"
```

Release assets are optional. If assets are added later, they must be generated from the tagged source and must not contain local audit outputs, scanner results, cloned repositories, secrets, or private findings.

## Security and disclosure review

Before publishing a release, confirm:

- no secrets, tokens, credentials, or private findings are present in the diff;
- no real audit run outputs, `runs/`, `batches/`, scanner output, or SQLite stores are included;
- public disclosure language in docs and examples remains cautious and consistent with `--allow-public` safeguards;
- any security fix with disclosure impact has an approved disclosure plan before public release notes are published.

If the release contains a security fix that should not be disclosed yet, coordinate privately and use appropriately limited changelog language until disclosure is approved.

## Hotfix releases

For urgent fixes, create a release branch from current `main`, include only the minimal fix plus `VERSION` and `CHANGELOG.md` updates, run the same validation checklist, and tag after merge. Do not bypass review or CI for hotfixes unless repository maintainers explicitly approve the exception in the release PR.

## Failed or withdrawn releases

If a tag or GitHub Release is published incorrectly:

1. Stop further promotion of that version.
2. Open an Issue describing the operational problem without exposing secrets or private findings.
3. Prefer a follow-up patch release over rewriting public history.
4. If deletion is unavoidable, document who approved it and why in the Issue or release notes.

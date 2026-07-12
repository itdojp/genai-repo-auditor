# v0.5.0 GitHub Release publication handoff

## Status and boundary

**Status: pending human publication.** During the pre-publication inspection
recorded in this handoff on 2026-07-12, neither the annotated `v0.5.0` tag nor
the matching GitHub Release existed. This record completes the repository-local
release checks and stops at the human-only gate. It is not a claim that
publication, environment approval, or attestation has occurred.

Codex and repository automation must not create, move, push, or delete the tag;
dispatch `publish=true`; approve the `release` environment; or create the
GitHub Release. A maintainer performs those actions explicitly. If any expected
identity already exists when the maintainer starts, stop and verify it instead
of overwriting or reusing it.

## Frozen release identity

| Field | Exact value |
|---|---|
| Version | `0.5.0` |
| Annotated tag | `v0.5.0` |
| Source commit | `fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0` |
| Source branch relationship | Commit is the reviewed `main` commit merged by PR #251 and is an ancestor of current `main` after this handoff PR |
| Release workflow | `.github/workflows/release.yml` from the frozen source commit |
| Release notes | `CHANGELOG.md` section `v0.5.0 - 2026-07-12` from the frozen source commit |

Do not retarget `v0.5.0` to the handoff-document commit or any later commit.
The handoff is historical metadata about the already frozen release source.

## Expected GitHub Release assets

`RELEASE_NOTES.md` is workflow input and is not uploaded as a separate asset.
The exact public asset set is:

| Asset | Size | SHA-256 |
|---|---:|---|
| `genai-repo-auditor-v0.5.0.tar.gz` | 835739 | `14f1e5bb80288a82aea4f665bbb28dfdeface193eb4e472839769fa968f170ca` |
| `genai-repo-auditor-v0.5.0.zip` | 1182052 | `18dd3718071a8de6caeaf22d14b26e3cd0697ab2e3f9487f39529c55127975a1` |
| `genai-repo-auditor-v0.5.0.cdx.json` | 991 | `479fe4c600d324bd1701d08ccbe866295179dfba2727ca459ff3013bb814fdf1` |
| `release-manifest.json` | 687 | `b642cdef86c2edc868ca0eb2253690d4e2048999c98242b07426eb7a63bba183` |
| `SHA256SUMS` | 384 | `dff06c49f7cbde8a47c9272b47e57f8ce2ea4409b42ca24b18e9447539b5afa3` |

Canonical `SHA256SUMS` content:

```text
479fe4c600d324bd1701d08ccbe866295179dfba2727ca459ff3013bb814fdf1  genai-repo-auditor-v0.5.0.cdx.json
14f1e5bb80288a82aea4f665bbb28dfdeface193eb4e472839769fa968f170ca  genai-repo-auditor-v0.5.0.tar.gz
18dd3718071a8de6caeaf22d14b26e3cd0697ab2e3f9487f39529c55127975a1  genai-repo-auditor-v0.5.0.zip
b642cdef86c2edc868ca0eb2253690d4e2048999c98242b07426eb7a63bba183  release-manifest.json
```

The manifest must declare schema version `1`, version `0.5.0`, tag `v0.5.0`,
and source commit `fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0`.

## Completed pre-publication evidence

Two clean builds from the frozen committed source were byte-identical. Both
passed `scripts/build_release.py --verify`. The dry run reported version
`0.5.0`, tag `v0.5.0`, the source commit above, five upload assets, and 484
tracked source files. Generated candidates remain only under ignored
`.codex-local/tmp/issue253/` storage and must not be committed.

Protected-`main` push runs for the frozen source all completed successfully:

| Workflow | Run |
|---|---|
| self-validation | [29182324198](https://github.com/itdojp/genai-repo-auditor/actions/runs/29182324198) |
| lint | [29182324187](https://github.com/itdojp/genai-repo-auditor/actions/runs/29182324187) |
| CodeQL | [29182324216](https://github.com/itdojp/genai-repo-auditor/actions/runs/29182324216) |
| install-matrix | [29182324214](https://github.com/itdojp/genai-repo-auditor/actions/runs/29182324214) |

The repository checks also confirm that release archives exclude local audit
runs, target clones, scanner results, findings, prompts/transcripts from runs,
private holdout content, proof/remediation workspaces, Issue drafts,
databases/SARIF output, credentials, and `.codex-local` state. Public synthetic
test fixtures remain intentional reviewed source inputs.

## Human-only publication gate

A maintainer must perform the following from a clean trusted checkout. Review
the commands before execution; these commands intentionally mutate the remote
tag/release state and are not for Codex execution.

1. Confirm the four frozen-source workflow runs above are still successful and
   fail closed unless the `release` GitHub environment already exists with at
   least one required reviewer and self-review prevention enabled. GitHub can
   otherwise create a referenced environment without protection rules:

   ```bash
   set -euo pipefail
   gh attestation verify --help >/dev/null
   environment_json="$(gh api \
     repos/itdojp/genai-repo-auditor/environments/release)"
   jq -e '
     .name == "release" and
     ([.protection_rules[]? |
       select(
         .type == "required_reviewers" and
         .prevent_self_review == true and
         (.reviewers | length) > 0
       )] | length) == 1
   ' <<<"$environment_json" >/dev/null
   ```

   A missing attestation subcommand, API error, missing rule, empty reviewer
   list, or disabled self-review prevention is a hard stop. Upgrade GitHub CLI
   or configure the environment in repository settings, then rerun this
   read-only check before creating the tag.
2. Confirm the tag and Release remain absent:

   ```bash
   set -euo pipefail
   git fetch origin main --tags
   test -z "$(git tag -l v0.5.0)"
   release_probe="$(gh api --include \
     repos/itdojp/genai-repo-auditor/releases/tags/v0.5.0 2>&1 || true)"
   printf '%s\n' "$release_probe" | grep -Eq '^HTTP/[0-9.]+ 404 '
   git merge-base --is-ancestor \
     fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0 origin/main
   ```

3. Create and push the exact annotated tag. Do not use `--force`, move an
   existing tag, or substitute another commit:

   ```bash
   git tag -a v0.5.0 \
     fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0 \
     -m "GenAI Repo Auditor v0.5.0"
   test "$(git cat-file -t v0.5.0)" = "tag"
   test "$(git rev-list -n 1 v0.5.0)" = \
     "fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0"
   git push origin refs/tags/v0.5.0
   ```

4. Dispatch the reviewed workflow from the tag, request publication, and
   approve the protected `release` environment only after reviewing the
   candidate artifact:

   ```bash
   gh workflow run release.yml \
     --repo itdojp/genai-repo-auditor \
     --ref v0.5.0 \
     -f publish=true
   ```

5. Record the workflow-run URL and confirm that both `build-candidate` and
   `publish` complete successfully. Do not bypass a failed check or environment
   gate.

To resume Codex read-only verification, report that the gate is complete and
provide the workflow-run URL. No credential, token, or private release detail
is needed.

## Post-publication read-only verification

After the maintainer confirms completion, Codex may perform these non-mutating
checks in ignored local storage:

```bash
gh release view v0.5.0 \
  --repo itdojp/genai-repo-auditor \
  --json tagName,targetCommitish,isDraft,isPrerelease,publishedAt,assets,url

rm -rf .codex-local/tmp/v0.5.0-release-verify
mkdir -p .codex-local/tmp/v0.5.0-release-verify
gh release download v0.5.0 \
  --repo itdojp/genai-repo-auditor \
  --dir .codex-local/tmp/v0.5.0-release-verify
python3 scripts/build_release.py --verify \
  --output-dir .codex-local/tmp/v0.5.0-release-verify
(
  cd .codex-local/tmp/v0.5.0-release-verify
  sha256sum -c SHA256SUMS
)

verify_dir=.codex-local/tmp/v0.5.0-release-verify
for asset in \
  genai-repo-auditor-v0.5.0.tar.gz \
  genai-repo-auditor-v0.5.0.zip \
  genai-repo-auditor-v0.5.0.cdx.json \
  release-manifest.json \
  SHA256SUMS
do
  gh attestation verify "$verify_dir/$asset" \
    --repo itdojp/genai-repo-auditor \
    --signer-workflow \
      itdojp/genai-repo-auditor/.github/workflows/release.yml \
    --source-ref refs/tags/v0.5.0 \
    --source-digest fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0
done

for archive in \
  genai-repo-auditor-v0.5.0.tar.gz \
  genai-repo-auditor-v0.5.0.zip
do
  gh attestation verify "$verify_dir/$archive" \
    --repo itdojp/genai-repo-auditor \
    --predicate-type https://cyclonedx.org/bom \
    --signer-workflow \
      itdojp/genai-repo-auditor/.github/workflows/release.yml \
    --source-ref refs/tags/v0.5.0 \
    --source-digest fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0
done
```

Verification must additionally compare the downloaded asset-name set and
checksums to this handoff, inspect `release-manifest.json` for the exact tag and
source commit, confirm release notes match the frozen changelog section, and
confirm the GitHub build-provenance and CycloneDX SBOM attestations. Downloaded
assets remain local and must not be committed.

## Failure handling

Stop promotion if the tag points elsewhere, any expected asset is missing or
extra, a checksum/size differs, the manifest identity differs, an attestation
fails, release notes diverge, or a prohibited/private path is detected. Do not
rewrite the public tag or overwrite release assets. Record the bounded failure
and use the reviewed hotfix/patch-release process from
[`RELEASE_PROCESS.md`](../RELEASE_PROCESS.md).

# v0.5.0 GitHub Release publication handoff

## Status and boundary

**Status: pending human publication.** During the pre-publication inspection
recorded in this handoff on 2026-07-12, neither the annotated `v0.5.0` tag nor
the matching GitHub Release existed. This record completes the repository-local
release checks and stops at the human-only gate. It is not a claim that
publication, environment approval, or attestation has occurred.

The handoff was amended on 2026-07-19 for the repository's documented
single-maintainer governance. A read-only recheck found that the `release`
environment is absent, immutable releases are disabled, no effective tag
ruleset exists, the maintainer account publishes no GPG or SSH signing key, and
the `v0.5.0` tag and Release remain absent. These are hard stops until the human
maintainer configures and verifies the controls below.

Codex, other AI review channels, and repository automation must not create,
move, push, or delete the tag;
dispatch `publish=true`; approve the `release` environment; or create the
GitHub Release. The accountable human maintainer `ootakazuhiko` performs those
actions explicitly. If any expected identity already exists when the maintainer
starts, stop and verify it instead of overwriting or reusing it.

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

## Single-maintainer release profile

This repository has one accountable human maintainer, `ootakazuhiko`, and will
not add a second human maintainer solely for release approval. The former
distinct-human-reviewer and self-review-prevention profile is not used for this
release. The replacement profile requires:

- required reviewer `ootakazuhiko` and `prevent_self_review=false`;
- a wait timer of at least 30 minutes and administrator bypass disabled;
- deployment restricted to tags matching `v*`;
- immutable releases enabled before publication;
- an active `v*` tag ruleset without bypass actors that restricts updates and
  deletions and blocks force pushes;
- a signed annotated `v0.5.0` tag bound to the frozen source commit;
- reproducible candidates, byte-identical results, candidate verification, and
  exact checksum verification;
- successful required CI plus artifact build-provenance and CycloneDX SBOM
  attestations;
- at least two distinct AI review channels with zero unresolved blockers; and
- one final accountable human approval by `ootakazuhiko`.

AI review is defense in depth. It is not separation of human duties, must not be
described as independent human approval, and cannot substitute for the final
human decision. Record each AI channel, reviewed subject and commit, result, and
blocker disposition. An unavailable channel, unknown result, or unresolved
blocker is a hard stop.

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
   fail closed unless the environment, immutable-release setting, and effective
   tag ruleset satisfy the repository validator. GitHub can otherwise create a
   referenced environment without protection rules. The validator rejects
   absent, malformed, incomplete, legacy, or weak API responses. It accepts a
   missing deployment-policy `type` only by returning an explicit mandatory UI
   check instead of inferring that the `v*` policy targets tags:

   ```bash
   set -euo pipefail
   gh attestation verify --help >/dev/null
   api_header='X-GitHub-Api-Version: 2026-03-10'
   environment_json="$(gh api \
     -H "$api_header" \
     repos/itdojp/genai-repo-auditor/environments/release)"
   deployment_policies_json="$(gh api \
     -H "$api_header" \
     --paginate --slurp \
     repos/itdojp/genai-repo-auditor/environments/release/deployment-branch-policies)"
   immutable_json="$(gh api \
     -H "$api_header" \
     repos/itdojp/genai-repo-auditor/immutable-releases)"
   ruleset_index_json="$(gh api \
     -H "$api_header" \
     --paginate --slurp \
     'repos/itdojp/genai-repo-auditor/rulesets?includes_parents=true&targets=tag')"
   ruleset_ids="$(jq -r '
     [.[] | .[]? |
       select(.target == "tag" and .enforcement == "active") | .id] | .[]
   ' <<<"$ruleset_index_json")"
   test -n "$ruleset_ids"
   rulesets_json="$({
     while IFS= read -r ruleset_id; do
       gh api -H "$api_header" \
         "repos/itdojp/genai-repo-auditor/rulesets/$ruleset_id"
     done <<<"$ruleset_ids"
   } | jq -s .)"
   python3 scripts/validate_release_controls.py \
     --environment-json "$environment_json" \
     --deployment-policies-json "$deployment_policies_json" \
     --immutable-releases-json "$immutable_json" \
     --rulesets-json "$rulesets_json"
   ```

   A missing attestation subcommand, API/validator error, additional or missing
   reviewer, `prevent_self_review` other than `false`, wait timer below 30
   minutes, additional/wrong deployment policy, disabled immutable-release
   setting, bypass actor, excluded release tag, creation restriction, or missing
   update/deletion/non-fast-forward rule is a hard stop.
2. In **Settings > Environments > release**, verify **Allow administrators to
   bypass configured protection rules** is deselected and the sole selected
   deployment policy is **Tag `v*`**. Record both check results and the check
   date in Issue #253. The documented environment and deployment-policy GET
   examples in REST API version `2026-03-10` do not expose both settings
   consistently, so these controls require human UI inspection. Inability to
   inspect or record either setting is a hard stop; do not infer them from other
   API fields.
3. Confirm that the two byte-identical frozen-source candidates, exact asset
   checksums above, candidate verification, and required CI evidence remain
   accepted. Record at least two distinct AI review channels for the exact
   frozen source/candidate and this publication handoff, with zero unresolved
   blockers. AI output is review evidence only; it is not human approval.
4. Confirm the tag and Release remain absent:

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

5. Publish an OpenPGP signing key on the `ootakazuhiko` GitHub account, record
   its complete uppercase primary-key fingerprint in Issue #253, and configure
   it as the approved maintainer key. Create and push the exact signed annotated
   tag with that key. Do not use `--force`, move an existing tag, or substitute
   another commit. Stop if the full primary fingerprint cannot be matched:

   ```bash
   set -euo pipefail
   : "${APPROVED_TAG_SIGNING_FINGERPRINT:?set the fingerprint recorded in Issue #253}"
   printf '%s\n' "$APPROVED_TAG_SIGNING_FINGERPRINT" |
     grep -Eq '^([0-9A-F]{40}|[0-9A-F]{64})$'
   git tag -s -u "$APPROVED_TAG_SIGNING_FINGERPRINT" v0.5.0 \
     fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0 \
     -m "GenAI Repo Auditor v0.5.0"
   test "$(git cat-file -t v0.5.0)" = "tag"
   test "$(git rev-list -n 1 v0.5.0)" = \
     "fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0"
   verify_output="$(git verify-tag --raw v0.5.0 2>&1)"
   verified_primary_fingerprint="$(awk \
     '/^\[GNUPG:\] VALIDSIG / {print (NF >= 12 ? $NF : $3)}' \
     <<<"$verify_output")"
   test "$verified_primary_fingerprint" = \
     "$APPROVED_TAG_SIGNING_FINGERPRINT"
   git push origin refs/tags/v0.5.0
   ```

6. Verify the pushed remote ref still names the same locally verified annotated
   tag object, resolves to the frozen source, and GitHub recognizes its
   signature before dispatch:

   ```bash
   set -euo pipefail
   api_header='X-GitHub-Api-Version: 2026-03-10'
   tag_ref_json="$(gh api -H "$api_header" \
     repos/itdojp/genai-repo-auditor/git/ref/tags/v0.5.0)"
   tag_object_sha="$(jq -er '.object | select(.type == "tag") | .sha' \
     <<<"$tag_ref_json")"
   test "$tag_object_sha" = "$(git rev-parse refs/tags/v0.5.0)"
   tag_object_json="$(gh api -H "$api_header" \
     "repos/itdojp/genai-repo-auditor/git/tags/$tag_object_sha")"
   jq -e '
     .object.type == "commit" and
     .object.sha == "fb8c5f00afa89e6f8b09eb6c76876833fef2fcd0" and
     .verification.verified == true
   ' <<<"$tag_object_json" >/dev/null
   ```

7. Dispatch the reviewed workflow from the tag and request publication. After
   the environment wait timer has elapsed, `ootakazuhiko` reviews the candidate,
   all recorded AI results, and every external control, then performs the one
   accountable human final approval. Do not use administrator bypass:

   ```bash
   gh workflow run release.yml \
     --repo itdojp/genai-repo-auditor \
     --ref v0.5.0 \
     -f publish=true
   ```

8. Record the workflow-run URL and confirm that both `build-candidate` and
   `publish` complete successfully. Do not bypass a failed check or environment
   gate.

To resume Codex read-only verification, report that the gate is complete and
provide the workflow-run URL. No credential, token, or private release detail
is needed.

## Post-publication read-only verification

After the maintainer confirms completion, Codex may perform these non-mutating
checks in ignored local storage:

```bash
api_header='X-GitHub-Api-Version: 2026-03-10'
release_json="$(gh api -H "$api_header" \
  repos/itdojp/genai-repo-auditor/releases/tags/v0.5.0)"
jq -e '
  .tag_name == "v0.5.0" and
  .draft == false and
  .prerelease == false and
  .immutable == true
' <<<"$release_json" >/dev/null

gh release verify v0.5.0 \
  --repo itdojp/genai-repo-auditor

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

Stop promotion if an external control is absent or unverifiable, an AI review
has an unresolved blocker, the tag signature fails, the tag points elsewhere,
the Release is not immutable, any expected asset is missing or extra, a
checksum/size differs, the manifest identity differs, an attestation fails,
release notes diverge, or a prohibited/private path is detected. Do not rewrite
the public tag or overwrite release assets. Record the bounded failure and use
the reviewed hotfix/patch-release process from
[`RELEASE_PROCESS.md`](../RELEASE_PROCESS.md).

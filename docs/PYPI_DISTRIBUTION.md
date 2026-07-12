# PyPI distribution and trusted publishing

## Readiness decision

The repository-side package is ready for a human-controlled TestPyPI trial and,
after that trial is reviewed, a separately approved production PyPI publication.
External activation is **not** complete:

- availability and ownership of the `genai-repo-auditor` project name are
  unknown until a human verifies them in the applicable PyPI account;
- neither the PyPI nor TestPyPI project/pending publisher is configured by this
  repository change;
- the `testpypi` and `pypi` GitHub environments must be created and protected by
  a maintainer; and
- no package URL is approved until the first upload and metadata review succeed.

Pending publishers do not reserve a project name. Recheck the name immediately
before the first upload; do not infer availability from an unauthenticated
search or a temporary 404 response.

The recommended rollout is TestPyPI first. Production PyPI remains a separate
decision and the workflow additionally downloads and verifies the complete
matching GitHub Release asset set before a production upload.

## Distribution contract

The canonical version remains [`VERSION`](../VERSION). The same value is used
by package metadata, `gra-* --version`, annotated Git tag `vX.Y.Z`, GitHub
Release, and PyPI distribution metadata. The PyPI workflow never creates,
moves, or force-pushes a tag.

[`pyproject.toml`](../pyproject.toml) declares:

- distribution name `genai-repo-auditor`;
- Apache-2.0 license expression and repository-owned README metadata;
- Python `>=3.10,<3.13`, matching the tested Python 3.10-3.12 support window;
- the complete `gra-*` console-script surface; and
- package data for commands, libraries, prompts, schemas, taxonomies, workflow
  profiles, and the public synthetic efficacy corpus.

[`MANIFEST.in`](../MANIFEST.in) excludes tests and local/generated roots from
the sdist. Public regression fixtures remain available in the Git repository
and GitHub source archives, but they are not required to install the PyPI
package.

[`scripts/validate_python_distribution.py`](../scripts/validate_python_distribution.py)
requires exactly one wheel and one sdist, checks metadata and all expected
runtime resources, rejects unsafe archive paths and links, and rejects local
run, target clone, scanner-result, Issue-draft, transcript, database, SARIF,
holdout, and test paths. This is a structural boundary; it does not replace
review of tracked source content.

## Workflow and privilege boundary

The guarded workflow is
[`publish-pypi.yml`](../.github/workflows/publish-pypi.yml). It is manual-only:
normal pushes and pull requests cannot upload a distribution.

The read-only `build-candidate` job:

1. checks out the explicitly dispatched ref without persisted credentials;
2. when upload is requested, requires an exact annotated `v$VERSION` tag whose
   commit is on or ancestral to `main`;
3. before production PyPI, downloads the matching GitHub Release, verifies its
   exact asset set and checksums, and binds its manifest tag and source commit
   to the dispatched ref and `github.sha`; a TestPyPI trial remains possible
   before production release publication;
4. installs build/check tooling from a hash-locked dependency file without a
   pip cache, then builds one wheel and one sdist without build isolation;
5. runs strict `twine check` and the repository distribution validator;
6. installs and smoke-tests the exact wheel and sdist independently; and
7. records checksums and the exact source commit in a seven-day workflow artifact.

Only one conditional upload job runs:

| Index | GitHub environment | PyPI publisher binding | Additional condition |
|---|---|---|---|
| TestPyPI | `testpypi` | repository `itdojp/genai-repo-auditor`, workflow `publish-pypi.yml`, environment `testpypi` | Exact annotated tag on `main` |
| PyPI | `pypi` | repository `itdojp/genai-repo-auditor`, workflow `publish-pypi.yml`, environment `pypi` | Exact annotated tag on `main` and matching, checksum-valid GitHub Release assets and manifest |

Each upload job has `actions: read` for read-only environment-policy API checks,
`contents: read` for release access, and `id-token: write` for publication. The
OIDC permission is absent from the build job and top-level workflow. Upload uses
the official `pypa/gh-action-pypi-publish` action pinned to the reviewed v1.14.0
commit. No `PYPI_API_TOKEN`, password, or long-lived upload secret is accepted.

The first step of each upload job requires the environment-level variable
`PYPI_TRUSTED_PUBLISHING_APPROVED` to equal the destination (`testpypi` or
`pypi`). The next step queries the GitHub API and requires the exact environment
to exist with non-empty required reviewers, self-review prevention, and exactly
one custom deployment policy, the `v*` tag pattern. A missing environment can
otherwise be auto-created without protection by GitHub Actions; absent or weak
configuration therefore fails before candidate download or OIDC publication.
Repository- or organization-level variables with the marker name remain
forbidden; unlike the marker alone, the API check independently verifies the
actual environment protection.

The downloaded candidate is checksum-verified and bound to `github.sha` before
the action obtains a short-lived trusted-publishing credential. Production also
redownloads the live GitHub Release immediately before publication and requires
its exact asset set, manifest, and release checksum list to remain byte-for-byte
identical to the reviewed candidate binding.

PyPI attestations are enabled for both trusted-publishing destinations. They
complement, but do not replace, the GitHub source-release checksums, SBOM, and
GitHub artifact attestations.

## Threat model

| Threat | Repository control | Residual / human control |
|---|---|---|
| PR or ordinary push uploads a package | Workflow has only `workflow_dispatch`; upload jobs also require `publish=true`. | Branch protection and review still protect changes to the workflow itself. |
| Tag/version substitution | Exact annotated tag, `VERSION`, checked-out commit, `main` ancestry, candidate source commit, and package metadata must agree. | Maintainer creates the tag only after release review and green `main` CI. |
| Long-lived credential theft | Trusted publishing uses GitHub OIDC; no PyPI token secret is referenced. | Maintainer must not add a token fallback in repository or environment secrets. |
| Over-broad OIDC permission | `id-token: write` exists only in conditional environment-gated upload jobs. | The pinned publish and download actions remain trusted dependencies and require reviewed updates. |
| Build dependency substitution | Build/check dependencies and transitive dependencies are version- and hash-locked; pip cache and isolated-build downloads are disabled. | Maintainers must review and regenerate the lock deliberately when updating tooling. |
| Unreviewed package content | Structural archive validation, strict metadata check, independent wheel/sdist installs, resource smoke tests, and checksum binding run before upload. | Review tracked source and the downloaded candidate; structural checks cannot prove source content is non-sensitive. |
| Wrong or unprotected publisher environment | Fixed names, destination marker, and read-only API checks require the real environment to have reviewers, self-review prevention, and only the `v*` deployment policy before OIDC. | PyPI/TestPyPI publisher records must still match exactly; maintainers configure the externally owned protection and marker. |
| Duplicate, partial, or wrong-index release | TestPyPI is the first rollout; production is a separate environment and additionally requires a GitHub Release. No skip-existing behavior is enabled. | PyPI files and versions are immutable; a failed/partial release requires investigation and normally a new version, not overwrite. |
| Project-name takeover | No availability claim is made; pending publisher does not reserve the name. | Verify ownership/name availability while configuring the publisher and immediately before first upload. |

## Repository validation without upload

Build and validate in ignored local storage:

```bash
python3 -m venv .codex-local/venvs/pypi-readiness
.codex-local/venvs/pypi-readiness/bin/python -m pip install \
  --require-hashes --no-cache-dir \
  -r .github/requirements/publish-build.txt
rm -rf .codex-local/tmp/pypi-dist
.codex-local/venvs/pypi-readiness/bin/python -m build \
  --no-isolation --outdir .codex-local/tmp/pypi-dist
.codex-local/venvs/pypi-readiness/bin/python -m twine check --strict \
  .codex-local/tmp/pypi-dist/*
python3 scripts/validate_python_distribution.py \
  --dist-dir .codex-local/tmp/pypi-dist
```

The workflow can also build and retain a candidate without OIDC or upload:

```bash
gh workflow run publish-pypi.yml \
  --ref main \
  -f publish=false \
  -f index=testpypi
```

Review the workflow artifact before configuring or approving an upload.

## Human-controlled external setup

Codex and repository automation must not perform these account actions.

1. Sign in to the intended TestPyPI and PyPI owner accounts and verify the
   project name/ownership state. For a new project, create a pending publisher;
   for an existing project, add a publisher in the project Publishing settings.
2. In GitHub, create environments named exactly `testpypi` and `pypi`. Before
   adding the readiness marker, configure at least one required reviewer,
   enable self-review prevention, select custom deployment branches and tags,
   and add exactly one deployment policy: tag pattern `v*`. The workflow's
   read-only GitHub API gate requires this exact minimum configuration. Do not
   store a PyPI API token in either environment.
3. Only after those protection rules are saved, add the environment-level
   variable `PYPI_TRUSTED_PUBLISHING_APPROVED` with value `testpypi` in the
   `testpypi` environment and value `pypi` in the `pypi` environment. Never
   create this variable at repository or organization scope. Its absence makes
   the upload job fail closed before OIDC publication.
4. Configure the TestPyPI trusted publisher with:
   - owner: `itdojp`
   - repository: `genai-repo-auditor`
   - workflow: `publish-pypi.yml`
   - environment: `testpypi`
5. Configure the production PyPI trusted publisher with the same owner,
   repository, and workflow, and environment `pypi`.
6. Recheck project-name ownership. Review the exact annotated release tag,
   successful `main` CI, package candidate, metadata, checksums, and environment
   reviewer list.
7. Approve the first TestPyPI trial from the exact tag:

   ```bash
   gh workflow run publish-pypi.yml \
     --ref vX.Y.Z \
     -f publish=true \
     -f index=testpypi
   ```

8. Verify TestPyPI metadata and install the exact version without dependency
   fallback:

   ```bash
   python3 -m venv .codex-local/tmp/testpypi-verify
   .codex-local/tmp/testpypi-verify/bin/python -m pip install \
     --index-url https://test.pypi.org/simple/ \
     --no-deps genai-repo-auditor==X.Y.Z
   .codex-local/tmp/testpypi-verify/bin/gra-audit --version
   .codex-local/tmp/testpypi-verify/bin/gra-doctor --help
   ```

9. Only after the TestPyPI result, GitHub Release, exact public metadata, and
   environment approval are accepted, separately dispatch `index=pypi` from the
   same tag. Verify the production package, attestations, console scripts, and
   metadata before recording an approved public package URL.

Do not add an unverified PyPI URL or index-based install command to README.

## Failure handling

- If OIDC reports a publisher mismatch, compare the exact owner, repository,
  workflow filename, environment, and event/ref claims. Do not add a token
  workaround.
- If environment readiness, tag, version, `main` ancestry, GitHub Release asset
  set/manifest, source commit, checksum, metadata, archive, install, or smoke
  validation fails, stop publication and correct the source or external
  protection through the applicable reviewed process.
- Do not overwrite, move, or reuse a release tag. Do not enable skip-existing.
- PyPI does not permit replacing an uploaded distribution file. Treat a partial
  upload as a release incident and use a new reviewed version when republishing
  is required.

## Official references

- [Adding a publisher to an existing PyPI project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Creating a project with a pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Publishing with a trusted publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [Trusted publisher internals](https://docs.pypi.org/trusted-publishers/internals/)
- [Trusted publisher troubleshooting](https://docs.pypi.org/trusted-publishers/troubleshooting/)
- [PyPI attestations](https://docs.pypi.org/attestations/producing-attestations/)
- [GitHub OIDC reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [GitHub REST API for deployment environments](https://docs.github.com/en/rest/deployments/environments)
- [GitHub REST API for deployment branch policies](https://docs.github.com/en/rest/deployments/branch-policies)
- [`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish)

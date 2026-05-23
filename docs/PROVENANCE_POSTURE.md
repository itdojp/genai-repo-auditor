# Artifact attestation and release provenance posture

`gra-recon` performs a deterministic local review of GitHub Actions workflows for
release, package, container, and binary artifact publication posture. The pass
does not execute repository code and does not contact GitHub or package
registries.

The command writes:

- `reports/provenance-posture.json`
- `reports/PROVENANCE_POSTURE.md`

`gra-targets --generate` appends workflows with actionable posture
recommendations as `TGT-PROVENANCE-NNN` target queue items.

## What is detected

The detector scans `.github/workflows/*.yml` and `.github/workflows/*.yaml` for:

- release asset publication, for example `gh release` or release upload actions;
- package publication, for example `npm publish`, `twine upload`, or
  `cargo publish`;
- container image build and push workflows, including `docker/build-push-action`
  and `ghcr.io` references;
- binary/archive artifact generation and upload;
- `actions/attest`, `actions/attest-build-provenance`, `actions/attest-sbom`,
  `gh attestation`, `cosign attest`, or SLSA generator usage;
- SBOM generation and `sbom-path` attestation inputs;
- workflow permissions relevant to attestation:
  - `id-token: write`
  - `contents: read`
  - `attestations: write`
  - `packages: write` for container registry publication.

Repositories without release, package, container, or binary publishing workflows
are reported as `not_applicable` rather than as failures.

## Classification

Missing attestations are supply-chain posture recommendations, not confirmed
high-severity vulnerabilities. A generated target is intended to help a reviewer
decide whether artifacts are published to users, whether documentation promises
provenance, and whether the workflow is security-critical.

The detector reports:

- `attested` when applicable workflows include attestation signals and required
  permissions;
- `needs_review` when artifact-publishing workflows lack attestations, SBOM
  attestations, or expected permissions;
- `not_applicable` when no applicable publishing workflow is detected.

## Verification limitations

This project is local-first. The provenance posture pass can identify workflow
configuration and documentation signals, but it does not verify that a published
artifact actually has an attestation in GitHub's service or in a registry.

Online verification normally uses `gh attestation verify`. Offline or air-gapped
verification requires separately exported attestation bundles and trust
material; do not assume online verification commands are available in an offline
audit environment.

## References

- [GitHub Docs: Using artifact attestations to establish provenance for builds](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [GitHub `actions/attest`](https://github.com/actions/attest)

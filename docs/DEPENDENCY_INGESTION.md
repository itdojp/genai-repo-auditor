# SBOM and dependency graph ingestion

GenAI Repo Auditor can ingest SBOM and dependency graph JSON as local dependency
posture evidence. The ingest path does not generate an SBOM and does not query
external vulnerability services. Generate or export the SBOM in an authorized
environment, then import the JSON artifact into an audit run.

Supported normalized inputs:

- CycloneDX JSON (`bomFormat: CycloneDX`)
- SPDX 2.3 JSON
- GitHub Dependency Graph SBOM export shape (`{"sbom": {... SPDX ...}}`)
- Syft native JSON inventory shape (`artifacts` / `artifactRelationships`) on a
  best-effort basis
- Trivy SBOM exports when emitted as CycloneDX JSON or SPDX JSON

Official references:

- GitHub Dependency Graph SBOM export: https://docs.github.com/en/rest/dependency-graph/sboms
- CycloneDX specification overview: https://cyclonedx.org/specification/overview/
- SPDX 2.3 package information: https://spdx.github.io/spdx-spec/v2.3/package-information/
- SPDX 2.3 relationships: https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/

## Ingest an SBOM

CycloneDX JSON:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file bom.json --format cyclonedx
```

SPDX JSON or GitHub Dependency Graph SBOM export:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file sbom.spdx.json --format spdx
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool sbom --file github-sbom.json --format auto
```

Syft native JSON or Trivy SBOM JSON:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool syft --file syft.json --format syft
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy-cyclonedx.json --format cyclonedx
```

The command still writes the normal scanner artifacts under
`reports/scanner-results/`. For dependency inputs it also writes:

```text
reports/dependencies.json
reports/DEPENDENCY_RISK.md
```

## Normalized dependency model

`dependencies.json` contains normalized components and vulnerability records:

```json
{
  "components": [
    {
      "id": "pkg:pypi/example@1.2.3",
      "name": "example",
      "version": "1.2.3",
      "ecosystem": "pypi",
      "scope": "direct",
      "licenses": ["MIT"],
      "manifest": "requirements.txt",
      "dependency_paths": [["pkg:github/example/demo@main", "pkg:pypi/example@1.2.3"]]
    }
  ],
  "vulnerabilities": [
    {
      "id": "GHSA-...",
      "component": "pkg:pypi/example@1.2.3",
      "severity": "High",
      "fixed_version": "1.2.4",
      "source": "osv",
      "evidence_ref": "GHSA-...",
      "dependency_paths": [["root", "pkg:pypi/example@1.2.3"]]
    }
  ]
}
```

Scope values are `root`, `direct`, `transitive`, or `unknown`. Dependency paths
are preserved when the input format provides graph relationships.

## Validation and dashboard

Validate dependency artifacts together with the normal report contract:

```bash
gra-validate-report --run runs/OWNER__REPO/RUN_ID
```

When `reports/dependencies.json` exists, validation checks the dependency schema,
component count consistency, vulnerability count consistency, component ID
uniqueness, dependency path shape, and vulnerability component references.

`gra-dashboard` includes dependency counts, scope distribution, vulnerability
severity counts, and the top dependency vulnerability records.

## Safety and issue policy

SBOMs can reveal internal dependency choices, package versions, private package
names, and technology stack decisions. Keep raw SBOMs and normalized dependency
artifacts local unless publication is explicitly approved.

Dependency vulnerability records are evidence, not automatically confirmed
findings. Promote a dependency issue only after repository manifests, dependency
paths, scanner evidence, exploitability context, and reachable usage are reviewed.
License data is included for posture context and should not create security Issues
unless an explicit policy enables license compliance workflows.

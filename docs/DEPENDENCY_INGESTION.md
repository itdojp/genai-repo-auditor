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
- Trivy vulnerability JSON (`Results[].Vulnerabilities[]`) as local
  vulnerability evidence
- Grype vulnerability JSON (`matches[]`) as local vulnerability evidence

Official references:

- GitHub Dependency Graph SBOM export: https://docs.github.com/en/rest/dependency-graph/sboms
- CycloneDX specification overview: https://cyclonedx.org/specification/overview/
- SPDX 2.3 package information: https://spdx.github.io/spdx-spec/v2.3/package-information/
- SPDX 2.3 relationships: https://spdx.github.io/spdx-spec/v2.3/relationships-between-SPDX-elements/
- Trivy reporting formats: https://trivy.dev/docs/latest/configuration/reporting/
- Grype result interpretation: https://oss.anchore.com/docs/guides/vulnerability/interpreting-results/

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

Trivy or Grype vulnerability JSON:

```bash
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool trivy --file trivy.json --format json
gra-ingest --run runs/OWNER__REPO/RUN_ID --tool grype --file grype.json --format json
```

When `reports/dependencies.json` already contains SBOM-derived components,
Trivy/Grype vulnerability records are linked to those components by package URL,
package name/version/ecosystem, or equivalent deterministic package identifiers.
If a vulnerability cannot be linked deterministically, the vulnerability evidence
is still retained with an empty component reference so validation does not create
or accept dangling component links. No external advisory service is queried.

The command still writes the normal scanner artifacts under
`reports/scanner-results/`. For dependency inputs it also writes:

```text
reports/dependencies.json
reports/DEPENDENCY_RISK.md
```

For bounded high-signal cases, `gra-ingest` also appends deterministic
`TGT-DEPENDENCY-NNN` queue entries to `reports/targets.json`. A target is created
only when the normalized vulnerability is Critical or High severity, the
component is direct or transitive, and at least one dependency path is present.
The queue generation is idempotent and avoids duplicate scopes.

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

## Boundary behavior

Dependency ingestion is intentionally local, best-effort, and bounded for CI and
operator workstations. Current normalized output limits are:

- input JSON file size: 20 MiB;
- normalized components: 1,000 records;
- normalized vulnerability records: 1,000 records;
- dependency relationship edges: 5,000 records;
- dependency graph path expansion steps: 10,000 steps;
- dependency paths per component or vulnerability: 5 paths;
- dependency path depth: 12 graph nodes.

If the input file exceeds the size limit, `reports/dependencies.json` is still
written for SBOM-style imports with `status: invalid`, empty normalized arrays,
and a bounded `parse_error`. Trivy/Grype vulnerability imports that do not match
the expected scanner shape are skipped so an existing dependency posture file is
not overwritten.

When component or vulnerability inputs exceed the normalized output limits, the normalized artifact
includes a `limits` object and the summary notes that bounded output may omit
records from the raw local artifact. Operators should inspect the raw SBOM or
scanner file locally when full inventory coverage is required. Cyclic dependency
graphs are not expanded indefinitely; repeated nodes in the active path are
skipped and path depth/count limits are applied.

Malformed or partial records are normalized defensively. Unsupported license,
advisory, relationship, and vulnerability shapes are ignored or preserved as
unlinked evidence instead of producing dangling component references. Markdown
summaries escape HTML-sensitive text and apply the scanner redaction rules to
secret-like evidence before rendering.

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

`gra-targets --generate` also re-runs the dependency posture helper when
`reports/dependencies.json` already exists, so dependency review targets can be
added after the initial target queue is generated without re-ingesting the SBOM.

## Safety and issue policy

SBOMs can reveal internal dependency choices, package versions, private package
names, and technology stack decisions. Keep raw SBOMs and normalized dependency
artifacts local unless publication is explicitly approved.

Dependency vulnerability records are evidence, not automatically confirmed
findings. Promote a dependency issue only after repository manifests, dependency
paths, scanner evidence, exploitability context, and reachable usage are reviewed.
`TGT-DEPENDENCY-NNN` target entries preserve this policy: they are bounded
review work items, not confirmed findings or automatic Issue candidates.
License data is included for posture context and should not create security Issues
unless an explicit policy enables license compliance workflows.

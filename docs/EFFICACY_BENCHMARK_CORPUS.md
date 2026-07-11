# Security efficacy benchmark corpus

The efficacy corpus is a small, versioned set of synthetic ground-truth cases
for measuring defensive security-review behavior. It is intentionally separate
from [`gra-benchmark`](BENCHMARKING.md), which remains the workflow-health and
publication-safety gate for an audit run.

The corpus contract does not run a model, scanner, GitHub operation, or network
request. It provides deterministic fixture data and a fail-closed local loader
for benchmark runners. The packaged deterministic runner and scoring contract
are documented in [`EFFICACY_BENCHMARK.md`](EFFICACY_BENCHMARK.md).

## Layout

```text
benchmarks/corpus/
  corpus.schema.json
  case.schema.json
  core.json
  cases/<category>/<case-id>/
    case.json
    <fixture files>
```

`core.json` is the versioned index. Every index entry pins its `case.json` with
SHA-256. Every case manifest pins its fixture files in the same way. Case IDs
and versions are stable public identifiers. Versions use
`<release>+sha256.<64-hex-content-fingerprint>`; the loader derives the suffix
from canonical metadata and the pinned child digests. Changing ground truth,
fixture content, or the corpus index therefore requires both the affected case
version and corpus version to change rather than silently replacing a baseline.
Repository attributes pin all corpus text to LF so the raw-byte integrity hashes
remain stable across supported checkout platforms.

## Core cases

| Case | Class | Category | Defensive ground truth |
|---|---|---|---|
| `python-web/authz-001` | positive | Python web | A tenant-scoped selector omits the tenant predicate. |
| `python-web/path-001` | positive | Python web | A local path helper omits normalized-base containment. |
| `github-actions/pr-target-001` | positive | automation | A fixture workflow model combines privileged authority with untrusted content. |
| `ai-agent-mcp/tool-boundary-001` | positive | agent/tool boundary | Untrusted selection is not constrained by an allowlist or argument schema. |
| `dependency-supply-chain/dependency-path-001` | positive | supply chain | A synthetic dependency risk is reachable from a local fixture entry point. |
| `python-web/authz-control-001` | negative control | Python web | Identifier and authenticated-tenant predicates are both enforced. |
| `github-actions/pr-control-001` | negative control | automation | Reviewed base content and read-only authority are combined. |
| `ai-agent-mcp/tool-control-001` | negative control | agent/tool boundary | An explicit tool allowlist and argument schema are enforced. |

The fixtures are deliberately small and non-deployable. Automation cases are
stored as inert workflow models outside `.github/workflows/`; dependency names
and advisory IDs are synthetic; agent configurations do not contain executable
tools or endpoints.

## Case contract

A positive case records exactly one reviewable ground-truth finding:

- a bounded vulnerability class and taxonomy/CWE mapping;
- local entry point, trust boundary, sink, and affected locations;
- an expected severity range;
- a safe remediation property rather than a patch or exploit procedure.

A negative-control case records exactly one lookalike control:

- the risk class it resembles;
- the local control location;
- the property that should prevent promotion to a finding.

All cases also declare required, optional, and prohibited stages. The sets must
not overlap, and `issue-publication` is prohibited for every synthetic case.
This stage metadata describes evaluation expectations; it is not permission to
run a stage or publish a result.

## Offline validation

`lib/efficacy_corpus.py` validates the corpus with Python standard-library code:

- closed schema fields, local `$ref` contracts, and rejection of unsupported
  schema keywords;
- bounded regular files and directory-handle-relative reads that preserve path
  containment across concurrent ancestor replacement;
- index-to-manifest and manifest-to-fixture SHA-256 integrity;
- content-bound case and corpus versions that fail when content changes without
  a corresponding version update;
- positive/control counts, case identity, severity ordering, and source-line
  references;
- non-overlapping stage expectations and the Issue-publication prohibition;
- absence of live-network URLs, credential markers, and external execution
  helpers across the index, case manifests, and fixtures, plus rejection of
  executable fixture files and oversized content.

A local source checkout can verify the contract without network access:

```bash
python3 -m unittest tests.test_efficacy_corpus -v
```

List or run the deterministic reference baseline without changing
`gra-benchmark` semantics:

```bash
gra-efficacy-benchmark --list
gra-efficacy-benchmark
```

## Adding or changing a case

1. Add a non-deployable fixture under `benchmarks/corpus/cases/<category>/<id>/`.
2. Add `case.json` using `case.schema.json`; keep descriptions defensive and
   avoid payloads, executable workflows, real vulnerable package coordinates,
   credentials, endpoints, or private-repository material.
3. Compute fixture SHA-256 values and add the sorted file references.
4. Recompute the case content-version suffix, then add the case to sorted
   `core.json` and pin the complete manifest SHA-256.
5. Recompute the corpus content-version suffix after all index entries are final.
6. Update packaging inventory and this case table.
7. Run the corpus tests twice and confirm the loaded objects are identical.
8. Request human security review for any new vulnerability class or fixture.

Existing case IDs must not be repurposed. If ground truth changes materially,
increment the case version and corpus version and document why.

## Interpretation limits

The corpus is too small and synthetic to support claims about overall product,
model, scanner, language, framework, or real-world vulnerability-detection
performance. A result on these cases is regression evidence for the specified
fixture versions only. It must not be presented as proof of production recall,
security coverage, exploitability assessment quality, or comparative model
superiority.

Do not publish detailed case execution traces automatically. Any external
summary must remain aggregate, identify the corpus/configuration versions, and
receive human review.

Configuration comparisons, optional worker rows, permitted wording, and
publication approval are governed by
[`EFFICACY_CLAIMS_AND_PUBLICATION.md`](EFFICACY_CLAIMS_AND_PUBLICATION.md).

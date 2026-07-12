# Public efficacy and operational evaluation

## Scope and evidence separation

This report combines three evidence layers without treating them as interchangeable:

1. deterministic results from the public synthetic corpus;
2. aggregate-only private holdout results, when an approved result exists; and
3. public-safe operational counts from the authorized ITDO_ERP4 dogfood campaign.

The report contains no private fixture content, target code, finding title or
body, scanner record, prompt, transcript, patch, credential, local absolute
path, or private run identifier. A missing layer remains missing; another layer
is never substituted for it.

## Methodology and versions

| Item | Evaluated value | Determinism | Public source |
|---|---|---|---|
| GenAI Repo Auditor | Version 0.4.0 at source commit 960dd1de42c129a524acbb2437f3a4406024bda9 | Version and source are fixed | VERSION and repository history |
| Public corpus | genai-repo-auditor-synthetic-core, version 1.1.0+sha256.33c20915076017869a6b99e0552be59f40aa05d701b61e4572d4d449a4fa6146, core suite, 20 cases | Deterministic, content-bound | benchmarks/corpus/core.json |
| Reference detector | synthetic-reference-rules-v2 | Deterministic | gra-efficacy-benchmark report contract |
| Full-signal configuration | reference-review-all-signals-v1; stage fixture-reference-review | Deterministic | EFFICACY_CLAIMS_AND_PUBLICATION.md |
| Severity-gated configuration | reference-review-high-severity-gate-v1; stages fixture-reference-review and high-severity-review-gate | Deterministic | EFFICACY_CLAIMS_AND_PUBLICATION.md |
| Worker/model row | Not executed or included | Non-deterministic if executed | No approved worker result exists for this report |
| Private holdout | Protocol available; no approved aggregate result exists | Would be non-deterministic when model-backed | PRIVATE_HOLDOUT_PROTOCOL.md |
| ITDO_ERP4 dogfood | Three reviewed target categories: authorization/user, financial state transition, and agent-mediated authorization/audit | Mixed: agent research non-deterministic; aggregate reporting deterministic | ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md |
| Scanner execution | Two adapters planned; none executed; no lead artifact ingested | Not measured | ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md |

The public corpus command was run twice from the stated source commit with the
same core suite and output format. Both JSON outputs and both Markdown outputs
were byte-identical. The deterministic comparison used the same corpus, case
selection, detector, command version, and output format. Only the recorded
workflow stage gate differed.

No worker profile, model, effort, or agent/worker CLI version is reported because no
worker-backed row was executed. Scanner version checks and immutable-image
execution were also not performed; configured scanner image pins are not
presented as execution evidence.

## Public synthetic corpus

These are synthetic regression results for the exact corpus version above.
They measure agreement between pinned synthetic fixtures, reference rules, and
the scoring pipeline. They are not product-wide precision, recall, severity
accuracy, language support, framework support, production readiness, or model
quality.

### Full-signal deterministic reference row

| Metric | Value |
|---|---:|
| Selected cases | 20 |
| Positive cases / negative controls | 10 / 10 |
| TP / FP / FN / TN | 10 / 0 / 0 / 10 |
| Precision | 1.000000 |
| Recall | 1.000000 |
| F1 | 1.000000 |
| Severity agreement | 10 / 10 (1.000000) |
| Target coverage | 20 / 20 (1.000000) |
| Human-review-required cases | 10 |

### Fixed configuration comparison

| Configuration | Deterministic | Stage difference | TP / FP / FN / TN | Precision | Recall | F1 | Human review |
|---|---|---|---:|---:|---:|---:|---:|
| reference-review-all-signals-v1 | Yes | fixture-reference-review | 10 / 0 / 0 / 10 | 1.000000 | 1.000000 | 1.000000 | 10 |
| reference-review-high-severity-gate-v1 | Yes | adds high-severity-review-gate | 7 / 0 / 3 / 10 | 1.000000 | 0.700000 | 0.823529 | 7 |

Both rows covered 20 of 20 cases. Severity agreement was 10 of 10 for the
full-signal row and 7 of 7 for the severity-gated row. The delta demonstrates
that the comparison machinery detects the pinned gate difference. It does not
establish that either configuration is a production security-review strategy
or superior to a scanner, model, provider, or full harness.

## Private holdout

No approved private holdout aggregate exists for this report. The repository
contains a validation protocol and aggregate-only schemas, but protocol
availability is not an evaluation result. Therefore this report publishes no
holdout TP, FP, FN, TN, rates, variance, control outcome, model, effort, prompt,
worker, or adjudication number.

A later revision may add only a separately approved, schema-valid aggregate.
It must not include private fixture text, paths, case implementation details,
prompts, transcripts, raw responses, or adjudication evidence.

## ITDO_ERP4 operational dogfood

The operational layer measures workflow use and review burden, not production
recall. All values below are copied from the reviewed public-safe second-pass
summary.

| Measure | Public-safe value |
|---|---:|
| Targets generated / selected / deep-researched | 47 / 3 / 3 |
| Targets left queued | 44 |
| Candidate findings after human review | 4 Medium |
| Status after human review | 1 Confirmed / 3 Probable |
| Downgraded or invalidated | 0 |
| Critical or High candidates | 0 |
| Scanner adapters planned / executed | 2 / 0 |
| Authorized scanner/external artifacts ingested / normalized scanner leads triaged | 0 / 0 |
| Workflow interruptions / checkpoint resumes | 1 / 1 |
| Approximate hands-on operator review time | 45 minutes |
| Workflow benchmark gates | 7 passed / 0 warnings / 0 failed |
| Evidence graph | 55 nodes / 18 edges |
| Issue dry-run would-create / warnings / published | 0 / 0 / 0 |

The public source records adversarial validation and chain, proof, and
remediation generation as not executed or not required. It does not publish a
patch-validation count, so this report does not supply one. Scanner execution
was not attempted because safe local prerequisites were absent. Missing scanner
evidence is not a clean scan. No target-specific candidate is disclosed here,
and zero published target Issues does not mean zero vulnerabilities.

## Human adjudication

Public synthetic positives are flagged for human review by the deterministic
runner; the count is not evidence that a human independently validated each
synthetic prediction during this report build.

For the operational dogfood layer, an independent source-level reviewer checked
all four candidates against bounded repository context and retained their
generated status and severity. Approximate hands-on operator review time was
collected from the campaign record and excludes model execution waits. Three
candidate decisions remain dependent on unavailable operational configuration
or lifecycle context; this uncertainty is intentionally reported only as an
aggregate.

## Supported conclusions

The bounded evidence supports these conclusions:

- fixed public synthetic inputs and deterministic reference configurations
  produced byte-stable reports at the stated source and corpus versions;
- the comparison pipeline detected a fixed, explicitly recorded severity-gate
  stage difference;
- the local-first operational workflow preserved private target artifacts,
  supported one checkpoint resume, and produced reviewed aggregate reports;
- scanner execution and Issue publication remained explicit gates rather than
  automatic side effects; and
- human review remained necessary for synthetic signals and real-repository
  candidates.

The evidence does not support production recall or precision, guaranteed
discovery, complete coverage, release safety, autonomous finding validation,
scanner or model superiority, or a claim that ITDO_ERP4 has no additional
security issues.

## Approval and traceability

Every number in this report maps to one of the following bounded
sources:

- the reproducible deterministic commands in
  EVALUATION_REPRODUCTION.md;
- the public corpus manifest and closed benchmark/comparison report contracts;
- the reviewed ITDO_ERP4 second-dogfood aggregate summary; or
- an explicit zero/not-executed state recorded in those sources.

Permitted wording, prohibited stronger wording, limitations, and required
approvers are recorded in CLAIM_EVIDENCE_MATRIX.md. This report is a draft
until its pull request receives security/disclosure and maintainer review; the
merge record is the publication approval record.

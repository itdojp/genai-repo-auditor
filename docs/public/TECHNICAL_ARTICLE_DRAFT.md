# Building and measuring a local-first AI AppSec audit harness

> Editorial note: bracketed claim tags link to
> [`ARTICLE_CLAIM_SOURCES.md`](ARTICLE_CLAIM_SOURCES.md) for disclosure review.
> They may remain as endnote references or be removed during final layout only
> after the destination publication preserves equivalent source links. No
> external publication URL has been approved yet.

AI-assisted repository review is easy to overstate. Generating observations is only one part of the job. The harder engineering problem is to keep evidence handling bounded, make deterministic and model-backed steps distinguishable, and stop publication from becoming an accidental side effect.

In the public documentation, GenAI Repo Auditor is presented as a local-first AppSec audit harness: generated target artifacts stay local by default, and only reviewed aggregate documentation is prepared for public use. [A01](ARTICLE_CLAIM_SOURCES.md) The same documentation treats issue creation as a separate approval step, not as a routine consequence of running an audit. [A02](ARTICLE_CLAIM_SOURCES.md) At the public-method level, the operating model is vendor-neutral: compatible local agents can be orchestrated through `gra-*` workflows without binding the published method to one model vendor. [A16](ARTICLE_CLAIM_SOURCES.md)

The harness model is staged rather than monolithic:

```text
prepare -> recon -> target queue -> research -> validation
  -> scanner triage -> defensive chain reasoning -> safe proof planning
  -> metrics / benchmark / evidence graph -> human review -> issue planning
```

That sequence matters because it separates exploratory work from validation and disclosure control. The public workflow description is a capability map, not a statement that every run executes every stage. [A03](ARTICLE_CLAIM_SOURCES.md)

## Control plane, evidence providers, and human decisions

The control plane owns the repository contracts, staged commands, deterministic
validators, and publication gates. Compatible AI workers can contribute bounded
research artifacts, while deterministic scanners can contribute evidence only
through explicit planning, execution, normalization, and provenance checks.
Neither source becomes security authority by itself: validation status and
publication eligibility remain separate decisions, and a human reviewer owns
the disclosure boundary. [A18](ARTICLE_CLAIM_SOURCES.md)

For routine operation, `gra-run` makes that separation visible. An operator
uses the declarative plan-review-execute-resume path: prepare inputs, create and
review a plan, execute approved steps, and resume the same profile checkpoint
after an interruption.
A checkpoint is execution state, not evidence that a finding is valid, and it
does not authorize issue publication. [A19](ARTICLE_CLAIM_SOURCES.md)

Adversarial validation, defensive chain reasoning, safe proof planning, and
remediation candidates are also bounded stages. Their artifacts are local
review inputs; proof material must remain non-destructive and remediation
candidates require independent validation before adoption. [A20](ARTICLE_CLAIM_SOURCES.md)

## What public measurement means here

The publication package separates evidence into deterministic public synthetic results, aggregate-only private holdout results when an approved result exists, and public-safe operational counts from authorized dogfood campaigns. In the current package, only the deterministic public corpus layer and the public-safe operational layer contain approved results. No approved private holdout aggregate is published, and no worker/model comparison row was executed for this report. [A07](ARTICLE_CLAIM_SOURCES.md)

That boundary is important because it constrains what the article can claim. The public material supports statements about fixed-input repeatability, workflow gating, review burden, and disclosure control. It does not support claims about production recall, complete coverage, vulnerability absence, autonomous validation, or model superiority. [A15](ARTICLE_CLAIM_SOURCES.md)

## Public measurements

The package uses three evidence layers. Their counts are not interchangeable.

### Deterministic synthetic regression

The synthetic rows test the scoring and comparison pipeline against pinned,
repository-owned cases. “Full-signal” means the reference configuration consumes
all fixture signals. [A05](ARTICLE_CLAIM_SOURCES.md) “Severity-gated” names a second
pinned configuration that adds one review gate; it is a regression contrast, not
a recommended production policy. [A06](ARTICLE_CLAIM_SOURCES.md)

| Public surface | Bound result | Interpretation boundary |
|---|---|---|
| Deterministic synthetic regression | At GenAI Repo Auditor version 0.4.0 on source commit `960dd1de42c129a524acbb2437f3a4406024bda9`, the public synthetic corpus version `1.1.0+sha256.33c20915076017869a6b99e0552be59f40aa05d701b61e4572d4d449a4fa6146` covered 20 cases. Two repeated runs with the same command, corpus, case selection, detector, and output format produced byte-identical JSON and Markdown outputs. [A04](ARTICLE_CLAIM_SOURCES.md) | Fixed-configuration stability only; no implication for model-backed runs. |
| Full-signal reference row | On that fixed 20-case corpus, the full-signal reference row reported TP/FP/FN/TN of 10/0/0/10. [A05](ARTICLE_CLAIM_SOURCES.md) | Synthetic regression control only; not a product-wide accuracy claim. |
| Severity-gated reference row | On the same fixed corpus, the severity-gated reference row reported TP/FP/FN/TN of 7/0/3/10, showing that the comparison pipeline detected the pinned review-gate difference. [A06](ARTICLE_CLAIM_SOURCES.md) | Pinned stage-difference detection only; not a superiority claim. |

### Workflow-health benchmark

A workflow-health benchmark asks whether required contracts and reporting stages
remain operable. Its gates do not measure how many real vulnerabilities a system
would discover. [A08](ARTICLE_CLAIM_SOURCES.md) An explicit empty findings artifact
is useful here because it lets downstream validators distinguish “reviewed and
empty” from “missing or failed.” [A08](ARTICLE_CLAIM_SOURCES.md)

| Public surface | Bound result | Interpretation boundary |
|---|---|---|
| Self-dogfood workflow check | The public self-dogfood summary shows a no-confirmed-finding workflow that still exercised validation, metrics, benchmark, evidence graph, dashboard, and issue dry-run stages. [A08](ARTICLE_CLAIM_SOURCES.md) | Bounded workflow exercise only; not finding publication. |
| Self-dogfood headline counts | In that public self-dogfood summary, 7 benchmark gates passed and 0 Issues were created from audit output. [A09](ARTICLE_CLAIM_SOURCES.md) | One bounded-run signal only; not a general benchmark. |

### Operational dogfood

Operational dogfood records what happened in an authorized repository review:
queue narrowing, human adjudication, omitted evidence, checkpoint recovery, and
publication controls. It is neither a synthetic accuracy row nor a production
performance estimate.

| Public surface | Bound result | Interpretation boundary |
|---|---|---|
| Business-application dogfood scope reduction | In the reviewed second ITDO_ERP4 campaign, the target queue produced 47 generated targets, exactly 3 selected targets, 3 deep-researched targets, and 44 queued targets left for later work. [A11](ARTICLE_CLAIM_SOURCES.md) | First-wave queue narrowing only; not complete coverage. |
| Business-application dogfood outcome | After human review, the same campaign retained 4 Medium candidates with status distribution 1 Confirmed and 3 Probable, with 0 downgraded or invalidated. [A12](ARTICLE_CLAIM_SOURCES.md) | Aggregate reviewed counts only; not public finding descriptions or evidence of no additional issues. |
| Operational burden and resilience | The second ITDO_ERP4 campaign recorded 1 workflow interruption, 1 checkpoint resume, and approximately 45 minutes of hands-on operator review time excluding model waits. [A13](ARTICLE_CLAIM_SOURCES.md) | One authorized campaign only; not a representative benchmark. |
| Scanner and publication gates | In that same campaign, 2 scanner adapters were planned, 0 were executed, 0 scanner or external artifacts were ingested, 0 normalized scanner leads were triaged, and Issue publication remained dry-run only with 0 would-create, 0 warnings, and 0 published target Issues. [A14](ARTICLE_CLAIM_SOURCES.md) | Missing-state and publication-gate counts only; not a clean-scan or zero-risk conclusion. |

## Self-dogfood: measuring the harness without publishing findings

The self-dogfood material is useful because it treats workflow evaluation as a first-class engineering activity. The public case study focuses on local artifact generation, deterministic reporting stages, and publication-preview behavior instead of trying to turn every internal signal into a public security claim. The public-safe output remains limited to bounded counts and product lessons.

One documented design detail is the explicit empty findings artifact. A no-confirmed-finding run still benefits from explicit structure. The self-dogfood package used an explicit empty findings artifact so that validation, metrics, benchmark, evidence graph, dashboard, and dry-run issue planning could be exercised without inventing findings or leaking local report content.

## ITDO_ERP4: measuring a realistic business-application review

The public ITDO_ERP4 material shows why a business application is a realistic operational test. The documented review surfaces include authorization and user boundaries, approval and financial state transitions, agent-mediated authorization and audit paths, attachments and storage, CI and supply-chain controls, and operations readiness. [A10](ARTICLE_CLAIM_SOURCES.md)

In the public second-pass aggregate, the target queue comes first, human narrowing comes second, and bounded deep research comes third.

The same material also shows why omission states should be explicit. Scanner execution did not happen because approved local prerequisites were absent, and that absence was reported directly. Publication also stayed in dry-run mode. In the published summaries, both choices keep missing evidence and publication control explicit.

## Design rules that emerge from the public package

The current publication package points to a small set of design rules for AI-assisted AppSec work:

1. Keep generated artifacts local unless a disclosure process approves exact public wording.
2. Separate deterministic measurement from model-backed exploration.
3. Use target queues to reduce broad repository surfaces before deep research.
4. Treat scanners and issue publication as explicit gates, not automatic side effects.
5. Preserve human review at the boundary where candidate findings become public statements.

These are not abstract governance slogans. They are the common pattern across the deterministic corpus evaluation, the self-dogfood workflow check, and the ITDO_ERP4 campaign summary.

## Measured limitations and next steps

The current evidence leaves deliberate gaps. There is no approved private
holdout aggregate, no worker/model comparison row, and no executed scanner row
in the aggregate report. The synthetic corpus remains a regression control, and
the operational observations come from bounded campaigns rather than a
representative production sample. [A07](ARTICLE_CLAIM_SOURCES.md)

The next measurement work should therefore preserve the same separation: add a
private-holdout aggregate only after disclosure approval, execute scanner or
worker-assisted rows only with recorded prerequisites and versions, expand the
public corpus without converting it into a production proxy, and repeat
operational dogfood with comparable review-burden fields. External article and
video publication remains a separate human editorial and disclosure decision.

## What this article does not claim

This article does not claim that the harness provides production-wide precision or recall, complete coverage, absence of vulnerabilities, automatic remediation, autonomous finding validation, or superior results from any model, provider, scanner, or workflow. It makes a narrower point: the public package documents explicit measurement boundaries and controlled publication paths around AI-assisted repository review. [A17](ARTICLE_CLAIM_SOURCES.md)

## Suggested companion materials

For publication packaging, pair this article with the
[public efficacy and operations report](../evaluation/PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md),
the [claim-evidence matrix](../evaluation/CLAIM_EVIDENCE_MATRIX.md), the
[public self-dogfood case study](../dogfood/PUBLIC_SELF_DOGFOOD_CASE_STUDY.md),
the [public ITDO_ERP4 case study](../dogfood/PUBLIC_ITDO_ERP4_CASE_STUDY.md),
and the
[disclosure-and-publication policy](../DISCLOSURE_AND_PUBLICATION_POLICY.md).
External publication links can be added only after the destination and exact URL
have been reviewed and approved.

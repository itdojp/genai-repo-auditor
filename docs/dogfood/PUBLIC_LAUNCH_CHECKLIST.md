# Public launch checklist for dogfood recognition

This checklist prepares public recognition material for the GenAI Repo Auditor
dogfood campaign. It is intentionally conservative: public claims must be tied
to reviewed dogfood evidence, local-first safety boundaries, and human-approved
wording.

Use it with:

- [`PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`](PUBLIC_SELF_DOGFOOD_CASE_STUDY.md)
- [`PUBLIC_ITDO_ERP4_CASE_STUDY.md`](PUBLIC_ITDO_ERP4_CASE_STUDY.md)
- [`BLOG_OUTLINE_AI_APPSEC_HARNESS.md`](BLOG_OUTLINE_AI_APPSEC_HARNESS.md)
- [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)
- [`README_POSITIONING_NOTES.md`](README_POSITIONING_NOTES.md)
- [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)
- [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md)

## Launch readiness gates

| Gate | Required check | Evidence source | Owner decision |
|---|---|---|---|
| Public-safe case studies | Self-dogfood and ITDO_ERP4 case studies are reviewed and linked. | `PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`, `PUBLIC_ITDO_ERP4_CASE_STUDY.md` | Human editorial approval. |
| Conservative positioning | Claims describe a local-first, vendor-neutral AppSec audit harness. | `README_POSITIONING_NOTES.md` | Product / maintainer approval. |
| Disclosure boundary | Public text excludes private findings, target evidence, scanner records, transcripts, issue bodies, and remediation content. | Disclosure policy and case-study checks. | Security reviewer approval. |
| Evidence-backed counts | Any count in public material maps to a reviewed public-safe case-study count. | Case-study sanitized metrics tables. | Maintainer approval. |
| Demo safety | Demo uses help output, sanitized artifacts, or an operator-owned repository only. | `DEMO_SCRIPT.md` | Demo owner approval. |
| README linkage | README links to public-safe dogfood materials without overstating capability. | `README.md` | Maintainer approval. |
| CI / docs validation | Documentation consistency and manifest tests pass. | Local validation log / CI. | Release owner approval. |

Do not publish until every gate has an owner decision.

## Claim review checklist

Public statements may say:

- GenAI Repo Auditor is a local-first, vendor-neutral AppSec audit harness.
- The harness orchestrates AI agents, deterministic scanners, evidence
  validation, defensive chain reasoning, remediation candidates, human review,
  and controlled GitHub Issue publication across authorized repositories.
- Dogfood runs demonstrated target queueing, validation, benchmark, evidence
  graph, issue-publication dry-run, and public-safe reporting boundaries.
- Public dogfood materials contain workflow narrative and aggregate counts only.

Public statements must not say or imply:

- replacement for managed frontier-model security products;
- unsupervised security authority;
- guaranteed vulnerability discovery;
- exploit generation as a product outcome;
- automatic fixes without maintainer review;
- approval to publish target-repository security details.

## Public-safe content inventory

| Material | Purpose | Must include | Must omit |
|---|---|---|---|
| Blog outline | Editorial structure for a technical article. | Problem, harness model, dogfood evidence, safety boundary, next steps. | Finding bodies, target code, private evidence, scanner records. |
| Demo script | Live or recorded demo runbook. | Setup checks, safe narration, sanitized outputs, stop conditions. | Local artifact contents, credentials, private target details. |
| README positioning notes | Maintainer guidance for README wording. | Conservative claim, proof points, cautions, suggested excerpt. | Capability exaggeration and unsupported comparisons. |
| Launch checklist | Publication gate record. | Owner decisions, safety checks, validation requirements. | Private run ledger content. |

## Pre-publication questions

Before sharing externally, answer these in the launch record:

1. Which audience will receive the material: README readers, blog readers, demo
   attendees, maintainers, or security reviewers?
2. Which exact dogfood case-study sections support each technical claim?
3. Are all counts aggregate, reviewed, and free of target commit hashes or local
   run identifiers?
4. Would any sentence require disclosure approval under
   [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)?
5. If a demo is live, which repository is authorized and who owns the retention
   decision for local artifacts?
6. Has a reviewer confirmed that security-impacting target details are routed
   privately first?

## Stop conditions

Stop public launch preparation and request review if:

- a claim depends on unreviewed local artifacts;
- a proposed screenshot shows local report contents, target code, scanner
  records, transcripts, dashboard details, or issue preview text;
- a count cannot be traced to an approved public-safe source;
- wording implies autonomous security authority or unsupported equivalence to
  another product;
- the demo repository, target commit, or artifact-retention decision is unclear;
- publication would bypass the disclosure policy.

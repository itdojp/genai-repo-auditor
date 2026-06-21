# README positioning notes for dogfood recognition

These notes help maintainers update README, release notes, blog posts, and demo
material after the dogfood campaign. They are not marketing claims by themselves;
they are wording guidance tied to public-safe dogfood evidence.

## Recommended conservative claim

Use this claim, or a shorter form that preserves its boundaries:

> GenAI Repo Auditor is a local-first, vendor-neutral AppSec audit harness for
> orchestrating AI agents, deterministic scanners, evidence validation,
> defensive chain reasoning, remediation candidates, human review, and controlled
> GitHub Issue publication across authorized repositories.

Short README-compatible form:

> Local-first, vendor-neutral AppSec audit harness for authorized repository
> review, evidence validation, human-reviewed remediation planning, and
> controlled GitHub Issue publication.

## Proof points from dogfood

| Proof point | Public-safe evidence |
|---|---|
| Local-first boundary | Self-dogfood and ITDO_ERP4 case studies keep generated run artifacts outside Git. |
| AppSec harness model | Workflows include prepare, recon, target queue, research, validation, scanner triage, metrics, benchmark, evidence graph, and issue dry-run stages. |
| Human-reviewed publication | Both case studies state that no GitHub Issues were created from audit output. |
| Business application applicability | ITDO_ERP4 case study covers ERP-style RBAC, approval, finance, agent-mediated, attachment, CI, and operations surfaces. |
| Product feedback loop | Self-dogfood backlog converts tool friction into product-improvement candidates. |

## Wording to prefer

- “AI-assisted review” rather than “autonomous security decision.”
- “Review leads” rather than “confirmed vulnerabilities” until validation and
  human review are complete.
- “Remediation candidates” rather than “automatic fixes.”
- “Issue dry-run preview” rather than “publication plan” unless a plan artifact
  has been generated and reviewed.
- “Authorized repositories” rather than broad public scanning.
- “Local/private by default” when discussing generated artifacts.

## Wording to avoid

Avoid wording that suggests:

- equivalence to managed frontier-model security offerings;
- guaranteed discovery of novel vulnerabilities;
- autonomous publication of findings;
- exploit generation as a public product outcome;
- automatic patching without maintainer review;
- permission to expose target-repository security details in public Issues.

## Suggested README dogfood paragraph

```markdown
GenAI Repo Auditor has been dogfooded on this repository and on a scoped
business-application repository review. The public case studies describe the
workflow, target queueing, validation, metrics, benchmark, evidence graph, and
issue-publication dry-run controls using aggregate counts only. Generated run
artifacts, scanner records, target evidence, transcripts, dashboards, and issue
body text remain local/private by default.
```

Suggested links:

- [`docs/dogfood/PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`](PUBLIC_SELF_DOGFOOD_CASE_STUDY.md)
- [`docs/dogfood/PUBLIC_ITDO_ERP4_CASE_STUDY.md`](PUBLIC_ITDO_ERP4_CASE_STUDY.md)
- [`docs/dogfood/PUBLIC_LAUNCH_CHECKLIST.md`](PUBLIC_LAUNCH_CHECKLIST.md)
- [`docs/DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)

## Claim-to-evidence mapping

| README claim | Required evidence before publication |
|---|---|
| “local-first” | Public text states generated artifacts remain under local run storage or outside Git. |
| “vendor-neutral” | Public text avoids model-provider lock-in claims and focuses on compatible local agents. |
| “evidence validation” | Public text links to validation, metrics, benchmark, or evidence graph stages. |
| “controlled Issue publication” | Public text explains dry-run preview and human approval requirements. |
| “business-application review” | Public text links to ITDO_ERP4 scope and public-safe case study, not to private evidence. |

## Editorial approval checklist

Before updating README or release material, confirm:

- the sentence can be supported by a public-safe case-study section;
- the wording does not require private evidence to understand;
- local-first and disclosure boundaries remain visible near capability claims;
- any count is aggregate and reviewed;
- no target commit hash, local run identifier, scanner record, transcript,
  dashboard detail, issue body text, or remediation content is included.

# Blog outline: building a local-first AI AppSec audit harness

This outline is for a public technical article about GenAI Repo Auditor after the
self-dogfood and ITDO_ERP4 dogfood case studies. It is an editorial plan, not a
finding report. Keep the final article conservative, evidence-backed, and
safe for public review.

## Working title options

1. `Building a local-first AI AppSec audit harness`
2. `Dogfooding GenAI Repo Auditor on itself and a business application`
3. `From AI review output to controlled security reporting`

## Thesis

GenAI Repo Auditor is a local-first, vendor-neutral AppSec audit harness for
orchestrating AI agents, deterministic scanners, evidence validation, defensive
chain reasoning, remediation candidates, human review, and controlled GitHub
Issue publication across authorized repositories.

The dogfood campaign demonstrates the harness pattern: AI-assisted review is
useful when it is bounded by local artifact handling, deterministic validation,
conservative disclosure policy, and human review.

## Audience

- application-security engineers evaluating AI-assisted repository review;
- maintainers who need safe issue-publication workflows;
- platform teams building local-first security automation;
- technical leaders who need precise capability claims.

## Article structure

### 1. Problem statement

Repository security review increasingly combines human expertise, static
scanner evidence, and AI-assisted reasoning. The hard part is not only generating
observations; it is controlling scope, evidence quality, publication, and
handoff.

Key message: the harness treats AI output as review input, not as final security
authority.

### 2. Harness model

Explain the workflow at a high level:

```text
prepare -> recon -> target queue -> research -> validation
  -> scanner triage -> defensive chain reasoning -> safe proof planning
  -> metrics / benchmark / evidence graph -> human review -> issue planning
```

Stress that generated artifacts stay local unless an explicit disclosure process
approves exact public wording.

### 3. Self-dogfood evidence

Use [`PUBLIC_SELF_DOGFOOD_CASE_STUDY.md`](PUBLIC_SELF_DOGFOOD_CASE_STUDY.md) as
the public-safe source.

Suggested points:

- the self run exercised local artifact generation and deterministic reporting;
- no Issues were created from audit output;
- benchmark, metrics, and evidence graph stages created useful review signals;
- product improvements were identified without publishing vulnerability details.

Do not quote or summarize local finding content.

### 4. ITDO_ERP4 business-application evidence

Use [`PUBLIC_ITDO_ERP4_CASE_STUDY.md`](PUBLIC_ITDO_ERP4_CASE_STUDY.md) as the
public-safe source.

Suggested points:

- business workflows such as RBAC, approvals, finance, agent-mediated writes,
  attachments, and operations are realistic AppSec review surfaces;
- the target queue reduced a broad ERP-style surface to a bounded first wave;
- scanner artifact absence was recorded explicitly rather than invented;
- issue dry-run produced preview counts without publication.

Do not include target-specific finding narratives, code excerpts, or scanner
record details.

### 5. Safety and disclosure model

Reference [`../DISCLOSURE_AND_PUBLICATION_POLICY.md`](../DISCLOSURE_AND_PUBLICATION_POLICY.md)
and [`../DOGFOOD_REPORTING.md`](../DOGFOOD_REPORTING.md).

Explain:

- public repositories are not automatically safe publication targets;
- sensitive target candidates use private reporting first;
- `gra-issues --dry-run` is a preview, not approval;
- public material should use aggregate counts and workflow narrative only.

### 6. Practical takeaways

- Treat AI agents as bounded reviewers inside a harness.
- Keep scanner and AI artifacts local by default.
- Use target queues to manage broad repositories.
- Validate structure before publication planning.
- Separate product-improvement Issues from target-repository security reports.
- Require human review for remediation candidates and public issue text.

### 7. Next steps

Point readers to:

- `README.md` for setup;
- [`../WORKFLOW_OVERVIEW.md`](../WORKFLOW_OVERVIEW.md) for architecture;
- [`../LOCAL_INSTALL_AND_AUDIT.md`](../LOCAL_INSTALL_AND_AUDIT.md) for first use;
- the two public dogfood case studies for evidence-backed examples.

## Claims table

| Claim | Support | Allowed public wording |
|---|---|---|
| Local-first | Both case studies keep generated artifacts local. | “Audit artifacts are local/private by default.” |
| Vendor-neutral harness | Project commands and docs are model-provider neutral. | “Compatible local agents can be orchestrated through `gra-*` workflows.” |
| Evidence validation | Validation, benchmark, metrics, and graph stages were exercised. | “Deterministic checks provide review checkpoints.” |
| Controlled issue publication | Dry-run planning was used and no audit-output Issues were created. | “Issue publication is gated by human review and policy.” |
| Business AppSec applicability | ITDO_ERP4 scope covers ERP-style business workflows. | “The harness can organize review of realistic business-application surfaces.” |

## Editorial guardrails

The final article must not:

- imply unsupervised security authority;
- promise vulnerability discovery;
- describe exploit construction as a product outcome;
- claim automatic remediation without maintainer validation;
- compare the project as equivalent to managed frontier-model security products;
- include private findings, target evidence, scanner records, local run IDs,
  target commit hashes, transcripts, dashboard contents, or issue body text.

## Review before publication

Run the launch checklist before publication. A security reviewer should verify
that the article has only workflow narrative, aggregate dogfood counts, public
document links, and conservative claims.

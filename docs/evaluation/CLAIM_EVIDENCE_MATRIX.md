# Claim-evidence matrix

## Decision rule

This matrix controls public wording derived from the aggregate evaluation. Each
claim is permitted only in the exact or narrower form shown, after both required
review roles approve the pull request containing the claim. Before merge, every
row is pending. On the default branch, the merge record and attached review
history record the approval decision.

| ID | Exact permitted wording | Evidence | Determinism | Limitation / uncertainty | Prohibited stronger wording | Required approvers |
|---|---|---|---|---|---|---|
| CLM-001 | Fixed public synthetic inputs produced byte-identical reports in two repeated runs at the stated source and corpus versions. | [Synthetic results](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#public-synthetic-corpus); [reproduction](EVALUATION_REPRODUCTION.md) | Deterministic | Applies only to the fixed command, corpus, selection, and format. | All audits or model runs are reproducible. | Security/disclosure reviewer; maintainer |
| CLM-002 | The evaluated workflow keeps generated target artifacts local by default and publishes only reviewed aggregate documentation. | [Evidence separation](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#scope-and-evidence-separation); [reporting policy](../DOGFOOD_REPORTING.md) | Mixed | Local-first is a handling policy and observed campaign behavior, not proof of host confidentiality. | No private data can leave the host. | Security/disclosure reviewer; maintainer |
| CLM-003 | The full-signal reference row produced TP/FP/FN/TN of 10/0/0/10 on the named synthetic corpus version. | [Full-signal row](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#full-signal-deterministic-reference-row) | Deterministic | Synthetic fixtures and reference rules are regression controls. | Product precision and recall are 100 percent. | Security/disclosure reviewer; maintainer |
| CLM-004 | The severity-gated reference row produced TP/FP/FN/TN of 7/0/3/10 on the same fixed synthetic corpus. | [Fixed comparison](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#fixed-configuration-comparison) | Deterministic | Demonstrates one pinned stage difference only. | The full-signal workflow is superior to another product, scanner, model, or provider. | Security/disclosure reviewer; maintainer |
| CLM-005 | The second dogfood campaign required approximately 45 minutes of hands-on operator review, excluding model waits. | [Second dogfood aggregate](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md); [operational table](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#itdoerp4-operational-dogfood) | Non-deterministic observation | One authorized campaign; not a representative cost or latency benchmark. | Typical audits complete in 45 minutes. | Security/disclosure reviewer; maintainer |
| CLM-006 | Two scanner adapters were planned and zero were executed because approved local prerequisites were absent. | [Scanner decision](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md#scanner-and-external-evidence-decision); [operational table](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#itdoerp4-operational-dogfood) | Deterministic aggregate of an operational decision | No scanner efficacy or clean-scan conclusion is available. | Scanner integration found no issues or covers the target. | Security/disclosure reviewer; maintainer |
| CLM-007 | Issue publication remained dry-run only and created zero target Issues in the campaign. | [Second dogfood aggregate](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md#aggregate-results); [operational table](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#itdoerp4-operational-dogfood) | Deterministic aggregate | Publication control does not validate or invalidate a candidate. | The system autonomously publishes only valid findings. | Security/disclosure reviewer; maintainer |
| CLM-008 | A temporary provider usage limit was recovered through one saved workflow checkpoint without repeating successful recon. | [Executed workflow](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md#executed-workflow); [operational table](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#itdoerp4-operational-dogfood) | Non-deterministic observation | One interruption; not a general reliability rate. | All provider failures recover automatically. | Security/disclosure reviewer; maintainer |
| CLM-009 | No approved private holdout aggregate is included in this report. | [Private holdout absence](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#private-holdout) | Deterministic absence statement | Protocol availability is not a result. | Public-corpus results validate private or production performance. | Security/disclosure reviewer; maintainer |
| CLM-010 | Worker/model comparison was not executed for this report. | [Methodology and versions](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md#methodology-and-versions) | Deterministic absence statement | No model, effort, CLI-version, or worker-performance conclusion is available. | One model, worker, or provider outperforms another. | Security/disclosure reviewer; maintainer |

## Categorically unsupported claims

The following wording remains prohibited regardless of approval:

- guaranteed vulnerability discovery or complete coverage;
- production-wide precision, recall, false-positive rate, or severity accuracy;
- release safety or absence of vulnerabilities;
- model, provider, scanner, language, framework, or workflow superiority;
- fully autonomous security auditing, exploitation, validation, remediation, or
  publication; and
- statistically significant improvement without a preregistered and adequately
  powered evaluation.

## Review decision record

| Review role | Decision before merge | Decision on the default branch | Scope |
|---|---|---|---|
| Security/disclosure reviewer | Pending | Approved only when the merge review history records no unresolved disclosure blocker | Public-safe content, claim boundaries, absence of private artifacts |
| Maintainer | Pending | Approved by accepting the merge after required checks and review completeness pass | Version/source traceability, maintainability, documentation ownership |

Approval covers only the exact report revision merged with this matrix. Later
numeric or wording changes require a new review decision.

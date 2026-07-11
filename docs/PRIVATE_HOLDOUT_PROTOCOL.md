# Private holdout protocol

This document defines the private-holdout operating protocol for Issue #238.
The English version is canonical. The Japanese companion document must remain
semantically aligned with this file.

The purpose of this protocol is narrow:

- keep the private corpus and all fixture-level evidence outside the repository;
- validate only aggregate-only records through `gra-efficacy-holdout`;
- make internal review and approved aggregate publication repeatable without
  turning benchmark material into public findings or product-efficacy claims.

`gra-efficacy-holdout` is a validator for pre-created private holdout records.
It is not a corpus runner, fixture loader, worker launcher, or publication tool.

## Current command contract

As currently implemented, the command contract is:

```bash
gra-efficacy-holdout --records-root ABSOLUTE_DIR
```

The command:

- does not load private fixtures or case files;
- requires `--records-root` to be an absolute, existing, readable,
  non-symlink directory with no symlink path components;
- requires that directory to stay outside the package/repository root and to
  not contain the package/repository root;
- loads only two fixed filenames from that directory:
  - `holdout-metadata.json`
  - `holdout-aggregate.json`
- validates them against the packaged closed schemas:
  - `templates/reports/efficacy-holdout-metadata.schema.json`
  - `templates/reports/efficacy-holdout-aggregate.schema.json`
- performs semantic consistency checks across the two records;
- pins the validated records-directory identity while reading both files and
  rejects credential-like, live-network, or execution markers in allowed
  identifier fields; and
- prints only an aggregate-only summary to stdout.

The current stdout summary format is:

```text
Private holdout records validated
Corpus: HOLDOUT_CORPUS_ID HOLDOUT_CORPUS_VERSION
Cases: CASE_COUNT (positive=POSITIVE_COUNT, controls=NEGATIVE_CONTROL_COUNT)
Configurations: CONFIGURATION_COUNT
Repeat runs: MIN_REPEAT-MAX_REPEAT
Publication approved: false
```

The summary is intentionally bounded. It does not emit case IDs, fixture paths,
locations, prompts, transcripts, evidence, or raw worker output.

## Required safety boundary

Private holdout material must remain outside tracked repository content.
Do not create or commit any real holdout fixture, case list, transcript, or
result bundle under this repository.

The following material is prohibited from this repository, from the validator
input records, and from public publication artifacts:

- private corpus files or fixture text;
- case IDs or per-case outcomes;
- source snippets, evidence bodies, locations, paths, or repository identifiers;
- prompts, transcripts, raw worker output, or scratchpad content;
- credentials, tokens, cookies, keys, or environment-derived secrets;
- approval packets, reviewer notes, or adjudication notes beyond digests;
- any pointer that would reconstruct the private corpus location.

The current aggregate schema encodes this safety boundary explicitly:

- `safety.aggregate_only` must be `true`;
- `fixture_text_included`, `case_ids_included`,
  `evidence_or_locations_included`, `prompts_or_transcripts_included`,
  `credentials_included`, `absolute_paths_included`, and
  `finding_publication_performed` must all remain `false`.

## Distinguish the three evaluation surfaces

| Surface | What it contains | Repository posture | Allowed output surface |
|---|---|---|---|
| Public corpus | Packaged public-safe synthetic fixtures used by `gra-efficacy-benchmark` | Tracked and releasable | Public-safe deterministic benchmark reports with explicit claim limits |
| Private holdout | Private evaluation corpus represented here only by aggregate metadata and aggregate metrics | Not tracked; access-controlled; validator reads aggregate records only | Restricted internal records and tightly bounded approved aggregate publication |
| Real repository dogfood | Actual repository content, findings, and workflow artifacts from self-dogfood or customer-scoped runs | Governed by dogfood/disclosure rules, not by this holdout protocol | Sanitized dogfood reporting only after repository-specific review |

Private holdout is not an extension of the public corpus, and it is not a real
repository dogfood run.

The current metadata schema expresses that separation through:

- `private_not_tracked: true`
- `public_corpus_reused: false`
- `real_repository_content_included: false`
- `storage_access_controlled: true`

If an operator needs richer prose explaining the separation, store it in the
restricted approval or campaign system, not in this repository.

## Metadata record requirements

`holdout-metadata.json` records the fixed evaluation plan and the corpus-level
boundary, not the corpus contents.

At minimum, metadata must record:

- an opaque corpus identifier and a content-bound corpus version;
- balanced corpus counts:
  - `case_count`
  - `positive_count`
  - `negative_control_count`
  - `category_count`
  - `balanced_controls`
  - `balance_exception_record_digest` for an externally approved exception when the counts are not balanced
- separation from the public corpus and from real-repository dogfood;
- an independent ground-truth review method and review-record digests; and
- a fixed evaluation plan for each configuration:
  - command version
  - report schema version
  - adjudication requirement
  - workflow version digest
  - prompt version digest
  - whether a worker/model channel was used
  - worker profile ID when applicable
  - worker CLI version when applicable
  - model ID when applicable
  - effort setting when applicable
  - repeat count

Current schema and validator constraints to preserve:

- `repeat_runs` must be at least `2`;
- `two-person` review requires at least two reviewers;
- the number of `review_record_digests` must equal `reviewer_count`;
- `balanced_controls` must match the positive/control counts; and
- unbalanced counts require an external `balance_exception_record_digest`;
- worker-specific fields must be all present for worker configurations and all
  absent for non-worker configurations.

## Aggregate record requirements

`holdout-aggregate.json` records only aggregate metrics and review-control
signals. It must not reveal fixture-level or case-level material.

At minimum, aggregate must record:

- an opaque `evaluation_id`;
- the executed `command_version` and `report_schema_version`;
- the same corpus identity and counts recorded in metadata;
- per-configuration repeated aggregate run results, including:
  - TP / FP / FN / TN counts
  - `evaluated_negative_control_count`
  - `negative_control_false_positive_case_count`
  - `prediction_count`
  - precision / recall / F1
  - severity-agreement aggregate
  - target-coverage aggregate
  - `human_review_required_count`
- recomputed repeat variance summaries for:
  - precision
  - recall
  - F1
  - severity agreement
  - target coverage
  - human review required count

`false_positives` and `prediction_count` count predictions. A positive case can
contribute an unmatched extra prediction, so `false_positives` may exceed
`negative_control_false_positive_case_count`, which counts affected control
cases rather than predictions.
- adjudication completion state and adjudication digest;
- safety flags; and
- publication approval state and separate approval digest.

Current validator behavior recomputes and checks:

- corpus counts between metadata and aggregate;
- `metadata.evaluation_plan.command_version` against aggregate `command_version`;
- `metadata.evaluation_plan.report_schema_version` against aggregate `report_schema_version`;
- configuration identity and fixed-plan alignment;
- contiguous ordered run numbers from `1..repeat_runs`;
- complete negative-control evaluation coverage and the partition of controls into
  true-negative and false-positive cases;
- rate math from aggregate counts;
- severity-agreement math;
- target-coverage math;
- repeat-variance summaries from the recorded repeated runs;
- `changed_ground_truth_count <= disputed_case_count <= case_count`; and
- the coupling of `publication.approved` with
  `publication.approval_record_digest`.
- records-root identity across both bounded reads and prohibited sensitive
  string markers even when the schema otherwise permits the identifier shape.

## Creation workflow

1. **Define the holdout boundary**
   - Create the private corpus outside the repository.
   - Assign an opaque corpus ID and a content-bound version.
   - Ensure the corpus remains separate from the public benchmark corpus and
     from any real repository dogfood content.
2. **Create the ground truth**
   - Use independent review.
   - Record only the approved review method, reviewer count, and digests of the
     external review records in `holdout-metadata.json`.
3. **Freeze the evaluation plan**
   - Pin the command version, workflow digest, prompt digest, worker/profile,
     model, effort, and repeat count before execution.
   - Require at least two repeats per configuration.
4. **Run the private evaluation outside this command**
   - The actual evaluation may be deterministic-only or may include a worker,
     depending on the approved plan.
   - Do not place private fixtures, prompts, transcripts, or raw responses into
     this repository.
5. **Write aggregate-only records**
   - Produce `holdout-metadata.json` and `holdout-aggregate.json` in a private,
     non-symlink records directory.
   - Exclude case IDs and all raw evidence.
6. **Validate with `gra-efficacy-holdout`**
   - Run the validator from the repository checkout.
   - Review stderr on failure; do not bypass the fail-closed checks.
7. **Adjudicate before publication review**
   - Resolve disputed cases outside the repository.
   - Update only the adjudication digest and aggregate metrics needed for the
     final approved aggregate record.
8. **Publish only approved aggregate summaries**
   - Internal restricted reporting may reference the validated aggregate record.
   - Any broader sharing must still remain aggregate-only and claim-limited.

## Review and access control workflow

The private holdout corpus, execution artifacts, and review packets must live in
access-controlled storage outside the repository. At minimum:

- restrict write access to designated operators;
- restrict read access to reviewers and approvers with a documented need;
- store approval and adjudication records in the restricted system and record
  only digests in the JSON artifacts;
- keep the records directory non-symlinked and outside packaged/tracked repo
  content;
- remove disposable local copies after validation and approval are complete,
  unless retention is explicitly required.

This repository may contain the protocol and the packaged schemas, but it must
not become the storage system for the private corpus.

## Worker/model channel confidentiality note

This protocol does not run the evaluation worker. It only records whether the
approved configuration used a worker/model channel.

If `worker_channel_used` is `true`:

- treat the model/control-plane channel as a confidential dependency;
- treat prompts, transcripts, and raw worker outputs as confidential
  operational artifacts;
- do not copy those artifacts into `holdout-metadata.json`,
  `holdout-aggregate.json`, commit messages, Issues, or public reports;
- do not treat read-only sandboxing or disabled auxiliary network access as a
  complete confidentiality boundary for private corpora;
- record only the bounded identifiers needed by the schema:
  worker profile ID, worker CLI version, model ID, effort, digests, and
  aggregate metrics.

## Adjudication protocol

Adjudication is mandatory for this protocol.

Use adjudication to resolve disputes in the private ground truth or in the
interpretation of repeated aggregate results without exposing case-level data.
The repository-visible artifact surface is limited to:

- `adjudication.completed: true`
- `disputed_case_count`
- `changed_ground_truth_count`
- `record_digest`

Keep the underlying adjudication notes, evidence, and reviewer discussion in the
restricted system only.

## Validation procedure

Run validation only against aggregate-only records in an external directory.
A disposable local example is acceptable when the records are synthetic and
non-sensitive.

Example flow:

```bash
REPO_ROOT=/absolute/path/to/genai-repo-auditor
WORKSPACE_ROOT=/absolute/path/to/workspace-containing-the-repo
RECORDS_ROOT="$WORKSPACE_ROOT/.codex-local/tmp/private-holdout-example"

mkdir -p "$RECORDS_ROOT"

cat > "$RECORDS_ROOT/holdout-metadata.json" <<'JSON'
{
  "schema_version": "1",
  "corpus": {
    "corpus_id": "holdout-012345abcdef",
    "corpus_version": "1.0.0+sha256.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "case_count": 12,
    "positive_count": 6,
    "negative_control_count": 6,
    "category_count": 4,
    "balanced_controls": true,
    "balance_exception_record_digest": null
  },
  "separation": {
    "private_not_tracked": true,
    "public_corpus_reused": false,
    "real_repository_content_included": false,
    "storage_access_controlled": true
  },
  "ground_truth_review": {
    "review_method": "two-person",
    "reviewer_count": 2,
    "independent_from_evaluation": true,
    "completed": true,
    "review_record_digests": [
      "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
    ]
  },
  "evaluation_plan": {
    "command_version": "0.9.0",
    "report_schema_version": "1",
    "adjudication_required": true,
    "configurations": [
      {
        "configuration_id": "config-012345abcdef",
        "workflow_version": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "prompt_version": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "worker_channel_used": false,
        "worker_profile_id": null,
        "worker_cli_version": null,
        "model_id": null,
        "effort": null,
        "repeat_runs": 2
      }
    ]
  }
}
JSON

cat > "$RECORDS_ROOT/holdout-aggregate.json" <<'JSON'
{
  "schema_version": "1",
  "evaluation_id": "evaluation-012345abcdef",
  "command_version": "0.9.0",
  "report_schema_version": "1",
  "corpus": {
    "corpus_id": "holdout-012345abcdef",
    "corpus_version": "1.0.0+sha256.aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "case_count": 12,
    "positive_count": 6,
    "negative_control_count": 6,
    "category_count": 4,
    "balanced_controls": true,
    "balance_exception_record_digest": null
  },
  "configurations": [
    {
      "configuration_id": "config-012345abcdef",
      "workflow_version": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "prompt_version": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "worker_channel_used": false,
      "worker_profile_id": null,
      "worker_cli_version": null,
      "model_id": null,
      "effort": null,
      "repeat_runs": 2,
      "runs": [
        {
          "run_number": 1,
          "evaluated_negative_control_count": 6,
          "negative_control_false_positive_case_count": 1,
          "counts": {
            "true_positives": 5,
            "false_positives": 1,
            "false_negatives": 1,
            "true_negatives": 5,
            "prediction_count": 6
          },
          "rates": {
            "precision": 0.833333,
            "recall": 0.833333,
            "f1": 0.833333
          },
          "severity_agreement": {
            "agreed": 4,
            "eligible": 5,
            "rate": 0.8
          },
          "target_coverage": {
            "covered": 12,
            "selected": 12,
            "rate": 1.0
          },
          "human_review_required_count": 2
        },
        {
          "run_number": 2,
          "evaluated_negative_control_count": 6,
          "negative_control_false_positive_case_count": 0,
          "counts": {
            "true_positives": 4,
            "false_positives": 0,
            "false_negatives": 2,
            "true_negatives": 6,
            "prediction_count": 4
          },
          "rates": {
            "precision": 1.0,
            "recall": 0.666667,
            "f1": 0.8
          },
          "severity_agreement": {
            "agreed": 3,
            "eligible": 4,
            "rate": 0.75
          },
          "target_coverage": {
            "covered": 12,
            "selected": 12,
            "rate": 1.0
          },
          "human_review_required_count": 3
        }
      ],
      "repeat_variance": {
        "precision": {
          "applicable_run_count": 2,
          "minimum": 0.833333,
          "maximum": 1.0,
          "mean": 0.916667,
          "population_variance": 0.006944
        },
        "recall": {
          "applicable_run_count": 2,
          "minimum": 0.666667,
          "maximum": 0.833333,
          "mean": 0.75,
          "population_variance": 0.006944
        },
        "f1": {
          "applicable_run_count": 2,
          "minimum": 0.8,
          "maximum": 0.833333,
          "mean": 0.816666,
          "population_variance": 0.000278
        },
        "severity_agreement": {
          "applicable_run_count": 2,
          "minimum": 0.75,
          "maximum": 0.8,
          "mean": 0.775,
          "population_variance": 0.000625
        },
        "target_coverage": {
          "applicable_run_count": 2,
          "minimum": 1.0,
          "maximum": 1.0,
          "mean": 1.0,
          "population_variance": 0.0
        },
        "human_review_required_count": {
          "applicable_run_count": 2,
          "minimum": 2,
          "maximum": 3,
          "mean": 2.5,
          "population_variance": 0.25
        }
      }
    }
  ],
  "adjudication": {
    "completed": true,
    "disputed_case_count": 1,
    "changed_ground_truth_count": 0,
    "record_digest": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
  },
  "safety": {
    "aggregate_only": true,
    "fixture_text_included": false,
    "case_ids_included": false,
    "evidence_or_locations_included": false,
    "prompts_or_transcripts_included": false,
    "credentials_included": false,
    "absolute_paths_included": false,
    "finding_publication_performed": false
  },
  "publication": {
    "approved": false,
    "approval_record_digest": null,
    "public_claim_allowed": false,
    "production_performance_claim_allowed": false,
    "finding_publication_authorized": false
  }
}
JSON

(
  cd "$REPO_ROOT"
  bin/gra-efficacy-holdout --records-root "$RECORDS_ROOT"
)
```

This example uses disposable non-sensitive placeholder data only. It must not be
replaced by real holdout fixtures inside the repository.

On native Windows, create the same two records in an access-controlled
directory outside the checkout, then validate them from PowerShell:

```powershell
$RecordsRoot = Join-Path $env:LOCALAPPDATA "GenAIRepoAuditor\private-holdout-records"
gra-efficacy-holdout --records-root $RecordsRoot
if ($LASTEXITCODE -ne 0) { throw "private holdout validation failed" }
```

This validation-only command does not use the efficacy report-generation path
that remains unsupported on native Windows. The install matrix executes this
semantic validation on Windows, macOS, and Ubuntu.

## Internal reporting vs public publication

Restricted internal reporting may discuss the validated aggregate metrics,
variance, adjudication status, and workflow differences, provided it still
omits case-level and evidence-level content.

Public publication is stricter than internal reporting:

- publish only an approved aggregate summary;
- keep the summary aggregate-only;
- keep `public_claim_allowed: false`;
- keep `production_performance_claim_allowed: false`;
- keep `finding_publication_authorized: false`;
- name the corpus version, command version, configuration IDs, repeat counts,
  and whether a worker/model channel was used;
- state that the result is a private holdout aggregate, not production recall
  or precision evidence.

Approval does not convert the benchmark into a finding publication workflow.
It only authorizes a bounded aggregate statement under the separate approval
record referenced by digest.

## Findings and claim limitations

A private holdout benchmark does not authorize publication of repository
findings.

Do not use this protocol to claim:

- product-wide recall or precision in production;
- superiority of one model, workflow, provider, or effort level;
- validation of a finding in a real repository;
- release safety for a target repository;
- permission to publish a vulnerability report, Issue, advisory, or case study.

The benchmark surface is for aggregate evaluation control only. Repository
finding publication remains governed by repository-specific evidence,
validation, disclosure, and approval workflows.

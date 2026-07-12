# Aggregate evaluation reproduction

## Purpose and boundary

This guide reproduces only the public deterministic synthetic rows in
PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md. It does not reproduce the private
holdout or rerun the real-repository dogfood campaign. It must not be used to
infer production performance or to publish target findings.

The evaluated baseline is GenAI Repo Auditor version 0.4.0 at source commit
960dd1de42c129a524acbb2437f3a4406024bda9. Use Python 3.10 or newer on
Linux, WSL2, or macOS for report generation. The commands use no worker, model,
scanner, GitHub mutation, or network helper.

## 1. Check out and verify the source

~~~bash
git checkout 960dd1de42c129a524acbb2437f3a4406024bda9
test "$(cat VERSION)" = "0.4.0"
python3 -m unittest tests.test_efficacy_corpus tests.test_efficacy_benchmark
~~~

Use a clean checkout. Do not run these commands in a directory containing
private holdout material or target-repository artifacts.

## 2. Run the public benchmark twice

~~~bash
mkdir -p .test-tmp/public-evaluation
bin/gra-efficacy-benchmark   --out-json .test-tmp/public-evaluation/public-a.json   --out-md .test-tmp/public-evaluation/public-a.md
bin/gra-efficacy-benchmark   --out-json .test-tmp/public-evaluation/public-b.json   --out-md .test-tmp/public-evaluation/public-b.md
cmp .test-tmp/public-evaluation/public-a.json     .test-tmp/public-evaluation/public-b.json
cmp .test-tmp/public-evaluation/public-a.md     .test-tmp/public-evaluation/public-b.md
~~~

The default selection is the core suite. The expected content-bound corpus
version is
1.1.0+sha256.33c20915076017869a6b99e0552be59f40aa05d701b61e4572d4d449a4fa6146.

## 3. Verify the aggregate row

~~~bash
python3 - .test-tmp/public-evaluation/public-a.json <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["mode"] == "deterministic-fixture"
assert report["corpus"]["corpus_id"] == "genai-repo-auditor-synthetic-core"
assert report["corpus"]["selection"]["suite"] == "core"
assert report["execution"]["selected_case_count"] == 20
assert report["execution"]["detector_id"] == "synthetic-reference-rules-v2"
assert report["scores"]["counts"] == {
    "false_negatives": 0,
    "false_positives": 0,
    "prediction_count": 10,
    "true_negatives": 10,
    "true_positives": 10,
}
assert report["scores"]["rates"] == {
    "f1": 1.0,
    "precision": 1.0,
    "recall": 1.0,
}
assert report["scores"]["severity_agreement"] == {
    "agreed": 10,
    "eligible": 10,
    "rate": 1.0,
}
assert report["scores"]["target_coverage"] == {
    "covered": 20,
    "rate": 1.0,
    "selected": 20,
}
assert report["scores"]["human_review_required_count"] == 10
assert report["safety"]["network_accessed"] is False
assert report["safety"]["model_channel_used"] is False
assert report["safety"]["issue_publication_performed"] is False
PY
~~~

## 4. Reproduce the fixed configuration comparison

~~~bash
bin/gra-efficacy-benchmark --compare   --out-json .test-tmp/public-evaluation/comparison.json   --out-md .test-tmp/public-evaluation/comparison.md
~~~

Verify the fixed stage IDs and bounded aggregate values:

~~~bash
python3 - .test-tmp/public-evaluation/comparison.json <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
rows = {row["configuration_id"]: row for row in report["configurations"]}
full = rows["reference-review-all-signals-v1"]
gated = rows["reference-review-high-severity-gate-v1"]
assert full["deterministic"] is True
assert gated["deterministic"] is True
assert full["workflow_stage_ids"] == ["fixture-reference-review"]
assert gated["workflow_stage_ids"] == [
    "fixture-reference-review",
    "high-severity-review-gate",
]
assert full["scores"]["counts"]["true_positives"] == 10
assert full["scores"]["counts"]["false_negatives"] == 0
assert gated["scores"]["counts"]["true_positives"] == 7
assert gated["scores"]["counts"]["false_negatives"] == 3
assert gated["scores"]["rates"] == {
    "f1": 0.823529,
    "precision": 1.0,
    "recall": 0.7,
}
assert report["safety"]["model_channel_used"] is False
assert report["claim_guardrails"]["product_capability_claim_allowed"] is False
assert report["claim_guardrails"]["production_performance_claim_allowed"] is False
PY
~~~

## 5. Layers that are not reproduced here

### Private holdout

No approved aggregate exists for this report. Do not create substitute numbers.
An authorized evaluator may separately validate two aggregate-only records with
gra-efficacy-holdout according to the
[private holdout protocol](../PRIVATE_HOLDOUT_PROTOCOL.md). Do not copy those
records or their source fixtures into Git.

### ITDO_ERP4 operational dogfood

Do not rerun a real-repository audit to reproduce this document. The public
source is the
[reviewed aggregate](../dogfood/ITDO_ERP4_SECOND_DOGFOOD_SUMMARY.md).
Target-specific artifacts and
findings remain outside Git and require the target owner's private disclosure
process.

### Worker and scanner rows

No worker/model or scanner execution row is included. Do not add one without
fixed inputs, explicit authorization, version capture, bounded local artifacts,
and new security/disclosure and maintainer review.

## 6. Publication check

Before reusing a number or claim:

1. identify its exact row in
   [PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md](PUBLIC_EFFICACY_AND_OPERATIONS_REPORT.md);
2. verify the permitted wording in
   [CLAIM_EVIDENCE_MATRIX.md](CLAIM_EVIDENCE_MATRIX.md);
3. keep the synthetic, holdout, and operational layers separate;
4. confirm the corpus, source, configuration, and stage versions still match;
5. rerun documentation and manifest tests; and
6. obtain the required review decisions for the changed revision.

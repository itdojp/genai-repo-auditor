from __future__ import annotations

from pathlib import Path
from typing import Any

from efficacy_benchmark import (
    EfficacyBenchmarkError,
    analyze_fixture_case,
    score_cases,
)
from efficacy_corpus import (
    EfficacyCorpusError,
    load_corpus_fixture_texts,
    load_schema_object,
    validate_schema_object,
)


COMPARISON_SCHEMA_VERSION = "1"
REFERENCE_CONFIGURATIONS = {
    "reference-review-all-signals-v1": "Reference fixture review retaining all supported synthetic signals.",
    "reference-review-high-severity-gate-v1": "Reference fixture review followed by a High/Critical severity gate.",
}
REFERENCE_WORKFLOW_STAGES = {
    "reference-review-all-signals-v1": ["fixture-reference-review"],
    "reference-review-high-severity-gate-v1": [
        "fixture-reference-review",
        "high-severity-review-gate",
    ],
}
DEFAULT_CONFIGURATIONS = tuple(REFERENCE_CONFIGURATIONS)
COMPARISON_LIMITATIONS = [
    "Configuration deltas on this small synthetic corpus are regression evidence, not product capability claims.",
    "Worker-assisted results are non-deterministic and are not comparable across model or prompt "
    + "changes without review.",
    "No benchmark result authorizes finding or Issue publication without repository-specific human validation.",
]


def list_configurations() -> str:
    lines = ["CONFIGURATION ID\tDETERMINISTIC\tDESCRIPTION"]
    for configuration_id, description in REFERENCE_CONFIGURATIONS.items():
        lines.append(f"{configuration_id}\tyes\t{description}")
    return "\n".join(lines) + "\n"


def select_configurations(configuration_ids: list[str] | None) -> list[str]:
    selected = list(DEFAULT_CONFIGURATIONS) if not configuration_ids else list(configuration_ids)
    if len(selected) != len(set(selected)):
        raise EfficacyBenchmarkError("--configuration values must be unique")
    unknown = sorted(set(selected) - set(REFERENCE_CONFIGURATIONS))
    if unknown:
        raise EfficacyBenchmarkError(f"unknown efficacy comparison configuration: {unknown[0]}")
    if len(selected) < 2:
        raise EfficacyBenchmarkError("efficacy comparison requires at least two deterministic configurations")
    return selected


def _reference_analyses(
    configuration_id: str,
    cases: list[dict[str, Any]],
    fixture_texts: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    analyses: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = case["case_id"]
        analysis = analyze_fixture_case(case, fixture_texts[case_id])
        if configuration_id == "reference-review-high-severity-gate-v1":
            predictions = [
                prediction
                for prediction in analysis["predictions"]
                if prediction["severity"] in {"High", "Critical"}
            ]
            analysis = {
                **analysis,
                "predictions": predictions,
                "human_review_required": bool(predictions) or not analysis["rule_supported"],
            }
        analyses[case_id] = analysis
    return analyses


def _bounded_case_outcomes(scored: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "case_id": case["case_id"],
            "outcome": case["outcome"],
            "true_positives": case["true_positives"],
            "false_positives": case["false_positives"],
            "false_negatives": case["false_negatives"],
            "human_review_required": case["human_review_required"],
        }
        for case in scored["cases"]
    ]


def _configuration_result(
    *,
    configuration_id: str,
    configuration_type: str,
    deterministic: bool,
    description: str,
    workflow_stage_ids: list[str],
    worker_profile_id: str | None,
    model_id: str | None,
    worker_effort: str | None,
    worker_cli_version: str | None,
    cases: list[dict[str, Any]],
    analyses: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    scored = score_cases(cases, analyses)
    return {
        "configuration_id": configuration_id,
        "configuration_type": configuration_type,
        "deterministic": deterministic,
        "description": description,
        "workflow_stage_ids": workflow_stage_ids,
        "worker_profile_id": worker_profile_id,
        "model_id": model_id,
        "worker_effort": worker_effort,
        "worker_cli_version": worker_cli_version,
        "case_ids": [case["case_id"] for case in cases],
        "scores": {
            "counts": scored["counts"],
            "rates": scored["rates"],
            "severity_agreement": scored["severity_agreement"],
            "target_coverage": scored["target_coverage"],
            "human_review_required_count": scored["human_review_required_count"],
        },
        "case_outcomes": _bounded_case_outcomes(scored),
    }


def _rate_delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return round(value - baseline, 6)


def _comparison_deltas(configurations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = configurations[0]["scores"]
    deltas: list[dict[str, Any]] = []
    for configuration in configurations[1:]:
        scores = configuration["scores"]
        deltas.append(
            {
                "configuration_id": configuration["configuration_id"],
                "true_positive_delta": scores["counts"]["true_positives"]
                - baseline["counts"]["true_positives"],
                "false_positive_delta": scores["counts"]["false_positives"]
                - baseline["counts"]["false_positives"],
                "false_negative_delta": scores["counts"]["false_negatives"]
                - baseline["counts"]["false_negatives"],
                "precision_delta": _rate_delta(scores["rates"]["precision"], baseline["rates"]["precision"]),
                "recall_delta": _rate_delta(scores["rates"]["recall"], baseline["rates"]["recall"]),
                "f1_delta": _rate_delta(scores["rates"]["f1"], baseline["rates"]["f1"]),
            }
        )
    return deltas


def build_comparison_report(
    lab_root: Path,
    *,
    suite: str | None = None,
    case_ids: list[str] | None = None,
    configuration_ids: list[str] | None = None,
    worker_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from efficacy_benchmark import select_cases

    try:
        loaded, fixture_texts = load_corpus_fixture_texts(lab_root)
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError(str(exc)) from exc
    cases, selection = select_cases(loaded, suite=suite, case_ids=case_ids)
    selected = select_configurations(configuration_ids)
    configurations = [
        _configuration_result(
            configuration_id=configuration_id,
            configuration_type="reference-workflow",
            deterministic=True,
            description=REFERENCE_CONFIGURATIONS[configuration_id],
            workflow_stage_ids=REFERENCE_WORKFLOW_STAGES[configuration_id],
            worker_profile_id=None,
            model_id=None,
            worker_effort=None,
            worker_cli_version=None,
            cases=cases,
            analyses=_reference_analyses(configuration_id, cases, fixture_texts),
        )
        for configuration_id in selected
    ]
    if worker_result is not None:
        selected_case_ids = {case["case_id"] for case in cases}
        if set(worker_result.get("analyses", {})) != selected_case_ids:
            raise EfficacyBenchmarkError("efficacy worker analyses must exactly match the selected case IDs")
        configurations.append(
            _configuration_result(
                configuration_id=f"worker:{worker_result['profile_id']}",
                configuration_type="worker-workflow",
                deterministic=False,
                description="Explicit opt-in worker-backed synthetic fixture analysis.",
                workflow_stage_ids=["worker-fixture-review"],
                worker_profile_id=worker_result["profile_id"],
                model_id=worker_result["model_id"],
                worker_effort=worker_result["effort"],
                worker_cli_version=worker_result["codex_cli_version"],
                cases=cases,
                analyses=worker_result["analyses"],
            )
        )
    case_id_list = [case["case_id"] for case in cases]
    report = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "benchmark_id": "genai-repo-auditor-security-efficacy-comparison",
        "mode": "worker-assisted-comparison" if worker_result is not None else "deterministic-comparison",
        "corpus": {
            "corpus_id": loaded["corpus"]["corpus_id"],
            "corpus_version": loaded["corpus"]["corpus_version"],
            "selection": selection,
        },
        "safety": {
            "benchmark_inputs_local_synthetic_only": True,
            "model_channel_used": worker_result is not None,
            "external_network_beyond_model_channel_enabled": False,
            "worker_user_configuration_loaded": False,
            "worker_project_rules_loaded": False,
            "github_accessed": False,
            "issue_publication_performed": False,
            "raw_fixture_content_included": False,
            "bounded_summary_only": True,
        },
        "configurations": configurations,
        "comparison": {
            "baseline_configuration_id": configurations[0]["configuration_id"],
            "case_ids": case_id_list,
            "deltas": _comparison_deltas(configurations),
        },
        "claim_guardrails": {
            "product_capability_claim_allowed": False,
            "production_performance_claim_allowed": False,
            "publication_requires_human_review": True,
            "finding_publication_performed": False,
        },
        "limitations": COMPARISON_LIMITATIONS,
    }
    try:
        schema = load_schema_object(
            lab_root,
            "templates/reports/efficacy-comparison.schema.json",
            label="efficacy comparison schema",
        )
        validate_schema_object(report, schema, label="efficacy comparison")
    except EfficacyCorpusError as exc:
        raise EfficacyBenchmarkError("efficacy comparison failed its closed schema contract") from exc
    return report


def render_comparison_markdown(report: dict[str, Any]) -> str:
    def display(value: float | None) -> str:
        return "not applicable" if value is None else f"{value:.6f}"

    lines = [
        "# Security efficacy comparison",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Corpus: `{report['corpus']['corpus_id']}`",
        f"- Corpus version: `{report['corpus']['corpus_version']}`",
        f"- Baseline: `{report['comparison']['baseline_configuration_id']}`",
        f"- Case IDs: `{','.join(report['comparison']['case_ids'])}`",
        "- GitHub/Issue publication: `false / false`",
        "",
        "## Configuration scores",
        "",
        "| Configuration | Type | Workflow stages | Deterministic | Worker profile | CLI | Model | Effort | "
        + "TP | FP | FN | TN | Precision | Recall | F1 | Severity | Coverage | Human review |",
        "|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for configuration in report["configurations"]:
        scores = configuration["scores"]
        counts = scores["counts"]
        rates = scores["rates"]
        lines.append(
            f"| `{configuration['configuration_id']}` | {configuration['configuration_type']} | "
            f"{','.join(configuration['workflow_stage_ids'])} | "
            f"{'yes' if configuration['deterministic'] else 'no'} | "
            f"{configuration['worker_profile_id'] or 'not applicable'} | "
            f"{configuration['worker_cli_version'] or 'not applicable'} | "
            f"{configuration['model_id'] or 'not applicable'} | "
            f"{configuration['worker_effort'] or 'not applicable'} | {counts['true_positives']} | "
            f"{counts['false_positives']} | {counts['false_negatives']} | {counts['true_negatives']} | "
            f"{display(rates['precision'])} | {display(rates['recall'])} | {display(rates['f1'])} | "
            f"{display(scores['severity_agreement']['rate'])} | {display(scores['target_coverage']['rate'])} | "
            f"{scores['human_review_required_count']} |"
        )
    lines.extend(
        [
            "",
            "## Case outcomes",
            "",
            "| Configuration | Case ID | Outcome | TP | FP | FN | Human review |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for configuration in report["configurations"]:
        for case in configuration["case_outcomes"]:
            lines.append(
                f"| `{configuration['configuration_id']}` | `{case['case_id']}` | {case['outcome']} | "
                f"{case['true_positives']} | {case['false_positives']} | {case['false_negatives']} | "
                f"{'yes' if case['human_review_required'] else 'no'} |"
            )
    lines.extend(
        [
            "",
            "## Claim and publication guardrails",
            "",
            "- Product capability claim allowed: `false`",
            "- Production performance claim allowed: `false`",
            "- Publication requires human review: `true`",
            "- Finding publication performed: `false`",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)

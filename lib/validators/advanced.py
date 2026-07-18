from __future__ import annotations

import json
import re
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Dict, List

from report_safety import (
    ReportSafetyError,
    iter_secret_findings,
    validate_relative_repo_path,
)
from gralib import load_context, load_targets_artifact
from provider_failures import (
    PROVIDER_ERROR_CLASSES,
    ProviderFailureError,
    validate_provider_error,
    validate_provider_failure_history,
)
from scanner_reporting import ScannerReportError, validate_scanner_runs_for_run
from scanner_readiness import ScannerReadinessError, read_scanner_readiness_report
from report_freshness import (
    FreshnessError,
    load_bounded_json_artifact,
    load_freshness,
    validate_public_summary,
)
from run_events import (
    COMMAND_EVENT_COMMANDS,
    COMMAND_EVENT_PHASES,
    EventValidationError,
    reports_dir as configured_reports_dir,
    validate_command_event_payload,
)
from workflow_profile import validate_workflow_profile_payload

from .common import (
    json_type_name,
    load_schema as load_schema_from_root,
    parse_event_time,
    validate_generated_at,
    validate_no_symlink_components,
    validate_run_artifact_path,
    validate_schema,
    validate_schema_shape,
    validate_string_list,
)
from .context import ValidationContext
from .findings import ASSESSMENT_STATUSES, CONFIDENCES, SEVERITIES
from .scanner import SCANNER_RESULTS_DIR

DEFAULT_LAB_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_LAB_ROOT: ContextVar[Path] = ContextVar("advanced_validator_schema_lab_root", default=DEFAULT_LAB_ROOT)

DEPENDENCIES_PATH = Path("reports/dependencies.json")
VALIDATION_PATH = Path("reports/validation.json")
CHAINS_PATH = Path("reports/chains.json")
PROOFS_PATH = Path("reports/proofs.json")
PROOFS_DIR = Path("reports/proofs")
REMEDIATION_PATH = Path("reports/remediation/remediation-candidates.json")
REMEDIATION_DIR = Path("reports/remediation")
PATCH_VALIDATION_FILENAME = "patch-validation.json"
NOVELTY_PATH = Path("reports/known-findings.json")
TRACES_PATH = Path("reports/traces.json")
METRICS_PATH = Path("reports/metrics.json")
EVIDENCE_GRAPH_PATH = Path("reports/evidence-graph.json")
IMPORTED_FINDINGS_PATH = Path("reports/imported-findings.json")
BENCHMARK_PATH = Path("reports/benchmark.json")
WORKFLOW_PROFILE_PATH = Path("reports/workflow-profile.json")
WORKFLOW_EXECUTION_PATH = Path("reports/workflow-execution.json")
ISSUE_LEDGER_PATH = Path("reports/issue-ledger.json")
DUPLICATE_DECISIONS_DIR = Path("reports/duplicate-decisions")
RUN_STATE_PATH = Path("reports/run-state.json")
COMMAND_EVENTS_PATH = Path("reports/command-events.jsonl")
STORE_IMPORT_STATE_PATH = Path("reports/store-import-state.json")
VALIDATION_DECISIONS = {"confirm", "downgrade", "invalidate", "needs-human-review"}
VALIDATION_SUBJECT_TYPES = {"finding", "chain"}
VALIDATION_SEVERITIES = SEVERITIES | {"Unknown"}
VALIDATION_CONFIDENCES = CONFIDENCES | {"Unknown"}
VALIDATION_POLICIES = {"human-review-on-split", "precision-biased", "recall-biased"}
VALIDATION_OWNER_SOURCES = {"CODEOWNERS", "path heuristic", "manual", "unknown"}
VALIDATION_PRIVATE_REASONING_KEYS = {
    "chain_of_thought",
    "chain-of-thought",
    "private_reasoning",
    "hidden_reasoning",
    "raw_reasoning",
    "scratchpad",
    "internal_deliberation",
}
CHAIN_STATUSES = {"Confirmed", "Probable", "Potential", "Invalid", "Needs human review"}
PROOF_TYPES = {
    "static-trace",
    "unit-test-plan",
    "local-regression-test",
    "config-check",
    "parser-only-local-input",
    "mocked-local-service",
}
PROOF_STATUSES = {"confirmed", "failed", "not-run", "needs-human-review"}
PROOF_COMMAND_CWD_SCOPES = {"run", "reports", "target_repo"}
PROOF_READ_ONLY_COMMANDS = {"rg", "sed", "python", "python3"}
PROOF_SHELL_METACHARS_RE = re.compile(r"[;&|`$<>\n\r]")
PROOF_SAFE_SED_SCRIPT_RE = re.compile(r"^(?:p|(?:\$|[0-9]+)(?:,(?:\$|[0-9]+))?p)$")
REMEDIATION_STATUSES = {"draft"}
PATCH_VALIDATION_BUILD_TEST_STATUSES = {"passed", "failed", "not-run"}
PATCH_VALIDATION_SAFE_PROOF_STATUSES = {"passed", "failed", "not-applicable", "not-run"}
PATCH_VALIDATION_ADVERSARIAL_STATUSES = {"passed", "failed", "needs-human-review", "not-run"}
PATCH_VALIDATION_DIFF_SCOPE_STATUSES = {"bounded", "too-broad", "needs-human-review"}
PATCH_VALIDATION_FINAL_STATUSES = {"validated", "failed", "needs-human-review"}
NOVELTY_STATUSES = {
    "new",
    "duplicate",
    "better-example",
    "accepted-risk",
    "regression",
    "invalid-known",
    "needs-human-review",
}
NOVELTY_SUPPRESSED_PUBLICATION_STATUSES = {"duplicate", "accepted-risk", "invalid-known"}
TRACE_STATUSES = {"Confirmed", "Probable", "Potential", "Invalid", "Needs human review"}
METRICS_FORBIDDEN_KEYS = {
    "evidence",
    "root_cause",
    "impact",
    "reasoning_summary",
    "safe_validation_steps",
    "issue_body",
    "issue_body_text",
}
EVIDENCE_GRAPH_FORBIDDEN_KEYS = {
    "evidence",
    "root_cause",
    "impact",
    "issue_body",
    "issue_body_text",
    "minimal_remediation",
    "regression_test_idea",
    "safe_validation_steps",
    "proof_payload",
    "secret",
    "token",
    "credential",
}
WORKFLOW_EXECUTION_FORBIDDEN_KEYS = {
    "prompt",
    "prompts",
    "raw_prompt",
    "raw_prompts",
    "finding",
    "findings",
    "raw_finding",
    "raw_findings",
    "evidence",
    "raw_evidence",
    "credential",
    "credentials",
    "secret",
    "secrets",
    "token",
    "tokens",
    "private_reasoning",
    "reasoning",
    "chain_of_thought",
    "scratchpad",
    "issue_body",
    "issue_body_text",
    "stdout",
    "stderr",
    "command_output",
}
WORKFLOW_EXECUTION_STAGE_STATUSES = {
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked_dependency",
    "external_prerequisite",
    "skipped_by_scope",
    "out_of_range",
}
WORKFLOW_EXECUTION_ABSENCE_REASONS = {
    "workflow_execution_not_recorded",
    "interrupted",
    "operator_scoped_skip",
    "external_prerequisite",
    "outside_selected_range",
    "blocked_by_dependency",
    "range_continuation",
    "workflow_paused",
    "workflow_blocked",
    "not_started",
}
SAFE_WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
EVIDENCE_GRAPH_NODE_TYPES = {
    "target",
    "scanner_run",
    "scanner_lead",
    "finding",
    "chain",
    "proof",
    "validation",
    "trace",
    "remediation_candidate",
    "patch_validation",
    "issue_plan_entry",
    "metric",
    "workflow_profile",
    "workflow_execution",
    "workflow_stage",
}


def configured_artifact_ref(run_dir: Path, default_ref: Path) -> Path:
    """Resolve a legacy reports/* reference against the run's configured reports_dir."""

    reports_ref = configured_reports_dir(run_dir).relative_to(run_dir)
    return reports_ref.joinpath(*default_ref.parts[1:])


def configured_artifact_path(run_dir: Path, default_ref: Path) -> Path:
    return run_dir / configured_artifact_ref(run_dir, default_ref)


EVIDENCE_GRAPH_EDGE_TYPES = {
    "produced",
    "supports",
    "challenges",
    "invalidates",
    "depends_on",
    "member_of",
    "validated_by",
    "publication_candidate",
    "not_applicable",
}
IMPORTED_FINDING_APPEND_STATUSES = {"review-only", "appended", "duplicate-skipped"}
BENCHMARK_GATE_STATUSES = {"pass", "warn", "fail"}
BENCHMARK_OVERALL_STATUSES = {"passed", "needs-review", "failed"}
BENCHMARK_FORBIDDEN_KEYS = {
    "evidence",
    "root_cause",
    "impact",
    "reasoning_summary",
    "safe_validation_steps",
    "issue_body",
    "issue_body_text",
    "proof_payload",
    "secret",
    "token",
    "credential",
}


def load_schema(name: str) -> Dict[str, Any]:
    """Backward-compatible schema loader for remaining in-file validators."""

    return load_schema_from_root(_SCHEMA_LAB_ROOT.get(), name)


def validate_no_private_reasoning_keys(value: Any, field_path: str, errors: List[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace(" ", "_")
            if normalized in VALIDATION_PRIVATE_REASONING_KEYS:
                errors.append(f"{field_path}.{key}: private reasoning / chain-of-thought fields are not allowed")
            validate_no_private_reasoning_keys(child, f"{field_path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_no_private_reasoning_keys(child, f"{field_path}[{index}]", errors)


def expected_vote_decision(vote_decisions: list[str], policy: str) -> str:
    counts = {decision: vote_decisions.count(decision) for decision in VALIDATION_DECISIONS}
    unique = {decision for decision in vote_decisions if counts.get(decision, 0) > 0}
    if not vote_decisions:
        return "needs-human-review"
    if policy == "human-review-on-split" and len(unique) > 1:
        return "needs-human-review"
    winner = max(VALIDATION_DECISIONS, key=lambda decision: counts.get(decision, 0))
    if counts.get(winner, 0) > len(vote_decisions) / 2:
        return winner
    if policy == "precision-biased":
        for candidate in ["invalidate", "downgrade", "needs-human-review", "confirm"]:
            if counts.get(candidate, 0):
                return candidate
    if policy == "recall-biased":
        for candidate in ["confirm", "downgrade", "needs-human-review", "invalidate"]:
            if counts.get(candidate, 0):
                return candidate
    return "needs-human-review"










def validate_dependencies(run_dir: Path, errors: List[str]) -> bool:
    dependencies_path = configured_artifact_path(run_dir, DEPENDENCIES_PATH)
    if not dependencies_path.exists():
        return False
    try:
        dependencies_data = json.loads(dependencies_path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"dependencies.json invalid JSON: {e}")
        return False

    validate_schema(dependencies_data, load_schema("dependencies.schema.json"), "dependencies", errors)
    if not isinstance(dependencies_data, dict):
        return True
    validate_generated_at(dependencies_data.get("generated_at"), "dependencies.generated_at", errors)

    components = dependencies_data.get("components")
    if not isinstance(components, list):
        errors.append("dependencies.components: components must be a list")
        return False
    vulnerabilities = dependencies_data.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        errors.append("dependencies.vulnerabilities: vulnerabilities must be a list")
        return False

    component_ids: set[str] = set()
    for index, component in enumerate(components):
        path = f"dependencies.components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{path}: component must be an object")
            continue
        cid = str(component.get("id") or "").strip()
        if not cid:
            errors.append(f"{path}.id: component id must not be empty")
        elif cid in component_ids:
            errors.append(f"{path}.id: duplicate component id {cid}")
        component_ids.add(cid)
        if component.get("scope") not in {"root", "direct", "transitive", "unknown"}:
            errors.append(f"{path}.scope: invalid scope {component.get('scope')}")
        if not isinstance(component.get("licenses"), list):
            errors.append(f"{path}.licenses: licenses must be list")
        paths = component.get("dependency_paths")
        if not isinstance(paths, list):
            errors.append(f"{path}.dependency_paths: dependency_paths must be list")
        else:
            for path_index, dep_path in enumerate(paths):
                if not isinstance(dep_path, list) or not all(isinstance(item, str) and item for item in dep_path):
                    errors.append(f"{path}.dependency_paths[{path_index}]: dependency path must be a list of non-empty strings")

    if dependencies_data.get("component_count") != len(components):
        errors.append("dependencies.component_count: value does not match components length")
    if dependencies_data.get("vulnerability_count") != len(vulnerabilities):
        errors.append("dependencies.vulnerability_count: value does not match vulnerabilities length")

    for index, vulnerability in enumerate(vulnerabilities):
        path = f"dependencies.vulnerabilities[{index}]"
        if not isinstance(vulnerability, dict):
            errors.append(f"{path}: vulnerability must be an object")
            continue
        vid = str(vulnerability.get("id") or "").strip()
        if not vid:
            errors.append(f"{path}.id: vulnerability id must not be empty")
        component = str(vulnerability.get("component") or "").strip()
        if component and component not in component_ids:
            errors.append(f"{path}.component: component {component} is not present in dependencies.components")
        if vulnerability.get("severity") not in {"Critical", "High", "Medium", "Low", "Informational", "Unknown"}:
            errors.append(f"{path}.severity: invalid severity {vulnerability.get('severity')}")
        paths = vulnerability.get("dependency_paths")
        if not isinstance(paths, list):
            errors.append(f"{path}.dependency_paths: dependency_paths must be list")
        else:
            for path_index, dep_path in enumerate(paths):
                if not isinstance(dep_path, list) or not all(isinstance(item, str) and item for item in dep_path):
                    errors.append(f"{path}.dependency_paths[{path_index}]: dependency path must be a list of non-empty strings")

    return True


def target_ids_from_reports(run_dir: Path, errors: List[str]) -> set[str] | None:
    targets_path = configured_reports_dir(run_dir) / "targets.json"
    if not targets_path.exists():
        return set()
    try:
        targets_data = load_targets_artifact(run_dir, {})
    except json.JSONDecodeError as exc:
        errors.append(f"targets.json invalid JSON: {exc}")
        return None
    except Exception as exc:
        errors.append(f"targets.json could not be read safely: {exc}")
        return None
    targets = targets_data.get("targets") if isinstance(targets_data, dict) else None
    if not isinstance(targets, list):
        errors.append("targets.targets: targets must be a list")
        return None
    ids = set()
    for index, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(f"targets.targets[{index}]: target must be an object")
            continue
        target_id = str(target.get("id") or "").strip()
        if target_id:
            ids.add(target_id)
    return ids


def scanner_refs_from_index(run_dir: Path, errors: List[str]) -> set[str]:
    scanner_results_dir = configured_artifact_ref(run_dir, SCANNER_RESULTS_DIR)
    index_path = run_dir / scanner_results_dir / "scanner-index.json"
    if not index_path.exists():
        return set()
    try:
        validate_no_symlink_components(run_dir, scanner_results_dir / "scanner-index.json", field_path="scanner_index")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return set()
    try:
        scanner_index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"scanner-index.json invalid JSON: {exc}")
        return set()
    results = scanner_index.get("results") if isinstance(scanner_index, dict) else None
    if not isinstance(results, list):
        errors.append("scanner_index.results: results must be a list")
        return set()
    refs = {str(index_path.relative_to(run_dir))}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            errors.append(f"scanner_index.results[{index}]: scanner index entry must be an object")
            continue
        for key in ["tool", "path", "normalized_path"]:
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                refs.add(value)
    return refs


def chain_ids_from_reports(run_dir: Path, errors: List[str]) -> set[str]:
    chains_path = configured_reports_dir(run_dir) / "chains.json"
    if not chains_path.exists():
        return set()
    try:
        chains_data = json.loads(chains_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"chains.json invalid JSON: {exc}")
        return set()
    chains = chains_data.get("chains") if isinstance(chains_data, dict) else None
    if not isinstance(chains, list):
        errors.append("chains.chains: chains must be a list")
        return set()
    ids = set()
    for index, chain in enumerate(chains):
        if not isinstance(chain, dict):
            errors.append(f"chains.chains[{index}]: chain must be an object")
            continue
        chain_id = str(chain.get("id") or "").strip()
        if chain_id:
            ids.add(chain_id)
    return ids


def validate_chains(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    chains_path = configured_artifact_path(run_dir, CHAINS_PATH)
    if not chains_path.exists():
        return False
    try:
        chains_data = json.loads(chains_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"chains.json invalid JSON: {exc}")
        return True

    validate_schema(chains_data, load_schema("chains.schema.json"), "chains", errors)
    if not isinstance(chains_data, dict):
        return True
    validate_generated_at(chains_data.get("generated_at"), "chains.generated_at", errors)

    chains = chains_data.get("chains")
    if not isinstance(chains, list):
        errors.append("chains.chains: chains must be a list")
        return True

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    target_ids: set[str] = set()
    target_ids_loaded = False
    target_ids_valid = True
    scanner_refs: set[str] = set()
    scanner_refs_loaded = False
    seen_ids: set[str] = set()
    for index, chain in enumerate(chains):
        path = f"chains.chains[{index}]"
        if not isinstance(chain, dict):
            errors.append(f"{path}: chain must be an object")
            continue

        chain_id = str(chain.get("id") or "").strip()
        if not re.fullmatch(r"CHAIN-[0-9]{3,}", chain_id):
            errors.append(f"{path}.id: chain id must match ^CHAIN-[0-9]{{3,}}$")
        elif chain_id in seen_ids:
            errors.append(f"{path}.id: duplicate chain id {chain_id}")
        seen_ids.add(chain_id)

        if chain.get("severity") not in SEVERITIES:
            errors.append(f"{path}.severity: invalid severity {chain.get('severity')}")
        if chain.get("confidence") not in CONFIDENCES:
            errors.append(f"{path}.confidence: invalid confidence {chain.get('confidence')}")
        if chain.get("status") not in CHAIN_STATUSES:
            errors.append(f"{path}.status: invalid status {chain.get('status')}")

        for key in [
            "findings",
            "targets",
            "scanner_refs",
            "trust_boundaries",
            "attacker_controlled_steps",
            "required_conditions",
            "broken_security_invariants",
            "safe_validation_plan",
            "recommended_remediation",
        ]:
            validate_string_list(chain.get(key), f"{path}.{key}", errors)

        finding_refs = chain.get("findings") if isinstance(chain.get("findings"), list) else []
        target_refs = chain.get("targets") if isinstance(chain.get("targets"), list) else []
        scanner_ref_values = chain.get("scanner_refs") if isinstance(chain.get("scanner_refs"), list) else []
        if not finding_refs and not target_refs and not scanner_ref_values:
            errors.append(f"{path}: chain must reference at least one existing finding, target, or scanner ref")

        for ref_index, finding_ref in enumerate(finding_refs):
            if isinstance(finding_ref, str) and finding_ref not in finding_ids:
                errors.append(f"{path}.findings[{ref_index}]: finding {finding_ref!r} is not present in reports/findings.json")

        if target_refs and not target_ids_loaded:
            loaded_target_ids = target_ids_from_reports(run_dir, errors)
            target_ids_valid = loaded_target_ids is not None
            target_ids = loaded_target_ids or set()
            target_ids_loaded = True
        for ref_index, target_ref in enumerate(target_refs):
            if target_ids_valid and isinstance(target_ref, str) and target_ref not in target_ids:
                errors.append(f"{path}.targets[{ref_index}]: target {target_ref!r} is not present in reports/targets.json")

        if scanner_ref_values and not scanner_refs_loaded:
            scanner_refs = scanner_refs_from_index(run_dir, errors)
            scanner_refs_loaded = True
        for ref_index, scanner_ref in enumerate(scanner_ref_values):
            if isinstance(scanner_ref, str) and scanner_ref not in scanner_refs:
                errors.append(
                    f"{path}.scanner_refs[{ref_index}]: scanner ref {scanner_ref!r} "
                    "is not present in reports/scanner-results/scanner-index.json"
                )

    return True


def validate_adversarial_validation(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    validation_path = configured_artifact_path(run_dir, VALIDATION_PATH)
    if not validation_path.exists():
        return False
    try:
        validation_data = json.loads(validation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"validation.json invalid JSON: {exc}")
        return True

    validate_schema(validation_data, load_schema("validation.schema.json"), "validation", errors)
    if not isinstance(validation_data, dict):
        return True
    validate_generated_at(validation_data.get("generated_at"), "validation.generated_at", errors)
    validate_no_private_reasoning_keys(validation_data, "validation", errors)

    requested_votes_raw = validation_data.get("requested_votes", 1)
    if not isinstance(requested_votes_raw, int) or isinstance(requested_votes_raw, bool) or requested_votes_raw < 1:
        errors.append("validation.requested_votes: must be an integer >= 1 when present")
        requested_votes = 1
    else:
        requested_votes = requested_votes_raw
    vote_policy = str(validation_data.get("vote_policy") or "human-review-on-split")
    if "vote_policy" in validation_data and vote_policy not in VALIDATION_POLICIES:
        errors.append(f"validation.vote_policy: invalid policy {validation_data.get('vote_policy')}")

    validations = validation_data.get("validations")
    if not isinstance(validations, list):
        errors.append("validation.validations: validations must be a list")
        return True

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    chains_path = configured_reports_dir(run_dir) / "chains.json"
    chain_ids: set[str] = set()
    chain_ids_loaded = False
    seen_ids: set[str] = set()
    for index, item in enumerate(validations):
        path = f"validation.validations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: validation must be an object")
            continue

        validation_id = str(item.get("id") or "").strip()
        if not re.fullmatch(r"VAL-[0-9]{3,}", validation_id):
            errors.append(f"{path}.id: validation id must match ^VAL-[0-9]{{3,}}$")
        elif validation_id in seen_ids:
            errors.append(f"{path}.id: duplicate validation id {validation_id}")
        seen_ids.add(validation_id)

        subject_type = item.get("subject_type")
        subject_id = str(item.get("subject_id") or "").strip()
        if subject_type not in VALIDATION_SUBJECT_TYPES:
            errors.append(f"{path}.subject_type: invalid subject type {subject_type}")
        elif subject_type == "finding" and subject_id not in finding_ids:
            errors.append(f"{path}.subject_id: finding {subject_id!r} is not present in reports/findings.json")
        elif subject_type == "chain":
            if not chains_path.exists():
                errors.append(f"{path}.subject_id: chain validation requires reports/chains.json")
            else:
                if not chain_ids_loaded:
                    chain_ids = chain_ids_from_reports(run_dir, errors)
                    chain_ids_loaded = True
            if chains_path.exists() and subject_id not in chain_ids:
                errors.append(f"{path}.subject_id: chain {subject_id!r} is not present in reports/chains.json")

        if item.get("decision") not in VALIDATION_DECISIONS:
            errors.append(f"{path}.decision: invalid decision {item.get('decision')}")
        if item.get("original_severity") not in VALIDATION_SEVERITIES:
            errors.append(f"{path}.original_severity: invalid severity {item.get('original_severity')}")
        if item.get("recommended_severity") not in VALIDATION_SEVERITIES:
            errors.append(f"{path}.recommended_severity: invalid severity {item.get('recommended_severity')}")
        if item.get("original_confidence") not in VALIDATION_CONFIDENCES:
            errors.append(f"{path}.original_confidence: invalid confidence {item.get('original_confidence')}")
        if item.get("recommended_confidence") not in VALIDATION_CONFIDENCES:
            errors.append(f"{path}.recommended_confidence: invalid confidence {item.get('recommended_confidence')}")
        for key in ["evidence_checked", "missing_evidence", "safe_validation_steps"]:
            validate_string_list(item.get(key), f"{path}.{key}", errors)

        if "owner_source" in item and item.get("owner_source") not in VALIDATION_OWNER_SOURCES:
            errors.append(f"{path}.owner_source: invalid owner source {item.get('owner_source')}")
        for key in ["component", "owner_hint"]:
            if key in item and not isinstance(item.get(key), str):
                errors.append(f"{path}.{key}: expected type string, got {json_type_name(item.get(key))}")

        item_policy = str(item.get("vote_policy") or vote_policy)
        if "vote_policy" in item and item_policy not in VALIDATION_POLICIES:
            errors.append(f"{path}.vote_policy: invalid policy {item.get('vote_policy')}")
        votes = item.get("votes")
        if votes is not None and not isinstance(votes, list):
            errors.append(f"{path}.votes: must be list")
            continue
        vote_decisions: list[str] = []
        if isinstance(votes, list):
            seen_vote_ids: set[str] = set()
            for vote_index, vote in enumerate(votes):
                vote_path = f"{path}.votes[{vote_index}]"
                if not isinstance(vote, dict):
                    errors.append(f"{vote_path}: vote must be an object")
                    continue
                vote_id = str(vote.get("vote_id") or "").strip()
                if not re.fullmatch(r"VOTE-[0-9]{3,}", vote_id):
                    errors.append(f"{vote_path}.vote_id: vote id must match ^VOTE-[0-9]{{3,}}$")
                elif vote_id in seen_vote_ids:
                    errors.append(f"{vote_path}.vote_id: duplicate vote id {vote_id}")
                seen_vote_ids.add(vote_id)
                if vote.get("decision") not in VALIDATION_DECISIONS:
                    errors.append(f"{vote_path}.decision: invalid decision {vote.get('decision')}")
                else:
                    vote_decisions.append(str(vote.get("decision")))
                if vote.get("recommended_severity") not in VALIDATION_SEVERITIES:
                    errors.append(f"{vote_path}.recommended_severity: invalid severity {vote.get('recommended_severity')}")
                if vote.get("recommended_confidence") not in VALIDATION_CONFIDENCES:
                    errors.append(f"{vote_path}.recommended_confidence: invalid confidence {vote.get('recommended_confidence')}")
                if not isinstance(vote.get("reasoning_summary"), str):
                    errors.append(f"{vote_path}.reasoning_summary: expected type string, got {json_type_name(vote.get('reasoning_summary'))}")
                for key in ["evidence_checked", "missing_evidence", "safe_validation_steps"]:
                    validate_string_list(vote.get(key), f"{vote_path}.{key}", errors)
            if item.get("vote_count") != len(votes):
                errors.append(f"{path}.vote_count: value must match votes length")
            if requested_votes > 1 and len(votes) != requested_votes:
                errors.append(f"{path}.votes: expected {requested_votes} votes, got {len(votes)}")
            expected_decision = expected_vote_decision(vote_decisions, item_policy)
            if vote_decisions and item.get("decision") != expected_decision:
                errors.append(
                    f"{path}.decision: expected {expected_decision} from {item_policy} vote policy, "
                    f"got {item.get('decision')}"
                )
        elif requested_votes > 1:
            errors.append(f"{path}.votes: required when validation.requested_votes is greater than 1")

    return True


def validate_proof_artifact_path(run_dir: Path, value: Any, *, field_path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReportSafetyError(f"{field_path}: path must be a non-empty string")
    rel = Path(value)
    if rel.is_absolute():
        raise ReportSafetyError(f"{field_path}: proof artifact path must be relative to the run directory")
    if ".." in rel.parts:
        raise ReportSafetyError(f"{field_path}: proof artifact path must not contain '..'")
    proofs_dir = configured_artifact_ref(run_dir, PROOFS_DIR)
    if rel == proofs_dir or proofs_dir not in (rel, *rel.parents):
        raise ReportSafetyError(f"{field_path}: proof artifact path must stay under {proofs_dir.as_posix()}")
    validate_no_symlink_components(run_dir, rel, field_path=field_path)
    expected_root = (run_dir / proofs_dir).resolve(strict=False)
    resolved_target = (run_dir / rel).resolve(strict=False)
    try:
        resolved_target.relative_to(expected_root)
    except ValueError as exc:
        raise ReportSafetyError(f"{field_path}: proof artifact path must not escape {proofs_dir.as_posix()}") from exc
    if not (run_dir / rel).exists():
        raise ReportSafetyError(f"{field_path}: proof artifact not found: {rel.as_posix()}")
    if not (run_dir / rel).is_file():
        raise ReportSafetyError(f"{field_path}: proof artifact must be a regular file: {rel.as_posix()}")


def proof_command_name(argv: list[str]) -> str:
    if not argv:
        return ""
    return Path(argv[0]).name


def validate_structured_proof_command(command: Any, *, field_path: str, errors: List[str]) -> None:
    if isinstance(command, str):
        errors.append(
            f"{field_path}: proof command must be a structured object with argv and safety metadata; "
            "free-form shell strings are not accepted"
        )
        if PROOF_SHELL_METACHARS_RE.search(command):
            errors.append(f"{field_path}: free-form proof command contains shell metacharacters")
        return
    if not isinstance(command, dict):
        errors.append(f"{field_path}: proof command must be an object, got {json_type_name(command)}")
        return

    argv = command.get("argv")
    if not isinstance(argv, list) or not argv:
        errors.append(f"{field_path}.argv: must be a non-empty array of strings")
        argv_strings: list[str] = []
    else:
        argv_strings = []
        for arg_index, arg in enumerate(argv):
            if not isinstance(arg, str) or not arg:
                errors.append(f"{field_path}.argv[{arg_index}]: must be a non-empty string")
            else:
                argv_strings.append(arg)

    command_name = proof_command_name(argv_strings)
    if command_name and command_name not in PROOF_READ_ONLY_COMMANDS:
        errors.append(
            f"{field_path}.argv[0]: command {command_name!r} is not in the safe proof command allowlist "
            f"{sorted(PROOF_READ_ONLY_COMMANDS)}"
        )

    read_only = command.get("read_only")
    writes = command.get("writes")
    network = command.get("network")
    requires_credentials = command.get("requires_credentials")
    cwd_scope = command.get("cwd_scope")

    if read_only is not True:
        errors.append(f"{field_path}.read_only: must be true for safe proof commands")
    if not isinstance(writes, list):
        errors.append(f"{field_path}.writes: must be an array")
        writes_list: list[Any] = []
    else:
        writes_list = writes
        for write_index, write_ref in enumerate(writes_list):
            if not isinstance(write_ref, str) or not write_ref.strip():
                errors.append(f"{field_path}.writes[{write_index}]: must be a non-empty string")
    if writes_list:
        errors.append(f"{field_path}.writes: read-only proof commands must declare no writes")
    if network is not False:
        errors.append(f"{field_path}.network: must be false for safe proof commands")
    if requires_credentials is not False:
        errors.append(f"{field_path}.requires_credentials: must be false for safe proof commands")
    if cwd_scope not in PROOF_COMMAND_CWD_SCOPES:
        errors.append(f"{field_path}.cwd_scope: must be one of {sorted(PROOF_COMMAND_CWD_SCOPES)}")

    if not argv_strings:
        return

    if command_name == "rg":
        for arg in argv_strings[1:]:
            if arg == "--pre" or arg.startswith("--pre=") or arg == "--pre-glob" or arg.startswith("--pre-glob="):
                errors.append(f"{field_path}.argv: rg --pre/--pre-glob is not allowed for safe proof commands")
    elif command_name == "sed":
        for arg in argv_strings[1:]:
            if arg == "-i" or arg.startswith("-i") or arg == "--in-place" or arg.startswith("--in-place="):
                errors.append(f"{field_path}.argv: sed in-place editing is not allowed for safe proof commands")
        if len(argv_strings) < 4 or argv_strings[1] != "-n" or not PROOF_SAFE_SED_SCRIPT_RE.fullmatch(argv_strings[2]):
            errors.append(
                f"{field_path}.argv: sed proof commands are limited to read-only `sed -n START,ENDp FILE` "
                "style excerpts"
            )
        if any(arg.startswith("-") for arg in argv_strings[3:]):
            errors.append(f"{field_path}.argv: sed proof command file arguments must not include additional options")
    elif command_name in {"python", "python3"}:
        if len(argv_strings) != 4 or argv_strings[1:3] != ["-m", "json.tool"]:
            errors.append(
                f"{field_path}.argv: python proof commands are limited to read-only JSON inspection "
                "using exactly `python -m json.tool FILE`"
            )
        elif argv_strings[3].startswith("-"):
            errors.append(f"{field_path}.argv: python json.tool input file must not be an option")
        if any(arg == "-c" for arg in argv_strings[1:]):
            errors.append(f"{field_path}.argv: python -c is not allowed for safe proof commands")


def validate_proofs(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    proofs_path = configured_artifact_path(run_dir, PROOFS_PATH)
    if not proofs_path.exists():
        return False
    try:
        proofs_data = json.loads(proofs_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"proofs.json invalid JSON: {exc}")
        return True

    validate_schema(proofs_data, load_schema("proofs.schema.json"), "proofs", errors)
    if not isinstance(proofs_data, dict):
        return True
    validate_generated_at(proofs_data.get("generated_at"), "proofs.generated_at", errors)

    proofs = proofs_data.get("proofs")
    if not isinstance(proofs, list):
        errors.append("proofs.proofs: proofs must be a list")
        return True

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    seen_ids: set[str] = set()
    for index, proof in enumerate(proofs):
        path = f"proofs.proofs[{index}]"
        if not isinstance(proof, dict):
            errors.append(f"{path}: proof must be an object")
            continue

        proof_id = str(proof.get("id") or "").strip()
        if not re.fullmatch(r"PROOF-[0-9]{3,}", proof_id):
            errors.append(f"{path}.id: proof id must match ^PROOF-[0-9]{{3,}}$")
        elif proof_id in seen_ids:
            errors.append(f"{path}.id: duplicate proof id {proof_id}")
        seen_ids.add(proof_id)

        finding_id = str(proof.get("finding_id") or "").strip()
        if finding_id not in finding_ids:
            errors.append(f"{path}.finding_id: finding {finding_id!r} is not present in reports/findings.json")
        if proof.get("proof_type") not in PROOF_TYPES:
            errors.append(f"{path}.proof_type: invalid proof type {proof.get('proof_type')}")
        if proof.get("status") not in PROOF_STATUSES:
            errors.append(f"{path}.status: invalid status {proof.get('status')}")
        if proof.get("safe_by_design") is not True:
            errors.append(f"{path}.safe_by_design: must be true for safe local proof artifacts")
        if not isinstance(proof.get("evidence"), str):
            errors.append(f"{path}.evidence: expected type string, got {json_type_name(proof.get('evidence'))}")

        for key in ["files_created", "limitations"]:
            validate_string_list(proof.get(key), f"{path}.{key}", errors)

        if not isinstance(proof.get("commands_run"), list):
            errors.append(f"{path}.commands_run: must be list")

        files_created = proof.get("files_created") if isinstance(proof.get("files_created"), list) else []
        for file_index, file_ref in enumerate(files_created):
            try:
                validate_proof_artifact_path(run_dir, file_ref, field_path=f"{path}.files_created[{file_index}]")
            except ReportSafetyError as exc:
                errors.append(str(exc))

        commands_run = proof.get("commands_run") if isinstance(proof.get("commands_run"), list) else []
        for command_index, command in enumerate(commands_run):
            validate_structured_proof_command(command, field_path=f"{path}.commands_run[{command_index}]", errors=errors)

    return True


def validate_remediation_artifact_path(
    run_dir: Path,
    value: Any,
    *,
    field_path: str,
    expected_suffix: str | None = None,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ReportSafetyError(f"{field_path}: path must be a non-empty string")
    rel = Path(value)
    if rel.is_absolute():
        raise ReportSafetyError(f"{field_path}: remediation artifact path must be relative to the run directory")
    if ".." in rel.parts:
        raise ReportSafetyError(f"{field_path}: remediation artifact path must not contain '..'")
    remediation_dir = configured_artifact_ref(run_dir, REMEDIATION_DIR)
    if rel == remediation_dir or remediation_dir not in (rel, *rel.parents):
        raise ReportSafetyError(f"{field_path}: remediation artifact path must stay under {remediation_dir.as_posix()}")
    if expected_suffix and rel.suffix.lower() != expected_suffix:
        raise ReportSafetyError(f"{field_path}: remediation artifact path must end with {expected_suffix}")
    validate_no_symlink_components(run_dir, rel, field_path=field_path)
    expected_root = (run_dir / remediation_dir).resolve(strict=False)
    resolved_target = (run_dir / rel).resolve(strict=False)
    try:
        resolved_target.relative_to(expected_root)
    except ValueError as exc:
        raise ReportSafetyError(f"{field_path}: remediation artifact path must not escape {remediation_dir.as_posix()}") from exc
    if not (run_dir / rel).exists():
        raise ReportSafetyError(f"{field_path}: remediation artifact not found: {rel.as_posix()}")
    if not (run_dir / rel).is_file():
        raise ReportSafetyError(f"{field_path}: remediation artifact must be a regular file: {rel.as_posix()}")


def validate_remediation_candidates(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    remediation_path = configured_artifact_path(run_dir, REMEDIATION_PATH)
    if not remediation_path.exists():
        return False
    try:
        remediation_data = json.loads(remediation_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"remediation-candidates.json invalid JSON: {exc}")
        return True

    validate_schema(remediation_data, load_schema("remediation-candidates.schema.json"), "remediation_candidates", errors)
    secret_like_count = sum(1 for _ in iter_secret_findings(remediation_data, field_path="remediation_candidates"))
    if secret_like_count:
        errors.append(
            "remediation_candidates: contains obvious unredacted secret-like value(s); "
            "remove or redact them before validation"
        )
    if not isinstance(remediation_data, dict):
        return True
    validate_generated_at(remediation_data.get("generated_at"), "remediation_candidates.generated_at", errors)

    candidates = remediation_data.get("candidates")
    if not isinstance(candidates, list):
        errors.append("remediation_candidates.candidates: candidates must be a list")
        return True

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    seen_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        path = f"remediation_candidates.candidates[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{path}: candidate must be an object")
            continue

        candidate_id = str(candidate.get("id") or "").strip()
        if not re.fullmatch(r"PATCH-[0-9]{3,}", candidate_id):
            errors.append(f"{path}.id: candidate id must match ^PATCH-[0-9]{{3,}}$")
        elif candidate_id in seen_ids:
            errors.append(f"{path}.id: duplicate remediation candidate id {candidate_id}")
        seen_ids.add(candidate_id)

        finding_id = str(candidate.get("finding_id") or "").strip()
        if finding_id not in finding_ids:
            errors.append(f"{path}.finding_id: finding {finding_id!r} is not present in reports/findings.json")
        if candidate.get("status") not in REMEDIATION_STATUSES:
            errors.append(f"{path}.status: remediation candidates must remain draft")
        if candidate.get("safe_by_design") is not True:
            errors.append(f"{path}.safe_by_design: must be true for draft remediation candidates")
        if candidate.get("requires_human_review") is not True:
            errors.append(f"{path}.requires_human_review: must be true for draft remediation candidates")
        if not isinstance(candidate.get("summary"), str) or not str(candidate.get("summary")).strip():
            errors.append(f"{path}.summary: expected non-empty string, got {json_type_name(candidate.get('summary'))}")

        for key in ["files_touched", "expected_validation", "limitations"]:
            validate_string_list(candidate.get(key), f"{path}.{key}", errors)
        files_touched = candidate.get("files_touched") if isinstance(candidate.get("files_touched"), list) else []
        for file_index, file_ref in enumerate(files_touched):
            try:
                validate_relative_repo_path(file_ref, field_path=f"{path}.files_touched[{file_index}]")
            except ReportSafetyError as exc:
                errors.append(str(exc))

        for field, expected_suffix in [("patch_file", ".diff"), ("notes_file", ".md"), ("subject_file", ".json")]:
            if field not in candidate:
                if field == "patch_file":
                    errors.append(f"{path}.{field}: missing required remediation artifact path")
                continue
            try:
                validate_remediation_artifact_path(
                    run_dir,
                    candidate.get(field),
                    field_path=f"{path}.{field}",
                    expected_suffix=expected_suffix,
                )
            except ReportSafetyError as exc:
                errors.append(str(exc))

    return True


def validate_patch_validations(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    remediation_root = configured_artifact_path(run_dir, REMEDIATION_DIR)
    if not remediation_root.exists():
        return False
    validation_paths = sorted(remediation_root.rglob(PATCH_VALIDATION_FILENAME))
    if not validation_paths:
        return False

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    candidate_records: set[tuple[str, str]] = set()
    remediation_path = configured_artifact_path(run_dir, REMEDIATION_PATH)
    try:
        remediation_data = json.loads(remediation_path.read_text(encoding="utf-8")) if remediation_path.exists() else {}
    except Exception:
        remediation_data = {}
    if isinstance(remediation_data, dict) and isinstance(remediation_data.get("candidates"), list):
        for candidate in remediation_data["candidates"]:
            if isinstance(candidate, dict):
                candidate_records.add((str(candidate.get("id") or ""), str(candidate.get("finding_id") or "")))

    for validation_path in validation_paths:
        try:
            rel_path = validation_path.resolve(strict=False).relative_to(run_dir.resolve(strict=False))
        except ValueError:
            errors.append(f"{validation_path}: patch validation report must stay under run directory")
            continue
        field_root = f"patch_validation[{rel_path.as_posix()}]"
        try:
            validate_remediation_artifact_path(
                run_dir,
                rel_path.as_posix(),
                field_path=field_root,
                expected_suffix=".json",
            )
            report = json.loads(validation_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{field_root}: invalid patch validation JSON: {exc}")
            continue

        validate_schema(report, load_schema("patch-validation.schema.json"), field_root, errors)
        secret_like_count = sum(1 for _ in iter_secret_findings(report, field_path=field_root))
        if secret_like_count:
            errors.append(f"{field_root}: contains obvious unredacted secret-like value(s); remove or redact them before validation")
        if not isinstance(report, dict):
            continue

        validate_generated_at(report.get("generated_at"), f"{field_root}.generated_at", errors)
        patch_id = str(report.get("patch_id") or "").strip()
        finding_id = str(report.get("finding_id") or "").strip()
        if not re.fullmatch(r"PATCH-[0-9]{3,}", patch_id):
            errors.append(f"{field_root}.patch_id: patch id must match ^PATCH-[0-9]{{3,}}$")
        if finding_id not in finding_ids:
            errors.append(f"{field_root}.finding_id: finding {finding_id!r} is not present in reports/findings.json")
        if candidate_records and (patch_id, finding_id) not in candidate_records:
            errors.append(f"{field_root}: patch_id/finding_id pair is not present in remediation-candidates.json")

        if report.get("network_allowed") is not False:
            errors.append(f"{field_root}.network_allowed: patch validation must not enable network access by default")
        if report.get("patch_applied") not in {True, False}:
            errors.append(f"{field_root}.patch_applied: expected boolean, got {json_type_name(report.get('patch_applied'))}")
        if report.get("build_status") not in PATCH_VALIDATION_BUILD_TEST_STATUSES:
            errors.append(f"{field_root}.build_status: invalid status {report.get('build_status')}")
        if report.get("test_status") not in PATCH_VALIDATION_BUILD_TEST_STATUSES:
            errors.append(f"{field_root}.test_status: invalid status {report.get('test_status')}")
        if report.get("safe_proof_replay_status") not in PATCH_VALIDATION_SAFE_PROOF_STATUSES:
            errors.append(f"{field_root}.safe_proof_replay_status: invalid status {report.get('safe_proof_replay_status')}")
        if report.get("adversarial_review_status") not in PATCH_VALIDATION_ADVERSARIAL_STATUSES:
            errors.append(f"{field_root}.adversarial_review_status: invalid status {report.get('adversarial_review_status')}")
        if report.get("diff_scope_status") not in PATCH_VALIDATION_DIFF_SCOPE_STATUSES:
            errors.append(f"{field_root}.diff_scope_status: invalid status {report.get('diff_scope_status')}")
        if report.get("final_status") not in PATCH_VALIDATION_FINAL_STATUSES:
            errors.append(f"{field_root}.final_status: invalid status {report.get('final_status')}")

        try:
            validate_remediation_artifact_path(
                run_dir,
                report.get("patch_file"),
                field_path=f"{field_root}.patch_file",
                expected_suffix=".diff",
            )
        except ReportSafetyError as exc:
            errors.append(str(exc))

        workspace = report.get("validation_workspace")
        if isinstance(workspace, dict):
            workspace_path = workspace.get("path")
            if not isinstance(workspace_path, str) or not workspace_path.strip():
                errors.append(f"{field_root}.validation_workspace.path: expected non-empty string")
            else:
                rel_workspace = Path(workspace_path)
                if rel_workspace.is_absolute() or ".." in rel_workspace.parts:
                    errors.append(f"{field_root}.validation_workspace.path: must be relative and must not contain '..'")
            if workspace.get("disposed") is not True:
                errors.append(f"{field_root}.validation_workspace.disposed: must be true")

        if not isinstance(report.get("checks"), list):
            errors.append(f"{field_root}.checks: must be list")
        if not isinstance(report.get("commands_run"), list):
            errors.append(f"{field_root}.commands_run: must be list")
        commands = report.get("commands_run") if isinstance(report.get("commands_run"), list) else []
        for command_index, command in enumerate(commands):
            command_path = f"{field_root}.commands_run[{command_index}]"
            if not isinstance(command, dict):
                errors.append(f"{command_path}: command must be an object")
                continue
            if command.get("kind") not in {"build", "test"}:
                errors.append(f"{command_path}.kind: invalid command kind {command.get('kind')}")
            if not isinstance(command.get("argv"), list) or not all(isinstance(item, str) for item in command.get("argv", [])):
                errors.append(f"{command_path}.argv: must be list of strings")
            if command.get("status") not in {"passed", "failed", "rejected"}:
                errors.append(f"{command_path}.status: invalid command status {command.get('status')}")
            if command.get("cwd") != "validation_workspace":
                errors.append(f"{command_path}.cwd: must be validation_workspace")

        if report.get("final_status") == "validated":
            if report.get("patch_applied") is not True:
                errors.append(f"{field_root}.final_status: validated requires patch_applied=true")
            if report.get("diff_scope_status") != "bounded":
                errors.append(f"{field_root}.final_status: validated requires diff_scope_status=bounded")
            for key in ["build_status", "test_status", "safe_proof_replay_status", "adversarial_review_status"]:
                if report.get(key) == "failed":
                    errors.append(f"{field_root}.final_status: validated cannot include failed {key}")

    return True


def validate_no_forbidden_novelty_payload(value: Any, path: str, errors: List[str]) -> None:
    forbidden = {
        "evidence",
        "root_cause",
        "impact",
        "issue_body",
        "issue_body_text",
        "minimal_remediation",
        "regression_test_idea",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key in forbidden and not path.endswith(".hashes"):
                errors.append(f"{path}.{key}: novelty ledger must not copy raw finding evidence or issue body content")
            validate_no_forbidden_novelty_payload(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_no_forbidden_novelty_payload(item, f"{path}[{index}]", errors)


def validate_novelty_ledger(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    novelty_path = configured_artifact_path(run_dir, NOVELTY_PATH)
    if not novelty_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, configured_artifact_ref(run_dir, NOVELTY_PATH), field_path="known_findings")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        novelty_data = json.loads(novelty_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"known_findings invalid JSON: {exc}")
        return True
    if not isinstance(novelty_data, dict):
        errors.append(f"known_findings: expected type object, got {json_type_name(novelty_data)}")
        return True

    validate_schema(novelty_data, load_schema("novelty.schema.json"), "known_findings", errors)
    validate_generated_at(novelty_data.get("generated_at"), "known_findings.generated_at", errors)
    if novelty_data.get("source") != "local-report-artifacts":
        errors.append("known_findings.source: must be local-report-artifacts")
    safety = novelty_data.get("safety") if isinstance(novelty_data.get("safety"), dict) else {}
    if safety.get("local_artifacts_only") is not True:
        errors.append("known_findings.safety.local_artifacts_only: must be true")
    if safety.get("raw_evidence_copied") is not False:
        errors.append("known_findings.safety.raw_evidence_copied: must be false")
    if safety.get("secrets_copied") is not False:
        errors.append("known_findings.safety.secrets_copied: must be false")
    if safety.get("accepted_risk_exported_by_default") is not False:
        errors.append("known_findings.safety.accepted_risk_exported_by_default: must be false")
    validate_no_forbidden_novelty_payload(novelty_data, "known_findings", errors)
    secret_like_count = sum(1 for _ in iter_secret_findings(novelty_data, field_path="known_findings"))
    if secret_like_count:
        errors.append("known_findings: contains obvious unredacted secret-like value(s); remove or hash them before validation")

    finding_by_id = {str(finding.get("id") or ""): finding for finding in findings if isinstance(finding, dict)}
    records = novelty_data.get("findings")
    if not isinstance(records, list):
        errors.append("known_findings.findings: findings must be a list")
        records = []
    seen_ids: set[str] = set()
    status_counts: dict[str, int] = {status: 0 for status in NOVELTY_STATUSES}
    suppressed_count = 0
    for index, record in enumerate(records):
        path = f"known_findings.findings[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{path}: finding novelty record must be an object")
            continue
        finding_id = str(record.get("finding_id") or "")
        if finding_id in seen_ids:
            errors.append(f"{path}.finding_id: duplicate novelty record for {finding_id}")
        seen_ids.add(finding_id)
        current = finding_by_id.get(finding_id)
        if current is None:
            errors.append(f"{path}.finding_id: finding {finding_id!r} is not present in reports/findings.json")
        elif str(record.get("fingerprint") or "") != str(current.get("fingerprint") or ""):
            errors.append(f"{path}.fingerprint: value does not match reports/findings.json")
        status = str(record.get("novelty_status") or "")
        if status not in NOVELTY_STATUSES:
            errors.append(f"{path}.novelty_status: invalid status {status!r}")
        else:
            status_counts[status] = status_counts.get(status, 0) + 1
        if status in NOVELTY_SUPPRESSED_PUBLICATION_STATUSES:
            suppressed_count += 1
            if record.get("issue_recommended") is not False:
                errors.append(f"{path}.issue_recommended: {status} must not be recommended for publication by default")
        accepted = record.get("accepted_risk") if isinstance(record.get("accepted_risk"), dict) else {}
        if status == "accepted-risk" and accepted.get("active") is not True:
            errors.append(f"{path}.accepted_risk.active: accepted-risk status requires active=true")
        hashes = record.get("hashes") if isinstance(record.get("hashes"), dict) else {}
        for key in [
            "root_cause",
            "source_to_sink",
            "evidence",
            "impact",
            "affected_locations",
            "entry_point",
            "trust_boundary",
            "chain_membership",
        ]:
            if not re.fullmatch(r"[a-f0-9]{24}", str(hashes.get(key) or "")):
                errors.append(f"{path}.hashes.{key}: expected 24 lowercase hex characters")

    summary = novelty_data.get("summary") if isinstance(novelty_data.get("summary"), dict) else {}
    if summary.get("finding_count") != len(records):
        errors.append("known_findings.summary.finding_count: value does not match findings length")
    if summary.get("suppressed_publication_count") != suppressed_count:
        errors.append("known_findings.summary.suppressed_publication_count: value does not match suppressed statuses")
    summary_counts = summary.get("status_counts") if isinstance(summary.get("status_counts"), dict) else {}
    for status, count in status_counts.items():
        if summary_counts.get(status) != count:
            errors.append(f"known_findings.summary.status_counts.{status}: value does not match findings")
    return True


def validate_traces(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    traces_path = configured_artifact_path(run_dir, TRACES_PATH)
    if not traces_path.exists():
        return False
    try:
        traces_data = json.loads(traces_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"traces.json invalid JSON: {exc}")
        return True

    validate_schema(traces_data, load_schema("traces.schema.json"), "traces", errors)
    if not isinstance(traces_data, dict):
        return True
    validate_generated_at(traces_data.get("generated_at"), "traces.generated_at", errors)

    traces = traces_data.get("traces")
    if not isinstance(traces, list):
        errors.append("traces.traces: traces must be a list")
        return True

    finding_ids = {str(finding.get("id")) for finding in findings if isinstance(finding, dict) and finding.get("id")}
    seen_ids: set[str] = set()
    for index, trace in enumerate(traces):
        path = f"traces.traces[{index}]"
        if not isinstance(trace, dict):
            errors.append(f"{path}: trace must be an object")
            continue

        trace_id = str(trace.get("id") or "").strip()
        if not re.fullmatch(r"TRACE-[0-9]{3,}", trace_id):
            errors.append(f"{path}.id: trace id must match ^TRACE-[0-9]{{3,}}$")
        elif trace_id in seen_ids:
            errors.append(f"{path}.id: duplicate trace id {trace_id}")
        seen_ids.add(trace_id)

        finding_id = str(trace.get("finding_id") or "").strip()
        if finding_id not in finding_ids:
            errors.append(f"{path}.finding_id: finding {finding_id!r} is not present in reports/findings.json")
        for key in ["producer_repo", "consumer_repo", "sink", "evidence"]:
            if not isinstance(trace.get(key), str) or not str(trace.get(key)).strip():
                errors.append(f"{path}.{key}: expected non-empty string, got {json_type_name(trace.get(key))}")
        for key in ["entry_points", "limitations"]:
            validate_string_list(trace.get(key), f"{path}.{key}", errors)
        if trace.get("attacker_control") not in ASSESSMENT_STATUSES:
            errors.append(f"{path}.attacker_control: invalid assessment value {trace.get('attacker_control')}")
        if trace.get("reachable") not in ASSESSMENT_STATUSES:
            errors.append(f"{path}.reachable: invalid assessment value {trace.get('reachable')}")
        if trace.get("status") not in TRACE_STATUSES:
            errors.append(f"{path}.status: invalid status {trace.get('status')}")

    return True








def validate_metrics_payload(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in METRICS_FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: metrics must not copy raw evidence or issue body content")
            validate_metrics_payload(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_metrics_payload(item, f"{path}[{index}]", errors)


def validate_embedded_report_freshness(value: Any, path: str, errors: List[str]) -> None:
    if value is None:
        return
    try:
        validate_public_summary(value)
    except FreshnessError as exc:
        errors.append(f"{path}: {exc}")


def validate_workflow_execution_summary_contract(
    value: Any,
    path: str,
    schema_name: str,
    errors: List[str],
) -> None:
    if value is None:
        return
    schema = load_schema(schema_name)
    definition = schema.get("$defs", {}).get("workflowExecutionSummary")
    if not isinstance(definition, dict):
        errors.append(f"{path}: workflow execution summary schema definition is missing")
        return
    validate_schema(value, definition, path, errors)
    if not isinstance(value, dict):
        return
    allowed_fields = set(definition.get("properties", {}))
    if set(value) - allowed_fields:
        errors.append(f"{path}: contains unsupported fields")
    by_status = value.get("by_status")
    if isinstance(by_status, dict) and set(by_status) != WORKFLOW_EXECUTION_STAGE_STATUSES:
        errors.append(f"{path}.by_status: must contain exactly the supported workflow stage statuses")
    if isinstance(by_status, dict) and any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in by_status.values()
    ):
        errors.append(f"{path}.by_status: counts must be non-negative integers")
    absence_reasons = value.get("absence_reasons")
    if isinstance(absence_reasons, dict) and set(absence_reasons) - WORKFLOW_EXECUTION_ABSENCE_REASONS:
        errors.append(f"{path}.absence_reasons: contains unsupported absence reasons")
    if isinstance(absence_reasons, dict) and any(
        not isinstance(count, int) or isinstance(count, bool) or count < 0
        for count in absence_reasons.values()
    ):
        errors.append(f"{path}.absence_reasons: counts must be non-negative integers")
    for field in ("failed_stages", "scoped_skip_stages", "blocked_dependency_stages"):
        identifiers = value.get(field)
        if isinstance(identifiers, list) and any(
            not isinstance(identifier, str) or not SAFE_WORKFLOW_ID_RE.fullmatch(identifier)
            for identifier in identifiers
        ):
            errors.append(f"{path}.{field}: contains an invalid stage id")
        if (
            isinstance(identifiers, list)
            and all(isinstance(identifier, str) for identifier in identifiers)
            and len(identifiers) != len(set(identifiers))
        ):
            errors.append(f"{path}.{field}: stage ids must be unique")
    provider_stage_lists: dict[str, list[str] | None] = {}
    for field in ("provider_failure_stages", "recovered_provider_failure_stages"):
        identifiers = value.get(field)
        provider_stage_lists[field] = identifiers if isinstance(identifiers, list) else None
        if identifiers is not None:
            if not isinstance(identifiers, list) or any(
                not isinstance(identifier, str) or not SAFE_WORKFLOW_ID_RE.fullmatch(identifier)
                for identifier in identifiers
            ):
                errors.append(f"{path}.{field}: contains an invalid stage id")
            elif len(identifiers) != len(set(identifiers)):
                errors.append(f"{path}.{field}: stage ids must be unique")
    provider_failure_stages = provider_stage_lists["provider_failure_stages"]
    recovered_provider_failure_stages = provider_stage_lists["recovered_provider_failure_stages"]
    provider_classes = value.get("provider_failures_by_class")
    if provider_classes is not None:
        if not isinstance(provider_classes, dict) or set(provider_classes) - set(PROVIDER_ERROR_CLASSES):
            errors.append(f"{path}.provider_failures_by_class: contains an unsupported provider class")
        elif any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in provider_classes.values()
        ):
            errors.append(f"{path}.provider_failures_by_class: counts must be non-negative integers")
    provider_count = value.get("provider_failure_count")
    provider_summary_fields = {
        "provider_failure_count",
        "retryable_provider_failure_count",
        "resume_recommended_count",
        "active_provider_failure_count",
        "recovered_provider_failure_count",
        "provider_failures_by_class",
        "provider_failure_stages",
        "recovered_provider_failure_stages",
    }
    present_provider_summary_fields = provider_summary_fields.intersection(value)
    if present_provider_summary_fields and present_provider_summary_fields != provider_summary_fields:
        errors.append(f"{path}: provider failure summary fields must be complete")
    if isinstance(provider_count, int) and not isinstance(provider_count, bool) and provider_count >= 0:
        if isinstance(provider_failure_stages, list) and provider_count < len(provider_failure_stages):
            errors.append(f"{path}.provider_failure_stages: length must not exceed provider_failure_count")
        if isinstance(provider_classes, dict) and all(
            isinstance(count, int) and not isinstance(count, bool) and count >= 0
            for count in provider_classes.values()
        ) and provider_count != sum(provider_classes.values()):
            errors.append(f"{path}.provider_failures_by_class: counts must match provider_failure_count")
        for field in ("retryable_provider_failure_count", "resume_recommended_count"):
            count = value.get(field)
            if isinstance(count, int) and not isinstance(count, bool) and not 0 <= count <= provider_count:
                errors.append(f"{path}.{field}: must not exceed provider_failure_count")
        for field in ("active_provider_failure_count", "recovered_provider_failure_count"):
            count = value.get(field)
            if isinstance(count, int) and not isinstance(count, bool) and not 0 <= count <= provider_count:
                errors.append(f"{path}.{field}: must not exceed provider_failure_count")
        recovered_count = value.get("recovered_provider_failure_count")
        if (
            isinstance(recovered_count, int)
            and not isinstance(recovered_count, bool)
            and isinstance(recovered_provider_failure_stages, list)
            and recovered_count != len(recovered_provider_failure_stages)
        ):
            errors.append(
                f"{path}.recovered_provider_failure_stages: length must match recovered_provider_failure_count"
            )
        if (
            isinstance(provider_failure_stages, list)
            and isinstance(recovered_provider_failure_stages, list)
            and set(recovered_provider_failure_stages) - set(provider_failure_stages)
        ):
            errors.append(f"{path}.recovered_provider_failure_stages: must be provider-failure stages")
        active_count = value.get("active_provider_failure_count")
        if (
            isinstance(active_count, int)
            and not isinstance(active_count, bool)
            and isinstance(provider_failure_stages, list)
            and active_count > len(provider_failure_stages)
        ):
            errors.append(f"{path}.active_provider_failure_count: must not exceed provider-failure stages")
    profile = value.get("profile")
    if not isinstance(profile, str) or not SAFE_WORKFLOW_ID_RE.fullmatch(profile):
        errors.append(f"{path}.profile: must be a bounded safe identifier")
    if value.get("status") not in {"not-recorded", "running", "paused", "blocked", "succeeded"}:
        errors.append(f"{path}.status: unsupported workflow execution status")
    if value.get("artifact_present") is True and value.get("absence_reason") is not None:
        errors.append(f"{path}.absence_reason: must be null when the artifact is present")
    if value.get("artifact_present") is False and value.get("absence_reason") != "workflow_execution_not_recorded":
        errors.append(f"{path}.absence_reason: must explain that workflow execution was not recorded")
    if isinstance(by_status, dict) and all(
        isinstance(count, int) and not isinstance(count, bool) and count >= 0
        for count in by_status.values()
    ):
        if value.get("stage_count") != sum(by_status.values()):
            errors.append(f"{path}.stage_count: must match workflow stage status counts")
        for count_field, status_name, list_field in (
            ("failed_count", "failed", "failed_stages"),
            ("skipped_by_scope_count", "skipped_by_scope", "scoped_skip_stages"),
            ("blocked_dependency_count", "blocked_dependency", "blocked_dependency_stages"),
        ):
            if value.get(count_field) != by_status.get(status_name):
                errors.append(f"{path}.{count_field}: must match workflow stage status counts")
            identifiers = value.get(list_field)
            if isinstance(identifiers, list) and value.get(count_field) != len(identifiers):
                errors.append(f"{path}.{list_field}: length must match {count_field}")
    if value.get("artifact_present") is True and isinstance(absence_reasons, dict) and all(
        isinstance(count, int) and not isinstance(count, bool) and count >= 0
        for count in absence_reasons.values()
    ) and value.get("absent_stage_count") != sum(absence_reasons.values()):
        errors.append(f"{path}.absent_stage_count: must match absence reason counts")
    if bool(value.get("resume_available")) != (value.get("resume_stage") is not None):
        errors.append(f"{path}.resume_available: must match whether resume_stage is set")
    resume_stage = value.get("resume_stage")
    if resume_stage is not None and (
        not isinstance(resume_stage, str) or not SAFE_WORKFLOW_ID_RE.fullmatch(resume_stage)
    ):
        errors.append(f"{path}.resume_stage: must be a bounded safe stage id")
    total_duration = value.get("total_duration_ms")
    maximum_duration = value.get("maximum_duration_ms")
    if (
        isinstance(total_duration, int)
        and not isinstance(total_duration, bool)
        and isinstance(maximum_duration, int)
        and not isinstance(maximum_duration, bool)
        and maximum_duration > total_duration
    ):
        errors.append(f"{path}.maximum_duration_ms: must not exceed total_duration_ms")


def validate_scanner_runs(run_dir: Path, errors: List[str]) -> bool:
    try:
        reports = configured_reports_dir(run_dir)
        reports_rel = reports.relative_to(run_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        errors.append(f"scanner_runs: invalid reports_dir: {exc}")
        return True
    scanner_runs_path = reports_rel / "scanner-runs.json"
    scanner_results_dir = reports_rel / "scanner-results"
    normalized_scanner_results_dir = scanner_results_dir / "normalized"
    scanner_index_path = scanner_results_dir / "scanner-index.json"
    report_path = run_dir / scanner_runs_path
    if not report_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, scanner_runs_path, field_path="scanner_runs")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"scanner-runs.json invalid JSON: {exc}")
        return True
    if not isinstance(report, dict):
        errors.append(f"scanner_runs: expected type object, got {json_type_name(report)}")
        return True
    validate_schema(report, load_schema("scanner-runs.schema.json"), "scanner_runs", errors)
    validate_generated_at(report.get("generated_at"), "scanner_runs.generated_at", errors)
    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    if safety != {
        "public_safe": True,
        "raw_scanner_bodies_copied": False,
        "secret_values_copied": False,
        "review_only": True,
    }:
        errors.append("scanner_runs.safety: public-safe review-only scanner safety flags are required")
    if list(iter_secret_findings(report, field_path="scanner_runs")):
        errors.append("scanner_runs: contains obvious unredacted secret-like value(s)")

    runs = report.get("runs") if isinstance(report.get("runs"), list) else []
    status_counts: dict[str, int] = {}
    adapter_counts: dict[str, int] = {}
    durations: list[int] = []
    result_count = 0
    normalized_leads_count = 0
    redaction_count = 0
    for index, item in enumerate(runs):
        if not isinstance(item, dict):
            continue
        path = f"scanner_runs.runs[{index}]"
        validate_generated_at(item.get("started_at"), f"{path}.started_at", errors)
        validate_generated_at(item.get("ended_at"), f"{path}.ended_at", errors)
        started = parse_event_time(item.get("started_at"))
        ended = parse_event_time(item.get("ended_at"))
        if started and ended and ended < started:
            errors.append(f"{path}.ended_at: must not precede started_at")
        status = str(item.get("status") or "unknown")
        adapter_id = str(item.get("adapter_id") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        adapter_counts[adapter_id] = adapter_counts.get(adapter_id, 0) + 1
        duration = item.get("duration_ms")
        if isinstance(duration, int) and not isinstance(duration, bool) and duration >= 0:
            durations.append(duration)
        for field, accumulator in (
            ("result_count", "result_count"),
            ("normalized_leads_count", "normalized_leads_count"),
            ("redaction_count", "redaction_count"),
        ):
            value = item.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                if accumulator == "result_count":
                    result_count += value
                elif accumulator == "normalized_leads_count":
                    normalized_leads_count += value
                else:
                    redaction_count += value
        normalized_ref = item.get("normalized_result_ref")
        if normalized_ref is not None:
            try:
                validate_run_artifact_path(
                    run_dir,
                    normalized_ref,
                    field_path=f"{path}.normalized_result_ref",
                    required_root=normalized_scanner_results_dir,
                    require_json=True,
                    missing_label="normalized scanner artifact",
                )
            except ReportSafetyError as exc:
                errors.append(str(exc))
        index_ref = item.get("scanner_index_ref")
        if index_ref is not None:
            if index_ref != scanner_index_path.as_posix():
                errors.append(
                    f"{path}.scanner_index_ref: must reference {scanner_index_path.as_posix()}"
                )
                continue
            try:
                validate_run_artifact_path(
                    run_dir,
                    index_ref,
                    field_path=f"{path}.scanner_index_ref",
                    required_root=scanner_results_dir,
                    require_json=True,
                    missing_label="scanner index",
                )
            except ReportSafetyError as exc:
                errors.append(str(exc))

    expected_summary = {
        "run_count": len(runs),
        "by_status": dict(sorted(status_counts.items())),
        "by_adapter": dict(sorted(adapter_counts.items())),
        "total_duration_ms": sum(durations),
        "maximum_duration_ms": max(durations, default=0),
        "result_count": result_count,
        "normalized_leads_count": normalized_leads_count,
        "redaction_count": redaction_count,
    }
    if report.get("summary") != expected_summary:
        errors.append("scanner_runs.summary: value does not match scanner run records")
    try:
        validate_scanner_runs_for_run(run_dir, report)
    except ScannerReportError as exc:
        errors.append(f"scanner_runs: {exc}")
    return True


def validate_scanner_readiness_reports(run_dir: Path, errors: List[str]) -> bool:
    try:
        reports = configured_reports_dir(run_dir)
        reports_rel = reports.relative_to(run_dir)
    except (OSError, ValueError) as exc:
        errors.append(f"scanner_readiness: invalid reports_dir: {exc}")
        return True
    readiness_rel = reports_rel / "scanner-readiness"
    readiness_dir = run_dir / readiness_rel
    if readiness_dir.is_symlink():
        errors.append("scanner_readiness: report directory must not be a symlink")
        return True
    if not readiness_dir.exists():
        return False
    if not readiness_dir.is_dir():
        errors.append("scanner_readiness: report path must be a directory")
        return True
    try:
        validate_no_symlink_components(run_dir, readiness_rel, field_path="scanner_readiness")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    entries = sorted(readiness_dir.iterdir())
    if len(entries) > 2:
        errors.append("scanner_readiness: at most one report per approved adapter is allowed")
    for report_path in entries:
        if report_path.is_symlink() or not report_path.is_file() or report_path.suffix != ".json":
            errors.append("scanner_readiness: only regular non-symlink JSON report files are allowed")
            continue
        try:
            report = read_scanner_readiness_report(report_path)
        except (OSError, ScannerReadinessError) as exc:
            errors.append(f"scanner_readiness.{report_path.name}: invalid bounded report: {exc}")
            continue
        validate_schema(
            report,
            load_schema("scanner-readiness.schema.json"),
            f"scanner_readiness.{report_path.stem}",
            errors,
        )
        if report_path.stem != report["adapter_id"]:
            errors.append(f"scanner_readiness.{report_path.name}: adapter_id must match the filename")
    return True


def validate_metrics(run_dir: Path, errors: List[str]) -> bool:
    metrics_path = configured_artifact_path(run_dir, METRICS_PATH)
    if not metrics_path.exists():
        return False
    try:
        metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"metrics.json invalid JSON: {exc}")
        return True
    if not isinstance(metrics_data, dict):
        errors.append(f"metrics: expected type object, got {json_type_name(metrics_data)}")
        return True
    validate_schema(metrics_data, load_schema("metrics.schema.json"), "metrics", errors)
    validate_embedded_report_freshness(metrics_data.get("report_freshness"), "metrics.report_freshness", errors)
    validate_workflow_execution_summary_contract(
        metrics_data.get("workflow_execution"),
        "metrics.workflow_execution",
        "metrics.schema.json",
        errors,
    )
    metrics_summary = metrics_data.get("summary") if isinstance(metrics_data.get("summary"), dict) else {}
    validate_workflow_execution_summary_contract(
        metrics_summary.get("workflow_execution"),
        "metrics.summary.workflow_execution",
        "metrics.schema.json",
        errors,
    )
    validate_generated_at(metrics_data.get("generated_at"), "metrics.generated_at", errors)
    if metrics_data.get("source") != "local-report-artifacts":
        errors.append("metrics.source: metrics must be generated from local-report-artifacts")
    safety = metrics_data.get("safety") if isinstance(metrics_data.get("safety"), dict) else {}
    if safety.get("local_artifacts_only") is not True:
        errors.append("metrics.safety.local_artifacts_only: must be true")
    if safety.get("raw_evidence_copied") is not False:
        errors.append("metrics.safety.raw_evidence_copied: must be false")
    if safety.get("secrets_copied") is not False:
        errors.append("metrics.safety.secrets_copied: must be false")
    from metrics import MetricsError, scanner_readiness_metrics, target_queue_metrics
    try:
        expected_readiness = scanner_readiness_metrics(configured_reports_dir(run_dir))
    except (OSError, ValueError, MetricsError) as exc:
        errors.append(f"metrics.scanner_readiness: unable to validate source reports safely: {exc}")
    else:
        if metrics_data.get("scanner_readiness") != expected_readiness:
            errors.append("metrics.scanner_readiness: counts must match scanner readiness reports")
        scanner_summary = metrics_data.get("summary", {}).get("scanner", {})
        expected_compact = {
            "readiness_artifact_present": expected_readiness["artifact_present"],
            "readiness_report_count": expected_readiness["report_count"],
            "readiness_by_state": expected_readiness["by_state"],
            "readiness_by_reason": expected_readiness["by_reason"],
        }
        if isinstance(scanner_summary, dict) and scanner_summary and any(
            scanner_summary.get(key) != value for key, value in expected_compact.items()
        ):
            errors.append("metrics.summary.scanner: readiness counts must match scanner readiness reports")

    try:
        targets_path = configured_reports_dir(run_dir) / "targets.json"
        targets_data = load_targets_artifact(run_dir, {}) if targets_path.exists() else {}
        expected_target_queue = target_queue_metrics(targets_data)
    except (OSError, ValueError, MetricsError) as exc:
        errors.append(f"metrics.target_queue: unable to validate reports/targets.json safely: {exc}")
    else:
        if metrics_data.get("target_queue") != expected_target_queue:
            errors.append("metrics.target_queue: counts must match reports/targets.json queue summary")
    validate_metrics_payload(metrics_data, "metrics", errors)
    return True


def validate_workflow_profile(run_dir: Path, errors: List[str]) -> bool:
    profile_path = configured_artifact_path(run_dir, WORKFLOW_PROFILE_PATH)
    if not profile_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, configured_artifact_ref(run_dir, WORKFLOW_PROFILE_PATH), field_path="workflow_profile")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"workflow_profile invalid JSON: {exc}")
        return True
    if not isinstance(profile_data, dict):
        errors.append(f"workflow_profile: expected type object, got {json_type_name(profile_data)}")
        return True
    validate_schema(profile_data, load_schema("workflow-profile.schema.json"), "workflow_profile", errors)
    validate_generated_at(profile_data.get("generated_at"), "workflow_profile.generated_at", errors)
    errors.extend(validate_workflow_profile_payload(profile_data))
    return True


def validate_workflow_execution_payload(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in WORKFLOW_EXECUTION_FORBIDDEN_KEYS:
                errors.append(
                    f"{path}.{key}: workflow execution must not copy raw prompts, findings, "
                    "evidence, credentials, private reasoning, command output, or Issue bodies"
                )
            validate_workflow_execution_payload(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_workflow_execution_payload(item, f"{path}[{index}]", errors)


def validate_closed_schema_fields(value: Any, schema: dict[str, Any], path: str, errors: List[str]) -> None:
    """Enforce closed object fields for the workflow report schema subset."""

    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            errors.append(f"{path}: contains fields outside the closed workflow execution contract")
        for key, item in value.items():
            subschema = properties.get(key)
            if isinstance(subschema, dict):
                validate_closed_schema_fields(item, subschema, f"{path}.{key}", errors)
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            validate_closed_schema_fields(item, schema["items"], f"{path}[{index}]", errors)


def validate_workflow_execution(run_dir: Path, errors: List[str]) -> bool:
    execution_path = configured_artifact_path(run_dir, WORKFLOW_EXECUTION_PATH)
    if not execution_path.exists():
        return False
    try:
        validate_no_symlink_components(
            run_dir,
            configured_artifact_ref(run_dir, WORKFLOW_EXECUTION_PATH),
            field_path="workflow_execution",
        )
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        execution = json.loads(execution_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"workflow_execution invalid JSON: {exc}")
        return True
    if not isinstance(execution, dict):
        errors.append(f"workflow_execution: expected type object, got {json_type_name(execution)}")
        return True
    execution_schema = load_schema("workflow-execution.schema.json")
    validate_schema(execution, execution_schema, "workflow_execution", errors)
    validate_closed_schema_fields(execution, execution_schema, "workflow_execution", errors)
    validate_generated_at(execution.get("generated_at"), "workflow_execution.generated_at", errors)
    validate_workflow_execution_payload(execution, "workflow_execution", errors)
    for secret_error in iter_secret_findings(execution, field_path="workflow_execution"):
        errors.append(secret_error)
    try:
        context = load_context(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"workflow_execution: could not load run context: {exc}")
        context = {}
    for field in ("run_id", "repo"):
        expected = context.get(field)
        if isinstance(expected, str) and execution.get(field) != expected:
            errors.append(f"workflow_execution.{field}: must match context.json")

    stages = execution.get("stages") if isinstance(execution.get("stages"), list) else []
    stage_ids = [str(stage.get("id") or "") for stage in stages if isinstance(stage, dict)]
    if len(stage_ids) != len(set(stage_ids)):
        errors.append("workflow_execution.stages: stage ids must be unique")
    statuses: Counter[str] = Counter()
    absence_reasons: Counter[str] = Counter()
    provider_classes: Counter[str] = Counter()
    provider_failure_stages: list[str] = []
    provider_failure_count = 0
    retryable_provider_failure_count = 0
    resume_recommended_count = 0
    active_provider_failure_count = 0
    recovered_provider_failure_count = 0
    durations: list[int] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        path = f"workflow_execution.stages[{index}]"
        status = str(stage.get("status") or "")
        statuses[status] += 1
        provider_error = stage.get("provider_error")
        provider_history = stage.get("provider_failure_history")
        error_category = stage.get("error_category")
        provider_error_valid = provider_error is None
        if "provider_error" in stage:
            try:
                validate_provider_error(provider_error, allow_none=True)
                provider_error_valid = True
            except ProviderFailureError:
                errors.append(f"{path}.provider_error: invalid bounded provider failure metadata")
        provider_history_valid = provider_history is None
        if "provider_failure_history" in stage:
            try:
                validate_provider_failure_history(provider_history, allow_none=True)
                provider_history_valid = True
            except ProviderFailureError:
                errors.append(f"{path}.provider_failure_history: invalid bounded provider failure history")
        if (error_category == "provider_error") != (isinstance(provider_error, dict)):
            errors.append(f"{path}.provider_error: must match error_category")
        if isinstance(provider_error, dict):
            if status != "failed":
                errors.append(f"{path}.provider_error: provider failure metadata requires failed status")
            if (
                not isinstance(provider_history, dict)
                or not provider_history_valid
                or not provider_error_valid
                or provider_history.get("last_error") != provider_error
                or provider_history.get("recovered") is not False
            ):
                errors.append(f"{path}.provider_failure_history: must bind the current provider failure")
        if isinstance(provider_history, dict) and provider_history_valid:
            attempt = stage.get("attempt")
            if isinstance(attempt, int) and not isinstance(attempt, bool) and provider_history["count"] > attempt:
                errors.append(f"{path}.provider_failure_history.count: must not exceed stage attempts")
            if provider_history["recovered"] != (status == "succeeded"):
                errors.append(f"{path}.provider_failure_history.recovered: must match succeeded stage status")
            stage_id = str(stage.get("id") or "")
            provider_failure_stages.append(stage_id)
            provider_failure_count += provider_history["count"]
            provider_classes.update(provider_history["by_class"])
            retryable_provider_failure_count += provider_history["retryable_count"]
            resume_recommended_count += provider_history["resume_recommended_count"]
            active_provider_failure_count += int(isinstance(provider_error, dict))
            if provider_history["recovered"]:
                recovered_provider_failure_count += 1
        absence_reason = stage.get("absence_reason")
        if isinstance(absence_reason, str):
            absence_reasons[absence_reason] += 1
        duration = stage.get("duration_ms")
        if isinstance(duration, int) and not isinstance(duration, bool) and duration >= 0:
            durations.append(duration)
        started_at = stage.get("started_at")
        ended_at = stage.get("ended_at")
        if started_at is not None:
            validate_generated_at(started_at, f"{path}.started_at", errors)
        if ended_at is not None:
            validate_generated_at(ended_at, f"{path}.ended_at", errors)
        started = parse_event_time(started_at)
        ended = parse_event_time(ended_at)
        expected_duration = 0
        if started is not None and ended is not None:
            try:
                if ended < started:
                    errors.append(f"{path}.ended_at: must not precede started_at")
                expected_duration = max(0, int((ended - started).total_seconds() * 1000))
            except (OverflowError, TypeError, ValueError):
                errors.append(f"{path}: timestamps must use compatible ISO-8601 timezone forms")
        if duration != expected_duration:
            errors.append(f"{path}.duration_ms: value does not match stage timestamps")
        dependencies = stage.get("depends_on") if isinstance(stage.get("depends_on"), list) else []
        blocked_by = stage.get("blocked_by") if isinstance(stage.get("blocked_by"), list) else []
        for dependency in dependencies:
            if dependency not in stage_ids:
                errors.append(f"{path}.depends_on: unknown stage {dependency!r}")
        for dependency in blocked_by:
            if dependency not in dependencies:
                errors.append(f"{path}.blocked_by: {dependency!r} is not a declared dependency")
        for artifact_index, artifact in enumerate(stage.get("output_artifact_refs") or []):
            validate_command_event_artifact_path(
                run_dir,
                artifact,
                field_path=f"{path}.output_artifact_refs[{artifact_index}]",
                errors=errors,
            )

    summary = execution.get("summary") if isinstance(execution.get("summary"), dict) else {}
    if summary.get("stage_count") != len(stages):
        errors.append("workflow_execution.summary.stage_count: value does not match stages length")
    if summary.get("by_status") != {
        status: statuses.get(status, 0)
        for status in [
            "pending", "running", "succeeded", "failed", "blocked_dependency",
            "external_prerequisite", "skipped_by_scope", "out_of_range",
        ]
    }:
        errors.append("workflow_execution.summary.by_status: values do not match stages")
    expected_values = {
        "total_duration_ms": sum(durations),
        "maximum_duration_ms": max(durations, default=0),
        "failed_count": statuses.get("failed", 0),
        "skipped_by_scope_count": statuses.get("skipped_by_scope", 0),
        "blocked_dependency_count": statuses.get("blocked_dependency", 0),
        "absent_stage_count": sum(absence_reasons.values()),
        "absence_reasons": dict(sorted(absence_reasons.items())),
    }
    for key, expected in expected_values.items():
        if summary.get(key) != expected:
            errors.append(f"workflow_execution.summary.{key}: value does not match stages")
    provider_summary_fields = {
        "provider_failure_count",
        "retryable_provider_failure_count",
        "resume_recommended_count",
        "active_provider_failure_count",
        "recovered_provider_failure_count",
        "provider_failures_by_class",
    }
    present_provider_summary_fields = provider_summary_fields.intersection(summary)
    if provider_failure_stages or present_provider_summary_fields:
        if present_provider_summary_fields != provider_summary_fields:
            errors.append("workflow_execution.summary: provider failure summary fields must be complete")
        expected_provider_values = {
            "provider_failure_count": provider_failure_count,
            "retryable_provider_failure_count": retryable_provider_failure_count,
            "resume_recommended_count": resume_recommended_count,
            "active_provider_failure_count": active_provider_failure_count,
            "recovered_provider_failure_count": recovered_provider_failure_count,
            "provider_failures_by_class": {
                error_class: int(provider_classes[error_class])
                for error_class in PROVIDER_ERROR_CLASSES
                if provider_classes[error_class]
            },
        }
        for key, expected in expected_provider_values.items():
            if summary.get(key) != expected:
                errors.append(f"workflow_execution.summary.{key}: value does not match provider failures")
    resume = execution.get("resume") if isinstance(execution.get("resume"), dict) else {}
    if bool(resume.get("available")) != (resume.get("stage") is not None):
        errors.append("workflow_execution.resume.available: must match whether resume.stage is set")
    if resume.get("stage") is not None and resume.get("stage") not in stage_ids:
        errors.append("workflow_execution.resume.stage: must reference a workflow stage")
    return True


def validate_benchmark_payload(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in BENCHMARK_FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: benchmark must not copy raw evidence, issue body content, proof payloads, or secrets")
            validate_benchmark_payload(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_benchmark_payload(item, f"{path}[{index}]", errors)


def validate_benchmark(run_dir: Path, errors: List[str]) -> bool:
    benchmark_path = configured_artifact_path(run_dir, BENCHMARK_PATH)
    if not benchmark_path.exists():
        return False
    try:
        benchmark_data = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"benchmark.json invalid JSON: {exc}")
        return True
    if not isinstance(benchmark_data, dict):
        errors.append(f"benchmark: expected type object, got {json_type_name(benchmark_data)}")
        return True
    validate_schema(benchmark_data, load_schema("benchmark.schema.json"), "benchmark", errors)
    validate_embedded_report_freshness(
        benchmark_data.get("report_freshness"),
        "benchmark.report_freshness",
        errors,
    )
    validate_generated_at(benchmark_data.get("generated_at"), "benchmark.generated_at", errors)
    if benchmark_data.get("source") != "local-benchmark":
        errors.append("benchmark.source: benchmark must be generated from local-benchmark")
    safety = benchmark_data.get("safety") if isinstance(benchmark_data.get("safety"), dict) else {}
    expected_safety = {
        "local_artifacts_only": True,
        "network_accessed": False,
        "issue_apply_performed": False,
        "raw_evidence_copied": False,
        "secrets_copied": False,
        "bounded_summaries_only": True,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) is not expected:
            errors.append(f"benchmark.safety.{key}: must be {str(expected).lower()}")
    gates = benchmark_data.get("quality_gates")
    if isinstance(gates, list):
        statuses: list[str] = []
        ids: set[str] = set()
        for index, gate in enumerate(gates):
            path = f"benchmark.quality_gates[{index}]"
            if not isinstance(gate, dict):
                errors.append(f"{path}: gate must be an object")
                continue
            gate_id = str(gate.get("id") or "")
            if gate_id in ids:
                errors.append(f"{path}.id: duplicate gate id {gate_id}")
            ids.add(gate_id)
            status = str(gate.get("status") or "")
            if status not in BENCHMARK_GATE_STATUSES:
                errors.append(f"{path}.status: invalid benchmark gate status {status!r}")
            statuses.append(status)
            artifact_paths = gate.get("artifact_paths")
            if isinstance(artifact_paths, list):
                for artifact_index, artifact_path in enumerate(artifact_paths):
                    field = f"{path}.artifact_paths[{artifact_index}]"
                    if not isinstance(artifact_path, str):
                        errors.append(f"{field}: expected type string, got {json_type_name(artifact_path)}")
                        continue
                    rel = Path(artifact_path)
                    if rel.is_absolute() or ".." in rel.parts:
                        errors.append(f"{field}: artifact path must be run-relative and must not contain '..'")
        summary = benchmark_data.get("summary") if isinstance(benchmark_data.get("summary"), dict) else {}
        if summary.get("gate_count") != len(gates):
            errors.append("benchmark.summary.gate_count: value does not match quality gate count")
        if summary.get("passed") != statuses.count("pass"):
            errors.append("benchmark.summary.passed: value does not match passing gate count")
        if summary.get("warnings") != statuses.count("warn"):
            errors.append("benchmark.summary.warnings: value does not match warning gate count")
        if summary.get("failed") != statuses.count("fail"):
            errors.append("benchmark.summary.failed: value does not match failed gate count")
        overall = summary.get("overall_status")
        expected_overall = "failed" if "fail" in statuses else ("needs-review" if "warn" in statuses else "passed")
        if overall not in BENCHMARK_OVERALL_STATUSES:
            errors.append(f"benchmark.summary.overall_status: invalid overall status {overall!r}")
        elif overall != expected_overall:
            errors.append("benchmark.summary.overall_status: value does not match gate statuses")
    else:
        errors.append("benchmark.quality_gates: expected type array")
    validate_benchmark_payload(benchmark_data, "benchmark", errors)
    for _secret_error in iter_secret_findings(benchmark_data, field_path="benchmark"):
        errors.append("benchmark: contains obvious unredacted full secret value")
        break
    return True


def validate_evidence_graph_payload(value: Any, path: str, errors: List[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in EVIDENCE_GRAPH_FORBIDDEN_KEYS:
                errors.append(f"{path}.{key}: evidence graph must not copy raw evidence, remediation text, issue body content, proof payloads, or secrets")
            validate_evidence_graph_payload(item, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_evidence_graph_payload(item, f"{path}[{index}]", errors)


def validate_evidence_graph_path(run_dir: Path, value: Any, field_path: str, errors: List[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{field_path}: expected type string, got {json_type_name(value)}")
        return
    if not value.strip():
        return
    artifact_part = value.split("#", 1)[0]
    if not artifact_part:
        return
    rel = Path(artifact_part)
    if rel.is_absolute():
        errors.append(f"{field_path}: artifact path must be relative to the run directory")
        return
    if ".." in rel.parts:
        errors.append(f"{field_path}: artifact path must not contain '..'")
        return
    try:
        validate_no_symlink_components(run_dir, rel, field_path=field_path)
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return
    target = run_dir / rel
    try:
        target.resolve(strict=False).relative_to(run_dir.resolve(strict=False))
    except ValueError:
        errors.append(f"{field_path}: artifact path must stay under the run directory")
        return
    if not target.exists():
        errors.append(f"{field_path}: referenced local artifact not found: {rel.as_posix()}")


def validate_evidence_graph(run_dir: Path, errors: List[str]) -> bool:
    graph_path = configured_artifact_path(run_dir, EVIDENCE_GRAPH_PATH)
    if not graph_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, configured_artifact_ref(run_dir, EVIDENCE_GRAPH_PATH), field_path="evidence_graph")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"evidence_graph invalid JSON: {exc}")
        return True
    if not isinstance(graph, dict):
        errors.append(f"evidence_graph: expected type object, got {json_type_name(graph)}")
        return True

    validate_schema(graph, load_schema("evidence-graph.schema.json"), "evidence_graph", errors)
    graph_summary = graph.get("summary") if isinstance(graph.get("summary"), dict) else {}
    validate_embedded_report_freshness(
        graph_summary.get("report_freshness"),
        "evidence_graph.summary.report_freshness",
        errors,
    )
    validate_workflow_execution_summary_contract(
        graph_summary.get("workflow_execution"),
        "evidence_graph.summary.workflow_execution",
        "evidence-graph.schema.json",
        errors,
    )
    validate_generated_at(graph.get("generated_at"), "evidence_graph.generated_at", errors)
    if graph.get("source") != "local-report-artifacts":
        errors.append("evidence_graph.source: must be local-report-artifacts")
    safety = graph.get("safety") if isinstance(graph.get("safety"), dict) else {}
    if safety.get("local_artifacts_only") is not True:
        errors.append("evidence_graph.safety.local_artifacts_only: must be true")
    if safety.get("raw_evidence_copied") is not False:
        errors.append("evidence_graph.safety.raw_evidence_copied: must be false")
    if safety.get("secret_values_copied") is not False:
        errors.append("evidence_graph.safety.secret_values_copied: must be false")
    if safety.get("bounded_summaries_only") is not True:
        errors.append("evidence_graph.safety.bounded_summaries_only: must be true")
    try:
        from metrics import MetricsError, target_queue_metrics

        targets_path = configured_reports_dir(run_dir) / "targets.json"
        targets_data = load_targets_artifact(run_dir, {}) if targets_path.exists() else {}
        queue_metrics = target_queue_metrics(targets_data)
        expected_queue = {
            "artifact_present": queue_metrics["available"],
            "generated": queue_metrics["generated"],
            "active": queue_metrics["active"],
            "retained_outside_budget": queue_metrics["retained_outside_budget"],
            "merged": queue_metrics["merged"],
            "deferred_by_budget": queue_metrics["deferred_by_budget"],
            "high_risk_deferred": queue_metrics["high_risk_deferred"],
            "by_source": queue_metrics["by_source"],
        }
        if graph_summary.get("target_queue") != expected_queue:
            errors.append("evidence_graph.summary.target_queue: counts must match reports/targets.json queue summary")
    except (OSError, ValueError, MetricsError) as exc:
        errors.append(f"evidence_graph.summary.target_queue: unable to validate target queue safely: {exc}")
    validate_evidence_graph_payload(graph, "evidence_graph", errors)
    secret_like_count = sum(1 for _ in iter_secret_findings(graph, field_path="evidence_graph"))
    if secret_like_count:
        errors.append("evidence_graph: contains obvious unredacted secret-like value(s); remove or hash them before validation")

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        errors.append("evidence_graph.nodes: nodes must be a list")
        nodes = []
    edges = graph.get("edges")
    if not isinstance(edges, list):
        errors.append("evidence_graph.edges: edges must be a list")
        edges = []

    node_ids: set[str] = set()
    node_type_counts: dict[str, int] = {}
    for index, node in enumerate(nodes):
        path = f"evidence_graph.nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{path}: node must be an object")
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            errors.append(f"{path}.id: node id must not be empty")
        elif node_id in node_ids:
            errors.append(f"{path}.id: duplicate node id {node_id}")
        node_ids.add(node_id)
        node_type = str(node.get("type") or "")
        if node_type not in EVIDENCE_GRAPH_NODE_TYPES:
            errors.append(f"{path}.type: invalid node type {node_type!r}")
        else:
            node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
        summary = node.get("summary")
        if not isinstance(summary, str):
            errors.append(f"{path}.summary: expected type string, got {json_type_name(summary)}")
        elif len(summary) > 200:
            errors.append(f"{path}.summary: must be at most 200 characters")
        validate_evidence_graph_path(run_dir, node.get("path"), f"{path}.path", errors)

    edge_keys: set[tuple[str, str, str]] = set()
    edge_type_counts: dict[str, int] = {}
    for index, edge in enumerate(edges):
        path = f"evidence_graph.edges[{index}]"
        if not isinstance(edge, dict):
            errors.append(f"{path}: edge must be an object")
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        edge_type = str(edge.get("type") or "")
        if source not in node_ids:
            errors.append(f"{path}.source: unknown node id {source!r}")
        if target not in node_ids:
            errors.append(f"{path}.target: unknown node id {target!r}")
        if edge_type not in EVIDENCE_GRAPH_EDGE_TYPES:
            errors.append(f"{path}.type: invalid edge type {edge_type!r}")
        else:
            edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
        key = (source, target, edge_type)
        if key in edge_keys:
            errors.append(f"{path}: duplicate edge {source} {edge_type} {target}")
        edge_keys.add(key)
        reason = edge.get("reason")
        if not isinstance(reason, str):
            errors.append(f"{path}.reason: expected type string, got {json_type_name(reason)}")
        elif len(reason) > 200:
            errors.append(f"{path}.reason: must be at most 200 characters")
        validate_evidence_graph_path(run_dir, edge.get("path"), f"{path}.path", errors)

    summary = graph.get("summary") if isinstance(graph.get("summary"), dict) else {}
    if summary.get("node_count") != len(nodes):
        errors.append("evidence_graph.summary.node_count: value does not match nodes length")
    if summary.get("edge_count") != len(edges):
        errors.append("evidence_graph.summary.edge_count: value does not match edges length")
    expected_node_counts = dict(sorted(node_type_counts.items()))
    if summary.get("node_counts") != expected_node_counts:
        errors.append("evidence_graph.summary.node_counts: value does not match node list")
    expected_edge_counts = dict(sorted(edge_type_counts.items()))
    if summary.get("edge_counts") != expected_edge_counts:
        errors.append("evidence_graph.summary.edge_counts: value does not match edge list")

    high_total = summary.get("high_critical_issue_recommended_findings")
    high_support = summary.get("high_critical_with_supporting_evidence")
    high_challenge = summary.get("high_critical_with_challenging_evidence")
    for key, value in [
        ("high_critical_issue_recommended_findings", high_total),
        ("high_critical_with_supporting_evidence", high_support),
        ("high_critical_with_challenging_evidence", high_challenge),
    ]:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"evidence_graph.summary.{key}: must be a non-negative integer")
    if isinstance(high_total, int) and isinstance(high_support, int) and high_support > high_total:
        errors.append("evidence_graph.summary.high_critical_with_supporting_evidence: cannot exceed high_critical_issue_recommended_findings")
    if isinstance(high_total, int) and isinstance(high_challenge, int) and high_challenge > high_total:
        errors.append("evidence_graph.summary.high_critical_with_challenging_evidence: cannot exceed high_critical_issue_recommended_findings")

    return True


def append_imported_secret_error(value: Any, errors: List[str]) -> None:
    for _secret_error in iter_secret_findings(value, field_path="imported_findings"):
        errors.append("imported_findings: contains obvious unredacted full secret value")
        return


def validate_imported_locations(value: Any, path: str, errors: List[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}.affected_locations: affected_locations must be list")
        return
    for index, loc in enumerate(value):
        loc_path = f"{path}.affected_locations[{index}]"
        if not isinstance(loc, dict):
            errors.append(f"{loc_path}: location must be object")
            continue
        try:
            validate_relative_repo_path(loc.get("file"), field_path=f"{loc_path}.file")
        except ReportSafetyError:
            errors.append(f"{loc_path}.file: invalid relative repository path")
        for key in ("line", "end_line"):
            if key in loc and loc.get(key) is not None:
                if not isinstance(loc.get(key), int) or isinstance(loc.get(key), bool):
                    errors.append(f"{loc_path}.{key}: {key} must be a positive integer or null")
                elif int(loc[key]) < 1:
                    errors.append(f"{loc_path}.{key}: {key} must be a positive integer")
        if isinstance(loc.get("line"), int) and isinstance(loc.get("end_line"), int) and loc["end_line"] < loc["line"]:
            errors.append(f"{loc_path}.end_line: end_line must be greater than or equal to line")


def validate_imported_assessments(finding: Dict[str, Any], path: str, errors: List[str]) -> None:
    for key in ["bug_existence", "attacker_reachability", "boundary_crossing", "impact_assessment"]:
        if key in finding and finding.get(key) not in ASSESSMENT_STATUSES:
            errors.append(f"{path}.{key}: invalid assessment status")
    chain_membership = finding.get("chain_membership")
    if chain_membership is not None:
        if not isinstance(chain_membership, list):
            errors.append(f"{path}.chain_membership: must be list when present")
        else:
            for index, chain_id in enumerate(chain_membership):
                if not isinstance(chain_id, str) or not re.fullmatch(r"CHAIN-[0-9]{3,}", chain_id):
                    errors.append(f"{path}.chain_membership[{index}]: invalid chain id")
    if "assessment_notes" in finding and not isinstance(finding.get("assessment_notes"), dict):
        errors.append(f"{path}.assessment_notes: must be object")


def validate_imported_findings(run_dir: Path, findings: list[dict[str, Any]], errors: List[str]) -> bool:
    imported_path = configured_artifact_path(run_dir, IMPORTED_FINDINGS_PATH)
    if not imported_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, configured_artifact_ref(run_dir, IMPORTED_FINDINGS_PATH), field_path="imported_findings")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        data = json.loads(imported_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"imported-findings.json invalid JSON: {exc}")
        return True

    validate_schema_shape(data, load_schema("imported-findings.schema.json"), "imported_findings", errors)
    if not isinstance(data, dict):
        return True
    validate_generated_at(data.get("generated_at"), "imported_findings.generated_at", errors)
    append_imported_secret_error(data, errors)

    imported = data.get("findings") if isinstance(data.get("findings"), list) else []
    rejected = data.get("rejected_findings") if isinstance(data.get("rejected_findings"), list) else []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    source = str(data.get("source") or "")
    current_fingerprints = {str(finding.get("fingerprint") or "") for finding in findings if isinstance(finding, dict)}
    appended_count = 0
    duplicate_skipped_count = 0
    seen_import_fingerprints: set[str] = set()
    finding_schema = load_schema("findings.schema.json")["properties"]["findings"]["items"]

    for index, item in enumerate(imported):
        path = f"imported_findings.findings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: imported finding must be an object")
            continue
        append_status = str(item.get("append_status") or "")
        if append_status not in IMPORTED_FINDING_APPEND_STATUSES:
            errors.append(f"{path}.append_status: invalid append status")
        if item.get("source") != source:
            errors.append(f"{path}.source: must match imported_findings.source")
        fingerprint = str(item.get("fingerprint") or "")
        if not re.fullmatch(r"[a-f0-9]{24}", fingerprint):
            errors.append(f"{path}.fingerprint: must be 24 lowercase hex characters")
        if fingerprint in seen_import_fingerprints and append_status != "duplicate-skipped":
            errors.append(f"{path}.append_status: duplicate import fingerprints must be duplicate-skipped")
        seen_import_fingerprints.add(fingerprint)
        if append_status == "appended":
            appended_count += 1
            if fingerprint not in current_fingerprints:
                errors.append(f"{path}.append_status: appended finding fingerprint is not present in reports/findings.json")
        elif append_status == "duplicate-skipped":
            duplicate_skipped_count += 1

        validate_imported_locations(item.get("affected_locations"), path, errors)
        normalized = item.get("normalized_finding")
        if not isinstance(normalized, dict):
            errors.append(f"{path}.normalized_finding: must be an object")
            continue
        validate_schema_shape(normalized, finding_schema, f"{path}.normalized_finding", errors)
        validate_imported_locations(normalized.get("affected_locations"), f"{path}.normalized_finding", errors)
        validate_imported_assessments(normalized, f"{path}.normalized_finding", errors)
        external_source = normalized.get("external_source") if isinstance(normalized.get("external_source"), dict) else {}
        if external_source.get("source") != source:
            errors.append(f"{path}.normalized_finding.external_source.source: must match imported_findings.source")
        if external_source.get("external_id") != item.get("external_id"):
            errors.append(f"{path}.normalized_finding.external_source.external_id: must match imported finding external_id")
        if normalized.get("fingerprint") != fingerprint:
            errors.append(f"{path}.normalized_finding.fingerprint: must match imported finding fingerprint")
        if normalized.get("issue_recommended") is not False:
            errors.append(f"{path}.normalized_finding.issue_recommended: imported findings must require review before publication")
        if normalized.get("issue_body_file"):
            errors.append(f"{path}.normalized_finding.issue_body_file: imported findings must not pre-bind issue body files")

    for index, item in enumerate(rejected):
        path = f"imported_findings.rejected_findings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: rejected finding must be an object")
            continue
        reasons = item.get("reasons")
        if not isinstance(reasons, list) or not reasons or any(not isinstance(reason, str) or not reason for reason in reasons):
            errors.append(f"{path}.reasons: must contain at least one non-empty reason")

    if summary:
        expected_counts = {
            "valid_count": len(imported),
            "rejected_count": len(rejected),
            "appended_count": appended_count,
            "duplicate_skipped_count": duplicate_skipped_count,
        }
        for key, expected in expected_counts.items():
            if summary.get(key) != expected:
                errors.append(f"imported_findings.summary.{key}: count does not match imported finding records")
        input_count = summary.get("input_count")
        if isinstance(input_count, int) and input_count != len(imported) + len(rejected):
            errors.append(
                "imported_findings.summary.input_count: "
                "count does not match valid plus rejected imported finding records"
            )
    return True


def validate_issue_ledger(run_dir: Path, errors: List[str]) -> bool:
    ledger_path = configured_artifact_path(run_dir, ISSUE_LEDGER_PATH)
    if not ledger_path.exists():
        return False
    try:
        ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"issue_ledger invalid JSON: {exc}")
        return True
    if not isinstance(ledger_data, dict):
        errors.append(f"issue_ledger: expected type object, got {json_type_name(ledger_data)}")
        return True
    validate_schema(ledger_data, load_schema("issue-ledger.schema.json"), "issue_ledger", errors)
    validate_generated_at(ledger_data.get("generated_at"), "issue_ledger.generated_at", errors)
    for index, entry in enumerate(ledger_data.get("findings") or []):
        if not isinstance(entry, dict):
            continue
        body_hash = entry.get("body_hash")
        if body_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(body_hash)):
            errors.append(f"issue_ledger.findings[{index}].body_hash: expected lowercase SHA-256 or null")
        current_body_hash = entry.get("current_body_hash")
        if current_body_hash is not None and not re.fullmatch(r"[a-f0-9]{64}", str(current_body_hash)):
            errors.append(f"issue_ledger.findings[{index}].current_body_hash: expected lowercase SHA-256 or null")
    return True


def validate_duplicate_decisions(run_dir: Path, errors: List[str]) -> bool:
    decisions_dir = configured_artifact_path(run_dir, DUPLICATE_DECISIONS_DIR)
    ledger_path = configured_artifact_path(run_dir, ISSUE_LEDGER_PATH)
    ledger_entries: List[Dict[str, Any]] = []
    if ledger_path.exists():
        try:
            ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
            if isinstance(ledger_data, dict):
                ledger_entries = [entry for entry in ledger_data.get("findings") or [] if isinstance(entry, dict)]
        except Exception as exc:
            errors.append(f"duplicate_decisions: could not read issue ledger for reconciliation: {exc}")

    published_entries = [
        entry
        for entry in ledger_entries
        if str(entry.get("publication_status") or "") in {"published", "duplicate"}
    ]
    if not decisions_dir.exists():
        if published_entries:
            errors.append("duplicate_decisions: reports/duplicate-decisions is required when issue ledger has published or duplicate entries")
        return False
    if not decisions_dir.is_dir():
        errors.append("duplicate_decisions: reports/duplicate-decisions must be a directory")
        return True

    records: Dict[tuple[str, str], Dict[str, Any]] = {}
    for decision_path in sorted(decisions_dir.glob("*.json")):
        rel = decision_path.relative_to(run_dir).as_posix()
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{rel}: invalid JSON: {exc}")
            continue
        if not isinstance(decision, dict):
            errors.append(f"{rel}: expected type object, got {json_type_name(decision)}")
            continue
        validate_schema(decision, load_schema("duplicate-decision.schema.json"), rel, errors)
        validate_generated_at(decision.get("checked_at"), f"{rel}.checked_at", errors)
        for field in ["root_cause_fingerprint", "source_to_sink_fingerprint"]:
            if not re.fullmatch(r"[a-f0-9]{24}", str(decision.get(field) or "")):
                errors.append(f"{rel}.{field}: expected 24 lowercase hex characters")
        key = (str(decision.get("finding_id") or ""), str(decision.get("fingerprint") or ""))
        if key in records:
            errors.append(f"{rel}: duplicate decision record for finding/fingerprint {key[0]} / {key[1]}")
        records[key] = decision
        exact_match = decision.get("exact_match")
        if exact_match is True:
            if decision.get("decision") != "exact-duplicate":
                errors.append(f"{rel}.decision: exact_match=true requires decision exact-duplicate")
            if not decision.get("exact_match_url") or not decision.get("exact_match_source"):
                errors.append(f"{rel}.exact_match_url: exact_match=true requires exact_match_url and exact_match_source")
        elif exact_match is False:
            if decision.get("exact_match_url") is not None or decision.get("exact_match_source") is not None:
                errors.append(f"{rel}.exact_match_url: exact_match=false requires null exact_match_url and exact_match_source")

    for entry in published_entries:
        finding_id = str(entry.get("finding_id") or "")
        fingerprint = str(entry.get("fingerprint") or "")
        record = records.get((finding_id, fingerprint))
        if not record:
            errors.append(f"duplicate_decisions: missing record for published ledger finding {finding_id} fingerprint {fingerprint}")
            continue
        if str(entry.get("publication_status") or "") == "duplicate" and record.get("decision") != "exact-duplicate":
            errors.append(
                f"duplicate_decisions: duplicate ledger finding {finding_id} requires exact-duplicate decision, "
                f"got {record.get('decision')!r}"
            )
    return True


def validate_run_state(run_dir: Path, errors: List[str]) -> bool:
    state_path = configured_artifact_path(run_dir, RUN_STATE_PATH)
    if not state_path.exists():
        return False
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"run_state invalid JSON: {exc}")
        return True
    if not isinstance(state_data, dict):
        errors.append(f"run_state: expected type object, got {json_type_name(state_data)}")
        return True
    validate_schema(state_data, load_schema("run-state.schema.json"), "run_state", errors)
    validate_generated_at(state_data.get("generated_at"), "run_state.generated_at", errors)
    for field in ["paused_at", "blocked_at", "resumed_at"]:
        value = state_data.get(field)
        if value is not None:
            validate_generated_at(value, f"run_state.{field}", errors)
    status = state_data.get("status")
    if status == "paused" and not state_data.get("pause_reason"):
        errors.append("run_state.pause_reason: required when status is paused")
    if status == "blocked" and not state_data.get("block_reason"):
        errors.append("run_state.block_reason: required when status is blocked")
    return True


def validate_command_event_artifact_path(run_dir: Path, value: Any, *, field_path: str, errors: List[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field_path}: artifact path must be a non-empty string")
        return
    rel = Path(value)
    if rel.is_absolute():
        errors.append(f"{field_path}: artifact path must be relative to the run directory")
    if ".." in rel.parts:
        errors.append(f"{field_path}: artifact path must not contain '..'")
    current = run_dir
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            errors.append(f"{field_path}: artifact path must not contain symlink components")
            break


def validate_command_events(run_dir: Path, errors: List[str]) -> bool:
    events_path = configured_artifact_path(run_dir, COMMAND_EVENTS_PATH)
    if not events_path.exists():
        return False
    try:
        validate_no_symlink_components(run_dir, configured_artifact_ref(run_dir, COMMAND_EVENTS_PATH), field_path="command_events")
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True

    context: Dict[str, Any] = {}
    try:
        context_value = json.loads((run_dir / "context.json").read_text(encoding="utf-8"))
        if isinstance(context_value, dict):
            context = context_value
    except Exception:
        context = {}

    for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        path = f"command_events[{line_number}]"
        try:
            event = json.loads(line)
        except Exception as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        if not isinstance(event, dict):
            errors.append(f"{path}: expected type object, got {json_type_name(event)}")
            continue
        validate_schema_shape(event, load_schema("command-event.schema.json"), path, errors)
        try:
            validate_command_event_payload(event)
        except EventValidationError as exc:
            errors.append(f"{path}: {exc}")
        schema_version = str(event.get("schema_version") or "")
        if schema_version not in {"1", "2"}:
            errors.append(f"{path}.schema_version: invalid command-event schema version")
        elif schema_version == "1":
            for key in ["repo", "target_id", "model", "effort", "artifact_paths"]:
                if key not in event:
                    errors.append(f"{path}.{key}: missing required v1 field")
        else:
            for key in ["event_id", "status", "attempt", "input_artifact_refs", "output_artifact_refs"]:
                if key not in event:
                    errors.append(f"{path}.{key}: missing required v2 field")
        if event.get("command") not in COMMAND_EVENT_COMMANDS:
            errors.append(f"{path}.command: invalid command")
        if event.get("phase") not in COMMAND_EVENT_PHASES:
            errors.append(f"{path}.phase: invalid phase")
        validate_generated_at(event.get("started_at"), f"{path}.started_at", errors)
        validate_generated_at(event.get("ended_at"), f"{path}.ended_at", errors)
        started = parse_event_time(event.get("started_at"))
        ended = parse_event_time(event.get("ended_at"))
        if started and ended and ended < started:
            errors.append(f"{path}.ended_at: must not be earlier than started_at")
        if event.get("run_id") != (context.get("run_id") or run_dir.name):
            errors.append(f"{path}.run_id: does not match run context")
        if "repo" in context and event.get("repo") != context.get("repo"):
            errors.append(f"{path}.repo: does not match run context")
        target_id = event.get("target_id")
        if target_id is not None and not re.fullmatch(r"TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}", str(target_id)):
            errors.append(f"{path}.target_id: invalid target id")
        for artifact_field in ["artifact_paths", "input_artifact_refs", "output_artifact_refs"]:
            artifacts = event.get(artifact_field)
            if not isinstance(artifacts, list):
                continue
            for artifact_index, artifact in enumerate(artifacts):
                validate_command_event_artifact_path(
                    run_dir,
                    artifact,
                    field_path=f"{path}.{artifact_field}[{artifact_index}]",
                    errors=errors,
                )
    return True


def validate_report_freshness(run_dir: Path, errors: List[str]) -> bool:
    """Validate optional freshness metadata without treating staleness as corruption."""

    try:
        return load_freshness(run_dir) is not None
    except (FreshnessError, OSError) as exc:
        errors.append(f"report_freshness: {exc}")
        return True


def validate_store_import_state(run_dir: Path, errors: List[str]) -> bool:
    path = configured_artifact_path(run_dir, STORE_IMPORT_STATE_PATH)
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        errors.append(f"store_import_state: invalid bounded artifact: {exc}")
        return True
    try:
        data = load_bounded_json_artifact(
            run_dir,
            configured_artifact_ref(run_dir, STORE_IMPORT_STATE_PATH),
            max_bytes=64 * 1024,
        )
    except (OSError, ValueError, FreshnessError) as exc:
        errors.append(f"store_import_state: invalid bounded artifact: {exc}")
        return True
    validate_schema_shape(data, load_schema("store-import-state.schema.json"), "store_import_state", errors)
    if not isinstance(data, dict):
        return True
    expected_keys = {
        "schema_version",
        "run_id",
        "generated_at",
        "source",
        "database_location_recorded",
        "imported_counts",
    }
    if set(data) != expected_keys:
        errors.append("store_import_state: contains unsupported fields")
    counts = data.get("imported_counts")
    expected_count_keys = {"targets", "findings", "scanner_results", "issues", "posture_artifacts"}
    if isinstance(counts, dict) and set(counts) != expected_count_keys:
        errors.append("store_import_state.imported_counts: must contain exactly the supported table counts")
    if isinstance(counts, dict) and any(
        not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 1_000_000
        for count in counts.values()
    ):
        errors.append("store_import_state.imported_counts: values must be bounded non-negative integers")
    context = load_context(run_dir)
    if data.get("run_id") != str(context.get("run_id") or run_dir.name):
        errors.append("store_import_state.run_id: does not match run context")
    validate_generated_at(data.get("generated_at"), "store_import_state.generated_at", errors)
    if data.get("database_location_recorded") is not False:
        errors.append("store_import_state.database_location_recorded: must be false")
    return True

ADVANCED_VALIDATOR_ORDER = (
    "dependencies",
    "chains",
    "adversarial_validation",
    "proofs",
    "remediation_candidates",
    "patch_validations",
    "novelty_ledger",
    "traces",
    "scanner_runs",
    "scanner_readiness",
    "metrics",
    "workflow_profile",
    "workflow_execution",
    "benchmark",
    "evidence_graph",
    "imported_findings",
    "issue_ledger",
    "duplicate_decisions",
    "run_state",
    "command_events",
    "store_import_state",
    "report_freshness",
)


def _run_with_context(context: ValidationContext, callback: Callable[[], bool]) -> bool:
    token = _SCHEMA_LAB_ROOT.set(context.lab_root)
    try:
        return callback()
    finally:
        _SCHEMA_LAB_ROOT.reset(token)


def _run_without_findings(context: ValidationContext, validator: Callable[[Path, List[str]], bool]) -> bool:
    return _run_with_context(context, lambda: validator(context.run_dir, context.errors))


def _run_with_findings(
    context: ValidationContext,
    validator: Callable[[Path, list[dict[str, Any]], List[str]], bool],
) -> bool:
    return _run_with_context(context, lambda: validator(context.run_dir, context.findings, context.errors))


def register_advanced_validators(registry: Any) -> None:
    registry.register("dependencies", lambda context: _run_without_findings(context, validate_dependencies))
    registry.register("chains", lambda context: _run_with_findings(context, validate_chains))
    registry.register("adversarial_validation", lambda context: _run_with_findings(context, validate_adversarial_validation))
    registry.register("proofs", lambda context: _run_with_findings(context, validate_proofs))
    registry.register("remediation_candidates", lambda context: _run_with_findings(context, validate_remediation_candidates))
    registry.register("patch_validations", lambda context: _run_with_findings(context, validate_patch_validations))
    registry.register("novelty_ledger", lambda context: _run_with_findings(context, validate_novelty_ledger))
    registry.register("traces", lambda context: _run_with_findings(context, validate_traces))
    registry.register("scanner_runs", lambda context: _run_without_findings(context, validate_scanner_runs))
    registry.register(
        "scanner_readiness",
        lambda context: _run_without_findings(context, validate_scanner_readiness_reports),
    )
    registry.register("metrics", lambda context: _run_without_findings(context, validate_metrics))
    registry.register("workflow_profile", lambda context: _run_without_findings(context, validate_workflow_profile))
    registry.register("workflow_execution", lambda context: _run_without_findings(context, validate_workflow_execution))
    registry.register("benchmark", lambda context: _run_without_findings(context, validate_benchmark))
    registry.register("evidence_graph", lambda context: _run_without_findings(context, validate_evidence_graph))
    registry.register("imported_findings", lambda context: _run_with_findings(context, validate_imported_findings))
    registry.register("issue_ledger", lambda context: _run_without_findings(context, validate_issue_ledger))
    registry.register("duplicate_decisions", lambda context: _run_without_findings(context, validate_duplicate_decisions))
    registry.register("run_state", lambda context: _run_without_findings(context, validate_run_state))
    registry.register("command_events", lambda context: _run_without_findings(context, validate_command_events))
    registry.register("store_import_state", lambda context: _run_without_findings(context, validate_store_import_state))
    registry.register("report_freshness", lambda context: _run_without_findings(context, validate_report_freshness))

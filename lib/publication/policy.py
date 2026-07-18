from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from novelty_ledger import suppresses_publication as novelty_suppresses_publication
from run_events import reports_dir as configured_reports_dir

from .rendering import stable_fingerprint, slug

SEVERITY_RANK = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2, "Informational": 1}
DEFAULT_LABELS: Dict[str, Tuple[str, str]] = {
    "security": ("d73a4a", "Security-related issue"),
    "genai-audit": ("5319e7", "Generated from local GenAI Repo Auditor"),
    "severity-critical": ("b60205", "Critical security severity"),
    "severity-high": ("d93f0b", "High security severity"),
    "severity-medium": ("fbca04", "Medium security severity"),
    "severity-low": ("0e8a16", "Low security severity"),
    "severity-informational": ("1d76db", "Informational security severity"),
    "status-confirmed": ("b60205", "Confirmed finding"),
    "status-probable": ("d93f0b", "Probable finding"),
    "status-potential": ("fbca04", "Potential finding"),
    "status-needs-human-review": ("5319e7", "Needs human review"),
}
ADVANCED_REQUIRED_SEVERITIES = {"Critical", "High"}
BLOCKING_VALIDATION_DECISIONS = {"downgrade", "invalidate", "needs-human-review"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def should_include(finding: Dict[str, Any], min_severity: str, statuses: Iterable[str]) -> bool:
    selected, _reason = finding_selection_decision(finding, min_severity, statuses)
    return selected


def novelty_suppression_reason(entry: Dict[str, Any]) -> str:
    status = str(entry.get("novelty_status") or "").strip()
    if status:
        return f"novelty status {status} suppresses publication"
    return "novelty ledger suppresses publication"


def finding_selection_decision(
    finding: Dict[str, Any],
    min_severity: str,
    statuses: Iterable[str],
    *,
    repo: Optional[str] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[bool, str]:
    selected, reason, _reason_code = finding_selection_outcome(
        finding,
        min_severity,
        statuses,
        repo=repo,
        novelty_entries=novelty_entries,
    )
    return selected, reason


def finding_selection_outcome(
    finding: Dict[str, Any],
    min_severity: str,
    statuses: Iterable[str],
    *,
    repo: Optional[str] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[bool, str, str]:
    """Return the canonical selection decision plus a stable aggregate reason code."""

    if finding.get("issue_recommended") is False:
        return False, "issue_recommended=false", "issue_recommendation_suppressed"
    severity = str(finding.get("severity") or "Informational")
    if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK[min_severity]:
        return False, f"severity below {min_severity}", "filtered_by_severity_or_status"
    status = str(finding.get("status") or "")
    if status not in set(statuses):
        return False, f"status {status or 'Unknown'} not selected", "filtered_by_severity_or_status"
    if repo is not None and novelty_entries is not None:
        entry = matching_novelty_entry(repo, finding, novelty_entries)
        if novelty_suppresses_publication(entry):
            return False, novelty_suppression_reason(entry or {}), "novelty_suppressed"
    return True, "selected", "selected"


def select_findings(
    *,
    repo: str,
    findings: Iterable[Dict[str, Any]],
    min_severity: str,
    statuses: Iterable[str],
    novelty_entries: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    for finding in findings:
        include, _reason = finding_selection_decision(
            finding,
            min_severity,
            statuses,
            repo=repo,
            novelty_entries=novelty_entries,
        )
        if include:
            selected.append(finding)
    return selected


def normalize_labels(finding: Dict[str, Any]) -> List[str]:
    labels = ["security", "genai-audit"]
    severity = str(finding.get("severity", "")).lower()
    if severity:
        labels.append(f"severity-{slug(severity)}")
    status = str(finding.get("status", "")).lower()
    if status:
        labels.append(f"status-{slug(status)}")
    category = str(finding.get("category", "")).strip()
    if category:
        labels.append(f"category-{slug(category)}")
    for label in finding.get("labels") or []:
        label = str(label).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def issue_title(finding: Dict[str, Any]) -> str:
    return str(finding.get("issue_title") or f"[Security][{finding.get('severity','Unknown')}] {finding.get('title','Security finding')}")


def plan_visibility(data: Dict[str, Any], context: Dict[str, Any]) -> str:
    return str(data.get("visibility") or context.get("visibility") or "UNKNOWN").upper()


def optional_report(run_dir: Path, rel_path: str, array_key: str) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    relative = Path(rel_path)
    if relative.parts and relative.parts[0] == "reports":
        relative = Path(*relative.parts[1:])
    path = configured_reports_dir(run_dir) / relative
    if not path.exists():
        return False, [], []
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return True, [], [f"{rel_path} could not be read: {exc}"]
    records = data.get(array_key) if isinstance(data, dict) else None
    if not isinstance(records, list):
        return True, [], [f"{rel_path} does not contain {array_key} array"]
    return True, [record for record in records if isinstance(record, dict)], []


def optional_patch_validations(run_dir: Path) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
    remediation_root = configured_reports_dir(run_dir) / "remediation"
    if not remediation_root.exists():
        return False, [], []
    paths = sorted(remediation_root.rglob("patch-validation.json"))
    if not paths:
        return False, [], []
    records: List[Dict[str, Any]] = []
    errors: List[str] = []
    for path in paths:
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(run_dir).as_posix()} could not be read: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path.relative_to(run_dir).as_posix()} is not a JSON object")
            continue
        data = dict(data)
        data.setdefault("report_file", path.relative_to(run_dir).as_posix())
        records.append(data)
    return True, records, errors


def load_advanced_artifacts(run_dir: Path) -> Dict[str, Any]:
    chains_present, chains, chain_errors = optional_report(run_dir, "reports/chains.json", "chains")
    proofs_present, proofs, proof_errors = optional_report(run_dir, "reports/proofs.json", "proofs")
    validations_present, validations, validation_errors = optional_report(run_dir, "reports/validation.json", "validations")
    remediation_present, remediation_candidates, remediation_errors = optional_report(
        run_dir,
        "reports/remediation/remediation-candidates.json",
        "candidates",
    )
    patch_validations_present, patch_validations, patch_validation_errors = optional_patch_validations(run_dir)
    return {
        "chains_present": chains_present,
        "chains": chains,
        "chain_errors": chain_errors,
        "proofs_present": proofs_present,
        "proofs": proofs,
        "proof_errors": proof_errors,
        "validations_present": validations_present,
        "validations": validations,
        "validation_errors": validation_errors,
        "remediation_present": remediation_present,
        "remediation_candidates": remediation_candidates,
        "remediation_errors": remediation_errors,
        "patch_validations_present": patch_validations_present,
        "patch_validations": patch_validations,
        "patch_validation_errors": patch_validation_errors,
    }


def string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def proof_not_applicable(finding: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    for field in ["safe_proof_not_applicable", "proof_not_applicable"]:
        if finding.get(field) is True:
            reason = str(
                finding.get("safe_proof_not_applicable_reason")
                or finding.get("proof_not_applicable_reason")
                or "finding marks safe local proof as not applicable"
            )
            return True, reason
    severity = str(finding.get("severity") or "")
    if severity not in ADVANCED_REQUIRED_SEVERITIES:
        return True, f"safe local proof is not required for severity {severity or 'Unknown'}"
    return False, None


def validation_detail(item: Dict[str, Any]) -> Dict[str, Any]:
    detail = {
        "id": str(item.get("id") or ""),
        "decision": str(item.get("decision") or ""),
        "recommended_severity": str(item.get("recommended_severity") or ""),
        "recommended_confidence": str(item.get("recommended_confidence") or ""),
    }
    if item.get("vote_count") is not None or item.get("vote_policy"):
        detail["vote_count"] = item.get("vote_count")
        detail["vote_policy"] = str(item.get("vote_policy") or "")
    owner_routing = {
        "component": str(item.get("component") or ""),
        "owner_hint": str(item.get("owner_hint") or ""),
        "owner_source": str(item.get("owner_source") or ""),
    }
    if any(owner_routing.values()):
        detail["owner_routing"] = owner_routing
    return detail


def first_owner_routing(details: List[Dict[str, Any]]) -> Dict[str, str]:
    for detail in details:
        owner_routing = detail.get("owner_routing") if isinstance(detail.get("owner_routing"), dict) else {}
        if any(owner_routing.get(key) for key in ["component", "owner_hint", "owner_source"]):
            return {
                "component": str(owner_routing.get("component") or ""),
                "owner_hint": str(owner_routing.get("owner_hint") or ""),
                "owner_source": str(owner_routing.get("owner_source") or ""),
            }
    return {}


def advanced_validation_summary(finding: Dict[str, Any], artifacts: Dict[str, Any]) -> Dict[str, Any]:
    finding_id = str(finding.get("id") or "SEC-UNKNOWN")
    chain_membership = string_list(finding.get("chain_membership"))
    chain_records = {
        str(chain.get("id")): chain
        for chain in artifacts.get("chains", [])
        if isinstance(chain.get("id"), str)
    }
    referenced_by_chains = sorted(
        str(chain_id)
        for chain_id, chain in chain_records.items()
        if finding_id in string_list(chain.get("findings"))
    )
    related_chain_ids = sorted(set(chain_membership) | set(referenced_by_chains))
    matched_chains = [chain_id for chain_id in related_chain_ids if chain_id in chain_records]
    missing_chains = [chain_id for chain_id in chain_membership if chain_id not in chain_records]

    validations = artifacts.get("validations", [])
    finding_validation_details = sorted(
        (
            validation_detail(item)
            for item in validations
            if item.get("subject_type") == "finding"
            and str(item.get("subject_id")) == finding_id
            and isinstance(item.get("id"), str)
        ),
        key=lambda item: item["id"],
    )
    chain_validation_details = sorted(
        (
            validation_detail(item)
            for item in validations
            if item.get("subject_type") == "chain"
            and str(item.get("subject_id")) in related_chain_ids
            and isinstance(item.get("id"), str)
        ),
        key=lambda item: item["id"],
    )
    finding_validations = [
        item["id"]
        for item in finding_validation_details
    ]
    chain_validations = [
        item["id"]
        for item in chain_validation_details
    ]
    blocking_validations = [
        f"{item['id']}={item['decision']}"
        for item in finding_validation_details + chain_validation_details
        if item.get("decision") in BLOCKING_VALIDATION_DECISIONS
    ]
    owner_routing = first_owner_routing(finding_validation_details + chain_validation_details)

    proofs = artifacts.get("proofs", [])
    finding_proofs = sorted(
        str(item.get("id"))
        for item in proofs
        if str(item.get("finding_id")) == finding_id and isinstance(item.get("id"), str)
    )
    not_applicable, not_applicable_reason = proof_not_applicable(finding)
    safe_proof_exists = bool(finding_proofs)
    validation_exists = bool(finding_validations or chain_validations)

    warnings: List[str] = []
    warnings.extend(str(error) for error in artifacts.get("chain_errors", []))
    warnings.extend(str(error) for error in artifacts.get("proof_errors", []))
    warnings.extend(str(error) for error in artifacts.get("validation_errors", []))
    if chain_membership and not artifacts.get("chains_present"):
        warnings.append("finding declares chain_membership but reports/chains.json is absent")
    if missing_chains:
        warnings.append(f"finding references missing chain records: {', '.join(missing_chains)}")
    if (
        str(finding.get("severity") or "") in ADVANCED_REQUIRED_SEVERITIES
        and finding.get("issue_recommended") is not False
    ):
        if not validation_exists:
            warnings.append("High/Critical issue-recommended finding lacks related adversarial validation")
        if blocking_validations:
            warnings.append(f"related adversarial validation has blocking decision(s): {', '.join(blocking_validations)}")
        if not safe_proof_exists and not not_applicable:
            warnings.append("High/Critical issue-recommended finding lacks safe local proof or explicit not-applicable reason")

    return {
        "chain_membership": chain_membership,
        "chains": {
            "artifact_present": bool(artifacts.get("chains_present")),
            "matched": matched_chains,
            "missing": missing_chains,
            "referenced_by": referenced_by_chains,
        },
        "adversarial_validation": {
            "artifact_present": bool(artifacts.get("validations_present")),
            "finding_validations": finding_validations,
            "finding_validation_details": finding_validation_details,
            "chain_validations": chain_validations,
            "chain_validation_details": chain_validation_details,
            "blocking_decisions": blocking_validations,
            "owner_routing": owner_routing,
            "exists": validation_exists,
        },
        "safe_local_proof": {
            "artifact_present": bool(artifacts.get("proofs_present")),
            "proofs": finding_proofs,
            "exists": safe_proof_exists,
            "not_applicable": not_applicable,
            "not_applicable_reason": not_applicable_reason,
        },
        "warnings": warnings,
    }


def remediation_candidate_summary(finding: Dict[str, Any], artifacts: Dict[str, Any]) -> Dict[str, Any]:
    finding_id = str(finding.get("id") or "SEC-UNKNOWN")
    candidates = []
    patch_validations = [
        item
        for item in artifacts.get("patch_validations", [])
        if isinstance(item, dict) and str(item.get("finding_id") or "") == finding_id
    ]
    for item in artifacts.get("remediation_candidates", []):
        if not isinstance(item, dict) or str(item.get("finding_id") or "") != finding_id:
            continue
        validation_matches = sorted(
            (
                {
                    "report_file": str(validation.get("report_file") or ""),
                    "final_status": str(validation.get("final_status") or ""),
                    "patch_applied": bool(validation.get("patch_applied")),
                    "diff_scope_status": str(validation.get("diff_scope_status") or ""),
                    "sandbox_profile": str(validation.get("sandbox_profile") or ""),
                }
                for validation in patch_validations
                if str(validation.get("patch_id") or "") == str(item.get("id") or "")
            ),
            key=lambda validation: validation["report_file"],
        )
        candidates.append(
            {
                "id": str(item.get("id") or ""),
                "status": str(item.get("status") or ""),
                "patch_file": str(item.get("patch_file") or ""),
                "requires_human_review": bool(item.get("requires_human_review")),
                "patch_validation": {
                    "artifact_present": bool(artifacts.get("patch_validations_present")),
                    "exists": bool(validation_matches),
                    "results": validation_matches,
                },
            }
        )
    candidates.sort(key=lambda item: item["id"])
    warnings = [str(error) for error in artifacts.get("remediation_errors", [])]
    warnings.extend(str(error) for error in artifacts.get("patch_validation_errors", []))
    for candidate in candidates:
        validation = candidate.get("patch_validation") if isinstance(candidate.get("patch_validation"), dict) else {}
        for result in validation.get("results") or []:
            if isinstance(result, dict) and result.get("final_status") in {"failed", "needs-human-review"}:
                warnings.append(
                    f"remediation candidate {candidate.get('id')} patch validation status is {result.get('final_status')}"
                )
    return {
        "artifact_present": bool(artifacts.get("remediation_present")),
        "exists": bool(candidates),
        "candidates": candidates,
        "warnings": warnings,
    }


def matching_novelty_entry(repo: str, finding: Dict[str, Any], novelty_entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    entry = novelty_entries.get(str(finding.get("id") or ""))
    if not entry:
        return None
    current_fingerprint = stable_fingerprint(repo, finding)
    if str(entry.get("fingerprint") or "") != current_fingerprint:
        return None
    return entry


def novelty_summary(repo: str, finding: Dict[str, Any], novelty_entries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    finding_id = str(finding.get("id") or "")
    raw_entry = novelty_entries.get(finding_id)
    entry = matching_novelty_entry(repo, finding, novelty_entries)
    if not entry:
        return {
            "artifact_present": bool(raw_entry),
            "status": "stale-ignored" if raw_entry else "not-run",
            "issue_recommended": bool(finding.get("issue_recommended")),
            "suppresses_publication": False,
            "match_reasons": [],
            "warning": "novelty fingerprint did not match current finding" if raw_entry else None,
        }
    match = entry.get("match") if isinstance(entry.get("match"), dict) else {}
    return {
        "artifact_present": True,
        "status": str(entry.get("novelty_status") or "needs-human-review"),
        "issue_recommended": bool(entry.get("issue_recommended")),
        "suppresses_publication": novelty_suppresses_publication(entry),
        "previous_fingerprint": match.get("previous_fingerprint"),
        "match_reasons": [str(item) for item in match.get("reasons") or []],
    }


def advanced_validation_errors(entries: Iterable[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for entry in entries:
        finding_id = str(entry.get("id") or "SEC-UNKNOWN")
        advanced = entry.get("advanced_validation") if isinstance(entry.get("advanced_validation"), dict) else {}
        for warning in advanced.get("warnings") or []:
            errors.append(f"{finding_id}: {warning}")
        remediation = entry.get("remediation_candidate") if isinstance(entry.get("remediation_candidate"), dict) else {}
        for warning in remediation.get("warnings") or []:
            errors.append(f"{finding_id}: {warning}")
    return errors


def finding_selection_reason(
    finding: Dict[str, Any],
    min_severity: str,
    statuses: Iterable[str],
    *,
    repo: Optional[str] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    selected, reason = finding_selection_decision(
        finding,
        min_severity,
        statuses,
        repo=repo,
        novelty_entries=novelty_entries,
    )
    return "not selected by current filters" if selected else reason

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from novelty_ledger import novelty_by_finding_id

from .policy import (
    advanced_validation_summary,
    issue_title,
    load_advanced_artifacts,
    normalize_labels,
    novelty_summary,
    remediation_candidate_summary,
)
from .rendering import render_body, sha256_text, stable_fingerprint


def plan_finding_entry(
    repo: str,
    run_id: str,
    commit: str,
    finding: Dict[str, Any],
    run_dir: Path,
    advanced_artifacts: Optional[Dict[str, Any]] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], str]:
    fingerprint = stable_fingerprint(repo, finding)
    body = render_body(repo, run_id, commit, finding, fingerprint, run_dir)
    issue_body_file = str(finding.get("issue_body_file") or "")
    artifacts = advanced_artifacts if advanced_artifacts is not None else load_advanced_artifacts(run_dir)
    advanced = advanced_validation_summary(finding, artifacts)
    remediation = remediation_candidate_summary(finding, artifacts)
    novelty = novelty_summary(repo, finding, novelty_entries if novelty_entries is not None else novelty_by_finding_id(run_dir))
    entry: Dict[str, Any] = {
        "id": str(finding.get("id", "SEC-UNKNOWN")),
        "fingerprint": fingerprint,
        "title": issue_title(finding),
        "issue_body_sha256": sha256_text(body),
        "issue_body_file": issue_body_file or None,
        "labels": normalize_labels(finding),
        "public_disclosure_risk": str(finding.get("public_disclosure_risk") or "Unknown"),
        "chain_membership": advanced["chain_membership"],
        "advanced_validation": advanced,
        "owner_routing": advanced["adversarial_validation"].get("owner_routing") or {},
        "remediation_candidate": remediation,
        "novelty": novelty,
    }
    if isinstance(finding.get("external_source"), dict):
        entry["external_source"] = finding["external_source"]
    return entry, body


def plan_entry_key(entry: Dict[str, Any]) -> str:
    return f"{entry.get('id', 'SEC-UNKNOWN')}\0{entry.get('fingerprint', '')}"


def finding_key(finding_id: object, fingerprint: object) -> str:
    return f"{str(finding_id or 'SEC-UNKNOWN')}\0{str(fingerprint or '')}"


def build_publication_plan(
    *,
    repo: str,
    run_id: str,
    commit: str,
    visibility: str,
    findings: Iterable[Dict[str, Any]],
    run_dir: Path,
    generated_at: str,
    advanced_artifacts: Optional[Dict[str, Any]] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    selected_findings: List[Dict[str, Any]] = []
    bodies: Dict[str, str] = {}
    artifacts = advanced_artifacts if advanced_artifacts is not None else load_advanced_artifacts(run_dir)
    novelty = novelty_entries if novelty_entries is not None else novelty_by_finding_id(run_dir)
    for finding in findings:
        entry, body = plan_finding_entry(repo, run_id, commit, finding, run_dir, artifacts, novelty)
        selected_findings.append(entry)
        bodies[plan_entry_key(entry)] = body
    plan = {
        "schema_version": "1",
        "run_id": run_id,
        "repo": repo,
        "commit": commit,
        "created_at": generated_at,
        "visibility": visibility,
        "selected_findings": selected_findings,
    }
    return plan, bodies


def verify_plan_against_findings(
    *,
    plan: Dict[str, Any],
    repo: str,
    run_id: str,
    commit: str,
    current_findings: Iterable[Dict[str, Any]],
    run_dir: Path,
    advanced_artifacts: Optional[Dict[str, Any]] = None,
    novelty_entries: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[str]]:
    candidates_by_id: Dict[str, List[Tuple[Dict[str, Any], str]]] = {}
    artifacts = advanced_artifacts if advanced_artifacts is not None else load_advanced_artifacts(run_dir)
    novelty_entries = novelty_entries if novelty_entries is not None else novelty_by_finding_id(run_dir)
    for finding in current_findings:
        current_entry, body = plan_finding_entry(repo, run_id, commit, finding, run_dir, artifacts, novelty_entries)
        candidates_by_id.setdefault(str(current_entry["id"]), []).append((current_entry, body))
    selected: List[Dict[str, Any]] = []
    bodies: Dict[str, str] = {}
    errors: List[str] = []

    if str(plan.get("repo") or "") != repo:
        errors.append(f"repo mismatch: plan={plan.get('repo')!r} current={repo!r}")
    if str(plan.get("run_id") or "") != run_id:
        errors.append(f"run_id mismatch: plan={plan.get('run_id')!r} current={run_id!r}")
    if str(plan.get("commit") or "") != commit:
        errors.append(f"commit mismatch: plan={plan.get('commit')!r} current={commit!r}")

    for index, planned in enumerate(plan.get("selected_findings") or []):
        if not isinstance(planned, dict):
            errors.append(f"selected_findings[{index}] must be an object")
            continue
        finding_id = str(planned.get("id") or "")
        candidates = candidates_by_id.get(finding_id) or []
        if not candidates:
            errors.append(f"{finding_id or 'SEC-UNKNOWN'}: selected finding no longer exists")
            continue
        planned_fingerprint = planned.get("fingerprint")
        current_entry, body = next(
            ((entry, candidate_body) for entry, candidate_body in candidates if entry.get("fingerprint") == planned_fingerprint),
            candidates[0],
        )
        for field in [
            "fingerprint",
            "title",
            "issue_body_sha256",
            "issue_body_file",
            "public_disclosure_risk",
            "chain_membership",
            "advanced_validation",
            "owner_routing",
            "remediation_candidate",
            "novelty",
            "external_source",
        ]:
            if field not in planned and field in {"chain_membership", "advanced_validation", "owner_routing", "remediation_candidate", "novelty", "external_source"}:
                continue
            if planned.get(field) != current_entry.get(field):
                errors.append(f"{finding_id}: {field} changed after plan creation")
        if list(planned.get("labels") or []) != current_entry["labels"]:
            errors.append(f"{finding_id}: labels changed after plan creation")
        selected.append(current_entry)
        bodies[plan_entry_key(current_entry)] = body
    return selected, bodies, errors

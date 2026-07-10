from __future__ import annotations

import re
from typing import Any, Dict, List

from report_safety import (
    ReportSafetyError,
    iter_secret_findings,
    safe_issue_body_path,
    validate_relative_repo_path,
)
from taxonomies import validate_taxonomy_refs

from .common import json_type_name, validate_generated_at, validate_schema, validate_string_list
from .registry import ValidationContext


SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
CONFIDENCES = {"High", "Medium", "Low"}
STATUSES = {"Confirmed", "Probable", "Potential", "Informational", "Invalid", "Needs human review"}
ASSESSMENT_STATUSES = {"Confirmed", "Probable", "Potential", "Invalid", "Not assessed"}
REQUIRED_TOP = ["run_id", "repo", "commit", "generated_at", "findings"]
REQUIRED_FINDING = [
    "id",
    "fingerprint",
    "title",
    "severity",
    "confidence",
    "status",
    "category",
    "affected_locations",
    "entry_point",
    "trust_boundary",
    "source_to_sink",
    "root_cause",
    "evidence",
    "impact",
    "validation_status",
    "minimal_remediation",
    "regression_test_idea",
    "issue_title",
    "issue_body_file",
    "issue_recommended",
    "labels",
]
PLACEHOLDER_FINGERPRINTS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "todo",
    "tbd",
    "placeholder",
    "fingerprint",
    "fingerprint-001",
}


def validate_affected_locations(finding: Dict[str, Any], path: str, errors: List[str]) -> None:
    locs = finding.get("affected_locations")
    if not isinstance(locs, list):
        errors.append(f"{path}.affected_locations: affected_locations must be list")
        return
    for index, loc in enumerate(locs):
        loc_path = f"{path}.affected_locations[{index}]"
        if not isinstance(loc, dict):
            errors.append(f"{loc_path}: location must be object")
            continue
        try:
            validate_relative_repo_path(loc.get("file"), field_path=f"{loc_path}.file")
        except ReportSafetyError as exc:
            errors.append(str(exc))
        for key in ("line", "end_line"):
            if key in loc and loc.get(key) is not None:
                if not isinstance(loc.get(key), int) or isinstance(loc.get(key), bool):
                    errors.append(f"{loc_path}.{key}: {key} must be a positive integer or null")
                elif int(loc[key]) < 1:
                    errors.append(f"{loc_path}.{key}: {key} must be a positive integer")
        if isinstance(loc.get("line"), int) and isinstance(loc.get("end_line"), int) and loc["end_line"] < loc["line"]:
            errors.append(f"{loc_path}.end_line: end_line must be greater than or equal to line")


def validate_fingerprint(finding: Dict[str, Any], path: str, fingerprints: set[str], errors: List[str]) -> None:
    fingerprint = str(finding.get("fingerprint") or "").strip()
    if not fingerprint:
        errors.append(f"{path}.fingerprint: empty fingerprint")
    elif fingerprint.lower() in PLACEHOLDER_FINGERPRINTS or "placeholder" in fingerprint.lower():
        errors.append(f"{path}.fingerprint: fingerprint must not be a placeholder")
    elif len(fingerprint) < 8:
        errors.append(f"{path}.fingerprint: fingerprint must be at least 8 characters")
    elif fingerprint in fingerprints:
        errors.append(f"{path}.fingerprint: duplicate fingerprint {fingerprint}")
    fingerprints.add(fingerprint)


def validate_finding_assessments(finding: Dict[str, Any], path: str, errors: List[str]) -> None:
    for key in ["bug_existence", "attacker_reachability", "boundary_crossing", "impact_assessment"]:
        if key in finding and finding.get(key) not in ASSESSMENT_STATUSES:
            errors.append(f"{path}.{key}: invalid assessment value {finding.get(key)}")

    if "chain_membership" in finding:
        validate_string_list(finding.get("chain_membership"), f"{path}.chain_membership", errors)
        if isinstance(finding.get("chain_membership"), list):
            for index, chain_id in enumerate(finding["chain_membership"]):
                if isinstance(chain_id, str) and not re.fullmatch(r"CHAIN-[0-9]{3,}", chain_id):
                    errors.append(f"{path}.chain_membership[{index}]: chain id must match ^CHAIN-[0-9]{{3,}}$")

    if "assessment_notes" in finding:
        notes = finding.get("assessment_notes")
        if not isinstance(notes, dict):
            errors.append(f"{path}.assessment_notes: assessment_notes must be object")
            return
        for key in ["bug_existence", "attacker_reachability", "boundary_crossing", "impact_assessment"]:
            if key in notes and not isinstance(notes.get(key), str):
                errors.append(f"{path}.assessment_notes.{key}: expected type string, got {json_type_name(notes.get(key))}")


def validate_findings(context: ValidationContext) -> bool:
    data = context.findings_data
    errors = context.errors
    validate_schema(data, context.schema("findings.schema.json"), "findings", errors)
    validate_generated_at(data.get("generated_at"), "findings.generated_at", errors)
    for secret_error in iter_secret_findings(data, field_path="findings"):
        errors.append(secret_error)

    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"findings.{key}: missing top-level key")
    if not isinstance(data.get("findings"), list):
        errors.append("findings.findings: findings must be a list")

    fingerprints: set[str] = set()
    for index, finding in enumerate(context.findings):
        path = f"findings.findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{path}: finding must be an object")
            continue
        for key in REQUIRED_FINDING:
            if key not in finding:
                errors.append(f"{path}.{key}: missing key")
        if finding.get("severity") not in SEVERITIES:
            errors.append(f"{path}.severity: invalid severity {finding.get('severity')}")
        if finding.get("confidence") not in CONFIDENCES:
            errors.append(f"{path}.confidence: invalid confidence {finding.get('confidence')}")
        if finding.get("status") not in STATUSES:
            errors.append(f"{path}.status: invalid status {finding.get('status')}")
        validate_fingerprint(finding, path, fingerprints, errors)
        validate_affected_locations(finding, path, errors)
        validate_finding_assessments(finding, path, errors)
        if not isinstance(finding.get("labels"), list):
            errors.append(f"{path}.labels: labels must be list")
        if not isinstance(finding.get("issue_recommended"), bool):
            errors.append(f"{path}.issue_recommended: issue_recommended must be boolean")
        if context.taxonomy_profiles_loaded:
            validate_taxonomy_refs(
                finding.get("taxonomies"),
                f"{path}.taxonomies",
                errors,
                context.taxonomy_profiles,
                context.taxonomy_labels,
                context.taxonomy_aliases,
            )
        if finding.get("issue_recommended"):
            if "public_disclosure_risk" not in finding:
                errors.append(f"{path}.public_disclosure_risk: required when issue_recommended is true")
            body_file = str(finding.get("issue_body_file") or "")
            if body_file:
                try:
                    safe_issue_body_path(context.run_dir, body_file, field_path=f"{path}.issue_body_file")
                except ReportSafetyError as exc:
                    errors.append(str(exc))
        elif finding.get("issue_body_file"):
            try:
                safe_issue_body_path(
                    context.run_dir,
                    finding.get("issue_body_file"),
                    field_path=f"{path}.issue_body_file",
                )
            except ReportSafetyError as exc:
                errors.append(str(exc))
    return True

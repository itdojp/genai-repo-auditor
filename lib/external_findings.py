from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any

from gralib import load_context, load_json, utc_now, write_json
from report_safety import ReportSafetyError, validate_relative_repo_path
from scanner_normalize import redact_text, sha256_short

SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
CONFIDENCES = {"High", "Medium", "Low"}
STATUSES = {"Confirmed", "Probable", "Potential", "Informational", "Invalid", "Needs human review"}
APPEND_STATUSES = {"review-only", "appended", "duplicate-skipped"}
MAX_IMPORTED_FINDINGS = 500
MAX_REJECTED_FINDINGS = 500
SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class ExternalFindingImportError(RuntimeError):
    """Raised when the external finding import cannot be performed safely."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    raw = Path(str(ctx.get("reports_dir", "reports") or "reports"))
    if raw.is_absolute() or PureWindowsPath(str(raw)).is_absolute():
        raise ExternalFindingImportError(f"reports_dir must be relative under run directory: {raw}")
    if raw == Path(".") or ".." in raw.parts:
        raise ExternalFindingImportError(f"reports_dir must not contain path traversal: {raw}")
    reports = run_dir / raw
    current = run_dir
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise ExternalFindingImportError(f"reports_dir must not contain symlink components: {raw}")
    try:
        reports.resolve(strict=False).relative_to(run_dir.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise ExternalFindingImportError(f"reports_dir must stay under run directory: {raw}") from exc
    return reports


def normalize_enum(value: Any, allowed: set[str], aliases: dict[str, str], *, field: str) -> tuple[str | None, str | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, f"{field} is required"
    normalized_key = raw.lower().replace("_", "-").replace(" ", "-")
    candidate = aliases.get(normalized_key, raw[:1].upper() + raw[1:])
    if candidate not in allowed:
        return None, f"{field} {raw!r} is not supported"
    return candidate, None


def normalize_severity(value: Any) -> tuple[str | None, str | None]:
    return normalize_enum(
        value,
        SEVERITIES,
        {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "info": "Informational",
            "informational": "Informational",
        },
        field="severity",
    )


def normalize_confidence(value: Any) -> tuple[str | None, str | None]:
    return normalize_enum(
        value,
        CONFIDENCES,
        {"high": "High", "medium": "Medium", "low": "Low"},
        field="confidence",
    )


def normalize_status(value: Any) -> tuple[str | None, str | None]:
    return normalize_enum(
        value,
        STATUSES,
        {
            "confirmed": "Confirmed",
            "probable": "Probable",
            "potential": "Potential",
            "informational": "Informational",
            "info": "Informational",
            "invalid": "Invalid",
            "needs-human-review": "Needs human review",
            "needs-review": "Needs human review",
        },
        field="status",
    )


def safe_source_label(source: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", source.strip())[:80].strip("-._")
    return value or "external-tool"


def safe_label_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return token[:40] or "external"


def redacted_string(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return redact_text(text)


def normalize_locations(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(value, list) or not value:
        return [], ["affected_locations must be a non-empty array"]
    locations: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        field = f"affected_locations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{field} must be an object")
            continue
        try:
            file_path = validate_relative_repo_path(item.get("file"), field_path=f"{field}.file")
        except ReportSafetyError as exc:
            errors.append(str(exc))
            continue
        loc: dict[str, Any] = {"file": file_path}
        for key in ("line", "end_line"):
            if key in item and item.get(key) is not None:
                line_value = item.get(key)
                if isinstance(line_value, bool) or not isinstance(line_value, int) or line_value < 1:
                    errors.append(f"{field}.{key} must be a positive integer or null")
                    continue
                loc[key] = line_value
        if isinstance(loc.get("line"), int) and isinstance(loc.get("end_line"), int) and loc["end_line"] < loc["line"]:
            errors.append(f"{field}.end_line must be greater than or equal to line")
        locations.append(loc)
    return locations, errors


def normalized_fingerprint(*, source: str, external_id: str, title: str, severity: str, locations: list[dict[str, Any]], evidence: str) -> str:
    location_key = json.dumps(locations, sort_keys=True, separators=(",", ":"))
    return sha256_short("|".join(["external-finding", source, external_id, title, severity, location_key, evidence]), length=24)


def import_id_for(*, source: str, external_id: str, fingerprint: str) -> str:
    stable = sha256_short("|".join([source, external_id, fingerprint]), length=12).upper()
    return f"IMP-{stable}"


def build_finding_record(
    *,
    source: str,
    source_version: str,
    external_id: str,
    index: int,
    import_id: str,
    fingerprint: str,
    title: str,
    severity: str,
    confidence: str,
    status: str,
    category: str,
    locations: list[dict[str, Any]],
    evidence: str,
    minimal_remediation: str,
    imported_at: str,
) -> dict[str, Any]:
    source_label = safe_label_token(source)
    return {
        "id": import_id,
        "fingerprint": fingerprint,
        "title": title,
        "severity": severity,
        "confidence": confidence,
        "status": status,
        "category": category,
        "affected_locations": locations,
        "entry_point": "Imported external finding; human review required before publication.",
        "trust_boundary": "Imported external finding; not assessed locally.",
        "source_to_sink": "Imported external finding; not assessed locally.",
        "root_cause": "Imported external finding; root cause not assessed locally.",
        "evidence": evidence or "Imported external finding did not provide evidence.",
        "impact": "Imported external finding; impact requires local human review.",
        "validation_status": "imported-needs-human-review",
        "minimal_remediation": minimal_remediation or "Review the imported recommendation and produce a local remediation plan.",
        "regression_test_idea": "Add a local regression test after validating the imported finding.",
        "issue_title": f"[Security][{severity}] {title}",
        "issue_body_file": "",
        "issue_recommended": False,
        "labels": ["security", "external-import", "needs-review", f"source-{source_label}"],
        "bug_existence": "Not assessed",
        "attacker_reachability": "Not assessed",
        "boundary_crossing": "Not assessed",
        "impact_assessment": "Not assessed",
        "assessment_notes": {
            "external_import": "Imported record requires local validation before issue publication.",
        },
        "external_source": {
            "source": source,
            "source_version": source_version,
            "external_id": external_id,
            "input_index": index,
            "imported_at": imported_at,
        },
    }


def normalize_external_record(
    *,
    source: str,
    source_version: str,
    item: Any,
    index: int,
    imported_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(item, dict):
        return None, {"index": index, "external_id": "", "title": "", "reasons": ["record must be an object"]}

    reasons: list[str] = []
    external_id = redacted_string(item.get("external_id"))
    if not external_id:
        reasons.append("external_id is required")
    title = redacted_string(item.get("title"))
    if not title:
        reasons.append("title is required")
    severity, severity_error = normalize_severity(item.get("severity"))
    if severity_error:
        reasons.append(severity_error)
    confidence, confidence_error = normalize_confidence(item.get("confidence"))
    if confidence_error:
        reasons.append(confidence_error)
    status, status_error = normalize_status(item.get("status"))
    if status_error:
        reasons.append(status_error)
    category = redacted_string(item.get("category"), fallback="external-import")
    if not category:
        reasons.append("category is required")
    locations, location_errors = normalize_locations(item.get("affected_locations"))
    reasons.extend(location_errors)
    evidence = redacted_string(item.get("evidence"), fallback="Imported external finding did not provide evidence.")
    minimal_remediation = redacted_string(
        item.get("minimal_remediation"),
        fallback="Review the imported recommendation and produce a local remediation plan.",
    )

    if reasons:
        return None, {
            "index": index,
            "external_id": external_id,
            "title": title,
            "reasons": reasons,
            "redacted_evidence": evidence,
        }

    assert severity is not None and confidence is not None and status is not None
    fingerprint = normalized_fingerprint(
        source=source,
        external_id=external_id,
        title=title,
        severity=severity,
        locations=locations,
        evidence=evidence,
    )
    import_id = import_id_for(source=source, external_id=external_id, fingerprint=fingerprint)
    finding = build_finding_record(
        source=source,
        source_version=source_version,
        external_id=external_id,
        index=index,
        import_id=import_id,
        fingerprint=fingerprint,
        title=title,
        severity=severity,
        confidence=confidence,
        status=status,
        category=category,
        locations=locations,
        evidence=evidence,
        minimal_remediation=minimal_remediation,
        imported_at=imported_at,
    )
    normalized = {
        "import_id": import_id,
        "external_id": external_id,
        "source": source,
        "source_version": source_version,
        "input_index": index,
        "fingerprint": fingerprint,
        "title": title,
        "severity": severity,
        "confidence": confidence,
        "status": status,
        "category": category,
        "affected_locations": locations,
        "evidence": evidence,
        "minimal_remediation": minimal_remediation,
        "append_status": "review-only",
        "normalized_finding": finding,
    }
    return normalized, None


def load_external_payload(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ExternalFindingImportError(f"external finding file is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExternalFindingImportError("external finding file must contain a JSON object")
    source = str(data.get("source") or "").strip()
    if not SOURCE_RE.fullmatch(source):
        raise ExternalFindingImportError("source must match ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ExternalFindingImportError("findings must be an array")
    if len(findings) > MAX_IMPORTED_FINDINGS:
        raise ExternalFindingImportError(f"findings must contain at most {MAX_IMPORTED_FINDINGS} records")
    return data


def load_or_create_findings(run_dir: Path, reports: Path, ctx: dict[str, Any]) -> dict[str, Any]:
    path = reports / "findings.json"
    data = load_json(path, None)
    if isinstance(data, dict):
        data.setdefault("run_id", ctx.get("run_id", run_dir.name))
        data.setdefault("repo", ctx.get("repo", ""))
        data.setdefault("commit", ctx.get("commit", ""))
        data.setdefault("generated_at", utc_now())
        data.setdefault("findings", [])
        return data
    return {
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "branch": ctx.get("branch", ""),
        "commit": ctx.get("commit", ""),
        "visibility": ctx.get("visibility", "UNKNOWN"),
        "generated_at": utc_now(),
        "findings": [],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Imported findings",
        "",
        "Local review artifact for vendor-neutral external finding imports.",
        "Raw proprietary exports are not embedded; normalized evidence and rejected leads are redacted/bounded.",
        "",
        "## Summary",
        "",
        f"- Source: `{report.get('source', '')}`",
        f"- Source version: `{report.get('source_version', '') or 'not provided'}`",
        f"- Valid findings: {summary.get('valid_count', 0)}",
        f"- Rejected leads: {summary.get('rejected_count', 0)}",
        f"- Appended findings: {summary.get('appended_count', 0)}",
        f"- Duplicate skipped: {summary.get('duplicate_skipped_count', 0)}",
        "",
        "## Normalized findings",
        "",
        "| Import ID | External ID | Severity | Confidence | Status | Append status | Title |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report.get("findings") or []:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|")
                for value in [
                    item.get("import_id", ""),
                    item.get("external_id", ""),
                    item.get("severity", ""),
                    item.get("confidence", ""),
                    item.get("status", ""),
                    item.get("append_status", ""),
                    item.get("title", ""),
                ]
            )
            + " |"
        )
    if not report.get("findings"):
        lines.append("| _none_ |  |  |  |  |  |  |")
    lines.extend(["", "## Rejected leads", "", "| Index | External ID | Title | Reasons |", "| --- | --- | --- | --- |"])
    for item in report.get("rejected_findings") or []:
        if not isinstance(item, dict):
            continue
        reasons = "; ".join(str(reason) for reason in item.get("reasons") or [])
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|")
                for value in [item.get("index", ""), item.get("external_id", ""), item.get("title", ""), reasons]
            )
            + " |"
        )
    if not report.get("rejected_findings"):
        lines.append("| _none_ |  |  |  |")
    lines.extend(["", "## Publication note", "", "Imported findings are appended with `issue_recommended=false`; run local validation and explicitly review findings before enabling issue publication.", ""])
    return "\n".join(lines)


def import_external_findings(run_dir: Path, input_file: Path, *, append_findings: bool = False) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    input_file = input_file.resolve()
    if not input_file.exists() or not input_file.is_file():
        raise ExternalFindingImportError(f"external finding file not found: {input_file}")
    ctx = load_context(run_dir)
    reports = safe_reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    payload = load_external_payload(input_file)
    source = safe_source_label(str(payload.get("source") or "external-tool"))
    source_version = redacted_string(payload.get("source_version"))
    imported_at = utc_now()
    normalized_findings: list[dict[str, Any]] = []
    rejected_findings: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("findings") or []):
        normalized, rejected = normalize_external_record(
            source=source,
            source_version=source_version,
            item=item,
            index=index,
            imported_at=imported_at,
        )
        if normalized is not None:
            normalized_findings.append(normalized)
        elif rejected is not None and len(rejected_findings) < MAX_REJECTED_FINDINGS:
            rejected_findings.append(rejected)

    appended_count = 0
    duplicate_skipped_count = 0
    seen_import_fingerprints: set[str] = set()
    for item in normalized_findings:
        fingerprint = str(item.get("fingerprint") or "")
        if fingerprint in seen_import_fingerprints:
            item["append_status"] = "duplicate-skipped"
            item["duplicate_reason"] = "fingerprint already present in this import"
            duplicate_skipped_count += 1
        else:
            seen_import_fingerprints.add(fingerprint)
    if append_findings:
        findings_data = load_or_create_findings(run_dir, reports, ctx)
        existing = findings_data.get("findings")
        if not isinstance(existing, list):
            raise ExternalFindingImportError("reports/findings.json findings must be an array before append")
        existing_fingerprints = {str(item.get("fingerprint") or "") for item in existing if isinstance(item, dict)}
        for item in normalized_findings:
            if item.get("append_status") == "duplicate-skipped":
                continue
            fingerprint = str(item.get("fingerprint") or "")
            if fingerprint in existing_fingerprints:
                item["append_status"] = "duplicate-skipped"
                item["duplicate_reason"] = "fingerprint already present in reports/findings.json"
                duplicate_skipped_count += 1
                continue
            finding = item.get("normalized_finding")
            if isinstance(finding, dict):
                existing.append(finding)
                existing_fingerprints.add(fingerprint)
                item["append_status"] = "appended"
                appended_count += 1
        findings_data["generated_at"] = utc_now()
        write_json(reports / "findings.json", findings_data)

    report = {
        "schema_version": "1",
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": imported_at,
        "source": source,
        "source_version": source_version,
        "source_file": {
            "name": redacted_string(input_file.name, fallback="external-findings.json"),
            "sha256": file_sha256(input_file),
            "bytes": input_file.stat().st_size,
        },
        "append_findings": append_findings,
        "summary": {
            "input_count": len(payload.get("findings") or []),
            "valid_count": len(normalized_findings),
            "rejected_count": len(rejected_findings),
            "appended_count": appended_count,
            "duplicate_skipped_count": duplicate_skipped_count,
        },
        "findings": normalized_findings,
        "rejected_findings": rejected_findings,
    }
    write_json(reports / "imported-findings.json", report)
    (reports / "IMPORTED_FINDINGS.md").write_text(render_markdown(report), encoding="utf-8")
    return report

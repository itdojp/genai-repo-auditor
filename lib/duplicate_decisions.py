from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from gralib import write_run_artifact_text
from run_events import reports_dir


DUPLICATE_DECISIONS_REL_DIR = Path("reports") / "duplicate-decisions"
DECISION_VALUES = {"new", "exact-duplicate", "variant", "related-not-duplicate"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def duplicate_decisions_dir(run_dir: Path) -> Path:
    return reports_dir(run_dir) / DUPLICATE_DECISIONS_REL_DIR.name


def safe_filename(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "SEC-UNKNOWN")).strip(".-")
    return text[:120] or "SEC-UNKNOWN"


def rel_to_run(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def sha256_short(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def issue_number_from_url(url: object) -> int | None:
    match = re.search(r"/issues/(\d+)(?:[#?].*)?$", str(url or ""))
    return int(match.group(1)) if match else None


def unique_ints(values: Iterable[object]) -> list[int]:
    out: set[int] = set()
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            out.add(value)
            continue
        text = str(value or "").strip()
        if text.isdigit():
            out.add(int(text))
            continue
        number = issue_number_from_url(text)
        if number is not None:
            out.add(number)
    return sorted(out)


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def finding_related_issue_numbers(finding: dict[str, Any]) -> list[int]:
    candidates: list[object] = []
    for field in [
        "related_issue_numbers",
        "related_issues",
        "candidate_issue_numbers",
        "candidate_issues",
    ]:
        value = finding.get(field)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)
    return unique_ints(candidates)


def decision_path_for(run_dir: Path, finding_id: object, fingerprint: object) -> Path:
    directory = duplicate_decisions_dir(run_dir)
    base = directory / f"{safe_filename(finding_id)}.json"
    if not base.exists():
        return base
    try:
        existing = json.loads(base.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if str(existing.get("finding_id") or "") == str(finding_id or "") and str(existing.get("fingerprint") or "") == str(fingerprint or ""):
        return base
    fingerprint_suffix = safe_filename(str(fingerprint or ""))[:24] or "no-fingerprint"
    return directory / f"{safe_filename(finding_id)}--{fingerprint_suffix}.json"


def decision_for(
    *,
    run_id: str,
    repo: str,
    commit: str,
    finding: dict[str, Any],
    fingerprint: str,
    exact_match_url: str | None = None,
    exact_match_source: str | None = None,
) -> dict[str, Any]:
    finding_id = str(finding.get("id") or "SEC-UNKNOWN")
    variant_of = string_list(finding.get("variant_of"))
    candidate_issue_numbers = finding_related_issue_numbers(finding)
    exact_issue_number = issue_number_from_url(exact_match_url or "")
    if exact_issue_number is not None:
        candidate_issue_numbers = unique_ints(candidate_issue_numbers + [exact_issue_number])

    exact_match = bool(exact_match_url)
    if exact_match:
        decision = "exact-duplicate"
        rationale = f"Exact fingerprint match found via {exact_match_source or 'duplicate check'}."
    elif variant_of:
        decision = "variant"
        rationale = "Finding declares variant_of; record it as a variant rather than an exact duplicate."
    elif candidate_issue_numbers:
        decision = "related-not-duplicate"
        rationale = "Related candidate issue(s) were recorded, but no exact fingerprint match was found."
    else:
        decision = "new"
        rationale = "No exact duplicate, variant marker, or related candidate issue was found."

    root_cause_basis = {
        "category": finding.get("category"),
        "title": finding.get("title") or finding.get("issue_title"),
        "root_cause": finding.get("root_cause"),
        "minimal_remediation": finding.get("minimal_remediation"),
    }
    source_to_sink_basis = {
        "entry_point": finding.get("entry_point"),
        "trust_boundary": finding.get("trust_boundary"),
        "call_path": finding.get("call_path") or finding.get("source_to_sink"),
        "affected_locations": finding.get("affected_locations"),
    }
    return {
        "schema_version": "1",
        "run_id": run_id,
        "repo": repo,
        "commit": commit,
        "finding_id": finding_id,
        "fingerprint": fingerprint,
        "candidate_issue_numbers": candidate_issue_numbers,
        "exact_match": exact_match,
        "exact_match_source": exact_match_source if exact_match else None,
        "exact_match_url": exact_match_url if exact_match else None,
        "variant_of": variant_of,
        "root_cause_fingerprint": sha256_short(root_cause_basis),
        "source_to_sink_fingerprint": sha256_short(source_to_sink_basis),
        "decision": decision,
        "rationale": rationale,
        "checked_at": utc_now(),
        "source": "gra-issues",
    }


def write_duplicate_decision(run_dir: Path, decision: dict[str, Any]) -> Path:
    path = decision_path_for(run_dir, decision.get("finding_id"), decision.get("fingerprint"))
    write_run_artifact_text(
        run_dir,
        path,
        json.dumps(decision, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )
    return path


def load_duplicate_decisions(run_dir: Path) -> list[dict[str, Any]]:
    directory = duplicate_decisions_dir(run_dir)
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{rel_to_run(run_dir, path)} must contain a JSON object")
        data = dict(data)
        data["_path"] = rel_to_run(run_dir, path)
        records.append(data)
    return records


def matching_decision(records: Iterable[dict[str, Any]], *, finding_id: object, fingerprint: object) -> dict[str, Any] | None:
    for record in records:
        if str(record.get("finding_id") or "") == str(finding_id or "") and str(record.get("fingerprint") or "") == str(fingerprint or ""):
            return record
    return None


def verify_ledger_decisions(run_dir: Path, ledger: dict[str, Any]) -> list[str]:
    try:
        records = load_duplicate_decisions(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"duplicate decisions could not be read: {exc}"]
    errors: list[str] = []
    for entry in ledger.get("findings") or []:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("publication_status") or "")
        if status not in {"published", "duplicate"}:
            continue
        finding_id = str(entry.get("finding_id") or "SEC-UNKNOWN")
        fingerprint = str(entry.get("fingerprint") or "")
        record = matching_decision(records, finding_id=finding_id, fingerprint=fingerprint)
        if not record:
            errors.append(f"{finding_id}: duplicate decision record missing for published ledger fingerprint {fingerprint}")
            continue
        decision = str(record.get("decision") or "")
        if decision not in DECISION_VALUES:
            errors.append(f"{finding_id}: duplicate decision has invalid decision {decision!r}")
        if status == "duplicate" and decision != "exact-duplicate":
            errors.append(f"{finding_id}: duplicate ledger entry requires exact-duplicate decision, got {decision!r}")
    return errors


def duplicate_decision_metrics(records: Any, present: bool) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    if isinstance(records, list):
        decisions = [item for item in records if isinstance(item, dict)]
    by_decision: dict[str, int] = {}
    exact_match_count = 0
    candidate_issue_count = 0
    for record in decisions:
        decision = str(record.get("decision") or "unknown")
        by_decision[decision] = by_decision.get(decision, 0) + 1
        if record.get("exact_match") is True:
            exact_match_count += 1
        candidates = record.get("candidate_issue_numbers")
        if isinstance(candidates, list):
            candidate_issue_count += len(candidates)
    return {
        "artifact_present": present,
        "total": len(decisions),
        "by_decision": by_decision,
        "exact_match_count": exact_match_count,
        "candidate_issue_count": candidate_issue_count,
    }

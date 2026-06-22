from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

LEDGER_REL_PATH = Path("reports") / "issue-ledger.json"
PUBLISHED_STATUSES = {"published", "duplicate"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_ledger_path(run_dir: Path) -> Path:
    return run_dir / LEDGER_REL_PATH


def issue_number_from_url(url: str) -> int | None:
    match = re.search(r"/issues/(\d+)(?:[#?].*)?$", str(url or ""))
    return int(match.group(1)) if match else None


def finding_key(finding_id: object, fingerprint: object) -> str:
    return f"{str(finding_id or '')}\0{str(fingerprint or '')}"


def entry_key(entry: dict[str, Any]) -> str:
    return finding_key(entry.get("finding_id"), entry.get("fingerprint"))


def empty_ledger(
    *,
    run_id: str,
    repo: str,
    commit: str,
    generated_at: str | None = None,
    plan_written: bool | None = None,
    publication_plan_status: str | None = None,
) -> dict[str, Any]:
    ledger = {
        "schema_version": "1",
        "run_id": run_id,
        "repo": repo,
        "commit": commit,
        "generated_at": generated_at or utc_now(),
        "source": "gra-issues",
        "findings": [],
        "warnings": [],
    }
    if plan_written is not None:
        ledger["plan_written"] = bool(plan_written)
    if publication_plan_status:
        ledger["publication_plan_status"] = publication_plan_status
    return ledger


def load_ledger(path: Path, *, run_id: str, repo: str, commit: str) -> dict[str, Any]:
    if not path.exists():
        return empty_ledger(run_id=run_id, repo=repo, commit=commit)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("issue ledger must be a JSON object")
    if not isinstance(data.get("findings"), list):
        raise ValueError("issue ledger must contain findings array")
    return data


def write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def entries_by_key(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for item in ledger.get("findings") or []:
        if not isinstance(item, dict):
            continue
        key = entry_key(item)
        if key.strip("\0"):
            entries[key] = item
    return entries


def published_entry(ledger: dict[str, Any], *, finding_id: object, fingerprint: object) -> dict[str, Any] | None:
    entry = entries_by_key(ledger).get(finding_key(finding_id, fingerprint))
    if not entry:
        return None
    if entry.get("url") and str(entry.get("publication_status") or "") in PUBLISHED_STATUSES:
        return entry
    return None


def published_entry_by_finding_id(ledger: dict[str, Any], *, finding_id: object) -> dict[str, Any] | None:
    matches = [
        entry
        for entry in (ledger.get("findings") or [])
        if isinstance(entry, dict)
        and str(entry.get("finding_id") or "") == str(finding_id or "")
        and entry.get("url")
        and str(entry.get("publication_status") or "") in PUBLISHED_STATUSES
    ]
    return matches[0] if len(matches) == 1 else None


def plan_source(plan_path: Path | None, run_dir: Path) -> str | None:
    if plan_path is None:
        return None
    try:
        return plan_path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(plan_path)


def base_entry(
    *,
    finding_id: str,
    fingerprint: str,
    title: str,
    labels: Iterable[str],
    body_hash: str | None,
    publication_status: str,
    selection_reason: str | None = None,
    source_plan: str | None = None,
    plan_sha256: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "finding_id": finding_id,
        "fingerprint": fingerprint,
        "publication_status": publication_status,
        "issue_number": None,
        "state": None,
        "url": None,
        "title": title,
        "labels": list(labels),
        "body_hash": body_hash,
        "published_at": None,
        "source_plan": source_plan,
        "plan_sha256": plan_sha256,
        "drift": [],
    }
    if selection_reason:
        entry["selection_reason"] = selection_reason
    return entry


def mark_published(
    entry: dict[str, Any],
    *,
    url: str,
    published_at: str | None = None,
    duplicate_detected: bool = False,
    state: str = "open",
) -> dict[str, Any]:
    updated = dict(entry)
    updated.update(
        {
            "publication_status": "duplicate" if duplicate_detected else "published",
            "issue_number": issue_number_from_url(url),
            "state": state,
            "url": url,
            "published_at": published_at or utc_now(),
        }
    )
    if duplicate_detected:
        updated["duplicate_detected"] = True
    return updated


def mark_dry_run(entry: dict[str, Any]) -> dict[str, Any]:
    updated = dict(entry)
    updated["publication_status"] = "dry-run"
    return updated


def merge_current_entries(
    *,
    existing: dict[str, Any],
    current_entries: Iterable[dict[str, Any]],
    run_id: str,
    repo: str,
    commit: str,
    plan_written: bool | None = None,
    publication_plan_status: str | None = None,
) -> dict[str, Any]:
    old_entries = entries_by_key(existing)
    merged_entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    superseded: set[str] = set()

    for current in current_entries:
        key = entry_key(current)
        seen.add(key)
        previous_fingerprint = current.get("previous_fingerprint")
        if previous_fingerprint:
            superseded.add(finding_key(current.get("finding_id"), previous_fingerprint))
        previous = old_entries.get(key)
        if previous and previous.get("url") and str(previous.get("publication_status") or "") in PUBLISHED_STATUSES:
            merged = dict(current)
            for field in ["publication_status", "issue_number", "state", "url", "published_at", "duplicate_detected"]:
                if field in previous:
                    merged[field] = previous.get(field)
            if previous.get("body_hash") and current.get("body_hash") and previous.get("body_hash") != current.get("body_hash"):
                merged["current_body_hash"] = current.get("body_hash")
                merged.setdefault("drift", [])
                merged["drift"] = list(merged.get("drift") or []) + ["current issue body hash differs from published ledger body_hash"]
                warnings.append(f"{current.get('finding_id')}: current issue body hash differs from published ledger body_hash")
            merged_entries.append(merged)
        else:
            merged_entries.append(dict(current))

    for key, previous in old_entries.items():
        if key not in seen and key not in superseded:
            orphan = dict(previous)
            orphan.setdefault("drift", [])
            orphan["drift"] = list(orphan.get("drift") or []) + ["finding is no longer present in current findings.json"]
            warnings.append(f"{previous.get('finding_id')}: ledger entry is not present in current findings.json")
            merged_entries.append(orphan)

    ledger = {
        "schema_version": "1",
        "run_id": run_id,
        "repo": repo,
        "commit": commit,
        "generated_at": utc_now(),
        "source": "gra-issues",
        "findings": sorted(merged_entries, key=lambda item: (str(item.get("finding_id") or ""), str(item.get("fingerprint") or ""))),
        "warnings": sorted(set(warnings + [str(item) for item in existing.get("warnings") or [] if item])),
    }
    if plan_written is not None:
        ledger["plan_written"] = bool(plan_written)
    elif isinstance(existing.get("plan_written"), bool):
        ledger["plan_written"] = existing["plan_written"]
    if publication_plan_status:
        ledger["publication_plan_status"] = publication_plan_status
    elif isinstance(existing.get("publication_plan_status"), str):
        ledger["publication_plan_status"] = existing["publication_plan_status"]
    return ledger


def ledger_metrics(ledger: Any, present: bool) -> dict[str, Any]:
    entries = []
    warnings = []
    if isinstance(ledger, dict):
        entries = [item for item in ledger.get("findings") or [] if isinstance(item, dict)]
        warnings = [str(item) for item in ledger.get("warnings") or [] if str(item)]
    by_status: dict[str, int] = {}
    drift_count = len(warnings)
    for entry in entries:
        status = str(entry.get("publication_status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        drift_count += len(entry.get("drift") or []) if isinstance(entry.get("drift"), list) else 0
    return {
        "artifact_present": present,
        "tracked_findings": len(entries),
        "published_findings": sum(1 for entry in entries if entry.get("url")),
        "by_publication_status": by_status,
        "drift_warning_count": drift_count,
    }

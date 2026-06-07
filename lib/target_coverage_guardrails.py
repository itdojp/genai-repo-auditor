from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any


TARGET_REVIEW_DEPTHS = {"none", "shallow", "medium", "deep"}
TARGET_REVIEW_DEPTH_ALIASES = {
    "bounded-deep": "deep",
    "bounded_deep": "deep",
    "bounded deep": "deep",
}


class CoverageSerializationError(ValueError):
    """Raised when target coverage metadata cannot be serialized safely."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_review_depth(value: Any, *, field_path: str) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip():
        raise CoverageSerializationError(f"{field_path}: review_depth must be a non-empty string")
    raw = value.strip()
    normalized = TARGET_REVIEW_DEPTH_ALIASES.get(raw.lower(), raw.lower())
    if normalized not in TARGET_REVIEW_DEPTHS:
        allowed = ", ".join(sorted(TARGET_REVIEW_DEPTHS))
        aliases = ", ".join(sorted(TARGET_REVIEW_DEPTH_ALIASES))
        raise CoverageSerializationError(
            f"{field_path}: invalid review depth {value!r}; allowed values: {allowed}; aliases: {aliases}"
        )
    reason = None
    if raw.lower() in TARGET_REVIEW_DEPTH_ALIASES:
        reason = f"normalized coverage.review_depth alias {value!r} -> {normalized!r}"
    elif normalized != value:
        reason = f"canonicalized coverage.review_depth value {value!r} -> {normalized!r}"
    return normalized, reason


def normalize_targets_coverage_for_write(targets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_targets = copy.deepcopy(targets)
    changes: list[dict[str, Any]] = []
    for index, target in enumerate(normalized_targets):
        if not isinstance(target, dict):
            continue
        coverage = target.get("coverage")
        if coverage is None:
            continue
        path = f"targets.targets[{index}].coverage"
        if not isinstance(coverage, dict):
            raise CoverageSerializationError(f"{path}: coverage must be an object")
        if "review_depth" not in coverage:
            continue
        before = coverage.get("review_depth")
        normalized, reason = normalize_review_depth(before, field_path=f"{path}.review_depth")
        coverage["review_depth"] = normalized
        if reason:
            changes.append(
                {
                    "field_path": f"{path}.review_depth",
                    "target_id": str(target.get("id") or f"index-{index}"),
                    "before": before,
                    "after": normalized,
                    "reason": reason,
                }
            )
    return normalized_targets, changes


def append_coverage_normalization_log(reports_dir: Path, changes: list[dict[str, Any]]) -> None:
    if not changes:
        return
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now()
    jsonl_path = reports_dir / "coverage-normalizations.jsonl"
    with jsonl_path.open("a", encoding="utf-8") as handle:
        for change in changes:
            event = {
                "timestamp": timestamp,
                "source": "write_targets",
                **change,
            }
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    audit_log = reports_dir / "AUDIT_LOG.md"
    lines = [
        "",
        f"## Coverage normalization - {timestamp}",
        "",
    ]
    for change in changes:
        lines.append(
            f"- `{change['field_path']}` for `{change['target_id']}`: "
            f"`{change['before']}` -> `{change['after']}` ({change['reason']})"
        )
    with audit_log.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


TARGET_SOURCES = (
    "model_generated",
    "agent_surface",
    "provenance",
    "scorecard",
    "dependency",
    "scanner",
    "gapfill",
)
BUDGETED_TARGET_SOURCES = tuple(source for source in TARGET_SOURCES if source != "gapfill")
POLICIES = ("strict", "risk-weighted")
DEFAULT_TOTAL_BUDGET = 20
DEFAULT_SOURCE_BUDGET = 10
MAX_BUDGET = 1000
MAX_TARGETS = 4096
MAX_LINEAGE = 64
MAX_TEXT = 240
MAX_NORMALIZATION_INPUT = 4096
TARGET_ID_RE = re.compile(r"^TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}$")
TARGET_STATUSES = {"queued", "in_progress", "reviewed", "skipped", "needs_human_review"}
RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
SOURCE_ORDER = {name: index for index, name in enumerate(TARGET_SOURCES)}
CANONICAL_SOURCE_ORDER = {
    name: index
    for index, name in enumerate(
        ("scanner", "dependency", "agent_surface", "provenance", "scorecard", "gapfill", "model_generated")
    )
}
LIST_FIELDS = (
    "entry_points",
    "trust_boundaries",
    "sinks",
    "security_invariants",
    "review_questions",
    "candidate_files",
)
EVIDENCE_REFS = {
    "model_generated": ("prompts/exec/generate-targets.prompt.md",),
    "agent_surface": ("reports/agent-surface.json",),
    "provenance": ("reports/provenance-posture.json",),
    "scorecard": ("reports/supply-chain-posture.json",),
    "dependency": ("reports/dependencies.json",),
    "scanner": ("reports/scanner-results/scanner-index.json",),
    "gapfill": ("reports/gapfill-targets.json",),
}


class TargetQueueError(ValueError):
    pass


@dataclass(frozen=True)
class TargetBudgets:
    total: int
    by_source: dict[str, int]


def default_budgets() -> TargetBudgets:
    return TargetBudgets(
        total=DEFAULT_TOTAL_BUDGET,
        by_source={source: DEFAULT_SOURCE_BUDGET for source in BUDGETED_TARGET_SOURCES},
    )


def validate_budgets(budgets: TargetBudgets) -> None:
    if isinstance(budgets.total, bool) or not isinstance(budgets.total, int) or not 1 <= budgets.total <= MAX_BUDGET:
        raise TargetQueueError(f"target budget must be between 1 and {MAX_BUDGET}")
    if set(budgets.by_source) != set(BUDGETED_TARGET_SOURCES):
        raise TargetQueueError("per-source budgets must use the closed target source set")
    for source, value in budgets.by_source.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BUDGET:
            raise TargetQueueError(f"{source} budget must be between 1 and {MAX_BUDGET}")


def target_source(target: dict[str, Any]) -> str:
    source = target.get("queue_source")
    # IDs are attacker/model-controlled and therefore cannot establish queue
    # provenance. Legacy targets without the producer-written marker are
    # conservatively treated as model generated on their next rebalance.
    return str(source) if source in TARGET_SOURCES else "model_generated"


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"\s+", " ", value[:MAX_NORMALIZATION_INPUT].strip().lower())
    return value[:MAX_TEXT]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_text(item) for item in value[:64] if _text(item)})


def _taxonomy_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({_text(item.get("id")) for item in value[:32] if isinstance(item, dict) and _text(item.get("id"))})


def _validate_target_for_queue(target: dict[str, Any]) -> None:
    target_id = target.get("id")
    if not isinstance(target_id, str) or len(target_id) > 80 or not TARGET_ID_RE.fullmatch(target_id):
        raise TargetQueueError("target queue id is invalid")
    risk = target.get("risk")
    if risk not in RISK_ORDER:
        raise TargetQueueError("target queue risk is invalid")
    priority = target.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
        raise TargetQueueError("target queue priority is invalid")
    if target.get("status") not in TARGET_STATUSES:
        raise TargetQueueError("target queue status is invalid")
    if "queue_source" in target and target.get("queue_source") not in TARGET_SOURCES:
        raise TargetQueueError("target queue source is invalid")
    for field in ("category", "title", "scope"):
        value = target.get(field)
        if not isinstance(value, str):
            raise TargetQueueError(f"target queue {field} is invalid")
    if target.get("recommended_mode") not in {"exec", "goal"}:
        raise TargetQueueError("target queue recommended_mode is invalid")
    required_lists = {"entry_points", "trust_boundaries", "sinks", "review_questions"}
    for field in LIST_FIELDS:
        value = target.get(field)
        if (field in required_lists and value is None) or (value is not None and (
            not isinstance(value, list)
            or len(value) > 64
            or any(not isinstance(item, str) or len(item) > MAX_NORMALIZATION_INPUT for item in value)
        )):
            raise TargetQueueError(f"target queue {field} is invalid or exceeds the bounded limit")
    for field in ("attack_class", "category", "attacker_model"):
        value = target.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > MAX_NORMALIZATION_INPUT):
            raise TargetQueueError(f"target queue {field} is invalid or exceeds the bounded limit")
    taxonomies = target.get("taxonomies")
    if taxonomies is not None and (
        not isinstance(taxonomies, list)
        or len(taxonomies) > 32
        or any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("name"), str)
            or len(item["id"]) > MAX_TEXT
            or len(item["name"]) > MAX_TEXT
            for item in taxonomies
        )
    ):
        raise TargetQueueError("target queue taxonomies are invalid or exceed the bounded limit")


def target_fingerprint(target: dict[str, Any]) -> str:
    structured = {
        "attack_class": _text(target.get("attack_class") or target.get("category")),
        "attacker_model": _text(target.get("attacker_model")),
        # Scope is used only alongside structured security fields. It is not a
        # title/notes prose fallback and prevents unrelated components with a
        # similar generic attack shape from being merged.
        "scope_identity": _text(target.get("scope")),
        "taxonomies": _taxonomy_ids(target.get("taxonomies")),
        "trust_boundaries": _strings(target.get("trust_boundaries")),
        "entry_points": _strings(target.get("entry_points")),
        "sinks": _strings(target.get("sinks")),
        "security_invariants": _strings(target.get("security_invariants")),
        "candidate_files": _strings(target.get("candidate_files")),
    }
    structured_values = [
        *structured["taxonomies"],
        *structured["trust_boundaries"],
        *structured["entry_points"],
        *structured["sinks"],
        *structured["security_invariants"],
        *structured["candidate_files"],
    ]
    # A category by itself is too weak to establish semantic overlap. Keep such
    # targets distinct without falling back to opaque title/scope/notes prose.
    if not structured_values or not structured["scope_identity"]:
        structured["insufficient_signal_target_id"] = _text(target.get("id"))
    encoded = json.dumps(structured, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lineage(target: dict[str, Any]) -> list[dict[str, Any]]:
    existing = target.get("source_lineage")
    if isinstance(existing, list):
        if not 1 <= len(existing) <= MAX_LINEAGE or any(not isinstance(item, dict) for item in existing):
            raise TargetQueueError("target source lineage is invalid")
        items = copy.deepcopy(existing)
    else:
        source = target_source(target)
        items = [{"source": source, "target_id": str(target.get("id") or ""), "evidence_refs": list(EVIDENCE_REFS[source])}]
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        source = item.get("source")
        target_id = item.get("target_id")
        if (
            not isinstance(source, str)
            or source not in TARGET_SOURCES
            or not isinstance(target_id, str)
            or not target_id
            or len(target_id) > 80
            or not TARGET_ID_RE.fullmatch(target_id)
        ):
            raise TargetQueueError("target source lineage is invalid")
        refs = item.get("evidence_refs")
        if (
            not isinstance(refs, list)
            or len(refs) > 8
            or any(not isinstance(ref, str) for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise TargetQueueError("target source lineage evidence references are invalid")
        safe_refs = sorted({ref[:MAX_TEXT] for ref in refs if ref and not ref.startswith("/") and ".." not in ref.split("/")})
        if safe_refs != list(EVIDENCE_REFS[source]):
            raise TargetQueueError("target source lineage evidence references are invalid")
        key = (source, target_id)
        if key in unique:
            raise TargetQueueError("target source lineage contains a duplicate entry")
        unique[key] = {"source": source, "target_id": target_id, "evidence_refs": safe_refs}
    if len(unique) > MAX_LINEAGE:
        raise TargetQueueError("target source lineage exceeds the bounded limit")
    return [unique[key] for key in sorted(unique, key=lambda item: (SOURCE_ORDER[item[0]], item[1]))]


def _union_strings(groups: Iterable[Any]) -> list[str]:
    values = {str(item)[:MAX_TEXT] for group in groups if isinstance(group, list) for item in group if isinstance(item, str) and item}
    return sorted(values)[:64]


def _union_taxonomies(groups: Iterable[Any]) -> list[dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if isinstance(item, dict) and item.get("name") and item.get("id"):
                key = (str(item["name"])[:80], str(item["id"])[:80])
                items[key] = copy.deepcopy(item)
    return [items[key] for key in sorted(items)[:32]]


def _canonical_key(target: dict[str, Any], index: int) -> tuple[Any, ...]:
    return (
        CANONICAL_SOURCE_ORDER[target_source(target)],
        RISK_ORDER.get(str(target.get("risk") or ""), 9),
        -int(target.get("priority") or 0),
        str(target.get("id") or ""),
        index,
    )


def _merge(group: list[tuple[int, dict[str, Any]]], fingerprint: str) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
    ordered = sorted(group, key=lambda pair: _canonical_key(pair[1], pair[0]))
    canonical = copy.deepcopy(ordered[0][1])
    canonical["queue_source"] = target_source(canonical)
    canonical["risk"] = min((str(item.get("risk") or "informational") for _, item in ordered), key=lambda risk: RISK_ORDER.get(risk, 9))
    canonical["priority"] = max(int(item.get("priority") or 0) for _, item in ordered)
    for field in LIST_FIELDS:
        canonical[field] = _union_strings(item.get(field) for _, item in ordered)
    taxonomies = _union_taxonomies(item.get("taxonomies") for _, item in ordered)
    if taxonomies:
        canonical["taxonomies"] = taxonomies
    canonical["queue_fingerprint"] = fingerprint
    canonical["source_lineage"] = _lineage(canonical)
    canonical_key = (target_source(canonical), str(canonical.get("id") or ""))
    if canonical_key not in {(item["source"], item["target_id"]) for item in canonical["source_lineage"]}:
        raise TargetQueueError("canonical target is missing from source lineage")
    for _, item in ordered[1:]:
        canonical["source_lineage"] = _lineage({"source_lineage": [*canonical["source_lineage"], *_lineage(item)]})
    return min(index for index, _ in group), canonical, [item for _, item in ordered]


def apply_target_queue_policy(
    targets: list[dict[str, Any]],
    *,
    budgets: TargetBudgets | None = None,
    policy: str = "risk-weighted",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    budgets = budgets or default_budgets()
    validate_budgets(budgets)
    if policy not in POLICIES:
        raise TargetQueueError("budget policy must be strict or risk-weighted")
    if len(targets) > MAX_TARGETS or any(not isinstance(target, dict) for target in targets):
        raise TargetQueueError("target queue is invalid or exceeds the bounded limit")
    for target in targets:
        _validate_target_for_queue(target)
    original = copy.deepcopy(targets)
    for target in original:
        target["queue_source"] = target_source(target)
    input_ids = [str(target.get("id") or "") for target in original]
    if any(not target_id for target_id in input_ids) or len(input_ids) != len(set(input_ids)):
        raise TargetQueueError("target queue ids must be non-empty and unique")
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    retained_groups: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    for index, target in enumerate(original):
        fingerprint = target_fingerprint(target)
        if str(target.get("status") or "") == "queued" and target_source(target) in BUDGETED_TARGET_SOURCES:
            grouped.setdefault(fingerprint, []).append((index, target))
        else:
            # A target already acted on by an operator is historical state, not
            # a seed competing for the next active budget. Keep its ID and
            # status intact, and never merge a new queued seed into it.
            retained_groups.append(_merge([(index, target)], fingerprint))
    queued_groups = [_merge(group, fingerprint) for fingerprint, group in sorted(grouped.items())]
    if policy == "strict":
        queued_groups.sort(key=lambda group: group[0])
    else:
        queued_groups.sort(key=lambda group: _canonical_key(group[1], group[0]))
    retained_groups.sort(key=lambda group: group[0])
    selected_active: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    primary_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []
    by_source = {
        source: {"generated": 0, "active": 0, "retained": 0, "merged": 0, "deferred": 0}
        for source in TARGET_SOURCES
    }
    generated_total = 0

    def record_group(
        canonical: dict[str, Any],
        *,
        action: str,
        reason: str,
    ) -> None:
        nonlocal generated_total
        lineage = _lineage(canonical)
        generated_total += len(lineage)
        for item in lineage:
            by_source[item["source"]]["generated"] += 1
        source = target_source(canonical)
        by_source[source][action] += 1
        canonical_id = str(canonical.get("id") or "")
        decisions.append({"target_id": canonical_id, "canonical_target_id": canonical_id, "source": source, "fingerprint": canonical["queue_fingerprint"], "action": action, "reason": reason})
        for contributor in lineage:
            contributor_id = str(contributor.get("target_id") or "")
            if contributor_id == canonical_id:
                continue
            contributor_source = str(contributor.get("source") or "")
            by_source[contributor_source]["merged"] += 1
            decisions.append({"target_id": contributor_id, "canonical_target_id": canonical_id, "source": contributor_source, "fingerprint": canonical["queue_fingerprint"], "action": "merged", "reason": "structured_fingerprint_match"})

    for _, canonical, _contributors in queued_groups:
        source = target_source(canonical)
        within_source = primary_counts[source] < budgets.by_source[source]
        within_total = len(selected_active) < budgets.total
        selected = within_source and within_total
        if selected:
            selected_active.append(canonical)
            primary_counts[source] += 1
            action, reason = "active", "selected"
        else:
            deferred.append(canonical)
            high = str(canonical.get("risk") or "") in {"critical", "high"}
            reason = ("source" if not within_source else "total") + "_budget_exhausted" + ("_high_risk" if high else "")
            action = "deferred"
        record_group(canonical, action=action, reason=reason)
    retained = [canonical for _, canonical, _contributors in retained_groups]
    for canonical in retained:
        reason = "workflow_target_retained" if target_source(canonical) == "gapfill" else "status_retained"
        record_group(canonical, action="retained", reason=reason)
    if generated_total > MAX_TARGETS:
        raise TargetQueueError("target source lineage exceeds the bounded queue limit")
    decisions.sort(key=lambda item: (item["target_id"], item["action"], item["canonical_target_id"]))
    decision_ids = [item["target_id"] for item in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise TargetQueueError("target source lineage ids must be globally unique")
    summary = {
        "schema_version": "1",
        "policy": policy,
        "budgets": {"total": budgets.total, "by_source": dict(sorted(budgets.by_source.items()))},
        "generated": generated_total,
        "active": len(selected_active),
        "retained_outside_budget": len(retained),
        "merged": generated_total - len(queued_groups) - len(retained_groups),
        "deferred_by_budget": len(deferred),
        "high_risk_deferred": sum(1 for target in deferred if str(target.get("risk") or "") in {"critical", "high"}),
        "by_source": by_source,
        "selection_input_ids": sorted(decision_ids),
        "decisions": decisions,
    }
    return [*selected_active, *retained], deferred, summary


def preserve_target_queue_membership(
    active: list[dict[str, Any]],
    deferred: list[dict[str, Any]],
    *,
    summary: dict[str, Any],
    allow_fingerprint_refresh: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Refresh queue metadata without selecting or promoting another seed.

    Status updates and post-selection appenders must not silently perform the
    operator-visible action provided by ``gra-targets --rebalance``. Existing
    active/deferred membership and decisions are preserved. A newly appended
    active-array target is retained outside the selected budget until an
    explicit rebalance.
    """

    if not isinstance(summary, dict):
        raise TargetQueueError("stored queue summary must be an object")
    budgets_data = summary.get("budgets")
    if not isinstance(budgets_data, dict) or set(budgets_data) != {"total", "by_source"}:
        raise TargetQueueError("stored target queue budgets are invalid")
    budgets = TargetBudgets(total=budgets_data.get("total"), by_source=budgets_data.get("by_source"))
    validate_budgets(budgets)
    policy = summary.get("policy")
    if policy not in POLICIES:
        raise TargetQueueError("stored target queue policy is invalid")
    if len(active) + len(deferred) > MAX_TARGETS or any(
        not isinstance(target, dict) for target in [*active, *deferred]
    ):
        raise TargetQueueError("target queue is invalid or exceeds the bounded limit")

    previous_decisions = summary.get("decisions")
    if not isinstance(previous_decisions, list):
        raise TargetQueueError("stored target queue decisions are invalid")
    selection_input_ids = summary.get("selection_input_ids")
    if (
        not isinstance(selection_input_ids, list)
        or len(selection_input_ids) > MAX_TARGETS
        or len(selection_input_ids) != len(set(selection_input_ids))
        or any(not isinstance(target_id, str) or not TARGET_ID_RE.fullmatch(target_id) for target_id in selection_input_ids)
    ):
        raise TargetQueueError("stored target queue selection input ids are invalid")
    previous_by_id = {
        str(item.get("target_id") or ""): item
        for item in previous_decisions
        if isinstance(item, dict) and item.get("target_id")
    }
    if len(previous_by_id) != len(previous_decisions):
        raise TargetQueueError("stored target queue decisions are invalid")

    refreshed_active: list[dict[str, Any]] = []
    refreshed_deferred: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    by_source = {
        source: {"generated": 0, "active": 0, "retained": 0, "merged": 0, "deferred": 0}
        for source in TARGET_SOURCES
    }

    def refresh_one(target: dict[str, Any], *, membership: str) -> dict[str, Any]:
        _validate_target_for_queue(target)
        value = copy.deepcopy(target)
        value["queue_source"] = target_source(value)
        fingerprint = target_fingerprint(value)
        old_fingerprint = value.get("queue_fingerprint")
        if old_fingerprint is not None and old_fingerprint != fingerprint and not allow_fingerprint_refresh:
            raise TargetQueueError("target queue fingerprint changed; run an explicit rebalance")
        value["queue_fingerprint"] = fingerprint
        lineage = _lineage(value)
        value["source_lineage"] = lineage
        canonical_id = str(value.get("id") or "")
        canonical_source = target_source(value)
        old = previous_by_id.get(canonical_id)
        old_action = old.get("action") if isinstance(old, dict) else None
        old_reason = old.get("reason") if isinstance(old, dict) else None
        if membership == "deferred":
            if old_action != "deferred":
                raise TargetQueueError("a target cannot enter the deferred queue without an explicit rebalance")
            action, reason = "deferred", str(old_reason or "budget_exhausted")
        elif old_action in {"active", "retained"}:
            action, reason = str(old_action), str(old_reason or ("selected" if old_action == "active" else "status_retained"))
        elif old_action == "deferred":
            raise TargetQueueError("a deferred target cannot enter the active queue without an explicit rebalance")
        else:
            action = "retained"
            reason = "workflow_target_retained" if canonical_source == "gapfill" else "added_after_selection"

        for contributor in lineage:
            source = contributor["source"]
            by_source[source]["generated"] += 1
            contributor_id = contributor["target_id"]
            if contributor_id == canonical_id:
                contributor_action, contributor_reason = action, reason
                by_source[source][action] += 1
            else:
                contributor_action, contributor_reason = "merged", "structured_fingerprint_match"
                by_source[source]["merged"] += 1
            decisions.append(
                {
                    "target_id": contributor_id,
                    "canonical_target_id": canonical_id,
                    "source": source,
                    "fingerprint": fingerprint,
                    "action": contributor_action,
                    "reason": contributor_reason,
                }
            )
        return value

    for target in active:
        refreshed_active.append(refresh_one(target, membership="active"))
    for target in deferred:
        refreshed_deferred.append(refresh_one(target, membership="deferred"))
    decisions.sort(key=lambda item: (item["target_id"], item["action"], item["canonical_target_id"]))
    decision_ids = [item["target_id"] for item in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise TargetQueueError("target source lineage ids must be globally unique")
    actions = Counter(item["action"] for item in decisions)
    generated = len(decisions)
    refreshed_summary = {
        "schema_version": "1",
        "policy": policy,
        "budgets": {"total": budgets.total, "by_source": dict(sorted(budgets.by_source.items()))},
        "generated": generated,
        "active": actions["active"],
        "retained_outside_budget": actions["retained"],
        "merged": actions["merged"],
        "deferred_by_budget": actions["deferred"],
        "high_risk_deferred": sum(
            1 for target in refreshed_deferred if str(target.get("risk") or "") in {"critical", "high"}
        ),
        "by_source": by_source,
        "selection_input_ids": list(selection_input_ids),
        "decisions": decisions,
    }
    if refreshed_summary["active"] + refreshed_summary["retained_outside_budget"] != len(refreshed_active):
        raise TargetQueueError("target queue active membership is inconsistent")
    return refreshed_active, refreshed_deferred, refreshed_summary


def validate_target_queue_artifact(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["targets: target queue must be an object"]
    has_summary = "queue_summary" in data
    has_deferred = "deferred_targets" in data
    if not has_summary and not has_deferred:
        return errors
    if not has_summary or not has_deferred:
        return ["targets: queue_summary and deferred_targets must appear together"]
    active = data.get("targets")
    deferred = data.get("deferred_targets")
    summary = data.get("queue_summary")
    if not isinstance(active, list) or not isinstance(deferred, list) or not isinstance(summary, dict):
        return ["targets: queue fields have invalid types"]
    if len(active) + len(deferred) > MAX_TARGETS:
        errors.append("targets: active and deferred targets exceed the bounded limit")
    allowed_summary = {
        "schema_version", "policy", "budgets", "generated", "active", "merged",
        "retained_outside_budget", "deferred_by_budget", "high_risk_deferred", "by_source",
        "selection_input_ids", "decisions",
    }
    if set(summary) != allowed_summary:
        errors.append("targets.queue_summary: fields must match the closed contract")
    if summary.get("schema_version") != "1" or summary.get("policy") not in POLICIES:
        errors.append("targets.queue_summary: schema_version or policy is invalid")
    budgets_data = summary.get("budgets")
    resolved_budgets: TargetBudgets | None = None
    try:
        if not isinstance(budgets_data, dict) or set(budgets_data) != {"total", "by_source"}:
            raise TargetQueueError("budget object is invalid")
        resolved_budgets = TargetBudgets(total=budgets_data.get("total"), by_source=budgets_data.get("by_source"))
        validate_budgets(resolved_budgets)
    except (TargetQueueError, TypeError):
        errors.append("targets.queue_summary.budgets: budget contract is invalid")
        budgets_data = {"total": 0, "by_source": {}}
    all_targets = [item for item in [*active, *deferred] if isinstance(item, dict)]
    if len(all_targets) != len(active) + len(deferred):
        errors.append("targets: active and deferred entries must be objects")
    target_ids = [str(item.get("id") or "") for item in all_targets]
    if len(target_ids) != len(set(target_ids)):
        errors.append("targets: active and deferred target ids must be unique")
    allowed_lineage = {"source", "target_id", "evidence_refs"}
    safe_refs = {ref for refs in EVIDENCE_REFS.values() for ref in refs}
    for index, target in enumerate(all_targets):
        path = f"targets.queue_target[{index}]"
        try:
            _validate_target_for_queue(target)
        except TargetQueueError as exc:
            errors.append(f"{path}: {exc}")
        if target.get("queue_source") not in TARGET_SOURCES:
            errors.append(f"{path}.queue_source: producer source marker is required for a queued artifact")
        fingerprint = target.get("queue_fingerprint")
        if fingerprint != target_fingerprint(target):
            errors.append(f"{path}.queue_fingerprint: value does not match normalized target fields")
        lineage = target.get("source_lineage")
        if not isinstance(lineage, list) or not 1 <= len(lineage) <= MAX_LINEAGE:
            errors.append(f"{path}.source_lineage: lineage must be a bounded non-empty list")
            continue
        seen_lineage: set[tuple[str, str]] = set()
        for line_index, item in enumerate(lineage):
            line_path = f"{path}.source_lineage[{line_index}]"
            if not isinstance(item, dict) or set(item) != allowed_lineage:
                errors.append(f"{line_path}: fields must match the closed lineage contract")
                continue
            source = item.get("source")
            contributor_id = item.get("target_id")
            refs = item.get("evidence_refs")
            if source not in TARGET_SOURCES or not isinstance(contributor_id, str) or not contributor_id:
                errors.append(f"{line_path}: source or target_id is invalid")
            key = (str(source), str(contributor_id))
            if key in seen_lineage:
                errors.append(f"{line_path}: duplicate source lineage entry")
            seen_lineage.add(key)
            if (
                not isinstance(refs, list)
                or len(refs) > 8
                or any(not isinstance(ref, str) for ref in refs)
                or len(refs) != len(set(refs))
                or any(ref not in safe_refs for ref in refs)
                or (source in TARGET_SOURCES and refs != list(EVIDENCE_REFS[source]))
            ):
                errors.append(f"{line_path}.evidence_refs: references must use the closed safe artifact set")
        canonical_key = (target.get("queue_source"), target.get("id"))
        if canonical_key not in seen_lineage:
            errors.append(f"{path}.source_lineage: canonical producer source and target id are missing")
    decisions = summary.get("decisions")
    if not isinstance(decisions, list) or len(decisions) > MAX_TARGETS:
        errors.append("targets.queue_summary.decisions: decisions must be a bounded list")
        decisions = []
    allowed_decision = {"target_id", "canonical_target_id", "source", "fingerprint", "action", "reason"}
    action_counts: Counter[str] = Counter()
    source_actions = {source: Counter() for source in TARGET_SOURCES}
    decision_ids: set[str] = set()
    selection_input_ids = summary.get("selection_input_ids")
    if (
        not isinstance(selection_input_ids, list)
        or len(selection_input_ids) > MAX_TARGETS
        or len(selection_input_ids) != len(set(selection_input_ids))
        or any(not isinstance(target_id, str) or not TARGET_ID_RE.fullmatch(target_id) for target_id in selection_input_ids)
    ):
        errors.append("targets.queue_summary.selection_input_ids: value must be a bounded unique target ID list")
        selection_ids: set[str] = set()
    else:
        selection_ids = set(selection_input_ids)
    active_ids = {str(item.get("id") or "") for item in active if isinstance(item, dict)}
    deferred_ids = {str(item.get("id") or "") for item in deferred if isinstance(item, dict)}
    fingerprints = {str(item.get("id") or ""): str(item.get("queue_fingerprint") or "") for item in all_targets}
    for index, decision in enumerate(decisions):
        path = f"targets.queue_summary.decisions[{index}]"
        if not isinstance(decision, dict) or set(decision) != allowed_decision:
            errors.append(f"{path}: fields must match the closed decision contract")
            continue
        target_id = str(decision.get("target_id") or "")
        canonical_id = str(decision.get("canonical_target_id") or "")
        action = str(decision.get("action") or "")
        source = str(decision.get("source") or "")
        if target_id in decision_ids:
            errors.append(f"{path}.target_id: duplicate decision target id")
        decision_ids.add(target_id)
        if source not in TARGET_SOURCES or action not in {"active", "retained", "merged", "deferred"}:
            errors.append(f"{path}: source or action is invalid")
            continue
        reason = decision.get("reason")
        allowed_reasons = {
            "active": {"selected"},
            "retained": {"status_retained", "workflow_target_retained", "added_after_selection"},
            "merged": {"structured_fingerprint_match"},
            "deferred": {
                "source_budget_exhausted",
                "source_budget_exhausted_high_risk",
                "total_budget_exhausted",
                "total_budget_exhausted_high_risk",
            },
        }
        if reason not in allowed_reasons[action]:
            errors.append(f"{path}.reason: reason is invalid for action {action}")
        if action in {"active", "deferred", "merged"} or reason == "status_retained":
            if target_id not in selection_ids:
                errors.append(f"{path}.target_id: selected-wave decision is missing from selection_input_ids")
        elif reason == "added_after_selection" and target_id in selection_ids:
            errors.append(f"{path}.target_id: post-selection target must not be in selection_input_ids")
        action_counts[action] += 1
        source_actions[source][action] += 1
        expected_ids = active_ids if action in {"active", "retained"} else deferred_ids if action == "deferred" else active_ids | deferred_ids
        if canonical_id not in expected_ids:
            errors.append(f"{path}.canonical_target_id: canonical target is not retained")
        if decision.get("fingerprint") != fingerprints.get(canonical_id):
            errors.append(f"{path}.fingerprint: value does not match canonical target")
    if not selection_ids.issubset(decision_ids):
        errors.append("targets.queue_summary.selection_input_ids: ids must reference queue decisions")
    numeric = {name: summary.get(name) for name in ["generated", "active", "retained_outside_budget", "merged", "deferred_by_budget", "high_risk_deferred"]}
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in numeric.values()):
        errors.append("targets.queue_summary: counts must be non-negative integers")
    else:
        if numeric["active"] + numeric["retained_outside_budget"] != len(active) or numeric["deferred_by_budget"] != len(deferred):
            errors.append("targets.queue_summary: active/retained/deferred counts do not match target arrays")
        if numeric["generated"] != numeric["active"] + numeric["retained_outside_budget"] + numeric["deferred_by_budget"] + numeric["merged"]:
            errors.append("targets.queue_summary: generated count invariant is invalid")
        expected_actions = Counter({
            "active": numeric["active"],
            "retained": numeric["retained_outside_budget"],
            "deferred": len(deferred),
            "merged": numeric["merged"],
        })
        if numeric["generated"] != len(decisions) or action_counts != expected_actions:
            errors.append("targets.queue_summary: decision counts do not match summary")
        high_deferred = sum(1 for item in deferred if isinstance(item, dict) and item.get("risk") in {"critical", "high"})
        if numeric["high_risk_deferred"] != high_deferred:
            errors.append("targets.queue_summary.high_risk_deferred: count does not match deferred targets")
        if numeric["active"] > int(budgets_data.get("total") or 0):
            errors.append("targets.queue_summary.active: active target count exceeds total budget")
    by_source = summary.get("by_source")
    if not isinstance(by_source, dict) or set(by_source) != set(TARGET_SOURCES):
        errors.append("targets.queue_summary.by_source: source set is invalid")
    else:
        for source in TARGET_SOURCES:
            counts = by_source.get(source)
            if not isinstance(counts, dict) or set(counts) != {"generated", "active", "retained", "merged", "deferred"}:
                errors.append(f"targets.queue_summary.by_source.{source}: fields are invalid")
                continue
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
                errors.append(f"targets.queue_summary.by_source.{source}: counts must be non-negative integers")
                continue
            expected = {
                "generated": sum(1 for decision in decisions if isinstance(decision, dict) and decision.get("source") == source),
                "active": source_actions[source]["active"],
                "retained": source_actions[source]["retained"],
                "merged": source_actions[source]["merged"],
                "deferred": source_actions[source]["deferred"],
            }
            if counts != expected:
                errors.append(f"targets.queue_summary.by_source.{source}: counts do not match decisions")
            if counts.get("active", 0) > int((budgets_data.get("by_source") or {}).get(source, 0)):
                if source in BUDGETED_TARGET_SOURCES:
                    errors.append(f"targets.queue_summary.by_source.{source}.active: count exceeds source budget")
    if resolved_budgets is not None and len(all_targets) == len(active) + len(deferred):
        try:
            preserved_active, preserved_deferred, preserved_summary = preserve_target_queue_membership(
                active,
                deferred,
                summary=summary,
            )
        except TargetQueueError as exc:
            errors.append(f"targets.queue_summary: membership replay failed: {exc}")
        else:
            if active != preserved_active or deferred != preserved_deferred or summary != preserved_summary:
                errors.append("targets.queue_summary: artifact does not match preserved queue membership")

        canonical_decisions = {
            str(item.get("canonical_target_id") or ""): item
            for item in decisions
            if isinstance(item, dict)
            and item.get("target_id") == item.get("canonical_target_id")
        }
        replay_targets = copy.deepcopy([*active, *deferred])
        for target in replay_targets:
            decision = canonical_decisions.get(str(target.get("id") or ""), {})
            action = decision.get("action")
            reason = decision.get("reason")
            if action in {"active", "deferred"}:
                target["status"] = "queued"
            elif action == "retained" and reason == "added_after_selection":
                # Exclude a post-selection append from the historical wave;
                # an explicit rebalance is required before it can compete.
                target["status"] = "in_progress"
        try:
            _expected_active, _expected_deferred, expected_summary = apply_target_queue_policy(
                replay_targets,
                budgets=resolved_budgets,
                policy=str(summary.get("policy") or ""),
            )
        except TargetQueueError as exc:
            errors.append(f"targets.queue_summary: deterministic selection replay failed: {exc}")
        else:
            actual_selected = {
                str(item.get("canonical_target_id") or "")
                for item in decisions
                if isinstance(item, dict)
                and item.get("target_id") == item.get("canonical_target_id")
                and item.get("action") == "active"
            }
            actual_deferred = {
                str(item.get("canonical_target_id") or "")
                for item in decisions
                if isinstance(item, dict)
                and item.get("target_id") == item.get("canonical_target_id")
                and item.get("action") == "deferred"
            }
            expected_selected = {
                str(item.get("canonical_target_id") or "")
                for item in expected_summary["decisions"]
                if item.get("target_id") == item.get("canonical_target_id") and item.get("action") == "active"
            }
            expected_deferred_ids = {
                str(item.get("canonical_target_id") or "")
                for item in expected_summary["decisions"]
                if item.get("target_id") == item.get("canonical_target_id") and item.get("action") == "deferred"
            }
            if actual_selected != expected_selected or actual_deferred != expected_deferred_ids:
                errors.append("targets.queue_summary: selected/deferred membership does not match deterministic policy replay")
    return errors


def refresh_target_queue_after_semantic_normalization(data: dict[str, Any]) -> dict[str, Any]:
    """Refresh a valid queue after a trusted deterministic semantic edit.

    Controlled taxonomy normalization can change a fingerprint even though the
    target ID and operator-visible status did not change. Preserve the existing
    wave when normalized fingerprints do not change grouping. If two canonical
    targets converge, deterministically reapply the stored policy so lineage,
    decisions, and membership remain coherent.

    Callers must validate the artifact before applying the trusted edit. This
    helper validates the final artifact and does not repair a poisoned queue.
    """

    if not isinstance(data, dict):
        raise TargetQueueError("targets artifact must be an object")
    has_summary = "queue_summary" in data
    has_deferred = "deferred_targets" in data
    if not has_summary and not has_deferred:
        return copy.deepcopy(data)
    if not has_summary or not has_deferred:
        raise TargetQueueError("queue_summary and deferred_targets must appear together")
    active = data.get("targets")
    deferred = data.get("deferred_targets")
    summary = data.get("queue_summary")
    if not isinstance(active, list) or not isinstance(deferred, list) or not isinstance(summary, dict):
        raise TargetQueueError("target queue fields have invalid types")

    refreshed_active, refreshed_deferred, refreshed_summary = preserve_target_queue_membership(
        active,
        deferred,
        summary=summary,
        allow_fingerprint_refresh=True,
    )
    refreshed = copy.deepcopy(data)
    refreshed.update(
        {
            "targets": refreshed_active,
            "deferred_targets": refreshed_deferred,
            "queue_summary": refreshed_summary,
        }
    )
    if not validate_target_queue_artifact(refreshed):
        return refreshed

    # A taxonomy mapping can make previously distinct queue groups equivalent.
    # Reconstruct the historical selected wave before applying the stored policy
    # so status-only changes do not become implicit promotions or demotions.
    previous_decisions = summary.get("decisions")
    if not isinstance(previous_decisions, list):
        raise TargetQueueError("stored target queue decisions are invalid")
    canonical_decisions = {
        str(item.get("canonical_target_id") or ""): item
        for item in previous_decisions
        if isinstance(item, dict) and item.get("target_id") == item.get("canonical_target_id")
    }
    replay_targets = copy.deepcopy([*active, *deferred])
    for target in replay_targets:
        decision = canonical_decisions.get(str(target.get("id") or ""), {})
        action = decision.get("action")
        reason = decision.get("reason")
        if action in {"active", "deferred"}:
            target["status"] = "queued"
        elif action == "retained" and reason == "added_after_selection":
            target["status"] = "in_progress"

    budgets_data = summary.get("budgets")
    if not isinstance(budgets_data, dict) or set(budgets_data) != {"total", "by_source"}:
        raise TargetQueueError("stored target queue budgets are invalid")
    budgets = TargetBudgets(total=budgets_data.get("total"), by_source=budgets_data.get("by_source"))
    rebalanced_active, rebalanced_deferred, rebalanced_summary = apply_target_queue_policy(
        replay_targets,
        budgets=budgets,
        policy=str(summary.get("policy") or ""),
    )

    # The replay statuses above reconstruct historical seed selection only.
    # Restore operator-visible progress on the resulting semantic group so a
    # taxonomy-only edit cannot turn reviewed or in-progress work back into a
    # queued target. When several progressed groups converge, choose the most
    # conservative deterministic status.
    operator_status_by_id = {
        str(target.get("id") or ""): str(target.get("status") or "")
        for target in [*active, *deferred]
        if target.get("status") in TARGET_STATUSES - {"queued"}
    }
    status_precedence = {
        "needs_human_review": 0,
        "in_progress": 1,
        "reviewed": 2,
        "skipped": 3,
    }
    for target in [*rebalanced_active, *rebalanced_deferred]:
        progressed = {
            operator_status_by_id.get(str(item.get("target_id") or ""), "")
            for item in target.get("source_lineage") or []
            if isinstance(item, dict)
        } - {""}
        if progressed:
            target["status"] = min(progressed, key=lambda status: (status_precedence[status], status))

    rebalanced = copy.deepcopy(data)
    rebalanced.update(
        {
            "targets": rebalanced_active,
            "deferred_targets": rebalanced_deferred,
            "queue_summary": rebalanced_summary,
        }
    )
    errors = validate_target_queue_artifact(rebalanced)
    if errors:
        raise TargetQueueError(errors[0])
    return rebalanced

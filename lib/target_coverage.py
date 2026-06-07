from __future__ import annotations

from pathlib import Path
from typing import Any

from gralib import load_context, load_targets, utc_now, write_json, write_targets
GAPFILL_DEPTHS = {"none", "shallow"}
GAPFILL_RISKS = {"critical", "high"}
TARGET_RISKS = {"critical", "high", "medium", "low", "informational"}
TARGET_MODES = {"exec", "goal"}
CHAIN_RELEVANCE = {"none", "possible-link", "candidate-chain-step"}
GAPFILL_TARGET_STATUSES = {"queued", "in_progress", "reviewed", "skipped", "needs_human_review"}


def coverage_for(target: dict[str, Any]) -> dict[str, Any]:
    coverage = target.get("coverage")
    return coverage if isinstance(coverage, dict) else {}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def reports_dir(run_dir: Path) -> Path:
    ctx = load_context(run_dir)
    return run_dir / ctx.get("reports_dir", "reports")


def review_depth(target: dict[str, Any]) -> str:
    return str(coverage_for(target).get("review_depth") or "unknown")


def gapfill_reason(target: dict[str, Any]) -> str:
    coverage = coverage_for(target)
    reason = str(coverage.get("gapfill_reason") or "").strip()
    if reason:
        return reason
    unresolved = string_list(coverage.get("unresolved_questions"))
    if unresolved:
        return unresolved[0]
    depth = review_depth(target)
    if depth in GAPFILL_DEPTHS:
        return f"Review depth is {depth}"
    return "Coverage gap requires bounded follow-up review"


def is_gapfill_candidate(target: dict[str, Any]) -> bool:
    coverage = coverage_for(target)
    if coverage.get("gapfill_recommended") is True:
        return True
    risk = str(target.get("risk") or "").lower()
    depth = str(coverage.get("review_depth") or "").lower()
    if risk in GAPFILL_RISKS and depth in GAPFILL_DEPTHS:
        return True
    if risk in GAPFILL_RISKS and string_list(coverage.get("unresolved_questions")):
        return True
    return False


def gapfill_candidates(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [target for target in targets if is_gapfill_candidate(target)]
    return sorted(
        candidates,
        key=lambda target: (
            -bounded_priority(target),
            str(target.get("id") or ""),
        ),
    )


def next_gapfill_id(existing_ids: set[str], start: int = 1) -> str:
    index = start
    while True:
        candidate = f"TGT-GAPFILL-{index:03d}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def existing_gapfill_target(targets: list[dict[str, Any]], source_id: str) -> dict[str, Any] | None:
    for target in targets:
        target_id = str(target.get("id") or "")
        if str(target.get("source_target_id") or "") == source_id and target_id.startswith("TGT-GAPFILL-"):
            return target
    return None


def is_gapfill_target(target: dict[str, Any]) -> bool:
    return str(target.get("id") or "").startswith("TGT-GAPFILL-") or target.get("category") == "gapfill"


def bounded_max_files(target: dict[str, Any]) -> int:
    value = target.get("max_files")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(1, min(8, value))
    return 6


def bounded_priority(target: dict[str, Any]) -> int:
    value = target.get("priority")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(100, value))
    return 70


def choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "")
    return text if text in allowed else default


def build_gapfill_target(source: dict[str, Any], target_id: str) -> dict[str, Any]:
    coverage = coverage_for(source)
    files_skipped = string_list(coverage.get("files_skipped"))
    candidate_files = files_skipped or string_list(source.get("candidate_files"))
    unresolved_questions = string_list(coverage.get("unresolved_questions"))
    reason = gapfill_reason(source)
    questions = [
        f"Close the documented coverage gap for source target {source.get('id')}.",
        reason,
        *unresolved_questions,
    ]
    target: dict[str, Any] = {
        "id": target_id,
        "category": "gapfill",
        "title": f"Gapfill coverage for {source.get('id')}: {source.get('title') or ''}".strip(),
        "risk": choice(source.get("risk"), TARGET_RISKS, "medium"),
        "priority": min(100, max(bounded_priority(source), 70)),
        "status": "queued",
        "scope": str(source.get("scope") or ""),
        "entry_points": string_list(source.get("entry_points")),
        "trust_boundaries": string_list(source.get("trust_boundaries")),
        "sinks": string_list(source.get("sinks")),
        "review_questions": [q for q in questions if q],
        "candidate_files": candidate_files[: bounded_max_files(source)],
        "recommended_mode": choice(source.get("recommended_mode"), TARGET_MODES, "exec"),
        "attack_class": str(source.get("attack_class") or "Gapfill"),
        "attacker_model": str(source.get("attacker_model") or ""),
        "security_invariants": string_list(source.get("security_invariants")),
        "max_files": bounded_max_files(source),
        "expected_output": "finding-or-no-finding-with-coverage",
        "chain_relevance": choice(source.get("chain_relevance"), CHAIN_RELEVANCE, "possible-link"),
        "source_target_id": str(source.get("id") or ""),
        "gapfill_reason": reason,
        "notes": (
            f"Generated by gra-gapfill from {source.get('id')} because review depth "
            f"was {review_depth(source)}. Focus on skipped files and unresolved questions only."
        ),
    }
    # Keep optional fields compact when source targets did not provide them.
    if not target["attacker_model"]:
        target.pop("attacker_model")
    if not target["security_invariants"]:
        target.pop("security_invariants")
    if not target["candidate_files"]:
        target.pop("candidate_files")
    return target


def gapfill_relationship(gapfill_target: dict[str, Any] | None, *, newly_created: bool = False) -> str:
    if not isinstance(gapfill_target, dict):
        return "not-generated"
    if gapfill_target.get("duplicate_of") or gapfill_target.get("duplicate_target_id"):
        return "duplicate"
    if gapfill_target.get("variant_of") or gapfill_target.get("variant_target_id"):
        return "variant"
    return "new" if newly_created else "reused"


def gapfill_summary(
    gapfill_target: dict[str, Any],
    *,
    source: dict[str, Any] | None = None,
    relationship: str | None = None,
) -> dict[str, Any]:
    source = source if isinstance(source, dict) else {}
    reason = str(gapfill_target.get("gapfill_reason") or "").strip()
    if not reason and source:
        reason = gapfill_reason(source)
    return {
        "target_id": str(gapfill_target.get("id") or ""),
        "source_target_id": str(gapfill_target.get("source_target_id") or source.get("id") or ""),
        "priority": gapfill_target.get("priority"),
        "status": str(gapfill_target.get("status") or ""),
        "gapfill_reason": reason,
        "relationship": relationship or gapfill_relationship(gapfill_target),
        "variant_of": gapfill_target.get("variant_of") or gapfill_target.get("variant_target_id"),
        "duplicate_of": gapfill_target.get("duplicate_of") or gapfill_target.get("duplicate_target_id"),
    }


def next_gapfill_targets(
    targets: list[dict[str, Any]],
    *,
    relationships_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    relationships_by_id = relationships_by_id or {}
    source_by_id = {str(target.get("id") or ""): target for target in targets if isinstance(target, dict)}
    queued = [
        target
        for target in targets
        if isinstance(target, dict)
        and is_gapfill_target(target)
        and str(target.get("status") or "") in {"queued", "in_progress", "needs_human_review"}
    ]
    ordered = sorted(
        queued,
        key=lambda target: (
            -bounded_priority(target),
            0 if str(target.get("status") or "") == "in_progress" else 1,
            str(target.get("id") or ""),
        ),
    )
    return [
        gapfill_summary(
            target,
            source=source_by_id.get(str(target.get("source_target_id") or "")),
            relationship=relationships_by_id.get(str(target.get("id") or "")),
        )
        for target in ordered
    ]


def target_summary(
    target: dict[str, Any],
    gapfill_target: dict[str, Any] | None = None,
    *,
    relationship: str | None = None,
) -> dict[str, Any]:
    coverage = coverage_for(target)
    gapfill_target_id = str(gapfill_target.get("id") or "") if isinstance(gapfill_target, dict) else None
    gapfill_target_status = str(gapfill_target.get("status") or "") if isinstance(gapfill_target, dict) else ""
    return {
        "source_target_id": str(target.get("id") or ""),
        "gapfill_target_id": gapfill_target_id,
        "gapfill_target_status": gapfill_target_status,
        "title": str(target.get("title") or ""),
        "risk": str(target.get("risk") or ""),
        "priority": target.get("priority"),
        "status": str(target.get("status") or ""),
        "review_depth": review_depth(target),
        "gapfill_recommended": coverage.get("gapfill_recommended") is True,
        "gapfill_reason": gapfill_reason(target),
        "relationship": relationship or gapfill_relationship(gapfill_target),
        "variant_of": (
            gapfill_target.get("variant_of") or gapfill_target.get("variant_target_id")
            if isinstance(gapfill_target, dict)
            else None
        ),
        "duplicate_of": (
            gapfill_target.get("duplicate_of") or gapfill_target.get("duplicate_target_id")
            if isinstance(gapfill_target, dict)
            else None
        ),
        "files_reviewed": string_list(coverage.get("files_reviewed")),
        "files_skipped": string_list(coverage.get("files_skipped")),
        "commands_run": string_list(coverage.get("commands_run")),
        "unresolved_questions": string_list(coverage.get("unresolved_questions")),
    }


def count_by_status(targets: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in sorted(GAPFILL_TARGET_STATUSES)}
    counts["unknown"] = 0
    for target in targets:
        status = str(target.get("status") or "")
        if status not in counts:
            status = "unknown"
        counts[status] += 1
    return counts


def write_coverage_markdown(
    run_dir: Path,
    *,
    targets: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    generated: list[dict[str, Any]],
    gapfill_relationships_by_id: dict[str, str] | None = None,
) -> Path:
    reports = reports_dir(run_dir)
    generated_by_source = {str(t.get("source_target_id") or ""): str(t.get("id") or "") for t in generated}
    all_gapfill_targets = [target for target in targets if is_gapfill_target(target)]
    next_targets = next_gapfill_targets(targets, relationships_by_id=gapfill_relationships_by_id)
    lines = [
        "# Target Coverage Ledger",
        "",
        "This local artifact summarizes target review depth and bounded gapfill requeue candidates.",
        "",
        "## Current run",
        "",
        f"- Current candidate count: {len(candidates)}",
        f"- Current generated/reused target count: {len(generated)}",
        "",
        "## Cumulative gapfill queue",
        "",
        f"- Cumulative generated gapfill targets: {len(all_gapfill_targets)}",
        f"- Cumulative reviewed gapfill targets: {sum(1 for target in all_gapfill_targets if target.get('status') == 'reviewed')}",
        "",
        "## Next gapfill targets",
        "",
    ]
    if not next_targets:
        lines.append("No queued gapfill targets.")
    else:
        lines.extend(["| Priority | Gapfill target | Source target | Status | Relationship | Reason |", "|---:|---|---|---|---|---|"])
        for target in next_targets:
            lines.append(
                f"| {target.get('priority', '')} | {target.get('target_id', '')} | "
                f"{target.get('source_target_id', '')} | {target.get('status', '')} | "
                f"{target.get('relationship', '')} | {target.get('gapfill_reason', '')} |"
            )
    lines.extend(
        [
            "",
            "## Targets",
            "",
            "| Target | Risk | Status | Depth | Gapfill | Reason |",
            "|---|---|---|---|---|---|",
        ]
    )
    candidate_ids = {str(target.get("id") or "") for target in candidates}
    for target in sorted(targets, key=lambda t: str(t.get("id") or "")):
        tid = str(target.get("id") or "")
        gapfill = "yes" if tid in candidate_ids else "no"
        lines.append(
            f"| {tid} | {target.get('risk', '')} | {target.get('status', '')} | "
            f"{review_depth(target)} | {gapfill} | {gapfill_reason(target) if gapfill == 'yes' else ''} |"
        )

    lines.extend(["", "## Gapfill candidates", ""])
    if not candidates:
        lines.append("No gapfill candidates were identified.")
    else:
        for target in candidates:
            source_id = str(target.get("id") or "")
            generated_id = generated_by_source.get(source_id, "")
            lines.extend(
                [
                    f"### {source_id} {target.get('title', '')}".rstrip(),
                    "",
                    f"- Review depth: {review_depth(target)}",
                    f"- Reason: {gapfill_reason(target)}",
                    f"- Generated target: {generated_id or 'not generated'}",
                    f"- Files reviewed: {', '.join(string_list(coverage_for(target).get('files_reviewed'))) or 'none recorded'}",
                    f"- Files skipped: {', '.join(string_list(coverage_for(target).get('files_skipped'))) or 'none recorded'}",
                    "",
                ]
            )
    path = reports / "COVERAGE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_gapfill_plan(run_dir: Path, source: dict[str, Any], gapfill_target: dict[str, Any]) -> Path:
    path = reports_dir(run_dir) / "target-research" / f"{source.get('id')}-gapfill.md"
    coverage = coverage_for(source)
    lines = [
        f"# Gapfill plan for {source.get('id')}",
        "",
        f"- Source target: {source.get('id')} {source.get('title', '')}".rstrip(),
        f"- Generated target: {gapfill_target.get('id')}",
        f"- Review depth: {review_depth(source)}",
        f"- Gapfill reason: {gapfill_reason(source)}",
        f"- Bounded max files: {gapfill_target.get('max_files')}",
        "",
        "## Files reviewed",
        "",
    ]
    reviewed = string_list(coverage.get("files_reviewed"))
    if reviewed:
        lines.extend(f"- {item}" for item in reviewed)
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Files skipped", ""])
    skipped = string_list(coverage.get("files_skipped"))
    if skipped:
        lines.extend(f"- {item}" for item in skipped)
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Unresolved questions", ""])
    unresolved = string_list(coverage.get("unresolved_questions"))
    if unresolved:
        lines.extend(f"- {item}" for item in unresolved)
    else:
        lines.append("- none recorded")
    lines.extend(
        [
            "",
            "## Requeue instruction",
            "",
            "Run the generated target as a bounded follow-up. Do not broaden into a full repository audit,",
            "do not modify the target repository, and keep any resulting evidence local by default.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def generate_gapfill_artifacts(run_dir: Path) -> dict[str, Any]:
    ctx = load_context(run_dir)
    targets = load_targets(run_dir)
    candidates = gapfill_candidates(targets)
    existing_ids = {str(target.get("id") or "") for target in targets}
    generated: list[dict[str, Any]] = []
    candidate_records: list[dict[str, Any]] = []
    relationships_by_id: dict[str, str] = {}
    newly_created_count = 0
    reused_count = 0
    changed = False

    for source in candidates:
        source_id = str(source.get("id") or "")
        gapfill = existing_gapfill_target(targets, source_id)
        newly_created = False
        if gapfill is None:
            gapfill_id = next_gapfill_id(existing_ids)
            gapfill = build_gapfill_target(source, gapfill_id)
            targets.append(gapfill)
            existing_ids.add(gapfill_id)
            changed = True
            newly_created = True
            newly_created_count += 1
        else:
            reused_count += 1
        generated.append(gapfill)
        relationship = gapfill_relationship(gapfill, newly_created=newly_created)
        relationships_by_id[str(gapfill.get("id") or "")] = relationship
        candidate_records.append(target_summary(source, gapfill, relationship=relationship))
        write_gapfill_plan(run_dir, source, gapfill)

    if changed:
        write_targets(run_dir, targets)

    reports = reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    coverage_path = write_coverage_markdown(
        run_dir,
        targets=targets,
        candidates=candidates,
        generated=generated,
        gapfill_relationships_by_id=relationships_by_id,
    )
    all_gapfill_targets = [target for target in targets if is_gapfill_target(target)]
    next_targets = next_gapfill_targets(targets, relationships_by_id=relationships_by_id)
    payload = {
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "candidate_count": len(candidates),
        "generated_target_count": len(generated),
        "current_run": {
            "candidate_count": len(candidates),
            "generated_target_count": len(generated),
            "new_target_count": newly_created_count,
            "reused_target_count": reused_count,
        },
        "cumulative": {
            "generated_target_count": len(all_gapfill_targets),
            "reviewed_target_count": sum(1 for target in all_gapfill_targets if target.get("status") == "reviewed"),
            "targets_by_status": count_by_status(all_gapfill_targets),
        },
        "next_targets": next_targets,
        "coverage_report": coverage_path.relative_to(run_dir).as_posix(),
        "candidates": candidate_records,
        "generated_targets": generated,
    }
    write_json(reports / "gapfill-targets.json", payload)
    return payload

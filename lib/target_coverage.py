from __future__ import annotations

from pathlib import Path
from typing import Any

from gralib import load_context, load_targets, utc_now, write_json, write_targets
GAPFILL_DEPTHS = {"none", "shallow"}
GAPFILL_RISKS = {"critical", "high"}
TARGET_RISKS = {"critical", "high", "medium", "low", "informational"}
TARGET_MODES = {"exec", "goal"}
CHAIN_RELEVANCE = {"none", "possible-link", "candidate-chain-step"}


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


def target_summary(target: dict[str, Any], gapfill_target_id: str | None = None) -> dict[str, Any]:
    coverage = coverage_for(target)
    return {
        "source_target_id": str(target.get("id") or ""),
        "gapfill_target_id": gapfill_target_id,
        "title": str(target.get("title") or ""),
        "risk": str(target.get("risk") or ""),
        "priority": target.get("priority"),
        "status": str(target.get("status") or ""),
        "review_depth": review_depth(target),
        "gapfill_recommended": coverage.get("gapfill_recommended") is True,
        "gapfill_reason": gapfill_reason(target),
        "files_reviewed": string_list(coverage.get("files_reviewed")),
        "files_skipped": string_list(coverage.get("files_skipped")),
        "commands_run": string_list(coverage.get("commands_run")),
        "unresolved_questions": string_list(coverage.get("unresolved_questions")),
    }


def write_coverage_markdown(
    run_dir: Path,
    *,
    targets: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    generated: list[dict[str, Any]],
) -> Path:
    reports = reports_dir(run_dir)
    generated_by_source = {str(t.get("source_target_id") or ""): str(t.get("id") or "") for t in generated}
    lines = [
        "# Target Coverage Ledger",
        "",
        "This local artifact summarizes target review depth and bounded gapfill requeue candidates.",
        "",
        "## Targets",
        "",
        "| Target | Risk | Status | Depth | Gapfill | Reason |",
        "|---|---|---|---|---|---|",
    ]
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
    changed = False

    for source in candidates:
        source_id = str(source.get("id") or "")
        gapfill = existing_gapfill_target(targets, source_id)
        if gapfill is None:
            gapfill_id = next_gapfill_id(existing_ids)
            gapfill = build_gapfill_target(source, gapfill_id)
            targets.append(gapfill)
            existing_ids.add(gapfill_id)
            changed = True
        generated.append(gapfill)
        write_gapfill_plan(run_dir, source, gapfill)

    if changed:
        write_targets(run_dir, targets)

    reports = reports_dir(run_dir)
    reports.mkdir(parents=True, exist_ok=True)
    coverage_path = write_coverage_markdown(run_dir, targets=targets, candidates=candidates, generated=generated)
    payload = {
        "run_id": ctx.get("run_id", run_dir.name),
        "repo": ctx.get("repo", ""),
        "commit": ctx.get("commit", ""),
        "generated_at": utc_now(),
        "candidate_count": len(candidates),
        "generated_target_count": len(generated),
        "coverage_report": coverage_path.relative_to(run_dir).as_posix(),
        "candidates": [
            target_summary(source, str(generated[index].get("id") or "") if index < len(generated) else None)
            for index, source in enumerate(candidates)
        ],
        "generated_targets": generated,
    }
    write_json(reports / "gapfill-targets.json", payload)
    return payload

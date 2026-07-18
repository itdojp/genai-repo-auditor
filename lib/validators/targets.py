from __future__ import annotations

import json
import re

from taxonomies import validate_taxonomy_refs
from target_artifact import load_targets_artifact_path
from target_queue import validate_target_queue_artifact

from .common import json_type_name, validate_generated_at, validate_schema, validate_string_list
from .context import ValidationContext


TARGET_STATUSES = {"queued", "in_progress", "reviewed", "skipped", "needs_human_review"}
TARGET_RISKS = {"critical", "high", "medium", "low", "informational"}
TARGET_REVIEW_DEPTHS = {"none", "shallow", "medium", "deep"}
REQUIRED_TARGET = [
    "id",
    "category",
    "title",
    "risk",
    "priority",
    "status",
    "scope",
    "entry_points",
    "trust_boundaries",
    "sinks",
    "review_questions",
    "recommended_mode",
]


def validate_targets(context: ValidationContext) -> bool:
    targets_path = context.findings_path.parent / "targets.json"
    if not targets_path.exists():
        return False
    errors = context.errors
    try:
        targets_data = load_targets_artifact_path(targets_path, {})
    except json.JSONDecodeError as exc:
        errors.append(f"targets.json invalid JSON: {exc}")
        return True
    except Exception as exc:
        errors.append(f"targets.json could not be read safely: {exc}")
        return True

    validate_schema(targets_data, context.schema("targets.schema.json"), "targets", errors)
    if not isinstance(targets_data, dict):
        return True
    validate_generated_at(targets_data.get("generated_at"), "targets.generated_at", errors)
    errors.extend(validate_target_queue_artifact(targets_data))

    targets = targets_data.get("targets")
    if not isinstance(targets, list):
        errors.append("targets.targets: targets must be a list")
        return True
    deferred_targets = targets_data.get("deferred_targets", [])
    if not isinstance(deferred_targets, list):
        errors.append("targets.deferred_targets: deferred_targets must be a list")
        deferred_targets = []
    seen: set[str] = set()
    for collection_name, collection in (("targets", targets), ("deferred_targets", deferred_targets)):
        for index, target in enumerate(collection):
            path = f"targets.{collection_name}[{index}]"
            if not isinstance(target, dict):
                errors.append(f"{path}: target must be an object")
                continue
            target_id = str(target.get("id") or f"index-{index}")
            for key in REQUIRED_TARGET:
                if key not in target:
                    errors.append(f"{path}.{key}: missing target key")
            if not re.fullmatch(r"TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{3,}", target_id):
                errors.append(f"{path}.id: target id must match ^TGT-(?:[A-Z][A-Z0-9]*-)?[0-9]{{3,}}$ (got {target_id})")
            if target_id in seen:
                errors.append(f"{path}.id: duplicate target id {target_id}")
            seen.add(target_id)
            if target.get("risk") not in TARGET_RISKS:
                errors.append(f"{path}.risk: invalid risk {target.get('risk')}")
            if target.get("status") not in TARGET_STATUSES:
                errors.append(f"{path}.status: invalid status {target.get('status')}")
            if not isinstance(target.get("priority"), int) or isinstance(target.get("priority"), bool):
                errors.append(f"{path}.priority: priority must be integer")
            elif not 0 <= int(target["priority"]) <= 100:
                errors.append(f"{path}.priority: priority must be between 0 and 100")
            for key in [
                "entry_points",
                "trust_boundaries",
                "sinks",
                "security_invariants",
                "review_questions",
                "candidate_files",
            ]:
                if key in target:
                    validate_string_list(target.get(key), f"{path}.{key}", errors)
            if "max_files" in target:
                max_files = target.get("max_files")
                if not isinstance(max_files, int) or isinstance(max_files, bool):
                    errors.append(f"{path}.max_files: max_files must be integer")
                elif not 1 <= int(max_files) <= 20:
                    errors.append(f"{path}.max_files: max_files must be between 1 and 20")
            if "coverage" in target:
                coverage = target.get("coverage")
                coverage_path = f"{path}.coverage"
                if not isinstance(coverage, dict):
                    errors.append(f"{coverage_path}: coverage must be an object")
                else:
                    if "review_depth" in coverage and coverage.get("review_depth") not in TARGET_REVIEW_DEPTHS:
                        errors.append(f"{coverage_path}.review_depth: invalid review depth {coverage.get('review_depth')}")
                    for key in ["files_reviewed", "files_skipped", "commands_run", "unresolved_questions"]:
                        if key in coverage:
                            validate_string_list(coverage.get(key), f"{coverage_path}.{key}", errors)
                    if "gapfill_recommended" in coverage and not isinstance(coverage.get("gapfill_recommended"), bool):
                        errors.append(
                            f"{coverage_path}.gapfill_recommended: expected type boolean, "
                            f"got {json_type_name(coverage.get('gapfill_recommended'))}"
                        )
                    if "gapfill_reason" in coverage and not isinstance(coverage.get("gapfill_reason"), str):
                        errors.append(
                            f"{coverage_path}.gapfill_reason: expected type string, "
                            f"got {json_type_name(coverage.get('gapfill_reason'))}"
                        )
            if context.taxonomy_profiles_loaded:
                validate_taxonomy_refs(
                    target.get("taxonomies"),
                    f"{path}.taxonomies",
                    errors,
                    context.taxonomy_profiles,
                    context.taxonomy_labels,
                    context.taxonomy_aliases,
                )
    return True

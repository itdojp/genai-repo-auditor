from __future__ import annotations

import json
from pathlib import Path

from report_safety import ReportSafetyError

from .common import (
    validate_generated_at,
    validate_no_symlink_components,
    validate_run_artifact_path,
    validate_schema,
)
from .registry import ValidationContext


SCANNER_RESULTS_DIR = Path("reports/scanner-results")
NORMALIZED_SCANNER_RESULTS_DIR = SCANNER_RESULTS_DIR / "normalized"


def validate_scanner_index(context: ValidationContext) -> bool:
    run_dir = context.run_dir
    errors = context.errors
    index_path = run_dir / SCANNER_RESULTS_DIR / "scanner-index.json"
    if not index_path.exists():
        return False
    try:
        validate_no_symlink_components(
            run_dir,
            SCANNER_RESULTS_DIR / "scanner-index.json",
            field_path="scanner_index",
        )
    except ReportSafetyError as exc:
        errors.append(str(exc))
        return True
    try:
        scanner_index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"scanner-index.json invalid JSON: {exc}")
        return True

    validate_schema(scanner_index, context.schema("scanner-index.schema.json"), "scanner_index", errors)
    validate_generated_at(scanner_index.get("generated_at"), "scanner_index.generated_at", errors)

    results = scanner_index.get("results")
    if not isinstance(results, list):
        errors.append("scanner_index.results: results must be a list")
        return True

    for index, entry in enumerate(results):
        path = f"scanner_index.results[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{path}: scanner index entry must be an object")
            continue
        validate_generated_at(entry.get("imported_at"), f"{path}.imported_at", errors)
        try:
            validate_run_artifact_path(
                run_dir,
                entry.get("path"),
                field_path=f"{path}.path",
                required_root=SCANNER_RESULTS_DIR,
                missing_label="raw scanner artifact",
            )
        except ReportSafetyError as exc:
            errors.append(str(exc))

        normalized_path = entry.get("normalized_path")
        if normalized_path is None:
            errors.append(f"{path}.normalized_path: missing normalized artifact reference")
            continue
        try:
            normalized_file = validate_run_artifact_path(
                run_dir,
                normalized_path,
                field_path=f"{path}.normalized_path",
                required_root=NORMALIZED_SCANNER_RESULTS_DIR,
                require_json=True,
                missing_label="normalized scanner artifact",
            )
        except ReportSafetyError as exc:
            errors.append(str(exc))
            continue

        try:
            normalized = json.loads(normalized_file.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path}.normalized_path: invalid normalized scanner JSON: {exc}")
            continue
        if not isinstance(normalized, dict):
            errors.append(f"{path}.normalized_path: normalized scanner artifact must be an object")
            continue

        leads = normalized.get("leads")
        if not isinstance(leads, list):
            errors.append(f"{path}.normalized_path.leads: leads must be a list")
        elif "normalized_leads_count" not in entry:
            errors.append(f"{path}.normalized_leads_count: missing normalized lead count")
        else:
            lead_count = entry.get("normalized_leads_count")
            if isinstance(lead_count, int) and not isinstance(lead_count, bool) and lead_count != len(leads):
                errors.append(
                    f"{path}.normalized_leads_count: value {lead_count} "
                    f"does not match normalized leads length {len(leads)}"
                )

        if not isinstance(normalized.get("normalization"), dict):
            errors.append(f"{path}.normalized_path.normalization: normalization must be an object")
        elif "normalization" not in entry:
            errors.append(f"{path}.normalization: missing normalization metadata")
        elif entry.get("normalization") != normalized.get("normalization"):
            errors.append(f"{path}.normalization: value does not match normalized artifact metadata")

        if isinstance(entry.get("raw_bytes"), int) and not isinstance(entry.get("raw_bytes"), bool):
            if entry.get("raw_bytes") != normalized.get("raw_bytes"):
                errors.append(f"{path}.raw_bytes: value does not match normalized artifact raw_bytes")

    return True

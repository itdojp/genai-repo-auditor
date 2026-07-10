from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from report_safety import ReportSafetyError


def load_schema(lab_root: Path, name: str) -> Dict[str, Any]:
    return json.loads((lab_root / "templates" / "reports" / name).read_text(encoding="utf-8"))


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def matches_json_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_schema(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(matches_json_type(value, item) for item in expected_types):
            errors.append(f"{path}: expected type {'/'.join(expected_types)}, got {json_type_name(value)}")
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value {value!r} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value {value!r} does not match required constant {schema['const']!r}")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                validate_schema(value[key], subschema, f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_schema(item, schema["items"], f"{path}[{index}]", errors)

    if isinstance(value, str) and "pattern" in schema:
        if not re.search(schema["pattern"], value):
            errors.append(f"{path}: value {value!r} does not match pattern {schema['pattern']}")

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value {value} is above maximum {schema['maximum']}")


def validate_schema_shape(value: Any, schema: Dict[str, Any], path: str, errors: List[str]) -> None:
    """Validate a schema subset without echoing untrusted values in messages."""

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(matches_json_type(value, item) for item in expected_types):
            errors.append(f"{path}: expected type {'/'.join(expected_types)}")
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value is not allowed")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: value does not match required constant")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                validate_schema_shape(value[key], subschema, f"{path}.{key}", errors)

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_schema_shape(item, schema["items"], f"{path}[{index}]", errors)

    if isinstance(value, str) and "pattern" in schema:
        if not re.search(schema["pattern"], value):
            errors.append(f"{path}: value does not match required pattern")

    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: value is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: value is above maximum {schema['maximum']}")


def validate_generated_at(value: Any, path: str, errors: List[str]) -> None:
    if not isinstance(value, str):
        return
    raw = value.strip()
    if not raw:
        errors.append(f"{path}: generated_at must not be empty")
        return
    try:
        dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{path}: generated_at must be valid ISO-8601 datetime")


def parse_event_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_string_list(value: Any, path: str, errors: List[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: must be list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{path}[{index}]: expected type string, got {json_type_name(item)}")


def validate_run_artifact_path(
    run_dir: Path,
    value: Any,
    *,
    field_path: str,
    required_root: Path,
    require_json: bool = False,
    missing_label: str = "artifact",
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ReportSafetyError(f"{field_path}: path must be a non-empty string")
    rel = Path(value)
    if rel.is_absolute():
        raise ReportSafetyError(f"{field_path}: scanner artifact path must be relative to the run directory")
    if ".." in rel.parts:
        raise ReportSafetyError(f"{field_path}: scanner artifact path must not contain '..'")
    if rel == required_root or required_root not in (rel, *rel.parents):
        raise ReportSafetyError(f"{field_path}: scanner artifact path must stay under {required_root.as_posix()}")
    if require_json and rel.suffix.lower() != ".json":
        raise ReportSafetyError(f"{field_path}: normalized scanner artifact must be a .json file")

    target = run_dir / rel
    current = run_dir
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ReportSafetyError(f"{field_path}: scanner artifact path must not contain symlink components: {rel.as_posix()}")
    expected_root = (run_dir / required_root).resolve(strict=False)
    resolved_target = target.resolve(strict=False)
    try:
        resolved_target.relative_to(expected_root)
    except ValueError as exc:
        raise ReportSafetyError(f"{field_path}: scanner artifact path must not escape {required_root.as_posix()}") from exc
    if not target.exists():
        raise ReportSafetyError(f"{field_path}: {missing_label} not found: {rel.as_posix()}")
    if not target.is_file():
        raise ReportSafetyError(f"{field_path}: {missing_label} must be a regular file: {rel.as_posix()}")
    return target


def validate_no_symlink_components(run_dir: Path, rel: Path, *, field_path: str) -> None:
    current = run_dir
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ReportSafetyError(f"{field_path}: scanner artifact path must not contain symlink components: {rel.as_posix()}")

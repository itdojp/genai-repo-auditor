from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TAXONOMY_DIR = Path(__file__).resolve().parents[1] / "templates" / "taxonomies"


def load_taxonomy_profiles(taxonomy_dir: Path = TAXONOMY_DIR) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    if not taxonomy_dir.exists():
        return profiles
    for path in sorted(taxonomy_dir.glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        name = str(profile.get("name") or path.stem)
        entries = profile.get("entries") or []
        ids = {str(entry.get("id")) for entry in entries if isinstance(entry, dict) and entry.get("id")}
        profile["_path"] = path.as_posix()
        profile["_ids"] = ids
        profiles[name] = profile
    return profiles


def taxonomy_label_map(profiles: dict[str, dict[str, Any]] | None = None) -> dict[tuple[str, str], str]:
    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels: dict[tuple[str, str], str] = {}
    for name, profile in profiles.items():
        for entry in profile.get("entries") or []:
            if isinstance(entry, dict) and entry.get("id"):
                labels[(name, str(entry["id"]))] = str(entry.get("label") or entry["id"])
    return labels


def validate_taxonomy_refs(value: Any, field_path: str, errors: list[str], profiles: dict[str, dict[str, Any]] | None = None) -> None:
    if value is None:
        return
    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels = taxonomy_label_map(profiles)
    if not isinstance(value, list):
        errors.append(f"{field_path}: taxonomies must be list")
        return
    for index, item in enumerate(value):
        path = f"{field_path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: taxonomy reference must be object")
            continue
        name = item.get("name")
        identifier = item.get("id")
        label = item.get("label")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{path}.name: taxonomy name must be non-empty string")
            continue
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{path}.id: taxonomy id must be non-empty string")
            continue
        if name not in profiles:
            errors.append(f"{path}.name: unknown taxonomy {name!r}")
            continue
        if identifier not in profiles[name].get("_ids", set()):
            errors.append(f"{path}.id: unknown id {identifier!r} for taxonomy {name!r}")
            continue
        expected_label = labels.get((name, identifier))
        if label is not None and label != expected_label:
            errors.append(f"{path}.label: label {label!r} does not match taxonomy label {expected_label!r}")

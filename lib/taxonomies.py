from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

TAXONOMY_DIR = Path(__file__).resolve().parents[1] / "templates" / "taxonomies"


class TaxonomyProfileError(ValueError):
    """Raised when a taxonomy profile file cannot be loaded safely."""


def _default_taxonomy_dir() -> Path:
    override = os.environ.get("GENAI_REPO_AUDITOR_TAXONOMY_DIR")
    return Path(override) if override else TAXONOMY_DIR


def load_taxonomy_profiles(taxonomy_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    taxonomy_dir = taxonomy_dir if taxonomy_dir is not None else _default_taxonomy_dir()
    profiles: dict[str, dict[str, Any]] = {}
    source_paths: dict[str, str] = {}
    if not taxonomy_dir.exists():
        return profiles
    for path in sorted(taxonomy_dir.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TaxonomyProfileError(
                f"{path.as_posix()}: invalid taxonomy JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(profile, dict):
            raise TaxonomyProfileError(f"{path.as_posix()}: taxonomy profile must be a JSON object")
        name = str(profile.get("name") or path.stem).strip()
        if not name:
            raise TaxonomyProfileError(f"{path.as_posix()}: taxonomy profile name must be a non-empty string")
        if name in profiles:
            raise TaxonomyProfileError(
                f"{path.as_posix()}: duplicate taxonomy profile name {name!r}; already defined in {source_paths[name]}"
            )
        entries = profile.get("entries") or []
        ids = {str(entry.get("id")) for entry in entries if isinstance(entry, dict) and entry.get("id")}
        labels = {
            str(entry["id"]): str(entry.get("label") or entry["id"])
            for entry in entries
            if isinstance(entry, dict) and entry.get("id")
        }
        profile["_path"] = path.as_posix()
        profile["_ids"] = ids
        profile["_labels"] = labels
        profiles[name] = profile
        source_paths[name] = path.as_posix()
    return profiles


def taxonomy_label_map(profiles: dict[str, dict[str, Any]] | None = None) -> dict[tuple[str, str], str]:
    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels: dict[tuple[str, str], str] = {}
    for name, profile in profiles.items():
        profile_labels = profile.get("_labels")
        if isinstance(profile_labels, dict):
            for identifier, label in profile_labels.items():
                labels[(name, str(identifier))] = str(label)
            continue
        for entry in profile.get("entries") or []:
            if isinstance(entry, dict) and entry.get("id"):
                labels[(name, str(entry["id"]))] = str(entry.get("label") or entry["id"])
    return labels


def validate_taxonomy_refs(
    value: Any,
    field_path: str,
    errors: list[str],
    profiles: dict[str, dict[str, Any]] | None = None,
    labels: dict[tuple[str, str], str] | None = None,
) -> None:
    if value is None:
        return
    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels = labels if labels is not None else taxonomy_label_map(profiles)
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
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{path}.label: taxonomy label must be non-empty string")
            continue
        if name not in profiles:
            errors.append(f"{path}.name: unknown taxonomy {name!r}")
            continue
        if identifier not in profiles[name].get("_ids", set()):
            errors.append(f"{path}.id: unknown id {identifier!r} for taxonomy {name!r}")
            continue
        expected_label = labels.get((name, identifier))
        if label != expected_label:
            errors.append(f"{path}.label: label {label!r} does not match taxonomy label {expected_label!r}")

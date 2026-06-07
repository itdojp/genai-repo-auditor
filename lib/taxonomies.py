from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

TAXONOMY_DIR = Path(__file__).resolve().parents[1] / "templates" / "taxonomies"
TAXONOMY_ALIAS_FILE = Path(__file__).resolve().parents[1] / "templates" / "taxonomy-aliases.json"


class TaxonomyProfileError(ValueError):
    """Raised when a taxonomy profile file cannot be loaded safely."""


class TaxonomyAliasError(ValueError):
    """Raised when a taxonomy alias file cannot be loaded safely."""


def _default_taxonomy_dir() -> Path:
    override = os.environ.get("GENAI_REPO_AUDITOR_TAXONOMY_DIR")
    return Path(override) if override else TAXONOMY_DIR


def _default_taxonomy_alias_file() -> Path:
    override = os.environ.get("GENAI_REPO_AUDITOR_TAXONOMY_ALIAS_FILE")
    return Path(override) if override else TAXONOMY_ALIAS_FILE


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


def load_taxonomy_aliases(alias_file: Path | None = None) -> dict[str, Any]:
    alias_file = alias_file if alias_file is not None else _default_taxonomy_alias_file()
    if not alias_file.exists():
        return {"schema_version": "1", "name_aliases": [], "id_mappings": []}
    try:
        aliases = json.loads(alias_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TaxonomyAliasError(
            f"{alias_file.as_posix()}: invalid taxonomy alias JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(aliases, dict):
        raise TaxonomyAliasError(f"{alias_file.as_posix()}: taxonomy alias file must be a JSON object")
    for key in ["name_aliases", "id_mappings"]:
        value = aliases.get(key, [])
        if not isinstance(value, list):
            raise TaxonomyAliasError(f"{alias_file.as_posix()}: {key} must be a list")
    validate_taxonomy_aliases(aliases, source=alias_file.as_posix())
    return aliases


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


def validate_taxonomy_aliases(aliases: dict[str, Any], *, source: str = "taxonomy aliases") -> None:
    for index, item in enumerate(aliases.get("name_aliases") or []):
        if not isinstance(item, dict):
            raise TaxonomyAliasError(f"{source}: name_aliases[{index}]: alias entry must be an object")
        if not isinstance(item.get("from"), str) or not item.get("from", "").strip():
            raise TaxonomyAliasError(f"{source}: name_aliases[{index}].from: must be a non-empty string")
        if not isinstance(item.get("to"), str) or not item.get("to", "").strip():
            raise TaxonomyAliasError(f"{source}: name_aliases[{index}].to: must be a non-empty string")

    for index, item in enumerate(aliases.get("id_mappings") or []):
        if not isinstance(item, dict):
            raise TaxonomyAliasError(f"{source}: id_mappings[{index}]: mapping entry must be an object")
        source_ref = item.get("from")
        target_ref = item.get("to")
        if not isinstance(source_ref, dict):
            raise TaxonomyAliasError(f"{source}: id_mappings[{index}].from: must be an object")
        if not isinstance(target_ref, dict):
            raise TaxonomyAliasError(f"{source}: id_mappings[{index}].to: must be an object")
        for field, value in [
            ("from.name", source_ref.get("name")),
            ("from.id", source_ref.get("id")),
            ("to.name", target_ref.get("name")),
            ("to.id", target_ref.get("id")),
        ]:
            if not isinstance(value, str) or not value.strip():
                raise TaxonomyAliasError(f"{source}: id_mappings[{index}].{field}: must be a non-empty string")
        mode = str(item.get("mode") or "suggest").strip().lower()
        if mode not in {"auto", "suggest"}:
            raise TaxonomyAliasError(f"{source}: id_mappings[{index}].mode: must be 'auto' or 'suggest'")


def taxonomy_name_alias_map(aliases: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    aliases = aliases if aliases is not None else load_taxonomy_aliases()
    mapping: dict[str, dict[str, str]] = {}
    for index, item in enumerate(aliases.get("name_aliases") or []):
        if not isinstance(item, dict):
            raise TaxonomyAliasError(f"name_aliases[{index}]: alias entry must be an object")
        source = item.get("from")
        target = item.get("to")
        if not isinstance(source, str) or not source.strip():
            raise TaxonomyAliasError(f"name_aliases[{index}].from: must be a non-empty string")
        if not isinstance(target, str) or not target.strip():
            raise TaxonomyAliasError(f"name_aliases[{index}].to: must be a non-empty string")
        mapping[source] = {
            "to": target,
            "reason": str(item.get("reason") or f"taxonomy name alias {source!r} -> {target!r}"),
        }
    return mapping


def taxonomy_id_mapping_map(aliases: dict[str, Any] | None = None) -> dict[tuple[str, str], dict[str, str]]:
    aliases = aliases if aliases is not None else load_taxonomy_aliases()
    mapping: dict[tuple[str, str], dict[str, str]] = {}
    for index, item in enumerate(aliases.get("id_mappings") or []):
        if not isinstance(item, dict):
            raise TaxonomyAliasError(f"id_mappings[{index}]: mapping entry must be an object")
        source = item.get("from")
        target = item.get("to")
        if not isinstance(source, dict):
            raise TaxonomyAliasError(f"id_mappings[{index}].from: must be an object")
        if not isinstance(target, dict):
            raise TaxonomyAliasError(f"id_mappings[{index}].to: must be an object")
        source_name = source.get("name")
        source_id = source.get("id")
        target_name = target.get("name")
        target_id = target.get("id")
        for field, value in [
            ("from.name", source_name),
            ("from.id", source_id),
            ("to.name", target_name),
            ("to.id", target_id),
        ]:
            if not isinstance(value, str) or not value.strip():
                raise TaxonomyAliasError(f"id_mappings[{index}].{field}: must be a non-empty string")
        mode = str(item.get("mode") or "suggest").strip().lower()
        if mode not in {"auto", "suggest"}:
            raise TaxonomyAliasError(f"id_mappings[{index}].mode: must be 'auto' or 'suggest'")
        mapping[(source_name, source_id)] = {
            "to_name": target_name,
            "to_id": target_id,
            "mode": mode,
            "reason": str(item.get("reason") or f"taxonomy id mapping {source_id!r} -> {target_id!r}"),
        }
    return mapping


def _taxonomy_ref(name: str, identifier: str, labels: dict[tuple[str, str], str]) -> dict[str, str]:
    return {
        "name": name,
        "id": identifier,
        "label": labels.get((name, identifier), identifier),
    }


def _normalize_mapping_key(name: str, identifier: str, name_aliases: dict[str, dict[str, str]]) -> tuple[str, str]:
    alias = name_aliases.get(name)
    if alias:
        return alias["to"], identifier
    return name, identifier


def suggest_taxonomy_replacement(
    name: str,
    identifier: str,
    profiles: dict[str, dict[str, Any]] | None = None,
    labels: dict[tuple[str, str], str] | None = None,
    aliases: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Return a configured replacement suggestion for a taxonomy reference."""

    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels = labels if labels is not None else taxonomy_label_map(profiles)
    aliases = aliases if aliases is not None else load_taxonomy_aliases()
    name_aliases = taxonomy_name_alias_map(aliases)
    id_mappings = taxonomy_id_mapping_map(aliases)

    keys = [(name, identifier)]
    aliased_name, aliased_identifier = _normalize_mapping_key(name, identifier, name_aliases)
    if (aliased_name, aliased_identifier) not in keys:
        keys.append((aliased_name, aliased_identifier))

    for key in keys:
        mapping = id_mappings.get(key)
        if mapping:
            return {
                **_taxonomy_ref(mapping["to_name"], mapping["to_id"], labels),
                "mode": mapping["mode"],
                "reason": mapping["reason"],
            }

    if name not in profiles and (alias := name_aliases.get(name)):
        target_name = alias["to"]
        if identifier in profiles.get(target_name, {}).get("_ids", set()):
            return {
                **_taxonomy_ref(target_name, identifier, labels),
                "mode": "auto",
                "reason": alias["reason"],
            }
    return None


def normalize_taxonomy_refs(
    value: Any,
    field_path: str,
    profiles: dict[str, dict[str, Any]] | None = None,
    labels: dict[tuple[str, str], str] | None = None,
    aliases: dict[str, Any] | None = None,
) -> tuple[Any, list[dict[str, Any]], list[str]]:
    """Normalize configured taxonomy aliases and labels.

    Returns ``(normalized_value, changes, errors)``. Only deterministic
    configured mappings with ``mode: "auto"`` and canonical label corrections
    are applied. Unsupported references without an automatic mapping are left
    unchanged and reported in ``errors`` with any configured suggestion.
    """

    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels = labels if labels is not None else taxonomy_label_map(profiles)
    aliases = aliases if aliases is not None else load_taxonomy_aliases()
    name_aliases = taxonomy_name_alias_map(aliases)
    id_mappings = taxonomy_id_mapping_map(aliases)
    errors: list[str] = []
    changes: list[dict[str, Any]] = []

    if value is None:
        return value, changes, errors
    if not isinstance(value, list):
        errors.append(f"{field_path}: taxonomies must be list")
        return value, changes, errors

    normalized: list[Any] = []
    for index, item in enumerate(value):
        path = f"{field_path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{path}: taxonomy reference must be object")
            normalized.append(item)
            continue
        before = dict(item)
        name = item.get("name")
        identifier = item.get("id")
        label = item.get("label")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{path}.name: taxonomy name must be non-empty string")
            normalized.append(item)
            continue
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"{path}.id: taxonomy id must be non-empty string")
            normalized.append(item)
            continue
        if not isinstance(label, str) or not label.strip():
            errors.append(f"{path}.label: taxonomy label must be non-empty string")
            normalized.append(item)
            continue

        current = dict(item)
        current["name"] = name.strip()
        current["id"] = identifier.strip()
        current["label"] = label.strip()
        reasons: list[str] = []

        alias = name_aliases.get(current["name"])
        if alias and current["id"] in profiles.get(alias["to"], {}).get("_ids", set()):
            current["name"] = alias["to"]
            reasons.append(alias["reason"])

        mapping_key = (current["name"], current["id"])
        mapping = id_mappings.get(mapping_key)
        if mapping and mapping["mode"] == "auto":
            current["name"] = mapping["to_name"]
            current["id"] = mapping["to_id"]
            reasons.append(mapping["reason"])

        if current["name"] not in profiles:
            suggestion = suggest_taxonomy_replacement(current["name"], current["id"], profiles, labels, aliases)
            suffix = ""
            if suggestion:
                suffix = f"; suggested replacement {suggestion['name']}:{suggestion['id']} ({suggestion['label']})"
            errors.append(f"{path}.name: unknown taxonomy {current['name']!r}{suffix}")
            normalized.append(current)
            continue
        if current["id"] not in profiles[current["name"]].get("_ids", set()):
            suggestion = suggest_taxonomy_replacement(current["name"], current["id"], profiles, labels, aliases)
            suffix = ""
            if suggestion:
                suffix = f"; suggested replacement {suggestion['name']}:{suggestion['id']} ({suggestion['label']})"
            errors.append(f"{path}.id: unknown id {current['id']!r} for taxonomy {current['name']!r}{suffix}")
            normalized.append(current)
            continue

        expected_label = labels.get((current["name"], current["id"]))
        if expected_label and current["label"] != expected_label:
            current["label"] = expected_label
            reasons.append(f"canonical label for {current['name']}:{current['id']}")

        if current != before:
            changes.append(
                {
                    "field_path": path,
                    "before": before,
                    "after": dict(current),
                    "reason": "; ".join(reasons) or "canonical taxonomy normalization",
                }
            )
        normalized.append(current)
    return normalized, changes, errors


def validate_taxonomy_refs(
    value: Any,
    field_path: str,
    errors: list[str],
    profiles: dict[str, dict[str, Any]] | None = None,
    labels: dict[tuple[str, str], str] | None = None,
    aliases: dict[str, Any] | None = None,
) -> None:
    if value is None:
        return
    profiles = profiles if profiles is not None else load_taxonomy_profiles()
    labels = labels if labels is not None else taxonomy_label_map(profiles)
    aliases = aliases if aliases is not None else load_taxonomy_aliases()
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
            suggestion = suggest_taxonomy_replacement(name, identifier, profiles, labels, aliases)
            suffix = ""
            if suggestion:
                suffix = f"; suggested replacement {suggestion['name']}:{suggestion['id']} ({suggestion['label']})"
            errors.append(f"{path}.name: unknown taxonomy {name!r}{suffix}")
            continue
        if identifier not in profiles[name].get("_ids", set()):
            suggestion = suggest_taxonomy_replacement(name, identifier, profiles, labels, aliases)
            suffix = ""
            if suggestion:
                suffix = f"; suggested replacement {suggestion['name']}:{suggestion['id']} ({suggestion['label']})"
            errors.append(f"{path}.id: unknown id {identifier!r} for taxonomy {name!r}{suffix}")
            continue
        expected_label = labels.get((name, identifier))
        if label != expected_label:
            errors.append(
                f"{path}.label: label {label!r} does not match taxonomy label {expected_label!r}; "
                "run gra-taxonomy-preflight --fix to apply the canonical label"
            )

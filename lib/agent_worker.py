from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROFILE_DIR = Path("templates") / "agent-workers"
CODEX_PROFILE_ID = "codex-cli"
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
REQUIRED_FIELDS = {
    "id",
    "display_name",
    "profile_status",
    "executable",
    "supports_exec",
    "supports_goal",
    "supports_json_events",
    "default_model",
    "default_effort",
    "sandbox_modes",
    "network_default",
    "command_templates",
}
ALLOWED_PROFILE_STATUSES = {"builtin", "experimental"}


class AgentWorkerProfileError(ValueError):
    """Raised when an agent worker profile is missing or invalid."""


@dataclass(frozen=True)
class AgentWorkerProfile:
    id: str
    display_name: str
    profile_status: str
    executable: str
    supports_exec: bool
    supports_goal: bool
    supports_json_events: bool
    default_model: str
    default_effort: str
    sandbox_modes: tuple[str, ...]
    network_default: bool
    command_templates: dict[str, str]
    source: Path | None = None
    description: str = ""

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "profile_status": self.profile_status,
            "executable": self.executable,
            "supports_exec": self.supports_exec,
            "supports_goal": self.supports_goal,
            "supports_json_events": self.supports_json_events,
            "default_model": self.default_model,
            "default_effort": self.default_effort,
            "sandbox_modes": list(self.sandbox_modes),
            "network_default": self.network_default,
            "source": str(self.source) if self.source else None,
        }


def profile_directory(lab_root: Path, profiles_dir: Path | None = None) -> Path:
    if profiles_dir is not None:
        return Path(profiles_dir)
    return Path(lab_root) / PROFILE_DIR


def profile_files(lab_root: Path, profiles_dir: Path | None = None) -> list[Path]:
    directory = profile_directory(lab_root, profiles_dir)
    if not directory.exists():
        raise AgentWorkerProfileError(f"agent worker profile directory does not exist: {directory}")
    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and (path.name.endswith(".json") or path.name.endswith(".json.example"))
    ]
    return sorted(files, key=lambda path: path.name)


def _source_stem(source: Path | None) -> str | None:
    if source is None:
        return None
    name = source.name
    if name.endswith(".json.example"):
        return name[: -len(".json.example")]
    if name.endswith(".json"):
        return name[: -len(".json")]
    return source.stem


def _is_example_path(path: Path | None) -> bool:
    return bool(path and path.name.endswith(".json.example"))


def _require_string(data: dict[str, Any], field: str, source: Path | None) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AgentWorkerProfileError(f"{source or '<profile>'}: {field} must be a non-empty string")
    return value.strip()


def _require_bool(data: dict[str, Any], field: str, source: Path | None) -> bool:
    value = data.get(field)
    if not isinstance(value, bool):
        raise AgentWorkerProfileError(f"{source or '<profile>'}: {field} must be boolean")
    return value


def _require_string_list(data: dict[str, Any], field: str, source: Path | None) -> tuple[str, ...]:
    value = data.get(field)
    if not isinstance(value, list) or not value:
        raise AgentWorkerProfileError(f"{source or '<profile>'}: {field} must be a non-empty string array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AgentWorkerProfileError(f"{source or '<profile>'}: {field} entries must be non-empty strings")
        items.append(item.strip())
    return tuple(items)


def _require_templates(data: dict[str, Any], source: Path | None) -> dict[str, str]:
    value = data.get("command_templates")
    if not isinstance(value, dict) or not value:
        raise AgentWorkerProfileError(f"{source or '<profile>'}: command_templates must be a non-empty object")
    templates: dict[str, str] = {}
    for key, template in value.items():
        if not isinstance(key, str) or not key.strip():
            raise AgentWorkerProfileError(f"{source or '<profile>'}: command template keys must be non-empty strings")
        if not isinstance(template, str) or not template.strip():
            raise AgentWorkerProfileError(f"{source or '<profile>'}: command template {key!r} must be a non-empty string")
        templates[key.strip()] = template.strip()
    return templates


def validate_profile(data: Any, *, source: Path | None = None) -> AgentWorkerProfile:
    if not isinstance(data, dict):
        raise AgentWorkerProfileError(f"{source or '<profile>'}: profile must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        raise AgentWorkerProfileError(f"{source or '<profile>'}: missing required fields: {', '.join(missing)}")

    profile_id = _require_string(data, "id", source)
    if not PROFILE_ID_RE.match(profile_id):
        raise AgentWorkerProfileError(f"{source or '<profile>'}: id must use lowercase letters, numbers, and hyphens")
    source_stem = _source_stem(source)
    if source_stem and source_stem != profile_id:
        raise AgentWorkerProfileError(f"{source}: file name must match profile id {profile_id!r}")

    status = _require_string(data, "profile_status", source)
    if status not in ALLOWED_PROFILE_STATUSES:
        raise AgentWorkerProfileError(
            f"{source or '<profile>'}: profile_status must be one of: {', '.join(sorted(ALLOWED_PROFILE_STATUSES))}"
        )

    executable = _require_string(data, "executable", source)
    if any(separator in executable for separator in ("/", "\\")):
        raise AgentWorkerProfileError(f"{source or '<profile>'}: executable must be a command name, not a path")

    supports_exec = _require_bool(data, "supports_exec", source)
    supports_goal = _require_bool(data, "supports_goal", source)
    command_templates = _require_templates(data, source)
    if supports_exec and "exec" not in command_templates:
        raise AgentWorkerProfileError(f"{source or '<profile>'}: supports_exec requires command_templates.exec")
    if supports_goal and "goal" not in command_templates:
        raise AgentWorkerProfileError(f"{source or '<profile>'}: supports_goal requires command_templates.goal")

    description = data.get("description", "")
    if description is not None and not isinstance(description, str):
        raise AgentWorkerProfileError(f"{source or '<profile>'}: description must be a string when present")

    return AgentWorkerProfile(
        id=profile_id,
        display_name=_require_string(data, "display_name", source),
        profile_status=status,
        executable=executable,
        supports_exec=supports_exec,
        supports_goal=supports_goal,
        supports_json_events=_require_bool(data, "supports_json_events", source),
        default_model=_require_string(data, "default_model", source),
        default_effort=_require_string(data, "default_effort", source),
        sandbox_modes=_require_string_list(data, "sandbox_modes", source),
        network_default=_require_bool(data, "network_default", source),
        command_templates=command_templates,
        source=source,
        description=description or "",
    )


def load_profile_file(path: Path) -> AgentWorkerProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentWorkerProfileError(f"{path}: invalid JSON: {exc.msg}") from exc
    except OSError as exc:
        raise AgentWorkerProfileError(f"{path}: cannot read profile: {exc}") from exc
    return validate_profile(data, source=path)


def load_profiles(lab_root: Path, profiles_dir: Path | None = None) -> list[AgentWorkerProfile]:
    profiles: list[AgentWorkerProfile] = []
    seen: dict[str, AgentWorkerProfile] = {}
    duplicates: set[str] = set()
    for path in profile_files(lab_root, profiles_dir):
        profile = load_profile_file(path)
        existing = seen.get(profile.id)
        if existing is None:
            seen[profile.id] = profile
            profiles.append(profile)
            continue
        if _is_example_path(existing.source) and not _is_example_path(profile.source):
            seen[profile.id] = profile
            profiles[profiles.index(existing)] = profile
            continue
        if not _is_example_path(existing.source) and _is_example_path(profile.source):
            continue
        duplicates.add(profile.id)
    if duplicates:
        raise AgentWorkerProfileError(f"duplicate agent worker profile ids: {', '.join(sorted(duplicates))}")
    return profiles


def load_profile(lab_root: Path, profile_id: str, profiles_dir: Path | None = None) -> AgentWorkerProfile:
    directory = profile_directory(lab_root, profiles_dir)
    for suffix in (".json", ".json.example"):
        path = directory / f"{profile_id}{suffix}"
        if path.exists() and path.is_file():
            return load_profile_file(path)
    for profile in load_profiles(lab_root, profiles_dir):
        if profile.id == profile_id:
            return profile
    raise AgentWorkerProfileError(f"unknown agent worker profile: {profile_id}")


def built_in_codex_profile(lab_root: Path) -> AgentWorkerProfile:
    return load_profile(lab_root, CODEX_PROFILE_ID)


def codex_worker_executable(lab_root: Path | None = None) -> str:
    root = Path(lab_root) if lab_root is not None else Path(__file__).resolve().parents[1]
    try:
        return built_in_codex_profile(root).executable
    except AgentWorkerProfileError:
        return "codex"


def check_profile_executable(profile: AgentWorkerProfile, *, path_env: str | None = None) -> dict[str, Any]:
    resolved = shutil.which(profile.executable, path=path_env)
    diagnostics: list[str]
    if resolved:
        diagnostics = [f"Required executable '{profile.executable}' was found at {resolved}."]
    else:
        diagnostics = [
            f"Required executable '{profile.executable}' for profile '{profile.id}' was not found on PATH.",
            "Install the worker CLI or adjust PATH before using this profile for execution.",
        ]
    return {
        "profile_id": profile.id,
        "display_name": profile.display_name,
        "profile_status": profile.profile_status,
        "executable": profile.executable,
        "available": resolved is not None,
        "resolved_path": resolved,
        "diagnostics": diagnostics,
    }


def profiles_as_jsonable(profiles: Iterable[AgentWorkerProfile]) -> list[dict[str, Any]]:
    return [profile.to_summary() for profile in profiles]

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .common import load_schema


@dataclass
class ValidationContext:
    """Shared validation inputs and ordered error state for validators."""

    lab_root: Path
    run_dir: Path
    findings_path: Path
    findings_data: Any
    errors: list[str]
    taxonomy_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    taxonomy_labels: dict[tuple[str, str], str] = field(default_factory=dict)
    taxonomy_aliases: dict[str, Any] = field(default_factory=dict)
    taxonomy_profiles_loaded: bool = False

    @property
    def findings(self) -> list[Any]:
        if not isinstance(self.findings_data, dict):
            return []
        value = self.findings_data.get("findings")
        return value if isinstance(value, list) else []

    def schema(self, name: str) -> dict[str, Any]:
        return load_schema(self.lab_root, name)


Validator = Callable[[ValidationContext], bool]

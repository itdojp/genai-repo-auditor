from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .common import load_schema


@dataclass
class ValidationContext:
    """Shared validation inputs and ordered error state for validators."""

    lab_root: Path
    run_dir: Path
    findings_path: Path
    findings_data: dict[str, Any]
    errors: list[str]
    taxonomy_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    taxonomy_labels: dict[tuple[str, str], str] = field(default_factory=dict)
    taxonomy_aliases: dict[str, Any] = field(default_factory=dict)
    taxonomy_profiles_loaded: bool = False

    @property
    def findings(self) -> list[Any]:
        value = self.findings_data.get("findings")
        return value if isinstance(value, list) else []

    def schema(self, name: str) -> dict[str, Any]:
        return load_schema(self.lab_root, name)


Validator = Callable[[ValidationContext], bool]


class ValidatorRegistry:
    """Ordered validator registry with explicit named dispatch."""

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._validators)

    def register(self, name: str, validator: Validator) -> None:
        if not name or name in self._validators:
            raise ValueError(f"validator already registered or invalid: {name!r}")
        self._validators[name] = validator

    def run(self, context: ValidationContext, names: Iterable[str]) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name in names:
            try:
                validator = self._validators[name]
            except KeyError as exc:
                raise KeyError(f"unknown validator: {name}") from exc
            results[name] = validator(context)
        return results


def core_validator_registry() -> ValidatorRegistry:
    from .findings import validate_findings
    from .run_manifest import validate_run_manifest
    from .scanner import validate_scanner_index
    from .targets import validate_targets

    registry = ValidatorRegistry()
    registry.register("findings", validate_findings)
    registry.register("targets", validate_targets)
    registry.register("scanner_index", validate_scanner_index)
    registry.register("run_manifest", validate_run_manifest)
    return registry

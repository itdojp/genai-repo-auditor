from __future__ import annotations

from typing import Iterable

from .context import ValidationContext, Validator


class ValidatorRegistry:
    """Ordered validator registry with explicit named dispatch."""

    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._validators)

    def register(self, name: str, validator: Validator) -> None:
        if not isinstance(name, str) or not name.strip() or name in self._validators:
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

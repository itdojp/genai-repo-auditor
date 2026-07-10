"""Modular report validators used by ``gra-validate-report``."""

from .registry import (
    ValidationContext,
    ValidatorRegistry,
    core_validator_registry,
    report_validator_registry,
)

__all__ = [
    "ValidationContext",
    "ValidatorRegistry",
    "core_validator_registry",
    "report_validator_registry",
]

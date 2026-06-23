"""
Router V6 Stage DRC Validators.

Per-stage Design Rule Check (DRC) validators that run after each
channel analysis micro-stage. Each validator is a standalone function
decorated with @register_validator(name) for auto-discovery.

Part of feat/decompose-stage2: U0 BoardState Extension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Global registry: validator_name -> callable
VALIDATOR_REGISTRY: dict[str, list[Callable]] = {}


@dataclass
class StageDRCFailure:
    """A design rule violation detected by a stage validator."""

    field: str
    value: Any
    reason: str
    stage: str = ""

    def __str__(self) -> str:
        return f"[{self.stage}] {self.field}: {self.reason} (value={self.value!r})"


def register_validator(name: str):
    """Decorator to register a validator function for a specific stage."""

    def decorator(func: Callable):
        if name not in VALIDATOR_REGISTRY:
            VALIDATOR_REGISTRY[name] = []
        VALIDATOR_REGISTRY[name].append(func)
        return func

    return decorator


def run_validators(stage_name: str, state) -> list[StageDRCFailure]:
    """Run all registered validators for a stage."""
    failures: list[StageDRCFailure] = []
    for validator in VALIDATOR_REGISTRY.get(stage_name, []):
        result = validator(state)
        if isinstance(result, list):
            failures.extend(result)
        elif result is not None:
            failures.append(result)
    return failures


def get_registered_stages() -> list[str]:
    """Return list of stage names that have validators registered."""
    return sorted(VALIDATOR_REGISTRY.keys())


def clear_validators():
    """Clear all registered validators (useful for testing)."""
    VALIDATOR_REGISTRY.clear()

"""
Router V6 Stage DRC Validators.

Per-stage Design Rule Check (DRC) validators that run after each
channel analysis micro-stage. Each validator is a standalone function
decorated with @register_validator(name) for auto-discovery.

Part of feat/decompose-stage2: U0 BoardState Extension.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Global registry: validator_name -> callable
VALIDATOR_REGISTRY: dict[str, list[Callable]] = {}


@dataclass
class StageDRCFailure:
    """A design rule violation detected by a stage validator.

    ``fatal`` (2026-08-07, R10/anti-vacuity hardening --
    docs/evidence/2026-08-07-router-silent-noop-diagnosis.md): historically
    *every* ``StageDRCFailure`` returned by a validator was purely advisory
    -- ``Stage2Orchestrator``/``Stage4Orchestrator`` only ever printed it,
    and only when ``verbose=True``. A validator correctly detecting the
    router's empty-model silent-noop bug would still have produced a clean
    exit code in CI. ``fatal=True`` marks a failure the orchestrator must
    raise on unconditionally (see ``assert_no_fatal_failures`` below) --
    reserved for non-emptiness/vacuity findings where "printed a warning
    nobody reads" is not an acceptable response. Ordinary per-item DRC
    findings (negative area, duplicate variable names, ...) stay
    non-fatal/advisory, unchanged from prior behavior.
    """

    field: str
    value: Any
    reason: str
    stage: str = ""
    fatal: bool = False

    def __str__(self) -> str:
        return f"[{self.stage}] {self.field}: {self.reason} (value={self.value!r})"


class FatalStageDRCFailure(RuntimeError):
    """Raised by ``assert_no_fatal_failures`` when a stage validator reports
    one or more ``fatal=True`` failures. Distinct from a bare ``assert`` so
    the message can enumerate every fatal finding, not just trip silently."""


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


def assert_no_fatal_failures(stage_name: str, failures: list[StageDRCFailure]) -> None:
    """Raise ``FatalStageDRCFailure`` if any failure in *failures* is fatal.

    Called by the Stage2/Stage4 orchestrators after every stage, regardless
    of ``verbose`` -- this is what makes ``fatal=True`` load-bearing rather
    than another advisory print statement. Non-fatal failures are left for
    the caller to print/log as before; this function only concerns itself
    with the fatal subset.
    """
    fatal = [f for f in failures if f.fatal]
    if not fatal:
        return
    detail = "\n".join(f"  - {f}" for f in fatal)
    raise FatalStageDRCFailure(
        f"Stage {stage_name!r} produced {len(fatal)} fatal DRC failure(s) -- "
        f"halting rather than continuing on a vacuously-empty or otherwise "
        f"structurally-broken stage output:\n{detail}"
    )


def get_registered_stages() -> list[str]:
    """Return list of stage names that have validators registered."""
    return sorted(VALIDATOR_REGISTRY.keys())


def clear_validators():
    """Clear all registered validators (useful for testing)."""
    VALIDATOR_REGISTRY.clear()

"""Strategy registry keyed by ``(phase: str, name: str)``.

Module-level, idempotent registration that decouples pipeline phases from
the registry itself — phases are plain strings, not enums.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.protocol import PipelineStage

# (phase, name) → factory that returns a PipelineStage
_registry: dict[tuple[str, str], Callable[[], PipelineStage]] = {}

# composite_name → ordered list of (phase, name) keys
_composites: dict[str, list[tuple[str, str]]] = {}


def register(
    phase: str,
    name: str,
    stage_factory: Callable[[], PipelineStage],
) -> None:
    """Register a stage factory under ``(phase, name)``.

    Idempotent — re-registering the same key is a no-op.
    """
    key = (phase, name)
    if key not in _registry:
        _registry[key] = stage_factory


def get(phase: str, name: str) -> PipelineStage:
    """Instantiate and return the stage for ``(phase, name)``.

    Raises:
        KeyError: If no stage is registered under the given key.
    """
    key = (phase, name)
    if key not in _registry:
        raise KeyError(f"No stage registered for phase='{phase}', name='{name}'")
    return _registry[key]()


def list_stages(phase: str | None = None) -> dict[str, PipelineStage]:
    """Return all registered stages, optionally filtered by *phase*.

    Returns:
        Dict mapping ``"phase/name"`` → instantiated ``PipelineStage``.
    """
    result: dict[str, PipelineStage] = {}
    for (p, n), factory in _registry.items():
        if phase is None or p == phase:
            result[f"{p}/{n}"] = factory()
    return result


def register_composite(
    name: str,
    stages: list[tuple[str, str]],
) -> None:
    """Register an ordered composite pipeline.

    Args:
        name: Composite key (e.g. ``"router_v6_full"``).
        stages: Ordered list of ``(phase, name)`` tuples.

    Idempotent — re-registering the same composite name is a no-op.
    """
    if name not in _composites:
        _composites[name] = stages


def get_composite(name: str) -> list[PipelineStage]:
    """Resolve and instantiate every stage in the named composite.

    Raises:
        KeyError: If the composite name is not registered.
    """
    if name not in _composites:
        raise KeyError(f"No composite registered: '{name}'")
    return [get(phase, stage_name) for phase, stage_name in _composites[name]]

"""Adapter that wraps any ``deterministic.stages.Stage`` subclass as a ``PipelineStage``.

A single function ``wrap_deterministic_stage()`` creates a closure that
translates ``StageInput.data`` (a ``BoardState``) → ``stage.run(state)`` →
``StageOutput(data=result)``.  The original stage is **not** modified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.deterministic.stages.base import Stage
    from temper_placer.protocol import PipelineStage, StageInput, StageOutput


class _WrappedDeterministicStage:
    """Protocol-compatible wrapper around a deterministic ``Stage``."""

    def __init__(
        self,
        stage: Stage,
        requires: list[str] | None = None,
        provides: list[str] | None = None,
    ) -> None:
        self._stage = stage
        self.name = stage.name
        self.requires: list[str] = requires or []
        self.provides: list[str] = provides or []
        self.contract = None

    def run(self, input: StageInput) -> StageOutput:
        from temper_placer.protocol import StageOutput

        state = input.data
        result = self._stage.run(state)
        return StageOutput(data=result, meta=input.meta)


def wrap_deterministic_stage(
    stage: Stage,
    *,
    requires: list[str] | None = None,
    provides: list[str] | None = None,
) -> PipelineStage:
    """Wrap a deterministic ``Stage`` so it satisfies ``PipelineStage``.

    Args:
        stage: Any subclass of ``deterministic.stages.base.Stage``.
        requires: Data-keys consumed (for data-flow validation).
        provides: Data-keys produced (for data-flow validation).

    Returns:
        An object that satisfies the ``PipelineStage`` Protocol.
        The original stage instance is not modified.
    """
    return _WrappedDeterministicStage(
        stage,
        requires=requires,
        provides=provides,
    )

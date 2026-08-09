"""Tests for deterministic_adapter.py — U7 coverage paydown."""

import pytest

from temper_placer.adapters.deterministic_adapter import (
    _WrappedDeterministicStage,
    wrap_deterministic_stage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.protocol import StageInput, StageMeta, StageOutput


# ---- Mock deterministic Stage ----

class _MockStage:
    """Minimal deterministic.stages.base.Stage-compatible mock."""

    def __init__(self, name: str = "mock_stage"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        """Return the state unchanged."""
        return state


class _MutatingStage:
    """A mock stage that returns a new state for verification."""

    def __init__(self, name: str = "mutator"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def run(self, state: BoardState) -> BoardState:
        # BoardState is frozen; return a replacement with config set.
        return BoardState(config="mutated")


# ---- wrap_deterministic_stage tests ----

def test_wrap_deterministic_stage_basic():
    """wrap_deterministic_stage returns a PipelineStage-compatible object."""
    mock = _MockStage()
    wrapped = wrap_deterministic_stage(mock)
    assert isinstance(wrapped, _WrappedDeterministicStage)
    assert wrapped.name == "mock_stage"
    assert wrapped.requires == []
    assert wrapped.provides == []
    assert wrapped.contract is None


def test_wrap_deterministic_stage_with_requires_provides():
    """Passing requires/provides is forwarded to the wrapper."""
    mock = _MockStage()
    wrapped = wrap_deterministic_stage(
        mock,
        requires=["parsed_pcb"],
        provides=["placements"],
    )
    assert wrapped.requires == ["parsed_pcb"]
    assert wrapped.provides == ["placements"]


def test_wrap_deterministic_stage_run():
    """Wrapped stage delegates to the inner Stage.run()."""
    mock = _MockStage()
    wrapped = wrap_deterministic_stage(mock)

    state = BoardState()
    meta = StageMeta(seed=42)
    inp = StageInput(data=state, meta=meta)

    result = wrapped.run(inp)
    assert isinstance(result, StageOutput)
    assert result.data is state
    assert result.meta is meta


def test_wrap_deterministic_stage_run_mutation():
    """Wrapped stage propagates mutations from inner Stage.run()."""
    mock = _MutatingStage()
    wrapped = wrap_deterministic_stage(mock)

    state = BoardState()
    inp = StageInput(data=state, meta=StageMeta())

    result = wrapped.run(inp)
    assert result.data is not state  # new state object returned
    assert result.data.config == "mutated"


def test_wrap_deterministic_stage_run_preserves_meta():
    """Meta is forwarded unchanged through the wrapper."""
    mock = _MockStage()
    wrapped = wrap_deterministic_stage(mock)

    meta = StageMeta(seed=99, timestamp=12345.0)
    meta.trace_context["key"] = "value"
    inp = StageInput(data=BoardState(), meta=meta)

    result = wrapped.run(inp)
    assert result.meta.seed == 99
    assert result.meta.timestamp == 12345.0
    assert result.meta.trace_context["key"] == "value"

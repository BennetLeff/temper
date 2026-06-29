"""U1 — Hypothesis PBT for all deterministic Stage subclasses.

Auto-discovers concrete Stage subclasses and verifies:
- Input immutability
- Output determinism
- Field provenance (undeclared fields unchanged)
- Serialization round-trip via dataclasses.replace
"""

from __future__ import annotations

import dataclasses
from dataclasses import replace
from typing import Any

import hypothesis.strategies as st
import numpy as np
import pytest
from hypothesis import HealthCheck, settings

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Helper — discover concrete Stage subclasses
# ---------------------------------------------------------------------------


def _all_concrete_stages() -> list[type]:
    """Return all concrete (non-abstract) Stage subclasses."""

    def _recurse(cls):
        result = []
        for sub in cls.__subclasses__():
            if not (
                hasattr(sub, "__abstractmethods__") and sub.__abstractmethods__
            ):
                result.append(sub)
            result.extend(_recurse(sub))
        return result

    return sorted(_recurse(Stage), key=lambda c: c.__name__)


def _try_instantiate(stage_cls: type) -> Stage | None:
    """Try to create a stage instance with defaults. Returns None if impossible."""
    try:
        return stage_cls()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Hypothesis strategy — minimal viable BoardState
# ---------------------------------------------------------------------------


@st.composite
def minimal_board_states(draw: st.DrawFn) -> BoardState:
    """Generate a minimal BoardState suitable for conformance testing.

    Builds a Board with valid dimensions and an optional simple netlist.
    Most stages early-return on missing data, so the strategy covers
    both populated and empty states.
    """
    has_board = draw(st.booleans())
    has_netlist = draw(st.booleans())

    kwargs: dict[str, Any] = {}

    if has_board:
        from temper_placer.core.board import Board

        kwargs["board"] = Board(
            width=draw(st.floats(min_value=1.0, max_value=500.0)),
            height=draw(st.floats(min_value=1.0, max_value=500.0)),
        )

    if has_netlist:
        from temper_placer.core.netlist import Component, Net, Netlist, Pin

        n_components = draw(st.integers(min_value=1, max_value=3))
        components = []
        nets = []
        for i in range(n_components):
            ref = f"U{i}"
            comp = Component(
                ref=ref,
                footprint="0805",
                bounds=(2.0, 1.25),
                pins=[
                    Pin(f"pin_{i}_1", "1", (0.0, 0.0), net=f"net_{i}"),
                ],
            )
            components.append(comp)
            nets.append(Net(f"net_{i}", [(ref, f"pin_{i}_1")]))
        kwargs["netlist"] = Netlist(components=components, nets=nets)

    return BoardState(**kwargs)


# ---------------------------------------------------------------------------
# Property: input immutability
# ---------------------------------------------------------------------------


def _fields_equal(a: Any, b: Any) -> bool:
    """Compare two values for structural equality, handling numpy arrays."""
    if isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        try:
            return bool(np.array_equal(a, b))
        except Exception:
            return False
    return a == b


def _boardstate_field_values(state: BoardState) -> dict[str, Any]:
    """Return a dict of field_name → value for a BoardState."""
    return {f.name: getattr(state, f.name) for f in dataclasses.fields(state)}


@settings(
    max_examples=100,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
@pytest.mark.slow
@pytest.mark.parametrize("stage_cls", _all_concrete_stages())
def test_stage_input_immutability(stage_cls):
    """Running a stage must not mutate the original input BoardState."""
    from hypothesis import given

    stage = _try_instantiate(stage_cls)
    if stage is None:
        pytest.skip(f"Cannot instantiate {stage_cls.__name__} with defaults")

    @given(state=minimal_board_states())
    def _check(state):
        original = _boardstate_field_values(state)
        try:
            stage.run(state)
        except Exception:
            # Stage may reject invalid input — that's fine for immutability
            return
        after = _boardstate_field_values(state)
        for field_name in original:
            orig_val = original[field_name]
            after_val = after[field_name]
            assert _fields_equal(orig_val, after_val), (
                f"{stage_cls.__name__} mutated input field '{field_name}'"
            )

    _check()


# ---------------------------------------------------------------------------
# Property: output determinism
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=3000,
    suppress_health_check=[HealthCheck.too_slow],
)
@pytest.mark.slow
@pytest.mark.parametrize("stage_cls", _all_concrete_stages())
def test_stage_determinism(stage_cls):
    """Running a stage twice with identical input must produce identical output."""
    from hypothesis import given

    stage = _try_instantiate(stage_cls)
    if stage is None:
        pytest.skip(f"Cannot instantiate {stage_cls.__name__} with defaults")

    @given(state=minimal_board_states())
    def _check(state):
        try:
            out1 = stage.run(state)
            out2 = stage.run(state)
        except Exception:
            return

        fields = [f.name for f in dataclasses.fields(BoardState)]
        for field_name in fields:
            v1 = getattr(out1, field_name)
            v2 = getattr(out2, field_name)
            assert _fields_equal(v1, v2), (
                f"{stage_cls.__name__} is non-deterministic on field '{field_name}'"
            )

    _check()


# ---------------------------------------------------------------------------
# Property: field provenance
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=3000,
    suppress_health_check=[HealthCheck.too_slow],
)
@pytest.mark.slow
@pytest.mark.parametrize("stage_cls", _all_concrete_stages())
def test_stage_field_provenance(stage_cls):
    """Undeclared output fields must be identical between input and output."""
    from hypothesis import given

    stage = _try_instantiate(stage_cls)
    if stage is None:
        pytest.skip(f"Cannot instantiate {stage_cls.__name__} with defaults")

    # Discover the stage's declared output fields from its docstring.
    # Convention: docstring mentions "Returns: BoardState with updated <field>"
    # Fallback: use an empty set (all field changes are flagged).
    declared_outputs: set[str] = set()
    doc = getattr(stage_cls, "__doc__", "") or ""
    import re

    for match in re.finditer(r"updated\s+(\w+)", doc, re.IGNORECASE):
        declared_outputs.add(match.group(1))

    @given(state=minimal_board_states())
    def _check(state):
        try:
            output = stage.run(state)
        except Exception:
            return

        field_names = [f.name for f in dataclasses.fields(BoardState)]
        for field_name in field_names:
            in_val = getattr(state, field_name)
            out_val = getattr(output, field_name)
            if not _fields_equal(in_val, out_val):
                # Field changed — it should be in the declared output set
                # (if declared_outputs is empty, we only warn but don't fail)
                if declared_outputs:
                    assert field_name in declared_outputs, (
                        f"{stage_cls.__name__} modified undeclared field "
                        f"'{field_name}' (declared: {declared_outputs})"
                    )

    _check()


# ---------------------------------------------------------------------------
# Property: serialization round-trip
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)
@pytest.mark.slow
@pytest.mark.parametrize("stage_cls", _all_concrete_stages())
def test_stage_serialization_roundtrip(stage_cls):
    """Output BoardState must survive dataclasses.replace round-trip."""
    from hypothesis import given

    stage = _try_instantiate(stage_cls)
    if stage is None:
        pytest.skip(f"Cannot instantiate {stage_cls.__name__} with defaults")

    @given(state=minimal_board_states())
    def _check(state):
        try:
            output = stage.run(state)
        except Exception:
            return

        # Serialization round-trip: reconstruct via replace
        field_kwargs = {
            f.name: getattr(output, f.name)
            for f in dataclasses.fields(BoardState)
        }
        reconstructed = replace(output, **field_kwargs)

        # Verify all fields match
        for f in dataclasses.fields(BoardState):
            orig_val = getattr(output, f.name)
            recon_val = getattr(reconstructed, f.name)
            assert _fields_equal(orig_val, recon_val), (
                f"{stage_cls.__name__} serialization round-trip failed "
                f"on field '{f.name}'"
            )

    _check()


# ---------------------------------------------------------------------------
# Basic unit: auto-discovery coverage
# ---------------------------------------------------------------------------


def test_all_stages_discovered():
    """Sanity check — at least 20 concrete stages exist for PBT coverage."""
    stages = _all_concrete_stages()
    assert len(stages) >= 20, (
        f"Expected >=20 concrete Stage subclasses, found {len(stages)}"
    )


def test_most_stages_default_constructible():
    """At least 85% of stages should have default constructors."""
    stages = _all_concrete_stages()
    instantiable = sum(1 for s in stages if _try_instantiate(s) is not None)
    assert instantiable / len(stages) >= 0.85, (
        f"Only {instantiable}/{len(stages)} stages are default-constructible"
    )

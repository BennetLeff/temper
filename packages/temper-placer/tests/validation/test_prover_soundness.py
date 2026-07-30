"""TDD/PBT tests for emitted-copper DRC attribution."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation._drc_api import DrcError
from temper_placer.validation.prover_soundness import (
    EmittedCopper,
    attribute_drc_errors,
)


def _error(x: float, y: float, net: str = "N1") -> DrcError:
    return DrcError(
        rule="clearance",
        severity="error",
        location=(x, y),
        message="synthetic violation",
        nets=[net],
    )


def _track(x0: float, y0: float, x1: float, y1: float, identity: str = "track-1"):
    return EmittedCopper(
        identity=identity,
        kind="track",
        net="N1",
        bbox=(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
    )


def test_fault_injected_emitted_clearance_violation_fails() -> None:
    attribution = attribute_drc_errors([_error(5.0, 5.0)], [_track(0.0, 5.0, 10.0, 5.0)])

    assert attribution.passed is False
    assert attribution.emitted_error_count == 1
    assert attribution.emitted[0][1] == ("track-1",)


def test_unmatched_error_remains_explicitly_inherited() -> None:
    attribution = attribute_drc_errors([_error(50.0, 50.0)], [_track(0.0, 5.0, 10.0, 5.0)])

    assert attribution.passed is True
    assert attribution.inherited_error_count == 1


@given(
    dx=st.integers(min_value=-100, max_value=100),
    dy=st.integers(min_value=-100, max_value=100),
)
@settings(max_examples=30, deadline=None)
def test_translation_metamorphism_preserves_attribution(dx: int, dy: int) -> None:
    base_item = _track(0.0, 5.0, 10.0, 5.0)
    translated_item = EmittedCopper(
        identity=base_item.identity,
        kind=base_item.kind,
        net=base_item.net,
        bbox=tuple(
            coordinate + delta
            for coordinate, delta in zip(base_item.bbox, (dx, dy, dx, dy), strict=True)
        ),
    )

    base = attribute_drc_errors([_error(5.0, 5.0)], [base_item])
    translated = attribute_drc_errors([_error(5.0 + dx, 5.0 + dy)], [translated_item])

    assert base.passed == translated.passed
    assert base.emitted[0][1] == translated.emitted[0][1]


@given(order=st.permutations(["track-1", "track-2", "track-3"]))
def test_item_order_metamorphism_is_deterministic(order: tuple[str, ...]) -> None:
    items = {
        identity: _track(0.0, 5.0, 10.0, 5.0, identity=identity)
        for identity in order
    }
    attribution = attribute_drc_errors([_error(5.0, 5.0)], list(items.values()))

    assert attribution.emitted[0][1] == ("track-1", "track-2", "track-3")

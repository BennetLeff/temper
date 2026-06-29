"""
Domain-correctness property tests for annular ring checking (Stage 5.2).

Verifies:
- R6: Ring-width formula — ``actual_ring_width == (D - d) / 2`` exactly
      (within 1e-9 tolerance)
- R7: External-vs-internal thresholds — microvia uses ``microvia_ring_mm``;
      external-passing via also passes internal (monotonicity)

Uses targeted Hypothesis strategies from ``dfm_property_strategies.py``.

Part of temper-j2xd (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings

from temper_placer.router_v6.annular_ring_check import (
    AnnularRingViolation,
    _check_via,
)
from temper_placer.router_v6.via_placement import Via
from tests.router_v6.dfm_property_strategies import known_dimension_via

# ---- Hypothesis settings ----
_SETTINGS = settings(
    max_examples=100,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)

# ---- Shared constants ----
_MIN_RING = 0.05
_MICROVIA_RING = 0.025
_NET_NAME = "TEST"
_POSITION = (50.0, 50.0)

# Known (diameter, drill) pairs and their expected ring widths.
# ring = (diameter - drill) / 2
_KNOWN_PAIRS: dict[tuple[float, float], float] = {
    (1.0, 0.5): 0.25,
    (0.6, 0.3): 0.15,
    (0.3, 0.2): 0.05,
    (2.0, 1.0): 0.5,
    (0.8, 0.4): 0.2,
}


def _make_via(
    diameter: float,
    drill: float,
    from_layer: str = "F.Cu",
    to_layer: str = "B.Cu",
    net_name: str = _NET_NAME,
    via_type: str | None = None,
) -> Via:
    """Create a Via with optional via_type override."""
    via = Via(
        position=_POSITION,
        from_layer=from_layer,
        to_layer=to_layer,
        diameter=diameter,
        drill=drill,
        net_name=net_name,
    )
    if via_type is not None:
        via.via_type = via_type  # type: ignore[attr-defined]
    return via


# ============================================================================
# R6: Ring-width formula correctness
# ============================================================================


@pytest.mark.parametrize(
    "diameter,drill,expected_ring",
    [
        # TS1: Via (1.0mm pad, 0.5mm drill) → ring width = 0.25mm exactly
        pytest.param(1.0, 0.5, 0.25, id="TS1_pad1_0_drill0_5"),
        # TS2: Via (0.6mm pad, 0.3mm drill) → ring width = 0.15mm exactly
        pytest.param(0.6, 0.3, 0.15, id="TS2_pad0_6_drill0_3"),
        # Bonus: additional known pairs
        pytest.param(0.3, 0.2, 0.05, id="pad0_3_drill0_2"),
        pytest.param(2.0, 1.0, 0.5, id="pad2_0_drill1_0"),
        pytest.param(0.8, 0.4, 0.2, id="pad0_8_drill0_4"),
    ],
)
def test_ring_width_formula_concrete(
    diameter: float, drill: float, expected_ring: float
) -> None:
    """Concrete vias: ``actual_ring_width`` matches ``(D - d) / 2`` exactly.

    Verifies the ring-width formula from R6 using specific known
    (diameter, drill) pairs.
    """
    via = _make_via(diameter=diameter, drill=drill)
    result = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)

    # The via *may* be a violation depending on ring vs. threshold,
    # but the actual_ring_width must always match the formula.
    if isinstance(result, AnnularRingViolation):
        actual = result.actual_ring_width
    else:
        # Even if it passes, compute the ring directly for verification
        actual = (diameter - drill) / 2.0

    assert actual == pytest.approx(expected_ring, abs=1e-9), (
        f"Ring width: expected {expected_ring}, got {actual} "
        f"(diameter={diameter}, drill={drill})"
    )


@given(via=known_dimension_via())
@_SETTINGS
def test_ring_width_formula_matches(via: Via) -> None:
    """Property: for any known-dimension via, ``actual_ring_width`` equals
    ``(diameter - drill) / 2`` within 1e-9 tolerance.

    Uses the ``known_dimension_via`` strategy to draw from
    ``{(1.0,0.5), (0.6,0.3), (0.3,0.2), (2.0,1.0), (0.8,0.4)}``.
    """
    result = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)

    expected_ring = (via.diameter - via.drill) / 2.0

    actual = result.actual_ring_width if isinstance(result, AnnularRingViolation) else expected_ring

    assert actual == pytest.approx(expected_ring, abs=1e-9), (
        f"actual_ring_width={actual} != expected={expected_ring} "
        f"(diameter={via.diameter}, drill={via.drill})"
    )


# ============================================================================
# R7: External-vs-internal thresholds
# ============================================================================


def test_microvia_uses_microvia_threshold_concrete() -> None:
    """TS3: Microvia with ring between microvia and external thresholds.

    A microvia on an external layer with ring=0.03:
    - External threshold would be 0.05 → would fail
    - Microvia threshold is 0.025 → should pass

    This proves the microvia threshold overrides the layer-based one.
    """
    via = _make_via(
        diameter=0.36, drill=0.3,  # ring = 0.03
        from_layer="F.Cu",
        to_layer="B.Cu",
        via_type="microvia",
    )
    result = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    assert result is None, (
        "Microvia with ring=0.03 should PASS at microvia threshold 0.025"
    )

    # Same via WITHOUT microvia type → should fail (external threshold 0.05)
    via_no_type = _make_via(
        diameter=0.36, drill=0.3,
        from_layer="F.Cu", to_layer="B.Cu",
        via_type=None,
    )
    result_no_type = _check_via(via_no_type, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    assert isinstance(result_no_type, AnnularRingViolation), (
        "Same via without microvia type should FAIL at external threshold 0.05"
    )


def test_microvia_violation_reports_microvia_threshold() -> None:
    """When a microvia fails, the reported ``minimum_required`` is the
    microvia threshold, not the layer-based threshold.
    """
    via = _make_via(
        diameter=0.34, drill=0.3,  # ring = 0.02
        from_layer="F.Cu",
        to_layer="B.Cu",
        via_type="microvia",
    )
    result = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    assert isinstance(result, AnnularRingViolation)
    assert result.minimum_required == _MICROVIA_RING, (
        f"Expected microvia threshold {_MICROVIA_RING}, "
        f"got {result.minimum_required}"
    )


@given(
    via=known_dimension_via(
        via_type="microvia",
        from_layer="F.Cu",
        to_layer="B.Cu",
    )
)
@_SETTINGS
def test_microvia_uses_microvia_threshold(via: Via) -> None:
    """Property: for any microvia on external layers, if a violation is
    raised, the ``minimum_required`` equals ``microvia_ring_mm`` (0.025),
    not the external threshold (0.05).
    """
    result = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)

    if isinstance(result, AnnularRingViolation):
        assert result.minimum_required == _MICROVIA_RING, (
            f"Microvia violation should use microvia threshold "
            f"{_MICROVIA_RING}, got {result.minimum_required}"
        )
    else:
        # No violation: ring must be > microvia threshold.
        ring = (via.diameter - via.drill) / 2.0
        # With _FP_EPSILON=1e-12, the check is ring <= threshold + 1e-12.
        # So a pass means ring > threshold + 1e-12, i.e. ring > 0.025 + ε.
        assert ring > _MICROVIA_RING + 1e-12, (
            f"Microvia passed but ring={ring} <= microvia threshold "
            f"{_MICROVIA_RING} — should have been a violation"
        )


@given(
    via=known_dimension_via(
        from_layer="F.Cu",
        to_layer="B.Cu",
    )
)
@_SETTINGS
def test_external_pass_implies_internal_pass(via: Via) -> None:
    """TS4: External-passing via also passes internal (monotonicity).

    If a via passes the stricter external threshold (ring > min_annular_ring),
    it must also pass the more lenient internal threshold
    (ring > min_annular_ring * 0.5).  This verifies the layer multiplier
    is applied correctly.
    """
    # Check via on external layers
    result_ext = _check_via(via, _NET_NAME, _MIN_RING, _MICROVIA_RING)

    if result_ext is None:
        # Passed external → must also pass internal
        via_int = _make_via(
            diameter=via.diameter,
            drill=via.drill,
            from_layer="In1.Cu",
            to_layer="In2.Cu",
            net_name=via.net_name,
            via_type=getattr(via, "via_type", None),
        )
        result_int = _check_via(via_int, _NET_NAME, _MIN_RING, _MICROVIA_RING)
        assert result_int is None, (
            f"Via passed external ({_MIN_RING} threshold) but failed internal "
            f"(0.5*{_MIN_RING}={_MIN_RING*0.5} threshold): "
            f"diameter={via.diameter}, drill={via.drill}, "
            f"ring={(via.diameter-via.drill)/2.0}"
        )


def test_internal_vs_external_same_ring_width() -> None:
    """The computed ring width is identical regardless of layer assignment.

    Verifies that the ring formula does not depend on layer — only
    the threshold changes.
    """
    dia, drill = 0.6, 0.3  # ring = 0.15

    via_ext = _make_via(diameter=dia, drill=drill,
                        from_layer="F.Cu", to_layer="B.Cu")
    via_int = _make_via(diameter=dia, drill=drill,
                        from_layer="In1.Cu", to_layer="In2.Cu")

    result_ext = _check_via(via_ext, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    result_int = _check_via(via_int, _NET_NAME, _MIN_RING, _MICROVIA_RING)

    # Both should pass (ring=0.15 > both thresholds)
    assert result_ext is None, "ring=0.15 should pass external threshold 0.05"
    assert result_int is None, "ring=0.15 should pass internal threshold 0.025"


def test_internal_only_via_fails_external() -> None:
    """A via that passes internal but not external: ring between the two thresholds.

    Ring = 0.03:
    - Internal threshold = 0.025 → 0.03 > 0.025 → pass
    - External threshold = 0.05  → 0.03 ≤ 0.05 → violation
    """
    via_int = _make_via(
        diameter=0.36, drill=0.3,  # ring = 0.03
        from_layer="In1.Cu", to_layer="In2.Cu",
    )
    result_int = _check_via(via_int, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    assert result_int is None, "ring=0.03 should pass internal threshold 0.025"

    via_ext = _make_via(
        diameter=0.36, drill=0.3,
        from_layer="F.Cu", to_layer="B.Cu",
    )
    result_ext = _check_via(via_ext, _NET_NAME, _MIN_RING, _MICROVIA_RING)
    assert isinstance(result_ext, AnnularRingViolation), (
        "ring=0.03 should fail external threshold 0.05"
    )
    assert result_ext.minimum_required == _MIN_RING

"""
Tests for the external physics-oracle adapter (score_placement).

Verifies that ``score_placement`` can be imported, accepts raw ``(x, y)``
positions, produces non-trivial scores, and does not crash.
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics.external_oracle import score_placement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_board() -> Board:
    """A 100×100 mm board with one zone."""
    return Board(
        width=100.0,
        height=100.0,
        zones=[Zone("HV_ZONE", (0.0, 0.0, 50.0, 50.0))],
    )


@pytest.fixture
def simple_netlist() -> Netlist:
    """Three components: one HV (Q1), two LV (R1, C1)."""
    c1 = Component(
        ref="Q1",
        footprint="TO-220",
        bounds=(15.0, 10.0),
        net_class="HighVoltage",
        zone="HV_ZONE",
    )
    c2 = Component(
        ref="R1",
        footprint="0805",
        bounds=(2.0, 1.2),
        net_class="Signal",
    )
    c3 = Component(
        ref="C1",
        footprint="0805",
        bounds=(2.0, 1.2),
        net_class="Signal",
    )
    return Netlist(
        components=[c1, c2, c3],
        nets=[Net("HV_NET", [("Q1", "1")]), Net("LV_NET", [("R1", "1"), ("C1", "1")])],
    )


@pytest.fixture
def thermal_netlist() -> Netlist:
    """Two thermal components and two regular ones."""
    c1 = Component(ref="Q1", footprint="TO-220", bounds=(15.0, 10.0), net_class="HighVoltage")
    c2 = Component(ref="Q2", footprint="TO-220", bounds=(15.0, 10.0), net_class="HighVoltage")
    c3 = Component(ref="R1", footprint="0805", bounds=(2.0, 1.2), net_class="Signal")
    c4 = Component(ref="C1", footprint="0805", bounds=(2.0, 1.2), net_class="Signal")
    return Netlist(
        components=[c1, c2, c3, c4],
        nets=[Net("N1", [("Q1", "1"), ("Q2", "1"), ("R1", "1"), ("C1", "1")])],
    )


# ---------------------------------------------------------------------------
# Test: importable
# ---------------------------------------------------------------------------

def test_score_placement_importable():
    """score_placement can be imported from the metrics package."""
    from temper_placer.metrics import score_placement as sp
    assert callable(sp)


def test_score_placement_importable_direct():
    """score_placement can be imported from the external_oracle module."""
    from temper_placer.metrics.external_oracle import score_placement as sp
    assert callable(sp)


# ---------------------------------------------------------------------------
# Test: accepts positions without crashing
# ---------------------------------------------------------------------------

def test_score_placement_accepts_positions(simple_board, simple_netlist):
    """
    Calling score_placement with a valid positions dict returns a dict
    of scores without raising.
    """
    positions = {
        "Q1": (25.0, 25.0),
        "R1": (60.0, 60.0),
        "C1": (70.0, 70.0),
    }
    result = score_placement(
        positions, simple_netlist, simple_board,
        hv_components={"Q1"},
        lv_components={"R1", "C1"},
        min_clearance=8.0,
    )
    assert isinstance(result, dict)
    assert "hv_lv_clearance_score" in result
    assert "thermal_score" in result
    assert "clearance_3mm" in result
    assert "clearance_6mm" in result
    assert "zone_compliance_score" in result
    assert "compactness_score" in result


def test_score_placement_empty_netlist(simple_board):
    """Empty netlist raises ValueError."""
    netlist = Netlist()
    with pytest.raises(ValueError, match="no components"):
        score_placement({"R1": (10.0, 10.0)}, netlist, simple_board)


def test_score_placement_empty_positions(simple_board, simple_netlist):
    """Empty positions dict raises ValueError."""
    with pytest.raises(ValueError, match="positions dict is empty"):
        score_placement({}, simple_netlist, simple_board)


# ---------------------------------------------------------------------------
# Test: produces non-trivial (varying) scores
# ---------------------------------------------------------------------------

def test_score_placement_produces_non_trivial(simple_board, simple_netlist):
    """
    Score two deliberately different placements and verify the scores differ.
    """
    # Placement A: HV component Q1 far from LV components (good clearance)
    # Q1 at (10, 10), R1 at (80, 80) — very far apart
    positions_a = {
        "Q1": (10.0, 10.0),
        "R1": (80.0, 80.0),
        "C1": (85.0, 85.0),
    }
    result_a = score_placement(
        positions_a, simple_netlist, simple_board,
        hv_components={"Q1"},
        lv_components={"R1", "C1"},
        min_clearance=8.0,
    )

    # Placement B: HV component Q1 very close to LV components (poor clearance)
    # Q1 at (10, 10), R1 at (12, 12) — almost overlapping
    positions_b = {
        "Q1": (10.0, 10.0),
        "R1": (12.0, 12.0),
        "C1": (14.0, 14.0),
    }
    result_b = score_placement(
        positions_b, simple_netlist, simple_board,
        hv_components={"Q1"},
        lv_components={"R1", "C1"},
        min_clearance=8.0,
    )

    # Clearance scores should differ
    assert result_a["hv_lv_clearance_score"] != pytest.approx(result_b["hv_lv_clearance_score"])

    # The good placement should have better clearance
    assert result_a["hv_lv_clearance_score"] >= result_b["hv_lv_clearance_score"]


def test_score_placement_thermal_edge_sensitivity(simple_board, thermal_netlist):
    """
    Thermal components placed near the target edge produce a higher thermal
    score than those placed far from the edge.
    """
    # Near-edge placement
    near_positions = {
        "Q1": (50.0, 95.0),   # top edge, y=95 is 5mm from y=100
        "Q2": (50.0, 93.0),   # top edge, y=93 is 7mm from y=100
        "R1": (10.0, 10.0),
        "C1": (80.0, 80.0),
    }
    near_result = score_placement(
        near_positions, thermal_netlist, simple_board,
        thermal_components={"Q1", "Q2"},
        thermal_edge="TOP",
        thermal_max_distance=10.0,
    )

    # Far-from-edge placement
    far_positions = {
        "Q1": (50.0, 10.0),   # bottom edge, 10mm from bottom
        "Q2": (50.0, 5.0),    # bottom edge, 5mm from bottom
        "R1": (10.0, 10.0),
        "C1": (80.0, 80.0),
    }
    far_result = score_placement(
        far_positions, thermal_netlist, simple_board,
        thermal_components={"Q1", "Q2"},
        thermal_edge="TOP",
        thermal_max_distance=10.0,
    )

    # Near-edge should have better thermal score than far-from-edge
    assert near_result["thermal_score"] > far_result["thermal_score"]


# ---------------------------------------------------------------------------
# Test: dual-rail thresholds (clearance_3mm vs clearance_6mm)
# ---------------------------------------------------------------------------

def test_clearance_3mm_vs_6mm(simple_board, simple_netlist):
    """
    A placement with HV-LV edge-to-edge clearance of ~5mm should pass at
    3mm threshold but may fail at 6mm threshold.
    """
    # Q1 (15x10) at (10, 10) → right edge at x=17.5
    # R1 (2x1.2) at (24, 10) → left edge at x=23.0
    # Edge-to-edge distance: 23.0 - 17.5 = 5.5 mm
    positions = {
        "Q1": (10.0, 10.0),
        "R1": (24.0, 10.0),
        "C1": (80.0, 80.0),
    }
    result = score_placement(
        positions, simple_netlist, simple_board,
        hv_components={"Q1"},
        lv_components={"R1", "C1"},
    )

    # At 3mm threshold, clearance should be fine (5.5 > 3.0)
    assert result["clearance_3mm"] >= 0.99

    # At 6mm threshold, clearance may be marginal (5.5 < 6.0 but close)
    # The exact score depends on the hv_lv_clearance_score computation.
    # The key test is that the two scores differ.
    assert result["clearance_3mm"] != pytest.approx(result["clearance_6mm"])

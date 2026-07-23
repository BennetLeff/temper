"""
Tests for Router V6 functional 4-layer power-plane geometry (W2 / U4).

Covers generate_ground_pour, generate_power_pours, generate_thermal_vias,
and the generate_power_planes orchestrator.
"""

import pytest

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component
from temper_placer.router_v6.power_plane import (
    DEFAULT_POWER_DOMAINS,
    THERMAL_NET,
    CopperPour,
    PowerPlaneGeometry,
    generate_ground_pour,
    generate_power_planes,
    generate_power_pours,
    generate_thermal_vias,
)


def _board(width=100.0, height=80.0, origin=(0.0, 0.0)) -> Board:
    return Board(
        width=width,
        height=height,
        origin=origin,
        layer_stackup=LayerStackup.default_4layer(),
    )


def _igbt(ref: str, position: tuple[float, float]) -> Component:
    return Component(
        ref=ref,
        footprint="Package_TO_SOT_THT:TO-247-3_Vertical",
        bounds=(16.0, 20.0),
        initial_position=position,
    )


# --------------------------------------------------------------------------
# generate_ground_pour
# --------------------------------------------------------------------------


def test_ground_pour_covers_board():
    board = _board(width=100.0, height=80.0, origin=(5.0, 10.0))
    pour = generate_ground_pour(board)

    assert pour.net == "GND"
    assert pour.layer == "In1.Cu"
    assert pour.is_ground is True
    assert pour.bounds == (5.0, 10.0, 105.0, 90.0)
    assert pour.area == pytest.approx(100.0 * 80.0)
    assert len(pour.polygon) == 4


def test_ground_pour_custom_layer():
    pour = generate_ground_pour(_board(), layer="GND")
    assert pour.layer == "GND"


# --------------------------------------------------------------------------
# generate_power_pours
# --------------------------------------------------------------------------


def test_power_pours_default_domains():
    board = _board(width=100.0, height=80.0)
    pours = generate_power_pours(board)

    assert [p.net for p in pours] == list(DEFAULT_POWER_DOMAINS)
    assert all(p.layer == "In2.Cu" for p in pours)
    assert len(pours) == 3


def test_power_pours_are_isolated():
    board = _board(width=100.0, height=80.0)
    gap = 0.5
    pours = generate_power_pours(board, isolation_gap_mm=gap)

    # Adjacent pours must be separated by at least the isolation gap.
    for left, right in zip(pours, pours[1:]):
        assert right.bounds[0] - left.bounds[2] == pytest.approx(gap)


def test_power_pours_span_board_width():
    board = _board(width=100.0, height=80.0, origin=(0.0, 0.0))
    pours = generate_power_pours(board, isolation_gap_mm=0.0)

    # With no gap the strips tile the full width.
    total = sum(p.width for p in pours)
    assert total == pytest.approx(100.0)
    assert pours[0].bounds[0] == pytest.approx(0.0)
    assert pours[-1].bounds[2] == pytest.approx(100.0)


def test_power_pours_custom_domains():
    pours = generate_power_pours(_board(), domains=["+12V", "-12V"])
    assert [p.net for p in pours] == ["+12V", "-12V"]


def test_power_pours_empty_domains():
    assert generate_power_pours(_board(), domains=[]) == []


def test_power_pours_negative_gap_raises():
    with pytest.raises(ValueError, match="isolation_gap_mm"):
        generate_power_pours(_board(), isolation_gap_mm=-1.0)


def test_power_pours_board_too_narrow_raises():
    board = _board(width=1.0, height=80.0)
    with pytest.raises(ValueError, match="too narrow"):
        generate_power_pours(board, isolation_gap_mm=1.0)


# --------------------------------------------------------------------------
# generate_thermal_vias
# --------------------------------------------------------------------------


def test_thermal_vias_3x3_under_each_igbt():
    board = _board()
    comps = [_igbt("Q1", (30.0, 40.0)), _igbt("Q2", (70.0, 40.0))]
    vias = generate_thermal_vias(board, comps)

    # 3x3 under each of Q1, Q2.
    assert len(vias) == 18
    q1_vias = [v for v in vias if abs(v.position[0] - 30.0) <= 3.0]
    assert len(q1_vias) == 9


def test_thermal_vias_dimensions_and_layers():
    board = _board()
    vias = generate_thermal_vias(board, [_igbt("Q1", (30.0, 40.0))])

    for via in vias:
        assert via.drill == 0.3
        assert via.width == 0.6
        assert via.layers == ("F.Cu", "B.Cu")
        assert via.net == THERMAL_NET


def test_thermal_vias_centered_on_component():
    board = _board()
    vias = generate_thermal_vias(board, [_igbt("Q1", (30.0, 40.0))], pitch_mm=1.0)
    xs = [v.position[0] for v in vias]
    ys = [v.position[1] for v in vias]
    # 3x3 grid, pitch 1.0 -> centroid at component centre.
    assert sum(xs) / len(xs) == pytest.approx(30.0)
    assert sum(ys) / len(ys) == pytest.approx(40.0)
    assert min(xs) == pytest.approx(29.0)
    assert max(xs) == pytest.approx(31.0)


def test_thermal_vias_ignores_non_igbt():
    board = _board()
    comps = [
        _igbt("Q1", (30.0, 40.0)),
        Component(ref="R5", footprint="R_0805", bounds=(2.0, 1.2), initial_position=(10.0, 10.0)),
    ]
    vias = generate_thermal_vias(board, comps)
    assert len(vias) == 9


def test_thermal_vias_skips_unplaced_component():
    board = _board()
    comp = Component(ref="Q1", footprint="TO-247", bounds=(16.0, 20.0), initial_position=None)
    assert generate_thermal_vias(board, [comp]) == []


def test_thermal_vias_non_square_count_raises():
    board = _board()
    with pytest.raises(ValueError, match="perfect square"):
        generate_thermal_vias(board, [_igbt("Q1", (30.0, 40.0))], count=8)


def test_thermal_vias_bad_diameter_raises():
    board = _board()
    with pytest.raises(ValueError, match="must exceed"):
        generate_thermal_vias(board, [_igbt("Q1", (30.0, 40.0))], diameter_mm=0.3, drill_mm=0.3)


def test_thermal_vias_custom_count_4():
    board = _board()
    vias = generate_thermal_vias(board, [_igbt("Q1", (30.0, 40.0))], count=4)
    assert len(vias) == 4


# --------------------------------------------------------------------------
# generate_power_planes orchestrator
# --------------------------------------------------------------------------


def test_generate_power_planes_bundles_geometry():
    board = _board()
    comps = [_igbt("Q1", (30.0, 40.0)), _igbt("Q2", (70.0, 40.0))]
    geometry = generate_power_planes(board, comps)

    assert isinstance(geometry, PowerPlaneGeometry)
    assert geometry.ground_pour.net == "GND"
    assert geometry.ground_pour.layer == "In1.Cu"
    assert len(geometry.power_pours) == 3
    assert geometry.via_count == 18


def test_generate_power_planes_deterministic():
    board = _board()
    comps = [_igbt("Q1", (30.0, 40.0)), _igbt("Q2", (70.0, 40.0))]
    a = generate_power_planes(board, comps)
    b = generate_power_planes(board, comps)

    assert a.ground_pour == b.ground_pour
    assert a.power_pours == b.power_pours
    assert a.thermal_vias == b.thermal_vias


def test_copper_pour_is_frozen():
    from dataclasses import FrozenInstanceError

    pour = CopperPour(net="GND", layer="In1.Cu", bounds=(0, 0, 1, 1))
    with pytest.raises(FrozenInstanceError):
        pour.net = "+5V"  # type: ignore[misc]

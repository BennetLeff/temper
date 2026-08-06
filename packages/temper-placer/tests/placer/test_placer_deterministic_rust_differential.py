"""Differential tests: ``placer/deterministic.py`` compute vs the pinned oracle.

Wave 4 Phase 4: the per-component placement compute of
``place_power_stage_template``, ``place_by_proximity`` and
``place_in_zone_center`` moved to
``temper-io-types/placer_core/placer_compute.rs`` (exposed as
``temper_io_types.placer_place_power_stage_template``,
``placer_place_by_proximity``, ``placer_place_in_zone_center``). The
oracle is the verbatim pre-migration module in
``tests/placer/_placer_py_oracle/deterministic.py``.

Bit-exactness notes:
- Positions/rotations are float32 arrays in the oracle; every ``positions[idx] =
  [x, y]`` is an f64->f32 store, reproduced as ``x as f32`` in the kernel and
  compared via ``tobytes()`` (dtype included).
- ``place_by_proximity`` uses ``math.cos``/``math.sin`` of the spiral
  angle -- a Python seam (``(cos, sin)`` callable) the kernel calls back
  into, preserving the oracle's libm bits.
- ``place_by_proximity``'s ``max_distance`` branch is a literal no-op in
  the oracle (``if distance > max_distance: pass``); the differential
  drives ``max_distance`` across values and asserts the shim is invariant
  to it, pinning the dead parameter.
- ``place_in_zone_center``'s ``grid_size = ceil(sqrt(len))`` is
  ``((len as f64).sqrt()).ceil()`` (IEEE correctly-rounded sqrt/ceil,
  bit-identical to ``math.sqrt``/``math.ceil``).
- Zone clamping uses CPython's ``min``/``max`` first-arg-on-tie semantics
  (``py_min``/``py_max`` in the kernel).
- The #763-fixed ``place_by_proximity`` spiral runs at function level
  regardless of ``zone_name``; the ``zone_name=None`` path must produce a
  non-empty placement (this differential's no-zone arms pin it).

RED state: this file fails to collect with ``AttributeError: module
'temper_io_types' has no attribute 'placer_place_by_proximity'`` until the
Rust kernels land (the TDD-RED evidence).
"""

from __future__ import annotations

import numpy as np
import pytest

import temper_io_types as _t

from temper_placer.placer.deterministic import (
    place_by_proximity,
    place_in_zone_center,
    place_power_stage_template,
)
from temper_placer.placer.template import ComponentPosition, ComponentTemplate
from tests.placer._placer_diff import assert_result_equal, assert_array_identical
from tests.placer._placer_fixtures import power_board, power_netlist
from tests.placer._placer_py_oracle import deterministic as oracle
from tests.placer._placer_py_oracle import template as oracle_template

# The Rust surface this differential pins. Imported at module level so the
# RED state is a collection failure (AttributeError) before the kernels
# land, per the TDD convention.
placer_place_power_stage_template = _t.placer_place_power_stage_template
placer_place_by_proximity = _t.placer_place_by_proximity
placer_place_in_zone_center = _t.placer_place_in_zone_center

COMPONENT_REFS = ["Q1", "Q2", "D1", "D2", "C1", "U1"]


def _hb(comps, anchor="Q1"):
    return ComponentTemplate(
        name="test_hb",
        components=[ComponentPosition(c.ref, c.x, c.y, c.rotation) for c in comps],
        anchor_point=anchor,
    )


def _oracle_hb(comps, anchor="Q1"):
    return oracle_template.ComponentTemplate(
        name="test_hb",
        components=[oracle_template.ComponentPosition(c.ref, c.x, c.y, c.rotation) for c in comps],
        anchor_point=anchor,
    )


def _cos_sin(theta):
    import math

    return (math.cos(theta), math.sin(theta))


@pytest.fixture
def hb_components():
    return [
        ComponentPosition("Q1", 0, 0, 0),
        ComponentPosition("Q2", 0, -20, 0),
        ComponentPosition("D1", 10, 0, 0),
        ComponentPosition("D2", 10, -20, 0),
    ]


# ---------------------------------------------------------------------------
# place_power_stage_template
# ---------------------------------------------------------------------------


def test_place_power_stage_template_defaults(hb_components):
    board, netlist = power_board(), power_netlist()
    prod = place_power_stage_template(netlist, board, _hb(hb_components), zone_name="power_zone")
    ref = oracle.place_power_stage_template(
        netlist, board, _oracle_hb(hb_components), zone_name="power_zone"
    )
    assert_result_equal(prod, ref)
    np.testing.assert_allclose(prod.positions[0], [25.0, 25.0])
    np.testing.assert_allclose(prod.positions[1], [25.0, 5.0])


def test_place_power_stage_template_with_initial_positions(hb_components):
    board, netlist = power_board(), power_netlist()
    initial = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0], [9.0, 10.0], [11.0, 12.0]])
    prod = place_power_stage_template(
        netlist, board, _hb(hb_components), zone_name="power_zone", initial_positions=initial
    )
    ref = oracle.place_power_stage_template(
        netlist, board, _oracle_hb(hb_components), zone_name="power_zone", initial_positions=initial
    )
    assert_result_equal(prod, ref)


def test_place_power_stage_template_initial_float64_cast(hb_components):
    # initial_positions as float64 -> np.array(..., dtype=float32) cast on
    # both arms; the tobytes comparison pins the cast.
    board, netlist = power_board(), power_netlist()
    initial = np.array([[0.123456789, 0.987654321]] * 6)
    assert initial.dtype == np.float64
    prod = place_power_stage_template(
        netlist, board, _hb(hb_components), zone_name="power_zone", initial_positions=initial
    )
    ref = oracle.place_power_stage_template(
        netlist, board, _oracle_hb(hb_components), zone_name="power_zone", initial_positions=initial
    )
    assert_result_equal(prod, ref)


def test_place_power_stage_template_zone_missing_raises(hb_components):
    board, netlist = power_board(), power_netlist()
    with pytest.raises(ValueError, match="not found in board"):
        place_power_stage_template(netlist, board, _hb(hb_components), zone_name="nope")
    with pytest.raises(ValueError, match="not found in board"):
        oracle.place_power_stage_template(netlist, board, _oracle_hb(hb_components), zone_name="nope")


def test_place_power_stage_template_partial_template(hb_components):
    # Template missing some components -> those keep zeros / land in
    # unplaced_refs.
    board, netlist = power_board(), power_netlist()
    partial = [c for c in hb_components if c.ref != "D2"]
    prod = place_power_stage_template(netlist, board, _hb(partial), zone_name="power_zone")
    ref = oracle.place_power_stage_template(
        netlist, board, _oracle_hb(partial), zone_name="power_zone"
    )
    assert_result_equal(prod, ref)
    assert "D2" in prod.unplaced_refs


# ---------------------------------------------------------------------------
# place_by_proximity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("max_distance", [1.0, 8.0, 15.0, 100.0])
def test_place_by_proximity_no_zone(max_distance):
    # The #763 fix: the spiral must run on the zone_name=None path.
    board, netlist = power_board(), power_netlist()
    prod = place_by_proximity(
        netlist, board, "U1", ["C1", "D1"], max_distance=max_distance
    )
    ref = oracle.place_by_proximity(
        netlist, board, "U1", ["C1", "D1"], max_distance=max_distance
    )
    assert_result_equal(prod, ref)
    assert "C1" in prod.placed_refs  # non-vacuous: the spiral ran


def test_place_by_proximity_with_zone(hb_components):
    board, netlist = power_board(), power_netlist()
    prod = place_by_proximity(
        netlist, board, "U1", ["C1", "D1", "Q1", "Q2"], zone_name="power_zone"
    )
    ref = oracle.place_by_proximity(
        netlist, board, "U1", ["C1", "D1", "Q1", "Q2"], zone_name="power_zone"
    )
    assert_result_equal(prod, ref)


def test_place_by_proximity_many_refs():
    # 9 refs -> angle_step smaller than pi/2; several spiral rings (i//4).
    board, netlist = power_board(), power_netlist()
    refs = ["C1", "D1", "Q1", "Q2", "D2", "U1", "C1", "D1", "Q1"]
    prod = place_by_proximity(netlist, board, "U1", refs)
    ref = oracle.place_by_proximity(netlist, board, "U1", refs)
    assert_result_equal(prod, ref)


def test_place_by_proximity_missing_target_raises():
    board, netlist = power_board(), power_netlist()
    with pytest.raises(ValueError, match="not found"):
        place_by_proximity(netlist, board, "ZZZ", ["C1"])
    with pytest.raises(ValueError, match="not found"):
        oracle.place_by_proximity(netlist, board, "ZZZ", ["C1"])


def test_place_by_proximity_ref_not_in_netlist():
    board, netlist = power_board(), power_netlist()
    prod = place_by_proximity(netlist, board, "U1", ["C1", "MISSING", "D1"])
    ref = oracle.place_by_proximity(netlist, board, "U1", ["C1", "MISSING", "D1"])
    assert_result_equal(prod, ref)
    assert "MISSING" in prod.unplaced_refs


def test_place_by_proximity_empty_refs():
    board, netlist = power_board(), power_netlist()
    prod = place_by_proximity(netlist, board, "U1", [])
    ref = oracle.place_by_proximity(netlist, board, "U1", [])
    assert_result_equal(prod, ref)


def test_place_by_proximity_board_center():
    # No zone -> base at board.center; also exercises nonzero board dims.
    board = power_board()
    board.width = 200.0
    board.height = 60.0
    netlist = power_netlist()
    prod = place_by_proximity(netlist, board, "U1", ["C1", "D1"])
    ref = oracle.place_by_proximity(netlist, board, "U1", ["C1", "D1"])
    assert_result_equal(prod, ref)


def test_place_by_proximity_kernel_matches_oracle():
    # Direct kernel-vs-oracle pin (bypassing the shim): the kernel's raw
    # flat positions + placed/unplaced lists must equal what the oracle
    # computes, given the same inputs the shim marshals.
    board, netlist = power_board(), power_netlist()
    ref = oracle.place_by_proximity(netlist, board, "U1", ["C1", "D1", "MISSING"], zone_name="power_zone")
    base_x = (board.zones[0].bounds[0] + board.zones[0].bounds[2]) / 2
    base_y = (board.zones[0].bounds[1] + board.zones[0].bounds[3]) / 2
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    refs = ["C1", "D1", "MISSING"]
    indices = [ref_to_idx.get(r) for r in refs]
    flat, placed, unplaced = placer_place_by_proximity(
        netlist.n_components, refs, indices, base_x, base_y, board.zones[0].bounds, _cos_sin
    )
    assert list(placed) == list(ref.placed_refs)
    assert list(unplaced) == list(ref.unplaced_refs)
    assert_array_identical(np.asarray(flat, dtype=np.float32).reshape(netlist.n_components, 2), ref.positions)


# ---------------------------------------------------------------------------
# place_in_zone_center
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("refs", [["U1"], ["U1", "C1"], ["U1", "C1", "Q1"], ["U1"] * 5, ["U1"] * 9])
def test_place_in_zone_center_matches(refs):
    board, netlist = power_board(), power_netlist()
    prod = place_in_zone_center(netlist, board, refs, "logic_zone")
    ref = oracle.place_in_zone_center(netlist, board, refs, "logic_zone")
    assert_result_equal(prod, ref)


def test_place_in_zone_center_clamps_to_zone():
    # Many refs -> grid spills beyond the zone; clamping must kick in.
    board = power_board()
    netlist = power_netlist()
    refs = ["U1", "C1", "Q1", "Q2", "D1", "D2"] * 3
    prod = place_in_zone_center(netlist, board, refs, "logic_zone")
    ref = oracle.place_in_zone_center(netlist, board, refs, "logic_zone")
    assert_result_equal(prod, ref)
    pos = prod.positions
    assert np.all(pos >= 50.0)
    assert np.all(pos <= 100.0)


def test_place_in_zone_center_zone_missing_raises():
    board, netlist = power_board(), power_netlist()
    with pytest.raises(ValueError, match="not found"):
        place_in_zone_center(netlist, board, ["U1"], "nope")
    with pytest.raises(ValueError, match="not found"):
        oracle.place_in_zone_center(netlist, board, ["U1"], "nope")


def test_place_in_zone_center_ref_not_in_netlist():
    board, netlist = power_board(), power_netlist()
    prod = place_in_zone_center(netlist, board, ["U1", "MISSING"], "logic_zone")
    ref = oracle.place_in_zone_center(netlist, board, ["U1", "MISSING"], "logic_zone")
    assert_result_equal(prod, ref)
    assert "MISSING" in prod.unplaced_refs

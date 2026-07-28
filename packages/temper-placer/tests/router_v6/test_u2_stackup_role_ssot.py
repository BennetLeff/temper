"""
U2 (docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md):
stackup role as declared SSOT, decoupled from zone content.

Falsifier for R8's bug: `_extract_stackup` marks a physical layer "plane"
if *any* zone on it sits on a plane-required net (`_is_plane_required_net`),
and `routing_space.py`'s `compute_routing_space` then excludes any layer
whose `layer_type` isn't "signal"/"mixed" from the router's routing space
entirely. On the production board, F.Cu carries 48 zones total but only 4
are plane-required (`ac_l`, `ac_n`, `DC_BUS_RTN`, `SW_NODE`) -- not a
full-layer plane -- yet F.Cu is absent from the routing space regardless.

`use_declared_layer_roles=True` (opt-in on `_extract_stackup` /
`parse_kicad_pcb_v6`, default `False`) fixes the classification: role comes
from structural position in the declared stackup, never from zone content.

Scope note (do not remove): this flag alone does NOT make F.Cu's routing
space usable, only present in the routing-space dict. The router's
obstacle map (`obstacle_map.py`) still treats every existing zone on a
layer as an opaque obstacle regardless of net, independent of
`layer_type` -- so the un-regenerated production board's 48 F.Cu zones
would still occupy nearly the whole layer if this flag were flipped on in
production today. That is the exact mechanism recorded in
`docs/evidence/2026-07-28-stackup-partial-revert.md`'s 12x completion
regression. Turning this flag on in production requires pours to become
derived, non-authoritative output first (this plan's U3) -- see that
document and `_extract_stackup`'s docstring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kiutils.board import Board as KiBoard

from temper_placer.io._parse_board import _is_plane_required_net
from temper_placer.io.kicad_parser import _extract_stackup, parse_kicad_pcb_v6
from temper_placer.router_v6.routing_space import compute_routing_space

_PCB_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
)


@pytest.fixture(scope="module")
def _ki_board() -> KiBoard:
    assert _PCB_PATH.exists(), f"production board not found at {_PCB_PATH}"
    return KiBoard.from_file(str(_PCB_PATH))


def test_production_board_fcu_is_not_a_full_layer_plane(_ki_board):
    """Establishes the premise: F.Cu carries many zones, only a handful of
    which are plane-required. It is not a plane by any reasonable reading
    of its content -- so classifying the whole physical layer "plane" is
    the bug, not a correct reading of the board."""
    fcu_zones = [z for z in _ki_board.zones if z.layers and "F.Cu" in z.layers]
    plane_required = [z for z in fcu_zones if z.netName and _is_plane_required_net(z.netName)]

    assert len(fcu_zones) > 10, "expected many zones on F.Cu on the production board"
    assert len(plane_required) == 4
    assert {z.netName for z in plane_required} == {"ac_l", "ac_n", "DC_BUS_RTN", "SW_NODE"}


def test_default_behavior_unchanged_fcu_still_classified_plane(_ki_board):
    """Regression guard on the opt-in's default: with the flag unset
    (today's call sites, unmodified), F.Cu is still classified "plane" --
    this documents today's bug baseline and proves the fix is inert unless
    explicitly enabled."""
    stackup = _extract_stackup(_ki_board, [])
    fcu = next(layer for layer in stackup.layers if layer.name == "F.Cu")
    assert fcu.layer_type == "plane"
    assert fcu.plane_net == "ac_l"


def test_declared_role_classifies_outer_layers_as_signal(_ki_board):
    """R8: with the opt-in, F.Cu/B.Cu's role comes from structural position
    in the declared stackup (outer layers), independent of zone content.
    plane_net is still surfaced for callers that want it."""
    stackup = _extract_stackup(_ki_board, [], use_declared_layer_roles=True)
    fcu = next(layer for layer in stackup.layers if layer.name == "F.Cu")
    bcu = next(layer for layer in stackup.layers if layer.name == "B.Cu")

    assert fcu.layer_type == "signal"
    assert bcu.layer_type == "signal"
    # Informational plane_net is retained even though it no longer decides
    # layer_type -- callers that want "does a plane-required pour sit here"
    # keep that answer.
    assert fcu.plane_net == "ac_l"
    assert bcu.plane_net == "ac_l"


def test_declared_role_leaves_inner_layers_unaffected(_ki_board):
    """Decoupling zone content from layer_type must not change layers that
    were never misclassified in the first place."""
    default_stackup = _extract_stackup(_ki_board, [])
    declared_stackup = _extract_stackup(_ki_board, [], use_declared_layer_roles=True)

    for name in ("In1.Cu", "In2.Cu"):
        default_layer = next(layer for layer in default_stackup.layers if layer.name == name)
        declared_layer = next(layer for layer in declared_stackup.layers if layer.name == name)
        assert default_layer.layer_type == declared_layer.layer_type == "mixed"


def test_declared_role_makes_fcu_present_in_the_routing_space(_ki_board):
    """The falsifier. Today (flag off), F.Cu is entirely absent from
    compute_routing_space's output -- routing_space.py excludes any layer
    whose layer_type isn't signal/mixed -- even though only 4 of 48 zones
    on it are plane-required. With the opt-in, F.Cu (and B.Cu) must be
    present in the routing space.

    This only asserts *presence*, not usable free area: making the area
    non-trivial requires U3 (pour regeneration) and is explicitly out of
    this unit's scope -- see the module docstring.
    """
    pcb = parse_kicad_pcb_v6(_PCB_PATH, use_declared_layer_roles=True)
    routing_spaces = compute_routing_space(pcb)

    assert "F.Cu" in routing_spaces
    assert "B.Cu" in routing_spaces


def test_default_behavior_unchanged_fcu_absent_from_routing_space(_ki_board):
    """Regression guard: with the flag unset, today's exact bug behavior
    (F.Cu/B.Cu absent from the routing space) is preserved byte-for-byte,
    proving this change does not silently flip production behavior."""
    pcb = parse_kicad_pcb_v6(_PCB_PATH)
    routing_spaces = compute_routing_space(pcb)

    assert "F.Cu" not in routing_spaces
    assert "B.Cu" not in routing_spaces
    assert set(routing_spaces.keys()) == {"In1.Cu", "In2.Cu"}

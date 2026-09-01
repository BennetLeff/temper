"""Tests for the protective-impedance chain co-location constraint.

The properties that matter, in the order they can silently break:

1. Chain membership is *derived* from the manifest's interior net names.
   If that derivation drifts, the constraint silently co-locates nothing
   (or the wrong parts) while still reporting "satisfied" -- the exact
   failure mode ``heatsink_colocation.py`` documents for ``Q1``/``Q2``.
2. The committed board must FAIL the predicate. A checker that passes on
   the board it was written to reject is vacuous.
3. Only wire types both backends register may be emitted, or Pumpkin
   ``exit(2)``s and OR-Tools silently under-constrains.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.protective_impedance_colocation import (
    MAX_CHAIN_GAP_MM,
    ChainPair,
    chain_colocation_wire_constraints,
    check_chain_colocation,
    load_protective_impedance_chains,
    resolve_chain_pairs,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

#: Wire types registered in BOTH backends. Emitting anything else makes
#: Pumpkin exit(2) and OR-Tools warn-and-continue.
REGISTERED_WIRE_TYPES = {"adjacent", "aligned", "separated", "bounded", "anchored", "fixed_rotation"}


@pytest.fixture(scope="module")
def netlist():
    if not BOARD.exists():
        pytest.skip(f"{BOARD} absent")
    return parse_kicad_pcb(BOARD).netlist


@pytest.fixture(scope="module")
def chains():
    if not MANIFEST.exists():
        pytest.skip(f"{MANIFEST} absent")
    return load_protective_impedance_chains(MANIFEST)


def test_manifest_declares_the_two_ovp_chains(chains):
    names = {c["name"] for c in chains}
    assert "ovp01_comparator_divider" in names
    assert "ovp01_adc_sense_divider" in names
    for c in chains:
        # min_length is the safety declaration; a chain shorter than it
        # stops being a valid protective-impedance construction.
        assert len(c["chain"]) >= c["min_length"]


def test_resolution_recovers_four_consecutive_pairs(chains, netlist):
    """Two chains of three yield exactly two consecutive pairs each."""
    pairs = resolve_chain_pairs(chains, netlist.components)
    assert len(pairs) == 4, [(p.a, p.b) for p in pairs]

    by_net = {p.interior_net: p for p in pairs}
    # The comparator chain's two interior nodes are the band's net pair.
    assert "safety.ovp.r_div_top1-p2" in by_net
    assert "safety.ovp.r_div_top2-p2" in by_net

    # Both interior nodes of one chain share the middle resistor.
    a = by_net["safety.ovp.r_div_top1-p2"]
    b = by_net["safety.ovp.r_div_top2-p2"]
    shared = {a.a, a.b} & {b.a, b.b}
    assert len(shared) == 1, (
        "the two interior nodes of a 3-resistor chain must terminate on the "
        f"same middle part; got {a} and {b}"
    )


def test_committed_board_violates_every_pair(chains, netlist):
    """The predicate must reject the board it was written to reject."""
    pairs = resolve_chain_pairs(chains, netlist.components)
    positions = {c.ref: tuple(c.initial_position) for c in netlist.components}
    rotations = {c.ref: int(c.initial_rotation_quadrant) for c in netlist.components}
    sizes = {c.ref: (float(c.bounds[0]), float(c.bounds[1])) for c in netlist.components}

    viols = check_chain_colocation(pairs, positions, rotations, sizes)
    assert len(viols) == len(pairs) == 4
    # Every gap is an order of magnitude past the bound, so this is not a
    # tolerance-sensitive assertion.
    assert all(v.measured_mm > 5 * MAX_CHAIN_GAP_MM for v in viols), [
        (v.refs, v.measured_mm) for v in viols
    ]


def test_checker_accepts_a_co_located_placement():
    pair = ChainPair("c", "RA", "RB", "n-p2")
    sizes = {"RA": (3.2, 1.6), "RB": (3.2, 1.6)}
    rot = {"RA": 0, "RB": 0}
    # 4mm centre-to-centre => 0.8mm edge-to-edge, well inside the bound.
    assert not check_chain_colocation(
        [pair], {"RA": (0.0, 0.0), "RB": (4.0, 0.0)}, rot, sizes
    )
    # 40mm apart => 36.8mm edge-to-edge, outside it.
    assert check_chain_colocation([pair], {"RA": (0.0, 0.0), "RB": (40.0, 0.0)}, rot, sizes)


def test_emits_only_wire_types_both_backends_register(chains, netlist):
    pairs = resolve_chain_pairs(chains, netlist.components)
    cs = chain_colocation_wire_constraints(pairs)
    assert cs, "expected constraints for a board that violates all four pairs"
    assert {c["type"] for c in cs} <= REGISTERED_WIRE_TYPES
    # `adjacent` is the only type this constraint needs; a rotation pin
    # would over-constrain (a series chain has no shared mounting face).
    assert {c["type"] for c in cs} == {"adjacent"}
    for c in cs:
        assert c["metric"] == "edge_to_edge"
        assert c["max_distance_mm"] == MAX_CHAIN_GAP_MM
        assert c["because"]


def test_absent_refs_are_filtered_not_silently_emitted(chains, netlist):
    """A constraint naming a component the payload lacks is dropped."""
    pairs = resolve_chain_pairs(chains, netlist.components)
    assert chain_colocation_wire_constraints(pairs, present_refs=frozenset()) == []


def test_unresolvable_chain_is_skipped_not_guessed():
    """A chain whose interior net is absent must not constrain anything."""
    assert resolve_chain_pairs([{"name": "x", "chain": ["a.b", "a.c"]}], []) == []


def test_strict_resolution_fails_closed_on_unresolvable_chain():
    """The production solver mode must not silently drop a safety pair."""
    with pytest.raises(ValueError, match="interior net"):
        resolve_chain_pairs(
            [{"name": "x", "chain": ["a.b", "a.c"]}],
            [],
            strict=True,
        )

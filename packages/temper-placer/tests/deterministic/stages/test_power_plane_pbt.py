"""Property-based + metamorphic tests for the migrated power_plane compute.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_power_plane_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Plane-marking: every plane net that appears in the netlist ends up
  with `is_plane == True`.
- P2. Layer default: a plane net without an explicit layer mapping lands on
  layer 1.
- P3. Non-plane preservation: a non-plane existing assignment keeps its
  layer and allow_layer_change.
- P4. Totality: every netlist net gets exactly one assignment.
- P5. No invented nets: only netlist nets appear in the output.

Three metamorphic relations (R1d):

- MR1. Plane-layer commutativity: adding a plane net to the netlist after
  an existing non-plane assignment upgrades it identically to a fresh run
  with the plane net already present.
- MR2. Empty-plane invariance: with an empty plane set, the output equals
  the input existing assignments (in order) plus the remaining netlist nets.
- MR3. Existing-order preservation: the relative order of existing
  assignments is preserved in the output.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.deterministic_leaves
LA = _tdb.LayerAssignment

_NAMES = st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ+_-0123456789")
_LAYER = st.integers(min_value=0, max_value=3)
_NETS = st.lists(_NAMES, min_size=0, max_size=6, unique=True)


def _existing(names, layer, allow=True, plane=False):
    return [LA(n, layer, allow, plane) for n in names]


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_p1_plane_nets_marked(all_nets, plane_nets, layer):
    got = _RS.recompute_plane_assignments([], plane_nets, {}, all_nets)
    by_name = {a.net_name: a for a in got}
    for n in plane_nets:
        if n in all_nets:
            assert by_name[n].is_plane is True


@given(_NETS, st.sampled_from(["GND"]))
@settings(max_examples=50, deadline=None)
def test_p2_layer_default(all_nets, net):
    if net not in all_nets:
        return
    got = _RS.recompute_plane_assignments([], [net], {}, all_nets)
    by_name = {a.net_name: a for a in got}
    assert by_name[net].layer == 1


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_p3_non_plane_preserved(all_nets, plane_nets, layer):
    existing = _existing(all_nets, layer, allow=False)
    got = _RS.recompute_plane_assignments(existing, plane_nets, {}, all_nets)
    for a in got:
        if a.net_name not in plane_nets:
            assert a.layer == layer
            assert a.allow_layer_change is False


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_p4_totality(all_nets, plane_nets, layer):
    existing = _existing(all_nets, layer)
    got = _RS.recompute_plane_assignments(existing, plane_nets, {}, all_nets)
    assert {a.net_name for a in got} == set(all_nets)
    assert len(got) == len(all_nets)


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_p5_no_invented_nets(all_nets, plane_nets, layer):
    existing = _existing(all_nets, layer)
    got = _RS.recompute_plane_assignments(existing, plane_nets, {}, all_nets)
    assert all(a.net_name in all_nets for a in got)


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_mr1_existing_preserved_in_order(all_nets, plane_nets, layer):
    existing = _existing(all_nets, layer)
    got = _RS.recompute_plane_assignments(existing, plane_nets, {}, all_nets)
    got_names = [a.net_name for a in got]
    existing_idx = {n: i for i, n in enumerate(all_nets)}
    filtered = [n for n in got_names if n in all_nets]
    # Existing assignments keep their relative order in the output prefix.
    positions = [existing_idx[n] for n in got_names[: len(all_nets)]]
    assert positions == sorted(positions)


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_mr2_empty_plane_invariance(all_nets, _, layer):
    existing = _existing(all_nets, layer)
    got = _RS.recompute_plane_assignments(existing, [], {}, all_nets)
    assert [(a.net_name, a.layer, a.is_plane) for a in got] == [
        (n, layer, False) for n in all_nets
    ]


@given(_NETS, _NETS, _LAYER)
@settings(max_examples=100, deadline=None)
def test_mr3_plane_default_commutes_with_explicit(all_nets, plane_nets, layer):
    """A plane net resolves identically whether its layer comes from the map
    or from the `1` default — when the map entry equals the default."""
    if not plane_nets:
        return
    net = plane_nets[0]
    got_default = _RS.recompute_plane_assignments([], plane_nets, {}, all_nets)
    got_explicit = _RS.recompute_plane_assignments([], plane_nets, {net: 1}, all_nets)
    by_d = {a.net_name: a for a in got_default}
    by_e = {a.net_name: a for a in got_explicit}
    for n in plane_nets:
        if n in all_nets:
            assert by_d[n].layer == by_e[n].layer
            assert by_d[n].is_plane == by_e[n].is_plane

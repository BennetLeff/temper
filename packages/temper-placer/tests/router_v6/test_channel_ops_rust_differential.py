"""R1a: behavioural A/B of the Phase E batch E4 channel-operations Rust
orchestration (temper-orchestration ``channel_mapping`` module) against the
pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E4: the channel
operations' ORCHESTRATION moves to temper-orchestration's
``channel_mapping.rs`` (Stage<BoardState> impls + the pyfunction FFI
surface); the modules keep their public API as delegation shims. The
pre-migration implementation is pinned VERBATIM as
``tests/router_v6/_channel_ops_py_oracle.py`` (byte-identical snapshot at the
dispatch base, origin/main d1b330b90; content-hash pinned in
``scripts/oracle_hashes.json`` AND in this file's body digest). Both arms
are driven with IDENTICAL inputs; every assertion is bit-exact (floats via
``float.hex()`` via ``canon``, per-field comparisons below).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
each shim function now binds to a ``temper_orchestration`` pyfunction
(``__module__`` / import binding), not resolving back onto the oracle.

Covered orchestrations:

- ``channel_mapping.map_topology_to_channels`` vs ``channel_mapping::run_channel_mapping``
- ``channel_mapping.fallback_channel_path``  vs ``channel_mapping::run_fallback_channel_path``
- ``channel_mapping.expand_channel_path_terminals`` (the two-pad validator
  and the all-pad-tree expander) vs ``channel_mapping::run_validated_two_pad_terminals`` /
  ``run_expand_all_pad_tree``
- ``channel_widths.compute_channel_widths`` (the EDT production path AND the
  per-point reference path) vs ``channel_mapping::run_channel_widths_edt``
  (the edge sampling / batch-lookup dispatch / node-edge-width assembly /
  statistics; the rasterise / fingerprint / disk-cache / per-point shapely
  work stays Python — the E4 boundary)

Widths are compared with numpy-scalar normalisation (``float.hex()`` on
``float(v)``): the oracle's ``node_widths`` values are ``np.float64`` (numpy
array indexing) while the Rust path returns Python floats; the IEEE bits are
the contract, the numpy wrapper is not (documented in VERIFICATION.md).
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from types import SimpleNamespace

import pytest
from shapely.geometry import MultiPolygon, box

from temper_placer.router_v6.channel_mapping import (
    expand_channel_path_terminals as shim_expand,
)
from temper_placer.router_v6.channel_mapping import (
    fallback_channel_path as shim_fallback,
)
from temper_placer.router_v6.channel_mapping import (
    map_topology_to_channels as shim_map,
)
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton, SkeletonGraph
from temper_placer.router_v6.channel_widths import compute_channel_widths as shim_widths
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.topology_extraction import NetTopology, PathGraph, TopologyGraph
from tests.core._contract_canon import canon
from tests.router_v6 import _channel_ops_py_oracle as _oracle

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------

_ORACLE_PATH = Path(__file__).with_name("_channel_ops_py_oracle.py")


def test_oracle_body_matches_pinned_digest() -> None:
    """The oracle is evidence only while it is unmodified.

    A differential whose oracle can be edited to agree with the port proves
    nothing, so the copied bodies are content-addressed. If this fails,
    either the oracle was edited (revert it) or a pre-migration module's
    source really changed upstream (re-pin deliberately, in its own commit).
    """
    text = _ORACLE_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digest == "2626835db704db59658f5f13a02caf6f6bce676225001fbc72b046c6eb65f2b1", (
        "the pinned oracle file changed; it must stay verbatim "
        "(see scripts/oracle_hashes.json for the registered hash)"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shims must bind to temper_orchestration pyfunctions,
    not resolve back onto the oracle."""
    import temper_orchestration as _to

    assert _to.run_channel_mapping.__module__ == "temper_orchestration.temper_orchestration"
    assert (
        _to.run_fallback_channel_path.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert (
        _to.run_validated_two_pad_terminals.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert (
        _to.run_expand_all_pad_tree.__module__
        == "temper_orchestration.temper_orchestration"
    )
    assert _to.run_channel_widths_edt.__module__ == "temper_orchestration.temper_orchestration"
    assert _oracle.map_topology_to_channels is not shim_map
    assert _oracle.compute_channel_widths is not shim_widths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_skeleton(nodes, edges=()):
    g = SkeletonGraph()
    for n in nodes:
        g.add_node(n, pos=n)
    for u, v in edges:
        g.add_edge(u, v, weight=1.0)
    return ChannelSkeleton(g, "F.Cu", 0.0)


def net_topo(net_name, uses, path_edges=None):
    pg = PathGraph(path_edges) if path_edges is not None else None
    return NetTopology(
        net_name=net_name,
        path_graph=pg,
        uses_channels=list(uses),
        total_length_estimate=0.0,
    )


def topology(net_topos):
    return TopologyGraph(net_topologies=net_topos)


def _assignment(reason, primary_layer):
    return SimpleNamespace(reason=reason, primary_layer=primary_layer)


# ---------------------------------------------------------------------------
# Canonical comparators
# ---------------------------------------------------------------------------


def _canon_waypoints(wps):
    return tuple((canon(x), canon(y)) for (x, y) in wps)


def _canon_path(p):
    return (
        p.net_name,
        tuple(p.channel_sequence),
        _canon_waypoints(p.waypoints),
        canon(p.total_length),
        p.preferred_layer,
    )


def _assert_mappings_same(want, got, msg=""):
    assert want.mapped_net_count == got.mapped_net_count, f"{msg}: mapped_net_count"
    assert set(want.channel_paths) == set(got.channel_paths), f"{msg}: net set"
    for net in want.channel_paths:
        assert _canon_path(want.channel_paths[net]) == _canon_path(
            got.channel_paths[net]
        ), f"{msg}: net={net!r}"


def _wbits(v):
    # Normalise np.float64 -> Python float (exact), then float.hex().
    return ("float", float(v).hex())


def _canon_widths(cw):
    node_widths = tuple(
        sorted(
            ((canon(x), canon(y), _wbits(w)) for (x, y), w in cw.node_widths.items()),
            key=lambda t: (t[0], t[1]),
        )
    )
    edge_widths = tuple(
        sorted(
            (
                (canon(ux), canon(uy), canon(vx), canon(vy), _wbits(w))
                for (u, v), w in cw.edge_widths.items()
                for (ux, uy) in [u]
                for (vx, vy) in [v]
            ),
            key=lambda t: (t[0], t[1], t[2], t[3]),
        )
    )
    return (
        cw.layer_name,
        node_widths,
        edge_widths,
        _wbits(cw.min_width),
        _wbits(cw.max_width),
        _wbits(cw.avg_width),
    )


def _assert_widths_same(want, got, msg=""):
    assert _canon_widths(want) == _canon_widths(got), (
        f"{msg}: oracle={_canon_widths(want)} shim={_canon_widths(got)}"
    )


# ---------------------------------------------------------------------------
# map_topology_to_channels
# ---------------------------------------------------------------------------


def test_map_empty_topology_matches_oracle():
    topo = topology({})
    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    want = _oracle.map_topology_to_channels(topo, sk)
    got = shim_map(topo, sk)
    _assert_mappings_same(want, got, "empty")


def test_map_none_topology_matches_oracle():
    sk = make_skeleton([(0.0, 0.0)])
    want = _oracle.map_topology_to_channels(None, sk)
    got = shim_map(None, sk)
    _assert_mappings_same(want, got, "none")


def test_map_sat_channels_matches_oracle():
    net = net_topo("NET1", ["(0.0, 0.0)", "(10.0, 0.0)", "(10.0, 10.0)"])
    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])
    want = _oracle.map_topology_to_channels(topology({"NET1": net}), sk)
    got = shim_map(topology({"NET1": net}), sk)
    _assert_mappings_same(want, got, "sat")


def test_map_non_coordinate_ids_matches_oracle():
    # Non-coordinate channel IDs yield no parseable waypoints and fall back
    # to the skeleton's coordinate-order slice.
    net = net_topo("NET1", ["CH1", "CH2", "CH3"])
    sk = make_skeleton([(5.0, 5.0), (0.0, 0.0), (10.0, 0.0)])
    want = _oracle.map_topology_to_channels(topology({"NET1": net}), sk)
    got = shim_map(topology({"NET1": net}), sk)
    _assert_mappings_same(want, got, "plain ids")


def test_map_edge_id_waypoints_matches_oracle():
    net = net_topo("NET1", ["edge_(0, 0)_(10, 0)", "(20, 5)"])
    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0), (20.0, 5.0)])
    want = _oracle.map_topology_to_channels(topology({"NET1": net}), sk)
    got = shim_map(topology({"NET1": net}), sk)
    _assert_mappings_same(want, got, "edge ids")


def test_map_underscore_format_matches_oracle():
    # "x_y" format requires the coordinate to be near a skeleton node.
    net = net_topo("NET1", ["1_1", "9_1"])
    sk = make_skeleton([(1.0, 1.0), (9.0, 1.0)])
    want = _oracle.map_topology_to_channels(topology({"NET1": net}), sk)
    got = shim_map(topology({"NET1": net}), sk)
    _assert_mappings_same(want, got, "underscore near")


def test_map_underscore_format_off_skeleton_snaps_matches_oracle():
    # Strategy 3: a parsed-but-off-skeleton coordinate snaps to the nearest
    # skeleton node when the skeleton has <= 20 nodes.
    net = net_topo("NET1", ["100_100"])
    sk = make_skeleton([(1.0, 1.0), (9.0, 1.0)])
    want = _oracle.map_topology_to_channels(topology({"NET1": net}), sk)
    got = shim_map(topology({"NET1": net}), sk)
    _assert_mappings_same(want, got, "underscore snap")


def test_map_path_graph_fallback_matches_oracle():
    net = net_topo("NET2", [], path_edges=[("A", "B"), ("B", "C")])
    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)])
    want = _oracle.map_topology_to_channels(topology({"NET2": net}), sk)
    got = shim_map(topology({"NET2": net}), sk)
    _assert_mappings_same(want, got, "path graph")


def test_map_unroutable_net_matches_oracle():
    # No uses_channels and no path_graph -> not mapped.
    net = net_topo("NET3", [])
    sk = make_skeleton([(0.0, 0.0)])
    want = _oracle.map_topology_to_channels(topology({"NET3": net}), sk)
    got = shim_map(topology({"NET3": net}), sk)
    assert want.mapped_net_count == 0
    _assert_mappings_same(want, got, "unroutable")


def test_map_layer_constraints_matches_oracle():
    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    nets = {
        "PWM_GATE": net_topo("PWM_GATE", ["(0.0, 0.0)", "(10.0, 0.0)"]),
        "GND": net_topo("GND", ["(0.0, 0.0)", "(10.0, 0.0)"]),
        "SIG1": net_topo("SIG1", ["(0.0, 0.0)", "(10.0, 0.0)"]),
    }
    constraints = {
        "PWM_GATE": _assignment(reason="netclass=GateDrive SSOT layer=B.Cu", primary_layer=4),
        "SIG1": _assignment(reason="netclass=Default SSOT layer=B.Cu", primary_layer=4),
        "GND": "B.Cu",  # bare-string shim assignment
    }
    want = _oracle.map_topology_to_channels(topology(nets), sk, constraints)
    got = shim_map(topology(nets), sk, constraints)
    _assert_mappings_same(want, got, "layer constraints")


def test_map_layer_constraints_enum_layer_matches_oracle():
    class _Layer:
        def __init__(self, value):
            self.value = value

    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    net = net_topo("PWM_GATE", ["(0.0, 0.0)", "(10.0, 0.0)"])
    constraints = {
        "PWM_GATE": _assignment(reason="netclass=GateDrive SSOT layer=B.Cu", primary_layer=_Layer(4)),
    }
    want = _oracle.map_topology_to_channels(topology({"PWM_GATE": net}), sk, constraints)
    got = shim_map(topology({"PWM_GATE": net}), sk, constraints)
    _assert_mappings_same(want, got, "enum layer")


def test_map_layer_heuristic_does_not_call_python_net_predicates(monkeypatch):
    """The Rust orchestration owns net classification; Python only owns mode.

    This fence is deliberately production-shaped: route a real mapped net
    through the public shim while replacing the Python predicates with
    failures.  It catches an accidental regression to per-net Python FFI
    even when the Rust/Python differential remains green.
    """
    from temper_placer.router_v6 import net_classification

    net_classification.set_single_layer_mode(False)
    for name in ("is_power_net", "is_ground_net", "is_hv_net"):
        monkeypatch.setattr(
            net_classification,
            name,
            lambda _net_name: (_ for _ in ()).throw(
                AssertionError("channel mapping called Python net predicate")
            ),
        )

    sk = make_skeleton([(0.0, 0.0), (10.0, 0.0)])
    got = shim_map(
        topology({"GND": net_topo("GND", ["(0.0, 0.0)", "(10.0, 0.0)"])}),
        sk,
    )
    assert got.channel_paths["GND"].preferred_layer == "B.Cu"


def _rng_net_id(rng):
    kind = rng.choice(["coords", "edge", "plain", "underscore"])
    if kind == "coords":
        return f"({rng.randint(-20, 20)}, {rng.randint(-20, 20)})"
    if kind == "edge":
        return f"e_({rng.randint(-20, 20)}, {rng.randint(-20, 20)})_({rng.randint(-20, 20)}, {rng.randint(-20, 20)})"
    if kind == "underscore":
        return f"{rng.randint(-20, 20)}_{rng.randint(-20, 20)}"
    return f"CH{rng.randint(0, 99)}"


@pytest.mark.parametrize("seed", range(20))
def test_map_random_matches_oracle(seed):
    rng = random.Random(7000 + seed)
    sk = make_skeleton([(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(rng.randint(0, 12))])
    net_topos = {}
    for i in range(rng.randint(0, 8)):
        name = f"NET{i}"
        kind = rng.choice(["sat", "path", "none"])
        if kind == "sat":
            uses = [_rng_net_id(rng) for _ in range(rng.randint(1, 5))]
            net_topos[name] = net_topo(name, uses)
        elif kind == "path":
            edges = [(f"N{i}A", f"N{i}B"), (f"N{i}B", f"N{i}C")]
            if rng.random() < 0.5:
                net_topos[name] = net_topo(name, [], path_edges=edges)
            else:
                net_topos[name] = net_topo(name, [_rng_net_id(rng)])
        else:
            net_topos[name] = net_topo(name, [])
    topo = topology(net_topos)
    constraints = {}
    if rng.random() < 0.5:
        for name in net_topos:
            if rng.random() < 0.4:
                constraints[name] = _assignment(
                    reason=rng.choice(["netclass=X SSOT layer=B.Cu", "netclass=Default SSOT layer=B.Cu"]),
                    primary_layer=rng.choice([1, 4]),
                )
    want = _oracle.map_topology_to_channels(topo, sk, constraints or None)
    got = shim_map(topo, sk, constraints or None)
    _assert_mappings_same(want, got, f"seed={seed}")


# ---------------------------------------------------------------------------
# fallback_channel_path
# ---------------------------------------------------------------------------


def _assert_path_same(want, got, msg=""):
    assert _canon_path(want) == _canon_path(got), f"{msg}: oracle={_canon_path(want)} shim={_canon_path(got)}"


def test_fallback_two_pad_matches_oracle():
    pads = [(0.0, 0.0), (10.0, 5.0)]
    want = _oracle.fallback_channel_path("NET", pads)
    got = shim_fallback("NET", pads)
    _assert_path_same(want, got, "2pad")


def test_fallback_multi_pad_default_matches_oracle():
    pads = [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)]
    want = _oracle.fallback_channel_path("NET", pads)
    got = shim_fallback("NET", pads)
    _assert_path_same(want, got, "multipad default")


def test_fallback_all_pad_tree_matches_oracle():
    pads = [(10.0, 0.0), (5.0, 5.0), (0.0, 0.0)]
    want = _oracle.fallback_channel_path("NET", pads, enable_all_pad_tree=True)
    got = shim_fallback("NET", pads, enable_all_pad_tree=True)
    _assert_path_same(want, got, "allpad")


def test_fallback_layer_constraints_matches_oracle():
    pads = [(0.0, 0.0), (10.0, 5.0)]
    constraints = {"NET": _assignment(reason="netclass=Power SSOT layer=B.Cu", primary_layer=4)}
    want = _oracle.fallback_channel_path("NET", pads, constraints)
    got = shim_fallback("NET", pads, constraints)
    _assert_path_same(want, got, "constraints")


@pytest.mark.parametrize("seed", range(10))
def test_fallback_random_matches_oracle(seed):
    rng = random.Random(8000 + seed)
    n = rng.randint(2, 7)
    pads = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(n)]
    enable = rng.random() < 0.5
    constraints = None
    if rng.random() < 0.5:
        constraints = {"NET": _assignment(reason="netclass=Default SSOT layer=B.Cu", primary_layer=4)}
    want = _oracle.fallback_channel_path("NET", pads, constraints, enable_all_pad_tree=enable)
    got = shim_fallback("NET", pads, constraints, enable_all_pad_tree=enable)
    _assert_path_same(want, got, f"seed={seed}")


# ---------------------------------------------------------------------------
# expand_channel_path_terminals
# ---------------------------------------------------------------------------


def _path(net_name, sequence, waypoints, total_length, preferred_layer="F.Cu"):
    from temper_placer.router_v6.channel_mapping import ChannelPath

    return ChannelPath(
        net_name=net_name,
        channel_sequence=list(sequence),
        waypoints=list(waypoints),
        total_length=total_length,
        preferred_layer=preferred_layer,
    )


def _assert_expand_same(path, pads, enable, msg=""):
    want = _oracle.expand_channel_path_terminals(path, pads, enable_all_pad_tree=enable)
    got = shim_expand(path, pads, enable_all_pad_tree=enable)
    assert _canon_path(want) == _canon_path(got), (
        f"{msg}: oracle={_canon_path(want)} shim={_canon_path(got)}"
    )
    # Identity parity: an unchanged path must be returned as the SAME object.
    assert (want is path) == (got is path), (
        f"{msg}: identity parity oracle={want is path} shim={got is path}"
    )


def test_expand_two_pad_identity_matches_oracle():
    path = _path("NET", ["c1", "c2"], [(0.0, 0.0), (10.0, 0.0)], 10.0)
    pads = [(0.0, 0.0), (10.0, 0.0)]
    _assert_expand_same(path, pads, False, "identity")


def test_expand_two_pad_swap_matches_oracle():
    path = _path("NET", ["c1", "c2"], [(0.0, 0.0), (10.0, 0.0)], 10.0)
    pads = [(10.0, 0.0), (0.0, 0.0)]  # true pads in swapped order
    _assert_expand_same(path, pads, False, "swap")


def test_expand_two_pad_wrong_endpoint_matches_oracle():
    # The Stage-3 defect: an endpoint that is a *different* net's pad.
    path = _path("NET", ["c1", "c2"], [(0.0, 0.0), (99.0, 99.0)], 10.0)
    pads = [(0.0, 0.0), (10.0, 0.0)]
    _assert_expand_same(path, pads, False, "wrong endpoint")


def test_expand_two_pad_short_path_matches_oracle():
    path = _path("NET", ["c1"], [(5.0, 5.0)], 0.0)
    pads = [(0.0, 0.0), (10.0, 0.0)]
    _assert_expand_same(path, pads, False, "short path")


def test_expand_two_pad_interior_preserved_matches_oracle():
    path = _path("NET", ["c1", "c2", "c3"], [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)], 14.14)
    pads = [(0.0, 0.0), (10.0, 0.0)]
    _assert_expand_same(path, pads, False, "interior")


def test_expand_all_pad_tree_appends_matches_oracle():
    path = _path("NET", ["c1", "c2"], [(0.0, 0.0), (10.0, 0.0)], 10.0)
    pads = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0), (3.0, 2.0)]
    _assert_expand_same(path, pads, True, "append")


def test_expand_all_pad_tree_noop_matches_oracle():
    path = _path("NET", ["c1", "c2"], [(0.0, 0.0), (10.0, 0.0)], 10.0)
    pads = [(0.0, 0.0), (10.0, 0.0)]
    _assert_expand_same(path, pads, True, "noop")


def test_expand_disabled_matches_oracle():
    path = _path("NET", ["c1"], [(0.0, 0.0)], 0.0)
    pads = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)]
    _assert_expand_same(path, pads, False, "disabled")


def test_expand_all_pad_tree_empty_path_matches_oracle():
    path = _path("NET", [], [], 0.0)
    pads = [(3.0, 3.0), (1.0, 1.0), (2.0, 2.0)]
    _assert_expand_same(path, pads, True, "empty path")


def test_expand_duplicate_pads_matches_oracle():
    # set(waypoints) / set(pads) dedup; a pad already on the path is not re-appended.
    path = _path("NET", ["c1"], [(0.0, 0.0)], 0.0)
    pads = [(0.0, 0.0), (10.0, 0.0), (10.0, 0.0), (5.0, 5.0)]
    _assert_expand_same(path, pads, True, "duplicates")


def test_expand_total_length_uses_pad_input_order_matches_oracle():
    """Faithful-wart pin: the all-pad-tree branch computes ``total_length``
    over ``[*waypoints, *missing]`` where ``missing`` is the pad-INPUT-order
    list (not the deterministically ordered ``ordered_missing``). Permuting
    the pads therefore changes the length even though the waypoints stay
    deterministic; both arms must reproduce that exactly."""
    path = _path("NET", ["c1"], [(0.0, 0.0)], 0.0)
    pads_a = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0), (3.0, 2.0)]
    pads_b = [(0.0, 0.0), (3.0, 2.0), (5.0, 8.0), (10.0, 0.0)]
    want_a = _oracle.expand_channel_path_terminals(path, pads_a, enable_all_pad_tree=True)
    got_a = shim_expand(path, pads_a, enable_all_pad_tree=True)
    want_b = _oracle.expand_channel_path_terminals(path, pads_b, enable_all_pad_tree=True)
    got_b = shim_expand(path, pads_b, enable_all_pad_tree=True)
    _assert_path_same(want_a, got_a, "order a")
    _assert_path_same(want_b, got_b, "order b")
    # The wart is live: the two orders really do give different lengths.
    assert want_a.waypoints == want_b.waypoints  # waypoints deterministic
    assert want_a.total_length != want_b.total_length  # length is not


@pytest.mark.parametrize("seed", range(10))
def test_expand_random_matches_oracle(seed):
    rng = random.Random(9000 + seed)
    n_waypoints = rng.randint(1, 4)
    waypoints = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(n_waypoints)]
    path = _path("NET", [f"c{i}" for i in range(n_waypoints)], waypoints, rng.uniform(0, 50))
    n_pads = rng.randint(2, 6)
    pads = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(n_pads)]
    enable = rng.random() < 0.5
    if len(pads) == 2:
        enable = False  # the two-pad validator runs regardless
    _assert_expand_same(path, pads, enable, f"seed={seed}")


# ---------------------------------------------------------------------------
# compute_channel_widths
# ---------------------------------------------------------------------------


def _routing_space(polygon, layer="F.Cu"):
    return RoutingSpace(
        layer_name=layer,
        available_area=polygon,
        total_area=float(polygon.area),
        obstacle_area=0.0,
        routing_area=float(polygon.area),
    )


def _line_skeleton(spacing=2.0, n_nodes=6):
    nodes = [(i * spacing, 1.0) for i in range(n_nodes)]
    edges = [(nodes[i], nodes[i + 1]) for i in range(n_nodes - 1)]
    return make_skeleton(nodes, edges)


def test_widths_edt_basic_matches_oracle():
    rs = _routing_space(box(0, 0, 20, 8))
    sk = _line_skeleton(spacing=2.0, n_nodes=8)
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=1.0)
    got = shim_widths(rs, sk, sample_distance=1.0)
    _assert_widths_same(want, got, "edt basic")


def test_widths_edt_multipolygon_matches_oracle():
    poly = MultiPolygon([box(0, 0, 10, 6), box(14, 0, 24, 6)])
    rs = _routing_space(poly)
    sk = make_skeleton(
        [(2.0, 1.0), (5.0, 1.0), (8.0, 1.0), (16.0, 1.0), (20.0, 1.0)],
        [((2.0, 1.0), (5.0, 1.0)), ((5.0, 1.0), (8.0, 1.0)), ((16.0, 1.0), (20.0, 1.0))],
    )
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=1.0)
    got = shim_widths(rs, sk, sample_distance=1.0)
    _assert_widths_same(want, got, "multipoly")


@pytest.mark.parametrize("sample_distance", [0.5, 1.0, 2.0, 5.0, 10.0])
def test_widths_edt_sample_distance_matches_oracle(sample_distance):
    rs = _routing_space(box(0, 0, 30, 10))
    sk = _line_skeleton(spacing=3.0, n_nodes=9)
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=sample_distance)
    got = shim_widths(rs, sk, sample_distance=sample_distance)
    _assert_widths_same(want, got, f"sample={sample_distance}")


def test_widths_edt_empty_skeleton_matches_oracle():
    rs = _routing_space(box(0, 0, 20, 8))
    sk = make_skeleton([])
    want = _oracle.compute_channel_widths(rs, sk)
    got = shim_widths(rs, sk)
    _assert_widths_same(want, got, "empty skeleton")


def test_widths_empty_area_matches_oracle():
    import shapely.wkt

    rs = _routing_space(shapely.wkt.loads("POLYGON EMPTY"))
    sk = _line_skeleton()
    want = _oracle.compute_channel_widths(rs, sk)
    got = shim_widths(rs, sk)
    _assert_widths_same(want, got, "empty area")


def test_widths_reference_path_matches_oracle():
    # use_edt=False drives the per-point shapely reference in BOTH arms
    # (that path stays Python in the shim; this pins the shim's untouched
    # copy against the oracle's).
    rs = _routing_space(box(0, 0, 20, 8))
    sk = _line_skeleton(spacing=2.0, n_nodes=6)
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=1.0, use_edt=False)
    got = shim_widths(rs, sk, sample_distance=1.0, use_edt=False)
    _assert_widths_same(want, got, "reference path")


def test_widths_edt_diagonal_edges_matches_oracle():
    rs = _routing_space(box(0, 0, 20, 20))
    sk = make_skeleton(
        [(0.5, 0.5), (19.5, 0.5), (19.5, 19.5), (10.0, 10.0)],
        [((0.5, 0.5), (19.5, 19.5)), ((19.5, 0.5), (19.5, 19.5)), ((0.5, 0.5), (10.0, 10.0))],
    )
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=2.0)
    got = shim_widths(rs, sk, sample_distance=2.0)
    _assert_widths_same(want, got, "diagonal")


@pytest.mark.parametrize("seed", range(8))
def test_widths_edt_random_skeleton_matches_oracle(seed):
    rng = random.Random(10000 + seed)
    rs = _routing_space(box(0, 0, 25, 12))
    n_nodes = rng.randint(2, 8)
    nodes = [(rng.uniform(0.5, 24.5), rng.uniform(0.5, 11.5)) for _ in range(n_nodes)]
    edges = []
    for i in range(n_nodes - 1):
        edges.append((nodes[i], nodes[i + 1]))
    if rng.random() < 0.5 and n_nodes > 3:
        edges.append((nodes[0], nodes[-1]))
    sk = make_skeleton(nodes, edges)
    sample_distance = rng.choice([0.5, 1.0, 2.0])
    want = _oracle.compute_channel_widths(rs, sk, sample_distance=sample_distance)
    got = shim_widths(rs, sk, sample_distance=sample_distance)
    _assert_widths_same(want, got, f"seed={seed}")

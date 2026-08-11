"""Metamorphic relations for the Phase E batch E5 net-batching Rust
orchestration (temper-rust-router ``net_batching`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E5. Four invariant
relations (G5, >= 3 required), each verified on BOTH arms (the shim and
the pinned oracle) and required to agree:

- MR1  order is invariant under a permutation of the net LIST: the
       resulting order, read as a sequence of net NAMES, is unchanged when
       the same Net objects are shuffled (the sort key and the diff-pair
       pass are name-based, never position-based).
- MR2  chunking merges: merging consecutive pairs of ``chunk(order, s)``
       yields ``chunk(order, 2s)`` whenever the order length is a multiple
       of ``2s`` (a full-last-chunk guard, so no partial pair is merged
       across a boundary).
- MR3  capacity shrink decomposes: shrinking by consumed set A and then by
       set B equals shrinking by A followed by B in one call, when A and B
       name disjoint channel edges (and therefore disjoint ``(u, v)``
       coordinate pairs, so the two passes' subtractions never share an
       edge and float subtraction order cannot diverge).
- MR4  capacity consume decomposes by batch: consuming nets A then nets B
       leaves the same ``consumed`` dict as consuming the union in one
       call, for disjoint net sets.

Each relation is run against the oracle FIRST to confirm the oracle itself
satisfies it, then against the shim, and the two arms' outputs are compared
bit-exact.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

from temper_placer.core.netlist import Net
from temper_placer.router_v6 import net_batching as _shim
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.topology_extraction import NetTopology
from tests.router_v6 import _net_batching_py_oracle as _oracle


def _make_net(name: str, pin_count: int) -> Net:
    return Net(name=name, pins=[(f"U{i}", f"P{j}") for j in range(pin_count)])


def _net_topo(name: str, uses_channels: list[str]) -> NetTopology:
    return NetTopology(
        net_name=name, path_graph=None, uses_channels=list(uses_channels), total_length_estimate=0.0
    )


def _make_widths(spec: dict[str, dict[tuple[tuple[float, float], tuple[float, float]], float]]) -> dict[str, ChannelWidths]:
    out = {}
    for layer, edge_widths in spec.items():
        vals = list(edge_widths.values())
        out[layer] = ChannelWidths(
            layer_name=layer,
            node_widths={},
            edge_widths=dict(edge_widths),
            min_width=min(vals) if vals else 0.0,
            max_width=max(vals) if vals else 0.0,
            avg_width=(sum(vals) / len(vals)) if vals else 0.0,
        )
    return out


def _fake_rules(widths: dict[str, tuple[float, float]]) -> SimpleNamespace:
    rules = {}
    for name, (tw, cl) in widths.items():
        rules[name] = SimpleNamespace(trace_width_mm=tw, clearance_mm=cl)
    return SimpleNamespace(
        get_rules_for_net=lambda n: rules.get(n, SimpleNamespace(trace_width_mm=0.25, clearance_mm=0.2))
    )


# ---------------------------------------------------------------------------
# MR1 — order is invariant under a permutation of the net list
# ---------------------------------------------------------------------------


def _names_of(order, nets):
    return [nets[i].name for i in order]


def test_mr1_order_is_permutation_invariant():
    rng = random.Random(7)
    nets = [
        _make_net("USB_D+", 5), _make_net("USB_D-", 1), _make_net("CLK_P", 2),
        _make_net("CLK_N", 4), _make_net("3V3", 3), _make_net("GND", 6),
        _make_net("TANK_P", 2), _make_net("TANK_N", 1),
    ]
    for _ in range(25):
        perm = list(range(len(nets)))
        rng.shuffle(perm)
        shuffled = [nets[i] for i in perm]

        o_names = _names_of(_oracle.order_nets_for_batching(nets, None), nets)
        o_names_s = _names_of(_oracle.order_nets_for_batching(shuffled, None), shuffled)
        assert o_names == o_names_s, "oracle violates MR1"

        s_names = _names_of(_shim.order_nets_for_batching(nets, None), nets)
        s_names_s = _names_of(_shim.order_nets_for_batching(shuffled, None), shuffled)
        assert s_names == s_names_s, "shim violates MR1"
        assert s_names == o_names


# ---------------------------------------------------------------------------
# MR2 — chunking merges by pairing
# ---------------------------------------------------------------------------


def test_mr2_chunk_merge_equals_double_size():
    rng = random.Random(3)
    for n in (4, 12, 40):
        order = list(range(n))
        rng.shuffle(order)
        for s in (1, 2, 4):
            if n % (2 * s) != 0:
                continue
            pairs = []
            chunks = list(_oracle._chunks(order, s))
            for i in range(0, len(chunks), 2):
                pairs.append(chunks[i] + chunks[i + 1])
            expected = list(_oracle._chunks(order, 2 * s))
            assert pairs == expected, "oracle violates MR2"

            pairs_s = []
            chunks_s = list(_shim._chunks(order, s))
            for i in range(0, len(chunks_s), 2):
                pairs_s.append(chunks_s[i] + chunks_s[i + 1])
            got_s = list(_shim._chunks(order, 2 * s))
            assert pairs_s == got_s, "shim violates MR2"
            assert pairs_s == pairs


# ---------------------------------------------------------------------------
# MR3 — capacity shrink decomposes over disjoint consumed sets
# ---------------------------------------------------------------------------


def _shrunk(arm, widths, consumed, lookup):
    return arm._shrink_channel_widths(widths, consumed, lookup)


def test_mr3_shrink_decomposes_over_disjoint_consumed_sets():
    edges = {
        "F.Cu": {
            ((0.0, 0.0), (1.0, 0.0)): 3.0,
            ((0.0, 1.0), (1.0, 1.0)): 2.5,
            ((0.0, 2.0), (1.0, 2.0)): 4.0,
            ((0.0, 3.0), (1.0, 3.0)): 1.5,
            ((0.0, 4.0), (1.0, 4.0)): 3.5,
            ((0.0, 5.0), (1.0, 5.0)): 2.0,
        }
    }
    widths = _make_widths(edges)
    lookup = {}
    for (u, v) in edges["F.Cu"]:
        lookup[f"F.Cu:{u}-{v}"] = ("F.Cu", u, v)
    eids = list(lookup)
    consumed_a = {eids[0]: 0.5, eids[1]: 1.0, eids[2]: 2.0}
    consumed_b = {eids[3]: 0.7, eids[4]: 0.3, eids[5]: 1.4}

    for arm in (_oracle, _shim):
        # sequential: shrink with A, then B (on the A-shrunk widths)
        seq = _shrunk(arm, _shrunk(arm, widths, consumed_a, lookup), consumed_b, lookup)
        # combined: shrink once with the union (A's keys then B's keys)
        combined = {**consumed_a, **consumed_b}
        one = _shrunk(arm, widths, combined, lookup)
        for layer, cw in seq.items():
            assert cw.edge_widths == one[layer].edge_widths, f"{arm} violates MR3"

    # the two arms agree bit-exact
    o = _shrunk(_oracle, widths, {**consumed_a, **consumed_b}, lookup)
    s = _shrunk(_shim, widths, {**consumed_a, **consumed_b}, lookup)
    assert {l: cw.edge_widths for l, cw in o.items()} == {l: cw.edge_widths for l, cw in s.items()}


# ---------------------------------------------------------------------------
# MR4 — capacity consume decomposes by batch
# ---------------------------------------------------------------------------


def test_mr4_consume_decomposes_by_batch():
    rules = _fake_rules(
        {"A1": (0.5, 0.2), "A2": (0.3, 0.1), "B1": (0.4, 0.15)}
    )
    topo_a = {"A1": _net_topo("A1", ["e1", "e2"]), "A2": _net_topo("A2", ["e1"])}
    topo_b = {"B1": _net_topo("B1", ["e2", "e3"])}
    nets_a = [_make_net("A1", 1), _make_net("A2", 1)]
    nets_b = [_make_net("B1", 1)]

    for arm in (_oracle, _shim):
        incremental: dict[str, float] = {}
        arm._consume_capacity(incremental, topo_a, nets_a, rules)
        arm._consume_capacity(incremental, topo_b, nets_b, rules)

        union: dict[str, float] = {}
        arm._consume_capacity(union, {**topo_a, **topo_b}, nets_a + nets_b, rules)
        assert incremental == union, f"{arm} violates MR4"

    inc_o: dict[str, float] = {}
    inc_s: dict[str, float] = {}
    _oracle._consume_capacity(inc_o, topo_a, nets_a, rules)
    _oracle._consume_capacity(inc_o, topo_b, nets_b, rules)
    _shim._consume_capacity(inc_s, topo_a, nets_a, rules)
    _shim._consume_capacity(inc_s, topo_b, nets_b, rules)
    assert inc_o == inc_s
    assert inc_o == {"e1": 1.1, "e2": 1.25, "e3": 0.55}

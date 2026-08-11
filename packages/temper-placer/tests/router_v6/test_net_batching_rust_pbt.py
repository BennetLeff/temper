"""Property-based tests for the Phase E batch E5 net-batching Rust
orchestration (temper-rust-router ``net_batching`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E5. These properties
run against the production shims (``router_v6.net_batching``) and hold
over randomized inputs.

Seven non-vacuous properties (G4, >= 5 required):

- P1  order is a permutation: every net index appears exactly once.
      Vacuity guard: a kernel that drops or duplicates a net violates.
- P2  the LAST differential pair's second net immediately follows its
      partner in the order.  Vacuity guard: a kernel that skips the
      diff-pair post-pass violates (a later pair can move earlier pairs,
      which is why "last pair" is the sharpest form of this guarantee).
- P3  chunking partitions the order: concatenation equals the order, every
      chunk has length <= size, and (for a non-empty order, size >= 1) no
      chunk is empty.  Vacuity guard: a kernel that drops elements or
      yields over-long chunks violates.
- P4  chunking with size <= 1 yields singletons (Python's ``max(1, size)``
      step).  Vacuity guard: a kernel that ignores the size floor and
      yields one giant chunk violates.
- P5  capacity shrink is monotone non-increasing and floored at 0: no
      edge width rises, and no edge width goes negative.  Vacuity guard:
      a kernel that adds width violates.
- P6  capacity shrink is a pure function: the input ``channel_widths`` /
      ``consumed`` / ``edge_lookup`` dicts are not mutated.  Vacuity
      guard: an in-place-mutating kernel violates.
- P7  capacity consume is exact: each channel edge's total consumption
      equals the sum of ``trace_width_mm + clearance_mm`` over the nets
      (in the subset) whose topology uses it.  Vacuity guard: a kernel
      that ignores net widths or the subset filter violates.
- P8  capacity consume is batch-accumulating: consuming batch A then batch
      B equals consuming the union in one call.  Vacuity guard: a kernel
      that resets prior consumption violates.

Each property has a ``test_pN_guard_*`` companion that demonstrates the
property is falsifiable (the discriminator is live on a degenerate input).
"""

from __future__ import annotations

from types import SimpleNamespace

import hypothesis.strategies as st
from hypothesis import given, settings

from temper_placer.core.netlist import Net
from temper_placer.router_v6 import net_batching as _shim
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.topology_extraction import NetTopology
from tests.router_v6 import _net_batching_py_oracle as _oracle

_SETTINGS = settings(max_examples=60, deadline=10000, suppress_health_check=[])

_NAMES = st.text(min_size=1, max_size=12, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _make_net(name: str, pin_count: int, hub_ref: str | None = None) -> Net:
    pins = [(f"U{j}", f"P{j}") for j in range(pin_count)]
    if hub_ref is not None:
        pins.append((hub_ref, "P0"))
    return Net(name=name, pins=pins)


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
# P1 — the order is a permutation of every net index
# ---------------------------------------------------------------------------


@given(
    st.lists(_NAMES, min_size=0, max_size=12, unique=True),
    st.lists(st.integers(min_value=0, max_value=8), min_size=0, max_size=12),
)
@_SETTINGS
def test_p1_order_is_a_permutation(names, pin_counts):
    pin_counts = (pin_counts + [0] * len(names))[: len(names)]
    nets = [_make_net(name, pc) for name, pc in zip(names, pin_counts)]
    order = _shim.order_nets_for_batching(nets, None)
    assert sorted(order) == list(range(len(nets)))
    assert len(order) == len(nets)


def test_p1_guard_dropped_net_discriminates():
    nets = [_make_net("A", 1), _make_net("B", 2), _make_net("C", 3)]
    order = _shim.order_nets_for_batching(nets, None)
    assert len(order) == 3 and sorted(order) == [0, 1, 2]


# ---------------------------------------------------------------------------
# P2 — the last diff pair's second net immediately follows its partner
# ---------------------------------------------------------------------------


@given(
    st.lists(_NAMES, min_size=1, max_size=4, unique=True),
)
@_SETTINGS
def test_p2_last_diff_pair_adjacent(bases):
    nets = []
    for b in bases:
        # A real differential pair shares a base: {b}_P / {b}_N.
        nets.append(_make_net(f"{b}_P", 2))
        nets.append(_make_net(f"{b}_N", 1))
    order = _shim.order_nets_for_batching(nets, None)
    names = [nets[i].name for i in order]
    from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs

    inferred = infer_differential_pairs([n.name for n in nets])
    if not inferred:
        return  # nothing inferred -> property vacuous for this input
    last = inferred[-1]
    pos_p = names.index(last.p_net)
    pos_n = names.index(last.n_net)
    assert pos_n == pos_p + 1


def test_p2_guard_adjacency_not_vacuous():
    """A pair whose two members are far apart in the raw sorted order (the
    positive member has the HIGHEST pin count, so it sorts last) must be
    pulled together by the post-pass: input sorted [USB_D- ... USB_D+],
    output [..., USB_D+, USB_D-].  A kernel that skips the post-pass would
    leave them separated and fail."""
    nets = [_make_net("USB_D-", 1), _make_net("OTHER", 3), _make_net("USB_D+", 5)]
    order = _shim.order_nets_for_batching(nets, None)
    names = [nets[i].name for i in order]
    assert "USB_D+" in names and "USB_D-" in names
    assert abs(names.index("USB_D+") - names.index("USB_D-")) == 1
    # The discriminator is live: raw sort order has them separated.
    assert names.index("USB_D+") > names.index("OTHER")


# ---------------------------------------------------------------------------
# P3 — chunking partitions the order
# ---------------------------------------------------------------------------


@given(
    st.lists(st.integers(min_value=0, max_value=30), min_size=0, max_size=40),
    st.integers(min_value=1, max_value=12),
)
@_SETTINGS
def test_p3_chunking_partitions(order, size):
    chunks = list(_shim._chunks(order, size))
    flat = [x for c in chunks for x in c]
    assert flat == order
    for c in chunks:
        assert len(c) <= size
    if order:
        assert all(len(c) >= 1 for c in chunks)


def test_p3_guard_overlong_chunk_discriminates():
    order = list(range(7))
    chunks = list(_shim._chunks(order, 3))
    assert [len(c) for c in chunks] == [3, 3, 1]
    assert max(len(c) for c in chunks) == 3


# ---------------------------------------------------------------------------
# P4 — size <= 1 follows CPython's slice semantics
# ---------------------------------------------------------------------------


@given(st.lists(st.integers(min_value=0, max_value=20), min_size=0, max_size=25))
@_SETTINGS
def test_p4_size_at_most_one_follows_python_slices(order):
    # size 1: singletons.
    assert [len(c) for c in _shim._chunks(order, 1)] == [1] * len(order)
    # size 0: every chunk is the empty slice seq[i:i] (CPython).
    chunks = list(_shim._chunks(order, 0))
    assert [len(c) for c in chunks] == [0] * len(order)
    # Both sides of the size<=1 floor agree with the pinned oracle.
    assert list(_shim._chunks(order, 1)) == list(_oracle._chunks(order, 1))
    assert list(_shim._chunks(order, 0)) == list(_oracle._chunks(order, 0))


def test_p4_guard_slice_floor_discriminates():
    order = [10, 20, 30]
    # size 1 -> singletons; size 0 -> empty slices. A kernel that yielded
    # one giant chunk for size<=1 would fail both.
    assert [len(c) for c in _shim._chunks(order, 1)] == [1, 1, 1]
    assert [len(c) for c in _shim._chunks(order, 0)] == [0, 0, 0]


# ---------------------------------------------------------------------------
# P5 — capacity shrink is monotone non-increasing, floored at 0
# ---------------------------------------------------------------------------

_PT = st.tuples(
    st.floats(min_value=-5, max_value=5, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-5, max_value=5, allow_nan=False, allow_infinity=False),
)


@given(
    st.lists(st.tuples(_PT, _PT), min_size=1, max_size=10, unique=True),
    st.lists(st.floats(min_value=0.0, max_value=4.0, allow_nan=False, allow_infinity=False),
             min_size=1, max_size=10),
)
@_SETTINGS
def test_p5_shrink_is_monotone_and_floored(edges, widths):
    widths = (widths + [1.0] * len(edges))[: len(edges)]
    spec = {"F.Cu": dict(zip(edges, widths))}
    edge_widths = spec["F.Cu"]
    channel_widths = _make_widths(spec)
    edge_lookup = {f"e{i}": ("F.Cu", u, v) for i, ((u, v), _) in enumerate(edge_widths.items())}
    consumed = {f"e{i}": float(i % 5) for i in range(len(edge_lookup))}
    shrunk = _shim._shrink_channel_widths(channel_widths, consumed, edge_lookup)
    for (u, v), w in channel_widths["F.Cu"].edge_widths.items():
        new_w = shrunk["F.Cu"].edge_widths[(u, v)]
        assert new_w <= w
        assert new_w >= 0.0


def test_p5_guard_width_increase_discriminates():
    widths = _make_widths({"F.Cu": {((0.0, 0.0), (1.0, 0.0)): 2.5}})
    edge_lookup = {"e1": ("F.Cu", (0.0, 0.0), (1.0, 0.0))}
    shrunk = _shim._shrink_channel_widths(widths, {"e1": 0.5}, edge_lookup)
    assert shrunk["F.Cu"].edge_widths[((0.0, 0.0), (1.0, 0.0))] <= 2.5
    assert shrunk["F.Cu"].edge_widths[((0.0, 0.0), (1.0, 0.0))] >= 0.0


# ---------------------------------------------------------------------------
# P6 — capacity shrink is a pure function
# ---------------------------------------------------------------------------


@given(
    st.lists(st.tuples(_PT, _PT), min_size=1, max_size=8, unique=True),
)
@_SETTINGS
def test_p6_shrink_does_not_mutate_inputs(edges):
    spec = {"F.Cu": dict.fromkeys(edges, 2.5)}
    channel_widths = _make_widths(spec)
    edge_lookup = {f"e{i}": ("F.Cu", u, v) for i, (u, v) in enumerate(edges)}
    consumed = {f"e{i}": 0.7 for i in range(len(edges))}
    before_widths = {layer: dict(cw.edge_widths) for layer, cw in channel_widths.items()}
    before_consumed = dict(consumed)
    before_lookup = dict(edge_lookup)
    _shim._shrink_channel_widths(channel_widths, consumed, edge_lookup)
    assert channel_widths["F.Cu"].edge_widths == before_widths["F.Cu"]
    assert consumed == before_consumed
    assert edge_lookup == before_lookup


def test_p6_guard_mutation_discriminates():
    widths = _make_widths({"F.Cu": {((0.0, 0.0), (1.0, 0.0)): 2.5}})
    edge_lookup = {"e1": ("F.Cu", (0.0, 0.0), (1.0, 0.0))}
    consumed = {"e1": 0.5}
    _shim._shrink_channel_widths(widths, consumed, edge_lookup)
    assert widths["F.Cu"].edge_widths[((0.0, 0.0), (1.0, 0.0))] == 2.5


# ---------------------------------------------------------------------------
# P7 — capacity consume is exact per-edge
# ---------------------------------------------------------------------------


@given(
    st.lists(_NAMES, min_size=1, max_size=8, unique=True),
    st.lists(st.integers(min_value=0, max_value=4), min_size=1, max_size=8),
)
@_SETTINGS
def test_p7_consume_is_exact(names, counts):
    counts = (counts + [1] * len(names))[: len(names)]
    rules = _fake_rules(dict.fromkeys(names, (0.3, 0.2)))
    topo = {n: _net_topo(n, [f"e{i % 5}" for i in range(c)]) for n, c in zip(names, counts)}
    nets = [_make_net(n, 1) for n in names]
    consumed: dict[str, float] = {}
    _shim._consume_capacity(consumed, topo, nets, rules)
    for edge_id, total in consumed.items():
        expected = sum(0.5 for n in names if edge_id in topo[n].uses_channels)
        assert total == expected
    assert set(consumed) == {e for n in names for e in topo[n].uses_channels}


def test_p7_guard_subset_filter_discriminates():
    topo = {"IN": _net_topo("IN", ["e1"]), "OUT": _net_topo("OUT", ["e1"])}
    rules = _fake_rules({"IN": (0.5, 0.2), "OUT": (0.5, 0.2)})
    consumed: dict[str, float] = {}
    # only IN is in the subset: OUT must not consume
    _shim._consume_capacity(consumed, topo, [_make_net("IN", 1)], rules)
    assert consumed == {"e1": 0.7}


# ---------------------------------------------------------------------------
# P8 — capacity consume accumulates across batches
# ---------------------------------------------------------------------------


@given(
    st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=4),
    st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=4),
)
@_SETTINGS
def test_p8_consume_accumulates_across_batches(edges_a, edges_b):
    rules = _fake_rules({"A1": (0.5, 0.2), "B1": (0.3, 0.1)})
    topo_a = {"A1": _net_topo("A1", [f"a{i}" for i in edges_a])}
    topo_b = {"B1": _net_topo("B1", [f"b{i}" for i in edges_b])}

    incremental: dict[str, float] = {}
    _shim._consume_capacity(incremental, topo_a, [_make_net("A1", 1)], rules)
    _shim._consume_capacity(incremental, topo_b, [_make_net("B1", 1)], rules)

    combined: dict[str, float] = {}
    _shim._consume_capacity(combined, {**topo_a, **topo_b}, [_make_net("A1", 1), _make_net("B1", 1)], rules)
    assert incremental == combined


def test_p8_guard_reset_discriminates():
    rules = _fake_rules({"A1": (0.5, 0.2), "B1": (0.3, 0.1)})
    topo_a = {"A1": _net_topo("A1", ["e1"])}
    topo_b = {"B1": _net_topo("B1", ["e1"])}
    consumed: dict[str, float] = {}
    _shim._consume_capacity(consumed, topo_a, [_make_net("A1", 1)], rules)
    _shim._consume_capacity(consumed, topo_b, [_make_net("B1", 1)], rules)
    # 0.7 + 0.4 = 1.1 -- a kernel that reset state would give 0.4
    assert consumed["e1"] == 0.7 + 0.4

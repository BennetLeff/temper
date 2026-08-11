"""Differential oracle tests: the core graph/geometry cluster.

Wave 4, unit ``core_graph_cluster``: the tractable kernels behind seven of
the nine modules ``temper_placer/core/{graph, hypergraph, pin_geometry,
power_topology, topology, courtyard, geometry_types}.py``, migrated to
``packages/temper-geometry/src/core_graph_geometry.rs`` (home crate:
``temper-geometry``). ``community.py`` and ``loop_ownership.py`` are
JUSTIFIED-KEEP (see VERIFICATION.md) and carry no differential here.

G1 (TDD): the oracle blocks below are verbatim copies of the pre-migration
implementation (origin/main, before this branch) — DO NOT EDIT, they are the
reference. The production imports are the delegation shims; after the
migration they call the Rust kernels, and every assertion drives IDENTICAL
inputs through both sides.

Comparison conventions:
- numpy arrays compared as ``(dtype, shape, tobytes())`` — bit-exact;
- scalar floats compared via ``float.hex()`` — bit-exact;
- shapely polygon vertex sequences compared as ``(x.hex(), y.hex())``.

Verification unit (per G4 cluster rule): the seven migrated modules are one
unit behind this shared oracle + corpus. Module-to-property map (with
test_core_graph_cluster_pbt.py):
  graph.py:            P1 (clique coverage + order), P2 (batch offsets),
                       MR1 (net-list permutation)
  hypergraph.py:       P3 (degree == H @ ones), MR2 (triplet-order invariance)
  pin_geometry.py:     P4 (quadrant rotation law), MR3 (mirror commutation)
  power_topology.py:   P5 (threshold lattice)
  topology.py:         P6 (partition correctness), MR4 (edge-order invariance)
  courtyard.py:        P7 (global == local + transform), MR5 (rotation ladder)
  geometry_types.py:   P8 (radius == hypot(w,h)/2 law), MR6 (distance symmetry)

The differential corpus below also pins the numpy-constructor edge cases that
PBT does not reach: the empty-netlist branches, the ``Coo`` length-extension
and negative-index semantics, the ``batch_graphs([])`` ValueError, and the
``Pin``/``Component`` override plumbing in ``pin_world_position_at``.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
from shapely.affinity import rotate as _s_rotate
from shapely.affinity import translate as _s_translate
from shapely.geometry import Polygon as _SPolygon

from temper_placer.core.courtyard import Courtyard, check_overlap
from temper_placer.core.geometry_types import Pad, Point, Track
from temper_placer.core.graph import NetlistGraph, batch_graphs, netlist_to_graph
from temper_placer.core.hypergraph import Coo
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.pin_geometry import _normalize_rotation, pin_world_position_at
from temper_placer.core.power_topology import (
    IPC2221Rule,
    PowerDeliveryStrategy,
    PowerRailSpec,
)
from temper_placer.core.topology import TopologicalGraph

# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/graph.py` (origin/main,
# pre-migration). DO NOT EDIT — these are the reference implementations.
# (Method-based kernels elsewhere in this file are transcribed as standalone
# functions with `self.<field>` reads replaced by explicit parameters — the
# only faithful way to pin a method body without the full class — with every
# arithmetic expression byte-identical.)
# ============================================================================


def _oracle_netlist_to_graph(netlist):
    """
    Convert a netlist to a graph representation.

    Args:
        netlist: The netlist to convert.

    Returns:
        NetlistGraph instance.
    """

    # 1. Node Features: [Area, PinCount, Fixed]
    areas = np.array([c.width * c.height for c in netlist.components])
    pin_counts = np.array([len(c.pins) for c in netlist.components])
    fixed = np.array([1.0 if c.fixed else 0.0 for c in netlist.components])

    nodes = np.stack([areas, pin_counts, fixed], axis=-1)

    # 2. Edges (Clique expansion of nets)
    edge_sources = []
    edge_targets = []
    edge_weights = []

    comp_refs = {c.ref: i for i, c in enumerate(netlist.components)}

    for net in netlist.nets:
        # Get component indices in this net
        indices = list({comp_refs[p[0]] for p in net.pins if p[0] in comp_refs})

        # Clique expansion: connect all pairs
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                u, v = indices[i], indices[j]
                edge_sources.append(u)
                edge_targets.append(v)
                edge_weights.append(net.weight)

    if not edge_sources:
        edges = np.zeros((0, 2), dtype=np.int32)
        weights = np.zeros((0,))
    else:
        edges = np.stack([np.array(edge_sources), np.array(edge_targets)], axis=-1)
        weights = np.array(edge_weights)

    return NetlistGraph(nodes=nodes, edges=edges, edge_weights=weights)


def _oracle_batch_graphs(graphs):
    """
    Batch multiple graphs into a single large disconnected graph.

    Shifts edge indices to maintain graph structure in the unified representation.

    Args:
        graphs: List of NetlistGraph instances.

    Returns:
        Unified NetlistGraph.
    """
    all_nodes = np.concatenate([g.nodes for g in graphs], axis=0)

    shifted_edges = []
    offset = 0
    for g in graphs:
        shifted_edges.append(g.edges + offset)
        offset += g.nodes.shape[0]

    all_edges = np.concatenate(shifted_edges, axis=0)
    all_weights = np.concatenate([g.edge_weights for g in graphs], axis=0)

    return NetlistGraph(nodes=all_nodes, edges=all_edges, edge_weights=all_weights)


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/hypergraph.py`'s
# `Coo.__matmul__` (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================


def _oracle_coo_matmul(row, col, data, shape, other):
    n_rows = shape[0]
    if int(data.shape[0]) == 0:
        return np.zeros(n_rows, dtype=np.float64)
    contributions = data.astype(np.float64) * other[col]
    return np.bincount(row, weights=contributions, minlength=n_rows)


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/pin_geometry.py`
# (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================

from temper_placer.geometry.kicad_transform import rotate_local_to_world  # noqa: E402


def _oracle_normalize_rotation(rotation):
    """Normalize a rotation value to radians.

    int values are treated as rotation indices (0-3 -> 0/90/180/270 deg),
    matching the convention used by Component.initial_rotation.
    float values are treated as radians and used as-is.
    None is treated as 0 (no rotation).
    """
    if rotation is None:
        return 0.0
    if isinstance(rotation, int):
        return rotation * math.pi / 2.0
    return float(rotation)


def _oracle_pin_world_position_at(pin, comp, pos_override=None, rotation_override=None):
    """Return the world (x, y) position of a pin, with optional overrides.

    Like :func:`pin_world_position` but accepts an explicit `pos_override`
    for the component's board position and/or `rotation_override` for the
    component's rotation index (0-3). When an override is provided, it
    replaces the corresponding ``comp.initial_*`` attribute.
    When None, falls back to ``comp.initial_*``.

    This is the canonical implementation; `pin_world_position` delegates to it.

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.
        pos_override: Optional (x, y) tuple overriding the component position.
            When None, uses ``comp.initial_position``.
        rotation_override: Optional rotation index (0-3) overriding
            ``comp.initial_rotation``. When None, uses ``comp.initial_rotation``.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    rot_source = rotation_override if rotation_override is not None else comp.initial_rotation
    rotation_rad = _oracle_normalize_rotation(rot_source)
    side = comp.initial_side or 0

    px, py = pin.position

    if side == 1:
        px = -px

    rx, ry = rotate_local_to_world(px, py, rotation_rad)

    cpos = pos_override if pos_override is not None else comp.initial_position or (0.0, 0.0)
    return (cpos[0] + rx, cpos[1] + ry)


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/power_topology.py`
# (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================


def _oracle_required_trace_width(max_current_a):
    return max_current_a * 0.15 + 0.1


def _oracle_delivery_strategy(max_current_a):
    if max_current_a >= 3.0:
        return PowerDeliveryStrategy.PLANE
    elif max_current_a >= 1.0:
        return PowerDeliveryStrategy.WIDE_TRACE
    else:
        return PowerDeliveryStrategy.STANDARD_TRACE


def _oracle_ipc2221_trace_width(copper_weight_oz, max_current_a):
    base_width = max_current_a * 0.15 + 0.1
    if copper_weight_oz == 1.0:
        return base_width
    else:
        return base_width / (copper_weight_oz**0.625)


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/topology.py`'s
# `TopologicalGraph.get_clusters` (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================


def _oracle_get_clusters(nodes, adjacency_edges):
    """Identify connected components in the adjacency graph.

    Connected components represent clusters of components that must stay
    relatively close to each other.
    """
    parent = {node: node for node in nodes}

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for a, b, _ in adjacency_edges:
        union(a, b)

    clusters_dict = {}
    for node in nodes:
        root = find(node)
        if root not in clusters_dict:
            clusters_dict[root] = set()
        clusters_dict[root].add(node)

    return list(clusters_dict.values())


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/courtyard.py`'s
# `Courtyard.get_global_polygon` (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================

from temper_placer.geometry.kicad_transform import (  # noqa: E402
    shapely_rotation_angle_deg,
)


def _oracle_courtyard_get_global_polygon(points, rotation_idx, x, y):
    """
    Transform local courtyard to global coordinates.
    rotation_idx: 0=0deg, 1=90deg, 2=180deg, 3=270deg, matching a
    footprint's raw KiCad board rotation (``fp.position.angle``).
    """
    angle = rotation_idx * 90.0
    rotated = _s_rotate(_SPolygon(points), shapely_rotation_angle_deg(angle), origin=(0, 0))
    return _s_translate(rotated, xoff=x, yoff=y)


# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/geometry_types.py`
# (origin/main, pre-migration). DO NOT EDIT.
# ============================================================================


def _oracle_point_distance(x, y, ox, oy):
    return math.hypot(x - ox, y - oy)


def _oracle_track_midpoint(sx, sy, ex, ey):
    return (
        (sx + ex) / 2,
        (sy + ey) / 2,
    )


def _oracle_pad_radius(w, h):
    return (w**2 + h**2) ** 0.5 / 2


# ============================================================================
# Bit-exact comparison helpers
# ============================================================================


def _assert_bit_exact(a, b):
    assert a.dtype == b.dtype, f"dtype {a.dtype} != {b.dtype}"
    assert a.shape == b.shape, f"shape {a.shape} != {b.shape}"
    assert a.tobytes() == b.tobytes(), "bit pattern mismatch"


def _assert_float_bit_exact(a, b):
    assert float(a).hex() == float(b).hex(), f"{a!r} != {b!r}"


def _assert_point_bit_exact(pa, pb):
    _assert_float_bit_exact(pa[0], pb[0])
    _assert_float_bit_exact(pa[1], pb[1])


# ============================================================================
# Random netlist corpus
# ============================================================================


def _random_netlist(rng, n_components, n_nets, max_pins_per_net=7):
    comps = []
    for i in range(n_components):
        w = round(rng.uniform(0.4, 9.0), 6)
        h = round(rng.uniform(0.4, 9.0), 6)
        c = Component(ref=f"C{i}", footprint="0603", bounds=(w, h))
        c.fixed = rng.random() < 0.3
        c.pins.extend([None] * rng.randint(0, 12))
        c.initial_position = (round(rng.uniform(-50.0, 50.0), 6), round(rng.uniform(-50.0, 50.0), 6))
        c.initial_rotation = rng.choice([None, 0, 1, 2, 3])
        c.initial_side = rng.choice([None, 0, 1])
        comps.append(c)
    refs = [c.ref for c in comps]
    nets = []
    for i in range(n_nets):
        k = rng.randint(0, max_pins_per_net) if n_components else 0
        chosen = rng.sample(refs, k=min(k, len(refs))) if refs else []
        pins = [(r, f"P{j}") for j, r in enumerate(chosen)]
        # Occasionally inject a pin whose ref is NOT in the netlist, to
        # exercise the `if p[0] in comp_refs` filter on both sides.
        if rng.random() < 0.3 and refs:
            pins.append(("Z_GHOST", "P99"))
        nets.append(
            Net(
                name=f"N{i}",
                pins=pins,
                weight=round(rng.uniform(0.1, 5.0), 6),
            )
        )
    return Netlist(components=comps, nets=nets)


def _random_pin_geometry(rng):
    pos = (round(rng.uniform(-10.0, 10.0), 6), round(rng.uniform(-10.0, 10.0), 6))
    comp = Component(ref="T1", footprint="0603", bounds=(1.6, 0.8))
    comp.initial_position = (round(rng.uniform(-50.0, 50.0), 6), round(rng.uniform(-50.0, 50.0), 6))
    comp.initial_rotation = rng.choice([None, 0, 1, 2, 3])
    comp.initial_side = rng.choice([None, 0, 1])
    rot_override = rng.choice([None, 0, 1, 2, 3])
    pos_override = (
        None if rng.random() < 0.4 else (round(rng.uniform(-50.0, 50.0), 6), round(rng.uniform(-50.0, 50.0), 6))
    )
    # float rotation source (radians, per _normalize_rotation)
    float_rot = rng.choice([None, None, rng.uniform(-6.0, 6.0)])
    return pos, comp, rot_override, pos_override, float_rot


def _rand_points(rng, n, spread=10.0):
    return [
        (round(rng.uniform(-spread, spread), 6), round(rng.uniform(-spread, spread), 6))
        for _ in range(n)
    ]


# ============================================================================
# graph.py
# ============================================================================


def test_netlist_to_graph_bit_exact_random():
    rng = random.Random(20260808)
    for _ in range(40):
        nl = _random_netlist(rng, rng.randint(0, 12), rng.randint(0, 14))
        got = netlist_to_graph(nl)
        want = _oracle_netlist_to_graph(nl)
        _assert_bit_exact(got.nodes, want.nodes)
        _assert_bit_exact(got.edges, want.edges)
        _assert_bit_exact(got.edge_weights, want.edge_weights)


def test_netlist_to_graph_empty_netlist():
    nl = Netlist(components=[], nets=[])
    got = netlist_to_graph(nl)
    want = _oracle_netlist_to_graph(nl)
    _assert_bit_exact(got.nodes, want.nodes)  # (0, 3)
    _assert_bit_exact(got.edges, want.edges)  # (0, 2) int32 empty branch
    _assert_bit_exact(got.edge_weights, want.edge_weights)


def test_netlist_to_graph_clique_order_matches_set_iteration():
    # The clique pair ORDER must come from the oracle's CPython set
    # iteration over the same pin list — a sorted/reordered expansion would
    # differ on a net with >2 members.
    comps = [Component(ref=f"C{i}", footprint="0603", bounds=(1.0, 2.0)) for i in range(5)]
    for c in comps:
        c.pins.extend([None, None])
    net = Net(name="N0", pins=[(c.ref, "1") for c in comps])
    nl = Netlist(components=comps, nets=[net])
    got = netlist_to_graph(nl)
    want = _oracle_netlist_to_graph(nl)
    _assert_bit_exact(got.edges, want.edges)
    _assert_bit_exact(got.edge_weights, want.edge_weights)
    assert got.edges.shape[0] == 10  # C(5, 2)


def test_batch_graphs_bit_exact_random():
    rng = random.Random(4242)
    for _ in range(30):
        graphs = [
            netlist_to_graph(_random_netlist(rng, rng.randint(1, 8), rng.randint(0, 6)))
            for _ in range(rng.randint(1, 5))
        ]
        got = batch_graphs(graphs)
        want = _oracle_batch_graphs(graphs)
        _assert_bit_exact(got.nodes, want.nodes)
        _assert_bit_exact(got.edges, want.edges)
        _assert_bit_exact(got.edge_weights, want.edge_weights)


def test_batch_graphs_empty_input_raises_like_numpy():
    with pytest.raises(ValueError):
        _oracle_batch_graphs([])
    with pytest.raises(ValueError):
        batch_graphs([])


# ============================================================================
# hypergraph.py — Coo @ vector
# ============================================================================


def _random_coo(rng, max_nnz=12):
    n_rows = rng.randint(0, 6)
    n_cols = rng.randint(0, 6)
    nnz = rng.randint(0, max_nnz)
    # A zero-width dimension admits no valid triplet (col < n_cols / row <
    # n_rows are both unsatisfiable), so such matrices are forced empty —
    # matching what the factory could ever produce.
    if n_rows == 0 or n_cols == 0:
        nnz = 0
    row = np.array([rng.randint(0, max(n_rows, 1)) for _ in range(nnz)], dtype=np.int64)
    col = np.array([rng.randint(0, max(n_cols, 1)) for _ in range(nnz)], dtype=np.int64)
    if n_cols:
        col = np.clip(col, 0, n_cols - 1)
    if n_rows:
        row = np.clip(row, 0, n_rows - 1)
    if rng.random() < 0.5:
        data = np.array([rng.uniform(-5.0, 5.0) for _ in range(nnz)], dtype=np.float64)
    else:
        data = np.array([rng.randint(0, 4) for _ in range(nnz)], dtype=np.int64)
    other = np.array([rng.uniform(-5.0, 5.0) for _ in range(n_cols)], dtype=np.float64)
    return row, col, data, (n_rows, n_cols), other


def test_coo_matmul_bit_exact_random():
    rng = random.Random(777)
    for _ in range(40):
        row, col, data, shape, other = _random_coo(rng)
        coo = Coo(row=row, col=col, data=data, shape=shape)
        got = coo @ other
        want = _oracle_coo_matmul(row, col, data, shape, other)
        _assert_bit_exact(got, want)


def test_coo_matmul_length_extension_matches_bincount():
    # row index >= n_rows extends the result to max(row) + 1, exactly as
    # np.bincount's minlength semantics do.
    row = np.array([0, 5], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([1.5, 2.5], dtype=np.float64)
    shape = (2, 2)
    other = np.array([1.0, 1.0], dtype=np.float64)
    coo = Coo(row=row, col=col, data=data, shape=shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert got.shape[0] == 6


def test_coo_matmul_negative_col_wraps():
    row = np.array([0], dtype=np.int64)
    col = np.array([-1], dtype=np.int64)
    data = np.array([2.0], dtype=np.float64)
    shape = (1, 3)
    other = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    coo = Coo(row=row, col=col, data=data, shape=shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert float(got[0]) == 6.0


def test_coo_matmul_nan_and_empty():
    row = np.array([0, 1], dtype=np.int64)
    col = np.array([0, 1], dtype=np.int64)
    data = np.array([np.nan, 1.0], dtype=np.float64)
    shape = (2, 2)
    other = np.array([1.0, 2.0], dtype=np.float64)
    coo = Coo(row=row, col=col, data=data, shape=shape)
    got = coo @ other
    want = _oracle_coo_matmul(row, col, data, shape, other)
    _assert_bit_exact(got, want)
    assert math.isnan(got[0]) and float(got[1]) == 2.0

    empty = Coo(row=np.array([], dtype=np.int64), col=np.array([], dtype=np.int64),
                data=np.array([], dtype=np.float64), shape=(3, 4))
    want = _oracle_coo_matmul(empty.row, empty.col, empty.data, empty.shape,
                              np.zeros(4))
    _assert_bit_exact(empty @ np.zeros(4), want)


def test_coo_degrees_match_oracle():
    # The two real consumers: H @ ones (node degrees) and H.T @ ones
    # (hyperedge degrees), order-invariant scatter-adds.
    rng = random.Random(99)
    for _ in range(20):
        row, col, data, shape, _ = _random_coo(rng)
        coo = Coo(row=row, col=col, data=data, shape=shape)
        other = np.ones(shape[1], dtype=np.float64)
        got = coo @ other
        want = _oracle_coo_matmul(row, col, data, shape, other)
        _assert_bit_exact(got, want)


# ============================================================================
# pin_geometry.py
# ============================================================================


class _PinStub:
    """Minimal pin duck-type: only `position` is read by the oracle."""

    def __init__(self, position):
        self.position = position


def test_normalize_rotation_bit_exact():
    for value in [None, 0, 1, 2, 3, -1, 7, 0.0, 1.5, math.pi, -2.75, float("inf"), float("nan")]:
        got = _normalize_rotation(value)
        want = _oracle_normalize_rotation(value)
        if isinstance(value, float) and math.isnan(value):
            assert math.isnan(got) and math.isnan(want)
        else:
            _assert_float_bit_exact(got, want)


def test_pin_world_position_bit_exact_random():
    rng = random.Random(31337)
    for _ in range(40):
        pos, comp, rot_override, pos_override, float_rot = _random_pin_geometry(rng)
        pin = _PinStub(pos)
        # rotation source: override, or the component's, or a float radian
        src = float_rot if float_rot is not None else rot_override
        if src is None:
            comp.initial_rotation = None
        kwargs = {}
        if rot_override is not None:
            kwargs["rotation_override"] = rot_override
        if float_rot is not None:
            kwargs["rotation_override"] = float_rot  # float source path
        if pos_override is not None:
            kwargs["pos_override"] = pos_override
        got = pin_world_position_at(pin, comp, **kwargs)
        want = _oracle_pin_world_position_at(pin, comp, **kwargs)
        _assert_point_bit_exact(got, want)


def test_pin_world_position_all_quadrants_sides():
    rng = random.Random(5)
    for rot in [0, 1, 2, 3]:
        for side in [0, 1]:
            for _ in range(5):
                pin = _PinStub((round(rng.uniform(-5, 5), 6), round(rng.uniform(-5, 5), 6)))
                comp = Component(ref="T", footprint="0603", bounds=(1, 1))
                comp.initial_position = (round(rng.uniform(-20, 20), 6), round(rng.uniform(-20, 20), 6))
                comp.initial_rotation = rot
                comp.initial_side = side
                got = pin_world_position_at(pin, comp)
                want = _oracle_pin_world_position_at(pin, comp)
                _assert_point_bit_exact(got, want)


# ============================================================================
# power_topology.py
# ============================================================================


def test_required_trace_width_bit_exact():
    rng = random.Random(11)
    for i in [0.0, 0.1, 0.999, 1.0, 1.5, 2.999, 3.0, 5.0, 20.0] + [
        rng.uniform(0.0, 50.0) for _ in range(30)
    ]:
        rail = PowerRailSpec(
            net_name="+X", max_current_a=i, voltage_v=1.0,
            source_component="S", sink_components=(),
        )
        _assert_float_bit_exact(rail.required_trace_width(), _oracle_required_trace_width(i))


def test_ipc2221_trace_width_bit_exact():
    rng = random.Random(22)
    for oz in [1.0, 0.5, 2.0, 3.0, 0.25] + [rng.uniform(0.2, 4.0) for _ in range(25)]:
        for i in [0.5, 1.0, 3.0] + [rng.uniform(0.0, 20.0) for _ in range(5)]:
            rule = IPC2221Rule(copper_weight_oz=oz, temp_rise_c=10.0)
            rail = PowerRailSpec(
                net_name="+X", max_current_a=i, voltage_v=1.0,
                source_component="S", sink_components=(),
            )
            got = rule.trace_width(rail)
            want = _oracle_ipc2221_trace_width(oz, i)
            _assert_float_bit_exact(got, want)


def test_delivery_strategy_bit_exact():
    for i in [0.0, 0.999, 1.0, 1.5, 2.999, 3.0, 5.0, float("nan"), float("-inf")]:
        rail = PowerRailSpec(
            net_name="+X", max_current_a=i, voltage_v=1.0,
            source_component="S", sink_components=(),
        )
        got = rail.delivery_strategy()
        want = _oracle_delivery_strategy(i)
        assert got is want, f"current {i!r}: {got} vs {want}"


def test_power_tree_flatten_and_find_unchanged():
    # Structural traversal stays Python — assert the public API still agrees
    # with itself across a build (guard against shim regressions).
    from temper_placer.core.power_topology import TemperPowerTopology

    tree = TemperPowerTopology.create()
    flat = [r.net_name for r in tree.flatten()]
    assert flat == ["+15V", "+5V", "+3V3", "VCC_BOOT"]
    assert tree.find_rail("+3V3") is not None
    assert tree.find_rail("NOPE") is None


# ============================================================================
# topology.py — get_clusters
# ============================================================================


def test_get_clusters_bit_exact_random():
    rng = random.Random(808)
    for _ in range(40):
        nodes = [f"N{i}" for i in range(rng.randint(0, 10))]
        edges = []
        for _ in range(rng.randint(0, 12)):
            if len(nodes) < 2:
                break
            a, b = rng.sample(nodes, 2)
            edges.append((a, b, round(rng.uniform(0.1, 5.0), 6)))
        g = TopologicalGraph()
        for n in nodes:
            g.add_node(n)
        for a, b, d in edges:
            g.add_adjacency(a, b, d)
        got = g.get_clusters()
        want = _oracle_get_clusters(g.nodes, g.adjacency_edges)
        assert got == want, f"nodes={nodes} edges={edges}\ngot={got}\nwant={want}"


def test_get_clusters_empty_and_singleton():
    g = TopologicalGraph()
    assert g.get_clusters() == []
    g.add_node("A")
    assert g.get_clusters() == [{"A"}]
    g.add_adjacency("A", "B", 1.0)
    assert g.get_clusters() == [{"A", "B"}]


def test_get_clusters_group_order_is_first_appearance():
    # Two disconnected components; the group containing the FIRST node must
    # come first regardless of union order.
    g = TopologicalGraph()
    g.add_adjacency("Z", "Y", 1.0)
    g.add_adjacency("A", "B", 1.0)
    got = g.get_clusters()
    want = _oracle_get_clusters(g.nodes, g.adjacency_edges)
    assert got == want
    assert got[0] == {"Z", "Y"}


# ============================================================================
# courtyard.py — get_global_polygon vertices (the transformed part)
# ============================================================================


def _coords(poly):
    return list(poly.exterior.coords)


def test_courtyard_global_polygon_vertices_bit_exact():
    rng = random.Random(2026)
    for _ in range(40):
        points = _rand_points(rng, rng.randint(3, 8))
        rot = rng.randint(0, 3)
        x, y = round(rng.uniform(-50, 50), 6), round(rng.uniform(-50, 50), 6)
        c = Courtyard(component_ref="U1", points=points)
        got = _coords(c.get_global_polygon(x, y, rot))
        want = _coords(_oracle_courtyard_get_global_polygon(points, rot, x, y))
        assert len(got) == len(want)
        for (gx, gy), (wx, wy) in zip(got, want):
            _assert_float_bit_exact(gx, wx)
            _assert_float_bit_exact(gy, wy)


def test_courtyard_rotation_ladder_quadrant_exact():
    # rotation_idx 0-3 must produce EXACT quadrant transforms (shapely zeroes
    # cosp/sinp below 2.5e-16, so 90° is exactly (y, -x) locally).
    points = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    for rot in range(4):
        c = Courtyard(component_ref="U1", points=points)
        got = _coords(c.get_global_polygon(3.0, 4.0, rot))
        want = _coords(_oracle_courtyard_get_global_polygon(points, rot, 3.0, 4.0))
        for (gx, gy), (wx, wy) in zip(got, want):
            _assert_float_bit_exact(gx, wx)
            _assert_float_bit_exact(gy, wy)


def test_courtyard_fallback_points_match_oracle():
    # <3 points -> the fixed 0.5mm box fallback, then the transform.
    for bad in [[], [(0.0, 0.0)], [(0.0, 0.0), (1.0, 1.0)]]:
        c = Courtyard(component_ref="U1", points=bad)
        want_poly = _oracle_courtyard_get_global_polygon(c.points, 1, 2.0, 3.0)
        got = _coords(c.get_global_polygon(2.0, 3.0, 1))
        want = _coords(want_poly)
        assert len(got) == len(want)
        for (gx, gy), (wx, wy) in zip(got, want):
            _assert_float_bit_exact(gx, wx)
            _assert_float_bit_exact(gy, wy)


def test_check_overlap_agrees_with_oracle_pipeline():
    # Both sides build polygons from the SAME vertex transform inputs and let
    # shapely/GEOS do the boolean; the boolean must agree.
    rng = random.Random(600)
    for _ in range(30):
        p1 = _rand_points(rng, 4)
        p2 = _rand_points(rng, 4)
        c1 = Courtyard(component_ref="A", points=p1)
        c2 = Courtyard(component_ref="B", points=p2)
        pos1 = (round(rng.uniform(-10, 10), 6), round(rng.uniform(-10, 10), 6))
        pos2 = (round(rng.uniform(-10, 10), 6), round(rng.uniform(-10, 10), 6))
        r1, r2 = rng.randint(0, 3), rng.randint(0, 3)
        got = check_overlap(c1, pos1, r1, c2, pos2, r2)
        poly1 = _oracle_courtyard_get_global_polygon(p1, r1, pos1[0], pos1[1])
        poly2 = _oracle_courtyard_get_global_polygon(p2, r2, pos2[0], pos2[1])
        want = poly1.intersects(poly2) and not poly1.touches(poly2)
        assert got == want


# ============================================================================
# geometry_types.py
# ============================================================================


def test_point_distance_bit_exact_random():
    rng = random.Random(1001)
    for _ in range(40):
        a = Point(round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6))
        b = Point(round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6))
        _assert_float_bit_exact(a.distance_to(b), _oracle_point_distance(a.x, a.y, b.x, b.y))


def test_track_midpoint_bit_exact():
    rng = random.Random(1002)
    for _ in range(30):
        t = Track(
            start=Point(round(rng.uniform(-50, 50), 6), round(rng.uniform(-50, 50), 6)),
            end=Point(round(rng.uniform(-50, 50), 6), round(rng.uniform(-50, 50), 6)),
            width=0.5, net="N", layer=1,
        )
        m = t.midpoint()
        mx, my = _oracle_track_midpoint(t.start.x, t.start.y, t.end.x, t.end.y)
        _assert_float_bit_exact(m.x, mx)
        _assert_float_bit_exact(m.y, my)


def test_pad_radius_bit_exact_random():
    rng = random.Random(1003)
    for w, h in [(0.0, 0.0), (1.0, 1.0), (3.0, 4.0), (0.5, 2.0)] + [
        (round(rng.uniform(0.0, 10.0), 6), round(rng.uniform(0.0, 10.0), 6)) for _ in range(30)
    ]:
        pad = Pad(center=Point(0.0, 0.0), shape="rect", size=(w, h), net="N", layer=1)
        _assert_float_bit_exact(pad.radius, _oracle_pad_radius(w, h))


# ============================================================================
# Kept modules — loop_ownership.py stays Python (R3 JUSTIFIED-KEEP, see
# VERIFICATION.md). These smoke tests guard that the kept modules still import
# and run through the unchanged Python path.
# (community.py detection functions were deleted in Spike S6, 2026-08-11.)
# Community dataclass is kept as a public export.
# ============================================================================


def test_community_dataclass_constructs():
    """Community dataclass is still importable and constructable."""
    from temper_placer.core.community import Community
    c = Community(name="test", component_refs=["U1", "C1"], modularity_score=0.5)
    assert c.name == "test"
    assert c.component_refs == ["U1", "C1"]
    assert c.modularity_score == 0.5


def test_loop_ownership_build_map_still_runs():
    from temper_placer.core.loop import (
        Loop,
        LoopCollection,
        LoopPin,
        LoopPriority,
        LoopType,
    )
    from temper_placer.core.loop_ownership import build_ownership_map

    comps = [Component(ref=f"C{i}", footprint="0603", bounds=(1.0, 2.0)) for i in range(3)]
    netlist = Netlist(components=comps, nets=[])
    loop = Loop(
        name="commutation_1",
        loop_type=LoopType.COMMUTATION,
        description="commutation",
        pins=[LoopPin(component_ref=f"C{i}", pin_name="P", net_name="N") for i in range(2)],
        priority=LoopPriority.CRITICAL,
    )
    ownership = build_ownership_map(LoopCollection(loops=[loop]), netlist)
    assert "C0" in ownership.component_to_loops
    assert ownership.components_share_loop("C0", "C1")

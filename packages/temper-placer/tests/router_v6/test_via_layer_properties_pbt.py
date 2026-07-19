"""Property-based guards for the via/layer seams surfaced by issue #226's U1 spike.

Each property targets a bug class this codebase has actually shipped (see
docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md
and the #226 U1 spike findings):

- P1a/P1c (green): the 3D search's via bookkeeping works when its caller
  holds up its end — via footprints get stamped with the owning net_id,
  and cross-layer routes always report their vias.
- P1b (strict xfail): `_route_segment_3d` drops `net_id` on the floor
  (astar_core.py:818 passes positionals only, so the `net_id > 0` guard
  at :715 never fires) — routed vias get ZERO occupancy-grid protection.
  Flips to XPASS when #226 U2 plumbs the parameter through, forcing this
  guard to be enabled.
- P2 (strict xfail): `_astar_search_3d` has no `max_iter` budget, unlike
  its 2D Theta*/Lazy-Theta* siblings in the same file — the spike measured
  a 66 s unbounded exhaustion on a degenerate segment. Flips to XPASS when
  U2 adds the cap.
- P3 (green): every net's emitted `(segment ...)` entries plus its pads
  must form a single same-layer-connected component — the pure-Python
  version of the "8 unconnected items" DRC regression that shipped in
  PR #220's first U9 attempt, catchable without kicad-cli. Writing this
  property immediately found a second real bug (#229, pinned below as a
  strict xfail): pads 0<d<=0.5mm off-path are never stitched.
- P4 (green): `_assign_layer` is total, closed over routable layers, and
  currently identical to the heuristic (the completion gate). U2+ must
  consciously break the identity sub-property when divergent SSOT layers
  become routable — that is a designed tripwire, not an accident.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.adapter import _write_routes_to_content
from temper_placer.router_v6.astar_core import (
    RouteNode3D,
    _astar_search_3d,
    _route_segment_3d,
)
from temper_placer.router_v6.channel_mapping import _assign_layer
from temper_placer.router_v6.net_classification import set_single_layer_mode
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

# =========================================================================
# Helpers
# =========================================================================

_LAYERS = ("F.Cu", "B.Cu")


def _make_grids(
    width_cells: int,
    height_cells: int,
    cell_size: float = 0.1,
    layers: tuple[str, ...] = _LAYERS,
) -> dict[str, OccupancyGrid]:
    return {
        layer: OccupancyGrid(
            layer_name=layer,
            grid=np.zeros((height_cells, width_cells), dtype=np.int32),
            origin=(0.0, 0.0),
            cell_size=cell_size,
            width_cells=width_cells,
            height_cells=height_cells,
        )
        for layer in layers
    }


_grid_dims = st.integers(min_value=8, max_value=24)
_net_ids = st.integers(min_value=1, max_value=10_000)


@st.composite
def _search_scenario(draw):
    """Small empty 2-layer grid with distinct start/goal cells."""
    w = draw(_grid_dims)
    h = draw(_grid_dims)
    sx = draw(st.integers(min_value=1, max_value=w - 2))
    sy = draw(st.integers(min_value=1, max_value=h - 2))
    gx = draw(st.integers(min_value=1, max_value=w - 2))
    gy = draw(st.integers(min_value=1, max_value=h - 2))
    if (sx, sy) == (gx, gy):
        gx = sx - 1 if sx > 1 else sx + 1
    net_id = draw(_net_ids)
    return w, h, (sx, sy), (gx, gy), net_id


# =========================================================================
# P1a — the callee honors net_id: via footprints are stamped with the owner
# =========================================================================


@given(_search_scenario())
@settings(max_examples=40, deadline=15000, suppress_health_check=[HealthCheck.too_slow])
def test_search3d_stamps_via_footprint_with_owner_net_id(scenario):
    w, h, (sx, sy), (gx, gy), net_id = scenario
    grids = _make_grids(w, h)

    result = _astar_search_3d(
        RouteNode3D(sx, sy, "F.Cu"),
        RouteNode3D(gx, gy, "B.Cu"),
        grids,
        net_id=net_id,
    )

    assert result is not None, "empty grid cross-layer search must succeed"
    path, vias = result
    assert len(vias) >= 1, "start/goal on different layers requires >=1 via"

    sample = next(iter(grids.values()))
    for via_gx, via_gy in vias:
        wx, wy = sample.grid_to_world(via_gx, via_gy)
        for grid in grids.values():
            cx, cy = grid.world_to_grid(wx, wy)
            assert grid.grid[cy, cx] == net_id, (
                f"via cell ({cx},{cy}) on {grid.layer_name} not stamped with "
                f"net {net_id} (value={grid.grid[cy, cx]})"
            )


@given(_search_scenario())
@settings(max_examples=25, deadline=15000, suppress_health_check=[HealthCheck.too_slow])
def test_search3d_net_id_zero_stamps_nothing(scenario):
    """Documents the :715 guard — net_id=0 silently disables via blocking.

    This is exactly why the caller-side default is dangerous (P1b).
    """
    w, h, (sx, sy), (gx, gy), _ = scenario
    grids = _make_grids(w, h)

    result = _astar_search_3d(
        RouteNode3D(sx, sy, "F.Cu"),
        RouteNode3D(gx, gy, "B.Cu"),
        grids,
        net_id=0,
    )

    assert result is not None
    for grid in grids.values():
        assert int(grid.grid.sum()) == 0, (
            "net_id=0 must not stamp cells; if this ever changes, "
            "re-examine P1b's premise"
        )


# =========================================================================
# P1b — the caller seam (THE spike bug): routed vias must end up protected
# =========================================================================


@pytest.mark.xfail(
    strict=True,
    reason="#226 U2: _route_segment_3d never passes net_id to _astar_search_3d "
    "(astar_core.py:818) so mark_via_blocked never fires — routed vias have "
    "zero occupancy-grid protection. Remove this marker when U2 plumbs net_id.",
)
@given(_grid_dims, _grid_dims, _net_ids)
@settings(max_examples=15, deadline=15000, suppress_health_check=[HealthCheck.too_slow])
def test_route_segment_3d_leaves_via_footprint_protected(w, h, net_id):
    grids = _make_grids(w, h)
    cell = next(iter(grids.values())).cell_size
    start_world = (1.5 * cell, 1.5 * cell)
    goal_world = ((w - 2) * cell, (h - 2) * cell)

    kwargs = {}
    if "net_id" in inspect.signature(_route_segment_3d).parameters:
        kwargs["net_id"] = net_id

    result = _route_segment_3d(
        start_world, goal_world, "F.Cu", "B.Cu", grids, **kwargs
    )

    assert result is not None, "empty-grid cross-layer segment must route"
    _path, vias = result
    assert len(vias) >= 1

    blocked_cells = sum(int((g.grid != 0).sum()) for g in grids.values())
    assert blocked_cells > 0, (
        "cross-layer route completed but no cell on any layer is blocked — "
        "the via footprint is unprotected and another net can route through it"
    )


def test_cross_layer_route_reports_vias_and_both_layers():
    """Green lock-in of what the U1 spike verified: via *detection* works."""
    grids = _make_grids(16, 16)
    result = _route_segment_3d((0.25, 0.25), (1.35, 1.35), "F.Cu", "B.Cu", grids)

    assert result is not None
    path, vias = result
    assert len(vias) >= 1
    layers_seen = {layer for (_x, _y, layer) in path}
    assert {"F.Cu", "B.Cu"} <= layers_seen


# =========================================================================
# P2 — termination budget (spike bug 2): no max_iter cap on the 3D search
# =========================================================================


@pytest.mark.xfail(
    strict=True,
    reason="#226 U2: _astar_search_3d has no max_iter budget unlike its 2D "
    "Theta*/Lazy-Theta* siblings (astar_core.py:324/511) — the U1 spike "
    "measured 66 s of unbounded exhaustion. Remove this marker when U2 adds "
    "the cap (param name `max_iter` for consistency with the siblings).",
)
def test_search3d_accepts_and_honors_max_iter_budget():
    grids = _make_grids(24, 24)
    # Wall off the goal on every layer so no path exists: without a budget
    # the search exhausts the full 2-layer state space.
    for grid in grids.values():
        grid.grid[:, 12] = 1

    result = _astar_search_3d(
        RouteNode3D(2, 2, "F.Cu"),
        RouteNode3D(21, 21, "F.Cu"),
        grids,
        net_id=1,
        max_iter=10,
    )
    assert result is None, "budget-exhausted search must return None, not a path"


# =========================================================================
# P3 — emitted-content connectivity (the '8 unconnected items' class)
# =========================================================================


class _Pin:
    def __init__(self, name: str, position: tuple[float, float]):
        self.name = name
        self.position = position


class _Comp:
    def __init__(self, ref: str, pins: dict[str, tuple[float, float]]):
        self.ref = ref
        self.initial_position = (0.0, 0.0)
        self._pins = {name: _Pin(name, pos) for name, pos in pins.items()}

    def get_pin(self, name: str) -> _Pin | None:
        return self._pins.get(name)


_SEG_RE = re.compile(
    r'\(segment \(start ([\-0-9.]+) ([\-0-9.]+)\) \(end ([\-0-9.]+) ([\-0-9.]+)\)'
    r' \(width [\-0-9.]+\) \(layer "([^"]+)"\) \(net (\d+)\)'
)


def _connected_components(edges, nodes):
    parent = {n: n for n in nodes}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return {find(n) for n in nodes}


_lattice_pt = st.tuples(
    st.integers(min_value=0, max_value=20), st.integers(min_value=0, max_value=20)
)


@st.composite
def _routing_scenario(draw):
    """1-2 nets, each 2-3 pads, mixed path/plane routes on a 0.5mm lattice.

    Extra pads (beyond the two the fake path covers) are kept only when
    they sit strictly more than CONNECTION_THRESHOLD_MM (0.5mm) from every
    path vertex — pads inside that band hit the known stitch-threshold
    hole (#229), which is pinned separately as a strict xfail below.
    """
    n_nets = draw(st.integers(min_value=1, max_value=2))
    sizes = [draw(st.integers(min_value=2, max_value=3)) for _ in range(n_nets)]
    total = sum(sizes)
    pts = draw(
        st.lists(_lattice_pt, min_size=total, max_size=total, unique=True)
    )
    nets = []
    idx = 0
    for ni, size in enumerate(sizes):
        raw_pads = [(x * 0.5, y * 0.5) for x, y in pts[idx : idx + size]]
        idx += size
        is_plane = draw(st.booleans())
        if is_plane or size == 2:
            pads = raw_pads
        else:
            (x0, y0), (x1, y1) = raw_pads[0], raw_pads[1]
            vertices = [(x0, y0), (x0, y1), (x1, y1)]
            pads = raw_pads[:2] + [
                (px, py)
                for px, py in raw_pads[2:]
                if min(
                    ((px - vx) ** 2 + (py - vy) ** 2) ** 0.5 for vx, vy in vertices
                )
                > 0.5
            ]
        nets.append((f"NET{ni}", pads, is_plane))
    return nets


@given(_routing_scenario())
@settings(max_examples=50, deadline=15000, suppress_health_check=[HealthCheck.too_slow])
def test_written_segments_connect_all_pads_per_net(nets):
    components = []
    pcb_nets = []
    compiled = {}
    net_decls = []

    for idx, (net_name, pads, is_plane) in enumerate(nets, start=1):
        ref = f"U{idx}"
        pin_map = {f"P{j}": pos for j, pos in enumerate(pads)}
        components.append(_Comp(ref, pin_map))
        pcb_nets.append(
            SimpleNamespace(
                name=net_name,
                pins=[(ref, pname) for pname in pin_map],
            )
        )
        net_decls.append(f'  (net {idx} "{net_name}")')

        if is_plane:
            path = SimpleNamespace(path_length=0.0, layer_name="F.Cu")
        else:
            (x0, y0), (x1, y1) = pads[0], pads[1]
            segments = [
                (x0, y0, "F.Cu"),
                (x0, y1, "F.Cu"),
                (x1, y1, "F.Cu"),
            ]
            length = abs(y1 - y0) + abs(x1 - x0)
            path = SimpleNamespace(path_length=max(length, 0.1), segments=segments)
        compiled[net_name] = SimpleNamespace(
            net_name=net_name, width_mm=0.25, path=path
        )

    result = SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(compiled_routes=compiled)
        ),
        pcb=SimpleNamespace(components=components, nets=pcb_nets),
    )
    content = "(kicad_pcb\n" + "\n".join(net_decls) + "\n)\n"

    out = _write_routes_to_content(content, result)

    segs_by_net: dict[int, list] = {}
    for m in _SEG_RE.finditer(out):
        x1, y1, x2, y2, layer, net_num = m.groups()
        segs_by_net.setdefault(int(net_num), []).append(
            (
                (round(float(x1), 4), round(float(y1), 4), layer),
                (round(float(x2), 4), round(float(y2), 4), layer),
            )
        )

    for idx, (net_name, pads, _is_plane) in enumerate(nets, start=1):
        segs = segs_by_net.get(idx, [])
        assert segs, f"net {net_name}: no segments emitted"

        # Nodes: segment endpoints (same-layer connectivity only — there are
        # no vias in the emitted content today, so a layer mismatch between
        # a pad stub and a track is a hard disconnect. This is the property
        # PR #220's first U9 attempt violated.)
        nodes = set()
        edges = []
        for a, b in segs:
            nodes.add(a)
            nodes.add(b)
            edges.append((a, b))

        pad_nodes = []
        for px, py in pads:
            key = (round(px, 4), round(py, 4), "F.Cu")
            assert key in nodes, (
                f"net {net_name}: pad {key} untouched by any emitted segment"
            )
            pad_nodes.append(key)

        components_found = _connected_components(edges, nodes)
        adjacency: dict[tuple, set] = {n: set() for n in nodes}
        for a, b in edges:
            adjacency[a].add(b)
            adjacency[b].add(a)
        seen = set()
        stack = [pad_nodes[0]]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adjacency[n] - seen)
        for pad in pad_nodes:
            assert pad in seen, (
                f"net {net_name}: pad {pad} is in a different connected "
                f"component — the emitted routing does not join all pads "
                f"({len(components_found)} components total)"
            )


@pytest.mark.xfail(
    strict=True,
    reason="#229: stitch-threshold hole — a pad 0<d<=0.5mm off-path gets no "
    "connector (adapter.py CONNECTION_THRESHOLD_MM fires only on d>0.5, and "
    "pad copper size is unknown here). Minimal falsifying example found by "
    "the general property's mutation hunt. Remove this marker when #229 "
    "lands its measured fix.",
)
def test_pad_exactly_at_stitch_threshold_is_connected():
    nets = [("NET0", [(0.0, 0.0), (0.0, 0.5), (0.0, 1.0)], False)]
    test_written_segments_connect_all_pads_per_net.hypothesis.inner_test(nets)


# =========================================================================
# P4 — _assign_layer totality + the completion-gate identity contract
# =========================================================================
_net_names = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=122),
    min_size=1,
    max_size=12,
)

_constraint_entries = st.one_of(
    st.none(),
    st.sampled_from(["F.Cu", "B.Cu", "In1.Cu", "garbage"]),
    st.builds(
        SimpleNamespace,
        reason=st.sampled_from(
            [
                "netclass=Default SSOT layer=B.Cu",
                "netclass=HighVoltage SSOT layer=B.Cu",
                "netclass=FinePitch SSOT layer=F.Cu",
                "",
                "totally unrelated reason text",
            ]
        ),
        primary_layer=st.sampled_from([None, 0, 1, 2, 3]),
    ),
)


@given(
    name=_net_names,
    constraints=st.one_of(
        st.none(), st.dictionaries(_net_names, _constraint_entries, max_size=5)
    ),
    include_self=st.booleans(),
    entry=_constraint_entries,
)
@settings(max_examples=100, deadline=15000)
def test_assign_layer_is_total_and_layer_closed(name, constraints, include_self, entry):
    if include_self:
        constraints = dict(constraints or {})
        constraints[name] = entry

    layer = _assign_layer(name, layer_constraints=constraints)
    assert layer in {"F.Cu", "B.Cu"}

    # Completion-gate identity contract (PR #220 final state): while the
    # router lacks via-aware transitions, SSOT input must never change the
    # outcome. #226 U2+ will consciously relax this — at which point this
    # assertion should be REPLACED with the reachability-conditional
    # property, not deleted.
    assert layer == _assign_layer(name, layer_constraints=None)


@given(name=_net_names)
@settings(max_examples=25, deadline=15000)
def test_assign_layer_single_layer_mode_forces_fcu(name):
    set_single_layer_mode(True)
    try:
        assert _assign_layer(name, layer_constraints=None) == "F.Cu"
        assert (
            _assign_layer(name, layer_constraints={name: "B.Cu"}) == "F.Cu"
        )
    finally:
        set_single_layer_mode(False)

"""Differential: Rust Tier-3 N-layer A* vs its pinned Python oracle.

Feeds **real** ``pcb/temper.kicad_pcb`` geometry -- the board's own routing
spaces, occupancy grids and pad coordinates -- to both
``astar_nlayer_rust.route_segment_3d_rust`` and the pinned
``_astar_nlayer_py_oracle._route_segment_3d``, and requires **bit-exact**
agreement on the emitted world path, the via positions, and the resulting
occupancy-grid mutations.

Why real geometry rather than synthetic grids
---------------------------------------------
A differential proves only what it is fed. ``test_astar_nlayer.py``'s
hand-built fixtures are 21x21 open planes; the production grids are
1680x2380 per layer at 85% free with real pad, via, track and keepout
obstacles. The float magnitudes, the cell indices, the frontier size and the
tie-break density are all different in kind, and it is exactly the tie-break
density that a parity claim has to survive.

Why bit-exact rather than invariant-level
------------------------------------------
The 2D kernel's differential (``test_astar_kernel_rust_differential``)
asserts invariants only, because that kernel computes in f32 and the f64->f32
heuristic cast can reorder heap ties. Nothing forces a narrower type in the
Tier-3 kernel, so it is held to the stronger standard: this is the search
that decides where copper lands on a mains-voltage board, and "the path is
legal" would not detect a port that quietly routes somewhere else.

The board is read strictly read-only. Nothing here writes to ``pcb/``.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:  # the oracle sits beside this module
    sys.path.insert(0, str(_HERE))

import _astar_nlayer_py_oracle as oracle  # noqa: E402

from temper_placer.router_v6.astar_nlayer_rust import (  # noqa: E402
    route_segment_3d_rust,
)

_REPO_ROOT = _HERE.parents[3]
_PCB = _REPO_ROOT / "pcb" / "temper.kicad_pcb"

# Keep in sync with scripts' extraction spec; `test_oracle_is_verbatim_copy`
# re-runs it against the committed oracle.
ORACLE_COMMIT = "9019da63fe1f8cfccb98c53fafbbf0a8537ee7a6"
ORACLE_SOURCE = "packages/temper-placer/src/temper_placer/router_v6/astar_core.py"
ORACLE_RANGES: tuple[tuple[int, int], ...] = (
    (20, 45),
    (48, 55),
    (80, 135),
    (176, 190),
    (366, 368),
    (371, 539),
    (542, 553),
    (556, 669),
)
VERBATIM_MARKER = "# --- BEGIN VERBATIM EXTRACTION ---"

# A per-net iteration budget that keeps the suite's wall time bounded while
# still exercising long, genuinely hard segments. Both engines get the
# identical cap, so a bail is itself a behaviour that must match.
_MAX_ITER = 60_000
_UNBLOCK_INFLATION_MM = 0.3  # default family: trace 0.2 -> 0.1 + 0.2 clearance


@pytest.fixture(scope="module")
def board_grids():
    """Real per-layer occupancy grids + pad centres from the production board."""
    if not _PCB.exists():
        pytest.skip(f"{_PCB} not present")
    from temper_placer.core.board_layer_roles import routable_signal_layers_from_path
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.astar_grid import _extract_pad_centers_per_net
    from temper_placer.router_v6.occupancy_grid import build_occupancy_grid
    from temper_placer.router_v6.routing_space import compute_routing_space

    pcb = parse_kicad_pcb_v6(_PCB, use_declared_layer_roles=True)
    routable = routable_signal_layers_from_path(_PCB)
    spaces = compute_routing_space(pcb)
    grids = {
        name: build_occupancy_grid(spaces[name], inflation_mm=0.1)
        for name in sorted(spaces)
        if name in routable
    }
    assert len(grids) > 2, (
        "this differential exists for the N-layer path; the board must present "
        f"more than 2 routable signal layers, got {sorted(grids)}"
    )
    return grids, _extract_pad_centers_per_net(pcb)


def _segment_cases(pads, grids):
    """Deterministic real segments: consecutive pad pairs of each net.

    Sorted by net name, then pad order, so the case list is stable across
    runs and independent of dict iteration order.
    """
    cases = []
    for net in sorted(pads):
        plist = pads[net]
        for i in range(len(plist) - 1):
            (x0, y0, _r0, l0), (x1, y1, _r1, l1) = plist[i], plist[i + 1]
            # THT / all-layer pads have no single "own" layer; the production
            # driver anchors those on the primary grid, so do the same.
            sl = l0 if l0 in grids else "F.Cu"
            gl = l1 if l1 in grids else "F.Cu"
            cases.append((net, (x0, y0), (x1, y1), sl, gl))
    return cases


def _prepared(grids, pads, net):
    """Deep-copied grids with ``net``'s own pads unblocked, as the driver does."""
    from temper_placer.router_v6.astar_grid import _unblock_net_pads

    fresh = {k: copy.deepcopy(v) for k, v in grids.items()}
    _unblock_net_pads(net, pads, fresh, inflation_mm=_UNBLOCK_INFLATION_MM)
    return fresh


def _grid_fingerprint(grids):
    import hashlib

    h = hashlib.sha256()
    for name in sorted(grids):
        h.update(name.encode())
        h.update(grids[name].grid.tobytes())
    return h.hexdigest()


def _run_pair(grids, pads, net, start, goal, sl, gl, *, net_id, via_cost=10.0,
              via_diameter=0.6, clearance=0.2, max_iter=_MAX_ITER):
    """Run oracle and Rust on independent copies of the same real grids."""
    g_py = _prepared(grids, pads, net)
    g_rs = _prepared(grids, pads, net)
    assert _grid_fingerprint(g_py) == _grid_fingerprint(g_rs), "setup diverged"

    py = oracle._route_segment_3d(
        start, goal, sl, gl, g_py, via_cost=via_cost, via_diameter=via_diameter,
        clearance=clearance, net_id=net_id, max_iter=max_iter,
    )
    rs = route_segment_3d_rust(
        start, goal, sl, gl, g_rs, via_cost=via_cost, via_diameter=via_diameter,
        clearance=clearance, net_id=net_id, max_iter=max_iter,
    )
    return py, rs, g_py, g_rs


def _assert_identical(py, rs, g_py, g_rs, ctx):
    if py is None or rs is None:
        assert py is None and rs is None, (
            f"{ctx}: found/not-found disagreement -- "
            f"oracle={'None' if py is None else 'path'}, "
            f"rust={'None' if rs is None else 'path'}"
        )
        return

    py_path, py_vias = py
    rs_path, rs_vias = rs

    assert len(py_path) == len(rs_path), (
        f"{ctx}: path length {len(py_path)} (oracle) vs {len(rs_path)} (rust)"
    )
    for i, (a, b) in enumerate(zip(py_path, rs_path)):
        # Bit-exact: identical f64 bit patterns and identical layer name.
        assert a[2] == b[2], f"{ctx}: point {i} layer {a[2]!r} vs {b[2]!r}"
        assert a[0].hex() == b[0].hex(), f"{ctx}: point {i} x {a[0]!r} vs {b[0]!r}"
        assert a[1].hex() == b[1].hex(), f"{ctx}: point {i} y {a[1]!r} vs {b[1]!r}"

    assert len(py_vias) == len(rs_vias), (
        f"{ctx}: via count {len(py_vias)} (oracle) vs {len(rs_vias)} (rust)"
    )
    for i, (a, b) in enumerate(zip(py_vias, rs_vias)):
        assert a[0].hex() == b[0].hex(), f"{ctx}: via {i} x {a[0]!r} vs {b[0]!r}"
        assert a[1].hex() == b[1].hex(), f"{ctx}: via {i} y {a[1]!r} vs {b[1]!r}"

    # The via-marking mutation must land identically too -- the port moved it
    # out of the search, so it needs its own evidence.
    assert _grid_fingerprint(g_py) == _grid_fingerprint(g_rs), (
        f"{ctx}: occupancy grids diverged after via marking"
    )


# ---------------------------------------------------------------------------
# The differential proper.
# ---------------------------------------------------------------------------


def test_real_board_segments_are_bit_identical(board_grids):
    """Every real consecutive-pad segment routes identically in both engines."""
    grids, pads = board_grids
    cases = _segment_cases(pads, grids)
    assert len(cases) >= 300, f"expected the real board's full segment set, got {len(cases)}"

    checked = 0
    routed = 0
    # Stride the full deterministic case list so the sample spans the whole
    # board (and the whole span distribution) rather than one corner of it.
    for idx in range(0, len(cases), 8):
        net, start, goal, sl, gl = cases[idx]
        py, rs, g_py, g_rs = _run_pair(
            grids, pads, net, start, goal, sl, gl, net_id=(idx % 100) + 1
        )
        _assert_identical(py, rs, g_py, g_rs, f"case{idx} net={net}")
        checked += 1
        routed += py is not None

    assert checked >= 40, f"differential covered only {checked} segments"
    assert routed > 0, "no segment routed in either engine -- the differential is vacuous"


def test_real_board_cross_layer_segments_are_bit_identical(board_grids):
    """Cross-layer terminals, which force the via move Tier 3 exists for.

    The board places every SMD pad on ``F.Cu`` (measured: 433 ``F.Cu`` + 90
    through-hole, zero ``B.Cu``), so same-layer pad pairs alone would never
    exercise a layer transition. Production reaches Tier 3 with differing
    ``tier3_start_layer``/``tier3_goal_layer`` whenever a route's own boundary
    anchors resolve to different layers, so these pairings are a real
    production shape, on real pad coordinates.
    """
    grids, pads = board_grids
    cases = _segment_cases(pads, grids)
    layers = list(grids)

    checked = 0
    with_via = 0
    for n, idx in enumerate(range(0, len(cases), 16)):
        net, start, goal, _sl, _gl = cases[idx]
        sl = layers[n % len(layers)]
        gl = layers[(n + 1) % len(layers)]
        py, rs, g_py, g_rs = _run_pair(
            grids, pads, net, start, goal, sl, gl, net_id=(idx % 100) + 1
        )
        _assert_identical(py, rs, g_py, g_rs, f"xlayer{idx} net={net} {sl}->{gl}")
        checked += 1
        if py is not None and py[1]:
            with_via += 1

    assert checked >= 20, f"cross-layer differential covered only {checked} segments"
    assert with_via > 0, (
        "no cross-layer case produced a via -- the via move is unexercised and "
        "this differential would not detect a broken layer transition"
    )


def test_bit_exactness_is_load_bearing_on_a_170v_net(board_grids):
    """Pins the exact real-board case that proves f64 parity is not pedantry.

    THIS IS THE REASON THIS SUITE ASSERTS BIT PATTERNS RATHER THAN INVARIANTS.

    The Tier-3 Rust kernel was deliberately mutated during review by routing
    its heuristic through f32 -- precisely what the shipped 2D kernel
    (``temper_rust_router_core::astar::astar_kernel_3d``) does, and the exact
    reason that kernel's own differential
    (``test_astar_kernel_rust_differential.test_same_net_bit_exact_vs_oracle``)
    can only assert invariants. With that one-line change, this segment's
    emitted copper moved to a **different layer**:

        case: net ``+170V_BUS``  (77.89, 166.0125) -> (104.03, 193.8525)
              anchored F.Cu -> In3.Cu
        f64 (correct):  path point 127 lands on 'In3.Cu'
        f32 (mutated):  path point 127 lands on 'B.Cu'

    Both routes are legal: connected, on-grid, respecting occupancy. An
    invariant-level differential passes the mutation without a murmur. What
    actually changed is which layer a **170 V** net's copper sits on -- a
    creepage- and clearance-relevant fact on a mains board, decided by a
    rounding mode.

    So this test is not "the port works" (the sweeps above cover that). It is
    the regression guard for the specific reintroduction that motivated the
    stricter standard: narrow the arithmetic anywhere in the Tier-3 kernel and
    this case diverges from the pinned oracle.
    """
    grids, pads = board_grids
    net = "+170V_BUS"
    assert net in pads, f"{net} is no longer on the board; re-pin this case"

    start, goal = (77.89, 166.01250000000002), (104.03, 193.8525)
    py, rs, g_py, g_rs = _run_pair(
        grids, pads, net, start, goal, "F.Cu", "In3.Cu", net_id=17
    )
    _assert_identical(py, rs, g_py, g_rs, f"170V-pin net={net}")

    assert py is not None, (
        "the pinned 170V case no longer routes at all -- it can no longer "
        "witness the f32/f64 layer divergence, so re-pin it against a case "
        "that does rather than leaving a guard that guards nothing"
    )
    # The divergence showed up as a layer change, so assert the layer
    # sequence explicitly and not merely 'the paths matched'.
    py_layers = [p[2] for p in py[0]]
    rs_layers = [p[2] for p in rs[0]]
    assert py_layers == rs_layers, "layer sequence diverged"
    assert set(py_layers) <= set(grids), f"unexpected layer in {set(py_layers)}"


def test_cell_level_search_matches_oracle(board_grids):
    """The raw cell-level entry point agrees with the oracle too.

    ``astar_search_3d_rust`` is the replacement for callers that work in grid
    cells rather than world millimetres (the pre-migration
    ``astar_core._astar_search_3d``). It shares the kernel with
    ``route_segment_3d_rust`` but has its own marshalling and its own
    ``RouteNode3D`` round-trip, so it needs its own evidence rather than
    inheriting the world-coordinate wrapper's.
    """
    from temper_placer.router_v6.astar_core import RouteNode3D
    from temper_placer.router_v6.astar_nlayer_rust import astar_search_3d_rust

    grids, pads = board_grids
    cases = _segment_cases(pads, grids)
    layers = list(grids)

    checked = routed = 0
    for n, idx in enumerate(range(0, len(cases), 24)):
        net, start, goal, _sl, _gl = cases[idx]
        sample = grids[layers[0]]
        sx, sy = sample.world_to_grid(*start)
        gx, gy = sample.world_to_grid(*goal)
        sl = layers[n % len(layers)]
        gl = layers[(n + 1) % len(layers)]

        g_py = _prepared(grids, pads, net)
        g_rs = _prepared(grids, pads, net)
        net_id = (idx % 100) + 1

        py = oracle._astar_search_3d(
            RouteNode3D(sx, sy, sl), RouteNode3D(gx, gy, gl), g_py,
            net_id=net_id, max_iter=_MAX_ITER,
        )
        rs = astar_search_3d_rust(
            RouteNode3D(sx, sy, sl), RouteNode3D(gx, gy, gl), g_rs,
            net_id=net_id, max_iter=_MAX_ITER,
        )
        ctx = f"cell{idx} net={net} {sl}->{gl}"
        if py is None or rs is None:
            assert py is None and rs is None, f"{ctx}: found/not-found disagreement"
            checked += 1
            continue

        py_nodes, py_vias = py
        rs_nodes, rs_vias = rs
        assert [(n_.x, n_.y, n_.layer) for n_ in py_nodes] == [
            (n_.x, n_.y, n_.layer) for n_ in rs_nodes
        ], f"{ctx}: cell path diverged"
        assert py_vias == rs_vias, f"{ctx}: via cells diverged"
        assert _grid_fingerprint(g_py) == _grid_fingerprint(g_rs), (
            f"{ctx}: grids diverged after via marking"
        )
        checked += 1
        routed += 1

    assert checked >= 10, f"cell-level differential covered only {checked} cases"
    assert routed > 0, "no cell-level case routed -- differential is vacuous"


def test_layers_with_different_frames_match(board_grids):
    """Layers whose grids differ in size/origin/cell size still agree.

    The real board cannot witness this: every layer's grid is built from one
    board outline, so they all share a frame, and a Rust port that collapsed
    the per-layer frame to the sample grid's would pass every other test in
    this module. The Python it replaces does *not* collapse them --
    ``OccupancyGrid.is_free`` bounds-checks against each grid's own
    dimensions, and ``_route_segment_3d`` converts each bulk path node with
    ``grids[node.layer].grid_to_world(...)``, its own layer's frame.

    So this case is deliberately synthetic. It is the one place in this suite
    where that is the right call: it covers a degree of freedom the
    production board holds fixed, and a differential only proves what it is
    fed.
    """
    import numpy as np

    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    # Three layers, three different frames: differing cell counts, origins
    # and cell sizes. Names chosen so lexicographic rank != insertion order,
    # exercising the tie-break mapping too.
    grids = {
        "F.Cu": OccupancyGrid("F.Cu", np.zeros((40, 30), dtype=np.int8), (0.0, 0.0), 0.5, 30, 40),
        "In3.Cu": OccupancyGrid(
            "In3.Cu", np.zeros((25, 25), dtype=np.int8), (1.0, -2.0), 0.25, 25, 25
        ),
        "B.Cu": OccupancyGrid("B.Cu", np.zeros((50, 20), dtype=np.int8), (-3.0, 4.0), 1.0, 20, 50),
    }
    # Wall off F.Cu so the search is forced through another layer's frame.
    grids["F.Cu"].grid[:, 10] = -1

    start, goal = (1.0, 1.0), (6.0, 8.0)
    routed = 0
    for sl, gl in (("F.Cu", "F.Cu"), ("F.Cu", "In3.Cu"), ("B.Cu", "In3.Cu")):
        g_py = {k: copy.deepcopy(v) for k, v in grids.items()}
        g_rs = {k: copy.deepcopy(v) for k, v in grids.items()}
        py = oracle._route_segment_3d(start, goal, sl, gl, g_py, net_id=3, max_iter=50_000)
        rs = route_segment_3d_rust(start, goal, sl, gl, g_rs, net_id=3, max_iter=50_000)
        _assert_identical(py, rs, g_py, g_rs, f"mixed-frame {sl}->{gl}")
        routed += py is not None
    assert routed > 0, (
        "no mixed-frame case produced a path, so this test would agree "
        "trivially even if the per-layer frame were collapsed to the sample "
        "grid's -- the exact divergence it exists to catch"
    )


def test_max_iter_bail_matches(board_grids):
    """A budget exhaustion must be reported identically by both engines."""
    grids, pads = board_grids
    cases = _segment_cases(pads, grids)
    # Longest real segments, which reliably exhaust a small budget.
    longest = sorted(
        cases,
        key=lambda c: (c[2][0] - c[1][0]) ** 2 + (c[2][1] - c[1][1]) ** 2,
        reverse=True,
    )[:6]
    bailed = 0
    for i, (net, start, goal, sl, gl) in enumerate(longest):
        py, rs, g_py, g_rs = _run_pair(
            grids, pads, net, start, goal, sl, gl, net_id=(i % 100) + 1, max_iter=500
        )
        _assert_identical(py, rs, g_py, g_rs, f"bail net={net}")
        bailed += py is None
    assert bailed > 0, "no case exhausted the 500-iteration budget; bail path unexercised"


def test_missing_layer_terminal_declines_in_both(board_grids):
    """A terminal naming a layer with no grid declines identically."""
    grids, pads = board_grids
    net, start, goal, sl, _gl = _segment_cases(pads, grids)[0]
    py, rs, g_py, g_rs = _run_pair(
        grids, pads, net, start, goal, sl, "In1.Cu", net_id=1
    )
    assert py is None and rs is None, (
        f"a goal layer with no occupancy grid must decline in both: {py!r} / {rs!r}"
    )


# ---------------------------------------------------------------------------
# Oracle integrity.
# ---------------------------------------------------------------------------


def test_oracle_is_verbatim_copy():
    """The oracle is byte-identical to the pinned commit's source ranges.

    Re-runs the extraction rather than trusting the file, so an edit to the
    oracle -- or a change in what those line ranges mean -- fails closed
    instead of silently redefining the reference the differential compares to.
    """
    import subprocess

    blob = subprocess.run(
        ["git", "show", f"{ORACLE_COMMIT}:{ORACLE_SOURCE}"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    lines = blob.split("\n")
    expected_parts: list[str] = []
    for start, end in ORACLE_RANGES:
        expected_parts.extend(lines[start - 1 : end])
        expected_parts.append("")
        expected_parts.append("")
    expected = "\n".join(expected_parts).rstrip("\n") + "\n"

    text = (_HERE / "_astar_nlayer_py_oracle.py").read_text()
    marker_at = text.index(VERBATIM_MARKER)
    actual = text[marker_at + len(VERBATIM_MARKER) :].lstrip("\n")

    assert actual == expected, (
        "oracle drifted from its pinned extraction -- the differential would be "
        "comparing Rust against a redefined reference"
    )


# --------------------------------------------------------------------------
# Tier-3 blocked-goal precheck (`astar_nlayer_rust._goal_is_unreachable`)
# --------------------------------------------------------------------------
#
# Measured on the model-E placement, 2026-08-20: 27 of Tier 3's 54 dispatches
# name a goal cell that is blocked, and each burns its full `max_iter` budget
# before declining -- 3.83 s of Tier 3's 7.94 s. The precheck declines them up
# front. It must be a pure short-circuit: identical return value, less wall
# time. These tests pin both halves of that claim.


def _walled_grids():
    """Three synthetic layers, all cells free, ready for a caller to wall off."""
    import numpy as np

    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    return {
        name: OccupancyGrid(name, np.zeros((40, 40), dtype=np.int8), (0.0, 0.0), 0.5, 40, 40)
        for name in ("F.Cu", "In3.Cu", "B.Cu")
    }


def test_blocked_goal_declines_identically_to_oracle():
    """A blocked goal cell declines in both engines, on every layer pairing.

    The oracle can only enqueue the goal key via a same-layer move guarded by
    ``grids[goal_layer].is_free(gx, gy)`` or a via transition guarded by the
    *same* test on the *same* cell, so a blocked goal is unsatisfiable at any
    budget. The precheck must therefore agree with the oracle exactly.
    """
    goal_world = (10.0, 10.0)
    start_world = (2.0, 2.0)

    for gl in ("F.Cu", "In3.Cu", "B.Cu"):
        g_py, g_rs = _walled_grids(), _walled_grids()
        gx, gy = g_py[gl].world_to_grid(*goal_world)
        # Block the goal cell on the goal layer only -- the rest of the board
        # stays open, so the segment is otherwise trivially routable and the
        # decline is attributable to this cell alone.
        for g in (g_py, g_rs):
            g[gl].grid[gy, gx] = -1

        py = oracle._route_segment_3d(
            start_world, goal_world, "F.Cu", gl, g_py, net_id=5, max_iter=50_000
        )
        rs = route_segment_3d_rust(
            start_world, goal_world, "F.Cu", gl, g_rs, net_id=5, max_iter=50_000
        )
        assert py is None, f"oracle unexpectedly routed to a blocked goal on {gl}"
        _assert_identical(py, rs, g_py, g_rs, f"blocked-goal {gl}")

        # And the same segment DOES route once the cell is freed, so the
        # decline above is caused by the blocked cell and not by the fixture.
        g_py2, g_rs2 = _walled_grids(), _walled_grids()
        open_py = oracle._route_segment_3d(
            start_world, goal_world, "F.Cu", gl, g_py2, net_id=5, max_iter=50_000
        )
        open_rs = route_segment_3d_rust(
            start_world, goal_world, "F.Cu", gl, g_rs2, net_id=5, max_iter=50_000
        )
        assert open_py is not None, f"control case did not route on {gl} -- test is vacuous"
        _assert_identical(open_py, open_rs, g_py2, g_rs2, f"open-goal control {gl}")


def test_blocked_goal_never_reaches_the_kernel(monkeypatch):
    """The precheck short-circuits *before* the FFI call, not after.

    This is the whole point of the change: the 27 unsatisfiable dispatches
    must stop costing a full ``max_iter`` sweep. Asserting on the return value
    alone would pass even if the kernel still ran, so assert the kernel is not
    entered at all.
    """
    import temper_rust_router as _trr

    def _explode(*_args, **_kwargs):  # pragma: no cover - must not be called
        raise AssertionError("kernel entered for a provably unsatisfiable goal")

    monkeypatch.setattr(_trr, "route_segment_3d_py", _explode)

    grids = _walled_grids()
    gx, gy = grids["F.Cu"].world_to_grid(10.0, 10.0)
    grids["F.Cu"].grid[gy, gx] = -1

    assert (
        route_segment_3d_rust(
            (2.0, 2.0), (10.0, 10.0), "F.Cu", "F.Cu", grids, net_id=5, max_iter=50_000
        )
        is None
    )


def test_degenerate_blocked_terminal_still_reports_found():
    """start == goal on a blocked cell must still succeed -- the naive fix's bug.

    ``_astar_search_3d`` seeds the start node into the frontier
    unconditionally, with no ``is_free`` test, so a segment whose two
    terminals quantise to the same cell on the same layer returns *found*
    even when that cell is blocked. An unguarded "goal is blocked -> decline"
    precheck would turn those into declines: a behaviour change, and a
    regression. The ``start != goal`` guard exists for this case, and this
    test is what holds it in place.
    """
    same = (10.0, 10.0)
    g_py, g_rs = _walled_grids(), _walled_grids()
    gx, gy = g_py["F.Cu"].world_to_grid(*same)
    for g in (g_py, g_rs):
        g["F.Cu"].grid[gy, gx] = -1

    py = oracle._route_segment_3d(same, same, "F.Cu", "F.Cu", g_py, net_id=5, max_iter=50_000)
    rs = route_segment_3d_rust(same, same, "F.Cu", "F.Cu", g_rs, net_id=5, max_iter=50_000)

    assert py is not None, (
        "oracle declined a degenerate same-cell segment -- the premise this "
        "guard rests on no longer holds; re-derive it before trusting the guard"
    )
    _assert_identical(py, rs, g_py, g_rs, "degenerate blocked terminal")


def test_cell_level_entry_point_honours_the_same_precheck():
    """``astar_search_3d_rust`` gets the precheck too, with the same guard."""
    from temper_placer.router_v6.astar_core import RouteNode3D
    from temper_placer.router_v6.astar_nlayer_rust import astar_search_3d_rust

    g_py, g_rs = _walled_grids(), _walled_grids()
    for g in (g_py, g_rs):
        g["In3.Cu"].grid[20, 20] = -1

    py = oracle._astar_search_3d(
        RouteNode3D(4, 4, "F.Cu"),
        RouteNode3D(20, 20, "In3.Cu"),
        g_py,
        net_id=5,
        max_iter=50_000,
    )
    rs = astar_search_3d_rust(
        RouteNode3D(4, 4, "F.Cu"),
        RouteNode3D(20, 20, "In3.Cu"),
        g_rs,
        net_id=5,
        max_iter=50_000,
    )
    assert py is None and rs is None, f"blocked-goal disagreement: {py!r} / {rs!r}"

    # Degenerate guard applies here as well.
    g_py2, g_rs2 = _walled_grids(), _walled_grids()
    for g in (g_py2, g_rs2):
        g["F.Cu"].grid[7, 7] = -1
    py2 = oracle._astar_search_3d(
        RouteNode3D(7, 7, "F.Cu"), RouteNode3D(7, 7, "F.Cu"), g_py2, net_id=5, max_iter=50_000
    )
    rs2 = astar_search_3d_rust(
        RouteNode3D(7, 7, "F.Cu"), RouteNode3D(7, 7, "F.Cu"), g_rs2, net_id=5, max_iter=50_000
    )
    assert py2 is not None and rs2 is not None, (
        f"degenerate same-cell terminal must still report found: {py2!r} / {rs2!r}"
    )

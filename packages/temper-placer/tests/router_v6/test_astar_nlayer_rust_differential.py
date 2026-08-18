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

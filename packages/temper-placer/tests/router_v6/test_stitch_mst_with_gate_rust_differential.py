"""Differential tests: the MST pad-to-pad stitcher + creepage-aware
C-space gate (Rust ``temper_geometry.stitch_mst_with_gate_py``, ported in
``packages/temper-geometry/src/zone_generator.rs::stitch_mst_with_gate``)
vs. the pre-migration Python (``_mst_edges`` + ``_gate_filter_edges``),
pinned in ``_stitch_mst_with_gate_py_oracle.py``.

Full root-cause analysis, the generalisation this migration enables, and
the per-net verdicts this suite locks in as regression tests:
docs/evidence/2026-08-18-zone-pour-fragmentation-rootcause.md.

Three things this suite verifies:

1. **Oracle is a verbatim pin**: the oracle file's two functions match,
   character for character, the functions as they existed at this
   migration's base commit.
2. **Edge-set agreement**: the Rust arm produces the exact same kept edges
   (as index pairs) and skip count as the Python oracle, across synthetic
   cases (empty/singleton/tie-break/blocked/clear) and every one of the 9
   target nets' REAL pad positions + real per-pair obstacle records
   collected from the committed board.
3. **Creepage-awareness is structural, not incidental**: a case with an
   obstacle whose CLEARANCE separation is tiny but whose CREEPAGE
   separation is PD3-large (12.6mm) is gated out by both arms identically
   -- proving the gate is not merely clearance-aware.
"""

from __future__ import annotations

import math
import random

import pytest

import tests.router_v6._stitch_mst_with_gate_py_oracle as ORACLE
import temper_geometry as _tg

PINNED_COMMIT = "9a55b56be95f985098c4cb9c0abfc4569a79dcad"
PINNED_FILE = "packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py"


# ===========================================================================
# 1. Oracle verbatim-copy proof
# ===========================================================================


def _extract_function(lines: list[str], name: str) -> str:
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"def {name}("))
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("def ") and i > start
        ),
        len(lines),
    )
    # Trim trailing blank lines between functions (or at end of file).
    body_lines = lines[start:end]
    while body_lines and body_lines[-1] == "":
        body_lines.pop()
    return "\n".join(body_lines) + "\n"


def test_oracle_is_verbatim_copy():
    """The pinned oracle's two functions must be byte-identical to the
    functions as they existed at this migration's base commit, not a
    paraphrase."""
    import subprocess

    result = subprocess.run(
        ["git", "show", f"{PINNED_COMMIT}:{PINNED_FILE}"],
        cwd="/home/bennet/Desktop/temper/.claude/worktrees/agent-af083e46ba1200240",
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    pinned_mst = _extract_function(lines, "_mst_edges")
    pinned_gate = _extract_function(lines, "_gate_filter_edges")

    import inspect

    oracle_source = inspect.getsource(ORACLE)
    oracle_lines = oracle_source.splitlines()
    oracle_mst = _extract_function(oracle_lines, "_mst_edges")
    oracle_gate = _extract_function(oracle_lines, "_gate_filter_edges")

    assert oracle_mst == pinned_mst, "oracle _mst_edges drifted from the pinned commit"
    assert oracle_gate == pinned_gate, "oracle _gate_filter_edges drifted from the pinned commit"


# ===========================================================================
# 2. Edge-set agreement: synthetic cases
# ===========================================================================


def _run_both(
    positions: list[tuple[float, float]],
    obstacles: list[tuple[int, float, float, float, float, float, float]],
    stitch_width_mm: float,
) -> tuple[tuple[list[tuple[int, int]], int], tuple[list[tuple[int, int]], int]]:
    py_edges = ORACLE._mst_edges(positions)
    py_kept, py_skipped = ORACLE._gate_filter_edges(positions, py_edges, obstacles, stitch_width_mm)

    rs_edges, rs_skipped = _tg.stitch_mst_with_gate_py(positions, obstacles, stitch_width_mm)

    return (py_kept, py_skipped), (list(rs_edges), rs_skipped)


def test_empty_and_singleton():
    for positions in ([], [(1.0, 2.0)]):
        (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, [], 0.2)
        assert py_kept == rs_kept == []
        assert py_skipped == rs_skipped == 0


def test_no_obstacles_straight_chain():
    positions = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (15.0, 0.0)]
    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, [], 0.2)
    assert py_kept == rs_kept
    assert py_skipped == rs_skipped == 0


@pytest.mark.parametrize("seed", range(30))
def test_random_clusters_no_obstacles(seed: int):
    rng = random.Random(seed)
    n = rng.randint(2, 12)
    positions = [(rng.uniform(0, 200), rng.uniform(0, 300)) for _ in range(n)]
    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, [], 0.2)
    assert py_kept == rs_kept, f"seed={seed} positions={positions}"
    assert py_skipped == rs_skipped


@pytest.mark.parametrize("seed", range(30))
def test_random_clusters_with_random_pad_obstacles(seed: int):
    rng = random.Random(seed + 1000)
    n = rng.randint(2, 10)
    positions = [(rng.uniform(0, 200), rng.uniform(0, 300)) for _ in range(n)]
    n_obs = rng.randint(0, 8)
    obstacles = [
        (
            0,  # Pad
            rng.uniform(0, 200),
            rng.uniform(0, 300),
            rng.uniform(0.3, 2.0),  # half_w
            rng.uniform(0.3, 2.0),  # half_h
            0.0,
            rng.choice([0.2, 2.0, 6.3, 12.6]),  # clearance/creepage separation
        )
        for _ in range(n_obs)
    ]
    stitch_width = rng.choice([0.2, 1.0, 3.0])
    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, obstacles, stitch_width)
    assert py_kept == rs_kept, f"seed={seed} positions={positions} obstacles={obstacles}"
    assert py_skipped == rs_skipped


def test_tie_break_matches():
    # Two points equidistant from the root: both arms must pick the same
    # (lower-index) edge first.
    positions = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, [], 0.2)
    assert py_kept == rs_kept
    assert py_kept[0] == (0, 1)


def test_track_and_via_obstacle_kinds():
    positions = [(0.0, 0.0), (10.0, 0.0)]
    obstacles = [
        (1, 0.0, 5.0, 10.0, 5.0, 1.0, 4.0),  # Track crossing the segment
        (2, 5.0, -5.0, 2.0, 0.0, 0.0, 1.0),  # Via, far below, should not block
    ]
    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, obstacles, 0.2)
    assert py_kept == rs_kept
    assert py_skipped == rs_skipped


# ===========================================================================
# 3. Creepage-awareness is structural
# ===========================================================================


def test_creepage_governs_over_clearance():
    """An obstacle placed such that a 2.0mm CLEARANCE separation would
    clear it, but the pair's real 12.6mm PD3 CREEPAGE separation does not,
    must be gated out by both arms identically -- proving the gate acts on
    whatever separation figure the CALLER resolved (max(clearance,
    creepage)), not a clearance-only figure baked into the gate itself."""
    positions = [(0.0, 0.0), (10.0, 0.0)]
    # Obstacle pad 3mm off the line's perpendicular distance: a 2.0mm
    # clearance halo would NOT reach the line's 0.1mm half-width footprint,
    # but a 12.6mm creepage-resolved separation easily does.
    obstacle_clearance_only = [(0, 5.0, 3.0, 0.5, 0.5, 0.0, 2.0)]
    obstacle_creepage_resolved = [(0, 5.0, 3.0, 0.5, 0.5, 0.0, 12.6)]

    (py_kept_c, py_skip_c), (rs_kept_c, rs_skip_c) = _run_both(
        positions, obstacle_clearance_only, 0.2
    )
    (py_kept_hv, py_skip_hv), (rs_kept_hv, rs_skip_hv) = _run_both(
        positions, obstacle_creepage_resolved, 0.2
    )

    assert py_kept_c == rs_kept_c == [(0, 1)], "2.0mm clearance-only case should clear"
    assert py_skip_c == rs_skip_c == 0

    assert py_kept_hv == rs_kept_hv == [], "12.6mm creepage-resolved case must be blocked"
    assert py_skip_hv == rs_skip_hv == 1


# ===========================================================================
# 4. Real-board differential -- the 9 target nets, real pad positions and
#    real per-pair obstacle records collected from the committed board.
#    ("A differential test only proves what you feed it" -- AGENTS.md.)
# ===========================================================================

TARGET_NETS = [
    "+170V_BUS",
    "DC_BUS_RTN",
    "PWR_RTN",
    "SW_NODE",
    "ac_n",
    "power_in.ntc-no",
    "tank.c_tank1-p2",
    "w1_1",
    "w1_2",
]


@pytest.mark.parametrize("net_name", TARGET_NETS)
def test_real_board_target_nets(net_name: str):
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6._zone_pour_stitch import _stitch_width_for_net
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
    from temper_placer.router_v6.zone_pour_clearance import (
        collect_zone_obstacle_records,
        default_table,
    )
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    repo_root = Path("/home/bennet/Desktop/temper/.claude/worktrees/agent-af083e46ba1200240")
    pcb_path = repo_root / "pcb" / "temper.kicad_pcb"
    pcb = parse_kicad_pcb_v6(pcb_path)
    pads_by_net = _pads_by_net(pcb)
    positions = [p.position for p in pads_by_net.get(net_name, [])]
    if len(positions) < 2:
        pytest.skip(f"{net_name} has < 2 pads on the committed board")

    import re

    net_number_to_name = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', pcb_path.read_text())
    }
    obstacles = collect_zone_obstacle_records(
        net_name,
        "In3.Cu",
        pcb=pcb,
        segments=[],
        net_number_to_name=net_number_to_name,
        clearance_table=default_table(),
        creepage_table=default_creepage_table(),
    )
    stitch_width = _stitch_width_for_net(net_name)

    (py_kept, py_skipped), (rs_kept, rs_skipped) = _run_both(positions, obstacles, stitch_width)
    assert py_kept == rs_kept, f"{net_name}: edge set mismatch"
    assert py_skipped == rs_skipped, f"{net_name}: skip count mismatch"


# ===========================================================================
# 5. gate_edges_py -- the standalone gate (no MST), used for the
#    `power_in.ntc-no` hand-verified edge list.
# ===========================================================================


@pytest.mark.parametrize("seed", range(20))
def test_gate_edges_py_matches_oracle_on_arbitrary_edges(seed: int):
    rng = random.Random(seed + 2000)
    n = rng.randint(2, 8)
    positions = [(rng.uniform(0, 200), rng.uniform(0, 300)) for _ in range(n)]
    n_edges = rng.randint(0, n)
    edges = [(rng.randrange(n), rng.randrange(n)) for _ in range(n_edges)]
    n_obs = rng.randint(0, 6)
    obstacles = [
        (
            0,
            rng.uniform(0, 200),
            rng.uniform(0, 300),
            rng.uniform(0.3, 2.0),
            rng.uniform(0.3, 2.0),
            0.0,
            rng.choice([0.2, 2.0, 6.3, 12.6]),
        )
        for _ in range(n_obs)
    ]
    stitch_width = rng.choice([0.2, 1.0, 5.0])

    py_kept, py_skipped = ORACLE._gate_filter_edges(positions, edges, obstacles, stitch_width)
    rs_kept, rs_skipped = _tg.gate_edges_py(positions, edges, obstacles, stitch_width)
    assert py_kept == list(rs_kept), f"seed={seed}"
    assert py_skipped == rs_skipped, f"seed={seed}"


def test_gate_edges_py_ntc_no_verified_edges():
    """The actual production edge list for power_in.ntc-no's verified
    override, gated at its real stitch width -- the specific case
    `gate_edges_py` exists to serve in production."""
    from temper_placer.router_v6._zone_pour_stitch import (
        _CONTINUITY_EXEMPT_NET_VERIFIED_EDGES,
        _stitch_width_for_net,
    )

    verified = _CONTINUITY_EXEMPT_NET_VERIFIED_EDGES["power_in.ntc-no"]
    all_positions = sorted({p for pair in verified for p in pair})
    idx = {p: i for i, p in enumerate(all_positions)}
    edges = [(idx[a], idx[b]) for a, b in verified]
    stitch_width = _stitch_width_for_net("power_in.ntc-no")

    py_kept, py_skipped = ORACLE._gate_filter_edges(all_positions, edges, [], stitch_width)
    rs_kept, rs_skipped = _tg.gate_edges_py(all_positions, edges, [], stitch_width)
    assert py_kept == list(rs_kept)
    assert py_skipped == rs_skipped == 0

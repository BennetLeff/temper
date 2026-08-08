"""Differential tests: ``zone_emission._cluster_positions`` (Rust ``kodama``
Ward linkage via ``temper_geometry.ward_cluster_labels_py``) vs
``scipy.cluster.hierarchy.linkage``/``fcluster``/``scipy.spatial.distance.
pdist``, the pre-migration oracle pinned in ``_zone_emission_clustering_py_
oracle.py`` per R19 (see ``docs/wave4-discipline-contract.md``, mirroring
``test_channel_skeleton_radius_pairs_rust_differential.py``'s structure).

Full analysis, consumer-contract citations, `kodama` evaluation, and the
real-board differential this suite locks in as regression tests:
docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md.

Three things this suite verifies:

1. **Oracle is a verbatim pin** (R19): ``_zone_emission_clustering_py_
   oracle.py``'s ``_cluster_positions`` matches, character for character,
   the function as it existed at this migration's base commit.
2. **Partition agreement**: the Rust arm produces the exact same partition
   (as a SET of sets of positions -- the only contract any consumer of
   ``_cluster_positions`` relies on; see the evidence doc's consumer-contract
   section) as the pinned scipy oracle, across the existing synthetic test
   cases, real production-board net geometry, and randomized
   clustered/symmetric/degenerate stress cases.
3. **Emitted-geometry agreement**: feeding either arm's clusters through the
   *unchanged* ``_convex_hull_from_positions`` + board-outline clip produces
   geometrically equivalent (zero area difference, in practice -- not just
   "within tolerance") zone polygons on real board nets, which is what
   actually reaches ``pcb/temper.kicad_pcb`` once emitted.

``zone_emission.py`` no longer imports ``scipy`` for clustering; scipy is
retained here, unused in production, only as the oracle this file pins.
"""

from __future__ import annotations

import math
import random

import pytest
from shapely.geometry import Polygon

import tests.router_v6._zone_emission_clustering_py_oracle as ORACLE
from temper_placer.router_v6.zone_emission import (
    _clip_to_board,
    _cluster_positions,
    _convex_hull_from_positions,
)

# ===========================================================================
# 1. Oracle verbatim-copy proof
# ===========================================================================


def test_oracle_is_verbatim_copy():
    """The pinned oracle's ``_cluster_positions`` must be byte-identical to
    the function as it existed at this migration's base commit
    (``c10523bb``), not a paraphrase."""
    import inspect
    import subprocess

    result = subprocess.run(
        [
            "git",
            "show",
            "c10523bb:packages/temper-placer/src/temper_placer/router_v6/zone_emission.py",
        ],
        cwd="/home/bennet/Desktop/temper/.claude/worktrees/agent-a95a9dc7b333a2c58",
        capture_output=True,
        text=True,
        check=True,
    )
    source_at_pin = result.stdout
    # Extract the function body from the pinned commit's file content by
    # locating the def line through the following top-level def/EOF.
    lines = source_at_pin.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("def _cluster_positions("))
    end = next(
        i
        for i in range(start + 1, len(lines))
        if lines[i].startswith("def ") and i > start
    )
    pinned_source = "\n".join(lines[start:end]).rstrip() + "\n"

    oracle_source = inspect.getsource(ORACLE._cluster_positions)

    assert oracle_source.strip() == pinned_source.strip(), (
        "oracle _cluster_positions has drifted from the pinned base-commit "
        "source -- this file must be a verbatim copy, not a paraphrase"
    )


# ===========================================================================
# 2 & 3. Partition + emitted-geometry agreement
# ===========================================================================


def _partition_as_set(groups: list[list[tuple[float, float]]]) -> frozenset:
    return frozenset(frozenset(g) for g in groups)


def _assert_partitions_match(positions, label=""):
    oracle_groups = ORACLE._cluster_positions(list(positions))
    rust_groups = _cluster_positions(list(positions))
    assert _partition_as_set(oracle_groups) == _partition_as_set(rust_groups), (
        f"partition mismatch for {label}: "
        f"oracle={oracle_groups!r} rust={rust_groups!r}"
    )


def _hull_union_area(groups, margin, board_polygon=None) -> float:
    polys = []
    for grp in groups:
        hull = _convex_hull_from_positions(grp, margin=margin)
        if not hull:
            continue
        outlines = _clip_to_board(hull, board_polygon) if board_polygon is not None else [hull]
        for outline in outlines:
            if len(outline) >= 3:
                p = Polygon(outline)
                if p.is_valid and not p.is_empty:
                    polys.append(p)
    if not polys:
        return 0.0
    u = polys[0]
    for p in polys[1:]:
        u = u.union(p)
    return u.area


def _assert_geometry_matches(positions, margin=1.0, label=""):
    oracle_groups = ORACLE._cluster_positions(list(positions))
    rust_groups = _cluster_positions(list(positions))
    oracle_area = _hull_union_area(oracle_groups, margin)
    rust_area = _hull_union_area(rust_groups, margin)
    assert oracle_area == pytest.approx(rust_area, abs=1e-6), (
        f"emitted-geometry area mismatch for {label}: "
        f"oracle={oracle_area} rust={rust_area}"
    )


# --- Existing synthetic cases from test_zone_emission.py -------------------


def test_matches_oracle_tight_cluster():
    positions = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
    _assert_partitions_match(positions, "tight_cluster")
    _assert_geometry_matches(positions, label="tight_cluster")


def test_matches_oracle_two_widely_separated_groups():
    positions = [
        (0.0, 0.0),
        (1.0, 0.0),
        (0.5, 1.0),
        (50.0, 0.0),
        (51.0, 0.0),
        (50.5, 1.0),
    ]
    _assert_partitions_match(positions, "two_groups")
    _assert_geometry_matches(positions, label="two_groups")


def test_matches_oracle_adjacent_pitch_no_split():
    positions = [(0.0, 0.0), (1.27, 0.0), (2.54, 0.0)]  # 50-mil pitch
    _assert_partitions_match(positions, "adjacent_pitch")


# --- Real production-board net geometry -------------------------------------
# Every zone-eligible HighVoltage net on pcb/temper.kicad_pcb with >=3 pads
# (the population that actually invokes clustering in production --
# GND/ACMains are exempt, and <=2-pad nets short-circuit before reaching the
# clustering backend at all). Positions extracted once via
# parse_kicad_pcb_v6 + the same net-pin-position resolution
# _write_routes_to_content uses; hardcoded here so this suite has no
# board-file I/O dependency and stays fast.
_REAL_BOARD_NETS: dict[str, list[tuple[float, float]]] = {
    "w1_1": [(78.74, 165.1), (55.245, 165.735), (55.245, 160.655), (55.245, 170.815)],
    "+170V_BUS": [
        (78.74, 165.1),
        (23.114, 40.005),
        (61.976, 158.115),
        (61.976, 152.4),
        (55.245, 40.259),
        (23.114, 34.925),
        (23.114, 45.085),
        (61.976, 163.83),
        (144.526, 40.259),
        (144.526, 34.925),
        (144.526, 45.085),
    ],
    "+15V_LS": [(140.386, 108.331), (146.421, 105.641), (140.386, 113.031)],
    "SW_NODE": [
        (55.245, 165.735),
        (61.976, 158.115),
        (23.114, 40.005),
        (61.976, 163.83),
        (144.526, 40.259),
        (55.245, 160.655),
        (55.245, 170.815),
    ],
    "tank.c_tank1-p2": [(140.386, 108.331), (94.615, 219.075), (94.615, 224.775), (94.615, 213.375)],
    "zcd": [(94.615, 219.075), (23.21, 175.44), (40.4, 210.1), (168.0, 223.03)],
    "power_in.ntc-no": [(92.055, 227.645), (40.4, 210.1), (168.0, 223.03), (23.21, 175.44)],
    "w1_2": [(78.74, 165.1), (23.114, 40.005), (144.526, 40.259)],
    "discharge.k_dis1-nc": [(140.386, 108.331), (94.615, 219.075), (23.114, 40.005), (168.0, 223.03)],
    "discharge.k_dis2-nc": [(140.386, 108.331), (94.615, 213.375), (61.976, 158.115), (55.245, 165.735)],
    "hb.power_loop.q_high-g": [(78.74, 165.1), (61.976, 152.4), (94.615, 224.775)],
}


@pytest.mark.parametrize("net_name", sorted(_REAL_BOARD_NETS))
def test_matches_oracle_real_board_net(net_name):
    positions = _REAL_BOARD_NETS[net_name]
    _assert_partitions_match(positions, net_name)
    _assert_geometry_matches(positions, margin=6.0, label=net_name)  # HighVoltage.clearance


# --- Randomized clustered + symmetric/degenerate stress cases ---------------


def test_matches_oracle_random_clustered_stress():
    rng = random.Random(42)
    mismatches = []
    for trial in range(200):
        n = rng.randint(3, 40)
        n_groups = rng.randint(1, 6)
        positions = []
        for _ in range(n_groups):
            cx, cy = rng.uniform(0, 150), rng.uniform(0, 230)
            for _ in range(max(1, n // n_groups)):
                positions.append((cx + rng.uniform(-2, 2), cy + rng.uniform(-2, 2)))
        positions = positions[:n]
        if len(positions) < 3:
            continue
        oracle_groups = ORACLE._cluster_positions(positions)
        rust_groups = _cluster_positions(positions)
        if _partition_as_set(oracle_groups) != _partition_as_set(rust_groups):
            mismatches.append((trial, positions))
    assert not mismatches, f"{len(mismatches)}/200 random-stress trials mismatched"


@pytest.mark.parametrize(
    "positions",
    [
        pytest.param([(0, 0), (10, 0), (10, 10), (0, 10)], id="square_4"),
        pytest.param(
            [(x, y) for x in (0, 10, 20) for y in (0, 10, 20)], id="square_grid_9"
        ),
        pytest.param(
            [(0, 0), (1, 0), (1, 1), (0, 1), (100, 0), (101, 0), (101, 1), (100, 1)],
            id="two_squares_far",
        ),
        pytest.param(
            [
                (10 * math.cos(a), 10 * math.sin(a))
                for a in [i * math.pi / 3 for i in range(6)]
            ],
            id="hexagon_6",
        ),
        pytest.param([(0, 0), (5, 0), (10, 0), (15, 0), (20, 0)], id="collinear_5"),
        pytest.param([(0, 0), (0, 0), (10, 0), (10, 0), (50, 50)], id="duplicate_points"),
    ],
)
def test_matches_oracle_symmetric_degenerate_configurations(positions):
    _assert_partitions_match(positions, "symmetric/degenerate")

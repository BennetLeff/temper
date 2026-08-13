"""R1a differential: zone/pour emission geometry vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED UNTIL PHASE B.**  Gate G1 requires the
differential that pins the pre-migration implementation verbatim to exist and
fail *before* the Rust exists; every comparison resolves its Rust arm through
``tests/router_v6/_pending_rust.rust`` and fails with a named
``PendingRustError`` until the ``temper_geometry`` migration supplies the
pyfunctions.

Arms
----
* **oracle** -- ``tests/router_v6/_zone_pour_geometry_py_oracle.py``, a
  verbatim ``git show`` copy of ``zone_emission.py`` and
  ``_zone_pour_stitch.py`` at ``a920657f2d4fa2f56b24d71f3ae558dd244dc0fc``
  (``origin/main``).
* **rust** -- the pyfunctions this migration adds to ``temper_geometry``,
  listed in :data:`REQUIRED_RUST_SYMBOLS` and bound in the adapter block
  below.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
No tolerance anywhere -- gate G2.

Kernels covered
----------------
1. ``emit_zone_s_expr`` -- pure string formatting.
2. ``_chamfer_path_points`` -- pure f64 arithmetic, no external library.
3. ``_stitch_isolated_pads``'s geometric core -- point-in-polygon
   (``shapely``) + nearest-boundary-vertex (``scipy.spatial.cKDTree``) --
   replaced by ``stitch_targets_py``. The adapter below composes it with the
   *unmigrated* eligibility/formatting glue exactly as the shipped
   ``_stitch_isolated_pads`` will, so this differential proves the
   composition, not just the raw kernel.

NOT covered here: ``_cluster_positions`` (scipy Ward-linkage clustering) --
migrated separately (2026-08-07) to ``hierarchical_clustering.rs``
(`kodama`), with its own oracle/differential --
``_zone_emission_clustering_py_oracle.py`` /
``test_zone_emission_clustering_rust_differential.py`` -- and its own
evidence doc,
``docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md``.
``_convex_hull_from_positions``'s ``buffer(margin, join_style=2)`` step
(GEOS mitre-join offsetting) remains JUSTIFIED-KEEP, not migrated -- see
``packages/temper-geometry/VERIFICATION.md``.
"""

from __future__ import annotations

import ast
import random
import subprocess
from pathlib import Path

import pytest

import tests.router_v6._zone_pour_geometry_py_oracle as ORACLE
from tests.router_v6._pending_rust import rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "emit_zone_s_expr_py",
    "chamfer_path_points_py",
    "stitch_targets_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


def _rust_emit_zone_s_expr(zone: ORACLE.ZoneDefinition) -> str:
    fn = _rust("emit_zone_s_expr_py")
    return fn(
        zone.net_number,
        zone.net_name,
        zone.layer,
        list(zone.points),
        zone.clearance,
        zone.priority,
        zone.min_thickness,
    )


def _rust_chamfer_path_points(path_points, chamfer_offset=0.1):
    fn = _rust("chamfer_path_points_py")
    return fn(path_points, chamfer_offset)


def _rust_stitch_isolated_pads(
    pad_positions,
    segments,
    net_name_to_number,
    zone_points,
    *,
    tstamp_counter=None,
) -> None:
    """Mirrors the SHIPPED (post-migration) ``_stitch_isolated_pads``: same
    eligibility/formatting glue (unmigrated), Rust for the point-in-polygon
    + nearest-vertex geometry.

    ONE deliberate divergence from the shipped function, added 2026-08-13:
    the shipped one now derives its segment width from the netclass table
    (``_stitch_width_for_net``) instead of the hardcoded ``0.2`` kept here.
    This differential exists to prove ``stitch_targets_py``'s GEOMETRY equals
    the pinned oracle's, and the oracle -- which is verbatim at its pin
    commit and must stay that way -- emits ``0.2``.  Changing the literal
    here would make every comparison below fail on width rather than on
    geometry, i.e. it would break the proof without testing anything new.
    The width itself is pinned separately, against the real netclass table,
    by ``test_trace_width_assignment.py`` and
    ``test_zone_stitch_netclass_width.py``.
    """
    from temper_placer.router_v6._adapter_convert import _next_tstamp
    from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

    if tstamp_counter is None:
        tstamp_counter = [0]

    stitch_fn = _rust("stitch_targets_py")

    for net_name, positions in pad_positions.items():
        if not _zone_layers_for_net(net_name):
            continue
        net_num = net_name_to_number.get(net_name, 0)
        if net_num <= 0 or len(positions) <= 1:
            continue

        zps = zone_points.get(net_name)
        if not zps:
            continue

        polygons = [list(pts) for pts in zps]
        targets = stitch_fn(positions, polygons)
        if not targets:
            continue

        trace_layer = (
            _zone_layers_for_net(net_name)[0] if _zone_layers_for_net(net_name) else "F.Cu"
        )

        for px, py, nearest_x, nearest_y in targets:
            segments.append(
                f"  (segment (start {px:.4f} {py:.4f})"
                f" (end {nearest_x:.4f} {nearest_y:.4f})"
                f' (width {0.2:.4f}) (layer "{trace_layer}")'
                f" (net {net_num})"
                f' (tstamp "{_next_tstamp(tstamp_counter)}"))'
            )


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================


def test_rust_symbols_exist():
    """Checklist: which Rust symbols this migration still owes."""
    from tests.router_v6._pending_rust import missing_symbols

    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, f"pending Rust symbols in {_RUST_MODULE}: {missing}"


# ---------------------------------------------------------------------------
# G1 evidence: oracle is a verbatim pin
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ORACLE_PIN_SHA = "a920657f2d4fa2f56b24d71f3ae558dd244dc0fc"


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def _git_show(rel: str) -> str:
    try:
        return subprocess.run(
            ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")


def test_oracle_is_verbatim_copy():
    """Every pinned definition is character-identical to the pin commit."""
    zone_emission_src = _git_show(
        "packages/temper-placer/src/temper_placer/router_v6/zone_emission.py"
    )
    stitch_src = _git_show(
        "packages/temper-placer/src/temper_placer/router_v6/_zone_pour_stitch.py"
    )

    with open(ORACLE.__file__, encoding="utf-8") as fh:
        oracle_src = fh.read()

    original = {
        **_segments_from_source(zone_emission_src, ("emit_zone_s_expr",)),
        **_segments_from_source(stitch_src, ("_chamfer_path_points", "_stitch_isolated_pads")),
    }
    copied = _segments_from_source(
        oracle_src, ("emit_zone_s_expr", "_chamfer_path_points", "_stitch_isolated_pads")
    )

    for name in ("emit_zone_s_expr", "_chamfer_path_points", "_stitch_isolated_pads"):
        assert name in copied, f"{name} missing from the oracle module"
        assert name in original, f"{name} missing from the pin commit"
        assert copied[name] == original[name], (
            f"{name} in the oracle is NOT verbatim -- the pin is broken and "
            f"the differential proves nothing"
        )


# ---------------------------------------------------------------------------
# emit_zone_s_expr
# ---------------------------------------------------------------------------


def _random_zone(rng: random.Random) -> ORACLE.ZoneDefinition:
    n = rng.randint(3, 8)
    points = tuple((round(rng.uniform(-50, 200), 4), round(rng.uniform(-50, 200), 4)) for _ in range(n))
    return ORACLE.ZoneDefinition(
        net_name=rng.choice(["GND", "+3V3", "AC_L", "SW_NODE", "vcc", "PWR_RTN"]),
        net_number=rng.randint(1, 200),
        layer=rng.choice(["F.Cu", "B.Cu"]),
        points=points,
        clearance=round(rng.uniform(0.1, 6.0), 4),
        min_thickness=round(rng.uniform(0.1, 1.0), 4),
        priority=rng.randint(0, 90),
    )


def test_emit_zone_s_expr_matches_oracle_random_corpus():
    rng = random.Random(20260806)
    for _ in range(200):
        zone = _random_zone(rng)
        oracle_out = ORACLE.emit_zone_s_expr(zone)
        rust_out = _rust_emit_zone_s_expr(zone)
        assert sig(oracle_out) == sig(rust_out), f"zone={zone!r}"


def test_emit_zone_s_expr_matches_oracle_edge_cases():
    cases = [
        ORACLE.ZoneDefinition("GND", 1, "F.Cu", ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),
        ORACLE.ZoneDefinition("GND", 1, "F.Cu", ((-0.0, -0.0), (1.0, 0.0), (0.0, 1.0))),
        ORACLE.ZoneDefinition(
            "ACMains", 999999, "B.Cu",
            ((0.00005, 0.00005), (100.99995, 0.00005), (100.99995, 100.99995)),
            clearance=6.0, min_thickness=0.25, priority=80,
        ),
        ORACLE.ZoneDefinition("N/et\"quote", 1, "F.Cu", ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))),
    ]
    for zone in cases:
        oracle_out = ORACLE.emit_zone_s_expr(zone)
        rust_out = _rust_emit_zone_s_expr(zone)
        assert sig(oracle_out) == sig(rust_out), f"zone={zone!r}"


# ---------------------------------------------------------------------------
# _chamfer_path_points
# ---------------------------------------------------------------------------


def _random_path(rng: random.Random, n: int) -> list[tuple[float, float, str]]:
    layers = ["F.Cu", "B.Cu"]
    layer = rng.choice(layers)
    pts: list[tuple[float, float, str]] = []
    x, y = 0.0, 0.0
    for i in range(n):
        if rng.random() < 0.15:
            layer = rng.choice(layers)
        if rng.random() < 0.5:
            x += rng.choice([-1, 1]) * round(rng.uniform(0.02, 5.0), 4)
        else:
            y += rng.choice([-1, 1]) * round(rng.uniform(0.02, 5.0), 4)
        pts.append((x, y, layer))
    return pts


def test_chamfer_matches_oracle_random_corpus():
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(0, 15)
        path = _random_path(rng, n)
        offset = round(rng.uniform(0.01, 0.5), 4)
        oracle_out = ORACLE._chamfer_path_points(path, chamfer_offset=offset)
        rust_out = _rust_chamfer_path_points(path, offset)
        assert sig(oracle_out) == sig(rust_out), f"path={path!r} offset={offset}"


def test_chamfer_matches_oracle_edge_cases():
    cases = [
        ([], 0.1),
        ([(1.0, 2.0, "F.Cu")], 0.1),
        ([(1.0, 2.0, "F.Cu"), (3.0, 4.0, "F.Cu")], 0.1),
        (
            [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")],
            0.1,
        ),
        (
            [(0.0, 0.0, "F.Cu"), (0.05, 0.0, "F.Cu"), (0.05, 1.0, "F.Cu")],
            0.1,
        ),
        (
            [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "B.Cu"), (1.0, 1.0, "B.Cu")],
            0.1,
        ),
        (
            [
                (0.0, 0.0, "F.Cu"),
                (2.0, 0.0, "F.Cu"),
                (2.0, 2.0, "F.Cu"),
                (4.0, 2.0, "F.Cu"),
                (4.0, 4.0, "F.Cu"),
            ],
            0.1,
        ),
        # default chamfer_offset
        ([(0.0, 0.0, "F.Cu"), (5.0, 0.0, "F.Cu"), (5.0, 5.0, "F.Cu")], 0.1),
    ]
    for path, offset in cases:
        oracle_out = ORACLE._chamfer_path_points(path, chamfer_offset=offset)
        rust_out = _rust_chamfer_path_points(path, offset)
        assert sig(oracle_out) == sig(rust_out), f"path={path!r} offset={offset}"


def test_chamfer_matches_oracle_default_offset():
    path = [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu"), (1.0, 1.0, "F.Cu")]
    oracle_out = ORACLE._chamfer_path_points(path)
    rust_out = _rust_chamfer_path_points(path)
    assert sig(oracle_out) == sig(rust_out)


# ---------------------------------------------------------------------------
# _stitch_isolated_pads
# ---------------------------------------------------------------------------


def test_stitch_matches_oracle_pad_inside_zone_not_stitched():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"ac_l": [(5.0, 5.0)]}
    net_map = {"ac_l": 1}
    zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, zone_points)
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, zone_points)
    assert sig(segments_oracle) == sig(segments_rust)


def test_stitch_matches_oracle_pad_outside_zone_gets_trace():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"ac_l": [(5.0, 5.0), (50.0, 50.0)]}
    net_map = {"ac_l": 1}
    zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, zone_points)
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, zone_points)
    assert sig(segments_oracle) == sig(segments_rust)
    assert len(segments_rust) == 1


def test_stitch_matches_oracle_non_eligible_net_skipped():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"SPI_MOSI": [(50.0, 50.0)]}
    net_map = {"SPI_MOSI": 1}
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, {})
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, {})
    assert sig(segments_oracle) == sig(segments_rust) == sig([])


def test_stitch_matches_oracle_empty_zone_points_skipped():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"ac_l": [(50.0, 50.0)]}
    net_map = {"ac_l": 1}
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, {})
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, {})
    assert sig(segments_oracle) == sig(segments_rust) == sig([])


def test_stitch_matches_oracle_single_pad_inside_is_noop():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"ac_l": [(5.0, 5.0)]}
    net_map = {"ac_l": 1}
    zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, zone_points)
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, zone_points)
    assert sig(segments_oracle) == sig(segments_rust) == sig([])


def test_stitch_matches_oracle_polygon_with_too_few_points_skipped():
    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    pad_positions = {"ac_l": [(50.0, 50.0)]}
    net_map = {"ac_l": 1}
    zone_points = {"ac_l": [((0.0, 0.0), (1.0, 1.0))]}  # degenerate, < 3 pts
    ORACLE._stitch_isolated_pads(pad_positions, segments_oracle, net_map, zone_points)
    _rust_stitch_isolated_pads(pad_positions, segments_rust, net_map, zone_points)
    assert sig(segments_oracle) == sig(segments_rust) == sig([])


def test_stitch_matches_oracle_multi_cluster_multi_pad_random_corpus():
    rng = random.Random(2026)
    for trial in range(60):
        n_clusters = rng.randint(1, 3)
        zone_points_list = []
        for _ in range(n_clusters):
            cx, cy = rng.uniform(0, 200), rng.uniform(0, 200)
            r = rng.uniform(3, 20)
            poly = tuple(
                (round(cx + r * (1 if k % 2 == 0 else -1), 4), round(cy + r * (1 if (k // 2) % 2 == 0 else -1), 4))
                for k in range(4)
            )
            zone_points_list.append(poly)
        n_pads = rng.randint(2, 10)
        positions = [
            (round(rng.uniform(-50, 250), 4), round(rng.uniform(-50, 250), 4)) for _ in range(n_pads)
        ]
        pad_positions = {"ac_l": positions}
        net_map = {"ac_l": trial + 1}
        zone_points = {"ac_l": zone_points_list}

        segments_oracle: list[str] = []
        segments_rust: list[str] = []
        tstamp_oracle = [0]
        tstamp_rust = [0]
        ORACLE._stitch_isolated_pads(
            pad_positions, segments_oracle, net_map, zone_points, tstamp_counter=tstamp_oracle
        )
        _rust_stitch_isolated_pads(
            pad_positions, segments_rust, net_map, zone_points, tstamp_counter=tstamp_rust
        )
        assert sig(segments_oracle) == sig(segments_rust), f"trial={trial}"
        assert tstamp_oracle == tstamp_rust, f"trial={trial}"


def test_stitch_matches_oracle_tstamp_counter_shared_and_advances():
    pad_positions = {"ac_l": [(50.0, 50.0), (60.0, 60.0)]}
    net_map = {"ac_l": 1}
    zone_points = {"ac_l": [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]}

    segments_oracle: list[str] = []
    segments_rust: list[str] = []
    tstamp_oracle = [5]
    tstamp_rust = [5]
    ORACLE._stitch_isolated_pads(
        pad_positions, segments_oracle, net_map, zone_points, tstamp_counter=tstamp_oracle
    )
    _rust_stitch_isolated_pads(
        pad_positions, segments_rust, net_map, zone_points, tstamp_counter=tstamp_rust
    )
    assert sig(segments_oracle) == sig(segments_rust)
    assert tstamp_oracle == tstamp_rust
    assert tstamp_oracle[0] == 7


def test_tie_break_class_exists_direct_cKDTree_comparison():
    """Recorded, non-blocking divergence (see module doc comment in
    zone_pour.rs): on an EXACT nearest-vertex distance tie, ``stitch_targets_py``
    (first-strictly-smaller-wins over input order) and ``scipy.spatial.
    cKDTree.query`` (internal tree-traversal order) do not always pick the
    same vertex.

    This is demonstrated directly against ``cKDTree`` -- not routed through
    ``_stitch_isolated_pads``, because reaching this exact tie through the
    polygon-exterior-coords vertex ordering that function builds is
    incidental to the point being made here (that the two ALGORITHMS
    disagree on ties, independent of how their vertex list is assembled).

    Re-derived 2026-08-07 (temper-NNN): the original 8-vertex forcing
    coordinates stopped reproducing the divergence under the currently
    installed scipy (1.16.3) -- not a Rust-port regression, a scipy-version
    dependency. Root cause: ``cKDTree``'s default ``leafsize`` is 16, and an
    8-point tree never splits into more than one leaf, so it is scanned as a
    single node whose traversal order happens to agree with
    first-strictly-smaller-wins on this scipy build. Reaching an actual
    internal-node split -- and therefore a traversal order that can disagree
    with input order -- needs strictly more than ``leafsize`` points. The
    re-derivation used 20 vertices (comfortably above 16) with the same
    1-decimal-rounded-coordinate randomized search described in the module
    doc comment; this specific set is one of 3 disagreements found scanning
    ~250 forced-tie trials at N=20 verts.
    """
    from scipy.spatial import cKDTree

    verts = [
        (-4.6, -0.4), (0.4, -2.9), (2.5, -2.3), (3.9, 1.9), (-4.3, 4.4),
        (-4.8, -2.2), (-2.3, 3.2), (-0.2, -0.5), (3.8, -0.1), (2.2, 2.7),
        (-1.5, 3.2), (-2.1, -1.4), (3.0, 4.9), (0.5, -0.3), (4.2, -3.9),
        (-1.9, 5.0), (-2.0, -0.7), (-4.6, -1.8), (-2.4, 2.1), (1.5, -1.3),
    ]
    query = (-1.6, -3.4)

    tree = cKDTree(verts)
    _dist, scipy_idx = tree.query(query)

    import temper_geometry as _tg

    # A single vertex far outside `verts`' bounding region keeps `query`
    # classified "outside" (stitch_targets_py only searches `verts` for the
    # nearest point once a pad is outside every polygon; a degenerate
    # 3-point polygon far away satisfies the >=3-point filter without
    # affecting containment of `query`).
    far_polygon = [(1000.0, 1000.0), (1000.1, 1000.0), (1000.0, 1000.1)]
    result = _tg.stitch_targets_py([query], [list(verts), far_polygon])
    assert len(result) == 1
    rust_nearest = (result[0][2], result[0][3])

    scipy_nearest = verts[scipy_idx]
    first_wins_nearest = verts[1]  # index 1, the first of the two tied vertices (indices 1, 11)

    assert rust_nearest == first_wins_nearest, (
        "stitch_targets_py's tie-break contract changed -- expected "
        "first-strictly-smaller-wins"
    )
    assert scipy_nearest != first_wins_nearest, (
        "the forcing coordinates no longer reproduce a scipy/first-wins "
        "disagreement -- this test no longer demonstrates the documented "
        "divergence and should be re-derived"
    )

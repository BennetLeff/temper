"""Differential tests: ``constraints_spatial_index.PCBGeometry``'s persistent
spatial index (Rust ``rstar`` R*-tree, ``temper_geometry.RadiusIndex``) vs
``scipy.spatial.cKDTree``, the pre-migration oracle pinned here per R19
(mirroring ``test_channel_skeleton_radius_pairs_rust_differential.py``'s
structure -- see that file and
``packages/temper-geometry/src/persistent_radius_index.rs`` for the
contract-determination writeup this suite verifies against).

Contract under test, established by reading every call site
(``constraints_spatial_index.py``'s three query methods and every caller in
``constraints_drc_oracle.py``):

1. **Query pattern**: each of ``query_tracks_near`` / ``query_vias_near`` /
   ``query_pads_near`` is a SINGLE-POINT radius query
   (``cKDTree.query_ball_point([x, y], radius)``, never an array of points)
   against a persistent, pre-built index (``rebuild_index()`` builds it once
   per geometry batch; each DRC check queries it again without rebuilding).
2. **Ordering is NOT contractual here** (unlike ``channel_skeleton.py``'s
   ``_radius_pairs``, whose Kruskal MST tie-break makes candidate-pair order
   load-bearing). Two independent reasons, both verified directly against
   this repo's actual source rather than assumed:
   - scipy's ``query_ball_point`` is called with no ``return_sorted``
     argument at any of the three call sites (default ``None``), and
     scipy's own docstring says ``None`` "does not sort single point
     queries" -- so the PRE-migration behavior was never guaranteed sorted
     to begin with. (A prior claim that ``return_sorted=True`` is set at
     these lines does not hold against either the current source or
     ``git log -p --all`` on this file, which has never contained that
     string.)
   - Every caller either early-returns on the first violation found (only
     changing which id lands in a ``reason`` string that
     ``drc_sweep.py``'s caller discards outright, never the pass/fail
     boolean any caller branches on) or collects every match with no
     assertion anywhere in this repo's test suite on a specific violation
     order.
   This suite therefore compares result SETS, not sequences, and separately
   verifies determinism (same query -> same result, repeatably, including
   across processes) rather than scipy-order-matching.
3. **Index set membership matches scipy's `<= radius` inclusion rule
   exactly** -- this IS a hard contract (a false negative silently misses a
   DRC violation; a false positive silently over-restricts placement).

``constraints_spatial_index.py`` no longer imports ``scipy``; it is
retained, unused there, only as the oracle pinned in this file.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import numpy as np
import pytest
from scipy.spatial import cKDTree

from temper_placer.router_v6.constraints_spatial_index import (
    Pad,
    PCBGeometry,
    Point,
    Track,
    Via,
)

# ---------------------------------------------------------------------------
# Oracle: the pre-migration scipy call, pinned verbatim (R19).
# ---------------------------------------------------------------------------


def _scipy_query_ball_point(points: np.ndarray, qx: float, qy: float, radius: float) -> set[int]:
    """Exactly what ``PCBGeometry.query_{tracks,vias,pads}_near`` computed
    before the Rust ``RadiusIndex`` migration: a single-point
    ``cKDTree.query_ball_point`` call, no ``return_sorted`` argument."""
    if len(points) == 0:
        return set()
    tree = cKDTree(points)
    return set(tree.query_ball_point([qx, qy], radius))


# ---------------------------------------------------------------------------
# Corpus: point sets, mirroring radius_pairs' differential corpus shape.
# ---------------------------------------------------------------------------


def _curated_point_sets() -> list[np.ndarray]:
    sets: list[np.ndarray] = []
    sets.append(np.array([[0.0, 0.0]]))
    sets.append(np.array([[0.0, 0.0], [3.0, 4.0]]))  # exact-5 distance pair
    # Coincident points -- real board geometry can produce exact duplicates
    # (stacked vias, symmetric layouts).
    sets.append(np.array([[1.0, 1.0]] * 5 + [[2.0, 2.0]] * 3 + [[50.0, 50.0]]))
    # Regular grid -- many exactly-equal distances from off-grid query
    # points, the sharpest boundary-inclusiveness stress case.
    grid = np.array([[x * 0.5, y * 0.5] for x in range(20) for y in range(20)])
    sets.append(grid)
    # Random dense / sparse, matching real board scale bands (tracks/vias/
    # pads on a real board number in the hundreds to low thousands, not the
    # tens of millions channel_skeleton.py's nodes reach).
    rng = np.random.default_rng(20260807)
    for n, extent in [(50, 5.0), (200, 20.0), (800, 100.0)]:
        sets.append(rng.random((n, 2)) * extent)
    return sets


def _query_radii() -> list[float]:
    """Search radii drawn from the ACTUAL formulas at every
    ``constraints_drc_oracle.py`` call site (``can_place_via``,
    ``can_place_track_segment``, ``validate_all``'s four clearance checks),
    not arbitrary values -- see that module's ``search_radius =`` lines.
    Spans 0 (exact-boundary probing) through the largest real search radius
    a HighVoltage via check can produce."""
    return [
        0.0,
        0.05,
        0.2,  # ClearanceMatrix default_clearance
        0.5,
        1.0,
        2.0,
        3.0,  # track/pad/via clearance-check "+3.0" margin
        4.725,  # can_place_via, via_radius=0.15: (0.15+3.0)*1.5
        5.25,  # can_place_via, via_radius=0.5: (0.5+3.0)*1.5
        8.0,
        20.0,
    ]


# ---------------------------------------------------------------------------
# 1. Result-SET agreement: temper_geometry.RadiusIndex vs cKDTree oracle.
# ---------------------------------------------------------------------------

_POINT_SETS = _curated_point_sets()
_RADII = _query_radii()


@pytest.mark.parametrize("set_idx", range(len(_POINT_SETS)))
def test_radius_index_matches_scipy_for_indexed_query_points(set_idx: int) -> None:
    """Query at every indexed point itself (the query point IS a member of
    the index) -- the common case for via-to-via / pad-to-pad checks where
    the query center coincides with a placed item's own position."""
    import temper_geometry as tg

    points = _POINT_SETS[set_idx]
    points_c = np.ascontiguousarray(points, dtype=np.float64)
    idx = tg.RadiusIndex(points_c.tobytes(), len(points_c))
    assert len(idx) == len(points_c)

    for i, (qx, qy) in enumerate(points_c):
        for radius in _RADII:
            got = set(idx.query_ball_point(float(qx), float(qy), radius))
            want = _scipy_query_ball_point(points_c, float(qx), float(qy), radius)
            assert got == want, f"set={set_idx} point_idx={i} radius={radius}: {got} != {want}"


@pytest.mark.parametrize("set_idx", range(len(_POINT_SETS)))
def test_radius_index_matches_scipy_for_offset_query_points(set_idx: int) -> None:
    """Query at points NOT in the index -- the common case for track/segment
    midpoint checks, where the query center is a computed midpoint that
    rarely coincides exactly with any indexed track/pad/via position."""
    import temper_geometry as tg

    points = _POINT_SETS[set_idx]
    points_c = np.ascontiguousarray(points, dtype=np.float64)
    idx = tg.RadiusIndex(points_c.tobytes(), len(points_c))

    rng = np.random.default_rng(1000 + set_idx)
    lo = points_c.min(axis=0) - 5.0
    hi = points_c.max(axis=0) + 5.0
    for _ in range(15):
        qx, qy = rng.uniform(lo, hi)
        for radius in _RADII:
            got = set(idx.query_ball_point(float(qx), float(qy), radius))
            want = _scipy_query_ball_point(points_c, float(qx), float(qy), radius)
            assert got == want, f"set={set_idx} query=({qx},{qy}) radius={radius}: {got} != {want}"


def test_radius_index_negative_radius_yields_no_matches() -> None:
    import temper_geometry as tg

    points = np.array([[0.0, 0.0], [1.0, 1.0]])
    idx = tg.RadiusIndex(points.tobytes(), len(points))
    assert idx.query_ball_point(0.0, 0.0, -1.0) == []


def test_radius_index_matches_scipy_at_exact_boundary_distance() -> None:
    """Directly addresses the pre-existing KTD9 JUSTIFIED-KEEP rationale
    (``docs/evidence/2026-08-07-constraints-spatial-index-triage-keep.md``,
    Sec "Why this stays Python for now"): "reproducing scipy's exact output
    (including on the boundary-radius ties the DRC clearance checks depend
    on) would require reimplementing scipy's own ball-tree C code." Tested
    directly here rather than assumed: an exact Euclidean distance of 5.0
    (the classic 3-4-5 triangle) at radius exactly 5.0 must be INCLUDED by
    both backends (``<=``, not ``<``), and excluded a hair below it -- this
    is the specific boundary case that rationale worried about, and it
    matches exactly (see also ``persistent_radius_index.rs``'s
    ``test_boundary_is_inclusive`` for the same check at the Rust-only
    level, and ``radius_pairs.rs``'s identical test for the batch API)."""
    import temper_geometry as tg

    points = np.array([[0.0, 0.0], [3.0, 4.0]])
    idx = tg.RadiusIndex(points.tobytes(), len(points))

    for radius in [5.0, 5.0 + 1e-12, 4.999999999999]:
        got = set(idx.query_ball_point(0.0, 0.0, radius))
        want = _scipy_query_ball_point(points, 0.0, 0.0, radius)
        assert got == want, f"radius={radius}: {got} != {want}"

    # Exactly at the boundary: both backends must include the far point
    # (index 0, the query point itself at distance 0, always matches too).
    assert set(idx.query_ball_point(0.0, 0.0, 5.0)) == {0, 1}
    assert _scipy_query_ball_point(points, 0.0, 0.0, 5.0) == {0, 1}
    # A hair under the boundary: both backends must exclude the far point.
    assert idx.query_ball_point(0.0, 0.0, 4.9999999) == [0]
    assert _scipy_query_ball_point(points, 0.0, 0.0, 4.9999999) == {0}


def test_radius_index_empty_geometry_query_returns_empty() -> None:
    """``PCBGeometry.query_*_near`` on empty geometry must return `[]`
    without touching the Rust index at all (pre-migration behavior, still
    required: `rebuild_index()` never builds an index over zero points)."""
    geo = PCBGeometry()
    assert geo.query_tracks_near(Point(0, 0), 5.0) == []
    assert geo.query_vias_near(Point(0, 0), 5.0) == []
    assert geo.query_pads_near(Point(0, 0), 5.0) == []


# ---------------------------------------------------------------------------
# 2. End-to-end: PCBGeometry.query_*_near vs a scipy-backed re-implementation
#    of the same three methods, on realistic mixed track/via/pad geometry.
# ---------------------------------------------------------------------------


def _scipy_query_tracks_near(tracks: list[Track], point: Point, radius: float, layer=None):
    if not tracks:
        return []
    mids = np.array([[t.midpoint().x, t.midpoint().y] for t in tracks])
    idxs = _scipy_query_ball_point(mids, point.x, point.y, radius)
    out = [tracks[i] for i in idxs]
    if layer is not None:
        out = [t for t in out if t.layer == layer]
    return out


def _scipy_query_vias_near(vias: list[Via], point: Point, radius: float):
    if not vias:
        return []
    centers = np.array([[v.center.x, v.center.y] for v in vias])
    idxs = _scipy_query_ball_point(centers, point.x, point.y, radius)
    return [vias[i] for i in idxs]


def _scipy_query_pads_near(pads: list[Pad], point: Point, radius: float, layer=None):
    if not pads:
        return []
    centers = np.array([[p.center.x, p.center.y] for p in pads])
    idxs = _scipy_query_ball_point(centers, point.x, point.y, radius)
    out = [pads[i] for i in idxs]
    if layer is not None:
        out = [p for p in out if p.layer == layer or p.is_pth]
    return out


def _build_mixed_geometry(rng: np.random.Generator, n_tracks: int, n_vias: int, n_pads: int) -> PCBGeometry:
    geo = PCBGeometry()
    for _ in range(n_tracks):
        sx, sy = rng.uniform(-20, 20, size=2)
        ex, ey = sx + rng.uniform(-5, 5), sy + rng.uniform(-5, 5)
        geo.add_track(
            Track(
                start=Point(float(sx), float(sy)),
                end=Point(float(ex), float(ey)),
                width=0.25,
                net=f"N{int(rng.integers(0, 5))}",
                layer=int(rng.integers(0, 2)),
            )
        )
    for _ in range(n_vias):
        cx, cy = rng.uniform(-20, 20, size=2)
        geo.add_via(
            Via(center=Point(float(cx), float(cy)), diameter=0.6, drill=0.3, net=f"N{int(rng.integers(0, 5))}")
        )
    for _ in range(n_pads):
        cx, cy = rng.uniform(-20, 20, size=2)
        geo.add_pad(
            Pad(
                center=Point(float(cx), float(cy)),
                shape="rect",
                size=(1.0, 1.0),
                net=f"N{int(rng.integers(0, 5))}",
                layer=int(rng.integers(0, 2)),
            )
        )
    geo.rebuild_index()
    return geo


def test_pcb_geometry_queries_match_scipy_oracle_on_mixed_geometry() -> None:
    rng = np.random.default_rng(20260807)
    geo = _build_mixed_geometry(rng, n_tracks=120, n_vias=60, n_pads=90)

    query_points = [Point(float(x), float(y)) for x, y in rng.uniform(-25, 25, size=(20, 2))]
    for point in query_points:
        for radius in _RADII:
            for layer in (None, 0, 1):
                got_tracks = {t.id for t in geo.query_tracks_near(point, radius, layer)}
                want_tracks = {t.id for t in _scipy_query_tracks_near(geo.tracks, point, radius, layer)}
                assert got_tracks == want_tracks

                got_pads = {p.id for p in geo.query_pads_near(point, radius, layer)}
                want_pads = {p.id for p in _scipy_query_pads_near(geo.pads, point, radius, layer)}
                assert got_pads == want_pads

            got_vias = {v.id for v in geo.query_vias_near(point, radius)}
            want_vias = {v.id for v in _scipy_query_vias_near(geo.vias, point, radius)}
            assert got_vias == want_vias


def test_drc_oracle_validate_all_violation_multiset_matches_scipy_backed_geometry() -> None:
    """The property that actually matters downstream: `DRCOracle.validate_all()`'s
    violation content (as an order-independent multiset of (type, a, b) triples)
    must be identical whether the underlying geometry index is the Rust
    ``RadiusIndex`` (production, exercised via the normal ``PCBGeometry`` import)
    or the pre-migration scipy oracle re-implementation above -- i.e. the
    migration must not change which DRC violations are found, only how the
    candidate geometry is looked up."""
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
    from temper_placer.router_v6.constraints_drc_oracle import DRCOracle

    rng = np.random.default_rng(7)
    rules = ClearanceMatrix(default_clearance=0.2)

    # Build once via the (now Rust-backed) production oracle.
    oracle = DRCOracle(rules=rules)
    tracks, vias, pads = [], [], []
    for _ in range(40):
        sx, sy = rng.uniform(-10, 10, size=2)
        ex, ey = sx + rng.uniform(-2, 2), sy + rng.uniform(-2, 2)
        t = Track(
            start=Point(float(sx), float(sy)),
            end=Point(float(ex), float(ey)),
            width=0.25,
            net=f"N{int(rng.integers(0, 4))}",
            layer=int(rng.integers(0, 2)),
        )
        tracks.append(t)
        oracle.register_track(t)
    for _ in range(20):
        cx, cy = rng.uniform(-10, 10, size=2)
        v = Via(center=Point(float(cx), float(cy)), diameter=0.6, drill=0.3, net=f"N{int(rng.integers(0, 4))}")
        vias.append(v)
        oracle.register_via(v)
    for _ in range(20):
        cx, cy = rng.uniform(-10, 10, size=2)
        p = Pad(
            center=Point(float(cx), float(cy)),
            shape="rect",
            size=(1.0, 1.0),
            net=f"N{int(rng.integers(0, 4))}",
            layer=int(rng.integers(0, 2)),
        )
        pads.append(p)
        oracle.register_pad(p)

    rust_violations = oracle.validate_all()
    rust_multiset = sorted(
        (v.type, v.geometry_a_id, v.geometry_b_id) for v in rust_violations
    )

    # Re-run the identical validate_all() algorithm, but with every
    # query_*_near swapped for the scipy oracle re-implementation above --
    # verifies the migration changed only the lookup, not the result.
    geo = oracle.geometry
    scipy_violations: list[tuple[str, str, str]] = []
    for track_a in geo.tracks:
        seg_a = track_a.to_segment()
        search_radius = (seg_a.length / 2) + rules.default_clearance + 0.5
        for track_b in _scipy_query_tracks_near(geo.tracks, seg_a.midpoint(), search_radius, track_a.layer):
            if track_a.id >= track_b.id or track_a.net == track_b.net or track_a.is_diff_pair_with(track_b):
                continue
            from temper_placer.router_v6.constraints_geometry import segment_to_segment_distance

            mid = seg_a.midpoint()
            required = rules.get_clearance(track_a.net, track_b.net, mid.x, mid.y)
            effective = required + (track_a.width / 2) + (track_b.width / 2)
            actual = segment_to_segment_distance(seg_a, track_b.to_segment())
            if actual < effective - 0.010:
                scipy_violations.append(("track_clearance", track_a.id, track_b.id))
    for via_a in geo.vias:
        search_radius = (via_a.diameter / 2) + rules.default_clearance + 0.5
        for via_b in _scipy_query_vias_near(geo.vias, via_a.center, search_radius):
            if via_a.id >= via_b.id or via_a.net == via_b.net:
                continue
            required = rules.get_clearance(via_a.net, via_b.net, via_a.center.x, via_a.center.y)
            effective = required + (via_a.diameter / 2) + (via_b.diameter / 2)
            actual = via_a.center.distance_to(via_b.center)
            if actual < effective:
                scipy_violations.append(("via_to_via", via_a.id, via_b.id))
    for track in geo.tracks:
        seg = track.to_segment()
        search_radius = (seg.length / 2) + rules.default_clearance + 3.0
        for pad in _scipy_query_pads_near(geo.pads, seg.midpoint(), search_radius, track.layer):
            if track.net == pad.net or track.diff_pair_companion == pad.net:
                continue
            from temper_placer.router_v6.constraints_geometry import (
                segment_to_rotated_rect_distance,
            )

            mid = seg.midpoint()
            required = rules.get_clearance(track.net, pad.net, mid.x, mid.y)
            effective = required + (track.width / 2) + pad.mask_expansion
            actual = segment_to_rotated_rect_distance(seg, pad.rot_rect)
            if actual < effective:
                scipy_violations.append(("track_pad_clearance", track.id, pad.id))
    for via in geo.vias:
        search_radius = (via.diameter / 2) + rules.default_clearance + 3.0
        for pad in _scipy_query_pads_near(geo.pads, via.center, search_radius):
            if via.net == pad.net:
                continue
            from temper_placer.router_v6.constraints_geometry import point_to_rotated_rect_distance

            required = rules.get_clearance(via.net, pad.net, via.center.x, via.center.y)
            effective = required + (via.diameter / 2) + pad.mask_expansion
            actual = point_to_rotated_rect_distance(via.center, pad.rot_rect)
            if actual < effective:
                scipy_violations.append(("via_pad_clearance", via.id, pad.id))

    scipy_multiset = sorted(scipy_violations)
    assert rust_multiset == scipy_multiset


# ---------------------------------------------------------------------------
# 3. Determinism: same-process repeated queries and cross-process.
# ---------------------------------------------------------------------------


def test_repeated_queries_against_same_index_are_deterministic() -> None:
    import temper_geometry as tg

    rng = np.random.default_rng(42)
    points = np.ascontiguousarray(rng.random((300, 2)) * 40.0, dtype=np.float64)
    idx = tg.RadiusIndex(points.tobytes(), len(points))

    first = idx.query_ball_point(20.0, 20.0, 5.0)
    for _ in range(10):
        assert idx.query_ball_point(20.0, 20.0, 5.0) == first

    # Interleaving other queries must not perturb a later repeat -- the
    # tree is read-only after construction.
    idx.query_ball_point(0.0, 0.0, 3.0)
    idx.query_ball_point(39.0, 1.0, 3.0)
    assert idx.query_ball_point(20.0, 20.0, 5.0) == first


def test_radius_index_byte_identical_across_processes() -> None:
    """Same content-addressing requirement radius_pairs.rs's differential
    suite already established for the batch API: the same index + same
    query must produce byte-identical results whether run again in this
    process or from a freshly started one."""
    script = textwrap.dedent(
        """
        import numpy as np
        import temper_geometry as tg
        import sys

        rng = np.random.default_rng(20260807)
        positions = np.ascontiguousarray(rng.random((300, 2)) * 40.0, dtype=np.float64)
        idx = tg.RadiusIndex(positions.tobytes(), len(positions))
        results = []
        for qx, qy, r in [(20.0, 20.0, 5.0), (0.0, 0.0, 3.0), (39.5, 39.5, 8.0)]:
            results.append(idx.query_ball_point(qx, qy, r))
        sys.stdout.write(repr(results))
        """
    )
    outputs = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
            text=True,
        )
        outputs.append(proc.stdout)
    assert len(outputs[0]) > 0
    assert outputs[0] == outputs[1], "RadiusIndex.query_ball_point output differs across processes"

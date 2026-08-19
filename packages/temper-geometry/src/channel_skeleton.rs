// Wave 4: router_v6/channel_skeleton.py's medial-axis extraction
// (`_extract_medial_axis` / `_extract_medial_axis_single`).
//
// Unblocked by `fix/constraint-model-edge-identity` (not yet on `main` as of
// this port; branched from `origin/fix/constraint-model-edge-identity`
// directly). SAT channel-edge identity
// (`constraint_model.py::canonical_channel_edges`) now comes from endpoint
// coordinates quantised to 1e-6 mm and ordered by that quantised key, not
// from Voronoi emission order or a raw float `repr()`. The 2026-08-04 spike
// (`docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md`)
// measured an independent (Qhull) Voronoi reproducing the GEOS skeleton to
// <1e-9 mm on 12/12 synthetic boards -- three orders of magnitude finer than
// the 1e-6 mm quantum -- so a correct independent Voronoi and GEOS now
// resolve to the SAME quantised SAT variable identity.
//
// Re-verified here before this port started (not inherited from the spike):
// 12/12 boards agree at the 1e-6 mm node-set level AND directly on
// `canonical_channel_edges()`-style ids computed independently over a
// GEOS-built graph and a Qhull-built graph. See this crate's PR description
// for the reproduction script; the claim held.
//
// This module uses `spade` (Delaunay triangulation, `robust`-crate exact
// circumcenter predicates) rather than shapely/GEOS: an independent,
// non-GEOS implementation, the same class the spike measured against
// (Qhull) and the class `docs/evidence/...-spike.md` §7 names as the
// parity target (`voronator`/`spade`/`geo`).
//
// Scope -- what moves here and what stays in Python
// ---------------------------------------------------
// MOVES: `_extract_medial_axis_single`'s full pipeline (boundary sampling,
// Voronoi, interior-edge filter, and the two fallback branches) and
// `_extract_medial_axis`'s (Multi)Polygon dispatch.
//
// STAYS IN PYTHON (orchestration, not compute -- out of scope for this
// pull): `_ensure_skeleton_connectivity` (`nx.Graph` bookkeeping -- an
// O(n^2) nearest-pair search over networkx node/component objects; the one
// arithmetic expression inside it is a one-line Euclidean distance, and
// marshalling the whole component/node structure across the FFI boundary
// per call is the "per-call marshalling boundary can be net-negative" trap
// this repo's own Wave 4 dispatch-readiness notes measured elsewhere, e.g.
// `docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md`) and
// `ChannelSkeletonStage`/`validate_channel_skeleton` (pipeline `Stage` /
// `@register_validator` wiring).
//
// 2026-08-18 CORRECTION: this list used to end "...plus the pad-anchoring
// dict/list bookkeeping in `extract_channel_skeleton`". That was wrong on
// cost and the claim has been retracted -- the pad anchoring's two nested
// scans were 73.4s of pure Python on this board, the largest single
// line-item in the route, and they now live in `pad_anchor_plan` below. The
// list/dict handling around them really was bookkeeping; the two
// O(pads x nodes) sweeps in the middle were not, and describing the block
// by its outer layer is how they went unexamined through three triage
// passes.
//
// `simplify_tolerance` is accepted for signature parity with the Python
// caller but is a documented no-op: the 2026-08-04 spike (§8) measured that
// GEOS's Voronoi edges on this path are always exactly 2 coordinates, and
// Douglas-Peucker simplification of a 2-point line is the identity. spade's
// undirected Voronoi edges are likewise always two circumcenters -- i.e.
// also always 2 points -- so the same holds structurally here, not just
// empirically for GEOS.

use crate::creepage_check::py_min;
use crate::host_math;
use crate::polygon::{point_in_polygon_winding, polygon_bounding_box, polygon_centroid};
use crate::types::Point;

use spade::handles::VoronoiVertex;
use spade::{DelaunayTriangulation, Point2, Triangulation};

/// One filtered, finite Voronoi/skeleton edge -- a straight segment between
/// its two endpoints. Mirrors what `_extract_medial_axis_single` yields per
/// `LineString` (always 2 coordinates on this path; see module doc).
pub type Segment = (Point, Point);

/// Sample points along one ring's edges at ~1mm spacing, appending into
/// `out`. Verbatim port of `channel_skeleton.py:240-269`'s boundary
/// sampling loop body. `ring` is expected closed (`ring[0] == ring[last]`),
/// matching a shapely `LinearRing`'s `.coords` -- the same convention
/// `channel_skeleton.py` relies on when it does `range(len(coords) - 1)`.
fn sample_ring(ring: &[Point], out: &mut Vec<Point>) {
    if ring.len() < 2 {
        return;
    }
    for pair in ring.windows(2) {
        let p1 = pair[0];
        let p2 = pair[1];
        let dx = p2.x - p1.x;
        let dy = p2.y - p1.y;
        // CPython: `dist = (dx**2 + dy**2) ** 0.5` -- `**` on floats is
        // libm `pow` (see `host_math` module doc), NOT `f64::sqrt`, and NOT
        // `math.hypot` (this file never calls `hypot`).
        let dist = host_math::pow(host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0), 0.5);
        // CPython: `num_points = max(2, int(dist))`. `int()` truncates
        // toward zero, not floor; `dist` is a Euclidean distance (always
        // >= 0 and finite for real polygon boundaries) so truncation and
        // floor agree numerically here, but the cast is written explicitly
        // (not `.floor()`) per this crate's documented `int()`-truncation
        // trap (see e.g. `grid_raster.rs`).
        let num_points = (dist as i64).max(2);
        for j in 0..num_points {
            let t = j as f64 / num_points as f64;
            out.push(Point::new(p1.x + t * dx, p1.y + t * dy));
        }
    }
}

/// Sample points along every ring of a polygon (exterior + holes).
///
/// Mirrors `channel_skeleton.py`'s iteration over `polygon.boundary`'s
/// parts: a `MultiLineString` (one `LineString` per ring) when holes are
/// present, a single `LinearRing` otherwise -- both reduce to "iterate
/// every ring, exterior first, in the polygon's own ring order".
pub fn sample_boundary_points(outer: &[Point], holes: &[Vec<Point>]) -> Vec<Point> {
    let mut points = Vec::new();
    sample_ring(outer, &mut points);
    for hole in holes {
        sample_ring(hole, &mut points);
    }
    points
}

/// Is `p` inside the available routing area (inside the outer ring, outside
/// every hole)? Boundary-inclusive (see `point_in_polygon_winding`), the
/// same convention `prepped_buffered.contains(midpoint)` uses for the
/// (already-buffered) polygon in the Python reference.
fn point_in_available_area(p: &Point, outer: &[Point], holes: &[Vec<Point>]) -> bool {
    if !point_in_polygon_winding(p, outer) {
        return false;
    }
    for hole in holes {
        if point_in_polygon_winding(p, hole) {
            return false;
        }
    }
    true
}

/// Fallback skeleton when Voronoi/triangulation yields nothing: a cross
/// pattern through the polygon centroid, inset from the bounding box.
/// Verbatim port of `channel_skeleton.py:331-349`.
///
/// Note: `polygon_centroid` is computed from the outer ring only. The
/// Python reference's `polygon.centroid` is shapely's area-weighted
/// centroid, which technically nets out hole area too -- this only differs
/// from the outer-ring-only centroid when holes exist AND this fallback
/// fires, which requires < 3 total boundary sample points across every ring
/// (practically unreachable for any real routing-space polygon: even a
/// single triangular ring samples at least 2 points per edge). Documented,
/// not fixed, given how far outside the reachable input space it sits.
fn fallback_cross_pattern(outer: &[Point]) -> Vec<Segment> {
    let centroid = polygon_centroid(outer);
    let aabb = polygon_bounding_box(outer);
    let width = aabb.x_max - aabb.x_min;
    let height = aabb.y_max - aabb.y_min;
    // CPython: `inset_x = min(0.5, width * 0.1)` -- builtin `min(a, b)`
    // semantics (first-arg-sticky on NaN), not `f64::min`. See
    // `creepage_check::py_min`.
    let inset_x = py_min(0.5, width * 0.1);
    let inset_y = py_min(0.5, height * 0.1);
    vec![
        (
            Point::new(aabb.x_min + inset_x, centroid.y),
            Point::new(aabb.x_max - inset_x, centroid.y),
        ),
        (
            Point::new(centroid.x, aabb.y_min + inset_y),
            Point::new(centroid.x, aabb.y_max - inset_y),
        ),
    ]
}

/// Degenerate "skeleton": a single zero-length point at the centroid, for
/// when fewer than 3 boundary sample points exist at all. Verbatim port of
/// `channel_skeleton.py:271-275`.
fn degenerate_point_segment(outer: &[Point]) -> Vec<Segment> {
    let centroid = polygon_centroid(outer);
    vec![(centroid, centroid)]
}

/// Extract the medial-axis skeleton for a single polygon (outer ring plus
/// optional holes) via an independent Voronoi diagram.
///
/// Mirrors `_extract_medial_axis_single` (`channel_skeleton.py:218-349`):
/// boundary sampling -> Voronoi -> interior-edge filter -> segments, with
/// the same two fallback branches on degenerate/failed input.
pub fn extract_medial_axis_single(
    outer: &[Point],
    holes: &[Vec<Point>],
    _simplify_tolerance: f64,
) -> Vec<Segment> {
    let points = sample_boundary_points(outer, holes);
    if points.len() < 3 {
        return degenerate_point_segment(outer);
    }

    let mut triangulation: DelaunayTriangulation<Point2<f64>> = DelaunayTriangulation::new();
    let mut insertion_ok = true;
    for p in &points {
        if triangulation.insert(Point2::new(p.x, p.y)).is_err() {
            insertion_ok = false;
            break;
        }
    }

    if insertion_ok {
        let mut skeleton_lines: Vec<Segment> = Vec::new();
        for edge in triangulation.undirected_voronoi_edges() {
            if let [VoronoiVertex::Inner(from), VoronoiVertex::Inner(to)] = edge.vertices() {
                let c1 = from.circumcenter();
                let c2 = to.circumcenter();
                let p1 = Point::new(c1.x, c1.y);
                let p2 = Point::new(c2.x, c2.y);
                if p1.x == p2.x && p1.y == p2.y {
                    // `if simplified.length > 0` filter -- simplify is the
                    // identity here (see module doc), so this is just a
                    // zero-length-segment check.
                    continue;
                }
                // `geom.interpolate(0.5, normalized=True)` on a straight
                // 2-point line is exactly the arithmetic midpoint.
                let mid = p1.midpoint(&p2);
                if point_in_available_area(&mid, outer, holes) {
                    skeleton_lines.push((p1, p2));
                }
            }
        }
        if !skeleton_lines.is_empty() {
            return skeleton_lines;
        }
    }

    fallback_cross_pattern(outer)
}

/// Extract the medial-axis skeleton for a (Multi)Polygon: dispatches over
/// each constituent polygon and concatenates. Mirrors `_extract_medial_axis`
/// (`channel_skeleton.py:181-215`); the `Polygon`/`MultiPolygon`/other-type
/// branch there collapses here to "iterate whatever polygons are given",
/// since the pyo3 boundary already receives a `Vec` of polygons (the
/// Python-side type dispatch is marshalling, not compute).
pub fn extract_medial_axis(
    polygons: &[(Vec<Point>, Vec<Vec<Point>>)],
    simplify_tolerance: f64,
) -> Vec<Segment> {
    let mut all = Vec::new();
    for (outer, holes) in polygons {
        all.extend(extract_medial_axis_single(outer, holes, simplify_tolerance));
    }
    all
}


// ===========================================================================
// Pad anchoring (`extract_channel_skeleton`'s "OPTION F FIX" block)
// ===========================================================================
//
// This block was explicitly declared out of scope by the medial-axis port
// above ("STAYS IN PYTHON ... the pad-anchoring dict/list bookkeeping in
// `extract_channel_skeleton`"), and by `_channel_skeleton_py_oracle.py`'s
// docstring, on the grounds that it is orchestration rather than compute.
//
// That was wrong on cost. A cProfile of a full production route (301.04s
// wall, board digest `6d4e17337bcf2633`, 4553 segments) attributes:
//
//   channel_skeleton.py:56  `extract_channel_skeleton`  22.3s SELF, 6 calls
//   channel_skeleton.py:159 `<genexpr>`                 15.2s, 97,412,627 calls
//
// The self time is the `for node in skeleton_nodes` nearest-node scan,
// which is written inline in `extract_channel_skeleton` and so is charged
// to it rather than to a callee. The genexpr is the `any(...)` pad-dedup
// scan. Both are brute-force O(pads x skeleton_nodes) sweeps over Python
// coordinate tuples, and this board's outer layers carry ~41k skeleton
// nodes each. The "bookkeeping" description fit the list/dict handling
// around them and missed the two nested scans in the middle -- together the
// largest single line-item in the whole route.
//
//
// Measured on this board after the port (isolated harness, same real
// routing spaces, both arms fed the identical node snapshot):
//
//   layer     nodes    pads    Python      Rust   speedup   anchored
//   B.Cu      77833     523     9.67s     1.131s      9x        488
//   F.Cu     115513     523    22.76s     1.716s     13x        494
//   In1.Cu    32694     523     4.65s     0.488s     10x        503
//   In2.Cu    32694     523     4.98s     0.491s     10x        503
//   In3.Cu    76413     523    15.16s     1.153s     13x        478
//   In4.Cu    80051     523    16.20s     1.167s     14x        488
//   TOTAL                      73.42s     6.145s     12x
//
// 67.3s removed, bit-exact on every layer. Note this is roughly DOUBLE the
// 37.5s the cProfile attributed (22.3s self + 15.2s genexpr): the profiled
// run's board digest was `6d4e17337bcf2633`, and this tree's skeletons carry
// more nodes than that run's genexpr count of 97,412,627 implies (523 pads x
// 415,198 total nodes is ~217M comparisons here). The measured figure is the
// one to trust for this tree; the profile's is not wrong, it is a different
// board state.
//
// The remaining 6.1s is almost entirely the two `host_math::pow` calls per
// comparison (~434M libm calls): the price of bit-exactness, paid
// deliberately. A provably-safe prune exists -- `dist >= sqrt(pow(dx,2))
// >= |dx|(1 - 2^-51)`, so a candidate with `|dx|` comfortably above the
// running minimum can be rejected without evaluating `pow` at all -- and is
// left undone here rather than bundled into a migration whose entire value
// is that the answer did not change.
//
// Fidelity: verbatim transcription, deliberately NOT a rewrite
// --------------------------------------------------------------
// This is search-and-classification code (which node is nearest?), not an
// emitted pour outline, so two different answers can both be "legal" and
// only equality reveals a change. The obvious optimisation -- put the nodes
// in the `rstar` R*-tree this crate already uses in `radius_pairs.rs` and
// ask it for nearest neighbours -- is NOT taken, because a tree's notion of
// "nearest" is its own distance metric with its own tie-breaking, and the
// Python being replaced resolves ties to the EARLIEST node in
// `skeleton_nodes` order via a strict `<`. A brute-force transcription is
// bit-exact by construction and still removes ~37s of the 301s route; a
// tree would buy a fraction of a second more and put the tie-break at risk.
// Deliberate non-optimisation, not an oversight.
//
// Points of behaviour preserved on purpose (each one is load-bearing):
//
//   * `skeleton_nodes` is snapshotted BEFORE the pad loop. Pads anchored
//     earlier in the loop are invisible to later dedup checks and later
//     nearest-node searches. Hence `nodes` here is a fixed slice that this
//     function never appends to.
//   * The dedup predicate is a strict axis-aligned BOX test
//     (`abs(dx) < 0.1 and abs(dy) < 0.1`), not a radius test. A pad
//     0.14mm away diagonally is NOT deduped.
//   * `any(...)` short-circuits, but the dedup result is the only thing
//     that escapes it, so evaluating it fused with the nearest-node scan
//     (one pass over `nodes` instead of two) is observationally identical.
//     The fused pass is why this is one loop below and two in the Python.
//   * The nearest search uses strict `<`, so the EARLIEST index wins a tie.
//   * A pad that duplicates an earlier pad's position still yields its own
//     record, so the caller still does its own `total_length += min_dist`
//     and `pads_added += 1` even though the graph dedupes the node and
//     edge away. That double-count is reproduced, not fixed.
//
// Float exactness: `**` is libm `pow`, and it is NOT `d * d` here
// ------------------------------------------------------------------
// The Python is `math.sqrt((pad[0] - node[0]) ** 2 + (pad[1] - node[1]) ** 2)`.
// `**` on CPython floats is libm `pow` (see `host_math`'s module doc), so
// this resolves both squarings through `host_math::pow` rather than writing
// the arithmetically-obvious `d * d`.
//
// This is not a stylistic point. `pow(d, 2.0) != d * d` on ordinary board
// coordinates -- MEASURED, not assumed. `d = 98.07985406973864` gives
// `9619.657774341229` from `pow` and `9619.657774341227` from the
// multiplication, one ulp apart, and CPython reproduces the `pow` answer
// exactly because CPython's `**` IS this libm `pow`. See
// `multiplication_is_not_a_valid_substitute_for_pow_at_board_scale`.
//
// One ulp is enough. This is an argmin over distances, so a last-bit
// difference can flip a near tie and re-anchor a pad to a DIFFERENT
// skeleton node -- another answer that is equally "legal" and that only
// bit-equality would ever expose. The plausible-looking argument for the
// multiplication ("glibc's pow is correctly rounded, and `d * d` is by
// definition the correctly rounded product, so they must agree") is exactly
// the correct-by-coincidence reasoning AGENTS.md's `net_currents()` story
// warns about, and here it is simply false.
//
// `math.sqrt` is a genuinely different case and IS lowered to `f64::sqrt`:
// IEEE-754 REQUIRES `sqrt` to be correctly rounded, so every conforming
// implementation returns the same bits. `pow` carries no such requirement --
// and CPython's `math.sqrt(s)` and `s ** 0.5` are therefore NOT the same
// function. They disagree at `s = 55489.646545994874` (`235.5624047805483`
// vs `235.56240478054826`). Both spellings appear in this module, reading
// from two different lines of the same Python file: `sample_ring`
// transcribes `** 0.5` and uses `host_math::pow(_, 0.5)`; `pad_anchor_plan`
// transcribes `math.sqrt` and uses `f64::sqrt`. See
// `math_sqrt_and_pow_half_are_not_interchangeable`.
//
// Note the comparison must stay on the `sqrt` value, not on the squared
// sum: `sqrt` is monotonic but rounds, so two distinct sums can collapse to
// one distance. Ranking by the squared sum would then break a tie the
// Python resolves by index order. See `argmin_ranks_on_the_rounded_sqrt`.

/// One pad that should be anchored into the skeleton graph.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PadAnchor {
    /// Index into the `pads` slice.
    pub pad_index: usize,
    /// Index into the `nodes` slice of the winning nearest skeleton node.
    pub node_index: usize,
    /// `math.sqrt(...)` distance between them, to be used verbatim as the
    /// new edge's `weight` and added to `total_length`.
    pub dist: f64,
}

/// Decide which pads get anchored, and to which skeleton node.
///
/// Transcribes the pad-anchoring scan of `extract_channel_skeleton`
/// (`channel_skeleton.py:153-179` at the pinned commit). Returns one record
/// per pad that survives the dedup check AND lands within `max_connect` of
/// some node, in pad order -- the caller replays them in that order so its
/// `total_length` accumulates in exactly the original sequence (float
/// addition is not associative, so the order is part of the contract).
///
/// `dedup_tol` is the Python's literal `0.1` and `max_connect` its literal
/// `50.0`; they are parameters here only so the differential harness can
/// prove the port over the same constants the caller passes, never to
/// permit a caller to widen them.
pub fn pad_anchor_plan(
    pads: &[Point],
    nodes: &[Point],
    dedup_tol: f64,
    max_connect: f64,
) -> Vec<PadAnchor> {
    let mut out: Vec<PadAnchor> = Vec::new();

    for (pad_index, pad) in pads.iter().enumerate() {
        // Fused dedup + nearest pass. `deduped` reproduces the `any(...)`
        // generator; `nearest`/`min_dist` reproduce the scan that follows
        // it. Fusing is safe because the Python discards the nearest-node
        // result whenever the dedup fired, and computing it anyway has no
        // other observable effect.
        let mut deduped = false;
        let mut nearest: Option<usize> = None;
        let mut min_dist = f64::INFINITY;

        for (i, node) in nodes.iter().enumerate() {
            let dx = pad.x - node.x;
            let dy = pad.y - node.y;

            if !deduped && dx.abs() < dedup_tol && dy.abs() < dedup_tol {
                deduped = true;
            }

            // CPython: `math.sqrt((dx) ** 2 + (dy) ** 2)` -- libm `pow`
            // twice, then libm `sqrt`. See this section's module comment
            // for why `dx * dx` is not written here.
            let dist = (host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0)).sqrt();
            if dist < min_dist {
                min_dist = dist;
                nearest = Some(i);
            }
        }

        if deduped {
            continue;
        }

        // CPython: `if nearest_node and min_dist < 50.0`. `nearest_node` is
        // a 2-tuple, and a non-empty tuple is always truthy, so the guard
        // is `is not None` in every reachable case -- including the pad at
        // the origin, where `(0.0, 0.0)` would be falsy only if it were a
        // number rather than a tuple.
        if let Some(node_index) = nearest
            && min_dist < max_connect
        {
            out.push(PadAnchor {
                pad_index,
                node_index,
                dist: min_dist,
            });
        }
    }

    out
}

// ===========================================================================
// pyo3 boundary
// ===========================================================================

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
type CoordPair = (f64, f64);

#[cfg(feature = "python")]
fn to_points(coords: Vec<CoordPair>) -> Vec<Point> {
    coords.into_iter().map(|(x, y)| Point::new(x, y)).collect()
}

#[cfg(feature = "python")]
fn segments_to_py(segments: Vec<Segment>) -> Vec<(CoordPair, CoordPair)> {
    segments
        .into_iter()
        .map(|(p1, p2)| ((p1.x, p1.y), (p2.x, p2.y)))
        .collect()
}

/// pyo3 boundary for [`extract_medial_axis_single`].
///
/// `outer`/`holes` are ring coordinate lists exactly as shapely exposes them
/// (`polygon.exterior.coords`, `[interior.coords for interior in
/// polygon.interiors]`) -- closed rings, first coordinate repeated last.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (outer, holes, simplify_tolerance))]
pub fn extract_medial_axis_single_py(
    outer: Vec<CoordPair>,
    holes: Vec<Vec<CoordPair>>,
    simplify_tolerance: f64,
) -> PyResult<Vec<(CoordPair, CoordPair)>> {
    temper_py_bridge::catch_unwind(|| {
        let outer_pts = to_points(outer);
        let holes_pts: Vec<Vec<Point>> = holes.into_iter().map(to_points).collect();
        let segments = extract_medial_axis_single(&outer_pts, &holes_pts, simplify_tolerance);
        segments_to_py(segments)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 boundary for [`extract_medial_axis`]. `polygons` is a list of
/// `(outer_ring, holes)` pairs, one per constituent polygon of a
/// `Polygon`/`MultiPolygon`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (polygons, simplify_tolerance))]
pub fn extract_medial_axis_py(
    polygons: Vec<(Vec<CoordPair>, Vec<Vec<CoordPair>>)>,
    simplify_tolerance: f64,
) -> PyResult<Vec<(CoordPair, CoordPair)>> {
    temper_py_bridge::catch_unwind(|| {
        let polys: Vec<(Vec<Point>, Vec<Vec<Point>>)> = polygons
            .into_iter()
            .map(|(outer, holes)| (to_points(outer), holes.into_iter().map(to_points).collect()))
            .collect();
        let segments = extract_medial_axis(&polys, simplify_tolerance);
        segments_to_py(segments)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// Decode `n` interleaved little-endian `(x, y)` `f64` pairs.
///
/// Mirrors `radius_pairs_transform`'s bytes-in convention
/// (`numpy.ascontiguousarray(a, dtype=np.float64).tobytes()`), which exists
/// so a 41k-node coordinate array crosses the boundary as one buffer copy
/// instead of 41k tuple unpacks. That matters here: the caller passes the
/// full skeleton node set once per layer, six times per route.
#[cfg(feature = "python")]
fn points_from_le_bytes(bytes: &[u8], n: usize) -> Vec<Point> {
    let mut pts = Vec::with_capacity(n);
    for i in 0..n {
        let base = i * 16;
        let mut xb = [0u8; 8];
        let mut yb = [0u8; 8];
        xb.copy_from_slice(&bytes[base..base + 8]);
        yb.copy_from_slice(&bytes[base + 8..base + 16]);
        pts.push(Point::new(f64::from_le_bytes(xb), f64::from_le_bytes(yb)));
    }
    pts
}

/// pyo3 boundary for [`pad_anchor_plan`].
///
/// `pads_bytes` / `nodes_bytes` are `n_pads` / `n_nodes` interleaved
/// `(x, y)` `f64` pairs as raw little-endian bytes. Returns
/// `[(pad_index, node_index, dist), ...]` in pad order -- a plain list of
/// tuples rather than a byte buffer because the result is one entry per
/// ANCHORED pad (hundreds), not per candidate comparison (10^8), so the
/// per-item marshalling cost is irrelevant on this side and the caller
/// needs to index back into its own Python list of coordinate tuples
/// anyway (the graph is keyed by the ORIGINAL tuple objects).
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (pads_bytes, n_pads, nodes_bytes, n_nodes, dedup_tol, max_connect))]
pub fn pad_anchor_plan_py(
    pads_bytes: Vec<u8>,
    n_pads: usize,
    nodes_bytes: Vec<u8>,
    n_nodes: usize,
    dedup_tol: f64,
    max_connect: f64,
) -> PyResult<Vec<(usize, usize, f64)>> {
    // Checked, not `debug_assert`ed. The buffer and its count are independent
    // arguments, so a caller CAN pass a correct array with a stale count --
    // it is a real boundary condition, not a can't-happen. Left unchecked, a
    // short buffer indexes past the end of the slice and panics inside
    // `catch_unwind`, reaching Python as an opaque failure instead of as
    // "your count does not match your array".
    for (label, len, n) in [
        ("pads", pads_bytes.len(), n_pads),
        ("nodes", nodes_bytes.len(), n_nodes),
    ] {
        if len != n * 16 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "pad_anchor_plan_py: {label}_bytes is {len} bytes but \
                 n_{label} = {n} implies {} (two f64 per point)",
                n * 16
            )));
        }
    }

    temper_py_bridge::catch_unwind(|| {
        let pads = points_from_le_bytes(&pads_bytes, n_pads);
        let nodes = points_from_le_bytes(&nodes_bytes, n_nodes);
        pad_anchor_plan(&pads, &nodes, dedup_tol, max_connect)
            .into_iter()
            .map(|a| (a.pad_index, a.node_index, a.dist))
            .collect()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_medial_axis_single_py, m)?)?;
    m.add_function(wrap_pyfunction!(extract_medial_axis_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_anchor_plan_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn box_ring(minx: f64, miny: f64, maxx: f64, maxy: f64) -> Vec<Point> {
        vec![
            Point::new(minx, miny),
            Point::new(maxx, miny),
            Point::new(maxx, maxy),
            Point::new(minx, maxy),
            Point::new(minx, miny), // closed
        ]
    }

    #[cfg_attr(test, test)]
    fn simple_box_produces_a_nonempty_skeleton() {
        let outer = box_ring(0.0, 0.0, 20.0, 10.0);
        let segments = extract_medial_axis_single(&outer, &[], 0.5);
        assert!(!segments.is_empty());
        for (p1, p2) in &segments {
            assert!(
                p1.x != p2.x || p1.y != p2.y,
                "zero-length segment leaked through"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn degenerate_ring_falls_back_to_centroid_point() {
        // A ring with only 2 distinct vertices closed on itself samples
        // fewer than 3 boundary points.
        let outer = vec![Point::new(0.0, 0.0), Point::new(0.0, 0.0)];
        let segments = extract_medial_axis_single(&outer, &[], 0.5);
        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].0, segments[0].1);
    }

    #[cfg_attr(test, test)]
    fn multi_polygon_dispatch_concatenates() {
        let a = box_ring(0.0, 0.0, 10.0, 10.0);
        let b = box_ring(20.0, 20.0, 30.0, 30.0);
        let combined = extract_medial_axis(&[(a.clone(), vec![]), (b.clone(), vec![])], 0.5);
        let a_only = extract_medial_axis_single(&a, &[], 0.5);
        let b_only = extract_medial_axis_single(&b, &[], 0.5);
        assert_eq!(combined.len(), a_only.len() + b_only.len());
    }

    #[cfg_attr(test, test)]
    fn hole_is_excluded_from_the_skeleton_interior_filter() {
        let outer = box_ring(0.0, 0.0, 40.0, 30.0);
        let hole = box_ring(15.0, 10.0, 25.0, 20.0);
        let segments = extract_medial_axis_single(&outer, std::slice::from_ref(&hole), 0.5);
        assert!(!segments.is_empty());
        for (p1, p2) in &segments {
            let mid = p1.midpoint(p2);
            assert!(
                !point_in_polygon_winding(&mid, &hole),
                "skeleton segment midpoint fell inside the hole: {mid:?}"
            );
        }
    }

    // --- pad anchoring -----------------------------------------------

    fn pt(x: f64, y: f64) -> Point {
        Point::new(x, y)
    }

    /// The dedup predicate is a strict axis-aligned BOX, not a radius: a pad
    /// 0.09mm off in BOTH axes is 0.127mm away and still deduped, while a
    /// pad 0.11mm off in one axis alone is not. Getting this wrong would
    /// silently change which pads get anchor nodes at all.
    #[cfg_attr(test, test)]
    fn dedup_is_a_box_not_a_radius() {
        let nodes = vec![pt(0.0, 0.0)];
        // Diagonal 0.09/0.09 -> Euclidean 0.1273mm, still inside the box.
        assert!(pad_anchor_plan(&[pt(0.09, 0.09)], &nodes, 0.1, 50.0).is_empty());
        // 0.11 on one axis alone -> outside the box despite being closer in
        // one coordinate than the diagonal case above.
        assert_eq!(pad_anchor_plan(&[pt(0.11, 0.0)], &nodes, 0.1, 50.0).len(), 1);
        // Exactly on the boundary: `<` is strict, so 0.1 does NOT dedup.
        assert_eq!(pad_anchor_plan(&[pt(0.1, 0.0)], &nodes, 0.1, 50.0).len(), 1);
    }

    /// Ties resolve to the EARLIEST node, because the Python's comparison is
    /// a strict `<` against the running minimum. Two nodes equidistant from
    /// the pad must therefore always yield the lower index, whichever order
    /// a spatial index would have visited them in.
    #[cfg_attr(test, test)]
    fn ties_resolve_to_the_earliest_node() {
        let pad = pt(0.0, 0.0);
        let a = pt(3.0, 0.0);
        let b = pt(-3.0, 0.0);
        let forward = pad_anchor_plan(&[pad], &[a, b], 0.1, 50.0);
        assert_eq!(forward.len(), 1);
        assert_eq!(forward[0].node_index, 0);
        // Same geometry, reversed node order: the winner must follow the
        // ORDER, not the coordinates.
        let reversed = pad_anchor_plan(&[pad], &[b, a], 0.1, 50.0);
        assert_eq!(reversed[0].node_index, 0);
        assert_eq!(forward[0].dist, reversed[0].dist);
    }

    /// `max_connect` is a strict `<` too, and it drops the pad entirely
    /// rather than anchoring it to something far away.
    #[cfg_attr(test, test)]
    fn pads_beyond_max_connect_are_dropped() {
        let nodes = vec![pt(50.0, 0.0)];
        assert!(pad_anchor_plan(&[pt(0.0, 0.0)], &nodes, 0.1, 50.0).is_empty());
        assert_eq!(
            pad_anchor_plan(&[pt(0.000001, 0.0)], &nodes, 0.1, 50.0).len(),
            1
        );
    }

    /// The node snapshot is fixed for the whole pad sweep: a pad anchored
    /// early must not become a dedup target or a nearest-node candidate for
    /// a later pad. Two pads at the SAME position therefore both produce a
    /// record -- which is what makes the caller's `total_length` double-count
    /// them, faithfully to the Python.
    #[cfg_attr(test, test)]
    fn duplicate_pads_each_produce_their_own_record() {
        let nodes = vec![pt(5.0, 0.0)];
        let plan = pad_anchor_plan(&[pt(0.0, 0.0), pt(0.0, 0.0)], &nodes, 0.1, 50.0);
        assert_eq!(plan.len(), 2);
        assert_eq!(plan[0].pad_index, 0);
        assert_eq!(plan[1].pad_index, 1);
        assert_eq!(plan[0].dist, plan[1].dist);
    }

    /// Ranking must happen on the ROUNDED `sqrt` value, not on the squared
    /// sum. `sqrt` is monotonic but it rounds, so distinct sums can collapse
    /// onto one `f64` distance; ranking by the sum would then split a tie
    /// that the Python resolves by index order. This searches for a real
    /// collapsing pair and asserts the earliest index still wins.
    #[cfg_attr(test, test)]
    fn argmin_ranks_on_the_rounded_sqrt() {
        // Find two squared sums s_hi > s_lo whose sqrt rounds identically.
        let mut found = false;
        let mut s_lo = 0.0f64;
        let mut s_hi = 0.0f64;
        let mut base = 1.0f64;
        for _ in 0..64 {
            let up = f64::from_bits(base.to_bits() + 1);
            if base.sqrt() == up.sqrt() {
                s_lo = base;
                s_hi = up;
                found = true;
                break;
            }
            base = f64::from_bits(base.to_bits() + 1);
        }
        assert!(found, "no sqrt-collapsing adjacent pair found near 1.0");
        assert!(s_hi > s_lo);
        assert_eq!(s_lo.sqrt(), s_hi.sqrt());
        // Place the LARGER squared distance first. Ranking by the squared
        // sum would pick index 1; ranking by the rounded sqrt keeps index 0,
        // which is what the Python does.
        let pad = pt(0.0, 0.0);
        let nodes = vec![pt(s_hi.sqrt(), 0.0), pt(s_lo.sqrt(), 0.0)];
        let plan = pad_anchor_plan(&[pad], &nodes, 0.1, 50.0);
        assert_eq!(plan.len(), 1);
        assert_eq!(
            plan[0].node_index, 0,
            "argmin fell through to the squared sum and broke the tie the \
             wrong way"
        );
    }

    /// **`d * d` is NOT a valid substitute for `d ** 2`, and this test is the
    /// counterexample.**
    ///
    /// The tempting simplification in `pad_anchor_plan` is to write
    /// `dx * dx` instead of `host_math::pow(dx, 2.0)`, on the reasoning that
    /// `d * d` is the correctly rounded product and a correctly rounded
    /// `pow` must return the same bits. glibc's `pow` is *nearly* correctly
    /// rounded, and the reasoning fails: this search finds a disagreement
    /// within a few hundred thousand samples of ordinary board coordinates
    /// (millimetres in +/-200mm), and CPython reproduces it exactly, because
    /// CPython's `**` IS this same libm `pow`:
    ///
    /// ```text
    /// >>> d = 98.07985406973864
    /// >>> d ** 2
    /// 9619.657774341229          # 0x40C2C5426BEB74DD
    /// >>> d * d
    /// 9619.657774341227          # 0x40C2C5426BEB74DC
    /// ```
    ///
    /// One ulp. In an argmin over distances that is enough to flip a near
    /// tie and re-anchor a pad to a different skeleton node -- a different,
    /// still-"legal" answer that only bit-equality would ever reveal. Hence
    /// the kernel calls `host_math::pow`.
    ///
    /// The test asserts a counterexample EXISTS rather than pinning one
    /// specific value, so it keeps its meaning on a libm whose rounding
    /// differs from this host's. If some future libm really is correctly
    /// rounded and this test fails, the kernel is still correct -- only this
    /// justification would need rewriting.
    #[cfg_attr(test, test)]
    fn multiplication_is_not_a_valid_substitute_for_pow_at_board_scale() {
        // The pinned counterexample from this host, checked first so a
        // regression names a concrete value rather than "search found none".
        let known = 98.07985406973864_f64;
        assert_ne!(
            host_math::pow(known, 2.0).to_bits(),
            (known * known).to_bits(),
            "the pinned counterexample stopped disagreeing; re-derive it \
             before trusting `d * d` anywhere on this path"
        );

        // ...and an independent search over the coordinate domain, so the
        // claim does not rest on one pinned constant.
        let mut disagreements = 0usize;
        let mut state: u64 = 0x2026_0818_C0FF_EE01;
        for _ in 0..200_000 {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let unit = (state >> 11) as f64 / (1u64 << 53) as f64;
            let d = unit * 400.0 - 200.0;
            if host_math::pow(d, 2.0).to_bits() != (d * d).to_bits() {
                disagreements += 1;
            }
        }
        assert!(
            disagreements > 0,
            "no pow/multiply disagreement found in 200k board-scale samples"
        );
    }

    /// **`math.sqrt(s)` and `s ** 0.5` are DIFFERENT functions in CPython,
    /// and this file depends on both readings being kept straight.**
    ///
    /// IEEE-754 requires `sqrt` to be correctly rounded; it says no such
    /// thing about `pow`. So `math.sqrt` lowers to `f64::sqrt`, while
    /// `** 0.5` must lower to `host_math::pow(_, 0.5)` -- and they disagree
    /// on real board-scale values:
    ///
    /// ```text
    /// >>> s = 55489.646545994874
    /// >>> math.sqrt(s)
    /// 235.5624047805483          # what pad anchoring computes
    /// >>> s ** 0.5
    /// 235.56240478054826         # what boundary sampling computes
    /// ```
    ///
    /// Both spellings live in THIS module, reading from two different lines
    /// of the same Python file:
    ///
    /// * `sample_ring` transcribes `dist = (dx**2 + dy**2) ** 0.5` and so
    ///   correctly uses `host_math::pow(..., 0.5)`.
    /// * `pad_anchor_plan` transcribes
    ///   `math.sqrt((dx) ** 2 + (dy) ** 2)` and so correctly uses
    ///   `.sqrt()` -- while STILL routing the two squarings through
    ///   `host_math::pow`, because those are `**`.
    ///
    /// Swapping either one for the other is a silent last-ulp change. This
    /// test exists so that "just use sqrt everywhere, it is the same thing"
    /// has a standing counterexample.
    #[cfg_attr(test, test)]
    fn math_sqrt_and_pow_half_are_not_interchangeable() {
        let known = 55489.646545994874_f64;
        assert_ne!(
            known.sqrt().to_bits(),
            host_math::pow(known, 0.5).to_bits(),
            "the pinned sqrt/pow(_,0.5) counterexample stopped disagreeing; \
             re-derive it before treating the two spellings as one"
        );

        let mut disagreements = 0usize;
        let mut state: u64 = 0x5EED_2026_0818_0001;
        for _ in 0..200_000 {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let unit = (state >> 11) as f64 / (1u64 << 53) as f64;
            let s = unit * 160_000.0; // squared board-scale distances
            if s.sqrt().to_bits() != host_math::pow(s, 0.5).to_bits() {
                disagreements += 1;
            }
        }
        assert!(
            disagreements > 0,
            "no sqrt / pow(_, 0.5) disagreement found in 200k samples"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("channel_skeleton::tests::simple_box_produces_a_nonempty_skeleton", simple_box_produces_a_nonempty_skeleton),
        ("channel_skeleton::tests::degenerate_ring_falls_back_to_centroid_point", degenerate_ring_falls_back_to_centroid_point),
        ("channel_skeleton::tests::multi_polygon_dispatch_concatenates", multi_polygon_dispatch_concatenates),
        ("channel_skeleton::tests::hole_is_excluded_from_the_skeleton_interior_filter", hole_is_excluded_from_the_skeleton_interior_filter),
        ("channel_skeleton::tests::dedup_is_a_box_not_a_radius", dedup_is_a_box_not_a_radius),
        ("channel_skeleton::tests::ties_resolve_to_the_earliest_node", ties_resolve_to_the_earliest_node),
        ("channel_skeleton::tests::pads_beyond_max_connect_are_dropped", pads_beyond_max_connect_are_dropped),
        ("channel_skeleton::tests::duplicate_pads_each_produce_their_own_record", duplicate_pads_each_produce_their_own_record),
        ("channel_skeleton::tests::argmin_ranks_on_the_rounded_sqrt", argmin_ranks_on_the_rounded_sqrt),
        ("channel_skeleton::tests::multiplication_is_not_a_valid_substitute_for_pow_at_board_scale", multiplication_is_not_a_valid_substitute_for_pow_at_board_scale),
        ("channel_skeleton::tests::math_sqrt_and_pow_half_are_not_interchangeable", math_sqrt_and_pow_half_are_not_interchangeable),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

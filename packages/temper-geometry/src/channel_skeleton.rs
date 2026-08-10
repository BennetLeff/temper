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
// `@register_validator` wiring, plus the pad-anchoring dict/list
// bookkeeping in `extract_channel_skeleton`).
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

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(extract_medial_axis_single_py, m)?)?;
    m.add_function(wrap_pyfunction!(extract_medial_axis_py, m)?)?;
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
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

//! Wave 4: zone/pour emission geometry, ported from
//! `router_v6/zone_emission.py` and `router_v6/_zone_pour_stitch.py`.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_zone_pour_geometry_py_oracle.py`
//! -- a verbatim `git show` extraction at
//! `a920657f2d4fa2f56b24d71f3ae558dd244dc0fc`.
//!
//! Scope
//! -----
//! Three kernels move here:
//!
//! * [`emit_zone_s_expr_py`] -- pure string formatting, `ZoneDefinition` ->
//!   the KiCad `(zone ...)` s-expression.
//! * [`chamfer_path_points_py`] -- 90-degree-turn chamfering, pure f64
//!   arithmetic, no external library.
//! * [`stitch_targets_py`] -- the geometric core of `_stitch_isolated_pads`:
//!   for each pad position, is it outside every pour polygon for its net
//!   (`shapely.Polygon.contains`/`.touches`), and if so, what is the nearest
//!   pour-boundary vertex (`scipy.spatial.cKDTree.query`)? Reuses
//!   [`crate::polygon::point_in_polygon_winding`] (already shipped, already
//!   wired elsewhere) for the containment half rather than re-deriving a
//!   second point-in-polygon predicate.
//!
//! What does NOT move here (JUSTIFIED-KEEP, see
//! `packages/temper-geometry/VERIFICATION.md` "Zone Pour Emission Geometry")
//! --------------------------------------------------------------------------
//! * `_cluster_positions` -- scipy `linkage`/`fcluster` (Ward hierarchical
//!   clustering). A scipy library boundary in the same class as KTD8/KTD9:
//!   the NN-chain / Lance-Williams recurrence is not a closed form to
//!   transcribe, it is a specific numerical algorithm to reimplement and
//!   independently validate bit-exact, which was judged out of scope for
//!   this slice.
//! * `_convex_hull_from_positions`'s `shapely.buffer(margin, join_style=2)`
//!   step -- GEOS mitre-join polygon offsetting. Measured: an analytic
//!   mitre-offset reimplementation agrees with GEOS to ~1e-13 (float noise,
//!   NOT bit-exact) on convex hulls, and diverges in vertex COUNT on ~10% of
//!   randomly generated hulls (mitre-limit beveling, GEOS's exact rule
//!   unconfirmed). Same divergence class as `drc_inflate.rs`'s recorded
//!   `buffer(r, resolution=16)` JUSTIFIED-KEEP (round join instead of mitre,
//!   same GEOS boundary).
//! * `_zone_layers_for_net` / `_zone_params_for_net` -- netclass-SSOT
//!   (`TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES`) lookups. Data-driven
//!   business logic, not geometry; out of this migration's scope by
//!   definition.
//!
//! Known divergence class: nearest-neighbour tie-break
//! -----------------------------------------------------
//! [`stitch_targets_py`] resolves ties (multiple pour-boundary vertices at
//! **exactly** equal distance from a pad) by keeping the first vertex found
//! in iteration order (`d < best`, strict). Measured: `scipy.spatial.
//! cKDTree.query` does NOT always agree -- of 2000 randomized tie-forced
//! queries (coordinates rounded to 1 decimal specifically to manufacture
//! ties), cKDTree returned a different tied index in 2 cases, because its
//! answer depends on the tree's internal space-partitioning traversal order,
//! not on input array order. Reproducing that traversal bit-for-bit would
//! mean re-deriving scipy's ckdtree splitting rule, which is out of scope
//! here. This is UNREACHABLE in practice for real board coordinates -- it
//! requires an exact float64 distance tie between two distinct pour-boundary
//! vertices, a measure-zero event for placement/routing-derived positions --
//! and is recorded, not hidden: see `test_tie_break_diverges_from_cKDTree` in
//! the differential suite (a known, non-blocking divergence, not a bug).

use crate::polygon::point_in_polygon_winding;
use crate::types::Point;
use pyo3::prelude::*;
use temper_py_bridge;

// ===========================================================================
// emit_zone_s_expr
// ===========================================================================

/// Render a zone definition as a KiCad `(zone ...)` s-expression.
///
/// Mirrors `zone_emission.py::emit_zone_s_expr` exactly, including its
/// `.4f`-formatted floats (Rust's `{:.4}` and Python's `f"{x:.4f}"` are both
/// correctly-rounded decimal conversions of the same f64 bit pattern, so
/// they agree digit for digit).
pub fn emit_zone_s_expr(
    net_number: i64,
    net_name: &str,
    layer: &str,
    points: &[(f64, f64)],
    clearance: f64,
    priority: i64,
    min_thickness: f64,
) -> String {
    let poly = points
        .iter()
        .map(|(x, y)| format!("(xy {x:.4} {y:.4})"))
        .collect::<Vec<_>>()
        .join(" ");
    format!(
        "  (zone (net {net_number}) (net_name \"{net_name}\") (layer \"{layer}\") \
         (hatch full 0.5) (priority {priority}) \
         (connect_pads yes (clearance {clearance:.4})) \
         (min_thickness {min_thickness:.4}) \
         (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)) \
         (polygon (pts {poly})))"
    )
}

#[pyfunction]
#[pyo3(signature = (net_number, net_name, layer, points, clearance, priority, min_thickness))]
pub fn emit_zone_s_expr_py(
    net_number: i64,
    net_name: String,
    layer: String,
    points: Vec<(f64, f64)>,
    clearance: f64,
    priority: i64,
    min_thickness: f64,
) -> PyResult<String> {
    temper_py_bridge::catch_unwind(|| {
        emit_zone_s_expr(
            net_number,
            &net_name,
            &layer,
            &points,
            clearance,
            priority,
            min_thickness,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// ===========================================================================
// chamfer_path_points
// ===========================================================================

/// A path point: `(x, y, layer)`.
pub type PathPoint = (f64, f64, String);

/// Chamfer 90-degree orthogonal turns to reduce grid-staircasing DRC
/// violations. Mirrors `_zone_pour_stitch.py::_chamfer_path_points` exactly
/// -- same op order, same `1e-12` thresholds, same `2.0 * chamfer_offset`
/// skip guard.
pub fn chamfer_path_points(path_points: &[PathPoint], chamfer_offset: f64) -> Vec<PathPoint> {
    if path_points.len() <= 2 {
        return path_points.to_vec();
    }

    let mut result: Vec<PathPoint> = Vec::with_capacity(path_points.len());
    result.push(path_points[0].clone());

    for triple in path_points.windows(3) {
        let prev = &triple[0];
        let curr = &triple[1];
        let nxt = &triple[2];

        if prev.2 != curr.2 || curr.2 != nxt.2 {
            result.push(curr.clone());
            continue;
        }

        let lyr = &curr.2;
        let dx1 = curr.0 - prev.0;
        let dy1 = curr.1 - prev.1;
        let dx2 = nxt.0 - curr.0;
        let dy2 = nxt.1 - curr.1;

        let h1 = dy1.abs() < 1e-12 && dx1.abs() > 1e-12;
        let v1 = dx1.abs() < 1e-12 && dy1.abs() > 1e-12;
        let h2 = dy2.abs() < 1e-12 && dx2.abs() > 1e-12;
        let v2 = dx2.abs() < 1e-12 && dy2.abs() > 1e-12;

        let is_orthogonal = (h1 && v2) || (v1 && h2);
        if !is_orthogonal {
            result.push(curr.clone());
            continue;
        }

        let seg1_len = (dx1 * dx1 + dy1 * dy1).sqrt();
        let seg2_len = (dx2 * dx2 + dy2 * dy2).sqrt();
        if seg1_len < 2.0 * chamfer_offset || seg2_len < 2.0 * chamfer_offset {
            result.push(curr.clone());
            continue;
        }

        let ux1 = dx1 / seg1_len;
        let uy1 = dy1 / seg1_len;
        let ux2 = dx2 / seg2_len;
        let uy2 = dy2 / seg2_len;

        let before = (
            curr.0 - ux1 * chamfer_offset,
            curr.1 - uy1 * chamfer_offset,
            lyr.clone(),
        );
        let after = (
            curr.0 + ux2 * chamfer_offset,
            curr.1 + uy2 * chamfer_offset,
            lyr.clone(),
        );

        result.push(before);
        result.push(after);
    }

    result.push(path_points[path_points.len() - 1].clone());
    result
}

#[pyfunction]
#[pyo3(signature = (path_points, chamfer_offset=0.1))]
pub fn chamfer_path_points_py(
    path_points: Vec<PathPoint>,
    chamfer_offset: f64,
) -> PyResult<Vec<PathPoint>> {
    temper_py_bridge::catch_unwind(|| chamfer_path_points(&path_points, chamfer_offset))
        .map_err(temper_py_bridge::panic_to_err)
}

// ===========================================================================
// stitch_targets — the geometric core of _stitch_isolated_pads
// ===========================================================================

/// For each of `positions`, decide whether it lies outside every polygon in
/// `polygons` (mirroring `poly.contains(pt) or poly.touches(pt)` for
/// `any(...)` over all polygons), and if so, find the nearest vertex among
/// ALL polygons' vertices combined (mirroring a single `scipy.spatial.
/// cKDTree` built over every pour polygon's exterior coords).
///
/// Polygons with fewer than 3 points are dropped first, exactly like the
/// oracle's `if len(pts) >= 3: pour_polys.append(...)`. If that leaves no
/// valid polygon, returns an empty result (mirrors the oracle's `if not
/// pour_polys: continue` -- no polygon means nothing to be "outside" of, so
/// no stitch targets are produced for this net).
///
/// Returns `(px, py, nearest_x, nearest_y)` tuples, one per outside pad, in
/// `positions` order -- pads that are inside (or touching) some polygon are
/// dropped, exactly like the oracle's `outside` list.
///
/// Tie-break note: see the module doc comment. Distance ties are broken by
/// "first strictly-smaller distance wins" over the flattened vertex list in
/// `polygons` order, which is NOT guaranteed to match `cKDTree`'s internal
/// traversal order on an exact tie (measured divergence, ~0.1% of forced-tie
/// queries; unreachable for realistic non-tied board coordinates).
pub fn stitch_targets(
    positions: &[(f64, f64)],
    polygons: &[Vec<(f64, f64)>],
) -> Vec<(f64, f64, f64, f64)> {
    let valid_polygons: Vec<&Vec<(f64, f64)>> = polygons.iter().filter(|p| p.len() >= 3).collect();
    if valid_polygons.is_empty() {
        return Vec::new();
    }

    let poly_points: Vec<Vec<Point>> = valid_polygons
        .iter()
        .map(|pts| pts.iter().map(|&(x, y)| Point::new(x, y)).collect())
        .collect();

    let all_verts: Vec<(f64, f64)> = valid_polygons
        .iter()
        .flat_map(|pts| pts.iter().copied())
        .collect();
    if all_verts.is_empty() {
        return Vec::new();
    }

    let mut out = Vec::new();
    for &(px, py) in positions {
        let p = Point::new(px, py);
        let inside_any = poly_points
            .iter()
            .any(|verts| point_in_polygon_winding(&p, verts));
        if inside_any {
            continue;
        }

        // Nearest vertex over the flattened vertex list, first-strictly-
        // smaller-wins tie-break (see module doc comment).
        let mut best_d = f64::INFINITY;
        let mut best = (0.0, 0.0);
        for &(vx, vy) in &all_verts {
            let dx = vx - px;
            let dy = vy - py;
            let d = (dx * dx + dy * dy).sqrt();
            if d < best_d {
                best_d = d;
                best = (vx, vy);
            }
        }
        out.push((px, py, best.0, best.1));
    }
    out
}

#[pyfunction]
#[pyo3(signature = (positions, polygons))]
pub fn stitch_targets_py(
    positions: Vec<(f64, f64)>,
    polygons: Vec<Vec<(f64, f64)>>,
) -> PyResult<Vec<(f64, f64, f64, f64)>> {
    temper_py_bridge::catch_unwind(|| stitch_targets(&positions, &polygons))
        .map_err(temper_py_bridge::panic_to_err)
}

// ===========================================================================
// Registration
// ===========================================================================

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(emit_zone_s_expr_py, m)?)?;
    m.add_function(wrap_pyfunction!(chamfer_path_points_py, m)?)?;
    m.add_function(wrap_pyfunction!(stitch_targets_py, m)?)?;
    Ok(())
}

// ===========================================================================
// Unit tests (pure-Rust, no libpython)
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_emit_zone_s_expr_basic() {
        let s = emit_zone_s_expr(5, "+3V3", "F.Cu", &[(0.0, 0.0), (5.0, 0.0), (0.0, 5.0)], 0.3, 0, 0.25);
        assert!(s.contains("(zone "));
        assert!(s.contains("(net_name \"+3V3\")"));
        assert!(s.contains("(net 5)"));
        assert!(s.contains("(layer \"F.Cu\")"));
        assert!(s.contains("(polygon "));
        assert!(s.contains("(fill yes"));
    }

    #[test]
    fn test_chamfer_orthogonal_turn() {
        let points: Vec<PathPoint> = vec![
            (0.0, 0.0, "F.Cu".to_string()),
            (1.0, 0.0, "F.Cu".to_string()),
            (1.0, 1.0, "F.Cu".to_string()),
        ];
        let result = chamfer_path_points(&points, 0.1);
        assert_eq!(result.len(), 4);
        assert_eq!(result[0], points[0]);
        assert_eq!(result[3], points[2]);
    }

    #[test]
    fn test_chamfer_straight_line_unchanged() {
        let points: Vec<PathPoint> = vec![
            (0.0, 0.0, "F.Cu".to_string()),
            (1.0, 0.0, "F.Cu".to_string()),
            (2.0, 0.0, "F.Cu".to_string()),
        ];
        let result = chamfer_path_points(&points, 0.1);
        assert_eq!(result, points);
    }

    #[test]
    fn test_chamfer_layer_change_preserved() {
        let points: Vec<PathPoint> = vec![
            (0.0, 0.0, "F.Cu".to_string()),
            (1.0, 0.0, "B.Cu".to_string()),
            (1.0, 1.0, "B.Cu".to_string()),
        ];
        let result = chamfer_path_points(&points, 0.1);
        assert_eq!(result, points);
    }

    #[test]
    fn test_chamfer_short_segment_skipped() {
        let points: Vec<PathPoint> = vec![
            (0.0, 0.0, "F.Cu".to_string()),
            (0.05, 0.0, "F.Cu".to_string()),
            (0.05, 1.0, "F.Cu".to_string()),
        ];
        let result = chamfer_path_points(&points, 0.1);
        assert_eq!(result, points);
    }

    #[test]
    fn test_chamfer_empty_and_short_paths() {
        let empty: Vec<PathPoint> = vec![];
        assert_eq!(chamfer_path_points(&empty, 0.1), empty);
        let one: Vec<PathPoint> = vec![(1.0, 2.0, "F.Cu".to_string())];
        assert_eq!(chamfer_path_points(&one, 0.1), one);
        let two: Vec<PathPoint> = vec![
            (1.0, 2.0, "F.Cu".to_string()),
            (3.0, 4.0, "F.Cu".to_string()),
        ];
        assert_eq!(chamfer_path_points(&two, 0.1), two);
    }

    #[test]
    fn test_stitch_pad_inside_polygon_not_stitched() {
        let positions = vec![(5.0, 5.0)];
        let polygons = vec![vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]];
        let result = stitch_targets(&positions, &polygons);
        assert!(result.is_empty());
    }

    #[test]
    fn test_stitch_pad_outside_polygon_gets_target() {
        let positions = vec![(5.0, 5.0), (50.0, 50.0)];
        let polygons = vec![vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]];
        let result = stitch_targets(&positions, &polygons);
        assert_eq!(result.len(), 1);
        assert_eq!((result[0].0, result[0].1), (50.0, 50.0));
    }

    #[test]
    fn test_stitch_no_valid_polygons_returns_empty() {
        let positions = vec![(50.0, 50.0)];
        let polygons = vec![vec![(0.0, 0.0), (1.0, 1.0)]]; // < 3 points
        let result = stitch_targets(&positions, &polygons);
        assert!(result.is_empty());
    }

    #[test]
    fn test_stitch_empty_polygons_returns_empty() {
        let positions = vec![(50.0, 50.0)];
        let polygons: Vec<Vec<(f64, f64)>> = vec![];
        let result = stitch_targets(&positions, &polygons);
        assert!(result.is_empty());
    }
}

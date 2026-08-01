// =============================================================================
// PyO3 bridge for temper-geometry — exposes all geometry functions to Python
// =============================================================================

#![allow(clippy::too_many_arguments)]
// PyO3 bridge functions mirror Python function signatures 1:1.

use pyo3::prelude::*;
use crate::bottleneck_geometry::{build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py};
use crate::audit::{bbox_from_center_py, chebyshev_gap_py};
use crate::channel_widths::edt_width_lookup_batch;
use crate::copper_coverage::rasterise_polygon_mask;
use crate::corridor::extract_corridor_mask;
use crate::grid_raster::{
    block_circle_into_grid_py, block_rect_into_grid_py, block_segment_into_grid_py,
    clear_circle_from_grid_py, closest_component_for_zone_py, effective_creepage_py,
    fence_samples_py, occupancy_bitmap_row_py,
};
use crate::creepage_check::{
    calculate_required_creepage_py, closest_point_on_segment_py, is_high_voltage_net_py,
    min_clearance_distance_py, point_to_segment_distance_py, segment_to_segment_info_py,
    segments_intersect_py,
};
use crate::{barrier_axis_gap_py, best_rotation_for_barrier_py, pad_axis_radius_py, pad_bounding_radius_py, pad_corner_radius_py, pad_core_half_extents_py, pad_support_radius_py, spice_infer_unit_py, spice_loop_inductance_py};
use crate::clearance_geometry::{
    component_reach_py, copper_scan_py, origin_distance_py, pad_pair_distance_py,
    rotate_local_to_world_py,
};




use crate::types::*;

// ---------------------------------------------------------------------------
// Conversion helpers
// ---------------------------------------------------------------------------

fn vec_to_points(v: &[f64]) -> Vec<Point> {
    v.chunks(2)
        .map(|c| Point::new(c[0], c[1]))
        .collect()
}

fn points_to_vec(pts: &[Point]) -> Vec<f64> {
    let mut out = Vec::with_capacity(pts.len() * 2);
    for p in pts {
        out.push(p.x);
        out.push(p.y);
    }
    out
}

fn vec_to_rects(v: &[f64]) -> Vec<Rect> {
    v.chunks(4)
        .map(|c| Rect::new(c[0], c[1], c[2], c[3]))
        .collect()
}

fn vec_to_aabbs(v: &[f64]) -> Vec<AABB> {
    v.chunks(4)
        .map(|c| AABB::new(c[0], c[1], c[2], c[3]))
        .collect()
}

fn aabb_to_tuple(bb: &AABB) -> (f64, f64, f64, f64) {
    (bb.x_min, bb.y_min, bb.x_max, bb.y_max)
}

// =============================================================================
// primitives module
// =============================================================================

#[pyfunction]
fn point_distance(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::primitives::point_distance(&Point::new(x1, y1), &Point::new(x2, y2))
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_distance_squared(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::primitives::point_distance_squared(&Point::new(x1, y1), &Point::new(x2, y2))
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_midpoint(x1: f64, y1: f64, x2: f64, y2: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let m = crate::primitives::point_midpoint(&Point::new(x1, y1), &Point::new(x2, y2));
        (m.x, m.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn points_centroid(points: Vec<f64>) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        let c = crate::primitives::points_centroid(&pts);
        (c.x, c.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_to_line_distance(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::primitives::point_to_line_distance(
            &Point::new(px, py),
            &Point::new(ax, ay),
            &Point::new(bx, by),
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn rect_from_center(cx: f64, cy: f64, half_w: f64, half_h: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = crate::primitives::rect_from_center(cx, cy, half_w, half_h);
        (r.x, r.y, r.w, r.h)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn rect_center(rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        let c = crate::primitives::rect_center(&r);
        (c.x, c.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn rect_dimensions(rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        Ok(crate::primitives::rect_dimensions(&r))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn rect_area(rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::primitives::rect_area(&r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn rect_contains_point(rx: f64, ry: f64, rw: f64, rh: f64, px: f64, py: f64) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::primitives::rect_contains_point(&r, &Point::new(px, py))
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn rect_corners(rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        let corners = crate::primitives::rect_corners(&r);
        Ok(points_to_vec(&corners))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn aabb_from_points(points: Vec<f64>) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        let bb = crate::primitives::aabb_from_points(&pts);
        Ok(aabb_to_tuple(&bb))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn aabb_intersects(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        crate::primitives::aabb_intersects(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn aabb_overlap_area(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        crate::primitives::aabb_overlap_area(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn aabb_union(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        let u = crate::primitives::aabb_union(&a, &b);
        Ok(aabb_to_tuple(&u))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn aabb_expand(x1: f64, y1: f64, x2: f64, y2: f64, margin: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(x1, y1, x2, y2);
        let e = crate::primitives::aabb_expand(&a, margin);
        Ok(aabb_to_tuple(&e))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn distance_to_rect_edge(px: f64, py: f64, rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::primitives::distance_to_rect_edge(&Point::new(px, py), &r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn distance_to_specific_edge(px: f64, py: f64, rx: f64, ry: f64, rw: f64, rh: f64, side: &str) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::primitives::distance_to_specific_edge(&Point::new(px, py), &r, side)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn distance_to_board_boundary(px: f64, py: f64, board_w: f64, board_h: f64, margin: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::primitives::distance_to_board_boundary(&Point::new(px, py), board_w, board_h, margin)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn pairwise_distances(points: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        Ok(crate::primitives::pairwise_distances(&pts))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn pairwise_distances_squared(points: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        Ok(crate::primitives::pairwise_distances_squared(&pts))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn batch_point_distance(points_a: Vec<f64>, points_b: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let a = vec_to_points(&points_a);
        let b = vec_to_points(&points_b);
        Ok(crate::primitives::batch_point_distance(&a, &b))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// =============================================================================
// polygon module
// =============================================================================

#[pyfunction]
fn polygon_signed_area(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::polygon_signed_area(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn polygon_area(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::polygon_area(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn triangle_area(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::polygon::triangle_area(
            &Point::new(ax, ay),
            &Point::new(bx, by),
            &Point::new(cx, cy),
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn polygon_centroid(vertices: Vec<f64>) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let c = crate::polygon::polygon_centroid(&pts);
        (c.x, c.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn points_centroid_winding(vertices: Vec<f64>) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let c = crate::polygon::points_centroid_winding(&pts);
        (c.x, c.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_in_polygon_winding(px: f64, py: f64, vertices: Vec<f64>) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::point_in_polygon_winding(&Point::new(px, py), &pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_in_polygon_soft(px: f64, py: f64, vertices: Vec<f64>, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::point_in_polygon_soft(&Point::new(px, py), &pts, alpha)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_in_rect(px: f64, py: f64, rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::polygon::point_in_rect(&Point::new(px, py), &r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_in_rect_soft(px: f64, py: f64, rx: f64, ry: f64, rw: f64, rh: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        crate::polygon::point_in_rect_soft(&Point::new(px, py), &r, alpha)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn polygon_perimeter(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::polygon_perimeter(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn compute_loop_area(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::compute_loop_area(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn compute_loop_perimeter(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::compute_loop_perimeter(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn loop_area_penalty(vertices: Vec<f64>, max_area_mm2: f64, weight: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::loop_area_penalty(&pts, max_area_mm2, weight)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn polygon_bounding_box(vertices: Vec<f64>) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let bb = crate::polygon::polygon_bounding_box(&pts);
        Ok(aabb_to_tuple(&bb))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn polygon_bounding_circle(vertices: Vec<f64>) -> PyResult<(f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let (center, radius) = crate::polygon::polygon_bounding_circle(&pts);
        (center.x, center.y, radius)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn is_convex(vertices: Vec<f64>) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::is_convex(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn polygon_orientation(vertices: Vec<f64>) -> PyResult<i32> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::polygon_orientation(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn nearest_point_on_segment(
    px: f64, py: f64,
    sx1: f64, sy1: f64, sx2: f64, sy2: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let seg = Segment::new(Point::new(sx1, sy1), Point::new(sx2, sy2));
        let np = crate::polygon::nearest_point_on_segment(&Point::new(px, py), &seg);
        (np.x, np.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn nearest_point_on_polygon(px: f64, py: f64, vertices: Vec<f64>) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let np = crate::polygon::nearest_point_on_polygon(&Point::new(px, py), &pts);
        (np.x, np.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn translate_polygon(vertices: Vec<f64>, dx: f64, dy: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let result = crate::polygon::translate_polygon(&pts, dx, dy);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn scale_polygon(vertices: Vec<f64>, sx: f64, sy: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let result = crate::polygon::scale_polygon(&pts, sx, sy);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn rotate_polygon(vertices: Vec<f64>, angle_rad: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let result = crate::polygon::rotate_polygon(&pts, angle_rad);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// =============================================================================
// sdf module
// =============================================================================

#[pyfunction]
fn sdf_circle(px: f64, py: f64, cx: f64, cy: f64, r: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_circle(&Point::new(px, py), cx, cy, r))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_rectangle(px: f64, py: f64, cx: f64, cy: f64, half_w: f64, half_h: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_rectangle(&Point::new(px, py), cx, cy, half_w, half_h))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_box_2d(px: f64, py: f64, center_x: f64, center_y: f64, half_x: f64, half_y: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let center = Point::new(center_x, center_y);
        let half_size = Point::new(half_x, half_y);
        crate::sdf::sdf_box_2d(&Point::new(px, py), &center, &half_size)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_rounded_rectangle(
    px: f64, py: f64, cx: f64, cy: f64, half_w: f64, half_h: f64, r: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::sdf::sdf_rounded_rectangle(&Point::new(px, py), cx, cy, half_w, half_h, r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_capsule(
    px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64, r: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::sdf::sdf_capsule(
            &Point::new(px, py),
            &Point::new(ax, ay),
            &Point::new(bx, by),
            r,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_polygon(px: f64, py: f64, vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::sdf::sdf_polygon(&Point::new(px, py), &pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_convex_polygon(px: f64, py: f64, vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::sdf::sdf_convex_polygon(&Point::new(px, py), &pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_union(d1: f64, d2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_union(d1, d2)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_intersection(d1: f64, d2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_intersection(d1, d2)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_subtraction(d1: f64, d2: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_subtraction(d1, d2)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_smooth_union(d1: f64, d2: f64, k: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_smooth_union(d1, d2, k)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_smooth_intersection(d1: f64, d2: f64, k: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_smooth_intersection(d1, d2, k)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_offset(d: f64, offset: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_offset(d, offset)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_round(d: f64, r: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_round(d, r)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_shell(d: f64, thickness: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_shell(d, thickness)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sdf_to_mask(distances: Vec<f64>, threshold: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::sdf::sdf_to_mask(&distances, threshold)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn sdf_to_penalty(distances: Vec<f64>, alpha: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::sdf::sdf_to_penalty(&distances, alpha)))
        .map_err(temper_py_bridge::panic_to_err)?
}

// NOTE: sdf_gradient is intentionally not wrapped because it takes a Rust
// function pointer (fn(&Point) -> f64) as an argument, which cannot be
// passed from Python.

// =============================================================================
// smooth module
// =============================================================================

#[pyfunction]
fn smooth_max(a: f64, b: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_max(a, b, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_max_axis(arr: Vec<f64>, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_max_axis(&arr, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_max_pair(a: Vec<f64>, b: Vec<f64>, alpha: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::smooth::smooth_max_pair(&a, &b, alpha)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn smooth_min(a: f64, b: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_min(a, b, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_min_axis(arr: Vec<f64>, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_min_axis(&arr, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_min_pair(a: Vec<f64>, b: Vec<f64>, alpha: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::smooth::smooth_min_pair(&a, &b, alpha)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn smooth_relu(x: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_relu(x, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_relu_penalty(x: f64, margin: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_relu_penalty(x, margin, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_leaky_relu(x: f64, alpha: f64, negative_slope: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_leaky_relu(x, alpha, negative_slope)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_abs(x: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_abs(x, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_clip(x: f64, min_val: f64, max_val: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_clip(x, min_val, max_val, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn smooth_step(x: f64, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_step(x, alpha)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn hpwl_smooth(points: Vec<f64>, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        // Convert flat Vec<f64> of x,y pairs to Vec<(f64, f64)>
        let pairs: Vec<(f64, f64)> = points.chunks(2).map(|c| (c[0], c[1])).collect();
        crate::smooth::hpwl_smooth(&pairs, alpha)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn weighted_average_smooth(values: Vec<f64>, weights: Vec<f64>, alpha: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::weighted_average_smooth(&values, &weights, alpha))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn get_alpha_schedule(start_alpha: f64, end_alpha: f64, epochs: usize) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::smooth::get_alpha_schedule(start_alpha, end_alpha, epochs)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn get_beta_schedule(start_beta: f64, end_beta: f64, epochs: usize) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::smooth::get_beta_schedule(start_beta, end_beta, epochs)))
        .map_err(temper_py_bridge::panic_to_err)?
}

// =============================================================================
// transform module
// =============================================================================

#[pyfunction]
fn get_rotation_matrix(angle_rad: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let m = crate::transform::get_rotation_matrix(angle_rad);
        (m[0][0], m[0][1], m[1][0], m[1][1])
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (x, y, angle_rad, center_x=0.0, center_y=0.0))]
fn rotate_point(x: f64, y: f64, angle_rad: f64, center_x: f64, center_y: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let center = Point::new(center_x, center_y);
        let r = crate::transform::rotate_point(&Point::new(x, y), angle_rad, Some(&center));
        (r.x, r.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (points, angle_rad, center_x=0.0, center_y=0.0))]
fn rotate_points(points: Vec<f64>, angle_rad: f64, center_x: f64, center_y: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        let center = Point::new(center_x, center_y);
        let result = crate::transform::rotate_points(&pts, angle_rad, Some(&center));
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn get_rotated_bounds(rx: f64, ry: f64, rw: f64, rh: f64, angle_rad: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        let bb = crate::transform::get_rotated_bounds(&r, angle_rad);
        Ok(aabb_to_tuple(&bb))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn rotate_rectangle_corners(
    rx: f64, ry: f64, rw: f64, rh: f64, angle_rad: f64, center_x: f64, center_y: f64,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        let center = Point::new(center_x, center_y);
        let corners = crate::transform::rotate_rectangle_corners(&r, angle_rad, &center);
        Ok(points_to_vec(&corners))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn get_rotated_aabb(vertices: Vec<f64>) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        let bb = crate::transform::get_rotated_aabb(&pts);
        Ok(aabb_to_tuple(&bb))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn transform_pin_position(
    pin_x: f64, pin_y: f64, comp_x: f64, comp_y: f64, rotation_rad: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let result = crate::transform::transform_pin_position(
            &Point::new(pin_x, pin_y),
            &Point::new(comp_x, comp_y),
            rotation_rad,
        );
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn transform_pin_positions(
    pin_positions: Vec<f64>, comp_x: f64, comp_y: f64, rotation_rad: f64,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pins = vec_to_points(&pin_positions);
        let comp = Point::new(comp_x, comp_y);
        let result = crate::transform::transform_pin_positions(&pins, &comp, rotation_rad);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn batch_get_rotated_bounds(rects: Vec<f64>, angles: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        let results = crate::transform::batch_get_rotated_bounds(&r, &angles);
        let mut out = Vec::with_capacity(results.len() * 4);
        for bb in &results {
            out.push(bb.x_min);
            out.push(bb.y_min);
            out.push(bb.x_max);
            out.push(bb.y_max);
        }
        Ok(out)
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn batch_rotate_points(points: Vec<f64>, angles: Vec<f64>, centers: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&points);
        let ctrs = vec_to_points(&centers);
        let result = crate::transform::batch_rotate_points(&pts, &angles, &ctrs);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn rotation_index_to_onehot(idx: usize, n_angles: usize) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::transform::rotation_index_to_onehot(idx, n_angles)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn rotation_degrees_to_onehot(deg: f64, allowed: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::transform::rotation_degrees_to_onehot(deg, &allowed)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn onehot_to_rotation_degrees(onehot: Vec<f64>, allowed: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::transform::onehot_to_rotation_degrees(&onehot, &allowed))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn onehot_to_rotation_radians(onehot: Vec<f64>, allowed_rad: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::transform::onehot_to_rotation_radians(&onehot, &allowed_rad))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn gumbel_softmax(logits: Vec<f64>, temperature: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| Ok(crate::transform::gumbel_softmax(&logits, temperature)))
        .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn sample_rotation(logits: Vec<f64>) -> PyResult<usize> {
    temper_py_bridge::catch_unwind(|| crate::transform::sample_rotation(&logits)).map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn sample_rotation_batch(logits: Vec<Vec<f64>>) -> PyResult<Vec<usize>> {
    temper_py_bridge::catch_unwind(|| {
        crate::transform::sample_rotation_batch(&logits)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// =============================================================================
// overlap module
// =============================================================================

#[pyfunction]
fn box_box_distance(
    ax: f64, ay: f64, aw: f64, ah: f64,
    bx: f64, by: f64, bw: f64, bh: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = Rect::new(ax, ay, aw, ah);
        let b = Rect::new(bx, by, bw, bh);
        crate::overlap::box_box_distance(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn box_box_distance_aabb(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        crate::overlap::box_box_distance_aabb(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn component_overlap_amount(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        crate::overlap::component_overlap_amount(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn overlap_area_estimate(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        crate::overlap::overlap_area_estimate(&a, &b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn compute_pairwise_distances(rects: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        Ok(crate::overlap::compute_pairwise_distances(&r))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn compute_total_overlap(rects: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        crate::overlap::compute_total_overlap(&r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn compute_overlap_penalty(rects: Vec<f64>, weight: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        crate::overlap::compute_overlap_penalty(&r, weight)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn check_clearance_violation(rects: Vec<f64>, clearance_mm: f64) -> PyResult<Vec<(usize, usize, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        Ok(crate::overlap::check_clearance_violation(&r, clearance_mm))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn compute_clearance_penalties(rects: Vec<f64>, clearances: Vec<(usize, usize, f64)>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        Ok(crate::overlap::compute_clearance_penalties(&r, &clearances))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn count_overlaps(rects: Vec<f64>) -> PyResult<usize> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        crate::overlap::count_overlaps(&r)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn get_worst_overlap(rects: Vec<f64>) -> PyResult<(usize, usize, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        Ok(crate::overlap::get_worst_overlap(&r))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// =============================================================================
// projections module
// =============================================================================

#[pyfunction]
fn identity_projection(px: f64, py: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let result = crate::projections::identity_projection(&Point::new(px, py));
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_onto_board(px: f64, py: f64, board_w: f64, board_h: f64, margin: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let result = crate::projections::project_onto_board(&Point::new(px, py), board_w, board_h, margin);
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_onto_zone(px: f64, py: f64, zx: f64, zy: f64, zw: f64, zh: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let zone = Rect::new(zx, zy, zw, zh);
        let result = crate::projections::project_onto_zone(&Point::new(px, py), &zone);
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_outside_keepout(
    px: f64, py: f64, kx: f64, ky: f64, kw: f64, kh: f64, half_w: f64, half_h: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let keepout = Rect::new(kx, ky, kw, kh);
        let result = crate::projections::project_outside_keepout(
            &Point::new(px, py), &keepout, half_w, half_h,
        );
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_onto_half_plane(
    px: f64, py: f64, ox: f64, oy: f64, nx: f64, ny: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let origin = Point::new(ox, oy);
        let normal = Vec2 { x: nx, y: ny };
        let result = crate::projections::project_onto_half_plane(
            &Point::new(px, py), &origin, &normal,
        );
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_onto_edge_strip(
    px: f64, py: f64,
    ex1: f64, ey1: f64, ex2: f64, ey2: f64,
    strip_width: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let start = Point::new(ex1, ey1);
        let end = Point::new(ex2, ey2);
        let result = crate::projections::project_onto_edge_strip(
            &Point::new(px, py), &start, &end, strip_width,
        );
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn project_onto_side(px: f64, py: f64, board_w: f64, board_h: f64, side: &str) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let result = crate::projections::project_onto_side(
            &Point::new(px, py), board_w, board_h, side,
        );
        (result.x, result.y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// =============================================================================
// constraints module
// =============================================================================

#[pyfunction]
fn compute_valid_bounds(
    component_half_width: f64,
    component_half_height: f64,
    region_x_min: f64,
    region_y_min: f64,
    region_x_max: f64,
    region_y_max: f64,
    margin: f64,
) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let vb = crate::constraints::compute_valid_bounds(
            component_half_width,
            component_half_height,
            region_x_min,
            region_y_min,
            region_x_max,
            region_y_max,
            margin,
        );
        Ok((vb.x_min, vb.x_max, vb.y_min, vb.y_max))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn compute_boundary_violation(
    position_x: f64,
    position_y: f64,
    component_half_width: f64,
    component_half_height: f64,
    board_x_min: f64,
    board_y_min: f64,
    board_x_max: f64,
    board_y_max: f64,
) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let bv = crate::constraints::compute_boundary_violation(
            position_x,
            position_y,
            component_half_width,
            component_half_height,
            board_x_min,
            board_y_min,
            board_x_max,
            board_y_max,
        );
        Ok((bv.left, bv.right, bv.bottom, bv.top))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn is_within_bounds(
    position_x: f64,
    position_y: f64,
    component_half_width: f64,
    component_half_height: f64,
    region_x_min: f64,
    region_y_min: f64,
    region_x_max: f64,
    region_y_max: f64,
    tolerance: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        crate::constraints::is_within_bounds(
            position_x,
            position_y,
            component_half_width,
            component_half_height,
            region_x_min,
            region_y_min,
            region_x_max,
            region_y_max,
            tolerance,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn compute_zone_distance(
    position_x: f64,
    position_y: f64,
    zone_x_min: f64,
    zone_y_min: f64,
    zone_x_max: f64,
    zone_y_max: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        crate::constraints::compute_zone_distance(
            position_x,
            position_y,
            zone_x_min,
            zone_y_min,
            zone_x_max,
            zone_y_max,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
fn point_in_zone(
    position_x: f64,
    position_y: f64,
    zone_x_min: f64,
    zone_y_min: f64,
    zone_x_max: f64,
    zone_y_max: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        crate::constraints::point_in_zone(
            position_x,
            position_y,
            zone_x_min,
            zone_y_min,
            zone_x_max,
            zone_y_max,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// =============================================================================
// drc_inflate module
// =============================================================================

#[pyfunction]
fn inflate_pad_polygon(pad_points: Vec<f64>, clearance_mm: f64) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&pad_points);
        let result = crate::drc_inflate::inflate_pad_polygon(&pts, clearance_mm);
        Ok(points_to_vec(&result))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn precompute_inflated_dims(width: f64, height: f64, clearance_mm: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        Ok(crate::drc_inflate::precompute_inflated_dims(width, height, clearance_mm))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn precompute_from_pad_polygons(pad_polys: Vec<Vec<f64>>, clearance_mm: f64) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        let polys: Vec<Vec<Point>> = pad_polys
            .iter()
            .map(|v| vec_to_points(v))
            .collect();
        Ok(crate::drc_inflate::precompute_from_pad_polygons(&polys, clearance_mm))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn compute_inflated_half_dims_from_bounds(
    x1: f64, y1: f64, x2: f64, y2: f64, clearance_mm: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let bb = AABB::new(x1, y1, x2, y2);
        Ok(crate::drc_inflate::compute_inflated_half_dims_from_bounds(&bb, clearance_mm))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

#[pyfunction]
fn compute_drc_proxy_score(
    component_rects: Vec<f64>,
    pad_polys: Vec<Vec<f64>>,
    clearance_mm: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let rects = vec_to_aabbs(&component_rects);
        let polys: Vec<Vec<Point>> = pad_polys
            .iter()
            .map(|v| vec_to_points(v))
            .collect();
        crate::drc_inflate::compute_drc_proxy_score(&rects, &polys, clearance_mm)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// =============================================================================
// Module registration
// =============================================================================

pub fn register_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // primitives
    m.add_function(wrap_pyfunction!(point_distance, m)?)?;
    m.add_function(wrap_pyfunction!(point_distance_squared, m)?)?;
    m.add_function(wrap_pyfunction!(point_midpoint, m)?)?;
    m.add_function(wrap_pyfunction!(points_centroid, m)?)?;
    m.add_function(wrap_pyfunction!(point_to_line_distance, m)?)?;
    m.add_function(wrap_pyfunction!(rect_from_center, m)?)?;
    m.add_function(wrap_pyfunction!(rect_center, m)?)?;
    m.add_function(wrap_pyfunction!(rect_dimensions, m)?)?;
    m.add_function(wrap_pyfunction!(rect_area, m)?)?;
    m.add_function(wrap_pyfunction!(rect_contains_point, m)?)?;
    m.add_function(wrap_pyfunction!(rect_corners, m)?)?;
    m.add_function(wrap_pyfunction!(aabb_from_points, m)?)?;
    m.add_function(wrap_pyfunction!(aabb_intersects, m)?)?;
    m.add_function(wrap_pyfunction!(aabb_overlap_area, m)?)?;
    m.add_function(wrap_pyfunction!(aabb_union, m)?)?;
    m.add_function(wrap_pyfunction!(aabb_expand, m)?)?;
    m.add_function(wrap_pyfunction!(distance_to_rect_edge, m)?)?;
    m.add_function(wrap_pyfunction!(distance_to_specific_edge, m)?)?;
    m.add_function(wrap_pyfunction!(distance_to_board_boundary, m)?)?;
    m.add_function(wrap_pyfunction!(pairwise_distances, m)?)?;
    m.add_function(wrap_pyfunction!(pairwise_distances_squared, m)?)?;
    m.add_function(wrap_pyfunction!(batch_point_distance, m)?)?;

    // polygon
    m.add_function(wrap_pyfunction!(polygon_signed_area, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_area, m)?)?;
    m.add_function(wrap_pyfunction!(triangle_area, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_centroid, m)?)?;
    m.add_function(wrap_pyfunction!(points_centroid_winding, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_polygon_winding, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_polygon_soft, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_rect, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_rect_soft, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_perimeter, m)?)?;
    m.add_function(wrap_pyfunction!(compute_loop_area, m)?)?;
    m.add_function(wrap_pyfunction!(compute_loop_perimeter, m)?)?;
    m.add_function(wrap_pyfunction!(loop_area_penalty, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_bounding_box, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_bounding_circle, m)?)?;
    m.add_function(wrap_pyfunction!(is_convex, m)?)?;
    m.add_function(wrap_pyfunction!(polygon_orientation, m)?)?;
    m.add_function(wrap_pyfunction!(nearest_point_on_segment, m)?)?;
    m.add_function(wrap_pyfunction!(nearest_point_on_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(translate_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(scale_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(rotate_polygon, m)?)?;

    // sdf
    m.add_function(wrap_pyfunction!(sdf_circle, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_rectangle, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_box_2d, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_rounded_rectangle, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_capsule, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_convex_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_union, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_intersection, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_subtraction, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_smooth_union, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_smooth_intersection, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_offset, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_round, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_shell, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_to_mask, m)?)?;
    m.add_function(wrap_pyfunction!(sdf_to_penalty, m)?)?;

    // smooth
    m.add_function(wrap_pyfunction!(smooth_max, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_max_axis, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_max_pair, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_min, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_min_axis, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_min_pair, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_relu, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_relu_penalty, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_leaky_relu, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_abs, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_clip, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_step, m)?)?;
    m.add_function(wrap_pyfunction!(hpwl_smooth, m)?)?;
    m.add_function(wrap_pyfunction!(weighted_average_smooth, m)?)?;
    m.add_function(wrap_pyfunction!(get_alpha_schedule, m)?)?;
    m.add_function(wrap_pyfunction!(get_beta_schedule, m)?)?;

    // transform
    m.add_function(wrap_pyfunction!(get_rotation_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(rotate_point, m)?)?;
    m.add_function(wrap_pyfunction!(rotate_points, m)?)?;
    m.add_function(wrap_pyfunction!(get_rotated_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(rotate_rectangle_corners, m)?)?;
    m.add_function(wrap_pyfunction!(get_rotated_aabb, m)?)?;
    m.add_function(wrap_pyfunction!(transform_pin_position, m)?)?;
    m.add_function(wrap_pyfunction!(transform_pin_positions, m)?)?;
    m.add_function(wrap_pyfunction!(batch_get_rotated_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(batch_rotate_points, m)?)?;
    m.add_function(wrap_pyfunction!(rotation_index_to_onehot, m)?)?;
    m.add_function(wrap_pyfunction!(rotation_degrees_to_onehot, m)?)?;
    m.add_function(wrap_pyfunction!(onehot_to_rotation_degrees, m)?)?;
    m.add_function(wrap_pyfunction!(onehot_to_rotation_radians, m)?)?;
    m.add_function(wrap_pyfunction!(gumbel_softmax, m)?)?;
    m.add_function(wrap_pyfunction!(sample_rotation, m)?)?;
    m.add_function(wrap_pyfunction!(sample_rotation_batch, m)?)?;

    // overlap
    m.add_function(wrap_pyfunction!(box_box_distance, m)?)?;
    m.add_function(wrap_pyfunction!(box_box_distance_aabb, m)?)?;
    m.add_function(wrap_pyfunction!(component_overlap_amount, m)?)?;
    m.add_function(wrap_pyfunction!(overlap_area_estimate, m)?)?;
    m.add_function(wrap_pyfunction!(compute_pairwise_distances, m)?)?;
    m.add_function(wrap_pyfunction!(compute_total_overlap, m)?)?;
    m.add_function(wrap_pyfunction!(compute_overlap_penalty, m)?)?;
    m.add_function(wrap_pyfunction!(check_clearance_violation, m)?)?;
    m.add_function(wrap_pyfunction!(compute_clearance_penalties, m)?)?;
    m.add_function(wrap_pyfunction!(count_overlaps, m)?)?;
    m.add_function(wrap_pyfunction!(get_worst_overlap, m)?)?;

    // projections
    m.add_function(wrap_pyfunction!(identity_projection, m)?)?;
    m.add_function(wrap_pyfunction!(project_onto_board, m)?)?;
    m.add_function(wrap_pyfunction!(project_onto_zone, m)?)?;
    m.add_function(wrap_pyfunction!(project_outside_keepout, m)?)?;
    m.add_function(wrap_pyfunction!(project_onto_half_plane, m)?)?;
    m.add_function(wrap_pyfunction!(project_onto_edge_strip, m)?)?;
    m.add_function(wrap_pyfunction!(project_onto_side, m)?)?;

    // constraints
    m.add_function(wrap_pyfunction!(compute_valid_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_boundary_violation, m)?)?;
    m.add_function(wrap_pyfunction!(is_within_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_zone_distance, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_zone, m)?)?;

    // drc_inflate
    m.add_function(wrap_pyfunction!(inflate_pad_polygon, m)?)?;
    m.add_function(wrap_pyfunction!(precompute_inflated_dims, m)?)?;
    m.add_function(wrap_pyfunction!(precompute_from_pad_polygons, m)?)?;
    m.add_function(wrap_pyfunction!(compute_inflated_half_dims_from_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_drc_proxy_score, m)?)?;

    // corridor
    m.add_function(wrap_pyfunction!(extract_corridor_mask, m)?)?;

    // pad geometry (Wave 2: isolation barrier)
    m.add_function(wrap_pyfunction!(pad_corner_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_core_half_extents_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_support_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_axis_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_bounding_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(barrier_axis_gap_py, m)?)?;
    m.add_function(wrap_pyfunction!(best_rotation_for_barrier_py, m)?)?;
    m.add_function(wrap_pyfunction!(spice_loop_inductance_py, m)?)?;
    m.add_function(wrap_pyfunction!(spice_infer_unit_py, m)?)?;

    // copper coverage
    m.add_function(wrap_pyfunction!(rasterise_polygon_mask, m)?)?;

    // channel widths
    m.add_function(wrap_pyfunction!(edt_width_lookup_batch, m)?)?;

    // grid rasterisation (Wave 3 candidate #1: ClearanceGrid compute)
    m.add_function(wrap_pyfunction!(block_circle_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(block_segment_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(block_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(clear_circle_from_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(occupancy_bitmap_row_py, m)?)?;
    m.add_function(wrap_pyfunction!(fence_samples_py, m)?)?;
    m.add_function(wrap_pyfunction!(effective_creepage_py, m)?)?;
    m.add_function(wrap_pyfunction!(closest_component_for_zone_py, m)?)?;

    // bottleneck geometry (Wave 3: min-cut bottleneck kernels)
    m.add_function(wrap_pyfunction!(cell_capacity_batch_py, m)?)?;
    m.add_function(wrap_pyfunction!(hard_blocked_batch_py, m)?)?;
    m.add_function(wrap_pyfunction!(build_capacitated_graph_py, m)?)?;

    // clearance geometry (Wave 3: REQ-SAFE-01 validator geometry)
    m.add_function(wrap_pyfunction!(rotate_local_to_world_py, m)?)?;
    m.add_function(wrap_pyfunction!(origin_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(component_reach_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_pair_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(copper_scan_py, m)?)?;

    // audit (Wave 3 #5: R24 post-solve audit geometry)
    m.add_function(wrap_pyfunction!(bbox_from_center_py, m)?)?;
    m.add_function(wrap_pyfunction!(chebyshev_gap_py, m)?)?;

    // creepage_check (Wave 3 #7: HV-isolation clearance geometry)
    m.add_function(wrap_pyfunction!(point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(closest_point_on_segment_py, m)?)?;
    m.add_function(wrap_pyfunction!(segments_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(segment_to_segment_info_py, m)?)?;
    m.add_function(wrap_pyfunction!(min_clearance_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_required_creepage_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_high_voltage_net_py, m)?)?;

    Ok(())
}

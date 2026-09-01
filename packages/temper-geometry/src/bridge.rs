// =============================================================================
// PyO3 bridge for temper-geometry — exposes all geometry functions to Python
// =============================================================================

#![allow(clippy::too_many_arguments)]
// PyO3 bridge functions mirror Python function signatures 1:1.

use pyo3::prelude::*;
use crate::bottleneck_geometry::{
    build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py, min_cut_py,
};
use crate::body_collision::{
    AREA_TOLERANCE_MM2, fab_body_relations_batch_py, fab_body_validate_py,
};
use crate::audit::{bbox_from_center_py, chebyshev_gap_py, dist_py};
use crate::channel_widths::{edt_width_lookup_batch, prepare_channel_widths_edt};
use crate::connected_components::connected_components_8_transform;
use crate::edt::exact_edt_transform;
use crate::radius_pairs::radius_pairs_transform;
use crate::convex_hull::convex_hull_area_py;
use crate::nearest_neighbor::nearest_neighbor_transform;
use crate::copper_coverage::rasterise_polygon_mask;
use crate::corridor::extract_corridor_mask;
use crate::corridor_erosion::corridor_mask_for_net_py;
use crate::occupancy_raster::{
    blocking_net_ids_py, downsample_or_blocks_py, mark_path_rect_into_grid_py,
    mark_segment_rect_into_grid_py, mark_via_circle_into_grid_py, rasterize_area_polygons_py,
    unmark_path_rect_into_grid_py, unmark_segment_rect_into_grid_py,
};
use crate::grid_raster::{
    block_circle_into_grid_py, block_rect_into_grid_py, block_segment_into_grid_py,
    clear_circle_from_grid_py, closest_component_for_zone_py, effective_creepage_py,
    fence_samples_py, occupancy_bitmap_row_py,
};
use crate::grid_leaf::{
    block_exclusion_zone_into_grid_py, count_blocked_cells_py, grid_cell_available_py,
};
use crate::creepage_check::{
    calculate_required_creepage_py, closest_point_on_segment_py, is_high_voltage_net_py,
    min_clearance_distance_py, point_to_segment_distance_py, segment_to_segment_info_py,
    segments_intersect_py,
};
use crate::{barrier_axis_gap_py, best_rotation_for_barrier_py, pad_axis_radius_py, pad_bounding_radius_py, pad_corner_radius_py, pad_core_half_extents_py, pad_support_radius_py, spice_infer_unit_py, spice_loop_inductance_py};
use crate::heuristics_geometry::keepout_mask_flags_py;
use crate::organizational_geometry::{
    circle_offsets_py, decoupling_candidate_positions_py, domain_grid_positions_py,
    module_grid_positions_py, power_flow_positions_py,
};
use crate::style_geometry::{radial_sector_positions_py, signal_chain_positions_py};
use crate::clearance_geometry::{
    component_reach_py, copper_scan_py, origin_distance_py, pad_pair_distance_py,
    pad_to_capsule_distance_py,
    rotate_local_to_world_py,
};
// Wave 4, router_v6 core slice. The `drc_` prefix is load-bearing: this
// crate already exports a `point_to_segment_distance_py` for creepage_check,
// and that is a DIFFERENT function (different degenerate-segment threshold).
// The prefix keeps the two visibly distinct at every call site.
use crate::drc_constraints_geometry::{
    drc_closest_points_segment_segment_py, drc_point_to_circle_distance_py,
    drc_point_to_rotated_rect_distance_py, drc_point_to_segment_distance_py,
    drc_rotated_rect_bounding_radius_py, drc_rotated_rect_corners_py, drc_segment_direction_py,
    drc_segment_length_py, drc_segment_midpoint_py, drc_segment_to_rotated_rect_distance_py,
    drc_segment_to_segment_distance_py, drc_segments_intersect_py,
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

// `vec_to_aabbs` lived here to feed the retired `compute_drc_proxy_score`
// binding (which took component rectangles; the real Python signature takes
// centre positions and half-dimensions). It had no other caller and went with it.

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

// =============================================================================
// polygon module
// =============================================================================

#[pyfunction]
fn polygon_area(vertices: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts = vec_to_points(&vertices);
        crate::polygon::polygon_area(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// =============================================================================
// sdf module
// =============================================================================

#[pyfunction]
fn sdf_circle(px: f64, py: f64, cx: f64, cy: f64, r: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::sdf::sdf_circle(&Point::new(px, py), cx, cy, r))
        .map_err(temper_py_bridge::panic_to_err)
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
fn smooth_leaky_relu(x: f64, alpha: f64, negative_slope: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| crate::smooth::smooth_leaky_relu(x, alpha, negative_slope))
        .map_err(temper_py_bridge::panic_to_err)
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
fn get_rotated_bounds(rx: f64, ry: f64, rw: f64, rh: f64, angle_rad: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let r = Rect::new(rx, ry, rw, rh);
        let bb = crate::transform::get_rotated_bounds(&r, angle_rad);
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

// =============================================================================
// overlap module
// =============================================================================

#[pyfunction]
fn compute_pairwise_distances(rects: Vec<f64>) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        let r = vec_to_rects(&rects);
        Ok(crate::overlap::compute_pairwise_distances(&r))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

// =============================================================================
// projections module
// =============================================================================

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
// Module registration
// =============================================================================

pub fn register_functions(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // body collision (Rust-owned validated F.Fab geometry authority)
    m.add("AREA_TOLERANCE_MM2", AREA_TOLERANCE_MM2)?;
    m.add_function(wrap_pyfunction!(fab_body_validate_py, m)?)?;
    m.add_function(wrap_pyfunction!(fab_body_relations_batch_py, m)?)?;

    // primitives
    m.add_function(wrap_pyfunction!(point_distance, m)?)?;

    // polygon
    m.add_function(wrap_pyfunction!(polygon_area, m)?)?;

    // sdf
    m.add_function(wrap_pyfunction!(sdf_circle, m)?)?;
    // smooth
    m.add_function(wrap_pyfunction!(smooth_max, m)?)?;
    m.add_function(wrap_pyfunction!(smooth_leaky_relu, m)?)?;

    // transform
    m.add_function(wrap_pyfunction!(get_rotation_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(rotate_point, m)?)?;
    m.add_function(wrap_pyfunction!(get_rotated_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(transform_pin_position, m)?)?;
    m.add_function(wrap_pyfunction!(transform_pin_positions, m)?)?;

    // overlap
    m.add_function(wrap_pyfunction!(compute_pairwise_distances, m)?)?;

    // constraints
    m.add_function(wrap_pyfunction!(compute_valid_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_boundary_violation, m)?)?;
    m.add_function(wrap_pyfunction!(is_within_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_zone_distance, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_zone, m)?)?;

    // corridor
    m.add_function(wrap_pyfunction!(extract_corridor_mask, m)?)?;
    m.add_function(wrap_pyfunction!(corridor_mask_for_net_py, m)?)?;

    // pad geometry (Wave 2: isolation barrier)
    m.add_function(wrap_pyfunction!(pad_corner_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_core_half_extents_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_support_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_axis_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_bounding_radius_py, m)?)?;
    crate::copper_reach::register(m)?;
    m.add_function(wrap_pyfunction!(barrier_axis_gap_py, m)?)?;
    m.add_function(wrap_pyfunction!(best_rotation_for_barrier_py, m)?)?;
    m.add_function(wrap_pyfunction!(spice_loop_inductance_py, m)?)?;
    m.add_function(wrap_pyfunction!(spice_infer_unit_py, m)?)?;

    // copper coverage
    m.add_function(wrap_pyfunction!(rasterise_polygon_mask, m)?)?;

    // channel widths
    m.add_function(wrap_pyfunction!(edt_width_lookup_batch, m)?)?;
    m.add_function(wrap_pyfunction!(exact_edt_transform, m)?)?;
    m.add_function(wrap_pyfunction!(connected_components_8_transform, m)?)?;

    // radius_pairs (router_v6/channel_skeleton.py's island-bridging MST
    // candidate generation -- replaces scipy.spatial.cKDTree.query_pairs)
    m.add_function(wrap_pyfunction!(radius_pairs_transform, m)?)?;

    // convex_hull (physics/loop_area.py + validation/trace_analyzer.py --
    // replaces scipy.spatial.ConvexHull; both call sites read only the
    // scalar hull area, see convex_hull.rs's module doc)
    m.add_function(wrap_pyfunction!(convex_hull_area_py, m)?)?;

    // nearest_neighbor (validation/mfem_compare.py's project_mfem_to_fdm --
    // replaces scipy.interpolate.griddata(method="nearest"))
    m.add_function(wrap_pyfunction!(nearest_neighbor_transform, m)?)?;

    // grid rasterisation (Wave 3 candidate #1: ClearanceGrid compute)
    m.add_function(wrap_pyfunction!(block_circle_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(block_segment_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(block_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(clear_circle_from_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(occupancy_bitmap_row_py, m)?)?;
    m.add_function(wrap_pyfunction!(fence_samples_py, m)?)?;
    m.add_function(wrap_pyfunction!(effective_creepage_py, m)?)?;
    m.add_function(wrap_pyfunction!(keepout_mask_flags_py, m)?)?;
    m.add_function(wrap_pyfunction!(closest_component_for_zone_py, m)?)?;

    // grid residual leaf compute (D3 batch: blocked-count reduction,
    // per-sample availability, EXP-13 exclusion-zone write)
    m.add_function(wrap_pyfunction!(count_blocked_cells_py, m)?)?;
    m.add_function(wrap_pyfunction!(grid_cell_available_py, m)?)?;
    m.add_function(wrap_pyfunction!(block_exclusion_zone_into_grid_py, m)?)?;

    // occupancy-grid rasterisation (Wave 4: router_v6/occupancy_grid.py)
    m.add_function(wrap_pyfunction!(mark_path_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(mark_segment_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(unmark_segment_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(unmark_path_rect_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(blocking_net_ids_py, m)?)?;
    m.add_function(wrap_pyfunction!(mark_via_circle_into_grid_py, m)?)?;
    m.add_function(wrap_pyfunction!(downsample_or_blocks_py, m)?)?;
    // build_occupancy_grid rasterisation (2026-08-15): strict-interior
    // point-in-polygon scanline replacing shapely.contains(check_area, ...)
    m.add_function(wrap_pyfunction!(rasterize_area_polygons_py, m)?)?;

    // Channel-width EDT preparation: Python supplies Shapely ring
    // coordinates; rasterisation and the exact transform remain Rust-owned.
    m.add_function(wrap_pyfunction!(prepare_channel_widths_edt, m)?)?;

    // organizational heuristics (Wave 4: heuristics/organizational.py's
    // five _place_* position kernels)
    m.add_function(wrap_pyfunction!(module_grid_positions_py, m)?)?;
    m.add_function(wrap_pyfunction!(circle_offsets_py, m)?)?;
    m.add_function(wrap_pyfunction!(power_flow_positions_py, m)?)?;
    m.add_function(wrap_pyfunction!(decoupling_candidate_positions_py, m)?)?;
    m.add_function(wrap_pyfunction!(domain_grid_positions_py, m)?)?;
    m.add_function(wrap_pyfunction!(radial_sector_positions_py, m)?)?;
    m.add_function(wrap_pyfunction!(signal_chain_positions_py, m)?)?;

    // bottleneck geometry (Wave 3: min-cut bottleneck kernels)
    m.add_function(wrap_pyfunction!(cell_capacity_batch_py, m)?)?;
    m.add_function(wrap_pyfunction!(hard_blocked_batch_py, m)?)?;
    m.add_function(wrap_pyfunction!(build_capacitated_graph_py, m)?)?;
    // Wave 4 migration: networkx min-cut → Rust (Edmonds-Karp)
    m.add_function(wrap_pyfunction!(min_cut_py, m)?)?;

    // clearance geometry (Wave 3: REQ-SAFE-01 validator geometry)
    m.add_function(wrap_pyfunction!(rotate_local_to_world_py, m)?)?;
    m.add_function(wrap_pyfunction!(origin_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(component_reach_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_pair_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(pad_to_capsule_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(copper_scan_py, m)?)?;

    // audit (Wave 3 #5: R24 post-solve audit geometry)
    m.add_function(wrap_pyfunction!(bbox_from_center_py, m)?)?;
    m.add_function(wrap_pyfunction!(chebyshev_gap_py, m)?)?;
    m.add_function(wrap_pyfunction!(dist_py, m)?)?;

    // creepage_check (Wave 3 #7: HV-isolation clearance geometry)
    m.add_function(wrap_pyfunction!(point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(closest_point_on_segment_py, m)?)?;
    m.add_function(wrap_pyfunction!(segments_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(segment_to_segment_info_py, m)?)?;
    m.add_function(wrap_pyfunction!(min_clearance_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_required_creepage_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_high_voltage_net_py, m)?)?;

    // area_sufficiency (Wave 4 Phase 4: analysis/_area_sufficiency.py)
    crate::area_sufficiency::register(m)?;

    // drc_constraints_geometry (Wave 4: router_v6/constraints_geometry.py)
    m.add_function(wrap_pyfunction!(drc_point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segment_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segments_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_closest_points_segment_segment_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_point_to_circle_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_rotated_rect_corners_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_rotated_rect_bounding_radius_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_point_to_rotated_rect_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segment_to_rotated_rect_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segment_length_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segment_direction_py, m)?)?;
    m.add_function(wrap_pyfunction!(drc_segment_midpoint_py, m)?)?;

    Ok(())
}

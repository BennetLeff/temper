pub mod types;
pub mod primitives;
pub mod smooth;
pub mod polygon;
pub mod sdf;
pub mod transform;
pub mod overlap;
pub mod projections;
pub mod constraints;
pub mod drc_inflate;
// Wholly pyo3 surface (see congestion_tensor.rs's module doc comment for
// why this can't be split into a kernel + wrapper like the other modules).
#[cfg(feature = "python")]
pub mod congestion_tensor;
// Wave 4 Phase 4: analysis/_area_sufficiency.py aggregation kernels
// (wholly pyo3 surface — the module is the pyfunction wrapper + the
// Neumaier kernel it owns).
#[cfg(feature = "python")]
pub mod area_sufficiency;
pub mod pad_geometry;
// Wave 4 Phase B: router_v6/escape_via_generator.py (survey cluster G, split)
// and the six-module congestion & placement-feedback cluster E. Both are
// wholly pyo3 surfaces: the kernel and its bridge are one module, because
// every entry point exists to mirror one Python function bit-for-bit.
#[cfg(feature = "python")]
pub mod escape_via;
#[cfg(feature = "python")]
pub mod congestion;
pub mod clearance_geometry;
pub mod spice_estimators;
#[cfg(feature = "python")]
pub use pad_geometry::{
    barrier_axis_gap_py, best_rotation_for_barrier_py, pad_axis_radius_py, pad_bounding_radius_py,
    pad_corner_radius_py, pad_core_half_extents_py, pad_support_radius_py,
};
#[cfg(feature = "python")]
pub use clearance_geometry::{
    component_reach_py, copper_scan_py, origin_distance_py, pad_pair_distance_py,
    rotate_local_to_world_py,
};
#[cfg(feature = "python")]
pub use spice_estimators::{spice_infer_unit_py, spice_loop_inductance_py};
pub mod corridor;
pub mod copper_coverage;
pub mod channel_widths;
pub mod grid_raster;
#[cfg(feature = "python")]
pub use grid_raster::{
    block_circle_into_grid_py, block_rect_into_grid_py, block_segment_into_grid_py,
    clear_circle_from_grid_py, closest_component_for_zone_py, effective_creepage_py,
    fence_samples_py, occupancy_bitmap_row_py,
};
pub mod host_math;
pub mod grid_utils;
#[cfg(feature = "python")]
pub use grid_utils::{add_endpoint_nudge_py, snap_to_grid_py};
pub mod via_placement;
#[cfg(feature = "python")]
pub use via_placement::{is_via_position_valid_py, place_via_with_clearance_py, via_distance_py};
pub mod bottleneck_geometry;
#[cfg(feature = "python")]
pub use bottleneck_geometry::{build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py};
pub mod audit;
pub mod creepage_check;
// Wave 4, router_v6 core slice: the DRC constraint-geometry kernel behind
// router_v6/constraints_geometry.py. Declared after creepage_check because
// it reuses that module's CPython min/max replications.
pub mod drc_constraints_geometry;
#[cfg(feature = "python")]
pub use drc_constraints_geometry::{
    drc_closest_points_segment_segment_py, drc_point_to_circle_distance_py,
    drc_point_to_rotated_rect_distance_py, drc_point_to_segment_distance_py,
    drc_rotated_rect_bounding_radius_py, drc_rotated_rect_corners_py, drc_segment_direction_py,
    drc_segment_length_py, drc_segment_midpoint_py, drc_segment_to_rotated_rect_distance_py,
    drc_segment_to_segment_distance_py, drc_segments_intersect_py,
};
#[cfg(feature = "python")]
mod bridge;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    crate::escape_via::register(m)?;
    crate::congestion::register(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    Ok(())
}

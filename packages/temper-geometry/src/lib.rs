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
pub mod bottleneck_geometry;
#[cfg(feature = "python")]
pub use bottleneck_geometry::{build_capacitated_graph_py, cell_capacity_batch_py, hard_blocked_batch_py};
pub mod audit;
pub mod creepage_check;
#[cfg(feature = "python")]
mod bridge;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    Ok(())
}

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
pub mod congestion_tensor;
pub mod pad_geometry;
pub mod clearance_geometry;
pub mod spice_estimators;
pub use pad_geometry::{
    barrier_axis_gap_py, best_rotation_for_barrier_py, pad_axis_radius_py, pad_bounding_radius_py,
    pad_corner_radius_py, pad_core_half_extents_py, pad_support_radius_py,
};
pub use clearance_geometry::{
    component_reach_py, copper_scan_py, origin_distance_py, pad_pair_distance_py,
    rotate_local_to_world_py,
};
pub use spice_estimators::{spice_infer_unit_py, spice_loop_inductance_py};
pub mod corridor;
pub mod copper_coverage;
pub mod channel_widths;
mod bridge;

use pyo3::prelude::*;

#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    Ok(())
}

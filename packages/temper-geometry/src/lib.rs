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
mod bridge;

use pyo3::prelude::*;

#[pymodule]
fn temper_geometry(m: &Bound<'_, PyModule>) -> PyResult<()> {
    bridge::register_functions(m)?;
    m.add_class::<crate::congestion_tensor::CongestionTensor>()?;
    Ok(())
}

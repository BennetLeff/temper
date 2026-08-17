//! Thin pyo3 adapter over the [`crate::drc_count`] module.
//!
//! Each `#[pyfunction]` delegates to pure-Rust logic in `drc_count.rs` (the
//! unconditional module, which is also where the unit/property tests live) —
//! the same pure-kernel/pyo3-surface split as `ipc`/`ipc_pyo3`. The Python
//! shim (`temper_placer.validation._drc_api.drc_count_from_kicad`) marshals
//! the returned tuple into a dataclass.

use pyo3::prelude::*;

use crate::drc_count;

/// Classify a raw kicad-cli DRC count against KiCad's per-category
/// reporting caps. Returns `(count, is_capped, display)` where `display`
/// is [`drc_count::DrcCount::display`] (`"42"` or
/// `"199 (CAPPED — true count >= 199)"`).
#[pyfunction]
fn drc_count_from_kicad(count: u32, category: &str) -> (u32, bool, String) {
    let c = drc_count::DrcCount::from_kicad(count, category);
    (c.count(), c.is_capped(), c.display())
}

/// The reporting cap for a kicad-cli violation *type*, or `None` for
/// categories known not to cap (e.g. `creepage`). Mirrors
/// `scripts/measure_uncapped_drc.py::cap_for`, single-sourced in Rust.
#[pyfunction]
fn drc_cap_for(category: &str) -> Option<u32> {
    drc_count::cap_for(category)
}

/// Register the drc-count kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(drc_count_from_kicad, m)?)?;
    m.add_function(wrap_pyfunction!(drc_cap_for, m)?)?;
    Ok(())
}

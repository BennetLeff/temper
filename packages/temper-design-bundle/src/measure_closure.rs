//! Wave 4 Phase 4 — regression slice: closure-measurement kernel.
//!
//! The portable compute of `temper_placer/regression/measure_closure.py`
//! (pinned verbatim as the oracle `_measure_closure_py_oracle.py`, commit
//! `0a29f15e3`) migrated into `temper-design-bundle`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `compute_drc_clearance_pass_pct` | the `drc_clearance_pass_pct` three-branch rule in `measure_closure` |
//!
//! Design boundaries (argued in-source; see
//! `packages/temper-design-bundle/VERIFICATION.md`):
//!
//! - `measure_closure.py` is a THIN harness over the kept `ClosureTest.run()`
//!   (a JUSTIFIED-KEEP-adjacent harness); its only portable compute is this
//!   one formula. Everything else — ClosureTest construction, the payload
//!   dict assembly (including the `closure_summary` string and the
//!   `errors!r` in the zero-results raise), the JSON CLI — is marshalling
//!   over the kept `ClosureResult` and stays in the delegation module.
//! - The `10.0 * drc_errors` multiplication promotes the int count to float
//!   (the oracle's int*float), and the result is clamped at 0.0 (the
//!   oracle's `max(0.0, ...)`, which also floors a negative count's effect).
//! - The `stages_exercised >= 4` boundary is inclusive, and a negative count
//!   is impossible in the pipeline (guarded anyway by the clamp).
//!
//! pyo3 panic policy: pyo3's default `catch_unwind` at the `#[pyfunction]`
//! boundary (R1g).

use pyo3::prelude::*;
use pyo3::types::PyModule;

/// DRC clearance pass percentage (verbatim port of the oracle's three-branch
/// rule): 100.0 when the DRC stage ran clean, `max(0, 100 - 10*errors)` when
/// it ran with errors, 0.0 when the DRC stage did not run.
#[pyfunction]
fn compute_drc_clearance_pass_pct(stages_exercised: i64, drc_errors: i64) -> f64 {
    if stages_exercised >= 4 && drc_errors == 0 {
        100.0
    } else if stages_exercised >= 4 {
        (100.0 - 10.0 * drc_errors as f64).max(0.0)
    } else {
        0.0
    }
}

/// Register the kernel on the `temper_design_bundle_python` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_drc_clearance_pass_pct, m)?)?;
    Ok(())
}

// temper-orchestration: the orchestration compute of the Wave-4 Phase-5
// Python→Rust migration slice (cli/adapters/temper-workflow).
//
// Surfaces hosted here (each with its own module and a differential against
// a VERBATIM pre-migration oracle in the temper-placer / temper-workflow
// test trees; see this crate's VERIFICATION.md):
//
// - `timing`        — cli/timing.py: compare_stage, p95
// - `trace_filter`  — cli/trace_commands.py: filter_decisions,
//                     find_rejected_alternative
// - `copper_length` — temper-workflow routing/route_and_measure.py:
//                     measure_copper_length
//
// Panic safety at the boundary (R1g): pyo3's `#[pyfunction]` expansion
// wraps every exported body in `catch_unwind` and converts a Rust panic
// into `PyPanicException`, so no panic can unwind across the pyo3 frame
// into CPython (the crate also sets `profile.release.panic = "unwind"` so
// that catch is what runs).
mod copper_length;
mod host_math;
mod timing;
mod trace_filter;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn temper_orchestration(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(timing::compare_stage, m)?)?;
    m.add_function(wrap_pyfunction!(timing::p95, m)?)?;
    m.add_function(wrap_pyfunction!(trace_filter::filter_decisions, m)?)?;
    m.add_function(wrap_pyfunction!(trace_filter::find_rejected_alternative, m)?)?;
    m.add_function(wrap_pyfunction!(copper_length::measure_copper_length, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn module_exports_exist() {
        // Compile-time sanity: the five exported names exist on their
        // modules. The behavioural proof is the differential suite.
        let _ = super::timing::compare_stage(0.0, 1.0, 0.2, 10.0);
        let _ = super::copper_length::measure_copper_length(vec![]);
    }
}

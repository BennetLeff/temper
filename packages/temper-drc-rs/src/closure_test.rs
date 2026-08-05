//! Wave 4 Phase 4 — regression slice: closure-test self-consistency kernels.
//!
//! The self-consistency compute of `temper_placer/regression/closure_test.py`
//! (pinned verbatim as the oracle `_closure_test_py_oracle.py`, commit
//! `0a29f15e3`) migrated into `temper_drc-rs`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `closure_validate` | `ClosureResult.validate` — the zero-results / insufficient-stages assertions |
//! | `closure_summary` | `ClosureResult.summary` — the exact report string (incl. `:.1f` formatting) |
//!
//! Design boundaries (argued in-source; see
//! `packages/temper-drc-rs/VERIFICATION.md`):
//!
//! - `ClosureTest.run()` orchestration stays Python — it consumes pipeline /
//!   router / DRC harness modules outside this slice's surface; only the two
//!   self-consistency kernels migrate.
//! - `:.1f` fixed-point formatting is measured CPython-parity (the
//!   validation-slice precedent: 100k/100k on random values, round-half-even).
//!
//! pyo3 panic policy: pyo3's default `catch_unwind` at every `#[pyfunction]`
//! boundary (R1g).

use pyo3::prelude::*;
use pyo3::types::PyModule;

/// Self-consistency assertions for a closure run (verbatim port of
/// `ClosureResult.validate`): returns the failure messages in the oracle's
/// exact order.
#[pyfunction]
fn closure_validate(
    benders_iterations: i64,
    router_completion_pct: f64,
    stages_exercised: i64,
) -> Vec<String> {
    let mut failures = Vec::new();
    if benders_iterations <= 0 {
        failures.push(
            "benders_iterations <= 0: pipeline produced no placement iterations".to_string(),
        );
    }
    if router_completion_pct <= 0.0 {
        failures.push("router_completion_pct <= 0: pipeline produced no routing results".to_string());
    }
    if stages_exercised < 2 {
        failures.push(format!(
            "stages_exercised ({stages_exercised}) < 2: insufficient pipeline execution"
        ));
    }
    if benders_iterations <= 0 && router_completion_pct <= 0.0 {
        failures.push("zero-results: both placement and routing produced no results".to_string());
    }
    failures
}

/// Render the closure report string (verbatim port of `ClosureResult.summary`),
/// including the oracle's `:.1f` formatting for the completion pct and wall
/// clock.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn closure_summary(
    board_id: String,
    passed: bool,
    benders_iterations: i64,
    benders_cuts: i64,
    router_completion_pct: f64,
    drc_errors: i64,
    drc_warnings: i64,
    wall_clock_seconds: f64,
    stages_exercised: i64,
    errors: Vec<String>,
    warnings: Vec<String>,
) -> String {
    let mut lines = vec![
        format!("=== Closure Test: {board_id} ==="),
        format!("Status: {}", if passed { "PASS" } else { "FAIL" }),
        format!("Benders iterations: {benders_iterations}, cuts: {benders_cuts}"),
        format!("Router completion: {router_completion_pct:.1}%"),
        format!("DRC: {drc_errors} errors, {drc_warnings} warnings"),
        format!("Wall clock: {wall_clock_seconds:.1}s"),
        format!("Stages exercised: {stages_exercised}"),
    ];
    for e in &errors {
        lines.push(format!("  ERROR: {e}"));
    }
    for w in &warnings {
        lines.push(format!("  WARNING: {w}"));
    }
    lines.join("\n")
}

/// Register the closure kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(closure_validate, m)?)?;
    m.add_function(wrap_pyfunction!(closure_summary, m)?)?;
    Ok(())
}

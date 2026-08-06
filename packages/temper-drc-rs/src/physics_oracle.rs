//! Wave 4 Phase 4 — regression slice: physics-oracle compute kernels.
//!
//! The portable compute of `temper_placer/regression/physics_oracle.py`
//! (pinned verbatim as the oracle `_physics_oracle_py_oracle.py`, commit
//! `0a29f15e3`) migrated into `temper_drc-rs`:
//!
//! | Kernel | Python origin |
//! |---|---|
//! | `compute_oracle_margins` | `compute_oracle_margins` — score → engineering-unit margin math |
//! | `overall_score` | the `sum(normalized_scores) / len(...)` aggregation |
//! | `clearance_passed` | `passed = clearance >= _CLEARANCE_PASS_THRESHOLD` |
//!
//! Design boundaries (argued in-source; see
//! `packages/temper-drc-rs/VERIFICATION.md`):
//!
//! - R1h: this is an ORACLE/comparison kernel, NOT a physics gate — it scores
//!   a placement against physics metrics, no CP-SAT constraint gates on a
//!   physics quantity here. The R24 discipline (soundness proof, BMC, audit)
//!   therefore does not apply; state recorded explicitly because the ledger
//!   requires it.
//! - The metric functions themselves (`thermal_score`, `dual_rail_clearance_report`,
//!   `zone_compliance_score`, `loop_area_score`, `compactness_score`,
//!   `derive_constraints_from_spec`, the KiCad parser, `infer_quality_config`)
//!   live in other surfaces outside this slice; the orchestration that calls
//!   them stays in the delegation module as cross-boundary Python call-backs.
//! - `overall_score` MUST reproduce CPython 3.12's builtin `sum()` float path:
//!   since 3.12 `sum()` uses Neumaier-compensated summation for floats
//!   (measured on this platform: a plain `+=` accumulation diverges from
//!   `sum()` on 4640/20000 random inputs; `sum([1e16, 1.0, -1e16])` is 1.0).
//!   The kernel transcribes that loop (an order-preserving compensated
//!   accumulate); the differential pins it. Plain `x += y` would be a REAL
//!   mutation.
//! - Margin multiplication is IEEE-754 — bit-identical in both arms.
//! - `compute_oracle_margins` reads its score keys with a 1.0 default (the
//!   oracle's `dict.get(key, 1.0)`). Values are extracted as `f64`; an int
//!   leaf converts exactly (pyo3 int→float), a non-numeric leaf fails closed
//!   with `PyValueError` (the oracle raises `TypeError` at the `*` — both
//!   fail closed on pathological reports).
//!
//! pyo3 panic policy: pyo3's default `catch_unwind` at every `#[pyfunction]`
//! boundary (R1g).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyModule};

/// Convert a score dict into engineering-unit margins (verbatim port of
/// `compute_oracle_margins`): `thermal_headroom_mm`, `clearance_margin_mm`,
/// `loop_area_margin_mm2`. Margins are *signed headroom* — positive above
/// threshold, negative a violation estimate.
#[pyfunction]
fn compute_oracle_margins(
    py: Python<'_>,
    report: &Bound<'_, PyDict>,
    max_heatspread_mm: f64,
    hv_lv_threshold_mm: f64,
    max_loop_area_mm2: f64,
) -> PyResult<Py<PyDict>> {
    let get = |key: &str| -> PyResult<f64> {
        match report.get_item(key)? {
            Some(v) => v.extract::<f64>().map_err(|_| {
                PyValueError::new_err(format!("quality_report[{key}] must be numeric"))
            }),
            None => Ok(1.0),
        }
    };
    let thermal_score = get("thermal_score")?;
    let clearance_score = get("hv_lv_clearance_score")?;
    let loop_score = get("loop_area_score")?;

    let thermal_headroom_mm = thermal_score * max_heatspread_mm;
    let clearance_margin_mm = (clearance_score - 1.0) * hv_lv_threshold_mm;
    let loop_area_margin_mm2 = loop_score * max_loop_area_mm2;

    let d = PyDict::new(py);
    d.set_item("thermal_headroom_mm", thermal_headroom_mm)?;
    d.set_item("clearance_margin_mm", clearance_margin_mm)?;
    d.set_item("loop_area_margin_mm2", loop_area_margin_mm2)?;
    Ok(d.into())
}

/// The overall quality score aggregation (verbatim port of the oracle's
/// `sum(normalized_scores) / len(normalized_scores) if normalized_scores
/// else 0.0`): CPython 3.12's Neumaier-compensated `sum()` over the scores,
/// divided by the count. Empty input → `0.0`.
#[pyfunction]
fn overall_score(scores: Vec<f64>) -> f64 {
    if scores.is_empty() {
        return 0.0;
    }
    // CPython 3.12 builtin `sum()` float path — Neumaier-compensated.
    let mut sum = 0.0_f64;
    let mut c = 0.0_f64;
    for x in &scores {
        let t = sum + x;
        if sum.abs() >= x.abs() {
            c += (sum - t) + x;
        } else {
            c += (x - t) + sum;
        }
        sum = t;
    }
    (sum + c) / scores.len() as f64
}

/// The oracle's single-run pass/fail decision: `clearance >= threshold`
/// (the default threshold `_CLEARANCE_PASS_THRESHOLD` is 0.95).
#[pyfunction]
fn clearance_passed(clearance: f64, threshold: f64) -> bool {
    clearance >= threshold
}

/// Register the physics-oracle kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_oracle_margins, m)?)?;
    m.add_function(wrap_pyfunction!(overall_score, m)?)?;
    m.add_function(wrap_pyfunction!(clearance_passed, m)?)?;
    Ok(())
}

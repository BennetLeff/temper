//! Wave 4 Phase 4 — regression slice: CP-SAT comparison kernel.
//!
//! `temper_placer/regression/cp_sat_comparison.py` (pinned verbatim as the
//! oracle `_cp_sat_comparison_py_oracle.py`, commit `0a29f15e3`) is fully
//! portable compute — `compare_metric_dicts` (the Pareto-style per-metric
//! gate, the wirelength ratio/tolerance rule, the `:.2f`/`:.3f`/`:.4f`
//! detail strings, the summary line, and the failing-metric list repr)
//! migrated into `temper-design-bundle`. The Python module becomes a
//! delegation shim over the returned records.
//!
//! Numeric-fidelity notes (each pinned by the differential):
//!
//! - Values are converted with Python `builtins.float` (the oracle's
//!   `float(candidate_scores.get(...))`) — int/float/str-number leaves all
//!   convert exactly like the oracle, and a non-numeric leaf raises the same
//!   `ValueError`/`TypeError` family the oracle's `float()` raises.
//! - Fixed-point `:.2f`/`:.3f`/`:.4f` formatting is measured CPython-parity
//!   (the validation-slice precedent, 100k/100k on random values).
//! - The summary's `Failing: ['a', 'b']` list is Python's repr of a list of
//!   str; rendered here as single-quoted names joined by `, `. Metric names
//!   are score-dict keys (realistically simple identifiers); a name carrying
//!   a quote/backslash is a documented narrowing (Python repr would escape
//!   it).
//! - `bool` interpolation in the detail lines renders `True`/`False`
//!   (Python), never Rust's `true`/`false`.
//! - The metric iteration order is `sorted()` of the key intersection —
//!   deterministic, so no set/dict hash-order dependence survives.
//! - Empty intersection: `passed=True`, no comparisons, summary
//!   `"Parity comparison: 0/0 metrics passed"` — the oracle's vacuous-true
//!   semantics, preserved exactly.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyModule};

/// Python's `bool` string rendering ("True"/"False").
fn py_bool(b: bool) -> &'static str {
    if b {
        "True"
    } else {
        "False"
    }
}

/// Call Python's builtin `float()` on a value (the oracle's `float(x)`
/// semantics — `float("1.5")` must parse, and a non-numeric raises).
fn py_builtin_float(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<f64> {
    let f = py.import("builtins")?.getattr("float")?;
    let out = f.call1((value,))?;
    out.extract::<f64>()
}

/// Compare two score dicts per-metric (verbatim port of
/// `compare_metric_dicts`). Returns a dict with `passed`, `comparisons` (a
/// list of `{name, cp_sat_value, jax_value, passed, detail}` dicts in sorted
/// metric-name order) and `summary`.
#[pyfunction]
#[pyo3(signature = (candidate_scores, baseline_scores, wirelength_metric))]
fn compare_metric_dicts(
    py: Python<'_>,
    candidate_scores: &Bound<'_, PyDict>,
    baseline_scores: &Bound<'_, PyDict>,
    wirelength_metric: String,
) -> PyResult<Py<PyDict>> {
    // metrics = set(candidate.keys()) & set(baseline.keys())
    let mut metric_names: Vec<String> = Vec::new();
    for key in candidate_scores.keys() {
        if let Ok(name) = key.extract::<String>()
            && baseline_scores.get_item(&name)?.is_some()
        {
            metric_names.push(name);
        }
    }
    metric_names.sort();

    let mut comparisons: Vec<(String, f64, f64, bool, String)> = Vec::new();
    let mut all_passed = true;

    for metric_name in &metric_names {
        let cand_val = match candidate_scores.get_item(metric_name)? {
            Some(v) => py_builtin_float(py, &v)?,
            None => 0.0,
        };
        let base_val = match baseline_scores.get_item(metric_name)? {
            Some(v) => py_builtin_float(py, &v)?,
            None => 0.0,
        };

        let (passed, detail) = if *metric_name == wirelength_metric {
            // Lower is better, within a 5% tolerance.
            let (ratio, passed) = if base_val > 0.0 {
                (cand_val / base_val, cand_val <= base_val * 1.05)
            } else {
                // baseline 0: candidate must be 0 too.
                (f64::INFINITY, cand_val <= 0.0)
            };
            (
                passed,
                format!(
                    "{metric_name}: candidate={cand_val:.2}, baseline={base_val:.2}, ratio={ratio:.3}, tolerance=1.05, passed={}",
                    py_bool(passed)
                ),
            )
        } else {
            // Higher is better (default for all oracle metrics), 1e-9 slack.
            let passed = cand_val >= base_val - 1e-9;
            let delta = cand_val - base_val;
            (
                passed,
                format!(
                    "{metric_name}: candidate={cand_val:.4}, baseline={base_val:.4}, delta={delta:.4}, passed={}",
                    py_bool(passed)
                ),
            )
        };

        if !passed {
            all_passed = false;
        }
        comparisons.push((metric_name.clone(), cand_val, base_val, passed, detail));
    }

    let passed_metrics = comparisons.iter().filter(|c| c.3).count();
    let total_metrics = comparisons.len();

    let summary = if all_passed {
        format!("Parity comparison: {passed_metrics}/{total_metrics} metrics passed")
    } else {
        let failing: Vec<String> = comparisons
            .iter()
            .filter(|c| !c.3)
            .map(|c| format!("'{}'", c.0))
            .collect();
        format!(
            "Parity FAILED: {passed_metrics}/{total_metrics} metrics passed. Failing: [{}]",
            failing.join(", ")
        )
    };

    let d = PyDict::new(py);
    d.set_item("passed", all_passed)?;
    let comps = PyList::empty(py);
    for (name, cand, base, passed, detail) in &comparisons {
        let cd = PyDict::new(py);
        cd.set_item("name", name)?;
        cd.set_item("cp_sat_value", cand)?;
        cd.set_item("jax_value", base)?;
        cd.set_item("passed", passed)?;
        cd.set_item("detail", detail)?;
        comps.append(cd)?;
    }
    d.set_item("comparisons", comps)?;
    d.set_item("summary", &summary)?;
    Ok(d.into())
}

/// Register the comparison kernel on the `temper_design_bundle_python` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare_metric_dicts, m)?)?;
    Ok(())
}

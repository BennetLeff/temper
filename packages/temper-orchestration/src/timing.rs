// The numeric compute of `temper_placer/cli/timing.py` (Wave 4, Phase 5).
//
// The pre-migration module computed these INLINE in its click command
// bodies; the delegation shim keeps the full click surface (flags, help,
// exit codes, output text) and calls across the pyo3 boundary here. The
// differential (`tests/cli/test_timing_rust_differential.py`, oracle
// `tests/cli/_timing_py_oracle.py`) extracts the inline expressions
// mechanically and pins bit-identical parity.
//
// Traps pinned (see the differential docstring for the measurement cites):
// - `round(x, 3)` is CPython's decimal round-half-to-even (David Gay dtoa
//   mode 1), NOT `(x * 1000).round_ties_even() / 1000` (double-rounding:
//   measured 494/2M mismatches). `p95` therefore calls Python's `round` for
//   the final step — bit-identical by identity — and does the sort + index
//   selection itself.
// - CPython `sorted()` on floats is a stable sort under `<`, where
//   `-0.0 < 0.0` is False and every NaN comparison is False. `py_cmp` maps
//   non-comparable pairs to `Equal`, which reproduces CPython's placement
//   for finite values, -0.0/+0.0 ties and NaN alike.
// - `max(baseline_ms, floor_ms)` is CPython's `max`, asymmetric on NaN
//   (`max(nan, 1.0)` -> nan, `max(1.0, nan)` -> 1.0). `py_max` reproduces
//   `if b > a { b } else { a }`, NOT `f64::max` (which always returns the
//   non-NaN operand).
// - `baseline_ms > 0` guards the division, so zero/-0.0/NaN baselines land
//   in the `else` arm (delta_pct == 0.0) and the division never executes.
// - The p95 result carries the SELECTED element's Python type: the oracle
//   `round(sorted(values)[...], 3)` returns an int when the selected element
//   is an int (round on an int is the identity), and the shim writes the
//   result into the YAML manifest where `100` and `100.0` render
//   differently. `p95` therefore carries each element as its original
//   Python object and hands the selected one to Python's `round`.

use pyo3::exceptions::PyIndexError;
use pyo3::prelude::*;

/// CPython `max(a, b)` — returns `a` unless `b > a`. Asymmetric on NaN,
/// unlike `f64::max`.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// CPython `sorted()` comparison semantics for floats: `<`-based, where
/// non-comparable pairs (NaN involved) and `-0.0`/`+0.0` ties compare
/// equal, keeping the stable-sort input order.
fn py_cmp(a: &f64, b: &f64) -> std::cmp::Ordering {
    match a.partial_cmp(b) {
        Some(ord) => ord,
        None => std::cmp::Ordering::Equal,
    }
}

/// The `timing_check` stage-comparison block: given a baseline entry and a
/// fresh measurement, compute the delta, delta %, effective baseline
/// (floored), threshold and pass/fail verdict.
///
/// Oracle extraction (pre-migration `timing_check` body):
/// ```python
/// delta_ms = current_ms - baseline_ms
/// delta_pct = (delta_ms / baseline_ms) * 100.0 if baseline_ms > 0 else 0.0
/// effective_baseline = max(baseline_ms, floor_ms)
/// threshold_ms = effective_baseline * (1.0 + margin)
/// passed = current_ms <= threshold_ms
/// ```
#[pyfunction]
pub fn compare_stage(
    baseline_ms: f64,
    current_ms: f64,
    margin: f64,
    floor_ms: f64,
) -> (f64, f64, f64, f64, bool) {
    let delta_ms = current_ms - baseline_ms;
    let delta_pct = if baseline_ms > 0.0 {
        (delta_ms / baseline_ms) * 100.0
    } else {
        0.0
    };
    let effective_baseline = py_max(baseline_ms, floor_ms);
    let threshold_ms = effective_baseline * (1.0 + margin);
    let passed = current_ms <= threshold_ms;
    (delta_ms, delta_pct, effective_baseline, threshold_ms, passed)
}

/// The `wall_ms_p95` expression: `round(sorted(values)[int(len(values) *
/// 0.95)], 3)`.
///
/// The sort and index selection are Rust; the final decimal rounding calls
/// Python's `round` (bit-identical by identity — decimal round-half-to-even
/// is a CPython library semantic, not a double multiply-divide). Each
/// element is carried as its original Python object alongside its f64
/// value, so `round` receives the SELECTED element with its original type:
/// an all-int list yields an int exactly like the oracle (the shim writes
/// the result into the YAML manifest, where `100` vs `100.0` render
/// differently). Values with |x| >= 2^53 sort by their f64 approximation —
/// the same boundary the pre-migration `Vec<f64>` extraction had; arbitrary
/// ints of that magnitude are outside the differential's claimed domain.
/// An empty list raises `IndexError` exactly like the bare expression; the
/// `timing_tighten` call site's `else 0.0` guard for empty qualifying runs
/// lives in the Python shim, not here.
#[pyfunction]
pub fn p95(py: Python<'_>, values: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let mut pairs: Vec<(f64, Py<PyAny>)> = Vec::new();
    for item in values.try_iter()? {
        let item = item?;
        let f = item.extract::<f64>()?;
        pairs.push((f, item.unbind()));
    }
    pairs.sort_by(|a, b| py_cmp(&a.0, &b.0));
    let idx = (pairs.len() as f64 * 0.95) as usize;
    let (_, selected) = pairs
        .get(idx)
        .ok_or_else(|| PyIndexError::new_err("list index out of range"))?;
    let builtins = py.import("builtins")?;
    let rounded = builtins.getattr("round")?.call1((selected, 3))?;
    Ok(rounded.unbind())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_max_asymmetric_on_nan() {
        let nan = f64::NAN;
        assert!(py_max(nan, 1.0).is_nan());
        assert_eq!(py_max(1.0, nan), 1.0);
        assert_eq!(py_max(2.0, 1.0), 2.0);
        assert_eq!(py_max(1.0, 2.0), 2.0);
    }

    #[test]
    fn py_cmp_nan_is_equal() {
        assert_eq!(py_cmp(&f64::NAN, &1.0), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&1.0, &f64::NAN), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&f64::NAN, &f64::NAN), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&0.0, &-0.0), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&-1.0, &1.0), std::cmp::Ordering::Less);
    }

    #[test]
    fn compare_stage_guards_zero_baseline() {
        // delta_pct == 0.0 for zero / -0.0 / NaN baselines; no division.
        let (_, pct, _, _, _) = compare_stage(0.0, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
        let (_, pct, _, _, _) = compare_stage(-0.0, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
        let (_, pct, _, _, _) = compare_stage(f64::NAN, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
    }
}

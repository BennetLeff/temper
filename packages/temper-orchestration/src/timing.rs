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

#[cfg(feature = "python")]
use pyo3::exceptions::PyIndexError;
#[cfg(feature = "python")]
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
#[cfg_attr(feature = "python", pyfunction)]
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

#[cfg(feature = "python")]
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
    let mut pairs: Vec<(f64, Py<PyAny>)> =
        Vec::with_capacity(values.len()?);
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn py_max_asymmetric_on_nan() {
        let nan = f64::NAN;
        assert!(py_max(nan, 1.0).is_nan());
        assert_eq!(py_max(1.0, nan), 1.0);
        assert_eq!(py_max(2.0, 1.0), 2.0);
        assert_eq!(py_max(1.0, 2.0), 2.0);
    }

    #[cfg_attr(test, test)]
    fn py_cmp_nan_is_equal() {
        assert_eq!(py_cmp(&f64::NAN, &1.0), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&1.0, &f64::NAN), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&f64::NAN, &f64::NAN), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&0.0, &-0.0), std::cmp::Ordering::Equal);
        assert_eq!(py_cmp(&-1.0, &1.0), std::cmp::Ordering::Less);
    }

    #[cfg_attr(test, test)]
    fn compare_stage_guards_zero_baseline() {
        // delta_pct == 0.0 for zero / -0.0 / NaN baselines; no division.
        let (_, pct, _, _, _) = compare_stage(0.0, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
        let (_, pct, _, _, _) = compare_stage(-0.0, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
        let (_, pct, _, _, _) = compare_stage(f64::NAN, 5.0, 0.20, 10.0);
        assert_eq!(pct, 0.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("timing::tests::py_max_asymmetric_on_nan", py_max_asymmetric_on_nan),
        ("timing::tests::py_cmp_nan_is_equal", py_cmp_nan_is_equal),
        ("timing::tests::compare_stage_guards_zero_baseline", compare_stage_guards_zero_baseline),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal_f64() -> impl Strategy<Value = f64> {
        prop::num::f64::NORMAL
    }

    fn positive_f64() -> impl Strategy<Value = f64> {
        (0.0f64..1e6).prop_filter("avoid subnormals near zero", |x| x.is_normal() || *x == 0.0)
    }

    proptest! {
        // -----------------------------------------------------------------
        // py_max
        // -----------------------------------------------------------------

        /// P1. For non-NaN values, py_max returns the conventional maximum.
        #[test]
        fn p1_py_max_returns_larger(a in normal_f64(), b in normal_f64()) {
            let r = py_max(a, b);
            let expected = a.max(b);
            prop_assert_eq!(r, expected,
                "py_max({},{})={} != f64::max={}", a, b, r, expected);
        }

        /// P2. py_max returns one of its two arguments (bit-exact identity).
        #[test]
        fn p2_py_max_returns_one_of_inputs(a in normal_f64(), b in normal_f64()) {
            let r = py_max(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(),
                "py_max({},{})={} is neither a nor b", a, b, r);
        }

        /// P3. py_max is commutative for non-NaN inputs.
        #[test]
        fn p3_py_max_commutative(a in normal_f64(), b in normal_f64()) {
            prop_assert_eq!(py_max(a, b), py_max(b, a));
        }

        // -----------------------------------------------------------------
        // py_cmp
        // -----------------------------------------------------------------

        /// P4. py_cmp is reflexive: py_cmp(x, x) == Equal.
        #[test]
        fn p4_py_cmp_reflexive(a in normal_f64()) {
            prop_assert_eq!(py_cmp(&a, &a), std::cmp::Ordering::Equal);
        }

        /// P5. py_cmp is anti-symmetric for distinct non-NaN values:
        /// cmp(a,b) is the reverse of cmp(b,a).
        #[test]
        fn p5_py_cmp_antisymmetric(a in normal_f64(), b in normal_f64()) {
            prop_assume!(a != b);
            let ab = py_cmp(&a, &b);
            let ba = py_cmp(&b, &a);
            if a < b {
                prop_assert_eq!(ab, std::cmp::Ordering::Less);
                prop_assert_eq!(ba, std::cmp::Ordering::Greater);
            } else {
                prop_assert_eq!(ab, std::cmp::Ordering::Greater);
                prop_assert_eq!(ba, std::cmp::Ordering::Less);
            }
        }

        /// P6. py_cmp is transitive: if a < b and b < c then a < c.
        ///
        /// We generate ordered triples directly by drawing a base value
        /// and two positive deltas. Base is kept modest to avoid
        /// overflow when adding deltas.
        #[test]
        fn p6_py_cmp_transitive(
            a in (-1e6f64..1e6),
            delta1 in (1e-3f64..1e3),
            delta2 in (1e-3f64..1e3),
        ) {
            prop_assume!(a.is_normal() || a == 0.0);
            let b = a + delta1;
            let c = b + delta2;
            prop_assume!(b.is_finite() && c.is_finite() && b > a && c > b);
            prop_assert_eq!(py_cmp(&a, &b), std::cmp::Ordering::Less);
            prop_assert_eq!(py_cmp(&b, &c), std::cmp::Ordering::Less);
            prop_assert_eq!(py_cmp(&a, &c), std::cmp::Ordering::Less);
        }

        // -----------------------------------------------------------------
        // compare_stage
        // -----------------------------------------------------------------

        /// P7. compare_stage: when current == baseline, delta_ms == 0.0 and
        /// delta_pct == 0.0.
        #[test]
        fn p7_compare_stage_zero_delta_at_parity(
            baseline in positive_f64(),
            margin in 0.01f64..1.0,
            floor in 0.0f64..100.0,
        ) {
            let (delta_ms, delta_pct, _, _, _) =
                compare_stage(baseline, baseline, margin, floor);
            prop_assert_eq!(delta_ms, 0.0);
            prop_assert_eq!(delta_pct, 0.0);
        }

        /// P8. compare_stage: when current > baseline, delta_pct is positive.
        /// (Except when baseline <= 0.0, which triggers the zero guard.)
        #[test]
        fn p8_compare_stage_positive_delta_pct_for_regression(
            baseline in 1.0f64..1000.0,
            excess in 0.1f64..500.0,
            margin in 0.01f64..1.0,
            floor in 0.0f64..100.0,
        ) {
            let current = baseline + excess;
            let (delta_ms, delta_pct, _, _, _) =
                compare_stage(baseline, current, margin, floor);
            prop_assert!(delta_ms > 0.0);
            prop_assert!(delta_pct > 0.0,
                "delta_pct should be positive: baseline={}, current={}, delta_ms={}, delta_pct={}",
                baseline, current, delta_ms, delta_pct);
        }

        /// P9. compare_stage: effective_baseline >= floor_ms (the floor is
        /// a lower bound).
        #[test]
        fn p9_compare_stage_effective_baseline_at_least_floor(
            baseline in normal_f64(),
            current in normal_f64(),
            margin in 0.01f64..1.0,
            floor in 0.0f64..1000.0,
        ) {
            let (_, _, effective, _, _) =
                compare_stage(baseline, current, margin, floor);
            prop_assert!(effective >= floor,
                "effective baseline {} < floor {}", effective, floor);
        }

        /// P10. compare_stage: margin 0.0 means threshold == effective_baseline,
        /// so passed is true exactly when current <= effective_baseline.
        #[test]
        fn p10_compare_stage_zero_margin_exact_threshold(
            baseline in positive_f64(),
            current in positive_f64(),
            floor in 0.0f64..100.0,
        ) {
            let (_, _, effective, threshold, passed) =
                compare_stage(baseline, current, 0.0, floor);
            prop_assert_eq!(threshold, effective,
                "threshold should equal effective_baseline at margin=0");
            prop_assert_eq!(passed, current <= effective,
                "passed should be current <= effective at margin=0");
        }
    }
}

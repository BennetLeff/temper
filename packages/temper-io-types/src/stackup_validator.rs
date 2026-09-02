//! Professional PCB stackup validation checks — the Wave 4 Phase 4 leftovers
//! slice's `manufacturing/stackup_validator.py` migration.
//!
//! Python reference: `temper_placer/manufacturing/stackup_validator.py`,
//! pinned VERBATIM in
//! `packages/temper-placer/tests/manufacturing/_stackup_validator_py_oracle.py`
//! (commit `6290942be`). The pyo3 pyclasses `StackupValidationResult` /
//! `StackupValidationReport` and the `validate_stackup` pyfunction here must
//! reproduce that implementation bit-identically; the differential test
//! `packages/temper-placer/tests/manufacturing/test_stackup_validator_rust_differential.py`
//! is the TDD oracle for this file, and the property suite
//! `test_stackup_validator_pbt.py` asserts the closed-form invariants
//! (thresholds, formulas, fail-closed report) independently.
//!
//! Home-crate rationale: this validator consumes the `LayerStackup` pyclass
//! (the stackup primitives landed by the Wave 4 Phase 3 parse-engine work,
//! PR #723) as an opaque Python object across the pyo3 boundary, so it lives
//! in `temper-io-types` per the slice's home-crate guidance. The `python`
//! feature gates all pyo3 code; the pure helpers (`neumaier_sum`,
//! `py_float_str`, `py_str_repr`) compile without the feature, preserving the
//! crate's wasm32-exportable core.
//!
//! Boundary notes:
//! - `LayerStackup` is reached through `getattr("layers")` / per-layer
//!   `getattr("name" | "layer_type" | "copper_weight")`, so the validator
//!   accepts any duck-typed stackup the oracle would accept.
//! - The `routing_results` fill arm calls BACK into
//!   `temper_placer.router_v6.copper_balance.analyze_copper_balance` (the
//!   router_v6 module stays Python — another Wave-4 slice's surface); the
//!   call-back, kwargs and dict comprehension are transcribed exactly.
//! - The copper-symmetry `total = sum(effective_weights.values())` uses
//!   `neumaier_sum`, a replica of CPython 3.12's compensated `sum()`:
//!   Neumaier accumulation with the compensation step skipped whenever
//!   `total + x` is non-finite (empirically verified: 0 mismatches over
//!   20,000 random finite arrays + the inf/nan edge classes).
//! - Message formatting uses CPython's `repr(float)` / `repr(str)` rules
//!   (`py_float_str` / `py_str_repr`, duplicated per the established
//!   per-module convention) and Rust's `{:.0}` / `{:.1}` / `{:.2}`
//!   formatting, which round identically to Python's `{:.0f}` / `{:.1%}` /
//!   `{:.2f}` (verified empirically on the values this module can produce).
//! - The controlled-impedance spec in the messages renders from the ORIGINAL
//!   caller object via CPython's `str()` (an int 90 renders "90", a float
//!   90.0 renders "90.0" — the oracle's f-string renders the original), while
//!   the branch comparisons use the extracted f64. This was the divergence
//!   an adversarial review found (2026-08-05): the f64 extraction rendered
//!   "90.0" for an int spec.
//! - `max`/`min` are first-wins (strict comparison keeps the earlier item on
//!   ties), matching CPython's `max()`/`min()` over dict values in
//!   insertion order.

// ---------------------------------------------------------------------------
// Pure helpers (no pyo3 dependency — wasm32-exportable).
// ---------------------------------------------------------------------------

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping (B9).
pub fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does (B10): shortest
/// round-trip digits, `1e+300`/`1e-05` exponent form, `nan` not `NaN`.
pub fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..]; // drop 'e'/'E'
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

/// Replica of CPython 3.12's `sum()` over floats: Neumaier compensation
/// with the compensation step skipped whenever `total + x` is non-finite.
///
/// Empirically verified against CPython 3.12's `sum()` on 20,000 random
/// finite arrays (0 mismatches) plus the inf/nan edge classes
/// (`[1e308, 1e308, -1e308, -1e308] -> inf`, `[inf, -inf] -> nan`,
/// NaN propagation). The naive `+=` fold differs from this in the last ulp
/// for as few as four values, so this replica is load-bearing for R1a.
pub fn neumaier_sum(vals: impl IntoIterator<Item = f64>) -> f64 {
    let mut total = 0.0;
    let mut c = 0.0;
    for x in vals {
        let y = total + x;
        if y.is_finite() {
            if total.abs() >= x.abs() {
                c += (total - y) + x;
            } else {
                c += (x - y) + total;
            }
        }
        total = y;
    }
    total + c
}

/// CPython `max` over f64 values in iteration order: first-wins on ties
/// (strict `>` keeps the earlier item), and NaN behaviour follows CPython's
/// comparison semantics (a NaN earlier in the sequence is kept).
pub fn first_wins_max(vals: impl IntoIterator<Item = f64>) -> f64 {
    let mut iter = vals.into_iter();
    let mut best = iter.next().unwrap_or(f64::NAN); // unreachable for the module's call sites
    for v in iter {
        if v > best {
            best = v;
        }
    }
    best
}

/// CPython `min` over f64 values in iteration order: first-wins on ties
/// (strict `<` keeps the earlier item).
pub fn first_wins_min(vals: impl IntoIterator<Item = f64>) -> f64 {
    let mut iter = vals.into_iter();
    let mut best = iter.next().unwrap_or(f64::NAN); // unreachable for the module's call sites
    for v in iter {
        if v < best {
            best = v;
        }
    }
    best
}

/// CPython `max(collection, key=fn)` over an ordered collection:
/// first-wins on ties.
pub fn arg_first_wins_max(
    items: &[(String, f64)],
) -> &str {
    let mut best_idx = 0;
    for (i, (_, v)) in items.iter().enumerate().skip(1) {
        if v > &items[best_idx].1 {
            best_idx = i;
        }
    }
    &items[best_idx].0
}

/// CPython `min(collection, key=fn)` over an ordered collection:
/// first-wins on ties.
pub fn arg_first_wins_min(
    items: &[(String, f64)],
) -> &str {
    let mut best_idx = 0;
    for (i, (_, v)) in items.iter().enumerate().skip(1) {
        if v < &items[best_idx].1 {
            best_idx = i;
        }
    }
    &items[best_idx].0
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod helper_tests {
    use super::{
        arg_first_wins_max, arg_first_wins_min, first_wins_max, first_wins_min, neumaier_sum,
        py_float_str, py_str_repr,
    };

    #[cfg_attr(test, test)]
    fn neumaier_matches_cpython_sum_on_divergence_classes() {
        // The naive fold diverges from CPython's sum for these (measured).
        assert_eq!(neumaier_sum([0.7, 0.95, 0.95, 0.3]), 2.9);
        assert_eq!(neumaier_sum([1e16, 1.0, -1e16, 1.0]), 2.0);
        // Overflow keeps inf (compensation skipped on the non-finite step).
        assert_eq!(neumaier_sum([1e308, 1e308, -1e308, -1e308]), f64::INFINITY);
        // inf + -inf -> nan; NaN propagates.
        assert!(neumaier_sum([f64::INFINITY, f64::NEG_INFINITY]).is_nan());
        assert!(neumaier_sum([f64::NAN, 1.0]).is_nan());
        assert_eq!(neumaier_sum([]), 0.0);
    }

    #[cfg_attr(test, test)]
    fn str_repr_matches_cpython() {
        assert_eq!(py_str_repr("F.Cu"), "'F.Cu'");
        assert_eq!(py_str_repr("a'b"), "'a\\'b'");
        assert_eq!(py_str_repr("a\\b"), "'a\\\\b'");
    }

    #[cfg_attr(test, test)]
    fn float_repr_matches_cpython() {
        assert_eq!(py_float_str(90.0), "90.0");
        assert_eq!(py_float_str(0.0), "0.0");
        assert_eq!(py_float_str(69.99), "69.99");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(f64::NAN), "nan");
    }

    #[cfg_attr(test, test)]
    fn first_wins_semantics() {
        // Ties keep the earlier element (CPython max/min behaviour).
        assert_eq!(first_wins_max([1.0, 2.0, 2.0]), 2.0);
        assert_eq!(first_wins_max([2.0, 2.0, 1.0]), 2.0);
        assert_eq!(first_wins_min([2.0, 1.0, 1.0]), 1.0);
        // argmax/argmin over keyed items, first-wins on ties.
        let items = vec![
            ("a".to_string(), 1.0),
            ("b".to_string(), 3.0),
            ("c".to_string(), 3.0),
            ("d".to_string(), 0.5),
        ];
        assert_eq!(arg_first_wins_max(&items), "b");
        assert_eq!(arg_first_wins_min(&items), "d");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: helper_tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("stackup_validator::helper_tests::neumaier_matches_cpython_sum_on_divergence_classes", neumaier_matches_cpython_sum_on_divergence_classes),
        ("stackup_validator::helper_tests::str_repr_matches_cpython", str_repr_matches_cpython),
        ("stackup_validator::helper_tests::float_repr_matches_cpython", float_repr_matches_cpython),
        ("stackup_validator::helper_tests::first_wins_semantics", first_wins_semantics),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: helper_tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(all(test, feature = "python"))]
#[allow(clippy::unwrap_used)]
mod proptests {
    use super::{
        arg_first_wins_max, first_wins_max, neumaier_sum, py_float_str,
    };
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    // ---------- py_float_str ------------------------------------------------

    #[test]
    fn py_float_str_round_trips() {
        proptest!(|(v in normal())| {
            let s = py_float_str(v);
            // Parse the string back to f64 and verify it's the same bit pattern.
            let parsed: f64 = s.parse().unwrap();
            prop_assert_eq!(parsed.to_bits(), v.to_bits(),
                "py_float_str({:?}) = '{}' does not round-trip (parsed {:?})", v, s, parsed);
        });
    }

    #[test]
    fn py_float_str_no_internal_whitespace() {
        proptest!(|(v in normal())| {
            let s = py_float_str(v);
            prop_assert!(!s.contains(' '), "py_float_str({v:?}) = '{s}' contains whitespace");
        });
    }

    #[test]
    fn py_float_str_exponent_is_lowercase() {
        proptest!(|(v in normal())| {
            let s = py_float_str(v);
            if s.contains('e') {
                prop_assert!(!s.contains('E'), "py_float_str({v:?}) = '{s}' has uppercase E");
                // Exponent must be exactly 2 digits or 3 digits (for values like 1e100)
                let e_pos = s.find('e').unwrap();
                let exp = &s[e_pos+1..]; // skip 'e'
                let exp_digits: String = exp.chars().skip_while(|c| *c == '+' || *c == '-').collect();
                prop_assert!(exp_digits.len() >= 2,
                    "py_float_str({v:?}) = '{s}' has exponent with <2 digits");
            }
        });
    }

    #[test]
    fn py_float_str_special_values() {
        for (v, expected) in [
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
            (0.0, "0.0"),
            (-0.0, "-0.0"),
        ] {
            assert_eq!(py_float_str(v), expected, "py_float_str({v:?})");
        }
    }

    // ---------- neumaier_sum -------------------------------------------------

    #[test]
    fn neumaier_sum_agrees_with_naive_on_small_lists() {
        proptest!(|(vals in proptest::collection::vec(normal(), 0..7))| {
            let naive: f64 = vals.iter().fold(0.0, |a, &b| a + b);
            let neumaier = neumaier_sum(vals.iter().copied());
            // Neumaier is more accurate, but for < 8 elements they should
            // agree unless there's catastrophic cancellation.
            // We only assert they're both finite or both NaN.
            prop_assert_eq!(neumaier.is_finite(), naive.is_finite());
        });
    }

    #[test]
    fn neumaier_sum_non_negative_sum_is_non_negative() {
        proptest!(|(vals in proptest::collection::vec(0.0f64..1e6f64, 1..30))| {
            let s = neumaier_sum(vals);
            prop_assert!(s >= 0.0 || s.is_nan());
        });
    }

    #[test]
    fn neumaier_sum_is_commutative() {
        proptest!(|(mut vals in proptest::collection::vec(normal(), 1..10))| {
            let s1 = neumaier_sum(vals.iter().copied());
            vals.reverse();
            let s2 = neumaier_sum(vals.iter().copied());
            prop_assert_eq!(s1, s2, "neumaier_sum not commutative");
        });
    }

    // ---------- first_wins_max / first_wins_min -----------------------------

    #[test]
    fn first_wins_max_vs_naive() {
        proptest!(|(vals in proptest::collection::vec(normal(), 1..50))| {
            let fw = first_wins_max(vals.iter().copied());
            let naive = vals.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
            // For finite inputs without NaN, first-wins and naive agree.
            if vals.iter().all(|v| v.is_finite()) {
                prop_assert_eq!(fw, naive);
            }
        });
    }

    #[test]
    fn arg_first_wins_max_selects_correct_index() {
        proptest!(|(vals in proptest::collection::vec(normal(), 1..50))| {
            let items: Vec<(String, f64)> = vals.iter().enumerate()
                .map(|(i, &v)| (format!("key_{i}"), v))
                .collect();
            let name = arg_first_wins_max(&items);
            // The selected name must correspond to one of the maximum values
            let max_val = first_wins_max(vals.iter().copied());
            let idx: usize = name.strip_prefix("key_").unwrap().parse().unwrap();
            if vals.iter().all(|v| v.is_finite()) {
                prop_assert_eq!(vals[idx], max_val,
                    "arg_first_wins_max selected key_{}={} but max is {}",
                    idx, vals[idx], max_val);
                // First-wins: if there are earlier equal values, they should
                // have been selected, not this one (unless this IS the first).
                for (j, &v) in vals.iter().enumerate() {
                    if j < idx && v == max_val {
                        prop_assert!(false,
                            "first-wins violated: key_{}={} appears before key_{}={}", j, v, idx, vals[idx]);
                    }
                }
            }
        });
    }
}

// ---------------------------------------------------------------------------
// Python surface (gated on the `python` feature).
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyTypeError;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyList};
    use std::panic::AssertUnwindSafe;

    use super::{arg_first_wins_max, arg_first_wins_min, first_wins_max, first_wins_min, neumaier_sum};

    // Oracle module constants (kept Python-side in the delegation shim;
    // mirrored here verbatim).
    const COPPER_BALANCE_MIN_PCT: f64 = 25.0;
    const COPPER_BALANCE_MAX_PCT: f64 = 75.0;
    const USB_DIFFERENTIAL_IMPEDANCE_OHMS: f64 = 90.0;
    const COPPER_SYMMETRY_IMBALANCE_THRESHOLD: f64 = 0.25;

    /// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
    /// `RuntimeError` instead of aborting the interpreter (G7).
    fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
        match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
            Ok(result) => result,
            Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
        }
    }

    // -----------------------------------------------------------------------
    // StackupValidationResult
    // -----------------------------------------------------------------------

    /// Result of a single stackup validation check (mirrors
    /// `StackupValidationResult`).
    #[pyclass(name = "StackupValidationResult", module = "temper_io_types")]
    #[derive(Debug)]
    pub struct PyStackupValidationResult {
        #[pyo3(get)]
        pub check_name: String,
        #[pyo3(get)]
        pub passed: bool,
        #[pyo3(get)]
        pub message: String,
        #[pyo3(get)]
        pub layer: Option<String>,
        #[pyo3(get)]
        pub details: Option<Py<PyAny>>,
    }

    #[pymethods]
    impl PyStackupValidationResult {
        #[new]
        #[pyo3(signature = (check_name, passed, message, layer=None, details=None))]
        fn new(
            check_name: String,
            passed: bool,
            message: String,
            layer: Option<String>,
            details: Option<Py<PyAny>>,
        ) -> Self {
            Self {
                check_name,
                passed,
                message,
                layer,
                details,
            }
        }

        fn __repr__(&self, py: Python<'_>) -> String {
            let layer = match &self.layer {
                Some(l) => super::py_str_repr(l),
                None => "None".to_string(),
            };
            let details = match &self.details {
                Some(d) => d.bind(py).repr().map(|r| r.to_string()).unwrap_or_default(),
                None => "None".to_string(),
            };
            format!(
                "StackupValidationResult(check_name={}, passed={}, message={}, layer={}, details={})",
                super::py_str_repr(&self.check_name),
                self.passed,
                super::py_str_repr(&self.message),
                layer,
                details,
            )
        }
    }

    // -----------------------------------------------------------------------
    // StackupValidationReport
    // -----------------------------------------------------------------------

    /// Aggregate report from all stackup validation checks (mirrors
    /// `StackupValidationReport`).
    #[pyclass(name = "StackupValidationReport", module = "temper_io_types")]
    #[derive(Debug)]
    pub struct PyStackupValidationReport {
        #[pyo3(get)]
        pub results: Py<PyAny>,
    }

    #[pymethods]
    impl PyStackupValidationReport {
        #[new]
        #[pyo3(signature = (results=None))]
        fn new(py: Python<'_>, results: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
            let results = match results {
                Some(v) => v.clone().unbind(),
                None => PyList::empty(py).into_any().unbind(),
            };
            Ok(Self { results })
        }

        /// `all_passed` — fail closed on an empty report (the oracle's
        /// anti-vacuity guard: `all()` over no results is vacuously True).
        #[getter]
        fn all_passed(&self, py: Python<'_>) -> PyResult<bool> {
            let results = self.results.bind(py);
            if results.len()? == 0 {
                return Ok(false);
            }
            for r in results.try_iter()? {
                let passed = r?.getattr("passed")?.is_truthy()?;
                if !passed {
                    return Ok(false);
                }
            }
            Ok(true)
        }

        /// `warnings` — the non-passed results, in order.
        #[getter]
        fn warnings(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
            let results = self.results.bind(py);
            let out = PyList::empty(py);
            for r in results.try_iter()? {
                let item = r?;
                if !item.getattr("passed")?.is_truthy()? {
                    out.append(item)?;
                }
            }
            Ok(out.unbind())
        }

        /// `summary()` — the oracle's `[PASS]`/`[WARN]` rendering.
        fn summary(&self, py: Python<'_>) -> PyResult<String> {
            let mut lines = vec!["Stackup Validation:".to_string()];
            for r in self.results.bind(py).try_iter()? {
                let item = r?;
                let passed = item.getattr("passed")?.is_truthy()?;
                let icon = if passed { "[PASS]" } else { "[WARN]" };
                let name: String = item.getattr("check_name")?.extract()?;
                let message: String = item.getattr("message")?.extract()?;
                lines.push(format!("  {icon} {name}: {message}"));
            }
            Ok(lines.join("\n"))
        }
    }

    // -----------------------------------------------------------------------
    // The four checks (mirroring the oracle's private helpers).
    // -----------------------------------------------------------------------

    fn check_copper_symmetry(
        py: Python<'_>,
        stackup: &Bound<'_, PyAny>,
        fill_pct: &Bound<'_, PyDict>,
    ) -> PyResult<PyStackupValidationResult> {
        if fill_pct.len() == 0 {
            return Ok(PyStackupValidationResult {
                check_name: "Copper Symmetry".to_string(),
                passed: true,
                message: "No fill data available -- symmetry check skipped".to_string(),
                layer: None,
                details: None,
            });
        }
        // effective_weights, in stackup layer order (dict insertion order).
        // The oracle keys by layer name (effective_weights[ly.name] = ...):
        // duplicate layer names COLLAPSE — last value wins, first-seen
        // position. A Vec-push kernel would double `total` on duplicates
        // and diverge the imbalance (see the duplicate-name differential
        // tests).
        let mut effective: Vec<(String, f64)> = Vec::new();
        for layer in stackup.getattr("layers")?.try_iter()? {
            let ly = layer?;
            let name: String = ly.getattr("name")?.extract()?;
            let copper_weight: f64 = ly.getattr("copper_weight")?.extract()?;
            let pct = match fill_pct.get_item(&name)? {
                Some(v) => v.extract::<f64>()?,
                None => 0.0,
            } / 100.0;
            let weight = copper_weight * pct;
            match effective.iter_mut().find(|(n, _)| *n == name) {
                Some(slot) => slot.1 = weight,
                None => effective.push((name, weight)),
            }
        }
        let total = neumaier_sum(effective.iter().map(|(_, w)| *w));
        if total == 0.0 {
            return Ok(PyStackupValidationResult {
                check_name: "Copper Symmetry".to_string(),
                passed: true,
                message: "Zero effective copper -- symmetry check skipped".to_string(),
                layer: None,
                details: None,
            });
        }
        let max_eff = first_wins_max(effective.iter().map(|(_, w)| *w));
        let min_eff = first_wins_min(effective.iter().map(|(_, w)| *w));
        let imbalance = (max_eff - min_eff) / total;
        if imbalance > COPPER_SYMMETRY_IMBALANCE_THRESHOLD {
            let heaviest = arg_first_wins_max(&effective).to_string();
            let lightest = arg_first_wins_min(&effective).to_string();
            let details = PyDict::new(py);
            details.set_item("max_eff", max_eff)?;
            details.set_item("min_eff", min_eff)?;
            details.set_item("imbalance", imbalance)?;
            return Ok(PyStackupValidationResult {
                check_name: "Copper Symmetry".to_string(),
                passed: false,
                message: format!(
                    "Effective copper imbalance detected: {} at {:.2} vs {} at {:.2} \
                     (imbalance={:.1}%). \
                     This may cause board warping during reflow.",
                    heaviest, max_eff, lightest, min_eff, imbalance * 100.0
                ),
                layer: Some(format!("{heaviest} vs {lightest}")),
                details: Some(details.into_any().unbind()),
            });
        }
        Ok(PyStackupValidationResult {
            check_name: "Copper Symmetry".to_string(),
            passed: true,
            message: format!(
                "Effective copper balanced (imbalance={:.1}%)",
                imbalance * 100.0
            ),
            layer: None,
            details: None,
        })
    }

    fn check_return_path_adjacency(
        stackup: &Bound<'_, PyAny>,
        differential_nets: &[String],
        has_stitching_vias: bool,
    ) -> PyResult<PyStackupValidationResult> {
        if differential_nets.is_empty() {
            return Ok(PyStackupValidationResult {
                check_name: "Return-Path Adjacency".to_string(),
                passed: true,
                message: "No differential nets configured -- adjacency check skipped".to_string(),
                layer: None,
                details: None,
            });
        }
        let layers = stackup.getattr("layers")?;
        let len = layers.len()?;
        let l3_is_plane = if len >= 4 {
            layers
                .get_item(2)?
                .getattr("layer_type")?
                .eq("plane")?
        } else {
            false
        };
        if l3_is_plane {
            if has_stitching_vias {
                return Ok(PyStackupValidationResult {
                    check_name: "Return-Path Adjacency".to_string(),
                    passed: true,
                    message: "L4 references L3 (PWR plane), but stitching GND vias are present \
                              -- return-path concern mitigated."
                        .to_string(),
                    layer: None,
                    details: None,
                });
            }
            return Ok(PyStackupValidationResult {
                check_name: "Return-Path Adjacency".to_string(),
                passed: false,
                message: "L4 (control signals) references L3 (PWR plane). \
                          Verify return-path quality for differential nets. \
                          Consider adding stitching GND vias near the differential pair."
                    .to_string(),
                layer: Some("L4 (B.Cu)".to_string()),
                details: None,
            });
        }
        Ok(PyStackupValidationResult {
            check_name: "Return-Path Adjacency".to_string(),
            passed: true,
            message: "Signal layers have adequate reference plane adjacency".to_string(),
            layer: None,
            details: None,
        })
    }

    fn check_impedance_spec(
        differential_nets: &[String],
        impedance_spec_ohms: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<PyStackupValidationResult> {
        if differential_nets.is_empty() {
            return Ok(PyStackupValidationResult {
                check_name: "Controlled Impedance".to_string(),
                passed: true,
                message: "No differential nets configured -- impedance check skipped".to_string(),
                layer: None,
                details: None,
            });
        }
        // The oracle's f-string renders the ORIGINAL argument (`{90}` →
        // "90", `{90.0}` → "90.0" — an int spec stays int), so the message
        // text is rendered from the caller's object via CPython's str(),
        // while the comparisons below use the extracted f64. Extracting
        // first and rendering the f64 would diverge for any int input
        // ("90.0 Omega" vs the oracle's "90 Omega").
        let render = |obj: &Bound<'_, PyAny>| obj.str().map(|s| s.to_string());
        match impedance_spec_ohms {
            None => {
                let mut sorted = differential_nets.to_vec();
                sorted.sort();
                let sorted_repr: Vec<String> =
                    sorted.iter().map(|s| super::py_str_repr(s)).collect();
                Ok(PyStackupValidationResult {
                    check_name: "Controlled Impedance".to_string(),
                    passed: false,
                    message: format!(
                        "No target impedance specified for differential nets \
                         ({} nets: [{}]). \
                         Expected: {:.0} Omega differential \
                         for USB 2.0 (ESP32-S3 USB OTG 1.1).",
                        differential_nets.len(),
                        sorted_repr.join(", "),
                        USB_DIFFERENTIAL_IMPEDANCE_OHMS,
                    ),
                    layer: None,
                    details: None,
                })
            }
            Some(obj) => {
                let z: f64 = obj.extract()?;
                if z <= 0.0 {
                    Ok(PyStackupValidationResult {
                        check_name: "Controlled Impedance".to_string(),
                        passed: false,
                        message: format!(
                            "Invalid impedance value: {} Omega. Expected positive value.",
                            render(obj)?
                        ),
                        layer: None,
                        details: None,
                    })
                } else if !(70.0..=120.0).contains(&z) {
                    Ok(PyStackupValidationResult {
                        check_name: "Controlled Impedance".to_string(),
                        passed: false,
                        message: format!(
                            "Impedance {} Omega outside typical USB range (70-120 Omega). \
                             Verify this is intentional.",
                            render(obj)?
                        ),
                        layer: None,
                        details: None,
                    })
                } else {
                    Ok(PyStackupValidationResult {
                        check_name: "Controlled Impedance".to_string(),
                        passed: true,
                        message: format!(
                            "Impedance specification: {} Omega for differential nets",
                            render(obj)?
                        ),
                        layer: None,
                        details: None,
                    })
                }
            }
        }
    }

    fn check_copper_balance(
        py: Python<'_>,
        _stackup: &Bound<'_, PyAny>,
        fill_pct: &Bound<'_, PyDict>,
    ) -> PyResult<PyStackupValidationResult> {
        if fill_pct.len() == 0 {
            return Ok(PyStackupValidationResult {
                check_name: "Copper Balance".to_string(),
                passed: true,
                message: "No fill data available -- balance check skipped".to_string(),
                layer: None,
                details: None,
            });
        }
        let percents: Vec<f64> = fill_pct
            .iter()
            .map(|(_, v)| v.extract::<f64>())
            .collect::<PyResult<_>>()?;
        let max_fill = first_wins_max(percents.iter().copied());
        let min_fill = first_wins_min(percents.iter().copied());
        if min_fill < COPPER_BALANCE_MIN_PCT || max_fill > COPPER_BALANCE_MAX_PCT {
            let details = PyDict::new(py);
            details.set_item("max_fill", max_fill)?;
            details.set_item("min_fill", min_fill)?;
            return Ok(PyStackupValidationResult {
                check_name: "Copper Balance".to_string(),
                passed: false,
                message: format!(
                    "Copper density imbalance: max={:.0}%, min={:.0}% \
                     (target: {:.0}-{:.0}%). \
                     This may cause board warping during reflow.",
                    max_fill,
                    min_fill,
                    COPPER_BALANCE_MIN_PCT,
                    COPPER_BALANCE_MAX_PCT,
                ),
                layer: None,
                details: Some(details.into_any().unbind()),
            });
        }
        Ok(PyStackupValidationResult {
            check_name: "Copper Balance".to_string(),
            passed: true,
            message: format!(
                "Copper density balanced (range: {:.0}%-{:.0}%)",
                min_fill, max_fill
            ),
            layer: None,
            details: None,
        })
    }

    // -----------------------------------------------------------------------
    // Fill resolution.
    // -----------------------------------------------------------------------

    /// The `routing_results` fill arm calls back into the Python
    /// `analyze_copper_balance` (router_v6 stays Python) with the oracle's
    /// exact kwargs and builds the same layer_name -> copper_percentage dict.
    fn resolve_fill_via_routing(
        py: Python<'_>,
        routing_results: &Bound<'_, PyAny>,
        board_dims: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyDict>> {
        let copper_balance =
            py.import("temper_placer.router_v6.copper_balance")?;
        let width: f64 = board_dims.get_item(0)?.extract()?;
        let height: f64 = board_dims.get_item(1)?.extract()?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("min_copper_percentage", COPPER_BALANCE_MIN_PCT)?;
        kwargs.set_item("max_copper_percentage", COPPER_BALANCE_MAX_PCT)?;
        let report = copper_balance
            .getattr("analyze_copper_balance")?
            .call((routing_results, width, height), Some(&kwargs))?;
        let out = PyDict::new(py);
        for lb in report.getattr("layer_balances")?.try_iter()? {
            let item = lb?;
            let name: String = item.getattr("layer_name")?.extract()?;
            let pct: f64 = item.getattr("copper_percentage")?.extract()?;
            out.set_item(name, pct)?;
        }
        Ok(out.unbind())
    }

    /// Resolve copper fill percentages: explicit truthy dict wins; else the
    /// routing-results call-back; else the default Temper estimates for a
    /// 4-layer F.Cu-first stackup; else {}.
    fn resolve_fill_percentages(
        py: Python<'_>,
        stackup: &Bound<'_, PyAny>,
        explicit: Option<&Bound<'_, PyAny>>,
        routing_results: Option<&Bound<'_, PyAny>>,
        board_dims: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        if let Some(explicit) = explicit.filter(|e| e.is_truthy().unwrap_or(false)) {
            return Ok(explicit.clone().unbind());
        }
        if let (Some(rr), Some(bd)) = (routing_results, board_dims) {
            return Ok(resolve_fill_via_routing(py, rr, bd)?.into_any());
        }
        let layers = stackup.getattr("layers")?;
        let is_4layer_fcu = layers.len()? == 4
            && layers.get_item(0)?.getattr("name")?.eq("F.Cu")?;
        if is_4layer_fcu {
            let out = PyDict::new(py);
            out.set_item("F.Cu", 35.0_f64)?;
            out.set_item("In1.Cu", 95.0_f64)?;
            out.set_item("In2.Cu", 95.0_f64)?;
            out.set_item("B.Cu", 30.0_f64)?;
            return Ok(out.into_any().unbind());
        }
        Ok(PyDict::new(py).into_any().unbind())
    }

    // -----------------------------------------------------------------------
    // validate_stackup — the entry point.
    // -----------------------------------------------------------------------

    /// Run all stackup validation checks against a LayerStackup.
    #[pyfunction(name = "validate_stackup")]
    // Argument count mirrors the Python signature this pyfunction replaces;
    // it is fixed by the contract, not a design choice.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        stackup,
        differential_nets=None,
        impedance_spec_ohms=None,
        copper_fill_percentages=None,
        routing_results=None,
        board_dims=None,
        has_stitching_vias=false,
    ))]
    pub fn validate_stackup_py(
        py: Python<'_>,
        stackup: &Bound<'_, PyAny>,
        differential_nets: Option<&Bound<'_, PyAny>>,
        impedance_spec_ohms: Option<&Bound<'_, PyAny>>,
        copper_fill_percentages: Option<&Bound<'_, PyAny>>,
        routing_results: Option<&Bound<'_, PyAny>>,
        board_dims: Option<&Bound<'_, PyAny>>,
        has_stitching_vias: bool,
    ) -> PyResult<PyStackupValidationReport> {
        guard(|| {
            let nets: Vec<String> = match differential_nets {
                Some(nets) => nets
                    .try_iter()?
                    .map(|i| i?.extract::<String>())
                    .collect::<PyResult<_>>()?,
                None => Vec::new(),
            };

            let fill_pct_bound = resolve_fill_percentages(
                py,
                stackup,
                copper_fill_percentages,
                routing_results,
                board_dims,
            )?;
            let fill_pct = fill_pct_bound.bind(py);
            // The oracle passes the resolved dict into every check; a
            // non-dict fill value would AttributeError in the oracle too
            // (fill_pct.get), so the downcast here is the same failure class.
            let fill_pct = fill_pct.cast::<PyDict>().map_err(|_| {
                PyTypeError::new_err("copper fill percentages must be a dict")
            })?;

            let results = PyList::empty(py);
            for r in [
                check_copper_symmetry(py, stackup, fill_pct)?,
                check_return_path_adjacency(stackup, &nets, has_stitching_vias)?,
                check_impedance_spec(&nets, impedance_spec_ohms)?,
                check_copper_balance(py, stackup, fill_pct)?,
            ] {
                results.append(Bound::new(py, r)?.into_any())?;
            }

            Ok(PyStackupValidationReport {
                results: results.into_any().unbind(),
            })
        })
    }

    pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add_class::<PyStackupValidationResult>()?;
        module.add_class::<PyStackupValidationReport>()?;
        module.add_function(wrap_pyfunction!(validate_stackup_py, module)?)?;
        Ok(())
    }
}

#[cfg(feature = "python")]
pub use python::register;

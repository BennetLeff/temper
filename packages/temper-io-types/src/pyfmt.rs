// CPython float-formatting seams and shared pyo3 helpers for the Wave-4
// Phase-5 report / explainability migrations.
//
// Python's `f"{x:.Nf}"` is round-half-even fixed-point decimal formatting
// with `nan`/`inf`/`-inf` rendered lowercase (CPython's float formatting
// never writes `NaN`). Rust's `{x:.N$}` produces the same digits on every
// finite value (both are correctly-rounded round-half-even; pinned by the
// Wave-3 message-formatting comparisons in temper-constraint-compiler), but
// renders NaN as `NaN` and inf as `inf`/`-inf` — so the special values must
// be special-cased here, exactly like `temper-constraint-compiler`'s
// `py_float_fmt_1`.
//
// The report formatter uses `:.1f`/`:.2f`/`:.3f`, the benchmark generator
// uses `:.0f`/`:.1f`/`:.2f`, the summary uses `:.1f`/`:.3f`, and the
// markdown renderer uses `:.1f`/`.2f`/`.4f` — every site goes through
// this module so a NaN/inf that reaches any of them renders identically to
// CPython.
//
// The `to_f64`/`py_str`/`iter_items` helpers were moved here when the
// report surface (previously `report.rs`) was deleted as an orphaned kernel
// cluster (2026-08-20); they are the shared seam the explainability
// migration still uses.

// Feature-gated: the three helpers below are the ONLY pyo3-dependent items in
// this module -- everything after them (`py_float_fmt_*`) is pure Rust and must
// stay available in a `--no-default-features` build, which is what `cargo test
// --doc` and the wasm32 target use. They arrived ungated when the orphaned
// `report.rs` cluster was deleted (2026-08-20) and its shared seam moved here.
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Python `float(obj)`.
#[cfg(feature = "python")]
pub fn to_f64(obj: &Bound<'_, PyAny>) -> PyResult<f64> {
    obj.call_method0("__float__")?.extract::<f64>()
}

/// Python `str(obj)`.
#[cfg(feature = "python")]
pub fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(obj.str()?.to_string())
}

/// Iterate a Python iterable's items.
#[cfg(feature = "python")]
pub fn iter_items<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(item?);
    }
    Ok(out)
}

/// CPython `f"{x:.0f}"`.
pub fn py_float_fmt_0(x: f64) -> String {
    py_float_fmt(x, 0)
}

/// CPython `f"{x:.1f}"`.
pub fn py_float_fmt_1(x: f64) -> String {
    py_float_fmt(x, 1)
}

/// CPython `f"{x:.2f}"`.
pub fn py_float_fmt_2(x: f64) -> String {
    py_float_fmt(x, 2)
}

/// CPython `f"{x:.3f}"`.
pub fn py_float_fmt_3(x: f64) -> String {
    py_float_fmt(x, 3)
}

/// CPython `f"{x:.4f}"`.
pub fn py_float_fmt_4(x: f64) -> String {
    py_float_fmt(x, 4)
}

fn py_float_fmt(x: f64, prec: usize) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 {
            "inf".to_string()
        } else {
            "-inf".to_string()
        };
    }
    format!("{x:.prec$}")
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn py_float_fmt_1_matches_cpython() {
        let cases: &[(f64, &str)] = &[
            (1.0, "1.0"),
            (2.0, "2.0"),
            (0.5, "0.5"),
            (-0.5, "-0.5"),
            (2.55, "2.5"), // 2.55 is 2.54999... in binary -> rounds down
            (2.65, "2.6"), // 2.65 is 2.65000...000355 -> rounds up
            (3.25, "3.2"), // round half to even at 1 dp
            (3.35, "3.4"), // 3.35 is 3.35000...000355 -> rounds up
            (-0.0, "-0.0"),
            // 1e300's exact decimal expansion (not "1"+300 zeros): both
            // CPython and Rust print the correctly-rounded expansion, and
            // this pins it byte-for-byte.
            (
                1e300,
                "1000000000000000052504760255204420248704468581108159154915854115511802457988908195786371375080447864043704443832883878176942523235360430575644792184786706982848387200926575803737830233794788090059368953234970799945081119038967640880074652742780142494579258788820056842838115669472196386865459400540160.0",
            ),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
        ];
        for (x, expected) in cases {
            assert_eq!(&py_float_fmt_1(*x), expected, "py_float_fmt_1({x:?})");
        }
    }

    #[cfg_attr(test, test)]
    fn py_float_fmt_0_round_half_even() {
        assert_eq!(py_float_fmt_0(2.5), "2");
        assert_eq!(py_float_fmt_0(3.5), "4");
        assert_eq!(py_float_fmt_0(0.5), "0");
        assert_eq!(py_float_fmt_0(42.0), "42");
        assert_eq!(py_float_fmt_0(f64::NAN), "nan");
    }

    #[cfg_attr(test, test)]
    fn py_float_fmt_2_and_4() {
        assert_eq!(py_float_fmt_2(1.23456), "1.23");
        assert_eq!(py_float_fmt_2(3.25), "3.25");
        assert_eq!(py_float_fmt_4(1.25), "1.2500");
        assert_eq!(py_float_fmt_4(f64::INFINITY), "inf");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pyfmt::tests::py_float_fmt_1_matches_cpython", py_float_fmt_1_matches_cpython),
        ("pyfmt::tests::py_float_fmt_0_round_half_even", py_float_fmt_0_round_half_even),
        ("pyfmt::tests::py_float_fmt_2_and_4", py_float_fmt_2_and_4),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    #[test]
    fn py_float_fmt_0_always_integer_form() {
        proptest!(|(x in normal())| {
            let s = py_float_fmt_0(x);
            // Should never have a decimal point (precision 0).
            prop_assert!(!s.contains('.'), "py_float_fmt_0({x:?}) = '{s}' has decimal");
        });
    }

    #[test]
    fn py_float_fmt_n_precision_exact() {
        proptest!(|(x in normal())| {
            for (prec, f) in [
                (1usize, py_float_fmt_1 as fn(f64) -> String),
                (2, py_float_fmt_2),
                (3, py_float_fmt_3),
                (4, py_float_fmt_4),
            ] {
                let s = f(x);
                if s.contains('.') {
                    let after = s.split('.').nth(1).unwrap();
                    prop_assert_eq!(after.len(), prec,
                        "py_float_fmt_{}({:?}) = '{}' has {} digits after dot",
                        prec, x, s, after.len());
                }
            }
        });
    }

    #[test]
    fn py_float_fmt_special_values_are_lowercase() {
        for v in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            for f in [
                py_float_fmt_0 as fn(f64) -> String,
                py_float_fmt_1,
                py_float_fmt_2,
                py_float_fmt_3,
                py_float_fmt_4,
            ] {
                let s = f(v);
                assert!(!s.contains(|c: char| c.is_uppercase()),
                    "py_float_fmt_n({v:?}) = '{s}' has uppercase");
            }
        }
    }

    #[test]
    fn py_float_fmt_negative_zero() {
        assert_eq!(py_float_fmt_1(-0.0), "-0.0");
        assert_eq!(py_float_fmt_2(-0.0), "-0.00");
        assert_eq!(py_float_fmt_0(-0.0), "-0");
    }
}

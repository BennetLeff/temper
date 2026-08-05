// CPython float-formatting seams for the Wave-4 Phase-5 report /
// explainability migrations.
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
// markdown renderer uses `:.1f`/`:.2f`/`:.4f` — every site goes through
// this module so a NaN/inf that reaches any of them renders identically to
// CPython.

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
        return if x > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    format!("{x:.prec$}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
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
            (1e300, "1" + &"0".repeat(300) + ".0"),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
        ];
        for (x, expected) in cases {
            assert_eq!(&py_float_fmt_1(*x), expected, "py_float_fmt_1({x:?})");
        }
    }

    #[test]
    fn py_float_fmt_0_round_half_even() {
        assert_eq!(py_float_fmt_0(2.5), "2");
        assert_eq!(py_float_fmt_0(3.5), "4");
        assert_eq!(py_float_fmt_0(0.5), "0");
        assert_eq!(py_float_fmt_0(42.0), "42");
        assert_eq!(py_float_fmt_0(f64::NAN), "nan");
    }

    #[test]
    fn py_float_fmt_2_and_4() {
        assert_eq!(py_float_fmt_2(1.23456), "1.23");
        assert_eq!(py_float_fmt_2(3.25), "3.25");
        assert_eq!(py_float_fmt_4(1.25), "1.2500");
        assert_eq!(py_float_fmt_4(f64::INFINITY), "inf");
    }
}

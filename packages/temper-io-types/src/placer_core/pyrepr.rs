//! CPython-compatible float rendering — bit-exactness catalog class **B13**
//! (`repr()`/`format()` of a float is not Rust's `{}`/`{:.Nf}`).
//!
//! Every `__repr__` this module's pyclasses expose has to reproduce the
//! dataclass-generated one *character for character*, and
//! `placement_drc`'s violation messages embed `f"{dist:.3f}"`. Rust's
//! own float formatting disagrees with CPython's in four measured ways:
//!
//! | value        | CPython            | Rust `{}` / `{:.3}` |
//! |--------------|--------------------|---------------------|
//! | `1.0`        | `1.0`              | `1`                 |
//! | `1e300`      | `1e+300`           | 300-digit expansion |
//! | `1e-5`       | `1e-05`            | `0.00001`           |
//! | `f64::NAN`   | `nan`              | `NaN`               |
//!
//! [`repr_f64`] implements CPython's `float_repr` (`PyOS_double_to_string`
//! with format code `'r'`, shortest round-tripping digits, `ADD_DOT_0`)
//! and [`format_fixed`] implements `format(x, '.Nf')`. Both are pinned
//! against the live interpreter by the R1a differential over a random
//! corpus plus every boundary listed above — they are not "believed
//! equivalent", they are measured.
//!
//! ## Why the exponent threshold is 16 and not 17
//!
//! CPython's `format_float_short` switches from fixed to exponential
//! notation when `decpt <= -4 || decpt > 16`, where the value is
//! `0.d1d2… × 10^decpt`. `repr(1e15)` is therefore `1000000000000000.0`
//! (decpt 16) and `repr(1e16)` is `1e+16` (decpt 17).

/// Decompose a finite, non-zero f64 into its shortest round-tripping
/// decimal digit string and decimal-point position, such that the value
/// is `0.<digits> * 10^decpt` (with a separate sign).
///
/// Rust's `{:e}` formatting already produces the shortest round-tripping
/// digit sequence (Grisu/Dragon4), so this reuses it rather than
/// reimplementing the digit generator.
fn shortest_digits(value: f64) -> (bool, String, i32) {
    debug_assert!(value.is_finite() && value != 0.0);
    let negative = value.is_sign_negative();
    // `{:e}` renders e.g. -1.25e-7 as "-1.25e-7": one leading digit,
    // optional fraction, then `e` and a (possibly negative) exponent.
    let sci = format!("{:e}", value.abs());
    let (mantissa, exponent) = match sci.split_once('e') {
        Some(parts) => parts,
        // `{:e}` on a finite non-zero f64 always emits an exponent.
        None => (sci.as_str(), "0"),
    };
    let exp: i32 = exponent.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(|c| c.is_ascii_digit()).collect();
    let digits = digits.trim_end_matches('0');
    let digits = if digits.is_empty() { "0" } else { digits };
    // mantissa is `d.ddd`, i.e. value = 0.dddd * 10^(exp + 1).
    (negative, digits.to_string(), exp + 1)
}

/// Render `digits`/`decpt` in CPython's exponential style: one digit,
/// optional `.rest`, then `e`, a mandatory sign, and >= 2 exponent digits.
fn render_exponential(negative: bool, digits: &str, decpt: i32) -> String {
    let mut out = String::new();
    if negative {
        out.push('-');
    }
    let mut chars = digits.chars();
    // `digits` is non-empty by construction in `shortest_digits`.
    out.push(chars.next().unwrap_or('0'));
    let rest: String = chars.collect();
    if !rest.is_empty() {
        out.push('.');
        out.push_str(&rest);
    }
    let exp = decpt - 1;
    out.push('e');
    out.push(if exp < 0 { '-' } else { '+' });
    let abs_exp = exp.unsigned_abs();
    if abs_exp < 10 {
        out.push('0');
    }
    out.push_str(&abs_exp.to_string());
    out
}

/// Render `digits`/`decpt` in CPython's fixed style, always with a
/// fractional part (`Py_DTSF_ADD_DOT_0`).
fn render_fixed_repr(negative: bool, digits: &str, decpt: i32) -> String {
    let mut out = String::new();
    if negative {
        out.push('-');
    }
    if decpt <= 0 {
        out.push_str("0.");
        for _ in 0..(-decpt) {
            out.push('0');
        }
        out.push_str(digits);
    } else {
        let decpt = decpt as usize;
        if decpt >= digits.len() {
            out.push_str(digits);
            for _ in 0..(decpt - digits.len()) {
                out.push('0');
            }
            out.push_str(".0");
        } else {
            out.push_str(&digits[..decpt]);
            out.push('.');
            out.push_str(&digits[decpt..]);
        }
    }
    out
}

/// CPython `repr(x)` for a float.
pub fn repr_f64(value: f64) -> String {
    if value.is_nan() {
        // CPython renders every NaN, including a sign-bit-set one, as
        // bare "nan" (measured: repr(float('-nan')) == 'nan').
        return "nan".to_string();
    }
    if value.is_infinite() {
        return if value < 0.0 { "-inf" } else { "inf" }.to_string();
    }
    if value == 0.0 {
        // Signed zero is observable and must survive.
        return if value.is_sign_negative() {
            "-0.0".to_string()
        } else {
            "0.0".to_string()
        };
    }
    let (negative, digits, decpt) = shortest_digits(value);
    if decpt <= -4 || decpt > 16 {
        render_exponential(negative, &digits, decpt)
    } else {
        render_fixed_repr(negative, &digits, decpt)
    }
}

/// CPython `format(x, '.<precision>f')`.
///
/// Rust's `{:.N}` is itself correctly rounded with ties resolved to even,
/// which is what CPython's `_Py_dg_dtoa` mode 3 does, so the digit
/// generation is delegated. Only the non-finite spellings differ.
pub fn format_fixed(value: f64, precision: usize) -> String {
    if value.is_nan() {
        return "nan".to_string();
    }
    if value.is_infinite() {
        return if value < 0.0 { "-inf" } else { "inf" }.to_string();
    }
    format!("{value:.precision$}")
}

/// CPython `repr(s)` for a `str` that contains no characters needing an
/// escape beyond quote selection.
///
/// The dataclass `__repr__` embeds `repr()` of each string field. CPython
/// prefers `'` and switches to `"` only when the string contains a `'`
/// and no `"`. Backslash, the quote in use, and the C0 controls are
/// escaped; everything else (including non-ASCII, since Python 3) is
/// emitted verbatim.
pub fn repr_str(s: &str) -> String {
    let use_double = s.contains('\'') && !s.contains('"');
    let quote = if use_double { '"' } else { '\'' };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || (c as u32) == 0x7f => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn repr_matches_cpython_boundaries() {
        // Every one of these was read off the live interpreter.
        assert_eq!(repr_f64(1.0), "1.0");
        assert_eq!(repr_f64(-1.0), "-1.0");
        assert_eq!(repr_f64(0.0), "0.0");
        assert_eq!(repr_f64(-0.0), "-0.0");
        assert_eq!(repr_f64(0.1), "0.1");
        assert_eq!(repr_f64(1e15), "1000000000000000.0");
        assert_eq!(repr_f64(1e16), "1e+16");
        assert_eq!(repr_f64(1e-4), "0.0001");
        assert_eq!(repr_f64(1e-5), "1e-05");
        assert_eq!(repr_f64(1e300), "1e+300");
        assert_eq!(repr_f64(1.5e-300), "1.5e-300");
        assert_eq!(repr_f64(f64::NAN), "nan");
        assert_eq!(repr_f64(f64::INFINITY), "inf");
        assert_eq!(repr_f64(f64::NEG_INFINITY), "-inf");
        assert_eq!(repr_f64(5e-324), "5e-324");
        assert_eq!(repr_f64(2.675), "2.675");
    }

    #[cfg_attr(test, test)]
    fn format_fixed_matches_cpython_boundaries() {
        assert_eq!(format_fixed(0.0005, 3), "0.001");
        assert_eq!(format_fixed(-0.0004, 3), "-0.000");
        assert_eq!(format_fixed(f64::NAN, 3), "nan");
        assert_eq!(format_fixed(f64::INFINITY, 3), "inf");
        assert_eq!(format_fixed(2.675, 3), "2.675");
    }

    #[cfg_attr(test, test)]
    fn repr_str_quote_selection() {
        assert_eq!(repr_str("F.Cu"), "'F.Cu'");
        assert_eq!(repr_str("it's"), "\"it's\"");
        assert_eq!(repr_str("it's \"x\""), "'it\\'s \"x\"'");
        assert_eq!(repr_str("a\nb"), "'a\\nb'");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("placer_core::pyrepr::tests::repr_matches_cpython_boundaries", repr_matches_cpython_boundaries),
        ("placer_core::pyrepr::tests::format_fixed_matches_cpython_boundaries", format_fixed_matches_cpython_boundaries),
        ("placer_core::pyrepr::tests::repr_str_quote_selection", repr_str_quote_selection),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

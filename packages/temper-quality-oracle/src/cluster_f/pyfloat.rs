//! Bit-faithful replicas of the CPython float primitives router_v6 cluster F
//! depends on.
//!
//! Every function here exists because the corresponding Rust intrinsic is
//! **not** bit-identical to what CPython evaluates at the pinned call site.
//! Catalog classes are from `docs/wave4-discipline-contract.md` §2, and the
//! per-call-site mapping is in
//! `packages/temper-placer/tests/router_v6/_quality_metrics_py_oracle.py`.
//!
//! * [`py_hypot`] — **B4**. `math.hypot` is CPython's `vector_norm`, a
//!   Dekker double-double reduction with a differential correction step. It is
//!   neither `f64::hypot` (platform libm) nor `sqrt(dx*dx + dy*dy)`.
//! * [`py_sum`] — **B7**. CPython 3.12's `sum()` is Neumaier-compensated and
//!   seeds from the *int* `0`, so the first term goes through `0 + x` (which
//!   turns `-0.0` into `+0.0`) before compensation starts.
//! * [`py_min2`] / [`py_max2`] / [`py_min4`] — **B5**. The builtins keep the
//!   first argument on NaN; `f64::min`/`f64::max`/`f64::clamp` do not.
//! * [`py_format_fixed`] — **B3**. `f"{x:.2f}"` is exact decimal conversion
//!   with round-**half-even**; Rust's `format!("{:.2}")` rounds half-away.
//! * [`py_float_str`] — `str(float)`, used for the `{max_ratio}` interpolation.

// ---------------------------------------------------------------------------
// B5 — CPython builtin min/max keep the FIRST argument on NaN.
// ---------------------------------------------------------------------------

/// `min(a, b)` as CPython's builtin evaluates it: `b if b < a else a`.
#[inline]
pub fn py_min2(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// `max(a, b)` as CPython's builtin evaluates it: `b if b > a else a`.
#[inline]
pub fn py_max2(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// The **variadic** `min(a, b, c, d)`.
///
/// CPython seeds the running minimum with the first argument and replaces it
/// only on a true `<`. With a NaN anywhere every comparison is false, so a NaN
/// first argument is returned unchanged while a NaN in any later position is
/// discarded. A Rust fold over `f64::min` collapses that distinction.
#[inline]
pub fn py_min4(a: f64, b: f64, c: f64, d: f64) -> f64 {
    let mut m = a;
    if b < m {
        m = b;
    }
    if c < m {
        m = c;
    }
    if d < m {
        m = d;
    }
    m
}

// ---------------------------------------------------------------------------
// B4 — CPython's math.hypot (Modules/mathmodule.c: vector_norm).
// ---------------------------------------------------------------------------

/// Dekker/Veltkamp splitting constant, `2**27 + 1`.
const DEKKER_SPLIT: f64 = 134_217_729.0;

/// Exact two-term split of `x` into a high and low half.
#[inline]
fn dl_split(x: f64) -> (f64, f64) {
    let t = x * DEKKER_SPLIT;
    let hi = t - (t - x);
    let lo = x - hi;
    (hi, lo)
}

/// Error-free transformation of a product: `x * y == z + zz` exactly.
#[inline]
fn dl_mul(x: f64, y: f64) -> (f64, f64) {
    let z = x * y;
    let (xh, xl) = dl_split(x);
    let (yh, yl) = dl_split(y);
    let zz = ((xh * yh - z) + xh * yl + xl * yh) + xl * yl;
    (z, zz)
}

/// Compensated sum of two floats where `|a| >= |b|`: `a + b == x + y` exactly.
#[inline]
fn dl_fast_sum(a: f64, b: f64) -> (f64, f64) {
    let x = a + b;
    let y = (a - x) + b;
    (x, y)
}

/// `frexp`'s exponent: the `e` with `x == m * 2**e`, `0.5 <= |m| < 1`.
fn frexp_exp(x: f64) -> i32 {
    let biased = ((x.to_bits() >> 52) & 0x7ff) as i32;
    if biased == 0 {
        // Subnormal: normalise by 2**54 first, then correct the exponent.
        let y = x * exp2i(54);
        let b2 = ((y.to_bits() >> 52) & 0x7ff) as i32;
        return b2 - 1022 - 54;
    }
    biased - 1022
}

/// `2**n`, exact for every `n` an f64 can represent (0 / inf outside).
fn exp2i(n: i32) -> f64 {
    if (-1022..=1023).contains(&n) {
        f64::from_bits(((n + 1023) as u64) << 52)
    } else if n < -1022 {
        let shift = 52 + (n + 1022);
        if shift >= 0 {
            f64::from_bits(1u64 << shift)
        } else {
            0.0
        }
    } else {
        f64::INFINITY
    }
}

/// CPython `vector_norm`. `vec` is mutated exactly as CPython mutates its
/// stack array in the subnormal-rescaling branch.
fn vector_norm(vec: &mut [f64], max: f64, found_nan: bool) -> f64 {
    if max.is_infinite() {
        return max;
    }
    if found_nan {
        return f64::NAN;
    }
    if max == 0.0 || vec.len() <= 1 {
        return max;
    }
    let max_e = frexp_exp(max);
    if max_e < -1023 {
        // ldexp(1.0, -max_e) would overflow; convert subnormals to normals.
        for v in vec.iter_mut() {
            *v /= f64::MIN_POSITIVE;
        }
        let rescaled_max = max / f64::MIN_POSITIVE;
        return f64::MIN_POSITIVE * vector_norm(vec, rescaled_max, found_nan);
    }
    let scale = exp2i(-max_e);
    let mut csum = 1.0f64;
    let mut frac1 = 0.0f64;
    let mut frac2 = 0.0f64;
    for &v in vec.iter() {
        let x = v * scale; // lossless
        let pr = dl_mul(x, x); // lossless
        let sm = dl_fast_sum(csum, pr.0); // lossless
        csum = sm.0;
        frac1 += pr.1; // lossy
        frac2 += sm.1; // lossy
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let pr = dl_mul(-h, h);
    let sm = dl_fast_sum(csum, pr.0);
    csum = sm.0;
    frac1 += pr.1;
    frac2 += sm.1;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h); // differential correction
    h / scale
}

/// Two-argument `math.hypot`.
///
/// Note the ordering CPython uses: `max` is only updated for non-NaN
/// coordinates but `isinf(max)` is tested *before* `found_nan`, so an infinity
/// beats a NaN — `math.hypot(inf, nan)` is `inf`, not `nan`.
pub fn py_hypot(a: f64, b: f64) -> f64 {
    let mut coords = [a.abs(), b.abs()];
    let mut max = 0.0f64;
    let mut found_nan = false;
    for &c in coords.iter() {
        if c.is_nan() {
            found_nan = true;
        }
        if c > max {
            max = c;
        }
    }
    vector_norm(&mut coords, max, found_nan)
}

// ---------------------------------------------------------------------------
// B7 — CPython 3.12 `sum()` over floats.
// ---------------------------------------------------------------------------

/// `sum(values)` for a non-empty sequence of Python floats.
///
/// CPython seeds with the *int* `0` and only switches into the compensated
/// float loop once the first non-int arrives, so the first term is folded by a
/// plain `0.0 + x` (which normalises `-0.0` to `+0.0`) and the Neumaier
/// compensator starts at the second term. Reproducing that seed matters: a
/// straight `iter().sum()` differs from CPython from n = 8 upward, and differs
/// on the very first term when it is `-0.0`.
///
/// `sum([])` is the *int* `0` in Python; every cluster-F call site guarantees
/// at least two terms, so this takes a non-empty slice and returns f64.
pub fn py_sum(values: &[f64]) -> f64 {
    debug_assert!(!values.is_empty());
    let mut f_result = 0.0f64 + values[0];
    let mut c = 0.0f64;
    for &x in &values[1..] {
        let t = f_result + x;
        if f_result.abs() >= x.abs() {
            c += (f_result - t) + x;
        } else {
            c += (x - t) + f_result;
        }
        f_result = t;
    }
    f_result + c
}

// ---------------------------------------------------------------------------
// B3 — CPython fixed-point float formatting (round-half-even, exact).
// ---------------------------------------------------------------------------

/// Little-endian base-1e9 magnitude, used only for the `2**e` blow-up when the
/// value's exponent is non-negative (`|x| >= 2**52`).
fn words_from_u128(mut v: u128) -> Vec<u32> {
    let mut out = Vec::new();
    if v == 0 {
        out.push(0);
        return out;
    }
    while v > 0 {
        out.push((v % 1_000_000_000) as u32);
        v /= 1_000_000_000;
    }
    out
}

fn words_double(w: &mut Vec<u32>) {
    let mut carry: u32 = 0;
    for limb in w.iter_mut() {
        let v = *limb * 2 + carry;
        if v >= 1_000_000_000 {
            *limb = v - 1_000_000_000;
            carry = 1;
        } else {
            *limb = v;
            carry = 0;
        }
    }
    if carry > 0 {
        w.push(carry);
    }
}

fn words_to_string(w: &[u32]) -> String {
    let mut s = String::new();
    for (i, limb) in w.iter().enumerate().rev() {
        if i == w.len() - 1 {
            s.push_str(&limb.to_string());
        } else {
            s.push_str(&format!("{limb:09}"));
        }
    }
    s
}

/// Decimal digits of `round_half_even(mag * 10**prec)` for finite `mag >= 0`.
fn scaled_digits(mag: f64, prec: usize) -> String {
    let bits = mag.to_bits();
    let biased = ((bits >> 52) & 0x7ff) as i32;
    let frac = bits & ((1u64 << 52) - 1);
    let (m, e) = if biased == 0 {
        (frac, -1074i32)
    } else {
        (frac | (1u64 << 52), biased - 1075)
    };
    if m == 0 {
        return "0".to_string();
    }
    // mag * 10**prec == m * 10**prec * 2**e, and m * 10**prec fits in u128
    // for every precision this codebase formats with (m < 2**53).
    let num: u128 = (m as u128) * 10u128.pow(prec as u32);
    if e >= 0 {
        let mut w = words_from_u128(num);
        for _ in 0..e {
            words_double(&mut w);
        }
        return words_to_string(&w);
    }
    let k = (-e) as u32;
    if k > 127 {
        // num < 2**73 < 2**(k-1), so the quotient is 0 and the remainder is
        // strictly below half — never a tie.
        return "0".to_string();
    }
    let q = num >> k;
    let rem = num & ((1u128 << k) - 1);
    let half = 1u128 << (k - 1);
    let rounded = if rem > half || (rem == half && (q & 1) == 1) {
        q + 1
    } else {
        q
    };
    rounded.to_string()
}

/// `format(x, f".{prec}f")` exactly as CPython renders it.
///
/// CPython converts through `_Py_dg_dtoa`, which is exact and breaks ties to
/// even. `format!("{:.2}", 0.125)` in Rust yields `"0.13"`; this yields
/// `"0.12"`, which is what the pinned `description` strings contain.
pub fn py_format_fixed(x: f64, prec: usize) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    let neg = x.is_sign_negative();
    if x.is_infinite() {
        return if neg { "-inf" } else { "inf" }.to_string();
    }
    let digits = scaled_digits(x.abs(), prec);
    let body = if prec == 0 {
        digits
    } else {
        let padded = if digits.len() <= prec {
            format!("{}{}", "0".repeat(prec + 1 - digits.len()), digits)
        } else {
            digits
        };
        let split = padded.len() - prec;
        format!("{}.{}", &padded[..split], &padded[split..])
    };
    if neg { format!("-{body}") } else { body }
}

/// `str(x)` / `repr(x)` for a float, as CPython renders it.
///
/// Used only for the `> {max_ratio}` interpolation in
/// `lint_single_net_detours`'s description. Rust's `Display` drops the `.0`
/// on integral values and never switches to exponent form, so neither `{}`
/// nor `{:?}` matches CPython across the range.
pub fn py_float_str(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x < 0.0 { "-inf" } else { "inf" }.to_string();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0" } else { "0.0" }.to_string();
    }
    // Rust's `{:e}` is the shortest round-tripping representation, the same
    // digit string CPython's repr uses; only the layout rules differ.
    let sci = format!("{:e}", x.abs());
    let (mantissa, exp_str) = match sci.split_once('e') {
        Some(parts) => parts,
        None => return sci,
    };
    let exp: i32 = exp_str.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let decpt = exp + 1; // value == 0.<digits> * 10**decpt
    let sign = if x < 0.0 { "-" } else { "" };
    if decpt <= -4 || decpt > 16 {
        let head = &digits[..1];
        let tail = &digits[1..];
        let mant = if tail.is_empty() {
            head.to_string()
        } else {
            format!("{head}.{tail}")
        };
        let e = decpt - 1;
        let esign = if e < 0 { '-' } else { '+' };
        return format!("{sign}{mant}e{esign}{:02}", e.abs());
    }
    if decpt <= 0 {
        return format!("{sign}0.{}{}", "0".repeat((-decpt) as usize), digits);
    }
    let d = decpt as usize;
    if d >= digits.len() {
        format!("{sign}{}{}.0", digits, "0".repeat(d - digits.len()))
    } else {
        format!("{sign}{}.{}", &digits[..d], &digits[d..])
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn hypot_matches_pinned_cpython_values() {
        // Pinned from CPython 3.12 `math.hypot(...).hex()`.
        assert_eq!(py_hypot(3.0, 4.0), 5.0);
        assert_eq!(py_hypot(0.1, 0.2).to_bits(), 0.223606797749979_f64.to_bits());
        assert!(py_hypot(f64::INFINITY, f64::NAN).is_infinite());
        assert!(py_hypot(f64::NAN, 0.0).is_nan());
        assert_eq!(py_hypot(-0.0, -0.0), 0.0);
        assert!(py_hypot(-0.0, -0.0).is_sign_positive());
        // Denormal band: the subnormal-rescaling branch of vector_norm.
        assert_eq!(py_hypot(5e-324, 5e-324), 5e-324);
    }

    #[cfg_attr(test, test)]
    fn sum_is_neumaier_compensated() {
        let v = [1e16, 1.0, -1e16, 1.0, 1.0, 1.0, 1.0, 1.0];
        assert_eq!(py_sum(&v), 6.0);
        let naive: f64 = v.iter().sum();
        assert_ne!(py_sum(&v), naive);
        // int-0 seed normalises a leading -0.0.
        assert!(py_sum(&[-0.0, 0.0]).is_sign_positive());
    }

    #[cfg_attr(test, test)]
    fn variadic_min_keeps_first_argument_on_nan() {
        assert!(py_min4(f64::NAN, 1.0, 2.0, 3.0).is_nan());
        assert_eq!(py_min4(1.0, f64::NAN, 2.0, 3.0), 1.0);
        // The clamp CPython performs in _angle_between.
        assert_eq!(py_max2(-1.0, py_min2(1.0, f64::NAN)), 1.0);
    }

    #[cfg_attr(test, test)]
    fn format_fixed_rounds_half_to_even() {
        assert_eq!(py_format_fixed(0.125, 2), "0.12");
        assert_eq!(py_format_fixed(0.135, 2), "0.14");
        assert_eq!(py_format_fixed(2.675, 2), "2.67");
        assert_eq!(py_format_fixed(-0.0, 2), "-0.00");
        assert_eq!(py_format_fixed(f64::NAN, 2), "nan");
        assert_eq!(py_format_fixed(f64::NEG_INFINITY, 1), "-inf");
        assert_eq!(py_format_fixed(180.0, 1), "180.0");
        assert_eq!(py_format_fixed(0.0, 2), "0.00");
    }

    #[cfg_attr(test, test)]
    fn float_str_matches_python_repr() {
        assert_eq!(py_float_str(1.5), "1.5");
        assert_eq!(py_float_str(1.0), "1.0");
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-7), "1e-07");
        assert_eq!(py_float_str(-0.0), "-0.0");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("cluster_f::pyfloat::tests::hypot_matches_pinned_cpython_values", hypot_matches_pinned_cpython_values),
        ("cluster_f::pyfloat::tests::sum_is_neumaier_compensated", sum_is_neumaier_compensated),
        ("cluster_f::pyfloat::tests::variadic_min_keeps_first_argument_on_nan", variadic_min_keeps_first_argument_on_nan),
        ("cluster_f::pyfloat::tests::format_fixed_rounds_half_to_even", format_fixed_rounds_half_to_even),
        ("cluster_f::pyfloat::tests::float_str_matches_python_repr", float_str_matches_python_repr),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

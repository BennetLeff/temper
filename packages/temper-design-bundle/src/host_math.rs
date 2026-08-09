//! Host-libm helpers for temper-design-bundle kernels that must match a
//! CPython reference bit-for-bit.
//!
//! CPython's `x ** y` on floats is libm `pow` (float_pow) and `math.sqrt`
//! is libm `sqrt` — NOT the statically-bound Rust intrinsics, whose
//! last-ulp answers can differ from the uv standalone Python build's libm
//! (measured for `sin` in temper-geometry's pad_geometry work). The
//! deterministic leaf kernels (component_assignment's `sqrt(w**2 + h**2)`
//! and `sqrt(dx**2 + dy**2)`) resolve `pow`/`sqrt` through
//! `dlsym(RTLD_DEFAULT, ...)` to the exact libm the host CPython process
//! loaded. `math.hypot` is NOT libm `hypot` — CPython uses a Dekker
//! double-double `vector_norm` (see `hypot` below), ported from
//! `temper-drc-rs/src/pymath.rs`. Mirrors `temper-geometry/src/host_math.rs`.

#![allow(clippy::missing_safety_doc)]

#[cfg(not(target_arch = "wasm32"))]
use std::ffi::CStr;

#[cfg(not(target_arch = "wasm32"))]
type UnaryMathFn = unsafe extern "C" fn(f64) -> f64;
#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(all(not(target_arch = "wasm32"), target_vendor = "apple"))]
const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2
#[cfg(all(not(target_arch = "wasm32"), not(target_vendor = "apple")))]
const RTLD_DEFAULT: *const u8 = core::ptr::null();

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_ptr(symbol: &CStr) -> Option<*mut u8> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated C string and `RTLD_DEFAULT` is this
    // platform's "search every loaded object" handle (never dereferenced).
    let p = unsafe { dlsym(RTLD_DEFAULT, symbol.as_ptr().cast::<u8>()) };
    if p.is_null() { None } else { Some(p) }
}

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_unary(symbol: &CStr) -> Option<UnaryMathFn> {
    // SAFETY: the resolved symbol is a C `double(double)` from libm.
    dlsym_ptr(symbol).map(|p| unsafe { std::mem::transmute::<*mut u8, UnaryMathFn>(p) })
}

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_binary(symbol: &CStr) -> Option<BinaryMathFn> {
    // SAFETY: the resolved symbol is a C `double(double, double)` from libm.
    dlsym_ptr(symbol).map(|p| unsafe { std::mem::transmute::<*mut u8, BinaryMathFn>(p) })
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    x.powf(y)
}
unsafe extern "C" fn fallback_sqrt(x: f64) -> f64 {
    f64::sqrt(x)
}

fn host_sqrt() -> &'static UnaryMathFn {
    #[cfg(not(target_arch = "wasm32"))]
    {
        static CELL: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
        CELL.get_or_init(|| dlsym_unary(c"sqrt").or(Some(fallback_sqrt)))
            .as_ref()
            .unwrap_or_else(|| unreachable!("fallback always set"))
    }
    #[cfg(target_arch = "wasm32")]
    {
        static CELL: std::sync::OnceLock<UnaryMathFn> = std::sync::OnceLock::new();
        CELL.get_or_init(fallback_sqrt)
    }
}

fn host_pow() -> &'static BinaryMathFn {
    #[cfg(not(target_arch = "wasm32"))]
    {
        static CELL: std::sync::OnceLock<Option<BinaryMathFn>> = std::sync::OnceLock::new();
        CELL.get_or_init(|| dlsym_binary(c"pow").or(Some(fallback_pow)))
            .as_ref()
            .unwrap_or_else(|| unreachable!("fallback always set"))
    }
    #[cfg(target_arch = "wasm32")]
    {
        static CELL: std::sync::OnceLock<BinaryMathFn> = std::sync::OnceLock::new();
        CELL.get_or_init(fallback_pow)
    }
}

/// CPython `float ** float` (libm `pow`), bit-exact with the reference.
pub fn pow(x: f64, y: f64) -> f64 {
    unsafe { host_pow()(x, y) }
}

/// CPython `math.sqrt` (libm `sqrt`), bit-exact with the reference.
pub fn sqrt(x: f64) -> f64 {
    unsafe { host_sqrt()(x) }
}

unsafe extern "C" fn fallback_log(x: f64) -> f64 {
    f64::ln(x)
}

fn host_log() -> &'static UnaryMathFn {
    #[cfg(not(target_arch = "wasm32"))]
    {
        static CELL: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
        CELL.get_or_init(|| dlsym_unary(c"log").or(Some(fallback_log)))
            .as_ref()
            .unwrap_or_else(|| unreachable!("fallback always set"))
    }
    #[cfg(target_arch = "wasm32")]
    {
        static CELL: std::sync::OnceLock<UnaryMathFn> = std::sync::OnceLock::new();
        CELL.get_or_init(fallback_log)
    }
}

/// Raw libm ``log``, bit-exact with the reference.
///
/// NOTE: most callers should use [`py_log`] instead — this raw libm ``log``
/// returns ``-inf`` for ``log(0)``, while CPython's ``math.log`` raises
/// ``ValueError``.
#[allow(dead_code)]
pub fn log(x: f64) -> f64 {
    unsafe { host_log()(x) }
}

/// CPython ``math.log`` semantics: libm `log`, but raises ``ValueError``
/// for domain errors (x <= 0 and finite), matching CPython's
/// ``math.log(0)`` → ``ValueError`` (not ``-inf``).
pub fn py_log(x: f64) -> Result<f64, &'static str> {
    if x.is_finite() && x <= 0.0 {
        return Err("math domain error");
    }
    Ok(unsafe { host_log()(x) })
}

/// Python `max(a, b)` semantics: the FIRST argument on ties, NaN kept only
/// if it is the current running maximum (Python's `if item > current`).
/// Rust's `f64::max` is different (it propagates NaN both ways and prefers
/// +0.0 over -0.0).
pub fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Python `min(a, b)` semantics (see [`py_max`]).
pub fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// CPython `round(x)` — round-half-to-even on the double, with the sign of
/// zero normalised to `+0.0` (the caller's `int()`/product normalises it).
pub fn py_round(x: f64) -> f64 {
    let r = x.round_ties_even();
    if r == 0.0 {
        0.0
    } else {
        r
    }
}

/// CPython's `float.__mod__` (`float_rem`): `fmod(a, b)` with the sign
/// correction `if (b < 0) != (mod < 0): mod += b` and the exact-multiple
/// branch `mod = copysign(0.0, b)`. NOT `f64::rem_euclid` — that returns
/// `-0.0` for `(-720.0).rem_euclid(360.0)` where CPython returns `+0.0`.
///
/// Moved here from `validation.rs` (2026-08-07, Wave 4 Phase 3
/// `write_board_geometry.rs`), which carried an identical private copy of
/// this exact CPython-quirk transcription -- consolidated to a single
/// canonical implementation rather than duplicated a third time, following
/// this crate's own `py_max`/`py_min`/`py_round` precedent above.
pub fn py_float_mod(a: f64, b: f64) -> f64 {
    let mut mod_ = a % b; // IEEE fmod
    if mod_ != 0.0 {
        if (b < 0.0) != (mod_ < 0.0) {
            mod_ += b;
        }
    } else {
        mod_ = if b < 0.0 { -0.0 } else { 0.0 };
    }
    mod_
}

/// CPython's `math.hypot` (the 2-argument `vector_norm`), replicated
/// exactly: a Dekker double-double compensated norm with fma-based
/// `dl_mul`. Rust's `f64::hypot` (libm) differs from it in the last ulp
/// (measured 30808/200000 random cases). Port of
/// `temper-drc-rs/src/pymath.rs::py_hypot` (itself ported from
/// `temper-geometry/src/pad_geometry.rs`), kept here so the validator
/// slot-grid kernels track CPython bit-for-bit.
pub fn hypot(x: f64, y: f64) -> f64 {
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
    }
    if x.is_infinite() || y.is_infinite() {
        return f64::INFINITY;
    }
    let x = x.abs();
    let y = y.abs();
    let max = x.max(y);
    if max == 0.0 {
        return 0.0;
    }
    vector_norm_2(x, y, max)
}

struct DL {
    hi: f64,
    lo: f64,
}

fn dl_fast_sum(a: f64, b: f64) -> DL {
    let s = a + b;
    DL { hi: s, lo: (a - s) + b }
}

fn dl_mul(x: f64, y: f64) -> DL {
    let z = x * y;
    DL { hi: z, lo: x.mul_add(y, -z) }
}

fn frexp(x: f64) -> (f64, i32) {
    let bits = x.to_bits();
    let e = ((bits >> 52) & 0x7ff) as i32 - 1022;
    let m = f64::from_bits((bits & 0x800f_ffff_ffff_ffff) | 0x3fe0_0000_0000_0000);
    (m, e)
}

/// Exact `2^e` for every `i32` exponent (same helper as `temper-geometry`'s
/// `pad_geometry::pow2` and `temper-drc-rs`'s `pymath::pow2`).
///
/// `2f64.powi(e)` is NOT sufficient: for `e = -1024` (reachable from
/// `frexp` of any `x >= 2^1023`, the top binade), `powi(-1024)` underflows
/// to `0.0`, making `v * scale = 0`, `h = 0`, and `h / scale = 0/0 = NaN`.
/// The subnormal `2^-1024` must be built from its bit pattern to keep full
/// mantissa precision. (This copy was fixed after `temper-drc-rs`'s; the
/// proptest there caught the same class.)
fn pow2(e: i32) -> f64 {
    if e > 1023 {
        return f64::INFINITY;
    }
    if e >= -1022 {
        return f64::from_bits(((e + 1023) as u64) << 52);
    }
    if e >= -1074 {
        return f64::from_bits(1u64 << (e + 1074));
    }
    0.0
}

fn vector_norm_2(x: f64, y: f64, max: f64) -> f64 {
    let (_, max_e) = frexp(max);
    if max_e < -1023 {
        return f64::MIN_POSITIVE
            * vector_norm_2(
                x / f64::MIN_POSITIVE,
                y / f64::MIN_POSITIVE,
                max / f64::MIN_POSITIVE,
            );
    }
    let scale = pow2(-max_e);
    let mut csum = 1.0f64;
    let mut frac1 = 0.0f64;
    let mut frac2 = 0.0f64;
    for v in [x * scale, y * scale] {
        let pr = dl_mul(v, v);
        let sm = dl_fast_sum(csum, pr.hi);
        csum = sm.hi;
        frac1 += pr.lo;
        frac2 += sm.lo;
    }
    let mut h = (csum - 1.0 + (frac1 + frac2)).sqrt();
    let pr = dl_mul(-h, h);
    let sm = dl_fast_sum(csum, pr.hi);
    csum = sm.hi;
    frac1 += pr.lo;
    frac2 += sm.lo;
    let x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h); // differential correction
    h / scale
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(not(target_arch = "wasm32"))]
    #[test]
    fn host_libm_symbols_actually_resolve() {
        assert!(dlsym_unary(c"sqrt").is_some(), "dlsym could not resolve `sqrt`");
        assert!(dlsym_binary(c"pow").is_some(), "dlsym could not resolve `pow`");
    }

    #[test]
    fn hypot_matches_cpython_on_the_top_binade() {
        // Top binade (x >= 2^1023): `pow2(-1024)` must build the subnormal
        // 2^-1024 from its bit pattern — `2f64.powi(-1024)` underflows to
        // 0.0, giving `h / scale = 0/0 = NaN`. Pinned against CPython 3.12
        // (same pin as temper-geometry's pad_geometry and temper-drc-rs).
        assert_eq!(hypot(1e308, 1e308).to_bits(), 0x7FE92C80954C51F5);
        assert!(hypot(f64::MAX, 0.0) == f64::MAX);
        assert!(hypot(1.091009947397983e308, 0.0) == 1.091009947397983e308);
    }

    #[test]
    fn py_float_mod_matches_cpython_zero_sign() {
        // CPython: -720.0 % 360.0 == 0.0 (positive zero), not -0.0.
        let result = py_float_mod(-720.0, 360.0);
        assert_eq!(result, 0.0);
        assert!(result.is_sign_positive(), "expected +0.0, got -0.0");
    }

    #[test]
    fn py_float_mod_matches_python_floored_semantics() {
        // Positive divisor: result always non-negative, unlike Rust's raw
        // `%` (which would give -30.0 here).
        assert_eq!(py_float_mod(-30.0, 360.0), 330.0);
        assert_eq!(py_float_mod(370.0, 360.0), 10.0);
        assert_eq!(py_float_mod(10.0, 360.0), 10.0);
        assert_eq!(py_float_mod(0.0, 360.0), 0.0);
    }

    #[test]
    fn py_max_min_matches_python() {
        assert_eq!(py_max(1.0, 2.0), 2.0);
        assert_eq!(py_max(2.0, 1.0), 2.0);
        assert_eq!(py_max(2.0, 2.0), 2.0);
        assert_eq!(py_max(-0.0, 0.0), -0.0); // first on tie
        assert_eq!(py_min(2.0, 1.0), 1.0);
        assert_eq!(py_min(1.0, 2.0), 1.0);
        assert_eq!(py_min(1.0, 1.0), 1.0);
    }

    #[test]
    fn hypot_matches_cpython_pinned_values() {
        assert_eq!(hypot(3.0, 4.0), 5.0);
        assert_eq!(hypot(0.0, 0.0), 0.0);
        // A known vector_norm last-ulp case where libm hypot diverges:
        // math.hypot(0x1.8330e0b997a2cp+497, -0x1.34c2707315642p+498)
        // == 0x1.6c6eee8dc9d68p+498, while libm hypot gives ...d67.
        let a = f64::from_bits(0x5f08330e0b997a2c);
        let b = f64::from_bits(0xdf134c2707315642);
        let expected = f64::from_bits(0x5f16c6eee8dc9d68);
        assert_eq!(hypot(a, b), expected);
        assert_ne!(expected, f64::hypot(a, b)); // libm diverges here
        assert!(hypot(f64::NAN, 1.0).is_nan());
        assert!(hypot(f64::INFINITY, 1.0).is_infinite());
    }
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    fn positive() -> impl Strategy<Value = f64> {
        0.001f64..1e6f64
    }

    fn safe_int() -> impl Strategy<Value = i64> {
        -1_000_000i64..1_000_000i64
    }

    // ---------- py_max

    #[test]
    fn p32_py_max_returns_larger() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_max(a, b);
            prop_assert_eq!(r, a.max(b));
        });
    }

    #[test]
    fn p33_py_max_returns_one_of_inputs() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_max(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits());
        });
    }

    #[test]
    fn p34_py_max_nan_first_returns_nan() {
        proptest!(|(b in normal())| {
            prop_assert!(py_max(f64::NAN, b).is_nan());
        });
    }

    #[test]
    fn p35_py_max_nan_second_returns_first() {
        proptest!(|(a in normal())| {
            prop_assert_eq!(py_max(a, f64::NAN), a);
        });
    }

    // ---------- py_min

    #[test]
    fn p36_py_min_returns_smaller() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_min(a, b);
            prop_assert_eq!(r, a.min(b));
        });
    }

    #[test]
    fn p37_py_min_returns_one_of_inputs() {
        proptest!(|(a in normal(), b in normal())| {
            let r = py_min(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits());
        });
    }

    #[test]
    fn p38_py_min_nan_first_returns_nan() {
        proptest!(|(b in normal())| {
            prop_assert!(py_min(f64::NAN, b).is_nan());
        });
    }

    #[test]
    fn p39_py_min_nan_second_returns_first() {
        proptest!(|(a in normal())| {
            prop_assert_eq!(py_min(a, f64::NAN), a);
        });
    }

    // ---------- py_round

    #[test]
    fn p40_py_round_is_integer() {
        proptest!(|(x in normal())| {
            let r = py_round(x);
            prop_assert_eq!(r.trunc(), r);
        });
    }

    #[test]
    fn p41_py_round_diff_at_most_half() {
        proptest!(|(x in normal())| {
            let r = py_round(x);
            prop_assert!((r - x).abs() <= 0.5 + 1e-12);
        });
    }

    #[test]
    fn p42_py_round_ties_to_even() {
        proptest!(|(n in safe_int())| {
            let x = n as f64 + 0.5;
            prop_assume!(n.unsigned_abs() < (1u64 << 52));
            let r = py_round(x);
            prop_assert_eq!(r % 2.0, 0.0);
        });
    }

    #[test]
    fn p43_py_round_preserves_sign() {
        proptest!(|(x in normal())| {
            prop_assume!(x.abs() >= 0.5);
            let r = py_round(x);
            prop_assert_eq!(r.is_sign_positive(), x.is_sign_positive());
        });
    }

    // ---------- py_float_mod

    #[test]
    fn p44_float_mod_in_range() {
        proptest!(|(a in normal(), b in positive())| {
            let r = py_float_mod(a, b);
            prop_assert!(r >= 0.0 && r < b.abs());
        });
    }

    #[test]
    fn p45_float_mod_sign_matches_b() {
        proptest!(|(a in normal(), b_abs in positive())| {
            let r_pos = py_float_mod(a, b_abs);
            prop_assert!(r_pos.is_sign_positive() || r_pos == 0.0);
            let r_neg = py_float_mod(a, -b_abs);
            prop_assert!(r_neg.is_sign_negative() || r_neg == -0.0 || r_neg == 0.0);
        });
    }

    #[test]
    fn p46_float_mod_exact_multiple_is_zero() {
        proptest!(|(k in -100i64..100i64, b_int in 1i64..1000i64)| {
            let b = b_int as f64;
            let a = (k * b_int) as f64;
            let r = py_float_mod(a, b);
            // Both a and b are exactly representable integers, so the
            // division is exact and the result must be exactly zero.
            prop_assert_eq!(r, 0.0);
            prop_assert!(r.is_sign_positive());
        });
    }

    // ---------- hypot

    #[test]
    fn p47_hypot_non_negative() {
        proptest!(|(a in normal(), b in normal())| {
            prop_assert!(hypot(a, b) >= 0.0);
        });
    }

    #[test]
    fn p48_hypot_symmetric() {
        proptest!(|(a in normal(), b in normal())| {
            prop_assert_eq!(hypot(a, b), hypot(b, a));
        });
    }

    #[test]
    fn p49_hypot_ge_max_abs() {
        proptest!(|(a in normal(), b in normal())| {
            let h = hypot(a, b);
            let m = a.abs().max(b.abs());
            prop_assert!(h >= m);
        });
    }

    #[test]
    fn p50_hypot_zero_returns_abs() {
        proptest!(|(x in normal())| {
            prop_assert_eq!(hypot(0.0, x), x.abs());
            prop_assert_eq!(hypot(x, 0.0), x.abs());
        });
    }

    #[test]
    fn p51_hypot_triangle_bound() {
        proptest!(|(a in normal(), b in normal())| {
            let h = hypot(a, b);
            let sum = a.abs() + b.abs();
            prop_assert!(h <= sum);
        });
    }

    #[test]
    fn p52_hypot_nan_returns_nan() {
        proptest!(|(x in normal())| {
            prop_assert!(hypot(f64::NAN, x).is_nan());
            prop_assert!(hypot(x, f64::NAN).is_nan());
        });
    }
}

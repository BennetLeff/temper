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
    let scale = 2f64.powi(-max_e);
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

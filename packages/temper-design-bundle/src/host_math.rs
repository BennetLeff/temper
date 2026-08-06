//! Host-libm helpers for temper-design-bundle kernels that must match a
//! CPython reference bit-for-bit.
//!
//! CPython's `x ** y` on floats is libm `pow` (float_pow), `math.sqrt` is
//! libm `sqrt`, and `math.hypot` is libm `hypot` — NOT the statically-bound
//! Rust intrinsics, whose last-ulp answers can differ from the uv standalone
//! Python build's libm (measured for `sin` in temper-geometry's pad_geometry
//! work). The deterministic leaf kernels (component_assignment's
//! `sqrt(w**2 + h**2)` and `sqrt(dx**2 + dy**2)`, the slot-grid validator's
//! `math.hypot`) resolve these through `dlsym(RTLD_DEFAULT, ...)` to the
//! exact libm the host CPython process loaded. Mirrors
//! `temper-geometry/src/host_math.rs`.

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

fn host_hypot() -> &'static BinaryMathFn {
    #[cfg(not(target_arch = "wasm32"))]
    {
        static CELL: std::sync::OnceLock<Option<BinaryMathFn>> = std::sync::OnceLock::new();
        CELL.get_or_init(|| dlsym_binary(c"hypot").or(Some(fallback_hypot)))
            .as_ref()
            .unwrap_or_else(|| unreachable!("fallback always set"))
    }
    #[cfg(target_arch = "wasm32")]
    {
        static CELL: std::sync::OnceLock<BinaryMathFn> = std::sync::OnceLock::new();
        CELL.get_or_init(fallback_hypot)
    }
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    x.powf(y)
}
unsafe extern "C" fn fallback_sqrt(x: f64) -> f64 {
    f64::sqrt(x)
}
unsafe extern "C" fn fallback_hypot(x: f64, y: f64) -> f64 {
    f64::hypot(x, y)
}

/// CPython `float ** float` (libm `pow`), bit-exact with the reference.
pub fn pow(x: f64, y: f64) -> f64 {
    unsafe { host_pow()(x, y) }
}

/// CPython `math.sqrt` (libm `sqrt`), bit-exact with the reference.
pub fn sqrt(x: f64) -> f64 {
    unsafe { host_sqrt()(x) }
}

/// CPython `math.hypot` (libm `hypot`), bit-exact with the reference.
pub fn hypot(x: f64, y: f64) -> f64 {
    unsafe { host_hypot()(x, y) }
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

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(not(target_arch = "wasm32"))]
    #[test]
    fn host_libm_symbols_actually_resolve() {
        assert!(dlsym_unary(c"sqrt").is_some(), "dlsym could not resolve `sqrt`");
        assert!(dlsym_binary(c"pow").is_some(), "dlsym could not resolve `pow`");
        assert!(dlsym_binary(c"hypot").is_some(), "dlsym could not resolve `hypot`");
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
}

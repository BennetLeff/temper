// Shared "host math" helpers: match the host Python runtime's libm bit-for-bit.
//
// CPython's `x ** y` on floats is libm `pow` (float_pow) — NOT repeated
// multiplication and NOT `sqrt`; `math.cos` / `math.sin` / `math.atan2` are
// the host libm's. The uv standalone Python build ships its own libm whose
// results can differ from this crate's statically-bound f64 intrinsics in
// the last ulp (measured for sin; see pad_geometry.rs for the original
// finding), so any kernel whose differential must be bit-identical to a
// Python reference resolves these functions through `dlsym(RTLD_DEFAULT, ...)`
// to the exact libm the host CPython process loaded.
//
// `dlsym` is a libc/dynamic-loader facility that does not exist on
// wasm32-unknown-unknown (no OS, no dynamic linker), so the dlsym path is
// compiled only off wasm32; on wasm32 the helpers fall back to the f64
// intrinsics. wasm32 builds may diverge from a host Python's libm in the
// last ulp — expected and acceptable: wasm32 has no host CPython process to
// match bit-for-bit against in the first place.
//
// Note on `RTLD_DEFAULT`: it is -2 on Darwin and NULL on most ELF platforms;
// passing NULL makes `dlsym` return null and LLVM would then lower the
// fallback `powf(x, 2.0)` → `x*x` — silently reintroducing the forbidden
// optimisation. The module therefore passes `core::ptr::null()` (==
// RTLD_DEFAULT on Darwin) exactly as grid_raster.rs did before extraction.

#![allow(clippy::missing_safety_doc)]

#[cfg(not(target_arch = "wasm32"))]
type UnaryMathFn = unsafe extern "C" fn(f64) -> f64;
#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_unary(symbol: &str) -> Option<UnaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut u8, UnaryMathFn>(p))
        }
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_binary(symbol: &str) -> Option<BinaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut u8, BinaryMathFn>(p))
        }
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn host_pow() -> &'static BinaryMathFn {
    static F: std::sync::OnceLock<Option<BinaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_binary("pow").or(Some(fallback_pow)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

#[cfg(not(target_arch = "wasm32"))]
fn host_cos() -> &'static UnaryMathFn {
    static F: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_unary("cos").or(Some(fallback_cos)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

#[cfg(not(target_arch = "wasm32"))]
fn host_sin() -> &'static UnaryMathFn {
    static F: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_unary("sin").or(Some(fallback_sin)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    x.powf(y)
}

unsafe extern "C" fn fallback_cos(x: f64) -> f64 {
    f64::cos(x)
}

unsafe extern "C" fn fallback_sin(x: f64) -> f64 {
    f64::sin(x)
}

/// CPython `float ** float` (libm `pow`), bit-exact with the reference.
#[cfg(not(target_arch = "wasm32"))]
pub fn pow(x: f64, y: f64) -> f64 {
    unsafe { host_pow()(x, y) }
}

/// `x.powf(y)` (wasm32 has no host CPython libm to dlsym against).
#[cfg(target_arch = "wasm32")]
pub fn pow(x: f64, y: f64) -> f64 {
    unsafe { fallback_pow(x, y) }
}

/// CPython `math.cos`, bit-exact with the reference.
#[cfg(not(target_arch = "wasm32"))]
pub fn cos(x: f64) -> f64 {
    unsafe { host_cos()(x) }
}

/// `f64::cos` (wasm32 has no host CPython libm to dlsym against).
#[cfg(target_arch = "wasm32")]
pub fn cos(x: f64) -> f64 {
    unsafe { fallback_cos(x) }
}

/// CPython `math.sin`, bit-exact with the reference.
#[cfg(not(target_arch = "wasm32"))]
pub fn sin(x: f64) -> f64 {
    unsafe { host_sin()(x) }
}

/// `f64::sin` (wasm32 has no host CPython libm to dlsym against).
#[cfg(target_arch = "wasm32")]
pub fn sin(x: f64) -> f64 {
    unsafe { fallback_sin(x) }
}

/// CPython `round(x)` — round-half-to-even on the double, returning the
/// integer-valued double (before any `int` conversion).
///
/// CPython's `float.__round__` without ndigits runs `_Py_double_round`,
/// which is round-half-to-even (ties to the nearest even integer). Rust's
/// `f64::round_ties_even` implements the same IEEE-754 roundTiesToEven and
/// therefore agrees bit-for-bit on every finite input; the one deliberate
/// correction below is the sign of zero: CPython converts the double result
/// to an `int` (`_PyLong_FromDouble`), and `int(-0.0)` is `0`, so a tie or
/// input that rounds to -0.0 yields `+0.0` once multiplied back by the grid
/// size. `round_ties_even(-0.5)` returns `-0.0`; the callers of this helper
/// must normalise `-0.0` to `+0.0` when they emulate `int * float`.
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

    #[test]
    fn py_round_ties_to_even() {
        assert_eq!(py_round(2.5), 2.0);
        assert_eq!(py_round(3.5), 4.0);
        assert_eq!(py_round(-2.5), -2.0);
        assert_eq!(py_round(-3.5), -4.0);
        assert_eq!(py_round(0.5), 0.0);
        assert_eq!(py_round(-0.5), 0.0); // int(-0.0) == 0
        assert_eq!(py_round(1.5), 2.0);
        assert_eq!(py_round(-1.5), -2.0);
        assert_eq!(py_round(0.0), 0.0);
        assert_eq!(py_round(-0.0), 0.0);
        assert_eq!(py_round(2.4), 2.0);
        assert_eq!(py_round(2.6), 3.0);
        assert_eq!(py_round(-2.6), -3.0);
    }

    #[test]
    fn py_round_large_values() {
        assert_eq!(py_round(1e300), 1e300);
        assert_eq!(py_round(-1e300), -1e300);
        assert_eq!(py_round(4503599627370496.0), 4503599627370496.0);
    }
}

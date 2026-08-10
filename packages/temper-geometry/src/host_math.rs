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
// passing NULL makes `dlsym` return null. That sentence was already here while
// the code below hardcoded `core::ptr::null()` for every target, so on macOS
// every lookup missed ("dlsym(0x0, cos): invalid handle"), `.or(Some(fallback))`
// swallowed it, and the host-libm guarantee this module exists to provide was
// inoperative. The handle is now selected per platform — see `RTLD_DEFAULT`.

#![allow(clippy::missing_safety_doc)]

#[cfg(not(target_arch = "wasm32"))]
use std::ffi::CStr;

#[cfg(not(target_arch = "wasm32"))]
type UnaryMathFn = unsafe extern "C" fn(f64) -> f64;
#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

/// `RTLD_DEFAULT` — "search every loaded object, in load order".
///
/// **The constant is not portable, and getting it wrong fails silently.**
/// glibc defines it as `((void *) 0)`; Darwin's `dlfcn.h` defines it as
/// `((void *) -2)` (`NULL` there is not a valid handle and simply misses).
/// A hardcoded null therefore resolves nothing on macOS, every lookup falls
/// through to the statically-bound `f64::*` fallback, and no test notices —
/// the fallback is a *plausible* answer, just not the host interpreter's.
/// Mirrors `temper-drc-rs/src/pymath.rs` and `temper-thermal/src/hostmath.rs`.
#[cfg(all(not(target_arch = "wasm32"), target_vendor = "apple"))]
const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2

#[cfg(all(not(target_arch = "wasm32"), not(target_vendor = "apple")))]
const RTLD_DEFAULT: *const u8 = core::ptr::null();

/// Resolve `symbol` in the host process's already-loaded libm.
///
/// `symbol` is a `&CStr`, not a `&str`: `dlsym` reads a NUL-terminated C
/// string, and a Rust `&str` carries its length out of band with no NUL, so
/// passing `str::as_ptr` made `dlsym` run off the end of the literal into
/// whatever `.rodata` followed it (measured in this crate before the fix:
/// `strlen("cos".as_ptr()) == 164`).
#[cfg(not(target_arch = "wasm32"))]
fn dlsym_ptr(symbol: &CStr) -> Option<*mut u8> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated C string and `RTLD_DEFAULT` is this
    // platform's "search every loaded object" handle (never dereferenced). A
    // miss returns null, which is checked here.
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

#[cfg(not(target_arch = "wasm32"))]
fn host_pow() -> &'static BinaryMathFn {
    static F: std::sync::OnceLock<Option<BinaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_binary(c"pow").or(Some(fallback_pow)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

#[cfg(not(target_arch = "wasm32"))]
fn host_cos() -> &'static UnaryMathFn {
    static F: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_unary(c"cos").or(Some(fallback_cos)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

#[cfg(not(target_arch = "wasm32"))]
fn host_sin() -> &'static UnaryMathFn {
    static F: std::sync::OnceLock<Option<UnaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| dlsym_unary(c"sin").or(Some(fallback_sin)))
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// The host-libm indirection is actually wired, not silently bypassed.
    ///
    /// Before the Darwin `RTLD_DEFAULT` correction this assertion failed on
    /// macOS: `dlsym(NULL, ...)` reports `invalid handle` there, every lookup
    /// returned `None`, and `.or(Some(fallback_*))` swallowed it — so the
    /// whole module silently degraded to `f64::cos`/`sin`/`powf` while
    /// claiming bit-exactness with the host interpreter. Nothing else in the
    /// suite could notice, because the fallback is a *plausible* answer.
    ///
    /// The `&CStr` signatures are load-bearing for the same reason: with the
    /// old `&str` parameters `dlsym` read past the end of the literal
    /// (measured here: `strlen("cos".as_ptr()) == 164`) and the lookup missed
    /// even once the handle was right.
    #[cfg(not(target_arch = "wasm32"))]
    #[cfg_attr(test, test)]
    fn host_libm_symbols_actually_resolve() {
        assert!(dlsym_unary(c"cos").is_some(), "dlsym could not resolve `cos`");
        assert!(dlsym_unary(c"sin").is_some(), "dlsym could not resolve `sin`");
        assert!(dlsym_binary(c"pow").is_some(), "dlsym could not resolve `pow`");
    }

    /// The resolved functions are the real thing, on the inputs the raster
    /// kernels reach (`2*pi*i/n`).
    #[cfg_attr(test, test)]
    fn host_math_is_sane_on_kernel_inputs() {
        for n in 2..65i64 {
            for i in 0..n {
                let a = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
                assert!(cos(a).abs() <= 1.0);
                assert!(sin(a).abs() <= 1.0);
                assert!((pow(a, 2.0) - a * a).abs() <= 1e-9 * (1.0 + a * a));
            }
        }
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn py_round_large_values() {
        assert_eq!(py_round(1e300), 1e300);
        assert_eq!(py_round(-1e300), -1e300);
        assert_eq!(py_round(4503599627370496.0), 4503599627370496.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(not(target_arch = "wasm32"))] ("host_math::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("host_math::tests::host_math_is_sane_on_kernel_inputs", host_math_is_sane_on_kernel_inputs),
        ("host_math::tests::py_round_ties_to_even", py_round_ties_to_even),
        ("host_math::tests::py_round_large_values", py_round_large_values),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

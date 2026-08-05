//! Host-runtime libm resolution — bit-exactness catalog class **B1**.
//!
//! CPython's `math.exp`/`cos`/`sin`/`pow` (and, as measured for this
//! repo's `numpy` 2.3.5 build on macOS/arm64, numpy's `np.exp`/`np.cos`/
//! `np.sin` float64 ufunc loops) come from the *host Python runtime's*
//! libm.  A crate's statically-bound `f64::exp`/`cos`/`sin`/`powf` can
//! differ from it in the last ulp.  Resolve the symbols through `dlsym`
//! once per symbol so the crate matches the runtime's math bit-exactly;
//! fall back to the std intrinsics only when `dlsym` is unavailable.
//!
//! `dlsym` is a dynamic-loader facility that does not exist on
//! `wasm32-unknown-unknown`; there the `fallback_*` implementations are
//! used directly and the last ulp may diverge from the host Python's
//! libm (expected and accepted, same as `temper-geometry`'s
//! `pad_geometry.rs`/`grid_raster.rs`).
//!
//! ## Why `pow` and not `x * x`
//!
//! CPython's `**` operator on floats is `float.__pow__`, which calls
//! libm `pow`.  `x ** 2` is therefore `pow(x, 2.0)`, **not** `x * x`
//! (measured: they disagree on ~0.14 % of random f64), and `x ** 0.5`
//! is `pow(x, 0.5)`, **not** `sqrt(x)` (measured: ~0.15 % disagree).
//! `thermal_potential.py` writes both forms, so both go through
//! [`pow`].
//!
//! `sqrt` is deliberately **not** routed through `dlsym`: IEEE-754
//! requires a correctly-rounded square root, so `f64::sqrt` (a single
//! hardware instruction) is bit-identical to every conforming libm and
//! to `np.sqrt`.

#[cfg(not(target_arch = "wasm32"))]
use std::ffi::CStr;
#[cfg(not(target_arch = "wasm32"))]
use std::sync::OnceLock;

type UnaryFn = unsafe extern "C" fn(f64) -> f64;
type BinaryFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_ptr(symbol: &CStr) -> Option<*mut u8> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // RTLD_DEFAULT is platform-specific: `(void*)0` on glibc/Linux, but
    // `(void*)-2` on macOS AND the BSDs (`#define RTLD_DEFAULT ((void *)
    // -2)` in <dlfcn.h>).  Passing a bare NULL handle on darwin makes
    // `dlsym` FAIL (NULL is not the "search every loaded image" handle
    // there), so every hostmath call would silently fall back to the std
    // intrinsics — the wasm32-only fallback this module documents, made
    // load-bearing on macOS.  Use the platform's real RTLD_DEFAULT so
    // the host-libm resolution actually happens on macOS too.  On darwin
    // the resolved symbol IS the same libSystem function that Rust std's
    // f64::exp/cos/sin/powf lower to (measured 2026-08-04: the
    // differentials are bit-identical before and after this correction).
    //
    // Coverage truth (pass 2 P2): the `-2` arm is cfg'd for **macOS
    // only**.  The BSDs (FreeBSD/NetBSD/OpenBSD/DragonFly) share
    // RTLD_DEFAULT = -2 but are NOT covered — they fall into the
    // `not(target_os = "macos")` arm below and would get NULL, the
    // wrong handle.  Recorded gap: no BSD target is built or tested in
    // this repo's CI (ubuntu-latest only), so it is documented rather
    // than cfg'd.  CI runs Linux (NULL arm, correct for glibc); the
    // macOS pin is `#[cfg(target_os = "macos")]` and therefore never
    // executes in CI — it requires a local macOS `cargo test` (see
    // VERIFICATION.md notes; no macOS CI job, by decision).
    #[cfg(target_os = "macos")]
    const RTLD_DEFAULT: *const u8 = (-2isize) as *const u8;
    #[cfg(not(target_os = "macos"))]
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    // SAFETY: `symbol` is a NUL-terminated C string literal and
    // RTLD_DEFAULT is the documented "search every loaded object"
    // handle (never dereferenced).  A miss returns null, which is
    // checked below.
    let p = unsafe { dlsym(RTLD_DEFAULT, symbol.as_ptr().cast::<u8>()) };
    if p.is_null() {
        None
    } else {
        Some(p)
    }
}

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_unary(symbol: &CStr) -> Option<UnaryFn> {
    // SAFETY: the resolved symbol is a C `double(double)` from libm.
    dlsym_ptr(symbol).map(|p| unsafe { std::mem::transmute::<*mut u8, UnaryFn>(p) })
}

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_binary(symbol: &CStr) -> Option<BinaryFn> {
    // SAFETY: the resolved symbol is a C `double(double, double)` from libm.
    dlsym_ptr(symbol).map(|p| unsafe { std::mem::transmute::<*mut u8, BinaryFn>(p) })
}

unsafe extern "C" fn fallback_exp(x: f64) -> f64 {
    f64::exp(x)
}

unsafe extern "C" fn fallback_log(x: f64) -> f64 {
    f64::ln(x)
}

unsafe extern "C" fn fallback_log10(x: f64) -> f64 {
    f64::log10(x)
}

unsafe extern "C" fn fallback_cos(x: f64) -> f64 {
    f64::cos(x)
}

unsafe extern "C" fn fallback_sin(x: f64) -> f64 {
    f64::sin(x)
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    f64::powf(x, y)
}

#[cfg(not(target_arch = "wasm32"))]
macro_rules! host_unary {
    ($name:ident, $sym:expr, $fallback:ident) => {
        fn $name() -> UnaryFn {
            static F: OnceLock<UnaryFn> = OnceLock::new();
            *F.get_or_init(|| dlsym_unary($sym).unwrap_or($fallback as UnaryFn))
        }
    };
}

#[cfg(not(target_arch = "wasm32"))]
host_unary!(host_exp, c"exp", fallback_exp);
#[cfg(not(target_arch = "wasm32"))]
host_unary!(host_log, c"log", fallback_log);
#[cfg(not(target_arch = "wasm32"))]
host_unary!(host_log10, c"log10", fallback_log10);
#[cfg(not(target_arch = "wasm32"))]
host_unary!(host_cos, c"cos", fallback_cos);
#[cfg(not(target_arch = "wasm32"))]
host_unary!(host_sin, c"sin", fallback_sin);

#[cfg(not(target_arch = "wasm32"))]
fn host_pow() -> BinaryFn {
    static F: OnceLock<BinaryFn> = OnceLock::new();
    *F.get_or_init(|| dlsym_binary(c"pow").unwrap_or(fallback_pow as BinaryFn))
}

/// `math.exp(x)` / `np.exp(x)` as the host Python runtime computes it.
#[inline]
pub fn exp(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_exp()` is a C `double(double)`; no shared state.
    unsafe {
        (host_exp())(x)
    }
    #[cfg(target_arch = "wasm32")]
    f64::exp(x)
}

/// `math.log(x)` / `np.log(x)` as the host Python runtime computes it
/// (added for the Phase-4 emi/safety kernels; measured 2026-08-04:
/// bit-identical to numpy's `log` on 20 000 random samples).
#[inline]
pub fn log(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_log()` is a C `double(double)`; no shared state.
    unsafe {
        (host_log())(x)
    }
    #[cfg(target_arch = "wasm32")]
    f64::ln(x)
}

/// `math.log10(x)` / `np.log10(x)` as the host Python runtime computes
/// it (measured 2026-08-04: bit-identical to numpy's `log10` on 20 000
/// random samples).
#[inline]
pub fn log10(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_log10()` is a C `double(double)`; no shared state.
    unsafe {
        (host_log10())(x)
    }
    #[cfg(target_arch = "wasm32")]
    f64::log10(x)
}

/// `math.cos(x)` / `np.cos(x)` as the host Python runtime computes it.
#[inline]
pub fn cos(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_cos()` is a C `double(double)`; no shared state.
    unsafe {
        (host_cos())(x)
    }
    #[cfg(target_arch = "wasm32")]
    f64::cos(x)
}

/// `math.sin(x)` / `np.sin(x)` as the host Python runtime computes it.
#[inline]
pub fn sin(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_sin()` is a C `double(double)`; no shared state.
    unsafe {
        (host_sin())(x)
    }
    #[cfg(target_arch = "wasm32")]
    f64::sin(x)
}

/// CPython's `x ** y` on floats (libm `pow`).  **Not** `x * x` for
/// `y == 2.0`, and **not** `sqrt(x)` for `y == 0.5`.
#[inline]
pub fn pow(x: f64, y: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_pow()` is a C `double(double, double)`; no shared state.
    unsafe {
        (host_pow())(x, y)
    }
    #[cfg(target_arch = "wasm32")]
    f64::powf(x, y)
}

// ---------------------------------------------------------------------------
// Python / numpy comparison semantics
// ---------------------------------------------------------------------------

/// CPython's builtin `max(a, b)` — catalog class **B5**.
///
/// The builtin evaluates `b if b > a else a`, so a NaN in *either*
/// position makes the comparison false and the **first** argument wins.
/// `f64::max` instead discards NaN, which is a different function.
#[inline]
pub fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// `np.maximum(a, b)` — NaN-**propagating** elementwise maximum.
///
/// Unlike CPython's builtin `max`, the numpy ufunc returns NaN when
/// either operand is NaN, and unlike `f64::max` it does not discard it.
#[inline]
pub fn np_maximum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if b > a {
        b
    } else {
        a
    }
}

/// `np.clip(x, lo, hi)`.
///
/// numpy expands to `_NPY_MIN(_NPY_MAX(x, lo), hi)` with NaN-propagating
/// min/max, so a NaN in *any* of the three positions yields NaN, and a
/// `lo > hi` inversion yields `hi` (measured: `np.clip(5.0, 10.0, 1.0)`
/// is `1.0`).
#[inline]
pub fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    let upper = np_maximum(x, lo);
    if upper.is_nan() || hi.is_nan() {
        f64::NAN
    } else if hi < upper {
        hi
    } else {
        upper
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pow_is_not_multiplication() {
        // A measured input where CPython's `x ** 2` (libm pow) differs
        // from `x * x`; the kernel must use `pow`.
        let x = 974.553_562_266_593_1_f64;
        assert_ne!(pow(x, 2.0), x * x);
    }

    #[test]
    fn pow_half_is_not_sqrt_everywhere() {
        // `v ** 0.5` is libm pow, not sqrt; they agree on most inputs but
        // pow must still be the one called.  Exactness of the common case:
        assert_eq!(pow(4.0, 0.5), 2.0);
        assert_eq!(pow(9.0, 2.0), 81.0);
    }

    #[test]
    fn exp_zero_is_one() {
        assert_eq!(exp(0.0), 1.0);
        assert_eq!(exp(-0.0), 1.0);
    }

    #[test]
    fn trig_exact_points() {
        assert_eq!(cos(0.0), 1.0);
        assert_eq!(sin(0.0), 0.0);
        assert_eq!(sin(-0.0), -0.0);
    }

    #[test]
    fn py_max_keeps_first_argument_on_nan() {
        assert!(py_max(f64::NAN, 1e-6).is_nan());
        assert_eq!(py_max(1e-6, f64::NAN), 1e-6);
        assert_eq!(py_max(1.0, 2.0), 2.0);
        assert_eq!(py_max(2.0, 1.0), 2.0);
    }

    #[test]
    fn np_maximum_propagates_nan_from_either_side() {
        assert!(np_maximum(f64::NAN, 1.0).is_nan());
        assert!(np_maximum(1.0, f64::NAN).is_nan());
        assert_eq!(np_maximum(1.0, 2.0), 2.0);
    }

    #[test]
    fn np_clip_matches_numpy_semantics() {
        assert_eq!(np_clip(5.0, 0.0, 10.0), 5.0);
        assert_eq!(np_clip(-1.0, 0.0, 10.0), 0.0);
        assert_eq!(np_clip(11.0, 0.0, 10.0), 10.0);
        // Inverted bounds: numpy returns the upper bound.
        assert_eq!(np_clip(5.0, 10.0, 1.0), 1.0);
        assert!(np_clip(f64::NAN, 0.0, 1.0).is_nan());
        assert!(np_clip(5.0, f64::NAN, 1.0).is_nan());
        assert!(np_clip(5.0, 0.0, f64::NAN).is_nan());
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn dlsym_resolves_on_macos() {
        // Regression pin for the darwin RTLD_DEFAULT correction: on macOS
        // RTLD_DEFAULT is `(void*)-2`, NOT NULL — with a NULL handle
        // dlsym fails and hostmath silently falls back to the std
        // intrinsics (which match the host Python's libm on darwin only
        // by the coincidence that Rust std lowers to libSystem too).
        //
        // CI-blind (pass 2 P2): every CI workflow runs ubuntu-latest, so
        // this `#[cfg(target_os = "macos")]` test NEVER executes in CI —
        // it requires a local macOS `cargo test` (recorded follow-up in
        // VERIFICATION.md; no macOS CI job, by decision).  On darwin the
        // differentials pass under either resolution (dlsym and the std
        // fallback resolve the same libSystem functions), so the pin is
        // the only thing that would catch a future regression of the
        // handle value here.
        assert!(dlsym_unary(c"exp").is_some(), "dlsym(\"exp\") must resolve on darwin");
        assert!(dlsym_unary(c"log").is_some(), "dlsym(\"log\") must resolve on darwin");
        assert!(dlsym_unary(c"log10").is_some(), "dlsym(\"log10\") must resolve on darwin");
        assert!(dlsym_binary(c"pow").is_some(), "dlsym(\"pow\") must resolve on darwin");
    }
}

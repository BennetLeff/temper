// Shared "host math" helpers: match the host Python runtime's libm bit-for-bit.
//
// CPython's `x ** y` on floats is libm `pow` (float_pow) — NOT repeated
// multiplication and NOT `sqrt`. Measured in this slice's own environment
// (uv standalone CPython 3.12, darwin arm64): `x ** 2` == `math.pow(x, 2.0)`
// on 0/300000 samples while `x * x` disagreed on 389/300000 — so any kernel
// whose differential must be bit-identical to a Python reference must call
// the exact libm `pow` the host CPython process loaded. `pow` is therefore
// resolved through `dlsym` once per process (same pattern as
// `temper-constraint-compiler/src/constraints/mod.rs`, which documents the
// same code path in full; the migration guide's class-B1 hostmath precedent
// is `temper-thermal/src/hostmath.rs`), with an `f64::powf` fallback on
// platforms where the dlsym route fails.
//
// `dlsym` is a libc/dynamic-loader facility that does not exist on
// wasm32-unknown-unknown (no OS, no dynamic linker), so the dlsym path is
// compiled only off wasm32; on wasm32 the helpers fall back to the f64
// intrinsics. wasm32 builds may diverge from a host Python's libm in the
// last ulp — expected and acceptable: wasm32 has no host CPython process to
// match bit-for-bit against in the first place.
//
// How the two routes actually resolve, per platform:
//
// - **Linux (Ubuntu CI)**: `dlsym(RTLD_DEFAULT, "pow")` — the NULL handle,
//   which on ELF means "search every loaded object" — resolves the
//   process-global glibc libm `pow`: the primary route.
// - **macOS/Darwin**: the NULL handle is NOT `RTLD_DEFAULT` (that is -2 on
//   Darwin) and `dlsym(NULL, "pow")` FAILS ('invalid handle'). This module
//   used to hardcode NULL on every target and treat the resulting miss as
//   load-bearing — "sound by accident", on the argument that the `f64::powf`
//   fallback lowers to a libSystem `_pow` call the runtime exponent stops
//   LLVM folding to `x * x`. That argument rested on an optimiser
//   *non*-guarantee: nothing stops a future rustc/LLVM from constant-folding
//   or inlining a libm shim, and the fallback is only reached because a
//   *different* bug (the wrong handle) fires first. The handle is now
//   correct on Darwin — `dlsym(-2, "pow")` resolves libSystem's `pow`
//   directly — so the primary route is live on macOS as it always was on
//   Linux, and the fallback is genuinely a fallback again.
// - **Windows**: `#[cfg(not(target_arch = "wasm32"))]` compiles the `dlsym`
//   declaration on Windows, where the CRT has no `dlsym` — a link error.
//   Recorded, not fixed: out of scope for the Ubuntu CI target (the guard
//   exists to keep wasm32 builds off the dlsym path).
//
// `math.sqrt` is the correctly-rounded IEEE-754 sqrt → `f64::sqrt` (measured
// 0/200000 mismatches in the batch-1 slice); sqrt is deliberately NOT routed
// through `dlsym`.

#![allow(clippy::missing_safety_doc)]

#[cfg(not(target_arch = "wasm32"))]
use std::ffi::CStr;

#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

/// `RTLD_DEFAULT` — "search every loaded object, in load order".
///
/// **The constant is not portable, and getting it wrong fails silently.**
/// glibc defines it as `((void *) 0)`; Darwin's `dlfcn.h` defines it as
/// `((void *) -2)` (`NULL` there is not a valid handle and simply misses).
#[cfg(all(not(target_arch = "wasm32"), target_vendor = "apple"))]
const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2

#[cfg(all(not(target_arch = "wasm32"), not(target_vendor = "apple")))]
const RTLD_DEFAULT: *const u8 = core::ptr::null();

/// Resolve `symbol` in the host process's already-loaded libm.
///
/// `symbol` is a `&CStr`, not a `&str`: `dlsym` reads a NUL-terminated C
/// string, and a Rust `&str` carries its length out of band with no NUL, so
/// passing `str::as_ptr` made `dlsym` read past the end of the literal into
/// whatever `.rodata` followed it.
#[cfg(not(target_arch = "wasm32"))]
fn dlsym_binary(symbol: &CStr) -> Option<BinaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated C string and `RTLD_DEFAULT` is this
    // platform's "search every loaded object" handle (never dereferenced). A
    // miss returns null, which is checked here. The resolved symbol is a C
    // `double(double, double)` from libm.
    unsafe {
        let p = dlsym(RTLD_DEFAULT, symbol.as_ptr().cast::<u8>());
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
    F.get_or_init(|| dlsym_binary(c"pow").or(Some(fallback_pow)))
        .as_ref()
        .unwrap_or_else(|| unreachable!("fallback always set"))
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    x.powf(y)
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// The host-libm indirection is actually wired, not silently bypassed.
    ///
    /// Before the Darwin `RTLD_DEFAULT` correction this failed on macOS:
    /// `dlsym(NULL, ...)` reports `invalid handle` there, so every lookup
    /// returned `None` and the fallback silently became the live route while
    /// the code claimed bit-exactness with the host interpreter. Nothing else
    /// in the suite could notice — the fallback is a *plausible* answer.
    #[cfg(not(target_arch = "wasm32"))]
    #[cfg_attr(test, test)]
    fn host_libm_symbols_actually_resolve() {
        assert!(dlsym_binary(c"pow").is_some(), "dlsym could not resolve `pow`");
    }

    #[cfg_attr(test, test)]
    fn pow_matches_python_libm_on_known_values() {
        // Values where x*x disagrees with libm pow (measured pre-migration).
        //
        // PLATFORM SENSITIVITY (measured 2026-08-05): which inputs land on a
        // pow-vs-multiply ulp boundary differs per libm. The pre-review
        // discriminator 31.651289106463764 bites on darwin (pow ->
        // 1001.8041021009517, hex 0x1.005edb92751c8p+9) but NOT on Ubuntu CI
        // (glibc 2.39): there pow(31.65..., 2.0) == x*x == 1001.8041021009518.
        // The value below was searched to bite on BOTH libms — verified on
        // darwin arm64 (this machine) and in the CI container image
        // ghcr.io/bennetleff/temper-ci (glibc 2.39), where it yields the SAME
        // absolute value, so the assert holds on both without a cfg split.
        let discriminator = 95.20693529967261_f64;
        // Rust's own x*x:
        let xx = discriminator * discriminator;
        // The host-libm pow (dlsym'd on Linux; the powf fallback, which is
        // the LIVE route on Darwin) must NOT equal the x*x result here.
        let p = pow(discriminator, 2.0);
        assert_ne!(p, xx, "discriminator lost its bite — pow now folds to multiply");
        // And it must match what CPython's math.pow gives for the same input
        // (9064.360529156045, hex 0x1.1b42e25d1c33cp+13) — the same value on
        // darwin libm and glibc (see the platform-sensitivity note above).
        assert_eq!(p, 9064.360529156045_f64);
    }

    #[cfg_attr(test, test)]
    fn pow_special_values() {
        assert_eq!(pow(0.0, 2.0), 0.0);
        assert_eq!(pow(-0.0, 2.0), 0.0);
        assert_eq!(pow(-2.0, 2.0), 4.0);
        assert!(pow(1e300, 2.0).is_infinite());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(not(target_arch = "wasm32"))] ("host_math::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("host_math::tests::pow_matches_python_libm_on_known_values", pow_matches_python_libm_on_known_values),
        ("host_math::tests::pow_special_values", pow_special_values),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal_f64() -> impl Strategy<Value = f64> {
        prop::num::f64::NORMAL
    }

    fn modest_f64() -> impl Strategy<Value = f64> {
        (-1e3f64..1e3).prop_filter("avoid subnormals", |x| x.is_normal() || *x == 0.0)
    }

    proptest! {
        // -----------------------------------------------------------------
        // pow — structural properties
        // -----------------------------------------------------------------

        /// P1. pow(x, 0.0) = 1.0 for any non-zero finite x.
        #[test]
        fn p1_pow_zero_exponent(x in normal_f64()) {
            prop_assume!(x != 0.0);
            prop_assert_eq!(pow(x, 0.0), 1.0,
                "pow({}, 0.0) should be 1.0", x);
        }

        /// P2. pow(x, 1.0) = x for any finite x.
        #[test]
        fn p2_pow_unity_exponent(x in normal_f64()) {
            prop_assert_eq!(pow(x, 1.0), x,
                "pow({}, 1.0) should be {}", x, x);
        }

        /// P3. pow(x, 2.0) is always non-negative for real x.
        #[test]
        fn p3_pow_square_non_negative(x in normal_f64()) {
            let r = pow(x, 2.0);
            prop_assert!(r >= 0.0 || r.is_nan(),
                "pow({}, 2.0) = {} is negative", x, r);
        }

        /// P4. pow(x, y) is finite for modest non-negative inputs.
        #[test]
        fn p4_pow_modest_inputs_finite(
            x in (0.0f64..1e3),
            y in (-50.0f64..50.0),
        ) {
            prop_assume!(x > 0.0 || y > 0.0); // 0^negative = inf
            let r = pow(x, y);
            prop_assert!(r.is_finite(),
                "pow({}, {}) = {} is not finite", x, y, r);
        }

        /// P5. pow(1.0, y) = 1.0 for all finite exponents.
        #[test]
        fn p5_pow_one_to_anything(y in normal_f64()) {
            prop_assert_eq!(pow(1.0, y), 1.0,
                "pow(1.0, {}) should be 1.0, got {}", y, pow(1.0, y));
        }

        /// P6. pow is multiplicative in the exponent: pow(x, a+b) ≈ pow(x,a)*pow(x,b).
        /// (Within a few ulps due to floating-point rounding.)
        #[test]
        fn p6_pow_additive_exponents(
            x in 0.1f64..10.0,
            a in (-10.0f64..10.0),
            b in (-10.0f64..10.0),
        ) {
            prop_assume!(a.is_finite() && b.is_finite() && (a+b).is_finite());
            let lhs = pow(x, a + b);
            let rhs = pow(x, a) * pow(x, b);
            // Both values should be finite and positive, so relative error
            // is meaningful.
            if lhs.is_finite() && rhs.is_finite() && lhs > 0.0 && rhs > 0.0 {
                let rel_err = (lhs - rhs).abs() / lhs.max(rhs);
                prop_assert!(rel_err < 1e-14,
                    "pow({}, {}+{}) = {} != pow({},{})*pow({},{}) = {}, rel_err={}",
                    x, a, b, lhs, x, a, x, b, rhs, rel_err);
            }
        }

        /// P7. pow is consistent with repeated multiplication for integer
        /// exponents: pow(x, 2.0) * pow(x, 2.0) ≈ pow(x, 4.0).
        #[test]
        fn p7_pow_square_then_square(x in modest_f64()) {
            let p2 = pow(x, 2.0);
            let p4a = pow(x, 4.0);
            let p4b = pow(p2, 2.0);
            if p4a.is_finite() && p4a > 0.0 {
                let rel_err = (p4a - p4b).abs() / p4a;
                prop_assert!(rel_err < 1e-14,
                    "pow({},4.0)={} != pow(pow({},2.0),2.0)={}, rel_err={}",
                    x, p4a, x, p4b, rel_err);
            }
        }
    }
}

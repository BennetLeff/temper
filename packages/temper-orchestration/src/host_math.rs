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
        assert!(
            dlsym_binary(c"pow").is_some(),
            "dlsym could not resolve `pow`"
        );
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
        assert_ne!(
            p, xx,
            "discriminator lost its bite — pow now folds to multiply"
        );
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

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' seven properties (P1-P7) below.
    // `proptest` is a dev-dependency (the `proptest-dev-dependency` exclusion
    // class), so its macro bodies cannot be registered directly; each
    // property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly.
    //
    // Host-math sensitivity, checked (per this campaign's own instructions):
    // `pow` resolves through `dlsym` to the host libm on native and falls
    // back to `f64::powf` on wasm32 (this module's own header). NONE of
    // P1-P7 below compares `pow`'s result against a captured host-CPython
    // reference value -- each is a STRUCTURAL relation (identity at
    // exponent 0/1, non-negativity of a square, finiteness, multiplicative
    // consistency between two calls of the SAME `pow` on the SAME platform)
    // that holds under either implementation. Contrast with
    // `pow_matches_python_libm_on_known_values` above (already registered,
    // not a proptest): THAT test pins a captured constant
    // (9064.360529156045) and is correctly wasm32-`expected-fail` via the
    // manifest, not mirrored here -- see `tools/wasm/
    // wasm_expected_failures_orchestration.json`. This module's `pow`
    // therefore mirrors cleanly in full: nothing was excluded on host-math
    // grounds because nothing here depends on it.
    use crate::wasm_campaign_prng::SplitMix64;

    /// A modest-but-wide-magnitude nonzero f64: `sign * (1+frac) * 2^exp`
    /// with `exp` in `-20..20`, `frac` in `[0,1)` -- wide enough to exercise
    /// `pow` across many orders of magnitude without risking overflow in the
    /// structural checks below (unlike `prop::num::f64::NORMAL`'s full
    /// double range, which is not needed here since none of these
    /// properties are about extreme-magnitude edge behavior).
    fn campaign_wide_f64(rng: &mut SplitMix64) -> f64 {
        let sign = if rng.bool() { 1.0 } else { -1.0 };
        let exp = rng.range_i64(-20, 20);
        let frac = 1.0 + rng.next_f64();
        sign * frac * 2f64.powi(exp as i32)
    }

    /// P1. pow(x, 0.0) = 1.0 for any non-zero finite x.
    fn p1_pow_zero_exponent_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = campaign_wide_f64(&mut rng);
        assert_eq!(
            pow(x, 0.0),
            1.0,
            "pow({x}, 0.0) should be 1.0 (seed={seed})"
        );
    }

    /// P2. pow(x, 1.0) = x for any finite x.
    fn p2_pow_unity_exponent_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = campaign_wide_f64(&mut rng);
        assert_eq!(pow(x, 1.0), x, "pow({x}, 1.0) should be {x} (seed={seed})");
    }

    /// P3. pow(x, 2.0) is always non-negative for real x.
    fn p3_pow_square_non_negative_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = campaign_wide_f64(&mut rng);
        let r = pow(x, 2.0);
        assert!(
            r >= 0.0 || r.is_nan(),
            "pow({x}, 2.0) = {r} is negative (seed={seed})"
        );
    }

    /// P4. pow(x, y) is finite for modest non-negative inputs. `x` is drawn
    /// strictly positive (see module note in `p4_pow_modest_inputs_finite`'s
    /// proptest sibling: the domain guard is `x > 0 || y > 0`, needed only
    /// to dodge `0^negative = inf`) so the condition is trivially satisfied
    /// and every seed exercises the real finiteness check, not the guard.
    fn p4_pow_modest_inputs_finite_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = rng.range(1e-6, 1e3);
        let y = rng.range(-50.0, 50.0);
        let r = pow(x, y);
        assert!(
            r.is_finite(),
            "pow({x}, {y}) = {r} is not finite (seed={seed})"
        );
    }

    /// P5. pow(1.0, y) = 1.0 for all finite exponents.
    fn p5_pow_one_to_anything_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let y = campaign_wide_f64(&mut rng);
        let r = pow(1.0, y);
        assert_eq!(r, 1.0, "pow(1.0, {y}) should be 1.0, got {r} (seed={seed})");
    }

    /// P6. pow is multiplicative in the exponent: pow(x, a+b) ~= pow(x,a)*pow(x,b).
    fn p6_pow_additive_exponents_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = rng.range(0.1, 10.0);
        let a = rng.range(-10.0, 10.0);
        let b = rng.range(-10.0, 10.0);
        let lhs = pow(x, a + b);
        let rhs = pow(x, a) * pow(x, b);
        if lhs.is_finite() && rhs.is_finite() && lhs > 0.0 && rhs > 0.0 {
            let rel_err = (lhs - rhs).abs() / lhs.max(rhs);
            assert!(
                rel_err < 1e-14,
                "pow({x}, {a}+{b}) = {lhs} != pow({x},{a})*pow({x},{b}) = {rhs}, rel_err={rel_err} (seed={seed})"
            );
        }
    }

    /// P7. pow is consistent with repeated multiplication for integer
    /// exponents: pow(x, 2.0) * pow(x, 2.0) ~= pow(x, 4.0).
    fn p7_pow_square_then_square_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = rng.range(-1e3, 1e3);
        let p2 = pow(x, 2.0);
        let p4a = pow(x, 4.0);
        let p4b = pow(p2, 2.0);
        if p4a.is_finite() && p4a > 0.0 {
            let rel_err = (p4a - p4b).abs() / p4a;
            assert!(
                rel_err < 1e-14,
                "pow({x},4.0)={p4a} != pow(pow({x},2.0),2.0)={p4b}, rel_err={rel_err} (seed={seed})"
            );
        }
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 7 properties x 20 seeds = 140 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_000() {
        p1_pow_zero_exponent_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_001() {
        p1_pow_zero_exponent_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_002() {
        p1_pow_zero_exponent_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_003() {
        p1_pow_zero_exponent_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_004() {
        p1_pow_zero_exponent_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_005() {
        p1_pow_zero_exponent_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_006() {
        p1_pow_zero_exponent_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_007() {
        p1_pow_zero_exponent_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_008() {
        p1_pow_zero_exponent_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_009() {
        p1_pow_zero_exponent_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_010() {
        p1_pow_zero_exponent_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_011() {
        p1_pow_zero_exponent_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_012() {
        p1_pow_zero_exponent_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_013() {
        p1_pow_zero_exponent_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_014() {
        p1_pow_zero_exponent_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_015() {
        p1_pow_zero_exponent_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_016() {
        p1_pow_zero_exponent_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_017() {
        p1_pow_zero_exponent_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_018() {
        p1_pow_zero_exponent_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p1_pow_zero_exponent_seed_019() {
        p1_pow_zero_exponent_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_000() {
        p2_pow_unity_exponent_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_001() {
        p2_pow_unity_exponent_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_002() {
        p2_pow_unity_exponent_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_003() {
        p2_pow_unity_exponent_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_004() {
        p2_pow_unity_exponent_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_005() {
        p2_pow_unity_exponent_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_006() {
        p2_pow_unity_exponent_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_007() {
        p2_pow_unity_exponent_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_008() {
        p2_pow_unity_exponent_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_009() {
        p2_pow_unity_exponent_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_010() {
        p2_pow_unity_exponent_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_011() {
        p2_pow_unity_exponent_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_012() {
        p2_pow_unity_exponent_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_013() {
        p2_pow_unity_exponent_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_014() {
        p2_pow_unity_exponent_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_015() {
        p2_pow_unity_exponent_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_016() {
        p2_pow_unity_exponent_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_017() {
        p2_pow_unity_exponent_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_018() {
        p2_pow_unity_exponent_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p2_pow_unity_exponent_seed_019() {
        p2_pow_unity_exponent_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_000() {
        p3_pow_square_non_negative_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_001() {
        p3_pow_square_non_negative_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_002() {
        p3_pow_square_non_negative_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_003() {
        p3_pow_square_non_negative_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_004() {
        p3_pow_square_non_negative_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_005() {
        p3_pow_square_non_negative_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_006() {
        p3_pow_square_non_negative_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_007() {
        p3_pow_square_non_negative_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_008() {
        p3_pow_square_non_negative_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_009() {
        p3_pow_square_non_negative_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_010() {
        p3_pow_square_non_negative_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_011() {
        p3_pow_square_non_negative_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_012() {
        p3_pow_square_non_negative_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_013() {
        p3_pow_square_non_negative_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_014() {
        p3_pow_square_non_negative_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_015() {
        p3_pow_square_non_negative_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_016() {
        p3_pow_square_non_negative_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_017() {
        p3_pow_square_non_negative_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_018() {
        p3_pow_square_non_negative_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p3_pow_square_non_negative_seed_019() {
        p3_pow_square_non_negative_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_000() {
        p4_pow_modest_inputs_finite_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_001() {
        p4_pow_modest_inputs_finite_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_002() {
        p4_pow_modest_inputs_finite_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_003() {
        p4_pow_modest_inputs_finite_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_004() {
        p4_pow_modest_inputs_finite_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_005() {
        p4_pow_modest_inputs_finite_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_006() {
        p4_pow_modest_inputs_finite_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_007() {
        p4_pow_modest_inputs_finite_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_008() {
        p4_pow_modest_inputs_finite_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_009() {
        p4_pow_modest_inputs_finite_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_010() {
        p4_pow_modest_inputs_finite_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_011() {
        p4_pow_modest_inputs_finite_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_012() {
        p4_pow_modest_inputs_finite_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_013() {
        p4_pow_modest_inputs_finite_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_014() {
        p4_pow_modest_inputs_finite_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_015() {
        p4_pow_modest_inputs_finite_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_016() {
        p4_pow_modest_inputs_finite_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_017() {
        p4_pow_modest_inputs_finite_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_018() {
        p4_pow_modest_inputs_finite_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p4_pow_modest_inputs_finite_seed_019() {
        p4_pow_modest_inputs_finite_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_000() {
        p5_pow_one_to_anything_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_001() {
        p5_pow_one_to_anything_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_002() {
        p5_pow_one_to_anything_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_003() {
        p5_pow_one_to_anything_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_004() {
        p5_pow_one_to_anything_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_005() {
        p5_pow_one_to_anything_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_006() {
        p5_pow_one_to_anything_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_007() {
        p5_pow_one_to_anything_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_008() {
        p5_pow_one_to_anything_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_009() {
        p5_pow_one_to_anything_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_010() {
        p5_pow_one_to_anything_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_011() {
        p5_pow_one_to_anything_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_012() {
        p5_pow_one_to_anything_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_013() {
        p5_pow_one_to_anything_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_014() {
        p5_pow_one_to_anything_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_015() {
        p5_pow_one_to_anything_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_016() {
        p5_pow_one_to_anything_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_017() {
        p5_pow_one_to_anything_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_018() {
        p5_pow_one_to_anything_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p5_pow_one_to_anything_seed_019() {
        p5_pow_one_to_anything_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_000() {
        p6_pow_additive_exponents_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_001() {
        p6_pow_additive_exponents_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_002() {
        p6_pow_additive_exponents_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_003() {
        p6_pow_additive_exponents_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_004() {
        p6_pow_additive_exponents_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_005() {
        p6_pow_additive_exponents_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_006() {
        p6_pow_additive_exponents_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_007() {
        p6_pow_additive_exponents_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_008() {
        p6_pow_additive_exponents_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_009() {
        p6_pow_additive_exponents_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_010() {
        p6_pow_additive_exponents_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_011() {
        p6_pow_additive_exponents_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_012() {
        p6_pow_additive_exponents_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_013() {
        p6_pow_additive_exponents_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_014() {
        p6_pow_additive_exponents_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_015() {
        p6_pow_additive_exponents_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_016() {
        p6_pow_additive_exponents_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_017() {
        p6_pow_additive_exponents_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_018() {
        p6_pow_additive_exponents_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p6_pow_additive_exponents_seed_019() {
        p6_pow_additive_exponents_impl(19);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_000() {
        p7_pow_square_then_square_impl(0);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_001() {
        p7_pow_square_then_square_impl(1);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_002() {
        p7_pow_square_then_square_impl(2);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_003() {
        p7_pow_square_then_square_impl(3);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_004() {
        p7_pow_square_then_square_impl(4);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_005() {
        p7_pow_square_then_square_impl(5);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_006() {
        p7_pow_square_then_square_impl(6);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_007() {
        p7_pow_square_then_square_impl(7);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_008() {
        p7_pow_square_then_square_impl(8);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_009() {
        p7_pow_square_then_square_impl(9);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_010() {
        p7_pow_square_then_square_impl(10);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_011() {
        p7_pow_square_then_square_impl(11);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_012() {
        p7_pow_square_then_square_impl(12);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_013() {
        p7_pow_square_then_square_impl(13);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_014() {
        p7_pow_square_then_square_impl(14);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_015() {
        p7_pow_square_then_square_impl(15);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_016() {
        p7_pow_square_then_square_impl(16);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_017() {
        p7_pow_square_then_square_impl(17);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_018() {
        p7_pow_square_then_square_impl(18);
    }
    #[cfg_attr(test, test)]
    fn p7_pow_square_then_square_seed_019() {
        p7_pow_square_then_square_impl(19);
    }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(not(target_arch = "wasm32"))] ("host_math::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("host_math::tests::pow_matches_python_libm_on_known_values", pow_matches_python_libm_on_known_values),
        ("host_math::tests::pow_special_values", pow_special_values),
        ("host_math::tests::p1_pow_zero_exponent_seed_000", p1_pow_zero_exponent_seed_000),
        ("host_math::tests::p1_pow_zero_exponent_seed_001", p1_pow_zero_exponent_seed_001),
        ("host_math::tests::p1_pow_zero_exponent_seed_002", p1_pow_zero_exponent_seed_002),
        ("host_math::tests::p1_pow_zero_exponent_seed_003", p1_pow_zero_exponent_seed_003),
        ("host_math::tests::p1_pow_zero_exponent_seed_004", p1_pow_zero_exponent_seed_004),
        ("host_math::tests::p1_pow_zero_exponent_seed_005", p1_pow_zero_exponent_seed_005),
        ("host_math::tests::p1_pow_zero_exponent_seed_006", p1_pow_zero_exponent_seed_006),
        ("host_math::tests::p1_pow_zero_exponent_seed_007", p1_pow_zero_exponent_seed_007),
        ("host_math::tests::p1_pow_zero_exponent_seed_008", p1_pow_zero_exponent_seed_008),
        ("host_math::tests::p1_pow_zero_exponent_seed_009", p1_pow_zero_exponent_seed_009),
        ("host_math::tests::p1_pow_zero_exponent_seed_010", p1_pow_zero_exponent_seed_010),
        ("host_math::tests::p1_pow_zero_exponent_seed_011", p1_pow_zero_exponent_seed_011),
        ("host_math::tests::p1_pow_zero_exponent_seed_012", p1_pow_zero_exponent_seed_012),
        ("host_math::tests::p1_pow_zero_exponent_seed_013", p1_pow_zero_exponent_seed_013),
        ("host_math::tests::p1_pow_zero_exponent_seed_014", p1_pow_zero_exponent_seed_014),
        ("host_math::tests::p1_pow_zero_exponent_seed_015", p1_pow_zero_exponent_seed_015),
        ("host_math::tests::p1_pow_zero_exponent_seed_016", p1_pow_zero_exponent_seed_016),
        ("host_math::tests::p1_pow_zero_exponent_seed_017", p1_pow_zero_exponent_seed_017),
        ("host_math::tests::p1_pow_zero_exponent_seed_018", p1_pow_zero_exponent_seed_018),
        ("host_math::tests::p1_pow_zero_exponent_seed_019", p1_pow_zero_exponent_seed_019),
        ("host_math::tests::p2_pow_unity_exponent_seed_000", p2_pow_unity_exponent_seed_000),
        ("host_math::tests::p2_pow_unity_exponent_seed_001", p2_pow_unity_exponent_seed_001),
        ("host_math::tests::p2_pow_unity_exponent_seed_002", p2_pow_unity_exponent_seed_002),
        ("host_math::tests::p2_pow_unity_exponent_seed_003", p2_pow_unity_exponent_seed_003),
        ("host_math::tests::p2_pow_unity_exponent_seed_004", p2_pow_unity_exponent_seed_004),
        ("host_math::tests::p2_pow_unity_exponent_seed_005", p2_pow_unity_exponent_seed_005),
        ("host_math::tests::p2_pow_unity_exponent_seed_006", p2_pow_unity_exponent_seed_006),
        ("host_math::tests::p2_pow_unity_exponent_seed_007", p2_pow_unity_exponent_seed_007),
        ("host_math::tests::p2_pow_unity_exponent_seed_008", p2_pow_unity_exponent_seed_008),
        ("host_math::tests::p2_pow_unity_exponent_seed_009", p2_pow_unity_exponent_seed_009),
        ("host_math::tests::p2_pow_unity_exponent_seed_010", p2_pow_unity_exponent_seed_010),
        ("host_math::tests::p2_pow_unity_exponent_seed_011", p2_pow_unity_exponent_seed_011),
        ("host_math::tests::p2_pow_unity_exponent_seed_012", p2_pow_unity_exponent_seed_012),
        ("host_math::tests::p2_pow_unity_exponent_seed_013", p2_pow_unity_exponent_seed_013),
        ("host_math::tests::p2_pow_unity_exponent_seed_014", p2_pow_unity_exponent_seed_014),
        ("host_math::tests::p2_pow_unity_exponent_seed_015", p2_pow_unity_exponent_seed_015),
        ("host_math::tests::p2_pow_unity_exponent_seed_016", p2_pow_unity_exponent_seed_016),
        ("host_math::tests::p2_pow_unity_exponent_seed_017", p2_pow_unity_exponent_seed_017),
        ("host_math::tests::p2_pow_unity_exponent_seed_018", p2_pow_unity_exponent_seed_018),
        ("host_math::tests::p2_pow_unity_exponent_seed_019", p2_pow_unity_exponent_seed_019),
        ("host_math::tests::p3_pow_square_non_negative_seed_000", p3_pow_square_non_negative_seed_000),
        ("host_math::tests::p3_pow_square_non_negative_seed_001", p3_pow_square_non_negative_seed_001),
        ("host_math::tests::p3_pow_square_non_negative_seed_002", p3_pow_square_non_negative_seed_002),
        ("host_math::tests::p3_pow_square_non_negative_seed_003", p3_pow_square_non_negative_seed_003),
        ("host_math::tests::p3_pow_square_non_negative_seed_004", p3_pow_square_non_negative_seed_004),
        ("host_math::tests::p3_pow_square_non_negative_seed_005", p3_pow_square_non_negative_seed_005),
        ("host_math::tests::p3_pow_square_non_negative_seed_006", p3_pow_square_non_negative_seed_006),
        ("host_math::tests::p3_pow_square_non_negative_seed_007", p3_pow_square_non_negative_seed_007),
        ("host_math::tests::p3_pow_square_non_negative_seed_008", p3_pow_square_non_negative_seed_008),
        ("host_math::tests::p3_pow_square_non_negative_seed_009", p3_pow_square_non_negative_seed_009),
        ("host_math::tests::p3_pow_square_non_negative_seed_010", p3_pow_square_non_negative_seed_010),
        ("host_math::tests::p3_pow_square_non_negative_seed_011", p3_pow_square_non_negative_seed_011),
        ("host_math::tests::p3_pow_square_non_negative_seed_012", p3_pow_square_non_negative_seed_012),
        ("host_math::tests::p3_pow_square_non_negative_seed_013", p3_pow_square_non_negative_seed_013),
        ("host_math::tests::p3_pow_square_non_negative_seed_014", p3_pow_square_non_negative_seed_014),
        ("host_math::tests::p3_pow_square_non_negative_seed_015", p3_pow_square_non_negative_seed_015),
        ("host_math::tests::p3_pow_square_non_negative_seed_016", p3_pow_square_non_negative_seed_016),
        ("host_math::tests::p3_pow_square_non_negative_seed_017", p3_pow_square_non_negative_seed_017),
        ("host_math::tests::p3_pow_square_non_negative_seed_018", p3_pow_square_non_negative_seed_018),
        ("host_math::tests::p3_pow_square_non_negative_seed_019", p3_pow_square_non_negative_seed_019),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_000", p4_pow_modest_inputs_finite_seed_000),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_001", p4_pow_modest_inputs_finite_seed_001),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_002", p4_pow_modest_inputs_finite_seed_002),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_003", p4_pow_modest_inputs_finite_seed_003),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_004", p4_pow_modest_inputs_finite_seed_004),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_005", p4_pow_modest_inputs_finite_seed_005),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_006", p4_pow_modest_inputs_finite_seed_006),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_007", p4_pow_modest_inputs_finite_seed_007),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_008", p4_pow_modest_inputs_finite_seed_008),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_009", p4_pow_modest_inputs_finite_seed_009),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_010", p4_pow_modest_inputs_finite_seed_010),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_011", p4_pow_modest_inputs_finite_seed_011),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_012", p4_pow_modest_inputs_finite_seed_012),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_013", p4_pow_modest_inputs_finite_seed_013),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_014", p4_pow_modest_inputs_finite_seed_014),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_015", p4_pow_modest_inputs_finite_seed_015),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_016", p4_pow_modest_inputs_finite_seed_016),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_017", p4_pow_modest_inputs_finite_seed_017),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_018", p4_pow_modest_inputs_finite_seed_018),
        ("host_math::tests::p4_pow_modest_inputs_finite_seed_019", p4_pow_modest_inputs_finite_seed_019),
        ("host_math::tests::p5_pow_one_to_anything_seed_000", p5_pow_one_to_anything_seed_000),
        ("host_math::tests::p5_pow_one_to_anything_seed_001", p5_pow_one_to_anything_seed_001),
        ("host_math::tests::p5_pow_one_to_anything_seed_002", p5_pow_one_to_anything_seed_002),
        ("host_math::tests::p5_pow_one_to_anything_seed_003", p5_pow_one_to_anything_seed_003),
        ("host_math::tests::p5_pow_one_to_anything_seed_004", p5_pow_one_to_anything_seed_004),
        ("host_math::tests::p5_pow_one_to_anything_seed_005", p5_pow_one_to_anything_seed_005),
        ("host_math::tests::p5_pow_one_to_anything_seed_006", p5_pow_one_to_anything_seed_006),
        ("host_math::tests::p5_pow_one_to_anything_seed_007", p5_pow_one_to_anything_seed_007),
        ("host_math::tests::p5_pow_one_to_anything_seed_008", p5_pow_one_to_anything_seed_008),
        ("host_math::tests::p5_pow_one_to_anything_seed_009", p5_pow_one_to_anything_seed_009),
        ("host_math::tests::p5_pow_one_to_anything_seed_010", p5_pow_one_to_anything_seed_010),
        ("host_math::tests::p5_pow_one_to_anything_seed_011", p5_pow_one_to_anything_seed_011),
        ("host_math::tests::p5_pow_one_to_anything_seed_012", p5_pow_one_to_anything_seed_012),
        ("host_math::tests::p5_pow_one_to_anything_seed_013", p5_pow_one_to_anything_seed_013),
        ("host_math::tests::p5_pow_one_to_anything_seed_014", p5_pow_one_to_anything_seed_014),
        ("host_math::tests::p5_pow_one_to_anything_seed_015", p5_pow_one_to_anything_seed_015),
        ("host_math::tests::p5_pow_one_to_anything_seed_016", p5_pow_one_to_anything_seed_016),
        ("host_math::tests::p5_pow_one_to_anything_seed_017", p5_pow_one_to_anything_seed_017),
        ("host_math::tests::p5_pow_one_to_anything_seed_018", p5_pow_one_to_anything_seed_018),
        ("host_math::tests::p5_pow_one_to_anything_seed_019", p5_pow_one_to_anything_seed_019),
        ("host_math::tests::p6_pow_additive_exponents_seed_000", p6_pow_additive_exponents_seed_000),
        ("host_math::tests::p6_pow_additive_exponents_seed_001", p6_pow_additive_exponents_seed_001),
        ("host_math::tests::p6_pow_additive_exponents_seed_002", p6_pow_additive_exponents_seed_002),
        ("host_math::tests::p6_pow_additive_exponents_seed_003", p6_pow_additive_exponents_seed_003),
        ("host_math::tests::p6_pow_additive_exponents_seed_004", p6_pow_additive_exponents_seed_004),
        ("host_math::tests::p6_pow_additive_exponents_seed_005", p6_pow_additive_exponents_seed_005),
        ("host_math::tests::p6_pow_additive_exponents_seed_006", p6_pow_additive_exponents_seed_006),
        ("host_math::tests::p6_pow_additive_exponents_seed_007", p6_pow_additive_exponents_seed_007),
        ("host_math::tests::p6_pow_additive_exponents_seed_008", p6_pow_additive_exponents_seed_008),
        ("host_math::tests::p6_pow_additive_exponents_seed_009", p6_pow_additive_exponents_seed_009),
        ("host_math::tests::p6_pow_additive_exponents_seed_010", p6_pow_additive_exponents_seed_010),
        ("host_math::tests::p6_pow_additive_exponents_seed_011", p6_pow_additive_exponents_seed_011),
        ("host_math::tests::p6_pow_additive_exponents_seed_012", p6_pow_additive_exponents_seed_012),
        ("host_math::tests::p6_pow_additive_exponents_seed_013", p6_pow_additive_exponents_seed_013),
        ("host_math::tests::p6_pow_additive_exponents_seed_014", p6_pow_additive_exponents_seed_014),
        ("host_math::tests::p6_pow_additive_exponents_seed_015", p6_pow_additive_exponents_seed_015),
        ("host_math::tests::p6_pow_additive_exponents_seed_016", p6_pow_additive_exponents_seed_016),
        ("host_math::tests::p6_pow_additive_exponents_seed_017", p6_pow_additive_exponents_seed_017),
        ("host_math::tests::p6_pow_additive_exponents_seed_018", p6_pow_additive_exponents_seed_018),
        ("host_math::tests::p6_pow_additive_exponents_seed_019", p6_pow_additive_exponents_seed_019),
        ("host_math::tests::p7_pow_square_then_square_seed_000", p7_pow_square_then_square_seed_000),
        ("host_math::tests::p7_pow_square_then_square_seed_001", p7_pow_square_then_square_seed_001),
        ("host_math::tests::p7_pow_square_then_square_seed_002", p7_pow_square_then_square_seed_002),
        ("host_math::tests::p7_pow_square_then_square_seed_003", p7_pow_square_then_square_seed_003),
        ("host_math::tests::p7_pow_square_then_square_seed_004", p7_pow_square_then_square_seed_004),
        ("host_math::tests::p7_pow_square_then_square_seed_005", p7_pow_square_then_square_seed_005),
        ("host_math::tests::p7_pow_square_then_square_seed_006", p7_pow_square_then_square_seed_006),
        ("host_math::tests::p7_pow_square_then_square_seed_007", p7_pow_square_then_square_seed_007),
        ("host_math::tests::p7_pow_square_then_square_seed_008", p7_pow_square_then_square_seed_008),
        ("host_math::tests::p7_pow_square_then_square_seed_009", p7_pow_square_then_square_seed_009),
        ("host_math::tests::p7_pow_square_then_square_seed_010", p7_pow_square_then_square_seed_010),
        ("host_math::tests::p7_pow_square_then_square_seed_011", p7_pow_square_then_square_seed_011),
        ("host_math::tests::p7_pow_square_then_square_seed_012", p7_pow_square_then_square_seed_012),
        ("host_math::tests::p7_pow_square_then_square_seed_013", p7_pow_square_then_square_seed_013),
        ("host_math::tests::p7_pow_square_then_square_seed_014", p7_pow_square_then_square_seed_014),
        ("host_math::tests::p7_pow_square_then_square_seed_015", p7_pow_square_then_square_seed_015),
        ("host_math::tests::p7_pow_square_then_square_seed_016", p7_pow_square_then_square_seed_016),
        ("host_math::tests::p7_pow_square_then_square_seed_017", p7_pow_square_then_square_seed_017),
        ("host_math::tests::p7_pow_square_then_square_seed_018", p7_pow_square_then_square_seed_018),
        ("host_math::tests::p7_pow_square_then_square_seed_019", p7_pow_square_then_square_seed_019),
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

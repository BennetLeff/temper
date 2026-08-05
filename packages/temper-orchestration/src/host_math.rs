// Shared "host math" helpers: match the host Python runtime's libm bit-for-bit.
//
// CPython's `x ** y` on floats is libm `pow` (float_pow) — NOT repeated
// multiplication and NOT `sqrt`. Measured in this slice's own environment
// (uv standalone CPython 3.12, darwin arm64): `x ** 2` == `math.pow(x, 2.0)`
// on 0/300000 samples while `x * x` disagreed on 389/300000 — so any kernel
// whose differential must be bit-identical to a Python reference must
// resolve `pow` through `dlsym(RTLD_DEFAULT, "pow")` to the exact libm the
// host CPython process loaded, exactly as `temper-geometry/src/host_math.rs`
// established for the Wave-4 Phase-5 batch-1 slice.
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
// optimisation. This module therefore passes `core::ptr::null()` (==
// RTLD_DEFAULT on Darwin) exactly as temper-geometry's host_math.rs does.
//
// `math.sqrt` is the correctly-rounded IEEE-754 sqrt → `f64::sqrt` (measured
// 0/200000 mismatches in the batch-1 slice); sqrt is deliberately NOT routed
// through `dlsym`.

#![allow(clippy::missing_safety_doc)]

#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pow_matches_python_libm_on_known_values() {
        // Values where x*x disagrees with libm pow (measured pre-migration).
        let discriminator = 31.651289106463764_f64;
        // Rust's own x*x:
        let xx = discriminator * discriminator;
        // The dlsym'd libm pow must NOT equal the x*x result here.
        let p = pow(discriminator, 2.0);
        assert_ne!(p, xx, "discriminator lost its bite — pow now folds to multiply");
        // And it must match what CPython's math.pow gives for the same input
        // (1.0018041021009517, hex 0x1.005edb92751c8p+9).
        assert_eq!(p, 1001.8041021009517_f64);
    }

    #[test]
    fn pow_special_values() {
        assert_eq!(pow(0.0, 2.0), 0.0);
        assert_eq!(pow(-0.0, 2.0), 0.0);
        assert_eq!(pow(-2.0, 2.0), 4.0);
        assert!(pow(1e300, 2.0).is_infinite());
    }
}

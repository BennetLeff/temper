//! CPython floating-point semantics, replicated bit-for-bit.
//!
//! Every function here exists because the obvious Rust spelling of the
//! same expression is a *different function* from the one CPython
//! evaluates. They are grouped by the Wave-4 divergence catalog class
//! they close (`docs/wave4-discipline-contract.md` §2):
//!
//! | class | CPython | naive Rust | why they differ |
//! |---|---|---|---|
//! | B1 | `math.cos/sin/acos` | `f64::cos/sin/acos` | the host runtime ships its own libm |
//! | B4 | `math.hypot` | `f64::hypot` | CPython uses a Dekker double-double `vector_norm` |
//! | B5 | `max`/`min` | `f64::max`/`min`/`clamp` | the builtins keep the **first** argument; `clamp` panics |
//! | B7 | `x ** 2` | `x * x` | `**` is libm `pow` (LLVM folds `powf(x, 2.0)` to a multiply) |
//! | B3 | `round(x, 9)` | `(x * 1e9).round() / 1e9` | CPython rounds in **decimal**, via dtoa/strtod |
//!
//! Deliberately free of `pyo3`: these are pure kernels, unit-testable
//! without a Python interpreter, and shared by `validation.rs` and
//! `dfm.rs`.

use std::ffi::CStr;
use std::fmt::Write as _;
use std::sync::OnceLock;

// ---------------------------------------------------------------------------
// B1 — host-runtime libm resolution
// ---------------------------------------------------------------------------
//
// The extension's statically-bound `f64::cos`/`sin`/`acos`/`powf` are not
// necessarily the same functions the *host CPython* calls: `uv`'s
// standalone interpreters ship their own libm, and a last-ulp difference
// there is a differential failure. `dlsym(RTLD_DEFAULT, ...)` resolves the
// symbol in the running process, which is the interpreter, so the crate
// tracks whatever libm that interpreter uses.
//
// `f64::powf` is additionally unusable as a proxy even when `dlsym`
// misses: LLVM folds `llvm.pow.f64` with a *constant* exponent
// (`powf(x, 2.0)` -> `x * x`, `powf(x, 0.5)` -> `sqrt(x)`), and both
// disagree with libm `pow` on this platform (measured in `validation.rs`:
// 262/200000 and 274/200000 respectively).
//
// Same pattern and rationale as `temper-thermal/src/hostmath.rs` and
// `temper-geometry/src/pad_geometry.rs`; kept crate-local so the DRC
// extension does not grow a dependency edge for four symbols.

type UnaryFn = unsafe extern "C" fn(f64) -> f64;
type BinaryFn = unsafe extern "C" fn(f64, f64) -> f64;

/// `RTLD_DEFAULT` — "search every loaded object, in load order".
///
/// **The constant is not portable, and getting it wrong fails silently.**
/// glibc defines it as `((void *) 0)`; Darwin's `dlfcn.h` defines it as
/// `((void *) -2)` (`NULL` there means something else and simply misses).
/// A hardcoded null therefore resolves nothing on macOS, `dlsym_ptr`
/// returns `None`, every lookup falls through to the statically-bound
/// `f64::*` fallback, and no test notices — the fallback is a *plausible*
/// answer, just not the host interpreter's. `host_libm_symbols_actually_resolve`
/// is the assertion that closes that hole.
#[cfg(all(
    not(target_arch = "wasm32"),
    any(target_os = "macos", target_os = "ios", target_vendor = "apple")
))]
const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2

#[cfg(all(
    not(target_arch = "wasm32"),
    not(any(target_os = "macos", target_os = "ios", target_vendor = "apple"))
))]
const RTLD_DEFAULT: *const u8 = core::ptr::null();

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_ptr(symbol: &CStr) -> Option<*mut u8> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated C string literal and
    // `RTLD_DEFAULT` is this platform's "search every loaded object"
    // handle. A miss returns null, which is checked here.
    let p = unsafe { dlsym(RTLD_DEFAULT, symbol.as_ptr().cast::<u8>()) };
    if p.is_null() { None } else { Some(p) }
}

/// `wasm32` has no dynamic loader, so every lookup misses and the
/// statically-bound `f64::*` fallbacks below are used instead.
///
/// **This is a `cfg`, not a stub for convenience.** Declaring `dlsym` on
/// `wasm32` emits an `env.dlsym` *import* into the module, and a module with a
/// non-empty import list cannot be instantiated by a bare isolate — the host
/// must supply JS glue for it. That is the exact failure the Phase 0 plan's
/// rung-2/rung-3 distinction predicted, and it is invisible to `cargo check`
/// and even to `cargo build`: it only appears when something instantiates the
/// module.
///
/// The semantics are right, not merely expedient. The indirection exists to
/// track *the host CPython interpreter's* libm, and in a Worker there is no
/// interpreter to track — the module's own compiled-in libm is the only
/// implementation present. The parent plan already anticipates the
/// consequence: WASM and native builds may differ in the last ULP, which R15
/// makes tolerable by keeping the tier advisory.
#[cfg(target_arch = "wasm32")]
fn dlsym_ptr(_symbol: &CStr) -> Option<*mut u8> {
    None
}

unsafe extern "C" fn fallback_cos(x: f64) -> f64 {
    f64::cos(x)
}
unsafe extern "C" fn fallback_sin(x: f64) -> f64 {
    f64::sin(x)
}
unsafe extern "C" fn fallback_acos(x: f64) -> f64 {
    f64::acos(x)
}
unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    f64::powf(x, y)
}

fn resolve_unary(symbol: &CStr, fallback: UnaryFn) -> UnaryFn {
    // SAFETY: the resolved symbol is a C `double(double)` from libm.
    dlsym_ptr(symbol)
        .map(|p| unsafe { std::mem::transmute::<*mut u8, UnaryFn>(p) })
        .unwrap_or(fallback)
}

/// `math.cos` — the host interpreter's libm `cos` (B1).
#[inline]
pub fn cos(x: f64) -> f64 {
    static F: OnceLock<UnaryFn> = OnceLock::new();
    let f = *F.get_or_init(|| resolve_unary(c"cos", fallback_cos));
    // SAFETY: `f` is a C `double(double)`; no shared state.
    unsafe { f(x) }
}

/// `math.sin` — the host interpreter's libm `sin` (B1).
#[inline]
pub fn sin(x: f64) -> f64 {
    static F: OnceLock<UnaryFn> = OnceLock::new();
    let f = *F.get_or_init(|| resolve_unary(c"sin", fallback_sin));
    // SAFETY: `f` is a C `double(double)`; no shared state.
    unsafe { f(x) }
}

/// `math.acos` — the host interpreter's libm `acos` (B1).
///
/// CPython raises `ValueError` for `|x| > 1`; every call site in this
/// crate clamps first, so the domain error is unreachable and the raw
/// libm result (NaN) is returned instead of being translated.
#[inline]
pub fn acos(x: f64) -> f64 {
    static F: OnceLock<UnaryFn> = OnceLock::new();
    let f = *F.get_or_init(|| resolve_unary(c"acos", fallback_acos));
    // SAFETY: `f` is a C `double(double)`; no shared state.
    unsafe { f(x) }
}

/// CPython's `x ** y` on floats — libm `pow` (B7).
///
/// **Not** `x * x` for `y == 2.0` and **not** `sqrt(x)` for `y == 0.5`.
#[inline]
pub fn pow(x: f64, y: f64) -> f64 {
    static F: OnceLock<BinaryFn> = OnceLock::new();
    let f = *F.get_or_init(|| {
        // SAFETY: the resolved symbol is a C `double(double, double)`.
        dlsym_ptr(c"pow")
            .map(|p| unsafe { std::mem::transmute::<*mut u8, BinaryFn>(p) })
            .unwrap_or(fallback_pow)
    });
    // SAFETY: `f` is a C `double(double, double)`; no shared state.
    unsafe { f(x, y) }
}

/// CPython `math.sqrt` (libm `sqrt`), bit-exact with the reference — the
/// statically-bound `f64::sqrt` can differ from the host runtime's libm in
/// the last ulp, same class as `pow`.
pub fn sqrt(x: f64) -> f64 {
    static F: OnceLock<UnaryFn> = OnceLock::new();
    let f = *F.get_or_init(|| {
        // SAFETY: the resolved symbol is a C `double(double)`.
        dlsym_ptr(c"sqrt")
            .map(|p| unsafe { std::mem::transmute::<*mut u8, UnaryFn>(p) })
            .unwrap_or(fallback_sqrt)
    });
    // SAFETY: `f` is a C `double(double)`; no shared state.
    unsafe { f(x) }
}

unsafe extern "C" fn fallback_sqrt(x: f64) -> f64 {
    f64::sqrt(x)
}

/// CPython's `float.__pow__` overflowed — `OverflowError(ERANGE,
/// strerror(ERANGE))`. See [`py_pow`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PowOverflow;/// CPython's `x ** y` on floats, **including its errno handling**.
///
/// `float_pow` runs `errno = 0; ix = pow(iv, iw); _Py_ADJUST_ERANGE1(ix);`
/// and raises `OverflowError` when `errno` ends up `ERANGE`.
/// `_Py_ADJUST_ERANGE1` sets `ERANGE` whenever the result is `±HUGE_VAL`,
/// and *clears* it when the result is exactly `0.0`. So:
///
/// * `1e200 ** 2` raises — it is **not** `inf` (measured);
/// * `1e-160 ** 2` is `1e-320`, a subnormal, and does **not** raise;
/// * `1e-200 ** 2` underflows to `0.0` and does **not** raise;
/// * `inf ** 2` is `inf` — `float_pow` returns before `errno` is armed
///   when either operand is non-finite.
///
/// [`pow`] is the raw libm call and is what `validation.rs` uses; this is
/// the spelling the DFM kernels need, because their corpus reaches the
/// overflowing magnitudes.
#[inline]
pub fn py_pow(x: f64, y: f64) -> Result<f64, PowOverflow> {
    let r = pow(x, y);
    if x.is_finite() && y.is_finite() && r.is_infinite() {
        return Err(PowOverflow);
    }
    Ok(r)
}

/// `math.degrees(x)` — CPython evaluates `x * radToDeg` with
/// `radToDeg = 180.0 / pi` folded once at compile time (B1/B7).
///
/// It is **one** multiply by a precomputed constant, not `(x * 180.0) / pi`.
#[inline]
pub fn degrees(x: f64) -> f64 {
    const RAD_TO_DEG: f64 = 180.0 / std::f64::consts::PI;
    x * RAD_TO_DEG
}

// ---------------------------------------------------------------------------
// B5 — the builtins `max` / `min`
// ---------------------------------------------------------------------------

/// CPython's builtin `max(a, b)`.
///
/// The builtin evaluates `b if b > a else a`, so a NaN in *either*
/// position makes the comparison false and the **first** argument wins.
/// It also keeps the first argument on a signed-zero tie
/// (`max(0.0, -0.0)` is `0.0`; `max(-0.0, 0.0)` is `-0.0`).
/// `f64::max` discards NaN and is a different function.
#[inline]
pub fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// CPython's builtin `min(a, b)` — `b if b < a else a`; see [`py_max`].
#[inline]
pub fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

// ---------------------------------------------------------------------------
// B4 — `math.hypot`
// ---------------------------------------------------------------------------

/// CPython's `math.hypot` (the 2-argument `vector_norm`), replicated
/// exactly: a Dekker double-double compensated norm with fma-based
/// `dl_mul`. Rust's `f64::hypot` (libm) differs from it in the last ulp.
///
/// **Source of truth:** `packages/temper-geometry/src/pad_geometry.rs`
/// `py_hypot`, ported here line for line rather than depended on, because
/// that function is `pub(crate)` by design and a path dependency would
/// pull `rand` and an optional `pyo3` extension-module into the DRC
/// extension's build graph for one function. `tests::hypot_pinned_values`
/// pins the outputs so the two copies cannot drift silently.
///
/// See CPython `Modules/mathmodule.c`, `vector_norm`.
pub fn py_hypot(x: f64, y: f64) -> f64 {
    // INFINITY IS CHECKED BEFORE NaN, and the order is the whole point.
    //
    // CPython's `math_hypot_impl` scans its coordinates recording `found_nan`,
    // but returns `+inf` as soon as any coordinate is infinite -- infinity wins
    // over NaN. Measured against CPython 3.12:
    //
    //     math.hypot(inf, nan) == inf      math.hypot(nan, inf) == inf
    //     math.hypot(-inf, nan) == inf
    //     math.hypot(nan, 1.0) == nan      math.hypot(1.0, nan) == nan
    //
    // This file had the guards in the opposite order and returned NaN where
    // CPython returns inf. Each guard in isolation is correct -- the previous
    // comment here claimed "both guards are exact CPython semantics", which is
    // true of each and false of the pair -- so only an input that is BOTH
    // infinite and NaN-bearing exposes it, which no fixture happened to carry.
    //
    // `temper-geometry`'s copy of this function already had the correct order,
    // fixed when the Wave-4 router_v6 constraints-geometry differential hit
    // `hypot(-inf, nan)` for real: it arises in `point_to_segment_distance`
    // when a segment endpoint is infinite and the clamped projection produces
    // a NaN coordinate. Two crates disagreeing on the same primitive is the
    // divergence class this port exists to eliminate, so this copy is brought
    // into line rather than left to be discovered a third time.
    if x.is_infinite() || y.is_infinite() {
        return f64::INFINITY;
    }
    if x.is_nan() || y.is_nan() {
        return f64::NAN;
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
        // Subnormal inputs: convert to normals, recurse, rescale
        // (CPython's `if (max_e < -1023)` branch). Reachable from the
        // denormal-band corpus rows (B8).
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

// ---------------------------------------------------------------------------
// B3 — `round(x, ndigits)` and `round(x)`
// ---------------------------------------------------------------------------

/// A fixed-capacity `core::fmt::Write` sink, so [`py_round`] does not
/// allocate on the hot path.
struct FixedBuf {
    buf: [u8; 512],
    len: usize,
}

impl FixedBuf {
    fn new() -> Self {
        Self { buf: [0u8; 512], len: 0 }
    }
    fn as_str(&self) -> Option<&str> {
        core::str::from_utf8(&self.buf[..self.len]).ok()
    }
}

impl core::fmt::Write for FixedBuf {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        let b = s.as_bytes();
        let end = self.len + b.len();
        if end > self.buf.len() {
            return Err(core::fmt::Error);
        }
        self.buf[self.len..end].copy_from_slice(b);
        self.len = end;
        Ok(())
    }
}

/// CPython's `round(x, ndigits)` for a `float` — **decimal** rounding.
///
/// CPython's `double_round` does not scale by a power of ten: it formats
/// `x` to `ndigits` places with the correctly-rounded `_Py_dg_dtoa`
/// (mode 3) and re-parses the decimal string with `_Py_dg_strtod`. That
/// is exactly `format!("{:.n$}")` + `str::parse`, both of which are
/// correctly rounded in Rust; the scale-round-unscale spelling
/// (`(x * 1e9).round_ties_even() / 1e9`) double-rounds and is a
/// different function.
///
/// dtoa breaks exact decimal ties to even. For `ndigits == 9` an exact
/// tie is unreachable — a tie needs `x` to be an exact odd multiple of
/// `5e-10`, and `5e-10` is not a dyadic rational — so the tie rule is
/// documented rather than relied on. Non-finite `x` rounds to itself
/// (CPython `float___round___impl`).
pub fn py_round(x: f64, ndigits: usize) -> f64 {
    if !x.is_finite() {
        return x;
    }
    let mut fb = FixedBuf::new();
    if write!(&mut fb, "{:.*}", ndigits, x).is_ok()
        && let Some(s) = fb.as_str()
        && let Ok(v) = s.parse::<f64>()
    {
        return v;
    }
    // Values whose fixed-point rendering exceeds the stack buffer (|x|
    // beyond ~1e500, unreachable for an f64) fall back to a heap format.
    format!("{:.*}", ndigits, x).parse::<f64>().unwrap_or(x)
}

/// CPython's `round(x)` with no `ndigits` — round-half-to-**even**,
/// yielding an integer.
///
/// CPython computes `rounded = round(x)` (C `round`, half away from zero)
/// and then corrects exact halves with `2.0 * round(x / 2.0)`, which is
/// precisely `f64::round_ties_even`. `f64::round` alone is half-away and
/// a different function.
#[inline]
pub fn py_round_to_int(x: f64) -> f64 {
    x.round_ties_even()
}

#[cfg(any(test, feature = "wasm-test-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn py_max_keeps_the_first_argument() {
        let nan = f64::NAN;
        // the two nestings the DFM cluster uses, with the values CPython
        // produces (pinned by the differential's trap tests)
        assert_eq!(py_max(-1.0, py_min(1.0, nan)), 1.0);
        assert_eq!(py_min(1.0, py_max(-1.0, nan)), -1.0);
        assert_eq!(py_max(0.0, py_min(nan, 10.0)), 0.0);
        assert!(py_max(nan, 1.0).is_nan());
        assert_eq!(py_max(1.0, nan), 1.0);
        assert_eq!(py_max(0.0, -0.0).to_bits(), 0.0f64.to_bits());
        assert_eq!(py_max(-0.0, 0.0).to_bits(), (-0.0f64).to_bits());
    }

    #[cfg_attr(test, test)]
    /// Infinity beats NaN, pinned against real CPython 3.12.
    ///
    /// Regression test for the guard ORDER. This file checked NaN first and
    /// returned NaN where CPython returns inf; `temper-geometry`'s copy already
    /// had it right. Only an input that is both infinite and NaN-bearing shows
    /// the difference, which is why no existing fixture caught it.
    #[cfg_attr(test, test)]
    fn hypot_infinity_beats_nan() {
        assert!(py_hypot(f64::INFINITY, f64::NAN).is_infinite());
        assert!(py_hypot(f64::NAN, f64::INFINITY).is_infinite());
        assert!(py_hypot(f64::NEG_INFINITY, f64::NAN).is_infinite());
        assert!(py_hypot(f64::INFINITY, f64::NAN) > 0.0, "must be +inf");
        // ...and a NaN with no infinity present is still NaN.
        assert!(py_hypot(f64::NAN, 1.0).is_nan());
        assert!(py_hypot(1.0, f64::NAN).is_nan());
    }

    #[cfg_attr(test, test)]
    fn hypot_pinned_values() {
        // `math.hypot(...).hex()` from CPython 3.12, including the two
        // where `f64::hypot` disagrees in the last ulp and the denormal
        // band that drives `vector_norm_2`'s subnormal branch.
        assert_eq!(py_hypot(0.3, 0.3), 0.4242640687119285);
        assert_eq!(py_hypot(3.0, 4.0), 5.0);
        assert_eq!(py_hypot(1e-300, 1e-300), 1.414213562373095e-300);
        // the subnormal branch of `vector_norm_2`: CPython returns the
        // argument itself here, which `f64::hypot` does not
        assert_eq!(py_hypot(5e-324, 5e-324), 5e-324);
        assert!(py_hypot(f64::NAN, 1.0).is_nan());
        // Was `.is_nan()`, which pinned the defect this file carried: CPython
        // returns +inf here (infinity wins over NaN in `math_hypot_impl`), so
        // the old assertion asserted the bug. Measured on CPython 3.12:
        //     math.hypot(inf, nan) == inf
        assert_eq!(py_hypot(f64::INFINITY, f64::NAN), f64::INFINITY);
        assert_eq!(py_hypot(f64::NEG_INFINITY, 1.0), f64::INFINITY);
        assert_eq!(py_hypot(0.0, 0.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn pow_is_not_a_multiply_or_a_sqrt() {
        // The two exponents the cluster uses. If LLVM ever folds these
        // into `x * x` / `sqrt(x)` the differential goes red; this test
        // catches it in the crate instead.
        let mut pow2_differs = 0usize;
        let mut pow_half_differs = 0usize;
        let mut state = 0x2545_F491_4F6C_DD1Du64;
        for _ in 0..200_000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let x = (state >> 11) as f64 / (1u64 << 53) as f64 * 200.0 - 100.0;
            if pow(x, 2.0) != x * x {
                pow2_differs += 1;
            }
        }
        for c in 1..100_000u32 {
            if pow(f64::from(c), 0.5) != f64::from(c).sqrt() {
                pow_half_differs += 1;
            }
        }
        assert!(
            pow2_differs > 0,
            "pow(x, 2.0) == x * x everywhere -- LLVM has folded the intrinsic, \
             or the platform libm changed; the B7 pin is no longer honoured"
        );
        assert!(
            pow_half_differs > 0,
            "pow(c, 0.5) == sqrt(c) everywhere -- see above"
        );
    }

    #[cfg_attr(test, test)]
    fn round_is_decimal_not_scaled() {
        // The load-bearing case: the exact 60-degree vertex.
        assert_eq!(py_round(59.99999999999999, 9), 60.0);
        assert_eq!(py_round(0.0, 9), 0.0);
        assert_eq!(py_round(180.0, 9), 180.0);
        assert_eq!(py_round(1e-300, 9), 0.0);
        assert_eq!(py_round(2.5e-9, 9), 3e-9);
        assert_eq!(py_round(1.5e-9, 9), 1e-9);
        assert!(py_round(f64::NAN, 9).is_nan());
        assert_eq!(py_round(f64::INFINITY, 9), f64::INFINITY);
        // half-to-even at the integer level (CPython `round(2.5) == 2`)
        assert_eq!(py_round_to_int(2.5), 2.0);
        assert_eq!(py_round_to_int(3.5), 4.0);
        assert_eq!(py_round_to_int(-2.5), -2.0);
    }

    #[cfg_attr(test, test)]
    fn host_libm_symbols_actually_resolve() {
        // Mutation-sweep survivor M06 (`pymath::cos/sin` -> `f64::cos/sin`)
        // did not change any differential result, because on this host the
        // two resolve to the same libm. That makes M06 an equivalent mutant
        // HERE and says nothing about CI, whose `uv`-standalone interpreter
        // ships its own libm -- the divergence `temper-geometry` measured
        // and the reason the indirection exists at all.
        //
        // What IS falsifiable, and what this asserts, is that the
        // indirection is actually wired: if `dlsym` silently missed and
        // every call fell through to the statically-bound fallback, the
        // protection would be absent and nothing else in the suite would
        // notice.
        assert!(dlsym_ptr(c"cos").is_some(), "dlsym could not resolve `cos`");
        assert!(dlsym_ptr(c"sin").is_some(), "dlsym could not resolve `sin`");
        assert!(dlsym_ptr(c"acos").is_some(), "dlsym could not resolve `acos`");
        assert!(dlsym_ptr(c"pow").is_some(), "dlsym could not resolve `pow`");
        // and that the resolved functions are sane on the values the spoke
        // kernel reaches (`2*pi*i/n`), whichever libm they came from
        for n in 2..65i64 {
            for i in 0..n {
                let a = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
                assert!(cos(a).abs() <= 1.0);
                assert!(sin(a).abs() <= 1.0);
            }
        }
    }

    #[cfg_attr(test, test)]
    fn degrees_is_a_single_multiply() {
        // CPython's `math.degrees` is `x * (180.0 / pi)`; the other
        // association `(x * 180.0) / pi` is a different function.
        let rad_to_deg = 180.0 / std::f64::consts::PI;
        let mut differs = 0usize;
        let mut state = 0x1234_5678_9abc_def0u64;
        for _ in 0..100_000 {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let x = (state >> 11) as f64 / (1u64 << 53) as f64 * std::f64::consts::PI;
            assert_eq!(degrees(x), x * rad_to_deg);
            if degrees(x) != (x * 180.0) / std::f64::consts::PI {
                differs += 1;
            }
        }
        assert!(differs > 0, "the two associations agree everywhere -- trap stale");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("pymath::tests::py_max_keeps_the_first_argument", py_max_keeps_the_first_argument),
        ("pymath::tests::hypot_pinned_values", hypot_pinned_values),
        ("pymath::tests::pow_is_not_a_multiply_or_a_sqrt", pow_is_not_a_multiply_or_a_sqrt),
        ("pymath::tests::round_is_decimal_not_scaled", round_is_decimal_not_scaled),
        ("pymath::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("pymath::tests::degrees_is_a_single_multiply", degrees_is_a_single_multiply),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

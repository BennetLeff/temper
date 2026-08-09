//! Aesthetic quality metric kernels — the Rust home of
//! `temper_placer/metrics/aesthetic.py`'s `compute_aesthetic_score`
//! (Wave 4 — `metrics/aesthetic` migration).
//!
//! The pinned reference is the verbatim pre-migration module copied into
//! `packages/temper-placer/tests/metrics/test_aesthetic_rust_differential.py`
//! (`_oracle_compute_aesthetic_score`).  That copy carries a *dead* branch
//! — its `get_prefix_groups` was retired with the JAX migration and now
//! raises `NotImplementedError`, so the committed module could never
//! complete for a non-empty placement.  The migration resolves that dead
//! call to the module's **own specified consequence** — with no prefix
//! groups, `alignment_score` is the module's vacuous `1.0` default — and
//! the divergence (raise → computed score) is recorded in this crate's
//! `VERIFICATION.md` rather than smuggled in.  This kernel reproduces the
//! module's remaining arithmetic bit-for-bit.
//!
//! Bit-exactness catalog classes that bite here
//! (`docs/wave4-discipline-contract.md` §2):
//!
//! - **B1 — `np.log` is the host libm `log`.**  The oracle computes
//!   `np.log(probs + 1e-8)`.  Measured on numpy 2.3.5 (200k random
//!   samples): `np.log` is bit-identical to the host C library `log` on
//!   this platform, so the kernel resolves `log` through
//!   `dlsym(RTLD_DEFAULT, "log")` exactly as [`placement_metrics`]
//!   resolves `pow` — never `f64::ln`.
//! - **B11 — `np.sum` is pairwise, but the entropy sum is only 4 terms.**
//!   numpy sums naively below 8 elements, so the 4-term entropy reduction
//!   is a plain left-to-right fold from `0.0`.  (The `grid_score` mean is
//!   a count of booleans, exact in every summation strategy.)
//! - **B12 — numpy ufunc comparison semantics.**  `np.minimum(a, b)`
//!   *propagates* NaN from either operand and returns the **second**
//!   argument when `a == b`; `np.clip(x, lo, hi)` expands to
//!   `min(max(x, lo), hi)`.  Rust's `f64::min`/`clamp` are different
//!   functions; [`np_minimum`] / [`np_clip`] replicate numpy's.
//! - **NEP 50 — the grid-snap chain runs in the source dtype.**  When
//!   `state.positions` is float32 (the `PlacementState` default), the whole
//!   `np.mod` → `np.minimum` → `< 0.01` chain computes in f32, and the
//!   `snapped` booleans can differ from the f64 chain for coordinates near
//!   a grid boundary (measured discriminator
//!   `x = 578.5099839972382`: f64-snapped, f32-not).  `np.argmax` likewise
//!   compares in the rotation array's dtype.  The two `*_are_f32` flags
//!   reproduce this exactly (the same flag the
//!   `connectivity_clustering_score` migration already needed).
//! - **B5 — `np.argmax` first-max-wins with NaN-propagating selection.**
//!   Measured: a NaN element wins over every finite value, ties keep the
//!   first index, and once a NaN is selected it is never displaced.
//!   [`numpy_argmax`] reproduces the measured loop, not Rust's
//!   `max_by_key` (which returns the *last* maximum).
//!
//! All arithmetic is closed-form (no recursion, no iteration over
//! variable-size state beyond the fixed 4-bin histogram), so the
//! induction requirement (R1e) is discharged by the structural argument
//! recorded in `VERIFICATION.md`.

#[cfg(not(target_arch = "wasm32"))]
use std::sync::OnceLock;

#[cfg(not(target_arch = "wasm32"))]
type UnaryMathFn = unsafe extern "C" fn(f64) -> f64;

/// The dynamic loader's "search every loaded image" pseudo-handle.
///
/// Platform-specific and easy to get wrong (Darwin's `RTLD_DEFAULT` is
/// `((void *) -2)`, glibc's is `NULL`) — see the equivalent constant in
/// `placement_metrics.rs` for the full writeup.
#[cfg(not(target_arch = "wasm32"))]
const RTLD_DEFAULT: *const u8 = if cfg!(target_vendor = "apple") {
    -2isize as *const u8
} else {
    core::ptr::null()
};

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_unary(symbol: &str) -> Option<UnaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated literal at every call site; a null
    // result is checked before the transmute, and the transmuted signature
    // matches the C prototype of every symbol we resolve (`double f(double)`).
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
fn host_log() -> Option<&'static UnaryMathFn> {
    static LOG: OnceLock<Option<UnaryMathFn>> = OnceLock::new();
    LOG.get_or_init(|| dlsym_unary("log\0")).as_ref()
}

/// CPython `math.log(x)` / numpy `np.log(x)` for finite float operands.
///
/// Routes through the host Python runtime's libm `log` so the last ulp
/// matches (catalog class B1).  Falls back to the std intrinsic only when
/// `dlsym` cannot resolve the symbol.
#[inline]
pub fn py_log(x: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    {
        if let Some(f) = host_log() {
            // SAFETY: resolved `log` from the host libm; the signature matches.
            return unsafe { f(x) };
        }
    }
    x.ln()
}

/// `np.minimum(a, b)` — NaN-**propagating** elementwise minimum (B12).
///
/// Returns the **second** argument when `a == b` (numpy's ufunc evaluates
/// `a < b ? a : b`), which makes `np.minimum(+0.0, -0.0)` the `-0.0`.
/// `f64::min` discards NaN and is a different function.
#[inline]
pub fn np_minimum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a < b {
        a
    } else {
        b
    }
}

/// The same [`np_minimum`] semantics in the float32 grid-snap chain.
#[inline]
fn np_minimum_f32(a: f32, b: f32) -> f32 {
    if a.is_nan() || b.is_nan() {
        f32::NAN
    } else if a < b {
        a
    } else {
        b
    }
}

/// `np.clip(x, lo, hi)` — expands to `min(max(x, lo), hi)` with
/// NaN-propagating min/max (B12), so a NaN in any of the three positions
/// yields NaN and an inverted `lo > hi` yields `hi`.
#[inline]
pub fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    let upper = if x.is_nan() || lo.is_nan() {
        f64::NAN
    } else if x > lo {
        x
    } else {
        lo
    };
    if upper.is_nan() || hi.is_nan() {
        f64::NAN
    } else if hi < upper {
        hi
    } else {
        upper
    }
}

/// numpy's floored modulo (`x % m`), bit-for-bit for `m = 0.5`.
///
/// `np.mod` is the *floored* remainder, `x - m * floor(x / m)` (same sign
/// as the divisor) — not C `fmod`.  For the kernel's `grid_size` (a power
/// of two) every step is exact: `x / m` and `floor` are exact, `m * floor`
/// is exact, and the final subtraction is exact by Sterbenz (the two
/// operands are within a factor of two and their exact difference is
/// representable), so the closed form matches numpy bit-for-bit.  NaN and
/// infinity inputs propagate to NaN exactly as numpy's does.
#[inline]
pub fn np_mod(x: f64, m: f64) -> f64 {
    x - m * (x / m).floor()
}

/// The same floored modulo in the float32 grid-snap chain (NEP 50).
#[inline]
fn np_mod_f32(x: f32, m: f32) -> f32 {
    x - m * (x / m).floor()
}

/// `np.argmax` over a 4-element row, in the source array's dtype.
///
/// Measured numpy semantics (`numpy 2.3.5`, f64 and f32):
///
/// - the *first* occurrence of the maximum wins (strict `>` replacement);
/// - a NaN element wins over every finite value, and once selected is never
///   displaced (so the first NaN's index is returned);
/// - comparisons happen in the array's dtype — for a float32 source two
///   f64-distinct logits can be f32-identical, moving the argmax
///   (measured discriminator `(0.9999999999999999, 1.0, 0.0, 0.0)`:
///   f64 → 1, f32 → 0).
pub fn numpy_argmax(row: &(f64, f64, f64, f64), as_f32: bool) -> usize {
    let vals = [row.0, row.1, row.2, row.3];
    let mut best_i = 0usize;
    if as_f32 {
        let mut best = vals[0] as f32;
        for (i, &v) in vals.iter().enumerate().skip(1) {
            let vi = v as f32;
            let replace = (vi.is_nan() && !best.is_nan())
                || (!vi.is_nan() && !best.is_nan() && vi > best);
            if replace {
                best = vi;
                best_i = i;
            }
        }
    } else {
        let mut best = vals[0];
        for (i, &v) in vals.iter().enumerate().skip(1) {
            let replace = (v.is_nan() && !best.is_nan())
                || (!v.is_nan() && !best.is_nan() && v > best);
            if replace {
                best = v;
                best_i = i;
            }
        }
    }
    best_i
}

/// The four sub-scores `compute_aesthetic_score` returns.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct AestheticScores {
    pub grid_snap_score: f64,
    pub orientation_score: f64,
    pub prefix_alignment_score: f64,
    pub aesthetic_index: f64,
}

/// `compute_aesthetic_score`'s numeric kernel.
///
/// Returns `None` for an empty placement — the oracle's `n == 0` early
/// return, which yields only `{"aesthetic_index": 1.0}` — and `Some(...)`
/// otherwise.  `positions_are_f32` / `rotations_are_f32` carry the source
/// dtype so the NEP 50 grid-snap and argmax comparisons reproduce the
/// numpy chain bit-for-bit (see the module doc).
///
/// The oracle's alignment factor is a constant here: its prefix-group
/// machinery (`get_prefix_groups`) was retired with the JAX migration and
/// the module's own `else` branch makes the score `1.0` when no groups
/// exist.  See `VERIFICATION.md` for the recorded divergence decision.
pub fn compute_aesthetic_score(
    positions: &[(f64, f64)],
    rotations: &[(f64, f64, f64, f64)],
    grid_size: f64,
    positions_are_f32: bool,
    rotations_are_f32: bool,
) -> Option<AestheticScores> {
    let n = positions.len();
    if n == 0 {
        return None;
    }

    // 1. Grid Snap Score — the whole chain runs in the source dtype.
    let mut snapped: u64 = 0;
    if positions_are_f32 {
        let m: f32 = grid_size as f32;
        let threshold: f32 = 0.01;
        for &(x, y) in positions {
            let xf = x as f32;
            let yf = y as f32;
            let x_off = np_mod_f32(xf, m);
            let y_off = np_mod_f32(yf, m);
            let dist_x = np_minimum_f32(x_off, m - x_off);
            let dist_y = np_minimum_f32(y_off, m - y_off);
            if dist_x < threshold && dist_y < threshold {
                snapped += 1;
            }
        }
    } else {
        let m = grid_size;
        let threshold = 0.01;
        for &(x, y) in positions {
            let x_off = np_mod(x, m);
            let y_off = np_mod(y, m);
            let dist_x = np_minimum(x_off, m - x_off);
            let dist_y = np_minimum(y_off, m - y_off);
            if dist_x < threshold && dist_y < threshold {
                snapped += 1;
            }
        }
    }
    // np.mean over a bool array is exactly count/n in f64.
    let grid_score = snapped as f64 / n as f64;

    // 2. Orientation Score.
    let mut counts = [0u64; 4];
    for row in rotations {
        counts[numpy_argmax(row, rotations_are_f32)] += 1;
    }
    // `probs = counts / n` then the 4-term `np.sum(p * log(p + 1e-8))`,
    // which numpy reduces naively (below 8 elements) and then negates.
    let mut entropy = 0.0_f64;
    for &c in &counts {
        let p = c as f64 / n as f64;
        entropy += p * py_log(p + 1e-8);
    }
    let entropy = -entropy;
    let orientation_score = np_clip(1.0 - entropy / 1.386, 0.0, 1.0);

    // 3. Alignment Score — the vacuous `1.0` default (no prefix groups).
    let alignment_score = 1.0_f64;

    // 4. Aggregate — the oracle's exact grouping, left to right.
    let aesthetic_index = (grid_score * 0.4) + (orientation_score * 0.3)
        + (alignment_score * 0.3);

    Some(AestheticScores {
        grid_snap_score: grid_score,
        orientation_score,
        prefix_alignment_score: alignment_score,
        aesthetic_index,
    })
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::*;

    #[test]
    fn np_minimum_returns_second_argument_on_ties() {
        // Measured: np.minimum(+0.0, -0.0) is -0.0, np.minimum(-0.0, +0.0)
        // is +0.0 — the ufunc returns b when a == b.
        assert!(np_minimum(0.0, -0.0).is_sign_negative());
        assert!(np_minimum(-0.0, 0.0).is_sign_positive());
    }

    #[test]
    fn np_minimum_propagates_nan_from_either_side() {
        assert!(np_minimum(f64::NAN, 1.0).is_nan());
        assert!(np_minimum(1.0, f64::NAN).is_nan());
        assert_eq!(np_minimum(1.0, 2.0), 1.0);
    }

    #[test]
    fn np_clip_matches_numpy_semantics() {
        assert_eq!(np_clip(5.0, 0.0, 10.0), 5.0);
        assert_eq!(np_clip(-1.0, 0.0, 10.0), 0.0);
        assert_eq!(np_clip(11.0, 0.0, 10.0), 10.0);
        assert!(np_clip(f64::NAN, 0.0, 10.0).is_nan());
        // Inverted lo > hi returns hi, it does not panic.
        assert_eq!(np_clip(5.0, 10.0, 1.0), 1.0);
    }

    #[test]
    fn np_mod_is_floored_not_fmod() {
        // numpy: mod(-0.25, 0.5) == 0.25 (floored), not -0.25 (fmod).
        assert_eq!(np_mod(-0.25, 0.5), 0.25);
        // -1.3 (f64) + 1.5 is 0.19999999999999996 — numpy's measured bits
        // (0x1.9999999999998p-3), reproduced by the exact floored formula.
        assert_eq!(np_mod(-1.3, 0.5).to_bits(), 0.19999999999999996_f64.to_bits());
        assert_eq!(np_mod(1.7, 0.5).to_bits(), 0.19999999999999996_f64.to_bits());
        assert_eq!(np_mod(-0.5, 0.5), 0.0);
        assert!(np_mod(f64::NAN, 0.5).is_nan());
        assert!(np_mod(f64::INFINITY, 0.5).is_nan());
    }

    #[test]
    fn numpy_argmax_first_max_wins_and_nan_propagates() {
        assert_eq!(numpy_argmax(&(0.5, 1.5, 1.5, 0.0), false), 1);
        // NaN wins over every finite value; first NaN is never displaced.
        assert_eq!(numpy_argmax(&(1.0, f64::NAN, 0.5, 0.0), false), 1);
        assert_eq!(numpy_argmax(&(f64::NAN, 2.0, 0.0, 0.0), false), 0);
        assert_eq!(numpy_argmax(&(1.0, f64::NAN, f64::NAN, 0.0), false), 1);
        // The dtype flag is load-bearing: f64 sees the second entry larger,
        // f32 rounds both to 1.0 and the first-max tie keeps index 0.
        let row = (0.9999999999999999, 1.0, 0.0, 0.0);
        assert_eq!(numpy_argmax(&row, false), 1);
        assert_eq!(numpy_argmax(&row, true), 0);
    }

    #[test]
    fn py_log_resolves_to_host_libm() {
        // Exact operand pins plumbing; the differential pins the ulp.
        assert_eq!(py_log(1.0), 0.0);
        assert_eq!(py_log(1e-8), -18.420680743952367);
    }

    #[test]
    fn empty_placement_is_none() {
        assert_eq!(
            compute_aesthetic_score(&[], &[], 0.5, false, false),
            None
        );
    }

    #[test]
    fn grid_snap_f32_flag_changes_the_result() {
        // Measured discriminator: x = 578.5099839972382 snaps in f64 but
        // not in f32 — the whole reason the dtype flag exists.
        let positions = [(578.5099839972382, 0.0)];
        let rotations = [(0.0, 0.0, 1.0, 0.0)];
        let as_f64 = compute_aesthetic_score(&positions, &rotations, 0.5, false, false)
            .unwrap();
        let as_f32 = compute_aesthetic_score(&positions, &rotations, 0.5, true, false)
            .unwrap();
        assert_eq!(as_f64.grid_snap_score, 1.0);
        assert_eq!(as_f32.grid_snap_score, 0.0);
        assert_ne!(as_f64.aesthetic_index.to_bits(), as_f32.aesthetic_index.to_bits());
    }

    #[test]
    fn alignment_is_the_vacuous_default() {
        let scores = compute_aesthetic_score(
            &[(0.0, 0.0), (1.0, 1.0)],
            &[(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)],
            0.5,
            false,
            false,
        )
        .unwrap();
        assert_eq!(scores.prefix_alignment_score, 1.0);
    }

    #[test]
    fn uniform_rotations_score_zero_orientation() {
        // probs = 0.25 each -> entropy ~ log(4) > 1.386 -> clipped to 0.
        // One row per rotation index so the histogram is truly uniform.
        let scores = compute_aesthetic_score(
            &[(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)],
            &[
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ],
            0.5,
            false,
            false,
        )
        .unwrap();
        assert_eq!(scores.orientation_score, 0.0);
    }
}

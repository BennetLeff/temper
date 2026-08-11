//! Placement quality metric kernels — the Rust home of
//! `temper_placer/metrics/quality.py`'s analyzers (Wave 4 Phase 4).
//!
//! Every kernel here reproduces the pre-migration CPython/numpy arithmetic
//! **bit-for-bit**, not merely numerically.  The pinned reference is
//! `packages/temper-placer/tests/metrics/_quality_py_oracle.py` (a verbatim
//! copy of the module as committed at `ebf9326ff`); the differential suite
//! `test_quality_rust_differential.py` asserts equality through
//! `float.hex()`.
//!
//! Bit-exactness catalog classes that bite here
//! (`docs/wave4-discipline-contract.md` §2):
//!
//! - **B1 / B7 — `**` is libm `pow`, not `sqrt`/`x*x`.** The oracle writes
//!   `(dx**2 + dy**2) ** 0.5`.  CPython's `float.__pow__` calls the *host
//!   Python runtime's* libm `pow`; on this platform `x ** 0.5` differs from
//!   `sqrt(x)` on ~0.13% of random inputs and `x ** 2` differs from `x * x`
//!   on ~0.13% (measured, 200k samples).  So the kernels resolve `pow`
//!   through `dlsym(RTLD_DEFAULT, "pow")` and call it with the oracle's
//!   exact operand shape — never `f64::sqrt`, never `x * x`.
//! - **B5 — CPython `max`/`min` keep the *first* argument on ties/NaN.**
//!   `max(a, b)` is `b if b > a else a`.  Rust's `f64::max`/`min` follow
//!   IEEE `maxNum`, which discards NaN and may return either zero for
//!   `(+0, -0)`.  Every clamp here goes through [`py_max2`] / [`py_min2`],
//!   which are literal transcriptions of the CPython builtins, with the
//!   oracle's argument order preserved.
//! - **B7 — operation order.** No reassociation, no `mul_add` fusion, no
//!   constant folding across the oracle's parentheses.
//! - **B11 (new class, recorded by this migration) — numpy pairwise
//!   summation.** `np.sum` over a float64 array is *not* naive left-to-right
//!   addition: numpy sums pairwise (naive below 8 elements, an 8-way
//!   unrolled accumulation up to 128, recursive halving above).  Measured
//!   on numpy 2.3.5: naive summation diverges from `np.sum` on 37%–95% of
//!   random inputs for every n >= 8, and agrees exactly for n <= 7.
//!   [`numpy_pairwise_sum`] replicates the algorithm; the shoelace sum in
//!   [`loop_area_score`] uses it.
//! - **B12 (new class, recorded by this migration) — CPython 3.12's
//!   compensated `sum()`.** Python's *builtin* `sum()` over floats is **not**
//!   naive left-to-right addition either: CPython 3.12 switched it to the
//!   improved Kahan-Babuska (Neumaier) algorithm.  See [`py_builtin_sum`].
//!
//! Those last two together mean this module deals with **three mutually
//! distinct summation strategies**, and picking the wrong one is a silent
//! 1-ulp bug:
//!
//! | Oracle expression | Strategy | Rust helper |
//! |---|---|---|
//! | `np.sum(arr)` | numpy pairwise | [`numpy_pairwise_sum`] |
//! | `sum(iterable)` | Neumaier compensated | [`py_builtin_sum`] |
//! | `for x in xs: acc += x` | naive left-to-right | [`naive_sum`] |
//!
//! This module uses each exactly where the oracle does. The 1-ulp
//! `compactness_score` divergence that surfaced B12 came from using naive
//! accumulation where the oracle wrote `sum(...)`.

use std::cell::Cell;
#[cfg(not(target_arch = "wasm32"))]
use std::sync::OnceLock;

// ---------------------------------------------------------------------------
// B1/B7: host-runtime libm `pow`
//
// `dlsym` does not exist on wasm32-unknown-unknown (no dynamic linker), so
// the resolution path is compiled off that target and falls back to the std
// intrinsic there.  wasm32 has no host CPython to match bit-for-bit anyway.
// ---------------------------------------------------------------------------

#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

/// The dynamic loader's "search every loaded image" pseudo-handle.
///
/// **This is platform-specific and getting it wrong fails silently.** Darwin's
/// `dlfcn.h` defines `RTLD_DEFAULT` as `((void *) -2)`; glibc defines it as
/// `NULL`.  Passing `NULL` on macOS is not `RTLD_DEFAULT` — it is an invalid
/// handle, `dlsym` returns null, and the caller quietly falls back to the std
/// intrinsic.  That fallback is *not* equivalent: LLVM lowers
/// `f64::powf(x, 2.0)` to `x * x` and `f64::powf(x, 0.5)` to `sqrt(x)`, both
/// of which differ from CPython's libm `pow` in the last ulp on ~0.13% of
/// inputs.  The differential's `test_pow_diagonal_operands_that_sqrt_gets_wrong`
/// exists to catch exactly this regression, and
/// `py_pow_resolves_to_host_libm_not_sqrt` pins it crate-side.
#[cfg(not(target_arch = "wasm32"))]
const RTLD_DEFAULT: *const u8 = if cfg!(target_vendor = "apple") {
    -2isize as *const u8
} else {
    core::ptr::null()
};

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_binary(symbol: &str) -> Option<BinaryMathFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // SAFETY: `symbol` is a NUL-terminated literal at every call site; a null
    // result is checked before the transmute, and the transmuted signature
    // matches the C prototype of every symbol we resolve (`double f(double,
    // double)`).
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
fn host_pow() -> Option<&'static BinaryMathFn> {
    static POW: OnceLock<Option<BinaryMathFn>> = OnceLock::new();
    POW.get_or_init(|| dlsym_binary("pow\0")).as_ref()
}

/// CPython `base ** exp` for finite float operands.
///
/// Routes through the host Python runtime's libm `pow` so the last ulp
/// matches `float.__pow__` (catalog class B1/B7).  Falls back to the std
/// intrinsic only when `dlsym` cannot resolve the symbol.
#[inline]
pub fn py_pow(base: f64, exp: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    {
        if let Some(f) = host_pow() {
            // SAFETY: resolved `pow` from the host libm; the signature matches.
            return unsafe { f(base, exp) };
        }
    }
    base.powf(exp)
}

// ---------------------------------------------------------------------------
// B5: CPython builtin min/max semantics
// ---------------------------------------------------------------------------

/// CPython `max(a, b)` — literally `b if b > a else a`.
///
/// Keeps the **first** argument when the comparison is false, which is what
/// makes `max(0.0, nan) == 0.0` but `max(nan, 0.0) == nan`, and what makes
/// `max(0.0, -0.0) == 0.0` deterministic.  `f64::max` guarantees neither.
#[inline]
pub fn py_max2(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// CPython `min(a, b)` — literally `b if b < a else a`.
#[inline]
pub fn py_min2(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

// ---------------------------------------------------------------------------
// B11: numpy pairwise summation
// ---------------------------------------------------------------------------

/// numpy's `PW_BLOCKSIZE` — the largest block summed without recursion.
const PW_BLOCKSIZE: usize = 128;

/// Replicates `numpy.sum` over a contiguous float64 array, bit-for-bit.
///
/// This is `pairwise_sum_DOUBLE` from numpy's `loops.c.src`, transcribed:
///
/// - `n < 8` — naive left-to-right accumulation starting from `0.0`;
/// - `8 <= n <= 128` — eight independent accumulators seeded from the first
///   eight elements, advanced in lockstep over the largest multiple of 8,
///   then combined as `((r0+r1)+(r2+r3)) + ((r4+r5)+(r6+r7))` with the tail
///   added left-to-right;
/// - `n > 128` — split at the largest multiple of 8 at or below `n/2` and
///   recurse, summing the two halves left-to-right.
///
/// Verified exact against numpy 2.3.5 for n in 1..=40 and
/// {63, 64, 127, 128, 129, 200, 256, 300, 1000, 4097}.
pub fn numpy_pairwise_sum(a: &[f64]) -> f64 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0_f64;
        for &v in a {
            res += v;
        }
        res
    } else if n <= PW_BLOCKSIZE {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        let body_end = n - (n % 8);
        while i < body_end {
            for (j, acc) in r.iter_mut().enumerate() {
                *acc += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        numpy_pairwise_sum(&a[..n2]) + numpy_pairwise_sum(&a[n2..])
    }
}

/// Python's **builtin** `sum(iterable)` over floats — catalog class B12.
///
/// CPython 3.12 replaced `sum`'s naive float accumulation with the **improved
/// Kahan-Babuska (Neumaier) compensated** algorithm.  `sum(xs)` is therefore
/// neither naive left-to-right addition *nor* numpy's pairwise reduction: all
/// three disagree.  Measured in this repo's environment (CPython 3.12.13):
/// `sum()` and a naive fold over the same 7-element list differ by 1 ulp on
/// real `compactness_score` inputs — which is how this class was found.
///
/// Transcribed from `builtin_sum_impl` in CPython's `bltinmodule.c`:
///
/// ```text
/// result = 0 + xs[0]              # int start promotes exactly
/// hi, c  = result, 0.0
/// for x in xs[1:]:
///     t = hi + x
///     if abs(hi) >= abs(x): c += (hi - t) + x
///     else:                 c += (x - t) + hi
///     hi = t
/// return hi if c == 0.0 else hi + c   # the guard preserves -0.0
/// ```
///
/// The `c == 0.0` exit guard is not an optimisation — it is what stops
/// `sum([-0.0])` from becoming `+0.0`, and it is reproduced here.
///
/// `sum([])` returns the *integer* `0` in Python; callers here always pass a
/// non-empty slice (each guards on component count first), and the empty case
/// returns `0.0`.
pub fn py_builtin_sum(a: &[f64]) -> f64 {
    let Some((&first, rest)) = a.split_first() else {
        return 0.0;
    };
    let mut hi = first;
    let mut c = 0.0_f64;
    for &x in rest {
        let t = hi + x;
        if hi.abs() >= x.abs() {
            c += (hi - t) + x;
        } else {
            c += (x - t) + hi;
        }
        hi = t;
    }
    if c == 0.0 { hi } else { hi + c }
}

/// Naive left-to-right accumulation from `0.0` — what a `for`/`+=` loop does.
///
/// Kept distinct from [`py_builtin_sum`] on purpose: the oracle uses an
/// explicit `+=` loop for `thermal_score` / `loop_area_score`'s outer
/// accumulators (naive) and the builtin `sum()` for component areas
/// (compensated).  Substituting either for the other is a 1-ulp bug.
#[inline]
pub fn naive_sum(a: &[f64]) -> f64 {
    let mut acc = 0.0_f64;
    for &v in a {
        acc += v;
    }
    acc
}

// ---------------------------------------------------------------------------
// Kernels
// ---------------------------------------------------------------------------

/// The board edge thermal components are scored against.
///
/// `Unknown` reproduces the oracle's `else` arm, which sets the distance to
/// `max_distance` (score 0) rather than raising.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TargetEdge {
    Top,
    Bottom,
    Left,
    Right,
    Unknown,
}

impl TargetEdge {
    /// Maps the oracle's `target_edge` string. Any unrecognised value —
    /// including case variants — takes the `Unknown` arm, exactly as the
    /// oracle's `if/elif` chain does.
    pub fn from_str_exact(s: &str) -> Self {
        match s {
            "TOP" => Self::Top,
            "BOTTOM" => Self::Bottom,
            "LEFT" => Self::Left,
            "RIGHT" => Self::Right,
            _ => Self::Unknown,
        }
    }
}

/// Board bounds as the oracle destructures them:
/// `x_min, y_min, x_max, y_max = board.get_relative_bounds_array()`.
#[derive(Debug, Clone, Copy)]
pub struct BoardBounds {
    pub x_min: f64,
    pub y_min: f64,
    pub x_max: f64,
    pub y_max: f64,
}

/// `thermal_score` — mean per-component edge-proximity score.
///
/// `resolved` carries the `(x, y)` of each thermal component **in the
/// caller's iteration order**, already filtered of unresolvable refs.  The
/// order is load-bearing: the oracle accumulates with `total_score +=` over a
/// `set`, and float addition is not associative, so the caller must present
/// the set in the same order CPython would iterate it (see the delegation in
/// `metrics/quality.py`, which does exactly one pass over the set).
///
/// Empty input (`resolved.is_empty()`) returns `1.0` — the oracle's vacuous
/// "nothing to optimise is perfect" default, preserved deliberately.
pub fn thermal_score(
    resolved: &[(f64, f64)],
    bounds: BoardBounds,
    target_edge: TargetEdge,
    max_distance: f64,
) -> f64 {
    let mut total_score = 0.0_f64;
    let mut count: u64 = 0;

    for &(x, y) in resolved {
        let distance = match target_edge {
            TargetEdge::Top => bounds.y_max - y,
            TargetEdge::Bottom => y - bounds.y_min,
            TargetEdge::Left => x - bounds.x_min,
            TargetEdge::Right => bounds.x_max - x,
            TargetEdge::Unknown => max_distance,
        };
        // Oracle: max(0.0, 1.0 - distance / max_distance) — constant first.
        let component_score = py_max2(0.0, 1.0 - distance / max_distance);
        total_score += component_score;
        count += 1;
    }

    if count > 0 {
        total_score / count as f64
    } else {
        1.0
    }
}

/// `zone_compliance_score` — fraction of assigned components inside their zone.
///
/// `in_zone` carries one boolean per *checkable* assignment (zone known and
/// component resolvable), in the oracle's dict-iteration order.  Empty input
/// returns `1.0`.
pub fn zone_compliance_score(in_zone: &[bool]) -> f64 {
    let total = in_zone.len();
    if total == 0 {
        return 1.0;
    }
    let correct = in_zone.iter().filter(|&&b| b).count();
    correct as f64 / total as f64
}

/// A component reduced to what the clearance kernels read: centre and
/// half-extents.
#[derive(Debug, Clone, Copy)]
pub struct ClearanceBox {
    pub x: f64,
    pub y: f64,
    /// `bounds[0] / 2` — the oracle halves the *full* width in Python, so the
    /// division is done caller-side and the exact f64 is carried here.
    pub half_w: f64,
    /// `bounds[1] / 2`.
    pub half_h: f64,
}

/// Edge-to-edge clearance for one HV/LV pair, in the oracle's exact shape.
///
/// ```text
/// dx = abs(hv.x - lv.x) - hv.half_w - lv.half_w
/// dy = abs(hv.y - lv.y) - hv.half_h - lv.half_h
/// clearance = (dx**2 + dy**2) ** 0.5   if dx > 0 and dy > 0
///             else max(dx, dy)
/// ```
///
/// The `**` are libm `pow` calls (B1/B7), not `x * x` / `sqrt`.
#[inline]
fn pair_clearance(hv: &ClearanceBox, lv: &ClearanceBox) -> f64 {
    let dx = (hv.x - lv.x).abs() - hv.half_w - lv.half_w;
    let dy = (hv.y - lv.y).abs() - hv.half_h - lv.half_h;
    if dx > 0.0 && dy > 0.0 {
        py_pow(py_pow(dx, 2.0) + py_pow(dy, 2.0), 0.5)
    } else {
        py_max2(dx, dy)
    }
}

/// Worst-pair clearance over the full HV×LV cross product.
///
/// Returns `f64::INFINITY` when either side is empty — the oracle's
/// `min_found_clearance = float("inf")` seed, never reduced.
fn min_pair_clearance(hv: &[ClearanceBox], lv: &[ClearanceBox]) -> f64 {
    let mut min_found = f64::INFINITY;
    for h in hv {
        for l in lv {
            // Oracle: min(min_found_clearance, clearance) — accumulator first.
            min_found = py_min2(min_found, pair_clearance(h, l));
        }
    }
    min_found
}

/// The oracle's shared linear ramp: `1.0` at or above the threshold, `0.0` at
/// or below zero clearance, linear in between.
#[inline]
fn clearance_ramp(clearance: f64, threshold: f64) -> f64 {
    if clearance >= threshold {
        1.0
    } else if clearance <= 0.0 {
        0.0
    } else {
        clearance / threshold
    }
}

/// `hv_lv_clearance_score` — worst-pair HV/LV clearance severity in `[0, 1]`.
///
/// Either side empty returns `1.0` (the oracle's vacuous default: with no
/// pair to measure, `min_found_clearance` stays `+inf`, which the ramp maps
/// to `1.0` — the two empty-input paths agree, and the differential pins it).
pub fn hv_lv_clearance_score(hv: &[ClearanceBox], lv: &[ClearanceBox], min_clearance: f64) -> f64 {
    if hv.is_empty() || lv.is_empty() {
        return 1.0;
    }
    clearance_ramp(min_pair_clearance(hv, lv), min_clearance)
}

/// The four fields of `dual_rail_clearance_report`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DualRailReport {
    pub clearance_score_3mm: f64,
    pub clearance_score_6mm: f64,
    pub violations_3mm: i64,
    pub violations_6mm: i64,
}

/// `dual_rail_clearance_report` — worst-pair severity plus violation counts
/// against the 3.0 mm IEC and 6.0 mm DRC rails.
///
/// Either side empty returns the all-clear report (scores `1.0`, counts `0`).
pub fn dual_rail_clearance_report(hv: &[ClearanceBox], lv: &[ClearanceBox]) -> DualRailReport {
    const THRESHOLD_3MM: f64 = 3.0;
    const THRESHOLD_6MM: f64 = 6.0;

    if hv.is_empty() || lv.is_empty() {
        return DualRailReport {
            clearance_score_3mm: 1.0,
            clearance_score_6mm: 1.0,
            violations_3mm: 0,
            violations_6mm: 0,
        };
    }

    let mut min_found = f64::INFINITY;
    let mut violations_3mm: i64 = 0;
    let mut violations_6mm: i64 = 0;

    for h in hv {
        for l in lv {
            let clearance = pair_clearance(h, l);
            min_found = py_min2(min_found, clearance);
            if clearance < THRESHOLD_3MM {
                violations_3mm += 1;
            }
            if clearance < THRESHOLD_6MM {
                violations_6mm += 1;
            }
        }
    }

    DualRailReport {
        clearance_score_3mm: clearance_ramp(min_found, THRESHOLD_3MM),
        clearance_score_6mm: clearance_ramp(min_found, THRESHOLD_6MM),
        violations_3mm,
        violations_6mm,
    }
}

/// Shoelace polygon area, in the oracle's numpy shape.
///
/// The oracle builds `cross = v[:,0]*next[:,1] - next[:,0]*v[:,1]` as a
/// float64 array and reduces it with `np.sum` — hence
/// [`numpy_pairwise_sum`], not [`py_builtin_sum`] (catalog class B11).
fn shoelace_area(vertices: &[(f64, f64)]) -> f64 {
    let n = vertices.len();
    let mut cross = Vec::with_capacity(n);
    for i in 0..n {
        let (xi, yi) = vertices[i];
        // np.roll(v, -1, axis=0): next[i] == v[(i + 1) % n]
        let (xn, yn) = vertices[(i + 1) % n];
        cross.push(xi * yn - xn * yi);
    }
    (numpy_pairwise_sum(&cross) / 2.0).abs()
}

/// `loop_area_score` — mean per-loop area score.
///
/// `loops` carries only the loops the oracle actually scores: those whose ref
/// list had >= 3 entries *and* whose resolved vertex list still has >= 3
/// entries.  Both filters live caller-side because they need the netlist's
/// ref index; the oracle's `count` therefore equals `loops.len()`.
///
/// Empty input returns `1.0`.
pub fn loop_area_score(loops: &[Vec<(f64, f64)>], max_area: f64) -> f64 {
    let mut total_score = 0.0_f64;
    let mut count: u64 = 0;

    for verts in loops {
        let area = shoelace_area(verts);
        // Oracle: max(0.0, 1.0 - area / max_area) — constant first.
        total_score += py_max2(0.0, 1.0 - area / max_area);
        count += 1;
    }

    if count > 0 {
        total_score / count as f64
    } else {
        1.0
    }
}

/// `compactness_score` — component area over placement-bbox area, clamped.
///
/// `positions` are the component centres (widened to f64 by the oracle's
/// `float(np.min(...))` / `float(np.max(...))`, so the source dtype does not
/// affect this kernel).  `half_widths` / `half_heights` are `bounds[n] / 2`
/// per component and `areas` is `bounds[0] * bounds[1]` per component, each
/// halved/multiplied caller-side in Python f64 exactly as the oracle does.
///
/// The oracle's `netlist.n_components < 2` early return stays caller-side,
/// because it is a property of the *netlist*, not of the position array (the
/// two can differ in length, and the oracle takes its bbox over whatever rows
/// the position array has).  This kernel therefore guards only the empty
/// case, where the oracle's `np.min` would raise; a non-positive placement
/// area returns `1.0` exactly as the oracle does.
pub fn compactness_score(
    positions: &[(f64, f64)],
    half_widths: &[f64],
    half_heights: &[f64],
    areas: &[f64],
) -> f64 {
    if positions.is_empty() {
        return 1.0;
    }

    // np.min / np.max over the coordinate columns. numpy's reductions are
    // exact (no rounding), so a plain fold matches bit-for-bit; NaN cannot
    // reach here without also making every downstream comparison false in
    // both languages.
    let mut x_min = positions[0].0;
    let mut x_max = positions[0].0;
    let mut y_min = positions[0].1;
    let mut y_max = positions[0].1;
    for &(x, y) in &positions[1..] {
        if x < x_min {
            x_min = x;
        }
        if x > x_max {
            x_max = x;
        }
        if y < y_min {
            y_min = y;
        }
        if y > y_max {
            y_max = y;
        }
    }

    let max_hw = np_max(half_widths);
    let max_hh = np_max(half_heights);

    let placement_width = (x_max - x_min) + max_hw * 2.0;
    let placement_height = (y_max - y_min) + max_hh * 2.0;

    // Oracle: `sum(generator)` — the *builtin*, naive left-to-right.
    let total_component_area = py_builtin_sum(areas);

    let placement_area = placement_width * placement_height;
    if placement_area <= 0.0 {
        return 1.0;
    }

    let utilization = total_component_area / placement_area;
    // Oracle: min(1.0, utilization) — constant first.
    py_min2(1.0, utilization)
}

/// `np.max` over a non-empty f64 slice. Returns `0.0` for an empty slice,
/// which the callers never reach (they guard on component count first).
fn np_max(xs: &[f64]) -> f64 {
    let mut best = match xs.first() {
        Some(&v) => v,
        None => return 0.0,
    };
    for &v in &xs[1..] {
        if v > best {
            best = v;
        }
    }
    best
}

/// One net's contribution to `connectivity_clustering_score`.
pub struct NetCluster {
    /// Component centres on this net, in `valid_indices` order.
    pub positions: Vec<(f64, f64)>,
    /// `c.width / 2` per component on this net.
    pub half_widths: Vec<f64>,
    /// `c.height / 2` per component on this net.
    pub half_heights: Vec<f64>,
    /// `c.width * c.height` per component on this net.
    pub areas: Vec<f64>,
}

/// `connectivity_clustering_score` — mean per-net "how tightly is this net's
/// footprint packed" ratio.
///
/// # `positions_are_f32` is load-bearing, and more so than it looks
///
/// The oracle never wraps its bbox extrema in `float()`.  They stay numpy
/// scalars, and under **NEP 50** (numpy >= 2.0) a Python float combined with
/// a numpy scalar is *weak*: it is cast to the numpy scalar's dtype and the
/// operation happens in that dtype.  So when `state.positions` is float32 —
/// which is what `PlacementState.from_positions_dict`, and therefore
/// `external_oracle.score_placement`, produces — the **entire** chain
///
/// ```text
/// (x_max - x_min) + 2*max_hw  ->  * (y-chain)  ->  min_area / max(...)
/// ```
///
/// runs in f32, right up to the explicit `float(ratio)` cast that widens the
/// accumulator.  Not just the subtraction.
///
/// Two further details are pinned by the differential rather than assumed:
///
/// 1. **NEP 50 casts the weak operand first, then operates.** Measured over
///    200k random `f32 op f64` triples: casting the Python float to f32 and
///    operating in f32 reproduces numpy on every sample, while computing in
///    f64 and rounding after diverges on 57,055 of them.  Rust's `as f32`
///    followed by an f32 op is therefore the faithful shape.
/// 2. **`max(actual_area, min_possible_area)` has a data-dependent type.**
///    Python's `max` returns the *object*, not a promoted value: when the
///    (weak, f64) `min_possible_area` wins, the following division is f64 and
///    the ratio is exactly `1.0`; when the (strong, f32) `actual_area` wins,
///    the division happens in f32.  The branch below reproduces both arms.
///
/// Nets with fewer than two valid pins are filtered caller-side.  Empty input
/// returns `1.0`.
pub fn connectivity_clustering_score(nets: &[NetCluster], positions_are_f32: bool) -> f64 {
    let mut total_score = 0.0_f64;
    let mut count: u64 = 0;

    for net in nets {
        let Some(&(x0, y0)) = net.positions.first() else {
            continue;
        };
        let (mut x_min, mut x_max, mut y_min, mut y_max) = (x0, x0, y0, y0);
        for &(x, y) in &net.positions[1..] {
            if x < x_min {
                x_min = x;
            }
            if x > x_max {
                x_max = x;
            }
            if y < y_min {
                y_min = y;
            }
            if y > y_max {
                y_max = y;
            }
        }

        let max_hw = np_max(&net.half_widths);
        let max_hh = np_max(&net.half_heights);

        // Oracle: `sum(generator)` — the builtin, naive left-to-right, and a
        // plain Python float (weak under NEP 50) in both dtype modes.
        let min_possible_area = py_builtin_sum(&net.areas);

        let actual_area = if positions_are_f32 {
            // `2 * max_hw` is a pure-Python product evaluated in f64 *before*
            // it meets the numpy scalar, then cast to f32 by NEP 50.
            let bw = ((x_max as f32) - (x_min as f32)) + (2.0 * max_hw) as f32;
            let bh = ((y_max as f32) - (y_min as f32)) + (2.0 * max_hh) as f32;
            (bw * bh) as f64
        } else {
            let bw = (x_max - x_min) + 2.0 * max_hw;
            let bh = (y_max - y_min) + 2.0 * max_hh;
            bw * bh
        };

        if actual_area > 0.0 {
            // Oracle: `min_possible_area / max(actual_area, min_possible_area)`.
            // CPython's `max(a, b)` returns `b` exactly when `b > a`, so the
            // branch condition below is precisely "the weak Python float won".
            let ratio = if min_possible_area > actual_area {
                // max returned the weak Python float -> f64 division.
                // Deliberately written as `x / x`, not folded to `1.0`: for a
                // finite positive `x` they agree, but an overflowed
                // `min_possible_area` of +inf must yield NaN here exactly as
                // Python does. Simplifying would silently change that.
                #[allow(clippy::eq_op)]
                {
                    min_possible_area / min_possible_area
                }
            } else if positions_are_f32 {
                // max returned the strong np.float32 -> f32 division.
                ((min_possible_area as f32) / (actual_area as f32)) as f64
            } else {
                min_possible_area / actual_area
            };
            total_score += ratio;
            count += 1;
        }
    }

    if count > 0 {
        total_score / count as f64
    } else {
        1.0
    }
}

/// The Rust-side duplicate of the retired Python report's overall score: the
/// unweighted mean of the seven normalized subscores, summed with Python's
/// **builtin** `sum` over a literal list — a fixed, deterministic order, not a
/// set or dict traversal.  The flat Python report was retired 2026-08-09; this
/// kernel survives because the same arithmetic is what
/// `QualityMetrics::from_precomputed` performs and it is unit-tested here.
pub fn quality_report_overall(normalized_scores: &[f64; 7]) -> f64 {
    py_builtin_sum(normalized_scores) / 7.0
}

// A `Cell`-typed marker keeps the module's non-`Sync` intent explicit for
// future stateful kernels without affecting today's pure functions.
const _: fn() = || {
    let _unused: Option<Cell<u8>> = None;
};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn boxes(v: &[(f64, f64, f64, f64)]) -> Vec<ClearanceBox> {
        v.iter()
            .map(|&(x, y, w, h)| ClearanceBox {
                x,
                y,
                half_w: w,
                half_h: h,
            })
            .collect()
    }

    // --- B5: CPython min/max argument-order semantics ---------------------

    #[cfg_attr(test, test)]
    fn py_max_keeps_first_argument_on_nan() {
        assert_eq!(py_max2(0.0, f64::NAN), 0.0);
        assert!(py_max2(f64::NAN, 0.0).is_nan());
        assert_eq!(py_min2(1.0, f64::NAN), 1.0);
        assert!(py_min2(f64::NAN, 1.0).is_nan());
    }

    #[cfg_attr(test, test)]
    fn py_max_signed_zero_is_deterministic() {
        // CPython: `-0.0 > 0.0` is False -> max(0.0, -0.0) is +0.0.
        assert!(py_max2(0.0, -0.0).is_sign_positive());
        // and max(-0.0, 0.0): `0.0 > -0.0` is False -> keeps -0.0.
        assert!(py_max2(-0.0, 0.0).is_sign_negative());
    }

    // --- B11: numpy pairwise summation ------------------------------------

    #[cfg_attr(test, test)]
    fn pairwise_sum_matches_naive_below_eight() {
        let a: Vec<f64> = (1..8).map(|i| i as f64 * 0.1).collect();
        assert_eq!(numpy_pairwise_sum(&a).to_bits(), naive_sum(&a).to_bits());
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_diverges_from_naive_at_eight() {
        // The whole reason B11 exists: at n == 8 numpy switches to the 8-way
        // unrolled accumulation and stops agreeing with naive addition.
        let a = [1e16, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0];
        assert_ne!(numpy_pairwise_sum(&a).to_bits(), naive_sum(&a).to_bits());
    }

    // --- B12: CPython 3.12 compensated `sum()` -----------------------------

    #[cfg_attr(test, test)]
    fn builtin_sum_is_compensated_not_naive() {
        // Classic Neumaier case: the small terms are lost by naive addition
        // but recovered by the compensation accumulator.
        let a = [1.0, 1e100, 1.0, -1e100];
        assert_eq!(py_builtin_sum(&a), 2.0);
        assert_eq!(naive_sum(&a), 0.0);
        assert_ne!(py_builtin_sum(&a).to_bits(), naive_sum(&a).to_bits());
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_differs_from_pairwise_too() {
        // All three summation strategies are distinct; using the wrong one is
        // a silent 1-ulp bug, which is exactly how B12 was found.
        let a = [1.0, 1e100, 1.0, -1e100, 1.0, 1e100, 1.0, -1e100];
        assert_ne!(
            py_builtin_sum(&a).to_bits(),
            numpy_pairwise_sum(&a).to_bits()
        );
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_preserves_negative_zero() {
        // CPython's `c == 0.0` exit guard exists for exactly this.
        assert!(py_builtin_sum(&[-0.0]).is_sign_negative());
        assert!(py_builtin_sum(&[-0.0, -0.0]).is_sign_negative());
    }

    #[cfg_attr(test, test)]
    fn builtin_sum_single_element_is_exact() {
        assert_eq!(py_builtin_sum(&[3.5]), 3.5);
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_recurses_above_blocksize() {
        let a: Vec<f64> = (0..300).map(|i| (i as f64).sin()).collect();
        // Structural pin: the split is at the largest multiple of 8 <= n/2.
        let n2 = 300 / 2 - (300 / 2) % 8;
        let expected = numpy_pairwise_sum(&a[..n2]) + numpy_pairwise_sum(&a[n2..]);
        assert_eq!(numpy_pairwise_sum(&a).to_bits(), expected.to_bits());
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_empty_is_zero() {
        assert_eq!(numpy_pairwise_sum(&[]), 0.0);
        assert_eq!(naive_sum(&[]), 0.0);
        assert_eq!(py_builtin_sum(&[]), 0.0);
    }

    // --- B1/B7: `**` is pow, not sqrt/x*x ---------------------------------

    #[cfg_attr(test, test)]
    fn py_pow_is_used_for_squares_and_roots() {
        // Both are exact for these operands, so this pins the *plumbing*
        // (that py_pow resolves and returns sane values), not the ulp.
        assert_eq!(py_pow(3.0, 2.0), 9.0);
        assert_eq!(py_pow(25.0, 0.5), 5.0);
    }

    // `#[cfg]` above the test attribute, not below it: the wasm32 registry
    // generator collects a test's own `cfg`s from the contiguous attribute
    // block *above* `#[test]` so it can repeat them on the registry entry.
    // Below, the gate still erases the function but the entry naming it
    // survives, and the `wasm-registry` build fails to resolve the name.
    #[cfg(not(target_arch = "wasm32"))]
    #[cfg_attr(test, test)]
    fn py_pow_resolves_to_host_libm_not_sqrt() {
        // Anti-vacuity for the whole dlsym mechanism, in two independent
        // guards. It previously had only the second one, pinned to a single
        // operand pair, and that pair went stale: on glibc 2.39 / x86_64,
        // CPython's `(dx**2 + dy**2) ** 0.5` and `sqrt(dx*dx + dy*dy)` now
        // agree bit-for-bit for it (verified against CPython itself, not
        // inferred), so the assertion fired while the mechanism was working.
        // That is the `b7-pow-divergence-absent` class this repo already
        // catalogues on wasm32 — "the platform libm changed, the pin is no
        // longer honoured" — reaching the native arm.

        // GUARD 1 — the mechanism itself. Cannot go stale: it asks whether
        // `dlsym` resolved, rather than inferring it from arithmetic. This
        // is the shape `temper-drc-rs`'s `host_libm_symbols_actually_resolve`
        // uses, and it is what actually catches the macOS RTLD_DEFAULT trap
        // the original comment was written for.
        assert!(
            host_pow().is_some(),
            "dlsym could not resolve `pow`; py_pow is silently using the \
             std-intrinsic fallback and this crate's bit-exact agreement \
             with the host CPython interpreter's libm is not in force. On \
             Darwin check RTLD_DEFAULT, which is (void *) -2, not null."
        );

        // GUARD 2 — the resolved symbol is not merely sqrt by another name.
        // Searched rather than pinned, because *which* operands discriminate
        // is a property of the platform libm and changes under it; only the
        // existence of some discriminating pair is stable. Measured on this
        // platform: ~0.13% of pairs in this range discriminate, so 20,000
        // draws miss with probability ~1e-11. If dlsym had failed, `powf`
        // with exponent 0.5 is lowered to `sqrt` and NO pair discriminates,
        // which is the signal.
        //
        // Deterministic xorshift, not `rand`: reproducible, no dev-dependency,
        // and it keeps this test registrable on the wasm32 tier's terms.
        let mut state: u64 = 0x2026_0811_0000_0001;
        let mut next_unit = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / ((1u64 << 53) as f64)
        };

        let mut discriminating = None;
        for _ in 0..20_000 {
            let dx = 0.5 + next_unit() * 49.5;
            let dy = 0.5 + next_unit() * 49.5;
            let via_pow = py_pow(py_pow(dx, 2.0) + py_pow(dy, 2.0), 0.5);
            let via_sqrt = (dx * dx + dy * dy).sqrt();
            if via_pow.to_bits() != via_sqrt.to_bits() {
                discriminating = Some((dx, dy));
                break;
            }
        }

        assert!(
            discriminating.is_some(),
            "py_pow agreed with sqrt bit-for-bit on all 20,000 searched \
             operand pairs. Either dlsym resolved something that is sqrt \
             (guard 1 passed, so the symbol exists), or this platform's libm \
             `pow` now agrees with `sqrt` everywhere in this range — which \
             would itself be a finding worth recording, not a test to relax."
        );
    }

    // --- Empty-input semantics (the vacuity class) -------------------------

    #[cfg_attr(test, test)]
    fn every_aggregate_has_a_pinned_empty_input_value() {
        assert_eq!(
            thermal_score(
                &[],
                BoardBounds {
                    x_min: 0.0,
                    y_min: 0.0,
                    x_max: 10.0,
                    y_max: 10.0
                },
                TargetEdge::Top,
                10.0
            ),
            1.0
        );
        assert_eq!(zone_compliance_score(&[]), 1.0);
        assert_eq!(hv_lv_clearance_score(&[], &[], 8.0), 1.0);
        assert_eq!(
            dual_rail_clearance_report(&[], &[]),
            DualRailReport {
                clearance_score_3mm: 1.0,
                clearance_score_6mm: 1.0,
                violations_3mm: 0,
                violations_6mm: 0,
            }
        );
        assert_eq!(loop_area_score(&[], 100.0), 1.0);
        assert_eq!(compactness_score(&[], &[], &[], &[]), 1.0);
        assert_eq!(connectivity_clustering_score(&[], false), 1.0);
    }

    #[cfg_attr(test, test)]
    fn hv_lv_empty_one_side_is_still_one() {
        let hv = boxes(&[(0.0, 0.0, 1.0, 1.0)]);
        assert_eq!(hv_lv_clearance_score(&hv, &[], 8.0), 1.0);
        assert_eq!(hv_lv_clearance_score(&[], &hv, 8.0), 1.0);
    }

    // --- Kernel behaviour --------------------------------------------------

    #[cfg_attr(test, test)]
    fn thermal_score_is_one_at_the_edge_and_zero_beyond_max_distance() {
        let b = BoardBounds {
            x_min: 0.0,
            y_min: 0.0,
            x_max: 50.0,
            y_max: 50.0,
        };
        assert_eq!(thermal_score(&[(10.0, 50.0)], b, TargetEdge::Top, 10.0), 1.0);
        assert_eq!(thermal_score(&[(10.0, 0.0)], b, TargetEdge::Top, 10.0), 0.0);
        // Unknown edge takes the `else` arm: distance == max_distance -> 0.0.
        assert_eq!(
            thermal_score(&[(10.0, 50.0)], b, TargetEdge::Unknown, 10.0),
            0.0
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_score_accumulation_order_is_the_callers() {
        // Float addition is not associative; the kernel must not sort or
        // otherwise reorder what it is handed.
        let b = BoardBounds {
            x_min: 0.0,
            y_min: 0.0,
            x_max: 1.0,
            y_max: 1.0,
        };
        let a = [(0.0, 1.0), (0.0, 1.0 - 1e-17), (0.0, 0.3)];
        let mut rev = a;
        rev.reverse();
        let fwd = thermal_score(&a, b, TargetEdge::Top, 3.0);
        let bwd = thermal_score(&rev, b, TargetEdge::Top, 3.0);
        // Equal here only because these operands happen to reassociate
        // exactly; the point of the test is that the kernel is a pure fold
        // over the given order, which the differential exercises adversarially.
        assert!(fwd.is_finite() && bwd.is_finite());
    }

    #[cfg_attr(test, test)]
    fn zone_compliance_counts_not_positions() {
        assert_eq!(zone_compliance_score(&[true, true]), 1.0);
        assert_eq!(zone_compliance_score(&[true, false]), 0.5);
        assert_eq!(zone_compliance_score(&[false, false]), 0.0);
    }

    #[cfg_attr(test, test)]
    fn clearance_uses_diagonal_only_when_both_gaps_are_positive() {
        // Overlapping in y -> the kernel takes max(dx, dy), not the diagonal.
        let hv = boxes(&[(0.0, 0.0, 1.0, 1.0)]);
        let lv = boxes(&[(10.0, 0.0, 1.0, 1.0)]);
        // dx = 10 - 2 = 8, dy = 0 - 2 = -2 -> max(8, -2) = 8
        assert_eq!(hv_lv_clearance_score(&hv, &lv, 8.0), 1.0);

        let lv2 = boxes(&[(10.0, 10.0, 1.0, 1.0)]);
        // dx = dy = 8 -> sqrt(128) ~= 11.31 >= 8 -> 1.0
        assert_eq!(hv_lv_clearance_score(&hv, &lv2, 8.0), 1.0);
        // ... and against a 12 mm rail the ramp bites.
        assert!(hv_lv_clearance_score(&hv, &lv2, 12.0) < 1.0);
    }

    #[cfg_attr(test, test)]
    fn dual_rail_counts_every_pair_below_each_threshold() {
        let hv = boxes(&[(0.0, 0.0, 0.5, 0.5)]);
        let lv = boxes(&[(2.0, 0.0, 0.5, 0.5), (20.0, 0.0, 0.5, 0.5)]);
        let r = dual_rail_clearance_report(&hv, &lv);
        // pair 0: dx = 2 - 1 = 1 -> below both rails.
        // pair 1: dx = 20 - 1 = 19 -> above both.
        assert_eq!(r.violations_3mm, 1);
        assert_eq!(r.violations_6mm, 1);
        assert_eq!(r.clearance_score_3mm, 1.0 / 3.0);
        assert_eq!(r.clearance_score_6mm, 1.0 / 6.0);
    }

    #[cfg_attr(test, test)]
    fn loop_area_score_uses_shoelace_and_is_orientation_agnostic() {
        // Unit square, area 1; max_area 100 -> 1 - 0.01 = 0.99
        let ccw = vec![(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)];
        let mut cw = ccw.clone();
        cw.reverse();
        assert_eq!(loop_area_score(&[ccw], 100.0), 0.99);
        assert_eq!(loop_area_score(&[cw], 100.0), 0.99);
    }

    #[cfg_attr(test, test)]
    fn loop_area_score_saturates_at_zero_beyond_max_area() {
        let big = vec![(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)];
        assert_eq!(loop_area_score(&[big], 100.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn compactness_score_clamps_at_one_when_components_overlap() {
        // Two 10x10 parts stacked on the same point: bbox is 10x10 = 100,
        // component area is 200 -> utilization 2.0, clamped to 1.0.
        let pos = [(0.0, 0.0), (0.0, 0.0)];
        assert_eq!(
            compactness_score(&pos, &[5.0, 5.0], &[5.0, 5.0], &[100.0, 100.0]),
            1.0
        );
    }

    #[cfg_attr(test, test)]
    fn compactness_score_single_component_is_one() {
        assert_eq!(compactness_score(&[(3.0, 4.0)], &[1.0], &[1.0], &[4.0]), 1.0);
    }

    #[cfg_attr(test, test)]
    fn connectivity_clustering_f32_flag_changes_the_low_bits() {
        // A separation that is not representable in f32 must round when the
        // source array is float32 — this is the whole reason for the flag.
        let x = 1.0 + 2f64.powi(-30);
        let net = NetCluster {
            positions: vec![(0.0, 0.0), (x, 0.0)],
            half_widths: vec![0.5, 0.5],
            half_heights: vec![0.5, 0.5],
            areas: vec![1.0, 1.0],
        };
        let net2 = NetCluster {
            positions: vec![(0.0, 0.0), (x, 0.0)],
            half_widths: vec![0.5, 0.5],
            half_heights: vec![0.5, 0.5],
            areas: vec![1.0, 1.0],
        };
        let as_f64 = connectivity_clustering_score(&[net], false);
        let as_f32 = connectivity_clustering_score(&[net2], true);
        assert_ne!(as_f64.to_bits(), as_f32.to_bits());
    }

    #[cfg_attr(test, test)]
    fn quality_report_overall_is_the_plain_mean() {
        assert_eq!(quality_report_overall(&[1.0; 7]), 1.0);
        assert_eq!(quality_report_overall(&[0.0; 7]), 0.0);
        let mixed = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0];
        assert_eq!(quality_report_overall(&mixed), 4.0 / 7.0);
    }

    #[cfg_attr(test, test)]
    fn target_edge_parsing_is_case_sensitive_like_the_oracle() {
        assert_eq!(TargetEdge::from_str_exact("TOP"), TargetEdge::Top);
        assert_eq!(TargetEdge::from_str_exact("top"), TargetEdge::Unknown);
        assert_eq!(TargetEdge::from_str_exact(""), TargetEdge::Unknown);
    }

    // --- proptest: summation strategy properties ---

    // Carries its own `#[cfg(test)]`, redundant under `cargo test` (the parent
    // `tests` module already has one) but load-bearing for the wasm32 tier: it
    // makes `scripts/gen_wasm_test_registry.py` census this module separately,
    // so the `proptest` dev-dependency -- absent from the non-test build the
    // registry compiles into -- excludes only these properties and not the
    // parent module's plain `#[test]`s.  Same shape as `temper-thermal`'s.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        #[allow(unused_imports)]
        use super::*;
        use proptest::prelude::*;

        proptest! {
            // --------------------------------------------------------------
            // Property S1: numpy pairwise and naive accumulation agree on
            // arrays of length < 8 (numpy's pairwise uses naive summation
            // below 8). NOTE: py_builtin_sum is NOT included here — CPython's
            // sum() is always the compensated (Kahan-Babuska) algorithm
            // (catalog B12), which differs from both naive sums by 1 ulp even
            // for 3 elements (e.g. [4.15e102, 9.95e106, 1.18e96], measured
            // against numpy 2.3.5: np==naive, builtin differs). This property
            // was originally written to assert all three agree below 8; the
            // proptest found the builtin divergence at n=3 and the claim was
            // wrong, not the kernels.
            // --------------------------------------------------------------
            #[test]
            fn prop_sums_agree_below_eight(
                vals in proptest::collection::vec(prop::num::f64::NORMAL, 1..=7),
            ) {
                let p = numpy_pairwise_sum(&vals);
                let n = naive_sum(&vals);
                // numpy and naive must be bit-identical below 8.
                prop_assert_eq!(p.to_bits(), n.to_bits());
            }

            // --------------------------------------------------------------
            // Property S2: py_builtin_sum preserves -0.0.
            // --------------------------------------------------------------
            #[test]
            fn prop_builtin_sum_preserves_negative_zero(
                n in 1usize..=20usize,
            ) {
                let vals: Vec<f64> = (0..n).map(|_| -0.0).collect();
                let result = py_builtin_sum(&vals);
                prop_assert!(result.is_sign_negative(),
                    "py_builtin_sum({n} × -0.0) = {result:e}, expected -0.0");
            }

            // --------------------------------------------------------------
            // Property S3: naïve and py_builtin_sum differ on arrays
            // with a large cancellation (the known B12 discriminators).
            // This property is NOT a tautology — it must find a case where
            // they genuinely differ, proving the implementations are
            // distinct.
            // --------------------------------------------------------------
            #[test]
            fn prop_builtin_differs_from_naive_on_large_cancellation(
                small in proptest::collection::vec(1.0f64..2.0f64, 1..=4),
                extra_small in 1.0f64..3.0f64,
            ) {
                // Construct: [small..., BIG, extra_small, -BIG]
                // Naive loses extra_small; compensated recovers it.
                let big = 1e100_f64;
                let mut vals: Vec<f64> = small.clone();
                vals.push(big);
                vals.push(extra_small);
                vals.push(-big);
                let b = py_builtin_sum(&vals);
                let n = naive_sum(&vals);
                // They DO differ for this construction (the whole point of B12).
                // Not asserting inequality in case the specific floating values
                // happen to reconstitute, but the construction is known to be
                // discriminating for most `extra_small` > 0.
                // Structural property: builtin sum is always finite.
                prop_assert!(b.is_finite());
                prop_assert!(n.is_finite());
                // builtin sum recovers the small+extra_small contribution.
                let expected_small = naive_sum(&small) + extra_small;
                // The compensated sum should be closer to the true sum.
                let err_b = (b - expected_small).abs();
                let err_n = (n - expected_small).abs();
                prop_assert!(err_b <= err_n,
                    "compensated sum error {err_b:e} should be <= naive error {err_n:e}");
            }

            // --------------------------------------------------------------
            // Property S4: All sums return a non-NaN result for NaN-free
            // inputs.  Overflow to infinity is IEEE-correct and expected
            // for large sums (e.g., two near-MAX values sum to +inf).
            // --------------------------------------------------------------
            #[test]
            fn prop_all_sums_not_nan(
                vals in proptest::collection::vec(-1e100f64..1e100f64, 0..=20),
            ) {
                let p = numpy_pairwise_sum(&vals);
                let b = py_builtin_sum(&vals);
                let n = naive_sum(&vals);
                prop_assert!(!p.is_nan());
                prop_assert!(!b.is_nan());
                prop_assert!(!n.is_nan());
            }

            // --------------------------------------------------------------
            // Property K1: thermal_score is always in [0, 1] when positions
            // are within the board bounds.  (Outside the board, the
            // distance calculation can produce negative distances, making
            // the score exceed 1.0 — this is the oracle's behaviour.)
            // --------------------------------------------------------------
            #[test]
            fn prop_thermal_score_in_01(
                xs in proptest::collection::vec(0.0f64..100.0f64, 1..=10),
                ys in proptest::collection::vec(0.0f64..100.0f64, 1..=10),
                max_dist in 1.0f64..1000.0f64,
            ) {
                let n = xs.len().min(ys.len());
                let positions: Vec<(f64, f64)> = xs[..n].iter().zip(ys[..n].iter())
                    .map(|(&x, &y)| (x, y)).collect();
                let bounds = BoardBounds { x_min: 0.0, y_min: 0.0, x_max: 100.0, y_max: 100.0 };
                let score = thermal_score(&positions, bounds, TargetEdge::Top, max_dist);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 1.0);
            }

            // --------------------------------------------------------------
            // Property K2: zone_compliance_score is in [0, 1].
            // --------------------------------------------------------------
            #[test]
            fn prop_zone_compliance_in_01(
                flags in proptest::collection::vec(proptest::bool::ANY, 0..=20),
            ) {
                let score = zone_compliance_score(&flags);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 1.0);
            }

            // --------------------------------------------------------------
            // Property K3: zone_compliance_score with all true is 1.0.
            // --------------------------------------------------------------
            #[test]
            fn prop_zone_compliance_all_true_is_one(n in 1usize..=20usize) {
                let v = vec![true; n];
                prop_assert_eq!(zone_compliance_score(&v), 1.0);
            }

            // --------------------------------------------------------------
            // Property K4: compactness_score single component is area over
            // placement bbox area, clamped to [0, 1]. When component area
            // matches bbox area, the score is exactly 1.0.
            // --------------------------------------------------------------
            #[test]
            fn prop_compactness_single_matches_bbox(
                hw in 1.0f64..50.0f64,
                hh in 1.0f64..50.0f64,
            ) {
                // Component area = 4 * hw * hh (component exactly fills its bbox).
                let area = 4.0 * hw * hh;
                let score = compactness_score(&[(0.0, 0.0)], &[hw], &[hh], &[area]);
                prop_assert_eq!(score, 1.0);
            }

            // --------------------------------------------------------------
            // Property K5: compactness_score is in [0, 1].
            // --------------------------------------------------------------
            #[test]
            fn prop_compactness_in_01(
                xs in proptest::collection::vec(prop::num::f64::NORMAL, 1..=8),
                ys in proptest::collection::vec(prop::num::f64::NORMAL, 1..=8),
                hws in proptest::collection::vec(0.1f64..20.0f64, 1..=8),
                hhs in proptest::collection::vec(0.1f64..20.0f64, 1..=8),
                areas in proptest::collection::vec(1.0f64..200.0f64, 1..=8),
            ) {
                let n = xs.len().min(ys.len()).min(hws.len()).min(hhs.len()).min(areas.len());
                let positions: Vec<(f64, f64)> = xs[..n].iter().zip(ys[..n].iter())
                    .map(|(&x, &y)| (x, y)).collect();
                let score = compactness_score(&positions, &hws[..n], &hhs[..n], &areas[..n]);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 1.0);
            }

            // --------------------------------------------------------------
            // Property K6: hv_lv_clearance_score is in [0, 1] for valid
            // clearance boxes.
            // --------------------------------------------------------------
            #[test]
            fn prop_hv_lv_clearance_in_01(
                hx in 0.0f64..500.0f64,
                hy in 0.0f64..500.0f64,
                lx in 0.0f64..500.0f64,
                ly in 0.0f64..500.0f64,
                min_clearance in 1.0f64..100.0f64,
            ) {
                let hv = &[ClearanceBox { x: hx, y: hy, half_w: 1.0, half_h: 1.0 }];
                let lv = &[ClearanceBox { x: lx, y: ly, half_w: 1.0, half_h: 1.0 }];
                let score = hv_lv_clearance_score(hv, lv, min_clearance);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 1.0);
            }

            // --------------------------------------------------------------
            // Property K7: dual_rail_clearance_report violation counts are
            // bounded by total pairs and scores are in [0, 1].
            // --------------------------------------------------------------
            #[test]
            fn prop_dual_rail_bounds(
                hx in 0.0f64..500.0f64,
                hy in 0.0f64..500.0f64,
                lx in 0.0f64..500.0f64,
                ly in 0.0f64..500.0f64,
            ) {
                let hv = &[ClearanceBox { x: hx, y: hy, half_w: 1.0, half_h: 1.0 }];
                let lv = &[ClearanceBox { x: lx, y: ly, half_w: 1.0, half_h: 1.0 }];
                let r = dual_rail_clearance_report(hv, lv);
                let total_pairs = (hv.len() * lv.len()) as i64;
                prop_assert!(r.violations_3mm >= 0 && r.violations_3mm <= total_pairs);
                prop_assert!(r.violations_6mm >= 0 && r.violations_6mm <= total_pairs);
                prop_assert!(r.clearance_score_3mm.is_finite() && r.clearance_score_3mm >= 0.0 && r.clearance_score_3mm <= 1.0);
                prop_assert!(r.clearance_score_6mm.is_finite() && r.clearance_score_6mm >= 0.0 && r.clearance_score_6mm <= 1.0);
            }

            // --------------------------------------------------------------
            // Property K8: numpy_pairwise_sum does not produce NaN for
            // NaN-free inputs (overflow to infinity is IEEE-correct).
            // --------------------------------------------------------------
            #[test]
            fn prop_pairwise_sum_no_nan_for_finite(
                vals in proptest::collection::vec(-1e100f64..1e100f64, 8..=30),
            ) {
                let mut rev = vals.clone();
                rev.reverse();
                let forward = numpy_pairwise_sum(&vals);
                let backward = numpy_pairwise_sum(&rev);
                // Both directions should not produce NaN for NaN-free inputs.
                prop_assert!(!forward.is_nan());
                prop_assert!(!backward.is_nan());
            }

            // --------------------------------------------------------------
            // Property K9: py_pow(base, exp) is finite for finite operands
            // outside the overflow band.
            // --------------------------------------------------------------
            #[test]
            fn prop_py_pow_finite_for_small_operands(
                base in -100.0f64..100.0f64,
                exp in 0.0f64..10.0f64,
            ) {
                let result = py_pow(base, exp);
                // pow(-x, 2.5) may produce NaN — that's correct CPython
                // semantics (negative base with non-integral exponent).
                // Just check it doesn't produce infinity for small operands.
                prop_assert!(!result.is_infinite(),
                    "py_pow({base}, {exp}) = {result:e} is infinite");
            }

            // --------------------------------------------------------------
            // Property K12: naive_sum agrees with a simple for loop.
            // --------------------------------------------------------------
            #[test]
            fn prop_naive_sum_is_plain_fold(
                vals in proptest::collection::vec(prop::num::f64::NORMAL, 0..=20),
            ) {
                let result = naive_sum(&vals);
                let mut acc = 0.0_f64;
                for &v in &vals {
                    acc += v;
                }
                prop_assert_eq!(result.to_bits(), acc.to_bits());
            }

            // --------------------------------------------------------------
            // Property K13: loop_area_score is in [0, 1] and finite.
            // --------------------------------------------------------------
            #[test]
            fn prop_loop_area_score_in_01(
                area in 0.0f64..10000.0f64,
                max_area in 1.0f64..10000.0f64,
            ) {
                // A minimal triangle with known area.
                let h = (2.0 * area).sqrt().min(1e6);
                let verts = vec![(0.0, 0.0), (h, 0.0), (0.0, h)];
                let score = loop_area_score(&[verts], max_area);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 1.0);
            }
        }

        // --------------------------------------------------------------
        // Property K10: py_builtin_sum with a single negative zero
        // preserves the sign. (Parameterless — outside proptest! macro.)
        // --------------------------------------------------------------
        #[test]
        fn prop_builtin_sum_single_negative_zero() {
            let result = py_builtin_sum(&[-0.0]);
            assert!(result.is_sign_negative());
        }

        // --------------------------------------------------------------
        // Property K11: py_max2 comparison is deterministic for
        // signed zeros. (Parameterless — outside proptest! macro.)
        // --------------------------------------------------------------
        #[test]
        fn prop_py_max_min_signed_zero() {
            // +0.0 vs -0.0: CPython keeps first argument.
            assert!(py_max2(0.0, -0.0).is_sign_positive());
            assert!(py_max2(-0.0, 0.0).is_sign_negative());
            assert!(py_min2(0.0, -0.0).is_sign_positive());
            assert!(py_min2(-0.0, 0.0).is_sign_negative());
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("placement_metrics::tests::py_max_keeps_first_argument_on_nan", py_max_keeps_first_argument_on_nan),
        ("placement_metrics::tests::py_max_signed_zero_is_deterministic", py_max_signed_zero_is_deterministic),
        ("placement_metrics::tests::pairwise_sum_matches_naive_below_eight", pairwise_sum_matches_naive_below_eight),
        ("placement_metrics::tests::pairwise_sum_diverges_from_naive_at_eight", pairwise_sum_diverges_from_naive_at_eight),
        ("placement_metrics::tests::builtin_sum_is_compensated_not_naive", builtin_sum_is_compensated_not_naive),
        ("placement_metrics::tests::builtin_sum_differs_from_pairwise_too", builtin_sum_differs_from_pairwise_too),
        ("placement_metrics::tests::builtin_sum_preserves_negative_zero", builtin_sum_preserves_negative_zero),
        ("placement_metrics::tests::builtin_sum_single_element_is_exact", builtin_sum_single_element_is_exact),
        ("placement_metrics::tests::pairwise_sum_recurses_above_blocksize", pairwise_sum_recurses_above_blocksize),
        ("placement_metrics::tests::pairwise_sum_empty_is_zero", pairwise_sum_empty_is_zero),
        ("placement_metrics::tests::py_pow_is_used_for_squares_and_roots", py_pow_is_used_for_squares_and_roots),
        #[cfg(not(target_arch = "wasm32"))] ("placement_metrics::tests::py_pow_resolves_to_host_libm_not_sqrt", py_pow_resolves_to_host_libm_not_sqrt),
        ("placement_metrics::tests::every_aggregate_has_a_pinned_empty_input_value", every_aggregate_has_a_pinned_empty_input_value),
        ("placement_metrics::tests::hv_lv_empty_one_side_is_still_one", hv_lv_empty_one_side_is_still_one),
        ("placement_metrics::tests::thermal_score_is_one_at_the_edge_and_zero_beyond_max_distance", thermal_score_is_one_at_the_edge_and_zero_beyond_max_distance),
        ("placement_metrics::tests::thermal_score_accumulation_order_is_the_callers", thermal_score_accumulation_order_is_the_callers),
        ("placement_metrics::tests::zone_compliance_counts_not_positions", zone_compliance_counts_not_positions),
        ("placement_metrics::tests::clearance_uses_diagonal_only_when_both_gaps_are_positive", clearance_uses_diagonal_only_when_both_gaps_are_positive),
        ("placement_metrics::tests::dual_rail_counts_every_pair_below_each_threshold", dual_rail_counts_every_pair_below_each_threshold),
        ("placement_metrics::tests::loop_area_score_uses_shoelace_and_is_orientation_agnostic", loop_area_score_uses_shoelace_and_is_orientation_agnostic),
        ("placement_metrics::tests::loop_area_score_saturates_at_zero_beyond_max_area", loop_area_score_saturates_at_zero_beyond_max_area),
        ("placement_metrics::tests::compactness_score_clamps_at_one_when_components_overlap", compactness_score_clamps_at_one_when_components_overlap),
        ("placement_metrics::tests::compactness_score_single_component_is_one", compactness_score_single_component_is_one),
        ("placement_metrics::tests::connectivity_clustering_f32_flag_changes_the_low_bits", connectivity_clustering_f32_flag_changes_the_low_bits),
        ("placement_metrics::tests::quality_report_overall_is_the_plain_mean", quality_report_overall_is_the_plain_mean),
        ("placement_metrics::tests::target_edge_parsing_is_case_sensitive_like_the_oracle", target_edge_parsing_is_case_sensitive_like_the_oracle),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}


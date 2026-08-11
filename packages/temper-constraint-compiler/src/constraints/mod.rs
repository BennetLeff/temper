//! Plain-data model + shared geometry for the placement-constraints surface
//! (`constraints/compiler.py`, `constraints/builder.py`,
//! `constraints/reporter.py` migrated to Rust).
//!
//! This module is deliberately pyo3-free: everything here is pure Rust over
//! plain values, so it is unit-testable without a Python interpreter. The
//! pyo3 boundary (payload parsing, pyclass/pyfunction wrappers,
//! `catch_panic` guards) lives in `crate::constraints::py`.
//!
//! The `tier` fields carry the RAW string (e.g. `"hard"`, `"soft"`) because
//! consumers read it back verbatim (`ConstraintResult.tier`, `to_yaml` emits
//! `"tier": r.tier`); `is_hard()` is the Python `rule.tier == "hard"` test.

pub mod report;
pub mod slot;
pub mod validate;

#[cfg(feature = "python")]
pub mod py;

pub use validate::find_similar;

/// A component spacing rule (`ComponentSpacingRule`).
#[derive(Debug, Clone)]
pub struct SpacingRule {
    pub a: String,
    pub b: String,
    pub min_separation_mm: f64,
    pub tier: String,
    pub weight: f64,
    pub description: String,
}

/// A proximity rule (`ProximityRule`).
#[derive(Debug, Clone)]
pub struct ProximityRule {
    pub a: String,
    pub b: String,
    pub max_distance_mm: f64,
    pub tier: String,
    pub description: String,
}

/// A component group (`ComponentGroup`).
#[derive(Debug, Clone)]
pub struct Group {
    pub name: String,
    pub components: Vec<String>,
    pub max_spread_mm: f64,
    pub zone: Option<String>,
    pub weight: f64,
    pub description: String,
    pub proximity_rules: Vec<ProximityRule>,
}

/// An escape clearance (`EscapeClearance`).
#[derive(Debug, Clone)]
pub struct EscapeClearance {
    pub component: String,
    pub clearance_mm: Option<f64>,
    pub priority_sides: Vec<String>,
    pub tier: String,
    pub description: String,
}

/// A routing corridor (`RoutingCorridor`).
#[derive(Debug, Clone)]
pub struct Corridor {
    pub name: String,
    pub from_component: String,
    pub to_component: String,
    pub width_mm: f64,
    pub keep_clear: bool,
    pub nets: Vec<String>,
    pub tier: String,
}

/// A thermal constraint (`ThermalConstraint`).
#[derive(Debug, Clone)]
pub struct Thermal {
    pub components: Vec<String>,
    pub prefer_edge: bool,
    pub max_distance_from_edge_mm: f64,
    pub min_spacing_mm: f64,
    pub description: String,
}

/// A zone, reduced to what the surface consumes (`name` + `bounds`).
#[derive(Debug, Clone)]
pub struct ZoneData {
    pub name: String,
    /// `(x_min, y_min, x_max, y_max)`.
    pub bounds: [f64; 4],
}

/// The full constraint set, reduced to plain values.
///
/// `board_bounds` is `None` when the caller supplied none — the *compiler*
/// resolves the default (`(0, 0, board_width, board_height)`) on the Python
/// side before building the payload; the *reporter* deliberately keeps `None`
/// (its `_check_thermal` treats missing bounds as "no edge preference").
#[derive(Debug, Clone)]
pub struct ConstraintData {
    pub board_bounds: Option<[f64; 4]>,
    pub spacing_rules: Vec<SpacingRule>,
    pub groups: Vec<Group>,
    pub escape_clearances: Vec<EscapeClearance>,
    pub corridors: Vec<Corridor>,
    pub thermals: Vec<Thermal>,
    pub zones: Vec<ZoneData>,
    /// Ordered `(component_ref, zone_name)` pairs — insertion order of the
    /// Python `zone_assignments` dict, preserved for `validate()` error order.
    pub zone_assignments: Vec<(String, String)>,
}

impl ConstraintData {
    /// `PlacementConstraints.get_zone_for_component(ref)` — exact-key dict
    /// lookup with `None` for a missing key.
    pub fn zone_for_component(&self, ref_: &str) -> Option<&str> {
        self.zone_assignments
            .iter()
            .find(|(r, _)| r == ref_)
            .map(|(_, z)| z.as_str())
    }
}

/// Default escape clearance used when `clearance_mm` is `None`
/// (`_in_escape_zone`: `ec.clearance_mm if ec.clearance_mm is not None else 3.0`).
pub const DEFAULT_ESCAPE_CLEARANCE: f64 = 3.0;

// ---------------------------------------------------------------------------
// Geometry — every formula replicates the Python source's operation ORDER so
// the f64 rounding is bit-identical (see VERIFICATION.md).
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Host-runtime libm `pow` — CPython's `x ** 2` is libm `pow`, not `x * x`.
//
// The oracle computes `math.sqrt((p1[0]-p2[0]) ** 2 + (p1[1]-p2[1]) ** 2)`,
// and CPython's float `**` calls the host runtime's libm `pow` — measured to
// differ from the (correctly-rounded) IEEE product `x * x` on ~0.14% of
// random f64. `f64::powf(2.0)` is not a safe stand-in either: the extension's
// release build folds it into `x * x`. So `pow` is resolved through `dlsym`
// once per process (same pattern as temper-thermal's `hostmath.rs`, same
// class-B1 bit-exactness rationale), with a `powf` fallback on platforms
// where the dlsym route fails. `sqrt` stays `f64::sqrt`: IEEE-754 requires a
// correctly-rounded square root, so it is bit-identical to `math.sqrt`.
//
// How the two routes actually resolve, per platform (verified 2026-08-04):
//
// - **Linux (Ubuntu CI)**: `dlsym(RTLD_DEFAULT, "pow")` resolves the
//   process-global glibc libm `pow` — the primary route; the 200k-sample A/B
//   against the oracle shows zero mismatches.
// - **macOS**: `RTLD_DEFAULT` is `((void *) -2)` in Darwin's `<dlfcn.h>`, not
//   NULL. This file used to hardcode NULL on every target, so on macOS the
//   call failed outright — `dlerror()` reports literally
//   `dlsym(0x0, pow): invalid handle` — and the `f64::powf` fallback ran
//   every time. That was rationalised as "sound by accident" (a runtime
//   exponent stops LLVM folding `powf` to `x * x`, and the emitted `_pow`
//   resolves to libSystem, the same function CPython's `float_pow` calls),
//   but it made a silent lookup failure load-bearing and rested on an
//   optimiser non-guarantee. With the correct handle the dlsym route is now
//   the live route on macOS as well as Linux.
// - **Windows**: `#[cfg(not(target_arch = "wasm32"))]` compiles the `dlsym`
//   declaration on Windows, where the CRT has no `dlsym` — a link error.
//   Recorded, not fixed: out of scope for the Ubuntu CI target (the guard
//   exists to keep wasm32 builds off the dlsym path).
// ---------------------------------------------------------------------------

type PowFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_pow() -> Option<PowFn> {
    unsafe extern "C" {
        fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
    }
    // `RTLD_DEFAULT` is `((void *) 0)` on glibc but `((void *) -2)` on Darwin;
    // hardcoding null made every macOS lookup miss silently.
    #[cfg(target_vendor = "apple")]
    const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2
    #[cfg(not(target_vendor = "apple"))]
    const RTLD_DEFAULT: *const u8 = core::ptr::null();
    let symbol = c"pow";
    // SAFETY: `symbol` is a NUL-terminated C string literal; RTLD_DEFAULT is
    // this platform's "search every loaded object" handle (never
    // dereferenced); a miss returns null, which is checked.
    let p = unsafe { dlsym(RTLD_DEFAULT, symbol.as_ptr().cast::<u8>()) };
    if p.is_null() {
        None
    } else {
        // SAFETY: the resolved symbol is C `double(double, double)` from libm.
        Some(unsafe { std::mem::transmute::<*mut u8, PowFn>(p) })
    }
}

/// `f64::powf` as an `extern "C"`-compatible fallback (dlsym unavailable).
///
/// No longer the live route on macOS: with the correct Darwin `RTLD_DEFAULT`
/// (`-2`, see the platform note above) the dlsym lookup succeeds, so this is
/// reached only where `dlsym` genuinely cannot resolve `pow`. Keeping it
/// correct still matters — `f64::powf` with a *runtime* exponent lowers to a
/// libSystem `_pow` call rather than `x * x` — but the bit-exactness
/// guarantee no longer depends on that optimiser behaviour.
unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    f64::powf(x, y)
}

#[cfg(not(target_arch = "wasm32"))]
fn host_pow() -> PowFn {
    static F: std::sync::OnceLock<PowFn> = std::sync::OnceLock::new();
    *F.get_or_init(|| dlsym_pow().unwrap_or(fallback_pow as PowFn))
}

/// CPython's float `**` (the host Python runtime's libm `pow`).
#[inline]
pub fn py_pow(x: f64, y: f64) -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    // SAFETY: `host_pow()` is C `double(double, double)`; no shared state.
    unsafe {
        (host_pow())(x, y)
    }
    #[cfg(target_arch = "wasm32")]
    f64::powf(x, y)
}

pub fn distance(p1: (f64, f64), p2: (f64, f64)) -> f64 {
    let dx = p1.0 - p2.0;
    let dy = p1.1 - p2.1;
    // `py_pow(x, 2.0)`, NOT `x * x` and not `x.powf(2.0)`: the oracle's
    // `_distance` uses `** 2` (libm pow — see the trap note above). `.sqrt()`
    // is correctly-rounded IEEE sqrt (== CPython `math.sqrt`).
    (py_pow(dx, 2.0) + py_pow(dy, 2.0)).sqrt()
}

/// CPython 3.12+ `sum()` is Neumaier-compensated (not naive `+=`); replicating
/// it exactly is what keeps `_centroid` bit-identical for n >= 8 with
/// cancellation (the Wave-4 guide's "summation strategy" trap).
pub fn neumaier_sum(iter: impl Iterator<Item = f64>) -> f64 {
    let mut sum = 0.0_f64;
    let mut c = 0.0_f64;
    for v in iter {
        let t = sum + v;
        if sum.abs() >= v.abs() {
            c += (sum - t) + v;
        } else {
            c += (v - t) + sum;
        }
        sum = t;
    }
    sum + c
}

/// `_centroid`: `sum(...) / len(points)`, empty -> `(0.0, 0.0)`.
pub fn centroid(points: &[(f64, f64)]) -> (f64, f64) {
    if points.is_empty() {
        return (0.0, 0.0);
    }
    let sx = neumaier_sum(points.iter().map(|p| p.0));
    let sy = neumaier_sum(points.iter().map(|p| p.1));
    let n = points.len() as f64;
    (sx / n, sy / n)
}

/// CPython builtin `min(list)` semantics: first element is the running result;
/// replace only when a later element is STRICTLY smaller. (Rust `f64::min`
/// would discard NaN; this fold matches Python exactly, including NaN.)
pub fn py_min(list: &[f64]) -> f64 {
    debug_assert!(!list.is_empty());
    let mut m = list[0];
    for &v in &list[1..] {
        if v < m {
            m = v;
        }
    }
    m
}

/// CPython builtin `max(list)` semantics: first element is the running result;
/// replace only when a later element is STRICTLY greater.
pub fn py_max(list: &[f64]) -> f64 {
    debug_assert!(!list.is_empty());
    let mut m = list[0];
    for &v in &list[1..] {
        if v > m {
            m = v;
        }
    }
    m
}

/// `min(1, t)` with CPython semantics: result is `t` only if `t < 1`, else `1`
/// (so `min(1, NaN) == 1`, unlike Rust's `f64::min`).
#[inline]
pub fn py_min_1(t: f64) -> f64 {
    if t < 1.0 {
        t
    } else {
        1.0
    }
}

/// `max(0, m)` with CPython semantics: result is `m` only if `m > 0`, else `0`
/// (so `max(0, NaN) == 0`).
#[inline]
pub fn py_max_0(m: f64) -> f64 {
    if m > 0.0 {
        m
    } else {
        0.0
    }
}

/// `_min_edge_distance`: `min(x - x0, x1 - x, y - y0, y1 - y)` — builtin-min
/// semantics over the four edge distances.
pub fn min_edge_distance(slot: (f64, f64), bounds: [f64; 4]) -> f64 {
    let (x, y) = slot;
    let [x0, y0, x1, y1] = bounds;
    py_min(&[x - x0, x1 - x, y - y0, y1 - y])
}

/// `_point_to_segment_distance` — perpendicular projection with endpoint
/// clamping. The clamp is `max(0, min(1, t))` with Python min/max NaN
/// semantics (a NaN `t` clamps to `1.0`, not NaN).
pub fn point_to_segment_distance(p: (f64, f64), a: (f64, f64), b: (f64, f64)) -> f64 {
    let ab_x = b.0 - a.0;
    let ab_y = b.1 - a.1;
    let ap_x = p.0 - a.0;
    let ap_y = p.1 - a.1;
    let ab_len_sq = ab_x * ab_x + ab_y * ab_y;
    if ab_len_sq == 0.0 {
        return distance(p, a);
    }
    let t = py_max_0(py_min_1((ap_x * ab_x + ap_y * ab_y) / ab_len_sq));
    let closest_x = a.0 + t * ab_x;
    let closest_y = a.1 + t * ab_y;
    distance(p, (closest_x, closest_y))
}

/// `_in_zone`: `x0 <= x <= x1 and y0 <= y <= y1`.
pub fn in_zone(slot: (f64, f64), bounds: [f64; 4]) -> bool {
    let (x, y) = slot;
    let [x0, y0, x1, y1] = bounds;
    x0 <= x && x <= x1 && y0 <= y && y <= y1
}

/// `_in_corridor`: both endpoints must be placed, then the slot is inside if
/// its point-to-segment distance is strictly less than half the corridor width.
pub fn in_corridor_impl(
    slot: (f64, f64),
    corridor: &Corridor,
    lookup: &dyn Fn(&str) -> Option<(f64, f64)>,
) -> bool {
    let Some(p1) = lookup(&corridor.from_component) else {
        return false;
    };
    let Some(p2) = lookup(&corridor.to_component) else {
        return false;
    };
    point_to_segment_distance(slot, p1, p2) < corridor.width_mm / 2.0
}

// ---------------------------------------------------------------------------
// Float formatting — `str(float)` parity (see VERIFICATION.md "CPython repr
// divergences"): Rust `{}` writes `1e300`/`1e-5`/`1` where CPython writes
// `1e+300`/`1e-05`/`1.0`.
// ---------------------------------------------------------------------------

/// CPython `str(x)` for floats: shortest round-trip digits (identical to
/// Rust's `{:e}` digit extraction), decimal notation for `1e-4 <= |x| < 1e16`
/// with a trailing `.0` on integrals, exponent notation otherwise with a
/// signed, zero-padded-to-2 exponent (`1e+16`, `1e-05`).
pub fn py_float_str(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0".to_string() } else { "0.0".to_string() };
    }
    // Rust's `{:e}` emits the shortest digits that round-trip — the same digit
    // sequence CPython's repr uses — with the decimal exponent in the suffix.
    let s = format!("{x:e}");
    // `{:e}` always contains exactly one `e`; the `match` is a non-panicking
    // fallback that satisfies the no-`expect` rule rather than an assertion
    // that can fail.
    let Some((mant, exp)) = s.split_once('e') else {
        return s;
    };
    let Ok(exp) = exp.parse::<i32>() else {
        return s;
    };
    let (sign, mant) = match mant.strip_prefix('-') {
        Some(m) => ("-", m),
        None => ("", mant),
    };
    let (int_part, frac_part) = match mant.split_once('.') {
        Some((a, b)) => (a, b),
        None => (mant, ""),
    };
    let sig = format!("{int_part}{frac_part}");
    let n = sig.len() as i32;
    let point_pos = exp + 1; // digits before the decimal point

    if (-4..16).contains(&exp) {
        let mut out = String::from(sign);
        if point_pos <= 0 {
            out.push_str("0.");
            for _ in 0..(-point_pos) {
                out.push('0');
            }
            out.push_str(&sig);
        } else if point_pos >= n {
            out.push_str(&sig);
            for _ in 0..(point_pos - n) {
                out.push('0');
            }
            out.push_str(".0");
        } else {
            out.push_str(&sig[..point_pos as usize]);
            out.push('.');
            out.push_str(&sig[point_pos as usize..]);
        }
        out
    } else {
        let mut out = String::from(sign);
        out.push_str(&sig[..1]);
        if sig.len() > 1 {
            out.push('.');
            out.push_str(&sig[1..]);
        }
        out.push('e');
        out.push(if exp < 0 { '-' } else { '+' });
        let e = exp.abs();
        if e < 10 {
            out.push('0');
        }
        out.push_str(&e.to_string());
        out
    }
}

/// Python's `str.lower()` restricted to the ASCII fold. Component refs and net
/// names are ASCII in every fixture and in the differential; using the full
/// Unicode fold (Rust `to_lowercase` applies the Greek final-sigma rule that
/// CPython's `lower` does not) would diverge on non-ASCII input for zero real
/// benefit — the divergence is documented in VERIFICATION.md.
pub fn py_lower(s: &str) -> String {
    s.chars().map(|c| c.to_ascii_lowercase()).collect()
}

/// CPython's `f"{x:.1f}"` for the message float sites: round-half-even at one
/// decimal — byte-identical to Rust's `{x:.1}` on every finite value (pinned
/// by the existing message comparisons) — except that NaN/inf render as
/// `nan`/`inf`/`-inf`, where Rust's Display writes `NaN` (CPython's `%.1f`
/// never writes `NaN`). The escape/corridor *distance* sites are unreachable
/// with NaN through `check()` (`NaN < x` is False, so no violation ever
/// carries a NaN distance), but every `{:.1}` message site goes through this
/// helper so a NaN that does reach one (spacing/proximity distance, thermal
/// edge distance/threshold, group-spread diagonal, escape/corridor zone
/// clearance) renders identically on both sides.
pub fn py_float_fmt_1(x: f64) -> String {
    if x.is_nan() {
        return "nan".to_string();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    format!("{x:.1}")
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
        assert!(dlsym_pow().is_some(), "dlsym could not resolve `pow`");
    }

    #[cfg_attr(test, test)]
    fn py_float_str_matches_cpython() {
        let cases: &[(f64, &str)] = &[
            (1.0, "1.0"),
            (2.0, "2.0"),
            (0.5, "0.5"),
            (-0.5, "-0.5"),
            (1e16, "1e+16"),
            (1.5e16, "1.5e+16"),
            (1e15, "1000000000000000.0"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (2.5e-5, "2.5e-05"),
            (5e-324, "5e-324"),
            (-0.0, "-0.0"),
            (0.0, "0.0"),
            (123.456, "123.456"),
            (100.0, "100.0"),
            (1e300, "1e+300"),
            (1e-300, "1e-300"),
            (2.675, "2.675"),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
            (0.30000000000000004, "0.30000000000000004"),
        ];
        for (x, expected) in cases {
            assert_eq!(&py_float_str(*x), expected, "py_float_str({x:?})");
        }
    }

    #[cfg_attr(test, test)]
    fn neumaier_matches_cpython_sum() {
        // CPython 3.12 sum([1e16, 1.0, -1e16]) == 1.0 (Neumaier); naive is 0.0.
        let v = [1e16_f64, 1.0, -1e16];
        assert_eq!(neumaier_sum(v.iter().copied()), 1.0);
        let w = [1e16_f64, -1e16, 1.0];
        assert_eq!(neumaier_sum(w.iter().copied()), 1.0);
        // Empty sum is 0.0 (CPython sum([]) == 0).
        assert_eq!(neumaier_sum(std::iter::empty()), 0.0);
    }

    #[cfg_attr(test, test)]
    fn clamp_nan_semantics_match_cpython() {
        // max(0, min(1, nan)) == 1 in CPython (nan < 1 is False, 1 is kept).
        assert_eq!(py_max_0(py_min_1(f64::NAN)), 1.0);
        // max(0, min(1, -inf)) == 0; max(0, min(1, inf)) == 1.
        assert_eq!(py_max_0(py_min_1(f64::NEG_INFINITY)), 0.0);
        assert_eq!(py_max_0(py_min_1(f64::INFINITY)), 1.0);
        assert_eq!(py_max_0(py_min_1(0.5)), 0.5);
        assert_eq!(py_max_0(py_min_1(-0.5)), 0.0);
    }

    #[cfg_attr(test, test)]
    fn min_max_fold_semantics() {
        // First element is the running result; NaN at position 0 wins, later
        // NaN never replaces.
        assert_eq!(py_min(&[3.0, 1.0, 2.0]), 1.0);
        assert!(py_min(&[f64::NAN, 1.0]).is_nan());
        assert_eq!(py_min(&[1.0, f64::NAN]), 1.0);
        assert_eq!(py_max(&[1.0, 3.0, 2.0]), 3.0);
        assert!(py_max(&[f64::NAN, 1.0]).is_nan());
        assert_eq!(py_max(&[1.0, f64::NAN]), 1.0);
    }

    #[cfg_attr(test, test)]
    fn py_lower_is_ascii_only() {
        assert_eq!(py_lower("U_MCU"), "u_mcu");
        assert_eq!(py_lower(""), "");
    }

    #[cfg_attr(test, test)]
    fn py_float_fmt_1_matches_cpython() {
        // CPython `f"{x:.1f}"` on the finite set is round-half-even at one
        // decimal — identical to Rust `{x:.1}` (pinned transitively by the
        // message comparisons). The divergence this helper closes is NaN:
        // CPython renders 'nan', Rust Display renders 'NaN'.
        let cases: &[(f64, &str)] = &[
            (10.0, "10.0"),
            (10.25, "10.2"),
            (10.26, "10.3"),
            (2.5, "2.5"),
            (3.5, "3.5"),
            (-0.0, "-0.0"),
            (0.0, "0.0"),
            (0.05, "0.1"),
            (0.04, "0.0"),
            (1e300, "1000000000000000052504760255204420248704468581108159154915854115511802457988908195786371375080447864043704443832883878176942523235360430575644792184786706982848387200926575803737830233794788090059368953234970799945081119038967640880074652742780142494579258788820056842838115669472196386865459400540160.0"),
            (f64::NAN, "nan"),
            (f64::INFINITY, "inf"),
            (f64::NEG_INFINITY, "-inf"),
        ];
        for (x, expected) in cases {
            assert_eq!(&py_float_fmt_1(*x), expected, "py_float_fmt_1({x:?})");
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(not(target_arch = "wasm32"))] ("constraints::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("constraints::tests::py_float_str_matches_cpython", py_float_str_matches_cpython),
        ("constraints::tests::neumaier_matches_cpython_sum", neumaier_matches_cpython_sum),
        ("constraints::tests::clamp_nan_semantics_match_cpython", clamp_nan_semantics_match_cpython),
        ("constraints::tests::min_max_fold_semantics", min_max_fold_semantics),
        ("constraints::tests::py_lower_is_ascii_only", py_lower_is_ascii_only),
        ("constraints::tests::py_float_fmt_1_matches_cpython", py_float_fmt_1_matches_cpython),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

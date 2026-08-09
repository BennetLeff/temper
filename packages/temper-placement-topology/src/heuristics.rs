//! Placement-heuristic kernels (Wave 4, heuristics/ slice).
//!
//! Ported from `packages/temper-placer/src/temper_placer/heuristics/` under the
//! R1 gate set: `conflict.py`'s overlap scan and nudge-candidate selection,
//! `topological_init.py`'s feasibility arithmetic, and `power_stage.py`'s
//! numpy-clip boundary clamp. See this crate's `VERIFICATION.md` for the
//! differential/PBT/metamorphic evidence.
//!
//! The shims keep the public API and all orchestration (object navigation,
//! `is_position_valid` trial loops, message formatting) in Python; only the
//! float arithmetic moved here. That split follows the sibling
//! organizational/style migrations in `temper-geometry` ("the trial loop stays
//! Python"), so a bit-exact differential never has to render float text in
//! Rust.

use crate::numeric::{neumaier_sum, py_min};

// ---------------------------------------------------------------------------
// numpy `np.clip` semantics (B12)
// ---------------------------------------------------------------------------

/// `np.maximum(a, b)`: NaN propagates from *either* operand (B12 — distinct
/// from both CPython's builtin `max` and from `f64::max`, which discards NaN).
#[inline]
fn np_maximum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else {
        a.max(b)
    }
}

/// `np.minimum(a, b)`; mirror of [`np_maximum`].
#[inline]
fn np_minimum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else {
        a.min(b)
    }
}

/// `np.clip(v, lo, hi)` = `np.minimum(np.maximum(v, lo), hi)`.
///
/// Two properties differ from `f64::clamp` (B12, measured): a NaN in *any* of
/// the three operands propagates (where `f64::clamp` panics on a NaN bound),
/// and an inverted `lo > hi` returns `hi` (where `f64::clamp` panics). The
/// `power_stage.py` shims call this for every boundary clamp.
#[inline]
pub fn np_clip(v: f64, lo: f64, hi: f64) -> f64 {
    np_minimum(np_maximum(v, lo), hi)
}

// ---------------------------------------------------------------------------
// conflict.py
// ---------------------------------------------------------------------------

/// First overlapping placement, mirroring `ConflictResolver.check_conflict`.
///
/// `boxes` is `(other_x, other_y, other_w, other_h)` in the caller's
/// `self.placements` insertion order; the returned index selects the caller's
/// ref from the list it built. Returns `(index, overlap)` where
/// `overlap = min(overlap_x, overlap_y)` with CPython builtin-`min` NaN
/// semantics ([`py_min`]), matching `ConflictResolver._nudge_placement`'s
/// later `overlap + min_spacing`.
pub fn overlap_check(
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    boxes: &[(f64, f64, f64, f64)],
    min_spacing: f64,
) -> Option<(usize, f64)> {
    let half_w = width / 2.0;
    let half_h = height / 2.0;
    for (i, &(ox, oy, other_w, other_h)) in boxes.iter().enumerate() {
        let other_half_w = other_w / 2.0;
        let other_half_h = other_h / 2.0;
        let dx = (x - ox).abs();
        let dy = (y - oy).abs();
        let overlap_x = (half_w + other_half_w + min_spacing) - dx;
        let overlap_y = (half_h + other_half_h + min_spacing) - dy;
        if overlap_x > 0.0 && overlap_y > 0.0 {
            return Some((i, py_min(overlap_x, overlap_y)));
        }
    }
    None
}

/// Ordered nudge candidates, mirroring `ConflictResolver._nudge_placement`.
///
/// The primary candidate follows the axis of max separation
/// (`|dx| > |dy|` → horizontal), with the sign of the separation; the four
/// fallback directions `(+d,0),(-d,0),(0,+d),(0,-d)` follow in the oracle's
/// trial order. The caller tries each candidate through
/// `context.is_position_valid` + a re-run of `overlap_check` — the trial loop
/// stays Python.
pub fn nudge_candidates(
    x: f64,
    y: f64,
    cx: f64,
    cy: f64,
    overlap_mm: f64,
    min_spacing: f64,
) -> Vec<(f64, f64)> {
    let d = overlap_mm + min_spacing;
    let dx = x - cx;
    let dy = y - cy;
    let primary = if dx.abs() > dy.abs() {
        if dx > 0.0 { (d, 0.0) } else { (-d, 0.0) }
    } else {
        if dy > 0.0 { (0.0, d) } else { (0.0, -d) }
    };
    vec![
        primary,
        (d, 0.0),
        (-d, 0.0),
        (0.0, d),
        (0.0, -d),
    ]
}

// ---------------------------------------------------------------------------
// topological_init.py
// ---------------------------------------------------------------------------

/// Feasibility arithmetic, mirroring `TopologicalInitializationHeuristic.
/// _check_feasibility`.
///
/// `sizes` is `(width, height)` in netlist order (the shim builds its dict in
/// netlist order, so the returned `fits` flags zip back 1:1). `zone_dims` is
/// `(width, height)` per zone — the shim already resolved the no-zone fallback
/// to `[(board.width, board.height)]`, matching the oracle's own branch. Both
/// area totals use [`neumaier_sum`] because the oracle computes them with
/// CPython 3.12's compensated builtin `sum()` (B12).
pub fn feasibility_check(
    sizes: &[(f64, f64)],
    zone_dims: &[(f64, f64)],
    margin: f64,
) -> (Vec<bool>, f64, f64) {
    let fits: Vec<bool> = sizes
        .iter()
        .map(|&(cw, ch)| {
            zone_dims.iter().any(|&(zw, zh)| {
                let available_w = zw - 2.0 * margin;
                let available_h = zh - 2.0 * margin;
                (cw <= available_w && ch <= available_h)
                    || (ch <= available_w && cw <= available_h)
            })
        })
        .collect();
    let total_component_area = neumaier_sum(sizes.iter().map(|&(w, h)| w * h));
    let total_zone_area = neumaier_sum(
        zone_dims
            .iter()
            .map(|&(w, h)| (w - 2.0 * margin) * (h - 2.0 * margin)),
    );
    (fits, total_component_area, total_zone_area)
}

// ---------------------------------------------------------------------------
// power_stage.py
// ---------------------------------------------------------------------------

/// Board-boundary clamp, mirroring `power_stage.py`'s `np.clip(...)` calls.
///
/// The shim computes `x = anchor_x + offset_x` (and the `comp.initial_position`
/// variant) in Python, so the plain additions stay in the oracle's language;
/// the numpy-clip semantics of the boundary clamp are the compute that moves
/// (B12 — `f64::clamp` panics on inverted bounds/NaN where `np.clip` returns a
/// value).
pub fn clamp_position(
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    board_w: f64,
    board_h: f64,
    margin: f64,
) -> (f64, f64) {
    let half_w = width / 2.0;
    let half_h = height / 2.0;
    let clamped_x = np_clip(x, margin + half_w, board_w - margin - half_w);
    let clamped_y = np_clip(y, margin + half_h, board_h - margin - half_h);
    (clamped_x, clamped_y)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlap_detects_a_real_conflict_and_reports_min_axis_overlap() {
        // Candidate at (0,0) size 2x2; existing at (0,0) size 4x4; spacing 0.5.
        // dx=0, dy=0; overlap_x = 1+2+0.5 = 3.5; overlap_y = 3.5.
        let hit = overlap_check(0.0, 0.0, 2.0, 2.0, &[(0.0, 0.0, 4.0, 4.0)], 0.5);
        assert_eq!(hit, Some((0, 3.5)));
    }

    #[test]
    fn overlap_exactly_at_spacing_is_not_a_conflict() {
        // half_w=1, other_half_w=1, spacing=0.5 -> overlap_x = 2.5 - dx.
        // dx=2.5 exactly -> overlap_x = 0.0; `> 0.0` excludes it (M: `>=` caught).
        let hit = overlap_check(0.0, 0.0, 2.0, 2.0, &[(2.5, 0.0, 2.0, 2.0)], 0.5);
        assert_eq!(hit, None);
    }

    #[test]
    fn overlap_picks_the_first_conflict_in_given_order() {
        let boxes = [(10.0, 10.0, 1.0, 1.0), (0.0, 0.0, 2.0, 2.0)];
        let hit = overlap_check(0.0, 0.0, 2.0, 2.0, &boxes, 0.0);
        assert_eq!(hit.map(|(i, _)| i), Some(1));
    }

    #[test]
    fn nudge_primary_follows_the_dominant_axis_and_sign() {
        // |dx|=5 > |dy|=1 -> horizontal; dx>0 -> +d.
        let c = nudge_candidates(10.0, 10.0, 5.0, 9.0, 3.0, 0.5);
        assert_eq!(c[0], (3.5, 0.0));
        // |dx|=1 < |dy|=5 -> vertical; dy>0 -> +d.
        let c = nudge_candidates(10.0, 10.0, 9.0, 5.0, 3.0, 0.5);
        assert_eq!(c[0], (0.0, 3.5));
        // dy<0 -> -d.
        let c = nudge_candidates(10.0, 10.0, 9.0, 15.0, 3.0, 0.5);
        assert_eq!(c[0], (0.0, -3.5));
    }

    #[test]
    fn nudge_tie_goes_vertical_and_fallbacks_follow_oracle_order() {
        // |dx| == |dy| -> vertical branch; dy>0 -> +d.
        let c = nudge_candidates(10.0, 10.0, 5.0, 5.0, 2.0, 1.0);
        assert_eq!(
            c,
            vec![(0.0, 3.0), (3.0, 0.0), (-3.0, 0.0), (0.0, 3.0), (0.0, -3.0)]
        );
    }

    #[test]
    fn feasibility_reports_fit_flags_in_input_order() {
        let sizes = [(50.0, 5.0), (1.0, 1.0)];
        let zone_dims = [(20.0, 20.0)];
        let (fits, _, _) = feasibility_check(&sizes, &zone_dims, 0.0);
        assert_eq!(fits, vec![false, true]);
    }

    #[test]
    fn feasibility_accepts_either_orientation() {
        // 18x2 fits in a 2x18 zone only rotated.
        let sizes = [(18.0, 2.0)];
        let zone_dims = [(2.0, 18.0)];
        let (fits, _, _) = feasibility_check(&sizes, &zone_dims, 0.0);
        assert_eq!(fits, vec![true]);
    }

    #[test]
    fn feasibility_margin_erodes_the_zone_in_both_axes() {
        // zone 20x20, margin 2 -> available 16x16. 15x15 fits; 17x17 doesn't.
        let (fits, _, _) = feasibility_check(&[(15.0, 15.0)], &[(20.0, 20.0)], 2.0);
        assert_eq!(fits, vec![true]);
        let (fits, _, _) = feasibility_check(&[(17.0, 17.0)], &[(20.0, 20.0)], 2.0);
        assert_eq!(fits, vec![false]);
        // the same 17x17 fits without the margin erosion
        let (fits, _, _) = feasibility_check(&[(17.0, 17.0)], &[(20.0, 20.0)], 0.0);
        assert_eq!(fits, vec![true]);
    }

    #[test]
    fn feasibility_area_totals_are_neumaier_compensated() {
        // The documented n=8 divergence: naive `+=` of [0.1]*8 is 1 ulp below
        // CPython `sum()`; the kernel must match the compensated value.
        let sizes = [(0.1, 1.0); 8];
        let (_, total, _) = feasibility_check(&sizes, &[(1.0, 1.0)], 0.0);
        assert_eq!(total.to_bits(), 0.8f64.to_bits());
        let mut naive = 0.0f64;
        for &(w, h) in &sizes {
            naive += w * h;
        }
        assert_ne!(naive.to_bits(), total.to_bits());
        // Catastrophic cancellation: naive loses every small term.
        let mut cancel = vec![(0.1, 1.0); 10];
        cancel.push((1e100, 1.0));
        cancel.push((-1e100, 1.0));
        let (_, total, _) = feasibility_check(&cancel, &[(1e6, 1e6)], 0.0);
        assert_eq!(total, 1.0);
    }

    #[test]
    fn clamp_inverted_bounds_returns_hi_like_np_clip_not_f64_clamp() {
        // Component wider than the board -> lo > hi. np.clip returns hi;
        // f64::clamp would panic. This is the B12 semantic the kernel exists for.
        let (x, y) = clamp_position(0.0, 0.0, 200.0, 1.0, 100.0, 100.0, 5.0);
        assert_eq!(x, 100.0 - 5.0 - 100.0); // hi = board_w - margin - half_w
        assert_eq!(y, 5.5); // y: lo = 5.5, hi = 94.5, both ordered -> clip to 5.5
    }

    #[test]
    fn clamp_propagates_nan_from_any_operand() {
        let (x, _) = clamp_position(f64::NAN, 0.0, 1.0, 1.0, 100.0, 100.0, 5.0);
        assert!(x.is_nan());
        let (x, _) = clamp_position(0.0, 0.0, f64::NAN, 1.0, 100.0, 100.0, 5.0);
        assert!(x.is_nan());
        // inverted bounds (via a NaN half-width -> lo=NaN) still return NaN
        let (x, _) = clamp_position(50.0, 0.0, f64::NAN, 1.0, 100.0, 100.0, 5.0);
        assert!(x.is_nan());
    }

    #[test]
    fn clamp_clips_to_the_valid_range_when_bounds_are_ordered() {
        let (x, y) = clamp_position(500.0, -500.0, 10.0, 10.0, 100.0, 100.0, 5.0);
        assert_eq!((x, y), (90.0, 10.0));
        let (x, y) = clamp_position(50.0, 50.0, 10.0, 10.0, 100.0, 100.0, 5.0);
        assert_eq!((x, y), (50.0, 50.0));
    }
}

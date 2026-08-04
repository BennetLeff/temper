// =============================================================================
// DRC inflation kernels — Wave 4 Phase 4 port of temper_placer/geometry/drc_inflate.py
// =============================================================================
//
// Scope. Three of the module's six public surfaces live here; the other three
// (`inflate_pad_polygon`, `precompute_inflated_dims`, `precompute_from_pad_polygons`)
// deliberately stay in Python on Shapely. That is a recorded R3 JUSTIFIED-KEEP
// with a named blocker, not an omission: `buffer(r, resolution=16)` is GEOS's
// *polygonal approximation* of the round offset, so the inflated bounds are not
// the closed form `bounds ± r`. Measured on 169 random polygons: 169/169 differ,
// worst deviation 2.4e-3 mm; even axis-aligned rectangles differ in 12/400 cases.
// See packages/temper-geometry/VERIFICATION.md.
//
// (An earlier revision of this file carried functions with those same three
// names. They were dead — no caller in Rust or Python — and they were *not* the
// Python semantics: `inflate_pad_polygon` pushed vertices away from the
// centroid instead of taking a Minkowski sum, and `precompute_inflated_dims`
// took a (width, height) pair where Python takes a list of polygons. They were
// retired with this port rather than left to be mistaken for the real thing.)
//
// Two properties of the numpy original are load-bearing and are reproduced
// exactly rather than "cleaned up":
//
//   * dtype width — the pairwise gap arithmetic runs in the caller's dtype
//     (float32 at every shipped call site), widening to float64 only at the
//     softplus. See `Width` below.
//   * reduction order — `np.sum` is a blocked pairwise reduction, and float
//     addition is not associative. See `pairwise_sum` below.

use crate::smooth::smooth_relu;

// -----------------------------------------------------------------------------
// numpy dtype-width emulation
// -----------------------------------------------------------------------------

/// Round an exact f64 intermediate to the width numpy would have produced.
///
/// Every operation this module performs on the geometry side is `+`, `-`,
/// `abs`, `min` or `max` over values that are exactly representable in f32. For
/// those, IEEE-754 gives `f32_op(a, b) == round_f32(f64_op(a, b))` — the f64
/// result of one such operation on f32 operands is exact, so a single rounding
/// step reproduces f32 arithmetic without needing a separate f32 code path.
#[inline]
fn round_to(as_f32: bool, v: f64) -> f64 {
    if as_f32 { v as f32 as f64 } else { v }
}

/// `np.minimum`, including its NaN and signed-zero behaviour.
///
/// numpy's scalar form is `(a < b || isnan(a)) ? a : b`, which propagates a NaN
/// in *either* operand (a NaN in `b` loses the `a < b` comparison and is
/// returned). `f64::min` instead *ignores* NaN, so it is the wrong primitive.
#[inline]
fn np_minimum(a: f64, b: f64) -> f64 {
    if a < b || a.is_nan() { a } else { b }
}

/// `np.maximum` — the mirror of [`np_minimum`], with the same NaN contract.
#[inline]
fn np_maximum(a: f64, b: f64) -> f64 {
    if a > b || a.is_nan() { a } else { b }
}

// -----------------------------------------------------------------------------
// numpy's blocked pairwise summation
// -----------------------------------------------------------------------------

/// numpy's unrolled-block size for `add.reduce` (`PW_BLOCKSIZE`).
const PW_BLOCKSIZE: usize = 128;

/// Reproduce `np.sum` over a contiguous f64 array, bit for bit.
///
/// `np.sum` does **not** accumulate left to right. It uses the blocked pairwise
/// algorithm below (numpy's `pairwise_sum_DOUBLE`), and because float addition
/// is not associative the two orders give different bits: measured on this
/// repo's own corpora they disagree at n = 8, 16, 129, 300 and 4950. A naive
/// `iter().sum()` here would be numerically reasonable and bit-wrong, so the
/// blocking is transcribed rather than approximated.
///
/// The differential suite pins that the two orders genuinely differ on the
/// tested corpus, so this reproduction cannot pass for the trivial reason.
fn pairwise_sum(a: &[f64]) -> f64 {
    let n = a.len();

    if n < 8 {
        let mut res = 0.0;
        for &v in a {
            res += v;
        }
        return res;
    }

    if n <= PW_BLOCKSIZE {
        // Eight independent accumulators, filled from the first eight elements.
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let unrolled_end = n - (n % 8);
        let mut i = 8;
        while i < unrolled_end {
            for (k, acc) in r.iter_mut().enumerate() {
                *acc += a[i + k];
            }
            i += 8;
        }
        // The reduction tree numpy uses to combine the accumulators; the
        // parenthesisation is part of the result, not a style choice.
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        return res;
    }

    // Split, keeping the left half a multiple of the unroll factor.
    let mut n2 = n / 2;
    n2 -= n2 % 8;
    pairwise_sum(&a[..n2]) + pairwise_sum(&a[n2..])
}

// -----------------------------------------------------------------------------
// Kernels
// -----------------------------------------------------------------------------

/// Vectorised smooth ReLU: `softplus(alpha * x) / alpha`, elementwise.
///
/// The Python original widened its input to float64 on entry and kept a stable
/// branch split so the untaken arm can never overflow. Both are preserved: the
/// per-element body is [`crate::smooth::smooth_relu`], which carries exactly
/// that split, and the caller hands us f64 already.
pub fn smooth_relu_array(xs: &[f64], alpha: f64) -> Vec<f64> {
    xs.iter().map(|&x| smooth_relu(x, alpha)).collect()
}

/// Inflate `(width, height)` bounds by `trace_width_mm` and halve them.
///
/// `half = (bound + trace_width_mm) / 2`, evaluated in `bounds`'s own width.
/// When `as_f32` is set, `trace_width_mm` is narrowed to f32 *first* — numpy's
/// NEP-50 weak-scalar promotion casts the Python float to the array's dtype
/// before the add, and for a value like 0.1, adding the f64 literal and then
/// rounding is not the same as adding the f32 literal.
///
/// Shape-agnostic by construction: the Python original broadcasts and never
/// indexes, so a flat buffer plus the caller's own reshape is faithful.
pub fn inflated_half_dims_from_bounds(
    bounds: &[f64],
    trace_width_mm: f64,
    as_f32: bool,
) -> Vec<f64> {
    let inflation = round_to(as_f32, trace_width_mm);
    bounds
        .iter()
        .map(|&b| round_to(as_f32, round_to(as_f32, b + inflation) / 2.0))
        .collect()
}

/// Sum of squared clearance violations over every component pair.
///
/// `positions` is a flat `(n, 2)` row-major buffer; `half_widths` and
/// `half_heights` are length `n`. The three `*_is_f32` flags carry the caller's
/// numpy dtypes so the gap arithmetic rounds where numpy would; they are
/// independent because numpy promotes per-operation, not per-call.
///
/// Only the strict upper triangle is evaluated. The Python original built the
/// full `n x n` matrix and then indexed `triu_indices(n, k=1)`; every operation
/// in that pipeline is elementwise, so the discarded entries cannot influence
/// the kept ones, and the row-major `(i, j)` order matches `triu_indices`.
#[allow(clippy::too_many_arguments)]
pub fn drc_proxy_score(
    positions: &[f64],
    half_widths: &[f64],
    half_heights: &[f64],
    clearance_mm: f64,
    beta: f64,
    positions_is_f32: bool,
    half_widths_is_f32: bool,
    half_heights_is_f32: bool,
) -> f64 {
    let n = half_widths.len();
    if n < 2 {
        return 0.0;
    }

    // numpy promotion: a gap is f32 only when *both* of its operands are.
    let gap_x_f32 = positions_is_f32 && half_widths_is_f32;
    let gap_y_f32 = positions_is_f32 && half_heights_is_f32;
    // `np.where` promotes across both branches, so `distances` — and the
    // `clearance_mm - distances` that follows — is f32 only if both gaps are.
    let dist_f32 = gap_x_f32 && gap_y_f32;
    let clearance = round_to(dist_f32, clearance_mm);

    let mut squared = Vec::with_capacity(n * (n - 1) / 2);
    for i in 0..n {
        let (xi, yi) = (positions[2 * i], positions[2 * i + 1]);
        for j in (i + 1)..n {
            let (xj, yj) = (positions[2 * j], positions[2 * j + 1]);

            // center_diff, then abs — both at the positions' own width.
            let dx = round_to(positions_is_f32, xi - xj).abs();
            let dy = round_to(positions_is_f32, yi - yj).abs();

            let sum_half_w = round_to(half_widths_is_f32, half_widths[i] + half_widths[j]);
            let sum_half_h = round_to(half_heights_is_f32, half_heights[i] + half_heights[j]);

            let gap_x = round_to(gap_x_f32, dx - sum_half_w);
            let gap_y = round_to(gap_y_f32, dy - sum_half_h);

            // Both gaps negative => the boxes overlap in both axes and the more
            // negative gap is the penetration depth. Otherwise at least one axis
            // is clear and the larger gap is the separation.
            let distance = if gap_x < 0.0 && gap_y < 0.0 {
                np_minimum(gap_x, gap_y)
            } else {
                np_maximum(gap_x, gap_y)
            };

            let violation = smooth_relu(round_to(dist_f32, clearance - distance), beta);
            squared.push(violation * violation);
        }
    }

    pairwise_sum(&squared)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // pairwise_sum
    // -----------------------------------------------------------------

    /// The whole point of transcribing numpy's blocking is that it differs from
    /// naive accumulation. If it did not, this port would be pointless — so pin
    /// the disagreement, not just the agreement.
    #[test]
    fn pairwise_sum_differs_from_naive_accumulation() {
        // 0.1 is not representable in binary, so a long run of it accumulates
        // visible reassociation error.
        let a: Vec<f64> = (0..1000).map(|k| 0.1 + (k as f64) * 1e-9).collect();
        let naive: f64 = a.iter().fold(0.0, |acc, &v| acc + v);
        assert_ne!(
            pairwise_sum(&a).to_bits(),
            naive.to_bits(),
            "pairwise and naive summation agree — the blocking is untested"
        );
    }

    #[test]
    fn pairwise_sum_small_inputs_are_naive() {
        for n in 0..8usize {
            let a: Vec<f64> = (0..n).map(|k| 0.1 + k as f64).collect();
            let naive: f64 = a.iter().fold(0.0, |acc, &v| acc + v);
            assert_eq!(pairwise_sum(&a).to_bits(), naive.to_bits(), "n={n}");
        }
    }

    #[test]
    fn pairwise_sum_exact_on_representable_values() {
        // Powers of two sum exactly regardless of order, so any correct
        // reduction lands on the same answer.
        let a: Vec<f64> = (0..300).map(|_| 0.5).collect();
        assert_eq!(pairwise_sum(&a), 150.0);
    }

    #[test]
    fn pairwise_sum_empty_is_zero() {
        assert_eq!(pairwise_sum(&[]), 0.0);
    }

    // -----------------------------------------------------------------
    // np_minimum / np_maximum
    // -----------------------------------------------------------------

    #[test]
    fn np_min_max_propagate_nan_from_either_operand() {
        assert!(np_minimum(f64::NAN, 1.0).is_nan());
        assert!(np_minimum(1.0, f64::NAN).is_nan());
        assert!(np_maximum(f64::NAN, 1.0).is_nan());
        assert!(np_maximum(1.0, f64::NAN).is_nan());
        // f64::min would silently drop the NaN; that is the bug this guards.
        assert!(!f64::min(1.0, f64::NAN).is_nan());
    }

    #[test]
    fn np_min_max_ordinary_values() {
        assert_eq!(np_minimum(-3.0, 2.0), -3.0);
        assert_eq!(np_maximum(-3.0, 2.0), 2.0);
        assert_eq!(np_minimum(2.0, 2.0), 2.0);
    }

    // -----------------------------------------------------------------
    // round_to
    // -----------------------------------------------------------------

    #[test]
    fn round_to_f32_narrows_and_f64_does_not() {
        let v = 0.1f64;
        assert_ne!(round_to(true, v).to_bits(), v.to_bits());
        assert_eq!(round_to(false, v).to_bits(), v.to_bits());
    }

    // -----------------------------------------------------------------
    // smooth_relu_array
    // -----------------------------------------------------------------

    #[test]
    fn smooth_relu_array_matches_scalar_elementwise() {
        let xs = [-5.0, -0.5, 0.0, 0.5, 5.0, 70.0, -70.0];
        let got = smooth_relu_array(&xs, 10.0);
        for (i, &x) in xs.iter().enumerate() {
            assert_eq!(got[i].to_bits(), smooth_relu(x, 10.0).to_bits(), "i={i}");
        }
    }

    #[test]
    fn smooth_relu_array_is_monotone_and_bounds_relu() {
        let xs: Vec<f64> = (-50..50).map(|k| k as f64 * 0.1).collect();
        let got = smooth_relu_array(&xs, 10.0);
        for w in got.windows(2) {
            assert!(w[1] >= w[0], "softplus must be non-decreasing");
        }
        for (i, &x) in xs.iter().enumerate() {
            assert!(got[i] >= x.max(0.0) - 1e-12, "softplus dominates relu");
        }
    }

    #[test]
    fn smooth_relu_array_empty() {
        assert!(smooth_relu_array(&[], 10.0).is_empty());
    }

    // -----------------------------------------------------------------
    // inflated_half_dims_from_bounds
    // -----------------------------------------------------------------

    #[test]
    fn half_dims_f64_closed_form() {
        let got = inflated_half_dims_from_bounds(&[10.0, 5.0], 0.25, false);
        assert_eq!(got[0].to_bits(), ((10.0 + 0.25) / 2.0f64).to_bits());
        assert_eq!(got[1].to_bits(), ((5.0 + 0.25) / 2.0f64).to_bits());
    }

    #[test]
    fn half_dims_f32_narrows_the_intermediate() {
        // A width that is representable in f32 but whose inflated value is not.
        let b = 1.9658657312393188f64; // exactly an f32; chosen so the widths diverge
        let wide = inflated_half_dims_from_bounds(&[b], 0.25, false);
        let narrow = inflated_half_dims_from_bounds(&[b], 0.25, true);
        assert_ne!(
            wide[0].to_bits(),
            narrow[0].to_bits(),
            "f32 and f64 paths must not collapse — the dtype flag would be dead"
        );
        assert_eq!(narrow[0].to_bits(), (((b as f32 + 0.25f32) / 2.0f32) as f64).to_bits());
    }

    #[test]
    fn half_dims_narrows_the_trace_width_before_adding() {
        // 0.1 differs between f32 and f64; adding the wide literal and then
        // rounding is NOT the same as adding the narrow one.
        let b = 0.14703835546970367f64; // exactly an f32; found by search
        let got = inflated_half_dims_from_bounds(&[b], 0.1, true);
        let correct = ((b as f32 + 0.1f32) / 2.0f32) as f64;
        let wrong = (((b + 0.1f64) as f32) / 2.0f32) as f64;
        assert_eq!(got[0].to_bits(), correct.to_bits());
        // Guard that the two really do differ, so the assertion above bites.
        assert_ne!(correct.to_bits(), wrong.to_bits());
    }

    #[test]
    fn half_dims_empty() {
        assert!(inflated_half_dims_from_bounds(&[], 0.25, true).is_empty());
    }

    // -----------------------------------------------------------------
    // drc_proxy_score
    // -----------------------------------------------------------------

    fn grid(n: usize, spacing: f64) -> Vec<f64> {
        (0..n).flat_map(|i| [i as f64 * spacing, 0.0]).collect()
    }

    #[test]
    fn proxy_score_fewer_than_two_components_is_zero() {
        assert_eq!(drc_proxy_score(&[], &[], &[], 0.2, 10.0, false, false, false), 0.0);
        assert_eq!(
            drc_proxy_score(&[0.0, 0.0], &[1.0], &[1.0], 0.2, 10.0, false, false, false),
            0.0
        );
    }

    #[test]
    fn proxy_score_separated_components_are_near_zero() {
        let pos = grid(3, 100.0);
        let hw = vec![3.0; 3];
        let hh = vec![3.0; 3];
        let s = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);
        assert!(s < 1e-6, "well-separated components scored {s}");
    }

    #[test]
    fn proxy_score_overlapping_components_are_positive() {
        let pos = [0.0, 0.0, 2.0, 0.0];
        let hw = [5.0, 5.0];
        let hh = [5.0, 5.0];
        let s = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);
        assert!(s > 0.0, "overlapping components scored {s}");
    }

    #[test]
    fn proxy_score_is_monotone_in_separation() {
        let hw = [2.0, 2.0];
        let hh = [2.0, 2.0];
        let mut prev = f64::INFINITY;
        for k in 0..20 {
            let pos = [0.0, 0.0, 1.0 + k as f64 * 0.5, 0.0];
            let s = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);
            assert!(s <= prev, "score rose as components separated: {s} > {prev}");
            prev = s;
        }
    }

    #[test]
    fn proxy_score_is_translation_invariant() {
        let hw = [1.5, 2.5, 0.5];
        let hh = [0.5, 1.5, 2.5];
        let base = [0.0, 0.0, 3.0, 1.0, -2.0, 4.0];
        let shifted: Vec<f64> = base
            .iter()
            .enumerate()
            .map(|(k, v)| if k % 2 == 0 { v + 17.0 } else { v - 9.0 })
            .collect();
        let a = drc_proxy_score(&base, &hw, &hh, 0.2, 10.0, false, false, false);
        let b = drc_proxy_score(&shifted, &hw, &hh, 0.2, 10.0, false, false, false);
        assert_eq!(a.to_bits(), b.to_bits(), "integer translation must be exact");
    }

    #[test]
    fn proxy_score_dtype_flags_change_the_answer() {
        // Values chosen so the f32 rounding is observable. If this ever stops
        // holding, the dtype plumbing has gone dead and the differential's
        // dtype matrix is testing nothing.
        let pos: Vec<f64> = vec![0.1, 0.2, 3.3, 1.7, -2.9, 4.1]
            .into_iter()
            .map(|v: f64| v as f32 as f64)
            .collect();
        let hw: Vec<f64> = vec![1.1f64, 2.3, 0.7].into_iter().map(|v| v as f32 as f64).collect();
        let hh: Vec<f64> = vec![0.9f64, 1.3, 2.1].into_iter().map(|v| v as f32 as f64).collect();
        let wide = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);
        let narrow = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, true, true, true);
        assert_ne!(wide.to_bits(), narrow.to_bits());
    }

    #[test]
    fn proxy_score_coincident_components_hit_the_overlap_branch() {
        let n = 4;
        let pos = vec![0.0; 2 * n];
        let hw = vec![1.0; n];
        let hh = vec![1.0; n];
        let s = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);
        // Every pair has gap_x == gap_y == -2, distance -2, violation
        // smooth_relu(2.2, 10) ~= 2.2, squared ~= 4.84, over 6 pairs.
        let one = smooth_relu(2.2, 10.0);
        let expected = pairwise_sum(&[one * one; 6]);
        assert_eq!(s.to_bits(), expected.to_bits());
    }

    #[test]
    fn proxy_score_uses_pairwise_not_naive_reduction() {
        // 40 components => 780 pairs, well past PW_BLOCKSIZE, so the blocked
        // reduction and a naive one land on different bits.
        let n = 40;
        let pos: Vec<f64> = (0..n)
            .flat_map(|i| {
                let f = i as f64;
                [f * 0.37 % 7.0, f * 0.91 % 5.0]
            })
            .collect();
        let hw: Vec<f64> = (0..n).map(|i| 1.0 + (i as f64) * 0.013).collect();
        let hh: Vec<f64> = (0..n).map(|i| 1.0 + (i as f64) * 0.017).collect();
        let s = drc_proxy_score(&pos, &hw, &hh, 0.2, 10.0, false, false, false);

        let mut squared = Vec::new();
        for i in 0..n {
            for j in (i + 1)..n {
                let dx = (pos[2 * i] - pos[2 * j]).abs();
                let dy = (pos[2 * i + 1] - pos[2 * j + 1]).abs();
                let gx = dx - (hw[i] + hw[j]);
                let gy = dy - (hh[i] + hh[j]);
                let d = if gx < 0.0 && gy < 0.0 { np_minimum(gx, gy) } else { np_maximum(gx, gy) };
                let v = smooth_relu(0.2 - d, 10.0);
                squared.push(v * v);
            }
        }
        let naive = squared.iter().fold(0.0f64, |acc, &v| acc + v);
        assert_eq!(s.to_bits(), pairwise_sum(&squared).to_bits());
        assert_ne!(s.to_bits(), naive.to_bits(), "reduction order is not observable here");
    }
}

// =============================================================================
// Smooth approximations for non-differentiable operations
// =============================================================================
//
// This module provides differentiable approximations to min, max, relu, and
// related functions using LogSumExp and other techniques. These are essential
// for computing differentiable HPWL (Half-Perimeter Wire Length) and other
// placement metrics.
//
// The smoothness is controlled by an alpha parameter:
// - Higher alpha = sharper approximation (closer to true min/max)
// - Lower alpha = smoother gradients (better for early training)
//
// These parameters should be annealed during training: start low for exploration,
// increase for refinement.

// =============================================================================
// LogSumExp
// =============================================================================

/// Numerically stable LogSumExp: `log(sum(exp(x)))`.
///
/// Uses the standard trick of subtracting the maximum value before exponentiating
/// to avoid overflow. This is the only "scipy dependency" being inlined.
#[allow(dead_code)]
fn logsumexp(x: &[f64]) -> f64 {
    let max_val = x.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    if max_val.is_infinite() {
        return max_val;
    }
    let sum_exp: f64 = x.iter().map(|v| (v - max_val).exp()).sum();
    max_val + sum_exp.ln()
}

// =============================================================================
// Smooth Maximum Functions
// =============================================================================

/// Smooth approximation of `max(a, b)` using LogSumExp.
///
/// As `alpha → ∞`, `smooth_max → max(a, b)`.
///
/// The implementation is numerically stable via the standard LSE trick:
///     max(a, b) ≈ (1/alpha) * log(exp(alpha * a) + exp(alpha * b))
pub fn smooth_max(a: f64, b: f64, alpha: f64) -> f64 {
    let c = a.max(b);
    c + ((alpha * (a - c)).exp() + (alpha * (b - c)).exp()).ln() / alpha
}

/// Smooth approximation of max over a slice.
///
/// As `alpha → ∞`, `smooth_max_axis → max(arr)`.
///
/// This is always >= `max(arr)`, with equality as `alpha → ∞`.
///
/// When alpha is low, the result is influenced by all elements.
/// When alpha is high, the result is dominated by the maximum element.
pub fn smooth_max_axis(arr: &[f64], alpha: f64) -> f64 {
    let max_val = arr.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    if max_val.is_infinite() {
        return max_val;
    }
    let sum_exp: f64 = arr.iter().map(|v| (alpha * (v - max_val)).exp()).sum();
    max_val + sum_exp.ln() / alpha
}

/// Element-wise smooth max between two slices.
///
/// Panics if the slices have different lengths.
pub fn smooth_max_pair(a: &[f64], b: &[f64], alpha: f64) -> Vec<f64> {
    assert_eq!(
        a.len(),
        b.len(),
        "smooth_max_pair: slices must have equal length"
    );
    a.iter()
        .zip(b.iter())
        .map(|(&x, &y)| smooth_max(x, y, alpha))
        .collect()
}

// =============================================================================
// Smooth Minimum Functions
// =============================================================================

/// Smooth approximation of `min(a, b)`.
///
/// As `alpha → ∞`, `smooth_min → min(a, b)`.
///
/// Uses the identity: `min(a, b) = -max(-a, -b)`.
pub fn smooth_min(a: f64, b: f64, alpha: f64) -> f64 {
    -smooth_max(-a, -b, alpha)
}

/// Smooth approximation of min over a slice.
///
/// As `alpha → ∞`, `smooth_min_axis → min(arr)`.
///
/// This is always <= `min(arr)`, with equality as `alpha → ∞`.
pub fn smooth_min_axis(arr: &[f64], alpha: f64) -> f64 {
    let min_val = arr.iter().cloned().fold(f64::INFINITY, f64::min);
    if min_val.is_infinite() {
        return min_val;
    }
    let sum_exp: f64 = arr
        .iter()
        .map(|v| (-alpha * (v - min_val)).exp())
        .sum();
    min_val - sum_exp.ln() / alpha
}

/// Element-wise smooth min between two slices.
///
/// Panics if the slices have different lengths.
pub fn smooth_min_pair(a: &[f64], b: &[f64], alpha: f64) -> Vec<f64> {
    assert_eq!(
        a.len(),
        b.len(),
        "smooth_min_pair: slices must have equal length"
    );
    a.iter()
        .zip(b.iter())
        .map(|(&x, &y)| smooth_min(x, y, alpha))
        .collect()
}

// =============================================================================
// Smooth ReLU and Related Activation Functions
// =============================================================================

/// Smooth approximation of ReLU: `max(0, x)`.
///
/// Uses numerically stable softplus: `softplus(alpha * x) / alpha`.
///
/// As `alpha → ∞`, `smooth_relu → relu(x)`.
///
/// Gradient behavior:
/// - For `x << 0`: gradient ≈ 0
/// - For `x >> 0`: gradient ≈ 1
/// - For `x ≈ 0`: smooth sigmoid-like transition
pub fn smooth_relu(x: f64, alpha: f64) -> f64 {
    let ax = alpha * x;
    if ax > 0.0 {
        // log(1 + exp(ax)) = ax + log(1 + exp(-ax))
        // ln_1p(y) = ln(1 + y), so ln_1p(exp(-ax)) = ln(1 + exp(-ax))
        (ax + (-ax).exp().ln_1p()) / alpha
    } else {
        // log(1 + exp(ax)) with ax <= 0 → exp(ax) is small
        (ax).exp().ln_1p() / alpha
    }
}

/// Smooth quadratic penalty for constraint violations: `smooth_relu(x - margin, alpha)^2`.
///
/// Penalizes positive violations beyond the margin while ignoring values below.
/// The squaring provides quadratic penalty growth.
///
/// Args:
///     x: Input value (positive values beyond margin are violations)
///     margin: Threshold below which no penalty is applied
///     alpha: Smoothing parameter (higher = sharper transition at margin)
pub fn smooth_relu_penalty(x: f64, margin: f64, alpha: f64) -> f64 {
    smooth_relu(x - margin, alpha).powi(2)
}

/// Smooth approximation of leaky ReLU.
///
/// Standard leaky ReLU: `x` for `x > 0`, `negative_slope * x` for `x < 0`.
/// This smooth version has a differentiable transition at 0.
///
/// Args:
///     x: Input value
///     alpha: Smoothing parameter for the transition at 0
///     negative_slope: Slope for x < 0 (typical default: 0.01)
pub fn smooth_leaky_relu(x: f64, alpha: f64, negative_slope: f64) -> f64 {
    smooth_relu(x, alpha) - negative_slope * smooth_relu(-x, alpha)
}

// =============================================================================
// Smooth Absolute Value and Clipping
// =============================================================================

/// Smooth approximation of `|x|`.
///
/// Uses `sqrt(x^2 + 1/alpha^2)` which is differentiable at 0.
/// As `alpha → ∞`, `smooth_abs → |x|`.
///
/// The epsilon term `1/alpha^2` prevents the gradient from diverging at x = 0.
pub fn smooth_abs(x: f64, alpha: f64) -> f64 {
    let epsilon = 1.0 / (alpha * alpha);
    (x * x + epsilon).sqrt()
}

/// Smooth approximation of `clip(x, min_val, max_val)`.
///
/// Chains smooth max and min:
///     `clip(x) = smooth_min(smooth_max(x, min_val, alpha), max_val, alpha)`
pub fn smooth_clip(x: f64, min_val: f64, max_val: f64, alpha: f64) -> f64 {
    let clipped_low = smooth_max(x, min_val, alpha);
    smooth_min(clipped_low, max_val, alpha)
}

/// Smooth approximation of step function (sigmoid).
///
/// Returns ≈1 for `x > 0`, ≈0 for `x < 0`, with a smooth differentiable
/// transition at 0. Output values are in `(0, 1)`.
pub fn smooth_step(x: f64, alpha: f64) -> f64 {
    1.0 / (1.0 + (-alpha * x).exp())
}

// =============================================================================
// HPWL-Specific Functions
// =============================================================================

/// Compute smooth Half-Perimeter Wire Length for a set of points.
///
/// HPWL = (max_x - min_x) + (max_y - min_y)
///
/// This is the standard metric for estimating wirelength in placement.
/// Each point is `(x, y)`. Returns 0 for an empty point list.
pub fn hpwl_smooth(points: &[(f64, f64)], alpha: f64) -> f64 {
    if points.is_empty() {
        return 0.0;
    }
    let (xs, ys): (Vec<f64>, Vec<f64>) = points.iter().cloned().unzip();
    let x_max = smooth_max_axis(&xs, alpha);
    let x_min = smooth_min_axis(&xs, alpha);
    let y_max = smooth_max_axis(&ys, alpha);
    let y_min = smooth_min_axis(&ys, alpha);
    (x_max - x_min) + (y_max - y_min)
}

/// Compute temperature-weighted average using softmax-normalised weights.
///
/// As `alpha → 0`, this approaches a hard selection of the highest-weighted value.
/// As `alpha → ∞`, this approaches uniform averaging.
///
/// Useful for differentiable selection among discrete options.
///
/// Panics if the slices have different lengths.
pub fn weighted_average_smooth(values: &[f64], weights: &[f64], alpha: f64) -> f64 {
    assert_eq!(
        values.len(),
        weights.len(),
        "weighted_average_smooth: slices must have equal length"
    );
    if values.is_empty() {
        return f64::NAN;
    }
    let max_weight = weights.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let exp_weights: Vec<f64> = weights
        .iter()
        .map(|w| ((w - max_weight) / alpha).exp())
        .collect();
    let sum_exp: f64 = exp_weights.iter().sum();
    values
        .iter()
        .zip(exp_weights.iter())
        .map(|(v, w)| v * w / sum_exp)
        .sum()
}

// =============================================================================
// Annealing Schedules
// =============================================================================

/// Compute an exponential alpha schedule over `epochs` steps.
///
/// Starts at `start_alpha` (smooth) and exponentially increases toward
/// `end_alpha` (sharp). Each element corresponds to one epoch.
///
/// The schedule is:
///     alpha(epoch) = start_alpha * (end_alpha / start_alpha) ^ (epoch / (epochs - 1))
pub fn get_alpha_schedule(start_alpha: f64, end_alpha: f64, epochs: usize) -> Vec<f64> {
    let denom = (epochs.saturating_sub(1)).max(1) as f64;
    (0..epochs)
        .map(|epoch| {
            let progress = epoch as f64 / denom;
            start_alpha * (end_alpha / start_alpha).powf(progress)
        })
        .collect()
}

/// Compute an exponential beta schedule over `epochs` steps.
///
/// Same formula as `get_alpha_schedule`, named separately for use when a
/// distinct beta schedule is desired (e.g., for ReLU smoothing vs min/max
/// smoothing).
pub fn get_beta_schedule(start_beta: f64, end_beta: f64, epochs: usize) -> Vec<f64> {
    get_alpha_schedule(start_beta, end_beta, epochs)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f64 = 1e-9;

    // -----------------------------------------------------------------
    // logsumexp
    // -----------------------------------------------------------------
    #[test]
    fn test_logsumexp_basic() {
        // LSE([0, 1, 2]) = log(exp(0) + exp(1) + exp(2))
        let result = logsumexp(&[0.0, 1.0, 2.0]);
        let expected = (1.0f64 + 1.0f64.exp() + 2.0f64.exp()).ln();
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    #[test]
    fn test_logsumexp_single() {
        assert!((logsumexp(&[5.0]) - 5.0).abs() < EPS);
    }

    #[test]
    fn test_logsumexp_empty() {
        let result = logsumexp(&[]);
        assert!(result.is_infinite() && result.is_sign_negative());
    }

    #[test]
    fn test_logsumexp_all_equal() {
        // LSE([3, 3, 3]) = log(3 * exp(3)) = 3 + ln(3)
        let result = logsumexp(&[3.0, 3.0, 3.0]);
        let expected = 3.0 + 3.0f64.ln();
        assert!((result - expected).abs() < EPS);
    }

    #[test]
    fn test_logsumexp_large_values() {
        // Verify numerical stability with large inputs
        let result = logsumexp(&[1000.0, 1001.0, 1002.0]);
        let expected = 1002.0 + ((-2.0f64).exp() + (-1.0f64).exp() + 1.0f64).ln();
        assert!((result - expected).abs() < 1e-9, "expected {expected}, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_max
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_max_slightly_above_true_max() {
        let result = smooth_max(5.0, 3.0, 10.0);
        assert!(result > 5.0, "should be slightly > true max (5.0), got {result}");
        assert!((result - 5.0).abs() < 0.01, "expected near 5.0, got {result}");
    }

    #[test]
    fn test_smooth_max_symmetric() {
        let ab = smooth_max(5.0, 3.0, 10.0);
        let ba = smooth_max(3.0, 5.0, 10.0);
        assert!((ab - ba).abs() < EPS, "smooth_max should be symmetric");
    }

    #[test]
    fn test_smooth_max_convergence() {
        for alpha in [1.0, 10.0, 100.0, 1000.0] {
            let result = smooth_max(7.0, 2.0, alpha);
            let diff = result - 7.0;
            assert!(diff >= 0.0, "smooth_max should always be >= true max");
            assert!(
                diff <= 10.0 / alpha,
                "overestimate {} should diminish with alpha={}",
                diff,
                alpha
            );
        }
    }

    #[test]
    fn test_smooth_max_high_alpha() {
        let result = smooth_max(10.0, 1.0, 1e6);
        assert!((result - 10.0).abs() < 1e-3, "expected ~10.0, got {result}");
    }

    #[test]
    fn test_smooth_max_equal_values() {
        // With equal inputs, the overestimate is ln(2) / alpha.
        let result = smooth_max(4.0, 4.0, 1000.0);
        assert!((result - 4.0).abs() < 1e-3, "expected ~4.0, got {result}");
    }

    #[test]
    fn test_smooth_max_negative_values() {
        let result = smooth_max(-5.0, -1.0, 1.0);
        assert!(result > -1.0);
        assert!((result - (-1.0)).abs() < 0.1);
    }

    // -----------------------------------------------------------------
    // smooth_max_axis
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_max_axis_basic() {
        let result = smooth_max_axis(&[1.0, 5.0, 3.0, 2.0], 10.0);
        assert!(result > 5.0, "should be > true max (5.0)");
        assert!((result - 5.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_max_axis_single() {
        assert!((smooth_max_axis(&[42.0], 10.0) - 42.0).abs() < EPS);
    }

    #[test]
    fn test_smooth_max_axis_empty() {
        let result = smooth_max_axis(&[], 10.0);
        assert!(result.is_infinite() && result.is_sign_negative());
    }

    #[test]
    fn test_smooth_max_axis_negative() {
        let result = smooth_max_axis(&[-10.0, -3.0, -7.0], 1.0);
        assert!(result > -3.0, "expected > -3.0, got {result}");
        assert!((result - (-3.0)).abs() < 0.1);
    }

    #[test]
    fn test_smooth_max_axis_high_alpha() {
        let result = smooth_max_axis(&[0.0, 10.0, 5.0], 1e6);
        assert!((result - 10.0).abs() < 1e-3);
    }

    // -----------------------------------------------------------------
    // smooth_max_pair
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_max_pair_basic() {
        let a = vec![1.0, 5.0, 3.0];
        let b = vec![4.0, 2.0, 6.0];
        let result = smooth_max_pair(&a, &b, 10.0);
        assert_eq!(result.len(), 3);
        assert!((result[0] - 4.0).abs() < 0.01);
        assert!((result[1] - 5.0).abs() < 0.01);
        assert!((result[2] - 6.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_max_pair_empty() {
        assert!(smooth_max_pair(&[], &[], 10.0).is_empty());
    }

    #[test]
    #[should_panic(expected = "must have equal length")]
    fn test_smooth_max_pair_mismatched_lengths() {
        smooth_max_pair(&[1.0, 2.0], &[3.0], 10.0);
    }

    // -----------------------------------------------------------------
    // smooth_min
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_min_slightly_below_true_min() {
        let result = smooth_min(3.0, 5.0, 10.0);
        assert!(result < 3.0, "should be slightly < true min (3.0), got {result}");
        assert!((result - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_min_symmetric() {
        let ab = smooth_min(3.0, 5.0, 10.0);
        let ba = smooth_min(5.0, 3.0, 10.0);
        assert!((ab - ba).abs() < EPS);
    }

    #[test]
    fn test_smooth_min_via_max_identity() {
        let a = 4.0;
        let b = 7.0;
        let direct = smooth_min(a, b, 10.0);
        let via_max = -smooth_max(-a, -b, 10.0);
        assert!((direct - via_max).abs() < EPS, "min = -max(-a, -b) identity failed");
    }

    // -----------------------------------------------------------------
    // smooth_min_axis
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_min_axis_basic() {
        let result = smooth_min_axis(&[3.0, 1.0, 5.0, 2.0], 10.0);
        assert!(result < 1.0, "should be < true min (1.0)");
        assert!((result - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_min_axis_single() {
        assert!((smooth_min_axis(&[7.0], 10.0) - 7.0).abs() < EPS);
    }

    #[test]
    fn test_smooth_min_axis_empty() {
        let result = smooth_min_axis(&[], 10.0);
        assert!(result.is_infinite() && result.is_sign_positive());
    }

    #[test]
    fn test_smooth_min_axis_via_max_identity() {
        let arr = [3.0, 1.0, 5.0, 2.0];
        let direct = smooth_min_axis(&arr, 10.0);
        let neg: Vec<f64> = arr.iter().map(|v| -v).collect();
        let via_max = -smooth_max_axis(&neg, 10.0);
        assert!((direct - via_max).abs() < EPS, "min(x) = -max(-x) identity failed");
    }

    // -----------------------------------------------------------------
    // smooth_min_pair
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_min_pair_basic() {
        let a = vec![1.0, 5.0, 3.0];
        let b = vec![4.0, 2.0, 6.0];
        let result = smooth_min_pair(&a, &b, 10.0);
        assert_eq!(result.len(), 3);
        assert!((result[0] - 1.0).abs() < 0.01);
        assert!((result[1] - 2.0).abs() < 0.01);
        assert!((result[2] - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_min_pair_empty() {
        assert!(smooth_min_pair(&[], &[], 10.0).is_empty());
    }

    #[test]
    fn test_min_pair_via_max_pair_identity() {
        let a = [1.0, 5.0, 3.0];
        let b = [4.0, 2.0, 6.0];
        let direct = smooth_min_pair(&a, &b, 10.0);
        let neg_a: Vec<f64> = a.iter().map(|v| -v).collect();
        let neg_b: Vec<f64> = b.iter().map(|v| -v).collect();
        let via_max: Vec<f64> = smooth_max_pair(&neg_a, &neg_b, 10.0)
            .iter()
            .map(|v| -v)
            .collect();
        for (d, v) in direct.iter().zip(via_max.iter()) {
            assert!((d - v).abs() < EPS, "min pair identity failed");
        }
    }

    #[test]
    #[should_panic(expected = "must have equal length")]
    fn test_smooth_min_pair_mismatched_lengths() {
        smooth_min_pair(&[1.0], &[2.0, 3.0], 10.0);
    }

    // -----------------------------------------------------------------
    // smooth_relu
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_relu_positive() {
        let result = smooth_relu(3.0, 10.0);
        assert!(result > 2.9 && result < 3.1, "expected ~3.0, got {result}");
    }

    #[test]
    fn test_smooth_relu_negative() {
        let result = smooth_relu(-3.0, 10.0);
        assert!(result < 0.001, "expected ~0, got {result}");
    }

    #[test]
    fn test_smooth_relu_zero() {
        let result = smooth_relu(0.0, 10.0);
        // softplus(0) / 10 = log(2) / 10 ≈ 0.0693
        let expected = core::f64::consts::LN_2 / 10.0;
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    #[test]
    fn test_smooth_relu_high_alpha() {
        let neg = smooth_relu(-2.0, 1e6);
        assert!(neg.abs() < 1e-6, "negative ~0 with high alpha, got {neg}");
        let pos = smooth_relu(5.0, 1e6);
        assert!((pos - 5.0).abs() < 1e-6, "positive ~x with high alpha, got {pos}");
    }

    // -----------------------------------------------------------------
    // smooth_relu_penalty
    // -----------------------------------------------------------------
    #[test]
    fn test_relu_penalty_below_margin() {
        let result = smooth_relu_penalty(2.0, 10.0, 10.0);
        assert!(result.abs() < 0.01, "expected ~0 below margin, got {result}");
    }

    #[test]
    fn test_relu_penalty_above_margin() {
        let result = smooth_relu_penalty(12.0, 10.0, 10.0);
        // smooth_relu(2, 10) ≈ 2, penalty ≈ 4
        assert!((result - 4.0).abs() < 0.1, "expected ~4, got {result}");
    }

    #[test]
    fn test_relu_penalty_at_margin() {
        let result = smooth_relu_penalty(10.0, 10.0, 10.0);
        // smooth_relu(0, 10) = ln(2)/10, penalty = (ln(2)/10)^2
        let expected = (core::f64::consts::LN_2 / 10.0).powi(2);
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_leaky_relu
    // -----------------------------------------------------------------
    #[test]
    fn test_leaky_relu_positive() {
        let result = smooth_leaky_relu(3.0, 10.0, 0.01);
        assert!((result - 3.0).abs() < 0.01, "expected ~3.0, got {result}");
    }

    #[test]
    fn test_leaky_relu_negative() {
        let result = smooth_leaky_relu(-3.0, 10.0, 0.01);
        // ≈ 0.01 * (-3) = -0.03
        assert!((result - (-0.03)).abs() < 0.001, "expected ~-0.03, got {result}");
    }

    #[test]
    fn test_leaky_relu_zero_negative_slope() {
        // With negative_slope = 0, acts like standard relu
        let result = smooth_leaky_relu(-2.0, 10.0, 0.0);
        assert!(result.abs() < 0.001, "expected ~0, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_abs
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_abs_positive() {
        assert!((smooth_abs(5.0, 10.0) - 5.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_abs_negative() {
        assert!((smooth_abs(-5.0, 10.0) - 5.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_abs_symmetry() {
        assert!((smooth_abs(3.0, 10.0) - smooth_abs(-3.0, 10.0)).abs() < EPS);
    }

    #[test]
    fn test_smooth_abs_at_zero() {
        let result = smooth_abs(0.0, 10.0);
        // sqrt(0 + 1/100) = sqrt(0.01) = 0.1
        assert!((result - 0.1).abs() < 1e-9);
    }

    #[test]
    fn test_smooth_abs_high_alpha() {
        let result = smooth_abs(-3.0, 1e6);
        assert!((result - 3.0).abs() < 0.001);
    }

    // -----------------------------------------------------------------
    // smooth_clip
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_clip_within_range() {
        let result = smooth_clip(5.0, 0.0, 10.0, 10.0);
        assert!((result - 5.0).abs() < 0.01);
    }

    #[test]
    fn test_smooth_clip_below_min() {
        let result = smooth_clip(-5.0, 0.0, 10.0, 10.0);
        assert!((result - 0.0).abs() < 0.01, "expected ~0, got {result}");
    }

    #[test]
    fn test_smooth_clip_above_max() {
        let result = smooth_clip(15.0, 0.0, 10.0, 10.0);
        assert!((result - 10.0).abs() < 0.01, "expected ~10, got {result}");
    }

    #[test]
    fn test_smooth_clip_high_alpha() {
        let below = smooth_clip(-5.0, 0.0, 10.0, 1e6);
        assert!((below - 0.0).abs() < 1e-6);
        let above = smooth_clip(15.0, 0.0, 10.0, 1e6);
        assert!((above - 10.0).abs() < 1e-6);
    }

    #[test]
    fn test_smooth_clip_min_equals_max() {
        // When min == max, the result should converge to that value with high alpha.
        let result = smooth_clip(3.0, 5.0, 5.0, 1000.0);
        assert!((result - 5.0).abs() < 0.01, "expected ~5.0, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_step
    // -----------------------------------------------------------------
    #[test]
    fn test_smooth_step_positive() {
        let result = smooth_step(2.0, 10.0);
        assert!(result > 0.99, "expected ~1, got {result}");
    }

    #[test]
    fn test_smooth_step_negative() {
        let result = smooth_step(-2.0, 10.0);
        assert!(result < 0.01, "expected ~0, got {result}");
    }

    #[test]
    fn test_smooth_step_zero() {
        let result = smooth_step(0.0, 10.0);
        assert!((result - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_smooth_step_high_alpha() {
        let pos = smooth_step(1.0, 1e6);
        assert!((pos - 1.0).abs() < 1e-6);
        let neg = smooth_step(-1.0, 1e6);
        assert!(neg.abs() < 1e-6);
    }

    #[test]
    fn test_smooth_step_output_in_01() {
        for x in -10..=10 {
            let s = smooth_step(x as f64, 5.0);
            assert!((0.0..=1.0).contains(&s), "step output outside [0,1] for x={x}: {s}");
        }
    }

    // -----------------------------------------------------------------
    // hpwl_smooth
    // -----------------------------------------------------------------
    #[test]
    fn test_hpwl_smooth_basic() {
        let points = [(0.0, 0.0), (10.0, 5.0), (5.0, 10.0)];
        let result = hpwl_smooth(&points, 1.0);
        // True HPWL = (10 - 0) + (10 - 0) = 20
        assert!(result > 20.0, "expected > 20, got {result}");
        assert!((result - 20.0).abs() < 0.1, "expected ~20, got {result}");
    }

    #[test]
    fn test_hpwl_smooth_single_point() {
        let result = hpwl_smooth(&[(5.0, 7.0)], 10.0);
        assert!((result - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_hpwl_smooth_two_points() {
        let points = [(0.0, 0.0), (3.0, 4.0)];
        let result = hpwl_smooth(&points, 10.0);
        // True HPWL = (3 - 0) + (4 - 0) = 7
        assert!((result - 7.0).abs() < 0.1, "expected ~7, got {result}");
    }

    #[test]
    fn test_hpwl_smooth_empty() {
        assert!((hpwl_smooth(&[], 10.0) - 0.0).abs() < EPS);
    }

    #[test]
    fn test_hpwl_smooth_high_alpha() {
        let points = [(0.0, 0.0), (10.0, 10.0)];
        let result = hpwl_smooth(&points, 1e6);
        assert!((result - 20.0).abs() < 1e-3, "expected ~20, got {result}");
    }

    // -----------------------------------------------------------------
    // weighted_average_smooth
    // -----------------------------------------------------------------
    #[test]
    fn test_weighted_average_uniform() {
        let result = weighted_average_smooth(&[1.0, 2.0, 3.0], &[1.0, 1.0, 1.0], 1.0);
        assert!((result - 2.0).abs() < 1e-9);
    }

    #[test]
    fn test_weighted_average_dominant_weight() {
        let result = weighted_average_smooth(&[1.0, 2.0, 3.0], &[0.001, 0.001, 1000.0], 1.0);
        assert!((result - 3.0).abs() < 0.01, "dominant weight should select 3, got {result}");
    }

    #[test]
    fn test_weighted_average_empty() {
        assert!(weighted_average_smooth(&[], &[], 1.0).is_nan());
    }

    #[test]
    fn test_weighted_average_temperature_effect() {
        let values = [10.0, 20.0, 30.0];
        let weights = [1.0, 2.0, 3.0];
        let low_t = weighted_average_smooth(&values, &weights, 0.01);
        let high_t = weighted_average_smooth(&values, &weights, 100.0);
        // Low temperature → sharper → closer to argmax value (30)
        // High temperature → smoother → closer to uniform average (20)
        assert!(
            (low_t - 30.0).abs() < (high_t - 20.0).abs(),
            "low temp should be sharper than high temp"
        );
    }

    #[test]
    fn test_weighted_average_high_temperature_uniform() {
        let result = weighted_average_smooth(&[10.0, 100.0], &[1.0, 100.0], 1e6);
        // Very high alpha → softmax ≈ uniform → average = 55.0
        assert!((result - 55.0).abs() < 0.1, "expected ~55, got {result}");
    }

    #[test]
    #[should_panic(expected = "must have equal length")]
    fn test_weighted_average_mismatched_lengths() {
        weighted_average_smooth(&[1.0, 2.0], &[1.0], 1.0);
    }

    // -----------------------------------------------------------------
    // get_alpha_schedule
    // -----------------------------------------------------------------
    #[test]
    fn test_alpha_schedule_endpoints() {
        let schedule = get_alpha_schedule(1.0, 50.0, 10);
        assert_eq!(schedule.len(), 10);
        assert!((schedule[0] - 1.0).abs() < EPS, "first: expected 1.0, got {}", schedule[0]);
        assert!(
            (schedule[9] - 50.0).abs() < 1e-6,
            "last: expected 50.0, got {}",
            schedule[9]
        );
    }

    #[test]
    fn test_alpha_schedule_monotonic() {
        let schedule = get_alpha_schedule(1.0, 50.0, 20);
        for w in schedule.windows(2) {
            assert!(w[1] >= w[0], "schedule not monotonic: {} > {}", w[0], w[1]);
        }
    }

    #[test]
    fn test_alpha_schedule_single_epoch() {
        let schedule = get_alpha_schedule(5.0, 10.0, 1);
        assert_eq!(schedule.len(), 1);
        assert!((schedule[0] - 5.0).abs() < EPS);
    }

    #[test]
    fn test_alpha_schedule_zero_epochs() {
        assert!(get_alpha_schedule(1.0, 50.0, 0).is_empty());
    }

    #[test]
    fn test_alpha_schedule_two_epochs() {
        let schedule = get_alpha_schedule(1.0, 10.0, 2);
        assert_eq!(schedule.len(), 2);
        assert!((schedule[0] - 1.0).abs() < EPS);
        assert!((schedule[1] - 10.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // get_beta_schedule
    // -----------------------------------------------------------------
    #[test]
    fn test_beta_schedule_matches_alpha() {
        let a = get_alpha_schedule(2.0, 100.0, 15);
        let b = get_beta_schedule(2.0, 100.0, 15);
        assert_eq!(a, b);
    }

    // -----------------------------------------------------------------
    // Cross-function consistency
    // -----------------------------------------------------------------
    #[test]
    fn test_max_min_bracket() {
        let a = 3.0;
        let b = 7.0;
        let smax = smooth_max(a, b, 10.0);
        let smin = smooth_min(a, b, 10.0);
        assert!(smax >= smin, "max >= min");
        assert!(smax >= b - 0.1, "max near true max");
        assert!(smin <= a + 0.1, "min near true min");
    }

    #[test]
    fn test_pair_max_ge_min() {
        let a = [1.0, 4.0, 2.0];
        let b = [3.0, 2.0, 5.0];
        let max_pair = smooth_max_pair(&a, &b, 10.0);
        let min_pair = smooth_min_pair(&a, &b, 10.0);
        for (&mx, &mn) in max_pair.iter().zip(min_pair.iter()) {
            assert!(mx >= mn, "pair max >= pair min failed: {mx} < {mn}");
        }
    }

    #[test]
    fn test_smooth_max_axis_via_logsumexp() {
        let arr = [1.0, 3.0, 2.0];
        let alpha = 5.0;
        let result = smooth_max_axis(&arr, alpha);
        let scaled: Vec<f64> = arr.iter().map(|v| v * alpha).collect();
        let expected = logsumexp(&scaled) / alpha;
        assert!(
            (result - expected).abs() < EPS,
            "smooth_max_axis should match logsumexp/alpha: {result} vs {expected}"
        );
    }
}

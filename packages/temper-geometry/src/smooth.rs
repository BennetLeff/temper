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
    smooth_max_axis_vals(arr, alpha)
}

/// Two-pass smooth max over a slice: first pass finds max, second pass
/// computes the LogSumExp.
fn smooth_max_axis_vals(arr: &[f64], alpha: f64) -> f64 {
    let max_val = arr.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    if max_val.is_infinite() {
        return max_val;
    }
    let sum_exp: f64 = arr.iter().map(|&v| (alpha * (v - max_val)).exp()).sum();
    max_val + sum_exp.ln() / alpha
}

/// Element-wise smooth max between two slices.
///
/// # Panics
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
    smooth_min_axis_vals(arr, alpha)
}

/// Two-pass smooth min over a slice: first pass finds min, second pass
/// computes the LogSumExp.
fn smooth_min_axis_vals(arr: &[f64], alpha: f64) -> f64 {
    let min_val = arr.iter().copied().fold(f64::INFINITY, f64::min);
    if min_val.is_infinite() {
        return min_val;
    }
    let sum_exp: f64 = arr.iter().map(|&v| (-alpha * (v - min_val)).exp()).sum();
    min_val - sum_exp.ln() / alpha
}

/// Element-wise smooth min between two slices.
///
/// # Panics
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
    // Pass 1: exact extrema in one traversal. Left-to-right fold order is
    // identical to the per-axis `smooth_max_axis_vals` /
    // `smooth_min_axis_vals` reductions (`.fold(f64::NEG_INFINITY,
    // f64::max)` etc.), so every intermediate value — and therefore the
    // result — is bit-identical.
    let mut x_max = f64::NEG_INFINITY;
    let mut x_min = f64::INFINITY;
    let mut y_max = f64::NEG_INFINITY;
    let mut y_min = f64::INFINITY;
    for &(x, y) in points {
        x_max = x_max.max(x);
        x_min = x_min.min(x);
        y_max = y_max.max(y);
        y_min = y_min.min(y);
    }
    // Pass 2: the four exp-sums, same element order as the per-axis
    // smooth aggregates use.
    let sx: f64 = points
        .iter()
        .map(|&(x, _)| (alpha * (x - x_max)).exp())
        .sum();
    let smx: f64 = points
        .iter()
        .map(|&(x, _)| (-alpha * (x - x_min)).exp())
        .sum();
    let sy: f64 = points
        .iter()
        .map(|&(_, y)| (alpha * (y - y_max)).exp())
        .sum();
    let smy: f64 = points
        .iter()
        .map(|&(_, y)| (-alpha * (y - y_min)).exp())
        .sum();
    (x_max + sx.ln() / alpha - (x_min - smx.ln() / alpha))
        + (y_max + sy.ln() / alpha - (y_min - smy.ln() / alpha))
}

/// Compute temperature-weighted average using softmax-normalised weights.
///
/// As `alpha → 0`, this approaches a hard selection of the highest-weighted value.
/// As `alpha → ∞`, this approaches uniform averaging.
///
/// Useful for differentiable selection among discrete options.
///
/// # Panics
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
    let max_weight = weights.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let sum_exp: f64 = weights
        .iter()
        .map(|w| ((w - max_weight) / alpha).exp())
        .sum();
    values
        .iter()
        .zip(weights.iter())
        .map(|(v, w)| v * ((w - max_weight) / alpha).exp() / sum_exp)
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    const EPS: f64 = 1e-9;

    // -----------------------------------------------------------------
    // logsumexp
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_logsumexp_basic() {
        // LSE([0, 1, 2]) = log(exp(0) + exp(1) + exp(2))
        let result = logsumexp(&[0.0, 1.0, 2.0]);
        let expected = (1.0f64 + 1.0f64.exp() + 2.0f64.exp()).ln();
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_logsumexp_single() {
        assert!((logsumexp(&[5.0]) - 5.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_logsumexp_empty() {
        let result = logsumexp(&[]);
        assert!(result.is_infinite() && result.is_sign_negative());
    }

    #[cfg_attr(test, test)]
    fn test_logsumexp_all_equal() {
        // LSE([3, 3, 3]) = log(3 * exp(3)) = 3 + ln(3)
        let result = logsumexp(&[3.0, 3.0, 3.0]);
        let expected = 3.0 + 3.0f64.ln();
        assert!((result - expected).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_logsumexp_large_values() {
        // Verify numerical stability with large inputs
        let result = logsumexp(&[1000.0, 1001.0, 1002.0]);
        let expected = 1002.0 + ((-2.0f64).exp() + (-1.0f64).exp() + 1.0f64).ln();
        assert!((result - expected).abs() < 1e-9, "expected {expected}, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_max
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_max_slightly_above_true_max() {
        let result = smooth_max(5.0, 3.0, 10.0);
        assert!(result > 5.0, "should be slightly > true max (5.0), got {result}");
        assert!((result - 5.0).abs() < 0.01, "expected near 5.0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_symmetric() {
        let ab = smooth_max(5.0, 3.0, 10.0);
        let ba = smooth_max(3.0, 5.0, 10.0);
        assert!((ab - ba).abs() < EPS, "smooth_max should be symmetric");
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn test_smooth_max_high_alpha() {
        let result = smooth_max(10.0, 1.0, 1e6);
        assert!((result - 10.0).abs() < 1e-3, "expected ~10.0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_equal_values() {
        // With equal inputs, the overestimate is ln(2) / alpha.
        let result = smooth_max(4.0, 4.0, 1000.0);
        assert!((result - 4.0).abs() < 1e-3, "expected ~4.0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_negative_values() {
        let result = smooth_max(-5.0, -1.0, 1.0);
        assert!(result > -1.0);
        assert!((result - (-1.0)).abs() < 0.1);
    }

    // -----------------------------------------------------------------
    // smooth_max_axis
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_max_axis_basic() {
        let result = smooth_max_axis(&[1.0, 5.0, 3.0, 2.0], 10.0);
        assert!(result > 5.0, "should be > true max (5.0)");
        assert!((result - 5.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_axis_single() {
        assert!((smooth_max_axis(&[42.0], 10.0) - 42.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_axis_empty() {
        let result = smooth_max_axis(&[], 10.0);
        assert!(result.is_infinite() && result.is_sign_negative());
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_axis_negative() {
        let result = smooth_max_axis(&[-10.0, -3.0, -7.0], 1.0);
        assert!(result > -3.0, "expected > -3.0, got {result}");
        assert!((result - (-3.0)).abs() < 0.1);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_axis_high_alpha() {
        let result = smooth_max_axis(&[0.0, 10.0, 5.0], 1e6);
        assert!((result - 10.0).abs() < 1e-3);
    }

    // -----------------------------------------------------------------
    // smooth_max_pair
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_max_pair_basic() {
        let a = vec![1.0, 5.0, 3.0];
        let b = vec![4.0, 2.0, 6.0];
        let result = smooth_max_pair(&a, &b, 10.0);
        assert_eq!(result.len(), 3);
        assert!((result[0] - 4.0).abs() < 0.01);
        assert!((result[1] - 5.0).abs() < 0.01);
        assert!((result[2] - 6.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_max_pair_empty() {
        assert!(smooth_max_pair(&[], &[], 10.0).is_empty());
    }

    #[cfg_attr(test, test)]
    #[should_panic(expected = "must have equal length")]
    fn test_smooth_max_pair_mismatched_lengths() {
        smooth_max_pair(&[1.0, 2.0], &[3.0], 10.0);
    }

    // -----------------------------------------------------------------
    // smooth_min
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_min_slightly_below_true_min() {
        let result = smooth_min(3.0, 5.0, 10.0);
        assert!(result < 3.0, "should be slightly < true min (3.0), got {result}");
        assert!((result - 3.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_min_symmetric() {
        let ab = smooth_min(3.0, 5.0, 10.0);
        let ba = smooth_min(5.0, 3.0, 10.0);
        assert!((ab - ba).abs() < EPS);
    }

    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_smooth_min_axis_basic() {
        let result = smooth_min_axis(&[3.0, 1.0, 5.0, 2.0], 10.0);
        assert!(result < 1.0, "should be < true min (1.0)");
        assert!((result - 1.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_min_axis_single() {
        assert!((smooth_min_axis(&[7.0], 10.0) - 7.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_min_axis_empty() {
        let result = smooth_min_axis(&[], 10.0);
        assert!(result.is_infinite() && result.is_sign_positive());
    }

    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_smooth_min_pair_basic() {
        let a = vec![1.0, 5.0, 3.0];
        let b = vec![4.0, 2.0, 6.0];
        let result = smooth_min_pair(&a, &b, 10.0);
        assert_eq!(result.len(), 3);
        assert!((result[0] - 1.0).abs() < 0.01);
        assert!((result[1] - 2.0).abs() < 0.01);
        assert!((result[2] - 3.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_min_pair_empty() {
        assert!(smooth_min_pair(&[], &[], 10.0).is_empty());
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    #[should_panic(expected = "must have equal length")]
    fn test_smooth_min_pair_mismatched_lengths() {
        smooth_min_pair(&[1.0], &[2.0, 3.0], 10.0);
    }

    // -----------------------------------------------------------------
    // smooth_relu
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_relu_positive() {
        let result = smooth_relu(3.0, 10.0);
        assert!(result > 2.9 && result < 3.1, "expected ~3.0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_relu_negative() {
        let result = smooth_relu(-3.0, 10.0);
        assert!(result < 0.001, "expected ~0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_relu_zero() {
        let result = smooth_relu(0.0, 10.0);
        // softplus(0) / 10 = log(2) / 10 ≈ 0.0693
        let expected = core::f64::consts::LN_2 / 10.0;
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_relu_high_alpha() {
        let neg = smooth_relu(-2.0, 1e6);
        assert!(neg.abs() < 1e-6, "negative ~0 with high alpha, got {neg}");
        let pos = smooth_relu(5.0, 1e6);
        assert!((pos - 5.0).abs() < 1e-6, "positive ~x with high alpha, got {pos}");
    }

    // -----------------------------------------------------------------
    // smooth_relu_penalty
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_relu_penalty_below_margin() {
        let result = smooth_relu_penalty(2.0, 10.0, 10.0);
        assert!(result.abs() < 0.01, "expected ~0 below margin, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_relu_penalty_above_margin() {
        let result = smooth_relu_penalty(12.0, 10.0, 10.0);
        // smooth_relu(2, 10) ≈ 2, penalty ≈ 4
        assert!((result - 4.0).abs() < 0.1, "expected ~4, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_relu_penalty_at_margin() {
        let result = smooth_relu_penalty(10.0, 10.0, 10.0);
        // smooth_relu(0, 10) = ln(2)/10, penalty = (ln(2)/10)^2
        let expected = (core::f64::consts::LN_2 / 10.0).powi(2);
        assert!((result - expected).abs() < 1e-8, "expected {expected}, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_leaky_relu
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_leaky_relu_positive() {
        let result = smooth_leaky_relu(3.0, 10.0, 0.01);
        assert!((result - 3.0).abs() < 0.01, "expected ~3.0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_leaky_relu_negative() {
        let result = smooth_leaky_relu(-3.0, 10.0, 0.01);
        // ≈ 0.01 * (-3) = -0.03
        assert!((result - (-0.03)).abs() < 0.001, "expected ~-0.03, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_leaky_relu_zero_negative_slope() {
        // With negative_slope = 0, acts like standard relu
        let result = smooth_leaky_relu(-2.0, 10.0, 0.0);
        assert!(result.abs() < 0.001, "expected ~0, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_abs
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_abs_positive() {
        assert!((smooth_abs(5.0, 10.0) - 5.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_abs_negative() {
        assert!((smooth_abs(-5.0, 10.0) - 5.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_abs_symmetry() {
        assert!((smooth_abs(3.0, 10.0) - smooth_abs(-3.0, 10.0)).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_abs_at_zero() {
        let result = smooth_abs(0.0, 10.0);
        // sqrt(0 + 1/100) = sqrt(0.01) = 0.1
        assert!((result - 0.1).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_abs_high_alpha() {
        let result = smooth_abs(-3.0, 1e6);
        assert!((result - 3.0).abs() < 0.001);
    }

    // -----------------------------------------------------------------
    // smooth_clip
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_clip_within_range() {
        let result = smooth_clip(5.0, 0.0, 10.0, 10.0);
        assert!((result - 5.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_clip_below_min() {
        let result = smooth_clip(-5.0, 0.0, 10.0, 10.0);
        assert!((result - 0.0).abs() < 0.01, "expected ~0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_clip_above_max() {
        let result = smooth_clip(15.0, 0.0, 10.0, 10.0);
        assert!((result - 10.0).abs() < 0.01, "expected ~10, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_clip_high_alpha() {
        let below = smooth_clip(-5.0, 0.0, 10.0, 1e6);
        assert!((below - 0.0).abs() < 1e-6);
        let above = smooth_clip(15.0, 0.0, 10.0, 1e6);
        assert!((above - 10.0).abs() < 1e-6);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_clip_min_equals_max() {
        // When min == max, the result should converge to that value with high alpha.
        let result = smooth_clip(3.0, 5.0, 5.0, 1000.0);
        assert!((result - 5.0).abs() < 0.01, "expected ~5.0, got {result}");
    }

    // -----------------------------------------------------------------
    // smooth_step
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_smooth_step_positive() {
        let result = smooth_step(2.0, 10.0);
        assert!(result > 0.99, "expected ~1, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_step_negative() {
        let result = smooth_step(-2.0, 10.0);
        assert!(result < 0.01, "expected ~0, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_smooth_step_zero() {
        let result = smooth_step(0.0, 10.0);
        assert!((result - 0.5).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_step_high_alpha() {
        let pos = smooth_step(1.0, 1e6);
        assert!((pos - 1.0).abs() < 1e-6);
        let neg = smooth_step(-1.0, 1e6);
        assert!(neg.abs() < 1e-6);
    }

    #[cfg_attr(test, test)]
    fn test_smooth_step_output_in_01() {
        for x in -10..=10 {
            let s = smooth_step(x as f64, 5.0);
            assert!((0.0..=1.0).contains(&s), "step output outside [0,1] for x={x}: {s}");
        }
    }

    // -----------------------------------------------------------------
    // hpwl_smooth
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_hpwl_smooth_basic() {
        let points = [(0.0, 0.0), (10.0, 5.0), (5.0, 10.0)];
        let result = hpwl_smooth(&points, 1.0);
        // True HPWL = (10 - 0) + (10 - 0) = 20
        assert!(result > 20.0, "expected > 20, got {result}");
        assert!((result - 20.0).abs() < 0.1, "expected ~20, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_hpwl_smooth_single_point() {
        let result = hpwl_smooth(&[(5.0, 7.0)], 10.0);
        assert!((result - 0.0).abs() < 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_hpwl_smooth_two_points() {
        let points = [(0.0, 0.0), (3.0, 4.0)];
        let result = hpwl_smooth(&points, 10.0);
        // True HPWL = (3 - 0) + (4 - 0) = 7
        assert!((result - 7.0).abs() < 0.1, "expected ~7, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_hpwl_smooth_empty() {
        assert!((hpwl_smooth(&[], 10.0) - 0.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_hpwl_smooth_high_alpha() {
        let points = [(0.0, 0.0), (10.0, 10.0)];
        let result = hpwl_smooth(&points, 1e6);
        assert!((result - 20.0).abs() < 1e-3, "expected ~20, got {result}");
    }

    // -----------------------------------------------------------------
    // weighted_average_smooth
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_weighted_average_uniform() {
        let result = weighted_average_smooth(&[1.0, 2.0, 3.0], &[1.0, 1.0, 1.0], 1.0);
        assert!((result - 2.0).abs() < 1e-9);
    }

    #[cfg_attr(test, test)]
    fn test_weighted_average_dominant_weight() {
        let result = weighted_average_smooth(&[1.0, 2.0, 3.0], &[0.001, 0.001, 1000.0], 1.0);
        assert!((result - 3.0).abs() < 0.01, "dominant weight should select 3, got {result}");
    }

    #[cfg_attr(test, test)]
    fn test_weighted_average_empty() {
        assert!(weighted_average_smooth(&[], &[], 1.0).is_nan());
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn test_weighted_average_high_temperature_uniform() {
        let result = weighted_average_smooth(&[10.0, 100.0], &[1.0, 100.0], 1e6);
        // Very high alpha → softmax ≈ uniform → average = 55.0
        assert!((result - 55.0).abs() < 0.1, "expected ~55, got {result}");
    }

    #[cfg_attr(test, test)]
    #[should_panic(expected = "must have equal length")]
    fn test_weighted_average_mismatched_lengths() {
        weighted_average_smooth(&[1.0, 2.0], &[1.0], 1.0);
    }

    // -----------------------------------------------------------------
    // get_alpha_schedule
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn test_alpha_schedule_monotonic() {
        let schedule = get_alpha_schedule(1.0, 50.0, 20);
        for w in schedule.windows(2) {
            assert!(w[1] >= w[0], "schedule not monotonic: {} > {}", w[0], w[1]);
        }
    }

    #[cfg_attr(test, test)]
    fn test_alpha_schedule_single_epoch() {
        let schedule = get_alpha_schedule(5.0, 10.0, 1);
        assert_eq!(schedule.len(), 1);
        assert!((schedule[0] - 5.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_alpha_schedule_zero_epochs() {
        assert!(get_alpha_schedule(1.0, 50.0, 0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn test_alpha_schedule_two_epochs() {
        let schedule = get_alpha_schedule(1.0, 10.0, 2);
        assert_eq!(schedule.len(), 2);
        assert!((schedule[0] - 1.0).abs() < EPS);
        assert!((schedule[1] - 10.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // get_beta_schedule
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_beta_schedule_matches_alpha() {
        let a = get_alpha_schedule(2.0, 100.0, 15);
        let b = get_beta_schedule(2.0, 100.0, 15);
        assert_eq!(a, b);
    }

    // -----------------------------------------------------------------
    // Cross-function consistency
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_max_min_bracket() {
        let a = 3.0;
        let b = 7.0;
        let smax = smooth_max(a, b, 10.0);
        let smin = smooth_min(a, b, 10.0);
        assert!(smax >= smin, "max >= min");
        assert!(smax >= b - 0.1, "max near true max");
        assert!(smin <= a + 0.1, "min near true min");
    }

    #[cfg_attr(test, test)]
    fn test_pair_max_ge_min() {
        let a = [1.0, 4.0, 2.0];
        let b = [3.0, 2.0, 5.0];
        let max_pair = smooth_max_pair(&a, &b, 10.0);
        let min_pair = smooth_min_pair(&a, &b, 10.0);
        for (&mx, &mn) in max_pair.iter().zip(min_pair.iter()) {
            assert!(mx >= mn, "pair max >= pair min failed: {mx} < {mn}");
        }
    }

    #[cfg_attr(test, test)]
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("smooth::tests::test_logsumexp_basic", test_logsumexp_basic),
        ("smooth::tests::test_logsumexp_single", test_logsumexp_single),
        ("smooth::tests::test_logsumexp_empty", test_logsumexp_empty),
        ("smooth::tests::test_logsumexp_all_equal", test_logsumexp_all_equal),
        ("smooth::tests::test_logsumexp_large_values", test_logsumexp_large_values),
        ("smooth::tests::test_smooth_max_slightly_above_true_max", test_smooth_max_slightly_above_true_max),
        ("smooth::tests::test_smooth_max_symmetric", test_smooth_max_symmetric),
        ("smooth::tests::test_smooth_max_convergence", test_smooth_max_convergence),
        ("smooth::tests::test_smooth_max_high_alpha", test_smooth_max_high_alpha),
        ("smooth::tests::test_smooth_max_equal_values", test_smooth_max_equal_values),
        ("smooth::tests::test_smooth_max_negative_values", test_smooth_max_negative_values),
        ("smooth::tests::test_smooth_max_axis_basic", test_smooth_max_axis_basic),
        ("smooth::tests::test_smooth_max_axis_single", test_smooth_max_axis_single),
        ("smooth::tests::test_smooth_max_axis_empty", test_smooth_max_axis_empty),
        ("smooth::tests::test_smooth_max_axis_negative", test_smooth_max_axis_negative),
        ("smooth::tests::test_smooth_max_axis_high_alpha", test_smooth_max_axis_high_alpha),
        ("smooth::tests::test_smooth_max_pair_basic", test_smooth_max_pair_basic),
        ("smooth::tests::test_smooth_max_pair_empty", test_smooth_max_pair_empty),
        ("smooth::tests::test_smooth_max_pair_mismatched_lengths", test_smooth_max_pair_mismatched_lengths),
        ("smooth::tests::test_smooth_min_slightly_below_true_min", test_smooth_min_slightly_below_true_min),
        ("smooth::tests::test_smooth_min_symmetric", test_smooth_min_symmetric),
        ("smooth::tests::test_smooth_min_via_max_identity", test_smooth_min_via_max_identity),
        ("smooth::tests::test_smooth_min_axis_basic", test_smooth_min_axis_basic),
        ("smooth::tests::test_smooth_min_axis_single", test_smooth_min_axis_single),
        ("smooth::tests::test_smooth_min_axis_empty", test_smooth_min_axis_empty),
        ("smooth::tests::test_smooth_min_axis_via_max_identity", test_smooth_min_axis_via_max_identity),
        ("smooth::tests::test_smooth_min_pair_basic", test_smooth_min_pair_basic),
        ("smooth::tests::test_smooth_min_pair_empty", test_smooth_min_pair_empty),
        ("smooth::tests::test_min_pair_via_max_pair_identity", test_min_pair_via_max_pair_identity),
        ("smooth::tests::test_smooth_min_pair_mismatched_lengths", test_smooth_min_pair_mismatched_lengths),
        ("smooth::tests::test_smooth_relu_positive", test_smooth_relu_positive),
        ("smooth::tests::test_smooth_relu_negative", test_smooth_relu_negative),
        ("smooth::tests::test_smooth_relu_zero", test_smooth_relu_zero),
        ("smooth::tests::test_smooth_relu_high_alpha", test_smooth_relu_high_alpha),
        ("smooth::tests::test_relu_penalty_below_margin", test_relu_penalty_below_margin),
        ("smooth::tests::test_relu_penalty_above_margin", test_relu_penalty_above_margin),
        ("smooth::tests::test_relu_penalty_at_margin", test_relu_penalty_at_margin),
        ("smooth::tests::test_leaky_relu_positive", test_leaky_relu_positive),
        ("smooth::tests::test_leaky_relu_negative", test_leaky_relu_negative),
        ("smooth::tests::test_leaky_relu_zero_negative_slope", test_leaky_relu_zero_negative_slope),
        ("smooth::tests::test_smooth_abs_positive", test_smooth_abs_positive),
        ("smooth::tests::test_smooth_abs_negative", test_smooth_abs_negative),
        ("smooth::tests::test_smooth_abs_symmetry", test_smooth_abs_symmetry),
        ("smooth::tests::test_smooth_abs_at_zero", test_smooth_abs_at_zero),
        ("smooth::tests::test_smooth_abs_high_alpha", test_smooth_abs_high_alpha),
        ("smooth::tests::test_smooth_clip_within_range", test_smooth_clip_within_range),
        ("smooth::tests::test_smooth_clip_below_min", test_smooth_clip_below_min),
        ("smooth::tests::test_smooth_clip_above_max", test_smooth_clip_above_max),
        ("smooth::tests::test_smooth_clip_high_alpha", test_smooth_clip_high_alpha),
        ("smooth::tests::test_smooth_clip_min_equals_max", test_smooth_clip_min_equals_max),
        ("smooth::tests::test_smooth_step_positive", test_smooth_step_positive),
        ("smooth::tests::test_smooth_step_negative", test_smooth_step_negative),
        ("smooth::tests::test_smooth_step_zero", test_smooth_step_zero),
        ("smooth::tests::test_smooth_step_high_alpha", test_smooth_step_high_alpha),
        ("smooth::tests::test_smooth_step_output_in_01", test_smooth_step_output_in_01),
        ("smooth::tests::test_hpwl_smooth_basic", test_hpwl_smooth_basic),
        ("smooth::tests::test_hpwl_smooth_single_point", test_hpwl_smooth_single_point),
        ("smooth::tests::test_hpwl_smooth_two_points", test_hpwl_smooth_two_points),
        ("smooth::tests::test_hpwl_smooth_empty", test_hpwl_smooth_empty),
        ("smooth::tests::test_hpwl_smooth_high_alpha", test_hpwl_smooth_high_alpha),
        ("smooth::tests::test_weighted_average_uniform", test_weighted_average_uniform),
        ("smooth::tests::test_weighted_average_dominant_weight", test_weighted_average_dominant_weight),
        ("smooth::tests::test_weighted_average_empty", test_weighted_average_empty),
        ("smooth::tests::test_weighted_average_temperature_effect", test_weighted_average_temperature_effect),
        ("smooth::tests::test_weighted_average_high_temperature_uniform", test_weighted_average_high_temperature_uniform),
        ("smooth::tests::test_weighted_average_mismatched_lengths", test_weighted_average_mismatched_lengths),
        ("smooth::tests::test_alpha_schedule_endpoints", test_alpha_schedule_endpoints),
        ("smooth::tests::test_alpha_schedule_monotonic", test_alpha_schedule_monotonic),
        ("smooth::tests::test_alpha_schedule_single_epoch", test_alpha_schedule_single_epoch),
        ("smooth::tests::test_alpha_schedule_zero_epochs", test_alpha_schedule_zero_epochs),
        ("smooth::tests::test_alpha_schedule_two_epochs", test_alpha_schedule_two_epochs),
        ("smooth::tests::test_beta_schedule_matches_alpha", test_beta_schedule_matches_alpha),
        ("smooth::tests::test_max_min_bracket", test_max_min_bracket),
        ("smooth::tests::test_pair_max_ge_min", test_pair_max_ge_min),
        ("smooth::tests::test_smooth_max_axis_via_logsumexp", test_smooth_max_axis_via_logsumexp),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    /// Reasonable f64 range for smooth function inputs — avoids NaN/inf
    /// unless a test explicitly needs those semantics.
    fn val() -> impl Strategy<Value = f64> {
        -1e6f64..1e6f64
    }

    /// Positive alpha values (including edge cases near zero).
    fn alpha() -> impl Strategy<Value = f64> {
        (0.001f64..1000.0f64).prop_map(|x| x)
    }

    /// Small vec of at most 8 reals, non-empty.
    fn small_vec() -> impl Strategy<Value = Vec<f64>> {
        prop::collection::vec(val(), 1..=8)
    }

    /// Small vec of at most 8 points, non-empty.
    fn small_points() -> impl Strategy<Value = Vec<(f64, f64)>> {
        prop::collection::vec((val(), val()), 1..=8)
    }

    proptest! {
        // -----------------------------------------------------------------
        // smooth_max
        // -----------------------------------------------------------------

        /// P1. smooth_max is always >= the true maximum (it overestimates due
        /// to the LogSumExp contribution from the non-maximal argument).
        #[test]
        fn p1_smooth_max_ge_max(a in val(), b in val(), alpha in alpha()) {
            let s = smooth_max(a, b, alpha);
            prop_assert!(s >= a.max(b), "smooth_max({a},{b},{alpha})={s} < max={}", a.max(b));
        }

        /// P2. smooth_max is symmetric in its two arguments (bit-exact).
        #[test]
        fn p2_smooth_max_symmetric(a in val(), b in val(), alpha in alpha()) {
            prop_assert_eq!(smooth_max(a, b, alpha), smooth_max(b, a, alpha));
        }

        /// P3. smooth_max is monotonic in alpha: increasing alpha brings the
        /// approximation closer to the true maximum, so the overestimate
        /// shrinks (never grows).
        #[test]
        fn p3_smooth_max_monotonic_in_alpha(
            a in val(), b in val(),
            alpha1 in alpha(),
            alpha2 in alpha(),
        ) {
            // Generate ordered pairs directly (not via prop_assume): a
            // ~50% rejection rate trips proptest's global-reject limit
            // (1024) before enough cases accumulate at high PROPTEST_CASES.
            let (alpha1, alpha2) = if alpha1 < alpha2 { (alpha1, alpha2) } else { (alpha2, alpha1) };
            let s1 = smooth_max(a, b, alpha1);
            let s2 = smooth_max(a, b, alpha2);
            let m = a.max(b);
            prop_assert!(s1 >= s2, "{s1} < {s2} for alpha {alpha1} < {alpha2}");
            prop_assert!(s2 >= m, "{s2} < {m}");
        }

        // -----------------------------------------------------------------
        // smooth_min
        // -----------------------------------------------------------------

        /// P4. smooth_min is always <= the true minimum.
        #[test]
        fn p4_smooth_min_le_min(a in val(), b in val(), alpha in alpha()) {
            let s = smooth_min(a, b, alpha);
            prop_assert!(s <= a.min(b), "smooth_min({a},{b},{alpha})={s} > min={}", a.min(b));
        }

        /// P5. smooth_min is symmetric (bit-exact).
        #[test]
        fn p5_smooth_min_symmetric(a in val(), b in val(), alpha in alpha()) {
            prop_assert_eq!(smooth_min(a, b, alpha), smooth_min(b, a, alpha));
        }

        /// P6. smooth_min(a,b,alpha) == -smooth_max(-a,-b,alpha) — the
        /// identity the implementation is built on.
        #[test]
        fn p6_smooth_min_via_max_identity(a in val(), b in val(), alpha in alpha()) {
            let direct = smooth_min(a, b, alpha);
            let via_max = -smooth_max(-a, -b, alpha);
            prop_assert_eq!(direct, via_max);
        }

        // -----------------------------------------------------------------
        // smooth_abs
        // -----------------------------------------------------------------

        /// P7. smooth_abs is symmetric: abs(-x) == abs(x).
        #[test]
        fn p7_smooth_abs_symmetric(x in val(), alpha in alpha()) {
            prop_assert_eq!(smooth_abs(x, alpha), smooth_abs(-x, alpha));
        }

        /// P8. smooth_abs is never negative.
        #[test]
        fn p8_smooth_abs_non_negative(x in val(), alpha in alpha()) {
            prop_assert!(smooth_abs(x, alpha) >= 0.0);
        }

        // -----------------------------------------------------------------
        // smooth_step
        // -----------------------------------------------------------------

        /// P9. smooth_step output is always in [0, 1].
        #[test]
        fn p9_smooth_step_output_in_01(x in val(), alpha in alpha()) {
            let s = smooth_step(x, alpha);
            prop_assert!((0.0..=1.0).contains(&s), "smooth_step({x},{alpha})={s} not in [0,1]");
        }

        // -----------------------------------------------------------------
        // smooth_max_axis / smooth_min_axis
        // -----------------------------------------------------------------

        /// P10. smooth_max_axis is never below the true maximum of the slice.
        #[test]
        fn p10_smooth_max_axis_ge_max(arr in small_vec(), alpha in alpha()) {
            let true_max = arr.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let s = smooth_max_axis(&arr, alpha);
            prop_assert!(s >= true_max, "smooth_max_axis={s} < max={true_max}");
        }

        /// P11. smooth_min_axis is never above the true minimum of the slice.
        #[test]
        fn p11_smooth_min_axis_le_min(arr in small_vec(), alpha in alpha()) {
            let true_min = arr.iter().copied().fold(f64::INFINITY, f64::min);
            let s = smooth_min_axis(&arr, alpha);
            prop_assert!(s <= true_min, "smooth_min_axis={s} > min={true_min}");
        }

        // -----------------------------------------------------------------
        // hpwl_smooth
        // -----------------------------------------------------------------

        /// P12. hpwl_smooth >= true HPWL (it overestimates).
        #[test]
        fn p12_hpwl_smooth_ge_true_hpwl(pts in small_points(), alpha in alpha()) {
            let xs: Vec<f64> = pts.iter().map(|(x, _)| *x).collect();
            let ys: Vec<f64> = pts.iter().map(|(_, y)| *y).collect();
            let true_max_x = xs.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let true_min_x = xs.iter().copied().fold(f64::INFINITY, f64::min);
            let true_max_y = ys.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let true_min_y = ys.iter().copied().fold(f64::INFINITY, f64::min);
            let true_hpwl = (true_max_x - true_min_x) + (true_max_y - true_min_y);
            let s = hpwl_smooth(&pts, alpha);
            prop_assert!(s >= true_hpwl - 1e-9,
                "hpwl_smooth={s} < true_hpwl={true_hpwl}");
        }

        // -----------------------------------------------------------------
        // weighted_average_smooth
        // -----------------------------------------------------------------

        /// P13. weighted_average_smooth result lies in [min(values), max(values)]
        /// when all weights are non-negative.
        #[test]
        fn p13_weighted_average_bounded_by_extrema(
            values in small_vec(),
            alpha in alpha(),
        ) {
            // Use values as their own weights (all non-negative) to test
            // that the result is a convex combination.
            let result = weighted_average_smooth(&values, &values, alpha);
            let lo = values.iter().copied().fold(f64::INFINITY, f64::min);
            let hi = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            prop_assert!(result >= lo - 1e-9,
                "weighted_average_smooth={result} < min={lo}");
            prop_assert!(result <= hi + 1e-9,
                "weighted_average_smooth={result} > max={hi}");
        }

        // -----------------------------------------------------------------
        // get_alpha_schedule
        // -----------------------------------------------------------------

        /// P14. First element equals start_alpha, last equals end_alpha
        /// (for epochs > 1).
        #[test]
        fn p14_alpha_schedule_endpoints(
            start in 0.1f64..100.0,
            end in 0.1f64..100.0,
            epochs in 2usize..20,
        ) {
            let schedule = get_alpha_schedule(start, end, epochs);
            prop_assert_eq!(schedule.len(), epochs);
            prop_assert!((schedule[0] - start).abs() < 1e-12,
                "first={} != start={start}", schedule[0]);
            prop_assert!((schedule[epochs - 1] - end).abs() < 1e-12,
                "last={} != end={end}", schedule[epochs - 1]);
        }

        /// P15. The schedule is monotonic (non-decreasing when start <= end).
        #[test]
        fn p15_alpha_schedule_monotonic(
            start in 0.1f64..100.0,
            end in 0.1f64..100.0,
            epochs in 2usize..20,
        ) {
            // Order directly; the 50% rejection rate of prop_assume!(start <= end)
            // trips the global-reject limit at high PROPTEST_CASES.
            let (start, end) = if start <= end { (start, end) } else { (end, start) };
            let schedule = get_alpha_schedule(start, end, epochs);
            for w in schedule.windows(2) {
                prop_assert!(w[1] >= w[0],
                    "schedule not monotonic: {} > {}", w[0], w[1]);
            }
        }
    }
}

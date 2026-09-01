// Deterministic via-placement kernels (Wave 4, Phase 5, first slice).
//
// Python reference:
//   temper_placer/deterministic/geometry/via_placement.py  — `distance`,
//     `is_via_position_valid` and `place_via_with_clearance` (the pure
//     compute; the Python module is now a delegation shim).
//
// Bit-exactness (see tests/deterministic/test_via_placement_rust_differential.py):
//
// 1. `distance` is `math.sqrt(dx ** 2 + dy ** 2)` — `** 2` is libm `pow`
//    (NOT `x * x`), `math.sqrt` is correctly-rounded IEEE sqrt
//    (`f64::sqrt`). `pow` is resolved via `host_math::pow` through dlsym.
// 2. `math.radians(d)` is `d * (pi / 180.0)`; `math.cos` / `math.sin` are
//    the host libm's (host_math::cos / host_math::sin via dlsym).
// 3. The validity predicate is `distance < required` (STRICT — equality is
//    valid), applied over the pads in caller order.
// 4. `place_via_with_clearance` search order is deterministic: the fixed
//    radius list in order (with `break` on `r > max_search_radius`), then
//    `angle_deg` over `range(0, 360, 45)` — first valid candidate wins,
//    `None` when the spiral is exhausted. The candidate at angle 0 for the
//    FIRST radius is checked only if the target was invalid; the target
//    position is checked once, up front.

use crate::host_math::{cos, pow, sin};

/// Flattened pad fields: `[x0, y0, radius0, mask_expansion0, x1, y1, ...]`.
pub fn is_via_position_valid(
    pos_x: f64,
    pos_y: f64,
    pads: &[f64],
    via_mask_radius: f64,
    min_clearance: f64,
) -> bool {
    for chunk in pads.chunks(4) {
        let pad_x = chunk[0];
        let pad_y = chunk[1];
        let pad_mask_radius = chunk[2] + chunk[3];
        let required_distance = via_mask_radius + pad_mask_radius + min_clearance;
        if distance(pos_x, pos_y, pad_x, pad_y) < required_distance {
            return false;
        }
    }
    true
}

/// `math.sqrt(dx ** 2 + dy ** 2)` bit-for-bit.
pub fn distance(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    let dx = x1 - x2;
    let dy = y1 - y2;
    pow(pow(dx, 2.0) + pow(dy, 2.0), 0.5)
}

/// The fixed search radii, in the oracle's order.
const SEARCH_RADII: [f64; 8] = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];

/// Find a valid via position near `target_pos`, respecting mask clearances.
/// Returns `None` when the spiral is exhausted.
pub fn place_via_with_clearance(
    target_x: f64,
    target_y: f64,
    pads: &[f64],
    via_mask_radius: f64,
    min_clearance: f64,
    max_search_radius: f64,
) -> Option<(f64, f64)> {
    // 1. Check if target position is already valid.
    if is_via_position_valid(target_x, target_y, pads, via_mask_radius, min_clearance) {
        return Some((target_x, target_y));
    }

    // 2. Search in expanding spiral for a valid position.
    //    Steps: 0.25 mm increments up to max_search_radius; 8 angles (45 deg).
    let pi_over_180 = std::f64::consts::PI / 180.0;
    for r in SEARCH_RADII {
        if r > max_search_radius {
            break;
        }
        for angle_deg in (0..360).step_by(45) {
            let angle_rad = angle_deg as f64 * pi_over_180;
            let candidate_x = target_x + r * cos(angle_rad);
            let candidate_y = target_y + r * sin(angle_rad);
            if is_via_position_valid(candidate_x, candidate_y, pads, via_mask_radius, min_clearance) {
                return Some((candidate_x, candidate_y));
            }
        }
    }

    None
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn pad(x: f64, y: f64, r: f64, m: f64) -> Vec<f64> {
        vec![x, y, r, m]
    }

    #[cfg_attr(test, test)]
    fn distance_pythagorean() {
        assert_eq!(distance(0.0, 0.0, 3.0, 4.0), 5.0);
        assert_eq!(distance(3.0, 4.0, 0.0, 0.0), 5.0);
        assert_eq!(distance(0.0, 0.0, 0.0, 0.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn valid_no_pads() {
        assert!(is_via_position_valid(1.0, 2.0, &[], 0.3, 0.1));
    }

    #[cfg_attr(test, test)]
    fn valid_strict_inequality() {
        // distance == required -> VALID (predicate is `< required`).
        // distance(0,0 -> 0.5,0) = 0.5 == 0.2 + 0.2 + 0.1 + 0.0
        let pads = pad(0.5, 0.0, 0.2, 0.1);
        assert!(is_via_position_valid(0.0, 0.0, &pads, 0.2, 0.0));
    }

    #[cfg_attr(test, test)]
    fn place_empty_pads_returns_target() {
        assert_eq!(
            place_via_with_clearance(1.5, -2.0, &[], 0.3, 0.1, 2.0),
            Some((1.5, -2.0))
        );
    }

    #[cfg_attr(test, test)]
    fn place_returns_none_when_exhausted() {
        // A pad that invalidates every point in the spiral.
        let pads = pad(0.0, 0.0, 3.0, 0.0);
        assert_eq!(place_via_with_clearance(0.0, 0.0, &pads, 0.2, 0.0, 2.0), None);
    }

    #[cfg_attr(test, test)]
    fn place_respects_max_search_radius() {
        // A pad that blocks every candidate within max_search_radius but
        // not the ones beyond it: the only valid candidates (r = 1.25+)
        // are skipped because r > 1.0 -> None.
        let pads = pad(0.0, 0.0, 1.0, 0.0);
        assert_eq!(place_via_with_clearance(0.0, 0.0, &pads, 0.1, 0.0, 1.0), None);
        // With a larger max_search_radius the r=1.25 candidate is reached.
        let got = place_via_with_clearance(0.0, 0.0, &pads, 0.1, 0.0, 1.25);
        assert!(got.is_some());
        let (x, _) = got.unwrap();
        assert_eq!(x, 1.25);
    }

    #[cfg_attr(test, test)]
    fn place_finds_first_valid_candidate() {
        // Target invalid (pad at origin, required 0.3 > distance 0).
        // r=0.25, angle 0 candidate (0.25, 0): distance 0.25 < 0.3 invalid.
        // r=0.5, angle 0 candidate (0.5, 0): distance 0.5 >= 0.3 valid.
        let pads = pad(0.0, 0.0, 0.0, 0.0);
        let got = place_via_with_clearance(0.0, 0.0, &pads, 0.3, 0.0, 2.0);
        assert!(got.is_some());
        let (x, _) = got.unwrap();
        assert_eq!(x, 0.5);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("via_placement::tests::distance_pythagorean", distance_pythagorean),
        ("via_placement::tests::valid_no_pads", valid_no_pads),
        ("via_placement::tests::valid_strict_inequality", valid_strict_inequality),
        ("via_placement::tests::place_empty_pads_returns_target", place_empty_pads_returns_target),
        ("via_placement::tests::place_returns_none_when_exhausted", place_returns_none_when_exhausted),
        ("via_placement::tests::place_respects_max_search_radius", place_respects_max_search_radius),
        ("via_placement::tests::place_finds_first_valid_candidate", place_finds_first_valid_candidate),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

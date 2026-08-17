//! `WorldPosition` — a pad's board-frame position, constructible ONLY by
//! the rotation kernel.
//!
//! A pad's world position is the `(x, y)` on the board after applying the
//! full component transform: component position + R(-θ) rotation +
//! quadrant quarter-turn + pin offset (+ the KiCad bottom-side X mirror).
//! The transform is `pin_world_position_kernel` (mirror X when
//! `side == 1`, rotate with KiCad's `R(-theta)` convention
//! `rotate_local_to_world`: `x*c + y*s`, `-x*s + y*c`, then add the
//! component position).
//!
//! # Why this type exists — the same bug hit three times
//!
//! Every one of these was fixed the same way — "call the rotation kernel
//! instead of naive `comp_pos + pin_pos`" — and nothing stopped the next
//! caller from reintroducing the naive sum:
//!
//! 1. **Zone-stitch swap shorts (2026-08-15).** `run_collect_pad_positions`
//!    (the board→pad-positions conversion feeding the zone-stitch writer)
//!    summed `comp.initial_position + pin.position` with NO component
//!    rotation. For a rotated 2-pad component that lands every pad on the
//!    MIRROR position across the anchor — i.e. the OTHER pad — so each
//!    net's stitch track was emitted from the other net's physical pad:
//!    204 `shorting_items` + 2 `tracks_crossing` on the 2026-08-15 routed
//!    board (e.g. w1_1's stitch from RV1's ac_n pad). See
//!    `docs/evidence/2026-08-15-router-pad-avoidance-fix.md`.
//! 2. **Zone hulls at wrong coordinates.** The same naive sum placed zone
//!    hulls and the connectivity preflight at wrong coordinates for the
//!    148/169 components with nonzero rotation — measured: only 21/59 real
//!    pads inside their same-layer hulls.
//! 3. **The `run_collect_pad_positions` rotation omission, again.**
//!    Re-introduced after fix 1 and re-fixed by calling back into
//!    `pin_world_position_at_py` (the same kernel).
//!
//! The structural fix: a world position is now a *type* with no public
//! constructor from raw coordinates. `from_component_pin` is the ONLY way
//! to build one, and it applies the full kernel (mirror + R(-θ) +
//! quadrant + component position) by construction. A future caller cannot
//! forget the rotation — there is no `comp_pos + pin_pos` path into the
//! type at all.
//!
//! ```compile_fail
//! use temper_geometry::WorldPosition;
//! // WorldPosition has NO public constructor from raw coordinates: this
//! // struct-literal form cannot compile (private fields), which is the
//! // whole point — an unrotated `comp_pos + pin_pos` result has no way in.
//! let _bad = WorldPosition { x: 1.0, y: 2.0 };
//! ```
//!
//! ```compile_fail
//! use temper_geometry::WorldPosition;
//! // And no `From<(f64, f64)>` impl either: a raw (x, y) pair can never
//! // become a WorldPosition without passing through the rotation kernel.
//! let _bad: WorldPosition = (1.0, 2.0).into();
//! ```
//!
//! Adoption is deliberately incremental: existing call sites that already
//! resolve through `pin_world_position_at_py` correctly can switch to
//! `from_component_pin` one at a time (`run_collect_pad_positions` is the
//! first proven call site). The type exists to prevent FUTURE naive-sum
//! callers, not to churn every correct site in one change.

use crate::core_graph_geometry::{normalize_rotation_index, pin_world_position_kernel};
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// A pad's world position — the `(x, y)` on the board after applying
/// component position + rotation + quadrant + pin offset (and the KiCad
/// bottom-side X mirror).
///
/// Fields are private: the ONLY way to construct one is
/// [`WorldPosition::from_component_pin`], which applies the full
/// `pin_world_position_kernel` (mirror + R(-θ) + quadrant + comp position).
/// Raw `(x, y)` values cannot be promoted into the type, so the recurring
/// "naive `comp_pos + pin_pos` without rotation" bug is unrepresentable.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WorldPosition {
    x: f64,
    y: f64,
}

impl WorldPosition {
    /// The ONLY way to construct a `WorldPosition`.
    ///
    /// Applies the full transform exactly as `pin_world_position_kernel`
    /// does (the same kernel the session's three rotation fixes all
    /// converged on):
    ///
    /// ```text
    /// rotation_rad = comp_rotation + quadrant * (PI / 2)   # index * PI / 2,
    ///                                                       # the oracle's
    ///                                                       # division chain
    /// world = comp_pos + R(-rotation_rad) · (mirror_x(pin_offset, side))
    /// ```
    ///
    /// `comp_rotation` is the resolved rotation in radians (the float path
    /// of `_normalize_rotation`); `initial_rotation_quadrant` is the
    /// quarter-turn *index* (0-3 → 0/90/180/270), added so callers holding
    /// the raw `Component.initial_rotation_quadrant` int need not do the
    /// index→radians conversion themselves (they pass `comp_rotation =
    /// 0.0`). `initial_side` is KiCad's bottom-side flag (1 → mirror X
    /// before rotation).
    pub fn from_component_pin(
        comp_pos: (f64, f64),
        comp_rotation: f64,
        pin_offset: (f64, f64),
        initial_rotation_quadrant: i32,
        initial_side: i32,
    ) -> Self {
        let quadrant_rad = normalize_rotation_index(initial_rotation_quadrant as i64);
        let rotation_rad = comp_rotation + quadrant_rad;
        let (x, y) = pin_world_position_kernel(
            pin_offset.0,
            pin_offset.1,
            initial_side as i64,
            rotation_rad,
            comp_pos.0,
            comp_pos.1,
        );
        Self { x, y }
    }

    pub fn x(&self) -> f64 {
        self.x
    }

    pub fn y(&self) -> f64 {
        self.y
    }

    pub fn as_point(&self) -> geo::Point<f64> {
        geo::Point::new(self.x, self.y)
    }

    pub fn as_tuple(&self) -> (f64, f64) {
        (self.x, self.y)
    }
}

/// Python-exported `WorldPosition::from_component_pin`: applies the full
/// R(-θ) + quadrant + side correction in one call and returns the world
/// `(x, y)` tuple. The only sanctioned way to construct a world position
/// from plain primitives — the duck-typed `pin_world_position_at_py`
/// (which reads the attributes off Python objects itself) stays for the
/// object-graph callers; this one exists for callers that already hold the
/// resolved values.
#[cfg(feature = "python")]
#[pyfunction]
pub fn world_position_from_component_pin_py(
    comp_pos: (f64, f64),
    comp_rotation: f64,
    pin_offset: (f64, f64),
    initial_rotation_quadrant: i32,
    initial_side: i32,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        WorldPosition::from_component_pin(
            comp_pos,
            comp_rotation,
            pin_offset,
            initial_rotation_quadrant,
            initial_side,
        )
        .as_tuple()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// Register this module's kernels with the `temper_geometry` module.
#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(world_position_from_component_pin_py, m)?)?;
    Ok(())
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Assert two world positions agree within float tolerance.
    fn assert_close(a: &WorldPosition, b: &WorldPosition, tol: f64, what: &str) {
        assert!(
            (a.x - b.x).abs() <= tol && (a.y - b.y).abs() <= tol,
            "{what}: ({}, {}) vs ({}, {}) differ by more than {tol}",
            a.x,
            a.y,
            b.x,
            b.y
        );
    }

    /// 0° rotation: world position is exactly `comp_pos + pin_offset`
    /// (identity — the kernel degenerates to the naive sum, which is what
    /// makes the naive sum so seductive: it is right for rotation-0
    /// components and wrong for the other 148/169 of them).
    #[cfg_attr(test, test)]
    fn zero_rotation_is_identity() {
        let wp = WorldPosition::from_component_pin((10.0, 20.0), 0.0, (1.5, -2.0), 0, 0);
        assert_eq!(wp.as_tuple(), (11.5, 18.0));
    }

    /// 180° rotation: a 2-pin component's pins SWAP positions — the exact
    /// bug that caused the zone-stitch swap shorts. With quadrant 2
    /// (rotation π), pin A at +x lands where pin B's UNROTATED position
    /// is, and vice versa; the naive `comp_pos + pin_pos` sum would land
    /// pin A on pin B's REAL (rotated) pad — the other net's pad.
    #[cfg_attr(test, test)]
    fn rotated_180_two_pin_component_swaps_pins() {
        let comp_pos = (10.0, 20.0);
        let pin_a = (1.5, 0.0);
        let pin_b = (-1.5, 0.0);
        let a_rot = WorldPosition::from_component_pin(comp_pos, 0.0, pin_a, 2, 0);
        let b_rot = WorldPosition::from_component_pin(comp_pos, 0.0, pin_b, 2, 0);
        let a_unrot = WorldPosition::from_component_pin(comp_pos, 0.0, pin_a, 0, 0);
        let b_unrot = WorldPosition::from_component_pin(comp_pos, 0.0, pin_b, 0, 0);

        // After 180°, A is where unrotated B was, and B where unrotated A
        // was — the swap.
        assert_close(&a_rot, &b_unrot, 1e-9, "A@180 must land on B's unrotated pad");
        assert_close(&b_rot, &a_unrot, 1e-9, "B@180 must land on A's unrotated pad");

        // And the naive sum is exactly the OTHER pad's real position — the
        // swap-short mechanism, pinned explicitly:
        let naive_a = WorldPosition::from_component_pin(comp_pos, 0.0, pin_a, 0, 0);
        assert_close(&naive_a, &b_rot, 1e-9, "naive A lands on B's real pad (the bug)");
        assert!(naive_a.as_tuple() != a_rot.as_tuple(), "naive A must differ from rotated A");
    }

    /// 90° rotation (quadrant 1): correct trigonometric transform. R(-θ)
    /// with θ = π/2 maps local +x to world -y: (1.5, 0) at comp (10, 20)
    /// lands at (10, 18.5).
    #[cfg_attr(test, test)]
    fn rotated_90_trigonometric_transform() {
        let wp = WorldPosition::from_component_pin((10.0, 20.0), 0.0, (1.5, 0.0), 1, 0);
        assert!((wp.x() - 10.0).abs() < 1e-9, "x={}", wp.x());
        assert!((wp.y() - 18.5).abs() < 1e-9, "y={}", wp.y());

        // Same transform via the float path: comp_rotation = π/2 (the
        // `_normalize_rotation` float branch), quadrant 0. Both paths must
        // agree.
        let via_float = WorldPosition::from_component_pin(
            (10.0, 20.0),
            std::f64::consts::FRAC_PI_2,
            (1.5, 0.0),
            0,
            0,
        );
        assert_close(&wp, &via_float, 1e-9, "quadrant path and float path must agree");
    }

    /// Side mirror: `initial_side == 1` (KiCad bottom side) mirrors X
    /// BEFORE rotation — (1.5, 0) becomes (-1.5, 0), then rotates.
    #[cfg_attr(test, test)]
    fn side_one_mirrors_x_before_rotation() {
        // side=1, rotation 0: world = comp_pos + (-px, py).
        let wp = WorldPosition::from_component_pin((10.0, 20.0), 0.0, (1.5, 0.0), 0, 1);
        assert_eq!(wp.as_tuple(), (8.5, 20.0));

        // side=1, 90° quadrant: (-1.5, 0) under R(-π/2) -> (0, 1.5),
        // world (10, 21.5) — matches the kernel's own anchored test.
        let wp = WorldPosition::from_component_pin((10.0, 20.0), 0.0, (1.5, 0.0), 1, 1);
        assert!((wp.x() - 10.0).abs() < 1e-9, "x={}", wp.x());
        assert!((wp.y() - 21.5).abs() < 1e-9, "y={}", wp.y());
    }

    /// Round-trip: rotate by θ then by -θ (about the origin) recovers the
    /// original pin offset — the invariant that catches a rotation-sign
    /// error (the `investigate/rotation-sign-defect` class of bug).
    #[cfg_attr(test, test)]
    fn round_trip_rotation_then_inverse_recovers_offset() {
        let theta = 0.7; // arbitrary, not a quadrant
        let pin_offset = (3.25, -1.75);
        let forward = WorldPosition::from_component_pin((0.0, 0.0), theta, pin_offset, 0, 0);
        let back = WorldPosition::from_component_pin(
            (0.0, 0.0),
            -theta,
            forward.as_tuple(),
            0,
            0,
        );
        assert_close(&back, &WorldPosition::from_component_pin((0.0, 0.0), 0.0, pin_offset, 0, 0), 1e-9, "round-trip");
    }

    /// A rotated pin must differ from the naive sum — the property the
    /// type exists to make structurally true.
    #[cfg_attr(test, test)]
    fn rotated_position_differs_from_naive_sum() {
        let wp = WorldPosition::from_component_pin((5.0, 5.0), 0.0, (2.0, 0.0), 1, 0);
        assert_ne!(wp.as_tuple(), (7.0, 5.0), "naive comp_pos + pin_pos");
    }

    // ------------------------------------------------------------------
    // Randomized sweep (proptest, dev-dependency).  `#[cfg(test)]` ONLY:
    // proptest is a dev-dependency, absent from the non-test wasm-registry
    // build this module would otherwise break — the same structural
    // exclusion `clearance_halo.rs`'s proptests submodule carries.
    // ------------------------------------------------------------------

    #[cfg(test)]
    #[allow(clippy::items_after_test_module)]
    mod proptests {
        use super::*;
        use proptest::prelude::*;

        proptest! {
            /// For random rotations and offsets, rotating by θ then by -θ
            /// (about the origin) recovers the original offset — the sign
            /// and magnitude of the R(-θ) transform stay consistent.
            #[test]
            fn round_trip_recovers_offset_property(
                theta in -6.3f64..6.3,
                px in -100.0f64..100.0,
                py in -100.0f64..100.0,
            ) {
                let pin_offset = (px, py);
                let forward = WorldPosition::from_component_pin((0.0, 0.0), theta, pin_offset, 0, 0);
                let back = WorldPosition::from_component_pin((0.0, 0.0), -theta, forward.as_tuple(), 0, 0);
                // Values stay bounded: coordinates up to ~100, trig error
                // ~1 ulp, accumulated error well under 1e-9.
                prop_assert!((back.x() - px).abs() < 1e-9, "x round-trip drift: {} vs {}", back.x(), px);
                prop_assert!((back.y() - py).abs() < 1e-9, "y round-trip drift: {} vs {}", back.y(), py);
            }

            /// For random rotations and offsets, rotating by θ₁ then by θ₂
            /// (about the origin) equals rotating once by θ₁+θ₂ — the
            /// transform composes like a rotation (R(-θ₁) then R(-θ₂) =
            /// R(-(θ₁+θ₂))). At the origin only: with a nonzero comp_pos
            /// the two-stage application adds `comp_pos` twice, which is
            /// not the same map.
            #[test]
            fn rotation_composition_property(
                theta1 in -3.15f64..3.15,
                theta2 in -3.15f64..3.15,
                px in -10.0f64..10.0,
                py in -10.0f64..10.0,
            ) {
                let once = WorldPosition::from_component_pin((0.0, 0.0), theta1 + theta2, (px, py), 0, 0);
                let twice = WorldPosition::from_component_pin(
                    (0.0, 0.0),
                    theta2,
                    WorldPosition::from_component_pin((0.0, 0.0), theta1, (px, py), 0, 0).as_tuple(),
                    0,
                    0,
                );
                prop_assert!((once.x() - twice.x()).abs() < 1e-9, "x composition drift: {} vs {}", once.x(), twice.x());
                prop_assert!((once.y() - twice.y()).abs() < 1e-9, "y composition drift: {} vs {}", once.y(), twice.y());
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("world_position::tests::zero_rotation_is_identity", zero_rotation_is_identity),
        ("world_position::tests::rotated_180_two_pin_component_swaps_pins", rotated_180_two_pin_component_swaps_pins),
        ("world_position::tests::rotated_90_trigonometric_transform", rotated_90_trigonometric_transform),
        ("world_position::tests::side_one_mirrors_x_before_rotation", side_one_mirrors_x_before_rotation),
        ("world_position::tests::round_trip_rotation_then_inverse_recovers_offset", round_trip_rotation_then_inverse_recovers_offset),
        ("world_position::tests::rotated_position_differs_from_naive_sum", rotated_position_differs_from_naive_sum),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

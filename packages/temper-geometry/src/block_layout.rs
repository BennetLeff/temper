//! Discrete functional-block transforms for bounded place-to-route search.
//!
//! Rotation delegates to `kicad_transform`; this module must not grow an
//! independent R(+/-theta) implementation.  Internal rearrangement is limited
//! to four dimension-derived orbit slots around an anchor body, not arbitrary
//! coordinate nudges.

use crate::kicad_transform::rotate_local_to_world_deg;

#[cfg(feature = "python")]
use pyo3::prelude::*;

fn snap_zero(value: f64) -> f64 {
    if value.abs() < 1e-12 {
        0.0
    } else {
        value
    }
}

pub fn transform_block(
    members: &[(String, f64, f64, f64)],
    anchor_x: f64,
    anchor_y: f64,
    quarter_turn: usize,
    dx_mm: f64,
    dy_mm: f64,
) -> Result<Vec<(String, f64, f64, f64)>, String> {
    if quarter_turn > 3 {
        return Err("quarter_turn must be in 0..=3".into());
    }
    if ![anchor_x, anchor_y, dx_mm, dy_mm]
        .iter()
        .all(|v| v.is_finite())
    {
        return Err("anchor and translation values must be finite".into());
    }
    let angle = quarter_turn as f64 * 90.0;
    members
        .iter()
        .map(|(reference, x, y, rotation)| {
            if ![x, y, rotation].iter().all(|v| v.is_finite()) {
                return Err(format!(
                    "{reference}: position and rotation must be finite"
                ));
            }
            let (rx, ry) = rotate_local_to_world_deg(x - anchor_x, y - anchor_y, angle);
            Ok((
                reference.clone(),
                anchor_x + snap_zero(rx) + dx_mm,
                anchor_y + snap_zero(ry) + dy_mm,
                (rotation + angle).rem_euclid(360.0),
            ))
        })
        .collect()
}

/// Four non-overlapping body-envelope slots around an anchor.  Odd pivot
/// rotations swap width/height before the separation is derived.
pub fn orbit_slots(
    anchor_x: f64,
    anchor_y: f64,
    anchor_width: f64,
    anchor_height: f64,
    pivot_width: f64,
    pivot_height: f64,
    gap_mm: f64,
    pivot_quarter_turn: usize,
) -> Result<Vec<(String, f64, f64, usize)>, String> {
    if pivot_quarter_turn > 3 {
        return Err("pivot_quarter_turn must be in 0..=3".into());
    }
    if ![
        anchor_x,
        anchor_y,
        anchor_width,
        anchor_height,
        pivot_width,
        pivot_height,
        gap_mm,
    ]
    .iter()
    .all(|v| v.is_finite())
    {
        return Err("orbit geometry must be finite".into());
    }
    if anchor_width <= 0.0
        || anchor_height <= 0.0
        || pivot_width <= 0.0
        || pivot_height <= 0.0
        || gap_mm < 0.0
    {
        return Err("body dimensions must be > 0 and gap_mm must be >= 0".into());
    }
    let (pw, ph) = if pivot_quarter_turn % 2 == 0 {
        (pivot_width, pivot_height)
    } else {
        (pivot_height, pivot_width)
    };
    let x_offset = anchor_width / 2.0 + gap_mm + pw / 2.0;
    let y_offset = anchor_height / 2.0 + gap_mm + ph / 2.0;
    Ok(vec![
        (
            "right".into(),
            anchor_x + x_offset,
            anchor_y,
            pivot_quarter_turn,
        ),
        (
            "left".into(),
            anchor_x - x_offset,
            anchor_y,
            pivot_quarter_turn,
        ),
        (
            "above".into(),
            anchor_x,
            anchor_y - y_offset,
            pivot_quarter_turn,
        ),
        (
            "below".into(),
            anchor_x,
            anchor_y + y_offset,
            pivot_quarter_turn,
        ),
    ])
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn block_transform_py(
    members: Vec<(String, f64, f64, f64)>,
    anchor_x: f64,
    anchor_y: f64,
    quarter_turn: usize,
    dx_mm: f64,
    dy_mm: f64,
) -> PyResult<Vec<(String, f64, f64, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        transform_block(&members, anchor_x, anchor_y, quarter_turn, dx_mm, dy_mm)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn block_orbit_slots_py(
    anchor_x: f64,
    anchor_y: f64,
    anchor_width: f64,
    anchor_height: f64,
    pivot_width: f64,
    pivot_height: f64,
    gap_mm: f64,
    pivot_quarter_turn: usize,
) -> PyResult<Vec<(String, f64, f64, usize)>> {
    temper_py_bridge::catch_unwind(|| {
        orbit_slots(
            anchor_x,
            anchor_y,
            anchor_width,
            anchor_height,
            pivot_width,
            pivot_height,
            gap_mm,
            pivot_quarter_turn,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn asymmetric_quarter_turn_uses_kicad_r_minus_theta() {
        let members = vec![("R4".into(), 10.0, 4.0, 0.0)];
        let moved = transform_block(&members, 0.0, 0.0, 1, 0.0, 0.0).unwrap();
        assert_eq!(moved, vec![("R4".into(), 4.0, -10.0, 90.0)]);
    }

    #[cfg_attr(test, test)]
    fn orbit_slots_derive_nonoverlap_from_body_dimensions() {
        let slots = orbit_slots(10.0, 20.0, 8.0, 6.0, 4.0, 2.0, 1.0, 0).unwrap();
        assert_eq!(slots[0], ("right".into(), 17.0, 20.0, 0));
        assert_eq!(slots[2], ("above".into(), 10.0, 15.0, 0));
    }

    #[cfg_attr(test, test)]
    fn odd_pivot_rotation_swaps_body_extents() {
        let slots = orbit_slots(0.0, 0.0, 8.0, 6.0, 4.0, 2.0, 1.0, 1).unwrap();
        assert_eq!(slots[0].1, 6.0);
        assert_eq!(slots[2].2, -6.0);
    }

    #[cfg_attr(test, test)]
    fn invalid_transform_and_orbit_requests_fail_closed() {
        assert!(transform_block(&[], 0.0, 0.0, 4, 0.0, 0.0).is_err());
        assert!(orbit_slots(0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0).is_err());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("block_layout::tests::asymmetric_quarter_turn_uses_kicad_r_minus_theta", asymmetric_quarter_turn_uses_kicad_r_minus_theta),
        ("block_layout::tests::orbit_slots_derive_nonoverlap_from_body_dimensions", orbit_slots_derive_nonoverlap_from_body_dimensions),
        ("block_layout::tests::odd_pivot_rotation_swaps_body_extents", odd_pivot_rotation_swaps_body_extents),
        ("block_layout::tests::invalid_transform_and_orbit_requests_fail_closed", invalid_transform_and_orbit_requests_fail_closed),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

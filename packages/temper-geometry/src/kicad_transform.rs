// KiCad's footprint-child rotation convention — the single sanctioned
// implementation of the R(-theta) rule this repo consolidated into
// `temper_placer.geometry.kicad_transform` (Wave 4: that module is now a
// shim delegating here; its docstring carries the incident history — 12
// wrong R(+theta) copies, one of which hid real clearance hazards).
//
// Convention: world = footprint_position + R(-theta) . local_offset, with
//
//     R(-theta) = [[ cos(theta),  sin(theta)],
//                  [-sin(theta),  cos(theta)]]
//
// confirmed against real `kicad-cli 10.0.4 pcb drc` output on a hand-built
// minimal board — see
// `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`
// Sec. 2. `rotate_world_to_local` is the transpose R(+theta), which for a
// rotation matrix is also its exact inverse.
//
// Bit-exactness (differential suite contract):
// - `cos`/`sin` are resolved through the host process's already-loaded
//   libm via `pad_geometry::math_cos_sin` (the B1 dlsym pattern), so the
//   kernels match CPython's `math.cos`/`math.sin` bit-for-bit on the host
//   runtime — NOT the plain statically-bound `f64::cos`/`f64::sin` that
//   `transform.rs::transform_pin_position` (a separate, older copy kept
//   for the crate's own consumers) uses and can diverge from by 1 ulp.
// - the degrees wrappers preserve the oracle's exact expression shape:
//   CPython's `math.radians(t)` is `t * (Py_MATH_PI / 180.0)`, so the
//   Rust side writes `t * (std::f64::consts::PI / 180.0)` (B2/B7) rather
//   than `f64::to_radians`.
// - `place_local_to_world` composes rotate-then-translate in the oracle's
//   op order; `shapely_rotation_angle_deg` is IEEE negation.
//
// Pinned by `tests/geometry/test_kicad_transform_rust_differential.py`
// (verbatim `_oracle_*` blocks, `float.hex()` equality over the exhaustive
// finite angle set, randomized sweeps, and NaN/inf/signed-zero/denormal
// edges) and `tests/geometry/test_kicad_transform_pbt.py`.

use crate::pad_geometry::math_cos_sin;

/// Rotate a local (footprint-relative) offset into world orientation —
/// KiCad's real R(-theta) convention. `theta_rad` is the footprint's own
/// board rotation, in radians.
pub fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let (c, s) = math_cos_sin(theta_rad);
    (x * c + y * s, -x * s + y * c)
}

/// CPython `math.radians`: `t * (PI / 180.0)` — the oracle's exact
/// expression shape, not `f64::to_radians` (B2/B7).
fn radians(theta_deg: f64) -> f64 {
    theta_deg * (std::f64::consts::PI / 180.0)
}

/// Degrees convenience wrapper for [`rotate_local_to_world`].
pub fn rotate_local_to_world_deg(x: f64, y: f64, theta_deg: f64) -> (f64, f64) {
    rotate_local_to_world(x, y, radians(theta_deg))
}

/// Inverse of [`rotate_local_to_world`]: rotate a world-oriented offset
/// back into the footprint's local frame. This is R(+theta) — the
/// transpose of R(-theta), which for a rotation matrix is also its exact
/// inverse.
pub fn rotate_world_to_local(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let (c, s) = math_cos_sin(theta_rad);
    (x * c - y * s, x * s + y * c)
}

/// Degrees convenience wrapper for [`rotate_world_to_local`].
pub fn rotate_world_to_local_deg(x: f64, y: f64, theta_deg: f64) -> (f64, f64) {
    rotate_world_to_local(x, y, radians(theta_deg))
}

/// Rotate a local offset by `theta_rad` (KiCad convention) and translate
/// by `(origin_x, origin_y)` — the common "rotate offset from a
/// component's origin, then place at the component's board position"
/// pattern, in one call.
pub fn place_local_to_world(
    local_x: f64,
    local_y: f64,
    origin_x: f64,
    origin_y: f64,
    theta_rad: f64,
) -> (f64, f64) {
    let (rx, ry) = rotate_local_to_world(local_x, local_y, theta_rad);
    (origin_x + rx, origin_y + ry)
}

/// The angle (degrees) to pass to `shapely.affinity.rotate` to apply this
/// convention to a polygon. `shapely.affinity.rotate`'s `angle` parameter
/// is CCW-positive (R(+theta)) — the opposite sign of R(-theta), so this
/// is the negation of the footprint's own rotation.
pub fn shapely_rotation_angle_deg(theta_deg: f64) -> f64 {
    -theta_deg
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

// ---------------------------------------------------------------------------
// PyO3 bridge — wholly-pyo3 surface in the style of the Wave 4 kernel
// modules: every entry point mirrors one Python function bit-for-bit and
// is wrapped in catch_unwind (G7). The Python names carry the `kicad_`
// prefix because bridge.rs already registers `rotate_local_to_world_py`
// (clearance_geometry.rs's own copy, used by `_copper.py`); the shim
// re-exports these six under the sanctioned public names.
// ---------------------------------------------------------------------------

/// Replicate CPython's `math.cos(±inf)` / `math.sin(±inf)` domain error.
///
/// The pre-migration module called `math.cos(theta)` / `math.sin(theta)`;
/// CPython raises `ValueError("math domain error")` for an infinite
/// argument (libm returns NaN and sets `errno = EDOM`, which the
/// `math_1` wrapper converts to the exception) while NaN passes through
/// as NaN. The pure kernels keep IEEE semantics (NaN), so this check
/// lives at the Python boundary to preserve the shim's behavior
/// bit-for-bit with the pre-migration Python module — an infinite
/// rotation is not a value a board can carry, and silently returning NaN
/// where the old code raised would be a silent behavioral regression
/// instead of a loud one. Pinned by
/// `test_infinite_theta_raises_math_domain_error[_deg]` in the
/// differential suite.
#[cfg(feature = "python")]
fn reject_infinite_theta(theta: f64) -> PyResult<()> {
    if theta.is_infinite() {
        Err(pyo3::exceptions::PyValueError::new_err("math domain error"))
    } else {
        Ok(())
    }
}

/// KiCad R(-theta) forward rotation (bit-identical to the pre-migration
/// `kicad_transform.rotate_local_to_world`, host-libm cos/sin).
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_rotate_local_to_world_py(x: f64, y: f64, theta_rad: f64) -> PyResult<(f64, f64)> {
    reject_infinite_theta(theta_rad)?;
    temper_py_bridge::catch_unwind(|| rotate_local_to_world(x, y, theta_rad))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Degrees wrapper for [`rotate_local_to_world`].
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_rotate_local_to_world_deg_py(x: f64, y: f64, theta_deg: f64) -> PyResult<(f64, f64)> {
    reject_infinite_theta(theta_deg)?;
    temper_py_bridge::catch_unwind(|| rotate_local_to_world_deg(x, y, theta_deg))
        .map_err(temper_py_bridge::panic_to_err)
}

/// KiCad R(+theta) inverse rotation (the transpose of R(-theta)).
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_rotate_world_to_local_py(x: f64, y: f64, theta_rad: f64) -> PyResult<(f64, f64)> {
    reject_infinite_theta(theta_rad)?;
    temper_py_bridge::catch_unwind(|| rotate_world_to_local(x, y, theta_rad))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Degrees wrapper for [`rotate_world_to_local`].
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_rotate_world_to_local_deg_py(x: f64, y: f64, theta_deg: f64) -> PyResult<(f64, f64)> {
    reject_infinite_theta(theta_deg)?;
    temper_py_bridge::catch_unwind(|| rotate_world_to_local_deg(x, y, theta_deg))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Rotate-then-translate placement (the shim's `place_local_to_world`).
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_place_local_to_world_py(
    local_x: f64,
    local_y: f64,
    origin_x: f64,
    origin_y: f64,
    theta_rad: f64,
) -> PyResult<(f64, f64)> {
    reject_infinite_theta(theta_rad)?;
    temper_py_bridge::catch_unwind(|| place_local_to_world(local_x, local_y, origin_x, origin_y, theta_rad))
        .map_err(temper_py_bridge::panic_to_err)
}

/// The negation feeding `shapely.affinity.rotate`.
#[cfg(feature = "python")]
#[pyfunction]
fn kicad_shapely_rotation_angle_deg_py(theta_deg: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| shapely_rotation_angle_deg(theta_deg))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(kicad_rotate_local_to_world_py, m)?)?;
    m.add_function(wrap_pyfunction!(kicad_rotate_local_to_world_deg_py, m)?)?;
    m.add_function(wrap_pyfunction!(kicad_rotate_world_to_local_py, m)?)?;
    m.add_function(wrap_pyfunction!(kicad_rotate_world_to_local_deg_py, m)?)?;
    m.add_function(wrap_pyfunction!(kicad_place_local_to_world_py, m)?)?;
    m.add_function(wrap_pyfunction!(kicad_shapely_rotation_angle_deg_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Closed-form quadrant law for R(-theta): 0 -> (x, y), 90 -> (y, -x),
    /// 180 -> (-x, -y), 270 -> (-y, x).
    fn quadrant_expected(x: f64, y: f64, angle_rad: f64) -> (f64, f64) {
        let two_pi = 2.0 * std::f64::consts::PI;
        let a = (angle_rad % two_pi + two_pi) % two_pi;
        let half_pi = std::f64::consts::FRAC_PI_2;
        if (a - 0.0).abs() < 1e-12 {
            (x, y)
        } else if (a - half_pi).abs() < 1e-12 {
            (y, -x)
        } else if (a - std::f64::consts::PI).abs() < 1e-12 {
            (-x, -y)
        } else if (a - 3.0 * half_pi).abs() < 1e-12 {
            (-y, x)
        } else {
            panic!("not a quadrant angle: {angle_rad}");
        }
    }

    #[test]
    fn test_rotate_local_to_world_quadrant_anchors() {
        for (px, py) in [(0.5, 0.3), (2.0, -1.0), (3.7, -2.1), (-5.0, 5.0)] {
            for angle in [
                0.0,
                std::f64::consts::FRAC_PI_2,
                std::f64::consts::PI,
                3.0 * std::f64::consts::FRAC_PI_2,
            ] {
                let got = rotate_local_to_world(px, py, angle);
                let expected = quadrant_expected(px, py, angle);
                assert!(
                    (got.0 - expected.0).abs() < 1e-9,
                    "angle {angle} offset ({px}, {py}): {} vs {}",
                    got.0,
                    expected.0
                );
                assert!(
                    (got.1 - expected.1).abs() < 1e-9,
                    "angle {angle} offset ({px}, {py}): {} vs {}",
                    got.1,
                    expected.1
                );
            }
        }
    }

    #[test]
    fn test_rotate_world_to_local_quadrant_anchors() {
        // R(+theta): 90 -> (-y, x), 270 -> (y, -x).
        let (rx, ry) = rotate_world_to_local(1.0, 0.0, std::f64::consts::FRAC_PI_2);
        assert!((rx - 0.0).abs() < 1e-9, "{rx}");
        assert!((ry - 1.0).abs() < 1e-9, "{ry}");
        let (rx, ry) = rotate_world_to_local(1.0, 0.0, 3.0 * std::f64::consts::FRAC_PI_2);
        assert!((rx - 0.0).abs() < 1e-9, "{rx}");
        assert!((ry - (-1.0)).abs() < 1e-9, "{ry}");
    }

    #[test]
    fn test_zero_rotation_is_exact_identity() {
        // math.cos(0.0) == 1.0 and math.sin(0.0) == 0.0 exactly, so the
        // forward and inverse transforms at theta == 0.0 are bit-exact
        // identities (x*1 + y*0 == x, -x*0 + y*1 == y).
        assert_eq!(rotate_local_to_world(3.0, -2.0, 0.0), (3.0, -2.0));
        assert_eq!(rotate_world_to_local(3.0, -2.0, 0.0), (3.0, -2.0));
    }

    #[test]
    fn test_place_local_to_world_is_rotate_then_translate() {
        let theta = 1.2345;
        let (rx, ry) = rotate_local_to_world(2.0, -1.0, theta);
        assert_eq!(place_local_to_world(2.0, -1.0, 100.0, 200.0, theta), (100.0 + rx, 200.0 + ry));
    }

    #[test]
    fn test_degrees_wrappers_match_radians_path() {
        let (a, b) = rotate_local_to_world_deg(1.5, -3.25, 62.0);
        let (c, d) = rotate_local_to_world(1.5, -3.25, radians(62.0));
        assert_eq!((a, b), (c, d));
        let (a, b) = rotate_world_to_local_deg(1.5, -3.25, 62.0);
        let (c, d) = rotate_world_to_local(1.5, -3.25, radians(62.0));
        assert_eq!((a, b), (c, d));
    }

    #[test]
    fn test_shapely_rotation_angle_deg_is_negation() {
        assert_eq!(shapely_rotation_angle_deg(30.0), -30.0);
        assert_eq!(shapely_rotation_angle_deg(-45.0), 45.0);
        assert_eq!(shapely_rotation_angle_deg(0.0), 0.0);
        assert_eq!(shapely_rotation_angle_deg(360.0), -360.0);
    }

    #[test]
    fn test_sign_flip_discriminates_at_quadrants() {
        // Falsifier: the R(-theta) anchors must differ from the flipped
        // R(+theta) reference by O(1) on asymmetric offsets at 90/270.
        for angle in [std::f64::consts::FRAC_PI_2, 3.0 * std::f64::consts::FRAC_PI_2] {
            for (px, py) in [(0.5, 0.3), (2.0, -1.0), (3.7, -2.1), (-5.0, 5.0)] {
                let got = rotate_local_to_world(px, py, angle);
                // R(+theta): [[c, -s], [s, c]]
                let (c, s) = (angle.cos(), angle.sin());
                let flipped = (px * c - py * s, px * s + py * c);
                assert!(
                    (got.0 - flipped.0).abs() > 1e-6 || (got.1 - flipped.1).abs() > 1e-6,
                    "angle {angle} offset ({px}, {py}): R(-θ) {:?} vs R(+θ) {:?} coincide",
                    got,
                    flipped
                );
            }
        }
    }
}

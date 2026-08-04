//! Per-cell vertical-sink field builder (Wave 4, Phase 4).
//!
//! Ports the pure grid arithmetic of
//! `temper_placer/physics/heat_removal.py::build_h_field` (issue #141 —
//! the per-device through-plane heatsink conductance field `h_field`
//! consumed by the thermal FDM solver) to Rust.  The Python module
//! keeps its public API (`build_h_field`, `H_CONV_BACKGROUND`) and the
//! dict-contract validation (missing `DeviceThermalConfig` raises the
//! original `ValueError`s); the grid arithmetic delegates here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B1 (host libm via dlsym):** `(cs * 1e-3) ** 2` is CPython
//!   `float.__pow__` → host libm `pow(x, 2.0)` — NOT `x * x`
//!   (`hostmath::pow`).
//! - **B7 (f64 operation order):** `h_bg = (10.0 * cell_area_m2) /
//!   (cs * cs)` is the left-to-right chain with the parenthesized
//!   `cs * cs` denominator; `h_cell = g_dev / ((n_cells * cs) * cs)` is
//!   `g_dev / (n_cells * cs * cs)` left-to-right with `n_cells` widened
//!   to f64 exactly like Python's int*float multiply.
//! - **Int-truncation parity:** `int(np.floor(x))` / `int(np.ceil(x))`
//!   are floor/ceil-then-truncate-toward-zero, identical to Rust's
//!   `x.floor() as i64` / `x.ceil() as i64` for the FINITE values that
//!   reach them (measured 2026-08-04 for negative and fractional
//!   inputs).  On degenerate values CPython RAISES (`int(NaN)` →
//!   ValueError, `int(±inf)` → OverflowError) where Rust's `as i64`
//!   cast would silently saturate — the kernel replicates the raise via
//!   [`BuildHFieldError`] (NaN centroids / NaN origin / ±inf centroids /
//!   cs == 0.0 are all reachable through the shim, which validates
//!   device_thermal presence but not coordinates/cs; pinned by the
//!   degenerate-input differential cases).
//! - **Iteration order:** devices are accumulated in the caller's dict
//!   iteration order (the Python shim passes them in that order); two
//!   overlapping footprints accumulate `+= h_cell` in the same order on
//!   both sides, so overlapping cells stay bit-identical.  A `set`/
//!   unordered source is NOT sorted — order is preserved as given.
//! - **B8 (denormal underflow):** default IEEE semantics.
//!
//! R24: N/A as a *constraint encoding* — `h_field` is an input FIELD
//! builder consumed by the FDM solver, not a CP-SAT constraint that
//! gates on a physics quantity.  The applicable contract is bit-exact
//! parity (R1a); the soundness property of the built field (bounded,
//! non-negative, dimensionally consistent with the FDM diagonal) is
//! asserted by the PBT suite.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyBytes;
#[cfg(feature = "python")]
use temper_py_bridge;

use crate::hostmath;

/// Background natural convection coefficient, W/(m²·K) — mirrors
/// `H_CONV_BACKGROUND = 10.0` in the reference module.
pub const H_CONV_BACKGROUND: f64 = 10.0;
/// Device footprint side length (mm) — mirrors `_DEVICE_FOOTPRINT_MM`.
pub const DEVICE_FOOTPRINT_MM: f64 = 5.0;

/// Error a degenerate input raises through the pyo3 bridge, matching the
/// reference's CPython exception exactly (the reference's
/// `int(np.floor(x))` / `int(np.ceil(x))` raise on degenerate floats and
/// its `... / (cs * cs)` raises on cs == 0.0; a Rust `as i64` cast would
/// silently saturate instead).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BuildHFieldError {
    /// `int(np.floor/ceil(NaN))` → `ValueError("cannot convert float NaN
    /// to integer")` (reachable via NaN device centroids or a NaN grid
    /// origin; the shim validates device_thermal presence but NOT
    /// coordinates/cs).
    NanToInt,
    /// `int(np.floor/ceil(±inf))` → `OverflowError("cannot convert float
    /// infinity to integer")` (a ±inf centroid, or the ±inf quotient of a
    /// finite numerator over cs == 0.0 — see below).
    InfToInt,
    /// `10.0 * (cs*1e-3)**2 / (cs*cs)` with cs == 0.0 is 0.0/0.0 in
    /// CPython → `ZeroDivisionError("float division by zero")`, raised by
    /// the reference BEFORE any per-device arithmetic (even with no
    /// devices).
    DivisionByZero,
}

/// Checked floor/ceil-then-truncate, matching `int(np.floor(x))` /
/// `int(np.ceil(x))`: NaN raises ValueError and ±inf raises
/// OverflowError exactly like CPython, instead of Rust's saturating
/// `as i64` cast (NaN→0, ±inf→i64::MAX/MIN).
fn checked_int_floor(v: f64) -> Result<i64, BuildHFieldError> {
    if v.is_nan() {
        return Err(BuildHFieldError::NanToInt);
    }
    if v.is_infinite() {
        return Err(BuildHFieldError::InfToInt);
    }
    Ok(v.floor() as i64)
}

fn checked_int_ceil(v: f64) -> Result<i64, BuildHFieldError> {
    if v.is_nan() {
        return Err(BuildHFieldError::NanToInt);
    }
    if v.is_infinite() {
        return Err(BuildHFieldError::InfToInt);
    }
    Ok(v.ceil() as i64)
}

/// Build the per-cell vertical conductance field `(H, W)` in
/// W/(K·mm²).  Mirrors `build_h_field`'s grid arithmetic verbatim:
///
/// - `cell_area_m2 = pow(cs * 1e-3, 2.0)` (host libm — B1);
///   `h_bg = (10.0 * cell_area_m2) / (cs * cs)` (B7); the field starts
///   filled with `h_bg` (matching `np.full`).
/// - Per device (in the given order): footprint bbox from
///   `max(0, floor((x - half_f - ox)/cs))` / `min(w, ceil((x + half_f -
///   ox)/cs))` (and the same for rows with `oy`); `n_cells = max(1,
///   (row_max - row_min) * (col_max - col_min))`;
///   `h_cell = g_dev / ((n_cells * cs) * cs)` with
///   `g_dev = 1.0 / (r_cs + r_sa)`; the bbox cells get `+= h_cell`.
/// - Devices with `r_cs + r_sa <= 0.0` are skipped (the reference's
///   `continue` for board-heatsinked devices).
///
/// Returns the `(height_cells * width_cells)` float64 field as
/// little-endian bytes.
///
/// # Errors
///
/// Returns [`BuildHFieldError`] for the same degenerate inputs that make
/// the reference raise: NaN or ±inf values reaching the int conversions
/// (NaN centroids/origin, ±inf centroids), or `cs == 0.0` (the
/// reference's 0.0/0.0 background division raises first).
///
/// # Arguments
///
/// * `cell_size_mm`, `origin_x`, `origin_y`, `height_cells`,
///   `width_cells` — FDM grid geometry (from `ThermalFDMConfig`).
/// * `xs`, `ys` — device centroid coordinates (mm), caller's dict
///   iteration order.
/// * `r_cs`, `r_sa` — per-device `R_theta_cs` / `R_theta_sa` (K/W),
///   parallel to `xs`/`ys`.  The Python shim has already validated that
///   every device has a `DeviceThermalConfig`.
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python reference signature; a config struct would change the FFI"
)]
pub fn build_h_field(
    cell_size_mm: f64,
    origin_x: f64,
    origin_y: f64,
    height_cells: usize,
    width_cells: usize,
    xs: &[f64],
    ys: &[f64],
    r_cs: &[f64],
    r_sa: &[f64],
) -> Result<Vec<f64>, BuildHFieldError> {
    let cs = cell_size_mm;
    let ox = origin_x;
    let oy = origin_y;
    let h = height_cells;
    let w = width_cells;

    // `h_bg = (10.0 * cell_area_m2) / (cs * cs)` — with cs == 0.0 the
    // reference's CPython float division is 0.0/0.0 → ZeroDivisionError,
    // raised before any per-device arithmetic.  Rust IEEE division would
    // silently produce NaN; replicate the reference's raise.
    if cs == 0.0 {
        return Err(BuildHFieldError::DivisionByZero);
    }

    // Background convection (uniform).  `(cs * 1e-3) ** 2` is host
    // libm pow (B1); `h_bg = (10.0 * cell_area_m2) / (cs * cs)` is the
    // reference's left-to-right chain (B7).
    let cell_area_m2 = hostmath::pow(cs * 1e-3, 2.0);
    let h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs);

    let mut field = vec![h_bg; h * w];

    let half_f = DEVICE_FOOTPRINT_MM / 2.0;

    for i in 0..xs.len() {
        let (dx_mm, dy_mm) = (xs[i], ys[i]);
        // R_vert = R_theta_cs + R_theta_sa (reference addition order);
        // R_vert <= 0 (board-heatsinked) → skip the device.
        let r_vert = r_cs[i] + r_sa[i];
        if r_vert <= 0.0 {
            continue;
        }
        let g_dev = 1.0 / r_vert;

        // Footprint bounding box in grid coordinates — the reference
        // computes `col_min = max(0, int(np.floor(...)))` and
        // `col_max = min(w, int(np.ceil(...)))` (floor/ceil then
        // truncate toward zero, identical to `as i64` for finite values,
        // with the int() raise on NaN/±inf replicated above), THEN numpy
        // reinterprets a NEGATIVE slice stop as `dim + stop` (e.g.
        // `a[:, 0:-3]` on a width-4 grid covers columns [0, 1)) —
        // measured 2026-08-04.  `n_cells` is computed from the RAW
        // post-clamp values BEFORE the numpy reinterpretation, exactly
        // like the reference.
        let col_min = 0i64.max(checked_int_floor((dx_mm - half_f - ox) / cs)?);
        let col_max_raw = (w as i64).min(checked_int_ceil((dx_mm + half_f - ox) / cs)?);
        let row_min = 0i64.max(checked_int_floor((dy_mm - half_f - oy) / cs)?);
        let row_max_raw = (h as i64).min(checked_int_ceil((dy_mm + half_f - oy) / cs)?);

        // `n_cells = max(1, (row_max_raw - row_min) * (col_max_raw -
        // col_min))` — computed from the RAW post-clamp values exactly
        // like the reference (i128 so an extreme negative product can
        // never overflow; Python ints are unbounded).  A negative
        // product selects the `1` arm, matching `max(1, x)`.
        let raw_product = (row_max_raw - row_min) as i128 * (col_max_raw - col_min) as i128;
        let n_cells = if raw_product <= 0 { 1usize } else { raw_product as usize };
        // g_dev / (n_cells * cs * cs) — left-to-right, n_cells widened
        // to f64 (Python int * float) (B7).
        let h_cell = g_dev / ((n_cells as f64) * cs * cs);

        // numpy slice-stop reinterpretation: a negative stop wraps as
        // `dim + stop` (clamped to >= 0 → empty when stop < -dim); a
        // start >= stop (or >= dim) yields an empty slice → no-op.
        let col_max_eff = if col_max_raw < 0 {
            ((w as i64) + col_max_raw).max(0) as usize
        } else {
            col_max_raw as usize
        };
        let row_max_eff = if row_max_raw < 0 {
            ((h as i64) + row_max_raw).max(0) as usize
        } else {
            row_max_raw as usize
        };
        let (col_min_eff, row_min_eff) = (col_min as usize, row_min as usize);

        if col_min_eff >= col_max_eff || row_min_eff >= row_max_eff {
            continue; // numpy empty slice — no accumulation
        }

        for r in row_min_eff..row_max_eff {
            for c in col_min_eff..col_max_eff {
                field[r * w + c] += h_cell;
            }
        }
    }

    Ok(field)
}

/// pyo3 bridge for [`build_h_field`].  Maps [`BuildHFieldError`] to the
/// reference's CPython exceptions (ValueError / OverflowError /
/// ZeroDivisionError) with the reference's message text.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (cell_size_mm, origin_x, origin_y, height_cells, width_cells, xs, ys, r_cs, r_sa))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python reference signature"
)]
pub fn build_h_field_py(
    py: Python<'_>,
    cell_size_mm: f64,
    origin_x: f64,
    origin_y: f64,
    height_cells: usize,
    width_cells: usize,
    xs: Vec<f64>,
    ys: Vec<f64>,
    r_cs: Vec<f64>,
    r_sa: Vec<f64>,
) -> PyResult<Bound<'_, PyBytes>> {
    let field = match temper_py_bridge::catch_unwind(|| {
        build_h_field(
            cell_size_mm,
            origin_x,
            origin_y,
            height_cells,
            width_cells,
            &xs,
            &ys,
            &r_cs,
            &r_sa,
        )
    }) {
        Ok(Ok(field)) => field,
        Ok(Err(BuildHFieldError::NanToInt)) => {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "cannot convert float NaN to integer",
            ))
        }
        Ok(Err(BuildHFieldError::InfToInt)) => {
            return Err(pyo3::exceptions::PyOverflowError::new_err(
                "cannot convert float infinity to integer",
            ))
        }
        Ok(Err(BuildHFieldError::DivisionByZero)) => {
            return Err(pyo3::exceptions::PyZeroDivisionError::new_err(
                "float division by zero",
            ))
        }
        Err(e) => return Err(temper_py_bridge::panic_to_err(e)),
    };
    let mut out = Vec::with_capacity(field.len() * 8);
    for v in field {
        out.extend_from_slice(&v.to_le_bytes());
    }
    PyBytes::new_with(py, out.len(), |b| {
        b.copy_from_slice(&out);
        Ok(())
    })
}

#[cfg(test)]
mod tests {
    // The crate denies `unwrap`/`expect` in production code (Cargo.toml
    // `[lints.clippy]`); a failing unwrap in a test IS the test failure,
    // which is the documented carve-out in the Wave-4 G7 bar.
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::*;

    #[test]
    fn empty_devices_background_only() {
        let f = build_h_field(1.0, 0.0, 0.0, 4, 4, &[], &[], &[], &[]).unwrap();
        // h_bg = 10.0 * pow(1e-3, 2.0) / (1.0 * 1.0) = 10.0 * 1e-6 = 1e-5
        assert_eq!(f.len(), 16);
        // h_bg = 10.0 * pow(1e-3, 2.0) / (1.0*1.0) — NOT exactly 1e-5
        // in f64 (9.999999999999999e-06); compute the reference value.
        let h_bg = 10.0 * (1e-3f64).powi(2) / (1.0 * 1.0);
        assert!(f.iter().all(|&v| v == h_bg));
    }

    #[test]
    fn device_sink_accumulates() {
        // One device at the centre of a 4x4 grid, cs=1, origin (0,0),
        // footprint 5x5 → covers the whole 4x4 grid (16 cells).
        let f = build_h_field(1.0, 0.0, 0.0, 4, 4, &[2.0], &[2.0], &[0.25], &[1.0]).unwrap();
        let g_dev = 1.0 / (0.25 + 1.0);
        let h_cell = g_dev / (16.0 * 1.0 * 1.0);
        let h_bg = 10.0 * (1e-3f64).powi(2) / (1.0 * 1.0);
        assert!(f.iter().all(|&v| (v - (h_bg + h_cell)).abs() < 1e-18));
    }

    #[test]
    fn board_heatsinked_device_skipped() {
        // R_vert = 0 → skip; the cell keeps only the background value.
        let h_bg = 10.0 * (1e-3f64).powi(2) / (1.0 * 1.0);
        let f = build_h_field(1.0, 0.0, 0.0, 4, 4, &[2.0], &[2.0], &[0.0], &[0.0]).unwrap();
        assert!(f.iter().all(|&v| v == h_bg));
    }

    #[test]
    fn off_grid_footprint_is_noop() {
        let h_bg = 10.0 * (1e-3f64).powi(2) / (1.0 * 1.0);
        let f = build_h_field(1.0, 0.0, 0.0, 4, 4, &[-100.0], &[-100.0], &[0.25], &[1.0]).unwrap();
        assert!(f.iter().all(|&v| v == h_bg));
    }

    #[test]
    fn overlapping_footprints_accumulate() {
        // Two devices whose footprints overlap the same cells; both
        // h_cells accumulate per cell.
        let f = build_h_field(1.0, 0.0, 0.0, 4, 4, &[1.0, 2.0], &[1.0, 2.0], &[0.25, 0.5], &[1.0, 1.0]).unwrap();
        let g1 = 1.0 / 1.25;
        let g2 = 1.0 / 1.5;
        // device 1 footprint: x in [2.5-2.5, 2.5+2.5] → [0, 5] → cols 0..4;
        // y same → rows 0..4 → 16 cells.  device 2: x in [2.5-1.0... no:
        // 2.0 ± 2.5 → [-0.5, 4.5] → cols 0..4; rows 0..4 → 16 cells.
        let h1 = g1 / (16.0 * 1.0);
        let h2 = g2 / (16.0 * 1.0);
        assert!(f.iter().all(|&v| (v - (1e-5 + h1 + h2)).abs() < 1e-18));
    }

    #[test]
    fn degenerate_inputs_raise_like_cpython() {
        // int(np.floor(NaN)) → ValueError; int(np.floor(±inf)) →
        // OverflowError; cs=0.0 → the reference's 0.0/0.0 background
        // division → ZeroDivisionError.  Rust `as i64` would saturate;
        // the checked conversions must reject.
        assert_eq!(
            build_h_field(1.0, 0.0, 0.0, 4, 4, &[f64::NAN], &[1.0], &[0.25], &[1.0]),
            Err(BuildHFieldError::NanToInt)
        );
        assert_eq!(
            build_h_field(1.0, 0.0, 0.0, 4, 4, &[f64::INFINITY], &[1.0], &[0.25], &[1.0]),
            Err(BuildHFieldError::InfToInt)
        );
        assert_eq!(
            build_h_field(1.0, 0.0, f64::NAN, 4, 4, &[1.0], &[1.0], &[0.25], &[1.0]),
            Err(BuildHFieldError::NanToInt)
        );
        assert_eq!(
            build_h_field(0.0, 0.0, 0.0, 4, 4, &[], &[], &[], &[]),
            Err(BuildHFieldError::DivisionByZero)
        );
    }
}

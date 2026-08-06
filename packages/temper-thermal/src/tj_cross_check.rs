//! T_j cross-check kernels (Wave 4, Phase 4).
//!
//! Ports the closed-form scalar arithmetic of
//! `temper_placer/physics/tj_cross_check.py` (U11 — the datasheet-R_θ
//! lumped-network cross-check: `_distance_to_heatsink_edge` and the
//! per-device `T_j_fdm` / `T_j_lumped` / `delta` / conservative-`T_j` /
//! margin / exceeds chains) to Rust.  The Python module keeps its
//! public API (`TjCrossCheckGate`, the FDM-solve orchestration, the
//! `Violation` construction, `_classify_disagreement`'s prose) and
//! `_area_average_temperature`'s `np.mean` call (numpy's SIMD
//! reduction is not bit-reproducible — measured 2026-08-04; that call
//! stays Python, argued in-source like the KTD9 spsolve boundary);
//! the scalar arithmetic delegates here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B7 (f64 operation order):** `R_total = R_jc + R_cs + R_sa`
//!   (left-to-right); `T_j_fdm = T_case_fdm + power * R_jc`;
//!   `T_j_lumped = T_amb + (power * R_total)`; `delta = abs(T_j_fdm -
//!   T_j_lumped)`; `margin = T_j_max - conservative`;
//!   `exceeds = delta > tau`.  `H = height_cells * cell_size` /
//!   `W = width_cells * cell_size` (int * float widened exactly like
//!   Python), `abs(oy + H - y)` etc.
//! - **Python max/min semantics:** `conservative_T_j = max(T_j_fdm,
//!   T_j_lumped)` is CPython's two-arg max (`a` unless `b > a` — NaN
//!   in the FIRST argument wins: `max(nan, 1.0) = nan`, `max(1.0,
//!   nan) = 1.0`, measured 2026-08-04); NOT `f64::max` (which
//!   discards NaN).
//!
//! R24 (physics-gated): this gate is a CP-SAT *gate* but not a
//! constraint encoder — it compares two independent models' T_j
//! estimates against a datasheet ceiling (fail-closed).  The
//! soundness argument (conservative-max gating, never the optimistic
//! estimate) is documented in VERIFICATION.md; the kernels pin the
//! arithmetic bit-exactly.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Heatsink-edge codes (same convention as fdm/thermal_potential):
/// TOP=0, BOTTOM=1, LEFT=2, RIGHT=3; any other = no edge → 0.0.
pub(crate) const EDGE_TOP: i64 = 0;
pub(crate) const EDGE_BOTTOM: i64 = 1;
pub(crate) const EDGE_LEFT: i64 = 2;
pub(crate) const EDGE_RIGHT: i64 = 3;

/// Distance from a device centroid to the heatsink edge (mm).  Mirrors
/// `_distance_to_heatsink_edge` verbatim: `H = height_cells * cell`,
/// `W = width_cells * cell`; TOP → `abs(oy + H - y)`, BOTTOM →
/// `abs(y - oy)`, LEFT → `abs(x - ox)`, RIGHT → `abs(ox + W - x)`,
/// unknown edge → `0.0`.
#[allow(clippy::too_many_arguments)]
pub fn distance_to_heatsink_edge(
    x: f64,
    y: f64,
    ox: f64,
    oy: f64,
    cell_size: f64,
    height_cells: usize,
    width_cells: usize,
    edge_code: i64,
) -> f64 {
    let h = height_cells as f64 * cell_size;
    let w = width_cells as f64 * cell_size;
    match edge_code {
        EDGE_TOP => (oy + h - y).abs(),
        EDGE_BOTTOM => (y - oy).abs(),
        EDGE_LEFT => (x - ox).abs(),
        EDGE_RIGHT => (ox + w - x).abs(),
        _ => 0.0,
    }
}

/// Per-device cross-check scalars.  Mirrors `TjCrossCheckGate.check`'s
/// per-device arithmetic verbatim:
///
/// - `t_j_fdm = t_case_fdm + power * r_jc`;
/// - `r_total = r_jc + r_cs + r_sa` (left-to-right);
/// - `t_j_lumped = t_amb + power * r_total`;
/// - `delta = abs(t_j_fdm - t_j_lumped)`;
/// - `conservative = max(t_j_fdm, t_j_lumped)` (CPython two-arg max);
/// - `margin = t_j_max - conservative`;
/// - `exceeds = delta > tau`.
///
/// Returns `(t_j_fdm, t_j_lumped, delta, conservative, margin,
/// exceeds)`.
#[allow(clippy::too_many_arguments)]
pub fn device_cross_check(
    t_case_fdm: f64,
    power: f64,
    r_jc: f64,
    r_cs: f64,
    r_sa: f64,
    t_amb: f64,
    t_j_max: f64,
    tau: f64,
) -> (f64, f64, f64, f64, f64, bool) {
    let t_j_fdm = t_case_fdm + power * r_jc;
    let r_total = r_jc + r_cs + r_sa;
    let t_j_lumped = t_amb + power * r_total;
    let delta = (t_j_fdm - t_j_lumped).abs();
    // CPython two-arg max: a unless b > a (NaN in the first argument
    // wins — measured 2026-08-04).  NOT f64::max.
    let conservative = if t_j_lumped > t_j_fdm { t_j_lumped } else { t_j_fdm };
    let margin = t_j_max - conservative;
    let exceeds = delta > tau;
    (t_j_fdm, t_j_lumped, delta, conservative, margin, exceeds)
}

/// pyo3 bridge for [`distance_to_heatsink_edge`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x, y, ox, oy, cell_size, height_cells, width_cells, edge_code))]
#[allow(clippy::too_many_arguments)]
pub fn distance_to_heatsink_edge_py(
    x: f64,
    y: f64,
    ox: f64,
    oy: f64,
    cell_size: f64,
    height_cells: usize,
    width_cells: usize,
    edge_code: i64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        distance_to_heatsink_edge(x, y, ox, oy, cell_size, height_cells, width_cells, edge_code)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`device_cross_check`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (t_case_fdm, power, r_jc, r_cs, r_sa, t_amb, t_j_max, tau))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python reference signature"
)]
pub fn device_cross_check_py(
    t_case_fdm: f64,
    power: f64,
    r_jc: f64,
    r_cs: f64,
    r_sa: f64,
    t_amb: f64,
    t_j_max: f64,
    tau: f64,
) -> PyResult<(f64, f64, f64, f64, f64, bool)> {
    temper_py_bridge::catch_unwind(|| {
        device_cross_check(t_case_fdm, power, r_jc, r_cs, r_sa, t_amb, t_j_max, tau)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distance_known_values() {
        // 20x20 grid, cs=1, origin (0,0): TOP edge at y=20, device at
        // (5, 3) → distance 17.
        assert_eq!(distance_to_heatsink_edge(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, EDGE_TOP), 17.0);
        assert_eq!(distance_to_heatsink_edge(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, EDGE_BOTTOM), 3.0);
        assert_eq!(distance_to_heatsink_edge(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, EDGE_LEFT), 5.0);
        assert_eq!(distance_to_heatsink_edge(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, EDGE_RIGHT), 15.0);
        assert_eq!(distance_to_heatsink_edge(5.0, 3.0, 0.0, 0.0, 1.0, 20, 20, 99), 0.0);
    }

    #[test]
    fn device_cross_check_known() {
        // T_case=50, P=5, R_jc=0.6, R_cs=0.25, R_sa=1.0, T_amb=40,
        // T_j_max=150, tau=5 → T_j_fdm=53, R_total=1.85,
        // T_j_lumped=49.25, delta=3.75, conservative=53, margin=97.
        let (f, l, d, c, m, e) = device_cross_check(50.0, 5.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0);
        assert_eq!(f, 53.0);
        assert_eq!(l, 49.25);
        assert_eq!(d, 3.75);
        assert_eq!(c, 53.0);
        assert_eq!(m, 97.0);
        assert!(!e);
    }

    #[test]
    fn conservative_max_nan_first_wins() {
        // max(nan, x) = nan (CPython first-arg wins) — NOT f64::max.
        let (_, _, _, c, _, _) = device_cross_check(f64::NAN, 5.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0);
        assert!(c.is_nan());
        // max(x, nan) = x — NaN in the SECOND argument (a NaN R_sa
        // poisons only the lumped estimate) is discarded, keeping the
        // FDM estimate.
        let (_, _, _, c, _, _) = device_cross_check(50.0, 5.0, 0.6, 0.25, f64::NAN, 40.0, 150.0, 5.0);
        assert!(!c.is_nan());
        assert_eq!(c, 53.0);
    }
}

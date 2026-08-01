//! SPICE post-processing estimators (Wave 2, SPICE slice).
//!
//! Python reference: `temper_placer/validation/spice.py`
//! (`estimate_loop_inductance`, `_infer_unit`). The loop-inductance
//! estimator (shoelace area + mu_0 * A / h) and the measurement-unit
//! classifier are pure functions of their inputs; the Python wrapper
//! keeps the component-ref resolution and the <3-components / missing-
//! ref early returns.
//!
//! Bit-exactness: identical f64 operation order (shoelace accumulation,
//! `mu_0 * area_m2 / h_m` left-to-right, the unit thresholds).

use pyo3::prelude::*;
use temper_py_bridge;

/// Estimate loop inductance from resolved component positions (mm).
/// Mirrors `estimate_loop_inductance`'s arithmetic exactly for n >= 3
/// positions (the wrapper handles the early returns).
fn loop_inductance(positions: &[(f64, f64)], trace_height_mm: f64) -> f64 {
    let n = positions.len();
    let mut area = 0.0f64;
    for i in 0..n {
        let (x1, y1) = positions[i];
        let (x2, y2) = positions[(i + 1) % n];
        area += x1 * y2 - x2 * y1;
    }
    let area = area.abs() / 2.0; // mm^2
    let area_m2 = area * 1e-6;
    let mu_0 = 4.0 * 3.14159265359e-7;
    let h_m = trace_height_mm * 1e-3;
    mu_0 * area_m2 / h_m
}

/// Infer the measurement unit from the name and value — mirrors
/// `_infer_unit` (same substring sets, same thresholds, same order).
fn infer_unit(name: &str, value: f64) -> String {
    let name_lower = name.to_lowercase();

    if ["time", "trise", "tfall", "delay", "period"]
        .iter()
        .any(|x| name_lower.contains(x))
    {
        let av = value.abs();
        return if av < 1e-9 {
            "ps"
        } else if av < 1e-6 {
            "ns"
        } else if av < 1e-3 {
            "us"
        } else {
            "s"
        }
        .to_string();
    }

    if ["v_", "vce", "vgs", "vout", "vin", "voltage"]
        .iter()
        .any(|x| name_lower.contains(x))
    {
        return "V".to_string();
    }

    if ["i_", "iout", "iin", "current"]
        .iter()
        .any(|x| name_lower.contains(x))
    {
        return if value.abs() < 1e-3 { "mA" } else { "A" }.to_string();
    }

    if ["e_", "eoff", "eon", "energy"]
        .iter()
        .any(|x| name_lower.contains(x))
    {
        let av = value.abs();
        return if av < 1e-6 {
            "uJ"
        } else if av < 1e-3 {
            "mJ"
        } else {
            "J"
        }
        .to_string();
    }

    if ["p_", "power", "pout", "pin"]
        .iter()
        .any(|x| name_lower.contains(x))
    {
        return "W".to_string();
    }

    String::new()
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (positions, trace_height_mm))]
pub fn spice_loop_inductance_py(
    _py: Python<'_>,
    positions: Vec<(f64, f64)>,
    trace_height_mm: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| loop_inductance(&positions, trace_height_mm))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[pyo3(signature = (name, value))]
pub fn spice_infer_unit_py(name: &str, value: f64) -> String {
    infer_unit(name, value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_loop_inductance_square() {
        // A 10x10 mm square loop at 0.035 mm height:
        // area = 100 mm^2 = 1e-4 m^2; L = 4pi e-7 * 1e-4 / 3.5e-5 = 3.59e-6 H
        let positions = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        let l = loop_inductance(&positions, 0.035);
        assert!((l - 4.0 * 3.14159265359e-7 * 1e-4 / 3.5e-5).abs() < 1e-12);
    }

    #[test]
    fn test_loop_inductance_order_dependent_area() {
        // Reversing the vertex order flips the signed shoelace sum but the
        // abs makes the area (and inductance) identical.
        let a = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        let mut b = a.clone();
        b.reverse();
        assert_eq!(loop_inductance(&a, 0.035), loop_inductance(&b, 0.035));
    }

    #[test]
    fn test_infer_unit_time_and_voltage() {
        assert_eq!(infer_unit("trise_time", 5e-11), "ps");
        assert_eq!(infer_unit("tfall_time", 5e-9), "ns");
        assert_eq!(infer_unit("period_time", 5e-6), "us");
        assert_eq!(infer_unit("delay_time", 5e-3), "s");
        assert_eq!(infer_unit("v_out", 1.0), "V");
    }

    #[test]
    fn test_infer_unit_current_energy_power() {
        assert_eq!(infer_unit("i_out", 0.0005), "mA");
        assert_eq!(infer_unit("i_out", 0.5), "A");
        assert_eq!(infer_unit("e_on", 1e-8), "uJ");
        assert_eq!(infer_unit("e_off", 1e-5), "mJ");
        assert_eq!(infer_unit("energy_total", 0.5), "J");
        assert_eq!(infer_unit("p_out", 12.0), "W");
        assert_eq!(infer_unit("unknown_meas", 1.0), "");
    }
}

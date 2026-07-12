use pyo3::prelude::*;
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// IPC-2221 trace current capacity
// ---------------------------------------------------------------------------

/// Calculate maximum current capacity using IPC-2221 formula.
///
/// I = k * ΔT^0.44 * A^0.725  where A is cross-sectional area in mils².
#[pyfunction]
fn estimate_trace_current(
    width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = thickness_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k = if internal_layer { 0.024 } else { 0.048 };
    Ok(k * temp_rise_c.powf(0.44) * area_mils2.powf(0.725))
}

/// Conservative current estimate (internal layer, 1oz, 10°C rise).
#[pyfunction]
fn estimate_current_from_net_class(
    trace_width_mm: f64,
    thickness_oz: f64,
    temp_rise_c: f64,
) -> PyResult<f64> {
    estimate_trace_current(trace_width_mm, thickness_oz, temp_rise_c, true)
}

/// Pre-computed lookup table for 1oz copper, 10°C rise, internal layers.
#[pyfunction]
fn trace_current_table_1oz() -> PyResult<HashMap<String, f64>> {
    let mut map = HashMap::new();
    map.insert("0.15".into(), 0.7);
    map.insert("0.2".into(), 1.0);
    map.insert("0.25".into(), 1.2);
    map.insert("0.4".into(), 2.0);
    map.insert("0.5".into(), 2.5);
    map.insert("1.0".into(), 5.0);
    map.insert("2.0".into(), 9.5);
    map.insert("3.0".into(), 14.0);
    map.insert("5.0".into(), 22.0);
    map.insert("10.0".into(), 42.0);
    Ok(map)
}

// ---------------------------------------------------------------------------
// IPC-2152 minimum trace width (inverse of 2221)
// ---------------------------------------------------------------------------

/// Calculate minimum trace width for a given current using IPC-2152.
///
/// width_mm = f(current_amps, copper_weight_oz, temp_rise_c, internal_layer)
#[pyfunction]
fn calculate_min_trace_width(
    current_amps: f64,
    copper_weight_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    let k = if internal_layer { 0.024 } else { 0.048 };
    let area_mils2 = (current_amps / (k * temp_rise_c.powf(0.44))).powf(1.0 / 0.725);
    let thickness_mils = copper_weight_oz * 1.37;
    let width_mils = area_mils2 / thickness_mils;
    Ok(width_mils / 39.3701)
}

#[pymodule]
fn temper_ipc(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_trace_current, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_current_from_net_class, m)?)?;
    m.add_function(wrap_pyfunction!(trace_current_table_1oz, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_min_trace_width, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_estimate_external_1oz_10c() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, false).unwrap();
        assert!(i > 1.0, "external 0.25mm should carry >1A");
    }

    #[test]
    fn test_estimate_internal_conservative() {
        let i = estimate_trace_current(0.25, 1.0, 10.0, true).unwrap();
        assert!(i > 0.5, "internal 0.25mm should carry >0.5A");
    }

    #[test]
    fn test_estimate_from_net_class() {
        let i = estimate_current_from_net_class(0.25, 1.0, 10.0).unwrap();
        assert_eq!(i, estimate_trace_current(0.25, 1.0, 10.0, true).unwrap());
    }

    #[test]
    fn test_table_lookup() {
        let table = trace_current_table_1oz().unwrap();
        assert_eq!(table["0.25"], 1.2);
        assert_eq!(table["10.0"], 42.0);
    }

    #[test]
    fn test_min_trace_width_roundtrip() {
        // Width → current → width should be approximately identity
        let width = 1.0;
        let current = estimate_trace_current(width, 1.0, 10.0, true).unwrap();
        let width2 = calculate_min_trace_width(current, 1.0, 10.0, true).unwrap();
        assert!((width - width2).abs() < 0.05, "round-trip error: {width} vs {width2}");
    }
}

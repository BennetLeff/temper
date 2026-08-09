// Wave 4, spatial-tier-2 unit: `router_v6/bottleneck_analysis.py`'s two
// compute kernels — the `_classify_severity` capacity/demand classification
// and the `identify_bottlenecks` per-layer aggregation.
//
// Both are integer-driven: capacity and demand are `int`, and the only
// float arithmetic is (a) the utilization `demand_per_layer /
// capacity.estimated_traces` — an IEEE f64 division of two exactly
// representable non-negative integers, identical in CPython and Rust —
// and (b) the severity `ratio = capacity / demand` inside
// `_classify_severity` — the same division, or `float("inf")` when
// `demand == 0`.  The `//` floor division that derives `demand_per_layer`
// is replicated with `i64::div_euclid` (Python `//` is floor division;
// Rust `/` truncates toward zero, so the two agree only for non-negative
// operands — `div_euclid` agrees for all).
//
// The `Bottleneck` / `BottleneckAnalysis` dataclasses, the
// `BottleneckSeverity` enum, the `LayerCapacity` / `RoutingDemand`
// object access, and the Stage / validator orchestration all stay in
// Python; this module is the numeric core.
//
// Severity names returned are the enum *values* ("none" / "low" /
// "medium" / "high" / "critical"); the Python shim maps them back onto
// `BottleneckSeverity`.

/// `_classify_severity(capacity, demand)` — returns the severity value.
pub fn classify_severity(capacity: i64, demand: i64) -> &'static str {
    if capacity == 0 {
        if demand > 0 {
            return "critical";
        }
        return "none";
    }
    let ratio = if demand > 0 {
        capacity as f64 / demand as f64
    } else {
        f64::INFINITY
    };
    if ratio < 0.5 {
        "critical"
    } else if ratio < 1.0 {
        "high"
    } else if ratio < 1.2 {
        "medium"
    } else if ratio < 2.0 {
        "low"
    } else {
        "none"
    }
}

/// One layer's `identify_bottlenecks` output row.
pub struct BottleneckRow {
    pub utilization: f64,
    pub severity: &'static str,
}

/// The aggregation core of `identify_bottlenecks`: `traces` holds each
/// layer's `capacity.estimated_traces` in dict iteration order.
pub fn identify_bottlenecks_kernel(
    traces: &[i64],
    total_demand: i64,
) -> (i64, i64, Vec<BottleneckRow>) {
    let num_layers = traces.len();
    let demand_per_layer = if num_layers > 0 {
        total_demand.div_euclid(num_layers as i64)
    } else {
        0
    };
    let mut total_capacity: i64 = 0;
    let mut rows = Vec::with_capacity(num_layers);
    for &cap in traces {
        total_capacity += cap;
        let utilization = if cap > 0 {
            demand_per_layer as f64 / cap as f64
        } else {
            f64::INFINITY
        };
        rows.push(BottleneckRow {
            utilization,
            severity: classify_severity(cap, demand_per_layer),
        });
    }
    (total_capacity, demand_per_layer, rows)
}

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 surface for `classify_severity`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn classify_severity_py(capacity: i64, demand: i64) -> PyResult<String> {
    temper_py_bridge::catch_unwind(move || classify_severity(capacity, demand).to_string())
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 surface for `identify_bottlenecks_kernel`.
#[cfg(feature = "python")]
#[pyfunction]
pub fn identify_bottlenecks_py(
    traces: Vec<i64>,
    total_demand: i64,
) -> PyResult<(i64, i64, Vec<f64>, Vec<String>)> {
    temper_py_bridge::catch_unwind(move || {
        let (total_capacity, demand_per_layer, rows) =
            identify_bottlenecks_kernel(&traces, total_demand);
        let utilizations: Vec<f64> = rows.iter().map(|r| r.utilization).collect();
        let severities: Vec<String> = rows.iter().map(|r| r.severity.to_string()).collect();
        (total_capacity, demand_per_layer, utilizations, severities)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(classify_severity_py, m)?)?;
    m.add_function(wrap_pyfunction!(identify_bottlenecks_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn severity_edge_matrix() {
        assert_eq!(classify_severity(0, 0), "none");
        assert_eq!(classify_severity(0, 1), "critical");
        assert_eq!(classify_severity(1, 1), "medium"); // ratio 1.0
        assert_eq!(classify_severity(5, 10), "high"); // 0.5 -> 0.5<0.5 false
        assert_eq!(classify_severity(6, 10), "high"); // 0.6
        assert_eq!(classify_severity(10, 10), "medium"); // 1.0
        assert_eq!(classify_severity(11, 10), "medium"); // 1.1
        assert_eq!(classify_severity(12, 10), "low"); // 1.2 -> 1.2<1.2 false
        assert_eq!(classify_severity(19, 10), "low"); // 1.9
        assert_eq!(classify_severity(20, 10), "none"); // 2.0
        assert_eq!(classify_severity(100, 0), "none"); // inf ratio
    }

    #[test]
    fn aggregation_math() {
        let (total, dpl, rows) = identify_bottlenecks_kernel(&[100, 50, 0], 120);
        assert_eq!(total, 150);
        assert_eq!(dpl, 40); // 120 // 3
        assert_eq!(rows[0].utilization, 0.4);
        // ratio 100/40 = 2.5 -> not < 2.0 -> none
        assert_eq!(rows[0].severity, "none");
        assert_eq!(rows[1].utilization, 0.8);
        // ratio 50/40 = 1.25 -> not < 1.2, but < 2.0 -> low
        assert_eq!(rows[1].severity, "low");
        assert_eq!(rows[2].utilization, f64::INFINITY);
        assert_eq!(rows[2].severity, "critical");
    }

    #[test]
    fn empty_and_zero_demand() {
        let (total, dpl, rows) = identify_bottlenecks_kernel(&[], 120);
        assert_eq!((total, dpl, rows.len()), (0, 0, 0));
        let (total2, dpl2, rows2) = identify_bottlenecks_kernel(&[100, 200], 0);
        assert_eq!((total2, dpl2), (300, 0));
        assert_eq!(rows2[0].utilization, 0.0);
        assert_eq!(rows2[0].severity, "none");
    }

    #[test]
    fn floor_division_for_negative_total_demand() {
        // Python `//` floors: -7 // 3 == -3 (Rust `/` would truncate to -2).
        let (_, dpl, _) = identify_bottlenecks_kernel(&[1, 1, 1], -7);
        assert_eq!(dpl, -3);
    }
}

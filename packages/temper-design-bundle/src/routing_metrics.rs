//! Routing-metrics data model — Wave 4 **Phase 5, batch 2** (deterministic
//! leaf stages).
//!
//! Ports the three dataclasses of
//! `temper_placer/deterministic/stages/routing_metrics.py` to pyo3
//! pyclasses (`SegmentMetrics`, `NetMetrics`, `RoutingMetrics`) with their
//! aggregation compute (`add_net`, `finalize`, `to_dict`, `to_json`) and
//! the two `NetMetrics` properties. The Python module becomes a delegation
//! shim; `print_summary` (I/O) stays Python.
//!
//! The oracle is the verbatim pre-migration module
//! (`tests/deterministic/stages/_routing_metrics_py_oracle.py`); bit-parity
//! is asserted by `test_routing_metrics_rust_differential.py` and the PBT
//! suite; the structural proof lives in `VERIFICATION.md`.
//!
//! Numerical traps pinned here:
//! - **`round(x, ndigits)` is round-half-to-EVEN** (CPython `_Py_double_round`):
//!   `to_dict` rounds `avg_iterations_per_segment` to 1 place and
//!   `total_trace_length_mm`/`total_elapsed_seconds` to 2 places. The kernel
//!   renders with the equivalent format-then-parse (Rust `{:.N}` rounds ties
//!   to even) — NOT `f64::round` (half-away-from-zero).
//! - **`max(x, 1)` for the completion rates**: the denominator is
//!   `x.max(1)` exactly as the oracle's `max(x, 1)`.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use pyo3::IntoPyObjectExt;

/// CPython `round(x, ndigits)` — round-half-to-even on the decimal digits,
/// via format-then-parse (Rust's `{:.N}` rounds ties to even, matching
/// `_Py_double_round`).
fn py_round_digits(x: f64, digits: usize) -> f64 {
    let s = format!("{x:.digits$}");
    s.parse::<f64>().unwrap_or(x)
}

fn opt_float(py: Python<'_>, v: Option<&Bound<'_, PyAny>>, default: f64) -> PyResult<Py<PyAny>> {
    match v {
        Some(x) => Ok(x.clone().unbind()),
        None => Ok(default.into_bound_py_any(py)?.unbind()),
    }
}

fn opt_int(py: Python<'_>, v: Option<&Bound<'_, PyAny>>, default: i64) -> PyResult<Py<PyAny>> {
    match v {
        Some(x) => Ok(x.clone().unbind()),
        None => Ok(default.into_bound_py_any(py)?.unbind()),
    }
}

fn opt_list(py: Python<'_>, v: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match v {
        Some(x) => Ok(x.clone().unbind()),
        None => {
            let list = PyList::empty(py);
            Ok(list.into_any().unbind())
        }
    }
}

fn opt_dict(py: Python<'_>, v: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match v {
        Some(x) => Ok(x.clone().unbind()),
        None => {
            let d = PyDict::new(py);
            Ok(d.into_any().unbind())
        }
    }
}

// ---------------------------------------------------------------------------
// SegmentMetrics
// ---------------------------------------------------------------------------

/// `SegmentMetrics` — 14-field mutable dataclass.
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct SegmentMetrics {
    net_name: Py<PyAny>,
    segment_idx: Py<PyAny>,
    start_pin: Py<PyAny>,
    end_pin: Py<PyAny>,
    distance_mm: Py<PyAny>,
    distance_cells: Py<PyAny>,
    success: Py<PyAny>,
    method: Py<PyAny>,
    iterations_used: Py<PyAny>,
    iterations_limit: Py<PyAny>,
    timeout: Py<PyAny>,
    path_length_mm: Py<PyAny>,
    via_count: Py<PyAny>,
    layers_used: Py<PyAny>,
}

#[pymethods]
impl SegmentMetrics {
    #[new]
    #[pyo3(signature = (
        net_name, segment_idx, start_pin, end_pin, distance_mm, distance_cells,
        success, method, iterations_used, iterations_limit, timeout,
        path_length_mm=None, via_count=None, layers_used=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        net_name: &Bound<'_, PyAny>,
        segment_idx: &Bound<'_, PyAny>,
        start_pin: &Bound<'_, PyAny>,
        end_pin: &Bound<'_, PyAny>,
        distance_mm: &Bound<'_, PyAny>,
        distance_cells: &Bound<'_, PyAny>,
        success: &Bound<'_, PyAny>,
        method: &Bound<'_, PyAny>,
        iterations_used: &Bound<'_, PyAny>,
        iterations_limit: &Bound<'_, PyAny>,
        timeout: &Bound<'_, PyAny>,
        path_length_mm: Option<&Bound<'_, PyAny>>,
        via_count: Option<&Bound<'_, PyAny>>,
        layers_used: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let layers_used = match layers_used {
            Some(v) => v.clone().unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        Ok(SegmentMetrics {
            net_name: net_name.clone().unbind(),
            segment_idx: segment_idx.clone().unbind(),
            start_pin: start_pin.clone().unbind(),
            end_pin: end_pin.clone().unbind(),
            distance_mm: distance_mm.clone().unbind(),
            distance_cells: distance_cells.clone().unbind(),
            success: success.clone().unbind(),
            method: method.clone().unbind(),
            iterations_used: iterations_used.clone().unbind(),
            iterations_limit: iterations_limit.clone().unbind(),
            timeout: timeout.clone().unbind(),
            path_length_mm: opt_float(py, path_length_mm, 0.0)?,
            via_count: opt_int(py, via_count, 0)?,
            layers_used,
        })
    }

    #[getter]
    fn net_name(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_name.clone_ref(py)
    }
    #[setter]
    fn set_net_name(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_name = v.into_any().unbind();
    }

    #[getter]
    fn segment_idx(&self, py: Python<'_>) -> Py<PyAny> {
        self.segment_idx.clone_ref(py)
    }
    #[setter]
    fn set_segment_idx(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segment_idx = v.into_any().unbind();
    }

    #[getter]
    fn start_pin(&self, py: Python<'_>) -> Py<PyAny> {
        self.start_pin.clone_ref(py)
    }
    #[setter]
    fn set_start_pin(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.start_pin = v.into_any().unbind();
    }

    #[getter]
    fn end_pin(&self, py: Python<'_>) -> Py<PyAny> {
        self.end_pin.clone_ref(py)
    }
    #[setter]
    fn set_end_pin(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.end_pin = v.into_any().unbind();
    }

    #[getter]
    fn distance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.distance_mm.clone_ref(py)
    }
    #[setter]
    fn set_distance_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.distance_mm = v.into_any().unbind();
    }

    #[getter]
    fn distance_cells(&self, py: Python<'_>) -> Py<PyAny> {
        self.distance_cells.clone_ref(py)
    }
    #[setter]
    fn set_distance_cells(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.distance_cells = v.into_any().unbind();
    }

    #[getter]
    fn success(&self, py: Python<'_>) -> Py<PyAny> {
        self.success.clone_ref(py)
    }
    #[setter]
    fn set_success(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.success = v.into_any().unbind();
    }

    #[getter]
    fn method(&self, py: Python<'_>) -> Py<PyAny> {
        self.method.clone_ref(py)
    }
    #[setter]
    fn set_method(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.method = v.into_any().unbind();
    }

    #[getter]
    fn iterations_used(&self, py: Python<'_>) -> Py<PyAny> {
        self.iterations_used.clone_ref(py)
    }
    #[setter]
    fn set_iterations_used(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.iterations_used = v.into_any().unbind();
    }

    #[getter]
    fn iterations_limit(&self, py: Python<'_>) -> Py<PyAny> {
        self.iterations_limit.clone_ref(py)
    }
    #[setter]
    fn set_iterations_limit(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.iterations_limit = v.into_any().unbind();
    }

    #[getter]
    fn timeout(&self, py: Python<'_>) -> Py<PyAny> {
        self.timeout.clone_ref(py)
    }
    #[setter]
    fn set_timeout(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.timeout = v.into_any().unbind();
    }

    #[getter]
    fn path_length_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.path_length_mm.clone_ref(py)
    }
    #[setter]
    fn set_path_length_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.path_length_mm = v.into_any().unbind();
    }

    #[getter]
    fn via_count(&self, py: Python<'_>) -> Py<PyAny> {
        self.via_count.clone_ref(py)
    }
    #[setter]
    fn set_via_count(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.via_count = v.into_any().unbind();
    }

    #[getter]
    fn layers_used(&self, py: Python<'_>) -> Py<PyAny> {
        self.layers_used.clone_ref(py)
    }
    #[setter]
    fn set_layers_used(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.layers_used = v.into_any().unbind();
    }

}

// ---------------------------------------------------------------------------
// NetMetrics
// ---------------------------------------------------------------------------

/// `NetMetrics` — 12-field mutable dataclass + `segment_details` list.
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct NetMetrics {
    net_name: Py<PyAny>,
    net_class: Py<PyAny>,
    pin_count: Py<PyAny>,
    segments_total: Py<PyAny>,
    segments_completed: Py<PyAny>,
    segments_failed: Py<PyAny>,
    segments_timeout: Py<PyAny>,
    total_iterations: Py<PyAny>,
    total_path_length_mm: Py<PyAny>,
    total_vias: Py<PyAny>,
    elapsed_seconds: Py<PyAny>,
    segment_details: Py<PyAny>,
}

#[pymethods]
impl NetMetrics {
    #[new]
    #[pyo3(signature = (
        net_name, net_class, pin_count, segments_total, segments_completed,
        segments_failed, segments_timeout, total_iterations,
        total_path_length_mm, total_vias, elapsed_seconds, segment_details=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        net_name: &Bound<'_, PyAny>,
        net_class: &Bound<'_, PyAny>,
        pin_count: &Bound<'_, PyAny>,
        segments_total: &Bound<'_, PyAny>,
        segments_completed: &Bound<'_, PyAny>,
        segments_failed: &Bound<'_, PyAny>,
        segments_timeout: &Bound<'_, PyAny>,
        total_iterations: &Bound<'_, PyAny>,
        total_path_length_mm: &Bound<'_, PyAny>,
        total_vias: &Bound<'_, PyAny>,
        elapsed_seconds: &Bound<'_, PyAny>,
        segment_details: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let segment_details = match segment_details {
            Some(v) => v.clone().unbind(),
            None => PyList::empty(py).into_any().unbind(),
        };
        Ok(NetMetrics {
            net_name: net_name.clone().unbind(),
            net_class: net_class.clone().unbind(),
            pin_count: pin_count.clone().unbind(),
            segments_total: segments_total.clone().unbind(),
            segments_completed: segments_completed.clone().unbind(),
            segments_failed: segments_failed.clone().unbind(),
            segments_timeout: segments_timeout.clone().unbind(),
            total_iterations: total_iterations.clone().unbind(),
            total_path_length_mm: total_path_length_mm.clone().unbind(),
            total_vias: total_vias.clone().unbind(),
            elapsed_seconds: elapsed_seconds.clone().unbind(),
            segment_details,
        })
    }

    #[getter]
    fn net_name(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_name.clone_ref(py)
    }
    #[setter]
    fn set_net_name(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_name = v.into_any().unbind();
    }

    #[getter]
    fn net_class(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_class.clone_ref(py)
    }
    #[setter]
    fn set_net_class(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_class = v.into_any().unbind();
    }

    #[getter]
    fn pin_count(&self, py: Python<'_>) -> Py<PyAny> {
        self.pin_count.clone_ref(py)
    }
    #[setter]
    fn set_pin_count(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.pin_count = v.into_any().unbind();
    }

    #[getter]
    fn segments_total(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_total.clone_ref(py)
    }
    #[setter]
    fn set_segments_total(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_total = v.into_any().unbind();
    }

    #[getter]
    fn segments_completed(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_completed.clone_ref(py)
    }
    #[setter]
    fn set_segments_completed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_completed = v.into_any().unbind();
    }

    #[getter]
    fn segments_failed(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_failed.clone_ref(py)
    }
    #[setter]
    fn set_segments_failed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_failed = v.into_any().unbind();
    }

    #[getter]
    fn segments_timeout(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_timeout.clone_ref(py)
    }
    #[setter]
    fn set_segments_timeout(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_timeout = v.into_any().unbind();
    }

    #[getter]
    fn total_iterations(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_iterations.clone_ref(py)
    }
    #[setter]
    fn set_total_iterations(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_iterations = v.into_any().unbind();
    }

    #[getter]
    fn total_path_length_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_path_length_mm.clone_ref(py)
    }
    #[setter]
    fn set_total_path_length_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_path_length_mm = v.into_any().unbind();
    }

    #[getter]
    fn total_vias(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_vias.clone_ref(py)
    }
    #[setter]
    fn set_total_vias(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_vias = v.into_any().unbind();
    }

    #[getter]
    fn elapsed_seconds(&self, py: Python<'_>) -> Py<PyAny> {
        self.elapsed_seconds.clone_ref(py)
    }
    #[setter]
    fn set_elapsed_seconds(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.elapsed_seconds = v.into_any().unbind();
    }

    #[getter]
    fn segment_details(&self, py: Python<'_>) -> Py<PyAny> {
        self.segment_details.clone_ref(py)
    }
    #[setter]
    fn set_segment_details(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segment_details = v.into_any().unbind();
    }


    /// `completion_rate`: `1.0` when `segments_total == 0`, else the ratio.
    #[getter]
    fn completion_rate(&self, py: Python<'_>) -> PyResult<f64> {
        let total: i64 = self.segments_total.bind(py).extract()?;
        if total == 0 {
            return Ok(1.0);
        }
        let completed: i64 = self.segments_completed.bind(py).extract()?;
        Ok(completed as f64 / total as f64)
    }

    /// `is_fully_routed`: `segments_completed == segments_total`.
    #[getter]
    fn is_fully_routed(&self, py: Python<'_>) -> PyResult<bool> {
        let total: i64 = self.segments_total.bind(py).extract()?;
        let completed: i64 = self.segments_completed.bind(py).extract()?;
        Ok(completed == total)
    }
}

// ---------------------------------------------------------------------------
// RoutingMetrics
// ---------------------------------------------------------------------------

/// `RoutingMetrics` — 19-field mutable dataclass with aggregation compute.
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct RoutingMetrics {
    nets_total: Py<PyAny>,
    nets_fully_routed: Py<PyAny>,
    nets_partially_routed: Py<PyAny>,
    nets_failed: Py<PyAny>,
    nets_plane: Py<PyAny>,
    segments_total: Py<PyAny>,
    segments_completed: Py<PyAny>,
    segments_failed: Py<PyAny>,
    segments_timeout: Py<PyAny>,
    total_iterations: Py<PyAny>,
    avg_iterations_per_segment: Py<PyAny>,
    timeout_rate: Py<PyAny>,
    total_traces: Py<PyAny>,
    total_vias: Py<PyAny>,
    total_trace_length_mm: Py<PyAny>,
    total_elapsed_seconds: Py<PyAny>,
    net_metrics: Py<PyAny>,
    failed_nets: Py<PyAny>,
    timeout_nets: Py<PyAny>,
}

#[pymethods]
impl RoutingMetrics {
    #[new]
    #[pyo3(signature = (
        nets_total=None, nets_fully_routed=None, nets_partially_routed=None,
        nets_failed=None, nets_plane=None, segments_total=None,
        segments_completed=None, segments_failed=None, segments_timeout=None,
        total_iterations=None, avg_iterations_per_segment=None,
        timeout_rate=None, total_traces=None, total_vias=None,
        total_trace_length_mm=None, total_elapsed_seconds=None,
        net_metrics=None, failed_nets=None, timeout_nets=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        nets_total: Option<&Bound<'_, PyAny>>,
        nets_fully_routed: Option<&Bound<'_, PyAny>>,
        nets_partially_routed: Option<&Bound<'_, PyAny>>,
        nets_failed: Option<&Bound<'_, PyAny>>,
        nets_plane: Option<&Bound<'_, PyAny>>,
        segments_total: Option<&Bound<'_, PyAny>>,
        segments_completed: Option<&Bound<'_, PyAny>>,
        segments_failed: Option<&Bound<'_, PyAny>>,
        segments_timeout: Option<&Bound<'_, PyAny>>,
        total_iterations: Option<&Bound<'_, PyAny>>,
        avg_iterations_per_segment: Option<&Bound<'_, PyAny>>,
        timeout_rate: Option<&Bound<'_, PyAny>>,
        total_traces: Option<&Bound<'_, PyAny>>,
        total_vias: Option<&Bound<'_, PyAny>>,
        total_trace_length_mm: Option<&Bound<'_, PyAny>>,
        total_elapsed_seconds: Option<&Bound<'_, PyAny>>,
        net_metrics: Option<&Bound<'_, PyAny>>,
        failed_nets: Option<&Bound<'_, PyAny>>,
        timeout_nets: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let z = 0_i64;
        Ok(RoutingMetrics {
            nets_total: opt_int(py, nets_total, z)?,
            nets_fully_routed: opt_int(py, nets_fully_routed, z)?,
            nets_partially_routed: opt_int(py, nets_partially_routed, z)?,
            nets_failed: opt_int(py, nets_failed, z)?,
            nets_plane: opt_int(py, nets_plane, z)?,
            segments_total: opt_int(py, segments_total, z)?,
            segments_completed: opt_int(py, segments_completed, z)?,
            segments_failed: opt_int(py, segments_failed, z)?,
            segments_timeout: opt_int(py, segments_timeout, z)?,
            total_iterations: opt_int(py, total_iterations, z)?,
            avg_iterations_per_segment: opt_float(py, avg_iterations_per_segment, 0.0)?,
            timeout_rate: opt_float(py, timeout_rate, 0.0)?,
            total_traces: opt_int(py, total_traces, z)?,
            total_vias: opt_int(py, total_vias, z)?,
            total_trace_length_mm: opt_float(py, total_trace_length_mm, 0.0)?,
            total_elapsed_seconds: opt_float(py, total_elapsed_seconds, 0.0)?,
            net_metrics: opt_dict(py, net_metrics)?,
            failed_nets: opt_list(py, failed_nets)?,
            timeout_nets: opt_list(py, timeout_nets)?,
        })
    }

    #[getter]
    fn nets_total(&self, py: Python<'_>) -> Py<PyAny> {
        self.nets_total.clone_ref(py)
    }
    #[setter]
    fn set_nets_total(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.nets_total = v.into_any().unbind();
    }

    #[getter]
    fn nets_fully_routed(&self, py: Python<'_>) -> Py<PyAny> {
        self.nets_fully_routed.clone_ref(py)
    }
    #[setter]
    fn set_nets_fully_routed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.nets_fully_routed = v.into_any().unbind();
    }

    #[getter]
    fn nets_partially_routed(&self, py: Python<'_>) -> Py<PyAny> {
        self.nets_partially_routed.clone_ref(py)
    }
    #[setter]
    fn set_nets_partially_routed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.nets_partially_routed = v.into_any().unbind();
    }

    #[getter]
    fn nets_failed(&self, py: Python<'_>) -> Py<PyAny> {
        self.nets_failed.clone_ref(py)
    }
    #[setter]
    fn set_nets_failed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.nets_failed = v.into_any().unbind();
    }

    #[getter]
    fn nets_plane(&self, py: Python<'_>) -> Py<PyAny> {
        self.nets_plane.clone_ref(py)
    }
    #[setter]
    fn set_nets_plane(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.nets_plane = v.into_any().unbind();
    }

    #[getter]
    fn segments_total(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_total.clone_ref(py)
    }
    #[setter]
    fn set_segments_total(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_total = v.into_any().unbind();
    }

    #[getter]
    fn segments_completed(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_completed.clone_ref(py)
    }
    #[setter]
    fn set_segments_completed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_completed = v.into_any().unbind();
    }

    #[getter]
    fn segments_failed(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_failed.clone_ref(py)
    }
    #[setter]
    fn set_segments_failed(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_failed = v.into_any().unbind();
    }

    #[getter]
    fn segments_timeout(&self, py: Python<'_>) -> Py<PyAny> {
        self.segments_timeout.clone_ref(py)
    }
    #[setter]
    fn set_segments_timeout(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.segments_timeout = v.into_any().unbind();
    }

    #[getter]
    fn total_iterations(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_iterations.clone_ref(py)
    }
    #[setter]
    fn set_total_iterations(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_iterations = v.into_any().unbind();
    }

    #[getter]
    fn avg_iterations_per_segment(&self, py: Python<'_>) -> Py<PyAny> {
        self.avg_iterations_per_segment.clone_ref(py)
    }
    #[setter]
    fn set_avg_iterations_per_segment(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.avg_iterations_per_segment = v.into_any().unbind();
    }

    #[getter]
    fn timeout_rate(&self, py: Python<'_>) -> Py<PyAny> {
        self.timeout_rate.clone_ref(py)
    }
    #[setter]
    fn set_timeout_rate(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.timeout_rate = v.into_any().unbind();
    }

    #[getter]
    fn total_traces(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_traces.clone_ref(py)
    }
    #[setter]
    fn set_total_traces(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_traces = v.into_any().unbind();
    }

    #[getter]
    fn total_vias(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_vias.clone_ref(py)
    }
    #[setter]
    fn set_total_vias(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_vias = v.into_any().unbind();
    }

    #[getter]
    fn total_trace_length_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_trace_length_mm.clone_ref(py)
    }
    #[setter]
    fn set_total_trace_length_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_trace_length_mm = v.into_any().unbind();
    }

    #[getter]
    fn total_elapsed_seconds(&self, py: Python<'_>) -> Py<PyAny> {
        self.total_elapsed_seconds.clone_ref(py)
    }
    #[setter]
    fn set_total_elapsed_seconds(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.total_elapsed_seconds = v.into_any().unbind();
    }

    #[getter]
    fn net_metrics(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_metrics.clone_ref(py)
    }
    #[setter]
    fn set_net_metrics(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_metrics = v.into_any().unbind();
    }

    #[getter]
    fn failed_nets(&self, py: Python<'_>) -> Py<PyAny> {
        self.failed_nets.clone_ref(py)
    }
    #[setter]
    fn set_failed_nets(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.failed_nets = v.into_any().unbind();
    }

    #[getter]
    fn timeout_nets(&self, py: Python<'_>) -> Py<PyAny> {
        self.timeout_nets.clone_ref(py)
    }
    #[setter]
    fn set_timeout_nets(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.timeout_nets = v.into_any().unbind();
    }


    /// `add_net`: store the net in `net_metrics`, then update every counter.
    fn add_net(&mut self, py: Python<'_>, net: &Bound<'_, PyAny>) -> PyResult<()> {
        let net_metrics = self.net_metrics.bind(py).cast::<PyDict>()?;
        let net_name = net.getattr("net_name")?;
        net_metrics.set_item(&net_name, net)?;

        let is_full = net.getattr("is_fully_routed")?.extract::<bool>()?;
        if is_full {
            self.bump_i64(py, "nets_fully_routed", 1)?;
        } else {
            let completed: i64 = net.getattr("segments_completed")?.extract()?;
            if completed > 0 {
                self.bump_i64(py, "nets_partially_routed", 1)?;
            } else {
                self.bump_i64(py, "nets_failed", 1)?;
                self.failed_nets.bind(py).cast::<PyList>()?.append(&net_name)?;
            }
        }
        self.bump_i64(py, "nets_total", 1)?;

        let timeout: i64 = net.getattr("segments_timeout")?.extract()?;
        if timeout > 0 {
            self.timeout_nets.bind(py).cast::<PyList>()?.append(&net_name)?;
        }

        self.bump_i64(py, "segments_total", net.getattr("segments_total")?.extract()?)?;
        self.bump_i64(py, "segments_completed", net.getattr("segments_completed")?.extract()?)?;
        self.bump_i64(py, "segments_failed", net.getattr("segments_failed")?.extract()?)?;
        self.bump_i64(py, "segments_timeout", timeout)?;
        self.bump_i64(py, "total_iterations", net.getattr("total_iterations")?.extract()?)?;
        self.bump_i64(py, "total_vias", net.getattr("total_vias")?.extract()?)?;
        self.bump_f64(py, "total_trace_length_mm", net.getattr("total_path_length_mm")?.extract()?)?;
        self.bump_f64(py, "total_elapsed_seconds", net.getattr("elapsed_seconds")?.extract()?)?;
        Ok(())
    }

    /// `finalize`: derived rates after all nets are added.
    fn finalize(&mut self, py: Python<'_>) -> PyResult<()> {
        let segments_total: i64 = self.segments_total.bind(py).extract()?;
        if segments_total > 0 {
            let total_iterations: i64 = self.total_iterations.bind(py).extract()?;
            let segments_timeout: i64 = self.segments_timeout.bind(py).extract()?;
            self.avg_iterations_per_segment =
                (total_iterations as f64 / segments_total as f64).into_bound_py_any(py)?.unbind();
            self.timeout_rate = (segments_timeout as f64 / segments_total as f64)
                .into_bound_py_any(py)?
                .unbind();
        }
        Ok(())
    }

    /// `to_dict`: build the JSON-serializable dict (insertion order
    /// preserved; CPython `round(x, ndigits)` half-to-even applied).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let nets_total: i64 = self.nets_total.bind(py).extract()?;
        let nets_full: i64 = self.nets_fully_routed.bind(py).extract()?;
        let net_completion_rate = nets_full as f64 / nets_total.max(1) as f64;

        let segments_total: i64 = self.segments_total.bind(py).extract()?;
        let segments_completed: i64 = self.segments_completed.bind(py).extract()?;
        let segments_completion_rate = segments_completed as f64 / segments_total.max(1) as f64;
        let timeout_rate: f64 = self.timeout_rate.bind(py).extract()?;
        let avg: f64 = self.avg_iterations_per_segment.bind(py).extract()?;
        let total_trace_length_mm: f64 = self.total_trace_length_mm.bind(py).extract()?;
        let total_elapsed_seconds: f64 = self.total_elapsed_seconds.bind(py).extract()?;

        let summary = PyDict::new(py);
        summary.set_item("nets_total", self.nets_total.bind(py))?;
        summary.set_item("nets_fully_routed", self.nets_fully_routed.bind(py))?;
        summary.set_item("nets_partially_routed", self.nets_partially_routed.bind(py))?;
        summary.set_item("nets_failed", self.nets_failed.bind(py))?;
        summary.set_item("nets_plane", self.nets_plane.bind(py))?;
        summary.set_item("net_completion_rate", net_completion_rate)?;

        let segments = PyDict::new(py);
        segments.set_item("total", self.segments_total.bind(py))?;
        segments.set_item("completed", self.segments_completed.bind(py))?;
        segments.set_item("failed", self.segments_failed.bind(py))?;
        segments.set_item("timeout", self.segments_timeout.bind(py))?;
        segments.set_item("completion_rate", segments_completion_rate)?;
        segments.set_item("timeout_rate", timeout_rate)?;

        let search = PyDict::new(py);
        search.set_item("total_iterations", self.total_iterations.bind(py))?;
        search.set_item("avg_iterations_per_segment", py_round_digits(avg, 1))?;

        let output = PyDict::new(py);
        output.set_item("total_traces", self.total_traces.bind(py))?;
        output.set_item("total_vias", self.total_vias.bind(py))?;
        output.set_item("total_trace_length_mm", py_round_digits(total_trace_length_mm, 2))?;

        let timing = PyDict::new(py);
        timing.set_item("total_elapsed_seconds", py_round_digits(total_elapsed_seconds, 2))?;

        let failures = PyDict::new(py);
        failures.set_item("failed_nets", self.failed_nets.bind(py))?;
        failures.set_item("timeout_nets", self.timeout_nets.bind(py))?;

        let out = PyDict::new(py);
        out.set_item("summary", summary)?;
        out.set_item("segments", segments)?;
        out.set_item("search", search)?;
        out.set_item("output", output)?;
        out.set_item("timing", timing)?;
        out.set_item("failures", failures)?;
        Ok(out.unbind())
    }

    /// `to_json`: `json.dumps(to_dict(), indent=indent)` via the real
    /// `json` module (library semantics).
    #[pyo3(signature = (indent=2))]
    fn to_json(&self, py: Python<'_>, indent: usize) -> PyResult<Py<PyString>> {
        let json = py.import("json")?;
        let dumps = json.getattr("dumps")?;
        let dict = self.to_dict(py)?;
        let dict = dict.bind(py);
        let kwargs = PyDict::new(py);
        kwargs.set_item("indent", indent)?;
        let s: Py<PyString> = dumps.call((dict,), Some(&kwargs))?.extract()?;
        Ok(s)
    }

    /// `print_summary`: the oracle's human-readable dump, rendered via
    /// CPython's own `format(x, spec)`/`print` (I/O stays Python-side, the
    /// strings are exact).
    fn print_summary(&self, py: Python<'_>) -> PyResult<()> {
        fn fmt(py: Python<'_>, value: &Bound<'_, PyAny>, spec: &str) -> PyResult<String> {
            let s: Py<PyString> = value.call_method1("__format__", (spec,))?.extract()?;
            Ok(s.bind(py).to_string())
        }

        let builtins = py.import("builtins")?;
        let print = builtins.getattr("print")?;
        let p = |line: &str| -> PyResult<()> {
            print.call1((line,))?;
            Ok(())
        };

        let nets_total: &Bound<'_, PyAny> = self.nets_total.bind(py);
        let nets_full: &Bound<'_, PyAny> = self.nets_fully_routed.bind(py);
        let nets_partial: &Bound<'_, PyAny> = self.nets_partially_routed.bind(py);
        let nets_failed: &Bound<'_, PyAny> = self.nets_failed.bind(py);
        let nets_plane: &Bound<'_, PyAny> = self.nets_plane.bind(py);
        let segments_total: &Bound<'_, PyAny> = self.segments_total.bind(py);
        let segments_completed: &Bound<'_, PyAny> = self.segments_completed.bind(py);
        let segments_failed: &Bound<'_, PyAny> = self.segments_failed.bind(py);
        let segments_timeout: &Bound<'_, PyAny> = self.segments_timeout.bind(py);
        let timeout_rate: &Bound<'_, PyAny> = self.timeout_rate.bind(py);
        let total_iterations: &Bound<'_, PyAny> = self.total_iterations.bind(py);
        let avg: &Bound<'_, PyAny> = self.avg_iterations_per_segment.bind(py);
        let total_traces: &Bound<'_, PyAny> = self.total_traces.bind(py);
        let total_vias: &Bound<'_, PyAny> = self.total_vias.bind(py);
        let trace_length: &Bound<'_, PyAny> = self.total_trace_length_mm.bind(py);
        let elapsed: &Bound<'_, PyAny> = self.total_elapsed_seconds.bind(py);

        let nets_total_i: i64 = nets_total.extract()?;
        let nets_full_i: i64 = nets_full.extract()?;
        let segments_total_i: i64 = segments_total.extract()?;
        let segments_completed_i: i64 = segments_completed.extract()?;
        let failed_nets_len: usize = self.failed_nets.bind(py).len()?;

        p(&format!("\n{}", "=".repeat(60)))?;
        p("ROUTING METRICS SUMMARY")?;
        p(&"=".repeat(60))?;
        p("\nNets:")?;
        p(&format!("  Total:           {}", fmt(py, nets_total, "")?))?;
        let full_pct = fmt(
            py,
            &(nets_full_i as f64 / nets_total_i.max(1) as f64).into_bound_py_any(py)?,
            ".1%",
        )?;
        p(&format!(
            "  Fully routed:    {} ({})",
            fmt(py, nets_full, "")?,
            full_pct
        ))?;
        p(&format!("  Partial:         {}", fmt(py, nets_partial, "")?))?;
        p(&format!("  Failed:          {}", fmt(py, nets_failed, "")?))?;
        p(&format!("  Plane (skipped): {}", fmt(py, nets_plane, "")?))?;
        p("\nSegments:")?;
        p(&format!("  Total:           {}", fmt(py, segments_total, "")?))?;
        let completed_pct = fmt(
            py,
            &(segments_completed_i as f64 / segments_total_i.max(1) as f64).into_bound_py_any(py)?,
            ".1%",
        )?;
        p(&format!(
            "  Completed:       {} ({})",
            fmt(py, segments_completed, "")?,
            completed_pct
        ))?;
        p(&format!("  Failed:          {}", fmt(py, segments_failed, "")?))?;
        p(&format!(
            "  Timeout:         {} ({})",
            fmt(py, segments_timeout, "")?,
            fmt(py, timeout_rate, ".1%")?
        ))?;
        p("\nSearch:")?;
        p(&format!(
            "  Total iterations:    {}",
            fmt(py, total_iterations, ",")?
        ))?;
        p(&format!("  Avg per segment:     {}", fmt(py, avg, ".0f")?))?;
        p("\nOutput:")?;
        p(&format!("  Traces:          {}", fmt(py, total_traces, "")?))?;
        p(&format!("  Vias:            {}", fmt(py, total_vias, "")?))?;
        p(&format!("  Trace length:    {} mm", fmt(py, trace_length, ".1f")?))?;
        p("\nTiming:")?;
        p(&format!("  Total:           {}s", fmt(py, elapsed, ".1f")?))?;
        if failed_nets_len > 0 {
            p(&format!("\nFailed nets ({}):", failed_nets_len))?;
            let failed = self.failed_nets.bind(py).cast::<PyList>()?;
            let shown = failed.iter().take(10).collect::<Vec<_>>();
            for net in &shown {
                p(&format!("  - {}", net))?;
            }
            if failed_nets_len > 10 {
                p(&format!("  ... and {} more", failed_nets_len - 10))?;
            }
        }
        Ok(())
    }

    fn bump_i64(&mut self, py: Python<'_>, field: &str, amount: i64) -> PyResult<()> {
        let cur: i64 = self_get_int(py, self, field)?;
        self_set_int(py, self, field, cur + amount)
    }

    fn bump_f64(&mut self, py: Python<'_>, field: &str, amount: f64) -> PyResult<()> {
        let cur: f64 = self_get_float(py, self, field)?;
        self_set_float(py, self, field, cur + amount)
    }
}

fn self_get_int(py: Python<'_>, s: &RoutingMetrics, field: &str) -> PyResult<i64> {
    match field {
        "nets_total" => s.nets_total.bind(py).extract(),
        "nets_fully_routed" => s.nets_fully_routed.bind(py).extract(),
        "nets_partially_routed" => s.nets_partially_routed.bind(py).extract(),
        "nets_failed" => s.nets_failed.bind(py).extract(),
        "nets_plane" => s.nets_plane.bind(py).extract(),
        "segments_total" => s.segments_total.bind(py).extract(),
        "segments_completed" => s.segments_completed.bind(py).extract(),
        "segments_failed" => s.segments_failed.bind(py).extract(),
        "segments_timeout" => s.segments_timeout.bind(py).extract(),
        "total_iterations" => s.total_iterations.bind(py).extract(),
        "total_traces" => s.total_traces.bind(py).extract(),
        "total_vias" => s.total_vias.bind(py).extract(),
        _ => Err(pyo3::exceptions::PyAttributeError::new_err(format!("no int field {field}"))),
    }
}

fn self_set_int(
    py: Python<'_>,
    s: &mut RoutingMetrics,
    field: &str,
    value: i64,
) -> PyResult<()> {
    let obj = value.into_bound_py_any(py)?.unbind();
    match field {
        "nets_total" => s.nets_total = obj,
        "nets_fully_routed" => s.nets_fully_routed = obj,
        "nets_partially_routed" => s.nets_partially_routed = obj,
        "nets_failed" => s.nets_failed = obj,
        "nets_plane" => s.nets_plane = obj,
        "segments_total" => s.segments_total = obj,
        "segments_completed" => s.segments_completed = obj,
        "segments_failed" => s.segments_failed = obj,
        "segments_timeout" => s.segments_timeout = obj,
        "total_iterations" => s.total_iterations = obj,
        "total_traces" => s.total_traces = obj,
        "total_vias" => s.total_vias = obj,
        _ => return Err(pyo3::exceptions::PyAttributeError::new_err(format!("no int field {field}"))),
    }
    Ok(())
}

fn self_get_float(py: Python<'_>, s: &RoutingMetrics, field: &str) -> PyResult<f64> {
    match field {
        "total_trace_length_mm" => s.total_trace_length_mm.bind(py).extract(),
        "total_elapsed_seconds" => s.total_elapsed_seconds.bind(py).extract(),
        _ => Err(pyo3::exceptions::PyAttributeError::new_err(format!("no float field {field}"))),
    }
}

fn self_set_float(
    py: Python<'_>,
    s: &mut RoutingMetrics,
    field: &str,
    value: f64,
) -> PyResult<()> {
    let obj = value.into_bound_py_any(py)?.unbind();
    match field {
        "total_trace_length_mm" => s.total_trace_length_mm = obj,
        "total_elapsed_seconds" => s.total_elapsed_seconds = obj,
        _ => return Err(pyo3::exceptions::PyAttributeError::new_err(format!("no float field {field}"))),
    }
    Ok(())
}

/// Register the routing-metrics pyclasses on the module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SegmentMetrics>()?;
    module.add_class::<NetMetrics>()?;
    module.add_class::<RoutingMetrics>()?;
    Ok(())
}

//! The pyo3 boundary for the placer's `core/` contract layer.
//!
//! Everything here is a thin adapter over the pure modules beside it.
//! The Python-visible names (`Rect`, `PinInfo`, `PlacementViolation`,
//! `FabPreset`) are exported from `temper_io_types` and re-bound by the
//! `temper_placer.core.*` shims, so no downstream import changes.

use pyo3::exceptions::{PyOverflowError, PyTypeError, PyValueError, PyZeroDivisionError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyTuple};
use std::panic::AssertUnwindSafe;

use super::manufacturing;
use super::netclass::{self, PatternSet};
use super::placer_compute;
use super::units;

// ---------------------------------------------------------------------------
// shared helpers
// ---------------------------------------------------------------------------

/// What `__reduce__` returns: `(callable, args)`, the two-tuple form
/// `pickle`/`copy` use to rebuild an object.
type Reduced<'py> = (Bound<'py, PyAny>, Bound<'py, PyTuple>);

/// `hash(...)` raised by an unhashable dataclass (`eq=True, frozen=False`
/// sets `__hash__ = None`).
fn unhashable(type_name: &str) -> PyErr {
    PyTypeError::new_err(format!("unhashable type: '{type_name}'"))
}

/// CPython `int(x)` on a float: truncate toward zero, `OverflowError` on
/// an infinity and `ValueError` on a NaN, with the interpreter's own
/// message text. Values outside `i64` are handed back to CPython so the
/// arbitrary-precision result is exact rather than saturated.
fn py_int_from_f64(py: Python<'_>, value: f64) -> PyResult<Py<PyInt>> {
    if value.is_nan() {
        return Err(PyValueError::new_err("cannot convert float NaN to integer"));
    }
    if value.is_infinite() {
        return Err(PyOverflowError::new_err(
            "cannot convert float infinity to integer",
        ));
    }
    let truncated = value.trunc();
    if truncated >= -(2f64.powi(63)) && truncated < 2f64.powi(63) {
        return Ok((truncated as i64).into_pyobject(py)?.unbind());
    }
    // |x| >= 2^63: every such f64 is already an integer, but it does not
    // fit i64. CPython's own float.__int__ is exact, so defer to it
    // instead of approximating.
    let as_float = PyFloat::new(py, truncated);
    Ok(as_float
        .call_method0("__int__")?
        .cast::<PyInt>()?
        .clone()
        .unbind())
}

// ---------------------------------------------------------------------------
// units
// ---------------------------------------------------------------------------

/// True for the Python scalar types whose arithmetic with `np.pi` is
/// plain f64 (`np.pi` is itself a Python `float`, so `int`/`bool`/`float`
/// all stay in f64). Anything else — a numpy scalar or an array — has
/// NEP 50 promotion rules and stays on the numpy path in the shim.
///
/// The test is **exact type identity, not `isinstance`**: `np.float64`
/// is a genuine subclass of Python's `float`, so `isinstance(x, float)`
/// accepts it and the Rust path would hand back a plain `float`, losing
/// the `np.float64` type the reference returns. The R1a differential
/// caught exactly that on `deg_to_rad(np.float64(1.0))`.
#[pyfunction]
pub fn is_plain_python_scalar(value: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py = value.py();
    let ty = value.get_type();
    Ok(ty.is(py.get_type::<PyFloat>())
        || ty.is(py.get_type::<PyInt>())
        || ty.is(py.get_type::<PyBool>()))
}

#[pyfunction]
pub fn deg_to_rad(degrees: f64) -> f64 {
    units::deg_to_rad(degrees)
}

#[pyfunction]
pub fn rad_to_deg(radians: f64) -> f64 {
    units::rad_to_deg(radians)
}

/// `int(mm / cell_size_mm)`.
///
/// Division by zero is `ZeroDivisionError` in Python but `inf`/`NaN` in
/// IEEE-754, so the zero divisor has to be caught explicitly — the R1a
/// differential found this one. CPython's message depends on the operand
/// types: `int / int` says "division by zero" and anything involving a
/// float says "float division by zero" (measured; `bool` counts as
/// `int`, so `True / 0` says "division by zero").
#[pyfunction]
pub fn mm_to_cell(
    py: Python<'_>,
    mm: &Bound<'_, PyAny>,
    cell_size_mm: &Bound<'_, PyAny>,
) -> PyResult<Py<PyInt>> {
    let divisor: f64 = cell_size_mm.extract()?;
    if divisor == 0.0 {
        let both_int = mm.is_instance_of::<PyInt>() && cell_size_mm.is_instance_of::<PyInt>();
        return Err(PyZeroDivisionError::new_err(if both_int {
            "division by zero"
        } else {
            "float division by zero"
        }));
    }
    let numerator: f64 = mm.extract()?;
    py_int_from_f64(py, units::mm_to_cell_quotient(numerator, divisor))
}

#[pyfunction]
pub fn cell_to_mm(cell: f64, cell_size_mm: f64) -> f64 {
    units::cell_to_mm(cell, cell_size_mm)
}

#[pyfunction]
pub fn distance_mm(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    units::distance_mm(x1, y1, x2, y2)
}

#[pyfunction]
pub fn manhattan_distance_mm(x1: f64, y1: f64, x2: f64, y2: f64) -> f64 {
    units::manhattan_distance_mm(x1, y1, x2, y2)
}

/// `0 <= layer < max_layers`.
///
/// Python integers are unbounded, so an `i64` extraction raises
/// `OverflowError` on `2**63` where the reference just answers `False`
/// — found by the R1a differential. The `i64` path stays as the fast
/// path and anything that does not fit falls back to Python-level
/// comparison, which is exact for any operand.
#[pyfunction]
#[pyo3(signature = (layer, max_layers = None))]
pub fn is_valid_layer(
    py: Python<'_>,
    layer: &Bound<'_, PyAny>,
    max_layers: Option<&Bound<'_, PyAny>>,
) -> PyResult<bool> {
    let default_max = 4i64.into_pyobject(py)?.into_any();
    let max_bound = match max_layers {
        Some(m) => m.clone(),
        None => default_max,
    };
    if let (Ok(l), Ok(m)) = (layer.extract::<i64>(), max_bound.extract::<i64>()) {
        return Ok(units::is_valid_layer(l, m));
    }
    let zero = 0i64.into_pyobject(py)?.into_any();
    Ok(zero.le(layer)? && layer.lt(&max_bound)?)
}

#[pyfunction]
pub fn is_valid_net_id(py: Python<'_>, net_id: &Bound<'_, PyAny>) -> PyResult<bool> {
    if let Ok(n) = net_id.extract::<i64>() {
        return Ok(units::is_valid_net_id(n));
    }
    let zero = 0i64.into_pyobject(py)?.into_any();
    net_id.ge(&zero)
}

// ---------------------------------------------------------------------------
// net classification
// ---------------------------------------------------------------------------

macro_rules! netclass_fn {
    ($py_name:ident, $set:expr) => {
        #[pyfunction]
        pub fn $py_name(name: &str) -> bool {
            netclass::matches_any(name, $set)
        }
    };
}

netclass_fn!(is_ground_net, PatternSet::GroundNet);
netclass_fn!(is_power_net, PatternSet::PowerNet);
netclass_fn!(is_hv_net, PatternSet::HvNet);
netclass_fn!(is_ground_pin, PatternSet::GroundPin);
netclass_fn!(is_power_pin, PatternSet::PowerPin);
netclass_fn!(is_hv_pin, PatternSet::HvPin);
netclass_fn!(is_clock_pin, PatternSet::ClockPin);

#[pyfunction]
pub fn is_signal_net(name: &str) -> bool {
    netclass::is_signal_net(name)
}

#[pyfunction]
pub fn classify_net_type(name: &str) -> &'static str {
    netclass::classify_net_type(name)
}

// `router_v6.net_classification`'s power-net variant (extra patterns + a
// "starts with '+'" prefix heuristic; see netclass.rs). Ground/HV/pin
// classification is byte-identical to the core module above, so router_v6
// reuses `is_ground_net`/`is_hv_net`/`is_*_pin` directly and only needs
// these three additional bindings.

#[pyfunction]
pub fn is_power_net_v6(name: &str) -> bool {
    netclass::is_power_net_v6(name)
}

#[pyfunction]
pub fn is_signal_net_v6(name: &str) -> bool {
    netclass::is_signal_net_v6(name)
}

#[pyfunction]
pub fn classify_net_type_v6(name: &str) -> &'static str {
    netclass::classify_net_type_v6(name)
}

// ---------------------------------------------------------------------------
// manufacturing
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (nominal, tolerance = 0.1))]
pub fn inflated_clearance(nominal: f64, tolerance: f64) -> f64 {
    manufacturing::inflated_clearance(nominal, tolerance)
}

#[pyfunction]
#[pyo3(signature = (nominal, tolerance = 0.1))]
pub fn inflated_width(nominal: f64, tolerance: f64) -> f64 {
    manufacturing::inflated_width(nominal, tolerance)
}

/// `temper_placer.core.manufacturing.FabPreset` — a plain (mutable,
/// unhashable) dataclass.
#[pyclass(name = "FabPreset", module = "temper_io_types", from_py_object)]
#[derive(Clone)]
pub struct PyFabPreset {
    #[pyo3(get, set)]
    pub name: String,
    #[pyo3(get, set)]
    pub trace_width_pct: f64,
    #[pyo3(get, set)]
    pub min_trace_mm: f64,
    #[pyo3(get, set)]
    pub min_clearance_mm: f64,
    #[pyo3(get, set)]
    pub etch_undercut_mm: f64,
    #[pyo3(get, set)]
    pub layer_registration_mm: f64,
    #[pyo3(get, set)]
    pub drill_tolerance_mm: f64,
}

impl PyFabPreset {
    fn from_pure(p: manufacturing::FabPreset) -> Self {
        PyFabPreset {
            name: p.name,
            trace_width_pct: p.trace_width_pct,
            min_trace_mm: p.min_trace_mm,
            min_clearance_mm: p.min_clearance_mm,
            etch_undercut_mm: p.etch_undercut_mm,
            layer_registration_mm: p.layer_registration_mm,
            drill_tolerance_mm: p.drill_tolerance_mm,
        }
    }

    fn pure(&self) -> manufacturing::FabPreset {
        manufacturing::FabPreset {
            name: self.name.clone(),
            trace_width_pct: self.trace_width_pct,
            min_trace_mm: self.min_trace_mm,
            min_clearance_mm: self.min_clearance_mm,
            etch_undercut_mm: self.etch_undercut_mm,
            layer_registration_mm: self.layer_registration_mm,
            drill_tolerance_mm: self.drill_tolerance_mm,
        }
    }
}

#[pymethods]
impl PyFabPreset {
    #[new]
    #[pyo3(signature = (
        name,
        trace_width_pct = 0.15,
        min_trace_mm = 0.127,
        min_clearance_mm = 0.127,
        etch_undercut_mm = 0.05,
        layer_registration_mm = 0.1,
        drill_tolerance_mm = 0.05,
    ))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        name: String,
        trace_width_pct: f64,
        min_trace_mm: f64,
        min_clearance_mm: f64,
        etch_undercut_mm: f64,
        layer_registration_mm: f64,
        drill_tolerance_mm: f64,
    ) -> Self {
        PyFabPreset {
            name,
            trace_width_pct,
            min_trace_mm,
            min_clearance_mm,
            etch_undercut_mm,
            layer_registration_mm,
            drill_tolerance_mm,
        }
    }

    #[staticmethod]
    fn jlcpcb_standard() -> Self {
        PyFabPreset::from_pure(manufacturing::FabPreset::jlcpcb_standard())
    }

    #[staticmethod]
    fn jlcpcb_hdi() -> Self {
        PyFabPreset::from_pure(manufacturing::FabPreset::jlcpcb_hdi())
    }

    #[staticmethod]
    fn oshpark() -> Self {
        PyFabPreset::from_pure(manufacturing::FabPreset::oshpark())
    }

    fn __repr__(&self) -> String {
        self.pure().repr()
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        match other.cast::<PyFabPreset>() {
            Ok(o) => Ok(self.pure() == o.borrow().pure()),
            Err(_) => Ok(false),
        }
    }

    /// A non-frozen `@dataclass` sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("FabPreset"))
    }

    /// See the deleted `Rect` pyclass's `__reduce__` — a pyclass is unpicklable by default.
    fn __reduce__<'py>(slf: &Bound<'py, Self>) -> PyResult<Reduced<'py>> {
        let py = slf.py();
        let s = slf.borrow();
        Ok((
            slf.get_type().into_any(),
            PyTuple::new(
                py,
                [
                    s.name.clone().into_pyobject(py)?.into_any(),
                    s.trace_width_pct.into_pyobject(py)?.into_any(),
                    s.min_trace_mm.into_pyobject(py)?.into_any(),
                    s.min_clearance_mm.into_pyobject(py)?.into_any(),
                    s.etch_undercut_mm.into_pyobject(py)?.into_any(),
                    s.layer_registration_mm.into_pyobject(py)?.into_any(),
                    s.drill_tolerance_mm.into_pyobject(py)?.into_any(),
                ],
            )?,
        ))
    }
}

#[pyfunction]
pub fn get_fab_presets(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new(py);
    dict.set_item("jlcpcb_standard", PyFabPreset::jlcpcb_standard())?;
    dict.set_item("jlcpcb_hdi", PyFabPreset::jlcpcb_hdi())?;
    dict.set_item("oshpark", PyFabPreset::oshpark())?;
    Ok(dict.unbind())
}

// ---------------------------------------------------------------------------
// registration
// ---------------------------------------------------------------------------

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7, R1g).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Build the per-call `(cos, sin)` closure the placer kernels call back
/// into: `cos_sin(theta)` must return a 2-sequence of floats. This is a
/// Python seam by design — the oracle's `math.cos`/`math.sin`/`np.cos`/
/// `np.sin` bits are library semantics Rust does not reproduce (measured
/// `f64::sin` divergence on this platform, 2026-08-05).
#[allow(clippy::type_complexity)] // the closure's return type is the seam's contract
fn cos_sin_impl<'a>(cb: &'a Bound<'_, PyAny>) -> impl Fn(f64) -> PyResult<(f64, f64)> + 'a {
    move |theta: f64| -> PyResult<(f64, f64)> {
        let r = cb.call1((theta,))?;
        let a = r.get_item(0)?;
        let b = r.get_item(1)?;
        Ok((a.extract()?, b.extract()?))
    }
}

// ---------------------------------------------------------------------------
// Wave-4 Phase 4: placer non-cp_sat compute kernels (placer_compute.rs)
// ---------------------------------------------------------------------------

/// `ComponentTemplate.apply` geometry compute.
#[pyfunction]
#[allow(clippy::too_many_arguments)] // mirrors ComponentTemplate.apply's Python signature
pub fn placer_apply_component_template(
    refs: Vec<String>,
    xs: Vec<f64>,
    ys: Vec<f64>,
    rots: Vec<i64>,
    anchor_idx: usize,
    anchor_x: f64,
    anchor_y: f64,
    rotation: i64,
    cos_sin: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, f64, f64, i64)>> {
    guard(|| {
        if anchor_idx >= refs.len() {
            return Err(PyValueError::new_err(
                "anchor index out of range for template components",
            ));
        }
        let components = build_template_components(refs, xs, ys, rots);
        let cb = cos_sin_impl(cos_sin);
        let out = placer_compute::apply_component_template(
            &components,
            anchor_idx,
            anchor_x,
            anchor_y,
            rotation,
            &cb,
        )?;
        Ok(out.into_iter().map(|p| (p.ref_, p.x, p.y, p.rotation)).collect())
    })
}

/// `ParametricTemplate.apply` geometry compute. `anchor_ratio` is the
/// anchor's `(x_ratio, y_ratio)` or `None` for the default-center fallback.
#[pyfunction]
#[allow(clippy::too_many_arguments)] // mirrors ParametricTemplate.apply's Python signature
pub fn placer_apply_parametric_template(
    refs: Vec<String>,
    xs: Vec<f64>,
    ys: Vec<f64>,
    rots: Vec<i64>,
    anchor_ratio: Option<(f64, f64)>,
    anchor_x: f64,
    anchor_y: f64,
    target_width: f64,
    target_height: f64,
    rotation: i64,
    cos_sin: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, f64, f64, i64)>> {
    guard(|| {
        let components = build_template_components(refs, xs, ys, rots);
        let cb = cos_sin_impl(cos_sin);
        let out = placer_compute::apply_parametric_template(
            &components,
            anchor_ratio,
            anchor_x,
            anchor_y,
            target_width,
            target_height,
            rotation,
            &cb,
        )?;
        Ok(out.into_iter().map(|p| (p.ref_, p.x, p.y, p.rotation)).collect())
    })
}

fn build_template_components(
    refs: Vec<String>,
    xs: Vec<f64>,
    ys: Vec<f64>,
    rots: Vec<i64>,
) -> Vec<placer_compute::TemplateComponent> {
    refs.into_iter()
        .zip(xs)
        .zip(ys)
        .zip(rots)
        .map(|(((ref_, x), y), rotation)| placer_compute::TemplateComponent {
            ref_,
            x,
            y,
            rotation,
        })
        .collect()
}

/// `place_power_stage_template` compute: template application at the zone
/// center plus the per-component mapping into the float32 arrays.
#[pyfunction]
#[allow(clippy::too_many_arguments)] // mirrors place_power_stage_template's Python signature
#[allow(clippy::type_complexity)] // the (positions, rotations, placed, unplaced) tuple is the shim's contract
pub fn placer_place_power_stage_template(
    component_refs: Vec<String>,
    template_refs: Vec<String>,
    template_xs: Vec<f64>,
    template_ys: Vec<f64>,
    template_rots: Vec<i64>,
    anchor_idx: usize,
    zone_center_x: f64,
    zone_center_y: f64,
    rotation: i64,
    initial: Option<Vec<f64>>,
    cos_sin: &Bound<'_, PyAny>,
) -> PyResult<(Vec<f32>, Vec<f32>, Vec<String>, Vec<String>)> {
    guard(|| {
        if anchor_idx >= template_refs.len() {
            return Err(PyValueError::new_err(
                "anchor index out of range for template components",
            ));
        }
        let components = build_template_components(template_refs, template_xs, template_ys, template_rots);
        let cb = cos_sin_impl(cos_sin);
        let out = placer_compute::place_power_stage_template(
            &component_refs,
            &components,
            anchor_idx,
            zone_center_x,
            zone_center_y,
            rotation,
            initial.as_deref(),
            &cb,
        )?;
        Ok((out.positions, out.rotations, out.placed, out.unplaced))
    })
}

/// `place_by_proximity` compute: the #763-fixed spiral loop.
#[pyfunction]
pub fn placer_place_by_proximity(
    n_components: usize,
    refs: Vec<String>,
    indices: Vec<Option<usize>>,
    base_x: f64,
    base_y: f64,
    zone: Option<(f64, f64, f64, f64)>,
    cos_sin: &Bound<'_, PyAny>,
) -> PyResult<(Vec<f32>, Vec<String>, Vec<String>)> {
    guard(|| {
        let cb = cos_sin_impl(cos_sin);
        placer_compute::place_by_proximity(
            n_components,
            &refs,
            &indices,
            base_x,
            base_y,
            zone,
            &cb,
        )
    })
}

/// `place_in_zone_center` compute: grid distribution around the zone center.
#[pyfunction]
pub fn placer_place_in_zone_center(
    n_components: usize,
    refs: Vec<String>,
    indices: Vec<Option<usize>>,
    center_x: f64,
    center_y: f64,
    zone: (f64, f64, f64, f64),
) -> PyResult<(Vec<f32>, Vec<String>, Vec<String>)> {
    guard(|| {
        Ok(placer_compute::place_in_zone_center(
            n_components,
            &refs,
            &indices,
            center_x,
            center_y,
            zone,
        ))
    })
}

/// `adjust_for_congestion` compute: the dtype-aware per-(bottleneck,
/// component) push loop. `dist_cb(dx, dy)` reproduces
/// `np.sqrt(dx**2 + dy**2)` in the caller's dtype; `uniform_cb()` is
/// `np.random.uniform(0, 2*pi)` drawn in the oracle's iteration order;
/// `cos_sin` applies to the random angle.
#[pyfunction]
#[allow(clippy::too_many_arguments)] // mirrors adjust_for_congestion's Python seam surface
pub fn placer_adjust_for_congestion(
    positions: Vec<f64>,
    is_f32: bool,
    fixed: Vec<bool>,
    bottlenecks: Vec<(f64, f64)>,
    push_strength: f64,
    influence_radius: f64,
    dist_cb: &Bound<'_, PyAny>,
    uniform_cb: &Bound<'_, PyAny>,
    cos_sin: &Bound<'_, PyAny>,
) -> PyResult<Vec<f64>> {
    guard(|| {
        let dist_impl = {
            let cb = dist_cb;
            move |dx: f64, dy: f64| -> PyResult<f64> {
                cb.call1((dx, dy))?.extract()
            }
        };
        let uniform_impl = {
            let cb = uniform_cb;
            move || -> PyResult<f64> { cb.call0()?.extract() }
        };
        let cos_sin_impl = cos_sin_impl(cos_sin);
        placer_compute::adjust_for_congestion(
            &positions,
            is_f32,
            &fixed,
            &bottlenecks,
            push_strength,
            influence_radius,
            &dist_impl,
            &uniform_impl,
            &cos_sin_impl,
        )
    })
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyFabPreset>()?;

    m.add_function(wrap_pyfunction!(is_plain_python_scalar, m)?)?;
    m.add_function(wrap_pyfunction!(deg_to_rad, m)?)?;
    m.add_function(wrap_pyfunction!(rad_to_deg, m)?)?;
    m.add_function(wrap_pyfunction!(mm_to_cell, m)?)?;
    m.add_function(wrap_pyfunction!(cell_to_mm, m)?)?;
    m.add_function(wrap_pyfunction!(distance_mm, m)?)?;
    m.add_function(wrap_pyfunction!(manhattan_distance_mm, m)?)?;
    m.add_function(wrap_pyfunction!(is_valid_layer, m)?)?;
    m.add_function(wrap_pyfunction!(is_valid_net_id, m)?)?;

    m.add_function(wrap_pyfunction!(is_ground_net, m)?)?;
    m.add_function(wrap_pyfunction!(is_power_net, m)?)?;
    m.add_function(wrap_pyfunction!(is_hv_net, m)?)?;
    m.add_function(wrap_pyfunction!(is_signal_net, m)?)?;
    m.add_function(wrap_pyfunction!(classify_net_type, m)?)?;
    m.add_function(wrap_pyfunction!(is_ground_pin, m)?)?;
    m.add_function(wrap_pyfunction!(is_power_pin, m)?)?;
    m.add_function(wrap_pyfunction!(is_hv_pin, m)?)?;
    m.add_function(wrap_pyfunction!(is_clock_pin, m)?)?;
    m.add_function(wrap_pyfunction!(is_power_net_v6, m)?)?;
    m.add_function(wrap_pyfunction!(is_signal_net_v6, m)?)?;
    m.add_function(wrap_pyfunction!(classify_net_type_v6, m)?)?;

    m.add_function(wrap_pyfunction!(inflated_clearance, m)?)?;
    m.add_function(wrap_pyfunction!(inflated_width, m)?)?;
    m.add_function(wrap_pyfunction!(get_fab_presets, m)?)?;

    // Wave-4 Phase 4: placer non-cp_sat compute kernels.
    m.add_function(wrap_pyfunction!(placer_apply_component_template, m)?)?;
    m.add_function(wrap_pyfunction!(placer_apply_parametric_template, m)?)?;
    m.add_function(wrap_pyfunction!(placer_place_power_stage_template, m)?)?;
    m.add_function(wrap_pyfunction!(placer_place_by_proximity, m)?)?;
    m.add_function(wrap_pyfunction!(placer_place_in_zone_center, m)?)?;
    m.add_function(wrap_pyfunction!(placer_adjust_for_congestion, m)?)?;
    Ok(())
}

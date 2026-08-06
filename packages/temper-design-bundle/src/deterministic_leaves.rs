//! Deterministic leaf-stage compute — Wave 4 **Phase 5, batch 2**
//! (deterministic leaf stages, remaining slice).
//!
//! Ports the pure compute of the remaining deterministic leaf stages to
//! Rust. The Python stages become delegation shims that keep their `run()`
//! orchestration (state guards, `frozenset` wraps, GEOS/shapely and
//! router_v6-bound surfaces) in Python; the pre-migration implementations
//! are pinned VERBATIM as the differential oracles in
//! `packages/temper-placer/tests/deterministic/stages/`
//! (`_*_py_oracle.py`); bit-exactness is asserted by the
//! `test_*_rust_differential.py` suites and the PBT suites; the structural
//! proof lives in `VERIFICATION.md`.
//!
//! Home-crate decision: `temper-design-bundle` hosts the placements /
//! component-math kernels (component_assignment, layer_assignment,
//! power_plane, fine_pitch_escape, phased_component_assignment_validator's
//! slot-grid kernels) and the leaf data contracts (sequential_routing_dataclasses
//! `DiffPairConfig`, routing_metrics), because they bind onto this crate's
//! contract pyclasses (`Netlist`/`Component`/`LayerAssignment`) — the same
//! rationale #762 recorded for `deterministic_stages.rs`. DRC-check stages
//! (courtyard_check / drc_sweep / drc_validation / placement_validation) land
//! in `temper-drc-rs`; GEOS/shapely- and router_v6-bound stages are recorded
//! R3-style in `VERIFICATION.md`.

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;


/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping (B9).
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does (B10): shortest
/// round-trip digits, `1e+300`/`1e-05` exponent form, `nan` not `NaN`.
fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..]; // drop 'e'/'E'
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

/// Render a numeric object the way CPython's dataclass repr does: if it is
/// a Python int, render via CPython's own `repr(int)` (so `1` not `1.0`);
/// otherwise render via the CPython `repr(float)` replica.
fn py_number_repr(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    if obj.is_instance_of::<pyo3::types::PyInt>() {
        return obj.repr().map(|r| r.to_string());
    }
    Ok(py_float_str(obj.extract::<f64>()?))
}

// ---------------------------------------------------------------------------
// DiffPairConfig — sequential_routing_dataclasses.py
// ---------------------------------------------------------------------------

/// `DiffPairConfig` — a five-field plain dataclass (two required strings,
/// three float defaults). The dataclass coerces nothing, so the three
/// numeric fields store the CALLER's object (an int stays int, exactly like
/// the oracle); the type-carrying differential canon pins that.
#[pyclass(module = "temper_design_bundle_python", subclass)]
#[derive(Debug)]
pub struct DiffPairConfig {
    net_pos: Py<PyAny>,
    net_neg: Py<PyAny>,
    spacing_mm: Py<PyAny>,
    coupling_tolerance_mm: Py<PyAny>,
    max_skew_mm: Py<PyAny>,
}

#[pymethods]
impl DiffPairConfig {
    /// Dataclass construction with defaults: `net_pos`/`net_neg` are
    /// required positional-or-keyword; `spacing_mm=0.15`,
    /// `coupling_tolerance_mm=0.5`, `max_skew_mm=0.5` are defaulted.
    #[new]
    #[pyo3(signature = (net_pos, net_neg, spacing_mm=None, coupling_tolerance_mm=None, max_skew_mm=None))]
    fn new(
        py: Python<'_>,
        net_pos: &Bound<'_, PyAny>,
        net_neg: &Bound<'_, PyAny>,
        spacing_mm: Option<&Bound<'_, PyAny>>,
        coupling_tolerance_mm: Option<&Bound<'_, PyAny>>,
        max_skew_mm: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(DiffPairConfig {
            net_pos: net_pos.clone().unbind(),
            net_neg: net_neg.clone().unbind(),
            spacing_mm: match spacing_mm {
                Some(v) => v.clone().unbind(),
                None => 0.15_f64.into_bound_py_any(py)?.unbind(),
            },
            coupling_tolerance_mm: match coupling_tolerance_mm {
                Some(v) => v.clone().unbind(),
                None => 0.5_f64.into_bound_py_any(py)?.unbind(),
            },
            max_skew_mm: match max_skew_mm {
                Some(v) => v.clone().unbind(),
                None => 0.5_f64.into_bound_py_any(py)?.unbind(),
            },
        })
    }

    #[getter]
    fn net_pos(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_pos.clone_ref(py)
    }
    #[setter]
    fn set_net_pos(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_pos = v.into_any().unbind();
    }

    #[getter]
    fn net_neg(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_neg.clone_ref(py)
    }
    #[setter]
    fn set_net_neg(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.net_neg = v.into_any().unbind();
    }

    #[getter]
    fn spacing_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.spacing_mm.clone_ref(py)
    }
    #[setter]
    fn set_spacing_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.spacing_mm = v.into_any().unbind();
    }

    #[getter]
    fn coupling_tolerance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.coupling_tolerance_mm.clone_ref(py)
    }
    #[setter]
    fn set_coupling_tolerance_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.coupling_tolerance_mm = v.into_any().unbind();
    }

    #[getter]
    fn max_skew_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.max_skew_mm.clone_ref(py)
    }
    #[setter]
    fn set_max_skew_mm(&mut self, _py: Python<'_>, v: Bound<'_, PyAny>) {
        self.max_skew_mm = v.into_any().unbind();
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let pos = self.net_pos.bind(py);
        let neg = self.net_neg.bind(py);
        Ok(format!(
            "DiffPairConfig(net_pos={}, net_neg={}, spacing_mm={}, coupling_tolerance_mm={}, max_skew_mm={})",
            py_str_repr(&pos.str()?.to_string()),
            py_str_repr(&neg.str()?.to_string()),
            py_number_repr(&self.spacing_mm.bind(py))?,
            py_number_repr(&self.coupling_tolerance_mm.bind(py))?,
            py_number_repr(&self.max_skew_mm.bind(py))?,
        ))
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let other = other.extract::<PyRef<'_, DiffPairConfig>>()?;
        let a = self.spacing_mm.bind(py);
        let b = other.spacing_mm.bind(py);
        Ok(self.net_pos.bind(py).eq(other.net_pos.bind(py))?
            && self.net_neg.bind(py).eq(other.net_neg.bind(py))?
            && a.eq(b)?
            && self
                .coupling_tolerance_mm
                .bind(py)
                .eq(other.coupling_tolerance_mm.bind(py))?
            && self.max_skew_mm.bind(py).eq(other.max_skew_mm.bind(py))?)
    }
}

// ---------------------------------------------------------------------------
// LayerAssignment — layer_assignment.py
// ---------------------------------------------------------------------------

/// `LayerAssignment` — a four-field frozen dataclass. `layer`/`allow_layer_change`/
/// `is_plane` are stored uncoerced (the dataclass coerces nothing) so an int
/// layer stays int.
#[pyclass(module = "temper_design_bundle_python", frozen, subclass)]
#[derive(Debug)]
pub struct LayerAssignment {
    net_name: Py<PyAny>,
    layer: Py<PyAny>,
    allow_layer_change: Py<PyAny>,
    is_plane: Py<PyAny>,
}

#[pymethods]
impl LayerAssignment {
    #[new]
    #[pyo3(signature = (net_name, layer, allow_layer_change=None, is_plane=None))]
    fn new(
        py: Python<'_>,
        net_name: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        allow_layer_change: Option<&Bound<'_, PyAny>>,
        is_plane: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(LayerAssignment {
            net_name: net_name.clone().unbind(),
            layer: layer.clone().unbind(),
            allow_layer_change: match allow_layer_change {
                Some(v) => v.clone().unbind(),
                None => true.into_bound_py_any(py)?.unbind(),
            },
            is_plane: match is_plane {
                Some(v) => v.clone().unbind(),
                None => false.into_bound_py_any(py)?.unbind(),
            },
        })
    }

    #[getter]
    fn net_name(&self, py: Python<'_>) -> Py<PyAny> {
        self.net_name.clone_ref(py)
    }
    #[getter]
    fn layer(&self, py: Python<'_>) -> Py<PyAny> {
        self.layer.clone_ref(py)
    }
    #[getter]
    fn allow_layer_change(&self, py: Python<'_>) -> Py<PyAny> {
        self.allow_layer_change.clone_ref(py)
    }
    #[getter]
    fn is_plane(&self, py: Python<'_>) -> Py<PyAny> {
        self.is_plane.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "LayerAssignment(net_name={}, layer={}, allow_layer_change={}, is_plane={})",
            py_str_repr(&self.net_name.bind(py).str()?.to_string()),
            self.layer.bind(py).repr()?,
            self.allow_layer_change.bind(py).repr()?,
            self.is_plane.bind(py).repr()?,
        ))
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let other = other.extract::<PyRef<'_, LayerAssignment>>()?;
        Ok(self.net_name.bind(py).eq(other.net_name.bind(py))?
            && self.layer.bind(py).eq(other.layer.bind(py))?
            && self
                .allow_layer_change
                .bind(py)
                .eq(other.allow_layer_change.bind(py))?
            && self.is_plane.bind(py).eq(other.is_plane.bind(py))?)
    }

    /// Frozen-dataclass hash: `hash((net_name, layer, allow_layer_change,
    /// is_plane))` via CPython's own tuple hash.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        crate::netlist_contracts::dataclass_hash(
            py,
            &[
                self.net_name.clone_ref(py),
                self.layer.clone_ref(py),
                self.allow_layer_change.clone_ref(py),
                self.is_plane.clone_ref(py),
            ],
        )
    }
}

/// Pure kernel: the net-class → (layer, is_plane) mapping table of
/// `LayerAssignmentStage._assign_layer_by_net_class`. An unknown net class
/// falls back to `(0, False)` exactly like the oracle's `dict.get`.
pub fn assign_layer_by_net_class(net_class: &str) -> (i64, bool) {
    match net_class {
        "HighVoltage" => (0, false),
        "Power" => (2, true),
        "PowerTrace" => (0, false),
        "Ground" => (1, true),
        "Signal" => (0, false),
        "Differential" => (0, false),
        "FinePitch" => (0, false),
        "FinePitchPower" => (2, true),
        _ => (0, false),
    }
}

/// Build one `LayerAssignment` Python object for a (net_name, layer, is_plane)
/// triple — the two construction shapes the oracle uses:
/// `(net_name, layer, True, is_plane)`.
fn build_layer_assignment<'py>(
    py: Python<'py>,
    net_name: &str,
    layer: i64,
    allow_layer_change: bool,
    is_plane: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let cls = py.get_type::<LayerAssignment>();
    Ok(cls.call1((net_name, layer, allow_layer_change, is_plane))?.into_any())
}

/// Run-loop kernel for `LayerAssignmentStage.run`: given the nets
/// (pyclass attribute surface `name`/`net_class`), the manual assignments
/// `{net_name: layer}`, and the config net-class overrides
/// `{net_name: net_class}`, produce the list of `LayerAssignment` objects in
/// net order.
///
/// Iteration order is `netlist.nets` order (a list — deterministic). The
/// manual-assignment branch infers plane status from the layer index
/// (`layer in (1, 2)`); the fallback resolves the net class as
/// `net_classes.get(net.name, net.net_class) or "Signal"`.
fn assign_layers_kernel<'py>(
    py: Python<'py>,
    nets: &Bound<'py, PyAny>,
    manual_assignments: &Bound<'py, PyDict>,
    net_classes: &Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out: Vec<Bound<'py, PyAny>> = Vec::new();
    for net in nets.try_iter()? {
        let net = net?;
        let name: String = net.getattr("name")?.extract()?;
        if let Some(layer_any) = manual_assignments.get_item(&name)? {
            let layer: i64 = layer_any.extract()?;
            let is_plane = layer == 1 || layer == 2;
            out.push(build_layer_assignment(py, &name, layer, true, is_plane)?);
            continue;
        }
        let net_class_raw: Option<String> = if let Some(nc) = net_classes.get_item(&name)? {
            Some(nc.extract()?)
        } else {
            net.getattr("net_class")?.extract()?
        };
        let net_class = match net_class_raw {
            Some(v) if !v.is_empty() => v,
            _ => "Signal".to_string(),
        };
        let (layer, is_plane) = assign_layer_by_net_class(&net_class);
        out.push(build_layer_assignment(py, &name, layer, true, is_plane)?);
    }
    Ok(out)
}

/// Python-visible net-class → (layer, is_plane) mapping-table lookup.
#[pyfunction]
pub fn assign_layer_by_net_class_py(net_class: &str) -> (i64, bool) {
    assign_layer_by_net_class(net_class)
}

/// Python-visible `assign_layers(nets, manual_assignments, net_classes)`
/// returning the assignment list.
#[pyfunction]
pub fn assign_layers<'py>(
    py: Python<'py>,
    nets: &Bound<'py, PyAny>,
    manual_assignments: &Bound<'py, PyDict>,
    net_classes: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyList>> {
    guard(|| {
        let items = assign_layers_kernel(py, nets, manual_assignments, net_classes)?;
        PyList::new(py, items)
    })
}

// ---------------------------------------------------------------------------
// PowerPlaneStage — power_plane.py
// ---------------------------------------------------------------------------

/// Pure kernel for `PowerPlaneStage.run`'s reassignment loop, operating on
/// marshalled primitives. Returns the new assignment triples in the oracle's
/// exact emission order:
///
/// 1. existing assignments in their original order, upgraded to
///    `is_plane=True` (and the plane layer) when the net is a plane net;
/// 2. plane nets not already assigned, in `plane_nets` iteration order
///    (a frozenset — but the oracle's `self.plane_nets` is a user-supplied
///    frozenset/list and `for net_name in self.plane_nets` iteration order is
///    only deterministic for the default `TEMPER_PLANE_NETS` literal;
///    callers that pass a set rely on it being the same set object; the
///    kernel iterates the caller-provided list exactly as the oracle would
///    iterate the same object);
/// 3. every netlist net without an assignment, in netlist order, as
///    `(layer=0, is_plane=False)`.
pub fn recompute_plane_assignments(
    existing: &[(String, i64, bool, bool)],
    plane_nets: &[String],
    plane_layers: &HashMap<String, i64>,
    all_nets: &[String],
) -> Vec<(String, i64, bool, bool)> {
    let plane: std::collections::HashSet<&str> =
        plane_nets.iter().map(|s| s.as_str()).collect();
    let mut out: Vec<(String, i64, bool, bool)> = Vec::with_capacity(existing.len() + all_nets.len());

    // 1. Existing assignments in order.
    for (net_name, layer, allow, is_plane) in existing {
        if plane.contains(net_name.as_str()) {
            let new_layer = plane_layers.get(net_name).copied().unwrap_or(1);
            out.push((net_name.clone(), new_layer, *allow, true));
        } else {
            out.push((net_name.clone(), *layer, *allow, *is_plane));
        }
    }

    // 2. Plane nets not already assigned (plane_nets iteration order).
    let mut assigned: std::collections::HashSet<String> =
        out.iter().map(|(n, _, _, _)| n.clone()).collect();
    for net_name in plane_nets {
        if !assigned.contains(net_name) && all_nets.iter().any(|n| n == net_name) {
            let layer = plane_layers.get(net_name).copied().unwrap_or(1);
            out.push((net_name.clone(), layer, true, true));
            assigned.insert(net_name.clone());
        }
    }

    // 3. Remaining netlist nets, netlist order, layer 0, non-plane.
    for net_name in all_nets {
        if !assigned.contains(net_name) {
            out.push((net_name.clone(), 0, true, false));
            assigned.insert(net_name.clone());
        }
    }
    out
}

/// Python-visible `recompute_plane_assignments(existing, plane_nets,
/// plane_layers, all_nets)` returning a list of `LayerAssignment` pyclasses.
#[pyfunction(name = "recompute_plane_assignments")]
pub fn recompute_plane_assignments_py<'py>(
    py: Python<'py>,
    existing: &Bound<'py, PyAny>,
    plane_nets: &Bound<'py, PyAny>,
    plane_layers: &Bound<'py, PyDict>,
    all_nets: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    guard(|| {
        let existing: Vec<(String, i64, bool, bool)> = existing
            .try_iter()?
            .map(|item| -> PyResult<(String, i64, bool, bool)> {
                let item = item?;
                let net_name: String = item.getattr("net_name")?.extract()?;
                let layer: i64 = item.getattr("layer")?.extract()?;
                let allow: bool = item.getattr("allow_layer_change")?.extract()?;
                let is_plane: bool = item.getattr("is_plane")?.extract()?;
                Ok((net_name, layer, allow, is_plane))
            })
            .collect::<PyResult<Vec<_>>>()?;

        let plane_nets: Vec<String> = plane_nets
            .try_iter()?
            .map(|item| item.and_then(|i| i.extract::<String>()))
            .collect::<PyResult<Vec<_>>>()?;

        let mut plane_layers_map: HashMap<String, i64> = HashMap::new();
        for (k, v) in plane_layers.iter() {
            plane_layers_map.insert(k.extract()?, v.extract()?);
        }

        let all_nets: Vec<String> = all_nets
            .try_iter()?
            .map(|item| item.and_then(|i| i.extract::<String>()))
            .collect::<PyResult<Vec<_>>>()?;

        let out = recompute_plane_assignments(&existing, &plane_nets, &plane_layers_map, &all_nets);
        let mut list_items: Vec<Bound<'py, PyAny>> = Vec::new();
        for (net_name, layer, allow, is_plane) in out {
            list_items.push(build_layer_assignment(py, &net_name, layer, allow, is_plane)?);
        }
        PyList::new(py, list_items)
    })
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as a submodule (`temper_design_bundle_python.deterministic_leaves`)
/// so the delegation shims and the differential/PBT suites can address the
/// migrated kernels by name. The pyclasses are registered at module top
/// level (matching the shim re-export path).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<DiffPairConfig>()?;
    module.add_class::<LayerAssignment>()?;

    let py = module.py();
    let sub = PyModule::new(py, "deterministic_leaves")?;
    sub.add_function(wrap_pyfunction!(assign_layer_by_net_class_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(assign_layers, &sub)?)?;
    sub.add_function(wrap_pyfunction!(recompute_plane_assignments_py, &sub)?)?;
    module.add_submodule(&sub)
}

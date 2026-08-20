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
//! `DiffPairConfig`), because they bind onto this crate's
//! contract pyclasses (`Netlist`/`Component`/`LayerAssignment`) — the same
//! rationale #762 recorded for `deterministic_stages.rs`. DRC-check stages
//! (courtyard_check / drc_sweep / drc_validation / placement_validation) land
//! in `temper-drc-rs`; GEOS/shapely- and router_v6-bound stages are recorded
//! R3-style in `VERIFICATION.md`.

use std::collections::{HashMap, HashSet};
use std::panic::AssertUnwindSafe;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::host_math::{pow, py_max, py_min, py_round, sqrt};


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
// ComponentAssignmentStage — component_assignment.py
// ---------------------------------------------------------------------------

/// A component's bounds, carrying each dimension's concrete Python type
/// (the oracle computes `w ** 2` as int-pow when `bounds` holds ints and as
/// libm `pow` when they are floats — the two differ in the last ulp).
#[derive(Clone, Copy, Debug)]
pub struct Bounds {
    pub w_int: bool,
    pub w: f64,
    pub h_int: bool,
    pub h: f64,
}

/// CPython `w ** 2` for a bounds dimension (int `**` int = exact int pow,
/// then widened to float at the sum; float `** 2` = libm `pow`).
fn sq_dim(is_int: bool, v: f64) -> f64 {
    if is_int {
        let i = v as i64;
        (i * i) as f64
    } else {
        pow(v, 2.0)
    }
}

/// `sqrt(w**2 + h**2) / 2 + 1.0` when bounds are present, else
/// `slot_spacing / 2.0` — `_get_footprint_radius`.
fn footprint_radius(bounds: Option<Bounds>, slot_spacing: f64) -> f64 {
    match bounds {
        Some(b) => {
            let w2 = sq_dim(b.w_int, b.w);
            let h2 = sq_dim(b.h_int, b.h);
            sqrt(w2 + h2) / 2.0 + 1.0
        }
        None => slot_spacing / 2.0,
    }
}

/// `sqrt(dx**2 + dy**2)` — the oracle's slot distance.
fn slot_dist(dx: f64, dy: f64) -> f64 {
    sqrt(pow(dx, 2.0) + pow(dy, 2.0))
}

/// `_reserve_slots`: add every slot within `radius` of `center` to
/// `used_slots`, iterating `all_slots` in order.
fn slot_key(s: (f64, f64)) -> (u64, u64) {
    (s.0.to_bits(), s.1.to_bits())
}

fn reserve_slots(
    center: (f64, f64),
    radius: f64,
    all_slots: &[(f64, f64)],
    used_slots: &mut HashSet<(u64, u64)>,
) {
    let (cx, cy) = center;
    for &(sx, sy) in all_slots {
        let dist = slot_dist(sx - cx, sy - cy);
        if dist <= radius {
            used_slots.insert(slot_key((sx, sy)));
        }
    }
}

/// `_get_footprint_radius`-style "size" used for the sort:
/// `max(comp.bounds)` when bounds present, else `0`.
fn get_size(bounds: Option<Bounds>) -> f64 {
    match bounds {
        Some(b) => py_max(b.w, b.h),
        None => 0.0,
    }
}

/// HPWL wirelength of placing `component_ref` at `candidate_slot`, given
/// the net-pin map and already-placed components — `_compute_wirelength`.
fn compute_wirelength(
    component_ref: &str,
    candidate_slot: (f64, f64),
    net_pins: &[(String, Vec<(String, String)>)],
    current_placements: &HashMap<String, (f64, f64)>,
) -> f64 {
    let mut total = 0.0;
    for (_net_name, pins) in net_pins {
        let component_on_net = pins.iter().any(|(r, _)| r == component_ref);
        if !component_on_net {
            continue;
        }
        let mut positions: Vec<(f64, f64)> = vec![candidate_slot];
        for (r, _) in pins {
            if r != component_ref && let Some(&p) = current_placements.get(r) {
                positions.push(p);
            }
        }
        if positions.len() > 1 {
            let mut x_min = positions[0].0;
            let mut x_max = positions[0].0;
            let mut y_min = positions[0].1;
            let mut y_max = positions[0].1;
            for &(px, py) in &positions {
                x_max = py_max(x_max, px);
                x_min = py_min(x_min, px);
                y_max = py_max(y_max, py);
                y_min = py_min(y_min, py);
            }
            total += (x_max - x_min) + (y_max - y_min);
        }
    }
    total
}

/// The greedy slot-assignment kernel. `components` is the netlist component
/// list in order; `net_pins` the net → pin-list map in netlist order;
/// `zone_slots` the (zone, slots) pairs in dict-insertion order;
/// `fixed_placements` the pre-resolved `{ref: (x, y)}` fixed placements;
/// `domain_ok` maps a component ref to the set of slots its HV/LV domain
/// region covers (empty/absent = no filter, NFR6).
///
/// Returns `(ref, x, y)` placements in assignment order.
pub fn assign_components_to_slots(
    components: &[(String, Option<Bounds>)],
    net_pins: &[(String, Vec<(String, String)>)],
    component_zone_map: &HashMap<String, String>,
    zone_slots: &[(String, Vec<(f64, f64)>)],
    fixed_placements: &[(String, (f64, f64))],
    domain_ok: &HashMap<String, HashSet<(u64, u64)>>,
    slot_spacing: f64,
) -> Vec<(String, f64, f64)> {
    let mut placements: HashMap<String, (f64, f64)> = HashMap::new();
    let mut placement_order: Vec<String> = Vec::new();
    let mut used_slots: HashSet<(u64, u64)> = HashSet::new();

    // Flatten all slots for reservation checks.
    let all_slots: Vec<(f64, f64)> =
        zone_slots.iter().flat_map(|(_, slots)| slots.iter().copied()).collect();

    // 1. Fixed placements first.
    for (ref_name, fixed_pos) in fixed_placements {
        let exists = components.iter().any(|(r, _)| r == ref_name);
        if !exists {
            continue; // sheetpath/ref lookup missed — ignored, like the oracle
        }
        let footprint_radius = footprint_radius(
            components.iter().find(|(r, _)| r == ref_name).map(|(_, b)| b).copied().flatten(),
            slot_spacing,
        );
        placements.insert(ref_name.clone(), *fixed_pos);
        placement_order.push(ref_name.clone());
        reserve_slots(*fixed_pos, footprint_radius, &all_slots, &mut used_slots);
    }

    // 2. Sort remaining components by (-size, ref) — Python's stable sort.
    let remaining: Vec<(String, Option<Bounds>)> = components
        .iter()
        .filter(|(r, _)| !placements.contains_key(r))
        .cloned()
        .collect();

    let mut sorted = remaining;
    sorted.sort_by(|a, b| {
        let size_a = get_size(a.1);
        let size_b = get_size(b.1);
        // Key is (-size, ref): descending size, ascending ref.
        match size_b.partial_cmp(&size_a) {
            Some(std::cmp::Ordering::Equal) | None => a.0.cmp(&b.0),
            Some(ord) => ord,
        }
    });

    let no_domain = domain_ok.is_empty();

    // 3. Greedy wirelength assignment.
    for (ref_name, bounds) in &sorted {
        let zone_name = component_zone_map.get(ref_name).cloned().unwrap_or_else(|| "Signal".to_string());
        let footprint_radius = footprint_radius(*bounds, slot_spacing);

        // Get available slots in this zone.
        let all_zone_slots: Vec<(f64, f64)> = zone_slots
            .iter()
            .find(|(z, _)| z == &zone_name)
            .map(|(_, slots)| slots.clone())
            .unwrap_or_default();
        let mut available_slots: Vec<(f64, f64)> =
            all_zone_slots.iter().copied().filter(|s| !used_slots.contains(&slot_key(*s))).collect();

        if available_slots.is_empty() {
            // Fallback: use any available slot from other zones.
            for (_other_zone, slots) in zone_slots {
                let found: Vec<(f64, f64)> =
                    slots.iter().copied().filter(|s| !used_slots.contains(&slot_key(*s))).collect();
                if !found.is_empty() {
                    available_slots = found;
                    break;
                }
            }
        }

        if available_slots.is_empty() {
            continue;
        }

        // Domain filter (precomputed by the shim from the GEOS region).
        if !no_domain && let Some(allowed) = domain_ok.get(ref_name) {
            available_slots.retain(|s| allowed.contains(&slot_key(*s)));
        }
        if available_slots.is_empty() {
            continue;
        }

        // Score each slot by wirelength (first minimum wins, like Python
        // `min`).
        let mut best_slot = available_slots[0];
        let mut best_score = compute_wirelength(ref_name, best_slot, net_pins, &placements);
        for &slot in &available_slots[1..] {
            let score = compute_wirelength(ref_name, slot, net_pins, &placements);
            if score < best_score {
                best_score = score;
                best_slot = slot;
            }
        }

        placements.insert(ref_name.clone(), best_slot);
        placement_order.push(ref_name.clone());
        reserve_slots(best_slot, footprint_radius, &all_slots, &mut used_slots);
    }

    placement_order
        .into_iter()
        .map(|r| {
            let (x, y) = placements[&r];
            (r, x, y)
        })
        .collect()
}

/// Python-visible `assign_components_to_slots` — marshals the netlist
/// pyclass + config dicts into the kernel and returns the placements dict.
#[pyfunction(name = "assign_components_to_slots")]
pub fn assign_components_to_slots_py<'py>(
    py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
    component_zone_map: &Bound<'py, PyDict>,
    zone_slots: &Bound<'py, PyDict>,
    fixed_placements: &Bound<'py, PyAny>,
    domain_ok: &Bound<'py, PyAny>,
    slot_spacing: f64,
) -> PyResult<Bound<'py, PyDict>> {
    guard(|| {
        let components = netlist.getattr("components")?;
        let nets = netlist.getattr("nets")?;

        let mut comps: Vec<(String, Option<Bounds>)> = Vec::new();
        for comp in components.try_iter()? {
            let comp = comp?;
            let ref_name: String = comp.getattr("ref")?.extract()?;
            let bounds = comp.getattr("bounds")?;
            let bounds = if bounds.is_none() {
                None
            } else {
                let w = bounds.get_item(0)?;
                let h = bounds.get_item(1)?;
                Some(Bounds {
                    w_int: w.is_instance_of::<pyo3::types::PyInt>(),
                    w: w.extract()?,
                    h_int: h.is_instance_of::<pyo3::types::PyInt>(),
                    h: h.extract()?,
                })
            };
            comps.push((ref_name, bounds));
        }

        let mut zone_map: HashMap<String, String> = HashMap::new();
        for (k, v) in component_zone_map.iter() {
            zone_map.insert(k.extract()?, v.extract()?);
        }

        let mut z_slots: Vec<(String, Vec<(f64, f64)>)> = Vec::new();
        for (k, v) in zone_slots.iter() {
            let zone: String = k.extract()?;
            let mut slots: Vec<(f64, f64)> = Vec::new();
            for item in v.try_iter()? {
                let item = item?;
                slots.push((item.get_item(0)?.extract()?, item.get_item(1)?.extract()?));
            }
            z_slots.push((zone, slots));
        }

        let mut fixed: Vec<(String, (f64, f64))> = Vec::new();
        // Fixed placements are pre-resolved by the shim to {ref: (x, y)}.
        if !fixed_placements.is_none() {
            let fp = fixed_placements.cast::<PyDict>()?;
            for (k, v) in fp.iter() {
                let ref_name: String = k.extract()?;
                let x: f64 = v.get_item(0)?.extract()?;
                let y: f64 = v.get_item(1)?.extract()?;
                fixed.push((ref_name, (x, y)));
            }
        }

        let mut dom_ok: HashMap<String, HashSet<(u64, u64)>> = HashMap::new();
        if !domain_ok.is_none() {
            let dok = domain_ok.cast::<PyDict>()?;
            for (k, v) in dok.iter() {
                let ref_name: String = k.extract()?;
                let mut allowed: HashSet<(u64, u64)> = HashSet::new();
                for item in v.try_iter()? {
                    let item = item?;
                    let x: f64 = item.get_item(0)?.extract()?;
                    let y: f64 = item.get_item(1)?.extract()?;
                    allowed.insert(slot_key((x, y)));
                }
                dom_ok.insert(ref_name, allowed);
            }
        }

        let mut net_pins: Vec<(String, Vec<(String, String)>)> = Vec::new();
        for net in nets.try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            let mut pins: Vec<(String, String)> = Vec::new();
            for pin in net.getattr("pins")?.try_iter()? {
                let pin = pin?;
                pins.push((pin.get_item(0)?.extract()?, pin.get_item(1)?.extract()?));
            }
            net_pins.push((name, pins));
        }

        let out = assign_components_to_slots(
            &comps, &net_pins, &zone_map, &z_slots, &fixed, &dom_ok, slot_spacing,
        );
        let dict = PyDict::new(py);
        for (r, x, y) in out {
            dict.set_item(&r, (x, y))?;
        }
        Ok(dict)
    })
}

// ---------------------------------------------------------------------------
// FinePitchEscapeStage — fine_pitch_escape.py
// ---------------------------------------------------------------------------

/// `_calculate_min_pin_pitch`: minimum pairwise pin distance (`dx*dx` —
/// direct multiplication, NOT `** 2`), `None` for fewer than two pins.
fn min_pin_pitch(pins: &[(f64, f64)]) -> Option<f64> {
    if pins.len() < 2 {
        return None;
    }
    let mut min_dist = f64::INFINITY;
    for i in 0..pins.len() {
        for j in (i + 1)..pins.len() {
            let (x1, y1) = pins[i];
            let (x2, y2) = pins[j];
            let dx = x1 - x2;
            let dy = y1 - y2;
            let dist = sqrt(dx * dx + dy * dy);
            min_dist = py_min(min_dist, dist);
        }
    }
    if min_dist != f64::INFINITY { Some(min_dist) } else { None }
}

/// `_get_escape_layer_for_net`: layer-3 nets → `(3, "B.Cu")`, layer-2 nets →
/// `(secondary, "In2.Cu")`, else `(primary, "In1.Cu")`.
fn escape_layer_for_net(
    net_name: &str,
    layer3_nets: &HashSet<String>,
    layer2_nets: &HashSet<String>,
    primary: i64,
    secondary: i64,
) -> (i64, &'static str) {
    if layer3_nets.contains(net_name) {
        return (3, "B.Cu");
    }
    if layer2_nets.contains(net_name) {
        return (secondary, "In2.Cu");
    }
    (primary, "In1.Cu")
}

/// Python-visible `min_pin_pitch(pins)` — pins is an iterable of objects
/// with a `.position` `(x, y)` attribute (the netlist `Pin` pyclass).
#[pyfunction]
pub fn min_pin_pitch_py(pins: &Bound<'_, PyAny>) -> PyResult<Option<f64>> {
    guard(|| {
        let mut positions: Vec<(f64, f64)> = Vec::new();
        for pin in pins.try_iter()? {
            let pin = pin?;
            let pos = pin.getattr("position")?;
            positions.push((pos.get_item(0)?.extract()?, pos.get_item(1)?.extract()?));
        }
        Ok(min_pin_pitch(&positions))
    })
}

/// Python-visible `escape_layer_for_net(net_name, layer2_nets,
/// layer3_nets, escape_layer, secondary_escape_layer)`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn escape_layer_for_net_py(
    net_name: &str,
    layer2_nets: &Bound<'_, PyAny>,
    layer3_nets: &Bound<'_, PyAny>,
    escape_layer: i64,
    secondary_escape_layer: i64,
) -> PyResult<(i64, String)> {
    guard(|| {
        let l2: HashSet<String> = layer2_nets
            .try_iter()?
            .map(|i| i.and_then(|x| x.extract::<String>()))
            .collect::<PyResult<_>>()?;
        let l3: HashSet<String> = layer3_nets
            .try_iter()?
            .map(|i| i.and_then(|x| x.extract::<String>()))
            .collect::<PyResult<_>>()?;
        let (layer, name) = escape_layer_for_net(net_name, &l3, &l2, escape_layer, secondary_escape_layer);
        Ok((layer, name.to_string()))
    })
}

// ---------------------------------------------------------------------------
// PhasedComponentAssignmentValidator — slot-grid kernels
// ---------------------------------------------------------------------------

/// The validator's `_DEFAULT_SLOT_SPACING` constant.
pub const DEFAULT_SLOT_SPACING: f64 = 5.0;

/// `_infer_slot_spacing`: minimum non-zero coordinate difference of the
/// flattened slot grid; falls back to `DEFAULT_SLOT_SPACING` for degenerate
/// inputs (fewer than 2 slots, or a uniform grid with no distinct coords).
fn infer_slot_spacing(slots: &[(f64, f64)]) -> f64 {
    if slots.len() < 2 {
        return DEFAULT_SLOT_SPACING;
    }
    let mut xs: Vec<f64> = slots.iter().map(|(x, _)| *x).collect();
    let mut ys: Vec<f64> = slots.iter().map(|(_, y)| *y).collect();
    xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    ys.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    xs.dedup();
    ys.dedup();
    let mut candidates: Vec<f64> = Vec::new();
    for w in xs.windows(2) {
        if w[1] > w[0] {
            candidates.push(w[1] - w[0]);
        }
    }
    for w in ys.windows(2) {
        if w[1] > w[0] {
            candidates.push(w[1] - w[0]);
        }
    }
    if candidates.is_empty() {
        return DEFAULT_SLOT_SPACING;
    }
    let mut it = candidates.iter().copied();
    let mut best = match it.next() {
        Some(b) => b,
        // `candidates` is non-empty here, so `next` always yields; the
        // fallback is unreachable and kept only to satisfy unwrap-free linting.
        None => return DEFAULT_SLOT_SPACING,
    };
    for c in it {
        best = py_min(best, c);
    }
    best
}

/// `int(round(x / spacing))` — CPython `round` (half-to-even) then `int`.
fn cell_index(x: f64, spacing: f64) -> i64 {
    py_round(x / spacing) as i64
}

/// `_build_slot_index`: `(i, j) -> [slots]` with `i = int(round(x/spacing))`,
/// `j = int(round(y/spacing))`; slots within a cell keep `all_slots` order.
/// Entries are returned in FIRST-SEEN key order (the oracle's
/// `dict.setdefault` insertion order) — never in HashMap iteration order,
/// which is randomized per process.
#[allow(clippy::type_complexity)]
fn build_slot_index(
    slots: &[(f64, f64)],
    spacing: f64,
) -> Vec<((i64, i64), Vec<(f64, f64)>)> {
    let mut pos: HashMap<(i64, i64), usize> = HashMap::new();
    let mut order: Vec<(i64, i64)> = Vec::new();
    let mut cells: Vec<Vec<(f64, f64)>> = Vec::new();
    for &slot in slots {
        let key = (cell_index(slot.0, spacing), cell_index(slot.1, spacing));
        match pos.get(&key) {
            Some(&idx) => cells[idx].push(slot),
            None => {
                pos.insert(key, cells.len());
                order.push(key);
                cells.push(vec![slot]);
            }
        }
    }
    order.into_iter().zip(cells).collect()
}

/// `_slots_within_radius`: walk the `(2k+1) x (2k+1)` cell window
/// (`k = ceil(radius / spacing)`), distance-check via `math.hypot`, in the
/// oracle's exact (di, dj) raster order with per-call de-dup.
fn slots_within_radius(
    center: (f64, f64),
    radius: f64,
    index: &HashMap<(i64, i64), Vec<(f64, f64)>>,
    spacing: f64,
) -> Vec<(f64, f64)> {
    if radius <= 0.0 || index.is_empty() {
        return Vec::new();
    }
    let k = (radius / spacing).ceil() as i64;
    let ci = cell_index(center.0, spacing);
    let cj = cell_index(center.1, spacing);
    let mut out: Vec<(f64, f64)> = Vec::new();
    let mut seen: HashSet<(u64, u64)> = HashSet::new();
    let (cx, cy) = center;
    for di in -k..=k {
        for dj in -k..=k {
            let cell = (ci + di, cj + dj);
            let Some(cell_slots) = index.get(&cell) else { continue };
            for &slot in cell_slots {
                if !seen.insert(slot_key(slot)) {
                    continue;
                }
                let (sx, sy) = slot;
                if crate::host_math::hypot(sx - cx, sy - cy) <= radius {
                    out.push(slot);
                }
            }
        }
    }
    out
}

/// Python-visible `infer_slot_spacing(slots)`.
#[pyfunction]
pub fn infer_slot_spacing_py(slots: &Bound<'_, PyAny>) -> PyResult<f64> {
    guard(|| {
        let flat = slots_to_vec(slots)?;
        Ok(infer_slot_spacing(&flat))
    })
}

/// Python-visible `build_slot_index(slots, spacing)` returning
/// `{(i, j): [slots]}` with `i = int(round(x/spacing))` (CPython
/// round-half-to-even). Insertion order follows `slots` order, exactly like
/// the oracle's `dict.setdefault` loop.
#[pyfunction]
pub fn build_slot_index_py<'py>(
    py: Python<'py>,
    slots: &Bound<'py, PyAny>,
    spacing: f64,
) -> PyResult<Bound<'py, PyDict>> {
    guard(|| {
        let flat = slots_to_vec(slots)?;
        let out = PyDict::new(py);
        for (key, cell) in build_slot_index(&flat, spacing) {
            let coords: Vec<Bound<'py, PyAny>> = cell
                .iter()
                .map(|&(x, y)| (x, y).into_bound_py_any(py))
                .collect::<PyResult<_>>()?;
            let list = PyList::new(py, coords)?;
            out.set_item(key, list)?;
        }
        Ok(out)
    })
}

/// Python-visible `slots_within_radius(center, radius, index, spacing)`
/// returning the slot list.
#[pyfunction]
pub fn slots_within_radius_py<'py>(
    py: Python<'py>,
    center: &Bound<'py, PyTuple>,
    radius: f64,
    index: &Bound<'py, PyDict>,
    spacing: f64,
) -> PyResult<Bound<'py, PyList>> {
    guard(|| {
        let cx: f64 = center.get_item(0)?.extract()?;
        let cy: f64 = center.get_item(1)?.extract()?;
        let idx = dict_index_to_rust(index)?;
        let out = slots_within_radius((cx, cy), radius, &idx, spacing);
        let mut items: Vec<Bound<'py, PyAny>> = Vec::new();
        for (x, y) in out {
            items.push((x, y).into_bound_py_any(py)?);
        }
        PyList::new(py, items)
    })
}

fn slots_to_vec(slots: &Bound<'_, PyAny>) -> PyResult<Vec<(f64, f64)>> {
    let mut out: Vec<(f64, f64)> = Vec::new();
    for item in slots.try_iter()? {
        let item = item?;
        out.push((item.get_item(0)?.extract()?, item.get_item(1)?.extract()?));
    }
    Ok(out)
}

#[allow(clippy::type_complexity)]
fn dict_index_to_rust(index: &Bound<'_, PyDict>) -> PyResult<HashMap<(i64, i64), Vec<(f64, f64)>>> {
    let mut idx: HashMap<(i64, i64), Vec<(f64, f64)>> = HashMap::new();
    for (k, v) in index.iter() {
        let i: i64 = k.get_item(0)?.extract()?;
        let j: i64 = k.get_item(1)?.extract()?;
        idx.insert((i, j), slots_to_vec(&v)?);
    }
    Ok(idx)
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as a submodule (`temper_design_bundle_python.deterministic_leaves`)
/// so the delegation shims and the differential/PBT suites can address the
/// migrated kernels by name. The pyclasses are registered at module top
/// level (matching the shim re-export path).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<LayerAssignment>()?;

    let py = module.py();
    let sub = PyModule::new(py, "deterministic_leaves")?;
    sub.add_function(wrap_pyfunction!(assign_layer_by_net_class_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(assign_layers, &sub)?)?;
    sub.add_function(wrap_pyfunction!(recompute_plane_assignments_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(assign_components_to_slots_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(min_pin_pitch_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(escape_layer_for_net_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(infer_slot_spacing_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(build_slot_index_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(slots_within_radius_py, &sub)?)?;
    module.add_submodule(&sub)
}

// ---------------------------------------------------------------------------
// Slot-grid kernel edge-case property tests
// ---------------------------------------------------------------------------
//
// The radius<=0 empty case is the kernel's pinned contract (the pre-migration
// oracle `if radius <= 0.0 or not index: return []`, reproduced verbatim at
// `slots_within_radius`). The Python PBT property p3 (inclusive radius
// membership) once over-asserted it for radius==0 and was reconciled to skip
// radius<=0 (commit 65760eb5e). These tests pin the kernel side of that
// contract and, separately, prove the positive-radius membership property the
// corrected p3 still relies on — so a future weakening of the kernel (e.g. a
// `ceil`->`floor` window mutant, or an `<=`->`<` distance mutant) fails here
// rather than silently passing both p3 and p4.
#[cfg(test)]
mod slot_grid_proptests {
    use super::*;
    use proptest::prelude::*;

    /// Naive O(N) reference scan — every slot whose CPython-`math.hypot`
    /// distance from `center` is `<= radius`. Deliberately shares no code with
    /// the cell-window walk under test (no `build_slot_index`, no raster
    /// order, no de-dup), so it is an independent oracle for membership.
    fn naive_within(center: (f64, f64), radius: f64, slots: &[(f64, f64)]) -> Vec<(f64, f64)> {
        let (cx, cy) = center;
        slots
            .iter()
            .copied()
            .filter(|&(sx, sy)| crate::host_math::hypot(sx - cx, sy - cy) <= radius)
            .collect()
    }

    fn index_map(slots: &[(f64, f64)], spacing: f64) -> HashMap<(i64, i64), Vec<(f64, f64)>> {
        build_slot_index(slots, spacing).into_iter().collect()
    }

    /// Bit-pattern key set (`slot_key`) — the same de-dup identity the kernel
    /// uses, so `-0.0` and `+0.0` stay distinct exactly as in the kernel.
    fn key_set(slots: impl IntoIterator<Item = (f64, f64)>) -> HashSet<(u64, u64)> {
        slots.into_iter().map(slot_key).collect()
    }

    fn coord() -> impl Strategy<Value = f64> {
        -50.0f64..50.0
    }

    fn spacing() -> impl Strategy<Value = f64> {
        1.0f64..10.0
    }

    fn positive_radius() -> impl Strategy<Value = f64> {
        1e-6f64..6.0
    }

    /// P3 (corrected): for positive radius the kernel returns EXACTLY the
    /// within-radius set — every returned slot is within radius and every
    /// within-radius slot is returned. Guards the cell-window completeness
    /// bound (k = ceil(radius/spacing)) and the inclusive `<=` distance check
    /// at once. The radius<=0 empty case is deliberately excluded: it is the
    /// kernel's documented empty contract, pinned by
    /// `nonpositive_radius_is_empty` below.
    #[test]
    fn within_radius_matches_naive_reference() {
        proptest!(|(
            slots in prop::collection::vec((coord(), coord()), 0..=16),
            spacing in spacing(),
            radius in positive_radius(),
            center in (coord(), coord()),
        )| {
            let idx = index_map(&slots, spacing);
            let got = key_set(slots_within_radius(center, radius, &idx, spacing));
            let exp = key_set(naive_within(center, radius, &slots));
            prop_assert_eq!(
                got,
                exp,
                "center={:?} radius={} spacing={} slots={:?}",
                center,
                radius,
                spacing,
                slots
            );
        });
    }

    /// A slot at distance EXACTLY `radius` must be included — the `<=` not
    /// `<`. This boundary is measure-zero under continuous random draws (the
    /// randomized property above can never hit it), so it is pinned
    /// deterministically with a 3-4-5 triangle (hypot == 5.0 exactly).
    #[test]
    fn within_radius_includes_slot_at_exactly_radius() {
        let slots = [(3.0, 4.0), (10.0, 10.0)];
        let idx = index_map(&slots, 5.0);
        assert_eq!(slots_within_radius((0.0, 0.0), 5.0, &idx, 5.0), vec![(3.0, 4.0)]);
        // And a slot just OUTSIDE is excluded — the radius is a closed ball.
        let just_out = [(3.0, 4.0), (5.0, 0.0)];
        let idx = index_map(&just_out, 5.0);
        let got = key_set(slots_within_radius((0.0, 0.0), 4.9, &idx, 5.0));
        assert!(!got.contains(&slot_key((5.0, 0.0))));
    }

    /// The ceil cell-window discriminator (the randomized completeness bound
    /// may miss it): radius 8.5 / spacing 5.0 -> k = ceil(1.7) = 2, and the
    /// slot (7.6, 0.0) rounds to cell (2, 0) — reachable only via the ceil
    /// window, so a `ceil`->`floor` mutant drops it.
    #[test]
    fn within_radius_ceil_window_discriminator() {
        let slots = [(7.6, 0.0), (0.0, 0.0)];
        let idx = index_map(&slots, 5.0);
        let got = key_set(slots_within_radius((0.0, 0.0), 8.5, &idx, 5.0));
        assert!(got.contains(&slot_key((7.6, 0.0))));
    }

    /// radius <= 0 (negative, and -0.0) is the empty case — the contract the
    /// p3 reconciliation delegates to. `radius == 0.0` with a center-
    /// coincident slot is pinned deterministically in
    /// `zero_radius_returns_empty_even_with_a_center_slot`.
    #[test]
    fn nonpositive_radius_is_empty() {
        proptest!(|(
            slots in prop::collection::vec((coord(), coord()), 0..=8),
            spacing in spacing(),
            radius in -10.0f64..0.0,
            center in (coord(), coord()),
        )| {
            let idx = index_map(&slots, spacing);
            prop_assert!(slots_within_radius(center, radius, &idx, spacing).is_empty());
        });
    }

    /// `radius == 0.0` with a slot EXACTLY at the center is the empty case —
    /// the exact input the p3 reconciliation (commit 65760eb5e) moved out of
    /// p3's inclusive-membership claim. Pinned deterministically: distance 0
    /// is `<= 0`, yet the kernel must still return nothing.
    #[test]
    fn zero_radius_returns_empty_even_with_a_center_slot() {
        let slots = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)];
        let idx = index_map(&slots, 5.0);
        assert!(slots_within_radius((0.0, 0.0), 0.0, &idx, 5.0).is_empty());
        // -0.0 is also <= 0.0 and must be empty.
        assert!(slots_within_radius((0.0, 0.0), -0.0, &idx, 5.0).is_empty());
    }

    #[test]
    fn empty_index_is_empty() {
        proptest!(|(
            spacing in spacing(),
            radius in positive_radius(),
            center in (coord(), coord()),
        )| {
            let idx: HashMap<(i64, i64), Vec<(f64, f64)>> = HashMap::new();
            prop_assert!(slots_within_radius(center, radius, &idx, spacing).is_empty());
        });
    }

    #[test]
    fn within_radius_is_deterministic() {
        proptest!(|(
            slots in prop::collection::vec((coord(), coord()), 0..=16),
            spacing in spacing(),
            radius in positive_radius(),
            center in (coord(), coord()),
        )| {
            let idx = index_map(&slots, spacing);
            let a = slots_within_radius(center, radius, &idx, spacing);
            let b = slots_within_radius(center, radius, &idx, spacing);
            prop_assert_eq!(a, b);
        });
    }

    /// Every slot within `radius` lands in a cell within Chebyshev
    /// `k = ceil(radius/spacing)` of the center's cell — the completeness
    /// bound a `ceil`->`floor` mutant breaks (the (7.6, 0.0) / radius 8.5 /
    /// spacing 5.0 discriminating case, randomized).
    #[test]
    fn cell_window_covers_every_within_radius_slot() {
        proptest!(|(
            slots in prop::collection::vec((coord(), coord()), 0..=16),
            spacing in spacing(),
            radius in positive_radius(),
            center in (coord(), coord()),
        )| {
            let idx = index_map(&slots, spacing);
            let got = key_set(slots_within_radius(center, radius, &idx, spacing));
            let (cx, cy) = center;
            for &slot in &slots {
                if crate::host_math::hypot(slot.0 - cx, slot.1 - cy) <= radius {
                    prop_assert!(
                        got.contains(&slot_key(slot)),
                        "within-radius slot {:?} dropped (center={:?} radius={} spacing={})",
                        slot,
                        center,
                        radius,
                        spacing
                    );
                }
            }
        });
    }

    /// `build_slot_index`: every slot appears in exactly one cell, that cell's
    /// key is `(round(x/spacing), round(y/spacing))`, and the total slot count
    /// is preserved.
    #[test]
    fn build_slot_index_partitions_slots() {
        proptest!(|(
            slots in prop::collection::vec((coord(), coord()), 0..=16),
            spacing in spacing(),
        )| {
            let idx = build_slot_index(&slots, spacing);
            let mut total = 0usize;
            for (key, cell) in &idx {
                let (i, j) = *key;
                for &(x, y) in cell {
                    prop_assert_eq!((i, j), (cell_index(x, spacing), cell_index(y, spacing)));
                    total += 1;
                }
            }
            prop_assert_eq!(total, slots.len());
        });
    }

    /// `infer_slot_spacing`: the minimum non-zero coordinate difference, or the
    /// 5.0 fallback for degenerate grids (fewer than 2 slots / no distinct
    /// coordinate).
    #[test]
    fn infer_slot_spacing_is_min_diff_or_fallback() {
        proptest!(|(slots in prop::collection::vec((coord(), coord()), 0..=12))| {
            let spacing = infer_slot_spacing(&slots);
            let mut xs: Vec<f64> = slots.iter().map(|s| s.0).collect();
            let mut ys: Vec<f64> = slots.iter().map(|s| s.1).collect();
            xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            ys.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
            let mut diffs: Vec<f64> = Vec::new();
            for w in xs.windows(2) {
                if w[1] > w[0] {
                    diffs.push(w[1] - w[0]);
                }
            }
            for w in ys.windows(2) {
                if w[1] > w[0] {
                    diffs.push(w[1] - w[0]);
                }
            }
            if diffs.is_empty() {
                prop_assert_eq!(spacing, DEFAULT_SLOT_SPACING);
            } else {
                // `diffs` is non-empty in this branch, so the index is safe.
                let mut best = diffs[0];
                for &c in &diffs[1..] {
                    best = py_min(best, c);
                }
                prop_assert_eq!(spacing, best);
            }
        });
    }
}

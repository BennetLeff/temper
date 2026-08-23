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
//! slot-grid kernels) and the leaf data contracts (the `LayerAssignment`
//! pyclass; the `DiffPairConfig` pyclass was deleted 2026-08-20 with the
//! orphaned sequential-routing dataclass cluster), because they bind onto
//! this crate's contract pyclasses (`Netlist`/`Component`/`LayerAssignment`)
//! — the same rationale #762 recorded for `deterministic_stages.rs`.
//! DRC-check stages (courtyard_check / drc_sweep / drc_validation /
//! placement_validation) land in `temper-drc-rs`; GEOS/shapely- and
//! router_v6-bound stages are recorded R3-style in `VERIFICATION.md`.

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
///
/// Uncalled since its only consumer, `py_number_repr` below, lost ITS caller.
/// Kept as a pair: five sibling modules (gates, loops, design_rules,
/// net_types, priority) carry their own byte-identical copy of this function
/// and all five are live, so the formula is load-bearing repo-wide -- this is
/// a stranded sixth copy, not a disproved one.
#[allow(dead_code)]
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
///
/// Uncalled. See `py_float_str` above, which this is the sole consumer of.
#[allow(dead_code)]
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

// --- BEGIN generated by scripts/gen_oracle_freeze.py: power_plane ---
    /// Frozen golden vectors for `recompute_plane_assignments` (FREEZE, batch 2).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec power_plane`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/power_plane.py's module docstring).
    #[cfg(test)]
    mod frozen_power_plane_tests {
        use super::*;
        use std::collections::HashMap;

        struct FrozenPowerPlaneCase {
            existing: &'static [(&'static str, i64, bool, bool)],
            plane_nets: &'static [&'static str],
            plane_layers: &'static [(&'static str, i64)],
            all_nets: &'static [&'static str],
            expected: &'static [(&'static str, i64, bool, bool)],
            tags: &'static [&'static str],
        }

        const FROZEN_POWER_PLANE_GOLDEN: &[FrozenPowerPlaneCase] = &[
            FrozenPowerPlaneCase {
                existing: &[("GND", 1i64, true, false), ("SPI_CLK", 0i64, true, false)],
                plane_nets: &["GND", "+5V"],
                plane_layers: &[("GND", 1i64), ("+5V", 2i64)],
                all_nets: &["GND", "SPI_CLK", "+5V"],
                expected: &[("GND", 1i64, true, true), ("SPI_CLK", 0i64, true, false), ("+5V", 2i64, true, true)],
                tags: &["existing_non_plane", "existing_upgrade", "kernel:recompute", "new_plane_added"],
            },
            FrozenPowerPlaneCase {
                existing: &[("SPI_CLK", 0i64, true, false)],
                plane_nets: &["GND"],
                plane_layers: &[("GND", 1i64)],
                all_nets: &["GND", "SPI_CLK"],
                expected: &[("SPI_CLK", 0i64, true, false), ("GND", 1i64, true, true)],
                tags: &["existing_non_plane", "kernel:recompute", "new_plane_added"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["GND"],
                plane_layers: &[],
                all_nets: &["GND"],
                expected: &[("GND", 1i64, true, true)],
                tags: &["kernel:recompute", "layer_fallback_1", "new_plane_added"],
            },
            FrozenPowerPlaneCase {
                existing: &[("GND", 0i64, true, false)],
                plane_nets: &["GND"],
                plane_layers: &[],
                all_nets: &["GND"],
                expected: &[("GND", 1i64, true, true)],
                tags: &["existing_upgrade", "kernel:recompute", "layer_fallback_1"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["SPI_CLK", "GATE_HI"],
                expected: &[("SPI_CLK", 0i64, true, false), ("GATE_HI", 0i64, true, false)],
                tags: &["kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("SPI_CLK", 0i64, false, false)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["SPI_CLK"],
                expected: &[("SPI_CLK", 0i64, false, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("GND", 1i64, true, false)],
                plane_nets: &["GND", "NONEXISTENT"],
                plane_layers: &[("GND", 1i64)],
                all_nets: &["GND"],
                expected: &[("GND", 1i64, true, true)],
                tags: &["existing_upgrade", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["GND"],
                plane_layers: &[("GND", 1i64)],
                all_nets: &[],
                expected: &[],
                tags: &["kernel:recompute", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &[],
                expected: &[],
                tags: &["empty_inputs", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("GND", 0i64, true, false)],
                plane_nets: &["GND"],
                plane_layers: &[("GND", 2i64)],
                all_nets: &["GND"],
                expected: &[("GND", 2i64, true, true)],
                tags: &["existing_upgrade", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("A", 0i64, true, false), ("B", 0i64, true, false)],
                plane_nets: &["Z"],
                plane_layers: &[("Z", 2i64)],
                all_nets: &["A", "B", "Z", "C"],
                expected: &[("A", 0i64, true, false), ("B", 0i64, true, false), ("Z", 2i64, true, true), ("C", 0i64, true, false)],
                tags: &["existing_non_plane", "kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("GND", 3i64, true, true)],
                plane_nets: &["GND"],
                plane_layers: &[("GND", 1i64)],
                all_nets: &["GND"],
                expected: &[("GND", 1i64, true, true)],
                tags: &["existing_upgrade", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("NET", 2i64, false, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["NET"],
                expected: &[("NET", 2i64, false, true)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("X", 0i64, true, false)],
                plane_nets: &["X"],
                plane_layers: &[("X", 4i64)],
                all_nets: &["X", "Y"],
                expected: &[("X", 4i64, true, true), ("Y", 0i64, true, false)],
                tags: &["existing_upgrade", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N1"],
                plane_layers: &[("N1", 3i64)],
                all_nets: &["N0"],
                expected: &[("N0", 0i64, true, false)],
                tags: &["kernel:recompute", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, true, false), ("N1", 1i64, false, true)],
                plane_nets: &["N0"],
                plane_layers: &[("N0", 3i64)],
                all_nets: &["N5"],
                expected: &[("N0", 3i64, true, true), ("N1", 1i64, false, true), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "existing_upgrade", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, true, false), ("N1", 0i64, true, true)],
                plane_nets: &["N4"],
                plane_layers: &[],
                all_nets: &["N4", "N5"],
                expected: &[("N0", 0i64, true, false), ("N1", 0i64, true, true), ("N4", 1i64, true, true), ("N5", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, false, false)],
                plane_nets: &["N1", "N2"],
                plane_layers: &[("N1", 0i64)],
                all_nets: &["N0", "N5"],
                expected: &[("N0", 0i64, false, false), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N0"],
                plane_layers: &[("N0", 3i64)],
                all_nets: &["N0", "N4"],
                expected: &[("N0", 3i64, true, true), ("N4", 0i64, true, false)],
                tags: &["kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, false, false), ("N1", 0i64, false, true), ("N2", 0i64, false, true)],
                plane_nets: &["N4"],
                plane_layers: &[],
                all_nets: &["N3"],
                expected: &[("N0", 1i64, false, false), ("N1", 0i64, false, true), ("N2", 0i64, false, true), ("N3", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, false), ("N1", 2i64, false, false)],
                plane_nets: &["N0", "N3", "N4"],
                plane_layers: &[("N3", 3i64), ("N4", 3i64)],
                all_nets: &["N1", "N5"],
                expected: &[("N0", 1i64, false, true), ("N1", 2i64, false, false), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_upgrade", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N0", "N1", "N3"],
                expected: &[("N0", 2i64, false, true), ("N1", 0i64, true, false), ("N3", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, false, false)],
                plane_nets: &["N0", "N2", "N3"],
                plane_layers: &[("N0", 3i64), ("N2", 2i64), ("N3", 2i64)],
                all_nets: &["N5"],
                expected: &[("N0", 3i64, false, true), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_upgrade", "kernel:recompute", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, true, false)],
                plane_nets: &["N3", "N5"],
                plane_layers: &[("N3", 3i64)],
                all_nets: &["N3"],
                expected: &[("N0", 0i64, true, false), ("N3", 3i64, true, true)],
                tags: &["existing_non_plane", "kernel:recompute", "layer_fallback_1", "new_plane_added", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N1", "N3", "N4"],
                plane_layers: &[("N1", 3i64), ("N3", 1i64)],
                all_nets: &["N1", "N2", "N3", "N4"],
                expected: &[("N1", 3i64, true, true), ("N3", 1i64, true, true), ("N4", 1i64, true, true), ("N2", 0i64, true, false)],
                tags: &["kernel:recompute", "layer_fallback_1", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, false, true), ("N1", 1i64, false, false)],
                plane_nets: &["N2", "N4", "N5"],
                plane_layers: &[("N2", 1i64), ("N5", 3i64)],
                all_nets: &[],
                expected: &[("N0", 1i64, false, true), ("N1", 1i64, false, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N5"],
                expected: &[("N0", 2i64, false, true), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N2", "N5"],
                plane_layers: &[("N2", 1i64), ("N5", 3i64)],
                all_nets: &["N1", "N3"],
                expected: &[("N1", 0i64, true, false), ("N3", 0i64, true, false)],
                tags: &["kernel:recompute", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, true, true), ("N1", 3i64, true, false), ("N2", 3i64, true, true)],
                plane_nets: &["N2", "N5"],
                plane_layers: &[("N2", 1i64), ("N5", 2i64)],
                all_nets: &["N2", "N4", "N5"],
                expected: &[("N0", 2i64, true, true), ("N1", 3i64, true, false), ("N2", 1i64, true, true), ("N5", 2i64, true, true), ("N4", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "existing_upgrade", "kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, true, false), ("N1", 1i64, true, false)],
                plane_nets: &["N0", "N4", "N5"],
                plane_layers: &[("N4", 1i64)],
                all_nets: &["N1", "N2"],
                expected: &[("N0", 1i64, true, true), ("N1", 1i64, true, false), ("N2", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_upgrade", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, true, true)],
                plane_nets: &["N1", "N2"],
                plane_layers: &[("N1", 0i64)],
                all_nets: &["N0", "N1", "N3"],
                expected: &[("N0", 1i64, true, true), ("N1", 0i64, true, true), ("N3", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "new_plane_added", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, true, true), ("N1", 2i64, true, true), ("N2", 2i64, true, false)],
                plane_nets: &["N3"],
                plane_layers: &[],
                all_nets: &[],
                expected: &[("N0", 3i64, true, true), ("N1", 2i64, true, true), ("N2", 2i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, false)],
                plane_nets: &["N4"],
                plane_layers: &[("N4", 1i64)],
                all_nets: &["N0", "N1"],
                expected: &[("N0", 2i64, false, false), ("N1", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "kernel:recompute", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, true, false)],
                plane_nets: &["N4"],
                plane_layers: &[("N4", 1i64)],
                all_nets: &["N2", "N3", "N4"],
                expected: &[("N0", 0i64, true, false), ("N4", 1i64, true, true), ("N2", 0i64, true, false), ("N3", 0i64, true, false)],
                tags: &["existing_non_plane", "kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, true)],
                plane_nets: &["N0", "N4"],
                plane_layers: &[("N4", 1i64)],
                all_nets: &["N0", "N1", "N3"],
                expected: &[("N0", 1i64, false, true), ("N1", 0i64, true, false), ("N3", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_upgrade", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, true, false)],
                plane_nets: &["N0", "N3"],
                plane_layers: &[("N0", 3i64), ("N3", 3i64)],
                all_nets: &["N0"],
                expected: &[("N0", 3i64, true, true)],
                tags: &["existing_upgrade", "kernel:recompute", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, true, true), ("N1", 3i64, false, true)],
                plane_nets: &["N2"],
                plane_layers: &[("N2", 3i64)],
                all_nets: &[],
                expected: &[("N0", 3i64, true, true), ("N1", 3i64, false, true)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, false, true), ("N1", 0i64, true, false), ("N2", 1i64, false, false)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N1", "N2", "N4", "N5"],
                expected: &[("N0", 0i64, false, true), ("N1", 0i64, true, false), ("N2", 1i64, false, false), ("N4", 0i64, true, false), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, false, false), ("N1", 1i64, false, false), ("N2", 3i64, false, false)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &[],
                expected: &[("N0", 1i64, false, false), ("N1", 1i64, false, false), ("N2", 3i64, false, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, true, false), ("N1", 2i64, true, true)],
                plane_nets: &["N4"],
                plane_layers: &[],
                all_nets: &["N3"],
                expected: &[("N0", 3i64, true, false), ("N1", 2i64, true, true), ("N3", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, true, false)],
                plane_nets: &["N2"],
                plane_layers: &[],
                all_nets: &[],
                expected: &[("N0", 1i64, true, false)],
                tags: &["existing_non_plane", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 0i64, true, false), ("N1", 3i64, false, true), ("N2", 3i64, true, true)],
                plane_nets: &["N2", "N3"],
                plane_layers: &[("N2", 3i64), ("N3", 2i64)],
                all_nets: &["N0", "N3", "N5"],
                expected: &[("N0", 0i64, true, false), ("N1", 3i64, false, true), ("N2", 3i64, true, true), ("N3", 2i64, true, true), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "existing_upgrade", "kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, true, false), ("N1", 3i64, false, true), ("N2", 2i64, false, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N0", "N2", "N4"],
                expected: &[("N0", 1i64, true, false), ("N1", 3i64, false, true), ("N2", 2i64, false, true), ("N4", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N0", "N1"],
                plane_layers: &[("N0", 2i64), ("N1", 2i64)],
                all_nets: &["N0"],
                expected: &[("N0", 2i64, true, true)],
                tags: &["kernel:recompute", "new_plane_added", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, true), ("N1", 0i64, true, true)],
                plane_nets: &["N0"],
                plane_layers: &[],
                all_nets: &["N2", "N4"],
                expected: &[("N0", 1i64, false, true), ("N1", 0i64, true, true), ("N2", 0i64, true, false), ("N4", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "existing_upgrade", "kernel:recompute", "layer_fallback_1", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, false, false), ("N1", 0i64, true, true), ("N2", 2i64, true, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &[],
                expected: &[("N0", 1i64, false, false), ("N1", 0i64, true, true), ("N2", 2i64, true, true)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, false, true), ("N1", 3i64, false, false), ("N2", 1i64, false, false)],
                plane_nets: &["N4"],
                plane_layers: &[("N4", 3i64)],
                all_nets: &["N1", "N3", "N4", "N5"],
                expected: &[("N0", 1i64, false, true), ("N1", 3i64, false, false), ("N2", 1i64, false, false), ("N4", 3i64, true, true), ("N3", 0i64, true, false), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 1i64, true, false), ("N1", 1i64, true, true), ("N2", 0i64, true, true)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N4", "N5"],
                expected: &[("N0", 1i64, true, false), ("N1", 1i64, true, true), ("N2", 0i64, true, true), ("N4", 0i64, true, false), ("N5", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, true, true)],
                plane_nets: &["N3", "N5"],
                plane_layers: &[],
                all_nets: &["N0", "N1"],
                expected: &[("N0", 3i64, true, true), ("N1", 0i64, true, false)],
                tags: &["existing_non_plane", "existing_plane_kept", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, false, true), ("N1", 1i64, true, true), ("N2", 2i64, true, false)],
                plane_nets: &["N5"],
                plane_layers: &[("N5", 2i64)],
                all_nets: &["N0"],
                expected: &[("N0", 2i64, false, true), ("N1", 1i64, true, true), ("N2", 2i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "plane_dropped_not_in_netlist"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 2i64, true, true), ("N1", 2i64, false, false)],
                plane_nets: &["N0", "N5"],
                plane_layers: &[],
                all_nets: &["N1", "N3", "N4"],
                expected: &[("N0", 1i64, true, true), ("N1", 2i64, false, false), ("N3", 0i64, true, false), ("N4", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_upgrade", "kernel:recompute", "layer_fallback_1", "plane_dropped_not_in_netlist", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, false, false)],
                plane_nets: &["N0"],
                plane_layers: &[("N0", 0i64)],
                all_nets: &["N1", "N3", "N5"],
                expected: &[("N0", 0i64, false, true), ("N1", 0i64, true, false), ("N3", 0i64, true, false), ("N5", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_upgrade", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[("N0", 3i64, true, false), ("N1", 0i64, false, true), ("N2", 2i64, false, false)],
                plane_nets: &[],
                plane_layers: &[],
                all_nets: &["N4"],
                expected: &[("N0", 3i64, true, false), ("N1", 0i64, false, true), ("N2", 2i64, false, false), ("N4", 0i64, true, false)],
                tags: &["allow_false_preserved", "existing_non_plane", "existing_plane_kept", "kernel:recompute", "remaining_layer0"],
            },
            FrozenPowerPlaneCase {
                existing: &[],
                plane_nets: &["N2"],
                plane_layers: &[("N2", 0i64)],
                all_nets: &["N0", "N1", "N2", "N3"],
                expected: &[("N2", 0i64, true, true), ("N0", 0i64, true, false), ("N1", 0i64, true, false), ("N3", 0i64, true, false)],
                tags: &["kernel:recompute", "new_plane_added", "remaining_layer0"],
            },
        ];

        #[test]
        fn frozen_power_plane_matches_golden_corpus() {
            for case in FROZEN_POWER_PLANE_GOLDEN {
                let existing: Vec<(String, i64, bool, bool)> = case.existing
                    .iter().map(|&(n, l, a, i)| (n.to_string(), l, a, i)).collect();
                let plane_nets: Vec<String> = case.plane_nets.iter().map(|s| s.to_string()).collect();
                let mut plane_layers: HashMap<String, i64> = HashMap::new();
                for &(k, v) in case.plane_layers { plane_layers.insert(k.to_string(), v); }
                let all_nets: Vec<String> = case.all_nets.iter().map(|s| s.to_string()).collect();
                let got = recompute_plane_assignments(&existing, &plane_nets, &plane_layers, &all_nets);
                let want: Vec<(String, i64, bool, bool)> = case.expected
                    .iter().map(|&(n, l, a, i)| (n.to_string(), l, a, i)).collect();
                assert_eq!(got, want, "tags={:?}", case.tags);
            }
        }

        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
        /// ever hand-edited down to something trivially satisfiable.
        #[test]
        fn frozen_power_plane_corpus_is_non_vacuous() {
            let n = FROZEN_POWER_PLANE_GOLDEN.len() as u32;
            let count = |tag: &str| FROZEN_POWER_PLANE_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(count("kernel:recompute") >= 10, "kernel:recompute: only {}/{} (need >= 10) -- recompute golden vectors must be present", count("kernel:recompute"), n);
            assert!(count("existing_upgrade") >= 4, "existing_upgrade: only {}/{} (need >= 4) -- existing plane-net assignment upgrade branch (is_plane=True)", count("existing_upgrade"), n);
            assert!(count("existing_non_plane") >= 4, "existing_non_plane: only {}/{} (need >= 4) -- existing non-plane assignment pass-through branch", count("existing_non_plane"), n);
            assert!(count("new_plane_added") >= 3, "new_plane_added: only {}/{} (need >= 3) -- plane net not in existing, present in netlist -> appended", count("new_plane_added"), n);
            assert!(count("plane_dropped_not_in_netlist") >= 2, "plane_dropped_not_in_netlist: only {}/{} (need >= 2) -- plane net absent from the netlist is silently dropped", count("plane_dropped_not_in_netlist"), n);
            assert!(count("layer_fallback_1") >= 2, "layer_fallback_1: only {}/{} (need >= 2) -- `plane_layers.get(net_name, 1)` default must be exercised", count("layer_fallback_1"), n);
            assert!(count("remaining_layer0") >= 3, "remaining_layer0: only {}/{} (need >= 3) -- netlist nets with no assignment -> layer 0, non-plane", count("remaining_layer0"), n);
            assert!(count("allow_false_preserved") >= 2, "allow_false_preserved: only {}/{} (need >= 2) -- allow_layer_change=False must survive the upgrade branch", count("allow_false_preserved"), n);
            assert!(count("empty_inputs") >= 1, "empty_inputs: only {}/{} (need >= 1) -- all-empty inputs must return the empty list", count("empty_inputs"), n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: power_plane ---

// --- BEGIN generated by scripts/gen_oracle_freeze.py: slot_grid_validator ---
    /// Frozen golden vectors for the validator slot-grid kernels
    /// `infer_slot_spacing` / `build_slot_index` / `slots_within_radius` (FREEZE, batch 2).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec slot_grid_validator`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/slot_grid_validator.py's module docstring).
    #[cfg(test)]
    mod frozen_slot_grid_tests {
        use super::*;
        use std::collections::HashMap;

        struct FrozenSpacingCase {
            slots: &'static [(f64, f64)],
            expected_bits: u64,
            tags: &'static [&'static str],
        }

        const FROZEN_SPACING_GOLDEN: &[FrozenSpacingCase] = &[
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected_bits: 0x3ff0000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected_bits: 0x4014000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[],
                expected_bits: 0x4014000000000000_u64,
                tags: &["kernel:spacing", "spacing_fallback_degenerate", "spacing_fallback_uniform"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected_bits: 0x4014000000000000_u64,
                tags: &["kernel:spacing", "spacing_fallback_degenerate", "spacing_fallback_uniform"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x4000000000000000_u64))],
                expected_bits: 0x3ff0000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4008000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4018000000000000_u64))],
                expected_bits: 0x4008000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4020000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected_bits: 0x4008000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FC999999999999A_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FD3333333333333_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FD999999999999A_u64), f64::from_bits(0x0000000000000000_u64))],
                expected_bits: 0x3fb9999999999998_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x4000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x4000000000000000_u64))],
                expected_bits: 0x4014000000000000_u64,
                tags: &["kernel:spacing", "spacing_fallback_uniform"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC008000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                expected_bits: 0x4008000000000000_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC01EE6E95924D1E8_u64), f64::from_bits(0x402C708AD188F430_u64)), (f64::from_bits(0xC031C192D2720C68_u64), f64::from_bits(0x4008D7CDE47E3650_u64)), (f64::from_bits(0xC02595898DB78DB7_u64), f64::from_bits(0x4030609B1868B6EC_u64))],
                expected_bits: 0x400142ad7d21e6a0_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC02D46661CC21E00_u64), f64::from_bits(0xC0308CCA1C02FC48_u64)), (f64::from_bits(0x40200A095BD00C2A_u64), f64::from_bits(0x40318BA8326295A4_u64)), (f64::from_bits(0x4030613BC870A704_u64), f64::from_bits(0xC0310F8E067F2270_u64)), (f64::from_bits(0x402C469641F651D8_u64), f64::from_bits(0xC02FCD601B73B570_u64))],
                expected_bits: 0x3fe0587d4f84c500_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x401A74DA57F56BE8_u64), f64::from_bits(0xC0331B15BD08ED9F_u64))],
                expected_bits: 0x4014000000000000_u64,
                tags: &["kernel:spacing", "spacing_fallback_degenerate", "spacing_fallback_uniform"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC021F1B0AC81D674_u64), f64::from_bits(0x403220F10328B634_u64)), (f64::from_bits(0xC0219007E0BE6EBA_u64), f64::from_bits(0xC02E669116EAEC47_u64)), (f64::from_bits(0x4028551184FFABC0_u64), f64::from_bits(0xC025D749297BA1F8_u64)), (f64::from_bits(0x403068B05D45E790_u64), f64::from_bits(0xC021F1DE3AAB4E5A_u64)), (f64::from_bits(0xC03330AD567C3B62_u64), f64::from_bits(0x3FE129AF63E41000_u64)), (f64::from_bits(0xC016EF950C87A116_u64), f64::from_bits(0xC02F77DC00955BF8_u64)), (f64::from_bits(0xC033456508479A64_u64), f64::from_bits(0xC0328D36C6EA2BC6_u64)), (f64::from_bits(0xC02B7AD232581EBE_u64), f64::from_bits(0x402F22E824EED2D4_u64))],
                expected_bits: 0x3fb4b7b1cb5f0200_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x400796C5B0490750_u64), f64::from_bits(0xC031F16D386F9EB1_u64)), (f64::from_bits(0x4022FCFA9AE4AC00_u64), f64::from_bits(0x400855217ED6DF48_u64)), (f64::from_bits(0x402B1FF140D2E9E4_u64), f64::from_bits(0xBF95A3124799CC00_u64)), (f64::from_bits(0xC0114E2544C0B5FC_u64), f64::from_bits(0xC02FFCABE088B1F4_u64))],
                expected_bits: 0x3fff317482b45b70_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x3FF0921C216210C0_u64), f64::from_bits(0xC032A0AE9BAAA090_u64)), (f64::from_bits(0xC00176D90F48F2E0_u64), f64::from_bits(0x4017E4A30BB4B74C_u64)), (f64::from_bits(0x401A7D631EEE1868_u64), f64::from_bits(0xC02806AD553CEB20_u64))],
                expected_bits: 0x4009bfe71ff9fb40_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x401BD7A0F0907848_u64), f64::from_bits(0x401A19ACB753AED8_u64)), (f64::from_bits(0xC019DE26BA2BF9DE_u64), f64::from_bits(0xC01E994CD82C83FA_u64)), (f64::from_bits(0xC0228E07E17CD24F_u64), f64::from_bits(0x4000927EFF162938_u64))],
                expected_bits: 0x40067bd2119b5580_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xBFE4DFBE3482A460_u64), f64::from_bits(0xBFF17A38001AFD10_u64)), (f64::from_bits(0x40295CC1DB8B6E88_u64), f64::from_bits(0xC02FDC9A2EB172F3_u64)), (f64::from_bits(0x4017821AC53918D4_u64), f64::from_bits(0xC030338C96FF0AF9_u64))],
                expected_bits: 0x3fd14fdfe9945fe0_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC02C12C9D39CDD37_u64), f64::from_bits(0x4032C2686B0E716A_u64)), (f64::from_bits(0x402A2BBCA27E8240_u64), f64::from_bits(0xC032B49F7B346CE7_u64)), (f64::from_bits(0x4009A591746640A0_u64), f64::from_bits(0xC01B84E66353C4CC_u64)), (f64::from_bits(0xBFFE1E5AB0311F80_u64), f64::from_bits(0x40278157DF9537CE_u64)), (f64::from_bits(0xC030DA3933490D9A_u64), f64::from_bits(0x4031A81EC1CB5E4C_u64)), (f64::from_bits(0x3FF6F955304AC770_u64), f64::from_bits(0xC021973F2E66AFA1_u64)), (f64::from_bits(0xC02C803EAD0A5FA6_u64), f64::from_bits(0xC00BDBC7CDF1D310_u64)), (f64::from_bits(0x402EBD87C3D88FFC_u64), f64::from_bits(0xC0267669BE54AD32_u64))],
                expected_bits: 0x3fcb5d365b609bc0_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC0320CED21D630C5_u64), f64::from_bits(0xBFE5DA682577CC20_u64)), (f64::from_bits(0xC0301BAFF528318F_u64), f64::from_bits(0x4032ACEC4DE4200E_u64)), (f64::from_bits(0xC02B4B16C4C98DBA_u64), f64::from_bits(0xC01B7D82EFBC8D50_u64)), (f64::from_bits(0x40308B3F790F5C38_u64), f64::from_bits(0xC00DA46FF08A7EB0_u64)), (f64::from_bits(0xC02928968758BEB8_u64), f64::from_bits(0x3FEB408EF34E9E40_u64)), (f64::from_bits(0x40095620B8FD7EC0_u64), f64::from_bits(0x4030C973085E780C_u64)), (f64::from_bits(0xC0147F40B574B674_u64), f64::from_bits(0xC01426C65A456EA0_u64))],
                expected_bits: 0x3ff11401eb867810_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x40100B2E25AD7C10_u64), f64::from_bits(0xC019DE0AFD6BF3FA_u64)), (f64::from_bits(0x401C0217EBC75CD8_u64), f64::from_bits(0x402E0405D7C9812C_u64)), (f64::from_bits(0xC028BF70B4CB022E_u64), f64::from_bits(0x403020B2DC639F12_u64)), (f64::from_bits(0x402C898D98B6A918_u64), f64::from_bits(0xC014F9B524820400_u64)), (f64::from_bits(0x40303C48DC77C780_u64), f64::from_bits(0xC033D9B3C915E559_u64)), (f64::from_bits(0x402D16B14FE042C0_u64), f64::from_bits(0xC02B54FC50EA746B_u64))],
                expected_bits: 0x3fd1a476e5333500_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC019DF68E0A2C6DC_u64), f64::from_bits(0xC032AF30DB0BF2FB_u64)), (f64::from_bits(0x403265F4FE774F74_u64), f64::from_bits(0xBFF0FFAB8A713420_u64)), (f64::from_bits(0xC0195386EBED284C_u64), f64::from_bits(0x3FE1753C380DA0A0_u64))],
                expected_bits: 0x3fc17c3e96b3d200_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0x400435A1A83A6EA0_u64), f64::from_bits(0x402535E551C48590_u64)), (f64::from_bits(0x402499EA2E10867C_u64), f64::from_bits(0x4015ED544CEB6448_u64)), (f64::from_bits(0xBFFAFDCF4E69E930_u64), f64::from_bits(0xC024B9B27F72608E_u64)), (f64::from_bits(0xBFF99B9A1A95E320_u64), f64::from_bits(0xC00CF36067138AC8_u64)), (f64::from_bits(0xC021460C084F0F8E_u64), f64::from_bits(0xC005A6BEAF1A1280_u64)), (f64::from_bits(0xC01E1EE5FB15FC7A_u64), f64::from_bits(0x3FE2522A627A5DC0_u64))],
                expected_bits: 0x3fb623533d406100_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
            FrozenSpacingCase {
                slots: &[(f64::from_bits(0xC033FE35F8EF3C71_u64), f64::from_bits(0xC031BA92FACB9756_u64)), (f64::from_bits(0x403155EAA72514C4_u64), f64::from_bits(0xC0310748B6D59A72_u64)), (f64::from_bits(0xC031980CFAEA9DE4_u64), f64::from_bits(0x4033C1B22488A042_u64)), (f64::from_bits(0xC03209956D022806_u64), f64::from_bits(0x40298A3924899920_u64)), (f64::from_bits(0xC030F16B7516ED8C_u64), f64::from_bits(0x400D7215F16DDA58_u64)), (f64::from_bits(0xC0331A8FBD291C5E_u64), f64::from_bits(0x402BE0DE89D71D88_u64)), (f64::from_bits(0x40107F8933BF7D0C_u64), f64::from_bits(0x401171F99E1ABCD0_u64)), (f64::from_bits(0xC0137FDD597B3C64_u64), f64::from_bits(0xBFF54309AC908420_u64))],
                expected_bits: 0x3fdc621c85e28880_u64,
                tags: &["kernel:spacing", "spacing_min_diff"],
            },
        ];

        // Frozen-fixture shape: the tuple nesting mirrors the oracle's
        // own return type exactly, which is the point of a frozen case --
        // a `type` alias here would hide the very shape the freeze pins.
        #[allow(clippy::type_complexity)]
        struct FrozenIndexCase {
            slots: &'static [(f64, f64)],
            spacing: f64,
            expected: &'static [((i64, i64), &'static [(f64, f64)])],
            tags: &'static [&'static str],
        }

        const FROZEN_INDEX_GOLDEN: &[FrozenIndexCase] = &[
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014666666666666_u64), f64::from_bits(0x4014666666666666_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[((0i64, 0i64), &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((1i64, 0i64), &[(f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((2i64, 0i64), &[(f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((0i64, 1i64), &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))]), ((1i64, 1i64), &[(f64::from_bits(0x4014666666666666_u64), f64::from_bits(0x4014666666666666_u64))])],
                tags: &["index_multi_cell", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x4029000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4029333333333333_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0xC029000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0xC004000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[((2i64, 0i64), &[(f64::from_bits(0x4029000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((3i64, 0i64), &[(f64::from_bits(0x4029333333333333_u64), f64::from_bits(0x0000000000000000_u64))]), ((-2i64, 0i64), &[(f64::from_bits(0xC029000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((0i64, 0i64), &[(f64::from_bits(0xC004000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                tags: &["index_half_even", "index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[],
                tags: &["index_empty", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x3FD0000000000000_u64), f64::from_bits(0x3FD0000000000000_u64)), (f64::from_bits(0x3FE8000000000000_u64), f64::from_bits(0x3FE8000000000000_u64))],
                spacing: f64::from_bits(0x3FF0000000000000_u64),
                expected: &[((0i64, 0i64), &[(f64::from_bits(0x3FD0000000000000_u64), f64::from_bits(0x3FD0000000000000_u64))]), ((1i64, 1i64), &[(f64::from_bits(0x3FE8000000000000_u64), f64::from_bits(0x3FE8000000000000_u64))])],
                tags: &["index_multi_cell", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x4026000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x4026000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[((0i64, 0i64), &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))]), ((2i64, 0i64), &[(f64::from_bits(0x4026000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))]), ((0i64, 2i64), &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x4026000000000000_u64))])],
                tags: &["index_multi_cell", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4032000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0xC02C000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                spacing: f64::from_bits(0x4010000000000000_u64),
                expected: &[((2i64, 0i64), &[(f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((4i64, 0i64), &[(f64::from_bits(0x4032000000000000_u64), f64::from_bits(0x0000000000000000_u64))]), ((-4i64, 0i64), &[(f64::from_bits(0xC02C000000000000_u64), f64::from_bits(0x0000000000000000_u64))])],
                tags: &["index_half_even", "index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x401E000000000000_u64), f64::from_bits(0x401E000000000000_u64)), (f64::from_bits(0x4029000000000000_u64), f64::from_bits(0x4029000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[((2i64, 2i64), &[(f64::from_bits(0x401E000000000000_u64), f64::from_bits(0x401E000000000000_u64)), (f64::from_bits(0x4029000000000000_u64), f64::from_bits(0x4029000000000000_u64))])],
                tags: &["index_half_even", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4020000000000000_u64)), (f64::from_bits(0x4022000000000000_u64), f64::from_bits(0x4028000000000000_u64))],
                spacing: f64::from_bits(0x4000000000000000_u64),
                expected: &[((2i64, 2i64), &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4010000000000000_u64))]), ((3i64, 4i64), &[(f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4020000000000000_u64))]), ((4i64, 6i64), &[(f64::from_bits(0x4022000000000000_u64), f64::from_bits(0x4028000000000000_u64))])],
                tags: &["index_half_even", "index_multi_cell", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC028D1A95498E6F4_u64), f64::from_bits(0x3FB108CA0BEC3700_u64)), (f64::from_bits(0x401C3812A3871878_u64), f64::from_bits(0xC001EEC442AB93B0_u64))],
                spacing: f64::from_bits(0x4012C48A18467923_u64),
                expected: &[((-3i64, 0i64), &[(f64::from_bits(0xC028D1A95498E6F4_u64), f64::from_bits(0x3FB108CA0BEC3700_u64))]), ((2i64, 0i64), &[(f64::from_bits(0x401C3812A3871878_u64), f64::from_bits(0xC001EEC442AB93B0_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[],
                spacing: f64::from_bits(0x40167B4A30B3964C_u64),
                expected: &[],
                tags: &["index_empty", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC031BF736794F156_u64), f64::from_bits(0x4020DEACC677A114_u64)), (f64::from_bits(0x401195BB3FE85FE4_u64), f64::from_bits(0xC0165F335EA01968_u64))],
                spacing: f64::from_bits(0x4018CC43DAA39A06_u64),
                expected: &[((-3i64, 1i64), &[(f64::from_bits(0xC031BF736794F156_u64), f64::from_bits(0x4020DEACC677A114_u64))]), ((1i64, -1i64), &[(f64::from_bits(0x401195BB3FE85FE4_u64), f64::from_bits(0xC0165F335EA01968_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x4022A4826EADCAA8_u64), f64::from_bits(0xC027E320722EC821_u64)), (f64::from_bits(0xC0233DE7C97BD25C_u64), f64::from_bits(0x402F437131EC0A20_u64)), (f64::from_bits(0x401233266D81BFE4_u64), f64::from_bits(0xC02C8F610195CB77_u64)), (f64::from_bits(0x3FDED6F4682BA240_u64), f64::from_bits(0x4032887E39718E04_u64))],
                spacing: f64::from_bits(0x401284011DC75CE6_u64),
                expected: &[((2i64, -3i64), &[(f64::from_bits(0x4022A4826EADCAA8_u64), f64::from_bits(0xC027E320722EC821_u64))]), ((-2i64, 3i64), &[(f64::from_bits(0xC0233DE7C97BD25C_u64), f64::from_bits(0x402F437131EC0A20_u64))]), ((1i64, -3i64), &[(f64::from_bits(0x401233266D81BFE4_u64), f64::from_bits(0xC02C8F610195CB77_u64))]), ((0i64, 4i64), &[(f64::from_bits(0x3FDED6F4682BA240_u64), f64::from_bits(0x4032887E39718E04_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x402567CB71410792_u64), f64::from_bits(0xC02C45CFE37988A2_u64)), (f64::from_bits(0x402BDB96D9A5CEC8_u64), f64::from_bits(0x4030AA96D85C4D64_u64)), (f64::from_bits(0xC0276539CF998E54_u64), f64::from_bits(0xC0041AF9FC4927F0_u64)), (f64::from_bits(0x4018E6D073C729CC_u64), f64::from_bits(0x3FFE2A4918CFC670_u64)), (f64::from_bits(0xC01F903327E6961E_u64), f64::from_bits(0x402BDF1FE79B5758_u64)), (f64::from_bits(0xC0252CE008953CF6_u64), f64::from_bits(0xC02F9ED1724F4898_u64)), (f64::from_bits(0xC01113C930D52910_u64), f64::from_bits(0x402C8F4BED0E8464_u64)), (f64::from_bits(0x3FED87C82EC7B780_u64), f64::from_bits(0xC0301C675FE82B06_u64))],
                spacing: f64::from_bits(0x4013AF4CCEF60829_u64),
                expected: &[((2i64, -3i64), &[(f64::from_bits(0x402567CB71410792_u64), f64::from_bits(0xC02C45CFE37988A2_u64))]), ((3i64, 3i64), &[(f64::from_bits(0x402BDB96D9A5CEC8_u64), f64::from_bits(0x4030AA96D85C4D64_u64))]), ((-2i64, -1i64), &[(f64::from_bits(0xC0276539CF998E54_u64), f64::from_bits(0xC0041AF9FC4927F0_u64))]), ((1i64, 0i64), &[(f64::from_bits(0x4018E6D073C729CC_u64), f64::from_bits(0x3FFE2A4918CFC670_u64))]), ((-2i64, 3i64), &[(f64::from_bits(0xC01F903327E6961E_u64), f64::from_bits(0x402BDF1FE79B5758_u64))]), ((-2i64, -3i64), &[(f64::from_bits(0xC0252CE008953CF6_u64), f64::from_bits(0xC02F9ED1724F4898_u64))]), ((-1i64, 3i64), &[(f64::from_bits(0xC01113C930D52910_u64), f64::from_bits(0x402C8F4BED0E8464_u64))]), ((0i64, -3i64), &[(f64::from_bits(0x3FED87C82EC7B780_u64), f64::from_bits(0xC0301C675FE82B06_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x4024452EE2CD2F98_u64), f64::from_bits(0xBFE73DFE763841A0_u64)), (f64::from_bits(0x401C95604A7E400C_u64), f64::from_bits(0x40208F167F361D08_u64)), (f64::from_bits(0xC02D583BCC5AEB16_u64), f64::from_bits(0x40293463A02424C0_u64))],
                spacing: f64::from_bits(0x401E830265B84695_u64),
                expected: &[((1i64, 0i64), &[(f64::from_bits(0x4024452EE2CD2F98_u64), f64::from_bits(0xBFE73DFE763841A0_u64))]), ((1i64, 1i64), &[(f64::from_bits(0x401C95604A7E400C_u64), f64::from_bits(0x40208F167F361D08_u64))]), ((-2i64, 2i64), &[(f64::from_bits(0xC02D583BCC5AEB16_u64), f64::from_bits(0x40293463A02424C0_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC0310AA8D5C86AF8_u64), f64::from_bits(0x40315C3E130DC866_u64)), (f64::from_bits(0xC02D2E5656C65732_u64), f64::from_bits(0x40187B0A57DFFC24_u64)), (f64::from_bits(0x40128015D81D228C_u64), f64::from_bits(0xC030800B063AF2DE_u64)), (f64::from_bits(0xC024D67821599314_u64), f64::from_bits(0x40140ACC2F15A780_u64)), (f64::from_bits(0xC02B6871192E1D12_u64), f64::from_bits(0xC025627C28D333B9_u64))],
                spacing: f64::from_bits(0x400654FACBA98FE5_u64),
                expected: &[((-6i64, 6i64), &[(f64::from_bits(0xC0310AA8D5C86AF8_u64), f64::from_bits(0x40315C3E130DC866_u64))]), ((-5i64, 2i64), &[(f64::from_bits(0xC02D2E5656C65732_u64), f64::from_bits(0x40187B0A57DFFC24_u64))]), ((2i64, -6i64), &[(f64::from_bits(0x40128015D81D228C_u64), f64::from_bits(0xC030800B063AF2DE_u64))]), ((-4i64, 2i64), &[(f64::from_bits(0xC024D67821599314_u64), f64::from_bits(0x40140ACC2F15A780_u64))]), ((-5i64, -4i64), &[(f64::from_bits(0xC02B6871192E1D12_u64), f64::from_bits(0xC025627C28D333B9_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x402925DAEA6B8570_u64), f64::from_bits(0x4027034FF8AFB23C_u64))],
                spacing: f64::from_bits(0x4006962FFC055E36_u64),
                expected: &[((4i64, 4i64), &[(f64::from_bits(0x402925DAEA6B8570_u64), f64::from_bits(0x4027034FF8AFB23C_u64))])],
                tags: &["kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0x400321692936B470_u64), f64::from_bits(0x3FEFE409E4D45EC0_u64)), (f64::from_bits(0x40237C3FE9A7C462_u64), f64::from_bits(0xC0307C92DF8712BE_u64)), (f64::from_bits(0x40324ECA718D7908_u64), f64::from_bits(0xC021A9D344EEDC0A_u64)), (f64::from_bits(0x403309C89E84B0FE_u64), f64::from_bits(0xC030C84BF143A0F1_u64))],
                spacing: f64::from_bits(0x401FE22CCE170B00_u64),
                expected: &[((0i64, 0i64), &[(f64::from_bits(0x400321692936B470_u64), f64::from_bits(0x3FEFE409E4D45EC0_u64))]), ((1i64, -2i64), &[(f64::from_bits(0x40237C3FE9A7C462_u64), f64::from_bits(0xC0307C92DF8712BE_u64))]), ((2i64, -1i64), &[(f64::from_bits(0x40324ECA718D7908_u64), f64::from_bits(0xC021A9D344EEDC0A_u64))]), ((2i64, -2i64), &[(f64::from_bits(0x403309C89E84B0FE_u64), f64::from_bits(0xC030C84BF143A0F1_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC01D205F80260958_u64), f64::from_bits(0x402426210039E9B6_u64)), (f64::from_bits(0xC030BBE6DFCF2D20_u64), f64::from_bits(0x4030FD3EC58629EE_u64)), (f64::from_bits(0xC033D798C252D60C_u64), f64::from_bits(0x4029182689EC9FF0_u64)), (f64::from_bits(0xC0309CEBD2D22626_u64), f64::from_bits(0xBFAEBDA666462000_u64)), (f64::from_bits(0xC031660A924AB7C2_u64), f64::from_bits(0xC0339916DC0CC4C7_u64))],
                spacing: f64::from_bits(0x400AD221CB92418E_u64),
                expected: &[((-2i64, 3i64), &[(f64::from_bits(0xC01D205F80260958_u64), f64::from_bits(0x402426210039E9B6_u64))]), ((-5i64, 5i64), &[(f64::from_bits(0xC030BBE6DFCF2D20_u64), f64::from_bits(0x4030FD3EC58629EE_u64))]), ((-6i64, 4i64), &[(f64::from_bits(0xC033D798C252D60C_u64), f64::from_bits(0x4029182689EC9FF0_u64))]), ((-5i64, 0i64), &[(f64::from_bits(0xC0309CEBD2D22626_u64), f64::from_bits(0xBFAEBDA666462000_u64))]), ((-5i64, -6i64), &[(f64::from_bits(0xC031660A924AB7C2_u64), f64::from_bits(0xC0339916DC0CC4C7_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC02C97428715A4C8_u64), f64::from_bits(0xBFF173A4645202B0_u64)), (f64::from_bits(0x401FDE151BE00068_u64), f64::from_bits(0x401CC6DE6443F018_u64)), (f64::from_bits(0x401EF308D424091C_u64), f64::from_bits(0x402DCFB1E84685A8_u64))],
                spacing: f64::from_bits(0x401BF3F98CA683E1_u64),
                expected: &[((-2i64, 0i64), &[(f64::from_bits(0xC02C97428715A4C8_u64), f64::from_bits(0xBFF173A4645202B0_u64))]), ((1i64, 1i64), &[(f64::from_bits(0x401FDE151BE00068_u64), f64::from_bits(0x401CC6DE6443F018_u64))]), ((1i64, 2i64), &[(f64::from_bits(0x401EF308D424091C_u64), f64::from_bits(0x402DCFB1E84685A8_u64))])],
                tags: &["index_multi_cell", "index_negative_key", "kernel:index"],
            },
            FrozenIndexCase {
                slots: &[(f64::from_bits(0xC033240C1533C1D4_u64), f64::from_bits(0xC0204CBF8E771224_u64))],
                spacing: f64::from_bits(0x3FF971A69D79D4C6_u64),
                expected: &[((-12i64, -5i64), &[(f64::from_bits(0xC033240C1533C1D4_u64), f64::from_bits(0xC0204CBF8E771224_u64))])],
                tags: &["index_negative_key", "kernel:index"],
            },
        ];

        struct FrozenWithinCase {
            center: (f64, f64),
            radius: f64,
            slots: &'static [(f64, f64)],
            spacing: f64,
            expected: &'static [(f64, f64)],
            tags: &'static [&'static str],
        }

        const FROZEN_WITHIN_GOLDEN: &[FrozenWithinCase] = &[
            FrozenWithinCase {
                center: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                radius: f64::from_bits(0x4018000000000000_u64),
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                radius: f64::from_bits(0x401399999999999A_u64),
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)),
                radius: f64::from_bits(0x4020000000000000_u64),
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                radius: f64::from_bits(0x0000000000000000_u64),
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[],
                tags: &["kernel:within", "within_empty_radius", "within_nonempty", "within_radius_inclusive"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                radius: f64::from_bits(0x3FF0000000000000_u64),
                slots: &[],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[],
                tags: &["kernel:within", "within_empty_index"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                radius: f64::from_bits(0x4014000000000000_u64),
                slots: &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                spacing: f64::from_bits(0x4014000000000000_u64),
                expected: &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4010000000000000_u64))],
                tags: &["kernel:within", "within_nonempty", "within_radius_inclusive"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x3FE0000000000000_u64), f64::from_bits(0x3FE0000000000000_u64)),
                radius: f64::from_bits(0x4000000000000000_u64),
                slots: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4000000000000000_u64))],
                spacing: f64::from_bits(0x3FF0000000000000_u64),
                expected: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x400C41D99DF07700_u64), f64::from_bits(0x3FE47CA6C774B200_u64)),
                radius: f64::from_bits(0x400266842A68750D_u64),
                slots: &[(f64::from_bits(0x4030317190AB16BE_u64), f64::from_bits(0xC02E46925C044EBC_u64)), (f64::from_bits(0xC00860A5D7897378_u64), f64::from_bits(0x4023769599901110_u64)), (f64::from_bits(0x4023EFF3C8186556_u64), f64::from_bits(0xC01915447C500E62_u64)), (f64::from_bits(0x402D74C4E464B578_u64), f64::from_bits(0xC02C3D80D15E3874_u64)), (f64::from_bits(0x402788A7E4D12D84_u64), f64::from_bits(0xC0337A441B3D67F4_u64)), (f64::from_bits(0xBFD0987DC24AF900_u64), f64::from_bits(0x402687B9BFCCF83A_u64)), (f64::from_bits(0xC03185FDD3A9B67A_u64), f64::from_bits(0xC01DE062B135E7C0_u64))],
                spacing: f64::from_bits(0x402266E5E9F4AFA6_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC0223278D5EAFFBD_u64), f64::from_bits(0x4017C0443BCFDF46_u64)),
                radius: f64::from_bits(0x401DFE20A6803747_u64),
                slots: &[(f64::from_bits(0x402C65E82F6A0C00_u64), f64::from_bits(0x402BC0F649460B58_u64)), (f64::from_bits(0xC0321944A596E7C5_u64), f64::from_bits(0xC012501623F8EB44_u64))],
                spacing: f64::from_bits(0x401D3662564B5BA0_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC0229ACF652F84ED_u64), f64::from_bits(0x40158DA3C9FF4164_u64)),
                radius: f64::from_bits(0x40265F78A9E0C882_u64),
                slots: &[(f64::from_bits(0x3FF4D91FE396D940_u64), f64::from_bits(0x401587DFB0A7D610_u64)), (f64::from_bits(0xC01A4FF128B8BDC4_u64), f64::from_bits(0xC01D42BEDD195C74_u64)), (f64::from_bits(0x401C9BAD6C2C1240_u64), f64::from_bits(0xBFADF7D5970B2000_u64)), (f64::from_bits(0xC02DAAB5C5C15D39_u64), f64::from_bits(0xC02D35582F6E03F5_u64)), (f64::from_bits(0x4017FA9C21513E40_u64), f64::from_bits(0xC01F30C3C6DDA354_u64)), (f64::from_bits(0x402CF1DD5DBD8648_u64), f64::from_bits(0xC0302C59588A0CCB_u64))],
                spacing: f64::from_bits(0x400DE670191D30DD_u64),
                expected: &[(f64::from_bits(0x3FF4D91FE396D940_u64), f64::from_bits(0x401587DFB0A7D610_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x3FF153B3E33F1FF0_u64), f64::from_bits(0xC012D63513511D12_u64)),
                radius: f64::from_bits(0x4017AD7E22FA2013_u64),
                slots: &[],
                spacing: f64::from_bits(0x4010CD9348E0F120_u64),
                expected: &[],
                tags: &["kernel:within", "within_empty_index"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC0128769C90BECEC_u64), f64::from_bits(0xC022899DA4EDBEE4_u64)),
                radius: f64::from_bits(0x4020235EFEED846F_u64),
                slots: &[(f64::from_bits(0xC00D392F038292F0_u64), f64::from_bits(0xC02ECBC93B7956FC_u64)), (f64::from_bits(0x4018772F769ED1F0_u64), f64::from_bits(0xC027A2895A2553EE_u64))],
                spacing: f64::from_bits(0x3FF55473B610A4EE_u64),
                expected: &[(f64::from_bits(0xC00D392F038292F0_u64), f64::from_bits(0xC02ECBC93B7956FC_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC021B29D52F2BDDB_u64), f64::from_bits(0xC0087F04A1D19BA4_u64)),
                radius: f64::from_bits(0x400530CCAACF3F22_u64),
                slots: &[(f64::from_bits(0x4007D074DF0006B0_u64), f64::from_bits(0xC01D4A52DF1332E4_u64))],
                spacing: f64::from_bits(0x4018A50F1910BE52_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC012A5343F8E4860_u64), f64::from_bits(0x402169712DCC8C70_u64)),
                radius: f64::from_bits(0x4024C00BE0A2E0F8_u64),
                slots: &[(f64::from_bits(0x4027E7FCC9054954_u64), f64::from_bits(0x4033B3FCBBB06F8C_u64)), (f64::from_bits(0xC0337468991ECFF6_u64), f64::from_bits(0xC02F56BDB4B5BAC5_u64)), (f64::from_bits(0x402A9F8FA5FE5340_u64), f64::from_bits(0xC02E083A2BADAF6A_u64)), (f64::from_bits(0xC032A8E6C2BA9584_u64), f64::from_bits(0x4025570125D6101C_u64))],
                spacing: f64::from_bits(0x4020F841A077B33D_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x402160132B88EA1C_u64), f64::from_bits(0x400624E4857D5EF8_u64)),
                radius: f64::from_bits(0x4013B7B3979CC846_u64),
                slots: &[(f64::from_bits(0xC0201C57EF311F7D_u64), f64::from_bits(0x40195176FA9494CC_u64)), (f64::from_bits(0x402578464FF3172C_u64), f64::from_bits(0xC03279FBA299CAED_u64)), (f64::from_bits(0xC02692D14746CFFA_u64), f64::from_bits(0xC030B3F100DDFF5D_u64)), (f64::from_bits(0x4019BE3F270A96D0_u64), f64::from_bits(0xC028245394A38E20_u64)), (f64::from_bits(0xBFCDDD7C8BD63400_u64), f64::from_bits(0x403182E4957EC10E_u64)), (f64::from_bits(0xC030C30ADF6F44D2_u64), f64::from_bits(0xC0209A7908A1150C_u64)), (f64::from_bits(0xC017499ED15C9E94_u64), f64::from_bits(0xC030E8CEB8FB38BF_u64)), (f64::from_bits(0xC01D4E377E4F75C4_u64), f64::from_bits(0x402B6CFF0E447748_u64))],
                spacing: f64::from_bits(0x402352019343B4E3_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC017A9E4B8B0BF98_u64), f64::from_bits(0xC002A51FF33329F6_u64)),
                radius: f64::from_bits(0x3FD57A604870B9B8_u64),
                slots: &[(f64::from_bits(0x402563C94889CA92_u64), f64::from_bits(0x402E1FE9E19C9968_u64))],
                spacing: f64::from_bits(0x401AC1251D330C43_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x4011A1A8E53F66AA_u64), f64::from_bits(0xC019E07EE0AFB569_u64)),
                radius: f64::from_bits(0x40070BB78280BC7E_u64),
                slots: &[(f64::from_bits(0xC02E3176149B2770_u64), f64::from_bits(0x400B711A05143448_u64)), (f64::from_bits(0xBFDF6D8316D001C0_u64), f64::from_bits(0x4021E576EE2A3964_u64)), (f64::from_bits(0x40319EC9566C0FE6_u64), f64::from_bits(0x403370EC6242D78E_u64))],
                spacing: f64::from_bits(0x3FF8EB9B8B556D74_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC011688D5D9B0D2A_u64), f64::from_bits(0x4011409AAA6191BC_u64)),
                radius: f64::from_bits(0x3FFD61767258B182_u64),
                slots: &[(f64::from_bits(0xC0129E708A821AAC_u64), f64::from_bits(0x402D8D6C2054EA1C_u64)), (f64::from_bits(0x3FF6F98F2115D9F0_u64), f64::from_bits(0xC02EB19FCA7888C9_u64)), (f64::from_bits(0xC02C9E9D8BCFE44C_u64), f64::from_bits(0xC02C4B5A5C2FC842_u64)), (f64::from_bits(0x401E1ED80BC73D50_u64), f64::from_bits(0xC023235EF77AC7A2_u64)), (f64::from_bits(0x4019BEE951D7B7D0_u64), f64::from_bits(0xC0262CBD044DD27A_u64)), (f64::from_bits(0xC032F361E7633AEA_u64), f64::from_bits(0x400255197DBEB788_u64)), (f64::from_bits(0x401481446BE5299C_u64), f64::from_bits(0x4025EE800B49D1E4_u64)), (f64::from_bits(0xC007F892CA6BFD40_u64), f64::from_bits(0xC02D0AC1CD123660_u64))],
                spacing: f64::from_bits(0x4020E8BC92A73725_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC023F06EE6118228_u64), f64::from_bits(0xC01CF046B83405DA_u64)),
                radius: f64::from_bits(0x402793324E7946FE_u64),
                slots: &[(f64::from_bits(0x4011E952823C9548_u64), f64::from_bits(0x4022A7C9149D013A_u64))],
                spacing: f64::from_bits(0x40212EA5E29C87BA_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x3FF3357405D83150_u64), f64::from_bits(0xC0116D00428C639A_u64)),
                radius: f64::from_bits(0x40232499622A4353_u64),
                slots: &[(f64::from_bits(0xC032B0461A9A5764_u64), f64::from_bits(0xC02D6A646EF8336A_u64)), (f64::from_bits(0x402560906198C7AE_u64), f64::from_bits(0xC01984A729F1C454_u64)), (f64::from_bits(0x3FF5FC0943A94C80_u64), f64::from_bits(0xC001D8AB98BAE068_u64))],
                spacing: f64::from_bits(0x4014327124C75E5F_u64),
                expected: &[(f64::from_bits(0x3FF5FC0943A94C80_u64), f64::from_bits(0xC001D8AB98BAE068_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC00B47425FF11CFC_u64), f64::from_bits(0xC005209178E38754_u64)),
                radius: f64::from_bits(0x4027E67496A70688_u64),
                slots: &[(f64::from_bits(0xC02741F2802FD9AD_u64), f64::from_bits(0x40298246DD67B838_u64)), (f64::from_bits(0x40314975FE8B90A0_u64), f64::from_bits(0xBFDCCE80928AA100_u64))],
                spacing: f64::from_bits(0x3FF07A843B4DAAAA_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC01B32B7504668A4_u64), f64::from_bits(0x40132275109B3590_u64)),
                radius: f64::from_bits(0x401C5EE1126D0DB8_u64),
                slots: &[(f64::from_bits(0xC01F0156B2E1BA98_u64), f64::from_bits(0xC02F2066275061C2_u64)), (f64::from_bits(0x4029C59711968344_u64), f64::from_bits(0x402C0706B62BD7C0_u64)), (f64::from_bits(0x3FF15D066EEFDB40_u64), f64::from_bits(0x4031E1F333305CA6_u64)), (f64::from_bits(0xC027C6DC56E0FF4F_u64), f64::from_bits(0x4022CFBBDCF78674_u64)), (f64::from_bits(0x401A3D157F0ADD04_u64), f64::from_bits(0xC022E87F2D3706B6_u64)), (f64::from_bits(0x4030916DA579664A_u64), f64::from_bits(0xC013532B7238496C_u64)), (f64::from_bits(0xC031F9808B1D45AE_u64), f64::from_bits(0xC02E7F5E4402E512_u64))],
                spacing: f64::from_bits(0x400C098B3DA4855D_u64),
                expected: &[(f64::from_bits(0xC027C6DC56E0FF4F_u64), f64::from_bits(0x4022CFBBDCF78674_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC01C8243D03EE29F_u64), f64::from_bits(0xC01E6683BB33E000_u64)),
                radius: f64::from_bits(0x4014919B54F52E60_u64),
                slots: &[(f64::from_bits(0xC02A553BEBD1E69A_u64), f64::from_bits(0xC0229B3F94BFF638_u64))],
                spacing: f64::from_bits(0x400FD7CE91076EB4_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC0172DB027B71CAE_u64), f64::from_bits(0xC01DF6CB4222F590_u64)),
                radius: f64::from_bits(0x3FE7E8897921A6EC_u64),
                slots: &[(f64::from_bits(0xC008063F3A39A2C0_u64), f64::from_bits(0x3FEEA153F7D87860_u64)), (f64::from_bits(0xC027EFA04F4E7941_u64), f64::from_bits(0x3FE6BE5D5E478E80_u64)), (f64::from_bits(0xC01CBFE88D00C72C_u64), f64::from_bits(0xC030304904C65352_u64)), (f64::from_bits(0x4021D3887F82750E_u64), f64::from_bits(0xC01419C165DD1604_u64)), (f64::from_bits(0x402EA4511E27A6C4_u64), f64::from_bits(0xC01B5E70A92085FC_u64)), (f64::from_bits(0x401E0EB7F9590268_u64), f64::from_bits(0xC0219E3DB6C5DE1E_u64)), (f64::from_bits(0xC01CDE9BF8782924_u64), f64::from_bits(0x403251E09CC3D406_u64))],
                spacing: f64::from_bits(0x40060C102DC33B6B_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x40229004ED0B4A38_u64), f64::from_bits(0x401BDBF14D5AC01C_u64)),
                radius: f64::from_bits(0x400DFF9C83A4E523_u64),
                slots: &[(f64::from_bits(0xC021B61D6D7F9E6C_u64), f64::from_bits(0x3FF78113771894E0_u64)), (f64::from_bits(0x402E6F6A654A4D84_u64), f64::from_bits(0x4033D2DF1A8057E0_u64)), (f64::from_bits(0x401C37C566A60818_u64), f64::from_bits(0x40315483708A81BA_u64)), (f64::from_bits(0xC02623E0D1304CFE_u64), f64::from_bits(0xC01919A7FE913BC4_u64)), (f64::from_bits(0x4027E34F245FB7EA_u64), f64::from_bits(0x40169CDE5705C590_u64)), (f64::from_bits(0xC0230DF8FFE528C2_u64), f64::from_bits(0xC006A6F57A0EB708_u64)), (f64::from_bits(0x402D0171E459F2F0_u64), f64::from_bits(0x4032D31880A27C38_u64)), (f64::from_bits(0xC011B02BBEF79C50_u64), f64::from_bits(0xC0280F55B3CFAE15_u64))],
                spacing: f64::from_bits(0x4019D4B832258403_u64),
                expected: &[(f64::from_bits(0x4027E34F245FB7EA_u64), f64::from_bits(0x40169CDE5705C590_u64))],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0xC022BE2E4BEB836D_u64), f64::from_bits(0xC023B0F58350105C_u64)),
                radius: f64::from_bits(0x40120150EA9FFFCC_u64),
                slots: &[(f64::from_bits(0x4025157DC3F47184_u64), f64::from_bits(0xC01C093D523614D8_u64)), (f64::from_bits(0x3FE0E989AD0F65A0_u64), f64::from_bits(0xC0319AB999F83A24_u64)), (f64::from_bits(0xC031D69FD8F9EB64_u64), f64::from_bits(0xC0192D66295B150A_u64))],
                spacing: f64::from_bits(0x40177128F8DDF049_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x401762053C0AFF16_u64), f64::from_bits(0x4019466FF7CA1C44_u64)),
                radius: f64::from_bits(0x3FC2B17AD03C3FF0_u64),
                slots: &[],
                spacing: f64::from_bits(0x40236E667BEE87EF_u64),
                expected: &[],
                tags: &["kernel:within", "within_empty_index"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x4000121D99FB98AC_u64), f64::from_bits(0xC0094D2E9FCE9DCC_u64)),
                radius: f64::from_bits(0x3FEBD6455EC482C8_u64),
                slots: &[(f64::from_bits(0x4024AE32F2DE1CFC_u64), f64::from_bits(0xC031F369D52EC86E_u64)), (f64::from_bits(0x4033288E61B242E0_u64), f64::from_bits(0x4019B7E2ACCFC2FC_u64))],
                spacing: f64::from_bits(0x401A64963E0E730B_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
            FrozenWithinCase {
                center: (f64::from_bits(0x40206A9D9C4778B0_u64), f64::from_bits(0x40145C123703404E_u64)),
                radius: f64::from_bits(0x3FF643033EDC52A8_u64),
                slots: &[(f64::from_bits(0xC032C680BD8DECA0_u64), f64::from_bits(0xC010F2539EB01528_u64)), (f64::from_bits(0x40306ECB9F617362_u64), f64::from_bits(0xC002CBA46CF470B0_u64)), (f64::from_bits(0xC02943FC85F7E368_u64), f64::from_bits(0x4031C8625F2AD8C4_u64)), (f64::from_bits(0x40089F6C9A04C4F8_u64), f64::from_bits(0xC026A5C150DB6B7E_u64)), (f64::from_bits(0x401EB616A6E796DC_u64), f64::from_bits(0xC0295083A9439E66_u64))],
                spacing: f64::from_bits(0x4023F946DC4988E0_u64),
                expected: &[],
                tags: &["kernel:within", "within_nonempty"],
            },
        ];

        #[test]
        fn frozen_slot_grid_matches_golden_corpus() {
            for case in FROZEN_SPACING_GOLDEN {
                let got = infer_slot_spacing(case.slots);
                let want = f64::from_bits(case.expected_bits);
                let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();
                assert!(ok, "spacing tags={:?}: got {:?} want {:?}", case.tags, got, want);
            }
            for case in FROZEN_INDEX_GOLDEN {
                let got = build_slot_index(case.slots, case.spacing);
                // Same frozen shape as FrozenIndexCase::expected above.
                #[allow(clippy::type_complexity)]
                let want: Vec<((i64, i64), Vec<(f64, f64)>)> = case.expected
                    .iter().map(|&(k, v)| (k, v.to_vec())).collect();
                assert_eq!(got, want, "index tags={:?}", case.tags);
            }
            for case in FROZEN_WITHIN_GOLDEN {
                let index: HashMap<(i64, i64), Vec<(f64, f64)>> =
                    build_slot_index(case.slots, case.spacing).into_iter().collect();
                let got = slots_within_radius(case.center, case.radius, &index, case.spacing);
                let want: Vec<(f64, f64)> = case.expected.to_vec();
                assert_eq!(got, want, "within tags={:?}", case.tags);
            }
        }

        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
        /// ever hand-edited down to something trivially satisfiable.
        #[test]
        fn frozen_slot_grid_corpus_is_non_vacuous() {
            let n = (FROZEN_SPACING_GOLDEN.len() + FROZEN_INDEX_GOLDEN.len() + FROZEN_WITHIN_GOLDEN.len()) as u32;
            let count = |tag: &str| FROZEN_SPACING_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32 + FROZEN_INDEX_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32 + FROZEN_WITHIN_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(count("kernel:spacing") >= 8, "kernel:spacing: only {}/{} (need >= 8) -- spacing golden vectors must be present", count("kernel:spacing"), n);
            assert!(count("kernel:index") >= 6, "kernel:index: only {}/{} (need >= 6) -- index golden vectors must be present", count("kernel:index"), n);
            assert!(count("kernel:within") >= 6, "kernel:within: only {}/{} (need >= 6) -- within-radius golden vectors must be present", count("kernel:within"), n);
            assert!(count("spacing_fallback_degenerate") >= 2, "spacing_fallback_degenerate: only {}/{} (need >= 2) -- <2 slots -> DEFAULT_SLOT_SPACING fallback branch", count("spacing_fallback_degenerate"), n);
            assert!(count("spacing_fallback_uniform") >= 2, "spacing_fallback_uniform: only {}/{} (need >= 2) -- uniform grid (no distinct coords) -> fallback branch", count("spacing_fallback_uniform"), n);
            assert!(count("spacing_min_diff") >= 6, "spacing_min_diff: only {}/{} (need >= 6) -- minimum non-zero difference branch", count("spacing_min_diff"), n);
            assert!(count("index_half_even") >= 2, "index_half_even: only {}/{} (need >= 2) -- `int(round(x/spacing))` round-half-to-even cell keys", count("index_half_even"), n);
            assert!(count("index_multi_cell") >= 5, "index_multi_cell: only {}/{} (need >= 5) -- multi-cell bucketing must be exercised", count("index_multi_cell"), n);
            assert!(count("index_negative_key") >= 1, "index_negative_key: only {}/{} (need >= 1) -- negative cell keys (CPython round ties-to-even on negatives)", count("index_negative_key"), n);
            assert!(count("within_empty_radius") >= 1, "within_empty_radius: only {}/{} (need >= 1) -- radius <= 0 -> [] branch", count("within_empty_radius"), n);
            assert!(count("within_empty_index") >= 1, "within_empty_index: only {}/{} (need >= 1) -- empty index -> [] branch", count("within_empty_index"), n);
            assert!(count("within_radius_inclusive") >= 1, "within_radius_inclusive: only {}/{} (need >= 1) -- inclusive `<= radius` distance check on an exact-boundary slot", count("within_radius_inclusive"), n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: slot_grid_validator ---

// --- BEGIN generated by scripts/gen_oracle_freeze.py: fine_pitch_escape ---
    /// Frozen golden vectors for `min_pin_pitch` / `escape_layer_for_net`
    /// (FREEZE, batch 2 — retired tests/deterministic/stages/_fine_pitch_escape_py_oracle.py).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec fine_pitch_escape`
    /// (requires reviving the deleted oracle from git history first -- see
    /// scripts/oracle_freeze_specs/fine_pitch_escape.py's module docstring).
    #[cfg(test)]
    mod frozen_fine_pitch_tests {
        use super::*;
        use std::collections::HashSet;

        struct FrozenPitchCase {
            pins: &'static [(f64, f64)],
            expected_bits: Option<u64>,
            tags: &'static [&'static str],
        }

        const FROZEN_PITCH_GOLDEN: &[FrozenPitchCase] = &[
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected_bits: Some(0x3ff0000000000000_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FE0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FD0000000000000_u64), f64::from_bits(0x3FD0000000000000_u64))],
                expected_bits: Some(0x3fd6a09e667f3bcd_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist"],
            },
            FrozenPitchCase {
                pins: &[],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected_bits: Some(0x0000000000000000_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_identical_pins_zero"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected_bits: Some(0x0000000000000000_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_identical_pins_zero"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC004000000000000_u64), f64::from_bits(0x400C000000000000_u64)), (f64::from_bits(0xC004000000000000_u64), f64::from_bits(0x400C000000000000_u64)), (f64::from_bits(0x401C000000000000_u64), f64::from_bits(0x401C000000000000_u64))],
                expected_bits: Some(0x0000000000000000_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_identical_pins_zero", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x3FC999999999999A_u64)), (f64::from_bits(0x3FD3333333333333_u64), f64::from_bits(0x3FD999999999999A_u64)), (f64::from_bits(0x3FFB333333333333_u64), f64::from_bits(0x4007333333333333_u64))],
                expected_bits: Some(0x3fd21a1851ff630a_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xBFF0000000000000_u64), f64::from_bits(0xBFF0000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)), (f64::from_bits(0x4008000000000000_u64), f64::from_bits(0xC000000000000000_u64))],
                expected_bits: Some(0x4006a09e667f3bcd_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4020000000000000_u64))],
                expected_bits: Some(0x4014000000000000_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FC999999999999A_u64), f64::from_bits(0x0000000000000000_u64))],
                expected_bits: Some(0x3fb999999999999a_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist"],
            },
            FrozenPitchCase {
                pins: &[],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x40236C354AFF1A62_u64), f64::from_bits(0x4017CE7DB87F3540_u64)), (f64::from_bits(0xC000BEBEA5712A18_u64), f64::from_bits(0x401EDCE946118A28_u64))],
                expected_bits: Some(0x4027df02a5a7ac1e_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x4013A4585C3685C0_u64), f64::from_bits(0x4023D0F8385DE05A_u64)), (f64::from_bits(0x4021706DA6981C1C_u64), f64::from_bits(0x401CF65D3ECFE710_u64)), (f64::from_bits(0xC020A1BA2B143AFB_u64), f64::from_bits(0x4019B1636E7A7F6C_u64)), (f64::from_bits(0x4020DB16E21C2C76_u64), f64::from_bits(0x401FCF949EFDB748_u64))],
                expected_bits: Some(0x3fe8a01b2890b2b6_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC022C7B32331556A_u64), f64::from_bits(0x3FB7EBE3AC7F1600_u64)), (f64::from_bits(0x401BE1CCD94F4938_u64), f64::from_bits(0x3FCD6897D6804180_u64)), (f64::from_bits(0x4023F825D0565BE2_u64), f64::from_bits(0x401877D9C4B81088_u64))],
                expected_bits: Some(0x401a74c2210b155e_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC01379164EC051A0_u64), f64::from_bits(0x401C6898437BF7EC_u64)), (f64::from_bits(0xC014C255EB3067E8_u64), f64::from_bits(0xBFDE73F7D8055C80_u64)), (f64::from_bits(0xBFE4F30C463D3A40_u64), f64::from_bits(0x3FE775276975ABC0_u64)), (f64::from_bits(0xC01883788D3293D6_u64), f64::from_bits(0x401B0F583EF20324_u64))],
                expected_bits: Some(0x3ff4df16ecd9011e_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC0153DFE7BA1B8B5_u64), f64::from_bits(0x4013E242B412EE88_u64)), (f64::from_bits(0xBFFA2F8B4B7E0A80_u64), f64::from_bits(0xC0230A577714D906_u64)), (f64::from_bits(0xC014BF7EAC3400A4_u64), f64::from_bits(0xC0156746741400CD_u64)), (f64::from_bits(0xC00398E9A20DED64_u64), f64::from_bits(0x3FE52012B8B46120_u64))],
                expected_bits: Some(0x4014b1e7e9f9e417_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC0218454936DDDCD_u64), f64::from_bits(0x40154638657E5E7C_u64)), (f64::from_bits(0xC0215553B3730A05_u64), f64::from_bits(0xC0158E685439DB64_u64)), (f64::from_bits(0xBFE40A9CC42036E0_u64), f64::from_bits(0x401BC5383B10C520_u64)), (f64::from_bits(0xC02073F43E974556_u64), f64::from_bits(0xC00B478F21B3859A_u64))],
                expected_bits: Some(0x4000384c0bcf4cbc_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC01AB9852B1CCE0C_u64), f64::from_bits(0xC01C1C3AB16E8DE9_u64))],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x400706829ACD9C10_u64), f64::from_bits(0xC01331A385743DE8_u64)), (f64::from_bits(0xBFDD96C94214F8C0_u64), f64::from_bits(0x3FF8374F5C9500A8_u64)), (f64::from_bits(0xC016897FB27E276C_u64), f64::from_bits(0x3FF422E1CE939A50_u64))],
                expected_bits: Some(0x4014b681dfd572b1_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x3FFB24BEA71E7BE0_u64), f64::from_bits(0xC022E3E4C8B7F33A_u64)), (f64::from_bits(0x3FFF7FA996D9C160_u64), f64::from_bits(0x4022DA283ABD9A10_u64))],
                expected_bits: Some(0x4032df8726e96a7a_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[],
                expected_bits: None,
                tags: &["kernel:pitch", "pitch_fewer_than_two"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC000A222125ACFC0_u64), f64::from_bits(0x4000788A568B26F4_u64)), (f64::from_bits(0x401C9C2BE187AA0C_u64), f64::from_bits(0xC01E429769CC5894_u64)), (f64::from_bits(0xC012D0E508F96BF4_u64), f64::from_bits(0x400FFCC8AA72ACB0_u64)), (f64::from_bits(0x40153A8236FC449A_u64), f64::from_bits(0xC00F0136781FDC20_u64))],
                expected_bits: Some(0x400a1c0a6231d8f9_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x3FB775897E37A000_u64), f64::from_bits(0xC02203A34DC4A996_u64)), (f64::from_bits(0x4017DDA564F3C66C_u64), f64::from_bits(0x3FFDFE79F1E1E700_u64)), (f64::from_bits(0x40198BE4B75DE7B8_u64), f64::from_bits(0x40121173836A2A26_u64))],
                expected_bits: Some(0x400567a655d56e72_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC012D52B645C6DB4_u64), f64::from_bits(0x400C85AEB2A0FFE0_u64)), (f64::from_bits(0x3FE1A6232AC79A20_u64), f64::from_bits(0xC022E1E990492B46_u64)), (f64::from_bits(0x40172574B0BA018A_u64), f64::from_bits(0xC01A3C3E5A3502E8_u64)), (f64::from_bits(0xC00399201868D5D2_u64), f64::from_bits(0x401CDFBA077CF580_u64))],
                expected_bits: Some(0x40112dff23497bd6_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0xC01E31CB4B2C8ED4_u64), f64::from_bits(0xC004590597D0C6A8_u64)), (f64::from_bits(0x4022EC4637A54D00_u64), f64::from_bits(0xC0181AE3D83BD19F_u64)), (f64::from_bits(0x40094599E8B2D234_u64), f64::from_bits(0x40053D4D8215A830_u64)), (f64::from_bits(0xBFD6A6D08268ACA0_u64), f64::from_bits(0x400DC698DA421178_u64))],
                expected_bits: Some(0x400d5f052ee35f6b_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x402378DC3021EAFC_u64), f64::from_bits(0x4023EE4620755AD6_u64)), (f64::from_bits(0x3FF1C20F1F2978B8_u64), f64::from_bits(0xC022FC2FDB90B5AE_u64))],
                expected_bits: Some(0x403548c8cf5a9ff2_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
            FrozenPitchCase {
                pins: &[(f64::from_bits(0x4001EFF4FF8F4968_u64), f64::from_bits(0xC017B70D9E6ED0A2_u64)), (f64::from_bits(0x401640EE0D05E966_u64), f64::from_bits(0x402068AE0626481C_u64))],
                expected_bits: Some(0x402d0952da1c8ddd_u64),
                tags: &["kernel:pitch", "pitch_ge_two", "pitch_min_dist", "pitch_negative_coords"],
            },
        ];

        struct FrozenEscapeCase {
            net_name: &'static str,
            layer2: &'static [&'static str],
            layer3: &'static [&'static str],
            primary: i64,
            secondary: i64,
            expected: (i64, &'static str),
            tags: &'static [&'static str],
        }

        const FROZEN_ESCAPE_GOLDEN: &[FrozenEscapeCase] = &[
            FrozenEscapeCase {
                net_name: "PWM_H",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (2i64, "In2.Cu"),
                tags: &["escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "SPI_CLK",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (2i64, "In2.Cu"),
                tags: &["escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "I_SENSE",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_l3", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "TEMP_SENSE",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_l3", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "GATE_H",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (1i64, "In1.Cu"),
                tags: &["escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "OTHER",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (1i64, "In1.Cu"),
                tags: &["escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "",
                layer2: &["PWM_H", "PWM_L", "SPI_CLK"],
                layer3: &["I_SENSE", "TEMP_SENSE"],
                primary: 1i64,
                secondary: 2i64,
                expected: (1i64, "In1.Cu"),
                tags: &["escape_default", "escape_empty_net_name", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "A",
                layer2: &["A"],
                layer3: &["B"],
                primary: 1i64,
                secondary: 2i64,
                expected: (2i64, "In2.Cu"),
                tags: &["escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "B",
                layer2: &["A"],
                layer3: &["B"],
                primary: 1i64,
                secondary: 2i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_l3", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "C",
                layer2: &["A"],
                layer3: &["B"],
                primary: 1i64,
                secondary: 2i64,
                expected: (1i64, "In1.Cu"),
                tags: &["escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "A",
                layer2: &["A"],
                layer3: &["B"],
                primary: 5i64,
                secondary: 9i64,
                expected: (9i64, "In2.Cu"),
                tags: &["escape_custom_layers", "escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "C",
                layer2: &["A"],
                layer3: &["B"],
                primary: 5i64,
                secondary: 9i64,
                expected: (5i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "X",
                layer2: &["X"],
                layer3: &["X"],
                primary: 1i64,
                secondary: 2i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_l3", "escape_l3_precedence", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "PWM_H",
                layer2: &["I_SENSE", "SPI_CLK"],
                layer3: &[],
                primary: 6i64,
                secondary: 4i64,
                expected: (6i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "",
                layer2: &["SPI_CLK", "TEMP_SENSE"],
                layer3: &["", "GATE_H", "NET_7"],
                primary: 8i64,
                secondary: 2i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_custom_layers", "escape_empty_net_name", "escape_l3", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "PWM_H",
                layer2: &[],
                layer3: &["SPI_CLK"],
                primary: 3i64,
                secondary: 3i64,
                expected: (3i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "TEMP_SENSE",
                layer2: &["I_SENSE"],
                layer3: &["GATE_H", "I_SENSE", "NET_8"],
                primary: 4i64,
                secondary: 3i64,
                expected: (4i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "NET_7",
                layer2: &["TEMP_SENSE"],
                layer3: &["", "PWM_H"],
                primary: 5i64,
                secondary: 5i64,
                expected: (5i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "",
                layer2: &[],
                layer3: &["GATE_H", "I_SENSE", "NET_7"],
                primary: 7i64,
                secondary: 7i64,
                expected: (7i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "escape_empty_net_name", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "SPI_CLK",
                layer2: &["PWM_H", "TEMP_SENSE"],
                layer3: &["GATE_H", "I_SENSE", "PWM_H"],
                primary: 4i64,
                secondary: 2i64,
                expected: (4i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "GATE_H",
                layer2: &["GATE_H", "NET_8", "SPI_CLK"],
                layer3: &["", "NET_8"],
                primary: 8i64,
                secondary: 1i64,
                expected: (1i64, "In2.Cu"),
                tags: &["escape_custom_layers", "escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "GATE_H",
                layer2: &["NET_7", "PWM_H"],
                layer3: &["NET_7", "PWM_H"],
                primary: 6i64,
                secondary: 6i64,
                expected: (6i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "I_SENSE",
                layer2: &["GATE_H"],
                layer3: &["GATE_H", "I_SENSE", "NET_7"],
                primary: 2i64,
                secondary: 8i64,
                expected: (3i64, "B.Cu"),
                tags: &["escape_custom_layers", "escape_l3", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "GATE_H",
                layer2: &["NET_7", "SPI_CLK"],
                layer3: &["", "I_SENSE"],
                primary: 5i64,
                secondary: 6i64,
                expected: (5i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "",
                layer2: &[],
                layer3: &["GATE_H", "NET_8", "TEMP_SENSE"],
                primary: 4i64,
                secondary: 8i64,
                expected: (4i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "escape_empty_net_name", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "NET_8",
                layer2: &[],
                layer3: &["TEMP_SENSE"],
                primary: 2i64,
                secondary: 6i64,
                expected: (2i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "TEMP_SENSE",
                layer2: &["GATE_H", "NET_7"],
                layer3: &["GATE_H"],
                primary: 6i64,
                secondary: 7i64,
                expected: (6i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "NET_8",
                layer2: &["I_SENSE", "PWM_H", "SPI_CLK"],
                layer3: &[],
                primary: 4i64,
                secondary: 4i64,
                expected: (4i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "I_SENSE",
                layer2: &[],
                layer3: &[],
                primary: 8i64,
                secondary: 8i64,
                expected: (8i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "SPI_CLK",
                layer2: &["I_SENSE", "SPI_CLK"],
                layer3: &["GATE_H"],
                primary: 1i64,
                secondary: 3i64,
                expected: (3i64, "In2.Cu"),
                tags: &["escape_custom_layers", "escape_l2", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "TEMP_SENSE",
                layer2: &[],
                layer3: &[""],
                primary: 5i64,
                secondary: 3i64,
                expected: (5i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "NET_7",
                layer2: &[],
                layer3: &["", "NET_8", "SPI_CLK"],
                primary: 3i64,
                secondary: 6i64,
                expected: (3i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "TEMP_SENSE",
                layer2: &["I_SENSE", "PWM_H"],
                layer3: &[],
                primary: 2i64,
                secondary: 8i64,
                expected: (2i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "SPI_CLK",
                layer2: &["", "NET_7", "TEMP_SENSE"],
                layer3: &[""],
                primary: 2i64,
                secondary: 2i64,
                expected: (2i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
            FrozenEscapeCase {
                net_name: "PWM_H",
                layer2: &[],
                layer3: &["", "GATE_H"],
                primary: 6i64,
                secondary: 8i64,
                expected: (6i64, "In1.Cu"),
                tags: &["escape_custom_layers", "escape_default", "kernel:escape"],
            },
        ];

        #[test]
        fn frozen_fine_pitch_matches_golden_corpus() {
            for case in FROZEN_PITCH_GOLDEN {
                let got = min_pin_pitch(case.pins);
                let want = case.expected_bits.map(f64::from_bits);
                let ok = match (got, want) {
                    (None, None) => true,
                    (Some(g), Some(w)) => g.to_bits() == w.to_bits(),
                    _ => false,
                };
                assert!(ok, "pitch tags={:?}: got {:?} want {:?}", case.tags, got, want);
            }
            for case in FROZEN_ESCAPE_GOLDEN {
                let l3: HashSet<String> = case.layer3.iter().map(|s| s.to_string()).collect();
                let l2: HashSet<String> = case.layer2.iter().map(|s| s.to_string()).collect();
                // NOTE: pure escape_layer_for_net takes (net, l3, l2, primary, secondary).
                let got = escape_layer_for_net(case.net_name, &l3, &l2, case.primary, case.secondary);
                assert_eq!(got, case.expected, "escape tags={:?}", case.tags);
            }
        }

        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
        /// ever hand-edited down to something trivially satisfiable.
        #[test]
        fn frozen_fine_pitch_corpus_is_non_vacuous() {
            let n = (FROZEN_PITCH_GOLDEN.len() + FROZEN_ESCAPE_GOLDEN.len()) as u32;
            let count = |tag: &str| FROZEN_PITCH_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32 + FROZEN_ESCAPE_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(count("kernel:pitch") >= 8, "kernel:pitch: only {}/{} (need >= 8) -- pitch golden vectors must be present", count("kernel:pitch"), n);
            assert!(count("kernel:escape") >= 8, "kernel:escape: only {}/{} (need >= 8) -- escape golden vectors must be present", count("kernel:escape"), n);
            assert!(count("pitch_fewer_than_two") >= 2, "pitch_fewer_than_two: only {}/{} (need >= 2) -- <2 pins -> None branch", count("pitch_fewer_than_two"), n);
            assert!(count("pitch_min_dist") >= 5, "pitch_min_dist: only {}/{} (need >= 5) -- minimum-distance branch (non-coincident pins)", count("pitch_min_dist"), n);
            assert!(count("pitch_identical_pins_zero") >= 2, "pitch_identical_pins_zero: only {}/{} (need >= 2) -- coincident pins -> exactly 0.0 (kept, not inf)", count("pitch_identical_pins_zero"), n);
            assert!(count("pitch_negative_coords") >= 2, "pitch_negative_coords: only {}/{} (need >= 2) -- negative coordinates must be exercised", count("pitch_negative_coords"), n);
            assert!(count("escape_l3") >= 3, "escape_l3: only {}/{} (need >= 3) -- layer-3 (B.Cu) branch", count("escape_l3"), n);
            assert!(count("escape_l2") >= 3, "escape_l2: only {}/{} (need >= 3) -- layer-2 (In2.Cu) branch", count("escape_l2"), n);
            assert!(count("escape_default") >= 4, "escape_default: only {}/{} (need >= 4) -- default (In1.Cu) branch", count("escape_default"), n);
            assert!(count("escape_custom_layers") >= 3, "escape_custom_layers: only {}/{} (need >= 3) -- non-default primary/secondary layer parameters", count("escape_custom_layers"), n);
            assert!(count("escape_l3_precedence") >= 1, "escape_l3_precedence: only {}/{} (need >= 1) -- net in both sets -> layer 3 wins (checked first)", count("escape_l3_precedence"), n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: fine_pitch_escape ---

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

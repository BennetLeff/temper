//! Phase-E E2 (rust-orchestration-engine plan 2026-08-09-001): the
//! fixed-copper orchestration from `placer/cp_sat/fixed_copper.py`
//! (1,246 LOC — verified: no ortools import) as `FixedCopperBuilder`,
//! plus the design-bundle contract pyclasses it constructs.
//!
//! | Python surface                    | Rust surface                                        |
//! |-----------------------------------|-----------------------------------------------------|
//! | `build_free_component_pads`       | [`FixedCopperBuilder::build_free_component_pads`]   |
//! | `build_fixed_copper_items`        | [`FixedCopperBuilder::build_fixed_copper_items`]    |
//! | `audit_fixed_copper` (R24 item 3) | [`FixedCopperBuilder::audit_fixed_copper`]          |
//! | `PadRectLocal`                    | the `PadRectLocal` pyclass                          |
//! | `FixedCopperItem`                 | the `FixedCopperItem` pyclass                       |
//! | `FixedCopperAuditViolation`       | the `FixedCopperAuditViolation` pyclass             |
//!
//! The pre-migration implementation is pinned VERBATIM as the oracle
//! `tests/placer/cp_sat/_fixed_copper_py_oracle.py` (the Wave-4 kernel-
//! migration oracle, extracted at `1dd54e3f2cc58e9dd6cbc5b3c54d68b4d0374ae9`
//! — a pure-Python snapshot that predates BOTH the temper-geometry kernel
//! carve-out and this E2 orchestration migration); the differential suite
//! `tests/placer/cp_sat/test_fixed_copper_builder_rust_differential.py`
//! drives both arms with identical inputs and compares the resulting pads /
//! items / audit violations field-by-field, bit-exactly (`float.hex()`).
//!
//! # What stays Python, and why
//!
//! The split is at the ortools boundary (plan D4 KEEP verdict):
//!
//! - **`encode_fixed_copper_constraints` / `_pad_rotation_tables_with` /
//!   `_add_no_overlap` stay Python.** They build `ortools.CpModel` calls
//!   directly (`NewBoolVar`, `AddBoolOr`, `OnlyEnforceIf`, `AddElement` via
//!   `CpSatModel.model_ref`) — that IS the CP-SAT solver boundary, and the
//!   phase-1 spike's KEEP verdict on `placer/cp_sat/model.py` /
//!   `_encoder_solve.py` is not reopened. They consume the pyclasses below
//!   through their `__all__`-exposed fields, unchanged.
//! - **The geometry kernels stay in `temper-geometry`.** `_mm_to_units`,
//!   `pad_world_rect`, `encoded_pad_world_rect`, `segment_slack_mm`,
//!   `exact_clearance_mm`, `encoded_overlap`, `encoded_overlap_edges`,
//!   `_pin_copper_layers`, `_local_pad_half`, the item-geometry builders and
//!   the exact-clearance oracle are already Rust `fixed_copper_*_py`
//!   kernels (pinned bit-exactly by
//!   `test_fixed_copper_rust_differential.py`). The shim's one-line
//!   wrappers stay as-is; the builder CALLS those kernels through FFI, so
//!   item geometry is bit-identical by construction.
//! - **`encode_fixed_copper_constraints`'s consumers** (`_encoder_solve.py`)
//!   keep importing the module-level functions; the shim's public API
//!   (`__all__`) is unchanged.
//!
//! # Bit-exactness notes
//!
//! - Iteration order is preserved wherever the oracle's output depends on
//!   it: `netlist.components` order, `comp.pins` order, `parse_result.traces`
//!   order, `parse_result.vias` order, `board.zones` order, and the
//!   pinned-component scan order — all live Python lists, iterated by the
//!   builder over the live objects (never a copied HashMap).
//! - Trace/via coordinates are origin-normalized in the same subtraction
//!   order (`t.start[0] - ox0`, ...) as the pre-migration body.
//! - Item labels use `format!("{:.2}")` — byte-identical to Python's
//!   `:.2f` (the B3 argument from `constraint_model.rs`, measured over
//!   250,005 adversarial samples on this host). A `None` net renders as
//!   the literal `"None"` exactly like an f-string interpolating `None`.
//! - `int(comp.initial_rotation or 0)` is truncated toward zero (Rust `as
//!   i64`), matching Python's `int()` on the truthy branch.
//! - `float("nan")` for a missing-position violation's `actual_mm` maps to
//!   `f64::NAN`.
//!
//! # Panic policy (G7)
//!
//! Every `#[pymethods]` entry point is wrapped in [`guard`] (`catch_unwind`);
//! no `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use std::collections::HashSet;
use std::panic::AssertUnwindSafe;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFrozenSet, PyList, PyModule};

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// The four copper layers of the temper 4-layer stackup (KiCad names) —
/// `fixed_copper.py`'s `COPPER_LAYERS` module constant.
const COPPER_LAYER_NAMES: [&str; 4] = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"];

/// Default pad-to-copper margin (mm) — `DEFAULT_MARGIN_MM`.
const DEFAULT_MARGIN_MM: f64 = 0.05;

/// `temper_geometry` module handle for the fixed-copper kernels.
fn tg(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "temper_geometry")
}

/// Python's builtin `getattr(obj, name, default)` — identical semantics to
/// the pre-migration source's `getattr(pin, name, default)` calls.
fn py_getattr<'py, D>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: D,
) -> PyResult<Bound<'py, PyAny>>
where
    D: IntoPyObject<'py>,
{
    let builtins = PyModule::import(py, "builtins")?;
    let getattr = builtins.getattr("getattr")?;
    getattr.call1((obj, name, default))
}

/// `getattr(obj, name, default)` with a `bool` default (the `is_pth` read).
fn getattr_bool<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: bool,
) -> PyResult<bool> {
    py_getattr(py, obj, name, default)?.extract()
}

/// `getattr(obj, name, default)` with an `f64` default (the `width` /
/// `height` / `pad_rotation_deg` reads).
fn getattr_f64<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: f64,
) -> PyResult<f64> {
    py_getattr(py, obj, name, default)?.extract()
}

/// `getattr(obj, name, None)` — a `str | None` attribute (the `net` /
/// `layer` reads).
fn getattr_opt_str<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Option<String>> {
    let none: Option<String> = None;
    py_getattr(py, obj, name, none)?.extract()
}

/// `getattr(obj, name, default)` with a `(f64, f64)` default (the
/// `position` read).
fn getattr_pos<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: (f64, f64),
) -> PyResult<(f64, f64)> {
    py_getattr(py, obj, name, default)?.extract()
}

/// `str(getattr(obj, name, default))` — the pre-migration
/// `str(getattr(pin, "number", ""))` pattern.
fn getattr_py_str(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    name: &str,
    default: &str,
) -> PyResult<String> {
    py_str(py, &py_getattr(py, obj, name, default)?)
}

/// Python's builtin `str(x)` — mirrors the pre-migration `str(getattr(...))`.
fn py_str(py: Python<'_>, v: &Bound<'_, PyAny>) -> PyResult<String> {
    let builtins = PyModule::import(py, "builtins")?;
    builtins.getattr("str")?.call1((v,))?.extract()
}

/// True when the two frozensets share no member — the Rust equivalent of
/// Python's `not (a & b)`.
fn frozensets_disjoint(
    a: &Bound<'_, PyFrozenSet>,
    b: &Bound<'_, PyFrozenSet>,
) -> PyResult<bool> {
    for m in a.iter() {
        if b.contains(m)? {
            return Ok(false);
        }
    }
    Ok(true)
}

/// An `Option<String>` net rendered the way an f-string renders `None` /
/// `"NET_B"`.
fn net_display(net: &Option<String>) -> String {
    match net {
        Some(s) => s.clone(),
        None => "None".to_string(),
    }
}

/// Build a `frozenset` over `items` filtered by membership in `universe`
/// (both Python sets) — the Rust equivalent of
/// `frozenset(items) & universe` with the same member set.
fn frozenset_intersect<'py>(
    py: Python<'py>,
    items: impl IntoIterator<Item = String>,
    universe: &Bound<'py, PyFrozenSet>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let mut kept = Vec::new();
    for item in items {
        if universe.contains(item.as_str())? {
            kept.push(item);
        }
    }
    PyFrozenSet::new(py, kept)
}

// ---------------------------------------------------------------------------
// Contract pyclasses (mirror the fixed_copper.py dataclasses)
// ---------------------------------------------------------------------------

/// `PadRectLocal`: one pad of a *free* component, in the component's local
/// (pre-rotation) placement frame.
#[pyclass(module = "temper_design_bundle_python.fixed_copper_builder", skip_from_py_object)]
#[derive(Debug)]
pub struct PadRectLocal {
    #[pyo3(get)]
    pub number: String,
    #[pyo3(get)]
    pub net: Option<String>,
    layers: Py<PyFrozenSet>,
    center: (f64, f64),
    half: (f64, f64),
}

#[pymethods]
impl PadRectLocal {
    #[new]
    #[pyo3(signature = (*, number, net, layers, center, half))]
    fn new(
        number: String,
        net: Option<String>,
        layers: Bound<'_, PyAny>,
        center: (f64, f64),
        half: (f64, f64),
    ) -> PyResult<Self> {
        let layers = layers.extract::<Py<PyFrozenSet>>()?;
        Ok(Self { number, net, layers, center, half })
    }

    #[getter]
    fn layers(&self, py: Python<'_>) -> Py<PyFrozenSet> {
        self.layers.clone_ref(py)
    }

    #[getter]
    fn center(&self) -> (f64, f64) {
        self.center
    }

    #[getter]
    fn half(&self) -> (f64, f64) {
        self.half
    }
}

/// `FixedCopperItem`: one fixed-copper obstacle.
#[pyclass(module = "temper_design_bundle_python.fixed_copper_builder", skip_from_py_object)]
#[derive(Debug)]
pub struct FixedCopperItem {
    #[pyo3(get)]
    pub kind: String,
    #[pyo3(get)]
    pub net: Option<String>,
    layers: Py<PyFrozenSet>,
    rect: (f64, f64, f64, f64),
    exact: Py<PyAny>,
    #[pyo3(get)]
    pub slack_mm: f64,
    #[pyo3(get)]
    pub margin_mm: f64,
    #[pyo3(get)]
    pub label: String,
    edges: Option<Py<PyAny>>,
}

#[pymethods]
impl FixedCopperItem {
    #[new]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    #[pyo3(signature = (
        *,
        kind,
        net,
        layers,
        rect,
        exact,
        slack_mm,
        margin_mm,
        label = "".to_string(),
        edges = None
    ))]
    fn new(
        kind: String,
        net: Option<String>,
        layers: Bound<'_, PyAny>,
        rect: (f64, f64, f64, f64),
        exact: Bound<'_, PyAny>,
        slack_mm: f64,
        margin_mm: f64,
        label: String,
        edges: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let layers = layers.extract::<Py<PyFrozenSet>>()?;
        Ok(Self {
            kind,
            net,
            layers,
            rect,
            exact: exact.unbind(),
            slack_mm,
            margin_mm,
            label,
            edges: edges.map(|e| e.unbind()),
        })
    }

    #[getter]
    fn layers(&self, py: Python<'_>) -> Py<PyFrozenSet> {
        self.layers.clone_ref(py)
    }

    #[getter]
    fn rect(&self) -> (f64, f64, f64, f64) {
        self.rect
    }

    #[getter]
    fn exact(&self, py: Python<'_>) -> Py<PyAny> {
        self.exact.clone_ref(py)
    }

    #[getter]
    fn edges(&self, py: Python<'_>) -> Py<PyAny> {
        match &self.edges {
            Some(e) => e.clone_ref(py),
            None => py.None(),
        }
    }
}

/// The `(exact_rect, encoded_rect, slack_mm)` triple returned by the
/// `temper-geometry` `fixed_copper_other_pad_item_geom_py` kernel.
type PadItemGeomPy = ((f64, f64, f64, f64), (f64, f64, f64, f64), f64);

/// `FixedCopperAuditViolation`: a post-solve mismatch — an encoded-clear
/// placement whose exact pad-to-copper clearance is below the margin.
#[pyclass(module = "temper_design_bundle_python.fixed_copper_builder", skip_from_py_object)]
#[derive(Debug)]
pub struct FixedCopperAuditViolation {
    #[pyo3(get, name = "ref")]
    pub ref_field: String,
    #[pyo3(get)]
    pub pad_number: String,
    #[pyo3(get)]
    pub item_label: String,
    #[pyo3(get)]
    pub item_kind: String,
    #[pyo3(get)]
    pub item_net: Option<String>,
    #[pyo3(get)]
    pub required_mm: f64,
    #[pyo3(get)]
    pub actual_mm: f64,
    #[pyo3(get)]
    pub reason: String,
}

#[pymethods]
impl FixedCopperAuditViolation {
    #[new]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    #[pyo3(signature = (
        *,
        r#ref,
        pad_number,
        item_label,
        item_kind,
        item_net,
        required_mm,
        actual_mm,
        reason
    ))]
    fn new(
        r#ref: &str,
        pad_number: String,
        item_label: String,
        item_kind: String,
        item_net: Option<String>,
        required_mm: f64,
        actual_mm: f64,
        reason: String,
    ) -> Self {
        Self {
            ref_field: r#ref.to_string(),
            pad_number,
            item_label,
            item_kind,
            item_net,
            required_mm,
            actual_mm,
            reason,
        }
    }
}

// ---------------------------------------------------------------------------
// FixedCopperBuilder — the build() orchestration
// ---------------------------------------------------------------------------

/// `FixedCopperBuilder`: mirror of the fixed_copper.py module-level build
/// orchestration (`build_free_component_pads` / `build_fixed_copper_items` /
/// `audit_fixed_copper`).
///
/// Holds the Python input objects opaquely (`Py<PyAny>`) so iteration order
/// and attribute reads are the live Python ones — the same objects the
/// pre-migration functions read.
#[pyclass(module = "temper_design_bundle_python.fixed_copper_builder", skip_from_py_object)]
pub struct FixedCopperBuilder {
    netlist: Py<PyAny>,
    free_refs: Py<PyAny>,
    parse_result: Option<Py<PyAny>>,
    margin_mm: f64,
    include_other_pads: bool,
    copper_layers: Py<PyFrozenSet>,
}

impl FixedCopperBuilder {
    /// `_pin_copper_layers(pin) & copper_layers` — the pad's copper layers
    /// intersected with the builder's copper-layer universe.
    fn pin_copper_layers<'py>(
        &self,
        py: Python<'py>,
        pin: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyFrozenSet>> {
        let is_pth = getattr_bool(py, pin, "is_pth", false)?;
        let layer = getattr_opt_str(py, pin, "layer")?;
        let kernel = tg(py)?.getattr("fixed_copper_pin_copper_layers_py")?;
        let raw: Vec<String> = kernel.call1((is_pth, layer))?.extract()?;
        let copper = self.copper_layers.bind(py);
        frozenset_intersect(py, raw, copper)
    }

    /// `_local_pad_half(pin)` via the pinned `temper-geometry` kernel.
    fn local_pad_half<'py>(
        &self,
        py: Python<'py>,
        pin: &Bound<'py, PyAny>,
    ) -> PyResult<(f64, f64)> {
        let width = getattr_f64(py, pin, "width", 1.0)?;
        let height = getattr_f64(py, pin, "height", 1.0)?;
        let pad_rotation_deg = getattr_f64(py, pin, "pad_rotation_deg", 0.0)?;
        let kernel = tg(py)?.getattr("fixed_copper_local_pad_half_py")?;
        kernel.call1((width, height, pad_rotation_deg))?.extract()
    }

    /// The `f"segment {net} ..."` / `f"via {net} ..."` label net rendering.
    fn label_net(&self, net: &Option<String>) -> String {
        net_display(net)
    }

    /// `_segment_item` — the full `FixedCopperItem` for one trace segment.
    #[allow(clippy::too_many_arguments)] // mirrors the pre-migration helper's parameter list
    fn segment_item(
        &self,
        py: Python<'_>,
        start: (f64, f64),
        end: (f64, f64),
        width: f64,
        net: Option<String>,
        layer: &str,
        margin: f64,
    ) -> PyResult<Py<FixedCopperItem>> {
        let (x1a, y1a) = (start.0, start.1);
        let (x2a, y2a) = (end.0, end.1);
        let kernel = tg(py)?.getattr("fixed_copper_segment_item_geom_py")?;
        let (rect, slack_mm): ((f64, f64, f64, f64), f64) =
            kernel.call1(((x1a, y1a), (x2a, y2a), width, margin))?.extract()?;
        let layers = PyFrozenSet::new(py, [layer.to_string()])?;
        let exact = PyDict::new(py);
        exact.set_item("p0", (x1a, y1a))?;
        exact.set_item("p1", (x2a, y2a))?;
        exact.set_item("width", width)?;
        let label = format!(
            "segment {} ({:.2},{:.2})-({:.2},{:.2})",
            self.label_net(&net),
            x1a,
            y1a,
            x2a,
            y2a
        );
        Py::new(
            py,
            FixedCopperItem {
                kind: "segment".to_string(),
                net,
                layers: layers.unbind(),
                rect,
                exact: exact.into_any().unbind(),
                slack_mm,
                margin_mm: margin,
                label,
                edges: None,
            },
        )
    }

    /// `_via_item`.
    fn via_item(
        &self,
        py: Python<'_>,
        position: (f64, f64),
        diameter: f64,
        net: Option<String>,
        layers: Bound<'_, PyFrozenSet>,
        margin: f64,
    ) -> PyResult<Py<FixedCopperItem>> {
        let (x, y) = position;
        let kernel = tg(py)?.getattr("fixed_copper_via_item_geom_py")?;
        let (rect, slack_mm): ((f64, f64, f64, f64), f64) =
            kernel.call1((position, diameter, margin))?.extract()?;
        let exact = PyDict::new(py);
        exact.set_item("center", (x, y))?;
        exact.set_item("diameter", diameter)?;
        let label = format!("via {} ({:.2},{:.2}) d={:.2}", self.label_net(&net), x, y, diameter);
        Py::new(
            py,
            FixedCopperItem {
                kind: "via".to_string(),
                net,
                layers: layers.unbind(),
                rect,
                exact: exact.into_any().unbind(),
                slack_mm,
                margin_mm: margin,
                label,
                edges: None,
            },
        )
    }

    /// `_zone_item` — returns `None` for zones with no usable polygon.
    fn zone_item(
        &self,
        py: Python<'_>,
        zone: &Bound<'_, PyAny>,
        margin: f64,
    ) -> PyResult<Option<Py<FixedCopperItem>>> {
        let polygon_obj = zone.getattr("polygon")?;
        let polygon: Vec<(f64, f64)> = polygon_obj.extract()?;
        if polygon.is_empty() || polygon.len() < 3 {
            return Ok(None);
        }
        let zone_layers: Vec<String> = zone.getattr("layers")?.extract()?;
        let all_layers = PyFrozenSet::new(py, COPPER_LAYER_NAMES)?;
        let layers = frozenset_intersect(py, zone_layers, &all_layers)?;
        if layers.is_empty() {
            return Ok(None);
        }
        let net_classes: Vec<String> = zone.getattr("net_classes")?.extract()?;
        let net = net_classes.first().cloned();
        let name: String = zone.getattr("name")?.extract()?;

        let polygon_list = PyList::new(py, polygon.iter().copied())?;
        let edges = tg(py)?
            .getattr("fixed_copper_convex_polygon_edges_py")?
            .call1((polygon_list.clone(), margin))?
            .extract::<Option<Py<PyAny>>>()?;
        let rect: (f64, f64, f64, f64) = tg(py)?
            .getattr("fixed_copper_zone_item_rect_py")?
            .call1((polygon_list.clone(), margin))?
            .extract()?;
        let exact = PyDict::new(py);
        exact.set_item("polygon", polygon_list)?;
        let label = format!("zone {} net={}", name, self.label_net(&net));
        Ok(Some(Py::new(
            py,
            FixedCopperItem {
                kind: "zone".to_string(),
                net,
                layers: layers.unbind(),
                rect,
                exact: exact.into_any().unbind(),
                slack_mm: f64::INFINITY,
                margin_mm: margin,
                label,
                edges,
            },
        )?))
    }

    /// `_other_component_pad_item` — one pinned component's pad as a fixed
    /// obstacle, in the solver frame.
    #[allow(clippy::too_many_arguments)] // mirrors the pre-migration helper's parameter list
    fn other_component_pad_item(
        &self,
        py: Python<'_>,
        comp: &Bound<'_, PyAny>,
        pin: &Bound<'_, PyAny>,
        margin: f64,
    ) -> PyResult<Option<Py<FixedCopperItem>>> {
        let layers = self.pin_copper_layers(py, pin)?;
        if layers.is_empty() {
            return Ok(None);
        }
        let center: Option<(f64, f64)> = comp.getattr("initial_position")?.extract()?;
        let (cx, cy) = match center {
            Some(c) => c,
            None => return Ok(None),
        };
        let rot_raw: Option<f64> = comp.getattr("initial_rotation")?.extract()?;
        let rot_idx = match rot_raw {
            None => 0,
            Some(r) => r as i64,
        };
        let (hw, hh) = self.local_pad_half(py, pin)?;
        let pos: (f64, f64) = pin.getattr("position")?.extract()?;
        let (lx, ly) = (pos.0, pos.1);
        let kernel = tg(py)?.getattr("fixed_copper_other_pad_item_geom_py")?;
        let (rect, encoded_rect, slack_mm): PadItemGeomPy =
            kernel.call1((lx, ly, hw, hh, rot_idx, cx, cy, margin))?.extract()?;
        let net = getattr_opt_str(py, pin, "net")?;
        let ref_str: String = comp.getattr("ref")?.extract()?;
        let number: String = getattr_py_str(py, pin, "number", "")?;
        let label = format!("pad {}.{} net={}", ref_str, number, self.label_net(&net));
        let exact = PyDict::new(py);
        exact.set_item("rect", rect)?;
        Ok(Some(Py::new(
            py,
            FixedCopperItem {
                kind: "pad".to_string(),
                net,
                layers: layers.unbind(),
                rect: encoded_rect,
                exact: exact.into_any().unbind(),
                slack_mm,
                margin_mm: margin,
                label,
                edges: None,
            },
        )?))
    }
}

#[pymethods]
impl FixedCopperBuilder {
    #[new]
    #[pyo3(signature = (
        *,
        netlist,
        free_refs,
        parse_result = None,
        margin_mm = DEFAULT_MARGIN_MM,
        include_other_pads = true,
        copper_layers = None
    ))]
    fn new(
        py: Python<'_>,
        netlist: Bound<'_, PyAny>,
        free_refs: Bound<'_, PyAny>,
        parse_result: Option<Bound<'_, PyAny>>,
        margin_mm: f64,
        include_other_pads: bool,
        copper_layers: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        guard(|| {
            let copper_layers = match copper_layers {
                Some(v) if !v.is_none() => v.extract::<Py<PyFrozenSet>>()?,
                _ => PyFrozenSet::new(py, COPPER_LAYER_NAMES)?.unbind(),
            };
            Ok(FixedCopperBuilder {
                netlist: netlist.unbind(),
                free_refs: free_refs.unbind(),
                parse_result: match parse_result {
                    Some(v) if !v.is_none() => Some(v.unbind()),
                    _ => None,
                },
                margin_mm,
                include_other_pads,
                copper_layers,
            })
        })
    }

    /// `build_free_component_pads(netlist, free_refs, copper_layers)`:
    /// per-pad local geometry for every *free* component.
    fn build_free_component_pads(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| {
            let result = PyDict::new(py);
            let netlist = self.netlist.bind(py);
            let components = netlist.getattr("components")?;
            let free_refs = self.free_refs.bind(py);
            for comp in components.try_iter()? {
                let comp = comp?;
                let ref_str: String = comp.getattr("ref")?.extract()?;
                if !free_refs.contains(ref_str.as_str())? {
                    continue;
                }
                let pads = PyList::empty(py);
                let pins = comp.getattr("pins")?;
                for pin in pins.try_iter()? {
                    let pin = pin?;
                    let layers = self.pin_copper_layers(py, &pin)?;
                    if layers.is_empty() {
                        continue;
                    }
                    let (hw, hh) = self.local_pad_half(py, &pin)?;
                    let number: String = getattr_py_str(py, &pin, "number", "")?;
                    let net = getattr_opt_str(py, &pin, "net")?;
                    let center = getattr_pos(py, &pin, "position", (0.0, 0.0))?;
                    let pad = Py::new(
                        py,
                        PadRectLocal {
                            number,
                            net,
                            layers: layers.unbind(),
                            center,
                            half: (hw, hh),
                        },
                    )?;
                    pads.append(pad)?;
                }
                result.set_item(ref_str, pads)?;
            }
            Ok(result.unbind())
        })
    }

    /// `build_fixed_copper_items(parse_result, netlist, free_refs, ...)`:
    /// the fixed-copper obstacle list (traces, vias, zones, other pads) in
    /// the solver's normalized frame.
    fn build_fixed_copper_items(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let parse_result = match &self.parse_result {
                Some(p) => p.bind(py),
                None => {
                    return Err(PyRuntimeError::new_err(
                        "FixedCopperBuilder.parse_result is None",
                    ))
                }
            };
            let items = PyList::empty(py);
            let board = parse_result.getattr("board")?;
            let (ox0, oy0) = if board.is_none() {
                (0.0, 0.0)
            } else {
                let origin: (f64, f64) = board.getattr("origin")?.extract()?;
                origin
            };

            // Traces (raw frame -> normalized).
            let traces = parse_result.getattr("traces")?;
            let copper_layers = self.copper_layers.bind(py);
            for t in traces.try_iter()? {
                let t = t?;
                let layer: String = t.getattr("layer")?.extract()?;
                if !copper_layers.contains(layer.as_str())? {
                    continue;
                }
                let start: (f64, f64) = t.getattr("start")?.extract()?;
                let end: (f64, f64) = t.getattr("end")?.extract()?;
                let width: f64 = t.getattr("width")?.extract()?;
                let net: Option<String> = t.getattr("net")?.extract()?;
                let item = self.segment_item(
                    py,
                    (start.0 - ox0, start.1 - oy0),
                    (end.0 - ox0, end.1 - oy0),
                    width,
                    net,
                    &layer,
                    self.margin_mm,
                )?;
                items.append(item)?;
            }

            // Vias (raw frame -> normalized).
            let vias = parse_result.getattr("vias")?;
            for v in vias.try_iter()? {
                let v = v?;
                let v_layers: Vec<String> = v.getattr("layers")?.extract()?;
                let layers = frozenset_intersect(py, v_layers, copper_layers)?;
                if layers.is_empty() {
                    continue;
                }
                let pos: (f64, f64) = v.getattr("position")?.extract()?;
                let diameter: f64 = v.getattr("diameter")?.extract()?;
                let net: Option<String> = v.getattr("net")?.extract()?;
                let item = self.via_item(
                    py,
                    (pos.0 - ox0, pos.1 - oy0),
                    diameter,
                    net,
                    layers,
                    self.margin_mm,
                )?;
                items.append(item)?;
            }

            // Zones (already normalized).
            if !board.is_none() {
                let zones = board.getattr("zones")?;
                for z in zones.try_iter()? {
                    let z = z?;
                    if let Some(item) = self.zone_item(py, &z, self.margin_mm)? {
                        items.append(item)?;
                    }
                }
            }

            // Pinned components' pads.
            if self.include_other_pads {
                let netlist = self.netlist.bind(py);
                let components = netlist.getattr("components")?;
                let free_refs = self.free_refs.bind(py);
                for comp in components.try_iter()? {
                    let comp = comp?;
                    let ref_str: String = comp.getattr("ref")?.extract()?;
                    if free_refs.contains(ref_str.as_str())? {
                        continue;
                    }
                    let pins = comp.getattr("pins")?;
                    for pin in pins.try_iter()? {
                        let pin = pin?;
                        if let Some(item) =
                            self.other_component_pad_item(py, &comp, &pin, self.margin_mm)?
                        {
                            items.append(item)?;
                        }
                    }
                }
            }

            Ok(items.unbind())
        })
    }

    /// `audit_fixed_copper(pads_by_ref, items, resolved_positions_mm,
    /// resolved_rotations)` — the R24 item-3 post-solve audit.
    #[staticmethod]
    fn audit_fixed_copper(
        py: Python<'_>,
        pads_by_ref: &Bound<'_, PyAny>,
        items: &Bound<'_, PyAny>,
        resolved_positions_mm: &Bound<'_, PyAny>,
        resolved_rotations: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyList>> {
        guard(|| {
            let violations = PyList::empty(py);
            let pads_by_ref = pads_by_ref.cast::<PyDict>()?;
            for (ref_obj, pads) in pads_by_ref.iter() {
                let ref_str: String = ref_obj.extract()?;
                let center: Option<(f64, f64)> = resolved_positions_mm.get_item(ref_str.as_str())?.extract()?;
                let Some(center) = center else {
                    violations.append(Py::new(
                        py,
                        FixedCopperAuditViolation {
                            ref_field: ref_str.clone(),
                            pad_number: String::new(),
                            item_label: String::new(),
                            item_kind: String::new(),
                            item_net: None,
                            required_mm: 0.0,
                            actual_mm: f64::NAN,
                            reason: format!("missing resolved position for {ref_str}"),
                        },
                    )?)?;
                    continue;
                };
                let rot_raw: Option<f64> = resolved_rotations.get_item(ref_str.as_str())?.extract()?;
                let rot_idx = rot_raw.map(|r| r as i64).unwrap_or(0);
                let pads = pads.cast::<PyList>()?;
                let mut comp_nets: HashSet<String> = HashSet::new();
                for p in pads.iter() {
                    let p = p.cast::<PadRectLocal>()?;
                    let p = p.borrow();
                    if let Some(n) = &p.net {
                        comp_nets.insert(n.clone());
                    }
                }
                for p in pads.iter() {
                    let p = p.cast::<PadRectLocal>()?;
                    let p = p.borrow();
                    let (lx, ly) = p.center;
                    let (hw, hh) = p.half;
                    let rect: (f64, f64, f64, f64) = tg(py)?
                        .getattr("fixed_copper_pad_world_rect_py")?
                        .call1((lx, ly, hw, hh, rot_idx, center.0, center.1))?
                        .extract()?;
                    for item_obj in items.try_iter()? {
                        let item_obj = item_obj?;
                        let item = item_obj.cast::<FixedCopperItem>()?;
                        let item = item.borrow();
                        let pad_layers = p.layers.bind(py);
                        let item_layers = item.layers.bind(py);
                        if frozensets_disjoint(pad_layers, item_layers)? {
                            continue;
                        }
                        if let Some(n) = &item.net
                            && comp_nets.contains(n)
                        {
                            continue;
                        }
                        let actual = exact_clearance_mm_dispatch(py, rect, &item)?;
                        if actual < item.margin_mm {
                            let reason = format!(
                                "{ref_str} pad {} is {:.4}mm from {} ({}) but {}mm is required",
                                p.number,
                                actual,
                                item.kind,
                                net_display(&item.net),
                                item.margin_mm
                            );
                            violations.append(Py::new(
                                py,
                                FixedCopperAuditViolation {
                                    ref_field: ref_str.clone(),
                                    pad_number: p.number.clone(),
                                    item_label: item.label.clone(),
                                    item_kind: item.kind.clone(),
                                    item_net: item.net.clone(),
                                    required_mm: item.margin_mm,
                                    actual_mm: actual,
                                    reason,
                                },
                            )?)?;
                        }
                    }
                }
            }
            Ok(violations.unbind())
        })
    }
}

/// `exact_clearance_mm(pad_rect, item)` — dispatch on `item.kind` and call
/// the pinned `temper-geometry` `fixed_copper_exact_clearance_mm_py` kernel
/// with the item's `exact` dict, mirroring the pre-migration function.
fn exact_clearance_mm_dispatch(
    py: Python<'_>,
    pad_rect: (f64, f64, f64, f64),
    item: &FixedCopperItem,
) -> PyResult<f64> {
    let exact = item.exact.bind(py);
    let kernel = tg(py)?.getattr("fixed_copper_exact_clearance_mm_py")?;
    match item.kind.as_str() {
        "segment" => {
            let p0: (f64, f64) = exact.get_item("p0")?.extract()?;
            let p1: (f64, f64) = exact.get_item("p1")?.extract()?;
            let width: f64 = exact.get_item("width")?.extract()?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("p0", p0)?;
            kwargs.set_item("p1", p1)?;
            kwargs.set_item("width", width)?;
            Ok(kernel.call((pad_rect, "segment"), Some(&kwargs))?.extract()?)
        }
        "via" => {
            let center: (f64, f64) = exact.get_item("center")?.extract()?;
            let diameter: f64 = exact.get_item("diameter")?.extract()?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("center", center)?;
            kwargs.set_item("diameter", diameter)?;
            Ok(kernel.call((pad_rect, "via"), Some(&kwargs))?.extract()?)
        }
        "pad" => {
            let other_rect: (f64, f64, f64, f64) = exact.get_item("rect")?.extract()?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("other_rect", other_rect)?;
            Ok(kernel.call((pad_rect, "pad"), Some(&kwargs))?.extract()?)
        }
        "zone" => {
            let polygon: Vec<(f64, f64)> = exact.get_item("polygon")?.extract()?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("polygon", polygon)?;
            Ok(kernel.call((pad_rect, "zone"), Some(&kwargs))?.extract()?)
        }
        other => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "unknown fixed-copper item kind {other:?}"
        ))),
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as the `fixed_copper_builder` submodule
/// (`temper_design_bundle_python.fixed_copper_builder`).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "fixed_copper_builder")?;
    sub.add_class::<PadRectLocal>()?;
    sub.add_class::<FixedCopperItem>()?;
    sub.add_class::<FixedCopperAuditViolation>()?;
    sub.add_class::<FixedCopperBuilder>()?;
    module.add_submodule(&sub)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn pad_rect_local_fields() {
        Python::attach(|py| {
            let layers = PyFrozenSet::new(py, ["F.Cu"]).unwrap();
            let pad = PadRectLocal {
                number: "1".into(),
                net: Some("NET_A".into()),
                layers: layers.unbind(),
                center: (0.0, 0.0),
                half: (0.5, 0.5),
            };
            assert_eq!(pad.number, "1");
            assert_eq!(pad.net.as_deref(), Some("NET_A"));
            assert_eq!(pad.center, (0.0, 0.0));
            assert_eq!(pad.half, (0.5, 0.5));
            assert_eq!(pad.layers.bind(py).len(), 1);
        })
    }

    #[test]
    fn item_fields() {
        Python::attach(|py| {
            let layers = PyFrozenSet::new(py, ["F.Cu"]).unwrap();
            let exact = PyDict::new(py);
            exact.set_item("p0", (0.0, 0.0)).unwrap();
            exact.set_item("p1", (4.0, 0.0)).unwrap();
            exact.set_item("width", 0.3).unwrap();
            let item = FixedCopperItem {
                kind: "segment".into(),
                net: None,
                layers: layers.unbind(),
                rect: (0.0, 0.0, 4.0, 4.0),
                exact: exact.into_any().unbind(),
                slack_mm: 0.1,
                margin_mm: DEFAULT_MARGIN_MM,
                label: "seg".into(),
                edges: None,
            };
            assert_eq!(item.rect, (0.0, 0.0, 4.0, 4.0));
            assert_eq!(item.slack_mm, 0.1);
            assert_eq!(item.margin_mm, DEFAULT_MARGIN_MM);
            assert!(item.edges.is_none());
        })
    }

    #[test]
    fn audit_violation_fields() {
        let v = FixedCopperAuditViolation {
            ref_field: "U1".into(),
            pad_number: "1".into(),
            item_label: "seg".into(),
            item_kind: "segment".into(),
            item_net: Some("NET_B".into()),
            required_mm: 0.05,
            actual_mm: 0.0,
            reason: "U1 pad 1 is 0.0000mm from segment (NET_B) but 0.05mm is required".into(),
        };
        assert_eq!(v.ref_field, "U1");
        assert_eq!(v.pad_number, "1");
        assert_eq!(v.item_kind, "segment");
        assert_eq!(v.item_net.as_deref(), Some("NET_B"));
        assert!(v.actual_mm.is_finite() && v.actual_mm == 0.0);
    }

    #[test]
    fn missing_position_violation_uses_nan() {
        let v = FixedCopperAuditViolation {
            ref_field: "U1".into(),
            pad_number: String::new(),
            item_label: String::new(),
            item_kind: String::new(),
            item_net: None,
            required_mm: 0.0,
            actual_mm: f64::NAN,
            reason: "missing resolved position for U1".into(),
        };
        assert!(v.actual_mm.is_nan());
    }

    #[test]
    fn net_display_matches_fstring() {
        assert_eq!(net_display(&None), "None");
        assert_eq!(net_display(&Some("NET_B".into())), "NET_B");
    }

    #[test]
    fn mm_to_units_delegates_to_kernel() {
        Python::attach(|py| {
            let v = tg(py)
                .unwrap()
                .getattr("fixed_copper_mm_to_units_py")
                .unwrap()
                .call1((0.05,))
                .unwrap()
                .extract::<i64>()
                .unwrap();
            assert_eq!(v, 5);
        })
    }
}

//! The U2 (O-C3) leaf-struct boundary: `Marshal` impls for the owned
//! `Component`/`Pin`/`Net` structs from `temper-data-model`, plus the two
//! tuple impls (`(f64, f64)`, `(String, String)`) their fields need.
//!
//! Unit U3 extends this file with the owned AGGREGATE boundary: `Marshal`
//! for `temper_data_model::Netlist` (components/nets — the derived index
//! dicts are recomputed by the pyclass constructor on write-back) and for
//! [`OwnedBoard`], the pyo3-side Board aggregate that composes the
//! data-model [`Board`]'s owned fields with the KEEP fields (`zones`,
//! `mounting_holes`, `ground_domains`, `layer_stackup`, `outline_polygon`)
//! as [`Plain::Opaque`] identity passthroughs. The keeps cannot live in
//! `temper-data-model` (it is pyo3-free for the wasm32 tier), so they live
//! here, on the pyo3 side of the boundary — identity-preserved, never
//! reconstructed (see the U3 VERIFICATION.md section for the field table).
//!
//! # Reading (never `extract::<Py<T>>()`)
//!
//! Each `from_python` reads the pyclass's fields via `obj.getattr("...")` and
//! marshals each through the scalar/container `Marshal` impls from
//! `marshal.rs` — **never** `extract::<Py<T>>()`, which is the
//! cross-`.so` pyclass-identity blocker
//! (`docs/evidence/2026-08-12-cross-extension-pyclass-identity.md`). A Rust
//! field that *names* a foreign pyclass is the bug; an owned struct with
//! plain scalar/collection fields is not.
//!
//! # Writing (runtime class lookup, not a compile-time dep)
//!
//! Each `to_python` reconstructs a faithful Python object of the design-bundle
//! pyclass by **runtime import** —
//! `py.import("temper_design_bundle_python")?.getattr("netlist_contracts")?.getattr("Component")`
//! — then calling it with keyword args, exactly the "runtime class lookup"
//! approach #1 the cross-extension evidence doc sanctions. This keeps the
//! reconstructed object's type/repr/`==` bit-identical to the original without
//! naming the pyclass in a Rust type (and without a `temper-design-bundle`
//! dependency edge, which would re-introduce the duplicated-`LazyTypeObject`
//! hazard). The tests inject a faithful `@dataclass` stand-in for the classes
//! into `sys.modules` under the same path (the d3–d7 mock pattern), so the
//! round-trip gate proves losslessness self-containedly.
//!
//! # The int-vs-float hazards (why `bounds` is `Vec<Val>`, not `Vec<f64>`)
//!
//! `Component.bounds` is the field the pipeline demonstrably populates with
//! ints (`Component("R1", "fp", (1, 2))` — see `netlist_contracts.rs:11-28`),
//! so it marshals element-wise through [`Val`] (int stays int, float stays
//! float) and is rebuilt as a **tuple** — the contractual `tuple[float,
//! float]`, NOT a `Vec`-marshalled list. The other numeric fields
//! (`position`, `initial_position`, `width`, `height`, `drill`, `weight`,
//! `max_current`, …) are always-float in the real pipeline, so they are
//! concrete `f64`/`(f64, f64)` and REJECT an int-shaped value loudly (the U0
//! "an int is not a float" discipline) rather than widen it.
//!
//! U3 adds the aggregate-level hazards: `Board.width`/`height`/`origin`/
//! `keepouts` are `Val`-shaped (the `board_contracts.Board` pyclass
//! raw-stores every constructor argument — `Board(100, 80)` keeps int width,
//! and `Board.from_polygon` computes width as `x_max - x_min`, type-
//! preserving — so ints are legal contract values, not pipeline accidents).
//! The `(Val, Val)` and `(Val, Val, Val, Val)` tuple impls below serve them.
//!
//! # U5: the remaining BoardState COLLECTION fields (unit O-C3/U5)
//!
//! U5 ports the owned collection FIELD types for the remaining BoardState
//! fields — `zones`, `component_zone_map`, `zone_slots`,
//! `layer_assignments`, `routes`, `vias`, `violations`, `placements`,
//! `component_domain_map` and the three violation lists. The owned element
//! structs + the owned collection types live in `temper-data-model`
//! (`collections.rs` — pyo3-free, with the full field table); the `Marshal`
//! impls here are the pyo3 half:
//!
//! - **frozenset fields** (`zones`, `component_zone_map`,
//!   `component_domain_map`, `zone_slots`, `layer_assignments`, `routes`,
//!   `vias`, `placements`) are owned as the `*Set` `HashSet` newtypes and
//!   marshalled by the shared [`frozenset_read`]/[`frozenset_write`]
//!   helpers: read accepts a frozenset OR a set, write always rebuilds a
//!   frozenset whose iteration order is a DETERMINISTIC function of the
//!   values (the rebuilt element objects are sorted by their Python `repr`
//!   before insertion — the U1 recorded bound, see `collections.rs`'s
//!   module doc). Bit-identity is pinned by the gate only on the guaranteed
//!   shapes (empty/single-element); content + type + determinism are pinned
//!   for multi-element sets.
//! - **the three violation lists** (`drc_violations`,
//!   `connectivity_violations`, `placement_violations`) are Python TUPLES —
//!   owned as the order-preserving `*List` `Vec` newtypes and marshalled by
//!   the shared [`tuple_list_read`]/[`tuple_list_write`] helpers (a list is
//!   REJECTED — the contract is a tuple, and accepting a list would silently
//!   change the collection kind on write-back).
//! - **`violations`** (the PreflightReport dict the `PreflightStage`
//!   writes) is owned as [`PreflightReport`] + [`PreflightCheck`] with the
//!   `details` leaves through [`OwnedPlain`] (the pyo3-free subset of
//!   `Plain`).
//!
//! Write-back is runtime class lookup at the REAL module paths — the zone
//! geometry `Zone` at `temper_placer.deterministic.stages.zone_geometry`,
//! `Trace`/`Via` at `temper_design_bundle_python.board_contracts`,
//! `LayerAssignment` at `temper_design_bundle_python` (root), `Violation`
//! at `temper_placer.router_v6.constraints_drc_oracle`, `Point` at
//! `temper_placer.router_v6.constraints_geometry`, the two stage violation
//! dataclasses at their own stage modules. The tests register faithful
//! stand-in classes under those same paths (the d3–d7 mock pattern).

#![allow(dead_code)] // U2/U3 scaffolding: consumed by U4+'s BoardState field
// ports and the stage rewires; until then only the round-trip gate tests
// exercise this file.

use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFrozenSet, PySet, PyTuple};

use pyo3::IntoPyObjectExt;

use temper_data_model::{
    Board, ClearanceCredit, ClearanceGrid, ClearanceMatrix, Component, ConnectivityViolation,
    ConnectivityViolationList, DrcOracle, LayerAssignment, LayerAssignmentSet, Net, Netlist, OwnedPlain,
    Placement, PlacementSet, PlacementViolation, PlacementViolationList, Pin, PreflightCheck,
    PreflightReport, Route, RouteSet, SlotPos, StrPairSet, Val, Via, ViaSet, Violation,
    ViolationList, Zone, ZoneSet, ZoneSlots, ZoneSlotsSet,
};

use crate::marshal::{Marshal, Plain, type_err};

// ---------------------------------------------------------------------------
// Tuple impls — the 2-element containers the leaf fields use
// ---------------------------------------------------------------------------

impl Marshal for (f64, f64) {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "(float, float)", "expected a 2-tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "(float, float)",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        let x = <f64 as Marshal>::from_python(py, &t.get_item(0)?)
            .map_err(|e| type_err(obj, "(float, float)", &format!("element 0: {e}")))?;
        let y = <f64 as Marshal>::from_python(py, &t.get_item(1)?)
            .map_err(|e| type_err(obj, "(float, float)", &format!("element 1: {e}")))?;
        Ok((x, y))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyTuple::new(py, [self.0, self.1])?
            .into_any()
            .unbind())
    }
}

impl Marshal for (String, String) {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "(str, str)", "expected a 2-tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "(str, str)",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        let a = <String as Marshal>::from_python(py, &t.get_item(0)?)
            .map_err(|e| type_err(obj, "(str, str)", &format!("element 0: {e}")))?;
        let b = <String as Marshal>::from_python(py, &t.get_item(1)?)
            .map_err(|e| type_err(obj, "(str, str)", &format!("element 1: {e}")))?;
        Ok((a, b))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyTuple::new(py, [self.0.as_str(), self.1.as_str()])?
            .into_any()
            .unbind())
    }
}

// ---------------------------------------------------------------------------
// Field-shape helpers (the concrete collection kinds the pyclasses hold)
// ---------------------------------------------------------------------------

/// `Component.bounds` — read the `(width, height)` TUPLE element-wise through
/// `Val` (int stays int, float stays float). A list is rejected: the contract
/// is `tuple[float, float]`, and accepting a list would silently change the
/// kind the same way widening an int leaf would change the type.
fn bounds_from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<Val>> {
    let t = obj
        .cast::<PyTuple>()
        .map_err(|_| type_err(obj, "bounds", "expected a (width, height) tuple"))?;
    let mut out = Vec::with_capacity(t.len());
    for item in t.iter() {
        out.push(Val::from_python(py, &item)?);
    }
    Ok(out)
}

/// Rebuild `bounds` as a TUPLE (the contractual kind) from `Vec<Val>`.
fn bounds_to_python(py: Python<'_>, vals: &[Val]) -> PyResult<Py<PyAny>> {
    let items: Vec<Py<PyAny>> = vals
        .iter()
        .map(|v| v.to_python(py))
        .collect::<PyResult<_>>()?;
    Ok(PyTuple::new(py, items.iter().map(|o| o.bind(py)))?
        .into_any()
        .unbind())
}

/// `Component.attributes` — an insertion-ordered `dict[str, str]`. Read in
/// iteration order (Python 3.7+ dicts are ordered) and rebuild in that order.
fn attrs_from_python(obj: &Bound<'_, PyAny>) -> PyResult<Vec<(String, String)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "attributes", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let key = k
            .extract::<String>()
            .map_err(|_| type_err(&k, "attributes", "expected a str key"))?;
        let val = v
            .extract::<String>()
            .map_err(|_| type_err(&v, "attributes", "expected a str value"))?;
        out.push((key, val));
    }
    Ok(out)
}

fn attrs_to_python(py: Python<'_>, pairs: &[(String, String)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (k, v) in pairs {
        d.set_item(k.as_str(), v.as_str())?;
    }
    Ok(d.into_any().unbind())
}

/// `Component.tags` — a `frozenset` of strings, read in iteration order (a
/// frozenset has no duplicates, so the `Vec` is faithful). `to_python` always
/// writes back a frozenset (the dataclass contract), same as the U1
/// `HashSet<SlotId>` write-back. Iteration order of the REBUILT frozenset
/// matches the original only for collision-free sets — the U1 recorded bound.
fn tags_from_python(obj: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let is_frozen = obj.is_instance_of::<PyFrozenSet>();
    let is_mutable = obj.is_instance_of::<PySet>();
    if !is_frozen && !is_mutable {
        return Err(type_err(obj, "tags", "expected frozenset or set"));
    }
    let mut out = Vec::with_capacity(obj.len()?);
    for item in obj.try_iter()? {
        let item = item?;
        let tag = item
            .extract::<String>()
            .map_err(|_| type_err(&item, "tags", "expected a str element"))?;
        out.push(tag);
    }
    Ok(out)
}

fn tags_to_python(py: Python<'_>, tags: &[String]) -> PyResult<Py<PyAny>> {
    Ok(PyFrozenSet::new(py, tags.iter().map(|t| pyo3::types::PyString::new(py, t)))?
        .into_any()
        .unbind())
}

/// The design-bundle pyclass at `temper_design_bundle_python.netlist_contracts.<name>`,
/// resolved at call time (runtime class lookup — see the module doc).
fn netlist_cls<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_design_bundle_python")?
        .getattr("netlist_contracts")?
        .getattr(name)
}

// ---------------------------------------------------------------------------
// Pin
// ---------------------------------------------------------------------------

impl Marshal for Pin {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Pin {
            name: <String as Marshal>::from_python(py, &obj.getattr("name")?)?,
            number: <String as Marshal>::from_python(py, &obj.getattr("number")?)?,
            position: <(f64, f64) as Marshal>::from_python(py, &obj.getattr("position")?)?,
            net: <Option<String> as Marshal>::from_python(py, &obj.getattr("net")?)?,
            width: <f64 as Marshal>::from_python(py, &obj.getattr("width")?)?,
            height: <f64 as Marshal>::from_python(py, &obj.getattr("height")?)?,
            shape: <String as Marshal>::from_python(py, &obj.getattr("shape")?)?,
            layer: <String as Marshal>::from_python(py, &obj.getattr("layer")?)?,
            drill: <f64 as Marshal>::from_python(py, &obj.getattr("drill")?)?,
            is_pth: <bool as Marshal>::from_python(py, &obj.getattr("is_pth")?)?,
            roundrect_ratio: <f64 as Marshal>::from_python(py, &obj.getattr("roundrect_ratio")?)?,
            pad_rotation_deg: <f64 as Marshal>::from_python(py, &obj.getattr("pad_rotation_deg")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = netlist_cls(py, "Pin")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("name", self.name.as_str())?;
        kwargs.set_item("number", self.number.as_str())?;
        kwargs.set_item("position", self.position.to_python(py)?)?;
        kwargs.set_item("net", self.net.to_python(py)?)?;
        kwargs.set_item("width", self.width)?;
        kwargs.set_item("height", self.height)?;
        kwargs.set_item("shape", self.shape.as_str())?;
        kwargs.set_item("layer", self.layer.as_str())?;
        kwargs.set_item("drill", self.drill)?;
        kwargs.set_item("is_pth", self.is_pth)?;
        kwargs.set_item("roundrect_ratio", self.roundrect_ratio)?;
        kwargs.set_item("pad_rotation_deg", self.pad_rotation_deg)?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

impl Marshal for Component {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Component {
            ref_: <String as Marshal>::from_python(py, &obj.getattr("ref")?)?,
            footprint: <String as Marshal>::from_python(py, &obj.getattr("footprint")?)?,
            bounds: bounds_from_python(py, &obj.getattr("bounds")?)?,
            pins: <Vec<Pin> as Marshal>::from_python(py, &obj.getattr("pins")?)?,
            net_class: <String as Marshal>::from_python(py, &obj.getattr("net_class")?)?,
            zone: <Option<String> as Marshal>::from_python(py, &obj.getattr("zone")?)?,
            fixed: <bool as Marshal>::from_python(py, &obj.getattr("fixed")?)?,
            initial_position: <Option<(f64, f64)> as Marshal>::from_python(
                py,
                &obj.getattr("initial_position")?,
            )?,
            initial_rotation: <Option<i64> as Marshal>::from_python(
                py,
                &obj.getattr("initial_rotation")?,
            )?,
            initial_side: <Option<i64> as Marshal>::from_python(py, &obj.getattr("initial_side")?)?,
            attributes: attrs_from_python(&obj.getattr("attributes")?)?,
            tags: tags_from_python(&obj.getattr("tags")?)?,
            sheetpath: <Option<String> as Marshal>::from_python(py, &obj.getattr("sheetpath")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = netlist_cls(py, "Component")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("ref", self.ref_.as_str())?;
        kwargs.set_item("footprint", self.footprint.as_str())?;
        kwargs.set_item("bounds", bounds_to_python(py, &self.bounds)?)?;
        kwargs.set_item("pins", self.pins.to_python(py)?)?;
        kwargs.set_item("net_class", self.net_class.as_str())?;
        kwargs.set_item("zone", self.zone.to_python(py)?)?;
        kwargs.set_item("fixed", self.fixed)?;
        kwargs.set_item("initial_position", self.initial_position.to_python(py)?)?;
        kwargs.set_item("initial_rotation", self.initial_rotation.to_python(py)?)?;
        kwargs.set_item("initial_side", self.initial_side.to_python(py)?)?;
        kwargs.set_item("attributes", attrs_to_python(py, &self.attributes)?)?;
        kwargs.set_item("tags", tags_to_python(py, &self.tags)?)?;
        kwargs.set_item("sheetpath", self.sheetpath.to_python(py)?)?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// Net
// ---------------------------------------------------------------------------

impl Marshal for Net {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Net {
            name: <String as Marshal>::from_python(py, &obj.getattr("name")?)?,
            pins: <Vec<(String, String)> as Marshal>::from_python(py, &obj.getattr("pins")?)?,
            net_class: <String as Marshal>::from_python(py, &obj.getattr("net_class")?)?,
            weight: <f64 as Marshal>::from_python(py, &obj.getattr("weight")?)?,
            max_current: <f64 as Marshal>::from_python(py, &obj.getattr("max_current")?)?,
            voltage_class: <String as Marshal>::from_python(py, &obj.getattr("voltage_class")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = netlist_cls(py, "Net")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("name", self.name.as_str())?;
        kwargs.set_item("pins", self.pins.to_python(py)?)?;
        kwargs.set_item("net_class", self.net_class.as_str())?;
        kwargs.set_item("weight", self.weight)?;
        kwargs.set_item("max_current", self.max_current)?;
        kwargs.set_item("voltage_class", self.voltage_class.as_str())?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U3: the `Val` tuple impls — the aggregate-level int-or-float containers
// ---------------------------------------------------------------------------
//
// `Board.origin` is the `tuple[float, float]` raw-stored by the pyclass
// (`Board(100.0, 80.0, origin=(0, 0))` keeps ints), and `Board.keepouts` is
// `list[tuple[float, float, float, float]]` with the same no-coercion
// contract — so their leaves marshal element-wise through `Val` (int stays
// int, float stays float), mirroring `Component.bounds`. A list-shaped quad
// is rejected (the contract is a tuple), and a wrong arity is a loud error.

impl Marshal for (Val, Val) {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "(Val, Val)", "expected a 2-tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "(Val, Val)",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        let x = <Val as Marshal>::from_python(py, &t.get_item(0)?)
            .map_err(|e| type_err(obj, "(Val, Val)", &format!("element 0: {e}")))?;
        let y = <Val as Marshal>::from_python(py, &t.get_item(1)?)
            .map_err(|e| type_err(obj, "(Val, Val)", &format!("element 1: {e}")))?;
        Ok((x, y))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let x = self.0.to_python(py)?;
        let y = self.1.to_python(py)?;
        Ok(PyTuple::new(py, [x.bind(py), y.bind(py)])?
            .into_any()
            .unbind())
    }
}

impl Marshal for (Val, Val, Val, Val) {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "(Val, Val, Val, Val)", "expected a 4-tuple"))?;
        if t.len() != 4 {
            return Err(type_err(
                obj,
                "(Val, Val, Val, Val)",
                &format!("expected a 4-tuple, got {} elements", t.len()),
            ));
        }
        let mut items = [Val::Int(0); 4];
        for (i, item) in t.iter().enumerate() {
            items[i] = <Val as Marshal>::from_python(py, &item)
                .map_err(|e| type_err(obj, "(Val, Val, Val, Val)", &format!("element {i}: {e}")))?;
        }
        Ok((items[0], items[1], items[2], items[3]))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let items: Vec<Py<PyAny>> = [self.0, self.1, self.2, self.3]
            .into_iter()
            .map(|v| v.to_python(py))
            .collect::<PyResult<_>>()?;
        Ok(PyTuple::new(py, items.iter().map(|o| o.bind(py)))?
            .into_any()
            .unbind())
    }
}

// ---------------------------------------------------------------------------
// U3: Netlist — the owned aggregate (components + nets; indices derived)
// ---------------------------------------------------------------------------
//
// `netlist_contracts.Netlist`'s three `_`-prefixed index dicts are DERIVED:
// `__post_init__`/`build_indices` recompute them unconditionally from
// components/nets (a pure function of the two lists in order), and
// `repr=False` excludes them from `__repr__`. The owned struct therefore
// stores only the two lists; `to_python` calls the pyclass constructor with
// just those kwargs, and the constructor recomputes the indices identically
// — the round-trip is bit-identical (type, repr, and `==`, whose
// `compare=True` index fields are then equal by recomputation).

impl Marshal for Netlist {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Netlist {
            components: <Vec<Component> as Marshal>::from_python(py, &obj.getattr("components")?)?,
            nets: <Vec<Net> as Marshal>::from_python(py, &obj.getattr("nets")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = netlist_cls(py, "Netlist")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("components", self.components.to_python(py)?)?;
        kwargs.set_item("nets", self.nets.to_python(py)?)?;
        // The three index dicts are deliberately NOT passed: the pyclass
        // constructor (`__post_init__` → `build_indices`) recomputes them
        // unconditionally from components/nets, identically to the original.
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U3: Board — the owned aggregate + the Opaque keeps (OwnedBoard)
// ---------------------------------------------------------------------------

/// The design-bundle pyclass at `temper_design_bundle_python.board_contracts.<name>`,
/// resolved at call time (runtime class lookup — see the module doc).
fn board_cls<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_design_bundle_python")?
        .getattr("board_contracts")?
        .getattr(name)
}

/// The pyo3-side owned Board aggregate: the pure-Rust [`Board`] (owned
/// fields) plus the KEEP fields as [`Plain::Opaque`] identity passthroughs.
///
/// The keeps (`zones`, `mounting_holes`, `ground_domains`, `layer_stackup`,
/// `outline_polygon`) cannot live in `temper-data-model` — it is pyo3-free
/// for the wasm32 tier — so they are held here as `Plain::Opaque` (the
/// `Plain` tree's reference-passthrough variant): `from_python` wraps each
/// attribute's Python object UNCONDITIONALLY (never tree-ified, never
/// inspected), and `to_python` returns that same object — identity
/// preserved, nothing reconstructed. `Board._zone_map` is DERIVED (the
/// constructor's `__post_init__` rebuilds it from `zones`, `init=False`), so
/// it is neither stored nor passed.
#[derive(Clone)]
pub struct OwnedBoard {
    /// The data-model owned fields (width/height/origin/keepouts).
    pub board: Board,
    /// Keep: `list[Zone]` — foreign pyclass, identity passthrough.
    pub zones: Plain,
    /// Keep: `list[MountingHole]` — foreign pyclass, identity passthrough.
    pub mounting_holes: Plain,
    /// Keep: `list[GroundDomain]` — foreign pyclass, identity passthrough.
    pub ground_domains: Plain,
    /// Keep: `LayerStackup | None` — foreign pyclass, identity passthrough.
    pub layer_stackup: Plain,
    /// Keep: the outline geometry (list of coords or a shapely polygon),
    /// identity passthrough — lossless for either concrete form.
    pub outline_polygon: Plain,
}

impl Marshal for OwnedBoard {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(OwnedBoard {
            board: Board {
                width: <Val as Marshal>::from_python(py, &obj.getattr("width")?)?,
                height: <Val as Marshal>::from_python(py, &obj.getattr("height")?)?,
                origin: <(Val, Val) as Marshal>::from_python(py, &obj.getattr("origin")?)?,
                keepouts: <Vec<(Val, Val, Val, Val)> as Marshal>::from_python(
                    py,
                    &obj.getattr("keepouts")?,
                )?,
            },
            zones: Plain::Opaque(obj.getattr("zones")?.unbind()),
            mounting_holes: Plain::Opaque(obj.getattr("mounting_holes")?.unbind()),
            ground_domains: Plain::Opaque(obj.getattr("ground_domains")?.unbind()),
            layer_stackup: Plain::Opaque(obj.getattr("layer_stackup")?.unbind()),
            outline_polygon: Plain::Opaque(obj.getattr("outline_polygon")?.unbind()),
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = board_cls(py, "Board")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("width", self.board.width.to_python(py)?)?;
        kwargs.set_item("height", self.board.height.to_python(py)?)?;
        kwargs.set_item("origin", self.board.origin.to_python(py)?)?;
        kwargs.set_item("keepouts", self.board.keepouts.to_python(py)?)?;
        kwargs.set_item("zones", opaque_to_python(py, &self.zones)?)?;
        kwargs.set_item("mounting_holes", opaque_to_python(py, &self.mounting_holes)?)?;
        kwargs.set_item("ground_domains", opaque_to_python(py, &self.ground_domains)?)?;
        kwargs.set_item("layer_stackup", opaque_to_python(py, &self.layer_stackup)?)?;
        kwargs.set_item("outline_polygon", opaque_to_python(py, &self.outline_polygon)?)?;
        // `_zone_map` is `init=False` — the constructor's `__post_init__`
        // rebuilds it from `zones` (the same objects, by identity).
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

/// Return the `Plain::Opaque` payload by reference — the keep fields are
/// Opaque BY CONSTRUCTION (the read path wraps unconditionally), so anything
/// else here is an internal-invariant violation and fails loudly rather than
/// silently reconstructing a keep (keeps are identity-passthrough ONLY).
fn opaque_to_python(py: Python<'_>, keep: &Plain) -> PyResult<Py<PyAny>> {
    match keep {
        Plain::Opaque(obj) => Ok(obj.clone_ref(py)),
        other => {
            let rendered = other.to_python(py)?;
            Err(type_err(
                rendered.bind(py),
                "Board keep field",
                "internal invariant: keep fields are always Plain::Opaque",
            ))
        }
    }
}

// ---------------------------------------------------------------------------
// U4: OwnedClearanceGrid — the owned scalar-dims + net-id registry + the
// numpy-cell-array keeps
// ---------------------------------------------------------------------------

/// The design-bundle pyclass at `temper_placer.deterministic.stages._grid_core.ClearanceGrid`,
/// resolved at call time (runtime class lookup — see the module doc).
fn grid_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_placer.deterministic.stages._grid_core")?
        .getattr("ClearanceGrid")
}

/// The pyo3-side owned `ClearanceGrid` aggregate: the pure-Rust
/// [`ClearanceGrid`] (dims + net-id registry) plus the two numpy-cell-array
/// KEEPs as [`Plain::Opaque`] identity passthroughs.
///
/// The cell arrays are kept (not owned) for the three reasons
/// `temper-data-model`'s `clearance_grid` module documents: (1) they are the
/// zero-copy in-place mutation targets of the `PyBuffer<i32>` rasterisation
/// kernels — owning them as `Vec<i32>` would force an O(rows·cols) copy per
/// kernel call; (2) numpy array identity (dtype/C-order/strides) is numpy's
/// serialization, and this crate's data-model half is pyo3-free; (3) the
/// downstream Cython A* consumes real numpy arrays. Identity passthrough is
/// zero-copy by construction — the SAME array objects are returned, so dtype
/// (`int32`) and bytes are unchanged because nothing is reconstructed.
///
/// `rows`/`cols` and the three caches are DERIVED: the constructor's
/// `__post_init__` recomputes them from the dims on every write-back.
#[derive(Clone)]
pub struct OwnedClearanceGrid {
    /// The data-model owned fields (dims + registry).
    pub grid: ClearanceGrid,
    /// Keep: `list[np.ndarray int32]` (`_trace_net_ids`) — identity.
    pub trace_net_ids: Plain,
    /// Keep: `list[np.ndarray int32]` (`_pad_net_ids`) — identity.
    pub pad_net_ids: Plain,
}

impl Marshal for OwnedClearanceGrid {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(OwnedClearanceGrid {
            grid: ClearanceGrid {
                width_mm: <Val as Marshal>::from_python(py, &obj.getattr("width_mm")?)?,
                height_mm: <Val as Marshal>::from_python(py, &obj.getattr("height_mm")?)?,
                cell_size_mm: <Val as Marshal>::from_python(py, &obj.getattr("cell_size_mm")?)?,
                layer_count: <i64 as Marshal>::from_python(py, &obj.getattr("layer_count")?)?,
                net_to_id: str_i64_dict_from_python(&obj.getattr("_net_to_id")?)?,
                id_to_net: i64_str_dict_from_python(&obj.getattr("_id_to_net")?)?,
                next_net_id: <i64 as Marshal>::from_python(py, &obj.getattr("_next_net_id")?)?,
            },
            trace_net_ids: Plain::Opaque(obj.getattr("_trace_net_ids")?.unbind()),
            pad_net_ids: Plain::Opaque(obj.getattr("_pad_net_ids")?.unbind()),
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = grid_cls(py)?;
        let args = PyTuple::new(
            py,
            [
                self.grid.width_mm.to_python(py)?,
                self.grid.height_mm.to_python(py)?,
                self.grid.cell_size_mm.to_python(py)?,
                self.grid.layer_count.to_python(py)?,
            ],
        )?;
        let obj = cls.call1(args)?;
        obj.setattr("_net_to_id", str_i64_dict_to_python(py, &self.grid.net_to_id)?)?;
        obj.setattr("_id_to_net", i64_str_dict_to_python(py, &self.grid.id_to_net)?)?;
        obj.setattr("_next_net_id", self.grid.next_net_id)?;
        // The cell arrays are KEEPS: overwrite the constructor's fresh arrays
        // with the original objects, by identity (zero-copy, dtype-preserving).
        obj.setattr("_trace_net_ids", opaque_to_python(py, &self.trace_net_ids)?)?;
        obj.setattr("_pad_net_ids", opaque_to_python(py, &self.pad_net_ids)?)?;
        Ok(obj.unbind())
    }
}

// ---------------------------------------------------------------------------
// U4: OwnedDrcOracle — the owned rules/credits/config surface + the foreign
// keeps (_net_class_rules models, zone_manager, PCBGeometry, callable pin_owner)
// ---------------------------------------------------------------------------

/// The design-bundle pyclass at `temper_placer.router_v6.constraints_drc_oracle.DRCOracle`
/// and the `...constraints_design_rules.ClearanceMatrix` it wraps, resolved at
/// call time (runtime class lookup — see the module doc).
fn drc_oracle_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_placer.router_v6.constraints_drc_oracle")?
        .getattr("DRCOracle")
}

fn clearance_matrix_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_placer.router_v6.constraints_design_rules")?
        .getattr("ClearanceMatrix")
}

/// The pyo3-side owned `DRCOracle` aggregate: the pure-Rust [`DrcOracle`]
/// (rules tables + scalar config + the R3 credits + the `pin_owner` Mapping)
/// plus the foreign KEEPs as [`Plain`] identity passthroughs:
/// `_net_class_rules` (a `dict[str, NetClassRules]` whose values are pydantic
/// models — owning the drc-rs `DrcNetClassRuleSnapshot` K1 subset would be
/// LOSSY), `zone_manager` (a plain identity-`==` class holding
/// shapely-adjacent `RoutingZone` polygons), `geometry` (`PCBGeometry`, the
/// Python-visible rstar R-tree over `Track`/`Pad`/`Via`), and a Callable
/// `pin_owner`. See `temper-data-model`'s `drc_oracle` module for the
/// field-by-field table.
#[derive(Clone)]
pub struct OwnedDrcOracle {
    /// The data-model owned fields (rules + config + credits + pin_owner map).
    pub oracle: DrcOracle,
    /// Keep: `dict[str, NetClassRules]` — foreign pydantic values, identity.
    pub net_class_rules: Plain,
    /// Keep: `ZoneManager | None` — `Null` when `None`, else identity.
    pub zone_manager: Plain,
    /// The Callable `pin_owner` keep: `Opaque` when `pin_owner` is callable,
    /// `Null` when it is a Mapping (the owned `oracle.pin_owner` holds it).
    pub pin_owner_callable: Plain,
    /// Keep: `PCBGeometry` — the spatial index, identity.
    pub geometry: Plain,
}

impl Marshal for OwnedDrcOracle {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let rules = obj.getattr("rules")?;
        let matrix = ClearanceMatrix {
            clearances: str_str_f64_dict_from_python(py, &rules.getattr("_clearances")?)?,
            net_to_class: str_str_dict_from_python(&rules.getattr("_net_to_class")?)?,
            differential_pairs: diff_pairs_from_python(py, &rules.getattr("_differential_pairs")?)?,
            default_clearance: <f64 as Marshal>::from_python(py, &rules.getattr("default_clearance")?)?,
            default_track_width: <f64 as Marshal>::from_python(py, &rules.getattr("default_track_width")?)?,
            default_via_diameter: <f64 as Marshal>::from_python(py, &rules.getattr("default_via_diameter")?)?,
            default_via_drill: <f64 as Marshal>::from_python(py, &rules.getattr("default_via_drill")?)?,
        };
        let pin_owner_obj = obj.getattr("pin_owner")?;
        // `pin_owner` may be a Mapping or a Callable (see
        // `constraints_drc_oracle.py::_resolve_owner`). The Mapping form is
        // owned; the Callable form is a keep (a live function object).
        let (pin_owner, pin_owner_callable) = if pin_owner_obj.is_callable() {
            (Vec::new(), Plain::Opaque(pin_owner_obj.unbind()))
        } else {
            (str_str_dict_from_python(&pin_owner_obj)?, Plain::Null)
        };
        Ok(OwnedDrcOracle {
            oracle: DrcOracle {
                rules: matrix,
                search_multiplier: <f64 as Marshal>::from_python(
                    py,
                    &obj.getattr("_search_multiplier")?,
                )?,
                enable_internal_layer_creepage: <bool as Marshal>::from_python(
                    py,
                    &obj.getattr("enable_internal_layer_creepage")?,
                )?,
                clearance_credits: credits_from_python(py, &obj.getattr("clearance_credits")?)?,
                pin_owner,
            },
            net_class_rules: Plain::Opaque(rules.getattr("_net_class_rules")?.unbind()),
            // `Plain::from_python` gives `Null` for `None` and `Opaque` for the
            // ZoneManager instance (a non-builtin class) — exactly the two legal
            // `zone_manager` states.
            zone_manager: Plain::from_python(py, &rules.getattr("zone_manager")?)?,
            pin_owner_callable,
            geometry: Plain::from_python(py, &obj.getattr("geometry")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        // Rebuild the ClearanceMatrix with the owned tables + the keeps.
        let cm_cls = clearance_matrix_cls(py)?;
        let cm = cm_cls.call0()?;
        cm.setattr("_clearances", str_str_f64_dict_to_python(py, &self.oracle.rules.clearances)?)?;
        cm.setattr("_net_to_class", str_str_dict_to_python(py, &self.oracle.rules.net_to_class)?)?;
        cm.setattr("_differential_pairs", diff_pairs_to_python(py, &self.oracle.rules.differential_pairs)?)?;
        cm.setattr("default_clearance", self.oracle.rules.default_clearance)?;
        cm.setattr("default_track_width", self.oracle.rules.default_track_width)?;
        cm.setattr("default_via_diameter", self.oracle.rules.default_via_diameter)?;
        cm.setattr("default_via_drill", self.oracle.rules.default_via_drill)?;
        cm.setattr("_net_class_rules", opaque_to_python(py, &self.net_class_rules)?)?;
        cm.setattr("zone_manager", null_or_opaque_to_python(py, &self.zone_manager)?)?;

        let cls = drc_oracle_cls(py)?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("rules", &cm)?;
        kwargs.set_item("geometry", null_or_opaque_to_python(py, &self.geometry)?)?;
        kwargs.set_item("_search_multiplier", self.oracle.search_multiplier)?;
        kwargs.set_item("enable_internal_layer_creepage", self.oracle.enable_internal_layer_creepage)?;
        kwargs.set_item("clearance_credits", credits_to_python(py, &self.oracle.clearance_credits)?)?;
        kwargs.set_item("pin_owner", pin_owner_to_python(py, &self.oracle.pin_owner, &self.pin_owner_callable)?)?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

/// Return a keep that may be `None` (`Null`) or an opaque passthrough
/// (`Opaque`) — the `zone_manager` / `geometry` / callable-`pin_owner` shape.
/// Anything else is an internal-invariant violation (keeps are identity or
/// `None`, never a reconstructed tree).
fn null_or_opaque_to_python(py: Python<'_>, keep: &Plain) -> PyResult<Py<PyAny>> {
    match keep {
        Plain::Opaque(obj) => Ok(obj.clone_ref(py)),
        Plain::Null => Ok(py.None()),
        other => {
            let rendered = other.to_python(py)?;
            Err(type_err(
                rendered.bind(py),
                "DRCOracle keep field",
                "internal invariant: keeps are Plain::Opaque or Plain::Null",
            ))
        }
    }
}

/// `pin_owner` write-back: the rebuilt dict when the Mapping form was read
/// (`callable` is `Null`), else the kept callable by identity.
fn pin_owner_to_python(
    py: Python<'_>,
    mapping: &[(String, String)],
    callable_keep: &Plain,
) -> PyResult<Py<PyAny>> {
    match callable_keep {
        Plain::Null => str_str_dict_to_python(py, mapping),
        Plain::Opaque(obj) => Ok(obj.clone_ref(py)),
        other => {
            let rendered = other.to_python(py)?;
            Err(type_err(
                rendered.bind(py),
                "pin_owner",
                "internal invariant: callable keep is Opaque or Null",
            ))
        }
    }
}

// ---------------------------------------------------------------------------
// U4: dict/tuple wire helpers (the plain collection kinds the rules use)
// ---------------------------------------------------------------------------

/// `_net_to_id` / `_net_classes`-shaped: a `dict[str, i64]` in insertion order.
fn str_i64_dict_from_python(obj: &Bound<'_, PyAny>) -> PyResult<Vec<(String, i64)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "net registry", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let key = k
            .extract::<String>()
            .map_err(|_| type_err(&k, "net registry", "expected a str key"))?;
        // Net-id values are the registry's own ints (1, 2, 3, ...) — never bool.
        let val = v
            .extract::<i64>()
            .map_err(|_| type_err(&v, "net registry", "expected an int value"))?;
        out.push((key, val));
    }
    Ok(out)
}

fn str_i64_dict_to_python(py: Python<'_>, pairs: &[(String, i64)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (k, v) in pairs {
        d.set_item(k.as_str(), *v)?;
    }
    Ok(d.into_any().unbind())
}

/// `_id_to_net`-shaped: a `dict[i64, str]` in insertion order.
fn i64_str_dict_from_python(obj: &Bound<'_, PyAny>) -> PyResult<Vec<(i64, String)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "net registry", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let key = k
            .extract::<i64>()
            .map_err(|_| type_err(&k, "net registry", "expected an int key"))?;
        let val = v
            .extract::<String>()
            .map_err(|_| type_err(&v, "net registry", "expected a str value"))?;
        out.push((key, val));
    }
    Ok(out)
}

fn i64_str_dict_to_python(py: Python<'_>, pairs: &[(i64, String)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (k, v) in pairs {
        d.set_item(*k, v.as_str())?;
    }
    Ok(d.into_any().unbind())
}

/// `_net_to_class` / Mapping-`pin_owner`-shaped: a `dict[str, str]` in
/// insertion order.
fn str_str_dict_from_python(obj: &Bound<'_, PyAny>) -> PyResult<Vec<(String, String)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "str->str dict", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let key = k
            .extract::<String>()
            .map_err(|_| type_err(&k, "str->str dict", "expected a str key"))?;
        let val = v
            .extract::<String>()
            .map_err(|_| type_err(&v, "str->str dict", "expected a str value"))?;
        out.push((key, val));
    }
    Ok(out)
}

fn str_str_dict_to_python(py: Python<'_>, pairs: &[(String, String)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (k, v) in pairs {
        d.set_item(k.as_str(), v.as_str())?;
    }
    Ok(d.into_any().unbind())
}

/// `_clearances`-shaped: a `dict[(str, str), f64]` in insertion order (each
/// tuple key is the `(class_a, class_b)` pair `set_class_to_class_clearance`
/// stored).
fn str_str_f64_dict_from_python(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, String, f64)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "_clearances", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let t = k
            .cast::<PyTuple>()
            .map_err(|_| type_err(&k, "_clearances", "expected a (class_a, class_b) tuple key"))?;
        if t.len() != 2 {
            return Err(type_err(&k, "_clearances", "expected a 2-tuple key"));
        }
        let a = t
            .get_item(0)?;
        let b = t
            .get_item(1)?;
        let a = a
            .extract::<String>()
            .map_err(|_| type_err(&a, "_clearances", "expected a str"))?;
        let b = b
            .extract::<String>()
            .map_err(|_| type_err(&b, "_clearances", "expected a str"))?;
        // Strict f64: an int-shaped clearance is a loud error (the U0 "an int
        // is not a float" discipline), not a silent widen.
        let val = <f64 as Marshal>::from_python(py, &v)?;
        out.push((a, b, val));
    }
    Ok(out)
}

fn str_str_f64_dict_to_python(py: Python<'_>, rows: &[(String, String, f64)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (a, b, v) in rows {
        let key = PyTuple::new(py, [a.as_str(), b.as_str()])?;
        d.set_item(key, *v)?;
    }
    Ok(d.into_any().unbind())
}

/// `_differential_pairs`-shaped: a `dict[frozenset[str], f64]` in insertion
/// order. The unordered 2-element `frozenset` key is read in its own
/// iteration order and stored as `(a, b)`; `to_python` rebuilds
/// `frozenset((a, b))` with the same two elements in that order, which (same
/// process, same str hashes) reproduces the same table layout.
fn diff_pairs_from_python(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, String, f64)>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "_differential_pairs", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        if !k.is_instance_of::<PyFrozenSet>() {
            return Err(type_err(&k, "_differential_pairs", "expected a frozenset key"));
        }
        let mut nets: Vec<String> = Vec::with_capacity(2);
        for item in k.try_iter()? {
            let item = item?;
            nets.push(
                item.extract::<String>()
                    .map_err(|_| type_err(&item, "_differential_pairs", "expected a str net"))?,
            );
        }
        if nets.len() != 2 {
            return Err(type_err(&k, "_differential_pairs", "expected a 2-net frozenset key"));
        }
        // Strict f64: an int-shaped clearance is a loud error, not a widen.
        let val = <f64 as Marshal>::from_python(py, &v)?;
        out.push((nets[0].clone(), nets[1].clone(), val));
    }
    Ok(out)
}

fn diff_pairs_to_python(py: Python<'_>, rows: &[(String, String, f64)]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for (a, b, v) in rows {
        let items: [Py<PyAny>; 2] = [a.clone().into_py_any(py)?, b.clone().into_py_any(py)?];
        let fs = PyFrozenSet::new(py, items.iter().map(|o| o.bind(py)))?;
        d.set_item(fs, *v)?;
    }
    Ok(d.into_any().unbind())
}

/// `clearance_credits`-shaped: `dict[(ref, lv, hv), (eff, hw, hl, smx, smy, axis)]`
/// in insertion order (the order is load-bearing — the oracle iterates
/// `dict.items()` and the first matching credit wins).
fn credits_from_python(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<Vec<ClearanceCredit>> {
    let d = obj
        .cast::<PyDict>()
        .map_err(|_| type_err(obj, "clearance_credits", "expected a dict"))?;
    let mut out = Vec::with_capacity(d.len());
    for (k, v) in d.iter() {
        let key = k
            .cast::<PyTuple>()
            .map_err(|_| type_err(&k, "clearance_credits", "expected a (ref, lv, hv) tuple key"))?;
        if key.len() != 3 {
            return Err(type_err(&k, "clearance_credits", "expected a 3-tuple key"));
        }
        let key0 = key.get_item(0)?;
        let key1 = key.get_item(1)?;
        let key2 = key.get_item(2)?;
        let component_ref = key0
            .extract::<String>()
            .map_err(|_| type_err(&key0, "clearance_credits", "expected a str component_ref"))?;
        let lv_pin = key1
            .extract::<String>()
            .map_err(|_| type_err(&key1, "clearance_credits", "expected a str lv_pin"))?;
        let hv_pin = key2
            .extract::<String>()
            .map_err(|_| type_err(&key2, "clearance_credits", "expected a str hv_pin"))?;
        let val = v
            .cast::<PyTuple>()
            .map_err(|_| type_err(&v, "clearance_credits", "expected a 6-tuple value"))?;
        if val.len() != 6 {
            return Err(type_err(&v, "clearance_credits", "expected a 6-tuple value"));
        }
        let v0 = val.get_item(0)?;
        let v1 = val.get_item(1)?;
        let v2 = val.get_item(2)?;
        let v3 = val.get_item(3)?;
        let v4 = val.get_item(4)?;
        let v5 = val.get_item(5)?;
        // Strict f64: `add_clearance_credit` float()-coerces every field, so the
        // stored values are always floats; an int-shaped credit field is a loud
        // error (never a silent widen).
        let effective_clearance_mm = <f64 as Marshal>::from_python(py, &v0)?;
        let half_width_mm = <f64 as Marshal>::from_python(py, &v1)?;
        let half_length_mm = <f64 as Marshal>::from_python(py, &v2)?;
        let slot_midpoint_x = <f64 as Marshal>::from_python(py, &v3)?;
        let slot_midpoint_y = <f64 as Marshal>::from_python(py, &v4)?;
        let axis = if v5.is_none() {
            None
        } else {
            Some(
                v5.extract::<String>()
                    .map_err(|_| type_err(&v5, "clearance_credits", "expected 'x', 'y' or None"))?,
            )
        };
        out.push(ClearanceCredit {
            component_ref,
            lv_pin,
            hv_pin,
            effective_clearance_mm,
            half_width_mm,
            half_length_mm,
            slot_midpoint_x,
            slot_midpoint_y,
            axis,
        });
    }
    Ok(out)
}

fn credits_to_python(py: Python<'_>, credits: &[ClearanceCredit]) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    for c in credits {
        let key = PyTuple::new(py, [c.component_ref.as_str(), c.lv_pin.as_str(), c.hv_pin.as_str()])?;
        let items: [Py<PyAny>; 6] = [
            c.effective_clearance_mm.into_py_any(py)?,
            c.half_width_mm.into_py_any(py)?,
            c.half_length_mm.into_py_any(py)?,
            c.slot_midpoint_x.into_py_any(py)?,
            c.slot_midpoint_y.into_py_any(py)?,
            match &c.axis {
                Some(a) => a.clone().into_py_any(py)?,
                None => py.None(),
            },
        ];
        let value = PyTuple::new(py, items.iter().map(|o| o.bind(py)))?;
        d.set_item(key, value)?;
    }
    Ok(d.into_any().unbind())
}

// ---------------------------------------------------------------------------
// U5: the shared collection marshallers — frozenset fields + tuple lists
// ---------------------------------------------------------------------------
//
// `frozenset_read`/`frozenset_write` serve every frozenset-backed `*Set`
// field (`zones`, `component_zone_map`, `component_domain_map`,
// `zone_slots`, `layer_assignments`, `routes`, `vias`, `placements`): read
// accepts a frozenset OR a mutable set (the dataclass default is
// `frozenset()`), write ALWAYS rebuilds a frozenset (the field contract).
//
// The write-back iteration order is SORTED BY PYTHON REPR, deliberately:
// `HashSet` iteration is process-random, an unacceptable property for a
// deterministic engine's write-back. Sorting the REBUILT element objects by
// their CPython `repr` (a deterministic function of the values) makes the
// rebuilt frozenset's table layout — and therefore its Python-side
// iteration order — deterministic across runs. The U1 recorded bound
// applies verbatim: for a COLLISION-FREE set CPython's iteration order is a
// pure function of the values, so the rebuilt frozenset round-trips
// bit-identically; with collisions the order is a
// deterministic-but-different table-layout artifact. Type, membership
// content and `==` are preserved in every case.
//
// `tuple_list_read`/`tuple_list_write` serve the three violation lists
// (`tuple[Violation, ...]` etc.): read casts a TUPLE (a list is rejected —
// the contract is a tuple, and accepting a list would silently change the
// collection kind on write-back), write rebuilds a tuple preserving order.

fn frozenset_read<T: Marshal + Eq + std::hash::Hash>(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<HashSet<T>> {
    let is_frozen = obj.is_instance_of::<PyFrozenSet>();
    let is_mutable = obj.is_instance_of::<PySet>();
    if !is_frozen && !is_mutable {
        return Err(type_err(
            obj,
            "frozenset field",
            "expected frozenset or set",
        ));
    }
    let mut out = HashSet::with_capacity(obj.len()?);
    for item in obj.try_iter()? {
        out.insert(T::from_python(py, &item?)?);
    }
    Ok(out)
}

fn frozenset_write<T: Marshal>(py: Python<'_>, set: &HashSet<T>) -> PyResult<Py<PyAny>> {
    // Rebuild every element, then sort by the element's CPython repr — a
    // deterministic sort key that needs no per-type canonicalization (the
    // repr of a rebuilt element is a pure function of its values). Two
    // distinct owned elements never produce equal reprs (a repr is a
    // function of the fields, and distinct fields render distinctly), so
    // the sort is total in practice; ties (none expected) are stable.
    let mut items: Vec<(String, Py<PyAny>)> = Vec::with_capacity(set.len());
    for element in set {
        let obj = element.to_python(py)?;
        let key: String = obj.bind(py).repr()?.extract()?;
        items.push((key, obj));
    }
    items.sort_by(|a, b| a.0.cmp(&b.0));
    let objs: Vec<Py<PyAny>> = items.into_iter().map(|(_, o)| o).collect();
    Ok(PyFrozenSet::new(py, objs.iter().map(|o| o.bind(py)))?
        .into_any()
        .unbind())
}

fn tuple_list_read<T: Marshal>(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<T>> {
    let t = obj
        .cast::<PyTuple>()
        .map_err(|_| type_err(obj, "violation list", "expected a tuple"))?;
    let mut out = Vec::with_capacity(t.len());
    for item in t.iter() {
        out.push(T::from_python(py, &item)?);
    }
    Ok(out)
}

fn tuple_list_write<T: Marshal>(py: Python<'_>, items: &[T]) -> PyResult<Py<PyAny>> {
    let objs: Vec<Py<PyAny>> = items
        .iter()
        .map(|i| i.to_python(py))
        .collect::<PyResult<_>>()?;
    Ok(PyTuple::new(py, objs.iter().map(|o| o.bind(py)))?
        .into_any()
        .unbind())
}

// ---------------------------------------------------------------------------
// U5: Zone — the zone_geometry 2-field frozen dataclass
// ---------------------------------------------------------------------------

/// The zone-geometry `Zone` class at
/// `temper_placer.deterministic.stages.zone_geometry`, resolved at call
/// time (runtime class lookup — see the module doc).
fn zone_geometry_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_placer.deterministic.stages.zone_geometry")?
        .getattr("Zone")
}

/// `Zone.bounds` — the nested `((x_min, y_min), (x_max, y_max))` TUPLE
/// shape, each coordinate element-wise through `Val` (the stage's
/// documented int-vs-float canon: HV `x_min`/every `y_min` are Python
/// `int` `0`).
fn zone_bounds_from_python(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
) -> PyResult<((Val, Val), (Val, Val))> {
    let t = obj
        .cast::<PyTuple>()
        .map_err(|_| type_err(obj, "Zone.bounds", "expected a ((x_min, y_min), (x_max, y_max)) tuple"))?;
    if t.len() != 2 {
        return Err(type_err(
            obj,
            "Zone.bounds",
            &format!("expected a 2-tuple of 2-tuples, got {} elements", t.len()),
        ));
    }
    let lo = <(Val, Val) as Marshal>::from_python(py, &t.get_item(0)?)
        .map_err(|e| type_err(obj, "Zone.bounds", &format!("lower corner: {e}")))?;
    let hi = <(Val, Val) as Marshal>::from_python(py, &t.get_item(1)?)
        .map_err(|e| type_err(obj, "Zone.bounds", &format!("upper corner: {e}")))?;
    Ok((lo, hi))
}

fn zone_bounds_to_python(
    py: Python<'_>,
    bounds: &((Val, Val), (Val, Val)),
) -> PyResult<Py<PyAny>> {
    let lo = bounds.0.to_python(py)?;
    let hi = bounds.1.to_python(py)?;
    Ok(PyTuple::new(py, [lo.bind(py), hi.bind(py)])?
        .into_any()
        .unbind())
}

impl Marshal for Zone {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Zone {
            name: <String as Marshal>::from_python(py, &obj.getattr("name")?)?,
            bounds: zone_bounds_from_python(py, &obj.getattr("bounds")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = zone_geometry_cls(py)?;
        cls.call1((self.name.as_str(), zone_bounds_to_python(py, &self.bounds)?))
            .map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U5: Route + Via — the board_contracts Trace/Via frozen pyclasses
// ---------------------------------------------------------------------------

/// The design-bundle `Trace`/`Via` classes at
/// `temper_design_bundle_python.board_contracts`, resolved at call time.
fn board_contracts_cls<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_design_bundle_python")?
        .getattr("board_contracts")?
        .getattr(name)
}

impl Marshal for Route {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Route {
            start: <(f64, f64) as Marshal>::from_python(py, &obj.getattr("start")?)?,
            end: <(f64, f64) as Marshal>::from_python(py, &obj.getattr("end")?)?,
            width: <f64 as Marshal>::from_python(py, &obj.getattr("width")?)?,
            layer: <String as Marshal>::from_python(py, &obj.getattr("layer")?)?,
            net: <Option<String> as Marshal>::from_python(py, &obj.getattr("net")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = board_contracts_cls(py, "Trace")?;
        let args = PyTuple::new(
            py,
            [
                self.start.to_python(py)?,
                self.end.to_python(py)?,
                self.width.into_py_any(py)?,
                self.layer.as_str().into_py_any(py)?,
                self.net.to_python(py)?,
            ],
        )?;
        cls.call1(args).map(Bound::unbind)
    }
}

impl Marshal for Via {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Via {
            position: <(f64, f64) as Marshal>::from_python(py, &obj.getattr("position")?)?,
            drill: <f64 as Marshal>::from_python(py, &obj.getattr("drill")?)?,
            width: <f64 as Marshal>::from_python(py, &obj.getattr("width")?)?,
            // `layers` is the `("F.Cu", "B.Cu")` 2-tuple the pyclass defaults
            // to — a wrong arity is a loud error (the U3 keepouts rule).
            layers: <(String, String) as Marshal>::from_python(py, &obj.getattr("layers")?)?,
            net: <Option<String> as Marshal>::from_python(py, &obj.getattr("net")?)?,
            is_diff_pair: <bool as Marshal>::from_python(py, &obj.getattr("is_diff_pair")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = board_contracts_cls(py, "Via")?;
        let args = PyTuple::new(
            py,
            [
                self.position.to_python(py)?,
                self.drill.into_py_any(py)?,
                self.width.into_py_any(py)?,
                self.layers.to_python(py)?,
                self.net.to_python(py)?,
                self.is_diff_pair.into_py_any(py)?,
            ],
        )?;
        cls.call1(args).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U5: LayerAssignment — the design-bundle root-module frozen pyclass
// ---------------------------------------------------------------------------

/// The design-bundle `LayerAssignment` class (registered on the ROOT
/// module — `deterministic_leaves.rs::register` adds it to the
/// `temper_design_bundle_python` module object), resolved at call time.
fn layer_assignment_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_design_bundle_python")?
        .getattr("LayerAssignment")
}

impl Marshal for LayerAssignment {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(LayerAssignment {
            net_name: <String as Marshal>::from_python(py, &obj.getattr("net_name")?)?,
            // The pyclass stores `layer` UNCOERCED ("an int layer stays
            // int") — `Val` records int vs float and round-trips either.
            layer: <Val as Marshal>::from_python(py, &obj.getattr("layer")?)?,
            allow_layer_change: <bool as Marshal>::from_python(
                py,
                &obj.getattr("allow_layer_change")?,
            )?,
            is_plane: <bool as Marshal>::from_python(py, &obj.getattr("is_plane")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = layer_assignment_cls(py)?;
        let args = PyTuple::new(
            py,
            [
                self.net_name.as_str().into_py_any(py)?,
                self.layer.to_python(py)?,
                self.allow_layer_change.into_py_any(py)?,
                self.is_plane.into_py_any(py)?,
            ],
        )?;
        cls.call1(args).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U5: Placement + SlotPos + ZoneSlots — the tuple-shaped frozenset elements
// ---------------------------------------------------------------------------

impl Marshal for Placement {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "Placement", "expected a (ref, (x, y)) tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "Placement",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        Ok(Placement {
            ref_: <String as Marshal>::from_python(py, &t.get_item(0)?)
                .map_err(|e| type_err(obj, "Placement", &format!("ref: {e}")))?,
            position: <(f64, f64) as Marshal>::from_python(py, &t.get_item(1)?)
                .map_err(|e| type_err(obj, "Placement", &format!("position: {e}")))?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let items: [Py<PyAny>; 2] = [
            self.ref_.clone().into_py_any(py)?,
            self.position.to_python(py)?,
        ];
        Ok(PyTuple::new(py, items.iter().map(|o| o.bind(py)))?
            .into_any()
            .unbind())
    }
}

impl Marshal for SlotPos {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "SlotPos", "expected a (x, y) tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "SlotPos",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        let x = <f64 as Marshal>::from_python(py, &t.get_item(0)?)
            .map_err(|e| type_err(obj, "SlotPos", &format!("x coordinate: {e}")))?;
        let y = <f64 as Marshal>::from_python(py, &t.get_item(1)?)
            .map_err(|e| type_err(obj, "SlotPos", &format!("y coordinate: {e}")))?;
        Ok(SlotPos(x, y))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        Ok(PyTuple::new(py, [self.0, self.1])?
            .into_any()
            .unbind())
    }
}

impl Marshal for ZoneSlots {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let t = obj
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "ZoneSlots", "expected a (zone_name, slots) tuple"))?;
        if t.len() != 2 {
            return Err(type_err(
                obj,
                "ZoneSlots",
                &format!("expected a 2-tuple, got {} elements", t.len()),
            ));
        }
        let zone = <String as Marshal>::from_python(py, &t.get_item(0)?)
            .map_err(|e| type_err(obj, "ZoneSlots", &format!("zone name: {e}")))?;
        // The slots value is the per-zone TUPLE of slot tuples — an ordered
        // sequence, so a `Vec` preserves its order (never a set).
        let slots_any = t.get_item(1)?;
        let slots_t = slots_any
            .cast::<PyTuple>()
            .map_err(|_| type_err(obj, "ZoneSlots", "expected the slots as a tuple"))?;
        let mut slots = Vec::with_capacity(slots_t.len());
        for item in slots_t.iter() {
            slots.push(SlotPos::from_python(py, &item)?);
        }
        Ok(ZoneSlots { zone, slots })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        // The slots are a TUPLE (the element's second half is the per-zone
        // `tuple(slots)` the stage writes) — NOT a `Vec`-marshalled list
        // (a list would make the frozenset element unhashable and change
        // the kind).
        let slot_objs: Vec<Py<PyAny>> = self
            .slots
            .iter()
            .map(|s| s.to_python(py))
            .collect::<PyResult<_>>()?;
        let slots = PyTuple::new(py, slot_objs.iter().map(|o| o.bind(py)))?
            .into_any()
            .unbind();
        let items: [Py<PyAny>; 2] = [self.zone.clone().into_py_any(py)?, slots];
        Ok(PyTuple::new(py, items.iter().map(|o| o.bind(py)))?
            .into_any()
            .unbind())
    }
}

// ---------------------------------------------------------------------------
// U5: the violation dataclasses — Violation / ConnectivityViolation /
// PlacementViolation (the three tuple-list element types)
// ---------------------------------------------------------------------------

/// The `Point` class at `temper_placer.router_v6.constraints_geometry`
/// (re-export of the design-bundle `geometry_contracts.Point`), resolved at
/// call time.
fn point_cls<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    py.import("temper_placer.router_v6.constraints_geometry")?
        .getattr("Point")
}

/// A `Point` object's `(x, y)` — strict `f64` (the oracle builds points
/// from kernel float coordinates; an int-shaped point is a loud error).
fn point_from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<(f64, f64)> {
    let x = <f64 as Marshal>::from_python(py, &obj.getattr("x")?)?;
    let y = <f64 as Marshal>::from_python(py, &obj.getattr("y")?)?;
    Ok((x, y))
}

fn point_to_python(py: Python<'_>, loc: &(f64, f64)) -> PyResult<Py<PyAny>> {
    let cls = point_cls(py)?;
    cls.call1((loc.0, loc.1)).map(Bound::unbind)
}

impl Marshal for Violation {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Violation {
            type_: <String as Marshal>::from_python(py, &obj.getattr("type")?)?,
            geometry_a_id: <String as Marshal>::from_python(py, &obj.getattr("geometry_a_id")?)?,
            geometry_b_id: <String as Marshal>::from_python(py, &obj.getattr("geometry_b_id")?)?,
            net_a: <String as Marshal>::from_python(py, &obj.getattr("net_a")?)?,
            net_b: <String as Marshal>::from_python(py, &obj.getattr("net_b")?)?,
            clearance_actual: <f64 as Marshal>::from_python(py, &obj.getattr("clearance_actual")?)?,
            clearance_required: <f64 as Marshal>::from_python(
                py,
                &obj.getattr("clearance_required")?,
            )?,
            location: point_from_python(py, &obj.getattr("location")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = py
            .import("temper_placer.router_v6.constraints_drc_oracle")?
            .getattr("Violation")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("type", self.type_.as_str())?;
        kwargs.set_item("geometry_a_id", self.geometry_a_id.as_str())?;
        kwargs.set_item("geometry_b_id", self.geometry_b_id.as_str())?;
        kwargs.set_item("net_a", self.net_a.as_str())?;
        kwargs.set_item("net_b", self.net_b.as_str())?;
        kwargs.set_item("clearance_actual", self.clearance_actual)?;
        kwargs.set_item("clearance_required", self.clearance_required)?;
        kwargs.set_item("location", point_to_python(py, &self.location)?)?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

impl Marshal for ConnectivityViolation {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ConnectivityViolation {
            type_: <String as Marshal>::from_python(py, &obj.getattr("type")?)?,
            net: <String as Marshal>::from_python(py, &obj.getattr("net")?)?,
            location: point_from_python(py, &obj.getattr("location")?)?,
            description: <String as Marshal>::from_python(py, &obj.getattr("description")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = py
            .import("temper_placer.deterministic.stages.connectivity_validation")?
            .getattr("ConnectivityViolation")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("type", self.type_.as_str())?;
        kwargs.set_item("net", self.net.as_str())?;
        kwargs.set_item("location", point_to_python(py, &self.location)?)?;
        kwargs.set_item("description", self.description.as_str())?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

impl Marshal for PlacementViolation {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(PlacementViolation {
            constraint_name: <String as Marshal>::from_python(py, &obj.getattr("constraint_name")?)?,
            violation_type: <String as Marshal>::from_python(py, &obj.getattr("violation_type")?)?,
            message: <String as Marshal>::from_python(py, &obj.getattr("message")?)?,
            severity: <String as Marshal>::from_python(py, &obj.getattr("severity")?)?,
            component_a: <Option<String> as Marshal>::from_python(py, &obj.getattr("component_a")?)?,
            component_b: <Option<String> as Marshal>::from_python(py, &obj.getattr("component_b")?)?,
            actual_distance_mm: <Option<f64> as Marshal>::from_python(
                py,
                &obj.getattr("actual_distance_mm")?,
            )?,
            required_distance_mm: <Option<f64> as Marshal>::from_python(
                py,
                &obj.getattr("required_distance_mm")?,
            )?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let cls = py
            .import("temper_placer.deterministic.stages.placement_validation")?
            .getattr("PlacementViolation")?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("constraint_name", self.constraint_name.as_str())?;
        kwargs.set_item("violation_type", self.violation_type.as_str())?;
        kwargs.set_item("message", self.message.as_str())?;
        kwargs.set_item("severity", self.severity.as_str())?;
        kwargs.set_item("component_a", self.component_a.to_python(py)?)?;
        kwargs.set_item("component_b", self.component_b.to_python(py)?)?;
        kwargs.set_item("actual_distance_mm", self.actual_distance_mm.to_python(py)?)?;
        kwargs.set_item("required_distance_mm", self.required_distance_mm.to_python(py)?)?;
        cls.call((), Some(&kwargs)).map(Bound::unbind)
    }
}

// ---------------------------------------------------------------------------
// U5: the violations field — the PreflightReport dict (OwnedPlain leaves)
// ---------------------------------------------------------------------------

#[allow(clippy::only_used_in_recursion)] // `py` threads through the nested
// list/dict recursion (the base scalar arms need no interpreter handle) — a
// genuine use, mirroring `Plain::from_python`'s helper-threaded recursion.
impl Marshal for OwnedPlain {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        if obj.is_none() {
            return Ok(OwnedPlain::Null);
        }
        // Order matters: bool before int (bool is an int subclass).
        if obj.is_instance_of::<pyo3::types::PyBool>() {
            return Ok(OwnedPlain::Bool(obj.extract::<bool>()?));
        }
        if obj.is_instance_of::<pyo3::types::PyInt>() {
            let i: i64 = obj
                .extract()
                .map_err(|e| type_err(obj, "plain value", &format!("int out of i64 range: {e}")))?;
            return Ok(OwnedPlain::Int(i));
        }
        if obj.is_instance_of::<pyo3::types::PyFloat>() {
            return Ok(OwnedPlain::Float(obj.extract::<f64>()?));
        }
        if obj.is_instance_of::<pyo3::types::PyString>() {
            return Ok(OwnedPlain::Str(obj.extract::<String>()?));
        }
        if let Ok(l) = obj.cast::<pyo3::types::PyList>() {
            let mut items = Vec::with_capacity(l.len());
            for item in l.iter() {
                items.push(OwnedPlain::from_python(py, &item)?);
            }
            return Ok(OwnedPlain::List(items));
        }
        if let Ok(d) = obj.cast::<PyDict>() {
            let mut items = Vec::with_capacity(d.len());
            for (k, v) in d.iter() {
                let key = k
                    .extract::<String>()
                    .map_err(|_| type_err(&k, "plain dict", "expected a str key"))?;
                items.push((key, OwnedPlain::from_python(py, &v)?));
            }
            return Ok(OwnedPlain::Dict(items));
        }
        Err(type_err(
            obj,
            "plain value",
            "expected None/bool/int/float/str/list/dict (the PreflightReport details shapes)",
        ))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self {
            OwnedPlain::Null => Ok(py.None()),
            OwnedPlain::Bool(b) => (*b).into_py_any(py),
            OwnedPlain::Int(i) => (*i).into_py_any(py),
            OwnedPlain::Float(f) => (*f).into_py_any(py),
            OwnedPlain::Str(s) => s.clone().into_py_any(py),
            OwnedPlain::List(items) => {
                let list = pyo3::types::PyList::empty(py);
                for item in items {
                    list.append(item.to_python(py)?.bind(py))?;
                }
                Ok(list.into_any().unbind())
            }
            OwnedPlain::Dict(items) => {
                let d = PyDict::new(py);
                for (k, v) in items {
                    d.set_item(k, v.to_python(py)?.bind(py))?;
                }
                Ok(d.into_any().unbind())
            }
        }
    }
}

impl Marshal for PreflightCheck {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        // Each check is a DICT (the `check_dict` shape the stage writes),
        // so its fields are read with get_item (dict keys), not getattr.
        Ok(PreflightCheck {
            name: <String as Marshal>::from_python(py, &obj.get_item("name")?)?,
            result: <String as Marshal>::from_python(py, &obj.get_item("result")?)?,
            message: <String as Marshal>::from_python(py, &obj.get_item("message")?)?,
            details: match obj.get_item("details")? {
                d if d.is_none() => None,
                d => Some(OwnedPlain::from_python(py, &d)?),
            },
            time_ms: <f64 as Marshal>::from_python(py, &obj.get_item("time_ms")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let d = PyDict::new(py);
        d.set_item("name", self.name.as_str())?;
        d.set_item("result", self.result.as_str())?;
        d.set_item("message", self.message.as_str())?;
        d.set_item("details", self.details.to_python(py)?)?;
        d.set_item("time_ms", self.time_ms)?;
        Ok(d.into_any().unbind())
    }
}

impl Marshal for PreflightReport {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(PreflightReport {
            checks: <Vec<PreflightCheck> as Marshal>::from_python(py, &obj.get_item("checks")?)?,
            overall: <String as Marshal>::from_python(py, &obj.get_item("overall")?)?,
            total_time_ms: <f64 as Marshal>::from_python(py, &obj.get_item("total_time_ms")?)?,
        })
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let d = PyDict::new(py);
        d.set_item("checks", self.checks.to_python(py)?)?;
        d.set_item("overall", self.overall.as_str())?;
        d.set_item("total_time_ms", self.total_time_ms)?;
        Ok(d.into_any().unbind())
    }
}

// ---------------------------------------------------------------------------
// U5: the owned collection FIELD types — the *Set frozenset newtypes + the
// *List tuple newtypes
// ---------------------------------------------------------------------------

impl Marshal for ZoneSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ZoneSet(frozenset_read::<Zone>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for StrPairSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(StrPairSet(frozenset_read::<(String, String)>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for ZoneSlotsSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ZoneSlotsSet(frozenset_read::<ZoneSlots>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for LayerAssignmentSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(LayerAssignmentSet(frozenset_read::<LayerAssignment>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for RouteSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(RouteSet(frozenset_read::<Route>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for ViaSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ViaSet(frozenset_read::<Via>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for PlacementSet {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(PlacementSet(frozenset_read::<Placement>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        frozenset_write(py, &self.0)
    }
}

impl Marshal for ViolationList {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ViolationList(tuple_list_read::<Violation>(py, obj)?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        tuple_list_write(py, &self.0)
    }
}

impl Marshal for ConnectivityViolationList {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(ConnectivityViolationList(tuple_list_read::<ConnectivityViolation>(
            py, obj,
        )?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        tuple_list_write(py, &self.0)
    }
}

impl Marshal for PlacementViolationList {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(PlacementViolationList(tuple_list_read::<PlacementViolation>(
            py, obj,
        )?))
    }
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        tuple_list_write(py, &self.0)
    }
}

// ---------------------------------------------------------------------------
// Tests — the U2 leaf round-trip losslessness proof
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use crate::marshal::{assert_roundtrip_with, to_owned, to_python};

    /// Faithful `@dataclass` stand-ins for the design-bundle pyclasses, in the
    /// oracle's exact field order (`tests/core/_netlist_py_oracle.py` and
    /// `tests/core/_board_py_oracle.py`). A dataclass reproduces the pyclass
    /// `__repr__`/`__eq__` bit-for-bit (both assemble the field list and
    /// delegate `repr`/`==` to CPython's), so the round-trip gate's
    /// type/repr/eq checks are meaningful without building the real `.so`
    /// (which `cargo test` here does not). The `Board` stand-in mirrors the
    /// oracle's `__post_init__` (default 4-layer stackup fill + `_zone_map`
    /// build) so constructor-normalised fields round-trip identically.
    const STANDIN: &str = r#"
from dataclasses import dataclass, field

@dataclass
class Pin:
    name: str
    number: str
    position: tuple
    net: object = None
    width: float = 1.0
    height: float = 1.0
    shape: str = "rect"
    layer: str = "F.Cu"
    drill: float = 0.0
    is_pth: bool = False
    roundrect_ratio: float = 0.25
    pad_rotation_deg: float = 0.0

@dataclass
class Component:
    ref: str
    footprint: str
    bounds: tuple
    pins: list = field(default_factory=list)
    net_class: str = "Signal"
    zone: object = None
    fixed: bool = False
    initial_position: object = None
    initial_rotation: object = None
    initial_side: object = None
    attributes: dict = field(default_factory=dict)
    tags: object = field(default_factory=frozenset)
    sheetpath: object = None

@dataclass
class Net:
    name: str
    pins: list
    net_class: str = "Signal"
    weight: float = 1.0
    max_current: float = 0.0
    voltage_class: str = "LV"

@dataclass
class Netlist:
    components: list = field(default_factory=list)
    nets: list = field(default_factory=list)
    _component_index: dict = field(default_factory=dict, repr=False)
    _net_index: dict = field(default_factory=dict, repr=False)
    _component_nets: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self.build_indices()

    def build_indices(self):
        self._component_index = {c.ref: i for i, c in enumerate(self.components)}
        self._net_index = {n.name: i for i, n in enumerate(self.nets)}
        self._component_nets = {c.ref: [] for c in self.components}
        for net in self.nets:
            for ref, _ in net.pins:
                if ref in self._component_nets:
                    self._component_nets[ref].append(net.name)

@dataclass
class Layer:
    name: str
    layer_type: str
    copper_weight: float = 1.0
    is_routable: bool = True

@dataclass
class LayerStackup:
    layers: tuple = ()
    thickness: float = 1.6

    @classmethod
    def default_4layer(cls):
        return cls(
            (Layer("F.Cu", "signal"), Layer("In1.Cu", "plane"),
             Layer("In2.Cu", "plane"), Layer("B.Cu", "signal"))
        )

@dataclass
class MountingHole:
    position: tuple
    diameter: float
    keepout_radius: float = 3.0

@dataclass
class Zone:
    name: str
    bounds: object
    net_classes: list = field(default_factory=lambda: ["Signal"])
    components: list = field(default_factory=list)
    weight: float = 1.0
    polygon: object = None
    layers: list = field(default_factory=lambda: ["F.Cu"])
    max_size: object = None
    can_expand: list = field(default_factory=lambda: ["up", "down", "left", "right"])
    zone_type: str = "placement"

@dataclass
class GroundDomain:
    name: str
    bounds: tuple
    star_point: object = None

@dataclass
class Board:
    width: object
    height: object
    origin: tuple = (0.0, 0.0)
    zones: list = field(default_factory=list)
    mounting_holes: list = field(default_factory=list)
    keepouts: list = field(default_factory=list)
    ground_domains: list = field(default_factory=list)
    layer_stackup: object = None
    outline_polygon: object = None
    _zone_map: dict = field(init=False, default_factory=dict)

    def __post_init__(self):
        if not self.layer_stackup:
            self.layer_stackup = LayerStackup.default_4layer()
        self._zone_map = {z.name: z for z in self.zones}

# --- U4: the ClearanceGrid / DRCOracle stand-ins --------------------------
# The numpy int32 cell arrays are KEPT opaque (identity passthrough) — a
# duck-typed stand-in stands in for the ndarray so the embedded interpreter
# needs no numpy. Its `dtype` field records the (constant) int32 dtype the
# identity keep preserves.

class _FakeInt32Array:
    def __init__(self, rows, cols, dtype='int32'):
        self.rows = rows
        self.cols = cols
        self.dtype = dtype

    def __repr__(self):
        return f"_FakeInt32Array(dtype={self.dtype!r}, shape=({self.rows}, {self.cols}))"

@dataclass
class ClearanceGrid:
    width_mm: object
    height_mm: object
    cell_size_mm: object
    layer_count: int = 2

    def __post_init__(self):
        self.cols = int(self.width_mm / self.cell_size_mm)
        self.rows = int(self.height_mm / self.cell_size_mm)
        self._trace_net_ids = [_FakeInt32Array(self.rows, self.cols) for _ in range(self.layer_count)]
        self._pad_net_ids = [_FakeInt32Array(self.rows, self.cols) for _ in range(self.layer_count)]
        self._net_to_id = {}
        self._id_to_net = {}
        self._next_net_id = 1
        self._occupancy_grid_cache = None
        self._bitmap_cache = None
        self._bitmap_stride_cache = None

@dataclass
class RoutingZone:
    name: str
    polygon: list
    clearance_mm: float
    allowed_net_classes: set
    layer_restrictions: object = None

class ZoneManager:
    def __init__(self, zones):
        self.zones = zones

@dataclass
class NetClassRules:
    name: str = ""
    trace_width: float = 0.2
    clearance: float = 0.2
    safety_category: object = None

    def __repr__(self):
        return f"NetClassRules(name={self.name!r})"

@dataclass
class ClearanceMatrix:
    _clearances: dict = field(default_factory=dict)
    default_clearance: float = 0.2
    default_track_width: float = 0.2
    default_via_diameter: float = 0.6
    default_via_drill: float = 0.3
    _net_class_rules: dict = field(default_factory=dict)
    _net_to_class: dict = field(default_factory=dict)
    zone_manager: object = None
    _differential_pairs: dict = field(default_factory=dict)

class PCBGeometry:
    def __init__(self):
        self.tracks = []
        self.pads = []
        self.vias = []

@dataclass
class DRCOracle:
    rules: object
    geometry: object = field(default_factory=PCBGeometry)
    _search_multiplier: float = 3.0
    enable_internal_layer_creepage: bool = True
    clearance_credits: dict = field(default_factory=dict)
    pin_owner: object = field(default_factory=dict)

# --- U5: the collection-element stand-ins ------------------------------
# The zone-geometry `Zone` (2-field frozen dataclass) lives in a SEPARATE
# namespace: the board_contracts `Zone` stand-in above already owns the
# globals name `Zone`, and the two classes are genuinely different (11 vs 2
# fields). The U5 round-trip tests eval against this `_u5` dict, so every
# class here is reachable under its REAL name. The field orders/defaults
# mirror the Python classes the stage writes bit-for-bit (the frozen
# dataclasses' `__repr__`/`__eq__`/`__hash__` are exactly the pyclass
# surfaces the gate compares).
_u5 = {}
exec('''
from dataclasses import dataclass

@dataclass(frozen=True)
class Zone:
    name: str
    bounds: object

@dataclass(frozen=True)
class Trace:
    start: object
    end: object
    width: object
    layer: object
    net: object = None

@dataclass(frozen=True)
class Via:
    position: object
    drill: object
    width: object
    layers: object = ("F.Cu", "B.Cu")
    net: object = None
    is_diff_pair: object = False

@dataclass(frozen=True)
class LayerAssignment:
    net_name: str
    layer: object
    allow_layer_change: object = True
    is_plane: object = False

@dataclass(frozen=True)
class Point:
    x: object
    y: object

@dataclass
class Violation:
    type: str
    geometry_a_id: str
    geometry_b_id: str
    net_a: str
    net_b: str
    clearance_actual: float
    clearance_required: float
    location: object

@dataclass
class ConnectivityViolation:
    type: str
    net: str
    location: object
    description: str

@dataclass
class PlacementViolation:
    constraint_name: str
    violation_type: str
    message: str
    severity: str
    component_a: object = None
    component_b: object = None
    actual_distance_mm: object = None
    required_distance_mm: object = None
''', _u5)
"#;

    /// The module's tests are serialized by this lock, taken BEFORE any
    /// Python (before `Python::initialize()`/`Python::attach`): each `setup()`
    /// call registers the stand-in classes into the PROCESS-GLOBAL
    /// `sys.modules`, and the round-trip gate's type check compares an
    /// eval-vs-import class identity (`orig.get_type().is(back.get_type())`).
    /// Concurrent test threads can interleave closures (the pyo3 GIL pool's
    /// already-attached fast path runs a previously-attached thread's closure
    /// without re-acquiring the GIL), so two concurrent `setup()`s would
    /// clobber `sys.modules` with DIFFERENT stand-in class objects and a test
    /// whose eval saw one set and whose `to_python` import saw the other
    /// would fail with a type mismatch whose reprs are identical. The lock
    /// makes the registrations sequential AND must be taken before attach:
    /// a lock taken inside a closure deadlocks when the closure's thread is
    /// on the GIL-pool fast path (it waits for the real GIL — held by the
    /// thread blocked on this lock — an ABBA cycle). `setup()` additionally
    /// REUSES an existing registration so every test's globals and the
    /// runtime-import path resolve the same class objects.
    static NETLIST_TESTS_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// Define the stand-in dataclasses in a globals dict and register them in
    /// `sys.modules` under the path the `to_python` runtime import looks up
    /// (`temper_design_bundle_python.netlist_contracts` and
    /// `...board_contracts`), exactly the mock pattern the d3–d7 stage
    /// runners use for their call-backs.
    fn setup<'py>(py: Python<'py>) -> Bound<'py, PyDict> {
        let globals = PyDict::new(py);
        // Reuse a registration a previous test already made: the classes
        // must be THE SAME objects the runtime-import path will resolve.
        // The U5 collection-element classes are part of the registration
        // set: a previous test's stand-in path registered them all, so if
        // any is missing the reuse branch falls through to (re)register.
        if let Ok(tdb) = py.import("temper_design_bundle_python")
            && let Ok(nc) = tdb.getattr("netlist_contracts")
            && let Ok(bc) = tdb.getattr("board_contracts")
            && let Ok(layer_assignment) = tdb.getattr("LayerAssignment")
            && let Ok(trace) = bc.getattr("Trace")
            && let Ok(via) = bc.getattr("Via")
            && let Ok(zg) = py.import("temper_placer.deterministic.stages.zone_geometry")
            && let Ok(zone) = zg.getattr("Zone")
            && let Ok(cv_mod) = py.import("temper_placer.deterministic.stages.connectivity_validation")
            && let Ok(connectivity_violation) = cv_mod.getattr("ConnectivityViolation")
            && let Ok(pv_mod) = py.import("temper_placer.deterministic.stages.placement_validation")
            && let Ok(placement_violation) = pv_mod.getattr("PlacementViolation")
            && let Ok(cg) = py.import("temper_placer.router_v6.constraints_geometry")
            && let Ok(point) = cg.getattr("Point")
            && let Ok(cdo_u5) = py.import("temper_placer.router_v6.constraints_drc_oracle")
            && let Ok(violation) = cdo_u5.getattr("Violation")
        {
            for name in ["Pin", "Component", "Net", "Netlist"] {
                globals.set_item(name, nc.getattr(name).expect("nc class")).expect("set nc class");
            }
            for name in ["Layer", "LayerStackup", "MountingHole", "Zone", "GroundDomain", "Board"] {
                globals.set_item(name, bc.getattr(name).expect("bc class")).expect("set bc class");
            }
            // U4: reuse the temper_placer registrations a previous test made.
            if let Ok(grid_core) = py.import("temper_placer.deterministic.stages._grid_core")
                && let Ok(cdr) = py.import("temper_placer.router_v6.constraints_design_rules")
                && let Ok(cdo) = py.import("temper_placer.router_v6.constraints_drc_oracle")
            {
                for (name, src) in [
                    ("ClearanceGrid", grid_core.getattr("ClearanceGrid").expect("ClearanceGrid class")),
                    ("ClearanceMatrix", cdr.getattr("ClearanceMatrix").expect("ClearanceMatrix class")),
                    ("RoutingZone", cdr.getattr("RoutingZone").expect("RoutingZone class")),
                    ("ZoneManager", cdr.getattr("ZoneManager").expect("ZoneManager class")),
                    ("NetClassRules", cdr.getattr("NetClassRules").expect("NetClassRules class")),
                    ("PCBGeometry", cdo.getattr("PCBGeometry").expect("PCBGeometry class")),
                    ("DRCOracle", cdo.getattr("DRCOracle").expect("DRCOracle class")),
                ] {
                    globals.set_item(name, src).expect("set u4 class");
                }
            }
            // U5: the collection-element classes, in the `_u5` namespace the
            // U5 round-trip tests eval against (their REAL names — the
            // zone-geometry `Zone` never collides with the board `Zone`).
            let u5 = PyDict::new(py);
            for (name, src) in [
                ("Zone", zone),
                ("Trace", trace),
                ("Via", via),
                ("LayerAssignment", layer_assignment),
                ("Point", point),
                ("Violation", violation),
                ("ConnectivityViolation", connectivity_violation),
                ("PlacementViolation", placement_violation),
            ] {
                u5.set_item(name, src).expect("set u5 class");
            }
            globals.set_item("_u5", &u5).expect("set _u5");
            return globals;
        }
        let standin = std::ffi::CString::new(STANDIN).expect("STANDIN has no NUL");
        py.run(standin.as_c_str(), Some(&globals), None)
            .expect("stand-in classes");
        let sys = py.import("sys").expect("sys");
        let modules = sys.getattr("modules").expect("sys.modules");
        let tdb = PyModule::new(py, "temper_design_bundle_python").expect("tdb");
        let nc = PyModule::new(py, "netlist_contracts").expect("netlist_contracts");
        nc.add("Pin", globals.get_item("Pin").expect("Pin"))
            .expect("register Pin");
        nc.add("Component", globals.get_item("Component").expect("Component"))
            .expect("register Component");
        nc.add("Net", globals.get_item("Net").expect("Net"))
            .expect("register Net");
        nc.add("Netlist", globals.get_item("Netlist").expect("Netlist"))
            .expect("register Netlist");
        tdb.add("netlist_contracts", &nc).expect("tdb.netlist_contracts");
        let bc = PyModule::new(py, "board_contracts").expect("board_contracts");
        for name in ["Layer", "LayerStackup", "MountingHole", "Zone", "GroundDomain", "Board"] {
            bc.add(name, globals.get_item(name).unwrap_or_else(|_| panic!("{name}")))
                .unwrap_or_else(|e| panic!("register {name}: {e}"));
        }
        // U5: the collection-element classes (from the `_u5` namespace the
        // STANDIN defined — the zone-geometry `Zone` lives there under its
        // REAL name, separate from the board `Zone` above).
        let u5 = globals
            .get_item("_u5")
            .expect("_u5")
            .expect("_u5 present");
        for name in ["Trace", "Via"] {
            bc.add(name, u5.get_item(name).unwrap_or_else(|_| panic!("u5 {name}")))
                .unwrap_or_else(|e| panic!("register {name}: {e}"));
        }
        tdb.add("board_contracts", &bc).expect("tdb.board_contracts");
        tdb.add("LayerAssignment", u5.get_item("LayerAssignment").expect("u5 LayerAssignment"))
            .expect("register LayerAssignment");
        modules
            .set_item("temper_design_bundle_python", &tdb)
            .expect("sys.modules tdb");
        modules
            .set_item("temper_design_bundle_python.netlist_contracts", &nc)
            .expect("sys.modules tdb.netlist_contracts");
        modules
            .set_item("temper_design_bundle_python.board_contracts", &bc)
            .expect("sys.modules tdb.board_contracts");
        // U4: temper_placer.deterministic.stages._grid_core (ClearanceGrid) and
        // temper_placer.router_v6.{constraints_design_rules,constraints_drc_oracle}
        // (ClearanceMatrix / RoutingZone / ZoneManager / NetClassRules /
        // PCBGeometry / DRCOracle). Every dotted prefix is registered in
        // sys.modules so `py.import(...)` of the leaf resolves without a
        // filesystem search (the D3 runner's fake-module pattern).
        let pkg = PyModule::new(py, "temper_placer").expect("temper_placer");
        let det = PyModule::new(py, "deterministic").expect("deterministic");
        let stages = PyModule::new(py, "stages").expect("stages");
        let grid_core = PyModule::new(py, "_grid_core").expect("_grid_core");
        grid_core
            .add("ClearanceGrid", globals.get_item("ClearanceGrid").expect("ClearanceGrid"))
            .expect("register ClearanceGrid");
        stages.add("_grid_core", &grid_core).expect("stages._grid_core");
        det.add("stages", &stages).expect("det.stages");
        pkg.add("deterministic", &det).expect("pkg.deterministic");
        let rv6 = PyModule::new(py, "router_v6").expect("router_v6");
        let cdr = PyModule::new(py, "constraints_design_rules").expect("constraints_design_rules");
        for name in ["ClearanceMatrix", "RoutingZone", "ZoneManager", "NetClassRules"] {
            cdr.add(name, globals.get_item(name).unwrap_or_else(|_| panic!("{name}")))
                .unwrap_or_else(|e| panic!("register {name}: {e}"));
        }
        let cdo = PyModule::new(py, "constraints_drc_oracle").expect("constraints_drc_oracle");
        for name in ["PCBGeometry", "DRCOracle"] {
            cdo.add(name, globals.get_item(name).unwrap_or_else(|_| panic!("{name}")))
                .unwrap_or_else(|e| panic!("register {name}: {e}"));
        }
        cdo.add("Violation", u5.get_item("Violation").expect("u5 Violation"))
            .expect("register Violation");
        rv6.add("constraints_design_rules", &cdr).expect("rv6.constraints_design_rules");
        rv6.add("constraints_drc_oracle", &cdo).expect("rv6.constraints_drc_oracle");
        pkg.add("router_v6", &rv6).expect("pkg.router_v6");
        // U5: the remaining collection-element module paths — the stage
        // violation dataclasses + the zone-geometry Zone + the router_v6
        // Point. Every dotted prefix is registered in sys.modules so the
        // runtime class lookup resolves without a filesystem search.
        let zone_geometry = PyModule::new(py, "zone_geometry").expect("zone_geometry");
        zone_geometry
            .add("Zone", u5.get_item("Zone").expect("u5 Zone"))
            .expect("register zone_geometry.Zone");
        stages.add("zone_geometry", &zone_geometry).expect("stages.zone_geometry");
        let connectivity_validation = PyModule::new(py, "connectivity_validation")
            .expect("connectivity_validation");
        connectivity_validation
            .add("ConnectivityViolation", u5.get_item("ConnectivityViolation").expect("u5 ConnectivityViolation"))
            .expect("register connectivity_validation.ConnectivityViolation");
        stages.add("connectivity_validation", &connectivity_validation)
            .expect("stages.connectivity_validation");
        let placement_validation = PyModule::new(py, "placement_validation")
            .expect("placement_validation");
        placement_validation
            .add("PlacementViolation", u5.get_item("PlacementViolation").expect("u5 PlacementViolation"))
            .expect("register placement_validation.PlacementViolation");
        stages.add("placement_validation", &placement_validation)
            .expect("stages.placement_validation");
        let constraints_geometry = PyModule::new(py, "constraints_geometry")
            .expect("constraints_geometry");
        constraints_geometry
            .add("Point", u5.get_item("Point").expect("u5 Point"))
            .expect("register constraints_geometry.Point");
        rv6.add("constraints_geometry", &constraints_geometry)
            .expect("rv6.constraints_geometry");
        for (path, module) in [
            ("temper_placer", &pkg),
            ("temper_placer.deterministic", &det),
            ("temper_placer.deterministic.stages", &stages),
            ("temper_placer.deterministic.stages._grid_core", &grid_core),
            ("temper_placer.deterministic.stages.zone_geometry", &zone_geometry),
            ("temper_placer.deterministic.stages.connectivity_validation", &connectivity_validation),
            ("temper_placer.deterministic.stages.placement_validation", &placement_validation),
            ("temper_placer.router_v6", &rv6),
            ("temper_placer.router_v6.constraints_design_rules", &cdr),
            ("temper_placer.router_v6.constraints_drc_oracle", &cdo),
            ("temper_placer.router_v6.constraints_geometry", &constraints_geometry),
        ] {
            modules.set_item(path, module).expect("sys.modules u4/u5");
        }
        globals.set_item("_u5", &u5).expect("set _u5");
        globals
    }

    #[test]
    fn component_int_vs_float_bounds_roundtrip_type_preserving() {
        // The netlist_contracts hazard: `Component("R1", "fp", (1, 2))` keeps
        // `int` bounds; `(1.0, 2.0)` keeps `float` bounds. Both round-trip
        // bit-identically — `1` must NOT widen to `1.0`.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Component>(py, "Component('R1', 'fp', (1, 2))", Some(&g));
            assert_roundtrip_with::<Component>(py, "Component('R1', 'fp', (1.0, 2.0))", Some(&g));
            // Explicitly: the owned bounds preserved int vs float.
            let owned = to_owned::<Component>(&eval_expr(py, &g, "Component('R1', 'fp', (1, 2))"))
                .unwrap();
            assert_eq!(owned.bounds, vec![Val::Int(1), Val::Int(2)]);
            let owned =
                to_owned::<Component>(&eval_expr(py, &g, "Component('R1', 'fp', (1.0, 2.0))"))
                    .unwrap();
            assert_eq!(owned.bounds, vec![Val::Float(1.0), Val::Float(2.0)]);
        });
    }

    /// Evaluate `expr` against the stand-in globals dict.
    fn eval_expr<'py>(
        py: Python<'py>,
        globals: &Bound<'py, PyDict>,
        expr: &str,
    ) -> Bound<'py, PyAny> {
        let cstr = std::ffi::CString::new(expr).expect("expr has no NUL");
        py.eval(cstr.as_c_str(), Some(globals), None)
            .expect("eval failed")
    }

    #[test]
    fn component_with_pins_and_all_fields_roundtrips_losslessly() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Component>(
                py,
                "Component('U1', 'QFN-56', (7.5, 7.5), [Pin('1', '1', (-3.5, 0.0), net='VCC'), \
                 Pin('2', '2', (3.5, 0.0))], net_class='HighVoltage', zone='power', fixed=True, \
                 initial_position=(10.0, 20.0), initial_rotation=1, initial_side=0, \
                 attributes={'value': '100nF'}, tags=frozenset({'power'}), sheetpath='hb.power_loop.q_high')",
                Some(&g),
            );
            // NOTE (U3 drive-by, R22-aligned): `tags` is a SINGLE-element
            // frozenset here — the recorded U2 bound ("The gate pins full
            // bit-identity on empty/single-element tags") guarantees its
            // iteration order is seed-independent. The previous multi-element
            // `{'power', 'top'}` could collide under a hash draw and rebuild
            // in a different order — the exact non-guaranteed case the bound
            // records — making this gate flaky on origin/main (~13%).
        });
    }

    #[test]
    fn component_defaults_roundtrip_losslessly() {
        // Only ref/footprint/bounds are given; the rest fall to dataclass
        // defaults and must come back exactly (empty list/dict/frozenset,
        // `None` for the optionals).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Component>(py, "Component('R1', 'fp', (1, 2))", Some(&g));
        });
    }

    #[test]
    fn pin_roundtrips_losslessly() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Pin>(
                py,
                "Pin('1', '1', (-3.5, 0.0), net='GND', width=0.5, height=0.5, shape='rect', \
                 layer='F.Cu', drill=0.3, is_pth=True, roundrect_ratio=0.25, pad_rotation_deg=90.0)",
                Some(&g),
            );
            assert_roundtrip_with::<Pin>(py, "Pin('A', 'A', (0.0, 0.0))", Some(&g));
        });
    }

    #[test]
    fn net_roundtrips_losslessly() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Net>(
                py,
                "Net('GND', [('U1', '1'), ('R1', '2'), ('C1', '1')], net_class='Ground', \
                 weight=2.0, max_current=3.5, voltage_class='HV')",
                Some(&g),
            );
            assert_roundtrip_with::<Net>(py, "Net('NET-1', [])", Some(&g));
        });
    }

    #[test]
    fn nan_and_infinities_roundtrip_in_leaf_fields() {
        // A NaN/±inf inside a leaf struct's float field must come back as the
        // SAME value (type + repr preserved; field-level NaN survives). The
        // dataclass `__eq__` itself returns False for NaN fields (CPython
        // `nan != nan`), so equality is asserted on the marshalled field
        // rather than through `assert_roundtrip_with`'s `==` arm.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            for expr in [
                "Net('n', [], weight=float('nan'))",
                "Net('n', [], max_current=float('inf'))",
                "Net('n', [], weight=float('-inf'))",
            ] {
                let orig = eval_expr(py, &g, expr);
                let owned = to_owned::<Net>(&orig).expect("to_owned");
                let back = to_python::<Net>(py, &owned).expect("to_python").bind(py).clone();
                assert!(orig.get_type().is(back.get_type()), "type mismatch for {expr}");
                let rp = orig.repr().unwrap().extract::<String>().unwrap();
                let rb = back.repr().unwrap().extract::<String>().unwrap();
                assert_eq!(rp, rb, "repr mismatch for {expr}");
            }
            // Field-level: the NaN in `weight` is still a NaN float after the
            // round-trip (not widened, not mangled).
            let owned = to_owned::<Net>(&eval_expr(py, &g, "Net('n', [], weight=float('nan'))"))
                .unwrap();
            assert!(owned.weight.is_nan(), "weight NaN must survive the round-trip");
            // A NaN pin position round-trips with repr preserved and the
            // coordinate still NaN.
            let pin = to_owned::<Pin>(&eval_expr(py, &g, "Pin('1', '1', (float('nan'), 0.0))"))
                .unwrap();
            assert!(pin.position.0.is_nan(), "position NaN must survive the round-trip");
        });
    }

    #[test]
    fn leaf_structs_reject_the_wrong_container_and_sibling_types() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let err = |expr: &str| -> bool {
                to_owned::<Component>(&eval_expr(py, &g, expr)).is_err()
            };
            assert!(err("Component('R1', 'fp', [1, 2])"), "list bounds must be rejected");
            assert!(err("Component('R1', 'fp', ('1', 2))"), "str bounds leaf must be rejected");
            assert!(err("Component('R1', 'fp', (1, True))"), "bool bounds leaf must be rejected");
            assert!(err("Component('R1', 'fp', (1, 2), fixed=1)"), "int fixed must be rejected");
            assert!(err("Component('R1', 'fp', (1, 2), zone=3)"), "int zone must be rejected");
            // Position is always-float: an int coordinate is rejected, not widened.
            assert!(
                to_owned::<Pin>(&eval_expr(py, &g, "Pin('1', '1', (1, 2))")).is_err(),
                "int position must be rejected"
            );
        });
    }

    #[test]
    fn tuple_impls_roundtrip_losslessly() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip_with::<(f64, f64)>(py, "(1.5, -2.5)", None);
            // -0.0 round-trips as -0.0 (repr bit-identity); the NaN element
            // case is covered field-wise in the leaf NaN test above (a tuple
            // `(-0.0, nan)` compares `!=` to itself under CPython tuple `==`,
            // which the gate's bare-float NaN arm cannot see).
            assert_roundtrip_with::<(f64, f64)>(py, "(-0.0, 2.5)", None);
            assert_roundtrip_with::<(String, String)>(py, "('U1', '1')", None);
        });
    }

    // -----------------------------------------------------------------------
    // U3: the owned aggregates — Netlist + Board round-trip gate
    // -----------------------------------------------------------------------

    #[test]
    fn netlist_roundtrips_bit_identically() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            // The dataclass default (empty lists) round-trips; `__post_init__`
            // rebuilds the three index dicts identically on both sides.
            assert_roundtrip_with::<Netlist>(py, "Netlist()", Some(&g));
            // A full netlist with U2-leaf components/nets. The `==` arm covers
            // the DERIVED indices (`compare=True`, `repr=False`): they are
            // recomputed by `build_indices` on both the original and the
            // rebuilt object and must be equal.
            assert_roundtrip_with::<Netlist>(
                py,
                "Netlist(components=[Component('U1', 'QFN-56', (7.5, 7.5), \
                 [Pin('1', '1', (-3.5, 0.0), net='VCC')], net_class='HighVoltage', \
                 attributes={'value': '100nF'}), Component('R1', 'fp', (1, 2))], \
                 nets=[Net('GND', [('U1', '1')], net_class='Ground', weight=2.0, \
                 max_current=3.5, voltage_class='HV'), Net('NET-2', [('R1', '1')])])",
                Some(&g),
            );
            // The owned struct holds exactly the two lists — the indices are
            // derived, not stored.
            let owned = to_owned::<Netlist>(&eval_expr(py, &g, "Netlist()")).unwrap();
            assert!(owned.components.is_empty() && owned.nets.is_empty());
            let owned =
                to_owned::<Netlist>(&eval_expr(py, &g, "Netlist(components=[Component('R1', 'fp', (1, 2))])"))
                    .unwrap();
            assert_eq!(owned.components.len(), 1);
            assert_eq!(owned.components[0].bounds, vec![Val::Int(1), Val::Int(2)]);
        });
    }

    #[test]
    fn netlist_nan_and_leaf_int_vs_float_roundtrip_preserved() {
        // The aggregate carries U2 leaves unchanged: an int `bounds` leaf
        // inside a component stays int, and a NaN `weight` inside a net
        // survives with type + repr preserved (manual type/repr arm — the
        // dataclass `__eq__` returns False for NaN fields, the recorded U2
        // bound).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            for expr in [
                "Netlist(nets=[Net('n', [], weight=float('nan'))])",
                "Netlist(nets=[Net('n', [], max_current=float('inf'))])",
                "Netlist(components=[Component('R1', 'fp', (1.0, float('nan')))])",
            ] {
                let orig = eval_expr(py, &g, expr);
                let owned = to_owned::<Netlist>(&orig).expect("to_owned");
                let back = to_python::<Netlist>(py, &owned).expect("to_python").bind(py).clone();
                assert!(orig.get_type().is(back.get_type()), "type mismatch for {expr}");
                let rp = orig.repr().unwrap().extract::<String>().unwrap();
                let rb = back.repr().unwrap().extract::<String>().unwrap();
                assert_eq!(rp, rb, "repr mismatch for {expr}");
            }
            let owned =
                to_owned::<Netlist>(&eval_expr(py, &g, "Netlist(nets=[Net('n', [], weight=float('nan'))])"))
                    .unwrap();
            assert!(owned.nets[0].weight.is_nan(), "net weight NaN must survive");
            let owned = to_owned::<Netlist>(&eval_expr(
                py,
                &g,
                "Netlist(components=[Component('R1', 'fp', (1, 2))])",
            ))
            .unwrap();
            assert_eq!(owned.components[0].bounds, vec![Val::Int(1), Val::Int(2)]);
        });
    }

    #[test]
    fn board_roundtrips_bit_identically_with_keeps_by_identity() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            // The constructor-normalised default board: `__post_init__` fills
            // the 4-layer stackup and the empty `_zone_map` on BOTH sides, so
            // the repr/eq arms (which include `_zone_map`, `repr=True`) match.
            assert_roundtrip_with::<OwnedBoard>(py, "Board(100.0, 80.0)", Some(&g));
            // Float-shaped dims/origin.
            assert_roundtrip_with::<OwnedBoard>(
                py,
                "Board(100.0, 80.0, origin=(0.0, 0.0))",
                Some(&g),
            );
            // The FULL board: every field populated, the keep fields holding
            // foreign pyclass values and an explicit stackup + outline.
            assert_roundtrip_with::<OwnedBoard>(
                py,
                "Board(100.0, 150.0, origin=(0.0, 0.0), \
                 zones=[Zone('HV_ZONE', (0, 0, 50, 80))], \
                 mounting_holes=[MountingHole((5, 5), 3.2)], \
                 keepouts=[(0, 0, 50, 80)], \
                 ground_domains=[GroundDomain('PGND', (0, 0, 50, 150))], \
                 layer_stackup=LayerStackup.default_4layer(), \
                 outline_polygon=[(0, 0), (100, 0), (100, 150), (0, 150)])",
                Some(&g),
            );
            // Keeps round-trip BY IDENTITY: the rebuilt board's keep fields ARE
            // the original objects (Plain::Opaque passthrough — never
            // reconstructed, never copied).
            let orig = eval_expr(
                py,
                &g,
                "Board(100.0, 80.0, zones=[Zone('HV_ZONE', (0, 0, 50, 80))], \
                 mounting_holes=[MountingHole((5, 5), 3.2)], \
                 ground_domains=[GroundDomain('PGND', (0, 0, 50, 150))], \
                 layer_stackup=LayerStackup.default_4layer(), \
                 outline_polygon=[(0, 0), (100, 0), (100, 150)])",
            );
            let owned = to_owned::<OwnedBoard>(&orig).unwrap();
            let back = to_python::<OwnedBoard>(py, &owned).unwrap().bind(py).clone();
            for attr in [
                "zones",
                "mounting_holes",
                "ground_domains",
                "layer_stackup",
                "outline_polygon",
            ] {
                let a = orig.getattr(attr).unwrap();
                let b = back.getattr(attr).unwrap();
                assert!(a.is(&b), "{attr} must pass through by identity");
            }
            // `_zone_map` is derived: rebuilt from the same zone objects by the
            // constructor, so it is value-equal (and repr-identical).
            let zm_orig = orig.getattr("_zone_map").unwrap();
            let zm_back = back.getattr("_zone_map").unwrap();
            assert!(
                zm_orig.eq(&zm_back).unwrap(),
                "_zone_map must be recomputed identically"
            );
        });
    }

    #[test]
    fn board_val_fields_preserve_int_vs_float() {
        // The aggregate-level hazard: `Board(100, 80)` keeps INT width/height
        // (the pyclass raw-stores constructor args), and `keepouts=[(0, 0, 50,
        // 80)]` keeps int quads. Both round-trip bit-identically — `1` must
        // NOT widen to `1.0` — and the owned `Val` fields record which.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<OwnedBoard>(py, "Board(100, 80, origin=(0, 0))", Some(&g));
            assert_roundtrip_with::<OwnedBoard>(
                py,
                "Board(100, 80, keepouts=[(0, 0, 50, 80), (10.5, 20.5, 30.5, 40.5)])",
                Some(&g),
            );
            assert_roundtrip_with::<OwnedBoard>(py, "Board(100.0, 80.0)", Some(&g));
            let owned =
                to_owned::<OwnedBoard>(&eval_expr(py, &g, "Board(100, 80, origin=(0, 0))"))
                    .unwrap();
            assert_eq!(owned.board.width, Val::Int(100));
            assert_eq!(owned.board.height, Val::Int(80));
            assert_eq!(owned.board.origin, (Val::Int(0), Val::Int(0)));
            let owned = to_owned::<OwnedBoard>(&eval_expr(
                py,
                &g,
                "Board(100, 80, keepouts=[(0, 0, 50, 80)])",
            ))
            .unwrap();
            assert_eq!(
                owned.board.keepouts,
                vec![(Val::Int(0), Val::Int(0), Val::Int(50), Val::Int(80))]
            );
            let owned = to_owned::<OwnedBoard>(&eval_expr(py, &g, "Board(100.0, 80.0)")).unwrap();
            assert_eq!(owned.board.width, Val::Float(100.0));
            assert_eq!(owned.board.origin, (Val::Float(0.0), Val::Float(0.0)));
        });
    }

    #[test]
    fn board_nan_and_infinities_roundtrip_in_val_fields() {
        // A NaN inside a `Val`-shaped Board field round-trips with type + repr
        // preserved and the owned field still NaN (manual type/repr arm — the
        // dataclass `__eq__` is False for NaN fields, the recorded U2 bound).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            for expr in [
                "Board(float('nan'), 80.0)",
                "Board(100.0, float('-inf'))",
                "Board(100.0, 80.0, origin=(float('nan'), 0.0))",
            ] {
                let orig = eval_expr(py, &g, expr);
                let owned = to_owned::<OwnedBoard>(&orig).expect("to_owned");
                let back = to_python::<OwnedBoard>(py, &owned).expect("to_python").bind(py).clone();
                assert!(orig.get_type().is(back.get_type()), "type mismatch for {expr}");
                let rp = orig.repr().unwrap().extract::<String>().unwrap();
                let rb = back.repr().unwrap().extract::<String>().unwrap();
                assert_eq!(rp, rb, "repr mismatch for {expr}");
            }
            let owned = to_owned::<OwnedBoard>(&eval_expr(py, &g, "Board(float('nan'), 80.0)"))
                .unwrap();
            match owned.board.width {
                Val::Float(f) => assert!(f.is_nan(), "width NaN must survive"),
                Val::Int(_) => panic!("width must be Val::Float"),
            }
        });
    }

    #[test]
    fn aggregate_guards_reject_the_wrong_container_and_sibling_types() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let err = |expr: &str| -> bool {
                to_owned::<OwnedBoard>(&eval_expr(py, &g, expr)).is_err()
            };
            // keepouts: the contract is a list of 4-tuples — a tuple-of-tuples,
            // a list-shaped quad, a wrong-arity quad and a bool leaf are all
            // LOUD errors, never coerced.
            assert!(err("Board(100.0, 80.0, keepouts=((0, 0, 50, 80),))"), "tuple keepouts must be rejected");
            assert!(err("Board(100.0, 80.0, keepouts=[[0, 0, 50, 80]])"), "list-shaped quad must be rejected");
            assert!(err("Board(100.0, 80.0, keepouts=[(0, 0, 50)])"), "3-tuple quad must be rejected");
            assert!(err("Board(100.0, 80.0, keepouts=[(0, 0, 50, True)])"), "bool quad leaf must be rejected");
            // origin: the contract is a 2-tuple.
            assert!(err("Board(100.0, 80.0, origin=(0,))"), "1-tuple origin must be rejected");
            assert!(err("Board(100.0, 80.0, origin=[0, 0])"), "list origin must be rejected");
            // width/height: a bool is not an int-or-float Val.
            assert!(err("Board(True, 80.0)"), "bool width must be rejected");
            // Netlist: components/nets are lists — a tuple-of-components
            // constructs fine in Python (build_indices iterates it) but must
            // be REJECTED by the marshal (a `Vec` is a `list`-shaped read).
            assert!(
                to_owned::<Netlist>(&eval_expr(
                    py,
                    &g,
                    "Netlist(components=(Component('R1', 'fp', (1, 2)),))"
                ))
                .is_err(),
                "tuple components must be rejected"
            );
        });
    }

    #[test]
    fn val_tuple_impls_roundtrip_losslessly() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<(Val, Val)>(py, "(0, 0)", None);
            assert_roundtrip_with::<(Val, Val)>(py, "(0.0, 1.5)", None);
            assert_roundtrip_with::<(Val, Val, Val, Val)>(py, "(0, 0, 50, 80)", None);
            assert_roundtrip_with::<(Val, Val, Val, Val)>(py, "(0.0, 0.0, 50.0, 80.0)", None);
            // Int leaves stay int in the owned tuple — never widened.
            let owned: (Val, Val, Val, Val) =
                to_owned(&eval_expr(py, &g, "(0, 0, 50, 80)")).unwrap();
            assert_eq!(
                owned,
                (Val::Int(0), Val::Int(0), Val::Int(50), Val::Int(80))
            );
        });
    }

    // -----------------------------------------------------------------------
    // U4: OwnedClearanceGrid — dims + registry owned, numpy cell arrays kept
    // -----------------------------------------------------------------------

    #[test]
    fn clearance_grid_roundtrips_bit_identically_with_arrays_by_identity() {
        // The dataclass `__eq__`/`__repr__` cover only the four constructor
        // dims (the `__post_init__` attrs are not declared fields), so
        // `assert_roundtrip_with` pins the dim round-trip; the registry and
        // the cell arrays are asserted explicitly below. The dims are
        // `Val`-shaped: `ClearageGrid(100, 80, ...)` keeps INT width/height
        // (the D3 stage passes `board.width`/`height` straight through), and
        // `100` must NOT widen to `100.0`.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<OwnedClearanceGrid>(py, "ClearanceGrid(100.0, 80.0, 0.5, 2)", Some(&g));
            assert_roundtrip_with::<OwnedClearanceGrid>(py, "ClearanceGrid(100, 80, 0.5, 2)", Some(&g));
            assert_roundtrip_with::<OwnedClearanceGrid>(py, "ClearanceGrid(100, 80, 1, 3)", Some(&g));

            // The cell arrays are KEEPS: the rebuilt grid's `_trace_net_ids` /
            // `_pad_net_ids` ARE the original list objects (identity) — the
            // dtype (`int32`) and element bytes are unchanged because nothing
            // is reconstructed (zero-copy passthrough).
            let orig = eval_expr(py, &g, "ClearanceGrid(100.0, 80.0, 0.5, 2)");
            let owned = to_owned::<OwnedClearanceGrid>(&orig).unwrap();
            let back = to_python::<OwnedClearanceGrid>(py, &owned).unwrap().bind(py).clone();
            for attr in ["_trace_net_ids", "_pad_net_ids"] {
                let a = orig.getattr(attr).unwrap();
                let b = back.getattr(attr).unwrap();
                assert!(a.is(&b), "{attr} must pass through by identity");
            }

            // The owned dims recorded int vs float (the Val convention).
            let owned = to_owned::<OwnedClearanceGrid>(&eval_expr(py, &g, "ClearanceGrid(100, 80, 0.5, 2)"))
                .unwrap();
            assert_eq!(owned.grid.width_mm, Val::Int(100));
            assert_eq!(owned.grid.height_mm, Val::Int(80));
            assert_eq!(owned.grid.cell_size_mm, Val::Float(0.5));
            assert_eq!(owned.grid.layer_count, 2);
            let owned = to_owned::<OwnedClearanceGrid>(&eval_expr(py, &g, "ClearanceGrid(100.0, 80.0, 0.5, 2)"))
                .unwrap();
            assert_eq!(owned.grid.width_mm, Val::Float(100.0));
        });
    }

    #[test]
    fn clearance_grid_net_registry_roundtrips_in_assignment_order() {
        // The net-id registry (`_net_to_id` / `_id_to_net` / `_next_net_id`)
        // is OWNED — the D3 differential pins the net-id ASSIGNMENT order, so
        // the `Vec`s must preserve insertion order through the round-trip.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let orig = eval_expr(py, &g, "ClearanceGrid(100.0, 80.0, 0.5, 2)");
            orig.setattr("_net_to_id", eval_expr(py, &g, "{'VCC': 1, 'GND': 2, 'SIG': 3}"))
                .unwrap();
            orig.setattr("_id_to_net", eval_expr(py, &g, "{1: 'VCC', 2: 'GND', 3: 'SIG'}"))
                .unwrap();
            orig.setattr("_next_net_id", 4).unwrap();
            let owned = to_owned::<OwnedClearanceGrid>(&orig).unwrap();
            assert_eq!(
                owned.grid.net_to_id,
                vec![
                    ("VCC".to_string(), 1),
                    ("GND".to_string(), 2),
                    ("SIG".to_string(), 3),
                ]
            );
            assert_eq!(owned.grid.id_to_net[1], (2, "GND".to_string()));
            assert_eq!(owned.grid.next_net_id, 4);
            let back = to_python::<OwnedClearanceGrid>(py, &owned).unwrap().bind(py).clone();
            let back_registry = back.getattr("_net_to_id").unwrap();
            assert!(
                back_registry
                    .eq(eval_expr(py, &g, "{'VCC': 1, 'GND': 2, 'SIG': 3}"))
                    .unwrap(),
                "_net_to_id must round-trip value-identically"
            );
            assert!(back.getattr("_next_net_id").unwrap().extract::<i64>().unwrap() == 4);
        });
    }

    // -----------------------------------------------------------------------
    // U4: OwnedDrcOracle — rules tables + credits + config owned, keeps by
    // identity (_net_class_rules models, zone_manager, PCBGeometry, callable)
    // -----------------------------------------------------------------------

    #[test]
    fn drc_oracle_roundtrips_bit_identically_with_keeps_by_identity() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            // The default/empty oracle (empty tables, empty credits, empty
            // pin_owner, no zones, no geometry) round-trips bit-identically.
            assert_roundtrip_with::<OwnedDrcOracle>(py, "DRCOracle(rules=ClearanceMatrix())", Some(&g));
            // A full single-element oracle: one clearance row, one net->class,
            // one differential pair, one net-class rule, one zone, one credit,
            // one pin_owner entry. The keeps (net_class_rules, zone_manager,
            // geometry) carry identity-bearing reprs, so they must pass by
            // identity for the repr arm to match.
            assert_roundtrip_with::<OwnedDrcOracle>(
                py,
                "DRCOracle(rules=ClearanceMatrix(_clearances={('Power', 'Signal'): 0.3}, \
                 _net_to_class={'VCC': 'Power'}, \
                 _differential_pairs={frozenset({'USB_D+', 'USB_D-'}): -0.05}, \
                 default_clearance=0.2, \
                 _net_class_rules={'Power': NetClassRules(name='Power', trace_width=0.5, clearance=0.3)}, \
                 zone_manager=ZoneManager([RoutingZone('HV', [(0, 0), (10, 0), (10, 10), (0, 10)], 3.0, {'Signal'})])), \
                 geometry=PCBGeometry(), \
                 clearance_credits={('K3', '2', '1'): (1.5, 0.75, 4.0, 10.0, 20.0, 'x')}, \
                 pin_owner={'K3-1': 'K3', 'K3-2': 'K3'})",
                Some(&g),
            );

            // Keeps round-trip BY IDENTITY: the rebuilt oracle's keep fields ARE
            // the original objects (never reconstructed).
            let orig = eval_expr(
                py,
                &g,
                "DRCOracle(rules=ClearanceMatrix(_net_class_rules={'Power': NetClassRules(name='Power')}, \
                 zone_manager=ZoneManager([RoutingZone('HV', [(0, 0), (10, 0), (10, 10), (0, 10)], 3.0, {'Signal'})])), \
                 geometry=PCBGeometry())",
            );
            let owned = to_owned::<OwnedDrcOracle>(&orig).unwrap();
            let back = to_python::<OwnedDrcOracle>(py, &owned).unwrap().bind(py).clone();
            let geo_orig = orig.getattr("geometry").unwrap();
            let geo_back = back.getattr("geometry").unwrap();
            assert!(geo_orig.is(&geo_back), "geometry must pass through by identity");
            let rules_orig = orig.getattr("rules").unwrap();
            let rules_back = back.getattr("rules").unwrap();
            for attr in ["_net_class_rules", "zone_manager"] {
                let a = rules_orig.getattr(attr).unwrap();
                let b = rules_back.getattr(attr).unwrap();
                assert!(a.is(&b), "rules.{attr} must pass through by identity");
            }

            // The owned rules/credit/config fields hold the exact values.
            let owned = to_owned::<OwnedDrcOracle>(&eval_expr(
                py,
                &g,
                "DRCOracle(rules=ClearanceMatrix(_clearances={('Power', 'Signal'): 0.3}, \
                 _net_to_class={'VCC': 'Power'}, default_clearance=0.25), \
                 _search_multiplier=4.0, enable_internal_layer_creepage=False, \
                 clearance_credits={('K3', '2', '1'): (1.5, 0.75, 4.0, 10.0, 20.0, 'x')}, \
                 pin_owner={'K3-1': 'K3'})",
            ))
            .unwrap();
            assert_eq!(owned.oracle.rules.clearances, vec![("Power".to_string(), "Signal".to_string(), 0.3)]);
            assert_eq!(owned.oracle.rules.net_to_class, vec![("VCC".to_string(), "Power".to_string())]);
            assert_eq!(owned.oracle.rules.default_clearance, 0.25);
            assert_eq!(owned.oracle.search_multiplier, 4.0);
            assert!(!owned.oracle.enable_internal_layer_creepage);
            assert_eq!(owned.oracle.pin_owner, vec![("K3-1".to_string(), "K3".to_string())]);
            assert_eq!(owned.oracle.clearance_credits.len(), 1);
            let credit = &owned.oracle.clearance_credits[0];
            assert_eq!(credit.component_ref, "K3");
            assert_eq!(credit.effective_clearance_mm, 1.5);
            assert_eq!(credit.axis.as_deref(), Some("x"));
        });
    }

    #[test]
    fn drc_oracle_callable_pin_owner_roundtrips_by_identity() {
        // `pin_owner` may be a Mapping (owned) OR a Callable (keep). A
        // callable is a live function object — identity passthrough, with the
        // owned Mapping `Vec` empty.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let orig = eval_expr(
                py,
                &g,
                "DRCOracle(rules=ClearanceMatrix(), pin_owner=lambda pid: 'K3' if pid.startswith('K3') else None)",
            );
            let owned = to_owned::<OwnedDrcOracle>(&orig).unwrap();
            assert!(owned.oracle.pin_owner.is_empty(), "callable form stores no Mapping rows");
            assert!(matches!(owned.pin_owner_callable, Plain::Opaque(_)), "callable form is a keep");
            let back = to_python::<OwnedDrcOracle>(py, &owned).unwrap().bind(py).clone();
            let a = orig.getattr("pin_owner").unwrap();
            let b = back.getattr("pin_owner").unwrap();
            assert!(a.is(&b), "callable pin_owner must pass through by identity");
            // The Mapping form (Null keep) rebuilds the dict instead.
            let orig_map = eval_expr(py, &g, "DRCOracle(rules=ClearanceMatrix(), pin_owner={'K3-1': 'K3'})");
            let owned_map = to_owned::<OwnedDrcOracle>(&orig_map).unwrap();
            assert!(matches!(owned_map.pin_owner_callable, Plain::Null), "Mapping form is not a callable keep");
            assert_eq!(owned_map.oracle.pin_owner, vec![("K3-1".to_string(), "K3".to_string())]);
            let back_map = to_python::<OwnedDrcOracle>(py, &owned_map).unwrap().bind(py).clone();
            assert!(
                back_map
                    .getattr("pin_owner")
                    .unwrap()
                    .eq(eval_expr(py, &g, "{'K3-1': 'K3'}"))
                    .unwrap(),
                "Mapping pin_owner must rebuild value-identically"
            );
        });
    }

    #[test]
    fn drc_oracle_guards_reject_the_wrong_shapes() {
        // The owned rules/credits have concrete types: a str where a float is
        // required, a wrong-arity tuple key, and a bool leaf are LOUD errors.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let err = |expr: &str| -> bool {
                to_owned::<OwnedDrcOracle>(&eval_expr(py, &g, expr)).is_err()
            };
            assert!(err("DRCOracle(rules=ClearanceMatrix(default_clearance='x'))"), "str default_clearance must be rejected");
            assert!(err("DRCOracle(rules=ClearanceMatrix(default_clearance=1))"), "int default_clearance must be rejected (an int is not a float)");
            assert!(err("DRCOracle(rules=ClearanceMatrix(_clearances={('Power',): 0.3}))"), "1-tuple clearance key must be rejected");
            assert!(err("DRCOracle(rules=ClearanceMatrix(_clearances={('Power', 'Signal'): 1}))"), "int clearance value must be rejected");
            assert!(err("DRCOracle(rules=ClearanceMatrix(), clearance_credits={('K3', '2'): (1.5, 0.75, 4.0, 10.0, 20.0, 'x')})"), "2-tuple credit key must be rejected");
            assert!(err("DRCOracle(rules=ClearanceMatrix(), pin_owner={'a': 1})"), "int pin_owner value must be rejected");
        });
    }

    #[test]
    fn grid_cell_arrays_preserve_numpy_int32_dtype_when_numpy_available() {
        // The dtype-preservation proof, expressed against REAL numpy when the
        // embedded interpreter can import it (the venv-backed PYO3_PYTHON); a
        // no-numpy interpreter skips the numpy arm — the identity assertions in
        // `clearance_grid_roundtrips_bit_identically_with_arrays_by_identity`
        // are the standing proof either way (the SAME array object is returned,
        // so its `int32` dtype and element bytes are unchanged by construction).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let Ok(np) = py.import("numpy") else { return; };
            let int32 = np.getattr("int32").expect("np.int32");
            let kw = PyDict::new(py);
            kw.set_item("dtype", &int32).expect("dtype kwarg");
            let arr = np
                .call_method("zeros", ((2, 3),), Some(&kw))
                .expect("np.zeros dtype=int32");
            let trace = pyo3::types::PyList::empty(py);
            trace.append(&arr).expect("append");
            let orig = eval_expr(py, &g, "ClearanceGrid(100.0, 80.0, 0.5, 2)");
            orig.setattr("_trace_net_ids", trace).expect("set trace");
            orig.setattr("_pad_net_ids", pyo3::types::PyList::empty(py)).expect("set pad");
            let owned = to_owned::<OwnedClearanceGrid>(&orig).unwrap();
            let back = to_python::<OwnedClearanceGrid>(py, &owned).unwrap().bind(py).clone();
            let orig_trace = orig.getattr("_trace_net_ids").unwrap();
            let back_trace = back.getattr("_trace_net_ids").unwrap();
            assert!(orig_trace.is(&back_trace), "the array list must pass by identity");
            let item = back_trace.get_item(0).unwrap();
            let dtype = item.getattr("dtype").unwrap();
            assert!(
                dtype.eq(&int32).unwrap(),
                "a numpy int32 array must round-trip as int32, not widen"
            );
            let orig_arr = orig_trace.get_item(0).unwrap();
            let orig_bytes = orig_arr.call_method0("tobytes").unwrap();
            let back_bytes = item.call_method0("tobytes").unwrap();
            assert!(
                orig_bytes.eq(&back_bytes).unwrap(),
                "the kept array's bytes must be unchanged"
            );
        });
    }

    // -----------------------------------------------------------------------
    // U5: the collection round-trip gate — the frozenset fields, the tuple
    // violation lists and the PreflightReport (violations)
    // -----------------------------------------------------------------------

    /// The U5 eval globals: the `_u5` namespace from `setup()` — the
    /// collection-element classes under their REAL names (the zone-geometry
    /// `Zone` lives there precisely so it never collides with the board
    /// `Zone` in the shared globals).
    fn u5<'py>(py: Python<'py>, g: &Bound<'py, PyDict>) -> Bound<'py, PyDict> {
        let _ = py;
        g.get_item("_u5")
            .expect("_u5 namespace")
            .expect("_u5 present")
            .cast::<PyDict>()
            .expect("_u5 is a dict")
            .clone()
    }

    /// The multi-element content gate: type + `==` + sorted element reprs.
    /// Iteration order of a rebuilt multi-element frozenset is
    /// deterministic-but-different (the recorded U1 bound), so the reprs are
    /// compared as a sorted multiset — never positionally.
    fn assert_content_roundtrip<'py, T: Marshal>(
        py: Python<'py>,
        globals: &Bound<'py, PyDict>,
        expr: &str,
    ) {
        let orig = eval_expr(py, globals, expr);
        let owned = to_owned::<T>(&orig).unwrap_or_else(|e| {
            panic!(
                "to_owned::<{}>({expr}) failed: {e}",
                std::any::type_name::<T>()
            )
        });
        let back = to_python::<T>(py, &owned).unwrap().bind(py).clone();
        assert!(
            orig.get_type().is(back.get_type()),
            "type mismatch for {expr}"
        );
        assert!(
            orig.eq(&back).unwrap(),
            "content mismatch for {expr}: orig {orig:?}, back {back:?}"
        );
        let sorted_repr = |o: &Bound<'_, PyAny>| -> Vec<String> {
            let mut items: Vec<String> = o
                .try_iter()
                .unwrap()
                .map(|s| s.unwrap().repr().unwrap().extract::<String>().unwrap())
                .collect();
            items.sort();
            items
        };
        assert_eq!(
            sorted_repr(&orig),
            sorted_repr(&back),
            "element reprs must be preserved for {expr}"
        );
    }

    #[test]
    fn zone_and_zone_slots_frozensets_roundtrip() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // The 2-field zone-geometry Zone: int-vs-float bounds canon (the
            // stage writes int `x_min`/`y_min` and board-dims with their
            // original type) round-trips bit-identically — `0` stays `0`.
            assert_roundtrip_with::<Zone>(py, "Zone('HV', ((0, 0), (50, 80)))", Some(&g5));
            assert_roundtrip_with::<Zone>(
                py,
                "Zone('HV', ((0, 0), (50.0, 80.0)))",
                Some(&g5),
            );
            let owned = to_owned::<Zone>(&eval_expr(py, &g5, "Zone('HV', ((0, 0), (50, 80)))"))
                .unwrap();
            assert_eq!(owned.name, "HV");
            assert_eq!(owned.bounds.0 .0, Val::Int(0));
            assert_eq!(owned.bounds.1 .0, Val::Int(50));
            // The zones frozenset: empty + single-element are bit-identical
            // (the guaranteed shapes); multi-element is content-gated.
            assert_roundtrip_with::<ZoneSet>(py, "frozenset()", Some(&g5));
            assert_roundtrip_with::<ZoneSet>(
                py,
                "frozenset({Zone('HV', ((0, 0), (50, 80)))})",
                Some(&g5),
            );
            assert_content_roundtrip::<ZoneSet>(
                py,
                &g5,
                "frozenset({Zone('HV', ((0, 0), (50, 80))), Zone('LV', ((0.0, 80.0), (100.0, 150.0)))})",
            );
            // zone_slots: (zone_name, tuple_of_slots) elements — the slots
            // tuple is ORDERED (a tuple, not a set) and preserved.
            assert_roundtrip_with::<ZoneSlotsSet>(
                py,
                "frozenset({('HV', ((0.0, 5.0), (5.0, 0.0)))})",
                Some(&g5),
            );
            assert_roundtrip_with::<ZoneSlotsSet>(py, "frozenset({('HV', ())})", Some(&g5));
            assert_content_roundtrip::<ZoneSlotsSet>(
                py,
                &g5,
                "frozenset({('HV', ((0.0, 5.0), (5.0, 0.0))), ('LV', ((10.0, 0.0), (0.0, 10.0)))})",
            );
            let owned = to_owned::<ZoneSlots>(&eval_expr(
                py,
                &g5,
                "('HV', ((0.0, 5.0), (5.0, 0.0)))",
            ))
            .unwrap();
            assert_eq!(owned.zone, "HV");
            assert_eq!(owned.slots.len(), 2);
            assert_eq!(owned.slots[1], SlotPos(5.0, 0.0));
        });
    }

    #[test]
    fn route_and_via_frozensets_roundtrip() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // routes = frozenset of Trace pyclasses; the owned Route reads
            // start/end/width/layer/net (strict floats — the pipeline and
            // D6 tests always construct Trace with float coords/width).
            assert_roundtrip_with::<Route>(
                py,
                "Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer='F.Cu', net='N')",
                Some(&g5),
            );
            // The `net` default (None) round-trips as None.
            assert_roundtrip_with::<Route>(
                py,
                "Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer='B.Cu')",
                Some(&g5),
            );
            assert_roundtrip_with::<RouteSet>(py, "frozenset()", Some(&g5));
            assert_roundtrip_with::<RouteSet>(
                py,
                "frozenset({Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer='F.Cu', net='N')})",
                Some(&g5),
            );
            // vias = frozenset of Via pyclasses (the default layers tuple
            // and the is_diff_pair default False).
            assert_roundtrip_with::<Via>(
                py,
                "Via(position=(10.0, 20.0), drill=0.3, width=0.6, layers=('F.Cu', 'B.Cu'), \
                 net='GND', is_diff_pair=False)",
                Some(&g5),
            );
            assert_roundtrip_with::<Via>(
                py,
                "Via(position=(10.0, 20.0), drill=0.3, width=0.6)",
                Some(&g5),
            );
            assert_roundtrip_with::<ViaSet>(
                py,
                "frozenset({Via(position=(10.0, 20.0), drill=0.3, width=0.6)})",
                Some(&g5),
            );
            // Multi-element content gates for both.
            assert_content_roundtrip::<RouteSet>(
                py,
                &g5,
                "frozenset({Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer='F.Cu', net='N1'), \
                  Trace(start=(1.0, 2.0), end=(3.0, 4.0), width=0.5, layer='B.Cu', net='N2')})",
            );
            assert_content_roundtrip::<ViaSet>(
                py,
                &g5,
                "frozenset({Via(position=(10.0, 20.0), drill=0.3, width=0.6, net='GND'), \
                  Via(position=(1.0, 2.0), drill=0.3, width=0.6, layers=('In1.Cu', 'In2.Cu'), net='VCC')})",
            );
        });
    }

    #[test]
    fn layer_assignment_roundtrips() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            assert_roundtrip_with::<LayerAssignment>(
                py,
                "LayerAssignment(net_name='VCC', layer=2, allow_layer_change=True, is_plane=True)",
                Some(&g5),
            );
            assert_roundtrip_with::<LayerAssignmentSet>(
                py,
                "frozenset({LayerAssignment(net_name='GND', layer=1, allow_layer_change=True, is_plane=True)})",
                Some(&g5),
            );
            // The pyclass stores `layer` UNCOERCED — int stays int (the
            // pipeline's `assign_layer_by_net_class` i64), and a float layer
            // stays float; `Val` records which.
            assert_roundtrip_with::<LayerAssignment>(
                py,
                "LayerAssignment(net_name='SIG', layer=2.0)",
                Some(&g5),
            );
            let owned =
                to_owned::<LayerAssignment>(&eval_expr(py, &g5, "LayerAssignment(net_name='SIG', layer=2)"))
                    .unwrap();
            assert_eq!(owned.layer, Val::Int(2));
            let owned =
                to_owned::<LayerAssignment>(&eval_expr(py, &g5, "LayerAssignment(net_name='SIG', layer=2.0)"))
                    .unwrap();
            assert_eq!(owned.layer, Val::Float(2.0));
            assert_content_roundtrip::<LayerAssignmentSet>(
                py,
                &g5,
                "frozenset({LayerAssignment(net_name='VCC', layer=2, is_plane=True), \
                  LayerAssignment(net_name='GND', layer=1, is_plane=True)})",
            );
        });
    }

    #[test]
    fn placements_and_pair_maps_roundtrip() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // placements = frozenset of (ref, (x, y)) tuples.
            assert_roundtrip_with::<PlacementSet>(py, "frozenset()", Some(&g5));
            assert_roundtrip_with::<PlacementSet>(
                py,
                "frozenset({('U1', (10.0, 20.0))})",
                Some(&g5),
            );
            // The U0 end-to-end multi-element shape — content gate.
            assert_content_roundtrip::<PlacementSet>(
                py,
                &g5,
                "frozenset({('U1', (10.0, 20.0)), ('R1', (5.5, 7.25))})",
            );
            // component_zone_map / component_domain_map — both StrPairSet.
            assert_roundtrip_with::<StrPairSet>(py, "frozenset({('U1', 'HV')})", Some(&g5));
            assert_roundtrip_with::<StrPairSet>(
                py,
                "frozenset({('K3', 'HV_edge')})",
                Some(&g5),
            );
            assert_content_roundtrip::<StrPairSet>(
                py,
                &g5,
                "frozenset({('U1', 'HV'), ('R1', 'LV'), ('K3', 'iso')})",
            );
            let owned = to_owned::<Placement>(&eval_expr(py, &g5, "('U1', (10.0, 20.0))")).unwrap();
            assert_eq!(owned.ref_, "U1");
            assert_eq!(owned.position, (10.0, 20.0));
        });
    }

    #[test]
    fn violation_lists_roundtrip() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // The three violation lists are Python TUPLES — the owned Vec
            // preserves order, so even a multi-element tuple round-trips
            // bit-identically (repr is order-based and the order is kept).
            assert_roundtrip_with::<ViolationList>(py, "()", Some(&g5));
            assert_roundtrip_with::<ViolationList>(
                py,
                "(Violation(type='track_clearance', geometry_a_id='t1', geometry_b_id='t2', \
                 net_a='N1', net_b='N2', clearance_actual=0.1, clearance_required=0.2, \
                 location=Point(x=1.0, y=2.0)),)",
                Some(&g5),
            );
            assert_roundtrip_with::<ViolationList>(
                py,
                "(Violation(type='a', geometry_a_id='x', geometry_b_id='y', net_a='N1', net_b='N2', \
                 clearance_actual=0.1, clearance_required=0.2, location=Point(x=1.0, y=2.0)), \
                 Violation(type='b', geometry_a_id='u', geometry_b_id='v', net_a='N3', net_b='N4', \
                 clearance_actual=0.3, clearance_required=0.4, location=Point(x=3.0, y=4.0)))",
                Some(&g5),
            );
            assert_roundtrip_with::<ConnectivityViolationList>(
                py,
                "(ConnectivityViolation(type='orphan_island', net='GND', \
                 location=Point(x=1.0, y=2.0), description='isolated copper'),)",
                Some(&g5),
            );
            // PlacementViolation with the optional fields unset (None) and
            // fully populated.
            assert_roundtrip_with::<PlacementViolationList>(
                py,
                "(PlacementViolation(constraint_name='c1', violation_type='missing_component', \
                 message='m', severity='warning'),)",
                Some(&g5),
            );
            assert_roundtrip_with::<PlacementViolationList>(
                py,
                "(PlacementViolation(constraint_name='c2', violation_type='proximity', \
                 message='too close', severity='error', component_a='U1', component_b='R1', \
                 actual_distance_mm=1.5, required_distance_mm=2.0),)",
                Some(&g5),
            );
            // The owned values hold the exact fields.
            let owned = to_owned::<Violation>(&eval_expr(
                py,
                &g5,
                "Violation(type='via_clearance', geometry_a_id='v1', geometry_b_id='p2', \
                 net_a='GND', net_b='SIG', clearance_actual=0.05, clearance_required=0.2, \
                 location=Point(x=5.0, y=6.0))",
            ))
            .unwrap();
            assert_eq!(owned.type_, "via_clearance");
            assert_eq!(owned.location, (5.0, 6.0));
            let owned = to_owned::<ConnectivityViolation>(&eval_expr(
                py,
                &g5,
                "ConnectivityViolation(type='dangling_track', net='SIG', location=Point(x=0.5, y=0.5), description='d')",
            ))
            .unwrap();
            assert_eq!(owned.net, "SIG");
            let owned = to_owned::<PlacementViolation>(&eval_expr(
                py,
                &g5,
                "PlacementViolation(constraint_name='c', violation_type='hv_clearance', message='m', severity='warning')",
            ))
            .unwrap();
            assert_eq!(owned.severity, "warning");
            assert_eq!(owned.component_a, None);
            assert_eq!(owned.actual_distance_mm, None);
        });
    }

    #[test]
    fn preflight_report_roundtrips() {
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            // `violations` at runtime is the PreflightReport-shaped DICT the
            // PreflightStage writes — plain data, rebuilt as a dict.
            assert_roundtrip_with::<PreflightReport>(
                py,
                "{'checks': [], 'overall': 'pass', 'total_time_ms': 0.0}",
                None,
            );
            assert_roundtrip_with::<PreflightReport>(
                py,
                "{'checks': [{'name': 'Component Area', 'result': 'pass', 'message': 'Fill ratio 10.0%', \
                 'details': None, 'time_ms': 0.5}, \
                 {'name': 'Constraint Satisfiability', 'result': 'fail', \
                 'message': 'Found 1 issues', 'details': {'impossible': ['U1-R1: max 5.0mm < min 6.0mm']}, \
                 'time_ms': 1.25}], \
                 'overall': 'fail', 'total_time_ms': 1.75}",
                None,
            );
            // The owned struct holds the typed checks.
            let owned = to_owned::<PreflightReport>(&eval_expr(
                py,
                &g,
                "{'checks': [{'name': 'Zone Capacity', 'result': 'fail', 'message': 'Zone HV over cap', \
                 'details': {'violations': ['Zone HV over cap']}, 'time_ms': 0.25}], \
                 'overall': 'fail', 'total_time_ms': 0.25}",
            ))
            .unwrap();
            assert_eq!(owned.overall, "fail");
            assert_eq!(owned.checks.len(), 1);
            assert_eq!(owned.checks[0].name, "Zone Capacity");
            assert_eq!(
                owned.checks[0].details,
                Some(OwnedPlain::Dict(vec![(
                    "violations".to_string(),
                    OwnedPlain::List(vec![OwnedPlain::Str("Zone HV over cap".to_string())]),
                )]))
            );
        });
    }

    #[test]
    fn collection_nan_and_infinities_roundtrip() {
        // NaN/±inf inside a collection element or the report round-trip with
        // type + repr preserved and the owned field still NaN (manual
        // type/repr arm — a dataclass/tuple `__eq__` is False for NaN
        // fields, the recorded U2 bound).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // Manual type/repr arm per shape: the rebuilt object's type and
            // repr are identical to the original's.
            for expr in [
                "(Violation(type='a', geometry_a_id='x', geometry_b_id='y', net_a='N1', net_b='N2', \
                 clearance_actual=float('nan'), clearance_required=0.2, location=Point(x=1.0, y=2.0)),)",
                "(ConnectivityViolation(type='orphan_island', net='GND', \
                 location=Point(x=float('inf'), y=0.0), description='d'),)",
                "{'checks': [], 'overall': 'pass', 'total_time_ms': float('-inf')}",
            ] {
                let back: Py<PyAny> = if expr.contains("ConnectivityViolation") {
                    let owned = to_owned::<ConnectivityViolationList>(&eval_expr(py, &g5, expr))
                        .expect("to_owned");
                    to_python::<ConnectivityViolationList>(py, &owned).expect("to_python")
                } else if expr.contains("'checks'") {
                    let owned =
                        to_owned::<PreflightReport>(&eval_expr(py, &g5, expr)).expect("to_owned");
                    to_python::<PreflightReport>(py, &owned).expect("to_python")
                } else {
                    let owned =
                        to_owned::<ViolationList>(&eval_expr(py, &g5, expr)).expect("to_owned");
                    to_python::<ViolationList>(py, &owned).expect("to_python")
                };
                let orig = eval_expr(py, &g5, expr);
                let back = back.bind(py).clone();
                assert!(orig.get_type().is(back.get_type()), "type mismatch for {expr}");
                let rp = orig.repr().unwrap().extract::<String>().unwrap();
                let rb = back.repr().unwrap().extract::<String>().unwrap();
                assert_eq!(rp, rb, "repr mismatch for {expr}");
            }
            // Field-level: the NaN clearance is still NaN after the
            // round-trip; the NaN Trace width survives in a single-element
            // frozenset (type + repr preserved).
            let owned = to_owned::<ViolationList>(&eval_expr(
                py,
                &g5,
                "(Violation(type='a', geometry_a_id='x', geometry_b_id='y', net_a='N1', net_b='N2', \
                 clearance_actual=float('nan'), clearance_required=0.2, location=Point(x=1.0, y=2.0)),)",
            ))
            .unwrap();
            assert!(owned[0].clearance_actual.is_nan(), "clearance NaN must survive");
            let orig = eval_expr(
                py,
                &g5,
                "frozenset({Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=float('nan'), layer='F.Cu')})",
            );
            let owned = to_owned::<RouteSet>(&orig).expect("to_owned");
            let back = to_python::<RouteSet>(py, &owned).expect("to_python").bind(py).clone();
            assert!(orig.get_type().is(back.get_type()), "NaN Trace type mismatch");
            let rp = orig.repr().unwrap().extract::<String>().unwrap();
            let rb = back.repr().unwrap().extract::<String>().unwrap();
            assert_eq!(rp, rb, "NaN Trace repr mismatch");
        });
    }

    #[test]
    fn frozenset_rebuild_is_deterministic() {
        // The repr-sorted rebuild is DETERMINISTIC: two `to_python` calls
        // from the same owned value produce repr-identical frozensets
        // (never the process-random HashSet iteration order).
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            let owned = to_owned::<RouteSet>(&eval_expr(
                py,
                &g5,
                "frozenset({Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer='F.Cu', net='N1'), \
                  Trace(start=(1.0, 2.0), end=(3.0, 4.0), width=0.5, layer='B.Cu', net='N2'), \
                  Trace(start=(5.0, 6.0), end=(7.0, 8.0), width=0.3, layer='F.Cu', net='N3')})",
            ))
            .unwrap();
            let r1 = to_python::<RouteSet>(py, &owned)
                .unwrap()
                .bind(py)
                .repr()
                .unwrap()
                .extract::<String>()
                .unwrap();
            let r2 = to_python::<RouteSet>(py, &owned)
                .unwrap()
                .bind(py)
                .repr()
                .unwrap()
                .extract::<String>()
                .unwrap();
            assert_eq!(r1, r2, "rebuild must be deterministic across calls");
        });
    }

    #[test]
    fn collection_guards_reject_wrong_shapes() {
        // Every owned collection element/field has a concrete type: an
        // int-shaped float coordinate, a wrong-arity tuple, a list where a
        // tuple/frozenset is the contract, and a str where a float is
        // required are LOUD errors, never coerced or kind-widened.
        let _guard = NETLIST_TESTS_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            let g5 = u5(py, &g);
            // int-shaped coords/width (an int is not a float).
            assert!(
                to_owned::<RouteSet>(&eval_expr(
                    py,
                    &g5,
                    "frozenset({Trace(start=(0, 0), end=(10.0, 0.0), width=0.2, layer='F.Cu', net='N')})"
                ))
                .is_err(),
                "int Trace coordinate must be rejected"
            );
            assert!(
                to_owned::<Route>(&eval_expr(
                    py,
                    &g5,
                    "Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=1, layer='F.Cu')"
                ))
                .is_err(),
                "int Trace width must be rejected"
            );
            assert!(
                to_owned::<PlacementSet>(&eval_expr(py, &g5, "frozenset({('U1', (10, 20))})")).is_err(),
                "int placement position must be rejected"
            );
            // Wrong-arity tuples.
            assert!(
                to_owned::<Via>(&eval_expr(
                    py,
                    &g5,
                    "Via(position=(10.0, 20.0), drill=0.3, width=0.6, layers=('F.Cu',))"
                ))
                .is_err(),
                "1-tuple via layers must be rejected"
            );
            assert!(
                to_owned::<Zone>(&eval_expr(py, &g5, "Zone('HV', ((0, 0),))")).is_err(),
                "1-corner bounds must be rejected"
            );
            assert!(
                to_owned::<ZoneSlots>(&eval_expr(py, &g5, "('HV', ((0, 5),))")).is_err(),
                "int slot coordinate must be rejected"
            );
            // Collection-kind mismatches: a list is not a frozenset/tuple.
            assert!(
                to_owned::<PlacementSet>(&eval_expr(py, &g5, "[('U1', (10.0, 20.0))]")).is_err(),
                "a list must be rejected for a frozenset field"
            );
            assert!(
                to_owned::<ViolationList>(&eval_expr(
                    py,
                    &g5,
                    "[Violation(type='a', geometry_a_id='x', geometry_b_id='y', net_a='N1', \
                     net_b='N2', clearance_actual=0.1, clearance_required=0.2, \
                     location=Point(x=1.0, y=2.0))]"
                ))
                .is_err(),
                "a list must be rejected for a tuple violation field"
            );
            // PreflightReport guards: tuple checks (list contract) and a
            // str total_time_ms (an int/str is not a float).
            assert!(
                to_owned::<PreflightReport>(&eval_expr(
                    py,
                    &g,
                    "{'checks': (), 'overall': 'pass', 'total_time_ms': 0.0}"
                ))
                .is_err(),
                "tuple checks must be rejected"
            );
            assert!(
                to_owned::<PreflightReport>(&eval_expr(
                    py,
                    &g,
                    "{'checks': [], 'overall': 'pass', 'total_time_ms': 'x'}"
                ))
                .is_err(),
                "str total_time_ms must be rejected"
            );
            // Violation: a str clearance (not a float) is a loud error.
            assert!(
                to_owned::<Violation>(&eval_expr(
                    py,
                    &g5,
                    "Violation(type='a', geometry_a_id='x', geometry_b_id='y', net_a='N1', \
                     net_b='N2', clearance_actual='x', clearance_required=0.2, \
                     location=Point(x=1.0, y=2.0))"
                ))
                .is_err(),
                "str clearance must be rejected"
            );
        });
    }
}

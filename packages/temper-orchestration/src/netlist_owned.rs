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

#![allow(dead_code)] // U2/U3 scaffolding: consumed by U4+'s BoardState field
// ports and the stage rewires; until then only the round-trip gate tests
// exercise this file.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFrozenSet, PySet, PyTuple};

use pyo3::IntoPyObjectExt;

use temper_data_model::{
    Board, ClearanceCredit, ClearanceGrid, ClearanceMatrix, Component, DrcOracle, Net, Netlist, Pin,
    Val,
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
        if let Ok(tdb) = py.import("temper_design_bundle_python")
            && let Ok(nc) = tdb.getattr("netlist_contracts")
            && let Ok(bc) = tdb.getattr("board_contracts")
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
        tdb.add("board_contracts", &bc).expect("tdb.board_contracts");
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
        rv6.add("constraints_design_rules", &cdr).expect("rv6.constraints_design_rules");
        rv6.add("constraints_drc_oracle", &cdo).expect("rv6.constraints_drc_oracle");
        pkg.add("router_v6", &rv6).expect("pkg.router_v6");
        for (path, module) in [
            ("temper_placer", &pkg),
            ("temper_placer.deterministic", &det),
            ("temper_placer.deterministic.stages", &stages),
            ("temper_placer.deterministic.stages._grid_core", &grid_core),
            ("temper_placer.router_v6", &rv6),
            ("temper_placer.router_v6.constraints_design_rules", &cdr),
            ("temper_placer.router_v6.constraints_drc_oracle", &cdo),
        ] {
            modules.set_item(path, module).expect("sys.modules u4");
        }
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
}

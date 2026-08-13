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

use temper_data_model::{Board, Component, Net, Netlist, Pin, Val};

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
"#;

    /// Define the stand-in dataclasses in a globals dict and register them in
    /// `sys.modules` under the path the `to_python` runtime import looks up
    /// (`temper_design_bundle_python.netlist_contracts` and
    /// `...board_contracts`), exactly the mock pattern the d3–d7 stage
    /// runners use for their call-backs.
    fn setup<'py>(py: Python<'py>) -> Bound<'py, PyDict> {
        let globals = PyDict::new(py);
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
        globals
    }

    #[test]
    fn component_int_vs_float_bounds_roundtrip_type_preserving() {
        // The netlist_contracts hazard: `Component("R1", "fp", (1, 2))` keeps
        // `int` bounds; `(1.0, 2.0)` keeps `float` bounds. Both round-trip
        // bit-identically — `1` must NOT widen to `1.0`.
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
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Component>(
                py,
                "Component('U1', 'QFN-56', (7.5, 7.5), [Pin('1', '1', (-3.5, 0.0), net='VCC'), \
                 Pin('2', '2', (3.5, 0.0))], net_class='HighVoltage', zone='power', fixed=True, \
                 initial_position=(10.0, 20.0), initial_rotation=1, initial_side=0, \
                 attributes={'value': '100nF'}, tags=frozenset({'power', 'top'}), sheetpath='hb.power_loop.q_high')",
                Some(&g),
            );
        });
    }

    #[test]
    fn component_defaults_roundtrip_losslessly() {
        // Only ref/footprint/bounds are given; the rest fall to dataclass
        // defaults and must come back exactly (empty list/dict/frozenset,
        // `None` for the optionals).
        Python::initialize();
        Python::attach(|py| {
            let g = setup(py);
            assert_roundtrip_with::<Component>(py, "Component('R1', 'fp', (1, 2))", Some(&g));
        });
    }

    #[test]
    fn pin_roundtrips_losslessly() {
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
}

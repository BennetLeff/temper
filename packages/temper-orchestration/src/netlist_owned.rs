//! The U2 (O-C3) leaf-struct boundary: `Marshal` impls for the owned
//! `Component`/`Pin`/`Net` structs from `temper-data-model`, plus the two
//! tuple impls (`(f64, f64)`, `(String, String)`) their fields need.
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

#![allow(dead_code)] // U2 scaffolding: consumed by U3+'s Board/Netlist
// aggregates and the stage ports; until then only the round-trip gate tests
// exercise this file.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFrozenSet, PySet, PyTuple};

use temper_data_model::{Component, Net, Pin, Val};

use crate::marshal::{Marshal, type_err};

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
// Tests — the U2 leaf round-trip losslessness proof
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;
    use crate::marshal::{assert_roundtrip_with, to_owned, to_python};

    /// Faithful `@dataclass` stand-ins for the design-bundle pyclasses, in the
    /// oracle's exact field order (`tests/core/_netlist_py_oracle.py`). A
    /// dataclass reproduces the pyclass `__repr__`/`__eq__` bit-for-bit
    /// (both assemble the field list and delegate `repr`/`==` to CPython's),
    /// so the round-trip gate's type/repr/eq checks are meaningful without
    /// building the real `.so` (which `cargo test` here does not).
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
"#;

    /// Define the stand-in dataclasses in a globals dict and register them in
    /// `sys.modules` under the path the `to_python` runtime import looks up
    /// (`temper_design_bundle_python.netlist_contracts`), exactly the mock
    /// pattern the d3–d7 stage runners use for their call-backs.
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
        tdb.add("netlist_contracts", &nc).expect("tdb.netlist_contracts");
        modules
            .set_item("temper_design_bundle_python", &tdb)
            .expect("sys.modules tdb");
        modules
            .set_item("temper_design_bundle_python.netlist_contracts", &nc)
            .expect("sys.modules tdb.netlist_contracts");
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
}

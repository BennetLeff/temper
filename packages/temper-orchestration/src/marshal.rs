//! Boundary marshaller for the orchestration data-model port (unit O-C3/U0).
//!
//! This is the foundation the later units (U1–U4) build on to replace the 23
//! `Option<Py<PyAny>>` `BoardState` fields with owned Rust structs. It proves
//! — once, at the boundary — that a Python object can be marshalled INTO an
//! owned Rust value and back OUT bit-identically, before any stage code is
//! rewritten.
//!
//! # Why owned marshalling (the cross-extension identity dodge)
//!
//! `docs/evidence/2026-08-12-cross-extension-pyclass-identity.md` records the
//! blocker this unit is the first step past: `temper-design-bundle` and
//! `temper-orchestration` are two extension `.so` files, so an
//! `extract::<Py<Netlist>>()` in orchestration checks `isinstance` against a
//! *second* `Netlist` type object and fails (`'Netlist' object is not an
//! instance of 'Netlist'`). Pure-Rust ownership dodges that by construction:
//! the marshaller reads fields with `obj.getattr("width")?.extract::<f64>()`
//! — never `extract::<Py<T>>()` — so the duplicated-`LazyTypeObject` problem
//! cannot arise. A Rust field that *names* a foreign pyclass is the bug; an
//! owned `struct`/`enum` with plain scalar and collection fields is not.
//!
//! # The `Val` enum (the concrete-Python-type hazard)
//!
//! `packages/temper-design-bundle/src/netlist_contracts.rs` documents the
//! hazard: a plain dataclass performs no `__init__` coercion, so
//! `Component("R1", "fp", (1, 2))` stores `int` bounds and `width` returns
//! `int` `1`, not `1.0`. A Rust field typed `f64` would silently widen every
//! such value, changing `repr`, `==`, and downstream numpy dtype promotion.
//! [`Val`] is the canonical type for any field that can hold `int` OR
//! `float`: it records which one it was and round-trips it back unchanged.
//!
//! # Lossless-proven types (the round-trip gate)
//!
//! [`Marshal`] is implemented for the minimal representative set the gate
//! proves bit-identical (type, `repr`, and NaN-aware `==`):
//!
//! - `i64` ↔ `int`, `f64` ↔ `float`, `String` ↔ `str`, `bool` ↔ `bool`
//!   (each *rejects* the sibling numeric type rather than widening it; `bool`
//!   is checked before `int` because it is an `int` subclass in CPython).
//! - [`Val`] ↔ `int` or `float` (type-preserving).
//! - `Option<T>` ↔ `None` or `T`.
//! - `Vec<T>` ↔ `list` (homogeneous; a `tuple` needs [`Plain`]).
//! - [`Plain`] ↔ any nested builtin value tree (`None`/`bool`/`int`/`float`/
//!   `str`/`bytes`/`tuple`/`list`/`set`/`frozenset`/`dict`), preserving the
//!   concrete collection kind and every leaf type.
//!
//! # Keeps (types that cannot round-trip through an owned struct)
//!
//! Anything not covered above marshals to [`Plain::Opaque`], a reference
//! passthrough (the object is stored as-is and returned unchanged — identity
//! preserved, nothing reconstructed). This is deliberate for numpy arrays
//! (`netlist_contracts.rs`: the dtype and every element bit pattern are
//! numpy's own — no Rust-side float conversion may widen `float32` to
//! `float64`), shapely/GEOS geometries, and the pyclasses owned by other
//! `.so` files. Those stay `Py<PyAny>`-shaped until their owner crate
//! migrates them; the boundary marshaller must not force a lossy copy.

#![allow(dead_code)] // U0 scaffolding: consumed by the U1+ stage ports; until
// then only the round-trip gate tests exercise this file.

use pyo3::IntoPyObjectExt;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::{
    PyBool, PyBytes, PyDict, PyFloat, PyFrozenSet, PyInt, PyList, PySet, PyString, PyTuple,
};

// ---------------------------------------------------------------------------
// The marshalling contract
// ---------------------------------------------------------------------------

/// The boundary-marshalling contract: convert a Python object into an owned
/// Rust value and back, bit-identically for the lossless-proven types.
///
/// Implementors must read scalars via `extract::<f64>()`/`extract::<i64>()`/
/// `extract::<String>()` and iterate collections — **never**
/// `extract::<Py<T>>()`, which is the cross-`.so` pyclass-identity blocker
/// (see the module doc and `docs/evidence/2026-08-12-cross-extension-pyclass-identity.md`).
pub trait Marshal: Sized {
    /// Marshal a Python object into the owned Rust value. Returns a `PyResult`
    /// with a clear, attribute-naming error on a type mismatch.
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self>;

    /// Marshal the owned value back to a Python object.
    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>>;
}

/// `to_owned::<T>(py_obj)`: marshal a Python object into owned `T`.
pub fn to_owned<T: Marshal>(obj: &Bound<'_, PyAny>) -> PyResult<T> {
    T::from_python(obj.py(), obj)
}

/// `to_python::<T>(owned)`: marshal owned `T` back to a Python object.
pub fn to_python<T: Marshal>(py: Python<'_>, owned: &T) -> PyResult<Py<PyAny>> {
    owned.to_python(py)
}

// ---------------------------------------------------------------------------
// The `Val` enum — the int-or-float canonical type
// ---------------------------------------------------------------------------

/// The concrete-Python-type canonical for a field that can hold `int` OR
/// `float` (e.g. a component's bounds `(1, 2)` vs `(1.0, 2.0)`).
///
/// Round-trips preserving WHICH it was — `extract::<f64>()` alone would
/// silently widen `int` `1` to `float` `1.0`, changing `repr` (`1` → `1.0`),
/// `==` against int-sensitive code, and downstream numpy dtype promotion.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Val {
    Int(i64),
    Float(f64),
}

impl Marshal for Val {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        // `bool` is an `int` subclass in CPython — reject it before the int
        // branch, or `True` would marshal to `Val::Int(1)` and round-trip as
        // `1` (a type change).
        if obj.is_instance_of::<PyBool>() {
            return Err(type_err(obj, "Val", "a bool is not an int-or-float value"));
        }
        if obj.is_instance_of::<PyInt>() {
            let i: i64 = obj
                .extract()
                .map_err(|e| type_err(obj, "Val", &format!("int out of i64 range: {e}")))?;
            return Ok(Val::Int(i));
        }
        if obj.is_instance_of::<PyFloat>() {
            return Ok(Val::Float(obj.extract::<f64>()?));
        }
        Err(type_err(obj, "Val", "expected int or float"))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self {
            Val::Int(i) => (*i).into_py_any(py),
            Val::Float(f) => (*f).into_py_any(py),
        }
    }
}

// ---------------------------------------------------------------------------
// Scalar impls — each rejects the sibling numeric type rather than widening
// ---------------------------------------------------------------------------

impl Marshal for i64 {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        if obj.is_instance_of::<PyBool>() {
            return Err(type_err(obj, "int", "a bool is not an int"));
        }
        obj.extract::<i64>()
            .map_err(|e| type_err(obj, "int", &format!("expected int: {e}")))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        (*self).into_py_any(py)
    }
}

impl Marshal for f64 {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        if obj.is_instance_of::<PyBool>() || obj.is_instance_of::<PyInt>() {
            return Err(type_err(
                obj,
                "float",
                "an int is not a float — use Val for an int-or-float field",
            ));
        }
        obj.extract::<f64>()
            .map_err(|e| type_err(obj, "float", &format!("expected float: {e}")))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        (*self).into_py_any(py)
    }
}

impl Marshal for bool {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        obj.extract::<bool>()
            .map_err(|e| type_err(obj, "bool", &format!("expected bool: {e}")))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        (*self).into_py_any(py)
    }
}

impl Marshal for String {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        obj.extract::<String>()
            .map_err(|e| type_err(obj, "str", &format!("expected str: {e}")))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        self.clone().into_py_any(py)
    }
}

// ---------------------------------------------------------------------------
// Generic container impls
// ---------------------------------------------------------------------------

impl<T: Marshal> Marshal for Option<T> {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        if obj.is_none() {
            Ok(None)
        } else {
            Ok(Some(T::from_python(_py, obj)?))
        }
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self {
            None => Ok(py.None()),
            Some(v) => v.to_python(py),
        }
    }
}

impl<T: Marshal> Marshal for Vec<T> {
    fn from_python(_py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        let list = obj
            .cast::<PyList>()
            .map_err(|_| type_err(obj, "list", "expected list"))?;
        let mut out = Vec::with_capacity(list.len());
        for item in list.iter() {
            out.push(T::from_python(_py, &item)?);
        }
        Ok(out)
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for item in self {
            list.append(item.to_python(py)?.bind(py))?;
        }
        Ok(list.into_any().unbind())
    }
}

// ---------------------------------------------------------------------------
// `Plain` — the lossless nested-value tree
// ---------------------------------------------------------------------------

/// A lossless plain-value tree: any builtin Python value, captured with
/// enough type information to round-trip bit-identically (type, `repr`, and
/// `==` all preserved). The `Int`/`Float` variants carry the same int-vs-float
/// distinction [`Val`] does, at each leaf of a nested collection.
///
/// `Opaque` is the *keep* fallback: a value with no owned representation
/// (numpy arrays, shapely geometries, foreign pyclasses) is passed through by
/// reference — identity preserved, nothing reconstructed.
#[derive(Clone, Debug)]
pub enum Plain {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Bytes(Vec<u8>),
    Tuple(Vec<Plain>),
    List(Vec<Plain>),
    Set(Vec<Plain>),
    FrozenSet(Vec<Plain>),
    Dict(Vec<(Plain, Plain)>),
    Opaque(Py<PyAny>),
}

impl Marshal for Plain {
    fn from_python(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Self> {
        if obj.is_none() {
            return Ok(Plain::Null);
        }
        // Order matters: bool before int (bool is an int subclass).
        if obj.is_instance_of::<PyBool>() {
            return Ok(Plain::Bool(obj.extract::<bool>()?));
        }
        if obj.is_instance_of::<PyInt>() {
            let i: i64 = obj
                .extract()
                .map_err(|e| type_err(obj, "Plain", &format!("int out of i64 range: {e}")))?;
            return Ok(Plain::Int(i));
        }
        if obj.is_instance_of::<PyFloat>() {
            return Ok(Plain::Float(obj.extract::<f64>()?));
        }
        if obj.is_instance_of::<PyString>() {
            return Ok(Plain::Str(obj.extract::<String>()?));
        }
        if obj.is_instance_of::<PyBytes>() {
            return Ok(Plain::Bytes(obj.extract::<Vec<u8>>()?));
        }
        if obj.is_instance_of::<PyTuple>() {
            return Ok(Plain::Tuple(plain_children(py, obj)?));
        }
        if obj.is_instance_of::<PyList>() {
            return Ok(Plain::List(plain_children(py, obj)?));
        }
        if obj.is_instance_of::<PyFrozenSet>() {
            return Ok(Plain::FrozenSet(plain_children(py, obj)?));
        }
        if obj.is_instance_of::<PySet>() {
            return Ok(Plain::Set(plain_children(py, obj)?));
        }
        if let Ok(d) = obj.cast::<PyDict>() {
            let mut items = Vec::with_capacity(d.len());
            for (k, v) in d.iter() {
                items.push((Plain::from_python(py, &k)?, Plain::from_python(py, &v)?));
            }
            return Ok(Plain::Dict(items));
        }
        // Keep: opaque passthrough (numpy, shapely, foreign pyclasses).
        Ok(Plain::Opaque(obj.clone().unbind()))
    }

    fn to_python(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self {
            Plain::Null => Ok(py.None()),
            Plain::Bool(b) => (*b).into_py_any(py),
            Plain::Int(i) => (*i).into_py_any(py),
            Plain::Float(f) => (*f).into_py_any(py),
            Plain::Str(s) => s.clone().into_py_any(py),
            Plain::Bytes(b) => b.clone().into_py_any(py),
            Plain::Tuple(items) => {
                let objs = plain_objs(items, py)?;
                Ok(PyTuple::new(py, objs.iter().map(|o| o.bind(py)))?
                    .into_any()
                    .unbind())
            }
            Plain::List(items) => {
                let list = PyList::empty(py);
                for o in plain_objs(items, py)? {
                    list.append(o.bind(py))?;
                }
                Ok(list.into_any().unbind())
            }
            Plain::Set(items) => {
                let set = PySet::empty(py)?;
                for o in plain_objs(items, py)? {
                    set.add(o.bind(py))?;
                }
                Ok(set.into_any().unbind())
            }
            Plain::FrozenSet(items) => {
                let objs = plain_objs(items, py)?;
                Ok(PyFrozenSet::new(py, objs.iter().map(|o| o.bind(py)))?
                    .into_any()
                    .unbind())
            }
            Plain::Dict(items) => {
                let d = PyDict::new(py);
                for (k, v) in items {
                    d.set_item(k.to_python(py)?.bind(py), v.to_python(py)?.bind(py))?;
                }
                Ok(d.into_any().unbind())
            }
            Plain::Opaque(obj) => Ok(obj.clone_ref(py)),
        }
    }
}

/// Recurse a Python iterable (tuple/list/set/frozenset) into `Vec<Plain>`.
fn plain_children(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<Plain>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(Plain::from_python(py, &item?)?);
    }
    Ok(out)
}

/// Marshal every `Plain` element to a Python object.
fn plain_objs(items: &[Plain], py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
    items.iter().map(|p| p.to_python(py)).collect()
}

// ---------------------------------------------------------------------------
// Error helper
// ---------------------------------------------------------------------------

fn type_err(obj: &Bound<'_, PyAny>, want: &str, why: &str) -> PyErr {
    let got = obj
        .get_type()
        .getattr("__name__")
        .and_then(|n| n.extract::<String>())
        .unwrap_or_else(|_| "?".to_string());
    PyTypeError::new_err(format!("marshalling {want}: {why} (got {got})"))
}

// ---------------------------------------------------------------------------
// Round-trip gate harness (reusable: U1+ plug their types in via
// `crate::marshal::assert_roundtrip::<T>(py, "<python literal>")`)
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
fn eval<'py>(py: Python<'py>, expr: &str) -> Bound<'py, PyAny> {
    let cstr = std::ffi::CString::new(expr).expect("expr has no NUL byte");
    py.eval(cstr.as_c_str(), None, None).expect("eval failed")
}

#[cfg(test)]
fn gate_equal(a: &Bound<'_, PyAny>, b: &Bound<'_, PyAny>) -> PyResult<bool> {
    // `float('nan') == float('nan')` is False in CPython, but the round-trip
    // reproduced the same NaN bit pattern — treat two NaN floats as equal.
    if a.is_instance_of::<PyFloat>() && b.is_instance_of::<PyFloat>() {
        let af: f64 = a.extract()?;
        let bf: f64 = b.extract()?;
        if af.is_nan() && bf.is_nan() {
            return Ok(true);
        }
    }
    a.eq(b)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
/// Reusable round-trip gate: evaluate `expr` in Python, marshal it to `T` and
/// back, and assert bit-identity — exact type, identical `repr`, and
/// (NaN-aware) `==`. Panics with the expression and the mismatch on failure.
pub(crate) fn assert_roundtrip<T: Marshal>(py: Python<'_>, expr: &str) {
    let orig = eval(py, expr);
    let owned = to_owned::<T>(&orig).unwrap_or_else(|e| {
        panic!(
            "to_owned::<{}>({expr}) failed: {e}",
            std::any::type_name::<T>()
        )
    });
    let back = to_python::<T>(py, &owned).unwrap_or_else(|e| {
        panic!(
            "to_python::<{}>({expr}) failed: {e}",
            std::any::type_name::<T>()
        )
    });
    let back = back.bind(py);

    assert!(
        orig.get_type().is(back.get_type()),
        "type mismatch for {expr}: orig {orig:?}, back {back:?}"
    );
    let repr_orig = orig
        .repr()
        .expect("repr(orig)")
        .extract::<String>()
        .expect("repr str");
    let repr_back = back
        .repr()
        .expect("repr(back)")
        .extract::<String>()
        .expect("repr str");
    assert_eq!(repr_orig, repr_back, "repr mismatch for {expr}");
    let eq = gate_equal(&orig, back).expect("equality");
    assert!(
        eq,
        "not equal for {expr}: orig={repr_orig}, back={repr_back}"
    );
}

// ---------------------------------------------------------------------------
// Tests — the U0 losslessness proof
// ---------------------------------------------------------------------------

#[cfg(test)]
#[cfg(feature = "python")]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    // -- scalars -----------------------------------------------------------

    #[test]
    fn scalar_roundtrips_are_lossless() {
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip::<i64>(py, "0");
            assert_roundtrip::<i64>(py, "42");
            assert_roundtrip::<i64>(py, "-123456789");
            assert_roundtrip::<f64>(py, "3.14");
            assert_roundtrip::<f64>(py, "-0.0");
            assert_roundtrip::<f64>(py, "1e308");
            assert_roundtrip::<String>(py, "'hello'");
            assert_roundtrip::<String>(py, "''");
            assert_roundtrip::<bool>(py, "True");
            assert_roundtrip::<bool>(py, "False");
        });
    }

    #[test]
    fn nan_and_infinities_roundtrip_losslessly() {
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip::<f64>(py, "float('nan')");
            assert_roundtrip::<f64>(py, "float('inf')");
            assert_roundtrip::<f64>(py, "float('-inf')");
            assert_roundtrip::<Val>(py, "float('nan')");
        });
    }

    // -- the Val convention: int vs float is preserved, never widened -------

    #[test]
    fn val_preserves_int_vs_float() {
        Python::initialize();
        Python::attach(|py| {
            // int stays int, float stays float — the concrete-Python-type hazard.
            assert_roundtrip::<Val>(py, "7");
            assert_roundtrip::<Val>(py, "7.0");
            assert_roundtrip::<Val>(py, "-3");
            assert_roundtrip::<Val>(py, "-3.5");
            // Explicitly: `7` did NOT widen to `7.0` (repr '7' vs '7.0').
            let owned: Val = to_owned(&eval(py, "7")).unwrap();
            assert_eq!(owned, Val::Int(7));
            let owned: Val = to_owned(&eval(py, "7.0")).unwrap();
            assert_eq!(owned, Val::Float(7.0));
        });
    }

    #[test]
    fn component_bounds_preserve_int_vs_float() {
        // The netlist_contracts case: `Component("R1", "fp", (1, 2))` keeps
        // `int` bounds; `(1.0, 2.0)` keeps `float` bounds.
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip::<Plain>(py, "(1, 2)");
            assert_roundtrip::<Plain>(py, "(1.0, 2.0)");
            assert_roundtrip::<Vec<Val>>(py, "[1, 2]");
            assert_roundtrip::<Vec<Val>>(py, "[1.0, 2.0]");
        });
    }

    // -- containers ---------------------------------------------------------

    #[test]
    fn option_roundtrips_none_and_some() {
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip::<Option<i64>>(py, "None");
            assert_roundtrip::<Option<i64>>(py, "5");
            assert_roundtrip::<Option<Vec<String>>>(py, "['a', 'b']");
        });
    }

    #[test]
    fn plain_nested_collections_roundtrip_losslessly() {
        Python::initialize();
        Python::attach(|py| {
            assert_roundtrip::<Plain>(py, "[]");
            assert_roundtrip::<Plain>(py, "()");
            assert_roundtrip::<Plain>(py, "set()");
            assert_roundtrip::<Plain>(py, "frozenset()");
            assert_roundtrip::<Plain>(py, "{}");
            assert_roundtrip::<Plain>(py, "[1, 2.5, 'three']");
            assert_roundtrip::<Plain>(py, "(1, (2, 3), [4, 5])");
            assert_roundtrip::<Plain>(py, "{'a': 1, 'b': [2, 3], 'c': {'d': 4}}");
            assert_roundtrip::<Plain>(py, "frozenset({1, 2, 3})");
            assert_roundtrip::<Plain>(py, "b'\\x00\\xffbytes'");
            assert_roundtrip::<Plain>(
                py,
                "{'ints': (1, 2), 'floats': (1.0, 2.0), 'mixed': [1, 'x', None, True, 2.5], \
                 'fs': frozenset({(1, 2), (3, 4)}), 'empty': {}}",
            );
        });
    }

    // -- keeps: opaque passthrough ------------------------------------------

    #[test]
    fn opaque_values_pass_through_by_identity() {
        Python::initialize();
        Python::attach(|py| {
            // An object with no owned representation (a duck-typed instance,
            // standing in for numpy/shapely/foreign pyclasses) round-trips as
            // the SAME object — identity preserved, nothing reconstructed.
            let orig = eval(py, "object()");
            let owned: Plain = to_owned(&orig).unwrap();
            assert!(matches!(owned, Plain::Opaque(_)));
            let back = to_python(py, &owned).unwrap();
            assert!(
                orig.is(back.bind(py)),
                "opaque must pass through by identity"
            );
        });
    }

    // -- guards: the sibling numeric type is rejected, not widened -----------

    #[test]
    fn scalar_impls_reject_the_sibling_numeric_type() {
        Python::initialize();
        Python::attach(|py| {
            assert!(
                to_owned::<f64>(&eval(py, "1")).is_err(),
                "int must not widen to f64"
            );
            assert!(
                to_owned::<i64>(&eval(py, "1.5")).is_err(),
                "float must not truncate to i64"
            );
            assert!(
                to_owned::<i64>(&eval(py, "True")).is_err(),
                "bool must not coerce to int"
            );
            assert!(
                to_owned::<Val>(&eval(py, "True")).is_err(),
                "bool must not coerce to Val"
            );
            assert!(
                to_owned::<Val>(&eval(py, "'x'")).is_err(),
                "str must not coerce to Val"
            );
            assert!(
                to_owned::<Vec<i64>>(&eval(py, "(1, 2)")).is_err(),
                "tuple must not coerce to Vec"
            );
        });
    }

    // -- minimal end-to-end proof on a real BoardState field -----------------

    #[test]
    fn end_to_end_placements_field_via_getattr() {
        // `BoardState.placements` is a `frozenset` of `(ref, (x, y))` tuples
        // (see component_assignment_stage.rs and deterministic/state.py). Read
        // it via getattr exactly as a U1+ stage will, marshal to `Plain`, and
        // round-trip bit-identically.
        Python::initialize();
        Python::attach(|py| {
            let state = eval(
                py,
                "type('S', (), {'placements': frozenset({('U1', (10.0, 20.0)), ('R1', (5.5, 7.25))})})()",
            );
            let placements = state.getattr("placements").unwrap();
            let owned: Plain = to_owned(&placements).unwrap();
            assert!(matches!(owned, Plain::FrozenSet(_)));
            let back = to_python(py, &owned).unwrap();
            let back = back.bind(py);
            assert!(placements.get_type().is(back.get_type()), "placements type");
            let rp = placements.repr().unwrap().extract::<String>().unwrap();
            let rb = back.repr().unwrap().extract::<String>().unwrap();
            assert_eq!(rp, rb, "placements repr");
            assert!(gate_equal(&placements, back).unwrap(), "placements eq");
        });
    }

    #[test]
    fn end_to_end_used_slots_field_via_getattr() {
        // `BoardState.used_slots` is a `frozenset` of integer slot ids (tuples
        // of ints). Same getattr -> marshal -> round-trip proof, plus the
        // int-vs-float distinction survives inside the frozenset.
        Python::initialize();
        Python::attach(|py| {
            let state = eval(
                py,
                "type('S', (), {'used_slots': frozenset({(0, 1), (2, 3), (1, 0)})})()",
            );
            let slots = state.getattr("used_slots").unwrap();
            assert_roundtrip::<Plain>(py, "frozenset({(0, 1), (2, 3), (1, 0)})");
            // The float-shaped variant round-trips floats, not ints.
            assert_roundtrip::<Plain>(py, "frozenset({(0.0, 1.0), (2.0, 3.0)})");
            let owned: Plain = to_owned(&slots).unwrap();
            assert!(matches!(owned, Plain::FrozenSet(_)));
        });
    }
}

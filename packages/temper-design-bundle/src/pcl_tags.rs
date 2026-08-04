//! PCL tag hierarchy and tag-expression algebra — Wave 4 Phase 2.
//!
//! Python reference: `temper_placer/pcl/tag_dispatch.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/pcl/_tag_dispatch_py_oracle.py` (commit
//! `5a17025b1`). The differential
//! `packages/temper-placer/tests/pcl/test_tag_dispatch_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! # What moved and why
//!
//! The five tag-expression node types (`TagRef`, `TagAnd`, `TagOr`,
//! `TagNot`, `ComponentRef`) are the objects `resolve()` walks once per
//! component per constraint — the marshalling cost Phase 2 exists to remove.
//! They are now pyo3 `#[pyclass(frozen)]` contract types, so an expression
//! tree built once in Python is walked entirely in Rust for the whole
//! netlist sweep.
//!
//! `ComponentTag` deliberately stays a Python `enum.Enum`. Production code
//! does `for t in ComponentTag` (`_tag_parser.py`) and `ComponentTag(value)`;
//! a pyo3 `#[pyclass]` enum can support neither (class-level iteration needs
//! a metaclass hook pyo3 does not expose — the deviation the `priority`
//! migration had to document). Migrating it would be a public API change, so
//! it does not move. Rust holds the tags as a `u8` lattice internally and
//! hands back the live Python singletons at the boundary.
//!
//! # Frozen-dataclass fidelity
//!
//! The pre-migration nodes were `@dataclass(frozen=True)`. Everything that
//! made observable is reproduced here and asserted by the differential:
//!
//! | behaviour            | how it is reproduced                              |
//! |----------------------|---------------------------------------------------|
//! | `__repr__`           | `Name(field=<repr of field>)`, via Python `repr()` |
//! | `__eq__`             | exact-type check, then per-field Python `==`       |
//! | `__hash__`           | `hash()` of a real Python tuple of the fields      |
//! | `__setattr__`        | raises `dataclasses.FrozenInstanceError`           |
//! | `copy.deepcopy`      | `__reduce__` -> `(cls, (fields...))`               |
//! | `pickle`             | same `__reduce__`                                  |
//! | `__match_args__`     | class attribute, same field order                  |
//!
//! `__hash__` is computed by handing CPython a real tuple rather than
//! replicating its xxPRIME mixing: identical by construction, and it keeps
//! working if CPython changes the algorithm. The *value* is not stable
//! across processes anyway — `hash(TagRef(ComponentTag.POWER))` depends on
//! `id(ComponentTag.POWER)` — which is exactly why only the *equal-implies-
//! equal-hash* invariant is asserted, never a literal.
//!
//! One recorded deviation: `dataclasses.fields()` no longer works on these
//! types (they are not dataclasses any more). No in-repo consumer calls it —
//! verified by grep across `src/`, `tests/` and `scripts/` — and it is
//! recorded in this crate's `VERIFICATION.md`.
//!
//! # Iteration order
//!
//! Two places in the reference read a `set`, whose iteration order is
//! `PYTHONHASHSEED`-dependent:
//!
//! * `resolve()`'s `for ct_str in comp.tags` loop. The loop body has no side
//!   effects and returns `True` on the first match, so the *result* is
//!   `True` iff some tag matches — order-invariant. Proven by induction in
//!   `VERIFICATION.md` and exercised by `test_resolve_is_hash_seed_invariant`.
//! * `_check_overconstrained`'s `set(adjacency) & set(separation)`. Here
//!   order IS observable: the function raises on the first offending pair, so
//!   which *message* you get depends on the seed. This port does not sort
//!   (that would be an undetectable behaviour change); it builds the very
//!   same CPython `set` objects and iterates them through CPython, so the
//!   live order is passed through rather than replicated.

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyAnyMethods, PyDict, PyFrozenSet, PySet, PyString, PyTuple, PyType};

// ---------------------------------------------------------------------------
// The 14-tag lattice, mirrored from the Python declaration order.
// ---------------------------------------------------------------------------

/// Tag names in *declaration order*. `_compute_transitive_closure` builds its
/// index map from `list(ComponentTag)`, so this order is load-bearing for the
/// Floyd-Warshall index arithmetic even though the final result is a set.
const TAG_NAMES: [&str; 14] = [
    "ALL",
    "POWER",
    "SIGNAL",
    "MECHANICAL",
    "HV",
    "LV",
    "GATE_DRIVE",
    "SENSOR",
    "MCU",
    "CONNECTOR",
    "MOUNTING",
    "THERMAL",
    "DECOUPLING",
    "FERRITE",
];

/// Lower-case enum *values*, index-aligned with [`TAG_NAMES`].
const TAG_VALUES: [&str; 14] = [
    "all",
    "power",
    "signal",
    "mechanical",
    "hv",
    "lv",
    "gate_drive",
    "sensor",
    "mcu",
    "connector",
    "mounting",
    "thermal",
    "decoupling",
    "ferrite",
];

/// Direct parents, index-aligned with [`TAG_NAMES`]. `ALL` has none.
const TAG_PARENTS: [&[usize]; 14] = [
    &[],  // ALL
    &[0], // POWER      -> ALL
    &[0], // SIGNAL     -> ALL
    &[0], // MECHANICAL -> ALL
    &[1], // HV         -> POWER
    &[1], // LV         -> POWER
    &[2], // GATE_DRIVE -> SIGNAL
    &[2], // SENSOR     -> SIGNAL
    &[2], // MCU        -> SIGNAL
    &[3], // CONNECTOR  -> MECHANICAL
    &[3], // MOUNTING   -> MECHANICAL
    &[3], // THERMAL    -> MECHANICAL
    &[1], // DECOUPLING -> POWER
    &[1], // FERRITE    -> POWER
];

/// Floyd-Warshall transitive closure as a bitmask per tag (bit `j` set means
/// tag `j` is an ancestor of tag `i`, including `i` itself).
///
/// This is the same triple loop the Python runs, kept in the same `k, i, j`
/// order so the *algorithm* is ported rather than replaced by a
/// reachability shortcut — a reviewer can diff it line for line.
fn compute_closure() -> [u16; 14] {
    let n = TAG_NAMES.len();
    let mut closure = [0u16; 14];
    for (i, parents) in TAG_PARENTS.iter().enumerate() {
        closure[i] |= 1 << i;
        for &j in parents.iter() {
            closure[i] |= 1 << j;
        }
    }
    for k in 0..n {
        for i in 0..n {
            for j in 0..n {
                if closure[i] & (1 << k) != 0 && closure[k] & (1 << j) != 0 {
                    closure[i] |= 1 << j;
                }
            }
        }
    }
    closure
}

static CLOSURE: std::sync::OnceLock<[u16; 14]> = std::sync::OnceLock::new();

fn closure() -> &'static [u16; 14] {
    CLOSURE.get_or_init(compute_closure)
}

/// `a <= b` in the tag partial order: true iff `b` is an ancestor of `a`.
fn tag_le_idx(a: usize, b: usize) -> bool {
    closure()[a] & (1 << b) != 0
}

fn tag_index_by_value(value: &str) -> Option<usize> {
    TAG_VALUES.iter().position(|v| *v == value)
}

// ---------------------------------------------------------------------------
// Cached Python handles.
// ---------------------------------------------------------------------------

struct TagTypes {
    component_tag: Py<PyAny>,
    frozen_instance_error: Py<PyAny>,
    validation_error: Py<PyAny>,
}

static TAG_TYPES: PyOnceLock<TagTypes> = PyOnceLock::new();

fn tag_types(py: Python<'_>) -> PyResult<&'static TagTypes> {
    TAG_TYPES.get_or_try_init(py, || {
        let dispatch = py.import("temper_placer.pcl.tag_dispatch")?;
        let dataclasses = py.import("dataclasses")?;
        Ok(TagTypes {
            component_tag: dispatch.getattr("ComponentTag")?.unbind(),
            frozen_instance_error: dataclasses.getattr("FrozenInstanceError")?.unbind(),
            validation_error: dispatch.getattr("TagValidationError")?.unbind(),
        })
    })
}

/// Resolve a Python object to a tag index, but ONLY if it really is a
/// `ComponentTag` member. Anything else returns `None` so the caller can fall
/// back to Python semantics (including raising the same `TypeError`).
fn component_tag_index(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Option<usize>> {
    let types = tag_types(py)?;
    if !obj.is_instance(types.component_tag.bind(py))? {
        return Ok(None);
    }
    let value: String = obj.getattr("value")?.extract()?;
    Ok(tag_index_by_value(&value))
}

fn component_tag_member(py: Python<'_>, idx: usize) -> PyResult<Py<PyAny>> {
    let types = tag_types(py)?;
    Ok(types
        .component_tag
        .bind(py)
        .getattr(TAG_NAMES[idx])?
        .unbind())
}

/// Reproduce `dataclasses.FrozenInstanceError` exactly, including its two
/// message forms: CPython emits "cannot assign to field 'x'" from
/// `__setattr__` and "cannot delete field 'x'" from `__delattr__`.
fn frozen_error(py: Python<'_>, cls: &str, verb: &str, name: &str) -> PyErr {
    let msg = format!("cannot {verb} field '{name}'");
    match tag_types(py) {
        Ok(t) => match t.frozen_instance_error.bind(py).call1((msg,)) {
            Ok(exc) => PyErr::from_value(exc),
            Err(e) => e,
        },
        Err(_) => PyTypeError::new_err(format!("{cls} is frozen")),
    }
}

fn validation_error(py: Python<'_>, msg: String) -> PyErr {
    match tag_types(py) {
        Ok(t) => match t.validation_error.bind(py).call1((msg,)) {
            Ok(exc) => PyErr::from_value(exc),
            Err(e) => e,
        },
        Err(e) => e,
    }
}

/// `hash(tuple(fields))` — CPython's own tuple hash, not a replica.
fn tuple_hash(py: Python<'_>, fields: Vec<Py<PyAny>>) -> PyResult<isize> {
    PyTuple::new(py, fields)?.hash()
}

// ---------------------------------------------------------------------------
// The five contract pyclasses.
// ---------------------------------------------------------------------------

/// Reference to a single component tag in a tag expression.
#[pyclass(frozen, module = "temper_placer.pcl.tag_dispatch")]
#[derive(Debug)]
pub struct TagRef {
    tag: Py<PyAny>,
    /// Lattice index, present only when `tag` really is a `ComponentTag`.
    /// `None` keeps the Python fallback path (and its `TypeError`) reachable
    /// for the duck-typed values the dataclass never rejected.
    idx: Option<usize>,
}

#[pymethods]
impl TagRef {
    #[new]
    fn new(py: Python<'_>, tag: Bound<'_, PyAny>) -> PyResult<Self> {
        let idx = component_tag_index(py, &tag)?;
        Ok(Self {
            tag: tag.unbind(),
            idx,
        })
    }

    #[getter]
    fn tag(&self, py: Python<'_>) -> Py<PyAny> {
        self.tag.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("TagRef(tag={})", self.tag.bind(py).repr()?))
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<TagRef>() else {
            return Ok(false);
        };
        self.tag.bind(py).eq(other.get().tag.bind(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, vec![self.tag.clone_ref(py)])
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "TagRef", "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "TagRef", "delete", name))
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        let cls = PyType::new::<TagRef>(py).into_any().unbind();
        let args = PyTuple::new(py, [self.tag.clone_ref(py)])?
            .into_any()
            .unbind();
        Ok((cls, args))
    }

    #[classattr]
    fn __match_args__() -> (&'static str,) {
        ("tag",)
    }
}

macro_rules! binary_node {
    ($name:ident, $lit:literal, $a:ident, $b:ident) => {
        #[pyclass(frozen, module = "temper_placer.pcl.tag_dispatch")]
        #[derive(Debug)]
        pub struct $name {
            $a: Py<PyAny>,
            $b: Py<PyAny>,
        }

        #[pymethods]
        impl $name {
            #[new]
            fn new($a: Bound<'_, PyAny>, $b: Bound<'_, PyAny>) -> Self {
                Self {
                    $a: $a.unbind(),
                    $b: $b.unbind(),
                }
            }

            #[getter]
            fn $a(&self, py: Python<'_>) -> Py<PyAny> {
                self.$a.clone_ref(py)
            }

            #[getter]
            fn $b(&self, py: Python<'_>) -> Py<PyAny> {
                self.$b.clone_ref(py)
            }

            fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
                Ok(format!(
                    concat!($lit, "(", stringify!($a), "={}, ", stringify!($b), "={})"),
                    self.$a.bind(py).repr()?,
                    self.$b.bind(py).repr()?
                ))
            }

            fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
                let Ok(other) = other.cast::<$name>() else {
                    return Ok(false);
                };
                let other = other.get();
                Ok(self.$a.bind(py).eq(other.$a.bind(py))?
                    && self.$b.bind(py).eq(other.$b.bind(py))?)
            }

            fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
                Ok(!self.__eq__(py, other)?)
            }

            fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
                tuple_hash(py, vec![self.$a.clone_ref(py), self.$b.clone_ref(py)])
            }

            fn __setattr__(
                &self,
                py: Python<'_>,
                name: &str,
                _value: Bound<'_, PyAny>,
            ) -> PyResult<()> {
                Err(frozen_error(py, $lit, "assign to", name))
            }

            fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
                Err(frozen_error(py, $lit, "delete", name))
            }

            fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
                let cls = PyType::new::<$name>(py).into_any().unbind();
                let args = PyTuple::new(py, [self.$a.clone_ref(py), self.$b.clone_ref(py)])?
                    .into_any()
                    .unbind();
                Ok((cls, args))
            }

            #[classattr]
            fn __match_args__() -> (&'static str, &'static str) {
                (stringify!($a), stringify!($b))
            }
        }
    };
}

binary_node!(TagAnd, "TagAnd", left, right);
binary_node!(TagOr, "TagOr", left, right);

/// Logical NOT of a tag expression.
#[pyclass(frozen, module = "temper_placer.pcl.tag_dispatch")]
#[derive(Debug)]
pub struct TagNot {
    expr: Py<PyAny>,
}

#[pymethods]
impl TagNot {
    #[new]
    fn new(expr: Bound<'_, PyAny>) -> Self {
        Self {
            expr: expr.unbind(),
        }
    }

    #[getter]
    fn expr(&self, py: Python<'_>) -> Py<PyAny> {
        self.expr.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("TagNot(expr={})", self.expr.bind(py).repr()?))
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<TagNot>() else {
            return Ok(false);
        };
        self.expr.bind(py).eq(other.get().expr.bind(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, vec![self.expr.clone_ref(py)])
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "TagNot", "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "TagNot", "delete", name))
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        let cls = PyType::new::<TagNot>(py).into_any().unbind();
        let args = PyTuple::new(py, [self.expr.clone_ref(py)])?
            .into_any()
            .unbind();
        Ok((cls, args))
    }

    #[classattr]
    fn __match_args__() -> (&'static str,) {
        ("expr",)
    }
}

/// Reference to a specific component by refdes.
#[pyclass(frozen, module = "temper_placer.pcl.tag_dispatch")]
#[derive(Debug)]
pub struct ComponentRef {
    r#ref: Py<PyAny>,
}

#[pymethods]
impl ComponentRef {
    #[new]
    fn new(r#ref: Bound<'_, PyAny>) -> Self {
        Self {
            r#ref: r#ref.unbind(),
        }
    }

    #[getter]
    fn r#ref(&self, py: Python<'_>) -> Py<PyAny> {
        self.r#ref.clone_ref(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!("ComponentRef(ref={})", self.r#ref.bind(py).repr()?))
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<ComponentRef>() else {
            return Ok(false);
        };
        self.r#ref.bind(py).eq(other.get().r#ref.bind(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, vec![self.r#ref.clone_ref(py)])
    }

    fn __setattr__(&self, py: Python<'_>, name: &str, _value: Bound<'_, PyAny>) -> PyResult<()> {
        Err(frozen_error(py, "ComponentRef", "assign to", name))
    }

    fn __delattr__(&self, py: Python<'_>, name: &str) -> PyResult<()> {
        Err(frozen_error(py, "ComponentRef", "delete", name))
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        let cls = PyType::new::<ComponentRef>(py).into_any().unbind();
        let args = PyTuple::new(py, [self.r#ref.clone_ref(py)])?
            .into_any()
            .unbind();
        Ok((cls, args))
    }

    #[classattr]
    fn __match_args__() -> (&'static str,) {
        ("ref",)
    }
}

// ---------------------------------------------------------------------------
// Closure + ordering, exposed to Python.
// ---------------------------------------------------------------------------

/// Build `_TAG_CLOSURE`: `dict[ComponentTag, frozenset[ComponentTag]]`.
///
/// Insertion order matches the Python's `for tag, i in idx_map.items()`,
/// which iterates `list(ComponentTag)` order — so the dict compares equal
/// *and* iterates identically.
#[pyfunction]
#[pyo3(name = "pcl_tag_closure")]
// The index IS the domain object here: `i` and `j` address TAG_NAMES, the
// closure bitmask, and the Python enum member simultaneously, exactly as the
// reference's `idx_map` does. Iterating one of those arrays and recovering
// the index would obscure the correspondence this port is trying to keep
// diffable against the Python.
#[allow(clippy::needless_range_loop)]
pub fn tag_closure(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let out = PyDict::new(py);
    let table = closure();
    for i in 0..TAG_NAMES.len() {
        let mut members: Vec<Py<PyAny>> = Vec::new();
        for j in 0..TAG_NAMES.len() {
            if table[i] & (1 << j) != 0 {
                members.push(component_tag_member(py, j)?);
            }
        }
        out.set_item(
            component_tag_member(py, i)?,
            PyFrozenSet::new(py, members.iter())?,
        )?;
    }
    Ok(out.unbind())
}

/// `ComponentTag.__le__`: "self is more specific than or equal to other".
///
/// Returns `NotImplemented` for a non-`ComponentTag` right-hand side, exactly
/// as the Python does — which is what makes `ComponentTag.HV <= 'power'`
/// raise `TypeError` rather than quietly answering `False`.
#[pyfunction]
#[pyo3(name = "pcl_tag_le")]
pub fn tag_le<'py>(
    py: Python<'py>,
    this: &Bound<'py, PyAny>,
    other: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(other_idx) = component_tag_index(py, other)? else {
        return Ok(py.NotImplemented().into_bound(py));
    };
    let Some(this_idx) = component_tag_index(py, this)? else {
        // `self` is always a ComponentTag when Python dispatches __le__, but
        // an explicit call could pass anything; mirror the reference, which
        // would raise AttributeError inside `_TAG_CLOSURE.get(self, ...)`
        // only for unhashable input and otherwise return False.
        return Ok(pyo3::types::PyBool::new(py, false).to_owned().into_any());
    };
    Ok(
        pyo3::types::PyBool::new(py, tag_le_idx(this_idx, other_idx))
            .to_owned()
            .into_any(),
    )
}

// ---------------------------------------------------------------------------
// resolve / components
// ---------------------------------------------------------------------------

/// Walk a tag expression against one component.
///
/// Structural recursion on the expression tree; every branch mirrors the
/// reference's `isinstance` chain in the same order, and the final
/// `return False` for an unrecognised node type is preserved (the reference
/// does not raise on a foreign node — it answers `False`).
fn resolve_inner(
    py: Python<'_>,
    expr: &Bound<'_, PyAny>,
    comp: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    if let Ok(node) = expr.cast::<TagRef>() {
        let node = node.get();
        let tag = node.tag.bind(py);
        // `comp_tags_upper = {t.upper() for t in comp.tags}` then a direct
        // membership test on `expr.tag.value.upper()`.
        let tag_value = tag.getattr("value")?;
        let tag_upper: String = crate::pcl_parse::py_upper(py, &tag_value.extract::<String>()?)?;
        let tags = comp.getattr("tags")?;

        let mut raw_tags: Vec<String> = Vec::new();
        for item in tags.try_iter()? {
            let item = item?;
            let s: String = item.extract()?;
            raw_tags.push(s);
        }
        // Uppercase comparison first — a plain set-membership test, so the
        // frozenset's iteration order cannot affect it. `py_upper` is
        // CPython's casing for non-ASCII and a local fast path for ASCII, so
        // this loop costs no FFI on the overwhelmingly common refdes/tag
        // alphabet.
        for t in &raw_tags {
            if crate::pcl_parse::py_upper(py, t)? == tag_upper {
                return Ok(true);
            }
        }
        // Then the hierarchy walk. `for ct_str in comp.tags` reads the
        // frozenset in hash order, but the body only ever returns True, so
        // the answer is "does ANY tag sit under expr.tag" — order-invariant.
        for t in &raw_tags {
            let lowered = crate::pcl_parse::py_lower(py, t)?;
            let Some(ct_idx) = tag_index_by_value(&lowered) else {
                continue; // ComponentTag(ct_str) raised ValueError
            };
            match node.idx {
                Some(tag_idx) => {
                    if tag_le_idx(ct_idx, tag_idx) {
                        return Ok(true);
                    }
                }
                None => {
                    // `expr.tag` is not a ComponentTag: `ct <= expr.tag`
                    // returns NotImplemented and Python raises TypeError.
                    // Delegate so the error text is CPython's, verbatim.
                    let ct = component_tag_member(py, ct_idx)?;
                    let res = ct.bind(py).le(tag)?;
                    if res {
                        return Ok(true);
                    }
                }
            }
        }
        return Ok(false);
    }
    if let Ok(node) = expr.cast::<TagAnd>() {
        let node = node.get();
        return Ok(resolve_inner(py, node.left.bind(py), comp)?
            && resolve_inner(py, node.right.bind(py), comp)?);
    }
    if let Ok(node) = expr.cast::<TagOr>() {
        let node = node.get();
        return Ok(resolve_inner(py, node.left.bind(py), comp)?
            || resolve_inner(py, node.right.bind(py), comp)?);
    }
    if let Ok(node) = expr.cast::<TagNot>() {
        let node = node.get();
        return Ok(!resolve_inner(py, node.expr.bind(py), comp)?);
    }
    if let Ok(node) = expr.cast::<ComponentRef>() {
        let node = node.get();
        return comp.getattr("ref")?.eq(node.r#ref.bind(py));
    }
    Ok(false)
}

/// Resolve a tag expression against a component.
#[pyfunction]
#[pyo3(name = "pcl_resolve")]
pub fn resolve(py: Python<'_>, expr: &Bound<'_, PyAny>, comp: &Bound<'_, PyAny>) -> PyResult<bool> {
    resolve_inner(py, expr, comp)
}

/// All components in a netlist matching a tag expression, order preserved.
///
/// This is the call the Phase-2 pivot is for: the expression tree is already
/// in Rust, so the whole sweep runs without re-marshalling it per component.
#[pyfunction]
#[pyo3(name = "pcl_components")]
pub fn components<'py>(
    py: Python<'py>,
    expr: &Bound<'py, PyAny>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Vec<Py<PyAny>>> {
    let comps = netlist.getattr("components")?;
    let mut out = Vec::new();
    for comp in comps.try_iter()? {
        let comp = comp?;
        if resolve_inner(py, expr, &comp)? {
            out.push(comp.unbind());
        }
    }
    Ok(out)
}

/// Refdes of every component matching a tag expression.
#[pyfunction]
#[pyo3(name = "pcl_tag_to_component_refs")]
pub fn tag_to_component_refs<'py>(
    py: Python<'py>,
    expr: &Bound<'py, PyAny>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Vec<Py<PyAny>>> {
    let comps = netlist.getattr("components")?;
    let mut out = Vec::new();
    for comp in comps.try_iter()? {
        let comp = comp?;
        if resolve_inner(py, expr, &comp)? {
            out.push(comp.getattr("ref")?.unbind());
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// _check_overconstrained
// ---------------------------------------------------------------------------

struct Entry {
    ty: String,
    id: String,
    dist: f64,
}

/// Detect contradictory adjacency/separation pairs produced by tag expansion.
///
/// Order note (the trap this port is most careful about): the reference
/// iterates `set(adjacency.keys()) & set(separation.keys())` and raises on
/// the first contradiction, so *which* message you get is
/// `PYTHONHASHSEED`-dependent. Sorting the keys would make the port
/// deterministic and therefore **different** — an undetectable behaviour
/// change. Instead the same CPython `set` objects are constructed here and
/// the intersection is iterated through CPython, so the live order is passed
/// through unchanged.
#[pyfunction]
#[pyo3(name = "pcl_check_overconstrained")]
pub fn check_overconstrained(py: Python<'_>, expanded: &Bound<'_, PyAny>) -> PyResult<()> {
    // Insertion-ordered maps, mirroring the Python dicts.
    let mut adjacency: Vec<((String, String), Vec<Entry>)> = Vec::new();
    let mut separation: Vec<((String, String), Vec<Entry>)> = Vec::new();

    for entry in expanded.try_iter()? {
        let entry = entry?;
        let tc = entry.get_item(0)?;
        let len = entry.len()?;
        let tc_type_obj = if len > 2 {
            entry.get_item(2)?
        } else {
            match tc.getattr("constraint_type") {
                Ok(v) => v,
                Err(_) => PyString::new(py, "unknown").into_any(),
            }
        };

        let has_a = tc.hasattr("a")?;
        let has_b = tc.hasattr("b")?;
        if !(has_a && has_b) {
            continue;
        }

        // `key = tuple(sorted([tc.a, tc.b]))`. Python sorts str by code
        // point; Rust's `str: Ord` sorts by UTF-8 bytes, and UTF-8 preserves
        // code-point order — so the two orderings agree on every input.
        let a: String = tc.getattr("a")?.extract()?;
        let b: String = tc.getattr("b")?.extract()?;
        let key = if a <= b {
            (a.clone(), b.clone())
        } else {
            (b.clone(), a.clone())
        };

        let ty: String = tc_type_obj.str()?.extract()?;
        let id: String = match tc.getattr("id") {
            Ok(v) => v.extract().unwrap_or_default(),
            Err(_) => String::new(),
        };

        // The reference uses `if hasattr(max) ... elif hasattr(min)`, so a
        // constraint carrying BOTH lands in adjacency only.
        if tc.hasattr("max_distance_mm")? {
            let dist: f64 = tc.getattr("max_distance_mm")?.extract()?;
            push_entry(&mut adjacency, key, Entry { ty, id, dist });
        } else if tc.hasattr("min_distance_mm")? {
            let dist: f64 = tc.getattr("min_distance_mm")?.extract()?;
            push_entry(&mut separation, key, Entry { ty, id, dist });
        }
    }

    // Build the real CPython sets and intersect them, so the iteration order
    // below is CPython's own, for this process, with this hash seed.
    let adj_set = PySet::empty(py)?;
    for (key, _) in &adjacency {
        adj_set.add((key.0.as_str(), key.1.as_str()))?;
    }
    let sep_set = PySet::empty(py)?;
    for (key, _) in &separation {
        sep_set.add((key.0.as_str(), key.1.as_str()))?;
    }
    let intersection = adj_set.call_method1("__and__", (&sep_set,))?;

    for key_obj in intersection.try_iter()? {
        let key_obj = key_obj?;
        let k0: String = key_obj.get_item(0)?.extract()?;
        let k1: String = key_obj.get_item(1)?.extract()?;
        let key = (k0, k1);
        let (Some(adj_entries), Some(sep_entries)) =
            (lookup(&adjacency, &key), lookup(&separation, &key))
        else {
            continue;
        };
        // itertools.product(adj, sep): adjacency is the OUTER loop.
        for a in adj_entries {
            for s in sep_entries {
                if s.dist > a.dist {
                    return Err(validation_error(
                        py,
                        format!(
                            "Overconstrained: components '{}' and '{}' from tags \
                             [{}:{}] must be \u{2264}{:.1}mm but \
                             [{}:{}] requires \u{2265}{:.1}mm",
                            key.0, key.1, a.ty, a.id, a.dist, s.ty, s.id, s.dist
                        ),
                    ));
                }
            }
        }
    }
    Ok(())
}

fn push_entry(map: &mut Vec<((String, String), Vec<Entry>)>, key: (String, String), entry: Entry) {
    if let Some(slot) = map.iter_mut().find(|(k, _)| *k == key) {
        slot.1.push(entry);
    } else {
        map.push((key, vec![entry]));
    }
}

fn lookup<'a>(
    map: &'a [((String, String), Vec<Entry>)],
    key: &(String, String),
) -> Option<&'a Vec<Entry>> {
    map.iter().find(|(k, _)| k == key).map(|(_, v)| v)
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<TagRef>()?;
    module.add_class::<TagAnd>()?;
    module.add_class::<TagOr>()?;
    module.add_class::<TagNot>()?;
    module.add_class::<ComponentRef>()?;
    module.add_function(wrap_pyfunction!(tag_closure, module)?)?;
    module.add_function(wrap_pyfunction!(tag_le, module)?)?;
    module.add_function(wrap_pyfunction!(resolve, module)?)?;
    module.add_function(wrap_pyfunction!(components, module)?)?;
    module.add_function(wrap_pyfunction!(tag_to_component_refs, module)?)?;
    module.add_function(wrap_pyfunction!(check_overconstrained, module)?)?;
    Ok(())
}

#[cfg(test)]
// Same reasoning as `tag_closure`: these are lattice proofs stated over tag
// INDICES, and the index is what `tag_le_idx` takes.
#[allow(clippy::needless_range_loop)]
mod tests {
    use super::*;

    fn idx(value: &str) -> usize {
        match tag_index_by_value(value) {
            Some(i) => i,
            None => panic!("unknown tag {value}"),
        }
    }

    #[test]
    fn closure_is_reflexive() {
        for i in 0..TAG_NAMES.len() {
            assert!(tag_le_idx(i, i), "{} not <= itself", TAG_NAMES[i]);
        }
    }

    #[test]
    fn closure_is_transitive() {
        let n = TAG_NAMES.len();
        for a in 0..n {
            for b in 0..n {
                for c in 0..n {
                    if tag_le_idx(a, b) && tag_le_idx(b, c) {
                        assert!(
                            tag_le_idx(a, c),
                            "{} <= {} <= {} but not {} <= {}",
                            TAG_NAMES[a],
                            TAG_NAMES[b],
                            TAG_NAMES[c],
                            TAG_NAMES[a],
                            TAG_NAMES[c]
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn closure_is_antisymmetric_so_the_order_is_partial_not_merely_a_preorder() {
        let n = TAG_NAMES.len();
        for a in 0..n {
            for b in 0..n {
                if a != b {
                    assert!(
                        !(tag_le_idx(a, b) && tag_le_idx(b, a)),
                        "{} and {} are mutually <=",
                        TAG_NAMES[a],
                        TAG_NAMES[b]
                    );
                }
            }
        }
    }

    #[test]
    fn every_tag_reaches_all_and_all_reaches_only_itself() {
        let all = idx("all");
        for i in 0..TAG_NAMES.len() {
            assert!(tag_le_idx(i, all), "{} does not reach ALL", TAG_NAMES[i]);
        }
        for i in 0..TAG_NAMES.len() {
            if i != all {
                assert!(!tag_le_idx(all, i), "ALL reaches {}", TAG_NAMES[i]);
            }
        }
    }

    #[test]
    fn specific_ancestries_match_the_declared_hierarchy() {
        assert!(tag_le_idx(idx("hv"), idx("power")));
        assert!(!tag_le_idx(idx("power"), idx("hv")));
        assert!(tag_le_idx(idx("decoupling"), idx("power")));
        assert!(tag_le_idx(idx("gate_drive"), idx("signal")));
        assert!(!tag_le_idx(idx("gate_drive"), idx("power")));
        assert!(tag_le_idx(idx("connector"), idx("mechanical")));
        assert!(!tag_le_idx(idx("connector"), idx("signal")));
    }

    #[test]
    fn closure_of_a_leaf_is_exactly_leaf_parent_all() {
        // HV -> {HV, POWER, ALL}: three bits, no more.
        let hv = closure()[idx("hv")];
        assert_eq!(hv.count_ones(), 3);
        assert!(hv & (1 << idx("hv")) != 0);
        assert!(hv & (1 << idx("power")) != 0);
        assert!(hv & (1 << idx("all")) != 0);
    }

    #[test]
    fn names_and_values_stay_index_aligned() {
        assert_eq!(TAG_NAMES.len(), TAG_VALUES.len());
        assert_eq!(TAG_NAMES.len(), TAG_PARENTS.len());
        for (i, name) in TAG_NAMES.iter().enumerate() {
            assert_eq!(name.to_lowercase(), TAG_VALUES[i]);
        }
    }
}

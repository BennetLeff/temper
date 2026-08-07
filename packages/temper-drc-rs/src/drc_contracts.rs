//! Wave 4 **Phase 2** contracts — drc_types / drc_result as pyo3 pyclasses.
//!
//! Python references: `temper_placer/validation/drc_types.py` and
//! `temper_placer/validation/drc_result.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/validation/_drc_types_py_oracle.py` and
//! `_drc_result_py_oracle.py` (commit `17553437d`). The differential test
//! `packages/temper-placer/tests/validation/test_drc_contracts_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! The pre-migration contracts are **plain `@dataclass`es**, and a dataclass
//! performs *no* coercion in `__init__`: `Location(1, 2)` stores `int`
//! coordinates, and `Location.x` then returns `int` `1`, not `1.0` — the
//! report surface depends on that (`Board Size: {placement.board_width}mm`
//! renders `100` vs `100.0` differently). A Rust field typed `f64` would
//! silently widen every such value and change `repr`, `==`, and downstream
//! formatting. Storing each field as the exact Python object the caller
//! passed — and doing arithmetic through Python's own operators
//! (`PyAnyMethods::sub`/`mul`/`div`/`pow`) — makes type preservation true
//! *by construction* (the netlist_contracts.rs precedent).
//!
//! Two fields are exceptions and use typed handles instead (Wave-4 "PyAny
//! removal" tightening, 2026-08-06 — `docs/evidence/2026-08-06-pyany-surface-audit-2.md`
//! Wave A): `Issue.severity` is always the `Severity` pyclass and
//! `Issue.location` / `Placement.via_placement` / `Placement.trace_placement`
//! are always their pyclass or `None`, so `Py<Severity>` /
//! `Option<Py<Location>>` / `Option<Py<ViaPlacement>>` /
//! `Option<Py<TracePlacement>>` replace the opaque handles with no observable
//! change (a non-pyclass payload previously stored opaquely now raises
//! `TypeError`; every verified production path passes the pyclass).
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Rather than re-deriving CPython's `repr(float)`/`repr(str)` rules, these
//! pyclasses call **CPython's own `repr()`** on each stored field object and
//! splice the results into the dataclass layout `Cls(f1=r1, f2=r2, ...)`.
//! Equality builds the same field tuple both sides and defers to Python `==`
//! on tuples, exactly as a generated dataclass `__eq__` does (including the
//! `NotImplemented` return for a foreign class). This is bit-exactness by
//! delegation, not by replication.
//!
//! # Mutation vs frozen semantics
//!
//! Every contract here is a plain (non-frozen) dataclass: fields are
//! `#[pyo3(get, set)]`, the classes carry the `dict` flag (a dataclass
//! instance has a `__dict__`; callers rely on attribute injection), and
//! `__hash__` is raised as `TypeError: unhashable type: 'X'` — the exact
//! message of `eq=True, frozen=False`.
//!
//! # Severity
//!
//! `Severity` is a plain `enum.Enum` with `auto()` values, a `weight` /
//! `is_failure` property surface and `__lt__`/`__le__` by value. It is
//! reproduced as a pyclass whose four members are `#[classattr]` singletons
//! (`Severity.INFO`, ...), with `name`/`value`/`weight`/`is_failure`
//! getters, `repr` `<Severity.INFO: 1>`, `str` `Severity.INFO`, value
//! equality and hashability. (pyo3 cannot subclass `enum.Enum`; the member
//! surface is what the consumers use — `.name`, `.value`, `.weight`,
//! `.is_failure`, comparisons, equality.)
//!
//! # Documented narrowing (same trade-off as the #724 board/netlist slice)
//!
//! pyo3's `Option<&Bound>` collapses "argument omitted" and "argument
//! `None`" into one `None`. For the **literal-default** fields (e.g.
//! `net_class="Signal"`, `board_width=100.0`) that is resolved with pyo3
//! *signature defaults*, which are injected only when the argument is
//! omitted — so `Placement(board_width=None)` stores `None` exactly as the
//! dataclass does. For the **default_factory** fields (e.g. `issues=[]`,
//! `details={}`) an explicit `None` collapses to a fresh empty
//! list/dict where the dataclass would store `None`. No consumer passes
//! `None` to a factory field (audited: `drc_runner`/`drc_oracle` pass
//! lists/dicts or omit the argument), and the narrowing is documented in
//! `VERIFICATION.md`.
//!
//! # Panic policy (R1g)
//!
//! pyo3 wraps every `#[pymethods]` boundary in its default `catch_unwind`:
//! a Rust panic surfaces as `pyo3_runtime.PanicException`, never across the
//! boundary as UB. All field access is through Python's own operators, and
//! no `unwrap`/`expect` is used outside `#[cfg(test)]` (clippy
//! `unwrap_used`/`expect_used` are denied).

use pyo3::IntoPyObjectExt;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::{
    PyAny, PyAnyMethods, PyDict, PyDictMethods, PyList, PyListMethods, PyModule, PyTuple,
    PyTupleMethods, PyType,
};

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/// Clone an owned handle to the same underlying Python object (NOT a copy) —
/// preserves identity for mutable containers.
fn same(py: Python<'_>, obj: &Py<PyAny>) -> Py<PyAny> {
    obj.clone_ref(py)
}

/// `obj` if present, else Python `None`.
fn opt_or_none(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> Py<PyAny> {
    value.map_or_else(|| py.None(), |v| v.clone().unbind())
}

/// `value` if present (stored verbatim, even when it is Python `None`),
/// else a freshly-created `default`. This is how the dataclass literal
/// defaults (`net_class="Signal"`, `board_width=100.0`, ...) are applied:
/// pyo3's signature defaults cannot carry a Python literal into a
/// `&Bound<PyAny>` parameter, and an explicit `None` must be stored
/// verbatim exactly as the dataclass does. The one narrowing: an explicit
/// `None` to a *default_factory* field (fresh list/dict below) collapses
/// to the fresh empty container — documented in `VERIFICATION.md`.
fn opt_or<'py, T>(
    py: Python<'py>,
    value: Option<&Bound<'py, PyAny>>,
    default: T,
) -> PyResult<Py<PyAny>>
where
    T: IntoPyObject<'py>,
{
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => default.into_bound_py_any(py).map(Bound::unbind),
    }
}

/// A fresh empty Python `list` (what `field(default_factory=list)` produces
/// on every construction).
fn list_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => Ok(PyList::empty(py).into()),
    }
}

/// A fresh empty Python `dict` (what `field(default_factory=dict)` produces
/// on every construction).
fn dict_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => Ok(PyDict::new(py).into()),
    }
}

/// `repr(obj)` as CPython renders it, used to assemble dataclass reprs.
fn repr_of(obj: &Py<PyAny>, py: Python<'_>) -> PyResult<String> {
    obj.bind(py).repr()?.extract()
}

/// Assemble a generated-dataclass `__repr__`: `Cls(name=repr, ...)`.
fn dataclass_repr(class: &str, fields: &[(&str, String)]) -> String {
    let mut out = String::with_capacity(class.len() + 2 + fields.len() * 16);
    out.push_str(class);
    out.push('(');
    for (i, (name, rendered)) in fields.iter().enumerate() {
        if i > 0 {
            out.push_str(", ");
        }
        out.push_str(name);
        out.push('=');
        out.push_str(rendered);
    }
    out.push(')');
    out
}

/// A generated dataclass `__eq__`: compare the `compare=True` field tuples
/// when `other.__class__ is self.__class__`, else return `NotImplemented`.
fn dataclass_eq<'py>(
    py: Python<'py>,
    this_class: &Bound<'py, PyAny>,
    other: &Bound<'py, PyAny>,
    lhs: &'py [Py<PyAny>],
    rhs_of: impl FnOnce(&Bound<'py, PyAny>) -> PyResult<Vec<Py<PyAny>>>,
) -> PyResult<Py<PyAny>> {
    // `other.__class__ is self.__class__` -- dataclasses use `is`, so a
    // subclass instance compares unequal (returns NotImplemented).
    if !other.get_type().is(this_class) {
        return Ok(py.NotImplemented());
    }
    let rhs = rhs_of(other)?;
    let lhs_tuple = PyTuple::new(py, lhs.iter().map(|v| v.bind(py)))?;
    let rhs_tuple = PyTuple::new(py, rhs.iter().map(|v| v.bind(py)))?;
    lhs_tuple.eq(&rhs_tuple)?.into_py_any(py)
}

/// The `TypeError` CPython raises for a class whose `__hash__` is `None` —
/// every `eq=True, frozen=False` dataclass here.
fn unhashable(class: &str) -> PyErr {
    PyTypeError::new_err(format!("unhashable type: '{class}'"))
}

/// The `builtins` module.
fn builtins(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "builtins")
}

/// Call Python's builtin `float()` — CPython's own conversion, so the
/// from_dict marshalling uses the exact `float(x)` semantics the oracle does.
fn py_float(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(builtins(py)?.getattr("float")?.call1((obj,))?.unbind())
}

/// Call Python's builtin `tuple()` — the oracle's `tuple(bounds)`.
fn py_tuple(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(builtins(py)?.getattr("tuple")?.call1((obj,))?.unbind())
}

/// Call Python's builtin `list()` — the oracle's `list(bounds)`.
fn py_list_of(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(builtins(py)?.getattr("list")?.call1((obj,))?.unbind())
}

/// Call Python's `math.sqrt` — the oracle's `math.sqrt(x)`.
fn math_sqrt(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    Ok(PyModule::import(py, "math")?
        .getattr("sqrt")?
        .call1((obj,))?
        .unbind())
}

/// `data.get(key, default)` — the oracle's `Mapping.get`. Implemented as a
/// method call so any Mapping (dict, UserDict, MappingProxyType, dict
/// subclass) behaves exactly as in Python.
fn mapping_get<'py>(
    py: Python<'py>,
    data: &Bound<'py, PyAny>,
    key: &str,
    default: impl IntoPyObject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let default = default.into_bound_py_any(py)?;
    data.call_method1("get", (key, default))
}

/// Python's builtin `max(a, b)`.
fn py_max2<'py>(
    py: Python<'py>,
    a: &Bound<'py, PyAny>,
    b: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    builtins(py)?.getattr("max")?.call1((a, b))
}

/// Python's builtin `min(a, b)`.
fn py_min2<'py>(
    py: Python<'py>,
    a: &Bound<'py, PyAny>,
    b: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    builtins(py)?.getattr("min")?.call1((a, b))
}

/// The `Severity` member with the given name, from the Python class.
fn severity_member<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.get_type::<Severity>().getattr(name)
}

/// `issue.severity == Severity.<name>` — the dataclass property-counting
/// comparisons (`i.severity == Severity.INFO` etc.) through Python equality.
fn issue_severity_is(
    py: Python<'_>,
    issue: &Bound<'_, PyAny>,
    member_name: &str,
) -> PyResult<bool> {
    let sev = issue.getattr("severity")?;
    sev.eq(severity_member(py, member_name)?)
}

// ---------------------------------------------------------------------------
// Severity
// ---------------------------------------------------------------------------

/// Check result severity levels (verbatim port of the `Severity` Enum in
/// `drc_result.py`).
///
/// `INFO=1, WARNING=2, ERROR=3, CRITICAL=4` (`enum.auto()`), with the
/// documented weight/is_failure table and value-based ordering.
#[pyclass(module = "temper_drc_rs")]
#[derive(Debug)]
pub struct Severity {
    name: String,
    value: i32,
}

impl Severity {
    fn new(name: &str, value: i32) -> Self {
        Severity {
            name: name.to_string(),
            value,
        }
    }
}

#[pymethods]
impl Severity {
    #[classattr]
    #[allow(non_snake_case)]
    fn INFO(py: Python<'_>) -> PyResult<Py<Severity>> {
        Py::new(py, Severity::new("INFO", 1))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn WARNING(py: Python<'_>) -> PyResult<Py<Severity>> {
        Py::new(py, Severity::new("WARNING", 2))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ERROR(py: Python<'_>) -> PyResult<Py<Severity>> {
        Py::new(py, Severity::new("ERROR", 3))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn CRITICAL(py: Python<'_>) -> PyResult<Py<Severity>> {
        Py::new(py, Severity::new("CRITICAL", 4))
    }

    #[getter]
    fn name(&self) -> String {
        self.name.clone()
    }

    #[getter]
    fn value(&self) -> i32 {
        self.value
    }

    /// The documented weight table (INFO 0.0, WARNING 1.0, ERROR 10.0,
    /// CRITICAL 100.0).
    #[getter]
    fn weight(&self) -> f64 {
        match self.value {
            1 => 0.0,
            2 => 1.0,
            3 => 10.0,
            _ => 100.0,
        }
    }

    /// `self in (ERROR, CRITICAL)`.
    #[getter]
    fn is_failure(&self) -> bool {
        self.value == 3 || self.value == 4
    }

    /// Enum repr: `<Severity.ERROR: 3>`.
    fn __repr__(&self) -> String {
        format!("<Severity.{}: {}>", self.name, self.value)
    }

    /// All members in declaration order (INFO, WARNING, ERROR, CRITICAL) —
    /// the pyo3 substitute for Python Enum class-level iteration
    /// (`list(Severity)`): pyo3 has no metaclass hook, so `iter(Severity)`
    /// cannot be wired (the `gates.py` `members()` precedent). The report
    /// formatter's PBT enumerates severities through this.
    #[staticmethod]
    fn members(py: Python<'_>) -> PyResult<Py<PyList>> {
        let list = PyList::empty(py);
        for name in ["INFO", "WARNING", "ERROR", "CRITICAL"] {
            list.append(severity_member(py, name)?)?;
        }
        Ok(list.unbind())
    }

    /// Enum str: `Severity.ERROR`.
    fn __str__(&self) -> String {
        format!("Severity.{}", self.name)
    }

    /// Enum members compare equal by value+name.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let rhs = other.cast::<Self>()?.borrow();
        Ok(slf.borrow().value == rhs.value && slf.borrow().name == rhs.name)
    }

    fn __hash__(&self) -> isize {
        // Enum members are hashable; consistent hashing over the name is
        // sufficient for dict/set membership (hash VALUES are not part of
        // the contract).
        self.name.as_str().chars().map(|c| c as isize).sum()
    }

    /// `__lt__`: value comparison; `NotImplemented` for a non-Severity.
    fn __lt__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(slf.py().NotImplemented());
        }
        (slf.borrow().value < other.cast::<Self>()?.borrow().value).into_py_any(slf.py())
    }

    /// `__le__`: value comparison; `NotImplemented` for a non-Severity.
    fn __le__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(slf.py().NotImplemented());
        }
        (slf.borrow().value <= other.cast::<Self>()?.borrow().value).into_py_any(slf.py())
    }
}

// ---------------------------------------------------------------------------
// Location
// ---------------------------------------------------------------------------

/// Spatial location of an issue on the PCB.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct Location {
    #[pyo3(get, set)]
    pub x: Py<PyAny>,
    #[pyo3(get, set)]
    pub y: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
}

impl Location {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.x), same(py, &self.y), same(py, &self.layer)]
    }
}

#[pymethods]
impl Location {
    #[new]
    #[pyo3(signature = (x=None, y=None, layer=None))]
    fn new(
        py: Python<'_>,
        x: Option<&Bound<'_, PyAny>>,
        y: Option<&Bound<'_, PyAny>>,
        layer: Option<&Bound<'_, PyAny>>,
    ) -> Self {
        Self {
            x: opt_or_none(py, x),
            y: opt_or_none(py, y),
            layer: opt_or_none(py, layer),
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Location",
            &[
                ("x", repr_of(&self.x, py)?),
                ("y", repr_of(&self.y, py)?),
                ("layer", repr_of(&self.layer, py)?),
            ],
        ))
    }

    /// The custom `__str__`: `(x, y) on layer` or `unknown`.
    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        if !self.x.bind(py).is_none() && !self.y.bind(py).is_none() {
            let mut loc = format!(
                "({}, {})",
                py_float_fmt_2(py, self.x.bind(py))?,
                py_float_fmt_2(py, self.y.bind(py))?
            );
            if self.layer.bind(py).is_truthy()? {
                loc.push_str(&format!(
                    " on {}",
                    self.layer.bind(py).str()?.to_string_lossy()
                ));
            }
            return Ok(loc);
        }
        Ok("unknown".to_string())
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Location"))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let d = PyDict::new(py);
        d.set_item("x", self.x.bind(py))?;
        d.set_item("y", self.y.bind(py))?;
        d.set_item("layer", self.layer.bind(py))?;
        Ok(d.into())
    }
}

/// CPython `f"{x:.2f}"` — round-half-even fixed-point, `nan`/`inf` lowercase.
fn py_float_fmt_2(py: Python<'_>, x: &Bound<'_, PyAny>) -> PyResult<String> {
    // The value may be an int (int stays int in storage); `:.2f` on an int
    // formats the same digits as on its float value, so route through
    // Python's own format() for byte-exactness on both.
    let fmt = builtins(py)?.getattr("format")?;
    let out = fmt.call1((x, ".2f"))?;
    out.extract()
}

// ---------------------------------------------------------------------------
// Issue
// ---------------------------------------------------------------------------

/// A single check issue found during verification.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct Issue {
    // Wave-4 "PyAny removal" tightening (2026-08-06): `severity` and
    // `location` wrap the same-crate `Severity`/`Location` pyclasses on every
    // production construction path (`drc_runner.py`, `drc_oracle.py` pass the
    // `_SEVERITY_MAP[...]` singletons and `_Location(...)`/`None`), so the
    // opaque handles are replaced by typed references. Behavior is unchanged:
    // the wrapped value IS the pyclass (or `None`) and identity is preserved.
    // The scalar/container fields stay `Py<PyAny>` (int-vs-float type
    // preservation / Python-built identity-mutable containers — INTENTIONAL +
    // STILL-NEEDED per the PyAny surface audit).
    #[pyo3(get, set)]
    pub severity: Py<Severity>,
    #[pyo3(get, set)]
    pub code: Py<PyAny>,
    #[pyo3(get, set)]
    pub message: Py<PyAny>,
    #[pyo3(get, set)]
    pub category: Py<PyAny>,
    #[pyo3(get, set)]
    pub check_name: Py<PyAny>,
    #[pyo3(get, set)]
    pub affected_items: Py<PyAny>,
    #[pyo3(get, set)]
    pub location: Option<Py<Location>>,
    #[pyo3(get, set)]
    pub details: Py<PyAny>,
    #[pyo3(get, set)]
    pub constraint_id: Py<PyAny>,
}

impl Issue {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.severity.clone_ref(py).into_any(),
            same(py, &self.code),
            same(py, &self.message),
            same(py, &self.category),
            same(py, &self.check_name),
            same(py, &self.affected_items),
            match self.location.as_ref() {
                Some(location) => location.clone_ref(py).into_any(),
                None => py.None(),
            },
            same(py, &self.details),
            same(py, &self.constraint_id),
        ]
    }
}

#[pymethods]
impl Issue {
    #[new]
    #[pyo3(signature = (severity, code, message, category, check_name, affected_items=None, location=None, details=None, constraint_id=None))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        severity: &Bound<'_, Severity>,
        code: &Bound<'_, PyAny>,
        message: &Bound<'_, PyAny>,
        category: &Bound<'_, PyAny>,
        check_name: &Bound<'_, PyAny>,
        affected_items: Option<&Bound<'_, PyAny>>,
        location: Option<&Bound<'_, Location>>,
        details: Option<&Bound<'_, PyAny>>,
        constraint_id: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            severity: severity.clone().unbind(),
            code: code.clone().unbind(),
            message: message.clone().unbind(),
            category: category.clone().unbind(),
            check_name: check_name.clone().unbind(),
            affected_items: list_or_new(py, affected_items)?,
            location: location.map(|l| l.clone().unbind()),
            details: dict_or_new(py, details)?,
            constraint_id: opt_or_none(py, constraint_id),
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let severity = self.severity.clone_ref(py).into_any();
        let location = match self.location.as_ref() {
            Some(location) => location.clone_ref(py).into_any(),
            None => py.None(),
        };
        Ok(dataclass_repr(
            "Issue",
            &[
                ("severity", repr_of(&severity, py)?),
                ("code", repr_of(&self.code, py)?),
                ("message", repr_of(&self.message, py)?),
                ("category", repr_of(&self.category, py)?),
                ("check_name", repr_of(&self.check_name, py)?),
                ("affected_items", repr_of(&self.affected_items, py)?),
                ("location", repr_of(&location, py)?),
                ("details", repr_of(&self.details, py)?),
                ("constraint_id", repr_of(&self.constraint_id, py)?),
            ],
        ))
    }

    /// The custom `__str__`: `[code] message (items)`.
    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        let affected = self.affected_items.bind(py);
        let mut items = String::new();
        let n = affected.len()?;
        for (i, item) in affected.try_iter()?.enumerate() {
            if i == 3 {
                break;
            }
            if i > 0 {
                items.push_str(", ");
            }
            items.push_str(&item?.str()?.to_string_lossy());
        }
        if n > 3 {
            items.push_str(&format!(" (+{} more)", n - 3));
        }
        Ok(format!(
            "[{}] {} ({items})",
            self.code.bind(py).str()?.to_string_lossy(),
            self.message.bind(py).str()?.to_string_lossy()
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Issue"))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let d = PyDict::new(py);
        d.set_item("severity", self.severity.bind(py).getattr("name")?)?;
        d.set_item("code", self.code.bind(py))?;
        d.set_item("message", self.message.bind(py))?;
        d.set_item("category", self.category.bind(py))?;
        d.set_item("check_name", self.check_name.bind(py))?;
        d.set_item("affected_items", self.affected_items.bind(py))?;
        match self.location.as_ref() {
            Some(location) => {
                let sub = location.bind(py).call_method0("to_dict")?;
                d.set_item("location", sub)?;
            }
            None => d.set_item("location", py.None())?,
        }
        d.set_item("details", self.details.bind(py))?;
        d.set_item("constraint_id", self.constraint_id.bind(py))?;
        Ok(d.into())
    }
}

// ---------------------------------------------------------------------------
// CheckResult
// ---------------------------------------------------------------------------

/// Result of running a single check.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct CheckResult {
    #[pyo3(get, set)]
    pub check_name: Py<PyAny>,
    #[pyo3(get, set)]
    pub passed: Py<PyAny>,
    #[pyo3(get, set)]
    pub issues: Py<PyAny>,
    #[pyo3(get, set)]
    pub elapsed_ms: Py<PyAny>,
    #[pyo3(get, set)]
    pub metrics: Py<PyAny>,
}

impl CheckResult {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.check_name),
            same(py, &self.passed),
            same(py, &self.issues),
            same(py, &self.elapsed_ms),
            same(py, &self.metrics),
        ]
    }

    fn count_severity(&self, py: Python<'_>, member_name: &str) -> PyResult<i64> {
        let mut count = 0_i64;
        for issue in self.issues.bind(py).try_iter()? {
            if issue_severity_is(py, &issue?, member_name)? {
                count += 1;
            }
        }
        Ok(count)
    }
}

#[pymethods]
impl CheckResult {
    #[new]
    #[pyo3(signature = (check_name, passed, issues=None, elapsed_ms=None, metrics=None))]
    fn new(
        py: Python<'_>,
        check_name: &Bound<'_, PyAny>,
        passed: &Bound<'_, PyAny>,
        issues: Option<&Bound<'_, PyAny>>,
        elapsed_ms: Option<&Bound<'_, PyAny>>,
        metrics: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            check_name: check_name.clone().unbind(),
            passed: passed.clone().unbind(),
            issues: list_or_new(py, issues)?,
            elapsed_ms: opt_or(py, elapsed_ms, 0.0_f64)?,
            metrics: dict_or_new(py, metrics)?,
        })
    }

    #[getter]
    fn info_count(&self, py: Python<'_>) -> PyResult<i64> {
        self.count_severity(py, "INFO")
    }

    #[getter]
    fn warning_count(&self, py: Python<'_>) -> PyResult<i64> {
        self.count_severity(py, "WARNING")
    }

    #[getter]
    fn error_count(&self, py: Python<'_>) -> PyResult<i64> {
        self.count_severity(py, "ERROR")
    }

    #[getter]
    fn critical_count(&self, py: Python<'_>) -> PyResult<i64> {
        self.count_severity(py, "CRITICAL")
    }

    /// `warning + error + critical` (INFO is excluded, verbatim).
    #[getter]
    fn total_issues(&self, py: Python<'_>) -> PyResult<i64> {
        Ok(self.warning_count(py)? + self.error_count(py)? + self.critical_count(py)?)
    }

    /// `sum(issue.severity.weight for issue in self.issues)` in issue order.
    /// The weights are exact f64 constants (0/1/10/100) and the oracle's
    /// `sum()` starts from int 0 then adds each weight; f64 accumulation in
    /// the same order is bit-identical for these values.
    #[getter]
    fn penalty(&self, py: Python<'_>) -> PyResult<f64> {
        let mut total = 0.0_f64;
        for issue in self.issues.bind(py).try_iter()? {
            let w: f64 = issue?.getattr("severity")?.getattr("weight")?.extract()?;
            total += w;
        }
        Ok(total)
    }

    /// The dataclass `merge`: new CheckResult with concatenated issues,
    /// AND-ed passed, added elapsed_ms, `{**a, **b}` metrics (later keys
    /// win, first-seen position kept).
    fn merge(&self, py: Python<'_>, other: &Bound<'_, Self>) -> PyResult<Py<PyAny>> {
        let other_ref = other.borrow();
        let issues = PyList::empty(py);
        for item in self.issues.bind(py).try_iter()? {
            issues.append(item?)?;
        }
        for item in other_ref.issues.bind(py).try_iter()? {
            issues.append(item?)?;
        }
        let metrics = PyDict::new(py);
        for (k, v) in self.metrics.bind(py).cast::<PyDict>()?.iter() {
            metrics.set_item(k, v)?;
        }
        for (k, v) in other_ref.metrics.bind(py).cast::<PyDict>()?.iter() {
            metrics.set_item(k, v)?;
        }
        // `self.passed and other.passed` -- truthiness, short-circuit.
        let passed = self.passed.bind(py).is_truthy()? && other_ref.passed.bind(py).is_truthy()?;
        // `self.elapsed_ms + other.elapsed_ms` -- Python `+` (int+float
        // promotes exactly as in CPython).
        let elapsed = self
            .elapsed_ms
            .bind(py)
            .add(other_ref.elapsed_ms.bind(py))?;
        let cr = CheckResult {
            check_name: same(py, &self.check_name),
            passed: passed.into_py_any(py)?,
            issues: issues.into(),
            elapsed_ms: elapsed.unbind(),
            metrics: metrics.into(),
        };
        Ok(Py::new(py, cr)?.into_any())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "CheckResult",
            &[
                ("check_name", repr_of(&self.check_name, py)?),
                ("passed", repr_of(&self.passed, py)?),
                ("issues", repr_of(&self.issues, py)?),
                ("elapsed_ms", repr_of(&self.elapsed_ms, py)?),
                ("metrics", repr_of(&self.metrics, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("CheckResult"))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let issues = PyList::empty(py);
        for issue in self.issues.bind(py).try_iter()? {
            issues.append(issue?.call_method0("to_dict")?)?;
        }
        let counts = PyDict::new(py);
        counts.set_item("info", self.info_count(py)?)?;
        counts.set_item("warning", self.warning_count(py)?)?;
        counts.set_item("error", self.error_count(py)?)?;
        counts.set_item("critical", self.critical_count(py)?)?;
        let d = PyDict::new(py);
        d.set_item("check_name", self.check_name.bind(py))?;
        d.set_item("passed", self.passed.bind(py))?;
        d.set_item("issues", issues)?;
        d.set_item("elapsed_ms", self.elapsed_ms.bind(py))?;
        d.set_item("metrics", self.metrics.bind(py))?;
        d.set_item("counts", counts)?;
        Ok(d.into())
    }
}

// ---------------------------------------------------------------------------
// RunResult
// ---------------------------------------------------------------------------

/// Result of running multiple checks.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct RunResult {
    #[pyo3(get, set)]
    pub check_results: Py<PyAny>,
    #[pyo3(get, set)]
    pub total_elapsed_ms: Py<PyAny>,
}

impl RunResult {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.check_results),
            same(py, &self.total_elapsed_ms),
        ]
    }

    fn sum_property(&self, py: Python<'_>, attr: &str) -> PyResult<f64> {
        let mut total = 0.0_f64;
        for cr in self.check_results.bind(py).try_iter()? {
            let v: f64 = cr?.getattr(attr)?.extract()?;
            total += v;
        }
        Ok(total)
    }
}

#[pymethods]
impl RunResult {
    #[new]
    #[pyo3(signature = (check_results=None, total_elapsed_ms=None))]
    fn new(
        py: Python<'_>,
        check_results: Option<&Bound<'_, PyAny>>,
        total_elapsed_ms: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            check_results: list_or_new(py, check_results)?,
            total_elapsed_ms: opt_or(py, total_elapsed_ms, 0.0_f64)?,
        })
    }

    /// A run that evaluated zero checks has not passed anything — fail
    /// closed instead of Python's vacuously-True `all([])`.
    #[getter]
    fn passed(&self, py: Python<'_>) -> PyResult<bool> {
        let checks = self.check_results.bind(py);
        if checks.len()? == 0 {
            return Ok(false);
        }
        for cr in checks.try_iter()? {
            if !cr?.getattr("passed")?.is_truthy()? {
                return Ok(false);
            }
        }
        Ok(true)
    }

    #[getter]
    fn all_issues(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for cr in self.check_results.bind(py).try_iter()? {
            let issues = cr?.getattr("issues")?;
            for issue in issues.try_iter()? {
                out.append(issue?)?;
            }
        }
        Ok(out.into())
    }

    #[getter]
    fn total_checks(&self, py: Python<'_>) -> PyResult<usize> {
        self.check_results.bind(py).len()
    }

    #[getter]
    fn passed_checks(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            if cr?.getattr("passed")?.is_truthy()? {
                n += 1;
            }
        }
        Ok(n)
    }

    #[getter]
    fn failed_checks(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            if !cr?.getattr("passed")?.is_truthy()? {
                n += 1;
            }
        }
        Ok(n)
    }

    #[getter]
    fn info_count(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            n += cr?.getattr("info_count")?.extract::<i64>()?;
        }
        Ok(n)
    }

    #[getter]
    fn warning_count(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            n += cr?.getattr("warning_count")?.extract::<i64>()?;
        }
        Ok(n)
    }

    #[getter]
    fn error_count(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            n += cr?.getattr("error_count")?.extract::<i64>()?;
        }
        Ok(n)
    }

    #[getter]
    fn critical_count(&self, py: Python<'_>) -> PyResult<i64> {
        let mut n = 0_i64;
        for cr in self.check_results.bind(py).try_iter()? {
            n += cr?.getattr("critical_count")?.extract::<i64>()?;
        }
        Ok(n)
    }

    #[getter]
    fn total_penalty(&self, py: Python<'_>) -> PyResult<f64> {
        self.sum_property(py, "penalty")
    }

    fn by_category(&self, py: Python<'_>, category: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for cr in self.check_results.bind(py).try_iter()? {
            let cr = cr?;
            let issues = cr.getattr("issues")?;
            let mut has = false;
            for issue in issues.try_iter()? {
                if issue?.getattr("category")?.eq(category)? {
                    has = true;
                    break;
                }
            }
            // `any(...) or not r.issues`
            if has || !issues.is_truthy()? {
                out.append(cr)?;
            }
        }
        Ok(out.into())
    }

    fn by_severity(&self, py: Python<'_>, severity: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for item in self.all_issues(py)?.bind(py).try_iter()? {
            let issue = item?;
            if issue.getattr("severity")?.eq(severity)? {
                out.append(issue)?;
            }
        }
        Ok(out.into())
    }

    fn issues_for_component(&self, py: Python<'_>, ref_: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let out = PyList::empty(py);
        for issue in self.all_issues(py)?.bind(py).try_iter()? {
            let issue = issue?;
            let items = issue.getattr("affected_items")?;
            if items.contains(ref_)? {
                out.append(issue)?;
            }
        }
        Ok(out.into())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "RunResult",
            &[
                ("check_results", repr_of(&self.check_results, py)?),
                ("total_elapsed_ms", repr_of(&self.total_elapsed_ms, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("RunResult"))
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let check_results = PyList::empty(py);
        for cr in self.check_results.bind(py).try_iter()? {
            check_results.append(cr?.call_method0("to_dict")?)?;
        }
        let summary = PyDict::new(py);
        summary.set_item("total_checks", self.total_checks(py)?)?;
        summary.set_item("passed_checks", self.passed_checks(py)?)?;
        summary.set_item("failed_checks", self.failed_checks(py)?)?;
        summary.set_item("info", self.info_count(py)?)?;
        summary.set_item("warning", self.warning_count(py)?)?;
        summary.set_item("error", self.error_count(py)?)?;
        summary.set_item("critical", self.critical_count(py)?)?;
        summary.set_item("total_penalty", self.total_penalty(py)?)?;
        let d = PyDict::new(py);
        d.set_item("passed", self.passed(py)?)?;
        d.set_item("total_elapsed_ms", self.total_elapsed_ms.bind(py))?;
        d.set_item("summary", summary)?;
        d.set_item("check_results", check_results)?;
        Ok(d.into())
    }
}

// ---------------------------------------------------------------------------
// ComponentPlacement
// ---------------------------------------------------------------------------

/// Single component placement on the PCB.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ComponentPlacement {
    #[pyo3(get, set)]
    pub r#ref: Py<PyAny>,
    #[pyo3(get, set)]
    pub footprint: Py<PyAny>,
    #[pyo3(get, set)]
    pub x: Py<PyAny>,
    #[pyo3(get, set)]
    pub y: Py<PyAny>,
    #[pyo3(get, set)]
    pub rotation: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub height: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_class: Py<PyAny>,
    #[pyo3(get, set)]
    pub voltage_domain: Py<PyAny>,
}

impl ComponentPlacement {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.r#ref),
            same(py, &self.footprint),
            same(py, &self.x),
            same(py, &self.y),
            same(py, &self.rotation),
            same(py, &self.layer),
            same(py, &self.width),
            same(py, &self.height),
            same(py, &self.net_class),
            same(py, &self.voltage_domain),
        ]
    }
}

#[pymethods]
impl ComponentPlacement {
    #[new]
    #[pyo3(signature = (r#ref, footprint, x, y, rotation, layer, width, height, net_class=None, voltage_domain=None))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        r#ref: &Bound<'_, PyAny>,
        footprint: &Bound<'_, PyAny>,
        x: &Bound<'_, PyAny>,
        y: &Bound<'_, PyAny>,
        rotation: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        height: &Bound<'_, PyAny>,
        net_class: Option<&Bound<'_, PyAny>>,
        voltage_domain: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            r#ref: r#ref.clone().unbind(),
            footprint: footprint.clone().unbind(),
            x: x.clone().unbind(),
            y: y.clone().unbind(),
            rotation: rotation.clone().unbind(),
            layer: layer.clone().unbind(),
            width: width.clone().unbind(),
            height: height.clone().unbind(),
            net_class: opt_or(py, net_class, "Signal")?,
            voltage_domain: opt_or_none(py, voltage_domain),
        })
    }

    /// Bounding box `(x - w/2, y - h/2, x + w/2, y + h/2)` — Python true
    /// division and arithmetic, so int leaves widen exactly as in CPython.
    #[getter]
    fn bounds<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let hw = self.width.bind(py).div(2)?;
        let hh = self.height.bind(py).div(2)?;
        let x = self.x.bind(py);
        let y = self.y.bind(py);
        PyTuple::new(py, [x.sub(&hw)?, y.sub(&hh)?, x.add(&hw)?, y.add(&hh)?])
    }

    /// Center point `(x, y)` — the stored objects verbatim (int stays int).
    #[getter]
    fn center<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, [self.x.bind(py), self.y.bind(py)])
    }

    /// `math.sqrt(dx * dx + dy * dy)` — the oracle's exact arithmetic.
    fn distance_to(&self, py: Python<'_>, other: &Bound<'_, Self>) -> PyResult<Py<PyAny>> {
        let ox = other.borrow().x.clone_ref(py);
        let oy = other.borrow().y.clone_ref(py);
        let dx = self.x.bind(py).sub(ox.bind(py))?;
        let dy = self.y.bind(py).sub(oy.bind(py))?;
        let sum = dx.mul(&dx)?.add(dy.mul(&dy)?)?;
        math_sqrt(py, &sum)
    }

    /// Edge-to-edge distance from the two bounding boxes.
    fn edge_distance_to(&self, py: Python<'_>, other: &Bound<'_, Self>) -> PyResult<Py<PyAny>> {
        let b1 = self.bounds(py)?;
        let b2 = other.borrow().bounds(py)?;
        let x1_min = b1.get_item(0)?;
        let y1_min = b1.get_item(1)?;
        let x1_max = b1.get_item(2)?;
        let y1_max = b1.get_item(3)?;
        let x2_min = b2.get_item(0)?;
        let y2_min = b2.get_item(1)?;
        let x2_max = b2.get_item(2)?;
        let y2_max = b2.get_item(3)?;
        let zero = 0_i32.into_bound_py_any(py)?;
        let dx = py_max2(
            py,
            &zero,
            &py_max2(py, &x1_min.sub(&x2_max)?, &x2_min.sub(&x1_max)?)?,
        )?;
        let dy = py_max2(
            py,
            &zero,
            &py_max2(py, &y1_min.sub(&y2_max)?, &y2_min.sub(&y1_max)?)?,
        )?;
        if dx.eq(&zero)? && dy.eq(&zero)? {
            return 0.0_f64.into_py_any(py);
        }
        let sum = dx.mul(&dx)?.add(dy.mul(&dy)?)?;
        math_sqrt(py, &sum)
    }

    /// `not (x1_max < x2_min or x2_max < x1_min or y1_max < y2_min or ...)`.
    fn overlaps(&self, py: Python<'_>, other: &Bound<'_, Self>) -> PyResult<bool> {
        let b1 = self.bounds(py)?;
        let b2 = other.borrow().bounds(py)?;
        let x1_min = b1.get_item(0)?;
        let y1_min = b1.get_item(1)?;
        let x1_max = b1.get_item(2)?;
        let y1_max = b1.get_item(3)?;
        let x2_min = b2.get_item(0)?;
        let y2_min = b2.get_item(1)?;
        let x2_max = b2.get_item(2)?;
        let y2_max = b2.get_item(3)?;
        let disjoint = x1_max.lt(&x2_min)?
            || x2_max.lt(&x1_min)?
            || y1_max.lt(&y2_min)?
            || y2_max.lt(&y1_min)?;
        Ok(!disjoint)
    }

    /// `x_overlap * y_overlap` with `max(0, ...)` clamps — Python min/max
    /// keep the int 0 when the boxes do not overlap (int-vs-float matters).
    fn overlap_area(&self, py: Python<'_>, other: &Bound<'_, Self>) -> PyResult<Py<PyAny>> {
        let b1 = self.bounds(py)?;
        let b2 = other.borrow().bounds(py)?;
        let x1_min = b1.get_item(0)?;
        let y1_min = b1.get_item(1)?;
        let x1_max = b1.get_item(2)?;
        let y1_max = b1.get_item(3)?;
        let x2_min = b2.get_item(0)?;
        let y2_min = b2.get_item(1)?;
        let x2_max = b2.get_item(2)?;
        let y2_max = b2.get_item(3)?;
        let zero = 0_i32.into_bound_py_any(py)?;
        let x_overlap = py_max2(
            py,
            &zero,
            &py_min2(py, &x1_max, &x2_max)?.sub(&py_max2(py, &x1_min, &x2_min)?)?,
        )?;
        let y_overlap = py_max2(
            py,
            &zero,
            &py_min2(py, &y1_max, &y2_max)?.sub(&py_max2(py, &y1_min, &y2_min)?)?,
        )?;
        x_overlap.mul(&y_overlap).map(|v| v.unbind())
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let d = PyDict::new(py);
        d.set_item("ref", self.r#ref.bind(py))?;
        d.set_item("footprint", self.footprint.bind(py))?;
        d.set_item("x", self.x.bind(py))?;
        d.set_item("y", self.y.bind(py))?;
        d.set_item("rotation", self.rotation.bind(py))?;
        d.set_item("layer", self.layer.bind(py))?;
        d.set_item("width", self.width.bind(py))?;
        d.set_item("height", self.height.bind(py))?;
        d.set_item("net_class", self.net_class.bind(py))?;
        d.set_item("voltage_domain", self.voltage_domain.bind(py))?;
        Ok(d.into())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ComponentPlacement",
            &[
                ("ref", repr_of(&self.r#ref, py)?),
                ("footprint", repr_of(&self.footprint, py)?),
                ("x", repr_of(&self.x, py)?),
                ("y", repr_of(&self.y, py)?),
                ("rotation", repr_of(&self.rotation, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("width", repr_of(&self.width, py)?),
                ("height", repr_of(&self.height, py)?),
                ("net_class", repr_of(&self.net_class, py)?),
                ("voltage_domain", repr_of(&self.voltage_domain, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ComponentPlacement"))
    }
}

// ---------------------------------------------------------------------------
// Placement
// ---------------------------------------------------------------------------

/// Complete placement data for DRC checking.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct Placement {
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
    #[pyo3(get, set)]
    pub nets: Py<PyAny>,
    #[pyo3(get, set)]
    pub zones: Py<PyAny>,
    #[pyo3(get, set)]
    pub board_width: Py<PyAny>,
    #[pyo3(get, set)]
    pub board_height: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_classes: Py<PyAny>,
    #[pyo3(get, set)]
    pub voltage_domains: Py<PyAny>,
    // Wave-4 "PyAny removal" tightening (2026-08-06): `via_placement` /
    // `trace_placement` are always the `ViaPlacement`/`TracePlacement`
    // pyclasses or `None` on every production path (`_pipeline_verify.py`
    // assigns the pyclass after default construction; `from_dict` emits
    // `None`). The typed `Option` handle preserves identity for the pyclass
    // case and `None` for the empty case. The container/scalar fields stay
    // `Py<PyAny>` (INTENTIONAL / STILL-NEEDED per the PyAny surface audit).
    #[pyo3(get, set)]
    pub via_placement: Option<Py<ViaPlacement>>,
    #[pyo3(get, set)]
    pub trace_placement: Option<Py<TracePlacement>>,
}

impl Placement {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.components),
            same(py, &self.nets),
            same(py, &self.zones),
            same(py, &self.board_width),
            same(py, &self.board_height),
            same(py, &self.net_classes),
            same(py, &self.voltage_domains),
            match self.via_placement.as_ref() {
                Some(vp) => vp.clone_ref(py).into_any(),
                None => py.None(),
            },
            match self.trace_placement.as_ref() {
                Some(tp) => tp.clone_ref(py).into_any(),
                None => py.None(),
            },
        ]
    }
}

#[pymethods]
impl Placement {
    #[new]
    #[pyo3(signature = (components=None, nets=None, zones=None, board_width=None, board_height=None, net_classes=None, voltage_domains=None, via_placement=None, trace_placement=None))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        components: Option<&Bound<'_, PyAny>>,
        nets: Option<&Bound<'_, PyAny>>,
        zones: Option<&Bound<'_, PyAny>>,
        board_width: Option<&Bound<'_, PyAny>>,
        board_height: Option<&Bound<'_, PyAny>>,
        net_classes: Option<&Bound<'_, PyAny>>,
        voltage_domains: Option<&Bound<'_, PyAny>>,
        via_placement: Option<&Bound<'_, ViaPlacement>>,
        trace_placement: Option<&Bound<'_, TracePlacement>>,
    ) -> PyResult<Self> {
        Ok(Self {
            components: dict_or_new(py, components)?,
            nets: dict_or_new(py, nets)?,
            zones: dict_or_new(py, zones)?,
            board_width: opt_or(py, board_width, 100.0_f64)?,
            board_height: opt_or(py, board_height, 100.0_f64)?,
            net_classes: dict_or_new(py, net_classes)?,
            voltage_domains: dict_or_new(py, voltage_domains)?,
            via_placement: via_placement.map(|vp| vp.clone().unbind()),
            trace_placement: trace_placement.map(|tp| tp.clone().unbind()),
        })
    }

    /// `self.components.get(ref)`.
    fn get_component<'py>(
        &self,
        py: Python<'py>,
        r#ref: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.components.bind(py).call_method1("get", (r#ref,))
    }

    /// The oracle's `components_in_zone`: refs whose component center falls
    /// inside the zone bounds (chained comparisons).
    fn components_in_zone<'py>(
        &self,
        py: Python<'py>,
        zone_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let zones = self.zones.bind(py);
        if !zones.contains(zone_name)? {
            return Ok(PyList::empty(py));
        }
        let bounds = zones.get_item(zone_name)?;
        let x_min = bounds.get_item(0)?;
        let y_min = bounds.get_item(1)?;
        let x_max = bounds.get_item(2)?;
        let y_max = bounds.get_item(3)?;
        let out = PyList::empty(py);
        for (ref_, comp) in self.components.bind(py).cast::<PyDict>()?.iter() {
            let cx = comp.getattr("x")?;
            let cy = comp.getattr("y")?;
            // `x_min <= comp.x <= x_max and y_min <= comp.y <= y_max`
            let in_x = x_min.le(&cx)? && cx.le(&x_max)?;
            if !in_x {
                continue;
            }
            let in_y = y_min.le(&cy)? && cy.le(&y_max)?;
            if in_y {
                out.append(ref_)?;
            }
        }
        Ok(out)
    }

    fn distance_between(
        &self,
        py: Python<'_>,
        ref_a: &Bound<'_, PyAny>,
        ref_b: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let a = self.get_component(py, ref_a)?;
        let b = self.get_component(py, ref_b)?;
        if a.is_none() || b.is_none() {
            return Ok(py.None());
        }
        a.call_method1("distance_to", (b,)).map(Bound::unbind)
    }

    fn edge_distance_between(
        &self,
        py: Python<'_>,
        ref_a: &Bound<'_, PyAny>,
        ref_b: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        let a = self.get_component(py, ref_a)?;
        let b = self.get_component(py, ref_b)?;
        if a.is_none() || b.is_none() {
            return Ok(py.None());
        }
        a.call_method1("edge_distance_to", (b,)).map(Bound::unbind)
    }

    /// `self.net_classes.get(net_name, "Signal")`.
    fn get_net_class<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.net_classes
            .bind(py)
            .call_method1("get", (net_name, "Signal"))
    }

    fn get_voltage_domain<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.voltage_domains
            .bind(py)
            .call_method1("get", (net_name,))
    }

    /// The oracle's `all_pairs`: every unique pair of component refs.
    fn all_pairs(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let keys = self.components.bind(py).call_method0("keys")?;
        let refs = py_list_of(py, &keys)?;
        let refs = refs.bind(py);
        let n = refs.len()?;
        let out = PyList::empty(py);
        for i in 0..n {
            let a = refs.get_item(i)?;
            for j in (i + 1)..n {
                let b = refs.get_item(j)?;
                out.append(PyTuple::new(py, [a.clone(), b.clone()])?)?;
            }
        }
        Ok(out.into())
    }

    /// Verbatim `from_dict` marshalling (see the module docstring for the
    /// default / `tuple(bounds)` semantics).
    #[classmethod]
    fn from_dict(cls: &Bound<'_, PyType>, data: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let empty_list = PyList::empty(py);
        let comps = mapping_get(py, data, "components", empty_list.clone())?;
        let components = PyDict::new(py);
        for comp_data in comps.try_iter()? {
            let comp_data = comp_data?;
            let r#ref = comp_data.get_item("ref")?;
            let footprint = mapping_get(py, &comp_data, "footprint", "")?;
            let x = comp_data.get_item("x")?;
            let y = comp_data.get_item("y")?;
            let rotation = mapping_get(py, &comp_data, "rotation", 0.0)?;
            let layer = mapping_get(py, &comp_data, "layer", "F.Cu")?;
            let width = mapping_get(py, &comp_data, "width", 1.0)?;
            let height = mapping_get(py, &comp_data, "height", 1.0)?;
            let net_class = mapping_get(py, &comp_data, "net_class", "Signal")?;
            let voltage_domain = mapping_get(py, &comp_data, "voltage_domain", py.None())?;
            let comp = ComponentPlacement {
                r#ref: r#ref.clone().unbind(),
                footprint: footprint.clone().unbind(),
                x: x.clone().unbind(),
                y: y.clone().unbind(),
                rotation: rotation.clone().unbind(),
                layer: layer.clone().unbind(),
                width: width.clone().unbind(),
                height: height.clone().unbind(),
                net_class: net_class.clone().unbind(),
                voltage_domain: voltage_domain.clone().unbind(),
            };
            let py_comp = Py::new(py, comp)?;
            components.set_item(r#ref, py_comp)?;
        }
        let zones = PyDict::new(py);
        for zone_data in mapping_get(py, data, "zones", empty_list)?.try_iter()? {
            let zone_data = zone_data?;
            let name = zone_data.get_item("name")?;
            let bounds = mapping_get(py, &zone_data, "bounds", vec![0, 0, 100, 100])?;
            let bounds_tuple = py_tuple(py, &bounds)?;
            zones.set_item(name, bounds_tuple)?;
        }
        let placement = Placement {
            components: components.into(),
            nets: mapping_get(py, data, "nets", PyDict::new(py))?.unbind(),
            zones: zones.into(),
            board_width: mapping_get(py, data, "board_width", 100.0)?.unbind(),
            board_height: mapping_get(py, data, "board_height", 100.0)?.unbind(),
            net_classes: mapping_get(py, data, "net_classes", PyDict::new(py))?.unbind(),
            voltage_domains: mapping_get(py, data, "voltage_domains", PyDict::new(py))?.unbind(),
            via_placement: None,
            trace_placement: None,
        };
        Ok(Py::new(py, placement)?.into_any())
    }

    /// Verbatim `from_yaml`: `yaml.safe_load(open(path))` then `from_dict`.
    #[classmethod]
    fn from_yaml(cls: &Bound<'_, PyType>, path: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let f = builtins(py)?.getattr("open")?.call1((path,))?;
        let data = PyModule::import(py, "yaml")?
            .getattr("safe_load")?
            .call1((&f,))?;
        // The oracle's `with open(...) as f` closes on block exit.
        let _ = f.call_method0("close");
        Self::from_dict(cls, &data)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let components = PyList::empty(py);
        for comp in self
            .components
            .bind(py)
            .call_method0("values")?
            .try_iter()?
        {
            components.append(comp?.call_method0("to_dict")?)?;
        }
        let zones = PyList::empty(py);
        for (name, bounds) in self.zones.bind(py).cast::<PyDict>()?.iter() {
            let entry = PyDict::new(py);
            entry.set_item("name", name)?;
            entry.set_item("bounds", py_list_of(py, &bounds)?)?;
            zones.append(entry)?;
        }
        let d = PyDict::new(py);
        d.set_item("components", components)?;
        d.set_item("nets", self.nets.bind(py))?;
        d.set_item("zones", zones)?;
        d.set_item("board_width", self.board_width.bind(py))?;
        d.set_item("board_height", self.board_height.bind(py))?;
        d.set_item("net_classes", self.net_classes.bind(py))?;
        d.set_item("voltage_domains", self.voltage_domains.bind(py))?;
        Ok(d.into())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let via_placement = match self.via_placement.as_ref() {
            Some(vp) => vp.clone_ref(py).into_any(),
            None => py.None(),
        };
        let trace_placement = match self.trace_placement.as_ref() {
            Some(tp) => tp.clone_ref(py).into_any(),
            None => py.None(),
        };
        Ok(dataclass_repr(
            "Placement",
            &[
                ("components", repr_of(&self.components, py)?),
                ("nets", repr_of(&self.nets, py)?),
                ("zones", repr_of(&self.zones, py)?),
                ("board_width", repr_of(&self.board_width, py)?),
                ("board_height", repr_of(&self.board_height, py)?),
                ("net_classes", repr_of(&self.net_classes, py)?),
                ("voltage_domains", repr_of(&self.voltage_domains, py)?),
                ("via_placement", repr_of(&via_placement, py)?),
                ("trace_placement", repr_of(&trace_placement, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Placement"))
    }
}

// ---------------------------------------------------------------------------
// ClearanceRule
// ---------------------------------------------------------------------------

/// Clearance rule between net classes.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ClearanceRule {
    #[pyo3(get, set)]
    pub from_class: Py<PyAny>,
    #[pyo3(get, set)]
    pub to_class: Py<PyAny>,
    #[pyo3(get, set)]
    pub min_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub description: Py<PyAny>,
}

impl ClearanceRule {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.from_class),
            same(py, &self.to_class),
            same(py, &self.min_mm),
            same(py, &self.description),
        ]
    }
}

#[pymethods]
impl ClearanceRule {
    #[new]
    #[pyo3(signature = (from_class, to_class, min_mm, description=None))]
    fn new(
        py: Python<'_>,
        from_class: &Bound<'_, PyAny>,
        to_class: &Bound<'_, PyAny>,
        min_mm: &Bound<'_, PyAny>,
        description: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            from_class: from_class.clone().unbind(),
            to_class: to_class.clone().unbind(),
            min_mm: min_mm.clone().unbind(),
            description: opt_or(py, description, "")?,
        })
    }

    /// Wildcard semantics: `*` matches anything, else symmetric matching.
    fn applies_to(
        &self,
        py: Python<'_>,
        class_a: &Bound<'_, PyAny>,
        class_b: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        if self.from_class.bind(py).eq("*")? || self.to_class.bind(py).eq("*")? {
            return Ok(true);
        }
        let fc = self.from_class.bind(py);
        let tc = self.to_class.bind(py);
        let fwd = fc.eq(class_a)? && tc.eq(class_b)?;
        let rev = fc.eq(class_b)? && tc.eq(class_a)?;
        Ok(fwd || rev)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ClearanceRule",
            &[
                ("from_class", repr_of(&self.from_class, py)?),
                ("to_class", repr_of(&self.to_class, py)?),
                ("min_mm", repr_of(&self.min_mm, py)?),
                ("description", repr_of(&self.description, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ClearanceRule"))
    }
}

// ---------------------------------------------------------------------------
// ZoneDefinition
// ---------------------------------------------------------------------------

/// Zone definition from PCL.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ZoneDefinition {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub bounds: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_classes: Py<PyAny>,
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
}

impl ZoneDefinition {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.bounds),
            same(py, &self.net_classes),
            same(py, &self.components),
        ]
    }
}

#[pymethods]
impl ZoneDefinition {
    #[new]
    #[pyo3(signature = (name, bounds, net_classes=None, components=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        bounds: &Bound<'_, PyAny>,
        net_classes: Option<&Bound<'_, PyAny>>,
        components: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            bounds: bounds.clone().unbind(),
            net_classes: list_or_new(py, net_classes)?,
            components: list_or_new(py, components)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ZoneDefinition",
            &[
                ("name", repr_of(&self.name, py)?),
                ("bounds", repr_of(&self.bounds, py)?),
                ("net_classes", repr_of(&self.net_classes, py)?),
                ("components", repr_of(&self.components, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ZoneDefinition"))
    }
}

// ---------------------------------------------------------------------------
// LoopConstraint
// ---------------------------------------------------------------------------

/// Critical loop constraint from PCL.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct LoopConstraint {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub nets: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_area_mm2: Py<PyAny>,
    #[pyo3(get, set)]
    pub weight: Py<PyAny>,
    #[pyo3(get, set)]
    pub description: Py<PyAny>,
}

impl LoopConstraint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.nets),
            same(py, &self.max_area_mm2),
            same(py, &self.weight),
            same(py, &self.description),
        ]
    }
}

#[pymethods]
impl LoopConstraint {
    #[new]
    #[pyo3(signature = (name, nets, max_area_mm2, weight=None, description=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        nets: &Bound<'_, PyAny>,
        max_area_mm2: &Bound<'_, PyAny>,
        weight: Option<&Bound<'_, PyAny>>,
        description: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            nets: nets.clone().unbind(),
            max_area_mm2: max_area_mm2.clone().unbind(),
            weight: opt_or(py, weight, 1.0_f64)?,
            description: opt_or(py, description, "")?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "LoopConstraint",
            &[
                ("name", repr_of(&self.name, py)?),
                ("nets", repr_of(&self.nets, py)?),
                ("max_area_mm2", repr_of(&self.max_area_mm2, py)?),
                ("weight", repr_of(&self.weight, py)?),
                ("description", repr_of(&self.description, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("LoopConstraint"))
    }
}

// ---------------------------------------------------------------------------
// ThermalConstraint
// ---------------------------------------------------------------------------

/// Thermal constraint from PCL.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ThermalConstraint {
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
    #[pyo3(get, set)]
    pub prefer_edge: Py<PyAny>,
    #[pyo3(get, set)]
    pub min_spacing_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_distance_from_edge_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub description: Py<PyAny>,
}

impl ThermalConstraint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.components),
            same(py, &self.prefer_edge),
            same(py, &self.min_spacing_mm),
            same(py, &self.max_distance_from_edge_mm),
            same(py, &self.description),
        ]
    }
}

#[pymethods]
impl ThermalConstraint {
    #[new]
    #[pyo3(signature = (components, prefer_edge=None, min_spacing_mm=None, max_distance_from_edge_mm=None, description=None))]
    fn new(
        py: Python<'_>,
        components: &Bound<'_, PyAny>,
        prefer_edge: Option<&Bound<'_, PyAny>>,
        min_spacing_mm: Option<&Bound<'_, PyAny>>,
        max_distance_from_edge_mm: Option<&Bound<'_, PyAny>>,
        description: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            components: components.clone().unbind(),
            prefer_edge: opt_or(py, prefer_edge, false)?,
            min_spacing_mm: opt_or(py, min_spacing_mm, 0.0_f64)?,
            max_distance_from_edge_mm: opt_or(py, max_distance_from_edge_mm, 100.0_f64)?,
            description: opt_or(py, description, "")?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ThermalConstraint",
            &[
                ("components", repr_of(&self.components, py)?),
                ("prefer_edge", repr_of(&self.prefer_edge, py)?),
                ("min_spacing_mm", repr_of(&self.min_spacing_mm, py)?),
                (
                    "max_distance_from_edge_mm",
                    repr_of(&self.max_distance_from_edge_mm, py)?,
                ),
                ("description", repr_of(&self.description, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ThermalConstraint"))
    }
}

// ---------------------------------------------------------------------------
// GroupConstraint
// ---------------------------------------------------------------------------

/// Component group constraint from PCL.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct GroupConstraint {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_spread_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub zone: Py<PyAny>,
    #[pyo3(get, set)]
    pub proximity_rules: Py<PyAny>,
    #[pyo3(get, set)]
    pub description: Py<PyAny>,
}

impl GroupConstraint {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.components),
            same(py, &self.max_spread_mm),
            same(py, &self.zone),
            same(py, &self.proximity_rules),
            same(py, &self.description),
        ]
    }
}

#[pymethods]
impl GroupConstraint {
    #[new]
    #[pyo3(signature = (name, components, max_spread_mm=None, zone=None, proximity_rules=None, description=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        components: &Bound<'_, PyAny>,
        max_spread_mm: Option<&Bound<'_, PyAny>>,
        zone: Option<&Bound<'_, PyAny>>,
        proximity_rules: Option<&Bound<'_, PyAny>>,
        description: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            components: components.clone().unbind(),
            max_spread_mm: opt_or(py, max_spread_mm, 100.0_f64)?,
            zone: opt_or_none(py, zone),
            proximity_rules: list_or_new(py, proximity_rules)?,
            description: opt_or(py, description, "")?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "GroupConstraint",
            &[
                ("name", repr_of(&self.name, py)?),
                ("components", repr_of(&self.components, py)?),
                ("max_spread_mm", repr_of(&self.max_spread_mm, py)?),
                ("zone", repr_of(&self.zone, py)?),
                ("proximity_rules", repr_of(&self.proximity_rules, py)?),
                ("description", repr_of(&self.description, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("GroupConstraint"))
    }
}

// ---------------------------------------------------------------------------
// ConstraintSet
// ---------------------------------------------------------------------------

/// Complete set of constraints loaded from PCL YAML.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ConstraintSet {
    #[pyo3(get, set)]
    pub clearances: Py<PyAny>,
    #[pyo3(get, set)]
    pub zones: Py<PyAny>,
    #[pyo3(get, set)]
    pub critical_loops: Py<PyAny>,
    #[pyo3(get, set)]
    pub thermal_constraints: Py<PyAny>,
    #[pyo3(get, set)]
    pub component_groups: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_classes: Py<PyAny>,
    #[pyo3(get, set)]
    pub voltage_domains: Py<PyAny>,
    #[pyo3(get, set)]
    pub hv_clearance_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub board_width: Py<PyAny>,
    #[pyo3(get, set)]
    pub board_height: Py<PyAny>,
}

impl ConstraintSet {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.clearances),
            same(py, &self.zones),
            same(py, &self.critical_loops),
            same(py, &self.thermal_constraints),
            same(py, &self.component_groups),
            same(py, &self.net_classes),
            same(py, &self.voltage_domains),
            same(py, &self.hv_clearance_mm),
            same(py, &self.board_width),
            same(py, &self.board_height),
        ]
    }
}

#[pymethods]
impl ConstraintSet {
    #[new]
    #[pyo3(signature = (clearances=None, zones=None, critical_loops=None, thermal_constraints=None, component_groups=None, net_classes=None, voltage_domains=None, hv_clearance_mm=None, board_width=None, board_height=None))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        clearances: Option<&Bound<'_, PyAny>>,
        zones: Option<&Bound<'_, PyAny>>,
        critical_loops: Option<&Bound<'_, PyAny>>,
        thermal_constraints: Option<&Bound<'_, PyAny>>,
        component_groups: Option<&Bound<'_, PyAny>>,
        net_classes: Option<&Bound<'_, PyAny>>,
        voltage_domains: Option<&Bound<'_, PyAny>>,
        hv_clearance_mm: Option<&Bound<'_, PyAny>>,
        board_width: Option<&Bound<'_, PyAny>>,
        board_height: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            clearances: list_or_new(py, clearances)?,
            zones: list_or_new(py, zones)?,
            critical_loops: list_or_new(py, critical_loops)?,
            thermal_constraints: list_or_new(py, thermal_constraints)?,
            component_groups: list_or_new(py, component_groups)?,
            net_classes: dict_or_new(py, net_classes)?,
            voltage_domains: dict_or_new(py, voltage_domains)?,
            hv_clearance_mm: opt_or(py, hv_clearance_mm, 10.0_f64)?,
            board_width: opt_or(py, board_width, 100.0_f64)?,
            board_height: opt_or(py, board_height, 100.0_f64)?,
        })
    }

    /// First rule whose `applies_to(class_a, class_b)` is true, else `0.0`.
    fn get_clearance(
        &self,
        py: Python<'_>,
        class_a: &Bound<'_, PyAny>,
        class_b: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyAny>> {
        for rule in self.clearances.bind(py).try_iter()? {
            let rule = rule?;
            if rule
                .call_method1("applies_to", (class_a, class_b))?
                .is_truthy()?
            {
                return Ok(rule.getattr("min_mm")?.unbind());
            }
        }
        0.0_f64.into_py_any(py)
    }

    /// Zone by name, or None.
    fn get_zone(&self, py: Python<'_>, name: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            if zone.getattr("name")?.eq(name)? {
                return Ok(zone.unbind());
            }
        }
        Ok(py.None())
    }

    /// Loop by name, or None.
    fn get_loop(&self, py: Python<'_>, name: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        for loop_ in self.critical_loops.bind(py).try_iter()? {
            let loop_ = loop_?;
            if loop_.getattr("name")?.eq(name)? {
                return Ok(loop_.unbind());
            }
        }
        Ok(py.None())
    }

    /// Group by name, or None.
    fn get_group(&self, py: Python<'_>, name: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        for group in self.component_groups.bind(py).try_iter()? {
            let group = group?;
            if group.getattr("name")?.eq(name)? {
                return Ok(group.unbind());
            }
        }
        Ok(py.None())
    }

    /// Verbatim `from_dict` marshalling (clearances as dict "A-B" or list).
    #[classmethod]
    fn from_dict(cls: &Bound<'_, PyType>, data: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let empty_list = PyList::empty(py);

        // clearances: dict "A-B" -> value, or list of rule dicts.
        let clearances = PyList::empty(py);
        let clearances_data = mapping_get(py, data, "clearances", empty_list.clone())?;
        let dict_ty = py.get_type::<PyDict>();
        if clearances_data.is_instance(&dict_ty)? {
            for (key, value) in clearances_data.cast::<PyDict>()?.iter() {
                let parts = key.call_method1("split", ("-",))?;
                let parts = parts.extract::<Vec<String>>()?;
                if parts.len() == 2 {
                    let min_mm = py_float(py, &value)?;
                    let rule = ClearanceRule {
                        from_class: parts[0].clone().into_py_any(py)?,
                        to_class: parts[1].clone().into_py_any(py)?,
                        min_mm,
                        description: String::new().into_py_any(py)?,
                    };
                    clearances.append(Py::new(py, rule)?)?;
                }
            }
        } else {
            for rule_data in clearances_data.try_iter()? {
                let rule_data = rule_data?;
                let from_class = mapping_get(py, &rule_data, "from", "*")?;
                let to_class = mapping_get(py, &rule_data, "to", "*")?;
                let min_mm = mapping_get(py, &rule_data, "clearance_mm", 0.0)?;
                let description = mapping_get(py, &rule_data, "description", "")?;
                let rule = ClearanceRule {
                    from_class: from_class.unbind(),
                    to_class: to_class.unbind(),
                    min_mm: min_mm.unbind(),
                    description: description.unbind(),
                };
                clearances.append(Py::new(py, rule)?)?;
            }
        }

        let zones = PyList::empty(py);
        for zone_data in mapping_get(py, data, "zones", empty_list.clone())?.try_iter()? {
            let zone_data = zone_data?;
            let name = zone_data.get_item("name")?;
            let bounds = mapping_get(py, &zone_data, "bounds", vec![0, 0, 100, 100])?;
            let net_classes = mapping_get(py, &zone_data, "net_classes", empty_list.clone())?;
            let components = mapping_get(py, &zone_data, "components", empty_list.clone())?;
            let zone = ZoneDefinition {
                name: name.clone().unbind(),
                bounds: py_tuple(py, &bounds)?,
                net_classes: net_classes.clone().unbind(),
                components: components.clone().unbind(),
            };
            zones.append(Py::new(py, zone)?)?;
        }

        let loops = PyList::empty(py);
        for loop_data in mapping_get(py, data, "critical_loops", empty_list.clone())?.try_iter()? {
            let loop_data = loop_data?;
            let name = loop_data.get_item("name")?;
            let nets = mapping_get(py, &loop_data, "nets", empty_list.clone())?;
            let max_area = mapping_get(py, &loop_data, "max_area_mm2", 100.0)?;
            let weight = mapping_get(py, &loop_data, "weight", 1.0)?;
            let description = mapping_get(py, &loop_data, "description", "")?;
            let loop_ = LoopConstraint {
                name: name.clone().unbind(),
                nets: nets.clone().unbind(),
                max_area_mm2: max_area.clone().unbind(),
                weight: weight.clone().unbind(),
                description: description.clone().unbind(),
            };
            loops.append(Py::new(py, loop_)?)?;
        }

        let thermal = PyList::empty(py);
        for t_data in mapping_get(py, data, "thermal", empty_list.clone())?.try_iter()? {
            let t_data = t_data?;
            let components = mapping_get(py, &t_data, "components", empty_list.clone())?;
            let prefer_edge = mapping_get(py, &t_data, "prefer_edge", false)?;
            let min_spacing = mapping_get(py, &t_data, "min_spacing_mm", 0.0)?;
            let max_dist = mapping_get(py, &t_data, "max_distance_from_edge_mm", 100.0)?;
            let description = mapping_get(py, &t_data, "description", "")?;
            let t = ThermalConstraint {
                components: components.clone().unbind(),
                prefer_edge: prefer_edge.clone().unbind(),
                min_spacing_mm: min_spacing.clone().unbind(),
                max_distance_from_edge_mm: max_dist.clone().unbind(),
                description: description.clone().unbind(),
            };
            thermal.append(Py::new(py, t)?)?;
        }

        let groups = PyList::empty(py);
        for g_data in mapping_get(py, data, "groups", empty_list.clone())?.try_iter()? {
            let g_data = g_data?;
            let name = g_data.get_item("name")?;
            let components = mapping_get(py, &g_data, "components", empty_list.clone())?;
            let max_spread = mapping_get(py, &g_data, "max_spread_mm", 100.0)?;
            let zone = mapping_get(py, &g_data, "zone", py.None())?;
            let prox = mapping_get(py, &g_data, "proximity", empty_list.clone())?;
            let description = mapping_get(py, &g_data, "description", "")?;
            let g = GroupConstraint {
                name: name.clone().unbind(),
                components: components.clone().unbind(),
                max_spread_mm: max_spread.clone().unbind(),
                zone: zone.clone().unbind(),
                proximity_rules: prox.clone().unbind(),
                description: description.clone().unbind(),
            };
            groups.append(Py::new(py, g)?)?;
        }

        let board = mapping_get(py, data, "board", PyDict::new(py))?;
        let cs = ConstraintSet {
            clearances: clearances.into(),
            zones: zones.into(),
            critical_loops: loops.into(),
            thermal_constraints: thermal.into(),
            component_groups: groups.into(),
            net_classes: mapping_get(py, data, "net_classes", PyDict::new(py))?.unbind(),
            voltage_domains: mapping_get(py, data, "voltage_domains", PyDict::new(py))?.unbind(),
            hv_clearance_mm: mapping_get(py, data, "hv_clearance_mm", 10.0)?.unbind(),
            board_width: mapping_get(py, &board, "width_mm", 100.0)?.unbind(),
            board_height: mapping_get(py, &board, "height_mm", 100.0)?.unbind(),
        };
        Ok(Py::new(py, cs)?.into_any())
    }

    /// Verbatim `from_yaml`: `yaml.safe_load(open(path))` then `from_dict`.
    #[classmethod]
    fn from_yaml(cls: &Bound<'_, PyType>, path: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = cls.py();
        let f = builtins(py)?.getattr("open")?.call1((path,))?;
        let data = PyModule::import(py, "yaml")?
            .getattr("safe_load")?
            .call1((&f,))?;
        let _ = f.call_method0("close");
        Self::from_dict(cls, &data)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let clearances = PyList::empty(py);
        for rule in self.clearances.bind(py).try_iter()? {
            let rule = rule?;
            let entry = PyDict::new(py);
            entry.set_item("from", rule.getattr("from_class")?)?;
            entry.set_item("to", rule.getattr("to_class")?)?;
            entry.set_item("clearance_mm", rule.getattr("min_mm")?)?;
            entry.set_item("description", rule.getattr("description")?)?;
            clearances.append(entry)?;
        }
        let zones = PyList::empty(py);
        for zone in self.zones.bind(py).try_iter()? {
            let zone = zone?;
            let entry = PyDict::new(py);
            entry.set_item("name", zone.getattr("name")?)?;
            entry.set_item("bounds", py_list_of(py, &zone.getattr("bounds")?)?)?;
            entry.set_item("net_classes", zone.getattr("net_classes")?)?;
            entry.set_item("components", zone.getattr("components")?)?;
            zones.append(entry)?;
        }
        let loops = PyList::empty(py);
        for loop_ in self.critical_loops.bind(py).try_iter()? {
            let loop_ = loop_?;
            let entry = PyDict::new(py);
            entry.set_item("name", loop_.getattr("name")?)?;
            entry.set_item("nets", loop_.getattr("nets")?)?;
            entry.set_item("max_area_mm2", loop_.getattr("max_area_mm2")?)?;
            entry.set_item("weight", loop_.getattr("weight")?)?;
            entry.set_item("description", loop_.getattr("description")?)?;
            loops.append(entry)?;
        }
        let board = PyDict::new(py);
        board.set_item("width_mm", self.board_width.bind(py))?;
        board.set_item("height_mm", self.board_height.bind(py))?;
        let d = PyDict::new(py);
        d.set_item("clearances", clearances)?;
        d.set_item("zones", zones)?;
        d.set_item("critical_loops", loops)?;
        d.set_item("net_classes", self.net_classes.bind(py))?;
        d.set_item("voltage_domains", self.voltage_domains.bind(py))?;
        d.set_item("hv_clearance_mm", self.hv_clearance_mm.bind(py))?;
        d.set_item("board", board)?;
        Ok(d.into())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ConstraintSet",
            &[
                ("clearances", repr_of(&self.clearances, py)?),
                ("zones", repr_of(&self.zones, py)?),
                ("critical_loops", repr_of(&self.critical_loops, py)?),
                (
                    "thermal_constraints",
                    repr_of(&self.thermal_constraints, py)?,
                ),
                ("component_groups", repr_of(&self.component_groups, py)?),
                ("net_classes", repr_of(&self.net_classes, py)?),
                ("voltage_domains", repr_of(&self.voltage_domains, py)?),
                ("hv_clearance_mm", repr_of(&self.hv_clearance_mm, py)?),
                ("board_width", repr_of(&self.board_width, py)?),
                ("board_height", repr_of(&self.board_height, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ConstraintSet"))
    }
}

// ---------------------------------------------------------------------------
// Via / ViaPlacement / TraceSegment / TracePlacement
// ---------------------------------------------------------------------------

/// A single via for DRC clearance and annular ring checks.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct Via {
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub from_layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub to_layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub diameter: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_name: Py<PyAny>,
}

impl Via {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.position),
            same(py, &self.from_layer),
            same(py, &self.to_layer),
            same(py, &self.diameter),
            same(py, &self.drill),
            same(py, &self.net_name),
        ]
    }
}

#[pymethods]
impl Via {
    #[new]
    #[pyo3(signature = (position, from_layer, to_layer, diameter, drill, net_name))]
    fn new(
        _py: Python<'_>,
        position: &Bound<'_, PyAny>,
        from_layer: &Bound<'_, PyAny>,
        to_layer: &Bound<'_, PyAny>,
        diameter: &Bound<'_, PyAny>,
        drill: &Bound<'_, PyAny>,
        net_name: &Bound<'_, PyAny>,
    ) -> Self {
        Self {
            position: position.clone().unbind(),
            from_layer: from_layer.clone().unbind(),
            to_layer: to_layer.clone().unbind(),
            diameter: diameter.clone().unbind(),
            drill: drill.clone().unbind(),
            net_name: net_name.clone().unbind(),
        }
    }

    /// `diameter / 2.0` — Python true division.
    #[getter]
    fn radius<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.diameter.bind(py).div(2.0)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Via",
            &[
                ("position", repr_of(&self.position, py)?),
                ("from_layer", repr_of(&self.from_layer, py)?),
                ("to_layer", repr_of(&self.to_layer, py)?),
                ("diameter", repr_of(&self.diameter, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("net_name", repr_of(&self.net_name, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("Via"))
    }
}

/// Collection of placed vias for DRC checking.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct ViaPlacement {
    #[pyo3(get, set)]
    pub vias: Py<PyAny>,
}

impl ViaPlacement {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.vias)]
    }
}

#[pymethods]
impl ViaPlacement {
    #[new]
    #[pyo3(signature = (vias=None))]
    fn new(py: Python<'_>, vias: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        Ok(Self {
            vias: list_or_new(py, vias)?,
        })
    }

    #[getter]
    fn via_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.vias.bind(py).len()
    }

    fn get_vias_for_net<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for via in self.vias.bind(py).try_iter()? {
            let via = via?;
            if via.getattr("net_name")?.eq(net_name)? {
                out.append(via)?;
            }
        }
        Ok(out)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ViaPlacement",
            &[("vias", repr_of(&self.vias, py)?)],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("ViaPlacement"))
    }
}

/// A single trace segment for DRC clearance checks.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct TraceSegment {
    #[pyo3(get, set)]
    pub net_name: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub start: Py<PyAny>,
    #[pyo3(get, set)]
    pub end: Py<PyAny>,
}

impl TraceSegment {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.net_name),
            same(py, &self.layer),
            same(py, &self.width),
            same(py, &self.start),
            same(py, &self.end),
        ]
    }
}

#[pymethods]
impl TraceSegment {
    #[new]
    #[pyo3(signature = (net_name, layer, width, start, end))]
    fn new(
        _py: Python<'_>,
        net_name: &Bound<'_, PyAny>,
        layer: &Bound<'_, PyAny>,
        width: &Bound<'_, PyAny>,
        start: &Bound<'_, PyAny>,
        end: &Bound<'_, PyAny>,
    ) -> Self {
        Self {
            net_name: net_name.clone().unbind(),
            layer: layer.clone().unbind(),
            width: width.clone().unbind(),
            start: start.clone().unbind(),
            end: end.clone().unbind(),
        }
    }

    /// `math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2)` — the
    /// `** 2` is Python float pow (libm), NOT `x*x`.
    #[getter]
    fn length(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dx = self
            .end
            .bind(py)
            .get_item(0)?
            .sub(self.start.bind(py).get_item(0)?)?;
        let dy = self
            .end
            .bind(py)
            .get_item(1)?
            .sub(self.start.bind(py).get_item(1)?)?;
        let sum = dx.pow(2, py.None())?.add(dy.pow(2, py.None())?)?;
        math_sqrt(py, &sum)
    }

    /// Axis-aligned bounding box around the segment's half-width.
    #[getter]
    fn bounding_box<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        let hw = self.width.bind(py).div(2.0)?;
        let sx0 = self.start.bind(py).get_item(0)?;
        let sy0 = self.start.bind(py).get_item(1)?;
        let ex0 = self.end.bind(py).get_item(0)?;
        let ey0 = self.end.bind(py).get_item(1)?;
        let x_min = py_min2(py, &sx0, &ex0)?.sub(&hw)?;
        let y_min = py_min2(py, &sy0, &ey0)?.sub(&hw)?;
        let x_max = py_max2(py, &sx0, &ex0)?.add(&hw)?;
        let y_max = py_max2(py, &sy0, &ey0)?.add(&hw)?;
        PyTuple::new(py, [x_min, y_min, x_max, y_max])
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "TraceSegment",
            &[
                ("net_name", repr_of(&self.net_name, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("width", repr_of(&self.width, py)?),
                ("start", repr_of(&self.start, py)?),
                ("end", repr_of(&self.end, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("TraceSegment"))
    }
}

/// Collection of routed trace segments for DRC checking.
#[pyclass(dict, module = "temper_drc_rs")]
#[derive(Debug)]
pub struct TracePlacement {
    #[pyo3(get, set)]
    pub segments: Py<PyAny>,
}

impl TracePlacement {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.segments)]
    }
}

#[pymethods]
impl TracePlacement {
    #[new]
    #[pyo3(signature = (segments=None))]
    fn new(py: Python<'_>, segments: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        Ok(Self {
            segments: list_or_new(py, segments)?,
        })
    }

    #[getter]
    fn segment_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.segments.bind(py).len()
    }

    fn get_segments_for_net<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for seg in self.segments.bind(py).try_iter()? {
            let seg = seg?;
            if seg.getattr("net_name")?.eq(net_name)? {
                out.append(seg)?;
            }
        }
        Ok(out)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "TracePlacement",
            &[("segments", repr_of(&self.segments, py)?)],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("TracePlacement"))
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Register the contract pyclasses on the `temper_drc_rs` module.
#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, pyo3::types::PyModule>) -> PyResult<()> {
    m.add_class::<Severity>()?;
    m.add_class::<Location>()?;
    m.add_class::<Issue>()?;
    m.add_class::<CheckResult>()?;
    m.add_class::<RunResult>()?;
    m.add_class::<ComponentPlacement>()?;
    m.add_class::<Placement>()?;
    m.add_class::<ClearanceRule>()?;
    m.add_class::<ZoneDefinition>()?;
    m.add_class::<LoopConstraint>()?;
    m.add_class::<ThermalConstraint>()?;
    m.add_class::<GroupConstraint>()?;
    m.add_class::<ConstraintSet>()?;
    m.add_class::<Via>()?;
    m.add_class::<ViaPlacement>()?;
    m.add_class::<TraceSegment>()?;
    m.add_class::<TracePlacement>()?;
    Ok(())
}

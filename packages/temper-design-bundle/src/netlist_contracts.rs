//! Netlist data model — Wave 4 **Phase 3, candidate 1** (part 1 of 2).
//!
//! Python reference: `temper_placer/core/netlist.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/_netlist_py_oracle.py` (commit
//! `e799183c4`). The pyo3 pyclasses here must reproduce that implementation
//! bit-identically, **including the concrete Python type of every field and
//! every returned numpy array's dtype**; the differential test
//! `packages/temper-placer/tests/core/test_netlist_rust_differential.py` is
//! the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! The pre-migration contracts are **plain `@dataclass`es**, and a dataclass
//! performs *no* coercion in `__init__`: `Component("R1", "fp", (1, 2))`
//! stores `int` bounds, and `Component.width` then returns `int` `1`, not
//! `1.0`. A Rust field typed `f64` would silently widen every such value and
//! change `repr`, `==` against `1`-vs-`1.0`-sensitive code, and downstream
//! `numpy` dtype promotion. Storing each field as the exact Python object the
//! caller passed — and doing arithmetic through Python's own operators
//! (`PyAnyMethods::sub`/`mul`/`div`) — makes type preservation true *by
//! construction* rather than by test coverage. The same choice is already
//! established in `design_rules.rs` (`Py<PyDict>`/`Py<PyList>` held
//! opaquely).
//!
//! This also preserves **object identity** for the mutable container fields,
//! which the repo depends on: `io/_parse_nets.py:50` does
//! `nets_dict[pin.net].pins.append(...)`, mutating `Net.pins` in place. A
//! getter that rebuilt a fresh list would silently drop those appends.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Rather than re-deriving CPython's `repr(float)`/`repr(str)` rules (the
//! `py_float_str`/`py_str_repr` helpers the earlier Phase-2 migrations
//! needed), these pyclasses call **CPython's own `repr()`** on each stored
//! field object and splice the results into the dataclass layout
//! `Cls(f1=r1, f2=r2, ...)`. Equality builds the same field tuple both sides
//! and defers to Python `==` on tuples, exactly as a generated dataclass
//! `__eq__` does (including the `NotImplemented` return for a foreign
//! class). This is bit-exactness by delegation, not by replication.
//!
//! # numpy arrays
//!
//! `get_bounds_array` / `get_fixed_mask` / `build_adjacency_matrix` return
//! numpy arrays. They are materialized by calling **numpy itself**
//! (`numpy.array(obj, dtype=...)`) with the identical argument object the
//! oracle builds, so the dtype and every element bit pattern are numpy's own
//! — there is no Rust-side float conversion that could widen `float32` to
//! `float64`. Compare `#688`'s judgment to keep `yaml.safe_load` on the
//! Python side rather than re-tokenize.
//!
//! # Deliberately NOT migrated (R3, see `VERIFICATION.md`)
//!
//! `compute_eigenvector_centrality` stays in Python: it is
//! `numpy.linalg.eigh`, i.e. LAPACK `?syevd`. Its output is not reproducible
//! bit-identically by any independent implementation, and a Rust wrapper
//! that merely re-called `numpy.linalg.eigh` would add a boundary crossing
//! while proving nothing. Named blocker recorded in `VERIFICATION.md`.

use pyo3::exceptions::{PyKeyError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PySet, PyString, PyTuple};
use pyo3::IntoPyObjectExt;

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/// `repr(obj)` as CPython renders it, used to assemble dataclass reprs.
pub(crate) fn repr_of(obj: &Py<PyAny>, py: Python<'_>) -> PyResult<String> {
    obj.bind(py).repr()?.extract()
}

/// Assemble a generated-dataclass `__repr__`: `Cls(name=repr, ...)`.
///
/// Only fields with `repr=True` are passed in, in declaration order — the
/// same contract `dataclasses._repr_fn` implements.
pub(crate) fn dataclass_repr(class: &str, fields: &[(&str, String)]) -> String {
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
pub(crate) fn dataclass_eq<'py>(
    py: Python<'py>,
    this_class: &Bound<'py, PyAny>,
    other: &Bound<'py, PyAny>,
    lhs: &[Py<PyAny>],
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

/// `hash(tuple(fields))` -- what a `frozen=True, eq=True` dataclass does.
/// Propagates `TypeError: unhashable type` verbatim when a field is
/// unhashable (e.g. a `LayerStackup` holding non-frozen `Layer`s).
pub(crate) fn dataclass_hash(py: Python<'_>, fields: &[Py<PyAny>]) -> PyResult<isize> {
    PyTuple::new(py, fields.iter().map(|v| v.bind(py)))?.hash()
}

/// Clone an owned handle to the same underlying Python object (NOT a copy) --
/// preserves identity for mutable containers.
pub(crate) fn same(py: Python<'_>, obj: &Py<PyAny>) -> Py<PyAny> {
    obj.clone_ref(py)
}

/// The `TypeError` CPython raises for a class whose `__hash__` is `None` --
/// which is every `eq=True, frozen=False` dataclass here.
///
/// pyo3 already makes a pyclass with `__eq__` unhashable, but its message
/// interpolates the type's *dotted* `tp_name`
/// (`temper_design_bundle_python.board_contracts.Layer`) where CPython's
/// heap types report the bare `__name__` (`Layer`). Raising explicitly keeps
/// the message byte-identical to the oracle's.
pub(crate) fn unhashable(class: &str) -> PyErr {
    pyo3::exceptions::PyTypeError::new_err(format!("unhashable type: '{class}'"))
}

/// Iterable unpacking with CPython's own arity diagnostics.
///
/// `a, b = value` raises `cannot unpack non-iterable X object`,
/// `not enough values to unpack (expected N, got M)` or
/// `too many values to unpack (expected N)`. A pyo3 tuple `extract()` raises
/// different text *and* rejects lists outright, so the unpack is written out.
pub(crate) fn unpack<'py>(
    value: &Bound<'py, PyAny>,
    expected: usize,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut iter = match value.try_iter() {
        Ok(iter) => iter,
        Err(_) => {
            return Err(PyTypeError::new_err(format!(
                "cannot unpack non-iterable {} object",
                value.get_type().name()?
            )));
        }
    };
    let mut out = Vec::with_capacity(expected);
    for _ in 0..expected {
        match iter.next() {
            Some(item) => out.push(item?),
            None => {
                return Err(PyValueError::new_err(format!(
                    "not enough values to unpack (expected {expected}, got {})",
                    out.len()
                )));
            }
        }
    }
    if iter.next().is_some() {
        return Err(PyValueError::new_err(format!(
            "too many values to unpack (expected {expected})"
        )));
    }
    Ok(out)
}

/// `a, b = value` -- the two-element unpack used for `(component_ref, pin_name)`.
pub(crate) fn unpack2<'py>(
    value: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let mut items = unpack(value, 2)?.into_iter();
    match (items.next(), items.next()) {
        (Some(a), Some(b)) => Ok((a, b)),
        // `unpack` guarantees exactly 2 on the Ok path.
        _ => Err(PyValueError::new_err(
            "not enough values to unpack (expected 2, got 0)",
        )),
    }
}

/// `numpy` module handle. Imported lazily at call time so importing the
/// extension never forces numpy, matching the oracle (which imports numpy at
/// module scope, but the extension is imported by far more callers).
fn numpy(py: Python<'_>) -> PyResult<Bound<'_, PyModule>> {
    PyModule::import(py, "numpy")
}

/// `numpy.array(obj, dtype=<numpy.NAME>)` -- the exact call the oracle makes.
fn np_array<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    dtype: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let np = numpy(py)?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr(dtype)?)?;
    np.getattr("array")?.call((obj,), Some(&kwargs))
}

/// Default a `None` argument to a freshly created empty `list` -- what
/// `field(default_factory=list)` does on every construction.
pub(crate) fn list_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => PyList::empty(py).into_py_any(py),
    }
}

/// Default a `None` argument to a freshly created empty `dict`.
pub(crate) fn dict_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => PyDict::new(py).into_py_any(py),
    }
}

/// Wrap a Rust value as the Python object the oracle's literal would produce.
fn py_obj<'py, T>(py: Python<'py>, value: T) -> PyResult<Py<PyAny>>
where
    T: IntoPyObject<'py>,
{
    value.into_bound_py_any(py).map(Bound::unbind)
}

// ---------------------------------------------------------------------------
// Pin
// ---------------------------------------------------------------------------

/// A pin on a component (mirrors `Pin` in `temper_placer/core/netlist.py`).
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.netlist_contracts")]
#[derive(Debug)]
pub struct Pin {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub number: Py<PyAny>,
    #[pyo3(get, set)]
    pub position: Py<PyAny>,
    #[pyo3(get, set)]
    pub net: Py<PyAny>,
    #[pyo3(get, set)]
    pub width: Py<PyAny>,
    #[pyo3(get, set)]
    pub height: Py<PyAny>,
    #[pyo3(get, set)]
    pub shape: Py<PyAny>,
    #[pyo3(get, set)]
    pub layer: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill: Py<PyAny>,
    #[pyo3(get, set)]
    pub is_pth: Py<PyAny>,
    #[pyo3(get, set)]
    pub roundrect_ratio: Py<PyAny>,
    #[pyo3(get, set)]
    pub pad_rotation_deg: Py<PyAny>,
}

impl Pin {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.number),
            same(py, &self.position),
            same(py, &self.net),
            same(py, &self.width),
            same(py, &self.height),
            same(py, &self.shape),
            same(py, &self.layer),
            same(py, &self.drill),
            same(py, &self.is_pth),
            same(py, &self.roundrect_ratio),
            same(py, &self.pad_rotation_deg),
        ]
    }
}

#[pymethods]
impl Pin {
    #[new]
    #[pyo3(signature = (
        name,
        number,
        position,
        net=None,
        width=None,
        height=None,
        shape=None,
        layer=None,
        drill=None,
        is_pth=None,
        roundrect_ratio=None,
        pad_rotation_deg=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        number: &Bound<'_, PyAny>,
        position: &Bound<'_, PyAny>,
        net: Option<&Bound<'_, PyAny>>,
        width: Option<&Bound<'_, PyAny>>,
        height: Option<&Bound<'_, PyAny>>,
        shape: Option<&Bound<'_, PyAny>>,
        layer: Option<&Bound<'_, PyAny>>,
        drill: Option<&Bound<'_, PyAny>>,
        is_pth: Option<&Bound<'_, PyAny>>,
        roundrect_ratio: Option<&Bound<'_, PyAny>>,
        pad_rotation_deg: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // `net=None` is the dataclass default AND a legal explicit value; both
        // land on Python `None`, so `Option::None` collapsing to `py.None()`
        // is faithful here (unlike the list/dict defaults above).
        Ok(Self {
            name: name.clone().unbind(),
            number: number.clone().unbind(),
            position: position.clone().unbind(),
            net: net.map_or_else(|| py.None(), |v| v.clone().unbind()),
            width: opt_or(py, width, 1.0_f64)?,
            height: opt_or(py, height, 1.0_f64)?,
            shape: opt_or(py, shape, "rect")?,
            layer: opt_or(py, layer, "F.Cu")?,
            drill: opt_or(py, drill, 0.0_f64)?,
            is_pth: opt_or(py, is_pth, false)?,
            roundrect_ratio: opt_or(py, roundrect_ratio, 0.25_f64)?,
            pad_rotation_deg: opt_or(py, pad_rotation_deg, 0.0_f64)?,
        })
    }

    /// Recommended solder mask expansion for this pin.
    ///
    /// Oracle: `return 0.15 if self.is_pth else 0.1`. `is_pth` is tested for
    /// Python truthiness (`bool(obj)`), not identity with `True`.
    #[getter]
    fn mask_expansion(&self, py: Python<'_>) -> PyResult<f64> {
        Ok(if self.is_pth.bind(py).is_truthy()? {
            0.15
        } else {
            0.1
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Pin",
            &[
                ("name", repr_of(&self.name, py)?),
                ("number", repr_of(&self.number, py)?),
                ("position", repr_of(&self.position, py)?),
                ("net", repr_of(&self.net, py)?),
                ("width", repr_of(&self.width, py)?),
                ("height", repr_of(&self.height, py)?),
                ("shape", repr_of(&self.shape, py)?),
                ("layer", repr_of(&self.layer, py)?),
                ("drill", repr_of(&self.drill, py)?),
                ("is_pth", repr_of(&self.is_pth, py)?),
                ("roundrect_ratio", repr_of(&self.roundrect_ratio, py)?),
                ("pad_rotation_deg", repr_of(&self.pad_rotation_deg, py)?),
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
        Err(unhashable("Pin"))
    }
}

/// `Option`-or-literal-default helper for scalar dataclass defaults.
pub(crate) fn opt_or<'py, T>(py: Python<'py>, value: Option<&Bound<'py, PyAny>>, default: T) -> PyResult<Py<PyAny>>
where
    T: IntoPyObject<'py>,
{
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => py_obj(py, default),
    }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/// A component to be placed on the PCB (mirrors `Component` in
/// `temper_placer/core/netlist.py` — distinct from the *board* `Component`).
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.netlist_contracts")]
#[derive(Debug)]
pub struct Component {
    #[pyo3(get, set, name = "ref")]
    pub ref_: Py<PyAny>,
    #[pyo3(get, set)]
    pub footprint: Py<PyAny>,
    #[pyo3(get, set)]
    pub bounds: Py<PyAny>,
    #[pyo3(get, set)]
    pub pins: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_class: Py<PyAny>,
    #[pyo3(get, set)]
    pub zone: Py<PyAny>,
    #[pyo3(get, set)]
    pub fixed: Py<PyAny>,
    #[pyo3(get, set)]
    pub initial_position: Py<PyAny>,
    #[pyo3(get, set)]
    pub initial_rotation_quadrant: Py<PyAny>,
    #[pyo3(get, set)]
    pub initial_side: Py<PyAny>,
    #[pyo3(get, set)]
    pub attributes: Py<PyAny>,
    #[pyo3(get, set)]
    pub tags: Py<PyAny>,
    #[pyo3(get, set)]
    pub sheetpath: Py<PyAny>,
}

impl Component {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.ref_),
            same(py, &self.footprint),
            same(py, &self.bounds),
            same(py, &self.pins),
            same(py, &self.net_class),
            same(py, &self.zone),
            same(py, &self.fixed),
            same(py, &self.initial_position),
            same(py, &self.initial_rotation_quadrant),
            same(py, &self.initial_side),
            same(py, &self.attributes),
            same(py, &self.tags),
            same(py, &self.sheetpath),
        ]
    }
}

#[pymethods]
impl Component {
    #[new]
    #[pyo3(signature = (
        r#ref,
        footprint,
        bounds,
        pins=None,
        net_class=None,
        zone=None,
        fixed=None,
        initial_position=None,
        initial_rotation_quadrant=None,
        initial_side=None,
        attributes=None,
        tags=None,
        sheetpath=None,
    ))]
    #[allow(clippy::too_many_arguments)] // mirrors the dataclass field list
    fn new(
        py: Python<'_>,
        r#ref: &Bound<'_, PyAny>,
        footprint: &Bound<'_, PyAny>,
        bounds: &Bound<'_, PyAny>,
        pins: Option<&Bound<'_, PyAny>>,
        net_class: Option<&Bound<'_, PyAny>>,
        zone: Option<&Bound<'_, PyAny>>,
        fixed: Option<&Bound<'_, PyAny>>,
        initial_position: Option<&Bound<'_, PyAny>>,
        initial_rotation_quadrant: Option<&Bound<'_, PyAny>>,
        initial_side: Option<&Bound<'_, PyAny>>,
        attributes: Option<&Bound<'_, PyAny>>,
        tags: Option<&Bound<'_, PyAny>>,
        sheetpath: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let none = || py.None();
        Ok(Self {
            ref_: r#ref.clone().unbind(),
            footprint: footprint.clone().unbind(),
            bounds: bounds.clone().unbind(),
            pins: list_or_new(py, pins)?,
            net_class: opt_or(py, net_class, "Signal")?,
            zone: zone.map_or_else(none, |v| v.clone().unbind()),
            fixed: opt_or(py, fixed, false)?,
            initial_position: initial_position.map_or_else(none, |v| v.clone().unbind()),
            initial_rotation_quadrant: initial_rotation_quadrant.map_or_else(none, |v| v.clone().unbind()),
            initial_side: initial_side.map_or_else(none, |v| v.clone().unbind()),
            attributes: dict_or_new(py, attributes)?,
            // `field(default_factory=frozenset)` -- a fresh empty frozenset.
            tags: match tags {
                Some(v) => v.clone().unbind(),
                None => py
                    .get_type::<pyo3::types::PyFrozenSet>()
                    .call0()?
                    .unbind()
                    .into_any(),
            },
            sheetpath: sheetpath.map_or_else(none, |v| v.clone().unbind()),
        })
    }

    /// Component width in mm — `self.bounds[0]`, type preserved.
    #[getter]
    fn width<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.bounds.bind(py).get_item(0)
    }

    /// Component height in mm — `self.bounds[1]`, type preserved.
    #[getter]
    fn height<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.bounds.bind(py).get_item(1)
    }

    /// Get a pin by name or number (first match, else `None`).
    ///
    /// **Not a safe physical-pad key when this component's footprint has
    /// duplicate pad numbers.** A footprint can fabricate more than one
    /// physical solder pad under the same pad number/name (this board's
    /// K2/K3, `temper:Relay_SPDT_Schrack-RT314012`, duplicate pads "1",
    /// "3", and "4" -- two physical holes 7.5mm apart per contact, for
    /// 16A current sharing); this method always returns the FIRST match
    /// and gives no signal that a second, physically distinct pad with
    /// the same name exists. Calling it once per `Net.pins` occurrence is
    /// exactly the mistake that made the router print "routed
    /// successfully" for a net while writing zero connecting copper (see
    /// `_pipeline_grid._nth_matching_pin`'s docstring, Python side, for
    /// the full incident). When a component's pin list might contain
    /// duplicate numbers, use [`Component::get_pin_occurrences`] (returns
    /// every match) instead and resolve which occurrence you mean
    /// explicitly -- see `temper_placer.core.pad_identity`
    /// (`PadOccurrence`) for the canonical Python-side helper, and
    /// `pad_occurrence::PadOccurrence` for the Rust-side typed identity.
    /// Safe uses of this method are ones that only need pin
    /// EXISTENCE/net-membership (every occurrence of a duplicated pad
    /// number shares the same net, by construction of what "duplicate
    /// contact pad" means), not a specific physical position.
    fn get_pin<'py>(
        &self,
        py: Python<'py>,
        name_or_number: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            if pin.getattr("name")?.eq(name_or_number)? || pin.getattr("number")?.eq(name_or_number)?
            {
                return Ok(pin);
            }
        }
        Ok(py.None().into_bound(py))
    }

    /// Every pin whose `name` or `number` equals `name_or_number`, in
    /// `self.pins` encounter order -- the general, ambiguity-safe
    /// alternative to [`Component::get_pin`] (see that method's doc for
    /// why the first-match shortcut is unsafe whenever a footprint
    /// duplicates a pad number). Empty list, not `None`, when nothing
    /// matches. Element `i` of the returned list is occurrence `i` in the
    /// sense of `pad_occurrence::PadOccurrence::new(name_or_number, i)`.
    fn get_pin_occurrences<'py>(
        &self,
        py: Python<'py>,
        name_or_number: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            if pin.getattr("name")?.eq(name_or_number)? || pin.getattr("number")?.eq(name_or_number)?
            {
                out.append(pin)?;
            }
        }
        Ok(out)
    }

    /// All pins whose `net` equals `net_name`.
    fn get_pins_for_net<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        for pin in self.pins.bind(py).try_iter()? {
            let pin = pin?;
            if pin.getattr("net")?.eq(net_name)? {
                out.append(pin)?;
            }
        }
        Ok(out)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Component",
            &[
                ("ref", repr_of(&self.ref_, py)?),
                ("footprint", repr_of(&self.footprint, py)?),
                ("bounds", repr_of(&self.bounds, py)?),
                ("pins", repr_of(&self.pins, py)?),
                ("net_class", repr_of(&self.net_class, py)?),
                ("zone", repr_of(&self.zone, py)?),
                ("fixed", repr_of(&self.fixed, py)?),
                ("initial_position", repr_of(&self.initial_position, py)?),
                ("initial_rotation_quadrant", repr_of(&self.initial_rotation_quadrant, py)?),
                ("initial_side", repr_of(&self.initial_side, py)?),
                ("attributes", repr_of(&self.attributes, py)?),
                ("tags", repr_of(&self.tags, py)?),
                ("sheetpath", repr_of(&self.sheetpath, py)?),
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
        Err(unhashable("Component"))
    }
}

// ---------------------------------------------------------------------------
// Net
// ---------------------------------------------------------------------------

/// An electrical net connecting multiple pins (mirrors `Net`).
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.netlist_contracts")]
#[derive(Debug)]
pub struct Net {
    #[pyo3(get, set)]
    pub name: Py<PyAny>,
    #[pyo3(get, set)]
    pub pins: Py<PyAny>,
    #[pyo3(get, set)]
    pub net_class: Py<PyAny>,
    #[pyo3(get, set)]
    pub weight: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_current: Py<PyAny>,
    #[pyo3(get, set)]
    pub voltage_class: Py<PyAny>,
}

impl Net {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.name),
            same(py, &self.pins),
            same(py, &self.net_class),
            same(py, &self.weight),
            same(py, &self.max_current),
            same(py, &self.voltage_class),
        ]
    }
}

#[pymethods]
impl Net {
    #[new]
    #[pyo3(signature = (name, pins, net_class=None, weight=None, max_current=None, voltage_class=None))]
    fn new(
        py: Python<'_>,
        name: &Bound<'_, PyAny>,
        pins: &Bound<'_, PyAny>,
        net_class: Option<&Bound<'_, PyAny>>,
        weight: Option<&Bound<'_, PyAny>>,
        max_current: Option<&Bound<'_, PyAny>>,
        voltage_class: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            name: name.clone().unbind(),
            // `pins` has NO default in the oracle -- it is a required
            // positional, and the caller's list object is stored by identity
            // so `net.pins.append(...)` (io/_parse_nets.py) still lands.
            pins: pins.clone().unbind(),
            net_class: opt_or(py, net_class, "Signal")?,
            weight: opt_or(py, weight, 1.0_f64)?,
            max_current: opt_or(py, max_current, 0.0_f64)?,
            voltage_class: opt_or(py, voltage_class, "LV")?,
        })
    }

    /// Number of pins in this net.
    #[getter]
    fn pin_count(&self, py: Python<'_>) -> PyResult<usize> {
        self.pins.bind(py).len()
    }

    /// Unique component references in this net: `{ref for ref, _ in pins}`.
    fn get_component_refs<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let refs = PyList::empty(py);
        for item in self.pins.bind(py).try_iter()? {
            // Tuple-unpacking `for ref, _ in self.pins` -- a 2-element
            // requirement; a wrong arity raises ValueError in Python, and
            // `get_item(0)` here would not. Unpack explicitly to keep that.
            let item = item?;
            let (r#ref, _pin_name) = unpack2(&item)?;
            refs.append(r#ref)?;
        }
        PySet::new(py, refs.iter())?.into_any().into_bound_py_any(py)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "Net",
            &[
                ("name", repr_of(&self.name, py)?),
                ("pins", repr_of(&self.pins, py)?),
                ("net_class", repr_of(&self.net_class, py)?),
                ("weight", repr_of(&self.weight, py)?),
                ("max_current", repr_of(&self.max_current, py)?),
                ("voltage_class", repr_of(&self.voltage_class, py)?),
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
        Err(unhashable("Net"))
    }
}

// ---------------------------------------------------------------------------
// Netlist
// ---------------------------------------------------------------------------

/// Complete netlist containing all components and nets (mirrors `Netlist`).
///
/// The three `_`-prefixed index fields are real dataclass fields in the
/// oracle: `init=True`, `repr=False`, `compare=True`. They are therefore
/// constructor-accepting, excluded from `__repr__`, and included in `__eq__`
/// — and `__post_init__` overwrites whatever was passed. All four properties
/// are reproduced here.
// `dict`: the dataclasses these replace are ordinary Python classes with a
// `__dict__`, so callers can attach attributes the contract never declared --
// and callers DO. `validation/trace_analyzer.py` and
// `visualization/board_renderer.py` both read `board.traces`, a field that
// exists on no `Board` definition anywhere; it is injected by the KiCad parse
// path. A pyclass without `dict` raises `AttributeError` on the assignment,
// so `dict` is required for behavioural parity, not convenience.
#[pyclass(dict, module = "temper_design_bundle_python.netlist_contracts")]
#[derive(Debug)]
pub struct Netlist {
    #[pyo3(get, set)]
    pub components: Py<PyAny>,
    #[pyo3(get, set)]
    pub nets: Py<PyAny>,
    #[pyo3(get, set, name = "_component_index")]
    pub component_index: Py<PyAny>,
    #[pyo3(get, set, name = "_net_index")]
    pub net_index: Py<PyAny>,
    #[pyo3(get, set, name = "_component_nets")]
    pub component_nets: Py<PyAny>,
}

impl Netlist {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.components),
            same(py, &self.nets),
            same(py, &self.component_index),
            same(py, &self.net_index),
            same(py, &self.component_nets),
        ]
    }
}

#[pymethods]
impl Netlist {
    #[new]
    #[pyo3(signature = (
        components=None,
        nets=None,
        _component_index=None,
        _net_index=None,
        _component_nets=None,
    ))]
    fn new(
        py: Python<'_>,
        components: Option<&Bound<'_, PyAny>>,
        nets: Option<&Bound<'_, PyAny>>,
        _component_index: Option<&Bound<'_, PyAny>>,
        _net_index: Option<&Bound<'_, PyAny>>,
        _component_nets: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let components = list_or_new(py, components)?;
        let nets = list_or_new(py, nets)?;
        // The three index arguments are accepted (they are real `init=True`
        // dataclass fields) and then immediately discarded, because
        // `__post_init__` calls `build_indices()` unconditionally. Evaluating
        // them anyway preserves any error a caller-supplied value would raise.
        let _ = dict_or_new(py, _component_index)?;
        let _ = dict_or_new(py, _net_index)?;
        let _ = dict_or_new(py, _component_nets)?;
        let (component_index, net_index, component_nets) =
            compute_indices(py, components.bind(py), nets.bind(py))?;
        Ok(Self {
            components,
            nets,
            component_index,
            net_index,
            component_nets,
        })
    }

    /// Build lookup indices for efficient queries.
    ///
    /// Rebinds the three index attributes to **fresh** dicts, matching the
    /// oracle's `self._component_index = {...}` rebinding (not in-place
    /// mutation) — code holding a reference to the old dict keeps the old
    /// dict.
    ///
    /// Takes `slf: &Bound<Self>` rather than `&self` so the rebinding goes
    /// through pyo3's checked `borrow_mut`; every Python call is made *before*
    /// the mutable borrow opens, so re-entrant user code (a `ref` property
    /// that calls back in) can never observe a locked object.
    fn build_indices(slf: &Bound<'_, Self>) -> PyResult<()> {
        let py = slf.py();
        let (components, nets) = {
            let this = slf.borrow();
            (this.components.bind(py).clone(), this.nets.bind(py).clone())
        };
        let indices = compute_indices(py, &components, &nets)?;
        let mut this = slf.borrow_mut();
        this.component_index = indices.0;
        this.net_index = indices.1;
        this.component_nets = indices.2;
        Ok(())
    }

    /// Array index for a component by reference (`KeyError` on miss).
    fn get_component_index<'py>(
        &self,
        py: Python<'py>,
        r#ref: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        dict_getitem(self.component_index.bind(py), r#ref)
    }

    /// A component by reference.
    fn get_component<'py>(
        &self,
        py: Python<'py>,
        r#ref: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let idx = dict_getitem(self.component_index.bind(py), r#ref)?;
        self.components.bind(py).get_item(idx.extract::<isize>()?)
    }

    /// A net by name.
    fn get_net<'py>(
        &self,
        py: Python<'py>,
        name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let idx = dict_getitem(self.net_index.bind(py), name)?;
        self.nets.bind(py).get_item(idx.extract::<isize>()?)
    }

    /// All net names connected to a component (`[]` when unknown).
    fn get_component_nets<'py>(
        &self,
        py: Python<'py>,
        r#ref: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        // `dict.get(ref, [])` -- a *fresh* empty list on miss, and the stored
        // list object (by identity) on hit.
        match self.component_nets.bind(py).get_item(r#ref) {
            Ok(value) => Ok(value),
            Err(err) if err.is_instance_of::<PyKeyError>(py) => Ok(PyList::empty(py).into_any()),
            Err(err) => Err(err),
        }
    }

    /// All `(component_ref, pin_name)` for a net.
    fn get_net_pins<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        self.get_net(py, net_name)?.getattr("pins")
    }

    /// Number of components.
    #[getter]
    fn n_components(&self, py: Python<'_>) -> PyResult<usize> {
        self.components.bind(py).len()
    }

    /// Number of nets.
    #[getter]
    fn n_nets(&self, py: Python<'_>) -> PyResult<usize> {
        self.nets.bind(py).len()
    }

    /// `(N, 2)` float32 array of component bounds — built by numpy itself.
    fn get_bounds_array<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let rows = PyList::empty(py);
        for comp in self.components.bind(py).try_iter()? {
            rows.append(comp?.getattr("bounds")?)?;
        }
        np_array(py, rows.as_any(), "float32")
    }

    /// `(N,)` boolean array of fixed components — built by numpy itself.
    fn get_fixed_mask<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        let rows = PyList::empty(py);
        for comp in self.components.bind(py).try_iter()? {
            rows.append(comp?.getattr("fixed")?)?;
        }
        np_array(py, rows.as_any(), "bool_")
    }

    /// Apply a `net_name -> net_class` mapping; returns the number changed.
    fn apply_net_class_mapping(&self, py: Python<'_>, mapping: &Bound<'_, PyAny>) -> PyResult<i64> {
        let mut updated = 0_i64;
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let name = net.getattr("name")?;
            // `if net.name in mapping` then `mapping[net.name]`.
            if mapping.contains(&name)? {
                let new_class = mapping.get_item(&name)?;
                if !net.getattr("net_class")?.eq(&new_class)? {
                    net.setattr("net_class", new_class)?;
                    updated += 1;
                }
            }
        }
        Ok(updated)
    }

    /// Strict variant of `apply_net_class_mapping`: every key in `mapping`
    /// must name a real net on this `Netlist` (checked with an exact,
    /// case-sensitive match against `self.nets`' own names), or the call
    /// raises `ValueError` naming every unresolved key and updates NOTHING
    /// -- as opposed to `apply_net_class_mapping`'s silent per-key skip on a
    /// miss. The two methods coexist deliberately:
    /// `apply_net_class_mapping` is an oracle-parity shim that must stay
    /// bit-identical to `_netlist_py_oracle.py` (see this file's module
    /// docstring), so its silent-skip behavior cannot change here; this is
    /// an additive, opt-in call for sites that want the miss to be loud.
    /// See `docs/evidence/2026-08-11-typed-net-refs-spike.md`.
    fn apply_net_class_mapping_strict(
        &self,
        py: Python<'_>,
        mapping: &Bound<'_, PyAny>,
    ) -> PyResult<i64> {
        let mut known_nets = std::collections::BTreeSet::new();
        for net in self.nets.bind(py).try_iter()? {
            let name: String = net?.getattr("name")?.extract()?;
            known_nets.insert(name);
        }
        let raw: std::collections::BTreeMap<String, String> = mapping.extract()?;

        let resolved = crate::net_class_validation::ValidatedNetClassMap::resolve(
            &known_nets,
            &raw,
        )
        .map_err(|errors| {
            PyValueError::new_err(crate::net_class_validation::format_unresolved(&errors))
        })?;

        // Every key is now known-good against this Netlist's own net names
        // (`resolve` cannot return `Ok` otherwise) -- unlike
        // `apply_net_class_mapping`, nothing here can silently skip a
        // caller-intended assignment.
        let mut updated = 0_i64;
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            if let Some(new_class) = resolved.get(&name)
                && net.getattr("net_class")?.extract::<String>()?.as_str() != new_class
            {
                net.setattr("net_class", new_class)?;
                updated += 1;
            }
        }
        Ok(updated)
    }

    /// Groups of topologically isomorphic components (Weisfeiler-Lehman).
    ///
    /// Transcribed from the oracle, including the `hashlib.md5` label digest
    /// and the `re.match(r"^([a-zA-Z]+)", ref)` prefix rule. Adjacency is
    /// taken from `build_adjacency_matrix` and thresholded at `> 0`; the
    /// counts it holds are exact small integers in `float32`, so the
    /// comparison is exact on both sides.
    #[pyo3(signature = (iterations=2))]
    fn find_isomorphic_groups<'py>(
        &self,
        py: Python<'py>,
        iterations: i64,
    ) -> PyResult<Bound<'py, PyList>> {
        let n = self.components.bind(py).len()?;
        if n == 0 {
            return Ok(PyList::empty(py));
        }

        let re_module = PyModule::import(py, "re")?;
        let hashlib = PyModule::import(py, "hashlib")?;

        // 1. Initial labels: "<footprint>|<ref letter prefix>".
        let mut labels: Vec<String> = Vec::with_capacity(n);
        for comp in self.components.bind(py).try_iter()? {
            let comp = comp?;
            let r#ref = comp.getattr("ref")?;
            let matched = re_module
                .getattr("match")?
                .call1(("^([a-zA-Z]+)", &r#ref))?;
            let prefix: String = if matched.is_none() {
                String::new()
            } else {
                matched.call_method1("group", (1,))?.extract()?
            };
            let footprint: String = comp.getattr("footprint")?.str()?.extract()?;
            labels.push(format!("{footprint}|{prefix}"));
        }

        // Neighbour lists: `np.where(adj[i] > 0)[0].tolist()`.
        let adj = build_adjacency_matrix_impl(py, self.components.bind(py), self.nets.bind(py))?;
        let np = numpy(py)?;
        let mut neighbor_lists: Vec<Vec<usize>> = Vec::with_capacity(n);
        for i in 0..n {
            let row = adj.get_item(i)?;
            // `adj[i] > 0` is an ELEMENTWISE numpy comparison producing a
            // boolean array. `PyAnyMethods::gt` would coerce it with
            // `__bool__` and raise "truth value of an array is ambiguous";
            // `rich_compare` keeps the array.
            let mask = row.rich_compare(0, pyo3::basic::CompareOp::Gt)?;
            let where_ = np.getattr("where")?.call1((mask,))?;
            let idx = where_.get_item(0)?.call_method0("tolist")?;
            neighbor_lists.push(idx.extract()?);
        }

        // 2. Iterative WL refinement.
        for _ in 0..iterations {
            let mut new_labels: Vec<String> = Vec::with_capacity(n);
            for i in 0..n {
                let mut neighbor_labels: Vec<String> = neighbor_lists[i]
                    .iter()
                    .filter_map(|j| labels.get(*j).cloned())
                    .collect();
                neighbor_labels.sort();
                let sig = format!("{}|{}", labels[i], neighbor_labels.join(","));
                let digest = hashlib
                    .getattr("md5")?
                    .call1((PyString::new(py, &sig).call_method0("encode")?,))?
                    .call_method0("hexdigest")?;
                new_labels.push(digest.extract()?);
            }
            labels = new_labels;
        }

        // 3./4. Group by final label (insertion-ordered), keep len > 1.
        let groups_dict = PyDict::new(py);
        for (i, label) in labels.iter().enumerate() {
            let key = PyString::new(py, label);
            match groups_dict.get_item(&key)? {
                Some(bucket) => bucket.cast::<PyList>()?.append(i)?,
                None => {
                    let bucket = PyList::empty(py);
                    bucket.append(i)?;
                    groups_dict.set_item(&key, bucket)?;
                }
            }
        }
        let out = PyList::empty(py);
        for bucket in groups_dict.values() {
            if bucket.len()? > 1 {
                out.append(bucket)?;
            }
        }
        Ok(out)
    }

    /// Validate netlist consistency; returns the error-message list.
    fn validate<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let errors = PyList::empty(py);

        // Duplicate component refs.
        let refs = PyList::empty(py);
        for comp in self.components.bind(py).try_iter()? {
            refs.append(comp?.getattr("ref")?)?;
        }
        if let Some(dups) = duplicates_of(py, &refs)? {
            errors.append(format!("Duplicate component refs: {dups}"))?;
        }

        // Duplicate net names.
        let names = PyList::empty(py);
        for net in self.nets.bind(py).try_iter()? {
            names.append(net?.getattr("name")?)?;
        }
        if let Some(dups) = duplicates_of(py, &names)? {
            errors.append(format!("Duplicate net names: {dups}"))?;
        }

        // Net pins must reference known components and known pins.
        let component_index = self.component_index.bind(py);
        for net in self.nets.bind(py).try_iter()? {
            let net = net?;
            let net_name = net.getattr("name")?;
            for pin in net.getattr("pins")?.try_iter()? {
                let (r#ref, pin_name) = unpack2(&pin?)?;
                if !component_index.contains(&r#ref)? {
                    errors.append(format!(
                        "Net {net_name} references unknown component {ref}",
                        net_name = net_name.str()?,
                        r#ref = r#ref.str()?
                    ))?;
                } else {
                    let comp = self.get_component(py, &r#ref)?;
                    if comp.call_method1("get_pin", (&pin_name,))?.is_none() {
                        errors.append(format!(
                            "Net {net_name} references unknown pin {pin_name} on {ref}",
                            net_name = net_name.str()?,
                            pin_name = pin_name.str()?,
                            r#ref = r#ref.str()?
                        ))?;
                    }
                }
            }
        }
        Ok(errors)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        // `_component_index`/`_net_index`/`_component_nets` carry
        // `repr=False` in the oracle and are omitted here.
        Ok(dataclass_repr(
            "Netlist",
            &[
                ("components", repr_of(&self.components, py)?),
                ("nets", repr_of(&self.nets, py)?),
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
        Err(unhashable("Netlist"))
    }
}

/// `d[key]`, raising CPython's own `KeyError` with the key as its argument.
fn dict_getitem<'py>(
    dict: &Bound<'py, PyAny>,
    key: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)
}

/// The body of `Netlist.build_indices`, as a free function so both `__new__`
/// (where no `Bound<Self>` exists yet) and the public method share one
/// transcription of the oracle.
fn compute_indices<'py>(
    py: Python<'py>,
    components: &Bound<'py, PyAny>,
    nets: &Bound<'py, PyAny>,
) -> PyResult<(Py<PyAny>, Py<PyAny>, Py<PyAny>)> {
    let component_index = PyDict::new(py);
    for (i, comp) in components.try_iter()?.enumerate() {
        component_index.set_item(comp?.getattr("ref")?, i)?;
    }
    let net_index = PyDict::new(py);
    for (i, net) in nets.try_iter()?.enumerate() {
        net_index.set_item(net?.getattr("name")?, i)?;
    }
    // `{c.ref: [] for c in self.components}` -- a distinct list per ref, and
    // a later duplicate ref replaces the earlier bucket, as in Python.
    let component_nets = PyDict::new(py);
    for comp in components.try_iter()? {
        component_nets.set_item(comp?.getattr("ref")?, PyList::empty(py))?;
    }
    for net in nets.try_iter()? {
        let net = net?;
        let name = net.getattr("name")?;
        for pin in net.getattr("pins")?.try_iter()? {
            // Oracle: `for ref, _ in net.pins` -- the same CPython unpack the
            // `unpack2` helper reproduces (lists are valid, and the arity
            // diagnostics are CPython's own). A pyo3 tuple `extract()` would
            // reject lists outright and raise different text.
            let (r#ref, _rest) = unpack2(&pin?)?;
            if let Some(bucket) = component_nets.get_item(&r#ref)? {
                bucket.cast::<PyList>()?.append(&name)?;
            }
        }
    }
    Ok((
        component_index.into_any().unbind(),
        net_index.into_any().unbind(),
        component_nets.into_any().unbind(),
    ))
}

/// Render `set(duplicates)` the way the oracle's f-string does, or `None`
/// when there are none.
///
/// Oracle:
/// ```python
/// if len(refs) != len(set(refs)):
///     duplicates = [r for r in refs if refs.count(r) > 1]
///     errors.append(f"Duplicate component refs: {set(duplicates)}")
/// ```
fn duplicates_of(py: Python<'_>, items: &Bound<'_, PyList>) -> PyResult<Option<String>> {
    let as_set = PySet::new(py, items.iter())?;
    if items.len() == as_set.len() {
        return Ok(None);
    }
    let dups = PyList::empty(py);
    for item in items.iter() {
        if items.as_any().call_method1("count", (&item,))?.extract::<usize>()? > 1 {
            dups.append(item)?;
        }
    }
    let dup_set = PySet::new(py, dups.iter())?;
    Ok(Some(dup_set.str()?.extract()?))
}

// ---------------------------------------------------------------------------
// Module-level functions
// ---------------------------------------------------------------------------

/// Shared body for `build_adjacency_matrix`, callable with the netlist's own
/// component/net lists (so `find_isomorphic_groups` reuses it exactly).
fn build_adjacency_matrix_impl<'py>(
    py: Python<'py>,
    components: &Bound<'py, PyAny>,
    nets: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let np = numpy(py)?;
    let n = components.len()?;

    if n == 0 {
        // Oracle: `np.array([]).reshape(0, 0)` -- note NO dtype, so this is
        // float64, unlike the float32 populated path. Preserved deliberately.
        return np
            .getattr("array")?
            .call1((PyList::empty(py),))?
            .call_method1("reshape", (0, 0));
    }

    // `ref_to_idx = {comp.ref: i for i, comp in enumerate(...)}` -- later
    // duplicates overwrite earlier ones, same as Python.
    let ref_to_idx = PyDict::new(py);
    for (i, comp) in components.try_iter()?.enumerate() {
        ref_to_idx.set_item(comp?.getattr("ref")?, i)?;
    }

    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr("float32")?)?;
    let adj = np
        .getattr("zeros")?
        .call((PyTuple::new(py, [n, n])?,), Some(&kwargs))?;

    for net in nets.try_iter()? {
        let net = net?;
        let mut comp_indices: Vec<usize> = Vec::new();
        for pin in net.getattr("pins")?.try_iter()? {
            let (comp_ref, _pin_name) = unpack2(&pin?)?;
            if let Some(idx) = ref_to_idx.get_item(&comp_ref)? {
                comp_indices.push(idx.extract()?);
            }
        }
        // `list(set(comp_indices))` -- deduplicate. The oracle's ordering
        // comes from CPython's small-int set iteration, but the result is
        // order-independent: every unordered pair gets +1 on both (i,j) and
        // (j,i) regardless of enumeration order, so the matrix is identical.
        comp_indices.sort_unstable();
        comp_indices.dedup();

        for i in 0..comp_indices.len() {
            for j in (i + 1)..comp_indices.len() {
                let (idx_i, idx_j) = (comp_indices[i], comp_indices[j]);
                incr(py, &adj, idx_i, idx_j)?;
                incr(py, &adj, idx_j, idx_i)?;
            }
        }
    }

    // Oracle's trailing `return np.array(adj)` -- a copy, dtype preserved.
    np.getattr("array")?.call1((adj,))
}

/// `adj[i, j] += 1` through numpy's own item protocol (float32 arithmetic).
fn incr(py: Python<'_>, adj: &Bound<'_, PyAny>, i: usize, j: usize) -> PyResult<()> {
    let key = PyTuple::new(py, [i, j])?;
    let current = adj.get_item(&key)?;
    adj.set_item(&key, current.add(1)?)
}

/// Build a weighted adjacency matrix from netlist connectivity.
#[pyfunction]
pub fn build_adjacency_matrix<'py>(
    py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    build_adjacency_matrix_impl(
        py,
        &netlist.getattr("components")?,
        &netlist.getattr("nets")?,
    )
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered into a **submodule** rather than the extension root: this
/// module and `board_contracts` each define a class called `Component`, and
/// adding both to one namespace would silently alias one over the other.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "netlist_contracts")?;
    sub.add_class::<Pin>()?;
    sub.add_class::<Component>()?;
    sub.add_class::<Net>()?;
    sub.add_class::<Netlist>()?;
    sub.add_function(wrap_pyfunction!(build_adjacency_matrix, &sub)?)?;
    module.add_submodule(&sub)
}

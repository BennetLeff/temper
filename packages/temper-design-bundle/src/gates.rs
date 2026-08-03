//! Gate-contract data model — the fourth Wave 4 Phase 2 contracts pivot.
//!
//! Python reference: the contract types in
//! `temper_placer/placer/cp_sat/gates.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/placer/cp_sat/_gates_py_oracle.py`
//! (commit `ef2ac25fd`). The pyo3 pyclasses here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/placer/cp_sat/test_gates_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! This is a pure data-contract model: three string-valued enums
//! (`GateStatus`, `GateStage`, `ViolationType`) and three frozen dataclasses
//! (`Violation`, `GateResult`, `BoardState`). The gate implementations
//! (`Gate` and its subclasses — DrcGate, RoutingGate, ...) run subprocesses
//! and stay Python-side in the delegation module. The structural proof and
//! the induction non-applicability note live in this crate's
//! `VERIFICATION.md`.
//!
//! Design notes (mirroring the landed net_types/loops/design_rules pivots):
//! - The enums are PLAIN Python `Enum`s with STRING values (not IntEnum):
//!   members are not equal to their value, construct by value via
//!   `Enum(value)`, and iterate via the class. The pyclasses use the
//!   `str_enum_member_impl!` macro from `loops.rs`: `#[new]` value
//!   constructor, `name`/`value` getters, `__str__`/`__repr__` (with the
//!   string value QUOTED in the repr — `<ViolationType.CLEARANCE:
//!   'clearance'>`), and a `members()` staticmethod for class-level
//!   iteration (the pyo3 substitute for `list(Enum)`).
//! - Enum *identity* is load-bearing: consumers compare
//!   `result.status is GateStatus.CLEAN` and
//!   `violation.type is ViolationType.CREEPAGE`. pyo3 caches enum members
//!   as class attributes (verified: `E.M is E.M` and
//!   `getattr(E, 'M') is E.M` both hold), and the dataclasses hold their
//!   enum fields opaquely as `Py<PyAny>` so the getter returns the exact
//!   cached member object — identity is preserved end to end.
//! - The frozen dataclasses hold their container/opaque fields as the
//!   actual Python objects (`Py<PyAny>`): `Violation.components`/`.nets`/
//!   `.context`, `GateResult.violations`, and every `BoardState` field.
//!   This mirrors `design_rules.rs`'s mutable-container handling: getters
//!   return the exact objects, equality and repr run through Python's own
//!   semantics on those objects, and the `context` default is a fresh empty
//!   `dict` per instance exactly like `field(default_factory=dict)`.
//! - `GateResult`'s constructor invariant (a `VIOLATIONS` status with an
//!   empty `violations` tuple is rejected with a `ValueError`) replicates
//!   the oracle's `__post_init__`: the check compares by IDENTITY against
//!   the cached `GateStatus.VIOLATIONS` member (resolved via
//!   `py.get_type::<GateStatus>()` + `getattr("VIOLATIONS")`, compared
//!   with a pointer `is`), which is exactly the oracle's
//!   `self.status is GateStatus.VIOLATIONS`.
//! - `__hash__` replicates the frozen-dataclass tuple-hash semantics by
//!   building the equivalent Python tuple and calling Python's `hash()`;
//!   this includes the oracle's behavior of raising `TypeError` when a
//!   field is unhashable (a `Violation` with its `context` dict is
//!   unhashable, exactly like the dataclass).
//! - `__repr__` renders floats with `py_float_str` and strings with
//!   `py_str_repr` (the B9 lesson); enum members, tuples, and dicts render
//!   via Python's own `repr()` on the held objects, so every component is
//!   byte-identical to the dataclass repr.
//!
//! Documented deviation (recorded in `VERIFICATION.md`): `severity` and
//! `threshold` are typed `f64`. The dataclass does not coerce — an
//! `int` passed pre-migration stays an `int` and reprs as `1`. Here an
//! `int` is coerced to `1.0` (repr `1.0`). No consumer passes ints
//! (every construction site uses float literals); the differential/PBT
//! suites drive floats.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyList, PyString, PyTuple};

// ---------------------------------------------------------------------------
// CPython repr(float) / repr(str) replicas (duplicated from net_types.rs /
// loops.rs / design_rules.rs — see the module docstring; kept private per
// module so each keeps its own tests).
// ---------------------------------------------------------------------------

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping (Python repr chooses single quotes
/// when the string contains no single quotes and no other quotable
/// characters force otherwise — identifiers render as `'Via1x1'`). Rust's
/// `{:?}` renders double quotes, which would diverge in dataclass reprs.
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does. Both languages use
/// shortest-round-trip digit selection, so the digits always agree; the
/// differences are in the exponent rendering only: CPython always writes
/// the exponent sign and pads to two digits (`1e+300`, `1e-05`), and writes
/// `nan` where Rust writes `NaN`.
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

/// Python's own `repr()` of a held object (falls back to `"?"` only when
/// repr itself errors, which never happens for the objects these
/// dataclasses hold — mirrored from `design_rules.rs`).
fn py_repr_of(obj: &Bound<'_, PyAny>) -> String {
    obj.repr().map_or_else(|_| "?".to_string(), |r| r.to_string())
}

#[cfg(test)]
mod repr_helper_tests {
    use super::{py_float_str, py_str_repr};

    #[test]
    fn py_float_str_matches_cpython_on_divergence_classes() {
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
        assert_eq!(py_float_str(0.0), "0.0");
        assert_eq!(py_float_str(-6.0), "-6.0");
        assert_eq!(py_float_str(4.5), "4.5");
    }

    #[test]
    fn py_str_repr_uses_single_quotes() {
        assert_eq!(py_str_repr("creepage"), "'creepage'");
        assert_eq!(py_str_repr("it's"), "'it\\'s'");
        assert_eq!(py_str_repr(""), "''");
    }
}

// ---------------------------------------------------------------------------
// Enums (Python `Enum` with STRING values — members are not equal to their
// value, are hashable, and construct by value via `Enum(value)`)
// ---------------------------------------------------------------------------

/// Three-state gate measurement result (mirrors `GateStatus` in
/// `temper_placer/placer/cp_sat/gates.py`).
#[pyclass(frozen, eq, hash, from_py_object)]
// Variant names intentionally mirror the Python Enum member identifiers
// (e.g. `VIOLATIONS`) — the pyo3 attribute access contract.
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum GateStatus {
    CLEAN,
    VIOLATIONS,
    UNMEASURED,
}

/// When in the place->route loop a gate is checked (mirrors `GateStage`).
#[pyclass(frozen, eq, hash, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum GateStage {
    PLACEMENT,
    ROUTING,
}

/// Category of a single violation (mirrors `ViolationType`).
#[pyclass(frozen, eq, hash, from_py_object)]
#[allow(non_camel_case_types)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum ViolationType {
    CLEARANCE,
    UNROUTED,
    SHORTING,
    MASK_BRIDGE,
    EDGE_CLEARANCE,
    REFERENCE_PLANE_SPLIT,
    CURRENT_DENSITY,
    LOOP_INDUCTANCE,
    THERMAL,
    CREEPAGE,
    VIA_COUNT,
    OCTILINEAR,
    SLOP,
}

macro_rules! str_enum_member_impl {
    ($ty:ident, $(($member:ident, $value:literal)),+ $(,)?) => {
        #[pymethods]
        impl $ty {
            /// Python `Enum(value)` mirror: resolve a member by its string
            /// value, raising the exact `ValueError` text CPython's Enum
            /// raises for unknown values.
            #[new]
            fn from_value(value: &str) -> PyResult<Self> {
                match value {
                    $($value => Ok(Self::$member),)+
                    _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
                        "'{value}' is not a valid {}",
                        stringify!($ty)
                    ))),
                }
            }

            /// Python `Enum.name` mirror.
            #[getter]
            pub fn name(&self) -> &'static str {
                match self {
                    $(Self::$member => stringify!($member),)+
                }
            }

            /// Python `Enum.value` mirror (the string value).
            #[getter]
            pub fn value(&self) -> &'static str {
                match self {
                    $(Self::$member => $value,)+
                }
            }

            /// Python `str(member)` mirror: `"GateStatus.CLEAN"`.
            fn __str__(&self) -> String {
                self.py_str()
            }

            /// Python `repr(member)` mirror:
            /// `"<GateStatus.CLEAN: 'clean'>"` (the string value is
            /// QUOTED, unlike the int-valued net-types enums).
            fn __repr__(&self) -> String {
                self.py_repr()
            }

            /// All members in declaration order — the pyo3 substitute for
            /// Python Enum class-level iteration (no metaclass hook; see
            /// the module docstring). Test code that iterates the enums
            /// (`list(GateStatus)`, `set(ViolationType)`) is adapted to use
            /// this, exactly like `io/loop_loader.py` was for the loops
            /// migration.
            #[staticmethod]
            pub fn members(py: Python<'_>) -> PyResult<Py<PyList>> {
                let list = PyList::empty(py);
                $(list.append(Self::$member)?;)+
                Ok(list.unbind())
            }
        }

        impl $ty {
            /// Rust-side `str(member)` rendering (callable from other
            /// pyclasses' reprs — `__str__` is a pymethod, not a Rust fn).
            pub fn py_str(&self) -> String {
                format!("{}.{}", stringify!($ty), self.name())
            }

            /// Rust-side `repr(member)` rendering.
            pub fn py_repr(&self) -> String {
                format!("<{}: '{}'>", self.py_str(), self.value())
            }
        }
    };
}

str_enum_member_impl!(
    GateStatus,
    (CLEAN, "clean"),
    (VIOLATIONS, "violations"),
    (UNMEASURED, "unmeasured"),
);

str_enum_member_impl!(
    GateStage,
    (PLACEMENT, "placement"),
    (ROUTING, "routing"),
);

str_enum_member_impl!(
    ViolationType,
    (CLEARANCE, "clearance"),
    (UNROUTED, "unrouted"),
    (SHORTING, "shorting"),
    (MASK_BRIDGE, "mask_bridge"),
    (EDGE_CLEARANCE, "edge_clearance"),
    (REFERENCE_PLANE_SPLIT, "reference_plane_split"),
    (CURRENT_DENSITY, "current_density"),
    (LOOP_INDUCTANCE, "loop_inductance"),
    (THERMAL, "thermal"),
    (CREEPAGE, "creepage"),
    (VIA_COUNT, "via_count"),
    (OCTILINEAR, "octilinear"),
    (SLOP, "slop"),
);

/// Is `status` the cached `GateStatus.VIOLATIONS` member, by pointer
/// identity? The oracle's `__post_init__` checks
/// `self.status is GateStatus.VIOLATIONS`; `py.get_type::<GateStatus>()` +
/// `getattr("VIOLATIONS")` returns the cached member (verified: enum member
/// access is stable), so `Bound::is` reproduces identity exactly.
fn is_violations_status(py: Python<'_>, status: &Bound<'_, PyAny>) -> PyResult<bool> {
    let violations_member = py.get_type::<GateStatus>().getattr("VIOLATIONS")?;
    Ok(status.is(&violations_member))
}

// ---------------------------------------------------------------------------
// Violation — the frozen dataclass
// ---------------------------------------------------------------------------

/// A single measured rule violation (mirrors `Violation` in
/// `temper_placer/placer/cp_sat/gates.py`).
///
/// Frozen exactly like the dataclass: attribute assignment raises
/// `AttributeError` (the dataclass raises the `FrozenInstanceError`
/// subclass — same base class; see `VERIFICATION.md` § documented
/// deviations). The `type` field is held opaquely as the exact enum member
/// object so `violation.type is ViolationType.CREEPAGE` identity holds; the
/// container fields are the actual Python objects.
#[pyclass(frozen)]
pub struct Violation {
    /// A `ViolationType` member (held opaquely for identity; the dataclass
    /// does not validate the field type).
    #[pyo3(get)]
    pub r#type: Py<PyAny>,
    /// `tuple[str, ...]` of component references.
    #[pyo3(get)]
    pub components: Py<PyAny>,
    /// `tuple[str, ...]` of net names.
    #[pyo3(get)]
    pub nets: Py<PyAny>,
    #[pyo3(get)]
    pub severity: f64,
    #[pyo3(get)]
    pub threshold: f64,
    #[pyo3(get)]
    pub description: String,
    /// `dict`; defaults to a fresh empty dict per instance, exactly like
    /// `field(default_factory=dict)`.
    #[pyo3(get)]
    pub context: Py<PyAny>,
}

/// Shared helper for building the canonical Python tuple whose `hash()`
/// reproduces the frozen-dataclass `__hash__` (`hash((f1, f2, ...))`).
fn dataclass_hash(py: Python<'_>, fields: &[Py<PyAny>]) -> PyResult<isize> {
    let tuple = PyTuple::new(py, fields.iter().map(|f| f.bind(py)))?;
    tuple.as_any().hash()
}

#[pymethods]
impl Violation {
    #[new]
    #[pyo3(signature = (
        r#type,
        components=None,
        nets=None,
        severity=0.0,
        threshold=0.0,
        description="",
        context=None,
    ))]
    fn new(
        py: Python<'_>,
        r#type: &Bound<'_, PyAny>,
        components: Option<&Bound<'_, PyAny>>,
        nets: Option<&Bound<'_, PyAny>>,
        severity: f64,
        threshold: f64,
        description: &str,
        context: Option<&Bound<'_, PyAny>>,
    ) -> Self {
        let empty_tuple = || PyTuple::empty(py).into_any().unbind();
        let fresh_dict = || PyDict::new(py).into_any().unbind();
        Self {
            r#type: r#type.clone().unbind(),
            components: match components {
                Some(obj) => obj.clone().unbind(),
                None => empty_tuple(),
            },
            nets: match nets {
                Some(obj) => obj.clone().unbind(),
                None => empty_tuple(),
            },
            severity,
            threshold,
            description: description.to_string(),
            context: match context {
                Some(obj) => obj.clone().unbind(),
                None => fresh_dict(),
            },
        }
    }

    /// Dataclass-style equality: every field via Python `==` on the held
    /// objects (floats via IEEE `==`, so NaN != NaN on both sides).
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<Violation>() else {
            return false;
        };
        let other = other.borrow();
        self.severity == other.severity
            && self.threshold == other.threshold
            && self.description == other.description
            && self.r#type.bind(py).eq(other.r#type.bind(py)).unwrap_or(false)
            && self
                .components
                .bind(py)
                .eq(other.components.bind(py))
                .unwrap_or(false)
            && self.nets.bind(py).eq(other.nets.bind(py)).unwrap_or(false)
            && self
                .context
                .bind(py)
                .eq(other.context.bind(py))
                .unwrap_or(false)
    }

    /// Frozen-dataclass hash semantics: `hash((type, components, nets,
    /// severity, threshold, description, context))` computed via Python's
    /// own tuple hash — including the oracle's `TypeError` when a field is
    /// unhashable (the `context` dict makes every Violation unhashable).
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(
            py,
            &[
                self.r#type.clone_ref(py),
                self.components.clone_ref(py),
                self.nets.clone_ref(py),
                PyFloat::new(py, self.severity).into_any().unbind(),
                PyFloat::new(py, self.threshold).into_any().unbind(),
                PyString::new(py, &self.description).into_any().unbind(),
                self.context.clone_ref(py),
            ],
        )
    }

    /// Dataclass-style repr with CPython string/float rendering; the enum
    /// member, tuples, and dict render via Python's own `repr()` on the
    /// held objects.
    fn __repr__(&self, py: Python<'_>) -> String {
        format!(
            "Violation(type={}, components={}, nets={}, severity={}, \
             threshold={}, description={}, context={})",
            py_repr_of(self.r#type.bind(py)),
            py_repr_of(self.components.bind(py)),
            py_repr_of(self.nets.bind(py)),
            py_float_str(self.severity),
            py_float_str(self.threshold),
            py_str_repr(&self.description),
            py_repr_of(self.context.bind(py)),
        )
    }
}

// ---------------------------------------------------------------------------
// GateResult — the frozen dataclass with the VIOLATIONS constructor invariant
// ---------------------------------------------------------------------------

/// Result of a single gate check (mirrors `GateResult` in
/// `temper_placer/placer/cp_sat/gates.py`).
///
/// The constructor invariant from the oracle's `__post_init__` is enforced
/// in `#[new]`: a `VIOLATIONS` status with an empty `violations` tuple is
/// rejected with the exact `ValueError` text, so "empty means clean, not
/// couldn't-measure" holds at the type boundary.
#[pyclass(frozen)]
pub struct GateResult {
    /// A `GateStatus` member (held opaquely for identity).
    #[pyo3(get)]
    pub status: Py<PyAny>,
    /// `tuple[Violation, ...]` (held as the actual Python object).
    #[pyo3(get)]
    pub violations: Py<PyAny>,
    /// Only populated for `UNMEASURED`.
    #[pyo3(get)]
    pub error_message: String,
}

#[pymethods]
impl GateResult {
    #[new]
    #[pyo3(signature = (status, violations=None, error_message=""))]
    fn new(
        py: Python<'_>,
        status: &Bound<'_, PyAny>,
        violations: Option<&Bound<'_, PyAny>>,
        error_message: &str,
    ) -> PyResult<Self> {
        let violations_obj = match violations {
            Some(obj) => obj.clone().unbind(),
            None => PyTuple::empty(py).into_any().unbind(),
        };
        // The oracle's __post_init__: `self.status is GateStatus.VIOLATIONS
        // and len(self.violations) == 0` -> ValueError.
        if is_violations_status(py, status)? && violations_obj.bind(py).len()? == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "GateResult with status=VIOLATIONS must have at least one Violation",
            ));
        }
        Ok(Self {
            status: status.clone().unbind(),
            violations: violations_obj,
            error_message: error_message.to_string(),
        })
    }

    /// Dataclass-style equality: status via Python `==` (enum), violations
    /// tuple via Python `==` (elementwise through `Violation.__eq__`),
    /// error message verbatim.
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<GateResult>() else {
            return false;
        };
        let other = other.borrow();
        self.error_message == other.error_message
            && self.status.bind(py).eq(other.status.bind(py)).unwrap_or(false)
            && self
                .violations
                .bind(py)
                .eq(other.violations.bind(py))
                .unwrap_or(false)
    }

    /// Frozen-dataclass hash semantics: `hash((status, violations,
    /// error_message))` via Python's own tuple hash. A `Violation` with a
    /// populated `context` dict inside the tuple raises `TypeError`, exactly
    /// like the dataclass.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(
            py,
            &[
                self.status.clone_ref(py),
                self.violations.clone_ref(py),
                PyString::new(py, &self.error_message).into_any().unbind(),
            ],
        )
    }

    /// Dataclass-style repr; the status member and the violations tuple
    /// render via Python's own `repr()` (the tuple repr recurses into each
    /// `Violation.__repr__`, byte-identical to the dataclass's).
    fn __repr__(&self, py: Python<'_>) -> String {
        format!(
            "GateResult(status={}, violations={}, error_message={})",
            py_repr_of(self.status.bind(py)),
            py_repr_of(self.violations.bind(py)),
            py_str_repr(&self.error_message),
        )
    }
}

// ---------------------------------------------------------------------------
// BoardState — the frozen snapshot dataclass
// ---------------------------------------------------------------------------

/// Frozen snapshot of the pipeline state handed to every gate (mirrors
/// `BoardState` in `temper_placer/placer/cp_sat/gates.py`).
///
/// Every field is an opaque payload held as the exact Python object
/// (`Py<PyAny>`), so `bs.board is board` identity holds and gates can
/// inspect the payload objects directly.
#[pyclass(frozen)]
pub struct BoardState {
    #[pyo3(get)]
    pub placement: Py<PyAny>,
    #[pyo3(get)]
    pub routing: Py<PyAny>,
    #[pyo3(get)]
    pub netlist: Py<PyAny>,
    #[pyo3(get)]
    pub board: Py<PyAny>,
    #[pyo3(get)]
    pub design_rules: Py<PyAny>,
    #[pyo3(get)]
    pub routed_pcb_path: Py<PyAny>,
}

#[pymethods]
impl BoardState {
    #[new]
    #[pyo3(signature = (
        placement=None,
        routing=None,
        netlist=None,
        board=None,
        design_rules=None,
        routed_pcb_path=None,
    ))]
    fn new(
        py: Python<'_>,
        placement: Option<&Bound<'_, PyAny>>,
        routing: Option<&Bound<'_, PyAny>>,
        netlist: Option<&Bound<'_, PyAny>>,
        board: Option<&Bound<'_, PyAny>>,
        design_rules: Option<&Bound<'_, PyAny>>,
        routed_pcb_path: Option<&Bound<'_, PyAny>>,
    ) -> Self {
        let none = || py.None();
        Self {
            placement: match placement {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
            routing: match routing {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
            netlist: match netlist {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
            board: match board {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
            design_rules: match design_rules {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
            routed_pcb_path: match routed_pcb_path {
                Some(obj) => obj.clone().unbind(),
                None => none(),
            },
        }
    }

    /// Dataclass-style equality: every field via Python `==` on the held
    /// objects.
    fn __eq__(&self, other: &Bound<'_, PyAny>, py: Python<'_>) -> bool {
        let Ok(other) = other.cast::<BoardState>() else {
            return false;
        };
        let other = other.borrow();
        let fields: [(&Bound<'_, PyAny>, &Bound<'_, PyAny>); 6] = [
            (self.placement.bind(py), other.placement.bind(py)),
            (self.routing.bind(py), other.routing.bind(py)),
            (self.netlist.bind(py), other.netlist.bind(py)),
            (self.board.bind(py), other.board.bind(py)),
            (self.design_rules.bind(py), other.design_rules.bind(py)),
            (self.routed_pcb_path.bind(py), other.routed_pcb_path.bind(py)),
        ];
        fields
            .iter()
            .all(|(a, b)| a.eq(b).unwrap_or(false))
    }

    /// Frozen-dataclass hash semantics: `hash((placement, routing,
    /// netlist, board, design_rules, routed_pcb_path))` via Python's own
    /// tuple hash.
    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        dataclass_hash(
            py,
            &[
                self.placement.clone_ref(py),
                self.routing.clone_ref(py),
                self.netlist.clone_ref(py),
                self.board.clone_ref(py),
                self.design_rules.clone_ref(py),
                self.routed_pcb_path.clone_ref(py),
            ],
        )
    }

    /// Dataclass-style repr; every field renders via Python's own `repr()`
    /// (`None` renders as `None`, a `Path` as `PosixPath('/tmp/...')`).
    fn __repr__(&self, py: Python<'_>) -> String {
        format!(
            "BoardState(placement={}, routing={}, netlist={}, board={}, \
             design_rules={}, routed_pcb_path={})",
            py_repr_of(self.placement.bind(py)),
            py_repr_of(self.routing.bind(py)),
            py_repr_of(self.netlist.bind(py)),
            py_repr_of(self.board.bind(py)),
            py_repr_of(self.design_rules.bind(py)),
            py_repr_of(self.routed_pcb_path.bind(py)),
        )
    }
}

// ---------------------------------------------------------------------------
// Python module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<GateStatus>()?;
    module.add_class::<GateStage>()?;
    module.add_class::<ViolationType>()?;
    module.add_class::<Violation>()?;
    module.add_class::<GateResult>()?;
    module.add_class::<BoardState>()?;
    Ok(())
}

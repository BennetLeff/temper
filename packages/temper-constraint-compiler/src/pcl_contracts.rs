//! PCL constraint pure-data contracts — Wave 4 Phase 2/6.
//!
//! Python reference: `temper_placer/pcl/constraints.py`. The pre-migration
//! implementation is pinned VERBATIM (as deterministic dataclasses) in
//! `packages/temper-placer/tests/pcl/test_constraints_rust_differential.py`
//! (the oracle block); that differential is the TDD oracle for this file.
//!
//! # What moved and why
//!
//! The eight PCL constraint classes and `CompilationContext` are contract
//! objects: every ortools/CP-SAT/DRC consumer reads their *data surface*
//! (fields, `id`, `tier`, `involves_component`, `to_dict`), and the parse
//! layer constructs them from YAML dicts. They are now pyo3 `#[pyclass]`
//! objects so construction validation, id generation, serialization and
//! involvement checks run in Rust.
//!
//! What deliberately stays Python:
//! - the value enums (`ConstraintTier`, `ConstraintType`, `DistanceMetric`,
//!   `Axis`, `BoardSide`, `EdgeType`, `CompilationTarget`, `SemanticTag`) —
//!   production does `for t in ConstraintType` and `ConstraintType(value)`,
//!   which a `#[pyclass]` enum cannot provide (the tag_dispatch precedent).
//!   The migrated objects hold the LIVE Python singletons and hand them back
//!   through the getters, so `c.tier is ConstraintTier.HARD` and
//!   `TYPE_HANDLERS[c.constraint_type]` keep working.
//! - `BaseConstraint` (the ABC the tagged-constraint classes subclass and
//!   the `backends` registry holder) — the sat/drc/rust bridge registration
//!   and `parser.py`'s dispatch are the Phase-1 ortools-encoder KEEP slice.
//!   The shim re-exports the pyclasses and registers them as virtual
//!   subclasses so `isinstance(c, BaseConstraint)` keeps holding.
//!
//! # Fidelity contract
//!
//! The pre-migration classes were *plain* classes with address-dependent
//! object `repr()` and identity `==`/`hash`. The migration defines the
//! contract as the deterministic dataclass-style surface (matching the
//! "contracts-as-pyo3-pyclasses" pivot): field order = the oracle dataclass
//! field order, `__repr__` byte-identical, `__eq__`/`__hash__` structural.
//! Every stored value is kept as the exact Python object passed in (never
//! coerced), so `region=(0, 0, 10, 10)` with ints round-trips untouched;
//! optional fields (`pin_a`, `pin_b`, `region`, `position`, and the
//! `CompilationContext` optionals) are stored as `None`, which is exactly
//! what the pre-migration `None` defaults were.
//!
//! One deliberate widening: the constructors accept `targets=` (the
//! `BaseConstraint` dataclass field) and validate it exactly like the
//! pre-migration `__post_init__`. The pre-migration concrete `__init__`
//! signatures rejected it, but no in-repo caller passes it (grep-verified),
//! and the oracle dataclass accepts it — see VERIFICATION.md.
//!
//! No `unwrap`/`expect` anywhere (clippy `unwrap_used`/`expect_used` deny is
//! a crate lint); the pyo3 entry points that run non-trivial logic are
//! wrapped in `temper_py_bridge::catch_panic` (R1g).

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyList, PyString, PyTuple, PyType};

use temper_py_bridge::catch_panic;

// ---------------------------------------------------------------------------
// Cached Python handles (the live enums the objects must hand back).
// ---------------------------------------------------------------------------

struct ConstraintTypes {
    constraint_tier: Py<PyAny>,
    constraint_type: Py<PyAny>,
    distance_metric: Py<PyAny>,
    compilation_target: Py<PyAny>,
}

static CONSTRAINT_TYPES: PyOnceLock<ConstraintTypes> = PyOnceLock::new();

fn constraint_types(py: Python<'_>) -> PyResult<&'static ConstraintTypes> {
    CONSTRAINT_TYPES.get_or_try_init(py, || {
        let constraints = py.import("temper_placer.pcl.constraints")?;
        Ok(ConstraintTypes {
            constraint_tier: constraints.getattr("ConstraintTier")?.unbind(),
            constraint_type: constraints.getattr("ConstraintType")?.unbind(),
            distance_metric: constraints.getattr("DistanceMetric")?.unbind(),
            compilation_target: constraints.getattr("CompilationTarget")?.unbind(),
        })
    })
}

fn enum_member(py: Python<'_>, cls: &Py<PyAny>, name: &str) -> PyResult<Py<PyAny>> {
    Ok(cls.bind(py).getattr(name)?.unbind())
}

/// `str(value)` with Python semantics (the pre-migration f-strings used it).
fn py_str(_py: Python<'_>, v: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(v.str()?.to_str()?.to_string())
}

/// `.value` of a stored enum member, as a string (used by id generation).
fn enum_value_str(py: Python<'_>, member: &Bound<'_, PyAny>) -> PyResult<String> {
    py_str(py, &member.getattr("value")?)
}

// ---------------------------------------------------------------------------
// Shared validation / id-generation helpers (replicating `__post_init__`).
// ---------------------------------------------------------------------------

fn validate_because(because: &str) -> PyResult<()> {
    let n = because.chars().count();
    if n < 10 {
        return Err(PyValueError::new_err(format!(
            "Rationale 'because' must be ≥10 chars, got {n}: '{because}'"
        )));
    }
    Ok(())
}

/// `targets` validation — the pre-migration `__post_init__` loop. The message
/// hardcodes `sorted(valid_targets)` == `['cp_sat', 'drc', 'jax', 'sat']`
/// (a constant string sort; pinned by the differential).
fn validate_targets(py: Python<'_>, targets: &Bound<'_, PyAny>) -> PyResult<()> {
    let types = constraint_types(py)?;
    let valid = PyList::empty(py);
    for name in ["JAX", "SAT", "DRC", "CP_SAT"] {
        let member = types.compilation_target.bind(py).getattr(name)?;
        valid.append(member.getattr("value")?)?;
    }
    for item in targets.try_iter()? {
        let item = item?;
        if !valid.as_any().contains(&item)? {
            let item_str = item.str()?.to_str()?.to_string();
            return Err(PyValueError::new_err(format!(
                "Invalid compilation target '{item_str}'. Must be one of ['cp_sat', 'drc', 'jax', 'sat']"
            )));
        }
    }
    Ok(())
}

/// `targets` default resolution: `["sat"]` (a fresh list per instance) or the
/// caller-provided list, validated.
fn resolve_targets(py: Python<'_>, targets: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match targets {
        Some(t) => {
            validate_targets(py, t)?;
            Ok(t.clone().unbind())
        }
        None => {
            let list = PyList::empty(py);
            list.append("sat")?;
            Ok(list.into_any().unbind())
        }
    }
}

/// `if not self.id: self.id = self._generate_id()`.
fn generate_id(
    py: Python<'_>,
    provided: Option<&Bound<'_, PyAny>>,
    gen_id: impl FnOnce(Python<'_>) -> PyResult<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    match provided {
        Some(v) if v.is_truthy()? => Ok(v.clone().unbind()),
        _ => gen_id(py),
    }
}

/// The shared `BaseConstraint`-state resolution: `because`/`targets`
/// validation, `constraint_type` member, and auto id generation.
struct BaseState {
    tier: Py<PyAny>,
    because: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[allow(clippy::too_many_arguments)]
fn resolve_base_state(
    py: Python<'_>,
    tier: Bound<'_, PyAny>,
    because: Bound<'_, PyAny>,
    id: Option<&Bound<'_, PyAny>>,
    targets: Option<&Bound<'_, PyAny>>,
    ct_name: &str,
    gen_id: impl FnOnce(Python<'_>) -> PyResult<Py<PyAny>>,
) -> PyResult<BaseState> {
    let because_str: String = because.extract()?;
    validate_because(&because_str)?;
    let types = constraint_types(py)?;
    let constraint_type = enum_member(py, &types.constraint_type, ct_name)?;
    let id = generate_id(py, id, gen_id)?;
    let targets = resolve_targets(py, targets)?;
    Ok(BaseState {
        tier: tier.unbind(),
        because: because.unbind(),
        id,
        constraint_type,
        targets,
    })
}

/// `"_".join(seq[:3])` with the pre-migration `TypeError` wording for
/// non-str elements (CPython: `sequence item 0: expected str instance, int
/// found`). Only reachable through Aligned/OnSide id generation.
fn join_first_three(_py: Python<'_>, components: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut parts = Vec::new();
    for (i, item) in components.try_iter()?.enumerate() {
        if i >= 3 {
            break;
        }
        let item = item?;
        match item.extract::<String>() {
            Ok(s) => parts.push(s),
            Err(_) => {
                let type_name = item.get_type().name()?.to_string();
                return Err(PyTypeError::new_err(format!(
                    "sequence item {i}: expected str instance, {type_name} found"
                )));
            }
        }
    }
    Ok(parts.join("_"))
}

// ---------------------------------------------------------------------------
// Shared contract-object machinery: repr / eq / hash / reduce / escalate.
// ---------------------------------------------------------------------------

/// Reproduce the dataclass-style `Name(field=repr, ...)` repr. `labels` and
/// `values` are the dataclass field order (see each class's `field_values`).
fn dataclass_repr<'py>(
    py: Python<'py>,
    name: &str,
    labels: &[&str],
    values: &[Py<PyAny>],
) -> PyResult<String> {
    let mut s = format!("{name}(");
    for (i, (label, value)) in labels.iter().zip(values).enumerate() {
        if i > 0 {
            s.push_str(", ");
        }
        s.push_str(label);
        s.push('=');
        s.push_str(value.bind(py).repr()?.to_str()?);
    }
    s.push(')');
    Ok(s)
}

/// Field-by-field Python `==` in the given order (dataclass `__eq__`).
fn eq_fields(py: Python<'_>, a: &[Py<PyAny>], b: &[Py<PyAny>]) -> PyResult<bool> {
    for (x, y) in a.iter().zip(b) {
        if !x.bind(py).eq(y.bind(py))? {
            return Ok(false);
        }
    }
    Ok(true)
}

/// `hash(tuple(fields))` — CPython's own tuple hash, not a replica.
fn tuple_hash(py: Python<'_>, fields: Vec<Py<PyAny>>) -> PyResult<isize> {
    PyTuple::new(py, fields)?.hash()
}

/// Build `(cls, (constructor-args...))` for `copy.deepcopy` / `pickle`.
fn reduce_args(
    py: Python<'_>,
    cls: &Bound<'_, PyType>,
    args: Vec<Py<PyAny>>,
) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
    let tuple = PyTuple::new(py, args)?.into_any().unbind();
    Ok((cls.clone().into_any().unbind(), tuple))
}

/// `SOFT -> STRONG -> HARD` (replicating `BaseConstraint.escalate`).
fn escalate_tier(py: Python<'_>, tier: &mut Py<PyAny>) -> PyResult<()> {
    let types = constraint_types(py)?;
    let soft = types.constraint_tier.bind(py).getattr("SOFT")?;
    let strong = types.constraint_tier.bind(py).getattr("STRONG")?;
    let hard = types.constraint_tier.bind(py).getattr("HARD")?;
    if tier.bind(py).eq(&soft)? {
        *tier = strong.unbind();
    } else if tier.bind(py).eq(&strong)? {
        *tier = hard.unbind();
    }
    Ok(())
}

/// `__hash__` values — list/dict fields cannot sit in a Python tuple (the
/// oracle dataclass's `unsafe_hash` is unhashable for list-bearing classes
/// for the same reason), so they are excluded; equal objects share equal
/// scalar fields, which is all the equal-implies-equal-hash invariant needs.
fn hashable_fields(py: Python<'_>, values: Vec<Py<PyAny>>) -> PyResult<Vec<Py<PyAny>>> {
    let mut out = Vec::new();
    for v in values {
        let b = v.bind(py);
        if b.is_instance_of::<PyList>() || b.is_instance_of::<PyDict>() {
            continue;
        }
        out.push(v);
    }
    Ok(out)
}

/// A Python float (for constructor defaults the pre-migration spelled as
/// literal values: margin_mm=0.0, tolerance_mm=0.5, max_distance_mm=5.0).
fn default_float(py: Python<'_>, v: f64) -> PyResult<Py<PyAny>> {
    Ok(v.into_pyobject(py)?.into_any().unbind())
}

fn set_dict_item(d: &Bound<'_, PyDict>, key: &str, value: &Bound<'_, PyAny>) -> PyResult<()> {
    d.set_item(key, value)?;
    Ok(())
}

fn to_value<'py>(_py: Python<'py>, member: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    member.getattr("value")
}
// ---------------------------------------------------------------------------
// AdjacentConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct AdjacentConstraint {
    a: Py<PyAny>,
    b: Py<PyAny>,
    max_distance_mm: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    metric: Py<PyAny>,
    pin_a: Py<PyAny>,
    pin_b: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl AdjacentConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (a, b, max_distance_mm, tier, because, metric=None, pin_a=None, pin_b=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        a: Bound<'_, PyAny>,
        b: Bound<'_, PyAny>,
        max_distance_mm: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        metric: Option<Bound<'_, PyAny>>,
        pin_a: Option<Bound<'_, PyAny>>,
        pin_b: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let metric = match metric {
                Some(m) => m.unbind(),
                None => enum_member(py, &constraint_types(py)?.distance_metric, "EDGE_TO_EDGE")?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "ADJACENT",
                |py| {
                    Ok(
                        PyString::new(py, &format!("adj_{}_{}", py_str(py, &a)?, py_str(py, &b)?))
                            .into_any()
                            .unbind(),
                    )
                },
            )?;
            Ok(Self {
                a: a.unbind(),
                b: b.unbind(),
                max_distance_mm: max_distance_mm.unbind(),
                tier: base.tier,
                because: base.because,
                metric,
                pin_a: pin_a.map_or_else(|| py.None(), |v| v.unbind()),
                pin_b: pin_b.map_or_else(|| py.None(), |v| v.unbind()),
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        Ok(self.a.bind(py).eq(&comp)? || self.b.bind(py).eq(&comp)?)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "a", self.a.bind(py))?;
            set_dict_item(&d, "b", self.b.bind(py))?;
            set_dict_item(&d, "max_distance_mm", self.max_distance_mm.bind(py))?;
            set_dict_item(&d, "metric", &to_value(py, self.metric.bind(py))?)?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            if self.pin_a.bind(py).is_truthy()? {
                set_dict_item(&d, "pin_a", self.pin_a.bind(py))?;
            }
            if self.pin_b.bind(py).is_truthy()? {
                set_dict_item(&d, "pin_b", self.pin_b.bind(py))?;
            }
            if self.id.bind(py).is_truthy()? {
                set_dict_item(&d, "id", self.id.bind(py))?;
            }
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn a(&self, py: Python<'_>) -> Py<PyAny> {
        self.a.clone_ref(py)
    }

    #[setter]
    fn set_a(&mut self, value: Bound<'_, PyAny>) {
        self.a = value.unbind();
    }

    #[getter]
    fn b(&self, py: Python<'_>) -> Py<PyAny> {
        self.b.clone_ref(py)
    }

    #[setter]
    fn set_b(&mut self, value: Bound<'_, PyAny>) {
        self.b = value.unbind();
    }

    #[getter]
    fn max_distance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.max_distance_mm.clone_ref(py)
    }

    #[setter]
    fn set_max_distance_mm(&mut self, value: Bound<'_, PyAny>) {
        self.max_distance_mm = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn metric(&self, py: Python<'_>) -> Py<PyAny> {
        self.metric.clone_ref(py)
    }

    #[setter]
    fn set_metric(&mut self, value: Bound<'_, PyAny>) {
        self.metric = value.unbind();
    }

    #[getter]
    fn pin_a(&self, py: Python<'_>) -> Py<PyAny> {
        self.pin_a.clone_ref(py)
    }

    #[setter]
    fn set_pin_a(&mut self, value: Bound<'_, PyAny>) {
        self.pin_a = value.unbind();
    }

    #[getter]
    fn pin_b(&self, py: Python<'_>) -> Py<PyAny> {
        self.pin_b.clone_ref(py)
    }

    #[setter]
    fn set_pin_b(&mut self, value: Bound<'_, PyAny>) {
        self.pin_b = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.a.clone_ref(py),
            self.b.clone_ref(py),
            self.max_distance_mm.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.metric.clone_ref(py),
            self.pin_a.clone_ref(py),
            self.pin_b.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "AdjacentConstraint",
            &[
                "a",
                "b",
                "max_distance_mm",
                "tier",
                "because",
                "metric",
                "pin_a",
                "pin_b",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<AdjacentConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<AdjacentConstraint>(py),
            vec![
                self.a.clone_ref(py),
                self.b.clone_ref(py),
                self.max_distance_mm.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.metric.clone_ref(py),
                self.pin_a.clone_ref(py),
                self.pin_b.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// SeparatedConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct SeparatedConstraint {
    a: Py<PyAny>,
    b: Py<PyAny>,
    min_distance_mm: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    metric: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl SeparatedConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (a, b, min_distance_mm, tier, because, metric=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        a: Bound<'_, PyAny>,
        b: Bound<'_, PyAny>,
        min_distance_mm: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        metric: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let metric = match metric {
                Some(m) => m.unbind(),
                None => enum_member(py, &constraint_types(py)?.distance_metric, "EDGE_TO_EDGE")?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "SEPARATED",
                |py| {
                    Ok(
                        PyString::new(py, &format!("sep_{}_{}", py_str(py, &a)?, py_str(py, &b)?))
                            .into_any()
                            .unbind(),
                    )
                },
            )?;
            Ok(Self {
                a: a.unbind(),
                b: b.unbind(),
                min_distance_mm: min_distance_mm.unbind(),
                tier: base.tier,
                because: base.because,
                metric,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        Ok(self.a.bind(py).eq(&comp)? || self.b.bind(py).eq(&comp)?)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "a", self.a.bind(py))?;
            set_dict_item(&d, "b", self.b.bind(py))?;
            set_dict_item(&d, "min_distance_mm", self.min_distance_mm.bind(py))?;
            set_dict_item(&d, "metric", &to_value(py, self.metric.bind(py))?)?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn a(&self, py: Python<'_>) -> Py<PyAny> {
        self.a.clone_ref(py)
    }

    #[setter]
    fn set_a(&mut self, value: Bound<'_, PyAny>) {
        self.a = value.unbind();
    }

    #[getter]
    fn b(&self, py: Python<'_>) -> Py<PyAny> {
        self.b.clone_ref(py)
    }

    #[setter]
    fn set_b(&mut self, value: Bound<'_, PyAny>) {
        self.b = value.unbind();
    }

    #[getter]
    fn min_distance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.min_distance_mm.clone_ref(py)
    }

    #[setter]
    fn set_min_distance_mm(&mut self, value: Bound<'_, PyAny>) {
        self.min_distance_mm = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn metric(&self, py: Python<'_>) -> Py<PyAny> {
        self.metric.clone_ref(py)
    }

    #[setter]
    fn set_metric(&mut self, value: Bound<'_, PyAny>) {
        self.metric = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.a.clone_ref(py),
            self.b.clone_ref(py),
            self.min_distance_mm.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.metric.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "SeparatedConstraint",
            &[
                "a",
                "b",
                "min_distance_mm",
                "tier",
                "because",
                "metric",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<SeparatedConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<SeparatedConstraint>(py),
            vec![
                self.a.clone_ref(py),
                self.b.clone_ref(py),
                self.min_distance_mm.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.metric.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// EnclosingConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct EnclosingConstraint {
    outer: Py<PyAny>,
    inner: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    margin_mm: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl EnclosingConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (outer, inner, tier, because, margin_mm=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        outer: Bound<'_, PyAny>,
        inner: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        margin_mm: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let margin_mm = match margin_mm {
                Some(v) => v.unbind(),
                None => default_float(py, 0.0)?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "ENCLOSING",
                |py| {
                    Ok(PyString::new(py, &format!("enc_{}", py_str(py, &outer)?))
                        .into_any()
                        .unbind())
                },
            )?;
            Ok(Self {
                outer: outer.unbind(),
                inner: inner.unbind(),
                tier: base.tier,
                because: base.because,
                margin_mm,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        Ok(self.outer.bind(py).eq(&comp)? || self.inner.bind(py).contains(&comp)?)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "outer", self.outer.bind(py))?;
            set_dict_item(&d, "inner", self.inner.bind(py))?;
            set_dict_item(&d, "margin_mm", self.margin_mm.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn outer(&self, py: Python<'_>) -> Py<PyAny> {
        self.outer.clone_ref(py)
    }

    #[setter]
    fn set_outer(&mut self, value: Bound<'_, PyAny>) {
        self.outer = value.unbind();
    }

    #[getter]
    fn inner(&self, py: Python<'_>) -> Py<PyAny> {
        self.inner.clone_ref(py)
    }

    #[setter]
    fn set_inner(&mut self, value: Bound<'_, PyAny>) {
        self.inner = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn margin_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.margin_mm.clone_ref(py)
    }

    #[setter]
    fn set_margin_mm(&mut self, value: Bound<'_, PyAny>) {
        self.margin_mm = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.outer.clone_ref(py),
            self.inner.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.margin_mm.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "EnclosingConstraint",
            &[
                "outer",
                "inner",
                "tier",
                "because",
                "margin_mm",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<EnclosingConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<EnclosingConstraint>(py),
            vec![
                self.outer.clone_ref(py),
                self.inner.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.margin_mm.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// KeepoutConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct KeepoutConstraint {
    zone_name: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    margin_mm: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl KeepoutConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (zone_name, tier, because, margin_mm=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        zone_name: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        margin_mm: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let margin_mm = match margin_mm {
                Some(v) => v.unbind(),
                None => default_float(py, 0.0)?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "KEEPOUT",
                |py| {
                    Ok(
                        PyString::new(py, &format!("keepout_{}", py_str(py, &zone_name)?))
                            .into_any()
                            .unbind(),
                    )
                },
            )?;
            Ok(Self {
                zone_name: zone_name.unbind(),
                tier: base.tier,
                because: base.because,
                margin_mm,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        self.zone_name.bind(py).eq(&comp)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "zone_name", self.zone_name.bind(py))?;
            set_dict_item(&d, "margin_mm", self.margin_mm.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn zone_name(&self, py: Python<'_>) -> Py<PyAny> {
        self.zone_name.clone_ref(py)
    }

    #[setter]
    fn set_zone_name(&mut self, value: Bound<'_, PyAny>) {
        self.zone_name = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn margin_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.margin_mm.clone_ref(py)
    }

    #[setter]
    fn set_margin_mm(&mut self, value: Bound<'_, PyAny>) {
        self.margin_mm = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.zone_name.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.margin_mm.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "KeepoutConstraint",
            &[
                "zone_name",
                "tier",
                "because",
                "margin_mm",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<KeepoutConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<KeepoutConstraint>(py),
            vec![
                self.zone_name.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.margin_mm.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// AlignedConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct AlignedConstraint {
    components: Py<PyAny>,
    axis: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    tolerance_mm: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl AlignedConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (components, axis, tier, because, tolerance_mm=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        components: Bound<'_, PyAny>,
        axis: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        tolerance_mm: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let n: usize = components.call_method0("__len__")?.extract()?;
            if n < 2 {
                return Err(PyValueError::new_err(
                    "AlignedConstraint requires at least 2 components",
                ));
            }
            let tolerance_mm = match tolerance_mm {
                Some(v) => v.unbind(),
                None => default_float(py, 0.5)?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "ALIGNED",
                |py| {
                    let axis_value = enum_value_str(py, &axis)?;
                    let comp_str = join_first_three(py, &components)?;
                    Ok(PyString::new(py, &format!("align_{axis_value}_{comp_str}"))
                        .into_any()
                        .unbind())
                },
            )?;
            Ok(Self {
                components: components.unbind(),
                axis: axis.unbind(),
                tier: base.tier,
                because: base.because,
                tolerance_mm,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        self.components.bind(py).contains(&comp)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "components", self.components.bind(py))?;
            set_dict_item(&d, "axis", &to_value(py, self.axis.bind(py))?)?;
            set_dict_item(&d, "tolerance_mm", self.tolerance_mm.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn components(&self, py: Python<'_>) -> Py<PyAny> {
        self.components.clone_ref(py)
    }

    #[setter]
    fn set_components(&mut self, value: Bound<'_, PyAny>) {
        self.components = value.unbind();
    }

    #[getter]
    fn axis(&self, py: Python<'_>) -> Py<PyAny> {
        self.axis.clone_ref(py)
    }

    #[setter]
    fn set_axis(&mut self, value: Bound<'_, PyAny>) {
        self.axis = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn tolerance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.tolerance_mm.clone_ref(py)
    }

    #[setter]
    fn set_tolerance_mm(&mut self, value: Bound<'_, PyAny>) {
        self.tolerance_mm = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.components.clone_ref(py),
            self.axis.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.tolerance_mm.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "AlignedConstraint",
            &[
                "components",
                "axis",
                "tier",
                "because",
                "tolerance_mm",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<AlignedConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<AlignedConstraint>(py),
            vec![
                self.components.clone_ref(py),
                self.axis.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.tolerance_mm.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// OnSideConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct OnSideConstraint {
    components: Py<PyAny>,
    side: Py<PyAny>,
    edge: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    max_distance_mm: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl OnSideConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (components, side, edge, tier, because, max_distance_mm=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        components: Bound<'_, PyAny>,
        side: Bound<'_, PyAny>,
        edge: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        max_distance_mm: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let max_distance_mm = match max_distance_mm {
                Some(v) => v.unbind(),
                None => default_float(py, 5.0)?,
            };
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "ON_SIDE",
                |py| {
                    let side_value = enum_value_str(py, &side)?;
                    let comp_str = join_first_three(py, &components)?;
                    Ok(PyString::new(py, &format!("side_{side_value}_{comp_str}"))
                        .into_any()
                        .unbind())
                },
            )?;
            Ok(Self {
                components: components.unbind(),
                side: side.unbind(),
                edge: edge.unbind(),
                tier: base.tier,
                because: base.because,
                max_distance_mm,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        self.components.bind(py).contains(&comp)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "components", self.components.bind(py))?;
            set_dict_item(&d, "side", &to_value(py, self.side.bind(py))?)?;
            set_dict_item(&d, "edge", &to_value(py, self.edge.bind(py))?)?;
            set_dict_item(&d, "max_distance_mm", self.max_distance_mm.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn components(&self, py: Python<'_>) -> Py<PyAny> {
        self.components.clone_ref(py)
    }

    #[setter]
    fn set_components(&mut self, value: Bound<'_, PyAny>) {
        self.components = value.unbind();
    }

    #[getter]
    fn side(&self, py: Python<'_>) -> Py<PyAny> {
        self.side.clone_ref(py)
    }

    #[setter]
    fn set_side(&mut self, value: Bound<'_, PyAny>) {
        self.side = value.unbind();
    }

    #[getter]
    fn edge(&self, py: Python<'_>) -> Py<PyAny> {
        self.edge.clone_ref(py)
    }

    #[setter]
    fn set_edge(&mut self, value: Bound<'_, PyAny>) {
        self.edge = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn max_distance_mm(&self, py: Python<'_>) -> Py<PyAny> {
        self.max_distance_mm.clone_ref(py)
    }

    #[setter]
    fn set_max_distance_mm(&mut self, value: Bound<'_, PyAny>) {
        self.max_distance_mm = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.components.clone_ref(py),
            self.side.clone_ref(py),
            self.edge.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.max_distance_mm.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "OnSideConstraint",
            &[
                "components",
                "side",
                "edge",
                "tier",
                "because",
                "max_distance_mm",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<OnSideConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<OnSideConstraint>(py),
            vec![
                self.components.clone_ref(py),
                self.side.clone_ref(py),
                self.edge.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.max_distance_mm.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// AnchoredConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct AnchoredConstraint {
    component: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    region: Py<PyAny>,
    position: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl AnchoredConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (component, tier, because, region=None, position=None, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        component: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        region: Option<Bound<'_, PyAny>>,
        position: Option<Bound<'_, PyAny>>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let region = region.map_or_else(|| py.None(), |v| v.unbind());
            let position = position.map_or_else(|| py.None(), |v| v.unbind());
            let region_is_none = region.bind(py).is_none();
            let position_is_none = position.bind(py).is_none();
            if region_is_none && position_is_none {
                return Err(PyValueError::new_err(
                    "AnchoredConstraint requires either region or position",
                ));
            }
            if !region_is_none && !position_is_none {
                return Err(PyValueError::new_err(
                    "AnchoredConstraint cannot have both region and position",
                ));
            }
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "ANCHORED",
                |py| {
                    Ok(
                        PyString::new(py, &format!("anchor_{}", py_str(py, &component)?))
                            .into_any()
                            .unbind(),
                    )
                },
            )?;
            Ok(Self {
                component: component.unbind(),
                tier: base.tier,
                because: base.because,
                region,
                position,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, py: Python<'_>, component: String) -> PyResult<bool> {
        let comp = component.into_pyobject(py)?.into_any();
        self.component.bind(py).eq(&comp)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "component", self.component.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            if self.region.bind(py).is_truthy()? {
                set_dict_item(&d, "region", self.region.bind(py))?;
            }
            if self.position.bind(py).is_truthy()? {
                set_dict_item(&d, "position", self.position.bind(py))?;
            }
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn component(&self, py: Python<'_>) -> Py<PyAny> {
        self.component.clone_ref(py)
    }

    #[setter]
    fn set_component(&mut self, value: Bound<'_, PyAny>) {
        self.component = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn region(&self, py: Python<'_>) -> Py<PyAny> {
        self.region.clone_ref(py)
    }

    #[setter]
    fn set_region(&mut self, value: Bound<'_, PyAny>) {
        self.region = value.unbind();
    }

    #[getter]
    fn position(&self, py: Python<'_>) -> Py<PyAny> {
        self.position.clone_ref(py)
    }

    #[setter]
    fn set_position(&mut self, value: Bound<'_, PyAny>) {
        self.position = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.component.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.region.clone_ref(py),
            self.position.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "AnchoredConstraint",
            &[
                "component",
                "tier",
                "because",
                "region",
                "position",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<AnchoredConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<AnchoredConstraint>(py),
            vec![
                self.component.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.region.clone_ref(py),
                self.position.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// LoopAreaConstraint
// ---------------------------------------------------------------------------

#[pyclass(module = "temper_placer.pcl.constraints")]
pub struct LoopAreaConstraint {
    loop_name: Py<PyAny>,
    max_area_mm2: Py<PyAny>,
    tier: Py<PyAny>,
    because: Py<PyAny>,
    id: Py<PyAny>,
    constraint_type: Py<PyAny>,
    targets: Py<PyAny>,
}

#[pymethods]
impl LoopAreaConstraint {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (loop_name, max_area_mm2, tier, because, id=None, targets=None))]
    fn new(
        py: Python<'_>,
        loop_name: Bound<'_, PyAny>,
        max_area_mm2: Bound<'_, PyAny>,
        tier: Bound<'_, PyAny>,
        because: Bound<'_, PyAny>,
        id: Option<Bound<'_, PyAny>>,
        targets: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        catch_panic(|| {
            let base = resolve_base_state(
                py,
                tier,
                because,
                id.as_ref(),
                targets.as_ref(),
                "LOOP_AREA",
                |py| {
                    Ok(
                        PyString::new(py, &format!("loop_{}", py_str(py, &loop_name)?))
                            .into_any()
                            .unbind(),
                    )
                },
            )?;
            Ok(Self {
                loop_name: loop_name.unbind(),
                max_area_mm2: max_area_mm2.unbind(),
                tier: base.tier,
                because: base.because,
                id: base.id,
                constraint_type: base.constraint_type,
                targets: base.targets,
            })
        })
    }

    fn involves_component(&self, _py: Python<'_>, _component: String) -> PyResult<bool> {
        Ok(false)
    }

    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let d = PyDict::new(py);
            set_dict_item(&d, "type", &to_value(py, self.constraint_type.bind(py))?)?;
            set_dict_item(&d, "loop_name", self.loop_name.bind(py))?;
            set_dict_item(&d, "max_area_mm2", self.max_area_mm2.bind(py))?;
            set_dict_item(&d, "tier", &to_value(py, self.tier.bind(py))?)?;
            set_dict_item(&d, "because", self.because.bind(py))?;
            set_dict_item(&d, "id", self.id.bind(py))?;
            Ok(d.unbind())
        })
    }

    fn escalate(&mut self, py: Python<'_>) -> PyResult<()> {
        escalate_tier(py, &mut self.tier)
    }

    #[getter]
    fn loop_name(&self, py: Python<'_>) -> Py<PyAny> {
        self.loop_name.clone_ref(py)
    }

    #[setter]
    fn set_loop_name(&mut self, value: Bound<'_, PyAny>) {
        self.loop_name = value.unbind();
    }

    #[getter]
    fn max_area_mm2(&self, py: Python<'_>) -> Py<PyAny> {
        self.max_area_mm2.clone_ref(py)
    }

    #[setter]
    fn set_max_area_mm2(&mut self, value: Bound<'_, PyAny>) {
        self.max_area_mm2 = value.unbind();
    }

    #[getter]
    fn tier(&self, py: Python<'_>) -> Py<PyAny> {
        self.tier.clone_ref(py)
    }

    #[setter]
    fn set_tier(&mut self, value: Bound<'_, PyAny>) {
        self.tier = value.unbind();
    }

    #[getter]
    fn because(&self, py: Python<'_>) -> Py<PyAny> {
        self.because.clone_ref(py)
    }

    #[setter]
    fn set_because(&mut self, value: Bound<'_, PyAny>) {
        self.because = value.unbind();
    }

    #[getter]
    fn id(&self, py: Python<'_>) -> Py<PyAny> {
        self.id.clone_ref(py)
    }

    #[setter]
    fn set_id(&mut self, value: Bound<'_, PyAny>) {
        self.id = value.unbind();
    }

    #[getter]
    fn constraint_type(&self, py: Python<'_>) -> Py<PyAny> {
        self.constraint_type.clone_ref(py)
    }

    #[setter]
    fn set_constraint_type(&mut self, value: Bound<'_, PyAny>) {
        self.constraint_type = value.unbind();
    }

    #[getter]
    fn targets(&self, py: Python<'_>) -> Py<PyAny> {
        self.targets.clone_ref(py)
    }

    #[setter]
    fn set_targets(&mut self, value: Bound<'_, PyAny>) {
        self.targets = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.loop_name.clone_ref(py),
            self.max_area_mm2.clone_ref(py),
            self.tier.clone_ref(py),
            self.because.clone_ref(py),
            self.id.clone_ref(py),
            self.constraint_type.clone_ref(py),
            self.targets.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "LoopAreaConstraint",
            &[
                "loop_name",
                "max_area_mm2",
                "tier",
                "because",
                "id",
                "constraint_type",
                "targets",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<LoopAreaConstraint>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<LoopAreaConstraint>(py),
            vec![
                self.loop_name.clone_ref(py),
                self.max_area_mm2.clone_ref(py),
                self.tier.clone_ref(py),
                self.because.clone_ref(py),
                self.id.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// CompilationContext
// ---------------------------------------------------------------------------

#[pyclass(name = "CompilationContext", module = "temper_placer.pcl.constraints")]
pub struct PyCompilationContext {
    netlist: Py<PyAny>,
    board: Py<PyAny>,
    skeletons: Py<PyAny>,
    channel_widths: Py<PyAny>,
    design_rules: Py<PyAny>,
    extra: Py<PyAny>,
}

#[pymethods]
impl PyCompilationContext {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (netlist, board=None, skeletons=None, channel_widths=None, design_rules=None, extra=None))]
    fn new(
        py: Python<'_>,
        netlist: Bound<'_, PyAny>,
        board: Option<Bound<'_, PyAny>>,
        skeletons: Option<Bound<'_, PyAny>>,
        channel_widths: Option<Bound<'_, PyAny>>,
        design_rules: Option<Bound<'_, PyAny>>,
        extra: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let extra = match extra {
            Some(v) => v.unbind(),
            None => PyDict::new(py).into_any().unbind(),
        };
        Ok(Self {
            netlist: netlist.unbind(),
            board: board.map_or_else(|| py.None(), |v| v.unbind()),
            skeletons: skeletons.map_or_else(|| py.None(), |v| v.unbind()),
            channel_widths: channel_widths.map_or_else(|| py.None(), |v| v.unbind()),
            design_rules: design_rules.map_or_else(|| py.None(), |v| v.unbind()),
            extra,
        })
    }

    #[getter]
    fn netlist(&self, py: Python<'_>) -> Py<PyAny> {
        self.netlist.clone_ref(py)
    }

    #[setter]
    fn set_netlist(&mut self, value: Bound<'_, PyAny>) {
        self.netlist = value.unbind();
    }

    #[getter]
    fn board(&self, py: Python<'_>) -> Py<PyAny> {
        self.board.clone_ref(py)
    }

    #[setter]
    fn set_board(&mut self, value: Bound<'_, PyAny>) {
        self.board = value.unbind();
    }

    #[getter]
    fn skeletons(&self, py: Python<'_>) -> Py<PyAny> {
        self.skeletons.clone_ref(py)
    }

    #[setter]
    fn set_skeletons(&mut self, value: Bound<'_, PyAny>) {
        self.skeletons = value.unbind();
    }

    #[getter]
    fn channel_widths(&self, py: Python<'_>) -> Py<PyAny> {
        self.channel_widths.clone_ref(py)
    }

    #[setter]
    fn set_channel_widths(&mut self, value: Bound<'_, PyAny>) {
        self.channel_widths = value.unbind();
    }

    #[getter]
    fn design_rules(&self, py: Python<'_>) -> Py<PyAny> {
        self.design_rules.clone_ref(py)
    }

    #[setter]
    fn set_design_rules(&mut self, value: Bound<'_, PyAny>) {
        self.design_rules = value.unbind();
    }

    #[getter]
    fn extra(&self, py: Python<'_>) -> Py<PyAny> {
        self.extra.clone_ref(py)
    }

    #[setter]
    fn set_extra(&mut self, value: Bound<'_, PyAny>) {
        self.extra = value.unbind();
    }
    /// The dataclass field order (repr/eq/hash order).
    fn field_values(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.netlist.clone_ref(py),
            self.board.clone_ref(py),
            self.skeletons.clone_ref(py),
            self.channel_widths.clone_ref(py),
            self.design_rules.clone_ref(py),
            self.extra.clone_ref(py),
        ]
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let values = self.field_values(py);
        dataclass_repr(
            py,
            "CompilationContext",
            &[
                "netlist",
                "board",
                "skeletons",
                "channel_widths",
                "design_rules",
                "extra",
            ],
            &values,
        )
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(other) = other.cast::<PyCompilationContext>() else {
            return Ok(false);
        };
        eq_fields(py, &self.field_values(py), &other.borrow().field_values(py))
    }

    fn __ne__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(!self.__eq__(py, other)?)
    }

    fn __hash__(&self, py: Python<'_>) -> PyResult<isize> {
        tuple_hash(py, hashable_fields(py, self.field_values(py))?)
    }

    fn __reduce__(&self, py: Python<'_>) -> PyResult<(Py<PyAny>, Py<PyAny>)> {
        reduce_args(
            py,
            &PyType::new::<PyCompilationContext>(py),
            vec![
                self.netlist.clone_ref(py),
                self.board.clone_ref(py),
                self.skeletons.clone_ref(py),
                self.channel_widths.clone_ref(py),
                self.design_rules.clone_ref(py),
                self.extra.clone_ref(py),
            ],
        )
    }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<AdjacentConstraint>()?;
    m.add_class::<SeparatedConstraint>()?;
    m.add_class::<EnclosingConstraint>()?;
    m.add_class::<KeepoutConstraint>()?;
    m.add_class::<AlignedConstraint>()?;
    m.add_class::<OnSideConstraint>()?;
    m.add_class::<AnchoredConstraint>()?;
    m.add_class::<LoopAreaConstraint>()?;
    m.add_class::<PyCompilationContext>()?;
    Ok(())
}

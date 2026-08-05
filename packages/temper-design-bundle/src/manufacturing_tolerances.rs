//! Manufacturing tolerance model — the Wave 4 Phase 4 leftovers slice's
//! `manufacturing/tolerances.py` migration.
//!
//! Python reference: `temper_placer/manufacturing/tolerances.py`, pinned
//! VERBATIM in `packages/temper-placer/tests/manufacturing/_tolerances_py_oracle.py`
//! (commit `6290942be`). The pyo3 pyclasses here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/manufacturing/test_tolerances_rust_differential.py`
//! is the TDD oracle for this file, and the property suite
//! `test_tolerances_pbt.py` asserts the closed-form invariants independently.
//!
//! This is a pure data model: two plain `Enum`s (`CopperWeight` with float
//! values, `LayerType` with str values), two dataclasses (`ToleranceTable`,
//! `FeatureTolerance`), and the `ToleranceAnalyzer` whose two analysis
//! methods are closed-form arithmetic (table lookup with a fixed fallback,
//! then `2 * etch + reg` / `width ± etch`). No recursion, no iteration over
//! caller-sized collections with an order-sensitive fold, no file IO — the
//! structural proof and the induction non-applicability note live in this
//! crate's `VERIFICATION.md`.
//!
//! Bit-exactness notes:
//! - The enums are plain Python `Enum`s (NOT `IntEnum`): `str(member)` is
//!   `"CopperWeight.HALF_OZ"` (not the bare value), `repr(member)` is
//!   `<CopperWeight.HALF_OZ: 0.5>` with the value rendered by CPython's
//!   `repr(float)`/`repr(str)` rules, and `Cls(value)` resolves by value with
//!   Python's exact `ValueError` text (`999 is not a valid CopperWeight`,
//!   `'x' is not a valid LayerType` — quotes only for str values).
//! - `__repr__` renders strings with `py_str_repr` (B9: single quotes) and
//!   floats with `py_float_str` (B10: `1e+300`/`1e-05`/`nan`); both helpers
//!   are duplicated from the priority/design_rules copies per the established
//!   per-module convention.
//! - The dict fields (`etch_tolerance`, `registration`) are real Python
//!   dicts keyed by the pyclass enum members, so dict lookup, repr, and
//!   insertion order are all CPython's own (the differential asserts the
//!   dict contents and repr byte-for-byte).
//! - `ToleranceAnalyzer` receives the enum arguments as `&Bound<PyAny>` and
//!   passes them through to `dict.get` (via `get_item`), so a missing key
//!   falls back to the oracle's constants (`0.05` / `0.1`) and an unhashable
//!   key raises CPython's own `TypeError: unhashable type` — never a pyo3
//!   extraction error.
//!
//! Known, documented deviations (see `VERIFICATION.md`):
//! - Class-level Enum iteration (`for m in CopperWeight:`) is unavailable on
//!   pyo3 enums (no metaclass hook); `getattr`-based access covers every
//!   member in the differential suite. No in-repo consumer iterates these
//!   enums at class level.
//! - `ToleranceAnalyzer()`'s default table is built per-instance. The Python
//!   oracle evaluates `table: ToleranceTable = ToleranceTable()` once at
//!   definition time and shares that instance across all default analyzers;
//!   the pyclass builds a fresh default per instance. The shared-instance
//!   behaviour is unobservable — no consumer mutates the table — so this is
//!   not covered by the differential (and cannot be, without a mutable
//!   class-level default).
//! - A non-numeric dict VALUE raises a pyo3 `TypeError` where the oracle's
//!   arithmetic would raise a different-text `TypeError`; the oracle itself
//!   is broken there, so the differential does not cover it.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict};
use pyo3::IntoPyObjectExt;

// ---------------------------------------------------------------------------
// CPython repr(str)/repr(float) replicas (duplicated from priority.rs — see
// the module docstring; kept private per module so each keeps its own tests).
// ---------------------------------------------------------------------------

/// Render a `str` as CPython's `repr(str)` does: single-quoted with
/// backslash and single-quote escaping. Rust's `{:?}` renders double
/// quotes, which would diverge in dataclass reprs (B9).
fn py_str_repr(s: &str) -> String {
    let escaped = s.replace('\\', "\\\\").replace('\'', "\\'");
    format!("'{escaped}'")
}

/// Render `v` exactly as CPython's `repr(float)` does (B10): shortest
/// round-trip digits, `1e+300`/`1e-05` exponent form, `nan` not `NaN`.
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

#[cfg(test)]
mod py_repr_tests {
    use super::{py_float_str, py_str_repr};

    #[test]
    fn str_repr_matches_cpython() {
        assert_eq!(py_str_repr("clearance"), "'clearance'");
        assert_eq!(py_str_repr("a'b"), "'a\\'b'");
        assert_eq!(py_str_repr("a\\b"), "'a\\\\b'");
    }

    #[test]
    fn float_repr_matches_cpython_on_divergence_classes() {
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
    }

    #[test]
    fn float_repr_matches_cpython_on_ordinary_values() {
        assert_eq!(py_float_str(0.5), "0.5");
        assert_eq!(py_float_str(1.0), "1.0");
        assert_eq!(py_float_str(0.025), "0.025");
        assert_eq!(py_float_str(0.075), "0.075");
        assert_eq!(py_float_str(0.0), "0.0");
        assert_eq!(py_float_str(0.2), "0.2");
        assert_eq!(py_float_str(-2.25), "-2.25");
    }
}

// ---------------------------------------------------------------------------
// CopperWeight — plain Enum with float values (0.5 oz, 1.0 oz, 2.0 oz).
// ---------------------------------------------------------------------------

/// Copper weight in ounces per square foot (mirrors `CopperWeight` in
/// `temper_placer/manufacturing/tolerances.py`).
#[allow(non_camel_case_types)]
#[allow(clippy::upper_case_acronyms)] // variant names are the Python API surface
#[pyclass(frozen, eq, hash, from_py_object, module = "temper_design_bundle_python")]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CopperWeight {
    HALF_OZ,
    ONE_OZ,
    TWO_OZ,
}

impl CopperWeight {
    fn value_f64(&self) -> f64 {
        match self {
            CopperWeight::HALF_OZ => 0.5,
            CopperWeight::ONE_OZ => 1.0,
            CopperWeight::TWO_OZ => 2.0,
        }
    }

    fn name_str(&self) -> &'static str {
        match self {
            CopperWeight::HALF_OZ => "HALF_OZ",
            CopperWeight::ONE_OZ => "ONE_OZ",
            CopperWeight::TWO_OZ => "TWO_OZ",
        }
    }

    /// Rust-side `str(member)` rendering: plain `Enum.__str__` is
    /// `"CopperWeight.HALF_OZ"` (NOT the bare value — that is IntEnum).
    pub fn py_str(&self) -> String {
        format!("CopperWeight.{}", self.name_str())
    }

    /// Rust-side `repr(member)` rendering: `<CopperWeight.HALF_OZ: 0.5>`
    /// with the float value rendered by CPython repr rules.
    pub fn py_repr(&self) -> String {
        format!("<{}: {}>", self.py_str(), py_float_str(self.value_f64()))
    }
}

#[pymethods]
impl CopperWeight {
    /// Python `Enum(value)` mirror: resolve a member by its value with
    /// CPython's own `==` semantics (so `CopperWeight(1)` matches the 1.0
    /// member), raising the exact `ValueError` text CPython's plain Enum
    /// raises for unknown values — the value rendered by CPython `repr`,
    /// so ints render `999` and floats `0.75` exactly as Python does.
    #[new]
    fn from_value(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let candidates: [(f64, Self); 3] = [
            (0.5, CopperWeight::HALF_OZ),
            (1.0, CopperWeight::ONE_OZ),
            (2.0, CopperWeight::TWO_OZ),
        ];
        for (v, member) in candidates {
            if value.eq(&v.into_bound_py_any(py)?)? {
                return Ok(member);
            }
        }
        Err(PyValueError::new_err(format!(
            "{} is not a valid CopperWeight",
            value.repr()?
        )))
    }

    /// Python `Enum.name` mirror.
    #[getter]
    pub fn name(&self) -> &'static str {
        self.name_str()
    }

    /// Python `Enum.value` mirror (the float value).
    #[getter]
    pub fn value(&self) -> f64 {
        self.value_f64()
    }

    /// Python `str(member)` mirror: `"CopperWeight.HALF_OZ"`.
    fn __str__(&self) -> String {
        self.py_str()
    }

    /// Python `repr(member)` mirror: `"<CopperWeight.HALF_OZ: 0.5>"`.
    fn __repr__(&self) -> String {
        self.py_repr()
    }
}

// ---------------------------------------------------------------------------
// LayerType — plain Enum with str values.
// ---------------------------------------------------------------------------

/// Type of PCB layer (mirrors `LayerType` in
/// `temper_placer/manufacturing/tolerances.py`).
#[allow(non_camel_case_types)]
#[allow(clippy::upper_case_acronyms)] // variant names are the Python API surface
#[pyclass(frozen, eq, hash, from_py_object, module = "temper_design_bundle_python")]
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum LayerType {
    OUTER,
    INNER,
}

impl LayerType {
    fn value_str(&self) -> &'static str {
        match self {
            LayerType::OUTER => "outer",
            LayerType::INNER => "inner",
        }
    }

    fn name_str(&self) -> &'static str {
        match self {
            LayerType::OUTER => "OUTER",
            LayerType::INNER => "INNER",
        }
    }

    /// Rust-side `str(member)` rendering: plain `Enum.__str__`.
    pub fn py_str(&self) -> String {
        format!("LayerType.{}", self.name_str())
    }

    /// Rust-side `repr(member)` rendering: `<LayerType.OUTER: 'outer'>`
    /// with the str value rendered by CPython repr rules (quoted).
    pub fn py_repr(&self) -> String {
        format!("<{}: {}>", self.py_str(), py_str_repr(self.value_str()))
    }
}

#[pymethods]
impl LayerType {
    /// Python `Enum(value)` mirror: resolve a member by its str value with
    /// CPython's own `==` semantics, raising the exact `ValueError` text
    /// CPython's plain Enum raises for unknown values (`'x' is not a valid
    /// LayerType` — the value rendered by CPython `repr`, so str values are
    /// quoted).
    #[new]
    fn from_value(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Self> {
        let candidates: [(&str, Self); 2] = [
            ("outer", LayerType::OUTER),
            ("inner", LayerType::INNER),
        ];
        for (v, member) in candidates {
            if value.eq(&v.into_bound_py_any(py)?)? {
                return Ok(member);
            }
        }
        Err(PyValueError::new_err(format!(
            "{} is not a valid LayerType",
            value.repr()?
        )))
    }

    /// Python `Enum.name` mirror.
    #[getter]
    pub fn name(&self) -> &'static str {
        self.name_str()
    }

    /// Python `Enum.value` mirror (the str value).
    #[getter]
    pub fn value(&self) -> &'static str {
        self.value_str()
    }

    /// Python `str(member)` mirror: `"LayerType.OUTER"`.
    fn __str__(&self) -> String {
        self.py_str()
    }

    /// Python `repr(member)` mirror: `"<LayerType.OUTER: 'outer'>"`.
    fn __repr__(&self) -> String {
        self.py_repr()
    }
}

// ---------------------------------------------------------------------------
// ToleranceTable — the per-feature tolerance specification dataclass.
// ---------------------------------------------------------------------------

/// Per-feature tolerance specifications (mirrors `ToleranceTable`).
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct ToleranceTable {
    #[pyo3(get)]
    pub etch_tolerance: Py<PyAny>,
    #[pyo3(get)]
    pub registration: Py<PyAny>,
    #[pyo3(get)]
    pub solder_mask_registration: f64,
}

impl ToleranceTable {
    /// Build the oracle's default etch dict:
    /// `{CopperWeight.HALF_OZ: 0.025, CopperWeight.ONE_OZ: 0.05,
    ///   CopperWeight.TWO_OZ: 0.075}` — a real Python dict keyed by the
    /// pyclass enum members, so repr/insertion order are CPython's own.
    fn default_etch_tolerance(py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item(CopperWeight::HALF_OZ.into_pyobject(py)?.into_any(), 0.025_f64)?;
        dict.set_item(CopperWeight::ONE_OZ.into_pyobject(py)?.into_any(), 0.05_f64)?;
        dict.set_item(CopperWeight::TWO_OZ.into_pyobject(py)?.into_any(), 0.075_f64)?;
        Ok(dict.into_any().unbind())
    }

    /// Build the oracle's default registration dict:
    /// `{LayerType.OUTER: 0.1, LayerType.INNER: 0.15}`.
    fn default_registration(py: Python<'_>) -> PyResult<Py<PyAny>> {
        let dict = PyDict::new(py);
        dict.set_item(LayerType::OUTER.into_pyobject(py)?.into_any(), 0.1_f64)?;
        dict.set_item(LayerType::INNER.into_pyobject(py)?.into_any(), 0.15_f64)?;
        Ok(dict.into_any().unbind())
    }
}

#[pymethods]
impl ToleranceTable {
    /// Dataclass-style constructor with the oracle's `default_factory` dicts.
    #[new]
    #[pyo3(signature = (etch_tolerance=None, registration=None, solder_mask_registration=0.075))]
    fn new(
        py: Python<'_>,
        etch_tolerance: Option<&Bound<'_, PyAny>>,
        registration: Option<&Bound<'_, PyAny>>,
        solder_mask_registration: f64,
    ) -> PyResult<Self> {
        Ok(Self {
            etch_tolerance: match etch_tolerance {
                Some(v) => v.clone().unbind(),
                None => Self::default_etch_tolerance(py)?,
            },
            registration: match registration {
                Some(v) => v.clone().unbind(),
                None => Self::default_registration(py)?,
            },
            solder_mask_registration,
        })
    }

    /// Dataclass-style equality (all three fields).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let Ok(other) = other.cast::<Self>() else {
            return Ok(PyBool::new(py, false).to_owned().into_any().unbind());
        };
        let lhs = slf.borrow();
        let rhs = other.borrow();
        let equal = lhs
            .etch_tolerance
            .bind(py)
            .eq(rhs.etch_tolerance.bind(py))?
            && lhs
                .registration
                .bind(py)
                .eq(rhs.registration.bind(py))?
            && lhs.solder_mask_registration == rhs.solder_mask_registration;
        Ok(PyBool::new(py, equal).to_owned().into_any().unbind())
    }

    /// Dataclass-style repr with CPython str/float rendering. The dicts
    /// render through Python's own `repr` (key reprs are the enum pyclass
    /// reprs, insertion order is CPython's).
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "ToleranceTable(etch_tolerance={}, registration={}, solder_mask_registration={})",
            self.etch_tolerance.bind(py).repr()?,
            self.registration.bind(py).repr()?,
            py_float_str(self.solder_mask_registration),
        ))
    }
}

// ---------------------------------------------------------------------------
// FeatureTolerance — the analysis-result dataclass.
// ---------------------------------------------------------------------------

/// Tolerance analysis for a specific feature (mirrors `FeatureTolerance`).
// Note: `from_py_object` (used on the other dataclasses) requires `Clone`,
// which `Py<PyAny>` fields cannot provide; nothing in the crate or the
// shim extracts a `FeatureTolerance` from an argument, so it is dropped.
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct FeatureTolerance {
    #[pyo3(get)]
    pub feature_type: String,
    /// The original caller object — the oracle's dataclass stores the
    /// argument unmodified, so an int nominal stays int (repr `1`, not
    /// `1.0`). Arithmetic-derived fields below are `f64` (the oracle's
    /// derived fields are floats whenever the table values are floats).
    #[pyo3(get)]
    pub nominal_value: Py<PyAny>,
    #[pyo3(get)]
    pub tolerance_plus: f64,
    #[pyo3(get)]
    pub tolerance_minus: f64,
    #[pyo3(get)]
    pub worst_case_min: f64,
    /// Original caller object for `analyze_clearance` (the oracle passes
    /// `clearance_mm` through unchanged); the trace arm stores the computed
    /// `width + etch` float.
    #[pyo3(get)]
    pub worst_case_max: Py<PyAny>,
}

#[pymethods]
impl FeatureTolerance {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (feature_type, nominal_value, tolerance_plus, tolerance_minus, worst_case_min, worst_case_max))]
    fn new(
        feature_type: String,
        nominal_value: &Bound<'_, PyAny>,
        tolerance_plus: f64,
        tolerance_minus: f64,
        worst_case_min: f64,
        worst_case_max: &Bound<'_, PyAny>,
    ) -> Self {
        Self {
            feature_type,
            nominal_value: nominal_value.clone().unbind(),
            tolerance_plus,
            tolerance_minus,
            worst_case_min,
            worst_case_max: worst_case_max.clone().unbind(),
        }
    }

    /// Dataclass-style equality (all six fields). The preserved-object
    /// fields compare through CPython's own `==` (int 1 == float 1.0 is
    /// True, exactly like the dataclass).
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let Ok(other) = other.cast::<Self>() else {
            return Ok(PyBool::new(py, false).to_owned().into_any().unbind());
        };
        let lhs = slf.borrow();
        let rhs = other.borrow();
        let equal = lhs.feature_type == rhs.feature_type
            && lhs.nominal_value.bind(py).eq(rhs.nominal_value.bind(py))?
            && lhs.tolerance_plus == rhs.tolerance_plus
            && lhs.tolerance_minus == rhs.tolerance_minus
            && lhs.worst_case_min == rhs.worst_case_min
            && lhs.worst_case_max.bind(py).eq(rhs.worst_case_max.bind(py))?;
        Ok(PyBool::new(py, equal).to_owned().into_any().unbind())
    }

    /// Dataclass-style repr with CPython str/float rendering. The
    /// preserved-object fields render through CPython's own `repr()` (int
    /// `1` renders `1`, float `1.0` renders `1.0` — the dataclass's
    /// rendering of the stored object).
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "FeatureTolerance(feature_type={}, nominal_value={}, tolerance_plus={}, \
             tolerance_minus={}, worst_case_min={}, worst_case_max={})",
            py_str_repr(&self.feature_type),
            self.nominal_value.bind(py).repr()?,
            py_float_str(self.tolerance_plus),
            py_float_str(self.tolerance_minus),
            py_float_str(self.worst_case_min),
            self.worst_case_max.bind(py).repr()?,
        ))
    }
}

// ---------------------------------------------------------------------------
// ToleranceAnalyzer — the analysis compute.
// ---------------------------------------------------------------------------

/// Analyze tolerances for a design based on manufacturing capabilities
/// (mirrors `ToleranceAnalyzer`).
#[pyclass(module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct ToleranceAnalyzer {
    #[pyo3(get)]
    pub table: Py<PyAny>,
}

impl ToleranceAnalyzer {
    /// `dict.get(key, fallback)` through CPython's own dict so a missing key
    /// yields the fallback and an unhashable key raises CPython's own
    /// `TypeError: unhashable type: 'X'`.
    fn dict_get_f64(
        dict_obj: &Bound<'_, PyAny>,
        key: &Bound<'_, PyAny>,
        fallback: f64,
    ) -> PyResult<f64> {
        let dict = dict_obj
            .cast::<PyDict>()
            .map_err(|_| pyo3::exceptions::PyTypeError::new_err("expected a dict"))?;
        match dict.get_item(key)? {
            Some(v) => v.extract::<f64>(),
            None => Ok(fallback),
        }
    }
}

#[pymethods]
impl ToleranceAnalyzer {
    /// Mirrors `__init__(self, table: ToleranceTable = ToleranceTable())`.
    /// The Python default is evaluated once at definition time and shared;
    /// the pyclass builds a fresh default per instance (unobservable — the
    /// table is never mutated; see the module docstring).
    #[new]
    #[pyo3(signature = (table=None))]
    fn new(py: Python<'_>, table: Option<&Bound<'_, PyAny>>) -> PyResult<Self> {
        let table = match table {
            Some(v) => v.clone().unbind(),
            None => Bound::new(py, ToleranceTable::new(
                py,
                None,
                None,
                0.075,
            )?)?
            .into_any()
            .unbind(),
        };
        Ok(Self { table })
    }

    /// Calculate tolerance for a clearance (gap) between copper features.
    ///
    /// The enum arguments arrive as `&Bound<PyAny>` and are passed straight
    /// through to the dict lookup, so the fallback semantics (`0.05` /
    /// `0.1`) and the unhashable-key error are exactly the oracle's.
    fn analyze_clearance(
        &self,
        py: Python<'_>,
        clearance_mm: &Bound<'_, PyAny>,
        copper_weight: &Bound<'_, PyAny>,
        layer_type: &Bound<'_, PyAny>,
    ) -> PyResult<FeatureTolerance> {
        let table = self.table.bind(py);
        // The etch fallback is the oracle's `0.05` — the same constant
        // `analyze_trace` uses (a `0.06` fallback here shipped once and was
        // caught by the clearance-side fallback differential case; see the
        // module's VERIFICATION.md mutation record).
        let etch = Self::dict_get_f64(&table.getattr("etch_tolerance")?, copper_weight, 0.05)?;
        let reg = Self::dict_get_f64(&table.getattr("registration")?, layer_type, 0.1)?;

        // Oracle: `total_minus = 2 * etch + reg` (left-associative).
        let total_minus = 2.0 * etch + reg;
        let clearance: f64 = clearance_mm.extract()?;

        Ok(FeatureTolerance {
            feature_type: "clearance".to_string(),
            // The oracle stores the ORIGINAL argument: `nominal_value` and
            // `worst_case_max` are the caller's object, so an int clearance
            // stays int (repr `1`, not `1.0`) — int preservation like the
            // monte_carlo dataclasses.
            nominal_value: clearance_mm.clone().unbind(),
            tolerance_plus: 0.0,
            tolerance_minus: total_minus,
            worst_case_min: clearance - total_minus,
            worst_case_max: clearance_mm.clone().unbind(),
        })
    }

    /// Calculate tolerance for trace width.
    fn analyze_trace(
        &self,
        py: Python<'_>,
        width_mm: &Bound<'_, PyAny>,
        copper_weight: &Bound<'_, PyAny>,
    ) -> PyResult<FeatureTolerance> {
        let table = self.table.bind(py);
        let etch = Self::dict_get_f64(&table.getattr("etch_tolerance")?, copper_weight, 0.05)?;
        let width: f64 = width_mm.extract()?;

        Ok(FeatureTolerance {
            feature_type: "trace_width".to_string(),
            // The oracle stores the ORIGINAL `width_mm` (int stays int).
            nominal_value: width_mm.clone().unbind(),
            tolerance_plus: etch,
            tolerance_minus: etch,
            worst_case_min: width - etch,
            worst_case_max: (width + etch).into_py_any(py)?,
        })
    }
}

// ---------------------------------------------------------------------------
// Registration.
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<CopperWeight>()?;
    module.add_class::<LayerType>()?;
    module.add_class::<ToleranceTable>()?;
    module.add_class::<FeatureTolerance>()?;
    module.add_class::<ToleranceAnalyzer>()?;
    Ok(())
}

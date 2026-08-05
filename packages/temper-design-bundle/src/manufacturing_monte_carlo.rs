//! Monte-Carlo statistical tolerance simulation — the Wave 4 Phase 4
//! leftovers slice's `manufacturing/monte_carlo.py` migration.
//!
//! Python reference: `temper_placer/manufacturing/monte_carlo.py`, pinned
//! VERBATIM in `packages/temper-placer/tests/manufacturing/_monte_carlo_py_oracle.py`
//! (commit `58b302ce8`). The pyo3 pyclasses here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/manufacturing/test_monte_carlo_rust_differential.py`
//! is the TDD oracle for this file, and the property suite
//! `test_monte_carlo_pbt.py` asserts the closed-form invariants
//! independently.
//!
//! Home crate: `temper-design-bundle` (the data-contract home — the
//! `manufacturing/tolerances.py` migration, this slice's sibling, landed
//! there; the simulator's result/config dataclasses are contract-adjacent).
//!
//! ## The RNG boundary (KTD9 — kept Python-side, argued in-source)
//!
//! `np.random.default_rng(seed)` returns a numpy `Generator` (PCG64 +
//! Ziggurat). The Ziggurat normal transform is a numpy library semantic
//! that no independent implementation reproduces bit-for-bit, and the
//! module's *contract* is the stream: same seed ⇒ same samples. The pyclass
//! therefore stores the numpy `Generator` itself as `_rng` (created by
//! numpy's own `default_rng` at construction) and every draw
//! (`rng.normal(mean, std, size=n)`, `rng.uniform(min_v, max_v, size=n)`)
//! is a Python call on that object with the oracle's exact arguments, in
//! the oracle's exact declaration order. The stream is bit-identical by
//! construction, and the differential pins it (same seed ⇒ same draws;
//! consecutive calls advance identically; the error path consumes draws
//! identically).
//!
//! ## The aggregation boundary (KTD9 — kept Python-side, argued in-source)
//!
//! `np.mean`/`np.std`/`astype`/`>=` on the min-distance vector are numpy
//! calls on both sides. numpy's `mean`/`std` use pairwise summation whose
//! block size is SIMD-dispatch-dependent (build and platform), so an
//! independent Rust replica would be bit-exact on one build and wrong on
//! another — a library semantic, not portable compute. The migrated part is
//! the [S,N,N] elementwise kernel (positions/bounds/etch/registration
//! expansion, pairwise separations, `np.maximum`, the 1e6 self-comparison
//! mask, and the exact min reduction): every elementwise op is a single
//! IEEE-754 double operation with the oracle's parenthesization, and the
//! min reduction is exact and order-independent for every value this
//! construction can produce (see `VERIFICATION.md` for the proof).
//!
//! ## Known, documented deviations (see `VERIFICATION.md`)
//!
//! - `MonteCarloSimulator(variables)` without `config` builds a FRESH
//!   default `MonteCarloConfig` per simulator. The Python oracle evaluates
//!   `config: MonteCarloConfig = MonteCarloConfig()` once at definition
//!   time and shares that instance across all default-config simulators.
//!   The shared-instance behaviour is unobservable through the values any
//!   consumer reads (no consumer mutates the shared config), and pyo3
//!   cannot hold a class-level mutable default instance (the config holds a
//!   Python tuple, so a `LazyLock<Py<...>>` static is not `Sync`).
//! - Input arrays must be 2-D numpy arrays (or any sequence-of-sequences of
//!   real numbers). Malformed shapes raise the oracle's own error classes
//!   where replicated (0-D/1-D positions and bounds → the fancy-indexing
//!   `IndexError` text, plain lists → the list-indexing `TypeError` text);
//!   ndim ≥ 3 positions/bounds compute something degenerate in the oracle
//!   and are outside the supported envelope (documented, no consumer has
//!   them). Complex dtypes are outside the envelope.
//! - Python-class `__eq__` semantics are reproduced via `dataclass_eq`;
//!   `MonteCarloSimulator` itself has no `__eq__` (identity, like the
//!   oracle's default object equality).

use pyo3::exceptions::{PyIndexError, PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use pyo3::IntoPyObjectExt;

use crate::netlist_contracts::{dataclass_eq, dataclass_repr, repr_of, unhashable};

// ---------------------------------------------------------------------------
// Shared helpers (per-module copies per the established convention).
// ---------------------------------------------------------------------------

/// `Option`-or-literal-default helper for scalar dataclass defaults —
/// type-preserving: the caller's object is stored as-is, and the default is
/// a freshly built Python object of the oracle's type.
fn opt_or<'py, T>(py: Python<'py>, value: Option<&Bound<'py, PyAny>>, default: T) -> PyResult<Py<PyAny>>
where
    T: IntoPyObject<'py>,
{
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => default.into_py_any(py),
    }
}

/// `samples.get(key, np.zeros(n_samples))` — dict get with numpy's zeros
/// default, both arms through CPython (the default is only built when the
/// key is absent, matching the observable result).
fn samples_get_or_zeros<'py>(
    py: Python<'py>,
    samples: &Bound<'py, PyAny>,
    key: &str,
    n_samples: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    if let Some(value) = samples.cast::<PyDict>()?.get_item(key)? {
        return Ok(value);
    }
    let np = py.import("numpy")?;
    np.call_method1("zeros", (n_samples,))
}

/// `np.maximum(a, b)` — NaN-propagating maximum. numpy's elementwise max
/// returns NaN when either operand is NaN (unlike Rust's `f64::max`, which
/// discards NaN), and returns the larger of ±0.0 on ties. In this
/// construction the separation operands can never be -0.0 (|a - b| is +0.0
/// or positive; `0.0 - 0.0` and `0.0 - (-0.0)` are both +0.0), so the
/// `b > a` tie-break is value-identical to numpy's.
#[inline]
fn np_max(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if b > a {
        b
    } else {
        a
    }
}

/// `np.min(a, b)` fold step — NaN-propagating minimum (numpy's min reduce
/// propagates NaN from any element; Rust's `f64::min` discards it). The
/// masked diagonal is 1e6 (positive), and no -0.0 value can appear (see
/// `np_max`), so the fold is exact and order-independent.
#[inline]
fn np_min(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if b < a {
        b
    } else {
        a
    }
}

/// Replicate the oracle's fancy-indexing error for non-2-D inputs.
/// `positions[None, :, :]` on a 0-D/1-D array raises
/// `IndexError: too many indices for array: array is N-dimensional, but 2
/// were indexed` (the `None` index does not count); on a plain list it
/// raises `TypeError: list indices must be integers or slices, not tuple`.
/// Both fire AFTER sampling in the oracle, and so do here.
fn check_positions_ndim(positions: &Bound<'_, PyAny>) -> PyResult<()> {
    match positions.getattr("ndim") {
        Ok(ndim) => {
            let ndim: i32 = ndim.extract()?;
            if ndim == 0 {
                return Err(PyIndexError::new_err(
                    "too many indices for array: array is 0-dimensional, but 2 were indexed",
                ));
            }
            if ndim == 1 {
                return Err(PyIndexError::new_err(
                    "too many indices for array: array is 1-dimensional, but 2 were indexed",
                ));
            }
            Ok(())
        }
        Err(_) => Err(PyTypeError::new_err(
            "list indices must be integers or slices, not tuple",
        )),
    }
}

/// `bounds[None, :, 0]` — the oracle's 3-index fancy indexing (a 0-D/1-D
/// array raises `IndexError` with "but 3 were indexed").
fn check_bounds_ndim(bounds: &Bound<'_, PyAny>) -> PyResult<()> {
    match bounds.getattr("ndim") {
        Ok(ndim) => {
            let ndim: i32 = ndim.extract()?;
            if ndim == 0 {
                return Err(PyIndexError::new_err(
                    "too many indices for array: array is 0-dimensional, but 3 were indexed",
                ));
            }
            if ndim == 1 {
                return Err(PyIndexError::new_err(
                    "too many indices for array: array is 1-dimensional, but 3 were indexed",
                ));
            }
            Ok(())
        }
        Err(_) => Err(PyTypeError::new_err(
            "list indices must be integers or slices, not tuple",
        )),
    }
}

// ---------------------------------------------------------------------------
// DistributionParams — the per-parameter distribution dataclass.
// ---------------------------------------------------------------------------

/// Parameters for a tolerance distribution (mirrors `DistributionParams`).
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct DistributionParams {
    #[pyo3(get, set)]
    pub mean: Py<PyAny>,
    #[pyo3(get, set)]
    pub std_dev: Py<PyAny>,
    #[pyo3(get, set)]
    pub distribution: Py<PyAny>,
    #[pyo3(get, set)]
    pub min_val: Py<PyAny>,
    #[pyo3(get, set)]
    pub max_val: Py<PyAny>,
}

impl DistributionParams {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.mean.clone_ref(py),
            self.std_dev.clone_ref(py),
            self.distribution.clone_ref(py),
            self.min_val.clone_ref(py),
            self.max_val.clone_ref(py),
        ]
    }

    fn build(
        py: Python<'_>,
        mean: &Bound<'_, PyAny>,
        std_dev: Option<&Bound<'_, PyAny>>,
        distribution: Option<&Bound<'_, PyAny>>,
        min_val: Option<&Bound<'_, PyAny>>,
        max_val: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let none = || py.None();
        Ok(Self {
            mean: mean.clone().unbind(),
            std_dev: opt_or(py, std_dev, 0.0_f64)?,
            distribution: opt_or(py, distribution, "normal")?,
            min_val: min_val.map_or_else(none, |v| v.clone().unbind()),
            max_val: max_val.map_or_else(none, |v| v.clone().unbind()),
        })
    }
}

#[pymethods]
impl DistributionParams {
    #[new]
    #[pyo3(signature = (mean, std_dev=None, distribution=None, min_val=None, max_val=None))]
    fn new(
        py: Python<'_>,
        mean: &Bound<'_, PyAny>,
        std_dev: Option<&Bound<'_, PyAny>>,
        distribution: Option<&Bound<'_, PyAny>>,
        min_val: Option<&Bound<'_, PyAny>>,
        max_val: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Self::build(py, mean, std_dev, distribution, min_val, max_val)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "DistributionParams",
            &[
                ("mean", repr_of(&self.mean, py)?),
                ("std_dev", repr_of(&self.std_dev, py)?),
                ("distribution", repr_of(&self.distribution, py)?),
                ("min_val", repr_of(&self.min_val, py)?),
                ("max_val", repr_of(&self.max_val, py)?),
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
        Err(unhashable("DistributionParams"))
    }
}

// ---------------------------------------------------------------------------
// ManufacturingVariables — all manufacturing parameters that vary.
// ---------------------------------------------------------------------------

/// All manufacturing parameters that vary during production (mirrors
/// `ManufacturingVariables`).
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct ManufacturingVariables {
    #[pyo3(get, set)]
    pub etch_tolerance: Py<PyAny>,
    #[pyo3(get, set)]
    pub drill_tolerance: Py<PyAny>,
    #[pyo3(get, set)]
    pub registration_x: Py<PyAny>,
    #[pyo3(get, set)]
    pub registration_y: Py<PyAny>,
    #[pyo3(get, set)]
    pub copper_thickness: Py<PyAny>,
    #[pyo3(get, set)]
    pub dielectric_thickness: Py<PyAny>,
}

impl ManufacturingVariables {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.etch_tolerance.clone_ref(py),
            self.drill_tolerance.clone_ref(py),
            self.registration_x.clone_ref(py),
            self.registration_y.clone_ref(py),
            self.copper_thickness.clone_ref(py),
            self.dielectric_thickness.clone_ref(py),
        ]
    }

    fn build(
        py: Python<'_>,
        etch_tolerance: Option<&Bound<'_, PyAny>>,
        drill_tolerance: Option<&Bound<'_, PyAny>>,
        registration_x: Option<&Bound<'_, PyAny>>,
        registration_y: Option<&Bound<'_, PyAny>>,
        copper_thickness: Option<&Bound<'_, PyAny>>,
        dielectric_thickness: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        let none = || py.None();
        Ok(Self {
            etch_tolerance: etch_tolerance.map_or_else(none, |v| v.clone().unbind()),
            drill_tolerance: drill_tolerance.map_or_else(none, |v| v.clone().unbind()),
            registration_x: registration_x.map_or_else(none, |v| v.clone().unbind()),
            registration_y: registration_y.map_or_else(none, |v| v.clone().unbind()),
            copper_thickness: copper_thickness.map_or_else(none, |v| v.clone().unbind()),
            dielectric_thickness: dielectric_thickness.map_or_else(none, |v| v.clone().unbind()),
        })
    }
}

#[pymethods]
impl ManufacturingVariables {
    #[new]
    #[pyo3(signature = (
        etch_tolerance=None,
        drill_tolerance=None,
        registration_x=None,
        registration_y=None,
        copper_thickness=None,
        dielectric_thickness=None,
    ))]
    fn new(
        py: Python<'_>,
        etch_tolerance: Option<&Bound<'_, PyAny>>,
        drill_tolerance: Option<&Bound<'_, PyAny>>,
        registration_x: Option<&Bound<'_, PyAny>>,
        registration_y: Option<&Bound<'_, PyAny>>,
        copper_thickness: Option<&Bound<'_, PyAny>>,
        dielectric_thickness: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Self::build(
            py,
            etch_tolerance,
            drill_tolerance,
            registration_x,
            registration_y,
            copper_thickness,
            dielectric_thickness,
        )
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ManufacturingVariables",
            &[
                ("etch_tolerance", repr_of(&self.etch_tolerance, py)?),
                ("drill_tolerance", repr_of(&self.drill_tolerance, py)?),
                ("registration_x", repr_of(&self.registration_x, py)?),
                ("registration_y", repr_of(&self.registration_y, py)?),
                ("copper_thickness", repr_of(&self.copper_thickness, py)?),
                ("dielectric_thickness", repr_of(&self.dielectric_thickness, py)?),
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
        Err(unhashable("ManufacturingVariables"))
    }
}

// ---------------------------------------------------------------------------
// MonteCarloConfig — simulation configuration dataclass.
// ---------------------------------------------------------------------------

/// Configuration for Monte Carlo simulation (mirrors `MonteCarloConfig`).
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct MonteCarloConfig {
    #[pyo3(get, set)]
    pub num_samples: Py<PyAny>,
    #[pyo3(get, set)]
    pub seed: Py<PyAny>,
    #[pyo3(get, set)]
    pub report_percentiles: Py<PyAny>,
}

impl MonteCarloConfig {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.num_samples.clone_ref(py),
            self.seed.clone_ref(py),
            self.report_percentiles.clone_ref(py),
        ]
    }

    fn build(
        py: Python<'_>,
        num_samples: Option<&Bound<'_, PyAny>>,
        seed: Option<&Bound<'_, PyAny>>,
        report_percentiles: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            num_samples: opt_or(py, num_samples, 1000_i64)?,
            seed: opt_or(py, seed, 42_i64)?,
            report_percentiles: match report_percentiles {
                Some(v) => v.clone().unbind(),
                None => PyTuple::new(py, [0.01_f64, 0.1, 0.5, 0.9, 0.99])?
                    .into_any()
                    .unbind(),
            },
        })
    }
}

#[pymethods]
impl MonteCarloConfig {
    #[new]
    #[pyo3(signature = (num_samples=None, seed=None, report_percentiles=None))]
    fn new(
        py: Python<'_>,
        num_samples: Option<&Bound<'_, PyAny>>,
        seed: Option<&Bound<'_, PyAny>>,
        report_percentiles: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Self::build(py, num_samples, seed, report_percentiles)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "MonteCarloConfig",
            &[
                ("num_samples", repr_of(&self.num_samples, py)?),
                ("seed", repr_of(&self.seed, py)?),
                ("report_percentiles", repr_of(&self.report_percentiles, py)?),
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
        Err(unhashable("MonteCarloConfig"))
    }
}

// ---------------------------------------------------------------------------
// MonteCarloResult — results of a statistical tolerance simulation.
// ---------------------------------------------------------------------------

/// Results of a statistical tolerance simulation (mirrors
/// `MonteCarloResult`).
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct MonteCarloResult {
    #[pyo3(get, set)]
    pub num_samples: Py<PyAny>,
    #[pyo3(get, set)]
    pub yield_probability: Py<PyAny>,
    #[pyo3(get, set)]
    pub failure_modes: Py<PyAny>,
    #[pyo3(get, set)]
    pub stats: Py<PyAny>,
}

impl MonteCarloResult {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.num_samples.clone_ref(py),
            self.yield_probability.clone_ref(py),
            self.failure_modes.clone_ref(py),
            self.stats.clone_ref(py),
        ]
    }

    fn build(
        py: Python<'_>,
        num_samples: &Bound<'_, PyAny>,
        yield_probability: &Bound<'_, PyAny>,
        failure_modes: Option<&Bound<'_, PyAny>>,
        stats: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            num_samples: num_samples.clone().unbind(),
            yield_probability: yield_probability.clone().unbind(),
            // `field(default_factory=list)` / `field(default_factory=dict)`
            // -- a FRESH empty container per instance.
            failure_modes: match failure_modes {
                Some(v) => v.clone().unbind(),
                None => PyList::empty(py).into_any().unbind(),
            },
            stats: match stats {
                Some(v) => v.clone().unbind(),
                None => PyDict::new(py).into_any().unbind(),
            },
        })
    }
}

#[pymethods]
impl MonteCarloResult {
    #[new]
    #[pyo3(signature = (num_samples, yield_probability, failure_modes=None, stats=None))]
    fn new(
        py: Python<'_>,
        num_samples: &Bound<'_, PyAny>,
        yield_probability: &Bound<'_, PyAny>,
        failure_modes: Option<&Bound<'_, PyAny>>,
        stats: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Self::build(py, num_samples, yield_probability, failure_modes, stats)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "MonteCarloResult",
            &[
                ("num_samples", repr_of(&self.num_samples, py)?),
                ("yield_probability", repr_of(&self.yield_probability, py)?),
                ("failure_modes", repr_of(&self.failure_modes, py)?),
                ("stats", repr_of(&self.stats, py)?),
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
        Err(unhashable("MonteCarloResult"))
    }
}

// ---------------------------------------------------------------------------
// MonteCarloSimulator — sampling + the clearance-simulation kernel.
// ---------------------------------------------------------------------------

/// The six manufacturing-parameter names, in the oracle's fixed declaration
/// order (dict insertion order and RNG consumption order both follow it).
const PARAMETER_NAMES: [&str; 6] = [
    "etch_tolerance",
    "drill_tolerance",
    "registration_x",
    "registration_y",
    "copper_thickness",
    "dielectric_thickness",
];

/// Run Monte Carlo tolerance simulations (mirrors `MonteCarloSimulator`).
// `dict`: the oracle class carries a `__dict__`; pyclass(dict) keeps
// attribute injection working.
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct MonteCarloSimulator {
    #[pyo3(get, set)]
    pub variables: Py<PyAny>,
    #[pyo3(get, set)]
    pub config: Py<PyAny>,
    /// The numpy `Generator` — created and advanced by numpy itself (the
    /// KTD9 RNG boundary; see the module docstring).
    #[pyo3(get, set, name = "_rng")]
    pub rng: Py<PyAny>,
}

impl MonteCarloSimulator {
    /// The [S,N,N] clearance kernel: expansion, pairwise separations, the
    /// 1e6 self-comparison mask and the NaN-propagating min reduction, all
    /// in exact IEEE-754 double arithmetic with the oracle's
    /// parenthesization. Returns one min distance per sample.
    fn clearance_min_distances(
        positions: &[Vec<f64>],
        bounds: &[Vec<f64>],
        etch: &[f64],
        reg_x: &[f64],
        reg_y: &[f64],
    ) -> Vec<f64> {
        let n = positions.len();
        let s = etch.len();
        let mut min_dists = Vec::with_capacity(s);
        for si in 0..s {
            let e = etch[si];
            let rx = reg_x[si];
            let ry = reg_y[si];
            let mut m = f64::INFINITY;
            for i in 0..n {
                // s_pos = positions[None, :, :] + stack([reg_x, reg_y])[:, None, :]
                let s_posx = positions[i][0] + rx;
                let s_posy = positions[i][1] + ry;
                // s_widths = bounds[None, :, 0] + 2 * etch[:, None]
                let sw = bounds[i][0] + 2.0 * e;
                let sh = bounds[i][1] + 2.0 * e;
                for j in 0..n {
                    let t_posx = positions[j][0] + rx;
                    let t_posy = positions[j][1] + ry;
                    let tw = bounds[j][0] + 2.0 * e;
                    let th = bounds[j][1] + 2.0 * e;
                    let dx = (s_posx - t_posx).abs();
                    let dy = (s_posy - t_posy).abs();
                    // mw = (s_widths[:, :, None] + s_widths[:, None, :]) / 2.0
                    let mw = (sw + tw) / 2.0;
                    let mh = (sh + th) / 2.0;
                    let sep_x = dx - mw;
                    let sep_y = dy - mh;
                    // dist = np.maximum(sep_x, sep_y), then the eye-mask
                    // np.where(mask, 1e6, dist) — 1e6 is exact in f64.
                    let d = if i == j { 1e6 } else { np_max(sep_x, sep_y) };
                    // min_dists = np.min(dist, axis=(1, 2))
                    m = np_min(m, d);
                }
            }
            min_dists.push(m);
        }
        min_dists
    }
}

#[pymethods]
impl MonteCarloSimulator {
    #[new]
    #[pyo3(signature = (variables, config=None))]
    fn new(
        py: Python<'_>,
        variables: &Bound<'_, PyAny>,
        config: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        // Fresh default config per simulator (documented deviation — the
        // oracle shares one definition-time instance; see the module doc).
        let config: Py<PyAny> = match config {
            Some(c) => c.clone().unbind(),
            None => Py::new(py, MonteCarloConfig::build(py, None, None, None)?)?.into_any(),
        };
        // np.random.default_rng(config.seed) — numpy's own Generator.
        let seed = config.bind(py).getattr("seed")?;
        let np_random = py.import("numpy")?.getattr("random")?;
        let rng = np_random.call_method1("default_rng", (seed,))?;
        Ok(Self {
            variables: variables.clone().unbind(),
            config,
            rng: rng.unbind(),
        })
    }

    /// Generate n samples of all manufacturing parameters.
    fn sample_parameters<'py>(
        &self,
        py: Python<'py>,
        n: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let samples = PyDict::new(py);
        let rng = self.rng.bind(py);
        for name in PARAMETER_NAMES {
            let params = self.variables.bind(py).getattr(name)?;
            if params.is_none() {
                continue;
            }
            let distribution = params.getattr("distribution")?;
            let mean = params.getattr("mean")?;
            if distribution.eq("normal")? {
                let std_dev = params.getattr("std_dev")?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("size", n)?;
                let arr = rng.call_method("normal", (mean, std_dev), Some(&kwargs))?;
                samples.set_item(name, arr)?;
            } else if distribution.eq("uniform")? {
                // min_v = params.min_val if params.min_val is not None
                //         else params.mean - 1.0   (Python arithmetic)
                let min_val = params.getattr("min_val")?;
                let min_v = if min_val.is_none() {
                    mean.call_method1("__sub__", (1.0_f64,))?
                } else {
                    min_val
                };
                let max_val = params.getattr("max_val")?;
                let max_v = if max_val.is_none() {
                    mean.call_method1("__add__", (1.0_f64,))?
                } else {
                    max_val
                };
                let kwargs = PyDict::new(py);
                kwargs.set_item("size", n)?;
                let arr = rng.call_method("uniform", (min_v, max_v), Some(&kwargs))?;
                samples.set_item(name, arr)?;
            }
            // Any other distribution string: the oracle falls through and
            // the parameter is silently skipped.
        }
        Ok(samples.into_any())
    }

    /// Run statistical clearance simulation.
    ///
    /// The kernel (this method's Rust half) computes the [S,N,N] expansion
    /// and the exact min reduction; every numpy aggregation on the result
    /// (asarray / `>=` / astype / mean / std) runs through numpy itself so
    /// the aggregation semantics (pairwise summation, SIMD blocking) are
    /// numpy's on both sides of the differential.
    fn run_clearance_simulation<'py>(
        &self,
        py: Python<'py>,
        positions: &Bound<'py, PyAny>,
        bounds: &Bound<'py, PyAny>,
        required_clearance: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let n_samples = self.config.bind(py).getattr("num_samples")?;
        let samples = self.sample_parameters(py, &n_samples)?;

        let etch = samples_get_or_zeros(py, &samples, "etch_tolerance", &n_samples)?;
        let reg_x = samples_get_or_zeros(py, &samples, "registration_x", &n_samples)?;
        let reg_y = samples_get_or_zeros(py, &samples, "registration_y", &n_samples)?;

        // Malformed-shape parity (fired after sampling, like the oracle).
        check_positions_ndim(positions)?;
        check_bounds_ndim(bounds)?;

        // Exact widening of any real numeric dtype to f64 (float32 → f64
        // is exact; ints convert via Python's float()).
        let pos_v: Vec<Vec<f64>> = positions.extract()?;
        let bnd_v: Vec<Vec<f64>> = bounds.extract()?;
        let etch_v: Vec<f64> = etch.extract()?;
        let reg_x_v: Vec<f64> = reg_x.extract()?;
        let reg_y_v: Vec<f64> = reg_y.extract()?;

        let n = pos_v.len();
        // numpy's min-reduction over empty slices has no identity:
        // np.min(dist, axis=(1, 2)) with N == 0 raises this exact error.
        if n == 0 {
            return Err(PyValueError::new_err(
                "zero-size array to reduction operation minimum which has no identity",
            ));
        }

        let min_dists = Self::clearance_min_distances(&pos_v, &bnd_v, &etch_v, &reg_x_v, &reg_y_v);

        // ---- The aggregation tail: numpy's own calls, in the oracle's
        // order, on the kernel's output (KTD9; see the module docstring).
        let np = py.import("numpy")?;
        let min_dists_list = PyList::new(py, min_dists)?;
        let min_dists_arr = np.call_method1("asarray", (min_dists_list,))?;
        // passes = min_dists >= required_clearance
        let passes = min_dists_arr.rich_compare(required_clearance, pyo3::basic::CompareOp::Ge)?;
        // yield_prob = np.mean(passes.astype(np.float32))
        let passes_f32 = passes.call_method1("astype", (np.getattr("float32")?,))?;
        let yield_prob = np.call_method1("mean", (passes_f32,))?;
        // float(np.float32) — exact widening to a Python float.
        let yield_prob_f: f64 = yield_prob.extract()?;
        // stats = {"mean_min_clearance": float(np.mean(min_dists)),
        //          "std_min_clearance": float(np.std(min_dists))}
        let mean_min = np.call_method1("mean", (min_dists_arr.clone(),))?;
        let std_min = np.call_method1("std", (min_dists_arr,))?;
        let mean_min_f: f64 = mean_min.extract()?;
        let std_min_f: f64 = std_min.extract()?;
        let stats = PyDict::new(py);
        stats.set_item("mean_min_clearance", mean_min_f.into_py_any(py)?)?;
        stats.set_item("std_min_clearance", std_min_f.into_py_any(py)?)?;

        let yield_obj = yield_prob_f.into_py_any(py)?;
        let stats_obj = stats.into_any();
        let result = Py::new(
            py,
            MonteCarloResult::build(
                py,
                &n_samples,
                yield_obj.bind(py),
                None,
                Some(&stats_obj),
            )?,
        )?;
        Ok(result.into_any().into_bound(py))
    }
}

// ---------------------------------------------------------------------------
// Registration.
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<DistributionParams>()?;
    module.add_class::<ManufacturingVariables>()?;
    module.add_class::<MonteCarloConfig>()?;
    module.add_class::<MonteCarloResult>()?;
    module.add_class::<MonteCarloSimulator>()?;
    Ok(())
}

#[cfg(test)]
mod kernel_tests {
    use super::*;

    #[test]
    fn np_max_propagates_nan_either_side() {
        assert!(np_max(f64::NAN, 1.0).is_nan());
        assert!(np_max(1.0, f64::NAN).is_nan());
    }

    #[test]
    fn np_min_propagates_nan_either_side() {
        assert!(np_min(f64::NAN, 1.0).is_nan());
        assert!(np_min(1.0, f64::NAN).is_nan());
    }

    #[test]
    fn np_max_returns_larger_including_signed_zero() {
        // numpy maximum(0.0, -0.0) == maximum(-0.0, 0.0) == 0.0; the b > a
        // tie-break returns +0.0 in both orders.
        assert_eq!(np_max(0.0, -0.0), 0.0);
        assert_eq!(np_max(-0.0, 0.0), 0.0);
        assert_eq!(np_max(0.0, 0.0).to_bits(), 0.0_f64.to_bits());
    }

    #[test]
    fn kernel_masks_diagonal_and_reduces_min() {
        // Two components, no noise: gap 2.0, sizes 1.0 → sep = 2.0 - 1.0.
        let positions = vec![vec![0.0, 0.0], vec![2.0, 0.0]];
        let bounds = vec![vec![1.0, 1.0], vec![1.0, 1.0]];
        let dists = MonteCarloSimulator::clearance_min_distances(
            &positions, &bounds, &[0.0], &[0.0], &[0.0],
        );
        assert_eq!(dists, vec![1.0]);
    }

    #[test]
    fn kernel_single_component_is_sentinel() {
        let positions = vec![vec![3.0, 4.0]];
        let bounds = vec![vec![2.0, 2.0]];
        let dists = MonteCarloSimulator::clearance_min_distances(
            &positions, &bounds, &[0.0, 1.0], &[0.0, 0.0], &[0.0, 0.0],
        );
        assert_eq!(dists, vec![1e6, 1e6]);
    }

    #[test]
    fn kernel_etch_expands_widths() {
        // gap 1.0, widths 2.0 → sep -1.0 with etch 0; etch 0.25 widens both
        // to 2.5 → sep 1.0 - 2.5 = -1.5.
        let positions = vec![vec![0.0, 0.0], vec![1.0, 0.0]];
        let bounds = vec![vec![2.0, 2.0], vec![2.0, 2.0]];
        let d0 = MonteCarloSimulator::clearance_min_distances(
            &positions, &bounds, &[0.0], &[0.0], &[0.0],
        );
        let d1 = MonteCarloSimulator::clearance_min_distances(
            &positions, &bounds, &[0.25], &[0.0], &[0.0],
        );
        assert_eq!(d0, vec![-1.0]);
        assert_eq!(d1, vec![-1.5]);
    }

    #[test]
    fn kernel_nan_propagates_through_reduction() {
        let positions = vec![vec![0.0, 0.0], vec![1.0, 0.0]];
        let bounds = vec![vec![1.0, 1.0], vec![1.0, 1.0]];
        let dists = MonteCarloSimulator::clearance_min_distances(
            &positions, &bounds, &[f64::NAN], &[0.0], &[0.0],
        );
        assert!(dists[0].is_nan());
    }
}

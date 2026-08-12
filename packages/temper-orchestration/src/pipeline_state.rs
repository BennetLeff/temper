// The U4 pipeline-state deliverable of the Rust Orchestration Engine plan
// (2026-08-09-001): the `pipeline/state.py` data model as pyclasses,
// bit-exact with the pre-migration module (the pinned oracle
// `tests/pipeline/_pipeline_state_py_oracle.py`; differential suite
// `tests/pipeline/test_pipeline_state_rust_differential.py`).
//
// `PipelinePhase`, `PipelineConfig` and `PipelineState` mirror the Python
// Enum/dataclass API exactly (constructors with the dataclass defaults,
// field get/set, `__eq__`/`__repr__`, unhashability). `PipelineError` is
// NOT migrated: it is an exception class (the plan's U4 row names only
// `PipelineConfig` / `PipelinePhase` for the Rust side; the shim keeps the
// Python exception).
//
// Bit-exactness traps pinned here (see the differential docstring):
// - The dataclass `__repr__` renders EVERY leaf via CPython's repr engine
//   (Paths, Enum members, dicts with Enum keys, floats incl. `1e+300`-style
//   exponent forms, strings with single quotes). The Rust `__repr__` calls
//   CPython `repr()` on each field value rather than using `format!`
//   (`{:.?}` on a float diverges for exponent notation; `{:?}` on a String
//   uses double quotes), so parity is by identity, not by coincidence of
//   formatter implementations.
// - Dataclass equality is exact-class + field-wise `==`. The Rust `__eq__`
//   type-checks the other operand's type identity first (subclasses and
//   non-instances are never equal), then compares every field with Python
//   `==` for the object fields and Rust `==` for the scalar fields (NaN !=
//   NaN and -0.0 == 0.0 behave identically in both).
// - Dataclasses are unhashable (`eq=True`, `frozen=False`). The Rust
//   `__hash__` raises `TypeError("unhashable type: '...'")`; `PipelinePhase`
//   members stay hashable (they are Enum singletons usable as dict keys).
// - The `field(default_factory=...)` defaults (`loops` -> fresh list,
//   `phase_timings` -> fresh dict) are per-instance: the constructor builds
//   a NEW `PyList`/`PyDict` whenever the argument is omitted. An EXPLICIT
//   `None` for either is treated as the omitted sentinel (a fresh container)
//   rather than stored as `None` -- a documented boundary: both fields are
//   type-annotated containers, so a caller passing `None` is already outside
//   the declared type (recorded in VERIFICATION.md, not silently diverged).
// - `current_phase=None` likewise constructs `PipelinePhase.INPUT` (the
//   dataclass default) instead of storing `None`.

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PyString};

// ---------------------------------------------------------------------------
// PipelinePhase (Enum)
// ---------------------------------------------------------------------------

/// Mirror of Python `pipeline.state.PipelinePhase(Enum)`.
///
/// Reproduced as a pyclass whose sixteen members are `#[classattr]`
/// singletons (the `TerminationReason` precedent). `__eq__` compares by
/// value; `__hash__` is a stable name hash (equal members must have equal
/// hashes), so members are usable as dict keys exactly like the Enum.
#[cfg_attr(feature = "python", pyclass(skip_from_py_object, module = "temper_orchestration", name = "PipelinePhase"))]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PipelinePhase {
    value: &'static str,
}

impl PipelinePhase {
    pub(crate) fn new(value: &'static str) -> Self {
        Self { value }
    }

    /// The Enum member name (the upper-case attribute), mirroring Python's
    /// `PipelinePhase.INPUT.name`.
    fn member_name(&self) -> &'static str {
        match self.value {
            "input" => "INPUT",
            "semantic" => "SEMANTIC",
            "topological" => "TOPOLOGICAL",
            "preflight" => "PREFLIGHT",
            "geometric" => "GEOMETRIC",
            "routing" => "ROUTING",
            "refinement" => "REFINEMENT",
            "output" => "OUTPUT",
            "zone_geometry" => "ZONE_GEOMETRY",
            "zone_assignment" => "ZONE_ASSIGNMENT",
            "slot_generation" => "SLOT_GENERATION",
            "component_assignment" => "COMPONENT_ASSIGNMENT",
            "apply_placements" => "APPLY_PLACEMENTS",
            "courtyard_check" => "COURTYARD_CHECK",
            "apply_placements_reapply" => "APPLY_PLACEMENTS_REAPPLY",
            "placement_validation" => "PLACEMENT_VALIDATION",
            _ => "UNKNOWN",
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PipelinePhase {
    #[classattr]
    #[allow(non_snake_case)]
    fn INPUT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("input"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn SEMANTIC(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("semantic"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn TOPOLOGICAL(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("topological"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn PREFLIGHT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("preflight"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn GEOMETRIC(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("geometric"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ROUTING(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("routing"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn REFINEMENT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("refinement"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn OUTPUT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("output"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ZONE_GEOMETRY(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("zone_geometry"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn ZONE_ASSIGNMENT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("zone_assignment"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn SLOT_GENERATION(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("slot_generation"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn COMPONENT_ASSIGNMENT(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("component_assignment"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn APPLY_PLACEMENTS(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("apply_placements"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn COURTYARD_CHECK(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("courtyard_check"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn APPLY_PLACEMENTS_REAPPLY(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("apply_placements_reapply"))
    }

    #[classattr]
    #[allow(non_snake_case)]
    fn PLACEMENT_VALIDATION(py: Python<'_>) -> PyResult<Py<Self>> {
        Py::new(py, Self::new("placement_validation"))
    }

    /// Python `PipelinePhase.INPUT.value` — the Enum's value string.
    #[getter]
    fn value(&self) -> &'static str {
        self.value
    }

    /// Python `PipelinePhase.INPUT.name` — the Enum member name.
    #[getter]
    fn name(&self) -> &'static str {
        self.member_name()
    }

    /// Enum repr: `<PipelinePhase.INPUT: 'input'>`.
    fn __repr__(&self) -> String {
        format!("<PipelinePhase.{}: '{}'>", self.member_name(), self.value)
    }

    /// Enum str: `PipelinePhase.INPUT`.
    fn __str__(&self) -> String {
        format!("PipelinePhase.{}", self.member_name())
    }

    /// Enum members compare equal by value; unequal to anything else.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let rhs = other.cast::<Self>()?.borrow();
        Ok(slf.borrow().value == rhs.value)
    }

    /// Enum members are hashable (dict keys); equal members hash equally.
    fn __hash__(&self) -> isize {
        self.value.as_bytes().iter().map(|&b| b as isize).sum()
    }
}

// ---------------------------------------------------------------------------
// repr helpers — every leaf rendered via CPython's repr engine
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
fn repr_obj(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    obj.repr()?.extract::<String>()
}

#[cfg(feature = "python")]
fn repr_opt(py: Python<'_>, obj: Option<&Py<PyAny>>) -> PyResult<String> {
    match obj {
        Some(o) => repr_obj(o.bind(py)),
        None => Ok("None".to_string()),
    }
}

#[cfg(feature = "python")]
fn repr_str(py: Python<'_>, s: &str) -> PyResult<String> {
    repr_obj(&PyString::new(py, s).into_any())
}

#[cfg(feature = "python")]
fn repr_float(py: Python<'_>, f: f64) -> PyResult<String> {
    repr_obj(&PyFloat::new(py, f).into_any())
}

// ---------------------------------------------------------------------------
// PipelineConfig (dataclass)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `pipeline.state.PipelineConfig` (dataclass).
#[pyclass(dict, from_py_object, module = "temper_orchestration", name = "PipelineConfig")]
#[derive(Clone, Debug)]
pub struct PipelineConfig {
    #[pyo3(get, set)]
    pub input_pcb: Py<PyAny>,
    #[pyo3(get, set)]
    pub constraints_yaml: Option<Py<PyAny>>,
    #[pyo3(get, set)]
    pub loops_yaml: Option<Py<PyAny>>,
    #[pyo3(get, set)]
    pub output_pcb: Option<Py<PyAny>>,
    #[pyo3(get, set)]
    pub output_report: Option<Py<PyAny>>,
    #[pyo3(get, set)]
    pub output_trace: Option<Py<PyAny>>,
    #[pyo3(get, set)]
    pub skip_topological: bool,
    #[pyo3(get, set)]
    pub skip_routing: bool,
    #[pyo3(get, set)]
    pub skip_local_refinement: bool,
    #[pyo3(get, set)]
    pub dry_run: bool,
    #[pyo3(get, set)]
    pub epochs: i64,
    #[pyo3(get, set)]
    pub seed: i64,
    #[pyo3(get, set)]
    pub max_movement_mm: f64,
    #[pyo3(get, set)]
    pub max_iterations: i64,
    #[pyo3(get, set)]
    pub routability_threshold: f64,
    #[pyo3(get, set)]
    pub convergence_threshold: f64,
    #[pyo3(get, set)]
    pub fab_preset: Option<String>,
}

#[cfg(feature = "python")]
#[pymethods]
impl PipelineConfig {
    /// The dataclass defaults, exactly.
    #[new]
    #[allow(clippy::too_many_arguments)] // one arg per dataclass field, mirroring the constructor
    #[pyo3(signature = (
        input_pcb,
        constraints_yaml=None,
        loops_yaml=None,
        output_pcb=None,
        output_report=None,
        output_trace=None,
        skip_topological=false,
        skip_routing=false,
        skip_local_refinement=false,
        dry_run=false,
        epochs=8000,
        seed=42,
        max_movement_mm=2.0,
        max_iterations=5,
        routability_threshold=0.85,
        convergence_threshold=0.01,
        fab_preset="jlcpcb_standard",
    ))]
    fn new(
        input_pcb: Py<PyAny>,
        constraints_yaml: Option<Py<PyAny>>,
        loops_yaml: Option<Py<PyAny>>,
        output_pcb: Option<Py<PyAny>>,
        output_report: Option<Py<PyAny>>,
        output_trace: Option<Py<PyAny>>,
        skip_topological: bool,
        skip_routing: bool,
        skip_local_refinement: bool,
        dry_run: bool,
        epochs: i64,
        seed: i64,
        max_movement_mm: f64,
        max_iterations: i64,
        routability_threshold: f64,
        convergence_threshold: f64,
        fab_preset: Option<&str>,
    ) -> Self {
        Self {
            input_pcb,
            constraints_yaml,
            loops_yaml,
            output_pcb,
            output_report,
            output_trace,
            skip_topological,
            skip_routing,
            skip_local_refinement,
            dry_run,
            epochs,
            seed,
            max_movement_mm,
            max_iterations,
            routability_threshold,
            convergence_threshold,
            fab_preset: fab_preset.map(str::to_owned),
        }
    }

    /// Dataclass-style repr — every leaf rendered via CPython's `repr()`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "PipelineConfig(input_pcb={}, constraints_yaml={}, loops_yaml={}, \
             output_pcb={}, output_report={}, output_trace={}, skip_topological={}, \
             skip_routing={}, skip_local_refinement={}, dry_run={}, epochs={}, \
             seed={}, max_movement_mm={}, max_iterations={}, routability_threshold={}, \
             convergence_threshold={}, fab_preset={})",
            repr_obj(self.input_pcb.bind(py))?,
            repr_opt(py, self.constraints_yaml.as_ref())?,
            repr_opt(py, self.loops_yaml.as_ref())?,
            repr_opt(py, self.output_pcb.as_ref())?,
            repr_opt(py, self.output_report.as_ref())?,
            repr_opt(py, self.output_trace.as_ref())?,
            if self.skip_topological { "True" } else { "False" },
            if self.skip_routing { "True" } else { "False" },
            if self.skip_local_refinement { "True" } else { "False" },
            if self.dry_run { "True" } else { "False" },
            self.epochs,
            self.seed,
            repr_float(py, self.max_movement_mm)?,
            self.max_iterations,
            repr_float(py, self.routability_threshold)?,
            repr_float(py, self.convergence_threshold)?,
            match &self.fab_preset {
                Some(s) => repr_str(py, s)?,
                None => "None".to_owned(),
            },
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        if !lhs.input_pcb.bind(slf.py()).eq(rhs.input_pcb.bind(slf.py()))? {
            return Ok(false);
        }
        if !opt_py_eq(slf.py(), lhs.constraints_yaml.as_ref(), rhs.constraints_yaml.as_ref())? {
            return Ok(false);
        }
        if !opt_py_eq(slf.py(), lhs.loops_yaml.as_ref(), rhs.loops_yaml.as_ref())? {
            return Ok(false);
        }
        if !opt_py_eq(slf.py(), lhs.output_pcb.as_ref(), rhs.output_pcb.as_ref())? {
            return Ok(false);
        }
        if !opt_py_eq(slf.py(), lhs.output_report.as_ref(), rhs.output_report.as_ref())? {
            return Ok(false);
        }
        if !opt_py_eq(slf.py(), lhs.output_trace.as_ref(), rhs.output_trace.as_ref())? {
            return Ok(false);
        }
        if lhs.skip_topological != rhs.skip_topological
            || lhs.skip_routing != rhs.skip_routing
            || lhs.skip_local_refinement != rhs.skip_local_refinement
            || lhs.dry_run != rhs.dry_run
        {
            return Ok(false);
        }
        if lhs.epochs != rhs.epochs || lhs.seed != rhs.seed {
            return Ok(false);
        }
        if lhs.max_movement_mm != rhs.max_movement_mm
            || lhs.max_iterations != rhs.max_iterations
            || lhs.routability_threshold != rhs.routability_threshold
            || lhs.convergence_threshold != rhs.convergence_threshold
        {
            return Ok(false);
        }
        if lhs.fab_preset != rhs.fab_preset {
            return Ok(false);
        }
        Ok(true)
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'PipelineConfig'"))
    }
}

// ---------------------------------------------------------------------------
// PipelineState (dataclass)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Mirror of Python `pipeline.state.PipelineState` (dataclass).
///
/// The `config` / `current_phase` / `failed_phase` fields are tightened to
/// their concrete pyclass counterparts (`PipelineConfig` / `PipelinePhase`):
/// the dataclass declares those types and every exercised caller (the
/// differential + re-export shim) passes them, so the typed extraction is a
/// lossless downcast, not a marshalling tax. The container / `Any` fields
/// stay `Py<PyAny>` (the dataclass does not type-enforce them; the
/// differential exercises them with arbitrary values). The scalar fields are
/// typed (`i64`/`bool`/`f64`).
#[pyclass(dict, from_py_object, module = "temper_orchestration", name = "PipelineState")]
#[derive(Clone, Debug)]
pub struct PipelineState {
    #[pyo3(get, set)]
    pub config: Py<PipelineConfig>,
    #[pyo3(get, set)]
    pub current_phase: Py<PipelinePhase>,
    #[pyo3(get, set)]
    pub iteration: i64,
    #[pyo3(get, set)]
    pub success: bool,
    #[pyo3(get, set)]
    pub failure_reason: Option<String>,
    #[pyo3(get, set)]
    pub failed_phase: Option<Py<PipelinePhase>>,
    #[pyo3(get, set)]
    pub elapsed_time_s: f64,
    #[pyo3(get, set)]
    pub phase_timings: Py<PyAny>,
    #[pyo3(get, set)]
    pub board: Py<PyAny>,
    #[pyo3(get, set)]
    pub netlist: Py<PyAny>,
    #[pyo3(get, set)]
    pub loops: Py<PyAny>,
    #[pyo3(get, set)]
    pub constraints: Py<PyAny>,
    #[pyo3(get, set)]
    pub deterministic_result: Py<PyAny>,
    #[pyo3(get, set)]
    pub placement_state: Py<PyAny>,
    #[pyo3(get, set)]
    pub routing_result: Py<PyAny>,
    #[pyo3(get, set)]
    pub physics_report: Py<PyAny>,
    #[pyo3(get, set)]
    pub preflight_report: Py<PyAny>,
    #[pyo3(get, set)]
    pub decision_trace: Py<PyAny>,
    #[pyo3(get, set)]
    pub _refinement_complete: bool,
    #[pyo3(get, set)]
    pub _best_routed_nets: Py<PyAny>,
    #[pyo3(get, set)]
    pub _best_routability: Option<f64>,
    #[pyo3(get, set)]
    pub _stall_count: i64,
}

#[cfg(feature = "python")]
#[pymethods]
impl PipelineState {
    /// The dataclass defaults, exactly. `config` is the only required field.
    #[new]
    #[allow(clippy::too_many_arguments)] // one arg per dataclass field, mirroring the constructor
    #[pyo3(signature = (
        config,
        current_phase=None,
        iteration=0,
        success=false,
        failure_reason=None,
        failed_phase=None,
        elapsed_time_s=0.0,
        phase_timings=None,
        board=None,
        netlist=None,
        loops=None,
        constraints=None,
        deterministic_result=None,
        placement_state=None,
        routing_result=None,
        physics_report=None,
        preflight_report=None,
        decision_trace=None,
        _refinement_complete=false,
        _best_routed_nets=None,
        _best_routability=None,
        _stall_count=0,
    ))]
    #[allow(non_snake_case)]
    fn new(
        py: Python<'_>,
        config: Py<PipelineConfig>,
        current_phase: Option<Py<PipelinePhase>>,
        iteration: i64,
        success: bool,
        failure_reason: Option<String>,
        failed_phase: Option<Py<PipelinePhase>>,
        elapsed_time_s: f64,
        phase_timings: Option<Py<PyAny>>,
        board: Option<Py<PyAny>>,
        netlist: Option<Py<PyAny>>,
        loops: Option<Py<PyAny>>,
        constraints: Option<Py<PyAny>>,
        deterministic_result: Option<Py<PyAny>>,
        placement_state: Option<Py<PyAny>>,
        routing_result: Option<Py<PyAny>>,
        physics_report: Option<Py<PyAny>>,
        preflight_report: Option<Py<PyAny>>,
        decision_trace: Option<Py<PyAny>>,
        _refinement_complete: bool,
        _best_routed_nets: Option<Py<PyAny>>,
        _best_routability: Option<f64>,
        _stall_count: i64,
    ) -> PyResult<Self> {
        Ok(Self {
            config,
            // Omitted `current_phase` (the `None` sentinel) -> the dataclass
            // default PipelinePhase.INPUT.
            current_phase: match current_phase {
                Some(obj) => obj,
                None => Py::new(py, PipelinePhase::new("input"))?,
            },
            iteration,
            success,
            failure_reason,
            failed_phase,
            elapsed_time_s,
            // Omitted `phase_timings` (the `None` sentinel) -> a fresh dict
            // (the dataclass `field(default_factory=dict)`).
            phase_timings: match phase_timings {
                Some(obj) => obj,
                None => PyDict::new(py).into_any().unbind(),
            },
            board: board.unwrap_or_else(|| py.None()),
            netlist: netlist.unwrap_or_else(|| py.None()),
            // Omitted `loops` (the `None` sentinel) -> a fresh list (the
            // dataclass `field(default_factory=list)`).
            loops: match loops {
                Some(obj) => obj,
                None => PyList::empty(py).into_any().unbind(),
            },
            constraints: constraints.unwrap_or_else(|| py.None()),
            deterministic_result: deterministic_result.unwrap_or_else(|| py.None()),
            placement_state: placement_state.unwrap_or_else(|| py.None()),
            routing_result: routing_result.unwrap_or_else(|| py.None()),
            physics_report: physics_report.unwrap_or_else(|| py.None()),
            preflight_report: preflight_report.unwrap_or_else(|| py.None()),
            decision_trace: decision_trace.unwrap_or_else(|| py.None()),
            _refinement_complete,
            _best_routed_nets: _best_routed_nets.unwrap_or_else(|| py.None()),
            _best_routability,
            _stall_count,
        })
    }

    /// Dataclass-style repr — every leaf rendered via CPython's `repr()`.
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "PipelineState(config={}, current_phase={}, iteration={}, success={}, \
             failure_reason={}, failed_phase={}, elapsed_time_s={}, phase_timings={}, \
             board={}, netlist={}, loops={}, constraints={}, deterministic_result={}, \
             placement_state={}, routing_result={}, physics_report={}, \
             preflight_report={}, decision_trace={}, _refinement_complete={}, \
             _best_routed_nets={}, _best_routability={}, _stall_count={})",
            repr_obj(self.config.bind(py).as_any())?,
            repr_obj(self.current_phase.bind(py).as_any())?,
            self.iteration,
            if self.success { "True" } else { "False" },
            repr_opt_str(py, self.failure_reason.as_deref())?,
            match &self.failed_phase {
                Some(p) => repr_obj(p.bind(py).as_any())?,
                None => "None".to_owned(),
            },
            repr_float(py, self.elapsed_time_s)?,
            repr_obj(self.phase_timings.bind(py))?,
            repr_obj(self.board.bind(py))?,
            repr_obj(self.netlist.bind(py))?,
            repr_obj(self.loops.bind(py))?,
            repr_obj(self.constraints.bind(py))?,
            repr_obj(self.deterministic_result.bind(py))?,
            repr_obj(self.placement_state.bind(py))?,
            repr_obj(self.routing_result.bind(py))?,
            repr_obj(self.physics_report.bind(py))?,
            repr_obj(self.preflight_report.bind(py))?,
            repr_obj(self.decision_trace.bind(py))?,
            if self._refinement_complete { "True" } else { "False" },
            repr_obj(self._best_routed_nets.bind(py))?,
            repr_opt_float(py, self._best_routability)?,
            self._stall_count,
        ))
    }

    /// Dataclass equality: exact class + field-wise `==`.
    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if !other.get_type().is(slf.get_type()) {
            return Ok(false);
        }
        let lhs = slf.borrow();
        let rhs = other.cast::<Self>()?.borrow();
        if !lhs.config.bind(slf.py()).as_any().eq(rhs.config.bind(slf.py()).as_any())? {
            return Ok(false);
        }
        if !lhs
            .current_phase
            .bind(slf.py())
            .as_any()
            .eq(rhs.current_phase.bind(slf.py()).as_any())?
        {
            return Ok(false);
        }
        if lhs.iteration != rhs.iteration {
            return Ok(false);
        }
        if lhs.success != rhs.success {
            return Ok(false);
        }
        if lhs.failure_reason != rhs.failure_reason {
            return Ok(false);
        }
        if !opt_py_eq_phase(slf.py(), lhs.failed_phase.as_ref(), rhs.failed_phase.as_ref())? {
            return Ok(false);
        }
        if lhs.elapsed_time_s != rhs.elapsed_time_s {
            return Ok(false);
        }
        if !lhs.phase_timings.bind(slf.py()).eq(rhs.phase_timings.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.board.bind(slf.py()).eq(rhs.board.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.netlist.bind(slf.py()).eq(rhs.netlist.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.loops.bind(slf.py()).eq(rhs.loops.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.constraints.bind(slf.py()).eq(rhs.constraints.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.deterministic_result.bind(slf.py()).eq(rhs.deterministic_result.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.placement_state.bind(slf.py()).eq(rhs.placement_state.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.routing_result.bind(slf.py()).eq(rhs.routing_result.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.physics_report.bind(slf.py()).eq(rhs.physics_report.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.preflight_report.bind(slf.py()).eq(rhs.preflight_report.bind(slf.py()))? {
            return Ok(false);
        }
        if !lhs.decision_trace.bind(slf.py()).eq(rhs.decision_trace.bind(slf.py()))? {
            return Ok(false);
        }
        if lhs._refinement_complete != rhs._refinement_complete {
            return Ok(false);
        }
        if !lhs._best_routed_nets.bind(slf.py()).eq(rhs._best_routed_nets.bind(slf.py()))? {
            return Ok(false);
        }
        if lhs._best_routability != rhs._best_routability {
            return Ok(false);
        }
        if lhs._stall_count != rhs._stall_count {
            return Ok(false);
        }
        Ok(true)
    }

    /// Dataclasses are unhashable (`eq=True`, `frozen=False`).
    fn __hash__(&self) -> PyResult<isize> {
        Err(PyTypeError::new_err("unhashable type: 'PipelineState'"))
    }
}

#[cfg(feature = "python")]
/// Python `==` for a pair of optional Python objects.
fn opt_py_eq(py: Python<'_>, a: Option<&Py<PyAny>>, b: Option<&Py<PyAny>>) -> PyResult<bool> {
    match (a, b) {
        (Some(x), Some(y)) => x.bind(py).eq(y.bind(py)),
        (None, None) => Ok(true),
        _ => Ok(false),
    }
}

#[cfg(feature = "python")]
/// Python `==` for a pair of optional `Py<PipelinePhase>` values — routed
/// through the pyclass `__eq__` (value-based), never `Py` pointer identity.
fn opt_py_eq_phase(
    py: Python<'_>,
    a: Option<&Py<PipelinePhase>>,
    b: Option<&Py<PipelinePhase>>,
) -> PyResult<bool> {
    match (a, b) {
        (Some(x), Some(y)) => x.bind(py).as_any().eq(y.bind(py).as_any()),
        (None, None) => Ok(true),
        _ => Ok(false),
    }
}

#[cfg(feature = "python")]
/// CPython `repr()` of an `Option<&str>` (None -> `None`, Some -> quoted str).
fn repr_opt_str(py: Python<'_>, s: Option<&str>) -> PyResult<String> {
    match s {
        Some(text) => repr_str(py, text),
        None => Ok("None".to_string()),
    }
}

#[cfg(feature = "python")]
/// CPython `repr()` of an `Option<f64>` (None -> `None`, Some -> float repr).
fn repr_opt_float(py: Python<'_>, f: Option<f64>) -> PyResult<String> {
    match f {
        Some(value) => repr_float(py, value),
        None => Ok("None".to_string()),
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn phase_member_names_map_exactly() {
        let cases = [
            ("input", "INPUT"),
            ("semantic", "SEMANTIC"),
            ("topological", "TOPOLOGICAL"),
            ("preflight", "PREFLIGHT"),
            ("geometric", "GEOMETRIC"),
            ("routing", "ROUTING"),
            ("refinement", "REFINEMENT"),
            ("output", "OUTPUT"),
            ("zone_geometry", "ZONE_GEOMETRY"),
            ("zone_assignment", "ZONE_ASSIGNMENT"),
            ("slot_generation", "SLOT_GENERATION"),
            ("component_assignment", "COMPONENT_ASSIGNMENT"),
            ("apply_placements", "APPLY_PLACEMENTS"),
            ("courtyard_check", "COURTYARD_CHECK"),
            ("apply_placements_reapply", "APPLY_PLACEMENTS_REAPPLY"),
            ("placement_validation", "PLACEMENT_VALIDATION"),
        ];
        for (value, name) in cases {
            let p = PipelinePhase::new(value);
            assert_eq!(p.value, value);
            assert_eq!(p.member_name(), name);
        }
    }

    #[cfg(feature = "python")]
    #[cfg_attr(test, test)]
    fn phase_eq_and_hash_are_value_consistent() {
        let a = PipelinePhase::new("input");
        let b = PipelinePhase::new("input");
        let c = PipelinePhase::new("output");
        assert_eq!(a, b);
        assert_ne!(a, c);
        assert_eq!(a.__hash__(), b.__hash__());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(feature = "python")] ("pipeline_state::tests::phase_member_names_map_exactly", phase_member_names_map_exactly),
        #[cfg(feature = "python")] ("pipeline_state::tests::phase_eq_and_hash_are_value_consistent", phase_eq_and_hash_are_value_consistent),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

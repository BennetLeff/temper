// Orchestration-port unit U-E (Rust Orchestration Engine plan 2026-08-09-001):
// the `DeterministicPipeline` pyclass hosting the factory + the run loop of
// `temper_placer/deterministic/__init__.py`.
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - the SEQUENCING loop of `DeterministicPipeline.run()`: `state =
//   stage.run(state)` per stage, with the per-stage DRCFence invocation
//   (`if self.fence and stage.invariants` -> `fence.check(...)` with the
//   `_board_state_to_drc_input` / `_issue_fingerprint` call-backs and the
//   `previous_violations` frozenset threading). The loop drives the stages
//   through the Rust `PipelineRunner<BoardState>`, threading the Python
//   `BoardState` object through a shared side-channel so untouched fields
//   keep OBJECT IDENTITY (the oracle never copies what no stage replaced).
//   A stage that raises halts the runner and the ORIGINAL exception is
//   re-raised (exception identity preserved, not re-wrapped).
// - the ORDER of `create_drc_aware_pipeline()`: the D1->D7 ordered
//   construction (23 stages), the zone-aware / standard slot-stage
//   selection, the phased / standard component-stage selection, and the
//   sidecar injection (`channel_map` into the phased stage when it has a
//   grid). The factory constructs the PYTHON shim stage objects (importing
//   `temper_placer.deterministic.stages` at runtime) so `pipeline.stages`
//   stays a list of the real Python stages -- the isolation-slots /
//   phased-integration / instrumentation tests iterate and re-wrap
//   `.stages`; the ORDER is what is now Rust.
//
// What stays Python (the U-E boundary, argued in the shim headers and
// VERIFICATION.md):
// - the config/design_rules parameter EXTRACTION (the `getattr(config, ...)`
//   chains assembling plain dicts/lists, the `max(...) + 0.3` margin, the
//   `DesignRules`/`NetClassRules` conversion and the `PadInfo` anonymous-
//   class pad conversion -- Python-object marshalling into stage
//   constructor kwargs, not ordering or sequencing);
// - `load_channel_map_from_sidecar` (file I/O, WARNING logging, the
//   `ChannelMap` parse + the `cell_size_um` hard error);
// - `_board_state_to_drc_input` / `_issue_fingerprint` (the fence's
//   call-backs -- `DRCFence.check` itself stays Python per the
//   validation-slice differential);
// - the `SidecarAwarePipeline` wrapper + `record_sidecar_load` counter;
// - the legacy pipeline factory (`create_legacy_pipeline`) and the
//   `DeterministicPipeline` class shell (`.stages` / `.fence` attributes).
//
// The loop's nondeterminism is preserved by design: `stage_wall_time_ms` is
// wall-clock (std::time::Instant, same semantics as `time.time()` deltas)
// and the per-stage compute (CPython `random` seeds, subprocesses inside
// stages) is untouched -- the loop only sequences.
//
// Panic safety (R1g): every shim `run()` body runs under
// `std::panic::catch_unwind` (a panic becomes `StageError { kind: Fatal }`,
// the plan's error model); the pyclass methods are additionally wrapped in
// catch_unwind by pyo3's `#[pymethod]`/`#[pyfunction]` expansion (the crate
// sets `profile.release.panic = "unwind"`). No `unwrap`/`expect` anywhere
// (crate clippy lint).

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::sync::{Arc, Mutex};

#[cfg(feature = "python")]
use pyo3::exceptions::{PyRuntimeError, PyTypeError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d1_bridge;
#[cfg(feature = "python")]
use crate::derivation_stage::pyerr_stage;
#[cfg(feature = "python")]
use crate::pipeline::{PipelineConfig, PipelineRunner};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError, StageErrorKind};

/// The canonical D1->D7 stage order of `create_drc_aware_pipeline()` (the
/// 23 stages of the factory's ordered construction, in declaration order).
#[cfg(feature = "python")]
const DRC_AWARE_STAGE_KINDS: &[&str] = &[
    "config_attach",
    "net_class_setup",
    "zone_geometry",
    "zone_assignment",
    "hv_lv_partition",
    "slot_generation",        // zone_aware -> zone_aware_slot_generation
    "component_assignment",   // phased config -> phased_component_assignment
    "apply_placements",
    "courtyard_check",
    "apply_placements",
    "placement_validation",
    "drc_oracle_setup",
    "clearance_grid",
    "net_ordering",
    "layer_assignment",
    "power_plane",
    "fine_pitch_escape",
    "track_deduplication",
    "short_circuit_detection",
    "via_deduplication",
    "via_validation",
    "drc_validation",
    "connectivity_validation",
];

/// The canonical 23-stage order with the zone-aware and phased substitutions
/// applied (what `create_drc_aware_pipeline()` actually builds by default).
#[cfg(feature = "python")]
pub fn drc_aware_stage_order(zone_aware: bool, phased: bool) -> Vec<&'static str> {
    DRC_AWARE_STAGE_KINDS
        .iter()
        .map(|k| match *k {
            "slot_generation" => {
                if zone_aware { "zone_aware_slot_generation" } else { "slot_generation" }
            }
            "component_assignment" => {
                if phased { "phased_component_assignment" } else { "component_assignment" }
            }
            other => other,
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Run loop
// ---------------------------------------------------------------------------

/// Mutable loop state shared by every stage shim of one run.
///
/// The runner threads a Rust `BoardState`; the PYTHON `BoardState` object is
/// threaded through `current_py_state` so each shim calls the Python stage
/// with the exact object the previous stage returned (untouched fields keep
/// object identity). `previous_violations` and `pending_error` carry the
/// fence threading and the first stage exception across shims.
#[cfg(feature = "python")]
struct RunContext {
    current_py_state: Mutex<Py<PyAny>>,
    previous_violations: Mutex<Option<Py<PyAny>>>,
    fence: Option<Py<PyAny>>,
    pending_error: Mutex<Option<Py<PyAny>>>,
}

/// A `Stage<BoardState>` wrapper over one Python stage object.
///
/// `run()` marshals the threaded Python state to the stage's own `run`
/// method, threads the result back into the shared context, performs the
/// oracle's per-stage fence invocation (when a fence is set and the stage
/// carries invariants), and returns the Rust `BoardState` snapshot of the
/// post-stage Python state so the runner's state threading mirrors the
/// Python loop's.
#[cfg(feature = "python")]
struct PythonStageShim {
    stage: Py<PyAny>,
    name: String,
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl PythonStageShim {
    fn new(py: Python<'_>, stage: Py<PyAny>, ctx: Arc<RunContext>) -> Self {
        let name = stage
            .bind(py)
            .getattr("name")
            .and_then(|n| n.extract::<String>())
            .unwrap_or_else(|_| String::new());
        Self { stage, name, ctx }
    }

    fn run_inner(&self, py: Python<'_>, _state: BoardState) -> PyResult<BoardState> {
        let t0 = std::time::Instant::now();
        let py_state = self
            .ctx
            .current_py_state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))?
            .clone();

        // `state = stage.run(state)` -- the Python stage's own run (each
        // shim stage delegates its compute to a Rust pyfunction already).
        let result = self.stage.bind(py).call_method1("run", (py_state,))?;
        *self
            .ctx
            .current_py_state
            .lock()
            .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))? = result.clone().unbind();

        // The oracle's fence block: `if self.fence and stage.invariants:`.
        if let Some(fence) = &self.ctx.fence {
            let invariants = self.stage.bind(py).getattr("invariants")?;
            if invariants.is_truthy()? {
                let stage_time_ms = t0.elapsed().as_secs_f64() * 1000.0;
                let drc_input = py
                    .import("temper_placer.deterministic")?
                    .getattr("_board_state_to_drc_input")?;
                let drc_input_result = drc_input.call1((result.clone(),))?;
                let placement = drc_input_result.get_item(0)?;
                let constraints = drc_input_result.get_item(1)?;

                let kwargs = PyDict::new(py);
                kwargs.set_item("stage_name", self.stage.bind(py).getattr("name")?)?;
                kwargs.set_item("invariants", invariants)?;
                kwargs.set_item("placement", placement)?;
                kwargs.set_item("constraints", constraints)?;
                kwargs.set_item(
                    "modified_regions",
                    self.stage.bind(py).getattr("last_modified_regions")?,
                )?;
                let prev = self
                    .ctx
                    .previous_violations
                    .lock()
                    .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))?
                    .clone();
                kwargs.set_item("previous_violations", prev)?;
                kwargs.set_item("stage_wall_time_ms", stage_time_ms)?;

                let fence_result = fence.bind(py).call_method("check", (), Some(&kwargs))?;

                // `previous_violations = frozenset(_issue_fingerprint(v.issue)
                // for v in result.violations)`.
                let violations = fence_result.getattr("violations")?;
                let issue_fingerprint = py
                    .import("temper_placer.validation.drc_fence")?
                    .getattr("_issue_fingerprint")?;
                let mut fingerprints = Vec::new();
                for v in violations.try_iter()? {
                    let v = v?;
                    fingerprints.push(issue_fingerprint.call1((v.getattr("issue")?,))?.unbind());
                }
                let frozenset_cls = py.import("builtins")?.getattr("frozenset")?;
                let fs = frozenset_cls
                    .call1((PyList::new(py, fingerprints)?,))?
                    .into_any()
                    .unbind();
                *self
                    .ctx
                    .previous_violations
                    .lock()
                    .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))? = Some(fs);
            }
        }

        d1_bridge::from_python(py, &result)
    }
}

#[cfg(feature = "python")]
impl Stage<BoardState> for PythonStageShim {
    fn name(&self) -> Cow<'static, str> {
        Cow::Owned(self.name.clone())
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let name = self.name.clone();
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            Python::attach(|py| self.run_inner(py, state))
        })) {
            Ok(result) => result.map_err(|e| {
                // Preserve the ORIGINAL exception (as its value object) so
                // the run loop can re-raise it -- exception identity, not a
                // re-wrap.
                let value: Py<PyAny> = Python::attach(|py| e.value(py).clone().into_any().unbind());
                if let Ok(mut slot) = self.ctx.pending_error.lock()
                    && slot.is_none()
                {
                    *slot = Some(value);
                }
                pyerr_stage(&name, e)
            }),
            Err(_) => Err(StageError::new(
                name,
                "stage panicked",
                StageErrorKind::Fatal,
            )),
        }
    }
}

/// The sequencing loop core (see the module docstring for the boundary).
#[cfg(feature = "python")]
pub(crate) fn run_pipeline(
    py: Python<'_>,
    stages: Option<Py<PyAny>>,
    fence: Option<Py<PyAny>>,
    initial_state: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    // `state = initial_state or BoardState()`.
    let py_state: Py<PyAny> = match initial_state {
        Some(s) => s,
        None => {
            let cls = py.import("temper_placer.deterministic.state")?.getattr("BoardState")?;
            cls.call0()?.into_any().unbind()
        }
    };

    let stage_objs: Vec<Py<PyAny>> = match stages {
        Some(s) => s
            .bind(py)
            .try_iter()?
            .map(|item| item.map(|b| b.unbind()))
            .collect::<PyResult<_>>()?,
        None => Vec::new(),
    };

    // An empty stage list runs nothing: return the state unchanged (the
    // oracle's `DeterministicPipeline(stages=[]).run(state)` identity).
    if stage_objs.is_empty() {
        return Ok(py_state);
    }

    let ctx = Arc::new(RunContext {
        current_py_state: Mutex::new(py_state.clone()),
        previous_violations: Mutex::new(None),
        fence,
        pending_error: Mutex::new(None),
    });

    let mut runner = PipelineRunner::new(PipelineConfig::default());
    for s in stage_objs {
        runner.add_stage(Box::new(PythonStageShim::new(py, s, ctx.clone())));
    }

    let rust_state = d1_bridge::from_python(py, py_state.bind(py))?;
    let (_final, report) = runner.run(rust_state);

    if report.halted_early {
        let value = ctx
            .pending_error
            .lock()
            .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))?
            .take();
        if let Some(v) = value {
            return Err(PyErr::from_value(v.bind(py).clone()));
        }
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.clone())
            .collect();
        return Err(PyRuntimeError::new_err(format!(
            "pipeline halted without a stage exception (stages: {names:?})"
        )));
    }

    let final_py = ctx
        .current_py_state
        .lock()
        .map_err(|_| PyRuntimeError::new_err("pipeline run context poisoned"))?
        .clone();
    Ok(final_py)
}

// ---------------------------------------------------------------------------
// Factory (the ORDER)
// ---------------------------------------------------------------------------

/// `getattr(obj, name, None)` with Python's AttributeError-only fallback
/// (a present-but-None attribute still yields None, exactly like Python).
#[cfg(feature = "python")]
fn attr_or_none(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Py<PyAny>> {
    if obj.hasattr(name)? {
        obj.getattr(name).map(|v| v.unbind())
    } else {
        Ok(obj.py().None())
    }
}

/// The factory's `use_phased_placement` decision: `config is not None and
/// (placement_priority or component_spacing_rules or component_groups)`.
#[cfg(feature = "python")]
fn config_has_phased_rules(py: Python<'_>, config: Option<&Bound<'_, PyAny>>) -> PyResult<bool> {
    let Some(config) = config else {
        return Ok(false);
    };
    for name in ["placement_priority", "component_spacing_rules", "component_groups"] {
        let v = attr_or_none(config, name)?;
        if v.bind(py).is_truthy()? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// The factory's `use_isolation_slots` decision:
/// `bool((getattr(config, "placer", None) or {}).get("use_isolation_slots", False))`.
#[cfg(feature = "python")]
fn config_use_isolation_slots(py: Python<'_>, config: Option<&Bound<'_, PyAny>>) -> PyResult<bool> {
    let Some(config) = config else {
        return Ok(false);
    };
    let placer = attr_or_none(config, "placer")?;
    let placer_cfg = if placer.bind(py).is_truthy()? {
        placer.bind(py).clone()
    } else {
        // `placer or {}` -- falsy (None / empty dict) falls back to {}.
        PyDict::new(py).into_any()
    };
    let value = placer_cfg.get_item("use_isolation_slots")?;
    value.is_truthy()
}

/// The factory core: construct the ordered D1->D7 PYTHON stage objects and
/// return them as a list. See the module docstring for the parameter split
/// (the config extraction happens Python-side; the ORDER + the selections +
/// the construction are here).
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
pub(crate) fn build_drc_aware_python_stages(
    py: Python<'_>,
    metadata: Option<Py<PyAny>>,
    config: Option<Py<PyAny>>,
    zone_aware: bool,
    parsed_pads: Option<Py<PyAny>>,
    channel_map: Option<Py<PyAny>>,
    zone_config: Option<Py<PyAny>>,
    slot_spacing: f64,
    max_clearance: f64,
    net_class_clearances: Option<Py<PyAny>>,
    net_priority: Option<Py<PyAny>>,
    placement_constraints: Option<Py<PyAny>>,
    hv_exclusion_zones: Option<Py<PyAny>>,
    net_classes: Option<Py<PyAny>>,
    pad_sizes_for_stage: Option<Py<PyAny>>,
    fixed_placements: Option<Py<PyAny>>,
    yaml_copper_zones: Option<Py<PyAny>>,
    yaml_isolation_slots: Option<Py<PyAny>>,
    config_rules: Option<Py<PyAny>>,
    resolved_design_rules: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let Some(metadata) = metadata else {
        return Err(PyTypeError::new_err(
            "create_drc_aware_pipeline() requires 'metadata' parameter (KiCadMetadata)",
        ));
    };
    let metadata = metadata.bind(py);
    let stages_mod = py.import("temper_placer.deterministic.stages")?;

    // -- slot stage selection (zone_aware -> zone-aware or standard) --
    let slot_stage: Py<PyAny> = if zone_aware {
        let kwargs = PyDict::new(py);
        kwargs.set_item("slot_spacing_mm", slot_spacing)?;
        kwargs.set_item("copper_zone_margin", 2.0_f64)?;
        kwargs.set_item("min_routing_channel", 3.0_f64)?;
        kwargs.set_item("yaml_copper_zones", yaml_copper_zones)?;
        kwargs.set_item("yaml_isolation_slots", yaml_isolation_slots)?;
        kwargs.set_item("net_class_rules", config_rules)?;
        stages_mod
            .getattr("ZoneAwareSlotGenerationStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind()
    } else {
        stages_mod
            .getattr("SlotGenerationStage")?
            .call1((slot_spacing,))?
            .into_any()
            .unbind()
    };

    // -- component stage selection (phased config -> phased or standard) --
    let use_phased = config_has_phased_rules(py, config.as_ref().map(|c| c.bind(py)))?;
    let component_stage: Py<PyAny> = if use_phased {
        let kwargs = PyDict::new(py);
        kwargs.set_item("constraints", config.clone())?;
        kwargs.set_item("slot_spacing", slot_spacing)?;
        kwargs.set_item("fixed_placements", fixed_placements.clone())?;
        kwargs.set_item("design_rules", resolved_design_rules.clone())?;
        kwargs.set_item(
            "use_isolation_slots",
            config_use_isolation_slots(py, config.as_ref().map(|c| c.bind(py)))?,
        )?;
        stages_mod
            .getattr("PhasedComponentAssignmentStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind()
    } else {
        let kwargs = PyDict::new(py);
        kwargs.set_item("slot_spacing", slot_spacing)?;
        kwargs.set_item("fixed_placements", fixed_placements.clone())?;
        stages_mod
            .getattr("ComponentAssignmentStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind()
    };

    // -- R4c sidecar injection: `if channel_map is not None and
    // channel_map.has_grid() and isinstance(component_stage,
    // PhasedComponentAssignmentStage): component_stage.channel_map = ...` --
    if let Some(cmap) = &channel_map {
        let has_grid = cmap.bind(py).call_method0("has_grid")?;
        if has_grid.is_truthy()? {
            let phased_mod =
                py.import("temper_placer.deterministic.stages.phased_component_assignment")?;
            let phased_cls = phased_mod.getattr("PhasedComponentAssignmentStage")?;
            if component_stage.bind(py).is_instance(&phased_cls)? {
                component_stage.bind(py).setattr("channel_map", cmap)?;
            }
        }
    }

    // -- the ordered construction (23 stages, D1 -> D7) --
    let mut stages: Vec<Py<PyAny>> = Vec::new();

    // D1 setup: config attach + net class mapping early.
    stages.push(
        stages_mod
            .getattr("ConfigAttachStage")?
            .call1((config.clone(),))?
            .into_any()
            .unbind(),
    );
    let kwargs = PyDict::new(py);
    kwargs.set_item("net_classes", net_classes.clone())?;
    stages.push(
        stages_mod
            .getattr("NetClassSetupStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );

    // D2 zones.
    let kwargs = PyDict::new(py);
    kwargs.set_item("zone_config", zone_config)?;
    stages.push(
        stages_mod
            .getattr("ZoneGeometryStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("ZoneAssignmentStage")?
            .call0()?
            .into_any()
            .unbind(),
    );

    // HV/LV domain map MUST run before component assignment (guard-strip).
    stages.push(
        stages_mod
            .getattr("HvLvPartitionStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    stages.push(slot_stage);
    stages.push(component_stage);

    // Placement stages.
    stages.push(
        stages_mod
            .getattr("ApplyPlacementsStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    let kwargs = PyDict::new(py);
    kwargs.set_item("courtyards", metadata.getattr("courtyards")?)?;
    kwargs.set_item("board_width", metadata.getattr("board_width")?)?;
    kwargs.set_item("board_height", metadata.getattr("board_height")?)?;
    kwargs.set_item("margin", 5.0_f64)?;
    stages.push(
        stages_mod
            .getattr("CourtyardCheckStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );
    // Re-apply placements after clamping (DRC-FIX-5).
    stages.push(
        stages_mod
            .getattr("ApplyPlacementsStage")?
            .call0()?
            .into_any()
            .unbind(),
    );

    // EXP-12 placement validation before routing.
    let kwargs = PyDict::new(py);
    kwargs.set_item("constraints", placement_constraints)?;
    kwargs.set_item("fail_on_hard_violations", false)?;
    kwargs.set_item("parsed_pads", parsed_pads.clone())?;
    stages.push(
        stages_mod
            .getattr("PlacementValidationStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );

    // DRC setup -- `design_rules=config if config else design_rules`.
    let oracle_design_rules: Py<PyAny> = match &config {
        Some(c) if c.bind(py).is_truthy()? => c.clone(),
        _ => match &resolved_design_rules {
            Some(r) => r.clone(),
            None => py.None(),
        },
    };
    let kwargs = PyDict::new(py);
    kwargs.set_item("design_rules", oracle_design_rules)?;
    kwargs.set_item("parsed_pads", parsed_pads)?;
    stages.push(
        stages_mod
            .getattr("DRCOracleSetupStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );

    // Routing.
    let kwargs = PyDict::new(py);
    kwargs.set_item("cell_size_mm", 0.25_f64)?;
    kwargs.set_item("layer_count", 4_i64)?;
    kwargs.set_item("max_clearance_mm", max_clearance)?;
    kwargs.set_item("net_class_clearances", net_class_clearances)?;
    kwargs.set_item("net_classes", net_classes.clone())?;
    kwargs.set_item("pad_sizes", pad_sizes_for_stage)?;
    kwargs.set_item("hv_exclusion_zones", hv_exclusion_zones)?;
    stages.push(
        stages_mod
            .getattr("ClearanceGridStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );
    let kwargs = PyDict::new(py);
    kwargs.set_item("net_priority", net_priority)?;
    stages.push(
        stages_mod
            .getattr("NetOrderingStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );
    let kwargs = PyDict::new(py);
    kwargs.set_item("net_classes", net_classes)?;
    stages.push(
        stages_mod
            .getattr("LayerAssignmentStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("PowerPlaneStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    let kwargs = PyDict::new(py);
    kwargs.set_item("pin_pitch_threshold_mm", 0.65_f64)?;
    kwargs.set_item("escape_layer", 1_i64)?;
    stages.push(
        stages_mod
            .getattr("FinePitchEscapeStage")?
            .call((), Some(&kwargs))?
            .into_any()
            .unbind(),
    );

    // Post-routing cleanup (order matters).
    stages.push(
        stages_mod
            .getattr("TrackDeduplicationStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("ShortCircuitDetectionStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("ViaDeduplicationStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("ViaValidationStage")?
            .call0()?
            .into_any()
            .unbind(),
    );

    // Validation.
    stages.push(
        stages_mod
            .getattr("DRCValidationStage")?
            .call0()?
            .into_any()
            .unbind(),
    );
    stages.push(
        stages_mod
            .getattr("ConnectivityValidationStage")?
            .call0()?
            .into_any()
            .unbind(),
    );

    debug_assert_eq!(stages.len(), DRC_AWARE_STAGE_KINDS.len());
    Ok(PyList::new(py, stages)?.into_any().unbind())
}

// ---------------------------------------------------------------------------
// The pyclass surface
// ---------------------------------------------------------------------------

/// The Rust host of `DeterministicPipeline.run()` and the
/// `create_drc_aware_pipeline()` stage factory (see the module docstring).
#[cfg(feature = "python")]
#[pyclass(module = "temper_orchestration")]
pub struct DeterministicPipeline;

#[cfg(feature = "python")]
#[pymethods]
impl DeterministicPipeline {
    #[new]
    fn new() -> Self {
        Self
    }

    /// Sequence the given Python stage objects through the Rust
    /// `PipelineRunner<BoardState>`, threading the Python `BoardState`
    /// (object identity preserved for untouched fields). `stages=None` runs
    /// nothing (returns the state unchanged, the oracle's empty-list
    /// semantics). A raising stage halts the run and re-raises the ORIGINAL
    /// exception.
    #[pyo3(signature = (stages=None, fence=None, initial_state=None))]
    fn run(
        &self,
        py: Python<'_>,
        stages: Option<Py<PyAny>>,
        fence: Option<Py<PyAny>>,
        initial_state: Option<Py<PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        run_pipeline(py, stages, fence, initial_state)
    }

    /// The `create_drc_aware_pipeline()` stage factory: build the ordered
    /// D1->D7 Python stage objects and return them as a list.
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        metadata=None,
        config=None,
        zone_aware=true,
        parsed_pads=None,
        channel_map=None,
        zone_config=None,
        slot_spacing=10.0,
        max_clearance=2.5,
        net_class_clearances=None,
        net_priority=None,
        placement_constraints=None,
        hv_exclusion_zones=None,
        net_classes=None,
        pad_sizes_for_stage=None,
        fixed_placements=None,
        yaml_copper_zones=None,
        yaml_isolation_slots=None,
        config_rules=None,
        resolved_design_rules=None,
    ))]
    #[staticmethod]
    fn create_drc_aware_pipeline_stages(
        py: Python<'_>,
        metadata: Option<Py<PyAny>>,
        config: Option<Py<PyAny>>,
        zone_aware: bool,
        parsed_pads: Option<Py<PyAny>>,
        channel_map: Option<Py<PyAny>>,
        zone_config: Option<Py<PyAny>>,
        slot_spacing: f64,
        max_clearance: f64,
        net_class_clearances: Option<Py<PyAny>>,
        net_priority: Option<Py<PyAny>>,
        placement_constraints: Option<Py<PyAny>>,
        hv_exclusion_zones: Option<Py<PyAny>>,
        net_classes: Option<Py<PyAny>>,
        pad_sizes_for_stage: Option<Py<PyAny>>,
        fixed_placements: Option<Py<PyAny>>,
        yaml_copper_zones: Option<Py<PyAny>>,
        yaml_isolation_slots: Option<Py<PyAny>>,
        config_rules: Option<Py<PyAny>>,
        resolved_design_rules: Option<Py<PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        build_drc_aware_python_stages(
            py,
            metadata,
            config,
            zone_aware,
            parsed_pads,
            channel_map,
            zone_config,
            slot_spacing,
            max_clearance,
            net_class_clearances,
            net_priority,
            placement_constraints,
            hv_exclusion_zones,
            net_classes,
            pad_sizes_for_stage,
            fixed_placements,
            yaml_copper_zones,
            yaml_isolation_slots,
            config_rules,
            resolved_design_rules,
        )
    }
}

// Orchestration-port unit U-G (Rust Orchestration Engine plan 2026-08-09-001):
// the `RouterPipeline` pyclass hosting the run-loop of
// `temper_placer/router_v6/_pipeline_core.py`.
//
// Migrated surface (the Python module keeps its public API and delegates):
//
// - the run() DRIVER of `RouterV6Pipeline.run()`: the fixed stage sequence —
//   Stage 0 load, Stage 0.5 legalization, Stage 1 escape vias, Stage 2
//   channel analysis, Stage 3 topological routing, Stage 4 geometric
//   realization, Stage 5 manufacturing DRC, result assembly — driven through
//   the Rust `PipelineRunner<BoardState>` as one shim per step. The shared
//   `RunContext` threads the Python objects (pcb, escape_vias, stage2,
//   stage3, stage4, manufacturing_report) so untouched objects keep OBJECT
//   IDENTITY (the oracle never copies what no stage replaced). The
//   conditionals are Rust (legalization on/off, manufacturing DRC on/off,
//   the dfm_fail_on raise decision, fence presence, ERC on/off), as are the
//   verbose print orchestration (through CPython `print`/`str.format`, so
//   the text stays bit-identical), the wall-clock runtime (std::time::Instant
//   — same semantics as `time.time()` deltas), the exception propagation
//   (a stage raising halts the runner and the ORIGINAL exception is
//   re-raised) and the result assembly (`RouterV6Result` construction,
//   `batch_results=list(self.last_batch_results)`, the final ledger
//   checkout).
//
// What stays Python (the U-G boundary, argued in the shim headers and
// VERIFICATION.md):
// - the leaf compute call-backs, invoked by the driver in oracle order:
//   `parse_kicad_pcb_v6` (through the module attribute seam, so the
//   plane-condemnation monkeypatch test keeps working), the Stage-0 setup
//   marshalling (`_run_stage0_setup`: pcb_override swap, netclass/assignment
//   injection, the CPython `list.sort` with the `_net_sort_key` callable —
//   Python-object marshalling, the U-E "parameter EXTRACTION" category),
//   the Legalizer methods, `identify_dense_packages` /
//   `generate_escape_vias`, `pcb.validate_placement`, `_run_stage2`,
//   `_compute_resource_bound`, `_run_stage3` (the ortools / CP-SAT solve),
//   `_run_stage4` (the A* geometric realization), `_run_stage5`,
//   `_run_manufacturing_drc` (the DFM checks), `_run_fence`, the
//   `StageLedger` orchestration (checkin/checkout — the ledger shim's own
//   boundary), the `ErcGate` gate and the `RouterV6Result` dataclass
//   construction.
// - the R7 skip_stage3 DECISION and the "SKIPPED" verbose print stay in the
//   shim's run(): test_wave3_skip_sat.py inspects the run() source text
//   (`if self.skip_stage3:` + "SKIPPED"), so the branch must execute there;
//   the driver consumes the resolved empty `Stage3Output` (or None to run
//   stage 3 normally). The skip-path print therefore lands before the
//   delegation — a documented positional divergence (the differential
//   compares verbose stdout on the non-skip path, where the driver prints
//   "Stage 3: Topological routing..." at the oracle position).
//
// The router's nondeterminism (wall-clock, seeds, the route_board.py
// subprocess) is preserved by design: the driver only sequences; the actual
// routing compute (subprocess + ortools + A*) stays Python.
//
// Panic safety (R1g): every shim `run()` body runs under `catch_unwind` (a
// panic becomes `StageError { kind: Fatal }`, the plan's error model); the
// pyclass methods are additionally wrapped in catch_unwind by pyo3's
// `#[pymethod]`/`#[pyfunction]` expansion (the crate sets
// `profile.release.panic = "unwind"`). No `unwrap`/`expect` anywhere
// (crate clippy lint).

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::sync::{Arc, Mutex};

#[cfg(feature = "python")]
use pyo3::exceptions::{PyRuntimeError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyString};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::pyerr_stage;
#[cfg(feature = "python")]
use crate::pipeline::{PipelineConfig, PipelineRunner};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError, StageErrorKind};

/// The pure dfm_fail_on raise decision (the oracle's `should_fail` block):
/// "critical" raises iff critical_violations > 0, "all" raises iff
/// total_violations > 0, "none" never raises. Deliberately NOT python-gated
/// so the wasm tier can pin it.
fn dfm_should_fail(fail_on: &str, critical: i64, total: i64) -> bool {
    match fail_on {
        "none" => false,
        "critical" => critical > 0,
        _ => total > 0,
    }
}

/// The oracle's summary completion expression:
/// `100 * success_count / max(1, success_count + failure_count)` as a float
/// (CPython true division of the exact int product by the exact int max).
/// The counts are small ints, so `100.0 * success as f64 / denom as f64` is
/// bit-identical. The `:.1f` rendering goes through CPython `str.format`.
fn completion_pct(success: i64, failure: i64) -> f64 {
    100.0 * (success as f64) / ((success + failure).max(1) as f64)
}

#[cfg(feature = "python")]
fn poison() -> PyErr {
    PyRuntimeError::new_err("router run context poisoned")
}

// ---------------------------------------------------------------------------
// Run loop
// ---------------------------------------------------------------------------

/// Mutable loop state shared by every stage shim of one run.
///
/// The runner threads a Rust `BoardState` (an all-None carrier: the router
/// loop's state is the tuple of Python objects threaded through this
/// context, exactly like the oracle's local variables). `pending_error`
/// carries the first stage exception across shims so the driver can
/// re-raise the ORIGINAL exception.
#[cfg(feature = "python")]
struct RunContext {
    pipeline: Py<PyAny>,
    pcb_path: Py<PyAny>,
    pcb_override: Option<Py<PyAny>>,
    net_class_assignments: Option<Py<PyAny>>,
    net_classes: Option<Py<PyAny>>,
    stage3_override: Option<Py<PyAny>>,
    started: std::time::Instant,
    pending_error: Mutex<Option<Py<PyAny>>>,
    pcb: Mutex<Option<Py<PyAny>>>,
    escape_vias: Mutex<Option<Py<PyAny>>>,
    stage2: Mutex<Option<Py<PyAny>>>,
    stage3: Mutex<Option<Py<PyAny>>>,
    stage4: Mutex<Option<Py<PyAny>>>,
    manufacturing_report: Mutex<Option<Py<PyAny>>>,
    result: Mutex<Option<Py<PyAny>>>,
}

#[cfg(feature = "python")]
impl RunContext {
    fn verbose(&self, py: Python<'_>) -> PyResult<bool> {
        self.pipeline.bind(py).getattr("verbose")?.is_truthy()
    }

    fn flag(&self, py: Python<'_>, name: &str) -> PyResult<bool> {
        self.pipeline.bind(py).getattr(name)?.is_truthy()
    }

    fn get(&self, _py: Python<'_>, slot: &Mutex<Option<Py<PyAny>>>) -> PyResult<Py<PyAny>> {
        slot.lock()
            .map_err(|_| poison())?
            .clone()
            .ok_or_else(|| PyRuntimeError::new_err("router run state missing"))
    }

    fn set(&self, slot: &Mutex<Option<Py<PyAny>>>, value: Py<PyAny>) -> PyResult<()> {
        let mut guard = slot.lock().map_err(|_| poison())?;
        *guard = Some(value);
        Ok(())
    }

    /// `if self.fence: self._run_fence(stage_name=..., invariants=...,
    /// pcb=..., [escape_vias=...|routing_results=...])` — the fence
    /// call-back (DRCFence orchestration stays Python; the driver owns the
    /// invocation point). The invariants come from the module-level
    /// `_stage_*_invariants()` functions, called at runtime so the
    /// monkeypatch seams stay visible.
    fn run_fence(
        &self,
        py: Python<'_>,
        stage_name: &str,
        invariants_fn: &str,
        pcb: &Bound<'_, PyAny>,
        escape_vias: Option<&Bound<'_, PyAny>>,
        routing_results: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<()> {
        let verify = py.import("temper_placer.router_v6._pipeline_verify")?;
        let invariants = verify.getattr(invariants_fn)?.call0()?;
        let kwargs = PyDict::new(py);
        kwargs.set_item("stage_name", stage_name)?;
        kwargs.set_item("invariants", invariants)?;
        kwargs.set_item("pcb", pcb)?;
        if let Some(ev) = escape_vias {
            kwargs.set_item("escape_vias", ev)?;
        }
        if let Some(rr) = routing_results {
            kwargs.set_item("routing_results", rr)?;
        }
        self.pipeline
            .bind(py)
            .call_method("_run_fence", (), Some(&kwargs))?;
        Ok(())
    }
}

#[cfg(feature = "python")]
fn opt_or_none<'py>(py: Python<'py>, opt: &Option<Py<PyAny>>) -> Bound<'py, PyAny> {
    match opt {
        Some(v) => v.bind(py).clone(),
        None => py.None().into_bound(py),
    }
}

/// The shared stage-body guard: a PyErr stores the ORIGINAL exception value
/// in the context (so the driver re-raises it — exception identity, not a
/// re-wrap) and becomes a Fatal `StageError`; a panic becomes a Fatal
/// `StageError` without touching the interpreter.
#[cfg(feature = "python")]
fn run_guarded(
    stage_name: &'static str,
    ctx: &RunContext,
    f: impl FnOnce(Python<'_>) -> PyResult<BoardState>,
) -> Result<BoardState, StageError> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| Python::attach(f))) {
        Ok(result) => result.map_err(|e| {
            let value: Py<PyAny> = Python::attach(|py| e.value(py).clone().into_any().unbind());
            if let Ok(mut slot) = ctx.pending_error.lock()
                && slot.is_none()
            {
                *slot = Some(value);
            }
            pyerr_stage(stage_name, e)
        }),
        Err(_) => Err(StageError::new(
            stage_name,
            "stage panicked",
            StageErrorKind::Fatal,
        )),
    }
}

#[cfg(feature = "python")]
fn stage_run(
    stage_name: &'static str,
    ctx: &RunContext,
    f: impl FnOnce(Python<'_>) -> PyResult<BoardState>,
) -> Result<BoardState, StageError> {
    run_guarded(stage_name, ctx, f)
}

// ---------------------------------------------------------------------------
// Stage shims (one per run()-step; the runner sequences them)
// ---------------------------------------------------------------------------

/// Stage 0 — load: parse via the module seam (`use_declared_layer_roles=True`,
/// the R8 plane-condemnation wiring), then the Stage-0 setup marshalling
/// call-back (override swap, netclass injection, net sort).
#[cfg(feature = "python")]
struct RouterStageLoad {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageLoad {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.load")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.load", &ctx, |py| {
            if ctx.verbose(py)? {
                d6_util::py_print(
                    py,
                    &[PyString::new(py, "Stage 0: Loading PCB...").into_any()],
                )?;
            }
            let parser = py.import("temper_placer.io.kicad_parser")?;
            let parse_fn = parser.getattr("parse_kicad_pcb_v6")?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("use_declared_layer_roles", true)?;
            let pcb = parse_fn.call((ctx.pcb_path.bind(py),), Some(&kwargs))?;
            let core = py.import("temper_placer.router_v6._pipeline_core")?;
            let setup = core.getattr("_run_stage0_setup")?;
            let pcb = setup.call1((
                pcb,
                opt_or_none(py, &ctx.pcb_override),
                opt_or_none(py, &ctx.net_class_assignments),
                opt_or_none(py, &ctx.net_classes),
            ))?;
            ctx.set(&ctx.pcb, pcb.into_any().unbind())?;
            Ok(state)
        })
    }
}

/// Stage 0.5 — legalization (added only when `enable_legalization` is set):
/// the Legalizer construction, the advisory collision audit and the
/// legalize() call, with the oracle's verbose prints.
#[cfg(feature = "python")]
struct RouterStageLegalize {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageLegalize {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.legalize")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.legalize", &ctx, |py| {
            if ctx.verbose(py)? {
                d6_util::py_print(
                    py,
                    &[
                        PyString::new(py, "Stage 0.5: Checking and Legalizing Placement...")
                            .into_any(),
                    ],
                )?;
            }
            let pcb = ctx.get(py, &ctx.pcb)?;
            let legalizer_mod = py.import("temper_placer.router_v6.placement_legalization")?;
            let legalizer = legalizer_mod.getattr("Legalizer")?.call1((pcb,))?;
            if ctx.verbose(py)? {
                let collisions = legalizer
                    .getattr("auditor")?
                    .call_method0("check_collisions")?;
                let n: usize = collisions.len()?;
                let msg = d6_util::py_format(
                    py,
                    "  Found {} initial collisions",
                    &[n.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
            let legalized = legalizer.call_method0("legalize")?;
            if legalized.is_truthy()? {
                if ctx.verbose(py)? {
                    d6_util::py_print(
                        py,
                        &[
                            PyString::new(py, "  Placement collision check passed (0 overlaps)")
                                .into_any(),
                        ],
                    )?;
                }
            } else {
                let collisions = legalizer
                    .getattr("auditor")?
                    .call_method0("check_collisions")?;
                if ctx.verbose(py)? {
                    let joined = advisory_overlaps(py, &collisions)?;
                    let msg =
                        d6_util::py_format(py, "  Advisory pin-hull overlaps: {}", &[joined])?;
                    d6_util::py_print(py, &[msg])?;
                }
            }
            Ok(state)
        })
    }
}

/// `", ".join(f"{c.ref1}/{c.ref2}" for c in collisions[:8])` — rendered
/// through CPython `str.format` and `str.join` (the tuple-f-string reprs
/// stay CPython).
#[cfg(feature = "python")]
fn advisory_overlaps<'a>(
    py: Python<'a>,
    collisions: &Bound<'_, PyAny>,
) -> PyResult<Bound<'a, PyAny>> {
    let items = PyList::empty(py);
    let n: usize = collisions.len()?;
    for i in 0..n.min(8) {
        let c = collisions.get_item(i)?;
        let item = d6_util::py_format(py, "{}/{}", &[c.getattr("ref1")?, c.getattr("ref2")?])?;
        items.append(item)?;
    }
    PyString::new(py, ", ").call_method1("join", (items,))
}

/// Post-legalization validation: `pcb.validate_placement()` with the
/// ValueError raise decision, the Stage-0.5 fence and the ledger checkin.
#[cfg(feature = "python")]
struct RouterStageValidate {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageValidate {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.validate")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.validate", &ctx, |py| {
            let pcb = ctx.get(py, &ctx.pcb)?;
            let errors = pcb.bind(py).call_method0("validate_placement")?;
            if errors.len()? > 0 {
                let msg = d6_util::py_format(py, "PCB validation failed: {}", &[errors])?;
                let msg_text: String = msg.extract()?;
                return Err(PyValueError::new_err(msg_text));
            }
            if ctx.flag(py, "fence")? {
                ctx.run_fence(
                    py,
                    "router_v6.legalization",
                    "_stage_0_5_invariants",
                    pcb.bind(py),
                    None,
                    None,
                )?;
            }
            ctx.pipeline
                .bind(py)
                .getattr("ledger")?
                .call_method1("checkin", (pcb,))?;
            Ok(state)
        })
    }
}

/// Stage 1 — escape vias: the dense-package detection + per-package
/// dog-bone → via-in-pad fallback loop (the sequencing is Rust; the two
/// generators are call-backs), the fence gate and the ledger checkout.
#[cfg(feature = "python")]
struct RouterStageEscapeVias {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageEscapeVias {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.escape_vias")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.escape_vias", &ctx, |py| {
            let pcb = ctx.get(py, &ctx.pcb)?;
            if ctx.verbose(py)? {
                let n: usize = pcb.bind(py).getattr("components")?.len()?;
                let msg = d6_util::py_format(
                    py,
                    "Stage 1: Detecting dense packages in {} components...",
                    &[n.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
            let dense_mod = py.import("temper_placer.router_v6.dense_package_detection")?;
            let dense = dense_mod
                .getattr("identify_dense_packages")?
                .call1((pcb.bind(py).getattr("components")?,))?;
            if ctx.verbose(py)? {
                let n: usize = dense.len()?;
                let msg = d6_util::py_format(
                    py,
                    "  Found {} dense packages",
                    &[n.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
            let escape_vias = PyList::empty(py);
            let design_rules = pcb.bind(py).getattr("design_rules")?;
            let escape_mod = py.import("temper_placer.router_v6.escape_via_generator")?;
            let generate = escape_mod.getattr("generate_escape_vias")?;
            for item in dense.try_iter()? {
                let pkg = item?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("strategy", "dog-bone")?;
                let vias = generate.call((&pkg, &design_rules), Some(&kwargs))?;
                if !vias.is_truthy()? {
                    if ctx.verbose(py)? {
                        let ref_name = pkg.getattr("component")?.getattr("ref")?;
                        let msg = d6_util::py_format(
                            py,
                            "    Falling back to via-in-pad for {}",
                            &[ref_name],
                        )?;
                        d6_util::py_print(py, &[msg])?;
                    }
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("strategy", "via-in-pad")?;
                    let vias = generate.call((pkg, &design_rules), Some(&kwargs))?;
                    escape_vias.call_method1("extend", (vias,))?;
                } else {
                    escape_vias.call_method1("extend", (vias,))?;
                }
            }
            if ctx.verbose(py)? {
                let n: usize = escape_vias.len();
                let msg = d6_util::py_format(
                    py,
                    "  Generated {} escape vias",
                    &[n.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
            if ctx.flag(py, "fence")? && escape_vias.is_truthy()? {
                ctx.run_fence(
                    py,
                    "router_v6.escape_vias",
                    "_stage_1_invariants",
                    pcb.bind(py),
                    Some(&escape_vias),
                    None,
                )?;
            }
            ctx.pipeline
                .bind(py)
                .getattr("ledger")?
                .call_method1("checkout", ("escape_vias", pcb))?;
            ctx.set(&ctx.escape_vias, escape_vias.into_any().unbind())?;
            Ok(state)
        })
    }
}

/// Stage 2 — channel analysis: `_run_stage2` + the resource exhaustion
/// bound call-backs.
#[cfg(feature = "python")]
struct RouterStageChannel {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageChannel {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.channel")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.channel", &ctx, |py| {
            if ctx.verbose(py)? {
                d6_util::py_print(
                    py,
                    &[PyString::new(py, "Stage 2: Channel analysis...").into_any()],
                )?;
            }
            let pcb = ctx.get(py, &ctx.pcb)?;
            let escape_vias = ctx.get(py, &ctx.escape_vias)?;
            let stage2 = ctx
                .pipeline
                .bind(py)
                .call_method1("_run_stage2", (pcb.clone(), escape_vias))?;
            ctx.pipeline
                .bind(py)
                .call_method1("_compute_resource_bound", (pcb, &stage2))?;
            ctx.set(&ctx.stage2, stage2.unbind())?;
            Ok(state)
        })
    }
}

/// Stage 3 — topological routing: the driver consumes the shim-resolved R7
/// `stage3_override` (skip path) or invokes the `_run_stage3` SAT call-back
/// with the oracle-position verbose print.
#[cfg(feature = "python")]
struct RouterStageTopology {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageTopology {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.topology")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.topology", &ctx, |py| {
            let stage3: Py<PyAny> = match &ctx.stage3_override {
                Some(stage3) => stage3.clone(),
                None => {
                    if ctx.verbose(py)? {
                        d6_util::py_print(
                            py,
                            &[PyString::new(py, "Stage 3: Topological routing...").into_any()],
                        )?;
                    }
                    let pcb = ctx.get(py, &ctx.pcb)?;
                    let stage2 = ctx.get(py, &ctx.stage2)?;
                    ctx.pipeline
                        .bind(py)
                        .call_method1("_run_stage3", (pcb, stage2))?
                        .unbind()
                }
            };
            ctx.set(&ctx.stage3, stage3)?;
            Ok(state)
        })
    }
}

/// Stage 4 — geometric realization: the `_run_stage4` call-back.
#[cfg(feature = "python")]
struct RouterStageGeometric {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageGeometric {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.geometric")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.geometric", &ctx, |py| {
            if ctx.verbose(py)? {
                d6_util::py_print(
                    py,
                    &[PyString::new(py, "Stage 4: Geometric realization...").into_any()],
                )?;
            }
            let pcb = ctx.get(py, &ctx.pcb)?;
            let stage2 = ctx.get(py, &ctx.stage2)?;
            let stage3 = ctx.get(py, &ctx.stage3)?;
            let escape_vias = ctx.get(py, &ctx.escape_vias)?;
            let stage4 = ctx
                .pipeline
                .bind(py)
                .call_method1("_run_stage4", (pcb, stage2, stage3, escape_vias))?;
            ctx.set(&ctx.stage4, stage4.unbind())?;
            Ok(state)
        })
    }
}

/// Stage 5 — manufacturing DRC (added only when `enable_manufacturing_drc`
/// is set): the DFM report call-back + the dfm_fail_on raise decision.
#[cfg(feature = "python")]
struct RouterStageManufacturing {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageManufacturing {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.manufacturing_drc")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.manufacturing_drc", &ctx, |py| {
            let pcb = ctx.get(py, &ctx.pcb)?;
            let stage4 = ctx.get(py, &ctx.stage4)?;
            let routing_results = stage4.bind(py).getattr("routing_results")?;
            let report = ctx
                .pipeline
                .bind(py)
                .call_method1("_run_manufacturing_drc", (pcb, routing_results))?;
            let fail_on: String = ctx.pipeline.bind(py).getattr("dfm_fail_on")?.extract()?;
            if fail_on != "none" {
                let critical: i64 = report.getattr("critical_violations")?.extract()?;
                let total: i64 = report.getattr("total_violations")?.extract()?;
                if dfm_should_fail(&fail_on, critical, total) {
                    let msg = d6_util::py_format(
                        py,
                        "Manufacturing DRC: {} violations ({} critical). Fail mode: {}.",
                        &[
                            total.into_pyobject(py)?.into_any(),
                            critical.into_pyobject(py)?.into_any(),
                            fail_on.into_pyobject(py)?.into_any(),
                        ],
                    )?;
                    let cls = py
                        .import("temper_placer.router_v6._pipeline_types")?
                        .getattr("ManufacturingDRCViolationError")?;
                    let exc = cls.call1((msg,))?;
                    return Err(PyErr::from_value(exc.into_any()));
                }
            }
            ctx.set(&ctx.manufacturing_report, report.unbind())?;
            Ok(state)
        })
    }
}

/// Stage-4 fence (added only when a fence is set): the geometric fence gate
/// on `stage4.routing_results`.
#[cfg(feature = "python")]
struct RouterStageFenceGeometric {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageFenceGeometric {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.fence_geometric")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.fence_geometric", &ctx, |py| {
            let stage4 = ctx.get(py, &ctx.stage4)?;
            let routing_results = stage4.bind(py).getattr("routing_results")?;
            if ctx.flag(py, "fence")? && routing_results.is_truthy()? {
                let pcb = ctx.get(py, &ctx.pcb)?;
                ctx.run_fence(
                    py,
                    "router_v6.geometric",
                    "_stage_4_invariants",
                    pcb.bind(py),
                    None,
                    Some(&routing_results),
                )?;
            }
            Ok(state)
        })
    }
}

/// Post-routing ERC check (added only when `enable_erc_check` is set): the
/// gate call-back + the UNMEASURED / VIOLATIONS identity branches with the
/// module logger's warning calls (the `%s` / `%d` formatting stays CPython).
#[cfg(feature = "python")]
struct RouterStageErc {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageErc {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.erc")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.erc", &ctx, |py| {
            let gates = py.import("temper_placer.placer.cp_sat.gates")?;
            // The oracle's `ErcGate().check(BoardState(routed_pcb_path=...))`
            // evaluates ErcGate() BEFORE the BoardState(...) argument; the
            // construction order is observable and pinned.
            let erc_gate = gates.getattr("ErcGate")?.call0()?;
            let bs_kwargs = PyDict::new(py);
            bs_kwargs.set_item("routed_pcb_path", ctx.pcb_path.bind(py))?;
            let bs = gates.getattr("BoardState")?.call((), Some(&bs_kwargs))?;
            let erc_result = erc_gate.call_method1("check", (bs,))?;
            let status = erc_result.getattr("status")?;
            let gate_status = gates.getattr("GateStatus")?;
            let logger = py
                .import("logging")?
                .call_method1("getLogger", ("temper_placer.router_v6._pipeline_core",))?;
            if status.is(&gate_status.getattr("UNMEASURED")?) {
                let msg = erc_result.getattr("error_message")?;
                logger.call_method("warning", ("ERC gate UNMEASURED: %s", msg), None)?;
            } else if status.is(&gate_status.getattr("VIOLATIONS")?) {
                let n: usize = erc_result.getattr("violations")?.len()?;
                logger.call_method(
                    "warning",
                    ("ERC gate found %d violation(s) on routed board", n),
                    None,
                )?;
            }
            Ok(state)
        })
    }
}

/// Result assembly: the wall-clock runtime, the verbose summary prints
/// (CPython `str.format` for the `:.1f` renders), the `RouterV6Result`
/// construction and the final ledger checkout.
#[cfg(feature = "python")]
struct RouterStageResult {
    ctx: Arc<RunContext>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for RouterStageResult {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("router_v6.result")
    }
    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        let ctx = self.ctx.clone();
        stage_run("router_v6.result", &ctx, |py| {
            let runtime = ctx.started.elapsed().as_secs_f64();
            let stage4 = ctx.get(py, &ctx.stage4)?;
            let routing_results = stage4.bind(py).getattr("routing_results")?;
            let success: i64 = routing_results.getattr("success_count")?.extract()?;
            let failure: i64 = routing_results.getattr("failure_count")?.extract()?;
            if ctx.verbose(py)? {
                let msg = d6_util::py_format(
                    py,
                    "\nRouter V6 complete in {:.1f}s",
                    &[runtime.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
                let msg = d6_util::py_format(
                    py,
                    "  Routed: {} nets",
                    &[success.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
                let msg = d6_util::py_format(
                    py,
                    "  Failed: {} nets",
                    &[failure.into_pyobject(py)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
                let msg = d6_util::py_format(
                    py,
                    "  Completion: {:.1f}%",
                    &[completion_pct(success, failure)
                        .into_pyobject(py)?
                        .into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }

            let result_cls = py
                .import("temper_placer.router_v6._pipeline_types")?
                .getattr("RouterV6Result")?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("pcb", ctx.get(py, &ctx.pcb)?)?;
            kwargs.set_item("escape_vias", ctx.get(py, &ctx.escape_vias)?)?;
            kwargs.set_item("stage2", ctx.get(py, &ctx.stage2)?)?;
            kwargs.set_item("stage3", ctx.get(py, &ctx.stage3)?)?;
            kwargs.set_item("stage4", stage4)?;
            let report = ctx
                .manufacturing_report
                .lock()
                .map_err(|_| poison())?
                .clone();
            match report {
                Some(r) => kwargs.set_item("manufacturing_report", r)?,
                None => kwargs.set_item("manufacturing_report", py.None())?,
            }
            kwargs.set_item("runtime_seconds", runtime)?;
            let batch = ctx.pipeline.bind(py).getattr("last_batch_results")?;
            let batch_list = py.import("builtins")?.getattr("list")?.call1((batch,))?;
            kwargs.set_item("batch_results", batch_list)?;
            let result = result_cls.call((), Some(&kwargs))?;
            ctx.pipeline
                .bind(py)
                .getattr("ledger")?
                .call_method1("checkout", ("routing_complete", &result))?;
            ctx.set(&ctx.result, result.into_any().unbind())?;
            Ok(state)
        })
    }
}

/// The sequencing loop core (see the module docstring for the boundary).
#[cfg(feature = "python")]
pub(crate) fn run_router_pipeline(
    py: Python<'_>,
    pipeline: Py<PyAny>,
    pcb_path: Py<PyAny>,
    pcb_override: Option<Py<PyAny>>,
    net_class_assignments: Option<Py<PyAny>>,
    net_classes: Option<Py<PyAny>>,
    stage3_override: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let ctx = Arc::new(RunContext {
        pipeline,
        pcb_path,
        pcb_override,
        net_class_assignments,
        net_classes,
        stage3_override,
        started: std::time::Instant::now(),
        pending_error: Mutex::new(None),
        pcb: Mutex::new(None),
        escape_vias: Mutex::new(None),
        stage2: Mutex::new(None),
        stage3: Mutex::new(None),
        stage4: Mutex::new(None),
        manufacturing_report: Mutex::new(None),
        result: Mutex::new(None),
    });

    let mut runner = PipelineRunner::new(PipelineConfig::default());
    runner.add_stage(Box::new(RouterStageLoad { ctx: ctx.clone() }));
    if ctx.flag(py, "enable_legalization")? {
        runner.add_stage(Box::new(RouterStageLegalize { ctx: ctx.clone() }));
    }
    runner.add_stage(Box::new(RouterStageValidate { ctx: ctx.clone() }));
    runner.add_stage(Box::new(RouterStageEscapeVias { ctx: ctx.clone() }));
    runner.add_stage(Box::new(RouterStageChannel { ctx: ctx.clone() }));
    runner.add_stage(Box::new(RouterStageTopology { ctx: ctx.clone() }));
    runner.add_stage(Box::new(RouterStageGeometric { ctx: ctx.clone() }));
    if ctx.flag(py, "enable_manufacturing_drc")? {
        runner.add_stage(Box::new(RouterStageManufacturing { ctx: ctx.clone() }));
    }
    if ctx.flag(py, "fence")? {
        runner.add_stage(Box::new(RouterStageFenceGeometric { ctx: ctx.clone() }));
    }
    if ctx.flag(py, "enable_erc_check")? {
        runner.add_stage(Box::new(RouterStageErc { ctx: ctx.clone() }));
    }
    runner.add_stage(Box::new(RouterStageResult { ctx: ctx.clone() }));

    let (_final, report) = runner.run(BoardState::new());

    if report.halted_early {
        let value = ctx.pending_error.lock().map_err(|_| poison())?.take();
        if let Some(v) = value {
            return Err(PyErr::from_value(v.bind(py).clone()));
        }
        let names: Vec<String> = report
            .stage_reports
            .iter()
            .map(|r| r.name.clone())
            .collect();
        return Err(PyRuntimeError::new_err(format!(
            "router pipeline halted without a stage exception (stages: {names:?})"
        )));
    }

    let result = ctx
        .result
        .lock()
        .map_err(|_| poison())?
        .clone()
        .ok_or_else(|| PyRuntimeError::new_err("router pipeline completed without a result"))?;
    Ok(result)
}

// ---------------------------------------------------------------------------
// The pyclass surface
// ---------------------------------------------------------------------------

/// The Rust host of `RouterV6Pipeline.run()` (see the module docstring).
#[cfg(feature = "python")]
#[pyclass(module = "temper_orchestration")]
pub struct RouterPipeline;

#[cfg(feature = "python")]
#[pymethods]
impl RouterPipeline {
    #[new]
    fn new() -> Self {
        Self
    }

    /// Sequence the Router V6 stages through the Rust
    /// `PipelineRunner<BoardState>`, threading the Python objects (pcb,
    /// escape_vias, stage2/3/4, the manufacturing report) through the shared
    /// context (object identity preserved for untouched objects). The leaf
    /// compute stays Python call-backs; a raising stage halts the run and
    /// re-raises the ORIGINAL exception. `stage3_override` carries the R7
    /// skip decision's resolved empty `Stage3Output` (None runs stage 3
    /// normally).
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        pipeline,
        pcb_path,
        pcb_override=None,
        net_class_assignments=None,
        net_classes=None,
        stage3_override=None,
    ))]
    fn run(
        &self,
        py: Python<'_>,
        pipeline: Py<PyAny>,
        pcb_path: Py<PyAny>,
        pcb_override: Option<Py<PyAny>>,
        net_class_assignments: Option<Py<PyAny>>,
        net_classes: Option<Py<PyAny>>,
        stage3_override: Option<Py<PyAny>>,
    ) -> PyResult<Py<PyAny>> {
        run_router_pipeline(
            py,
            pipeline,
            pcb_path,
            pcb_override,
            net_class_assignments,
            net_classes,
            stage3_override,
        )
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn dfm_should_fail_matches_the_oracle_decision_table() {
        // The oracle: "critical" -> critical_violations > 0; "all" ->
        // total_violations > 0; "none" -> never. The differential pins this
        // end-to-end via the raise-parity cases; these pin the pure helper.
        assert!(!dfm_should_fail("none", 9, 9));
        assert!(!dfm_should_fail("critical", 0, 5));
        assert!(dfm_should_fail("critical", 1, 0));
        assert!(!dfm_should_fail("all", 1, 0));
        assert!(dfm_should_fail("all", 0, 3));
    }

    #[cfg_attr(test, test)]
    fn completion_pct_matches_cpython_true_division() {
        // 100 * s / max(1, s + f) as float: (0,0) -> 0/1 -> 0.0; (3,1) ->
        // 300/4 -> 75.0; (1,0) -> 100.0.
        assert_eq!(completion_pct(0, 0), 0.0);
        assert_eq!(completion_pct(3, 1), 75.0);
        assert_eq!(completion_pct(1, 0), 100.0);
        assert_eq!(completion_pct(0, 4), 0.0);
    }

    #[cfg_attr(test, test)]
    fn completion_pct_matches_cpython_for_typical_counts() {
        // Round-trip a few count pairs through the oracle expression using
        // exact rationals (the values are small ints, so f64 division of the
        // exact product is bit-identical to CPython true division).
        for (s, f) in [(2_i64, 3_i64), (7, 13), (1, 99), (42, 0)] {
            let denom = (s + f).max(1);
            let expected = (100.0 * s as f64) / denom as f64;
            assert_eq!(completion_pct(s, f), expected);
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("router_pipeline::tests::dfm_should_fail_matches_the_oracle_decision_table", dfm_should_fail_matches_the_oracle_decision_table),
        ("router_pipeline::tests::completion_pct_matches_cpython_true_division", completion_pct_matches_cpython_true_division),
        ("router_pipeline::tests::completion_pct_matches_cpython_for_typical_counts", completion_pct_matches_cpython_for_typical_counts),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

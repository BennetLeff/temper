// temper-drc-rs: Rust DRC engine for Temper induction cooker.
//
// A Rust library enforcing ~33 PCB design rule checks (15 migrated
// from Python with calibrated parity, 8 compile-time type invariants,
// 10 runtime geometric checks) consumed through a single PyO3 entry
// point by the placer fence, router post-route, and CI.
//
// Origin: U7 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

// All modules public for external / test access.
pub mod board;
#[cfg(feature = "python")]
pub mod board_py_bridge;
// Wave 4 Phase 4 — regression slice: DRC ratchet comparison kernels
// (drc_ratchet.rs) and the closure-test self-consistency kernels
// (closure_test.rs) and the physics-oracle compute kernels (physics_oracle.rs).
#[cfg(feature = "python")]
pub mod closure_test;
#[cfg(feature = "python")]
pub mod drc_ratchet;
#[cfg(feature = "python")]
pub mod physics_oracle;
pub mod constraints;
#[cfg(feature = "python")]
pub mod drc_contracts;
pub mod pyfmt;
#[cfg(feature = "python")]
pub mod req_safe_01;
pub mod dfm;
#[cfg(feature = "python")]
pub mod dfm_py;
// U1 of docs/plans/2026-08-11-001-feat-wasm-tier-phase2-plan.md — the
// portable FabricationEnvelope type. Plain data, no pyo3: unconditional
// like ipc.rs, so it is present in a `--no-default-features` wasm32 build.
pub mod manufacturing;
pub mod pymath;
pub mod validation_kernels;
#[cfg(feature = "python")]
pub mod router_clearance;
pub mod rules;
pub mod types;
#[cfg(feature = "python")]
pub mod validation;
#[cfg(feature = "python")]
pub mod violation_report;
// NOT gated on `python`. The wasm32 tier builds with --no-default-features,
// so an added `python` gate here silently excludes the registry and the
// runner fails to compile against it. Stacked `cfg` attributes are ANDed.
// `wasm-registry` is implied by every per-family feature and by
// `wasm-test-registry`, so any wasm build compiles this module.
#[cfg(feature = "wasm-registry")]
pub mod wasm_test_registry;
// Wave 4 Phase 5 — deterministic leaf DRC-check kernels (drc_validation /
// drc_sweep dedup / placement_validation / courtyard_check clamp).
#[cfg(feature = "python")]
pub mod deterministic_leaf_drc;
// Wave 4 orchestration-port — residual deterministic stage-leaf kernels of
// the validation + partition cluster (placement_validation's parsed-pads
// pin-position resolution, the phased validator's zone-slot flatten, and
// hv_lv_partition's bounds-area product).
#[cfg(feature = "python")]
pub mod deterministic_stage_leaves;
// Wave 4 Phase 5 — deterministic connectivity-validation kernel
// (connectivity_validation.py per-net algorithm).
#[cfg(feature = "python")]
pub mod deterministic_connectivity;
// Wave 4 — router_v6/constraints_design_rules.py hot-path clearance kernels
// (ClearanceMatrix.get_clearance / _get_base_clearance / get_track_width /
// get_via_diameter / get_via_drill / is_differential_pair, the
// add_differential_pair clearance arithmetic, and ZoneManager.get_zone_at).
#[cfg(feature = "python")]
pub mod clearance_matrix;
// Wave 4 marshalling boundary — drc_oracle pydantic→plain conversion and
// K1-schema dict builders migrated from validation/drc_oracle.py.
#[cfg(feature = "python")]
pub mod drc_oracle_marshal;
// Phase-A U5 (rust-orchestration-engine plan) — typed DRC marshalling
// types: DrcBoardSnapshot, ConstraintSet (pyclass TypedConstraintSet),
// ConstraintValue and the CheckRunner data surface, migrated from
// validation/drc_oracle.py + validation/drc_runner.py.
#[cfg(feature = "python")]
pub mod drc_marshal;
// Phase-A U6 (rust-orchestration-engine plan) — typed quality-oracle
// marshalling types OracleInput / OracleOutput, migrated from
// validation/human_reference_extractor.py (_netlist_to_oracle_dict /
// _placement_to_oracle_dict).
#[cfg(feature = "python")]
pub mod oracle_marshal;
// Phase-A U9 (rust-orchestration-engine plan) — typed DRC-feedback wire
// types Violation / DrcReport, migrated from
// deterministic/feedback/{violation_mapper,drc_parser}.py.
#[cfg(feature = "python")]
pub mod violation_contracts;
// Wave 4 — router_v6/constraints_drc_oracle.py DRCOracle decision kernels
// (Violation.severity, the R3 clearance-credit spatial scoping,
// can_place_via / can_place_track_segment, validate_all pairwise checks).
#[cfg(feature = "python")]
pub mod drc_oracle;

// Crate-fold 3 (2026-08-09): IPC-2221/2152 current-capacity and trace-width
// scalar kernels, consolidated from the deleted temper-ipc crate. `ipc` holds
// the pure kernels and their unit tests (unconditional, like the other DRC
// kernels); `ipc_pyo3` is the wholly-pyo3 surface exposing them on
// temper_drc_rs (see its module doc).
pub mod ipc;
#[cfg(feature = "python")]
pub mod ipc_pyo3;
// Crate-fold 3 (2026-08-15): DrcCount — a violation count that knows
// whether it's capped at KiCad's ERROR_LIMIT/EXTENDED_ERROR_LIMIT reporting
// caps or honest (drc_count.rs, pure data, unconditional like ipc.rs so it
// survives a --no-default-features wasm32 build; drc_count_pyo3.rs is the
// thin pyo3 surface).
pub mod drc_count;
#[cfg(feature = "python")]
pub mod drc_count_pyo3;
// Wave 4 — validation-glue kernels (port-inventory entry-5 cluster):
// _drc_api.py parsing, scheduler.py decision logic, validation_gates.py
// gate decisions.
#[cfg(feature = "python")]
pub mod validation_glue;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyDict, PyList};
#[cfg(feature = "python")]
use pyo3::Py;

#[cfg(feature = "python")]
use crate::board_py_bridge::build_board_state;
#[cfg(feature = "python")]
use crate::constraints::build_constraint_set;
#[cfg(feature = "python")]
use crate::rules::create_default_registry;
#[cfg(feature = "python")]
use crate::rules::{DrcCategory, Violation};

// ---------------------------------------------------------------------------
// Primary entry point
// ---------------------------------------------------------------------------

/// Python-callable entry point: run DRC checks on a board.
///
/// # Parameters (all positional)
///
/// | Parameter | Type | Description |
/// |-----------|------|-------------|
/// | `board_dict` | `dict \| DrcBoardSnapshot` | Board state matching the K1 schema (plan §K1) — or the Phase-A U5 typed snapshot |
/// | `constraints_dict` | `dict \| TypedConstraintSet` | Constraint configuration from YAML — or the Phase-A U5 typed set |
/// | `categories` | `list[str] \| None` | Filter: only run checks in these categories |
/// | `check_names` | `list[str] \| None` | Filter: only run these named checks |
/// | `modified_regions` | `list[[x1,y1,x2,y2]] \| None` | Bboxes for incremental re-checking |
///
/// # Returns
///
/// A Python list of violation dicts (empty list = clean board). Each
/// dict has keys: `severity`, `code`, `message`, `category`,
/// `check_name`, `affected_items`, `location`, `details`.
///
/// # Errors
///
/// - `PyValueError` if `board_dict` or `constraints_dict` are malformed, or
///   are neither a dict nor the typed Phase-A U5 struct.
///
/// During the strangler-fig migration (U4–U6), this function is called
/// alongside the Python `temper-drc` engine. After cutover, it becomes
/// the sole DRC provider.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (board_dict, constraints_dict, categories = None, check_names = None, modified_regions = None))]
fn run_drc(
    py: Python<'_>,
    board_dict: &Bound<'_, PyAny>,
    constraints_dict: &Bound<'_, PyAny>,
    categories: Option<Vec<String>>,
    check_names: Option<Vec<String>>,
    modified_regions: Option<Vec<(f64, f64, f64, f64)>>,
) -> PyResult<Py<PyAny>> {
    // ── 1. Deserialize ──────────────────────────────────────────────────
    // Polymorphic entry: the caller may pass the K1-schema dict wire
    // format (drc_ratchet.py and other dict-based consumers, plus the
    // WASM serialize path) OR the Phase-A U5 typed structs
    // (DrcBoardSnapshot / TypedConstraintSet) directly — the typed path
    // converts without a dict round-trip.
    let board_state = if let Ok(dict) = board_dict.cast::<PyDict>() {
        build_board_state(dict).map_err(|e| {
            PyValueError::new_err(format!("board deserialization error: {e}"))
        })?
    } else if board_dict.is_instance_of::<crate::drc_marshal::DrcBoardSnapshot>() {
        board_dict
            .cast::<crate::drc_marshal::DrcBoardSnapshot>()
            .map_err(|e| PyValueError::new_err(format!("board is not a DrcBoardSnapshot: {e}")))?
            .borrow()
            .to_board_state()
            .map_err(|e| {
                PyValueError::new_err(format!("board snapshot conversion error: {e}"))
            })?
    } else {
        return Err(PyValueError::new_err(
            "board must be a K1-schema dict or a temper_drc_rs.DrcBoardSnapshot",
        ));
    };
    let constraints_set = if let Ok(dict) = constraints_dict.cast::<PyDict>() {
        build_constraint_set(dict).map_err(|e| {
            PyValueError::new_err(format!("constraint deserialization error: {e}"))
        })?
    } else if constraints_dict.is_instance_of::<crate::drc_marshal::ConstraintSet>() {
        constraints_dict
            .cast::<crate::drc_marshal::ConstraintSet>()
            .map_err(|e| {
                PyValueError::new_err(format!("constraints is not a TypedConstraintSet: {e}"))
            })?
            .borrow()
            .to_engine()
    } else {
        return Err(PyValueError::new_err(
            "constraints must be a constraints dict or a temper_drc_rs.TypedConstraintSet",
        ));
    };

    // ── 2. Create registry with all default checks ──────────────────────
    let registry = create_default_registry();

    // ── 3. Run checks (filtered / incremental / full) ───────────────────
    let violations = if let Some(regions) = modified_regions {
        // Incremental mode: check only within modified bboxes
        let rects: Vec<geo::Rect<f64>> = regions
            .into_iter()
            .map(|(x1, y1, x2, y2)| {
                geo::Rect::new(
                    geo::Coord { x: x1, y: y1 },
                    geo::Coord { x: x2, y: y2 },
                )
            })
            .collect();
        registry.run_incremental(&board_state, &constraints_set, &rects)
    } else if let Some(cats) = categories {
        // Category-filtered mode
        let parsed: Vec<DrcCategory> = cats
            .iter()
            .map(|c| parse_category(c))
            .collect::<Result<Vec<_>, _>>()
            .map_err(PyValueError::new_err)?;
        registry.run_categories(&board_state, &constraints_set, &parsed)
    } else if let Some(names) = check_names {
        // Check-name-filtered mode
        registry
            .run_all(&board_state, &constraints_set)
            .into_iter()
            .filter(|v| names.contains(&v.check_name))
            .collect()
    } else {
        // Full sweep
        registry.run_all(&board_state, &constraints_set)
    };

    // ── 4. Convert violations to Python dicts ───────────────────────────
    let py_list = PyList::empty(py);
    for v in &violations {
        let d = violation_to_py_dict(py, v)?;
        py_list.append(d)?;
    }

    Ok(py_list.into())
}

// ---------------------------------------------------------------------------
// Board serialization helper (for WASM tier cost-model measurements)
// ---------------------------------------------------------------------------

/// Serialize a BoardState to JSON from a Python board dict.
///
/// This exists so cost-model benchmarks can deserialize a pre-computed
/// board snapshot without embedding Python in the measurement process.
/// The Rust rules need a `BoardState`; the only path to one from a
/// production `.kicad_pcb` file is through the Python bridge.  This
/// function captures that bridge output as a JSON string the Rust
/// example `r2_full_board_pass` reads back via `serde_json`.
#[cfg(feature = "python")]
#[pyfunction]
fn serialize_board_state(board_dict: &Bound<'_, PyDict>) -> PyResult<String> {
    let board = build_board_state(board_dict).map_err(|e| {
        PyValueError::new_err(format!("board deserialization error: {e}"))
    })?;
    serde_json::to_string(&board)
        .map_err(|e| PyValueError::new_err(format!("board serialization error: {e}")))
}

// ---------------------------------------------------------------------------
// Category parsing
// ---------------------------------------------------------------------------

/// Parse a category string into a `DrcCategory` enum value.
#[cfg(feature = "python")]
fn parse_category(s: &str) -> Result<DrcCategory, String> {
    match s.to_lowercase().as_str() {
        "drc" => Ok(DrcCategory::Drc),
        "erc" => Ok(DrcCategory::Erc),
        "safety" => Ok(DrcCategory::Safety),
        "emc" => Ok(DrcCategory::Emc),
        "dfm" => Ok(DrcCategory::Dfm),
        other => Err(format!(
            "unknown DRC category: '{other}'. Expected one of: drc, erc, safety, emc, dfm"
        )),
    }
}

// ---------------------------------------------------------------------------
// Violation → PyDict conversion
// ---------------------------------------------------------------------------

/// Convert a single `Violation` to a Python dict with the standard schema:
///
/// ```python
/// {
///     "severity": "CRITICAL",       # uppercase string
///     "code": "DRC_CLR_001",
///     "message": "...",
///     "category": "drc",            # lowercase
///     "check_name": "drc_clearance",
///     "affected_items": ["C1", "C2"],
///     "location": {"x": 10.0, "y": 20.0, "layer": "F.Cu"},  # or None
///     "details": {...},
/// }
/// ```
#[cfg(feature = "python")]
fn violation_to_py_dict<'py>(py: Python<'py>, v: &Violation) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);

    // ── Scalars ─────────────────────────────────────────────────────
    d.set_item("severity", v.severity.to_string().to_uppercase())?;
    d.set_item("code", &v.code)?;
    d.set_item("message", &v.message)?;
    d.set_item("category", v.category.to_string())?;
    d.set_item("check_name", &v.check_name)?;

    // ── Affected items (list of strings) ────────────────────────────
    let affected = PyList::empty(py);
    for item in &v.affected_items {
        affected.append(item)?;
    }
    d.set_item("affected_items", affected)?;

    // ── Location dict (or None) ─────────────────────────────────────
    if let Some(ref loc) = v.location {
        let loc_dict = PyDict::new(py);
        if let Some(x) = loc.x {
            loc_dict.set_item("x", x)?;
        } else {
            loc_dict.set_item("x", py.None())?;
        }
        if let Some(y) = loc.y {
            loc_dict.set_item("y", y)?;
        } else {
            loc_dict.set_item("y", py.None())?;
        }
        if let Some(ref layer) = loc.layer {
            loc_dict.set_item("layer", layer)?;
        } else {
            loc_dict.set_item("layer", py.None())?;
        }
        d.set_item("location", loc_dict)?;
    } else {
        d.set_item("location", py.None())?;
    }

    // ── Details (serde_json::Value → Python dict/object) ────────────
    let details = json_value_to_py(py, &v.details)?;
    d.set_item("details", details)?;

    Ok(d)
}

// ---------------------------------------------------------------------------
// serde_json → PyObject conversion
// ---------------------------------------------------------------------------

/// Recursively convert a `serde_json::Value` to a Python object.
///
/// Handles:
/// - `Null`      → `None`
/// - `Bool`      → `bool`
/// - `Number`    → `int` or `float` (f64 fallback)
/// - `String`    → `str`
/// - `Array`     → `list`
/// - `Object`    → `dict`
#[cfg(feature = "python")]
fn json_value_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<Py<PyAny>> {
    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => {
            let obj = (*b).into_pyobject(py)?;
            Ok(obj.as_any().clone().unbind())
        }
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                let obj = i.into_pyobject(py)?;
                Ok(obj.as_any().clone().unbind())
            } else if let Some(f) = n.as_f64() {
                let obj = f.into_pyobject(py)?;
                Ok(obj.as_any().clone().unbind())
            } else {
                let s = n.to_string();
                let obj = s.into_pyobject(py)?;
                Ok(obj.as_any().clone().unbind())
            }
        }
        serde_json::Value::String(s) => {
            let obj = s.clone().into_pyobject(py)?;
            Ok(obj.as_any().clone().unbind())
        }
        serde_json::Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(json_value_to_py(py, item)?)?;
            }
            Ok(list.into())
        }
        serde_json::Value::Object(map) => {
            let d = PyDict::new(py);
            for (k, v) in map {
                d.set_item(k.as_str(), json_value_to_py(py, v)?)?;
            }
            Ok(d.into())
        }
    }
}

// ---------------------------------------------------------------------------
// Module entry point
// ---------------------------------------------------------------------------

/// Python module entry point: `temper_drc_rs`.
#[cfg(feature = "python")]
#[pymodule]
fn temper_drc_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_drc, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_board_state, m)?)?;
    m.add_function(wrap_pyfunction!(
        crate::router_clearance::verify_route_clearance,
        m
    )?)?;
    // Wave 4 Phase 4 — validation DRC-check kernels (validation.rs).
    crate::validation::register(m)?;
    // Wave 4 Phase 4 — analysis/_violation_report.py report kernels.
    crate::violation_report::register(m)?;
    // Wave 4 Phase 5 — REQ-SAFE-01 clearance/creepage validator
    // (req_safe_01.rs).
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_check_domain_clearance,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_check_creepage_path,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_verify_iec60335,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_format_clearance_report,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_requirement_matrix,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_nets_domain_map,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_components_in_domain,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_domain_boundary_pairs,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_component_pads,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        crate::req_safe_01::req_safe_01_copper_model_init,
        m
    )?)?;
    // Wave 4 cluster D — router_v6 post-route DFM kernels (dfm.rs).
    crate::dfm_py::register(m)?;
    // Wave 4 Phase 4 — regression slice: drc_ratchet / closure_test /
    // physics_oracle kernels.
    crate::drc_ratchet::register(m)?;
    crate::closure_test::register(m)?;
    crate::physics_oracle::register(m)?;
    // Wave 4 Phase 4 — regression slice: drc_ratchet / closure_test /
    // physics_oracle kernels.
    // Wave 4 Phase 2 — drc_types / drc_result contract pyclasses.
    crate::drc_contracts::register(m)?;
    // Wave 4 Phase 5 — deterministic leaf DRC-check kernels.
    crate::deterministic_leaf_drc::register(m)?;
    crate::deterministic_connectivity::register(m)?;
    // Wave 4 orchestration-port — residual validation + partition stage-leaf
    // kernels.
    crate::deterministic_stage_leaves::register(m)?;
    // Wave 4 — router_v6/constraints_design_rules.py hot-path clearance
    // kernels (clearance_matrix.rs).
    crate::clearance_matrix::register(m)?;
    // Wave 4 marshalling boundary — drc_oracle pydantic→plain + K1 dict
    // builders migrated from validation/drc_oracle.py.
    crate::drc_oracle_marshal::register(m)?;
    // Phase-A U5 — typed DRC marshalling types (DrcBoardSnapshot,
    // TypedConstraintSet, ConstraintValue) + the CheckRunner data surface.
    crate::drc_marshal::register(m)?;
    // Phase-A U6 — typed quality-oracle marshalling types (OracleInput,
    // OracleOutput) from validation/human_reference_extractor.py.
    crate::oracle_marshal::register(m)?;
    // Phase-A U9 — typed DRC-feedback wire types (Violation, DrcReport)
    // from deterministic/feedback/{violation_mapper,drc_parser}.py.
    crate::violation_contracts::register(m)?;
    // Wave 4 — router_v6/constraints_drc_oracle.py DRCOracle decision
    // kernels (drc_oracle.rs): severity, R3 clearance credits,
    // can_place_via / can_place_track_segment, validate_all pairwise checks.
    crate::drc_oracle::register(m)?;
    // Crate-fold 3 (2026-08-09) — IPC-2221/2152 current-capacity and
    // trace-width kernels (from temper-ipc).
    crate::ipc_pyo3::register(m)?;
    // Crate-fold 3 (2026-08-15) — DrcCount cap-classification kernels
    // (drc_count.rs pure logic; this pyo3 surface).
    crate::drc_count_pyo3::register(m)?;
    // Wave 4 — validation-glue kernels (port-inventory entry-5 cluster):
    // _drc_api.py parsing, scheduler.py decisions, validation_gates.py gates.
    crate::validation_glue::register(m)?;
    Ok(())
}

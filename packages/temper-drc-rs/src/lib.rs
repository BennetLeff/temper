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
pub mod pymath;
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
#[cfg(feature = "wasm-test-registry")]
pub mod wasm_test_registry;

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList};
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
/// | `board_dict` | `dict` | Board state matching the K1 schema (plan §K1) |
/// | `constraints_dict` | `dict` | Constraint configuration from YAML |
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
/// - `PyValueError` if `board_dict` or `constraints_dict` are malformed.
///
/// During the strangler-fig migration (U4–U6), this function is called
/// alongside the Python `temper-drc` engine. After cutover, it becomes
/// the sole DRC provider.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (board_dict, constraints_dict, categories = None, check_names = None, modified_regions = None))]
fn run_drc(
    py: Python<'_>,
    board_dict: &Bound<'_, PyDict>,
    constraints_dict: &Bound<'_, PyDict>,
    categories: Option<Vec<String>>,
    check_names: Option<Vec<String>>,
    modified_regions: Option<Vec<(f64, f64, f64, f64)>>,
) -> PyResult<Py<PyAny>> {
    // ── 1. Deserialize ──────────────────────────────────────────────────
    let board = build_board_state(board_dict).map_err(|e| {
        PyValueError::new_err(format!("board deserialization error: {e}"))
    })?;
    let constraints = build_constraint_set(constraints_dict).map_err(|e| {
        PyValueError::new_err(format!("constraint deserialization error: {e}"))
    })?;

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
        registry.run_incremental(&board, &constraints, &rects)
    } else if let Some(cats) = categories {
        // Category-filtered mode
        let parsed: Vec<DrcCategory> = cats
            .iter()
            .map(|c| parse_category(c))
            .collect::<Result<Vec<_>, _>>()
            .map_err(PyValueError::new_err)?;
        registry.run_categories(&board, &constraints, &parsed)
    } else if let Some(names) = check_names {
        // Check-name-filtered mode
        registry
            .run_all(&board, &constraints)
            .into_iter()
            .filter(|v| names.contains(&v.check_name))
            .collect()
    } else {
        // Full sweep
        registry.run_all(&board, &constraints)
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
    Ok(())
}

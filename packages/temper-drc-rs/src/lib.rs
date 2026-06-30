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
pub mod board_py_bridge;
pub mod constraints;
pub mod rules;
pub mod types;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::ToPyObject;
use pyo3::types::{PyDict, PyList};

use crate::board_py_bridge::build_board_state;
use crate::constraints::build_constraint_set;
use crate::rules::create_default_registry;
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
#[pyfunction]
#[pyo3(signature = (board_dict, constraints_dict, categories = None, check_names = None, modified_regions = None))]
fn run_drc(
    py: Python<'_>,
    board_dict: &Bound<'_, PyDict>,
    constraints_dict: &Bound<'_, PyDict>,
    categories: Option<Vec<String>>,
    check_names: Option<Vec<String>>,
    modified_regions: Option<Vec<(f64, f64, f64, f64)>>,
) -> PyResult<PyObject> {
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
            .map_err(|e| PyValueError::new_err(e))?;
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
fn json_value_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => Ok(b.to_object(py)),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(f) = n.as_f64() {
                Ok(f.to_object(py))
            } else {
                Ok(n.to_string().to_object(py))
            }
        }
        serde_json::Value::String(s) => Ok(s.to_object(py)),
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
#[pymodule]
fn temper_drc_rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_drc, m)?)?;
    Ok(())
}

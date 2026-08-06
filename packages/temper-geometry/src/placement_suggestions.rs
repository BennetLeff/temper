//! Wave-4 Phase B: `router_v6/placement_suggestions.py`, part of the
//! congestion & placement-feedback cluster (cluster E).
//!
//! Mirrors, bit for bit, the pinned Python oracle's
//! `generate_placement_suggestions`, `_find_affected_components` and
//! `_calculate_suggested_position`.
//!
//! # `placement_suggestions_generate_py`'s return shape
//!
//! `docs/evidence/2026-08-06-751-phase-a-adapter-inconsistencies.md`
//! documents that the differential's two call sites for this symbol project
//! two different tuple arities out of the same oracle object:
//! `test_generate_placement_suggestions_bit_exact` signs the 5-tuple
//! `(component_id, current_position, suggested_position, reason, priority)`,
//! and `test_generate_placement_suggestions_over_many_regions` signs a
//! 4-tuple that drops `current_position`. Both are lossy views of the same
//! `PlacementSuggestion` dataclass, which carries all five fields, and the
//! note establishes the 5-tuple as correct (`current_position` is compared
//! everywhere else in the cluster, and the 4-tuple looks like a copy/paste
//! slip in the test file). This kernel returns the 5-tuple unconditionally,
//! so `test_generate_placement_suggestions_over_many_regions` is expected to
//! fail — not a Rust defect, a test-file defect, tracked for a one-line fix.
//!
//! # Why `(dx**2 + dy**2) ** 0.5` goes through `pow_operator`
//!
//! CPython's `**` is libm `pow`, is two separate calls here (once per
//! coordinate, once for the square root), and — unlike `math.pow` or
//! `f64::powf` — **raises** `OverflowError(34, 'Result too large')` when a
//! FINITE base's result overflows to infinity, while leaving an already
//! infinite or NaN base alone. `escape_via.rs` measured and documented this
//! trap (B7) first; this module carries its own copy of the same guard
//! because that file is out of scope here.

use pyo3::exceptions::PyOverflowError;
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyDict, PyList};

use crate::congestion::cpython_min2;
use crate::host_math;

/// `(cx, cy, radius, severity, failed_net_count, bottleneck_score)` — the
/// flat shape `SUGGESTION_REGIONS` rows carry, and what `_region()` in the
/// differential builds a `CongestedRegion` from. `severity` arrives as the
/// plain string the oracle's own `region.severity.value` resolves to,
/// whether the oracle's `region.severity` was a real `CongestionSeverity`
/// member or the differential's `_FakeSeverity` shim — both expose the same
/// `.value` string, so the Rust side never needs to model either type.
type RegionRow = (f64, f64, f64, String, i64, f64);

/// `(component_id, current_position, suggested_position, reason, priority)`
/// -- the 5-tuple `placement_suggestions_generate_py` returns per
/// suggestion. See the module doc comment for why this is the only
/// projection implemented.
type SuggestionRow = (String, (f64, f64), (f64, f64), String, f64);

/// CPython's float `**` operator, including its overflow behaviour.
///
/// `host_math::pow` is libm, which saturates to infinity; CPython's `**`
/// raises instead when the base was finite. See the module doc comment (B7).
fn pow_operator(base: f64, exp: f64) -> PyResult<f64> {
    let r = host_math::pow(base, exp);
    if r.is_infinite() && base.is_finite() {
        return Err(PyOverflowError::new_err((34, "Result too large")));
    }
    Ok(r)
}

/// `(dx**2 + dy**2) ** 0.5` — three `pow_operator` calls, in the reference's
/// own grouping (NOT `math.hypot`, NOT `math.sqrt(dx*dx + dy*dy)`; both
/// measurably disagree with this form on real inputs).
fn pow_distance(dx: f64, dy: f64) -> PyResult<f64> {
    let sum = pow_operator(dx, 2.0)? + pow_operator(dy, 2.0)?;
    pow_operator(sum, 0.5)
}

/// `_find_affected_components`'s inclusion test and body, shared by the
/// standalone pyfunction and by `generate_placement_suggestions`'s loop.
fn find_affected_components(
    region: &RegionRow,
    positions: &[(String, (f64, f64))],
) -> PyResult<Vec<(String, (f64, f64))>> {
    let (cx, cy, radius, _severity, _failed, _score) = region;
    let mut affected = Vec::new();
    for (comp_id, pos) in positions {
        let dx = pos.0 - cx;
        let dy = pos.1 - cy;
        let distance = pow_distance(dx, dy)?;
        // NaN makes this comparison false, so a NaN-tainted position (or a
        // NaN-tainted region centre) is excluded, not included -- the same
        // IEEE `<` CPython uses, so no CPython-`min`/`max`-style asymmetry
        // applies here.
        if distance < radius * 2.0 {
            affected.push((comp_id.clone(), *pos));
        }
    }
    Ok(affected)
}

/// `_calculate_suggested_position`'s body, shared the same way.
fn calculate_suggested_position(
    current_pos: (f64, f64),
    congestion_center: (f64, f64),
    severity: &str,
) -> PyResult<(f64, f64)> {
    let mut dx = current_pos.0 - congestion_center.0;
    let mut dy = current_pos.1 - congestion_center.1;
    let mut distance = pow_distance(dx, dy)?;

    if distance < 0.1 {
        dx = 5.0;
        dy = 0.0;
        distance = 5.0;
    }

    let dx_norm = dx / distance;
    let dy_norm = dy / distance;

    // `.get(severity, 3.0)` -- an exact string match against the four known
    // keys; anything else, including the corpus's "none" and
    // "UNKNOWN_SEVERITY" rows, takes the 3.0 default.
    let move_distance = match severity {
        "critical" => 10.0,
        "high" => 7.0,
        "medium" => 5.0,
        "low" => 3.0,
        _ => 3.0,
    };

    let new_x = current_pos.0 + dx_norm * move_distance;
    let new_y = current_pos.1 + dy_norm * move_distance;
    Ok((new_x, new_y))
}

/// `format(score, '.2f')` -- half-to-even rounding of the exact binary
/// value, e.g. `0.125` renders `'0.12'`. Delegated to Python's own
/// `format()` rather than any Rust formatting, which rounds half-away and
/// would disagree on exactly the corpus rows chosen to catch it (B3).
fn format_2f(py: Python<'_>, value: f64) -> PyResult<String> {
    py.import("builtins")?
        .call_method1("format", (value, ".2f"))?
        .extract()
}

/// A `component_positions` dict's `.items()`, preserving CPython's
/// insertion-order iteration -- the suggestion list's ORDER is part of the
/// contract (`test_generate_placement_suggestions_over_many_regions`'s own
/// docstring says so), so this must not be collected into anything
/// unordered like a `HashMap`.
fn positions_items(positions: Option<&Bound<'_, PyDict>>) -> PyResult<Vec<(String, (f64, f64))>> {
    let Some(dict) = positions else {
        return Ok(Vec::new());
    };
    let mut out = Vec::with_capacity(dict.len());
    for (k, v) in dict.iter() {
        let key: String = k.extract()?;
        let val: (f64, f64) = v.extract()?;
        out.push((key, val));
    }
    Ok(out)
}

/// `_find_affected_components`.
#[pyfunction]
pub fn placement_find_affected_py<'py>(
    py: Python<'py>,
    region: RegionRow,
    component_positions: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let positions = positions_items(component_positions.as_ref())?;
    let affected = find_affected_components(&region, &positions)?;
    Ok(affected.into_pyobject(py)?.into_any())
}

/// `_calculate_suggested_position`.
#[pyfunction]
pub fn placement_suggested_position_py(
    current_pos: (f64, f64),
    congestion_center: (f64, f64),
    severity: String,
) -> PyResult<(f64, f64)> {
    calculate_suggested_position(current_pos, congestion_center, &severity)
}

/// `generate_placement_suggestions`, returning the 5-tuple
/// `(component_id, current_position, suggested_position, reason, priority)`
/// per suggestion -- see the module doc comment for why the 4-tuple the
/// `over_many_regions` test asks for is not implemented.
///
/// `regions` accepts either a single region row (the `bit_exact` and
/// `find_affected` call sites) or a Python list of rows (the
/// `over_many_regions` call site, which builds a `CongestionMap` with one
/// region per corpus row) -- an input-shape polymorphism, not a return-shape
/// one: both arms build the identical list of `CongestedRegion`s the oracle
/// would from the same input and always emit the same 5-tuple per
/// suggestion.
#[pyfunction]
#[pyo3(signature = (regions, component_positions))]
pub fn placement_suggestions_generate_py<'py>(
    py: Python<'py>,
    regions: Bound<'py, PyAny>,
    component_positions: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let region_rows: Vec<RegionRow> = if let Ok(list) = regions.cast::<PyList>() {
        list.extract()?
    } else {
        vec![regions.extract()?]
    };
    let positions = positions_items(component_positions.as_ref())?;

    let mut out: Vec<SuggestionRow> = Vec::new();

    for region in &region_rows {
        let (cx, cy, _radius, severity, _failed, score) = region;
        // NaN `bottleneck_score < 0.5` is false, so a NaN-scored region is
        // NOT skipped here -- matches the oracle's plain `<` (no CPython
        // min/max asymmetry involved in a bare comparison).
        if *score < 0.5 {
            continue;
        }

        let affected = find_affected_components(region, &positions)?;
        for (comp_id, comp_pos) in affected {
            let suggested = calculate_suggested_position(comp_pos, (*cx, *cy), severity)?;
            let priority = cpython_min2(1.0, score * 1.2);
            let score_str = format_2f(py, *score)?;
            let reason = format!("Reduce {severity} congestion (score: {score_str})");
            out.push((comp_id, comp_pos, suggested, reason, priority));
        }
    }

    Ok(out.into_pyobject(py)?.into_any())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(placement_suggestions_generate_py, m)?)?;
    m.add_function(wrap_pyfunction!(placement_find_affected_py, m)?)?;
    m.add_function(wrap_pyfunction!(placement_suggested_position_py, m)?)?;
    Ok(())
}

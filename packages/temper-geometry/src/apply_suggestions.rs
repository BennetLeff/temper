//! Wave-4 Phase B: `router_v6/apply_suggestions.py` in Rust.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_congestion_py_oracle.py`'s
//! `apply_suggestions.py` section (`apply_suggestions_with_damping`,
//! `_calculate_damped_position`, `AdjustmentResult.total_movement`,
//! `update_component_positions`).
//!
//! # Known test-file defect in scope
//!
//! `docs/evidence/2026-08-06-751-phase-a-adapter-inconsistencies.md` (finding
//! 2) documents that `test_congestion_rust_differential.py` asks
//! `apply_suggestions_damped_py` for two different return projections from
//! two call sites, and the two are not distinguishable by input (the only
//! difference is the SIZE of a `dict` argument). This kernel implements the
//! **3-tuple** projection
//! `([(component_id, original_position, suggested_position, applied_position,
//! damping_factor)], adjustment_count, total_movement)`, per that note's
//! conclusion: `total_movement` is where the `(dx**2 + dy**2) ** 0.5`
//! libm-`pow` trap actually bites, and the id-only projection the other call
//! site wants cannot see it.
//! `test_apply_suggestions_with_missing_component` therefore fails on a type
//! mismatch (`list` vs `tuple`) by design; it is a defect in the test file,
//! not this kernel, per the evidence doc.
//!
//! # Why `**` is `pow_operator`, not `x * x`
//!
//! `_find_affected_components`, `_calculate_suggested_position` and
//! `AdjustmentResult.total_movement` all compute a Euclidean distance as
//! `(dx**2 + dy**2) ** 0.5`. CPython's `**` on floats is libm `pow`, not
//! repeated multiplication, and it RAISES `OverflowError(34, 'Result too
//! large')` when a finite base overflows, where libm `pow` alone saturates to
//! `inf`. `escape_via.rs`'s `pow_operator` already carries this guard (its
//! module doc calls out the same trap, B7); it is reused here as
//! `pub(crate)` rather than copied. The corpus exercises the raise directly:
//! `test_total_movement_bit_exact` includes a `(1e200, 1e200)` move, whose
//! `dx ** 2` is `1e400` and overflows `f64`.
//!
//! `min(1.0, region.bottleneck_score * 1.2)` reuses `congestion.rs`'s
//! `cpython_min2` for the same reason `congestion.rs` documents: CPython's
//! `min` keeps the FIRST argument on a tie or a NaN comparison, which is the
//! opposite asymmetry from `f64::min`. The corpus carries a NaN
//! `bottleneck_score` row specifically to catch a mirror that reaches for
//! `f64::min`.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods};

use crate::congestion::cpython_min2;
use crate::escape_via::pow_operator;

/// `(dx ** 2 + dy ** 2) ** 0.5`, exactly as the oracle spells it -- three
/// separate libm `pow` calls (two squarings, one square root), each subject
/// to CPython's overflow-to-exception behaviour via [`pow_operator`].
fn hypot_pow(dx: f64, dy: f64) -> PyResult<f64> {
    let dx2 = pow_operator(dx, 2.0)?;
    let dy2 = pow_operator(dy, 2.0)?;
    pow_operator(dx2 + dy2, 0.5)
}

/// `_calculate_damped_position` -- linear interpolation, no clamping of
/// `damping` (the corpus deliberately carries out-of-[0,1] and non-finite
/// damping factors and expects them applied verbatim).
fn calculate_damped_position(current: (f64, f64), suggested: (f64, f64), damping: f64) -> (f64, f64) {
    let new_x = current.0 + (suggested.0 - current.0) * damping;
    let new_y = current.1 + (suggested.1 - current.1) * damping;
    (new_x, new_y)
}

/// The `{"critical": 10.0, "high": 7.0, "medium": 5.0, "low": 3.0}.get(severity, 3.0)`
/// table from `_calculate_suggested_position`. Any severity string not in the
/// table -- including the corpus's `"none"` and `"UNKNOWN_SEVERITY"` -- takes
/// the `3.0` default.
fn move_distance_for_severity(severity: &str) -> f64 {
    match severity {
        "critical" => 10.0,
        "high" => 7.0,
        "medium" => 5.0,
        "low" => 3.0,
        _ => 3.0,
    }
}

/// `_calculate_suggested_position`.
fn calculate_suggested_position(
    current: (f64, f64),
    center: (f64, f64),
    severity: &str,
) -> PyResult<(f64, f64)> {
    let mut dx = current.0 - center.0;
    let mut dy = current.1 - center.1;
    let mut distance = hypot_pow(dx, dy)?;

    // "Already at centre, move arbitrarily" -- strictly `< 0.1`, not `<=`.
    if distance < 0.1 {
        dx = 5.0;
        dy = 0.0;
        distance = 5.0;
    }

    let dx_norm = dx / distance;
    let dy_norm = dy / distance;
    let move_distance = move_distance_for_severity(severity);

    Ok((current.0 + dx_norm * move_distance, current.1 + dy_norm * move_distance))
}

/// A `(component_id, position)` pair, in the order Python's `dict.items()`
/// yields them -- iteration order is part of the value here, so a Rust
/// `HashMap` (unordered) is not a legal stand-in for the source dict.
fn extract_ordered_positions(dict: &Bound<'_, PyDict>) -> PyResult<Vec<(String, (f64, f64))>> {
    let mut out = Vec::with_capacity(dict.len());
    for (k, v) in dict.iter() {
        let key: String = k.extract()?;
        let val: (f64, f64) = v.extract()?;
        out.push((key, val));
    }
    Ok(out)
}

/// One `CongestedRegion`, flattened to the 6-tuple `SUGGESTION_REGIONS` rows
/// carry: `(center_x, center_y, radius, severity, failed_net_count,
/// bottleneck_score)`. `failed_net_count` is never read downstream of
/// `generate_placement_suggestions` (it only feeds the `reason` string, which
/// this cluster's projection does not sign), so it is accepted and unused.
type RegionRow = (f64, f64, f64, String, i64, f64);

/// One `PlacementSuggestion`, minus the `reason` field this kernel's callers
/// never project.
struct Suggestion {
    component_id: String,
    current_position: (f64, f64),
    suggested_position: (f64, f64),
    priority: f64,
}

/// `generate_placement_suggestions`, restricted to the fields
/// `apply_suggestions_with_damping` actually consumes.
///
/// Iterates `regions` in the given order and, within each region,
/// `positions` in dict order -- both orders are part of the differential's
/// contract (the final adjustments list is not resorted anywhere downstream).
fn generate_suggestions(
    regions: &[RegionRow],
    positions: &[(String, (f64, f64))],
) -> PyResult<Vec<Suggestion>> {
    let mut suggestions = Vec::new();

    for region in regions {
        let score = region.5;
        // `region.bottleneck_score < 0.5 -> skip`. NaN `<` is false, so a NaN
        // score is NOT skipped (B5) -- the comparison, not a helper, carries
        // that.
        if score < 0.5 {
            continue;
        }
        let center = (region.0, region.1);
        let radius = region.2;
        let severity = region.3.as_str();

        for (component_id, comp_pos) in positions {
            let dx = comp_pos.0 - center.0;
            let dy = comp_pos.1 - center.1;
            let distance = hypot_pow(dx, dy)?;

            // "within 2x region radius" -- strictly `<`, so a component
            // sitting exactly on the boundary is excluded.
            if distance < radius * 2.0 {
                let suggested_position = calculate_suggested_position(*comp_pos, center, severity)?;
                // `min(1.0, region.bottleneck_score * 1.2)` -- CPython's
                // asymmetric `min`, not `f64::min`.
                let priority = cpython_min2(1.0, score * 1.2);
                suggestions.push(Suggestion {
                    component_id: component_id.clone(),
                    current_position: *comp_pos,
                    suggested_position,
                    priority,
                });
            }
        }
    }

    Ok(suggestions)
}

/// One `AppliedAdjustment`, flattened to the 5-tuple the differential
/// projects.
type AppliedRow = (String, (f64, f64), (f64, f64), (f64, f64), f64);

/// `apply_suggestions_with_damping`'s filter-and-apply pass, plus
/// `AdjustmentResult.total_movement` computed in the same left-to-right order
/// the adjustments are produced in (which is the order `total_movement`'s
/// own `for adj in self.adjustments` loop would see).
fn apply_damping(
    suggestions: &[Suggestion],
    damping_factor: f64,
    min_priority_threshold: f64,
) -> PyResult<(Vec<AppliedRow>, f64)> {
    let mut adjustments = Vec::with_capacity(suggestions.len());
    let mut total_movement = 0.0;

    for s in suggestions {
        // `s.priority >= min_priority_threshold`, written as the positive
        // comparison the oracle itself performs. This is NOT the same test
        // as `s.priority < min_priority_threshold` when the threshold is
        // NaN: `priority >= NaN` is always false (skip, matching the
        // corpus's `(0.5, NaN)` case, where nothing is applied), while
        // `priority < NaN` is ALSO always false (which would wrongly keep
        // every suggestion). Written as a positive guard around the body,
        // rather than `if !(...) { continue }`, so clippy's
        // `neg_cmp_op_on_partial_ord` has nothing to flag -- the semantics
        // are unchanged either way.
        if s.priority >= min_priority_threshold {
            // `current_positions.get(comp_id) is None -> continue` in the
            // oracle. Unreachable here: `s.current_position` was itself read
            // from THIS SAME positions dict during generation (this
            // function is only ever called with the one dict the
            // differential passes for both steps -- see the module doc), so
            // every suggestion's component is provably present.
            let current_position = s.current_position;
            let applied_position =
                calculate_damped_position(current_position, s.suggested_position, damping_factor);

            let dx = applied_position.0 - current_position.0;
            let dy = applied_position.1 - current_position.1;
            total_movement += hypot_pow(dx, dy)?;

            adjustments.push((
                s.component_id.clone(),
                current_position,
                s.suggested_position,
                applied_position,
                damping_factor,
            ));
        }
    }

    Ok((adjustments, total_movement))
}

/// `apply_suggestions_with_damping`, given the regions its suggestions would
/// have been generated from rather than a pre-built `PlacementSuggestions`
/// (there is no shared Rust type for that yet; the two adapter arguments
/// fully determine it). Signs the 3-tuple
/// `(adjustments, adjustment_count, total_movement)` -- see the module doc
/// for why the sibling id-only projection cannot be satisfied by the same
/// function.
#[pyfunction]
#[pyo3(signature = (regions, current_positions, damping_factor=0.5, min_priority_threshold=0.5))]
pub fn apply_suggestions_damped_py<'py>(
    py: Python<'py>,
    regions: Vec<RegionRow>,
    current_positions: Bound<'py, PyDict>,
    damping_factor: f64,
    min_priority_threshold: f64,
) -> PyResult<Bound<'py, PyAny>> {
    let positions = extract_ordered_positions(&current_positions)?;
    let suggestions = generate_suggestions(&regions, &positions)?;
    let (adjustments, total_movement) =
        apply_damping(&suggestions, damping_factor, min_priority_threshold)?;
    let adjustment_count = adjustments.len() as i64;

    let out = (adjustments, adjustment_count, total_movement);
    Ok(out.into_pyobject(py)?.into_any())
}

/// `_calculate_damped_position`.
#[pyfunction]
pub fn apply_damped_position_py(current: (f64, f64), suggested: (f64, f64), damping: f64) -> (f64, f64) {
    calculate_damped_position(current, suggested, damping)
}

/// `AdjustmentResult.total_movement`.
///
/// `moves` is `[(original_position, applied_position), ...]`, one pair per
/// `AppliedAdjustment` -- the oracle test builds each adjustment with
/// `suggested_position == applied_position`, and `total_movement` never
/// reads `suggested_position`, so the pair fully determines it.
#[pyfunction]
pub fn apply_total_movement_py(moves: Vec<((f64, f64), (f64, f64))>) -> PyResult<f64> {
    let mut total = 0.0;
    for (original, applied) in moves {
        let dx = applied.0 - original.0;
        let dy = applied.1 - original.1;
        total += hypot_pow(dx, dy)?;
    }
    Ok(total)
}

/// `update_component_positions`.
///
/// `positions.copy()` then `updated[component_id] = applied_position` per
/// adjustment. Dict-assignment semantics matter for the returned iteration
/// order: an EXISTING key keeps its original position, a NEW key is
/// APPENDED, and the last write for a repeated key wins -- `PyDict::copy`
/// plus `PyDict::set_item` in a loop reproduce exactly that, so there is no
/// need to hand-roll ordered-map semantics.
#[pyfunction]
pub fn apply_update_positions_py<'py>(
    positions: Bound<'py, PyDict>,
    applied: Vec<(String, (f64, f64))>,
) -> PyResult<Bound<'py, PyDict>> {
    let updated = positions.copy()?;
    for (component_id, applied_position) in applied {
        updated.set_item(component_id, applied_position)?;
    }
    Ok(updated)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(apply_suggestions_damped_py, m)?)?;
    m.add_function(wrap_pyfunction!(apply_damped_position_py, m)?)?;
    m.add_function(wrap_pyfunction!(apply_total_movement_py, m)?)?;
    m.add_function(wrap_pyfunction!(apply_update_positions_py, m)?)?;
    Ok(())
}

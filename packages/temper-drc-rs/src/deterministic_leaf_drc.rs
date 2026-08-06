//! Deterministic DRC-check leaf compute — Wave 4 **Phase 5, batch 2**
//! (deterministic leaf stages, remaining slice).
//!
//! Ports the pure compute of the DRC-check leaf stages to this crate:
//!
//! | Python module | Rust function(s) |
//! |---|---|
//! | `deterministic/stages/drc_validation.py` | [`summarize_violations`] |
//! | `deterministic/stages/drc_sweep.py` (TrackDeduplicationStage) | [`deduplicate_traces`] |
//! | `deterministic/stages/placement_validation.py` | [`point_to_segment_distance`], [`validate_proximity`], [`validate_signal_hv`] |
//! | `deterministic/stages/courtyard_check.py` | [`clamp_position`] |
//!
//! The Python stages are delegation shims keeping their `run()` orchestration
//! (state guards, the `frozenset` wraps, the DRCOracle / shapely / router_v6
//! surfaces) in Python; the pre-migration implementations are pinned VERBATIM
//! as the differential oracles in `packages/temper-placer/tests/deterministic/stages/`
//! (`_*_py_oracle.py`); the structural proof lives in `VERIFICATION.md`.
//!
//! Numerical traps pinned here:
//! - `round(x / tol) * tol` in deduplication is CPython round-half-to-even
//!   followed by the product — NOT `f64::round` (half-away-from-zero).
//! - `(px - closest_x) ** 2` is libm `pow` (B7) and `math.sqrt` is the host
//!   libm, resolved via `pymath::{pow, sqrt}`.
//! - Python `max`/`min` keep the FIRST argument on ties (`pymath::py_max`).
//! - `:.1f` message formatting is delegated to CPython's `__format__` so the
//!   decimal rounding is Python's own.

use pyo3::prelude::*;
use pyo3::types::{PyList, PyString};

use crate::pymath::{pow, py_max, py_min, sqrt};

// ---------------------------------------------------------------------------
// drc_validation.py — violation summary
// ---------------------------------------------------------------------------

/// `_log_summary`'s counting: `{v.type: count}` with the summary rows
/// sorted by descending count (Python's stable `sorted(by_type.items(),
/// key=lambda x: -x[1])` — ties keep first-seen type order).
///
/// Returns `(total, [(type_str, count), ...])`.
pub fn summarize_violations(violations: &[String]) -> (usize, Vec<(String, usize)>) {
    let mut by_type: Vec<(String, usize)> = Vec::new();
    for t in violations {
        if let Some(entry) = by_type.iter_mut().find(|(k, _)| k == t) {
            entry.1 += 1;
        } else {
            by_type.push((t.clone(), 1));
        }
    }
    by_type.sort_by(|a, b| b.1.cmp(&a.1));
    (violations.len(), by_type)
}

/// Python-visible `summarize_violations(violations)`.
#[pyfunction]
pub fn summarize_violations_py<'py>(
    py: Python<'py>,
    violations: &Bound<'py, PyAny>,
) -> PyResult<(usize, Bound<'py, PyList>)> {
    let mut types: Vec<String> = Vec::new();
    for v in violations.try_iter()? {
        let v = v?;
        types.push(v.getattr("type")?.str()?.to_string());
    }
    let (total, rows) = summarize_violations(&types);
    let list = PyList::new(py, rows.iter().map(|(t, c)| (t.clone(), *c)))?;
    Ok((total, list))
}

/// Threshold decision of `DRCValidationStage.run`: returns `(should_raise,
/// message)` — the oracle raises when `fail_on_violations` and there is any
/// violation, or when `max_violations > 0` and the count exceeds it (the
/// `>` is strict — `max_violations == count` passes).
pub fn threshold_decision(
    fail_on_violations: bool,
    max_violations: i64,
    count: usize,
) -> (bool, String) {
    if fail_on_violations && count > 0 {
        return (true, format!("{count} DRC violations found"));
    }
    if max_violations > 0 && (count as i64) > max_violations {
        return (true, format!("{count} violations exceeds max {max_violations}"));
    }
    (false, String::new())
}

// ---------------------------------------------------------------------------
// drc_sweep.py — track deduplication
// ---------------------------------------------------------------------------

/// `TrackDeduplicationStage.run`'s key: normalize segment direction
/// (`(sx, sy) > (ex, ey)` tuple comparison), then
/// `round(coord / tol) * tol` for each endpoint coordinate, then the layer
/// and net. Returns the kept indices and the duplicate count.
#[allow(clippy::type_complexity)]
pub fn deduplicate_traces(
    traces: &[(f64, f64, f64, f64, String, Option<String>)],
    tolerance: f64,
) -> (Vec<usize>, usize) {
    let mut seen: std::collections::HashSet<(u64, u64, u64, u64, String, String)> =
        std::collections::HashSet::new();
    let mut kept: Vec<usize> = Vec::new();
    let mut duplicates = 0usize;

    for (i, (sx, sy, ex, ey, layer, net)) in traces.iter().enumerate() {
        let (mut sx, mut sy, mut ex, mut ey) = (*sx, *sy, *ex, *ey);
        if (sx, sy) > (ex, ey) {
            std::mem::swap(&mut sx, &mut ex);
            std::mem::swap(&mut sy, &mut ey);
        }
        let net_key = net.clone().unwrap_or_default();
        let key = (
            round_step(sx, tolerance).to_bits(),
            round_step(sy, tolerance).to_bits(),
            round_step(ex, tolerance).to_bits(),
            round_step(ey, tolerance).to_bits(),
            layer.clone(),
            net_key,
        );
        if !seen.insert(key) {
            duplicates += 1;
            continue;
        }
        kept.push(i);
    }
    (kept, duplicates)
}

/// `round(x / tol) * tol` — CPython round-half-to-even on `x / tol`, then
/// the float product.
fn round_step(x: f64, tol: f64) -> f64 {
    crate::pymath::py_round_to_int(x / tol) * tol
}

/// Python-visible `deduplicate_traces(traces, tolerance)` — traces is a
/// list of `(start, end, layer, net)` tuples; returns `(kept_indices, duplicates)`.
#[pyfunction]
pub fn deduplicate_traces_py<'py>(
    py: Python<'py>,
    traces: &Bound<'py, PyAny>,
    tolerance: f64,
) -> PyResult<(Bound<'py, PyList>, usize)> {
    let mut marshalled: Vec<(f64, f64, f64, f64, String, Option<String>)> = Vec::new();
    for t in traces.try_iter()? {
        let t = t?;
        let start = t.get_item(0)?;
        let end = t.get_item(1)?;
        let layer: String = t.get_item(2)?.str()?.to_string();
        let net_any = t.get_item(3)?;
        let net: Option<String> = if net_any.is_none() {
            None
        } else {
            Some(net_any.str()?.to_string())
        };
        marshalled.push((
            start.get_item(0)?.extract()?,
            start.get_item(1)?.extract()?,
            end.get_item(0)?.extract()?,
            end.get_item(1)?.extract()?,
            layer,
            net,
        ));
    }
    let (kept, duplicates) = deduplicate_traces(&marshalled, tolerance);
    let list = PyList::new(py, kept)?;
    Ok((list, duplicates))
}

// ---------------------------------------------------------------------------
// placement_validation.py — geometry + constraint kernels
// ---------------------------------------------------------------------------

/// `_point_to_segment_distance` — projection onto the segment with the
/// oracle's exact expression order: `dx*dx + dy*dy`, `max(0, min(1, t))`
/// via `py_max`/`py_min`, `(px - closest_x) ** 2` via libm `pow`, and
/// `math.sqrt`.
pub fn point_to_segment_distance(
    px: f64,
    py: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> f64 {
    let dx = x2 - x1;
    let dy = y2 - y1;
    let len_sq = dx * dx + dy * dy;
    if len_sq == 0.0 {
        return sqrt(pow(px - x1, 2.0) + pow(py - y1, 2.0));
    }
    let t = py_max(0.0, py_min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq));
    let closest_x = x1 + t * dx;
    let closest_y = y1 + t * dy;
    sqrt(pow(px - closest_x, 2.0) + pow(py - closest_y, 2.0))
}

/// Python-visible `point_to_segment_distance(point, seg_start, seg_end)`.
#[pyfunction]
pub fn point_to_segment_distance_py(
    point: (f64, f64),
    seg_start: (f64, f64),
    seg_end: (f64, f64),
) -> f64 {
    point_to_segment_distance(
        point.0, point.1, seg_start.0, seg_start.1, seg_end.0, seg_end.1,
    )
}

/// CPython `f"{value:.1f}"` — delegate to the float's own `__format__` so
/// the decimal rounding is Python's (Rust `{:.1}` can differ).
fn fmt_1f(py: Python<'_>, value: f64) -> PyResult<String> {
    let f = pyo3::types::PyFloat::new(py, value);
    let s: Py<PyString> = f.call_method1("__format__", (".1f",))?.extract()?;
    Ok(s.bind(py).to_string())
}

/// `_validate_proximity`: given the marshalled constraint fields and the
/// two pin positions (both present), return `(violation: bool, severity,
/// actual_distance_mm, message)` — `message` is empty when there is no
/// violation. The severity is `"error"` iff `tier == "hard"`.
#[allow(clippy::too_many_arguments)]
pub fn validate_proximity(
    name: &str,
    from_component: &str,
    from_pin: &str,
    to_component: &str,
    to_pin: &str,
    max_distance_mm: f64,
    tier: &str,
    from_pos: Option<(f64, f64)>,
    to_pos: Option<(f64, f64)>,
    py: Python<'_>,
) -> PyResult<(bool, String, f64, f64, String, String, String)> {
    // Returns (violation, severity, actual, required, message, comp_a, comp_b).
    let (fx, fy, tx, ty) = match (from_pos, to_pos) {
        (Some((fx, fy)), Some((tx, ty))) => (fx, fy, tx, ty),
        _ => {
            let msg = format!("Cannot validate {name}: component not found");
            return Ok((
                true,
                "warning".to_string(),
                0.0,
                0.0,
                msg,
                from_component.to_string(),
                to_component.to_string(),
            ));
        }
    };
    let distance = sqrt(pow(tx - fx, 2.0) + pow(ty - fy, 2.0));
    if distance > max_distance_mm {
        let severity: String = if tier == "hard" { "error".to_string() } else { "warning".to_string() };
        let msg = format!(
            "{}.{} is {}mm from {}.{} (max: {}mm)",
            from_component,
            from_pin,
            fmt_1f(py, distance)?,
            to_component,
            to_pin,
            fmt_1f(py, max_distance_mm)?,
        );
        Ok((true, severity.to_string(), distance, max_distance_mm, msg, from_component.to_string(), to_component.to_string()))
    } else {
        Ok((false, String::new(), distance, 0.0, String::new(), String::new(), String::new()))
    }
}

/// `_validate_signal_hv`: the two geometry checks — path length and the
/// per-HV-pin `_point_to_segment_distance` clearance — plus the message
/// construction. `hv_positions` is the list of `(pin_name, (x, y))`.
#[allow(clippy::too_many_arguments)]
pub fn validate_signal_hv(
    name: &str,
    signal_component: &str,
    signal_pin: &str,
    target_component: &str,
    target_pin: &str,
    hv_component: &str,
    required_clearance_mm: f64,
    max_path_length_mm: f64,
    tier: &str,
    signal_pos: Option<(f64, f64)>,
    target_pos: Option<(f64, f64)>,
    hv_positions: &[(String, (f64, f64))],
    py: Python<'_>,
) -> PyResult<(bool, String, f64, f64, String, String, String)> {
    let (sx, sy, tx, ty) = match (signal_pos, target_pos) {
        (Some((sx, sy)), Some((tx, ty))) => (sx, sy, tx, ty),
        _ => {
            let msg = format!("Cannot validate {name}: component not found");
            return Ok((
                true,
                "warning".to_string(),
                0.0,
                0.0,
                msg,
                String::new(),
                String::new(),
            ));
        }
    };
    let path_length = sqrt(pow(tx - sx, 2.0) + pow(ty - sy, 2.0));
    let severity: String = if tier == "hard" { "error".to_string() } else { "warning".to_string() };
    if path_length > max_path_length_mm {
        let msg = format!(
            "Signal path from {}.{} to {}.{} is {}mm (max: {}mm)",
            signal_component,
            signal_pin,
            target_component,
            target_pin,
            fmt_1f(py, path_length)?,
            fmt_1f(py, max_path_length_mm)?,
        );
        return Ok((true, severity, path_length, max_path_length_mm, msg, signal_component.to_string(), target_component.to_string()));
    }
    for (hv_pin, (hx, hy)) in hv_positions {
        let clearance = point_to_segment_distance(*hx, *hy, sx, sy, tx, ty);
        if clearance < required_clearance_mm {
            let msg = format!(
                "Signal path {}.{} -> {}.{} passes within {}mm of HV pin {}.{} (required: {}mm)",
                signal_component,
                signal_pin,
                target_component,
                target_pin,
                fmt_1f(py, clearance)?,
                hv_component,
                hv_pin,
                fmt_1f(py, required_clearance_mm)?,
            );
            return Ok((true, severity, clearance, required_clearance_mm, msg, signal_component.to_string(), hv_component.to_string()));
        }
    }
    Ok((false, String::new(), 0.0, 0.0, String::new(), String::new(), String::new()))
}

/// Python-visible `validate_proximity(constraint, from_pos, to_pos)` — the
/// constraint is any object exposing the oracle's attribute surface
/// (`name`, `from_component`, `from_pin`, `to_component`, `to_pin`,
/// `max_distance_mm`, `tier`); `from_pos`/`to_pos` are the PRE-RESOLVED pin
/// positions (the shim applies the `_get_pin_position` parsed-pads lookup
/// before delegating). Returns the violation 7-tuple or `None`.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn validate_proximity_py(
    py: Python<'_>,
    constraint: &Bound<'_, PyAny>,
    from_pos: Option<(f64, f64)>,
    to_pos: Option<(f64, f64)>,
) -> PyResult<Option<(bool, String, f64, f64, String, String, String)>> {
    let name: String = constraint.getattr("name")?.str()?.to_string();
    let from_component: String = constraint.getattr("from_component")?.str()?.to_string();
    let from_pin: String = constraint.getattr("from_pin")?.str()?.to_string();
    let to_component: String = constraint.getattr("to_component")?.str()?.to_string();
    let to_pin: String = constraint.getattr("to_pin")?.str()?.to_string();
    let max_distance_mm: f64 = constraint.getattr("max_distance_mm")?.extract()?;
    let tier: String = constraint.getattr("tier")?.str()?.to_string();

    let result = validate_proximity(
        &name, &from_component, &from_pin, &to_component, &to_pin,
        max_distance_mm, &tier, from_pos, to_pos, py,
    )?;
    Ok(Some(result))
}

/// Python-visible `validate_signal_hv(constraint, signal_pos, target_pos,
/// hv_positions)` — positions are PRE-RESOLVED by the shim (parsed-pads
/// lookup). Returns the violation 7-tuple or `None`.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn validate_signal_hv_py(
    py: Python<'_>,
    constraint: &Bound<'_, PyAny>,
    signal_pos: Option<(f64, f64)>,
    target_pos: Option<(f64, f64)>,
    hv_positions: &Bound<'_, PyAny>,
) -> PyResult<Option<(bool, String, f64, f64, String, String, String)>> {
    let name: String = constraint.getattr("name")?.str()?.to_string();
    let signal_component: String = constraint.getattr("signal_component")?.str()?.to_string();
    let signal_pin: String = constraint.getattr("signal_pin")?.str()?.to_string();
    let target_component: String = constraint.getattr("target_component")?.str()?.to_string();
    let target_pin: String = constraint.getattr("target_pin")?.str()?.to_string();
    let hv_component: String = constraint.getattr("hv_component")?.str()?.to_string();
    let required_clearance_mm: f64 = constraint.getattr("required_clearance_mm")?.extract()?;
    let max_path_length_mm: f64 = constraint.getattr("max_path_length_mm")?.extract()?;
    let tier: String = constraint.getattr("tier")?.str()?.to_string();

    let mut hv_pos: Vec<(String, (f64, f64))> = Vec::new();
    for item in hv_positions.try_iter()? {
        let item = item?;
        let pin_name: String = item.get_item(0)?.str()?.to_string();
        let pos = item.get_item(1)?;
        hv_pos.push((pin_name, (pos.get_item(0)?.extract()?, pos.get_item(1)?.extract()?)));
    }
    let result = validate_signal_hv(
        &name, &signal_component, &signal_pin, &target_component, &target_pin,
        &hv_component, required_clearance_mm, max_path_length_mm, &tier,
        signal_pos, target_pos, &hv_pos, py,
    )?;
    Ok(Some(result))
}

// ---------------------------------------------------------------------------
// courtyard_check.py — position clamping
// ---------------------------------------------------------------------------

/// `CourtyardCheckStage._clamp_position`: clamp each coordinate to
/// `[margin, dim - margin]` via Python `max`/`min` (first-arg-on-ties).
pub fn clamp_position(x: f64, y: f64, margin: f64, board_width: f64, board_height: f64) -> (f64, f64) {
    let x_min = margin;
    let x_max = board_width - margin;
    let y_min = margin;
    let y_max = board_height - margin;
    (
        py_max(x_min, py_min(x_max, x)),
        py_max(y_min, py_min(y_max, y)),
    )
}

/// Python-visible `clamp_position(x, y, margin, board_width, board_height)`.
#[pyfunction]
pub fn clamp_position_py(
    x: f64,
    y: f64,
    margin: f64,
    board_width: f64,
    board_height: f64,
) -> (f64, f64) {
    clamp_position(x, y, margin, board_width, board_height)
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Register the leaf DRC-check kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(summarize_violations_py, m)?)?;
    m.add_function(wrap_pyfunction!(deduplicate_traces_py, m)?)?;
    m.add_function(wrap_pyfunction!(point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(validate_proximity_py, m)?)?;
    m.add_function(wrap_pyfunction!(validate_signal_hv_py, m)?)?;
    m.add_function(wrap_pyfunction!(clamp_position_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn summarize_violations_orders_by_count_desc() {
        let (total, rows) = summarize_violations(&[
            "a".into(), "b".into(), "a".into(), "c".into(), "a".into(),
        ]);
        assert_eq!(total, 5);
        assert_eq!(rows, vec![("a".to_string(), 3), ("b".to_string(), 1), ("c".to_string(), 1)]);
        let (t, r) = summarize_violations(&[]);
        assert_eq!(t, 0);
        assert!(r.is_empty());
    }

    #[test]
    fn dedup_normalizes_direction_and_rounds() {
        let traces = vec![
            (0.0, 0.0, 10.0, 0.0, "0".to_string(), Some("A".to_string())),
            (10.0, 0.0, 0.0, 0.0, "0".to_string(), Some("A".to_string())), // reversed duplicate
            (0.0, 0.0, 10.0, 0.0, "0".to_string(), Some("B".to_string())), // different net
            (0.04, 0.0, 10.0, 0.0, "0".to_string(), Some("A".to_string())), // within tol
        ];
        let (kept, dup) = deduplicate_traces(&traces, 0.05);
        assert_eq!(dup, 1);
        assert_eq!(kept.len(), 3);
    }

    #[test]
    fn point_to_segment_distance_cases() {
        // Zero-length segment: distance to the single point.
        let d0 = point_to_segment_distance(3.0, 4.0, 1.0, 1.0, 1.0, 1.0);
        assert_eq!(d0, sqrt(pow(2.0, 2.0) + pow(3.0, 2.0)));
        // Perpendicular foot inside the segment.
        let d = point_to_segment_distance(2.0, 3.0, 0.0, 0.0, 4.0, 0.0);
        assert_eq!(d, 3.0);
        // Foot beyond the end -> distance to the end point.
        let d2 = point_to_segment_distance(6.0, 3.0, 0.0, 0.0, 4.0, 0.0);
        assert_eq!(d2, sqrt(pow(2.0, 2.0) + pow(3.0, 2.0)));
    }

    #[test]
    fn clamp_position_bounds() {
        assert_eq!(clamp_position(200.0, -5.0, 5.0, 100.0, 150.0), (95.0, 5.0));
        assert_eq!(clamp_position(50.0, 75.0, 5.0, 100.0, 150.0), (50.0, 75.0));
    }
}

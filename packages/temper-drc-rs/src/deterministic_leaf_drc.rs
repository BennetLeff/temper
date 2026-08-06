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
use pyo3::types::{PyDict, PyList, PyString};

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

/// Python-visible `threshold_decision(fail_on_violations, max_violations,
/// count)` — wired into `DRCValidationStage.run` so the raise decision is
/// the migrated kernel, not a parallel Python copy.
#[pyfunction]
pub fn threshold_decision_py(
    fail_on_violations: bool,
    max_violations: i64,
    count: usize,
) -> (bool, String) {
    threshold_decision(fail_on_violations, max_violations, count)
}

// ---------------------------------------------------------------------------
// drc_sweep.py — track deduplication
// ---------------------------------------------------------------------------

/// `TrackDeduplicationStage.run`'s key: normalize segment direction
/// (`(sx, sy) > (ex, ey)` tuple comparison), then
/// `round(coord / tol) * tol` for each endpoint coordinate, then the layer
/// and net. Returns the kept indices and the duplicate count.
///
/// The net key is the marshalled `Option<String>` verbatim: the oracle keys
/// on `net` directly, so `None` and `Some("")` are DISTINCT keys (a
/// `unwrap_or_default` collapse would dedup a pair the oracle keeps).
#[allow(clippy::type_complexity)]
pub fn deduplicate_traces(
    traces: &[(f64, f64, f64, f64, String, Option<String>)],
    tolerance: f64,
) -> (Vec<usize>, usize) {
    let mut seen: std::collections::HashSet<(u64, u64, u64, u64, String, Option<String>)> =
        std::collections::HashSet::new();
    let mut kept: Vec<usize> = Vec::new();
    let mut duplicates = 0usize;

    for (i, (sx, sy, ex, ey, layer, net)) in traces.iter().enumerate() {
        let (mut sx, mut sy, mut ex, mut ey) = (*sx, *sy, *ex, *ey);
        if (sx, sy) > (ex, ey) {
            std::mem::swap(&mut sx, &mut ex);
            std::mem::swap(&mut sy, &mut ey);
        }
        let key = (
            round_step(sx, tolerance).to_bits(),
            round_step(sy, tolerance).to_bits(),
            round_step(ex, tolerance).to_bits(),
            round_step(ey, tolerance).to_bits(),
            layer.clone(),
            net.clone(),
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
///
/// The oracle's guard ordering is preserved: with no resolved HV pin there is
/// nothing to check against, so a no-violation is returned BEFORE the
/// path-length check (an over-long signal path alone yields no violation when
/// `hv_positions` is empty).
///
/// The final element is the explicit violation kind (`"missing_component"`,
/// `"path_too_long"`, `"hv_clearance"`, or `""` for no violation) — the shim
/// must not re-infer the kind from message text.
#[allow(clippy::too_many_arguments)]
#[allow(clippy::type_complexity)]
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
) -> PyResult<(bool, String, f64, f64, String, String, String, String)> {
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
                "missing_component".to_string(),
            ));
        }
    };
    if hv_positions.is_empty() {
        return Ok((
            false,
            String::new(),
            0.0,
            0.0,
            String::new(),
            String::new(),
            String::new(),
            String::new(),
        ));
    }
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
        return Ok((true, severity, path_length, max_path_length_mm, msg, signal_component.to_string(), target_component.to_string(), "path_too_long".to_string()));
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
            return Ok((true, severity, clearance, required_clearance_mm, msg, signal_component.to_string(), hv_component.to_string(), "hv_clearance".to_string()));
        }
    }
    Ok((false, String::new(), 0.0, 0.0, String::new(), String::new(), String::new(), String::new()))
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
/// lookup). Returns the violation 8-tuple (kind as the final element) or
/// `None`.
#[pyfunction]
#[allow(clippy::type_complexity)]
pub fn validate_signal_hv_py(
    py: Python<'_>,
    constraint: &Bound<'_, PyAny>,
    signal_pos: Option<(f64, f64)>,
    target_pos: Option<(f64, f64)>,
    hv_positions: &Bound<'_, PyAny>,
) -> PyResult<Option<(bool, String, f64, f64, String, String, String, String)>> {
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
// via_validation.py — via connectivity + position-dedup kernels
// ---------------------------------------------------------------------------

/// `ViaValidationStage._count_connected_layers` — the per-layer trace/pin
/// distance sweep.
///
/// Mirrors the oracle exactly: `tol_sq = tol * tol` is a PLAIN MULTIPLY while
/// every distance term is `(vx - tx) ** 2` (libm `pow` via
/// [`crate::pymath::pow`]), the plane-layer auto-connect short-circuits only
/// when `is_plane`, the trace sweep `break`s on the first hit, and the pin
/// sweep is skipped for a layer the trace sweep already connected (`layer not
/// in connected_layers`). Returns the count of distinct connected layers.
pub fn count_connected_layers(
    via_position: (f64, f64),
    via_layers: &[String],
    tolerance: f64,
    trace_index: &std::collections::HashMap<String, Vec<(f64, f64)>>,
    pin_index: &std::collections::HashMap<String, Vec<(f64, f64)>>,
    is_plane: bool,
    plane_layers: &std::collections::HashSet<String>,
) -> usize {
    let (vx, vy) = via_position;
    let tol_sq = tolerance * tolerance;
    let mut connected_layers: std::collections::HashSet<String> = std::collections::HashSet::new();

    for layer in via_layers {
        if is_plane && plane_layers.contains(layer) {
            connected_layers.insert(layer.clone());
            continue;
        }

        if let Some(pts) = trace_index.get(layer) {
            for &(tx, ty) in pts {
                let dist_sq = pow(vx - tx, 2.0) + pow(vy - ty, 2.0);
                if dist_sq <= tol_sq {
                    connected_layers.insert(layer.clone());
                    break;
                }
            }
        }

        if !connected_layers.contains(layer) {
            if let Some(pts) = pin_index.get(layer) {
                for &(px, py) in pts {
                    let dist_sq = pow(vx - px, 2.0) + pow(vy - py, 2.0);
                    if dist_sq <= tol_sq {
                        connected_layers.insert(layer.clone());
                        break;
                    }
                }
            }
        }
    }

    connected_layers.len()
}

/// Python-visible `count_connected_layers_py(via_position, via_layers,
/// tolerance, trace_index, pin_index, is_plane, plane_layers)`.
#[allow(clippy::too_many_arguments)]
#[pyfunction]
pub fn count_connected_layers_py(
    via_position: (f64, f64),
    via_layers: &Bound<'_, PyAny>,
    tolerance: f64,
    trace_index: &Bound<'_, PyDict>,
    pin_index: &Bound<'_, PyDict>,
    is_plane: bool,
    plane_layers: &Bound<'_, PyAny>,
) -> PyResult<usize> {
    let layers: Vec<String> = via_layers
        .try_iter()?
        .map(|i| i.and_then(|x| x.extract::<String>()))
        .collect::<PyResult<_>>()?;
    let plane_set: std::collections::HashSet<String> = plane_layers
        .try_iter()?
        .map(|i| i.and_then(|x| x.extract::<String>()))
        .collect::<PyResult<_>>()?;
    let trace_map = points_index(trace_index)?;
    let pin_map = points_index(pin_index)?;
    Ok(count_connected_layers(
        via_position, &layers, tolerance, &trace_map, &pin_map, is_plane, &plane_set,
    ))
}

/// Marshal `{layer: [ (x, y), ... ]}` into a Rust map.
fn points_index(
    index: &Bound<'_, PyDict>,
) -> PyResult<std::collections::HashMap<String, Vec<(f64, f64)>>> {
    let mut out: std::collections::HashMap<String, Vec<(f64, f64)>> =
        std::collections::HashMap::new();
    for (layer, pts) in index.iter() {
        let layer: String = layer.extract()?;
        let mut coords: Vec<(f64, f64)> = Vec::new();
        for pt_item in pts.try_iter()? {
            let pt: Bound<'_, PyAny> = pt_item?;
            coords.push((pt.get_item(0)?.extract()?, pt.get_item(1)?.extract()?));
        }
        out.insert(layer, coords);
    }
    Ok(out)
}

/// `ViaDeduplicationStage.run`'s position-dedup sweep.
///
/// First-seen-wins in INPUT order with `tol_sq = tolerance ** 2` (libm `pow`,
/// NOT a plain multiply — a distinct pin from `_count_connected_layers`),
/// `<=` boundary, one `duplicates` increment per rejected position. Returns
/// `(kept_indices, duplicates)` so the shim can recover the ORIGINAL via
/// objects by index (object identity matters when two vias share an exact
/// position).
pub fn dedup_via_positions(
    positions: &[(f64, f64)],
    tolerance: f64,
) -> (Vec<usize>, usize) {
    let tol_sq = pow(tolerance, 2.0);
    let mut kept: Vec<usize> = Vec::new();
    let mut seen: Vec<(f64, f64)> = Vec::new();
    let mut duplicates = 0usize;

    for (i, &(vx, vy)) in positions.iter().enumerate() {
        let mut is_duplicate = false;
        for &(sx, sy) in &seen {
            let dist_sq = pow(vx - sx, 2.0) + pow(vy - sy, 2.0);
            if dist_sq <= tol_sq {
                is_duplicate = true;
                duplicates += 1;
                break;
            }
        }
        if !is_duplicate {
            kept.push(i);
            seen.push((vx, vy));
        }
    }

    (kept, duplicates)
}

/// Python-visible `dedup_via_positions_py(positions, tolerance)` returning
/// `(kept_indices, duplicates)`.
#[pyfunction]
pub fn dedup_via_positions_py<'py>(
    py: Python<'py>,
    positions: &Bound<'py, PyAny>,
    tolerance: f64,
) -> PyResult<(Bound<'py, PyList>, usize)> {
    let mut coords: Vec<(f64, f64)> = Vec::new();
    for pos in positions.try_iter()? {
        let pos = pos?;
        coords.push((pos.get_item(0)?.extract()?, pos.get_item(1)?.extract()?));
    }
    let (kept, duplicates) = dedup_via_positions(&coords, tolerance);
    let list = PyList::new(py, kept)?;
    Ok((list, duplicates))
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Register the leaf DRC-check kernels on the `temper_drc_rs` module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(summarize_violations_py, m)?)?;
    m.add_function(wrap_pyfunction!(threshold_decision_py, m)?)?;
    m.add_function(wrap_pyfunction!(deduplicate_traces_py, m)?)?;
    m.add_function(wrap_pyfunction!(point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(validate_proximity_py, m)?)?;
    m.add_function(wrap_pyfunction!(validate_signal_hv_py, m)?)?;
    m.add_function(wrap_pyfunction!(clamp_position_py, m)?)?;
    m.add_function(wrap_pyfunction!(count_connected_layers_py, m)?)?;
    m.add_function(wrap_pyfunction!(dedup_via_positions_py, m)?)?;
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
    fn dedup_none_and_empty_net_are_distinct_keys() {
        // The oracle keys on `net` directly: None and '' must NOT collapse.
        let traces = vec![
            (0.0, 0.0, 10.0, 0.0, "0".to_string(), None),
            (0.0, 0.0, 10.0, 0.0, "0".to_string(), Some(String::new())),
        ];
        let (kept, dup) = deduplicate_traces(&traces, 0.05);
        assert_eq!(dup, 0);
        assert_eq!(kept, vec![0, 1]);
    }

    #[test]
    fn threshold_strict_greater_than() {
        assert_eq!(threshold_decision(true, 0, 1), (true, "1 DRC violations found".into()));
        assert_eq!(threshold_decision(true, 0, 0), (false, String::new()));
        assert_eq!(threshold_decision(false, 3, 4), (true, "4 violations exceeds max 3".into()));
        // Strict `>`: count == max_violations passes.
        assert_eq!(threshold_decision(false, 3, 3), (false, String::new()));
        assert_eq!(threshold_decision(false, 3, 2), (false, String::new()));
    }

    #[test]
    fn signal_hv_empty_hv_guard_before_path_length() {
        // An over-long signal path with no resolved HV pin yields no violation
        // (oracle returns None before the path-length check).
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let result = validate_signal_hv(
                "S", "U1", "1", "U2", "2", "MISSING", 6.0, 10.0, "hard",
                Some((0.0, 0.0)), Some((50.0, 0.0)), &[], py,
            )
            .unwrap_or_else(|e| panic!("validate_signal_hv failed: {e}"));
            assert!(!result.0);
            assert_eq!(result.1, "");
        });
    }

    #[test]
    fn signal_hv_kind_is_explicit_not_inferred() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            // missing_component
            let r = validate_signal_hv(
                "S", "U1", "1", "MISSING", "2", "Q1", 6.0, 50.0, "hard",
                Some((0.0, 0.0)), None, &[("3".into(), (25.0, 0.0))], py,
            )
            .unwrap_or_else(|e| panic!("validate_signal_hv failed: {e}"));
            assert_eq!(r.7, "missing_component");
            // path_too_long
            let r = validate_signal_hv(
                "S", "U1", "1", "U2", "2", "Q1", 6.0, 10.0, "hard",
                Some((0.0, 0.0)), Some((50.0, 0.0)), &[("3".into(), (25.0, 1.0))], py,
            )
            .unwrap_or_else(|e| panic!("validate_signal_hv failed: {e}"));
            assert!(r.0);
            assert_eq!(r.7, "path_too_long");
            // hv_clearance
            let r = validate_signal_hv(
                "S", "U1", "1", "U2", "2", "Q1", 6.0, 50.0, "hard",
                Some((0.0, 0.0)), Some((50.0, 0.0)), &[("3".into(), (25.0, 0.5))], py,
            )
            .unwrap_or_else(|e| panic!("validate_signal_hv failed: {e}"));
            assert!(r.0);
            assert_eq!(r.7, "hv_clearance");
            // no violation
            let r = validate_signal_hv(
                "S", "U1", "1", "U2", "2", "Q1", 6.0, 50.0, "hard",
                Some((0.0, 0.0)), Some((50.0, 0.0)), &[("3".into(), (25.0, 30.0))], py,
            )
            .unwrap_or_else(|e| panic!("validate_signal_hv failed: {e}"));
            assert!(!r.0);
            assert_eq!(r.7, "");
        });
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

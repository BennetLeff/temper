//! Deterministic leaf-stage compute — Wave 4 **Phase 5, final leaves**.
//!
//! Ports the remaining pure compute of the deterministic helper/stage files to
//! Rust:
//!
//! | Python module | Rust function(s) |
//! |---|---|
//! | `deterministic/stages/_phase_core.py` | [`effective_ghost_pad_radius`] (formerly `_phase_rotation.py`), [`compute_wirelength`] (formerly `_phase_zones.py`), [`find_critical_bottleneck_violations`] (formerly `_phase_validation.py`); the four `_phase_*` mixin modules were collapsed into `_phase_core.py` 2026-08-20 |
//! | `deterministic/stages/zone_aware_slot_generation.py` | [`point_in_polygon`], [`slot_intersects_iso`], [`min_distance_to_polygon`] (over temper-geometry's canonical point-to-segment kernel, issue #987) |
//!
//! The pre-migration implementations are pinned VERBATIM as the differential
//! oracles in `packages/temper-placer/tests/deterministic/stages/`
//! (`_phase_rotation_py_oracle.py`, `_phase_zones_py_oracle.py`,
//! `_phase_validation_py_oracle.py`,
//! `_zone_aware_slot_generation_py_oracle.py`); the Python mixins/stages become
//! delegation shims that keep their orchestration (state guards, GEOS/shapely
//! and ConstraintCompiler-bound surfaces) in Python. Bit-exactness is asserted
//! by the `test_*_rust_differential.py` suites and the PBT suites; the
//! structural proof lives in `VERIFICATION.md`.
//!
//! # Numerical traps pinned here (see the differentials)
//!
//! - **`math.hypot` is NOT libm `hypot`**: CPython's `math.hypot` is a Dekker
//!   double-double `vector_norm`; [`effective_ghost_pad_radius`] uses
//!   [`crate::host_math::hypot`], and the differential pins the known
//!   last-ulp divergence operand pair.
//! - **`** 0.5` is libm `pow`, NOT `sqrt`**: the Wave-4
//!   `point_to_segment_distance` reimplementation used to close with
//!   `pow(pow(px-cx, 2.0) + pow(py-cy, 2.0), 0.5)`; `sqrt` and `pow(_, 0.5)`
//!   differ by 1 ulp on a measurable input class (pinned by
//!   `test_ptsd_pow_vs_sqrt_discriminating_operand`). That kernel was
//!   DELETED on 2026-08-11 (issue #987); [`min_distance_to_polygon`] now
//!   delegates to temper-geometry's canonical hypot contract (see
//!   `docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md`).
//! - **`bn.severity` reads the LAST bottleneck** in
//!   [`find_critical_bottleneck_violations`]: the violation dict's `severity`
//!   key is the first loop's trailing `bn`, NOT the matched cell — pinned
//!   verbatim (a "corrected" `cell_bn.severity` diverges).
//! - **CPython floor semantics**: grid indices are
//!   `floor((x_mm * 1000.0) / cell_um)` with NaN -> `ValueError` and ±inf ->
//!   `OverflowError` matching `math.floor`'s exact failure modes.
//! - **CPython `min`/`max` are first-argument-on-ties folds** (NaN stays the
//!   running value only when it is first); the HPWL and polygon kernels use
//!   `py_min`/`py_max` folds, never `f64::min`/`f64::max`.

use std::collections::HashMap;
use std::panic::AssertUnwindSafe;

use pyo3::exceptions::{PyOverflowError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::host_math::{py_max, py_min};

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

// ---------------------------------------------------------------------------
// _phase_core.py (merged from _phase_rotation.py 2026-08-20) —
// effective_ghost_pad_radius (U2 isolation-slot kernel)
// ---------------------------------------------------------------------------

/// `_PhaseHVMixin._effective_ghost_pad_radius` — the U2 isolation-slot
/// reduction kernel (IEC 62368-1 Annex G projection).
///
/// Mirrors the oracle exactly: `math.hypot(dx, dy)` (Dekker vector_norm,
/// NOT libm hypot), unit vector `dx / d_len, dy / d_len` with the
/// `d_len <= 0.0` early-out, naive `reduction += projection` accumulation
/// over strict-positive projections, and `max(0.0, base - reduction)`.
///
/// Slots arrive as flattened `(sx0, sy0, sx1, sy1)` tuples; the NFR4
/// `use_isolation_slots` toggle and the per-ref slot lookup stay in the shim.
pub fn effective_ghost_pad_radius(
    base_radius: f64,
    current_pin_absolute: (f64, f64),
    nearest_other_hv_pin_absolute: (f64, f64),
    slots: &[(f64, f64, f64, f64)],
) -> f64 {
    let dx = nearest_other_hv_pin_absolute.0 - current_pin_absolute.0;
    let dy = nearest_other_hv_pin_absolute.1 - current_pin_absolute.1;
    let d_len = crate::host_math::hypot(dx, dy);
    if d_len <= 0.0 {
        return base_radius;
    }
    let ux = dx / d_len;
    let uy = dy / d_len;

    let mut reduction = 0.0;
    for &(sx0, sy0, sx1, sy1) in slots {
        let sdx = sx1 - sx0;
        let sdy = sy1 - sy0;
        let projection = sdx * ux + sdy * uy;
        if projection > 0.0 {
            reduction += projection;
        }
    }
    py_max(0.0, base_radius - reduction)
}

/// Python-visible `effective_ghost_pad_radius(base_radius, current_pin,
/// nearest_other_pin, slots)`.
#[pyfunction]
pub fn effective_ghost_pad_radius_py(
    base_radius: f64,
    current_pin_absolute: (f64, f64),
    nearest_other_hv_pin_absolute: (f64, f64),
    slots: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    guard(|| {
        let mut flat: Vec<(f64, f64, f64, f64)> = Vec::new();
        for slot in slots.try_iter()? {
            let slot = slot?;
            flat.push((
                slot.get_item(0)?.extract()?,
                slot.get_item(1)?.extract()?,
                slot.get_item(2)?.extract()?,
                slot.get_item(3)?.extract()?,
            ));
        }
        Ok(effective_ghost_pad_radius(
            base_radius,
            current_pin_absolute,
            nearest_other_hv_pin_absolute,
            &flat,
        ))
    })
}

// ---------------------------------------------------------------------------
// _phase_core.py (merged from _phase_zones.py 2026-08-20) —
// compute_wirelength (HPWL)
// ---------------------------------------------------------------------------

/// CPython `min(iterable)` as a fold: the FIRST minimal element wins on ties,
/// and a NaN is only the result if it is the first element (a later NaN does
/// not replace the running value because `nan < best` is false).
fn py_list_min(vals: &[f64]) -> f64 {
    let mut best = vals[0];
    for &v in &vals[1..] {
        if v < best {
            best = v;
        }
    }
    best
}

/// CPython `max(iterable)` as a fold (see [`py_list_min`]).
fn py_list_max(vals: &[f64]) -> f64 {
    let mut best = vals[0];
    for &v in &vals[1..] {
        if v > best {
            best = v;
        }
    }
    best
}

/// `_PhasePlacementMixin._compute_wirelength` — HPWL over the nets the
/// component participates in.
///
/// For each net containing `component_ref`, the positions list is
/// `[candidate_slot]` plus every already-placed other ref in net_pins LIST
/// order (a ref listed on two pins appends twice — NOT deduplicated). A net
/// contributes nothing when that list has one element. HPWL is
/// `(max(xs) - min(xs)) + (max(ys) - min(ys))`; the fold is a plain
/// `total_hpwl += hpwl`.
///
/// `net_pins` is the LIST of per-net member lists: the net NAMES are never
/// read by the kernel (the oracle iterates `net_pins.items()` but only uses
/// the values), so the marshaler may pass opaque-key dicts (the unit suite
/// drives this with Mock net objects).
pub fn compute_wirelength(
    component_ref: &str,
    candidate_slot: (f64, f64),
    net_pins: &[Vec<(String, String)>],
    current_placements: &HashMap<String, (f64, f64)>,
) -> f64 {
    let mut total_hpwl = 0.0;
    for pins in net_pins {
        let component_on_net = pins.iter().any(|(ref_, _)| ref_ == component_ref);
        if !component_on_net {
            continue;
        }
        let mut positions: Vec<(f64, f64)> = vec![candidate_slot];
        for (ref_, _) in pins {
            if ref_ != component_ref
                && let Some(p) = current_placements.get(ref_)
            {
                positions.push(*p);
            }
        }
        if positions.len() > 1 {
            let xs: Vec<f64> = positions.iter().map(|p| p.0).collect();
            let ys: Vec<f64> = positions.iter().map(|p| p.1).collect();
            let hpwl = (py_list_max(&xs) - py_list_min(&xs)) + (py_list_max(&ys) - py_list_min(&ys));
            total_hpwl += hpwl;
        }
    }
    total_hpwl
}

/// Python-visible `compute_wirelength(component_ref, candidate_slot, net_pins,
/// current_placements)`.
#[pyfunction]
pub fn compute_wirelength_py<'py>(
    component_ref: &str,
    candidate_slot: &Bound<'py, PyAny>,
    net_pins: &Bound<'py, PyDict>,
    current_placements: &Bound<'py, PyDict>,
) -> PyResult<f64> {
    guard(|| {
        // candidate_slot is extracted INDEX-wise (tuple OR list), matching the
        // oracle's `positions = [candidate_slot]` + `p[0]` subscripting — a
        // 2-element LIST is accepted, a bare tuple extraction would reject it.
        let candidate: (f64, f64) = (
            candidate_slot.get_item(0)?.extract()?,
            candidate_slot.get_item(1)?.extract()?,
        );

        let mut lists: Vec<Vec<(String, String)>> = Vec::new();
        for pins in net_pins.values() {
            let mut members: Vec<(String, String)> = Vec::new();
            for pin in pins.try_iter()? {
                let pin = pin?;
                // The oracle unpacks `for ref, _ in pins:` — a 3-element pin
                // raises ValueError (a too-lenient marshaler silently drops
                // element 2), and a 1-element pin raises ValueError too.
                let n = pin.len()?;
                if n < 2 {
                    return Err(PyValueError::new_err(format!(
                        "not enough values to unpack (expected 2, got {n})"
                    )));
                }
                if n > 2 {
                    return Err(PyValueError::new_err(
                        "too many values to unpack (expected 2)",
                    ));
                }
                members.push((pin.get_item(0)?.extract()?, pin.get_item(1)?.extract()?));
            }
            lists.push(members);
        }
        let mut cp: HashMap<String, (f64, f64)> = HashMap::new();
        for (ref_, pos) in current_placements.iter() {
            let ref_: String = ref_.extract()?;
            let x: f64 = pos.get_item(0)?.extract()?;
            let y: f64 = pos.get_item(1)?.extract()?;
            cp.insert(ref_, (x, y));
        }
        Ok(compute_wirelength(component_ref, candidate, &lists, &cp))
    })
}

// ---------------------------------------------------------------------------
// _phase_core.py (merged from _phase_validation.py 2026-08-20) —
// find_critical_bottleneck_violations
// ---------------------------------------------------------------------------

/// CPython `int(math.floor((x_mm * 1000.0) / cell_um))`, with `math.floor`'s
/// exact failure modes: NaN quotient -> ValueError, ±inf -> OverflowError.
///
/// Values whose floor exceeds i64 saturate — which is behaviorally identical
/// here because a saturated index is always out of the (real) board bounds
/// and therefore skipped, exactly as the oracle's big-Python-int would be.
fn grid_index(mm: f64, cell_um: f64) -> PyResult<i64> {
    let q = (mm * 1000.0) / cell_um;
    if q.is_nan() {
        return Err(PyValueError::new_err("cannot convert float NaN to integer"));
    }
    if q.is_infinite() {
        return Err(PyOverflowError::new_err(
            "cannot convert float infinity to integer",
        ));
    }
    Ok(q.floor() as i64)
}

/// `_PhaseValidationMixin.find_critical_bottleneck_violations` — the
/// critical-cell invariant check.
///
/// Verbatim quirk pinned: the violation's `severity` is `bn.severity` where
/// `bn` is the first loop's trailing variable — the severity of the LAST
/// bottleneck in the input list, NOT the matched cell's severity.
///
/// Bottlenecks arrive as flattened `(x, y, layer, severity, score)` tuples;
/// placements as `(ref, Some((x_mm, y_mm)))` (None = skipped non-coordinate
/// value). Returns `(ref, gx, gy, layer, severity)` tuples in placements
/// dict order.
#[allow(clippy::type_complexity)]
pub fn find_critical_bottleneck_violations(
    placements: &[(String, Option<(f64, f64)>)],
    bottlenecks: &[(i64, i64, String, String, f64)],
    cell_um: f64,
    width: f64,
    height: f64,
) -> PyResult<Vec<(String, i64, i64, String, String)>> {
    let mut critical_by_cell: HashMap<(i64, i64), (String, f64)> = HashMap::new();
    let mut last_severity: Option<String> = None;
    for (bx, by, layer, severity, score) in bottlenecks {
        last_severity = Some(severity.clone());
        if severity != "CRITICAL" {
            continue;
        }
        let key = (*bx, *by);
        // The oracle's `existing is None or bn.score > existing.score` with
        // the FIRST bottleneck kept on score ties.
        let replaces = match critical_by_cell.get(&key) {
            Some((_, existing_score)) => *score > *existing_score,
            None => true,
        };
        if replaces {
            critical_by_cell.insert(key, (layer.clone(), *score));
        }
    }

    let mut out: Vec<(String, i64, i64, String, String)> = Vec::new();
    for (ref_, pos) in placements {
        let Some((x_mm, y_mm)) = pos else { continue };
        let gx = grid_index(*x_mm, cell_um)?;
        let gy = grid_index(*y_mm, cell_um)?;
        // The oracle compares `gx < 0 or gx >= width` with Python int-vs-int
        // (or int-vs-float when a float width is passed); `(gx as f64) >=
        // width` is the same promotion.
        if gx < 0 || (gx as f64) >= width || gy < 0 || (gy as f64) >= height {
            continue;
        }
        if let Some((layer, _)) = critical_by_cell.get(&(gx, gy)) {
            out.push((
                ref_.clone(),
                gx,
                gy,
                layer.clone(),
                last_severity.clone().unwrap_or_default(),
            ));
        }
    }
    Ok(out)
}

/// CPython `float(x)` — the oracle's explicit placement-coordinate coercion
/// (`float(x_mm) * 1000.0 / cell_um`). Accepts int, float and numeric str;
/// rejects everything else with the error CPython's `float()` raises. A bare
/// pyo3 `extract::<f64>()` would raise TypeError on a numeric str, diverging
/// from the oracle.
fn py_float_coerce<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<f64> {
    let float_ctor = py.import("builtins")?.getattr("float")?;
    float_ctor.call1((value,))?.extract()
}

/// Python-visible `find_critical_bottleneck_violations(placements,
/// bottlenecks, cell_um, width, height)` returning a list of dicts.
#[pyfunction]
pub fn find_critical_bottleneck_violations_py<'py>(
    py: Python<'py>,
    placements: &Bound<'py, PyDict>,
    bottlenecks: &Bound<'py, PyAny>,
    cell_um: f64,
    width: &Bound<'py, PyAny>,
    height: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    guard(|| {
        // width/height extract as f64 (int OR float), matching the oracle's
        // `gx >= width` int-vs-(int|float) comparison; a str still raises
        // TypeError exactly as `int >= str` does in Python.
        let width: f64 = width.extract()?;
        let height: f64 = height.extract()?;

        let mut bns: Vec<(i64, i64, String, String, f64)> = Vec::new();
        for bn in bottlenecks.try_iter()? {
            let bn = bn?;
            bns.push((
                bn.get_item(0)?.extract()?,
                bn.get_item(1)?.extract()?,
                bn.get_item(2)?.extract::<String>()?,
                bn.get_item(3)?.extract::<String>()?,
                bn.get_item(4)?.extract()?,
            ));
        }

        // Marshalled placements: a non-(tuple|list) value or a short list is
        // SKIPPED (None), mirroring the oracle's `isinstance`/`len` guards.
        // Coordinates are coerced with CPython `float()` (the oracle's
        // `float(x_mm)`), so `(0.5, "0.5")` is accepted like the oracle.
        let mut plcs: Vec<(String, Option<(f64, f64)>)> = Vec::new();
        for (ref_, pos) in placements.iter() {
            let ref_: String = ref_.extract()?;
            let is_container = pos.is_instance_of::<PyTuple>() || pos.is_instance_of::<PyList>();
            if !is_container || pos.len()? < 2 {
                plcs.push((ref_, None));
                continue;
            }
            plcs.push((
                ref_,
                Some((
                    py_float_coerce(py, &pos.get_item(0)?)?,
                    py_float_coerce(py, &pos.get_item(1)?)?,
                )),
            ));
        }

        let violations = find_critical_bottleneck_violations(&plcs, &bns, cell_um, width, height)?;
        let list = PyList::empty(py);
        for (ref_, gx, gy, layer, severity) in violations {
            let d = PyDict::new(py);
            d.set_item("ref", ref_)?;
            d.set_item("x", gx)?;
            d.set_item("y", gy)?;
            d.set_item("layer", layer)?;
            d.set_item("severity", severity)?;
            list.append(d)?;
        }
        Ok(list)
    })
}

// ---------------------------------------------------------------------------
// zone_aware_slot_generation.py — geometry kernels
// ---------------------------------------------------------------------------

/// The module-level `_point_in_polygon` — classic ray casting with CPython
/// `min`/`max` (first-argument-on-ties) and the `p1y != p2y` ternary for
/// `xinters`. Pinned verbatim including the half-open y tests and the
/// `x <= max(p1x, p2x)` gate.
pub fn point_in_polygon(x: f64, y: f64, polygon: &[(f64, f64)]) -> bool {
    if polygon.len() < 3 {
        return false;
    }

    let n = polygon.len();
    let mut inside = false;

    let mut p1x = polygon[0].0;
    let mut p1y = polygon[0].1;
    for i in 1..=n {
        let (p2x, p2y) = polygon[i % n];
        if y > py_min(p1y, p2y) && y <= py_max(p1y, p2y) && x <= py_max(p1x, p2x) {
            let xinters = if p1y != p2y {
                (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            } else {
                x
            };
            if p1x == p2x || x <= xinters {
                inside = !inside;
            }
        }
        p1x = p2x;
        p1y = p2y;
    }

    inside
}

/// Python-visible `point_in_polygon(x, y, polygon)`.
#[pyfunction]
pub fn point_in_polygon_py(
    x: f64,
    y: f64,
    polygon: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    guard(|| {
        let mut verts: Vec<(f64, f64)> = Vec::new();
        for v in polygon.try_iter()? {
            let v = v?;
            verts.push((v.get_item(0)?.extract()?, v.get_item(1)?.extract()?));
        }
        Ok(point_in_polygon(x, y, &verts))
    })
}

/// The module-level `_slot_intersects_iso` — inclusive AABB-vs-AABB test.
#[allow(clippy::type_complexity)]
pub fn slot_intersects_iso(
    slot: (f64, f64),
    iso_aabbs: &[((f64, f64), (f64, f64))],
) -> bool {
    let (sx, sy) = slot;
    for &((x_lo, y_lo), (x_hi, y_hi)) in iso_aabbs {
        if x_lo <= sx && sx <= x_hi && y_lo <= sy && sy <= y_hi {
            return true;
        }
    }
    false
}

/// Python-visible `slot_intersects_iso(slot, iso_aabbs)`.
#[pyfunction]
pub fn slot_intersects_iso_py(
    slot: (f64, f64),
    iso_aabbs: &Bound<'_, PyAny>,
) -> PyResult<bool> {
    guard(|| {
        let mut aabbs: Vec<((f64, f64), (f64, f64))> = Vec::new();
        for aabb in iso_aabbs.try_iter()? {
            let aabb = aabb?;
            let lo = aabb.get_item(0)?;
            let hi = aabb.get_item(1)?;
            aabbs.push((
                (lo.get_item(0)?.extract()?, lo.get_item(1)?.extract()?),
                (hi.get_item(0)?.extract()?, hi.get_item(1)?.extract()?),
            ));
        }
        Ok(slot_intersects_iso(slot, &aabbs))
    })
}

/// The `RoutingChannelAwareSlotStage._min_distance_to_polygon` — min
/// point-to-segment distance over the polygon edges in order; `float("inf")`
/// sentinel and `len < 2` -> `inf`, matching the oracle.
///
/// The inner distance is temper-geometry's canonical point-to-segment kernel
/// (issue #987); the Wave-4 reimplementation this module used to carry
/// (`pow`/`** 0.5` close) was deleted — its ≤1-ulp divergence is documented
/// in
/// `docs/evidence/2026-08-11-point-to-segment-distance-dedupe-execution.md`.
pub fn min_distance_to_polygon(x: f64, y: f64, polygon: &[(f64, f64)]) -> f64 {
    if polygon.len() < 2 {
        return f64::INFINITY;
    }

    let n = polygon.len();
    let mut min_dist = f64::INFINITY;

    for i in 0..n {
        let p1 = polygon[i];
        let p2 = polygon[(i + 1) % n];
        let dist = temper_geometry::creepage_check::point_to_segment_distance(
            x, y, p1.0, p1.1, p2.0, p2.1,
        );
        min_dist = py_min(min_dist, dist);
    }

    min_dist
}

/// Python-visible `min_distance_to_polygon(x, y, polygon)`.
#[pyfunction]
pub fn min_distance_to_polygon_py(
    x: f64,
    y: f64,
    polygon: &Bound<'_, PyAny>,
) -> PyResult<f64> {
    guard(|| {
        let mut verts: Vec<(f64, f64)> = Vec::new();
        for v in polygon.try_iter()? {
            let v = v?;
            verts.push((v.get_item(0)?.extract()?, v.get_item(1)?.extract()?));
        }
        Ok(min_distance_to_polygon(x, y, &verts))
    })
}

// ---------------------------------------------------------------------------
// _phase_core.py — footprint radius / slot reservation / distance
// ---------------------------------------------------------------------------

/// A component's `bounds` carrying each dimension's concrete Python type.
///
/// The oracle (`_PhaseCoreMixin._get_footprint_radius`) computes `w ** 2` as
/// exact integer pow when `bounds` holds ints and as libm `pow` when they are
/// floats — the two differ in the last ulp (mirrors `deterministic_leaves`'
/// component-assignment `Bounds` / `sq_dim`).
#[derive(Clone, Copy, Debug)]
pub struct FootprintBounds {
    pub w_int: bool,
    pub w: f64,
    pub h_int: bool,
    pub h: f64,
}

/// CPython `w ** 2` for a bounds dimension (int `**` int = exact int pow,
/// then widened to float at the sum; float `**` 2 = libm `pow`).
fn sq_dim(is_int: bool, v: f64) -> f64 {
    if is_int {
        let i = v as i64;
        (i * i) as f64
    } else {
        crate::host_math::pow(v, 2.0)
    }
}

/// `_PhaseCoreMixin._get_footprint_radius` — `math.sqrt(w**2 + h**2) / 2 +
/// 1.0` over the component bounds, or `slot_spacing / 2.0` when the component
/// has no bounds. `** 2` is libm `pow` / exact int pow per [`sq_dim`];
/// `math.sqrt` is libm `sqrt`.
pub fn footprint_radius(bounds: Option<FootprintBounds>, slot_spacing: f64) -> f64 {
    match bounds {
        Some(b) => {
            let w2 = sq_dim(b.w_int, b.w);
            let h2 = sq_dim(b.h_int, b.h);
            crate::host_math::sqrt(w2 + h2) / 2.0 + 1.0
        }
        None => slot_spacing / 2.0,
    }
}

/// `_PhaseCoreMixin._reserve_slots` — every slot whose Euclidean distance
/// from `center` is `<= radius`, in `all_slots` order. The distance is
/// `math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)` (`** 2` is libm `pow`).
pub fn reserve_slots(
    center: (f64, f64),
    radius: f64,
    all_slots: &[(f64, f64)],
) -> Vec<(f64, f64)> {
    let (cx, cy) = center;
    all_slots
        .iter()
        .copied()
        .filter(|&(sx, sy)| {
            let dist = crate::host_math::sqrt(
                crate::host_math::pow(sx - cx, 2.0) + crate::host_math::pow(sy - cy, 2.0),
            );
            dist <= radius
        })
        .collect()
}

/// `_PhaseCoreMixin._distance` — `math.sqrt((p1[0]-p2[0]) ** 2 +
/// (p1[1]-p2[1]) ** 2)` (`** 2` is libm `pow`, `math.sqrt` is libm `sqrt`).
pub fn distance(p1: (f64, f64), p2: (f64, f64)) -> f64 {
    crate::host_math::sqrt(
        crate::host_math::pow(p1.0 - p2.0, 2.0) + crate::host_math::pow(p1.1 - p2.1, 2.0),
    )
}

/// Python-visible `footprint_radius(bounds, slot_spacing)` where `bounds` is
/// a 2-element sequence (int or float elements) or `None`.
#[pyfunction]
pub fn footprint_radius_py(
    bounds: Option<&Bound<'_, PyAny>>,
    slot_spacing: f64,
) -> PyResult<f64> {
    guard(|| {
        let b = match bounds {
            None => None,
            Some(seq) => {
                let w = seq.get_item(0)?;
                let h = seq.get_item(1)?;
                Some(FootprintBounds {
                    w_int: w.is_instance_of::<pyo3::types::PyInt>(),
                    w: w.extract()?,
                    h_int: h.is_instance_of::<pyo3::types::PyInt>(),
                    h: h.extract()?,
                })
            }
        };
        Ok(footprint_radius(b, slot_spacing))
    })
}

/// Python-visible `reserve_slots(center, radius, all_slots)` — the list of
/// slots within `radius`, in `all_slots` order.
#[pyfunction]
pub fn reserve_slots_py<'py>(
    py: Python<'py>,
    center: (f64, f64),
    radius: f64,
    all_slots: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    guard(|| {
        let mut flat: Vec<(f64, f64)> = Vec::new();
        for s in all_slots.try_iter()? {
            let s = s?;
            flat.push((s.get_item(0)?.extract()?, s.get_item(1)?.extract()?));
        }
        let list = PyList::empty(py);
        for (sx, sy) in reserve_slots(center, radius, &flat) {
            list.append((sx, sy))?;
        }
        Ok(list)
    })
}

/// Python-visible `distance(p1, p2)`.
#[pyfunction]
pub fn distance_py(p1: (f64, f64), p2: (f64, f64)) -> PyResult<f64> {
    guard(|| Ok(distance(p1, p2)))
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as a submodule (`temper_design_bundle_python.deterministic_phase`)
/// so the delegation shims and the differential/PBT suites can address the
/// kernels.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "deterministic_phase")?;
    sub.add_function(wrap_pyfunction!(effective_ghost_pad_radius_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(compute_wirelength_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(find_critical_bottleneck_violations_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(point_in_polygon_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(slot_intersects_iso_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(min_distance_to_polygon_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(footprint_radius_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(reserve_slots_py, &sub)?)?;
    sub.add_function(wrap_pyfunction!(distance_py, &sub)?)?;
    module.add_submodule(&sub)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::host_math::sqrt;

    fn slot(sx0: f64, sy0: f64, sx1: f64, sy1: f64) -> (f64, f64, f64, f64) {
        (sx0, sy0, sx1, sy1)
    }

// --- BEGIN generated by scripts/gen_oracle_freeze.py: zone_aware_slot_generation ---
    /// Frozen golden vectors for zone_aware_slot_generation geometry kernels
    /// (FREEZE, U4/U5, batch 3 — retired stages/_zone_aware_slot_generation_py_oracle.py).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec zone_aware_slot_generation`
    /// (requires reviving the deleted oracle from git history first — see
    /// scripts/oracle_freeze_specs/zone_aware_slot_generation.py's module docstring).
    #[cfg(test)]
    mod frozen_zone_aware_tests {
        use super::*;
        use temper_geometry::creepage_check::point_to_segment_distance;

        struct FrozenPipCase {
            x: f64, y: f64,
            polygon: &'static [(f64, f64)],
            expected: bool,
            tags: &'static [&'static str],
        }

        const FROZEN_PIP_GOLDEN: &[FrozenPipCase] = &[
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:inside", "pip", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFF0000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:outside_left", "pip", "pip:horizontal_edge", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4026000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:outside_above", "pip", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4026000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:outside_right", "pip", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4024000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:top_edge", "pip", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:bottom_edge", "pip", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:left_edge", "pip", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4024000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:right_edge", "pip", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:vertex_00", "pip", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4024000000000000_u64), y: f64::from_bits(0x4024000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:vertex_1010", "pip", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:degenerate_2", "pip", "pip:degenerate", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                expected: false,
                tags: &["named:degenerate_1", "pip", "pip:degenerate", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[],
                expected: false,
                tags: &["named:degenerate_0", "pip", "pip:degenerate", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4000000000000000_u64), y: f64::from_bits(0x4020000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:concave_notch", "pip", "pip:concave", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: true,
                tags: &["named:concave_vertex", "pip", "pip:concave", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401C000000000000_u64), y: f64::from_bits(0x4020000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: false,
                tags: &["named:concave_right", "pip", "pip:concave", "pip:horizontal_edge", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4000000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4020000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4010000000000000_u64))],
                expected: true,
                tags: &["named:pent_h_edge", "pip", "pip:concave", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x3FF0000000000000_u64), y: f64::from_bits(0x4010000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4020000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4010000000000000_u64))],
                expected: true,
                tags: &["named:pent_on_h", "pip", "pip:concave", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4022000000000000_u64), y: f64::from_bits(0x4010000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4010000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4020000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4010000000000000_u64))],
                expected: true,
                tags: &["named:pent_on_h2", "pip", "pip:concave", "pip:horizontal_edge", "pip:inside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                polygon: &[(f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected: true,
                tags: &["named:neg_tri_center", "pip", "pip:horizontal_edge", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC010000000000000_u64), y: f64::from_bits(0xC01399999999999A_u64),
                polygon: &[(f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected: true,
                tags: &["named:neg_tri_edge", "pip", "pip:horizontal_edge", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0xC014000000000000_u64),
                polygon: &[(f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected: false,
                tags: &["named:neg_tri_bottom", "pip", "pip:horizontal_edge", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02F4338A6DF517E_u64), y: f64::from_bits(0xC035756A836DE57B_u64),
                polygon: &[(f64::from_bits(0xC020BD485125BD54_u64), f64::from_bits(0x403061B0E56B9FF6_u64)), (f64::from_bits(0x4028290E2C7E4CF0_u64), f64::from_bits(0x402F332773DB7430_u64)), (f64::from_bits(0x40185251849C75C8_u64), f64::from_bits(0x401A96F5E2F17570_u64)), (f64::from_bits(0x402D89D99A406AC8_u64), f64::from_bits(0x40168D9B06AE3368_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4030B815332ABC8C_u64), y: f64::from_bits(0xC034C0A16D0DF1C7_u64),
                polygon: &[(f64::from_bits(0x4023934BB0F25240_u64), f64::from_bits(0xC032CD1102D793C3_u64)), (f64::from_bits(0xC02DE571AF9F9970_u64), f64::from_bits(0x401D773A242B04D8_u64)), (f64::from_bits(0x4033EB96CE127934_u64), f64::from_bits(0x4033B810CF611238_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4009A7CAE1123228_u64), y: f64::from_bits(0xC00C2B3FC076AD70_u64),
                polygon: &[(f64::from_bits(0x402A1BF65082BA88_u64), f64::from_bits(0x4023947BAE5E1E66_u64)), (f64::from_bits(0x4031F91260B291B4_u64), f64::from_bits(0x4027806BBEC52862_u64)), (f64::from_bits(0xC023769EE271501C_u64), f64::from_bits(0x402BFEC040571C7C_u64)), (f64::from_bits(0xBFE0EA2130480EA0_u64), f64::from_bits(0x4024667A977F3D24_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC007D91F0028AF20_u64), y: f64::from_bits(0x4026E518738AE13C_u64),
                polygon: &[(f64::from_bits(0x402F17213E4C5850_u64), f64::from_bits(0x40162EE27A467548_u64)), (f64::from_bits(0x4018D7200658E228_u64), f64::from_bits(0xC018A4B0C79B6CB4_u64)), (f64::from_bits(0x400E4BCA27EE2B20_u64), f64::from_bits(0x401567D2C3B6B008_u64)), (f64::from_bits(0xC022F8043F173CEF_u64), f64::from_bits(0xC00084EB09D4B8E0_u64)), (f64::from_bits(0x4011CA4B96F7DDE4_u64), f64::from_bits(0x40337C7631AC9CE0_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0160FEF7BF20AA4_u64), y: f64::from_bits(0x4025E36102CDCF20_u64),
                polygon: &[(f64::from_bits(0xC029DE8A751121F0_u64), f64::from_bits(0xC027CA34E234B496_u64)), (f64::from_bits(0x3FED0C2418FFF000_u64), f64::from_bits(0xC023BC2CDC49F3A3_u64)), (f64::from_bits(0xBFF9F23BCB0F1BD0_u64), f64::from_bits(0x4010E13ADD9A4CB8_u64)), (f64::from_bits(0xC010ADC73636F364_u64), f64::from_bits(0xC02D899B1C3A5C92_u64)), (f64::from_bits(0xBFD767DE0FFDD4C0_u64), f64::from_bits(0xC0252A0BAA58AFF3_u64)), (f64::from_bits(0xC025254ECD223FF2_u64), f64::from_bits(0xC0287146A0FC0A90_u64)), (f64::from_bits(0xC0155E9F0D60C2D0_u64), f64::from_bits(0xC03111A7F1D91CCF_u64)), (f64::from_bits(0x401832740C94EB88_u64), f64::from_bits(0x4032258A4F5179F0_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02B826FF53A6A0B_u64), y: f64::from_bits(0xBFB94055F63F6000_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02CD4140E3AF916_u64), y: f64::from_bits(0x401772B6A21067A0_u64),
                polygon: &[(f64::from_bits(0x40163FB6C112F0C0_u64), f64::from_bits(0xC02B382EB2AB21C7_u64)), (f64::from_bits(0xC00BAED33A8CBEC8_u64), f64::from_bits(0x402D75961A834560_u64)), (f64::from_bits(0x402EE53889997F18_u64), f64::from_bits(0x402840F70D818394_u64)), (f64::from_bits(0xC027C15DBCF2317A_u64), f64::from_bits(0x402C4AD6A04E1350_u64)), (f64::from_bits(0xC01409FBF997CAC0_u64), f64::from_bits(0x40215225AA918F98_u64)), (f64::from_bits(0xC02D0A1618FC50C8_u64), f64::from_bits(0x4032DA254B84FE28_u64)), (f64::from_bits(0x40108F5C30C0D0A0_u64), f64::from_bits(0x4021D1306EF6A472_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01C2138BC6CA37C_u64), y: f64::from_bits(0x4026C4F4A01FA418_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40378E2A533F584E_u64), y: f64::from_bits(0x403044900F64E4FC_u64),
                polygon: &[(f64::from_bits(0xC0296D8C030BF7C3_u64), f64::from_bits(0xC02891EDE85AEC24_u64)), (f64::from_bits(0x4026FDFB5AD71EBA_u64), f64::from_bits(0x4001B1963C7D8B48_u64)), (f64::from_bits(0x40300653D820B6A6_u64), f64::from_bits(0xC02A9D1DC54EFDD7_u64)), (f64::from_bits(0xC006AC6DCE424920_u64), f64::from_bits(0x400E6F994E3F01B0_u64)), (f64::from_bits(0x40288F8AB96EE350_u64), f64::from_bits(0x401F39A728C6CBF4_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC022F0FB4CFB25F1_u64), y: f64::from_bits(0xC012642426766150_u64),
                polygon: &[(f64::from_bits(0x3FF103CC103CEB20_u64), f64::from_bits(0xC02DE198FE05573C_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4007E774A87D4708_u64), y: f64::from_bits(0x3FFA36A407AB2CD0_u64),
                polygon: &[(f64::from_bits(0x4004D03ACFE3EE60_u64), f64::from_bits(0x401FD75D758C6D78_u64)), (f64::from_bits(0x4031893FBE5975B8_u64), f64::from_bits(0x3FEC2F049AABF080_u64)), (f64::from_bits(0x402C216AF6585424_u64), f64::from_bits(0xC032918F6CF8AEFE_u64)), (f64::from_bits(0xC01CD9B9C14E10DA_u64), f64::from_bits(0xC02B984CAF08CF05_u64))],
                expected: true,
                tags: &["pip", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC00CD83A11CEC0E0_u64), y: f64::from_bits(0x401C240E9BC53E60_u64),
                polygon: &[(f64::from_bits(0xC02627E0214E132A_u64), f64::from_bits(0xC0276C026308D104_u64)), (f64::from_bits(0x4027E7994E5140F8_u64), f64::from_bits(0xC013D02B59F8F38C_u64)), (f64::from_bits(0x4021234D911AA0CC_u64), f64::from_bits(0xC02B6F0AD69DC3A4_u64)), (f64::from_bits(0xC02C4A67396AB6C3_u64), f64::from_bits(0xC007E26E94A35A28_u64)), (f64::from_bits(0x4029EF6E867DBE74_u64), f64::from_bits(0xC026C949A16A1E50_u64)), (f64::from_bits(0xC0080C2CB07AC220_u64), f64::from_bits(0xC025237C5671C11C_u64)), (f64::from_bits(0x4025D539CE714D08_u64), f64::from_bits(0x400D780E037E8110_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC00A03F85A6C1008_u64), y: f64::from_bits(0xC032268C3B529CC0_u64),
                polygon: &[(f64::from_bits(0xC03279C8C76A5312_u64), f64::from_bits(0xC01060E392C95C80_u64)), (f64::from_bits(0xC030879BB7A83861_u64), f64::from_bits(0x4024A6D67874C1DA_u64)), (f64::from_bits(0x400FF05A8CDA1E18_u64), f64::from_bits(0xC033D60F3ABBB975_u64)), (f64::from_bits(0x4025E879E51054E8_u64), f64::from_bits(0xC028C40483814492_u64)), (f64::from_bits(0xBFE8A8F2615C4100_u64), f64::from_bits(0x40017B2BCF965C88_u64)), (f64::from_bits(0xC01ABDCC86C6275A_u64), f64::from_bits(0xC020D85BE2B82C7B_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC033673D13B24EA2_u64), y: f64::from_bits(0x40302CD9AB7A0356_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40110C2113E93BB4_u64), y: f64::from_bits(0x4010A839FDBF0F88_u64),
                polygon: &[(f64::from_bits(0xC01EBA2965EED4CA_u64), f64::from_bits(0x401084878BC45134_u64)), (f64::from_bits(0xC020B9C33FAA8F8F_u64), f64::from_bits(0xC018627DF56F3D00_u64)), (f64::from_bits(0xC0300379EE31E304_u64), f64::from_bits(0xBFD74AD9729A0580_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFF0DC65AECFEA00_u64), y: f64::from_bits(0xC019AB645C3DA654_u64),
                polygon: &[(f64::from_bits(0xC03241C9773EAA91_u64), f64::from_bits(0x3FF66EFCC7A36FE0_u64)), (f64::from_bits(0xC02DA6CA6252F330_u64), f64::from_bits(0x40284B29BE7DE250_u64)), (f64::from_bits(0xC01C5DA258AACE30_u64), f64::from_bits(0x402F6E8B12DF3BE8_u64)), (f64::from_bits(0x3FFD0ECDFB2C32C0_u64), f64::from_bits(0xC02DF2FA68FA041C_u64)), (f64::from_bits(0xC033CD6D0C86FE7B_u64), f64::from_bits(0xC0242677D0E06192_u64)), (f64::from_bits(0x402D71C37CD0DCCC_u64), f64::from_bits(0xC02C0521B71A68B0_u64))],
                expected: true,
                tags: &["pip", "pip:concave", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC03649EE1E808D10_u64), y: f64::from_bits(0x4002D800E6E0FAF8_u64),
                polygon: &[(f64::from_bits(0xC022DFE62DFB6E14_u64), f64::from_bits(0x4029B8B23C2336B4_u64)), (f64::from_bits(0xC0321F397D687B00_u64), f64::from_bits(0xC024F9D7D155893A_u64)), (f64::from_bits(0x402A3B37C75A7C4C_u64), f64::from_bits(0xC024E70094CD110E_u64)), (f64::from_bits(0x4026E52B7D34575C_u64), f64::from_bits(0x40251429E867C3E4_u64)), (f64::from_bits(0xC028656652446A7F_u64), f64::from_bits(0xC0111B37A3968410_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0333B44ACAAAFC0_u64), y: f64::from_bits(0xC0322454E71BE02A_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4037F5A084350F2C_u64), y: f64::from_bits(0x40216D258CF34394_u64),
                polygon: &[(f64::from_bits(0x4024CCABDA1FCD24_u64), f64::from_bits(0xC014AE293153FD3C_u64)), (f64::from_bits(0xC0108D507A027E62_u64), f64::from_bits(0xC02C1461AA61A438_u64)), (f64::from_bits(0x3FFD1A8807D40220_u64), f64::from_bits(0xC02323748121934C_u64)), (f64::from_bits(0xC0145F2D4EF552E6_u64), f64::from_bits(0x403144BA7C26EB64_u64)), (f64::from_bits(0xC02AA32F42BB0C13_u64), f64::from_bits(0xC033606EB376D7AC_u64)), (f64::from_bits(0x3FEEDE361294F840_u64), f64::from_bits(0xC0224C3545562A06_u64)), (f64::from_bits(0xC0305CD9F5007A09_u64), f64::from_bits(0xC01A9DD74BD1986A_u64)), (f64::from_bits(0x401461C9147CAAC8_u64), f64::from_bits(0xC02B2827BBC75765_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC023E859AC743FEE_u64), y: f64::from_bits(0x3FF5114D8EED2D70_u64),
                polygon: &[(f64::from_bits(0x4030BBD1FBCF5E62_u64), f64::from_bits(0xC0325E57EB73F330_u64)), (f64::from_bits(0xC030369248752BD4_u64), f64::from_bits(0xC00E2842E0278468_u64)), (f64::from_bits(0xC011F83D22934FD0_u64), f64::from_bits(0xC01195C3B2A51028_u64)), (f64::from_bits(0xC02BEE981E26D7E1_u64), f64::from_bits(0xC02C0A51337F8681_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFF31DC77CDC3360_u64), y: f64::from_bits(0xC02EED9B9DA304CD_u64),
                polygon: &[(f64::from_bits(0xC02347310D3CCA86_u64), f64::from_bits(0xC01AE33A137903B4_u64)), (f64::from_bits(0x40317D7F6EF600AE_u64), f64::from_bits(0xC02437435875CC9F_u64)), (f64::from_bits(0x402C01D3E5862A4C_u64), f64::from_bits(0x402C484559BFF550_u64)), (f64::from_bits(0xC00AD56A49BC9D98_u64), f64::from_bits(0x4033BAD2F92E1142_u64)), (f64::from_bits(0x4024F280E4026312_u64), f64::from_bits(0xBFE46B4B3E87DA80_u64)), (f64::from_bits(0xC023156FAC730496_u64), f64::from_bits(0xBFF8E9B5E1BE57B0_u64)), (f64::from_bits(0x403014F99ACA4858_u64), f64::from_bits(0x3FF77AFF750D8FA0_u64)), (f64::from_bits(0xC0287CCF2A565B33_u64), f64::from_bits(0xC013E89FF5B7CF2C_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFECE7E33BC0DCA0_u64), y: f64::from_bits(0x3FA42FD4BBE3C200_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFC39FD5570E9380_u64), y: f64::from_bits(0x3FF11C3F4077C200_u64),
                polygon: &[(f64::from_bits(0xC02FC51019F1E6AA_u64), f64::from_bits(0x400C703C55512310_u64)), (f64::from_bits(0xC01ED608BA62FC58_u64), f64::from_bits(0x402ED072C5094734_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02C91E7892EB560_u64), y: f64::from_bits(0x402888E0BB6399D4_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0344D95B53A21BA_u64), y: f64::from_bits(0xC0225E14C95EDC11_u64),
                polygon: &[(f64::from_bits(0xC032EB58D6340DC3_u64), f64::from_bits(0x3FF43F0201C32500_u64)), (f64::from_bits(0x402626B52A9F6BEE_u64), f64::from_bits(0x401CFBE9E6DE463C_u64)), (f64::from_bits(0xC02025C3999A46EE_u64), f64::from_bits(0x40131BEFB7132AF8_u64)), (f64::from_bits(0x40180E0F211257F4_u64), f64::from_bits(0x40228EDB1501C018_u64)), (f64::from_bits(0xC0070D6FD2F74108_u64), f64::from_bits(0x402411493492F87A_u64)), (f64::from_bits(0xC025F1535F229B94_u64), f64::from_bits(0xC03323B2BDF5B3D6_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x402615714F551FE4_u64), y: f64::from_bits(0x4020B7F5408B38DC_u64),
                polygon: &[(f64::from_bits(0xC0339DCB4E24B769_u64), f64::from_bits(0xC00032365451DD80_u64)), (f64::from_bits(0x4024C8180F1200F4_u64), f64::from_bits(0xC0199CA3DEF0E73A_u64)), (f64::from_bits(0xC0265D5215EB3180_u64), f64::from_bits(0xC031F788F2607CF7_u64)), (f64::from_bits(0x40200C4C5FECF262_u64), f64::from_bits(0xC0074CCD7E954838_u64)), (f64::from_bits(0x403090075F8CD4C2_u64), f64::from_bits(0x40233E5928209324_u64)), (f64::from_bits(0xC02FF7FB3E4F669C_u64), f64::from_bits(0x40309105D1BDE770_u64)), (f64::from_bits(0x4031464BC3557AFE_u64), f64::from_bits(0x40295BEDFF864E9C_u64)), (f64::from_bits(0x402A80ED2D554A84_u64), f64::from_bits(0x401D044F5EE547F4_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40269EC6313AF284_u64), y: f64::from_bits(0x40134E1B359CBD84_u64),
                polygon: &[(f64::from_bits(0xC0236C96A0DF1978_u64), f64::from_bits(0xC02D5155F8BF15B9_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4002B4BE7C15BE90_u64), y: f64::from_bits(0xC031EA30ED2FE8E0_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x402A93148C7ACCA4_u64), y: f64::from_bits(0x4035957024D6E080_u64),
                polygon: &[(f64::from_bits(0xC032F5431F1FF66E_u64), f64::from_bits(0xBFF859D639E4AAC0_u64)), (f64::from_bits(0xC016FDB9D460BDA4_u64), f64::from_bits(0x4008FAE3D896B9B0_u64)), (f64::from_bits(0x4006BCC9A3F87820_u64), f64::from_bits(0x402863C69FB81004_u64)), (f64::from_bits(0x3FE0F74342381A80_u64), f64::from_bits(0xC0314DD77E55C0A2_u64)), (f64::from_bits(0x402CBABA7C71CD64_u64), f64::from_bits(0x3FF172B93C311D70_u64)), (f64::from_bits(0xC0218FCBC69E10CA_u64), f64::from_bits(0xC0134527228DC04C_u64)), (f64::from_bits(0xC02E0875C8DF9BE0_u64), f64::from_bits(0xC0278BC8F129E2C0_u64)), (f64::from_bits(0xC01B9F40AC7E7280_u64), f64::from_bits(0x400995F3331BE860_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02C736E97F5ACA4_u64), y: f64::from_bits(0xC031B5CACAEC3075_u64),
                polygon: &[(f64::from_bits(0x40291FC6D747E7F0_u64), f64::from_bits(0x4026BF9724432F14_u64)), (f64::from_bits(0x403372505590BECE_u64), f64::from_bits(0xC000BB0C406B22A0_u64)), (f64::from_bits(0xC00CA2F834BDDEC0_u64), f64::from_bits(0x40048A042BC71C58_u64)), (f64::from_bits(0x4023FA31B69C0274_u64), f64::from_bits(0xC030CD9657BF7600_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4036CB8AC7EB1052_u64), y: f64::from_bits(0x4005D3907B5518E8_u64),
                polygon: &[(f64::from_bits(0x40339C83EB7FDE28_u64), f64::from_bits(0x402B35F7F7AEBFEC_u64)), (f64::from_bits(0x3FF3C969109E9440_u64), f64::from_bits(0xC005EF5A02A923D8_u64)), (f64::from_bits(0x4003AFF813C8B310_u64), f64::from_bits(0xC0338C6FBCFB155B_u64)), (f64::from_bits(0x4014A17F6F7CA5BC_u64), f64::from_bits(0x402E1A6486E41E38_u64)), (f64::from_bits(0x4023F8684120F534_u64), f64::from_bits(0x4018F8C9229267BC_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4038441BA7C599E6_u64), y: f64::from_bits(0xC03017345760E36A_u64),
                polygon: &[(f64::from_bits(0xC01DDB8820D1624C_u64), f64::from_bits(0x4033AA4E2B14110A_u64)), (f64::from_bits(0xC02B33449D048670_u64), f64::from_bits(0xC0292EABB181D65A_u64)), (f64::from_bits(0xC031C70011D7C68E_u64), f64::from_bits(0xC00403229161D2B0_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC00F5993FD20D170_u64), y: f64::from_bits(0xC02987BBB138DE08_u64),
                polygon: &[(f64::from_bits(0x40200B52B0CE8EA8_u64), f64::from_bits(0x4027C59D34DE7C8A_u64)), (f64::from_bits(0x402C3E6D3D21F470_u64), f64::from_bits(0xC02B98FA2CE2FB7A_u64)), (f64::from_bits(0xC031D6B38541B248_u64), f64::from_bits(0x4013590111094920_u64)), (f64::from_bits(0x3FE8171BE33D7B20_u64), f64::from_bits(0x3FEADAA03C94A580_u64)), (f64::from_bits(0x40268C674D7FD23A_u64), f64::from_bits(0xC02A0FAACB15AF9E_u64)), (f64::from_bits(0x40207CD77FC101F4_u64), f64::from_bits(0xC00786D79BCE5630_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC036A5F2FAA3D564_u64), y: f64::from_bits(0xC03307D48077A2F0_u64),
                polygon: &[(f64::from_bits(0x40287B2A6FCA1E18_u64), f64::from_bits(0x402139BB598A3024_u64)), (f64::from_bits(0xC00A56A263BAE2F0_u64), f64::from_bits(0xC0215DAE7B32BE71_u64)), (f64::from_bits(0x402375071D2801E8_u64), f64::from_bits(0xC0270ECB1307C2FF_u64)), (f64::from_bits(0x402B258AA4851AD8_u64), f64::from_bits(0xC0309EF8023253F4_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x400206D815014808_u64), y: f64::from_bits(0xC03228AF1E102DCF_u64),
                polygon: &[(f64::from_bits(0xC02C08FBBDEAFC24_u64), f64::from_bits(0x4033DFBF2B192266_u64)), (f64::from_bits(0x4013EDBB4E1BA114_u64), f64::from_bits(0xC02FFC521CF7CA5D_u64)), (f64::from_bits(0xBFD1D3E9F2B6FF40_u64), f64::from_bits(0x400F9B43742C6FF8_u64)), (f64::from_bits(0xC03229E8377A6321_u64), f64::from_bits(0x402F9EE72DC14CF0_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0299E8B17A6E9EA_u64), y: f64::from_bits(0xC03172D38252488C_u64),
                polygon: &[(f64::from_bits(0xC02555176F37F020_u64), f64::from_bits(0xC01AEE1EC72D38F0_u64)), (f64::from_bits(0xC015D53BF98087E0_u64), f64::from_bits(0xC033EB2D257000B2_u64)), (f64::from_bits(0x402EF3534EE64C2C_u64), f64::from_bits(0xC030785EC984AA66_u64)), (f64::from_bits(0xC02FE8E2C64E627A_u64), f64::from_bits(0x4027D421468E7544_u64)), (f64::from_bits(0x402979182AB035A8_u64), f64::from_bits(0xC000CB72BF633E20_u64)), (f64::from_bits(0xC009276D4B2FE2F0_u64), f64::from_bits(0xC02CDCC944F02C36_u64)), (f64::from_bits(0xC033F38C63D6EF1E_u64), f64::from_bits(0x3FEA3A1BF671DD40_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFDA2C93CBE63100_u64), y: f64::from_bits(0x4004A987606AE940_u64),
                polygon: &[(f64::from_bits(0xC0333AA709372F9B_u64), f64::from_bits(0xC0160822E56E4F7C_u64)), (f64::from_bits(0x4024200F3D7D61C8_u64), f64::from_bits(0x4023BD11D3EDD0E0_u64)), (f64::from_bits(0xC02F71D9B68537B0_u64), f64::from_bits(0x40235E86EF99748E_u64)), (f64::from_bits(0x40044C8336C60E28_u64), f64::from_bits(0x4014CB431C8BE218_u64)), (f64::from_bits(0x4031BBA6784893F0_u64), f64::from_bits(0x4027E40D69917F04_u64)), (f64::from_bits(0x400FC661794A3B20_u64), f64::from_bits(0x40259713913B5C62_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01FF6905634A678_u64), y: f64::from_bits(0xC00C62B831FD7610_u64),
                polygon: &[(f64::from_bits(0x40131C7A4AFEFBC0_u64), f64::from_bits(0xC013C367AC01A366_u64)), (f64::from_bits(0xC0332F3A77026C94_u64), f64::from_bits(0x40272C3FF3F01144_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40319E99C9B0856A_u64), y: f64::from_bits(0x3FE3D79088808300_u64),
                polygon: &[(f64::from_bits(0xC030C8D887392733_u64), f64::from_bits(0xC0249C9C5DFD8F2E_u64)), (f64::from_bits(0xC02A858815A8EE80_u64), f64::from_bits(0x4032453561F8771C_u64)), (f64::from_bits(0x4024162907956C90_u64), f64::from_bits(0xC03207F89415BE35_u64)), (f64::from_bits(0xBFF8BAF89CC35FC0_u64), f64::from_bits(0xC02FC35EFEA2CDBD_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0310221A7C04F6D_u64), y: f64::from_bits(0x402B1BE851934C5C_u64),
                polygon: &[(f64::from_bits(0x40237DEACB6DF058_u64), f64::from_bits(0x402F45A77DCADAB0_u64)), (f64::from_bits(0x40028FD4C1BC5B30_u64), f64::from_bits(0x4001A7ACFCE89DA8_u64)), (f64::from_bits(0xC028ED0D73BB2D5C_u64), f64::from_bits(0xC024B4370A475DAB_u64)), (f64::from_bits(0xC004F5B4763612B0_u64), f64::from_bits(0xBFA87A1F454A6800_u64)), (f64::from_bits(0x402FF13EC83EF16C_u64), f64::from_bits(0xC0324B8AAA20422C_u64)), (f64::from_bits(0xC0180F0DA42FB8CC_u64), f64::from_bits(0x402336391D150BE4_u64)), (f64::from_bits(0xBFFA44328FFA43F0_u64), f64::from_bits(0x402BDEDF54289A40_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01560B330F2A99C_u64), y: f64::from_bits(0x4034CC2F6D7755DE_u64),
                polygon: &[(f64::from_bits(0x402453342DACEAC8_u64), f64::from_bits(0xC011138806DC689E_u64)), (f64::from_bits(0xC0117A466BF1689A_u64), f64::from_bits(0xC0264284FBF8CC2F_u64)), (f64::from_bits(0x4019F7D77AB40180_u64), f64::from_bits(0xC028B23A225C2C34_u64)), (f64::from_bits(0x402E5475303AB634_u64), f64::from_bits(0xC027A16D3D9C259C_u64)), (f64::from_bits(0xC032847B49810871_u64), f64::from_bits(0xC03355DB63C4A9FA_u64)), (f64::from_bits(0x3FEF9CDCF3D977C0_u64), f64::from_bits(0x401DA1F6743D4018_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x403286F54545A41A_u64), y: f64::from_bits(0xBFFBA3D003FA1440_u64),
                polygon: &[(f64::from_bits(0xC02D6DE8DD58405E_u64), f64::from_bits(0x40325CDDD844460A_u64)), (f64::from_bits(0xC0308EE91F89D390_u64), f64::from_bits(0x4032C414CB72B3B0_u64)), (f64::from_bits(0x400BC96349272090_u64), f64::from_bits(0xC000B90064BEAFD0_u64)), (f64::from_bits(0x40316E8273AC6A00_u64), f64::from_bits(0x3FDF6F961CA243C0_u64)), (f64::from_bits(0x3FD5924CC442CF00_u64), f64::from_bits(0xC0319A7BED7204D0_u64)), (f64::from_bits(0x4027CF9190E44D42_u64), f64::from_bits(0x401645E2D38B2434_u64)), (f64::from_bits(0xC024D4EA10C3B432_u64), f64::from_bits(0xC02EE7EA27B9EBEA_u64)), (f64::from_bits(0xC009947FFBED6220_u64), f64::from_bits(0x4031684D6DCCF7A0_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0111845FE46C614_u64), y: f64::from_bits(0xC036EA8ABC7C91EF_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC024848DE5E391F7_u64), y: f64::from_bits(0x40238877BFF32048_u64),
                polygon: &[(f64::from_bits(0x402279870E045AC4_u64), f64::from_bits(0xBF9794217B28BC00_u64)), (f64::from_bits(0x40328BF4F4BE08AC_u64), f64::from_bits(0xC02C3036E472AFE2_u64)), (f64::from_bits(0x40277EB4543DDDB0_u64), f64::from_bits(0x40219ED9BBBAE2F6_u64)), (f64::from_bits(0xC0334F5B5F1CAAE5_u64), f64::from_bits(0x4004EC0D62AAF620_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40260F8969F08258_u64), y: f64::from_bits(0xC035B669B9D3B350_u64),
                polygon: &[(f64::from_bits(0x401A942A17DDECC0_u64), f64::from_bits(0xBFCEADF97EC09580_u64)), (f64::from_bits(0x401099943E57D660_u64), f64::from_bits(0xC0241CD08F522822_u64)), (f64::from_bits(0xBFF4B5ED318C6720_u64), f64::from_bits(0xC02EAF65995AA602_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4035E3AF28AB7C1C_u64), y: f64::from_bits(0x40243A6C73632C34_u64),
                polygon: &[(f64::from_bits(0x401F8E71F7973618_u64), f64::from_bits(0xC028A3A8C25E43AA_u64)), (f64::from_bits(0x403096E14F486D78_u64), f64::from_bits(0x40228FCC9646473C_u64)), (f64::from_bits(0xC012E8345F8094A8_u64), f64::from_bits(0xC02791AED2CE1EE8_u64)), (f64::from_bits(0x4033F6151270FA64_u64), f64::from_bits(0xBFFF6A7439D139F0_u64)), (f64::from_bits(0x4028589927F4E934_u64), f64::from_bits(0xC01B736ABD256334_u64)), (f64::from_bits(0xC00099A10ED89E28_u64), f64::from_bits(0x4010091AC4B9D984_u64)), (f64::from_bits(0x402562BDE9C0F05E_u64), f64::from_bits(0x402E9D2A11660C64_u64)), (f64::from_bits(0x402B22D4AE678A08_u64), f64::from_bits(0x40096ACF84EEF480_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x402F3BB3DC9EAB5C_u64), y: f64::from_bits(0xC01414C2E68B39A0_u64),
                polygon: &[(f64::from_bits(0x3FC3B222CDFC9900_u64), f64::from_bits(0xC00681D9838108F0_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02C3C63D7FFB1C3_u64), y: f64::from_bits(0xC0267014EE6E0112_u64),
                polygon: &[(f64::from_bits(0xC024592C22381B2A_u64), f64::from_bits(0xC01E96B25644280C_u64)), (f64::from_bits(0xBFFF2E5A92480720_u64), f64::from_bits(0x402419E0D810A26C_u64)), (f64::from_bits(0xC02F73FC2C5B86B2_u64), f64::from_bits(0xC0026C2C65B3D8E8_u64)), (f64::from_bits(0xC025309B44DE8992_u64), f64::from_bits(0x401B5C41C01F0330_u64)), (f64::from_bits(0x40294350B3DA91E8_u64), f64::from_bits(0xC022DEB3EBCBE725_u64)), (f64::from_bits(0x4021949DF5B45F8C_u64), f64::from_bits(0xBFF70BC0E34C6870_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4035DBB94207C434_u64), y: f64::from_bits(0xC034C1385C216F0C_u64),
                polygon: &[(f64::from_bits(0x403074C57308AFC2_u64), f64::from_bits(0x40206BC14604A92E_u64)), (f64::from_bits(0x402FD93D92015D94_u64), f64::from_bits(0x4019F2903BA10098_u64)), (f64::from_bits(0x4030D26A69E69F50_u64), f64::from_bits(0xC02DC7722BC644CC_u64)), (f64::from_bits(0xC01B2EC4D32D836C_u64), f64::from_bits(0x403356CC58343D52_u64)), (f64::from_bits(0xC03347F3128A23F1_u64), f64::from_bits(0xC0100AC81293E11C_u64)), (f64::from_bits(0xC02FF8750C9DB4A0_u64), f64::from_bits(0xC032940F9A9B3321_u64)), (f64::from_bits(0xC01B7ACDA728807E_u64), f64::from_bits(0xC032DE0C07A59E86_u64)), (f64::from_bits(0x402BA273D6E86078_u64), f64::from_bits(0xC030F9FE0073E9BD_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC038F6F7C1D580A2_u64), y: f64::from_bits(0x3FE282B39749B280_u64),
                polygon: &[(f64::from_bits(0x4023B48C97B1BF78_u64), f64::from_bits(0xBFE1F1C8334CD3C0_u64)), (f64::from_bits(0x4006EC7C92B2C7F0_u64), f64::from_bits(0x40081A3B2C9591A8_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4036E63E4ADDB5B2_u64), y: f64::from_bits(0xC02004AD5C964F34_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC024C58AD5E95B92_u64), y: f64::from_bits(0xBFC9F8787BD7E200_u64),
                polygon: &[(f64::from_bits(0xC030D25CCF8FD753_u64), f64::from_bits(0xC00DEC17A170A868_u64)), (f64::from_bits(0xC00D0F28B5B01080_u64), f64::from_bits(0x402FA3B9EABCF718_u64)), (f64::from_bits(0xC030B5E2EA05FAA2_u64), f64::from_bits(0xC0273FB47C7ED240_u64)), (f64::from_bits(0xC0197221E0E402A4_u64), f64::from_bits(0xC02E82A77042F1CA_u64)), (f64::from_bits(0xC02BA3FD0B41C0A2_u64), f64::from_bits(0xC011E559085624B8_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0236C6AF45F9AB6_u64), y: f64::from_bits(0x401C41DCAA0DB760_u64),
                polygon: &[(f64::from_bits(0x402944A111F96ABC_u64), f64::from_bits(0xBFC00477843F7C00_u64)), (f64::from_bits(0xC02FB9BF48381FEC_u64), f64::from_bits(0x3FF732675EBCDD10_u64)), (f64::from_bits(0xC01FB0207310420E_u64), f64::from_bits(0xC030E42AA278927A_u64)), (f64::from_bits(0xBFFF3C8332086C70_u64), f64::from_bits(0xC02834900546C3A0_u64)), (f64::from_bits(0xC033AD9FA09590AB_u64), f64::from_bits(0xC0321B4C97DE22FB_u64)), (f64::from_bits(0x3FEA01044B615000_u64), f64::from_bits(0xBFF104F55F071720_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC032526C20BA6067_u64), y: f64::from_bits(0x40370B454AA34F58_u64),
                polygon: &[(f64::from_bits(0xC0339291FD7E651C_u64), f64::from_bits(0x4031D857ED5AF274_u64)), (f64::from_bits(0xC0332BBF58C16162_u64), f64::from_bits(0xC02AB8444CBABD79_u64)), (f64::from_bits(0xC01B67626F3D44C4_u64), f64::from_bits(0x4027CA32CAEB1E94_u64)), (f64::from_bits(0x4023679835D63358_u64), f64::from_bits(0x402375AF70129BB4_u64)), (f64::from_bits(0xC0067A7EC7F6F1B8_u64), f64::from_bits(0x40307A821D1DAB9C_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01A07B0C5290384_u64), y: f64::from_bits(0xC030ACC9550E82B0_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01CBBAFE1294F9C_u64), y: f64::from_bits(0x4033AA4599362772_u64),
                polygon: &[(f64::from_bits(0x402594DA42EBEEAE_u64), f64::from_bits(0x401BB1E243ABFE84_u64)), (f64::from_bits(0xC0241DC44301D8CC_u64), f64::from_bits(0x402D579B5B3B10D4_u64)), (f64::from_bits(0x3FE350028CCCCE00_u64), f64::from_bits(0xC0277F350BC5245D_u64)), (f64::from_bits(0xC030243CEC6D9753_u64), f64::from_bits(0x40338F2461D82CEE_u64)), (f64::from_bits(0xC031C478BEC4B396_u64), f64::from_bits(0xC0266BC4252FAEA4_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC00706CC013DA0B8_u64), y: f64::from_bits(0xC0248A9D10117050_u64),
                polygon: &[(f64::from_bits(0x402B558483315B30_u64), f64::from_bits(0x4014F2BF4DBBCBF4_u64)), (f64::from_bits(0xC033899DD8EDA3FA_u64), f64::from_bits(0x40230B4CDF29429C_u64)), (f64::from_bits(0xC028C316B0713237_u64), f64::from_bits(0x4031E46D614AC3C2_u64)), (f64::from_bits(0x4032CFF1539AF242_u64), f64::from_bits(0xC0315CB2233FC794_u64)), (f64::from_bits(0x40228002E55149B8_u64), f64::from_bits(0xC024AA7FB09DE7E5_u64)), (f64::from_bits(0xC02FA4F2B7D53194_u64), f64::from_bits(0x402DFD0C81F01AE8_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0350CEBC0BDEB45_u64), y: f64::from_bits(0xC0213E02F6F2889E_u64),
                polygon: &[(f64::from_bits(0xC0238DD21D5AF867_u64), f64::from_bits(0x401ED5459C79B930_u64)), (f64::from_bits(0xC021528EE3815362_u64), f64::from_bits(0xC025CDFC715B23CB_u64)), (f64::from_bits(0xC004FB23B3191B50_u64), f64::from_bits(0xBFE707BAF1004280_u64)), (f64::from_bits(0xC0245A5166F23DE5_u64), f64::from_bits(0xC0315537E2F7BEE0_u64)), (f64::from_bits(0xC02EA1B11CA9B69E_u64), f64::from_bits(0xC0268934C04F94F8_u64)), (f64::from_bits(0x401C703B39D23C00_u64), f64::from_bits(0x4032CAAC6A46EEF6_u64)), (f64::from_bits(0xC01899A668064958_u64), f64::from_bits(0xC0242BBC481A5790_u64)), (f64::from_bits(0x400D8A204C969400_u64), f64::from_bits(0xC01CF28B5D85904C_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01D60788F99065C_u64), y: f64::from_bits(0x4030807FF7378702_u64),
                polygon: &[(f64::from_bits(0xBFF50D8778F9C660_u64), f64::from_bits(0xC009103870803810_u64)), (f64::from_bits(0xC01037EF8A7DAD0E_u64), f64::from_bits(0xC015586170A659F2_u64)), (f64::from_bits(0xC00BACE1C3AF9D70_u64), f64::from_bits(0xC029BA7B7B6250E8_u64)), (f64::from_bits(0xC0204DB4042EBDDA_u64), f64::from_bits(0x401E7DD487811DDC_u64)), (f64::from_bits(0xBFEA1EEFE89E48C0_u64), f64::from_bits(0xC03147C7CD57C8DA_u64)), (f64::from_bits(0xC02C612A58E7593A_u64), f64::from_bits(0x402B46D2E4A8FE84_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401918E52D5014B4_u64), y: f64::from_bits(0xC01CDDF3668F185C_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401A824194E65A48_u64), y: f64::from_bits(0xC012042FADC53EBC_u64),
                polygon: &[(f64::from_bits(0x4023AAA7A92A5B96_u64), f64::from_bits(0xC0120F06B11AA5C0_u64)), (f64::from_bits(0xC02B6C48D8ECF0BC_u64), f64::from_bits(0x4018A1186445B78C_u64)), (f64::from_bits(0x4032306F6B843AA0_u64), f64::from_bits(0x4021A283BD45724E_u64)), (f64::from_bits(0xC0104E03D3BE8974_u64), f64::from_bits(0x401512FD5535A010_u64)), (f64::from_bits(0x3FC38ED1426C5680_u64), f64::from_bits(0x4011180C7E5E8328_u64)), (f64::from_bits(0xC0277E9FAAC1AA72_u64), f64::from_bits(0x401AE7787CF56B90_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC036CEEC9DC77EFF_u64), y: f64::from_bits(0x4035D96BEB8A6712_u64),
                polygon: &[(f64::from_bits(0x402D5483A80ECFDC_u64), f64::from_bits(0xC00F0004D9584700_u64)), (f64::from_bits(0xC0311C4DDFB04892_u64), f64::from_bits(0xC0225DCF2F82FA5F_u64)), (f64::from_bits(0x401F48D638C71778_u64), f64::from_bits(0xC033B64BB62ABCA0_u64)), (f64::from_bits(0x402A0C1E8FE7DC54_u64), f64::from_bits(0x4029E93CCCD88840_u64)), (f64::from_bits(0xBFB654E0CF8E5400_u64), f64::from_bits(0xC02202B42859ABAA_u64)), (f64::from_bits(0xC0297AFAA440EBE8_u64), f64::from_bits(0x401D195619BEFD38_u64)), (f64::from_bits(0x4021D0D2355F1FCC_u64), f64::from_bits(0x402D797222A320EC_u64)), (f64::from_bits(0x4025A6585C9FC2C8_u64), f64::from_bits(0x4029CB3C35D34DD8_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x403463834B94F8CA_u64), y: f64::from_bits(0x40321DB45BAB1516_u64),
                polygon: &[(f64::from_bits(0x4032ADD59329029E_u64), f64::from_bits(0x4024645E52835AB8_u64)), (f64::from_bits(0x402D3B6C214A56E8_u64), f64::from_bits(0x402FC1567A9691EC_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC03581A7EDB4CDF5_u64), y: f64::from_bits(0x402F93DD499CFDC0_u64),
                polygon: &[(f64::from_bits(0xC032CF2F7D9C5489_u64), f64::from_bits(0xC0307011721D456D_u64)), (f64::from_bits(0x40078CBD8F320340_u64), f64::from_bits(0xBFF695C18E2383D0_u64)), (f64::from_bits(0xC017C8527860D8A8_u64), f64::from_bits(0xC00B1AC72C117F50_u64)), (f64::from_bits(0xC03336D49642DF37_u64), f64::from_bits(0xC023377810554EB1_u64)), (f64::from_bits(0xC029D240383BDFBE_u64), f64::from_bits(0xC024E6B8A8121D92_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC033A6DB28E8E133_u64), y: f64::from_bits(0xC02A312CCBD9DB42_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x3FF42C5DC4012DA0_u64), y: f64::from_bits(0xC03300F93DDB54B0_u64),
                polygon: &[(f64::from_bits(0xBFFD8E67233CEE30_u64), f64::from_bits(0x40235622199C752E_u64)), (f64::from_bits(0xC029069D0C587E0E_u64), f64::from_bits(0x40204020974FB12C_u64)), (f64::from_bits(0xC02F72A8EC956720_u64), f64::from_bits(0x40274F7A0A51320C_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401C19B46C0F2F80_u64), y: f64::from_bits(0xC030879B5F777FC2_u64),
                polygon: &[(f64::from_bits(0x402A80D389D95604_u64), f64::from_bits(0xC031D57AC3C4BDF6_u64)), (f64::from_bits(0x40315C1F79782D52_u64), f64::from_bits(0xC03176A69F85F5D5_u64)), (f64::from_bits(0x40149A362B67972C_u64), f64::from_bits(0xC01E315CEEE53EB8_u64)), (f64::from_bits(0xC027A36BCAF4FE5E_u64), f64::from_bits(0xC02EFFE55133D2CA_u64)), (f64::from_bits(0x403336762A03D600_u64), f64::from_bits(0xC03114041AA87E50_u64)), (f64::from_bits(0xC032871560B4A6C7_u64), f64::from_bits(0xC0206E3094AEED61_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x402E9BA36A38D520_u64), y: f64::from_bits(0x4031CD3A5662E7E8_u64),
                polygon: &[(f64::from_bits(0x4025C70E1869FF1C_u64), f64::from_bits(0x402AFD5CB9FA8294_u64)), (f64::from_bits(0x40105EEFF131D194_u64), f64::from_bits(0x402DD3A89CAF2820_u64)), (f64::from_bits(0x3FF1C5771951F560_u64), f64::from_bits(0xC00B3220BABBDB88_u64)), (f64::from_bits(0xC01D50C83ADF39CC_u64), f64::from_bits(0xC022773ED43FF5B5_u64)), (f64::from_bits(0xC02BC0854AC6E5A2_u64), f64::from_bits(0x4030ECB0C828E954_u64)), (f64::from_bits(0x4000CFF7015082B0_u64), f64::from_bits(0xC030A93E968C98EE_u64)), (f64::from_bits(0xC0274D43EFC41F78_u64), f64::from_bits(0xC0084907674443F8_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x400ACB2084090A58_u64), y: f64::from_bits(0xC0388065358C2E66_u64),
                polygon: &[(f64::from_bits(0xC018C9456B754A9E_u64), f64::from_bits(0x4012550ECEF2CDF0_u64)), (f64::from_bits(0xC027B7AE9C1FB504_u64), f64::from_bits(0x4005ACC109FB4B40_u64)), (f64::from_bits(0x402F1BBAE280C148_u64), f64::from_bits(0x4024EDFF3ECC76AE_u64)), (f64::from_bits(0xC00DC40923BE4478_u64), f64::from_bits(0x402F1D864B182C90_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0081C1D2100B4C8_u64), y: f64::from_bits(0xC0329859B21D229C_u64),
                polygon: &[(f64::from_bits(0xC021BA013946EA28_u64), f64::from_bits(0x403137144893EE2C_u64)), (f64::from_bits(0xC01F2BE80279ACF8_u64), f64::from_bits(0x4012E3F1347E92A0_u64)), (f64::from_bits(0xC030C662143E87ED_u64), f64::from_bits(0xC031E03185798974_u64)), (f64::from_bits(0x4022DF9F20683702_u64), f64::from_bits(0x401AE9272FB283E0_u64)), (f64::from_bits(0x401CF1E678307660_u64), f64::from_bits(0xC0310A0A0F3B857A_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4032EA80DC39C3E2_u64), y: f64::from_bits(0x40349C4E1B53BA46_u64),
                polygon: &[(f64::from_bits(0x40329303850C3B5A_u64), f64::from_bits(0xC033D99CFCF0B5C4_u64)), (f64::from_bits(0xC02F641BDE61090E_u64), f64::from_bits(0x4030072933E9DD6E_u64)), (f64::from_bits(0x403093EFDA30152C_u64), f64::from_bits(0x3FCE5179D05A9D80_u64)), (f64::from_bits(0xC02066156172492A_u64), f64::from_bits(0xC0202616999FD4AA_u64)), (f64::from_bits(0x4022B03F56139710_u64), f64::from_bits(0x4009BBFA234DE9C0_u64)), (f64::from_bits(0xC00122B419B66670_u64), f64::from_bits(0x401E94E448E3F9A8_u64)), (f64::from_bits(0xC0300804E684A2DA_u64), f64::from_bits(0xC011C33BB357B1B4_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02B4CEE7E626637_u64), y: f64::from_bits(0xC025B115AB79ECD2_u64),
                polygon: &[(f64::from_bits(0xC0220AFA4A2D6372_u64), f64::from_bits(0x4015604CF9B0F5F8_u64)), (f64::from_bits(0xBFED45F74C8E1CE0_u64), f64::from_bits(0xC029447B5292435E_u64)), (f64::from_bits(0xC029475660F537E3_u64), f64::from_bits(0xC032C6C639A4E88A_u64)), (f64::from_bits(0x40311981A0B4F274_u64), f64::from_bits(0x3FFD161AFA1E1350_u64)), (f64::from_bits(0xC032E98FC3C9F8F0_u64), f64::from_bits(0xC02264FF20862CB6_u64)), (f64::from_bits(0xC02AE65A7938DF74_u64), f64::from_bits(0xC01CC2F3A750B510_u64)), (f64::from_bits(0x4015CDD27472F8D0_u64), f64::from_bits(0xC0129DF098E19CCA_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4034F9103DAD33DA_u64), y: f64::from_bits(0x4017C0C04FB2564C_u64),
                polygon: &[(f64::from_bits(0xC01BBA6F0983F664_u64), f64::from_bits(0xC030ED2C1016F7B1_u64)), (f64::from_bits(0xC029EA6187515AD5_u64), f64::from_bits(0xC0326EF8215635D2_u64)), (f64::from_bits(0x402FD7F54554107C_u64), f64::from_bits(0xC027C8B41665406C_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC032A45DA6B31332_u64), y: f64::from_bits(0x4033BD37F03E11E6_u64),
                polygon: &[(f64::from_bits(0x401BCAB9011A39F0_u64), f64::from_bits(0xC03232584E940628_u64)), (f64::from_bits(0xC031B5F585E4B1C8_u64), f64::from_bits(0x401C76991DE75DB8_u64)), (f64::from_bits(0xC0311CE6F69A9209_u64), f64::from_bits(0xC022A47F38E6C812_u64)), (f64::from_bits(0xBFF0EF79381F8A50_u64), f64::from_bits(0xBFF1D3A67C5F4A20_u64)), (f64::from_bits(0x40301360028491D8_u64), f64::from_bits(0x40128544D6D3E220_u64)), (f64::from_bits(0xC018B4C8D2FD06A8_u64), f64::from_bits(0xBFF14875E5826820_u64)), (f64::from_bits(0x400CEDA50106A270_u64), f64::from_bits(0x40265182EDE3E0D4_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4038915ABE7BED82_u64), y: f64::from_bits(0x40316B149869D256_u64),
                polygon: &[(f64::from_bits(0xC02A10302F1A4D5A_u64), f64::from_bits(0xC01274B55EECAC94_u64)), (f64::from_bits(0xC0182ED8FFA0A950_u64), f64::from_bits(0xBFF75B5F8558D7E0_u64)), (f64::from_bits(0xC00E3C73493BDF28_u64), f64::from_bits(0xC0268933315DF01C_u64)), (f64::from_bits(0xC02A816A8842D93C_u64), f64::from_bits(0xBFF4C1AFACC250B0_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401CC699BD794828_u64), y: f64::from_bits(0x402E035541C7BDE8_u64),
                polygon: &[(f64::from_bits(0x402B477A06575C88_u64), f64::from_bits(0x4011EC8B5AED47E0_u64)), (f64::from_bits(0xC0322D66035F7C0C_u64), f64::from_bits(0xC02CABF1BE0B0DCC_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4031232E827C6822_u64), y: f64::from_bits(0xC0337803BCE535FD_u64),
                polygon: &[(f64::from_bits(0x402F55BAE9DEF6D8_u64), f64::from_bits(0x4020D88FA51B5742_u64)), (f64::from_bits(0xC00017FDD21A5930_u64), f64::from_bits(0xC019D317E1BEF9DE_u64)), (f64::from_bits(0x4004D2B36E90ECE0_u64), f64::from_bits(0xC033F3F349F52556_u64)), (f64::from_bits(0xC033A230C617E63D_u64), f64::from_bits(0x3FE76990570EEF60_u64)), (f64::from_bits(0xC009E5C0A3DCDC58_u64), f64::from_bits(0xC0203BFE3E180052_u64)), (f64::from_bits(0xC02BAD22E97CCD4C_u64), f64::from_bits(0x3FE3372DE73C4C60_u64)), (f64::from_bits(0xC0328B7EC50AA22A_u64), f64::from_bits(0xC031EA867012F867_u64)), (f64::from_bits(0xC00BA1F7FB914900_u64), f64::from_bits(0xC025E21ADAC0D43A_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40230B08E530D9E0_u64), y: f64::from_bits(0x40214BC8E592A988_u64),
                polygon: &[(f64::from_bits(0x4012BC06167CB948_u64), f64::from_bits(0x4030B0038E616A10_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4029731AF708ECE4_u64), y: f64::from_bits(0xC02615EC2AB4B86B_u64),
                polygon: &[(f64::from_bits(0xC02B6109A7B6874C_u64), f64::from_bits(0x4008E879126AADD8_u64)), (f64::from_bits(0x4020CB2C784FBD06_u64), f64::from_bits(0xC026F6DB15190384_u64)), (f64::from_bits(0x4023A92A233D41B6_u64), f64::from_bits(0x3FE024951CA6EBA0_u64)), (f64::from_bits(0x4018F420624014B8_u64), f64::from_bits(0xC033C53CEEC546F2_u64)), (f64::from_bits(0xC00C889EEF367120_u64), f64::from_bits(0x401DD6CEE15A4850_u64)), (f64::from_bits(0x4033FCC474925078_u64), f64::from_bits(0x4021FAD55C6AF8CC_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x40294E8CCC6F3C28_u64), y: f64::from_bits(0xC0228E5C8F36479A_u64),
                polygon: &[(f64::from_bits(0xC020792963F4C6D6_u64), f64::from_bits(0x401B1D55D5D08424_u64)), (f64::from_bits(0xC03195CA89E91BC6_u64), f64::from_bits(0xC00C040261445E80_u64)), (f64::from_bits(0x4016317A5651BE88_u64), f64::from_bits(0x402D161A96B99278_u64)), (f64::from_bits(0x3FDC7AADE41FBB80_u64), f64::from_bits(0x401A60DC731F3CA8_u64)), (f64::from_bits(0x401A34715A6E74D0_u64), f64::from_bits(0x4017A1EE9D032458_u64)), (f64::from_bits(0xBFFF1B541D2903E0_u64), f64::from_bits(0xC01D4C042742DA1C_u64)), (f64::from_bits(0xC02DC77C0EB0118D_u64), f64::from_bits(0x402EF686E2F56B78_u64)), (f64::from_bits(0x402605ABF4480198_u64), f64::from_bits(0x40183331B544E770_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFFD71033CC3F8E0_u64), y: f64::from_bits(0x402E3811E7ABBDA4_u64),
                polygon: &[(f64::from_bits(0xC0193623195AA7AE_u64), f64::from_bits(0xC01966F5B2A6323C_u64)), (f64::from_bits(0x402E3018367CC88C_u64), f64::from_bits(0xC03283292DA23FAB_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4036F02F7BB0DDA2_u64), y: f64::from_bits(0xC0013D25CDAB9308_u64),
                polygon: &[(f64::from_bits(0x40052AC4DCCD9290_u64), f64::from_bits(0x400E1A86EDE6F448_u64)), (f64::from_bits(0x402F56D6DF031794_u64), f64::from_bits(0x4030D195947260FA_u64)), (f64::from_bits(0xC03234214267209D_u64), f64::from_bits(0x4032F497D3F15170_u64)), (f64::from_bits(0xC030331DE2618847_u64), f64::from_bits(0x4000801F93F62E40_u64)), (f64::from_bits(0xBF622AB415EF4000_u64), f64::from_bits(0x4033287EDC7C48D0_u64)), (f64::from_bits(0xC025508F936F2EC5_u64), f64::from_bits(0xC0323AC4C58BD8A7_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4030C53640F84178_u64), y: f64::from_bits(0x4001EB3453EEDB78_u64),
                polygon: &[(f64::from_bits(0x4033E335C622569A_u64), f64::from_bits(0x3FFB25FC562CE800_u64)), (f64::from_bits(0xC02E4A19C3B4E1E4_u64), f64::from_bits(0x402C6ED95F9082D0_u64)), (f64::from_bits(0x4033D5AF181490DA_u64), f64::from_bits(0xC019562E2602E1C0_u64)), (f64::from_bits(0x401464B07BE9D340_u64), f64::from_bits(0xC0325ED1EF153F57_u64)), (f64::from_bits(0x3FFDCDA208A9CB50_u64), f64::from_bits(0x401F9526DAB010E4_u64)), (f64::from_bits(0x403219DAD19C4058_u64), f64::from_bits(0x4028D1777C12F890_u64)), (f64::from_bits(0xC0225B2E4434F4AE_u64), f64::from_bits(0x400C883DF50D9998_u64))],
                expected: true,
                tags: &["pip", "pip:concave", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0360CF26A3CDADE_u64), y: f64::from_bits(0x4030AEFD0E11446E_u64),
                polygon: &[(f64::from_bits(0xC026D1E328B6974A_u64), f64::from_bits(0xC029DDCF5D1BFFB1_u64)), (f64::from_bits(0x4008E8CE2536C030_u64), f64::from_bits(0x401EA74975DEF5C0_u64)), (f64::from_bits(0xC029BCE9A177C266_u64), f64::from_bits(0x3FB5B9BAEAE3DF00_u64)), (f64::from_bits(0x4003D13914AA87C0_u64), f64::from_bits(0xBF949958006DF400_u64)), (f64::from_bits(0xC01DB8C1DAC714F8_u64), f64::from_bits(0xC0010D06C747E368_u64)), (f64::from_bits(0xC02F2E18786A580A_u64), f64::from_bits(0xC03010C5DB30568E_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401D8E5E20B289F0_u64), y: f64::from_bits(0x4033F3403F4FD198_u64),
                polygon: &[(f64::from_bits(0xC032DB333FA09E80_u64), f64::from_bits(0x400911A3A49961F0_u64)), (f64::from_bits(0xC0197B3736526E64_u64), f64::from_bits(0xC0272874CDB70E52_u64)), (f64::from_bits(0x3FF1345B4071F300_u64), f64::from_bits(0x402A8634FD5093D8_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC0258503395DA06C_u64), y: f64::from_bits(0xC03325246CF1490A_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x403644F53A55E970_u64), y: f64::from_bits(0x402434E723A1C2E8_u64),
                polygon: &[(f64::from_bits(0xC0323C89B4E84290_u64), f64::from_bits(0x402D33D90C72AA80_u64)), (f64::from_bits(0xC02C79B20EA74F00_u64), f64::from_bits(0x401C2C9FE152B1F0_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x400FCD6CB26CE128_u64), y: f64::from_bits(0xC03278461CF7EB1C_u64),
                polygon: &[(f64::from_bits(0xC019D00D7C87D8DC_u64), f64::from_bits(0x4007D735C0ABE300_u64)), (f64::from_bits(0x402BD352698AE108_u64), f64::from_bits(0xC0198C09E3B3FD74_u64)), (f64::from_bits(0xC02B0E74168C896A_u64), f64::from_bits(0xC03210F47882AD21_u64)), (f64::from_bits(0xC017B6F208CCB014_u64), f64::from_bits(0x4033C5BC19F4B972_u64)), (f64::from_bits(0x402C976A42FCAB78_u64), f64::from_bits(0xC0265D3327079171_u64)), (f64::from_bits(0x4033B8E6D3C11E74_u64), f64::from_bits(0xC033F4B9C5434E66_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC003A935C280C200_u64), y: f64::from_bits(0x4021581D895CF1E0_u64),
                polygon: &[(f64::from_bits(0xC02F57400B7DBFBA_u64), f64::from_bits(0xC030446B3A9FBDD0_u64)), (f64::from_bits(0xC023C2694FE696E2_u64), f64::from_bits(0xC014A9FB2E75857C_u64)), (f64::from_bits(0xBFE422173457E660_u64), f64::from_bits(0x403229B718830550_u64)), (f64::from_bits(0xC02C0E654E99E11F_u64), f64::from_bits(0x4017757DC583A28C_u64)), (f64::from_bits(0x3FC1A2D0008B7680_u64), f64::from_bits(0xC02DEAEC8A5ABDD8_u64)), (f64::from_bits(0x4033D80F85524950_u64), f64::from_bits(0x4030A0292E34097A_u64)), (f64::from_bits(0xC018A9CF8149FAA4_u64), f64::from_bits(0x402DA097BEF91E48_u64))],
                expected: true,
                tags: &["pip", "pip:concave", "pip:inside", "pip:negative_coords"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x402744BDD50B7664_u64), y: f64::from_bits(0xC025A71B79C5937C_u64),
                polygon: &[(f64::from_bits(0x40164345AE4742D0_u64), f64::from_bits(0xC0163907D54BE728_u64)), (f64::from_bits(0xC031E68375706366_u64), f64::from_bits(0xBFF57CA643010650_u64)), (f64::from_bits(0x4009245D736055C0_u64), f64::from_bits(0xC0222E4D928663E4_u64)), (f64::from_bits(0x40087EFC9A6F3288_u64), f64::from_bits(0xC0335B67AFC68255_u64)), (f64::from_bits(0xC023C6A4E97CBCFC_u64), f64::from_bits(0xBFE7AFACCB7E44C0_u64)), (f64::from_bits(0xBFE6F8B315ED05C0_u64), f64::from_bits(0x40207BC1AAF8327A_u64)), (f64::from_bits(0xC025781D0227BFE9_u64), f64::from_bits(0xC0218AF40AE329F6_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02B560DF45D5594_u64), y: f64::from_bits(0x403335410931ECCC_u64),
                polygon: &[(f64::from_bits(0xC01D3CCC138E1456_u64), f64::from_bits(0x402B3A513980155C_u64)), (f64::from_bits(0x4033C100AFF20B46_u64), f64::from_bits(0x40305F58FAD89140_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC01C0896B02D3228_u64), y: f64::from_bits(0x4035A5DD953CA2D4_u64),
                polygon: &[],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4035150F6068B1F2_u64), y: f64::from_bits(0x402C9022D89BEC58_u64),
                polygon: &[(f64::from_bits(0x401C84CC282E69B0_u64), f64::from_bits(0x40202687290E61A2_u64)), (f64::from_bits(0xC02ECECBAEC41CCB_u64), f64::from_bits(0xC021A59647F7764D_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x401225EAE071D75C_u64), y: f64::from_bits(0xC02416772F3140E1_u64),
                polygon: &[(f64::from_bits(0x3FFC0C0FC7131A10_u64), f64::from_bits(0x402B78FBC2BEC248_u64))],
                expected: false,
                tags: &["pip", "pip:degenerate", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC02C5E3F16A09EF2_u64), y: f64::from_bits(0xC031AAB8467676A8_u64),
                polygon: &[(f64::from_bits(0xC0131FD5F00D3E38_u64), f64::from_bits(0x402111C09DC556FC_u64)), (f64::from_bits(0xC01F7E852B616F04_u64), f64::from_bits(0x402A36DC9763FC98_u64)), (f64::from_bits(0xC02EF261E8AF3288_u64), f64::from_bits(0xC030F86C29B1CA24_u64)), (f64::from_bits(0xC0337B6C72369397_u64), f64::from_bits(0x4001F4E31FBC42E8_u64)), (f64::from_bits(0xBFEA37313F877380_u64), f64::from_bits(0x3FF6BB4939E1DF60_u64)), (f64::from_bits(0xBFF1D08AFF768D30_u64), f64::from_bits(0x402E3380E71CDE34_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xBFD6EC8F21B4C540_u64), y: f64::from_bits(0xC0293FC99CD9D9E4_u64),
                polygon: &[(f64::from_bits(0x4021A0A7A454C4D2_u64), f64::from_bits(0xC02A45A41BE2E52C_u64)), (f64::from_bits(0x4032B2D62D9095DA_u64), f64::from_bits(0xBFEC41367FD7E520_u64)), (f64::from_bits(0xC012946A6C37A11C_u64), f64::from_bits(0xC0166B6384A0B914_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC021196EB69D2408_u64), y: f64::from_bits(0xBFECD1F12966D760_u64),
                polygon: &[(f64::from_bits(0xC0321E0E6AB2300F_u64), f64::from_bits(0x3FD786ACC3E8FC00_u64)), (f64::from_bits(0xC02A374D798DBF4C_u64), f64::from_bits(0x401D33F40062475C_u64)), (f64::from_bits(0xC02B8DE0B81E6E4C_u64), f64::from_bits(0x4004B1DF92F48AB8_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC031DE11A16AB0A6_u64), y: f64::from_bits(0xC02754BE4052376B_u64),
                polygon: &[(f64::from_bits(0x3FEDE23637FD5580_u64), f64::from_bits(0x4032FBD5C0C71624_u64)), (f64::from_bits(0x4021A42949484364_u64), f64::from_bits(0xC025DDEE737EA75E_u64)), (f64::from_bits(0xC023C49ED871EFCA_u64), f64::from_bits(0x40296175CDB2CD5C_u64)), (f64::from_bits(0x4026233DFD681048_u64), f64::from_bits(0xC02C7F0CC7E84E42_u64)), (f64::from_bits(0x4028C7EE98581CE8_u64), f64::from_bits(0xC0202BBA572C6226_u64)), (f64::from_bits(0x40057D0E8D6B4390_u64), f64::from_bits(0x402F5DC374C80B10_u64)), (f64::from_bits(0x4030BAD0FF569080_u64), f64::from_bits(0xC02A0BBA92F44C1C_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0x4033344E53445A6C_u64), y: f64::from_bits(0x4038DBA98310BA50_u64),
                polygon: &[(f64::from_bits(0x40329B17A3AA9768_u64), f64::from_bits(0x4018853E7A337A3C_u64)), (f64::from_bits(0x402507BF8D3258C4_u64), f64::from_bits(0x4029C4AEC55A8F6C_u64)), (f64::from_bits(0xBFEFE9B2CDC8C2E0_u64), f64::from_bits(0xC013D9BAF4E1D264_u64)), (f64::from_bits(0x4027D796A279A144_u64), f64::from_bits(0x40135301CF78D3A0_u64))],
                expected: false,
                tags: &["pip", "pip:negative_coords", "pip:outside"],
            },
            FrozenPipCase {
                x: f64::from_bits(0xC00853BE7DF4C5E8_u64), y: f64::from_bits(0x4038DAF23491E87A_u64),
                polygon: &[(f64::from_bits(0x40028C6ABDC6F360_u64), f64::from_bits(0xC00C58977ADAB940_u64)), (f64::from_bits(0xC020F13F2C275CB6_u64), f64::from_bits(0x402432814F2757F8_u64)), (f64::from_bits(0xC013DF2095B20A3C_u64), f64::from_bits(0x3FDA28AAE2107140_u64)), (f64::from_bits(0xC01317AD2D6DEC3C_u64), f64::from_bits(0x4033D6D5CF67D470_u64)), (f64::from_bits(0xC030329575B31A84_u64), f64::from_bits(0xC020FA17957D469D_u64)), (f64::from_bits(0x402638AAD04736B4_u64), f64::from_bits(0x4010D2891E465F48_u64)), (f64::from_bits(0xC003AA5404AC7A70_u64), f64::from_bits(0x4005E01EE9F15D40_u64))],
                expected: false,
                tags: &["pip", "pip:concave", "pip:negative_coords", "pip:outside"],
            },
        ];

        struct FrozenIsoCase {
            slot: (f64, f64),
            aabbs: &'static [((f64, f64), (f64, f64))],
            expected: bool,
            tags: &'static [&'static str],
        }

        const FROZEN_ISO_GOLDEN: &[FrozenIsoCase] = &[
            FrozenIsoCase {
                slot: (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x4000000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "named:inside"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "named:inside_2"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4008000000000000_u64), f64::from_bits(0x4008000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "named:inside_3"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC008000000000000_u64), f64::from_bits(0xC008000000000000_u64)),
                aabbs: &[((f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0xBFF0000000000000_u64), f64::from_bits(0xBFF0000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "named:inside_neg"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "named:outside"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4000000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:boundary_inclusive", "iso:hit", "named:boundary_x"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x4010000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:boundary_inclusive", "iso:hit", "named:boundary_y"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:boundary_inclusive", "iso:hit", "named:boundary_corner"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4018000000000000_u64), f64::from_bits(0x4018000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64))), ((f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4022000000000000_u64), f64::from_bits(0x4022000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "iso:multiple_aabbs", "named:multi_hit"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4012000000000000_u64), f64::from_bits(0x4012000000000000_u64)),
                aabbs: &[((f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4010000000000000_u64), f64::from_bits(0x4010000000000000_u64))), ((f64::from_bits(0x4014000000000000_u64), f64::from_bits(0x4014000000000000_u64)), (f64::from_bits(0x4022000000000000_u64), f64::from_bits(0x4022000000000000_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs", "named:multi_miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x4000000000000000_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss", "named:empty"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC008000000000000_u64), f64::from_bits(0xC008000000000000_u64)),
                aabbs: &[((f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0xBFF0000000000000_u64), f64::from_bits(0xBFF0000000000000_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "named:negative"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC01D4B5BB006C237_u64), f64::from_bits(0x401AF609500EA9B8_u64)),
                aabbs: &[((f64::from_bits(0xBFFB775BD7BB7C90_u64), f64::from_bits(0xC00F73C5FCCA444C_u64)), (f64::from_bits(0x3FFF08942E0F6536_u64), f64::from_bits(0xC0017A283B210822_u64))), ((f64::from_bits(0x40106951B90ACD88_u64), f64::from_bits(0x3FE9B7F964E91FF0_u64)), (f64::from_bits(0x401B8ADEE697CF6D_u64), f64::from_bits(0x4023F5100D5FCF51_u64))), ((f64::from_bits(0xC0141676E22885A1_u64), f64::from_bits(0x40193702D776C58C_u64)), (f64::from_bits(0xBFEA70D5672BC428_u64), f64::from_bits(0x402DCD31CC7C695B_u64))), ((f64::from_bits(0x4018309E672CA240_u64), f64::from_bits(0x40067BE570ED32C4_u64)), (f64::from_bits(0x4029C89D83F33DB2_u64), f64::from_bits(0x40241B3FCD3C515A_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401C026119A1684C_u64), f64::from_bits(0x403479F484EA2F10_u64)),
                aabbs: &[((f64::from_bits(0x4019023B79EA8F20_u64), f64::from_bits(0x401E067B61F734D4_u64)), (f64::from_bits(0x401F0B9B5A548CB2_u64), f64::from_bits(0x402D1FC09650A1B4_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x3FFEDCE365911600_u64), f64::from_bits(0x4014FDC23DF9E7C0_u64)),
                aabbs: &[((f64::from_bits(0xC00B08C31D33633C_u64), f64::from_bits(0xC01E1EB63B2CE993_u64)), (f64::from_bits(0x400E3680912FDF28_u64), f64::from_bits(0xC01B5A52EBA12313_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401EE3F4B22A1464_u64), f64::from_bits(0xC027A636581FB11D_u64)),
                aabbs: &[((f64::from_bits(0x40066D9563ED30A8_u64), f64::from_bits(0x3FFFFB4ECDAA0EA0_u64)), (f64::from_bits(0x4023425D59031BB5_u64), f64::from_bits(0x401857A6357BA365_u64))), ((f64::from_bits(0x3FBF14294CC8B500_u64), f64::from_bits(0xC00A2DC97FA4B038_u64)), (f64::from_bits(0x4011CC00DC0F8AFA_u64), f64::from_bits(0x40038EB01CDF9592_u64))), ((f64::from_bits(0x401FC0170B85358C_u64), f64::from_bits(0x40131C68898BE202_u64)), (f64::from_bits(0x4020E18F0EA8B01C_u64), f64::from_bits(0x402319A8E935D4FD_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4024C84D489D5B14_u64), f64::from_bits(0x403329786AFA6E0A_u64)),
                aabbs: &[((f64::from_bits(0xC014E25FD4D4402E_u64), f64::from_bits(0x3FF22E6AF88DC138_u64)), (f64::from_bits(0x401169525369EB28_u64), f64::from_bits(0x40199F3E0FECDE22_u64))), ((f64::from_bits(0xC006725E26D67768_u64), f64::from_bits(0xC0129FBC955B8CFC_u64)), (f64::from_bits(0x40143C4408F5631D_u64), f64::from_bits(0xC005D401253D7174_u64))), ((f64::from_bits(0x40009F990892A864_u64), f64::from_bits(0x3FF1C65D0D5346E0_u64)), (f64::from_bits(0x401E73714ACB8898_u64), f64::from_bits(0x40033F0DC12A144A_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402AA2CF98D0F76A_u64), f64::from_bits(0x40107034CFC34284_u64)),
                aabbs: &[((f64::from_bits(0xC01A57817CADE485_u64), f64::from_bits(0xC0203C4776746D87_u64)), (f64::from_bits(0xBFEAC3276E4CE2F8_u64), f64::from_bits(0xBFD2CC4858BF4CB0_u64))), ((f64::from_bits(0xC00A61D427CE02FC_u64), f64::from_bits(0xC021F997C73BD0AC_u64)), (f64::from_bits(0x401A6E25F3D67076_u64), f64::from_bits(0xC02197361E90D55C_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40299229722F7AAA_u64), f64::from_bits(0xBFF779ABFA736838_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402AE09471634194_u64), f64::from_bits(0x4028A417CE3C3FDC_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC0131D708E256891_u64), f64::from_bits(0x4030A0FABAA2EC46_u64)),
                aabbs: &[((f64::from_bits(0xC0232C6D68E50BF0_u64), f64::from_bits(0x3FF48A050D028BF8_u64)), (f64::from_bits(0xC005D076B831E708_u64), f64::from_bits(0x4015415B00AD4B55_u64))), ((f64::from_bits(0x401287FF3383AC1C_u64), f64::from_bits(0x402264824CE49538_u64)), (f64::from_bits(0x4025118C80CC5DE3_u64), f64::from_bits(0x402A395DF459E2E0_u64))), ((f64::from_bits(0xC0185920320BC87E_u64), f64::from_bits(0xC013E2F32A641973_u64)), (f64::from_bits(0xC01250EB26AA1B41_u64), f64::from_bits(0xC00EF0BF91B5503C_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401E553CBBC72800_u64), f64::from_bits(0x402E7E4A94027048_u64)),
                aabbs: &[((f64::from_bits(0xC00F2E3387E6BA98_u64), f64::from_bits(0x401F2D589133ACF0_u64)), (f64::from_bits(0xBFE7C2619F2C7AF8_u64), f64::from_bits(0x4025E96B44B97B33_u64))), ((f64::from_bits(0xC01B15809ABD8B78_u64), f64::from_bits(0xBFF9EBB7E449CEC8_u64)), (f64::from_bits(0x3FC2372743A952E0_u64), f64::from_bits(0x3FF7F90CB07D9548_u64))), ((f64::from_bits(0xC013F4EBC36CECAD_u64), f64::from_bits(0x4023E24AA304B6BE_u64)), (f64::from_bits(0xBFC7E3AC419CE2A0_u64), f64::from_bits(0x402EBA0CF6BB3649_u64))), ((f64::from_bits(0x3FEB8AA582EB9340_u64), f64::from_bits(0x40232C04D13561AA_u64)), (f64::from_bits(0x4008E15A040D896C_u64), f64::from_bits(0x40332A45356F903C_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40294A7B2A0BA324_u64), f64::from_bits(0x401234E832F80B20_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401E9C3186A773F0_u64), f64::from_bits(0x4016A4F7462F81C4_u64)),
                aabbs: &[((f64::from_bits(0x4019F4B0CCDD6524_u64), f64::from_bits(0xC01633BC9475CD24_u64)), (f64::from_bits(0x402522BA61B8B990_u64), f64::from_bits(0x3FE6F649F61EFE38_u64))), ((f64::from_bits(0xC020E76CDC29BF0C_u64), f64::from_bits(0xBFEA0336D3DC8670_u64)), (f64::from_bits(0xC0191010ED2E4B57_u64), f64::from_bits(0x401010ECBF1BC9A0_u64))), ((f64::from_bits(0x401991D481E35398_u64), f64::from_bits(0x4022CA54F7D209B6_u64)), (f64::from_bits(0x4028BF7F3883D340_u64), f64::from_bits(0x403302B7FE17428C_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40326078C3498450_u64), f64::from_bits(0xBFEA52F17CD88F60_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x400E1BEC55262274_u64), f64::from_bits(0x403117A86924A1D4_u64)),
                aabbs: &[((f64::from_bits(0xC01A7890D2B3D262_u64), f64::from_bits(0x4022955D3EC7801E_u64)), (f64::from_bits(0xC0113A1C0EA33698_u64), f64::from_bits(0x4028DA55C732FDB2_u64))), ((f64::from_bits(0xC01A3A1BCC04DEBA_u64), f64::from_bits(0x4022E6DB88C61F1A_u64)), (f64::from_bits(0xC011C8D2B580969E_u64), f64::from_bits(0x402B93FFE929A6CC_u64))), ((f64::from_bits(0xBFF04D3C5856F2B8_u64), f64::from_bits(0xC0204355B3682543_u64)), (f64::from_bits(0x3FA290DBC40C2C60_u64), f64::from_bits(0xC0200D894BED355A_u64))), ((f64::from_bits(0x4021B031AFE0E64A_u64), f64::from_bits(0x401FE3D4C50A1AB4_u64)), (f64::from_bits(0x402CC1F63ECA7E7D_u64), f64::from_bits(0x4023851FB5A4A7CD_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x403595DFA8C8E836_u64), f64::from_bits(0x4030184AA294C638_u64)),
                aabbs: &[((f64::from_bits(0x3FE733B8EBF32820_u64), f64::from_bits(0xBFE00C11CBC68CC0_u64)), (f64::from_bits(0x3FEB12F50FB8253E_u64), f64::from_bits(0x40010FF972E5846B_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402FC293C59E2D82_u64), f64::from_bits(0x40357FFB1F1C75DE_u64)),
                aabbs: &[((f64::from_bits(0xC00A065EBCF5DF80_u64), f64::from_bits(0xC00B6654A7C667C2_u64)), (f64::from_bits(0xC005E1779849EA10_u64), f64::from_bits(0xC003843088994628_u64))), ((f64::from_bits(0x400ABE17A9FC63C8_u64), f64::from_bits(0xC023635AF1DCB7C6_u64)), (f64::from_bits(0x4011E2417959FC8C_u64), f64::from_bits(0xC004BBC9B6634BA8_u64))), ((f64::from_bits(0xC00FC61C23C13DD6_u64), f64::from_bits(0xC017ACF71211AFB7_u64)), (f64::from_bits(0x400EA0811D3B6610_u64), f64::from_bits(0x3FFDC8CB7DE54B64_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xBFC87D724095F140_u64), f64::from_bits(0x4019F2958CE1B7DC_u64)),
                aabbs: &[((f64::from_bits(0x3FE76A2A81B386D0_u64), f64::from_bits(0x4014BE0BE93D79C2_u64)), (f64::from_bits(0x40079E2E2119447C_u64), f64::from_bits(0x40275B7373B1E4CA_u64))), ((f64::from_bits(0x401C0A5339FFF274_u64), f64::from_bits(0x401784082B3A3658_u64)), (f64::from_bits(0x40269513E063D6BA_u64), f64::from_bits(0x4019D97F9BEB4881_u64))), ((f64::from_bits(0x3FE911F534C91A50_u64), f64::from_bits(0xC018F41FB0418CF2_u64)), (f64::from_bits(0x4018AE8B77E8EE5C_u64), f64::from_bits(0xC00C5A37F8F1715E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC00DD58110982CD0_u64), f64::from_bits(0x40133F67ABF8A0DC_u64)),
                aabbs: &[((f64::from_bits(0xBFFE3B01537B8C40_u64), f64::from_bits(0xC023B3A7C55F08E1_u64)), (f64::from_bits(0x401672E0A91A3DBA_u64), f64::from_bits(0xC019D54566567F1B_u64))), ((f64::from_bits(0x40149C37797EB704_u64), f64::from_bits(0x401A7224F1F0AD40_u64)), (f64::from_bits(0x4015F3850DA08D9E_u64), f64::from_bits(0x402BD6EF4C220475_u64))), ((f64::from_bits(0xC01136B392BF07E2_u64), f64::from_bits(0xC00C897401A69778_u64)), (f64::from_bits(0xBFEEC01398E12C00_u64), f64::from_bits(0x3FFD112675708AD0_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x403525EAD5988400_u64), f64::from_bits(0x401DCBD3BF93FF88_u64)),
                aabbs: &[((f64::from_bits(0xBFF263267303BEE8_u64), f64::from_bits(0xC0139A96BD800F34_u64)), (f64::from_bits(0xBFDA60C1F5955BC8_u64), f64::from_bits(0xBFE646910F94C778_u64))), ((f64::from_bits(0x400D9460C40191D0_u64), f64::from_bits(0xBFD5FD17E5822200_u64)), (f64::from_bits(0x4013EAF168123AFC_u64), f64::from_bits(0x4012D1DACB94016E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401FC240831769B8_u64), f64::from_bits(0x4033D15187190121_u64)),
                aabbs: &[((f64::from_bits(0xC020ABDF43D20E70_u64), f64::from_bits(0xBFF3FDD382E082B0_u64)), (f64::from_bits(0x3FE471CD7A68B690_u64), f64::from_bits(0x401A3E2728E5BA0B_u64))), ((f64::from_bits(0x4000B5241B33DC18_u64), f64::from_bits(0x40200049E7C54F96_u64)), (f64::from_bits(0x4021711EA032DDD3_u64), f64::from_bits(0x4022DAB0ECAE9200_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402E5A5D9297A0DC_u64), f64::from_bits(0xC0017AE2E215C8E4_u64)),
                aabbs: &[((f64::from_bits(0x401840DE8ABB5058_u64), f64::from_bits(0x401E7B1684D0D040_u64)), (f64::from_bits(0x402F42B2E7B2D766_u64), f64::from_bits(0x4027621E2B128CE0_u64))), ((f64::from_bits(0x4002AD7240B92544_u64), f64::from_bits(0xC01A827142FA553A_u64)), (f64::from_bits(0x4022E6DD190EE145_u64), f64::from_bits(0x3FF2720508CD15E8_u64))), ((f64::from_bits(0xBFF75A71A21BF828_u64), f64::from_bits(0xC00C8782F1308504_u64)), (f64::from_bits(0x40187C031AB04BC4_u64), f64::from_bits(0x400F7FA421D43400_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xBFE3850ABCFDB080_u64), f64::from_bits(0xC022C60D9457226A_u64)),
                aabbs: &[((f64::from_bits(0xBFB5E245DF966800_u64), f64::from_bits(0x3FA84D90F4816A00_u64)), (f64::from_bits(0x400D1CE0451540E2_u64), f64::from_bits(0x40199BCD6685B70C_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40323FC85FF094AC_u64), f64::from_bits(0x3FEB7FD2A9282CF0_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x400DD0F5F8ED0298_u64), f64::from_bits(0xC01BCCBB7B9CDE33_u64)),
                aabbs: &[((f64::from_bits(0xC0212D3361587F40_u64), f64::from_bits(0xC010440843459724_u64)), (f64::from_bits(0xC016D04FB8FE168E_u64), f64::from_bits(0x401403120D8BD688_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4015E73E7CBFB680_u64), f64::from_bits(0xC01C7A2EEB9583AE_u64)),
                aabbs: &[((f64::from_bits(0x40137AD008A91182_u64), f64::from_bits(0xC00EABC31054E68C_u64)), (f64::from_bits(0x402B022A5B24DFD1_u64), f64::from_bits(0x4015890AC1B5493A_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4034426B4EF9E81A_u64), f64::from_bits(0x402B554E0E8C33E6_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4026DFA678126A82_u64), f64::from_bits(0x400A37C7E85CE398_u64)),
                aabbs: &[((f64::from_bits(0x4004171BD77A2EE8_u64), f64::from_bits(0x401FD8CE13EFC41C_u64)), (f64::from_bits(0x401457D7B0EC9E1E_u64), f64::from_bits(0x402441FB880059C8_u64))), ((f64::from_bits(0x3FEC8B566568CDD0_u64), f64::from_bits(0xC004E78937370DFE_u64)), (f64::from_bits(0x40205138EAEDB213_u64), f64::from_bits(0x3FF2435FDAF9837A_u64))), ((f64::from_bits(0x4021CBBA6364CC04_u64), f64::from_bits(0xC00EC43BABE94D18_u64)), (f64::from_bits(0x40329C6408954642_u64), f64::from_bits(0x4004F5A9E21F587E_u64))), ((f64::from_bits(0x401E80A6D1289508_u64), f64::from_bits(0xC02385FF07D2F695_u64)), (f64::from_bits(0x403050C1A8C030DC_u64), f64::from_bits(0xC00F877F8CB20970_u64))), ((f64::from_bits(0xC007AD04068088B8_u64), f64::from_bits(0x400800665DD733DC_u64)), (f64::from_bits(0x3FF146C227758E5C_u64), f64::from_bits(0x40223383171BC3F4_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4031C750BC016E0E_u64), f64::from_bits(0x40340E83D6D5276C_u64)),
                aabbs: &[((f64::from_bits(0x401428898E262784_u64), f64::from_bits(0xC016F636881B4440_u64)), (f64::from_bits(0x401C7AFD826B1D70_u64), f64::from_bits(0xC000E706C8D76DFC_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x3FB2383D9112C500_u64), f64::from_bits(0x401415621E4B876C_u64)),
                aabbs: &[((f64::from_bits(0x4015264DAA558BDA_u64), f64::from_bits(0x401B5CE857CC2030_u64)), (f64::from_bits(0x401800E04B9CABC7_u64), f64::from_bits(0x402ADC4E37E48B78_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC01E24E723FE573B_u64), f64::from_bits(0x4031DE21579A573F_u64)),
                aabbs: &[((f64::from_bits(0x4021941CDBEBB892_u64), f64::from_bits(0xBFD43E2589FA1B80_u64)), (f64::from_bits(0x402A69B020F4A89D_u64), f64::from_bits(0x4018962759D0D33E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40353E278003AAF8_u64), f64::from_bits(0x40117B1F14B0E090_u64)),
                aabbs: &[((f64::from_bits(0xC015C7E5B325820A_u64), f64::from_bits(0xBFFF690DC8DCC128_u64)), (f64::from_bits(0xBFE2B77503CABA20_u64), f64::from_bits(0x401A392878247774_u64))), ((f64::from_bits(0x400ED6CF9FE3A184_u64), f64::from_bits(0xC014DDF3ACBBABBA_u64)), (f64::from_bits(0x402ABB8B02EFDFC0_u64), f64::from_bits(0x401054509A5667D4_u64))), ((f64::from_bits(0x401C9FC719BC45D8_u64), f64::from_bits(0xBFC2BF2DFC49F4C0_u64)), (f64::from_bits(0x4027C6B1B99CF23E_u64), f64::from_bits(0x400F598B5EF6B10E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC01C0E1974635254_u64), f64::from_bits(0x4031244777875C42_u64)),
                aabbs: &[((f64::from_bits(0xBFB0DACB6C9B7700_u64), f64::from_bits(0xC012D4E1194743B1_u64)), (f64::from_bits(0x3FF39337E53017E6_u64), f64::from_bits(0xC0091E796FFDB1BE_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401C9E77379355B8_u64), f64::from_bits(0x402CD35D4A817ECE_u64)),
                aabbs: &[((f64::from_bits(0xBFF2D8870DD6A360_u64), f64::from_bits(0xC0207F8AF4813816_u64)), (f64::from_bits(0x3FFC92E5E721334C_u64), f64::from_bits(0xC000FE26E38E202A_u64))), ((f64::from_bits(0xC013342A60AFC9DC_u64), f64::from_bits(0xC00E2E173F0DC7B0_u64)), (f64::from_bits(0xBFF0448420663EE8_u64), f64::from_bits(0xBFF23C58F1EC3D74_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40283A0F358F59DA_u64), f64::from_bits(0xC0027F86DFD19A38_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC02046C75D0A0F02_u64), f64::from_bits(0x401686FFC8641EBC_u64)),
                aabbs: &[((f64::from_bits(0x4020BAF7295BC3C0_u64), f64::from_bits(0x401053DE188E4594_u64)), (f64::from_bits(0x40263956E71847BA_u64), f64::from_bits(0x40247C4532A818E9_u64))), ((f64::from_bits(0x402006D3D6689ADA_u64), f64::from_bits(0x40220E89A70FB4FE_u64)), (f64::from_bits(0x402F6074D52976C7_u64), f64::from_bits(0x40243553372B94BD_u64))), ((f64::from_bits(0xC0047DB45C8E2B80_u64), f64::from_bits(0xBFDB439E38914780_u64)), (f64::from_bits(0x3FE766A0DDE48F78_u64), f64::from_bits(0x401CA474EC6FD148_u64))), ((f64::from_bits(0xBFC1F6EB4A981380_u64), f64::from_bits(0x4023245713193EA2_u64)), (f64::from_bits(0xBFAFCAFB29C908A0_u64), f64::from_bits(0x4031A668390B410B_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402887F2BE546738_u64), f64::from_bits(0x4033E95121B7235C_u64)),
                aabbs: &[((f64::from_bits(0x401C1FA383D2ABC0_u64), f64::from_bits(0xC01EC92479E30BA6_u64)), (f64::from_bits(0x4029390A074EF8D5_u64), f64::from_bits(0xC01B9EF44AAEB828_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4019025EC8CE2D60_u64), f64::from_bits(0xBFF0158E95F54E00_u64)),
                aabbs: &[((f64::from_bits(0x4013706A3E9C1918_u64), f64::from_bits(0xC01C833DC181BAD6_u64)), (f64::from_bits(0x401B50CA53590D4C_u64), f64::from_bits(0x3FEEB74E5DA50570_u64))), ((f64::from_bits(0xC0221DE19F9BB003_u64), f64::from_bits(0x401ED332D46A93EC_u64)), (f64::from_bits(0xC01981638C2012BC_u64), f64::from_bits(0x4031AABD2B186F3A_u64))), ((f64::from_bits(0xC01F80EC8444140F_u64), f64::from_bits(0xC0202754194C3427_u64)), (f64::from_bits(0xC008EC6AC4540C1E_u64), f64::from_bits(0xC013F3037CA57A86_u64))), ((f64::from_bits(0x40070D54BA02B5FC_u64), f64::from_bits(0xC00F8D3C4BE197B6_u64)), (f64::from_bits(0x4018C10094C4A81C_u64), f64::from_bits(0xC00E38643981BA93_u64))), ((f64::from_bits(0xC020758C0F14BE5B_u64), f64::from_bits(0xC023E022E0D4102E_u64)), (f64::from_bits(0xC00CED9025492026_u64), f64::from_bits(0xBFF2D8CC64198C18_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40263FAF8D54E3E6_u64), f64::from_bits(0x4030FE9EA427B4ED_u64)),
                aabbs: &[((f64::from_bits(0x40210DBD22D418BC_u64), f64::from_bits(0xC021B65A2EA5B0D2_u64)), (f64::from_bits(0x402ACC661B0FB44D_u64), f64::from_bits(0xC00C1CE3301FCDE0_u64))), ((f64::from_bits(0xBFE47171783F5500_u64), f64::from_bits(0x400131666E9500E8_u64)), (f64::from_bits(0x3FE2E011BCBFCF92_u64), f64::from_bits(0x4025A37DF99EE8CF_u64))), ((f64::from_bits(0x401A7AF9F4A93244_u64), f64::from_bits(0xC01BAE8030613EBD_u64)), (f64::from_bits(0x403030C361C10324_u64), f64::from_bits(0xBFC2EE613899A380_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC011CEC66946F38C_u64), f64::from_bits(0xBFE76C759EF8DA80_u64)),
                aabbs: &[((f64::from_bits(0x400C8CD26001CAA4_u64), f64::from_bits(0x401DF162CCF328D8_u64)), (f64::from_bits(0x40261B945F0CE1A6_u64), f64::from_bits(0x402EDBB17DB030F0_u64))), ((f64::from_bits(0xC01F5D754BD9FD22_u64), f64::from_bits(0x40153A1779CF96AC_u64)), (f64::from_bits(0x3FC5448D6DC55880_u64), f64::from_bits(0x40246636E0B12670_u64))), ((f64::from_bits(0xBFFCC5AD5F730E20_u64), f64::from_bits(0x4017D42E01A1471A_u64)), (f64::from_bits(0x4013CCBE1B74654E_u64), f64::from_bits(0x402773EB8869314A_u64))), ((f64::from_bits(0x3FF415A8241087D8_u64), f64::from_bits(0x4012C350E20C4406_u64)), (f64::from_bits(0x401D1CFEDBA9BAD9_u64), f64::from_bits(0x4028D07B8D5CD56E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC021454B90E76FD0_u64), f64::from_bits(0xC0141F1F04375AFF_u64)),
                aabbs: &[((f64::from_bits(0x40093D73AA5901CC_u64), f64::from_bits(0xBFE2A0AE66D1B720_u64)), (f64::from_bits(0x40261E42EE6E3734_u64), f64::from_bits(0x3FF872EB10FF4694_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC026639CAF278B79_u64), f64::from_bits(0x4019A09480F7D0F4_u64)),
                aabbs: &[((f64::from_bits(0xBFE49451EF5869D0_u64), f64::from_bits(0xBFF33F61EE920900_u64)), (f64::from_bits(0x40081393FC4A0384_u64), f64::from_bits(0x4009554C30E41B1E_u64))), ((f64::from_bits(0xC021E6E76501546E_u64), f64::from_bits(0x40226BA2309BFDF8_u64)), (f64::from_bits(0xC019D5002CFB534E_u64), f64::from_bits(0x40279AA189BCB784_u64))), ((f64::from_bits(0x401F1977029D9270_u64), f64::from_bits(0x401D79692F1ED13C_u64)), (f64::from_bits(0x4026C8D6CA61A442_u64), f64::from_bits(0x40274E68DB86AA0F_u64))), ((f64::from_bits(0x40107F4030754B58_u64), f64::from_bits(0x3FE5F03ADCC53EA0_u64)), (f64::from_bits(0x4022AD33FD199DD9_u64), f64::from_bits(0x4020AFBC58D613DC_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC00F1323A9ECF21C_u64), f64::from_bits(0xC007B5F9FC91EBFC_u64)),
                aabbs: &[((f64::from_bits(0x401009FFCDEB2FE8_u64), f64::from_bits(0xC00C95C667C71114_u64)), (f64::from_bits(0x4027ADC2139FE302_u64), f64::from_bits(0x40151BFAF5F9880A_u64))), ((f64::from_bits(0x4023536CD0EE74D4_u64), f64::from_bits(0xC006A909BC483138_u64)), (f64::from_bits(0x402F7EBBF414F6F3_u64), f64::from_bits(0x3FD59DC5DDA82E00_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC003E1DB997D9980_u64), f64::from_bits(0xC014718D5E9BA4B5_u64)),
                aabbs: &[((f64::from_bits(0x4020ECD9DA3B84E4_u64), f64::from_bits(0xC01F2670C0B795DE_u64)), (f64::from_bits(0x402167093C7A5743_u64), f64::from_bits(0xC019A59EC17268C2_u64))), ((f64::from_bits(0x3FC32273F0F9EC00_u64), f64::from_bits(0x40117C7B5072CF50_u64)), (f64::from_bits(0x4022A6A4DB3B4AB7_u64), f64::from_bits(0x4011C71646E53D6E_u64))), ((f64::from_bits(0xC023B01B2F225E3A_u64), f64::from_bits(0xC002CB02F47D7F92_u64)), (f64::from_bits(0xC00A2ACFE58B1474_u64), f64::from_bits(0x3FFA3D5EF1020240_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x403287EC7F233EE4_u64), f64::from_bits(0x402AEEFDE9DFF226_u64)),
                aabbs: &[((f64::from_bits(0xC023469BB6F7A277_u64), f64::from_bits(0x40219347EAC35724_u64)), (f64::from_bits(0xC013D65A8B4C8A53_u64), f64::from_bits(0x40249341CBF4043F_u64))), ((f64::from_bits(0xC016518766610800_u64), f64::from_bits(0xBFF8E0C00C01DF48_u64)), (f64::from_bits(0xBFFF66A76049EEF4_u64), f64::from_bits(0x4016364DD4A47086_u64))), ((f64::from_bits(0x401FA6047678EC40_u64), f64::from_bits(0xBFE3951D78D4D420_u64)), (f64::from_bits(0x402343C362FFCD7F_u64), f64::from_bits(0x3FFDDD8E018C64E8_u64))), ((f64::from_bits(0xC0140EC35CE2E00E_u64), f64::from_bits(0xC01FD348D56772E2_u64)), (f64::from_bits(0x3FC4840E775EB660_u64), f64::from_bits(0xC0013477B83B1BDE_u64))), ((f64::from_bits(0xC00C49BDFAFB0878_u64), f64::from_bits(0xC0132046EEEA6450_u64)), (f64::from_bits(0x3FD7D57B58CACC10_u64), f64::from_bits(0xBFD011FD9E513A40_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x400D10249FF8C8A8_u64), f64::from_bits(0x4000DE9E1D6572C0_u64)),
                aabbs: &[((f64::from_bits(0xC017052E7BDE3C1F_u64), f64::from_bits(0xC01FA49D39AD4F9F_u64)), (f64::from_bits(0xC0016E9B70995963_u64), f64::from_bits(0xBFE86A333BCE0798_u64))), ((f64::from_bits(0xC018F397DA74D992_u64), f64::from_bits(0x401547149743B01C_u64)), (f64::from_bits(0xC00FB6E896D08F27_u64), f64::from_bits(0x4024C32AE891D408_u64))), ((f64::from_bits(0xC01AF8AD458C9E38_u64), f64::from_bits(0x40212EFD92E0E4EE_u64)), (f64::from_bits(0x40085BBB28F80E4C_u64), f64::from_bits(0x402D8E5911E7066A_u64))), ((f64::from_bits(0xBFCD934798915780_u64), f64::from_bits(0x401C2E8D6452E1E0_u64)), (f64::from_bits(0x401B90DC070D56D8_u64), f64::from_bits(0x402E687A4BCBD2BD_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40339BAC71A3AE5E_u64), f64::from_bits(0xBFF2268FD6C35790_u64)),
                aabbs: &[((f64::from_bits(0x3FEA60636541D4C0_u64), f64::from_bits(0x3FFA0394F36EEE80_u64)), (f64::from_bits(0x4022812F1ED3BCAA_u64), f64::from_bits(0x40018BB703FB4353_u64))), ((f64::from_bits(0xC0206F0DA4AEB340_u64), f64::from_bits(0x4003EC2C9F5B7B34_u64)), (f64::from_bits(0xC01580B46F899904_u64), f64::from_bits(0x402094D88C5C929C_u64))), ((f64::from_bits(0xC002C11E0AEDDFA0_u64), f64::from_bits(0xC022A2473038D87B_u64)), (f64::from_bits(0x401792A995F76AAA_u64), f64::from_bits(0xC01DCB4DEB67B6E8_u64))), ((f64::from_bits(0xC00AA02B8B4C3E7C_u64), f64::from_bits(0x40137B0F81A2D77A_u64)), (f64::from_bits(0x40173F77CF00E812_u64), f64::from_bits(0x402ADE8CBF2B3E36_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40359DEFA4C0398A_u64), f64::from_bits(0x4000CAC209575738_u64)),
                aabbs: &[((f64::from_bits(0x3FF4627A3A594D38_u64), f64::from_bits(0x40227A829023A8FC_u64)), (f64::from_bits(0x4010D21E15D54853_u64), f64::from_bits(0x40309A3EF999D753_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401A08BC4B464560_u64), f64::from_bits(0x402301233987EEEA_u64)),
                aabbs: &[((f64::from_bits(0x3FF564A8C7F701E8_u64), f64::from_bits(0xBFF739C08399A9E8_u64)), (f64::from_bits(0x4024490E3F55C579_u64), f64::from_bits(0x3FFA561FEDB06690_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40108FF1B453E5F0_u64), f64::from_bits(0xC0126451B2AA67B8_u64)),
                aabbs: &[((f64::from_bits(0x401585124BDF0ACC_u64), f64::from_bits(0x3FE2455B5BCE8BA0_u64)), (f64::from_bits(0x40215D32BD44C4D6_u64), f64::from_bits(0x40247BB5A226C475_u64))), ((f64::from_bits(0xC00BA9939740B588_u64), f64::from_bits(0xC023CE8E5457A3D0_u64)), (f64::from_bits(0x4018B55826E47334_u64), f64::from_bits(0xC0005573085D257A_u64))), ((f64::from_bits(0xC0209A2CC7300948_u64), f64::from_bits(0x3FFBA5FB748FC3F8_u64)), (f64::from_bits(0xC00A65CEC0A3711C_u64), f64::from_bits(0x4025D9B0E27CC50A_u64))), ((f64::from_bits(0xC0208292E9F087F8_u64), f64::from_bits(0x40146504B7B36A7A_u64)), (f64::from_bits(0xC01ABFFBD868C406_u64), f64::from_bits(0x402B19D9DB58C087_u64))), ((f64::from_bits(0xBFDFD3130D2D5A40_u64), f64::from_bits(0x40211A1A06AC8C4C_u64)), (f64::from_bits(0x401E976DD261E9F6_u64), f64::from_bits(0x4030D4545824D8BE_u64)))],
                expected: true,
                tags: &["iso", "iso:hit", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4032B125C98098CC_u64), f64::from_bits(0xC015B6526AEE3A98_u64)),
                aabbs: &[((f64::from_bits(0x40182074C52EFD44_u64), f64::from_bits(0xBFFA0BF826D03468_u64)), (f64::from_bits(0x402BC6F011B01584_u64), f64::from_bits(0x4019E2D8C40FB1A6_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4016FABFE917002C_u64), f64::from_bits(0xC01A04F9991601AF_u64)),
                aabbs: &[((f64::from_bits(0x4006AB3EC97A0F60_u64), f64::from_bits(0xBFFBDF1B90BC3AC0_u64)), (f64::from_bits(0x401543AA961A0E6D_u64), f64::from_bits(0x3FEFE193662C8910_u64))), ((f64::from_bits(0xC0109EE0CEADFB7F_u64), f64::from_bits(0xC01A1131D691F64E_u64)), (f64::from_bits(0x3FD5C7C450620390_u64), f64::from_bits(0x3FA8ECEB049A2900_u64))), ((f64::from_bits(0x402290ADF3E6B8E0_u64), f64::from_bits(0xC012CBB78F3D0D6A_u64)), (f64::from_bits(0x4023DA63E650AB9A_u64), f64::from_bits(0x4004074EB7E92DE4_u64))), ((f64::from_bits(0xBFE056DF3AE6B010_u64), f64::from_bits(0x402042CF35432D3E_u64)), (f64::from_bits(0x400AEE10F342416C_u64), f64::from_bits(0x402DCEFBC1C8FD6F_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC01205D4F2330051_u64), f64::from_bits(0x4034B902C51E0A82_u64)),
                aabbs: &[((f64::from_bits(0xC00A3E00D3D26398_u64), f64::from_bits(0xC01713328381B831_u64)), (f64::from_bits(0x4010A784AF6009B5_u64), f64::from_bits(0xBFEDC50000AFC6B0_u64))), ((f64::from_bits(0xC01E3E12B7DCC2B0_u64), f64::from_bits(0x4018BB1E6E56D9EC_u64)), (f64::from_bits(0xBFF2ED1318371EC0_u64), f64::from_bits(0x402E7DAEA75070F0_u64))), ((f64::from_bits(0x3FCBB053B4C2E280_u64), f64::from_bits(0x40103C615504B570_u64)), (f64::from_bits(0x401CA59F5CC987A1_u64), f64::from_bits(0x40118835E4415AE4_u64))), ((f64::from_bits(0xC022FE94FC843A8A_u64), f64::from_bits(0xC0212F73933D4663_u64)), (f64::from_bits(0xC014D8BCC9EBE3A8_u64), f64::from_bits(0xC020894721C11D25_u64))), ((f64::from_bits(0x4007CFA026E428B0_u64), f64::from_bits(0x401233BB4D78300C_u64)), (f64::from_bits(0x4027327F24CF4BE9_u64), f64::from_bits(0x4025610181C51782_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402EF67B79C37A06_u64), f64::from_bits(0x4021CB820F08BC90_u64)),
                aabbs: &[((f64::from_bits(0x400710221D9EF880_u64), f64::from_bits(0xC012E7E88344D773_u64)), (f64::from_bits(0x40282669C42BCF04_u64), f64::from_bits(0xBFFDE762D1B17F3C_u64))), ((f64::from_bits(0x402148AA26AA55AA_u64), f64::from_bits(0x40192246D8993DB4_u64)), (f64::from_bits(0x40216281FBCEFC3A_u64), f64::from_bits(0x402F94DD1360DEB1_u64))), ((f64::from_bits(0x4018D0AC63ABD970_u64), f64::from_bits(0xC02384394E7DABF2_u64)), (f64::from_bits(0x40280D50F6AB4848_u64), f64::from_bits(0xC01E1BD33E379149_u64))), ((f64::from_bits(0x4019B2DF0F536078_u64), f64::from_bits(0x400BDC05D8ED346C_u64)), (f64::from_bits(0x401B2B6DC9EFEE78_u64), f64::from_bits(0x4027CF4B2384C115_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401867F52D81DA58_u64), f64::from_bits(0x40199B6D61DDDF44_u64)),
                aabbs: &[((f64::from_bits(0xC00539648351D4E4_u64), f64::from_bits(0xC0180D92EF01D89A_u64)), (f64::from_bits(0x4003D0C9E6A858B8_u64), f64::from_bits(0x400910B4D48ED250_u64))), ((f64::from_bits(0x3FF3CC7D3D5F9B90_u64), f64::from_bits(0xC01713AA16E046B6_u64)), (f64::from_bits(0x3FF52CE46CC7906D_u64), f64::from_bits(0xBFF8CA4331981758_u64))), ((f64::from_bits(0xC012EE1CD04F4CC6_u64), f64::from_bits(0x402288031AB63C9C_u64)), (f64::from_bits(0x4010673A4A07C42C_u64), f64::from_bits(0x40330A111AC2815C_u64))), ((f64::from_bits(0x4020899B45DEC7D0_u64), f64::from_bits(0xC011970B101E2790_u64)), (f64::from_bits(0x402D3EF30B357673_u64), f64::from_bits(0x3FF1EC93599D2628_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x400C45DC8F639570_u64), f64::from_bits(0x4021C6EE8C834380_u64)),
                aabbs: &[((f64::from_bits(0x40028193C71A7110_u64), f64::from_bits(0xC01008DA61731208_u64)), (f64::from_bits(0x40200417C5001E80_u64), f64::from_bits(0x4014B249916260E8_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC0236BB13517D788_u64), f64::from_bits(0x400555477598209C_u64)),
                aabbs: &[((f64::from_bits(0xC01F05DBA10D4093_u64), f64::from_bits(0xC01AD013E71401A8_u64)), (f64::from_bits(0xC01CF0950D09CFE9_u64), f64::from_bits(0xC012B7CEF31AFA36_u64))), ((f64::from_bits(0xC0155C2DD04BBF94_u64), f64::from_bits(0x3FDB35D651317980_u64)), (f64::from_bits(0xC003E35CD1AB00E8_u64), f64::from_bits(0x4023E9186C899756_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402666F23B7C07E4_u64), f64::from_bits(0x402D911CD462085E_u64)),
                aabbs: &[((f64::from_bits(0xBFEEA89CD167B2C0_u64), f64::from_bits(0x40112EEDF703EA4A_u64)), (f64::from_bits(0x40177BC5D5A6F6F9_u64), f64::from_bits(0x40153EA1A6422DF6_u64))), ((f64::from_bits(0x401471AB814FE9EC_u64), f64::from_bits(0xBFC4A034024D1BC0_u64)), (f64::from_bits(0x40281B25C07BDB76_u64), f64::from_bits(0xBFBD311F9EF1D680_u64))), ((f64::from_bits(0xBFFD356C15C10190_u64), f64::from_bits(0xC01839CFAFDF2806_u64)), (f64::from_bits(0x401DC4E63F934A4E_u64), f64::from_bits(0xC0170AE11E4A74DB_u64))), ((f64::from_bits(0xC022FD0DE0A7506A_u64), f64::from_bits(0xC00BFB4CCBBCF59C_u64)), (f64::from_bits(0xBFF52EB249997DA0_u64), f64::from_bits(0xBFF911922BD9A766_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4022CA44072D9310_u64), f64::from_bits(0x3FFD3A62B40D6858_u64)),
                aabbs: &[((f64::from_bits(0xC0181581E8222DE1_u64), f64::from_bits(0x40110275E772D3B2_u64)), (f64::from_bits(0x400E97FE30ECCAFA_u64), f64::from_bits(0x402920BE8964C79A_u64))), ((f64::from_bits(0x401B2B8546A547C0_u64), f64::from_bits(0x400A5591BC4D2684_u64)), (f64::from_bits(0x4021A1DE0EF7C9E0_u64), f64::from_bits(0x4029C0D48E6A81C0_u64))), ((f64::from_bits(0xC0060DB8B9534D4C_u64), f64::from_bits(0x4022A6453DA3F94A_u64)), (f64::from_bits(0x400F3122E41F0B36_u64), f64::from_bits(0x4032824CFDF654AF_u64))), ((f64::from_bits(0xC00F0541F62127B4_u64), f64::from_bits(0xC020983783906B58_u64)), (f64::from_bits(0x400329BCF4B5F7F4_u64), f64::from_bits(0x3FE6B7ECF2F89B30_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4019CB6BB7C47ED0_u64), f64::from_bits(0xC011B726A276559B_u64)),
                aabbs: &[((f64::from_bits(0x402179E705BAB1E8_u64), f64::from_bits(0xC00ADF3AEC455260_u64)), (f64::from_bits(0x402584564B78EAD6_u64), f64::from_bits(0x3FFC614FD5852A44_u64))), ((f64::from_bits(0x4021B957203DF348_u64), f64::from_bits(0xC014ABEFD903F032_u64)), (f64::from_bits(0x40272C4962A078D2_u64), f64::from_bits(0xBFF4BE3D486E754C_u64))), ((f64::from_bits(0x402188B357D98034_u64), f64::from_bits(0xC0103E067255E0D0_u64)), (f64::from_bits(0x402566BB8FDBC2E1_u64), f64::from_bits(0xBFA78E5C933EB300_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC0157679CF347E8E_u64), f64::from_bits(0x4017D12436429FCC_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402206CC40C1052A_u64), f64::from_bits(0x401D91F259AB9624_u64)),
                aabbs: &[((f64::from_bits(0x400C585D85AC0178_u64), f64::from_bits(0x401D16F265C1012C_u64)), (f64::from_bits(0x4019F43E37291F83_u64), f64::from_bits(0x4025F7CF536030FE_u64))), ((f64::from_bits(0x3FE18720805FA8E0_u64), f64::from_bits(0xC0120DE107B9B940_u64)), (f64::from_bits(0x4022F5BF9BED2414_u64), f64::from_bits(0xC002A305BF0FFBD0_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4034C16D48A5E650_u64), f64::from_bits(0x40342F758C02AC34_u64)),
                aabbs: &[((f64::from_bits(0xC008EFA9CB44EC2E_u64), f64::from_bits(0xC01AF4B532BCF37E_u64)), (f64::from_bits(0x400321CA80ADA7EC_u64), f64::from_bits(0x4006FA86A558107C_u64))), ((f64::from_bits(0x4021BAF2CD4031CC_u64), f64::from_bits(0xC014467EB644C8C2_u64)), (f64::from_bits(0x402597425E9D6BB4_u64), f64::from_bits(0x3FFC25F3DF3A80B8_u64))), ((f64::from_bits(0x401CC49E58F5BA5C_u64), f64::from_bits(0xC01E29D6794BE322_u64)), (f64::from_bits(0x4028B3EE5089215E_u64), f64::from_bits(0xC011999549B79116_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC0124E0C1323FBA2_u64), f64::from_bits(0x4031A0D89BCE7F92_u64)),
                aabbs: &[((f64::from_bits(0xC01DC84D4A6A8123_u64), f64::from_bits(0x3FCC3A93EE197EC0_u64)), (f64::from_bits(0xC00FE1DC48538DE4_u64), f64::from_bits(0x3FDC7966021DB234_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402F48959014F52A_u64), f64::from_bits(0x402534254EF40CB2_u64)),
                aabbs: &[((f64::from_bits(0x3FF902D7EC4239D0_u64), f64::from_bits(0x4004D39821D97894_u64)), (f64::from_bits(0x402584F135F6DB31_u64), f64::from_bits(0x4023DFDDE41A13A8_u64))), ((f64::from_bits(0xC00C2A2DDA6C4294_u64), f64::from_bits(0xBFF96A5A968420B0_u64)), (f64::from_bits(0xBF8F9748B5790C00_u64), f64::from_bits(0x3FE98009537ECED0_u64))), ((f64::from_bits(0xC00C70A27D12DDD0_u64), f64::from_bits(0x401047C41AC27414_u64)), (f64::from_bits(0x3FE84C666516C0B8_u64), f64::from_bits(0x4012800D1F9A81D3_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401E2C5A81200B34_u64), f64::from_bits(0xBFD9054FC0940DC0_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC01DD90C9996C88D_u64), f64::from_bits(0xC022A0F8A60AA890_u64)),
                aabbs: &[((f64::from_bits(0x401003047BB175D4_u64), f64::from_bits(0x3FF944457C11CF28_u64)), (f64::from_bits(0x40240D8F1B46DFD1_u64), f64::from_bits(0x401513E263CAA864_u64))), ((f64::from_bits(0xC011B22A4E7AAFB0_u64), f64::from_bits(0xC022ABCA6CDF1BEB_u64)), (f64::from_bits(0xBFB397CC817862C0_u64), f64::from_bits(0xC010F17E038059AE_u64))), ((f64::from_bits(0xC01A11E813C2B3C8_u64), f64::from_bits(0x40214DFAFA8D4260_u64)), (f64::from_bits(0x400501F9F14713B0_u64), f64::from_bits(0x4027CBD1B41D6DE6_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4031090C83C75809_u64), f64::from_bits(0x400310B579A08090_u64)),
                aabbs: &[((f64::from_bits(0x3FB2AE9AE6D6AA80_u64), f64::from_bits(0xC021860781DA5177_u64)), (f64::from_bits(0x40132AC8378791E7_u64), f64::from_bits(0xC00595F08AEE6124_u64))), ((f64::from_bits(0xC021E78E2B5BFA25_u64), f64::from_bits(0xC0210EB3B7DDDBA6_u64)), (f64::from_bits(0xC02167BCC84E1804_u64), f64::from_bits(0xC0023517A1652A54_u64))), ((f64::from_bits(0x4020581C6B6FB48E_u64), f64::from_bits(0x3FFBA1013DB5DC70_u64)), (f64::from_bits(0x402BE0F7FBA97630_u64), f64::from_bits(0x4014A63488AB309A_u64))), ((f64::from_bits(0xC017970778B8553C_u64), f64::from_bits(0x401A674831667CC8_u64)), (f64::from_bits(0x3FF7B87A6DBBC5A0_u64), f64::from_bits(0x40304375D72C70E4_u64))), ((f64::from_bits(0x4021FB92086657D4_u64), f64::from_bits(0x4000286CEB136A14_u64)), (f64::from_bits(0x40248E1E0AD60EC7_u64), f64::from_bits(0x40251017A7A0CE13_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4015CBCE42F08F28_u64), f64::from_bits(0x4029837EFC53EC56_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401AAF7998137B6C_u64), f64::from_bits(0xC0130F70DCCD74F5_u64)),
                aabbs: &[((f64::from_bits(0x401884BA0A485B04_u64), f64::from_bits(0x401A10A65F40A69C_u64)), (f64::from_bits(0x402042D9F556EAC3_u64), f64::from_bits(0x402E86DCA18E80E4_u64))), ((f64::from_bits(0xBFCC9A5C0F7E1000_u64), f64::from_bits(0x40056BA7102D24CC_u64)), (f64::from_bits(0x4015809331D3CCAD_u64), f64::from_bits(0x402268B2610547FF_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC02413941ECF2AC4_u64), f64::from_bits(0x402752099857C42E_u64)),
                aabbs: &[((f64::from_bits(0xC01D26F6AAA87F48_u64), f64::from_bits(0xBFF7D8757DBDD3E0_u64)), (f64::from_bits(0x4005398489A3A6E8_u64), f64::from_bits(0x400484F39621DC24_u64))), ((f64::from_bits(0x400CA0D075E19300_u64), f64::from_bits(0x401650A60300112C_u64)), (f64::from_bits(0x4023DF9913772908_u64), f64::from_bits(0x401D29D2C7952CF5_u64))), ((f64::from_bits(0x40088D45F84A8AB0_u64), f64::from_bits(0x400CD0968B6521AC_u64)), (f64::from_bits(0x40172298DA9AD451_u64), f64::from_bits(0x40133D8CC414C091_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402881673E18718C_u64), f64::from_bits(0x4015224CC45AACF0_u64)),
                aabbs: &[((f64::from_bits(0xC023432B38B4B988_u64), f64::from_bits(0xBFFCC305E1A50B58_u64)), (f64::from_bits(0xBFFB461E31FE1E7C_u64), f64::from_bits(0x401AFBF5CD47F69A_u64))), ((f64::from_bits(0x4015750438013670_u64), f64::from_bits(0xC01B51FD6E4694CC_u64)), (f64::from_bits(0x4021C3231CF1AF3E_u64), f64::from_bits(0xC019137E18BDDED8_u64))), ((f64::from_bits(0xC0021267A379D194_u64), f64::from_bits(0x40138F38E727D8C4_u64)), (f64::from_bits(0x3FD6B2F3D6B4AC00_u64), f64::from_bits(0x402D3B573FAB7E31_u64))), ((f64::from_bits(0xC013229FFC4029C4_u64), f64::from_bits(0xBFC3A08C9FA27A80_u64)), (f64::from_bits(0x3FE563AD553C8AE8_u64), f64::from_bits(0x40143994F18D6F48_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x401EF9C176CFEF38_u64), f64::from_bits(0x4034884351B60A6C_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4011329DE17CA554_u64), f64::from_bits(0xC0247113DBCC5AD5_u64)),
                aabbs: &[((f64::from_bits(0x401F1E403161E214_u64), f64::from_bits(0x4021AEABFECB162A_u64)), (f64::from_bits(0x402C9EDD21EF9358_u64), f64::from_bits(0x402A22959ED38671_u64))), ((f64::from_bits(0xC0199D80456B5EBE_u64), f64::from_bits(0xC0146976CBF74460_u64)), (f64::from_bits(0xBFF70A8464321D9C_u64), f64::from_bits(0x4003EDBDD88027D8_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x40295A286EC9D9C8_u64), f64::from_bits(0x40175E4297ED35A8_u64)),
                aabbs: &[((f64::from_bits(0x3FF1A739A5D0D670_u64), f64::from_bits(0xC003F29A3875D3E8_u64)), (f64::from_bits(0x402539682372A7B8_u64), f64::from_bits(0x401011D2054D86C6_u64))), ((f64::from_bits(0xC0219BA3EA6F9E0E_u64), f64::from_bits(0x40204A5DA6927294_u64)), (f64::from_bits(0xC00BC393C7245084_u64), f64::from_bits(0x4030C06405CBEBDF_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xC00B7B2C50A34134_u64), f64::from_bits(0x40334ADBA6E66540_u64)),
                aabbs: &[((f64::from_bits(0x40217E83A74C3740_u64), f64::from_bits(0xC00D905CEFB16B84_u64)), (f64::from_bits(0x4028BDB93B2DC728_u64), f64::from_bits(0x4013AF9A319BE280_u64))), ((f64::from_bits(0x40076F05CED742B8_u64), f64::from_bits(0x40160103AB06F39A_u64)), (f64::from_bits(0x40079D781CED0D04_u64), f64::from_bits(0x402C34DEE348C5A0_u64))), ((f64::from_bits(0x40238C850A241E9E_u64), f64::from_bits(0xC0027FCCB7C73494_u64)), (f64::from_bits(0x4031DF2E4F319640_u64), f64::from_bits(0xBFF11B3FDC62A1F6_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4031CCB865DB2580_u64), f64::from_bits(0x4033F7FB570B062C_u64)),
                aabbs: &[((f64::from_bits(0xC015D3451433FDDA_u64), f64::from_bits(0x3FBD9EDFCB69F480_u64)), (f64::from_bits(0xC010BF47B177341A_u64), f64::from_bits(0x400A6108BD65B9DB_u64)))],
                expected: false,
                tags: &["iso", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0xBFDEC4918308B180_u64), f64::from_bits(0x402507B4A8C91AC0_u64)),
                aabbs: &[],
                expected: false,
                tags: &["iso", "iso:empty_aabbs", "iso:miss"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4030A11E5CE9A944_u64), f64::from_bits(0xC027F2B0D4CBA57D_u64)),
                aabbs: &[((f64::from_bits(0x3FDED016CEDC1320_u64), f64::from_bits(0xBFF8E892B80C9D40_u64)), (f64::from_bits(0x401D3AFCEE95F2BA_u64), f64::from_bits(0x3FDD1078428C69C0_u64))), ((f64::from_bits(0x4023C1852E0AA3A8_u64), f64::from_bits(0xC002C999C3A9AE88_u64)), (f64::from_bits(0x403188C99D5E39F6_u64), f64::from_bits(0xBFF5E63533AC7D6E_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x4023D69A1D0B27D0_u64), f64::from_bits(0x40243CA58F9010DA_u64)),
                aabbs: &[((f64::from_bits(0xBFE8DED6A84C22A0_u64), f64::from_bits(0x4023A46BEA49A0EC_u64)), (f64::from_bits(0x401302D6129249E8_u64), f64::from_bits(0x4029273C8984600D_u64))), ((f64::from_bits(0x40114968E604BCDC_u64), f64::from_bits(0x4020CCD92D7BD684_u64)), (f64::from_bits(0x401723DEC5E1CDE9_u64), f64::from_bits(0x40285DF4CCBB13F4_u64))), ((f64::from_bits(0xBFDE2BD46CF4F920_u64), f64::from_bits(0x4020D355534346A4_u64)), (f64::from_bits(0x40214F12D0593AB0_u64), f64::from_bits(0x4025CBCCA7CB1E78_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
            FrozenIsoCase {
                slot: (f64::from_bits(0x402672AFC3E8A51E_u64), f64::from_bits(0x4031D03763DCD778_u64)),
                aabbs: &[((f64::from_bits(0x401724A3D08809B8_u64), f64::from_bits(0xC020742EDBE6CDFE_u64)), (f64::from_bits(0x4024453F5809B626_u64), f64::from_bits(0xC010A82B8E71BBC4_u64))), ((f64::from_bits(0x3FE4F2E03B47B6E0_u64), f64::from_bits(0xC01826862E540928_u64)), (f64::from_bits(0x400B249690CAEC92_u64), f64::from_bits(0x4003CAD035A63CB8_u64))), ((f64::from_bits(0xBFF5986FCFC31F08_u64), f64::from_bits(0x3FE940CC65BF88E0_u64)), (f64::from_bits(0x3FEB08311119FF70_u64), f64::from_bits(0x4017A5FAF9DA249E_u64))), ((f64::from_bits(0x3FF896D180CCFF48_u64), f64::from_bits(0xC01BE07E659A8A64_u64)), (f64::from_bits(0x4025CD3643EA8B05_u64), f64::from_bits(0xC013FC492BCC3EBF_u64)))],
                expected: false,
                tags: &["iso", "iso:miss", "iso:multiple_aabbs"],
            },
        ];

        struct FrozenPtsdCase {
            px: f64, py: f64,
            p1: (f64, f64), p2: (f64, f64),
            expected: f64,
            tags: &'static [&'static str],
        }

        const FROZEN_PTSD_GOLDEN: &[FrozenPtsdCase] = &[
            FrozenPtsdCase {
                px: f64::from_bits(0x0000000000000000_u64), py: f64::from_bits(0x0000000000000000_u64),
                p1: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)),
                p2: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)),
                expected: f64::from_bits(0x3FF6A09E667F3BCD_u64),
                tags: &["named:degen_same", "ptsd", "ptsd:degenerate_segment", "ptsd:zero_denom"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4008000000000000_u64), py: f64::from_bits(0x4010000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                expected: f64::from_bits(0x4014000000000000_u64),
                tags: &["named:degen_offset", "ptsd", "ptsd:degenerate_segment", "ptsd:zero_denom"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4014000000000000_u64), py: f64::from_bits(0x4014000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                expected: f64::from_bits(0x401C48C6001F0AC0_u64),
                tags: &["named:degen_origin", "ptsd", "ptsd:degenerate_segment", "ptsd:zero_denom"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x0000000000000000_u64), py: f64::from_bits(0x3FF0000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x4000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                expected: f64::from_bits(0x3FF0000000000000_u64),
                tags: &["named:interior", "ptsd", "ptsd:interior_projection"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3FE0000000000000_u64), py: f64::from_bits(0x3FE0000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64)),
                expected: f64::from_bits(0x0000000000000000_u64),
                tags: &["named:interior_diag", "ptsd", "ptsd:interior_projection"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFF0000000000000_u64), py: f64::from_bits(0x3FF0000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                expected: f64::from_bits(0x3FF6A09E667F3BCD_u64),
                tags: &["named:clamp_before", "ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4000000000000000_u64), py: f64::from_bits(0x3FF0000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                expected: f64::from_bits(0x3FF6A09E667F3BCD_u64),
                tags: &["named:clamp_after", "ptsd", "ptsd:clamped_after"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3FF0000000000000_u64), py: f64::from_bits(0x3FE0000000000000_u64),
                p1: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4000000000000000_u64)),
                expected: f64::from_bits(0x3FF0000000000000_u64),
                tags: &["named:vertical", "ptsd", "ptsd:interior_projection"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC014000000000000_u64), py: f64::from_bits(0xC014000000000000_u64),
                p1: (f64::from_bits(0xC024000000000000_u64), f64::from_bits(0x0000000000000000_u64)),
                p2: (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0xC024000000000000_u64)),
                expected: f64::from_bits(0x0000000000000000_u64),
                tags: &["named:negative", "ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4031B66BD18A6984_u64), py: f64::from_bits(0x403C7DBB103150AC_u64),
                p1: (f64::from_bits(0x40005F7810119FC0_u64), f64::from_bits(0x3FF2630057E64320_u64)),
                p2: (f64::from_bits(0xC0254B0677521E94_u64), f64::from_bits(0x4048D741BD4EB7E0_u64)),
                expected: f64::from_bits(0x4036131066A96F94_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0351041E430F0C7_u64), py: f64::from_bits(0xC04196464F48002A_u64),
                p1: (f64::from_bits(0xC037E46374277686_u64), f64::from_bits(0xC037F4CECEDA06F3_u64)),
                p2: (f64::from_bits(0xC031436787E66018_u64), f64::from_bits(0xC037357B7D91922E_u64)),
                expected: f64::from_bits(0x4026ED9444750807_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0439E28582AB843_u64), py: f64::from_bits(0xC0317334E348F496_u64),
                p1: (f64::from_bits(0xC032E4BBF436D895_u64), f64::from_bits(0x401BB22D78E15338_u64)),
                p2: (f64::from_bits(0xC03DD63F8282BC04_u64), f64::from_bits(0xC04575EACCBF5C02_u64)),
                expected: f64::from_bits(0x402D48C3768A6824_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03DBEAB06138C06_u64), py: f64::from_bits(0x4010FA1F1EC7C4E8_u64),
                p1: (f64::from_bits(0xC02649A29758FE8C_u64), f64::from_bits(0x403758D8C1EBD85C_u64)),
                p2: (f64::from_bits(0x403E4E52F63B2C34_u64), f64::from_bits(0xC0211CCB979476A0_u64)),
                expected: f64::from_bits(0x403AA9B793A237DC_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0440836596171C2_u64), py: f64::from_bits(0x4036CCAB46CA2CF0_u64),
                p1: (f64::from_bits(0x403990F9F528F2EC_u64), f64::from_bits(0xC024C98EB4FE1248_u64)),
                p2: (f64::from_bits(0x402FA8697DBAF540_u64), f64::from_bits(0xC034184CCADDA496_u64)),
                expected: f64::from_bits(0x40519D25C844F25A_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4044BEA2EFE3AE78_u64), py: f64::from_bits(0x4040B0BA56BDA17C_u64),
                p1: (f64::from_bits(0x403D3240DE76A208_u64), f64::from_bits(0x4046B21CBB0A3A9A_u64)),
                p2: (f64::from_bits(0xC03AB74347D0FBA5_u64), f64::from_bits(0x401219CC42D477C0_u64)),
                expected: f64::from_bits(0x40312FC3E9751135_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40372341DCD8B270_u64), py: f64::from_bits(0x403E25BD901771C8_u64),
                p1: (f64::from_bits(0xC025F1A896365070_u64), f64::from_bits(0xC04212A4A6A88D92_u64)),
                p2: (f64::from_bits(0x4029437242552350_u64), f64::from_bits(0xC043C4958E947487_u64)),
                expected: f64::from_bits(0x40519E211B5B98DF_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403489365C39D26C_u64), py: f64::from_bits(0xC048A6FA2E84D7FB_u64),
                p1: (f64::from_bits(0xC0123336CEB45BC8_u64), f64::from_bits(0xC0003248FC9633A0_u64)),
                p2: (f64::from_bits(0xC04302937E3FB859_u64), f64::from_bits(0xBFFFB0C673151CA0_u64)),
                expected: f64::from_bits(0x404AC2EEA5944CCD_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3F7B2B12CCE64000_u64), py: f64::from_bits(0xC02A2F89B84AE114_u64),
                p1: (f64::from_bits(0x4043D04BD3632C4C_u64), f64::from_bits(0x40424DB2B9A59960_u64)),
                p2: (f64::from_bits(0x404386D82CC49642_u64), f64::from_bits(0xC03982FB25DB19B6_u64)),
                expected: f64::from_bits(0x40439477506550E4_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC047B4B4AF566F98_u64), py: f64::from_bits(0xC028AD7BEEB47868_u64),
                p1: (f64::from_bits(0xC043512CE686B64A_u64), f64::from_bits(0x403485E959A7C8A0_u64)),
                p2: (f64::from_bits(0xC037B4CB54CEB34C_u64), f64::from_bits(0xC04294B1AF4700F1_u64)),
                expected: f64::from_bits(0x4030BB09767E2604_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC035A114116267F1_u64), py: f64::from_bits(0xC02350B9DFAC0F8C_u64),
                p1: (f64::from_bits(0x40378A3ACDA35888_u64), f64::from_bits(0xC00F2B07DC20EFC0_u64)),
                p2: (f64::from_bits(0xC033E1DB802566D9_u64), f64::from_bits(0x4031BCAC7D119B4C_u64)),
                expected: f64::from_bits(0x40394C964502BDD8_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC046BBD182445A2B_u64), py: f64::from_bits(0xC03D1453271BE867_u64),
                p1: (f64::from_bits(0x4032BF3C009009DC_u64), f64::from_bits(0x40393466DD41ECE8_u64)),
                p2: (f64::from_bits(0xC043EF3EEBDB3F03_u64), f64::from_bits(0xC045AD35DD520D30_u64)),
                expected: f64::from_bits(0x402B0FC5368CBF46_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3FE28C65C47E13C0_u64), py: f64::from_bits(0x402F4A3EA6E99878_u64),
                p1: (f64::from_bits(0xC04831B80967B84F_u64), f64::from_bits(0xC0194A20D38D5E58_u64)),
                p2: (f64::from_bits(0xC036851F878ECC13_u64), f64::from_bits(0xC044BEA7B4F5CDBE_u64)),
                expected: f64::from_bits(0x404A3B2CF96146F8_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC040716B4B0FD29E_u64), py: f64::from_bits(0xC0356A7B0B761F58_u64),
                p1: (f64::from_bits(0xC00A5E3724D5F0F0_u64), f64::from_bits(0xC043638D3BBB8A3A_u64)),
                p2: (f64::from_bits(0x40281195ABBDE148_u64), f64::from_bits(0x4042F00FC27CFFA0_u64)),
                expected: f64::from_bits(0x404035CE1CFBF657_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403265CB9BA29FC0_u64), py: f64::from_bits(0xC04599E7CCD1D88A_u64),
                p1: (f64::from_bits(0x402DB2FC72A6A1C8_u64), f64::from_bits(0x402AC606F8D47764_u64)),
                p2: (f64::from_bits(0xC0488FBFA682FCEA_u64), f64::from_bits(0xC0270F68CA7B04E0_u64)),
                expected: f64::from_bits(0x404B0258013B8384_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x402E82801D3E8A00_u64), py: f64::from_bits(0x404681CF9FBB3CC6_u64),
                p1: (f64::from_bits(0x4045729B503EE5C8_u64), f64::from_bits(0x401BD00485488A30_u64)),
                p2: (f64::from_bits(0x4021C52E12EA24A8_u64), f64::from_bits(0x4046EC667494CC6C_u64)),
                expected: f64::from_bits(0x4010FCD64BFB891C_u64),
                tags: &["ptsd", "ptsd:interior_projection"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03CEFF563B24C4E_u64), py: f64::from_bits(0x3FED41DA0EF98100_u64),
                p1: (f64::from_bits(0xC045EC3D8B58B377_u64), f64::from_bits(0x403B75AA2782EBAC_u64)),
                p2: (f64::from_bits(0x402EBAA72B631AC0_u64), f64::from_bits(0xC03CF10EE4B2AD99_u64)),
                expected: f64::from_bits(0x4021E05843C88610_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03E4AAD4CD39EA9_u64), py: f64::from_bits(0x4002FAA2BA991310_u64),
                p1: (f64::from_bits(0x40392B91BC494FE0_u64), f64::from_bits(0xC04234A370137036_u64)),
                p2: (f64::from_bits(0xC031A8D6A0F2B786_u64), f64::from_bits(0x3FF4694F88B239C0_u64)),
                expected: f64::from_bits(0x40295C012F2305B8_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC037E14D197931D6_u64), py: f64::from_bits(0x4043395195FAAB28_u64),
                p1: (f64::from_bits(0x403680EEC43953A4_u64), f64::from_bits(0x4046C52568A9A6AA_u64)),
                p2: (f64::from_bits(0x402C3204ABA6F170_u64), f64::from_bits(0x403220A86C9BFFE0_u64)),
                expected: f64::from_bits(0x404522174DD1DF14_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC035740770ECD57E_u64), py: f64::from_bits(0x3FDE268FC75BA180_u64),
                p1: (f64::from_bits(0xC01C4CDBA0B30318_u64), f64::from_bits(0xC0013C60C66EFB10_u64)),
                p2: (f64::from_bits(0xC045E063D50D49C1_u64), f64::from_bits(0x40417BDF0D65D1F6_u64)),
                expected: f64::from_bits(0x4020C3DF63BE7505_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC041476EE0413FCE_u64), py: f64::from_bits(0xC010AAE2AF57E568_u64),
                p1: (f64::from_bits(0x404580889F793602_u64), f64::from_bits(0x3FF4BA1006308DC0_u64)),
                p2: (f64::from_bits(0x40426D06F021968C_u64), f64::from_bits(0xC037F301CE883FA9_u64)),
                expected: f64::from_bits(0x4052840C59D4A2ED_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC00A84A066691170_u64), py: f64::from_bits(0xC028265401D88520_u64),
                p1: (f64::from_bits(0xC031923BE26140FA_u64), f64::from_bits(0xC02A1E180552B274_u64)),
                p2: (f64::from_bits(0xC015E70163000A58_u64), f64::from_bits(0x404116995F12ACC2_u64)),
                expected: f64::from_bits(0x402B222FC169CF5D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40478C4044C05032_u64), py: f64::from_bits(0xC044450E9E06847B_u64),
                p1: (f64::from_bits(0x4030C4EB49BD9280_u64), f64::from_bits(0x400712A300F9A0B0_u64)),
                p2: (f64::from_bits(0xC0215E2920909A10_u64), f64::from_bits(0xC046F64B9B4D33CB_u64)),
                expected: f64::from_bits(0x40477BF91D29F663_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC02BA1B265A87F20_u64), py: f64::from_bits(0xC0324CCC8609ED24_u64),
                p1: (f64::from_bits(0xC02A95A0948D5E54_u64), f64::from_bits(0x4022B1C727465DDC_u64)),
                p2: (f64::from_bits(0xC02A9454C8E055DC_u64), f64::from_bits(0xC0346C30BC3990F3_u64)),
                expected: f64::from_bits(0x3FE0D45F46CACE2E_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03692AE60E5589A_u64), py: f64::from_bits(0x4047DD2417EA55DC_u64),
                p1: (f64::from_bits(0xC025A119C034B2C4_u64), f64::from_bits(0x4047A4CB6290A24C_u64)),
                p2: (f64::from_bits(0xC040B819049029D8_u64), f64::from_bits(0x40306401226FEF00_u64)),
                expected: f64::from_bits(0x40237E79B590A17C_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4015C9D27B5802A8_u64), py: f64::from_bits(0x4034FD277874BD08_u64),
                p1: (f64::from_bits(0x3FF71186EA342220_u64), f64::from_bits(0x4042B1848DFA4D80_u64)),
                p2: (f64::from_bits(0x4021830BCEE62484_u64), f64::from_bits(0xC046AAF315C69A20_u64)),
                expected: f64::from_bits(0x40045D301D7EA2B5_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403242E4C2C03470_u64), py: f64::from_bits(0x4026A1DB791C5A68_u64),
                p1: (f64::from_bits(0xC0397834DFBA23C0_u64), f64::from_bits(0x403710ADD4518FB8_u64)),
                p2: (f64::from_bits(0x4040C9522F753D5E_u64), f64::from_bits(0xC0364903701C3B90_u64)),
                expected: f64::from_bits(0x40315222CA3A62F4_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC041943CA9B054AA_u64), py: f64::from_bits(0xC035163171FB065D_u64),
                p1: (f64::from_bits(0x4021E5C7A118A970_u64), f64::from_bits(0xC01658ACBF958998_u64)),
                p2: (f64::from_bits(0xC04563FE15A85118_u64), f64::from_bits(0xC014235BD0781130_u64)),
                expected: f64::from_bits(0x402FF09685D7CF87_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4012E566E247EB68_u64), py: f64::from_bits(0x401F7D77973DED60_u64),
                p1: (f64::from_bits(0xC02D3C2B63873270_u64), f64::from_bits(0x403C8735E14A98C0_u64)),
                p2: (f64::from_bits(0x4031AEDEDE832C9C_u64), f64::from_bits(0xC03828F5A6C7CF41_u64)),
                expected: f64::from_bits(0x4016C66A5705DA4A_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC02EB717847E4A50_u64), py: f64::from_bits(0x4045442A6F3E657E_u64),
                p1: (f64::from_bits(0xC03BE5527D0F7F9A_u64), f64::from_bits(0xC01503FE257A9148_u64)),
                p2: (f64::from_bits(0xC03398B8A940FEF7_u64), f64::from_bits(0x4020A6CC413B93D8_u64)),
                expected: f64::from_bits(0x40413BF51B087800_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403D83D19EFA26D0_u64), py: f64::from_bits(0xC042D38D39B00626_u64),
                p1: (f64::from_bits(0xC03EF7848CD0E143_u64), f64::from_bits(0xC045CFB8F8AAC410_u64)),
                p2: (f64::from_bits(0xC042B3E6941578A7_u64), f64::from_bits(0x40008E25BC182350_u64)),
                expected: f64::from_bits(0x404E634AC5AFD57A_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFF1C8BC81F0F300_u64), py: f64::from_bits(0x4046466C1785132A_u64),
                p1: (f64::from_bits(0xC012C5889783E2E0_u64), f64::from_bits(0x400459CF1A907E20_u64)),
                p2: (f64::from_bits(0xC047AD61F9A60326_u64), f64::from_bits(0xC03B75B1AD3BD53E_u64)),
                expected: f64::from_bits(0x40451450DA597A4C_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0330F8DF08A5BB8_u64), py: f64::from_bits(0xC039A03578B6872D_u64),
                p1: (f64::from_bits(0x403CCE3FEDFF0C94_u64), f64::from_bits(0xC02099D39A269608_u64)),
                p2: (f64::from_bits(0xC0422F5168B2D26D_u64), f64::from_bits(0x400B4FC12701A0F0_u64)),
                expected: f64::from_bits(0x40398510613E59EA_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC04130FDF7E3E78E_u64), py: f64::from_bits(0xC03F6418FB0F12CD_u64),
                p1: (f64::from_bits(0x40259C504FEFD2EC_u64), f64::from_bits(0xC044B3500A815848_u64)),
                p2: (f64::from_bits(0x4039AA5BEF057D64_u64), f64::from_bits(0xC0187A23B872F2C8_u64)),
                expected: f64::from_bits(0x4047244801638F1A_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC045C7FAD723BBE6_u64), py: f64::from_bits(0x403167FDFBEBEB4C_u64),
                p1: (f64::from_bits(0x404712BEEDC337F6_u64), f64::from_bits(0x4037DA1BAF067A8C_u64)),
                p2: (f64::from_bits(0x404111CEA686C2A2_u64), f64::from_bits(0x4045F5A837464984_u64)),
                expected: f64::from_bits(0x4054866AE569DAE1_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC036DA5D26E53434_u64), py: f64::from_bits(0xBFF5EF2AAF3F4EC0_u64),
                p1: (f64::from_bits(0x40381F87D101A220_u64), f64::from_bits(0xC0249EE0746E041C_u64)),
                p2: (f64::from_bits(0x40475720F227AAC2_u64), f64::from_bits(0xC01EB1902BC76FC8_u64)),
                expected: f64::from_bits(0x4047E8DA278334A3_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC047E9AFFFA0C08C_u64), py: f64::from_bits(0xC0443EBAED2B7306_u64),
                p1: (f64::from_bits(0xC01D2FC033988E08_u64), f64::from_bits(0xC0480DD99051CC7D_u64)),
                p2: (f64::from_bits(0x4025F8EFC49BF68C_u64), f64::from_bits(0x4048B9B5364F9E70_u64)),
                expected: f64::from_bits(0x40449E9147B79AFD_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4045A62F4E7D283A_u64), py: f64::from_bits(0x404855C71A945F50_u64),
                p1: (f64::from_bits(0xC03918F237245925_u64), f64::from_bits(0xC03FF86F64531595_u64)),
                p2: (f64::from_bits(0xC04578A0A818FEF4_u64), f64::from_bits(0x40458A5DB167082E_u64)),
                expected: f64::from_bits(0x40554C73789DA287_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC047B32ABF7D9264_u64), py: f64::from_bits(0xC045606183F2093F_u64),
                p1: (f64::from_bits(0x4030B98CFDAFF054_u64), f64::from_bits(0x40466308504CE682_u64)),
                p2: (f64::from_bits(0x400B50334DD46990_u64), f64::from_bits(0xC045D8F7F3B26311_u64)),
                expected: f64::from_bits(0x4049694C1967A0B5_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0473D28FBAA1E0E_u64), py: f64::from_bits(0x403FF39EAF4333A0_u64),
                p1: (f64::from_bits(0x4032D66C1025A284_u64), f64::from_bits(0xC032F6636B58177C_u64)),
                p2: (f64::from_bits(0x4048346779DAABD6_u64), f64::from_bits(0xC035E06F2F2FBB5A_u64)),
                expected: f64::from_bits(0x4054B42B28BA73CB_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC041939DA200B049_u64), py: f64::from_bits(0x404750337CCE64CA_u64),
                p1: (f64::from_bits(0xC046378991BA41FA_u64), f64::from_bits(0xC02B6F1B6FCBCEB0_u64)),
                p2: (f64::from_bits(0xC0400173A745EBC0_u64), f64::from_bits(0x402BF4D31A663E3C_u64)),
                expected: f64::from_bits(0x4040664D29D40238_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFF1EA040998C460_u64), py: f64::from_bits(0xC038CB388A0AC343_u64),
                p1: (f64::from_bits(0x40298CA1CDAB6FC4_u64), f64::from_bits(0xC043A80BD82075D8_u64)),
                p2: (f64::from_bits(0x404829E44BFD37FE_u64), f64::from_bits(0x403C588BCF31C888_u64)),
                expected: f64::from_bits(0x40330DA3A399AF2C_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03D1FDC7012279D_u64), py: f64::from_bits(0x402331436D4784C8_u64),
                p1: (f64::from_bits(0xC036D90DF890851F_u64), f64::from_bits(0x401DED80FF50BA18_u64)),
                p2: (f64::from_bits(0xC0327A65C94689E1_u64), f64::from_bits(0xC03CFA7D5F4669C1_u64)),
                expected: f64::from_bits(0x401A7E138722FCFF_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFEDA21C0B56A740_u64), py: f64::from_bits(0xC0456B3AA3D7D182_u64),
                p1: (f64::from_bits(0x4048A501D3FF6ED2_u64), f64::from_bits(0x403CC831D61147C4_u64)),
                p2: (f64::from_bits(0xC03B41B6FCA4206E_u64), f64::from_bits(0x4023C0E88B6A72CC_u64)),
                expected: f64::from_bits(0x404CBEBDD4EF110E_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC04028B0EA5794DF_u64), py: f64::from_bits(0xC040A87B04075C79_u64),
                p1: (f64::from_bits(0xC027594E50BFBC18_u64), f64::from_bits(0x40359A16522ED9FC_u64)),
                p2: (f64::from_bits(0xC0458ADAE2D14EA7_u64), f64::from_bits(0x4045D0BDD3EC056E_u64)),
                expected: f64::from_bits(0x404D55BF3BCA43E4_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC038DF4C7637F437_u64), py: f64::from_bits(0xC040C9B149350D8C_u64),
                p1: (f64::from_bits(0xBFF3D045EE0B1220_u64), f64::from_bits(0x404441AD94E8EB44_u64)),
                p2: (f64::from_bits(0xC020E00F3BD2AB80_u64), f64::from_bits(0x400D7766F73F24E0_u64)),
                expected: f64::from_bits(0x40445C7F153ED973_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40485838BEBAF732_u64), py: f64::from_bits(0x4005CB739FB902C0_u64),
                p1: (f64::from_bits(0xC02E95EBFFC564E8_u64), f64::from_bits(0xC03F131D81882E16_u64)),
                p2: (f64::from_bits(0x400138BCC731FBA0_u64), f64::from_bits(0x402A38501D6E81EC_u64)),
                expected: f64::from_bits(0x4047D73619C6E9D2_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4022701278C00680_u64), py: f64::from_bits(0xC03EA408132737DE_u64),
                p1: (f64::from_bits(0xC04861FA2BCE971B_u64), f64::from_bits(0x404745D2778278D8_u64)),
                p2: (f64::from_bits(0x4032E4A216C9473C_u64), f64::from_bits(0x40413D2C526BED50_u64)),
                expected: f64::from_bits(0x40507555AF36FC59_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x404114C71EDE7418_u64), py: f64::from_bits(0xC01DBC9500967D30_u64),
                p1: (f64::from_bits(0xC03F54B098E5EDF8_u64), f64::from_bits(0x40472D3A3E1A16E8_u64)),
                p2: (f64::from_bits(0x4043D2CAEFDA2CFE_u64), f64::from_bits(0xC045B4D727AAAA8A_u64)),
                expected: f64::from_bits(0x403203584A2A7F1C_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4029F94DB8209AB8_u64), py: f64::from_bits(0x3FA4191C164F4800_u64),
                p1: (f64::from_bits(0xC047C9883E1D10C3_u64), f64::from_bits(0x401B803A5D010570_u64)),
                p2: (f64::from_bits(0x402E172B64DB1F88_u64), f64::from_bits(0xC01560B84AF5A108_u64)),
                expected: f64::from_bits(0x40138F2A591E4671_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0387BBCBEFEBA07_u64), py: f64::from_bits(0x4043519B5D173D30_u64),
                p1: (f64::from_bits(0x40312771CB087970_u64), f64::from_bits(0xC03622EAAB3180E3_u64)),
                p2: (f64::from_bits(0x403BCF2A5EA127E8_u64), f64::from_bits(0x404479F44118A9D8_u64)),
                expected: f64::from_bits(0x404996A20626BB8B_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC026623139249AA0_u64), py: f64::from_bits(0x401D62F9E5C519F0_u64),
                p1: (f64::from_bits(0xC0444B53FDFB7F61_u64), f64::from_bits(0xC042607B9C791E1A_u64)),
                p2: (f64::from_bits(0x40418374776A427E_u64), f64::from_bits(0x4046BE16301A2C10_u64)),
                expected: f64::from_bits(0x40206B25B72C9C30_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40459242BD7A02D8_u64), py: f64::from_bits(0xC0418E514333D518_u64),
                p1: (f64::from_bits(0x4034303F85722C7C_u64), f64::from_bits(0xC02584DB3A1EFF38_u64)),
                p2: (f64::from_bits(0xC03C7E737B0976C8_u64), f64::from_bits(0x4043AE9B51E31814_u64)),
                expected: f64::from_bits(0x4040BB922A5770E4_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC044398DA4D8CA51_u64), py: f64::from_bits(0xC044F03A9B79C635_u64),
                p1: (f64::from_bits(0xC02E1CA8A247717C_u64), f64::from_bits(0xC041B2134E016050_u64)),
                p2: (f64::from_bits(0xC024A5D06BC44170_u64), f64::from_bits(0x402A3ABC46B7003C_u64)),
                expected: f64::from_bits(0x403A35734AA3983F_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3FF8A3769EA608E0_u64), py: f64::from_bits(0x40450E54C164BC88_u64),
                p1: (f64::from_bits(0xBFFB728D9F9906A0_u64), f64::from_bits(0xC041C2874DE4BD49_u64)),
                p2: (f64::from_bits(0x401376965AD8A4A8_u64), f64::from_bits(0xC047D638A125793A_u64)),
                expected: f64::from_bits(0x40536CCBD3172D49_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x402FF075180F8C20_u64), py: f64::from_bits(0xC0410DE4DD2A29E7_u64),
                p1: (f64::from_bits(0xBFF464076EF123A0_u64), f64::from_bits(0xC018B2E48474E1C0_u64)),
                p2: (f64::from_bits(0x40457E23EE771BE2_u64), f64::from_bits(0xC0429DFC440599C6_u64)),
                expected: f64::from_bits(0x4029EB863CACB924_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC035C2969D1CD251_u64), py: f64::from_bits(0xC0312350222D5FE4_u64),
                p1: (f64::from_bits(0x3FFFAA645189EC40_u64), f64::from_bits(0xC026B877FCB94D9C_u64)),
                p2: (f64::from_bits(0x4048125E84D8BCD8_u64), f64::from_bits(0x404550E958815F9A_u64)),
                expected: f64::from_bits(0x40386EA3433DE7F6_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4046304019EAE106_u64), py: f64::from_bits(0x4030F529F0BEE3D8_u64),
                p1: (f64::from_bits(0x403D94C0D0D7370C_u64), f64::from_bits(0x401453434D6214F8_u64)),
                p2: (f64::from_bits(0xC03DCE3522F3ACA7_u64), f64::from_bits(0xC040ADC31B4AFCEE_u64)),
                expected: f64::from_bits(0x4032F907E4AB7656_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03F0CEC82D6191C_u64), py: f64::from_bits(0x403ABA39A026FB74_u64),
                p1: (f64::from_bits(0x4030F12A0B21C59C_u64), f64::from_bits(0xC047492F6299BFC4_u64)),
                p2: (f64::from_bits(0xC034CBFB1C92573D_u64), f64::from_bits(0xC045498A4A8E1855_u64)),
                expected: f64::from_bits(0x4051839C5A6FB8B2_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40038F62E8856DD0_u64), py: f64::from_bits(0xC02FB09FBE767778_u64),
                p1: (f64::from_bits(0xBFFBEBDEF8234AC0_u64), f64::from_bits(0xC02A04A2B3B314D0_u64)),
                p2: (f64::from_bits(0xC0234C9F2DD75C60_u64), f64::from_bits(0xC0126EDEF5ED1258_u64)),
                expected: f64::from_bits(0x40143D024585860F_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403CACAEE1716BAC_u64), py: f64::from_bits(0xC04590E889952C2E_u64),
                p1: (f64::from_bits(0x4039C86DB6F63624_u64), f64::from_bits(0x40210A5A24D4C5B0_u64)),
                p2: (f64::from_bits(0x403D2A4DF18B8918_u64), f64::from_bits(0xC04130F8F2062305_u64)),
                expected: f64::from_bits(0x402186C890F3E549_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0352D83C19BD01C_u64), py: f64::from_bits(0x40445CE20E3F2CE4_u64),
                p1: (f64::from_bits(0x4046F11258CABE14_u64), f64::from_bits(0xC036ADD97C0B8BE3_u64)),
                p2: (f64::from_bits(0xC028BFDC20A7C1BC_u64), f64::from_bits(0xC03051D33BBB0630_u64)),
                expected: f64::from_bits(0x404CDC39CBB8E2B4_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03132141C95DFAC_u64), py: f64::from_bits(0x404666C4D1DF673A_u64),
                p1: (f64::from_bits(0x3FC65F5E75B74B00_u64), f64::from_bits(0xC01DD5F09AE65198_u64)),
                p2: (f64::from_bits(0x40442D0F92BA673A_u64), f64::from_bits(0x402B02355ACF03DC_u64)),
                expected: f64::from_bits(0x404B2F44910BD155_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4045E2A695620F76_u64), py: f64::from_bits(0x402DEC8F6D163970_u64),
                p1: (f64::from_bits(0xC01721022342FC30_u64), f64::from_bits(0xC04510C3807CCB60_u64)),
                p2: (f64::from_bits(0xBFD4609D04858C80_u64), f64::from_bits(0x40014C3E2152F350_u64)),
                expected: f64::from_bits(0x4046F46B37294809_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4027843100845CC0_u64), py: f64::from_bits(0x40415AC458545AB4_u64),
                p1: (f64::from_bits(0xC02AD98785AA8278_u64), f64::from_bits(0x4013D4C796F89908_u64)),
                p2: (f64::from_bits(0x40403785448718BC_u64), f64::from_bits(0x40467BAD22BFA43A_u64)),
                expected: f64::from_bits(0x401773E2EC8A9FBC_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4040318EB0DA48FC_u64), py: f64::from_bits(0xC037A632839F48AC_u64),
                p1: (f64::from_bits(0x404032B0122350AC_u64), f64::from_bits(0x403159B4767BDC2C_u64)),
                p2: (f64::from_bits(0xC0327BD6C5CAD430_u64), f64::from_bits(0x40155232FF3237A8_u64)),
                expected: f64::from_bits(0x4043F3198E3EF4A4_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403D5C11443816EC_u64), py: f64::from_bits(0x403EC33E86B21FE8_u64),
                p1: (f64::from_bits(0xC0399855CFC7F223_u64), f64::from_bits(0xBFF276F4ED3FAF80_u64)),
                p2: (f64::from_bits(0x40305BAA1758739C_u64), f64::from_bits(0xC0406C0DC517A987_u64)),
                expected: f64::from_bits(0x404D4BA2CE7B19AE_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403A614838DCC840_u64), py: f64::from_bits(0x403CFC3E3349E970_u64),
                p1: (f64::from_bits(0x402068E95242AD90_u64), f64::from_bits(0x4046C6EAB1CF2850_u64)),
                p2: (f64::from_bits(0xC0325E3F7E6C8F07_u64), f64::from_bits(0xC03615DA3181E44F_u64)),
                expected: f64::from_bits(0x4036F995E1A31A4F_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x404795AF7474EEBA_u64), py: f64::from_bits(0x402721C671C31588_u64),
                p1: (f64::from_bits(0xC048AD6C8FEE5ABD_u64), f64::from_bits(0xC01AAAC32590B460_u64)),
                p2: (f64::from_bits(0xC03247EE28E4F9CE_u64), f64::from_bits(0x40406274F840642A_u64)),
                expected: f64::from_bits(0x405133263980953B_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4047A34795CD81AE_u64), py: f64::from_bits(0xC0422ACD213962D2_u64),
                p1: (f64::from_bits(0x4031CD4C133363F0_u64), f64::from_bits(0x4041C572B48270F6_u64)),
                p2: (f64::from_bits(0xC04340459F4967AE_u64), f64::from_bits(0xC017291431294408_u64)),
                expected: f64::from_bits(0x4052D877329FD3D4_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC04755AC4BC785E9_u64), py: f64::from_bits(0xC02D241426A58688_u64),
                p1: (f64::from_bits(0x402083606D75C8D0_u64), f64::from_bits(0x4034DDDC7F825858_u64)),
                p2: (f64::from_bits(0xC036947171C0838A_u64), f64::from_bits(0x402FBA8D5A7E8098_u64)),
                expected: f64::from_bits(0x404368481662CF68_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40157DEDC39A6328_u64), py: f64::from_bits(0xC02B106C358FFF04_u64),
                p1: (f64::from_bits(0x3FE25EF1B29B7280_u64), f64::from_bits(0x403E2B4AD79B36A0_u64)),
                p2: (f64::from_bits(0x403CE926456D7E30_u64), f64::from_bits(0xC0205200D17E0B70_u64)),
                expected: f64::from_bits(0x40361ED8AA5D3232_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403D4EF17B1B7A94_u64), py: f64::from_bits(0xC0182F6DD2F55AB0_u64),
                p1: (f64::from_bits(0xC005A1CB9A100AC0_u64), f64::from_bits(0xC03B52F46E3DC73C_u64)),
                p2: (f64::from_bits(0xBFBBE88461DDF600_u64), f64::from_bits(0xC04624249DC6ADBA_u64)),
                expected: f64::from_bits(0x4043382751B769A4_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40414BD4077D9D02_u64), py: f64::from_bits(0xC02A006D9803BA0C_u64),
                p1: (f64::from_bits(0xC02C1AF554C01700_u64), f64::from_bits(0x4041D1E4692E6556_u64)),
                p2: (f64::from_bits(0x403294891B8F0BD0_u64), f64::from_bits(0xC011FC0C3CFA7E00_u64)),
                expected: f64::from_bits(0x40322171A11BB0D8_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4042212C78ECB488_u64), py: f64::from_bits(0x4023772751BCB3FC_u64),
                p1: (f64::from_bits(0x404208F054A14596_u64), f64::from_bits(0xC037B4DA6BD0CDB7_u64)),
                p2: (f64::from_bits(0x403C7EE06A3AED04_u64), f64::from_bits(0x404662B074B07E70_u64)),
                expected: f64::from_bits(0x400EEA602228D236_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC023DBA905E70B68_u64), py: f64::from_bits(0x403A062E00FD74A0_u64),
                p1: (f64::from_bits(0x4047B113E5F6DFE2_u64), f64::from_bits(0x402234BB2F1E8400_u64)),
                p2: (f64::from_bits(0x4039A9C2B2696E68_u64), f64::from_bits(0xC043796BCA1F42AC_u64)),
                expected: f64::from_bits(0x404D98E9A2AA1F4D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0434B2BECAF32AA_u64), py: f64::from_bits(0x4040319AD664F376_u64),
                p1: (f64::from_bits(0x403AFD5E76973FA0_u64), f64::from_bits(0xC04149247AD0E092_u64)),
                p2: (f64::from_bits(0x403D47FC3379C2C4_u64), f64::from_bits(0xC041D2C5A9A2EDC0_u64)),
                expected: f64::from_bits(0x40576E3817406194_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40419021626C3686_u64), py: f64::from_bits(0x40457FE6F85C6A24_u64),
                p1: (f64::from_bits(0x400957446D664420_u64), f64::from_bits(0xC03428CE4AC15351_u64)),
                p2: (f64::from_bits(0x403A18131584F674_u64), f64::from_bits(0x40425C9516BD0104_u64)),
                expected: f64::from_bits(0x4025FF297B05BE59_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC041328E366186CB_u64), py: f64::from_bits(0xC0068C568E7185A0_u64),
                p1: (f64::from_bits(0x402DCA76B4A6ADA8_u64), f64::from_bits(0x403A34582E5B00B8_u64)),
                p2: (f64::from_bits(0xC0484414AFE54F66_u64), f64::from_bits(0x403E596436E43794_u64)),
                expected: f64::from_bits(0x4040167029D3239D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4028EB2A18EEA214_u64), py: f64::from_bits(0x404026FF4B113A80_u64),
                p1: (f64::from_bits(0xC0428C3A51334660_u64), f64::from_bits(0xC0213F7B6118A840_u64)),
                p2: (f64::from_bits(0x40291B712C27BD58_u64), f64::from_bits(0x4043E1FD8C593458_u64)),
                expected: f64::from_bits(0x40151BD23562C80D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0213B9466ECD470_u64), py: f64::from_bits(0x4045FC9F6B082878_u64),
                p1: (f64::from_bits(0x400848613C09FB40_u64), f64::from_bits(0x4044C9C7F452D7A4_u64)),
                p2: (f64::from_bits(0x4047D5DFDEF2C1F8_u64), f64::from_bits(0xC04504EABB88D89C_u64)),
                expected: f64::from_bits(0x4027CA9FCA0DE115_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03D7A247452EB59_u64), py: f64::from_bits(0xC03280573EA54F80_u64),
                p1: (f64::from_bits(0x400B1C1BB4F35410_u64), f64::from_bits(0x403550784C205BF0_u64)),
                p2: (f64::from_bits(0x4022AEF1AC01460C_u64), f64::from_bits(0xC02EFCFB5D751308_u64)),
                expected: f64::from_bits(0x40436687044D3237_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0402DB5A9C1171C_u64), py: f64::from_bits(0xC01AA1F2BE9065A8_u64),
                p1: (f64::from_bits(0x404897B8F6408418_u64), f64::from_bits(0xC03EA3FF1A2D6697_u64)),
                p2: (f64::from_bits(0xC040191B87B7CE9E_u64), f64::from_bits(0x400F8A86AFC0D5F0_u64)),
                expected: f64::from_bits(0x4023A3825A9822B0_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC04012009842A3A0_u64), py: f64::from_bits(0x403D817F25C55690_u64),
                p1: (f64::from_bits(0xC001EF26FBF6CCF0_u64), f64::from_bits(0xC045247551F65795_u64)),
                p2: (f64::from_bits(0xC005E3A3D93168D0_u64), f64::from_bits(0x403405D2025B413C_u64)),
                expected: f64::from_bits(0x403EE55656E18F74_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40209B1E187821A8_u64), py: f64::from_bits(0xC03B5DDB2223E77A_u64),
                p1: (f64::from_bits(0x4045FD7FE40C051A_u64), f64::from_bits(0xC04394389F3940B3_u64)),
                p2: (f64::from_bits(0xC047AD120BB1FBE5_u64), f64::from_bits(0xC0399F6F01CC1230_u64)),
                expected: f64::from_bits(0x4019BC354248C351_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40432744A9BF948C_u64), py: f64::from_bits(0x40049DCF97171770_u64),
                p1: (f64::from_bits(0x402F72768B6116E8_u64), f64::from_bits(0xC02A48B0CA038FB8_u64)),
                p2: (f64::from_bits(0xC02C4C41FADDC6CC_u64), f64::from_bits(0xC0182AE3B107DE50_u64)),
                expected: f64::from_bits(0x403B83E86E70BB3A_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03F43BF40F74FE6_u64), py: f64::from_bits(0x4022E066CF04D060_u64),
                p1: (f64::from_bits(0xC032BB36CFE5E015_u64), f64::from_bits(0x4046876B885BFEC0_u64)),
                p2: (f64::from_bits(0x403BDFA81C5F9A24_u64), f64::from_bits(0xC03F1B890B1F450D_u64)),
                expected: f64::from_bits(0x403D482934CAC529_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4045B2487DDF48D0_u64), py: f64::from_bits(0xC042D71C4A1B7FB9_u64),
                p1: (f64::from_bits(0x404549B445EA9D16_u64), f64::from_bits(0xC015724D7B214BE0_u64)),
                p2: (f64::from_bits(0x40409C82DEF99798_u64), f64::from_bits(0x4004FCF657E75B70_u64)),
                expected: f64::from_bits(0x40402A24F3945DBA_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC01D7A26947D13D0_u64), py: f64::from_bits(0xC02C5CE4592AB688_u64),
                p1: (f64::from_bits(0x4019BFB2A3032068_u64), f64::from_bits(0x4008477CBE5493F0_u64)),
                p2: (f64::from_bits(0xC042E4F2EBAD055A_u64), f64::from_bits(0xC00067C169C458F0_u64)),
                expected: f64::from_bits(0x402F0D847542517D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFFDB854869862A0_u64), py: f64::from_bits(0x4040FDF027E4EB36_u64),
                p1: (f64::from_bits(0xC040B3E0DD2A8187_u64), f64::from_bits(0xC03EAC708FDA03F5_u64)),
                p2: (f64::from_bits(0xC044B9FAB18C9CDE_u64), f64::from_bits(0xC025CFE06C162888_u64)),
                expected: f64::from_bits(0x404DEDBE01A1ABC7_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0207FC95ADE1BE0_u64), py: f64::from_bits(0xC02C49BACB68B0F8_u64),
                p1: (f64::from_bits(0xC044A9C52F608898_u64), f64::from_bits(0x404533138A24EC3E_u64)),
                p2: (f64::from_bits(0xC046536C807C2BA3_u64), f64::from_bits(0x4032400564A3D36C_u64)),
                expected: f64::from_bits(0x40485D48CFA18534_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03C10ECA51E63C7_u64), py: f64::from_bits(0xBFF7150ED36BAAE0_u64),
                p1: (f64::from_bits(0xC0243BA871E5853C_u64), f64::from_bits(0x3FE1A013F21CF4C0_u64)),
                p2: (f64::from_bits(0xC043DF495AA48B3C_u64), f64::from_bits(0xC03C56359EC1CA8E_u64)),
                expected: f64::from_bits(0x402634F091F99C1B_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0445F6630ED0E41_u64), py: f64::from_bits(0x4034602E794854AC_u64),
                p1: (f64::from_bits(0xC047D3CE711B8EA6_u64), f64::from_bits(0x40314492EA8A719C_u64)),
                p2: (f64::from_bits(0xC036E7E35A58CABF_u64), f64::from_bits(0xC043A3C520D7BEFA_u64)),
                expected: f64::from_bits(0x401E4E0977E35391_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4040C6358FBB9590_u64), py: f64::from_bits(0x403896884246FA68_u64),
                p1: (f64::from_bits(0xC041F8EFCAF376DA_u64), f64::from_bits(0xC0389C396017364A_u64)),
                p2: (f64::from_bits(0x4038E00443F60208_u64), f64::from_bits(0xC03322611BC2A476_u64)),
                expected: f64::from_bits(0x40464982FD426A2F_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x403877654D66DAC4_u64), py: f64::from_bits(0x4018D2B677BD2600_u64),
                p1: (f64::from_bits(0x401478C084EC74C8_u64), f64::from_bits(0xC034A930B006BB66_u64)),
                p2: (f64::from_bits(0x400796BD269C5ED0_u64), f64::from_bits(0x4042CECDE911D58E_u64)),
                expected: f64::from_bits(0x403455A0BE9D7FC0_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC04487C23AD146C7_u64), py: f64::from_bits(0xBFFA2E6F6F357860_u64),
                p1: (f64::from_bits(0xBFF094FA0BE2DE80_u64), f64::from_bits(0xC04849E7687E4689_u64)),
                p2: (f64::from_bits(0xC035C219CB9DC5EC_u64), f64::from_bits(0xC03DFE0E6E69FD49_u64)),
                expected: f64::from_bits(0x404126B2B4031C35_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40310DB96135589C_u64), py: f64::from_bits(0x403233A3C0F7E474_u64),
                p1: (f64::from_bits(0x402A288BC0985138_u64), f64::from_bits(0xC021BDFD83B71244_u64)),
                p2: (f64::from_bits(0x403DFC40C91926F4_u64), f64::from_bits(0x40403E76C2880E80_u64)),
                expected: f64::from_bits(0x401A424A740C3C10_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4033AEB098357798_u64), py: f64::from_bits(0xC04654AFA964F770_u64),
                p1: (f64::from_bits(0xC03F081CDFC2D192_u64), f64::from_bits(0x40403BE6B1988F0A_u64)),
                p2: (f64::from_bits(0xC03D700F77B8F310_u64), f64::from_bits(0x4023EF6B0393ED14_u64)),
                expected: f64::from_bits(0x40525DC61E293C1E_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4044FE9C2A6A4836_u64), py: f64::from_bits(0xC033260D6074771B_u64),
                p1: (f64::from_bits(0xC016042C2A6E4F78_u64), f64::from_bits(0xC029861EFE757AB0_u64)),
                p2: (f64::from_bits(0x4013E187C8B34168_u64), f64::from_bits(0xC02D76594849BC24_u64)),
                expected: f64::from_bits(0x4042A4095DA63C1A_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03D1A5DA840DCC6_u64), py: f64::from_bits(0x4046945CA867B10C_u64),
                p1: (f64::from_bits(0xC028464258686EC4_u64), f64::from_bits(0x4046272352EE65B0_u64)),
                p2: (f64::from_bits(0xC01C0CBDC84BF3D0_u64), f64::from_bits(0xC041EC1970B9B47D_u64)),
                expected: f64::from_bits(0x4030FCB9F15C2927_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03D069CA3EB025C_u64), py: f64::from_bits(0xC021691B144B927C_u64),
                p1: (f64::from_bits(0x40485E7E7F373034_u64), f64::from_bits(0xC018C04A247CE870_u64)),
                p2: (f64::from_bits(0xC0435215E8E90D5E_u64), f64::from_bits(0xC02ACA5006FDFC3C_u64)),
                expected: f64::from_bits(0x400F1183F1D2A6D3_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC02190009F6427A4_u64), py: f64::from_bits(0x401FFE192E5B46D8_u64),
                p1: (f64::from_bits(0xC041D5FAED8B03C7_u64), f64::from_bits(0xC033E03844CC2B0C_u64)),
                p2: (f64::from_bits(0xC0431D962824C6BC_u64), f64::from_bits(0xC0313E2BD31E49A8_u64)),
                expected: f64::from_bits(0x40435AF471E94B3D_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x3FACD41B17768400_u64), py: f64::from_bits(0x403D388408B0E5F0_u64),
                p1: (f64::from_bits(0xC0427D64267DA09E_u64), f64::from_bits(0xC042BA695CFB27A4_u64)),
                p2: (f64::from_bits(0xC04264E7E7073DBA_u64), f64::from_bits(0xC025966441E381B0_u64)),
                expected: f64::from_bits(0x404B326882B148E6_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x4044235E6D13C138_u64), py: f64::from_bits(0x40485C746E15643A_u64),
                p1: (f64::from_bits(0xC005B290D16DC0D0_u64), f64::from_bits(0x4044611B669D3CBE_u64)),
                p2: (f64::from_bits(0xC032F13E9B6A06B7_u64), f64::from_bits(0xC02A4A704AB4C340_u64)),
                expected: f64::from_bits(0x4045DC26766DF506_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03A98CBC61A3C28_u64), py: f64::from_bits(0x3FF61611F441BA00_u64),
                p1: (f64::from_bits(0xC03BD0D692DE7541_u64), f64::from_bits(0x4041935FD5B20900_u64)),
                p2: (f64::from_bits(0x403C17739777D090_u64), f64::from_bits(0x40348699356AD00C_u64)),
                expected: f64::from_bits(0x40402E776718EDF8_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x402D28A989A5E328_u64), py: f64::from_bits(0xC030A340664ECEBA_u64),
                p1: (f64::from_bits(0xC031A453FD12ABAC_u64), f64::from_bits(0x402C67851E4FCFA0_u64)),
                p2: (f64::from_bits(0xC02A3B23733ACF7C_u64), f64::from_bits(0x40212AF0882E3A7C_u64)),
                expected: f64::from_bits(0x4042BAAED4DA896E_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03ECAE8F53353D0_u64), py: f64::from_bits(0x40216D5DA9172880_u64),
                p1: (f64::from_bits(0x4041C8FF36EE74D8_u64), f64::from_bits(0x402D534B457C7420_u64)),
                p2: (f64::from_bits(0xC034504C8E52E19E_u64), f64::from_bits(0xC03448B5FED05F10_u64)),
                expected: f64::from_bits(0x403E246536A73C82_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03204BF23B84B22_u64), py: f64::from_bits(0xC0305DBF61E0FCB2_u64),
                p1: (f64::from_bits(0x4040019272B2ACCC_u64), f64::from_bits(0xC044478702191545_u64)),
                p2: (f64::from_bits(0x4025040B95A4CA40_u64), f64::from_bits(0xC03CFA940AE2E992_u64)),
                expected: f64::from_bits(0x403F30B8DA0CE650_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x400EF8FC7B7959C0_u64), py: f64::from_bits(0x403599584A22B408_u64),
                p1: (f64::from_bits(0xC01A8EB0BAAAD070_u64), f64::from_bits(0xC03D570C61524ECE_u64)),
                p2: (f64::from_bits(0x4022A82202EBB1F8_u64), f64::from_bits(0xC031A8DD2919D522_u64)),
                expected: f64::from_bits(0x4043D16A29C5BDC5_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40190B8B480E79C8_u64), py: f64::from_bits(0x4037401FA2A6CE00_u64),
                p1: (f64::from_bits(0xC03196A5BDA9FB38_u64), f64::from_bits(0x400E68368E7C26A0_u64)),
                p2: (f64::from_bits(0x401E8D4B54DE5E98_u64), f64::from_bits(0x3FEFE4E835A4B240_u64)),
                expected: f64::from_bits(0x4035F72861D03931_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03444345B713FFC_u64), py: f64::from_bits(0xC03C3EF5384342FF_u64),
                p1: (f64::from_bits(0x4041A0096526788A_u64), f64::from_bits(0xC0409FB2F7612499_u64)),
                p2: (f64::from_bits(0xC042572C528DA70D_u64), f64::from_bits(0xC048FE548AA7F832_u64)),
                expected: f64::from_bits(0x4031746A024ACA71_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x404592CE31D8A5E8_u64), py: f64::from_bits(0xC039BDC29F403D5C_u64),
                p1: (f64::from_bits(0x40341D4C4D4A2908_u64), f64::from_bits(0xC031073E906CE3E4_u64)),
                p2: (f64::from_bits(0x402ACA013B282A70_u64), f64::from_bits(0x40203CD86881BB34_u64)),
                expected: f64::from_bits(0x4038A01A31CD2804_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC035072B07548C29_u64), py: f64::from_bits(0xC0278C6CE1B28628_u64),
                p1: (f64::from_bits(0x404419FC336B10F6_u64), f64::from_bits(0x4031DF638A7AC390_u64)),
                p2: (f64::from_bits(0xC04248B0087C57A3_u64), f64::from_bits(0x4040FBAA286F3710_u64)),
                expected: f64::from_bits(0x4044CA1C8E88A6D4_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC020A59A943D9D7C_u64), py: f64::from_bits(0xC048D54018C9771F_u64),
                p1: (f64::from_bits(0x400F46C13D8712F0_u64), f64::from_bits(0x4040E3B4DE02B758_u64)),
                p2: (f64::from_bits(0x4023C927F41AAA2C_u64), f64::from_bits(0xC036C02784DF7B1D_u64)),
                expected: f64::from_bits(0x4040400C32DA9DD0_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x401984E83DBDAC20_u64), py: f64::from_bits(0xC044CCCD2C257632_u64),
                p1: (f64::from_bits(0xC044BFC8608711FE_u64), f64::from_bits(0xC045FBA799DB75F8_u64)),
                p2: (f64::from_bits(0x401054DA22BFF198_u64), f64::from_bits(0x400EFFFD69EC9D10_u64)),
                expected: f64::from_bits(0x4040840CC5F802E2_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0230C42E3284138_u64), py: f64::from_bits(0x4029156D90A1077C_u64),
                p1: (f64::from_bits(0xC03C9DC7402217CF_u64), f64::from_bits(0x4048C5C71259F4F2_u64)),
                p2: (f64::from_bits(0xC0403AE048CD04E2_u64), f64::from_bits(0xC021A68878C05508_u64)),
                expected: f64::from_bits(0x40357B84574949B9_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0x40293BB551BF9FB8_u64), py: f64::from_bits(0xC043AEF0151E9D80_u64),
                p1: (f64::from_bits(0x40486DFAFB73B1A8_u64), f64::from_bits(0xC04566E904F2126A_u64)),
                p2: (f64::from_bits(0x4036C9C43C7C98A0_u64), f64::from_bits(0xC045B1CD95650DD6_u64)),
                expected: f64::from_bits(0x4025E0406D577F53_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xBFFA604EC20B63A0_u64), py: f64::from_bits(0x4043E2A0F6C46E22_u64),
                p1: (f64::from_bits(0x40285C505AD0DF30_u64), f64::from_bits(0xC03C28FEA96354AE_u64)),
                p2: (f64::from_bits(0x40454B8948991918_u64), f64::from_bits(0xC0402895843386C5_u64)),
                expected: f64::from_bits(0x405154BBE08AC82E_u64),
                tags: &["ptsd", "ptsd:clamped_before", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC0400F6CE4399060_u64), py: f64::from_bits(0x3FF27BE68754D340_u64),
                p1: (f64::from_bits(0x402CDAEAA4AF7850_u64), f64::from_bits(0xC0283A50CD7C07BC_u64)),
                p2: (f64::from_bits(0x400D5D09DB7A4780_u64), f64::from_bits(0x400DBD93C79386C0_u64)),
                expected: f64::from_bits(0x4041F0F723BBFA5A_u64),
                tags: &["ptsd", "ptsd:clamped_after", "ptsd:negative_coords"],
            },
            FrozenPtsdCase {
                px: f64::from_bits(0xC03D1122AC77894A_u64), py: f64::from_bits(0xC0194561A197D190_u64),
                p1: (f64::from_bits(0xC03C1157B22E6435_u64), f64::from_bits(0x40444471C455BD90_u64)),
                p2: (f64::from_bits(0x402DEFA5AC706E18_u64), f64::from_bits(0xC04242F070D424F9_u64)),
                expected: f64::from_bits(0x4037B7B1209DA6C5_u64),
                tags: &["ptsd", "ptsd:interior_projection", "ptsd:negative_coords"],
            },
        ];

        struct FrozenMdpCase {
            x: f64, y: f64,
            polygon: &'static [(f64, f64)],
            expected: f64,
            tags: &'static [&'static str],
        }

        const FROZEN_MDP_GOLDEN: &[FrozenMdpCase] = &[
            FrozenMdpCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x3FF0000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected: f64::from_bits(0x3FE6A09E667F3BCD_u64),
                tags: &["mdp", "named:triangle_above"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x3FE0000000000000_u64), y: f64::from_bits(0x3FE0000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x3FF0000000000000_u64), f64::from_bits(0x3FF0000000000000_u64))],
                expected: f64::from_bits(0x0000000000000000_u64),
                tags: &["mdp", "named:triangle_inside"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x4014000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x4024000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4024000000000000_u64))],
                expected: f64::from_bits(0x4014000000000000_u64),
                tags: &["mdp", "named:square_inside"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "named:degen_1"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x0000000000000000_u64), y: f64::from_bits(0x0000000000000000_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "named:degen_0"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4014000000000000_u64), y: f64::from_bits(0x3FF0000000000000_u64),
                polygon: &[(f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x0000000000000000_u64)), (f64::from_bits(0x4024000000000000_u64), f64::from_bits(0x0000000000000000_u64))],
                expected: f64::from_bits(0x3FF0000000000000_u64),
                tags: &["mdp", "mdp:collinear", "named:collinear"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC008000000000000_u64), y: f64::from_bits(0xC008000000000000_u64),
                polygon: &[(f64::from_bits(0xC014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x4014000000000000_u64), f64::from_bits(0xC014000000000000_u64)), (f64::from_bits(0x0000000000000000_u64), f64::from_bits(0x4014000000000000_u64))],
                expected: f64::from_bits(0x3FEC9F25C5BFEDD9_u64),
                tags: &["mdp", "mdp:negative_coords", "named:negative"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02E10DA1E68EF9C_u64), y: f64::from_bits(0x4037DABA57D0B280_u64),
                polygon: &[(f64::from_bits(0xC030F492754555D5_u64), f64::from_bits(0x400F87AB29CB4668_u64)), (f64::from_bits(0x4010EB1765C59E70_u64), f64::from_bits(0xC03087DD6E72C226_u64)), (f64::from_bits(0x4031172608B81510_u64), f64::from_bits(0xC011222E77B0ABD0_u64)), (f64::from_bits(0xC0334100792175F4_u64), f64::from_bits(0xC032B4CBFD7B38E0_u64)), (f64::from_bits(0x402BCB2B107270C0_u64), f64::from_bits(0x401859FD807F03C4_u64)), (f64::from_bits(0x40283EF5CF7EE3F0_u64), f64::from_bits(0xC030944485019CD8_u64)), (f64::from_bits(0xBFB59B435A7F5100_u64), f64::from_bits(0x4030B2BB4D09F4A0_u64)), (f64::from_bits(0x3FFB0D3A9191C0E0_u64), f64::from_bits(0x402AE2EB554DF614_u64))],
                expected: f64::from_bits(0x403092BAE1ACAC11_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0242996E18584FD_u64), y: f64::from_bits(0x3FE30679FE18F5E0_u64),
                polygon: &[(f64::from_bits(0xC00525DF48A27DA8_u64), f64::from_bits(0xC00D6BB6F5077020_u64)), (f64::from_bits(0x40276ADB30D67DCC_u64), f64::from_bits(0x400408B86CF0A150_u64)), (f64::from_bits(0xC02849B3A8904E86_u64), f64::from_bits(0x401BD0B32C72D834_u64))],
                expected: f64::from_bits(0x400598326665FA35_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4024CBEF21908358_u64), y: f64::from_bits(0xBFF6E0F25C4575A0_u64),
                polygon: &[(f64::from_bits(0x40298001AA1B8810_u64), f64::from_bits(0x40325854F8EE398C_u64)), (f64::from_bits(0xBFF19A2A46BE62C0_u64), f64::from_bits(0xC02C81708A7A0DB0_u64)), (f64::from_bits(0xC01EDDC448DD7E58_u64), f64::from_bits(0xC0200E327C210A6E_u64))],
                expected: f64::from_bits(0x401646222B728AEC_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4031DF7A321E9434_u64), y: f64::from_bits(0xC02797743C9FFFD3_u64),
                polygon: &[(f64::from_bits(0x40227C22D560551E_u64), f64::from_bits(0x402F2C1485AC20B8_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4037AA634A0BB560_u64), y: f64::from_bits(0x401B015C495BCC5C_u64),
                polygon: &[(f64::from_bits(0x40282802B8B15218_u64), f64::from_bits(0x4000AC985FEA1640_u64)), (f64::from_bits(0xC02AEF593DD95F8C_u64), f64::from_bits(0x4014077BD51B5FC4_u64)), (f64::from_bits(0xC007ADE5B5562418_u64), f64::from_bits(0xC0217F9912A5AB06_u64)), (f64::from_bits(0x4012CBD10D2FFFD8_u64), f64::from_bits(0xC02B8B5D02CA3006_u64)), (f64::from_bits(0x4023A36F28BFBC04_u64), f64::from_bits(0x402B8E294CFD9170_u64))],
                expected: f64::from_bits(0x4028864CE895A3BE_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0096D239E761670_u64), y: f64::from_bits(0xC024FA601E0CF65C_u64),
                polygon: &[(f64::from_bits(0x401B762EBD913394_u64), f64::from_bits(0xC0336431C0237265_u64)), (f64::from_bits(0x40246752A03800F6_u64), f64::from_bits(0xC0103C6A6D865F1E_u64)), (f64::from_bits(0xC00B6869BB958240_u64), f64::from_bits(0x3FFF11A5CADF3E40_u64))],
                expected: f64::from_bits(0x4014B653E554CDD1_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4036FC5039B30B90_u64), y: f64::from_bits(0x40327B92BD8D4F80_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4029FA74E09340AC_u64), y: f64::from_bits(0xC02336FA0CFE5879_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40360C2002EC9D06_u64), y: f64::from_bits(0x3FED3C969871CBA0_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4036727B0C7DB114_u64), y: f64::from_bits(0x3FE7B4C160F9B1C0_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0316F1FD5A9069C_u64), y: f64::from_bits(0x402594A5D61D20F4_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02DD2E42AF544FD_u64), y: f64::from_bits(0x401ACC4CE6B5586C_u64),
                polygon: &[(f64::from_bits(0xC0258D3171579663_u64), f64::from_bits(0xC032E48D0958A9B2_u64)), (f64::from_bits(0xC02895A30B6DBB93_u64), f64::from_bits(0xBF748D3E36C7F000_u64)), (f64::from_bits(0xC02DD9A0200CE457_u64), f64::from_bits(0xC02EFAA22894E184_u64)), (f64::from_bits(0xC02AC366358F5E89_u64), f64::from_bits(0xC032A70C81C2EB95_u64)), (f64::from_bits(0x4026AE8D6FC88CD2_u64), f64::from_bits(0x402D4002983BC4C8_u64))],
                expected: f64::from_bits(0x401CCAE52EFE3A38_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC00A0E50615E70F0_u64), y: f64::from_bits(0xC0185698F7BB6A34_u64),
                polygon: &[(f64::from_bits(0xC02482C7E29120FD_u64), f64::from_bits(0xC01AA72AEB7601C4_u64)), (f64::from_bits(0x402E83599E3E0FB8_u64), f64::from_bits(0x4024F3A65602CBA2_u64)), (f64::from_bits(0x401362F29E4E4924_u64), f64::from_bits(0x40278342570C8344_u64)), (f64::from_bits(0x40075B94B2184680_u64), f64::from_bits(0xC01D9FB0975FBC08_u64)), (f64::from_bits(0x401DA28BD04BBAA0_u64), f64::from_bits(0x4026B69047B89172_u64)), (f64::from_bits(0xC031C7ECB28902BE_u64), f64::from_bits(0xC01C770A27C23EC6_u64)), (f64::from_bits(0xC020744D8C3E61CF_u64), f64::from_bits(0x402EE94455A21588_u64)), (f64::from_bits(0xC020F36109ECBF60_u64), f64::from_bits(0x401BCA2F9252C58C_u64))],
                expected: f64::from_bits(0x400B60F24ABFDAAF_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402FA25763042150_u64), y: f64::from_bits(0xC005BC83335149C8_u64),
                polygon: &[(f64::from_bits(0x4026F2E6CCF32612_u64), f64::from_bits(0xC032EAAD0BB58BBE_u64)), (f64::from_bits(0xC01C027AF0365FAE_u64), f64::from_bits(0xC02D0D4C287EEE58_u64)), (f64::from_bits(0xC02A5EF47A8E4814_u64), f64::from_bits(0x401359FBCD6AD230_u64)), (f64::from_bits(0xC00EC98D3E2880C8_u64), f64::from_bits(0x3FE1646BFFC45040_u64)), (f64::from_bits(0xC0308E0AD2601F91_u64), f64::from_bits(0xC02820CADE9957D4_u64)), (f64::from_bits(0xBFF02100B723ACE0_u64), f64::from_bits(0xC03237E2C1C90A16_u64)), (f64::from_bits(0x402A63A00C38B9AC_u64), f64::from_bits(0x400C570A315CBCD0_u64))],
                expected: f64::from_bits(0x4008BE2B9691FB14_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC033A495AE44BD68_u64), y: f64::from_bits(0xC028F4C51506ADCC_u64),
                polygon: &[(f64::from_bits(0x401861C436CBDEA8_u64), f64::from_bits(0xC02A9F47023DB89D_u64)), (f64::from_bits(0xC032BEE7603CBD62_u64), f64::from_bits(0x40161EC3ED1D8150_u64)), (f64::from_bits(0xC031E1EB18D8BF9A_u64), f64::from_bits(0x3FFF312669B83B80_u64)), (f64::from_bits(0x4032DB6C62A1B53A_u64), f64::from_bits(0xBFF73C72E8AE7B40_u64)), (f64::from_bits(0xC01E127AB2E99F24_u64), f64::from_bits(0xC02F812A76B59AB4_u64)), (f64::from_bits(0xC01FB23FF35A7AF8_u64), f64::from_bits(0xC01CC275E79F0286_u64)), (f64::from_bits(0xC02EA1B56017A400_u64), f64::from_bits(0x4020332EB48DCF72_u64)), (f64::from_bits(0x40106033874AD9AC_u64), f64::from_bits(0x40216DC65804CC48_u64))],
                expected: f64::from_bits(0x4027E98E83998946_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x401FD07BE6D8C8A0_u64), y: f64::from_bits(0x4027761192875AC0_u64),
                polygon: &[(f64::from_bits(0xC033A5C17040A0FE_u64), f64::from_bits(0xC014D3CF943939FA_u64)), (f64::from_bits(0x40296F345A394F30_u64), f64::from_bits(0xC025B14B57ABF966_u64)), (f64::from_bits(0xC02664EF2CA85BCC_u64), f64::from_bits(0x4015FD37010001F4_u64)), (f64::from_bits(0xC023DBE2969569D9_u64), f64::from_bits(0xC01A3A62F19B9068_u64)), (f64::from_bits(0xC011577DCEC4A2A8_u64), f64::from_bits(0xC0201AB0E5E7814C_u64))],
                expected: f64::from_bits(0x402FE7605D977111_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402EDCD84C79B4B0_u64), y: f64::from_bits(0xC033D498613F4E19_u64),
                polygon: &[(f64::from_bits(0x4018EF2E3D222D3C_u64), f64::from_bits(0xC03115A8BD1145EF_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC022201883CF3A74_u64), y: f64::from_bits(0xC0359EB33EB56C4E_u64),
                polygon: &[(f64::from_bits(0xC027A912F8B77615_u64), f64::from_bits(0xC0325E449E9F93B6_u64)), (f64::from_bits(0x4033BF444776DE6A_u64), f64::from_bits(0x402A2CF7378140AC_u64)), (f64::from_bits(0x4026404BCFAB6C3A_u64), f64::from_bits(0x402561819A962FE8_u64))],
                expected: f64::from_bits(0x40111475A562C2D8_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0201EF184E909A8_u64), y: f64::from_bits(0x40277C43A2C8C814_u64),
                polygon: &[(f64::from_bits(0x401634370C38EF04_u64), f64::from_bits(0x402B3F554D1422E8_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4037105FB513739E_u64), y: f64::from_bits(0x402AD5F319F3A29C_u64),
                polygon: &[(f64::from_bits(0xC01587CB49886834_u64), f64::from_bits(0x4018B582ADB14E34_u64)), (f64::from_bits(0xC0154F253E3B0F2A_u64), f64::from_bits(0x40302437DE3C9736_u64)), (f64::from_bits(0xC02E16B0AFCFF4DA_u64), f64::from_bits(0x401F7403AABFE658_u64)), (f64::from_bits(0xC01892BB195CE458_u64), f64::from_bits(0x4030628866A33D48_u64)), (f64::from_bits(0x40284ECE4F075078_u64), f64::from_bits(0xC02A00E0B8E752C8_u64)), (f64::from_bits(0xC0335FEDA1CADC94_u64), f64::from_bits(0xC0254C946AD587BF_u64))],
                expected: f64::from_bits(0x403739CAC680271D_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x403605E290C76EF4_u64), y: f64::from_bits(0xC0026834464A8310_u64),
                polygon: &[(f64::from_bits(0x40305552B20FB090_u64), f64::from_bits(0xC00FD5AAEE316A38_u64)), (f64::from_bits(0xC013A414015889C0_u64), f64::from_bits(0x3FE1794D629C4180_u64)), (f64::from_bits(0x402A510F12995824_u64), f64::from_bits(0xC027E229299138BC_u64))],
                expected: f64::from_bits(0x4017BA78B56245B4_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBFF540C5A396C7F0_u64), y: f64::from_bits(0xC0238988A08BBE66_u64),
                polygon: &[(f64::from_bits(0xC01D3AE91DDA59A4_u64), f64::from_bits(0xC020488738B055C8_u64)), (f64::from_bits(0x402DA8E50990F810_u64), f64::from_bits(0xC026A59B697535B2_u64)), (f64::from_bits(0x3FC3CAF5D9941E00_u64), f64::from_bits(0x402E04603451F9E0_u64)), (f64::from_bits(0x402A3E54A04B0DD0_u64), f64::from_bits(0x402179C14C18FACE_u64)), (f64::from_bits(0xC024903DED871744_u64), f64::from_bits(0x40145FA9641C1930_u64))],
                expected: f64::from_bits(0x3FE85003947708E3_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40217C3E05D4D824_u64), y: f64::from_bits(0x4033AFDF6AD77772_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40380CC1C49EA67C_u64), y: f64::from_bits(0xC0301C5081ED622A_u64),
                polygon: &[(f64::from_bits(0x40255BB3377047F8_u64), f64::from_bits(0xC03394172BA5161A_u64)), (f64::from_bits(0x4030F8DFC4B32562_u64), f64::from_bits(0x400936F61C1ADAD0_u64)), (f64::from_bits(0x4010D4D3E4DB8C50_u64), f64::from_bits(0xC019C027380F8FDC_u64)), (f64::from_bits(0x401095B5739216A8_u64), f64::from_bits(0xC01EA5CCC2A04D9C_u64)), (f64::from_bits(0xC0241AEE1917EF8E_u64), f64::from_bits(0x401C4FD40C1CBED0_u64)), (f64::from_bits(0xC03268639E719C0B_u64), f64::from_bits(0x403221BAB51D5812_u64))],
                expected: f64::from_bits(0x4027EBDF94D0B200_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4022039A86F7C73C_u64), y: f64::from_bits(0x4024993A74D43740_u64),
                polygon: &[(f64::from_bits(0x4026C42A10C37C52_u64), f64::from_bits(0x402EB0D7B5C21454_u64)), (f64::from_bits(0xC01D5214423B35B4_u64), f64::from_bits(0xC02BE03DC093AA8E_u64)), (f64::from_bits(0xBFF8FA9F131478D0_u64), f64::from_bits(0xC02EFC55C2545B16_u64)), (f64::from_bits(0x40326923BBC59B74_u64), f64::from_bits(0xC0330D2D6BC9AB86_u64)), (f64::from_bits(0x3FD78C91011A5580_u64), f64::from_bits(0xC02AF45415E1230A_u64)), (f64::from_bits(0xC033E7E6D18E1175_u64), f64::from_bits(0x4033DFBF4A8D65DA_u64))],
                expected: f64::from_bits(0x3FE6E1B2B8EA4D0F_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402781B462ED0088_u64), y: f64::from_bits(0x4027CE6DBB34B018_u64),
                polygon: &[(f64::from_bits(0x4026F1E464553B66_u64), f64::from_bits(0x40116E4D940432F8_u64)), (f64::from_bits(0x401A3A3DAE393CE4_u64), f64::from_bits(0xC01D7D1D940E71D0_u64)), (f64::from_bits(0xC02FC10A1A4F681B_u64), f64::from_bits(0x402219895C80A09C_u64))],
                expected: f64::from_bits(0x401DEFEDB10DB4BA_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402906D34261E424_u64), y: f64::from_bits(0x4022E445A51C9D14_u64),
                polygon: &[(f64::from_bits(0xC019F1073B0FDD7A_u64), f64::from_bits(0xC0219CB285241BAA_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40226678C07AC4D4_u64), y: f64::from_bits(0xC02A5267566351BD_u64),
                polygon: &[(f64::from_bits(0x40039D20D5587E10_u64), f64::from_bits(0x3FFBB3E8B588DB10_u64)), (f64::from_bits(0x40265D8A309302EC_u64), f64::from_bits(0x40274975034EC812_u64)), (f64::from_bits(0xBFFF1B77E60078C0_u64), f64::from_bits(0x401AE20AC027D8A0_u64)), (f64::from_bits(0x403203F51EAD4FF0_u64), f64::from_bits(0x4032C63642CCE83C_u64))],
                expected: f64::from_bits(0x4030599C1C2D6DF4_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402C096E9495D264_u64), y: f64::from_bits(0xBFE8B9208FD34260_u64),
                polygon: &[(f64::from_bits(0xC02777D2AF313A2E_u64), f64::from_bits(0x4011A49FA4D58580_u64)), (f64::from_bits(0x4028D6E4E227AF0C_u64), f64::from_bits(0xC033E06973146A39_u64)), (f64::from_bits(0x4031FD226FE54B42_u64), f64::from_bits(0xC016113D36D4B480_u64)), (f64::from_bits(0x3FC52171CC837880_u64), f64::from_bits(0xC023813C92306492_u64)), (f64::from_bits(0x4023527FBCF86A12_u64), f64::from_bits(0xC03314664DD0E69E_u64))],
                expected: f64::from_bits(0x4016227458EFE929_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02B80ECC084AB23_u64), y: f64::from_bits(0xC02E24DA604E39FE_u64),
                polygon: &[(f64::from_bits(0x4032A59C5F87B594_u64), f64::from_bits(0xC02F0E602F4AEF09_u64)), (f64::from_bits(0x4031CC3485BFD41C_u64), f64::from_bits(0x4028812941A5596C_u64))],
                expected: f64::from_bits(0x40402F50FEB88D6F_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40284C39B71566A0_u64), y: f64::from_bits(0xC02C8E418041D30C_u64),
                polygon: &[(f64::from_bits(0x400E81ECD35C7F28_u64), f64::from_bits(0xC0331CB5E670A9C0_u64)), (f64::from_bits(0x4032275E5B09B162_u64), f64::from_bits(0x3FE478D076A8E140_u64)), (f64::from_bits(0x402200FABB690DDC_u64), f64::from_bits(0x3F9D3F6CB63AC400_u64)), (f64::from_bits(0x4021502F6E3F1A22_u64), f64::from_bits(0xC03052AABEE30212_u64)), (f64::from_bits(0x40223327E7286B4A_u64), f64::from_bits(0xC01CEC7F8D2171F8_u64)), (f64::from_bits(0x4032EB5949A82A32_u64), f64::from_bits(0xC032D0FC2D3AADAB_u64)), (f64::from_bits(0xC003CAD0CE028550_u64), f64::from_bits(0x40132B57207C4BF0_u64)), (f64::from_bits(0xC033EBED76CDA4E4_u64), f64::from_bits(0x40297BCBF34C25D4_u64))],
                expected: f64::from_bits(0x3FFF8309165ACCD0_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402D2D4DCF1F9A20_u64), y: f64::from_bits(0xC02DEFB12B16D5A8_u64),
                polygon: &[(f64::from_bits(0xC0235A7CDEB6C544_u64), f64::from_bits(0x3FE42937F7A13920_u64)), (f64::from_bits(0xC0266D1DBD5F4A57_u64), f64::from_bits(0x4024D954825EF5B8_u64)), (f64::from_bits(0x3FFA5F95F9B95300_u64), f64::from_bits(0xC02349DD174374D0_u64)), (f64::from_bits(0xC01E35BE7F0A4FAC_u64), f64::from_bits(0xC0335494C883EED0_u64)), (f64::from_bits(0xC0308B0D28493C50_u64), f64::from_bits(0x400CE49DE2BA7A10_u64)), (f64::from_bits(0x4033FA79A1A02E5C_u64), f64::from_bits(0x40300A067C00B6B0_u64)), (f64::from_bits(0xC01AC0EFCE7EA53C_u64), f64::from_bits(0xC01877B88F2EE36C_u64)), (f64::from_bits(0x4017D6E5007EF2FC_u64), f64::from_bits(0xBFDFEA6BA27E7E40_u64))],
                expected: f64::from_bits(0x402BFC2E26140B8E_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC034DBF343203919_u64), y: f64::from_bits(0x402146BE2AD6E348_u64),
                polygon: &[(f64::from_bits(0xC02AE3D91E961CDE_u64), f64::from_bits(0xC0330419D790FB51_u64)), (f64::from_bits(0xC02253946D237C4C_u64), f64::from_bits(0xC01628D0FB0F5064_u64)), (f64::from_bits(0x4004553D2BDF07D0_u64), f64::from_bits(0x401CEE69A0A71FB4_u64)), (f64::from_bits(0x4031A06966DBB5DA_u64), f64::from_bits(0x4032A5D920D7E9BA_u64)), (f64::from_bits(0x4025DB9893EB59E8_u64), f64::from_bits(0xC022332BFF501A82_u64)), (f64::from_bits(0x4015E5AD8A799950_u64), f64::from_bits(0x40254ADF417C8298_u64))],
                expected: f64::from_bits(0x403233A7EC88EE4C_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4016753033EBFCCC_u64), y: f64::from_bits(0x4038503545211E02_u64),
                polygon: &[(f64::from_bits(0xC02BCA7B43B7C38A_u64), f64::from_bits(0x402C2126C12ADB48_u64)), (f64::from_bits(0x40214109F6441E48_u64), f64::from_bits(0x4011DE7C10923E50_u64)), (f64::from_bits(0xBFE03493BFB9E600_u64), f64::from_bits(0x402BF26A8958CB74_u64)), (f64::from_bits(0xC032F0F7CC2D857F_u64), f64::from_bits(0x4031433F7E3CC83E_u64)), (f64::from_bits(0xC0151ADD4997FA30_u64), f64::from_bits(0xC0251AD1F3B4BC46_u64)), (f64::from_bits(0xC033FFA175EA0B45_u64), f64::from_bits(0x4027673207A114EC_u64)), (f64::from_bits(0xC032E96792B6CEF6_u64), f64::from_bits(0x402A635B647EB1F4_u64)), (f64::from_bits(0xC025A4FF54D10158_u64), f64::from_bits(0x40331575C9A1688A_u64))],
                expected: f64::from_bits(0x4028080B2E36E2BB_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0103E7A2E7BC180_u64), y: f64::from_bits(0xC0121190D3069DB4_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC018ED9F99F11800_u64), y: f64::from_bits(0x4022DD6EABF62B50_u64),
                polygon: &[(f64::from_bits(0xC0327FBB5C579C0C_u64), f64::from_bits(0xC01F72529B256A90_u64)), (f64::from_bits(0xC016C36F7A405308_u64), f64::from_bits(0xBFEB2688784532C0_u64)), (f64::from_bits(0x401C4EC18D8AC7F4_u64), f64::from_bits(0xC012C61E69159A86_u64)), (f64::from_bits(0xC015574BA3225DE8_u64), f64::from_bits(0xC01AB59C79217BF0_u64))],
                expected: f64::from_bits(0x40249720FBAC8C55_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBFCEBB345455BB00_u64), y: f64::from_bits(0x40351DCA7A8F4C2C_u64),
                polygon: &[(f64::from_bits(0xC0319664479A5158_u64), f64::from_bits(0x402B606087ABD6A0_u64)), (f64::from_bits(0x4000F1F12B5FD780_u64), f64::from_bits(0xBFFCA5C60826B170_u64)), (f64::from_bits(0x40313F2655B35D5E_u64), f64::from_bits(0x40270D7B2915DA58_u64)), (f64::from_bits(0x40235F090EB824E4_u64), f64::from_bits(0xC032E48BD55E93C8_u64)), (f64::from_bits(0xC031FAD7BD5ED051_u64), f64::from_bits(0xC0164CB114A8EF76_u64)), (f64::from_bits(0xC0298BC6A8CCE27A_u64), f64::from_bits(0x4029F40DFC7E4310_u64)), (f64::from_bits(0xC02479EA71A6025C_u64), f64::from_bits(0xC03333DC20AE9301_u64)), (f64::from_bits(0xC019B98BAAD7D4A8_u64), f64::from_bits(0xC01FF344E72BF860_u64))],
                expected: f64::from_bits(0x402DE36C0AF0C3A3_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402617E520030E5C_u64), y: f64::from_bits(0xC0234CD55130A45C_u64),
                polygon: &[(f64::from_bits(0x3FF4235807078440_u64), f64::from_bits(0xC0242B263FCBD429_u64)), (f64::from_bits(0xC017D87CD87BE6C0_u64), f64::from_bits(0x3FEB3FB22779D020_u64))],
                expected: f64::from_bits(0x40239867DEAE9570_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC030AD887759583A_u64), y: f64::from_bits(0x401C6FE9318F2F88_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402AF7C2FEA5C9F0_u64), y: f64::from_bits(0x40382720E4782D6C_u64),
                polygon: &[(f64::from_bits(0xBFF679462BE98580_u64), f64::from_bits(0xC02496CD0352B1F3_u64)), (f64::from_bits(0x4021E952D94A2C04_u64), f64::from_bits(0xC02BB869895AA917_u64)), (f64::from_bits(0x40310A399736FF6A_u64), f64::from_bits(0x402609D3B1579B06_u64))],
                expected: f64::from_bits(0x402B368DA60EDB12_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x403053D76E08172C_u64), y: f64::from_bits(0x400B074FC3124B28_u64),
                polygon: &[(f64::from_bits(0x402EEC48686438B4_u64), f64::from_bits(0xC033641A4664F7DC_u64)), (f64::from_bits(0xC017ABD3BAABABBC_u64), f64::from_bits(0xC02E41FF9998F541_u64)), (f64::from_bits(0xC00911B03BC32DF0_u64), f64::from_bits(0x402C5E8C9DADAA14_u64))],
                expected: f64::from_bits(0x4027940D42DA412C_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBFFDB0B3895EA200_u64), y: f64::from_bits(0x4013B792686E7618_u64),
                polygon: &[(f64::from_bits(0xBFD11C652D278E00_u64), f64::from_bits(0xC031EDDC1BAD5812_u64)), (f64::from_bits(0x3FFA05BB39423B20_u64), f64::from_bits(0xC01C8DA593A4A23A_u64)), (f64::from_bits(0x402EE435A459D568_u64), f64::from_bits(0xC02EE9A053BAEB8F_u64)), (f64::from_bits(0xC0245FD41A7B1AE2_u64), f64::from_bits(0x4028CE13F7F58370_u64)), (f64::from_bits(0xC01E933DA2E4ABB4_u64), f64::from_bits(0x40335C68AAA3C788_u64))],
                expected: f64::from_bits(0x3FF122EC044F3E59_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC01A45221123258C_u64), y: f64::from_bits(0x4024A39DBD3215C8_u64),
                polygon: &[(f64::from_bits(0xC02055E4EBDF6586_u64), f64::from_bits(0xC0316AB8E6723B9B_u64)), (f64::from_bits(0xC010BFAC15DC11E0_u64), f64::from_bits(0x401A284A12308E30_u64)), (f64::from_bits(0x4021B5B886A50D1C_u64), f64::from_bits(0xC02AB6851819879B_u64)), (f64::from_bits(0xC0168DB078F8700C_u64), f64::from_bits(0x403186FC45CECA30_u64)), (f64::from_bits(0x4028668DCDBE9458_u64), f64::from_bits(0x402BEAB1976BB104_u64)), (f64::from_bits(0xC0185DD8360D8124_u64), f64::from_bits(0x402584E5B3E80184_u64)), (f64::from_bits(0x4022789C9137A160_u64), f64::from_bits(0x402FCFFE35642624_u64)), (f64::from_bits(0x4024EAACBF8ED146_u64), f64::from_bits(0x401AC3FC55E29990_u64))],
                expected: f64::from_bits(0x3FE4BD59E1C29B66_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0289D49402262D3_u64), y: f64::from_bits(0x4037497B422081AA_u64),
                polygon: &[(f64::from_bits(0xC0330A53360246AC_u64), f64::from_bits(0x3FD994D0413F1400_u64)), (f64::from_bits(0xC027273D95055666_u64), f64::from_bits(0xC031A0B27E044308_u64)), (f64::from_bits(0x3FF931F374BA9880_u64), f64::from_bits(0x3FFA317ABE888C10_u64)), (f64::from_bits(0xC031C7EEB72EA575_u64), f64::from_bits(0x401A5AD7D07F426C_u64)), (f64::from_bits(0x40323A4F06665A7C_u64), f64::from_bits(0x40049907E3002DD0_u64)), (f64::from_bits(0xC01C25818C39924E_u64), f64::from_bits(0xBFDF377B831B8500_u64)), (f64::from_bits(0xC0150F1C4A76B270_u64), f64::from_bits(0x3FF4C0D6393FF810_u64)), (f64::from_bits(0x40238995A9191724_u64), f64::from_bits(0x40242203EB90CDA2_u64))],
                expected: f64::from_bits(0x403133B33BA3CBD3_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC00E88CB7FE1FC68_u64), y: f64::from_bits(0xC00B93C75CD7A470_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0189658C11AEF24_u64), y: f64::from_bits(0xC0360BFFEB423CC2_u64),
                polygon: &[(f64::from_bits(0xC01A6A6ECF5B29B8_u64), f64::from_bits(0x402C8AAEE2E5A7E4_u64)), (f64::from_bits(0xC017932585D1D4C8_u64), f64::from_bits(0x4031F5E85D11DA0A_u64)), (f64::from_bits(0x4032AA44EB598D7A_u64), f64::from_bits(0xC01342447753FEE2_u64)), (f64::from_bits(0xC02536F423A2859C_u64), f64::from_bits(0x40331D5CE86BF6B0_u64)), (f64::from_bits(0x3FFBEE32158DDB00_u64), f64::from_bits(0x400A937A5800EB30_u64))],
                expected: f64::from_bits(0x403A91784D81F340_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC010F1CDF845BD98_u64), y: f64::from_bits(0xC0253A6F6316B685_u64),
                polygon: &[(f64::from_bits(0xC01A215E50E30866_u64), f64::from_bits(0x4024FE7AC8164AB8_u64)), (f64::from_bits(0xC02C621B2696F329_u64), f64::from_bits(0x402DAE76D11482C4_u64)), (f64::from_bits(0x40083C227DD64550_u64), f64::from_bits(0x402EE42AFB27D8A4_u64)), (f64::from_bits(0x4032115409E62984_u64), f64::from_bits(0xC002A49E2105BA30_u64)), (f64::from_bits(0x400720DFF2AD9E98_u64), f64::from_bits(0x402DED4502EC0E10_u64)), (f64::from_bits(0x400F000F161410C0_u64), f64::from_bits(0x402363C4AD758D5C_u64)), (f64::from_bits(0xC01C285379F13788_u64), f64::from_bits(0xC0170B3FA8F4C8AC_u64))],
                expected: f64::from_bits(0x40166B14516C93C6_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4029DB2CF48AD95C_u64), y: f64::from_bits(0xC038A700AC4CEA38_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0230B0B43C6D513_u64), y: f64::from_bits(0x401991DAD08B5D38_u64),
                polygon: &[(f64::from_bits(0x40234E4B29A49680_u64), f64::from_bits(0xC033A3ED91469665_u64)), (f64::from_bits(0x4011E1A7190EE7AC_u64), f64::from_bits(0xC02F7CF395CCE56C_u64))],
                expected: f64::from_bits(0x403A3010285300B7_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC022CA582002238E_u64), y: f64::from_bits(0xC02BA13D02840FCE_u64),
                polygon: &[(f64::from_bits(0xC02A9660BD55A2C2_u64), f64::from_bits(0xBFD59F3F682AF780_u64)), (f64::from_bits(0x4001292CAB3711A8_u64), f64::from_bits(0x4033040870184844_u64)), (f64::from_bits(0x3FDDE95DB51ABBC0_u64), f64::from_bits(0x4014E9492DA320B0_u64)), (f64::from_bits(0xC01C04FB0794DF78_u64), f64::from_bits(0xC021E38AE05EEFBC_u64)), (f64::from_bits(0x40321D6B17ED8B32_u64), f64::from_bits(0xC02AA2B50C4EA47F_u64)), (f64::from_bits(0xC0088B9B3FE46C10_u64), f64::from_bits(0x4033B210B9661FCA_u64)), (f64::from_bits(0xC01A5BF5EB907D28_u64), f64::from_bits(0xC02DABFFC16127E2_u64)), (f64::from_bits(0xC02FA7AC5CA5C1A2_u64), f64::from_bits(0xC020B9AFAB622FD5_u64))],
                expected: f64::from_bits(0x3FE8C2D5A3972D8C_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC038ECD05F369EFC_u64), y: f64::from_bits(0xC02E33CE93CEDBBA_u64),
                polygon: &[(f64::from_bits(0x40212639A8231022_u64), f64::from_bits(0xC0321733C68B907E_u64)), (f64::from_bits(0xBFD2779B53DAE900_u64), f64::from_bits(0xC02C18984C5EFCFC_u64)), (f64::from_bits(0xC024A4B9EDEAF753_u64), f64::from_bits(0xC012C876FDDE1FF8_u64)), (f64::from_bits(0x400FCB308241BA28_u64), f64::from_bits(0x4022E24B498A1900_u64)), (f64::from_bits(0x401368BE05A3454C_u64), f64::from_bits(0xC022CF5C61C42CD3_u64)), (f64::from_bits(0x40190F2093D7C820_u64), f64::from_bits(0xC032D7F38C1EF5AC_u64)), (f64::from_bits(0xC02897943D2B0D16_u64), f64::from_bits(0x4030C8F43A69B9E0_u64))],
                expected: f64::from_bits(0x4031EE66896F442F_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4033547FC2160106_u64), y: f64::from_bits(0x4002C22970252088_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4020D59FAF061DE8_u64), y: f64::from_bits(0xC036C937E4568F5D_u64),
                polygon: &[(f64::from_bits(0x4030E0397C450532_u64), f64::from_bits(0xC02851D8EF54E618_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4036E77857A4E648_u64), y: f64::from_bits(0x402BF749F7B4A0FC_u64),
                polygon: &[(f64::from_bits(0x40200A67D028B104_u64), f64::from_bits(0x40233703E7C4D234_u64)), (f64::from_bits(0xC0218FA6ED56FD49_u64), f64::from_bits(0xC03135643A315470_u64))],
                expected: f64::from_bits(0x402F070206190AFD_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4013EF7C82C7767C_u64), y: f64::from_bits(0xC026D2BA05D33715_u64),
                polygon: &[(f64::from_bits(0xC00C49ED84EC0050_u64), f64::from_bits(0xC0250D8FA3577722_u64)), (f64::from_bits(0x401BF9183F4FC848_u64), f64::from_bits(0xC018CC4400B3A5FA_u64)), (f64::from_bits(0x40151E9BE95258A0_u64), f64::from_bits(0xC0275C00D61113C3_u64)), (f64::from_bits(0xC026B3BFFFFD6B0D_u64), f64::from_bits(0x402D58EF43E757D4_u64)), (f64::from_bits(0xC0323E42FBB7517C_u64), f64::from_bits(0xC02392FC77B510F2_u64)), (f64::from_bits(0xC024857676B8665A_u64), f64::from_bits(0x4032FEE050B7B328_u64))],
                expected: f64::from_bits(0x3FBB746FED5A4F89_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x403114A9666D9FB8_u64), y: f64::from_bits(0x3FFEAE74CB2B9560_u64),
                polygon: &[(f64::from_bits(0xC0102B372F62CB30_u64), f64::from_bits(0x401B05C641462850_u64)), (f64::from_bits(0xC01D40EE5E152760_u64), f64::from_bits(0x402151F57C1A3042_u64)), (f64::from_bits(0x403386AD07464020_u64), f64::from_bits(0xC023BE0BA616A578_u64)), (f64::from_bits(0xC02BA41C3DEA68F4_u64), f64::from_bits(0xC02C6A887FCEF27D_u64)), (f64::from_bits(0xC02D492813B4DB9B_u64), f64::from_bits(0x401A07F0DCB5E584_u64)), (f64::from_bits(0xC004FFA6A47A5BE8_u64), f64::from_bits(0xC029B7375FBA9F00_u64))],
                expected: f64::from_bits(0x40209F94733B8E0B_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0363CBD84C9AEC5_u64), y: f64::from_bits(0x403648966532F7DA_u64),
                polygon: &[(f64::from_bits(0x4028F5C017C6DE84_u64), f64::from_bits(0xC02B697E50FEBAE8_u64)), (f64::from_bits(0x4004598BE899C4E0_u64), f64::from_bits(0x401AD7E6F32EADD4_u64)), (f64::from_bits(0x401B0AAADDEBBC8C_u64), f64::from_bits(0xC02085D7CA71C9DA_u64)), (f64::from_bits(0x402162BECA1FBECA_u64), f64::from_bits(0x4026F62408378B38_u64))],
                expected: f64::from_bits(0x403D44914B6E40A1_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402AA3A4CC08C650_u64), y: f64::from_bits(0x40359FA8A72E46DA_u64),
                polygon: &[(f64::from_bits(0xC02597DB3388A59A_u64), f64::from_bits(0xC027E83C05460CC4_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40133711A2C7D240_u64), y: f64::from_bits(0x402F85692A7943F4_u64),
                polygon: &[(f64::from_bits(0xC0162057EBA04488_u64), f64::from_bits(0xC01923D763203D2C_u64)), (f64::from_bits(0xC018746A520DA716_u64), f64::from_bits(0xC01C4BF9ACEED310_u64)), (f64::from_bits(0xC00BB731E8B50DC8_u64), f64::from_bits(0xC02A76192DBD3B3F_u64)), (f64::from_bits(0x402E3AD7232DD928_u64), f64::from_bits(0x4022F92AFCAC04A6_u64)), (f64::from_bits(0xC03234701F52233C_u64), f64::from_bits(0xC01BEC4DBA2EB710_u64)), (f64::from_bits(0x402C13451EFBC3B0_u64), f64::from_bits(0xC0150D36E5FC1E9C_u64)), (f64::from_bits(0x402D3FEE6498D3BC_u64), f64::from_bits(0xC01AC772D85E9F60_u64))],
                expected: f64::from_bits(0x402462D27EBFF826_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC010F48AD72E5FF8_u64), y: f64::from_bits(0x402A5E46F96254F0_u64),
                polygon: &[(f64::from_bits(0x3FF177F9B31938A0_u64), f64::from_bits(0x402EC59228A688B0_u64)), (f64::from_bits(0xC00F8E1980145248_u64), f64::from_bits(0xC02BA0DD57C36998_u64)), (f64::from_bits(0x4024FAB24DABE4C8_u64), f64::from_bits(0x4001137F5A5C5D18_u64)), (f64::from_bits(0xC029187C39A9888E_u64), f64::from_bits(0xC0305EB28712111B_u64)), (f64::from_bits(0x40270A64431750CA_u64), f64::from_bits(0x40153751A8DFC3AC_u64)), (f64::from_bits(0xC024B46019159EA8_u64), f64::from_bits(0xC0032830A0B6F9F0_u64)), (f64::from_bits(0x4033EA0821D5060C_u64), f64::from_bits(0xC02C74CBA58A6BEE_u64))],
                expected: f64::from_bits(0x401383EC7647DFE6_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4024FE177951BFDC_u64), y: f64::from_bits(0x4035793E5C507D4E_u64),
                polygon: &[(f64::from_bits(0xBFFC4C3A9C7FC520_u64), f64::from_bits(0x3FFEC32904349170_u64)), (f64::from_bits(0x402FBB93665E2588_u64), f64::from_bits(0x402684874F117AC0_u64)), (f64::from_bits(0xC021E7BD392B0026_u64), f64::from_bits(0xBFF40FB2C2354ED0_u64)), (f64::from_bits(0xC01D535948C3B94C_u64), f64::from_bits(0x40243FC2A72C7B70_u64)), (f64::from_bits(0x40310F948E35379C_u64), f64::from_bits(0xC031FCE56BA15302_u64)), (f64::from_bits(0x402BBF355214EF48_u64), f64::from_bits(0xC02897397F1BA218_u64)), (f64::from_bits(0x4032437337DE0284_u64), f64::from_bits(0xC01B266A23722068_u64)), (f64::from_bits(0x400645D6E221CFC0_u64), f64::from_bits(0x401A534490821B44_u64))],
                expected: f64::from_bits(0x402713CA71CCC070_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC036B540AAEF3E2E_u64), y: f64::from_bits(0xC036B6721E52CD19_u64),
                polygon: &[(f64::from_bits(0x4029FFE0B04A923C_u64), f64::from_bits(0xC029A819198D6FDE_u64)), (f64::from_bits(0x4010E0011DBE56BC_u64), f64::from_bits(0xC00EEF2147CA2780_u64)), (f64::from_bits(0xC03087566D28BBD6_u64), f64::from_bits(0xC033C0AC5BFF294E_u64)), (f64::from_bits(0x4032D46B091BB604_u64), f64::from_bits(0xC02D118010132F0E_u64)), (f64::from_bits(0x4020D12D5E75DB18_u64), f64::from_bits(0x4031F9B6A7B2DB10_u64)), (f64::from_bits(0x4029E4F9B13E9508_u64), f64::from_bits(0xC0273AB9F3CD69C2_u64)), (f64::from_bits(0x402029BEC5EEAA28_u64), f64::from_bits(0xC02D4C84039C4BFC_u64)), (f64::from_bits(0xC00F1AE5204FD5E8_u64), f64::from_bits(0xC030F3FB5B943870_u64))],
                expected: f64::from_bits(0x401B682E30B53AAE_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC030EC8A7FDF9343_u64), y: f64::from_bits(0xC030B7DA559CF3D9_u64),
                polygon: &[(f64::from_bits(0x40339D3990D6E004_u64), f64::from_bits(0x4012AF5C85B1DF50_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBFF64B368345A560_u64), y: f64::from_bits(0x4037FEC4418960AE_u64),
                polygon: &[(f64::from_bits(0x4020A9D17E680054_u64), f64::from_bits(0x40041309355F2898_u64)), (f64::from_bits(0x40309CDB4971EE2C_u64), f64::from_bits(0x4002E3BB3BFB6D88_u64))],
                expected: f64::from_bits(0x403795956A75A5F5_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0243D98A8036027_u64), y: f64::from_bits(0x4038BC7D98809F6C_u64),
                polygon: &[(f64::from_bits(0x402047C988E69EAA_u64), f64::from_bits(0xC01D5ECD207FD108_u64)), (f64::from_bits(0xC0304FB2916150BF_u64), f64::from_bits(0xC01B83CB28438B1C_u64)), (f64::from_bits(0x3FFCF56601091880_u64), f64::from_bits(0xC02182120700E5A4_u64)), (f64::from_bits(0xBFF045345B8C67C0_u64), f64::from_bits(0xC018FFB5BC9DA3EC_u64)), (f64::from_bits(0x402F1AFECBBE6DA8_u64), f64::from_bits(0xC0142094E5CD03C6_u64)), (f64::from_bits(0xC021C89AA3007B71_u64), f64::from_bits(0xBFEB22FEC9E0A680_u64)), (f64::from_bits(0xBFF017C90B1C81B0_u64), f64::from_bits(0xC0302891D7140B9F_u64)), (f64::from_bits(0xC02E7F412864FC22_u64), f64::from_bits(0x4001635014C80910_u64))],
                expected: f64::from_bits(0x40372364825D5B11_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x401B1A1173A193EC_u64), y: f64::from_bits(0x4036777709A929FC_u64),
                polygon: &[(f64::from_bits(0xC028151F568C5740_u64), f64::from_bits(0xC00FB6F49CF9EBA8_u64)), (f64::from_bits(0xC031D010B273A5B6_u64), f64::from_bits(0x4023BFD860AEA8D4_u64)), (f64::from_bits(0x402659B23EBFF4F2_u64), f64::from_bits(0xC033D6652890F7EC_u64)), (f64::from_bits(0xC02B43AC721F06F3_u64), f64::from_bits(0x40330D0A070A0392_u64))],
                expected: f64::from_bits(0x40330AC3EFA678C8_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02A233084449DD4_u64), y: f64::from_bits(0x4037168725423554_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC00325AC82A0BBC8_u64), y: f64::from_bits(0xBFA21A79C27B1600_u64),
                polygon: &[(f64::from_bits(0x40259548D63C94F6_u64), f64::from_bits(0xC02AE45D8C18DCF4_u64)), (f64::from_bits(0xC0039D4E0D75C838_u64), f64::from_bits(0xBFD5D94E74B2FD00_u64)), (f64::from_bits(0xC013F3DB42F963EC_u64), f64::from_bits(0xC007BB4D3D7083E0_u64)), (f64::from_bits(0x402ADBB3A457F8C0_u64), f64::from_bits(0xC02A80C566230F9D_u64))],
                expected: f64::from_bits(0x3FD3F084B0E27880_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x4025105A23D155BC_u64), y: f64::from_bits(0xC021A6685E12CD54_u64),
                polygon: &[(f64::from_bits(0x4033F67127C4E692_u64), f64::from_bits(0xC0028B81E058C4B0_u64)), (f64::from_bits(0x40302FBE0765F5DC_u64), f64::from_bits(0x402C1079DB78D348_u64)), (f64::from_bits(0x402AC11D471609D0_u64), f64::from_bits(0xC0245CC46946DF16_u64)), (f64::from_bits(0x3FFC23EA679DA270_u64), f64::from_bits(0x4021F271707B716E_u64)), (f64::from_bits(0x402C2F5591919C9C_u64), f64::from_bits(0x402C4765B90666A8_u64))],
                expected: f64::from_bits(0x3FFBAB8BC98B7B79_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40197ED1525F2300_u64), y: f64::from_bits(0xC0284DBCB5F40870_u64),
                polygon: &[(f64::from_bits(0xC0278E730981D27F_u64), f64::from_bits(0x403042F7532C2662_u64)), (f64::from_bits(0xC02295D563714AAE_u64), f64::from_bits(0xC012DB4C0264E2C2_u64)), (f64::from_bits(0xC033072F68FAA97C_u64), f64::from_bits(0x401236C1FD3DB890_u64)), (f64::from_bits(0x40216C09B15A27FC_u64), f64::from_bits(0x402A0168AABF8114_u64)), (f64::from_bits(0xC00776F97EE30658_u64), f64::from_bits(0x3FEDBA8FD22C1A20_u64)), (f64::from_bits(0x4032753ADCE197C2_u64), f64::from_bits(0x40325D1FAA4A6FD0_u64)), (f64::from_bits(0x402D55C85FBEA340_u64), f64::from_bits(0xC0315604F6D89E3B_u64))],
                expected: f64::from_bits(0x400A7BF3E50605CE_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x400A977FCA44A008_u64), y: f64::from_bits(0xC026E45093F348BE_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0326B5B3E83C142_u64), y: f64::from_bits(0xC0100CEEFC817034_u64),
                polygon: &[(f64::from_bits(0x402CE388856AD5B8_u64), f64::from_bits(0xC00B53F683D82E10_u64)), (f64::from_bits(0xC033C69C43C57E78_u64), f64::from_bits(0xC0322EB85370CC44_u64)), (f64::from_bits(0xC029A11AE6086F13_u64), f64::from_bits(0xC0214BBA4C02F89E_u64))],
                expected: f64::from_bits(0x401D17B04722D2C1_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402A4069CA9494A0_u64), y: f64::from_bits(0x40146BC4417A571C_u64),
                polygon: &[(f64::from_bits(0x401E53CCF20A56F8_u64), f64::from_bits(0xC015C4E40A0D9DEC_u64)), (f64::from_bits(0x4033A665EF508F04_u64), f64::from_bits(0x3FB3592408EAD500_u64)), (f64::from_bits(0x4000F52CBC2A7CA0_u64), f64::from_bits(0x3FEEC6B1010688C0_u64)), (f64::from_bits(0xC0322A660A67C4DF_u64), f64::from_bits(0x40062F9F5DAFD4A0_u64)), (f64::from_bits(0x40320A257F44D644_u64), f64::from_bits(0x40247AE55062AB1C_u64)), (f64::from_bits(0xC017F825A2F9A444_u64), f64::from_bits(0xC020166E740EB40C_u64)), (f64::from_bits(0x40060CF0E5D0B530_u64), f64::from_bits(0x4013431D11EB45E8_u64)), (f64::from_bits(0x4024DBCFEA020826_u64), f64::from_bits(0xBFEBCE1DC73D0E00_u64))],
                expected: f64::from_bits(0x3FF1C79C27129EC8_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x403098DF077F5284_u64), y: f64::from_bits(0xC02883A1F85E1273_u64),
                polygon: &[(f64::from_bits(0xC02EBDC9F27994F2_u64), f64::from_bits(0xC0312D7A098BA9CA_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0387DC550F2E7A8_u64), y: f64::from_bits(0x40160C27A0B30548_u64),
                polygon: &[(f64::from_bits(0x40338F5CAC615E16_u64), f64::from_bits(0xC027BB8DD02F6EBD_u64)), (f64::from_bits(0x40316420BA19352C_u64), f64::from_bits(0x4022A15D65A8736A_u64)), (f64::from_bits(0x400402EC397AF508_u64), f64::from_bits(0x40094260E401DE50_u64))],
                expected: f64::from_bits(0x403B185FA2054030_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02909D7F32FF18A_u64), y: f64::from_bits(0x40326B43F2875532_u64),
                polygon: &[(f64::from_bits(0x4022C6ECECCD28EC_u64), f64::from_bits(0xC02D69F424DD7302_u64)), (f64::from_bits(0x40224486A270F738_u64), f64::from_bits(0xC02DFFFC9C5DD974_u64)), (f64::from_bits(0xC0291D4A6FAAF63C_u64), f64::from_bits(0xC02B2888A862C59A_u64)), (f64::from_bits(0x402E7C8861986F1C_u64), f64::from_bits(0xC026390B55056426_u64)), (f64::from_bits(0xC026736668D449AC_u64), f64::from_bits(0xC02532D5A61C41D2_u64)), (f64::from_bits(0xC033AF580762CC86_u64), f64::from_bits(0x4031C82792CB791A_u64)), (f64::from_bits(0xC02020EB8690BA21_u64), f64::from_bits(0x4012144E209C66A0_u64)), (f64::from_bits(0xC0139FDF6D37C91C_u64), f64::from_bits(0xC0058E4B98737C50_u64))],
                expected: f64::from_bits(0x40173CC6B0D2FD01_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402EBBC6729E361C_u64), y: f64::from_bits(0xC02A0542728F972F_u64),
                polygon: &[(f64::from_bits(0xC03118A023A21B8B_u64), f64::from_bits(0x402865617ED40934_u64)), (f64::from_bits(0xC02E25559FAFA466_u64), f64::from_bits(0x400708E170DF5F38_u64))],
                expected: f64::from_bits(0x40412B2E00A7D5AF_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC027E93C67E4489C_u64), y: f64::from_bits(0x4037AD167B5F482E_u64),
                polygon: &[(f64::from_bits(0xC02DEADCED7228F8_u64), f64::from_bits(0xC02BA06180B1EF78_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0132D86CA5B9A4C_u64), y: f64::from_bits(0x3FD64E2C7FE75940_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC031A2509623FAEA_u64), y: f64::from_bits(0xC025520FD44B6821_u64),
                polygon: &[(f64::from_bits(0x402FA483A4C625B8_u64), f64::from_bits(0xC0309863ADDF7EB4_u64)), (f64::from_bits(0x3FE8C3C9C4FFA800_u64), f64::from_bits(0x3FFE33DB15249DB0_u64)), (f64::from_bits(0xC02A49B01757752E_u64), f64::from_bits(0xC018AC85E8FF000E_u64)), (f64::from_bits(0xC0338BA8D992014E_u64), f64::from_bits(0x402392FC9F98BF92_u64)), (f64::from_bits(0xC033C06BDF596F4C_u64), f64::from_bits(0x3FFAEBBF1D9587E0_u64)), (f64::from_bits(0x402A893C31EE157C_u64), f64::from_bits(0x40276B837968BBD2_u64)), (f64::from_bits(0xC0287128922B6463_u64), f64::from_bits(0xC023AD817093D9DA_u64)), (f64::from_bits(0xC013FE0B541EA7A0_u64), f64::from_bits(0xC009FBCD010CABC0_u64))],
                expected: f64::from_bits(0x4015E6656D744EC0_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x3FFD4E1C34419250_u64), y: f64::from_bits(0xC0224BBFE0A1746F_u64),
                polygon: &[(f64::from_bits(0xC016112512C0A9E6_u64), f64::from_bits(0x403172F30446C30A_u64)), (f64::from_bits(0xC00D0F1900CC4628_u64), f64::from_bits(0x402CAF63342AB808_u64)), (f64::from_bits(0x3FEF70FF6082A880_u64), f64::from_bits(0x4022253985792D9A_u64))],
                expected: f64::from_bits(0x40323D8C5D3CA746_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40363FE1DF40C83C_u64), y: f64::from_bits(0x40318107F78936A0_u64),
                polygon: &[(f64::from_bits(0xC01E3CF366F35552_u64), f64::from_bits(0x4031ACF2EBD452EC_u64)), (f64::from_bits(0xC01A6329AA7C9538_u64), f64::from_bits(0xC0168647E2FE459A_u64))],
                expected: f64::from_bits(0x403DC6CE5D87A7E3_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBFFF0A498F04BB70_u64), y: f64::from_bits(0x40257F9D2A00C9C4_u64),
                polygon: &[(f64::from_bits(0x403205675B7BCBEA_u64), f64::from_bits(0x402EF50A0B71BDF8_u64)), (f64::from_bits(0xC01813DD8125C428_u64), f64::from_bits(0x40293D8E5B5A31F8_u64)), (f64::from_bits(0x40285A6E9ED424A8_u64), f64::from_bits(0x4022818AC94CDE2C_u64)), (f64::from_bits(0x4022FC06674E298C_u64), f64::from_bits(0xC01C458A74CD29F4_u64)), (f64::from_bits(0x402F87C1B2F1F894_u64), f64::from_bits(0x4027338A42F8843E_u64)), (f64::from_bits(0xC02E15F3CB5BD84C_u64), f64::from_bits(0xC01A50B9E15C7C84_u64)), (f64::from_bits(0x401AC97CB932E348_u64), f64::from_bits(0xC0301BCC759FCDDC_u64))],
                expected: f64::from_bits(0x3FF18F261B303D13_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC027A47DAD443D96_u64), y: f64::from_bits(0x4035F3D5A101D522_u64),
                polygon: &[(f64::from_bits(0xC02C9AD16BF40858_u64), f64::from_bits(0xC021E11D9EBCC8F0_u64)), (f64::from_bits(0x4017FDA00F2B54C8_u64), f64::from_bits(0xC027C3C69E3AB84F_u64)), (f64::from_bits(0x40332E49BA4DC7FA_u64), f64::from_bits(0x402111E6849CC0CC_u64)), (f64::from_bits(0x3FDC44FACDB05100_u64), f64::from_bits(0xC031B0F92E70E659_u64)), (f64::from_bits(0x4021E1104AA699E2_u64), f64::from_bits(0xC01EC0F749566CB4_u64)), (f64::from_bits(0x400EAD52EBB1AE40_u64), f64::from_bits(0xBFC42A2262DD4380_u64)), (f64::from_bits(0x402FF386A3B363AC_u64), f64::from_bits(0xC012CD1C5D7389EA_u64)), (f64::from_bits(0x4009C7C65178B310_u64), f64::from_bits(0x4026F326858E578E_u64))],
                expected: f64::from_bits(0x40323D4C40F0F0EF_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40121DD4B29F7424_u64), y: f64::from_bits(0x40222FB3D95C643C_u64),
                polygon: &[(f64::from_bits(0xC0327C464BC33C26_u64), f64::from_bits(0x4031321943730996_u64)), (f64::from_bits(0x4033A745692794E0_u64), f64::from_bits(0xC01AC15CD89639F6_u64)), (f64::from_bits(0xBFD1F530C6317380_u64), f64::from_bits(0xC0330661948827B9_u64)), (f64::from_bits(0xC002B6CD4C2411D0_u64), f64::from_bits(0x40317059C81DFD18_u64)), (f64::from_bits(0x402D628382238A40_u64), f64::from_bits(0x40038FBF8B4E9998_u64)), (f64::from_bits(0x4004F4A97D7D9D80_u64), f64::from_bits(0x402842FD6F9E08C0_u64))],
                expected: f64::from_bits(0x3FF2CA5256E58C7A_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x403473BCBBEE619A_u64), y: f64::from_bits(0xC022011473DE360C_u64),
                polygon: &[(f64::from_bits(0xC030FE7863C4B9BE_u64), f64::from_bits(0x3FABFAD733F1DC00_u64)), (f64::from_bits(0x4010CBD5D594F658_u64), f64::from_bits(0xC01F123E23A02074_u64)), (f64::from_bits(0x4030E5C43B63AEFE_u64), f64::from_bits(0xBFFC8401072300B0_u64)), (f64::from_bits(0x402BA4CF76413ED0_u64), f64::from_bits(0x403318EA081450E4_u64)), (f64::from_bits(0xBFFC8B14A82E7790_u64), f64::from_bits(0x40163FD7183B5288_u64)), (f64::from_bits(0x4030C1A193D53452_u64), f64::from_bits(0x401C05412A38B860_u64))],
                expected: f64::from_bits(0x4020184D3B3DF6AB_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC033ECA183284E9F_u64), y: f64::from_bits(0xC00C51B497626A38_u64),
                polygon: &[],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02E08C24E231EB2_u64), y: f64::from_bits(0xC035BAC8F49D84B6_u64),
                polygon: &[(f64::from_bits(0x40266EE5575B0CD0_u64), f64::from_bits(0x40331584933F2BD4_u64)), (f64::from_bits(0x40301386DDBCF350_u64), f64::from_bits(0xBFA0278DE7ED1800_u64))],
                expected: f64::from_bits(0x4042F537B8903A09_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40150148F6B1ADE4_u64), y: f64::from_bits(0x40102DE4C147A004_u64),
                polygon: &[(f64::from_bits(0x400B32A0C378A238_u64), f64::from_bits(0x4022B060D5AAD7B8_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02C88E53FDD4415_u64), y: f64::from_bits(0xC0326E654E185BB0_u64),
                polygon: &[(f64::from_bits(0x400ABAA16F6031D0_u64), f64::from_bits(0x402FE40E61A823C4_u64)), (f64::from_bits(0x401C82968705B4BC_u64), f64::from_bits(0x402C53834E52D3B0_u64)), (f64::from_bits(0x402DEDD0B7C6E380_u64), f64::from_bits(0xC022E7AB75E950FC_u64)), (f64::from_bits(0xC03357CC77F7C8DE_u64), f64::from_bits(0xC02E4E17EDD28BA8_u64)), (f64::from_bits(0x401A8CACE356DC08_u64), f64::from_bits(0x4025301E6FCDF7D4_u64))],
                expected: f64::from_bits(0x401043D84399DCDC_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02F3AC1DCEDD3A0_u64), y: f64::from_bits(0xBFEB0ACB4D6517E0_u64),
                polygon: &[(f64::from_bits(0x3FF52169427F99B0_u64), f64::from_bits(0xC027C8F087D62720_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x40348FC02586CEF6_u64), y: f64::from_bits(0xC025D23A19FD0B54_u64),
                polygon: &[(f64::from_bits(0x402C4D95F4591F78_u64), f64::from_bits(0x400A8A3C62C258C0_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x402D77D8A0F8B43C_u64), y: f64::from_bits(0x4036EA205412FA26_u64),
                polygon: &[(f64::from_bits(0x402E90554732B384_u64), f64::from_bits(0x4023CA21A6824BB4_u64)), (f64::from_bits(0x3FF592CD9EDDF940_u64), f64::from_bits(0xC020563951425964_u64)), (f64::from_bits(0x4026694E389D3028_u64), f64::from_bits(0xBFFB2991F3000DA0_u64)), (f64::from_bits(0x40339DAE16F996DC_u64), f64::from_bits(0x401CA23704E9EE98_u64)), (f64::from_bits(0x402385A178949DD6_u64), f64::from_bits(0x40007A7C44DCAF30_u64)), (f64::from_bits(0xC0159E136E4CD2DC_u64), f64::from_bits(0x401C118C687760F0_u64)), (f64::from_bits(0x402E2E004E3DCED8_u64), f64::from_bits(0xC031B3A09CA1CA2A_u64)), (f64::from_bits(0x3FF9F46F1023AF50_u64), f64::from_bits(0x4030303C9B2C3A3C_u64))],
                expected: f64::from_bits(0x40273105C0A980FE_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xBF9819AE9725D000_u64), y: f64::from_bits(0x401434E989E51870_u64),
                polygon: &[(f64::from_bits(0x4033A46DFB8F2F46_u64), f64::from_bits(0x402244766193FEBA_u64)), (f64::from_bits(0xC02D9379C75C39E6_u64), f64::from_bits(0xC031E71A6142818E_u64)), (f64::from_bits(0xC01A5CAA529B38C2_u64), f64::from_bits(0x402886B20AC48D54_u64)), (f64::from_bits(0x401C8A63AAB82C48_u64), f64::from_bits(0x401B3BC4FF475470_u64))],
                expected: f64::from_bits(0x40111AF1FC6D4068_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02E5EC09011145C_u64), y: f64::from_bits(0xC00927474BDA5788_u64),
                polygon: &[(f64::from_bits(0x40029AD0FA992A28_u64), f64::from_bits(0x3FF824C81FD39850_u64))],
                expected: f64::from_bits(0x7FF0000000000000_u64),
                tags: &["mdp", "mdp:degenerate_polygon", "mdp:inf_result", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC0317F9896B20C1A_u64), y: f64::from_bits(0xC02F6DF2890B6802_u64),
                polygon: &[(f64::from_bits(0xC031AA66F950EF08_u64), f64::from_bits(0x40335F775FA1BFEE_u64)), (f64::from_bits(0x40315C28B5E61A66_u64), f64::from_bits(0xC02EDA02109B0CC0_u64)), (f64::from_bits(0xC030F33C4A7AE271_u64), f64::from_bits(0xC002D471B0383450_u64)), (f64::from_bits(0xC01176DECC0BB7E6_u64), f64::from_bits(0x40246B80115D4BD4_u64)), (f64::from_bits(0x401D0ADAC94A51F8_u64), f64::from_bits(0x40084BB632B55F38_u64)), (f64::from_bits(0x402A004F46591AE8_u64), f64::from_bits(0x403295C373D9AD1A_u64)), (f64::from_bits(0xC03378DA2707D8BC_u64), f64::from_bits(0xC00C797FCB9D6F28_u64)), (f64::from_bits(0xBFD5F7CB9C8C2D00_u64), f64::from_bits(0x4033A83A0D23E5F4_u64))],
                expected: f64::from_bits(0x4028A1139BD982C4_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC02EF62C294725A3_u64), y: f64::from_bits(0x401029491A8FC918_u64),
                polygon: &[(f64::from_bits(0x402EA955F1623278_u64), f64::from_bits(0x402FD80AE1A5A010_u64)), (f64::from_bits(0xC02AB377362F24A2_u64), f64::from_bits(0x401740E9338D67B4_u64)), (f64::from_bits(0x40190A8D806FE408_u64), f64::from_bits(0xC02DFA625EF8E575_u64)), (f64::from_bits(0x4003175D863503B0_u64), f64::from_bits(0x4003CCDA5E093430_u64)), (f64::from_bits(0xC01AAD372924EBF8_u64), f64::from_bits(0xC0318EE219B715BC_u64)), (f64::from_bits(0x3FD395316C531F00_u64), f64::from_bits(0x40314F425FBDFCFE_u64)), (f64::from_bits(0xC014A27F4466CFDC_u64), f64::from_bits(0x3FE0858E84EBCEE0_u64)), (f64::from_bits(0x403143716507F842_u64), f64::from_bits(0x4030E83269B9ADEA_u64))],
                expected: f64::from_bits(0x40062C49B4B1B3DA_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC00183F5B759F130_u64), y: f64::from_bits(0x402BB4080E1B9CA0_u64),
                polygon: &[(f64::from_bits(0xC031D426D39189C2_u64), f64::from_bits(0x403249864208679A_u64)), (f64::from_bits(0xC025663244A6F657_u64), f64::from_bits(0xC0307FD550F20F44_u64)), (f64::from_bits(0x3FF03EE4C13403A0_u64), f64::from_bits(0x4031A74E57BB006E_u64)), (f64::from_bits(0xC02F4D6D6CF00566_u64), f64::from_bits(0x40176996AED11EC0_u64)), (f64::from_bits(0x40061B3479D09C20_u64), f64::from_bits(0xBFF33CBB774A81B0_u64)), (f64::from_bits(0xC02FC8DA7C6B46B4_u64), f64::from_bits(0xC02A434BF8B6F1C6_u64))],
                expected: f64::from_bits(0x3FF4042069E2EEC2_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0x3FF578D774D61E00_u64), y: f64::from_bits(0xC0357A558AF5D1E6_u64),
                polygon: &[(f64::from_bits(0x403259C287E66B40_u64), f64::from_bits(0x4023ABA16E493894_u64)), (f64::from_bits(0xBFDA0908EACEF500_u64), f64::from_bits(0xC01B17527C3467DC_u64))],
                expected: f64::from_bits(0x402D9E0FF0E48C73_u64),
                tags: &["mdp", "mdp:collinear", "mdp:negative_coords"],
            },
            FrozenMdpCase {
                x: f64::from_bits(0xC033209CF2399A98_u64), y: f64::from_bits(0x402358535B3B03F0_u64),
                polygon: &[(f64::from_bits(0x403101FBE3DC07D8_u64), f64::from_bits(0x401DA60CFDBB6164_u64)), (f64::from_bits(0x402544589D06859A_u64), f64::from_bits(0xC0239C5C91529070_u64)), (f64::from_bits(0x401B4A5EE6DA7880_u64), f64::from_bits(0x40320C902EB95F5A_u64)), (f64::from_bits(0xC01C58D6EDD4E468_u64), f64::from_bits(0x40247089FE7A84F8_u64))],
                expected: f64::from_bits(0x40281B2BE3D76EFC_u64),
                tags: &["mdp", "mdp:negative_coords"],
            },
        ];

        #[test]
        fn frozen_pip_matches_golden_corpus() {
            for case in FROZEN_PIP_GOLDEN {
                let got = point_in_polygon(case.x, case.y, case.polygon);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[test]
        fn frozen_iso_matches_golden_corpus() {
            for case in FROZEN_ISO_GOLDEN {
                let got = slot_intersects_iso(case.slot, case.aabbs);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[test]
        fn frozen_ptsd_matches_golden_corpus() {
            for case in FROZEN_PTSD_GOLDEN {
                let got = point_to_segment_distance(
                    case.px, case.py,
                    case.p1.0, case.p1.1, case.p2.0, case.p2.1,
                );
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[test]
        fn frozen_mdp_matches_golden_corpus() {
            for case in FROZEN_MDP_GOLDEN {
                let got = min_distance_to_polygon(case.x, case.y, case.polygon);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were
        /// ever hand-edited down to something trivially satisfiable.
        #[test]
        fn frozen_zone_aware_corpus_is_non_vacuous() {
            let pip_n = FROZEN_PIP_GOLDEN.len() as u32;
            let iso_n = FROZEN_ISO_GOLDEN.len() as u32;
            let ptsd_n = FROZEN_PTSD_GOLDEN.len() as u32;
            let mdp_n = FROZEN_MDP_GOLDEN.len() as u32;
            let pip_count = |tag: &str| FROZEN_PIP_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            let iso_count = |tag: &str| FROZEN_ISO_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            let ptsd_count = |tag: &str| FROZEN_PTSD_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            let mdp_count = |tag: &str| FROZEN_MDP_GOLDEN.iter()
                .filter(|c| c.tags.contains(&tag)).count() as u32;
            assert!(pip_count("pip") >= 50, "pip: only {}/{} (need >= 50) -- point_in_polygon must be exercised", pip_count("pip"), pip_n);
            assert!(pip_count("pip:inside") >= 10, "pip:inside: only {}/{} (need >= 10) -- inside (true) results must be present", pip_count("pip:inside"), pip_n);
            assert!(pip_count("pip:outside") >= 10, "pip:outside: only {}/{} (need >= 10) -- outside (false) results must be present", pip_count("pip:outside"), pip_n);
            assert!(pip_count("pip:degenerate") >= 3, "pip:degenerate: only {}/{} (need >= 3) -- degenerate (< 3 vertices) polygons must be exercised", pip_count("pip:degenerate"), pip_n);
            assert!(pip_count("pip:horizontal_edge") >= 3, "pip:horizontal_edge: only {}/{} (need >= 3) -- horizontal edges (p1y==p2y ternary) must be exercised", pip_count("pip:horizontal_edge"), pip_n);
            assert!(pip_count("pip:negative_coords") >= 5, "pip:negative_coords: only {}/{} (need >= 5) -- negative-coordinate polygons must be exercised", pip_count("pip:negative_coords"), pip_n);
            assert!(pip_count("pip:concave") >= 3, "pip:concave: only {}/{} (need >= 3) -- concave (5+ vertex) polygons must be exercised", pip_count("pip:concave"), pip_n);
            assert!(iso_count("iso") >= 30, "iso: only {}/{} (need >= 30) -- slot_intersects_iso must be exercised", iso_count("iso"), iso_n);
            assert!(iso_count("iso:hit") >= 10, "iso:hit: only {}/{} (need >= 10) -- hit (true) results must be present", iso_count("iso:hit"), iso_n);
            assert!(iso_count("iso:miss") >= 10, "iso:miss: only {}/{} (need >= 10) -- miss (false) results must be present", iso_count("iso:miss"), iso_n);
            assert!(iso_count("iso:boundary_inclusive") >= 3, "iso:boundary_inclusive: only {}/{} (need >= 3) -- inclusive-boundary cases must be exercised", iso_count("iso:boundary_inclusive"), iso_n);
            assert!(iso_count("iso:empty_aabbs") >= 1, "iso:empty_aabbs: only {}/{} (need >= 1) -- empty AABB list must be exercised", iso_count("iso:empty_aabbs"), iso_n);
            assert!(ptsd_count("ptsd") >= 50, "ptsd: only {}/{} (need >= 50) -- point_to_segment_distance must be exercised", ptsd_count("ptsd"), ptsd_n);
            assert!(ptsd_count("ptsd:degenerate_segment") >= 3, "ptsd:degenerate_segment: only {}/{} (need >= 3) -- degenerate (zero-length) segments must be exercised", ptsd_count("ptsd:degenerate_segment"), ptsd_n);
            assert!(ptsd_count("ptsd:interior_projection") >= 10, "ptsd:interior_projection: only {}/{} (need >= 10) -- interior projection (0<t<1) cases must be exercised", ptsd_count("ptsd:interior_projection"), ptsd_n);
            assert!(ptsd_count("ptsd:clamped_before") >= 5, "ptsd:clamped_before: only {}/{} (need >= 5) -- clamp-before (t<0) cases must be exercised", ptsd_count("ptsd:clamped_before"), ptsd_n);
            assert!(ptsd_count("ptsd:clamped_after") >= 5, "ptsd:clamped_after: only {}/{} (need >= 5) -- clamp-after (t>1) cases must be exercised", ptsd_count("ptsd:clamped_after"), ptsd_n);
            assert!(mdp_count("mdp") >= 50, "mdp: only {}/{} (need >= 50) -- min_distance_to_polygon must be exercised", mdp_count("mdp"), mdp_n);
            assert!(mdp_count("mdp:inf_result") >= 3, "mdp:inf_result: only {}/{} (need >= 3) -- inf result (degenerate polygon) must be exercised", mdp_count("mdp:inf_result"), mdp_n);
            assert!(mdp_count("mdp:collinear") >= 2, "mdp:collinear: only {}/{} (need >= 2) -- collinear (2-vertex) polygons must be exercised", mdp_count("mdp:collinear"), mdp_n);
        }
    }
// --- END generated by scripts/gen_oracle_freeze.py: zone_aware_slot_generation ---

    #[test]
    fn ghost_pad_aligned_slot_reduces() {
        // Pin at (3,4) 5mm away; slot 1..6 along +x: projection 5, reduction 5.
        let r = effective_ghost_pad_radius(6.0, (0.0, 0.0), (3.0, 4.0), &[slot(1.0, 0.0, 6.0, 0.0)]);
        assert!((r - 3.0).abs() < 1e-12);
    }

    #[test]
    fn ghost_pad_perpendicular_slot_no_reduction() {
        let r = effective_ghost_pad_radius(6.0, (0.0, 0.0), (3.0, 0.0), &[slot(1.0, -2.0, 1.0, 2.0)]);
        assert_eq!(r, 6.0);
    }

    #[test]
    fn ghost_pad_coincident_pins_early_out() {
        assert_eq!(effective_ghost_pad_radius(6.0, (2.0, 3.0), (2.0, 3.0), &[slot(0.0, 0.0, 4.0, 0.0)]), 6.0);
    }

    #[test]
    fn ghost_pad_clamps_to_zero() {
        // Slot longer than the base radius -> max(0, negative) -> 0.0.
        assert_eq!(effective_ghost_pad_radius(6.0, (0.0, 0.0), (1.0, 0.0), &[slot(0.0, 0.0, 10.0, 0.0)]), 0.0);
    }

    #[test]
    fn ghost_pad_negative_zero_tie_py_max() {
        // Exact reduction == base -> base - reduction == -0.0 -> py_max keeps +0.0.
        let r = effective_ghost_pad_radius(4.0, (0.0, 0.0), (1.0, 0.0), &[slot(0.0, 0.0, 4.0, 0.0)]);
        assert_eq!(r, 0.0);
        assert!(r.is_sign_positive());
    }

    #[test]
    fn hpwl_basic() {
        let net_pins: Vec<Vec<(String, String)>> =
            vec![vec![("R1".to_string(), "1".into()), ("R2".to_string(), "1".into())]];
        let mut placements: HashMap<String, (f64, f64)> = HashMap::new();
        placements.insert("R2".to_string(), (0.0, 0.0));
        assert_eq!(compute_wirelength("R1", (5.0, 5.0), &net_pins, &placements), 10.0);
    }

    #[test]
    fn hpwl_skips_nets_without_component() {
        let net_pins: Vec<Vec<(String, String)>> = vec![vec![("R2".to_string(), "1".into())]];
        assert_eq!(compute_wirelength("R1", (5.0, 5.0), &net_pins, &HashMap::new()), 0.0);
    }

    #[test]
    fn hpwl_unplaced_members_excluded() {
        let net_pins: Vec<Vec<(String, String)>> =
            vec![vec![("R1".to_string(), "1".into()), ("R2".to_string(), "1".into())]];
        assert_eq!(compute_wirelength("R1", (5.0, 5.0), &net_pins, &HashMap::new()), 0.0);
    }

    #[test]
    fn hpwl_multiple_nets_accumulate() {
        let net_pins: Vec<Vec<(String, String)>> = vec![
            vec![("U1".to_string(), "1".into()), ("U2".to_string(), "1".into()), ("U3".to_string(), "1".into())],
            vec![("U1".to_string(), "2".into()), ("U4".to_string(), "2".into())],
        ];
        let mut placements: HashMap<String, (f64, f64)> = HashMap::new();
        placements.insert("U2".to_string(), (10.0, 0.0));
        placements.insert("U3".to_string(), (10.0, 10.0));
        placements.insert("U4".to_string(), (0.0, -10.0));
        // A: 20 + 10 = 30; B: 0 + 10 = 10; total 40.
        assert_eq!(compute_wirelength("U1", (0.0, 0.0), &net_pins, &placements), 40.0);
    }

    fn viols(
        placements: &[(String, Option<(f64, f64)>)],
        bns: &[(i64, i64, String, String, f64)],
        cell_um: f64,
        w: f64,
        h: f64,
    ) -> Vec<(String, i64, i64, String, String)> {
        match find_critical_bottleneck_violations(placements, bns, cell_um, w, h) {
            Ok(out) => out,
            Err(_) => unreachable!("finite test inputs never produce an index error"),
        }
    }

    #[test]
    fn critical_violations_basic() {
        let placements = vec![("R1".to_string(), Some((0.5, 0.5)))];
        let bns = vec![(0i64, 0i64, "F.Cu".to_string(), "CRITICAL".to_string(), 1.0)];
        let out = viols(&placements, &bns, 1000.0, 5.0, 5.0);
        assert_eq!(out, vec![("R1".to_string(), 0, 0, "F.Cu".to_string(), "CRITICAL".to_string())]);
    }

    #[test]
    fn critical_severity_reads_last_bottleneck() {
        // Verbatim quirk: severity == the LAST bottleneck's severity.
        let placements = vec![("R1".to_string(), Some((0.5, 0.5)))];
        let bns = vec![
            (0i64, 0i64, "F.Cu".to_string(), "CRITICAL".to_string(), 0.9),
            (0i64, 0i64, "B.Cu".to_string(), "MEDIUM".to_string(), 0.5),
        ];
        let out = viols(&placements, &bns, 1000.0, 5.0, 5.0);
        assert_eq!(out[0].4, "MEDIUM");
    }

    #[test]
    fn critical_floor_negative_coords() {
        let placements = vec![("R1".to_string(), Some((-0.001, 0.0)))];
        let bns = vec![(0i64, 0i64, "F.Cu".to_string(), "CRITICAL".to_string(), 1.0)];
        // gx = -1 -> out of grid -> skipped.
        assert!(viols(&placements, &bns, 1000.0, 5.0, 5.0).is_empty());
    }

    #[test]
    fn critical_nan_index_value_error() {
        let placements = vec![("R1".to_string(), Some((f64::NAN, 0.0)))];
        let bns = vec![(0i64, 0i64, "F.Cu".to_string(), "CRITICAL".to_string(), 1.0)];
        assert!(find_critical_bottleneck_violations(&placements, &bns, 1000.0, 5.0, 5.0).is_err());
    }

    #[test]
    fn point_in_polygon_square() {
        let sq = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        assert!(point_in_polygon(5.0, 5.0, &sq));
        assert!(!point_in_polygon(-1.0, 5.0, &sq));
        // top edge y == max counts (y <= max).
        assert!(point_in_polygon(5.0, 10.0, &sq));
    }

    #[test]
    fn point_in_polygon_degenerate() {
        assert!(!point_in_polygon(5.0, 5.0, &[(0.0, 0.0), (10.0, 10.0)]));
        assert!(!point_in_polygon(5.0, 5.0, &[]));
    }

    #[test]
    fn slot_intersects_iso_inclusive() {
        assert!(slot_intersects_iso((4.0, 2.0), &[((0.0, 0.0), (4.0, 4.0))]));
        assert!(!slot_intersects_iso((5.0, 5.0), &[((0.0, 0.0), (4.0, 4.0))]));
        assert!(!slot_intersects_iso((2.0, 2.0), &[]));
    }

    #[test]
    fn min_distance_polygon_triangle() {
        let tri = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)];
        let d = min_distance_to_polygon(0.0, 1.0, &tri);
        assert!((d - sqrt(2.0) / 2.0).abs() < 1e-12);
        assert_eq!(min_distance_to_polygon(0.0, 0.0, &[]), f64::INFINITY);
    }

    #[test]
    fn py_list_min_max_matches_cpython() {
        // NaN only becomes the result if it is FIRST (Python min/max semantics).
        assert_eq!(py_list_min(&[1.0, f64::NAN]), 1.0);
        assert!(py_list_min(&[f64::NAN, 1.0]).is_nan());
        assert_eq!(py_list_max(&[1.0, f64::NAN]), 1.0);
        assert!(py_list_max(&[f64::NAN, 1.0]).is_nan());
        // signed-zero ties keep the first.
        assert_eq!(py_list_min(&[0.0, -0.0]), 0.0);
        assert_eq!(py_list_min(&[-0.0, 0.0]), -0.0);
    }

    fn fb(w: f64, h: f64) -> Option<FootprintBounds> {
        Some(FootprintBounds { w_int: false, w, h_int: false, h })
    }

    #[test]
    fn footprint_radius_3_4_5() {
        // sqrt(3**2 + 4**2)/2 + 1 = 5/2 + 1 = 3.5.
        assert_eq!(footprint_radius(fb(3.0, 4.0), 12.0), 3.5);
    }

    #[test]
    fn footprint_radius_no_bounds_falls_back_to_half_spacing() {
        assert_eq!(footprint_radius(None, 12.0), 6.0);
        assert_eq!(footprint_radius(None, 7.5), 3.75);
    }

    #[test]
    fn footprint_radius_int_bounds_exact_pow() {
        // int bounds: (6**2 + 8**2) == 100 exactly -> sqrt/2 + 1 == 6.0.
        let b = FootprintBounds { w_int: true, w: 6.0, h_int: true, h: 8.0 };
        assert_eq!(footprint_radius(Some(b), 12.0), 6.0);
    }

    #[test]
    fn reserve_slots_within_radius() {
        let slots = [(0.0, 0.0), (3.0, 4.0), (10.0, 10.0), (4.0, 3.0)];
        let got = reserve_slots((0.0, 0.0), 5.0, &slots);
        assert_eq!(got, vec![(0.0, 0.0), (3.0, 4.0), (4.0, 3.0)]);
    }

    #[test]
    fn reserve_slots_exclusive_boundary() {
        // Exactly at radius 5.0 is INCLUSIVE (<=).
        let slots = [(3.0, 4.0), (6.0, 0.0)];
        let got = reserve_slots((0.0, 0.0), 5.0, &slots);
        assert_eq!(got, vec![(3.0, 4.0)]);
    }

    #[test]
    fn distance_matches_pythagorean() {
        assert_eq!(distance((0.0, 0.0), (3.0, 4.0)), 5.0);
        assert_eq!(distance((1.0, 2.0), (1.0, 2.0)), 0.0);
    }
}

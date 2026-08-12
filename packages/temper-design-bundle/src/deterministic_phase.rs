//! Deterministic leaf-stage compute — Wave 4 **Phase 5, final leaves**.
//!
//! Ports the remaining pure compute of the deterministic helper/stage files to
//! Rust:
//!
//! | Python module | Rust function(s) |
//! |---|---|
//! | `deterministic/stages/_phase_rotation.py` | [`effective_ghost_pad_radius`] |
//! | `deterministic/stages/_phase_zones.py` | [`compute_wirelength`] |
//! | `deterministic/stages/_phase_validation.py` | [`find_critical_bottleneck_violations`] |
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
// _phase_rotation.py — effective_ghost_pad_radius (U2 isolation-slot kernel)
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
// _phase_zones.py — compute_wirelength (HPWL)
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
// _phase_validation.py — find_critical_bottleneck_violations
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

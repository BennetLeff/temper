//! `router_v6/constraints_design_rules.py::ClearanceMatrix` / `ZoneManager` —
//! hot-path clearance kernels, ported from the pinned oracle
//! `packages/temper-placer/tests/router_v6/_constraints_design_rules_py_oracle.py`
//! (verbatim copy of commit `4884d284c`, origin/main).
//!
//! `ClearanceMatrix` is queried up to 11 times per constraint check
//! (`constraints_drc_oracle.py`), once per track/pad/via pair. The class-level
//! configuration tables it consults (`_clearances`, `_net_class_rules`,
//! `_differential_pairs`) are small (bounded by the number of net *classes*
//! and registered differential *pairs*, not the number of nets on the
//! board — typically single digits to a few dozen entries), so each kernel
//! here takes those tables as plain `Vec<...>` arguments rather than holding
//! Rust-side mutable state that would need to be kept in sync with the
//! Python object's mutators (`set_net_class`, `add_net_class_rules`, ...).
//! The per-net class resolution (`_net_to_class.get(net, "Default")`, an O(1)
//! Python dict lookup keyed on the potentially-large net table) stays in
//! Python, which is where it is cheapest.
//!
//! Ported (see the module docstring in the oracle for the full worth-porting
//! rationale, carried over verbatim from the Wave 4 triage):
//! - [`base_clearance`] — `ClearanceMatrix._get_base_clearance`
//! - [`get_clearance_kernel`] — `ClearanceMatrix.get_clearance` (differential
//!   pair shortcut + base clearance + zone override)
//! - [`class_attr`] — the shared lookup behind `get_track_width`,
//!   `get_via_diameter`, `get_via_drill`
//! - [`is_differential_pair`] — `ClearanceMatrix.is_differential_pair`
//! - [`diff_pair_required_clearance`] — the `spacing_mm - 2*track_width`
//!   arithmetic inside `add_differential_pair`
//! - [`zone_at`] / [`point_in_polygon`] — `ZoneManager.get_zone_at`
//!
//! NOT ported (see the oracle docstring): `ZoneManager.get_clearance`,
//! `ZoneManager.can_route_net_at`, `ClearanceMatrix.can_route_at` (zero
//! callers repo-wide), `infer_zones` (shapely `convex_hull`/`buffer`, not
//! bit-exactly reproducible in Rust — a library boundary), and the kiutils
//! marshalling in `DesignRulesParser`/`ClearanceMatrix.parse` (one-shot glue,
//! not hot path).
//!
//! ## The NaN trap
//!
//! `_get_base_clearance`'s fallback (`max(clear_a, clear_b)`) and
//! `get_clearance`'s zone override (`max(base_clearance, zone.clearance_mm)`)
//! both use CPython's builtin `max(a, b)`, which keeps the FIRST argument
//! unless the second compares strictly greater — a NaN on either side never
//! wins a `>` comparison, so `max` silently keeps whichever operand it saw
//! first. `f64::max` has IEEE-754-minimum-propagating semantics instead (it
//! discards NaN). Both kernels here go through [`crate::pymath::py_max`],
//! this crate's existing CPython-`max`-shaped helper, rather than `f64::max`.
//!
//! ## Zone point-in-polygon fidelity
//!
//! The oracle's `ZoneManager.get_zone_at` queries a shapely `STRtree` by
//! bounding-box first, then confirms containment with GEOS's
//! `Polygon.contains(Point)` (strict interior; boundary points are
//! excluded). [`point_in_polygon`] here is an even-odd ray-casting test over
//! the *full* zone list (no bounding-box pre-filter — the zone counts in
//! practice are 0-3, so brute force is cheap and the pre-filter is purely a
//! performance optimization in the oracle, not part of its observable
//! behavior for non-overlapping zones), with an exact on-segment pre-check
//! ([`point_on_segment`]) so vertices and edges get a definite "outside"
//! answer rather than depending on plain ray casting's inherent ambiguity
//! there. Two residual caveats, both practically unreachable for the zones
//! this codebase actually constructs (`ClearanceMatrix.parse`'s `HV`/rect
//! zones and `infer_zones`'s output, neither of which overlaps by
//! construction): first, a boundary point that is only *nearly* exact (off
//! by a ULP or two from the polygon's own vertices/edges, e.g. after an
//! upstream floating-point transform) can still land on the wrong side of
//! `point_on_segment`'s exact-cross-product test — GEOS uses its own robust
//! predicates there and may disagree in the last bit; second, if zones DO
//! overlap, `get_zone_at` returns whichever zone the STRtree happens to
//! enumerate first (unspecified order), while this kernel always returns the
//! first zone in list order — for non-overlapping zones (the only case this
//! codebase produces) both return the unique containing zone, so the two
//! orders agree.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::PyModule;

use crate::pymath::py_max;

// ---------------------------------------------------------------------------
// _get_base_clearance
// ---------------------------------------------------------------------------

/// `ClearanceMatrix._get_base_clearance`: symmetric class-pair table lookup
/// (`key1` then `key2`), falling back to `max` of the two classes'
/// individual clearances (each defaulting to `default_clearance` if the
/// class has no registered rules).
pub fn base_clearance(
    class_a: &str,
    class_b: &str,
    clearances: &[(String, String, f64)],
    class_clearance: &[(String, f64)],
    default_clearance: f64,
) -> f64 {
    let table: HashMap<(&str, &str), f64> = clearances
        .iter()
        .map(|(a, b, v)| ((a.as_str(), b.as_str()), *v))
        .collect();

    if let Some(v) = table.get(&(class_a, class_b)) {
        return *v;
    }
    if let Some(v) = table.get(&(class_b, class_a)) {
        return *v;
    }

    let clear_a = class_attr(class_a, class_clearance, default_clearance);
    let clear_b = class_attr(class_b, class_clearance, default_clearance);
    py_max(clear_a, clear_b)
}

#[pyfunction]
pub fn clearance_get_base_clearance_py(
    class_a: String,
    class_b: String,
    clearances: Vec<(String, String, f64)>,
    class_clearance: Vec<(String, f64)>,
    default_clearance: f64,
) -> f64 {
    base_clearance(&class_a, &class_b, &clearances, &class_clearance, default_clearance)
}

// ---------------------------------------------------------------------------
// get_track_width / get_via_diameter / get_via_drill — shared class lookup
// ---------------------------------------------------------------------------

/// The lookup shared by `get_track_width`, `get_via_diameter`,
/// `get_via_drill`, and `_get_class_clearance`: `if net_class in
/// self._net_class_rules: return <attr>`, else the type's own default.
pub fn class_attr(net_class: &str, table: &[(String, f64)], default: f64) -> f64 {
    for (c, v) in table {
        if c == net_class {
            return *v;
        }
    }
    default
}

#[pyfunction]
pub fn clearance_class_attr_py(net_class: String, table: Vec<(String, f64)>, default: f64) -> f64 {
    class_attr(&net_class, &table, default)
}

// ---------------------------------------------------------------------------
// is_differential_pair / differential-pair value lookup
// ---------------------------------------------------------------------------

/// `frozenset([net_a, net_b]) in self._differential_pairs` — unordered
/// membership, so `(a, b)` and `(b, a)` rows both match either query order.
pub fn diff_pair_lookup(net_a: &str, net_b: &str, pairs: &[(String, String, f64)]) -> Option<f64> {
    for (a, b, v) in pairs {
        if (a == net_a && b == net_b) || (a == net_b && b == net_a) {
            return Some(*v);
        }
    }
    None
}

/// `ClearanceMatrix.is_differential_pair`.
pub fn is_differential_pair(net_a: &str, net_b: &str, pairs: &[(String, String, f64)]) -> bool {
    diff_pair_lookup(net_a, net_b, pairs).is_some()
}

#[pyfunction]
pub fn clearance_is_differential_pair_py(
    net_a: String,
    net_b: String,
    pairs: Vec<(String, String, f64)>,
) -> bool {
    is_differential_pair(&net_a, &net_b, &pairs)
}

// ---------------------------------------------------------------------------
// add_differential_pair's clearance arithmetic
// ---------------------------------------------------------------------------

/// `add_differential_pair`'s `required_clearance = spacing_mm - (2 *
/// track_width)`. DRC re-adds the two half-widths back on the check side, so
/// this can legitimately go negative — see the oracle's docstring example.
pub fn diff_pair_required_clearance(spacing_mm: f64, track_width: f64) -> f64 {
    spacing_mm - (2.0 * track_width)
}

#[pyfunction]
pub fn clearance_diff_pair_required_py(spacing_mm: f64, track_width: f64) -> f64 {
    diff_pair_required_clearance(spacing_mm, track_width)
}

// ---------------------------------------------------------------------------
// get_clearance
// ---------------------------------------------------------------------------

/// `ClearanceMatrix.get_clearance`, minus the class/zone *resolution* glue
/// (plain attribute/dict access with no numeric risk, left in Python): the
/// differential-pair shortcut, the base-clearance lookup, and the
/// NaN-sensitive zone-override `max`.
///
/// `zone` is `Some((zone_name, zone_clearance_mm))` when the caller supplied
/// `x`/`y`, `self.zone_manager` is set, AND `zone_manager.get_zone_at(x, y)`
/// found a containing zone — i.e. the oracle's `if zone:` guard has already
/// been evaluated by the caller. The oracle's `zone.name == "HV"` gate and
/// `class_a == "HighVoltage" or class_b == "HighVoltage"` test are
/// reproduced here since both feed directly into the `max` this kernel must
/// get right.
#[allow(clippy::too_many_arguments)]
pub fn get_clearance_kernel(
    net_a: &str,
    net_b: &str,
    class_a: &str,
    class_b: &str,
    pairs: &[(String, String, f64)],
    clearances: &[(String, String, f64)],
    class_clearance: &[(String, f64)],
    default_clearance: f64,
    zone: Option<(&str, f64)>,
) -> f64 {
    // 0. Differential pair shortcut.
    if let Some(v) = diff_pair_lookup(net_a, net_b, pairs) {
        return v;
    }

    // 1. Class-based baseline.
    let base = base_clearance(class_a, class_b, clearances, class_clearance, default_clearance);

    // 2. Spatial override.
    if let Some((zone_name, zone_clearance_mm)) = zone {
        let zone_applies =
            zone_name == "HV" && (class_a == "HighVoltage" || class_b == "HighVoltage");
        if zone_applies {
            return py_max(base, zone_clearance_mm);
        }
    }

    base
}

#[pyfunction]
#[pyo3(signature = (net_a, net_b, class_a, class_b, pairs, clearances, class_clearance, default_clearance, zone=None))]
#[allow(clippy::too_many_arguments)]
pub fn clearance_get_clearance_py(
    net_a: String,
    net_b: String,
    class_a: String,
    class_b: String,
    pairs: Vec<(String, String, f64)>,
    clearances: Vec<(String, String, f64)>,
    class_clearance: Vec<(String, f64)>,
    default_clearance: f64,
    zone: Option<(String, f64)>,
) -> f64 {
    let zone_ref = zone.as_ref().map(|(name, clearance)| (name.as_str(), *clearance));
    get_clearance_kernel(
        &net_a,
        &net_b,
        &class_a,
        &class_b,
        &pairs,
        &clearances,
        &class_clearance,
        default_clearance,
        zone_ref,
    )
}

// ---------------------------------------------------------------------------
// ZoneManager.get_zone_at
// ---------------------------------------------------------------------------

/// Exact on-segment test (collinear via a zero cross product, then a
/// bounding-box check) used to give polygon EDGES and VERTICES a definite,
/// non-ray-casting-dependent answer before falling through to the even-odd
/// sweep below. Plain ray casting is only ambiguous exactly ON a boundary
/// (a ray through a vertex can toggle 0, 1, or 2 times depending on which
/// way its neighbours lean) -- for points strictly off the boundary this
/// pre-check never fires and the sweep is the sole decider.
fn point_on_segment(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> bool {
    let cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
    if cross != 0.0 {
        return false;
    }
    let min_x = ax.min(bx);
    let max_x = ax.max(bx);
    let min_y = ay.min(by);
    let max_y = ay.max(by);
    px >= min_x && px <= max_x && py >= min_y && py <= max_y
}

/// Even-odd ray-casting point-in-polygon test. See the module docstring for
/// the fidelity discussion relative to GEOS's `Polygon.contains`.
///
/// Boundary points (vertices and edges) are treated as OUTSIDE (matching
/// `contains`, not `covers`): [`point_on_segment`] checks every edge first
/// and returns `false` immediately on a hit, sidestepping plain ray
/// casting's inherent ambiguity exactly at a vertex.
pub fn point_in_polygon(x: f64, y: f64, poly: &[(f64, f64)]) -> bool {
    if poly.len() < 3 {
        return false;
    }
    let n = poly.len();

    for i in 0..n {
        let (ax, ay) = poly[i];
        let (bx, by) = poly[(i + 1) % n];
        if point_on_segment(x, y, ax, ay, bx, by) {
            return false;
        }
    }

    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let (xi, yi) = poly[i];
        let (xj, yj) = poly[j];
        if (yi > y) != (yj > y) {
            let x_intersect = (xj - xi) * (y - yi) / (yj - yi) + xi;
            if x < x_intersect {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

/// `ZoneManager.get_zone_at`: the index of the first zone (in list order)
/// containing `(x, y)`, or `None` if unzoned.
pub fn zone_at(x: f64, y: f64, polygons: &[Vec<(f64, f64)>]) -> Option<usize> {
    polygons.iter().position(|poly| point_in_polygon(x, y, poly))
}

#[pyfunction]
pub fn clearance_zone_at_py(x: f64, y: f64, polygons: Vec<Vec<(f64, f64)>>) -> Option<usize> {
    zone_at(x, y, &polygons)
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(clearance_get_base_clearance_py, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_class_attr_py, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_is_differential_pair_py, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_diff_pair_required_py, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_get_clearance_py, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_zone_at_py, module)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests (Rust-side; the Python differential is the primary proof)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_clearance_prefers_key1_then_key2_then_class_fallback() {
        let clearances = vec![("Power".to_string(), "Signal".to_string(), 0.3)];
        assert_eq!(base_clearance("Power", "Signal", &clearances, &[], 0.2), 0.3);
        // key2 (reversed order) also matches.
        assert_eq!(base_clearance("Signal", "Power", &clearances, &[], 0.2), 0.3);
        // No table entry: falls back to max of class clearances (both default here).
        assert_eq!(base_clearance("GND", "HV", &clearances, &[], 0.2), 0.2);
    }

    #[test]
    fn base_clearance_max_keeps_first_nan_not_f64_max() {
        let class_clearance = vec![("HighVoltage".to_string(), f64::NAN)];
        // max(clear_a=NAN, clear_b=0.2): CPython keeps clear_a (NaN) because
        // `0.2 > NaN` is False. f64::max would discard the NaN and return 0.2.
        let got = base_clearance("HighVoltage", "Signal", &[], &class_clearance, 0.2);
        assert!(got.is_nan(), "expected NaN to survive py_max, got {got}");
    }

    #[test]
    fn class_attr_falls_back_to_default() {
        let table = vec![("Power".to_string(), 0.5)];
        assert_eq!(class_attr("Power", &table, 0.2), 0.5);
        assert_eq!(class_attr("Signal", &table, 0.2), 0.2);
    }

    #[test]
    fn diff_pair_lookup_is_order_independent() {
        let pairs = vec![("USB_D+".to_string(), "USB_D-".to_string(), 0.1)];
        assert_eq!(diff_pair_lookup("USB_D+", "USB_D-", &pairs), Some(0.1));
        assert_eq!(diff_pair_lookup("USB_D-", "USB_D+", &pairs), Some(0.1));
        assert_eq!(diff_pair_lookup("USB_D-", "OTHER", &pairs), None);
    }

    #[test]
    fn diff_pair_required_clearance_matches_formula() {
        assert_eq!(diff_pair_required_clearance(0.25, 0.15), 0.25 - 0.30);
    }

    #[test]
    fn get_clearance_kernel_short_circuits_on_differential_pair() {
        let pairs = vec![("A".to_string(), "B".to_string(), 0.1)];
        let got = get_clearance_kernel(
            "A", "B", "Signal", "Signal", &pairs, &[], &[], 0.2, None,
        );
        assert_eq!(got, 0.1);
    }

    #[test]
    fn get_clearance_kernel_applies_hv_zone_override_via_py_max() {
        let got = get_clearance_kernel(
            "HV_NET",
            "SIG_NET",
            "HighVoltage",
            "Signal",
            &[],
            &[],
            &[],
            0.2,
            Some(("HV", 3.0)),
        );
        assert_eq!(got, 3.0);
    }

    #[test]
    fn get_clearance_kernel_ignores_zone_when_neither_net_is_hv() {
        let got = get_clearance_kernel(
            "SIG_A",
            "SIG_B",
            "Signal",
            "Signal",
            &[],
            &[],
            &[],
            0.2,
            Some(("HV", 3.0)),
        );
        assert_eq!(got, 0.2);
    }

    #[test]
    fn point_in_polygon_excludes_boundary_like_contains() {
        let square = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        assert!(point_in_polygon(5.0, 5.0, &square));
        assert!(!point_in_polygon(20.0, 20.0, &square));
    }

    #[test]
    fn point_in_polygon_excludes_exact_vertices_and_edges() {
        // Plain ray casting is ambiguous exactly at a vertex; the
        // point_on_segment pre-check must give a definite "outside" answer
        // for every corner and every mid-edge point of this square.
        let square = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        for &(x, y) in &[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (10.0, 5.0), (5.0, 0.0)] {
            assert!(!point_in_polygon(x, y, &square), "boundary point ({x}, {y}) should be OUTSIDE");
        }
    }

    #[test]
    fn zone_at_returns_first_containing_zone_in_list_order() {
        let a = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)];
        let b = vec![(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)];
        let polygons = vec![a, b];
        assert_eq!(zone_at(5.0, 5.0, &polygons), Some(0));
        assert_eq!(zone_at(105.0, 105.0, &polygons), Some(1));
        assert_eq!(zone_at(500.0, 500.0, &polygons), None);
    }
}

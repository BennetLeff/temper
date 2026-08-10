// Wave 4, spatial-tier-2 unit: `router_v6/connectivity.py`'s union-find
// connectivity kernel and its ten non-zone touch predicates.
//
// `verify_net_connectivity` builds a union-find over the sorted copper
// items (pads, tracks, vias, zones), unions every touching pair, groups
// the pads by component root, and reports the components.  The union-find
// and every predicate that is pure geometry (no shapely) run here; the
// four ``_zone_*`` predicates are JUSTIFIED-KEEP — they call GEOS
// `contains` / `touches` / `intersects` on `CopperZone.polygon`, whose
// bit-exact reproduction is a "vendor GEOS" bar
// (`docs/evidence/2026-08-04-geos-polygon-algebra-spike.md` §3).  The
// Python shim evaluates the zone predicates and hands this kernel the
// resulting (i, j) union pairs.
//
// The final partition is order-independent: the reference's `union` sets
// `parent[max(left_root, right_root)] = min(left_root, right_root)`, so
// every set's root is its minimum item index regardless of union order or
// path-halving intermediate state.  Applying the zone pairs in any order
// therefore yields the same components as the reference, and the kernel
// returns each component's pad indices (ascending).
//
// Predicates transcribed verbatim from the pre-migration module, reusing
// the already-migrated kernels where the reference itself calls them:
// * `point_to_segment_distance` / `segment_to_segment_distance` —
//   `router_v6/constraints_geometry.py` already delegates to
//   `drc_constraints_geometry.rs`; this module calls the same pure fns.
// * `Point.distance_to` — the reference resolves to
//   `temper_geometry.point_distance_py` (`primitives::point_distance`,
//   the `+ 1e-12` epsilon-guarded distance); reused unchanged.
// * pad-rotation unwinding — `_to_pad_coordinates` is
//   `rotate_world_to_local_deg`, i.e. `math.radians(rotation)` (which is
//   `rotation * (PI / 180.0)`) then R(+theta) with host-libm cos/sin
//   (bit-exactness class B1 via `host_math`).
// * `max`/`min` in the Liang-Barsky box test are CPython builtins —
//   `py_max`/`py_min` (first-argument NaN/tie semantics), shared from
//   `creepage_check.rs`.
//
// `CONTACT_TOLERANCE_MM = 1e-4` is the module constant the reference
// reads; the shim passes nothing for it and the kernel hardcodes the same
// literal.

pub const CONTACT_TOLERANCE_MM: f64 = 1e-4;

/// A copper pad, denormalized to the fields the predicates read.
pub struct PadData {
    pub x: f64,
    pub y: f64,
    pub rotation: f64,
    pub w: f64,
    pub h: f64,
    pub is_circle: bool,
    pub layers: Vec<i64>,
}

/// A copper track segment, denormalized.
pub struct TrackData {
    pub x1: f64,
    pub y1: f64,
    pub x2: f64,
    pub y2: f64,
    pub layer: i64,
    pub width: f64,
}

/// A copper via, denormalized.
pub struct ViaData {
    pub x: f64,
    pub y: f64,
    pub diameter: f64,
    pub layers: Vec<i64>,
}

/// `_to_pad_coordinates`: world point -> pad-local frame via
/// `rotate_world_to_local_deg` (R(+theta), the inverse of KiCad's
/// R(-theta)).
fn to_pad_coordinates(px: f64, py: f64, pad: &PadData) -> (f64, f64) {
    let dx = px - pad.x;
    let dy = py - pad.y;
    let theta = pad.rotation * (std::f64::consts::PI / 180.0);
    let c = crate::host_math::cos(theta);
    let s = crate::host_math::sin(theta);
    (dx * c - dy * s, dx * s + dy * c)
}

/// `_point_in_pad(point, pad, radius)`.
fn point_in_pad(px: f64, py: f64, pad: &PadData, radius: f64) -> bool {
    let (local_x, local_y) = to_pad_coordinates(px, py, pad);
    let half_x = pad.w / 2.0 + radius;
    let half_y = pad.h / 2.0 + radius;
    if pad.is_circle {
        return local_x * local_x + local_y * local_y <= half_x * half_x + CONTACT_TOLERANCE_MM;
    }
    local_x.abs() <= half_x + CONTACT_TOLERANCE_MM && local_y.abs() <= half_y + CONTACT_TOLERANCE_MM
}

/// `_segment_intersects_box`: Liang-Barsky clipping against pad-local
/// rectangular copper.
fn segment_intersects_box(start: (f64, f64), end: (f64, f64), half_x: f64, half_y: f64) -> bool {
    let dx = end.0 - start.0;
    let dy = end.1 - start.1;
    let mut lower = 0.0_f64;
    let mut upper = 1.0_f64;
    for (position, delta, mut bound) in [(start.0, dx, half_x), (start.1, dy, half_y)] {
        bound += CONTACT_TOLERANCE_MM;
        if delta == 0.0 {
            if position.abs() > bound {
                return false;
            }
            continue;
        }
        let entry = (-bound - position) / delta;
        let exit = (bound - position) / delta;
        lower = crate::creepage_check::py_max(lower, crate::creepage_check::py_min(entry, exit));
        upper = crate::creepage_check::py_min(upper, crate::creepage_check::py_max(entry, exit));
    }
    lower <= upper && lower <= 1.0 && upper >= 0.0
}

/// `_segment_touches_pad(segment, pad, radius)`.
fn segment_touches_pad(seg: &TrackData, pad: &PadData, radius: f64) -> bool {
    if pad.is_circle {
        let d = crate::drc_constraints_geometry::point_to_segment_distance(
            pad.x, pad.y, seg.x1, seg.y1, seg.x2, seg.y2,
        );
        return d <= pad.w / 2.0 + radius + CONTACT_TOLERANCE_MM;
    }
    let start = to_pad_coordinates(seg.x1, seg.y1, pad);
    let end = to_pad_coordinates(seg.x2, seg.y2, pad);
    let half_x = pad.w / 2.0 + radius;
    let half_y = pad.h / 2.0 + radius;
    segment_intersects_box(start, end, half_x, half_y)
}

/// `_tracks_touch`: same-layer tracks whose segment distance is within the
/// half-width sum + tolerance.
fn tracks_touch(left: &TrackData, right: &TrackData) -> bool {
    let clearance = (left.width + right.width) / 2.0 + CONTACT_TOLERANCE_MM;
    crate::drc_constraints_geometry::segment_to_segment_distance(
        left.x1, left.y1, left.x2, left.y2, right.x1, right.y1, right.x2, right.y2,
    ) <= clearance
}

/// `_track_touches_via`.
fn track_touches_via(track: &TrackData, via: &ViaData) -> bool {
    crate::drc_constraints_geometry::point_to_segment_distance(
        via.x, via.y, track.x1, track.y1, track.x2, track.y2,
    ) <= (track.width / 2.0 + via.diameter / 2.0 + CONTACT_TOLERANCE_MM)
}

/// `_points_touch`: `Point.distance_to` (the `+1e-12` guarded kernel) with
/// the contact tolerance.
fn points_touch(ax: f64, ay: f64, bx: f64, by: f64) -> bool {
    crate::primitives::point_distance(&crate::types::Point::new(ax, ay), &crate::types::Point::new(bx, by))
        <= CONTACT_TOLERANCE_MM
}

/// `_via_touches_pad`: via center within the pad's contact circle inflated
/// by the via radius.
fn via_touches_pad(via: &ViaData, pad: &PadData) -> bool {
    point_in_pad(via.x, via.y, pad, via.diameter / 2.0)
}

/// `_pads_touch`: either pad's center inside the other's contact shape.
fn pads_touch(left: &PadData, right: &PadData) -> bool {
    point_in_pad(left.x, left.y, right, 0.0) || point_in_pad(right.x, right.y, left, 0.0)
}

fn layers_intersect(a: &[i64], b: &[i64]) -> bool {
    a.iter().any(|x| b.contains(x))
}

/// The connectivity union-find over pads, tracks and vias, plus the zone
/// union pairs computed in Python from the kept shapely predicates.
/// Returns each component's pad indices in ascending order.
pub fn connectivity_components(
    pads: &[PadData],
    tracks: &[TrackData],
    vias: &[ViaData],
    zone_pairs: &[(usize, usize)],
    total_items: usize,
) -> Vec<Vec<usize>> {
    let pad_count = pads.len();
    let track_start = pad_count;
    let via_start = track_start + tracks.len();
    let zone_start = via_start + vias.len();
    debug_assert!(total_items >= zone_start);

    let mut parent: Vec<usize> = (0..total_items).collect();

    fn find(parent: &mut [usize], mut index: usize) -> usize {
        while parent[index] != index {
            parent[index] = parent[parent[index]];
            index = parent[index];
        }
        index
    }

    fn union(parent: &mut [usize], left: usize, right: usize) {
        let left_root = find(parent, left);
        let right_root = find(parent, right);
        if left_root != right_root {
            parent[left_root.max(right_root)] = left_root.min(right_root);
        }
    }

    for left in 0..tracks.len() {
        for right in (left + 1)..tracks.len() {
            let t = &tracks[left];
            let o = &tracks[right];
            if t.layer == o.layer && tracks_touch(t, o) {
                union(&mut parent, track_start + left, track_start + right);
            }
        }
        let t = &tracks[left];
        for (pad_index, pad) in pads.iter().enumerate() {
            if pad.layers.contains(&t.layer) && segment_touches_pad(t, pad, t.width / 2.0) {
                union(&mut parent, track_start + left, pad_index);
            }
        }
        for (via_index, via) in vias.iter().enumerate() {
            if via.layers.contains(&t.layer) && track_touches_via(t, via) {
                union(&mut parent, track_start + left, via_start + via_index);
            }
        }
    }

    for left in 0..pads.len() {
        for right in (left + 1)..pads.len() {
            let a = &pads[left];
            let b = &pads[right];
            if layers_intersect(&a.layers, &b.layers) && pads_touch(a, b) {
                union(&mut parent, left, right);
            }
        }
    }

    for left in 0..vias.len() {
        for right in (left + 1)..vias.len() {
            let a = &vias[left];
            let b = &vias[right];
            if layers_intersect(&a.layers, &b.layers) && points_touch(a.x, a.y, b.x, b.y) {
                union(&mut parent, via_start + left, via_start + right);
            }
        }
        let a = &vias[left];
        for (pad_index, pad) in pads.iter().enumerate() {
            if layers_intersect(&a.layers, &pad.layers) && via_touches_pad(a, pad) {
                union(&mut parent, via_start + left, pad_index);
            }
        }
    }

    for &(i, j) in zone_pairs {
        union(&mut parent, i, j);
    }

    // Group pads by canonical root. Iterating pads in index order keeps each
    // group ascending; grouping by BTreeMap key keeps the group order
    // deterministic (the Python shim re-sorts by (-len, identity) anyway).
    let mut groups: std::collections::BTreeMap<usize, Vec<usize>> = std::collections::BTreeMap::new();
    for (pad_index, _) in pads.iter().enumerate() {
        groups.entry(find(&mut parent, pad_index)).or_default().push(pad_index);
    }
    groups.into_values().collect()
}

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// pyo3 surface for `connectivity_components`.
///
/// `pads` is a flat `[x, y, rotation, w, h]` array (5 per pad),
/// `pad_shapes` is `1` for shape `"circle"` else `0`, `tracks` is a flat
/// `[x1, y1, x2, y2, width]` array (5 per track), `vias` is a flat
/// `[x, y, diameter]` array (3 per via); layer lists accompany each item.
#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn connectivity_components_py(
    pads: Vec<f64>,
    pad_shapes: Vec<i64>,
    pad_layers: Vec<Vec<i64>>,
    tracks: Vec<f64>,
    track_layers: Vec<i64>,
    vias: Vec<f64>,
    via_layers: Vec<Vec<i64>>,
    zone_pairs: Vec<(i64, i64)>,
    total_items: i64,
) -> PyResult<Vec<Vec<i64>>> {
    let n_pads = pads.len() / 5;
    if !pads.len().is_multiple_of(5) || pad_shapes.len() != n_pads || pad_layers.len() != n_pads {
        return Err(PyValueError::new_err("pad array length mismatch"));
    }
    let n_tracks = tracks.len() / 5;
    if !tracks.len().is_multiple_of(5) || track_layers.len() != n_tracks {
        return Err(PyValueError::new_err("track array length mismatch"));
    }
    let n_vias = vias.len() / 3;
    if !vias.len().is_multiple_of(3) || via_layers.len() != n_vias {
        return Err(PyValueError::new_err("via array length mismatch"));
    }
    let zone_start = n_pads + n_tracks + n_vias;
    let total_items = total_items as usize;
    if total_items < zone_start {
        return Err(PyValueError::new_err("total_items smaller than item counts"));
    }
    for &(i, j) in &zone_pairs {
        if i < 0 || j < 0 || i as usize >= total_items || j as usize >= total_items {
            return Err(PyValueError::new_err("zone pair index out of range"));
        }
    }

    temper_py_bridge::catch_unwind(move || {
        let pads_v: Vec<PadData> = (0..n_pads)
            .map(|k| PadData {
                x: pads[5 * k],
                y: pads[5 * k + 1],
                rotation: pads[5 * k + 2],
                w: pads[5 * k + 3],
                h: pads[5 * k + 4],
                is_circle: pad_shapes[k] == 1,
                layers: pad_layers[k].clone(),
            })
            .collect();
        let tracks_v: Vec<TrackData> = (0..n_tracks)
            .map(|k| TrackData {
                x1: tracks[5 * k],
                y1: tracks[5 * k + 1],
                x2: tracks[5 * k + 2],
                y2: tracks[5 * k + 3],
                layer: track_layers[k],
                width: tracks[5 * k + 4],
            })
            .collect();
        let vias_v: Vec<ViaData> = (0..n_vias)
            .map(|k| ViaData {
                x: vias[3 * k],
                y: vias[3 * k + 1],
                diameter: vias[3 * k + 2],
                layers: via_layers[k].clone(),
            })
            .collect();
        let zone_pairs_v: Vec<(usize, usize)> =
            zone_pairs.into_iter().map(|(i, j)| (i as usize, j as usize)).collect();
        let components = connectivity_components(&pads_v, &tracks_v, &vias_v, &zone_pairs_v, total_items);
        components
            .into_iter()
            .map(|g| g.into_iter().map(|i| i as i64).collect())
            .collect()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(connectivity_components_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn pad(x: f64, y: f64, w: f64, h: f64, circle: bool, layers: &[i64]) -> PadData {
        PadData {
            x,
            y,
            rotation: 0.0,
            w,
            h,
            is_circle: circle,
            layers: layers.to_vec(),
        }
    }

    fn track(x1: f64, y1: f64, x2: f64, y2: f64, layer: i64, width: f64) -> TrackData {
        TrackData { x1, y1, x2, y2, layer, width }
    }

    fn via(x: f64, y: f64, d: f64, layers: &[i64]) -> ViaData {
        ViaData { x, y, diameter: d, layers: layers.to_vec() }
    }

    #[cfg_attr(test, test)]
    fn two_circle_pads_touch_at_contact_radius() {
        // centers 0.5 apart with w=h=1 (contact radius 0.5): each center is
        // exactly on the other's contact boundary.
        let pads = vec![pad(0.0, 0.0, 1.0, 1.0, true, &[0]), pad(0.5, 0.0, 1.0, 1.0, true, &[0])];
        let comps = connectivity_components(&pads, &[], &[], &[], 2);
        assert_eq!(comps, vec![vec![0, 1]]);
    }

    #[cfg_attr(test, test)]
    fn circle_pads_beyond_contact_radius_do_not_touch() {
        let pads = vec![pad(0.0, 0.0, 1.0, 1.0, true, &[0]), pad(1.0, 0.0, 1.0, 1.0, true, &[0])];
        let comps = connectivity_components(&pads, &[], &[], &[], 2);
        assert_eq!(comps, vec![vec![0], vec![1]]);
    }

    #[cfg_attr(test, test)]
    fn different_layers_never_join() {
        let pads = vec![pad(0.0, 0.0, 1.0, 1.0, true, &[0]), pad(0.0, 0.0, 1.0, 1.0, true, &[1])];
        let comps = connectivity_components(&pads, &[], &[], &[], 2);
        assert_eq!(comps, vec![vec![0], vec![1]]);
    }

    #[cfg_attr(test, test)]
    fn shared_endpoint_tracks_touch() {
        let t1 = track(0.0, 0.0, 2.0, 0.0, 0, 0.5);
        let t2 = track(2.0, 0.0, 4.0, 0.0, 0, 0.5);
        let comps = connectivity_components(&[], &[t1, t2], &[], &[], 2);
        assert_eq!(comps, Vec::<Vec<usize>>::new());
        // track-track touch is exercised through pads: both tracks connect
        // to a pad each, and the tracks themselves join.
        let p1 = pad(1.0, 0.0, 0.5, 0.5, true, &[0]);
        let p2 = pad(3.0, 0.0, 0.5, 0.5, true, &[0]);
        let t1 = track(0.0, 0.0, 2.0, 0.0, 0, 0.5);
        let t2 = track(2.0, 0.0, 4.0, 0.0, 0, 0.5);
        let comps = connectivity_components(&[p1, p2], &[t1, t2], &[], &[], 4);
        assert_eq!(comps, vec![vec![0, 1]]);
    }

    #[cfg_attr(test, test)]
    fn via_via_same_point_joins_on_shared_layer() {
        let v = via(3.0, 3.0, 0.6, &[0, 1]);
        let comps = connectivity_components(&[], &[], &[v, via(3.0, 3.0, 0.6, &[0, 1])], &[], 2);
        assert_eq!(comps, Vec::<Vec<usize>>::new());
        // via-via joining is observable through a shared pad pair: two pads
        // joined only through the coincident vias.
        let p1 = pad(0.0, 0.0, 0.5, 0.5, true, &[0]);
        let p2 = pad(0.5, 0.0, 0.5, 0.5, true, &[0]);
        let v1 = via(0.25, 0.0, 0.6, &[0]);
        let v2 = via(0.25, 0.0, 0.6, &[0]);
        // p1 --via-- via-- p2 on layer 0: pad contact radius 0.25 + via
        // radius 0.3 = 0.55 >= 0.25 (each pad-to-via distance).
        let comps = connectivity_components(&[p1, p2], &[], &[v1, v2], &[], 4);
        assert_eq!(comps, vec![vec![0, 1]]);
    }

    #[cfg_attr(test, test)]
    fn zone_pairs_join_pads() {
        // zone pair union applied directly: pads 0 and 1 joined by a zone
        // (the zone predicates stay in Python; this pins the pair path).
        let p1 = pad(0.0, 0.0, 0.5, 0.5, true, &[0]);
        let p2 = pad(10.0, 10.0, 0.5, 0.5, true, &[0]);
        let comps = connectivity_components(&[p1, p2], &[], &[], &[(2, 0), (2, 1)], 3);
        assert_eq!(comps, vec![vec![0, 1]]);
    }

    #[cfg_attr(test, test)]
    fn rotated_rect_pad_accepts_crossing_track() {
        // 2x2 rect rotated 45 deg; the y=-x diagonal track crosses it.
        let pr = PadData {
            x: 0.0,
            y: 0.0,
            rotation: 45.0,
            w: 2.0,
            h: 2.0,
            is_circle: false,
            layers: vec![0],
        };
        let tr = track(-3.0, 3.0, 3.0, -3.0, 0, 0.2);
        assert!(segment_touches_pad(&tr, &pr, 0.1));
        let comps = connectivity_components(&[pr], &[tr], &[], &[], 2);
        assert_eq!(comps, vec![vec![0]]);
    }

    #[cfg_attr(test, test)]
    fn liang_barsky_misses_offset_line() {
        // A line parallel to a rect edge but 2 units away does not touch a
        // 1x1 rect.
        let pr = PadData { x: 0.0, y: 0.0, rotation: 0.0, w: 1.0, h: 1.0, is_circle: false, layers: vec![0] };
        let tr = track(-5.0, 3.0, 5.0, 3.0, 0, 0.2);
        assert!(!segment_touches_pad(&tr, &pr, 0.1));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("connectivity_kernels::tests::two_circle_pads_touch_at_contact_radius", two_circle_pads_touch_at_contact_radius),
        ("connectivity_kernels::tests::circle_pads_beyond_contact_radius_do_not_touch", circle_pads_beyond_contact_radius_do_not_touch),
        ("connectivity_kernels::tests::different_layers_never_join", different_layers_never_join),
        ("connectivity_kernels::tests::shared_endpoint_tracks_touch", shared_endpoint_tracks_touch),
        ("connectivity_kernels::tests::via_via_same_point_joins_on_shared_layer", via_via_same_point_joins_on_shared_layer),
        ("connectivity_kernels::tests::zone_pairs_join_pads", zone_pairs_join_pads),
        ("connectivity_kernels::tests::rotated_rect_pad_accepts_crossing_track", rotated_rect_pad_accepts_crossing_track),
        ("connectivity_kernels::tests::liang_barsky_misses_offset_line", liang_barsky_misses_offset_line),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

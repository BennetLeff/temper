//! Deterministic connectivity-validation leaf kernel — Wave 4, Phase 5.
//!
//! The per-net connectivity algorithm of
//! `deterministic/stages/connectivity_validation.py`:
//! `ConnectivityValidationStage._validate_net_connectivity` plus its touch
//! predicates. UnionFind semantics are transcribed bit-exactly from
//! `core/topology.py` (path-compressed `find`, `union` always attaches
//! `ra` under `rb`, `get_components` iterates item IDs in insertion order);
//! the pad-touch predicate calls temper-geometry's single-source-of-truth
//! `point_to_rotated_rect_distance` — the same function the Python arm
//! delegates to — so the `<= 1e-4` boundary is one function, not two.
//!
//! The Python module stays a delegation shim: drc-oracle geometry
//! extraction, per-net grouping, plane-net/empty-net skipping, `run()`
//! orchestration, logging and `fail_on_violations` raising all stay Python.

use pyo3::prelude::*;

use std::panic::AssertUnwindSafe;

use temper_geometry::drc_constraints_geometry::point_to_rotated_rect_distance;

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python exception
/// instead of poisoning the interpreter.
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match std::panic::catch_unwind(AssertUnwindSafe(body)) {
        Ok(r) => r,
        Err(_) => Err(pyo3::exceptions::PyRuntimeError::new_err(
            "panic in connectivity_validate_net kernel",
        )),
    }
}

/// `_UnionFind` replication — `core/topology.py` verbatim semantics.
struct UnionFind {
    parent: Vec<usize>,
}

impl UnionFind {
    fn new(n: usize) -> Self {
        UnionFind { parent: (0..n).collect() }
    }

    fn find(&mut self, x: usize) -> usize {
        let p = self.parent[x];
        if p != x {
            let root = self.find(p);
            self.parent[x] = root;
            root
        } else {
            x
        }
    }

    fn union(&mut self, a: usize, b: usize) {
        let ra = self.find(a);
        let rb = self.find(b);
        if ra != rb {
            self.parent[ra] = rb;
        }
    }

    /// `get_components` — iterate items in insertion order (0..n), grouping
    /// by final root, first-appearance order preserved.
    fn get_components(&mut self) -> Vec<(usize, Vec<usize>)> {
        let mut comps: Vec<(usize, Vec<usize>)> = Vec::new();
        for elem in 0..self.parent.len() {
            let root = self.find(elem);
            match comps.iter_mut().find(|(r, _)| *r == root) {
                Some((_, members)) => members.push(elem),
                None => comps.push((root, vec![elem])),
            }
        }
        comps
    }
}

struct PadRec {
    x: f64,
    y: f64,
    layer: i64,
    id: String,
    w: f64,
    h: f64,
    rotation: f64,
}

struct TrackRec {
    sx: f64,
    sy: f64,
    ex: f64,
    ey: f64,
    layer: i64,
}

impl TrackRec {
    fn start(&self) -> (f64, f64) {
        (self.sx, self.sy)
    }
    fn end(&self) -> (f64, f64) {
        (self.ex, self.ey)
    }
}

struct ViaRec {
    x: f64,
    y: f64,
}

fn pts_eq(ax: f64, ay: f64, bx: f64, by: f64) -> bool {
    ax == bx && ay == by
}

fn tracks_touch(t1: &TrackRec, t2: &TrackRec) -> bool {
    if t1.layer != t2.layer {
        return false;
    }
    pts_eq(t1.sx, t1.sy, t2.sx, t2.sy)
        || pts_eq(t1.sx, t1.sy, t2.ex, t2.ey)
        || pts_eq(t1.ex, t1.ey, t2.sx, t2.sy)
        || pts_eq(t1.ex, t1.ey, t2.ex, t2.ey)
}

fn track_touches_via(t: &TrackRec, v: &ViaRec) -> bool {
    pts_eq(t.sx, t.sy, v.x, v.y) || pts_eq(t.ex, t.ey, v.x, v.y)
}

fn point_touches_pad(px: f64, py: f64, p: &PadRec) -> bool {
    point_to_rotated_rect_distance(px, py, p.x, p.y, p.w, p.h, p.rotation) <= 1e-4
}

fn track_touches_pad(t: &TrackRec, p: &PadRec) -> bool {
    if t.layer != p.layer {
        return false;
    }
    point_touches_pad(t.sx, t.sy, p) || point_touches_pad(t.ex, t.ey, p)
}

fn via_touches_pad(v: &ViaRec, p: &PadRec) -> bool {
    point_touches_pad(v.x, v.y, p)
}

/// `_point_touches_item(pt, item, exclude_track=t)` for the dangling scan.
/// `item` is addressed by its index in `pads ++ tracks ++ vias`; `self_layer`
/// is the excluded track's layer (None semantics are only used for non-track
/// exclude cases, which never occur in this kernel).
#[allow(clippy::too_many_arguments)]
fn point_touches_item_at(
    px: f64,
    py: f64,
    item_id: usize,
    np: usize,
    nt: usize,
    pads: &[PadRec],
    tracks: &[TrackRec],
    vias: &[ViaRec],
    self_layer: i64,
) -> bool {
    if item_id < np {
        let p = &pads[item_id];
        if p.layer != self_layer {
            return false;
        }
        point_touches_pad(px, py, p)
    } else if item_id < np + nt {
        let t = &tracks[item_id - np];
        if t.layer != self_layer {
            return false;
        }
        pts_eq(px, py, t.sx, t.sy) || pts_eq(px, py, t.ex, t.ey)
    } else {
        let v = &vias[item_id - np - nt];
        pts_eq(px, py, v.x, v.y)
    }
}

/// `_get_item_location` — pads/vias carry `.center`, tracks carry `.start`.
fn get_item_location(
    item_id: usize,
    np: usize,
    nt: usize,
    pads: &[PadRec],
    tracks: &[TrackRec],
    vias: &[ViaRec],
) -> (f64, f64) {
    if item_id < np {
        (pads[item_id].x, pads[item_id].y)
    } else if item_id < np + nt {
        let t = &tracks[item_id - np];
        (t.sx, t.sy)
    } else {
        let v = &vias[item_id - np - nt];
        (v.x, v.y)
    }
}

/// The per-net connectivity algorithm. Returns `(vtype, x, y, description)`.
fn connectivity_validate_net(
    net_name: &str,
    pads: &[PadRec],
    tracks: &[TrackRec],
    vias: &[ViaRec],
) -> Vec<(String, f64, f64, String)> {
    let np = pads.len();
    let nt = tracks.len();
    let nv = vias.len();
    let n = np + nt + nv;
    let mut violations: Vec<(String, f64, f64, String)> = Vec::new();
    if n == 0 {
        return violations;
    }

    let mut uf = UnionFind::new(n);

    // 1. Track-Track
    for i in 0..nt {
        for j in (i + 1)..nt {
            if tracks_touch(&tracks[i], &tracks[j]) {
                uf.union(np + i, np + j);
            }
        }
    }
    // 2. Track-Via
    for (ti, t) in tracks.iter().enumerate() {
        for (vi, v) in vias.iter().enumerate() {
            if track_touches_via(t, v) {
                uf.union(np + ti, np + nt + vi);
            }
        }
    }
    // 3. Track-Pad
    for (ti, t) in tracks.iter().enumerate() {
        for (pi, p) in pads.iter().enumerate() {
            if track_touches_pad(t, p) {
                uf.union(np + ti, pi);
            }
        }
    }
    // 4. Via-Pad
    for (vi, v) in vias.iter().enumerate() {
        for (pi, p) in pads.iter().enumerate() {
            if via_touches_pad(v, p) {
                uf.union(np + nt + vi, pi);
            }
        }
    }
    // 5. Via-Via (stacking)
    for i in 0..nv {
        for j in (i + 1)..nv {
            if vias[i].x == vias[j].x && vias[i].y == vias[j].y {
                uf.union(np + nt + i, np + nt + j);
            }
        }
    }

    let comps = uf.get_components();
    let mut with_pads: Vec<(usize, Vec<usize>)> = Vec::new();
    let mut without_pads: Vec<(usize, Vec<usize>)> = Vec::new();
    for (root, members) in comps {
        let island_pads: Vec<usize> = members.iter().copied().filter(|&m| m < np).collect();
        if island_pads.is_empty() {
            without_pads.push((root, members));
        } else {
            with_pads.push((root, island_pads));
        }
    }

    // 1. Orphan islands (no pads).
    for (_root, members) in &without_pads {
        let (lx, ly) = get_item_location(members[0], np, nt, pads, tracks, vias);
        violations.push((
            "orphan_island".to_string(),
            lx,
            ly,
            format!("Isolated copper island for net {net_name} with no pads"),
        ));
    }

    // 2. Multiple pad components -> the non-primary ones are unconnected.
    if with_pads.len() > 1 {
        with_pads.sort_by(|a, b| {
            // Python `sorted(keys, key=(len, root), reverse=True)`.
            b.1.len()
                .cmp(&a.1.len())
                .then(b.0.cmp(&a.0))
        });
        for (_root, island_pads) in with_pads.iter().skip(1) {
            let p0 = &pads[island_pads[0]];
            violations.push((
                "unconnected_pad".to_string(),
                p0.x,
                p0.y,
                format!(
                    "Pad {} and {} others are not connected to the main group of net {}",
                    p0.id,
                    island_pads.len() - 1,
                    net_name
                ),
            ));
        }
    }

    // 3. Dangling tracks.
    for (ti, t) in tracks.iter().enumerate() {
        let start_connected = {
            let mut connected = false;
            for m in 0..n {
                if m == np + ti {
                    continue;
                }
                if point_touches_item_at(t.sx, t.sy, m, np, nt, pads, tracks, vias, t.layer) {
                    connected = true;
                    break;
                }
            }
            connected
        };
        let end_connected = {
            let mut connected = false;
            for m in 0..n {
                if m == np + ti {
                    continue;
                }
                if point_touches_item_at(t.ex, t.ey, m, np, nt, pads, tracks, vias, t.layer) {
                    connected = true;
                    break;
                }
            }
            connected
        };
        if !start_connected || !end_connected {
            let (lx, ly) = if !start_connected { t.start() } else { t.end() };
            violations.push((
                "dangling_track".to_string(),
                lx,
                ly,
                format!("Track segment in net {net_name} has a dangling endpoint"),
            ));
        }
    }

    violations
}

fn extract_pads(v: &Bound<'_, PyAny>) -> PyResult<Vec<PadRec>> {
    let mut out = Vec::new();
    for item in v.try_iter()? {
        let item = item?;
        let t = item.extract::<(f64, f64, i64, String, f64, f64, f64)>()?;
        out.push(PadRec {
            x: t.0,
            y: t.1,
            layer: t.2,
            id: t.3,
            w: t.4,
            h: t.5,
            rotation: t.6,
        });
    }
    Ok(out)
}

fn extract_tracks(v: &Bound<'_, PyAny>) -> PyResult<Vec<TrackRec>> {
    let mut out = Vec::new();
    for item in v.try_iter()? {
        let item = item?;
        let t = item.extract::<(f64, f64, f64, f64, i64)>()?;
        out.push(TrackRec {
            sx: t.0,
            sy: t.1,
            ex: t.2,
            ey: t.3,
            layer: t.4,
        });
    }
    Ok(out)
}

fn extract_vias(v: &Bound<'_, PyAny>) -> PyResult<Vec<ViaRec>> {
    let mut out = Vec::new();
    for item in v.try_iter()? {
        let item = item?;
        let t = item.extract::<(f64, f64)>()?;
        out.push(ViaRec { x: t.0, y: t.1 });
    }
    Ok(out)
}

/// Python-visible `connectivity_validate_net_py(net_name, pads, tracks,
/// vias)` — pads are `(x, y, layer, id, w, h, rotation)` 7-tuples, tracks
/// `(sx, sy, ex, ey, layer)` 5-tuples, vias `(x, y)` 2-tuples. Returns a
/// list of `(type, x, y, description)` 4-tuples in oracle violation order.
#[pyfunction]
pub fn connectivity_validate_net_py(
    net_name: &str,
    pads: &Bound<'_, PyAny>,
    tracks: &Bound<'_, PyAny>,
    vias: &Bound<'_, PyAny>,
) -> PyResult<Vec<(String, f64, f64, String)>> {
    guard(|| {
        let pads = extract_pads(pads)?;
        let tracks = extract_tracks(tracks)?;
        let vias = extract_vias(vias)?;
        Ok(connectivity_validate_net(net_name, &pads, &tracks, &vias))
    })
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(connectivity_validate_net_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pad(x: f64, y: f64, layer: i64, id: &str) -> PadRec {
        PadRec { x, y, layer, id: id.to_string(), w: 1.0, h: 1.0, rotation: 0.0 }
    }
    fn track(sx: f64, sy: f64, ex: f64, ey: f64, layer: i64) -> TrackRec {
        TrackRec { sx, sy, ex, ey, layer }
    }
    fn via(x: f64, y: f64) -> ViaRec {
        ViaRec { x, y }
    }

    #[test]
    fn clean_chain() {
        let pads = vec![pad(0.0, 0.0, 0, "P1"), pad(10.0, 0.0, 0, "P2")];
        let tracks = vec![track(0.0, 0.0, 10.0, 0.0, 0)];
        let vs = connectivity_validate_net("A", &pads, &tracks, &[]);
        assert!(vs.is_empty());
    }

    #[test]
    fn unconnected_pads() {
        let pads = vec![pad(0.0, 0.0, 0, "P1"), pad(10.0, 0.0, 0, "P2")];
        let vs = connectivity_validate_net("A", &pads, &[], &[]);
        assert_eq!(vs.len(), 1);
        assert_eq!(vs[0].0, "unconnected_pad");
        assert!(vs[0].3.contains("Pad P"));
    }

    #[test]
    fn orphan_and_dangling() {
        let tracks = vec![track(10.0, 10.0, 15.0, 10.0, 0)];
        let vs = connectivity_validate_net("A", &[], &tracks, &[]);
        let kinds: Vec<&str> = vs.iter().map(|v| v.0.as_str()).collect();
        assert_eq!(kinds, vec!["orphan_island", "dangling_track"]);
        assert_eq!((vs[0].1, vs[0].2), (10.0, 10.0));
    }

    #[test]
    fn via_bridges_layers() {
        let pads = vec![pad(0.0, 0.0, 0, "P1"), pad(5.0, 0.0, 1, "P2")];
        let tracks = vec![track(0.0, 0.0, 5.0, 0.0, 0)];
        let vias = vec![via(5.0, 0.0)];
        let vs = connectivity_validate_net("A", &pads, &tracks, &vias);
        assert!(vs.is_empty());
    }

    #[test]
    fn same_layer_requirement() {
        let pads = vec![pad(0.0, 0.0, 2, "P1")];
        let tracks = vec![track(0.0, 0.0, 8.0, 0.0, 0)];
        let vs = connectivity_validate_net("A", &pads, &tracks, &[]);
        assert!(vs.iter().any(|v| v.0 == "dangling_track"));
    }
}

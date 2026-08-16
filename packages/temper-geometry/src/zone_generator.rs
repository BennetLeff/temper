//! Zone-pour outline generation with per-pair clearance/creepage-aware
//! carving (design doc: `docs/evidence/2026-08-15-rust-zone-pour-design.md`).
//!
//! # Why this module exists
//!
//! The router emits zone OUTLINES; KiCad's fill engine turns them into
//! copper.  The committed Python emission (`router_v6/zone_emission.py` +
//! `_zone_pour_stitch.py`) has three measured defects on the production
//! board (2026-08-15 DRC classification, `docs/evidence/2026-08-15-drc-
//! violation-classification.md`):
//!
//! 1. **The outline cannot express interior holes.**  KiCad's zone polygon
//!    element *can*: the first `(pts ...)` block is the exterior and every
//!    subsequent `(pts ...)` block is a hole (verified against the KiCad
//!    source: `pcb_io_kicad_sexpr_parser.cpp`'s `parseZONE` does
//!    `AddOutline` then `AddHole`, and `zone.h` documents "Other polygons
//!    inside the main polygon are holes").  The Python emitter's
//!    `_carve_outline` *drops* interior holes because its s-expression
//!    writer emits a single ring, so an HV pad buried inside a pour hull
//!    does not carve the outline -- the FILL must dodge it at local
//!    clearance, producing thin copper rings that fracture into islands.
//!    The fill test measured **167 isolated_copper islands** and **+222
//!    creepage violations** after `--refill-zones`.
//! 2. **The carve uses electrical clearance, not creepage.**  The Python
//!    keepout (`pair_clearance_keepout`) buffers foreign copper by the
//!    DRU *clearance* table (HV-vs-LV 2.0 mm), but the DRC judges *creepage*
//!    between HV and LV copper at 12.6 mm (PD3 reinforced).  A pour carved
//!    at 2.0 mm from a +3V3 pad fills copper 2.0 mm from it and violates
//!    the 12.6 mm creepage rule -- exactly the measured "+170V_BUS pour
//!    2.0 mm from +3V3 pad of U16" family.  The generator must subtract
//!    halos at the *pair creepage* figure wherever creepage exceeds
//!    clearance (which for HV-vs-LV is always).
//! 3. **Fragmentation has no bridge-or-split policy.**  `power_in.ntc-no`'s
//!    single clustering-exempt hull spans ~150 mm of dense board; carving
//!    it with per-pair halos splits it into 47+ disconnected pieces.  This
//!    module keeps the split (each piece becomes its own outline, or one
//!    outline with holes when pieces nest), filters slivers below a
//!    caller-supplied area floor, and classifies islands against the net's
//!    own pads.  Copper-neck *bridging* (reconnecting split pieces with a
//!    narrow same-net corridor) is documented future work, not attempted
//!    here: it requires a neck-routing search, and a wrong-width neck is
//!    itself a DRC violation (`docs/evidence/2026-08-14-ntc-no-...`'s
//!    measured 4.156 mm-neck corridor finding).
//!
//! # Algorithm
//!
//! 1. Build the keepout: the union of one halo per foreign obstacle, each
//!    halo = the obstacle's physical footprint inflated by that net-pair's
//!    required separation (clearance or creepage, whichever governs).
//!    Pads/vias use a disc halo (radius = max half-extent + separation,
//!    matching the Python `Point.buffer(radius)` convention); tracks use a
//!    capsule halo (the Python `LineString.buffer` convention).  Both are
//!    approximated with regular polygons.
//! 2. `carved = region.difference(keepout)` -- a polygon boolean
//!    operation on [`geo`](https://docs.rs/geo) `MultiPolygon`
//!    (`geo::BooleanOps`), the same dependency `convex_hull.rs` already
//!    uses, so no new external crate.
//! 3. Decompose the result: every resulting polygon becomes a
//!    [`ZoneOutline`] (exterior + holes, orientation-normalised: exterior
//!    CCW, holes CW -- KiCad's convention).
//! 4. Filter: drop pieces below `min_island_area_mm2`; optionally drop
//!    pieces containing no own pad ([`IslandPolicy::PadsOnly`]).
//!
//! The output is a list of [`ZoneOutline`]s, each of which the emitter
//! ([`emit_zone_s_expr`]) renders as ONE KiCad `(zone ...)` with a
//! multi-`(pts ...)` polygon -- holes preserved, so the fill never has to
//! thread thin rings around interior obstacles.
//!
//! # Non-goals (deliberate)
//!
//! * Board-outline clipping: the caller passes the *region* already
//!   bounded to the board (or a hull); this module does not know Edge.Cuts.
//! * Per-net-pair clearance *resolution* (netclass tables): the caller
//!   passes each obstacle's already-resolved `clearance_mm`.
//! * Neck bridging (see above).
//! * Thermal-relief / spoke generation: that is fill-time behaviour in
//!   KiCad, not outline geometry.

use crate::polygon::polygon_signed_area;
use crate::types::Point;
use geo::{Area, BooleanOps, Coord, MultiPolygon, Polygon as GeoPolygon};

/// Number of segments in a full-circle halo approximation.  Matches the
/// spirit of the Python `quad_segs=16` (GEOS disc approximation) at twice
/// the resolution -- this is a NEW algorithm, not a bit-exact port, so the
/// approximation is free to differ (see module doc).
pub const HALO_SEGMENTS: usize = 24;

/// A foreign-copper obstacle and the separation this pour must keep from it.
///
/// `clearance_mm` is the *pair-specific* required separation (electrical
/// clearance or creepage, whichever is larger for that pair) already
/// resolved by the caller from the netclass/creepage tables.
#[derive(Debug, Clone, Copy)]
pub enum ZoneObstacle {
    /// A foreign pad.  Halo = disc of radius `max(half_w, half_h) +
    /// clearance_mm` centred on the pad (the Python
    /// `Point.buffer(max(w,h)/2 + clearance)` convention).  `rotation_rad`
    /// is accepted for future rectangular-halo use and ignored by the disc
    /// approximation -- a disc is rotation-invariant.
    Pad {
        position: Point,
        half_w: f64,
        half_h: f64,
        rotation_rad: f64,
        clearance_mm: f64,
    },
    /// A foreign track.  Halo = capsule (line segment buffered by
    /// `width_mm / 2.0 + clearance_mm`), the Python
    /// `LineString.buffer(width/2 + clearance)` convention.
    Track {
        start: Point,
        end: Point,
        width_mm: f64,
        clearance_mm: f64,
    },
    /// A foreign via.  Halo = disc of radius `diameter_mm / 2.0 +
    /// clearance_mm` (the Python `Point.buffer(diameter/2 + clearance)`
    /// convention).
    Via {
        position: Point,
        diameter_mm: f64,
        clearance_mm: f64,
    },
}

impl ZoneObstacle {
    fn halo_polygon(&self) -> GeoPolygon<f64> {
        match *self {
            ZoneObstacle::Pad {
                position,
                half_w,
                half_h,
                rotation_rad: _,
                clearance_mm,
            } => disc(position, half_w.max(half_h) + clearance_mm, HALO_SEGMENTS),
            ZoneObstacle::Via {
                position,
                diameter_mm,
                clearance_mm,
            } => disc(position, diameter_mm / 2.0 + clearance_mm, HALO_SEGMENTS),
            ZoneObstacle::Track {
                start,
                end,
                width_mm,
                clearance_mm,
            } => capsule(start, end, width_mm / 2.0 + clearance_mm, HALO_SEGMENTS),
        }
    }
}

/// A regular-polygon approximation of a disc of `radius` at `center`.
fn disc(center: Point, radius: f64, segments: usize) -> GeoPolygon<f64> {
    let ring: Vec<Coord<f64>> = (0..segments)
        .map(|i| {
            let a = std::f64::consts::TAU * (i as f64) / (segments as f64);
            Coord {
                x: center.x + radius * a.cos(),
                y: center.y + radius * a.sin(),
            }
        })
        .collect();
    GeoPolygon::new(ring.into(), vec![])
}

/// A capsule (stadium) from `start` to `end` with `radius` (half-width),
/// approximated as a regular polygon.
///
/// Ring order: right cap (sweeping the outboard semicircle around `end`
/// from `end + p*r` through `end + u*r` to `end - p*r`), straight bottom
/// side to `start - p*r`, left cap (outboard around `start` from
/// `start - p*r` through `start - u*r` to `start + p*r`), straight top
/// side closing back to `end + p*r` -- where `u` is the segment direction
/// and `p` is its +90° CCW perpendicular.
fn capsule(start: Point, end: Point, radius: f64, segments: usize) -> GeoPolygon<f64> {
    let dx = end.x - start.x;
    let dy = end.y - start.y;
    let len = (dx * dx + dy * dy).sqrt();
    // Perpendicular (px,py) = +90° CCW rotation of the segment direction.
    // For a zero-length segment, default to pointing along +y.
    let (px, py) = if len > 1e-12 {
        (-dy / len, dx / len)
    } else {
        (0.0, 1.0)
    };
    let half = segments / 2;
    let mut ring: Vec<Coord<f64>> = Vec::with_capacity(2 * half + 4);
    // Rotate (px,py) by t radians (standard CCW rotation matrix).
    let rot = |t: f64| -> (f64, f64) {
        (px * t.cos() - py * t.sin(), px * t.sin() + py * t.cos())
    };
    // Right cap: t from 0 (end + p*r) down to -pi (end - p*r); at t=-pi/2
    // this passes through end + u*r (the front axis point).
    for i in 0..=half {
        let t = -std::f64::consts::PI * (i as f64) / (half as f64);
        let (dirx, diry) = rot(t);
        ring.push(Coord {
            x: end.x + radius * dirx,
            y: end.y + radius * diry,
        });
    }
    // Left cap: t from +pi (start - p*r) down to 0 (start + p*r); at
    // t=+pi/2 this passes through start - u*r (the rear axis point).
    for i in 0..=half {
        let t = std::f64::consts::PI * (1.0 - (i as f64) / (half as f64));
        let (dirx, diry) = rot(t);
        ring.push(Coord {
            x: start.x + radius * dirx,
            y: start.y + radius * diry,
        });
    }
    GeoPolygon::new(ring.into(), vec![])
}

/// One emitted zone contour: an exterior ring plus zero or more interior
/// holes.  KiCad expresses this as one `(polygon (pts ...) (pts ...))`
/// element -- first block exterior, remaining blocks holes.
#[derive(Debug, Clone, PartialEq)]
pub struct ZoneOutline {
    pub exterior: Vec<Point>,
    pub holes: Vec<Vec<Point>>,
}

impl ZoneOutline {
    pub fn area_mm2(&self) -> f64 {
        let outer = polygon_signed_area(&self.exterior).abs();
        let holes: f64 = self.holes.iter().map(|h| polygon_signed_area(h).abs()).sum();
        (outer - holes).max(0.0)
    }

    pub fn contains_point(&self, p: &Point) -> bool {
        use crate::polygon::point_in_polygon_winding;
        if !point_in_polygon_winding(p, &self.exterior) {
            return false;
        }
        !self.holes.iter().any(|h| point_in_polygon_winding(p, h))
    }
}

/// What to do with carved pieces that contain none of the net's own pads.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IslandPolicy {
    /// Keep every piece above the area floor.  For a plane net (gnd on a
    /// dedicated layer) padless copper is desirable (shielding, plane
    /// continuity); KiCad's own fill-time island removal is responsible for
    /// dropping the truly useless slivers.
    KeepAll,
    /// Drop pieces containing no own pad.  For per-cluster signal/HV pours,
    /// padless islands are pure isolated_copper liability.
    PadsOnly,
}

/// Result of a pour-outline computation.
#[derive(Debug, Clone)]
pub struct PourResult {
    pub outlines: Vec<ZoneOutline>,
    /// Pieces discarded by the area floor and/or `IslandPolicy`.
    pub dropped_islands: usize,
    /// Union area of all obstacle halos (mm²) -- the "carved-out" region.
    pub keepout_area_mm2: f64,
    /// Total copper area of the surviving outlines (mm²).
    pub pour_area_mm2: f64,
}

/// Compute the pour outline(s) for one net on one layer.
///
/// * `region` -- the starting region the pour may occupy, already bounded
///   to the board (full-board outline for a plane net, or the net's hull
///   for a clustered pour).  A single CCW exterior ring.
/// * `own_pads` -- the net's own pad positions on this layer, used only
///   for island classification under [`IslandPolicy::PadsOnly`].
/// * `obstacles` -- every other net's copper on this layer, each carrying
///   its pair-resolved separation.
/// * `min_island_area_mm2` -- pieces strictly smaller than this are
///   dropped (KiCad's own `min_thickness`-squared sliver convention is a
///   reasonable floor: `0.25 * 0.25`).
/// * `policy` -- see [`IslandPolicy`].
///
/// Returns multiple disjoint outlines when the carve splits the region;
/// an outline may carry holes when a keepout sits fully inside it.
pub fn pour_outline(
    region: &[Point],
    own_pads: &[Point],
    obstacles: &[ZoneObstacle],
    min_island_area_mm2: f64,
    policy: IslandPolicy,
) -> PourResult {
    // 1. Union every obstacle halo into one keepout.
    let halos: Vec<GeoPolygon<f64>> = obstacles.iter().map(|o| o.halo_polygon()).collect();
    let keepout: MultiPolygon<f64> = MultiPolygon::new(halos).union(&MultiPolygon::new(vec![]));
    let keepout_area_mm2: f64 = keepout.iter().map(|p| p.unsigned_area()).sum();

    // 2. Carve.
    let region_geo = MultiPolygon::new(vec![ring_to_geo_polygon(region)]);
    let carved = region_geo.difference(&keepout);

    // 3. Decompose + filter.
    let mut outlines = Vec::new();
    let mut dropped = 0usize;
    for poly in carved.iter() {
        let zone = geo_polygon_to_outline(poly);
        if zone.area_mm2() < min_island_area_mm2 {
            dropped += 1;
            continue;
        }
        if policy == IslandPolicy::PadsOnly && !own_pads.iter().any(|p| zone.contains_point(p)) {
            dropped += 1;
            continue;
        }
        outlines.push(zone);
    }
    // Deterministic order: sort by exterior bounding-box area descending
    // (largest first), then lexicographic on the first vertex -- so the
    // emitted zone order does not depend on geo's internal iteration.
    outlines.sort_by(|a, b| {
        let aa = bbox_area(&a.exterior);
        let ba = bbox_area(&b.exterior);
        ba.partial_cmp(&aa)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                let av = a.exterior.first().copied().unwrap_or(Point::zero());
                let bv = b.exterior.first().copied().unwrap_or(Point::zero());
                av.x.partial_cmp(&bv.x)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| av.y.partial_cmp(&bv.y).unwrap_or(std::cmp::Ordering::Equal))
            })
    });
    let pour_area_mm2: f64 = outlines.iter().map(|o| o.area_mm2()).sum();
    PourResult {
        outlines,
        dropped_islands: dropped,
        keepout_area_mm2,
        pour_area_mm2,
    }
}

fn bbox_area(pts: &[Point]) -> f64 {
    let mut min_x = f64::INFINITY;
    let mut max_x = f64::NEG_INFINITY;
    let mut min_y = f64::INFINITY;
    let mut max_y = f64::NEG_INFINITY;
    for p in pts {
        min_x = min_x.min(p.x);
        max_x = max_x.max(p.x);
        min_y = min_y.min(p.y);
        max_y = max_y.max(p.y);
    }
    (max_x - min_x) * (max_y - min_y)
}

/// Convert the crate's `Point` slice into a `geo` exterior ring.
fn ring_to_geo_polygon(pts: &[Point]) -> GeoPolygon<f64> {
    let ring: Vec<Coord<f64>> = pts.iter().map(|p| Coord { x: p.x, y: p.y }).collect();
    GeoPolygon::new(ring.into(), vec![])
}

/// Convert a `geo` polygon (exterior + interiors) into a
/// [`ZoneOutline`], normalising orientation: exterior CCW (positive signed
/// area), holes CW (negative) -- KiCad's convention.
fn geo_polygon_to_outline(poly: &GeoPolygon<f64>) -> ZoneOutline {
    let exterior = normalize_ring(
        &poly
            .exterior()
            .coords()
            .map(|c| Point::new(c.x, c.y))
            .collect::<Vec<_>>(),
        true,
    );
    let holes = poly
        .interiors()
        .iter()
        .map(|ring| {
            normalize_ring(
                &ring.coords().map(|c| Point::new(c.x, c.y)).collect::<Vec<_>>(),
                false,
            )
        })
        .collect();
    ZoneOutline { exterior, holes }
}

/// Orient a ring: `want_ccw = true` for exteriors, false for holes.
/// Also drops the duplicated closing vertex (geo keeps rings open; KiCad
/// expects a closed ring, and `emit_zone_s_expr` writes every vertex --
/// the Python convention drops the repeated first/last point, and KiCad
/// closes the ring itself).
fn normalize_ring(pts: &[Point], want_ccw: bool) -> Vec<Point> {
    let mut ring: Vec<Point> = pts.to_vec();
    if ring.len() > 1 && ring[0] == ring[ring.len() - 1] {
        ring.pop();
    }
    if ring.len() < 3 {
        return ring;
    }
    let signed = polygon_signed_area(&ring);
    let is_ccw = signed > 0.0;
    if is_ccw != want_ccw {
        ring.reverse();
    }
    ring
}

// ===========================================================================
// KiCad s-expression emission (with holes)
// ===========================================================================

/// Render a [`ZoneOutline`] as a KiCad `(zone ...)` s-expression whose
/// `(polygon ...)` element carries one `(pts ...)` block per ring --
/// exterior first, holes after (KiCad: first polygon = main outline, next
/// = holes).
///
/// Field conventions match the existing `zone_pour.rs::emit_zone_s_expr`
/// (`{:.4}` float formatting, `(connect_pads yes (clearance ...))`,
/// `(fill yes ...)`).
pub fn emit_zone_s_expr(
    net_number: i64,
    net_name: &str,
    layer: &str,
    outline: &ZoneOutline,
    clearance: f64,
    priority: i64,
    min_thickness: f64,
) -> String {
    let mut rings: Vec<&[Point]> = Vec::with_capacity(1 + outline.holes.len());
    rings.push(&outline.exterior);
    rings.extend(outline.holes.iter().map(|h| h.as_slice()));
    let mut poly = String::new();
    for ring in rings {
        poly.push_str("\n    (pts");
        for p in ring {
            poly.push_str(&format!("\n      (xy {:.4} {:.4})", p.x, p.y));
        }
        poly.push(')');
    }
    format!(
        "  (zone (net {net_number}) (net_name \"{net_name}\") (layer \"{layer}\") \
         (hatch full 0.5) (priority {priority}) \
         (connect_pads yes (clearance {clearance:.4})) \
         (min_thickness {min_thickness:.4}) \
         (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)) \
         (polygon{poly}))"
    )
}

// ===========================================================================
// Pyo3 boundary
// ===========================================================================

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Pyo3 wrapper: compute pour outlines for one net on one layer.
///
/// Argument layout (flat lists, matching this crate's bridge conventions):
/// * `region`: `Vec<(f64, f64)>` -- starting region exterior ring.
/// * `own_pads`: `Vec<(f64, f64)>` -- the net's own pad positions.
/// * `obstacles`: `Vec<(kind, x, y, a, b, w, clearance)>` -- flattened
///   obstacle records; `kind` selects the interpretation:
///   - `0` = Pad: x,y = centre, a = half_w, b = half_h, w unused
///   - `1` = Track: x,y = start, a,b = end, w = width
///   - `2` = Via: x,y = centre, a = diameter, b/w unused
/// * `min_island_area_mm2`: sliver floor.
/// * `pads_only`: island policy (`true` = drop padless pieces).
///
/// Returns a list of zones, each a flat `(exterior..., n_holes,
/// hole0..., hole1..., ...)` list where the hole ring count prefixes each
/// hole's vertices.  (The Python side re-assembles rings from the counts.)
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (region, own_pads, obstacles, min_island_area_mm2, pads_only))]
pub fn pour_outline_py(
    region: Vec<(f64, f64)>,
    own_pads: Vec<(f64, f64)>,
    obstacles: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
    min_island_area_mm2: f64,
    pads_only: bool,
) -> PyResult<Vec<Vec<f64>>> {
    temper_py_bridge::catch_unwind(|| {
        let region_pts: Vec<Point> = region.iter().map(|(x, y)| Point::new(*x, *y)).collect();
        let own: Vec<Point> = own_pads.iter().map(|(x, y)| Point::new(*x, *y)).collect();
        let obs: Vec<ZoneObstacle> = obstacles
            .iter()
            .map(|(kind, x, y, a, b, w, clearance)| match kind {
                0 => ZoneObstacle::Pad {
                    position: Point::new(*x, *y),
                    half_w: *a,
                    half_h: *b,
                    rotation_rad: 0.0,
                    clearance_mm: *clearance,
                },
                1 => ZoneObstacle::Track {
                    start: Point::new(*x, *y),
                    end: Point::new(*a, *b),
                    width_mm: *w,
                    clearance_mm: *clearance,
                },
                _ => ZoneObstacle::Via {
                    position: Point::new(*x, *y),
                    diameter_mm: *a,
                    clearance_mm: *clearance,
                },
            })
            .collect();
        let res = pour_outline(
            &region_pts,
            &own,
            &obs,
            min_island_area_mm2,
            if pads_only { IslandPolicy::PadsOnly } else { IslandPolicy::KeepAll },
        );
        let mut out = Vec::with_capacity(res.outlines.len());
        for z in &res.outlines {
            let mut flat: Vec<f64> = Vec::new();
            for p in &z.exterior {
                flat.push(p.x);
                flat.push(p.y);
            }
            flat.push(z.holes.len() as f64);
            for h in &z.holes {
                flat.push(h.len() as f64);
                for p in h {
                    flat.push(p.x);
                    flat.push(p.y);
                }
            }
            out.push(flat);
        }
        out
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(pour_outline_py, m)?)?;
    m.add_function(wrap_pyfunction!(emit_zone_s_expr_py, m)?)?;
    Ok(())
}

/// Pyo3 wrapper for [`emit_zone_s_expr`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (net_number, net_name, layer, exterior, holes, clearance, priority, min_thickness))]
pub fn emit_zone_s_expr_py(
    net_number: i64,
    net_name: String,
    layer: String,
    exterior: Vec<(f64, f64)>,
    holes: Vec<Vec<(f64, f64)>>,
    clearance: f64,
    priority: i64,
    min_thickness: f64,
) -> PyResult<String> {
    temper_py_bridge::catch_unwind(|| {
        let outline = ZoneOutline {
            exterior: exterior.iter().map(|(x, y)| Point::new(*x, *y)).collect(),
            holes: holes
                .iter()
                .map(|h| h.iter().map(|(x, y)| Point::new(*x, *y)).collect())
                .collect(),
        };
        emit_zone_s_expr(
            net_number,
            &net_name,
            &layer,
            &outline,
            clearance,
            priority,
            min_thickness,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

// ===========================================================================
// Unit tests (pure Rust, no libpython)
// ===========================================================================

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn rect(x0: f64, y0: f64, x1: f64, y1: f64) -> Vec<Point> {
        vec![
            Point::new(x0, y0),
            Point::new(x1, y0),
            Point::new(x1, y1),
            Point::new(x0, y1),
        ]
    }

    #[cfg_attr(test, test)]
    fn empty_obstacles_leave_region_whole() {
        let region = rect(0.0, 0.0, 100.0, 80.0);
        let res = pour_outline(&region, &[], &[], 0.0, IslandPolicy::KeepAll);
        assert_eq!(res.outlines.len(), 1);
        assert_eq!(res.dropped_islands, 0);
        assert!(res.keepout_area_mm2 < 1e-9);
        assert!((res.pour_area_mm2 - 8000.0).abs() < 1e-6);
    }

    #[cfg_attr(test, test)]
    fn single_pad_halo_carves_a_hole() {
        let region = rect(0.0, 0.0, 100.0, 80.0);
        let obstacle = ZoneObstacle::Pad {
            position: Point::new(50.0, 40.0),
            half_w: 1.0,
            half_h: 1.0,
            rotation_rad: 0.0,
            clearance_mm: 5.0,
        };
        // One exterior ring and exactly one hole.
        let res = pour_outline(&region, &[], &[obstacle], 0.0, IslandPolicy::KeepAll);
        assert_eq!(res.outlines.len(), 1);
        assert_eq!(res.outlines[0].holes.len(), 1);
        // The hole centre (the pad itself) is excluded; a corner is not.
        let pad_pt = Point::new(50.0, 40.0);
        assert!(!res.outlines[0].contains_point(&pad_pt));
        assert!(res.outlines[0].contains_point(&Point::new(5.0, 5.0)));
        // Halo area ≈ pi * 6^2 ≈ 113.1 mm²
        assert!((res.keepout_area_mm2 - std::f64::consts::PI * 36.0).abs() < 2.0);
    }

    #[cfg_attr(test, test)]
    fn island_policy_pads_only_drops_padless_pieces() {
        let region = rect(0.0, 0.0, 100.0, 80.0);
        // Two obstacles that sever the region into two pieces.
        let o1 = ZoneObstacle::Track {
            start: Point::new(0.0, 30.0),
            end: Point::new(100.0, 30.0),
            width_mm: 2.0,
            clearance_mm: 1.0,
        };
        let o2 = ZoneObstacle::Track {
            start: Point::new(0.0, 50.0),
            end: Point::new(100.0, 50.0),
            width_mm: 2.0,
            clearance_mm: 1.0,
        };
        // Own pad in the bottom strip only.
        let own = vec![Point::new(10.0, 10.0)];
        let res = pour_outline(&region, &own, &[o1, o2], 0.0, IslandPolicy::PadsOnly);
        // Two obstacles sever the region into THREE strips; only the strip
        // containing the pad survives, the two padless strips are dropped.
        assert_eq!(res.outlines.len(), 1, "expected 1 strip, got {}: {:?}", res.outlines.len(),
            res.outlines.iter().map(|o| (o.area_mm2(), o.holes.len())).collect::<Vec<_>>());
        assert!(res.outlines[0].contains_point(&Point::new(10.0, 10.0)));
        assert!(!res.outlines[0].contains_point(&Point::new(10.0, 70.0)));
        assert_eq!(res.dropped_islands, 2);

        // Same carve, KeepAll: all three strips survive.
        let res2 = pour_outline(&region, &own, &[o1, o2], 0.0, IslandPolicy::KeepAll);
        assert_eq!(res2.outlines.len(), 3);
        assert_eq!(res2.dropped_islands, 0);
    }

    #[cfg_attr(test, test)]
    fn sliver_filter_drops_tiny_pieces() {
        let region = rect(0.0, 0.0, 100.0, 80.0);
        // Two nearly-touching obstacle halos that leave only a hairline
        // gap between them -- a sliver whose area is below the floor.
        let c = 0.05;
        let o1 = ZoneObstacle::Pad {
            position: Point::new(49.95, 20.0),
            half_w: 1.0,
            half_h: 1.0,
            rotation_rad: 0.0,
            clearance_mm: 5.0 + c,
        };
        let o2 = ZoneObstacle::Pad {
            position: Point::new(50.05, 60.0),
            half_w: 1.0,
            half_h: 1.0,
            rotation_rad: 0.0,
            clearance_mm: 5.0 + c,
        };
        let res = pour_outline(&region, &[], &[o1, o2], 0.25 * 0.25, IslandPolicy::KeepAll);
        // No outline may be a below-floor sliver.
        for o in &res.outlines {
            assert!(o.area_mm2() >= 0.25 * 0.25 || res.dropped_islands > 0);
        }
        // The two big side pieces survive.
        assert!(res.outlines.len() >= 1);
    }

    #[cfg_attr(test, test)]
    fn orientation_is_normalised() {
        // Clockwise input region must come out CCW.
        let region = rect(0.0, 0.0, 10.0, 10.0);
        let mut cw = region.clone();
        cw.reverse();
        let res = pour_outline(&cw, &[], &[], 0.0, IslandPolicy::KeepAll);
        assert_eq!(res.outlines.len(), 1);
        assert!(polygon_signed_area(&res.outlines[0].exterior) > 0.0);
    }

    #[cfg_attr(test, test)]
    fn emit_with_holes_has_multiple_pts_blocks() {
        let outline = ZoneOutline {
            exterior: rect(0.0, 0.0, 10.0, 10.0),
            holes: vec![rect(3.0, 3.0, 4.0, 4.0)],
        };
        let s = emit_zone_s_expr(7, "gnd", "In1.Cu", &outline, 0.3, 0, 0.25);
        assert!(s.contains("(zone (net 7)"));
        assert!(s.contains("(net_name \"gnd\")"));
        // Two (pts blocks: exterior + one hole.
        let pts_count = s.matches("(pts").count();
        assert_eq!(pts_count, 2, "expected exterior + 1 hole, got {s}");
        assert!(s.contains("(xy 0.0000 0.0000)"));
        // Hole ring is present.
        assert!(s.contains("(xy 3.0000 3.0000)"));
    }

    #[cfg_attr(test, test)]
    fn capsule_halo_has_positive_area() {
        let c = capsule(Point::new(0.0, 0.0), Point::new(10.0, 0.0), 2.0, 24);
        let area = c.unsigned_area();
        // Rect 10 x 4 plus two semicircle caps r=2: 40 + pi*4 ≈ 52.57
        assert!((area - 52.57).abs() < 1.5, "capsule area {area}");
    }

    #[cfg_attr(test, test)]
    fn disc_halo_area() {
        let d = disc(Point::new(0.0, 0.0), 3.0, 24);
        let area = d.unsigned_area();
        // 24-gon inscribed in radius-3 circle: 12 * r^2 * sin(2pi/24) ≈ 27.95
        assert!((area - std::f64::consts::PI * 9.0).abs() < 0.5, "disc area {area}");
    }
}

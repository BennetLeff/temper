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
//! 1. **The outline cannot express interior holes.**  KiCad's zone
//!    serialization *can*: the writer emits one `(polygon (pts ...))`
//!    element per ring (verified against `pcb_io_kicad_sexpr.cpp`'s
//!    `format(const ZONE*)`), and `parseZONE` documents "The first polygon
//!    is the main outline. Others are holes inside the main outline"
//!    (`ZONE::AddPolygon`).  The Python emitter's `_carve_outline` *drops*
//!    interior holes because its s-expression writer emits a single ring,
//!    so an HV pad buried inside a pour hull does not carve the outline --
//!    the FILL must dodge it at local clearance, producing thin copper
//!    rings that fracture into islands.  The fill test measured
//!    **167 isolated_copper islands** and **+222 creepage violations**
//!    after `--refill-zones`.
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
//! ([`emit_zone_s_expr`]) renders as ONE KiCad `(zone ...)` carrying one
//! `(polygon (pts ...))` element per ring -- exterior first, then one
//! element per hole -- so holes are preserved and the fill never has to
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

/// Radius inflation factor for polygonal halo approximations.
///
/// A regular n-gon built from vertices at radius R is INSCRIBED: its edge
/// midpoints (the points of closest approach to the centre) sit at
/// `R * cos(pi/n)`, not at R.  The carve distance is the edge-to-edge gap,
/// so an un-inflated halo undercuts the required separation by
/// `R * (1 - cos(pi/n))` -- for a 12.6mm creepage halo at 24 segments that
/// is 0.11mm, and the DRC measures it (12.49mm actual vs 12.60mm required,
/// measured on the production board 2026-08-16).  Inflating the radius by
/// `1/cos(pi/n)` puts the polygon's EDGES at the true required distance
/// (the vertices then sit slightly further out -- conservative, never a
/// violation).
pub fn halo_radius_inflate() -> f64 {
    1.0 / (std::f64::consts::PI / HALO_SEGMENTS as f64).cos()
}

/// Coordinate snap grid (mm) applied to every input ring before the
/// polygon-boolean carve.
///
/// Why: `geo::BooleanOps` (0.28) is a sweep-line implementation that
/// PANICS ("unable to compare active segments!" /
/// "segment not found in active-vec-set") when hundreds of overlapping
/// halos produce nearly-coincident collinear edges with floating-point
/// noise (measured on the production board: every zone-eligible net
/// panicked with 500+ obstacles; georust/geo#1174 is the same crash,
/// fixed upstream only in 0.29 via a different engine).  Snapping every
/// ring vertex to this grid turns near-coincident points into exactly
/// coincident points so the sweep's segment ordering is total.  0.001mm
/// is 1/12500 of the board's smallest DRC-relevant separation (12.6mm
/// creepage) -- far below any meaningful dimension, and KiCad itself
/// writes 4-decimal coordinates (0.0001mm resolution), so the snap is
/// at 10x KiCad's own coordinate resolution.
pub const SNAP_GRID_MM: f64 = 0.001;

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
    /// The obstacle's clearance halo as a geo polygon for the keepout union.
    ///
    /// ADOPTED (2026-08-16) onto
    /// [`ClearanceHalo`](crate::clearance_halo::ClearanceHalo): every halo is
    /// now built through the typed constructor, whose conservative-superset
    /// guarantee is structural — the polygon is circumscribed (contains the
    /// true shape, edges at the true required distance) and the containment
    /// is verified against boundary witnesses before the value can exist.
    /// The polygons produced are geometrically identical to the previous
    /// hand-rolled `disc`/`capsule` construction (same circumscribed
    /// vertices at `r / cos(π/24)`), so the carve geometry is unchanged; the
    /// half-diagonal pad convention and the `1/cos(π/24)` inflation that the
    /// 2026-08-16 DRC findings (`9c06de200`) established are now enforced by
    /// the type rather than by one-line fixes.
    fn halo_polygon(&self) -> GeoPolygon<f64> {
        use crate::clearance_halo::ClearanceHalo;
        let halo: ClearanceHalo = match *self {
            ZoneObstacle::Pad {
                position,
                half_w,
                half_h,
                rotation_rad,
                clearance_mm,
            } => {
                // HALF-DIAGONAL, not max(half_w, half_h): the furthest
                // point on a RECTANGULAR pad from its own centre is a
                // corner, not an edge midpoint.  A disc of radius
                // max(w,h)/2 under-covers a rect pad's corners by
                // hypot(w/2,h/2) - max(w,h)/2 -- measured 0.30mm for the
                // 3.0x2.0mm PTH relay pad and a 12.6mm creepage halo
                // (DRC actual 12.48 vs 12.60 required, 2026-08-16).  The
                // same half-diagonal convention is already documented in
                // router_v6/_ground_plane.py's _collect_hv_copper_geometry.
                // (rotation_rad is unused by the disc -- a disc is
                // rotation-invariant, so the corner reach is the same in
                // every orientation.)
                ClearanceHalo::from_rect_pad_with_segments(
                    geo::Point::new(position.x, position.y),
                    2.0 * half_w,
                    2.0 * half_h,
                    0.0,
                    rotation_rad,
                    clearance_mm,
                    HALO_SEGMENTS,
                )
            }
            ZoneObstacle::Via {
                position,
                diameter_mm,
                clearance_mm,
            } => ClearanceHalo::from_circular_pad_with_segments(
                geo::Point::new(position.x, position.y),
                diameter_mm / 2.0,
                clearance_mm,
                HALO_SEGMENTS,
            ),
            ZoneObstacle::Track {
                start,
                end,
                width_mm,
                clearance_mm,
            } => ClearanceHalo::from_track_with_segments(
                geo::Point::new(start.x, start.y),
                geo::Point::new(end.x, end.y),
                width_mm,
                clearance_mm,
                HALO_SEGMENTS,
            ),
        };
        let ring: Vec<Coord<f64>> = halo
            .polygon()
            .exterior()
            .coords()
            .map(|c| Coord { x: c.x, y: c.y })
            .collect();
        GeoPolygon::new(ring.into(), vec![])
    }
}

/// A regular-polygon approximation of a disc of `radius` at `center`.
///
/// Retained as the REFERENCE construction the halo-area tests compare the
/// [`ClearanceHalo`](crate::clearance_halo::ClearanceHalo) adoption against
/// (bit-identical polygons — the adoption changed the guarantee layer, not
/// the shape); production halo construction now goes through `ClearanceHalo`.
#[cfg(any(test, feature = "wasm-registry"))]
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
///
/// Retained as the REFERENCE construction the halo-area tests compare the
/// [`ClearanceHalo`](crate::clearance_halo::ClearanceHalo) adoption against
/// (bit-identical polygons — the adoption changed the guarantee layer, not
/// the shape); production halo construction now goes through `ClearanceHalo`.
#[cfg(any(test, feature = "wasm-registry"))]
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
/// holes.  KiCad expresses this as one `(zone ...)` carrying one
/// `(polygon (pts ...))` element per ring -- first element exterior,
/// remaining elements holes (the format `pcb_io_kicad_sexpr.cpp` writes
/// and `parseZONE` reads).
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
///   **These must be WORLD positions** (component rotation + side mirror
///   applied) -- the zone generator computes hulls/carves from them
///   directly and has no component context to fix them up. The 2026-08-15
///   zone-hull incident (only 21/59 real pads inside their same-layer
///   hulls) and the zone-stitch swap shorts were both caused by callers
///   feeding naive `comp_pos + pin_pos` coordinates with the rotation
///   omitted. The sanctioned way to produce them is
///   [`crate::world_position::WorldPosition::from_component_pin`] (the
///   only constructor of a world position -- there is no raw-coordinate
///   path into the type).
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
    // 1. Union every obstacle halo into one keepout.  Every ring is
    // snapped to SNAP_GRID_MM and deduped of repeated consecutive points
    // FIRST -- geo 0.28's sweep-line BooleanOps panics on floating-point
    // near-coincident collinear edges (measured on the production board
    // with 500+ overlapping halos; see SNAP_GRID_MM's doc comment).
    let snap = |pts: &[Point]| -> Vec<Point> {
        let mut out: Vec<Point> = Vec::with_capacity(pts.len());
        for p in pts {
            let q = Point::new(
                (p.x / SNAP_GRID_MM).round() * SNAP_GRID_MM,
                (p.y / SNAP_GRID_MM).round() * SNAP_GRID_MM,
            );
            if out.last() != Some(&q) {
                out.push(q);
            }
        }
        // Close the ring: if the snapped ring's first/last differ, append
        // the first point so geo sees a closed polygon.  (geo's polygon
        // ring handling tolerates an open ring, but a closed one is the
        // unambiguous form.)
        if out.len() > 1 && out[0] != out[out.len() - 1] {
            out.push(out[0]);
        }
        out
    };
    let halos: Vec<GeoPolygon<f64>> = obstacles
        .iter()
        .map(|o| {
            let poly = o.halo_polygon();
            let snapped = snap(
                &poly
                    .exterior()
                    .coords()
                    .map(|c| Point::new(c.x, c.y))
                    .collect::<Vec<_>>(),
            );
            let ring: Vec<Coord<f64>> = snapped.iter().map(|p| Coord { x: p.x, y: p.y }).collect();
            GeoPolygon::new(ring.into(), vec![])
        })
        .collect();
    // Union incrementally (fold), not in one giant MultiPolygon::union:
    // geo 0.28's sweep-line BooleanOps panics
    // ("unable to compare active segments!" / "segment not found in
    // active-vec-set") when hundreds of overlapping halos are unioned at
    // once (measured on the production board: every zone-eligible net
    // panicked with 500+ obstacles).  A fold keeps each sweep's active-set
    // small enough to stay total.  The result is order-independent (union
    // is commutative) up to floating-point snap effects, and the final
    // polygon set is the same; deterministic per run.
    let mut keepout: MultiPolygon<f64> = MultiPolygon::new(vec![]);
    for halo in &halos {
        keepout = keepout.union(&MultiPolygon::new(vec![halo.clone()]));
    }
    let keepout_area_mm2: f64 = keepout.iter().map(|p| p.unsigned_area()).sum();

    // 2. Carve.  The region ring is snapped/deduped the same way so the
    // difference's sweep sees the same total ordering.
    let region_snapped = snap(region);
    let region_geo = MultiPolygon::new(vec![ring_to_geo_polygon(&region_snapped)]);
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
/// outline carries one `(polygon (pts ...))` element per ring -- exterior
/// first, then one element per hole.
///
/// This is KiCad's own serialization (verified against
/// `pcb_io_kicad_sexpr.cpp::format(const ZONE*)`): the writer emits a
/// `(polygon ...)` element per `SHAPE_LINE_CHAIN` of the outline poly-set,
/// and `pcb_io_kicad_sexpr_parser.cpp::parseZONE` documents "The first
/// polygon is the main outline. Others are holes inside the main outline"
/// (`ZONE::AddPolygon`).  A single `(polygon ...)` element with multiple
/// `(pts ...)` blocks is NOT the format -- it fails to parse (measured
/// against kicad-cli 10.0.5, 2026-08-15).
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
    let mut poly = String::new();
    for ring in std::iter::once(&outline.exterior).chain(outline.holes.iter()) {
        poly.push_str("\n    (polygon\n      (pts");
        for p in ring {
            poly.push_str(&format!("\n        (xy {:.4} {:.4})", p.x, p.y));
        }
        poly.push_str("))");
    }
    format!(
        "  (zone (net {net_number}) (net_name \"{net_name}\") (layer \"{layer}\") \
         (hatch full 0.5) (priority {priority}) \
         (connect_pads yes (clearance {clearance:.4})) \
         (min_thickness {min_thickness:.4}) \
         (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)){poly})"
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
/// * `own_pads`: `Vec<(f64, f64)>` -- the net's own pad positions. **World
///   positions** (component rotation + side mirror applied); the generator
///   has no component context to fix them up. Produce them via
///   `temper_geometry.world_position_from_component_pin_py` /
///   `WorldPosition::from_component_pin` -- never a bare
///   `comp_pos + pin_pos` sum (that omission caused the 2026-08-15
///   zone-hull and zone-stitch swap-short incidents).
/// * `obstacles`: `Vec<(kind, x, y, a, b, w, clearance)>` -- flattened
///   obstacle records; `kind` selects the interpretation:
///   - `0` = Pad: x,y = centre, a = half_w, b = half_h, w unused
///   - `1` = Track: x,y = start, a,b = end, w = width
///   - `2` = Via: x,y = centre, a = diameter, b/w unused
/// * `min_island_area_mm2`: sliver floor.
/// * `pads_only`: island policy (`true` = drop padless pieces).
///
/// Returns a list of zones; each zone is a list of rings, ring 0 the
/// exterior and rings 1.. the holes (each ring an open `Vec<(x, y)>`).
/// The ring-per-zone structure is unambiguous by construction (an early
/// prototype flattened rings with only the HOLE lengths prefixed, which
/// left the Python side unable to locate the exterior's end -- this
/// structured form is the production contract).
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (region, own_pads, obstacles, min_island_area_mm2, pads_only))]
// `clippy::type_complexity`: the return type is the pyo3 bridge contract
// the Python shim marshals (`list[list[list[(float, float)]]]`); factoring
// it would change the module's Python surface. Same treatment as
// `pipeline_route.rs::run_build_route_payload`.
#[allow(clippy::type_complexity)]
pub fn pour_outline_py(
    region: Vec<(f64, f64)>,
    own_pads: Vec<(f64, f64)>,
    obstacles: Vec<(u8, f64, f64, f64, f64, f64, f64)>,
    min_island_area_mm2: f64,
    pads_only: bool,
) -> PyResult<Vec<Vec<Vec<(f64, f64)>>>> {
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
            let mut rings: Vec<Vec<(f64, f64)>> = Vec::with_capacity(z.holes.len() + 1);
            rings.push(z.exterior.iter().map(|p| (p.x, p.y)).collect());
            for h in &z.holes {
                rings.push(h.iter().map(|p| (p.x, p.y)).collect());
            }
            out.push(rings);
        }
        out
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(pour_outline_py, m)?)?;
    m.add_function(wrap_pyfunction!(emit_zone_outline_s_expr_py, m)?)?;
    Ok(())
}

/// Pyo3 wrapper for [`emit_zone_s_expr`].
///
/// Named `emit_zone_outline_s_expr_py` (NOT `emit_zone_s_expr_py`) to avoid
/// silently shadowing `zone_pour.rs`'s single-ring emitter of that name --
/// the pyo3 registration-order hazard documented in AGENTS.md: a later
/// `add_function` of the same name shadows the earlier one with no error.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (net_number, net_name, layer, exterior, holes, clearance, priority, min_thickness))]
// `clippy::too_many_arguments`: all eight parameters are the pyo3 bridge
// contract the Python shim calls by keyword (the `#[pyo3(signature = ...)]`
// names are the Python-side parameter names); collapsing them into a struct
// would change the module's Python surface.
#[allow(clippy::too_many_arguments)]
pub fn emit_zone_outline_s_expr_py(
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
        // The halo's EDGES must sit at the required separation, so the
        // radius is inflated by 1/cos(pi/24) (inscribed-polygon effect,
        // see halo_radius_inflate()).  The pad halo radius is the
        // half-DIAGONAL (hypot(1,1) = sqrt(2)) plus the clearance, so the
        // nominal area is pi * (sqrt(2)+5)^2, scaled by the inflation
        // factor squared.
        let nominal_r = std::f64::consts::SQRT_2 + 5.0;
        let expected =
            std::f64::consts::PI * nominal_r * nominal_r * halo_radius_inflate() * halo_radius_inflate();
        assert!((res.keepout_area_mm2 - expected).abs() < 2.0);
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
        assert!(!res.outlines.is_empty());
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
    fn emit_with_holes_has_one_polygon_element_per_ring() {
        let outline = ZoneOutline {
            exterior: rect(0.0, 0.0, 10.0, 10.0),
            holes: vec![rect(3.0, 3.0, 4.0, 4.0)],
        };
        let s = emit_zone_s_expr(7, "gnd", "In1.Cu", &outline, 0.3, 0, 0.25);
        assert!(s.contains("(zone (net 7)"));
        assert!(s.contains("(net_name \"gnd\")"));
        // One (polygon ...) element per ring: exterior + 1 hole.
        let polygons = s.matches("(polygon").count();
        assert_eq!(polygons, 2, "expected exterior + 1 hole polygon elements, got {s}");
        // Each polygon element carries exactly one (pts ...) block.
        let pts_count = s.matches("(pts").count();
        assert_eq!(pts_count, 2, "expected one (pts per polygon element, got {s}");
        assert!(s.contains("(xy 0.0000 0.0000)"));
        // Hole ring is present.
        assert!(s.contains("(xy 3.0000 3.0000)"));
        // Whole zone is one balanced s-expression.
        assert_eq!(s.matches('(').count(), s.matches(')').count());
        // The hole ring is NOT inside the exterior's polygon element: the
        // hole has its own (polygon ...) element.
        let first = s.find("(polygon").unwrap();
        let second = s[first + 1..]
            .find("(polygon")
            .map(|i| first + 1 + i)
            .unwrap_or(s.len());
        let ext_block = &s[first..second];
        assert!(ext_block.contains("(xy 0.0000 0.0000)"));
        assert!(!ext_block.contains("(xy 3.0000 3.0000)"));
    }

    #[cfg_attr(test, test)]
    fn capsule_halo_has_positive_area() {
        let c = capsule(Point::new(0.0, 0.0), Point::new(10.0, 0.0), 2.0, 24);
        let area = c.unsigned_area();
        // Rect 10 x 4 plus two semicircle caps r=2: 40 + pi*4 ≈ 52.57,
        // inflated by the inscribed-polygon factor (halo_radius_inflate())
        // so the capsule's straight-side edges sit at the true radius.
        let infl = halo_radius_inflate();
        let expected = 10.0 * 2.0 * 2.0 * infl + std::f64::consts::PI * 4.0 * infl * infl;
        assert!((area - expected).abs() < 1.5, "capsule area {area} vs {expected}");
    }

    #[cfg_attr(test, test)]
    fn disc_halo_area() {
        let d = disc(Point::new(0.0, 0.0), 3.0, 24);
        let area = d.unsigned_area();
        // 24-gon with vertices at inflated radius R*1/cos(pi/24): the
        // inscribed area at R=3 is 12 * r^2 * sin(2pi/24) ≈ 27.95, scaled
        // by the inflation factor squared.
        let infl = halo_radius_inflate();
        let expected = 12.0 * 9.0 * (2.0 * std::f64::consts::PI / 24.0).sin() * infl * infl;
        assert!((area - expected).abs() < 0.5, "disc area {area} vs {expected}");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("zone_generator::tests::empty_obstacles_leave_region_whole", empty_obstacles_leave_region_whole),
        ("zone_generator::tests::single_pad_halo_carves_a_hole", single_pad_halo_carves_a_hole),
        ("zone_generator::tests::island_policy_pads_only_drops_padless_pieces", island_policy_pads_only_drops_padless_pieces),
        ("zone_generator::tests::sliver_filter_drops_tiny_pieces", sliver_filter_drops_tiny_pieces),
        ("zone_generator::tests::orientation_is_normalised", orientation_is_normalised),
        ("zone_generator::tests::emit_with_holes_has_one_polygon_element_per_ring", emit_with_holes_has_one_polygon_element_per_ring),
        ("zone_generator::tests::capsule_halo_has_positive_area", capsule_halo_has_positive_area),
        ("zone_generator::tests::disc_halo_area", disc_halo_area),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

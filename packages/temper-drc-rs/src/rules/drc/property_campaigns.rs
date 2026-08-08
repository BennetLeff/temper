// Property-based campaigns over the portable clearance/courtyard geometry
// kernel (`Component::edge_distance_to` / `Component::overlaps`, board.rs),
// seeded from real footprint courtyard geometry extracted from
// `pcb/temper.kicad_pcb` (read-only extraction; that file is never touched
// by this module or its generator).
//
// Why this exists (R7 / the WASM-tier volume payload)
// -----------------------------------------------------------------------
// The wasm32 tier's existing 147-test suite is a *fixed* fixture: running it
// 10,000 times explores the same 147 inputs 10,000 times. This module gives
// the tier a payload where each invocation gets a **distinct** generated
// input: `Component::edge_distance_to` is a pure function over two
// polygons, seeded from a `u64`, so a Worker calling
// `edge_distance_symmetric_seed_000042` explores different geometry than
// `..._seed_000043`.
//
// Each property below is a metamorphic relation over a real geometry
// kernel, not an example-based assertion, and each states -- in its own
// doc comment -- the specific bug class it is designed to catch. A property
// that cannot fail is not a test; see `docs/evidence/` for the one relation
// in this campaign's design space that genuinely does fail (containment),
// and why it was deliberately kept OUT of this file's committed, always-
// green registry rather than weakened to pass here (see
// `packages/temper-drc-rs/tests/property_containment_gap.rs` and
// `packages/temper-drc-rs/examples/property_containment_sweep.rs`).
//
// Seeding from real geometry
// -----------------------------------------------------------------------
// `REAL_FOOTPRINTS` below is a read-only extraction of every footprint on
// `pcb/temper.kicad_pcb` that carries an `F.CrtYd`/`B.CrtYd` courtyard
// rectangle or polygon: 127 `(x_mm, y_mm, rotation_deg, courtyard_w_mm,
// courtyard_h_mm)` tuples, spanning real component sizes from a 0603 SMD
// capacitor (2.96 x 1.46 mm) to a TO-247-class power device (51.0 x 28.0
// mm) at their real board positions and rotations. Each property's
// `gen_case` draws two entries from this corpus (by index, from the seed's
// PRNG stream) and *perturbs* them -- jittering position, and placing the
// second component at a random angle and a radius biased toward small
// separations -- rather than sampling uniform-random polygons, which
// rarely resemble a PCB (courtyard aspect ratios, size distribution, and
// board-scale absolute coordinates all come from the real board).
//
// Extraction method: `pcb/temper.kicad_pcb` is an s-expression text file;
// footprint blocks were located by paren-depth tracking, and courtyard
// geometry was read directly from each footprint's `fp_rect`/`fp_poly` on
// layer `F.CrtYd`/`B.CrtYd`. No `pcb/temper.kicad_pcb` byte was written.

use crate::board::{BoardSide, Component, ComponentRef, NetClassName, PackageType};
use geo::{Coord, LineString, Point, Polygon};

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- pure, no external dependency, portable
// to wasm32-unknown-unknown without an entropy source. Every property's
// entire input is a function of a `u64` seed through this generator, so a
// failing invocation is reproducible from that seed alone (see
// `replay_seed` at the bottom of this file).
// ---------------------------------------------------------------------------

pub(crate) struct SplitMix64(u64);

impl SplitMix64 {
    pub(crate) fn new(seed: u64) -> Self {
        Self(seed)
    }

    pub(crate) fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform float in `[0, 1)`.
    fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform float in `[lo, hi)`.
    pub(crate) fn range(&mut self, lo: f64, hi: f64) -> f64 {
        lo + self.next_f64() * (hi - lo)
    }

    /// Uniform index in `[0, n)`. `n` is always a small, non-zero,
    /// compile-time-bounded corpus length in this module.
    pub(crate) fn index(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
}

/// A property-local PRNG stream, independent of `gen_case`'s stream, so a
/// property's own randomized parameters (translation vector, rotation
/// angle, scale factor, ...) don't correlate with which corpus entries
/// `gen_case` drew. `salt` distinguishes properties sharing the same base
/// seed.
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

// `dead_code`: these, and every property `..._impl` function and
// transform helper below, are reachable only through the generated
// `WASM_TESTS` const in `tests` (`#[cfg(any(test, feature =
// "wasm-registry"))]`) -- the same reason `scripts/gen_wasm_test_registry.py`
// applies `#[allow(dead_code, ...)]` to every eligible module's `tests`
// block itself (see that script's `ALLOW` constant). A plain
// `--no-default-features` build with neither `test` nor `wasm-registry`
// has no root that reaches them, so rustc's dead-code pass (correctly)
// cannot see the wasm32 host's indirect calls through the registry array.
#[allow(dead_code)]
const SALT_TRANSLATE: u64 = 0xA1;
#[allow(dead_code)]
const SALT_ROTATE: u64 = 0xA2;
#[allow(dead_code)]
const SALT_SCALE: u64 = 0xA3;
#[allow(dead_code)]
const SALT_SEPARATE: u64 = 0xA4;

// ---------------------------------------------------------------------------
// Real geometry corpus (extracted from pcb/temper.kicad_pcb; read-only, see
// module doc). (x_mm, y_mm, rotation_deg, courtyard_w_mm, courtyard_h_mm).
// ---------------------------------------------------------------------------

const REAL_FOOTPRINTS: &[(f64, f64, f64, f64, f64)] = &[
    (51.4900, 214.2200, 90.0, 18.5000, 7.5000),
    (106.2800, 27.0400, 180.0, 2.9600, 1.4600),
    (166.6000, 54.4700, 180.0, 4.6000, 3.2000),
    (123.9700, 42.5800, 0.0, 4.6000, 3.2000),
    (157.9000, 92.5200, 90.0, 2.9600, 1.4600),
    (139.0900, 29.0800, 90.0, 7.4000, 5.9000),
    (106.1500, 144.7800, 0.0, 4.6000, 3.2000),
    (28.8100, 220.5800, 90.0, 2.9600, 1.4600),
    (46.1200, 118.4800, 0.0, 4.6000, 3.2000),
    (21.2400, 24.4300, 90.0, 2.9600, 1.4600),
    (25.6300, 35.6300, 90.0, 2.9600, 1.4600),
    (28.8100, 111.0000, 90.0, 2.9600, 1.4600),
    (131.3400, 56.7300, 90.0, 2.9600, 1.4600),
    (75.8900, 187.7000, 270.0, 2.9600, 1.4600),
    (21.2400, 74.6900, 90.0, 2.9600, 1.4600),
    (31.5700, 88.8600, 0.0, 18.5000, 11.5000),
    (160.0000, 152.7000, 90.0, 43.1000, 23.0000),
    (65.9200, 72.3200, 270.0, 43.1000, 23.0000),
    (28.6200, 242.0000, 0.0, 43.1000, 23.0000),
    (41.6900, 21.9800, 90.0, 2.9600, 1.4600),
    (170.0200, 59.3800, 0.0, 2.9600, 1.4600),
    (162.5600, 23.0700, 90.0, 2.9600, 1.4600),
    (158.6100, 88.5600, 270.0, 2.9600, 1.4600),
    (21.2400, 30.0700, 90.0, 2.9600, 1.4600),
    (170.6200, 42.2600, 90.0, 2.9600, 1.4600),
    (133.8000, 49.1200, 90.0, 2.9600, 1.4600),
    (158.6100, 21.9800, 90.0, 2.9600, 1.4600),
    (47.5900, 21.9800, 90.0, 2.9600, 1.4600),
    (117.9600, 23.1200, 180.0, 2.9600, 1.4600),
    (21.2400, 203.4400, 90.0, 2.9600, 1.4600),
    (41.0400, 32.9500, 90.0, 3.4000, 1.9600),
    (33.5500, 35.4000, 270.0, 2.9600, 1.4600),
    (65.9900, 201.7600, 270.0, 13.0000, 5.5000),
    (137.7200, 244.6600, 180.0, 18.5000, 11.5000),
    (164.5800, 228.5800, 270.0, 18.5000, 11.5000),
    (88.1500, 251.2000, 90.0, 4.6000, 3.2000),
    (101.0800, 140.8000, 180.0, 3.5400, 6.0900),
    (95.2300, 221.3950, 180.0, 30.5000, 23.5000),
    (144.8200, 97.5500, 90.0, 29.9000, 13.6000),
    (66.8700, 50.5900, 90.0, 29.9000, 13.6000),
    (130.4800, 188.1300, 90.0, 51.0000, 28.0000),
    (22.0000, 199.9100, 90.0, 12.2600, 3.0000),
    (66.4300, 190.7800, 270.0, 2.9600, 1.4600),
    (55.7100, 174.0900, 180.0, 25.7600, 9.5000),
    (166.7300, 194.8300, 270.0, 25.7600, 9.5000),
    (117.2300, 196.9500, 90.0, 25.7600, 9.5000),
    (46.9700, 77.9600, 180.0, 25.7600, 9.5000),
    (160.1600, 54.0000, 180.0, 4.5600, 2.2600),
    (107.2900, 140.5900, 180.0, 4.5600, 2.2600),
    (37.3200, 36.1600, 180.0, 3.3600, 1.9000),
    (160.3900, 27.2300, 270.0, 3.3600, 1.9000),
    (118.6400, 249.5600, 270.0, 7.6600, 3.8600),
    (149.1500, 252.1200, 180.0, 3.3600, 1.9000),
    (42.1400, 109.9900, 270.0, 7.6600, 3.8600),
    (30.3400, 36.3800, 0.0, 2.9600, 1.4600),
    (37.1200, 33.4800, 180.0, 2.9600, 1.4600),
    (46.1400, 115.3500, 180.0, 4.5600, 2.2600),
    (81.0000, 21.5000, 180.0, 2.9600, 1.4600),
    (25.6000, 145.9100, 180.0, 2.9600, 1.4600),
    (106.7800, 21.2400, 180.0, 2.9600, 1.4600),
    (55.5400, 223.1000, 0.0, 4.5600, 2.2600),
    (51.7500, 184.2200, 270.0, 2.9600, 1.4600),
    (25.2300, 190.7800, 90.0, 2.9600, 1.4600),
    (154.9000, 21.4600, 180.0, 3.3600, 1.9000),
    (21.6400, 34.8300, 270.0, 4.5600, 2.2600),
    (63.9700, 190.1800, 270.0, 2.9600, 1.4600),
    (109.9900, 26.3100, 90.0, 2.9600, 1.4600),
    (138.8200, 137.4300, 180.0, 3.3600, 1.9000),
    (165.7800, 171.0100, 0.0, 2.9600, 1.4600),
    (166.4200, 46.2200, 180.0, 2.9600, 1.4600),
    (32.2400, 31.0200, 180.0, 2.9600, 1.4600),
    (159.3500, 33.1000, 180.0, 2.9600, 1.4600),
    (21.2400, 111.0000, 270.0, 2.9600, 1.4600),
    (78.4900, 164.0500, 90.0, 7.6600, 3.8600),
    (114.0000, 21.2400, 0.0, 2.9600, 1.4600),
    (28.4800, 143.4500, 180.0, 2.9600, 1.4600),
    (45.2900, 63.7300, 270.0, 2.9600, 1.4600),
    (42.4400, 60.0800, 180.0, 2.9600, 1.4600),
    (162.4600, 96.0200, 180.0, 2.9600, 1.4600),
    (82.4800, 251.1800, 90.0, 3.3600, 1.9000),
    (161.8200, 45.9100, 180.0, 2.9600, 1.4600),
    (162.5600, 92.8100, 270.0, 2.9600, 1.4600),
    (41.5400, 187.5700, 180.0, 2.9600, 1.4600),
    (161.5600, 30.6400, 180.0, 2.9600, 1.4600),
    (28.2300, 67.7400, 180.0, 7.6600, 3.8600),
    (94.2000, 244.0100, 270.0, 2.9600, 1.4600),
    (97.4300, 189.1900, 90.0, 4.5600, 2.2600),
    (168.7900, 170.6300, 90.0, 4.5600, 2.2600),
    (84.4100, 242.2700, 180.0, 4.5600, 2.2600),
    (154.1400, 29.9000, 270.0, 2.9600, 1.4600),
    (127.4100, 23.8500, 270.0, 2.9600, 1.4600),
    (33.2300, 97.2900, 90.0, 4.5600, 2.2600),
    (167.8200, 174.4400, 180.0, 4.5600, 2.2600),
    (114.3500, 138.7600, 90.0, 4.5600, 2.2600),
    (102.5300, 251.9000, 180.0, 2.9600, 1.4600),
    (142.3500, 59.7300, 180.0, 4.5600, 2.2600),
    (108.6000, 37.6000, 180.0, 4.5400, 2.1000),
    (119.2100, 207.8800, 90.0, 2.9600, 1.4600),
    (22.7300, 149.1200, 90.0, 2.9600, 1.4600),
    (91.4800, 242.6200, 90.0, 2.9600, 1.4600),
    (137.1600, 140.1000, 0.0, 2.9600, 1.4600),
    (44.9200, 36.0600, 90.0, 12.2600, 3.0000),
    (169.7400, 48.6800, 180.0, 2.9600, 1.4600),
    (101.3700, 144.9000, 180.0, 2.9600, 1.4600),
    (21.2700, 211.7600, 270.0, 2.9600, 1.4600),
    (123.1700, 59.9300, 270.0, 2.9600, 1.4600),
    (151.2100, 229.1100, 90.0, 4.5600, 2.2600),
    (97.4100, 241.8700, 180.0, 2.9600, 1.4600),
    (117.3600, 144.9000, 180.0, 2.9600, 1.4600),
    (25.3400, 187.5700, 180.0, 2.9600, 1.4600),
    (151.4800, 23.0700, 270.0, 2.9600, 1.4600),
    (110.7400, 23.1000, 180.0, 2.9600, 1.4600),
    (79.6500, 242.7700, 180.0, 2.9600, 1.4600),
    (36.7600, 31.0200, 180.0, 2.9600, 1.4600),
    (139.7700, 140.7000, 270.0, 2.9600, 1.4600),
    (170.0200, 51.1400, 0.0, 2.9600, 1.4600),
    (123.0800, 56.3900, 90.0, 12.2600, 3.0000),
    (71.2500, 223.0200, 90.0, 2.9600, 1.4600),
    (23.2700, 164.0800, 90.0, 2.9600, 1.4600),
    (106.4700, 241.8700, 180.0, 2.9600, 1.4600),
    (139.7700, 144.6600, 270.0, 2.9600, 1.4600),
    (53.2100, 148.9100, 90.0, 24.8600, 30.5000),
    (168.0000, 223.0300, 180.0, 10.5000, 4.9000),
    (28.2900, 175.4400, 180.0, 10.5000, 4.9000),
    (156.9200, 72.4800, 0.0, 12.2600, 8.1200),
    (23.7200, 233.2500, 270.0, 16.4000, 5.5300),
    (100.0700, 159.3300, 180.0, 16.4000, 5.5300),
];

/// Number of real footprints in the corpus. `pub(crate)` so the containment
/// investigation (`examples/property_containment_sweep.rs`) can reuse it.
pub const REAL_FOOTPRINT_COUNT: usize = REAL_FOOTPRINTS.len();

// ---------------------------------------------------------------------------
// Geometry construction / transforms
// ---------------------------------------------------------------------------

fn rotate_point(x: f64, y: f64, deg: f64) -> (f64, f64) {
    let r = deg.to_radians();
    let (s, c) = r.sin_cos();
    (x * c - y * s, x * s + y * c)
}

/// A closed rectangular ring (first point repeated as last, matching the
/// OGC "linear ring" convention `geo`'s `polygon!` macro produces) centered
/// at `(cx, cy)`, `w` x `h`, rotated `rot_deg` about its own center.
fn rect_polygon(cx: f64, cy: f64, w: f64, h: f64, rot_deg: f64) -> Polygon<f64> {
    let hw = w / 2.0;
    let hh = h / 2.0;
    let corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)];
    let mut pts: Vec<Coord<f64>> = corners
        .iter()
        .map(|&(x, y)| {
            let (rx, ry) = rotate_point(x, y, rot_deg);
            Coord { x: cx + rx, y: cy + ry }
        })
        .collect();
    pts.push(pts[0]);
    Polygon::new(LineString::new(pts), Vec::new())
}

fn make_component(refdes: &str, cx: f64, cy: f64, w: f64, h: f64, rot_deg: f64) -> Component {
    Component {
        refdes: ComponentRef(refdes.to_string()),
        center: Point::new(cx, cy),
        rotation: rot_deg,
        side: BoardSide::Top,
        width: w,
        height: h,
        net_class: NetClassName("Signal".into()),
        power_dissipation_w: None,
        package_type: PackageType::Smd,
        is_magnetic: false,
        is_electrolytic: false,
        vent_direction: None,
        footprint_polygon: Some(rect_polygon(cx, cy, w, h, rot_deg)),
    }
}

// `make_component` (the only constructor every property-campaign
// component goes through) always sets `footprint_polygon = Some(..)`, so
// this invariant holds for every value this module or its consumers
// (the containment sweep/regression test) can construct -- the crate-wide
// `clippy::expect_used = "deny"` lint is for production DRC-rule code
// paths that receive externally-supplied `Component`s, not this
// self-contained campaign's own generated inputs.
#[allow(clippy::expect_used)]
pub fn polygon_points(c: &Component) -> Vec<(f64, f64)> {
    c.footprint_polygon
        .as_ref()
        .expect("property-campaign components always carry a footprint polygon")
        .exterior()
        .points()
        .map(|p| (p.x(), p.y()))
        .collect()
}

fn rebuild_polygon(points: &[(f64, f64)]) -> Polygon<f64> {
    let coords: Vec<Coord<f64>> = points.iter().map(|&(x, y)| Coord { x, y }).collect();
    Polygon::new(LineString::new(coords), Vec::new())
}

fn translate_component(c: &Component, dx: f64, dy: f64) -> Component {
    let pts: Vec<(f64, f64)> = polygon_points(c).iter().map(|&(x, y)| (x + dx, y + dy)).collect();
    Component {
        center: Point::new(c.center.x() + dx, c.center.y() + dy),
        footprint_polygon: Some(rebuild_polygon(&pts)),
        ..c.clone()
    }
}

#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
fn rotate_component_about(c: &Component, pivot: (f64, f64), deg: f64) -> Component {
    let pts: Vec<(f64, f64)> = polygon_points(c)
        .iter()
        .map(|&(x, y)| {
            let (rx, ry) = rotate_point(x - pivot.0, y - pivot.1, deg);
            (rx + pivot.0, ry + pivot.1)
        })
        .collect();
    let (rcx, rcy) = rotate_point(c.center.x() - pivot.0, c.center.y() - pivot.1, deg);
    Component {
        center: Point::new(rcx + pivot.0, rcy + pivot.1),
        rotation: c.rotation + deg,
        footprint_polygon: Some(rebuild_polygon(&pts)),
        ..c.clone()
    }
}

#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
fn scale_component_about(c: &Component, origin: (f64, f64), k: f64) -> Component {
    let pts: Vec<(f64, f64)> = polygon_points(c)
        .iter()
        .map(|&(x, y)| (origin.0 + (x - origin.0) * k, origin.1 + (y - origin.1) * k))
        .collect();
    Component {
        center: Point::new(
            origin.0 + (c.center.x() - origin.0) * k,
            origin.1 + (c.center.y() - origin.1) * k,
        ),
        width: c.width * k,
        height: c.height * k,
        footprint_polygon: Some(rebuild_polygon(&pts)),
        ..c.clone()
    }
}

/// Build a `(a, b)` case from a seed: two real courtyard shapes, `a` at (a
/// small jitter of) its real board position, `b` at a random angle from
/// `a` and a radius biased toward small separations (cubic bias in `u`) so
/// the generated corpus spans far-apart, near-miss, touching, overlapping,
/// AND fully-nested regimes -- regimes a fixed unit-test fixture never
/// reaches by construction, and the regimes where a clearance kernel's
/// bugs actually live.
pub fn gen_case(seed: u64) -> (Component, Component) {
    let mut rng = SplitMix64::new(seed);
    let ia = rng.index(REAL_FOOTPRINTS.len());
    let ib = rng.index(REAL_FOOTPRINTS.len());
    let (ax0, ay0, arot, aw, ah) = REAL_FOOTPRINTS[ia];
    let (_, _, brot0, bw, bh) = REAL_FOOTPRINTS[ib];

    let jx = rng.range(-1.0, 1.0);
    let jy = rng.range(-1.0, 1.0);
    let ax = ax0 + jx;
    let ay = ay0 + jy;
    let a = make_component("A", ax, ay, aw, ah, arot);

    let theta = rng.range(0.0, std::f64::consts::TAU);
    let u = rng.next_f64();
    let max_r = (aw.max(ah) + bw.max(bh)) * 1.5 + 20.0;
    let r = u * u * u * max_r; // cubic bias toward small separations
    let bx = ax + r * theta.cos();
    let by = ay + r * theta.sin();
    let brot = if rng.next_f64() < 0.5 { brot0 } else { rng.range(0.0, 360.0) };
    let b = make_component("B", bx, by, bw, bh, brot);

    (a, b)
}

// ---------------------------------------------------------------------------
// Independent naive reference implementation.
//
// Deliberately does NOT call `geo::EuclideanDistance` or any `geo`
// algorithm -- it is a from-scratch point/segment/segment implementation
// over raw `(f64, f64)` tuples, so agreement with `Component::edge_distance_to`
// (which delegates to `geo::Line::euclidean_distance`) is a genuine
// cross-check between two independently-written algorithms, not the same
// code compared with itself. This is the check that would catch a `geo`
// version upgrade silently changing `euclidean_distance` semantics (a
// real-world precedent for this class of divergence:
// docs/evidence/2026-08-06-wasm32-float-divergence.md), or an off-by-one
// in `edge_distance_to`'s nested edge-pair iteration.
// ---------------------------------------------------------------------------

fn point_seg_closest(p: (f64, f64), s0: (f64, f64), s1: (f64, f64)) -> (f64, (f64, f64)) {
    let dx = s1.0 - s0.0;
    let dy = s1.1 - s0.1;
    let len2 = dx * dx + dy * dy;
    let t = if len2 < 1e-30 {
        0.0
    } else {
        (((p.0 - s0.0) * dx + (p.1 - s0.1) * dy) / len2).clamp(0.0, 1.0)
    };
    let cx = s0.0 + t * dx;
    let cy = s0.1 + t * dy;
    let d = ((p.0 - cx).powi(2) + (p.1 - cy).powi(2)).sqrt();
    (d, (cx, cy))
}

fn orient(a: (f64, f64), b: (f64, f64), c: (f64, f64)) -> f64 {
    (b.0 - a.0) * (c.1 - a.1) - (b.1 - a.1) * (c.0 - a.0)
}

fn on_segment(a: (f64, f64), b: (f64, f64), p: (f64, f64)) -> bool {
    let eps = 1e-9;
    p.0 >= a.0.min(b.0) - eps
        && p.0 <= a.0.max(b.0) + eps
        && p.1 >= a.1.min(b.1) - eps
        && p.1 <= a.1.max(b.1) + eps
}

fn segments_intersect(a0: (f64, f64), a1: (f64, f64), b0: (f64, f64), b1: (f64, f64)) -> bool {
    let o1 = orient(a0, a1, b0);
    let o2 = orient(a0, a1, b1);
    let o3 = orient(b0, b1, a0);
    let o4 = orient(b0, b1, a1);
    let eps = 1e-9;
    if (o1 > eps) != (o2 > eps)
        && (o1 < -eps) != (o2 < -eps)
        && (o3 > eps) != (o4 > eps)
        && (o3 < -eps) != (o4 < -eps)
    {
        return true;
    }
    if o1.abs() < eps && on_segment(a0, a1, b0) {
        return true;
    }
    if o2.abs() < eps && on_segment(a0, a1, b1) {
        return true;
    }
    if o3.abs() < eps && on_segment(b0, b1, a0) {
        return true;
    }
    if o4.abs() < eps && on_segment(b0, b1, a1) {
        return true;
    }
    false
}

/// Minimum boundary-to-boundary distance between two closed polygon rings,
/// plus a closest-point witness pair `(point_on_a, point_on_b)`. O(n*m)
/// segment pairs, exactly mirroring what `edge_distance_to`'s nested-loop
/// fold does -- but implemented independently (see module doc above).
pub fn naive_closest(poly_a: &[(f64, f64)], poly_b: &[(f64, f64)]) -> (f64, (f64, f64), (f64, f64)) {
    let mut best = f64::MAX;
    let mut wa = poly_a[0];
    let mut wb = poly_b[0];
    let na = poly_a.len();
    let nb = poly_b.len();
    for i in 0..na.saturating_sub(1) {
        let a0 = poly_a[i];
        let a1 = poly_a[i + 1];
        for j in 0..nb.saturating_sub(1) {
            let b0 = poly_b[j];
            let b1 = poly_b[j + 1];
            if segments_intersect(a0, a1, b0, b1) {
                return (0.0, a0, b0);
            }
            let candidates = [
                {
                    let (d, c) = point_seg_closest(a0, b0, b1);
                    (d, a0, c)
                },
                {
                    let (d, c) = point_seg_closest(a1, b0, b1);
                    (d, a1, c)
                },
                {
                    let (d, c) = point_seg_closest(b0, a0, a1);
                    (d, c, b0)
                },
                {
                    let (d, c) = point_seg_closest(b1, a0, a1);
                    (d, c, b1)
                },
            ];
            for (d, pa, pb) in candidates {
                if d < best {
                    best = d;
                    wa = pa;
                    wb = pb;
                }
            }
        }
    }
    (best, wa, wb)
}

// ---------------------------------------------------------------------------
// Properties. Each is a metamorphic relation over the real kernel
// `Component::edge_distance_to` (board.rs). Every function takes a `u64`
// seed and panics (with the seed and the offending values in the message)
// on violation -- the same failure protocol every other wasm-registry test
// in this crate already uses, so a failure surfaces through the existing
// tier machinery (WebAssembly trap -> `temper_panic_message_ptr`) with no
// new plumbing.
// ---------------------------------------------------------------------------

/// `d(a, b) == d(b, a)`.
///
/// Bug this would catch: an asymmetric edge-pair iteration (e.g. a
/// refactor that iterates `a`'s edges against `b`'s *vertices* instead of
/// `b`'s edges) would silently make a clearance check pass in one
/// component order and fail in the other -- and `ClearanceCheck::check`
/// iterates unordered pairs `(i, j)` with `i < j`, so which order a rule
/// sees is an accident of vector layout, not something a caller chooses.
#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
pub(crate) fn edge_distance_symmetric_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let d1 = a.edge_distance_to(&b);
    let d2 = b.edge_distance_to(&a);
    let diff = (d1 - d2).abs();
    assert!(
        diff < 1e-9,
        "edge_distance_to not symmetric: seed={seed} d(a,b)={d1} d(b,a)={d2} diff={diff}"
    );
}

/// Translating both components by the same vector leaves `edge_distance_to`
/// unchanged.
///
/// Bug this would catch: any absolute-coordinate-dependent code path (a
/// spatial hash/grid bucket boundary, a fixed-epsilon comparison that only
/// misfires far from the origin, catastrophic cancellation at large
/// coordinate offsets) -- the real board's components sit at absolute
/// coordinates in the 20-250mm range already, so this also exercises that
/// realistic offset, not just coordinates near zero.
#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
pub(crate) fn edge_distance_translation_invariant_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let d0 = a.edge_distance_to(&b);
    let mut rng = sub_rng(seed, SALT_TRANSLATE);
    let dx = rng.range(-1000.0, 1000.0);
    let dy = rng.range(-1000.0, 1000.0);
    let a2 = translate_component(&a, dx, dy);
    let b2 = translate_component(&b, dx, dy);
    let d1 = a2.edge_distance_to(&b2);
    let tol = (d0.abs() * 1e-6).max(1e-6);
    assert!(
        (d0 - d1).abs() < tol,
        "translation changed edge distance: seed={seed} dx={dx} dy={dy} d0={d0} d1={d1}"
    );
}

/// Rotating both components by the same angle about the same pivot leaves
/// `edge_distance_to` unchanged.
///
/// Bug this would catch: exactly the class of bug this repository has
/// already hit in creepage/isolation code
/// (`docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`)
/// -- a distance computation that implicitly assumes axis-aligned geometry
/// (e.g. a bounding-box shortcut that is only a lower bound at 0/90/180/270
/// degrees) would diverge from the true edge-to-edge distance at other
/// rotations.
#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
pub(crate) fn edge_distance_rotation_invariant_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let d0 = a.edge_distance_to(&b);
    let mut rng = sub_rng(seed, SALT_ROTATE);
    let angle = rng.range(-720.0, 720.0);
    let pivot = (rng.range(-50.0, 250.0), rng.range(-50.0, 250.0));
    let a2 = rotate_component_about(&a, pivot, angle);
    let b2 = rotate_component_about(&b, pivot, angle);
    let d1 = a2.edge_distance_to(&b2);
    let tol = (d0.abs() * 1e-6).max(1e-6);
    assert!(
        (d0 - d1).abs() < tol,
        "rotation changed edge distance: seed={seed} angle={angle} pivot={pivot:?} d0={d0} d1={d1}"
    );
}

/// Scaling both components uniformly about a fixed origin by `k` scales
/// `edge_distance_to` by exactly `k`.
///
/// Bug this would catch: any absolute-epsilon threshold baked into the
/// distance path (a fixed `1e-9`-style early-out compared against a
/// scale-dependent quantity) would break linearity at small or large `k` --
/// this is the metamorphic relation the task's own brief names explicitly
/// ("monotonicity under scaling").
#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
pub(crate) fn edge_distance_scale_invariant_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let d0 = a.edge_distance_to(&b);
    let mut rng = sub_rng(seed, SALT_SCALE);
    let k = rng.range(0.1, 8.0);
    let a2 = scale_component_about(&a, (0.0, 0.0), k);
    let b2 = scale_component_about(&b, (0.0, 0.0), k);
    let d1 = a2.edge_distance_to(&b2);
    let expected = d0 * k;
    let tol = (expected.abs() * 1e-6).max(1e-6);
    assert!(
        (d1 - expected).abs() < tol,
        "scale invariance violated: seed={seed} k={k} d0={d0} d1={d1} expected={expected}"
    );
}

/// The independently-implemented naive reference (`naive_closest`, above)
/// agrees with `Component::edge_distance_to`.
///
/// Bug this would catch: a `geo` crate version upgrade silently changing
/// `euclidean_distance` semantics (this repository has already measured one
/// native-vs-wasm32 float divergence class,
/// `docs/evidence/2026-08-06-wasm32-float-divergence.md`, though a
/// different mechanism than this check); or an indexing bug in
/// `edge_distance_to`'s nested `flat_map` that silently skips an edge pair.
#[allow(dead_code)] // see SALT_* comment above: reachable only via tests::WASM_TESTS
pub(crate) fn edge_distance_naive_reference_agreement_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let fast = a.edge_distance_to(&b);
    let pa = polygon_points(&a);
    let pb = polygon_points(&b);
    let (naive, _, _) = naive_closest(&pa, &pb);
    let tol = (fast.abs().max(naive.abs()) * 1e-6).max(1e-6);
    assert!(
        (fast - naive).abs() < tol,
        "fast/naive edge-distance disagreement: seed={seed} fast={fast} naive={naive} diff={}",
        (fast - naive).abs()
    );
}

/// Translating `b` strictly away from `a` along the *true separating
/// direction* (the vector between the naive reference's closest-point
/// witnesses) by `t` never decreases `edge_distance_to`, and in fact must
/// increase it by at least `t` (a provable property of convex sets: if `u`
/// is the unit vector from `a`'s nearest point to `b`'s nearest point, `A`
/// lies entirely in the half-space `{x : (x-p)*u <= 0}` and `B` entirely in
/// `{x : (x-q)*u >= 0}`, so translating `B` by `t*u` increases every
/// `a-to-b'` distance's projection onto `u` by at least `t`) -- **provided
/// `A` and `B` are disjoint as solid regions**. `d0 < 1e-6` is skipped as
/// degenerate (touching, separating direction undefined), but that guard
/// alone is NOT sufficient: this property is not wired into this module's
/// `tests` block (i.e. NOT part of the committed wasm volume registry)
/// because it genuinely fails, at real volume, whenever `gen_case` draws a
/// fully-nested pair (one courtyard's bbox inside the other's) -- `d0` is
/// then a small positive *boundary* gap even though the solid regions
/// overlap completely, so the convex-disjoint-sets proof this property
/// relies on does not apply. That is not a flaw in this property's
/// *design* (the math is correct for disjoint convex sets) -- it is a
/// second, independent metamorphic relation exposing the exact same
/// underlying gap as `docs/evidence/2026-08-07-property-campaign-*`'s
/// containment finding: `edge_distance_to`'s boundary-distance semantics
/// silently break down under full containment. See
/// `examples/property_containment_sweep.rs`, which reuses this exact
/// function as an automatic containment detector (a monotonicity
/// violation IS the signal) instead of adding an exclusion here that
/// would just be `overlaps()` in disguise -- excluding containment cases
/// from this property to make it pass in the registry would be exactly
/// the kind of weakening the campaign's brief prohibits.
///
/// Bug this would catch (in the disjoint regime it's valid for): a sign
/// error in a translation/direction computation (components moving the
/// wrong way), or the bbox pre-filter in `ClearanceCheck::check`
/// (`rules/drc/clearance.rs`) producing a non-monotonic accept/reject
/// boundary as a board is perturbed.
pub fn edge_distance_monotonic_under_separation_impl(seed: u64) {
    let (a, b) = gen_case(seed);
    let pa = polygon_points(&a);
    let pb = polygon_points(&b);
    let (d0, wa, wb) = naive_closest(&pa, &pb);
    if d0 < 1e-6 {
        return; // touching/overlapping: separating direction undefined.
    }
    let ux = (wb.0 - wa.0) / d0;
    let uy = (wb.1 - wa.1) / d0;
    let mut rng = sub_rng(seed, SALT_SEPARATE);
    let t = rng.range(0.01, 200.0);
    let b2 = translate_component(&b, ux * t, uy * t);
    let d1 = a.edge_distance_to(&b2);
    let expected_min = d0 + t;
    assert!(
        d1 + 1e-6 >= expected_min,
        "monotonicity under true separating-direction translation violated: \
         seed={seed} d0={d0} t={t} d1={d1} expected>={expected_min}"
    );
}

/// Replay a single seed's `(a, b)` case. Used by
/// `examples/property_containment_sweep.rs` and by anyone reproducing a
/// reported failure locally: every property above is a pure function of
/// `seed`, so `replay_seed(seed)` reconstructs the exact failing input.
pub fn replay_seed(seed: u64) -> (Component, Component) {
    gen_case(seed)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn gen_case_is_deterministic_in_seed() {
        let (a1, a2b) = gen_case(12345);
        let (a2, b2) = gen_case(12345);
        assert_eq!(a1.center, a2.center);
        assert_eq!(a2b.center, b2.center);
        assert_eq!(polygon_points(&a1), polygon_points(&a2));
    }

    #[cfg_attr(test, test)]
    fn gen_case_varies_with_seed() {
        let (a1, _) = gen_case(1);
        let (a2, _) = gen_case(2);
        assert_ne!(a1.center, a2.center);
    }

    #[cfg_attr(test, test)]
    fn naive_closest_agrees_on_disjoint_unit_squares() {
        // Two axis-aligned unit squares, gap of exactly 3.0 on the x-axis.
        let a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)];
        let b = [(4.0, 0.0), (5.0, 0.0), (5.0, 1.0), (4.0, 1.0), (4.0, 0.0)];
        let (d, _, _) = naive_closest(&a, &b);
        assert!((d - 3.0).abs() < 1e-9, "expected 3.0, got {d}");
    }

    #[cfg_attr(test, test)]
    fn naive_closest_zero_for_touching_squares() {
        let a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)];
        let b = [(1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0), (1.0, 0.0)];
        let (d, _, _) = naive_closest(&a, &b);
        assert!(d < 1e-9, "expected ~0.0, got {d}");
    }

    // --- BEGIN generated seeded property wrappers (tools/wasm/gen_property_campaign.py) ---
    // 5 properties x 300 seeds = 1500 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn symmetric_seed_000000() { edge_distance_symmetric_impl(0); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000001() { edge_distance_symmetric_impl(1); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000002() { edge_distance_symmetric_impl(2); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000003() { edge_distance_symmetric_impl(3); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000004() { edge_distance_symmetric_impl(4); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000005() { edge_distance_symmetric_impl(5); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000006() { edge_distance_symmetric_impl(6); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000007() { edge_distance_symmetric_impl(7); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000008() { edge_distance_symmetric_impl(8); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000009() { edge_distance_symmetric_impl(9); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000010() { edge_distance_symmetric_impl(10); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000011() { edge_distance_symmetric_impl(11); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000012() { edge_distance_symmetric_impl(12); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000013() { edge_distance_symmetric_impl(13); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000014() { edge_distance_symmetric_impl(14); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000015() { edge_distance_symmetric_impl(15); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000016() { edge_distance_symmetric_impl(16); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000017() { edge_distance_symmetric_impl(17); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000018() { edge_distance_symmetric_impl(18); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000019() { edge_distance_symmetric_impl(19); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000020() { edge_distance_symmetric_impl(20); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000021() { edge_distance_symmetric_impl(21); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000022() { edge_distance_symmetric_impl(22); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000023() { edge_distance_symmetric_impl(23); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000024() { edge_distance_symmetric_impl(24); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000025() { edge_distance_symmetric_impl(25); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000026() { edge_distance_symmetric_impl(26); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000027() { edge_distance_symmetric_impl(27); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000028() { edge_distance_symmetric_impl(28); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000029() { edge_distance_symmetric_impl(29); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000030() { edge_distance_symmetric_impl(30); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000031() { edge_distance_symmetric_impl(31); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000032() { edge_distance_symmetric_impl(32); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000033() { edge_distance_symmetric_impl(33); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000034() { edge_distance_symmetric_impl(34); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000035() { edge_distance_symmetric_impl(35); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000036() { edge_distance_symmetric_impl(36); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000037() { edge_distance_symmetric_impl(37); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000038() { edge_distance_symmetric_impl(38); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000039() { edge_distance_symmetric_impl(39); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000040() { edge_distance_symmetric_impl(40); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000041() { edge_distance_symmetric_impl(41); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000042() { edge_distance_symmetric_impl(42); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000043() { edge_distance_symmetric_impl(43); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000044() { edge_distance_symmetric_impl(44); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000045() { edge_distance_symmetric_impl(45); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000046() { edge_distance_symmetric_impl(46); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000047() { edge_distance_symmetric_impl(47); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000048() { edge_distance_symmetric_impl(48); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000049() { edge_distance_symmetric_impl(49); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000050() { edge_distance_symmetric_impl(50); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000051() { edge_distance_symmetric_impl(51); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000052() { edge_distance_symmetric_impl(52); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000053() { edge_distance_symmetric_impl(53); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000054() { edge_distance_symmetric_impl(54); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000055() { edge_distance_symmetric_impl(55); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000056() { edge_distance_symmetric_impl(56); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000057() { edge_distance_symmetric_impl(57); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000058() { edge_distance_symmetric_impl(58); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000059() { edge_distance_symmetric_impl(59); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000060() { edge_distance_symmetric_impl(60); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000061() { edge_distance_symmetric_impl(61); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000062() { edge_distance_symmetric_impl(62); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000063() { edge_distance_symmetric_impl(63); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000064() { edge_distance_symmetric_impl(64); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000065() { edge_distance_symmetric_impl(65); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000066() { edge_distance_symmetric_impl(66); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000067() { edge_distance_symmetric_impl(67); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000068() { edge_distance_symmetric_impl(68); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000069() { edge_distance_symmetric_impl(69); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000070() { edge_distance_symmetric_impl(70); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000071() { edge_distance_symmetric_impl(71); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000072() { edge_distance_symmetric_impl(72); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000073() { edge_distance_symmetric_impl(73); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000074() { edge_distance_symmetric_impl(74); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000075() { edge_distance_symmetric_impl(75); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000076() { edge_distance_symmetric_impl(76); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000077() { edge_distance_symmetric_impl(77); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000078() { edge_distance_symmetric_impl(78); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000079() { edge_distance_symmetric_impl(79); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000080() { edge_distance_symmetric_impl(80); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000081() { edge_distance_symmetric_impl(81); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000082() { edge_distance_symmetric_impl(82); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000083() { edge_distance_symmetric_impl(83); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000084() { edge_distance_symmetric_impl(84); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000085() { edge_distance_symmetric_impl(85); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000086() { edge_distance_symmetric_impl(86); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000087() { edge_distance_symmetric_impl(87); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000088() { edge_distance_symmetric_impl(88); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000089() { edge_distance_symmetric_impl(89); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000090() { edge_distance_symmetric_impl(90); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000091() { edge_distance_symmetric_impl(91); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000092() { edge_distance_symmetric_impl(92); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000093() { edge_distance_symmetric_impl(93); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000094() { edge_distance_symmetric_impl(94); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000095() { edge_distance_symmetric_impl(95); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000096() { edge_distance_symmetric_impl(96); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000097() { edge_distance_symmetric_impl(97); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000098() { edge_distance_symmetric_impl(98); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000099() { edge_distance_symmetric_impl(99); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000100() { edge_distance_symmetric_impl(100); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000101() { edge_distance_symmetric_impl(101); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000102() { edge_distance_symmetric_impl(102); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000103() { edge_distance_symmetric_impl(103); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000104() { edge_distance_symmetric_impl(104); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000105() { edge_distance_symmetric_impl(105); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000106() { edge_distance_symmetric_impl(106); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000107() { edge_distance_symmetric_impl(107); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000108() { edge_distance_symmetric_impl(108); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000109() { edge_distance_symmetric_impl(109); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000110() { edge_distance_symmetric_impl(110); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000111() { edge_distance_symmetric_impl(111); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000112() { edge_distance_symmetric_impl(112); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000113() { edge_distance_symmetric_impl(113); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000114() { edge_distance_symmetric_impl(114); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000115() { edge_distance_symmetric_impl(115); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000116() { edge_distance_symmetric_impl(116); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000117() { edge_distance_symmetric_impl(117); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000118() { edge_distance_symmetric_impl(118); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000119() { edge_distance_symmetric_impl(119); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000120() { edge_distance_symmetric_impl(120); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000121() { edge_distance_symmetric_impl(121); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000122() { edge_distance_symmetric_impl(122); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000123() { edge_distance_symmetric_impl(123); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000124() { edge_distance_symmetric_impl(124); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000125() { edge_distance_symmetric_impl(125); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000126() { edge_distance_symmetric_impl(126); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000127() { edge_distance_symmetric_impl(127); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000128() { edge_distance_symmetric_impl(128); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000129() { edge_distance_symmetric_impl(129); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000130() { edge_distance_symmetric_impl(130); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000131() { edge_distance_symmetric_impl(131); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000132() { edge_distance_symmetric_impl(132); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000133() { edge_distance_symmetric_impl(133); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000134() { edge_distance_symmetric_impl(134); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000135() { edge_distance_symmetric_impl(135); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000136() { edge_distance_symmetric_impl(136); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000137() { edge_distance_symmetric_impl(137); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000138() { edge_distance_symmetric_impl(138); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000139() { edge_distance_symmetric_impl(139); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000140() { edge_distance_symmetric_impl(140); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000141() { edge_distance_symmetric_impl(141); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000142() { edge_distance_symmetric_impl(142); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000143() { edge_distance_symmetric_impl(143); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000144() { edge_distance_symmetric_impl(144); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000145() { edge_distance_symmetric_impl(145); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000146() { edge_distance_symmetric_impl(146); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000147() { edge_distance_symmetric_impl(147); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000148() { edge_distance_symmetric_impl(148); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000149() { edge_distance_symmetric_impl(149); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000150() { edge_distance_symmetric_impl(150); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000151() { edge_distance_symmetric_impl(151); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000152() { edge_distance_symmetric_impl(152); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000153() { edge_distance_symmetric_impl(153); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000154() { edge_distance_symmetric_impl(154); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000155() { edge_distance_symmetric_impl(155); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000156() { edge_distance_symmetric_impl(156); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000157() { edge_distance_symmetric_impl(157); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000158() { edge_distance_symmetric_impl(158); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000159() { edge_distance_symmetric_impl(159); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000160() { edge_distance_symmetric_impl(160); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000161() { edge_distance_symmetric_impl(161); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000162() { edge_distance_symmetric_impl(162); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000163() { edge_distance_symmetric_impl(163); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000164() { edge_distance_symmetric_impl(164); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000165() { edge_distance_symmetric_impl(165); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000166() { edge_distance_symmetric_impl(166); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000167() { edge_distance_symmetric_impl(167); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000168() { edge_distance_symmetric_impl(168); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000169() { edge_distance_symmetric_impl(169); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000170() { edge_distance_symmetric_impl(170); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000171() { edge_distance_symmetric_impl(171); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000172() { edge_distance_symmetric_impl(172); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000173() { edge_distance_symmetric_impl(173); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000174() { edge_distance_symmetric_impl(174); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000175() { edge_distance_symmetric_impl(175); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000176() { edge_distance_symmetric_impl(176); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000177() { edge_distance_symmetric_impl(177); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000178() { edge_distance_symmetric_impl(178); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000179() { edge_distance_symmetric_impl(179); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000180() { edge_distance_symmetric_impl(180); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000181() { edge_distance_symmetric_impl(181); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000182() { edge_distance_symmetric_impl(182); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000183() { edge_distance_symmetric_impl(183); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000184() { edge_distance_symmetric_impl(184); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000185() { edge_distance_symmetric_impl(185); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000186() { edge_distance_symmetric_impl(186); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000187() { edge_distance_symmetric_impl(187); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000188() { edge_distance_symmetric_impl(188); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000189() { edge_distance_symmetric_impl(189); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000190() { edge_distance_symmetric_impl(190); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000191() { edge_distance_symmetric_impl(191); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000192() { edge_distance_symmetric_impl(192); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000193() { edge_distance_symmetric_impl(193); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000194() { edge_distance_symmetric_impl(194); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000195() { edge_distance_symmetric_impl(195); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000196() { edge_distance_symmetric_impl(196); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000197() { edge_distance_symmetric_impl(197); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000198() { edge_distance_symmetric_impl(198); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000199() { edge_distance_symmetric_impl(199); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000200() { edge_distance_symmetric_impl(200); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000201() { edge_distance_symmetric_impl(201); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000202() { edge_distance_symmetric_impl(202); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000203() { edge_distance_symmetric_impl(203); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000204() { edge_distance_symmetric_impl(204); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000205() { edge_distance_symmetric_impl(205); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000206() { edge_distance_symmetric_impl(206); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000207() { edge_distance_symmetric_impl(207); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000208() { edge_distance_symmetric_impl(208); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000209() { edge_distance_symmetric_impl(209); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000210() { edge_distance_symmetric_impl(210); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000211() { edge_distance_symmetric_impl(211); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000212() { edge_distance_symmetric_impl(212); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000213() { edge_distance_symmetric_impl(213); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000214() { edge_distance_symmetric_impl(214); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000215() { edge_distance_symmetric_impl(215); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000216() { edge_distance_symmetric_impl(216); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000217() { edge_distance_symmetric_impl(217); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000218() { edge_distance_symmetric_impl(218); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000219() { edge_distance_symmetric_impl(219); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000220() { edge_distance_symmetric_impl(220); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000221() { edge_distance_symmetric_impl(221); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000222() { edge_distance_symmetric_impl(222); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000223() { edge_distance_symmetric_impl(223); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000224() { edge_distance_symmetric_impl(224); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000225() { edge_distance_symmetric_impl(225); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000226() { edge_distance_symmetric_impl(226); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000227() { edge_distance_symmetric_impl(227); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000228() { edge_distance_symmetric_impl(228); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000229() { edge_distance_symmetric_impl(229); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000230() { edge_distance_symmetric_impl(230); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000231() { edge_distance_symmetric_impl(231); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000232() { edge_distance_symmetric_impl(232); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000233() { edge_distance_symmetric_impl(233); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000234() { edge_distance_symmetric_impl(234); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000235() { edge_distance_symmetric_impl(235); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000236() { edge_distance_symmetric_impl(236); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000237() { edge_distance_symmetric_impl(237); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000238() { edge_distance_symmetric_impl(238); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000239() { edge_distance_symmetric_impl(239); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000240() { edge_distance_symmetric_impl(240); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000241() { edge_distance_symmetric_impl(241); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000242() { edge_distance_symmetric_impl(242); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000243() { edge_distance_symmetric_impl(243); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000244() { edge_distance_symmetric_impl(244); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000245() { edge_distance_symmetric_impl(245); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000246() { edge_distance_symmetric_impl(246); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000247() { edge_distance_symmetric_impl(247); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000248() { edge_distance_symmetric_impl(248); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000249() { edge_distance_symmetric_impl(249); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000250() { edge_distance_symmetric_impl(250); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000251() { edge_distance_symmetric_impl(251); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000252() { edge_distance_symmetric_impl(252); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000253() { edge_distance_symmetric_impl(253); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000254() { edge_distance_symmetric_impl(254); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000255() { edge_distance_symmetric_impl(255); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000256() { edge_distance_symmetric_impl(256); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000257() { edge_distance_symmetric_impl(257); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000258() { edge_distance_symmetric_impl(258); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000259() { edge_distance_symmetric_impl(259); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000260() { edge_distance_symmetric_impl(260); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000261() { edge_distance_symmetric_impl(261); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000262() { edge_distance_symmetric_impl(262); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000263() { edge_distance_symmetric_impl(263); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000264() { edge_distance_symmetric_impl(264); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000265() { edge_distance_symmetric_impl(265); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000266() { edge_distance_symmetric_impl(266); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000267() { edge_distance_symmetric_impl(267); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000268() { edge_distance_symmetric_impl(268); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000269() { edge_distance_symmetric_impl(269); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000270() { edge_distance_symmetric_impl(270); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000271() { edge_distance_symmetric_impl(271); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000272() { edge_distance_symmetric_impl(272); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000273() { edge_distance_symmetric_impl(273); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000274() { edge_distance_symmetric_impl(274); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000275() { edge_distance_symmetric_impl(275); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000276() { edge_distance_symmetric_impl(276); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000277() { edge_distance_symmetric_impl(277); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000278() { edge_distance_symmetric_impl(278); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000279() { edge_distance_symmetric_impl(279); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000280() { edge_distance_symmetric_impl(280); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000281() { edge_distance_symmetric_impl(281); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000282() { edge_distance_symmetric_impl(282); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000283() { edge_distance_symmetric_impl(283); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000284() { edge_distance_symmetric_impl(284); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000285() { edge_distance_symmetric_impl(285); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000286() { edge_distance_symmetric_impl(286); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000287() { edge_distance_symmetric_impl(287); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000288() { edge_distance_symmetric_impl(288); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000289() { edge_distance_symmetric_impl(289); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000290() { edge_distance_symmetric_impl(290); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000291() { edge_distance_symmetric_impl(291); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000292() { edge_distance_symmetric_impl(292); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000293() { edge_distance_symmetric_impl(293); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000294() { edge_distance_symmetric_impl(294); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000295() { edge_distance_symmetric_impl(295); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000296() { edge_distance_symmetric_impl(296); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000297() { edge_distance_symmetric_impl(297); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000298() { edge_distance_symmetric_impl(298); }
    #[cfg_attr(test, test)]
    fn symmetric_seed_000299() { edge_distance_symmetric_impl(299); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000000() { edge_distance_translation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000001() { edge_distance_translation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000002() { edge_distance_translation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000003() { edge_distance_translation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000004() { edge_distance_translation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000005() { edge_distance_translation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000006() { edge_distance_translation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000007() { edge_distance_translation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000008() { edge_distance_translation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000009() { edge_distance_translation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000010() { edge_distance_translation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000011() { edge_distance_translation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000012() { edge_distance_translation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000013() { edge_distance_translation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000014() { edge_distance_translation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000015() { edge_distance_translation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000016() { edge_distance_translation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000017() { edge_distance_translation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000018() { edge_distance_translation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000019() { edge_distance_translation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000020() { edge_distance_translation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000021() { edge_distance_translation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000022() { edge_distance_translation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000023() { edge_distance_translation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000024() { edge_distance_translation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000025() { edge_distance_translation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000026() { edge_distance_translation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000027() { edge_distance_translation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000028() { edge_distance_translation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000029() { edge_distance_translation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000030() { edge_distance_translation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000031() { edge_distance_translation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000032() { edge_distance_translation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000033() { edge_distance_translation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000034() { edge_distance_translation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000035() { edge_distance_translation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000036() { edge_distance_translation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000037() { edge_distance_translation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000038() { edge_distance_translation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000039() { edge_distance_translation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000040() { edge_distance_translation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000041() { edge_distance_translation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000042() { edge_distance_translation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000043() { edge_distance_translation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000044() { edge_distance_translation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000045() { edge_distance_translation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000046() { edge_distance_translation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000047() { edge_distance_translation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000048() { edge_distance_translation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000049() { edge_distance_translation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000050() { edge_distance_translation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000051() { edge_distance_translation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000052() { edge_distance_translation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000053() { edge_distance_translation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000054() { edge_distance_translation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000055() { edge_distance_translation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000056() { edge_distance_translation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000057() { edge_distance_translation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000058() { edge_distance_translation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000059() { edge_distance_translation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000060() { edge_distance_translation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000061() { edge_distance_translation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000062() { edge_distance_translation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000063() { edge_distance_translation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000064() { edge_distance_translation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000065() { edge_distance_translation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000066() { edge_distance_translation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000067() { edge_distance_translation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000068() { edge_distance_translation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000069() { edge_distance_translation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000070() { edge_distance_translation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000071() { edge_distance_translation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000072() { edge_distance_translation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000073() { edge_distance_translation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000074() { edge_distance_translation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000075() { edge_distance_translation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000076() { edge_distance_translation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000077() { edge_distance_translation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000078() { edge_distance_translation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000079() { edge_distance_translation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000080() { edge_distance_translation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000081() { edge_distance_translation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000082() { edge_distance_translation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000083() { edge_distance_translation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000084() { edge_distance_translation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000085() { edge_distance_translation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000086() { edge_distance_translation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000087() { edge_distance_translation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000088() { edge_distance_translation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000089() { edge_distance_translation_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000090() { edge_distance_translation_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000091() { edge_distance_translation_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000092() { edge_distance_translation_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000093() { edge_distance_translation_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000094() { edge_distance_translation_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000095() { edge_distance_translation_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000096() { edge_distance_translation_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000097() { edge_distance_translation_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000098() { edge_distance_translation_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000099() { edge_distance_translation_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000100() { edge_distance_translation_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000101() { edge_distance_translation_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000102() { edge_distance_translation_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000103() { edge_distance_translation_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000104() { edge_distance_translation_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000105() { edge_distance_translation_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000106() { edge_distance_translation_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000107() { edge_distance_translation_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000108() { edge_distance_translation_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000109() { edge_distance_translation_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000110() { edge_distance_translation_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000111() { edge_distance_translation_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000112() { edge_distance_translation_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000113() { edge_distance_translation_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000114() { edge_distance_translation_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000115() { edge_distance_translation_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000116() { edge_distance_translation_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000117() { edge_distance_translation_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000118() { edge_distance_translation_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000119() { edge_distance_translation_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000120() { edge_distance_translation_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000121() { edge_distance_translation_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000122() { edge_distance_translation_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000123() { edge_distance_translation_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000124() { edge_distance_translation_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000125() { edge_distance_translation_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000126() { edge_distance_translation_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000127() { edge_distance_translation_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000128() { edge_distance_translation_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000129() { edge_distance_translation_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000130() { edge_distance_translation_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000131() { edge_distance_translation_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000132() { edge_distance_translation_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000133() { edge_distance_translation_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000134() { edge_distance_translation_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000135() { edge_distance_translation_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000136() { edge_distance_translation_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000137() { edge_distance_translation_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000138() { edge_distance_translation_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000139() { edge_distance_translation_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000140() { edge_distance_translation_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000141() { edge_distance_translation_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000142() { edge_distance_translation_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000143() { edge_distance_translation_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000144() { edge_distance_translation_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000145() { edge_distance_translation_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000146() { edge_distance_translation_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000147() { edge_distance_translation_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000148() { edge_distance_translation_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000149() { edge_distance_translation_invariant_impl(149); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000150() { edge_distance_translation_invariant_impl(150); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000151() { edge_distance_translation_invariant_impl(151); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000152() { edge_distance_translation_invariant_impl(152); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000153() { edge_distance_translation_invariant_impl(153); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000154() { edge_distance_translation_invariant_impl(154); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000155() { edge_distance_translation_invariant_impl(155); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000156() { edge_distance_translation_invariant_impl(156); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000157() { edge_distance_translation_invariant_impl(157); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000158() { edge_distance_translation_invariant_impl(158); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000159() { edge_distance_translation_invariant_impl(159); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000160() { edge_distance_translation_invariant_impl(160); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000161() { edge_distance_translation_invariant_impl(161); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000162() { edge_distance_translation_invariant_impl(162); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000163() { edge_distance_translation_invariant_impl(163); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000164() { edge_distance_translation_invariant_impl(164); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000165() { edge_distance_translation_invariant_impl(165); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000166() { edge_distance_translation_invariant_impl(166); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000167() { edge_distance_translation_invariant_impl(167); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000168() { edge_distance_translation_invariant_impl(168); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000169() { edge_distance_translation_invariant_impl(169); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000170() { edge_distance_translation_invariant_impl(170); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000171() { edge_distance_translation_invariant_impl(171); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000172() { edge_distance_translation_invariant_impl(172); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000173() { edge_distance_translation_invariant_impl(173); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000174() { edge_distance_translation_invariant_impl(174); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000175() { edge_distance_translation_invariant_impl(175); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000176() { edge_distance_translation_invariant_impl(176); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000177() { edge_distance_translation_invariant_impl(177); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000178() { edge_distance_translation_invariant_impl(178); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000179() { edge_distance_translation_invariant_impl(179); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000180() { edge_distance_translation_invariant_impl(180); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000181() { edge_distance_translation_invariant_impl(181); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000182() { edge_distance_translation_invariant_impl(182); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000183() { edge_distance_translation_invariant_impl(183); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000184() { edge_distance_translation_invariant_impl(184); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000185() { edge_distance_translation_invariant_impl(185); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000186() { edge_distance_translation_invariant_impl(186); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000187() { edge_distance_translation_invariant_impl(187); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000188() { edge_distance_translation_invariant_impl(188); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000189() { edge_distance_translation_invariant_impl(189); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000190() { edge_distance_translation_invariant_impl(190); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000191() { edge_distance_translation_invariant_impl(191); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000192() { edge_distance_translation_invariant_impl(192); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000193() { edge_distance_translation_invariant_impl(193); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000194() { edge_distance_translation_invariant_impl(194); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000195() { edge_distance_translation_invariant_impl(195); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000196() { edge_distance_translation_invariant_impl(196); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000197() { edge_distance_translation_invariant_impl(197); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000198() { edge_distance_translation_invariant_impl(198); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000199() { edge_distance_translation_invariant_impl(199); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000200() { edge_distance_translation_invariant_impl(200); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000201() { edge_distance_translation_invariant_impl(201); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000202() { edge_distance_translation_invariant_impl(202); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000203() { edge_distance_translation_invariant_impl(203); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000204() { edge_distance_translation_invariant_impl(204); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000205() { edge_distance_translation_invariant_impl(205); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000206() { edge_distance_translation_invariant_impl(206); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000207() { edge_distance_translation_invariant_impl(207); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000208() { edge_distance_translation_invariant_impl(208); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000209() { edge_distance_translation_invariant_impl(209); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000210() { edge_distance_translation_invariant_impl(210); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000211() { edge_distance_translation_invariant_impl(211); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000212() { edge_distance_translation_invariant_impl(212); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000213() { edge_distance_translation_invariant_impl(213); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000214() { edge_distance_translation_invariant_impl(214); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000215() { edge_distance_translation_invariant_impl(215); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000216() { edge_distance_translation_invariant_impl(216); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000217() { edge_distance_translation_invariant_impl(217); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000218() { edge_distance_translation_invariant_impl(218); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000219() { edge_distance_translation_invariant_impl(219); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000220() { edge_distance_translation_invariant_impl(220); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000221() { edge_distance_translation_invariant_impl(221); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000222() { edge_distance_translation_invariant_impl(222); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000223() { edge_distance_translation_invariant_impl(223); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000224() { edge_distance_translation_invariant_impl(224); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000225() { edge_distance_translation_invariant_impl(225); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000226() { edge_distance_translation_invariant_impl(226); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000227() { edge_distance_translation_invariant_impl(227); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000228() { edge_distance_translation_invariant_impl(228); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000229() { edge_distance_translation_invariant_impl(229); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000230() { edge_distance_translation_invariant_impl(230); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000231() { edge_distance_translation_invariant_impl(231); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000232() { edge_distance_translation_invariant_impl(232); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000233() { edge_distance_translation_invariant_impl(233); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000234() { edge_distance_translation_invariant_impl(234); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000235() { edge_distance_translation_invariant_impl(235); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000236() { edge_distance_translation_invariant_impl(236); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000237() { edge_distance_translation_invariant_impl(237); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000238() { edge_distance_translation_invariant_impl(238); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000239() { edge_distance_translation_invariant_impl(239); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000240() { edge_distance_translation_invariant_impl(240); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000241() { edge_distance_translation_invariant_impl(241); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000242() { edge_distance_translation_invariant_impl(242); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000243() { edge_distance_translation_invariant_impl(243); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000244() { edge_distance_translation_invariant_impl(244); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000245() { edge_distance_translation_invariant_impl(245); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000246() { edge_distance_translation_invariant_impl(246); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000247() { edge_distance_translation_invariant_impl(247); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000248() { edge_distance_translation_invariant_impl(248); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000249() { edge_distance_translation_invariant_impl(249); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000250() { edge_distance_translation_invariant_impl(250); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000251() { edge_distance_translation_invariant_impl(251); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000252() { edge_distance_translation_invariant_impl(252); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000253() { edge_distance_translation_invariant_impl(253); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000254() { edge_distance_translation_invariant_impl(254); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000255() { edge_distance_translation_invariant_impl(255); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000256() { edge_distance_translation_invariant_impl(256); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000257() { edge_distance_translation_invariant_impl(257); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000258() { edge_distance_translation_invariant_impl(258); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000259() { edge_distance_translation_invariant_impl(259); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000260() { edge_distance_translation_invariant_impl(260); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000261() { edge_distance_translation_invariant_impl(261); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000262() { edge_distance_translation_invariant_impl(262); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000263() { edge_distance_translation_invariant_impl(263); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000264() { edge_distance_translation_invariant_impl(264); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000265() { edge_distance_translation_invariant_impl(265); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000266() { edge_distance_translation_invariant_impl(266); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000267() { edge_distance_translation_invariant_impl(267); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000268() { edge_distance_translation_invariant_impl(268); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000269() { edge_distance_translation_invariant_impl(269); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000270() { edge_distance_translation_invariant_impl(270); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000271() { edge_distance_translation_invariant_impl(271); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000272() { edge_distance_translation_invariant_impl(272); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000273() { edge_distance_translation_invariant_impl(273); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000274() { edge_distance_translation_invariant_impl(274); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000275() { edge_distance_translation_invariant_impl(275); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000276() { edge_distance_translation_invariant_impl(276); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000277() { edge_distance_translation_invariant_impl(277); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000278() { edge_distance_translation_invariant_impl(278); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000279() { edge_distance_translation_invariant_impl(279); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000280() { edge_distance_translation_invariant_impl(280); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000281() { edge_distance_translation_invariant_impl(281); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000282() { edge_distance_translation_invariant_impl(282); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000283() { edge_distance_translation_invariant_impl(283); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000284() { edge_distance_translation_invariant_impl(284); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000285() { edge_distance_translation_invariant_impl(285); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000286() { edge_distance_translation_invariant_impl(286); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000287() { edge_distance_translation_invariant_impl(287); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000288() { edge_distance_translation_invariant_impl(288); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000289() { edge_distance_translation_invariant_impl(289); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000290() { edge_distance_translation_invariant_impl(290); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000291() { edge_distance_translation_invariant_impl(291); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000292() { edge_distance_translation_invariant_impl(292); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000293() { edge_distance_translation_invariant_impl(293); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000294() { edge_distance_translation_invariant_impl(294); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000295() { edge_distance_translation_invariant_impl(295); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000296() { edge_distance_translation_invariant_impl(296); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000297() { edge_distance_translation_invariant_impl(297); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000298() { edge_distance_translation_invariant_impl(298); }
    #[cfg_attr(test, test)]
    fn translation_invariant_seed_000299() { edge_distance_translation_invariant_impl(299); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000000() { edge_distance_rotation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000001() { edge_distance_rotation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000002() { edge_distance_rotation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000003() { edge_distance_rotation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000004() { edge_distance_rotation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000005() { edge_distance_rotation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000006() { edge_distance_rotation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000007() { edge_distance_rotation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000008() { edge_distance_rotation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000009() { edge_distance_rotation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000010() { edge_distance_rotation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000011() { edge_distance_rotation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000012() { edge_distance_rotation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000013() { edge_distance_rotation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000014() { edge_distance_rotation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000015() { edge_distance_rotation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000016() { edge_distance_rotation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000017() { edge_distance_rotation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000018() { edge_distance_rotation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000019() { edge_distance_rotation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000020() { edge_distance_rotation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000021() { edge_distance_rotation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000022() { edge_distance_rotation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000023() { edge_distance_rotation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000024() { edge_distance_rotation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000025() { edge_distance_rotation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000026() { edge_distance_rotation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000027() { edge_distance_rotation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000028() { edge_distance_rotation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000029() { edge_distance_rotation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000030() { edge_distance_rotation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000031() { edge_distance_rotation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000032() { edge_distance_rotation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000033() { edge_distance_rotation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000034() { edge_distance_rotation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000035() { edge_distance_rotation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000036() { edge_distance_rotation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000037() { edge_distance_rotation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000038() { edge_distance_rotation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000039() { edge_distance_rotation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000040() { edge_distance_rotation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000041() { edge_distance_rotation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000042() { edge_distance_rotation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000043() { edge_distance_rotation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000044() { edge_distance_rotation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000045() { edge_distance_rotation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000046() { edge_distance_rotation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000047() { edge_distance_rotation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000048() { edge_distance_rotation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000049() { edge_distance_rotation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000050() { edge_distance_rotation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000051() { edge_distance_rotation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000052() { edge_distance_rotation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000053() { edge_distance_rotation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000054() { edge_distance_rotation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000055() { edge_distance_rotation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000056() { edge_distance_rotation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000057() { edge_distance_rotation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000058() { edge_distance_rotation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000059() { edge_distance_rotation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000060() { edge_distance_rotation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000061() { edge_distance_rotation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000062() { edge_distance_rotation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000063() { edge_distance_rotation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000064() { edge_distance_rotation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000065() { edge_distance_rotation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000066() { edge_distance_rotation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000067() { edge_distance_rotation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000068() { edge_distance_rotation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000069() { edge_distance_rotation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000070() { edge_distance_rotation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000071() { edge_distance_rotation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000072() { edge_distance_rotation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000073() { edge_distance_rotation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000074() { edge_distance_rotation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000075() { edge_distance_rotation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000076() { edge_distance_rotation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000077() { edge_distance_rotation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000078() { edge_distance_rotation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000079() { edge_distance_rotation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000080() { edge_distance_rotation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000081() { edge_distance_rotation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000082() { edge_distance_rotation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000083() { edge_distance_rotation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000084() { edge_distance_rotation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000085() { edge_distance_rotation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000086() { edge_distance_rotation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000087() { edge_distance_rotation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000088() { edge_distance_rotation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000089() { edge_distance_rotation_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000090() { edge_distance_rotation_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000091() { edge_distance_rotation_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000092() { edge_distance_rotation_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000093() { edge_distance_rotation_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000094() { edge_distance_rotation_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000095() { edge_distance_rotation_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000096() { edge_distance_rotation_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000097() { edge_distance_rotation_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000098() { edge_distance_rotation_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000099() { edge_distance_rotation_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000100() { edge_distance_rotation_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000101() { edge_distance_rotation_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000102() { edge_distance_rotation_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000103() { edge_distance_rotation_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000104() { edge_distance_rotation_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000105() { edge_distance_rotation_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000106() { edge_distance_rotation_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000107() { edge_distance_rotation_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000108() { edge_distance_rotation_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000109() { edge_distance_rotation_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000110() { edge_distance_rotation_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000111() { edge_distance_rotation_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000112() { edge_distance_rotation_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000113() { edge_distance_rotation_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000114() { edge_distance_rotation_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000115() { edge_distance_rotation_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000116() { edge_distance_rotation_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000117() { edge_distance_rotation_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000118() { edge_distance_rotation_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000119() { edge_distance_rotation_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000120() { edge_distance_rotation_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000121() { edge_distance_rotation_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000122() { edge_distance_rotation_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000123() { edge_distance_rotation_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000124() { edge_distance_rotation_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000125() { edge_distance_rotation_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000126() { edge_distance_rotation_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000127() { edge_distance_rotation_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000128() { edge_distance_rotation_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000129() { edge_distance_rotation_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000130() { edge_distance_rotation_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000131() { edge_distance_rotation_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000132() { edge_distance_rotation_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000133() { edge_distance_rotation_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000134() { edge_distance_rotation_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000135() { edge_distance_rotation_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000136() { edge_distance_rotation_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000137() { edge_distance_rotation_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000138() { edge_distance_rotation_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000139() { edge_distance_rotation_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000140() { edge_distance_rotation_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000141() { edge_distance_rotation_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000142() { edge_distance_rotation_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000143() { edge_distance_rotation_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000144() { edge_distance_rotation_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000145() { edge_distance_rotation_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000146() { edge_distance_rotation_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000147() { edge_distance_rotation_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000148() { edge_distance_rotation_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000149() { edge_distance_rotation_invariant_impl(149); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000150() { edge_distance_rotation_invariant_impl(150); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000151() { edge_distance_rotation_invariant_impl(151); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000152() { edge_distance_rotation_invariant_impl(152); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000153() { edge_distance_rotation_invariant_impl(153); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000154() { edge_distance_rotation_invariant_impl(154); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000155() { edge_distance_rotation_invariant_impl(155); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000156() { edge_distance_rotation_invariant_impl(156); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000157() { edge_distance_rotation_invariant_impl(157); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000158() { edge_distance_rotation_invariant_impl(158); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000159() { edge_distance_rotation_invariant_impl(159); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000160() { edge_distance_rotation_invariant_impl(160); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000161() { edge_distance_rotation_invariant_impl(161); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000162() { edge_distance_rotation_invariant_impl(162); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000163() { edge_distance_rotation_invariant_impl(163); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000164() { edge_distance_rotation_invariant_impl(164); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000165() { edge_distance_rotation_invariant_impl(165); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000166() { edge_distance_rotation_invariant_impl(166); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000167() { edge_distance_rotation_invariant_impl(167); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000168() { edge_distance_rotation_invariant_impl(168); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000169() { edge_distance_rotation_invariant_impl(169); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000170() { edge_distance_rotation_invariant_impl(170); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000171() { edge_distance_rotation_invariant_impl(171); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000172() { edge_distance_rotation_invariant_impl(172); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000173() { edge_distance_rotation_invariant_impl(173); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000174() { edge_distance_rotation_invariant_impl(174); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000175() { edge_distance_rotation_invariant_impl(175); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000176() { edge_distance_rotation_invariant_impl(176); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000177() { edge_distance_rotation_invariant_impl(177); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000178() { edge_distance_rotation_invariant_impl(178); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000179() { edge_distance_rotation_invariant_impl(179); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000180() { edge_distance_rotation_invariant_impl(180); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000181() { edge_distance_rotation_invariant_impl(181); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000182() { edge_distance_rotation_invariant_impl(182); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000183() { edge_distance_rotation_invariant_impl(183); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000184() { edge_distance_rotation_invariant_impl(184); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000185() { edge_distance_rotation_invariant_impl(185); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000186() { edge_distance_rotation_invariant_impl(186); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000187() { edge_distance_rotation_invariant_impl(187); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000188() { edge_distance_rotation_invariant_impl(188); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000189() { edge_distance_rotation_invariant_impl(189); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000190() { edge_distance_rotation_invariant_impl(190); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000191() { edge_distance_rotation_invariant_impl(191); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000192() { edge_distance_rotation_invariant_impl(192); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000193() { edge_distance_rotation_invariant_impl(193); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000194() { edge_distance_rotation_invariant_impl(194); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000195() { edge_distance_rotation_invariant_impl(195); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000196() { edge_distance_rotation_invariant_impl(196); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000197() { edge_distance_rotation_invariant_impl(197); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000198() { edge_distance_rotation_invariant_impl(198); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000199() { edge_distance_rotation_invariant_impl(199); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000200() { edge_distance_rotation_invariant_impl(200); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000201() { edge_distance_rotation_invariant_impl(201); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000202() { edge_distance_rotation_invariant_impl(202); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000203() { edge_distance_rotation_invariant_impl(203); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000204() { edge_distance_rotation_invariant_impl(204); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000205() { edge_distance_rotation_invariant_impl(205); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000206() { edge_distance_rotation_invariant_impl(206); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000207() { edge_distance_rotation_invariant_impl(207); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000208() { edge_distance_rotation_invariant_impl(208); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000209() { edge_distance_rotation_invariant_impl(209); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000210() { edge_distance_rotation_invariant_impl(210); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000211() { edge_distance_rotation_invariant_impl(211); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000212() { edge_distance_rotation_invariant_impl(212); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000213() { edge_distance_rotation_invariant_impl(213); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000214() { edge_distance_rotation_invariant_impl(214); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000215() { edge_distance_rotation_invariant_impl(215); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000216() { edge_distance_rotation_invariant_impl(216); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000217() { edge_distance_rotation_invariant_impl(217); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000218() { edge_distance_rotation_invariant_impl(218); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000219() { edge_distance_rotation_invariant_impl(219); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000220() { edge_distance_rotation_invariant_impl(220); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000221() { edge_distance_rotation_invariant_impl(221); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000222() { edge_distance_rotation_invariant_impl(222); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000223() { edge_distance_rotation_invariant_impl(223); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000224() { edge_distance_rotation_invariant_impl(224); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000225() { edge_distance_rotation_invariant_impl(225); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000226() { edge_distance_rotation_invariant_impl(226); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000227() { edge_distance_rotation_invariant_impl(227); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000228() { edge_distance_rotation_invariant_impl(228); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000229() { edge_distance_rotation_invariant_impl(229); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000230() { edge_distance_rotation_invariant_impl(230); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000231() { edge_distance_rotation_invariant_impl(231); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000232() { edge_distance_rotation_invariant_impl(232); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000233() { edge_distance_rotation_invariant_impl(233); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000234() { edge_distance_rotation_invariant_impl(234); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000235() { edge_distance_rotation_invariant_impl(235); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000236() { edge_distance_rotation_invariant_impl(236); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000237() { edge_distance_rotation_invariant_impl(237); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000238() { edge_distance_rotation_invariant_impl(238); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000239() { edge_distance_rotation_invariant_impl(239); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000240() { edge_distance_rotation_invariant_impl(240); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000241() { edge_distance_rotation_invariant_impl(241); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000242() { edge_distance_rotation_invariant_impl(242); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000243() { edge_distance_rotation_invariant_impl(243); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000244() { edge_distance_rotation_invariant_impl(244); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000245() { edge_distance_rotation_invariant_impl(245); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000246() { edge_distance_rotation_invariant_impl(246); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000247() { edge_distance_rotation_invariant_impl(247); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000248() { edge_distance_rotation_invariant_impl(248); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000249() { edge_distance_rotation_invariant_impl(249); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000250() { edge_distance_rotation_invariant_impl(250); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000251() { edge_distance_rotation_invariant_impl(251); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000252() { edge_distance_rotation_invariant_impl(252); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000253() { edge_distance_rotation_invariant_impl(253); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000254() { edge_distance_rotation_invariant_impl(254); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000255() { edge_distance_rotation_invariant_impl(255); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000256() { edge_distance_rotation_invariant_impl(256); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000257() { edge_distance_rotation_invariant_impl(257); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000258() { edge_distance_rotation_invariant_impl(258); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000259() { edge_distance_rotation_invariant_impl(259); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000260() { edge_distance_rotation_invariant_impl(260); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000261() { edge_distance_rotation_invariant_impl(261); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000262() { edge_distance_rotation_invariant_impl(262); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000263() { edge_distance_rotation_invariant_impl(263); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000264() { edge_distance_rotation_invariant_impl(264); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000265() { edge_distance_rotation_invariant_impl(265); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000266() { edge_distance_rotation_invariant_impl(266); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000267() { edge_distance_rotation_invariant_impl(267); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000268() { edge_distance_rotation_invariant_impl(268); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000269() { edge_distance_rotation_invariant_impl(269); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000270() { edge_distance_rotation_invariant_impl(270); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000271() { edge_distance_rotation_invariant_impl(271); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000272() { edge_distance_rotation_invariant_impl(272); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000273() { edge_distance_rotation_invariant_impl(273); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000274() { edge_distance_rotation_invariant_impl(274); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000275() { edge_distance_rotation_invariant_impl(275); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000276() { edge_distance_rotation_invariant_impl(276); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000277() { edge_distance_rotation_invariant_impl(277); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000278() { edge_distance_rotation_invariant_impl(278); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000279() { edge_distance_rotation_invariant_impl(279); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000280() { edge_distance_rotation_invariant_impl(280); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000281() { edge_distance_rotation_invariant_impl(281); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000282() { edge_distance_rotation_invariant_impl(282); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000283() { edge_distance_rotation_invariant_impl(283); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000284() { edge_distance_rotation_invariant_impl(284); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000285() { edge_distance_rotation_invariant_impl(285); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000286() { edge_distance_rotation_invariant_impl(286); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000287() { edge_distance_rotation_invariant_impl(287); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000288() { edge_distance_rotation_invariant_impl(288); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000289() { edge_distance_rotation_invariant_impl(289); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000290() { edge_distance_rotation_invariant_impl(290); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000291() { edge_distance_rotation_invariant_impl(291); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000292() { edge_distance_rotation_invariant_impl(292); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000293() { edge_distance_rotation_invariant_impl(293); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000294() { edge_distance_rotation_invariant_impl(294); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000295() { edge_distance_rotation_invariant_impl(295); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000296() { edge_distance_rotation_invariant_impl(296); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000297() { edge_distance_rotation_invariant_impl(297); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000298() { edge_distance_rotation_invariant_impl(298); }
    #[cfg_attr(test, test)]
    fn rotation_invariant_seed_000299() { edge_distance_rotation_invariant_impl(299); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000000() { edge_distance_scale_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000001() { edge_distance_scale_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000002() { edge_distance_scale_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000003() { edge_distance_scale_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000004() { edge_distance_scale_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000005() { edge_distance_scale_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000006() { edge_distance_scale_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000007() { edge_distance_scale_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000008() { edge_distance_scale_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000009() { edge_distance_scale_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000010() { edge_distance_scale_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000011() { edge_distance_scale_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000012() { edge_distance_scale_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000013() { edge_distance_scale_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000014() { edge_distance_scale_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000015() { edge_distance_scale_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000016() { edge_distance_scale_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000017() { edge_distance_scale_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000018() { edge_distance_scale_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000019() { edge_distance_scale_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000020() { edge_distance_scale_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000021() { edge_distance_scale_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000022() { edge_distance_scale_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000023() { edge_distance_scale_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000024() { edge_distance_scale_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000025() { edge_distance_scale_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000026() { edge_distance_scale_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000027() { edge_distance_scale_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000028() { edge_distance_scale_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000029() { edge_distance_scale_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000030() { edge_distance_scale_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000031() { edge_distance_scale_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000032() { edge_distance_scale_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000033() { edge_distance_scale_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000034() { edge_distance_scale_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000035() { edge_distance_scale_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000036() { edge_distance_scale_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000037() { edge_distance_scale_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000038() { edge_distance_scale_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000039() { edge_distance_scale_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000040() { edge_distance_scale_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000041() { edge_distance_scale_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000042() { edge_distance_scale_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000043() { edge_distance_scale_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000044() { edge_distance_scale_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000045() { edge_distance_scale_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000046() { edge_distance_scale_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000047() { edge_distance_scale_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000048() { edge_distance_scale_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000049() { edge_distance_scale_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000050() { edge_distance_scale_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000051() { edge_distance_scale_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000052() { edge_distance_scale_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000053() { edge_distance_scale_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000054() { edge_distance_scale_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000055() { edge_distance_scale_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000056() { edge_distance_scale_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000057() { edge_distance_scale_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000058() { edge_distance_scale_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000059() { edge_distance_scale_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000060() { edge_distance_scale_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000061() { edge_distance_scale_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000062() { edge_distance_scale_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000063() { edge_distance_scale_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000064() { edge_distance_scale_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000065() { edge_distance_scale_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000066() { edge_distance_scale_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000067() { edge_distance_scale_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000068() { edge_distance_scale_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000069() { edge_distance_scale_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000070() { edge_distance_scale_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000071() { edge_distance_scale_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000072() { edge_distance_scale_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000073() { edge_distance_scale_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000074() { edge_distance_scale_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000075() { edge_distance_scale_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000076() { edge_distance_scale_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000077() { edge_distance_scale_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000078() { edge_distance_scale_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000079() { edge_distance_scale_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000080() { edge_distance_scale_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000081() { edge_distance_scale_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000082() { edge_distance_scale_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000083() { edge_distance_scale_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000084() { edge_distance_scale_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000085() { edge_distance_scale_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000086() { edge_distance_scale_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000087() { edge_distance_scale_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000088() { edge_distance_scale_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000089() { edge_distance_scale_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000090() { edge_distance_scale_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000091() { edge_distance_scale_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000092() { edge_distance_scale_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000093() { edge_distance_scale_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000094() { edge_distance_scale_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000095() { edge_distance_scale_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000096() { edge_distance_scale_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000097() { edge_distance_scale_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000098() { edge_distance_scale_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000099() { edge_distance_scale_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000100() { edge_distance_scale_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000101() { edge_distance_scale_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000102() { edge_distance_scale_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000103() { edge_distance_scale_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000104() { edge_distance_scale_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000105() { edge_distance_scale_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000106() { edge_distance_scale_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000107() { edge_distance_scale_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000108() { edge_distance_scale_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000109() { edge_distance_scale_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000110() { edge_distance_scale_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000111() { edge_distance_scale_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000112() { edge_distance_scale_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000113() { edge_distance_scale_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000114() { edge_distance_scale_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000115() { edge_distance_scale_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000116() { edge_distance_scale_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000117() { edge_distance_scale_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000118() { edge_distance_scale_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000119() { edge_distance_scale_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000120() { edge_distance_scale_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000121() { edge_distance_scale_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000122() { edge_distance_scale_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000123() { edge_distance_scale_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000124() { edge_distance_scale_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000125() { edge_distance_scale_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000126() { edge_distance_scale_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000127() { edge_distance_scale_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000128() { edge_distance_scale_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000129() { edge_distance_scale_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000130() { edge_distance_scale_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000131() { edge_distance_scale_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000132() { edge_distance_scale_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000133() { edge_distance_scale_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000134() { edge_distance_scale_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000135() { edge_distance_scale_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000136() { edge_distance_scale_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000137() { edge_distance_scale_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000138() { edge_distance_scale_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000139() { edge_distance_scale_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000140() { edge_distance_scale_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000141() { edge_distance_scale_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000142() { edge_distance_scale_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000143() { edge_distance_scale_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000144() { edge_distance_scale_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000145() { edge_distance_scale_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000146() { edge_distance_scale_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000147() { edge_distance_scale_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000148() { edge_distance_scale_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000149() { edge_distance_scale_invariant_impl(149); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000150() { edge_distance_scale_invariant_impl(150); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000151() { edge_distance_scale_invariant_impl(151); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000152() { edge_distance_scale_invariant_impl(152); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000153() { edge_distance_scale_invariant_impl(153); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000154() { edge_distance_scale_invariant_impl(154); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000155() { edge_distance_scale_invariant_impl(155); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000156() { edge_distance_scale_invariant_impl(156); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000157() { edge_distance_scale_invariant_impl(157); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000158() { edge_distance_scale_invariant_impl(158); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000159() { edge_distance_scale_invariant_impl(159); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000160() { edge_distance_scale_invariant_impl(160); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000161() { edge_distance_scale_invariant_impl(161); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000162() { edge_distance_scale_invariant_impl(162); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000163() { edge_distance_scale_invariant_impl(163); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000164() { edge_distance_scale_invariant_impl(164); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000165() { edge_distance_scale_invariant_impl(165); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000166() { edge_distance_scale_invariant_impl(166); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000167() { edge_distance_scale_invariant_impl(167); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000168() { edge_distance_scale_invariant_impl(168); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000169() { edge_distance_scale_invariant_impl(169); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000170() { edge_distance_scale_invariant_impl(170); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000171() { edge_distance_scale_invariant_impl(171); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000172() { edge_distance_scale_invariant_impl(172); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000173() { edge_distance_scale_invariant_impl(173); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000174() { edge_distance_scale_invariant_impl(174); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000175() { edge_distance_scale_invariant_impl(175); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000176() { edge_distance_scale_invariant_impl(176); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000177() { edge_distance_scale_invariant_impl(177); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000178() { edge_distance_scale_invariant_impl(178); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000179() { edge_distance_scale_invariant_impl(179); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000180() { edge_distance_scale_invariant_impl(180); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000181() { edge_distance_scale_invariant_impl(181); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000182() { edge_distance_scale_invariant_impl(182); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000183() { edge_distance_scale_invariant_impl(183); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000184() { edge_distance_scale_invariant_impl(184); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000185() { edge_distance_scale_invariant_impl(185); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000186() { edge_distance_scale_invariant_impl(186); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000187() { edge_distance_scale_invariant_impl(187); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000188() { edge_distance_scale_invariant_impl(188); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000189() { edge_distance_scale_invariant_impl(189); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000190() { edge_distance_scale_invariant_impl(190); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000191() { edge_distance_scale_invariant_impl(191); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000192() { edge_distance_scale_invariant_impl(192); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000193() { edge_distance_scale_invariant_impl(193); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000194() { edge_distance_scale_invariant_impl(194); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000195() { edge_distance_scale_invariant_impl(195); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000196() { edge_distance_scale_invariant_impl(196); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000197() { edge_distance_scale_invariant_impl(197); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000198() { edge_distance_scale_invariant_impl(198); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000199() { edge_distance_scale_invariant_impl(199); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000200() { edge_distance_scale_invariant_impl(200); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000201() { edge_distance_scale_invariant_impl(201); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000202() { edge_distance_scale_invariant_impl(202); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000203() { edge_distance_scale_invariant_impl(203); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000204() { edge_distance_scale_invariant_impl(204); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000205() { edge_distance_scale_invariant_impl(205); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000206() { edge_distance_scale_invariant_impl(206); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000207() { edge_distance_scale_invariant_impl(207); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000208() { edge_distance_scale_invariant_impl(208); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000209() { edge_distance_scale_invariant_impl(209); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000210() { edge_distance_scale_invariant_impl(210); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000211() { edge_distance_scale_invariant_impl(211); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000212() { edge_distance_scale_invariant_impl(212); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000213() { edge_distance_scale_invariant_impl(213); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000214() { edge_distance_scale_invariant_impl(214); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000215() { edge_distance_scale_invariant_impl(215); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000216() { edge_distance_scale_invariant_impl(216); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000217() { edge_distance_scale_invariant_impl(217); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000218() { edge_distance_scale_invariant_impl(218); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000219() { edge_distance_scale_invariant_impl(219); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000220() { edge_distance_scale_invariant_impl(220); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000221() { edge_distance_scale_invariant_impl(221); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000222() { edge_distance_scale_invariant_impl(222); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000223() { edge_distance_scale_invariant_impl(223); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000224() { edge_distance_scale_invariant_impl(224); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000225() { edge_distance_scale_invariant_impl(225); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000226() { edge_distance_scale_invariant_impl(226); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000227() { edge_distance_scale_invariant_impl(227); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000228() { edge_distance_scale_invariant_impl(228); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000229() { edge_distance_scale_invariant_impl(229); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000230() { edge_distance_scale_invariant_impl(230); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000231() { edge_distance_scale_invariant_impl(231); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000232() { edge_distance_scale_invariant_impl(232); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000233() { edge_distance_scale_invariant_impl(233); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000234() { edge_distance_scale_invariant_impl(234); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000235() { edge_distance_scale_invariant_impl(235); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000236() { edge_distance_scale_invariant_impl(236); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000237() { edge_distance_scale_invariant_impl(237); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000238() { edge_distance_scale_invariant_impl(238); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000239() { edge_distance_scale_invariant_impl(239); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000240() { edge_distance_scale_invariant_impl(240); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000241() { edge_distance_scale_invariant_impl(241); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000242() { edge_distance_scale_invariant_impl(242); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000243() { edge_distance_scale_invariant_impl(243); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000244() { edge_distance_scale_invariant_impl(244); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000245() { edge_distance_scale_invariant_impl(245); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000246() { edge_distance_scale_invariant_impl(246); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000247() { edge_distance_scale_invariant_impl(247); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000248() { edge_distance_scale_invariant_impl(248); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000249() { edge_distance_scale_invariant_impl(249); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000250() { edge_distance_scale_invariant_impl(250); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000251() { edge_distance_scale_invariant_impl(251); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000252() { edge_distance_scale_invariant_impl(252); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000253() { edge_distance_scale_invariant_impl(253); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000254() { edge_distance_scale_invariant_impl(254); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000255() { edge_distance_scale_invariant_impl(255); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000256() { edge_distance_scale_invariant_impl(256); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000257() { edge_distance_scale_invariant_impl(257); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000258() { edge_distance_scale_invariant_impl(258); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000259() { edge_distance_scale_invariant_impl(259); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000260() { edge_distance_scale_invariant_impl(260); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000261() { edge_distance_scale_invariant_impl(261); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000262() { edge_distance_scale_invariant_impl(262); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000263() { edge_distance_scale_invariant_impl(263); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000264() { edge_distance_scale_invariant_impl(264); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000265() { edge_distance_scale_invariant_impl(265); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000266() { edge_distance_scale_invariant_impl(266); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000267() { edge_distance_scale_invariant_impl(267); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000268() { edge_distance_scale_invariant_impl(268); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000269() { edge_distance_scale_invariant_impl(269); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000270() { edge_distance_scale_invariant_impl(270); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000271() { edge_distance_scale_invariant_impl(271); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000272() { edge_distance_scale_invariant_impl(272); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000273() { edge_distance_scale_invariant_impl(273); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000274() { edge_distance_scale_invariant_impl(274); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000275() { edge_distance_scale_invariant_impl(275); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000276() { edge_distance_scale_invariant_impl(276); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000277() { edge_distance_scale_invariant_impl(277); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000278() { edge_distance_scale_invariant_impl(278); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000279() { edge_distance_scale_invariant_impl(279); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000280() { edge_distance_scale_invariant_impl(280); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000281() { edge_distance_scale_invariant_impl(281); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000282() { edge_distance_scale_invariant_impl(282); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000283() { edge_distance_scale_invariant_impl(283); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000284() { edge_distance_scale_invariant_impl(284); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000285() { edge_distance_scale_invariant_impl(285); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000286() { edge_distance_scale_invariant_impl(286); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000287() { edge_distance_scale_invariant_impl(287); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000288() { edge_distance_scale_invariant_impl(288); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000289() { edge_distance_scale_invariant_impl(289); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000290() { edge_distance_scale_invariant_impl(290); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000291() { edge_distance_scale_invariant_impl(291); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000292() { edge_distance_scale_invariant_impl(292); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000293() { edge_distance_scale_invariant_impl(293); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000294() { edge_distance_scale_invariant_impl(294); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000295() { edge_distance_scale_invariant_impl(295); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000296() { edge_distance_scale_invariant_impl(296); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000297() { edge_distance_scale_invariant_impl(297); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000298() { edge_distance_scale_invariant_impl(298); }
    #[cfg_attr(test, test)]
    fn scale_invariant_seed_000299() { edge_distance_scale_invariant_impl(299); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000000() { edge_distance_naive_reference_agreement_impl(0); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000001() { edge_distance_naive_reference_agreement_impl(1); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000002() { edge_distance_naive_reference_agreement_impl(2); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000003() { edge_distance_naive_reference_agreement_impl(3); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000004() { edge_distance_naive_reference_agreement_impl(4); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000005() { edge_distance_naive_reference_agreement_impl(5); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000006() { edge_distance_naive_reference_agreement_impl(6); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000007() { edge_distance_naive_reference_agreement_impl(7); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000008() { edge_distance_naive_reference_agreement_impl(8); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000009() { edge_distance_naive_reference_agreement_impl(9); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000010() { edge_distance_naive_reference_agreement_impl(10); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000011() { edge_distance_naive_reference_agreement_impl(11); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000012() { edge_distance_naive_reference_agreement_impl(12); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000013() { edge_distance_naive_reference_agreement_impl(13); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000014() { edge_distance_naive_reference_agreement_impl(14); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000015() { edge_distance_naive_reference_agreement_impl(15); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000016() { edge_distance_naive_reference_agreement_impl(16); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000017() { edge_distance_naive_reference_agreement_impl(17); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000018() { edge_distance_naive_reference_agreement_impl(18); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000019() { edge_distance_naive_reference_agreement_impl(19); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000020() { edge_distance_naive_reference_agreement_impl(20); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000021() { edge_distance_naive_reference_agreement_impl(21); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000022() { edge_distance_naive_reference_agreement_impl(22); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000023() { edge_distance_naive_reference_agreement_impl(23); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000024() { edge_distance_naive_reference_agreement_impl(24); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000025() { edge_distance_naive_reference_agreement_impl(25); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000026() { edge_distance_naive_reference_agreement_impl(26); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000027() { edge_distance_naive_reference_agreement_impl(27); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000028() { edge_distance_naive_reference_agreement_impl(28); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000029() { edge_distance_naive_reference_agreement_impl(29); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000030() { edge_distance_naive_reference_agreement_impl(30); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000031() { edge_distance_naive_reference_agreement_impl(31); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000032() { edge_distance_naive_reference_agreement_impl(32); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000033() { edge_distance_naive_reference_agreement_impl(33); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000034() { edge_distance_naive_reference_agreement_impl(34); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000035() { edge_distance_naive_reference_agreement_impl(35); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000036() { edge_distance_naive_reference_agreement_impl(36); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000037() { edge_distance_naive_reference_agreement_impl(37); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000038() { edge_distance_naive_reference_agreement_impl(38); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000039() { edge_distance_naive_reference_agreement_impl(39); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000040() { edge_distance_naive_reference_agreement_impl(40); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000041() { edge_distance_naive_reference_agreement_impl(41); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000042() { edge_distance_naive_reference_agreement_impl(42); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000043() { edge_distance_naive_reference_agreement_impl(43); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000044() { edge_distance_naive_reference_agreement_impl(44); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000045() { edge_distance_naive_reference_agreement_impl(45); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000046() { edge_distance_naive_reference_agreement_impl(46); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000047() { edge_distance_naive_reference_agreement_impl(47); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000048() { edge_distance_naive_reference_agreement_impl(48); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000049() { edge_distance_naive_reference_agreement_impl(49); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000050() { edge_distance_naive_reference_agreement_impl(50); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000051() { edge_distance_naive_reference_agreement_impl(51); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000052() { edge_distance_naive_reference_agreement_impl(52); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000053() { edge_distance_naive_reference_agreement_impl(53); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000054() { edge_distance_naive_reference_agreement_impl(54); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000055() { edge_distance_naive_reference_agreement_impl(55); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000056() { edge_distance_naive_reference_agreement_impl(56); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000057() { edge_distance_naive_reference_agreement_impl(57); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000058() { edge_distance_naive_reference_agreement_impl(58); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000059() { edge_distance_naive_reference_agreement_impl(59); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000060() { edge_distance_naive_reference_agreement_impl(60); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000061() { edge_distance_naive_reference_agreement_impl(61); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000062() { edge_distance_naive_reference_agreement_impl(62); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000063() { edge_distance_naive_reference_agreement_impl(63); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000064() { edge_distance_naive_reference_agreement_impl(64); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000065() { edge_distance_naive_reference_agreement_impl(65); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000066() { edge_distance_naive_reference_agreement_impl(66); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000067() { edge_distance_naive_reference_agreement_impl(67); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000068() { edge_distance_naive_reference_agreement_impl(68); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000069() { edge_distance_naive_reference_agreement_impl(69); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000070() { edge_distance_naive_reference_agreement_impl(70); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000071() { edge_distance_naive_reference_agreement_impl(71); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000072() { edge_distance_naive_reference_agreement_impl(72); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000073() { edge_distance_naive_reference_agreement_impl(73); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000074() { edge_distance_naive_reference_agreement_impl(74); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000075() { edge_distance_naive_reference_agreement_impl(75); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000076() { edge_distance_naive_reference_agreement_impl(76); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000077() { edge_distance_naive_reference_agreement_impl(77); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000078() { edge_distance_naive_reference_agreement_impl(78); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000079() { edge_distance_naive_reference_agreement_impl(79); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000080() { edge_distance_naive_reference_agreement_impl(80); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000081() { edge_distance_naive_reference_agreement_impl(81); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000082() { edge_distance_naive_reference_agreement_impl(82); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000083() { edge_distance_naive_reference_agreement_impl(83); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000084() { edge_distance_naive_reference_agreement_impl(84); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000085() { edge_distance_naive_reference_agreement_impl(85); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000086() { edge_distance_naive_reference_agreement_impl(86); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000087() { edge_distance_naive_reference_agreement_impl(87); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000088() { edge_distance_naive_reference_agreement_impl(88); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000089() { edge_distance_naive_reference_agreement_impl(89); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000090() { edge_distance_naive_reference_agreement_impl(90); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000091() { edge_distance_naive_reference_agreement_impl(91); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000092() { edge_distance_naive_reference_agreement_impl(92); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000093() { edge_distance_naive_reference_agreement_impl(93); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000094() { edge_distance_naive_reference_agreement_impl(94); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000095() { edge_distance_naive_reference_agreement_impl(95); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000096() { edge_distance_naive_reference_agreement_impl(96); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000097() { edge_distance_naive_reference_agreement_impl(97); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000098() { edge_distance_naive_reference_agreement_impl(98); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000099() { edge_distance_naive_reference_agreement_impl(99); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000100() { edge_distance_naive_reference_agreement_impl(100); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000101() { edge_distance_naive_reference_agreement_impl(101); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000102() { edge_distance_naive_reference_agreement_impl(102); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000103() { edge_distance_naive_reference_agreement_impl(103); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000104() { edge_distance_naive_reference_agreement_impl(104); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000105() { edge_distance_naive_reference_agreement_impl(105); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000106() { edge_distance_naive_reference_agreement_impl(106); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000107() { edge_distance_naive_reference_agreement_impl(107); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000108() { edge_distance_naive_reference_agreement_impl(108); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000109() { edge_distance_naive_reference_agreement_impl(109); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000110() { edge_distance_naive_reference_agreement_impl(110); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000111() { edge_distance_naive_reference_agreement_impl(111); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000112() { edge_distance_naive_reference_agreement_impl(112); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000113() { edge_distance_naive_reference_agreement_impl(113); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000114() { edge_distance_naive_reference_agreement_impl(114); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000115() { edge_distance_naive_reference_agreement_impl(115); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000116() { edge_distance_naive_reference_agreement_impl(116); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000117() { edge_distance_naive_reference_agreement_impl(117); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000118() { edge_distance_naive_reference_agreement_impl(118); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000119() { edge_distance_naive_reference_agreement_impl(119); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000120() { edge_distance_naive_reference_agreement_impl(120); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000121() { edge_distance_naive_reference_agreement_impl(121); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000122() { edge_distance_naive_reference_agreement_impl(122); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000123() { edge_distance_naive_reference_agreement_impl(123); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000124() { edge_distance_naive_reference_agreement_impl(124); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000125() { edge_distance_naive_reference_agreement_impl(125); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000126() { edge_distance_naive_reference_agreement_impl(126); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000127() { edge_distance_naive_reference_agreement_impl(127); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000128() { edge_distance_naive_reference_agreement_impl(128); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000129() { edge_distance_naive_reference_agreement_impl(129); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000130() { edge_distance_naive_reference_agreement_impl(130); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000131() { edge_distance_naive_reference_agreement_impl(131); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000132() { edge_distance_naive_reference_agreement_impl(132); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000133() { edge_distance_naive_reference_agreement_impl(133); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000134() { edge_distance_naive_reference_agreement_impl(134); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000135() { edge_distance_naive_reference_agreement_impl(135); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000136() { edge_distance_naive_reference_agreement_impl(136); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000137() { edge_distance_naive_reference_agreement_impl(137); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000138() { edge_distance_naive_reference_agreement_impl(138); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000139() { edge_distance_naive_reference_agreement_impl(139); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000140() { edge_distance_naive_reference_agreement_impl(140); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000141() { edge_distance_naive_reference_agreement_impl(141); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000142() { edge_distance_naive_reference_agreement_impl(142); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000143() { edge_distance_naive_reference_agreement_impl(143); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000144() { edge_distance_naive_reference_agreement_impl(144); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000145() { edge_distance_naive_reference_agreement_impl(145); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000146() { edge_distance_naive_reference_agreement_impl(146); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000147() { edge_distance_naive_reference_agreement_impl(147); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000148() { edge_distance_naive_reference_agreement_impl(148); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000149() { edge_distance_naive_reference_agreement_impl(149); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000150() { edge_distance_naive_reference_agreement_impl(150); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000151() { edge_distance_naive_reference_agreement_impl(151); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000152() { edge_distance_naive_reference_agreement_impl(152); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000153() { edge_distance_naive_reference_agreement_impl(153); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000154() { edge_distance_naive_reference_agreement_impl(154); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000155() { edge_distance_naive_reference_agreement_impl(155); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000156() { edge_distance_naive_reference_agreement_impl(156); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000157() { edge_distance_naive_reference_agreement_impl(157); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000158() { edge_distance_naive_reference_agreement_impl(158); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000159() { edge_distance_naive_reference_agreement_impl(159); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000160() { edge_distance_naive_reference_agreement_impl(160); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000161() { edge_distance_naive_reference_agreement_impl(161); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000162() { edge_distance_naive_reference_agreement_impl(162); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000163() { edge_distance_naive_reference_agreement_impl(163); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000164() { edge_distance_naive_reference_agreement_impl(164); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000165() { edge_distance_naive_reference_agreement_impl(165); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000166() { edge_distance_naive_reference_agreement_impl(166); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000167() { edge_distance_naive_reference_agreement_impl(167); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000168() { edge_distance_naive_reference_agreement_impl(168); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000169() { edge_distance_naive_reference_agreement_impl(169); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000170() { edge_distance_naive_reference_agreement_impl(170); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000171() { edge_distance_naive_reference_agreement_impl(171); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000172() { edge_distance_naive_reference_agreement_impl(172); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000173() { edge_distance_naive_reference_agreement_impl(173); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000174() { edge_distance_naive_reference_agreement_impl(174); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000175() { edge_distance_naive_reference_agreement_impl(175); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000176() { edge_distance_naive_reference_agreement_impl(176); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000177() { edge_distance_naive_reference_agreement_impl(177); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000178() { edge_distance_naive_reference_agreement_impl(178); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000179() { edge_distance_naive_reference_agreement_impl(179); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000180() { edge_distance_naive_reference_agreement_impl(180); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000181() { edge_distance_naive_reference_agreement_impl(181); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000182() { edge_distance_naive_reference_agreement_impl(182); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000183() { edge_distance_naive_reference_agreement_impl(183); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000184() { edge_distance_naive_reference_agreement_impl(184); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000185() { edge_distance_naive_reference_agreement_impl(185); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000186() { edge_distance_naive_reference_agreement_impl(186); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000187() { edge_distance_naive_reference_agreement_impl(187); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000188() { edge_distance_naive_reference_agreement_impl(188); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000189() { edge_distance_naive_reference_agreement_impl(189); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000190() { edge_distance_naive_reference_agreement_impl(190); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000191() { edge_distance_naive_reference_agreement_impl(191); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000192() { edge_distance_naive_reference_agreement_impl(192); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000193() { edge_distance_naive_reference_agreement_impl(193); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000194() { edge_distance_naive_reference_agreement_impl(194); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000195() { edge_distance_naive_reference_agreement_impl(195); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000196() { edge_distance_naive_reference_agreement_impl(196); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000197() { edge_distance_naive_reference_agreement_impl(197); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000198() { edge_distance_naive_reference_agreement_impl(198); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000199() { edge_distance_naive_reference_agreement_impl(199); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000200() { edge_distance_naive_reference_agreement_impl(200); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000201() { edge_distance_naive_reference_agreement_impl(201); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000202() { edge_distance_naive_reference_agreement_impl(202); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000203() { edge_distance_naive_reference_agreement_impl(203); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000204() { edge_distance_naive_reference_agreement_impl(204); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000205() { edge_distance_naive_reference_agreement_impl(205); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000206() { edge_distance_naive_reference_agreement_impl(206); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000207() { edge_distance_naive_reference_agreement_impl(207); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000208() { edge_distance_naive_reference_agreement_impl(208); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000209() { edge_distance_naive_reference_agreement_impl(209); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000210() { edge_distance_naive_reference_agreement_impl(210); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000211() { edge_distance_naive_reference_agreement_impl(211); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000212() { edge_distance_naive_reference_agreement_impl(212); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000213() { edge_distance_naive_reference_agreement_impl(213); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000214() { edge_distance_naive_reference_agreement_impl(214); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000215() { edge_distance_naive_reference_agreement_impl(215); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000216() { edge_distance_naive_reference_agreement_impl(216); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000217() { edge_distance_naive_reference_agreement_impl(217); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000218() { edge_distance_naive_reference_agreement_impl(218); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000219() { edge_distance_naive_reference_agreement_impl(219); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000220() { edge_distance_naive_reference_agreement_impl(220); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000221() { edge_distance_naive_reference_agreement_impl(221); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000222() { edge_distance_naive_reference_agreement_impl(222); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000223() { edge_distance_naive_reference_agreement_impl(223); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000224() { edge_distance_naive_reference_agreement_impl(224); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000225() { edge_distance_naive_reference_agreement_impl(225); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000226() { edge_distance_naive_reference_agreement_impl(226); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000227() { edge_distance_naive_reference_agreement_impl(227); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000228() { edge_distance_naive_reference_agreement_impl(228); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000229() { edge_distance_naive_reference_agreement_impl(229); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000230() { edge_distance_naive_reference_agreement_impl(230); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000231() { edge_distance_naive_reference_agreement_impl(231); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000232() { edge_distance_naive_reference_agreement_impl(232); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000233() { edge_distance_naive_reference_agreement_impl(233); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000234() { edge_distance_naive_reference_agreement_impl(234); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000235() { edge_distance_naive_reference_agreement_impl(235); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000236() { edge_distance_naive_reference_agreement_impl(236); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000237() { edge_distance_naive_reference_agreement_impl(237); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000238() { edge_distance_naive_reference_agreement_impl(238); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000239() { edge_distance_naive_reference_agreement_impl(239); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000240() { edge_distance_naive_reference_agreement_impl(240); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000241() { edge_distance_naive_reference_agreement_impl(241); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000242() { edge_distance_naive_reference_agreement_impl(242); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000243() { edge_distance_naive_reference_agreement_impl(243); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000244() { edge_distance_naive_reference_agreement_impl(244); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000245() { edge_distance_naive_reference_agreement_impl(245); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000246() { edge_distance_naive_reference_agreement_impl(246); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000247() { edge_distance_naive_reference_agreement_impl(247); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000248() { edge_distance_naive_reference_agreement_impl(248); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000249() { edge_distance_naive_reference_agreement_impl(249); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000250() { edge_distance_naive_reference_agreement_impl(250); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000251() { edge_distance_naive_reference_agreement_impl(251); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000252() { edge_distance_naive_reference_agreement_impl(252); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000253() { edge_distance_naive_reference_agreement_impl(253); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000254() { edge_distance_naive_reference_agreement_impl(254); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000255() { edge_distance_naive_reference_agreement_impl(255); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000256() { edge_distance_naive_reference_agreement_impl(256); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000257() { edge_distance_naive_reference_agreement_impl(257); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000258() { edge_distance_naive_reference_agreement_impl(258); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000259() { edge_distance_naive_reference_agreement_impl(259); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000260() { edge_distance_naive_reference_agreement_impl(260); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000261() { edge_distance_naive_reference_agreement_impl(261); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000262() { edge_distance_naive_reference_agreement_impl(262); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000263() { edge_distance_naive_reference_agreement_impl(263); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000264() { edge_distance_naive_reference_agreement_impl(264); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000265() { edge_distance_naive_reference_agreement_impl(265); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000266() { edge_distance_naive_reference_agreement_impl(266); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000267() { edge_distance_naive_reference_agreement_impl(267); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000268() { edge_distance_naive_reference_agreement_impl(268); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000269() { edge_distance_naive_reference_agreement_impl(269); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000270() { edge_distance_naive_reference_agreement_impl(270); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000271() { edge_distance_naive_reference_agreement_impl(271); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000272() { edge_distance_naive_reference_agreement_impl(272); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000273() { edge_distance_naive_reference_agreement_impl(273); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000274() { edge_distance_naive_reference_agreement_impl(274); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000275() { edge_distance_naive_reference_agreement_impl(275); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000276() { edge_distance_naive_reference_agreement_impl(276); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000277() { edge_distance_naive_reference_agreement_impl(277); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000278() { edge_distance_naive_reference_agreement_impl(278); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000279() { edge_distance_naive_reference_agreement_impl(279); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000280() { edge_distance_naive_reference_agreement_impl(280); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000281() { edge_distance_naive_reference_agreement_impl(281); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000282() { edge_distance_naive_reference_agreement_impl(282); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000283() { edge_distance_naive_reference_agreement_impl(283); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000284() { edge_distance_naive_reference_agreement_impl(284); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000285() { edge_distance_naive_reference_agreement_impl(285); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000286() { edge_distance_naive_reference_agreement_impl(286); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000287() { edge_distance_naive_reference_agreement_impl(287); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000288() { edge_distance_naive_reference_agreement_impl(288); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000289() { edge_distance_naive_reference_agreement_impl(289); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000290() { edge_distance_naive_reference_agreement_impl(290); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000291() { edge_distance_naive_reference_agreement_impl(291); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000292() { edge_distance_naive_reference_agreement_impl(292); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000293() { edge_distance_naive_reference_agreement_impl(293); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000294() { edge_distance_naive_reference_agreement_impl(294); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000295() { edge_distance_naive_reference_agreement_impl(295); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000296() { edge_distance_naive_reference_agreement_impl(296); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000297() { edge_distance_naive_reference_agreement_impl(297); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000298() { edge_distance_naive_reference_agreement_impl(298); }
    #[cfg_attr(test, test)]
    fn naive_reference_agreement_seed_000299() { edge_distance_naive_reference_agreement_impl(299); }
    // --- END generated seeded property wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::drc::property_campaigns::tests::gen_case_is_deterministic_in_seed", gen_case_is_deterministic_in_seed),
        ("rules::drc::property_campaigns::tests::gen_case_varies_with_seed", gen_case_varies_with_seed),
        ("rules::drc::property_campaigns::tests::naive_closest_agrees_on_disjoint_unit_squares", naive_closest_agrees_on_disjoint_unit_squares),
        ("rules::drc::property_campaigns::tests::naive_closest_zero_for_touching_squares", naive_closest_zero_for_touching_squares),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000000", symmetric_seed_000000),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000001", symmetric_seed_000001),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000002", symmetric_seed_000002),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000003", symmetric_seed_000003),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000004", symmetric_seed_000004),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000005", symmetric_seed_000005),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000006", symmetric_seed_000006),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000007", symmetric_seed_000007),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000008", symmetric_seed_000008),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000009", symmetric_seed_000009),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000010", symmetric_seed_000010),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000011", symmetric_seed_000011),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000012", symmetric_seed_000012),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000013", symmetric_seed_000013),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000014", symmetric_seed_000014),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000015", symmetric_seed_000015),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000016", symmetric_seed_000016),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000017", symmetric_seed_000017),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000018", symmetric_seed_000018),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000019", symmetric_seed_000019),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000020", symmetric_seed_000020),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000021", symmetric_seed_000021),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000022", symmetric_seed_000022),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000023", symmetric_seed_000023),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000024", symmetric_seed_000024),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000025", symmetric_seed_000025),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000026", symmetric_seed_000026),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000027", symmetric_seed_000027),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000028", symmetric_seed_000028),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000029", symmetric_seed_000029),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000030", symmetric_seed_000030),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000031", symmetric_seed_000031),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000032", symmetric_seed_000032),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000033", symmetric_seed_000033),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000034", symmetric_seed_000034),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000035", symmetric_seed_000035),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000036", symmetric_seed_000036),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000037", symmetric_seed_000037),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000038", symmetric_seed_000038),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000039", symmetric_seed_000039),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000040", symmetric_seed_000040),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000041", symmetric_seed_000041),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000042", symmetric_seed_000042),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000043", symmetric_seed_000043),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000044", symmetric_seed_000044),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000045", symmetric_seed_000045),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000046", symmetric_seed_000046),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000047", symmetric_seed_000047),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000048", symmetric_seed_000048),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000049", symmetric_seed_000049),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000050", symmetric_seed_000050),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000051", symmetric_seed_000051),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000052", symmetric_seed_000052),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000053", symmetric_seed_000053),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000054", symmetric_seed_000054),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000055", symmetric_seed_000055),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000056", symmetric_seed_000056),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000057", symmetric_seed_000057),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000058", symmetric_seed_000058),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000059", symmetric_seed_000059),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000060", symmetric_seed_000060),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000061", symmetric_seed_000061),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000062", symmetric_seed_000062),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000063", symmetric_seed_000063),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000064", symmetric_seed_000064),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000065", symmetric_seed_000065),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000066", symmetric_seed_000066),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000067", symmetric_seed_000067),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000068", symmetric_seed_000068),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000069", symmetric_seed_000069),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000070", symmetric_seed_000070),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000071", symmetric_seed_000071),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000072", symmetric_seed_000072),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000073", symmetric_seed_000073),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000074", symmetric_seed_000074),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000075", symmetric_seed_000075),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000076", symmetric_seed_000076),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000077", symmetric_seed_000077),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000078", symmetric_seed_000078),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000079", symmetric_seed_000079),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000080", symmetric_seed_000080),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000081", symmetric_seed_000081),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000082", symmetric_seed_000082),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000083", symmetric_seed_000083),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000084", symmetric_seed_000084),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000085", symmetric_seed_000085),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000086", symmetric_seed_000086),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000087", symmetric_seed_000087),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000088", symmetric_seed_000088),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000089", symmetric_seed_000089),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000090", symmetric_seed_000090),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000091", symmetric_seed_000091),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000092", symmetric_seed_000092),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000093", symmetric_seed_000093),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000094", symmetric_seed_000094),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000095", symmetric_seed_000095),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000096", symmetric_seed_000096),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000097", symmetric_seed_000097),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000098", symmetric_seed_000098),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000099", symmetric_seed_000099),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000100", symmetric_seed_000100),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000101", symmetric_seed_000101),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000102", symmetric_seed_000102),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000103", symmetric_seed_000103),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000104", symmetric_seed_000104),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000105", symmetric_seed_000105),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000106", symmetric_seed_000106),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000107", symmetric_seed_000107),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000108", symmetric_seed_000108),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000109", symmetric_seed_000109),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000110", symmetric_seed_000110),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000111", symmetric_seed_000111),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000112", symmetric_seed_000112),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000113", symmetric_seed_000113),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000114", symmetric_seed_000114),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000115", symmetric_seed_000115),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000116", symmetric_seed_000116),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000117", symmetric_seed_000117),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000118", symmetric_seed_000118),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000119", symmetric_seed_000119),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000120", symmetric_seed_000120),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000121", symmetric_seed_000121),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000122", symmetric_seed_000122),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000123", symmetric_seed_000123),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000124", symmetric_seed_000124),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000125", symmetric_seed_000125),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000126", symmetric_seed_000126),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000127", symmetric_seed_000127),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000128", symmetric_seed_000128),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000129", symmetric_seed_000129),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000130", symmetric_seed_000130),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000131", symmetric_seed_000131),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000132", symmetric_seed_000132),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000133", symmetric_seed_000133),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000134", symmetric_seed_000134),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000135", symmetric_seed_000135),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000136", symmetric_seed_000136),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000137", symmetric_seed_000137),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000138", symmetric_seed_000138),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000139", symmetric_seed_000139),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000140", symmetric_seed_000140),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000141", symmetric_seed_000141),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000142", symmetric_seed_000142),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000143", symmetric_seed_000143),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000144", symmetric_seed_000144),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000145", symmetric_seed_000145),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000146", symmetric_seed_000146),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000147", symmetric_seed_000147),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000148", symmetric_seed_000148),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000149", symmetric_seed_000149),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000150", symmetric_seed_000150),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000151", symmetric_seed_000151),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000152", symmetric_seed_000152),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000153", symmetric_seed_000153),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000154", symmetric_seed_000154),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000155", symmetric_seed_000155),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000156", symmetric_seed_000156),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000157", symmetric_seed_000157),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000158", symmetric_seed_000158),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000159", symmetric_seed_000159),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000160", symmetric_seed_000160),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000161", symmetric_seed_000161),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000162", symmetric_seed_000162),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000163", symmetric_seed_000163),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000164", symmetric_seed_000164),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000165", symmetric_seed_000165),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000166", symmetric_seed_000166),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000167", symmetric_seed_000167),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000168", symmetric_seed_000168),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000169", symmetric_seed_000169),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000170", symmetric_seed_000170),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000171", symmetric_seed_000171),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000172", symmetric_seed_000172),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000173", symmetric_seed_000173),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000174", symmetric_seed_000174),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000175", symmetric_seed_000175),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000176", symmetric_seed_000176),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000177", symmetric_seed_000177),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000178", symmetric_seed_000178),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000179", symmetric_seed_000179),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000180", symmetric_seed_000180),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000181", symmetric_seed_000181),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000182", symmetric_seed_000182),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000183", symmetric_seed_000183),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000184", symmetric_seed_000184),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000185", symmetric_seed_000185),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000186", symmetric_seed_000186),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000187", symmetric_seed_000187),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000188", symmetric_seed_000188),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000189", symmetric_seed_000189),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000190", symmetric_seed_000190),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000191", symmetric_seed_000191),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000192", symmetric_seed_000192),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000193", symmetric_seed_000193),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000194", symmetric_seed_000194),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000195", symmetric_seed_000195),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000196", symmetric_seed_000196),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000197", symmetric_seed_000197),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000198", symmetric_seed_000198),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000199", symmetric_seed_000199),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000200", symmetric_seed_000200),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000201", symmetric_seed_000201),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000202", symmetric_seed_000202),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000203", symmetric_seed_000203),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000204", symmetric_seed_000204),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000205", symmetric_seed_000205),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000206", symmetric_seed_000206),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000207", symmetric_seed_000207),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000208", symmetric_seed_000208),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000209", symmetric_seed_000209),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000210", symmetric_seed_000210),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000211", symmetric_seed_000211),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000212", symmetric_seed_000212),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000213", symmetric_seed_000213),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000214", symmetric_seed_000214),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000215", symmetric_seed_000215),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000216", symmetric_seed_000216),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000217", symmetric_seed_000217),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000218", symmetric_seed_000218),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000219", symmetric_seed_000219),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000220", symmetric_seed_000220),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000221", symmetric_seed_000221),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000222", symmetric_seed_000222),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000223", symmetric_seed_000223),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000224", symmetric_seed_000224),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000225", symmetric_seed_000225),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000226", symmetric_seed_000226),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000227", symmetric_seed_000227),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000228", symmetric_seed_000228),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000229", symmetric_seed_000229),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000230", symmetric_seed_000230),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000231", symmetric_seed_000231),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000232", symmetric_seed_000232),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000233", symmetric_seed_000233),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000234", symmetric_seed_000234),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000235", symmetric_seed_000235),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000236", symmetric_seed_000236),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000237", symmetric_seed_000237),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000238", symmetric_seed_000238),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000239", symmetric_seed_000239),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000240", symmetric_seed_000240),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000241", symmetric_seed_000241),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000242", symmetric_seed_000242),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000243", symmetric_seed_000243),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000244", symmetric_seed_000244),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000245", symmetric_seed_000245),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000246", symmetric_seed_000246),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000247", symmetric_seed_000247),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000248", symmetric_seed_000248),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000249", symmetric_seed_000249),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000250", symmetric_seed_000250),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000251", symmetric_seed_000251),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000252", symmetric_seed_000252),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000253", symmetric_seed_000253),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000254", symmetric_seed_000254),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000255", symmetric_seed_000255),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000256", symmetric_seed_000256),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000257", symmetric_seed_000257),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000258", symmetric_seed_000258),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000259", symmetric_seed_000259),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000260", symmetric_seed_000260),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000261", symmetric_seed_000261),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000262", symmetric_seed_000262),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000263", symmetric_seed_000263),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000264", symmetric_seed_000264),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000265", symmetric_seed_000265),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000266", symmetric_seed_000266),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000267", symmetric_seed_000267),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000268", symmetric_seed_000268),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000269", symmetric_seed_000269),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000270", symmetric_seed_000270),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000271", symmetric_seed_000271),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000272", symmetric_seed_000272),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000273", symmetric_seed_000273),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000274", symmetric_seed_000274),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000275", symmetric_seed_000275),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000276", symmetric_seed_000276),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000277", symmetric_seed_000277),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000278", symmetric_seed_000278),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000279", symmetric_seed_000279),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000280", symmetric_seed_000280),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000281", symmetric_seed_000281),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000282", symmetric_seed_000282),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000283", symmetric_seed_000283),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000284", symmetric_seed_000284),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000285", symmetric_seed_000285),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000286", symmetric_seed_000286),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000287", symmetric_seed_000287),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000288", symmetric_seed_000288),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000289", symmetric_seed_000289),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000290", symmetric_seed_000290),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000291", symmetric_seed_000291),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000292", symmetric_seed_000292),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000293", symmetric_seed_000293),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000294", symmetric_seed_000294),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000295", symmetric_seed_000295),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000296", symmetric_seed_000296),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000297", symmetric_seed_000297),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000298", symmetric_seed_000298),
        ("rules::drc::property_campaigns::tests::symmetric_seed_000299", symmetric_seed_000299),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000000", translation_invariant_seed_000000),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000001", translation_invariant_seed_000001),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000002", translation_invariant_seed_000002),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000003", translation_invariant_seed_000003),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000004", translation_invariant_seed_000004),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000005", translation_invariant_seed_000005),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000006", translation_invariant_seed_000006),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000007", translation_invariant_seed_000007),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000008", translation_invariant_seed_000008),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000009", translation_invariant_seed_000009),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000010", translation_invariant_seed_000010),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000011", translation_invariant_seed_000011),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000012", translation_invariant_seed_000012),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000013", translation_invariant_seed_000013),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000014", translation_invariant_seed_000014),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000015", translation_invariant_seed_000015),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000016", translation_invariant_seed_000016),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000017", translation_invariant_seed_000017),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000018", translation_invariant_seed_000018),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000019", translation_invariant_seed_000019),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000020", translation_invariant_seed_000020),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000021", translation_invariant_seed_000021),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000022", translation_invariant_seed_000022),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000023", translation_invariant_seed_000023),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000024", translation_invariant_seed_000024),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000025", translation_invariant_seed_000025),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000026", translation_invariant_seed_000026),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000027", translation_invariant_seed_000027),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000028", translation_invariant_seed_000028),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000029", translation_invariant_seed_000029),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000030", translation_invariant_seed_000030),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000031", translation_invariant_seed_000031),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000032", translation_invariant_seed_000032),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000033", translation_invariant_seed_000033),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000034", translation_invariant_seed_000034),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000035", translation_invariant_seed_000035),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000036", translation_invariant_seed_000036),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000037", translation_invariant_seed_000037),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000038", translation_invariant_seed_000038),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000039", translation_invariant_seed_000039),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000040", translation_invariant_seed_000040),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000041", translation_invariant_seed_000041),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000042", translation_invariant_seed_000042),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000043", translation_invariant_seed_000043),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000044", translation_invariant_seed_000044),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000045", translation_invariant_seed_000045),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000046", translation_invariant_seed_000046),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000047", translation_invariant_seed_000047),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000048", translation_invariant_seed_000048),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000049", translation_invariant_seed_000049),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000050", translation_invariant_seed_000050),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000051", translation_invariant_seed_000051),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000052", translation_invariant_seed_000052),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000053", translation_invariant_seed_000053),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000054", translation_invariant_seed_000054),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000055", translation_invariant_seed_000055),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000056", translation_invariant_seed_000056),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000057", translation_invariant_seed_000057),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000058", translation_invariant_seed_000058),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000059", translation_invariant_seed_000059),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000060", translation_invariant_seed_000060),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000061", translation_invariant_seed_000061),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000062", translation_invariant_seed_000062),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000063", translation_invariant_seed_000063),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000064", translation_invariant_seed_000064),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000065", translation_invariant_seed_000065),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000066", translation_invariant_seed_000066),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000067", translation_invariant_seed_000067),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000068", translation_invariant_seed_000068),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000069", translation_invariant_seed_000069),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000070", translation_invariant_seed_000070),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000071", translation_invariant_seed_000071),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000072", translation_invariant_seed_000072),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000073", translation_invariant_seed_000073),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000074", translation_invariant_seed_000074),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000075", translation_invariant_seed_000075),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000076", translation_invariant_seed_000076),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000077", translation_invariant_seed_000077),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000078", translation_invariant_seed_000078),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000079", translation_invariant_seed_000079),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000080", translation_invariant_seed_000080),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000081", translation_invariant_seed_000081),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000082", translation_invariant_seed_000082),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000083", translation_invariant_seed_000083),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000084", translation_invariant_seed_000084),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000085", translation_invariant_seed_000085),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000086", translation_invariant_seed_000086),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000087", translation_invariant_seed_000087),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000088", translation_invariant_seed_000088),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000089", translation_invariant_seed_000089),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000090", translation_invariant_seed_000090),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000091", translation_invariant_seed_000091),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000092", translation_invariant_seed_000092),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000093", translation_invariant_seed_000093),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000094", translation_invariant_seed_000094),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000095", translation_invariant_seed_000095),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000096", translation_invariant_seed_000096),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000097", translation_invariant_seed_000097),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000098", translation_invariant_seed_000098),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000099", translation_invariant_seed_000099),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000100", translation_invariant_seed_000100),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000101", translation_invariant_seed_000101),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000102", translation_invariant_seed_000102),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000103", translation_invariant_seed_000103),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000104", translation_invariant_seed_000104),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000105", translation_invariant_seed_000105),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000106", translation_invariant_seed_000106),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000107", translation_invariant_seed_000107),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000108", translation_invariant_seed_000108),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000109", translation_invariant_seed_000109),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000110", translation_invariant_seed_000110),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000111", translation_invariant_seed_000111),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000112", translation_invariant_seed_000112),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000113", translation_invariant_seed_000113),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000114", translation_invariant_seed_000114),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000115", translation_invariant_seed_000115),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000116", translation_invariant_seed_000116),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000117", translation_invariant_seed_000117),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000118", translation_invariant_seed_000118),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000119", translation_invariant_seed_000119),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000120", translation_invariant_seed_000120),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000121", translation_invariant_seed_000121),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000122", translation_invariant_seed_000122),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000123", translation_invariant_seed_000123),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000124", translation_invariant_seed_000124),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000125", translation_invariant_seed_000125),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000126", translation_invariant_seed_000126),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000127", translation_invariant_seed_000127),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000128", translation_invariant_seed_000128),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000129", translation_invariant_seed_000129),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000130", translation_invariant_seed_000130),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000131", translation_invariant_seed_000131),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000132", translation_invariant_seed_000132),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000133", translation_invariant_seed_000133),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000134", translation_invariant_seed_000134),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000135", translation_invariant_seed_000135),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000136", translation_invariant_seed_000136),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000137", translation_invariant_seed_000137),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000138", translation_invariant_seed_000138),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000139", translation_invariant_seed_000139),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000140", translation_invariant_seed_000140),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000141", translation_invariant_seed_000141),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000142", translation_invariant_seed_000142),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000143", translation_invariant_seed_000143),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000144", translation_invariant_seed_000144),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000145", translation_invariant_seed_000145),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000146", translation_invariant_seed_000146),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000147", translation_invariant_seed_000147),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000148", translation_invariant_seed_000148),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000149", translation_invariant_seed_000149),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000150", translation_invariant_seed_000150),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000151", translation_invariant_seed_000151),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000152", translation_invariant_seed_000152),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000153", translation_invariant_seed_000153),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000154", translation_invariant_seed_000154),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000155", translation_invariant_seed_000155),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000156", translation_invariant_seed_000156),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000157", translation_invariant_seed_000157),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000158", translation_invariant_seed_000158),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000159", translation_invariant_seed_000159),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000160", translation_invariant_seed_000160),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000161", translation_invariant_seed_000161),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000162", translation_invariant_seed_000162),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000163", translation_invariant_seed_000163),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000164", translation_invariant_seed_000164),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000165", translation_invariant_seed_000165),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000166", translation_invariant_seed_000166),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000167", translation_invariant_seed_000167),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000168", translation_invariant_seed_000168),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000169", translation_invariant_seed_000169),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000170", translation_invariant_seed_000170),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000171", translation_invariant_seed_000171),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000172", translation_invariant_seed_000172),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000173", translation_invariant_seed_000173),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000174", translation_invariant_seed_000174),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000175", translation_invariant_seed_000175),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000176", translation_invariant_seed_000176),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000177", translation_invariant_seed_000177),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000178", translation_invariant_seed_000178),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000179", translation_invariant_seed_000179),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000180", translation_invariant_seed_000180),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000181", translation_invariant_seed_000181),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000182", translation_invariant_seed_000182),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000183", translation_invariant_seed_000183),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000184", translation_invariant_seed_000184),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000185", translation_invariant_seed_000185),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000186", translation_invariant_seed_000186),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000187", translation_invariant_seed_000187),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000188", translation_invariant_seed_000188),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000189", translation_invariant_seed_000189),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000190", translation_invariant_seed_000190),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000191", translation_invariant_seed_000191),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000192", translation_invariant_seed_000192),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000193", translation_invariant_seed_000193),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000194", translation_invariant_seed_000194),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000195", translation_invariant_seed_000195),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000196", translation_invariant_seed_000196),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000197", translation_invariant_seed_000197),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000198", translation_invariant_seed_000198),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000199", translation_invariant_seed_000199),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000200", translation_invariant_seed_000200),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000201", translation_invariant_seed_000201),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000202", translation_invariant_seed_000202),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000203", translation_invariant_seed_000203),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000204", translation_invariant_seed_000204),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000205", translation_invariant_seed_000205),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000206", translation_invariant_seed_000206),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000207", translation_invariant_seed_000207),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000208", translation_invariant_seed_000208),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000209", translation_invariant_seed_000209),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000210", translation_invariant_seed_000210),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000211", translation_invariant_seed_000211),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000212", translation_invariant_seed_000212),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000213", translation_invariant_seed_000213),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000214", translation_invariant_seed_000214),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000215", translation_invariant_seed_000215),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000216", translation_invariant_seed_000216),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000217", translation_invariant_seed_000217),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000218", translation_invariant_seed_000218),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000219", translation_invariant_seed_000219),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000220", translation_invariant_seed_000220),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000221", translation_invariant_seed_000221),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000222", translation_invariant_seed_000222),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000223", translation_invariant_seed_000223),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000224", translation_invariant_seed_000224),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000225", translation_invariant_seed_000225),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000226", translation_invariant_seed_000226),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000227", translation_invariant_seed_000227),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000228", translation_invariant_seed_000228),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000229", translation_invariant_seed_000229),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000230", translation_invariant_seed_000230),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000231", translation_invariant_seed_000231),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000232", translation_invariant_seed_000232),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000233", translation_invariant_seed_000233),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000234", translation_invariant_seed_000234),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000235", translation_invariant_seed_000235),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000236", translation_invariant_seed_000236),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000237", translation_invariant_seed_000237),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000238", translation_invariant_seed_000238),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000239", translation_invariant_seed_000239),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000240", translation_invariant_seed_000240),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000241", translation_invariant_seed_000241),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000242", translation_invariant_seed_000242),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000243", translation_invariant_seed_000243),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000244", translation_invariant_seed_000244),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000245", translation_invariant_seed_000245),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000246", translation_invariant_seed_000246),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000247", translation_invariant_seed_000247),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000248", translation_invariant_seed_000248),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000249", translation_invariant_seed_000249),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000250", translation_invariant_seed_000250),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000251", translation_invariant_seed_000251),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000252", translation_invariant_seed_000252),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000253", translation_invariant_seed_000253),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000254", translation_invariant_seed_000254),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000255", translation_invariant_seed_000255),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000256", translation_invariant_seed_000256),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000257", translation_invariant_seed_000257),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000258", translation_invariant_seed_000258),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000259", translation_invariant_seed_000259),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000260", translation_invariant_seed_000260),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000261", translation_invariant_seed_000261),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000262", translation_invariant_seed_000262),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000263", translation_invariant_seed_000263),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000264", translation_invariant_seed_000264),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000265", translation_invariant_seed_000265),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000266", translation_invariant_seed_000266),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000267", translation_invariant_seed_000267),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000268", translation_invariant_seed_000268),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000269", translation_invariant_seed_000269),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000270", translation_invariant_seed_000270),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000271", translation_invariant_seed_000271),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000272", translation_invariant_seed_000272),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000273", translation_invariant_seed_000273),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000274", translation_invariant_seed_000274),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000275", translation_invariant_seed_000275),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000276", translation_invariant_seed_000276),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000277", translation_invariant_seed_000277),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000278", translation_invariant_seed_000278),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000279", translation_invariant_seed_000279),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000280", translation_invariant_seed_000280),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000281", translation_invariant_seed_000281),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000282", translation_invariant_seed_000282),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000283", translation_invariant_seed_000283),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000284", translation_invariant_seed_000284),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000285", translation_invariant_seed_000285),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000286", translation_invariant_seed_000286),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000287", translation_invariant_seed_000287),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000288", translation_invariant_seed_000288),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000289", translation_invariant_seed_000289),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000290", translation_invariant_seed_000290),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000291", translation_invariant_seed_000291),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000292", translation_invariant_seed_000292),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000293", translation_invariant_seed_000293),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000294", translation_invariant_seed_000294),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000295", translation_invariant_seed_000295),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000296", translation_invariant_seed_000296),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000297", translation_invariant_seed_000297),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000298", translation_invariant_seed_000298),
        ("rules::drc::property_campaigns::tests::translation_invariant_seed_000299", translation_invariant_seed_000299),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000000", rotation_invariant_seed_000000),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000001", rotation_invariant_seed_000001),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000002", rotation_invariant_seed_000002),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000003", rotation_invariant_seed_000003),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000004", rotation_invariant_seed_000004),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000005", rotation_invariant_seed_000005),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000006", rotation_invariant_seed_000006),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000007", rotation_invariant_seed_000007),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000008", rotation_invariant_seed_000008),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000009", rotation_invariant_seed_000009),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000010", rotation_invariant_seed_000010),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000011", rotation_invariant_seed_000011),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000012", rotation_invariant_seed_000012),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000013", rotation_invariant_seed_000013),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000014", rotation_invariant_seed_000014),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000015", rotation_invariant_seed_000015),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000016", rotation_invariant_seed_000016),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000017", rotation_invariant_seed_000017),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000018", rotation_invariant_seed_000018),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000019", rotation_invariant_seed_000019),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000020", rotation_invariant_seed_000020),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000021", rotation_invariant_seed_000021),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000022", rotation_invariant_seed_000022),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000023", rotation_invariant_seed_000023),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000024", rotation_invariant_seed_000024),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000025", rotation_invariant_seed_000025),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000026", rotation_invariant_seed_000026),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000027", rotation_invariant_seed_000027),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000028", rotation_invariant_seed_000028),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000029", rotation_invariant_seed_000029),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000030", rotation_invariant_seed_000030),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000031", rotation_invariant_seed_000031),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000032", rotation_invariant_seed_000032),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000033", rotation_invariant_seed_000033),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000034", rotation_invariant_seed_000034),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000035", rotation_invariant_seed_000035),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000036", rotation_invariant_seed_000036),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000037", rotation_invariant_seed_000037),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000038", rotation_invariant_seed_000038),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000039", rotation_invariant_seed_000039),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000040", rotation_invariant_seed_000040),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000041", rotation_invariant_seed_000041),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000042", rotation_invariant_seed_000042),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000043", rotation_invariant_seed_000043),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000044", rotation_invariant_seed_000044),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000045", rotation_invariant_seed_000045),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000046", rotation_invariant_seed_000046),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000047", rotation_invariant_seed_000047),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000048", rotation_invariant_seed_000048),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000049", rotation_invariant_seed_000049),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000050", rotation_invariant_seed_000050),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000051", rotation_invariant_seed_000051),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000052", rotation_invariant_seed_000052),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000053", rotation_invariant_seed_000053),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000054", rotation_invariant_seed_000054),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000055", rotation_invariant_seed_000055),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000056", rotation_invariant_seed_000056),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000057", rotation_invariant_seed_000057),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000058", rotation_invariant_seed_000058),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000059", rotation_invariant_seed_000059),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000060", rotation_invariant_seed_000060),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000061", rotation_invariant_seed_000061),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000062", rotation_invariant_seed_000062),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000063", rotation_invariant_seed_000063),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000064", rotation_invariant_seed_000064),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000065", rotation_invariant_seed_000065),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000066", rotation_invariant_seed_000066),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000067", rotation_invariant_seed_000067),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000068", rotation_invariant_seed_000068),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000069", rotation_invariant_seed_000069),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000070", rotation_invariant_seed_000070),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000071", rotation_invariant_seed_000071),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000072", rotation_invariant_seed_000072),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000073", rotation_invariant_seed_000073),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000074", rotation_invariant_seed_000074),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000075", rotation_invariant_seed_000075),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000076", rotation_invariant_seed_000076),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000077", rotation_invariant_seed_000077),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000078", rotation_invariant_seed_000078),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000079", rotation_invariant_seed_000079),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000080", rotation_invariant_seed_000080),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000081", rotation_invariant_seed_000081),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000082", rotation_invariant_seed_000082),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000083", rotation_invariant_seed_000083),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000084", rotation_invariant_seed_000084),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000085", rotation_invariant_seed_000085),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000086", rotation_invariant_seed_000086),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000087", rotation_invariant_seed_000087),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000088", rotation_invariant_seed_000088),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000089", rotation_invariant_seed_000089),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000090", rotation_invariant_seed_000090),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000091", rotation_invariant_seed_000091),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000092", rotation_invariant_seed_000092),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000093", rotation_invariant_seed_000093),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000094", rotation_invariant_seed_000094),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000095", rotation_invariant_seed_000095),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000096", rotation_invariant_seed_000096),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000097", rotation_invariant_seed_000097),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000098", rotation_invariant_seed_000098),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000099", rotation_invariant_seed_000099),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000100", rotation_invariant_seed_000100),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000101", rotation_invariant_seed_000101),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000102", rotation_invariant_seed_000102),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000103", rotation_invariant_seed_000103),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000104", rotation_invariant_seed_000104),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000105", rotation_invariant_seed_000105),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000106", rotation_invariant_seed_000106),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000107", rotation_invariant_seed_000107),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000108", rotation_invariant_seed_000108),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000109", rotation_invariant_seed_000109),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000110", rotation_invariant_seed_000110),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000111", rotation_invariant_seed_000111),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000112", rotation_invariant_seed_000112),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000113", rotation_invariant_seed_000113),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000114", rotation_invariant_seed_000114),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000115", rotation_invariant_seed_000115),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000116", rotation_invariant_seed_000116),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000117", rotation_invariant_seed_000117),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000118", rotation_invariant_seed_000118),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000119", rotation_invariant_seed_000119),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000120", rotation_invariant_seed_000120),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000121", rotation_invariant_seed_000121),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000122", rotation_invariant_seed_000122),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000123", rotation_invariant_seed_000123),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000124", rotation_invariant_seed_000124),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000125", rotation_invariant_seed_000125),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000126", rotation_invariant_seed_000126),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000127", rotation_invariant_seed_000127),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000128", rotation_invariant_seed_000128),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000129", rotation_invariant_seed_000129),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000130", rotation_invariant_seed_000130),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000131", rotation_invariant_seed_000131),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000132", rotation_invariant_seed_000132),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000133", rotation_invariant_seed_000133),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000134", rotation_invariant_seed_000134),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000135", rotation_invariant_seed_000135),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000136", rotation_invariant_seed_000136),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000137", rotation_invariant_seed_000137),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000138", rotation_invariant_seed_000138),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000139", rotation_invariant_seed_000139),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000140", rotation_invariant_seed_000140),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000141", rotation_invariant_seed_000141),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000142", rotation_invariant_seed_000142),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000143", rotation_invariant_seed_000143),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000144", rotation_invariant_seed_000144),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000145", rotation_invariant_seed_000145),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000146", rotation_invariant_seed_000146),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000147", rotation_invariant_seed_000147),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000148", rotation_invariant_seed_000148),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000149", rotation_invariant_seed_000149),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000150", rotation_invariant_seed_000150),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000151", rotation_invariant_seed_000151),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000152", rotation_invariant_seed_000152),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000153", rotation_invariant_seed_000153),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000154", rotation_invariant_seed_000154),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000155", rotation_invariant_seed_000155),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000156", rotation_invariant_seed_000156),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000157", rotation_invariant_seed_000157),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000158", rotation_invariant_seed_000158),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000159", rotation_invariant_seed_000159),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000160", rotation_invariant_seed_000160),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000161", rotation_invariant_seed_000161),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000162", rotation_invariant_seed_000162),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000163", rotation_invariant_seed_000163),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000164", rotation_invariant_seed_000164),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000165", rotation_invariant_seed_000165),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000166", rotation_invariant_seed_000166),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000167", rotation_invariant_seed_000167),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000168", rotation_invariant_seed_000168),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000169", rotation_invariant_seed_000169),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000170", rotation_invariant_seed_000170),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000171", rotation_invariant_seed_000171),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000172", rotation_invariant_seed_000172),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000173", rotation_invariant_seed_000173),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000174", rotation_invariant_seed_000174),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000175", rotation_invariant_seed_000175),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000176", rotation_invariant_seed_000176),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000177", rotation_invariant_seed_000177),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000178", rotation_invariant_seed_000178),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000179", rotation_invariant_seed_000179),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000180", rotation_invariant_seed_000180),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000181", rotation_invariant_seed_000181),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000182", rotation_invariant_seed_000182),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000183", rotation_invariant_seed_000183),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000184", rotation_invariant_seed_000184),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000185", rotation_invariant_seed_000185),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000186", rotation_invariant_seed_000186),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000187", rotation_invariant_seed_000187),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000188", rotation_invariant_seed_000188),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000189", rotation_invariant_seed_000189),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000190", rotation_invariant_seed_000190),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000191", rotation_invariant_seed_000191),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000192", rotation_invariant_seed_000192),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000193", rotation_invariant_seed_000193),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000194", rotation_invariant_seed_000194),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000195", rotation_invariant_seed_000195),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000196", rotation_invariant_seed_000196),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000197", rotation_invariant_seed_000197),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000198", rotation_invariant_seed_000198),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000199", rotation_invariant_seed_000199),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000200", rotation_invariant_seed_000200),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000201", rotation_invariant_seed_000201),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000202", rotation_invariant_seed_000202),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000203", rotation_invariant_seed_000203),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000204", rotation_invariant_seed_000204),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000205", rotation_invariant_seed_000205),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000206", rotation_invariant_seed_000206),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000207", rotation_invariant_seed_000207),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000208", rotation_invariant_seed_000208),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000209", rotation_invariant_seed_000209),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000210", rotation_invariant_seed_000210),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000211", rotation_invariant_seed_000211),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000212", rotation_invariant_seed_000212),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000213", rotation_invariant_seed_000213),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000214", rotation_invariant_seed_000214),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000215", rotation_invariant_seed_000215),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000216", rotation_invariant_seed_000216),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000217", rotation_invariant_seed_000217),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000218", rotation_invariant_seed_000218),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000219", rotation_invariant_seed_000219),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000220", rotation_invariant_seed_000220),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000221", rotation_invariant_seed_000221),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000222", rotation_invariant_seed_000222),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000223", rotation_invariant_seed_000223),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000224", rotation_invariant_seed_000224),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000225", rotation_invariant_seed_000225),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000226", rotation_invariant_seed_000226),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000227", rotation_invariant_seed_000227),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000228", rotation_invariant_seed_000228),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000229", rotation_invariant_seed_000229),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000230", rotation_invariant_seed_000230),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000231", rotation_invariant_seed_000231),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000232", rotation_invariant_seed_000232),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000233", rotation_invariant_seed_000233),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000234", rotation_invariant_seed_000234),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000235", rotation_invariant_seed_000235),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000236", rotation_invariant_seed_000236),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000237", rotation_invariant_seed_000237),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000238", rotation_invariant_seed_000238),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000239", rotation_invariant_seed_000239),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000240", rotation_invariant_seed_000240),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000241", rotation_invariant_seed_000241),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000242", rotation_invariant_seed_000242),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000243", rotation_invariant_seed_000243),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000244", rotation_invariant_seed_000244),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000245", rotation_invariant_seed_000245),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000246", rotation_invariant_seed_000246),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000247", rotation_invariant_seed_000247),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000248", rotation_invariant_seed_000248),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000249", rotation_invariant_seed_000249),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000250", rotation_invariant_seed_000250),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000251", rotation_invariant_seed_000251),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000252", rotation_invariant_seed_000252),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000253", rotation_invariant_seed_000253),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000254", rotation_invariant_seed_000254),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000255", rotation_invariant_seed_000255),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000256", rotation_invariant_seed_000256),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000257", rotation_invariant_seed_000257),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000258", rotation_invariant_seed_000258),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000259", rotation_invariant_seed_000259),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000260", rotation_invariant_seed_000260),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000261", rotation_invariant_seed_000261),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000262", rotation_invariant_seed_000262),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000263", rotation_invariant_seed_000263),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000264", rotation_invariant_seed_000264),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000265", rotation_invariant_seed_000265),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000266", rotation_invariant_seed_000266),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000267", rotation_invariant_seed_000267),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000268", rotation_invariant_seed_000268),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000269", rotation_invariant_seed_000269),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000270", rotation_invariant_seed_000270),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000271", rotation_invariant_seed_000271),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000272", rotation_invariant_seed_000272),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000273", rotation_invariant_seed_000273),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000274", rotation_invariant_seed_000274),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000275", rotation_invariant_seed_000275),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000276", rotation_invariant_seed_000276),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000277", rotation_invariant_seed_000277),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000278", rotation_invariant_seed_000278),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000279", rotation_invariant_seed_000279),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000280", rotation_invariant_seed_000280),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000281", rotation_invariant_seed_000281),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000282", rotation_invariant_seed_000282),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000283", rotation_invariant_seed_000283),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000284", rotation_invariant_seed_000284),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000285", rotation_invariant_seed_000285),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000286", rotation_invariant_seed_000286),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000287", rotation_invariant_seed_000287),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000288", rotation_invariant_seed_000288),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000289", rotation_invariant_seed_000289),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000290", rotation_invariant_seed_000290),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000291", rotation_invariant_seed_000291),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000292", rotation_invariant_seed_000292),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000293", rotation_invariant_seed_000293),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000294", rotation_invariant_seed_000294),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000295", rotation_invariant_seed_000295),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000296", rotation_invariant_seed_000296),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000297", rotation_invariant_seed_000297),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000298", rotation_invariant_seed_000298),
        ("rules::drc::property_campaigns::tests::rotation_invariant_seed_000299", rotation_invariant_seed_000299),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000000", scale_invariant_seed_000000),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000001", scale_invariant_seed_000001),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000002", scale_invariant_seed_000002),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000003", scale_invariant_seed_000003),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000004", scale_invariant_seed_000004),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000005", scale_invariant_seed_000005),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000006", scale_invariant_seed_000006),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000007", scale_invariant_seed_000007),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000008", scale_invariant_seed_000008),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000009", scale_invariant_seed_000009),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000010", scale_invariant_seed_000010),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000011", scale_invariant_seed_000011),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000012", scale_invariant_seed_000012),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000013", scale_invariant_seed_000013),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000014", scale_invariant_seed_000014),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000015", scale_invariant_seed_000015),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000016", scale_invariant_seed_000016),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000017", scale_invariant_seed_000017),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000018", scale_invariant_seed_000018),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000019", scale_invariant_seed_000019),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000020", scale_invariant_seed_000020),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000021", scale_invariant_seed_000021),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000022", scale_invariant_seed_000022),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000023", scale_invariant_seed_000023),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000024", scale_invariant_seed_000024),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000025", scale_invariant_seed_000025),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000026", scale_invariant_seed_000026),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000027", scale_invariant_seed_000027),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000028", scale_invariant_seed_000028),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000029", scale_invariant_seed_000029),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000030", scale_invariant_seed_000030),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000031", scale_invariant_seed_000031),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000032", scale_invariant_seed_000032),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000033", scale_invariant_seed_000033),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000034", scale_invariant_seed_000034),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000035", scale_invariant_seed_000035),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000036", scale_invariant_seed_000036),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000037", scale_invariant_seed_000037),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000038", scale_invariant_seed_000038),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000039", scale_invariant_seed_000039),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000040", scale_invariant_seed_000040),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000041", scale_invariant_seed_000041),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000042", scale_invariant_seed_000042),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000043", scale_invariant_seed_000043),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000044", scale_invariant_seed_000044),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000045", scale_invariant_seed_000045),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000046", scale_invariant_seed_000046),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000047", scale_invariant_seed_000047),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000048", scale_invariant_seed_000048),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000049", scale_invariant_seed_000049),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000050", scale_invariant_seed_000050),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000051", scale_invariant_seed_000051),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000052", scale_invariant_seed_000052),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000053", scale_invariant_seed_000053),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000054", scale_invariant_seed_000054),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000055", scale_invariant_seed_000055),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000056", scale_invariant_seed_000056),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000057", scale_invariant_seed_000057),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000058", scale_invariant_seed_000058),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000059", scale_invariant_seed_000059),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000060", scale_invariant_seed_000060),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000061", scale_invariant_seed_000061),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000062", scale_invariant_seed_000062),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000063", scale_invariant_seed_000063),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000064", scale_invariant_seed_000064),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000065", scale_invariant_seed_000065),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000066", scale_invariant_seed_000066),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000067", scale_invariant_seed_000067),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000068", scale_invariant_seed_000068),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000069", scale_invariant_seed_000069),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000070", scale_invariant_seed_000070),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000071", scale_invariant_seed_000071),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000072", scale_invariant_seed_000072),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000073", scale_invariant_seed_000073),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000074", scale_invariant_seed_000074),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000075", scale_invariant_seed_000075),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000076", scale_invariant_seed_000076),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000077", scale_invariant_seed_000077),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000078", scale_invariant_seed_000078),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000079", scale_invariant_seed_000079),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000080", scale_invariant_seed_000080),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000081", scale_invariant_seed_000081),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000082", scale_invariant_seed_000082),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000083", scale_invariant_seed_000083),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000084", scale_invariant_seed_000084),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000085", scale_invariant_seed_000085),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000086", scale_invariant_seed_000086),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000087", scale_invariant_seed_000087),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000088", scale_invariant_seed_000088),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000089", scale_invariant_seed_000089),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000090", scale_invariant_seed_000090),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000091", scale_invariant_seed_000091),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000092", scale_invariant_seed_000092),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000093", scale_invariant_seed_000093),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000094", scale_invariant_seed_000094),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000095", scale_invariant_seed_000095),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000096", scale_invariant_seed_000096),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000097", scale_invariant_seed_000097),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000098", scale_invariant_seed_000098),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000099", scale_invariant_seed_000099),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000100", scale_invariant_seed_000100),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000101", scale_invariant_seed_000101),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000102", scale_invariant_seed_000102),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000103", scale_invariant_seed_000103),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000104", scale_invariant_seed_000104),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000105", scale_invariant_seed_000105),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000106", scale_invariant_seed_000106),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000107", scale_invariant_seed_000107),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000108", scale_invariant_seed_000108),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000109", scale_invariant_seed_000109),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000110", scale_invariant_seed_000110),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000111", scale_invariant_seed_000111),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000112", scale_invariant_seed_000112),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000113", scale_invariant_seed_000113),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000114", scale_invariant_seed_000114),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000115", scale_invariant_seed_000115),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000116", scale_invariant_seed_000116),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000117", scale_invariant_seed_000117),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000118", scale_invariant_seed_000118),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000119", scale_invariant_seed_000119),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000120", scale_invariant_seed_000120),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000121", scale_invariant_seed_000121),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000122", scale_invariant_seed_000122),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000123", scale_invariant_seed_000123),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000124", scale_invariant_seed_000124),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000125", scale_invariant_seed_000125),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000126", scale_invariant_seed_000126),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000127", scale_invariant_seed_000127),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000128", scale_invariant_seed_000128),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000129", scale_invariant_seed_000129),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000130", scale_invariant_seed_000130),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000131", scale_invariant_seed_000131),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000132", scale_invariant_seed_000132),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000133", scale_invariant_seed_000133),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000134", scale_invariant_seed_000134),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000135", scale_invariant_seed_000135),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000136", scale_invariant_seed_000136),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000137", scale_invariant_seed_000137),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000138", scale_invariant_seed_000138),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000139", scale_invariant_seed_000139),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000140", scale_invariant_seed_000140),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000141", scale_invariant_seed_000141),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000142", scale_invariant_seed_000142),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000143", scale_invariant_seed_000143),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000144", scale_invariant_seed_000144),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000145", scale_invariant_seed_000145),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000146", scale_invariant_seed_000146),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000147", scale_invariant_seed_000147),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000148", scale_invariant_seed_000148),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000149", scale_invariant_seed_000149),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000150", scale_invariant_seed_000150),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000151", scale_invariant_seed_000151),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000152", scale_invariant_seed_000152),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000153", scale_invariant_seed_000153),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000154", scale_invariant_seed_000154),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000155", scale_invariant_seed_000155),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000156", scale_invariant_seed_000156),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000157", scale_invariant_seed_000157),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000158", scale_invariant_seed_000158),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000159", scale_invariant_seed_000159),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000160", scale_invariant_seed_000160),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000161", scale_invariant_seed_000161),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000162", scale_invariant_seed_000162),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000163", scale_invariant_seed_000163),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000164", scale_invariant_seed_000164),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000165", scale_invariant_seed_000165),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000166", scale_invariant_seed_000166),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000167", scale_invariant_seed_000167),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000168", scale_invariant_seed_000168),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000169", scale_invariant_seed_000169),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000170", scale_invariant_seed_000170),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000171", scale_invariant_seed_000171),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000172", scale_invariant_seed_000172),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000173", scale_invariant_seed_000173),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000174", scale_invariant_seed_000174),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000175", scale_invariant_seed_000175),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000176", scale_invariant_seed_000176),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000177", scale_invariant_seed_000177),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000178", scale_invariant_seed_000178),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000179", scale_invariant_seed_000179),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000180", scale_invariant_seed_000180),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000181", scale_invariant_seed_000181),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000182", scale_invariant_seed_000182),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000183", scale_invariant_seed_000183),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000184", scale_invariant_seed_000184),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000185", scale_invariant_seed_000185),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000186", scale_invariant_seed_000186),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000187", scale_invariant_seed_000187),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000188", scale_invariant_seed_000188),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000189", scale_invariant_seed_000189),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000190", scale_invariant_seed_000190),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000191", scale_invariant_seed_000191),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000192", scale_invariant_seed_000192),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000193", scale_invariant_seed_000193),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000194", scale_invariant_seed_000194),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000195", scale_invariant_seed_000195),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000196", scale_invariant_seed_000196),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000197", scale_invariant_seed_000197),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000198", scale_invariant_seed_000198),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000199", scale_invariant_seed_000199),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000200", scale_invariant_seed_000200),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000201", scale_invariant_seed_000201),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000202", scale_invariant_seed_000202),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000203", scale_invariant_seed_000203),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000204", scale_invariant_seed_000204),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000205", scale_invariant_seed_000205),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000206", scale_invariant_seed_000206),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000207", scale_invariant_seed_000207),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000208", scale_invariant_seed_000208),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000209", scale_invariant_seed_000209),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000210", scale_invariant_seed_000210),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000211", scale_invariant_seed_000211),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000212", scale_invariant_seed_000212),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000213", scale_invariant_seed_000213),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000214", scale_invariant_seed_000214),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000215", scale_invariant_seed_000215),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000216", scale_invariant_seed_000216),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000217", scale_invariant_seed_000217),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000218", scale_invariant_seed_000218),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000219", scale_invariant_seed_000219),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000220", scale_invariant_seed_000220),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000221", scale_invariant_seed_000221),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000222", scale_invariant_seed_000222),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000223", scale_invariant_seed_000223),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000224", scale_invariant_seed_000224),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000225", scale_invariant_seed_000225),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000226", scale_invariant_seed_000226),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000227", scale_invariant_seed_000227),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000228", scale_invariant_seed_000228),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000229", scale_invariant_seed_000229),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000230", scale_invariant_seed_000230),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000231", scale_invariant_seed_000231),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000232", scale_invariant_seed_000232),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000233", scale_invariant_seed_000233),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000234", scale_invariant_seed_000234),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000235", scale_invariant_seed_000235),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000236", scale_invariant_seed_000236),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000237", scale_invariant_seed_000237),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000238", scale_invariant_seed_000238),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000239", scale_invariant_seed_000239),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000240", scale_invariant_seed_000240),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000241", scale_invariant_seed_000241),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000242", scale_invariant_seed_000242),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000243", scale_invariant_seed_000243),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000244", scale_invariant_seed_000244),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000245", scale_invariant_seed_000245),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000246", scale_invariant_seed_000246),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000247", scale_invariant_seed_000247),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000248", scale_invariant_seed_000248),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000249", scale_invariant_seed_000249),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000250", scale_invariant_seed_000250),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000251", scale_invariant_seed_000251),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000252", scale_invariant_seed_000252),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000253", scale_invariant_seed_000253),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000254", scale_invariant_seed_000254),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000255", scale_invariant_seed_000255),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000256", scale_invariant_seed_000256),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000257", scale_invariant_seed_000257),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000258", scale_invariant_seed_000258),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000259", scale_invariant_seed_000259),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000260", scale_invariant_seed_000260),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000261", scale_invariant_seed_000261),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000262", scale_invariant_seed_000262),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000263", scale_invariant_seed_000263),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000264", scale_invariant_seed_000264),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000265", scale_invariant_seed_000265),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000266", scale_invariant_seed_000266),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000267", scale_invariant_seed_000267),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000268", scale_invariant_seed_000268),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000269", scale_invariant_seed_000269),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000270", scale_invariant_seed_000270),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000271", scale_invariant_seed_000271),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000272", scale_invariant_seed_000272),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000273", scale_invariant_seed_000273),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000274", scale_invariant_seed_000274),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000275", scale_invariant_seed_000275),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000276", scale_invariant_seed_000276),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000277", scale_invariant_seed_000277),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000278", scale_invariant_seed_000278),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000279", scale_invariant_seed_000279),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000280", scale_invariant_seed_000280),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000281", scale_invariant_seed_000281),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000282", scale_invariant_seed_000282),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000283", scale_invariant_seed_000283),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000284", scale_invariant_seed_000284),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000285", scale_invariant_seed_000285),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000286", scale_invariant_seed_000286),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000287", scale_invariant_seed_000287),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000288", scale_invariant_seed_000288),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000289", scale_invariant_seed_000289),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000290", scale_invariant_seed_000290),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000291", scale_invariant_seed_000291),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000292", scale_invariant_seed_000292),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000293", scale_invariant_seed_000293),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000294", scale_invariant_seed_000294),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000295", scale_invariant_seed_000295),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000296", scale_invariant_seed_000296),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000297", scale_invariant_seed_000297),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000298", scale_invariant_seed_000298),
        ("rules::drc::property_campaigns::tests::scale_invariant_seed_000299", scale_invariant_seed_000299),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000000", naive_reference_agreement_seed_000000),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000001", naive_reference_agreement_seed_000001),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000002", naive_reference_agreement_seed_000002),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000003", naive_reference_agreement_seed_000003),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000004", naive_reference_agreement_seed_000004),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000005", naive_reference_agreement_seed_000005),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000006", naive_reference_agreement_seed_000006),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000007", naive_reference_agreement_seed_000007),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000008", naive_reference_agreement_seed_000008),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000009", naive_reference_agreement_seed_000009),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000010", naive_reference_agreement_seed_000010),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000011", naive_reference_agreement_seed_000011),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000012", naive_reference_agreement_seed_000012),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000013", naive_reference_agreement_seed_000013),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000014", naive_reference_agreement_seed_000014),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000015", naive_reference_agreement_seed_000015),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000016", naive_reference_agreement_seed_000016),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000017", naive_reference_agreement_seed_000017),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000018", naive_reference_agreement_seed_000018),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000019", naive_reference_agreement_seed_000019),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000020", naive_reference_agreement_seed_000020),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000021", naive_reference_agreement_seed_000021),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000022", naive_reference_agreement_seed_000022),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000023", naive_reference_agreement_seed_000023),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000024", naive_reference_agreement_seed_000024),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000025", naive_reference_agreement_seed_000025),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000026", naive_reference_agreement_seed_000026),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000027", naive_reference_agreement_seed_000027),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000028", naive_reference_agreement_seed_000028),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000029", naive_reference_agreement_seed_000029),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000030", naive_reference_agreement_seed_000030),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000031", naive_reference_agreement_seed_000031),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000032", naive_reference_agreement_seed_000032),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000033", naive_reference_agreement_seed_000033),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000034", naive_reference_agreement_seed_000034),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000035", naive_reference_agreement_seed_000035),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000036", naive_reference_agreement_seed_000036),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000037", naive_reference_agreement_seed_000037),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000038", naive_reference_agreement_seed_000038),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000039", naive_reference_agreement_seed_000039),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000040", naive_reference_agreement_seed_000040),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000041", naive_reference_agreement_seed_000041),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000042", naive_reference_agreement_seed_000042),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000043", naive_reference_agreement_seed_000043),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000044", naive_reference_agreement_seed_000044),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000045", naive_reference_agreement_seed_000045),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000046", naive_reference_agreement_seed_000046),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000047", naive_reference_agreement_seed_000047),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000048", naive_reference_agreement_seed_000048),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000049", naive_reference_agreement_seed_000049),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000050", naive_reference_agreement_seed_000050),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000051", naive_reference_agreement_seed_000051),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000052", naive_reference_agreement_seed_000052),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000053", naive_reference_agreement_seed_000053),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000054", naive_reference_agreement_seed_000054),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000055", naive_reference_agreement_seed_000055),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000056", naive_reference_agreement_seed_000056),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000057", naive_reference_agreement_seed_000057),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000058", naive_reference_agreement_seed_000058),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000059", naive_reference_agreement_seed_000059),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000060", naive_reference_agreement_seed_000060),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000061", naive_reference_agreement_seed_000061),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000062", naive_reference_agreement_seed_000062),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000063", naive_reference_agreement_seed_000063),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000064", naive_reference_agreement_seed_000064),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000065", naive_reference_agreement_seed_000065),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000066", naive_reference_agreement_seed_000066),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000067", naive_reference_agreement_seed_000067),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000068", naive_reference_agreement_seed_000068),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000069", naive_reference_agreement_seed_000069),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000070", naive_reference_agreement_seed_000070),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000071", naive_reference_agreement_seed_000071),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000072", naive_reference_agreement_seed_000072),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000073", naive_reference_agreement_seed_000073),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000074", naive_reference_agreement_seed_000074),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000075", naive_reference_agreement_seed_000075),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000076", naive_reference_agreement_seed_000076),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000077", naive_reference_agreement_seed_000077),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000078", naive_reference_agreement_seed_000078),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000079", naive_reference_agreement_seed_000079),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000080", naive_reference_agreement_seed_000080),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000081", naive_reference_agreement_seed_000081),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000082", naive_reference_agreement_seed_000082),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000083", naive_reference_agreement_seed_000083),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000084", naive_reference_agreement_seed_000084),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000085", naive_reference_agreement_seed_000085),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000086", naive_reference_agreement_seed_000086),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000087", naive_reference_agreement_seed_000087),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000088", naive_reference_agreement_seed_000088),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000089", naive_reference_agreement_seed_000089),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000090", naive_reference_agreement_seed_000090),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000091", naive_reference_agreement_seed_000091),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000092", naive_reference_agreement_seed_000092),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000093", naive_reference_agreement_seed_000093),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000094", naive_reference_agreement_seed_000094),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000095", naive_reference_agreement_seed_000095),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000096", naive_reference_agreement_seed_000096),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000097", naive_reference_agreement_seed_000097),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000098", naive_reference_agreement_seed_000098),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000099", naive_reference_agreement_seed_000099),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000100", naive_reference_agreement_seed_000100),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000101", naive_reference_agreement_seed_000101),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000102", naive_reference_agreement_seed_000102),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000103", naive_reference_agreement_seed_000103),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000104", naive_reference_agreement_seed_000104),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000105", naive_reference_agreement_seed_000105),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000106", naive_reference_agreement_seed_000106),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000107", naive_reference_agreement_seed_000107),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000108", naive_reference_agreement_seed_000108),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000109", naive_reference_agreement_seed_000109),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000110", naive_reference_agreement_seed_000110),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000111", naive_reference_agreement_seed_000111),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000112", naive_reference_agreement_seed_000112),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000113", naive_reference_agreement_seed_000113),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000114", naive_reference_agreement_seed_000114),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000115", naive_reference_agreement_seed_000115),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000116", naive_reference_agreement_seed_000116),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000117", naive_reference_agreement_seed_000117),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000118", naive_reference_agreement_seed_000118),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000119", naive_reference_agreement_seed_000119),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000120", naive_reference_agreement_seed_000120),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000121", naive_reference_agreement_seed_000121),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000122", naive_reference_agreement_seed_000122),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000123", naive_reference_agreement_seed_000123),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000124", naive_reference_agreement_seed_000124),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000125", naive_reference_agreement_seed_000125),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000126", naive_reference_agreement_seed_000126),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000127", naive_reference_agreement_seed_000127),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000128", naive_reference_agreement_seed_000128),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000129", naive_reference_agreement_seed_000129),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000130", naive_reference_agreement_seed_000130),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000131", naive_reference_agreement_seed_000131),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000132", naive_reference_agreement_seed_000132),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000133", naive_reference_agreement_seed_000133),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000134", naive_reference_agreement_seed_000134),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000135", naive_reference_agreement_seed_000135),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000136", naive_reference_agreement_seed_000136),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000137", naive_reference_agreement_seed_000137),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000138", naive_reference_agreement_seed_000138),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000139", naive_reference_agreement_seed_000139),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000140", naive_reference_agreement_seed_000140),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000141", naive_reference_agreement_seed_000141),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000142", naive_reference_agreement_seed_000142),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000143", naive_reference_agreement_seed_000143),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000144", naive_reference_agreement_seed_000144),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000145", naive_reference_agreement_seed_000145),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000146", naive_reference_agreement_seed_000146),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000147", naive_reference_agreement_seed_000147),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000148", naive_reference_agreement_seed_000148),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000149", naive_reference_agreement_seed_000149),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000150", naive_reference_agreement_seed_000150),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000151", naive_reference_agreement_seed_000151),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000152", naive_reference_agreement_seed_000152),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000153", naive_reference_agreement_seed_000153),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000154", naive_reference_agreement_seed_000154),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000155", naive_reference_agreement_seed_000155),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000156", naive_reference_agreement_seed_000156),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000157", naive_reference_agreement_seed_000157),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000158", naive_reference_agreement_seed_000158),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000159", naive_reference_agreement_seed_000159),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000160", naive_reference_agreement_seed_000160),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000161", naive_reference_agreement_seed_000161),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000162", naive_reference_agreement_seed_000162),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000163", naive_reference_agreement_seed_000163),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000164", naive_reference_agreement_seed_000164),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000165", naive_reference_agreement_seed_000165),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000166", naive_reference_agreement_seed_000166),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000167", naive_reference_agreement_seed_000167),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000168", naive_reference_agreement_seed_000168),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000169", naive_reference_agreement_seed_000169),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000170", naive_reference_agreement_seed_000170),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000171", naive_reference_agreement_seed_000171),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000172", naive_reference_agreement_seed_000172),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000173", naive_reference_agreement_seed_000173),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000174", naive_reference_agreement_seed_000174),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000175", naive_reference_agreement_seed_000175),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000176", naive_reference_agreement_seed_000176),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000177", naive_reference_agreement_seed_000177),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000178", naive_reference_agreement_seed_000178),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000179", naive_reference_agreement_seed_000179),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000180", naive_reference_agreement_seed_000180),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000181", naive_reference_agreement_seed_000181),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000182", naive_reference_agreement_seed_000182),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000183", naive_reference_agreement_seed_000183),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000184", naive_reference_agreement_seed_000184),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000185", naive_reference_agreement_seed_000185),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000186", naive_reference_agreement_seed_000186),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000187", naive_reference_agreement_seed_000187),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000188", naive_reference_agreement_seed_000188),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000189", naive_reference_agreement_seed_000189),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000190", naive_reference_agreement_seed_000190),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000191", naive_reference_agreement_seed_000191),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000192", naive_reference_agreement_seed_000192),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000193", naive_reference_agreement_seed_000193),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000194", naive_reference_agreement_seed_000194),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000195", naive_reference_agreement_seed_000195),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000196", naive_reference_agreement_seed_000196),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000197", naive_reference_agreement_seed_000197),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000198", naive_reference_agreement_seed_000198),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000199", naive_reference_agreement_seed_000199),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000200", naive_reference_agreement_seed_000200),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000201", naive_reference_agreement_seed_000201),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000202", naive_reference_agreement_seed_000202),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000203", naive_reference_agreement_seed_000203),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000204", naive_reference_agreement_seed_000204),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000205", naive_reference_agreement_seed_000205),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000206", naive_reference_agreement_seed_000206),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000207", naive_reference_agreement_seed_000207),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000208", naive_reference_agreement_seed_000208),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000209", naive_reference_agreement_seed_000209),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000210", naive_reference_agreement_seed_000210),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000211", naive_reference_agreement_seed_000211),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000212", naive_reference_agreement_seed_000212),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000213", naive_reference_agreement_seed_000213),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000214", naive_reference_agreement_seed_000214),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000215", naive_reference_agreement_seed_000215),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000216", naive_reference_agreement_seed_000216),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000217", naive_reference_agreement_seed_000217),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000218", naive_reference_agreement_seed_000218),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000219", naive_reference_agreement_seed_000219),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000220", naive_reference_agreement_seed_000220),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000221", naive_reference_agreement_seed_000221),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000222", naive_reference_agreement_seed_000222),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000223", naive_reference_agreement_seed_000223),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000224", naive_reference_agreement_seed_000224),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000225", naive_reference_agreement_seed_000225),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000226", naive_reference_agreement_seed_000226),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000227", naive_reference_agreement_seed_000227),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000228", naive_reference_agreement_seed_000228),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000229", naive_reference_agreement_seed_000229),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000230", naive_reference_agreement_seed_000230),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000231", naive_reference_agreement_seed_000231),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000232", naive_reference_agreement_seed_000232),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000233", naive_reference_agreement_seed_000233),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000234", naive_reference_agreement_seed_000234),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000235", naive_reference_agreement_seed_000235),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000236", naive_reference_agreement_seed_000236),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000237", naive_reference_agreement_seed_000237),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000238", naive_reference_agreement_seed_000238),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000239", naive_reference_agreement_seed_000239),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000240", naive_reference_agreement_seed_000240),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000241", naive_reference_agreement_seed_000241),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000242", naive_reference_agreement_seed_000242),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000243", naive_reference_agreement_seed_000243),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000244", naive_reference_agreement_seed_000244),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000245", naive_reference_agreement_seed_000245),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000246", naive_reference_agreement_seed_000246),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000247", naive_reference_agreement_seed_000247),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000248", naive_reference_agreement_seed_000248),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000249", naive_reference_agreement_seed_000249),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000250", naive_reference_agreement_seed_000250),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000251", naive_reference_agreement_seed_000251),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000252", naive_reference_agreement_seed_000252),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000253", naive_reference_agreement_seed_000253),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000254", naive_reference_agreement_seed_000254),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000255", naive_reference_agreement_seed_000255),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000256", naive_reference_agreement_seed_000256),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000257", naive_reference_agreement_seed_000257),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000258", naive_reference_agreement_seed_000258),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000259", naive_reference_agreement_seed_000259),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000260", naive_reference_agreement_seed_000260),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000261", naive_reference_agreement_seed_000261),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000262", naive_reference_agreement_seed_000262),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000263", naive_reference_agreement_seed_000263),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000264", naive_reference_agreement_seed_000264),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000265", naive_reference_agreement_seed_000265),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000266", naive_reference_agreement_seed_000266),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000267", naive_reference_agreement_seed_000267),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000268", naive_reference_agreement_seed_000268),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000269", naive_reference_agreement_seed_000269),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000270", naive_reference_agreement_seed_000270),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000271", naive_reference_agreement_seed_000271),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000272", naive_reference_agreement_seed_000272),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000273", naive_reference_agreement_seed_000273),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000274", naive_reference_agreement_seed_000274),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000275", naive_reference_agreement_seed_000275),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000276", naive_reference_agreement_seed_000276),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000277", naive_reference_agreement_seed_000277),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000278", naive_reference_agreement_seed_000278),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000279", naive_reference_agreement_seed_000279),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000280", naive_reference_agreement_seed_000280),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000281", naive_reference_agreement_seed_000281),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000282", naive_reference_agreement_seed_000282),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000283", naive_reference_agreement_seed_000283),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000284", naive_reference_agreement_seed_000284),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000285", naive_reference_agreement_seed_000285),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000286", naive_reference_agreement_seed_000286),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000287", naive_reference_agreement_seed_000287),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000288", naive_reference_agreement_seed_000288),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000289", naive_reference_agreement_seed_000289),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000290", naive_reference_agreement_seed_000290),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000291", naive_reference_agreement_seed_000291),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000292", naive_reference_agreement_seed_000292),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000293", naive_reference_agreement_seed_000293),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000294", naive_reference_agreement_seed_000294),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000295", naive_reference_agreement_seed_000295),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000296", naive_reference_agreement_seed_000296),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000297", naive_reference_agreement_seed_000297),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000298", naive_reference_agreement_seed_000298),
        ("rules::drc::property_campaigns::tests::naive_reference_agreement_seed_000299", naive_reference_agreement_seed_000299),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}


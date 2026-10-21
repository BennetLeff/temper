//! HV input leads for the Rev C probe, option B (owner decision 2026-10-20):
//! two dedicated probes, each with one permanent job on stage 53.
//!
//! - Probe 1 (bank): TIP+ insulated M4 ring on J5 (RES_A); TIP- soldered into
//!   C22's free plated hole on SW_B.
//! - Probe 2 (coil): TIP+ ring on J5 as well (two rings stacked); TIP- ring on J2
//!   (COIL_FEED).
//!
//! Each probe's two leads ride a rigid printed spine from the probe enclosure's
//! tip-end wall to a printed dock on stage 53. Printed resin gets no insulation
//! credit: the rated wire insulation, air clearance and the FR4 board creepage
//! remain the HV design, and the printed parts only fix geometry.
//!
//! One source of geometry for:
//! - the capacitance / inductance / resonance / pickup / setback / clearance
//!   budget (validation/leads/leads.txt), with pass/fail gates;
//! - validation/leads/geometry.json, which the CadQuery scripts in mech3d/ read
//!   (they do not repeat dimensions by hand);
//! - the section view docs/hv-leads-section.svg.
//!
//! Inputs read (committed, regenerated only by their own extract commands):
//! - validation/leads/stage53-bodies.txt (component bodies from the stage-53
//!   board-of-record STEP; mech3d/stage53_bodies.py);
//! - validation/leads/stage53-earth.txt (stage-53 earth-referenced copper;
//!   tools/stage53_probe_points.py --extract-earth).
//!
//! Run from the probe directory (`make check` does this):
//!     rustc --edition 2021 tools/leads.rs -o /tmp/temper-probe-leads && /tmp/temper-probe-leads
//! Every `gate` is a design requirement; a failing gate exits non-zero.
//!
//! Frames. Probe-box frame: the probe board's (x along the board, tip edge x = 0,
//! output end x = 150; y across it, KiCad sense, inter-leg axis y = 35; z up from
//! the enclosure's inner floor). Stage-53 frame: KiCad x, KiCad y (down), z up
//! from the stage-53 board top. geometry.json converts both to right-handed
//! frames (y negated); see its "frames" entry. Units are mm, pF, uH and MHz
//! unless named otherwise.
use std::{f64::consts::PI, fmt::Write as _, fs};

const EPS0: f64 = 8.8541878128e-12; // F/m
const MU0: f64 = 1.25663706212e-6; // H/m
const C0: f64 = 299_792_458.0; // m/s

// ---- Lead wire: see docs/hv-leads.md "Lead wire" for the basis ----
/// Primary wire is the owner's AliExpress "20 AWG silicone 10 kV" wire, accepted
/// on incoming OD and hipot only. Rated fallbacks: Rowe R800-1020 and Alpha Wire
/// 392040 (UL AWM 3239, 150 C, 10 kV DC, 20 AWG 10/30). The conductor envelope
/// spans Alpha's 0.037 in (0.94 mm) 10/30 bundle and a fine-stranded 20 AWG
/// bundle up to 1.05 mm (incoming check, qualification 7).
const COND_BUNDLE: f64 = 0.037 * 25.4;
const COND_MAX: f64 = 1.05;
/// Conductor cross-section of 20 AWG (ten 30 AWG strands, 0.0509 mm2 each): its
/// equal-area diameter is used for lower estimates and inductance upper estimates.
const COND_AREA_MM2: f64 = 10.0 * 0.0509;
/// Insulation OD envelope: incoming inspection rejects wire outside 2.87..3.15 mm.
const OD_NOM: f64 = (2.87 + 3.15) / 2.0;
const OD_TOL: f64 = (3.15 - 2.87) / 2.0;
/// Silicone rubber permittivity bracket (2.7-3.6 published, widened).
const ER_MAX: f64 = 4.0;
const ER_MIN: f64 = 2.5;
/// Printed resin permittivity: Formlabs publishes none. The bracket 3-4 is
/// typical of cured methacrylate resins; bounds use 5.0.
const ER_RESIN: f64 = 4.0;
const ER_BOUND: f64 = 5.0;
/// The incoming hipot (qualification 7) is the acceptance basis for the
/// unrated wire; 10 kV is the seller's claim and the rated fallbacks' UL rating.
const WIRE_HIPOT_KV_DC: f64 = 5.0;
const WIRE_RATED_KV_DC: f64 = 10.0;
/// Minimum bend radius of a fixed, clamped lead (both ends held by printed parts).
const R_BEND: f64 = 15.0;

// ---- Enclosure (reference design): Hammond 1455N2201 ----
/// Hammond 1455N2201 drawing: extrusion 103.00 x 53.00 mm outside, internal
/// height 49.70 +/- 0.56 mm (minimum 49.14), length 220.00 +/- 0.50 mm;
/// polycarbonate bezel lip 1.60 mm between each extrusion end and its end
/// plate; end plate 103.12 x 53.09 x 1.50 mm, 4 x 0.165 in holes on
/// 95.00 x 45.47 mm, countersunk 0.230 in x 82 deg, #6 thread-forming screws.
const BOX_H: f64 = 49.14;
const BOX_H_NOM: f64 = 49.70;
/// Internal width at the side-wall rib tips (revc.md section 9).
const BOX_W: f64 = 95.0;
/// Extrusion outside section and wall (bottom wall = (53.00 - 49.70) / 2).
const BOX_OUT_W: f64 = 103.0;
const BOX_OUT_H: f64 = 53.0;
const BOX_FLOOR_T: f64 = (53.0 - 49.70) / 2.0;
/// Board placement: underside 22.0 mm above the floor, 1.6 mm thick.
const BOARD_UNDER: f64 = 22.0;
const BOARD_T: f64 = 1.6;
const BOARD_TOP: f64 = BOARD_UNDER + BOARD_T;
/// Board centred across the box: y = 0 edge is this far from the rib tips.
const SIDE_GAP: f64 = (BOX_W - 70.0) / 2.0;
/// Output-end panel inner face at the BNC housing face (pins x = 142.4 + 7.37).
const OUT_PANEL_X: f64 = 142.4 + 7.37;
/// Internal length between the end-plate inner faces: extrusion plus two bezel lips.
const BOX_L_INT: f64 = 220.0 + 2.0 * 1.60;
const TIP_PLATE_X: f64 = OUT_PANEL_X - BOX_L_INT;

// ---- Tip-end wall insert (printed, reference) and gland ----
/// Insert outline as Hammond's end panel; the gland seat is counterbored from
/// the outside to SEAT_T so the gland thread reaches through seat and locknut.
const PLATE_W: f64 = 103.12;
const PLATE_H: f64 = 53.09;
const WALL_T: f64 = 3.0;
const SEAT_T: f64 = 2.5;
const SEAT_D: f64 = 21.0;
/// Insert outline centre in board y and in z above the inner floor.
const PLATE_CY: f64 = 35.0;
const PLATE_CZ: f64 = BOX_H_NOM / 2.0;
/// End-panel screw holes, offsets from the plate centre (u, v) and diameter.
const PLATE_SCREWS: [(f64, f64); 4] = [(-47.5, -22.735), (47.5, -22.735), (-47.5, 22.735), (47.5, 22.735)];
const PLATE_SCREW_D: f64 = 4.2;
/// Gland: Essentra CG-PG7-1-BK (PG7, clamps 2.00-5.00 mm, panel hole 0.500 in
/// = 12.7 mm, thread length 8.00 mm) with locknut CGLN-PG7-BK (width 19.00 mm,
/// thickness 5.00 mm, DigiKey attributes). The 19 mm width is taken as across
/// flats, so the keep-out is the across-corners 19 / cos 30 deg = 21.94 mm.
const GLAND_HOLE: f64 = 12.7;
const GLAND_THREAD: f64 = 8.0;
const GLAND_NUT_AC: f64 = 22.0;
const GLAND_DY: f64 = 14.5;
const NUT_T: f64 = 5.0;
/// Outside envelope of the gland body and dome nut (diameter, length from the
/// insert's outer face). Not on the distributor page; an estimate to fit-check.
const GLAND_OUT_D: f64 = 20.0;
const GLAND_OUT_L: f64 = 20.0;
/// Ledge on the insert's inner face, between the locknuts, that carries the
/// lead bridge's insert end (the FR4 design passed a bridge tab through a slot;
/// the insert centre now takes the spine socket instead). Width (y), overlap
/// under the bridge (x), thickness (z, below the board-top plane).
const LEDGE_W: f64 = 5.0;
const LEDGE_OVERLAP: f64 = 6.0;
const LEDGE_T: f64 = 3.0;
/// Spine: a rod on the spine axis (between the gland domes) carrying saddles
/// every SADDLE_PITCH; the rod enters a socket boss on the insert's outer face.
const ROD_W: f64 = 5.0;
const ROD_H: f64 = 8.0;
const BOSS_WALL: f64 = 1.5;
const BOSS_L: f64 = 12.0;

// ---- HV landings on the probe board ----
const W_HV: [(f64, f64); 2] = [(7.0, 27.0), (7.0, 43.0)];
/// Exposed conductor envelope at a landing: 4 mm pad, solder fillet <= 1.5 mm
/// above the board top, trimmed tail <= 1.0 mm below the underside.
const PAD_R: f64 = 2.0;
const FILLET_UP: f64 = 1.5;
const TAIL_DOWN: f64 = 1.0;
/// H3/H4: unplated M3 holes on the tip-end prongs (layout.rs mounting_holes).
const H34: [(f64, f64); 2] = [(5.0, 5.0), (5.0, 65.0)];

// ---- Lead bridge (printed, on the board top, held by the H3/H4 nylon screws) ----
/// 3.0 mm Flame Retardant resin with a 1.5 mm-deep groove under each lead, so the
/// lead lies 1.5 mm above the board top plane.
const BRIDGE_T: f64 = 3.0;
const GROOVE: f64 = 1.5;
const BRIDGE_X1: f64 = -1.0;
const ARM_X2: f64 = 10.0;
const ARM_W: f64 = 9.0;
/// Tie points along each lead: x of each slot pair (last one 11 mm before the pad).
const TIES_X: [f64; 3] = [-61.0, -32.5, -4.0];
/// Cable-tie slot (along the lead x across it) and the slot's gap to the insulation.
const TIE_SLOT: (f64, f64) = (3.0, 1.4);
const TIE_GAP: f64 = 1.0;

// ---- Stage 53 (board of record runs-native21/s53/c53int, sha256 82af7bd9...) ----
/// Probe points (validation/leads/stage53-probe-points.txt).
const J5: (f64, f64) = (132.0, 70.5);
const J2: (f64, f64) = (132.0, 85.5);
const C22_HOLE: (f64, f64) = (190.5, 68.2);
const C22_HOLE_D: f64 = 1.2;
/// Mounting holes (all M3; H1/H2 metal, the rest "M3 NYLON ONLY").
const S53_HOLES: [(&str, f64, f64, bool); 10] = [
    ("H1", 285.0, 135.0, true), ("H2", 223.0, 135.0, true), ("H3", 6.0, 180.0, false), ("H4", 86.0, 180.0, false),
    ("H5", 24.0, 74.0, false), ("H6", 88.0, 100.0, false), ("H7", 128.0, 54.0, false), ("H8", 194.0, 130.0, false),
    ("H9", 142.0, 4.0, false), ("H10", 152.0, 122.0, false),
];
const S53_W: f64 = 290.0;
const S53_H: f64 = 190.0;
/// Würth 7466004R REDCUBE SMT (WP-SMBU), Würth product table and the stage-53
/// footprint note (datasheet rev 001.003): body D7.0, 5.0 mm above the board,
/// M4 internal through-hole thread 6 mm long including the 1.0 mm spigot in the
/// D5.2 NPTH; 50 A; 1.2 N*m. Stage-53 PCB 1.6 mm.
const REDCUBE_D: f64 = 7.0;
const REDCUBE_H: f64 = 5.0;
const REDCUBE_THREAD: f64 = 6.0;
const S53_BOARD_T: f64 = 1.6;
const REDCUBE_TORQUE: f64 = 1.2;
/// Stack parts, (min, max) thickness. Coil lug: not selected by stage 53 yet
/// (example TE PLASTI-GRIP 2-34853-1); bracketed. Probe ring: TE 34108,
/// material 0.79 mm (distributor listing), +/- 0.05 assumed. DIN 125-A M4
/// washer 0.8 mm, +/- 0.1 assumed. DIN 127-B M4 split washer 0.9 mm, 0.8..1.0.
const T_LUG: (f64, f64) = (0.5, 1.2);
const T_RING: (f64, f64) = (0.74, 0.84);
const T_WASHER: (f64, f64) = (0.7, 0.9);
const T_SPLIT: (f64, f64) = (0.8, 1.0);
/// ISO 7045 M4 pan-head lengths and their length tolerance (ISO 4759-1 grade A, js15).
const SCREW_LENGTHS: [f64; 5] = [5.0, 6.0, 8.0, 10.0, 12.0];
const SCREW_L_TOL: f64 = 0.29;
const SCREW_HEAD_K: f64 = 2.6;
/// Minimum thread engagement in the REDCUBE (see the strip check below).
const ENGAGE_MIN: f64 = 3.5;
/// TE 34108 ring: overall length 14.58, width 7.14 (distributor listing); the
/// barrel end is length - width/2 from the stud axis. Barrel axis above the
/// tongue mid-plane: estimate (closed 22-16 AWG barrel, about 3.3 mm OD).
const RING_L: f64 = 14.58;
const RING_W: f64 = 7.14;
const BARREL_DZ: f64 = 1.3;
/// Heat-shrink sleeve over the ring's barrel and neck (docs/hv-leads.md: two
/// layers of RNF-100 3/16 in, recovered wall 0.51 +/- 0.08 mm, overlapping the
/// wire by SLEEVE_ON_WIRE): diameter over the barrel (estimated 3.3 mm OD, as
/// BARREL_DZ) with both layers at maximum wall. The docks' sleeve channels and
/// grooves add 0.5 mm all round.
const SLEEVE_D: f64 = 3.3 + 4.0 * 0.59;
const SLEEVE_ON_WIRE: f64 = 10.0;
const WASHER_D: f64 = 9.0;
/// Stage-53 rule: insulated ring, bare ring <= 10.0 mm wide; J2-J5 exposed
/// metal >= 5.0 mm apart at any rotation.
const S53_RING_MAX_W: f64 = 10.0;
const S53_EXPOSED_GAP: f64 = 5.0;
/// Coil Litz barrels: upturned lugs, barrel axis <= 8 mm from the stud axis,
/// offset away from the other stud along the J2-J5 line, barrel plus insulation
/// OD <= ~7 mm (stage-53 ASSEMBLY.md, J2 constraint). Keep-out half-width 4.5.
const LITZ_OFF: f64 = 8.0;
const LITZ_KO: f64 = 4.5;

// ---- Bench layout (assumptions stated in docs/hv-leads.md) ----
/// Stage 53 is probed on the bench, out of the appliance enclosure, its board top
/// Z_BENCH above an insulating bench. The probe boxes stand on risers so their
/// gland axes are at the spine height.
const Z_BENCH: f64 = 50.0;
/// Spine lead-axis height above the stage-53 board top; spine lead spacing.
const Z_SP: f64 = 50.0;
const S_SP: f64 = 15.0;
/// Spine body section: half-width, depth below the lead axis, top above it (the
/// rod is ROD_H tall on the axis; a horizontal saddle reaches R_RESIN). The dock
/// seats' tops are at Z_SP - SP_BELOW, under the rod.
const SP_HALF_W: f64 = 12.5;
const SP_BELOW: f64 = ROD_H / 2.0;
const SP_ABOVE: f64 = if ROD_H / 2.0 > R_RESIN { ROD_H / 2.0 } else { R_RESIN };
/// Resin envelope around a lead in a spine or dock groove (radius from the lead
/// axis) and the fraction of the lead's surface it wraps. Dock: continuous
/// grooves holding about half the circumference. Spine: the lead is held in
/// snap saddles SADDLE_L long (pitch <= SADDLE_PITCH, saddle_stations) and crosses
/// air between them; a saddle wraps the lead except its snap mouth (about 95
/// degrees of the groove, so 0.75 wraps).
const R_RESIN: f64 = 4.0;
const WRAP_DOCK: f64 = 0.5;
const SADDLE_L: f64 = 12.0;
const SADDLE_PITCH: f64 = 30.0;
const WRAP_SADDLE: f64 = 0.75;
/// Length of each dock's spine seat (along the spine axis, ending at the spine end).
const SEAT_L: f64 = 10.0;
/// Probe 1's risers run in air between the dock-bank fork legs, held by one clip
/// band (RISER_CLIP_Z) each; below the arm band the wrap is the clip's share.
const RISER_CLIP_Z: (f64, f64) = (24.0, 28.0);
const WRAP_RISER: f64 = 0.1;
/// Dock-bank arm band (z): 3.5 mm over the bank-cap tops (29.51).
const ARM_Z: (f64, f64) = (33.0, 39.0);
/// Gap from each probe box's insert outer face to the stage-53 board edge.
const G2: f64 = 10.0;
const G1: f64 = 10.0;
/// Probe 2 (coil): spine axis y, dock (S-bend) start x, half-twist length.
const P2_Y: f64 = (J5.1 + J2.1) / 2.0;
const P2_X_DOCK: f64 = J5.0 - (RING_L - RING_W / 2.0) - 2.0 * R_BEND;
const L_TWIST: f64 = 80.0;
/// Probe 1 (bank): risers at C22_HOLE.x and its mirror about the C22 body
/// centre (161.0..187.5 -> 174.25), in the plane y = C22_HOLE.y.
const C22_BODY_X: (f64, f64) = (161.0, 187.5);
const P1_X: f64 = (C22_BODY_X.0 + C22_BODY_X.1) / 2.0;
const P1_RISER_DX: f64 = C22_HOLE.0 - P1_X;
/// Probe 1 spine end (y) where the plan S-bend toward the risers starts.
const P1_Y_SPINE_END: f64 = 32.0;
/// TIP- strain relief: clamp offset (x) and clamp height band; each S-jog is
/// JOG_L tall so its curvature radius stays >= R_BEND.
const JOG: f64 = 3.0;
const JOG_L: f64 = 15.0;
const CLAMP_L: f64 = 5.0;
// (Z_SP - R_BEND) = 2 JOG_L + CLAMP_L is asserted where the riser is built.
/// Nylon M3 standoffs between stage-53's top face and the dock posts.
const H_SO: f64 = 10.0;
/// Dock post half-width (sits on an M3 hex standoff, 5.5 mm across flats).
const POST_R: f64 = 3.0;

// ---- Trimmer access (probe board frame) and tools ----
/// CT1/CT2 GKG60015 (tools/build.rs envelope: body 4.5 mm, rotor to 5.0 mm);
/// RV1/RV2 Bourns 3296W (10.03 mm tall; screw position to be read from a sample).
const TRIMMERS: [(&str, f64, f64, f64); 4] = [("CT1", 62.0, 23.0, 5.0), ("CT2", 62.0, 47.0, 5.0), ("RV1", 65.0, 7.0, 10.03), ("RV2", 65.0, 63.0, 10.03)];
/// Vessel CA-18 zirconia blade (code 125672): slotted 1.8 x 0.4 mm tip, shank
/// D1.8, 21 mm long (vessel.co.jp product page).
const BLADE: (f64, f64, f64, f64) = (1.8, 0.4, 1.8, 21.0);
/// Guide: sleeve bore, sleeve OD (lid hole = OD + 0.4), flange, and the gap left
/// above the trimmer at the minimum lid height.
const GUIDE_BORE: f64 = 4.3;
const GUIDE_OD: f64 = 7.0;
const GUIDE_FLANGE: (f64, f64) = (14.0, 2.0);
const GUIDE_GAP: f64 = 2.0;
const NOSE_D: f64 = 4.0;
const BLADE_OUT: f64 = 10.0;

// ---- Calibration jigs: replica of the stage-53 attachment region ----
const JIG_X: (f64, f64) = (80.0, 200.0);
const JIG_Y: (f64, f64) = (26.0, 136.0); // reaches under dock-bank's north foot (y 31..39)
const JIG_T: f64 = 6.0;

// ---- Budgets ----
const C_TIP_TARGET: f64 = 12.0;
/// Ladder: five 33 pF +/-5 % C0G sections in series per leg.
const C_SECTION: f64 = 33.0;
const C_SECTION_TOL: f64 = 0.05;
/// Unmodelled reserves inside the per-tip budget.
const RESERVE_BOARD: f64 = 1.0;
const RESERVE_TIP: f64 = 0.5;
const SETBACK: f64 = 20.0;
const BW: f64 = 5.0;
const V_EXT: f64 = 3000.0;
/// Magnetic pickup: 28 A peak (the stage-53 ceiling) at 35 kHz.
const I_COIL: f64 = 28.0;
const F_SW: f64 = 35e3;
const R_REF: f64 = 20.0;
/// Pickup requirement: <= 0.02 % of a 1 kV reading.
const PICKUP_MAX: f64 = 0.2;
/// Clearance from printed parts to stage-53 bodies, and from a lead's surface.
const BODY_CLR: f64 = 1.0;
const LEAD_CLR: f64 = 1.0;

// ======================================================================
// Small vector helpers
// ======================================================================
type P = [f64; 3];
fn add(a: P, b: P) -> P {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
fn sub(a: P, b: P) -> P {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn mul(a: P, k: f64) -> P {
    [a[0] * k, a[1] * k, a[2] * k]
}
fn dist(a: P, b: P) -> f64 {
    let d = sub(a, b);
    (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]).sqrt()
}
fn acosh(x: f64) -> f64 {
    (x + (x * x - 1.0).sqrt()).ln()
}
fn d_area() -> f64 {
    (4.0 * COND_AREA_MM2 / PI).sqrt()
}

// ======================================================================
// Lead paths
// ======================================================================
/// A polyline with a tag per vertex: 0 = paired (spine, spacing S_SP),
/// 1 = dock (fan-out / drop), 2 = gland / entry.
#[derive(Clone)]
struct Path {
    pts: Vec<P>,
    tag: Vec<u8>,
}
impl Path {
    fn new(p: P, tag: u8) -> Self {
        Path { pts: vec![p], tag: vec![tag] }
    }
    fn last(&self) -> P {
        *self.pts.last().unwrap()
    }
    fn line_to(&mut self, p: P, tag: u8) {
        let a = self.last();
        let n = (dist(a, p) / 2.0).ceil().max(1.0) as usize;
        for i in 1..=n {
            self.pts.push(add(a, mul(sub(p, a), i as f64 / n as f64)));
            self.tag.push(tag);
        }
    }
    /// Arc from the current point: centre c, unit u from c to the start point,
    /// unit v = direction of travel at the start, sweep angle th.
    fn arc(&mut self, c: P, u: P, v: P, r: f64, th: f64, tag: u8) {
        let n = ((r * th) / 1.0).ceil().max(4.0) as usize;
        for i in 1..=n {
            let t = th * i as f64 / n as f64;
            self.pts.push(add(c, add(mul(u, r * t.cos()), mul(v, r * t.sin()))));
            self.tag.push(tag);
        }
    }
    /// Plan S-bend (two arcs of R_BEND) moving sideways by `off` along unit `side`
    /// while travelling along unit `fwd`.
    fn s_bend(&mut self, fwd: P, side: P, off: f64, tag: u8) {
        if off.abs() < 1e-9 {
            return;
        }
        let th = (1.0 - off.abs() / (2.0 * R_BEND)).acos();
        let s = if off > 0.0 { side } else { mul(side, -1.0) };
        let p0 = self.last();
        let c1 = add(p0, mul(s, R_BEND));
        self.arc(c1, mul(s, -1.0), fwd, R_BEND, th, tag);
        let p1 = self.last();
        // Second arc turns back: centre on the far side.
        let t1 = add(mul(fwd, th.cos()), mul(s, th.sin()));
        let n1 = sub(p1, c1);
        let n1 = mul(n1, 1.0 / R_BEND);
        let c2 = add(p1, mul(n1, R_BEND));
        self.arc(c2, mul(n1, -1.0), t1, R_BEND, th, tag);
        // Snap to the exact end (removes accumulated rounding).
        let l = self.pts.len();
        let end = add(add(p0, mul(fwd, 2.0 * R_BEND * th.sin())), mul(s, off.abs()));
        self.pts[l - 1] = end;
    }
    fn len(&self) -> f64 {
        self.pts.windows(2).map(|w| dist(w[0], w[1])).sum()
    }
    fn len_tag(&self, tag: u8) -> f64 {
        self.pts.windows(2).zip(self.tag.iter().skip(1)).filter(|(_, &t)| t == tag).map(|(w, _)| dist(w[0], w[1])).sum()
    }
}

struct Lead {
    probe: usize,
    name: &'static str,
    path: Path,
    /// Bare metal from the end of the insulated path to the contact point (ring
    /// tongue to the stud axis, or conductor into the plated hole).
    metal: f64,
    contact: P,
}

/// Probe 2 (coil) lead, j = 0 TIP+ (to J5), 1 TIP- (to J2). Box west of stage 53,
/// facing +x; seen from stage 53 TIP- leaves the box on the north (smaller y)
/// side, so a printed half twist swaps the pair before the dock.
fn probe2_lead(j: usize) -> Lead {
    let sgn = if j == 0 { 1.0 } else { -1.0 }; // TIP+ leaves on the south (+y)
    let y_gl = P2_Y + sgn * GLAND_DY;
    let y_sp = P2_Y + sgn * S_SP / 2.0;
    let x0 = -G2;
    let mut p = Path::new([x0, y_gl, Z_SP], 2);
    p.line_to([x0 + GLAND_OUT_L, y_gl, Z_SP], 2);
    let xt0 = p.last()[0];
    // Converging half twist about the spine axis (y = P2_Y, z = Z_SP): the radius
    // shrinks from the gland pitch to the spine pitch while the pair turns 180
    // degrees, both with a smooth (zero-slope) start and end. TIP+ passes over.
    let n = 120;
    let _ = y_sp;
    for i in 1..=n {
        let t = i as f64 / n as f64;
        let sm = t - (2.0 * PI * t).sin() / (2.0 * PI);
        let phi = PI * sm;
        let r = GLAND_DY + (S_SP / 2.0 - GLAND_DY) * sm;
        let (dy, dz) = if j == 0 { (r * phi.cos(), r * phi.sin()) } else { (-r * phi.cos(), -r * phi.sin()) };
        p.pts.push([xt0 + L_TWIST * t, P2_Y + dy, Z_SP + dz]);
        p.tag.push(0);
    }
    let y_end = if j == 0 { J5.1 } else { J2.1 };
    p.line_to([P2_X_DOCK, y_end, Z_SP], 0);
    // S-bend down to the ring height, in the plane y = y_end.
    let z_r = ring_z(2, j);
    p.arc([P2_X_DOCK, y_end, Z_SP - R_BEND], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0], R_BEND, PI / 2.0, 1);
    p.line_to([P2_X_DOCK + R_BEND, y_end, z_r + R_BEND], 1);
    p.arc([P2_X_DOCK + 2.0 * R_BEND, y_end, z_r + R_BEND], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0], R_BEND, PI / 2.0, 1);
    let stud = if j == 0 { J5 } else { J2 };
    Lead { probe: 2, name: ["TIP+", "TIP-"][j], metal: RING_L - RING_W / 2.0, contact: [stud.0, stud.1, z_r], path: p }
}

/// Probe 1 (bank) lead, j = 0 TIP+ (to J5), 1 TIP- (C22 hole). Box north of
/// stage 53, facing +y; seen from stage 53 TIP- leaves on the east, as needed.
fn probe1_lead(j: usize) -> Lead {
    let sgn = if j == 0 { -1.0 } else { 1.0 };
    let x_gl = P1_X + sgn * GLAND_DY;
    let x_sp = P1_X + sgn * S_SP / 2.0;
    let x_r = P1_X + sgn * P1_RISER_DX;
    let y0 = -G1;
    let mut p = Path::new([x_gl, y0, Z_SP], 2);
    p.line_to([x_gl, y0 + GLAND_OUT_L, Z_SP], 2);
    p.s_bend([0.0, 1.0, 0.0], [1.0, 0.0, 0.0], x_sp - x_gl, 0);
    p.line_to([x_sp, P1_Y_SPINE_END, Z_SP], 0);
    p.s_bend([0.0, 1.0, 0.0], [1.0, 0.0, 0.0], x_r - x_sp, 1);
    let yb = p.last()[1];
    p.arc([x_r, yb, Z_SP - R_BEND], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0], R_BEND, PI / 2.0, 1);
    let yr = p.last()[1];
    if j == 0 {
        let z_r = ring_z(1, 0);
        p.line_to([x_r, yr, z_r + R_BEND], 1);
        p.arc([x_r - R_BEND, yr, z_r + R_BEND], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0], R_BEND, PI / 2.0, 1);
        let end = p.last();
        let metal = ((end[0] - J5.0).powi(2) + (end[1] - J5.1).powi(2)).sqrt();
        Lead { probe: 1, name: "TIP+", metal, contact: [J5.0, J5.1, z_r], path: p }
    } else {
        // Riser, S-jog out to the strain-relief clamp, clamp, S-jog back into the hole.
        // The bend ends at z = Z_SP - R_BEND; the jogs and the clamp fill it exactly.
        let z_c1 = clamp_top();
        assert!((z_c1 + JOG_L - (Z_SP - R_BEND)).abs() < 1e-9, "TIP- riser: jog + clamp + jog must equal the riser height");
        jog(&mut p, x_r, yr, z_c1 + JOG_L, JOG, JOG_L);
        p.line_to([x_r + JOG, yr, z_c1 - CLAMP_L], 1);
        jog(&mut p, x_r + JOG, yr, z_c1 - CLAMP_L, -JOG, JOG_L);
        Lead { probe: 1, name: "TIP-", metal: S53_BOARD_T, contact: [C22_HOLE.0, C22_HOLE.1, 0.0], path: p }
    }
}
/// Spine axis length (insert outer face to the spine end) and the saddle
/// stations along it: the first clears the gland dome by 1 mm, the last ends
/// 1 mm before the dock seat, evenly spaced at <= SADDLE_PITCH (one saddle when
/// the spine is too short for two; it may then rest on the seat).
fn spine_len(probe: usize) -> f64 {
    if probe == 1 { P1_Y_SPINE_END + G1 } else { P2_X_DOCK + G2 }
}
fn saddle_stations(probe: usize) -> Vec<f64> {
    let s0 = GLAND_OUT_L + 1.0 + SADDLE_L / 2.0;
    let s1 = spine_len(probe) - SEAT_L - 1.0 - SADDLE_L / 2.0;
    if s1 <= s0 {
        return vec![s0];
    }
    let n = ((s1 - s0) / SADDLE_PITCH).ceil() as usize;
    (0..=n).map(|i| s0 + (s1 - s0) * i as f64 / n as f64).collect()
}
/// Axial coordinate of a point along probe `probe`'s spine.
fn spine_s(probe: usize, p: P) -> f64 {
    if probe == 1 { p[1] + G1 } else { p[0] + G2 }
}
/// Top of the TIP- strain-relief clamp band (above the board top).
fn clamp_top() -> f64 {
    JOG_L + CLAMP_L
}
/// Cosine S-jog in x while descending JOG_L in z.
fn jog(p: &mut Path, x0: f64, y: f64, z0: f64, a: f64, l: f64) {
    let n = 30;
    for i in 1..=n {
        let t = i as f64 / n as f64;
        p.pts.push([x0 + a / 2.0 * (1.0 - (PI * t).cos()), y, z0 - l * t]);
        p.tag.push(1);
    }
}
/// Height of a ring's barrel axis above the stage-53 board top. J5 stack: coil
/// lug, probe-1 ring, probe-2 ring, washer. J2 stack: coil lug, spacer washer
/// (same thickness as a ring), probe-2 ring, washer.
fn ring_z(probe: usize, _j: usize) -> f64 {
    let lug = (T_LUG.0 + T_LUG.1) / 2.0;
    let ring = (T_RING.0 + T_RING.1) / 2.0;
    let below = if probe == 1 { 0.0 } else { ring };
    REDCUBE_H + lug + below + ring / 2.0 + BARREL_DZ
}

fn leads() -> Vec<Lead> {
    vec![probe1_lead(0), probe1_lead(1), probe2_lead(0), probe2_lead(1)]
}

// ======================================================================
// Stage-53 data (bodies and earthed copper)
// ======================================================================
struct Body {
    refd: String,
    lo: P,
    hi: P,
}
fn load_bodies() -> (Vec<Body>, String) {
    let txt = fs::read_to_string("validation/leads/stage53-bodies.txt").expect("validation/leads/stage53-bodies.txt");
    let mut out = Vec::new();
    let mut hdr = String::new();
    for l in txt.lines() {
        let f: Vec<&str> = l.split_whitespace().collect();
        if l.starts_with("# board") {
            hdr = l.trim_start_matches("# ").to_string();
        }
        if f.first() == Some(&"body") {
            let v: Vec<f64> = f[2..8].iter().map(|s| s.parse().unwrap()).collect();
            out.push(Body { refd: f[1].to_string(), lo: [v[0], v[1], v[2]], hi: [v[3], v[4], v[5]] });
        } else if f.first() == Some(&"nomodel") {
            let v: Vec<f64> = f[2..6].iter().map(|s| s.parse().unwrap()).collect();
            let r = f[1];
            // Heights for footprints the STEP lacks: the REDCUBE from the Würth table,
            // test points and fiducials are flat, a 0603 is <= 1 mm, the RECOM SSOP-36
            // modules are taken as <= 4 mm (not read from a datasheet), the rest
            // (THT parts far from the probes) as 30 mm.
            let h = match r {
                "J2" | "J5" => REDCUBE_H,
                _ if r.starts_with("TP") || r.starts_with("FID") => 0.1,
                "C66" | "R116" => 1.0,
                "U41" | "U42" | "U36" => 4.0,
                _ => 30.0,
            };
            if r == "J2" || r == "J5" {
                let c = if r == "J2" { J2 } else { J5 };
                let rr = REDCUBE_D / 2.0;
                out.push(Body { refd: r.to_string(), lo: [c.0 - rr, c.1 - rr, 0.0], hi: [c.0 + rr, c.1 + rr, h] });
            } else {
                out.push(Body { refd: r.to_string(), lo: [v[0], v[1], 0.0], hi: [v[2], v[3], h] });
            }
        }
    }
    (out, hdr)
}

enum Earth {
    Poly(Vec<(f64, f64)>),
    Seg((f64, f64), (f64, f64), f64),
    Disc((f64, f64), f64),
}
fn load_earth() -> (Vec<Earth>, String) {
    let txt = fs::read_to_string("validation/leads/stage53-earth.txt").expect("validation/leads/stage53-earth.txt");
    let mut out = Vec::new();
    let mut hdr = String::new();
    for l in txt.lines() {
        if l.starts_with("# source") {
            hdr = l.trim_start_matches("# ").to_string();
        }
        let f: Vec<&str> = l.split_whitespace().collect();
        let nums = |s: &[&str]| -> Vec<f64> { s.iter().map(|x| x.parse().unwrap()).collect() };
        match f.first() {
            Some(&"zone") => {
                let v = nums(&f[3..]);
                out.push(Earth::Poly(v.chunks(2).map(|c| (c[0], c[1])).collect()));
            }
            Some(&"pad") => {
                let v = nums(&f[3..]);
                out.push(Earth::Poly(v.chunks(2).map(|c| (c[0], c[1])).collect()));
            }
            Some(&"track") => {
                let v = nums(&f[3..]);
                out.push(Earth::Seg((v[1], v[2]), (v[3], v[4]), v[0] / 2.0));
            }
            Some(&"via") => {
                let v = nums(&f[2..]);
                out.push(Earth::Disc((v[1], v[2]), v[0] / 2.0));
            }
            _ => {}
        }
    }
    (out, hdr)
}
fn seg2(p: (f64, f64), a: (f64, f64), b: (f64, f64)) -> f64 {
    let (dx, dy) = (b.0 - a.0, b.1 - a.1);
    let l2 = dx * dx + dy * dy;
    let t = if l2 == 0.0 { 0.0 } else { (((p.0 - a.0) * dx + (p.1 - a.1) * dy) / l2).clamp(0.0, 1.0) };
    ((p.0 - a.0 - t * dx).powi(2) + (p.1 - a.1 - t * dy).powi(2)).sqrt()
}
fn inside(p: (f64, f64), poly: &[(f64, f64)]) -> bool {
    let mut c = false;
    let n = poly.len();
    for i in 0..n {
        let (a, b) = (poly[i], poly[(i + 1) % n]);
        if (a.1 > p.1) != (b.1 > p.1) && p.0 < a.0 + (p.1 - a.1) * (b.0 - a.0) / (b.1 - a.1) {
            c = !c;
        }
    }
    c
}
/// Plan distance from p to stage-53 earthed copper (0 inside a pour).
fn earth_plan(e: &[Earth], p: (f64, f64)) -> f64 {
    let mut best = f64::INFINITY;
    for it in e {
        let d = match it {
            Earth::Poly(v) => {
                if inside(p, v) {
                    0.0
                } else {
                    (0..v.len()).map(|i| seg2(p, v[i], v[(i + 1) % v.len()])).fold(f64::INFINITY, f64::min)
                }
            }
            Earth::Seg(a, b, w) => (seg2(p, *a, *b) - w).max(0.0),
            Earth::Disc(c, r) => (((p.0 - c.0).powi(2) + (p.1 - c.1).powi(2)).sqrt() - r).max(0.0),
        };
        best = best.min(d);
    }
    best
}
fn box_dist(p: P, lo: P, hi: P) -> f64 {
    let mut s = 0.0;
    for k in 0..3 {
        let d = (lo[k] - p[k]).max(0.0).max(p[k] - hi[k]);
        s += d * d;
    }
    s.sqrt()
}
fn box_gap(alo: P, ahi: P, blo: P, bhi: P) -> f64 {
    let mut s = 0.0;
    for k in 0..3 {
        let d = (blo[k] - ahi[k]).max(0.0).max(alo[k] - bhi[k]);
        s += d * d;
    }
    s.sqrt()
}

// ======================================================================
// Probe boxes (reference Hammond) and other earthed metal in the stage-53 frame
// ======================================================================
/// Gland axis height above the box underside.
fn gland_z_box() -> f64 {
    BOX_FLOOR_T + wire_z()
}
/// Extrusion as four slabs (the tip-end insert is printed, the output plate metal).
fn box_slabs(probe: usize) -> Vec<(P, P)> {
    // Box-local: u along the box away from stage 53 (from the insert's outer
    // face), w across, z from the box underside. Extrusion starts at the bezel.
    let u0 = WALL_T + 1.6; // insert plus bezel lip
    let u1 = u0 + 220.0;
    let (w0, w1) = (-BOX_OUT_W / 2.0, BOX_OUT_W / 2.0);
    let zb = Z_SP - gland_z_box(); // box underside in the stage-53 frame
    let t = BOX_FLOOR_T;
    let local = vec![
        ([u0, w0, 0.0], [u1, w1, t]),
        ([u0, w0, BOX_OUT_H - t], [u1, w1, BOX_OUT_H]),
        ([u0, w0, 0.0], [u1, w0 + t, BOX_OUT_H]),
        ([u0, w1 - t, 0.0], [u1, w1, BOX_OUT_H]),
        ([u1, w0, 0.0], [u1 + 1.6, w1, BOX_OUT_H]), // output end plate (metal)
    ];
    local
        .into_iter()
        .map(|(a, b)| {
            let m = |q: P| -> P {
                if probe == 2 {
                    [-G2 - q[0], P2_Y + q[1], zb + q[2]]
                } else {
                    [P1_X + q[1], -G1 - q[0], zb + q[2]]
                }
            };
            let (pa, pb) = (m(a), m(b));
            ([pa[0].min(pb[0]), pa[1].min(pb[1]), pa[2].min(pb[2])], [pa[0].max(pb[0]), pa[1].max(pb[1]), pa[2].max(pb[2])])
        })
        .collect()
}
/// Earthed metal other than stage-53 copper, as boxes with a label. The heatsink
/// and PS2 entries are assumptions (docs/hv-leads.md).
fn earthed_boxes(bodies: &[Body]) -> Vec<(String, P, P)> {
    let mut v = Vec::new();
    for pr in [1, 2] {
        for (a, b) in box_slabs(pr) {
            v.push((format!("probe-{pr} box"), a, b));
        }
    }
    for &(n, x, y, metal) in &S53_HOLES {
        if metal {
            v.push((format!("{n} metal standoff"), [x - 3.5, y - 3.5, -Z_BENCH], [x + 3.5, y + 3.5, 3.0]));
        }
    }
    for b in bodies {
        if b.refd == "J6" && b.hi[2] > 5.0 {
            v.push(("J6 PE terminal".into(), b.lo, b.hi));
        }
        if b.refd == "PS2" && b.hi[2] > 5.0 {
            v.push(("PS2 (output SELV, taken as earthed)".into(), b.lo, b.hi));
        }
    }
    v.push(("heatsink keep-out (assumed)".into(), [0.0, -60.0, -40.0], [110.0, 8.0, 40.0]));
    v
}

// ======================================================================
// Capacitance models (pF/m)
// ======================================================================
/// Wire of diameter d over a plane at h, uniform er (rigorous for a lone wire in
/// that dielectric when the earth is the plane; used here as the bound with ER_BOUND).
fn wire_plane(d: f64, h: f64, er: f64) -> f64 {
    2.0 * PI * EPS0 * er / acosh((2.0 * h / d).max(1.0001)) * 1e12
}
/// Estimate: silicone shell, then (in a printed part) a resin shell to R_RESIN,
/// then air to a plane at h; series layers.
fn wire_est(h: f64, wrap: f64) -> f64 {
    let (a, od) = (COND_BUNDLE, OD_NOM - OD_TOL);
    let shell = (od / a).ln() / ER_MAX;
    let air = 2.0 * PI * EPS0 / (shell + acosh((2.0 * h / od).max(1.0001))) * 1e12;
    if wrap <= 0.0 {
        return air;
    }
    // Resin sector in parallel with the air sector (radial-field approximation).
    let res = (2.0 * R_RESIN / od).ln() / ER_RESIN;
    let full = 2.0 * PI * EPS0 / (shell + res + acosh((2.0 * h / (2.0 * R_RESIN)).max(1.0001))) * 1e12;
    wrap * full + (1.0 - wrap) * air
}
/// Common-mode share of one leg of a pair at spacing s (both at the same
/// potential): the pair acts as one conductor of radius sqrt(r s); per leg is
/// half, scaled by the lone-wire shell factor of wire_est.
fn pair_leg_est(h: f64, s: f64, wrap: f64) -> f64 {
    let r = OD_NOM / 2.0;
    let req = (r * s).sqrt();
    let air_pair = 2.0 * PI * EPS0 / acosh(h / req) * 1e12 / 2.0;
    let air_lone = 2.0 * PI * EPS0 / acosh(2.0 * h / OD_NOM) * 1e12;
    air_pair * wire_est(h, wrap) / air_lone
}
/// pF/m between two wires at spacing s, uniform er.
fn pair_c(d: f64, s: f64, er: f64) -> f64 {
    PI * EPS0 * er / acosh(s / d) * 1e12
}
/// uH/m loop inductance of a two-wire line, low-frequency internal inductance included.
fn pair_l(d: f64, s: f64) -> f64 {
    (MU0 / PI * acosh(s / d) + 2.0 * MU0 / (8.0 * PI)) * 1e6
}
fn plane_l(d: f64, h: f64) -> f64 {
    (MU0 / (2.0 * PI) * acosh(2.0 * h / d) + MU0 / (8.0 * PI)) * 1e6
}
fn f_res(l_uh: f64, c_pf: f64) -> f64 {
    1.0 / (2.0 * PI * (l_uh * 1e-6 * c_pf * 1e-12).sqrt()) / 1e6
}

// ======================================================================
// Inside the probe box (unchanged geometry, printed bridge)
// ======================================================================
fn wire_z() -> f64 {
    BOARD_TOP + BRIDGE_T - GROOVE + OD_NOM / 2.0
}
fn gland(j: usize) -> (f64, f64) {
    (TIP_PLATE_X, 35.0 + if j == 0 { -GLAND_DY } else { GLAND_DY })
}
fn lead_path_int(j: usize) -> Vec<(f64, f64)> {
    let (gx, gy) = gland(j);
    let (px, py) = W_HV[j];
    vec![(gx, gy), (TIES_X[2], py), (px, py)]
}
fn path_y(p: &[(f64, f64)], x: f64) -> f64 {
    let w = p.windows(2).find(|w| w[0].0 <= x && x <= w[1].0).unwrap();
    w[0].1 + (x - w[0].0) / (w[1].0 - w[0].0) * (w[1].1 - w[0].1)
}
fn path_len2(p: &[(f64, f64)]) -> f64 {
    p.windows(2).map(|w| ((w[1].0 - w[0].0).powi(2) + (w[1].1 - w[0].1).powi(2)).sqrt()).sum()
}
/// Internal length: insert inner face to the landing hole (plan path, step down, hole).
fn l_int(j: usize) -> f64 {
    path_len2(&lead_path_int(j)) + (BRIDGE_T - GROOVE) + BOARD_T + 1.0
}
fn bridge_outline() -> Vec<(f64, f64)> {
    let x0 = bridge_x0();
    let (y0, y1) = (H34[0].1 - ARM_W / 2.0, H34[1].1 + ARM_W / 2.0);
    vec![
        (x0, y0), (ARM_X2, y0), (ARM_X2, y0 + ARM_W), (BRIDGE_X1, y0 + ARM_W),
        (BRIDGE_X1, y1 - ARM_W), (ARM_X2, y1 - ARM_W), (ARM_X2, y1), (x0, y1),
    ]
}
fn bridge_x0() -> f64 {
    TIP_PLATE_X + NUT_T + 1.0
}
fn plate_uv(y: f64, z: f64) -> (f64, f64) {
    (PLATE_CY - y, z - PLATE_CZ)
}

// ======================================================================
// Printed parts in the stage-53 frame (envelope boxes; mech3d adds detail)
// ======================================================================
struct Part {
    name: &'static str,
    resin: &'static str,
    boxes: Vec<(&'static str, P, P)>,
}
fn post(name: &'static str, h: (f64, f64), z1: f64) -> (&'static str, P, P) {
    (name, [h.0 - POST_R, h.1 - POST_R, H_SO], [h.0 + POST_R, h.1 + POST_R, z1])
}
fn hole(n: &str) -> (f64, f64) {
    let h = S53_HOLES.iter().find(|h| h.0 == n).unwrap();
    (h.1, h.2)
}
/// Dock A (probe 2 and the J5/J2 ring guard). Everything within 15 mm of either
/// probe-2 lead is mirror-symmetric about y = P2_Y; the legs beyond are not.
fn dock_coil() -> Part {
    let (x0, x1) = (P2_X_DOCK - SEAT_L, P2_X_DOCK + 2.0 * R_BEND);
    let (yi0, yi1) = (J5.1, J2.1); // faces on the lead planes; mech3d cuts half-depth grooves
    let zc = Z_SP - SP_BELOW;
    let mirror = |y: f64| 2.0 * P2_Y - y;
    let h6 = hole("H6");
    let h7 = hole("H7");
    let gz = (REDCUBE_H + 7.6, REDCUBE_H + 10.6); // guard plate above the screw heads
    Part {
        name: "dock-coil",
        resin: "Flame Retardant",
        boxes: vec![
            ("cradle block", [x0, yi0, 4.0], [x1, yi1, zc]),
            ("spine-2 seat", [x0, P2_Y - SP_HALF_W - 3.0, zc - 6.0], [P2_X_DOCK, P2_Y + SP_HALF_W + 3.0, zc]),
            ("guard plate", [x1, J5.1 - LITZ_OFF + LITZ_KO + BODY_CLR, gz.0], [J5.0 + 9.0, J2.1 + LITZ_OFF - LITZ_KO - BODY_CLR, gz.1]),
            ("guard web", [x1, yi0, 4.0], [J5.0 - 5.0, yi1, gz.1]),
            ("H6 arm", [h6.0 - 3.0, yi1, zc - 12.0], [h6.0 + 3.0, h6.1 + 3.5, zc - 6.0]),
            post("H6 post", h6, zc - 6.0),
            ("H6 mirror stub", [h6.0 - 3.0, mirror(J2.1 + 15.0), zc - 12.0], [h6.0 + 3.0, yi0, zc - 6.0]),
            ("H7 arm", [h7.0 - POST_R, h7.1 - POST_R, gz.0], [J5.0 - LITZ_KO - BODY_CLR, yi0, gz.1]),
            post("H7 post", h7, gz.1),
            ("H7 mirror stub", [h7.0 - POST_R, yi1, gz.0], [J5.0 - LITZ_KO - BODY_CLR, mirror(J5.1 - 7.5), gz.1]),
        ],
    }
}
/// Dock B (probe 1, C22 strain relief). Mirror-symmetric about x = P1_X except
/// the two posts (H10 at -22.25, H8 at +19.75) and the strain-relief clamp.
fn dock_bank() -> Part {
    let h10 = hole("H10");
    let h8 = hole("H8");
    let (za, zb) = ARM_Z;
    let xl = P1_X - P1_RISER_DX; // TIP+ riser
    let xr = P1_X + P1_RISER_DX; // TIP- riser
    let yr = C22_HOLE.1;
    let fork = |x: f64, y: f64| ([x - 1.5, y - 1.5, 0.0], [x + 1.5, y + 1.5, zb]);
    let (fwl, fwh) = (xl - 3.0, xr + 3.0);
    let (f1, f2, f3, f4) = (fork(fwl, yr - 6.0), fork(fwl, yr + 6.0), fork(fwh, yr - 6.0), fork(fwh, yr + 6.0));
    let zc1 = clamp_top();
    Part {
        name: "dock-bank",
        resin: "Flame Retardant",
        boxes: vec![
            post("H10 post", h10, za),
            post("H8 post", h8, za),
            ("cross member", [h10.0 - 3.5, h10.1 - 3.5, za], [h8.0 + 3.5, h8.1 + 3.5, zb]),
            ("arm", [P1_X - 13.0, P1_Y_SPINE_END - SEAT_L, za], [P1_X + 13.0, h10.1, zb]),
            ("spine-1 seat", [P1_X - SP_HALF_W - 3.0, P1_Y_SPINE_END - SEAT_L, zb], [P1_X + SP_HALF_W + 3.0, P1_Y_SPINE_END, Z_SP - SP_BELOW]),
            ("north foot", [P1_X - 4.0, 31.0, 0.0], [P1_X + 4.0, 39.0, za]),
            // Top on the lead plane: mech3d cuts half-depth grooves along the plan S-bends.
            ("guide plate", [xl - 3.5, P1_Y_SPINE_END, zb], [xr + 3.5, yr - 7.5, Z_SP]),
            ("riser bridge", [fwl - 1.5, yr - 7.5, za], [fwh + 1.5, yr + 7.5, zb]),
            ("fork W1", f1.0, f1.1),
            ("fork W2", f2.0, f2.1),
            ("fork E1", f3.0, f3.1),
            ("fork E2", f4.0, f4.1),
            ("riser clip W", [fwl - 1.5, yr - 7.5, RISER_CLIP_Z.0], [xl + 1.0, yr + 7.5, RISER_CLIP_Z.1]),
            ("riser clip E", [xr - 1.0, yr - 7.5, RISER_CLIP_Z.0], [fwh + 1.5, yr + 7.5, RISER_CLIP_Z.1]),
            // Spans the fork legs' inner faces (fused to them); the tie round the
            // legs at this band presses the lead into the clamp channel.
            ("TIP- clamp", [xr + JOG - 3.0, yr - 4.5, zc1 - CLAMP_L], [fwh + 1.5, yr + 4.5, zc1]),
        ],
    }
}
/// Spine envelopes in the stage-53 frame (straight runs; the twist module's
/// envelope covers the rotating pair).
fn spines() -> Vec<Part> {
    let p2: Vec<_> = leads().into_iter().filter(|l| l.probe == 2).collect();
    let xt0 = -G2 + GLAND_OUT_L;
    let _ = p2;
    let hw = SP_HALF_W;
    let w_entry = GLAND_DY + 6.0;
    let p1_conv = 2.0 * R_BEND * (1.0 - (GLAND_DY - S_SP / 2.0) / (2.0 * R_BEND)).acos().sin();
    vec![
        Part {
            name: "spine-coil",
            resin: "Flame Retardant",
            boxes: vec![
                ("entry", [-G2, P2_Y - w_entry, Z_SP - SP_BELOW], [xt0, P2_Y + w_entry, Z_SP + SP_ABOVE]),
                ("converging half twist", [xt0, P2_Y - w_entry, Z_SP - w_entry], [xt0 + L_TWIST, P2_Y + w_entry, Z_SP + w_entry]),
                ("straight", [xt0 + L_TWIST, P2_Y - hw, Z_SP - SP_BELOW], [P2_X_DOCK, P2_Y + hw, Z_SP + SP_ABOVE]),
            ],
        },
        Part {
            name: "spine-bank",
            resin: "Flame Retardant",
            boxes: vec![
                ("entry", [P1_X - w_entry, -G1, Z_SP - SP_BELOW], [P1_X + w_entry, -G1 + GLAND_OUT_L + p1_conv, Z_SP + SP_ABOVE]),
                ("straight", [P1_X - hw, -G1 + GLAND_OUT_L + p1_conv, Z_SP - SP_BELOW], [P1_X + hw, P1_Y_SPINE_END, Z_SP + SP_ABOVE]),
            ],
        },
    ]
}

// ======================================================================
// JSON writer (no dependencies)
// ======================================================================
struct J;
impl J {
    fn p(v: P) -> String {
        // Right-handed: y negated.
        format!("[{:.4},{:.4},{:.4}]", v[0], -v[1], v[2])
    }
    fn pb(v: P) -> String {
        format!("[{:.4},{:.4},{:.4}]", v[0], -v[1], v[2])
    }
    fn pts(v: &[P]) -> String {
        format!("[{}]", v.iter().map(|q| J::p(*q)).collect::<Vec<_>>().join(","))
    }
    fn bx(lo: P, hi: P) -> String {
        // Right-handed box: y range flips.
        format!("{{\"lo\":[{:.4},{:.4},{:.4}],\"hi\":[{:.4},{:.4},{:.4}]}}", lo[0], -hi[1], lo[2], hi[0], -lo[1], hi[2])
    }
}

// ======================================================================
// Section view (probe-box internals; unchanged layout, printed parts)
// ======================================================================
fn svg() -> String {
    let k = 4.0;
    let mut s = String::new();
    let (w, h) = (1040.0, 820.0);
    writeln!(s, "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" viewBox=\"0 0 {w} {h}\" font-family=\"Helvetica, Arial, sans-serif\" font-size=\"12\">").unwrap();
    writeln!(s, "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>").unwrap();
    writeln!(s, "<defs><marker id=\"a\" viewBox=\"0 0 10 10\" refX=\"10\" refY=\"5\" markerWidth=\"7\" markerHeight=\"7\" orient=\"auto-start-reverse\"><path d=\"M0,0 L10,5 L0,10 z\" fill=\"#333\"/></marker></defs>").unwrap();
    let px = |x: f64| 60.0 + (x - TIP_PLATE_X + 20.0) * k;
    let py = |y: f64| 70.0 + (y + SIDE_GAP) * k;
    writeln!(s, "<text x=\"20\" y=\"28\" font-size=\"16\" font-weight=\"bold\">Rev C HV lead entry: plan (top) and section through TIP+ (bottom). Generated by tools/leads.rs; dimensions in mm.</text>").unwrap();
    writeln!(s, "<text x=\"20\" y=\"50\" font-size=\"13\">Plan, lid removed (Hammond reference). Grey: aluminium extrusion. Blue-grey: printed resin (wall insert, lead bridge; no insulation credit). Green: probe board.</text>").unwrap();
    let xr = 152.0;
    let resin = "#c9d6e3";
    let resin_s = "#4a6278";
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#888\" stroke-width=\"6\"/>", px(TIP_PLATE_X), py(-SIDE_GAP), px(xr) - px(TIP_PLATE_X), BOX_W * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#cfe8cf\" stroke=\"#2e7d32\"/>", px(0.0), py(0.0), (xr - 4.0) * k, 70.0 * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"white\" stroke=\"#2e7d32\"/>", px(0.0), py(34.2), 36.0 * k, 1.6 * k).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">probe board (ladder from x = 12.5)</text>", px(40.0), py(36.5)).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"{resin}\" stroke=\"{resin_s}\"/>", px(TIP_PLATE_X - WALL_T), py(-SIDE_GAP), WALL_T * k, BOX_W * k).unwrap();
    let br = bridge_outline();
    let pts: Vec<String> = br.iter().map(|&(x, y)| format!("{:.1},{:.1}", px(x), py(y))).collect();
    writeln!(s, "<polygon points=\"{}\" fill=\"{resin}\" fill-opacity=\"0.8\" stroke=\"{resin_s}\"/>", pts.join(" ")).unwrap();
    for &(x, y) in &H34 {
        writeln!(s, "<circle cx=\"{}\" cy=\"{}\" r=\"{}\" fill=\"white\" stroke=\"#333\"/>", px(x), py(y), 1.7 * k).unwrap();
    }
    for j in 0..2 {
        let col = if j == 0 { "#c62828" } else { "#222" };
        let p = lead_path_int(j);
        let mut d = format!("M{:.1},{:.1}", px(p[0].0 - 25.0), py(p[0].1));
        for q in &p {
            write!(d, " L{:.1},{:.1}", px(q.0), py(q.1)).unwrap();
        }
        writeln!(s, "<path d=\"{d}\" fill=\"none\" stroke=\"{col}\" stroke-width=\"{}\" stroke-linecap=\"round\"/>", OD_NOM * k).unwrap();
        let (gx, gy) = gland(j);
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", px(gx - WALL_T - GLAND_OUT_L), py(gy - GLAND_OUT_D / 2.0), GLAND_OUT_L * k, GLAND_OUT_D * k).unwrap();
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", px(gx), py(gy - GLAND_NUT_AC / 2.0), NUT_T * k, GLAND_NUT_AC * k).unwrap();
        let (wx, wy) = W_HV[j];
        writeln!(s, "<circle cx=\"{}\" cy=\"{}\" r=\"{}\" fill=\"#d4a017\" stroke=\"#7a5c00\"/>", px(wx), py(wy), PAD_R * k).unwrap();
        for &tx in &TIES_X {
            let y = path_y(&p, tx);
            writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#fff\" stroke=\"#1565c0\" stroke-width=\"2\"/>", px(tx - 1.25), py(y - OD_NOM / 2.0 - TIE_GAP - TIE_SLOT.1), 2.5 * k, (OD_NOM + 2.0 * TIE_GAP + 2.0 * TIE_SLOT.1) * k).unwrap();
        }
        writeln!(s, "<text x=\"{}\" y=\"{}\">W_HV{} ({wx}, {wy}) {}</text>", px(wx) + 12.0, py(wy) + if j == 0 { -10.0 } else { 20.0 }, j + 1, ["TIP+", "TIP-"][j]).unwrap();
    }
    writeln!(s, "<text x=\"{}\" y=\"{}\" fill=\"#1565c0\">blue: cable ties through slot pairs at x = {}, {}, {}</text>", px(-56.0), py(55.0), TIES_X[0], TIES_X[1], TIES_X[2]).unwrap();
    dim(&mut s, (px(TIP_PLATE_X), py(73.0)), (px(0.0), py(73.0)), &format!("{:.1} insert inner face to board edge", -TIP_PLATE_X));
    dim(&mut s, (px(-8.0), py(27.0)), (px(-8.0), py(43.0)), "16.0");
    dim(&mut s, (px(TIP_PLATE_X - 14.0), py(35.0 - GLAND_DY)), (px(TIP_PLATE_X - 14.0), py(35.0 + GLAND_DY)), &format!("{:.0} gland pitch", 2.0 * GLAND_DY));
    dim(&mut s, (px(20.0), py(-SIDE_GAP)), (px(20.0), py(0.0)), &format!("{SIDE_GAP:.1}"));
    writeln!(s, "<text x=\"{}\" y=\"{}\" font-size=\"11\">leads leave left into the printed spine (15 mm pitch), which docks on stage 53</text>", 20.0, py(-SIDE_GAP) - 4.0).unwrap();
    let top = py(BOX_W - SIDE_GAP) + 70.0;
    let sx = |x: f64| px(x);
    let sz = |z: f64| top + (BOX_H + 10.0 - z) * k;
    writeln!(s, "<text x=\"20\" y=\"{}\" font-size=\"13\">Section A-A on y = {} (TIP+ lead), side view. z from the inner floor.</text>", top - 12.0, W_HV[0].1).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#888\" stroke-width=\"6\"/>", sx(TIP_PLATE_X), sz(BOX_H), sx(xr) - sx(TIP_PLATE_X), BOX_H * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"{resin}\" stroke=\"{resin_s}\"/>", sx(TIP_PLATE_X - WALL_T), sz(BOX_H + 1.5), WALL_T * k, (BOX_H + 3.0) * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#cfe8cf\" stroke=\"#2e7d32\"/>", sx(0.0), sz(BOARD_TOP), (xr - 4.0) * k, BOARD_T * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"{resin}\" stroke=\"{resin_s}\"/>", sx(bridge_x0()), sz(BOARD_TOP + BRIDGE_T), (BRIDGE_X1 - bridge_x0()) * k, BRIDGE_T * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"{resin}\" fill-opacity=\"0.5\" stroke=\"{resin_s}\" stroke-dasharray=\"4 3\"/>", sx(BRIDGE_X1), sz(BOARD_TOP + BRIDGE_T), (ARM_X2 - BRIDGE_X1) * k, BRIDGE_T * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#fff8e1\" stroke=\"#999\" stroke-dasharray=\"4 3\"/>", sx(3.0), sz(BOARD_UNDER), 4.0 * k, BOARD_UNDER * k).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\" font-size=\"11\">nylon standoff H3 (y = 5, behind)</text>", sx(-2.0) - 40.0, sz(8.0)).unwrap();
    let wz = wire_z();
    let (wx, _) = W_HV[0];
    let d = format!(
        "M{:.1},{:.1} L{:.1},{:.1} L{:.1},{:.1} Q{:.1},{:.1} {:.1},{:.1} L{:.1},{:.1}",
        sx(TIP_PLATE_X - 30.0), sz(wz), sx(TIES_X[2]), sz(wz), sx(-1.0), sz(wz),
        sx(wx - 1.5), sz(wz), sx(wx), sz(BOARD_TOP + 0.8), sx(wx), sz(BOARD_UNDER - TAIL_DOWN)
    );
    writeln!(s, "<path d=\"{d}\" fill=\"none\" stroke=\"#c62828\" stroke-width=\"{}\" stroke-linecap=\"round\"/>", OD_NOM * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#d4a017\"/>", sx(wx - PAD_R), sz(BOARD_TOP + 0.1), 2.0 * PAD_R * k, 0.3 * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#d4a017\"/>", sx(wx - PAD_R), sz(BOARD_UNDER), 2.0 * PAD_R * k, 0.3 * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", sx(TIP_PLATE_X - WALL_T - GLAND_OUT_L), sz(wz + GLAND_OUT_D / 2.0), GLAND_OUT_L * k, GLAND_OUT_D * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", sx(TIP_PLATE_X), sz(wz + GLAND_NUT_AC / 2.0), NUT_T * k, GLAND_NUT_AC * k).unwrap();
    for &tx in &TIES_X {
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#1565c0\" stroke-width=\"2\"/>", sx(tx - 1.25), sz(wz + OD_NOM / 2.0 + 0.6), 2.5 * k, (OD_NOM + BRIDGE_T + 1.8) * k).unwrap();
    }
    let up = BOX_H - (BOARD_TOP + FILLET_UP);
    let down = BOARD_UNDER - TAIL_DOWN;
    dim(&mut s, (sx(wx + 6.0), sz(BOARD_TOP + FILLET_UP)), (sx(wx + 6.0), sz(BOX_H)), &format!("{up:.2} joint to lid (>= 20)"));
    dim(&mut s, (sx(wx + 6.0), sz(0.0)), (sx(wx + 6.0), sz(BOARD_UNDER - TAIL_DOWN)), &format!("{down:.2} tail to floor (>= 20)"));
    dim(&mut s, (sx(-12.0), sz(BOARD_TOP)), (sx(-12.0), sz(BOARD_TOP + BRIDGE_T - GROOVE + OD_NOM + OD_TOL)), &format!("{:.2} loop (<= 5.5)", BRIDGE_T - GROOVE + OD_NOM + OD_TOL));
    dim(&mut s, (sx(TIP_PLATE_X + 12.0), sz(wz)), (sx(TIP_PLATE_X + 12.0), sz(BOX_H)), &format!("{:.2} lead axis to lid", BOX_H - wz));
    dim(&mut s, (sx(60.0), sz(0.0)), (sx(60.0), sz(BOARD_UNDER)), &format!("{BOARD_UNDER:.1}"));
    dim(&mut s, (sx(80.0), sz(0.0)), (sx(80.0), sz(BOX_H)), &format!("{BOX_H:.2} min internal"));
    writeln!(s, "<text x=\"{}\" y=\"{}\">W_HV1 joint</text>", sx(wx) - 120.0, sz(BOARD_TOP) - 40.0).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">printed wall insert {WALL_T} mm (seat {SEAT_T}), PG7 gland</text>", sx(TIP_PLATE_X + 3.0), sz(BOX_H + 4.0)).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">printed lead bridge {BRIDGE_T} mm, {GROOVE} mm lead grooves (arms dashed)</text>", sx(-45.0), sz(BOARD_TOP) + 22.0).unwrap();
    writeln!(s, "</svg>").unwrap();
    s
}
fn esc(t: &str) -> String {
    t.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}
fn dim(s: &mut String, a: (f64, f64), b: (f64, f64), label: &str) {
    let label = esc(label);
    writeln!(s, "<line x1=\"{:.1}\" y1=\"{:.1}\" x2=\"{:.1}\" y2=\"{:.1}\" stroke=\"#333\" marker-start=\"url(#a)\" marker-end=\"url(#a)\"/>", a.0, a.1, b.0, b.1).unwrap();
    let (mx, my) = ((a.0 + b.0) / 2.0, (a.1 + b.1) / 2.0);
    writeln!(s, "<text x=\"{:.1}\" y=\"{:.1}\" font-size=\"11\" fill=\"#333\">{label}</text>", mx + 5.0, my - 4.0).unwrap();
}

// ======================================================================
fn main() {
    let mut r = String::new();
    let mut failed = Vec::new();
    let mut gate = |ok: bool, what: String, r: &mut String| {
        writeln!(r, "{} {what}", if ok { "PASS" } else { "FAIL" }).unwrap();
        if !ok {
            failed.push(what);
        }
    };
    let (bodies, bodies_src) = load_bodies();
    let (earth, earth_src) = load_earth();
    let leads = leads();

    writeln!(r, "Rev C HV leads, option B (two dedicated probes): geometry, capacitance, inductance, resonance, pickup,").unwrap();
    writeln!(r, "setback and clearance budget (generated by tools/leads.rs; do not edit). Calculated from stated geometry,").unwrap();
    writeln!(r, "datasheet dimensions and the stage-53 board of record; nothing here is measured. 'Bound' marks a rigorous").unwrap();
    writeln!(r, "inequality given the stated permittivity bracket and geometry; 'estimate' marks a model value the bench must confirm.").unwrap();
    writeln!(r, "Stage-53 inputs: {bodies_src}; earthed copper {earth_src}.").unwrap();
    writeln!(r, "Assumption: stage 53 is probed on the bench, out of the appliance enclosure, board top {Z_BENCH:.0} mm above an insulating").unwrap();
    writeln!(r, "bench; the coil and its load sit >= 300 mm from both spines (the coil's own field is outside this model).\n").unwrap();

    // ---- Ladder and wire ----
    let c_in_nom = C_SECTION / 5.0;
    let c_in_max = C_SECTION * (1.0 + C_SECTION_TOL) / 5.0;
    let c_in_min = C_SECTION * (1.0 - C_SECTION_TOL) / 5.0;
    writeln!(r, "Ladder input capacitance per tip (5 x 33 pF +/-5 % in series): {c_in_min:.3}..{c_in_max:.3} pF (nominal {c_in_nom:.3}).").unwrap();
    let (da, db) = (d_area(), COND_BUNDLE);
    let (od_lo, od_hi) = (OD_NOM - OD_TOL, OD_NOM + OD_TOL);
    writeln!(r, "Wire: conductor {da:.3} mm equal-area, {db:.2}..{COND_MAX:.2} mm bundle; OD {OD_NOM:.2} +/- {OD_TOL:.2} mm; silicone er {ER_MIN}..{ER_MAX}; resin er {ER_RESIN} (bound {ER_BOUND}).").unwrap();
    let e_cond = V_EXT / (COND_MAX / 2.0 * (od_lo / COND_MAX).ln()) / 1000.0;
    writeln!(r, "Insulation stress at the conductor, wire on earthed metal (coaxial limit, thinnest wall, largest conductor): {e_cond:.2} kV/mm at {V_EXT:.0} V.").unwrap();
    gate(V_EXT / 1000.0 * 1.5 <= WIRE_HIPOT_KV_DC, format!("incoming hipot {WIRE_HIPOT_KV_DC:.0} kV DC >= 1.5 x the {:.0} kV extension (acceptance basis of the unrated wire)", V_EXT / 1000.0), &mut r);
    gate(V_EXT / 1000.0 <= WIRE_RATED_KV_DC / 3.0, format!("rated fallback wire {WIRE_RATED_KV_DC:.0} kV DC >= 3 x the {:.0} kV extension", V_EXT / 1000.0), &mut r);

    // ---- Geometry summary ----
    writeln!(r, "\nGeometry (stage-53 frame: KiCad x, y; z above the stage-53 board top):").unwrap();
    writeln!(r, "  spine lead axis z = {Z_SP:.1} mm ({:.1} mm above the bench), lead pitch {S_SP:.1} mm, bend radius >= {R_BEND:.0} mm ({:.1} x max OD).", Z_SP + Z_BENCH, R_BEND / od_hi).unwrap();
    writeln!(r, "  probe 1 (bank): box north of stage 53, insert outer face at y = {:.1}, axis x = {P1_X:.2} (C22 body centre); spine to y = {P1_Y_SPINE_END:.1};", -G1).unwrap();
    writeln!(r, "    risers at x = {:.2} (TIP+) and {:.2} (TIP-, the C22 hole), {:.2} mm outside each end of the C22 body, plane y = {:.1}.", P1_X - P1_RISER_DX, P1_X + P1_RISER_DX, P1_RISER_DX - (C22_BODY_X.1 - C22_BODY_X.0) / 2.0, C22_HOLE.1).unwrap();
    writeln!(r, "  probe 2 (coil): box west of stage 53, insert outer face at x = {:.1}, axis y = {P2_Y:.1}; half twist over {L_TWIST:.0} mm; spine to x = {P2_X_DOCK:.1};", -G2).unwrap();
    writeln!(r, "    S-bend down in the planes y = {:.1} (TIP+) and {:.1} (TIP-) to the ring barrels at x = {:.2}.", J5.1, J2.1, J5.0 - (RING_L - RING_W / 2.0)).unwrap();
    writeln!(r, "  probe-box riser (Hammond reference, gland axis {:.2} mm above the box underside): {:.1} mm.", gland_z_box(), Z_SP + Z_BENCH - gland_z_box()).unwrap();
    for l in &leads {
        writeln!(r, "  probe {} {}: insulated length {:.1} mm (paired {:.1}, dock {:.1}, entry {:.1}) + {:.2} mm bare metal to the contact.", l.probe, l.name, l.path.len(), l.path.len_tag(0), l.path.len_tag(1), l.path.len_tag(2), l.metal).unwrap();
    }
    // Minimum bend radius along each path (three-point curvature).
    let mut rmin = f64::INFINITY;
    for l in &leads {
        let p = &l.path.pts;
        for i in 1..p.len() - 1 {
            let (a, b, c) = (p[i - 1], p[i], p[i + 1]);
            let (ab, bc, ca) = (dist(a, b), dist(b, c), dist(c, a));
            if ab < 0.2 || bc < 0.2 {
                continue;
            }
            let s = (ab + bc + ca) / 2.0;
            let area = (s * (s - ab) * (s - bc) * (s - ca)).max(0.0).sqrt();
            if area > 1e-6 {
                rmin = rmin.min(ab * bc * ca / (4.0 * area));
            }
        }
    }
    gate(rmin >= R_BEND - 0.5, format!("every external lead bend radius >= {R_BEND:.0} mm (smallest {rmin:.1} mm)"), &mut r);

    // ---- J5 / J2 stud stack ----
    writeln!(r, "\nJ5/J2 stud stacks (Würth 7466004R: M4 through-thread {REDCUBE_THREAD:.0} mm incl. the 1.0 mm spigot; body {REDCUBE_H:.0} mm; board {S53_BOARD_T} mm):").unwrap();
    let tip_limit = REDCUBE_THREAD + (S53_BOARD_T - 1.0) - 0.1; // stop 0.1 mm above the board underside
    let stacks: [(&str, Vec<(f64, f64)>); 2] = [
        ("J5: coil lug + probe-1 ring + probe-2 ring + DIN 125 washer", vec![T_LUG, T_RING, T_RING, T_WASHER]),
        ("J2: coil lug + DIN 125 spacer + probe-2 ring + DIN 125 washer", vec![T_LUG, T_WASHER, T_RING, T_WASHER]),
    ];
    let mut chosen = Vec::new();
    for (name, parts) in &stacks {
        for split in [false, true] {
            let mut lo: f64 = parts.iter().map(|p| p.0).sum();
            let mut hi: f64 = parts.iter().map(|p| p.1).sum();
            if split {
                lo += T_SPLIT.0;
                hi += T_SPLIT.1;
            }
            let ok: Vec<f64> = SCREW_LENGTHS.iter().copied().filter(|&l| l - SCREW_L_TOL - hi >= ENGAGE_MIN && l + SCREW_L_TOL - lo <= tip_limit).collect();
            writeln!(r, "  {name}{}: stack {lo:.2}..{hi:.2} mm; ISO 7045 lengths giving engagement >= {ENGAGE_MIN} mm and tip <= {tip_limit:.1} mm below the body top at every corner: {}",
                if split { " + DIN 127 split washer" } else { "" },
                if ok.is_empty() { "none (measure the stack and choose)".to_string() } else { ok.iter().map(|l| format!("M4x{l:.0}")).collect::<Vec<_>>().join(", ") }).unwrap();
            if !split {
                chosen.push((name.to_string(), lo, hi, ok.first().copied()));
            }
        }
    }
    let all8 = chosen.iter().all(|c| c.3 == Some(8.0));
    for (name, lo, hi, l) in &chosen {
        if let Some(l) = l {
            writeln!(r, "    {}: M4x{l:.0} engages {:.2}..{:.2} mm.", &name[..2], l - SCREW_L_TOL - hi, l + SCREW_L_TOL - lo).unwrap();
        }
    }
    gate(all8, "J5 and J2 stacks (flat washers, no split washer) both take an ISO 7045 M4x8 pan head at every tolerance corner".into(), &mut r);
    // Thread strip check at the stage-53 torque: preload F = T / (K d), K = 0.2.
    let preload = REDCUBE_TORQUE / (0.2 * 0.004);
    let shear_area = PI * 3.242 * ENGAGE_MIN * 0.75; // mm2, M4 minor dia 3.242, 0.75 shear-area factor
    let tau = 150.0; // MPa, copper-alloy shear strength taken low
    writeln!(r, "  thread strip: {REDCUBE_TORQUE} N*m gives ~{preload:.0} N preload (K = 0.2); {ENGAGE_MIN} mm of engaged thread in copper alloy at {tau:.0} MPa shear holds ~{:.0} N.", shear_area * tau).unwrap();
    gate(shear_area * tau >= 2.0 * preload, format!("minimum engagement strips at >= 2 x the 1.2 N*m preload ({:.1} x)", shear_area * tau / preload), &mut r);
    let ring_exposed = (S53_RING_MAX_W.min(RING_W.max(WASHER_D))) / 2.0;
    let gap = (J2.1 - J5.1) - 2.0 * (RING_W.max(WASHER_D) / 2.0);
    writeln!(r, "  TE 34108 ring width {RING_W} mm (<= {S53_RING_MAX_W} stage-53 limit); washer {WASHER_D} mm; J5-J2 exposed-metal gap at any rotation {gap:.1} mm (ring and barrel sleeved; exposed radius {ring_exposed:.2}).").unwrap();
    gate(RING_W <= S53_RING_MAX_W && gap >= S53_EXPOSED_GAP, format!("probe rings keep the stage-53 J2-J5 exposed-metal gap >= {S53_EXPOSED_GAP} mm ({gap:.1} mm)"), &mut r);
    let z1 = ring_z(1, 0);
    let z2a = ring_z(2, 0);
    let z2b = REDCUBE_H + (T_LUG.0 + T_LUG.1) / 2.0 + (T_WASHER.0 + T_WASHER.1) / 2.0 + (T_RING.0 + T_RING.1) / 4.0 + BARREL_DZ;
    writeln!(r, "  barrel axis heights: probe-1 ring {z1:.2} mm; probe-2 rings {z2a:.2} (J5) / {z2b:.2} (J2) mm, so probe 2's legs differ by {:.3} mm.", (z2a - z2b).abs()).unwrap();

    // ---- Per-tip capacitance ----
    writeln!(r, "\nPer-tip capacitance to earth. Earth = stage-53 PE and SELV copper (stage53-earth.txt, taken at the board top), J6, H1/H2,").unwrap();
    writeln!(r, "PS2 and the heatsink keep-out (assumptions), both probe boxes' extrusions and a {Z_BENCH:.0} mm-down bench plane (treated as earthed).").unwrap();
    writeln!(r, "Each 1 mm of lead takes the nearest earth distance h; estimate = series silicone / resin / air layers to a plane at h (where").unwrap();
    writeln!(r, "the other leg is within s <= h/2: one conductor of radius sqrt(r s), half per leg); bound = lone conductor ({COND_MAX} mm) over a plane at h, er {ER_BOUND} throughout.").unwrap();
    let eboxes = earthed_boxes(&bodies);
    let bench = |p: P| p[2] + Z_BENCH;
    let near = |p: P| -> (f64, String) {
        let mut best = (f64::INFINITY, String::new());
        let dpl = earth_plan(&earth, (p[0], p[1]));
        let d = (dpl * dpl + p[2] * p[2]).sqrt();
        if d < best.0 {
            best = (d, "stage-53 PE/SELV copper".into());
        }
        for (n, lo, hi) in &eboxes {
            let d = box_dist(p, *lo, *hi);
            if d < best.0 {
                best = (d, n.clone());
            }
        }
        if bench(p) < best.0 {
            best = (bench(p), "bench".into());
        }
        best
    };
    let c_int_est;
    let c_int_bound;
    {
        let wz = wire_z();
        let (h_lid, h_floor) = (BOX_H - wz, wz);
        let a = h_lid + h_floor;
        let geom = (2.0 * a / (PI * od_hi / 2.0) * (PI * h_floor / a).sin()).ln();
        let between = 2.0 * PI * EPS0 / ((od_lo / db).ln() / ER_MAX + geom) * 1e12;
        c_int_est = between * l_int(0) / 1000.0;
        c_int_bound = 2.0 * PI * EPS0 * ER_BOUND / (2.0 * h_lid.min(h_floor) / COND_MAX).ln() * 1e12 * l_int(0) / 1000.0;
        writeln!(r, "  inside the box (Hammond reference): {:.2} mm per lead, axis {wz:.2} mm above the floor, {h_lid:.2} mm below the lid: estimate {c_int_est:.2} pF (coaxial bound at the lid distance, er {ER_BOUND}: {c_int_bound:.2} pF).", l_int(0)).unwrap();
    }
    let fixed = c_in_max + RESERVE_BOARD + RESERVE_TIP + c_int_est;
    let mut per_leg = Vec::new();
    for l in &leads {
        let other = leads.iter().find(|o| o.probe == l.probe && o.name != l.name).unwrap();
        let (mut est, mut bnd, mut hmin, mut what) = (0.0, 0.0, f64::INFINITY, String::new());
        let mut by_tag = [0.0f64; 3];
        let p = &l.path.pts;
        for i in 1..p.len() {
            let seg = dist(p[i - 1], p[i]) / 1000.0;
            let mid = mul(add(p[i - 1], p[i]), 0.5);
            let (h, n) = near(mid);
            if h < hmin {
                hmin = h;
                what = n;
            }
            let tag = l.path.tag[i];
            // Local spacing to the other leg; the pair model needs s <= h / 2.
            let s_loc = other.path.pts.iter().map(|q| dist(*q, mid)).fold(f64::INFINITY, f64::min);
            let wrap = match tag {
                0 => {
                    let sm = spine_s(l.probe, mid);
                    if saddle_stations(l.probe).iter().any(|st| (sm - st).abs() <= SADDLE_L / 2.0) { WRAP_SADDLE } else { 0.0 }
                }
                1 if l.probe == 1 && mid[2] < ARM_Z.1 => WRAP_RISER,
                1 => WRAP_DOCK,
                _ => 0.0,
            };
            let e = if s_loc <= h / 2.0 { pair_leg_est(h, s_loc, wrap) } else { wire_est(h, wrap) };
            est += e * seg;
            by_tag[tag as usize] += e * seg;
            bnd += wire_plane(COND_MAX, h, ER_BOUND) * seg;
        }
        let total = fixed + est;
        writeln!(r, "  probe {} {}: external estimate {est:.2} pF (entry {:.2}, spine {:.2}, dock {:.2}; bound {bnd:.2} pF); nearest earth {hmin:.1} mm ({what}); per-tip total {total:.2} pF.", l.probe, l.name, by_tag[2], by_tag[0], by_tag[1]).unwrap();
        per_leg.push((l.probe, l.name, est, bnd, total));
    }
    writeln!(r, "  fixed part: ladder max {c_in_max:.2} + board/enclosure reserve {RESERVE_BOARD:.2} + tip reserve {RESERVE_TIP:.2} + inside the box {c_int_est:.2} = {fixed:.2} pF.").unwrap();
    for &(pr, nm, _, bnd, total) in &per_leg {
        gate(total <= C_TIP_TARGET, format!("probe {pr} {nm} per-tip loading {total:.2} pF <= {C_TIP_TARGET:.0} pF (estimate; lead part bounded by {bnd:.2} pF)"), &mut r);
    }
    let worst_bound = per_leg.iter().map(|p| c_in_max + RESERVE_BOARD + RESERVE_TIP + c_int_bound + p.3).fold(0.0, f64::max);
    writeln!(r, "  with every lead term at its bound (inside {c_int_bound:.2}, external bound): worst tip {worst_bound:.2} pF, reserves still estimates.").unwrap();
    let dvdt = 70e9;
    let worst_est = per_leg.iter().map(|p| p.4).fold(0.0, f64::max);
    writeln!(r, "  switch-edge current at 70 V/ns: ideal ladder {:.2} A, worst tip estimate {:.2} A; reactance at 60 kHz {:.0} kOhm.", dvdt * c_in_nom * 1e-12, dvdt * worst_est * 1e-12, 1.0 / (2.0 * PI * 60e3 * worst_est * 1e-12) / 1e3).unwrap();
    writeln!(r, "  tap stray that alone limits CMRR to 60 dB: {:.4} pF (0.1 % of the {c_in_nom:.1} pF top capacitance).", 1e-3 * c_in_nom).unwrap();

    // ---- Lead-to-lead ----
    writeln!(r, "\nLead-to-lead capacitance (loads the DUT differentially; symmetric, so it converts no common mode):").unwrap();
    let mut ll = Vec::new();
    for pr in [1usize, 2] {
        let pl: Vec<&Lead> = leads.iter().filter(|l| l.probe == pr).collect();
        let lp = pl[0].path.len_tag(0) / 1000.0;
        let est = pair_c(da, S_SP, 1.0) * 1.15 * lp;
        let bnd = pair_c(COND_MAX, S_SP, ER_BOUND) * lp;
        // Fan-out / drop: spacing grows; bound with the spine spacing over the dock length.
        let ld = pl[0].path.len_tag(1).min(pl[1].path.len_tag(1)) / 1000.0;
        let bnd_d = pair_c(COND_MAX, S_SP, ER_BOUND) * ld;
        writeln!(r, "  probe {pr}: paired {:.0} mm at {S_SP} mm: estimate {est:.2} pF (air, +15 % for shells), bound {bnd:.2} pF; dock sections (spacing >= {S_SP} mm) bound {bnd_d:.2} pF.", lp * 1e3).unwrap();
        ll.push(bnd + bnd_d);
    }

    // ---- Inductance, resonance ----
    writeln!(r, "\nDifferential loop inductance (upper estimate: equal-area conductor, low-frequency internal inductance), resonance with").unwrap();
    writeln!(r, "ladder/2 + lead-to-lead bound + tip reserve all lumped at the probe end (lower estimate of f0):").unwrap();
    let integ = |len: f64, s0: f64, s1: f64| -> f64 {
        let n = 400;
        (0..n).map(|i| {
            let t = (i as f64 + 0.5) / n as f64;
            pair_l(da, s0 + t * (s1 - s0)) * len / 1000.0 / n as f64
        }).sum()
    };
    let l_in = integ(l_int(0), 2.0 * GLAND_DY, 16.0);
    let mut fdm = Vec::new();
    let mut ldm_of = Vec::new();
    for pr in [1usize, 2] {
        let pl: Vec<&Lead> = leads.iter().filter(|l| l.probe == pr).collect();
        let l_entry = integ(pl[0].path.len_tag(2), 2.0 * GLAND_DY, 2.0 * GLAND_DY);
        let l_pair = pair_l(da, S_SP) * pl[0].path.len_tag(0) / 1000.0;
        // Dock: spacing grows to the tip spacing; use the larger of each path's
        // dock length at the tip spacing (upper estimate), plus the bare metal.
        let tip_s = dist(pl[0].contact, pl[1].contact).max(S_SP);
        let ld = pl[0].path.len_tag(1).max(pl[1].path.len_tag(1)) + (pl[0].metal + pl[1].metal) / 2.0;
        let l_dock = pair_l(da, tip_s) * ld / 1000.0;
        let l_dm = l_in + l_entry + l_pair + l_dock;
        let c_dm = c_in_max / 2.0 + ll[pr - 1] + RESERVE_TIP;
        let f = f_res(l_dm, c_dm);
        writeln!(r, "  probe {pr}: internal {l_in:.3} + entry {l_entry:.3} + paired {l_pair:.3} + dock (spacing {tip_s:.1} mm) {l_dock:.3} = {l_dm:.3} uH; C {c_dm:.2} pF; f0 = {f:.1} MHz.").unwrap();
        fdm.push(f);
        ldm_of.push(l_dm);
        gate(f >= 10.0 * BW, format!("probe {pr} differential lead resonance {f:.1} MHz >= 10 x the {BW:.0} MHz bandwidth"), &mut r);
        let rise = 1.0 / (1.0 - (BW / f).powi(2)) - 1.0;
        writeln!(r, "    undamped differential LC rise at {BW:.0} MHz: {:.2} %.", 100.0 * rise).unwrap();
    }
    for pr in [1usize, 2] {
        let pl: Vec<&Lead> = leads.iter().filter(|l| l.probe == pr).collect();
        let len = (pl[0].path.len() + l_int(0)) / 1000.0;
        // Pair over an earth return at the spine height above the bench (z = -Z_BENCH plane).
        let h = Z_SP + Z_BENCH;
        let r_eq = (OD_NOM / 2.0 * S_SP).sqrt();
        let l_cm = plane_l(2.0 * r_eq, h) * len;
        let c_cm = 2.0 * per_leg.iter().filter(|p| p.0 == pr).map(|p| p.4).fold(0.0, f64::max);
        let f = f_res(l_cm, c_cm);
        let fq = C0 / ER_MAX.sqrt() / (4.0 * len) / 1e6;
        writeln!(r, "  probe {pr} common mode: pair over an earth return {h:.0} mm away, {l_cm:.3} uH with both tips' {c_cm:.1} pF: f0 = {f:.1} MHz; quarter-wave (er {ER_MAX}) {fq:.0} MHz.").unwrap();
        gate(f >= 10.0 * BW, format!("probe {pr} common-mode lead resonance {f:.1} MHz >= 10 x the {BW:.0} MHz bandwidth"), &mut r);
    }

    // ---- CM to DM conversion ----
    writeln!(r, "\nCommon-mode to differential conversion through the leads at {BW:.0} MHz. Load mismatch dC (ladder +/-5 % twice, 0.5 pF tip").unwrap();
    writeln!(r, "asymmetry, and the two legs' computed external-capacitance difference) through the leakage inductance L_dm/2, plus the").unwrap();
    writeln!(r, "conductor-length difference (partial self-inductance x the tip's CM current):").unwrap();
    for pr in [1usize, 2] {
        let pl: Vec<&Lead> = leads.iter().filter(|l| l.probe == pr).collect();
        let cl: Vec<f64> = per_leg.iter().filter(|p| p.0 == pr).map(|p| p.2).collect();
        let d_env = (cl[0] - cl[1]).abs();
        let dc = 2.0 * C_SECTION_TOL * c_in_nom + 0.5 + d_env;
        let w = 2.0 * PI * BW * 1e6;
        let e_load = w * w * ldm_of[pr - 1] / 2.0 * 1e-6 * dc * 1e-12;
        let len_tot = |l: &Lead| l.path.len() + l.metal;
        let dl = (len_tot(pl[0]) - len_tot(pl[1])).abs() + 2.0; // + the +/-1 mm cutting tolerance
        let total_len = (len_tot(pl[0]) + l_int(0)) / 1000.0;
        let l_self = MU0 / (2.0 * PI) * ((2.0 * total_len / (da / 2000.0)).ln() - 1.0); // H/m
        let c_tip = per_leg.iter().filter(|p| p.0 == pr).map(|p| p.4).fold(0.0, f64::max);
        let e_len = w * w * l_self * dl / 1000.0 * c_tip * 1e-12;
        let e = e_load + e_len;
        writeln!(r, "  probe {pr}: legs {:.1} / {:.1} mm conductor; length residual {:.1} mm + 2 mm cutting = {dl:.1} mm ({:.1} nH) -> {e_len:.1e};", len_tot(pl[0]), len_tot(pl[1]), dl - 2.0, l_self * dl * 1e6).unwrap();
        writeln!(r, "    leg external-C difference {d_env:.2} pF, dC = {dc:.2} pF -> {e_load:.1e}; total {e:.1e} ({:.0} dB).", -20.0 * e.log10()).unwrap();
        gate(e <= 1e-3, format!("probe {pr} lead CM-to-DM conversion at {BW:.0} MHz {:.0} dB >= 60 dB", -20.0 * e.log10()), &mut r);
    }

    // ---- Magnetic pickup ----
    writeln!(r, "\nMagnetic pickup from stage-53 currents ({I_COIL:.0} A peak at {:.0} kHz). Open loop area per probe, each part in the field of one", F_SW / 1e3).unwrap();
    writeln!(r, "{I_COIL:.0} A conductor at its nearest approach (dock areas at the {R_REF:.0} mm reference distance of the twisted-pair estimate, 0.13 V):").unwrap();
    let b_at = |rmm: f64| MU0 * I_COIL / (2.0 * PI * rmm * 1e-3);
    let w_sw = 2.0 * PI * F_SW;
    let mut pk = Vec::new();
    for pr in [1usize, 2] {
        let pl: Vec<&Lead> = leads.iter().filter(|l| l.probe == pr).collect();
        // Paired region: integrate along the path, spacing S_SP, distance to the
        // board top (over the board) or to the board edge in 3-D (off it).
        let (mut flux, mut area_p) = (0.0, 0.0);
        let p = &pl[0].path.pts;
        for i in 1..p.len() {
            if pl[0].path.tag[i] != 0 {
                continue;
            }
            let ds = dist(p[i - 1], p[i]);
            let m = mul(add(p[i - 1], p[i]), 0.5);
            let dx = (0.0 - m[0]).max(0.0).max(m[0] - S53_W);
            let dy = (0.0 - m[1]).max(0.0).max(m[1] - S53_H);
            let rr = (dx * dx + dy * dy + m[2] * m[2]).sqrt();
            flux += b_at(rr) * ds * S_SP * 1e-6;
            area_p += ds * S_SP;
        }
        // Dock region: area between the two dock paths and the tip-to-tip line,
        // by the shoelace formula on the loop projected onto its best-fit plane
        // (sum of the three projected areas, an upper value).
        let mut lp: Vec<P> = Vec::new();
        let start0 = pl[0].path.tag.iter().position(|&t| t == 1).unwrap();
        let start1 = pl[1].path.tag.iter().position(|&t| t == 1).unwrap();
        lp.extend(pl[0].path.pts[start0 - 1..].iter().copied());
        lp.push(pl[0].contact);
        lp.push(pl[1].contact);
        lp.extend(pl[1].path.pts[start1 - 1..].iter().rev().copied());
        let mut a = [0.0; 3];
        for i in 0..lp.len() {
            let (u, v) = (lp[i], lp[(i + 1) % lp.len()]);
            a[0] += u[1] * v[2] - u[2] * v[1];
            a[1] += u[2] * v[0] - u[0] * v[2];
            a[2] += u[0] * v[1] - u[1] * v[0];
        }
        let area_d = 0.5 * (a[0].abs() + a[1].abs() + a[2].abs());
        let flux_d = b_at(R_REF) * area_d * 1e-6;
        let emf = w_sw * (flux + flux_d);
        writeln!(r, "  probe {pr}: paired {area_p:.0} mm2 -> {:.3} V; dock loop {area_d:.0} mm2 at {:.2} mT -> {:.3} V; total {emf:.3} V peak ({:.4} % of 1 kV).", w_sw * flux, b_at(R_REF) * 1e3, w_sw * flux_d, emf / 10.0).unwrap();
        pk.push(emf);
        gate(emf <= PICKUP_MAX, format!("probe {pr} magnetic pickup {emf:.3} V <= {PICKUP_MAX} V (0.02 % of 1 kV)"), &mut r);
    }
    {
        // Probe 2's drop rectangle lies in the plane x = J5.x - ring - bend, parallel to
        // the vertical coil Litz at each stud: exact 2-D flux of the two Litz currents.
        let a = J5.0 - (RING_L - RING_W / 2.0) - R_BEND; // x of the vertical drop
        let dperp = J5.0 - a;
        let z = Z_SP - R_BEND - ring_z(2, 0);
        let th = |y: f64, yw: f64| ((y - yw) / dperp).atan();
        let ph = MU0 * I_COIL * z * 1e-3 / (2.0 * PI)
            * ((th(J2.1, J5.1 - LITZ_OFF) - th(J5.1, J5.1 - LITZ_OFF)) + (th(J2.1, J2.1 + LITZ_OFF) - th(J5.1, J2.1 + LITZ_OFF))).abs();
        writeln!(r, "  probe 2, coil Litz rising {LITZ_OFF:.0} mm outboard of each stud: exact flux through the {z:.1} mm vertical drop at {dperp:.1} mm from the studs -> {:.3} V.", w_sw * ph).unwrap();
    }

    // ---- Setback ----
    writeln!(r, "\nSetback from exposed HV conductors to metal (>= {SETBACK:.0} mm). Printed parts and nylon hardware are not metal; resin gets no").unwrap();
    writeln!(r, "insulation credit, so this is air distance. Stage-53's own stud-to-stud and pad spacings are its design (stage53-probe-points.txt).").unwrap();
    let stack_top = REDCUBE_H + (T_LUG.1 + 2.0 * T_RING.1 + T_WASHER.1) + SCREW_HEAD_K;
    let exposed: Vec<(&str, P, P)> = vec![
        ("J5 stack", [J5.0 - WASHER_D / 2.0, J5.1 - WASHER_D / 2.0, 0.0], [J5.0 + WASHER_D / 2.0, J5.1 + WASHER_D / 2.0, stack_top]),
        ("J2 stack", [J2.0 - WASHER_D / 2.0, J2.1 - WASHER_D / 2.0, 0.0], [J2.0 + WASHER_D / 2.0, J2.1 + WASHER_D / 2.0, stack_top]),
        ("C22 TIP- joint", [C22_HOLE.0 - 2.5, C22_HOLE.1 - 2.5, -2.5], [C22_HOLE.0 + 2.5, C22_HOLE.1 + 2.5, 1.5]),
    ];
    let mut worst_sb = f64::INFINITY;
    for (n, lo, hi) in &exposed {
        let (mut d, mut what) = (f64::INFINITY, String::new());
        for (m, a, b) in &eboxes {
            let g = box_gap(*lo, *hi, *a, *b);
            if g < d {
                d = g;
                what = m.clone();
            }
        }
        // Stage-53 earthed copper: plan distance from the envelope's centre minus its half-width.
        let c = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0);
        let dc = earth_plan(&earth, c) - (hi[0] - lo[0]) / 2.0;
        if dc < d {
            d = dc;
            what = "stage-53 PE/SELV copper (plan)".into();
        }
        writeln!(r, "  {n}: nearest metal {d:.1} mm ({what}).").unwrap();
        worst_sb = worst_sb.min(d);
    }
    gate(worst_sb >= SETBACK, format!("exposed HV on stage 53 >= {SETBACK:.0} mm from earthed metal and both probe boxes (worst {worst_sb:.1} mm)"), &mut r);
    {
        let h7 = hole("H7");
        let d = ((h7.0 - J5.0).powi(2) + (h7.1 - J5.1).powi(2)).sqrt() - WASHER_D / 2.0;
        writeln!(r, "  H7 (dock-coil post) is {d:.1} mm from the J5 stack: its standoff and screw must be nylon (stage 53 marks it NYLON ONLY).").unwrap();
        gate(S53_HOLES.iter().filter(|h| ["H6", "H7", "H8", "H10"].contains(&h.0)).all(|h| !h.3), "all four dock holes (H6, H7, H8, H10) are stage-53 nylon-only holes; dock hardware is nylon".into(), &mut r);
    }
    // Inside the probe box (Hammond reference).
    let wz = wire_z();
    let mut worst = f64::INFINITY;
    for (j, &(x, y)) in W_HV.iter().enumerate() {
        let up = BOX_H - (BOARD_TOP + FILLET_UP);
        let down = BOARD_UNDER - TAIL_DOWN;
        let side = (y - PAD_R + SIDE_GAP).min(70.0 - y - PAD_R + SIDE_GAP);
        writeln!(r, "  W_HV{} joint (inside the box): lid {up:.2}, floor {down:.2}, side wall {side:.2} mm; the tip-end insert is printed ({:.1} mm away).", j + 1, x - PAD_R - TIP_PLATE_X).unwrap();
        worst = worst.min(up).min(down).min(side);
    }
    gate(worst >= SETBACK, format!("every exposed W_HV joint >= {SETBACK:.0} mm from metal (worst {worst:.2} mm)"), &mut r);
    gate(BOX_H - wz >= SETBACK, format!("internal lead conductor {:.2} mm >= {SETBACK:.0} mm from the lid", BOX_H - wz), &mut r);
    let mut screw = f64::INFINITY;
    for j in 0..2 {
        let g = plate_uv(gland(j).1, wz);
        for &(u, v) in &PLATE_SCREWS {
            screw = screw.min(((u - g.0).powi(2) + (v - g.1).powi(2)).sqrt() - PLATE_SCREW_D / 2.0 - GLAND_HOLE / 2.0);
        }
    }
    gate(screw >= SETBACK, format!("insert screw to gland hole {screw:.2} mm >= {SETBACK:.0} mm (the lead in the hole is insulated by the wire)"), &mut r);
    let loop_h = BRIDGE_T - GROOVE + od_hi;
    gate(loop_h <= 5.5, format!("lead height above the board at W_HV {loop_h:.2} mm <= 5.5 mm"), &mut r);
    gate(SEAT_T + NUT_T + 0.5 <= GLAND_THREAD, format!("gland thread {GLAND_THREAD} mm spans the {SEAT_T} mm insert seat and the {NUT_T} mm locknut with >= 0.5 mm spare"), &mut r);
    let nut_ledge = GLAND_DY - GLAND_NUT_AC / 2.0 - LEDGE_W / 2.0;
    gate(nut_ledge >= 1.0, format!("insert ledge clears the gland locknuts by {nut_ledge:.2} mm"), &mut r);
    let ledge_top = BOARD_TOP;
    let nut_bottom = wire_z() - GLAND_NUT_AC / 2.0;
    writeln!(r, "  insert ledge top {ledge_top:.2} mm above the floor carries the bridge's insert end; locknut bottoms at {nut_bottom:.2} mm.").unwrap();
    let boss_w = ROD_W + 2.0 * BOSS_WALL;
    let dome_gap = 2.0 * GLAND_DY - GLAND_OUT_D;
    gate(boss_w + 1.0 <= dome_gap, format!("spine socket boss ({boss_w:.1} mm wide) fits between the gland domes ({dome_gap:.1} mm gap) with >= 0.5 mm each side"), &mut r);
    let rod_clear = S_SP / 2.0 - od_hi / 2.0 - ((ROD_W / 2.0).powi(2) + (ROD_H / 2.0).powi(2)).sqrt();
    gate(rod_clear >= 0.5, format!("spine rod clears the leads by {rod_clear:.2} mm at the tightest twist radius"), &mut r);
    let gap_nuts = 2.0 * GLAND_DY - GLAND_NUT_AC;
    gate(gap_nuts >= 3.0, format!("gland locknuts clear each other by {gap_nuts:.1} mm"), &mut r);
    let nut_lid = BOX_H - (wz + GLAND_NUT_AC / 2.0);
    let nut_floor = wz - GLAND_NUT_AC / 2.0;
    gate(nut_lid >= 2.0 && nut_floor >= 2.0, format!("gland locknut inside the box clears the lid by {nut_lid:.1} mm and the floor by {nut_floor:.1} mm"), &mut r);
    gate(l_int(0) == l_int(1), format!("internal routes are mirror images of equal length {:.2} mm", l_int(0)), &mut r);

    // ---- Clearances to stage-53 bodies ----
    writeln!(r, "\nClearance of printed parts and leads to stage-53 component bodies (STEP boxes; J2/J5 from the Würth table) and to the").unwrap();
    writeln!(r, "coil-Litz keep-outs ({LITZ_OFF:.0} mm outboard of each stud along the J2-J5 line, half-width {LITZ_KO}):").unwrap();
    let litz: Vec<(String, P, P)> = vec![
        ("J5 coil Litz".into(), [J5.0 - LITZ_KO, J5.1 - LITZ_OFF - LITZ_KO, REDCUBE_H], [J5.0 + LITZ_KO, J5.1 - LITZ_OFF + LITZ_KO, 300.0]),
        ("J2 coil Litz".into(), [J2.0 - LITZ_KO, J2.1 + LITZ_OFF - LITZ_KO, REDCUBE_H], [J2.0 + LITZ_KO, J2.1 + LITZ_OFF + LITZ_KO, 300.0]),
    ];
    let mut parts = vec![dock_coil(), dock_bank()];
    parts.extend(spines());
    let mut obst: Vec<(String, P, P)> = bodies.iter().map(|b| (b.refd.clone(), b.lo, b.hi)).collect();
    obst.extend(litz.iter().cloned());
    for part in &parts {
        let (mut d, mut what) = (f64::INFINITY, String::new());
        for (bn, lo, hi) in &part.boxes {
            for (on, a, b) in &obst {
                // Feet and posts stand on the board: ignore z below 0.2 for them.
                let lo2 = [lo[0], lo[1], lo[2].max(0.2)];
                let g = box_gap(lo2, *hi, *a, *b);
                if g < d {
                    d = g;
                    what = format!("{bn} to {on}");
                }
            }
        }
        writeln!(r, "  {}: {d:.2} mm ({what}).", part.name).unwrap();
        gate(d >= BODY_CLR, format!("{} clears stage-53 bodies and Litz keep-outs by {d:.2} mm >= {BODY_CLR} mm", part.name), &mut r);
    }
    for l in &leads {
        let (mut d, mut what) = (f64::INFINITY, String::new());
        let p = &l.path.pts;
        // Skip the last 2 mm: the lead lands on its own stud or hole.
        let n_end = p.len().saturating_sub(3);
        for q in &p[..n_end] {
            for (on, a, b) in &obst {
                let g = box_dist(*q, *a, *b) - od_hi / 2.0;
                if g < d {
                    d = g;
                    what = on.clone();
                }
            }
        }
        writeln!(r, "  probe {} {} lead surface: {d:.2} mm ({what}).", l.probe, l.name).unwrap();
        gate(d >= LEAD_CLR, format!("probe {} {} lead surface clears stage-53 bodies by {d:.2} mm >= {LEAD_CLR} mm", l.probe, l.name), &mut r);
    }
    // Parts against each other's leads: each lead must not pass through another probe's parts.
    {
        let mut d = f64::INFINITY;
        let mut what = String::new();
        for l in &leads {
            for part in &parts {
                let own = (l.probe == 1 && (part.name == "dock-bank" || part.name == "spine-bank")) || (l.probe == 2 && (part.name == "dock-coil" || part.name == "spine-coil"));
                if own {
                    continue;
                }
                for (bn, lo, hi) in &part.boxes {
                    for q in &l.path.pts {
                        let g = box_dist(*q, *lo, *hi) - od_hi / 2.0;
                        if g < d {
                            d = g;
                            what = format!("probe {} {} to {} {bn}", l.probe, l.name, part.name);
                        }
                    }
                }
            }
        }
        writeln!(r, "  closest approach of a lead to the other probe's parts: {d:.2} mm ({what}).").unwrap();
        gate(d >= LEAD_CLR, format!("the two probes' docks and spines do not collide with each other's leads ({d:.2} mm)"), &mut r);
        let (b1, b2) = (box_slabs(1), box_slabs(2));
        let mut g = f64::INFINITY;
        for (a, b) in &b1 {
            for (c, e) in &b2 {
                g = g.min(box_gap(*a, *b, *c, *e));
            }
        }
        gate(g >= 20.0, format!("the two probe boxes are {g:.0} mm apart (>= 20 mm)"), &mut r);
        // Each box stays off the stage-53 board outline and out of the heatsink keep-out.
        let mut gb = f64::INFINITY;
        for (a, b) in b1.iter().chain(b2.iter()) {
            gb = gb.min(box_gap(*a, *b, [0.0, 0.0, -Z_BENCH], [S53_W, S53_H, 60.0]));
            gb = gb.min(box_gap(*a, *b, [0.0, -60.0, -40.0], [110.0, 8.0, 40.0]));
        }
        gate(gb >= 5.0, format!("both probe boxes stand clear of the stage-53 board volume and the heatsink keep-out ({gb:.1} mm)"), &mut r);
        // Spine envelopes against each other.
        let s = spines();
        let mut gs = f64::INFINITY;
        for (_, a, b) in &s[0].boxes {
            for (_, c, e) in &s[1].boxes {
                gs = gs.min(box_gap(*a, *b, *c, *e));
            }
        }
        gate(gs >= 5.0, format!("the two spines are {gs:.0} mm apart"), &mut r);
    }

    // ---- Asymmetric printed material near the leads ----
    writeln!(r, "\nAsymmetric printed material. First-order dielectric perturbation of a lead's capacitance by a resin volume V at distance d:").unwrap();
    writeln!(r, "dC ~ (er - 1) eps0 (C'/(2 pi eps0))^2 V / d^2, with C' the lead's per-length capacitance (12 pF/m upper). Outside the divider it only").unwrap();
    writeln!(r, "loads the source; it is fixed, and enters the CM-to-DM budget above only through dC.").unwrap();
    {
        let cp = 12e-12;
        let k = (ER_BOUND - 1.0) * EPS0 * (cp / (2.0 * PI * EPS0)).powi(2);
        let mut worst = (0.0, String::new());
        for part in [dock_coil(), dock_bank()] {
            for (bn, lo, hi) in &part.boxes {
                let asym = bn.contains("post") || bn.contains("H6 arm") || bn.contains("H7 arm") || bn.contains("cross") || bn.contains("TIP- clamp");
                if !asym {
                    continue;
                }
                let v = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2]) * 1e-9;
                let mut d = f64::INFINITY;
                for l in &leads {
                    for q in &l.path.pts {
                        d = d.min(box_dist(*q, *lo, *hi));
                    }
                }
                let d = (d + R_RESIN).max(R_RESIN) * 1e-3;
                let dc = k * v / (d * d) * 1e12;
                if dc > worst.0 {
                    worst = (dc, format!("{} {bn}", part.name));
                }
            }
        }
        writeln!(r, "  largest single asymmetric feature: {} -> {:.3} pF (estimate).", worst.1, worst.0).unwrap();
        gate(worst.0 <= 0.1, format!("asymmetric printed features shift a leg by <= 0.1 pF ({:.3} pF), inside the 0.5 pF tip-asymmetry reserve", worst.0), &mut r);
    }

    // ---- Parts summary ----
    let bo = bridge_outline();
    let (bx0, bx1) = bo.iter().fold((f64::INFINITY, f64::NEG_INFINITY), |a, p| (a.0.min(p.0), a.1.max(p.0)));
    let (by0, by1) = bo.iter().fold((f64::INFINITY, f64::NEG_INFINITY), |a, p| (a.0.min(p.1), a.1.max(p.1)));
    writeln!(r, "\nPrinted parts: wall insert {PLATE_W} x {PLATE_H} x {WALL_T} mm (gland seats {SEAT_T} mm); lead bridge {:.1} x {:.1} x {BRIDGE_T} mm overall", bx1 - bx0, by1 - by0).unwrap();
    writeln!(r, "(x {bx0:.2}..{bx1:.2}, y {by0:.1}..{by1:.1}); docks and spines as in geometry.json (mech3d/ builds them).").unwrap();

    // ---- geometry.json ----
    let mut js = String::new();
    writeln!(js, "{{").unwrap();
    writeln!(js, "  \"generator\": \"tools/leads.rs (do not edit; make leads regenerates it)\",").unwrap();
    writeln!(js, "  \"frames\": {{\"s53\": \"stage-53 board: X = KiCad x, Y = -KiCad y, Z = height above the board top (board.step z - 1.6); mm\", \"box\": \"probe board: X = x (tip edge 0, output 150), Y = -y (KiCad), Z = height above the enclosure inner floor; mm\"}},").unwrap();
    writeln!(js, "  \"wire\": {{\"od_min\": {:.3}, \"od_max\": {:.3}, \"od_nom\": {:.3}, \"cond_max\": {COND_MAX}, \"bend_r_min\": {R_BEND}}},", od_lo, od_hi, OD_NOM).unwrap();
    writeln!(js, "  \"clearances\": {{\"setback_hv_to_metal\": {SETBACK}, \"body_clearance\": {BODY_CLR}, \"lead_clearance\": {LEAD_CLR}, \"lead_groove_r\": {:.3}, \"resin_wall_min\": 3.0, \"litz_offset\": {LITZ_OFF}, \"litz_keepout_half\": {LITZ_KO}}},", od_hi / 2.0 + 0.15).unwrap();
    writeln!(js, "  \"bench\": {{\"z_board_top_above_bench\": {Z_BENCH}, \"spine_z\": {Z_SP}, \"spine_pitch\": {S_SP}, \"spine_half_width\": {SP_HALF_W}, \"spine_below\": {SP_BELOW}, \"spine_above\": {SP_ABOVE}, \"half_twist_length\": {L_TWIST}, \"box_riser\": {:.3}, \"standoff_h\": {H_SO}}},", Z_SP + Z_BENCH - gland_z_box()).unwrap();
    writeln!(js, "  \"stage53\": {{\"board\": [{S53_W}, {S53_H}], \"board_t\": {S53_BOARD_T}, \"J5\": {}, \"J2\": {}, \"C22_hole\": {}, \"C22_hole_d\": {C22_HOLE_D},", J::p([J5.0, J5.1, 0.0]), J::p([J2.0, J2.1, 0.0]), J::p([C22_HOLE.0, C22_HOLE.1, 0.0])).unwrap();
    writeln!(js, "    \"redcube\": {{\"d\": {REDCUBE_D}, \"h\": {REDCUBE_H}, \"thread\": {REDCUBE_THREAD}}}, \"washer_d\": {WASHER_D}, \"stack_top\": {:.3}, \"ring\": {{\"l\": {RING_L}, \"w\": {RING_W}, \"barrel_dz\": {BARREL_DZ}, \"sleeve_d\": {SLEEVE_D:.2}, \"sleeve_on_wire\": {SLEEVE_ON_WIRE}, \"z_probe1\": {:.3}, \"z_probe2\": {:.3}}},", stack_top, ring_z(1, 0), ring_z(2, 0)).unwrap();
    let hs: Vec<String> = S53_HOLES.iter().map(|h| format!("{{\"name\": \"{}\", \"at\": {}, \"metal\": {}}}", h.0, J::p([h.1, h.2, 0.0]), h.3)).collect();
    writeln!(js, "    \"holes\": [{}],", hs.join(", ")).unwrap();
    let lz: Vec<String> = litz.iter().map(|(n, a, b)| format!("{{\"name\": \"{n}\", \"box\": {}}}", J::bx(*a, *b))).collect();
    writeln!(js, "    \"litz_keepouts\": [{}],", lz.join(", ")).unwrap();
    let bb: Vec<String> = bodies.iter().filter(|b| b.hi[2] > 3.0 || ["J5", "J2", "C22"].contains(&b.refd.as_str())).map(|b| format!("{{\"ref\": \"{}\", \"box\": {}}}", b.refd, J::bx(b.lo, b.hi))).collect();
    writeln!(js, "    \"bodies_over_3mm\": [{}]}},", bb.join(", ")).unwrap();
    let ls: Vec<String> = leads.iter().map(|l| {
        let tags: Vec<String> = l.path.tag.iter().map(|t| t.to_string()).collect();
        format!("{{\"probe\": {}, \"name\": \"{}\", \"length\": {:.3}, \"metal\": {:.3}, \"contact\": {}, \"tags\": [{}], \"pts\": {}}}", l.probe, l.name, l.path.len(), l.metal, J::p(l.contact), tags.join(","), J::pts(&l.path.pts))
    }).collect();
    writeln!(js, "  \"leads\": [\n    {}\n  ],", ls.join(",\n    ")).unwrap();
    let pjs = |p: &Part| -> String {
        let b: Vec<String> = p.boxes.iter().map(|(n, lo, hi)| format!("{{\"name\": \"{n}\", \"box\": {}}}", J::bx(*lo, *hi))).collect();
        format!("{{\"name\": \"{}\", \"resin\": \"{}\", \"boxes\": [{}]}}", p.name, p.resin, b.join(", "))
    };
    let all_parts: Vec<String> = parts.iter().map(pjs).collect();
    writeln!(js, "  \"parts_s53\": [\n    {}\n  ],", all_parts.join(",\n    ")).unwrap();
    // Probe box poses: origin = insert outer face centre at the gland axis height; x_axis = along the box away from stage 53.
    let pose = |pr: usize| -> String {
        let (o, xa, ya): (P, P, P) = if pr == 2 { ([-G2, P2_Y, Z_SP], [-1.0, 0.0, 0.0], [0.0, -1.0, 0.0]) } else { ([P1_X, -G1, Z_SP], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0]) };
        // ya: direction of the box's +y_kicad (TIP- side) in the s53 KiCad frame.
        let sl: Vec<String> = box_slabs(pr).iter().map(|(a, b)| J::bx(*a, *b)).collect();
        format!("{{\"probe\": {pr}, \"insert_outer_centre\": {}, \"box_x_dir\": {}, \"box_y_dir\": {}, \"extrusion_slabs\": [{}]}}", J::p(o), J::pb(xa), J::pb(ya), sl.join(", "))
    };
    writeln!(js, "  \"probe_boxes\": [{}, {}],", pose(1), pose(2)).unwrap();
    // Box-local parts: insert, lead bridge, internal lead paths.
    let br: Vec<String> = bo.iter().map(|&(x, y)| format!("[{x:.4},{:.4}]", -y)).collect();
    let ties: Vec<String> = (0..2).flat_map(|j| {
        let p = lead_path_int(j);
        TIES_X.iter().map(move |&tx| format!("[{tx:.3},{:.3}]", -path_y(&p, tx))).collect::<Vec<_>>()
    }).collect();
    let ints: Vec<String> = (0..2).map(|j| {
        let p = lead_path_int(j);
        format!("[{}]", p.iter().map(|&(x, y)| format!("[{x:.3},{:.3},{:.3}]", -y, wire_z())).collect::<Vec<_>>().join(","))
    }).collect();
    let glands: Vec<String> = (0..2).map(|j| format!("[{:.3},{:.3},{:.3}]", gland(j).0, -gland(j).1, wire_z())).collect();
    writeln!(js, "  \"box\": {{\"hammond\": {{\"box_h_min\": {BOX_H}, \"box_h_nom\": {BOX_H_NOM}, \"box_w\": {BOX_W}, \"out_w\": {BOX_OUT_W}, \"out_h\": {BOX_OUT_H}, \"floor_t\": {BOX_FLOOR_T:.3}, \"l_int\": {BOX_L_INT}, \"board_under\": {BOARD_UNDER}, \"board_t\": {BOARD_T}}},").unwrap();
    let screws: Vec<String> = PLATE_SCREWS.iter().map(|(u, v)| format!("[{u},{v}]")).collect();
    writeln!(js, "    \"insert\": {{\"inner_face_x\": {TIP_PLATE_X:.4}, \"t\": {WALL_T}, \"seat_t\": {SEAT_T}, \"seat_d\": {SEAT_D}, \"w\": {PLATE_W}, \"h\": {PLATE_H}, \"centre_y\": {:.3}, \"centre_z\": {PLATE_CZ:.3}, \"screws_uv\": [{}], \"screw_d\": {PLATE_SCREW_D}, \"gland_hole\": {GLAND_HOLE}, \"glands\": [{}], \"gland_out_d\": {GLAND_OUT_D}, \"gland_out_l\": {GLAND_OUT_L}, \"nut_ac\": {GLAND_NUT_AC}, \"nut_t\": {NUT_T}, \"ledge_w\": {LEDGE_W}, \"ledge_t\": {LEDGE_T}, \"ledge_x1\": {:.4}, \"ledge_top_z\": {BOARD_TOP}, \"rod_w\": {ROD_W}, \"rod_h\": {ROD_H}, \"boss_wall\": {BOSS_WALL}, \"boss_l\": {BOSS_L}}},", -PLATE_CY, screws.join(","), glands.join(","), bridge_x0() + LEDGE_OVERLAP).unwrap();
    let h34: Vec<String> = H34.iter().map(|&(x, y)| format!("[{x},{:.3}]", -y)).collect();
    let whv: Vec<String> = W_HV.iter().map(|&(x, y)| format!("[{x},{:.3}]", -y)).collect();
    writeln!(js, "    \"bridge\": {{\"outline\": [{}], \"t\": {BRIDGE_T}, \"groove\": {GROOVE}, \"board_top_z\": {BOARD_TOP}, \"h34\": [{}], \"tie_points\": [{}], \"tie_slot\": [{}, {}], \"tie_gap\": {TIE_GAP}, \"arm_x2\": {ARM_X2}}},", br.join(","), h34.join(","), ties.join(","), TIE_SLOT.0, TIE_SLOT.1).unwrap();
    writeln!(js, "    \"w_hv\": [{}], \"internal_leads\": [{}], \"wire_z\": {:.4}}}", whv.join(","), ints.join(","), wire_z()).unwrap();
    let st = |pr: usize| saddle_stations(pr).iter().map(|v| format!("{v:.3}")).collect::<Vec<_>>().join(", ");
    writeln!(js, "  ,\"spine\": {{\"rod_w\": {ROD_W}, \"rod_h\": {ROD_H}, \"saddle_l\": {SADDLE_L}, \"saddle_pitch\": {SADDLE_PITCH}, \"r_resin\": {R_RESIN}, \"seat_l\": {SEAT_L}, \"probe1_axis\": [{}, {}], \"probe2_axis\": [{}, {}], \"probe1_saddles\": [{}], \"probe2_saddles\": [{}]}}", J::p([P1_X, -G1, Z_SP]), J::p([P1_X, P1_Y_SPINE_END, Z_SP]), J::p([-G2, P2_Y, Z_SP]), J::p([P2_X_DOCK, P2_Y, Z_SP]), st(1), st(2)).unwrap();
    // Trimmer access: lid inner face at the minimum internal height.
    let tr: Vec<String> = TRIMMERS.iter().map(|&(n, x, y, h)| {
        let top = BOARD_TOP + h;
        let sleeve = BOX_H - top - GUIDE_GAP; // below the lid's inner face
        format!("{{\"ref\": \"{n}\", \"xy\": [{x},{:.3}], \"top_z\": {top:.3}, \"sleeve_below_lid\": {sleeve:.3}, \"reach_from_flange_top\": {:.3}}}", -y, GUIDE_FLANGE.1 + BOX_FLOOR_T + (BOX_H - top))
    }).collect();
    writeln!(js, "  ,\"trim\": {{\"lid_inner_z_min\": {BOX_H}, \"lid_t\": {BOX_FLOOR_T:.3}, \"trimmers\": [{}], \"guide\": {{\"bore\": {GUIDE_BORE}, \"od\": {GUIDE_OD}, \"flange_d\": {}, \"flange_t\": {}, \"gap\": {GUIDE_GAP}}}, \"blade\": {{\"w\": {}, \"t\": {}, \"shank_d\": {}, \"l\": {}, \"part\": \"Vessel CA-18 (code 125672), zirconia\"}}, \"nose_d\": {NOSE_D}, \"blade_out\": {BLADE_OUT}}}", tr.join(", "), GUIDE_FLANGE.0, GUIDE_FLANGE.1, BLADE.0, BLADE.1, BLADE.2, BLADE.3).unwrap();
    writeln!(js, "  ,\"jig\": {{\"region\": {}, \"t\": {JIG_T}, \"holes\": [\"H6\", \"H7\", \"H8\", \"H10\"]}}", J::bx([JIG_X.0, JIG_Y.0, -JIG_T], [JIG_X.1, JIG_Y.1, 0.0])).unwrap();
    writeln!(js, "}}").unwrap();

    fs::create_dir_all("validation/leads").unwrap();
    fs::write("validation/leads/leads.txt", &r).unwrap();
    fs::write("validation/leads/geometry.json", &js).unwrap();
    fs::write("docs/hv-leads-section.svg", svg()).unwrap();
    print!("{r}");
    if !failed.is_empty() {
        eprintln!("leads: {} gate(s) failed", failed.len());
        std::process::exit(1);
    }
}

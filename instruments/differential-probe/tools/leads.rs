//! HV input leads, tip-end plate and lead bridge for the Rev C probe.
//!
//! One source of geometry for:
//! - the capacitance / inductance / resonance budget and the 20 mm setback
//!   audit (validation/leads/leads.txt),
//! - the dimensioned plan and section view (docs/hv-leads-section.svg),
//! - the two copper-free JLC FR4 parts (mech/tip-plate, mech/lead-bridge).
//!
//! Run from the probe directory (`make check` does this):
//!     rustc --edition 2021 tools/leads.rs -o /tmp/temper-probe-leads && /tmp/temper-probe-leads
//! Every `gate` is a design requirement; a failing gate exits non-zero.
//!
//! Coordinates are the probe board's: x along the board (tip edge x = 0, output
//! end x = 150), y across it (inter-leg axis y = 35), z up from the enclosure's
//! inner floor. Units are mm, pF, uH and MHz unless named otherwise.
use std::{f64::consts::PI, fmt::Write as _, fs};

const EPS0: f64 = 8.8541878128e-12; // F/m
const MU0: f64 = 1.25663706212e-6; // H/m
const C0: f64 = 299_792_458.0; // m/s

// ---- Lead wire: see docs/hv-leads.md "Lead wire" for the datasheet basis ----
/// Alpha Wire 392040 (UL AWM 3239, 150 C, 10 kV DC), customer specification:
/// 20 AWG 10/30 tinned copper, conductor 0.037 in; 0.040 in nominal silicone
/// wall; OD 0.117 +/- 0.004 in. Stranded conductor outer diameter (bundle) is
/// used for capacitance upper bounds.
const COND_BUNDLE: f64 = 0.037 * 25.4;
/// Conductor cross-section, ten 30 AWG strands (0.0509 mm2 each): its
/// equal-area diameter is used for lower estimates and inductance upper estimates.
const COND_AREA_MM2: f64 = 10.0 * 0.0509;
/// Insulation outer diameter, nominal and tolerance.
const OD_NOM: f64 = 0.117 * 25.4;
const OD_TOL: f64 = 0.004 * 25.4;
/// Relative permittivity bracket for silicone rubber insulation. The Alpha
/// specification gives none; published silicone-rubber values are about
/// 2.7-3.6, and the bracket is widened to 2.5-4.0.
const ER_MAX: f64 = 4.0;
const ER_MIN: f64 = 2.5;
const WIRE_RATED_KV_DC: f64 = 10.0;

// ---- Enclosure: Hammond 1455N2201 ----
/// Hammond 1455N2201 drawing: extrusion 103.00 x 53.00 mm outside, internal
/// height 49.70 +/- 0.56 mm (minimum 49.14), length 220.00 +/- 0.50 mm;
/// polycarbonate bezel lip 1.60 mm between each extrusion end and its end
/// plate; end plate 103.12 x 53.09 x 1.50 mm, 4 x 0.165 in holes on
/// 95.00 x 45.47 mm, countersunk 0.230 in x 82 deg, #6 thread-forming screws.
const BOX_H: f64 = 49.14;
const BOX_H_NOM: f64 = 49.70;
/// Internal width at the side-wall rib tips (revc.md section 9).
const BOX_W: f64 = 95.0;
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

// ---- Tip-end plate (FR4) and gland ----
/// Plate outline (as Hammond's aluminium end panel), thickness, corner radius.
const PLATE_W: f64 = 103.12;
const PLATE_H: f64 = 53.09;
const PLATE_T: f64 = 1.6;
/// Plate outline centre in board y and in z above the inner floor: the board
/// is centred across the box and the end plate on the extrusion.
const PLATE_CY: f64 = 35.0;
const PLATE_CZ: f64 = BOX_H_NOM / 2.0;
/// End-panel screw holes, offsets from the plate centre (u, v) and diameter.
const PLATE_SCREWS: [(f64, f64); 4] = [(-47.5, -22.735), (47.5, -22.735), (-47.5, 22.735), (47.5, 22.735)];
const PLATE_SCREW_D: f64 = 4.2;
/// Gland: panel hole, locknut across corners (keep-out), centres +/- GLAND_DY.
/// PROVISIONAL (M12 nylon gland class) until the gland part is selected.
const GLAND_HOLE: f64 = 12.2;
const GLAND_NUT_AC: f64 = 17.5;
const GLAND_DY: f64 = 12.5;
/// Gland locknut thickness on the plate's inner face.
const NUT_T: f64 = 5.0;
/// Bridge tab through the plate: width (y), protrusion beyond the plate's
/// outer face, and the slot clearance.
const TAB_W: f64 = 5.0;
const TAB_OUT: f64 = 1.0;
const SLOT_CLR: f64 = 0.4;

// ---- HV landings ----
const W_HV: [(f64, f64); 2] = [(7.0, 27.0), (7.0, 43.0)];
/// Exposed conductor envelope at a landing: 4 mm pad, solder fillet <= 1.5 mm
/// above the board top, trimmed tail <= 1.0 mm below the underside.
const PAD_R: f64 = 2.0;
const FILLET_UP: f64 = 1.5;
const TAIL_DOWN: f64 = 1.0;
/// H3/H4: unplated M3 holes on the tip-end prongs (layout.rs mounting_holes).
const H34: [(f64, f64); 2] = [(5.0, 5.0), (5.0, 65.0)];

// ---- Lead bridge (FR4 on the board top, held by the H3/H4 nylon screws) ----
const BRIDGE_T: f64 = 1.6;
/// Board-side end of the bridge's main plate, and the arms' reach onto the board.
const BRIDGE_X1: f64 = -1.0;
const ARM_X2: f64 = 10.0;
const ARM_W: f64 = 9.0;
/// Tie points along each lead: x of each slot pair (last one 11 mm before the pad).
const TIES_X: [f64; 3] = [-61.0, -32.5, -4.0];
/// Cable-tie slot (along the lead x across it) and the slot's gap to the insulation.
const TIE_SLOT: (f64, f64) = (3.0, 1.4);
const TIE_GAP: f64 = 1.0;

// ---- External lead ----
const L_EXT: f64 = 200.0;
const L_TAIL: f64 = 70.0;
/// Widest tip spacing in use: J5 to the C22 free hole on stage 53
/// (validation/leads/stage53-probe-points.txt).
const S_TIP_MAX: f64 = 58.55;

// ---- Budgets ----
/// Per-tip loading target (pF). qualification.md section 4 set a tentative
/// 10 pF; this design shows 10 pF cannot be met with a lead that reaches both
/// stage-53 bank nodes, and adopts 12 pF (docs/hv-leads.md "Capacitance budget").
const C_TIP_TARGET: f64 = 12.0;
const C_TIP_TENTATIVE: f64 = 10.0;
/// Ladder: five 33 pF +/-5 % C0G sections in series per leg (C1812C330JHGACTU).
const C_SECTION: f64 = 33.0;
const C_SECTION_TOL: f64 = 0.05;
/// Unmodelled reserves inside the per-tip budget: ladder copper and bodies to
/// the enclosure, and the tip accessory.
const RESERVE_BOARD: f64 = 1.0;
const RESERVE_TIP: f64 = 0.5;
/// Operating rule: lead axis >= H_REF from any earthed conductor.
const H_REF: f64 = 50.0;
const H_FAR: f64 = 300.0;
const SETBACK: f64 = 20.0;
const BW: f64 = 5.0;
const V_EXT: f64 = 3000.0;
/// Magnetic pickup example: 28 A (the stage-53 ceiling) at 35 kHz in a
/// conductor 20 mm from the tails' loop.
const I_COIL: f64 = 28.0;
const R_COIL: f64 = 20.0;

fn acosh(x: f64) -> f64 {
    (x + (x * x - 1.0).sqrt()).ln()
}
fn d_area() -> f64 {
    (4.0 * COND_AREA_MM2 / PI).sqrt()
}
/// pF/m: coaxial shell of permittivity er between diameters d and od.
fn coax(d: f64, od: f64, er: f64) -> f64 {
    2.0 * PI * EPS0 * er / (od / d).ln() * 1e12
}
/// pF/m: wire of diameter d, axis at h from a plane, uniform permittivity er.
fn wire_plane(d: f64, h: f64, er: f64) -> f64 {
    2.0 * PI * EPS0 * er / acosh(2.0 * h / d) * 1e12
}
/// pF/m: insulated wire, axis at h from a plane; shell and air in series (estimate).
fn wire_plane_series(d: f64, od: f64, er: f64, h: f64) -> f64 {
    2.0 * PI * EPS0 / ((od / d).ln() / er + acosh(2.0 * h / od)) * 1e12
}
/// pF/m: two wires of diameter d at centre spacing s, uniform permittivity er.
fn pair(d: f64, s: f64, er: f64) -> f64 {
    PI * EPS0 * er / acosh(s / d) * 1e12
}
/// uH/m: loop inductance of a two-wire line, with low-frequency internal inductance.
fn pair_l(d: f64, s: f64) -> f64 {
    (MU0 / PI * acosh(s / d) + 2.0 * MU0 / (8.0 * PI)) * 1e6
}
/// uH/m: wire over a return plane at h, with low-frequency internal inductance.
fn plane_l(d: f64, h: f64) -> f64 {
    (MU0 / (2.0 * PI) * acosh(2.0 * h / d) + MU0 / (8.0 * PI)) * 1e6
}
fn f_res(l_uh: f64, c_pf: f64) -> f64 {
    1.0 / (2.0 * PI * (l_uh * 1e-6 * c_pf * 1e-12).sqrt()) / 1e6
}
fn wire_z() -> f64 {
    // The wire lies on the bridge top surface.
    BOARD_TOP + BRIDGE_T + OD_NOM / 2.0
}
fn gland(j: usize) -> (f64, f64) {
    (TIP_PLATE_X, 35.0 + if j == 0 { -GLAND_DY } else { GLAND_DY })
}
/// Lead centre-line in plan, gland face to the landing hole.
fn lead_path(j: usize) -> Vec<(f64, f64)> {
    let (gx, gy) = gland(j);
    let (px, py) = W_HV[j];
    vec![(gx, gy), (TIES_X[2], py), (px, py)]
}
fn path_y(p: &[(f64, f64)], x: f64) -> f64 {
    let w = p.windows(2).find(|w| w[0].0 <= x && x <= w[1].0).unwrap();
    w[0].1 + (x - w[0].0) / (w[1].0 - w[0].0) * (w[1].1 - w[0].1)
}
fn path_len(p: &[(f64, f64)]) -> f64 {
    p.windows(2).map(|w| ((w[1].0 - w[0].0).powi(2) + (w[1].1 - w[0].1).powi(2)).sqrt()).sum()
}
/// Internal length: plan path, the bridge-to-board step and the hole depth.
fn l_int(j: usize) -> f64 {
    path_len(&lead_path(j)) + BRIDGE_T + BOARD_T + 1.0
}

// ======================================================================
// Mechanical parts as KiCad boards (copper-free FR4)
// ======================================================================
struct Pcb {
    items: String,
}
impl Pcb {
    fn new() -> Self {
        Pcb { items: String::new() }
    }
    fn line(&mut self, a: (f64, f64), b: (f64, f64)) {
        writeln!(self.items, "  (gr_line (start {:.4} {:.4}) (end {:.4} {:.4}) (stroke (width 0.1) (type solid)) (layer \"Edge.Cuts\"))", a.0, a.1, b.0, b.1).unwrap();
    }
    fn poly(&mut self, p: &[(f64, f64)]) {
        for i in 0..p.len() {
            self.line(p[i], p[(i + 1) % p.len()]);
        }
    }
    fn rect(&mut self, c: (f64, f64), w: f64, h: f64, ang: f64) {
        let (s, k) = ang.sin_cos();
        let pts: Vec<_> = [(-w / 2., -h / 2.), (w / 2., -h / 2.), (w / 2., h / 2.), (-w / 2., h / 2.)]
            .iter()
            .map(|&(x, y)| (c.0 + x * k - y * s, c.1 + x * s + y * k))
            .collect();
        self.poly(&pts);
    }
    fn circle(&mut self, c: (f64, f64), d: f64) {
        writeln!(self.items, "  (gr_circle (center {:.4} {:.4}) (end {:.4} {:.4}) (stroke (width 0.1) (type solid)) (fill no) (layer \"Edge.Cuts\"))", c.0, c.1, c.0 + d / 2.0, c.1).unwrap();
    }
    fn drill(&mut self, r: &str, c: (f64, f64), d: f64) {
        writeln!(self.items, "  (footprint \"Probe:NPTH_{d:.2}\" (layer \"F.Cu\") (at {:.4} {:.4}) (attr board_only exclude_from_pos_files exclude_from_bom) (property \"Reference\" \"{r}\" (at 0 0) (layer \"F.Fab\") (hide yes) (effects (font (size 1 1) (thickness 0.15)))) (property \"Value\" \"NPTH\" (at 0 0) (layer \"F.Fab\") (hide yes) (effects (font (size 1 1) (thickness 0.15)))) (pad \"\" np_thru_hole circle (at 0 0) (size {d:.3} {d:.3}) (drill {d:.3}) (layers \"*.Cu\" \"*.Mask\")))", c.0, c.1).unwrap();
    }
    fn text(&mut self, c: (f64, f64), size: f64, t: &str) {
        writeln!(self.items, "  (gr_text \"{t}\" (at {:.4} {:.4} 0) (layer \"F.SilkS\") (effects (font (size {size} {size}) (thickness {:.2}))))", c.0, c.1, size * 0.15).unwrap();
    }
    fn write(&self, path: &str, thickness: f64) {
        let mut s = format!("(kicad_pcb (version 20241229) (generator \"temper_probe_leads\") (generator_version \"10.0\")\n  (general (thickness {thickness}) (legacy_teardrops no))\n  (paper \"A4\")\n  (layers (0 \"F.Cu\" signal) (2 \"B.Cu\" signal) (5 \"F.SilkS\" user \"F.Silkscreen\") (7 \"B.SilkS\" user \"B.Silkscreen\") (1 \"F.Mask\" user) (3 \"B.Mask\" user) (13 \"F.Paste\" user) (15 \"B.Paste\" user) (25 \"Edge.Cuts\" user) (27 \"Margin\" user) (31 \"F.CrtYd\" user \"F.Courtyard\") (29 \"B.CrtYd\" user \"B.Courtyard\") (35 \"F.Fab\" user) (33 \"B.Fab\" user))\n  (setup (pad_to_mask_clearance 0))\n  (net 0 \"\")\n");
        s += &self.items;
        s += ")\n";
        fs::create_dir_all(std::path::Path::new(path).parent().unwrap()).unwrap();
        fs::write(path, s).unwrap();
    }
}

/// Lead bridge in board coordinates, shifted so KiCad sees positive values.
const BR_OFF: (f64, f64) = (80.0, 20.0);
fn bridge() -> Pcb {
    let o = |p: (f64, f64)| (p.0 + BR_OFF.0, p.1 + BR_OFF.1);
    let mut b = Pcb::new();
    let pts: Vec<_> = bridge_outline().into_iter().map(o).collect();
    b.poly(&pts);
    for (i, &h) in H34.iter().enumerate() {
        b.drill(&format!("H{}", i + 3), o(h), 3.4);
    }
    // Cable-tie slot pairs straddling each lead, square to the lead.
    for j in 0..2 {
        let p = lead_path(j);
        for &tx in &TIES_X {
            let seg = p.windows(2).find(|w| w[0].0 <= tx && tx <= w[1].0).unwrap();
            let t = (tx - seg[0].0) / (seg[1].0 - seg[0].0);
            let y = seg[0].1 + t * (seg[1].1 - seg[0].1);
            let ang = (seg[1].1 - seg[0].1).atan2(seg[1].0 - seg[0].0);
            let off = OD_NOM / 2.0 + TIE_GAP + TIE_SLOT.1 / 2.0;
            for sgn in [-1.0, 1.0] {
                let c = (tx - sgn * off * ang.sin(), y + sgn * off * ang.cos());
                b.rect(o(c), TIE_SLOT.0, TIE_SLOT.1, ang);
            }
        }
    }
    b.text(o((-30.0, 35.0)), 2.0, "TEMPER PROBE REV C LEAD BRIDGE");
    b.text(o((-30.0, 10.0)), 1.5, "FR4, NO COPPER");
    b.text(o((-30.0, 60.0)), 1.5, "NYLON M3 AT H3/H4 ONLY");
    b.text(o((-16.0, W_HV[0].1 - 4.5)), 1.5, "TIP +");
    b.text(o((-16.0, W_HV[1].1 + 4.5)), 1.5, "TIP -");
    b
}

/// Tip-end plate seen from outside the box: u to the right, v up. KiCad X = u,
/// Y = -v, shifted. From outside, board +y points left, so u = PLATE_CY - y.
const PL_OFF: (f64, f64) = (80.0, 60.0);
fn plate_uv(y: f64, z: f64) -> (f64, f64) {
    (PLATE_CY - y, z - PLATE_CZ)
}
fn plate() -> Pcb {
    let o = |p: (f64, f64)| (p.0 + PL_OFF.0, -p.1 + PL_OFF.1);
    let mut b = Pcb::new();
    let (w, h) = (PLATE_W / 2.0, PLATE_H / 2.0);
    b.poly(&[o((-w, -h)), o((w, -h)), o((w, h)), o((-w, h))]);
    for (i, &(u, v)) in PLATE_SCREWS.iter().enumerate() {
        b.drill(&format!("S{}", i + 1), o((u, v)), PLATE_SCREW_D);
    }
    for j in 0..2 {
        let g = plate_uv(gland(j).1, wire_z());
        b.circle(o(g), GLAND_HOLE);
    }
    // Slot for the bridge tab (board top .. bridge top, plus clearance).
    let c = plate_uv(35.0, BOARD_TOP + BRIDGE_T / 2.0);
    b.rect(o(c), TAB_W + 2.0 * SLOT_CLR, BRIDGE_T + 2.0 * SLOT_CLR, 0.0);
    let gp = plate_uv(gland(0).1, wire_z());
    let gn = plate_uv(gland(1).1, wire_z());
    b.text(o((gp.0, gp.1 + 12.0)), 2.5, "TIP +");
    b.text(o((gn.0, gn.1 + 12.0)), 2.5, "TIP -");
    b.text(o((0.0, -17.0)), 1.8, "HV 1.5 kV  (3 kV EXTENSION, QUALIFY FIRST)  ISOLATED DUT ONLY");
    b.text(o((0.0, -20.5)), 1.4, "TEMPER PROBE REV C TIP PLATE - FR4, NO COPPER");
    b
}

// ======================================================================
// Section view
// ======================================================================
fn svg() -> String {
    let k = 4.0; // px per mm
    let mut s = String::new();
    let (w, h) = (1040.0, 820.0);
    writeln!(s, "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" viewBox=\"0 0 {w} {h}\" font-family=\"Helvetica, Arial, sans-serif\" font-size=\"12\">").unwrap();
    writeln!(s, "<rect width=\"100%\" height=\"100%\" fill=\"white\"/>").unwrap();
    writeln!(s, "<defs><marker id=\"a\" viewBox=\"0 0 10 10\" refX=\"10\" refY=\"5\" markerWidth=\"7\" markerHeight=\"7\" orient=\"auto-start-reverse\"><path d=\"M0,0 L10,5 L0,10 z\" fill=\"#333\"/></marker></defs>").unwrap();
    // --- plan view (x, y) ---
    let px = |x: f64| 60.0 + (x - TIP_PLATE_X + 20.0) * k;
    let py = |y: f64| 70.0 + (y + SIDE_GAP) * k;
    writeln!(s, "<text x=\"20\" y=\"28\" font-size=\"16\" font-weight=\"bold\">Rev C HV lead entry: plan (top) and section through TIP+ (bottom). Generated by tools/leads.rs; dimensions in mm.</text>").unwrap();
    writeln!(s, "<text x=\"20\" y=\"50\" font-size=\"13\">Plan, lid removed. Grey: aluminium extrusion. Tan: copper-free FR4 (tip plate, lead bridge). Green: probe board. Red/black: leads.</text>").unwrap();
    // box walls
    let xr = 152.0;
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#888\" stroke-width=\"6\"/>", px(TIP_PLATE_X), py(-SIDE_GAP), px(xr) - px(TIP_PLATE_X), BOX_W * k).unwrap();
    // board
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#cfe8cf\" stroke=\"#2e7d32\"/>", px(0.0), py(0.0), (xr - 4.0 - 0.0) * k, 70.0 * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"white\" stroke=\"#2e7d32\"/>", px(0.0), py(34.2), 36.0 * k, 1.6 * k).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">probe board (ladder from x = 12.5)</text>", px(40.0), py(36.5)).unwrap();
    // plate
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#e8d2a6\" stroke=\"#8d6e3f\"/>", px(TIP_PLATE_X - PLATE_T), py(-SIDE_GAP), PLATE_T * k, BOX_W * k).unwrap();
    // bridge outline (plan)
    let br = bridge_outline();
    let pts: Vec<String> = br.iter().map(|&(x, y)| format!("{:.1},{:.1}", px(x), py(y))).collect();
    writeln!(s, "<polygon points=\"{}\" fill=\"#e8d2a6\" fill-opacity=\"0.8\" stroke=\"#8d6e3f\"/>", pts.join(" ")).unwrap();
    for &(x, y) in &H34 {
        writeln!(s, "<circle cx=\"{}\" cy=\"{}\" r=\"{}\" fill=\"white\" stroke=\"#333\"/>", px(x), py(y), 1.7 * k).unwrap();
    }
    for j in 0..2 {
        let col = if j == 0 { "#c62828" } else { "#222" };
        let p = lead_path(j);
        let mut d = format!("M{:.1},{:.1}", px(p[0].0 - 25.0), py(p[0].1));
        for q in &p {
            write!(d, " L{:.1},{:.1}", px(q.0), py(q.1)).unwrap();
        }
        writeln!(s, "<path d=\"{d}\" fill=\"none\" stroke=\"{col}\" stroke-width=\"{}\" stroke-linecap=\"round\"/>", OD_NOM * k).unwrap();
        let (gx, gy) = gland(j);
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", px(gx - PLATE_T - 9.0), py(gy - 7.5), 9.0 * k, 15.0 * k).unwrap();
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", px(gx), py(gy - GLAND_NUT_AC / 2.0), NUT_T * k, GLAND_NUT_AC * k).unwrap();
        let (wx, wy) = W_HV[j];
        writeln!(s, "<circle cx=\"{}\" cy=\"{}\" r=\"{}\" fill=\"#d4a017\" stroke=\"#7a5c00\"/>", px(wx), py(wy), PAD_R * k).unwrap();
        for &tx in &TIES_X {
            let y = path_y(&p, tx);
            writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#fff\" stroke=\"#1565c0\" stroke-width=\"2\"/>", px(tx - 1.25), py(y - OD_NOM / 2.0 - TIE_GAP - TIE_SLOT.1), 2.5 * k, (OD_NOM + 2.0 * TIE_GAP + 2.0 * TIE_SLOT.1) * k).unwrap();
        }
        writeln!(s, "<text x=\"{}\" y=\"{}\">W_HV{} ({wx}, {wy})</text>", px(wx) + 12.0, py(wy) + if j == 0 { -10.0 } else { 20.0 }, j + 1).unwrap();
    }
    writeln!(s, "<text x=\"{}\" y=\"{}\" fill=\"#1565c0\">blue: cable ties through slot pairs at x = {}, {}, {}</text>", px(-56.0), py(55.0), TIES_X[0], TIES_X[1], TIES_X[2]).unwrap();
    dim(&mut s, (px(TIP_PLATE_X), py(73.0)), (px(0.0), py(73.0)), &format!("{:.1} plate inner face to board edge", -TIP_PLATE_X));
    dim(&mut s, (px(-8.0), py(27.0)), (px(-8.0), py(43.0)), "16.0");
    dim(&mut s, (px(TIP_PLATE_X - 14.0), py(35.0 - GLAND_DY)), (px(TIP_PLATE_X - 14.0), py(35.0 + GLAND_DY)), &format!("{:.0} gland pitch", 2.0 * GLAND_DY));
    dim(&mut s, (px(20.0), py(-SIDE_GAP)), (px(20.0), py(0.0)), &format!("{SIDE_GAP:.1}"));
    writeln!(s, "<text x=\"{}\" y=\"{}\" font-size=\"11\">leads leave left, toward stage 53: twisted pair {:.0} mm + tails {:.0} mm</text>", 20.0, py(-SIDE_GAP) - 4.0, L_EXT - L_TAIL, L_TAIL).unwrap();
    // --- section through TIP+ (x, z) ---
    let top = py(BOX_W - SIDE_GAP) + 70.0;
    let sx = |x: f64| px(x);
    let sz = |z: f64| top + (BOX_H + 10.0 - z) * k;
    writeln!(s, "<text x=\"20\" y=\"{}\" font-size=\"13\">Section A-A on y = {} (TIP+ lead), side view. z from the inner floor.</text>", top - 12.0, W_HV[0].1).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#888\" stroke-width=\"6\"/>", sx(TIP_PLATE_X), sz(BOX_H), sx(xr) - sx(TIP_PLATE_X), BOX_H * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#e8d2a6\" stroke=\"#8d6e3f\"/>", sx(TIP_PLATE_X - PLATE_T), sz(BOX_H + 1.5), PLATE_T * k, (BOX_H + 3.0) * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#cfe8cf\" stroke=\"#2e7d32\"/>", sx(0.0), sz(BOARD_TOP), (xr - 4.0) * k, BOARD_T * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#e8d2a6\" stroke=\"#8d6e3f\"/>", sx(bridge_x0()), sz(BOARD_TOP + BRIDGE_T), (BRIDGE_X1 - bridge_x0()) * k, BRIDGE_T * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#e8d2a6\" fill-opacity=\"0.5\" stroke=\"#8d6e3f\" stroke-dasharray=\"4 3\"/>", sx(BRIDGE_X1), sz(BOARD_TOP + BRIDGE_T), (ARM_X2 - BRIDGE_X1) * k, BRIDGE_T * k).unwrap();
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
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", sx(TIP_PLATE_X - PLATE_T - 9.0), sz(wz + 7.5), 9.0 * k, 15.0 * k).unwrap();
    writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#bbb\" stroke=\"#555\"/>", sx(TIP_PLATE_X), sz(wz + GLAND_NUT_AC / 2.0), NUT_T * k, GLAND_NUT_AC * k).unwrap();
    for &tx in &TIES_X {
        writeln!(s, "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"none\" stroke=\"#1565c0\" stroke-width=\"2\"/>", sx(tx - 1.25), sz(wz + OD_NOM / 2.0 + 0.6), 2.5 * k, (OD_NOM + BRIDGE_T + 1.8) * k).unwrap();
    }
    let up = BOX_H - (BOARD_TOP + FILLET_UP);
    let down = BOARD_UNDER - TAIL_DOWN;
    dim(&mut s, (sx(wx + 6.0), sz(BOARD_TOP + FILLET_UP)), (sx(wx + 6.0), sz(BOX_H)), &format!("{up:.2} joint to lid (>= 20)"));
    dim(&mut s, (sx(wx + 6.0), sz(0.0)), (sx(wx + 6.0), sz(BOARD_UNDER - TAIL_DOWN)), &format!("{down:.2} tail to floor (>= 20)"));
    dim(&mut s, (sx(-12.0), sz(BOARD_TOP)), (sx(-12.0), sz(BOARD_TOP + BRIDGE_T + OD_NOM + OD_TOL)), &format!("{:.2} loop (<= 5.5)", BRIDGE_T + OD_NOM + OD_TOL));
    dim(&mut s, (sx(TIP_PLATE_X + 12.0), sz(wz)), (sx(TIP_PLATE_X + 12.0), sz(BOX_H)), &format!("{:.2} lead axis to lid", BOX_H - wz));
    dim(&mut s, (sx(60.0), sz(0.0)), (sx(60.0), sz(BOARD_UNDER)), &format!("{BOARD_UNDER:.1}"));
    dim(&mut s, (sx(80.0), sz(0.0)), (sx(80.0), sz(BOX_H)), &format!("{BOX_H:.2} min internal"));
    writeln!(s, "<text x=\"{}\" y=\"{}\">W_HV1 joint</text>", sx(wx) - 120.0, sz(BOARD_TOP) - 40.0).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">FR4 tip plate {PLATE_T} mm, gland</text>", sx(TIP_PLATE_X + 3.0), sz(BOX_H + 4.0)).unwrap();
    writeln!(s, "<text x=\"{}\" y=\"{}\">lead bridge {BRIDGE_T} mm FR4 on board top (arms dashed)</text>", sx(-45.0), sz(BOARD_TOP) + 22.0).unwrap();
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
fn bridge_outline() -> Vec<(f64, f64)> {
    // The main plate starts clear of the gland locknuts; a tab passes between
    // the two locknuts and through the plate's slot.
    let x0 = bridge_x0();
    let (y0, y1) = (H34[0].1 - ARM_W / 2.0, H34[1].1 + ARM_W / 2.0);
    let xt = TIP_PLATE_X - PLATE_T - TAB_OUT;
    vec![
        (x0, y0), (ARM_X2, y0), (ARM_X2, y0 + ARM_W), (BRIDGE_X1, y0 + ARM_W),
        (BRIDGE_X1, y1 - ARM_W), (ARM_X2, y1 - ARM_W), (ARM_X2, y1), (x0, y1),
        (x0, 35.0 + TAB_W / 2.0), (xt, 35.0 + TAB_W / 2.0),
        (xt, 35.0 - TAB_W / 2.0), (x0, 35.0 - TAB_W / 2.0),
    ]
}
fn bridge_x0() -> f64 {
    TIP_PLATE_X + NUT_T + 1.0
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
    writeln!(r, "Rev C HV leads: capacitance, inductance, resonance and setback budget (generated by tools/leads.rs; do not edit).").unwrap();
    writeln!(r, "Calculated from stated geometry and datasheet dimensions; nothing here is measured. 'Bound' marks a rigorous").unwrap();
    writeln!(r, "inequality given the stated permittivity bracket and geometry; 'estimate' marks a model value the bench must confirm.\n").unwrap();

    // ---- Ladder ----
    let c_in_nom = C_SECTION / 5.0;
    let c_in_max = C_SECTION * (1.0 + C_SECTION_TOL) / 5.0;
    let c_in_min = C_SECTION * (1.0 - C_SECTION_TOL) / 5.0;
    writeln!(r, "Ladder input capacitance per tip (5 x 33 pF +/-5 % in series): {c_in_min:.3}..{c_in_max:.3} pF (nominal {c_in_nom:.3}).").unwrap();

    // ---- Wire ----
    let (da, db) = (d_area(), COND_BUNDLE);
    let (od_lo, od_hi) = (OD_NOM - OD_TOL, OD_NOM + OD_TOL);
    writeln!(r, "Wire: conductor {da:.3} mm equal-area / {db:.2} mm bundle; OD {OD_NOM:.2} +/- {OD_TOL:.2} mm; silicone er {ER_MIN}..{ER_MAX}; rated {WIRE_RATED_KV_DC:.0} kV DC.").unwrap();
    let e_cond = V_EXT / (db / 2.0 * (od_lo / db).ln()) / 1000.0;
    let e_rated = WIRE_RATED_KV_DC * 1000.0 / (db / 2.0 * (od_lo / db).ln()) / 1000.0;
    writeln!(r, "Insulation stress at the conductor, wire lying on earthed metal (coaxial limit, thinnest wall): {e_cond:.2} kV/mm at {V_EXT:.0} V; {e_rated:.1} kV/mm at the {WIRE_RATED_KV_DC:.0} kV rating.").unwrap();

    // ---- External pair ----
    let twisted = (L_EXT - L_TAIL) / 1000.0;
    let tails = L_TAIL / 1000.0;
    writeln!(r, "\nExternal lead: {L_EXT:.0} mm, gland face to tip contact: twisted pair {:.0} mm, then {L_TAIL:.0} mm untwisted tails.", twisted * 1e3).unwrap();
    let ll_air = pair(db, od_hi, 1.0);
    let ll_hi = PI * EPS0 * ER_MAX / (od_lo / db).ln() * 1e12;
    writeln!(r, "Lead-to-lead (twisted, insulations touching): air-filled lower estimate {ll_air:.1} pF/m; bound <= {ll_hi:.1} pF/m").unwrap();
    writeln!(r, "  (concentric conductors, thinnest OD, both shells at er_max, the space between them shorted) -> <= {:.2} pF over the twisted section.", ll_hi * twisted).unwrap();
    // Common-mode loading per leg. A leg of a pair driven in common mode never
    // carries more charge than the same wire alone; the twisted section behaves
    // as one conductor of radius sqrt(r * s) shared by two legs.
    let r_eq = (db / 2.0 * od_hi).sqrt();
    let cm_lone = |h: f64| wire_plane_series(db, od_lo, ER_MAX, h);
    let cm_pair_leg = |h: f64| wire_plane(2.0 * r_eq, h, 1.0) / 2.0 * (1.0 + 0.1);
    let cm_air = |h: f64| wire_plane(da, h, 1.0);
    writeln!(r, "Per-leg capacitance to earth in common mode:").unwrap();
    for h in [H_REF, 100.0, H_FAR] {
        writeln!(r, "  axis {h:>3.0} mm from earthed metal: lone wire {:.2} pF/m (estimate, series shell, er_max); twisted pair per leg {:.2} pF/m (estimate, equivalent radius {r_eq:.2} mm, +10 % for the shells); air lower estimate (lone, equal-area) {:.2} pF/m.", cm_lone(h), cm_pair_leg(h), cm_air(h)).unwrap();
    }
    let lone_bound = wire_plane(db, H_REF, ER_MAX);
    writeln!(r, "  bound, any route in air with the axis >= {H_REF:.0} mm from earth (lone wire, er_max everywhere): <= {lone_bound:.1} pF/m -> <= {:.1} pF per leg.", lone_bound * L_EXT / 1000.0).unwrap();
    let ext_ref = cm_pair_leg(H_REF) * twisted + cm_lone(H_REF) * tails;
    let ext_far = cm_air(H_FAR) * (twisted + tails) / 2.0;
    let lying = coax(db, od_lo, ER_MAX);
    writeln!(r, "  lying on earthed metal along its whole length: bound <= {lying:.1} pF/m (concentric conductor, thinnest OD, er_max) -> <= {:.1} pF per leg.", lying * L_EXT / 1000.0).unwrap();

    // ---- Internal run ----
    let wz = wire_z();
    let r_lid = BOX_H - wz;
    let (h_lid, h_floor) = (r_lid, wz);
    // Wire between two parallel earthed planes (lid and floor), image series,
    // with the insulation shell in series (estimate); bound: coax at the lid.
    let between = {
        let a = h_lid + h_floor;
        let x = h_floor;
        let geom = (2.0 * a / (PI * od_hi / 2.0) * (PI * x / a).sin()).ln();
        2.0 * PI * EPS0 / ((od_lo / db).ln() / ER_MAX + geom) * 1e12
    };
    let int_bound = 2.0 * PI * EPS0 / ((od_lo / db).ln() / ER_MAX + (2.0 * r_lid / od_hi).ln()) * 1e12;
    let li = l_int(0);
    writeln!(r, "\nEnclosure: end-plate inner faces {BOX_L_INT:.1} mm apart (220.0 extrusion + 2 x 1.60 bezel lip); output plate at x = {OUT_PANEL_X:.2} (BNC housing face), so the tip plate's inner face is at x = {TIP_PLATE_X:.2}, {:.2} mm from the board's tip edge.", -TIP_PLATE_X).unwrap();
    writeln!(r, "Internal run: lead axis z = {wz:.2} mm, {h_lid:.2} mm below the lid and {h_floor:.2} mm above the floor.").unwrap();
    for j in 0..2 {
        let (gx, gy) = gland(j);
        writeln!(r, "  leg {}: gland ({gx:.2}, {gy:.1}) to W_HV{} ({:.0}, {:.0}): {:.2} mm.", ["P", "N"][j], j + 1, W_HV[j].0, W_HV[j].1, l_int(j)).unwrap();
    }
    writeln!(r, "  C to earth: estimate {:.3} pF ({between:.1} pF/m between lid and floor, shell in series); coax at the lid distance {:.3} pF. Neither models the FR4 bridge under the lead or the board copper near W_HV, so neither is a bound.", between * li / 1000.0, int_bound * li / 1000.0).unwrap();
    gate((l_int(0) - l_int(1)).abs() < 1e-9, format!("internal routes are mirror images of equal length {li:.2} mm"), &mut r);
    let c_int = between * li / 1000.0;

    // ---- Per-tip budget ----
    let fixed = c_in_max + RESERVE_BOARD + RESERVE_TIP + c_int;
    let total = fixed + ext_ref;
    writeln!(r, "\nPer-tip capacitance to earth (estimate):").unwrap();
    writeln!(r, "  ladder max {c_in_max:.2} + board/enclosure reserve {RESERVE_BOARD:.2} + tip reserve {RESERVE_TIP:.2} + internal {c_int:.2} + external at {H_REF:.0} mm {ext_ref:.2} = {total:.2} pF.").unwrap();
    let per_m = ext_ref / (L_EXT / 1000.0);
    let l_tent = (C_TIP_TENTATIVE - fixed) / cm_lone(H_REF) * 1000.0;
    writeln!(r, "  the tentative {C_TIP_TENTATIVE:.0} pF leaves {:.2} pF for the external lead: {:.0} mm even as a lone wire, too short to reach J5 and the C22 free hole ({S_TIP_MAX:.1} mm apart).", C_TIP_TENTATIVE - fixed, l_tent).unwrap();
    gate(total <= C_TIP_TARGET, format!("per-tip loading {total:.2} pF <= {C_TIP_TARGET:.0} pF (lead >= {H_REF:.0} mm from earthed metal)"), &mut r);
    writeln!(r, "  longest external lead within {C_TIP_TARGET:.0} pF at this mix: {:.0} mm (chosen {L_EXT:.0} mm; {per_m:.2} pF/m).", (C_TIP_TARGET - fixed) / per_m * 1000.0).unwrap();
    writeln!(r, "  far-field (axis {H_FAR:.0} mm, air) lower estimate for the external lead: {ext_far:.2} pF.").unwrap();
    writeln!(r, "  lead lying on earthed metal: up to {:.1} pF per tip (bound); the operating rule forbids it.", fixed + lying * L_EXT / 1000.0).unwrap();

    // ---- Derived figures quoted in docs/hv-leads.md ----
    let dvdt = 70e9; // V/s, the stage-53 switch-edge figure used in design.md
    writeln!(r, "  switch-edge current at 70 V/ns: ideal ladder {:.2} A, this budget {:.2} A, lead lying on metal (bound) {:.1} A.", dvdt * c_in_nom * 1e-12, dvdt * total * 1e-12, dvdt * (fixed + lying * L_EXT / 1000.0) * 1e-12).unwrap();
    writeln!(r, "  reactance of the per-tip budget at 60 kHz: {:.0} kOhm.", 1.0 / (2.0 * PI * 60e3 * total * 1e-12) / 1e3).unwrap();
    writeln!(r, "  lead-to-lead over the twisted section: air-filled estimate {:.2} pF.", ll_air * twisted).unwrap();
    writeln!(r, "  tap stray that alone limits CMRR to 60 dB: {:.4} pF (0.1 % of the {c_in_nom:.1} pF top capacitance).", 1e-3 * c_in_nom).unwrap();
    // Open tip end: below-cutoff attenuation of the lowest mode, ~27.3 dB per
    // (depth / widest aperture), evaluated at the tap and buffers.
    let depth = 57.5 - TIP_PLATE_X; // tap node x = 57.5
    writeln!(r, "  open tip end: tap {depth:.0} mm inside; below-cutoff estimate {:.0} dB for a {BOX_W:.0} mm aperture (27.3 dB per aperture width).", 27.3 * depth / BOX_W).unwrap();

    // ---- Inductance and resonance ----
    let l_tw = pair_l(da, od_lo) * twisted;
    let n = 400;
    let integ = |len: f64, s0: f64, s1: f64| -> f64 {
        (0..n).map(|i| {
            let t = (i as f64 + 0.5) / n as f64;
            pair_l(da, s0 + t * (s1 - s0)) * len / 1000.0 / n as f64
        }).sum()
    };
    let l_tail = integ(L_TAIL, od_lo, S_TIP_MAX);
    let l_in = integ(li, 2.0 * GLAND_DY, 16.0);
    let l_dm = l_tw + l_tail + l_in;
    writeln!(r, "\nDifferential loop inductance (upper estimate: equal-area conductor, low-frequency internal inductance):").unwrap();
    writeln!(r, "  twisted {l_tw:.3} + tails opening to {S_TIP_MAX:.1} mm {l_tail:.3} + internal {l_in:.3} = {l_dm:.3} uH.").unwrap();
    let c_dm = c_in_max / 2.0 + ll_hi * twisted + RESERVE_TIP;
    let f_dm = f_res(l_dm, c_dm);
    writeln!(r, "  C = ladder/2 {:.2} + lead-to-lead bound {:.2} + tip {RESERVE_TIP:.2} = {c_dm:.2} pF, all lumped at the probe end: f0 = {f_dm:.1} MHz (lower estimate).", c_in_max / 2.0, ll_hi * twisted).unwrap();
    let l_cm = plane_l(2.0 * r_eq, H_FAR) * (L_EXT + li) / 1000.0;
    let c_cm = 2.0 * total;
    let f_cm = f_res(l_cm, c_cm);
    writeln!(r, "Common mode: pair over an earth return {H_FAR:.0} mm away, {l_cm:.3} uH with both tips' {c_cm:.1} pF: f0 = {f_cm:.1} MHz.").unwrap();
    let f_q = C0 / ER_MAX.sqrt() / (4.0 * (L_EXT + li) / 1000.0) / 1e6;
    writeln!(r, "Quarter-wave resonance of the whole lead, er_max throughout: {f_q:.0} MHz.").unwrap();
    gate(f_dm >= 10.0 * BW, format!("differential lead resonance {f_dm:.1} MHz >= 10 x the {BW:.0} MHz bandwidth"), &mut r);
    let rise = |f: f64| 1.0 / (1.0 - (f / f_dm).powi(2)) - 1.0;
    writeln!(r, "  undamped differential LC rise: {:.2} % at {BW:.0} MHz, {:.1e} % at 60 kHz.", 100.0 * rise(BW), 100.0 * rise(0.06)).unwrap();
    // CM-to-DM conversion: with the legs tightly coupled, a common-mode current
    // difference sees only the leakage inductance L_dm/2.
    let dc = 2.0 * C_SECTION_TOL * c_in_nom + 0.5;
    for f in [0.06, 1.0, BW] {
        let w = 2.0 * PI * f * 1e6;
        let e = w * w * l_dm / 2.0 * 1e-6 * dc * 1e-12;
        writeln!(r, "  CM-to-DM conversion through the lead for a {dc:.2} pF leg-load mismatch at {f} MHz: {e:.1e} ({:.0} dB).", -20.0 * e.log10()).unwrap();
    }
    // Unequal self-inductance from a length mismatch adds jw dL I_cm.
    let dl_mm = 2.0;
    let l_self = MU0 / (2.0 * PI) * ((2.0 * (L_EXT + li) / 1000.0 / (da / 2000.0)).ln() - 1.0); // H/m
    let w = 2.0 * PI * BW * 1e6;
    let e_len = w * w * l_self * dl_mm / 1000.0 * total * 1e-12;
    writeln!(r, "  length mismatch {dl_mm:.0} mm ({:.2} nH of partial self-inductance) at {BW:.0} MHz: {e_len:.1e} ({:.0} dB).", l_self * dl_mm * 1e6, -20.0 * e_len.log10()).unwrap();
    let e5 = w * w * l_dm / 2.0 * 1e-6 * dc * 1e-12 + e_len;
    gate(e5 <= 1e-3, format!("lead CM-to-DM conversion at {BW:.0} MHz (load mismatch + length mismatch) {:.0} dB >= 60 dB", -20.0 * e5.log10()), &mut r);
    let area = 0.5 * L_TAIL * S_TIP_MAX * 1e-6;
    let b = MU0 * I_COIL / (2.0 * PI * R_COIL * 1e-3);
    let emf = 2.0 * PI * 35e3 * b * area;
    writeln!(r, "Magnetic pickup example: tails' open triangle {:.0} mm2 in {:.2} mT peak ({I_COIL:.0} A peak at {R_COIL:.0} mm, 35 kHz): {emf:.3} V peak, {:.4} % of 1 kV.", area * 1e6, b * 1e3, emf / 1000.0 * 100.0).unwrap();

    // ---- Setback ----
    writeln!(r, "\nSetback from exposed HV conductors to earthed metal (>= {SETBACK:.0} mm required):").unwrap();
    let mut worst = f64::INFINITY;
    for (j, &(x, y)) in W_HV.iter().enumerate() {
        let up = BOX_H - (BOARD_TOP + FILLET_UP);
        let down = BOARD_UNDER - TAIL_DOWN;
        let side = (y - PAD_R + SIDE_GAP).min(70.0 - y - PAD_R + SIDE_GAP);
        let end = x - PAD_R - TIP_PLATE_X;
        writeln!(r, "  W_HV{} joint: lid {up:.2}, floor {down:.2}, side wall {side:.2} mm; the tip-end plate is FR4 ({end:.1} mm away).", j + 1).unwrap();
        worst = worst.min(up).min(down).min(side);
    }
    let pc = (PLATE_CY, PLATE_CZ);
    let mut screw = f64::INFINITY;
    for j in 0..2 {
        let g = plate_uv(gland(j).1, wz);
        for &(u, v) in &PLATE_SCREWS {
            screw = screw.min(((u - g.0).powi(2) + (v - g.1).powi(2)).sqrt() - PLATE_SCREW_D / 2.0 - GLAND_HOLE / 2.0);
        }
    }
    writeln!(r, "  tip plate: metal end-panel screw edge to gland-hole edge {screw:.2} mm (the lead inside the hole is insulated twice: wire and gland).").unwrap();
    let wire_lid = BOX_H - wz - od_hi / 2.0;
    let wire_side = (35.0 - GLAND_DY + SIDE_GAP).min(W_HV[0].1 + SIDE_GAP) - od_hi / 2.0;
    writeln!(r, "  internal lead conductor to lid {:.2} mm, insulation surface to lid {wire_lid:.2} mm, to side wall >= {wire_side:.2} mm.", BOX_H - wz).unwrap();
    let _ = pc;
    gate(worst >= SETBACK, format!("every exposed HV joint >= {SETBACK:.0} mm from metal (worst {worst:.2} mm)"), &mut r);
    gate(BOX_H - wz >= SETBACK, format!("internal lead conductor {:.2} mm >= {SETBACK:.0} mm from the lid", BOX_H - wz), &mut r);
    gate(screw >= SETBACK, format!("plate screw to gland hole {screw:.2} mm >= {SETBACK:.0} mm"), &mut r);
    let loop_h = BRIDGE_T + od_hi;
    gate(loop_h <= 5.5, format!("lead height above the board {loop_h:.2} mm <= 5.5 mm"), &mut r);
    gate(V_EXT / 1000.0 <= WIRE_RATED_KV_DC / 3.0, format!("wire DC rating {WIRE_RATED_KV_DC:.0} kV >= 3 x the {:.0} kV extension", V_EXT / 1000.0), &mut r);
    let web = GLAND_DY - GLAND_HOLE / 2.0 - (TAB_W / 2.0 + SLOT_CLR);
    gate(web >= 3.0, format!("FR4 web between a gland hole and the tab slot {web:.2} mm >= 3 mm"), &mut r);
    let nut_tab = GLAND_DY - GLAND_NUT_AC / 2.0 - TAB_W / 2.0;
    gate(nut_tab >= 1.0, format!("bridge tab clears the gland locknuts by {nut_tab:.2} mm"), &mut r);
    let first_tie = TIES_X[0] - TIE_SLOT.0 / 2.0 - bridge_x0();
    gate(first_tie >= 2.0, format!("first tie slot {first_tie:.2} mm from the bridge's plate-end edge"), &mut r);
    let gap_nuts = 2.0 * GLAND_DY - GLAND_NUT_AC;
    gate(gap_nuts >= 3.0, format!("gland locknuts clear each other by {gap_nuts:.1} mm"), &mut r);
    let nut_lid = BOX_H - (wz + GLAND_NUT_AC / 2.0);
    gate(nut_lid >= 2.0 && wz - GLAND_NUT_AC / 2.0 >= BOARD_TOP - 6.0, format!("gland locknut inside the box clears the lid by {nut_lid:.1} mm"), &mut r);

    fs::create_dir_all("validation/leads").unwrap();
    fs::write("validation/leads/leads.txt", &r).unwrap();
    bridge().write("mech/lead-bridge/lead-bridge.kicad_pcb", BRIDGE_T);
    plate().write("mech/tip-plate/tip-plate.kicad_pcb", PLATE_T);
    fs::write("docs/hv-leads-section.svg", svg()).unwrap();
    print!("{r}");
    if !failed.is_empty() {
        eprintln!("leads: {} gate(s) failed", failed.len());
        std::process::exit(1);
    }
}

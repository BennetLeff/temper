//! Rev C explicit probe placement and hand-authored routing. KiCad owns pad transforms.
//!
//! The two divider legs are mirror images about the inter-leg slot axis y = AXIS.
//! Leg P lies above the axis (smaller y), leg N below. Every leg-P coordinate in
//! the divider and low-leg cells is generated once and mirrored for leg N.
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fs,
};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
const LENGTH: f64 = 150.;
const HEIGHT: f64 = 70.;
const AXIS: f64 = 35.;
/// Resistor-row pitch between the legs (rows face each other across the slot).
const PITCH: f64 = 16.;
/// Capacitor row offset, outward from each resistor row.
const CAP_OFFSET: f64 = 7.;
/// Section pitch along the ladder and first section centre.
const SECTION: f64 = 9.;
const FIRST: f64 = 17.;
const TIP_X: f64 = 7.;
/// Inter-leg notch: open to the tip-end board edge, 1.6 mm nominal (>= 1.4 mm
/// finished at JLC +/-0.2 mm), ending at x = NOTCH.0. Being open at the edge it
/// leaves no surface path around its tip-end.
const NOTCH: (f64, f64) = (36., 1.6);
/// Inner/bottom pours and hidden-layer routing are allowed only for x >= PLANE_X.
const PLANE_X: f64 = 59.;
/// Low-leg (tap) cell origin shift relative to the Rev C draft coordinates.
const CELL_DX: f64 = -17.;

fn mirror(y: f64) -> f64 {
    2. * AXIS - y
}
/// Resistor-row and capacitor-row y for leg j (0 = P above the axis, 1 = N below).
fn rows(j: usize) -> (f64, f64) {
    let p = (AXIS - PITCH / 2., AXIS - PITCH / 2. - CAP_OFFSET);
    if j == 0 {
        p
    } else {
        (mirror(p.0), mirror(p.1))
    }
}
fn section_x(i: usize) -> f64 {
    FIRST + SECTION * i as f64
}
/// x of the vertical node trace joining resistor and capacitor rows, node k = 0..5.
fn node_x(k: usize) -> f64 {
    FIRST - SECTION / 2. + SECTION * k as f64
}

fn landing(name: &str, pads: &[(u8, f64, f64)], diam: f64, drill: f64) -> Result<()> {
    let mut s=format!("(footprint \"{name}\" (version 20241229) (generator \"temper_probe\") (layer \"F.Cu\") (attr through_hole board_only exclude_from_pos_files exclude_from_bom) (property \"Reference\" \"W\" (at 0 -4) (layer \"F.SilkS\") (effects (font (size .8 .8) (thickness .12)))) (property \"Value\" \"wire landing\" (at 0 4) (layer \"F.Fab\") (effects (font (size .8 .8) (thickness .12))))");
    for &(n, x, y) in pads {
        s+=&format!("(pad \"{n}\" thru_hole circle (at {x} {y}) (size {diam} {diam}) (drill {drill}) (layers \"*.Cu\" \"*.Mask\"))");
    }
    s += ")\n";
    fs::write(format!("cad/Probe.pretty/{name}.kicad_mod"), s)?;
    Ok(())
}

/// Leg-P low-leg cell, (reference, x, y, angle). Leg N uses mirrored y and the
/// mirrored angle; pads of these parts are mirror-symmetric under that map.
fn low_leg_cell() -> Vec<(&'static str, &'static str, f64, f64, i32)> {
    // (leg-P ref, leg-N ref, x, y, angle)
    vec![
        ("C41", "C51", 78.0, 11.0, 0),
        ("C42", "C52", 77.5, 14.5, 0),
        ("C43", "C53", 77.5, 17.5, 0),
        ("CT1", "CT2", 79.0, 23.0, 180),
        ("R11", "R31", 78.0, 7.0, 0),
        ("RV1", "RV2", 82.0, 7.0, 180),
        ("R12", "R32", 80.0, 29.5, 0),
        ("D1", "D2", 85.0, 28.4, 270),
    ]
    .into_iter()
    .map(|(p, n, x, y, a)| (p, n, x + CELL_DX, y, a))
    .collect()
}
fn mirrored_angle(a: i32) -> i32 {
    // Mirroring about a horizontal line: 90 <-> 270, 0 and 180 keep their pad rows.
    match a {
        90 => 270,
        270 => 90,
        other => other,
    }
}

fn placement() -> Result<()> {
    landing("HV_Captive_Lead", &[(1, 0., 0.)], 4., 1.6)?;
    let mut s = "reference\tx\ty\tangle\tfootprint_override\tside\n".to_string();
    let mut seen = BTreeSet::new();
    let mut put_side = |r: String, x: f64, y: f64, a: i32, fp: &str, side: &str| {
        assert!(seen.insert(r.clone()), "duplicate {r}");
        s += &format!("{r}\t{x:.4}\t{y:.4}\t{a}\t{fp}\t{side}\n");
    };
    let mut put = |r: String, x: f64, y: f64, a: i32, fp: &str| put_side(r, x, y, a, fp, "F");
    for j in 0..2 {
        let (ry, cy) = rows(j);
        let base = j * 20;
        for i in 0..5 {
            put(format!("R{}", base + i + 1), section_x(i), ry, 0, "");
            put(format!("C{}", base + i + 1), section_x(i), cy, 0, "");
        }
        put(format!("W_HV{}", j + 1), TIP_X, ry, 0, "Probe:HV_Captive_Lead");
    }
    for (p, n, x, y, a) in low_leg_cell() {
        put(p.into(), x, y, a, "");
        put(n.into(), x, mirror(y), mirrored_angle(a), "");
    }
    for (r, x, y, a) in lv_parts() {
        put(r.into(), x, y, a, "");
    }
    for (i, x, y, fp) in mounting_holes() {
        put(format!("H{i}"), x, y, 0, fp);
    }
    drop(put);
    // Battery holders hang beneath the low-voltage section, inside the
    // 20 mm floor setback that the HV region needs anyway.
    for (r, x, y, a) in bottom_parts() {
        put_side(r.into(), x, y, a, "", "B");
    }
    fs::write("layout/placement.tsv", s)?;
    let mut land = "reference\tpin\tnet\nW_HV1\t1\tTIP_P\nW_HV2\t1\tTIP_N\n".to_string();
    for (i, _, _, fp) in mounting_holes() {
        if fp.ends_with("Pad_Via") {
            land += &format!("H{i}\t1\tGND\n");
        }
    }
    fs::write("layout/landings.tsv", land)?;
    let mut labels = "reference\tx\ty\n".to_string();
    for line in fs::read_to_string("layout/placement.tsv")?.lines().skip(1) {
        let a: Vec<_> = line.split('\t').collect();
        let r = a[0];
        let x: f64 = a[1].parse()?;
        let y: f64 = a[2].parse()?;
        // References sit on the Fab layer at the footprint origin.
        let xy = label_offset(r).map_or((x, y), |(dx, dy)| (x + dx, y + dy));
        labels += &format!("{r}\t{}\t{}\n", xy.0, xy.1);
    }
    fs::write("layout/references.tsv", labels)?;
    println!("Placed {} footprints", seen.len());
    Ok(())
}
fn main() -> Result<()> {
    if std::env::args().nth(1).as_deref() == Some("route") {
        route()
    } else {
        placement()
    }
}

#[derive(Clone, Debug)]
struct Pad {
    net: String,
    x: f64,
    y: f64,
    w: f64,
    h: f64,
    angle: f64,
    through: bool,
}
#[derive(Default)]
struct Copper {
    pads: BTreeMap<String, Pad>,
    centers: BTreeMap<String, (f64, f64)>,
    out: String,
    via_done: BTreeSet<String>,
}
impl Copper {
    fn load() -> Result<Self> {
        let mut c = Self::default();
        for l in fs::read_to_string("layout/placement.tsv")?.lines().skip(1) {
            let a: Vec<_> = l.split('\t').collect();
            c.centers
                .insert(a[0].into(), (a[1].parse()?, a[2].parse()?));
        }
        for l in fs::read_to_string("validation/pcb-pads.tsv")?
            .lines()
            .skip(1)
        {
            let a: Vec<_> = l.split('\t').collect();
            if a[1].is_empty() {
                continue;
            }
            c.pads.entry(format!("{}.{}", a[0], a[1])).or_insert(Pad {
                net: a[2].into(),
                x: a[3].parse()?,
                y: a[4].parse()?,
                w: a[5].parse()?,
                h: a[6].parse()?,
                angle: a[7].parse()?,
                through: a[8] == "1",
            });
        }
        Ok(c)
    }
    fn p(&self, key: &str) -> (f64, f64) {
        let p = self
            .pads
            .get(key)
            .unwrap_or_else(|| panic!("no pad {key}"));
        (p.x, p.y)
    }
    fn net(&self, key: &str) -> String {
        self.pads
            .get(key)
            .unwrap_or_else(|| panic!("no pad {key}"))
            .net
            .clone()
    }
    fn path(&mut self, net: &str, layer: &str, width: f64, pts: &[(f64, f64)]) {
        for pair in pts.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            if (a.0 - b.0).abs() < 1e-9 && (a.1 - b.1).abs() < 1e-9 {
                continue;
            }
            self.out += &format!(
                "track\t{net}\t{layer}\t{width}\t{:.6}\t{:.6}\t{:.6}\t{:.6}\n",
                a.0, a.1, b.0, b.1
            );
        }
    }
    fn via(&mut self, net: &str, p: (f64, f64)) {
        let key = format!("{net}:{:.6}:{:.6}", p.0, p.1);
        if self.via_done.insert(key) {
            self.out += &format!("via\t{net}\t{:.6}\t{:.6}\t0.6\t0.3\n", p.0, p.1);
        }
    }
    /// Short F.Cu stub from an SMD pad to a via at an explicit point.
    fn stub(&mut self, key: &str, v: (f64, f64)) {
        let net = self.net(key);
        let p = self.p(key);
        self.path(&net, "F.Cu", 0.25, &[p, v]);
        self.via(&net, v);
    }
    /// Pad-to-pad route on one layer through explicit waypoints. For inner or
    /// bottom layers the pad ends must be through-hole or already have vias at
    /// the first/last waypoint (supplied by the caller with `stub`).
    fn link(&mut self, a: &str, b: &str, layer: &str, mid: &[(f64, f64)]) {
        assert_eq!(self.net(a), self.net(b), "{a} {b}");
        let net = self.net(a);
        let mut pts = vec![self.p(a)];
        pts.extend_from_slice(mid);
        pts.push(self.p(b));
        self.path(&net, layer, 0.25, &pts);
    }
    /// Route through waypoints on F.Cu, changing to `layer` between the first and
    /// last waypoint with vias at both ends.
    fn jump(&mut self, a: &str, b: &str, layer: &str, mid: &[(f64, f64)]) {
        assert_eq!(self.net(a), self.net(b), "{a} {b}");
        assert!(mid.len() >= 2);
        let net = self.net(a);
        let first = mid[0];
        let last = *mid.last().unwrap();
        let pa = self.p(a);
        let pb = self.p(b);
        self.path(&net, "F.Cu", 0.25, &[pa, first]);
        self.via(&net, first);
        self.path(&net, layer, 0.25, mid);
        self.via(&net, last);
        self.path(&net, "F.Cu", 0.25, &[last, pb]);
    }
    fn rect(&mut self, layer: &str, x1: f64, y1: f64, x2: f64, y2: f64) {
        let pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)];
        for p in pts.windows(2) {
            self.out += &format!(
                "line\t{layer}\t0.05\t{}\t{}\t{}\t{}\n",
                p[0].0, p[0].1, p[1].0, p[1].1
            );
        }
    }
    /// Both legs: ladder, capacitor slots, tip landing, low-leg cell copper.
    fn hv(&mut self) {
        for j in 0..2 {
            let (ry, cy) = rows(j);
            let b = j * 20;
            let leg = if j == 0 { "P" } else { "N" };
            for i in 0..5 {
                let r = format!("R{}", b + i + 1);
                let c = format!("C{}", b + i + 1);
                let left = node_x(i);
                let right = node_x(i + 1);
                // Left node of the section: resistor pad 1, capacitor pad 1.
                let net = self.net(&format!("{r}.1"));
                let (r1, c1) = (self.p(&format!("{r}.1")), self.p(&format!("{c}.1")));
                self.path(&net, "F.Cu", 0.25, &[r1, (left, ry), (left, cy), c1]);
                let net = self.net(&format!("{r}.2"));
                let (r2, c2) = (self.p(&format!("{r}.2")), self.p(&format!("{c}.2")));
                self.path(&net, "F.Cu", 0.25, &[r2, (right, ry), (right, cy), c2]);
                // 1.2 x 8 mm routed slot beneath each 600-V section capacitor.
                let x = section_x(i);
                self.rect("Edge.Cuts", x - 0.6, cy - 4., x + 0.6, cy + 4.);
            }
            let tip = self.net(&format!("W_HV{}.1", j + 1));
            let w = self.p(&format!("W_HV{}.1", j + 1));
            self.path(&tip, "F.Cu", 0.25, &[w, (node_x(0), ry)]);
            assert_eq!(tip, format!("TIP_{leg}"));
        }
        // Low-leg cells, authored for leg P (draft coordinates + CELL_DX) and mirrored for leg N.
        let tap_x = node_x(5);
        let d = CELL_DX;
        let bus = 76.5 + d;
        let cell: Vec<(&str, Vec<(f64, f64)>)> = vec![
            // TAP bus from the ladder node to the bank, trimmer, DC trim and R12.
            ("TAP", vec![(tap_x, rows(0).0), (bus, rows(0).0)]),
            ("TAP", vec![(bus, 7.0), (bus, 29.5)]),
            ("TAP", vec![(bus, 7.0), (77.175 + d, 7.0)]),
            ("TAP", vec![(bus, 11.0), (76.525 + d, 11.0)]),
            ("TAP", vec![(bus, 29.5), (79.0875 + d, 29.5)]),
            // DC trim: R11 to RV1 pin 1; RV1 pins 2-3 tied (wiper to end).
            ("TRIM", vec![(78.825 + d, 7.0), (82.0 + d, 7.0)]),
            ("GND", vec![(84.54 + d, 7.0), (87.08 + d, 7.0)]),
            // R12 to the clamp junction; the buffer input route is per-leg below.
            ("IN", vec![(80.9125 + d, 29.5), (85.0 + d, 29.5)]),
        ];
        for j in 0..2 {
            let leg = if j == 0 { "P" } else { "N" };
            for (net, pts) in &cell {
                let name = if *net == "GND" {
                    "GND".to_string()
                } else {
                    format!("{net}_{leg}")
                };
                let pts: Vec<_> = pts
                    .iter()
                    .map(|&(x, y)| (x, if j == 0 { y } else { mirror(y) }))
                    .collect();
                self.path(&name, "F.Cu", 0.25, &pts);
            }
            // Bank and trimmer ground returns: short stubs to GND vias, mirrored.
            for (key, v) in [
                ("C41.2", (80.6 + d, 11.0)),
                ("C42.2", (79.6 + d, 14.5)),
                ("C43.2", (79.6 + d, 17.5)),
                ("CT1.2", (83.5 + d, 23.0)),
                ("RV1.3", (87.08 + d, 9.6)),
            ] {
                let key = if j == 0 {
                    key.to_string()
                } else {
                    paired(key)
                };
                let v = if j == 0 { v } else { (v.0, mirror(v.1)) };
                self.stub(&key, v);
            }
        }
    }
    fn outline(&mut self) {
        let c = 3.;
        let (nx, nw) = NOTCH;
        let pts = [
            (c, 0.),
            (LENGTH - c, 0.),
            (LENGTH, c),
            (LENGTH, HEIGHT - c),
            (LENGTH - c, HEIGHT),
            (c, HEIGHT),
            (0., HEIGHT - c),
            // Inter-leg notch, open at the tip-end edge.
            (0., AXIS + nw / 2.),
            (nx, AXIS + nw / 2.),
            (nx, AXIS - nw / 2.),
            (0., AXIS - nw / 2.),
            (0., c),
            (c, 0.),
        ];
        for p in pts.windows(2) {
            self.out += &format!(
                "line\tEdge.Cuts\t0.05\t{}\t{}\t{}\t{}\n",
                p[0].0, p[0].1, p[1].0, p[1].1
            );
        }
        for (layer, net) in [("In1.Cu", "GND"), ("In2.Cu", "+4V8"), ("B.Cu", "-4V8")] {
            self.out += &format!(
                "zone\t{net}\t{layer}\t{PLANE_X}\t1\t{}\t{}\n",
                LENGTH - 1.,
                HEIGHT - 1.
            );
        }
        // No planes, hidden tracks or vias beneath the HV ladders on any layer.
        for layer in ["In1.Cu", "In2.Cu", "B.Cu"] {
            self.out += &format!("keepout\tall\t{layer}\t0.5\t0.5\t{}\t{}\n", PLANE_X - 1., HEIGHT - 0.5);
        }
        self.out += &format!("keepout\tpours\tF.Cu\t0.5\t0.5\t{}\t{}\n", PLANE_X - 1., HEIGHT - 0.5);
        for (x1, y1, x2, y2) in amplifier_input_voids() {
            for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] {
                self.out += &format!("keepout\tpours\t{layer}\t{x1}\t{y1}\t{x2}\t{y2}\n");
            }
        }
        for (x, y, size, text) in silk_text() {
            self.out += &format!("text\tF.SilkS\t{x}\t{y}\t{size}\t{text}\n");
        }
        self.out += &format!("line\tDwgs.User\t0.2\t{PLANE_X}\t1\t{PLANE_X}\t{}\n", HEIGHT - 1.);
    }
}
/// Both copies of a duplicated THT button pad number (same row), left first.
fn sw3_row(c: &Copper, key: &str) -> ((f64, f64), (f64, f64)) {
    let (x, y) = c.p(key);
    let (cx, _) = c.centers["SW3"];
    let far = (2. * cx - x, y);
    if x < far.0 { ((x, y), far) } else { (far, (x, y)) }
}
fn paired(key: &str) -> String {
    let (r, pin) = key.split_once('.').unwrap();
    for (p, n, _, _, _) in low_leg_cell() {
        if p == r {
            return format!("{n}.{pin}");
        }
    }
    panic!("no pair for {key}")
}
fn route() -> Result<()> {
    let mut c = Copper::load()?;
    c.rules()?;
    c.outline();
    c.hv();
    c.signals();
    fs::write("layout/copper.tsv", c.out)?;
    Ok(())
}

impl Copper {
    fn rules(&self) -> Result<()> {
        // Prototype spacing budget, NOT an IEC/CAT certification: 2 mm air and
        // 4 mm surface per 600-V compensated section (1 mm / 2 mm per 300 V,
        // unchanged from Rev B). Opposite legs use max(rankA, rankB) under
        // simultaneous |tip| <= 3 kV and |differential| <= 3 kV.
        let mut hv = Vec::new();
        for (leg, base) in [(0, 0), (1, 20)] {
            for i in 0..5 {
                hv.push((self.net(&format!("R{}.1", base + i + 1)), leg, 5 - i));
            }
        }
        let names = hv
            .iter()
            .map(|(n, _, _)| format!("B.NetName != '{n}'"))
            .collect::<Vec<_>>()
            .join(" && ");
        let mut s = "(version 1)\n# Generated by tools/layout.rs; see docs/layout.md for voltage assumptions.\n".to_string();
        for (name, _, rank) in &hv {
            s += &format!("(rule \"{name} to LV\" (condition \"A.NetName == '{name}' && ({names})\") (constraint clearance (min {}mm)) (constraint creepage (min {}mm)))\n", rank * 2, rank * 4);
        }
        for i in 0..hv.len() {
            for j in i + 1..hv.len() {
                let (a, la, ra) = &hv[i];
                let (b, lb, rb) = &hv[j];
                let delta = if la == lb {
                    (*ra as i32 - *rb as i32).unsigned_abs()
                } else {
                    (*ra).max(*rb) as u32
                };
                s += &format!("(rule \"{a} to {b}\" (condition \"A.NetName == '{a}' && B.NetName == '{b}'\") (constraint clearance (min {}mm)) (constraint creepage (min {}mm)))\n", delta * 2, delta * 4);
            }
        }
        s += "# Only the selected VSSOP package's adjacent pads require 0.15 mm.\n(rule \"U6 VSSOP pads\" (condition \"A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('U6') && B.memberOfFootprint('U6')\") (constraint clearance (min 0.15mm)))\n";
        fs::write("cad/differential-probe.kicad_dru", s)?;
        Ok(())
    }
}

/// Low-voltage placement: (reference, x, y, angle).
///
/// Bands: the analog chain runs along the slot axis from the buffers (U1) to
/// the BNC; the range-select x5 stage and the warning latch sit above it; the
/// warning comparators, threshold ladders and supplies sit below it. The
/// panel strip x > 126 holds the PCB-mount BNC and toggles.
fn lv_parts() -> Vec<(&'static str, f64, f64, i32)> {
    vec![
        // Dual input buffer on the slot axis between the two tap cells.
        ("U1", 76.0, 35.0, 270),
        ("C81", 80.60, 37.600, 0),
        ("C82", 72.2, 33.4, 90),
        // U3: channel 2 = x2 subtractor (left column), channel 1 = coax driver.
        ("U3", 89.0, 35.0, 180),
        ("R61", 83.77, 30.0, 0),
        ("R62", 82.5, 40.0, 0),
        ("R63", 86.9, 28.6, 0),
        ("R65", 84.4, 35.0, 270),
        ("C83", 88.0, 39.0, 0),
        ("C84", 90.6, 30.6, 0),
        // Shared output pole, series resistor and output clamp toward the BNC.
        ("R69", 95.2, 34.365, 180),
        ("C61", 93.90, 31.000, 90),
        ("R70", 95.2, 36.905, 0),
        ("D3", 132.0, 40.0, 0),
        // Range select: x5 stage and selection resistors.
        ("U12", 88.0, 16.0, 0),
        ("R100", 82.0, 16.635, 0),
        ("R67", 82.0, 13.5, 180),
        ("R68", 88.0, 12.0, 0),
        ("C85", 91.5, 21.0, 0),
        ("C86", 85.5, 20.5, 0),
        ("R101", 80.0, 20.5, 180),
        ("R102", 96.0, 16.635, 0),
        ("R103", 128.5, 24.0, 90),
        // Warning latch, reset and indicator.
        ("U7", 106.0, 19.0, 180),
        ("C91", 100.6, 23.6, 90),
        ("C92", 106.0, 13.0, 0),
        ("Q1", 112.4, 16.46, 180),
        ("R73", 117.21, 14.400, 270),
        ("R74", 116.30, 17.410, 180),
        ("R75", 110.6, 12.6, 90),
        ("R96", 111.5, 24.0, 0),
        ("D9", 115.0, 24.0, 180),
        ("R95", 113.0, 20.7, 270),
        ("C95", 116.5, 20.9, 90),
        ("D8", 119.0, 21.2, 270),
        // Warning comparators, threshold ladders and the selected-output divider.
        ("U5", 80.0, 52.0, 0),
        ("C87", 74.5, 49.5, 90),
        ("C88", 86.0, 49.0, 90),
        ("R87", 77.50, 57.500, 0),
        ("R88", 81.0, 57.500, 0),
        ("R89", 84.50, 57.500, 0),
        ("R91", 74.4, 60.0, 0),
        ("R92", 77.8, 60.0, 0),
        ("R93", 81.2, 60.0, 0),
        ("U6", 93.0, 52.0, 0),
        ("C89", 97.5, 49.0, 0),
        ("C90", 92.5, 56.0, 0),
        ("R71", 98.8, 53.2, 180),
        ("R72", 97.89, 56.0, 270),
        // Supplies: switch-side reverse protection, LDOs, bulk and clamp diodes.
        ("D4", 118.50, 45.500, 0),
        ("U8", 112.0, 46.000, 180),
        ("C71", 116.50, 41.700, 0),
        ("C72", 107.0, 47.000, 90),
        ("R81", 107.50, 43.500, 0),
        ("R82", 108.41, 40.500, 90),
        ("D6", 103.50, 45.000, 90),
        ("D5", 119.50, 62.500, 180),
        ("U9", 112.0, 57.000, 180),
        ("C73", 117.0, 56.500, 0),
        ("C74", 107.0, 58.500, 90),
        ("R83", 107.50, 54.500, 0),
        ("R84", 108.41, 51.500, 90),
        ("D7", 103.50, 57.500, 90),
        // Board-edge, panel-mounted through-hole parts. Panel faces point +x.
        ("J3", 142.4, 35.0, 270),
        ("SW1", 135.3, 14.0, 270),
        ("SW2", 135.3, 56.0, 270),
        // Through-hole latch reset, owner-soldered: in the panel strip between
        // J3 and SW2, because its tails must stay off the bottom-side holders
        // (x 71.3..126.6). Pressed through a lid hole like the trimmers.
        ("SW3", 131.85, 46.25, 180),
    ]
}
/// Bottom-side 9 V holders under the low-voltage section, clear of every
/// top-side through-hole tail (tap cells x < 71, panel parts x > 126). A
/// bottom flip mirrors the holder, so BT1 (contacts toward the tap cell) and
/// BT2 (contacts toward the panel) both keep their two-screw edge outboard.
fn bottom_parts() -> Vec<(&'static str, f64, f64, i32)> {
    vec![("BT1", 73.9, 25.6, 180), ("BT2", 124.0, 44.4, 0)]
}
fn mounting_holes() -> Vec<(usize, f64, f64, &'static str)> {
    vec![
        (1, 145.5, 4.5, "MountingHole:MountingHole_3.2mm_M3_Pad_Via"),
        (2, 145.5, HEIGHT - 4.5, "MountingHole:MountingHole_3.2mm_M3_Pad_Via"),
        (3, 5.0, 5.0, "MountingHole:MountingHole_3.2mm_M3"),
        (4, 5.0, HEIGHT - 5.0, "MountingHole:MountingHole_3.2mm_M3"),
    ]
}
fn label_offset(r: &str) -> Option<(f64, f64)> {
    match r {
        "H3" | "H4" | "H1" | "H2" => Some((0., 0.)),
        _ => None,
    }
}
/// Pour-free rectangles around amplifier inputs, all copper layers.
fn amplifier_input_voids() -> Vec<(f64, f64, f64, f64)> {
    vec![]
}
fn silk_text() -> Vec<(f64, f64, f64, &'static str)> {
    vec![
        (33., 2.2, 0.9, "TEMPER | DIFFERENTIAL PROBE | REV C ENGINEERING PROTOTYPE"),
        (33., 67.8, 0.9, "HV: NO PLANES BELOW | METAL 20 mm FROM HV | NOT CAT RATED"),
        (TIP_X, rows(0).0 - 5., 1., "TIP +"),
        (TIP_X, rows(1).0 + 5., 1., "TIP -"),
    ]
}
impl Copper {
    /// Power pin to a plane via (In1 GND, In2 +4V8, B.Cu -4V8), net from the pad.
    fn rail(&mut self, key: &str, v: (f64, f64)) {
        let net = self.net(key);
        let p = self.p(key);
        self.path(&net, "F.Cu", 0.3, &[p, v]);
        self.via(&net, v);
    }
    /// Track on `layer` between explicit points (pads are referenced by key).
    fn run(&mut self, net: &str, layer: &str, pts: &[(f64, f64)]) {
        self.path(net, layer, 0.25, pts);
    }
    /// Inner/bottom-layer run with vias at both ends.
    fn hop(&mut self, net: &str, layer: &str, pts: &[(f64, f64)]) {
        self.via(net, pts[0]);
        self.path(net, layer, 0.25, pts);
        self.via(net, *pts.last().unwrap());
    }
    fn signals(&mut self) {
        let k = |c: &Copper, key: &str| c.p(key);
        // ---- Slot-axis analog chain ------------------------------------------------
        // Tap-to-buffer inputs: equal length (the N side jogs to absorb U1's 1.27 mm
        // pin offset), F.Cu only.
        let (u13, u15) = (k(self, "U1.3"), k(self, "U1.5"));
        self.run("IN_P", "F.Cu", &[(68.0, 29.5), (u13.0, 29.5), u13]);
        self.run("IN_N", "F.Cu", &[(68.0, 40.5), (71.5, 40.5), (71.5, 41.135), (u15.0, 41.135), u15]);
        // Buffer outputs to the subtractor resistors: mirrored, equal length.
        let (u11, u12, u16, u17) = (k(self, "U1.1"), k(self, "U1.2"), k(self, "U1.6"), k(self, "U1.7"));
        let (r61, r62) = (k(self, "R61.1"), k(self, "R62.1"));
        self.run("BUF_P", "F.Cu", &[u11, (u11.0, r61.1), r61]);
        self.run("BUF_N", "F.Cu", &[u17, (u17.0, r62.1), r62]);
        self.run("BUF_P", "F.Cu", &[u11, u12]);
        self.run("BUF_N", "F.Cu", &[u16, u17]);
        // Comparator taps leave from the feedback pins: BUF_P on In2, BUF_N on B.Cu.
        self.run("BUF_P", "F.Cu", &[u12, (u12.0, 30.8)]);
        self.hop("BUF_P", "In2.Cu", &[(u12.0, 30.8), (u12.0, 46.0), (75.6, 47.0), (75.6, 54.8)]);
        self.run("BUF_N", "F.Cu", &[u16, (u16.0, 39.2)]);
        self.hop("BUF_N", "B.Cu", &[(u16.0, 39.2), (79.5, 43.3), (88.4, 43.3), (88.4, 54.8), (84.4, 54.8)]);
        self.rail("U1.4", k(self, "C82.2"));
        self.rail("C82.2", (72.2, 31.0));
        self.rail("C82.1", (70.9, 34.35));
        self.rail("U1.8", k(self, "C81.1"));
        self.rail("C81.1", (79.65, 36.2));
        self.rail("C81.2", (81.55, 36.3));
        // x2 subtractor (U3 channel 2).
        let (r612, u35, r631) = (k(self, "R61.2"), k(self, "U3.5"), k(self, "R63.1"));
        self.run("SUM_P", "F.Cu", &[r612, (85.6, r612.1), (85.6, u35.1), u35]);
        self.run("SUM_P", "F.Cu", &[r631, (85.6, r631.1), (85.6, r612.1)]);
        self.rail("R63.2", (88.9, 28.6));
        self.rail("C84.1", (88.9, 28.6));
        let (r651, u36, r622) = (k(self, "R65.1"), k(self, "U3.6"), k(self, "R62.2"));
        self.run("SUM_N", "F.Cu", &[r651, (85.3, u36.1), u36]);
        self.run("SUM_N", "F.Cu", &[r622, (r622.0, r651.1), r651]);
        let (u37, r652) = (k(self, "U3.7"), k(self, "R65.2"));
        self.run("RAW_OUT", "F.Cu", &[u37, r652, (r652.0, 37.2)]);
        self.hop("RAW_OUT", "In2.Cu", &[(r652.0, 37.2), (83.0, 35.8), (83.0, 22.6), (81.0, 20.6), (81.0, 18.6)]);
        let (r1001, r1011) = (k(self, "R100.1"), k(self, "R101.1"));
        self.run("RAW_OUT", "F.Cu", &[r1001, (81.0, 18.6), r1011]);
        self.rail("U3.8", (86.525, 38.1));
        self.rail("C83.1", (86.525, 38.1));
        self.rail("C83.2", (88.95, 40.3));
        self.rail("U3.4", k(self, "C84.2"));
        self.rail("C84.2", (91.55, 29.2));
        // Shared output pole and coax driver (U3 channel 1).
        let (u33, r692, c611) = (k(self, "U3.3"), k(self, "R69.2"), k(self, "C61.1"));
        self.run("FILTER", "F.Cu", &[u33, r692]);
        self.run("FILTER", "F.Cu", &[c611, (c611.0, u33.1)]);
        self.rail("C61.2", (93.9, 28.9));
        let (u31, u32, r701) = (k(self, "U3.1"), k(self, "U3.2"), k(self, "R70.1"));
        self.run("DRIVE", "F.Cu", &[u32, u31, r701]);
        let (r702, j31, d33) = (k(self, "R70.2"), k(self, "J3.1"), k(self, "D3.3"));
        self.run("OUT", "F.Cu", &[r702, (138.5, r702.1), (140.4, j31.1), j31]);
        self.run("OUT", "F.Cu", &[(d33.0, r702.1), d33]);
        self.rail("D3.1", (129.8, 39.05));
        self.rail("D3.2", (129.8, 40.95));
        // Input clamps (the leg cells are mirror images; rails are not checked for symmetry).
        self.rail("D1.1", (68.95, 25.6));
        self.rail("D1.2", (67.05, 25.6));
        self.rail("D2.1", (67.05, 44.4));
        self.rail("D2.2", (68.95, 44.4));
        // ---- Range select and x5 stage ---------------------------------------------
        let (r1002, u123) = (k(self, "R100.2"), k(self, "U12.3"));
        self.run("GAIN5_IN", "F.Cu", &[r1002, u123]);
        let (u122, r671, r681) = (k(self, "U12.2"), k(self, "R67.1"), k(self, "R68.1"));
        self.run("GAIN5_FB", "F.Cu", &[u122, (84.0, u122.1), (84.0, r681.1), r681]);
        self.run("GAIN5_FB", "F.Cu", &[r671, (84.0, r671.1)]);
        let (u126, r1021, r682) = (k(self, "U12.6"), k(self, "R102.1"), k(self, "R68.2"));
        self.run("FINE_OUT", "F.Cu", &[u126, r1021]);
        self.run("FINE_OUT", "F.Cu", &[(93.5, u126.1), (93.5, r682.1), r682]);
        self.rail("U12.7", (92.3, 15.365));
        self.rail("U12.4", (86.45, 18.9));
        self.run("-4V8", "F.Cu", &[(86.45, 18.9), k(self, "C86.2")]);
        self.rail("C86.2", (87.6, 20.5));
        self.rail("C86.1", (84.55, 21.9));
        self.rail("C85.1", (90.55, 22.3));
        self.rail("C85.2", (92.45, 22.3));
        self.rail("R67.2", (80.0, 13.5));
        // Selected-range wiring to the PCB toggle: WIDE on the outer edge track.
        let (r1012, sw11) = (k(self, "R101.2"), k(self, "SW1.1"));
        self.run("WIDE_SEL", "F.Cu", &[r1012, (78.5, r1012.1), (78.5, 3.0), (sw11.0, 3.0), sw11]);
        let (r1022, sw13) = (k(self, "R102.2"), k(self, "SW1.3"));
        self.run("FINE_SEL", "F.Cu", &[r1022, (97.8, r1022.1), (97.8, 5.0), (sw13.0, 5.0), sw13]);
        let (sw12, r691, r1031) = (k(self, "SW1.2"), k(self, "R69.1"), k(self, "R103.1"));
        self.run("SELECTED", "F.Cu", &[sw12, (sw12.0, 33.0), (97.6, 33.0), r691]);
        self.run("SELECTED", "F.Cu", &[r1031, (r1031.0, 26.0), (sw12.0, 26.0)]);
        self.rail("R103.2", (128.5, 21.9));
        let r711 = k(self, "R71.1");
        self.hop("SELECTED", "B.Cu", &[(100.5, 33.0), (100.5, 51.4)]);
        self.run("SELECTED", "F.Cu", &[(100.5, 51.4), r711]);
        // ---- Warning latch ------------------------------------------------------------
        let (u76, q13, r751) = (k(self, "U7.6"), k(self, "Q1.3"), k(self, "R75.1"));
        self.run("SET", "F.Cu", &[u76, q13]);
        self.run("SET", "F.Cu", &[r751, (r751.0, u76.1)]);
        self.rail("R75.2", (110.6, 10.4));
        self.rail("Q1.2", (114.7, 15.2));
        self.run("Q_BASE", "F.Cu", &[k(self, "Q1.1"), k(self, "R74.2")]);
        let (r741, r732) = (k(self, "R74.1"), k(self, "R73.2"));
        self.run("OV_N", "F.Cu", &[r732, r741, (118.8, r741.1)]);
        self.rail("R73.1", (117.21, 12.2));
        // RESET to the THT button in the panel strip: F.Cu to a via, In2 hop
        // around BT2's GND pin straight onto the THT pad, F.Cu across the row
        // to the second (internally common) pin 2. Pin 1 (+4V8) joins the In2 pour.
        let u74 = k(self, "U7.4");
        let (sw3a, sw3b) = sw3_row(self, "SW3.2");
        self.run("RESET", "F.Cu", &[u74, (123.98, u74.1), (123.98, 26.25)]);
        self.via("RESET", (123.98, 26.25));
        self.run("RESET", "In2.Cu", &[(123.98, 26.25), (123.98, 41.5), (sw3a.0 - 2.1, sw3a.1), sw3a]);
        self.run("RESET", "F.Cu", &[sw3a, sw3b]);
        for key in ["R95.1", "C95.2", "D8.1"] {
            let p = k(self, key);
            self.run("RESET", "F.Cu", &[p, (p.0, u74.1)]);
        }
        self.rail("R95.2", (114.0, 22.3));
        self.rail("C95.1", (117.6, 22.9));
        self.rail("D8.2", (120.3, 22.85));
        let (u71, r961) = (k(self, "U7.1"), k(self, "R96.1"));
        self.run("OV_LED", "F.Cu", &[u71, (109.8, u71.1), (r961.0, 23.6), r961]);
        self.run("LED_A", "F.Cu", &[k(self, "R96.2"), k(self, "D9.2")]);
        self.rail("D9.1", (117.3, 24.6));
        for (key, v) in [
            ("U7.8", (101.6, 15.19)),
            ("U7.9", (101.6, 16.46)),
            ("U7.10", (100.5, 17.73)),
            ("U7.11", (101.6, 19.0)),
            ("U7.5", (110.3, 17.73)),
            ("U7.3", (110.3, 20.27)),
        ] {
            self.rail(key, v);
        }
        let (u714, c911) = (k(self, "U7.14"), k(self, "C91.1"));
        self.run("+4V8", "F.Cu", &[u714, (102.0, c911.1), c911]);
        self.rail("C91.1", (100.6, 25.8));
        self.rail("C91.2", (99.3, 22.65));
        self.rail("U7.7", k(self, "C92.2"));
        self.rail("C92.2", (106.95, 11.8));
        self.rail("C92.1", (105.05, 11.8));
        // ---- Warning comparators ------------------------------------------------------
        // U5: LIM_P and LIM_N cross under the body; BUF_P/BUF_N loop around the outside.
        let (u55, u59) = (k(self, "U5.5"), k(self, "U5.9"));
        self.run("LIM_P", "F.Cu", &[u55, (78.3, u55.1), (81.7, u59.1), u59]);
        let (u56, u510) = (k(self, "U5.6"), k(self, "U5.10"));
        self.run("LIM_N", "F.Cu", &[u56, (78.3, u56.1), (78.9, 54.1)]);
        self.run("LIM_N", "F.Cu", &[u510, (81.7, u510.1), (81.1, 51.9)]);
        self.hop("LIM_N", "B.Cu", &[(78.9, 54.1), (80.9, 54.1), (81.1, 51.9)]);
        self.hop("LIM_N", "B.Cu", &[(78.9, 54.1), (77.6, 55.4), (77.6, 58.9), (76.1, 59.0)]);
        self.run("LIM_N", "F.Cu", &[(76.1, 59.0), (76.1, 60.0)]);
        self.link("R91.2", "R92.1", "F.Cu", &[]);
        self.hop("LIM_P", "In2.Cu", &[(80.0, 52.975), (79.25, 55.9)]);
        self.run("LIM_P", "F.Cu", &[(79.25, 55.9), (79.25, 57.5)]);
        self.link("R87.2", "R88.1", "F.Cu", &[]);
        let (u52, u513, u51, u514) = (k(self, "U5.2"), k(self, "U5.13"), k(self, "U5.1"), k(self, "U5.14"));
        self.run("OV_N", "F.Cu", &[u51, u52, u513, u514, (83.8, 49.2)]);
        let (u54, u57) = (k(self, "U5.4"), k(self, "U5.7"));
        self.run("BUF_P", "F.Cu", &[u54, (75.6, u54.1), (75.6, 54.8)]);
        self.run("BUF_P", "F.Cu", &[u57, (75.6, u57.1)]);
        let (u511, u58) = (k(self, "U5.11"), k(self, "U5.8"));
        self.run("BUF_N", "F.Cu", &[u511, (84.4, u511.1), (84.4, 54.8)]);
        self.run("BUF_N", "F.Cu", &[u58, (84.4, u58.1)]);
        let (u53, c871) = (k(self, "U5.3"), k(self, "C87.1"));
        self.run("+4V8", "F.Cu", &[u53, (75.6, u53.1), c871]);
        self.rail("C87.1", (73.3, 50.45));
        self.rail("C87.2", (73.3, 48.55));
        self.rail("U5.12", (85.4, 51.35));
        self.rail("C88.2", (87.2, 48.05));
        self.rail("C88.1", (87.2, 49.95));
        // Threshold ladders.
        self.rail("R87.1", (75.4, 57.5));
        self.rail("R89.2", (86.6, 57.5));
        self.rail("R91.1", (72.3, 60.0));
        self.rail("R93.2", (83.3, 60.0));
        let (r882, r891, u63) = (k(self, "R88.2"), k(self, "R89.1"), k(self, "U6.3"));
        self.run("OUT_LIM_P", "F.Cu", &[r882, r891]);
        self.run("OUT_LIM_P", "F.Cu", &[(82.75, 57.5), (82.75, 56.3), (87.3, 56.3), (88.5, 55.1), (88.5, u63.1), u63]);
        self.run("OUT_LIM_N", "F.Cu", &[(79.5, 60.0), (79.5, 61.6)]);
        self.link("R92.2", "R93.1", "F.Cu", &[]);
        let u66 = k(self, "U6.6");
        self.hop("OUT_LIM_N", "In2.Cu", &[(79.5, 61.6), (81.7, 63.8), (95.8, 63.8), (95.8, 56.5), (96.6, 55.7), (96.6, u66.1)]);
        self.run("OUT_LIM_N", "F.Cu", &[u66, (96.6, u66.1)]);
        // U6: OV_N and OUT_HALF cross under the body.
        let (u61, u67, u62, u65) = (k(self, "U6.1"), k(self, "U6.7"), k(self, "U6.2"), k(self, "U6.5"));
        self.run("OV_N", "F.Cu", &[u61, (91.9, u61.1), (94.1, u67.1), u67]);
        self.run("OUT_HALF", "F.Cu", &[u62, (91.9, u62.1), (94.1, u65.1), u65]);
        self.run("OV_N", "F.Cu", &[u61, (90.0, u61.1), (89.4, 50.4)]);
        self.hop("OV_N", "In2.Cu", &[(83.8, 49.2), (88.2, 49.2), (89.4, 50.4)]);
        self.hop("OV_N", "In2.Cu", &[(89.4, 50.4), (89.4, 44.5), (101.8, 44.5), (101.8, 26.0), (118.8, 26.0), (118.8, 17.41)]);
        let (r712, r721) = (k(self, "R71.2"), k(self, "R72.1"));
        self.run("OUT_HALF", "F.Cu", &[u65, r712, r721]);
        self.rail("R72.2", (99.2, 57.5));
        let (u64, c902) = (k(self, "U6.4"), k(self, "C90.2"));
        self.run("-4V8", "F.Cu", &[u64, (91.9, 53.9), (c902.0 - 0.6, c902.1 - 0.6), c902]);
        self.rail("C90.2", (94.6, 56.0));
        self.rail("C90.1", (91.55, 57.3));
        let (u68, c891) = (k(self, "U6.8"), k(self, "C89.1"));
        self.run("+4V8", "F.Cu", &[u68, (96.0, 50.1), c891]);
        self.rail("C89.1", (96.55, 47.7));
        self.rail("C89.2", (98.45, 47.7));
        // ---- Supplies -----------------------------------------------------------------
        let (bt11, sw22) = (k(self, "BT1.1"), k(self, "SW2.2"));
        self.run("BAT_P", "B.Cu", &[bt11, (bt11.0, 27.0), (126.0, 27.0), (126.0, 50.0)]);
        self.via("BAT_P", (126.0, 50.0));
        self.run("BAT_P", "F.Cu", &[(126.0, 50.0), (sw22.0, 50.0), sw22]);
        // SW_P passes under the SW3 pads and the SW2 rows on B.Cu (y = 50.9).
        let (sw21, d42) = (k(self, "SW2.1"), k(self, "D4.2"));
        self.run("SW_P", "B.Cu", &[sw21, (sw21.0, 50.9), (121.5, 50.9)]);
        self.via("SW_P", (121.5, 50.9));
        self.run("SW_P", "F.Cu", &[(121.5, 50.9), (121.5, 47.0), d42]);
        let (sw24, d51) = (k(self, "SW2.4"), k(self, "D5.1"));
        self.run("SW_N", "F.Cu", &[sw24, (sw24.0, 64.5), (d51.0, 64.5), d51]);
        let (bt22, sw25) = (k(self, "BT2.2"), k(self, "SW2.5"));
        self.run("BAT_N", "F.Cu", &[bt22, (bt22.0, 60.6), (sw25.0, 60.6), sw25]);
        // Positive LDO.
        let (u81, u83, d41, c711) = (k(self, "U8.1"), k(self, "U8.3"), k(self, "D4.1"), k(self, "C71.1"));
        self.run("+BAT", "F.Cu", &[u81, (114.3, u81.1), (114.3, u83.1), u83]);
        self.run("+BAT", "F.Cu", &[d41, (114.3, d41.1)]);
        self.run("+BAT", "F.Cu", &[c711, (114.3, 42.5), (114.3, u83.1)]);
        self.rail("C71.2", (119.3, 41.7));
        let u82 = k(self, "U8.2");
        self.rail("U8.2", (110.9, u82.1));
        let (u85, c721, d61) = (k(self, "U8.5"), k(self, "C72.1"), k(self, "D6.1"));
        self.run("+4V8", "F.Cu", &[u85, (109.5, c721.1), c721]);
        self.run("+4V8", "F.Cu", &[d61, (105.0, c721.1), c721]);
        self.rail("C72.1", (105.5, 49.3));
        let (u84, r812, r821) = (k(self, "U8.4"), k(self, "R81.2"), k(self, "R82.1"));
        self.run("ADJ_0", "F.Cu", &[u84, r812, r821]);
        self.rail("R81.1", (105.3, 43.5));
        self.rail("R82.2", (108.41, 38.3));
        self.rail("C72.2", (109.0, 46.3));
        self.rail("D6.2", (104.9, 41.2));
        // Negative LDO.
        let (u92, u93, d52, c731) = (k(self, "U9.2"), k(self, "U9.3"), k(self, "D5.2"), k(self, "C73.1"));
        self.run("-BAT", "F.Cu", &[u93, u92, (114.5, u92.1), (114.5, 59.5), d52]);
        self.run("-BAT", "F.Cu", &[c731, (114.5, c731.1), (114.5, u92.1)]);
        self.rail("C73.2", (119.8, 56.5));
        let u91 = k(self, "U9.1");
        self.run("GND", "F.Cu", &[u91, (112.0, u91.1), (112.0, u92.1), (110.9, u92.1)]);
        self.via("GND", (110.9, u92.1));
        let (u95, c741) = (k(self, "U9.5"), k(self, "C74.1"));
        self.run("-4V8", "F.Cu", &[u95, (109.0, c741.1), c741]);
        let (u94, r832, r841) = (k(self, "U9.4"), k(self, "R83.2"), k(self, "R84.1"));
        self.run("ADJ_1", "F.Cu", &[u94, r832, r841]);
        self.rail("R83.1", (105.3, 54.5));
        self.rail("R84.2", (109.6, 50.587));
        self.rail("C74.1", (105.3, 60.6));
        self.rail("C74.2", (105.3, 56.5));
        self.rail("D7.1", (101.9, 59.5));
        self.rail("D7.2", (101.9, 55.5));
    }
}


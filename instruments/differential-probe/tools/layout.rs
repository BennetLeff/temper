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
const FIRST: f64 = 34.;
const TIP_X: f64 = 24.;
/// Long inter-leg routed slot, 1.6 mm nominal (>= 1.4 mm finished at JLC +/-0.2 mm).
const SLOT: (f64, f64, f64) = (12., 53., 1.6);
/// Inner/bottom pours and hidden-layer routing are allowed only for x >= PLANE_X.
const PLANE_X: f64 = 76.;

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
        let below = y > AXIS;
        let mut xy = (x, if below { y + 2.6 } else { y - 2.6 });
        if let Some((dx, dy)) = label_offset(r) {
            xy = (x + dx, y + dy);
        }
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
        // Long inter-leg slot on the axis.
        let (x1, x2, wdt) = SLOT;
        self.rect("Edge.Cuts", x1, AXIS - wdt / 2., x2, AXIS + wdt / 2.);
        // Low-leg cells, authored for leg P and mirrored for leg N.
        let tap_x = node_x(5);
        let bus = 76.5;
        let cell: Vec<(&str, Vec<(f64, f64)>)> = vec![
            // TAP bus from the ladder node to the bank, trimmer, DC trim and R12.
            ("TAP", vec![(tap_x, rows(0).0), (bus, rows(0).0)]),
            ("TAP", vec![(bus, 7.0), (bus, 29.5)]),
            ("TAP", vec![(bus, 7.0), (77.175, 7.0)]),
            ("TAP", vec![(bus, 11.0), (76.525, 11.0)]),
            ("TAP", vec![(bus, 29.5), (79.0875, 29.5)]),
            // DC trim: R11 to RV1 pin 1; RV1 pins 2-3 tied (wiper to end).
            ("TRIM", vec![(78.825, 7.0), (82.0, 7.0)]),
            ("GND", vec![(84.54, 7.0), (87.08, 7.0)]),
            // R12 to the clamp junction; the buffer input route is per-leg below.
            ("IN", vec![(80.9125, 29.5), (85.0, 29.5)]),
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
                ("C41.2", (80.6, 11.0)),
                ("C42.2", (79.6, 14.5)),
                ("C43.2", (79.6, 17.5)),
                ("CT1.2", (83.5, 23.0)),
                ("RV1.3", (87.08, 9.6)),
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
        let pts = [
            (c, 0.),
            (LENGTH - c, 0.),
            (LENGTH, c),
            (LENGTH, HEIGHT - c),
            (LENGTH - c, HEIGHT),
            (c, HEIGHT),
            (0., HEIGHT - c),
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

/// Low-voltage placement: (reference, x, y, angle). Board-edge parts last.
fn lv_parts() -> Vec<(&'static str, f64, f64, i32)> {
    vec![
        // Dual input buffer on the slot axis between the two tap cells.
        ("U1", 92.0, 35.0, 270),
        ("C82", 87.4, 32.6, 0),
        ("C81", 95.0, 41.4, 0),
        // U3: channel 2 = x2 subtractor (left column), channel 1 = coax driver.
        ("U3", 104.0, 35.0, 180),
        ("R61", 98.0, 32.6, 0),
        ("R62", 97.5, 34.2, 0),
        ("R65", 99.6, 35.0, 270),
        ("R63", 99.9, 30.7, 90),
        ("C83", 101.0, 39.6, 0),
        ("C84", 105.0, 30.4, 0),
        // Shared filter, coax driver output and clamp toward the BNC.
        ("R69", 110.0, 34.4, 180),
        ("C61", 110.0, 31.8, 0),
        ("R70", 110.0, 37.0, 0),
        ("D3", 132.0, 38.0, 0),
        // Fine x5 stage and range-selection feeds.
        ("U12", 118.0, 45.0, 0),
        ("R100", 113.0, 45.6, 0),
        ("R67", 113.4, 42.4, 90),
        ("R68", 118.0, 41.2, 0),
        ("C85", 123.0, 42.0, 90),
        ("C86", 114.0, 49.0, 0),
        ("R101", 126.0, 50.0, 0),
        ("R102", 126.0, 46.0, 0),
        ("R103", 132.0, 58.0, 90),
        // Initial-envelope warning comparators and threshold ladders.
        ("U5", 100.0, 53.0, 0),
        ("C87", 96.0, 48.0, 0),
        ("C88", 104.0, 48.0, 0),
        ("R87", 96.0, 60.0, 90),
        ("R88", 99.0, 60.0, 90),
        ("R89", 102.0, 60.0, 90),
        ("R91", 96.0, 65.0, 90),
        ("R92", 99.0, 65.0, 90),
        ("R93", 102.0, 65.0, 90),
        ("U6", 112.0, 57.0, 0),
        ("C89", 108.0, 61.0, 0),
        ("C90", 116.0, 61.0, 0),
        ("R71", 120.0, 54.0, 90),
        ("R72", 117.0, 54.0, 90),
        // Latch, reset and indicator.
        ("R73", 106.0, 66.0, 0),
        ("R74", 110.0, 66.0, 0),
        ("Q1", 114.0, 66.0, 0),
        ("R75", 118.0, 66.0, 0),
        ("U7", 125.0, 60.0, 0),
        ("C91", 122.0, 66.0, 0),
        ("C92", 129.0, 54.0, 0),
        ("SW3", 133.0, 65.0, 0),
        ("R95", 128.0, 66.5, 0),
        ("C95", 131.0, 52.0, 90),
        ("D8", 134.0, 52.0, 90),
        ("R96", 128.0, 50.0, 0),
        ("D9", 133.0, 47.0, 0),
        // Supplies: switch-side reverse protection, LDOs, bulk capacitors.
        ("D4", 128.0, 8.0, 0),
        ("D5", 128.0, 20.0, 0),
        ("U8", 118.0, 8.0, 0),
        ("U9", 118.0, 20.0, 0),
        ("C71", 123.0, 12.0, 0),
        ("C72", 112.0, 8.0, 90),
        ("C73", 123.0, 16.0, 0),
        ("C74", 112.0, 20.0, 90),
        ("R81", 114.0, 4.0, 0),
        ("R82", 118.0, 4.0, 0),
        ("R83", 114.0, 24.0, 0),
        ("R84", 118.0, 24.0, 0),
        ("D6", 104.0, 8.0, 90),
        ("D7", 104.0, 20.0, 90),
        // Board-edge, panel-mounted through-hole parts (owner hand-solders).
        ("J3", 142.0, 35.0, 270),
        ("SW1", 141.0, 55.0, 0),
        ("SW2", 141.0, 15.0, 0),
    ]
}
fn bottom_parts() -> Vec<(&'static str, f64, f64, i32)> {
    vec![("BT1", 100.0, 8.0, 270), ("BT2", 133.0, 8.0, 270)]
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
        (40., 3.5, 1., "TEMPER | DIFFERENTIAL PROBE | REV C ENGINEERING PROTOTYPE"),
        (40., 66.5, 1., "HV: NO PLANES BELOW | SHIELD 20 mm FROM HV | NOT CAT RATED"),
        (TIP_X, rows(0).0 - 5., 1., "TIP +"),
        (TIP_X, rows(1).0 + 5., 1., "TIP -"),
    ]
}
impl Copper {
    fn signals(&mut self) {}
}

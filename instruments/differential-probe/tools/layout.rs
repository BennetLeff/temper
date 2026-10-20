//! Explicit probe placement and hand-authored routing. KiCad owns pad transforms.
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fs,
};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
const HEIGHT: f64 = 84.;
const ROWS: [f64; 2] = [20., 55.];
fn landing(name: &str, pads: &[(u8, f64, f64)], diam: f64, drill: f64) -> Result<()> {
    let mut s=format!("(footprint \"{name}\" (version 20241229) (generator \"temper_probe\") (layer \"F.Cu\") (attr through_hole board_only exclude_from_pos_files exclude_from_bom) (property \"Reference\" \"W\" (at 0 -4) (layer \"F.SilkS\") (effects (font (size .8 .8) (thickness .12)))) (property \"Value\" \"wire landing\" (at 0 4) (layer \"F.Fab\") (effects (font (size .8 .8) (thickness .12))))");
    for &(n, x, y) in pads {
        s+=&format!("(pad \"{n}\" thru_hole circle (at {x} {y}) (size {diam} {diam}) (drill {drill}) (layers \"*.Cu\" \"*.Mask\"))");
    }
    s += ")\n";
    fs::write(format!("cad/Probe.pretty/{name}.kicad_mod"), s)?;
    Ok(())
}
fn placement() -> Result<()> {
    landing("HV_Captive_Lead", &[(1, 0., 0.)], 4., 1.6)?;
    landing("Wire_Pair", &[(1, -2.5, 0.), (2, 2.5, 0.)], 2.6, 1.2)?;
    landing(
        "Range_Wire_Pads",
        &[(1, 0., -4.), (2, 0., 0.), (3, 0., 4.)],
        1.8,
        0.9,
    )?;
    landing(
        "Power_Wire_Pads",
        &[(1, 0., -3.), (2, 0., 0.), (4, 4., -3.), (5, 4., 0.)],
        2.4,
        1.2,
    )?;
    let mut s = "reference\tx\ty\tangle\tfootprint_override\n".to_string();
    let mut seen = BTreeSet::new();
    let mut put = |r: String, x: f64, y: f64, a: i32, fp: &str| {
        assert!(seen.insert(r.clone()), "duplicate {r}");
        s += &format!("{r}\t{x:.4}\t{y:.4}\t{a}\t{fp}\n");
    };
    for (j, y) in ROWS.into_iter().enumerate() {
        let base = j * 20;
        for i in 0..5 {
            let x = 30. + 18. * i as f64;
            put(format!("R{}", base + i * 2 + 1), x + 4.5, y, 0, "");
            put(format!("R{}", base + i * 2 + 2), x + 13.5, y, 0, "");
            put(format!("C{}", base + i + 1), x + 9., y + 8., 0, "");
        }
        put(format!("W_HV{}", j + 1), 20., y, 0, "Probe:HV_Captive_Lead");
        put(format!("U{}", j + 1), 141., y, 0, "");
        put(format!("R{}", base + 12), 135., y + 0.635, 0, "");
        put(format!("D{}", j + 1), 135., y + 5., 0, "");
        put(format!("R{}", base + 11), 124., y + 12., 270, "");
        put(format!("RV{}", j + 1), 126., y + 18., 0, "");
        for i in 0..7 {
            put(
                format!("C{}", 41 + j * 10 + i),
                130.,
                y - 10. + 3. * i as f64,
                0,
                "",
            );
        }
        put(format!("C{}", 81 + j * 2), 147., y - 4., 270, "");
        put(format!("C{}", 82 + j * 2), 140.5, y + 5.5, 90, "");
    }
    // Compact low-voltage cells; coordinates are the final native-board positions.
    for (r, x, y, a) in [
        ("U3", 163.0000, 38.0000, 180),
        ("R61", 173.0000, 36.8000, 180),
        ("R62", 173.0000, 39.2000, 180),
        ("R63", 167.0000, 32.0000, 0),
        ("R64", 171.0000, 32.0000, 0),
        ("R65", 168.5000, 42.0000, 180),
        ("R66", 164.5000, 42.0000, 180),
        ("R67", 180.0000, 22.0000, 270),
        ("R68", 183.0000, 19.0000, 0),
        ("C85", 157.0000, 41.0000, 270),
        ("C86", 161.0000, 33.0000, 90),
        ("U4", 198.0000, 40.0000, 0),
        ("R69", 184.0000, 40.6350, 0),
        ("C61", 190.0000, 43.0000, 270),
        ("R70", 207.0000, 40.6350, 0),
        ("D3", 220.0000, 41.0000, 0),
        ("C87", 204.0000, 38.0000, 270),
        ("C88", 195.0000, 46.0000, 90),
        ("U5", 180.0000, 61.0000, 0),
        ("U6", 195.0000, 61.0000, 0),
        ("U7", 216.0000, 62.0000, 0),
        ("C89", 173.0000, 58.0000, 270),
        ("C90", 188.0000, 57.0000, 90),
        ("C91", 201.0000, 58.0000, 270),
        ("C92", 190.0000, 65.0000, 90),
        ("C93", 222.0000, 57.0000, 270),
        ("C94", 204.5000, 68.0000, 90),
        ("R71", 193.0000, 51.0000, 90),
        ("R72", 196.0000, 51.0000, 270),
        ("R73", 204.0000, 53.0000, 90),
        ("R74", 206.0000, 56.0000, 0),
        ("R75", 207.0000, 65.5000, 90),
        ("Q1", 210.0000, 59.0000, 0),
        ("R95", 226.0000, 61.0000, 90),
        ("C95", 230.0000, 61.0000, 90),
        ("D8", 234.0000, 61.0000, 90),
        ("R96", 220.0000, 48.0000, 0),
        ("D9", 230.0000, 48.0000, 0),
        ("SW3", 227.0000, 70.0000, 0),
        ("U8", 173.0000, 73.0000, 0),
        ("U9", 194.0000, 73.0000, 0),
        ("C71", 167.0000, 71.0000, 0),
        ("C72", 179.0000, 71.0000, 0),
        ("C73", 188.0000, 71.0000, 0),
        ("C74", 200.0000, 71.0000, 0),
        ("R81", 177.0000, 77.0000, 0),
        ("R82", 173.0000, 78.0000, 90),
        ("R83", 198.0000, 77.0000, 0),
        ("R84", 194.0000, 78.0000, 90),
        ("D4", 163.0000, 76.0000, 0),
        ("D5", 184.0000, 76.0000, 0),
        ("D6", 183.0000, 81.0000, 0),
        ("D7", 205.0000, 81.0000, 0),
        ("U10", 157.0000, 15.0000, 0),
        ("U11", 157.0000, 60.0000, 0),
        ("R85", 157.0000, 10.0000, 90),
        ("R86", 157.0000, 66.0000, 90),
        ("R87", 165.0000, 14.0000, 90),
        ("R88", 165.0000, 19.0000, 90),
        ("R89", 170.0000, 11.0000, 90),
        ("R90", 170.0000, 19.0000, 90),
        ("R91", 165.0000, 56.0000, 90),
        ("R92", 165.0000, 61.0000, 90),
        ("R93", 170.0000, 53.0000, 90),
        ("R94", 170.0000, 61.0000, 90),
        ("CT1", 138.0000, 38.0000, 0),
        ("CT2", 138.0000, 73.0000, 0),
        ("U12", 188.0000, 25.0000, 0),
        ("R97", 187.0000, 19.0000, 0),
        ("R98", 191.0000, 19.0000, 0),
        ("R99", 195.0000, 19.0000, 0),
        ("R100", 154.0000, 34.0000, 180),
        ("R101", 154.0000, 45.0000, 180),
        ("R102", 198.0000, 28.0000, 0),
        ("R103", 215.0000, 28.0000, 0),
        ("C96", 194.0000, 22.0000, 270),
        ("C97", 187.0000, 31.5000, 90),
    ] {
        put(r.into(), x, y, a, "");
    }
    for (r, x, y, fp) in [
        ("W_SW1", 210., 28., "Range_Wire_Pads"),
        ("W_SW2", 210., 74., "Power_Wire_Pads"),
        ("W_BT1", 226., 78., "Wire_Pair"),
        ("W_BT2", 215., 80., "Wire_Pair"),
        ("W_J3", 234., 40., "Wire_Pair"),
    ] {
        put(r.into(), x, y, 0, &format!("Probe:{fp}"));
    }
    for (i, x, y) in [(1, 135., 6.), (2, 234., 6.), (3, 147., 78.), (4, 234., 78.)] {
        put(
            format!("H{i}"),
            x,
            y,
            0,
            "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
        );
    }
    for (i, y) in [(5, 7.), (6, 77.)] {
        put(
            format!("H{i}"),
            7.,
            y,
            0,
            "MountingHole:MountingHole_3.2mm_M3",
        );
    }
    fs::write("layout/placement.tsv", s)?;
    let mut land = "reference\tpin\tnet\nW_HV1\t1\tTIP_P\nW_HV2\t1\tTIP_N\n".to_string();
    for line in fs::read_to_string("validation/expected-pins.tsv")?
        .lines()
        .skip(1)
    {
        let a: Vec<_> = line.split('\t').collect();
        if ["BT1", "BT2", "SW1", "SW2", "J3"].contains(&a[0]) && a[2] != "NC" {
            land += &format!("W_{}\t{}\t{}\n", a[0], a[1], a[2]);
        }
    }
    for i in 1..=4 {
        land += &format!("H{i}\t1\tGND\n");
    }
    fs::write("layout/landings.tsv", land)?;
    let mut labels = "reference\tx\ty\n".to_string();
    for line in fs::read_to_string("layout/placement.tsv")?.lines().skip(1) {
        let a: Vec<_> = line.split('\t').collect();
        let r = a[0];
        let x: f64 = a[1].parse()?;
        let y: f64 = a[2].parse()?;
        let mut xy = (x, y - 3.1);
        if let Some(n) = r.strip_prefix('C').and_then(|n| n.parse::<usize>().ok()) {
            if (1..=5).contains(&n) || (21..=25).contains(&n) {
                xy = (x, y + 5.5);
            }
            if (41..=47).contains(&n) || (51..=57).contains(&n) {
                xy = (x - 7., y);
            }
        }
        xy = match r {
            "C82" | "C84" => (x + 4., y + 1.),
            "D1" | "D2" => (x, y + 3.5),
            "C88" => (x, y + 3.),
            "R61" | "R62" => (x + 4., y),
            "R66" => (x, y + 2.5),
            "CT1" | "CT2" => (x, y - 5.),
            "C96" => (x + 3.5, y),
            "C86" => (x - 3., y),
            "R72" => (x + 3., y),
            "R65" | "R68" => (x, y + 2.5),
            "R82" | "R84" => (x - 2.7, y),
            "R88" | "R92" => (x + 2.8, y),
            "R11" | "R31" => (x - 3., y),
            "D6" => (x, y + 2.5),
            "SW3" => (x + 8., y),
            "W_SW1" => (x, y + 11.),
            "W_SW2" => (x, y - 7.),
            "U10" => (x + 4., y),
            "H1" | "H2" => (x, y + 6.),
            "H3" | "H4" => (x, y - 6.),
            "H5" | "H6" => (x + 5., y),
            _ => xy,
        };
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
        let p = &self.pads[key];
        (p.x, p.y)
    }
    fn net(&self, key: &str) -> String {
        self.pads[key].net.clone()
    }
    fn path(&mut self, net: &str, layer: &str, width: f64, pts: &[(f64, f64)]) {
        for pair in pts.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            if a == b {
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
            self.out += &format!("via\t{net}\t{}\t{}\t0.6\t0.3\n", p.0, p.1);
        }
    }
    fn escape(&mut self, key: &str) -> (f64, f64) {
        let p = self.pads[key].clone();
        if p.through {
            return (p.x, p.y);
        }
        let r = key.split('.').next().unwrap();
        let (cx, cy) = self.centers[r];
        let vertical = (p.angle.abs() % 180. - 90.).abs() < 1.;
        let (w, h) = if vertical { (p.h, p.w) } else { (p.w, p.h) };
        let mut v = if key.ends_with(".9") && ["U1", "U2", "U3"].contains(&r) {
            (p.x, p.y - 3.8)
        } else if (p.x - cx).abs() > (p.y - cy).abs()
            || r.starts_with('U')
            || r.starts_with('D') && !vertical
            || r == "Q1"
        {
            (
                p.x + (if p.x >= cx { 1. } else { -1. }) * (w / 2. + 0.55),
                p.y,
            )
        } else {
            (
                p.x,
                p.y + (if p.y >= cy { 1. } else { -1. }) * (h / 2. + 0.55),
            )
        };
        if ["U5", "U6"].contains(&r)
            && key.split('.').nth(1).unwrap().parse::<u32>().unwrap() % 2 == 1
        {
            v.0 += if p.x >= cx { 1. } else { -1. };
        }
        if key == "U5.8" {
            v.0 = 187.;
        }
        if key == "D3.2" {
            v.0 = 216.5;
        }
        if key == "R74.1" {
            v.0 = 203.;
        }
        if key == "Q1.3" {
            v.0 = 211.85;
        }
        if key == "U3.9" {
            v.0 = 171.;
        }
        self.path(&p.net, "F.Cu", 0.25, &[(p.x, p.y), v]);
        self.via(&p.net, v);
        v
    }
    fn link(&mut self, a: &str, b: &str, layer: &str, mid: &[(f64, f64)]) {
        assert_eq!(self.net(a), self.net(b), "{a} {b}");
        let net = self.net(a);
        let a = if layer == "F.Cu" {
            self.p(a)
        } else {
            self.escape(a)
        };
        let b = if layer == "F.Cu" {
            self.p(b)
        } else {
            self.escape(b)
        };
        let mut pts = vec![a];
        pts.extend_from_slice(mid);
        pts.push(b);
        self.path(&net, layer, 0.25, &pts);
    }
    fn hv(&mut self) -> Result<()> {
        for (j, y) in ROWS.into_iter().enumerate() {
            let b = j * 20;
            for i in 0..5 {
                let x = 30. + 18. * i as f64;
                let r1 = format!("R{}", b + i * 2 + 1);
                let r2 = format!("R{}", b + i * 2 + 2);
                let cap = format!("C{}", b + i + 1);
                self.link(&format!("{r1}.2"), &format!("{r2}.1"), "F.Cu", &[]);
                self.link(
                    &format!("{r1}.1"),
                    &format!("{cap}.1"),
                    "F.Cu",
                    &[(x, y), (x, y + 8.)],
                );
                self.link(
                    &format!("{r2}.2"),
                    &format!("{cap}.2"),
                    "F.Cu",
                    &[(x + 18., y), (x + 18., y + 8.)],
                );
                if i == 0 {
                    self.link(&format!("W_HV{}.1", j + 1), &format!("{r1}.1"), "F.Cu", &[]);
                } else {
                    self.link(
                        &format!("R{}.2", b + i * 2),
                        &format!("{r1}.1"),
                        "F.Cu",
                        &[],
                    );
                }
                // 1.2-mm routed slot beneath the 600-V segment capacitor; no inner copper.
                self.rect("Edge.Cuts", x + 8.4, y + 4., x + 9.6, y + 12.);
            }
            let tap = self.net(&format!("R{}.2", b + 10));
            self.path(
                &tap,
                "F.Cu",
                0.25,
                &[
                    self.p(&format!("R{}.2", b + 10)),
                    (124., y),
                    (127., y),
                    (127., y - 10.),
                ],
            );
            self.path(&tap, "F.Cu", 0.25, &[(127., y - 10.), (127., y + 8.)]);
            for i in 0..7 {
                let cap = format!("C{}.1", 41 + j * 10 + i);
                let p = self.p(&cap);
                self.path(&tap, "F.Cu", 0.25, &[(127., p.1), p]);
            }
            self.path(
                &tap,
                "F.Cu",
                0.25,
                &[(124., y), self.p(&format!("R{}.1", b + 11))],
            );
            self.path(
                &tap,
                "F.Cu",
                0.25,
                &[(127., y + 0.635), self.p(&format!("R{}.1", b + 12))],
            );
            self.link(
                &format!("R{}.2", b + 11),
                &format!("RV{}.1", j + 1),
                "F.Cu",
                &[(126., y + 14.)],
            );
            self.link(
                &format!("RV{}.2", j + 1),
                &format!("RV{}.3", j + 1),
                "F.Cu",
                &[],
            );
            self.link(
                &format!("R{}.2", b + 12),
                &format!("U{}.3", j + 1),
                "F.Cu",
                &[],
            );
            self.link(
                &format!("D{}.3", j + 1),
                &format!("U{}.3", j + 1),
                "B.Cu",
                &[(136., y + 5.), (136., y + 0.635)],
            );
            self.link(
                &format!("U{}.1", j + 1),
                &format!("U{}.2", j + 1),
                "F.Cu",
                &[],
            );
            self.link(
                &format!("U{}.1", j + 1),
                &format!("U{}.6", j + 1),
                "In2.Cu",
                &[],
            );
        }
        Ok(())
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
    fn outline(&mut self) {
        let pts = [
            (3., 0.),
            (237., 0.),
            (240., 3.),
            (240., HEIGHT - 3.),
            (237., HEIGHT),
            (3., HEIGHT),
            (0., HEIGHT - 3.),
            (0., 3.),
            (3., 0.),
        ];
        for p in pts.windows(2) {
            self.out += &format!(
                "line\tEdge.Cuts\t0.05\t{}\t{}\t{}\t{}\n",
                p[0].0, p[0].1, p[1].0, p[1].1
            );
        }
        for (layer, net) in [("In1.Cu", "GND"), ("In2.Cu", "+4V8"), ("B.Cu", "-4V8")] {
            self.out += &format!("zone\t{net}\t{layer}\t128\t3\t237\t{}\n", HEIGHT - 1.);
        }
        for layer in ["In1.Cu", "In2.Cu", "B.Cu"] {
            self.out += &format!("keepout\tall\t{layer}\t1\t1\t119\t{}\n", HEIGHT - 1.);
        }
        self.out += &format!("keepout\tpours\tF.Cu\t1\t1\t119\t{}\n", HEIGHT - 1.);
        for (x, y, right) in [
            (141., 20., false),
            (141., 55., false),
            (163., 38., true),
            (198., 40., false),
            (188., 25., false),
        ] {
            for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] {
                self.out += &format!(
                    "keepout\tpours\t{layer}\t{}\t{}\t{}\t{}\n",
                    if right { x + 1.5 } else { x - 8. },
                    y - 4.,
                    if right { x + 8. } else { x - 1.5 },
                    y + 3.
                );
            }
        }
        for (x, y, text) in [
            (65., 5., "TEMPER | DIFFERENTIAL PROBE"),
            (65., 10., "REV B | ENGINEERING PROTOTYPE"),
            (65., 38., "HV DIVIDERS: NO INNER / BOTTOM PLANES"),
            (65., 42., "FIXED SHIELD: KEEP 20 mm FROM HV CONDUCTORS"),
            (65., 46., "3 kV TIP / DIFFERENTIAL TARGET | NOT CAT RATED"),
            (20., 15., "TIP +"),
            (20., 50., "TIP -"),
            (190., 4., "EARTH / SHIELD BOND AT OUTPUT"),
            (230., 34., "BNC / 1M"),
            (205., 18., "OUTPUT RANGE SELECT"),
        ] {
            self.out += &format!("text\tF.SilkS\t{x}\t{y}\t1\t{text}\n");
        }
        self.out += &format!("line\tDwgs.User\t0.2\t128\t2\t128\t{}\n", HEIGHT - 2.);
    }
    fn rails(&mut self) {
        let keys: Vec<_> = self
            .pads
            .iter()
            .filter(|(key, p)| {
                ["GND", "+4V8", "-4V8"].contains(&p.net.as_str())
                    && !p.through
                    && !["U1.4", "U2.4", "U3.4", "U4.4", "U12.4"].contains(&key.as_str())
            })
            .map(|(k, _)| k.clone())
            .collect();
        for key in keys {
            self.escape(&key);
        }
        // Grounded top perimeter gives the enclosure a defined RF return at the output.
        self.path("GND", "F.Cu", 1., &[(133., 5.), (235., 5.), (235., 30.)]);
        self.path(
            "GND",
            "F.Cu",
            0.5,
            &[(145., HEIGHT - 0.85), (230., HEIGHT - 0.85)],
        );
        self.via("GND", (235., 30.));
        for x in [145., 160., 175., 190., 205., 220., 230.] {
            self.via("GND", (x, 5.));
            self.via("GND", (x, HEIGHT - 0.85));
        }
    }
}
fn route() -> Result<()> {
    let mut c = Copper::load()?;
    c.rules()?;
    c.outline();
    c.hv()?;
    c.rails();
    c.signals();
    fs::write("layout/copper.tsv", c.out)?;
    Ok(())
}

impl Copper {
    fn rules(&self) -> Result<()> {
        // Prototype spacing budget, NOT an IEC/CAT certification: 1 mm air and
        // 2 mm surface per 300 V of distributed ladder voltage. Opposite legs
        // use max(rankA,rankB) under simultaneous |tip|<=3kV and |diff|<=3kV.
        let mut hv = Vec::new();
        for (leg, base) in [(0, 0), (1, 20)] {
            for i in 0..10 {
                hv.push((self.net(&format!("R{}.1", base + i + 1)), leg, 10 - i));
            }
        }
        let names = hv
            .iter()
            .map(|(n, _, _)| format!("B.NetName != '{n}'"))
            .collect::<Vec<_>>()
            .join(" && ");
        let mut s = "(version 1)\n# Generated by tools/layout.rs; see docs/layout.md for voltage assumptions.\n".to_string();
        for (name, _, rank) in &hv {
            s += &format!("(rule \"{name} to LV\" (condition \"A.NetName == '{name}' && ({names})\") (constraint clearance (min {rank}mm)) (constraint creepage (min {}mm)))\n", rank*2);
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
                s += &format!("(rule \"{a} to {b}\" (condition \"A.NetName == '{a}' && B.NetName == '{b}'\") (constraint clearance (min {delta}mm)) (constraint creepage (min {}mm)))\n", delta*2);
            }
        }
        s += "# Only the selected VSSOP package's adjacent pads require 0.15 mm.\n(rule \"U6 VSSOP pads\" (condition \"A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('U6') && B.memberOfFootprint('U6')\") (constraint clearance (min 0.15mm)))\n";
        fs::write("cad/differential-probe.kicad_dru", s)?;
        Ok(())
    }
    // Explicit routes; both wanted buffer feeds stay on F.Cu.
    fn signals(&mut self) {
        self.path("+4V8", "F.Cu", 0.25, &[(223.02, 67.75), (230.98, 67.75)]);
        self.path("RESET", "F.Cu", 0.25, &[(223.02, 72.25), (230.98, 72.25)]);
        for (u, cap) in [
            ("U1", "C82"),
            ("U2", "C84"),
            ("U3", "C86"),
            ("U4", "C88"),
            ("U12", "C97"),
        ] {
            self.link(&format!("{u}.4"), &format!("{cap}.2"), "F.Cu", &[]);
        }
        for (j, y) in ROWS.into_iter().enumerate() {
            self.link(
                &format!("RV{}.2", j + 1),
                &format!("C{}.2", 47 + j * 10),
                "F.Cu",
                &[(123.46, y + 21.), (132., y + 21.), (132., y + 8.)],
            );
            let tap = self.net(&format!("CT{}.1", j + 1));
            self.path(&tap, "F.Cu", 0.25, &[(127., y + 8.), (127., y + 11.)]);
            self.via(&tap, (127., y + 11.));
            self.path(&tap, "B.Cu", 0.25, &[(127., y + 11.), (140.5, y + 18.)]);
        }
        for (a, b, l, p) in [
            (
                "U1.6",
                "R61.1",
                "F.Cu",
                vec![
                    (150., 20.635),
                    (150., 18.3),
                    (152., 18.3),
                    (152., 22.),
                    (174.8, 22.),
                    (174.8, 36.8),
                ],
            ),
            (
                "U2.6",
                "R62.1",
                "F.Cu",
                vec![(150., 55.635), (150., 49.5), (177., 49.5), (177., 39.2)],
            ),
            ("R61.2", "U3.3", "F.Cu", vec![]),
            ("R62.2", "U3.2", "F.Cu", vec![]),
            ("U3.3", "R63.1", "F.Cu", vec![(166.8, 37.365), (166.8, 32.)]),
            ("R63.2", "R64.1", "F.Cu", vec![]),
            ("U3.2", "R65.1", "F.Cu", vec![(168., 38.635), (168., 40.5)]),
            ("R65.2", "R66.1", "F.Cu", vec![]),
            ("R66.2", "U3.6", "B.Cu", vec![]),
            ("U3.6", "R100.1", "F.Cu", vec![(157., 37.365), (157., 34.)]),
            (
                "R100.2",
                "U12.3",
                "In2.Cu",
                vec![(153., 34.), (153., 27.), (182., 27.)],
            ),
            ("U12.2", "R68.1", "F.Cu", vec![(182., 24.365), (182., 19.)]),
            (
                "R68.1",
                "R67.1",
                "F.Cu",
                vec![(182., 21.175), (180., 21.175)],
            ),
            ("R68.2", "R97.1", "F.Cu", vec![]),
            ("R97.2", "R98.1", "F.Cu", vec![]),
            ("R98.2", "R99.1", "F.Cu", vec![]),
            ("R99.2", "U12.6", "B.Cu", vec![]),
            (
                "U3.6",
                "R101.1",
                "F.Cu",
                vec![(158.2, 37.365), (158.2, 45.)],
            ),
            (
                "R101.2",
                "W_SW1.1",
                "B.Cu",
                vec![(150., 45.), (150., 8.), (206., 8.), (206., 24.)],
            ),
            ("U12.6", "R102.1", "F.Cu", vec![(194., 25.635)]),
            ("R102.2", "W_SW1.3", "F.Cu", vec![(205., 28.), (209., 32.)]),
            ("W_SW1.2", "R103.1", "F.Cu", vec![]),
            (
                "W_SW1.2",
                "R69.1",
                "In2.Cu",
                vec![(212., 28.), (212., 46.), (182., 46.)],
            ),
            ("R69.2", "U4.3", "F.Cu", vec![]),
            ("R69.2", "C61.1", "F.Cu", vec![(190., 40.635)]),
            (
                "U4.6",
                "U4.2",
                "B.Cu",
                vec![(205.5, 40.635), (205.5, 35.), (193., 35.), (193., 39.365)],
            ),
            ("U4.6", "R70.1", "F.Cu", vec![]),
            (
                "R70.2",
                "W_J3.1",
                "F.Cu",
                vec![(212., 40.635), (215., 37.635), (229., 37.635)],
            ),
            ("D3.3", "W_J3.1", "F.Cu", vec![(224., 41.), (229., 41.)]),
            (
                "R69.1",
                "R71.1",
                "F.Cu",
                vec![(182., 40.635), (182., 53.), (193., 53.)],
            ),
            ("R71.2", "R72.1", "F.Cu", vec![]),
            ("R71.2", "U6.2", "B.Cu", vec![(192., 49.), (192., 60.675)]),
            ("U6.2", "U6.5", "F.Cu", vec![(195., 60.675), (195., 61.975)]),
            (
                "U1.6",
                "U5.4",
                "B.Cu",
                vec![(149., 20.635), (149., 50.), (177., 50.), (177., 61.)],
            ),
            ("U5.4", "U5.7", "F.Cu", vec![(173.5, 61.), (173.5, 62.95)]),
            (
                "U2.6",
                "U5.8",
                "B.Cu",
                vec![(148., 55.635), (148., 69.2), (187., 69.2), (187., 62.95)],
            ),
            ("U5.8", "U5.11", "F.Cu", vec![(181., 62.95), (181., 61.)]),
            ("R74.2", "Q1.1", "F.Cu", vec![]),
            (
                "Q1.3",
                "R75.1",
                "In2.Cu",
                vec![(210.5, 61.), (206., 61.), (206., 66.4125)],
            ),
            ("R75.1", "U7.6", "In2.Cu", vec![(209., 67.), (209., 64.54)]),
            ("R96.2", "D9.2", "F.Cu", vec![(225., 46.), (232., 46.)]),
            (
                "R96.1",
                "U7.1",
                "F.Cu",
                vec![(216., 48.), (212., 52.), (212., 58.19)],
            ),
            ("SW3.1", "C95.1", "In2.Cu", vec![]),
            ("R95.1", "C95.2", "F.Cu", vec![]),
            ("C95.2", "D8.1", "F.Cu", vec![(232., 62.5)]),
            ("R95.1", "SW3.2", "B.Cu", vec![(225., 64.), (225., 72.)]),
            (
                "R95.1",
                "U7.4",
                "B.Cu",
                vec![(224., 62.635), (211., 62.635), (211., 62.)],
            ),
            ("U8.1", "U8.3", "In2.Cu", vec![(170., 72.05), (170., 73.95)]),
            ("U8.1", "C71.1", "F.Cu", vec![(171., 68.5), (165.525, 68.5)]),
            ("D4.1", "C71.1", "F.Cu", vec![(160., 73.), (160., 71.)]),
            ("U8.4", "R81.2", "F.Cu", vec![(176., 74.), (178.8, 75.8)]),
            ("R81.2", "R82.1", "F.Cu", vec![(177.9125, 80.), (173., 80.)]),
            ("U9.2", "U9.3", "F.Cu", vec![]),
            (
                "U9.2",
                "C73.1",
                "In2.Cu",
                vec![(189.5, 73.), (189.5, 68.5), (186.525, 68.5)],
            ),
            ("D5.2", "C73.1", "F.Cu", vec![(187., 76.), (187., 71.)]),
            ("U9.4", "R83.2", "F.Cu", vec![(197., 74.), (199.8, 75.8)]),
            ("R83.2", "R84.1", "F.Cu", vec![(198.9125, 80.), (194., 80.)]),
            (
                "W_BT1.1",
                "W_SW2.2",
                "B.Cu",
                vec![(221., 78.), (221., 76.), (210., 76.)],
            ),
            (
                "W_BT2.2",
                "W_SW2.5",
                "In2.Cu",
                vec![(217.5, 77.), (216., 77.)],
            ),
            (
                "W_SW2.1",
                "D4.2",
                "B.Cu",
                vec![(208., 71.), (208., 75.25), (161., 75.25), (161., 78.)],
            ),
            (
                "W_SW2.4",
                "D5.1",
                "In2.Cu",
                vec![
                    (215., 69.),
                    (195., 69.),
                    (195., 75.),
                    (180., 75.),
                    (180., 76.),
                ],
            ),
            ("U10.1", "U10.2", "F.Cu", vec![]),
            ("U11.1", "U11.2", "F.Cu", vec![]),
            (
                "R85.2",
                "U10.1",
                "F.Cu",
                vec![(154., 9.0875), (154., 15.95)],
            ),
            ("R86.2", "U11.3", "F.Cu", vec![(160., 65.0875), (160., 60.)]),
            ("R87.1", "U10.1", "B.Cu", vec![(162., 16.), (154., 16.)]),
            (
                "R89.1",
                "R87.1",
                "B.Cu",
                vec![(171.5, 12.975), (171.5, 15.975), (165., 15.975)],
            ),
            (
                "R91.1",
                "U11.3",
                "F.Cu",
                vec![(165., 58.), (161., 58.), (159.9, 60.)],
            ),
            (
                "R93.1",
                "R91.1",
                "F.Cu",
                vec![(168., 53.9125), (168., 56.9125)],
            ),
            ("R87.2", "R88.1", "F.Cu", vec![(163., 13.), (163., 20.)]),
            ("R89.2", "R90.1", "F.Cu", vec![(172., 10.0875), (172., 20.)]),
            (
                "R91.2",
                "R92.1",
                "In2.Cu",
                vec![(162., 54.025), (162., 62.975)],
            ),
            (
                "R93.2",
                "R94.1",
                "B.Cu",
                vec![(169., 51.025), (169., 62.975)],
            ),
        ] {
            self.link(a, b, l, &p);
        }
        self.bus_x(&["R87.2", "U5.5", "U5.9"], "B.Cu", 178.7);
        self.bus_x(&["R91.2", "U5.6", "U5.10"], "B.Cu", 171.6);
        self.bus_x(&["R89.2", "U6.3"], "B.Cu", 188.9);
        self.bus_x(&["R93.2", "U6.6"], "B.Cu", 202.);
        self.bus_x(&["D1.2", "D2.2", "D3.2", "U10.1"], "B.Cu", 143.5);
        self.bus_x(&["D1.1", "D2.1", "D3.1", "U11.3"], "B.Cu", 142.);
        self.bus_y(
            &[
                "U5.1", "U5.2", "U5.13", "U5.14", "U6.1", "U6.7", "R73.2", "R74.1",
            ],
            "B.Cu",
            52.,
        );
    }
    fn bus_x(&mut self, keys: &[&str], layer: &str, x: f64) {
        let net = self.net(keys[0]);
        let mut pts = Vec::new();
        for &k in keys {
            assert_eq!(self.net(k), net);
            let p = self.escape(k);
            let y = match k {
                "D1.1" => 22.8,
                "D2.1" => 57.8,
                "D3.1" => 46.5,
                "D3.2" => 50.,
                "U10.1" => 12.8,
                "D1.2" => 25.95,
                "U5.9" => 64.,
                "U5.10" => 65.,
                _ => p.1,
            };
            self.path(&net, "B.Cu", 0.25, &[p, (p.0, y)]);
            self.via(&net, (p.0, y));
            self.path(&net, "In2.Cu", 0.25, &[(p.0, y), (x, y)]);
            self.via(&net, (x, y));
            pts.push((x, y));
        }
        pts.sort_by(|a, b| a.1.total_cmp(&b.1));
        self.path(&net, layer, 0.25, &pts);
    }
    fn bus_y(&mut self, keys: &[&str], layer: &str, y: f64) {
        let net = self.net(keys[0]);
        let mut pts = Vec::new();
        for &k in keys {
            assert_eq!(self.net(k), net);
            let p = self.escape(k);
            self.path(&net, layer, 0.25, &[p, (p.0, y)]);
            self.via(&net, (p.0, y));
            pts.push((p.0, y));
        }
        pts.sort_by(|a, b| a.0.total_cmp(&b.0));
        self.path(&net, "In2.Cu", 0.25, &pts);
    }
}

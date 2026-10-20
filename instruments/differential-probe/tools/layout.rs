//! Explicit probe placement and hand-authored routing. KiCad owns pad transforms.
use std::{
    collections::{BTreeMap, BTreeSet},
    error::Error,
    fs,
};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
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
        &[
            (1, 0., -4.),
            (2, 0., 0.),
            (3, 0., 4.),
            (4, 5., -4.),
            (5, 5., 0.),
            (6, 5., 4.),
        ],
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
    for (j, y) in [25., 95.].into_iter().enumerate() {
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
    for (r, x, y, a) in [
        ("U3", 170., 60., 0),
        ("R61", 162., 62., 0),
        ("R62", 162., 59.365, 0),
        ("R63", 152., 53.5, 180),
        ("R64", 148., 53.5, 180),
        ("R65", 155., 66., 0),
        ("R66", 159., 66., 0),
        ("R67", 147., 64., 90),
        ("R68", 164., 66., 0),
        ("C62", 168., 55., 0),
        ("C63", 164., 49., 0),
        ("C85", 177., 57., 270),
        ("C86", 167., 66., 90),
        ("U4", 198., 60., 0),
        ("R69", 184., 60.635, 0),
        ("C61", 190., 63., 270),
        ("R70", 207., 60.635, 0),
        ("D3", 220., 61., 0),
        ("C87", 204., 58., 270),
        ("C88", 195., 66., 90),
        ("U5", 180., 86., 0),
        ("U6", 195., 86., 0),
        ("U7", 216., 87., 0),
        ("C89", 173., 83., 270),
        ("C90", 188., 82., 90),
        ("C91", 201., 83., 270),
        ("C92", 190., 90., 90),
        ("C93", 222., 82., 270),
        ("C94", 210., 93., 90),
        ("R71", 193., 76., 90),
        ("R72", 196., 76., 270),
        ("R73", 204., 78., 90),
        ("R74", 206., 81., 0),
        ("R75", 207., 90.5, 90),
        ("Q1", 210., 84., 0),
        ("R95", 226., 86., 90),
        ("C95", 230., 86., 90),
        ("D8", 234., 86., 90),
        ("R96", 220., 73., 0),
        ("D9", 230., 73., 0),
        ("SW3", 227., 95., 0),
        ("U8", 173., 108., 0),
        ("U9", 194., 108., 0),
        ("C71", 167., 106., 0),
        ("C72", 179., 106., 0),
        ("C73", 188., 106., 0),
        ("C74", 200., 106., 0),
        ("R81", 177., 112., 0),
        ("R82", 173., 113., 90),
        ("R83", 198., 112., 0),
        ("R84", 194., 113., 90),
        ("D4", 163., 111., 0),
        ("D5", 184., 111., 0),
        ("D6", 183., 116., 0),
        ("D7", 205., 116., 0),
        ("U10", 157., 20., 0),
        ("U11", 157., 100., 0),
        ("R85", 157., 15., 90),
        ("R86", 157., 106., 90),
        ("R87", 165., 19., 90),
        ("R88", 165., 24., 90),
        ("R89", 170., 16., 90),
        ("R90", 170., 24., 90),
        ("R91", 165., 96., 90),
        ("R92", 165., 101., 90),
        ("R93", 170., 93., 90),
        ("R94", 170., 101., 90),
    ] {
        put(r.into(), x, y, a, "");
    }
    for (r, x, y, fp) in [
        ("W_SW1", 151., 60., "Range_Wire_Pads"),
        ("W_SW2", 210., 109., "Power_Wire_Pads"),
        ("W_BT1", 226., 105., "Wire_Pair"),
        ("W_BT2", 226., 114., "Wire_Pair"),
        ("W_J3", 234., 60., "Wire_Pair"),
    ] {
        put(r.into(), x, y, 0, &format!("Probe:{fp}"));
    }
    for (i, x, y) in [
        (1, 135., 6.),
        (2, 234., 6.),
        (3, 135., 114.),
        (4, 234., 114.),
    ] {
        put(
            format!("H{i}"),
            x,
            y,
            0,
            "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
        );
    }
    for (i, y) in [(5, 7.), (6, 113.)] {
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
            "C86" | "C88" => (x, y + 3.),
            "R61" => (x, y + 1.5),
            "R65" | "R68" => (x, y + 2.5),
            "R82" | "R84" => (x - 2.7, y),
            "R88" | "R92" => (x + 2.8, y),
            "R11" | "R31" => (x - 3., y),
            "D6" => (x, y + 2.5),
            "SW3" => (x, y + 5.),
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
        for (j, y) in [25., 95.].into_iter().enumerate() {
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
            (240., 117.),
            (237., 120.),
            (3., 120.),
            (0., 117.),
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
            self.out += &format!("zone\t{net}\t{layer}\t128\t3\t237\t119\n");
        }
        for layer in ["In1.Cu", "In2.Cu", "B.Cu"] {
            self.out += &format!("keepout\tall\t{layer}\t1\t1\t119\t119\n");
        }
        self.out += "keepout\tpours\tF.Cu\t1\t1\t119\t119\n";
        for (x, y) in [(141., 25.), (141., 95.), (170., 60.), (198., 60.)] {
            for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] {
                self.out += &format!(
                    "keepout\tpours\t{layer}\t{}\t{}\t{}\t{}\n",
                    x - 8.,
                    y - 4.,
                    x - 1.5,
                    y + 3.
                );
            }
        }
        for (x, y, text) in [
            (65., 10., "TEMPER | DIFFERENTIAL PROBE"),
            (65., 15., "REV A | ENGINEERING PROTOTYPE"),
            (65., 58., "HV DIVIDERS: NO COPPER ON INNER / BOTTOM LAYERS"),
            (65., 63., "FIXED SHIELD: KEEP 20 mm ABOVE / BELOW HV COPPER"),
            (65., 68., "NOT CAT RATED | QUALIFICATION REQUIRED"),
            (20., 20., "TIP +"),
            (20., 90., "TIP -"),
            (179., 8., "EARTH / SHIELD BOND AT OUTPUT"),
            (230., 54., "BNC / 1M"),
            (160., 42., "RANGE: SHORT WIRES ONLY"),
        ] {
            self.out += &format!("text\tF.SilkS\t{x}\t{y}\t1\t{text}\n");
        }
        self.out += "line\tDwgs.User\t0.2\t128\t2\t128\t118\n";
    }
    fn rails(&mut self) {
        let keys: Vec<_> = self
            .pads
            .iter()
            .filter(|(key, p)| {
                ["GND", "+4V8", "-4V8"].contains(&p.net.as_str())
                    && !p.through
                    && !["U1.4", "U2.4", "U3.4", "U4.4"].contains(&key.as_str())
            })
            .map(|(k, _)| k.clone())
            .collect();
        for key in keys {
            self.escape(&key);
        }
        // Grounded top perimeter gives the enclosure a defined RF return at the output.
        self.path("GND", "F.Cu", 1., &[(133., 5.), (235., 5.), (235., 50.)]);
        self.path("GND", "F.Cu", 0.5, &[(145., 118.), (230., 118.)]);
        self.via("GND", (235., 50.));
        for x in [145., 160., 175., 190., 205., 220., 230.] {
            self.via("GND", (x, 5.));
            self.via("GND", (x, 118.));
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
        // use the sum of ranks, allowing +/-3 kV to earth independently.
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
                    (ra + rb) as u32
                };
                s += &format!("(rule \"{a} to {b}\" (condition \"A.NetName == '{a}' && B.NetName == '{b}'\") (constraint clearance (min {delta}mm)) (constraint creepage (min {}mm)))\n", delta*2);
            }
        }
        s += "# Only the selected VSSOP package's adjacent pads require 0.15 mm.\n(rule \"U6 VSSOP pads\" (condition \"A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('U6') && B.memberOfFootprint('U6')\") (constraint clearance (min 0.15mm)))\n";
        fs::write("cad/differential-probe.kicad_dru", s)?;
        Ok(())
    }
    // Explicit signal routes. Each row names the actual pads and chosen layer/waypoints.
    fn signals(&mut self) {
        // Each tactile-switch terminal has two physical pads with one pin number.
        self.path("+4V8", "F.Cu", 0.25, &[(223.02, 92.75), (230.98, 92.75)]);
        self.path("RESET", "F.Cu", 0.25, &[(223.02, 97.25), (230.98, 97.25)]);
        for (u, cap) in [("U1", "C82"), ("U2", "C84"), ("U3", "C86"), ("U4", "C88")] {
            self.link(&format!("{u}.4"), &format!("{cap}.2"), "F.Cu", &[]);
        }
        for (j, y) in [25., 95.].into_iter().enumerate() {
            self.link(
                &format!("RV{}.2", j + 1),
                &format!("C{}.2", 47 + j * 10),
                "F.Cu",
                &[(123.46, y + 21.), (132., y + 21.), (132., y + 8.)],
            );
        }
        for (a, b, l, points) in [
            (
                "U1.6",
                "R61.1",
                "F.Cu",
                vec![(150., 25.635), (150., 44.), (158.2, 52.2), (158.2, 62.)],
            ),
            (
                "U2.6",
                "R62.1",
                "In2.Cu",
                vec![
                    (148.5, 95.635),
                    (148.5, 77.635),
                    (158., 69.635),
                    (158., 59.365),
                ],
            ),
            (
                "R61.2",
                "U3.3",
                "F.Cu",
                vec![(165., 62.), (166.365, 60.635)],
            ),
            ("R62.2", "U3.2", "F.Cu", vec![]),
            ("W_SW1.2", "R61.2", "B.Cu", vec![(154., 62.2), (164., 62.2)]),
            (
                "W_SW1.5",
                "R62.2",
                "B.Cu",
                vec![(159., 57.5), (164., 57.5), (164., 59.365)],
            ),
            ("W_SW1.1", "R63.1", "F.Cu", vec![]),
            ("R63.2", "R64.1", "F.Cu", vec![]),
            ("W_SW1.3", "R67.1", "F.Cu", vec![]),
            ("W_SW1.4", "R65.1", "F.Cu", vec![(153., 56.), (153., 66.)]),
            ("R65.2", "R66.1", "F.Cu", vec![]),
            (
                "W_SW1.6",
                "R68.1",
                "F.Cu",
                vec![(162., 64.), (163.175, 65.175)],
            ),
            ("R66.2", "R68.2", "B.Cu", vec![(161., 69.), (166., 69.)]),
            (
                "R68.2",
                "U3.6",
                "In2.Cu",
                vec![(166., 70.), (176., 70.), (176., 60.635)],
            ),
            (
                "U3.1",
                "U3.6",
                "F.Cu",
                vec![(169.5, 58.095), (169.5, 55.), (175., 55.), (175., 60.635)],
            ),
            (
                "C62.2",
                "U3.1",
                "F.Cu",
                vec![(169.5, 56.5), (167.525, 56.5)],
            ),
            ("C62.1", "U3.2", "F.Cu", vec![(166., 55.), (166., 59.365)]),
            ("C63.1", "R61.2", "In2.Cu", vec![(162., 56.), (162., 61.)]),
            ("U3.6", "R69.1", "F.Cu", vec![]),
            ("R69.2", "U4.3", "F.Cu", vec![]),
            ("R69.2", "C61.1", "F.Cu", vec![(190., 60.635)]),
            (
                "U4.6",
                "U4.2",
                "B.Cu",
                vec![(205.5, 60.635), (205.5, 55.), (193., 55.), (193., 59.365)],
            ),
            ("U4.6", "R70.1", "F.Cu", vec![]),
            (
                "R70.2",
                "W_J3.1",
                "F.Cu",
                vec![(212., 60.635), (215., 57.635), (229., 57.635)],
            ),
            ("D3.3", "W_J3.1", "F.Cu", vec![(224., 61.), (229., 61.)]),
            (
                "R69.1",
                "R71.1",
                "F.Cu",
                vec![(182., 60.635), (182., 78.), (193., 78.)],
            ),
            ("R71.2", "R72.1", "F.Cu", vec![]),
            ("R71.2", "U6.2", "B.Cu", vec![(192., 74.), (192., 85.675)]),
            ("U6.2", "U6.5", "F.Cu", vec![(195., 85.675), (195., 86.975)]),
            (
                "U1.6",
                "U5.4",
                "B.Cu",
                vec![(149., 25.635), (149., 82.), (172., 82.), (172., 86.)],
            ),
            ("U5.4", "U5.7", "F.Cu", vec![(173.5, 86.), (173.5, 87.95)]),
            (
                "U2.6",
                "U5.8",
                "B.Cu",
                vec![(149.5, 95.635), (149.5, 102.), (186., 102.), (186., 87.95)],
            ),
            ("U5.8", "U5.11", "F.Cu", vec![(181., 87.95), (181., 86.)]),
            ("R74.2", "Q1.1", "F.Cu", vec![]),
            (
                "Q1.3",
                "R75.1",
                "In2.Cu",
                vec![(210.5, 86.), (206., 86.), (206., 91.4125)],
            ),
            ("R75.1", "U7.6", "In2.Cu", vec![(209., 92.), (209., 89.54)]),
            ("R96.2", "D9.2", "F.Cu", vec![(225., 71.), (232., 71.)]),
            (
                "R96.1",
                "U7.1",
                "F.Cu",
                vec![(216., 73.), (212., 77.), (212., 83.19)],
            ),
            ("SW3.1", "C95.1", "In2.Cu", vec![]),
            ("R95.1", "C95.2", "F.Cu", vec![]),
            ("C95.2", "D8.1", "F.Cu", vec![(232., 87.5)]),
            ("R95.1", "SW3.2", "B.Cu", vec![(225., 89.), (225., 97.)]),
            (
                "R95.1",
                "U7.4",
                "B.Cu",
                vec![(224., 87.635), (211., 87.635), (211., 87.)],
            ),
            (
                "U8.1",
                "U8.3",
                "In2.Cu",
                vec![(170., 107.05), (170., 108.95)],
            ),
            (
                "U8.1",
                "C71.1",
                "F.Cu",
                vec![(171., 103.5), (165.525, 103.5)],
            ),
            ("D4.1", "C71.1", "F.Cu", vec![(160., 108.), (160., 106.)]),
            ("U8.4", "R81.2", "F.Cu", vec![(176., 109.), (178.8, 110.8)]),
            (
                "R81.2",
                "R82.1",
                "F.Cu",
                vec![(177.9125, 115.), (173., 115.)],
            ),
            ("U9.2", "U9.3", "F.Cu", vec![]),
            (
                "U9.2",
                "C73.1",
                "In2.Cu",
                vec![(189.5, 108.), (189.5, 103.5), (186.525, 103.5)],
            ),
            ("D5.2", "C73.1", "F.Cu", vec![(187., 111.), (187., 106.)]),
            ("U9.4", "R83.2", "F.Cu", vec![(197., 109.), (199.8, 110.8)]),
            (
                "R83.2",
                "R84.1",
                "F.Cu",
                vec![(198.9125, 115.), (194., 115.)],
            ),
            (
                "W_BT1.1",
                "W_SW2.2",
                "B.Cu",
                vec![(223., 104.), (218., 104.), (218., 111.), (210., 111.)],
            ),
            (
                "W_BT2.2",
                "W_SW2.5",
                "In2.Cu",
                vec![(228.5, 111.), (216., 111.)],
            ),
            (
                "W_SW2.1",
                "D4.2",
                "B.Cu",
                vec![(207., 104.), (161., 104.), (161., 113.)],
            ),
            (
                "W_SW2.4",
                "D5.1",
                "In2.Cu",
                vec![(215., 102.), (180., 102.), (180., 111.)],
            ),
            ("U10.1", "U10.2", "F.Cu", vec![]),
            ("U11.1", "U11.2", "F.Cu", vec![]),
            (
                "R85.2",
                "U10.1",
                "F.Cu",
                vec![(154., 14.0875), (154., 20.95)],
            ),
            (
                "R86.2",
                "U11.3",
                "F.Cu",
                vec![(160., 105.0875), (160., 100.)],
            ),
            ("R87.1", "U10.1", "B.Cu", vec![(162., 21.), (154., 21.)]),
            (
                "R89.1",
                "R87.1",
                "B.Cu",
                vec![(171.5, 17.975), (171.5, 20.975), (165., 20.975)],
            ),
            (
                "R91.1",
                "U11.3",
                "F.Cu",
                vec![(165., 98.), (161., 98.), (159.9, 100.)],
            ),
            (
                "R93.1",
                "R91.1",
                "F.Cu",
                vec![(170., 94.8), (173.5, 94.8), (173.5, 98.), (166.5, 98.)],
            ),
            ("R87.2", "R88.1", "F.Cu", vec![(163., 18.), (163., 25.)]),
            ("R89.2", "R90.1", "F.Cu", vec![(172., 15.0875), (172., 25.)]),
            (
                "R91.2",
                "R92.1",
                "In2.Cu",
                vec![(162., 94.025), (162., 102.975)],
            ),
            (
                "R93.2",
                "R94.1",
                "F.Cu",
                vec![(174., 92.0875), (174., 102.)],
            ),
        ] {
            self.link(a, b, l, &points);
        }
        // Dedicated vertical channels on the back carry the slow comparator references.
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
            72.,
        );
    }
    fn bus_x(&mut self, keys: &[&str], layer: &str, x: f64) {
        let net = self.net(keys[0]);
        let mut pts = Vec::new();
        for &k in keys {
            assert_eq!(self.net(k), net);
            let p = self.escape(k);
            let y = match k {
                "D1.1" => 27.8,
                "D2.1" => 97.8,
                "D3.1" => 48.,
                "D3.2" => 46.,
                "U10.1" => 17.8,
                "U5.9" => 89.,
                "U5.10" => 90.,
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

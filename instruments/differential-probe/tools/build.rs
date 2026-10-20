//! Reproducible KiCad schematic authoring, using only the Rust standard library.
//! Run from instruments/differential-probe; native KiCad files are checked in.
use std::{collections::BTreeMap, fs, path::Path};
type Pt = (f64, f64);
const G: f64 = 1.27;
const LIB: &str = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols";
fn q(s: &str) -> String {
    format!(
        "\"{}\"",
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
    )
}
fn id(s: &str) -> String {
    let mut a = 0xcbf29ce484222325u64;
    let mut b = 0x84222325cbf29ce4u64;
    for c in s.bytes() {
        a = (a ^ c as u64).wrapping_mul(0x100000001b3);
        b = (b ^ c as u64).wrapping_mul(0x100000001b3).rotate_left(7);
    }
    let h = format!("{a:016x}{b:016x}");
    format!(
        "{}-{}-4{}-8{}-{}",
        &h[..8],
        &h[8..12],
        &h[13..16],
        &h[17..20],
        &h[20..]
    )
}
fn effects(size: f64, hide: bool) -> String {
    format!(
        "(effects (font (size {size} {size})) {})",
        if hide { "hide" } else { "" }
    )
}
fn prop(k: &str, v: &str, p: Pt, hide: bool) -> String {
    format!(
        "(property {} {} (at {} {} 0) {})",
        q(k),
        q(v),
        p.0 * G,
        p.1 * G,
        effects(1.27, hide)
    )
}
#[derive(Clone)]
struct Pin {
    n: String,
    name: String,
    typ: String,
    p: Pt,
    angle: i32,
}
fn pin(n: &str, name: &str, typ: &str, x: f64, y: f64, angle: i32) -> Pin {
    Pin {
        n: n.into(),
        name: name.into(),
        typ: typ.into(),
        p: (x, y),
        angle,
    }
}
#[derive(Clone)]
struct Sym {
    text: String,
    pins: Vec<Pin>,
    h: f64,
}
fn custom(name: &str, pins: Vec<Pin>, w: f64, h: f64, triangle: bool) -> Sym {
    let shape = if triangle {
        format!("(polyline (pts (xy {} {}) (xy {} 0) (xy {} {}) (xy {} {})) (stroke (width .254) (type default)) (fill (type background)))",-w*G,h*G,w*G,-w*G,-h*G,-w*G,h*G)
    } else {
        format!("(rectangle (start {} {}) (end {} {}) (stroke (width .254) (type default)) (fill (type background)))",-w*G,h*G,w*G,-h*G)
    };
    let ps = pins
        .iter()
        .map(|p| {
            format!(
                "(pin {} line (at {} {} {}) (length {}) (name {} {}) (number {} {}))",
                p.typ,
                p.p.0 * G,
                p.p.1 * G,
                p.angle,
                2.0 * G,
                q(&p.name),
                effects(0.9, false),
                q(&p.n),
                effects(0.9, false)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    Sym{text:format!("(symbol {} (pin_names (offset .508)) (in_bom yes) (on_board yes) {} {} (symbol {} {}) (symbol {} {}))",q(&format!("Probe:{name}")),prop("Reference","U",(0.,-h-2.),false),prop("Value",name,(0.,h+2.),false),q(&format!("{name}_0_1")),shape,q(&format!("{name}_1_1")),ps),pins,h}
}
fn official(lib: &str, name: &str, pins: Vec<Pin>, h: f64) -> Sym {
    let txt = fs::read_to_string(format!("{LIB}/{lib}.kicad_sym")).unwrap();
    let start = txt.find(&format!("(symbol \"{name}\"\n")).expect(name);
    let mut depth = 0;
    let mut quoted = false;
    let mut esc = false;
    let mut end = start;
    for (i, c) in txt[start..].char_indices() {
        if esc {
            esc = false;
            continue;
        }
        if c == '\\' && quoted {
            esc = true;
            continue;
        }
        if c == '"' {
            quoted = !quoted
        }
        if !quoted {
            if c == '(' {
                depth += 1
            }
            if c == ')' {
                depth -= 1;
                if depth == 0 {
                    end = start + i + 1;
                    break;
                }
            }
        }
    }
    let text = txt[start..end].replacen(
        &format!("(symbol \"{name}\""),
        &format!("(symbol \"Probe:{name}\""),
        1,
    );
    Sym { text, pins, h }
}
#[derive(Clone)]
struct Part {
    value: String,
    mpn: String,
    mfr: String,
    fp: String,
    url: String,
    lcsc: String,
}
fn part(v: &str, m: &str, mfr: &str, fp: &str, url: &str, lcsc: &str) -> Part {
    Part {
        value: v.into(),
        mpn: m.into(),
        mfr: mfr.into(),
        fp: fp.into(),
        url: url.into(),
        lcsc: lcsc.into(),
    }
}
struct Placed {
    pins: BTreeMap<String, (Pt, i32)>,
    sheet: usize,
}
struct Design {
    syms: BTreeMap<String, Sym>,
    pages: Vec<String>,
    placed: BTreeMap<String, Placed>,
    expected: BTreeMap<(String, String), String>,
    count: usize,
}
impl Design {
    fn new() -> Self {
        Self {
            syms: BTreeMap::new(),
            pages: vec![String::new(); 3],
            placed: BTreeMap::new(),
            expected: BTreeMap::new(),
            count: 0,
        }
    }
    fn uid(&mut self) -> String {
        self.count += 1;
        id(&format!("graphic-{}", self.count))
    }
    fn wire(&mut self, s: usize, a: Pt, b: Pt) {
        if a == b {
            return;
        }
        let u = self.uid();
        self.pages[s] += &format!(
            "(wire (pts (xy {} {}) (xy {} {})) (stroke (width 0) (type default)) (uuid {u}))\n",
            a.0 * G,
            a.1 * G,
            b.0 * G,
            b.1 * G
        );
    }
    fn dot(&mut self, s: usize, p: Pt) {
        let u = self.uid();
        self.pages[s] += &format!(
            "(junction (at {} {}) (diameter 0) (color 0 0 0 0) (uuid {u}))\n",
            p.0 * G,
            p.1 * G
        );
    }
    fn text(&mut self, s: usize, p: Pt, t: &str, size: f64) {
        let u = self.uid();
        self.pages[s]+=&format!("(text {} (at {} {} 0) (effects (font (size {size} {size})) (justify left top)) (uuid {u}))\n",q(t),p.0*G,p.1*G);
    }
    fn block(&mut self, s: usize, a: Pt, b: Pt, t: &str) {
        let u = self.uid();
        self.pages[s]+=&format!("(rectangle (start {} {}) (end {} {}) (stroke (width .254) (type default)) (fill (color 0 0 0 0)) (uuid {u}))\n",a.0*G,a.1*G,b.0*G,b.1*G);
        self.text(s, (a.0 + 3., a.1 + 3.), t, 1.8);
    }
    fn label(&mut self, s: usize, p: Pt, n: &str) {
        self.label_dir(s, p, n, 0)
    }
    fn label_dir(&mut self, s: usize, p: Pt, n: &str, angle: i32) {
        let u = self.uid();
        self.pages[s]+=&format!("(global_label {} (shape bidirectional) (at {} {} {angle}) (effects (font (size 1.27 1.27)) (justify {})) (uuid {u}) {})\n",q(n),p.0*G,p.1*G,if angle==180 {"right"}else{"left"},prop("Intersheetrefs","${INTERSHEET_REFS}",(p.0,p.1),true));
    }
    fn power(&mut self, s: usize, p: Pt, n: &str) {
        let kind = if n == "GND" {
            "GND"
        } else if n.starts_with('-') {
            "VSS"
        } else {
            "VDD"
        };
        let reference = format!("#PWR{}", self.count + 1);
        let u = self.uid();
        let mut sym = self.syms[kind].clone();
        // Power symbols use their value as the global net name in KiCad 10.
        sym.text = sym.text.replace(&format!("\"{kind}\""), &q(n));
        let newkind = format!("PWR_{}", n.replace(['+', '-', '.'], "_"));
        sym.text = sym
            .text
            .replace(&format!("Probe:{kind}"), &format!("Probe:{newkind}"))
            .replace(&format!("{kind}_"), &format!("{newkind}_"));
        self.syms.insert(newkind.clone(), sym);
        let path = self.path(s);
        let dy = if n == "GND" {
            4.
        } else if n.starts_with('-') {
            4.
        } else {
            -4.
        };
        let rot = if n.starts_with('-') { 180 } else { 0 };
        self.pages[s]+=&format!("(symbol (lib_id {}) (at {} {} {rot}) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid {u}) {} {} (instances (project \"differential-probe\" (path {} (reference {}) (unit 1)))))\n",q(&format!("Probe:{newkind}")),p.0*G,p.1*G,prop("Reference",&reference,p,true),prop("Value",n,(p.0,p.1+dy),false),q(&path),q(&reference));
    }
    fn net(&mut self, s: usize, p: Pt, n: &str) {
        if ["GND", "+4V8", "-4V8", "+BAT", "-BAT"].contains(&n) {
            self.power(s, p, n)
        } else {
            self.label(s, p, n)
        }
    }
    fn path(&self, s: usize) -> String {
        if s == 0 {
            format!("/{}", id("root"))
        } else {
            format!("/{}/{}", id("root"), id(&format!("sheet{s}")))
        }
    }
    fn place(
        &mut self,
        s: usize,
        reference: &str,
        kind: &str,
        p: &Part,
        xy: Pt,
        rot: i32,
        dnp: bool,
        on_board: bool,
    ) {
        assert!(
            !self.placed.contains_key(reference),
            "duplicate {reference}"
        );
        let sym = self.syms[kind].clone();
        let (cx, cy) = xy;
        let angle = (rot as f64).to_radians();
        let mut pins = BTreeMap::new();
        for a in &sym.pins {
            let x = cx + a.p.0 * angle.cos() - a.p.1 * angle.sin();
            let y = cy - a.p.0 * angle.sin() - a.p.1 * angle.cos();
            pins.insert(
                a.n.clone(),
                (
                    (x.round_to_grid(), y.round_to_grid()),
                    (a.angle + rot) % 360,
                ),
            );
        }
        let small = kind == "R_Small_US"
            || kind == "C"
            || kind == "D"
            || kind == "D_Schottky"
            || kind == "LED";
        let (rp, vp) = if small && rot == 90 {
            ((cx, cy - 5.), (cx, cy - 3.))
        } else if ["D", "D_Schottky", "LED"].contains(&kind) {
            ((cx, cy - 5.), (cx, cy - 3.))
        } else if small {
            ((cx + 7., cy - 1.), (cx + 7., cy + 1.))
        } else if kind == "OPA2810" {
            ((cx - 12., cy - 22.), (cx - 12., cy - 20.))
        } else if kind == "BUTTON" {
            ((cx + 7., cy - 10.), (cx + 7., cy - 8.))
        } else {
            ((cx - 8., cy - sym.h - 5.), (cx - 8., cy - sym.h - 3.))
        };
        let mut properties =
            prop("Reference", reference, rp, false) + &prop("Value", &p.value, vp, false);
        if rot == 90 {
            properties = properties.replace(" 0) (effects", " 90) (effects");
        }
        for (k, v) in [
            ("Footprint", p.fp.as_str()),
            ("Datasheet", &p.url),
            ("MPN", &p.mpn),
            ("Manufacturer", &p.mfr),
            ("LCSC", &p.lcsc),
        ] {
            properties += &prop(k, v, xy, true)
        }
        let path = self.path(s);
        self.pages[s]+=&format!("(symbol (lib_id {}) (at {} {} {rot}) (unit 1) (in_bom yes) (on_board {}) (dnp {}) (uuid {}) {properties} (instances (project \"differential-probe\" (path {} (reference {}) (unit 1)))))\n",q(&format!("Probe:{kind}")),cx*G,cy*G,if on_board{"yes"}else{"no"},if dnp{"yes"}else{"no"},id(reference),q(&path),q(reference));
        self.placed
            .insert(reference.into(), Placed { pins, sheet: s });
    }
    fn point(&self, r: &str, n: &str) -> Pt {
        self.placed[r].pins[n].0
    }
    fn tag(&mut self, r: &str, n: &str, net: &str) {
        assert!(
            self.expected
                .insert((r.into(), n.into()), net.into())
                .is_none(),
            "duplicate tag {r}.{n}"
        );
    }
    fn link(&mut self, r: &str, n: &str, net: &str) {
        self.tag(r, n, net);
        let p = &self.placed[r];
        let s = p.sheet;
        let (xy, a) = p.pins[n];
        let rad = (a as f64).to_radians();
        let end = (xy.0 - 5. * rad.cos(), xy.1 + 5. * rad.sin());
        self.wire(s, xy, end);
        if ["GND", "+4V8", "-4V8", "+BAT", "-BAT"].contains(&net) {
            let wants_down = net == "GND" || net.starts_with('-');
            if (a == 270 && wants_down) || (a == 90 && !wants_down) {
                let p = (end.0 - 8., end.1);
                self.wire(s, end, p);
                self.power(s, p, net)
            } else {
                self.power(s, end, net)
            }
        } else {
            self.label_dir(s, end, net, if a == 0 { 180 } else { 0 });
        }
    }
    fn nc(&mut self, r: &str, n: &str) {
        self.tag(r, n, "NC");
        let s = self.placed[r].sheet;
        let p = self.point(r, n);
        let u = self.uid();
        self.pages[s] += &format!("(no_connect (at {} {}) (uuid {u}))\n", p.0 * G, p.1 * G);
    }
    fn two(
        &mut self,
        s: usize,
        r: &str,
        kind: &str,
        p: &Part,
        xy: Pt,
        rot: i32,
        a: &str,
        b: &str,
        dnp: bool,
    ) {
        self.place(s, r, kind, p, xy, rot, dnp, true);
        self.link(r, "1", a);
        self.link(r, "2", b);
    }
    fn amp_power(&mut self, r: &str) {
        self.link(r, "7", "+4V8");
        self.link(r, "4", "-4V8");
    }
    fn dual_power(&mut self, r: &str) {
        self.link(r, "8", "+4V8");
        self.link(r, "4", "-4V8");
    }
    fn finish(&self) {
        for (r, p) in &self.placed {
            for n in p.pins.keys() {
                assert!(
                    self.expected.contains_key(&(r.clone(), n.clone())),
                    "unassigned {r}.{n}"
                )
            }
        }
        let syms = self
            .syms
            .values()
            .map(|s| s.text.as_str())
            .collect::<Vec<_>>()
            .join("\n");
        let names = ["differential-probe", "signal", "power"];
        let titles = [
            "Differential probe / compensated inputs",
            "Differential probe / gain, output and overload",
            "Differential probe / battery supply and thresholds",
        ];
        for s in 0..3 {
            let mut body = self.pages[s].clone();
            if s == 0 {
                body += "(sheet_instances (path \"/\" (page \"1\")))";
                for j in 1..3 {
                    let x = if j == 1 { 190. } else { 250. };
                    body+=&format!("(sheet (at {} {}) (size {} {}) (stroke (width .254) (type default)) (fill (color 0 0 0 0)) (uuid {}) {} {} (instances (project \"differential-probe\" (path {} (page {})))))\n",x*G,182.*G,45.*G,10.*G,id(&format!("sheet{j}")),prop("Sheetname",names[j],(x,180.),false),prop("Sheetfile",&format!("{}.kicad_sch",names[j]),(x,194.),false),q(&format!("/{}",id("root"))),q(&(j+1).to_string()));
                }
            }
            fs::write(format!("cad/{}.kicad_sch",names[s]),format!("(kicad_sch (version 20250114) (generator \"temper_probe\") (uuid {}) (paper \"A3\") (title_block (title {}) (date \"2026-10-20\") (rev \"C prototype\") (company \"Temper / instruments\") (comment 1 \"Voltage ratings are qualification targets; not CAT rated\")) (lib_symbols {syms}) {body} (embedded_fonts no))\n",id(if s==0 {"root"} else {names[s]}),q(titles[s]))).unwrap();
        }
        let local = syms.replace("(symbol \"Probe:", "(symbol \"");
        fs::write(
            "cad/Probe.kicad_sym",
            format!("(kicad_symbol_lib (version 20241209) (generator \"temper_probe\") {local})\n"),
        )
        .unwrap();
        fs::write("cad/sym-lib-table","(sym_lib_table (version 7) (lib (name \"Probe\") (type \"KiCad\") (uri \"${KIPRJMOD}/Probe.kicad_sym\") (options \"\") (descr \"Datasheet-specific ICs and KiCad standard passives\")))\n").unwrap();
        if !std::path::Path::new("cad/differential-probe.kicad_pro").exists() {
            fs::write(
                "cad/differential-probe.kicad_pro",
                "{\"meta\": {\"filename\": \"differential-probe.kicad_pro\", \"version\": 1}}\n",
            )
            .unwrap();
        }
        let mut expected = "reference\tpin\tnet\n".to_string();
        for ((r, n), v) in &self.expected {
            expected += &format!("{r}\t{n}\t{v}\n");
        }
        fs::write("validation/expected-pins.tsv", expected).unwrap();
        let mut table="(fp_lib_table (version 7) (lib (name \"Probe\") (type \"KiCad\") (uri \"${KIPRJMOD}/Probe.pretty\") (options \"\") (descr \"Project HV, trimmer, board-edge and landing footprints\"))".to_string();
        for lib in [
            "Resistor_SMD",
            "Capacitor_SMD",
            "Package_SO",
            "Package_TO_SOT_SMD",
            "Potentiometer_THT",
            "Diode_SMD",
            "Button_Switch_SMD",
            "LED_SMD",
            "MountingHole",
        ] {
            table+=&format!("(lib (name {0}) (type \"KiCad\") (uri \"${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty\") (options \"\") (descr \"KiCad 10 standard library\"))",q(lib));
        }
        table += ")\n";
        fs::write("cad/fp-lib-table", table).unwrap();
        fs::create_dir_all("cad/Probe.pretty").unwrap();
        // The HV capacitor straddles a routed slot. Keep the body outline on
        // the assembly layer; printing it across the cutout is not useful.
        let cap = fs::read_to_string("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Capacitor_SMD.pretty/C_1812_4532Metric.kicad_mod").unwrap()
            .replacen("\"C_1812_4532Metric\"", "\"C_1812_HV_Slot\"", 1)
            .replace("(layer \"F.SilkS\")", "(layer \"F.Fab\")");
        fs::write("cad/Probe.pretty/C_1812_HV_Slot.kicad_mod", cap).unwrap();
        let trim_fp = r#"(footprint "GKG60015_TopAdjust" (version 20241229) (generator "temper_probe") (layer "F.Cu")
(descr "EW Electronics GKG60015; 6mm body, 5mm pitch, top adjust. Project pin1 STATOR right, pin2 ROTOR left. Drawing April2026.")
(attr through_hole)
(property "Reference" "CT" (at 0 -4.5) (layer "F.SilkS") (effects (font (size .8 .8) (thickness .12))))
(property "Value" "GKG60015" (at 0 4.5) (layer "F.Fab") (effects (font (size .8 .8) (thickness .12))))
(fp_circle (center 0 0) (end 3.1 0) (stroke (width .1) (type default)) (fill none) (layer "F.Fab"))
(fp_circle (center 0 0) (end 1.25 0) (stroke (width .1) (type default)) (fill none) (layer "F.Fab"))
(fp_rect (start -3.75 -3.5) (end 3.75 3.5) (stroke (width .05) (type default)) (fill none) (layer "F.CrtYd"))
(fp_line (start -1.5 -3.2) (end 1.5 -3.2) (stroke (width .12) (type default)) (layer "F.SilkS"))
(fp_line (start -1.5 3.2) (end 1.5 3.2) (stroke (width .12) (type default)) (layer "F.SilkS"))
(pad "1" thru_hole circle (at 2.5 0) (size 2 2) (drill 1.2) (layers "*.Cu" "*.Mask"))
(pad "2" thru_hole circle (at -2.5 0) (size 2 2) (drill 1.2) (layers "*.Cu" "*.Mask"))
(model "${KIPRJMOD}/Probe.3dshapes/GKG60015.wrl" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0))))
"#;
        fs::write("cad/Probe.pretty/GKG60015_TopAdjust.kicad_mod", trim_fp).unwrap();
        fs::create_dir_all("cad/Probe.3dshapes").unwrap();
        fs::write("cad/Probe.3dshapes/GKG60015.wrl", trimmer_model()).unwrap();
        let mut pins = "symbol\tpin\tname\telectrical_type\n".to_string();
        for (k, s) in &self.syms {
            for p in &s.pins {
                pins += &format!("{k}\t{}\t{}\t{}\n", p.n, p.name, p.typ)
            }
        }
        fs::write("validation/symbol-pins.tsv", pins).unwrap();
        println!(
            "Generated 3 sheets, {} components, {} assigned pins",
            self.placed.len(),
            self.expected.len()
        );
    }
}
trait Grid {
    fn round_to_grid(self) -> f64;
}
impl Grid for f64 {
    fn round_to_grid(self) -> f64 {
        (self * 1000.).round() / 1000.
    }
}
fn r(v: &str, code: &str) -> Part {
    part(
        v,
        &format!("RT0805BRD07{code}L"),
        "Yageo",
        "Resistor_SMD:R_0805_2012Metric",
        "https://www.yageo.com/en/Chart/Download/pdf/RT/RT0805",
        " ",
    )
}
fn c(v: &str, code: &str) -> Part {
    let m = if code == "010" {
        "C0805C109C5GACTU".into()
    } else {
        format!("C0805C{code}J5GACTU")
    };
    part(
        v,
        &m,
        "KEMET",
        "Capacitor_SMD:C_0805_2012Metric",
        &format!("https://search.kemet.com/download/specsheet/{m}"),
        "",
    )
}
fn c1(v: &str, code: &str) -> Part {
    let m = format!("C0805C{code}F5GACTU");
    part(
        v,
        &m,
        "KEMET",
        "Capacitor_SMD:C_0805_2012Metric",
        &format!("https://search.kemet.com/download/specsheet/{m}"),
        "",
    )
}
fn trimmer_model() -> String {
    // KiCad's VRML importer needs meshes rather than Cylinder primitives.
    // Models use 2.54 mm units. This is only the 6.2 mm maximum body envelope.
    let mut model =
        "#VRML V2.0 utf8\n# GKG60015 low-fidelity envelope; units 2.54mm.\n".to_string();
    let count = 32;
    for (radius, bottom, top, color) in [
        (3.1, 0., 4.5, ".35 .18 .07"),
        (1.25, 4.5, 5., ".65 .65 .65"),
    ] {
        model += &format!("Shape {{ appearance Appearance {{ material Material {{ diffuseColor {color} }} }} geometry IndexedFaceSet {{ solid TRUE coord Coordinate {{ point [\n");
        for z in [bottom, top] {
            for i in 0..count {
                let angle = i as f64 * 2. * std::f64::consts::PI / count as f64;
                model += &format!(
                    "{:.6} {:.6} {:.6},\n",
                    radius * angle.cos() / 2.54,
                    radius * angle.sin() / 2.54,
                    z / 2.54
                );
            }
        }
        model += "] } coordIndex [\n";
        for i in 0..count {
            let j = (i + 1) % count;
            model += &format!("{i}, {j}, {}, {}, -1,\n", j + count, i + count);
        }
        for i in (0..count).rev() {
            model += &format!("{i}, ");
        }
        model += "-1,\n";
        for i in count..count * 2 {
            model += &format!("{i}, ");
        }
        model += "-1\n] } }\n";
    }
    model += "Shape { appearance Appearance { material Material { diffuseColor .05 .05 .05 } } geometry IndexedFaceSet { solid FALSE coord Coordinate { point [-.433071 -.118110 1.969291, .433071 -.118110 1.969291, .433071 .118110 1.969291, -.433071 .118110 1.969291] } coordIndex [0,1,2,3,-1] } }\n";
    model
}
fn main() {
    assert!(
        Path::new("evidence").is_dir(),
        "run in instruments/differential-probe"
    );
    for d in ["cad", "validation", "previews", "docs"] {
        fs::create_dir_all(d).unwrap();
    }
    let mut d = Design::new();
    for (lib, k, p, h) in [
        (
            "Device",
            "R_Small_US",
            vec![
                pin("1", "", "passive", 0., 2., 270),
                pin("2", "", "passive", 0., -2., 90),
            ],
            2.,
        ),
        (
            "Device",
            "C",
            vec![
                pin("1", "", "passive", 0., 3., 270),
                pin("2", "", "passive", 0., -3., 90),
            ],
            3.,
        ),
        (
            "Device",
            "C_Trim",
            vec![
                pin("1", "", "passive", 0., 3., 270),
                pin("2", "", "passive", 0., -3., 90),
            ],
            3.,
        ),
        (
            "Device",
            "D",
            vec![
                pin("1", "K", "passive", -3., 0., 0),
                pin("2", "A", "passive", 3., 0., 180),
            ],
            2.,
        ),
        (
            "Device",
            "D_Schottky",
            vec![
                pin("1", "K", "passive", -3., 0., 0),
                pin("2", "A", "passive", 3., 0., 180),
            ],
            2.,
        ),
        (
            "Device",
            "LED",
            vec![
                pin("1", "K", "passive", -3., 0., 0),
                pin("2", "A", "passive", 3., 0., 180),
            ],
            2.,
        ),
        (
            "power",
            "GND",
            vec![pin("1", "GND", "power_in", 0., 0., 90)],
            2.,
        ),
        (
            "power",
            "VDD",
            vec![pin("1", "VDD", "power_in", 0., 0., 90)],
            2.,
        ),
        (
            "power",
            "VSS",
            vec![pin("1", "VSS", "power_in", 0., 0., 90)],
            2.,
        ),
    ] {
        d.syms.insert(k.into(), official(lib, k, p, h));
    }
    // One-unit block symbol for the dual OPA2810: SOIC-8/VSSOP-8 pin numbers.
    d.syms.insert(
        "OPA2810".into(),
        custom(
            "OPA2810",
            vec![
                pin("3", "+IN1", "input", -10., 12., 0),
                pin("2", "-IN1", "input", -10., 8., 0),
                pin("1", "OUT1", "output", 10., 10., 180),
                pin("5", "+IN2", "input", -10., -8., 0),
                pin("6", "-IN2", "input", -10., -12., 0),
                pin("7", "OUT2", "output", 10., -10., 180),
                pin("8", "V+", "power_in", 0., 18., 270),
                pin("4", "V-", "power_in", 0., -18., 90),
            ],
            8.,
            16.,
            false,
        ),
    );
    d.syms.insert(
        "OPA810".into(),
        custom(
            "OPA810",
            vec![
                pin("3", "+IN", "input", -8., 3., 0),
                pin("2", "-IN", "input", -8., -3., 0),
                pin("6", "OUT", "output", 8., 0., 180),
                pin("7", "V+", "power_in", 0., 10., 270),
                pin("4", "V-", "power_in", 0., -10., 90),
                pin("1", "NC", "no_connect", -4., -10., 90),
                pin("5", "NC", "no_connect", 4., -10., 90),
                pin("8", "NC", "no_connect", 8., -6., 180),
            ],
            6.,
            8.,
            true,
        ),
    );
    d.syms.insert(
        "BAV199".into(),
        custom(
            "BAV199",
            vec![
                pin("1", "A1", "passive", -7., -3., 0),
                pin("2", "K2", "passive", -7., 3., 0),
                pin("3", "K1/A2", "passive", 7., 0., 180),
            ],
            5.,
            5.,
            false,
        ),
    );
    d.syms.insert(
        "TRIM".into(),
        custom(
            "TRIM",
            vec![
                pin("1", "CCW", "passive", 0., 6., 270),
                pin("2", "WIPER", "passive", 6., 0., 180),
                pin("3", "CW", "passive", 0., -6., 90),
            ],
            4.,
            4.,
            false,
        ),
    );
    d.syms.insert(
        "DPDT".into(),
        custom(
            "DPDT",
            vec![
                pin("2", "COM1", "passive", -8., 4., 0),
                pin("5", "COM2", "passive", -8., -4., 0),
                pin("1", "A1", "passive", 8., 7., 180),
                pin("3", "B1", "passive", 8., 2., 180),
                pin("4", "A2", "passive", 8., -2., 180),
                pin("6", "B2", "passive", 8., -7., 180),
            ],
            6.,
            9.,
            false,
        ),
    );
    for (k, vin, gnd) in [("ADP7142", "1", "2"), ("ADP7182", "2", "1")] {
        d.syms.insert(
            k.into(),
            custom(
                k,
                vec![
                    pin(vin, "VIN", "power_in", -10., 4., 0),
                    pin("3", "EN", "input", -10., -3., 0),
                    pin("5", "VOUT", "power_out", 10., 4., 180),
                    pin("4", "ADJ", "input", 10., -3., 180),
                    pin(gnd, "GND", "power_in", 0., -9., 90),
                ],
                8.,
                7.,
                false,
            ),
        );
    }
    let mut ps = vec![
        pin("3", "V+", "power_in", 0., 18., 270),
        pin("12", "V-", "power_in", 0., -18., 90),
    ];
    for (i, (plus, minus, out)) in [
        ("5", "4", "2"),
        ("7", "6", "1"),
        ("9", "8", "14"),
        ("11", "10", "13"),
    ]
    .iter()
    .enumerate()
    {
        let y = 12. - i as f64 * 8.;
        ps.extend([
            pin(plus, &format!("{}IN+", i + 1), "input", -12., y, 0),
            pin(minus, &format!("{}IN-", i + 1), "input", -12., y - 3., 0),
            pin(
                out,
                &format!("{}OUT", i + 1),
                "open_collector",
                12.,
                y - 1.,
                180,
            ),
        ]);
    }
    d.syms
        .insert("TLV1704".into(), custom("TLV1704", ps, 10., 16., false));
    d.syms.insert(
        "TLV1702".into(),
        custom(
            "TLV1702",
            vec![
                pin("3", "1IN+", "input", -12., 5., 0),
                pin("2", "1IN-", "input", -12., 2., 0),
                pin("5", "2IN+", "input", -12., -3., 0),
                pin("6", "2IN-", "input", -12., -6., 0),
                pin("1", "1OUT", "open_collector", 12., 4., 180),
                pin("7", "2OUT", "open_collector", 12., -4., 180),
                pin("8", "V+", "power_in", 0., 12., 270),
                pin("4", "V-", "power_in", 0., -12., 90),
            ],
            10.,
            10.,
            false,
        ),
    );
    d.syms.insert(
        "CD4013".into(),
        custom(
            "CD4013",
            vec![
                pin("6", "SET1", "input", -12., 12., 0),
                pin("4", "RESET1", "input", -12., 8., 0),
                pin("5", "D1", "input", -12., 4., 0),
                pin("3", "CLK1", "input", -12., 0., 0),
                pin("8", "SET2", "input", -12., -4., 0),
                pin("10", "RESET2", "input", -12., -8., 0),
                pin("9", "D2", "input", -12., -12., 0),
                pin("11", "CLK2", "input", -12., -16., 0),
                pin("1", "Q1", "output", 12., 12., 180),
                pin("2", "/Q1", "output", 12., 8., 180),
                pin("13", "Q2", "output", 12., 0., 180),
                pin("12", "/Q2", "output", 12., -4., 180),
                pin("14", "VDD", "power_in", 0., 22., 270),
                pin("7", "VSS", "power_in", 0., -22., 90),
            ],
            10.,
            20.,
            false,
        ),
    );
    d.syms.insert(
        "PNP".into(),
        custom(
            "PNP",
            vec![
                pin("1", "B", "input", -6., 0., 0),
                pin("2", "E", "passive", 4., 6., 270),
                pin("3", "C", "passive", 4., -6., 90),
            ],
            4.,
            4.,
            false,
        ),
    );
    for (k, n) in [("PAD", 1), ("BNC", 2), ("BATTERY", 2), ("BUTTON", 2)] {
        let ps = (1..=n)
            .map(|i| {
                pin(
                    &i.to_string(),
                    &i.to_string(),
                    "passive",
                    -6.,
                    3. - (i - 1) as f64 * 6.,
                    0,
                )
            })
            .collect();
        d.syms.insert(k.into(), custom(k, ps, 4., 5., false));
    }
    // Rev C: one 2 MR body per compensated section (five per leg), replacing
    // Rev B's two series 1 MR bodies. Current Stackpole HVC catalog, 2512.
    let hv = part(
        "2 MR / 0.1%",
        "HVCB2512BDE2M00",
        "Stackpole",
        "Resistor_SMD:R_2512_6332Metric",
        "https://www.seielect.com/Catalog/SEI-hvc.pdf",
        "",
    );
    let hv_c = part(
        "33 pF / 3 kV",
        "C1812C330JHGACTU",
        "KEMET",
        "Probe:C_1812_HV_Slot",
        "https://search.kemet.com/download/specsheet/C1812C330JHGACTU",
        "",
    );
    let opa2 = part(
        "OPA2810IDR",
        "OPA2810IDR",
        "Texas Instruments",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "https://www.ti.com/lit/ds/symlink/opa2810.pdf",
        "C1849413",
    );
    let opa = part(
        "OPA810IDR",
        "OPA810IDR",
        "Texas Instruments",
        "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "https://www.ti.com/lit/ds/symlink/opa810.pdf",
        "C1852077",
    );
    let clamp = part(
        "BAV199,215",
        "BAV199,215",
        "Nexperia",
        "Package_TO_SOT_SMD:SOT-23",
        "https://assets.nexperia.com/documents/data-sheet/BAV199.pdf",
        "C40919",
    );
    let trim = part(
        "50 R / set 12.50 R",
        "3296W-1-500LF",
        "Bourns",
        "Potentiometer_THT:Potentiometer_Bourns_3296W_Vertical",
        "https://www.bourns.com/docs/product-datasheets/3296.pdf",
        "C83692",
    );
    let rp = part(
        "499 R / 0.01%",
        "RNCF0603TKY499R",
        "Stackpole",
        "Resistor_SMD:R_0603_1608Metric",
        "https://seielect.com/Catalog/SEI-RNCF.pdf",
        "",
    );
    let rp1k = part(
        "1.00 kR / 0.01%",
        "RNCF0603TKY1K00",
        "Stackpole",
        "Resistor_SMD:R_0603_1608Metric",
        "https://seielect.com/Catalog/SEI-RNCF.pdf",
        "",
    );
    let rp2k = part(
        "2.00 kR / 0.01%",
        "RNCF0603TKY2K00",
        "Stackpole",
        "Resistor_SMD:R_0603_1608Metric",
        "https://seielect.com/Catalog/SEI-RNCF.pdf",
        "",
    );
    let rf = part(
        "4.99 kR / 0.01%",
        "RNCF0603TKY4K99",
        "Stackpole",
        "Resistor_SMD:R_0603_1608Metric",
        "https://seielect.com/Catalog/SEI-RNCF.pdf",
        "C3942722",
    );
    let dec = part(
        "100 nF / 50 V",
        "C0805C104K5RACTU",
        "KEMET",
        "Capacitor_SMD:C_0805_2012Metric",
        "https://search.kemet.com/download/specsheet/C0805C104K5RACTU",
        "",
    );
    let bulk = part(
        "10 uF / 25 V",
        "C1210C106K3RACTU",
        "KEMET",
        "Capacitor_SMD:C_1210_3225Metric",
        "https://search.kemet.com/download/specsheet/C1210C106K3RACTU",
        "",
    );
    // Sheet 1: symmetrical five-section input dividers, one 2 MR body per section.
    d.text(
        0,
        (12., 10.),
        "2000:1 INPUTS  /  mirror-matched geometry about the inter-leg slot, fixed grounded shield",
        2.5,
    );
    for (row, suffix) in ["P", "N"].iter().enumerate() {
        let y = 48. + row as f64 * 70.;
        let base = row * 20;
        d.block(
            0,
            (10., 26. + row as f64 * 70.),
            (318., 87. + row as f64 * 70.),
            &format!("INPUT {suffix}  |  10 MR + 5.00250 kR  |  5 x (2 MR || 33 pF)"),
        );
        let tip = format!("TIP_{suffix}");
        d.label(0, (20., y), &tip);
        for i in 0..5 {
            let x = 22. + i as f64 * 36.;
            let a = if i == 0 {
                tip.clone()
            } else {
                format!("{suffix}_SEG{i}")
            };
            let b = if i == 4 {
                format!("TAP_{suffix}")
            } else {
                format!("{suffix}_SEG{}", i + 1)
            };
            let rr = format!("R{}", base + i + 1);
            let cr = format!("C{}", base + i + 1);
            d.place(0, &rr, "R_Small_US", &hv, (x + 18., y), 90, false, true);
            d.tag(&rr, "1", &a);
            d.tag(&rr, "2", &b);
            d.wire(0, (x, y), (x + 16., y));
            d.wire(0, (x + 20., y), (x + 36., y));
            d.place(0, &cr, "C", &hv_c, (x + 18., y + 12.), 90, false, true);
            d.tag(&cr, "1", &a);
            d.tag(&cr, "2", &b);
            d.wire(0, (x, y), (x, y + 12.));
            d.wire(0, (x, y + 12.), (x + 15., y + 12.));
            d.wire(0, (x + 21., y + 12.), (x + 36., y + 12.));
            d.wire(0, (x + 36., y + 12.), (x + 36., y));
            d.dot(0, (x + 36., y));
        }
        d.wire(0, (20., y), (22., y));
        d.label(0, (202., y), &format!("TAP_{suffix}"));
        let lr = format!("R{}", base + 11);
        let vr = format!("RV{}", row + 1);
        d.place(0, &lr, "R_Small_US", &rf, (212., y + 12.), 0, false, true);
        d.tag(&lr, "1", &format!("TAP_{suffix}"));
        d.tag(&lr, "2", &format!("TRIM_{suffix}"));
        d.wire(0, (202., y), (212., y));
        d.wire(0, (212., y), (212., y + 10.));
        d.place(0, &vr, "TRIM", &trim, (212., y + 26.), 0, false, true);
        d.tag(&vr, "1", &format!("TRIM_{suffix}"));
        d.tag(&vr, "2", "GND");
        d.tag(&vr, "3", "GND");
        d.wire(0, (212., y + 14.), (212., y + 20.));
        d.wire(0, (218., y + 26.), (224., y + 26.));
        d.wire(0, (224., y + 26.), (224., y + 34.));
        d.wire(0, (212., y + 32.), (212., y + 34.));
        d.wire(0, (212., y + 34.), (224., y + 34.));
        d.power(0, (212., y + 34.), "GND");
        let ir = format!("R{}", base + 12);
        d.two(
            0,
            &ir,
            "R_Small_US",
            &r("220 R", "220R"),
            (238., y),
            90,
            &format!("TAP_{suffix}"),
            &format!("IN_{suffix}"),
            false,
        );
        // Rail-referenced input clamps: pin 1 (A1) to -4V8, pin 2 (K2) to +4V8.
        let dr = format!("D{}", row + 1);
        d.place(0, &dr, "BAV199", &clamp, (255., y + 26.), 0, false, true);
        d.link(&dr, "1", "-4V8");
        d.link(&dr, "2", "+4V8");
        d.link(&dr, "3", &format!("IN_{suffix}"));
    }
    // One OPA2810 buffers both taps; it sits on the slot axis between the legs.
    d.place(0, "U1", "OPA2810", &opa2, (285., 118.), 0, false, true);
    for (p, n) in [
        ("3", "IN_P"),
        ("2", "BUF_P"),
        ("1", "BUF_P"),
        ("5", "IN_N"),
        ("6", "BUF_N"),
        ("7", "BUF_N"),
    ] {
        d.link("U1", p, n);
    }
    d.dual_power("U1");
    d.block(
        0,
        (10., 162.),
        (178., 215.),
        "AC COMPENSATION / fixed C0G + two select-on-test C0G + accessible fine trim",
    );
    let c10 = part(
        "10 nF / 1%",
        "C1206C103F5GACTU",
        "KEMET",
        "Capacitor_SMD:C_1206_3216Metric",
        "https://search.kemet.com/download/specsheet/C1206C103F5GACTU",
        "",
    );
    for (row, suf) in ["P", "N"].iter().enumerate() {
        let y = 179. + row as f64 * 23.;
        let tap = format!("TAP_{suf}");
        let cps = [
            c10.clone(),
            c1("SOT 3.0 nF / 1%", "302"),
            c1("SOT 160 pF / 1%", "161"),
        ];
        d.label(0, (20., y - 5.), &tap);
        d.power(0, (20., y + 5.), "GND");
        for (i, p) in cps.iter().enumerate() {
            let x = 24. + i as f64 * 22.;
            let cr = format!("C{}", 41 + row * 10 + i);
            d.place(0, &cr, "C", p, (x, y), 0, false, true);
            d.tag(&cr, "1", &tap);
            d.tag(&cr, "2", "GND");
            d.wire(0, (x, y - 3.), (x, y - 5.));
            d.wire(0, (x, y + 3.), (x, y + 5.));
            d.wire(0, (if i == 0 { 20. } else { x - 22. }, y - 5.), (x, y - 5.));
            d.wire(0, (if i == 0 { 20. } else { x - 22. }, y + 5.), (x, y + 5.));
            if i < 2 {
                d.dot(0, (x, y - 5.));
                d.dot(0, (x, y + 5.));
            }
        }
    }
    let ac_trim = part(
        "12-60 pF / set ~33 pF", "GKG60015", "EW Electronics",
        "Probe:GKG60015_TopAdjust",
        "https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8929/Gkgxxx15%20Specs%20and%20Kit-April%202026.pdf", "",
    );
    for (refdes, y, tap) in [("CT1", 171., "TAP_P"), ("CT2", 207., "TAP_N")] {
        d.two(
            0,
            refdes,
            "C_Trim",
            &ac_trim,
            (208., y),
            0,
            tap,
            "GND",
            false,
        );
    }
    d.text(0,(230.,165.),"Fixed 10 nF 1% + select-on-test S1 (E24 1.6-3.9 nF, 1%)\n+ S2 (E24 0-360 pF, 1%) + 12-60 pF trimmer.\nNominal 10 nF + 3.0 nF + 160 pF + ~33 pF.\nCT1/2: rotor to GND. Adjust through shield tool holes.\nTIP_P / TIP_N: captive HV leads.",1.27);
    // Sheet 2: subtraction, bandwidth limit, output clamp, latched overrange.
    d.text(
        1,
        (12., 10.),
        "1000:1 / 200:1 OUTPUT  /  scope input = 1 MR",
        2.5,
    );
    d.block(
        1,
        (10., 22.),
        (195., 106.),
        "FIXED x2 SUBTRACTOR / FIXED x5 GAIN / OUTPUT SELECTION",
    );
    // U3 is one OPA2810: channel 1 is the fixed x2 subtractor, channel 2 the
    // output driver. The possibly saturated x5 stage stays in its own OPA810.
    d.place(1, "U3", "OPA2810", &opa2, (82., 60.), 0, false, true);
    for (p, n) in [("3", "SUM_P"), ("2", "SUM_N"), ("1", "RAW_OUT")] {
        d.link("U3", p, n);
    }
    d.dual_power("U3");
    d.two(
        1,
        "R61",
        "R_Small_US",
        &rp,
        (30., 43.),
        90,
        "BUF_P",
        "SUM_P",
        false,
    );
    d.two(
        1,
        "R62",
        "R_Small_US",
        &rp,
        (30., 64.),
        90,
        "BUF_N",
        "SUM_N",
        false,
    );
    d.two(1, "R63", "R_Small_US", &rp1k, (42., 83.), 90, "SUM_P", "GND", false);
    d.two(
        1,
        "R65",
        "R_Small_US",
        &rp1k,
        (42., 99.),
        90,
        "SUM_N",
        "RAW_OUT",
        false,
    );
    d.place(1, "U12", "OPA810", &opa, (156., 56.), 0, false, true);
    d.amp_power("U12");
    for (p, n) in [("3", "GAIN5_IN"), ("2", "GAIN5_FB"), ("6", "FINE_OUT")] {
        d.link("U12", p, n);
    }
    for p in ["1", "5", "8"] {
        d.nc("U12", p);
    }
    d.two(
        1,
        "R100",
        "R_Small_US",
        &r("49.9 R", "49R9"),
        (118., 40.),
        90,
        "RAW_OUT",
        "GAIN5_IN",
        false,
    );
    d.two(1, "R67", "R_Small_US", &rp, (102., 98.), 0, "GAIN5_FB", "GND", false);
    d.two(
        1,
        "R68",
        "R_Small_US",
        &rp2k,
        (130., 90.),
        90,
        "GAIN5_FB",
        "FINE_OUT",
        false,
    );
    d.two(
        1,
        "R101",
        "R_Small_US",
        &r("49.9 R", "49R9"),
        (86., 30.),
        90,
        "RAW_OUT",
        "WIDE_SEL",
        false,
    );
    d.two(
        1,
        "R102",
        "R_Small_US",
        &r("49.9 R", "49R9"),
        (155., 30.),
        90,
        "FINE_OUT",
        "FINE_SEL",
        false,
    );
    d.place(1, "SW1", "SPDT", &switch, (230., 83.), 0, false, true);
    for (p, n) in [("1", "WIDE_SEL"), ("2", "SELECTED"), ("3", "FINE_SEL")] {
        d.link("SW1", p, n);
    }
    d.two(
        1,
        "R103",
        "R_Small_US",
        &r("1 MR", "1M"),
        (280., 97.),
        0,
        "SELECTED",
        "GND",
        false,
    );
    d.text(1,(15.,16.),"SW1 common (pin 2) selects 1 = 1000:1, 3 = 200:1. No switched feedback. Verify BBM contacts; allow settling during changes.",1.27);
    d.block(
        1,
        (200., 22.),
        (318., 106.),
        "SHARED FILTER / COAX DRIVER (U3 ch 2) / OUTPUT CLAMP",
    );
    d.two(
        1,
        "R69",
        "R_Small_US",
        &part(
            "97.6 R / 1%", "RC0805FR-0797R6L", "YAGEO",
            "Resistor_SMD:R_0805_2012Metric",
            "https://www.yageo.com/upload/media/product/productsearch/datasheet/rchip/PYu-RC_Group_51_RoHS_L.pdf",
            "C483266",
        ),
        (219., 44.),
        90,
        "SELECTED",
        "FILTER",
        false,
    );
    d.two(
        1,
        "C61",
        "C",
        &c("180 pF", "181"),
        (231., 61.),
        0,
        "FILTER",
        "GND",
        false,
    );
    d.link("U3", "5", "FILTER");
    d.link("U3", "6", "DRIVE");
    d.link("U3", "7", "DRIVE");
    d.two(
        1,
        "R70",
        "R_Small_US",
        &r("49.9 R", "49R9"),
        (294., 47.),
        90,
        "DRIVE",
        "OUT",
        false,
    );
    d.place(1, "D3", "BAV199", &clamp, (267., 88.), 0, false, true);
    for (p, n) in [("1", "-4V8"), ("2", "+4V8"), ("3", "OUT")] {
        d.link("D3", p, n)
    }
    let bnc = part(
        "BNC / panel / 50 R",
        "31-221-RFX",
        "Amphenol RF",
        "",
        "https://www.amphenolrf.com/31-221-rfx.html",
        "",
    );
    d.place(1, "J3", "BNC", &bnc, (306., 86.), 0, false, false);
    d.link("J3", "1", "OUT");
    d.link("J3", "2", "GND");
    d.block(
        1,
        (10., 112.),
        (194., 209.),
        "OPERATING-LIMIT WARNING / tips ~1406 V; selected signal ~1.266 V",
    );
    let quad = part(
        "TLV1704AIPWR",
        "TLV1704AIPWR",
        "Texas Instruments",
        "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
        "https://www.ti.com/lit/ds/symlink/tlv1704.pdf",
        "C181596",
    );
    d.place(1, "U5", "TLV1704", &quad, (50., 151.), 0, false, true);
    for (p, n) in [
        ("3", "+4V8"),
        ("12", "-4V8"),
        ("5", "LIM_P"),
        ("4", "BUF_P"),
        ("7", "BUF_P"),
        ("6", "LIM_N"),
        ("9", "LIM_P"),
        ("8", "BUF_N"),
        ("11", "BUF_N"),
        ("10", "LIM_N"),
        ("2", "OV_N"),
        ("1", "OV_N"),
        ("14", "OV_N"),
        ("13", "OV_N"),
    ] {
        d.link("U5", p, n)
    }
    let dual = part(
        "TLV1702AIDGKR",
        "TLV1702AIDGKR",
        "Texas Instruments",
        "Package_SO:VSSOP-8_3x3mm_P0.65mm",
        "https://www.ti.com/lit/ds/symlink/tlv1704.pdf",
        "C2870937",
    );
    d.place(1, "U6", "TLV1702", &dual, (133., 151.), 0, false, true);
    for (p, n) in [
        ("8", "+4V8"),
        ("4", "-4V8"),
        ("3", "OUT_LIM_P"),
        ("2", "OUT_HALF"),
        ("5", "OUT_HALF"),
        ("6", "OUT_LIM_N"),
        ("1", "OV_N"),
        ("7", "OV_N"),
    ] {
        d.link("U6", p, n)
    }
    d.two(
        1,
        "R71",
        "R_Small_US",
        &r("10 kR", "10K"),
        (110., 187.),
        90,
        "SELECTED",
        "OUT_HALF",
        false,
    );
    d.two(
        1,
        "R72",
        "R_Small_US",
        &r("10 kR", "10K"),
        (150., 187.),
        90,
        "OUT_HALF",
        "GND",
        false,
    );
    d.text(1,(18.,194.),"TLV170x: 560 ns typical delay. Indicator is not a fast peak detector.\nUnused x5 stage may saturate in 1000:1 range; selected signal alone drives output warning.",1.27);
    d.block(1, (200., 112.), (318., 196.), "LATCHED OVERLOAD / RESET");
    d.two(
        1,
        "R73",
        "R_Small_US",
        &r("10 kR", "10K"),
        (216., 130.),
        0,
        "+4V8",
        "OV_N",
        false,
    );
    d.two(
        1,
        "R74",
        "R_Small_US",
        &r("47 kR", "47K"),
        (216., 157.),
        90,
        "OV_N",
        "Q_BASE",
        false,
    );
    let pnp = part(
        "MMBT3906,215",
        "MMBT3906,215",
        "Nexperia",
        "Package_TO_SOT_SMD:SOT-23",
        "https://assets.nexperia.com/documents/data-sheet/MMBT3906.pdf",
        "",
    );
    d.place(1, "Q1", "PNP", &pnp, (238., 146.), 0, false, true);
    for (p, n) in [("1", "Q_BASE"), ("2", "+4V8"), ("3", "SET")] {
        d.link("Q1", p, n)
    }
    d.two(
        1,
        "R75",
        "R_Small_US",
        &r("10 kR", "10K"),
        (238., 175.),
        0,
        "SET",
        "-4V8",
        false,
    );
    let ff = part(
        "CD4013BM96",
        "CD4013BM96",
        "Texas Instruments",
        "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
        "https://www.ti.com/lit/ds/symlink/cd4013b.pdf",
        "C13527",
    );
    d.place(1, "U7", "CD4013", &ff, (283., 161.), 0, false, true);
    for (p, n) in [
        ("14", "+4V8"),
        ("7", "-4V8"),
        ("6", "SET"),
        ("4", "RESET"),
        ("10", "+4V8"),
        ("1", "OV_LED"),
    ] {
        d.link("U7", p, n)
    }
    for p in ["2", "13", "12"] {
        d.nc("U7", p)
    }
    for p in ["5", "3", "8", "9", "11"] {
        d.tag("U7", p, "-4V8");
        let xy = d.point("U7", p);
        d.wire(1, xy, (260., xy.1));
    }
    d.wire(1, (260., 157.), (260., 181.));
    for y in [161., 165., 173., 177.] {
        d.dot(1, (260., y));
    }
    d.power(1, (260., 181.), "-4V8");
    d.text(
        1,
        (205., 190.),
        "Reset / LED on power sheet. Verify both rails first.",
        1.27,
    );
    // Sheet 3: battery supply, decoupling, rail-referenced thresholds, latch UI.
    d.text(
        2,
        (12., 10.),
        "BATTERY POWER  /  scope shield defines circuit ground",
        2.5,
    );
    d.block(
        2,
        (10., 22.),
        (194., 124.),
        "TWO 9 V BATTERIES / +/-4.8 V LOW-NOISE RAILS",
    );
    let bat = part(
        "9 V battery clip",
        "235",
        "Keystone Electronics",
        "",
        "https://www.keyelco.com/product.cfm/product_id/911",
        "",
    );
    for (rr, xy, a, b) in [
        ("BT1", (28., 45.), "BAT_P", "GND"),
        ("BT2", (28., 91.), "GND", "BAT_N"),
    ] {
        d.place(2, rr, "BATTERY", &bat, xy, 0, false, false);
        d.link(rr, "1", a);
        d.link(rr, "2", b)
    }
    let power_switch = part(
        "POWER / DPDT / 5 A",
        "7201SYZQE",
        "C&K",
        "",
        "https://www.ckswitches.com/media/1422/7000.pdf",
        "",
    );
    d.place(2, "SW2", "DPDT", &power_switch, (57., 71.), 0, false, false);
    for (p, n) in [("2", "BAT_P"), ("5", "BAT_N"), ("1", "SW_P"), ("4", "SW_N")] {
        d.link("SW2", p, n)
    }
    d.nc("SW2", "3");
    d.nc("SW2", "6");
    let sch = part(
        "SS14",
        "SS14",
        "MDD (Microdiode Semiconductor)",
        "Diode_SMD:D_SMA",
        "https://www.lcsc.com/product-detail/C2480.html",
        "C2480",
    );
    d.two(
        2,
        "D4",
        "D_Schottky",
        &sch,
        (86., 45.),
        0,
        "+BAT",
        "SW_P",
        false,
    );
    d.two(
        2,
        "D5",
        "D_Schottky",
        &sch,
        (86., 93.),
        0,
        "SW_N",
        "-BAT",
        false,
    );
    for (i, (k, mpn, net, vin, gnd, y, top)) in [
        (
            "ADP7142",
            "ADP7142AUJZ-R7",
            "+4V8",
            "1",
            "2",
            47.,
            r("30 kR", "30K"),
        ),
        (
            "ADP7182",
            "ADP7182AUJZ-R7",
            "-4V8",
            "2",
            "1",
            90.,
            r("29.4 kR", "29K4"),
        ),
    ]
    .iter()
    .enumerate()
    {
        let ur = format!("U{}", i + 8);
        let input = if i == 0 { "+BAT" } else { "-BAT" };
        let adj = format!("ADJ_{}", i);
        let p = part(
            mpn,
            mpn,
            "Analog Devices",
            "Package_TO_SOT_SMD:TSOT-23-5",
            &format!("https://www.analog.com/media/en/technical-documentation/data-sheets/{k}.pdf"),
            if i == 0 { "C514356" } else { "C514358" },
        );
        d.place(2, &ur, k, &p, (131., *y), 0, false, true);
        for (pn, nn) in [
            (*vin, input),
            ("3", input),
            ("5", *net),
            ("4", adj.as_str()),
            (*gnd, "GND"),
        ] {
            d.link(&ur, pn, nn)
        }
        d.two(
            2,
            &format!("C{}", 71 + i * 2),
            "C",
            &bulk,
            (104., *y + 19.),
            0,
            input,
            "GND",
            false,
        );
        d.two(
            2,
            &format!("C{}", 72 + i * 2),
            "C",
            &bulk,
            (179., *y),
            0,
            net,
            "GND",
            false,
        );
        d.two(
            2,
            &format!("R{}", 81 + i * 2),
            "R_Small_US",
            top,
            (156., *y + 15.),
            0,
            net,
            &adj,
            false,
        );
        d.two(
            2,
            &format!("R{}", 82 + i * 2),
            "R_Small_US",
            &r("10 kR", "10K"),
            (176., *y + 23.),
            0,
            &adj,
            "GND",
            false,
        );
    }
    d.block(
        2,
        (200., 22.),
        (318., 124.),
        "RAIL-REFERENCED COMPARATOR THRESHOLDS (no shunt references)",
    );
    // One three-resistor ladder per polarity: rail - 66.5k - LIM - 1k - OUT_LIM - 10k - GND.
    for (i, (rail, lim, out_lim, y)) in [
        ("+4V8", "LIM_P", "OUT_LIM_P", 40.),
        ("-4V8", "LIM_N", "OUT_LIM_N", 90.),
    ]
    .iter()
    .enumerate()
    {
        let x = 240. + i as f64 * 40.;
        let base = 87 + i * 4;
        d.two(2, &format!("R{base}"), "R_Small_US", &r("66.5 kR", "66K5"), (x, *y - 12.), 0, rail, lim, false);
        d.two(2, &format!("R{}", base + 1), "R_Small_US", &r("1 kR", "1K"), (x, *y), 0, lim, out_lim, false);
        d.two(2, &format!("R{}", base + 2), "R_Small_US", &r("10 kR", "10K"), (x, *y + 12.), 0, out_lim, "GND", false);
    }
    d.text(2,(205.,112.),"Thresholds track the LDO rails; budget in tools/check.rs.\nInput clamps D1-D3 return to the rails; rail load absorbs clamp current.",1.27);
    d.block(
        2,
        (10., 130.),
        (194., 209.),
        "LOCAL DECOUPLING / RAIL REVERSAL DIODES",
    );
    for (i, u) in ["U1", "U3", "U12", "U5", "U6", "U7"].iter().enumerate() {
        let x = 23. + i as f64 * 25.;
        d.text(2, (x + 2., 142.), u, 1.27);
        for (j, (y, a, b)) in [(153., "+4V8", "GND"), (179., "GND", "-4V8")]
            .iter()
            .enumerate()
        {
            let cr = format!("C{}", 81 + i * 2 + j);
            d.place(2, &cr, "C", &dec, (x, *y), 0, false, true);
            d.tag(&cr, "1", a);
            d.tag(&cr, "2", b);
            let top = if j == 0 { 144. } else { 166. };
            let bottom = if j == 0 { 166. } else { 190. };
            d.wire(2, (x, *y - 3.), (x, top));
            d.wire(2, (x, *y + 3.), (x, bottom));
        }
        if i > 0 {
            for y in [144., 166., 190.] {
                d.wire(2, (x - 25., y), (x, y));
                if i < 5 {
                    d.dot(2, (x, y));
                }
            }
        }
    }
    d.power(2, (23., 144.), "+4V8");
    d.power(2, (23., 190.), "-4V8");
    d.wire(2, (23., 166.), (16., 166.));
    d.power(2, (16., 166.), "GND");
    d.two(
        2,
        "D6",
        "D_Schottky",
        &sch,
        (50., 201.),
        0,
        "+4V8",
        "GND",
        false,
    );
    d.two(
        2,
        "D7",
        "D_Schottky",
        &sch,
        (125., 201.),
        0,
        "GND",
        "-4V8",
        false,
    );
    d.block(
        2,
        (200., 130.),
        (318., 196.),
        "RESET / STATUS / POWER VALIDATION",
    );
    let button = part(
        "RESET / NO",
        "PTS645SL43SMTR92 LFS",
        "C&K",
        "Button_Switch_SMD:SW_SPST_PTS645Sx43SMTR92",
        "https://www.ckswitches.com/media/1471/pts645.pdf",
        "",
    );
    d.place(2, "SW3", "BUTTON", &button, (220., 154.), 0, false, true);
    d.link("SW3", "1", "+4V8");
    d.link("SW3", "2", "RESET");
    d.two(
        2,
        "R95",
        "R_Small_US",
        &r("100 kR", "100K"),
        (250., 154.),
        0,
        "RESET",
        "-4V8",
        false,
    );
    d.two(2, "C95", "C", &dec, (277., 154.), 0, "+4V8", "RESET", false);
    let small_d = part(
        "1N4148W-E3-18",
        "1N4148W-E3-18",
        "Vishay",
        "Diode_SMD:D_SOD-123",
        "https://www.vishay.com/docs/85748/1n4148w.pdf",
        "C191428",
    );
    d.two(
        2,
        "D8",
        "D",
        &small_d,
        (304., 154.),
        90,
        "RESET",
        "-4V8",
        false,
    );
    let led = part(
        "RED / OVERLOAD",
        "LTST-C170KRKT",
        "Lite-On",
        "LED_SMD:LED_0805_2012Metric",
        "https://optoelectronics.liteon.com/upload/download/DS22-2000-073/LTST-C170KRKT.pdf",
        "",
    );
    d.two(
        2,
        "R96",
        "R_Small_US",
        &r("10 kR", "10K"),
        (219., 175.),
        90,
        "OV_LED",
        "LED_A",
        false,
    );
    d.two(
        2,
        "D9",
        "LED",
        &led,
        (265., 175.),
        0,
        "-4V8",
        "LED_A",
        false,
    );
    d.text(2,(205.,184.),"Two 9 V alkaline batteries; center tap = GND.\nVerify rails, reset, then connect DUT.\nNo charging / USB connection during measurement.",1.27);
    // Power flags only on the battery-fed rails and the center-tap return.
    let flag = official(
        "power",
        "PWR_FLAG",
        vec![pin("1", "pwr", "power_out", 0., 0., 90)],
        2.,
    );
    d.syms.insert("PWR_FLAG".into(), flag);
    for (i, (xy, net)) in [
        ((73., 36.), "+BAT"),
        ((73., 112.), "-BAT"),
        ((36., 70.), "GND"),
    ]
    .iter()
    .enumerate()
    {
        let u = d.uid();
        d.pages[2]+=&format!("(symbol (lib_id \"Probe:PWR_FLAG\") (at {} {} 0) (unit 1) (in_bom no) (on_board no) (uuid {u}) {} {} (instances (project \"differential-probe\" (path {} (reference {}) (unit 1)))))",xy.0*G,xy.1*G,prop("Reference",&format!("#FLG{}",i+1),*xy,true),prop("Value","PWR_FLAG",(xy.0,xy.1-3.),true),q(&format!("/{}/{}",id("root"),id("sheet2"))),q(&format!("#FLG{}",i+1)));
        d.wire(2, *xy, (xy.0, xy.1 + 2.));
        d.net(2, (xy.0, xy.1 + 2.), net);
    }
    d.finish();
}

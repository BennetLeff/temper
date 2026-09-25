//! Isolated schematic authoring fixture. Native KiCad export is connectivity authority.
use std::{collections::BTreeMap, error::Error, fs};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
#[derive(Clone)]
struct Pin {
    n: &'static str,
    name: &'static str,
    x: f64,
    y: f64,
    a: i32,
    kind: &'static str,
}
fn p(n: &'static str, name: &'static str, x: f64, y: f64, a: i32, kind: &'static str) -> Pin {
    Pin {
        n,
        name,
        x,
        y,
        a,
        kind,
    }
}
fn q(s: &str) -> String {
    format!(
        "\"{}\"",
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
    )
}
fn block(s: &str, start: usize) -> Result<&str> {
    let (mut depth, mut quoted, mut escape) = (0, false, false);
    for (i, c) in s[start..].char_indices() {
        if escape {
            escape = false;
            continue;
        }
        if quoted && c == '\\' {
            escape = true;
            continue;
        }
        if c == '"' {
            quoted = !quoted;
        }
        if !quoted {
            if c == '(' {
                depth += 1
            }
            if c == ')' {
                depth -= 1;
                if depth == 0 {
                    return Ok(&s[start..start + i + 1]);
                }
            }
        }
    }
    Err("unclosed s-expression".into())
}
// Snap sheet coordinates, not library geometry, to the 50 mil connection grid.
fn snap_sheet(s: &str) -> String {
    let mut out = String::new();
    let mut rest = s;
    while let Some((i, prefix)) = ["(at ", "(xy ", "(start ", "(end "]
        .iter()
        .filter_map(|p| rest.find(p).map(|i| (i, *p)))
        .min_by_key(|v| v.0)
    {
        out.push_str(&rest[..i + prefix.len()]);
        rest = &rest[i + prefix.len()..];
        for _ in 0..2 {
            let end = rest.find([' ', ')']).unwrap();
            let n: f64 = rest[..end].parse().expect("sheet coordinate");
            out.push_str(&format!("{:.4}", (n / 1.27).round() * 1.27));
            out.push_str(&rest[end..end + 1]);
            rest = &rest[end + 1..];
        }
    }
    out.push_str(rest);
    out
}
struct Sch {
    name: String,
    root: String,
    seq: u32,
    lib: BTreeMap<String, String>,
    body: Vec<String>,
    expected: Vec<String>,
    count: usize,
}
impl Sch {
    fn new(name: &str) -> Self {
        Self {
            name: name.into(),
            root: format!(
                "16000000-0000-4000-8000-{:012}",
                if name == "clamp" { 1 } else { 2 }
            ),
            seq: 10,
            lib: BTreeMap::new(),
            body: vec![],
            expected: vec![],
            count: 0,
        }
    }
    fn id(&mut self) -> String {
        self.seq += 1;
        format!("16000000-0000-4000-8000-{:012}", self.seq)
    }
    fn wire(&mut self, a: (f64, f64), b: (f64, f64)) {
        if a == b {
            return;
        }
        let id = self.id();
        self.body.push(format!(
            "(wire (pts (xy {} {}) (xy {} {})) (stroke (width 0) (type default)) (uuid {id}))",
            a.0, a.1, b.0, b.1
        ));
    }
    fn label(&mut self, n: &str, x: f64, y: f64, right: bool) {
        let id = self.id();
        self.body.push(format!("(label {} (at {x} {y} {}) (effects (font (size 1.27 1.27)) (justify {} bottom)) (uuid {id}))",q(n),if right{0}else{180},if right{"left"}else{"right"}));
    }
    fn note(&mut self, s: &str, x: f64, y: f64, size: f64) {
        let id = self.id();
        self.body.push(format!("(text {} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid {id}))",q(s)));
    }
    fn panel(&mut self, title: &str, x: f64, y: f64, w: f64, h: f64) {
        let id = self.id();
        self.body.push(format!("(rectangle (start {x} {y}) (end {} {}) (stroke (width 0.3) (type default) (color 40 95 130 1)) (fill (type none)) (uuid {id}))",x+w,y+h));
        self.note(title, x + 3., y + 4., 1.8);
    }
    fn standard(&mut self, library: &str, name: &str) -> Result<String> {
        let id = format!("{library}:{name}");
        if !self.lib.contains_key(&id) {
            let text = fs::read_to_string(format!(
                "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/{library}.kicad_sym"
            ))?;
            let search = format!("(symbol \"{name}\"");
            let start = text.find(&search).ok_or("symbol missing")?;
            let symbol = block(&text, start)?.replacen(&search, &format!("(symbol {}", q(&id)), 1);
            self.lib.insert(id.clone(), symbol);
        }
        Ok(id)
    }
    fn custom(&mut self, name: &str, pins: &[Pin], w: f64, h: f64) -> String {
        let id = format!("Temper16:{name}");
        if self.lib.contains_key(&id) {
            return id;
        }
        let mut s=format!("(symbol {} (pin_names (offset 0.8)) (in_bom yes) (on_board yes) (property \"Reference\" \"U\" (at 0 0 0) (effects (font (size 1.27 1.27)))) (property \"Value\" {} (at 0 0 0) (effects (font (size 1.27 1.27)))) (symbol \"{name}_0_1\" (rectangle (start {} {}) (end {} {}) (stroke (width 0.254) (type default)) (fill (type background)))) (symbol \"{name}_1_1\"",q(&id),q(name),-w/2.,h/2.,w/2.,-h/2.);
        for t in pins {
            s+=&format!("(pin {} line (at {} {} {}) (length 2.54) (name {} (effects (font (size 1.0 1.0)))) (number {} (effects (font (size 1.0 1.0)))))",t.kind,t.x,t.y,t.a,q(t.name),q(t.n));
        }
        s += "))";
        self.lib.insert(id.clone(), s);
        id
    }
    fn instance(
        &mut self,
        reference: &str,
        value: &str,
        lib: &str,
        x: f64,
        y: f64,
        fp: &str,
        dy: f64,
    ) {
        let id = self.id();
        let fx = if reference.starts_with(['U', 'Q']) {
            x + 24.
        } else {
            x
        };
        let fy = if self.name == "reset" && reference == "U4" {
            30.
        } else {
            y - dy
        };
        let fx = if self.name == "reset" && reference == "U4" {
            x
        } else {
            fx
        };
        self.body.push(format!("(symbol (lib_id {}) (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid {id}) (property \"Reference\" {} (at {x} {} 0) (effects (font (size 1.27 1.27)))) (property \"Value\" {} (at {x} {} 0) (effects (font (size 1.27 1.27)))) (property \"Footprint\" {} (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide)) (instances (project {} (path {} (reference {}) (unit 1)))))",q(lib),q(reference),y-dy,q(value),y-dy+2.54,q(fp),q(&self.name),q(&format!("/{}",self.root)),q(reference)));
        let last = self.body.last_mut().unwrap();
        *last = last
            .replace(
                &format!("(at {x} {} 0)", y - dy),
                &format!("(at {fx} {fy} 0)"),
            )
            .replace(
                &format!("(at {x} {} 0)", y - dy + 2.54),
                &format!("(at {fx} {} 0)", fy + 2.54),
            );
        self.count += 1;
    }
    fn terminal(&mut self, r: &str, pin: &Pin, x: f64, y: f64, net: &str) {
        let (a, b) = (x + pin.x, y - pin.y);
        self.expected.push(format!("{r}\t{}\t{net}", pin.n));
        if net == "NC" {
            let id = self.id();
            self.body
                .push(format!("(no_connect (at {a} {b}) (uuid {id}))"));
            return;
        }
        if self.name == "reset" && (r.starts_with('C') || (r.starts_with('R') && pin.n == "2")) {
            return;
        }
        if self.name == "reset"
            && ((r == "U4" && ["2", "8", "9", "15"].contains(&pin.n))
                || (r == "U3" && ["2", "4", "10", "11", "12", "13"].contains(&pin.n))
                || (r == "U6" && ["4", "10", "12"].contains(&pin.n)))
        {
            return;
        }
        if self.name == "clamp" && !(r == "U1" && ["2", "3", "6", "10", "11"].contains(&pin.n)) {
            return;
        }
        let mut end = match pin.a {
            0 => (a - 7.62, b),
            180 => (a + 7.62, b),
            270 => (a, b - 5.08),
            _ => (a, b + 5.08),
        };
        if self.name == "clamp" && r == "U1" && pin.n == "2" {
            end.0 = 170.;
        }
        self.wire((a, b), end);
        if net.ends_with("GND")
            || ["AUX_RAW", "AUX_PROTECTED", "SELV3V3", "HOT_LOGIC5"].contains(&net)
        {
            self.power(net, end.0, end.1);
        } else {
            self.label(net, end.0, end.1, pin.a != 0);
        }
    }
    fn power(&mut self, net: &str, x: f64, y: f64) {
        let ground = net.ends_with("GND");
        let name = format!("PWR_{net}");
        let lib = format!("Temper16:{name}");
        let shape = if ground {
            "(polyline (pts (xy -1.27 0) (xy 1.27 0) (xy 0 -1.27) (xy -1.27 0)) (stroke (width 0.254) (type default)) (fill (type none)))"
        } else {
            "(polyline (pts (xy 0 0) (xy 0 2.54) (xy -1.27 1.27) (xy 0 2.54) (xy 1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))"
        };
        self.lib.entry(lib.clone()).or_insert_with(||format!("(symbol {} (power) (pin_names (offset 0) hide) (pin_numbers hide) (in_bom no) (on_board no) (property \"Reference\" \"#PWR\" (at 0 0 0) (effects (font (size 1.27 1.27)) hide)) (property \"Value\" {} (at 0 0 0) (effects (font (size 1.27 1.27)))) (symbol \"{name}_0_1\" {shape}) (symbol \"{name}_1_1\" (pin power_in line (at 0 0 90) (length 0) (name {} (effects (font (size 1.27 1.27)))) (number \"1\" (effects (font (size 1.27 1.27)))))))",q(&lib),q(net),q(net)));
        let id = self.id();
        let r = format!("#PWR{}", self.seq);
        let ty = if ground { y + 3.2 } else { y - 4.0 };
        self.body.push(format!("(symbol (lib_id {}) (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (uuid {id}) (property \"Reference\" {} (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide)) (property \"Value\" {} (at {x} {ty} 0) (effects (font (size 1.27 1.27)))) (instances (project {} (path {} (reference {}) (unit 1)))))",q(&lib),q(&r),q(net),q(&self.name),q(&format!("/{}",self.root)),q(&r)));
    }
    fn path(&mut self, points: &[(f64, f64)]) {
        for segment in points.windows(2) {
            self.wire(segment[0], segment[1]);
        }
    }
    fn junction(&mut self, x: f64, y: f64) {
        let id = self.id();
        self.body.push(format!(
            "(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid {id}))"
        ));
    }
    fn ic(
        &mut self,
        r: &str,
        v: &str,
        pins: &[Pin],
        nets: &[&str],
        x: f64,
        y: f64,
        w: f64,
        h: f64,
        fp: &str,
    ) {
        let lib = self.custom(&v.replace(['#', '-'], "_"), pins, w, h);
        self.instance(r, v, &lib, x, y, fp, h / 2. + 6.);
        for (pin, net) in pins.iter().zip(nets) {
            self.terminal(r, pin, x, y, net)
        }
    }
    fn passive(
        &mut self,
        r: &str,
        v: &str,
        typ: &str,
        x: f64,
        y: f64,
        a: &str,
        b: &str,
    ) -> Result<()> {
        let lib = self.standard("Device", typ)?;
        let d = if typ == "R_Small_US" { 2.54 } else { 3.81 };
        let fp = if r == "C4" && self.name == "clamp" {
            "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"
        } else if typ == "R_Small_US" {
            "Resistor_SMD:R_0805_2012Metric"
        } else {
            "Capacitor_SMD:C_1206_3216Metric"
        };
        self.instance(r, v, &lib, x + 0., y, fp, 6.5);
        // Place passive fields beside the symbol, clear of vertical wires.
        if let Some(last) = self.body.last_mut() {
            *last = last
                .replace(
                    &format!("(at {x} {} 0)", y - 6.5),
                    &format!("(at {} {} 0)", x + 14., y - 1.3),
                )
                .replace(
                    &format!("(at {x} {} 0)", y - 6.5 + 2.54),
                    &format!("(at {} {} 0)", x + 14., y + 1.3),
                );
        }
        let pins = [
            p("1", "", 0., d, 270, "passive"),
            p("2", "", 0., -d, 90, "passive"),
        ];
        self.terminal(r, &pins[0], x, y, a);
        self.terminal(r, &pins[1], x, y, b);
        Ok(())
    }
    fn save(&self) -> Result<()> {
        let head=format!("(kicad_sch (version 20250114) (generator \"eeschema\") (uuid {}) (paper \"A3\") (title_block (title {}) (date \"2026-09-22\") (rev \"16-prototype\") (comment 1 \"Review fixture - not production or hardware qualification\")) (lib_symbols {} )\n",self.root,q(&format!("Temper / {} interface fixture",self.name)),self.lib.values().cloned().collect::<Vec<_>>().join("\n"));
        fs::write(
            format!("{}.kicad_sch", self.name),
            head + &snap_sheet(&self.body.join("\n")) + "\n)\n",
        )?;
        fs::write(
            format!("{}-expected.tsv", self.name),
            self.expected.join("\n") + "\n",
        )?;
        println!("{}: {} component instances", self.name, self.count);
        let mut own = String::from(
            "(kicad_symbol_lib (version 20241209) (generator \"kicad_symbol_editor\")\n",
        );
        for (id, symbol) in &self.lib {
            if let Some(name) = id.strip_prefix("Temper16:") {
                own += &symbol.replacen(&q(id), &q(name), 1);
            }
        }
        own += ")\n";
        fs::write(format!("{}-symbols.kicad_sym", self.name), own)?;
        fs::write(
            format!("{}.kicad_pro", self.name),
            "{\"meta\":{\"version\":1}}\n",
        )?;
        Ok(())
    }
}
fn and_pins() -> Vec<Pin> {
    vec![
        p("1", "A", -10.16, 2.54, 0, "input"),
        p("2", "B", -10.16, -2.54, 0, "input"),
        p("3", "GND", 0., -10.16, 90, "power_in"),
        p("4", "Y", 10.16, 0., 180, "output"),
        p("5", "VCC", 0., 10.16, 270, "power_in"),
    ]
}
fn dff() -> Vec<Pin> {
    vec![
        p("1", "/CLR1", -17.78, 15.24, 0, "input"),
        p("2", "D1", -17.78, 10.16, 0, "input"),
        p("3", "CLK1", -17.78, 5.08, 0, "input"),
        p("4", "/PRE1", -17.78, 0., 0, "input"),
        p("5", "Q1", 17.78, 10.16, 180, "output"),
        p("6", "/Q1", 17.78, 5.08, 180, "output"),
        p("7", "GND", 0., -27.94, 90, "power_in"),
        p("8", "/Q2", 17.78, -15.24, 180, "output"),
        p("9", "Q2", 17.78, -10.16, 180, "output"),
        p("10", "/PRE2", -17.78, -5.08, 0, "input"),
        p("11", "CLK2", -17.78, -10.16, 0, "input"),
        p("12", "D2", -17.78, -15.24, 0, "input"),
        p("13", "/CLR2", -17.78, -20.32, 0, "input"),
        p("14", "VCC", 0., 27.94, 270, "power_in"),
    ]
}
fn main() -> Result<()> {
    let mut s = Sch::new("clamp");
    s.panel(
        "AUX ACTIVE CLAMP / ALL NETS HOT-REFERENCED",
        15.,
        15.,
        385.,
        235.,
    );
    let pins = vec![
        p("1", "FB", -17.78, 10.16, 0, "input"),
        p("2", "OUT", 17.78, 10.16, 180, "input"),
        p("3", "SNS", 17.78, 15.24, 180, "input"),
        p("4", "GATE", 17.78, 0., 180, "output"),
        p("5", "VCC", 0., 25.4, 270, "power_in"),
        p("6", "/SHDN", -17.78, 0., 0, "input"),
        p("7", "GND", -5.08, -25.4, 90, "power_in"),
        p("8", "UV", -17.78, 15.24, 0, "input"),
        p("9", "GND", 5.08, -25.4, 90, "power_in"),
        p("10", "/FLT", 17.78, -10.16, 180, "open_collector"),
        p("11", "ENOUT", 17.78, -15.24, 180, "open_collector"),
        p("12", "TMR", -17.78, -15.24, 0, "passive"),
    ];
    s.ic(
        "U1",
        "LT4363HMS-1#PBF",
        &pins,
        &[
            "FB",
            "AUX_PROTECTED",
            "SNS",
            "GATE_DRV",
            "AUX_RAW",
            "SERVICE_RESET_N",
            "HOT_GND",
            "UV",
            "HOT_GND",
            "FLT_TP",
            "ENOUT_TP",
            "TMR",
        ],
        130.,
        105.,
        30.48,
        45.72,
        "Package_SO:MSOP-12_3x4.039mm_P0.65mm",
    );
    let qlib = s.standard("Transistor_FET", "Q_NMOS_GDS")?;
    s.instance(
        "Q1",
        "FDB33N25",
        &qlib,
        245.,
        65.,
        "Package_TO_SOT_SMD:TO-263-2",
        12.,
    );
    for (pin, n) in [
        p("1", "G", -5.08, 0., 0, "input"),
        p("2", "D", 2.54, 5.08, 270, "passive"),
        p("3", "S", 2.54, -5.08, 90, "passive"),
    ]
    .iter()
    .zip(["Q_GATE", "AUX_RAW", "SNS"])
    {
        s.terminal("Q1", pin, 245., 65., n);
    }
    for (r, v, t, x, y, a, b) in [
        (
            "R1",
            "0.22R / 1% total",
            "R_Small_US",
            247.54,
            100.,
            "SNS",
            "AUX_PROTECTED",
        ),
        (
            "R2",
            "59.0kR / 0.1% total",
            "R_Small_US",
            55.,
            85.,
            "AUX_PROTECTED",
            "FB",
        ),
        (
            "R3",
            "4.99kR / 0.1% total",
            "R_Small_US",
            55.,
            115.,
            "FB",
            "HOT_GND",
        ),
        (
            "R4",
            "91.0kR / 1% total",
            "R_Small_US",
            55.,
            165.,
            "AUX_RAW",
            "UV",
        ),
        (
            "R5",
            "10.0kR / 1% total",
            "R_Small_US",
            55.,
            195.,
            "UV",
            "HOT_GND",
        ),
        ("R6", "10R", "R_Small_US", 200., 95., "GATE_DRV", "Q_GATE"),
        ("R7", "100R", "R_Small_US", 245., 150., "Q_GATE", "CG"),
        ("C1", "100nF / 50V", "C", 100., 55., "AUX_RAW", "HOT_GND"),
        (
            "C2",
            "100nF / +/-10% eff",
            "C",
            105.,
            185.,
            "TMR",
            "HOT_GND",
        ),
        ("C3", "1.5uF / 63V target", "C", 245., 195., "CG", "HOT_GND"),
        (
            "C4",
            "220uF / 50V target",
            "C_Polarized",
            330.,
            140.,
            "AUX_PROTECTED",
            "HOT_GND",
        ),
    ] {
        s.passive(r, v, t, x, y, a, b)?;
    }
    let dl = s.standard("Device", "D")?;
    s.instance("D1", "1N4148W", &dl, 300., 150., "Diode_SMD:D_SOD-123", 8.);
    s.terminal(
        "D1",
        &p("1", "K", -3.81, 0., 0, "passive"),
        300.,
        150.,
        "CG",
    );
    s.terminal(
        "D1",
        &p("2", "A", 3.81, 0., 180, "passive"),
        300.,
        150.,
        "Q_GATE",
    );
    s.note(
        "Input: regulated 15V; 35V fault envelope remains conditional.",
        25.,
        30.,
        1.27,
    );
    s.note("C4: low ESR bulk at protected pass-device output.\nRequire Cbulk,min >= max(22uF, 10 x Cceramic,max).\nTotal downstream C <=300uF for startup screen.\nC3 changed from470nF to1.5uF with larger bulk.",290.,190.,1.27);
    s.note("SERVICE_RESET_N: local contact to HOT_GND only; normally open.\nDoes not follow source PERMIT. Hold >=120ms; verify release slew.\nFLT_TP / ENOUT_TP are observation only; no fault-net pullup fitted.",105.,225.,1.27);
    s.note("Capacitor MPN/ESR/temperature limits remain unselected; footprints are placeholders.\nNo output-peak, startup, SOA or single-pass-FET-short qualification is claimed.",25.,242.,1.27);
    s.path(&[(247.54, 59.92), (247.54, 45.)]);
    s.power("AUX_RAW", 247.54, 45.);
    s.path(&[(247.54, 70.08), (247.54, 85.), (247.54, 97.46)]);
    s.label("SNS", 247.54, 85., true);
    s.path(&[
        (247.54, 102.54),
        (247.54, 125.),
        (330., 125.),
        (330., 136.19),
    ]);
    s.label("AUX_PROTECTED", 275., 125., true);
    s.junction(275., 125.);
    s.path(&[(330., 143.81), (330., 152.)]);
    s.power("HOT_GND", 330., 152.);
    s.path(&[(55., 82.46), (55., 73.)]);
    s.power("AUX_PROTECTED", 55., 73.);
    s.path(&[(55., 87.54), (55., 100.), (55., 112.46)]);
    s.path(&[(55., 100.), (85., 100.), (85., 94.84), (112.22, 94.84)]);
    s.junction(55., 100.);
    s.label("FB", 85., 94.84, true);
    s.path(&[(55., 117.54), (55., 125.)]);
    s.power("HOT_GND", 55., 125.);
    s.path(&[(55., 162.46), (55., 152.)]);
    s.power("AUX_RAW", 55., 152.);
    s.path(&[(55., 167.54), (55., 180.), (55., 192.46)]);
    s.label("UV", 55., 180., true);
    s.path(&[(55., 197.54), (55., 207.)]);
    s.power("HOT_GND", 55., 207.);
    s.path(&[(112.22, 89.76), (102., 89.76)]);
    s.label("UV", 102., 89.76, false);
    s.path(&[(147.78, 105.), (180., 105.), (180., 92.46), (200., 92.46)]);
    s.label("GATE_DRV", 164., 105., true);
    s.path(&[(200., 97.54), (210., 97.54), (210., 65.), (239.92, 65.)]);
    s.label("Q_GATE", 215., 65., true);
    s.path(&[
        (245., 147.46),
        (245., 140.),
        (315., 140.),
        (315., 150.),
        (303.81, 150.),
    ]);
    s.label("Q_GATE", 245., 140., true);
    s.path(&[(245., 152.54), (245., 175.), (245., 191.19)]);
    s.path(&[(245., 175.), (280., 175.), (280., 150.), (296.19, 150.)]);
    s.junction(245., 175.);
    s.label("CG", 245., 175., true);
    s.path(&[(245., 198.81), (245., 207.)]);
    s.power("HOT_GND", 245., 207.);
    s.path(&[(100., 51.19), (130., 51.19), (130., 79.6)]);
    s.power("AUX_RAW", 130., 51.19);
    s.path(&[(100., 58.81), (100., 66.)]);
    s.power("HOT_GND", 100., 66.);
    s.path(&[
        (124.92, 130.4),
        (124.92, 140.),
        (135.08, 140.),
        (135.08, 130.4),
    ]);
    s.power("HOT_GND", 130., 140.);
    s.junction(130., 140.);
    s.path(&[
        (112.22, 120.24),
        (90., 120.24),
        (90., 170.),
        (105., 170.),
        (105., 181.19),
    ]);
    s.label("TMR", 90., 170., true);
    s.path(&[(105., 188.81), (105., 198.)]);
    s.power("HOT_GND", 105., 198.);
    s.save()?;
    let mut s = Sch::new("reset");
    s.panel("SELV / FAULT CAPTURE", 10., 15., 180., 140.);
    s.panel("ISOLATION / 3 FORWARD + 1 RETURN", 195., 15., 205., 140.);
    s.panel("HOT / HARDWARE AUTHORIZATION AND RUN", 10., 165., 390., 95.);
    let ap = and_pins();
    let fp = "Package_TO_SOT_SMD:SOT-23-5";
    s.ic(
        "U1",
        "SN74LVC1G08DBVR",
        &ap,
        &[
            "SOURCE_RESET_GOOD",
            "SOURCE_WATCHDOG_GOOD",
            "SELV_GND",
            "RESET_WD_OK",
            "SELV3V3",
        ],
        65.,
        53.,
        15.24,
        15.24,
        fp,
    );
    s.ic(
        "U2",
        "SN74LVC1G08DBVR",
        &ap,
        &[
            "RESET_WD_OK",
            "INTERLOCK_PERMIT",
            "SELV_GND",
            "SOURCE_HEALTH",
            "SELV3V3",
        ],
        135.,
        53.,
        15.24,
        15.24,
        fp,
    );
    s.ic(
        "U3",
        "SN74HCS74PWR",
        &dff(),
        &[
            "SOURCE_HEALTH",
            "SELV3V3",
            "SOURCE_REARM_PULSE",
            "SELV3V3",
            "PERMIT_TX",
            "NC",
            "SELV_GND",
            "NC",
            "NC",
            "SELV3V3",
            "SELV_GND",
            "SELV_GND",
            "SELV_GND",
            "SELV3V3",
        ],
        115.,
        111.,
        30.48,
        50.8,
        "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    );
    let iso = vec![
        p("1", "VCC1", -10.16, 30.48, 270, "power_in"),
        p("2", "GND1", -10.16, -30.48, 90, "power_in"),
        p("3", "INA", -20.32, 15.24, 0, "input"),
        p("4", "INB", -20.32, 5.08, 0, "input"),
        p("5", "INC", -20.32, -5.08, 0, "input"),
        p("6", "OUTD", -20.32, -15.24, 0, "output"),
        p("7", "EN1", -20.32, 25.4, 0, "input"),
        p("8", "GND1", -5.08, -30.48, 90, "power_in"),
        p("9", "GND2", 5.08, -30.48, 90, "power_in"),
        p("10", "EN2", 20.32, 25.4, 180, "input"),
        p("11", "IND", 20.32, -15.24, 180, "input"),
        p("12", "OUTC", 20.32, -5.08, 180, "output"),
        p("13", "OUTB", 20.32, 5.08, 180, "output"),
        p("14", "OUTA", 20.32, 15.24, 180, "output"),
        p("15", "GND2", 10.16, -30.48, 90, "power_in"),
        p("16", "VCC2", 10.16, 30.48, 270, "power_in"),
    ];
    s.ic(
        "U4",
        "ISO7741FDWR",
        &iso,
        &[
            "SELV3V3",
            "SELV_GND",
            "COMMAND_TX",
            "PERMIT_TX",
            "RELAY_CMD",
            "SELV_RESPONSE_RX",
            "SELV3V3",
            "SELV_GND",
            "HOT_GND",
            "HOT_LOGIC5",
            "HOT_RESPONSE_TX",
            "HOT_RELAY_CMD",
            "HOT_PERMIT_RX",
            "HOT_COMMAND_RX",
            "HOT_GND",
            "HOT_LOGIC5",
        ],
        295.,
        82.,
        35.56,
        55.88,
        "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
    );
    s.ic(
        "U5",
        "SN74LVC1G08DBVR",
        &ap,
        &[
            "CLEAR_OK_EXISTING",
            "HOT_WATCHDOG_GOOD",
            "HOT_GND",
            "CLEAR_OK_HW",
            "HOT_LOGIC5",
        ],
        65.,
        205.,
        15.24,
        15.24,
        fp,
    );
    s.ic(
        "U6",
        "SN74HCS74PWR",
        &dff(),
        &[
            "CLEAR_OK_HW",
            "ARM_AUTHORIZED",
            "VALIDATED_START_5V",
            "HOT_LOGIC5",
            "RUN",
            "NC",
            "HOT_GND",
            "NC",
            "ARM_AUTHORIZED",
            "HOT_LOGIC5",
            "SESSION_ARM_5V",
            "HOT_LOGIC5",
            "CLEAR_OK_HW",
            "HOT_LOGIC5",
        ],
        195.,
        212.,
        30.48,
        50.8,
        "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    );
    s.ic(
        "U7",
        "SN74LVC1G08DBVR",
        &ap,
        &["RUN", "CLEAR_OK_HW", "HOT_GND", "ENABLE_GOOD", "HOT_LOGIC5"],
        330.,
        205.,
        15.24,
        15.24,
        fp,
    );
    s.note(
        "U6 reuses both halves of existing HOT latch; U7 represents existing enable AND.",
        100.,
        254.,
        1.27,
    );
    s.note("CLEAR_OK_EXISTING includes HOT_PERMIT_RX via existing buffer + health gates.\nENABLE_GOOD drives existing BSS138 / UCC27511A disable network.\nThese external circuits are required; they are not duplicated in this fixture.",250.,235.,1.1);
    s.note("External supervisor / watchdog producers are not selected.\nSOURCE_REARM_PULSE must stay low at boot and until HOT clear is established.",18.,147.,1.1);
    s.note("No galvanic wire joins SELV_GND and HOT_GND.\nDecoder / framing / level translation remain external.\nBoth validated HOT pulses must meet5V logic thresholds.",225.,136.,1.27);
    // Local ground pins join on their own side of the isolation boundary.
    for (xs, gnd) in [
        ([284.84, 289.92], "SELV_GND"),
        ([300.08, 305.16], "HOT_GND"),
    ] {
        s.path(&[
            (xs[0], 112.48),
            (xs[0], 121.),
            (xs[1], 121.),
            (xs[1], 112.48),
        ]);
        s.power(
            gnd,
            if gnd == "SELV_GND" {
                xs[0] - 10.16
            } else {
                xs[1] + 10.16
            },
            121.,
        );
        s.wire(
            (xs[0], 121.),
            (
                if gnd == "SELV_GND" {
                    xs[0] - 10.16
                } else {
                    xs[1] + 10.16
                },
                121.,
            ),
        );
    }
    s.path(&[
        (97.22, 121.16),
        (85., 121.16),
        (85., 136.),
        (97.22, 136.),
        (97.22, 131.32),
    ]);
    s.wire((97.22, 126.24), (85., 126.24));
    s.junction(85., 126.24);
    s.power("SELV_GND", 85., 136.);
    for (x, endpoint, ys, rail) in [
        (30., 97.22, [100.84, 111., 116.08], "SELV3V3"),
        (110., 177.22, [212., 217.08, 227.24], "HOT_LOGIC5"),
    ] {
        s.wire((x, ys[0]), (x, ys[2]));
        for y in ys {
            s.wire((x, y), (endpoint, y));
        }
        s.junction(x, ys[1]);
        s.power(rail, x, ys[0]);
    }
    // Bias/bypass bank is a separate, explicitly labelled section on the same sheet.
    s.panel(
        "LOCAL BYPASS AND DEFAULT BIAS / CAPTURED COMPONENTS",
        10.,
        270.,
        390.,
        112.,
    );
    s.note(
        "C1:U1  C2:U2  C3:U3  C4:U4 SELV  |  C5:U4 HOT  C6:U5  C7:U6  C8:U7; place at supply pins.",
        18.,
        280.,
        1.1,
    );
    for (i, (rail, gnd)) in [
        ("SELV3V3", "SELV_GND"),
        ("SELV3V3", "SELV_GND"),
        ("SELV3V3", "SELV_GND"),
        ("SELV3V3", "SELV_GND"),
        ("HOT_LOGIC5", "HOT_GND"),
        ("HOT_LOGIC5", "HOT_GND"),
        ("HOT_LOGIC5", "HOT_GND"),
        ("HOT_LOGIC5", "HOT_GND"),
    ]
    .iter()
    .enumerate()
    {
        s.passive(
            &format!("C{}", i + 1),
            "100nF",
            "C",
            30. + i as f64 * 45.,
            298.,
            rail,
            gnd,
        )?;
    }
    let biases = [
        ("SOURCE_RESET_GOOD", "SELV_GND"),
        ("SOURCE_WATCHDOG_GOOD", "SELV_GND"),
        ("INTERLOCK_PERMIT", "SELV_GND"),
        ("SOURCE_REARM_PULSE", "SELV_GND"),
        ("PERMIT_TX", "SELV_GND"),
        ("COMMAND_TX", "SELV_GND"),
        ("RELAY_CMD", "SELV_GND"),
        ("SELV_RESPONSE_RX", "SELV_GND"),
        ("HOT_RELAY_CMD", "HOT_GND"),
        ("HOT_PERMIT_RX", "HOT_GND"),
        ("HOT_WATCHDOG_GOOD", "HOT_GND"),
        ("SESSION_ARM_5V", "HOT_GND"),
        ("VALIDATED_START_5V", "HOT_GND"),
    ];
    for (i, (n, g)) in biases.iter().enumerate() {
        s.passive(
            &format!("R{}", i + 1),
            "10kR",
            "R_Small_US",
            30. + (i % 7) as f64 * 53.,
            330. + (i / 7) as f64 * 32.,
            n,
            g,
        )?;
    }
    for (first, rail, gnd) in [(0, "SELV3V3", "SELV_GND"), (4, "HOT_LOGIC5", "HOT_GND")] {
        let left = 30. + first as f64 * 45.;
        for i in 0..4 {
            let x = left + i as f64 * 45.;
            s.wire((x, 294.19), (x, 289.11));
            s.wire((x, 301.81), (x, 310.));
            if i > 0 {
                s.wire((x - 45., 289.11), (x, 289.11));
                s.wire((x - 45., 310.), (x, 310.));
            }
            if i > 0 && i < 3 {
                s.junction(x, 289.11);
                s.junction(x, 310.);
            }
        }
        s.power(rail, left, 289.11);
        s.power(gnd, left, 310.);
    }
    for (first, last, y, gnd) in [
        (0, 6, 330., "SELV_GND"),
        (0, 0, 362., "SELV_GND"),
        (1, 5, 362., "HOT_GND"),
    ] {
        for i in first..=last {
            let x = 30. + i as f64 * 53.;
            s.wire((x, y + 2.54), (x, y + 8.));
            if i > first {
                s.wire((x - 53., y + 8.), (x, y + 8.));
            }
            if i > first && i < last {
                s.junction(x, y + 8.);
            }
        }
        s.power(gnd, 30. + first as f64 * 53., y + 8.);
    }
    s.save()?;
    let text = fs::read_to_string("reset.kicad_sch")?
        .replace("(paper \"A3\")", "(paper \"User\" 420 440)");
    fs::write("reset.kicad_sch", text)?;
    let mut merged = BTreeMap::new();
    for name in ["clamp", "reset"] {
        let source = fs::read_to_string(format!("{name}-symbols.kicad_sym"))?;
        let mut rest = source.as_str();
        while let Some(i) = rest.find("(symbol \"") {
            let b = block(rest, i)?;
            let name = b.split('"').nth(1).ok_or("missing symbol name")?;
            merged.insert(name.to_owned(), b.to_owned());
            rest = &rest[i + b.len()..];
        }
    }
    fs::write(
        "Temper16.kicad_sym",
        format!(
            "(kicad_symbol_lib (version 20241209) (generator \"kicad_symbol_editor\")\n{}\n)",
            merged.values().cloned().collect::<Vec<_>>().join("\n")
        ),
    )?;
    fs::write("sym-lib-table", "(sym_lib_table (version 7) (lib (name \"Temper16\") (type \"KiCad\") (uri \"${KIPRJMOD}/Temper16.kicad_sym\") (options \"\") (descr \"Isolated review symbols\")))\n")?;
    let mut table = String::from("(fp_lib_table (version 7)\n");
    for name in [
        "Diode_SMD",
        "Package_SO",
        "Package_TO_SOT_SMD",
        "Resistor_SMD",
        "Capacitor_SMD",
        "Capacitor_THT",
    ] {
        table+=&format!("(lib (name {0}) (type \"KiCad\") (uri \"${{KICAD10_FOOTPRINT_DIR}}/{name}.pretty\") (options \"\") (descr \"KiCad standard footprints; passive choices unqualified\"))\n",q(name));
    }
    table += ")\n";
    fs::write("fp-lib-table", table)?;
    Ok(())
}

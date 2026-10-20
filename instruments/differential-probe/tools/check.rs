//! Check KiCad's exported connectivity against the authoring intent and physical pads.
//! This verifies serialization/connectivity, not analogue performance or insulation.
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
};
fn attr<'a>(s: &'a str, k: &str) -> &'a str {
    let p = format!("{k}=\"");
    let t = s
        .split_once(&p)
        .unwrap_or_else(|| panic!("missing {k} in {s}"))
        .1;
    t.split('"').next().unwrap()
}
fn body<'a>(s: &'a str, k: &str) -> &'a str {
    s.split_once(&format!("<{k}>"))
        .map(|(_, v)| v.split_once(&format!("</{k}>")).unwrap().0)
        .unwrap_or("")
}
fn main() {
    let xml = fs::read_to_string("validation/netlist.xml").unwrap();
    let input = fs::read_to_string("validation/expected-pins.tsv").unwrap();
    let mut intended = BTreeMap::<String, BTreeSet<String>>::new();
    let mut by_pin = BTreeMap::new();
    for line in input.lines().skip(1) {
        let v: Vec<_> = line.split('\t').collect();
        let p = format!("{}.{}", v[0], v[1]);
        let n = if v[2] == "NC" {
            format!("NC:{p}")
        } else {
            v[2].into()
        };
        intended.entry(n.clone()).or_default().insert(p.clone());
        by_pin.insert(p, n);
    }
    let mut actual = BTreeMap::<String, BTreeSet<String>>::new();
    let mut observed = BTreeMap::new();
    for section in xml.split("<net code=").skip(1) {
        let section = section.split("</net>").next().unwrap();
        let net = attr(section, "name");
        for node in section.split("<node ").skip(1) {
            let r = attr(node, "ref");
            if r.starts_with('#') {
                continue;
            }
            let p = format!("{r}.{}", attr(node, "pin"));
            assert!(
                observed.insert(p.clone(), net.to_string()).is_none(),
                "duplicate pin {p}"
            );
            actual.entry(net.into()).or_default().insert(p);
        }
    }
    assert_eq!(observed.len(), by_pin.len(), "pin census");
    for (name, pins) in &intended {
        let first = pins.first().unwrap();
        let physical = observed
            .get(first)
            .unwrap_or_else(|| panic!("missing {first}"));
        assert_eq!(pins, &actual[physical], "net {name} exported as {physical}");
    }
    // Critical pin numbers checked separately from placement/wire generation.
    for (r, p, n) in [
        ("U8", "1", "+BAT"),
        ("U8", "2", "GND"),
        ("U9", "1", "GND"),
        ("U9", "2", "-BAT"),
        ("U10", "1", "REF_P"),
        ("U10", "2", "REF_P"),
        ("U10", "3", "GND"),
        ("U11", "1", "GND"),
        ("U11", "2", "GND"),
        ("U11", "3", "REF_N"),
        ("D1", "1", "REF_N"),
        ("D1", "2", "REF_P"),
        ("D1", "3", "IN_P"),
        ("U5", "3", "+4V8"),
        ("U5", "12", "-4V8"),
        ("U6", "8", "+4V8"),
        ("U6", "4", "-4V8"),
        ("U7", "14", "+4V8"),
        ("U7", "7", "-4V8"),
        ("U7", "6", "SET"),
        ("U7", "4", "RESET"),
        ("SW2", "3", "NC:SW2.3"),
        ("SW2", "6", "NC:SW2.6"),
        ("J3", "1", "OUT"),
        ("J3", "2", "GND"),
    ] {
        assert_eq!(
            by_pin[&format!("{r}.{p}")],
            n,
            "datasheet/intent mismatch at {r}.{p}"
        );
    }
    for u in ["U1", "U2", "U3"] {
        for (p, n) in [("7", "+4V8"), ("4", "-4V8"), ("8", "+4V8"), ("9", "GND")] {
            assert_eq!(by_pin[&format!("{u}.{p}")], n);
        }
    }
    let mut count = 0;
    let mut footprints = 0;
    let mut audit = "reference\tmpn\tfootprint\tpad_numbers\n".to_string();
    for component in xml.split("<comp ref=").skip(1) {
        let component = component.split("</comp>").next().unwrap();
        let r = component.split('"').nth(1).unwrap();
        if r.starts_with('#') {
            continue;
        }
        count += 1;
        let mpn = component
            .split("<field name=\"MPN\">")
            .nth(1)
            .unwrap()
            .split("</field>")
            .next()
            .unwrap();
        assert!(!mpn.trim().is_empty(), "missing MPN {r}");
        let fp = body(component, "footprint");
        if fp.is_empty() {
            assert!(
                ["BT1", "BT2", "SW1", "SW2", "J3"].contains(&r),
                "unexpected offboard part {r}"
            );
            audit += &format!("{r}\t{mpn}\tOFFBOARD\tsee drawing / wiring notes\n");
            continue;
        }
        let (lib, name) = fp.split_once(':').unwrap();
        let path = if lib == "Probe" {
            format!("cad/Probe.pretty/{name}.kicad_mod")
        } else {
            format!("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/{lib}.pretty/{name}.kicad_mod")
        };
        let ft = fs::read_to_string(&path).unwrap_or_else(|e| panic!("{r}: {path}: {e}"));
        let pads: BTreeSet<String> = ft
            .split("(pad \"")
            .skip(1)
            .map(|p| p.split('"').next().unwrap().to_string())
            .filter(|p| !p.is_empty())
            .collect();
        let wanted: BTreeSet<String> = by_pin
            .keys()
            .filter_map(|p| p.strip_prefix(&format!("{r}.")))
            .map(String::from)
            .collect();
        assert_eq!(pads, wanted, "footprint pin mismatch {r}");
        footprints += 1;
        audit += &format!(
            "{r}\t{mpn}\t{fp}\t{}\n",
            pads.into_iter().collect::<Vec<_>>().join(",")
        );
    }
    fs::write("validation/footprint-audit.tsv", audit).unwrap();
    let mut report=format!("PASS: {count} exact-MPN components; {footprints} board footprints; 5 offboard components.\nPASS: {} pins, {} independent connectivity groups agree with KiCad export.\nPASS: critical package pin mappings and power polarity assertions.\n",observed.len(),intended.len());
    let top = 10e6f64;
    let bottom = top / 1999.;
    let tau = 2e6 * 33e-12;
    let cap = 1999. * 33e-12 / 5.;
    let cutoff = 1. / (2. * std::f64::consts::PI * 97.6 * 330e-12);
    report+=&format!("\nIdeal circuit calculations (not measurements):\nRbottom = {bottom:.6} ohm; nominal trim = {:.6} ohm.\nCbottom TOTAL incl parasitics = {:.4} nF; input series C = 6.6 pF.\nDivider crossover = {:.2} Hz.\nOutput RC pole = {:.6} MHz.\n",bottom-4990.,cap*1e9,1./(2.*std::f64::consts::PI*tau),cutoff/1e6);
    let min_trim = (top * 0.999) / 1999. - 4990. * 1.0001;
    let max_trim = (top * 1.001) / 1999. - 4990. * 0.9999;
    assert!(min_trim >= 0. && max_trim < 45.);
    report+=&format!("DC trim at all 0.1% upper-string / 0.01% bottom-resistor corners: {min_trim:.3} to {max_trim:.3} ohm (50-ohm pot, min end-to-end 45 ohm).\n");
    for f in [35e3, 60e3] {
        let x = f / cutoff;
        report += &format!(
            "RC filter at {:.0} kHz: gain {:.6}, phase {:.4} deg.\n",
            f / 1e3,
            1. / (1. + x * x).sqrt(),
            -x.atan().to_degrees()
        );
    }
    for (g, range) in [(2., 1500.), (10., 300.)] {
        report += &format!(
            "Gain {g}: input/output ratio {:.0}:1, initial {range:.0} Vpk -> {:.3} Vpk output.\n",
            2000. / g,
            range / 2000. * g
        );
    }
    report+=&format!("At 3000 V DC per tip: total dissipation {:.3} W/leg; {:.4} W per 1-Mohm resistor; ~300 V/resistor and ~600 V/segment capacitor.\n",3000f64.powi(2)/(top+bottom),(3000./(top+bottom)).powi(2)*1e6);
    report+="At 3000 Vpk sine: roughly 0.450 W/leg (half DC heating), 5.28 mArms at 60 kHz through ideal 6.6 pF.\nAt 70 V/ns: ideal 6.6 pF implies 0.462 A transient; actual lead/shield capacitance adds to this.\n";
    report+=&format!("Nominal rails +{:.4} / -{:.4} V. Input comparator threshold +/-{:.4} V. Output comparator threshold +/-{:.4} V raw.\n",1.2*(1.+30./10.),1.22*(1.+29.4/10.),2.495*10./15.62,2.*2.495*10./16.65);
    report+="\nNot established by these checks: CMRR, amplitude/phase accuracy, 5 MHz system bandwidth, input-to-earth capacitance, overload recovery, unpowered input survival, transient withstand, creepage or clearance. PCB, fixed shield and fixture must be qualified together.\n";
    fs::write("validation/checks.txt", &report).unwrap();
    print!("{report}");
}

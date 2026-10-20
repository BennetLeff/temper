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
    for u in ["U1", "U2"] {
        for (p, n) in [("7", "+4V8"), ("4", "-4V8"), ("8", "+4V8"), ("9", "GND")] {
            assert_eq!(by_pin[&format!("{u}.{p}")], n);
        }
    }
    for u in ["U3", "U4", "U12"] {
        for (p, n) in [("7", "+4V8"), ("4", "-4V8")] {
            assert_eq!(by_pin[&format!("{u}.{p}")], n);
        }
        for p in ["1", "5", "8"] {
            assert_eq!(by_pin[&format!("{u}.{p}")], format!("NC:{u}.{p}"));
        }
    }
    for (refdes, pin, net) in [
        ("CT1", "1", "TAP_P"),
        ("CT1", "2", "GND"),
        ("CT2", "1", "TAP_N"),
        ("CT2", "2", "GND"),
        ("R63", "1", "SUM_P"),
        ("R64", "2", "GND"),
        ("R65", "1", "SUM_N"),
        ("R66", "2", "RAW_OUT"),
        ("U12", "3", "GAIN5_IN"),
        ("U12", "2", "GAIN5_FB"),
        ("U12", "6", "FINE_OUT"),
        ("R67", "1", "GAIN5_FB"),
        ("R67", "2", "GND"),
        ("R68", "1", "GAIN5_FB"),
        ("R99", "2", "FINE_OUT"),
        ("R100", "1", "RAW_OUT"),
        ("R100", "2", "GAIN5_IN"),
        ("SW1", "1", "WIDE_SEL"),
        ("SW1", "2", "SELECTED"),
        ("SW1", "3", "FINE_SEL"),
        ("R101", "1", "RAW_OUT"),
        ("R101", "2", "WIDE_SEL"),
        ("R102", "1", "FINE_OUT"),
        ("R102", "2", "FINE_SEL"),
        ("R103", "1", "SELECTED"),
        ("R103", "2", "GND"),
        ("R69", "1", "SELECTED"),
        ("R71", "1", "SELECTED"),
    ] {
        assert_eq!(
            by_pin[&format!("{refdes}.{pin}")],
            net,
            "Rev B topology {refdes}.{pin}"
        );
    }
    for pin in ["4", "5", "6"] {
        assert_eq!(by_pin[&format!("SW1.{pin}")], format!("NC:SW1.{pin}"));
    }
    for n in ["SUM_P", "SUM_N", "GAIN5_IN", "GAIN5_FB"] {
        assert!(
            intended[n].iter().all(|p| !p.starts_with("SW1.")),
            "selector touches sensitive gain input {n}"
        );
    }
    let mut mpns = BTreeMap::new();
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
        mpns.insert(r.to_string(), mpn.to_string());
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
    for (r, m) in [
        ("C61", "C0805C181J5GACTU"),
        ("R69", "RC0805FR-0797R6L"),
        ("R101", "RT0805BRD0749R9L"),
        ("R102", "RT0805BRD0749R9L"),
        ("CT1", "GKG60015"),
        ("CT2", "GKG60015"),
        ("C45", "C0805C470J5GACTU"),
        ("C55", "C0805C470J5GACTU"),
    ] {
        assert_eq!(mpns[r], m, "calculation source {r}");
    }
    for r in ["R87", "R91"] {
        assert_eq!(mpns[r], "RT0805BRD0725K5L");
    }
    for r in [
        "R61", "R62", "R63", "R64", "R65", "R66", "R67", "R68", "R97", "R98", "R99",
    ] {
        assert_eq!(mpns[r], "RNCF0603TKY499R");
    }
    for r in ["R89", "R93"] {
        assert_eq!(mpns[r], "RT0805BRD0729K4L");
    }
    let load = 1. / (1. / 20_000. + 1. / 1_000_000.);
    let selection_gain = load / (load + 49.9);
    let source_r = 97.6 + 1. / (1. / 49.9 + 1. / load);
    let cutoff = 1. / (2. * std::f64::consts::PI * source_r * 180e-12);
    report+=&format!("\nIdeal circuit calculations (not measurements):\nRbottom = {bottom:.6} ohm; nominal trim = {:.6} ohm.\nCbottom TOTAL incl parasitics = {:.4} nF; input series C = 6.6 pF.\nDivider crossover = {:.2} Hz.\nShared filter pole including 49.9-ohm selector source resistance and loading = {:.6} MHz.\n",bottom-4990.,cap*1e9,1./(2.*std::f64::consts::PI*tau),cutoff/1e6);
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
    let coarse_cap = 13_158e-12;
    let trim_pf = (cap - coarse_cap) * 1e12;
    assert!((12. ..60.).contains(&trim_pf));
    report+=&format!("Coarse low-leg C = 13.158 nF, fine trimmer 12-60 pF; ideal nominal trim = {trim_pf:.3} pF before assembly strays.\nSelected-path DC insertion factor = {selection_gain:.8}, load = {load:.3} ohm; shared RC source R = {source_r:.4} ohm.\n");
    let mag = |f: f64, fine: bool| {
        let mut value = 1. / (1. + (f / cutoff).powi(2)).sqrt();
        for pole in [70e6 / 3., 140e6] {
            value /= (1. + (f / pole).powi(2)).sqrt();
        }
        if fine {
            value /= (1. + (f / (70e6 / 5.)).powi(2)).sqrt();
        }
        value
    };
    for (g, range, fine) in [(2., 1500., false), (10., 300., true)] {
        let mut lo = 0.;
        let mut hi = 20e6;
        for _ in 0..80 {
            let mid = (lo + hi) / 2.;
            if mag(mid, fine) > 1. / 2f64.sqrt() {
                lo = mid;
            } else {
                hi = mid;
            }
        }
        let total_gain = g * selection_gain * 1_000_000. / (1_000_000. + 49.9);
        report+=&format!("Gain {g}: nominal probe ratio {:.0}:1 before insertion loss; loaded DC estimate {:.3}:1; initial {range:.0} Vpk -> {:.4} Vpk output.\n",2000./g,2000./total_gain,range/2000.*total_gain);
        report+=&format!("Gain {g}: illustrative first-order cascaded -3dB bandwidth {:.3} MHz; NOT an IC macromodel result or qualification.\n",(lo+hi)/2e6);
    }
    report+="Bandwidth estimate uses U3 noise gain 3 / 70 MHz GBW, U12 gain 5 / 70 MHz GBW, U4 140 MHz unity bandwidth, and C61 only; real amplifier poles, parasitics, scope cable/load and source impedance must be simulated/measured.\n";
    report+=&format!("At 3000 V DC per tip: total dissipation {:.3} W/leg; {:.4} W per 1-Mohm resistor; ~300 V/resistor and ~600 V/segment capacitor.\n",3000f64.powi(2)/(top+bottom),(3000./(top+bottom)).powi(2)*1e6);
    report+="At 3000 Vpk sine: roughly 0.450 W/leg (half DC heating), 5.28 mArms at 60 kHz through ideal 6.6 pF.\nAt 70 V/ns: ideal 6.6 pF implies 0.462 A transient; actual lead/shield capacitance adds to this.\n";
    let threshold = 2.495 * 10. / 35.5;
    let output_threshold = 2.495 * 10. / 39.4;
    // Conservative static warning budget, conditional on the documented calibrated gain/offset bounds.
    let res_tol = 0.001 + 25e-6 * 60.; // 0.1% initial plus 25ppm/C over -25..85C, relative to 25C.
    let ref_max = 2.507 + 0.034 + 0.005; // TL431B initial + full-temp deviation + current/load allowance.
    let div_max = 10_000. * (1. + res_tol) / (25_500. * (1. - res_tol) + 10_000. * (1. + res_tol));
    let output_div_max =
        10_000. * (1. + res_tol) / (29_400. * (1. - res_tol) + 10_000. * (1. + res_tol));
    let comp_error = 0.0055 + 0.0002; // comparator offset and input-bias/PSRR allowance.
    let tip_max = (ref_max * div_max + comp_error + 0.005) / 0.98 * 2000.;
    let sense_min = (1. - res_tol) / 2.; // matched nominal 10k/10k, opposing tolerances.
    let selected_max = (ref_max * output_div_max + comp_error) / sense_min;
    let wide_offset = 0.025;
    let fine_offset = 0.130;
    assert!(tip_max < 1500.);
    assert!((selected_max + wide_offset) / 0.98 * 1000. < 1500.);
    assert!((selected_max + fine_offset) / 0.98 * 200. < 300.);
    report+=&format!("Nominal rails +{:.4} / -{:.4} V. Input warning +/-{threshold:.6} V buffered = {:.2} V/tip. Selected-output warning +/-{:.6} V = {:.2} V differential on wide / {:.2} V on fine.\n",1.2*(1.+30./10.),1.22*(1.+29.4/10.),threshold*2000.,output_threshold*2.,output_threshold*2000.,output_threshold*400.);
    report+=&format!("Conditional late-trip budget (-25..85C): tip < {tip_max:.2} V; selected comparator < {selected_max:.6} V, corresponding to < {:.2} V wide / {:.2} V fine with minimum calibrated gain 98% nominal and actual analog zero offsets <=25mV wide / <=130mV fine.\n",(selected_max+wide_offset)/0.98*1000.,(selected_max+fine_offset)/0.98*200.);
    report+="Warning budget requires measured divider/system gain >=98% nominal, buffer offset within +/-5mV each, actual selected-path zero within the stated range-specific limits, regulator/reference rails valid, and no clamp-induced reference disturbance; scope zero subtraction does not remove the comparator offset. These are qualification acceptance conditions, not assumed measured facts. Comparator finite delay means this LED is not a transient peak guarantee.\n";
    report+="\nNot established by these checks: CMRR, amplitude/phase accuracy, 5 MHz system bandwidth, input-to-earth capacitance, overload recovery, unpowered input survival, transient withstand, creepage or clearance. PCB, fixed shield and fixture must be qualified together.\n";
    fs::write("validation/checks.txt", &report).unwrap();
    print!("{report}");
}

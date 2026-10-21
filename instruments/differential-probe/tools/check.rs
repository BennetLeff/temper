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
#[path = "budget.rs"]
mod budget;
fn budget_class(mpn: &str) -> &'static str {
    if budget::tolerance(mpn) == budget::PRECISION {
        "0.1 % + 25 ppm/C"
    } else {
        "1 % + 100 ppm/C"
    }
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
        ("D1", "1", "-4V8"),
        ("D1", "2", "+4V8"),
        ("D1", "3", "IN_P"),
        ("D2", "1", "-4V8"),
        ("D2", "2", "+4V8"),
        ("D2", "3", "IN_N"),
        ("D3", "1", "-4V8"),
        ("D3", "2", "+4V8"),
        ("D3", "3", "OUT"),
        ("U5", "3", "+4V8"),
        ("U5", "12", "-4V8"),
        ("U6", "8", "+4V8"),
        ("U6", "4", "-4V8"),
        ("U7", "14", "+4V8"),
        ("U7", "7", "-4V8"),
        ("U7", "6", "SET"),
        ("U7", "4", "RESET"),
        ("J3", "1", "OUT"),
        ("J3", "2", "GND"),
    ] {
        assert_eq!(
            by_pin[&format!("{r}.{p}")],
            n,
            "datasheet/intent mismatch at {r}.{p}"
        );
    }
    // OPA2810 dual, SOIC-8: 1 OUT1, 2 -IN1, 3 +IN1, 4 V-, 5 +IN2, 6 -IN2, 7 OUT2, 8 V+.
    for (u, pins) in [
        (
            "U1",
            [
                ("1", "BUF_P"),
                ("2", "BUF_P"),
                ("3", "IN_P"),
                ("5", "IN_N"),
                ("6", "BUF_N"),
                ("7", "BUF_N"),
            ],
        ),
        (
            "U3",
            [
                ("1", "DRIVE"),
                ("2", "DRIVE"),
                ("3", "FILTER"),
                ("5", "SUM_P"),
                ("6", "SUM_N"),
                ("7", "RAW_OUT"),
            ],
        ),
    ] {
        for (p, n) in pins.iter().chain([("8", "+4V8"), ("4", "-4V8")].iter()) {
            assert_eq!(by_pin[&format!("{u}.{p}")], *n, "OPA2810 pinout {u}.{p}");
        }
    }
    // OPA810 single, SOIC-8: 2 -IN, 3 +IN, 4 V-, 6 OUT, 7 V+, 1/5/8 NC.
    for (p, n) in [("7", "+4V8"), ("4", "-4V8"), ("3", "GAIN5_IN"), ("2", "GAIN5_FB"), ("6", "FINE_OUT")] {
        assert_eq!(by_pin[&format!("U12.{p}")], n);
    }
    for p in ["1", "5", "8"] {
        assert_eq!(by_pin[&format!("U12.{p}")], format!("NC:U12.{p}"));
    }
    for (refdes, pin, net) in [
        ("CT1", "1", "TAP_P"),
        ("CT1", "2", "GND"),
        ("CT2", "1", "TAP_N"),
        ("CT2", "2", "GND"),
        ("R63", "1", "SUM_P"),
        ("R63", "2", "GND"),
        ("R65", "1", "SUM_N"),
        ("R65", "2", "RAW_OUT"),
        ("U12", "3", "GAIN5_IN"),
        ("U12", "2", "GAIN5_FB"),
        ("U12", "6", "FINE_OUT"),
        ("R67", "1", "GAIN5_FB"),
        ("R67", "2", "GND"),
        ("R68", "1", "GAIN5_FB"),
        ("R68", "2", "FINE_OUT"),
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
            "Rev C topology {refdes}.{pin}"
        );
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
        // Rev C mounts the BNC, both switches and both battery holders on the PCB.
        assert!(!fp.is_empty(), "unexpected offboard part {r}");
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
            // Unnumbered holes and "MP" mechanical support pins carry no net.
            .filter(|p| !p.is_empty() && p != "MP")
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
    let mut report=format!("PASS: {count} exact-MPN components; {footprints} board footprints; no offboard (hand-wired) components.\nPASS: {} pins, {} independent connectivity groups agree with KiCad export.\nPASS: critical package pin mappings and power polarity assertions.\n",observed.len(),intended.len());
    let top = 10e6f64;
    let bottom = top / 1999.;
    let tau = 2e6 * 33e-12;
    let cap = 1999. * 33e-12 / 5.;
    for (r, m) in [
        ("C61", "CL21C470JBANNNC"),
        ("C62", "CL10C331JB8NNNC"),
        ("R69", "0805W8F2200T5E"),
        ("R101", "0805W8F499JT5E"),
        ("R102", "0805W8F499JT5E"),
        ("CT1", "GKG60015"),
        ("CT2", "GKG60015"),
        ("C41", "CC1206FKNPO9BN103"),
        ("C51", "CC1206FKNPO9BN103"),
        ("C42", "C0805C302F5GACTU"),
        ("C52", "C0805C302F5GACTU"),
        ("C43", "C0805C161F5GACTU"),
        ("C53", "C0805C161F5GACTU"),
        ("R12", "0805W8F2200T5E"),
        ("R32", "0805W8F2200T5E"),
        ("U1", "OPA2810IDR"),
        ("U3", "OPA2810IDR"),
        ("U12", "OPA810IDR"),
    ] {
        assert_eq!(mpns[r], m, "calculation source {r}");
    }
    for leg in [0, 20] {
        for i in 1..=5 {
            assert_eq!(mpns[&format!("R{}", leg + i)], "HV121WF2004T4E");
        }
        assert_eq!(mpns[&format!("R{}", leg + 11)], "RT0603BRD074K87L");
    }
    for (r, m) in [
        ("R61", "RNCF0603TKY499R"),
        ("R62", "RNCF0603TKY499R"),
        ("R67", "RNCF0603TKY499R"),
        ("R63", "RNCF0603TKY1K00"),
        ("R65", "RNCF0603TKY1K00"),
        ("R68", "RNCF0603TKY2K00"),
        ("R87", "RT0805BRD0766K5L"),
        ("R91", "RT0805BRD0766K5L"),
        ("R88", "0805W8F1001T5E"),
        ("R92", "0805W8F1001T5E"),
        ("R89", "RT0805BRD0710KL"),
        ("R93", "RT0805BRD0710KL"),
    ] {
        assert_eq!(mpns[r], m, "gain/threshold source {r}");
    }
    let wide_gain = 1000. / 499.;
    let fine_stage = 1. + 2000. / 499.;
    let load = 1. / (1. / 20_000. + 1. / 1_000_000.);
    let selection_gain = load / (load + 49.9);
    let source_r = 220. + 1. / (1. / 49.9 + 1. / load);
    // Output filter (tools/output_filter_study.py): C61 47 pF after R69, and C62 330 pF
    // shunting OUT after R70 (49.9 R) through the bridged jumper JP1, in parallel with
    // the lumped 1 m cable + scope input (120 pF). Cutting JP1 leaves only the cable.
    let cutoff = 1. / (2. * std::f64::consts::PI * source_r * 47e-12);
    let out_pole = 1. / (2. * std::f64::consts::PI * 49.9 * (330e-12 + 120e-12));
    let out_pole_open = 1. / (2. * std::f64::consts::PI * 49.9 * 120e-12);
    report+=&format!("\nIdeal circuit calculations (not measurements):\nRbottom = {bottom:.6} ohm; nominal trim = {:.6} ohm.\nCbottom TOTAL incl parasitics = {:.4} nF; input series C = 6.6 pF.\nDivider crossover = {:.2} Hz.\nFirst filter pole (R69 + 49.9-ohm selector source and loading, C61 47 pF) = {:.6} MHz; second pole (R70 49.9 ohm into C62 330 pF + 120 pF cable/scope, JP1 bridged) = {:.6} MHz ({:.3} MHz with JP1 cut).\n",bottom-4870.,cap*1e9,1./(2.*std::f64::consts::PI*tau),cutoff/1e6,out_pole/1e6,out_pole_open/1e6);
    // Cost-down DC trim (docs/cost-down.md section 2): 1 % upper string (HV121WF2004T4E),
    // 4.87 k 0.1 % fixed part (RT0603BRD074K87L), 500-ohm 3296 trimmer at +/-10 %,
    // usable from max(1 %, 2 ohm) of nominal to 0.9 x nominal.
    let (fixed, pot) = (4870., 500.);
    let min_trim = (top * 0.99) / 1999. - fixed * 1.001;
    let max_trim = (top * 1.01) / 1999. - fixed * 0.999;
    let (pot_lo, pot_hi) = ((0.01f64 * pot).max(2.), 0.9 * pot);
    assert!(min_trim >= pot_lo && max_trim <= pot_hi);
    report+=&format!("DC trim at all 1% upper-string / 0.1% fixed-resistor corners: {min_trim:.3} to {max_trim:.3} ohm (500-ohm pot, usable {pot_lo:.0} to {pot_hi:.0} ohm; {:.0} ohm per turn of 25).\n",pot/25.);
    // Ratio drift from datasheet TCR limits, -25..85 C relative to 25 C: string 100 ppm/C;
    // bottom = 4.87 k at 25 ppm/C plus the nominal trim at the 3296's 100 ppm/C.
    let bottom_tcr = (fixed * 25. + (bottom - fixed) * 100.) / bottom;
    let ratio_drift = (100. + bottom_tcr) * 1e-6 * 60.;
    assert!(ratio_drift < 0.01);
    // Gain-resistor drift (docs/fee-consolidation.md section 3): RNCF0603TKY 5 ppm/C in the
    // subtractor (R61/R62 in, R63/R65 feedback) and fine stage (R67/R68), opposing signs.
    for r in ["R61", "R62", "R63", "R65", "R67", "R68"] {
        assert!(mpns[r].starts_with("RNCF0603TKY"), "gain-drift budget assumes 5 ppm/C RNCF at {r}");
    }
    let rncf_tc = 5e-6;
    let fine_gain = 1. + 2000. / 499.;
    let wide_gain_drift = 2. * rncf_tc * 60.;
    let fine_gain_drift = wide_gain_drift + 2. * rncf_tc * 60. * (fine_gain - 1.) / fine_gain;
    let need_wide = 0.98 / ((1. - ratio_drift) * (1. - wide_gain_drift));
    let need_fine = 0.98 / ((1. - ratio_drift) * (1. - fine_gain_drift));
    assert!(need_fine < 0.99, "calibrated-gain acceptance would leave < 1 % margin");
    report+=&format!("Divider ratio drift from TCR limits over -25..85 C: <= {:.2} % (string 100 ppm/C, bottom {bottom_tcr:.1} ppm/C); gain-resistor drift <= {:.3} % wide / {:.3} % fine (RNCF 5 ppm/C). The warning budget's >= 98 % gain condition therefore needs >= {:.2} % (wide) / {:.2} % (fine) calibrated gain at 25 C.\n",ratio_drift*100.,wide_gain_drift*100.,fine_gain_drift*100.,need_wide*100.,need_fine*100.);
    for f in [35e3, 60e3] {
        let (x, y) = (f / cutoff, f / out_pole);
        report += &format!(
            "Two-pole RC filter at {:.0} kHz: gain {:.6}, phase {:.4} deg.\n",
            f / 1e3,
            1. / ((1. + x * x) * (1. + y * y)).sqrt(),
            -(x.atan() + y.atan()).to_degrees()
        );
    }
    // Rev C low-leg compensation coverage. Fixed 10 nF 1% C0G, then two
    // select-on-test C0G positions chosen in sequence with a re-measurement
    // after each fit, then the 12-60 pF trimmer. Every fitted part is taken
    // at either end of its tolerance; selection does not know where.
    let c_nominal = cap * 1e12; // pF
    // Archived divider model (evidence/2026-10-20-divider-output.txt): untrimmed
    // 60 kHz-vs-DC mismatch, 1st..99th percentile, -8.26..+4.20 %.
    let need_lo = c_nominal * (1. - 0.0826);
    let need_hi = c_nominal * (1. + 0.0420);
    let parasitic = (2.0, 15.0); // buffer, clamp and layout capacitance at the tap, pF
    let tol = 0.01;
    let fixed = 10_000.0;
    let (trim_lo, trim_hi) = (12.0, 60.0);
    let s2: Vec<f64> = [
        0., 10., 11., 12., 13., 15., 16., 18., 20., 22., 24., 27., 30., 33., 36., 39., 43., 47.,
        51., 56., 62., 68., 75., 82., 91., 100., 110., 120., 130., 150., 160., 180., 200., 220.,
        240., 270., 300., 330., 360.,
    ]
    .to_vec();
    let s1: Vec<f64> = [1800., 2000., 2200., 2400., 2700., 3000., 3300., 3600., 3900.].to_vec();
    // Residual X2 that stage 2 + trimmer can absorb for every S2 tolerance outcome.
    let covers = |set: &[f64], lo: f64, hi: f64, x: f64| -> Option<f64> {
        set.iter()
            .map(|&v| {
                let a = x - v * (1. + tol) - lo; // trimmer/next stage must not go below lo
                let b = hi - (x - v * (1. - tol)); // nor above hi
                a.min(b)
            })
            .filter(|m| *m >= 0.)
            .reduce(f64::max)
    };
    let stage2_hi = s2.last().unwrap() * (1. - tol) + trim_hi;
    let mut worst2 = f64::INFINITY;
    let mut x = trim_lo;
    while x <= stage2_hi {
        let m = covers(&s2, trim_lo, trim_hi, x)
            .unwrap_or_else(|| panic!("stage-2 coverage gap at residual {x:.2} pF"));
        worst2 = worst2.min(m);
        x += 0.05;
    }
    let x1_lo = need_lo - parasitic.1 - fixed * (1. + tol);
    let x1_hi = need_hi - parasitic.0 - fixed * (1. - tol);
    let mut worst1 = f64::INFINITY;
    let mut x = x1_lo;
    while x <= x1_hi {
        let m = covers(&s1, trim_lo, stage2_hi, x)
            .unwrap_or_else(|| panic!("stage-1 coverage gap at residual {x:.1} pF"));
        worst1 = worst1.min(m);
        x += 0.5;
    }
    // Overlap between the coverage windows of consecutive select-on-test values.
    let overlap = |set: &[f64], lo: f64, hi: f64| {
        set.windows(2)
            .map(|w| (w[0] * (1. - tol) + hi) - (w[1] * (1. + tol) + lo))
            .fold(f64::INFINITY, f64::min)
    };
    let overlap2 = overlap(&s2, trim_lo, trim_hi);
    let overlap1 = overlap(&s1, trim_lo, stage2_hi);
    assert!(overlap1 > 0. && overlap2 > 0.);
    let _ = (worst1, worst2);
    let nominal_trim = c_nominal - fixed - 3000. - 160.;
    assert!((trim_lo..trim_hi).contains(&(nominal_trim - parasitic.0)));
    report+=&format!("Low-leg C requirement: {need_lo:.1}..{need_hi:.1} pF (archived -8.26/+4.20 % 60 kHz-vs-DC spread on {c_nominal:.1} pF), less {:.0}..{:.0} pF tap parasitics.\nCompensation coverage PASS: fixed 10 nF +/-1 %, S1 E24 1.8-3.9 nF +/-1 %, S2 E24 0-360 pF +/-1 %, trimmer {trim_lo:.0}-{trim_hi:.0} pF. Stage-1 residual {x1_lo:.1}..{x1_hi:.1} pF and stage-2 residual {trim_lo:.0}..{stage2_hi:.1} pF swept without a gap at worst-case part tolerance; adjacent select steps overlap by >= {overlap1:.1} pF (S1) and >= {overlap2:.1} pF (S2), which bounds the allowable measurement error when choosing a value. Nominal 10 nF + 3.0 nF + 160 pF leaves {nominal_trim:.1} pF for trimmer plus parasitics.\n",parasitic.0,parasitic.1);
    report+=&format!("Selected-path DC insertion factor = {selection_gain:.8}, load = {load:.3} ohm; shared RC source R = {source_r:.4} ohm.\n");
    let mag = |f: f64, fine: bool| {
        let mut value = 1. / ((1. + (f / cutoff).powi(2)) * (1. + (f / out_pole).powi(2))).sqrt();
        for pole in [70e6 / (1. + wide_gain), 140e6] {
            value /= (1. + (f / pole).powi(2)).sqrt();
        }
        if fine {
            value /= (1. + (f / (70e6 / fine_stage)).powi(2)).sqrt();
        }
        value
    };
    for (g, range, fine) in [(wide_gain, 1500., false), (wide_gain * fine_stage, 300., true)] {
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
        report+=&format!("Gain {g:.6}: loaded DC estimate {:.3}:1; initial {range:.0} Vpk -> {:.4} Vpk output.\n",2000./total_gain,range/2000.*total_gain);
        report+=&format!("Gain {g:.6}: illustrative first-order cascaded -3dB bandwidth {:.3} MHz; NOT an IC macromodel result or qualification.\n",(lo+hi)/2e6);
    }
    report+="Bandwidth estimate uses U3B (subtractor) noise gain 3.004 / 70 MHz GBW, U12 gain 5.008 / 70 MHz GBW, U3A (driver) 140 MHz unity bandwidth, and the C61 and C62 poles (JP1 bridged); see validation/spice for the vendor-model result.\n";
    let body = 2e6;
    let i_dc = 3000. / (top + bottom);
    report+=&format!("At 3000 V DC per tip: total dissipation {:.3} W/leg; {:.4} W and {:.0} V per 2-Mohm body (five per leg); section capacitor ~600 V.\n",3000f64.powi(2)/(top+bottom),i_dc*i_dc*body,i_dc*body);
    // HV121WF2004T4E: 1 W at 70 C, 3000 V working, 4000 V overload (docs/cost-down.md section 1).
    let p_rated = 1.0f64;
    assert!(i_dc * i_dc * body < 0.25 * p_rated);
    assert!((750f64).powi(2) / body < 0.3 * p_rated); // 1.5 kV DC with the 3-body group bypassed
    report+=&format!("2-Mohm 2512 (HV121WF2004T4E) power-limited continuous voltage sqrt(1 W x 2 Mohm) = {:.0} V. Protective-impedance split 2+3 bodies: if the 3-body group is bypassed at 3 kV DC, each remaining body sees 1500 V and {:.3} W, {:.1} % of the 1 W rating at 70 C: this double condition (fault plus sustained 3 kV DC on the extension envelope) exceeds the rating. At the 1.5 kV guarantee the same fault is {:.3} W ({:.1} %).\n",(p_rated*body).sqrt(),1500f64.powi(2)/body,1500f64.powi(2)/body/p_rated*100.,750f64.powi(2)/body,750f64.powi(2)/body/p_rated*100.);
    report+="At 3000 Vpk sine: roughly 0.450 W/leg (half DC heating), 5.28 mArms at 60 kHz through ideal 6.6 pF.\nAt 70 V/ns: ideal 6.6 pF implies 0.462 A transient; actual lead/shield capacitance adds to this.\n";
    // Rail-referenced warning thresholds (no TL431): tools/budget.rs, with each
    // resistor's tolerance class taken from its MPN in the netlist.
    for (a, b) in [("R87", "R91"), ("R88", "R92"), ("R89", "R93"), ("R71", "R72")] {
        assert_eq!(mpns[a], mpns[b], "threshold ladders must match: {a} {b}");
    }
    let class = |r: &str, nom: f64| budget::Res { nom, tol: budget::tolerance(&mpns[r]) };
    let design = budget::Warn {
        r81: class("R81", 30_000.),
        r82: class("R82", 10_000.),
        r83: class("R83", 29_400.),
        r84: class("R84", 10_000.),
        ra: class("R87", 66_500.),
        rb: class("R88", 1_000.),
        rc: class("R89", 10_000.),
        sense: budget::tolerance(&mpns["R71"]),
    };
    let w = budget::warning(&design);
    assert!(w.tip_max < 1500.);
    assert!(w.wide_late < 1500.);
    assert!(w.fine_late < 300.);
    let (rail_min, rail_max, tip_max, selected_max, wide_late, fine_late, tip_early) = (w.rail_min, w.rail_max, w.tip_max, w.selected_max, w.wide_late, w.fine_late, w.tip_early);
    report+=&format!("Rails: +{:.4} / -{:.4} V nominal; worst-case magnitudes {rail_min:.4}..{rail_max:.4} V (ADP7142 +/-1.8 %, ADP7182 -2.95/+1.97 % ADJ, feedback {}).\n",w.pos_nom,w.neg_nom,if ["R81","R82","R83","R84"].iter().all(|r| budget::tolerance(&mpns[*r]) == budget::PRECISION) {"0.1 % + 25 ppm/C".to_string()} else {format!("R81 {}, R82 {}, R83 {}, R84 {}",budget_class(&mpns["R81"]),budget_class(&mpns["R82"]),budget_class(&mpns["R83"]),budget_class(&mpns["R84"]))});
    report+=&format!("Input warning +/-{:.6} V buffered = {:.2} V/tip nominal. Selected-output warning +/-{:.6} V = {:.2} V differential on wide / {:.2} V on fine (nominal, before gain calibration).\n",w.tip_nom,w.tip_nom*2000.,w.out_nom*2.,w.out_nom*2000.,w.out_nom*400.);
    report+=&format!("Conditional late-trip budget (-25..85C): tip < {tip_max:.2} V; selected comparator < {selected_max:.6} V, corresponding to < {wide_late:.2} V wide / {fine_late:.2} V fine with minimum calibrated gain 98% nominal and actual analog zero offsets <=25mV wide / <=130mV fine. Earliest possible trip (gain <=102%): {tip_early:.0} V/tip, {:.0} V wide / {:.0} V fine.\n",w.wide_early,w.fine_early);
    report+=&format!("Ladder classes: R87/R91 {}, R88/R92 {}, R89/R93 {}; sense R71/R72 {}.\n",budget_class(&mpns["R87"]),budget_class(&mpns["R88"]),budget_class(&mpns["R89"]),budget_class(&mpns["R71"]));
    report+="Warning budget requires measured divider/system gain >=98% nominal, buffer offset within +/-5mV each, actual selected-path zero within the stated range-specific limits and both rails inside their regulated range; scope zero subtraction does not remove the comparator offset. These are qualification acceptance conditions, not assumed measured facts. Comparator finite delay means this LED is not a transient peak guarantee.\n";
    // Clamp current returned into the LDO outputs must stay below their own load.
    // OPA2810 2x2 channels + OPA810: 2.9 mA/channel minimum, -40..125C (3.6 typ);
    // ladder, ADJ divider and latch pull-ups add ~0.2 mA per rail.
    let rail_load_min = 5. * 2.9e-3 + 0.2e-3;
    let clamp_worst = 5.28e-3 * 2f64.sqrt(); // one tap, open bottom bank, 3 kVpk 60 kHz
    assert!(clamp_worst < rail_load_min);
    report+=&format!("Clamp return: single fault (one bottom bank open, 3 kVpk at 60 kHz) injects <= {:.1} mA peak into a rail whose minimum load is ~{:.1} mA, so neither LDO output is back-driven. Normal in-range inputs (|tap| <= 1.5 V) never forward-bias the rail clamps.\n",clamp_worst*1e3,rail_load_min*1e3);
    report+="\nNot established by these checks: CMRR, amplitude/phase accuracy, 5 MHz system bandwidth, input-to-earth capacitance, overload recovery, unpowered input survival, transient withstand, creepage or clearance. PCB, fixed shield and fixture must be qualified together.\n";
    fs::write("validation/checks.txt", &report).unwrap();
    print!("{report}");
}

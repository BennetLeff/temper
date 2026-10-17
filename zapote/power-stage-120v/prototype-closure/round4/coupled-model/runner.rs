use std::{collections::BTreeMap, env, error::Error, fs, path::Path, process::Command};
#[derive(Clone)]
struct Case {
    name: String,
    v: BTreeMap<&'static str, f64>,
}
fn base(name: &str) -> Case {
    Case {
        name: name.into(),
        v: BTreeMap::from([
            ("VRMS", 140.),
            ("PH", 90.),
            ("RDAMP", 3.9),
            ("RP", 11.),
            ("STOP", 0.21),
            ("OPEN", 0.234),
            ("BOPEN", 1.),
            ("DELAY", 2e-6),
            ("LC", 20e-6),
            ("RT", 2.),
            ("CC", 42.3e-6),
            ("VI", 0.),
            ("CR", 0.08),
            ("CL", 1e-6),
            ("DT", 443e-9),
            ("PSET", 1500.),
            ("SHORT", 0.),
            ("DS", 0.),
            ("FO", 0.),
            ("CAPSHORT", 0.),
            ("AUXPEAK", 30.),
            ("STEP", 0.5e-6),
            ("END", 0.26),
            ("CONTACTDELAY", 0.024),
            ("BUSSHORT", 0.),
        ]),
    }
}
fn control_pwl(c: &Case) -> Result<String, Box<dyn Error>> {
    if c.v["PSET"] == 0.0 {
        return Ok("Vgf gf 0 0".into());
    }
    let mut points = String::from("Vgf gf 0 PWL(0 0");
    let mut previous = 0.0;
    for line in include_str!("conductance-study.csv").lines().skip(1) {
        let cols: Vec<&str> = line.split(',').collect();
        if cols.len() != 5 {
            return Err("bad control CSV".into());
        }
        let line_v: f64 = cols[0].parse()?;
        if line_v != c.v["VRMS"] {
            continue;
        }
        let t = cols[1].parse::<f64>()? + 0.045;
        let g: f64 = cols[2].parse()?;
        if t > c.v["END"] {
            break;
        }
        points.push_str(&format!(
            " {:.12e} {:.12e} {:.12e} {:.12e}",
            t - 1e-9,
            previous,
            t + 1e-6,
            g
        ));
        previous = g;
    }
    points.push(')');
    Ok(points)
}
fn render(template: &str, c: &Case) -> Result<String, Box<dyn Error>> {
    let mut s = template.replace("@CONTROL@", &control_pwl(c)?);
    for (k, v) in &c.v {
        if !v.is_finite() {
            return Err("nonfinite parameter".into());
        }
        s = s.replace(&format!("@{k}@"), &format!("{v:.12e}"));
    }
    if s.contains('@') {
        return Err("unresolved token".into());
    }
    Ok(s)
}
const METRICS: [&str; 19] = [
    "bus_pk",
    "tank_pk",
    "tank_current_pk",
    "catch_pk",
    "catch_i_pk",
    "catch_i2t",
    "bridge_i2t",
    "inlet_i2t",
    "precharge_j",
    "damper_j",
    "tank_i2t",
    "bus_end",
    "catch_end",
    "trip_end",
    "precharge_bus",
    "precharge_drop",
    "proof_i2t",
    "qualification",
    "precharge_crest_drop",
];
fn parse(s: &str) -> Result<Vec<f64>, Box<dyn Error>> {
    let mut out = Vec::new();
    if s.contains("Timestep too small") || s.contains("run simulation(s) aborted") {
        return Err("ngspice aborted".into());
    }
    for m in METRICS {
        let vals: Vec<_> = s
            .lines()
            .filter_map(|l| {
                let (name, value) = l.split_once('=')?;
                if name.trim() == m {
                    value.split_whitespace().next()
                } else {
                    None
                }
            })
            .collect();
        if vals.len() != 1 {
            return Err(format!("expected one {m}, got {}", vals.len()).into());
        }
        let x: f64 = vals[0].parse()?;
        if !x.is_finite() {
            return Err("nonfinite metric".into());
        }
        out.push(x)
    }
    Ok(out)
}
fn cases() -> Vec<Case> {
    let mut cs = vec![];
    for (name, key, value) in [
        ("nominal", "VRMS", 120.),
        ("low_line", "VRMS", 100.),
        ("crest_140", "VRMS", 140.),
        ("zero_phase", "PH", 0.),
        ("detuned_low_loss", "RT", 0.3),
        ("larger_coil", "LC", 40e-6),
        ("damper_open", "RDAMP", 1e9),
        ("charged_catch", "VI", 240.),
        ("catch_fuse_open", "FO", 1.),
        ("catch_diode_short", "DS", 1.),
        ("catch_cap_short", "CAPSHORT", 1.),
        ("switch_short", "SHORT", 1.),
        ("delayed_inhibit", "DELAY", 20e-6),
        ("rail_loss_order", "BOPEN", 0.210001),
        ("resistor_one_open", "RP", 22.),
        ("resistor_short", "RP", 0.001),
        ("pc125", "RP", 12.5),
        ("pc125_high_r", "RP", 13.125),
        ("pc125_low_r", "RP", 11.875),
        ("series88", "RP", 88.),
        ("series88_one_short", "RP", 66.),
        ("catch_route_3u", "CL", 3e-6),
    ] {
        let mut c = base(name);
        c.v.insert(key, value);
        cs.push(c)
    }
    let mut c = base("precharge_short_timeout");
    c.v.insert("BUSSHORT", 1.);
    c.v.insert("BOPEN", 0.);
    c.v.insert("OPEN", 0.470458);
    c.v.insert("END", 0.5);
    c.v.insert("STOP", 1.);
    c.v.insert("PSET", 0.);
    cs.push(c.clone());
    c.name = "series88_short_timeout".into();
    c.v.insert("RP", 88.);
    cs.push(c);
    let mut c = base("switch_reference");
    c.v.insert("STOP", 0.138);
    c.v.insert("OPEN", 0.162);
    c.v.insert("END", 0.168);
    cs.push(c);
    let mut c = base("high_energy");
    c.v.insert("RT", 0.3);
    c.v.insert("STOP", 0.9);
    c.v.insert("OPEN", 0.924);
    c.v.insert("END", 1.0);
    c.v.insert("DELAY", 20e-6);
    c.v.insert("CL", 3e-6);
    cs.push(c);
    let mut c = base("pc125_short_timeout");
    c.v.insert("RP", 11.875);
    c.v.insert("BUSSHORT", 1.);
    c.v.insert("BOPEN", 0.);
    c.v.insert("OPEN", 0.470458);
    c.v.insert("END", 0.5);
    c.v.insert("STOP", 1.);
    c.v.insert("PSET", 0.);
    cs.push(c);
    let refined: Vec<_> = cs
        .iter()
        .filter(|c| ["crest_140", "detuned_low_loss", "catch_cap_short"].contains(&c.name.as_str()))
        .cloned()
        .collect();
    for mut c in refined {
        c.name.push_str("_refined");
        c.v.insert("STEP", 0.25e-6);
        cs.push(c);
    }
    let mut c = base("detuned_low_loss_fine");
    c.v.insert("RT", 0.3);
    c.v.insert("STEP", 0.125e-6);
    cs.push(c);
    cs
}
fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<_> = env::args().collect();
    let out = Path::new(args.get(1).ok_or("output argument required")?);
    if out.exists() {
        return Err("output exists: require fresh directory".into());
    }
    fs::create_dir_all(out)?;
    fs::write(out.join("STATUS"), "INCOMPLETE\n")?;
    let version = Command::new("ngspice").arg("--version").output()?;
    let vs = String::from_utf8(version.stdout)?;
    if !vs.contains("ngspice-45.2") {
        return Err("requires ngspice45.2".into());
    }
    fs::write(out.join("ngspice-version.txt"), vs)?;
    let template =
        fs::read_to_string(args.get(3).map(String::as_str).unwrap_or(
            "zapote/power-stage-120v/prototype-closure/round4/coupled-model/reduced.cir",
        ))?;
    let filter = args.get(2);
    if let Some(f) = filter {
        if f != "all" && !cases().iter().any(|c| c.name == *f) {
            return Err("unknown case".into());
        }
    }
    let mut csv = format!("case,{}\n", METRICS.join(","));
    for c in cases()
        .into_iter()
        .filter(|c| filter.is_none_or(|f| f == "all" || c.name == *f))
    {
        let dir = out.join(&c.name);
        fs::create_dir(&dir)?;
        fs::write(dir.join("joined.cir"), render(&template, &c)?)?;
        let r = Command::new("ngspice")
            .args(["-b", "joined.cir"])
            .current_dir(&dir)
            .output()?;
        let mut log = String::from_utf8(r.stdout)?;
        log.push_str(&String::from_utf8(r.stderr)?);
        fs::write(dir.join("ngspice.log"), &log)?;
        if !r.status.success() {
            return Err(format!("{} ngspice status {}", c.name, r.status).into());
        }
        let values = parse(&log)?;
        csv.push_str(&format!(
            "{},{}\n",
            c.name,
            values
                .iter()
                .map(|v| format!("{v:.10e}"))
                .collect::<Vec<_>>()
                .join(",")
        ));
        fs::write(out.join("results.csv"), &csv)?;
        println!(
            "{}: Vbus={} Vtank={} Ipk={}",
            c.name, values[0], values[1], values[2]
        );
    }
    fs::write(out.join("STATUS"), "SIMULATED_DIAGNOSTIC_ONLY\n")?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_missing_metrics() {
        assert!(parse("bus_pk = 2").is_err())
    }
    #[test]
    fn rejects_tokens() {
        assert!(render("@MISSING@", &base("x")).is_err())
    }
    #[test]
    fn rejects_nonfinite_parameters() {
        let mut c = base("x");
        c.v.insert("VRMS", f64::NAN);
        assert!(render("@VRMS@", &c).is_err())
    }
    #[test]
    fn all_cases_resolve() {
        for t in [include_str!("joined.cir"), include_str!("reduced.cir")] {
            for c in cases() {
                assert!(!render(t, &c).unwrap().contains('@'))
            }
        }
    }
    fn complete_log() -> String {
        METRICS.iter().map(|m| format!("{m}= 1.0\n")).collect()
    }
    #[test]
    fn parses_long_names_without_space_before_equals() {
        assert_eq!(parse(&complete_log()).unwrap(), vec![1.0; METRICS.len()]);
    }
    #[test]
    fn rejects_duplicate_and_nonfinite_measurements() {
        assert!(parse(&(complete_log() + "bus_pk = 2\n")).is_err());
        assert!(parse(&complete_log().replace("bus_pk= 1.0", "bus_pk= NaN")).is_err());
    }
    #[test]
    fn rejects_aborted_run_even_if_metrics_are_present() {
        assert!(parse(&(complete_log() + "Timestep too small\n")).is_err());
    }
}

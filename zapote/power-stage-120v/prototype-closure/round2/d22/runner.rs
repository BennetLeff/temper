//! Standalone ngspice experiment adapter. No shared Cargo/PyO3 cache is touched.
use std::{error::Error, fs, path::Path, process::Command};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
#[derive(Clone)]
struct Case {
    name: String,
    vrms: f64,
    freq: f64,
    phase: f64,
    r: f64,
    l: f64,
    leakage: f64,
    damper: f64,
    bleed: f64,
    power: f64,
    cpl: f64,
    burst: f64,
    step: f64,
    caps: f64,
    precharge: f64,
}
fn cases() -> Vec<Case> {
    let base = Case {
        name: "base".into(),
        vrms: 120.,
        freq: 60.,
        phase: 0.,
        r: 0.1,
        l: 20e-6,
        leakage: 18e-6,
        damper: 3.9,
        bleed: 30000.,
        power: 1500.,
        cpl: 0.,
        burst: 0.,
        step: 2e-6,
        caps: 1.,
        precharge: 0.,
    };
    let mut cases = Vec::new();
    for voltage in [100., 120., 140.] {
        for cpl in [0., 1.] {
            for burst in [0., 1.] {
                let mut c = base.clone();
                c.vrms = voltage;
                c.cpl = cpl;
                c.burst = burst;
                c.name = format!("v{voltage}-cpl{cpl}-burst{burst}");
                cases.push(c);
            }
        }
    }
    for (name, r, l, phase, freq, leakage, damper, bleed, caps) in [
        ("crest-close", 0.1, 20e-6, 90., 60., 18e-6, 3.9, 30000., 1.),
        ("weak-source", 1., 500e-6, 90., 60., 18e-6, 3.9, 30000., 1.),
        ("low-leakage", 0.1, 20e-6, 90., 60., 9e-6, 3.9, 30000., 0.9),
        (
            "high-leakage",
            0.1,
            20e-6,
            90.,
            60.,
            27e-6,
            3.9,
            30000.,
            1.1,
        ),
        ("damper-open", 0.1, 20e-6, 90., 60., 18e-6, 1e9, 30000., 1.),
        (
            "damper-short",
            0.1,
            20e-6,
            90.,
            60.,
            18e-6,
            0.035,
            30000.,
            1.,
        ),
        ("bleed-open", 0.1, 20e-6, 90., 60., 18e-6, 3.9, 1e12, 1.),
        ("line50", 0.1, 20e-6, 90., 50., 18e-6, 3.9, 30000., 1.),
    ] {
        let mut c = base.clone();
        c.name = name.into();
        c.vrms = 140.;
        c.cpl = 1.;
        c.burst = 1.;
        c.r = r;
        c.l = l;
        c.phase = phase;
        c.freq = freq;
        c.leakage = leakage;
        c.damper = damper;
        c.bleed = bleed;
        c.caps = caps;
        cases.push(c);
    }
    for phase in [0., 90., 180., 270.] {
        let mut c = base.clone();
        c.name = format!("precharge10-phase{phase}");
        c.vrms = 140.;
        c.phase = phase;
        c.precharge = 10.;
        c.burst = 1.;
        cases.push(c);
    }
    let refinements: Vec<_> = cases
        .iter()
        .filter(|c| {
            [
                "crest-close",
                "weak-source",
                "damper-open",
                "damper-short",
                "v100-cpl1-burst0",
                "precharge10-phase90",
            ]
            .contains(&c.name.as_str())
        })
        .cloned()
        .collect();
    for mut c in refinements {
        c.name.push_str("-fine");
        c.step = 0.5e-6;
        cases.push(c);
    }
    cases
}
fn deck(template: &str, c: &Case) -> String {
    let mut s = template.to_owned();
    for (k, v) in [
        ("VRMS", c.vrms),
        ("FREQ", c.freq),
        ("PHASE", c.phase),
        ("RSOURCE", c.r),
        ("LSOURCE", c.l),
        ("LDM", c.leakage),
        ("RDAMP", c.damper),
        ("RBLEED", c.bleed),
        ("POWER", c.power),
        ("CPL", c.cpl),
        ("BURST", c.burst),
        ("STEP", c.step),
        ("CAPMULT", c.caps),
        ("PRECHARGE", c.precharge),
    ] {
        s = s.replace(&format!("@{k}@"), &format!("{v:.12e}"));
    }
    s
}
fn parse(text: &str) -> Result<Vec<[f64; 8]>> {
    let expected = [
        "time",
        "v(source)",
        "i(Lsource)",
        "bus",
        "damper",
        "xout",
        "iload",
        "v(mid)",
    ];
    if text
        .lines()
        .next()
        .ok_or("missing header")?
        .split_whitespace()
        .collect::<Vec<_>>()
        != expected
    {
        return Err("wrong waveform variables".into());
    }
    let mut rows = Vec::new();
    for line in text.lines().skip(1) {
        let v: Vec<f64> = line
            .split_whitespace()
            .map(str::parse)
            .collect::<std::result::Result<_, _>>()?;
        if v.len() != 8 || v.iter().any(|x| !x.is_finite()) {
            return Err("invalid waveform row".into());
        }
        let row: [f64; 8] = v.try_into().map_err(|_| "column count")?;
        if rows.last().is_some_and(|p: &[f64; 8]| p[0] >= row[0]) {
            return Err("nonmonotonic time".into());
        }
        rows.push(row);
    }
    if rows.len() < 1000
        || rows.first().ok_or("empty")?[0] > 1e-6
        || rows.last().ok_or("empty")?[0] < 0.299999
    {
        return Err("truncated waveform".into());
    }
    Ok(rows)
}
fn integral(rows: &[[f64; 8]], start: f64, end: f64, f: impl Fn(&[f64; 8]) -> f64) -> f64 {
    rows.windows(2)
        .filter_map(|w| {
            let a = w[0][0].max(start);
            let b = w[1][0].min(end);
            if b <= a {
                None
            } else {
                let slope = (f(&w[1]) - f(&w[0])) / (w[1][0] - w[0][0]);
                Some((b - a) * (f(&w[0]) + slope * ((a + b) / 2. - w[0][0])))
            }
        })
        .sum()
}
fn metrics(rows: &[[f64; 8]], c: &Case) -> [f64; 12] {
    // Last100ms contains integer line and burst cycles for both50/60Hz.
    let rms = |col: usize| (integral(rows, 0.2, 0.3, |r| r[col] * r[col]) / 0.1).sqrt();
    let peak = rows
        .iter()
        .filter(|r| r[0] <= 0.04)
        .map(|r| r[2].abs())
        .fold(0., f64::max);
    let minbus = rows
        .iter()
        .filter(|r| r[0] >= 0.2)
        .map(|r| r[3])
        .fold(f64::INFINITY, f64::min);
    let maxbus = rows.iter().map(|r| r[3]).fold(0., f64::max);
    [
        peak,
        integral(rows, 0., 0.04, |r| r[2] * r[2]),
        rms(2),
        minbus,
        maxbus,
        rms(4).powi(2) * c.damper,
        rms(5),
        integral(rows, 0.2, 0.3, |r| r[3] * r[6]) / 0.1,
        integral(rows, 0.2, 0.3, |r| r[1] * r[2]) / 0.1,
        integral(rows, 0., 0.04, |r| r[4] * r[4] * c.damper),
        rows.iter()
            .filter(|r| r[0] <= 0.04)
            .map(|r| r[3])
            .fold(0., f64::max),
        integral(rows, 0., 0.02, |r| r[2] * r[2] * c.precharge),
    ]
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    let replay = args.len() == 4 && args[3] == "--replay";
    if args.len() != 3 && !replay {
        return Err("usage: runner TEMPLATE NEW_OUTPUT_DIR [--replay]".into());
    }
    let out = Path::new(&args[2]);
    if out.exists() && !replay {
        return Err("output must not exist; preserve prior evidence".into());
    }
    if replay && !out.is_dir() {
        return Err("replay input directory missing".into());
    }
    fs::create_dir_all(out)?;
    fs::write(out.join("STATUS"), "INCOMPLETE\n")?;
    let version = Command::new("ngspice").arg("--version").output()?;
    if !version.status.success()
        || !String::from_utf8_lossy(&version.stdout).contains("ngspice-45.2")
    {
        return Err("requires ngspice45.2".into());
    }
    fs::write(out.join("ngspice-version.txt"), version.stdout)?;
    let template = fs::read_to_string(&args[1])?;
    let mut csv="case,inrush_peak_A,inrush_I2t_A2s,line_rms_A,bus_min_V,bus_peak_V,damper_steady_W,xout_rms_A,load_W,input_W,damper_start_J,bus_start_peak_V,precharge_J\n".to_owned();
    let mut all = Vec::new();
    for c in cases() {
        let dir = out.join(&c.name);
        if replay {
            if fs::read_to_string(dir.join("case.cir"))? != deck(&template, &c) {
                return Err(format!("deck drift {}", c.name).into());
            }
        } else {
            fs::create_dir(&dir)?;
            fs::write(dir.join("case.cir"), deck(&template, &c))?;
            let p = Command::new("ngspice")
                .args(["-n", "-b", "case.cir"])
                .current_dir(&dir)
                .output()?;
            fs::write(dir.join("stdout.log"), &p.stdout)?;
            fs::write(dir.join("stderr.log"), &p.stderr)?;
            if !p.status.success() {
                return Err(format!("ngspice failed {}", c.name).into());
            }
        }
        let rows = parse(&fs::read_to_string(dir.join("waves.txt"))?)?;
        let m = metrics(&rows, &c);
        csv.push_str(&c.name);
        for x in m {
            csv.push_str(&format!(",{x:.9}"));
        }
        csv.push('\n');
        println!(
            "{} line {:.3}A damper {:.3}W peakbus {:.2}V",
            c.name, m[2], m[5], m[4]
        );
        all.push((c.name, m));
    }
    fs::write(out.join("results.csv"), csv)?;
    let mut convergence = "case,max_relative_metric_delta,criterion,status\n".to_owned();
    for (name, fine) in &all {
        if let Some(base) = name.strip_suffix("-fine") {
            let (_, coarse) = all
                .iter()
                .find(|(n, _)| n == base)
                .ok_or("missing refinement base")?;
            // Exclude near-zero bus minima; compare peaks, integrals, RMS and powers.
            let delta = (0..12)
                .filter(|i| *i != 3)
                .map(|i| (coarse[i] - fine[i]).abs() / fine[i].abs().max(0.01))
                .fold(0., f64::max);
            convergence.push_str(&format!(
                "{base},{delta:.9},0.02,{}\n",
                if delta <= 0.02 { "PASS" } else { "FAIL" }
            ));
            if delta > 0.02 {
                fs::write(out.join("convergence.csv"), convergence)?;
                return Err("timestep refinement >2%".into());
            }
        }
    }
    fs::write(out.join("convergence.csv"), convergence)?;
    fs::write(out.join("STATUS"), "SIMULATED_DIAGNOSTIC_ONLY\n")?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_truncated_waveform() {
        assert!(
            parse("time v(source) i(Lsource) bus damper xout iload v(mid)\n0 0 0 0 0 0 0 0\n")
                .is_err()
        );
    }
    #[test]
    fn rejects_wrong_variables() {
        assert!(parse("time v(other) i(Lsource) bus damper xout iload v(mid)\n").is_err());
    }
    #[test]
    fn integration_clips_interval() {
        let rows = [[0.; 8], [2.; 8]];
        assert!((integral(&rows, 0.5, 1.5, |r| r[1]) - 1.).abs() < 1e-12);
    }
    #[test]
    fn differential_leakage_is_not_doubled() {
        let t = include_str!("line-model.cir");
        assert!(t.contains("Lnew nl mid {LDM}"));
        assert!(!deck(t, &cases()[0]).contains('@'));
    }
    #[test]
    fn refinement_covers_faults() {
        assert_eq!(
            cases().iter().filter(|c| c.name.ends_with("-fine")).count(),
            6
        );
    }
}

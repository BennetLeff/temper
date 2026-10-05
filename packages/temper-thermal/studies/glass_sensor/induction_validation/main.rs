//! Induction sensitivity and evidence evaluation. No instrument control.
use std::{collections::BTreeMap, env, error::Error, f64::consts::PI, fs, path::Path};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
const MU0: f64 = 4.0e-7 * PI;
#[derive(Clone, Copy)]
struct Cap {
    radius: f64,
    inner: f64,
    roof: f64,
    skirt: f64,
    resistivity: f64,
    mu_r: f64,
}
impl Cap {
    fn selected() -> Self {
        Self {
            radius: 0.005,
            inner: 0.0046,
            roof: 0.00015,
            skirt: 0.00185,
            resistivity: 0.75e-6,
            mu_r: 1.0,
        }
    }
    fn volume(self) -> f64 {
        PI * (self.radius.powi(2) * self.roof
            + (self.radius.powi(2) - self.inner.powi(2)) * self.skirt)
    }
    fn powers(self, hz: f64, b_rms: f64) -> (f64, f64) {
        let common = PI * (2.0 * PI * hz * b_rms).powi(2) / (8.0 * self.resistivity);
        (
            common * self.roof * self.radius.powi(4),
            common * self.skirt * (self.radius.powi(4) - self.inner.powi(4)),
        )
    }
    fn skin(self, hz: f64) -> f64 {
        (self.resistivity / (PI * hz * MU0 * self.mu_r)).sqrt()
    }
    // Engineering small-parameter screens, not rigorous relative-error bounds.
    fn validity(self, hz: f64) -> (f64, f64, bool) {
        let wall = self.roof.max(self.radius - self.inner);
        let skin_ratio = wall / self.skin(hz);
        let shielding = MU0 * self.mu_r / self.resistivity * 2.0 * PI * hz * self.radius * wall;
        (
            skin_ratio,
            shielding,
            skin_ratio <= 0.3 && shielding <= 0.3 && self.mu_r <= 1.05,
        )
    }
}
fn sweep(out: &Path) -> Result<()> {
    fs::create_dir_all(out)?;
    let mut csv=String::from("evidence,geometry,hz,b_rms_mT,resistivity_ohm_m,mu_r,roof_W,skirt_W,total_W,skin_mm,wall_over_skin,sheet_shielding_parameter,regime,adiabatic_initial_K_s,deltaT_if_G_0p01_K,deltaT_if_G_0p1_K\n");
    for (name, roof, skirt) in [
        ("candidate_316L", 0.00015, 0.00185),
        ("prior_geometry_316L", 0.00035, 0.00165),
    ] {
        for resistivity in [0.75e-6, 1.125e-6, 1.5e-6] {
            for mu_r in [1.0, 1.05, 2.0] {
                for hz in [5000., 10000., 20000., 33000., 40000., 60000.] {
                    for b in [0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3] {
                        let c = Cap {
                            roof,
                            skirt,
                            resistivity,
                            mu_r,
                            ..Cap::selected()
                        };
                        let (r, s) = c.powers(hz, b);
                        let (sk, sh, valid) = c.validity(hz);
                        csv.push_str(&format!("SIMULATED,{name},{hz},{},{resistivity},{mu_r},{r:.9},{s:.9},{:.9},{:.6},{sk:.6},{sh:.6},{},{:.6},{:.6},{:.6}\n",b*1000.,r+s,c.skin(hz)*1000.,if valid {"SMALL_PARAMETER_SCREEN"} else {"OUTSIDE_SMALL_PARAMETER_REGIME"},(r+s)/(8000.*500.*c.volume()),(r+s)/0.01,(r+s)/0.1));
                    }
                }
            }
        }
    }
    fs::write(out.join("cap_sensitivity.csv"), csv)?;
    let mut csv = String::from(
        "evidence,hz,b_rms_mT,lead_loop_mm2,excitation_mA,induced_rms_mV,equivalent_unfiltered_K\n",
    );
    for hz in [20000., 40000., 60000.] {
        for b in [0.1e-3, 1e-3, 10e-3] {
            for area in [0.1e-6, 1e-6, 10e-6, 100e-6] {
                for current in [0.3e-3, 1e-3] {
                    let v = 2.0 * PI * hz * b * area;
                    csv.push_str(&format!(
                        "SIMULATED,{hz},{},{},{},{},{:.6}\n",
                        b * 1000.,
                        area * 1e6,
                        current * 1000.,
                        v * 1000.,
                        v / (current * 0.385)
                    ));
                }
            }
        }
    }
    fs::write(out.join("lead_coupling.csv"), csv)?;
    Ok(())
}
fn fields<'a>(line: &'a str, n: usize) -> Result<Vec<&'a str>> {
    let f: Vec<_> = line.split(',').collect();
    if f.len() != n || f.iter().any(|s| s.is_empty() || s.contains('"')) {
        return Err("empty, quoted or wrong-count CSV field".into());
    }
    Ok(f)
}
fn number(s: &str) -> Result<f64> {
    let x: f64 = s.parse()?;
    if !x.is_finite() {
        return Err("non-finite number".into());
    }
    Ok(x)
}
fn nonnegative(s: &str) -> Result<f64> {
    let x = number(s)?;
    if x < 0. {
        return Err("negative magnitude".into());
    }
    Ok(x)
}
fn metadata(path: &Path) -> Result<BTreeMap<String, String>> {
    let data = fs::read_to_string(path)?;
    let mut m: BTreeMap<String, String> = BTreeMap::new();
    for line in data
        .lines()
        .filter(|s| !s.is_empty() && !s.starts_with('#'))
    {
        let (k, v) = line.split_once('=').ok_or("metadata expects key=value")?;
        if v.is_empty() || m.insert(k.into(), v.into()).is_some() {
            return Err("missing/duplicate metadata".into());
        }
    }
    for k in [
        "evidence",
        "run_id",
        "assembly_revision",
        "instrument_calibration",
        "raw_sha256",
        "requirement_source",
    ] {
        if !m.contains_key(k) {
            return Err(format!("missing metadata {k}").into());
        }
    }
    if !matches!(m["evidence"].as_str(), "MEASURED" | "SYNTHETIC") {
        return Err("invalid evidence class".into());
    }
    if m["evidence"] == "MEASURED"
        && [
            "instrument_calibration",
            "assembly_revision",
            "requirement_source",
        ]
        .iter()
        .any(|k| m[*k].contains("PENDING") || m[*k].contains("SYNTHETIC"))
    {
        return Err("unresolved measured provenance".into());
    }
    let h = &m["raw_sha256"];
    if h.len() != 64 || !h.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("raw_sha256 must be full digest".into());
    }
    // The CLI verifies this digest against the exact CSV bytes before evaluation.
    Ok(m)
}
fn value(m: &BTreeMap<String, String>, key: &str) -> Result<f64> {
    nonnegative(m.get(key).ok_or(format!("missing metadata {key}"))?)
}
#[derive(Clone, Copy)]
struct Sample {
    time: f64,
    sensor: f64,
    reference: f64,
    ref2: f64,
    current: f64,
    hz: f64,
}
fn pair_effect(before: Sample, on: Sample, after: Sample) -> Result<f64> {
    if !(before.time < on.time && on.time < after.time) {
        return Err("pair is not time-bracketed".into());
    }
    let w = (on.time - before.time) / (after.time - before.time);
    Ok(on.sensor
        - on.reference
        - ((1. - w) * (before.sensor - before.reference) + w * (after.sensor - after.reference)))
}
fn paired(csv: &Path, m: &BTreeMap<String, String>) -> Result<String> {
    let data = fs::read_to_string(csv)?;
    let mut lines = data.lines();
    if lines.next()!=Some("pair_id,phase,time_s,pan_ref_c,sensor_c,ref2_c,coil_current_a,drive_hz,acquisition_valid"){return Err("wrong paired CSV header".into());}
    let mut groups: BTreeMap<String, BTreeMap<String, Sample>> = BTreeMap::new();
    let mut prev = -1.;
    let ur = value(m, "reference_agreement_uncertainty_c")?;
    let rb = value(m, "reference_agreement_budget_c")?;
    for line in lines {
        let f = fields(line, 9)?;
        let s = Sample {
            time: nonnegative(f[2])?,
            reference: number(f[3])?,
            sensor: number(f[4])?,
            ref2: number(f[5])?,
            current: nonnegative(f[6])?,
            hz: nonnegative(f[7])?,
        };
        if s.time <= prev || f[8] != "1" {
            return Err("non-monotonic time or invalid acquisition".into());
        }
        prev = s.time;
        if (s.reference - s.ref2).abs() + ur > rb {
            return Err(
                "independent references disagree; possible reference EMI or spatial offset".into(),
            );
        }
        if !matches!(f[1], "off_before" | "on" | "off_after") {
            return Err("unknown phase".into());
        }
        if (f[1] == "on" && (s.current <= 0. || s.hz <= 0.)) || (f[1] != "on" && s.current != 0.) {
            return Err("coil phase/current inconsistent".into());
        }
        if groups
            .entry(f[0].into())
            .or_default()
            .insert(f[1].into(), s)
            .is_some()
        {
            return Err("duplicate phase within pair".into());
        }
    }
    if groups.len() < 3 {
        return Err("at least three independent bracket pairs required".into());
    }
    let u = value(m, "paired_expanded_uncertainty_c")?;
    let budget = value(m, "paired_budget_c")?;
    let max_gap = value(m, "max_bracket_s")?;
    let mut text=String::from("pair_id,incremental_on_minus_off_c,expanded_uncertainty_c,absolute_bound_c,engineering_screen\n");
    let mut all = true;
    for (id, g) in groups {
        let b = *g.get("off_before").ok_or("missing off_before")?;
        let o = *g.get("on").ok_or("missing on")?;
        let a = *g.get("off_after").ok_or("missing off_after")?;
        if a.time - b.time > max_gap {
            return Err("bracket exceeds specified thermal drift interval".into());
        }
        let effect = pair_effect(b, o, a)?;
        let bound = effect.abs() + u;
        let pass = bound <= budget;
        all &= pass;
        text.push_str(&format!(
            "{id},{effect:.6},{u:.6},{bound:.6},{}\n",
            if pass {
                "WITHIN_CONFIGURED_BUDGET"
            } else {
                "EXCEEDS_CONFIGURED_BUDGET"
            }
        ));
    }
    text.push_str(&format!(
        "evidence={},overall={}\n",
        m["evidence"],
        if m["evidence"] == "SYNTHETIC" {
            "SYNTHETIC_ONLY_NO_HARDWARE_VERDICT"
        } else if all {
            "MEASURED_SCREEN_WITHIN_BUDGET_NOT_QUALIFICATION"
        } else {
            "MEASURED_SCREEN_FAIL"
        }
    ));
    Ok(text)
}
const REQUIRED: [(&str, &str, &str); 8] = [
    ("touch_current", "mA", "max"),
    ("insulation_resistance", "Mohm", "min"),
    ("water_ingress", "mg", "max"),
    ("thermal_cycles", "cycles", "min"),
    ("cleaning_cycles", "cycles", "min"),
    ("return_force_after", "N", "min"),
    ("drift_after", "degC_abs", "max"),
    ("corrosion_after", "defects", "max"),
];
fn endurance(csv: &Path, m: &BTreeMap<String, String>) -> Result<String> {
    let data = fs::read_to_string(csv)?;
    let mut lines = data.lines();
    if lines.next()!=Some("check,unit,value,expanded_uncertainty,limit,direction,requirement_source,performed,record_id"){return Err("wrong endurance CSV header".into());}
    let mut rows = BTreeMap::new();
    let mut output = String::from("check,guarded_value,configured_limit,engineering_screen\n");
    let mut all = true;
    for line in lines {
        let f = fields(line, 9)?;
        if !REQUIRED.iter().any(|r| r.0 == f[0]) {
            return Err("unknown endurance check".into());
        }
        if rows
            .insert(
                f[0].to_owned(),
                f.into_iter().map(str::to_owned).collect::<Vec<_>>(),
            )
            .is_some()
        {
            return Err("duplicate endurance check".into());
        }
    }
    for (check, unit, direction) in REQUIRED {
        let f = rows
            .get(check)
            .ok_or(format!("NOT_RUN: missing required measurement {check}"))?;
        if f[1] != unit || f[5] != direction {
            return Err(format!("wrong unit/direction for {check}").into());
        }
        if f[7] != "1"
            || f[6].contains("PENDING")
            || (m["evidence"] == "MEASURED" && f[6].contains("SYNTHETIC"))
        {
            return Err(format!("NOT_RUN: missing measurement/requirement for {check}").into());
        }
        let v = nonnegative(&f[2])?;
        let u = nonnegative(&f[3])?;
        let limit = nonnegative(&f[4])?;
        let guarded = if direction == "max" { v + u } else { v - u };
        let pass = if direction == "max" {
            guarded <= limit
        } else {
            guarded >= limit
        };
        all &= pass;
        output.push_str(&format!(
            "{check},{guarded:.6},{limit:.6},{}\n",
            if pass {
                "WITHIN_CONFIGURED_LIMIT"
            } else {
                "EXCEEDS_CONFIGURED_LIMIT"
            }
        ));
    }
    output.push_str(&format!(
        "evidence={},overall={}\n",
        m["evidence"],
        if m["evidence"] == "SYNTHETIC" {
            "SYNTHETIC_ONLY_NO_HARDWARE_VERDICT"
        } else if all {
            "MEASURED_SCREEN_WITHIN_LIMIT_NOT_QUALIFICATION"
        } else {
            "MEASURED_SCREEN_FAIL"
        }
    ));
    Ok(output)
}
fn verify_hash(csv: &Path, metadata: &BTreeMap<String, String>) -> Result<()> {
    let output = std::process::Command::new("shasum")
        .args(["-a", "256"])
        .arg(csv)
        .output()?;
    let text = String::from_utf8(output.stdout)?;
    if !output.status.success()
        || text.split_whitespace().next() != Some(metadata["raw_sha256"].as_str())
    {
        return Err("raw CSV digest mismatch".into());
    }
    Ok(())
}
fn run() -> Result<bool> {
    let a: Vec<_> = env::args().collect();
    match a.get(1).map(String::as_str) {
        Some("sweep") if a.len() == 3 => {
            sweep(Path::new(&a[2]))?;
            Ok(true)
        }
        Some("paired") | Some("endurance") if a.len() == 4 => {
            let m = metadata(Path::new(&a[3]))?;
            verify_hash(Path::new(&a[2]), &m)?;
            let result = if a[1] == "paired" {
                paired(Path::new(&a[2]), &m)?
            } else {
                endurance(Path::new(&a[2]), &m)?
            };
            print!("{result}");
            Ok(!result.contains("MEASURED_SCREEN_FAIL"))
        }
        _ => Err("usage: induction sweep OUT | paired CSV META | endurance CSV META".into()),
    }
}
fn main() {
    match run() {
        Ok(true) => (),
        Ok(false) => std::process::exit(1),
        Err(e) => {
            eprintln!("INCOMPLETE_OR_INVALID: {e}");
            std::process::exit(2);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn power_is_quadratic_in_field() {
        let c = Cap::selected();
        assert!((c.powers(40000., 0.002).0 / c.powers(40000., 0.001).0 - 4.).abs() < 1e-12);
    }
    #[test]
    fn roof_matches_ring_integration() {
        let c = Cap::selected();
        let f = 40000.;
        let b = 0.001;
        let dr = c.radius / 100000.;
        let p: f64 = (0..100000)
            .map(|i| {
                let r = (i as f64 + 0.5) * dr;
                let e = PI * f * b * r;
                e * e / c.resistivity * 2. * PI * r * dr * c.roof
            })
            .sum();
        assert!((p / c.powers(f, b).0 - 1.).abs() < 1e-9);
    }
    #[test]
    fn skirt_cannot_be_omitted() {
        let (r, s) = Cap::selected().powers(40000., 0.001);
        assert!(s > 3. * r);
    }
    #[test]
    fn frequency_range_outside_small_parameter_regime_is_flagged() {
        assert!(!Cap::selected().validity(40000.).2);
    }
    #[test]
    fn low_frequency_screen_can_be_valid() {
        assert!(Cap::selected().validity(5000.).2);
    }
    #[test]
    fn magnetic_candidate_is_flagged() {
        assert!(
            !Cap {
                mu_r: 2.,
                ..Cap::selected()
            }
            .validity(100.)
            .2
        );
    }
    #[test]
    fn nonfinite_is_rejected() {
        assert!(number("NaN").is_err());
    }
    #[test]
    fn negative_uncertainty_is_rejected() {
        assert!(nonnegative("-1").is_err());
    }
    #[test]
    fn empty_measurement_is_rejected() {
        assert!(fields("a,,c", 3).is_err());
    }
    fn sample(t: f64, error: f64) -> Sample {
        Sample {
            time: t,
            sensor: 100. + 2. * t + error,
            reference: 100. + 2. * t,
            ref2: 100. + 2. * t,
            current: 0.,
            hz: 0.,
        }
    }
    #[test]
    fn paired_linear_drift_cancels() {
        assert!(
            (pair_effect(sample(0., 1.), sample(1., 1.25), sample(2., 1.)).unwrap() - 0.25).abs()
                < 1e-12
        );
    }
    #[test]
    fn unbracketed_on_is_rejected() {
        assert!(pair_effect(sample(0., 1.), sample(3., 1.), sample(2., 1.)).is_err());
    }
    #[test]
    fn zero_field_has_zero_power() {
        assert_eq!(Cap::selected().powers(40000., 0.), (0., 0.));
    }
    fn mutation(kind: &str, name: &str, from: &str, to: &str) -> Result<String> {
        let source = fs::read_to_string(format!("fixtures/{kind}.csv"))?;
        let temp = env::temp_dir().join(format!("induction-{}-{name}.csv", std::process::id()));
        fs::write(&temp, source.replace(from, to))?;
        let m = metadata(Path::new(&format!("fixtures/{kind}.meta")))?;
        let result = if kind == "paired" {
            paired(&temp, &m)
        } else {
            endurance(&temp, &m)
        };
        fs::remove_file(temp)?;
        result
    }
    #[test]
    fn reference_interference_is_rejected() {
        assert!(mutation("paired", "bad-reference", "102.05", "112.05").is_err());
    }
    #[test]
    fn reversed_time_is_rejected() {
        assert!(mutation("paired", "bad-time", "p1,on,1,", "p1,on,0,").is_err());
    }
    #[test]
    fn invalid_acquisition_is_rejected() {
        assert!(mutation("paired", "bad-acq", "40000,1", "40000,0").is_err());
    }
    #[test]
    fn missing_phase_is_rejected() {
        assert!(mutation("paired", "bad-phase", "off_after", "off_before").is_err());
    }
    #[test]
    fn unperformed_endurance_is_rejected() {
        assert!(mutation("endurance", "unperformed", ",1,syn-04", ",0,syn-04").is_err());
    }
    #[test]
    fn wrong_units_are_rejected() {
        assert!(mutation(
            "endurance",
            "bad-units",
            "touch_current,mA",
            "touch_current,A"
        )
        .is_err());
    }
    #[test]
    fn missing_required_check_is_rejected() {
        assert!(mutation("endurance", "missing-check", "touch_current", "absent").is_err());
    }
    #[test]
    fn synthetic_results_never_claim_hardware_pass() {
        assert!(
            mutation("endurance", "synthetic", "nonexistent", "irrelevant")
                .unwrap()
                .contains("SYNTHETIC_ONLY_NO_HARDWARE_VERDICT")
        );
    }
    #[test]
    fn digest_mismatch_is_rejected() {
        let m = metadata(Path::new("fixtures/endurance.meta")).unwrap();
        assert!(verify_hash(Path::new("fixtures/paired.csv"), &m).is_err());
    }
    #[test]
    fn failing_limit_is_preserved_in_synthetic_screen() {
        assert!(mutation(
            "endurance",
            "limit-fail",
            "touch_current,mA,0.02",
            "touch_current,mA,0.2"
        )
        .unwrap()
        .contains("EXCEEDS_CONFIGURED_LIMIT"));
    }
}

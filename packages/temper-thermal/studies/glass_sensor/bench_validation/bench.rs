//! Offline measurement reduction; no hardware output or control path.
use std::{collections::BTreeMap, env, error::Error, fs, path::Path, process::Command};
type Result<T> = std::result::Result<T, Box<dyn Error>>;
const HEADER: &str = "time_s,pan_ref_c,sensor_c,body_c,force_n,stroke_mm,rock_a_mm,rock_b_mm,command,contact_reference";
#[derive(Clone, Debug)]
struct Row {
    t: f64,
    pan: f64,
    sensor: f64,
    body: f64,
    force: f64,
    stroke: f64,
    a: f64,
    b: f64,
    command: String,
    contact: bool,
}
#[derive(Clone, Debug)]
struct Fit {
    tau: f64,
    gain: f64,
    offset: f64,
    rmse: f64,
    edge: bool,
}
fn parse(text: &str) -> Result<Vec<Row>> {
    let mut lines = text.lines();
    if lines.next() != Some(HEADER) {
        return Err("CSV header mismatch".into());
    }
    let mut rows = Vec::new();
    for (line_no, line) in lines.enumerate() {
        let v: Vec<_> = line.split(',').collect();
        if v.len() != 10 {
            return Err(format!("line {}: expected 10 unquoted fields", line_no + 2).into());
        }
        let n: Vec<f64> = v[..8]
            .iter()
            .map(|s| s.parse::<f64>())
            .collect::<std::result::Result<_, _>>()?;
        if n.iter().any(|x| !x.is_finite()) {
            return Err("nonfinite sample".into());
        }
        if n[0] < 0. || rows.last().is_some_and(|r: &Row| n[0] <= r.t) {
            return Err("timestamps must strictly increase from nonnegative origin".into());
        }
        if !["preload", "load", "unload", "release", "thermal"].contains(&v[8])
            || !["0", "1"].contains(&v[9])
        {
            return Err("unknown command/contact".into());
        }
        rows.push(Row {
            t: n[0],
            pan: n[1],
            sensor: n[2],
            body: n[3],
            force: n[4],
            stroke: n[5],
            a: n[6],
            b: n[7],
            command: v[8].to_owned(),
            contact: v[9] == "1",
        });
    }
    if rows.len() < 5 {
        return Err("at least five acquired samples required; empty templates are NOT_RUN".into());
    }
    Ok(rows)
}
fn metadata(text: &str) -> Result<BTreeMap<String, String>> {
    let mut m = BTreeMap::new();
    for line in text
        .lines()
        .filter(|s| !s.starts_with('#') && !s.is_empty())
    {
        let (k, v) = line.split_once('=').ok_or("metadata requires key=value")?;
        if v.is_empty()
            || ["NOT_RUN", "UNKNOWN", "TODO", "NONE"].contains(&v)
            || m.insert(k.to_owned(), v.to_owned()).is_some()
        {
            return Err("empty, NOT_RUN, or duplicate metadata".into());
        }
    }
    for k in [
        "run_id",
        "evidence_kind",
        "role",
        "cartridge_id",
        "pan_id",
        "firmware_commit",
        "calibration_ids",
        "operator",
        "acquired_utc",
        "max_gap_s",
        "u_error_c",
        "u_time_s",
        "u_force_n",
        "u_stroke_mm",
        "plateau_start_s",
        "step_time_s",
        "reference_transition_s",
        "reference_lag_bound_s",
        "approved_temperature_max_c",
        "raw_origin",
        "schema",
        "reference_id",
        "reference_calibration_id",
        "clock_source",
        "contact_reference_method",
        "acquisition_valid",
    ] {
        if !m.contains_key(k) {
            return Err(format!("missing metadata {k}").into());
        }
    }
    if m["schema"] != "temper-bench-v1" || m["acquisition_valid"] != "true" {
        return Err("unknown schema or invalid acquisition".into());
    }
    if m["evidence_kind"] == "MEASURED"
        && m.values().any(|v| {
            let v = v.to_ascii_uppercase();
            ["SYNTHETIC", "PENDING", "UNKNOWN", "NOT_RUN", "TODO"]
                .iter()
                .any(|token| v.contains(token))
        })
    {
        return Err("measured provenance cannot contain unresolved or synthetic identity".into());
    }
    if !["MEASURED", "SYNTHETIC"].contains(&m["evidence_kind"].as_str())
        || !["fit", "holdout", "mechanical"].contains(&m["role"].as_str())
    {
        return Err("unknown evidence_kind/role".into());
    }
    for key in [
        "max_gap_s",
        "u_error_c",
        "u_time_s",
        "u_force_n",
        "u_stroke_mm",
        "reference_transition_s",
        "reference_lag_bound_s",
        "approved_temperature_max_c",
    ] {
        if number(&m, key)? <= 0. {
            return Err(format!("{key} must be positive; unknown uncertainty is not zero").into());
        }
    }
    Ok(m)
}
fn number(m: &BTreeMap<String, String>, key: &str) -> Result<f64> {
    let x = m
        .get(key)
        .ok_or("missing numeric metadata")?
        .parse::<f64>()?;
    if !x.is_finite() {
        return Err("nonfinite metadata".into());
    }
    Ok(x)
}
fn validate(rows: &[Row], m: &BTreeMap<String, String>) -> Result<()> {
    let max_gap = number(m, "max_gap_s")?;
    if rows
        .windows(2)
        .any(|w| w[1].t - w[0].t > max_gap * (1. + 1e-9))
    {
        return Err("acquisition gap exceeds declared budget".into());
    }
    let max_temp = number(m, "approved_temperature_max_c")?;
    if rows
        .iter()
        .any(|r| [r.pan, r.sensor, r.body].iter().any(|v| *v > max_temp))
    {
        return Err("sample exceeds reviewed assembly temperature".into());
    }
    if m["role"] != "mechanical" && rows.iter().any(|r| !r.contact || r.command != "thermal") {
        return Err(
            "thermal fit requires independent continuous contact; split interrupted runs".into(),
        );
    }
    Ok(())
}
// Exact ZOH integration uses left-end measured input, without future sample leakage.
fn prediction(rows: &[Row], tau: f64, gain: f64, offset: f64) -> Vec<f64> {
    let mut y = rows[0].sensor;
    let mut out = vec![y];
    for w in rows.windows(2) {
        let q = (-(w[1].t - w[0].t) / tau).exp();
        let target = w[0].body + gain * (w[0].pan - w[0].body) + offset;
        y = q * y + (1. - q) * target;
        out.push(y);
    }
    out
}
fn rmse(rows: &[Row], p: &[f64]) -> f64 {
    (rows
        .iter()
        .zip(p)
        .skip(1)
        .map(|(r, y)| (r.sensor - y).powi(2))
        .sum::<f64>()
        / (rows.len() - 1) as f64)
        .sqrt()
}
fn fit(rows: &[Row]) -> Result<Fit> {
    let excitation = rows
        .iter()
        .map(|r| r.pan - r.body)
        .fold(f64::NEG_INFINITY, f64::max)
        - rows
            .iter()
            .map(|r| r.pan - r.body)
            .fold(f64::INFINITY, f64::min);
    if excitation < 20. {
        return Err("unidentifiable fit: require >=20 C pan-minus-body excitation".into());
    }
    let mut best = Fit {
        tau: 0.,
        gain: 0.,
        offset: 0.,
        rmse: f64::INFINITY,
        edge: false,
    };
    for i in 0..401 {
        let tau = 0.05_f64 * (1200_f64.ln() * i as f64 / 400.).exp();
        let base = prediction(rows, tau, 0., 0.);
        let g = prediction(rows, tau, 1., 0.);
        let o = prediction(rows, tau, 0., 1.);
        let (mut xx, mut zz, mut xz, mut xy, mut zy) = (0., 0., 0., 0., 0.);
        for j in 1..rows.len() {
            let x = g[j] - base[j];
            let z = o[j] - base[j];
            let y = rows[j].sensor - base[j];
            xx += x * x;
            zz += z * z;
            xz += x * z;
            xy += x * y;
            zy += z * y;
        }
        let det = xx * zz - xz * xz;
        if det <= 1e-10 * xx * zz {
            continue;
        }
        let gain = (xy * zz - zy * xz) / det;
        let offset = (zy * xx - xy * xz) / det;
        if !(0.0..=1.1).contains(&gain) || offset.abs() > 20. {
            continue;
        }
        let score = rmse(rows, &prediction(rows, tau, gain, offset));
        if score < best.rmse {
            best = Fit {
                tau,
                gain,
                offset,
                rmse: score,
                edge: i == 0 || i == 400,
            };
        }
    }
    if !best.rmse.is_finite() {
        return Err("no identifiable physical surrogate fit".into());
    }
    Ok(best)
}
fn mean(v: impl Iterator<Item = f64>) -> f64 {
    let (s, n) = v.fold((0., 0), |(s, n), x| (s + x, n + 1));
    s / n as f64
}
fn crossing(rows: &[Row], start: f64, initial: f64, final_value: f64) -> Option<f64> {
    let direction = (final_value - initial).signum();
    if (final_value - initial).abs() < 1e-9 {
        return None;
    }
    let threshold = initial + 0.9 * (final_value - initial);
    for w in rows.windows(2).filter(|w| w[0].t >= start) {
        let (a, b) = (
            direction * (w[0].sensor - threshold),
            direction * (w[1].sensor - threshold),
        );
        if a < 0. && b >= 0. {
            return Some(w[0].t + (w[1].t - w[0].t) * (-a) / (b - a) - start);
        }
    }
    None
}
fn thermal_metrics(rows: &[Row], m: &BTreeMap<String, String>) -> Result<String> {
    let plateau = number(m, "plateau_start_s")?;
    let step = number(m, "step_time_s")?;
    if step <= rows[0].t || plateau <= step || plateau >= rows[rows.len() - 1].t {
        return Err("baseline/step/plateau chronology invalid".into());
    }
    let final_rows: Vec<_> = rows.iter().filter(|r| r.t >= plateau).collect();
    let initial_rows: Vec<_> = rows.iter().filter(|r| r.t < step).collect();
    if initial_rows.len() < 5
        || final_rows.len() < 5
        || final_rows.last().ok_or("missing plateau")?.t - final_rows[0].t < 60.
    {
        return Err("need >=5 baseline samples and measured plateau >=60 s".into());
    }
    let spread = |f: fn(&Row) -> f64| {
        final_rows
            .iter()
            .map(|r| f(r))
            .fold(f64::NEG_INFINITY, f64::max)
            - final_rows
                .iter()
                .map(|r| f(r))
                .fold(f64::INFINITY, f64::min)
    };
    let stable = spread(|r| r.pan) <= 0.5 && spread(|r| r.sensor) <= 0.5;
    let initial = mean(initial_rows.iter().map(|r| r.sensor));
    let initial_pan = mean(initial_rows.iter().map(|r| r.pan));
    let final_sensor = mean(final_rows.iter().map(|r| r.sensor));
    let final_pan = mean(final_rows.iter().map(|r| r.pan));
    let error = mean(final_rows.iter().map(|r| r.sensor - r.pan));
    let expanded = 2. * number(m, "u_error_c")?;
    let limit = if (40.0..=100.).contains(&final_pan) {
        Some(2.)
    } else if final_pan > 100. && final_pan <= 250. {
        Some(5.)
    } else {
        None
    };
    let error_status = match limit {
        Some(l) if stable && error.abs() + expanded <= l => "PROPOSED_SCREEN_PASS",
        Some(l) if stable && error.abs() - expanded > l => "PROPOSED_SCREEN_FAIL",
        _ => "INDETERMINATE",
    };
    let format_t =
        |x: Option<f64>| x.map_or_else(|| "NOT_REACHED".to_owned(), |v| format!("{v:.6}"));
    let final_t = if stable {
        crossing(rows, step, initial, final_sensor)
    } else {
        None
    };
    let imposed_t = if stable && (final_pan - initial_pan).abs() >= 20. {
        crossing(rows, step, initial, initial + final_pan - initial_pan)
    } else {
        None
    };
    let ideal_step =
        number(m, "reference_transition_s")? + number(m, "reference_lag_bound_s")? <= 0.3;
    let response_status = match imposed_t {
        Some(t) if ideal_step && t + 2. * number(m, "u_time_s")? <= 3. => "PROPOSED_SCREEN_PASS",
        Some(t) if ideal_step && t - 2. * number(m, "u_time_s")? > 3. => "PROPOSED_SCREEN_FAIL",
        _ => "INDETERMINATE",
    };
    Ok(format!("plateau_stable={stable}\nlocal_error_c={error:.6}\nexpanded_error_c={expanded:.6}\nerror_screen={error_status}\nt90_relative_final_s={}\nt90_imposed_pan_step_s={}\nfast_reference_step={ideal_step}\nresponse_screen={response_status}\n",format_t(final_t),format_t(imposed_t)))
}
fn mechanics(rows: &[Row]) -> Result<String> {
    let order = |r: &Row| match r.command.as_str() {
        "preload" => 0,
        "load" => 1,
        "unload" => 2,
        "release" => 3,
        _ => 4,
    };
    if rows.iter().any(|r| order(r) == 4) || rows.windows(2).any(|w| order(&w[1]) < order(&w[0])) {
        return Err("mechanical phases must be preload/load/unload/release in order".into());
    }
    let pre: Vec<_> = rows.iter().filter(|r| r.command == "preload").collect();
    let release: Vec<_> = rows.iter().filter(|r| r.command == "release").collect();
    let load: Vec<_> = rows.iter().filter(|r| r.command == "load").collect();
    let unload: Vec<_> = rows.iter().filter(|r| r.command == "unload").collect();
    if [pre.len(), release.len(), load.len(), unload.len()]
        .iter()
        .any(|n| *n < 2)
    {
        return Err(
            "mechanics requires >=2 samples in each preload/load/unload/release phase".into(),
        );
    }
    if load.windows(2).any(|w| w[1].stroke <= w[0].stroke)
        || unload.windows(2).any(|w| w[1].stroke >= w[0].stroke)
    {
        return Err("split cycles: load stroke increasing and unload decreasing required".into());
    }
    let mut hysteresis: f64 = 0.;
    let mut pairs = 0;
    for r in &load {
        for w in unload.windows(2) {
            if r.stroke >= w[1].stroke && r.stroke <= w[0].stroke {
                let f = w[1].force
                    + (w[0].force - w[1].force) * (r.stroke - w[1].stroke)
                        / (w[0].stroke - w[1].stroke);
                hysteresis = hysteresis.max((r.force - f).abs());
                pairs += 1;
                break;
            }
        }
    }
    if pairs < 2 {
        return Err("insufficient common stroke for hysteresis".into());
    }
    let zero = mean(pre.iter().map(|r| r.stroke));
    let rocking_zero = mean(pre.iter().map(|r| r.a - r.b));
    let max_force = rows
        .iter()
        .map(|r| r.force)
        .fold(f64::NEG_INFINITY, f64::max);
    let stroke = rows
        .iter()
        .map(|r| r.stroke - zero)
        .fold(f64::NEG_INFINITY, f64::max);
    let residual = release.last().ok_or("missing release")?.stroke - zero;
    let rocking = rows
        .iter()
        .map(|r| (r.a - r.b - rocking_zero).abs())
        .fold(0., f64::max);
    let start = release[0].t;
    let returned = settled_return(&release, zero).map(|t| t - start);
    Ok(format!("max_total_tip_force_n={max_force:.6}\nmax_stroke_mm={stroke:.6}\nmax_hysteresis_n={hysteresis:.6}\nresidual_stroke_mm={residual:.6}\nrocking_differential_peak_mm={rocking:.6}\nreturn_to_0p02mm_s={}\nmechanical_acceptance=CHARACTERIZATION_ONLY\n",returned.map_or_else(||"NOT_RETURNED".into(),|t|format!("{t:.6}"))))
}
fn settled_return(release: &[&Row], zero: f64) -> Option<f64> {
    let first = release
        .iter()
        .rposition(|r| (r.stroke - zero).abs() > 0.02)
        .map_or(0, |i| i + 1);
    let start = release.get(first)?;
    if release.last()?.t - start.t < 1. {
        return None;
    }
    Some(start.t)
}
fn holdout_residual(rows: &[Row], p: &[f64], step: f64, tau: f64) -> Result<(f64, f64)> {
    let pan_range = rows
        .iter()
        .map(|r| r.pan - r.body)
        .fold(f64::NEG_INFINITY, f64::max)
        - rows
            .iter()
            .map(|r| r.pan - r.body)
            .fold(f64::INFINITY, f64::min);
    if pan_range < 20. || step <= rows[0].t || rows[rows.len() - 1].t < step + 5. * tau {
        return Err(
            "holdout INDETERMINATE: require excitation, baseline, and >=5 tau duration".into(),
        );
    }
    let dynamic: Vec<_> = rows
        .iter()
        .zip(p)
        .filter(|(r, _)| r.t >= step && r.t <= step + (5. * tau).max(3.))
        .map(|(r, y)| (r.sensor - y).abs())
        .collect();
    if dynamic.len() < 10 {
        return Err("holdout INDETERMINATE: insufficient dynamic samples".into());
    }
    Ok((
        (dynamic.iter().map(|e| e * e).sum::<f64>() / dynamic.len() as f64).sqrt(),
        dynamic.into_iter().fold(0., f64::max),
    ))
}
fn hash(path: &Path) -> Result<String> {
    let out = Command::new("shasum")
        .args(["-a", "256"])
        .arg(path)
        .output()?;
    if !out.status.success() {
        return Err("shasum failed".into());
    }
    Ok(String::from_utf8(out.stdout)?
        .split_whitespace()
        .next()
        .ok_or("empty hash")?
        .to_owned())
}
fn load(path: &str, meta: &str) -> Result<(Vec<Row>, BTreeMap<String, String>)> {
    let r = parse(&fs::read_to_string(path)?)?;
    let m = metadata(&fs::read_to_string(meta)?)?;
    validate(&r, &m)?;
    Ok((r, m))
}
fn main() -> Result<()> {
    let args: Vec<_> = env::args().collect();
    if args.len() == 3 && args[1] == "budget" {
        let text = fs::read_to_string(&args[2])?;
        let (kind, u) = uncertainty(&text)?;
        println!("schema=temper-bench-uncertainty-v1\nevidence_kind={kind}\nraw_sha256={}\nstandard_uncertainty={u:.8}\nexpanded_uncertainty_k2={:.8}\nphysical_validation=NOT_ESTABLISHED", hash(Path::new(&args[2]))?, 2. * u);
        return Ok(());
    }
    if args.len() != 4 && args.len() != 6 {
        return Err("usage: bench mechanical|thermal|calibrate data.csv metadata.txt [holdout.csv holdout.txt]".into());
    }
    let (rows, m) = load(&args[2], &args[3])?;
    let mut output=format!("schema=temper-bench-v1\nevidence_kind={}\nrun_id={}\nraw_sha256={}\nmetadata_sha256={}\nphysical_validation={}\n",m["evidence_kind"],m["run_id"],hash(Path::new(&args[2]))?,hash(Path::new(&args[3]))?,if m["evidence_kind"]=="SYNTHETIC"{"NOT_RUN"}else{"ACQUIRED_REQUIRES_REVIEW"});
    match args[1].as_str() {
        "mechanical" if args.len() == 4 && m["role"] == "mechanical" => {
            output.push_str(&mechanics(&rows)?)
        }
        "thermal" if args.len() == 4 && m["role"] != "mechanical" => {
            output.push_str(&thermal_metrics(&rows, &m)?)
        }
        "calibrate" if args.len() == 6 && m["role"] == "fit" => {
            let (hold, hm) = load(&args[4], &args[5])?;
            if hm["role"] != "holdout"
                || m["run_id"] == hm["run_id"]
                || m["raw_origin"] == hm["raw_origin"]
                || hash(Path::new(&args[2]))? == hash(Path::new(&args[4]))?
            {
                return Err("holdout must be separately acquired, declared holdout, and have distinct raw data".into());
            }
            if m["evidence_kind"] != hm["evidence_kind"] || m["cartridge_id"] != hm["cartridge_id"]
            {
                return Err("cannot mix provenance or cartridge identity".into());
            }
            let f = fit(&rows)?;
            let predictions = prediction(&hold, f.tau, f.gain, f.offset);
            let residual = rmse(&hold, &predictions);
            let (dynamic_rmse, dynamic_max) =
                holdout_residual(&hold, &predictions, number(&hm, "step_time_s")?, f.tau)?;
            let threshold = 2. * number(&hm, "u_error_c")?;
            output.push_str(&format!("model=effective_first_order_not_physical_component_identification\ntau_s={:.6}\npan_gain={:.6}\noffset_c={:.6}\nfit_rmse_c={:.6}\nfit_at_search_boundary={}\nholdout_rmse_c={residual:.6}\nholdout_dynamic_rmse_c={dynamic_rmse:.6}\nholdout_dynamic_max_c={dynamic_max:.6}\nholdout_screen={}\nholdout_raw_sha256={}\nholdout_metadata_sha256={}\n",f.tau,f.gain,f.offset,f.rmse,f.edge,if !f.edge&&residual<=threshold&&dynamic_max<=threshold{"SURROGATE_WITHIN_DECLARED_UNCERTAINTY"}else{"REJECT_TRANSFER"},hash(Path::new(&args[4]))?,hash(Path::new(&args[5]))?));
        }
        _ => return Err("command/role/argument mismatch".into()),
    }
    print!("{output}");
    Ok(())
}
// Fully correlated terms add within each group; independent groups combine in quadrature.
// Absolute contributions deliberately avoid assuming beneficial cancellation.
fn uncertainty(text: &str) -> Result<(String, f64)> {
    let mut lines = text.lines();
    if lines.next() != Some("evidence_kind,component,standard_uncertainty,sensitivity,correlation_group,unit,evidence_id") {
        return Err("uncertainty header mismatch".into());
    }
    let mut groups = BTreeMap::<String, f64>::new();
    let mut units = String::new();
    let mut kind = String::new();
    let mut components = std::collections::BTreeSet::new();
    for line in lines {
        let v: Vec<_> = line.split(',').collect();
        if v.len() != 7
            || v.iter()
                .any(|s| s.is_empty() || ["NOT_RUN", "UNKNOWN", "TODO"].contains(s))
        {
            return Err("incomplete uncertainty component".into());
        }
        if !["MEASURED", "SYNTHETIC"].contains(&v[0])
            || (!kind.is_empty() && kind != v[0])
            || (!units.is_empty() && units != v[5])
            || !components.insert(v[1].to_owned())
        {
            return Err("mixed provenance/units or duplicate component".into());
        }
        kind = v[0].to_owned();
        units = v[5].to_owned();
        let u = v[2].parse::<f64>()?;
        let sensitivity = v[3].parse::<f64>()?;
        if !u.is_finite() || !sensitivity.is_finite() || u < 0. {
            return Err("invalid uncertainty value".into());
        }
        *groups.entry(v[4].to_owned()).or_default() += (u * sensitivity).abs();
    }
    let u = groups.values().map(|v| v * v).sum::<f64>().sqrt();
    if !u.is_finite() || u <= 0. || groups.is_empty() {
        return Err("missing uncertainty budget".into());
    }
    Ok((kind, u))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn settled_return_survives_bounce_before_final_settle() {
        let mut r = fixture(1., 1.);
        r.truncate(50);
        for x in &mut r {
            x.stroke = 0.;
        }
        r[3].stroke = 0.1;
        let refs: Vec<_> = r.iter().collect();
        assert_eq!(settled_return(&refs, 0.), Some(0.2));
    }
    #[test]
    fn holdout_constant_temperature_is_not_dynamic_evidence() {
        let mut r = fixture(1., 1.);
        for x in &mut r {
            x.pan = 100.;
        }
        assert!(holdout_residual(&r, &prediction(&r, 1., 1., 0.), 5., 1.).is_err());
    }
    #[test]
    fn small_overall_rmse_does_not_hide_bad_transient() {
        let r = fixture(1., 1.);
        let mut p: Vec<_> = r.iter().map(|x| x.sensor).collect();
        p[110] += 3.;
        let (_, peak) = holdout_residual(&r, &p, 5., 1.).unwrap();
        assert!(rmse(&r, &p) < 0.1 && peak == 3.);
    }
    #[test]
    fn correlated_budget_does_not_get_false_sqrt_reduction() {
        let csv="evidence_kind,component,standard_uncertainty,sensitivity,correlation_group,unit,evidence_id\nSYNTHETIC,a,0.3,1,common,C,SYNTHETIC\nSYNTHETIC,b,0.4,1,common,C,SYNTHETIC\n";
        assert!((uncertainty(csv).unwrap().1 - 0.7).abs() < 1e-12);
    }
    #[test]
    fn missing_budget_is_not_zero_uncertainty() {
        assert!(uncertainty("evidence_kind,component,standard_uncertainty,sensitivity,correlation_group,unit,evidence_id\n").is_err());
    }
    fn fixture(tau: f64, gain: f64) -> Vec<Row> {
        let mut r: Vec<_> = (0..2401)
            .map(|i| {
                let t = i as f64 * 0.05;
                Row {
                    t,
                    pan: if t < 5. { 25. } else { 100. },
                    sensor: 25.,
                    body: 25.,
                    force: 0.4,
                    stroke: 0.6,
                    a: 0.,
                    b: 0.,
                    command: "thermal".into(),
                    contact: true,
                }
            })
            .collect();
        let p = prediction(&r, tau, gain, 0.);
        for (r, v) in r.iter_mut().zip(p) {
            r.sensor = v;
        }
        r
    }
    #[test]
    fn rejects_header_only() {
        assert!(parse(HEADER).is_err());
    }
    #[test]
    fn rejects_nan() {
        assert!(parse(&format!("{HEADER}\n0,NaN,25,25,0,0,0,0,thermal,1")).is_err());
    }
    #[test]
    fn recovers_known_effective_parameters() {
        let f = fit(&fixture(1.5, 0.94)).unwrap();
        assert!((f.tau - 1.5).abs() < 0.02 && (f.gain - 0.94).abs() < 0.001);
    }
    #[test]
    fn rejects_no_excitation() {
        let mut r = fixture(1.5, 1.);
        for x in &mut r {
            x.pan = 25.;
        }
        assert!(fit(&r).is_err());
    }
    #[test]
    fn distinguishes_biased_fast_final_from_unreachable_pan_step() {
        let r = fixture(1., 0.8);
        assert!(crossing(&r, 5., 25., 85.).is_some() && crossing(&r, 5., 25., 100.).is_none());
    }
    #[test]
    fn t90_matches_external_analytic_first_order() {
        let r = fixture(1.5, 1.);
        let t = crossing(&r, 5., 25., 100.).unwrap();
        assert!((t - 1.5 * 10_f64.ln()).abs() < 0.002);
    }
    #[test]
    fn transfer_detects_weaker_contact() {
        let r = fixture(1.5, 1.);
        let f = fit(&r).unwrap();
        let hold = fixture(5., 0.8);
        assert!(rmse(&hold, &prediction(&hold, f.tau, f.gain, f.offset)) > 10.);
    }
    #[test]
    fn thermal_continuity_rejects_loss() {
        let mut r = fixture(1.5, 1.);
        r[20].contact = false;
        let m = BTreeMap::from([
            ("role".into(), "fit".into()),
            ("max_gap_s".into(), "0.1".into()),
            ("approved_temperature_max_c".into(), "250".into()),
        ]);
        assert!(validate(&r, &m).is_err());
    }
    #[test]
    fn gap_is_rejected() {
        let r = fixture(1.5, 1.);
        let m = BTreeMap::from([
            ("role".into(), "fit".into()),
            ("max_gap_s".into(), "0.01".into()),
            ("approved_temperature_max_c".into(), "250".into()),
        ]);
        assert!(validate(&r, &m).is_err());
    }
    #[test]
    fn incomplete_metadata_rejected() {
        assert!(metadata("u_error_c=0").is_err());
    }
    #[test]
    fn mechanics_finds_hysteresis_and_sticking() {
        let mut r = fixture(1., 1.);
        r.truncate(12);
        for (i, x) in r.iter_mut().enumerate() {
            x.command = if i < 2 {
                "preload"
            } else if i < 6 {
                "load"
            } else if i < 10 {
                "unload"
            } else {
                "release"
            }
            .into();
            x.stroke = match i {
                0 | 1 => 0.,
                2..=5 => (i - 2) as f64 * 0.2,
                6..=9 => (9 - i) as f64 * 0.2,
                _ => 0.08,
            };
            x.force = 0.2 + x.stroke + if i < 6 { 0.05 } else { -0.05 };
        }
        let s = mechanics(&r).unwrap();
        assert!(s.contains("max_hysteresis_n=0.100000") && s.contains("NOT_RETURNED"));
    }
    #[test]
    fn cooling_t90_supported() {
        let mut r = fixture(1.5, 1.);
        for x in &mut r {
            x.pan = 125. - x.pan;
            x.sensor = 125. - x.sensor;
        }
        let t = crossing(&r, 5., 100., 25.).unwrap();
        assert!((t - 1.5 * 10_f64.ln()).abs() < 0.002);
    }
}

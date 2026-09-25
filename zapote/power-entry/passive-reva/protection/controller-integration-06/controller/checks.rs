const INTEGRATED_HEADER: &str = "time v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(isense) v(vsense) v(vcomp) v(icomp) v(pwm) v(q) v(en) v(fault) v(f2ctl) v(xu.pcl_hold) v(xu.m1) v(xu.m2) v(xu.ov) v(arm) v(standby_req)";
const SOFT_START_HEADER: &str = "time v(vcc) v(vsense) v(vcomp) v(cs) v(gate)";
const CURRENT_LOOP_HEADER: &str = "time v(icomp) v(xu.m1) v(xu.m2) v(gate) v(isense)";
const FUNCTIONAL_HEADER: &str = "time v(vcc) v(vsense) v(isense) v(gate) v(xu.uv) v(xu.ov) v(xu.pcl_hold) v(xu.raw) v(xu.blank) i(Vvc)";
use std::{env, fs};
fn trace(path: &str, header: &str, stop: f64, maxgap: f64) -> Result<Vec<Vec<f64>>, String> {
    let input = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let expected: Vec<_> = header.split_whitespace().collect();
    if input
        .lines()
        .next()
        .map(|line| line.split_whitespace().collect::<Vec<_>>())
        != Some(expected.clone())
    {
        return Err("wrong trace header/order".into());
    }
    let cols = expected.len();
    let mut out: Vec<Vec<f64>> = Vec::new();
    for (n, line) in input.lines().enumerate() {
        if n == 0 {
            continue;
        }
        let row = line
            .split_whitespace()
            .map(|s| {
                s.parse::<f64>()
                    .map_err(|_| format!("invalid number at row{n}"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        if row.len() != cols || row.iter().any(|x| !x.is_finite()) {
            return Err(format!("bad width/nonfinite row{n}"));
        }
        if let Some(prev) = out.last() {
            if row[0] <= prev[0] || row[0] - prev[0] > maxgap {
                return Err(format!("time gap/order row{n}"));
            }
        }
        out.push(row);
    }
    if out.len() < 100
        || (out[0][0] < 0. || out[0][0] > 1e-8)
        || (out.last().unwrap()[0] - stop).abs() > 1e-9
    {
        return Err("incomplete trace".into());
    }
    Ok(out)
}
fn window(data: &[Vec<f64>], a: f64, b: f64) -> Vec<&[f64]> {
    data.iter()
        .filter(|r| r[0] >= a * 1e-6 && r[0] <= b * 1e-6)
        .map(Vec::as_slice)
        .collect()
}
fn functional(d: &[Vec<f64>]) -> Result<Vec<String>, String> {
    let mut results = Vec::new();
    for (name, a, b, on) in [
        ("UVLO rising hysteresis", 12., 29., false),
        ("UVLO enabled", 35., 59., true),
        ("UVLO retained at10V", 65., 89., true),
        ("UVLO disabled at9V", 95., 119., false),
        ("UVLO recovery", 130., 190., true),
        ("OVP set", 205., 219., false),
        ("OVP retained at5.2V", 225., 249., false),
        ("OVP reset below5.1V", 260., 295., true),
        ("VSENSE standby", 305., 319., false),
        ("standby recovery", 330., 345., true),
        ("ISENSE openpin", 405., 419., false),
        ("ICOMP short", 481., 489., false),
    ] {
        let w = window(d, a, b);
        if w.len() < 10 {
            return Err(format!("{name}:missing window"));
        }
        let peak = w.iter().map(|r| r[4]).fold(0., f64::max);
        if (on && peak < 8.) || (!on && peak > 0.01) {
            return Err(format!("{name}:gate peak{peak}"));
        }
        results.push(format!("PASS {name}"));
    }
    let pcl = window(d, 351., 367.);
    if !pcl.iter().any(|r| r[7] > 2.5) {
        return Err("PCL never latched".into());
    }
    if pcl.iter().any(|r| r[7] > 2.5 && r[4] > 0.01) {
        return Err("PCL did not inhibit gate".into());
    }
    if !pcl.iter().any(|r| r[3] > -0.2 && r[7] > 2.5 && r[8] > 2.5) {
        return Err("missing retained PCL after comparator released".into());
    }
    if !pcl.iter().any(|r| r[3] < -0.4 && r[4] > 8. && r[9] < 0.31) {
        return Err("no leading-edge blanking witness".into());
    }
    results.push("PASS cycle-latched PCL with blanking and hold after comparator release".into());
    let edr = window(d, 432., 444.);
    if edr.is_empty() || edr.iter().any(|r| (r[10] - 275e-6).abs() > 1e-6) {
        return Err("EDR source did not reach275uA".into());
    }
    results.push("PASS low-voltage EDR sources275uA".into());
    let soc = window(d, 455., 468.);
    if soc.iter().any(|r| (r[10] + 0.00075).abs() > 1e-6) {
        return Err("SOC did not discharge through4k".into());
    }
    results.push("PASS SOC 4k VCOMP discharge".into());
    Ok(results)
}
fn integrated(d: &[Vec<f64>]) -> Result<Vec<String>, String> {
    let pre = window(d, 300., 590.);
    let peak = |col: usize| d.iter().map(|r| r[col]).fold(f64::NEG_INFINITY, f64::max);
    if !pre.iter().any(|r| r[4] > 10.0 && r[6] > 1.0 && r[14] > 2.5) {
        return Err("no armed channel conduction before F2".into());
    }
    if !pre.iter().any(|r| r[8].abs() > 1.0 && r[9] < -0.01) {
        return Err("missing causal mains/shunt current".into());
    }
    let opened = d.iter().find(|r| r[17] < 2.5).ok_or("F2 did not open")?[0];
    let fault = d
        .iter()
        .find(|r| r[0] >= opened && r[16] > 2.5)
        .ok_or("no external detector fault")?[0];
    let cleared = d
        .iter()
        .find(|r| r[0] >= fault && r[14] < 2.5)
        .ok_or("latch did not clear")?[0];
    if d.iter()
        .any(|r| r[0] > cleared + 2e-6 && (r[14] > 0.1 || r[4] > 1.0 || r[6] > 0.01))
    {
        return Err("not retained off after fault".into());
    }
    if peak(1) > 500. || peak(2) > 450. || peak(3) > 650. || peak(4) > 25. {
        return Err("node screen exceeded".into());
    }
    if d.iter().any(|r| r[4] < -25.0 || r[9] < -1.1) {
        return Err("negative gate/sense pin screen exceeded".into());
    }
    let last = d.last().unwrap();
    if last[23] < 2.5 || last[10] > 0.82 || last[13] > 0.1 {
        return Err("PFC standby coupling did not stop PWM".into());
    }
    Ok(vec![
        format!(
            "PASS integrated witness: F2={:.6}us detector={:.6}us latch={:.6}us",
            opened * 1e6,
            fault * 1e6,
            cleared * 1e6
        ),
        format!(
            "VD_peak={:.6}V VB_peak={:.6}V VDS_peak={:.6}V VGS_peak={:.6}V IL_peak={:.6}A",
            peak(1),
            peak(2),
            peak(3),
            peak(4),
            peak(5)
        ),
        format!(
            "final_VCOMP={:.9}V final_VSENSE={:.9}V final_PWM={:.9}V",
            last[11], last[10], last[13]
        ),
    ])
}
fn current_loop(d: &[Vec<f64>]) -> Result<Vec<String>, String> {
    let at = |t: f64| {
        d.iter()
            .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
            .unwrap()
    };
    let initial = at(90e-6)[1];
    let final_v = at(490e-6)[1];
    let ti_tau = 7.0 * 2.7e-9 / (0.95e-3 * 0.538);
    let response = (at(100.001e-6 + ti_tau)[1] - initial) / (final_v - initial);
    if (response - (1.0 - (-1.0_f64).exp())).abs() > 0.003 {
        return Err(format!("current pole mismatch: fraction{response}"));
    }
    if (final_v - (3.0 + 0.001 * 2.5 * 7.0 / 0.538)).abs() > 0.0001 {
        return Err("current-loop DC gain mismatch".into());
    }
    let last = d.last().unwrap();
    if (last[2] - 0.538).abs() > 1e-8
        || (last[3] - 118.0 / 65.0 * 0.1223 * 2.5_f64.powi(2)).abs() > 1e-6
    {
        return Err("TI M1/M2 worked example mismatch".into());
    }
    let edges: Vec<_> = d
        .windows(2)
        .filter(|w| w[0][4] < 7.0 && w[1][4] > 7.0 && w[1][0] > 300e-6)
        .map(|w| w[1][0])
        .collect();
    if edges.len() < 15 {
        return Err("too few PWM cycles".into());
    }
    let mean_period = (edges.last().unwrap() - edges[0]) / (edges.len() - 1) as f64;
    if (mean_period - 1.0 / 118e3).abs() > 20e-9 {
        return Err("oscillator frequency wrong".into());
    }
    Ok(vec![format!(
        "PASS TIeq81-88 M1=.538 M2={:.9}V/us; eq100 tau={:.6}us response={:.9}; oscillator={:.3}Hz",
        last[3],
        ti_tau * 1e6,
        response,
        1.0 / mean_period
    )])
}
fn soft_start(d: &[Vec<f64>]) -> Result<Vec<String>, String> {
    let at = |t: f64| {
        d.iter()
            .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
            .unwrap()
    };
    if at(0.5e-3)[3] > 0.01 {
        return Err("VCOMP started before UVLO release".into());
    }
    if at(5e-3)[3] < 1.5 || at(19e-3)[3] <= at(5e-3)[3] {
        return Err("soft-start capacitor not charging".into());
    }
    if at(24e-3)[3] >= at(19e-3)[3] * 0.5 {
        return Err("SOC did not discharge actual compensation network".into());
    }
    if at(29e-3)[3] < 1.5 {
        return Err("no recovery after SOC".into());
    }
    if at(31e-3)[3] > 0.1 {
        return Err("standby did not discharge VCOMP".into());
    }
    if at(49e-3)[3] < 1.5 {
        return Err("soft-start did not retry after standby".into());
    }
    Ok(vec![format!("PASS capacitor-backed soft-start, SOC discharge/recovery and standby/retry: VCOMP5ms={:.6}V,29ms={:.6}V,31ms={:.6}V,49ms={:.6}V",at(5e-3)[3],at(29e-3)[3],at(31e-3)[3],at(49e-3)[3])])
}
fn refinement(a: &[Vec<f64>], b: &[Vec<f64>]) -> Result<Vec<String>, String> {
    let max = |d: &[Vec<f64>], c: usize| d.iter().map(|r| r[c]).fold(f64::NEG_INFINITY, f64::max);
    let mut diffs = Vec::new();
    for c in 1..=5 {
        let delta = (max(a, c) - max(b, c)).abs();
        if delta > 0.05 {
            return Err(format!("peak refinement failure col{c} delta{delta}"));
        }
        diffs.push(delta);
    }
    let event = |d: &[Vec<f64>]| {
        d.iter()
            .find(|r| r[0] > 600e-6 && r[14] < 2.5)
            .map(|r| r[0])
            .ok_or_else(|| "missing latch event in refinement".to_string())
    };
    let dt = (event(a)? - event(b)?).abs();
    if dt > 50e-9 {
        return Err("latch event changes>50ns on refinement".into());
    }
    Ok(vec![format!(
        "PASS10ns→5ns: VD/VB/VDS/VGS/IL peak deltas={diffs:?}; latch difference={:.6}ns",
        dt * 1e9
    )])
}
fn main() {
    let args: Vec<_> = env::args().collect();
    let r = (|| {
        if args.len() < 3 || args.len() > 4 {
            return Err("usage: checks functional|integrated TRACE.tsv".into());
        }
        let results = match args[1].as_str() {
            "refinement" if args.len() == 4 => refinement(
                &trace(&args[2], INTEGRATED_HEADER, 900e-6, 25e-9)?,
                &trace(&args[3], INTEGRATED_HEADER, 900e-6, 25e-9)?,
            )?,
            "soft-start" if args.len() == 3 => {
                soft_start(&trace(&args[2], SOFT_START_HEADER, 50e-3, 110e-9)?)?
            }
            "current-loop" if args.len() == 3 => {
                current_loop(&trace(&args[2], CURRENT_LOOP_HEADER, 500e-6, 25e-9)?)?
            }
            "functional" if args.len() == 3 => {
                functional(&trace(&args[2], FUNCTIONAL_HEADER, 500e-6, 25e-9)?)?
            }
            "integrated" if args.len() == 3 => {
                integrated(&trace(&args[2], INTEGRATED_HEADER, 900e-6, 25e-9)?)?
            }
            _ => return Err("unknown check mode".into()),
        };
        for line in results {
            println!("{line}");
        }
        Ok::<_, String>(())
    })();
    if let Err(e) = r {
        eprintln!("FAIL {e}");
        std::process::exit(1);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_model_cannot_pass() {
        assert!(functional(&[]).is_err());
    }

    #[test]
    fn malformed_trace_cannot_reach_behavior_checks() {
        let path = env::temp_dir().join(format!("ucc06-parser-test-{}.tsv", std::process::id()));
        let rows = (0..100)
            .map(|i| format!("{} 1\n", i as f64 * 1e-9))
            .collect::<String>();
        fs::write(&path, format!("time v(a)\n{rows}")).unwrap();
        assert!(trace(path.to_str().unwrap(), "time v(a)", 99e-9, 2e-9).is_ok());
        assert!(trace(path.to_str().unwrap(), "time v(b)", 99e-9, 2e-9)
            .unwrap_err()
            .contains("header"));
        fs::write(&path, format!("time v(a)\n{}", rows.replace(" 1", " NaN"))).unwrap();
        assert!(trace(path.to_str().unwrap(), "time v(a)", 99e-9, 2e-9)
            .unwrap_err()
            .contains("nonfinite"));
        fs::write(&path, "time v(a)\n0 1\n0.00000005 1\n").unwrap();
        assert!(trace(path.to_str().unwrap(), "time v(a)", 99e-9, 2e-9)
            .unwrap_err()
            .contains("gap"));
        fs::remove_file(path).unwrap();
    }
    #[test]
    fn absent_refinement_event_is_an_error() {
        let row = vec![1.0; 24];
        assert!(refinement(&[row.clone()], &[row]).is_ok());
        let row = vec![5.0; 24];
        assert!(refinement(&[row.clone()], &[row])
            .unwrap_err()
            .contains("missing latch"));
    }
}

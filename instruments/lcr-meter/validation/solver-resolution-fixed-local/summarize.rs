#[path = "strict_order.rs"]
mod strict_order;
use std::fs;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn data(path: &str, cols: usize) -> Result<Vec<Vec<f64>>> {
    let t = fs::read_to_string(path)?;
    let rows = t
        .lines()
        .skip(1)
        .filter(|x| !x.trim().is_empty())
        .map(|line| {
            line.split_whitespace()
                .map(str::parse::<f64>)
                .collect::<std::result::Result<Vec<_>, _>>()
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if rows.is_empty()
        || rows
            .iter()
            .any(|r| r.len() != cols || r.iter().any(|x| !x.is_finite()))
    {
        return Err(format!("invalid data {path}").into());
    }
    Ok(rows)
}
fn near(d: &[Vec<f64>], t: f64) -> &[f64] {
    d.iter()
        .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
        .expect("validated nonempty")
}
fn bounds(d: &[Vec<f64>], a: usize, b: usize) -> (f64, f64) {
    d.iter()
        .flat_map(|r| r[a..b].iter())
        .fold((f64::INFINITY, f64::NEG_INFINITY), |(lo, hi), &x| {
            (lo.min(x), hi.max(x))
        })
}
fn main() -> Result<()> {
    let mut out=String::from("case,tia_dc_step_uv,tia_peak_uv,rise_overshoot_pct,rise_1pct_ns,fall_1pct_ns,high_peak_uv,low_peak_uv,adc_min_v,adc_max_v,rf_min_ua,rf_max_ua,cf_min_ua,cf_max_ua,highout_min_ma,highout_max_ma,lowout_min_ma,lowout_max_ma,tiaout_min_ma,tiaout_max_ma,max_kcl_a\n");
    let csv = fs::read_to_string("run-results.csv")?;
    let mut rows: Vec<Vec<String>> = csv
        .lines()
        .skip(1)
        .map(|l| l.split(',').map(str::to_owned).collect())
        .collect();
    if rows.len() != 7 {
        return Err("expected seven candidate pulse cases".into());
    }
    rows.push(
        "uncompensated5k,PASS,5000,matched,0,0,0,12,5,20,1,0"
            .split(',')
            .map(str::to_owned)
            .collect(),
    );
    let mut md=String::from("# Fixed local 100 pF transient results\n\nAll cases below use the full coupled source/TIDA/FDA network, official unmodified TI models, actual FDA DC input loading, and static ADC RC loading. This is finite-window modeled behavior, not measured hardware accuracy or a universal stability proof.\n\n|Case|TIA DC step / peak (µV)|Rising overshoot (%)|Rise / fall 1% settling (ns)|ADC pin min / max (V)|\n|---|---:|---:|---:|---:|\n");
    let mut dc=String::from("case,fda_mid_a_v,fda_mid_b_v,source_ac_input_dc_v,highout_ma,lowout_ma,tiaout_ma,max_external_kcl_a\n");
    for p in rows {
        let n = &p[0];
        let end: f64 = p[9].parse::<f64>()? * 1e-6;
        let width = if n == "matched100k" { 60e-6 } else { 10e-6 };
        if p[1] != "PASS" {
            return Err(format!("runner failed {n}").into());
        }
        let op = strict_order::true_op(&format!("{n}_op.raw"))?;
        let log = fs::read_to_string(format!("{n}.log"))?;
        if log.contains("Error") || log.contains("aborted") {
            return Err(format!("log failure {n}").into());
        }
        let kcl = data(&format!("{n}_kcl.dat"), 4)?;
        let km = kcl
            .iter()
            .flat_map(|r| r[1..].iter())
            .map(|x| x.abs())
            .fold(0., f64::max);
        if km > 1e-9 {
            return Err(format!("external KCL {n} {km}").into());
        }
        let sig = data(&format!("{n}_signal.dat"), 6)?;
        if sig[0][0] != 1000.0 {
            return Err("1k AC point absent".into());
        }
        let target = data(&format!("{n}_step_target.dat"), 4)?;
        if target.len() != 1 || target[0][0] != 1.0 {
            return Err("1Hz step transfer absent".into());
        }
        let d = data(&format!("{n}_tran.dat"), 15)?;
        if d.len() < 20000
            || (d.last().ok_or("empty")?[0] - end).abs() > 1e-12
            || d.windows(2).any(|w| w[1][0] <= w[0][0])
        {
            return Err(format!("incomplete transient {n}").into());
        }
        let b = near(&d, 0.9e-6);
        let delta = target[0][1] * 1e-6;
        let peak = |c: usize| d.iter().map(|r| (r[c] - b[c]).abs()).fold(0., f64::max);
        let pk = peak(3);
        if pk < 1e-12 {
            return Err("no pulse response".into());
        }
        let over = if p[3] == "coil" {
            None
        } else {
            Some(
                d.iter()
                    .filter(|r| r[0] >= 1.001e-6 && r[0] < 1e-6 + width)
                    .map(|r| (r[3] - b[3]) / delta - 1.)
                    .fold(0., f64::max)
                    * 100.,
            )
        };
        // Last crossing plus the next sample gives conservative discrete settling time.
        let settling = |start: f64, stop: f64, target: f64| -> Option<f64> {
            let last = d
                .iter()
                .enumerate()
                .filter(|(_, r)| r[0] >= start && r[0] < stop && (r[3] - target).abs() > 0.01 * pk)
                .map(|(i, _)| i)
                .last();
            match last {
                None => Some(0.),
                Some(i) => d
                    .get(i + 1)
                    .filter(|r| r[0] < stop)
                    .map(|r| (r[0] - start) * 1e9),
            }
        };
        let rise = settling(1.001e-6, 1e-6 + width, b[3] + delta);
        let fall = settling(1.002e-6 + width, end, b[3]);
        let (al, ah) = bounds(&d, 6, 10);
        let rail: f64 = p[8].parse()?;
        if al < 0.1
            || ah > rail - 0.1
            || d.iter().any(|r| {
                r[1..6].iter().any(|x| x.abs() > 10.0) || r[12..15].iter().any(|x| x.abs() > 0.02)
            })
        {
            return Err(format!("headroom guard {n}").into());
        }
        let (rl, rh) = bounds(&d, 10, 11);
        let (cl, ch) = bounds(&d, 11, 12);
        let (hl, hh) = bounds(&d, 12, 13);
        let (ll, lh) = bounds(&d, 13, 14);
        let (tl, th) = bounds(&d, 14, 15);
        let opt = |x: Option<f64>| x.map_or("not-settled".into(), |v| format!("{v:.6}"));
        let os = over.map_or("NA".into(), |x| format!("{x:.6}"));
        out += &format!(
            "{n},{},{},{os},{},{},{},{},{al},{ah},{},{},{},{},{},{},{},{},{},{},{km}\n",
            delta * 1e6,
            pk * 1e6,
            opt(rise),
            opt(fall),
            peak(4) * 1e6,
            peak(5) * 1e6,
            rl * 1e6,
            rh * 1e6,
            cl * 1e6,
            ch * 1e6,
            hl * 1e3,
            hh * 1e3,
            ll * 1e3,
            lh * 1e3,
            tl * 1e3,
            th * 1e3
        );
        md += &format!(
            "|{n}|{:.6} / {:.6}|{os}|{} / {}|{al:.6} / {ah:.6}|\n",
            delta * 1e6,
            pk * 1e6,
            opt(rise),
            opt(fall)
        );
        dc += &format!(
            "{n},{},{},{},{},{},{},{km}\n",
            op["v(xa.mid)"],
            op["v(xb.mid)"],
            op["v(acin)"],
            b[12] * 1e3,
            b[13] * 1e3,
            b[14] * 1e3
        );
    }
    fs::write("pulse-results.csv", out)?;
    fs::write("results.md", md)?;
    fs::write("dc-kcl.csv", dc)?;
    let mut ac=String::from("range_ohm,frequency_hz,b_over_a_magnitude,b_over_a_phase_deg,a_peak_v_at_dds_0p3,b_peak_v_at_dds_0p3,source_peak_v_at_dds_0p3\n");
    for (n, r) in [
        ("matched100", 100),
        ("matched5k", 5000),
        ("matched100k", 100000),
    ] {
        strict_order::true_op(&format!("ac-{n}_op.raw"))?;
        let d = data(&format!("ac-{n}.dat"), 6)?;
        if d.len() != 21 || (d.last().ok_or("empty")?[0] - 100000.).abs() > 1e-5 {
            return Err(format!("AC endpoint missing {n}").into());
        }
        for row in d.iter().filter(|r| {
            (r[0] - 1000.).abs() < 1e-6
                || (r[0] - 10000.).abs() < 1e-5
                || (r[0] - 100000.).abs() < 1e-5
        }) {
            ac += &format!(
                "{r},{},{},{},{},{},{}\n",
                row[0],
                row[1].hypot(row[2]),
                row[2].atan2(row[1]).to_degrees(),
                row[3] * 0.3,
                row[4] * 0.3,
                row[5] * 0.3
            );
        }
    }
    fs::write("ac-results.csv", ac)?;
    println!("PASS eight full-network pulse cases and three 21-point AC sweeps; finite/MID/DC/KCL/headroom/endtime guards applied");
    Ok(())
}

#[path = "strict_order.rs"]
mod strict_order;
use std::fs;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn data(path: &str, n: usize) -> Result<Vec<Vec<f64>>> {
    let s = fs::read_to_string(path)?;
    let r = s
        .lines()
        .skip(1)
        .filter(|l| !l.trim().is_empty())
        .map(|l| {
            l.split_whitespace()
                .map(str::parse::<f64>)
                .collect::<std::result::Result<Vec<_>, _>>()
        })
        .collect::<std::result::Result<Vec<_>, _>>()?;
    if r.is_empty()
        || r.iter()
            .any(|r| r.len() != n || r.iter().any(|v| !v.is_finite()))
    {
        return Err(format!("invalid {path}").into());
    }
    Ok(r)
}
fn fit(d: &[Vec<f64>], column: impl Fn(&[f64]) -> f64) -> (f64, f64, f64) {
    let mut m = [[0.; 4]; 3];
    for row in d {
        let p = std::f64::consts::TAU * 1e5 * row[0];
        let x = [1., p.cos(), p.sin()];
        let y = column(row);
        for i in 0..3 {
            for j in 0..3 {
                m[i][j] += x[i] * x[j]
            }
            m[i][3] += x[i] * y
        }
    }
    for k in 0..3 {
        let pivot = m[k][k];
        for j in k..4 {
            m[k][j] /= pivot
        }
        for i in 0..3 {
            if i != k {
                let a = m[i][k];
                for j in k..4 {
                    m[i][j] -= a * m[k][j]
                }
            }
        }
    }
    let c = [m[0][3], m[1][3], m[2][3]];
    let amp = c[1].hypot(c[2]);
    let err = d
        .iter()
        .map(|r| {
            let p = std::f64::consts::TAU * 1e5 * r[0];
            (column(r) - c[0] - c[1] * p.cos() - c[2] * p.sin()).powi(2)
        })
        .sum::<f64>()
        / d.len() as f64;
    (amp, c[2].atan2(c[1]).to_degrees(), err.sqrt() / amp)
}
fn main() -> Result<()> {
    let mut out=String::from("case,a_peak_v,b_peak_v,b_over_a_magnitude,a_fit_residual_rms_over_peak,b_fit_residual_rms_over_peak,adc_min_v,adc_max_v,highout_min_ma,highout_max_ma,lowout_min_ma,lowout_max_ma,tiaout_min_ma,tiaout_max_ma,max_kcl_a\n");
    let mut md=String::from("# Final-network sine and common-mode verification\n\nThe sine cases apply DDS SIN(0.3 V DC,0.3 V peak,100 kHz), run 120 µs with maximum 5 ns steps and strict Newton/LTE tolerances. A three-coefficient least-squares DC/cos/sin fit uses the final 40 µs at the actual nonuniform solver timestamps. The outputs are static ADC RC nodes, not simulated digitized codes.\n\n|Case|A peak(V)|B peak(V)|B/A|A / B fit RMS relative to peak|ADC range(V)|\n|---|---:|---:|---:|---:|---:|\n");
    for n in ["sine100", "sine5k", "sine100k", "cm5k"] {
        strict_order::true_op(&format!("{n}_op.raw"))?;
        let log = fs::read_to_string(format!("{n}.log"))?;
        if log.contains("Error") || log.contains("aborted") {
            return Err(format!("log {n}").into());
        }
        let k = data(&format!("{n}_kcl.dat"), 4)?;
        let km = k
            .iter()
            .flat_map(|r| r[1..].iter())
            .map(|v| v.abs())
            .fold(0., f64::max);
        if km > 1e-9 {
            return Err("KCL".into());
        }
        data(&format!("{n}_signal.dat"), 6)?;
        data(&format!("{n}_step_target.dat"), 4)?;
        let d = data(&format!("{n}_tran.dat"), 15)?;
        let end = if n == "cm5k" { 20e-6 } else { 120e-6 };
        if d.len() < 20000
            || (d.last().ok_or("empty")?[0] - end).abs() > 1e-12
            || d.windows(2).any(|w| w[1][0] <= w[0][0])
        {
            return Err(format!("incomplete {n}").into());
        }
        let bounds = |start: usize, end: usize| {
            d.iter()
                .flat_map(|r| r[start..end].iter())
                .fold((f64::INFINITY, f64::NEG_INFINITY), |(a, b), &x| {
                    (a.min(x), b.max(x))
                })
        };
        let (al, ah) = bounds(6, 10);
        let (hl, hh) = bounds(12, 13);
        let (ll, lh) = bounds(13, 14);
        let (tl, th) = bounds(14, 15);
        if al < 0.1
            || ah > 4.9
            || d.iter().any(|r| {
                r[1..6].iter().any(|v| v.abs() > 10.) || r[12..15].iter().any(|v| v.abs() > 0.02)
            })
        {
            return Err(format!("headroom {n}").into());
        }
        if n != "cm5k" {
            let tail: Vec<_> = d.iter().filter(|r| r[0] >= 80e-6).cloned().collect();
            let (aa, _, ar) = fit(&tail, |r| r[6] - r[7]);
            let (ba, _, br) = fit(&tail, |r| r[8] - r[9]);
            if ar > 0.01 || br > 0.01 {
                return Err(format!("sine residual {n} {ar} {br}").into());
            }
            let acname = match n {
                "sine100" => "matched100",
                "sine5k" => "matched5k",
                _ => "matched100k",
            };
            let ac = data(&format!("ac-{acname}.dat"), 6)?;
            let ac = ac.last().ok_or("AC empty")?;
            if (aa / (ac[3] * 0.3) - 1.).abs() > 0.01 || (ba / (ac[4] * 0.3) - 1.).abs() > 0.01 {
                return Err(format!("AC/transient amplitude inconsistency {n}").into());
            }
            out += &format!(
                "{n},{aa},{ba},{},{ar},{br},{al},{ah},{},{},{},{},{},{},{km}\n",
                ba / aa,
                hl * 1e3,
                hh * 1e3,
                ll * 1e3,
                lh * 1e3,
                tl * 1e3,
                th * 1e3
            );
            md += &format!(
                "|{n}|{aa:.9}|{ba:.9}|{:.9}|{ar:.3e} / {br:.3e}|{al:.6}–{ah:.6}|\n",
                ba / aa
            );
        } else {
            let near = |t: f64| {
                d.iter()
                    .min_by(|a, b| (a[0] - t).abs().total_cmp(&(b[0] - t).abs()))
                    .expect("nonempty")
            };
            let baseline = near(0.9e-6);
            let plateau = near(10.9e-6);
            md+="\nThe matched5k common-mode case applies a 10 mV VOCM step with 1 ns edges at 1 µs, 10 µs width, 20 µs window, 1 ns maximum step. ADC common-mode metrics include the 22 Ω internal-feedback isolation drop.\n\n|Channel|CM final change(mV)|CM rising overshoot|CM 1% settling(ns)|Differential peak glitch(µV)|\n|---|---:|---:|---:|---:|\n";
            let mut cm=String::from("channel,cm_step_mv,cm_overshoot_pct,cm_1pct_settling_ns,differential_peak_glitch_uv\n");
            for (label, p, m) in [("A", 6, 7), ("B", 8, 9)] {
                let b = (baseline[p] + baseline[m]) * 0.5;
                let target = (plateau[p] + plateau[m]) * 0.5;
                let delta = target - b;
                let over = d
                    .iter()
                    .filter(|r| r[0] >= 1.001e-6 && r[0] < 10.9e-6)
                    .map(|r| (((r[p] + r[m]) * 0.5 - b) / delta - 1.) * 100.)
                    .fold(0., f64::max);
                let last = d
                    .iter()
                    .enumerate()
                    .filter(|(_, r)| {
                        r[0] >= 1.001e-6
                            && r[0] < 10.9e-6
                            && ((r[p] + r[m]) * 0.5 - target).abs() > delta.abs() * 0.01
                    })
                    .map(|(i, _)| i)
                    .last()
                    .ok_or("no CM transition")?;
                let settle = (d[last + 1][0] - 1.001e-6) * 1e9;
                if d[last + 1][0] > 10.8e-6 {
                    return Err("CM not settled".into());
                }
                let diff = d
                    .iter()
                    .map(|r| ((r[p] - r[m]) - (baseline[p] - baseline[m])).abs())
                    .fold(0., f64::max)
                    * 1e6;
                cm += &format!("{label},{},{over},{settle},{diff}\n", delta * 1e3);
                md += &format!(
                    "|{label}|{:.9}|{over:.6}%|{settle:.3}|{diff:.6}|\n",
                    delta * 1e3
                );
            }
            fs::write("common-mode-results.csv", cm)?;
            md += &format!(
                "\nAll CM ADC nodes stayed {al:.6}–{ah:.6}V. External DC KCL residual≤{km:.3e}A.\n"
            );
        }
    }
    fs::write("sine-results.csv", out)?;
    fs::write("sine-common-mode.md", md)?;
    println!("PASS three matched100kHzsines and one10mVcommon-mode step; fullbias/finite/KCL/headroom/endtime guards; AC-to-transient amplitude consistency within1%");
    Ok(())
}

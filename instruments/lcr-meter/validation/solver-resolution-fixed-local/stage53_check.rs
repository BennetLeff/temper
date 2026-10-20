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
fn fit(d: &[Vec<f64>], hz: f64, p: usize, n: usize) -> (f64, f64, f64) {
    let mut m = [[0.; 4]; 3];
    for row in d {
        let a = std::f64::consts::TAU * hz * row[0];
        let x = [1., a.cos(), a.sin()];
        let y = row[p] - row[n];
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
            let a = std::f64::consts::TAU * hz * r[0];
            (r[p] - r[n] - c[0] - c[1] * a.cos() - c[2] * a.sin()).powi(2)
        })
        .sum::<f64>()
        / d.len() as f64;
    (amp, c[2].atan2(c[1]), err.sqrt() / amp)
}
fn main() -> Result<()> {
    let cases = fs::read_to_string("stage53-cases.csv")?;
    if cases.lines().count() != 5 {
        return Err("four cases required".into());
    }
    let mut out=String::from("case,hz,a_peak_v,b_peak_v,uncalibrated_fit_re_ohm,uncalibrated_fit_im_ohm,a_residual_fraction,b_residual_fraction,adc_min_v,adc_max_v,tiaout_min_ma,tiaout_max_ma,max_kcl_a\n");
    let mut md=String::from("# Stage53 load equivalents on the final 100 Ω range\n\nExact final FDA and local 100 pF compensation; 100 nH RF path and 5 nH local CF path. Ideal isolated DUT equivalents, no fixture ground capacitors for these sine runs. DDS 0.3 V peak. All four strict OP/AC/transient runs pass finite/MID/KCL/endtime/headroom checks. 100 nF and 50 µH + 0.5 Ω use 50 kHz for 240 µs; 500 nF extends to 600 µs. All use maximum 10 ns steps. The 9 µF case uses 1 kHz for 12 ms, maximum 250 ns steps. The final four cycles are fit at actual solver timestamps, except 500 nF uses the final three cycles after its longer settling window. The original 240 µs capacitor record showed about 1% startup residual and is retained under startup-history, excluded from settled qualification. Strict rel 1e−5/abs 1e−12/V 1e−7 tolerances remain unchanged; the smooth 1 kHz drive uses a larger maximum step, with the solver retaining adaptive timesteps.\n\n|DUT|Frequency|A peak(V)|B peak(V)|Uncalibrated fitted Z(Ω)|ADC pin window(V)|TIA outputcurrent(mA)|\n|---|---:|---:|---:|---:|---:|---:|\n");
    for row in cases.lines().skip(1) {
        let p: Vec<_> = row.split(',').collect();
        let n = p[0];
        let hz: f64 = p[1].parse()?;
        let end: f64 = p[2].parse()?;
        if p[5] != "PASS" {
            return Err(format!("runner {n}").into());
        }
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
        let ac = data(&format!("{n}_signal.dat"), 6)?;
        if ac.len() != 1 || ac[0][0] != hz {
            return Err("ACpoint".into());
        }
        let d = data(&format!("{n}_tran.dat"), 15)?;
        if d.len() < 20000
            || (d.last().ok_or("empty")?[0] - end).abs() > 1e-12
            || d.windows(2).any(|w| w[1][0] <= w[0][0])
        {
            return Err(format!("incomplete {n}").into());
        }
        let bounds = |a: usize, b: usize| {
            d.iter()
                .flat_map(|r| r[a..b].iter())
                .fold((f64::INFINITY, f64::NEG_INFINITY), |(l, h), &x| {
                    (l.min(x), h.max(x))
                })
        };
        let (al, ah) = bounds(6, 10);
        let (tl, th) = bounds(14, 15);
        if al < 0.1
            || ah > 4.9
            || d.iter().any(|r| {
                r[1..6].iter().any(|v| v.abs() > 10.)
                    || r[12..15].iter().any(|v| v.abs() > 0.02)
                    || (r[6] - r[7]).abs() > 4.096
                    || (r[8] - r[9]).abs() > 4.096
            })
        {
            return Err(format!("headroom {n}").into());
        }
        let fit_cycles = if n == "stage500n" { 3.0 } else { 4.0 };
        let tail: Vec<_> = d
            .iter()
            .filter(|r| r[0] >= end - fit_cycles / hz)
            .cloned()
            .collect();
        let (aa, ap, ar) = fit(&tail, hz, 6, 7);
        let (ba, bp, br) = fit(&tail, hz, 8, 9);
        if ar > 0.01
            || br > 0.01
            || (aa / (ac[0][3] * 0.3) - 1.).abs() > 0.01
            || (ba / (ac[0][4] * 0.3) - 1.).abs() > 0.01
        {
            return Err(format!("sine/AC consistency {n}").into());
        }
        let wrc = std::f64::consts::TAU * hz * 100. * 100e-12;
        let zabs = 100. / (1. + wrc * wrc).sqrt() * aa / ba;
        let phi = -wrc.atan() + bp - ap;
        let re = zabs * phi.cos();
        let im = zabs * phi.sin();
        out += &format!(
            "{n},{hz},{aa},{ba},{re},{im},{ar},{br},{al},{ah},{},{},{km}\n",
            tl * 1e3,
            th * 1e3
        );
        md += &format!(
            "|{n}|{hz:.0}|{aa:.8}|{ba:.8}|{re:.6} {im:+.6}j|{al:.6}–{ah:.6}|{:.6}–{:.6}|\n",
            tl * 1e3,
            th * 1e3
        );
    }
    md+="\nThe complex values use nominal 100 Ω ∥ 100 pF correction without fixture calibration; they demonstrate coherent sign/scale and signal headroom, not a promised component accuracy. The models include finite-amplifier phase/loading, while DUTs are ideal equivalents. Real stage53 coil resistance, capacitor ESR/tolerance and fixture parasitics require measurement and independent standards. These runs do not model switched ADC sampling, supply-ripple, thermal/noise distributions, turn-on DC transients, or powered/in-circuit stage53 operation.\n";
    fs::write("stage53-results.csv", out)?;
    fs::write("stage53-results.md", md)?;
    println!("PASS four stage53 load-equivalent OP/AC/sine cases, actualtargetfrequencies, fullbiasfinite/KCL/headroom/endtimeandAC/transient consistency");
    Ok(())
}

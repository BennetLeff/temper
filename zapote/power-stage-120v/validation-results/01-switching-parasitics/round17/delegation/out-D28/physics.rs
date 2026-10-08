//! D28 engineering calculations. Standalone rustc; no workspace/native bridge.
use std::{env, fs};
const L: f64 = 70e-6;
const C: f64 = 0.54e-6;
type Mat = [[f64; 2]; 2];
fn mul(a: Mat, x: [f64; 2]) -> [f64; 2] {
    [
        a[0][0] * x[0] + a[0][1] * x[1],
        a[1][0] * x[0] + a[1][1] * x[1],
    ]
}
fn exp(r: f64, t: f64) -> Mat {
    let alpha = r / (2.0 * L);
    let w2 = 1.0 / (L * C) - alpha * alpha;
    let (c, s) = if w2 > 0.0 {
        let w = w2.sqrt();
        ((w * t).cos(), (w * t).sin() / w)
    } else {
        let w = (-w2).sqrt();
        ((w * t).cosh(), (w * t).sinh() / w)
    };
    let d = (-alpha * t).exp();
    [
        [d * (c - alpha * s), -d * s / L],
        [d * s / C, d * (c + alpha * s)],
    ]
}
fn evolve(x: [f64; 2], r: f64, v: f64, t: f64) -> [f64; 2] {
    let z = mul(exp(r, t), [x[0], x[1] - v]);
    [z[0], z[1] + v]
}
fn state(r: f64, v: f64, f: f64, phase: f64) -> ([f64; 2], [f64; 2]) {
    let h = 0.5 / f;
    let delta = phase / 360.0 / f;
    let e = exp(r, h);
    let b = evolve(evolve([0.0, 0.0], r, v, delta), r, 0.0, h - delta);
    let a = e[0][0] + 1.0;
    let d = e[1][1] + 1.0;
    let det = a * d - e[0][1] * e[1][0];
    let x = [
        (-d * b[0] + e[0][1] * b[1]) / det,
        (e[1][0] * b[0] - a * b[1]) / det,
    ];
    (x, evolve(x, r, v, delta))
}
fn ideal() {
    println!("bus_V,R_ohm,phase_deg,leading_A,lagging_A,power_W,zero_after_A_ns,zero_after_B_ns");
    for v in [170.0, 198.0] {
        for r in [2.0, 100.0] {
            for degree in 0..=180 {
                let phase = degree as f64;
                let f = 50000.0;
                let h = 0.5 / f;
                let dt = phase / 360.0 / f;
                let (x, y) = state(r, v, f, phase);
                let n = 10000;
                let mut sum = 0.0;
                let mut zero = None;
                let mut prior = x[0];
                for k in 0..=n {
                    let t = h * k as f64 / n as f64;
                    let z = if t <= dt {
                        evolve(x, r, v, t)
                    } else {
                        evolve(y, r, 0.0, t - dt)
                    };
                    sum += z[0] * z[0] * if k == 0 || k == n { 0.5 } else { 1.0 };
                    if prior < 0.0 && z[0] >= 0.0 && zero.is_none() {
                        zero = Some(t - h / n as f64 + (-prior) / (z[0] - prior) * h / n as f64);
                    }
                    prior = z[0];
                }
                let z = zero
                    .map(|t| format!("{:.6},{:.6}", t * 1e9, (t + h - dt) * 1e9))
                    .unwrap_or("NaN,NaN".into());
                println!(
                    "{v},{r},{phase},{:.9},{:.9},{:.9},{z}",
                    -x[0],
                    y[0],
                    r * sum / n as f64
                );
            }
        }
    }
}
fn interp(rows: &[Vec<f64>], col: usize, t: f64) -> f64 {
    let k = rows.partition_point(|x| x[0] < t);
    // ngspice's save-window boundary can fall between accepted solver points.
    // Only the turn-off current may use the first sample (within 2 ns); the
    // incoming-VDS sample 443 ns later must be interpolated inside the capture.
    if k == 0 {
        assert!(rows[0][0] - t <= 2e-9 && col == 1);
        return rows[0][col];
    }
    assert!(k < rows.len(), "sample outside capture");
    let a = &rows[k - 1];
    let b = &rows[k];
    let u = (t - a[0]) / (b[0] - a[0]);
    a[col] + u * (b[col] - a[col])
}
fn peak(rows: &[Vec<f64>], col: usize, lo: f64, hi: f64) -> f64 {
    rows.iter()
        .filter(|r| r[0] >= lo && r[0] < hi)
        .map(|r| r[col])
        .fold(f64::NEG_INFINITY, f64::max)
}
fn zvs(vds: f64, vbus: f64, current: f64) -> bool {
    current > 0.0 && vds <= 0.05 * vbus
}
fn metrics(
    path: &str,
    vbus: f64,
    f: f64,
    phase: f64,
    cycles: f64,
    resistance: Option<f64>,
) -> Result<(), Box<dyn std::error::Error>> {
    // CSV order: time,tank current, then for A/B each HS/LS die VDS,VGS,ID.
    let rows: Vec<Vec<f64>> = fs::read_to_string(path)?
        .lines()
        .skip(1)
        .map(|l| l.split(',').map(|s| s.parse::<f64>().unwrap()).collect())
        .collect();
    assert!(
        rows.len() > 2
            && rows
                .iter()
                .all(|r| r.len() == 14 && r.iter().all(|x| x.is_finite()))
    );
    assert!(rows.windows(2).all(|w| w[1][0] > w[0][0]));
    let period = 1.0 / f;
    let end = 2e-6 + cycles * period;
    assert!(rows.last().unwrap()[0] >= end - 1e-11);
    // Use penultimate complete cycle so last commutation's integration window fits.
    let start = end - 2.0 * period;
    let dead = 443e-9;
    let mut events = Vec::new();
    let mut total_energy = 0.0;
    for leg in 0..2 {
        for edge in 0..2 {
            let off = start + leg as f64 * phase / 360.0 / f + edge as f64 * period / 2.0;
            let on = off + dead;
            let incoming = if edge == 0 { 0 } else { 1 };
            let outgoing = 1 - incoming;
            let base = 2 + leg * 6;
            let incoming_v = interp(&rows, base + incoming * 3, on);
            let sign = if (leg == 0) == (edge == 0) { -1.0 } else { 1.0 };
            let current = interp(&rows, 1, off + 1e-12) * sign;
            let mut zero_delay = None;
            if current > 0.0 {
                for w in rows.windows(2) {
                    let a = &w[0];
                    let b = &w[1];
                    if a[0] >= off
                        && a[0] < off + period / 2.0
                        && a[1] * sign > 0.0
                        && b[1] * sign <= 0.0
                    {
                        zero_delay =
                            Some((a[0] + (-a[1]) / (b[1] - a[1]) * (b[0] - a[0]) - off) * 1e9);
                        break;
                    }
                }
            }
            let mut offmax = f64::NEG_INFINITY;
            let mut vdsmax = f64::NEG_INFINITY;
            let mut energy = 0.0;
            for pair in rows.windows(2) {
                let a = &pair[0];
                let b = &pair[1];
                let lo = a[0].max(off);
                let hi = b[0].min(on + 0.75e-6);
                if hi > lo {
                    let u = (lo - a[0]) / (b[0] - a[0]);
                    let w = (hi - a[0]) / (b[0] - a[0]);
                    for side in 0..2 {
                        let c = base + side * 3;
                        let v0 = a[c] + u * (b[c] - a[c]);
                        let v1 = a[c] + w * (b[c] - a[c]);
                        vdsmax = vdsmax.max(v0).max(v1);
                        let p0 = (a[c] * a[c + 2]).max(0.0);
                        let p1 = (b[c] * b[c + 2]).max(0.0);
                        energy += ((p0 + u * (p1 - p0)) + (p0 + w * (p1 - p0))) * 0.5 * (hi - lo);
                    }
                }
                if a[0] >= on && a[0] <= on + 0.75e-6 {
                    offmax = offmax.max(a[base + outgoing * 3 + 1]);
                }
            }
            assert!(offmax.is_finite() && vdsmax.is_finite() && energy.is_finite());
            let commutation_off_gate = offmax;
            let commutation_vds = vdsmax;
            // Another leg can disturb this device outside its own commutation
            // window. Screen the full commanded-off half-cycle and full cycle.
            offmax = peak(
                &rows,
                base + outgoing * 3 + 1,
                on,
                off + period / 2.0 + dead,
            );
            vdsmax = peak(&rows, base, start, start + period).max(peak(
                &rows,
                base + 3,
                start,
                start + period,
            ));
            assert!(offmax.is_finite() && vdsmax.is_finite());
            total_energy += energy;
            events.push(format!("{{\"leg\":\"{}\",\"edge\":{},\"current_inductive_A\":{},\"ct_zero_delay_ns\":{},\"incoming_vds_V\":{},\"zvs\":{},\"off_gate_commutation_V\":{},\"vds_commutation_peak_V\":{},\"off_gate_V\":{},\"screen3\":{},\"screen1p9\":{},\"vds_peak_V\":{},\"screen520\":{},\"overlap_uJ\":{}}}",if leg==0 {"A"} else {"B"},edge,current,zero_delay.map(|v|v.to_string()).unwrap_or("null".into()),incoming_v,zvs(incoming_v,vbus,current),commutation_off_gate,commutation_vds,offmax,offmax<3.0,offmax<1.9,vdsmax,vdsmax<520.0,energy*1e6));
        }
    }
    let mut i2 = 0.0;
    for w in rows.windows(2) {
        let a = &w[0];
        let b = &w[1];
        let lo = a[0].max(end - period);
        let hi = b[0].min(end);
        if hi > lo {
            let u = (lo - a[0]) / (b[0] - a[0]);
            let v = (hi - a[0]) / (b[0] - a[0]);
            let p = a[1] * a[1];
            let q = b[1] * b[1];
            i2 += ((p + u * (q - p)) + (p + v * (q - p))) * 0.5 * (hi - lo) / period;
        }
    }
    let power = resistance
        .map(|r| (r * i2).to_string())
        .unwrap_or("null".into());
    println!(
        "{{\"tank_i_rms_A\":{},\"tank_power_W\":{},\"bridge_overlap_proxy_W\":{},\"events\":[{}]}}",
        i2.sqrt(),
        power,
        total_energy * f,
        events.join(",")
    );
    Ok(())
}
fn oracle(path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let mut worst: f64 = 0.0;
    let mut count = 0;
    for line in fs::read_to_string(path)?.lines().skip(1) {
        let v: Vec<f64> = line
            .split(',')
            .map(str::parse::<f64>)
            .collect::<Result<_, _>>()?;
        if v.len() != 5 {
            return Err("oracle row requires R,phase,ia,ib,irms".into());
        }
        let (a, b) = state(v[0], 170.0, 50000.0, v[1]);
        worst = worst.max((a[0] - v[2]).abs()).max((b[0] - v[3]).abs());
        count += 1;
    }
    if count != 6 || worst > 5e-5 {
        return Err(format!("oracle mismatch: count={count}, worst_A={worst}").into());
    }
    println!("PASS: six independent ngspice operating points; maximum transition-current error {worst:.9} A (limit 0.00005 A)");
    Ok(())
}
fn all_true(value: &str, count: Option<usize>) -> bool {
    let parts: Vec<_> = value.split(';').collect();
    !value.is_empty()
        && count.is_none_or(|n| parts.len() == n)
        && parts.iter().all(|p| *p == "true")
}
fn classify(path: &str) -> Result<(), Box<dyn std::error::Error>> {
    println!("label,numerics_qualified,verdict");
    for line in fs::read_to_string(path)?.lines().skip(1) {
        let v: Vec<_> = line.split('\t').collect();
        if v.len() != 10 {
            return Err("classification input requires ten TSV fields".into());
        }
        let qualified = v[1] == "unqualified_complete"
            && v[2] == "complete"
            && v[3] == "comparisons_complete"
            && all_true(v[4], Some(56))
            && all_true(v[5], Some(56));
        let screens = v[6..10].iter().all(|x| all_true(x, Some(4)));
        let verdict = if !qualified {
            "INDETERMINATE"
        } else if screens {
            "PASS_SAMPLED_MODEL"
        } else {
            "FAIL_SAMPLED_MODEL"
        };
        println!("{},{},{}", v[0], qualified, verdict);
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let a: Vec<String> = env::args().collect();
    match a.get(1).map(String::as_str) {
        Some("ideal") if a.len() == 2 => ideal(),
        Some("oracle") if a.len() == 3 => oracle(&a[2])?,
        Some("classify") if a.len() == 3 => classify(&a[2])?,
        Some("metrics") if a.len() == 7 || a.len() == 8 => metrics(
            &a[2],
            a[3].parse()?,
            a[4].parse()?,
            a[5].parse()?,
            a[6].parse()?,
            a.get(7).map(|v| v.parse()).transpose()?,
        )?,
        _ => {
            return Err(
                "usage: physics ideal | oracle CSV | metrics CSV VBUS FREQ PHASE CYCLES".into(),
            )
        }
    }
    Ok(())
}
#[test]
fn periodic_boundary() {
    for r in [2.0, 100.0] {
        for ph in [0.0, 30.0, 90.0, 180.0] {
            let (x, y) = state(r, 170.0, 50000.0, ph);
            let z = evolve(y, r, 0.0, (180.0 - ph) / 360.0 / 50000.0);
            assert!((x[0] + z[0]).abs() < 1e-10);
            assert!((x[1] + z[1]).abs() < 1e-10);
        }
    }
}
#[test]
fn zero_drive() {
    let (x, y) = state(2.0, 170.0, 50000.0, 0.0);
    assert_eq!(x, [0.0, 0.0]);
    assert_eq!(y, [0.0, 0.0]);
}
#[test]
fn full_bridge_symmetry() {
    let (x, y) = state(2.0, 170.0, 50000.0, 180.0);
    assert!((x[0] + y[0]).abs() < 1e-10);
    assert!(x[0] < 0.0);
}

#[test]
fn missing_or_incomplete_screens_never_pass() {
    assert!(!all_true("", None));
    assert!(!all_true("true;true;true", Some(4)));
    assert!(!all_true("true;false;true;true", Some(4)));
    assert!(all_true("true;true;true;true", Some(4)));
}

#[test]
fn full_off_window_catches_other_leg_disturbance() {
    let rows = vec![
        vec![0.0, 0.1],
        vec![0.5, 0.2],
        vec![3.0, 2.2],
        vec![5.0, 15.0],
    ];
    assert_eq!(peak(&rows, 1, 0.0, 1.0), 0.2);
    assert_eq!(peak(&rows, 1, 0.0, 5.0), 2.2);
}

#[test]
fn voltage_alone_does_not_prove_inductive_commutation() {
    assert!(!zvs(0.0, 170.0, -1.0));
    assert!(!zvs(0.0, 170.0, 0.0));
    assert!(!zvs(9.0, 170.0, 10.0));
    assert!(zvs(8.5, 170.0, 10.0));
}

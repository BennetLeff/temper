use std::env;
use std::fmt;
use std::io::{self, BufRead};
const H: [&str; 12] = [
    "time_s", "v_ac_v", "i_ac_a", "v_load_v", "i_load_a", "v_b_v", "i_l_a", "v_d_v", "v_ds_v",
    "v_gs_v", "armed", "on",
];
#[derive(Clone, Copy, Debug)]
struct P {
    t: f64,
    a: f64,
    i: f64,
    lv: f64,
    li: f64,
    b: f64,
    il: f64,
    d: f64,
    ds: f64,
    gs: f64,
    arm: f64,
    on: f64,
}
#[derive(Debug)]
struct E(String);
impl fmt::Display for E {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str(&self.0)
    }
}
#[derive(Clone, Copy)]
struct C {
    expected_end: Option<f64>,
    hz: f64,
    n: usize,
    gap: f64,
    step: Option<f64>,
    nom: f64,
    tol: f64,
    imax: f64,
    drift: f64,
    vd: f64,
    vb: f64,
    vds: f64,
    vgs: f64,
}
impl Default for C {
    fn default() -> Self {
        Self {
            expected_end: None,
            hz: 60.,
            n: 3,
            gap: 1e-3,
            step: Some(1. / (8. * 130_000.)),
            nom: 389.615,
            tol: 0.05,
            imax: 15.,
            drift: 0.005,
            vd: 500.,
            vb: 450.,
            vds: 650.,
            vgs: 25.,
        }
    }
}
#[derive(Debug)]
struct M {
    lo: f64,
    hi: f64,
    vr: f64,
    ir: f64,
    p: f64,
    pf: f64,
    lp: f64,
    bm: f64,
    bmin: f64,
    bmax: f64,
    br: f64,
    cm: Vec<f64>,
    dr: f64,
    il: f64,
    dp: f64,
    bp: f64,
    dsp: f64,
    gsp: f64,
    af: f64,
    of: f64,
    de: f64,
    balance: f64,
    st: Vec<String>,
}
fn finite(x: f64, n: &str) -> Result<f64, E> {
    if x.is_finite() {
        Ok(x)
    } else {
        Err(E(format!("non-finite {n}")))
    }
}
fn parse<R: BufRead>(rd: R, c: C) -> Result<Vec<P>, E> {
    let mut it = rd.lines();
    let hd = it
        .next()
        .ok_or(E("missing header".into()))?
        .map_err(|e| E(e.to_string()))?;
    if hd.split_whitespace().collect::<Vec<_>>() != H {
        return Err(E(format!("exact header required: {}", H.join("\t"))));
    }
    let mut out = Vec::new();
    let mut prev = None;
    for (ln, l) in it.enumerate() {
        let ln = ln + 2;
        let s = l.map_err(|e| E(e.to_string()))?;
        if s.trim().is_empty() {
            return Err(E(format!("line {ln}: blank row")));
        }
        let f = s.split_whitespace().collect::<Vec<_>>();
        if f.len() != 12 {
            return Err(E(format!("line {ln}: expected 12 fields")));
        }
        let mut x = [0.; 12];
        for j in 0..12 {
            x[j] = f[j]
                .parse()
                .map_err(|_| E(format!("line {ln}: invalid {}", H[j])))?;
            finite(x[j], H[j])?;
        }
        if let Some(q) = prev {
            let dt = x[0] - q;
            if dt <= 0. {
                return Err(E(format!("line {ln}: time not strictly increasing")));
            }
            if dt > c.gap {
                return Err(E(format!(
                    "line {ln}: gap {dt:.3e}s exceeds {:.3e}s",
                    c.gap
                )));
            }
            if let Some(mx) = c.step {
                if dt > mx {
                    return Err(E(format!(
                        "line {ln}: step {dt:.3e}s aliases switching current (limit {mx:.3e}s)"
                    )));
                }
            }
        }
        prev = Some(x[0]);
        out.push(P {
            t: x[0],
            a: x[1],
            i: x[2],
            lv: x[3],
            li: x[4],
            b: x[5],
            il: x[6],
            d: x[7],
            ds: x[8],
            gs: x[9],
            arm: x[10],
            on: x[11],
        })
    }
    if out.len() < 2 {
        Err(E("trace has fewer than two samples".into()))
    } else {
        Ok(out)
    }
}
fn at(a: &[P], t: f64) -> Option<P> {
    if t < a[0].t || t > a[a.len() - 1].t {
        return None;
    }
    match a.binary_search_by(|p| p.t.partial_cmp(&t).unwrap()) {
        Ok(i) => Some(a[i]),
        Err(i) if i > 0 && i < a.len() => {
            let (x, y) = (a[i - 1], a[i]);
            let r = (t - x.t) / (y.t - x.t);
            Some(P {
                t,
                a: x.a + r * (y.a - x.a),
                i: x.i + r * (y.i - x.i),
                lv: x.lv + r * (y.lv - x.lv),
                li: x.li + r * (y.li - x.li),
                b: x.b + r * (y.b - x.b),
                il: x.il + r * (y.il - x.il),
                d: x.d + r * (y.d - x.d),
                ds: x.ds + r * (y.ds - x.ds),
                gs: x.gs + r * (y.gs - x.gs),
                arm: x.arm + r * (y.arm - x.arm),
                on: x.on + r * (y.on - x.on),
            })
        }
        _ => None,
    }
}
fn integ<F: Fn(P) -> f64>(a: &[P], lo: f64, hi: f64, f: F) -> Result<f64, E> {
    let mut k = vec![at(a, lo).ok_or(E("cycle start not bracketed".into()))?];
    for p in a {
        if p.t > lo && p.t < hi {
            k.push(*p)
        }
    }
    k.push(at(a, hi).ok_or(E("cycle end not bracketed".into()))?);
    Ok(k.windows(2)
        .map(|z| 0.5 * (z[1].t - z[0].t) * (f(z[0]) + f(z[1])))
        .sum())
}
fn energy(p: P) -> f64 {
    0.5 * 2240e-6 * p.b * p.b + 0.5 * 19.8e-6 * p.d * p.d + 0.5 * 180e-6 * p.il * p.il
}
fn eval(a: &[P], c: C) -> Result<M, E> {
    let en = a.last().ok_or(E("empty trace".into()))?.t;
    if a[0].t < 0.0 || a[0].t > 1e-6 {
        return Err(E("missing startup prefix".into()));
    }
    if let Some(expected) = c.expected_end {
        if (en - expected).abs() > 1e-9 {
            return Err(E(format!("truncated/wrong end: {en} != {expected}")));
        }
    }
    let per = 1. / c.hz;
    let dur = per * c.n as f64;
    if en - a[0].t + 1e-15 < dur {
        return Err(E(format!("coverage shorter than {} integer cycles", c.n)));
    }
    let lo = en - dur;
    let q = |f: fn(P) -> f64| integ(a, lo, en, f).map(|x| x / dur);
    let vr = q(|p| p.a * p.a)?.sqrt();
    let ir = q(|p| p.i * p.i)?.sqrt();
    let p = q(|p| p.a * p.i)?;
    let lp = q(|p| p.lv * p.li)?;
    if p <= 0. {
        return Err(E(format!(
            "non-positive real input power {p:.3e} W; check current sign"
        )));
    }
    if lp < 0. {
        return Err(E(format!("negative load power {lp:.3e} W")));
    }
    let pf = p / (vr * ir);
    if !pf.is_finite() || pf.abs() > 1.000001 {
        return Err(E(format!("invalid PF {pf:?}")));
    }
    if vr < 107.999 || vr > 132.001 {
        return Err(E(format!(
            "mains Vrms {vr:.3} V outside 108--132 V source contract"
        )));
    }
    if lp <= 0. {
        return Err(E(format!("non-positive load power {lp:.3e} W")));
    }
    let bm = q(|p| p.b)?;
    let mut cm = Vec::new();
    for j in (0..c.n).rev() {
        let x = en - per * (j as f64 + 1.);
        cm.push(integ(a, x, x + per, |p| p.b)? / per)
    }
    let cmin = cm.iter().fold(f64::INFINITY, |x, y| x.min(*y));
    let cmax = cm.iter().fold(f64::NEG_INFINITY, |x, y| x.max(*y));
    let dr = (cmax - cmin) / cm[0].abs().max(1e-12);
    let mut mn = f64::INFINITY;
    let mut mx = f64::NEG_INFINITY;
    let (mut il, mut dp, mut bp, mut dsp, mut gsp) = (0.0f64, 0.0f64, 0.0f64, 0.0f64, 0.0f64);
    for x in a.iter().filter(|x| x.t >= lo && x.t <= en) {
        mn = mn.min(x.b);
        mx = mx.max(x.b);
    }
    // Regulation is evaluated over settled cycles; device stress includes
    // the entire cold-start prefix so a startup overshoot cannot disappear.
    for x in a {
        il = il.max(x.il.abs());
        dp = dp.max(x.d.abs());
        bp = bp.max(x.b.abs());
        dsp = dsp.max(x.ds.abs());
        gsp = gsp.max(x.gs.abs())
    }
    let af = q(|p| if p.arm > 0.5 { 1. } else { 0. })?;
    let of = q(|p| if p.on > 0.5 { 1. } else { 0. })?;
    let de = (energy(at(a, en).unwrap()) - energy(at(a, lo).unwrap())) / dur;
    let balance = p - lp - de;
    for value in [
        vr, ir, p, pf, lp, bm, dr, il, dp, bp, dsp, gsp, af, of, de, balance,
    ] {
        finite(value, "derived metric")?;
    }
    let etol = (p.abs() * 0.005).max(1.0);
    let mut st = Vec::new();
    let bl = c.nom * (1. - c.tol);
    let bh = c.nom * (1. + c.tol);
    if bm < bl || bm > bh || mn < bl || mx > bh {
        st.push(format!(
            "bus envelope [{mn:.3},{mx:.3}] V outside engineering screen [{bl:.3},{bh:.3}]"
        ))
    }
    if dr >= c.drift {
        st.push(format!("bus cycle drift {dr:.6} >= {:.6}", c.drift))
    }
    if ir > c.imax {
        st.push(format!(
            "Irms {ir:.3} A exceeds engineering screen {:.3} A",
            c.imax
        ))
    }
    if dp > c.vd {
        st.push(format!("VD peak {dp:.3} V exceeds screen {:.3} V", c.vd))
    }
    if bp > c.vb {
        st.push(format!("VB peak {bp:.3} V exceeds limit {:.3} V", c.vb))
    }
    if dsp > c.vds {
        st.push(format!("VDS peak {dsp:.3} V exceeds rating {:.3} V", c.vds))
    }
    if gsp > c.vgs {
        st.push(format!(
            "|VGS| peak {gsp:.3} V exceeds limit {:.3} V",
            c.vgs
        ))
    }
    if af < 0.99 {
        st.push(format!("arm fraction {af:.4}: loop disabled/unstable"))
    }
    if of < 0.99 {
        st.push(format!(
            "on fraction {of:.4}: local enable disabled/semantics unknown"
        ))
    }
    if balance < -etol {
        st.push(format!(
            "energy balance Pin-Pout-dE/dt={balance:.3} W below -tolerance {etol:.3} W"
        ))
    }
    Ok(M {
        lo,
        hi: en,
        vr,
        ir,
        p,
        pf,
        lp,
        bm,
        bmin: mn,
        bmax: mx,
        br: mx - mn,
        cm,
        dr,
        il,
        dp,
        bp,
        dsp,
        gsp,
        af,
        of,
        de,
        balance,
        st,
    })
}
fn number<I: Iterator<Item = String>>(it: &mut I, name: &str) -> f64 {
    let raw = it.next().unwrap_or_else(|| {
        eprintln!("missing {name}");
        std::process::exit(2)
    });
    let v = raw.parse::<f64>().unwrap_or_else(|_| {
        eprintln!("invalid {name}: {raw}");
        std::process::exit(2)
    });
    if !v.is_finite() || v <= 0. {
        eprintln!("{name} must be finite and > 0");
        std::process::exit(2)
    }
    v
}
fn main() {
    let mut c = C::default();
    let mut file = None;
    let mut x = env::args().skip(1);
    while let Some(s) = x.next() {
        match s.as_str() {
            "--input" => {
                file = Some(x.next().unwrap_or_else(|| {
                    eprintln!("--input requires a path");
                    std::process::exit(2)
                }))
            }
            "--end-s" => c.expected_end = Some(number(&mut x, "--end-s")),
            "--no-switch-check" => c.step = None,
            "--max-gap-s" => c.gap = number(&mut x, "--max-gap-s"),
            "--max-step-s" => c.step = Some(number(&mut x, "--max-step-s")),
            "--cycles" => {
                let v = number(&mut x, "--cycles");
                if v.fract() != 0. || !(3.0..=1000.0).contains(&v) {
                    eprintln!("--cycles must be an integer from3 to1000");
                    std::process::exit(2)
                }
                c.n = v as usize
            }
            "--mains-hz" => c.hz = number(&mut x, "--mains-hz"),
            "--help" => {
                println!(
                    "stdin/--input FILE; --end-s REQUIRED; exact 12-column TSV; --no-switch-check diagnostics only"
                );
                return;
            }
            _ => {
                eprintln!("unknown argument {s}");
                std::process::exit(2)
            }
        }
    }
    if c.expected_end.is_none() {
        eprintln!("--end-s is required to reject incomplete simulations");
        std::process::exit(2);
    }
    let r = if let Some(f) = file {
        match std::fs::File::open(f) {
            Ok(f) => parse(io::BufReader::new(f), c),
            Err(e) => Err(E(e.to_string())),
        }
    } else {
        parse(io::BufReader::new(io::stdin()), c)
    }
    .and_then(|v| eval(&v, c));
    match r {
        Ok(m) => {
            println!(
                "window_s={:.9e}..{:.9e} vrms={:.6} irms={:.6} real_input_power_w={:.6} pf={:.6}",
                m.lo, m.hi, m.vr, m.ir, m.p, m.pf
            );
            println!("load_power_w={:.6} vb_mean_v={:.6} vb_min_v={:.6} vb_max_v={:.6} vb_ripple_pp_v={:.6} vb_cycle_means_v={:?} vb_cycle_drift={:.6}",m.lp,m.bm,m.bmin,m.bmax,m.br,m.cm,m.dr);
            println!(
                "energy_delta_rate_w={:.6} energy_balance_pin_pout_de_w={:.6}",
                m.de, m.balance
            );
            println!("il_peak_a={:.6} vd_peak_v={:.6} vb_peak_v={:.6} vds_peak_v={:.6} vgs_abs_peak_v={:.6} armed_fraction={:.6} on_fraction={:.6}",m.il,m.dp,m.bp,m.dsp,m.gsp,m.af,m.of);
            println!(
                "engineering_screen={}",
                if c.step.is_none() {
                    "DIAGNOSTIC_ONLY"
                } else if m.st.is_empty() {
                    "PASS"
                } else {
                    "STOP"
                }
            );
            for s in &m.st {
                println!("STOP: {s}")
            }
            println!("qualification=NOT_CLAIMED (loss estimate/screen do not establish thermal qualification or product compliance)");
            if !m.st.is_empty() || c.step.is_none() {
                std::process::exit(1)
            }
        }
        Err(e) => {
            eprintln!("REJECTED: {e}");
            std::process::exit(1)
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    fn t(f: impl Fn(f64) -> [f64; 11]) -> String {
        let mut s = H.join("\t") + "\n";
        let (mut z, mut n) = (0., 0);
        while z <= 3. / 60. + 0.001 {
            let v = f(z);
            s.push_str(&format!(
                "{z:.12e}\t{}\n",
                v.iter()
                    .map(|q| format!("{q:.12e}"))
                    .collect::<Vec<_>>()
                    .join("\t")
            ));
            z += if n % 2 == 0 { 0.000071 } else { 0.000113 };
            n += 1
        }
        s
    }
    fn c() -> C {
        C {
            step: None,
            gap: 0.001,
            ..C::default()
        }
    }
    #[test]
    fn startup_stress_is_not_hidden_by_settled_window() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615,
                1.,
                390.,
                if z == 0. { 900. } else { 390. },
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let m = eval(&v, c()).unwrap();
        assert!(m.lo > 0.);
        assert_eq!(m.dsp, 900.);
        assert!(m.st.iter().any(|x| x.contains("VDS peak")));
    }
    #[test]
    fn sine_nonuniform() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615,
                1.,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let m = eval(&v, c()).unwrap();
        assert!((m.vr - 120.2).abs() < 0.3);
        assert!((m.ir - 7.07).abs() < 0.03);
        assert!((m.pf - 1.).abs() < 0.003)
    }
    #[test]
    fn wrong_sign() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                -10. * w,
                400.,
                2.,
                389.615,
                1.,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        assert!(eval(&v, c()).is_err())
    }
    #[test]
    fn malformed_truncated() {
        let s="time_s\tv_ac_v\ti_ac_a\tv_load_v\ti_load_a\tv_b_v\ti_l_a\tv_d_v\tv_ds_v\tv_gs_v\tarmed\ton\n0 1 2\n";
        assert!(parse(Cursor::new(s), c()).is_err());
        let s = t(|_| [170., 10., 400., 2., 389.615, 1., 390., 390., 15., 1., 1.]);
        let z = s.lines().take(8).collect::<Vec<_>>().join("\n");
        let v = parse(Cursor::new(z), c()).unwrap();
        assert!(eval(&v, c()).is_err())
    }
    #[test]
    fn flat_off() {
        let s = t(|_| [170., 0., 400., 0., 389.615, 0., 390., 390., 15., 1., 0.]);
        let v = parse(Cursor::new(s), c()).unwrap();
        assert!(eval(&v, c()).is_err())
    }
    #[test]
    fn mostly_off_healthy_is_stop() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615,
                1.,
                390.,
                390.,
                15.,
                1.,
                0.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let m = eval(&v, c()).unwrap();
        assert!(!m.st.is_empty());
        assert!(m.st.iter().any(|x| x.contains("on fraction")))
    }
    #[test]
    fn oscillating_bus_mean_flat_is_stop() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615 + 40. * w,
                1.,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let m = eval(&v, c()).unwrap();
        assert!(m.st.iter().any(|x| x.contains("bus envelope")))
    }
    #[test]
    fn output_above_input_beyond_storage_is_stop() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                1000.,
                10.,
                389.615,
                1.,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let m = eval(&v, c()).unwrap();
        assert!(m.st.iter().any(|x| x.contains("energy balance")))
    }
    #[test]
    fn malformed_nonfinite_rejected() {
        let s = H.join("\t")
            + "\n0 NaN 1 1 1 389 1 390 390 15 1 1\n0.001 1 1 1 1 389 1 390 390 15 1 1\n";
        assert!(parse(Cursor::new(s), c()).is_err())
    }

    #[test]
    fn truncated_but_three_cycle_trace_is_rejected() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615,
                1.,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        let cfg = C {
            expected_end: Some(0.1),
            ..c()
        };
        assert!(eval(&v, cfg).unwrap_err().0.contains("end"));
    }
    #[test]
    fn derived_energy_overflow_is_rejected() {
        let s = t(|z| {
            let w = (2. * std::f64::consts::PI * 60. * z).sin();
            [
                170. * w,
                10. * w,
                400.,
                2.,
                389.615,
                1e300,
                390.,
                390.,
                15.,
                1.,
                1.,
            ]
        });
        let v = parse(Cursor::new(s), c()).unwrap();
        assert!(eval(&v, c()).is_err());
    }
}

//! Cost-down trade calculations for docs/cost-down.md (Rev C, 2026-10-20).
//!
//! Ideal-network and datasheet-rating arithmetic only; nothing here is a
//! measurement. Writes validation/cost-down.txt and fails (panics) if a
//! recommended option loses a coverage proof or exceeds a rating in a case the
//! document claims it meets.
use std::fmt::Write as _;

const R_TOP: f64 = 10e6; // five 2 MOhm sections per leg
const N_SEC: f64 = 5.;
const RATIO: f64 = 1999.; // Rtop / Rbottom for 2000:1
const C_SEC: f64 = 33e-12;
const F_C: f64 = 1. / (2. * std::f64::consts::PI * 2e6 * 33e-12); // divider crossover

struct HvPart {
    mpn: &'static str,
    tol: f64,
    tcr_ppm: f64,
    p_rated: f64,    // W at 70 C
    t_zero: f64,     // C where the linear derating reaches zero
    v_max: f64,      // maximum working voltage, V
    v_overload: f64, // maximum overload voltage, V (0 = not stated)
}

const HV: [HvPart; 4] = [
    HvPart { mpn: "HVCB2512BDE2M00 (incumbent)", tol: 0.001, tcr_ppm: 25., p_rated: 2., t_zero: 155., v_max: 3000., v_overload: 0. },
    HvPart { mpn: "HV121WF2004T4E (Uni-Royal HV12)", tol: 0.01, tcr_ppm: 100., p_rated: 1., t_zero: 155., v_max: 3000., v_overload: 4000. },
    HvPart { mpn: "HV733ATTE2004F (KOA HV73)", tol: 0.01, tcr_ppm: 100., p_rated: 1., t_zero: 155., v_max: 3000., v_overload: 0. },
    HvPart { mpn: "CHV2512-FX-2004ELF (Bourns CHV)", tol: 0.01, tcr_ppm: 100., p_rated: 1., t_zero: 155., v_max: 3000., v_overload: 0. },
];

/// (description, volts per body, watts per body, continuous?)
fn stress_cases() -> Vec<(&'static str, f64, f64)> {
    let body = R_TOP / N_SEC;
    let r_bot = R_TOP / RATIO;
    let mut v = Vec::new();
    // Intact leg, 3 kV DC on one tip.
    let i = 3000. / (R_TOP + r_bot);
    v.push(("3 kV DC, intact leg (extension)", i * body, i * i * body));
    let i = 1500. / (R_TOP + r_bot);
    v.push(("1.5 kV DC, intact leg (guaranteed)", i * body, i * i * body));
    // One section shorted (exploration study 10).
    let i = 3000. / (R_TOP - body + r_bot);
    v.push(("3 kV DC, one section shorted", i * body, i * i * body));
    // Protective 2 + 3 split: the 3-body group bypassed, two bodies hold the tip.
    v.push(("3 kV DC, 3 bodies bypassed (2-body group holds the tip)", 1500., 1500f64.powi(2) / body));
    v.push(("1.5 kV DC, 3 bodies bypassed", 750., 750f64.powi(2) / body));
    v.push(("3 kVpk sine, 3 bodies bypassed (rms)", 1500. / 2f64.sqrt(), 0.5 * 1500f64.powi(2) / body));
    v.push(("3 kV DC, 2 bodies bypassed (3-body group holds the tip)", 1000., 1000f64.powi(2) / body));
    v
}

/// Low-leg C coverage proof of tools/check.rs, parametrised by the fixed-part
/// tolerance and the S1 kit. Returns (x1_lo, x1_hi, min overlap S1, min overlap S2)
/// or the first gap.
fn coverage(fixed_tol: f64, s1: &[f64]) -> Result<(f64, f64, f64, f64), String> {
    let c_nominal = RATIO * C_SEC / N_SEC * 1e12;
    let (need_lo, need_hi) = (c_nominal * (1. - 0.0826), c_nominal * (1. + 0.0420));
    let parasitic = (2.0, 15.0);
    let tol = 0.01; // select-on-test parts
    let fixed = 10_000.0;
    let (trim_lo, trim_hi) = (12.0, 60.0);
    let s2: Vec<f64> = vec![
        0., 10., 11., 12., 13., 15., 16., 18., 20., 22., 24., 27., 30., 33., 36., 39., 43., 47.,
        51., 56., 62., 68., 75., 82., 91., 100., 110., 120., 130., 150., 160., 180., 200., 220.,
        240., 270., 300., 330., 360.,
    ];
    let covers = |set: &[f64], lo: f64, hi: f64, x: f64| {
        set.iter()
            .map(|&v| (x - v * (1. + tol) - lo).min(hi - (x - v * (1. - tol))))
            .filter(|m| *m >= 0.)
            .reduce(f64::max)
    };
    let stage2_hi = s2.last().unwrap() * (1. - tol) + trim_hi;
    let mut x = trim_lo;
    while x <= stage2_hi {
        covers(&s2, trim_lo, trim_hi, x).ok_or(format!("stage-2 gap at {x:.2} pF"))?;
        x += 0.05;
    }
    let x1_lo = need_lo - parasitic.1 - fixed * (1. + fixed_tol);
    let x1_hi = need_hi - parasitic.0 - fixed * (1. - fixed_tol);
    let mut x = x1_lo;
    while x <= x1_hi {
        covers(s1, trim_lo, stage2_hi, x).ok_or(format!("stage-1 gap at {x:.1} pF"))?;
        x += 0.5;
    }
    let overlap = |set: &[f64], lo: f64, hi: f64| {
        set.windows(2)
            .map(|w| (w[0] * (1. - tol) + hi) - (w[1] * (1. + tol) + lo))
            .fold(f64::INFINITY, f64::min)
    };
    Ok((x1_lo, x1_hi, overlap(s1, trim_lo, stage2_hi), overlap(&s2, trim_lo, trim_hi)))
}

/// DC trim coverage: required pot setting range vs what the pot can reach.
/// Returns (need_lo, need_hi, reach_lo, reach_hi).
fn trim(string_tol: f64, fixed: &[(f64, f64)], pot: f64) -> (f64, f64, f64, f64) {
    let (f_lo, f_hi) = fixed.iter().fold((0., 0.), |a, &(r, t)| (a.0 + r * (1. - t), a.1 + r * (1. + t)));
    let need_lo = R_TOP * (1. - string_tol) / RATIO - f_hi;
    let need_hi = R_TOP * (1. + string_tol) / RATIO - f_lo;
    // Bourns 3296: total resistance +/-10 %; absolute minimum resistance
    // max(1 % of nominal, 2 ohm).
    (need_lo, need_hi, (0.01 * pot).max(2.), pot * 0.9)
}

fn db(x: f64) -> f64 {
    -20. * x.abs().log10()
}

fn main() {
    let mut r = String::new();
    let body = R_TOP / N_SEC;
    writeln!(r, "Rev C cost-down trade calculations (ideal network + datasheet ratings; not measurements).").unwrap();
    writeln!(r, "Divider: 5 x 2 MOhm || 33 pF per leg, Rbottom = Rtop/1999; crossover fc = {:.2} Hz.\n", F_C).unwrap();

    // 1. Voltage / power stress per body against each part's ratings.
    writeln!(r, "1. HV resistor stress per 2 MOhm body versus ratings (70 C ambient; sqrt(P*R) = power-limited continuous voltage).").unwrap();
    for p in &HV {
        let v_pl = (p.p_rated * body).sqrt().min(p.v_max);
        writeln!(r, "   {}: {:.1} %, {} ppm/C, {} W at 70 C (zero at {} C), max working {} V{}; continuous limit {:.0} V.",
            p.mpn, p.tol * 100., p.tcr_ppm, p.p_rated, p.t_zero, p.v_max,
            if p.v_overload > 0. { format!(", max overload {} V", p.v_overload) } else { String::new() }, v_pl).unwrap();
        for (case, v, w) in stress_cases() {
            let ok = v <= v_pl + 1e-9 && w <= p.p_rated + 1e-9;
            writeln!(r, "      {case:<58} {v:>6.0} V {w:>6.3} W  {:>5.1} % of P, {:>5.1} % of V -> {}",
                100. * w / p.p_rated, 100. * v / v_pl, if ok { "within" } else { "EXCEEDS" }).unwrap();
        }
    }
    // Claims the document makes for the chosen part.
    let chosen = &HV[1];
    let v_pl = (chosen.p_rated * body).sqrt();
    for (case, v, w) in stress_cases() {
        let exceeds = !(v <= v_pl && w <= chosen.p_rated);
        let expect = case.starts_with("3 kV DC, 3 bodies bypassed");
        assert_eq!(exceeds, expect, "HV12 rating claim changed: {case}");
    }
    writeln!(r, "   HV12 exceeds its 1 W / sqrt(P*R) rating only in the continuous 3 kV DC case with three bodies bypassed: 1.125 W (112.5 %) and 1500 V against 1414 V.\n").unwrap();

    // 2. DC trim coverage for a 1 % string.
    writeln!(r, "2. DC trim coverage (fixed part tolerance at its corners, every upper-string corner; pot reaches max(1 %, 2 ohm) .. 0.9 x nominal).").unwrap();
    let options: [(&str, f64, Vec<(f64, f64)>, f64); 5] = [
        ("incumbent: 0.1 % string, 4.99 k 0.01 %, 50 ohm pot", 0.001, vec![(4990., 1e-4)], 50.),
        ("1 % string, 4.99 k 0.01 %, 50 ohm pot", 0.01, vec![(4990., 1e-4)], 50.),
        ("1 % string, 4.87 k 0.1 %, 200 ohm pot", 0.01, vec![(4870., 1e-3)], 200.),
        ("1 % string, 4.87 k + 22.1 ohm 0.1 %, 200 ohm pot (study 06)", 0.01, vec![(4870., 1e-3), (22.1, 1e-3)], 200.),
        ("1 % string, 4.87 k 0.1 %, 500 ohm pot (chosen)", 0.01, vec![(4870., 1e-3)], 500.),
    ];
    for (i, (name, st, fixed, pot)) in options.iter().enumerate() {
        let (nl, nh, rl, rh) = trim(*st, fixed, *pot);
        let ok = nl >= rl && nh <= rh;
        let nominal = R_TOP / RATIO - fixed.iter().map(|f| f.0).sum::<f64>();
        writeln!(r, "   {name}: need {nl:.3}..{nh:.3} ohm, pot reaches {rl:.1}..{rh:.1} ohm -> {}; nominal setting {nominal:.1} ohm ({:.1} ohm per turn of 25).",
            if ok { "covered" } else { "GAP" }, pot / 25.).unwrap();
        match i {
            0 | 3 | 4 => assert!(ok, "trim coverage lost: {name}"),
            _ => assert!(!ok),
        }
    }
    writeln!(r, "   Bourns 3296 contact-resistance variation max(1 %, 3 ohm): 3 ohm (600 ppm of Rbottom) at 50/200 ohm, 5 ohm (1000 ppm) at 500 ohm.\n").unwrap();

    // 3. DC CMRR drift from TCR mismatch (worst-case bound from the TCR specs,
    // linear TCR assumed over the range).
    writeln!(r, "3. DC differential-ratio drift between legs from TCR (worst-case from datasheet TCR limits, linear TCR assumed).").unwrap();
    let rb = R_TOP / RATIO;
    let bottom = |r11: f64, t11: f64, pot_set: f64, tpot: f64| (r11 * t11 + pot_set * tpot) / rb;
    let legs = [
        ("incumbent (25 ppm string; 4.99 k 5 ppm + 12.5 ohm of 100 ppm pot)", 25., bottom(4990., 5., 12.5, 100.)),
        ("chosen (100 ppm string; 4.87 k 25 ppm + 132.5 ohm of 100 ppm pot)", 100., bottom(4870., 25., 132.5, 100.)),
    ];
    let mut per_c = Vec::new();
    for (name, at, ab) in &legs {
        let k = 2. * (at + ab); // ppm per C, one leg at +TCR, the other at -TCR
        per_c.push(k);
        write!(r, "   {name}: bottom {ab:.2} ppm/C; leg mismatch <= {k:.1} ppm/C.").unwrap();
        for dt in [5., 10., 30., 60.] {
            let d = k * dt * 1e-6;
            write!(r, " |dT| {dt:.0} C: {:.0} ppm ({:.1} dB)", d * 1e6, db(d)).unwrap();
        }
        writeln!(r).unwrap();
    }
    let g35 = 1. / (1. + (35e3 / F_C).powi(2)).sqrt();
    let g60 = 1. / (1. + (60e3 / F_C).powi(2)).sqrt();
    writeln!(r, "   Above crossover the resistive error reaches the output scaled by |1/(1+jf/fc)| = {g35:.5} at 35 kHz, {g60:.5} at 60 kHz:").unwrap();
    for (i, (name, ..)) in legs.iter().enumerate() {
        let d = per_c[i] * 10. * 1e-6;
        writeln!(r, "      {}: |dT| 10 C -> {:.0} ppm ({:.1} dB) at 35 kHz, {:.0} ppm ({:.1} dB) at 60 kHz.",
            name.split(' ').next().unwrap(), d * g35 * 1e6, db(d * g35), d * g60 * 1e6, db(d * g60)).unwrap();
    }

    // 4. Self-heating. Thermal resistance is board-dependent; the two
    // manufacturers' derating curves imply (T_zero - 70)/P_rated for their own
    // test boards. Both values are applied to both parts as a range, not a bound.
    let thetas = [(155. - 70.) / 2., (155. - 70.) / 1.];
    writeln!(r, "\n4. Self-heating (body rise = P x theta; theta {:.1}..{:.1} K/W from the two derating curves, applied to both parts; an estimate, not a bound).", thetas[0], thetas[1]).unwrap();
    let i3 = 3000. / (R_TOP + rb);
    let p3 = i3 * i3 * body;
    for (name, at, _) in &legs {
        let short = name.split(' ').next().unwrap();
        for (label, p) in [("3 kV DC", p3), ("1.5 kV DC", p3 / 4.), ("3 kVpk sine", p3 / 2.)] {
            let (d0, d1) = (p * thetas[0], p * thetas[1]);
            writeln!(r, "   {short}, {label}: {p:.3} W/body, rise {d0:.1}..{d1:.1} K. Common-mode (both legs heated equally) mismatch <= {:.0}..{:.0} ppm ({:.1}..{:.1} dB); one tip only: that leg's gain moves <= {:.0}..{:.0} ppm.",
                2. * at * d0, 2. * at * d1, db(2. * at * d0 * 1e-6), db(2. * at * d1 * 1e-6), at * d0, at * d1).unwrap();
        }
    }
    writeln!(r, "   Neither part specifies a voltage coefficient; that remains a measured qualification item for both.\n").unwrap();

    // 5. AC section mismatch (study 06 method) for a 1 % string with equal C.
    let mut worst = [0f64; 2];
    for mask in 0..32u32 {
        for (k, f) in [35e3, 60e3].iter().enumerate() {
            let w = 2. * std::f64::consts::PI * f;
            let (mut zr, mut zi, mut rsum) = (0., 0., 0.);
            for s in 0..5 {
                let ri = body * if mask >> s & 1 == 1 { 1.01 } else { 0.99 };
                rsum += ri;
                let (a, b) = (1., w * ri * C_SEC);
                let den = a * a + b * b;
                zr += ri * a / den;
                zi += -ri * b / den;
            }
            let rbot = rsum / RATIO;
            let cbot = RATIO * C_SEC / N_SEC;
            let b = w * rbot * cbot;
            let den = 1. + b * b;
            let (br, bi) = (rbot / den, -rbot * b / den);
            let (tr, ti) = (zr + br, zi + bi);
            // Complex H = B / T, normalised error |2000 H - 1|.
            let d = tr * tr + ti * ti;
            let (hr, hi) = ((br * tr + bi * ti) / d, (bi * tr - br * ti) / d);
            worst[k] = worst[k].max(((2000. * hr - 1.).powi(2) + (2000. * hi).powi(2)).sqrt());
        }
    }
    writeln!(r, "5. AC ratio error from +/-1 % section mismatch, equal 33 pF, all 32 corners after DC trim: <= {:.2} ppm at 35 kHz, {:.2} ppm at 60 kHz (complex).\n", worst[0] * 1e6, worst[1] * 1e6).unwrap();
    assert!(worst[0] < 10e-6 && worst[1] < 10e-6);

    // 6. Low-leg C coverage at candidate fixed-part tolerances.
    writeln!(r, "6. Low-leg compensation coverage (tools/check.rs algorithm) at candidate tolerances of the fixed 10 nF part:").unwrap();
    let e24_s1 = [1800., 2000., 2200., 2400., 2700., 3000., 3300., 3600., 3900.];
    let e24_s1_wide = [1500., 1600., 1800., 2000., 2200., 2400., 2700., 3000., 3300., 3600., 3900.];
    for (tol, set, label) in [
        (0.01, &e24_s1[..], "1 % (incumbent KEMET and chosen Yageo CC1206FKNPO9BN103), S1 1.8-3.9 nF"),
        (0.02, &e24_s1[..], "2 %, S1 1.8-3.9 nF"),
        (0.05, &e24_s1[..], "5 %, S1 1.8-3.9 nF"),
        (0.05, &e24_s1_wide[..], "5 %, S1 1.5-3.9 nF"),
    ] {
        match coverage(tol, set) {
            Ok((lo, hi, o1, o2)) => writeln!(r, "   {label}: PASS; stage-1 residual {lo:.1}..{hi:.1} pF; overlaps >= {o1:.1} pF (S1), {o2:.1} pF (S2).").unwrap(),
            Err(e) => writeln!(r, "   {label}: FAIL ({e}).").unwrap(),
        }
    }
    assert!(coverage(0.01, &e24_s1).is_ok());
    assert!(coverage(0.05, &e24_s1).is_err());
    assert!(coverage(0.05, &e24_s1_wide).is_ok());

    std::fs::write("validation/cost-down.txt", &r).unwrap();
    print!("{r}");
}

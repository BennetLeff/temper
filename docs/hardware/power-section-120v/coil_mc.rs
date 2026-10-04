// Monte Carlo design-robustness screen over ASSUMED coil/pan distributions.
//
// Purpose: rank candidate coil targets and topologies, and find which
// uncertain parameter drives failure (i.e. what to measure first). It does
// NOT certify component limits: the priors below are engineering
// assumptions anchored to a handful of published points, not an observed
// population. Worst-case corners still size parts.
//
//   rustc --edition=2021 -O docs/hardware/power-section-120v/coil_mc.rs -o /tmp/coil_mc
//   /tmp/coil_mc [samples] [seed] > docs/hardware/power-section-120v/coil-mc-output.txt
//   rustc --edition=2021 --test docs/hardware/power-section-120v/coil_mc.rs -o /tmp/coil_mc_t && /tmp/coil_mc_t

use std::f64::consts::PI;

// ---------- deterministic RNG (splitmix64), no crates ----------
struct Rng(u64);
impl Rng {
    fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
    fn uniform(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn range(&mut self, lo: f64, hi: f64) -> f64 {
        lo + (hi - lo) * self.uniform()
    }
    fn log_range(&mut self, lo: f64, hi: f64) -> f64 {
        (lo.ln() + (hi.ln() - lo.ln()) * self.uniform()).exp()
    }
    fn normal(&mut self, mean: f64, sd: f64) -> f64 {
        let u1 = self.uniform().max(1e-300);
        let u2 = self.uniform();
        mean + sd * (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
    }
}

// ---------- priors ----------
// Pan classes. kl = L_loaded / L_no_pan; r40 = reflected pan resistance per
// µH of no-pan inductance at 40 kHz (ohm/µH), a turns-independent ratio.
// Anchors (see provisional-coil-pan-model.md on the coil-intake branch):
//   Infineon kit chart: kl 60/87 = 0.69, r40 2.91/87 = 0.0334
//   MDPI 180 mm study transferred: cast iron kl 0.816 r 0.0445;
//   stainless kl 0.744 r 0.0347; Silargan kl 0.628 r 0.0246
//   Half-coupling synthetic: kl 0.845 r 0.0167
// Tri-ply/clad has NO measured anchor here; its range is a guess.
struct PanClass {
    name: &'static str,
    weight: f64,
    kl: (f64, f64),
    r40: (f64, f64),
}
const PANS: [PanClass; 5] = [
    PanClass { name: "cast_iron", weight: 0.25, kl: (0.74, 0.86), r40: (0.036, 0.052) },
    PanClass { name: "carbon_or_430_steel", weight: 0.25, kl: (0.66, 0.80), r40: (0.029, 0.041) },
    PanClass { name: "triply_clad_GUESS", weight: 0.25, kl: (0.66, 0.82), r40: (0.018, 0.032) },
    PanClass { name: "low_R_silargan_like", weight: 0.10, kl: (0.58, 0.68), r40: (0.020, 0.029) },
    PanClass { name: "offset_or_small_pan", weight: 0.15, kl: (0.80, 0.90), r40: (0.012, 0.022) },
];
// Coil winding quality: R_coil per µH (ohm/µH), log-uniform. Kit = 0.0039.
const COIL_Q: (f64, f64) = (0.0015, 0.0060);
const L_TOL_SD: f64 = 0.05; // coil inductance manufacturing spread
const C_TOL_SD: f64 = 0.03; // resonant capacitor spread (±10 % parts)
const FREQ_EXP: f64 = 0.5; // R_pan ∝ f^0.5 (ASSUMED skin-effect scaling)

// ---------- design constraints ----------
const PHASE_MIN_DEG: f64 = 20.0; // ZVS margin at the operating point
// Historical comparative allocation, not an operating limit. The broader
// protection calculation gives shunt 38.44–85.55 A and CT 50.56–60.01 A
// static bands; 45 A overlaps the shunt band. See readiness/power/README.md.
const I_PK_MAX: f64 = 45.0;
// Comparison knob only. 942C's 1,200 Vdc and 430 Vac at 60 Hz do not establish
// an allowable 30–50 kHz voltage at temperature for the selected bank.
const COMPARATIVE_VC_PK: f64 = 650.0;
const F_MIN: f64 = 20e3; // audible limit
const F_MAX: f64 = 60e3;
const PF: f64 = 0.95;
const I_LINE_MAX: f64 = 15.0;
// Losses outside the tank: diode bridge (~29 W at 15 A) + 9.8 W allowance.
const FRONT_LOSS: f64 = 39.0;
// Selected full bridge: four single IPW65R018CFD7, one per position.
// Historical half-bridge comparison: two paralleled 600 V CFD7 per position
// (also four devices total). Both use an inherited 35 mΩ hot/device proxy;
// neither hot value nor switching loss is selected-part qualification.
fn r_on_position(topo: Topo) -> f64 {
    if topo == Topo::Full { 0.035 } else { 0.035 / 2.0 }
}

#[derive(Clone, Copy, PartialEq)]
enum Topo {
    Half,
    Full,
}

#[derive(Clone, Copy)]
struct Design {
    name: &'static str,
    topo: Topo,
    l0_uh: f64,  // nominal no-pan inductance
    f_ref: f64,  // resonant frequency with the reference pan (kl 0.69)
}

struct Sample {
    pan: usize,
    l0: f64,
    kl: f64,
    r40: f64,
    q: f64,
    c: f64,
}

struct Outcome {
    pass: bool,
    reason: &'static str,
    eff: f64,     // pan power / input power at the operating point
    f_op: f64,
    p_min_60k: f64,
    p_max: f64, // max tank power within limits (W)
    vc_crest: f64,
    vc_line_rms: f64,
}

// The first harmonic has a switching-frequency sine whose envelope follows
// the rectified mains sine. Its line-cycle RMS is crest / 2. For the
// half-bridge's split-cap comparison, remove the bus/2 DC term first.
fn cap_line_rms(topo: Topo, vc_crest: f64, line_vrms: f64) -> f64 {
    let ac_crest = match topo {
        Topo::Full => vc_crest,
        Topo::Half => vc_crest - line_vrms * 2f64.sqrt() / 2.0,
    };
    ac_crest / 2.0
}

/// Line-averaged tank quantities for an unfiltered bus at frequency f.
fn tank_at(topo: Topo, vrms: f64, l: f64, c: f64, r: f64, f: f64) -> (f64, f64, f64, f64) {
    let vpk = vrms * 2f64.sqrt();
    let g = if topo == Topo::Half { 1.0 } else { 2.0 };
    let w = 2.0 * PI * f;
    let x = w * l - 1.0 / (w * c);
    let z2 = r * r + x * x;
    let p = g * g * vpk * vpk * r / (PI * PI * z2);
    let ipk = 2.0 * g * vpk / (PI * z2.sqrt()); // tank sine peak at line crest
    let vc = match topo {
        Topo::Half => vpk / 2.0 + ipk / (w * c), // split caps: each C/2 carries I/2
        Topo::Full => ipk / (w * c),
    };
    (p, ipk, vc, x.atan2(r).to_degrees())
}

/// Lowest frequency in [F_MIN, F_MAX] at which `ok` holds (constraints relax
/// monotonically above resonance). None if it fails even at F_MAX.
fn lowest_ok(ok: &dyn Fn(f64) -> bool) -> Option<f64> {
    if !ok(F_MAX) {
        return None;
    }
    if ok(F_MIN) {
        return Some(F_MIN);
    }
    let (mut lo, mut hi) = (F_MIN, F_MAX);
    for _ in 0..60 {
        let mid = 0.5 * (lo + hi);
        if ok(mid) { hi = mid } else { lo = mid }
    }
    Some(hi)
}

fn evaluate(d: &Design, s: &Sample, vrms: f64) -> Outcome {
    let l_loaded = s.l0 * 1e-6 * s.kl;
    let r_coil = s.q * s.l0;
    let r_pan_at = |f: f64| s.r40 * s.l0 * (f / 40e3).powf(FREQ_EXP);
    let r_at = |f: f64| r_coil + r_pan_at(f);
    let p_in = I_LINE_MAX * vrms * PF;
    let in_path = if d.topo == Topo::Half { 1.0 } else { 2.0 };
    let q = |f: f64| tank_at(d.topo, vrms, l_loaded, s.c, r_at(f), f);
    let fail = |reason| Outcome { pass: false, reason, eff: 0.0, f_op: 0.0, p_min_60k: 0.0, p_max: 0.0, vc_crest: 0.0, vc_line_rms: 0.0 };
    // Each limit separately, so the binding one can be named.
    let fp = lowest_ok(&|f| q(f).3 >= PHASE_MIN_DEG);
    // Current and capacitor voltage peak at resonance, so each is only
    // monotonic above it: search them together with "inductive" (phase >= 0).
    let fi = lowest_ok(&|f| q(f).3 >= 0.0 && q(f).1 <= I_PK_MAX);
    let fv = lowest_ok(&|f| q(f).3 >= 0.0 && q(f).2 <= COMPARATIVE_VC_PK);
    let (fp, fi, fv) = match (fp, fi, fv) {
        (Some(a), Some(b), Some(c)) => (a, b, c),
        _ => return fail("screen-unreachable: a provisional constraint fails at f_max"),
    };
    let f_floor = fp.max(fi).max(fv);
    let binding = if f_floor == F_MIN {
        "audible floor"
    } else if f_floor == fp {
        "phase margin"
    } else if f_floor == fi {
        "peak current"
    } else {
        "capacitor voltage"
    };
    let p_max = q(f_floor).0;
    let p60 = q(F_MAX).0;
    let mut p_need = p_in - FRONT_LOSS;
    let mut f_op = f_floor;
    for _ in 0..4 {
        if p_max < p_need {
            let mut o = fail(match binding {
                "phase margin" => "power-limited: phase margin (impedance too high)",
                "peak current" => "power-limited: peak current",
                "capacitor voltage" => "power-limited: comparative capacitor screen",
                _ => "power-limited: audible floor",
            });
            o.p_max = p_max;
            o.p_min_60k = p60;
            return o;
        }
        let (mut a, mut b) = (f_floor, F_MAX);
        for _ in 0..60 {
            let m = 0.5 * (a + b);
            if q(m).0 > p_need { a = m } else { b = m }
        }
        f_op = 0.5 * (a + b);
        let i2 = q(f_op).0 / r_at(f_op);
        p_need = p_in - FRONT_LOSS - i2 * in_path * r_on_position(d.topo);
    }
    let (p, _, vc_crest, _) = q(f_op);
    let pan = p * r_pan_at(f_op) / r_at(f_op);
    Outcome { pass: true, reason: "", eff: pan / p_in, f_op, p_min_60k: p60, p_max,
        vc_crest, vc_line_rms: cap_line_rms(d.topo, vc_crest, vrms) }
}

fn draw(rng: &mut Rng, d: &Design) -> Sample {
    let u = rng.uniform();
    let mut acc = 0.0;
    let mut pan = PANS.len() - 1;
    for (i, pc) in PANS.iter().enumerate() {
        acc += pc.weight;
        if u < acc {
            pan = i;
            break;
        }
    }
    let pc = &PANS[pan];
    let l0 = d.l0_uh * rng.normal(1.0, L_TOL_SD).max(0.7);
    // Capacitor chosen for f_ref with the reference pan on the NOMINAL coil.
    let c_nom = 1.0 / ((2.0 * PI * d.f_ref).powi(2) * d.l0_uh * 1e-6 * 0.69);
    Sample {
        pan,
        l0,
        kl: rng.range(pc.kl.0, pc.kl.1),
        r40: rng.range(pc.r40.0, pc.r40.1),
        q: rng.log_range(COIL_Q.0, COIL_Q.1),
        c: c_nom * rng.normal(1.0, C_TOL_SD).max(0.8),
    }
}

fn pct(v: &[f64], p: f64) -> f64 {
    if v.is_empty() {
        return f64::NAN;
    }
    let mut v = v.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    v[((v.len() - 1) as f64 * p).round() as usize]
}

/// Pans for the comparative full-power ranking. No part qualification follows.
const INTENDED: [usize; 3] = [0, 1, 2];

struct Summary {
    pass_intended: f64,
    screen_unreachable: f64,
    eff_p05: f64,
    eff_p50: f64,
    vc_crest_p95: f64,
    vc_rms_p95: f64,
    detail: Vec<String>,
}

fn run(d: &Design, n: usize, seed: u64, vrms: f64, verbose: bool) -> Summary {
    let mut rng = Rng(seed);
    let p_need = I_LINE_MAX * vrms * PF - FRONT_LOSS;
    let (mut n_int, mut pass_int, mut unreachable_n) = (0usize, 0usize, 0usize);
    let mut by_pan = vec![(0usize, 0usize); PANS.len()];
    let mut derate: Vec<Vec<f64>> = vec![Vec::new(); PANS.len()];
    let (mut effs, mut fops, mut p60s) = (Vec::new(), Vec::new(), Vec::new());
    let (mut cap_crest, mut cap_rms) = (Vec::new(), Vec::new());
    let mut reasons: Vec<(&str, usize)> = Vec::new();
    let mut sens = [[(0usize, 0usize); 2]; 4]; // intended cookware only
    for _ in 0..n {
        let s = draw(&mut rng, d);
        let o = evaluate(d, &s, vrms);
        if o.reason.starts_with("screen-unreachable") {
            unreachable_n += 1;
        }
        by_pan[s.pan].1 += 1;
        if o.pass {
            cap_crest.push(o.vc_crest);
            cap_rms.push(o.vc_line_rms);
            by_pan[s.pan].0 += 1;
        }
        derate[s.pan].push((o.p_max / p_need).min(1.0));
        if !INTENDED.contains(&s.pan) {
            continue;
        }
        n_int += 1;
        let pc = &PANS[s.pan];
        let halves = [
            s.l0 >= d.l0_uh,
            (s.kl - pc.kl.0) / (pc.kl.1 - pc.kl.0) >= 0.5,
            (s.r40 - pc.r40.0) / (pc.r40.1 - pc.r40.0) >= 0.5,
            (s.q.ln() - COIL_Q.0.ln()) / (COIL_Q.1.ln() - COIL_Q.0.ln()) >= 0.5,
        ];
        for (i, hi) in halves.iter().enumerate() {
            let c = &mut sens[i][*hi as usize];
            c.1 += 1;
            if o.pass { c.0 += 1 }
        }
        if o.pass {
            pass_int += 1;
            effs.push(o.eff);
            fops.push(o.f_op);
            p60s.push(o.p_min_60k);
        } else if let Some(r) = reasons.iter_mut().find(|r| r.0 == o.reason) {
            r.1 += 1;
        } else {
            reasons.push((o.reason, 1));
        }
    }
    let rate = |a: (usize, usize)| if a.1 == 0 { f64::NAN } else { 100.0 * a.0 as f64 / a.1 as f64 };
    let mut detail = Vec::new();
    if verbose {
        detail.push(format!(
            "  f_op p05-p95 {:.1}-{:.1} kHz; tank power at 60 kHz p50 {:.0} W, p95 {:.0} W (burst handoff)",
            pct(&fops, 0.05) / 1e3, pct(&fops, 0.95) / 1e3, pct(&p60s, 0.5), pct(&p60s, 0.95)
        ));
        let pans: Vec<String> = PANS
            .iter()
            .enumerate()
            .map(|(i, p)| format!("{} full-power {:.0}% (median {:.0}% of full)", p.name, rate(by_pan[i]), 100.0 * pct(&derate[i], 0.5)))
            .collect();
        detail.push(format!("  by pan: {}", pans.join("; ")));
        let names = ["coil L0", "pan coupling", "pan resistance", "coil resistance"];
        let sv: Vec<String> = names
            .iter()
            .zip(&sens)
            .map(|(nm, c)| format!("{} low-half {:.0}% vs high-half {:.0}%", nm, rate(c[0]), rate(c[1])))
            .collect();
        detail.push(format!("  intended-cookware pass by input half: {}", sv.join("; ")));
        if !reasons.is_empty() {
            let r: Vec<String> = reasons.iter().map(|(a, b)| format!("{} ({})", a, b)).collect();
            detail.push(format!("  intended-cookware failures: {}", r.join("; ")));
        }
    }
    Summary {
        pass_intended: 100.0 * pass_int as f64 / n_int.max(1) as f64,
        screen_unreachable: 100.0 * unreachable_n as f64 / n as f64,
        eff_p05: 100.0 * pct(&effs, 0.05),
        eff_p50: 100.0 * pct(&effs, 0.5),
        vc_crest_p95: pct(&cap_crest, 0.95),
        vc_rms_p95: pct(&cap_rms, 0.95),
        detail,
    }
}

fn print_row(d: &Design, v: f64, s: &Summary) {
    println!(
        "{},{},{:.0},{:.1},{:.0},{:.1},{:.1},{:.1},{:.1},{:.0},{:.0}",
        d.name,
        if d.topo == Topo::Half { "half" } else { "full" },
        d.l0_uh,
        d.f_ref / 1e3,
        v,
        s.pass_intended,
        s.screen_unreachable,
        s.eff_p05,
        s.eff_p50,
        s.vc_crest_p95,
        s.vc_rms_p95
    );
    for l in &s.detail {
        println!("{}", l);
    }
}

fn selected_cap_reference_frequency() -> f64 {
    1.0 / (2.0 * PI * (70e-6 * 0.69 * 0.54e-6f64).sqrt())
}

// Deliberately enumerate simultaneous endpoint combinations. These are
// design probes, not probabilities or a physical worst-case certificate.
fn print_selected_corners(d: &Design, vrms: f64) {
    let mut n = 0;
    let mut full_power = 0;
    let mut unreachable = 0;
    let mut vc_max: f64 = 0.0;
    let mut vac_rms_max: f64 = 0.0;
    let mut vc_60k_max: f64 = 0.0;
    for (pan, pc) in PANS.iter().enumerate() {
        for l_factor in [0.90, 1.10] {
            for kl in [pc.kl.0, pc.kl.1] {
                for r40 in [pc.r40.0, pc.r40.1] {
                    for q in [COIL_Q.0, COIL_Q.1] {
                        for c_factor in [0.90, 1.10] {
                            let s = Sample { pan, l0: d.l0_uh * l_factor, kl, r40, q,
                                c: 0.54e-6 * c_factor };
                            let o = evaluate(d, &s, vrms);
                            let l = s.l0 * 1e-6 * s.kl;
                            let r = s.q * s.l0 + s.r40 * s.l0 * (F_MAX / 40e3).powf(FREQ_EXP);
                            vc_60k_max = vc_60k_max.max(tank_at(d.topo, vrms, l, s.c, r, F_MAX).2);
                            n += 1;
                            full_power += usize::from(o.pass);
                            unreachable += usize::from(o.reason.starts_with("screen-unreachable"));
                            if o.pass {
                                vc_max = vc_max.max(o.vc_crest);
                                vac_rms_max = vac_rms_max.max(o.vc_line_rms);
                            }
                        }
                    }
                }
            }
        }
    }
    println!("{vrms:.0},{n},{full_power},{unreachable},{vc_max:.0},{vac_rms_max:.0},{vc_60k_max:.0}");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let n: usize = args.get(1).and_then(|s| s.parse().ok()).unwrap_or(20000);
    let seed: u64 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(20260925);
    println!("# Coil/pan Monte Carlo, seed={}", seed);
    println!("# ASSUMED priors; percentages rank alternatives, not a cookware population or component safety.");
    println!("# Comparative screens: phase>={}deg, Ipk<={}A, Vc_crest<={}V (UNQUALIFIED), {}-{} kHz, 15 A line, PF {}",
             PHASE_MIN_DEG, I_PK_MAX, COMPARATIVE_VC_PK, F_MIN / 1e3, F_MAX / 1e3, PF);
    println!("# Selected bank 942C12P22K-F x2 + 942C12P1K-F: 1200 Vdc, 430 Vac at 60 Hz catalog; 30-50 kHz hot waveform envelope NOT ESTABLISHED.");
    println!("# Cap RMS estimate is first-harmonic switching-ripple line-cycle RMS, not an actual waveform, AC-frequency rating or safe margin. P95 only among modeled full-power draws; half-bridge low-frequency/DC voltage is excluded.");
    println!("# CURRENT ENVELOPE UNRELEASED: 45 A is a historical comparative screen, not a normal-operation command or an implementable full-power claim.");
    println!("# Independent detectors: shunt static 38.44–85.55 A (+85 C board, assumed +50 C R5 rise); CT static 50.56–60.01 A (temperature/tolerance model). 45 A overlaps the shunt band; the older CT-only 50.93–59.51 A model does not resolve it.");
    println!("# model_full_power fields use the historical comparative screens only. Shunt dynamics, control error/overshoot, fault-to-current-extinction and selected capacitor limits are NOT qualified; do not use these rows to release firmware or hardware.");
    println!("# Loss proxy: full bridge four single 650 V IPW65R018CFD7 (35 mohm/position); half bridge four parallel-paired historical 600 V CFD7 (17.5 mohm/position); hot/switching loss unverified.");
    let header = "design,topology,L0_uH,f_ref_kHz,line_V,model_full_power_pct,screen_unreachable_pct,eff_p05_pct,eff_p50_pct,cap_crest_p95_V,cap_line_rms_p95_V";

    // 1. Grid search over the free design choices at 114 V (US low line).
    let n_grid = (n / 5).max(1000);
    let mut grid: Vec<(Design, Summary)> = Vec::new();
    for &(topo, lo, hi, step) in &[(Topo::Half, 18.0, 44.0, 2.0), (Topo::Full, 40.0, 150.0, 5.0)] {
        let mut l0 = lo;
        while l0 <= hi + 1e-9 {
            let mut fr = 22e3;
            while fr <= 52e3 + 1.0 {
                let d = Design { name: "grid", topo, l0_uh: l0, f_ref: fr };
                let s = run(&d, n_grid, seed, 114.0, false);
                grid.push((d, s));
                fr += 2e3;
            }
            l0 += step;
        }
    }
    let key = |s: &Summary| (s.pass_intended, if s.eff_p50.is_nan() { -1.0 } else { s.eff_p50 });
    grid.sort_by(|a, b| {
        let (ka, kb) = (key(&a.1), key(&b.1));
        kb.0.total_cmp(&ka.0).then(kb.1.total_cmp(&ka.1))
    });
    println!();
    println!("## Grid search at 114 V, n={} per point: top 6 per topology", n_grid);
    println!("{}", header);
    for topo in [Topo::Half, Topo::Full] {
        for (d, s) in grid.iter().filter(|g| g.0.topo == topo).take(6) {
            print_row(d, 114.0, s);
        }
    }
    let best_h = grid.iter().find(|g| g.0.topo == Topo::Half).map(|g| (g.0.l0_uh, g.0.f_ref)).unwrap();
    let best_f = grid.iter().find(|g| g.0.topo == Topo::Full).map(|g| (g.0.l0_uh, g.0.f_ref)).unwrap();

    // 2. Full-size runs: grid optima, the earlier hand design, and stock coils.
    let selected = Design { name: "FB_selected_70uH_0p54uF", topo: Topo::Full, l0_uh: 70.0,
        f_ref: selected_cap_reference_frequency() };
    let designs = [
        Design { name: "HB_grid_best", topo: Topo::Half, l0_uh: best_h.0, f_ref: best_h.1 },
        Design { name: "HB_33uH_hand_design", topo: Topo::Half, l0_uh: 33.0, f_ref: 35e3 },
        Design { name: "HB_stock_87uH", topo: Topo::Half, l0_uh: 87.0, f_ref: 35e3 },
        Design { name: "FB_grid_best", topo: Topo::Full, l0_uh: best_f.0, f_ref: best_f.1 },
        Design { name: "FB_stock_87uH", topo: Topo::Full, l0_uh: 87.0, f_ref: 35e3 },
        Design { name: "FB_stock_123uH", topo: Topo::Full, l0_uh: 123.0, f_ref: 35e3 },
        selected,
    ];
    for &v in &[114.0, 127.0] {
        println!();
        println!("## Detailed runs at {} V, n={}", v, n);
        println!("{}", header);
        for d in &designs {
            let s = run(d, n, seed, v, true);
            print_row(d, v, &s);
        }
    }
    println!();
    println!("## Selected 70 uH / 0.54 uF deterministic endpoint probes (all 5 assumed pan classes)");
    println!("# Per pan: L0 +/-10%, kL endpoints, Rpan endpoints, coil-R endpoints, C +/-10%; 160 combinations per line. Counts are neither population percentages nor product qualification.");
    println!("# Crest/RMS at modeled full-power operating points are conditional on the arbitrary 650 V screen; 60 kHz crest includes every corner whether screened reachable or not.");
    println!("line_V,corners,model_full_power,screen_unreachable,max_cap_crest_full_power_V,max_cap_line_rms_full_power_V,max_cap_crest_at_60k_V");
    for vrms in [108.0, 114.0, 127.0, 140.0] {
        print_selected_corners(&selected, vrms);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn closed_form_matches_resonance_power() {
        // At resonance, half bridge: P = Vpk^2/(pi^2 R).
        let (l, c, r): (f64, f64, f64) = (20e-6, 1e-6, 1.0);
        let f = 1.0 / (2.0 * PI * (l * c).sqrt());
        let (p, _, _, ph) = tank_at(Topo::Half, 120.0, l, c, r, f);
        let expect = 2.0 * 120.0f64.powi(2) / (PI * PI);
        assert!((p - expect).abs() / expect < 1e-9 && ph.abs() < 1e-6);
    }

    #[test]
    fn full_bridge_quadruples_power_at_same_impedance() {
        let (l, c, r, f) = (20e-6, 1e-6, 1.0, 40e3);
        let h = tank_at(Topo::Half, 120.0, l, c, r, f).0;
        let fb = tank_at(Topo::Full, 120.0, l, c, r, f).0;
        assert!((fb / h - 4.0).abs() < 1e-9);
    }

    #[test]
    fn current_limit_is_enforced_near_resonance() {
        // Low-R pan on a low-L coil: current at the phase-margin frequency
        // exceeds the limit; the floor must move up to satisfy it.
        let d = Design { name: "t", topo: Topo::Half, l0_uh: 22.0, f_ref: 44e3 };
        let c = 1.0 / ((2.0 * PI * 44e3f64).powi(2) * 22e-6 * 0.69);
        let s = Sample { pan: 4, l0: 22.0, kl: 0.85, r40: 0.012, q: 0.0015, c };
        let o = evaluate(&d, &s, 127.0);
        if o.pass {
            let l = s.l0 * 1e-6 * s.kl;
            let r = s.q * s.l0 + s.r40 * s.l0 * (o.f_op / 40e3).sqrt();
            assert!(tank_at(Topo::Half, 127.0, l, c, r, o.f_op).1 <= I_PK_MAX + 1e-6);
        }
    }

    #[test]
    fn deterministic_seed() {
        let (mut a, mut b) = (Rng(7), Rng(7));
        assert_eq!(a.next_u64(), b.next_u64());
    }

    #[test]
    fn pan_weights_sum_to_one() {
        let s: f64 = PANS.iter().map(|p| p.weight).sum();
        assert!((s - 1.0).abs() < 1e-12);
    }

    #[test]
    fn current_hardware_screen_rejects_old_half_bridge_and_accepts_cast_iron_case() {
        let d = Design { name: "t", topo: Topo::Half, l0_uh: 33.0, f_ref: 35e3 };
        let c = 1.0 / ((2.0 * PI * 35e3f64).powi(2) * 33e-6 * 0.69);
        let good = Sample { pan: 1, l0: 33.0, kl: 0.69, r40: 0.0334, q: 0.0039, c };
        // The historical half bridge needed the obsolete 85 A screen.
        assert!(!evaluate(&d, &good, 120.0).pass);
        let selected = Design { name: "selected", topo: Topo::Full, l0_uh: 70.0,
            f_ref: selected_cap_reference_frequency() };
        let cast_iron = Sample { pan: 0, l0: 70.0, kl: 0.80, r40: 0.052,
            q: 0.0039, c: 0.54e-6 };
        assert!(evaluate(&selected, &cast_iron, 120.0).pass);
        let d87 = Design { name: "t", topo: Topo::Half, l0_uh: 87.0, f_ref: 35e3 };
        let c87 = 1.0 / ((2.0 * PI * 35e3f64).powi(2) * 87e-6 * 0.69);
        let bad = Sample { pan: 1, l0: 87.0, kl: 0.69, r40: 0.0334, q: 0.0039, c: c87 };
        assert!(!evaluate(&d87, &bad, 114.0).pass);
    }

    #[test]
    fn full_bridge_cap_line_rms_is_half_crest_for_unfiltered_bus() {
        assert!((cap_line_rms(Topo::Full, 600.0, 120.0) - 300.0).abs() < 1e-12);
    }

    #[test]
    fn selected_reference_tuning_yields_selected_capacitance() {
        let f = selected_cap_reference_frequency();
        let c = 1.0 / ((2.0 * PI * f).powi(2) * 70e-6 * 0.69);
        assert!((c - 0.54e-6).abs() < 1e-15);
    }

    #[test]
    fn selected_full_bridge_uses_single_device_per_position() {
        // Pin the declared proxies independently: a shared accidental scale
        // change could preserve the topology ratio while corrupting loss.
        assert!((r_on_position(Topo::Full) - 0.035).abs() < 1e-12);
        assert!((r_on_position(Topo::Half) - 0.0175).abs() < 1e-12);
        assert!((r_on_position(Topo::Full) / r_on_position(Topo::Half) - 2.0).abs() < 1e-12);
    }

    #[test]
    fn half_bridge_cap_rms_excludes_bus_bias() {
        let vrms = 120.0;
        let bus_crest = vrms * 2.0_f64.sqrt();
        // A 100 V carrier crest with a rectified-sine line envelope gives
        // 100 / sqrt(2) / sqrt(2) = 50 V RMS, excluding the bus bias.
        let cap_crest = bus_crest / 2.0 + 100.0;
        assert!((cap_line_rms(Topo::Half, cap_crest, vrms) - 50.0).abs() < 1e-12);
    }

    #[test]
    fn selected_carbon_pan_at_high_line_cannot_claim_full_power_above_ct_trip() {
        // The former 85 A screen accepted this case at 61.64 A, above even
        // the broader CT static model's 60.01 A maximum. Rejecting it does
        // not qualify the remaining 45 A-screen cases against the shunt.
        let design = Design { name: "selected", topo: Topo::Full, l0_uh: 70.0,
            f_ref: selected_cap_reference_frequency() };
        let pan = Sample { pan: 1, l0: 70.0, kl: 0.80, r40: 0.029,
            q: 0.0015, c: 0.54e-6 };
        assert!(!evaluate(&design, &pan, 140.0).pass);
    }
}

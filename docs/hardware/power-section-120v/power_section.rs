// 120 V-class unfiltered-bus half-bridge power-section screen.
//
// First-harmonic, line-cycle-averaged model (same method family as
// zapote/inverter/evidence/plant_screen.rs). Every number it prints is a
// design screen from stated inputs, not a measurement or a rating.
//
// Build and run from the repo root:
//   rustc --edition=2021 -O docs/hardware/power-section-120v/power_section.rs -o /tmp/ps120
//   /tmp/ps120 > docs/hardware/power-section-120v/power-section-output.txt
// Tests:
//   rustc --edition=2021 --test docs/hardware/power-section-120v/power_section.rs -o /tmp/ps120t && /tmp/ps120t

use std::f64::consts::PI;

/// Tank as seen from the half-bridge switch node (split resonant capacitors
/// are AC-parallel, so `c` is their sum).
#[derive(Clone, Copy)]
struct Tank {
    name: &'static str,
    l: f64,      // loaded inductance, H
    r_coil: f64, // winding AC resistance, ohm
    r_pan: f64,  // reflected pan resistance, ohm
    c: f64,      // total resonant capacitance, F
}

impl Tank {
    fn r(&self) -> f64 {
        self.r_coil + self.r_pan
    }
    fn f_res(&self) -> f64 {
        1.0 / (2.0 * PI * (self.l * self.c).sqrt())
    }
    /// Impedance magnitude and phase (rad, positive = inductive) at f.
    fn z(&self, f: f64) -> (f64, f64) {
        let w = 2.0 * PI * f;
        let x = w * self.l - 1.0 / (w * self.c);
        ((self.r() * self.r() + x * x).sqrt(), x.atan2(self.r()))
    }
}

/// Reverse-conducting IGBT, piecewise-linear conduction fits and a
/// hard-switched turn-off energy scaled from the datasheet test point.
struct Switch {
    v0: f64,
    r: f64,
    vd0: f64,
    rd: f64,
    eoff_ref: f64, // J at (v_ref, i_ref)
    v_ref: f64,
    i_ref: f64,
}

// IHW40N65R5 (Infineon Rev.2.3 2015-12-22). VCEsat 1.60 V typ at 40 A,
// Tvj=175 degC; VF 2.00 V typ at 175 degC; Eoff 0.61 mJ typ at 400 V/40 A,
// 175 degC, RG=10 ohm. The 0.8 V / 1.0 V knees are ASSUMED fits to the
// typical output curves, not datasheet limits.
const IHW40N65R5: Switch = Switch {
    v0: 0.8,
    r: (1.60 - 0.8) / 40.0,
    vd0: 1.0,
    rd: (2.00 - 1.0) / 40.0,
    eoff_ref: 0.61e-3,
    v_ref: 400.0,
    i_ref: 40.0,
};

struct Point {
    p_tank: f64,     // W, line-cycle average
    p_pan: f64,      // W
    i_tank_avg: f64, // A rms, line-cycle average (sqrt of mean square)
    i_tank_pk: f64,  // A, peak at line crest
    i_off_pk: f64,   // A, turn-off current at line crest
    phase_deg: f64,
    igbt_cond_w: f64, // per switch
    diode_cond_w: f64,
    igbt_off_w: f64,
    vc_pk: f64,        // V, one split capacitor absolute peak
    i_c_each_rms: f64, // A rms, one split capacitor, line average
    i_bus_hf_rms: f64, // A rms HF current the bus film cap must carry, line average
}

/// Evaluate a tank at fixed f on a rectified bus v(theta) = vpk*|sin theta|.
fn evaluate(t: &Tank, s: &Switch, vrms: f64, f: f64) -> Point {
    let vpk = vrms * 2f64.sqrt();
    let (zm, ph) = t.z(f);
    let n = 2000;
    let (mut p, mut i2, mut ic, mut id, mut ioff, mut ibus2) = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0);
    for k in 0..n {
        let th = PI * (k as f64 + 0.5) / n as f64;
        let vbus = vpk * th.sin();
        let v1 = 2f64.sqrt() * vbus / PI; // fundamental rms of 0..vbus square wave
        let irms = v1 / zm;
        let ipk = irms * 2f64.sqrt();
        p += irms * irms * t.r();
        i2 += irms * irms;
        // One switch conducts for half a period. Current i = ipk*sin(x - ph),
        // x in [0, pi): diode for x < ph, IGBT for ph..pi.
        let m = 400;
        let (mut ca, mut cr, mut da, mut dr) = (0.0, 0.0, 0.0, 0.0);
        for j in 0..m {
            let x = PI * (j as f64 + 0.5) / m as f64;
            let i = ipk * (x - ph).sin();
            if i >= 0.0 {
                ca += i;
                cr += i * i;
            } else {
                da += -i;
                dr += i * i;
            }
        }
        // Averages over the full switching period (switch idle other half).
        let norm = 2.0 * m as f64;
        let cond = s.v0 * ca / norm + s.r * cr / norm;
        let dcond = s.vd0 * da / norm + s.rd * dr / norm;
        let i_turnoff = ipk * ph.sin().max(0.0);
        let eoff = s.eoff_ref * (vbus / s.v_ref) * (i_turnoff / s.i_ref);
        ic += cond + eoff * f;
        id += dcond;
        ioff = f64::max(ioff, i_turnoff);
        // Rail current is the tank current while the high side conducts.
        // With split resonant caps half returns via each rail cap; the bus
        // film cap carries the HF part of the bridge-leg current, bounded
        // here by the half-bridge result I^2/2 - mean^2.
        let mean = ipk * ph.cos() / PI;
        ibus2 += (ipk * ipk / 4.0 - mean * mean).max(0.0);
    }
    let nf = n as f64;
    let irms_avg = (i2 / nf).sqrt();
    let w = 2.0 * PI * f;
    let crest_irms = vpk * 2f64.sqrt() / PI / zm;
    let igbt_total = ic / nf;
    let eoff_w = {
        // Separate turn-off share for reporting.
        let mut e = 0.0;
        for k in 0..n {
            let th = PI * (k as f64 + 0.5) / nf;
            let vbus = vpk * th.sin();
            let ipk = 2f64.sqrt() * (2f64.sqrt() * vbus / PI) / zm;
            e += s.eoff_ref * (vbus / s.v_ref) * (ipk * ph.sin().max(0.0) / s.i_ref) * f;
        }
        e / nf
    };
    Point {
        p_tank: p / nf,
        p_pan: p / nf * t.r_pan / t.r(),
        i_tank_avg: irms_avg,
        i_tank_pk: crest_irms * 2f64.sqrt(),
        i_off_pk: ioff,
        phase_deg: ph.to_degrees(),
        igbt_cond_w: igbt_total - eoff_w,
        diode_cond_w: id / nf,
        igbt_off_w: eoff_w,
        vc_pk: vpk / 2.0 + crest_irms * 2f64.sqrt() / 2.0 / (w * t.c / 2.0),
        i_c_each_rms: irms_avg / 2.0,
        i_bus_hf_rms: (ibus2 / nf).sqrt(),
    }
}

/// Lowest frequency above resonance (inductive, ZVS side) that delivers
/// p_target, by bisection. None if unreachable at `f_min_phase`.
fn freq_for_power(t: &Tank, s: &Switch, vrms: f64, p_target: f64, min_phase_deg: f64) -> Option<f64> {
    // Frequency where phase equals min_phase: tan(ph) = X/R.
    let mut lo = t.f_res();
    let mut hi = t.f_res() * 3.0;
    let x_needed = t.r() * min_phase_deg.to_radians().tan();
    for _ in 0..100 {
        let mid = 0.5 * (lo + hi);
        let w = 2.0 * PI * mid;
        if w * t.l - 1.0 / (w * t.c) < x_needed { lo = mid } else { hi = mid }
    }
    let f_floor = hi;
    if evaluate(t, s, vrms, f_floor).p_tank < p_target {
        return None;
    }
    let (mut lo, mut hi) = (f_floor, t.f_res() * 6.0);
    for _ in 0..100 {
        let mid = 0.5 * (lo + hi);
        if evaluate(t, s, vrms, mid).p_tank > p_target { lo = mid } else { hi = mid }
    }
    Some(0.5 * (lo + hi))
}

// Bridge rectifier: two elements conduct; Vf0/r fit is an ASSUMED linear fit
// to a 25 A-class glass-passivated bridge (1.0 V at 12.5 A per element typ).
// Four elements, each conducting alternate half cycles: per element
// avg = I_avg/2 and rms^2 = I_rms^2/2, so total = 2*vf0*I_avg + 2*rf*I_rms^2.
fn bridge_loss(i_line_rms: f64) -> f64 {
    let (vf0, rf) = (0.75, 0.02);
    let i_avg = i_line_rms * 2.0 * 2f64.sqrt() / PI; // sinusoidal line current
    2.0 * vf0 * i_avg + 2.0 * rf * i_line_rms * i_line_rms
}

// ---------------------------------------------------------------------------
// Loss-budget comparison for the low-loss refactor (LOSS-REFACTOR.md).
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
enum Dev {
    /// IGBT with the piecewise fits above (hard turn-off Eoff scaling).
    Igbt,
    /// MOSFET used synchronously: tank current flows in the channel whenever
    /// the switch is on; the body diode conducts only during dead time.
    /// Turn-off is taken as lossless (ZVS with snubber) — an assumption that
    /// bench waveforms must confirm.
    Mosfet { r_hot: f64, vsd: f64, n_par: f64 },
}

#[derive(Clone, Copy)]
enum Topo {
    Half,
    Full,
}

#[derive(Clone, Copy)]
enum Rect {
    Diode,
    /// Low-side diodes replaced by MOSFETs (TEA2206-style), r_hot each.
    LowSideSync(f64),
    /// All four replaced (needs high-side drive).
    FullSync(f64),
}

struct Config {
    name: &'static str,
    dev: Dev,
    topo: Topo,
    rect: Rect,
    coil_fraction: f64, // R_coil / R_total at the reference vessel
}

// Dead time from the gate board's 39 kohm setting (~390 ns, unverified).
const DEAD_TIME: f64 = 390e-9;
// Fixed small losses, W: EMI choke copper (~2x5 mohm at 15 A), resonant and
// bus capacitor ESR (~2.5 W), PCB/wiring (~3 W), SELV + gate supplies (~2 W).
// These are ALLOWANCES pending part selection, not calculations.
const FIXED_LOSS: f64 = 2.0 * 0.005 * 15.0 * 15.0 + 2.5 + 3.0 + 2.0;

fn rect_loss(r: Rect, i_line_rms: f64) -> f64 {
    let (vf0, rf) = (0.75, 0.02);
    let i_avg = i_line_rms * 2.0 * 2f64.sqrt() / PI;
    let diode_pair = vf0 * i_avg + rf * i_line_rms * i_line_rms; // two of four diodes
    let i2 = i_line_rms * i_line_rms;
    match r {
        Rect::Diode => 2.0 * diode_pair,
        Rect::LowSideSync(rm) => diode_pair + i2 * rm,
        Rect::FullSync(rm) => 2.0 * i2 * rm,
    }
}

/// Returns (tank power, total switch loss) at frequency f for a tank whose
/// R/L are already scaled for the topology.
fn switch_losses(t: &Tank, dev: Dev, topo: Topo, vrms: f64, f: f64) -> (f64, f64) {
    let vpk = vrms * 2f64.sqrt();
    let (zm, ph) = t.z(f);
    let n = 1000;
    let (mut p, mut loss) = (0.0, 0.0);
    let gain = match topo { Topo::Half => 1.0, Topo::Full => 2.0 };
    for k in 0..n {
        let th = PI * (k as f64 + 0.5) / n as f64;
        let vbus = vpk * th.sin();
        let irms = gain * 2f64.sqrt() * vbus / PI / zm;
        let ipk = irms * 2f64.sqrt();
        p += irms * irms * t.r();
        let i_off = ipk * ph.sin().max(0.0);
        // Devices in the current path at any instant: 1 (half) or 2 (full);
        // total devices: 2 or 4. Each device carries the tank current for
        // half of each period.
        let (in_path, total) = match topo { Topo::Half => (1.0, 2.0), Topo::Full => (2.0, 4.0) };
        let _ = total;
        match dev {
            Dev::Igbt => {
                // Reuse the IGBT per-switch model (per half-period waveform).
                let s = IHW40N65R5;
                let m = 200;
                let (mut ca, mut cr, mut da, mut dr) = (0.0, 0.0, 0.0, 0.0);
                for j in 0..m {
                    let x = PI * (j as f64 + 0.5) / m as f64;
                    let i = ipk * (x - ph).sin();
                    if i >= 0.0 { ca += i; cr += i * i } else { da -= i; dr += i * i }
                }
                let norm = 2.0 * m as f64;
                let per_dev = s.v0 * ca / norm + s.r * cr / norm + s.vd0 * da / norm + s.rd * dr / norm
                    + s.eoff_ref * (vbus / s.v_ref) * (i_off / s.i_ref) * f;
                // Every device of the leg set sees this waveform; in a full
                // bridge each device sees the same (halved) current pattern.
                loss += per_dev * 2.0 * in_path;
            }
            Dev::Mosfet { r_hot, vsd, n_par } => {
                // Channel conduction: tank current always flows through
                // `in_path` switch positions; each position is n_par parallel.
                let cond = irms * irms * in_path * r_hot / n_par;
                // Dead-time body-diode conduction: two transitions per period,
                // each carrying ~i_off through the incoming device's diode,
                // for every leg in the path.
                let dt = 2.0 * vsd * i_off * DEAD_TIME * f * in_path;
                loss += cond + dt;
            }
        }
    }
    (p / n as f64, loss / n as f64)
}

fn solve_config(cfg: &Config, base: &Tank, vrms: f64, i_limit: f64, pf: f64) -> String {
    // Keep the pan-reflected resistance and inductance (turns-scaled for the
    // topology) and set the coil resistance from the configured fraction.
    let scale = match cfg.topo { Topo::Half => 1.0, Topo::Full => 4.0 };
    let r_pan = base.r_pan * scale;
    let r_coil = r_pan * cfg.coil_fraction / (1.0 - cfg.coil_fraction);
    let t = Tank { name: cfg.name, l: base.l * scale, r_coil, r_pan, c: base.c / scale };
    let p_in = f64::min(1800.0, i_limit * vrms * pf);
    let i_line = p_in / (vrms * pf);
    let front = rect_loss(cfg.rect, i_line) + FIXED_LOSS;
    // Bus power = tank power + switch loss = p_in - front. Iterate on f.
    let mut sw = 0.0;
    let mut f = t.f_res() * 1.05;
    for _ in 0..6 {
        let p_tank_target = p_in - front - sw;
        let (mut lo, mut hi) = (t.f_res() * 1.03, t.f_res() * 4.0);
        for _ in 0..80 {
            let mid = 0.5 * (lo + hi);
            if switch_losses(&t, cfg.dev, cfg.topo, vrms, mid).0 > p_tank_target { lo = mid } else { hi = mid }
        }
        f = 0.5 * (lo + hi);
        sw = switch_losses(&t, cfg.dev, cfg.topo, vrms, f).1;
    }
    let (p_tank, _) = switch_losses(&t, cfg.dev, cfg.topo, vrms, f);
    let coil = p_tank * cfg.coil_fraction;
    let pan = p_tank - coil;
    let total = p_in - pan;
    let i_avg = (p_tank / t.r()).sqrt();
    format!(
        "{},{:.0},{:.1},{:.1},{:.1},{:.1},{:.1},{:.0},{:.0},{:.1},{:.1}",
        cfg.name, p_in, f / 1e3, rect_loss(cfg.rect, i_line), sw, coil, FIXED_LOSS, total, pan,
        100.0 * pan / p_in, i_avg
    )
}

fn loss_refactor(base: &Tank) {
    // Datasheet-derived hot resistances:
    //  IPW60R018CFD7: 18 mohm max @25C, 29 mohm typ @150C (x1.93) -> 35 mohm
    //    conservative (max x typ ratio); VSD 1.0 V typ @58 A, 25C.
    //  C3M0015065K: 21 mohm max @25C, 20 typ @175C (x1.33) -> 28 mohm
    //    conservative; VSD 4.7 V @ -4 V gate (use 4.7).
    let cfd7 = Dev::Mosfet { r_hot: 0.035, vsd: 1.0, n_par: 1.0 };
    let cfd7x2 = Dev::Mosfet { r_hot: 0.035, vsd: 1.0, n_par: 2.0 };
    let sic = Dev::Mosfet { r_hot: 0.028, vsd: 4.7, n_par: 1.0 };
    let rect_m = 0.035; // CFD7-class rectifier MOSFET, hot
    let k0 = 0.34 / 3.25; // kit chart-derived coil fraction (10.5%)
    let cfgs = [
        Config { name: "A0_baseline_IGBT_HB_diode_bridge", dev: Dev::Igbt, topo: Topo::Half, rect: Rect::Diode, coil_fraction: k0 },
        Config { name: "A1_CFD7_HB", dev: cfd7, topo: Topo::Half, rect: Rect::Diode, coil_fraction: k0 },
        Config { name: "A2_SiC_HB", dev: sic, topo: Topo::Half, rect: Rect::Diode, coil_fraction: k0 },
        Config { name: "A3_2xCFD7_HB", dev: cfd7x2, topo: Topo::Half, rect: Rect::Diode, coil_fraction: k0 },
        Config { name: "A4_2xCFD7_HB_lowside_sync_rect", dev: cfd7x2, topo: Topo::Half, rect: Rect::LowSideSync(rect_m), coil_fraction: k0 },
        Config { name: "A5_A4_plus_coil_7pct", dev: cfd7x2, topo: Topo::Half, rect: Rect::LowSideSync(rect_m), coil_fraction: 0.07 },
        Config { name: "A6_A4_plus_coil_5pct", dev: cfd7x2, topo: Topo::Half, rect: Rect::LowSideSync(rect_m), coil_fraction: 0.05 },
        Config { name: "A7_A6_plus_full_sync_rect", dev: cfd7x2, topo: Topo::Half, rect: Rect::FullSync(rect_m), coil_fraction: 0.05 },
        Config { name: "B1_CFD7_full_bridge_coil_5pct", dev: cfd7, topo: Topo::Full, rect: Rect::LowSideSync(rect_m), coil_fraction: 0.05 },
        Config { name: "B2_IGBT_full_bridge_coil_10pct", dev: Dev::Igbt, topo: Topo::Full, rect: Rect::Diode, coil_fraction: k0 },
        Config { name: "C1_coil_5pct_only_IGBT", dev: Dev::Igbt, topo: Topo::Half, rect: Rect::Diode, coil_fraction: 0.05 },
    ];
    println!();
    println!("## Loss refactor comparison at 120 V, 15 A input limit, PF 0.95");
    println!("# fixed allowance {:.1} W (EMI, cap ESR, wiring, aux); dead time {:.0} ns", FIXED_LOSS, DEAD_TIME * 1e9);
    println!("config,p_in_W,f_kHz,rectifier_W,switches_W,coil_W,fixed_W,total_loss_W,pan_W,eff_pct,tank_I_avg_A");
    for c in &cfgs {
        println!("{}", solve_config(c, base, 120.0, 15.0, 0.95));
    }
}

fn main() {
    // Scale the Infineon kit reference coil (chart reads at ~40 kHz: loaded
    // 60 uH / 0.34 ohm coil / 2.91 ohm pan) by turns^2 factor k so that
    // R_total ~= 1.25 ohm. The turns-scaling keeps every L and R ratio.
    let k = 1.25 / 3.25;
    let c = 0.90e-6; // 2 sides x 3 x 0.15 uF (CDE 942C12P15K-F) split resonant capacitors
    let kit = [
        ("kit_reference_vessel", 60.0, 0.34, 2.91),
        ("cast_iron_transfer", 70.99, 0.34, 3.87),
        ("steel_transfer", 64.70, 0.34, 3.02),
        ("silargan_transfer", 54.63, 0.34, 2.14),
        ("half_coupling", 73.5, 0.34, 1.455),
        ("reference_L_minus_10pct", 54.0, 0.34, 2.91),
        ("no_pan", 87.0, 0.34, 0.0),
    ];
    let tanks: Vec<Tank> = kit
        .iter()
        .map(|&(name, l_uh, rc, rp)| Tank { name, l: l_uh * 1e-6 * k, r_coil: rc * k, r_pan: rp * k, c })
        .collect();
    let s = IHW40N65R5;
    let eta_front = 0.95; // input -> tank, ASSUMED until losses below are summed
    let pf = 0.95; // conservative end of published 0.95-0.995

    println!("# 120 V unfiltered-bus half-bridge power-section screen");
    println!("# coil scale k={:.3}; C_total={:.2} uF; switch IHW40N65R5 fits", k, c * 1e6);
    println!();
    println!("## Design coil (reference vessel) at fixed input-current limit 15.0 A");
    let t = tanks[0];
    println!("f_res loaded = {:.1} kHz, L = {:.1} uH, R_total = {:.3} ohm", t.f_res() / 1e3, t.l * 1e6, t.r());
    println!("vrms,p_in_W,p_tank_W,f_kHz,phase_deg,i_tank_avg_A,i_tank_pk_A,i_turnoff_pk_A,igbt_cond_W,igbt_off_W,diode_W,per_switch_W,bridge_W,vc_pk_V,i_c_each_A,i_bus_hf_A,line_A");
    for &v in &[108.0, 114.0, 120.0, 127.0, 140.0] {
        let p_in = f64::min(1800.0, 15.0 * v * pf);
        let p_tank = p_in * eta_front;
        match freq_for_power(&t, &s, v, p_tank, 20.0) {
            Some(f) => {
                let pt = evaluate(&t, &s, v, f);
                let line = p_in / (v * pf);
                let sw = pt.igbt_cond_w + pt.igbt_off_w + pt.diode_cond_w;
                println!(
                    "{v},{p_in:.0},{:.0},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.1},{:.0},{:.1},{:.1},{:.2}",
                    pt.p_tank, f / 1e3, pt.phase_deg, pt.i_tank_avg, pt.i_tank_pk, pt.i_off_pk,
                    pt.igbt_cond_w, pt.igbt_off_w, pt.diode_cond_w, sw, bridge_loss(line), pt.vc_pk,
                    pt.i_c_each_rms, pt.i_bus_hf_rms, line
                );
            }
            None => println!("{v},{p_in:.0},UNREACHABLE at >=20 deg phase"),
        }
    }

    println!();
    println!("## Pan/no-pan cases at the 120 V full-power frequency of the design coil");
    let f_full = freq_for_power(&t, &s, 120.0, 15.0 * 120.0 * pf * eta_front, 20.0).unwrap();
    println!("f = {:.1} kHz", f_full / 1e3);
    println!("case,L_uH,R_total_ohm,f_res_kHz,phase_deg,p_tank_W,p_pan_W,i_tank_avg_A,i_tank_pk_A,i_turnoff_pk_A,per_switch_W,vc_pk_V");
    for t in &tanks {
        let pt = evaluate(t, &s, 120.0, f_full);
        println!(
            "{},{:.1},{:.3},{:.1},{:.1},{:.0},{:.0},{:.1},{:.1},{:.1},{:.1},{:.0}",
            t.name, t.l * 1e6, t.r(), t.f_res() / 1e3, pt.phase_deg, pt.p_tank, pt.p_pan,
            pt.i_tank_avg, pt.i_tank_pk, pt.i_off_pk,
            pt.igbt_cond_w + pt.igbt_off_w + pt.diode_cond_w, pt.vc_pk
        );
    }
    println!("# 140 V high line, same frequency (controller must raise f; this bounds the unregulated case)");
    for t in &tanks {
        let pt = evaluate(t, &s, 140.0, f_full);
        println!("{}@140V,p_tank={:.0}W,i_pk={:.1}A,vc_pk={:.0}V", t.name, pt.p_tank, pt.i_tank_pk, pt.vc_pk);
    }

    println!();
    println!("## Continuous power range vs frequency, design coil, 120 V");
    println!("f_kHz,phase_deg,p_tank_W,i_turnoff_pk_A,per_switch_W");
    for &fk in &[36.0, 38.0, 40.0, 45.0, 50.0, 60.0] {
        let pt = evaluate(&t, &s, 120.0, fk * 1e3);
        println!("{fk},{:.1},{:.0},{:.1},{:.1}", pt.phase_deg, pt.p_tank,
                 pt.i_off_pk, pt.igbt_cond_w + pt.igbt_off_w + pt.diode_cond_w);
    }

    println!();
    println!("## Passive sizing checks");
    let c_bus: f64 = 5e-6;
    let vpk_hi: f64 = 140.0 * 2f64.sqrt();
    println!("bus film cap energy at 140 V line peak: {:.3} J", 0.5 * c_bus * vpk_hi * vpk_hi);
    let pt = evaluate(&t, &s, 120.0, f_full);
    let dv = pt.i_bus_hf_rms / (2.0 * PI * f_full * c_bus);
    println!("bus HF ripple (rms current {:.1} A) on 5 uF: {:.1} V rms", pt.i_bus_hf_rms, dv);
    let cx = 2.0e-6;
    let r_bleed = 2.0 * 120e3;
    let tau = r_bleed * cx;
    println!("X-cap bleed: 2 x 120k across 2.0 uF -> tau {:.2} s; plug voltage after 1 s from {:.0} V pk: {:.1} V (limit 34 V)",
             tau, vpk_hi, vpk_hi * (-1.0f64 / tau).exp());
    println!("X-cap bleed dissipation at 140 V: {:.0} mW", 140.0 * 140.0 / r_bleed * 1e3);
    let fuse_i = 15.0 / 0.75;
    println!("fuse: 15 A continuous / 0.75 derating -> >= {:.1} A rating", fuse_i);
    let ct_v = pt.i_tank_pk / 100.0 * 1.0;
    let vt = ct_v * 0.5 / f_full * 1e6;
    println!("CT 1:100, 1.0 ohm burden: {:.2} V pk at {:.1} A pk; volt-time per half cycle {:.1} V-us (limit 638)",
             ct_v, pt.i_tank_pk, vt);
    let qg = 193e-9;
    let fmax = 60e3;
    println!("gate supply: 2 x Qg 193 nC x 15 V x {:.0} kHz = {:.2} W", fmax / 1e3, 2.0 * qg * 15.0 * fmax);

    loss_refactor(&t);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn resistive_tank() -> Tank {
        Tank { name: "t", l: 20e-6, r_coil: 0.0, r_pan: 1.0, c: 1e-6 }
    }

    #[test]
    fn resonance_matches_closed_form_line_average() {
        // At resonance P = Vpk^2 / (pi^2 R) for the unfiltered bus.
        let t = resistive_tank();
        let p = evaluate(&t, &IHW40N65R5, 120.0, t.f_res()).p_tank;
        let expect = (120.0f64 * 2f64.sqrt()).powi(2) / (PI * PI * 1.0);
        assert!((p - expect).abs() / expect < 1e-3, "{p} vs {expect}");
    }

    #[test]
    fn above_resonance_is_inductive_and_lower_power() {
        let t = resistive_tank();
        let a = evaluate(&t, &IHW40N65R5, 120.0, t.f_res());
        let b = evaluate(&t, &IHW40N65R5, 120.0, t.f_res() * 1.2);
        assert!(b.phase_deg > 0.0 && b.p_tank < a.p_tank);
    }

    #[test]
    fn frequency_search_hits_target() {
        let t = resistive_tank();
        let f = freq_for_power(&t, &IHW40N65R5, 120.0, 1000.0, 20.0).unwrap();
        let p = evaluate(&t, &IHW40N65R5, 120.0, f).p_tank;
        assert!((p - 1000.0).abs() < 1.0);
    }

    #[test]
    fn unreachable_power_is_reported() {
        let t = resistive_tank();
        assert!(freq_for_power(&t, &IHW40N65R5, 120.0, 1e6, 20.0).is_none());
    }
}

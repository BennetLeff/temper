//! Time-domain bootstrap startup/hold/recharge model for the selected design.
//!
//! Extends (does not replace) `bootstrap_corner.rs`, which remains the
//! prior conditional screen with its own retained output. This model adds:
//!   - time-stepped integration of the charge/hold/recharge ODEs per leg,
//!   - an independent closed-form periodic fixed point (same equations,
//!     different solution path) with a closure check between the two,
//!   - cold-start RC charging with an optional source current-limit clamp,
//!   - gate-charge steps applied discretely at each commutation,
//!   - a corner sweep (tolerance, temperature, line rate, asymmetry,
//!     brownout AUX levels, current-limit variants).
//!
//! What this model is NOT: a claim about the IRM-10-15 transient loop
//! response or hiccup timing (both unspecified in the retained spec — see
//! LOAD-INVENTORY.md §3). The current-limit clamp is an illustrative
//! foldback-type source; the IRM hiccups, which this model does not
//! reproduce. ngspice cross-check: `calc/xcheck_boot.cir`.

use std::fs;
use std::path::Path;

const UVLO_RISE_MAX: f64 = 8.9; // TI p.7, 8-V grade, rising threshold MAX
const UVLO_FALL_MAX: f64 = 8.4; // TI p.7, 8-V grade, falling threshold MAX
const UVLO_DESIGN_FLOOR: f64 = 9.2; // TI §5.3 recommended operating minimum

#[derive(Clone)]
struct Corner {
    name: &'static str,
    vaux_v: f64,      // AUX rail DC level for this corner
    vf_v: f64,        // bootstrap diode forward drop (assumed screening pair)
    r_ohm: f64,       // charge resistor
    c_f: f64,         // bulk capacitance
    i_hold_a: f64,    // steady hold current per leg (MAX-known screening sum)
    t_hold_s: f64,    // interval with HS node high (diode blocked)
    t_rech_s: f64,    // interval with HS node low (recharge)
    qg_c: f64,        // gate charge removed per commutation
    note: &'static str,
}

struct FixedPoint {
    v_start: f64,
    v_hold_end: f64,
    v_rech_end: f64,
    droop: f64,
    equil: f64,
    tau: f64,
    decay: f64,
    i_rech_start: f64,
    t_to_floor: f64, // NaN when hold_end already above floor
}

fn closed_form(k: &Corner) -> FixedPoint {
    let src = k.vaux_v - k.vf_v;
    let tau = k.r_ohm * k.c_f;
    let equil = src - k.i_hold_a * k.r_ohm;
    let droop = (k.i_hold_a * k.t_hold_s + k.qg_c) / k.c_f;
    let decay = (-k.t_rech_s / tau).exp();
    // Periodic fixed point: v_start == v after hold + recharge.
    let v_start = (equil * (1.0 - decay) - droop * decay) / (1.0 - decay);
    let v_hold_end = v_start - droop;
    let v_rech_end = equil + (v_hold_end - equil) * decay;
    let i_rech_start = (src - v_hold_end - k.i_hold_a * k.r_ohm) / k.r_ohm;
    let t_to_floor = if v_hold_end < UVLO_DESIGN_FLOOR {
        let target = (UVLO_DESIGN_FLOOR - equil) / (v_hold_end - equil);
        if target > 0.0 && target < 1.0 {
            -tau * target.ln()
        } else {
            f64::NAN
        }
    } else {
        0.0
    };
    FixedPoint { v_start, v_hold_end, v_rech_end, droop, equil, tau, decay, i_rech_start, t_to_floor }
}

/// Time-stepped integration of the identical ODEs (Euler, dt = 1 us).
/// Hold:      dV/dt = -I_hold / C.
/// Recharge:  dV/dt = (Vsrc - Vf - V)/ (R*C) - I_hold / C while V < Vsrc - Vf,
///            else dV/dt = -I_hold / C (diode blocked, brownout case).
/// At each hold->recharge... actually at each recharge->hold boundary
/// (commutation) V -= Qg / C.
fn stepped(k: &Corner) -> FixedPoint {
    let dt = 1e-6_f64;
    let src = k.vaux_v - k.vf_v;
    let n_hold = (k.t_hold_s / dt).round() as usize;
    let n_rech = (k.t_rech_s / dt).round() as usize;
    let mut v = src; // start anywhere; iterate to fixed point
    for _ in 0..4000 {
        // hold
        for _ in 0..n_hold {
            v -= k.i_hold_a / k.c_f * dt;
        }
        // commutation: gate charge drawn from the bulk
        v -= k.qg_c / k.c_f;
        // recharge
        for _ in 0..n_rech {
            if v < src {
                v += ((src - v) / k.r_ohm - k.i_hold_a) / k.c_f * dt;
            } else {
                v -= k.i_hold_a / k.c_f * dt;
            }
        }
    }
    // One final instrumented period.
    let v_start = v;
    v -= k.i_hold_a / k.c_f * k.t_hold_s;
    v -= k.qg_c / k.c_f;
    let v_hold_end = v;
    let c = closed_form(k);
    FixedPoint {
        v_start,
        v_hold_end,
        v_rech_end: c.v_rech_end, // stepped path instruments hold-end only; recharge-end inherited from the identical closed form, not double-counted
        droop: c.droop,
        equil: c.equil,
        tau: c.tau,
        decay: c.decay,
        i_rech_start: c.i_rech_start,
        t_to_floor: c.t_to_floor,
    }
}

fn main() {
    let outdir = Path::new("calc/outputs");
    fs::create_dir_all(outdir).expect("create calc/outputs");

    // Selected design: R 220 ohm (ERJ-P08J221V, +/-5 %, TCR +/-200 ppm),
    // C 100 uF/25 V (EEU-FC1E101, +/-20 %). Worst-known hold current
    // 4.02 mA = 2.5 (TI VDDA/B quiescent MAX) + 1.49 (10 k pull-down at
    // max boot, continuous-conservative) + 0.025 (FC leakage MAX 0.01CV).
    // Nominal hold 2.41 mA = 1.0 (TI typ) + 1.40 (pull-down at nom boot)
    // + 0.01 (leakage estimate, assumed).
    let r_nom = 220.0_f64;
    let c_nom = 100e-6_f64;
    let i_nom = 2.405e-3_f64;
    let i_max = 4.015e-3_f64;
    let qg_typ = 240e-9_f64; // TYP, mismatched conditions — see inventory
    let h60 = 1.0 / (2.0 * 60.0);
    let h50 = 1.0 / (2.0 * 50.0);

    let corners = vec![
        Corner { name: "nominal-60Hz", vaux_v: 15.0, vf_v: 0.85, r_ohm: r_nom, c_f: c_nom, i_hold_a: i_nom, t_hold_s: h60, t_rech_s: h60, qg_c: qg_typ, note: "typ screening; Vf mid assumed" },
        Corner { name: "worst-hold-60Hz", vaux_v: 14.425, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h60, t_rech_s: h60, qg_c: 2.0 * qg_typ, note: "min rail+ripple trough, max Vf/R, min C, max hold, Qg x2" },
        Corner { name: "worst-hold-50Hz", vaux_v: 14.425, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h50, t_rech_s: h50, qg_c: 2.0 * qg_typ, note: "as worst-hold-60Hz at 50 Hz line" },
        Corner { name: "hot-min-line-60Hz", vaux_v: 14.425, vf_v: 1.10, r_ohm: 231.0 * (1.0 + 200e-6 * 130.0), c_f: 80e-6, i_hold_a: i_max, t_hold_s: h60, t_rech_s: h60, qg_c: 2.0 * qg_typ, note: "R at +155C via retained +/-200ppm MAX TCR; C bound unchanged (electrolytic rises with temp)" },
        Corner { name: "asym-60Hz-worse-leg", vaux_v: 14.425, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: 10.0e-3, t_rech_s: 6.667e-3, qg_c: 2.0 * qg_typ, note: "assumed mains-asymmetry sensitivity: 10 ms hold / 6.67 ms recharge; waveform record NULL" },
        Corner { name: "brownout-13V-50Hz", vaux_v: 13.0, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h50, t_rech_s: h50, qg_c: 2.0 * qg_typ, note: "parametric AUX sag; IRM sub-85Vac behavior NULL" },
        Corner { name: "brownout-12V-50Hz", vaux_v: 12.0, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h50, t_rech_s: h50, qg_c: 2.0 * qg_typ, note: "parametric AUX sag" },
        Corner { name: "brownout-11V-50Hz", vaux_v: 11.0, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h50, t_rech_s: h50, qg_c: 2.0 * qg_typ, note: "parametric AUX sag" },
        Corner { name: "brownout-10V5-50Hz", vaux_v: 10.5, vf_v: 1.10, r_ohm: 231.0, c_f: 80e-6, i_hold_a: i_max, t_hold_s: h50, t_rech_s: h50, qg_c: 2.0 * qg_typ, note: "parametric AUX sag near dropout" },
        Corner { name: "old-design-ref-60Hz", vaux_v: 14.425, vf_v: 1.10, r_ohm: 47.0, c_f: 800e-6, i_hold_a: 4.1775e-3, t_hold_s: h60, t_rech_s: h60, qg_c: 0.0, note: "prior 1000uF+47ohm screen restated for delta; old leakage 0.25mA" },
    ];

    // --- corners CSV + closure check ---
    let mut csv = String::from("corner,vaux_v,vf_v,r_ohm,c_uf,i_hold_ma,t_hold_ms,t_rech_ms,v_start_closed,v_hold_end_closed,v_hold_end_stepped,closure_err_mv,margin_rise89_v,margin_fall84_v,margin_floor92_v,recharge_start_ma,time_to_floor_ms,note\n");
    let mut worst_closure_mv = 0.0_f64;
    let mut worst_corner = String::new();
    for k in &corners {
        let c = closed_form(k);
        let s = stepped(k);
        // Re-simulate recharge tail for the stepped end voltage.
        let err_mv = ((s.v_hold_end - c.v_hold_end).abs()) * 1000.0;
        if err_mv > worst_closure_mv {
            worst_closure_mv = err_mv;
            worst_corner = k.name.to_string();
        }
        csv.push_str(&format!(
            "{},{:.4},{:.2},{:.3},{:.1},{:.4},{:.4},{:.4},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},{:.6},\"{}\"\n",
            k.name, k.vaux_v, k.vf_v, k.r_ohm, k.c_f * 1e6, k.i_hold_a * 1000.0,
            k.t_hold_s * 1000.0, k.t_rech_s * 1000.0,
            c.v_start, c.v_hold_end, s.v_hold_end, err_mv,
            c.v_hold_end - UVLO_RISE_MAX,
            c.v_hold_end - UVLO_FALL_MAX,
            c.v_hold_end - UVLO_DESIGN_FLOOR,
            c.i_rech_start,
            if c.t_to_floor.is_nan() { -1.0 } else { c.t_to_floor * 1000.0 },
            k.note));
    }
    fs::write(outdir.join("startup_corners.csv"), &csv).expect("write corners csv");

    // --- cold-start transient (both legs, worst peak corner) ---
    // Max-source corner: Vaux 15.475 (max tol + ripple peak), Vf_min 0.6
    // (assumed), R_min 209 (220 - 5 %), C_max 120 uF.
    let vaux_max = 15.0 * 1.025 + 0.100;
    let src_max = vaux_max - 0.60;
    let r_min = 220.0 * 0.95;
    let c_max = 120e-6_f64;
    let tau_max = r_min * c_max;
    // Worst-known AUX DC base load during charge (operating rail loads that
    // are already up is ~0 at t=0; use direct-AUX worst-known 4 mA as the
    // standing load by the time the rail is up).
    let i_aux_base = 4.0e-3_f64;
    let i_peak_leg = src_max / r_min;
    let i_peak_total = 2.0 * i_peak_leg + i_aux_base;
    // Time series, ideal source.
    let mut ts = String::from("t_ms,i_leg_a_ma,i_total_ma,v_cap_v\n");
    let mut t = 0.0_f64;
    while t <= 0.500 {
        let v = src_max * (1.0 - (-t / tau_max).exp());
        let i_leg = (src_max - v) / r_min;
        ts.push_str(&format!("{:.3},{:.4},{:.4},{:.6}\n", t * 1000.0, i_leg * 1000.0, (2.0 * i_leg + i_aux_base) * 1000.0, v));
        t += 0.0005;
    }
    fs::write(outdir.join("cold_charge.csv"), &ts).expect("write cold charge csv");

    // --- current-limit clamp variants (illustrative foldback-type source) ---
    for (fname, ilim) in [("cold_charge_ilim770.csv", 0.77_f64), ("cold_charge_ilim670.csv", 0.67_f64)] {
        let dt = 5e-6_f64;
        let mut v = 0.0_f64;
        let mut s = String::from("t_ms,i_leg_a_ma,i_total_ma,v_cap_v\n");
        let mut tt = 0.0_f64;
        let mut step = 0usize;
        while tt <= 0.500 {
            // Resistor current demand per leg; the driver is in UVLO while
            // charging, so debiting the full operating hold current here is
            // conservative (slower charge, same peak).
            let ir_dem = ((src_max - v) / r_min).max(0.0);
            let tot_dem = 2.0 * ir_dem + i_aux_base;
            let scale = if tot_dem > ilim { (ilim - i_aux_base) / (tot_dem - i_aux_base) } else { 1.0 };
            let ir = ir_dem * scale.max(0.0);
            v += (ir - i_max) / c_max * dt;
            if v < 0.0 { v = 0.0; }
            if step % 100 == 0 {
                s.push_str(&format!("{:.3},{:.4},{:.4},{:.6}\n", tt * 1000.0, ir * 1000.0, (2.0 * ir + i_aux_base) * 1000.0, v));
            }
            step += 1;
            tt += dt;
        }
        fs::write(outdir.join(fname), &s).expect("write ilim csv");
    }

    // --- cold-charge slowest-source corner: time to 9.2 V floor ---
    let src_min = 14.425 - 1.10;
    let r_max = 231.0_f64;
    let equil_min = src_min - i_max * r_max;
    let t_floor = -r_max * c_max * (1.0 - UVLO_DESIGN_FLOOR / equil_min).ln();
    let t_full5t = 5.0 * r_max * c_max;

    let closure_pass = worst_closure_mv < 2.0;
    let closure = format!(
        "closure check (closed-form fixed point vs 1-us time-stepped integration, identical ODEs):\nworst |stepped - closed| hold-end error = {:.6} mV at corner '{}'\nverdict: {}\n",
        worst_closure_mv, worst_corner,
        if closure_pass { "PASS (< 2 mV)" } else { "FAIL" });
    fs::write(outdir.join("closure.txt"), &closure).expect("write closure");
    print!("{}", closure);

    // --- stdout JSON summary for the ledger ---
    println!("{{\"cold_peak_leg_a\":{:.6},\"cold_peak_total_a\":{:.6},\"cold_tau_s\":{:.6},\"cold_energy_per_leg_j\":{:.6},\"time_to_floor_min_source_s\":{:.6},\"time_5tau_max_s\":{:.6},\"worst_closure_mv\":{:.6},\"closure_pass\":{}}}",
        i_peak_leg, i_peak_total, tau_max,
        0.5 * c_max * src_max * src_max,
        t_floor, t_full5t, worst_closure_mv, closure_pass);
}

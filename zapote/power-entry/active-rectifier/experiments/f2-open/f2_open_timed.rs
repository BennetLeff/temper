//! F2-open time-domain model: diode-side transient with detection delay,
//! continued switching under a stated simplified gate law, and mains inflow.
//!
//! Scope: healthy U9 (controllable switch) only. Failed-short U9 is a separate
//! case and is NOT modeled here (no gate command opens that path).
//!
//! Circuit modeled (authored source `elec/src/power_entry_active_unit.ato`,
//! read-only; diode-side ECO: U20.1 senses BOOST_DIODE_POSITIVE):
//!   mains -> bridge -> L_boost (L) -> node a1 -> { U9 -> CONTROL_GND (switch),
//!                                                 U10 -> BOOST_DIODE_POSITIVE (diode) }
//!   BOOST_DIODE_POSITIVE -> C_hf (U40) -> CONTROL_GND
//!   BOOST_DIODE_POSITIVE -> divider (5x200k + 13k) -> CONTROL_GND -> VSENSE
//!   VSENSE -> 680 pF filter (tau ~ 8.7 us with 12.83k Thevenin)
//! F2 open: bank (2240 uF) disconnected from BOOST_DIODE_POSITIVE.
//!
//! Gate law (STATED SIMPLIFICATION, not controller qualification):
//! fixed-period switching at fsw with duty D = clamp(1 - vin/v, 0, DMAX)
//! evaluated at each cycle start (steady-CCM boost duty at that phase),
//! cycle-by-cycle PCL early-OFF at the ISENSE pin threshold corner, until
//! the (filtered) sense crosses the OVP/detector threshold; the gate then
//! continues the same pattern for T_resp (detection + comparator + driver +
//! fall latency, a swept REQUIREMENT axis, not a measured value) and then
//! turns OFF latched for the event. Freewheeling through the ideal diode
//! (Vf = 0, stated) follows until i = 0; the cap then bleeds into the divider.
//!
//! Energy identity (asserted per run, residual printed):
//!   dEcap + dEL = Wsrc - Ediv,  with Ediv into Rdiv, Wsrc = Vin*I from source,
//!   all integrated to the voltage peak with the trapezoidal rule.
//!
//! Build: rustc -O f2_open_timed.rs -o /tmp/f2_open_timed

use std::f64::consts::PI;

// ---------- retained / authored inputs ----------
const VPK_LINE: f64 = 169.705627485; // 120 Vrms * sqrt(2); retained CCM model input (assumed operating point)
const FLINE: f64 = 60.0; // assumed mains frequency (stated assumption)
const FSW: f64 = 129_107.0; // retained switching frequency, Hz
const DMAX: f64 = 0.965; // UCC28180 DMAX typ 96.5% (assumed fixed; corners NULL)
const RSENSE: f64 = 0.010; // authored HCSM2818FT10L0 10 mOhm (+/-1% via retained Stackpole doc + MPN F code)
const RDIV: f64 = 1_013_000.0; // 5x200k + 13k nominal
const KDIV: f64 = 13.0 / 1013.0; // divider ratio nominal
const TAU_V: f64 = 8.726e-6; // 12.835k Thevenin * 680 pF (nominal)
const VSTART: f64 = 389.6153846; // pre-open regulated diode-side voltage (nominal divider, VREF=5.00)
// PCL pin-voltage thresholds (TI UCC28180 Rev D, EC table p.6): min/typ/max
const VPCL: [f64; 3] = [-0.345, -0.400, -0.438];
// OVP_H %VREF corners (TI EC table p.6): min/typ/max
const VOVP_H_PCT: [f64; 3] = [1.07, 1.09, 1.11];
// VREF corners (TI EC table p.6): 25 C min/typ/max, over-temp min/max
const VREF_25: [f64; 3] = [4.93, 5.00, 5.07];
const VREF_TEMP_MIN: f64 = 4.87;
const VREF_TEMP_MAX: f64 = 5.15;
// Assumed divider resistor tolerance axis (no retained CRCW doc: ASSUMED, not qualified)
const RDIV_TOL: f64 = 0.01;

#[derive(Clone, Copy)]
struct ThresholdSet {
    name: &'static str,
    vth: f64, // diode-side trip voltage at the power node (V)
}

fn divider_ratio(top_each: f64, bot: f64) -> f64 {
    bot / (5.0 * top_each + bot)
}

fn ovp_thresholds() -> Vec<ThresholdSet> {
    let k_nom = divider_ratio(200_000.0, 13_000.0);
    debug_assert!((k_nom - KDIV).abs() < 1e-12);
    // Assumed tolerance corners on the ratio (bottom-low/top-high engages latest).
    let k_min = divider_ratio(200_000.0 * (1.0 + RDIV_TOL), 13_000.0 * (1.0 - RDIV_TOL));
    let k_max = divider_ratio(200_000.0 * (1.0 - RDIV_TOL), 13_000.0 * (1.0 + RDIV_TOL));
    let mut v = Vec::new();
    // Controller OVP_H at the diode-side node.
    v.push(ThresholdSet { name: "ovp_latest", vth: VOVP_H_PCT[2] * VREF_TEMP_MAX / k_min });
    v.push(ThresholdSet { name: "ovp_typ", vth: VOVP_H_PCT[1] * VREF_25[1] / k_nom });
    v.push(ThresholdSet { name: "ovp_early", vth: VOVP_H_PCT[0] * VREF_25[0] / k_max });
    // Independent-detector candidate threshold (selection proposal): 500 V nominal
    // at the node; corners from the same assumed divider tolerance.
    v.push(ThresholdSet { name: "det_latest", vth: 500.0 * (k_nom / k_min) });
    v.push(ThresholdSet { name: "det_typ", vth: 500.0 });
    v.push(ThresholdSet { name: "det_early", vth: 500.0 * (k_nom / k_max) });
    let _ = VREF_TEMP_MIN;
    v
}

#[derive(Clone, Copy)]
struct Run {
    vpk: f64,
    phase_deg: f64,
    i0: f64,
    l: f64,
    c: f64,
    vth: f64,
    t_resp: f64,
    ipcl: f64, // PCL trip current (A), corner
}

struct Out {
    vpeak: f64,
    t_peak: f64,
    t_trip: f64, // sense-trip time, -1 if never
    ecap: f64,   // dEcap to peak (J)
    el_rel: f64, // inductor energy released to peak: 0.5L(I0^2 - Ipeak^2) (J)
    wsrc: f64,   // source work to peak (J)
    ediv: f64,   // divider loss to peak (J)
    resid: f64,  // ecap - el_rel - wsrc + ediv (must be ~0)
    aborted: bool,
}

fn simulate(r: Run) -> Out {
    let dt = 2e-9;
    let w = 2.0 * PI * FLINE;
    let tsw = 1.0 / FSW;
    let th0 = r.phase_deg * PI / 180.0;
    let vin_now = |t: f64| (r.vpk * (th0 + w * t).sin()).abs();
    let mut t = 0.0;
    let mut i = r.i0;
    let mut v = VSTART;
    let mut vsf = KDIV * v;
    let mut gate_off = false;
    let mut t_cmd = f64::INFINITY;
    let mut tripped = false;
    let mut t_trip = -1.0;
    let mut cyc_t = 0.0;
    let mut d = (1.0 - vin_now(0.0) / v).clamp(0.0, DMAX);
    let mut cyc_ton = d * tsw;
    let mut sw_on = true;
    let mut vpeak = v;
    let mut t_peak = 0.0;
    // energy accumulators with snapshots at the running peak
    let mut wsrc = 0.0;
    let mut ediv = 0.0;
    let (mut s_wsrc, mut s_ediv, mut s_i) = (0.0, 0.0, i);
    let mut aborted = false;
    let t_end = 400e-6;
    // derivative closure: returns (di, dv) for a switch state
    let deriv = |vin: f64, i: f64, v: f64, on: bool| -> (f64, f64) {
        if on {
            (vin / r.l, -v / (RDIV * r.c))
        } else if i > 0.0 {
            ((vin - v) / r.l, i / r.c - v / (RDIV * r.c))
        } else {
            (0.0, -v / (RDIV * r.c))
        }
    };
    while t < t_end {
        let vin = vin_now(t);
        if cyc_t >= tsw {
            cyc_t -= tsw;
            if !gate_off {
                d = (1.0 - vin / v).clamp(0.0, DMAX);
                cyc_ton = d * tsw;
                sw_on = true;
            }
        }
        if !gate_off && sw_on && cyc_t >= cyc_ton {
            sw_on = false;
        }
        // PCL early-off (healthy-switch cycle-by-cycle limit, corner value)
        if !gate_off && sw_on && i >= r.ipcl {
            sw_on = false;
        }
        // detection on filtered sense
        if !tripped && vsf >= r.vth * KDIV {
            tripped = true;
            t_trip = t;
            t_cmd = t + r.t_resp;
        }
        if tripped && t >= t_cmd {
            gate_off = true;
            sw_on = false;
        }
        let on = !gate_off && sw_on;
        let (di, dv) = deriv(vin, i, v, on);
        let mut i1 = i + dt * di;
        if !on && i1 < 0.0 {
            i1 = 0.0;
        }
        if on && i1 < 0.0 {
            i1 = 0.0;
        }
        let v1 = v + dt * dv;
        let vin1 = vin_now(t + dt);
        let on1 = on; // switch state held over the step (dt << tsw)
        let (di2, dv2) = deriv(vin1, i1, v1, on1);
        let mut i2 = i + 0.5 * dt * (di + di2);
        if i2 < 0.0 {
            i2 = 0.0;
        }
        let v2 = v + 0.5 * dt * (dv + dv2);
        wsrc += 0.5 * (vin + vin1) * (0.5 * (i + i2)) * dt;
        ediv += 0.5 * (v * v + v2 * v2) / RDIV * dt;
        i = i2;
        v = v2;
        vsf += dt / TAU_V * (KDIV * v - vsf);
        t += dt;
        cyc_t += dt;
        if v > vpeak {
            vpeak = v;
            t_peak = t;
            s_wsrc = wsrc;
            s_ediv = ediv;
            s_i = i;
        }
        if v > 950.0 {
            aborted = true;
            break;
        }
        if gate_off && i == 0.0 && t > t_peak && (t - t_peak) > 20e-6 {
            break;
        }
    }
    let ecap = 0.5 * r.c * (vpeak * vpeak - VSTART * VSTART);
    let el_rel = 0.5 * r.l * (r.i0 * r.i0 - s_i * s_i);
    let resid = ecap - el_rel - s_wsrc + s_ediv;
    Out { vpeak, t_peak, t_trip, ecap, el_rel, wsrc: s_wsrc, ediv: s_ediv, resid, aborted }
}

fn immediate_off_closed(vin: f64, v0: f64, i0: f64, l: f64, c: f64) -> f64 {
    vin + ((v0 - vin) * (v0 - vin) + l / c * i0 * i0).sqrt()
}

fn run_closed_form_check() {
    // Second path, part 1: gate already off at t=0 with constant Vin must
    // reproduce the retained immediate-off closed form (f2_open.rs algebra).
    let r = Run { vpk: VPK_LINE, phase_deg: 90.0, i0: 21.1709662361 + 2.0608720834, l: 180e-6, c: 470e-9, vth: 1e9, t_resp: 0.0, ipcl: 1e9 };
    // force immediate-off: emulate by starting tripped with t_cmd = 0
    let o = simulate_immediate_off(r);
    let expect = immediate_off_closed(VPK_LINE, VSTART, r.i0, r.l, r.c);
    let rel = ((o.vpeak - expect) / expect).abs();
    eprintln!("closed-form check: model {:.4} V vs formula {:.4} V (rel {:.3e})", o.vpeak, expect, rel);
    assert!(rel < 3e-3, "closed-form limit diverged");
    assert!(o.resid.abs() < 1e-6, "energy identity failed in check run");
    // Second path, part 2: burst-period closed form vs numeric bleed integration.
    for (name, c, vt, vr) in [
        ("typ", 470e-9, 424.68_f64, 397.37_f64),
        ("latest", 470e-9, 454.33_f64, 406.0_f64),
    ] {
        let tau = RDIV * c;
        let t_log = tau * (vt / vr).ln();
        // numeric: integrate dv/dt = -v/tau from vt to vr
        let dt = 1e-6;
        let (mut v, mut t) = (vt, 0.0);
        while v > vr {
            v += dt * (-v / tau);
            t += dt;
        }
        let rel = ((t - t_log) / t_log).abs();
        eprintln!("burst-period check {name}: numeric {t:.6}s vs log {t_log:.6}s (rel {rel:.3e})");
        assert!(rel < 1e-4, "burst period mismatch");
    }
}

/// Immediate-off variant: gate off at t=0, constant Vin (the retained screen).
/// Shares the OFF-phase physics and energy bookkeeping of simulate().
fn simulate_immediate_off(r: Run) -> Out {
    simulate_immediate_off_v0(r, VSTART)
}

fn simulate_immediate_off_v0(r: Run, v0: f64) -> Out {
    let dt = 2e-9;
    let vin = r.vpk; // constant crest value
    let mut t = 0.0;
    let mut i = r.i0;
    let mut v = v0;
    let mut wsrc = 0.0;
    let mut ediv = 0.0;
    let (mut s_wsrc, mut s_ediv, mut s_i) = (0.0, 0.0, i);
    let mut vpeak = v;
    let mut t_peak = 0.0;
    while t < 400e-6 {
        let (di, dv) = if i > 0.0 { ((vin - v) / r.l, i / r.c - v / (RDIV * r.c)) } else { (0.0, -v / (RDIV * r.c)) };
        let mut i1 = i + dt * di;
        if i1 < 0.0 {
            i1 = 0.0;
        }
        let v1 = v + dt * dv;
        let (di2, dv2) = if i1 > 0.0 { ((vin - v1) / r.l, i1 / r.c - v1 / (RDIV * r.c)) } else { (0.0, -v1 / (RDIV * r.c)) };
        let mut i2 = i + 0.5 * dt * (di + di2);
        if i2 < 0.0 {
            i2 = 0.0;
        }
        let v2 = v + 0.5 * dt * (dv + dv2);
        wsrc += vin * (0.5 * (i + i2)) * dt;
        ediv += 0.5 * (v * v + v2 * v2) / RDIV * dt;
        i = i2;
        v = v2;
        t += dt;
        if v > vpeak {
            vpeak = v;
            t_peak = t;
            s_wsrc = wsrc;
            s_ediv = ediv;
            s_i = i;
        }
        if i == 0.0 && t > t_peak && (t - t_peak) > 20e-6 {
            break;
        }
    }
    let ecap = 0.5 * r.c * (vpeak * vpeak - v0 * v0);
    let el_rel = 0.5 * r.l * (r.i0 * r.i0 - s_i * s_i);
    let resid = ecap - el_rel - s_wsrc + s_ediv;
    Out { vpeak, t_peak, t_trip: 0.0, ecap, el_rel, wsrc: s_wsrc, ediv: s_ediv, resid, aborted: false }
}

fn simulate_pattern() -> Out {
    // Prescribed gate pattern mirroring evidence/f2-open-timed-02/patt.cir:
    // ON 0-4 us, OFF 4-8 us, ON 8-12 us, latched OFF after 12 us.
    // Const crest Vin, V0 = VSTART, I0 = crest, L = 180 uH, C = 470 nF.
    let dt = 2e-9;
    let vin = VPK_LINE;
    let (l, c) = (180e-6, 470e-9);
    let i0 = 21.1709662361 + 2.0608720834;
    let mut t = 0.0;
    let mut i = i0;
    let mut v = VSTART;
    let mut wsrc = 0.0;
    let mut ediv = 0.0;
    let (mut s_wsrc, mut s_ediv, mut s_i) = (0.0, 0.0, i);
    let mut vpeak = v;
    let mut t_peak = 0.0;
    while t < 200e-6 {
        let on = (t < 4e-6) || (t >= 8e-6 && t < 12e-6);
        let (di, dv) = if on {
            (vin / l, -v / (RDIV * c))
        } else if i > 0.0 {
            ((vin - v) / l, i / c - v / (RDIV * c))
        } else {
            (0.0, -v / (RDIV * c))
        };
        let mut i1 = i + dt * di;
        if i1 < 0.0 {
            i1 = 0.0;
        }
        let v1 = v + dt * dv;
        let (di2, dv2) = if on {
            (vin / l, -v1 / (RDIV * c))
        } else if i1 > 0.0 {
            ((vin - v1) / l, i1 / c - v1 / (RDIV * c))
        } else {
            (0.0, -v1 / (RDIV * c))
        };
        let mut i2 = i + 0.5 * dt * (di + di2);
        if i2 < 0.0 {
            i2 = 0.0;
        }
        let v2 = v + 0.5 * dt * (dv + dv2);
        wsrc += vin * (0.5 * (i + i2)) * dt;
        ediv += 0.5 * (v * v + v2 * v2) / RDIV * dt;
        i = i2;
        v = v2;
        t += dt;
        if v > vpeak {
            vpeak = v;
            t_peak = t;
            s_wsrc = wsrc;
            s_ediv = ediv;
            s_i = i;
        }
        if i == 0.0 && t > t_peak && (t - t_peak) > 20e-6 {
            break;
        }
    }
    let ecap = 0.5 * c * (vpeak * vpeak - VSTART * VSTART);
    let el_rel = 0.5 * l * (i0 * i0 - s_i * s_i);
    let resid = ecap - el_rel - s_wsrc + s_ediv;
    Out { vpeak, t_peak, t_trip: -1.0, ecap, el_rel, wsrc: s_wsrc, ediv: s_ediv, resid, aborted: false }
}

fn run_burst_table() {
    // Case (a)/(c): startup into open F2 and repeated restart bursts.
    // All closed-form; assumptions stated per row in MODEL.md.
    println!("param,value,unit,note");
    let c = 470e-9;
    let vt = 424.68; // typ OVP_H engage at node
    let vr = 397.37; // typ OVP_H reset (102%) at node
    let e_trip = 0.5 * c * vt * vt;
    println!("E_trip_typ_J,{:.6},J,0.5*C*Vt^2 from 0 V typ threshold", e_trip);
    let tsw = 1.0 / FSW;
    let ton = DMAX * tsw;
    let ipk_cyc = VPK_LINE * ton / 180e-6;
    println!("worst_cycle_Ipk_A,{:.3},A,Vin crest DMAX one ON (bounding)", ipk_cyc);
    let e_cyc_max = VPK_LINE * ipk_cyc * tsw;
    println!("worst_cycle_E_mJ,{:.4},mJ,Vin*Ipk*Tsw generous bound", e_cyc_max * 1e3);
    println!("cycles_to_first_trip_le,{:.1},cycles,E_trip/E_cyc_max ceiling bound", (e_trip / e_cyc_max).ceil());
    // overshoot bound: one more full ON worth of current + freewheel from Vt
    let i_over = ipk_cyc * 2.0; // residual + one fresh ON (bounding)
    let v_over = immediate_off_closed(VPK_LINE, vt, i_over, 180e-6, c);
    println!("first_burst_overshoot_bound_V,{:.1},V,closed form from Vt with 2xIpk (bounding)", v_over);
    for (name, cc, vtt, vrr) in [("typ", c, vt, vr), ("latest", c, 454.33, 406.0), ("typ_1p5uF", 1.5e-6, vt, vr)] {
        let tau = RDIV * cc;
        let tb = tau * (vtt / vrr).ln();
        let e_burst = 0.5 * cc * (vtt * vtt - vrr * vrr);
        println!("burst_period_{}_s,{:.6},s,Rdiv*C*ln(Vt/Vr)", name, tb);
        println!("burst_energy_{}_mJ,{:.4},mJ,0.5*C*(Vt^2-Vr^2)", name, e_burst * 1e3);
        println!("burst_avg_power_{}_mW,{:.4},mW,E_burst/T", name, e_burst / tb * 1e3);
    }
    println!("unfused_energy_470nF_400V_J,{:.5},J,0.5*C*V^2", 0.5 * 470e-9 * 400.0 * 400.0);
    println!("unfused_energy_1p5uF_400V_J,{:.5},J,0.5*C*V^2", 0.5 * 1.5e-6 * 400.0 * 400.0);
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 && args[1] == "burst" {
        run_burst_table();
        return;
    }
    if args.len() > 3 && args[1] == "xcheck" {
        // Immediate-off at caller-supplied (V0, I0) for ngspice cross-checks.
        let v0: f64 = args[2].parse().expect("V0");
        let i0: f64 = args[3].parse().expect("I0");
        let o = simulate_immediate_off_v0(Run { vpk: VPK_LINE, phase_deg: 90.0, i0, l: 180e-6, c: 470e-9, vth: 1e9, t_resp: 0.0, ipcl: 1e9 }, v0);
        println!("xcheck,V0={:.3},I0={:.4},Vpeak={:.4},resid_J={:.3e}", v0, i0, o.vpeak, o.resid);
        println!("closed,{:.4}", immediate_off_closed(VPK_LINE, v0, i0, 180e-6, 470e-9));
        return;
    }
    if args.len() > 1 && args[1] == "patt" {
        // Prescribed gate pattern (mirrors the ngspice PWL deck):
        // ON 0-4 us, OFF 4-8 us, ON 8-12 us, latched OFF after 12 us.
        // Const crest Vin, V0 = 389.615 V, I0 = crest, ideal switch/diode.
        let o = simulate_pattern();
        println!("patt,Vpeak={:.4},t_peak_us={:.4},resid_J={:.3e}", o.vpeak, o.t_peak * 1e6, o.resid);
        return;
    }
    let thr = ovp_thresholds();
    run_closed_form_check();
    eprintln!("thresholds:");
    for th in &thr {
        eprintln!("  {} = {:.2} V", th.name, th.vth);
    }
    // I0 basis (retained ripple numbers): mean 21.1710 A + half-ripple 2.0609 A at crest.
    let i_crest = 21.1709662361 + 2.0608720834;
    let ipcl_typ = VPCL[1].abs() / RSENSE; // 40.0 A
    let ipcl_min = VPCL[0].abs() / (RSENSE * 1.01); // 34.16 A
    let ipcl_max = VPCL[2].abs() / (RSENSE * 0.99); // 44.24 A
    eprintln!("i_crest = {:.4} A, ipcl corners = {:.2}/{:.2}/{:.2} A", i_crest, ipcl_min, ipcl_typ, ipcl_max);
    let vth_typ = thr[1].vth;
    println!("case,phase_deg,i0_a,l_uH,c_nF,vth_v,t_resp_us,ipcl_a,vpeak_v,t_peak_us,t_trip_us,ecap_mJ,elrel_mJ,wsrc_mJ,ediv_mJ,resid_uJ,aborted");
    // Core sweep: crest phase, nominal L/C, typ OVP, response axis
    for t_resp_us in [0.0, 2.0, 5.0, 10.0, 20.0] {
        let r = Run { vpk: VPK_LINE, phase_deg: 90.0, i0: i_crest, l: 180e-6, c: 470e-9, vth: vth_typ, t_resp: t_resp_us * 1e-6, ipcl: ipcl_typ };
        let o = simulate(r);
        println!("crest_nom_ovptyp_r{},90.0,{:.4},{:.3},{:.3},{:.2},{:.2},{:.2},{:.2},{:.3},{:.3},{:.4},{:.4},{:.4},{:.6},{:.3},{}", t_resp_us, r.i0, r.l * 1e6, r.c * 1e9, r.vth, t_resp_us, r.ipcl, o.vpeak, o.t_peak * 1e6, o.t_trip * 1e6, o.ecap * 1e3, o.el_rel * 1e3, o.wsrc * 1e3, o.ediv * 1e3, o.resid * 1e6, o.aborted as u8);
    }
    let extra: Vec<(&str, f64, f64, f64, f64, f64, f64, f64)> = vec![
        // name, phase, i0, l, c, vth_idx(99=typ), t_resp_us, ipcl_sel(0=min,1=typ,2=max)
        ("crest_1uF", 90.0, i_crest, 180e-6, 1.0e-6, 1.0, 5.0, 1.0),
        ("crest_1p5uF", 90.0, i_crest, 180e-6, 1.5e-6, 1.0, 5.0, 1.0),
        ("crest_470nF_L216", 90.0, i_crest, 216e-6, 470e-9, 1.0, 5.0, 1.0),
        ("crest_470nF_C90", 90.0, i_crest, 180e-6, 423e-9, 1.0, 5.0, 1.0),
        ("crest_470nF_C110", 90.0, i_crest, 180e-6, 517e-9, 1.0, 5.0, 1.0),
        ("phase45", 45.0, 21.1709662361 * 0.70710678 + 2.0608720834, 180e-6, 470e-9, 1.0, 5.0, 1.0),
        ("phase30", 30.0, 21.1709662361 * 0.5 + 2.0608720834, 180e-6, 470e-9, 1.0, 5.0, 1.0),
        ("crest_ovp_latest", 90.0, i_crest, 180e-6, 470e-9, 0.0, 5.0, 1.0),
        ("crest_ovp_early", 90.0, i_crest, 180e-6, 470e-9, 2.0, 5.0, 1.0),
        ("crest_det_latest", 90.0, i_crest, 180e-6, 470e-9, 3.0, 5.0, 1.0),
        ("crest_i0_p10", 90.0, i_crest * 1.10, 180e-6, 470e-9, 1.0, 5.0, 1.0),
        ("crest_pcl_min", 90.0, i_crest, 180e-6, 470e-9, 1.0, 5.0, 0.0),
        ("crest_1p5uF_r0", 90.0, i_crest, 180e-6, 1.5e-6, 1.0, 0.0, 1.0),
        ("crest_1p5uF_r20", 90.0, i_crest, 180e-6, 1.5e-6, 1.0, 20.0, 1.0),
        ("crest_1p5uF_detlate_r10", 90.0, i_crest, 180e-6, 1.5e-6, 3.0, 10.0, 1.0),
        ("crest_470nF_detlate_r0", 90.0, i_crest, 180e-6, 470e-9, 3.0, 0.0, 1.0),
        ("crest_470nF_detlate_r2", 90.0, i_crest, 180e-6, 470e-9, 3.0, 2.0, 1.0),
        ("crest_vpk_p10", 90.0, i_crest, 180e-6, 470e-9, 1.0, 5.0, 1.0), // vpk overridden below
        ("c15_L216_r5", 90.0, i_crest, 216e-6, 1.5e-6, 1.0, 5.0, 1.0),
        ("c15_C90_r5", 90.0, i_crest, 180e-6, 1.35e-6, 1.0, 5.0, 1.0),
        ("c15_i0p10_r5", 90.0, i_crest * 1.10, 180e-6, 1.5e-6, 1.0, 5.0, 1.0),
        ("c15_vpkp10_r5", 90.0, i_crest, 180e-6, 1.5e-6, 1.0, 5.0, 1.0), // vpk overridden below
        ("c15_ovplate_r5", 90.0, i_crest, 180e-6, 1.5e-6, 0.0, 5.0, 1.0),
        ("c15_r10", 90.0, i_crest, 180e-6, 1.5e-6, 1.0, 10.0, 1.0),
        ("c15_phase45_r5", 45.0, 21.1709662361 * 0.70710678 + 2.0608720834, 180e-6, 1.5e-6, 1.0, 5.0, 1.0),
    ];
    for (name, ph, i0, l, c, vi, tr, ps) in extra {
        let vth = thr[vi as usize].vth;
        let ipcl = if ps < 0.5 { ipcl_min } else if ps > 1.5 { ipcl_max } else { ipcl_typ };
        let vpk = if name == "crest_vpk_p10" || name == "c15_vpkp10_r5" { VPK_LINE * 1.10 } else { VPK_LINE };
        let r = Run { vpk, phase_deg: ph, i0, l, c, vth, t_resp: tr * 1e-6, ipcl };
        let o = simulate(r);
        println!("{},{},{:.4},{:.3},{:.3},{:.2},{:.2},{:.2},{:.2},{:.3},{:.3},{:.4},{:.4},{:.4},{:.6},{:.3},{}", name, ph, r.i0, r.l * 1e6, r.c * 1e9, r.vth, tr, r.ipcl, o.vpeak, o.t_peak * 1e6, o.t_trip * 1e6, o.ecap * 1e3, o.el_rel * 1e3, o.wsrc * 1e3, o.ediv * 1e3, o.resid * 1e6, o.aborted as u8);
    }
}

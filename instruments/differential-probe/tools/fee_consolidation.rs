//! JLC Extended-fee consolidation (docs/fee-consolidation.md): the electrical side of
//! each candidate swap. Fees and savings come from procurement/cost.py; this tool
//! checks what each swap does to the warning budget, the output filter and the
//! subtractor. Writes validation/fee-consolidation.txt. Datasheet limits only.
#[path = "budget.rs"]
mod budget;

use budget::{Res, Warn, BASIC, PRECISION};
use std::f64::consts::PI;
use std::fmt::Write;

/// OPA2810 input common-mode range: to VS+ - 3 V over temperature (datasheet),
/// against the +/-1.5 V tap at the extended +/-3 kV tip voltage (docs/design.md).
const OPA2810_CM_HEADROOM: f64 = 3.0;
const TAP_MAX: f64 = 1.5;

fn ladders(out: &mut String) {
    let p = |nom| Res { nom, tol: PRECISION };
    let b = |nom| Res { nom, tol: BASIC };
    let base = Warn::precision();
    let variants: Vec<(&str, &str, Warn)> = vec![
        ("now", "committed before this change (all 0.1 % / 25 ppm)", base),
        ("L1", "R88/R92 1 k -> 1 % / 100 ppm Basic", Warn { rb: b(1_000.), ..base }),
        ("L2", "R81 30 k -> 1 % / 100 ppm Basic", Warn { r81: b(30_000.), ..base }),
        ("L1+L2", "both", Warn { rb: b(1_000.), r81: b(30_000.), ..base }),
        ("L3", "R83 29.4 k -> 30 k 0.1 % (neg rail -4.88 V)", Warn { r83: p(30_000.), ..base }),
        ("L2+L3", "R81 and R83 30 k 1 % Basic", Warn { r81: b(30_000.), r83: b(30_000.), ..base }),
        ("L4", "R81 -> 3 x 10 k 0.1 % in series (each part independent)", base),
        ("(R87)", "R87/R91 66.5 k -> 1 % (no Basic 66.5 k exists; bound only)", Warn { ra: b(66_500.), ..base }),
    ];
    out.push_str("1. Warning-threshold budget per ladder variant (-25..85 C; limits tip < 1500 V, wide < 1500 V, fine < 300 V)\n");
    out.push_str("   PRECISION = 0.1 % + 25 ppm/C x 60 C; BASIC (Uni-Royal 0805W8F) = 1 % + 100 ppm/C x 60 C.\n");
    out.push_str("   OPA2810 headroom = V+min - 3.0 V (CM range over temperature) - 1.5 V tap.\n\n");
    out.push_str("   variant  late tip/wide/fine (V)       early tip/wide/fine (V)   +rail min  -rail min  OPA2810 headroom  pass\n");
    let mut prev = None;
    for (key, label, w) in &variants {
        let o = budget::warning(w);
        let headroom = o.pos_min - OPA2810_CM_HEADROOM - TAP_MAX;
        let pass = o.tip_max < 1500. && o.wide_late < 1500. && o.fine_late < 300. && headroom > 0.;
        writeln!(
            out,
            "   {key:7}  {:7.1} / {:7.1} / {:6.2}   {:6.0} / {:6.0} / {:5.0}    {:.4} V   {:.4} V   {:+.3} V          {}",
            o.tip_max, o.wide_late, o.fine_late, o.tip_early, o.wide_early, o.fine_early, o.pos_min, o.neg_min, headroom,
            if pass { "yes" } else { "NO" }
        )
        .unwrap();
        writeln!(out, "            {label}").unwrap();
        if *key == "now" {
            prev = Some(o);
        } else if let Some(n) = &prev {
            writeln!(
                out,
                "            late-trip rise vs now: tip {:+.1} V, wide {:+.1} V, fine {:+.2} V",
                o.tip_max - n.tip_max,
                o.wide_late - n.wide_late,
                o.fine_late - n.fine_late
            )
            .unwrap();
        }
    }
    out.push_str("\n   Series or parallel copies of one MPN do not tighten these bounds: each part is\n");
    out.push_str("   independently +/-0.1 % / +/-25 ppm/C with no tracking specification, so the\n");
    out.push_str("   worst case of the combination equals one part's (only the statistical spread narrows).\n\n");
}

struct Part {
    nom: f64,
    tol: f64,
    tc: f64, // ppm/C magnitude
}

fn filter(out: &mut String) {
    // Selector 49.9 R (Uni-Royal 0805W8F 1 % / 100 ppm), loaded by the warning divider
    // (R71 + R72 = 20 k) and R103 1 M; R69 then C61 into U3A (high impedance).
    let load = 1. / (1. / 20_000. + 1. / 1_000_000.);
    let sel = Part { nom: 49.9, tol: 0.01, tc: 100. };
    // R69: Yageo RC0805FR 1 % / 100 ppm and Uni-Royal 0805W8F 1 % / 100 ppm.
    // C61: Yageo CC0805JRNPO9BN181 and Samsung CL21C101JBANNNC, 5 % C0G, 0 +/- 30 ppm/C.
    let variants = [
        ("A", "97.6 R RC0805FR-0797R6L / 180 pF CC0805JRNPO9BN181 (before)", 97.6, 180e-12),
        ("F1", "220 R 0805W8F2200T5E / 180 pF", 220., 180e-12),
        ("F2", "97.6 R / 100 pF CL21C101JBANNNC", 97.6, 100e-12),
        ("F3", "220 R 0805W8F2200T5E / 100 pF CL21C101JBANNNC (adopted)", 220., 100e-12),
        ("F4", "100 R 0805W8F1000T5E / 180 pF", 100., 180e-12),
    ];
    out.push_str("2. Shared output filter (R69 + 49.9 R || 20 k || 1 M source, C61), single pole\n");
    out.push_str("   Tolerance corners: resistors 1 % + 100 ppm/C x 60 C, C61 5 % + 30 ppm/C x 60 C.\n");
    out.push_str("   Drift after a 25 C calibration: TC terms only, x 60 C.\n\n");
    let pole = |r69: f64, s: f64, c: f64| 1. / (2. * PI * (r69 + 1. / (1. / s + 1. / load)) * c);
    let phase = |f: f64, fp: f64| -(f / fp).atan().to_degrees();
    let kt4 = 4. * 1.380649e-23 * 300.;
    for (key, label, r69, c) in variants {
        let r = Part { nom: r69, tol: 0.01, tc: 100. };
        let cp = Part { nom: c, tol: 0.05, tc: 30. };
        let nom = pole(r.nom, sel.nom, cp.nom);
        let dev = |p: &Part| p.tol + p.tc * 1e-6 * 60.;
        let lo = pole(r.nom * (1. + dev(&r)), sel.nom * (1. + dev(&sel)), cp.nom * (1. + dev(&cp)));
        let hi = pole(r.nom * (1. - dev(&r)), sel.nom * (1. - dev(&sel)), cp.nom * (1. - dev(&cp)));
        let drift = |p: &Part| p.tc * 1e-6 * 60.;
        let d_lo = pole(r.nom * (1. + drift(&r)), sel.nom * (1. + drift(&sel)), cp.nom * (1. + drift(&cp)));
        let d_hi = pole(r.nom * (1. - drift(&r)), sel.nom * (1. - drift(&sel)), cp.nom * (1. - drift(&cp)));
        let rs = r.nom + 1. / (1. / sel.nom + 1. / load);
        // Source thermal noise integrated to the pole's noise bandwidth (pi/2 fp).
        let noise = (kt4 * rs * PI / 2. * nom).sqrt();
        writeln!(out, "   {key:3} {label}").unwrap();
        writeln!(
            out,
            "       pole {:.3} MHz (corners {:.3}..{:.3}); 35 kHz {:.4} deg, 60 kHz {:.4} deg (corners {:.4}..{:.4}); 60 kHz amplitude {:.6} dB",
            nom / 1e6,
            lo / 1e6,
            hi / 1e6,
            phase(35e3, nom),
            phase(60e3, nom),
            phase(60e3, lo),
            phase(60e3, hi),
            -10. * (1. + (60e3 / nom).powi(2)).log10()
        )
        .unwrap();
        writeln!(
            out,
            "       60 kHz phase drift after calibration {:+.5}/{:+.5} deg; source {rs:.2} ohm, thermal noise {:.2} uVrms in the pole bandwidth",
            phase(60e3, d_lo) - phase(60e3, nom),
            phase(60e3, d_hi) - phase(60e3, nom),
            noise * 1e6
        )
        .unwrap();
        if key == "F3" {
            assert!((nom / pole(97.6, 49.9, 180e-12) - 1.).abs() < 0.02, "F3 pole moved > 2 %");
        }
    }
    out.push_str("\n   The vendor-model sweep of A, F3 (B) and F4 (C) is validation/spice/candidates.cir\n");
    out.push_str("   (reported in validation/spice/results.txt).\n\n");
}

/// Worst-case common-mode gain of the U3B subtractor, referred to the input as an
/// equivalent leg-ratio mismatch: Vout = Vcm (R4/(R3+R4)(1+R2/R1) - R2/R1), divided by
/// the differential gain R2/R1. R1 = R61, R2 = R63, R3 = R62, R4 = R65.
fn cm_mismatch(nom1: f64, nom2: f64, e1: f64, e2: f64) -> f64 {
    let mut worst = 0f64;
    for s in 0..16 {
        let sg = |k: u32| if s >> k & 1 == 1 { 1. } else { -1. };
        let r1 = nom1 * (1. + sg(0) * e1);
        let r3 = nom1 * (1. + sg(1) * e1);
        let r2 = nom2 * (1. + sg(2) * e2);
        let r4 = nom2 * (1. + sg(3) * e2);
        let acm = r4 / (r3 + r4) * (1. + r2 / r1) - r2 / r1;
        worst = worst.max((acm / (r2 / r1)).abs());
    }
    worst
}

fn subtractor(out: &mut String) {
    // Stackpole RNCF0603TKY: 0.01 %, +/-5 ppm/C (DigiKey parametric for RNCF0603TKY1K00).
    // Yageo RT0805/RT0603 BRD07: 0.1 %, +/-25 ppm/C.
    let (rncf_tc, rt_tc) = (5e-6, 25e-6);
    let variants = [
        ("now", "RNCF 499 / 1 k / 2 k", 499., 1_000., 2_000., rncf_tc, rncf_tc, rncf_tc),
        ("G1", "R63/R65 -> RT0805 1 k; R61/R62/R67/R68 RNCF", 499., 1_000., 2_000., rncf_tc, rt_tc, rncf_tc),
        ("G2", "R68 -> 2 x RNCF 1 k in series", 499., 1_000., 2_000., rncf_tc, rncf_tc, rncf_tc),
        ("G3", "all RT0603 1 k (499 = 1 k || 1 k, 2 k = 1 k + 1 k)", 500., 1_000., 2_000., rt_tc, rt_tc, rt_tc),
    ];
    out.push_str("3. Gain resistors (U3B subtractor R61/R62 in, R63/R65 feedback; fine stage R67/R68)\n");
    out.push_str("   Initial tolerance is calibrated out (per-range gain, DC CMRR trim); what is left is TCR drift.\n");
    out.push_str("   Leg mismatch = subtractor CM gain / differential gain, worst sign combination.\n\n");
    // HV divider string alone: 100 ppm/C per leg, opposing legs.
    let string_per_10c = 2. * 100e-6 * 10.;
    for (key, label, r_in, r_fb, r_fine, tc_in, tc_fb, tc_fine) in variants {
        let wide = r_fb / r_in;
        let fine = 1. + r_fine / r_in;
        let m10 = cm_mismatch(r_in, r_fb, tc_in * 10., tc_fb * 10.);
        let m60 = cm_mismatch(r_in, r_fb, tc_in * 60., tc_fb * 60.);
        let wide_drift = (tc_in + tc_fb) * 60.;
        // Fine stage gain 1 + R68/R67 times the wide gain: R67 and R68 opposing.
        let fine_drift = wide_drift + (tc_in + tc_fine) * 60. * (fine - 1.) / fine;
        writeln!(out, "   {key:4} {label}").unwrap();
        writeln!(
            out,
            "        gains: subtractor {wide:.4}, fine stage {fine:.4}; leg mismatch {:.1} ppm per 10 C, {:.1} ppm over 60 C (HV string alone allows {:.0} ppm per 10 C)",
            m10 * 1e6,
            m60 * 1e6,
            string_per_10c * 1e6
        )
        .unwrap();
        writeln!(
            out,
            "        gain drift over 60 C: wide {:.3} %, fine {:.3} %",
            wide_drift * 100.,
            fine_drift * 100.
        )
        .unwrap();
    }
    out.push('\n');
}

fn main() {
    let mut out = String::from(
        "Rev C fee consolidation, electrical checks (tools/fee_consolidation.rs; docs/fee-consolidation.md)\n\n",
    );
    ladders(&mut out);
    filter(&mut out);
    subtractor(&mut out);
    std::fs::write("validation/fee-consolidation.txt", &out).expect("write validation/fee-consolidation.txt");
    print!("{out}");
}

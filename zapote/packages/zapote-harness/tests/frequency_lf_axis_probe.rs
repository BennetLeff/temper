//! Pre-campaign diagnostic probe (G0 premise check).
//!
//! The PFC campaign plan's six frequency tasks (F030/F045/F065/F090/F129/F180)
//! change `frequency_hz` while holding the product `L * f` fixed at the
//! baseline value. Before spending six workers on that axis, this probe asks a
//! single question of the *maintained* kernels:
//!
//!   At fixed `L * f`, does anything in the current waveform or its loss terms
//!   depend on frequency other than the explicitly f-proportional terms?
//!
//! It is a diagnostic. It adds no model, no verdict authority and no new
//! physics; it calls `zapote_erc::{pfc_currents, pfc_losses, pfc_switching}`
//! exactly as `pfc_drive_experiment` does. The baseline drive condition is
//! copied from that module's `no-assist` / IPW65R045C7 nominal point.
//!
//! Run: cargo test -p zapote-harness --test frequency_lf_axis_probe -- --nocapture

use zapote_erc::{pfc_currents, pfc_losses, pfc_switching};

const BUS_V: f64 = 400.0;
const INPUT_RMS_LIMIT_A: f64 = 15.0;
const LINE_RMS_V: f64 = 120.0;
const L0_H: f64 = 180e-6;
/// Requested nominal real input power from the campaign's contract C1.
const REQUESTED_POWER_W: f64 = 1796.31003212911;

// IPW65R045C7 source values, as used by pfc_drive_experiment::DEVICES.
const QG_C: f64 = 93e-9;
const QGD_C: f64 = 30e-9;
const PLATEAU_V: f64 = 5.4;
const INTRINSIC_GATE_R_OHM: f64 = 0.85;
const EOSS_J: f64 = 11.7e-6;
const RDS_MAX_OHM: f64 = 0.045;

// `no-assist` driver profile.
const DRIVER_SOURCE_R_OHM: f64 = 5.0;
const DRIVER_SINK_R_OHM: f64 = 0.6;
const EXTERNAL_GATE_R_OHM: f64 = 4.7;
const DRIVER_V: f64 = 12.0;
const CURRENT_TRANSFER_CHARGE_C: f64 = 10e-9;

const SOURCE_PEAK_A: f64 = 5.0;
const SINK_PEAK_A: f64 = 5.0;
const LOOP_INDUCTANCE_H: f64 = 10e-9;
const TIMESTEP_S: f64 = 0.25e-9;
const PHASE_SAMPLES: usize = 1024;

fn baseline_frequency_hz() -> f64 {
    zapote_erc::power_entry::frequency_from_rf(16_200.0).expect("nominal RFREQ resolves")
}

fn solve_at(line_rms_v: f64, f_hz: f64, l_h: f64, limit_a: f64) -> pfc_losses::Moments {
    pfc_losses::moments(pfc_currents::Config {
        line_rms_v,
        input_rms_limit_a: limit_a,
        bus_v: BUS_V,
        inductance_h: l_h,
        switching_hz: f_hz,
        phase_samples: PHASE_SAMPLES,
    })
    .expect("valid CCM operating point")
}

/// Mirrors `pfc_candidates::LineModel`'s matched-power inversion using only the
/// public API: recover the ripple variance from a 15 A solve, then derive the
/// total input RMS that carries `power_w`, clamp to the ceiling, resolve.
fn matched_power_moments(line_rms_v: f64, f_hz: f64, l_h: f64, power_w: f64) -> pfc_losses::Moments {
    let reference = pfc_currents::calculate(pfc_currents::Config {
        line_rms_v,
        input_rms_limit_a: INPUT_RMS_LIMIT_A,
        bus_v: BUS_V,
        inductance_h: l_h,
        switching_hz: f_hz,
        phase_samples: PHASE_SAMPLES,
    })
    .expect("valid CCM reference point");
    let ripple_variance = INPUT_RMS_LIMIT_A.powi(2) - reference.fundamental_rms_a.powi(2);
    let fundamental = power_w / line_rms_v;
    let required_rms = (fundamental * fundamental + ripple_variance).sqrt();
    let effective_limit = required_rms.min(INPUT_RMS_LIMIT_A);
    solve_at(line_rms_v, f_hz, l_h, effective_limit)
}

struct Row {
    f_hz: f64,
    l_h: f64,
    moments: pfc_losses::Moments,
    overlap_w: f64,
    eoss_w: f64,
    conduction_w: f64,
    gate_w: f64,
    total_w: f64,
}

fn row(f_hz: f64, l_h: f64) -> Row {
    let m = matched_power_moments(LINE_RMS_V, f_hz, l_h, REQUESTED_POWER_W);
    let config = pfc_switching::Config {
        bus_v: BUS_V,
        switching_hz: f_hz,
        turn_on_current_a: m.mean_turn_on_a,
        turn_off_current_a: m.mean_turn_off_a,
        switch_rms_a: m.switch_rms_a,
        gate_bias_v: DRIVER_V,
        qg_c: QG_C,
        qgd_c: QGD_C,
        current_transfer_charge_c: CURRENT_TRANSFER_CHARGE_C,
        gate_plateau_v: PLATEAU_V,
        external_gate_r_ohm: EXTERNAL_GATE_R_OHM + DRIVER_SOURCE_R_OHM,
        intrinsic_gate_r_ohm: INTRINSIC_GATE_R_OHM,
        driver_source_peak_a: SOURCE_PEAK_A,
        driver_sink_peak_a: SINK_PEAK_A,
        coss_energy_j: EOSS_J,
        loop_inductance_h: LOOP_INDUCTANCE_H,
        rds_on_ohm: RDS_MAX_OHM,
        timestep_s: TIMESTEP_S,
    };
    let path = pfc_switching::GatePath {
        turn_on_external_r_ohm: EXTERNAL_GATE_R_OHM + DRIVER_SOURCE_R_OHM,
        turn_off_external_r_ohm: EXTERNAL_GATE_R_OHM + DRIVER_SINK_R_OHM,
    };
    let sim = pfc_switching::simulate_with_gate_path(config, path)
        .expect("baseline gate path simulates")
        .result;
    let total = sim.overlap_loss_w
        + sim.output_capacitance_loss_w
        + sim.conduction_loss_w
        + sim.gate_charge_loss_w;
    Row {
        f_hz,
        l_h,
        moments: m,
        overlap_w: sim.overlap_loss_w,
        eoss_w: sim.output_capacitance_loss_w,
        conduction_w: sim.conduction_loss_w,
        gate_w: sim.gate_charge_loss_w,
        total_w: total,
    }
}

#[test]
fn fixed_lf_product_makes_the_frequency_axis_monotone() {
    let f0 = baseline_frequency_hz();
    assert!(
        (f0 - 129_107.391_985_769_05).abs() < 0.01,
        "baseline frequency {f0} does not match the campaign baseline"
    );

    let frequencies = [30_000.0, 45_000.0, 65_000.0, 90_000.0, f0, 180_000.0];
    // The campaign rule: L(f) = L0 * f0 / f, so L * f is invariant.
    let rows: Vec<Row> = frequencies
        .iter()
        .map(|f| row(*f, L0_H * f0 / f))
        .collect();

    println!("\n=== campaign rule: L*f held at baseline (L0=180 uH @ {f0:.5} Hz) ===");
    println!(
        "{:>10} {:>10} {:>12} {:>10} {:>9} {:>8} {:>11} {:>8} {:>10}",
        "f (kHz)", "L (uH)", "Pin (W)", "Isw_rms", "overlap", "eoss", "conduction", "gate", "total"
    );
    for r in &rows {
        println!(
            "{:>10.2} {:>10.3} {:>12.4} {:>10.5} {:>9.4} {:>8.4} {:>11.5} {:>8.4} {:>10.4}",
            r.f_hz / 1e3,
            r.l_h * 1e6,
            r.moments.input_power_w,
            r.moments.switch_rms_a,
            r.overlap_w,
            r.eoss_w,
            r.conduction_w,
            r.gate_w,
            r.total_w
        );
    }

    // 1. The current waveform and every current moment are invariant at fixed L*f.
    let first = &rows[0];
    for r in &rows[1..] {
        assert!(
            (r.moments.input_power_w - first.moments.input_power_w).abs() < 1e-6,
            "input power moved with frequency at fixed L*f: {} vs {}",
            r.moments.input_power_w,
            first.moments.input_power_w
        );
        assert!(
            (r.moments.switch_rms_a - first.moments.switch_rms_a).abs() < 1e-9,
            "switch RMS moved with frequency at fixed L*f"
        );
        assert!(
            (r.moments.mean_turn_on_a - first.moments.mean_turn_on_a).abs() < 1e-9
                && (r.moments.mean_turn_off_a - first.moments.mean_turn_off_a).abs() < 1e-9,
            "switching currents moved with frequency at fixed L*f"
        );
    }

    // 2. Conduction follows the invariant waveform, so it is flat.
    for r in &rows[1..] {
        assert!(
            (r.conduction_w - first.conduction_w).abs() < 1e-6,
            "conduction loss moved with frequency at fixed L*f"
        );
    }

    // 3. The f-proportional terms scale, and the total is strictly increasing.
    for pair in rows.windows(2) {
        let (lo, hi) = (&pair[0], &pair[1]);
        assert!(
            hi.total_w > lo.total_w,
            "total loss is not strictly increasing in f at fixed L*f: {} -> {}",
            lo.total_w,
            hi.total_w
        );
        assert!(
            (hi.overlap_w / lo.overlap_w - hi.f_hz / lo.f_hz).abs() < 1e-6,
            "overlap is not f-proportional"
        );
    }

    println!(
        "\nVERDICT: at fixed L*f the waveform is invariant; only f-proportional switching terms \
         move, so total loss is strictly increasing in f. Minimum is the lowest swept frequency.\n"
    );
}

#[test]
fn fixed_inductance_changes_the_waveform_so_the_axis_is_not_tautological() {
    // Contrast case: if L is NOT scaled with f, the ripple and the solved
    // waveform do move, which is what the campaign rule deliberately removes.
    let f0 = baseline_frequency_hz();
    let rows: Vec<Row> = [30_000.0, 65_000.0, f0, 180_000.0]
        .iter()
        .map(|f| row(*f, L0_H))
        .collect();
    println!("\n=== contrast: L fixed at 180 uH while f varies ===");
    for r in &rows {
        println!(
            "{:>10.2} kHz  L {:>7.3} uH  Pin {:>10.4} W  Isw_rms {:>8.5}  total {:>9.4} W",
            r.f_hz / 1e3,
            r.l_h * 1e6,
            r.moments.input_power_w,
            r.moments.switch_rms_a,
            r.total_w
        );
    }
    let moved = rows
        .windows(2)
        .any(|p| (p[0].moments.input_power_w - p[1].moments.input_power_w).abs() > 1.0);
    assert!(
        moved,
        "fixed-L sweep should move the waveform; if it does not, the probe is wrong"
    );
}

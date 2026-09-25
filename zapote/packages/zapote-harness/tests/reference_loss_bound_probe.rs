//! Reference-bound probe: does the maintained model's switch-only loss fit
//! inside a real board's measured whole-board loss?
//!
//! A whole-board loss number bounds every individual device term from above.
//! It cannot validate a per-device switching-energy claim, but it CAN falsify
//! one: if the model attributes more loss to the boost switch alone than the
//! entire reference board dissipates, the model is inconsistent with that
//! board regardless of how the remaining terms divide.
//!
//! Reference: Infineon EVAL_2.5KW_CCM_4PIN / AN_201408_PL11_027 Rev 1.2,
//! SHA-256 fdbed1c55c3b36b71da7dd7b2938646f9f55f4cc2f36aeaa253178e3884d49ce,
//! captured by campaign task B-INF. Table 3 (p.20), 100 kHz.
//!
//! Device parameters are the source-captured IPZ60R040C7 values (campaign task
//! K-SILICON, PDF SHA-256 b1ea13f87f17a27336ea5a25ef01bad2d154c54140d8a4b1307e5f0289d6c089).
//! They are 0/+10 V datasheet typicals; the model is therefore run at 10 V
//! gate bias, which is the device's own sourced condition, not contract C1's
//! 12 V nominal. This is a bound check, not a C1 comparison.
//!
//! Run: cargo test -p zapote-harness --test reference_loss_bound_probe -- --nocapture

use zapote_erc::{pfc_currents, pfc_losses, pfc_switching};

/// Source-captured IPZ60R040C7 parameters, each at its datasheet condition.
struct Device {
    id: &'static str,
    qg_c: f64,
    qgd_c: f64,
    plateau_v: f64,
    intrinsic_gate_r_ohm: f64,
    eoss_j: f64,
    rds_max_ohm: f64,
}

/// IPZ60R040C7: qg/qgd/plateau at VDD=400 V, ID=24.9 A, VGS 0->10 V (p.6 Table 6);
/// Rg at 1 MHz (p.6 Table 4); Eoss at VDS=400 V (p.11 Diag. 15);
/// Rds(max) at VGS=10 V, ID=24.9 A, Tj=25 C (p.6 Table 4).
const IPZ60R040C7: Device = Device {
    id: "IPZ60R040C7",
    qg_c: 107e-9,
    qgd_c: 36e-9,
    plateau_v: 5.0,
    intrinsic_gate_r_ohm: 0.77,
    eoss_j: 12.6e-6,
    rds_max_ohm: 0.040,
};

/// Board driver 1EDI60N12AF: 6 A headline. Treated as a bound on the driver
/// stage, not as a measured output impedance.
const BOARD_DRIVER_PEAK_A: f64 = 6.0;
/// The document names three different populated gate resistances (3.3 / 10 / 20 ohm).
const BOARD_GATE_R_OHMS: [f64; 3] = [3.3, 10.0, 20.0];
const BOARD_GATE_BIAS_V: f64 = 10.0;
/// Unknown for the board; the campaign baseline assumption is reused and flagged.
const LOOP_INDUCTANCE_H: f64 = 10e-9;
const TIMESTEP_S: f64 = 0.25e-9;
const PHASE_SAMPLES: usize = 1024;
const BOARD_L_H: f64 = 600e-6;
const BOARD_F_HZ: f64 = 100_000.0;

/// One published board operating point (Table 3, p.20).
struct BoardPoint {
    label: &'static str,
    line_rms_v: f64,
    input_rms_a: f64,
    bus_v: f64,
    measured_input_w: f64,
    measured_output_w: f64,
}

const BOARD_POINTS: [BoardPoint; 3] = [
    BoardPoint { label: "230 Vac full", line_rms_v: 229.56, input_rms_a: 11.178, bus_v: 401.15, measured_input_w: 2561.5, measured_output_w: 2500.9 },
    BoardPoint { label: "230 Vac ~1.8kW", line_rms_v: 229.72, input_rms_a: 7.807, bus_v: 401.24, measured_input_w: 1789.0, measured_output_w: 1753.2 },
    BoardPoint { label: "85 Vac max", line_rms_v: 84.31, input_rms_a: 15.215, bus_v: 401.34, measured_input_w: 1280.2, measured_output_w: 1197.6 },
];

fn moments(line_rms_v: f64, limit_a: f64, bus_v: f64, l_h: f64, f_hz: f64) -> pfc_losses::Moments {
    pfc_losses::moments(pfc_currents::Config {
        line_rms_v,
        input_rms_limit_a: limit_a,
        bus_v,
        inductance_h: l_h,
        switching_hz: f_hz,
        phase_samples: PHASE_SAMPLES,
    })
    .expect("board operating point is a valid CCM point")
}

struct SwitchLoss {
    overlap_w: f64,
    eoss_w: f64,
    conduction_w: f64,
    gate_w: f64,
    total_w: f64,
}

fn switch_loss(dev: &Device, m: &pfc_losses::Moments, bus_v: f64, f_hz: f64, gate_r_ohm: f64) -> SwitchLoss {
    let config = pfc_switching::Config {
        bus_v,
        switching_hz: f_hz,
        turn_on_current_a: m.mean_turn_on_a,
        turn_off_current_a: m.mean_turn_off_a,
        switch_rms_a: m.switch_rms_a,
        gate_bias_v: BOARD_GATE_BIAS_V,
        qg_c: dev.qg_c,
        qgd_c: dev.qgd_c,
        current_transfer_charge_c: 10e-9,
        gate_plateau_v: dev.plateau_v,
        external_gate_r_ohm: gate_r_ohm,
        intrinsic_gate_r_ohm: dev.intrinsic_gate_r_ohm,
        driver_source_peak_a: BOARD_DRIVER_PEAK_A,
        driver_sink_peak_a: BOARD_DRIVER_PEAK_A,
        coss_energy_j: dev.eoss_j,
        loop_inductance_h: LOOP_INDUCTANCE_H,
        rds_on_ohm: dev.rds_max_ohm,
        timestep_s: TIMESTEP_S,
    };
    let path = pfc_switching::GatePath {
        turn_on_external_r_ohm: gate_r_ohm,
        turn_off_external_r_ohm: gate_r_ohm,
    };
    let sim = pfc_switching::simulate_with_gate_path(config, path)
        .expect("board gate path simulates")
        .result;
    SwitchLoss {
        overlap_w: sim.overlap_loss_w,
        eoss_w: sim.output_capacitance_loss_w,
        conduction_w: sim.conduction_loss_w,
        gate_w: sim.gate_charge_loss_w,
        total_w: sim.overlap_loss_w + sim.output_capacitance_loss_w + sim.conduction_loss_w + sim.gate_charge_loss_w,
    }
}

#[test]
fn model_switch_loss_fits_inside_the_reference_board_total() {
    println!("\n=== model switch-only loss for IPZ60R040C7 at the EVAL_2.5KW board points ===");
    println!(
        "{:<16} {:>10} {:>10} {:>12} {:>9} {:>9}",
        "board point", "Pin(meas)", "Ploss(meas)", "model R", "model switch", "share"
    );
    let mut any_violation = false;
    for p in &BOARD_POINTS {
        let m = moments(p.line_rms_v, p.input_rms_a, p.bus_v, BOARD_L_H, BOARD_F_HZ);
        let board_loss = p.measured_input_w - p.measured_output_w;
        for r in BOARD_GATE_R_OHMS {
            let s = switch_loss(&IPZ60R040C7, &m, p.bus_v, BOARD_F_HZ, r);
            let share = s.total_w / board_loss;
            let flag = if s.total_w > board_loss { "  <-- EXCEEDS BOARD TOTAL" } else { "" };
            if s.total_w > board_loss { any_violation = true; }
            println!(
                "{:<16} {:>10.1} {:>10.2} {:>11.1}ohms {:>9.2} {:>8.1}%{}",
                p.label, p.measured_input_w, board_loss, r, s.total_w, share * 100.0, flag
            );
            println!(
                "                 overlap {:>7.2}  eoss {:>6.2}  conduction {:>6.2}  gate {:>6.2}   (Pin_model {:.1})",
                s.overlap_w, s.eoss_w, s.conduction_w, s.gate_w, m.input_power_w
            );
        }
    }

    // Contrast: the same device at C1's own nominal conditions (not a board
    // assertion -- a different line, power and frequency).
    let c1 = moments(120.0, 15.0, 400.0, 180e-6, 129_107.391_985_769_05);
    let s = switch_loss(&IPZ60R040C7, &c1, 400.0, 129_107.391_985_769_05, 4.7);
    println!(
        "\ncontrast: IPZ60R040C7 at C1 nominal (120 V/15 A/400 V/129 kHz/180 uH, 10 V drive, 4.7 ohm):"
    );
    println!(
        "   overlap {:.2}  eoss {:.2}  conduction {:.2}  gate {:.2}  TOTAL {:.2} W",
        s.overlap_w, s.eoss_w, s.conduction_w, s.gate_w, s.total_w
    );
    println!(
        "   (baseline IPW65R045C7 at the same point was 45.5023 W; the C7-at-10V parameter set is not a C1-matched comparison)\n"
    );

    if any_violation {
        println!("VERDICT: at least one board point has model switch-only loss exceeding the measured whole-board loss.");
    } else {
        println!("VERDICT: model switch-only loss fits inside every measured whole-board loss (necessary, not sufficient, consistency).");
    }
}

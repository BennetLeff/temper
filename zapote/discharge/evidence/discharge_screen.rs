//! Rev38 discharge arithmetic screen. Run with:
//! rustc --edition=2021 --test zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-screen && /tmp/zapote-discharge-screen
//! This is a source snapshot and historical 34 V / 60 s comparison, not a service-safety proof.

const VD_C_NOM: f64 = 22.47e-6;
const VD_C_MAX_INITIAL: f64 = VD_C_NOM * 1.10;
const VB_C_NOM: f64 = 2240e-6;
const VB_C_MAX_INITIAL: f64 = VB_C_NOM * 1.20;
const F2_DIVIDER: f64 = 4.0 * 200e3 + 187e3 + 200.0 + 5.62e3;
const PFC_VSENSE: f64 = 5.0 * 200e3 + 13e3;
const BANK_BLEEDER: f64 = 3.0 * 150e3;

#[derive(Clone, Copy)]
struct Paths {
    vd_detector: bool,
    vd_vsense: bool,
    vb_detector: bool,
    vb_bleeder: bool,
}

impl Paths {
    const fn intact() -> Self {
        Self {
            vd_detector: true,
            vd_vsense: true,
            vb_detector: true,
            vb_bleeder: true,
        }
    }
}

fn parallel_resistance(paths: &[Option<f64>]) -> Option<f64> {
    let conductance: f64 = paths.iter().flatten().map(|r| 1.0 / r).sum();
    (conductance > 0.0).then_some(1.0 / conductance)
}

fn vd_resistance(paths: Paths) -> Option<f64> {
    parallel_resistance(&[
        paths.vd_detector.then_some(F2_DIVIDER),
        paths.vd_vsense.then_some(PFC_VSENSE),
    ])
}

fn vb_resistance(paths: Paths) -> Option<f64> {
    parallel_resistance(&[
        paths.vb_detector.then_some(F2_DIVIDER),
        paths.vb_bleeder.then_some(BANK_BLEEDER),
    ])
}

fn discharge_seconds(c: f64, r: Option<f64>, initial_v: f64, target_v: f64) -> f64 {
    assert!(c > 0.0 && initial_v > target_v && target_v > 0.0);
    r.map_or(f64::INFINITY, |r| c * r * (initial_v / target_v).ln())
}

fn stored_joules(c: f64, voltage: f64) -> f64 {
    0.5 * c * voltage * voltage
}

fn largest_resistance_for_time(c: f64, initial_v: f64, target_v: f64, seconds: f64) -> f64 {
    seconds / (c * (initial_v / target_v).ln())
}

#[test]
fn f2_open_keeps_two_distinct_energy_islands() {
    let p = Paths::intact();
    // There is no F2 path in either equation. The return is common HOT0.
    assert!((stored_joules(VD_C_NOM, 400.0) - 1.7976).abs() < 1e-9);
    assert!((stored_joules(VB_C_NOM, 400.0) - 179.2).abs() < 1e-9);
    assert!((vd_resistance(p).unwrap() - 501_404.24365).abs() < 0.01);
    assert!((vb_resistance(p).unwrap() - 309_649.85237).abs() < 0.01);
}

#[test]
fn two_open_vd_ladders_leave_no_resistor_after_f2_opens() {
    let p = Paths {
        vd_detector: false,
        vd_vsense: false,
        ..Paths::intact()
    };
    assert!(vd_resistance(p).is_none());
    assert!(discharge_seconds(VD_C_NOM, vd_resistance(p), 400.0, 34.0).is_infinite());
    assert!(vb_resistance(p).is_some()); // VB health cannot stand in for VD.
}

#[test]
fn a_single_open_bank_bleeder_is_not_a_fast_discharge() {
    let p = Paths {
        vb_bleeder: false,
        ..Paths::intact()
    };
    assert!((vb_resistance(p).unwrap() - F2_DIVIDER).abs() < 1e-9);
    assert!(discharge_seconds(VB_C_NOM, vb_resistance(p), 400.0, 34.0) > 5400.0);
    assert!(vd_resistance(p).is_some());
}

#[test]
fn historical_60_second_screen_needs_much_lower_bank_resistance() {
    // This screen is NOT an adopted Rev38 threshold or a selected resistor.
    let r_limit = largest_resistance_for_time(VB_C_MAX_INITIAL, 400.0, 34.0, 60.0);
    assert!((r_limit - 9054.964).abs() < 0.01);
    assert!(400.0 * 400.0 / r_limit > 17.6); // energized continuous watts
    assert!(stored_joules(VB_C_MAX_INITIAL, 400.0) > 215.0); // pulse energy
    assert!(
        discharge_seconds(
            VB_C_MAX_INITIAL,
            vb_resistance(Paths::intact()),
            400.0,
            34.0
        ) > 2000.0
    );
    let mut vd_single = Paths::intact();
    vd_single.vd_detector = false;
    assert!(discharge_seconds(VD_C_MAX_INITIAL, vd_resistance(vd_single), 400.0, 34.0) > 60.0);
}

#[test]
fn inverter_capacitance_changes_bank_energy_and_may_become_separate() {
    let inverter_c = 10e-6; // example parameter, not a selected part
    let initial_v = 400.0;
    assert!(stored_joules(VB_C_NOM + inverter_c, initial_v) > stored_joules(VB_C_NOM, initial_v));
    // If disconnected from VB while charged, no Rev38 path exists on its side.
    let inverter_side_path: Option<f64> = None;
    assert!(discharge_seconds(inverter_c, inverter_side_path, initial_v, 34.0).is_infinite());
}

#[test]
fn powered_mains_invalidates_an_unforced_rc_decay_claim() {
    // The Rev38 NTC/bridge/inductor/diode path can supply VD with AUX off.
    // A positive source current means passive RC decay is not an upper bound.
    let source_current_a = 0.001; // illustrative only; no Rev38 source waveform is measured
    let resistor_current_a = 400.0 / vd_resistance(Paths::intact()).unwrap();
    assert!(source_current_a > resistor_current_a);
}

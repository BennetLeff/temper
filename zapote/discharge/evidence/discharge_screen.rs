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
// Candidate values from Vishay TNPW1206 e3 and RH50 families, not source selections.
const VD_STRING: f64 = 4.0 * 200e3;
const VB_BRANCH: f64 = 2.0 * 7.5e3;
const CANDIDATE_TOLERANCE: f64 = 0.01;

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

/// Conservative delay plus RC: gives no credit for passive drain before the NC contact closes.
fn delayed_discharge_seconds(
    c: f64,
    switched_resistance: Option<f64>,
    initial_v: f64,
    target_v: f64,
    release_delay_s: f64,
) -> f64 {
    assert!(release_delay_s >= 0.0);
    release_delay_s + discharge_seconds(c, switched_resistance, initial_v, target_v)
}

/// A live mains source invalidates the isolated-capacitor RC result.
fn qualified_decay_seconds(
    mains_isolated: bool,
    c: f64,
    resistance: Option<f64>,
    initial_v: f64,
    target_v: f64,
    delay_s: f64,
) -> Option<f64> {
    mains_isolated.then(|| delayed_discharge_seconds(c, resistance, initial_v, target_v, delay_s))
}

fn vd_candidate_resistance(one_string_open: bool) -> f64 {
    let surviving_strings = if one_string_open { 1.0 } else { 2.0 };
    VD_STRING * (1.0 + CANDIDATE_TOLERANCE) / surviving_strings
}

fn vb_candidate_resistance(one_branch_open: bool) -> f64 {
    let surviving_branches = if one_branch_open { 1.0 } else { 2.0 };
    VB_BRANCH * (1.0 + CANDIDATE_TOLERANCE) / surviving_branches
}

// Resistor short in one 2x7.5k branch: its other resistor is across full V,
// while the intact branch remains 15k. Neither short bypasses the relay.
fn vb_resistor_short_power_per_survivor(voltage: f64) -> f64 {
    voltage * voltage / 7.5e3
}

#[cfg(not(test))]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 6 {
        eprintln!(
            "usage: discharge_screen <initial_V> <target_V> <target_s> <direct_inverter_uF> <release_delay_s>"
        );
        std::process::exit(2);
    }
    let parse = |index: usize| args[index].parse::<f64>().expect("finite numeric argument");
    let (v0, target, time_limit, inverter_uf, delay) =
        (parse(1), parse(2), parse(3), parse(4), parse(5));
    assert!([v0, target, time_limit, inverter_uf, delay]
        .iter()
        .all(|x| x.is_finite()));
    assert!(v0 > target && target > 0.0 && time_limit > 0.0 && inverter_uf >= 0.0 && delay >= 0.0);
    let vb_c = VB_C_MAX_INITIAL + inverter_uf * 1e-6;
    println!("CONDITIONAL SCREEN, not an adopted product requirement");
    println!(
        "source Cmax: VD {:.3} uF, VB {:.1} uF; direct inverter C {:.3} uF",
        VD_C_MAX_INITIAL * 1e6,
        VB_C_MAX_INITIAL * 1e6,
        inverter_uf
    );
    println!(
        "inputs: {:.1} -> {:.1} V by {:.1} s; NC release allowance {:.3} s",
        v0, target, time_limit, delay
    );
    let existing = Paths::intact();
    println!(
        "existing Rev38 F2-open RC: VD {:.2} s, VB {:.2} s",
        discharge_seconds(VD_C_MAX_INITIAL, vd_resistance(existing), v0, target),
        discharge_seconds(vb_c, vb_resistance(existing), v0, target)
    );
    println!(
        "VB total R bound for input time (zero delay): {:.2} ohm",
        largest_resistance_for_time(vb_c, v0, target, time_limit)
    );
    for (label, c, resistance, activation_delay) in [
        (
            "VD, both passive strings",
            VD_C_MAX_INITIAL,
            vd_candidate_resistance(false),
            0.0,
        ),
        (
            "VD, one string open",
            VD_C_MAX_INITIAL,
            vd_candidate_resistance(true),
            0.0,
        ),
        (
            "VB, two active branches",
            vb_c,
            vb_candidate_resistance(false),
            delay,
        ),
        (
            "VB, one branch open",
            vb_c,
            vb_candidate_resistance(true),
            delay,
        ),
    ] {
        let seconds = delayed_discharge_seconds(c, Some(resistance), v0, target, activation_delay);
        println!(
            "{label}: {seconds:.2} s; {}",
            if seconds <= time_limit {
                "within input time"
            } else {
                "exceeds input time"
            }
        );
    }
    // With F2 closed, both capacitors start at the same voltage and share
    // both candidate resistor networks. This is a different timing case from
    // F2-open VB alone.
    let coupled_c = vb_c + VD_C_MAX_INITIAL;
    let coupled_r = parallel_resistance(&[
        Some(vb_candidate_resistance(false)),
        Some(vd_candidate_resistance(false)),
    ]);
    println!(
        "F2 closed, VB+VD candidate paths: {:.2} s",
        delayed_discharge_seconds(coupled_c, coupled_r, v0, target, delay)
    );
    println!(
        "VB isolated energy at input V: {:.2} J",
        stored_joules(vb_c, v0)
    );
    println!(
        "VB fast path while mains attached: {:.2} W total at input V; no RC completion claim",
        v0 * v0 / (VB_BRANCH / 2.0)
    );
    println!(
        "single-short VB resistor: {:.2} W in the surviving series resistor",
        vb_resistor_short_power_per_survivor(v0)
    );
    assert!(qualified_decay_seconds(
        false,
        vb_c,
        Some(vb_candidate_resistance(false)),
        v0,
        target,
        delay
    )
    .is_none());
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
    assert!(qualified_decay_seconds(
        false,
        VB_C_MAX_INITIAL,
        Some(vb_candidate_resistance(false)),
        400.0,
        34.0,
        1.0
    )
    .is_none());
}

#[test]
fn candidate_strings_remain_separate_with_f2_open() {
    let target = 34.0; // historical sensitivity input only
    let vd_single_open = delayed_discharge_seconds(
        VD_C_MAX_INITIAL,
        Some(vd_candidate_resistance(true)),
        400.0,
        target,
        0.0,
    );
    let vb_nominal = delayed_discharge_seconds(
        VB_C_MAX_INITIAL,
        Some(vb_candidate_resistance(false)),
        400.0,
        target,
        1.0,
    );
    assert!(vd_single_open < 60.0);
    assert!(vb_nominal < 60.0);
    // The bank path never substitutes for VD, nor VD for the bank.
    assert_ne!(
        vd_candidate_resistance(true),
        vb_candidate_resistance(false)
    );
}

#[test]
fn one_open_vb_fast_resistor_or_contact_fails_historical_time() {
    let c = VB_C_MAX_INITIAL;
    assert!(
        delayed_discharge_seconds(c, Some(vb_candidate_resistance(true)), 400.0, 34.0, 1.0) > 90.0
    );
    assert!(
        delayed_discharge_seconds(c, vb_resistance(Paths::intact()), 400.0, 34.0, 0.0) > 2000.0
    );
}

#[test]
fn single_short_in_candidate_string_does_not_shunt_the_bank() {
    // One 7.5k RH50 short leaves at least 7.5k in that branch; the other
    // 15k branch remains. The surviving resistor sees the full bus.
    let shorted_branch = 7.5e3;
    let still_limited = parallel_resistance(&[Some(shorted_branch), Some(VB_BRANCH)]).unwrap();
    assert!((still_limited - 5e3).abs() < 1e-9);
    assert!((vb_resistor_short_power_per_survivor(450.0) - 27.0).abs() < 1e-9);
    // Source-listed RH50 mounted rating at 70 C is 40 W, unmounted 9.6 W.
    assert!(vb_resistor_short_power_per_survivor(450.0) < 40.0);
    assert!(vb_resistor_short_power_per_survivor(450.0) > 9.6);
}

#[test]
fn single_short_in_vd_string_stays_below_element_voltage_screen() {
    let remaining = 3.0;
    assert!(450.0 / remaining < 200.0); // TNPW1206 e3 operating voltage
    assert!(450.0 * 450.0 / (remaining * 200e3) / remaining < 0.4);
}

#[test]
fn direct_inverter_capacitance_consumes_timing_margin() {
    let base = delayed_discharge_seconds(
        VB_C_MAX_INITIAL,
        Some(vb_candidate_resistance(false)),
        400.0,
        34.0,
        1.0,
    );
    let added = delayed_discharge_seconds(
        VB_C_MAX_INITIAL + 100e-6,
        Some(vb_candidate_resistance(false)),
        400.0,
        34.0,
        1.0,
    );
    assert!(added > base);
    assert!(
        qualified_decay_seconds(true, 100e-6, None, 400.0, 34.0, 0.0)
            .unwrap()
            .is_infinite()
    ); // disconnected input C has no source-declared path
}

#[test]
fn f2_closed_coupled_capacitance_needs_vd_paths_for_the_edge_screen() {
    let vb_c = VB_C_MAX_INITIAL + 100e-6;
    let coupled_c = vb_c + VD_C_MAX_INITIAL;
    let with_vd_path = parallel_resistance(&[
        Some(vb_candidate_resistance(false)),
        Some(vd_candidate_resistance(false)),
    ]);
    let without_vd_path = Some(vb_candidate_resistance(false));
    let joined_time = delayed_discharge_seconds(coupled_c, with_vd_path, 450.0, 34.0, 5.0);
    let joined_without_vd = delayed_discharge_seconds(coupled_c, without_vd_path, 450.0, 34.0, 5.0);
    assert!((joined_time - 59.01899).abs() < 0.001);
    assert!(joined_without_vd > 60.0);
}

//! Rev38 discharge arithmetic screen. Run with:
//! rustc --edition=2021 --test zapote/discharge/evidence/discharge_screen.rs -o /tmp/zapote-discharge-screen && /tmp/zapote-discharge-screen
//! The --case gate is a source-locked conditional screen, not a service-safety proof.

use std::collections::HashMap;
use std::str::FromStr;

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
    if args.len() == 3 && args[1] == "--case" {
        let source_check = std::process::Command::new("shasum")
            .args([
                "-a",
                "256",
                "-c",
                "zapote/discharge/evidence/source-inputs.sha256",
            ])
            .output()
            .expect("shasum must be available");
        if !source_check.status.success() {
            eprintln!("REJECT: Rev38 source hash drift or missing source");
            eprintln!("{}", String::from_utf8_lossy(&source_check.stdout));
            std::process::exit(1);
        }
        let input = std::fs::read_to_string(&args[2]).expect("read scenario file");
        match GateCase::parse(&input) {
            Ok(case) => {
                let result = evaluate(&case);
                println!("{}", result.render());
                std::process::exit(match result.verdict {
                    Verdict::Conditional => 0,
                    Verdict::Rejected => 1,
                    Verdict::Indeterminate => 2,
                });
            }
            Err(message) => {
                eprintln!("REJECT: invalid or incomplete scenario: {message}");
                std::process::exit(1);
            }
        }
    }
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Verdict {
    Conditional,
    Rejected,
    Indeterminate,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Fault {
    None,
    VdStringOpen,
    VdResistorShort,
    VbResistorOpen,
    VbResistorShort,
    ContactStuckOpen,
    ContactStuckClosed,
    CoilStuckEnergized,
    VdSenseOpen,
    VbSenseOpen,
}

impl FromStr for Fault {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "none" => Ok(Self::None),
            "vd_string_open" => Ok(Self::VdStringOpen),
            "vd_resistor_short" => Ok(Self::VdResistorShort),
            "vb_resistor_open" => Ok(Self::VbResistorOpen),
            "vb_resistor_short" => Ok(Self::VbResistorShort),
            "contact_stuck_open" => Ok(Self::ContactStuckOpen),
            "contact_stuck_closed" => Ok(Self::ContactStuckClosed),
            "coil_stuck_energized" => Ok(Self::CoilStuckEnergized),
            "vd_sense_open" => Ok(Self::VdSenseOpen),
            "vb_sense_open" => Ok(Self::VbSenseOpen),
            _ => Err(format!("unknown fault {s}")),
        }
    }
}

#[derive(Clone, Debug)]
struct GateCase {
    initial_v: f64,
    max_v: f64,
    target_v: f64,
    target_s: f64,
    vd_cap_uf: f64,
    vb_cap_uf: f64,
    inverter_direct_uf: f64,
    inverter_detached_uf: f64,
    inverter_detached_path_ohm: f64,
    f2_closed: bool,
    mains_isolated: bool,
    aux_lost: bool,
    discharge_requested: bool,
    fan_available: bool,
    fan_supply_independent_verified: bool,
    contact_release_max_s: f64,
    contact_pickup_max_s: f64,
    coil_supply_min_v: f64,
    coil_supply_max_v: f64,
    coil_loss_residual_max_v: f64,
    coil_pickup_required_v: f64,
    coil_hold_required_v: f64,
    coil_release_required_below_v: f64,
    coil_absolute_max_v: f64,
    coil_recovery_cycles: u32,
    coil_recovery_period_min_s: f64,
    coil_brownout_dwell_max_s: f64,
    resistor_tolerance_pct: f64,
    resistor_drift_pct: f64,
    fault: Fault,
    single_fault_fast_deadline: bool,
    criteria_adopted: bool,
    exact_parts_verified: bool,
    contact_dc_life_verified: bool,
    coil_timing_verified: bool,
    installed_thermal_verified: bool,
    fan_off_thermal_verified: bool,
    fault_detection_verified: bool,
    service_measurement_verified: bool,
    f2_continuity_verified: bool,
    deliberate_rearm_verified: bool,
    restart_claim: bool,
    residual_vd_v: f64,
    residual_vb_v: f64,
    claim_deadline_while_mains_live: bool,
}

impl GateCase {
    fn parse(input: &str) -> Result<Self, String> {
        let mut fields = HashMap::new();
        for (line_index, raw) in input.lines().enumerate() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let (key, value) = line
                .split_once('=')
                .ok_or_else(|| format!("line {} needs key=value", line_index + 1))?;
            let key = key.trim().to_owned();
            if fields
                .insert(key.clone(), value.trim().to_owned())
                .is_some()
            {
                return Err(format!("duplicate key {key}"));
            }
        }
        fn take<T: FromStr>(fields: &mut HashMap<String, String>, key: &str) -> Result<T, String> {
            let value = fields.remove(key).ok_or_else(|| format!("missing {key}"))?;
            value.parse().map_err(|_| format!("invalid {key}={value}"))
        }
        let case = Self {
            initial_v: take(&mut fields, "initial_v")?,
            max_v: take(&mut fields, "max_v")?,
            target_v: take(&mut fields, "target_v")?,
            target_s: take(&mut fields, "target_s")?,
            vd_cap_uf: take(&mut fields, "vd_cap_uf")?,
            vb_cap_uf: take(&mut fields, "vb_cap_uf")?,
            inverter_direct_uf: take(&mut fields, "inverter_direct_uf")?,
            inverter_detached_uf: take(&mut fields, "inverter_detached_uf")?,
            inverter_detached_path_ohm: take(&mut fields, "inverter_detached_path_ohm")?,
            f2_closed: take(&mut fields, "f2_closed")?,
            mains_isolated: take(&mut fields, "mains_isolated")?,
            aux_lost: take(&mut fields, "aux_lost")?,
            discharge_requested: take(&mut fields, "discharge_requested")?,
            fan_available: take(&mut fields, "fan_available")?,
            fan_supply_independent_verified: take(&mut fields, "fan_supply_independent_verified")?,
            contact_release_max_s: take(&mut fields, "contact_release_max_s")?,
            contact_pickup_max_s: take(&mut fields, "contact_pickup_max_s")?,
            coil_supply_min_v: take(&mut fields, "coil_supply_min_v")?,
            coil_supply_max_v: take(&mut fields, "coil_supply_max_v")?,
            coil_loss_residual_max_v: take(&mut fields, "coil_loss_residual_max_v")?,
            coil_pickup_required_v: take(&mut fields, "coil_pickup_required_v")?,
            coil_hold_required_v: take(&mut fields, "coil_hold_required_v")?,
            coil_release_required_below_v: take(&mut fields, "coil_release_required_below_v")?,
            coil_absolute_max_v: take(&mut fields, "coil_absolute_max_v")?,
            coil_recovery_cycles: take(&mut fields, "coil_recovery_cycles")?,
            coil_recovery_period_min_s: take(&mut fields, "coil_recovery_period_min_s")?,
            coil_brownout_dwell_max_s: take(&mut fields, "coil_brownout_dwell_max_s")?,
            resistor_tolerance_pct: take(&mut fields, "resistor_tolerance_pct")?,
            resistor_drift_pct: take(&mut fields, "resistor_drift_pct")?,
            fault: take(&mut fields, "fault")?,
            single_fault_fast_deadline: take(&mut fields, "single_fault_fast_deadline")?,
            criteria_adopted: take(&mut fields, "criteria_adopted")?,
            exact_parts_verified: take(&mut fields, "exact_parts_verified")?,
            contact_dc_life_verified: take(&mut fields, "contact_dc_life_verified")?,
            coil_timing_verified: take(&mut fields, "coil_timing_verified")?,
            installed_thermal_verified: take(&mut fields, "installed_thermal_verified")?,
            fan_off_thermal_verified: take(&mut fields, "fan_off_thermal_verified")?,
            fault_detection_verified: take(&mut fields, "fault_detection_verified")?,
            service_measurement_verified: take(&mut fields, "service_measurement_verified")?,
            f2_continuity_verified: take(&mut fields, "f2_continuity_verified")?,
            deliberate_rearm_verified: take(&mut fields, "deliberate_rearm_verified")?,
            restart_claim: take(&mut fields, "restart_claim")?,
            residual_vd_v: take(&mut fields, "residual_vd_v")?,
            residual_vb_v: take(&mut fields, "residual_vb_v")?,
            claim_deadline_while_mains_live: take(&mut fields, "claim_deadline_while_mains_live")?,
        };
        if !fields.is_empty() {
            return Err(format!(
                "unknown keys: {:?}",
                fields.keys().collect::<Vec<_>>()
            ));
        }
        Ok(case)
    }
}

struct GateResult {
    verdict: Verdict,
    rejects: Vec<String>,
    unknowns: Vec<String>,
    vd_seconds: Option<f64>,
    vb_seconds: Option<f64>,
    coupled_seconds: Option<f64>,
    inverter_seconds: Option<f64>,
    vb_continuous_w: f64,
    vb_peak_resistor_w: f64,
    vb_energy_j: f64,
    vb_peak_resistor_j_upper: f64,
}

impl GateResult {
    fn render(&self) -> String {
        let mut lines = vec![format!(
            "{:?}: source-locked conditional engineering screen",
            self.verdict
        )];
        for (name, value) in [
            ("VD independent decay s", self.vd_seconds),
            ("VB independent decay s", self.vb_seconds),
            ("F2-closed coupled decay s", self.coupled_seconds),
            ("detached inverter decay s", self.inverter_seconds),
        ] {
            lines.push(format!(
                "{name}: {}",
                value.map_or("UNBOUNDED/NOT APPLICABLE".to_owned(), |v| format!("{v:.3}"))
            ));
        }
        lines.push(format!(
            "VB candidate at max V: {:.3} W path load (maintained only if a source reaches VB); {:.3} W peak in one resistor; {:.3} J bank+direct-inverter stored; {:.3} J one-resistor stored-energy upper bound (excludes mains input)",
            self.vb_continuous_w, self.vb_peak_resistor_w, self.vb_energy_j, self.vb_peak_resistor_j_upper
        ));
        for reason in &self.rejects {
            lines.push(format!("REJECT: {reason}"));
        }
        for reason in &self.unknowns {
            lines.push(format!("INDETERMINATE: {reason}"));
        }
        lines.join("\n")
    }
}

fn evaluate(c: &GateCase) -> GateResult {
    let mut r = GateResult {
        verdict: Verdict::Indeterminate,
        rejects: Vec::new(),
        unknowns: Vec::new(),
        vd_seconds: None,
        vb_seconds: None,
        coupled_seconds: None,
        inverter_seconds: None,
        vb_continuous_w: 0.0,
        vb_peak_resistor_w: 0.0,
        vb_energy_j: 0.0,
        vb_peak_resistor_j_upper: 0.0,
    };
    let numeric = [
        c.initial_v,
        c.max_v,
        c.target_v,
        c.target_s,
        c.vd_cap_uf,
        c.vb_cap_uf,
        c.inverter_direct_uf,
        c.inverter_detached_uf,
        c.inverter_detached_path_ohm,
        c.contact_release_max_s,
        c.contact_pickup_max_s,
        c.coil_supply_min_v,
        c.coil_supply_max_v,
        c.coil_loss_residual_max_v,
        c.coil_pickup_required_v,
        c.coil_hold_required_v,
        c.coil_release_required_below_v,
        c.coil_absolute_max_v,
        c.coil_recovery_period_min_s,
        c.coil_brownout_dwell_max_s,
        c.resistor_tolerance_pct,
        c.resistor_drift_pct,
        c.residual_vd_v,
        c.residual_vb_v,
    ];
    if numeric.iter().any(|x| !x.is_finite() || *x < 0.0)
        || c.target_v <= 0.0
        || c.target_v >= c.initial_v
        || c.max_v < c.initial_v
        || c.target_s <= 0.0
        || c.vd_cap_uf <= 0.0
        || c.vb_cap_uf <= 0.0
        || c.coil_supply_min_v <= 0.0
        || c.coil_pickup_required_v <= 0.0
        || c.coil_hold_required_v <= 0.0
        || c.coil_release_required_below_v <= 0.0
        || c.coil_absolute_max_v <= 0.0
        || c.coil_supply_min_v > c.coil_supply_max_v
        || c.coil_loss_residual_max_v > c.coil_supply_max_v
        || c.resistor_tolerance_pct + c.resistor_drift_pct >= 100.0
    {
        r.rejects
            .push("invalid or inconsistent numeric bounds".into());
        r.verdict = Verdict::Rejected;
        return r;
    }
    if c.vd_cap_uf + 1e-9 < VD_C_MAX_INITIAL * 1e6 || c.vb_cap_uf + 1e-9 < VB_C_MAX_INITIAL * 1e6 {
        r.rejects
            .push("entered capacitance understates committed Rev38 tolerance-high minimum".into());
        r.verdict = Verdict::Rejected;
        return r;
    }
    if !c.criteria_adopted {
        r.unknowns
            .push("product voltage/time criteria have not been adopted".into());
    }
    if !c.exact_parts_verified {
        r.unknowns
            .push("exact part variants and installed circuit are unverified".into());
    }
    if !c.contact_dc_life_verified {
        r.unknowns
            .push("contact DC switching and life for the actual waveform are unverified".into());
    }
    if !c.coil_timing_verified {
        r.unknowns
            .push("coil pickup, hold, release and brownout timing bounds are unverified".into());
    }
    if !c.installed_thermal_verified {
        r.unknowns
            .push("installed chassis thermal impedance and duty are unverified".into());
    }
    if !c.service_measurement_verified {
        r.unknowns
            .push("independent service voltage measurement is unverified".into());
    }

    let delta = (c.resistor_tolerance_pct + c.resistor_drift_pct) / 100.0;
    let high = 1.0 + delta;
    let low = 1.0 - delta;
    let vd_nom = match c.fault {
        Fault::VdStringOpen => Some(VD_STRING),
        Fault::VdResistorShort => parallel_resistance(&[Some(3.0 * 200e3), Some(VD_STRING)]),
        _ => Some(VD_STRING / 2.0),
    }
    .unwrap();
    let vb_contact_closed = !matches!(c.fault, Fault::ContactStuckOpen | Fault::CoilStuckEnergized)
        && (c.aux_lost || c.discharge_requested || c.fault == Fault::ContactStuckClosed);
    let vb_nom = if vb_contact_closed {
        match c.fault {
            Fault::VbResistorOpen => Some(VB_BRANCH),
            Fault::VbResistorShort => parallel_resistance(&[Some(7.5e3), Some(VB_BRANCH)]),
            _ => Some(VB_BRANCH / 2.0),
        }
    } else {
        None
    };
    let vd_r_slow = Some(vd_nom * high);
    let vb_r_slow = vb_nom.map(|v| v * high);
    let vd_c = c.vd_cap_uf * 1e-6;
    let vb_c = (c.vb_cap_uf + c.inverter_direct_uf) * 1e-6;
    let delay = if vb_contact_closed && c.fault != Fault::ContactStuckClosed {
        c.contact_release_max_s
    } else {
        0.0
    };
    if c.mains_isolated {
        if c.f2_closed {
            let coupled = parallel_resistance(&[vd_r_slow, vb_r_slow]);
            r.coupled_seconds = Some(delayed_discharge_seconds(
                vd_c + vb_c,
                coupled,
                c.max_v,
                c.target_v,
                delay,
            ));
        } else {
            r.vd_seconds = Some(discharge_seconds(vd_c, vd_r_slow, c.max_v, c.target_v));
            r.vb_seconds = Some(delayed_discharge_seconds(
                vb_c, vb_r_slow, c.max_v, c.target_v, delay,
            ));
        }
    } else {
        r.unknowns.push("mains remains attached: no isolated-RC completion time exists without a bounded source waveform".into());
        if c.claim_deadline_while_mains_live {
            r.rejects
                .push("finite discharge deadline claimed while mains can replenish VD/VB".into());
        }
    }
    if c.inverter_detached_uf > 0.0 {
        if c.inverter_detached_path_ohm == 0.0 {
            r.rejects
                .push("detached inverter capacitance has no bounded local discharge path".into());
        } else if c.mains_isolated {
            r.inverter_seconds = Some(discharge_seconds(
                c.inverter_detached_uf * 1e-6,
                Some(c.inverter_detached_path_ohm * high),
                c.max_v,
                c.target_v,
            ));
        }
    }
    let mut times = vec![];
    for v in [
        r.vd_seconds,
        r.vb_seconds,
        r.coupled_seconds,
        r.inverter_seconds,
    ]
    .into_iter()
    .flatten()
    {
        times.push(v);
    }
    if c.mains_isolated && times.iter().any(|t| *t > c.target_s) {
        if c.fault != Fault::None && !c.single_fault_fast_deadline {
            r.unknowns.push("single fault misses illustrative deadline; fault response and service hold require evidence".into());
        } else {
            r.rejects
                .push("one or more isolated energy islands exceed the entered deadline".into());
        }
    }
    if !vb_contact_closed {
        r.unknowns.push("bank fast discharge contact is open or stuck energized; passive Rev38 bleed is not an accepted safety path".into());
    }
    // The charged bank retains energy even when the fast contact is open.
    r.vb_energy_j = stored_joules(vb_c, c.max_v);
    if let Some(vb_r) = vb_nom {
        r.vb_continuous_w = c.max_v * c.max_v / (vb_r * low);
        let one_resistor_r = 7.5e3 * low;
        r.vb_peak_resistor_w = if c.fault == Fault::VbResistorShort {
            c.max_v * c.max_v / one_resistor_r
        } else {
            c.max_v * c.max_v / (4.0 * one_resistor_r)
        };
        // A bank may place all stored energy in one surviving element after a short.
        r.vb_peak_resistor_j_upper = r.vb_energy_j
            + if c.f2_closed {
                stored_joules(vd_c, c.max_v)
            } else {
                0.0
            };
        if r.vb_peak_resistor_w > 40.0 {
            r.rejects
                .push("one RH50 exceeds its 40 W mounted-at-70 C datasheet screen".into());
        }
        if c.max_v > 1285.0 {
            r.rejects
                .push("RH50 working-voltage screen exceeded".into());
        }
        if c.max_v > 3500.0 || r.vb_continuous_w > 200.0 || c.max_v / (vb_r * low) > 3.0 {
            r.rejects
                .push("Coto 5504 catalog voltage/current/resistive-power screen exceeded".into());
        }
        if c.aux_lost {
            if !c.fan_available && !c.fan_off_thermal_verified {
                r.unknowns.push("AUX-loss bank discharge with fan off lacks installed fan-off thermal proof; mains-attached duty may be continuous".into());
            }
            if c.fan_available && !c.fan_supply_independent_verified {
                r.unknowns.push(
                    "fan availability during AUX loss has no verified independent supply".into(),
                );
            }
        }
    }
    let vd_survivors = if c.fault == Fault::VdResistorShort {
        3.0
    } else {
        4.0
    };
    let vd_worst_share = high / (high + (vd_survivors - 1.0) * low);
    if c.max_v * vd_worst_share > 200.0 {
        r.rejects
            .push("VD TNPW element exceeds 200 V under tolerance-skewed sharing".into());
    }
    let vd_worst_element_w =
        c.max_v * c.max_v * (200e3 * high) / (200e3 * (high + (vd_survivors - 1.0) * low)).powi(2);
    if vd_worst_element_w > 0.4 {
        r.rejects
            .push("VD TNPW element exceeds 0.4 W under tolerance-skewed sharing".into());
    }
    if c.coil_absolute_max_v > 15.0 || c.coil_supply_max_v > c.coil_absolute_max_v {
        r.rejects.push(
            "coil maximum supply or declared limit exceeds Coto 12 V coil 15 V maximum".into(),
        );
    }
    if c.coil_supply_min_v < c.coil_pickup_required_v
        || c.coil_supply_min_v < c.coil_hold_required_v
    {
        r.rejects
            .push("coil minimum supply does not meet entered pickup/hold bounds".into());
    }
    if c.aux_lost && c.coil_loss_residual_max_v >= c.coil_release_required_below_v {
        r.unknowns.push(
            "post-AUX-loss coil voltage may remain above guaranteed release threshold".into(),
        );
    }
    if c.coil_recovery_cycles > 0 && !c.deliberate_rearm_verified {
        r.unknowns.push(
            "AUX brownout/recovery can chatter NC contact without verified deliberate rearm".into(),
        );
    }
    if c.coil_recovery_cycles > 0
        && (c.coil_recovery_period_min_s == 0.0 || c.coil_brownout_dwell_max_s == 0.0)
    {
        r.rejects.push(
            "brownout/recovery cycles require explicit nonzero period and dwell bounds".into(),
        );
    }
    if c.fault != Fault::None && !c.fault_detection_verified {
        r.unknowns
            .push("specified single fault has no verified detection and lockout".into());
    }
    if c.restart_claim {
        if !c.f2_closed || !c.f2_continuity_verified {
            r.rejects
                .push("restart claims shared-bus state without verified F2 continuity".into());
        }
        if matches!(c.fault, Fault::VdSenseOpen | Fault::VbSenseOpen) {
            r.rejects
                .push("restart claimed with an open voltage sense path".into());
        }
        if c.residual_vd_v > c.target_v || c.residual_vb_v > c.target_v {
            r.rejects.push(
                "restart claimed while a recorded residual island exceeds target voltage".into(),
            );
        }
        if !c.deliberate_rearm_verified {
            r.unknowns
                .push("restart lacks verified deliberate rearm".into());
        }
    }
    r.verdict = if !r.rejects.is_empty() {
        Verdict::Rejected
    } else if !r.unknowns.is_empty() {
        Verdict::Indeterminate
    } else {
        Verdict::Conditional
    };
    r
}

#[cfg(test)]
fn illustrative_case() -> GateCase {
    GateCase {
        initial_v: 390.0,
        max_v: 400.0,
        target_v: 80.0,
        target_s: 120.0,
        vd_cap_uf: 24.717,
        vb_cap_uf: 2688.0,
        inverter_direct_uf: 0.0,
        inverter_detached_uf: 0.0,
        inverter_detached_path_ohm: 0.0,
        f2_closed: false,
        mains_isolated: true,
        aux_lost: true,
        discharge_requested: true,
        fan_available: false,
        fan_supply_independent_verified: false,
        contact_release_max_s: 1.0,
        contact_pickup_max_s: 1.0,
        coil_supply_min_v: 12.0,
        coil_supply_max_v: 12.0,
        coil_loss_residual_max_v: 0.0,
        coil_pickup_required_v: 9.0,
        coil_hold_required_v: 8.0,
        coil_release_required_below_v: 2.0,
        coil_absolute_max_v: 15.0,
        coil_recovery_cycles: 0,
        coil_recovery_period_min_s: 0.0,
        coil_brownout_dwell_max_s: 0.0,
        resistor_tolerance_pct: 1.0,
        resistor_drift_pct: 0.0,
        fault: Fault::None,
        single_fault_fast_deadline: true,
        criteria_adopted: false,
        exact_parts_verified: false,
        contact_dc_life_verified: false,
        coil_timing_verified: false,
        installed_thermal_verified: false,
        fan_off_thermal_verified: false,
        fault_detection_verified: false,
        service_measurement_verified: false,
        f2_continuity_verified: false,
        deliberate_rearm_verified: false,
        restart_claim: false,
        residual_vd_v: 0.0,
        residual_vb_v: 0.0,
        claim_deadline_while_mains_live: false,
    }
}

#[test]
fn unadopted_illustration_cannot_pass() {
    let r = evaluate(&illustrative_case());
    assert_eq!(r.verdict, Verdict::Indeterminate);
    assert!(r.vd_seconds.unwrap() < 120.0 && r.vb_seconds.unwrap() < 120.0);
}

#[test]
fn f2_topology_and_detached_inverter_are_distinct() {
    let mut c = illustrative_case();
    let open = evaluate(&c);
    c.f2_closed = true;
    let joined = evaluate(&c);
    assert!(open.coupled_seconds.is_none() && joined.vb_seconds.is_none());
    assert!(joined.coupled_seconds.is_some());
    c.inverter_detached_uf = 10.0;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
}

#[test]
fn attached_mains_has_no_rc_completion_and_fan_off_stress() {
    let mut c = illustrative_case();
    c.mains_isolated = false;
    let r = evaluate(&c);
    assert_eq!(r.verdict, Verdict::Indeterminate);
    assert!(r.vd_seconds.is_none() && r.vb_seconds.is_none());
    assert!(r.vb_continuous_w > 20.0);
    assert!(r.unknowns.iter().any(|s| s.contains("fan off")));
    c.claim_deadline_while_mains_live = true;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
}

#[test]
fn coil_and_contact_adverse_cases_fail_closed() {
    let mut c = illustrative_case();
    c.coil_supply_max_v = 15.75;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
    c.coil_supply_max_v = 12.0;
    c.coil_recovery_cycles = 3;
    c.coil_recovery_period_min_s = 10.0;
    c.coil_brownout_dwell_max_s = 2.0;
    assert!(evaluate(&c).unknowns.iter().any(|s| s.contains("chatter")));
    c.fault = Fault::ContactStuckOpen;
    let open = evaluate(&c);
    assert_eq!(open.verdict, Verdict::Rejected);
    assert!(open.vb_energy_j > 0.0);
    assert_eq!(open.vb_continuous_w, 0.0);
    c.fault = Fault::CoilStuckEnergized;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
}

#[test]
fn single_opens_shorts_and_tolerance_change_bounds() {
    let mut c = illustrative_case();
    let base = evaluate(&c);
    c.fault = Fault::VdStringOpen;
    assert!(evaluate(&c).vd_seconds.unwrap() > base.vd_seconds.unwrap());
    c.fault = Fault::VbResistorOpen;
    assert!(evaluate(&c).vb_seconds.unwrap() > base.vb_seconds.unwrap());
    c.fault = Fault::VbResistorShort;
    let short = evaluate(&c);
    assert!(short.vb_peak_resistor_w > base.vb_peak_resistor_w);
    assert!(short.vb_peak_resistor_j_upper >= short.vb_energy_j);
    c.fault = Fault::VdResistorShort;
    c.max_v = 700.0;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
    c.fault = Fault::None;
    c.max_v = 400.0;
    c.vb_cap_uf = 2000.0;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
}

#[test]
fn restart_cannot_infer_island_health_or_ignore_sense_open() {
    let mut c = illustrative_case();
    c.restart_claim = true;
    c.residual_vb_v = 100.0;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
    c.residual_vb_v = 0.0;
    c.f2_closed = true;
    c.f2_continuity_verified = true;
    c.fault = Fault::VdSenseOpen;
    assert_eq!(evaluate(&c).verdict, Verdict::Rejected);
}

#[test]
fn parser_requires_every_field_and_rejects_unknowns() {
    assert!(GateCase::parse("initial_v=390")
        .unwrap_err()
        .contains("missing"));
    assert!(GateCase::parse("surprise=true")
        .unwrap_err()
        .contains("missing"));
    let case = GateCase::parse(include_str!("isolated-illustrative.case")).unwrap();
    assert_eq!(case.fault, Fault::None);
    assert!(evaluate(&case).render().starts_with("Indeterminate:"));
}

#[test]
fn conditional_requires_all_asserted_evidence() {
    let mut c = illustrative_case();
    c.criteria_adopted = true;
    c.exact_parts_verified = true;
    c.contact_dc_life_verified = true;
    c.coil_timing_verified = true;
    c.installed_thermal_verified = true;
    c.fan_off_thermal_verified = true;
    c.service_measurement_verified = true;
    assert_eq!(evaluate(&c).verdict, Verdict::Conditional);
    c.fan_off_thermal_verified = false;
    assert_eq!(evaluate(&c).verdict, Verdict::Indeterminate);
}

#[test]
fn adopted_deadline_uses_declared_maximum_island_voltage() {
    let mut c = illustrative_case();
    c.max_v = 450.0;
    c.target_s = 35.0;
    c.criteria_adopted = true;
    c.exact_parts_verified = true;
    c.contact_dc_life_verified = true;
    c.coil_timing_verified = true;
    c.installed_thermal_verified = true;
    c.fan_off_thermal_verified = true;
    c.service_measurement_verified = true;
    let result = evaluate(&c);
    assert_eq!(result.verdict, Verdict::Rejected);
    assert!(result.vb_seconds.unwrap() > c.target_s);
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

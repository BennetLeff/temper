//! Illustrative RC and initial-power comparison; no product safety verdict.
//! rustc --edition=2021 topology_screen.rs -o /tmp/topology_screen && /tmp/topology_screen

const VD_F: f64 = 24.717e-6; // committed Rev38 22 uF + 0.47 uF, +10%
const VB_F: f64 = 2688e-6; // committed Rev38 4 x 560 uF, +20%
const DIRECT_INV_F: f64 = 100e-6; // hypothetical directly attached inverter capacitor
const DETACHED_INV_F: f64 = 100e-6; // hypothetical separated island
const RESISTOR_HIGH: f64 = 1.01; // illustrative +1% total, aging excluded
const RESISTOR_LOW: f64 = 0.99; // illustrative -1% initial-power sensitivity
const CONTACT_DELAY_S: f64 = 5.0; // assumed upper bound, not measured

#[derive(Clone, Copy)]
struct Scenario {
    name: &'static str,
    initial_v: f64,
    target_v: f64,
    deadline_s: f64,
}

const SCENARIOS: [Scenario; 2] = [
    Scenario {
        name: "sensitivity_400_to_80_120",
        initial_v: 400.0,
        target_v: 80.0,
        deadline_s: 120.0,
    },
    Scenario {
        name: "sensitivity_450_to_34_60",
        initial_v: 450.0,
        target_v: 34.0,
        deadline_s: 60.0,
    },
];

#[derive(Clone, Copy)]
struct Candidate {
    name: &'static str,
    // Each branch is an independent VB-to-HOT0 resistor route. Switched
    // branches require physically independent contacts, not merely parallel
    // resistors behind one common contact.
    branch_ohm: f64,
    branches: usize,
    switched: bool,
}

const CANDIDATES: [Candidate; 3] = [
    Candidate {
        name: "passive_7k5",
        branch_ohm: 7_500.0,
        branches: 1,
        switched: false,
    },
    Candidate {
        name: "one_nc_2x15k",
        branch_ohm: 15_000.0,
        branches: 2,
        switched: true,
    },
    Candidate {
        name: "two_nc_2x7k5",
        branch_ohm: 7_500.0,
        branches: 2,
        switched: true,
    },
];

#[derive(Clone, Copy)]
enum Fault {
    None,
    OneBranchOpen,
    OneContactOpen,
    CommonHoldEnergized,
    AuxLost,
}

impl Fault {
    fn name(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::OneBranchOpen => "one_resistor_branch_open",
            Self::OneContactOpen => "one_contact_stuck_open",
            Self::CommonHoldEnergized => "common_hold_energized",
            Self::AuxLost => "aux_lost_nc_release_assumed",
        }
    }
}

const FAULTS: [Fault; 5] = [
    Fault::None,
    Fault::OneBranchOpen,
    Fault::OneContactOpen,
    Fault::CommonHoldEnergized,
    Fault::AuxLost,
];

fn parallel_ohms(paths: &[f64]) -> Option<f64> {
    let conductance: f64 = paths.iter().map(|r| 1.0 / r).sum();
    (conductance > 0.0).then_some(1.0 / conductance)
}

fn seconds(c_f: f64, resistance: Option<f64>, s: Scenario, delay_s: f64) -> Option<f64> {
    resistance.map(|r| delay_s + c_f * r * (s.initial_v / s.target_v).ln())
}

fn active_paths(candidate: Candidate, fault: Fault) -> Vec<f64> {
    if candidate.switched && matches!(fault, Fault::CommonHoldEnergized) {
        return vec![];
    }
    let lost = match fault {
        Fault::OneBranchOpen => 1,
        Fault::OneContactOpen if candidate.switched => {
            // The old candidate's one contact is common to both branches.
            if candidate.branches == 2 && candidate.branch_ohm == 15_000.0 {
                2
            } else {
                1
            }
        }
        _ => 0,
    };
    vec![candidate.branch_ohm * RESISTOR_HIGH; candidate.branches.saturating_sub(lost)]
}

fn result_seconds(candidate: Candidate, fault: Fault, s: Scenario) -> Option<f64> {
    let mut paths = active_paths(candidate, fault);
    // Committed Rev38 bank bleeder and F2 detector are slow surviving paths.
    paths.extend([450_000.0 * RESISTOR_HIGH, 992_820.0 * RESISTOR_HIGH]);
    // Delay is pessimistically charged against the entire decay. If the NC
    // coil fails to release, the two passive source paths remain.
    let delay = if candidate.switched && !matches!(fault, Fault::CommonHoldEnergized) {
        CONTACT_DELAY_S
    } else {
        0.0
    };
    seconds(VB_F + DIRECT_INV_F, parallel_ohms(&paths), s, delay)
}

fn qualified_seconds(
    mains_isolated: bool,
    candidate: Candidate,
    fault: Fault,
    s: Scenario,
) -> Option<f64> {
    mains_isolated
        .then(|| result_seconds(candidate, fault, s))
        .flatten()
}

fn vd_seconds(s: Scenario, one_string_open: bool) -> f64 {
    let strings = if one_string_open { 1.0 } else { 2.0 };
    seconds(VD_F, Some(800_000.0 * RESISTOR_HIGH / strings), s, 0.0).unwrap_or(f64::INFINITY)
}

fn detached_seconds(s: Scenario, path_ohm: Option<f64>) -> Option<f64> {
    seconds(DETACHED_INV_F, path_ohm.map(|r| r * RESISTOR_HIGH), s, 0.0)
}

fn fmt_time(value: Option<f64>) -> String {
    value.map_or("UNBOUNDED".to_owned(), |v| format!("{v:.3}"))
}

fn main() {
    println!("scenario,candidate,fault,vb_seconds_if_mains_isolated,vb_seconds_if_mains_attached,vd_seconds,vd_one_string_open_seconds,detached_1meg_seconds,detached_no_path_seconds,initial_vb_path_w_at_minus1pct_if_held,initial_vb_path_a_at_minus1pct_if_held,initial_joules_vb_direct,illustrative_deadline_s");
    for s in SCENARIOS {
        for c in CANDIDATES {
            for fault in FAULTS {
                let paths = active_paths(c, fault);
                let power: f64 = if paths.is_empty() {
                    0.0
                } else {
                    paths
                        .iter()
                        .map(|r| s.initial_v.powi(2) / (r / RESISTOR_HIGH * RESISTOR_LOW))
                        .sum()
                };
                let energy = 0.5 * (VB_F + DIRECT_INV_F) * s.initial_v.powi(2);
                println!(
                    "{},{},{},{},NO_RC_COMPLETION,{:.3},{:.3},{},UNBOUNDED,{:.3},{:.5},{:.3},{:.3}",
                    s.name,
                    c.name,
                    fault.name(),
                    fmt_time(qualified_seconds(true, c, fault, s)),
                    vd_seconds(s, false),
                    vd_seconds(s, true),
                    fmt_time(detached_seconds(s, Some(1_000_000.0))),
                    power,
                    power / s.initial_v,
                    energy,
                    s.deadline_s
                );
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn common_contact_open_removes_both_old_branches() {
        assert!(active_paths(CANDIDATES[1], Fault::OneContactOpen).is_empty());
        assert_eq!(active_paths(CANDIDATES[2], Fault::OneContactOpen).len(), 1);
    }

    #[test]
    fn one_independent_contact_survives_illustrative_fast_case() {
        let t = result_seconds(CANDIDATES[2], Fault::OneContactOpen, SCENARIOS[1]).unwrap();
        assert!(t < SCENARIOS[1].deadline_s, "{t}");
    }

    #[test]
    fn common_hold_fault_misses_fast_case() {
        let t = result_seconds(CANDIDATES[2], Fault::CommonHoldEnergized, SCENARIOS[1]).unwrap();
        assert!(t > SCENARIOS[1].deadline_s, "{t}");
    }

    #[test]
    fn detached_island_requires_own_path() {
        assert!(detached_seconds(SCENARIOS[1], None).is_none());
        assert!(detached_seconds(SCENARIOS[1], Some(1_000_000.0)).unwrap() > 60.0);
    }

    #[test]
    fn no_mains_live_rc_completion_is_modelled() {
        assert!(qualified_seconds(false, CANDIDATES[0], Fault::None, SCENARIOS[0]).is_none());
    }
}

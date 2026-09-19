//! Bounded regression for this experimental protection circuit, not a
//! transistor/rail simulation or protection acceptance certificate.

/// CD4013 permission state. RESET is the persistent fault; CLOCK is ready.
#[derive(Clone, Copy, Debug)]
struct Permission {
    q: bool,
    previous_ready: bool,
}

impl Permission {
    fn step(&mut self, ready: bool, fault: bool) -> bool {
        if fault {
            self.q = false;
        } else if ready && !self.previous_ready {
            self.q = true;
        }
        self.previous_ready = ready;
        // Two independent parallel VSENSE pull-downs: POR and QN.
        !ready || !self.q
    }
}

/// Sequential delays AFTER the diode-side voltage crosses the independent
/// detector threshold. None is unknown, not zero. Sum ends at U9 turn-off.
fn total_turn_off_delay(segments_s: [Option<f64>; 6]) -> Option<f64> {
    segments_s.into_iter().try_fold(0.0, |sum, delay| {
        let value = delay?;
        (value.is_finite() && value >= 0.0).then_some(sum + value)
    })
}

fn main() {
    let mut permission = Permission {
        q: true,
        previous_ready: false,
    };
    let inhibited = [
        permission.step(false, true),
        permission.step(true, true),
        permission.step(true, false),
    ];
    println!("persistent_startup_fault_inhibit_trace={inhibited:?}; logical model only");
    println!("status=INDETERMINATE; no protection acceptance");
    println!("detector_nominal_v=505; selected_local_cap_f=0.0000015");
    println!("clamp=NONE_SELECTED; first_peak_control=UNESTABLISHED");
    println!("timing_segments=detector,logic,inhibit_gate,vsense_discharge,controller_standby,U9_turn_off");
    println!(
        "total_turn_off_delay_s={:?}",
        total_turn_off_delay([None; 6])
    );
    println!("startup_current_at_trip_A=null; startup_peak_bound_V=null");
    println!("single_event_guaranteed=false; hardware_qualification=NOT_PERFORMED");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    const SOURCE: &str = include_str!("../../../../../elec/src/power_entry_active_unit.ato");

    // This fixture reader supports the explicit single-line Atopile wiring
    // used by this module only. Native netlist/ERC remain separate checks.
    fn nets(source: &str) -> BTreeMap<String, usize> {
        let module = source
            .split("module PowerEntryActiveUnit:")
            .nth(1)
            .expect("module");
        let mut nets = BTreeMap::new();
        let mut next = 0;
        for line in module.lines() {
            let line = line.split('#').next().unwrap_or("").trim();
            let Some((a, b)) = line.split_once('~') else {
                continue;
            };
            assert!(
                !b.contains('~'),
                "fixture reader needs an explicit two-node connection"
            );
            let (a, b) = (a.trim(), b.trim());
            let left = *nets.entry(a.to_owned()).or_insert_with(|| {
                next += 1;
                next
            });
            let right = *nets.entry(b.to_owned()).or_insert_with(|| {
                next += 1;
                next
            });
            for id in nets.values_mut() {
                if *id == right {
                    *id = left;
                }
            }
        }
        nets
    }

    fn wiring_matches_permission_model(source: &str) -> bool {
        let n = nets(source);
        let connected = |a: &str, b: &str| n.get(a).is_some() && n.get(a) == n.get(b);
        [
            ("det_latch.R1", "por_gate.Y2"),
            ("por_gate.A2", "fault_n"),
            ("det_latch.CLK1", "por_gate.Y3"),
            ("por_gate.A3", "por_gate.Y1"),
            ("det_latch.D1", "aux_15v"),
            ("det_latch.S1", "control_gnd"),
            ("det_latch.QN1", "r_inh2_gate.p1"),
            ("por_gate.Y1", "r_start_gate.p1"),
            ("q_startup.D", "pfc.VSENSE"),
            ("q_startup.S", "control_gnd"),
            ("q_inhibit2.D", "pfc.VSENSE"),
        ]
        .into_iter()
        .all(|(a, b)| connected(a, b))
            && !connected("det_cmp.INA_N", "det_cmp.INA_P")
            && !connected("det_latch.R1", "det_latch.CLK1")
    }

    #[test]
    fn fault_present_before_ready_cannot_be_lost() {
        for initial_q in [false, true] {
            let mut p = Permission {
                q: initial_q,
                previous_ready: false,
            };
            assert!(p.step(false, true));
            assert!(p.step(true, true));
            assert!(p.step(true, false), "fault clearance must not rearm");
        }
    }

    #[test]
    fn startup_inhibits_even_with_unknown_initial_permission() {
        let mut p = Permission {
            q: true,
            previous_ready: false,
        };
        assert!(p.step(false, false));
        assert!(
            !p.step(true, false),
            "positive control: healthy startup can run"
        );
    }

    #[test]
    fn fault_at_or_after_ready_resets_and_stays_inhibited() {
        for at_ready in [true, false] {
            let mut p = Permission {
                q: false,
                previous_ready: false,
            };
            p.step(false, false);
            p.step(true, at_ready);
            assert!(p.step(true, true));
            assert!(p.step(true, false));
        }
    }

    #[test]
    fn new_ready_cycle_can_rearm_but_persistent_fault_cannot() {
        let mut p = Permission {
            q: false,
            previous_ready: true,
        };
        assert!(p.step(false, true));
        assert!(p.step(true, true));
        p.step(false, false);
        assert!(!p.step(true, false));
    }

    #[test]
    fn vsense_low_alone_does_not_establish_turn_off_delay() {
        assert!((total_turn_off_delay([Some(1e-6); 6]).unwrap() - 6e-6).abs() < 1e-15);
        assert_eq!(
            total_turn_off_delay([Some(1e-6), Some(1e-6), Some(1e-6), Some(1e-6), None, None]),
            None
        );
        assert_eq!(total_turn_off_delay([Some(-1.0); 6]), None);
    }

    #[test]
    fn source_wiring_matches_permission_model() {
        assert!(wiring_matches_permission_model(SOURCE));
    }

    #[test]
    fn historical_edge_trigger_and_shorted_detector_are_rejected() {
        let old_clock = SOURCE.replace(
            "por_gate.Y3 ~ det_latch.CLK1",
            "por_gate.Y2 ~ det_latch.CLK1",
        );
        assert!(!wiring_matches_permission_model(&old_clock));
        let old_detector = SOURCE.replace("det_cmp.INA_P ~ ref_5v", "det_cmp.INA_P ~ det_tap");
        assert!(!wiring_matches_permission_model(&old_detector));
    }
}

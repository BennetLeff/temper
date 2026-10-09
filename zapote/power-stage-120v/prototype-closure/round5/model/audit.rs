//! Audits complete receipts and negative controls; reports diagnostic convergence.
use std::{collections::BTreeMap, env, fs, path::Path};
fn number(s: &str, key: &str) -> f64 {
    let value: f64 = s
        .split(&format!("\"{key}\":"))
        .nth(1)
        .unwrap()
        .split([',', '}'])
        .next()
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    assert!(value.is_finite(), "nonfinite receipt metric: {key}");
    value
}
fn verify_joined_run(s: &str, expected: bool) {
    assert_eq!(number(s, "first_run_s") >= 0., expected);
    assert_eq!(
        number(s, "unsafe_run_s"),
        0.,
        "RUN with precharge isolation closed"
    );
    if expected {
        assert!(
            number(s, "joined_run_s") > 0.05,
            "no sustained joined permission"
        );
        assert!(number(s, "load_j") > 1., "RUN enum without electrical load");
    } else {
        assert_eq!(number(s, "joined_run_s"), 0.);
        assert_eq!(number(s, "load_j"), 0.);
    }
}
fn verify_stop_time(events: &str) {
    let stop = events
        .lines()
        .skip(1)
        .find_map(|row| {
            let fields: Vec<_> = row.split(',').collect();
            (fields[1..] == ["state", "7", "0"]).then(|| fields[0].parse::<f64>().unwrap())
        })
        .expect("missing normal STOP transition");
    assert!(
        (stop - 1.270).abs() < 1e-9,
        "STOP event missed integer deadline"
    );
}
fn verify_readback_fault_time(events: &str) {
    let fault = events
        .lines()
        .skip(1)
        .find_map(|row| {
            let fields: Vec<_> = row.split(',').collect();
            (fields[1..] == ["state", "8", "1"]).then(|| fields[0].parse::<f64>().unwrap())
        })
        .expect("missing readback health fault");
    assert!(
        (fault - 1.001).abs() < 1e-9,
        "readback fault must follow injected loss at1s"
    );
}
fn verify_demand_pause(samples: &str) {
    let mut paused = 0;
    let mut resumed = 0;
    for row in samples.lines().skip(1) {
        let v: Vec<_> = row.split(',').collect();
        let t: f64 = v[0].parse().unwrap();
        assert_ne!(v[1], "8", "demand pause faulted session");
        if (0.951..1.050).contains(&t) {
            assert_eq!(v[11], "0", "demand did not withdraw");
            assert_eq!(v[12], "0", "RUN remained asserted during zero demand");
            paused += 1;
        }
        if (1.100..1.260).contains(&t) && v[12] == "1" {
            resumed += 1;
        }
    }
    assert!(paused >= 90, "missing zero-demand interval");
    assert!(resumed >= 100, "missing resumed RUN interval");
}
fn main() {
    let a: Vec<_> = env::args().collect();
    assert_eq!(a.len(), 2);
    let out = Path::new(&a[1]);
    let mut max_relative: f64 = 0.;
    let mut max_peak_w: f64 = 0.;
    let mut max_i2t: f64 = 0.;
    let mut checked = 0;
    for (name, state, fault, run) in [
        ("nominal", 7, 0, true),
        ("low-loss", 7, 0, true),
        ("demand-pause", 7, 0, true),
        ("no-demand", 8, 1, false),
        // Shared catch-history now withdraws below100V; the bus-short study
        // clips its explicitly ideal300A ADC range. These are software paths,
        // not assertions of native comparator/fuse interruption behavior.
        ("catch-short", 8, 6, true),
        ("bus-short", 8, 1, true),
        ("stale", 8, 1, true),
        // Retained-session live PWM qualification faults through hardware_ok
        // before the adapter's separate readback fault path can execute.
        ("readback", 8, 1, true),
        ("proof-open", 8, 3, false),
        ("bypass-open", 8, 3, false),
        // The new isolation controller faults an invalid START/POST; the
        // wrapper then withdraws hardware health from the portable core.
        ("bad-post", 8, 1, false),
        ("inhibited", 8, 8, false),
    ] {
        let mut pair = Vec::new();
        for step in [0.625, 0.3125] {
            let p = out.join("verified-cases").join(format!("{name}-{step}us"));
            let s = fs::read_to_string(p.join("result.json")).unwrap();
            assert!(fs::read_to_string(p.join("STATUS"))
                .unwrap()
                .contains("SIMULATED_DIAGNOSTIC_ONLY"));
            assert_eq!(number(&s, "final_state") as i32, state);
            assert_eq!(number(&s, "final_fault") as i32, fault);
            verify_joined_run(&s, run);
            if fault == 0 {
                verify_stop_time(&fs::read_to_string(p.join("events.csv")).unwrap());
            }
            if name == "demand-pause" {
                verify_demand_pause(&fs::read_to_string(p.join("samples.csv")).unwrap());
            }
            if name == "readback" {
                verify_readback_fault_time(&fs::read_to_string(p.join("events.csv")).unwrap());
            }
            assert!(number(&s, "completed_time_s") >= 1.3);
            max_peak_w = max_peak_w.max(number(&s, "pre1_peak_w"));
            max_i2t = max_i2t.max(number(&s, "catch_i2t"));
            checked += 1;
            pair.push(s);
        }
        for key in [
            "bus_peak_v",
            "catch_peak_v",
            "catch_i2t",
            "rect_i2t",
            "pre1_j",
            "pre1_peak_w",
        ] {
            let x = number(&pair[0], key);
            let y = number(&pair[1], key);
            if y.abs() > 1e-6 {
                max_relative = max_relative.max((x - y).abs() / y.abs());
            }
        }
    }
    let mut energy: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut energy_res: f64 = 0.;
    let mut energy_peak: f64 = 0.;
    let mut energy_conv: f64 = 0.;
    for l in fs::read_to_string(out.join("energy-ode.csv"))
        .unwrap()
        .lines()
        .skip(1)
    {
        let v: Vec<_> = l.split(',').collect();
        let key = v[1..6].join(",");
        let nums: Vec<f64> = v[6..].iter().map(|x| x.parse().unwrap()).collect();
        assert!(
            nums.iter().all(|x| x.is_finite()),
            "nonfinite energy metric"
        );
        energy_res = energy_res.max(nums[7].abs());
        energy_peak = energy_peak.max(nums[4]);
        if let Some(old) = energy.insert(key, nums.clone()) {
            for n in 0..7 {
                if nums[n].abs() > 1e-8 {
                    energy_conv = energy_conv.max((nums[n] - old[n]).abs() / nums[n].abs());
                }
            }
        }
    }
    assert!(
        max_relative < 0.02,
        "closed-loop refinement exceeds2% acceptance"
    );
    assert!(energy_res < 0.002);
    assert!(energy_conv < 0.02);
    assert_eq!(energy.len(), 32);
    let json=format!("{{\"status\":\"DIAGNOSTIC_ONLY_NO_POWER_RELEASE\",\"closed_loop_cases_completed\":{checked},\"negative_controls_match\":true,\"maximum_case_refinement_fraction\":{max_relative},\"precharge_branch_peak_w_prospective\":{max_peak_w},\"catch_i2t_prospective\":{max_i2t},\"energy_cases\":64,\"maximum_energy_residual_fraction\":{energy_res},\"energy_refinement_fraction\":{energy_conv},\"energy_catch_peak_v\":{energy_peak},\"installed_catch_inductance_extracted\":false,\"shared_target_measurement_source\":true,\"shared_loaded_bypass_predicate\":true,\"whole_target_hal_parity\":false,\"dc_fuse_clearing_qualified\":false}}\n");
    fs::write(out.join("audit.json"), &json).unwrap();
    println!("{json}");
}

#[cfg(test)]
mod tests {
    use super::{number, verify_joined_run, verify_readback_fault_time, verify_stop_time};

    #[test]
    #[should_panic(expected = "readback fault must follow injected loss at1s")]
    fn unrelated_earlier_fault_cannot_pass_readback_injection() {
        verify_readback_fault_time("time_s,event,state,fault\n0.9,state,8,1\n");
    }

    #[test]
    #[should_panic(expected = "STOP event missed integer deadline")]
    fn one_tick_stop_drift_is_rejected() {
        verify_stop_time("time_s,event,state,fault\n1.271000000,state,7,0\n");
    }

    #[test]
    #[should_panic(expected = "no sustained joined permission")]
    fn energy_run_enum_without_joined_permission_is_rejected() {
        verify_joined_run(
            r#"{"first_run_s":0.8,"unsafe_run_s":0,"joined_run_s":0,"load_j":0}"#,
            true,
        );
    }

    #[test]
    #[should_panic(expected = "RUN enum without electrical load")]
    fn permission_without_electrical_load_is_rejected() {
        verify_joined_run(
            r#"{"first_run_s":0.8,"unsafe_run_s":0,"joined_run_s":0.2,"load_j":0}"#,
            true,
        );
    }

    #[test]
    #[should_panic(expected = "RUN with precharge isolation closed")]
    fn loaded_run_with_connected_precharge_is_rejected() {
        verify_joined_run(
            r#"{"first_run_s":0.8,"unsafe_run_s":0.000001,"joined_run_s":0.2,"load_j":5}"#,
            true,
        );
    }

    #[test]
    #[should_panic(expected = "nonfinite receipt metric")]
    fn receipt_nan_cannot_disappear_in_maximum() {
        number("{\"peak\":NaN}", "peak");
    }

    #[test]
    #[should_panic(expected = "nonfinite receipt metric")]
    fn receipt_infinity_cannot_pass_refinement() {
        number("{\"peak\":inf}", "peak");
    }
}

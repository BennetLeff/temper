use serde_json::{json, Value};
use zapote_core::{CheckReport, Status};
use zapote_erc::interlock::{evaluate_graph, InterlockInputs, InterlockState};
const SOURCE: &str = include_str!("../../../interlock/candidate/source-manifest.json");
const NATIVE: &str = include_str!("../../../interlock/evidence/native-final.json");
const CONTRACT: &str = include_str!("../../../interlock/interface-contract.json");
fn value(s: &str) -> Value {
    serde_json::from_str(s).unwrap()
}
fn report(s: &Value, n: &Value, c: &Value) -> CheckReport {
    zapote_harness::interlock::run_interlock(&s.to_string(), &n.to_string(), &c.to_string())
}
fn erc(s: &Value, n: &Value) -> CheckReport {
    zapote_erc::interlock::validate(&s.to_string(), &n.to_string())
}
fn fail(r: CheckReport, rule: &str) {
    assert_eq!(r.status, Status::Fail);
    assert!(
        r.findings
            .iter()
            .any(|f| f.rule == rule && f.status == Status::Fail),
        "missing {rule}: {r:?}"
    );
}
/// Move the existing physical endpoint, preserving the complete endpoint census.
fn move_pin(s: &mut Value, reference: &str, pin: &str, destination: &str) {
    let pair = json!([reference, pin]);
    let mut count = 0;
    for n in s["bridge"]["nets"].as_array_mut().unwrap() {
        n["nodes"].as_array_mut().unwrap().retain(|p| {
            if *p == pair {
                count += 1;
                false
            } else {
                true
            }
        })
    }
    assert_eq!(count, 1);
    s["bridge"]["nets"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|n| n["name"] == destination)
        .unwrap()["nodes"]
        .as_array_mut()
        .unwrap()
        .push(pair);
}
#[test]
fn actual_artifacts_have_no_hard_failure_and_all_4096_graph_vectors_pass() {
    let r = report(&value(SOURCE), &value(NATIVE), &value(CONTRACT));
    assert_eq!(r.status, Status::Indeterminate, "{r:?}");
    assert!(!r.findings.iter().any(|f| f.status == Status::Fail));
    assert!(r
        .findings
        .iter()
        .any(|f| f.rule == "ERC.INTERLOCK.DIGITAL_MODEL"
            && f.status == Status::Pass
            && f.message.starts_with("4096/4096")));
}
#[test]
fn reset_retains_permission_and_recovery_needs_a_new_edge() {
    for fault_kind in 0..9 {
        let mut q = false;
        let mut old_reset = true;
        for (fault, reset, expected) in [
            (false, true, false),
            (false, false, true),
            (false, true, true),
            (true, false, false),
            (false, false, false),
            (false, true, false),
            (false, false, true),
        ] {
            let i = InterlockInputs {
                faults: if fault && fault_kind < 7 {
                    1 << fault_kind
                } else {
                    0
                },
                sensor_live: !(fault && fault_kind == 7),
                watchdog_reset_n: !(fault && fault_kind == 8),
                prior: InterlockState {
                    permit: q,
                    latched_fault: !q,
                },
                reset_falling_edge: old_reset && !reset,
            };
            let actual = evaluate_graph(SOURCE, i, old_reset, reset).unwrap();
            assert_eq!(actual.permit, expected, "fault kind {fault_kind}");
            assert_eq!(actual.latched_fault, !expected);
            q = actual.permit;
            old_reset = reset;
        }
    }
}
#[test]
fn bypassing_actual_clear_pin_breaks_graph_behavior() {
    let mut s = value(SOURCE);
    move_pin(&mut s, "U4", "6", "vcc");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.DIGITAL_MODEL");
}
#[test]
fn bypassing_reset_inverter_breaks_actual_clock_behavior() {
    let mut s = value(SOURCE);
    move_pin(&mut s, "U4", "1", "reset_n");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.DIGITAL_MODEL");
}
#[test]
fn swapped_q_outputs_break_connector_behavior() {
    let mut s = value(SOURCE);
    move_pin(&mut s, "U4", "5", "latched_fault");
    move_pin(&mut s, "U4", "3", "permit");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.DIGITAL_MODEL");
}
#[test]
fn nand_input_bypass_hides_fault_and_is_rejected() {
    let mut s = value(SOURCE);
    move_pin(&mut s, "U3", "1", "vcc");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.DIGITAL_MODEL");
}
#[test]
fn d_tied_low_cannot_grant_permission() {
    let mut s = value(SOURCE);
    move_pin(&mut s, "U4", "2", "gnd");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.DIGITAL_MODEL");
}
#[test]
fn changed_resistance_fails_electrical_margin_not_just_part_identity() {
    let mut s = value(SOURCE);
    s["source_attributes"]["ocp_pullup"]["value"] = json!("100kohm +/- 1%");
    for c in s["components"].as_array_mut().unwrap() {
        if c["instance_path"] == "ocp_pullup" {
            c["value"] = json!("100kohm +/- 1%")
        }
    }
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.OPEN_MARGIN");
}
#[test]
fn missing_pull_component_fails_census() {
    let mut s = value(SOURCE);
    s["components"]
        .as_array_mut()
        .unwrap()
        .retain(|c| c["instance_path"] != "ocp_pullup");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.INPUT");
}
#[test]
fn wdi_bias_substitution_is_rejected() {
    let mut s = value(SOURCE);
    s["source_attributes"]["wdi_pulldown"]["value"] = json!("10kohm +/- 1%");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.PARTS");
}
#[test]
fn wrong_bypass_value_is_rejected() {
    let mut s = value(SOURCE);
    s["source_attributes"]["latch_bypass"]["value"] = json!("1nF +/- 10%");
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.PARTS");
}
#[test]
fn split_native_cluster_with_all_nodes_present_is_rejected() {
    let mut n = value(NATIVE);
    let clusters = n["connectivity_clusters"].as_array_mut().unwrap();
    let c = clusters
        .iter_mut()
        .find(|c| c["net"] == "all_good")
        .unwrap();
    let node = c["nodes"].as_array_mut().unwrap().pop().unwrap();
    let mut other = c.clone();
    other["nodes"] = json!([node]);
    clusters.push(other);
    fail(erc(&value(SOURCE), &n), "ERC.INTERLOCK.CONNECTIVITY");
}
#[test]
fn nc_connected_to_ground_is_rejected() {
    let mut n = value(NATIVE);
    for c in n["components"].as_array_mut().unwrap() {
        if c["id"] == "control_inv" {
            for p in c["footprint_pads"].as_array_mut().unwrap() {
                if p["pad"] == "12" {
                    p["net"] = json!("gnd")
                }
            }
        }
    }
    for c in n["connections"].as_array_mut().unwrap() {
        if c["component"] == "control_inv" && c["pin"] == "12" {
            c["net"] = json!("gnd")
        }
    }
    fail(erc(&value(SOURCE), &n), "ERC.INTERLOCK.TOPOLOGY");
}
#[test]
fn strict_pin_mapping_cannot_be_deleted() {
    let mut s = value(SOURCE);
    s["strict_pin_map"].as_array_mut().unwrap().pop();
    fail(erc(&s, &value(NATIVE)), "ERC.INTERLOCK.STRICT_PIN_MAP");
}
#[test]
fn stale_embedded_board_digest_is_rejected() {
    let mut n = value(NATIVE);
    n["board_sha256"] = json!("0".repeat(64));
    let r = report(&value(SOURCE), &n, &value(CONTRACT));
    assert_eq!(r.status, Status::Fail);
    assert!(
        r.findings
            .iter()
            .any(|f| f.status == Status::Fail && f.rule == "DRC.BOARD.STACKUP"),
        "{r:?}"
    );
}
#[test]
fn timing_polarity_leakage_and_qualification_cannot_be_relaxed() {
    for (key, v) in [
        ("reset_active_low_edge", json!(false)),
        ("aggregate_input_leakage_a", json!(0)),
        ("reset_pulse_min_s", json!(0)),
        ("watchdog_timeout_s", json!([0, 1, 100])),
        ("qualification", json!("pass")),
    ] {
        let mut c = value(CONTRACT);
        c[key] = v;
        fail(
            report(&value(SOURCE), &value(NATIVE), &c),
            "ERC.INTERLOCK.INTERFACE_CONTRACT",
        );
    }
}
#[test]
fn malformed_input_is_a_hard_failure() {
    fail(
        zapote_erc::interlock::validate("{", NATIVE),
        "ERC.INTERLOCK.INPUT",
    );
    fail(
        zapote_harness::interlock::run_interlock(SOURCE, NATIVE, "{"),
        "ERC.INTERLOCK.CONTRACT",
    );
}

#[test]
fn native_fields_cannot_contradict_saved_board_bytes() {
    let mut n = value(NATIVE);
    n["components"][0]["mpn"] = json!("WRONG-PART");
    fail(
        report(&value(SOURCE), &n, &value(CONTRACT)),
        "DRC.NATIVE.DOCUMENT_BINDING",
    );
}

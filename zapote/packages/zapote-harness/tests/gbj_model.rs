use std::{fs, path::PathBuf};
use zapote_core::Status;
use zapote_harness::{bridge_thermal, pfc_power};

fn inputs() -> (Vec<u8>, Vec<u8>, pfc_power::Report) {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../power-entry/bridge-redesign/variants/alternate-gbj");
    let native = fs::read(dir.join("evidence/native-fresh.json")).unwrap();
    let manufacturing = fs::read(dir.join("evidence/manufacturing-fresh.json")).unwrap();
    let report = pfc_power::run(
        &fs::read_to_string(dir.join("source-manifest.json")).unwrap(),
        std::str::from_utf8(&native).unwrap(),
        &fs::read_to_string(dir.join("section.kicad_pcb")).unwrap(),
        &serde_json::from_slice(&manufacturing).unwrap(),
    )
    .unwrap();
    (native, manufacturing, report)
}

#[test]
fn gbj_current_model_binds_actual_trace_ids_and_keeps_sharing_indeterminate() {
    let (native, manufacturing, pfc) = inputs();
    let w = bridge_thermal::physical_waveform_for_native(&pfc, &native, &manufacturing).unwrap();
    assert!(w.neck_rms_a.values().all(|i| (i - 15.0).abs() < 1e-8));
    let powers = zapote_thermal::joint_model::gbj_diode_power(&w).unwrap();
    assert!(powers.iter().all(|p| (p - 10.0).abs() < 1e-8));
    assert_eq!(pfc.checks.status, Status::Indeterminate);
}

#[test]
fn unknown_ac2_cut_cannot_hide_changed_load_or_missing_segments() {
    let (native, manufacturing, mut pfc) = inputs();
    let id = "fcbfb9cb-ae96-4261-8ec9-a57c3db7f95d:0";
    pfc.branches
        .iter_mut()
        .find(|b| b.id == id)
        .unwrap()
        .rms_envelope_a = 30.0;
    assert!(bridge_thermal::physical_waveform_for_native(&pfc, &native, &manufacturing).is_err());
    pfc.branches.retain(|b| !b.id.starts_with("fcbfb9cb-"));
    assert!(bridge_thermal::physical_waveform_for_native(&pfc, &native, &manufacturing).is_err());
}

#[test]
fn fresh_hash_does_not_authorize_forged_native_trace_geometry() {
    let (native, manufacturing, pfc) = inputs();
    let mut n: serde_json::Value = serde_json::from_slice(&native).unwrap();
    let t = n["traces"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .find(|t| t["uuid"] == "c060f5f6-a3d7-4399-923b-4094c1d4c60e")
        .unwrap();
    t["width_mm"] = serde_json::json!(8.0);
    assert!(bridge_thermal::physical_waveform_for_native(
        &pfc,
        &serde_json::to_vec(&n).unwrap(),
        &manufacturing
    )
    .is_err());
}

#[test]
fn missing_gbj_evidence_cannot_satisfy_common_thermal_obligations() {
    let (native, manufacturing, pfc) = inputs();
    let reports = bridge_thermal::run_gbj_model(None, &native, Some(&manufacturing), Some(&pfc));
    for report in [reports.thermal, reports.physical, reports.joint] {
        assert_eq!(report.status, Status::Fail);
    }
}

#[test]
fn asymmetric_half_cycles_follow_current_entering_the_bridge_not_copper_injection() {
    let mut w = zapote_thermal::physical_model::WaveformInput {
        profile_sha256: "0".repeat(64),
        samples: vec![zapote_thermal::physical_model::WaveformSample {
            weight: 1.0,
            line_sign: 1.0,
            inductor_a: 15.0,
        }],
        neck_rms_a: ["plus", "ac1", "ac2", "minus"]
            .into_iter()
            .map(|n| (n.into(), 15.0))
            .collect(),
    };
    // Production injections: bridge.2=-I, bridge.3=+I, plus=+I,
    // minus=-I. Injection is INTO PCB COPPER, so current enters the
    // device at AC1 and minus, and leaves at plus and AC2.
    assert_eq!(
        zapote_thermal::joint_model::gbj_diode_power(&w).unwrap(),
        [20.0, 0.0, 0.0, 20.0]
    );
    w.samples[0].line_sign = -1.0;
    assert_eq!(
        zapote_thermal::joint_model::gbj_diode_power(&w).unwrap(),
        [0.0, 20.0, 20.0, 0.0]
    );
    w.samples[0].line_sign = 0.0;
    assert!(zapote_thermal::joint_model::gbj_diode_power(&w).is_err());
}

#[test]
fn retained_gbj_raw_evidence_satisfies_numerics_without_qualifying_hardware() {
    let (native, manufacturing, pfc) = inputs();
    let root =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../thermal/gbj-study/evidence-01");
    let reports =
        bridge_thermal::run_gbj_model(Some(&root), &native, Some(&manufacturing), Some(&pfc));
    assert!(reports
        .thermal
        .findings
        .iter()
        .any(|f| f.message.contains("weak-assembly")));
    let fan = reports
        .thermal
        .findings
        .iter()
        .find(|f| f.object == "power-entry.gbj-thermal.fan-loss")
        .expect("fan-loss cooling sensitivity finding");
    assert_eq!(fan.status, Status::Indeterminate);
    assert!(fan.message.contains("119.53 C hottest diode"));
    assert!(fan.message.contains("118.64 C whole-joint peak"));
    for report in [reports.thermal, reports.physical, reports.joint] {
        assert_eq!(report.status, Status::Indeterminate, "{report:?}");
        assert!(!report.findings.iter().any(|f| f.status == Status::Fail));
    }
}

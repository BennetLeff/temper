use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static COUNTER: AtomicU64 = AtomicU64::new(0);

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn fixture(extra: &str, times: [f64; 3]) -> Vec<u8> {
    let variables = if extra.is_empty() {
        "0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\n"
    } else {
        "0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\n5 i(aux) current\n"
    };
    let columns = if extra.is_empty() { 5 } else { 6 };
    let mut bytes = format!(
        "Title: deterministic test\nFlags: real\nNo. Variables: {columns}\nNo. Points: 3\nVariables:\n{variables}Binary:\n"
    )
    .into_bytes();
    for time in times {
        let values = [time, 3.3, 15.0, 0.25, 0.2];
        bytes.extend_from_slice(&values[0].to_le_bytes());
        for value in values.iter().skip(1) {
            bytes.extend_from_slice(&value.to_le_bytes());
        }
        if columns == 6 {
            let value = if extra == "nan" { f64::NAN } else { 0.0 };
            bytes.extend_from_slice(&value.to_le_bytes());
        }
    }
    bytes
}

fn root_path(label: &str) -> PathBuf {
    std::env::temp_dir().join(format!(
        "temper-binary-{label}-{}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ))
}

fn requirements() -> String {
    json!({"revision":"test","requirements":[{"id":"load_step_endpoints","profiles":[{"id":"continuous_50mA_to_500mA","low_a":0.05,"high_a":0.5},{"id":"pulse_50mA_to_1A","low_a":0.05,"high_a":1.0}]}]}).to_string()
}

fn input(root: &Path, bytes: &[u8]) -> Value {
    let specs = vec![json!({
        "raw_format":"ngspice-binary-le64",
        "window_start_s":0.0,"window_end_s":2.0,"max_step_s":1.0,
        "target_v":3.3,"settling_band_v":0.1,"event_s":0.0,
        "limits":{"vout_avg":{"min":0.0,"max":5.0},"vout_pp":{"min":0.0,"max":5.0},"overshoot_v":{"min":0.0,"max":5.0},"settling_s":{"min":0.0,"max":5.0},"vin_span":{"min":0.0,"max":20.0}}
    })];
    let req = requirements();
    json!({
        "profile":"engineering-simulation", "model":{}, "qualification_verified":false,
        "circuit_sha256":"a".repeat(64), "requirements_sha256":digest(req.as_bytes()),
        "settings_sha256":digest(&serde_json::to_vec(&specs).unwrap()),
        "requirements_manifest":req,
        "scenarios":[{"name":"input_variation","status":"pass","deck_sha256":"b".repeat(64),
            "spec":specs[0],"raw_format":"ngspice-binary-le64","raw_file":"waveform.raw",
            "artifact_sha256":digest(bytes)}],
        "raw_root_hint":root.to_string_lossy()
    })
}

fn assert_waveform_invalid(root: &Path, payload: Value, needle: &str) {
    let result = run_with_payload(root, payload);
    let findings = result["findings"].as_array().expect("top-level findings");
    assert!(
        findings.iter().any(|finding| {
            finding["id"] == "waveform_invalid"
                && finding["message"]
                    .as_str()
                    .is_some_and(|message| message.contains(needle))
        }),
        "expected waveform_invalid containing {needle:?}, got {result}"
    );
}

fn run_with_payload(root: &Path, payload: Value) -> Value {
    let input = serde_json::to_vec(&payload).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_temper-harness-e00"))
        .env("TEMPER_SIMULATION_RAW_ROOT", root)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .and_then(|mut child| {
            use std::io::Write;
            child.stdin.take().unwrap().write_all(&input)?;
            child.wait_with_output()
        })
        .expect("run harness");
    assert!(
        output.status.success(),
        "harness stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("JSON response")
}

fn write_waveform(root: &Path, bytes: &[u8]) {
    fs::create_dir_all(root).unwrap();
    fs::write(root.join("waveform.raw"), bytes).unwrap();
}

#[test]
fn binary_parser_rejects_malformed_waveforms_and_bindings() {
    let root = root_path("malformed");
    let bytes = fixture("", [0.0, 1.0, 2.0]);
    write_waveform(&root, &bytes);

    let mut truncated = bytes.clone();
    truncated.pop();
    let mut payload = input(&root, &truncated);
    payload["scenarios"][0]["artifact_sha256"] = json!(digest(&truncated));
    write_waveform(&root, &truncated);
    assert_waveform_invalid(&root, payload, "truncated or extra");

    let mut trailing = bytes.clone();
    trailing.push(0);
    let mut payload = input(&root, &trailing);
    payload["scenarios"][0]["artifact_sha256"] = json!(digest(&trailing));
    write_waveform(&root, &trailing);
    assert_waveform_invalid(&root, payload, "truncated or extra");

    let nan = fixture("nan", [0.0, 1.0, 2.0]);
    let payload = {
        let mut p = input(&root, &nan);
        p["scenarios"][0]["artifact_sha256"] = json!(digest(&nan));
        p
    };
    write_waveform(&root, &nan);
    assert_waveform_invalid(&root, payload, "nonfinite");

    for (needle, replacement) in [
        ("duplicate signal", "1 v(out) voltage\n2 v(out) voltage\n"),
        ("wrong binary units", "1 v(out) current\n"),
        ("missing signal", "1 v(other) voltage\n"),
    ] {
        let mut malformed = bytes.clone();
        let marker = b"1 v(out) voltage\n";
        let position = malformed
            .windows(marker.len())
            .position(|w| w == marker)
            .unwrap();
        malformed.splice(
            position..position + marker.len(),
            replacement.as_bytes().iter().copied(),
        );
        let mut p = input(&root, &malformed);
        p["scenarios"][0]["artifact_sha256"] = json!(digest(&malformed));
        write_waveform(&root, &malformed);
        assert_waveform_invalid(&root, p, needle);
    }

    let nonmonotonic = fixture("", [0.0, 2.0, 1.0]);
    let mut p = input(&root, &nonmonotonic);
    p["scenarios"][0]["artifact_sha256"] = json!(digest(&nonmonotonic));
    write_waveform(&root, &nonmonotonic);
    assert_waveform_invalid(&root, p, "timebase");

    let mut traversal = input(&root, &bytes);
    traversal["scenarios"][0]["raw_file"] = json!("../waveform.raw");
    assert_waveform_invalid(&root, traversal, "relative and contained");

    let mut absolute = input(&root, &bytes);
    absolute["scenarios"][0]["raw_file"] = json!(root.join("waveform.raw"));
    assert_waveform_invalid(&root, absolute, "relative and contained");

    let mut dual = input(&root, &bytes);
    dual["scenarios"][0]["raw_waveform"] = json!("ASCII");
    assert_waveform_invalid(&root, dual, "dual waveform");

    let mut unknown = input(&root, &bytes);
    unknown["scenarios"][0]["raw_format"] = json!("unknown");
    unknown["scenarios"][0]["spec"]["raw_format"] = json!("unknown");
    assert_waveform_invalid(&root, unknown, "unsupported waveform format");

    let mut mismatch = input(&root, &bytes);
    mismatch["scenarios"][0]["spec"]["raw_format"] = json!("ascii");
    assert_waveform_invalid(&root, mismatch, "not bound");

    let _ = fs::remove_dir_all(root);
}

#[cfg(unix)]
#[test]
fn binary_parser_rejects_symlink_escape() {
    use std::os::unix::fs::symlink;
    let root = root_path("symlink");
    let outside = root_path("outside");
    write_waveform(&outside, &fixture("", [0.0, 1.0, 2.0]));
    fs::create_dir_all(&root).unwrap();
    symlink(outside.join("waveform.raw"), root.join("link.raw")).unwrap();
    let bytes = fs::read(outside.join("waveform.raw")).unwrap();
    let mut payload = input(&root, &bytes);
    payload["scenarios"][0]["raw_file"] = json!("link.raw");
    assert_waveform_invalid(&root, payload, "escapes root");
    let _ = fs::remove_dir_all(root);
    let _ = fs::remove_dir_all(outside);
}

#[test]
fn settings_manifest_preserves_python_exponents_and_rejects_drift() {
    let root = root_path("settings");
    let bytes = fixture("", [0.0, 1e-8, 2e-8]);
    write_waveform(&root, &bytes);
    let mut payload = input(&root, &bytes);
    payload["scenarios"][0]["name"] = json!("startup");
    payload["scenarios"][0]["spec"]["window_end_s"] = json!(2e-8);
    payload["scenarios"][0]["spec"]["max_step_s"] = json!(2e-8);
    let manifest = serde_json::to_string(&vec![payload["scenarios"][0]["spec"].clone()])
        .unwrap()
        .replace("2e-8", "2e-08");
    assert!(manifest.contains("2e-08"));
    payload["settings_manifest"] = json!(manifest);
    payload["settings_sha256"] = json!(digest(manifest.as_bytes()));
    let baseline = run_with_payload(&root, payload.clone());
    assert_eq!(baseline["scenarios"][0]["status"], "pass", "{baseline}");
    assert!(!baseline["findings"]
        .as_array()
        .unwrap()
        .iter()
        .any(|f| f["id"] == "settings_identity_mismatch"));

    let ascii = "Flags: real\nNo. Variables: 5\nNo. Points: 3\nVariables:\n0 time time\n1 v(out) voltage\n2 v(in) voltage\n3 i(vin) current\n4 i(load) current\nValues:\n0 0 3.3 15 0.25 0.2\n1 1e-8 3.3 15 0.25 0.2\n2 2e-8 3.3 15 0.25 0.2\n";
    let mut ascii_payload = payload.clone();
    ascii_payload["scenarios"][0]
        .as_object_mut()
        .unwrap()
        .remove("raw_file");
    ascii_payload["scenarios"][0]["raw_waveform"] = json!(ascii);
    ascii_payload["scenarios"][0]["artifact_sha256"] = json!(digest(ascii.as_bytes()));
    ascii_payload["scenarios"][0]["raw_format"] = json!("ascii");
    ascii_payload["scenarios"][0]["spec"]["raw_format"] = json!("ascii");
    let ascii_manifest =
        serde_json::to_string(&vec![ascii_payload["scenarios"][0]["spec"].clone()]).unwrap();
    ascii_payload["settings_sha256"] = json!(digest(ascii_manifest.as_bytes()));
    ascii_payload["settings_manifest"] = json!(ascii_manifest);
    let ascii_result = run_with_payload(&root, ascii_payload);
    assert_eq!(baseline["scenarios"], ascii_result["scenarios"]);

    for mutation in ["digest", "spec", "manifest"] {
        let mut bad = payload.clone();
        match mutation {
            "digest" => bad["settings_sha256"] = json!("0".repeat(64)),
            "spec" => bad["scenarios"][0]["spec"]["target_v"] = json!(3.31),
            "manifest" => {
                let changed = manifest.replace("2e-08", "3e-08");
                bad["settings_sha256"] = json!(digest(changed.as_bytes()));
                bad["settings_manifest"] = json!(changed);
            }
            _ => unreachable!(),
        }
        let result = run_with_payload(&root, bad);
        assert!(
            result["findings"]
                .as_array()
                .unwrap()
                .iter()
                .any(|f| f["id"] == "settings_identity_mismatch"),
            "{mutation}: {result}"
        );
    }
    let _ = fs::remove_dir_all(root);
}

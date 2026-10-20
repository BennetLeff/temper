use std::fs;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use temper_lcr::{Complex, Point, Setup, Sweep};

#[test]
fn calibration_and_csv_commands_preserve_a_capacitors_negative_reactance() {
    let folder = std::env::temp_dir().join(format!(
        "temper-lcr-cli-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir(&folder).unwrap();
    let setup = Setup {
        board_revision: "A".into(),
        unit: "fixture-test".into(),
        fixture: "reference-plane".into(),
        range: "r20".into(),
        clock_hz: 16_000_000,
        excitation_range: 4,
        pga: 1,
        settling_cycles: 15,
        averages: 4,
        dft_sign: "AD5933-real-minus-i-imag".into(),
    };
    // Hand-derived linear fixture: offset10+j5; scale100000; series10ohm.
    for (name, re, im) in [
        ("open", 10.0, 5.0),
        ("a", 5010.0, 5.0),
        ("b", 2010.0, 5.0),
        ("dut", 2510.0, 2505.0),
    ] {
        let sweep = Sweep {
            schema: "temper-lcr-raw-v1".into(),
            captured_unix_seconds: 1,
            setup: setup.clone(),
            points: vec![Point {
                frequency_word: 1_677_721,
                frequency_hz: 1_677_721.0 * 16_000_000.0 / 536_870_912.0,
                raw: Complex::new(re, im),
                peak_dft_component: 10000,
            }],
        };
        fs::write(
            folder.join(format!("{name}.json")),
            serde_json::to_vec(&sweep).unwrap(),
        )
        .unwrap();
    }
    let cal = Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .current_dir(&folder)
        .args([
            "calibrate",
            "--open",
            "open.json",
            "--a",
            "a.json",
            "--ra",
            "10",
            "--b",
            "b.json",
            "--rb",
            "40",
            "--out",
            "cal.json",
        ])
        .output()
        .unwrap();
    assert!(
        cal.status.success(),
        "{}",
        String::from_utf8_lossy(&cal.stderr)
    );
    let result = Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .current_dir(&folder)
        .args([
            "convert", "--cal", "cal.json", "--raw", "dut.json", "--out", "dut.csv",
        ])
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let csv = fs::read_to_string(folder.join("dut.csv")).unwrap();
    let fields: Vec<_> = csv.lines().nth(1).unwrap().split(',').collect();
    assert!(
        (fields[2].parse::<f64>().unwrap() + 20.0).abs() < 1e-8
            && fields[9].contains("prototype_unqualified")
    );
    let duplicate = Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .current_dir(&folder)
        .args([
            "convert", "--cal", "cal.json", "--raw", "dut.json", "--out", "dut.csv",
        ])
        .output()
        .unwrap();
    assert!(!duplicate.status.success());
    fs::remove_dir_all(&folder).unwrap();
}

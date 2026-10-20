use temper_lcr::*;
fn packed(a: i16, b: i16) -> u32 {
    (0..16).fold(0, |v, i| {
        v | ((((a as u16 >> i) & 1) as u32) << (2 * i))
            | ((((b as u16 >> i) & 1) as u32) << (2 * i + 1))
    })
}
fn synthetic(z: Complex, range: u32) -> Record {
    let tuning_word = frequency_word(43721.0).unwrap();
    let f = frequency_hz(tuning_word);
    let a = z / feedback(range, f).unwrap() * Complex::new(8000.0, 0.0);
    let packed_samples: Vec<_> = (0..DEFAULT_COUNT)
        .map(|i| {
            let p = std::f64::consts::TAU * f * i as f64 / SAMPLE_BASE_HZ;
            packed(
                (123.0 + a.re * p.cos() - a.im * p.sin()).round() as i16,
                (-213.0 + 8000.0 * p.cos()).round() as i16,
            )
        })
        .collect();
    let bytes: Vec<_> = packed_samples
        .iter()
        .flat_map(|v| v.to_le_bytes())
        .collect();
    Record {
        source_enabled: true,
        tuning_word,
        sample_divider: 1,
        packed_samples,
        transport_crc32: crc32(&bytes),
    }
}
#[test]
fn signed_wire_order_and_crc() {
    assert_eq!(decode_word(packed(-32768, 0x1234)), [-32768, 0x1234]);
    assert_eq!(decode_word(packed(-1, 0)), [-1, 0]);
    assert_eq!(crc32(b"123456789"), 0xcbf43926);
}
#[test]
fn noncoherent_capacitor_and_inductor() {
    for z in [Complex::new(5.0, -26.0), Complex::new(10.0, 30.0)] {
        let m = analyze(&synthetic(z, 100), 100).unwrap();
        assert!(m.valid);
        assert!((m.impedance_ohm - z).abs() < 0.002);
        assert_eq!(m.series_capacitance_f.is_some(), z.im < 0.0);
        assert_eq!(m.series_inductance_h.is_some(), z.im > 0.0);
    }
}
#[test]
fn parallel_feedback_capacitance() {
    let z = Complex::new(25000.0, -12000.0);
    let m = analyze(&synthetic(z, 100000), 100000).unwrap();
    assert!(m.valid);
    assert!((m.impedance_ohm - z).abs() < 1.0);
    let f = feedback(100000, 100000.0).unwrap();
    assert!((f.im.atan2(f.re).to_degrees() + 17.44059449).abs() < 1e-6);
}
#[test]
fn bilinear_fixture_recovers_complex_dut() {
    let a = Complex::new(1.08, 0.03);
    let b = Complex::new(0.4, 0.05);
    let c = Complex::new(0.0002, 0.0001);
    let one = Complex::new(1.0, 0.0);
    let forward = |z| (a * z + b) / (c * z + one);
    let got = calibration_coefficients(
        b,
        forward(Complex::new(20.0, 0.0)),
        20.0,
        forward(Complex::new(100.0, 0.0)),
        100.0,
    )
    .unwrap();
    for z in [Complex::new(7.0, -28.0), Complex::new(14.0, 22.0)] {
        let m = forward(z);
        let recovered = (m - got[1]) / (got[0] - m * got[2]);
        assert!((recovered - z).abs() < 1e-10);
    }
}
#[test]
fn corruption_and_weak_signal_rejected() {
    let mut r = synthetic(Complex::new(5.0, -26.0), 100);
    r.packed_samples[50] ^= 1;
    assert!(analyze(&r, 100).is_err());
    let m = analyze(&synthetic(Complex::new(0.001, 0.0), 100), 100).unwrap();
    assert!(!m.valid);
    assert!(calibration_coefficients(
        Complex::default(),
        Complex::new(1.0, 0.0),
        100.0,
        Complex::new(2.0, 0.0),
        100.0
    )
    .is_err());
}
#[test]
fn noise_records_cannot_be_impedance() {
    let mut r = synthetic(Complex::new(5.0, -26.0), 100);
    assert!(noise(&r).is_err());
    r.source_enabled = false;
    assert!(analyze(&r, 100).is_err());
    let n = noise(&r).unwrap();
    assert!((n.tone_peak_codes[1] - 8000.0).abs() < 0.1);
    assert!((n.rms_codes[1] - 8000.0 / 2.0f64.sqrt()).abs() < 2.0);
}
#[test]
fn clock_and_frequency_bounds() {
    assert_eq!(frequency_word(100000.0).unwrap(), 1118481);
    assert!(frequency_word(f64::NAN).is_err());
    assert!(frequency_word(99.0).is_err());
    assert_eq!(divider_for(100.0), 20);
    assert_eq!(divider_for(60000.0), 1);
}
fn setup() -> Setup {
    Setup {
        revision: "B".into(),
        unit_id: "test-device".into(),
        fixture: "fixture-1".into(),
        range_ohm: 100,
        system_clock_hz: 120000000,
        dds_clock_hz: 24000000,
    }
}
#[test]
fn full_calibration_and_identity_checks() {
    let sweep = |z| Sweep {
        setup: setup(),
        records: vec![synthetic(z, 100)],
    };
    let s = sweep(Complex::new(0.2, 0.03));
    let a = sweep(Complex::new(20.6, 0.43));
    let b = sweep(Complex::new(102.2, 2.03));
    let cal = calibrate(&s, &a, 20.0, &b, 100.0).unwrap();
    let true_z = Complex::new(7.0, -26.0);
    let r = synthetic(
        Complex::new(1.02, 0.02) * true_z + Complex::new(0.2, 0.03),
        100,
    );
    let mut m = analyze(&r, 100).unwrap();
    correct(&mut m, &r, &setup(), &cal).unwrap();
    assert!(m.calibrated);
    assert!((m.impedance_ohm - true_z).abs() < 0.003);
    let mut wrong = setup();
    wrong.fixture = "different".into();
    assert!(correct(&mut m, &r, &wrong, &cal).is_err());
    wrong = setup();
    wrong.system_clock_hz = 125000000;
    assert!(wrong.validate().is_err());
}
#[test]
fn cli_produces_correct_negative_reactance() {
    let folder = std::env::temp_dir().join(format!("temper-lcr-revb-test-{}", std::process::id()));
    std::fs::create_dir_all(&folder).unwrap();
    let file = folder.join("capture.json");
    let s = Sweep {
        setup: setup(),
        records: vec![synthetic(Complex::new(5.0, -26.0), 100)],
    };
    std::fs::write(&file, serde_json::to_vec(&s).unwrap()).unwrap();
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_temper-lcr"))
        .arg("analyze")
        .arg(&file)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let values: Vec<Measurement> = serde_json::from_slice(&output.stdout).unwrap();
    assert!(values[0].impedance_ohm.im < 0.0);
    assert!(values[0].valid);
    std::fs::remove_dir_all(folder).unwrap();
}
#[test]
fn firmware_host_clock_contract() {
    let pins = include_str!("../../firmware/src/pins.h");
    let constant = |name: &str| -> u32 {
        pins.lines()
            .find_map(|line| {
                let parts: Vec<_> = line.split_whitespace().collect();
                (parts.len() >= 3 && parts[0] == "#define" && parts[1] == name)
                    .then(|| parts[2].trim_end_matches('u').parse().unwrap())
            })
            .unwrap()
    };
    assert_eq!(constant("SYSTEM_CLOCK_HZ"), setup().system_clock_hz);
    assert_eq!(f64::from(constant("DDS_CLOCK_HZ")), DDS_CLOCK_HZ);
    assert_eq!(constant("SYSTEM_CLOCK_HZ") / 5, constant("DDS_CLOCK_HZ"));
    assert_eq!(
        constant("SYSTEM_CLOCK_HZ") / constant("CAPTURE_CYCLES"),
        SAMPLE_BASE_HZ as u32
    );
}

//! Closed-form line integrals: no production quadrature or emitted samples.
use std::f64::consts::{PI, SQRT_2};
use zapote_erc::pfc_currents::{Config, calculate};

fn nominal() -> Config {
    Config {
        line_rms_v: 120.,
        input_rms_limit_a: 15.,
        bus_v: 389.615,
        inductance_h: 180e-6,
        switching_hz: 129_000.,
        phase_samples: 2048,
    }
}

// Over a full cycle E[|sin|^n] for n=2..5 is known analytically.
// delta = k(s - m*s²). Integrate its square directly, independently of
// the production midpoint/Gauss-point loops.
fn reference(c: Config) -> [f64; 6] {
    let m = SQRT_2 * c.line_rms_v / c.bus_v;
    let k = SQRT_2 * c.line_rms_v / (c.inductance_h * c.switching_hz);
    let [s2, s3, s4, s5] = [0.5, 4. / (3. * PI), 3. / 8., 16. / (15. * PI)];
    let variance = k * k / 12. * (s2 - 2. * m * s3 + m * m * s4);
    let fundamental_sq = c.input_rms_limit_a.powi(2) - variance;
    let diode_sq = m * (2. * fundamental_sq * s3 + k * k / 12. * (s3 - 2. * m * s4 + m * m * s5));
    let power = c.line_rms_v * fundamental_sq.sqrt();
    let load = power / c.bus_v;
    [
        fundamental_sq.sqrt(),
        power,
        (c.input_rms_limit_a.powi(2) - diode_sq).sqrt(),
        diode_sq.sqrt(),
        load,
        (diode_sq - load * load).sqrt(),
    ]
}

#[test]
fn branch_moments_match_closed_form_line_integrals() {
    for (volts, amps, bus, inductance, frequency) in [
        (120., 15., 389.615, 180e-6, 129_000.),
        (90., 12., 400., 300e-6, 65_000.),
        (230., 8., 400., 500e-6, 100_000.),
    ] {
        let c = Config {
            line_rms_v: volts,
            input_rms_limit_a: amps,
            bus_v: bus,
            inductance_h: inductance,
            switching_hz: frequency,
            ..nominal()
        };
        let p = calculate(c).unwrap();
        let actual = [
            p.fundamental_rms_a,
            p.input_power_w,
            p.switch_rms_a,
            p.diode_rms_a,
            p.load_rms_a,
            p.capacitor_rms_a,
        ];
        for (actual, expected) in actual.into_iter().zip(reference(c)) {
            assert!(
                (actual - expected).abs() < 1e-8 * expected.abs().max(1.),
                "{c:?}: actual={actual}, closed-form={expected}"
            );
        }
    }
}

#[test]
fn ccm_validity_cannot_depend_on_missing_a_line_zero_crossing() {
    let mut c = nominal();
    let k = SQRT_2 * c.line_rms_v / (c.inductance_h * c.switching_hz);
    let fundamental = reference(c)[0];
    let ripple_variance = c.input_rms_limit_a.powi(2) - fundamental.powi(2);
    // Near a line zero, valley/sin(theta) -> Ipeak - k/2. A value
    // 0.5% below this limit enters DCM even if coarse quadrature misses it.
    c.input_rms_limit_a = ((0.995 * k / (2. * SQRT_2)).powi(2) + ripple_variance).sqrt();
    for n in [32, 256, 2048] {
        c.phase_samples = n;
        assert!(calculate(c).is_err(), "accepted DCM at {n} phase samples");
    }
}

#[test]
fn current_samples_match_pinned_independent_ngspice_measurements() {
    use sha2::{Digest, Sha256};
    use std::{collections::BTreeMap, fs, path::Path};
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../validation/p1-current/oracle-2026-09-12/spice");
    // Immutable receipt pin: rebaseline only with a reviewed new solver run.
    // Include names and lengths so both file identity and contents are bound.
    let mut files = BTreeMap::new();
    for name in ["result.json".to_owned(), "ngspice-version.txt".to_owned()]
        .into_iter()
        .chain([2, 23, 55].into_iter().flat_map(|phase| {
            ["5.0e-9", "2.5e-9"].into_iter().flat_map(move |step| {
                ["cir", "log"]
                    .into_iter()
                    .map(move |ext| format!("phase-{phase}-step-{step}.{ext}"))
            })
        }))
    {
        files.insert(
            name.clone(),
            fs::read(root.join(name)).expect("retained solver evidence"),
        );
    }
    let mut hash = Sha256::new();
    for (name, bytes) in &files {
        hash.update((name.len() as u64).to_be_bytes());
        hash.update(name.as_bytes());
        hash.update((bytes.len() as u64).to_be_bytes());
        hash.update(bytes);
    }
    assert_eq!(
        format!("{:x}", hash.finalize()),
        "f30ac7a2d6e954101a6d34d96cc46f3b4b36160b90ae18a89fc604d5dfb5c249",
        "retained solver evidence changed; do not replace external measurements with model outputs"
    );
    let evidence: serde_json::Value = serde_json::from_str(include_str!(
        "../../../validation/p1-current/oracle-2026-09-12/spice/result.json"
    ))
    .unwrap();
    assert_eq!(evidence["status"], "pass");
    let p = calculate(Config {
        phase_samples: 256,
        ..nominal()
    })
    .unwrap();
    let rows = evidence["results"].as_array().unwrap();
    assert_eq!(rows.len(), 6);
    for row in rows {
        let phase = row["phase_index"].as_u64().unwrap() as usize;
        let local = &p.samples[phase * 8..(phase + 1) * 8];
        let log = std::str::from_utf8(&files[row["log"].as_str().unwrap()]).unwrap();
        for (index, field) in [
            (|s: &zapote_erc::pfc_currents::Sample| s.inductor_a)
                as fn(&zapote_erc::pfc_currents::Sample) -> f64,
            |s| s.switch_a,
            |s| s.diode_a,
            |s| s.capacitor_a,
        ]
        .into_iter()
        .enumerate()
        {
            let actual = local
                .iter()
                .map(|s| s.weight * 256. * field(s).powi(2))
                .sum::<f64>()
                .sqrt();
            let field_name = ["inductor_rms", "switch_rms", "diode_rms", "capacitor_rms"][index];
            let measured: f64 = log
                .lines()
                .find_map(|line| {
                    let (key, value) = line.split_once('=')?;
                    (key.trim() == field_name)
                        .then(|| value.split_whitespace().next().unwrap().parse().unwrap())
                })
                .expect("actual ngspice measurement");
            assert_eq!(measured, row["ngspice_rms_a"][index].as_f64().unwrap());
            assert!(
                (actual - measured).abs() < 5e-4 * measured,
                "phase={phase}, branch={index}: Rust={actual}, ngspice={measured}"
            );
        }
    }
}

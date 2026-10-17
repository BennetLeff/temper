use proptest::prelude::*;
use zapote_drc::layout_quality::{coupling::*, decoupling, returns, thermal};

fn magnetic(m: f64, slew: f64) -> InductiveTerm {
    InductiveTerm {
        object: "P1->P3".into(),
        mutual_nh: m,
        slew_a_per_ns: slew,
    }
}
fn electric(c: f64, slew: f64) -> CapacitiveTerm {
    CapacitiveTerm {
        object: "SW->sense".into(),
        capacitance_pf: c,
        slew_v_per_ns: slew,
    }
}
fn shared(r: f64, l: f64, i: f64, slew: f64) -> SharedImpedance {
    SharedImpedance {
        object: "R5-return".into(),
        resistance_ohm: r,
        inductance_nh: l,
        current_a: i,
        slew_a_per_ns: slew,
    }
}
fn close(a: f64, b: f64) {
    assert!(
        (a - b).abs() <= 1e-10 * (1.0 + a.abs() + b.abs()),
        "{a} != {b}"
    );
}

#[test]
fn displacement_current_uses_picofarads_and_nanoseconds() {
    let (current, bound) = displacement_current(&[electric(2.0, 10.0)]).unwrap();
    close(current, 0.02);
    close(bound, 0.02);
}
#[test]
fn kelvin_cancellation_preserves_independent_sign_bound() {
    let input = KelvinInput {
        shared: vec![shared(0.0001, 0.0, 10.0, 0.0)],
        magnetic: vec![magnetic(0.0, 0.0)],
        positive_pickup: vec![electric(1.0, 1.0)],
        negative_pickup: vec![electric(1.0, 1.0)],
        positive_transfer_ohm: 10.0,
        negative_transfer_ohm: 10.0,
        shunt_ohm: 0.001,
    };
    let r = kelvin_error(&input).unwrap();
    close(r.error_v, 0.001);
    close(r.equivalent_current_error_a, 1.0);
    close(r.current_error_bound_a, 21.0);
}
#[test]
fn emi_bypass_combines_inductive_and_capacitive_bounds() {
    close(
        emi_bypass_voltage(&[magnetic(-2.0, 0.1)], &[electric(3.0, 2.0)], 50.0).unwrap(),
        0.5,
    );
}
#[test]
fn nonfinite_and_empty_electrical_inputs_are_not_zero_noise() {
    assert!(induced_voltage(&[]).is_err());
    assert!(displacement_current(&[]).is_err());
    assert!(shared_voltage(&[]).is_err());
    for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        assert!(induced_voltage(&[magnetic(bad, 1.0)]).is_err());
        assert!(displacement_current(&[electric(1.0, bad)]).is_err());
        assert!(shared_voltage(&[shared(1.0, 1.0, bad, 1.0)]).is_err());
    }
    assert!(induced_voltage(&[magnetic(f64::MAX, 2.0)]).is_err());
    assert!(induced_voltage(&[magnetic(1.0, 1.0), magnetic(2.0, 1.0)]).is_err());
    assert!(displacement_current(&[electric(-1.0, 1.0)]).is_err());
    assert!(shared_voltage(&[shared(-1.0, 1.0, 1.0, 1.0)]).is_err());
}
#[test]
fn real_leg_a_matrix_preserves_port_orientation_and_mutual_sign() {
    let source = include_str!("../../../power-stage-120v/validation-results/01-switching-parasitics/round17/d2/legA-h0-lin12-m20corr.matrix.txt");
    let matrix: serde_json::Value =
        serde_json::from_str(source.trim().strip_prefix("RESULT ").unwrap()).unwrap();
    assert_eq!(matrix["names"][2], "P3_gate_high");
    let m = matrix["L0_nH"][2][3].as_f64().unwrap();
    let r = induced_voltage(&[magnetic(m, 1.0)]).unwrap();
    close(r.signed_v, -0.2134); // Unit-slew sensitivity, NOT an operating waveform.
}
#[test]
fn rlc_series_resonance_and_parallel_sharing_match_closed_form() {
    let b = decoupling::Branch {
        object: "C38".into(),
        capacitance_f: 1e-6,
        resistance_ohm: 0.1,
        inductance_h: 1e-8,
    };
    let frequency = 1.0 / (std::f64::consts::TAU * (b.capacitance_f * b.inductance_h).sqrt());
    let mut b2 = b.clone();
    b2.object = "C39".into();
    let result = decoupling::sweep(&[b, b2], &[frequency]).unwrap();
    close(result[0].impedance_ohm, 0.05);
    close(result[0].branch_current_ratios[0], 0.5);
}
#[test]
fn antiresonance_can_have_branch_current_larger_than_total() {
    let branches = vec![
        decoupling::Branch {
            object: "a".into(),
            capacitance_f: 1e-6,
            resistance_ohm: 0.001,
            inductance_h: 1e-8,
        },
        decoupling::Branch {
            object: "b".into(),
            capacitance_f: 1e-8,
            resistance_ohm: 0.001,
            inductance_h: 1e-8,
        },
    ];
    let omega =
        ((1.0 / branches[0].capacitance_f + 1.0 / branches[1].capacitance_f) / 2e-8_f64).sqrt();
    let r = decoupling::sweep(&branches, &[omega / std::f64::consts::TAU]).unwrap();
    assert!(r[0].branch_current_ratios.iter().all(|i| *i > 1.0));
    assert!(r[0].impedance_ohm > 100.0);
}
#[test]
fn decoupling_rejects_missing_sweep_or_lossless_resonance() {
    let b = decoupling::Branch {
        object: "C".into(),
        capacitance_f: 1e-6,
        resistance_ohm: 0.0,
        inductance_h: 1e-8,
    };
    assert!(decoupling::sweep(&[b], &[1e6]).is_err());
    assert!(decoupling::sweep(&[], &[1e6]).is_err());
}
#[test]
fn decoupling_overflow_cannot_silently_remove_capacitive_reactance() {
    let branch = decoupling::Branch {
        object: "invalid-capacitance-scale".into(),
        capacitance_f: f64::MAX,
        resistance_ohm: 1.0,
        inductance_h: 0.0,
    };
    assert!(decoupling::sweep(&[branch], &[1.0]).is_err());
}
#[test]
fn thermal_model_keeps_calibration_drift_and_domain_explicit() {
    let mut input = thermal::Input {
        object: "REF25".into(),
        ambient_c: 30.0,
        reference_c: 25.0,
        coefficient_ppm_per_k: -10.0,
        valid_temperature_c: [-40.0, 85.0],
        influences: vec![thermal::Influence {
            object: "Q2".into(),
            power_w: 5.0,
            transfer_k_per_w: 2.0,
        }],
    };
    let result = thermal::evaluate(&input).unwrap();
    close(result.temperature_c, 40.0);
    close(result.drift_ppm, -150.0);
    input.influences[0].power_w = 100.0;
    assert!(thermal::evaluate(&input).is_err());
}
#[test]
fn return_length_includes_vias_and_reports_shared_noise_separately() {
    let input = returns::Input {
        object: "gate-return".into(),
        points_mm: vec![
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [3.0, 0.0, 1.0],
            [3.0, 0.0, 0.0],
        ],
        shared: vec![shared(0.01, 2.0, 1.0, 0.1)],
    };
    let r = returns::evaluate(&input).unwrap();
    close(r.route_length_mm, 5.0);
    close(r.detour_ratio, 5.0 / 3.0);
    close(r.shared_voltage_v, 0.21);
}

proptest! {
    #[test]
    fn reversing_both_port_and_current_orientation_preserves_pickup(
        m in -100.0..100.0,
        slew in -10.0..10.0,
    ) {
        let a = induced_voltage(&[magnetic(m, slew)]).unwrap();
        let b = induced_voltage(&[magnetic(-m, -slew)]).unwrap();
        prop_assert_eq!(a.signed_v, b.signed_v);
    }
    #[test]
    fn signed_pickup_never_exceeds_independent_bound(
        values in prop::collection::vec((-100.0..100.0, -10.0..10.0),1..40),
    ) {
        let terms: Vec<_> = values
            .iter()
            .enumerate()
            .map(|(i, (m, s))| InductiveTerm {
                object: i.to_string(),
                mutual_nh: *m,
                slew_a_per_ns: *s,
            })
            .collect();
        let r = induced_voltage(&terms).unwrap();
        prop_assert!(r.signed_v.abs() <= r.independent_sign_bound_v * (1.0 + 1e-12));
    }
    #[test]
    fn parallel_identical_decouplers_halve_impedance(
        c in 1e-9..1e-4,
        l in 1e-10..1e-6,
        r in 0.001..1.0,
        f in 1e3..1e8,
    ) {
        let a = decoupling::Branch {
            object: "a".into(),
            capacitance_f: c,
            resistance_ohm: r,
            inductance_h: l,
        };
        let mut b = a.clone();
        b.object = "b".into();
        let single = decoupling::sweep(std::slice::from_ref(&a), &[f]).unwrap();
        let pair = decoupling::sweep(&[a, b], &[f]).unwrap();
        prop_assert!(
            (single[0].impedance_ohm - 2.0 * pair[0].impedance_ohm).abs()
                < 1e-9 * (1.0 + single[0].impedance_ohm)
        );
    }
    #[test]
    fn thermal_rise_is_monotone_in_positive_power(
        p in 0.0..100.0,
        delta in 0.0..100.0,
        theta in 0.0..2.0,
    ) {
        let mut input = thermal::Input {
            object: "R5".into(),
            ambient_c: 25.0,
            reference_c: 25.0,
            coefficient_ppm_per_k: 10.0,
            valid_temperature_c: [-40.0, 1000.0],
            influences: vec![thermal::Influence {
                object: "Q2".into(),
                power_w: p,
                transfer_k_per_w: theta,
            }],
        };
        let a = thermal::evaluate(&input).unwrap();
        input.influences[0].power_w += delta;
        let b = thermal::evaluate(&input).unwrap();
        prop_assert!(b.temperature_c >= a.temperature_c);
    }
    #[test]
    fn subdividing_a_straight_return_does_not_change_its_detour(
        x in 0.1..100.0,
        fraction in 0.01..0.99,
    ) {
        let mut input = returns::Input {
            object: "return".into(),
            points_mm: vec![[0.0, 0.0, 0.0], [x, 2.0 * x, 0.0]],
            shared: vec![shared(0.0, 0.0, 0.0, 0.0)],
        };
        let a = returns::evaluate(&input).unwrap();
        input
            .points_mm
            .insert(1, [x * fraction, 2.0 * x * fraction, 0.0]);
        let b = returns::evaluate(&input).unwrap();
        prop_assert!((a.route_length_mm - b.route_length_mm).abs() < 1e-10);
    }
}

use zapote_erc::pfc_control::{calculate, evaluate_selected, PfcControlInput};

fn ti_example() -> PfcControlInput {
    PfcControlInput {
        input_power_w: 360.0 / 0.92,
        vin_rms: 115.0,
        vout: 390.0,
        cout: 270e-6,
        rsense: 0.032,
        fsw: 118_000.0,
        gmi: 0.95e-3,
        gmv: 56e-6,
        k1: 7.0,
        rfb1: 1e6,
        rfb2: 13e3,
        fvoltage: 10.0,
        fpole: 20.0,
    }
}

#[test]
fn reproduces_ti_m1m2_and_frequency_scale() {
    let r = calculate(ti_example()).unwrap();
    assert!((r.m1m2 - 0.751).abs() < 0.02, "{}", r.m1m2);
    assert!((r.vcomp - 3.004).abs() < 0.08, "{}", r.vcomp);
    assert!((r.cicomp - 2.33e-9).abs() < 0.15e-9, "{}", r.cicomp);
    assert!((r.f_pwm_ps - 1.479).abs() < 0.1, "{}", r.f_pwm_ps);
}

#[test]
fn calculates_1800w_nominal_case() {
    let mut i = ti_example();
    i.input_power_w = 1800.0;
    i.vin_rms = 120.0;
    i.cout = 2240e-6;
    i.rsense = 0.010;
    i.fsw = 130_000.0;
    let r = calculate(i).unwrap();
    assert!(r.m1m2 > 1.0 && r.m1m2 < 1.2);
    assert!((r.f_pwm_ps - 0.80).abs() < 0.3, "{}", r.f_pwm_ps);
    assert!(r.crossover_hz.is_finite() && r.phase_margin_deg.is_finite());
}

#[test]
fn rejects_bad_inputs_and_out_of_range_m1m2() {
    let mut i = ti_example();
    i.vout = f64::NAN;
    assert!(calculate(i).is_err());
    let mut i = ti_example();
    i.rsense = 1.0;
    assert!(calculate(i).is_err());
    let i = ti_example();
    assert!(evaluate_selected(&i, 2.7e-9, 4.7e-6, 40.2e3, 220e-9).is_ok());
    assert!(evaluate_selected(&i, 2.7e-9, 4.7e-6, 40.2e3, -220e-9).is_err());
    let mut i = ti_example();
    i.gmv = 1e-12;
    assert!(evaluate_selected(&i, 2.7e-9, 4.7e-6, 40.2e3, 220e-9).is_err());
}

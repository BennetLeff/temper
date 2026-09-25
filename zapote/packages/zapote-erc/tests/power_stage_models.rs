use zapote_erc::power_stage_models as model;

fn config(dt: f64) -> model::DoublerConfig {
    model::DoublerConfig {
        line_rms_v: 120.0,
        line_hz: 60.0,
        load_w: 1800.0,
        diode_drop_v: 1.2,
        series_r_ohm: 1.0,
        capacitance_per_physical_cap_f: 1800e-6,
        parallel_caps_per_half: 2,
        timestep_s: dt,
        cycles: 120,
        convergence_tolerance: 1e-3,
    }
}

#[test]
fn nominal_doubler_conserves_energy_and_has_expected_current() {
    let r = model::simulate_doubler(config(2e-6)).unwrap();
    assert!(r.input_rms_a > 20.0 && r.input_rms_a < 27.0);
    assert!(r.energy_balance_error_w.abs() < 1.0);
    assert!((r.physical_cap_rms_a - 7.44).abs() < 0.1);
}

#[test]
fn timestep_converges() {
    let a = model::simulate_doubler(config(2e-6)).unwrap();
    let b = model::simulate_doubler(config(1e-6)).unwrap();
    assert!((a.input_rms_a - b.input_rms_a).abs() < 0.05);
    assert!((a.bus_ripple_pp_v - b.bus_ripple_pp_v).abs() < 0.1);
}

#[test]
fn cold_tcr_and_initial_tolerance_are_independent_corners() {
    let a = model::dead_time_corners(39.0, 0.01, 100.0, &[-40.0], (1.0, 1.0)).unwrap();
    let minimum = 8.6 * 39.0 * 0.99 * (1.0 - 65.0 * 100e-6) + 13.0;
    assert!((a.min_ns - minimum).abs() < 1e-10);
}

#[test]
fn requested_work_and_equation_domain_are_bounded() {
    let mut c = config(2e-6);
    c.cycles = u32::MAX;
    assert!(model::simulate_doubler(c).is_err());
    assert!(model::dead_time_corners(101.0, 0.01, 100.0, &[25.0], (0.9, 1.1)).is_err());
}

#[test]
fn parallel_scaling_preserves_bus_and_halves_per_cap_current() {
    let mut one = config(2e-6);
    one.capacitance_per_physical_cap_f = 3600e-6;
    one.parallel_caps_per_half = 1;
    let two = config(2e-6);
    let a = model::simulate_doubler(one).unwrap();
    let b = model::simulate_doubler(two).unwrap();
    assert!((a.input_rms_a - b.input_rms_a).abs() < 0.01);
    assert!((a.bus_ripple_pp_v - b.bus_ripple_pp_v).abs() < 0.01);
    assert!((a.physical_cap_rms_a - 2.0 * b.physical_cap_rms_a).abs() < 0.01);
}

#[test]
fn dead_time_34k_fails_and_39k_passes_300ns_floor() {
    let a = model::dead_time_corners(34.0, 0.01, 100.0, &[-40.0, 25.0, 125.0], (0.9, 1.1)).unwrap();
    let b = model::dead_time_corners(39.0, 0.01, 100.0, &[-40.0, 25.0, 125.0], (0.9, 1.1)).unwrap();
    assert!(a.min_ns < 300.0);
    assert!(b.min_ns >= 300.0);
    assert!(b.max_ns > 360.0);
}

#[test]
fn invalid_and_nonconverged_inputs_fail_closed() {
    assert!(matches!(
        model::simulate_doubler(model::DoublerConfig { ..config(1.0) }),
        Err(model::ModelError::InvalidInput(_))
    ));
    assert!(model::dead_time_corners(39.0, 0.01, 100.0, &[f64::NAN], (0.9, 1.1)).is_err());
    assert!(model::dead_time_corners(39.0, 0.01, -100.0, &[25.0], (0.9, 1.1)).is_err());
    assert!(model::dead_time_corners(39.0, 0.01, 100.0, &[-41.0], (0.9, 1.1)).is_err());
    let mut short = config(2e-6);
    short.cycles = 8;
    short.convergence_tolerance = 1e-12;
    assert!(matches!(
        model::simulate_doubler(short),
        Err(model::ModelError::NonConverged { .. })
    ));
}

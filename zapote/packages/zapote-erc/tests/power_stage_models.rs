use zapote_erc::power_stage_models as model;

#[test]
fn cold_tcr_and_initial_tolerance_are_independent_corners() {
    let a = model::dead_time_corners(39.0, 0.01, 100.0, &[-40.0], (1.0, 1.0)).unwrap();
    let minimum = 8.6 * 39.0 * 0.99 * (1.0 - 65.0 * 100e-6) + 13.0;
    assert!((a.min_ns - minimum).abs() < 1e-10);
}

#[test]
fn equation_domain_is_bounded() {
    assert!(model::dead_time_corners(101.0, 0.01, 100.0, &[25.0], (0.9, 1.1)).is_err());
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
fn invalid_inputs_fail_closed() {
    assert!(model::dead_time_corners(39.0, 0.01, 100.0, &[f64::NAN], (0.9, 1.1)).is_err());
    assert!(model::dead_time_corners(39.0, 0.01, -100.0, &[25.0], (0.9, 1.1)).is_err());
    assert!(model::dead_time_corners(39.0, 0.01, 100.0, &[-41.0], (0.9, 1.1)).is_err());
}

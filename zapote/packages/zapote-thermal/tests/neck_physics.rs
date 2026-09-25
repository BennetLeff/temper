use zapote_thermal::neck_physics::{parse_validate, sif, Params};

const LOG: &[u8] = include_bytes!("neck-physics-fixture/solver.log");
const DATA: &[u8] = include_bytes!("neck-physics-fixture/scalars.dat");
const NAMES: &[u8] = include_bytes!("neck-physics-fixture/scalars.dat.names");
const CONSTANT_LOG: &[u8] = include_bytes!("neck-physics-constant-fixture/solver.log");
const CONSTANT_DATA: &[u8] = include_bytes!("neck-physics-constant-fixture/scalars.dat");
const CONSTANT_NAMES: &[u8] = include_bytes!("neck-physics-constant-fixture/scalars.dat.names");

fn params() -> Params {
    Params {
        current_a: 15.0,
        ambient_k: 293.15,
        terminal_k: 333.15,
        board_k: 293.15,
        convection_w_m2k: 8.0,
        terminal_conductance_w_k: 0.02,
        board_conductance_w_k: 0.08,
        conductivity_s_m: 5.8e7,
        alpha_per_k: 0.00393,
        copper_k_w_mk: 400.0,
        fr4_k_w_mk: 0.3,
    }
}

#[test]
fn captured_neck_fixture_has_independent_energy_and_electrical_checks() {
    let measurement = parse_validate(LOG, DATA, NAMES, &params(), [2e-6, 2e-6, 6e-5]).unwrap();
    assert!(measurement.energy_balance_residual_w.abs() < 1e-9);
    assert!(measurement.electrical_residual_w.abs() < 1e-9);
    assert_eq!(measurement.converged_iterations, 4);
    assert!(measurement.terminal_relative_change.unwrap() < 1e-8);
}

#[test]
fn scalar_mutations_fail_closed() {
    let mut data = DATA.to_vec();
    data = String::from_utf8_lossy(&data)
        .replacen("2.000000000000E-006", "3.000000000000E-006", 1)
        .into_bytes();
    assert!(parse_validate(LOG, &data, NAMES, &params(), [2e-6, 2e-6, 6e-5]).is_err());

    let mut names = NAMES.to_vec();
    names = String::from_utf8_lossy(&names)
        .replacen("max: temperature", "max: potential", 1)
        .into_bytes();
    assert!(parse_validate(LOG, DATA, &names, &params(), [2e-6, 2e-6, 6e-5]).is_err());

    let no_convergence = LOG
        .split(|byte| *byte == b'\n')
        .filter(|line| {
            !line
                .windows(b"TEMPERATURE ITERATION".len())
                .any(|window| window == b"TEMPERATURE ITERATION")
                && !line
                    .windows(b"Relative Change".len())
                    .any(|window| window == b"Relative Change")
        })
        .flat_map(|line| line.iter().copied().chain(std::iter::once(b'\n')))
        .collect::<Vec<_>>();
    assert!(parse_validate(&no_convergence, DATA, NAMES, &params(), [2e-6, 2e-6, 6e-5]).is_err());

    let malformed_log = String::from_utf8_lossy(LOG).replace(
        "Total Heating Power   :   2.0172730501769934E-002",
        "Total Heating Power   :   corrupted",
    );
    assert!(parse_validate(
        malformed_log.as_bytes(),
        DATA,
        NAMES,
        &params(),
        [2e-6, 2e-6, 6e-5]
    )
    .is_err());
}

#[test]
fn sif_binds_area_current_and_robin_conductance() {
    let mut altered = params();
    altered.ambient_k = 313.15;
    let text = sif(&altered, [2e-6, 2e-6, 6e-5]).unwrap();
    assert!(text.contains("Mesh DB \".\" \"neck\""));
    assert!(text.contains("Current Density = 7.500000000000e6"));
    assert!(text.contains("Heat Transfer Coefficient = 1.000000000000e4"));
    assert!(text.contains("Heat Transfer Coefficient = 4.000000000000e4"));
    assert!(text.contains("Target Bodies(1) = 2"));
    assert!(text.contains("tx-293.15"));
    assert!(text.contains("External Temperature = 313.150000000000"));
}

#[test]
fn invalid_physics_inputs_are_rejected() {
    let mut p = params();
    p.current_a = f64::NAN;
    assert!(sif(&p, [2e-6, 2e-6, 6e-5]).is_err());
    p = params();
    p.fr4_k_w_mk = 0.0;
    assert!(sif(&p, [2e-6, 2e-6, 6e-5]).is_err());
}

#[test]
fn constant_robin_oracle_corroborates_constant_sigma_reference() {
    use sha2::{Digest, Sha256};
    assert_eq!(
        format!(
            "{:x}",
            Sha256::digest(include_bytes!("neck-physics-constant-fixture/case.sif"))
        ),
        "445008d9c69e5b95fa2dec8f58015db1dbdbc6229ec7a3ff7d79eab1323e7d93"
    );
    let mut p = params();
    p.alpha_per_k = 0.0;
    let result =
        zapote_thermal::neck_physics::constant_robin_bar_oracle(&p, 0.01, 0.002, 0.001).unwrap();
    assert!((result.power_w - 0.01939655172414).abs() < 1.0e-12);
    assert!((result.max_temperature_k - 306.6625159273).abs() < 1.0e-3);
    assert!((result.min_temperature_k - 299.9532897972).abs() < 1.0e-3);

    let measured = parse_validate(
        CONSTANT_LOG,
        CONSTANT_DATA,
        CONSTANT_NAMES,
        &p,
        [2e-6, 2e-6, 6e-5],
    )
    .unwrap();
    assert!((measured.joule_power_w - result.power_w).abs() < 1.0e-9);
    assert!((measured.max_temperature_k - result.max_temperature_k).abs() < 1.0e-3);
    assert!((measured.min_temperature_k - result.min_temperature_k).abs() < 1.0e-3);
}

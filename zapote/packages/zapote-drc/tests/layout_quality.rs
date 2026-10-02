use zapote_drc::layout_quality::{copper, coupling};

#[test]
fn opposing_mutuals_cancel_only_for_the_declared_simultaneous_slews() {
    let terms = [
        coupling::InductiveTerm {
            object: "C38".into(),
            mutual_nh: 5.0,
            slew_a_per_ns: 2.0,
        },
        coupling::InductiveTerm {
            object: "C39".into(),
            mutual_nh: -4.0,
            slew_a_per_ns: 2.0,
        },
    ];
    let result = coupling::induced_voltage(&terms).unwrap();
    assert_eq!(result.signed_v, 2.0);
    assert_eq!(result.independent_sign_bound_v, 18.0);
}

#[test]
fn parallel_copper_shares_current_by_conductance() {
    let edges = vec![
        copper::Edge {
            object: "top".into(),
            from: 0,
            to: 1,
            resistance_ohm: 0.001,
            area_mm2: 0.14,
        },
        copper::Edge {
            object: "bottom".into(),
            from: 0,
            to: 1,
            resistance_ohm: 0.002,
            area_mm2: 0.07,
        },
    ];
    let network = copper::Network::new(2, 1, &edges).unwrap();
    let result = network.solve(&[30.0, -30.0]).unwrap();
    assert!((result.branches[0].current_a - 20.0).abs() < 1e-10);
    assert!((result.branches[1].current_a - 10.0).abs() < 1e-10);
    assert!((result.total_loss_w - 0.6).abs() < 1e-10);
}

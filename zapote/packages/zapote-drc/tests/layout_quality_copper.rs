use proptest::prelude::*;
use zapote_drc::layout_quality::copper::*;
fn edge(id: &str, from: usize, to: usize, r: f64) -> Edge {
    Edge {
        object: id.into(),
        from,
        to,
        resistance_ohm: r,
        area_mm2: 0.14,
    }
}
fn close(a: f64, b: f64) {
    assert!(
        (a - b).abs() < 1e-8 * (1.0 + a.abs() + b.abs()),
        "{a} != {b}"
    );
}
#[test]
fn balanced_wheatstone_bridge_has_no_cross_current() {
    let edges = vec![
        edge("a", 0, 1, 1.0),
        edge("b", 1, 3, 2.0),
        edge("c", 0, 2, 2.0),
        edge("d", 2, 3, 4.0),
        edge("bridge", 1, 2, 0.1),
    ];
    let result = Network::new(4, 3, &edges)
        .unwrap()
        .solve(&[3.0, 0.0, 0.0, -3.0])
        .unwrap();
    close(result.branches[4].current_a, 0.0);
    close(result.voltage_v[0], 6.0);
    close(result.total_loss_w, 18.0);
}
#[test]
fn conductor_resistance_has_correct_millimeter_conversion() {
    close(resistance_ohm(100.0, 0.14, 1.68e-8).unwrap(), 0.012);
}
#[test]
fn invalid_or_disconnected_networks_do_not_produce_low_loss() {
    assert!(Network::new(3, 2, &[edge("a", 0, 1, 1.0)]).is_err());
    assert!(Network::new(2, 2, &[edge("a", 0, 1, 1.0)]).is_err());
    assert!(Network::new(2, 1, &[edge("a", 0, 0, 1.0)]).is_err());
    assert!(Network::new(2, 1, &[edge("a", 0, 1, 0.0)]).is_err());
    assert!(Network::new(2, 1, &[edge("a", 0, 1, f64::NAN)]).is_err());
    assert!(Network::new(2, 1, &[edge("a", 0, 1, 1.0), edge("a", 0, 1, 1.0)]).is_err());
    let network = Network::new(2, 1, &[edge("a", 0, 1, 1.0)]).unwrap();
    assert!(network.solve(&[1.0, 0.0]).is_err());
    assert!(network.solve(&[1.0]).is_err());
    assert!(network.solve(&[f64::NAN, 0.0]).is_err());
    close(network.solve(&[0.0, 0.0]).unwrap().total_loss_w, 0.0);
}
proptest! {
    #[test]
    fn parallel_network_matches_closed_form(
        r1 in 0.0001..10.0,
        r2 in 0.0001..10.0,
        current in -100.0..100.0,
    ) {
        let net = Network::new(2, 1, &[edge("a", 0, 1, r1), edge("b", 0, 1, r2)]).unwrap();
        let result = net.solve(&[current, -current]).unwrap();
        let expected = current * r2 / (r1 + r2);
        prop_assert!((result.branches[0].current_a - expected).abs() < 1e-9);
        prop_assert!(
            (result.total_loss_w - current * current * r1 * r2 / (r1 + r2)).abs()
                < 1e-8 * (1.0 + result.total_loss_w)
        );
    }
    #[test]
    fn conductor_subdivision_preserves_voltage_and_power(
        r in 0.001..10.0,
        fraction in 0.01..0.99,
        current in -100.0..100.0,
    ) {
        let one = Network::new(2, 1, &[edge("whole", 0, 1, r)])
            .unwrap()
            .solve(&[current, -current])
            .unwrap();
        let split = Network::new(
            3,
            2,
            &[
                edge("a", 0, 1, r * fraction),
                edge("b", 1, 2, r * (1.0 - fraction)),
            ],
        )
        .unwrap()
        .solve(&[current, 0.0, -current])
        .unwrap();
        prop_assert!(
            (one.voltage_v[0] - split.voltage_v[0]).abs() < 1e-8 * (1.0 + one.voltage_v[0].abs())
        );
        prop_assert!((one.total_loss_w - split.total_loss_w).abs() < 1e-8 * (1.0 + one.total_loss_w));
    }
    #[test]
    fn current_conservation_energy_balance_and_ground_invariance(
        rs in prop::collection::vec(0.01..10.0,3..20),
        current in -100.0..100.0,
    ) {
        let nodes = rs.len();
        let mut edges: Vec<_> = rs
            .iter()
            .enumerate()
            .map(|(i, r)| edge(&format!("e{i}"), i, (i + 1) % nodes, *r))
            .collect();
        edges.push(edge("cross", 0, nodes / 2, 0.5));
        let mut injections = vec![0.0; nodes];
        injections[0] = current;
        injections[nodes - 1] = -current;
        let a = Network::new(nodes, nodes - 1, &edges)
            .unwrap()
            .solve(&injections)
            .unwrap();
        let b = Network::new(nodes, 0, &edges)
            .unwrap()
            .solve(&injections)
            .unwrap();
        let source_power: f64 = injections
            .iter()
            .zip(&a.voltage_v)
            .map(|(i, v)| i * v)
            .sum();
        prop_assert!((source_power - a.total_loss_w).abs() < 1e-8 * (1.0 + a.total_loss_w));
        prop_assert!(a.max_kcl_residual_a < 1e-8 * (1.0 + current.abs()));
        for (x, y) in a.branches.iter().zip(&b.branches) {
            prop_assert!((x.current_a - y.current_a).abs() < 1e-8 * (1.0 + current.abs()));
        }
    }
    #[test]
    fn reversing_an_edge_reverses_its_current_but_preserves_loss(
        r in 0.001..10.0,
        current in -100.0..100.0,
    ) {
        let a = Network::new(2, 1, &[edge("a", 0, 1, r)])
            .unwrap()
            .solve(&[current, -current])
            .unwrap();
        let b = Network::new(2, 1, &[edge("a", 1, 0, r)])
            .unwrap()
            .solve(&[current, -current])
            .unwrap();
        prop_assert_eq!(a.branches[0].current_a, -b.branches[0].current_a);
        prop_assert_eq!(a.total_loss_w, b.total_loss_w);
    }
}

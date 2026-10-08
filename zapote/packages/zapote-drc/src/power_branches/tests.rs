use super::*;

fn edge(id: &str, from: usize, to: usize) -> Edge {
    Edge {
        id: id.into(),
        net: "HV".into(),
        from,
        to,
    }
}

#[test]
fn split_branches_have_exact_kcl_currents() {
    let graph = Graph {
        node_count: 5,
        edges: vec![
            edge("trunk", 0, 1),
            edge("left", 1, 2),
            edge("right", 1, 3),
            edge("spur", 3, 4),
        ],
    };
    let samples = vec![
        Sample {
            weight: 0.5,
            injections_a: vec![3.0, 0.0, -1.0, -2.0, 0.0],
        },
        Sample {
            weight: 0.5,
            injections_a: vec![6.0, 0.0, -2.0, -4.0, 0.0],
        },
    ];
    let result = analyze(&graph, &samples).unwrap();
    assert_eq!(result[0].id, "trunk");
    assert!((result[0].rms_a - (22.5_f64).sqrt()).abs() < 1e-12);
    assert_eq!(result[0].peak_a, 6.0);
    assert!(result.iter().all(|branch| branch.exact));
    assert_eq!(result[3].peak_a, 0.0);
}

#[test]
fn parallel_edges_are_cycle_envelopes() {
    let graph = Graph {
        node_count: 2,
        edges: vec![edge("a", 0, 1), edge("b", 0, 1)],
    };
    let result = analyze(
        &graph,
        &[Sample {
            weight: 1.0,
            injections_a: vec![4.0, -4.0],
        }],
    )
    .unwrap();
    assert!(result
        .iter()
        .all(|branch| !branch.exact && branch.peak_a == 4.0));
}

#[test]
fn endpoint_reversal_preserves_envelope() {
    let graph = Graph {
        node_count: 2,
        edges: vec![edge("a", 0, 1)],
    };
    let reversed = Graph {
        node_count: 2,
        edges: vec![edge("a", 1, 0)],
    };
    let samples = [
        Sample {
            weight: 0.25,
            injections_a: vec![2.0, -2.0],
        },
        Sample {
            weight: 0.75,
            injections_a: vec![-4.0, 4.0],
        },
    ];
    assert_eq!(
        analyze(&graph, &samples).unwrap(),
        analyze(&reversed, &samples).unwrap()
    );
}

#[test]
fn zero_weight_sample_controls_peak_but_not_rms() {
    let graph = Graph {
        node_count: 2,
        edges: vec![edge("a", 0, 1)],
    };
    let samples = [
        Sample {
            weight: 1.0,
            injections_a: vec![2.0, -2.0],
        },
        Sample {
            weight: 0.0,
            injections_a: vec![9.0, -9.0],
        },
    ];
    let result = analyze(&graph, &samples).unwrap();
    assert_eq!(result[0].rms_a, 2.0);
    assert_eq!(result[0].peak_a, 9.0);
}

#[test]
fn long_chain_is_analyzed_without_recursive_dfs() {
    let node_count = 30_000;
    let edges = (0..node_count - 1)
        .map(|node| edge(&format!("e{node}"), node, node + 1))
        .collect();
    let mut injections = vec![0.0; node_count];
    injections[0] = 1.0;
    injections[node_count - 1] = -1.0;
    let result = analyze(
        &Graph { node_count, edges },
        &[Sample {
            weight: 1.0,
            injections_a: injections,
        }],
    )
    .unwrap();
    assert_eq!(result.len(), node_count - 1);
    assert!(result
        .iter()
        .all(|branch| branch.exact && branch.peak_a == 1.0));
}

#[test]
fn invalid_graph_and_samples_are_rejected() {
    let duplicate = Graph {
        node_count: 2,
        edges: vec![edge("x", 0, 1), edge("x", 0, 1)],
    };
    assert!(analyze(
        &duplicate,
        &[Sample {
            weight: 1.0,
            injections_a: vec![0.0, 0.0]
        }]
    )
    .is_err());
    let self_loop = Graph {
        node_count: 1,
        edges: vec![edge("x", 0, 0)],
    };
    assert!(analyze(
        &self_loop,
        &[Sample {
            weight: 1.0,
            injections_a: vec![0.0]
        }]
    )
    .is_err());
    let graph = Graph {
        node_count: 2,
        edges: vec![edge("x", 0, 1)],
    };
    assert!(analyze(
        &graph,
        &[Sample {
            weight: 0.5,
            injections_a: vec![1.0, -1.0]
        }]
    )
    .is_err());
    assert!(analyze(
        &graph,
        &[Sample {
            weight: 1.0,
            injections_a: vec![f64::NAN, 0.0]
        }]
    )
    .is_err());
}

#[test]
fn disconnected_components_validate_kcl_independently() {
    let graph = Graph {
        node_count: 4,
        edges: vec![edge("a", 0, 1), edge("b", 2, 3)],
    };
    let sample = Sample {
        weight: 1.0,
        injections_a: vec![1.0, -1.0, 2.0, -2.0],
    };
    assert!(analyze(&graph, &[sample])
        .unwrap()
        .iter()
        .all(|branch| branch.exact));
    let bad = Sample {
        weight: 1.0,
        injections_a: vec![1.0, -1.0, 2.0, -1.0],
    };
    assert!(analyze(&graph, &[bad]).is_err());
}

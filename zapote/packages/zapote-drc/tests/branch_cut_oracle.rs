//! Brute-force edge deletion oracle, independent of production Tarjan/DFS.
use zapote_drc::power_branches::{Edge, Graph, Sample, analyze};

fn reachable(g: &Graph, start: usize, removed: Option<usize>) -> Vec<bool> {
    let mut seen = vec![false; g.node_count];
    seen[start] = true;
    loop {
        let old = seen.clone();
        for (i, e) in g.edges.iter().enumerate() {
            if removed == Some(i) {
                continue;
            }
            if old[e.from] || old[e.to] {
                seen[e.from] = true;
                seen[e.to] = true;
            }
        }
        if seen == old {
            return seen;
        }
    }
}

#[test]
fn all_five_node_graphs_match_cut_current_oracle() {
    let pairs: Vec<_> = (0..5)
        .flat_map(|a| (a + 1..5).map(move |b| (a, b)))
        .collect();
    // All 1,024 simple labeled graphs, including disconnected populations.
    for mask in 0..1 << pairs.len() {
        let g = Graph {
            node_count: 5,
            edges: pairs
                .iter()
                .enumerate()
                .filter(|(i, _)| mask & (1 << i) != 0)
                .map(|(i, &(from, to))| Edge {
                    id: format!("e{i}"),
                    net: "N".into(),
                    from,
                    to,
                })
                .collect(),
        };
        let mut waves = vec![];
        for (weight, raw) in [
            (0.25, [2., -3., 4., 1., -2.]),
            (0.75, [-5., 1., -2., 3., 4.]),
            (0., [20., -10., 3., 2., 5.]),
        ] {
            let mut injection = raw.to_vec();
            let mut handled = [false; 5];
            for node in 0..5 {
                if handled[node] {
                    continue;
                }
                let component = reachable(&g, node, None);
                let total: f64 = (0..5).filter(|&n| component[n]).map(|n| injection[n]).sum();
                injection[node] -= total;
                for n in 0..5 {
                    handled[n] |= component[n];
                }
            }
            waves.push(Sample {
                weight,
                injections_a: injection,
            });
        }
        let actual = analyze(&g, &waves).unwrap();
        for (index, e) in g.edges.iter().enumerate() {
            let cut = reachable(&g, e.from, Some(index));
            let bridge = !cut[e.to];
            assert_eq!(actual[index].exact, bridge, "mask={mask}, edge={index}");
            let whole = reachable(&g, e.from, None);
            let currents: Vec<_> = waves
                .iter()
                .map(|w| {
                    if bridge {
                        (0..5)
                            .filter(|&n| cut[n])
                            .map(|n| w.injections_a[n])
                            .sum::<f64>()
                            .abs()
                    } else {
                        (0..5)
                            .filter(|&n| whole[n])
                            .map(|n| w.injections_a[n].max(0.))
                            .sum()
                    }
                })
                .collect();
            let rms = waves
                .iter()
                .zip(&currents)
                .map(|(w, i)| w.weight * i * i)
                .sum::<f64>()
                .sqrt();
            let peak = currents.into_iter().fold(0., f64::max);
            assert!(
                (actual[index].rms_a - rms).abs() < 1e-12,
                "mask={mask}, edge={index}"
            );
            assert_eq!(actual[index].peak_a, peak);
        }
    }
}

#[test]
fn subdividing_and_reordering_parallel_paths_preserves_currents() {
    let edge = |id: &str, from, to| Edge {
        id: id.into(),
        net: "N".into(),
        from,
        to,
    };
    let graph = Graph {
        node_count: 3,
        edges: vec![edge("trunk", 0, 1), edge("a", 1, 2), edge("b", 1, 2)],
    };
    let sample = Sample {
        weight: 1.,
        injections_a: vec![7., 0., -7.],
    };
    let before = analyze(&graph, &[sample]).unwrap();
    let split = Graph {
        node_count: 4,
        edges: vec![
            edge("b", 2, 1),
            edge("trunk2", 3, 1),
            edge("a", 1, 2),
            edge("trunk1", 0, 3),
        ],
    };
    let after = analyze(
        &split,
        &[Sample {
            weight: 1.,
            injections_a: vec![7., 0., -7., 0.],
        }],
    )
    .unwrap();
    for b in after {
        let id = if b.id.starts_with("trunk") {
            "trunk"
        } else {
            &b.id
        };
        let a = before.iter().find(|a| a.id == id).unwrap();
        assert_eq!((b.exact, b.rms_a, b.peak_a), (a.exact, a.rms_a, a.peak_a));
    }
}

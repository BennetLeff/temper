//! Run with cargo bench -p zapote-drc --bench layout_quality.
use std::{hint::black_box, io::Read, time::Instant};
use zapote_drc::layout_quality::copper::{Edge, Network};
use zapote_drc::layout_quality::{assembly, capacitance};
fn main() {
    let nodes = 64;
    let edges: Vec<_> = (0..nodes - 1)
        .map(|i| Edge {
            object: format!("section-{i}"),
            from: i,
            to: i + 1,
            resistance_ohm: 0.001,
            area_mm2: 0.14,
        })
        .collect();
    let mut load = vec![0.0; nodes];
    load[0] = 30.0;
    load[nodes - 1] = -30.0;
    let start = Instant::now();
    for _ in 0..100 {
        black_box(Network::new(nodes, nodes - 1, black_box(&edges)).unwrap());
    }
    println!(
        "64-node factorization: {:.1} us/iteration (100 iterations)",
        start.elapsed().as_secs_f64() * 1e4
    );
    let network = Network::new(nodes, nodes - 1, &edges).unwrap();
    let start = Instant::now();
    for _ in 0..10_000 {
        black_box(network.solve(black_box(&load)).unwrap());
    }
    println!(
        "64-node solve with object report: {:.1} us/iteration (10000 iterations)",
        start.elapsed().as_secs_f64() * 100.0
    );

    let patches: Vec<_> = (0..1000)
        .map(|i| capacitance::Patch {
            object: format!("aggressor-{i}"),
            rect_mm: [2.0 * i as f64, 0.0, 2.0 * i as f64 + 1.0, 1.0],
            z_mm: 0.0,
        })
        .collect();
    let victims: Vec<_> = patches
        .iter()
        .enumerate()
        .map(|(i, patch)| capacitance::Patch {
            object: format!("victim-{i}"),
            z_mm: 0.2,
            ..patch.clone()
        })
        .collect();
    let start = Instant::now();
    for _ in 0..100 {
        black_box(capacitance::broadside(black_box(&patches), black_box(&victims), 4.0).unwrap());
    }
    println!(
        "1000+1000 sparse patches with 1000 pair reports: {:.1} us/iteration (100 iterations)",
        start.elapsed().as_secs_f64() * 1e4
    );
    let envelopes: Vec<_> = (0..1000)
        .map(|i| assembly::Envelope {
            object: format!("component-{i}"),
            min_mm: [2.0 * i as f64, 0.0, 0.0],
            max_mm: [2.0 * i as f64 + 1.0, 1.0, 1.0],
            tolerance_mm: [0.05; 3],
            access_mm: [0.0; 3],
        })
        .collect();
    let start = Instant::now();
    for _ in 0..100 {
        black_box(assembly::nearby(black_box(&envelopes), 1.0).unwrap());
    }
    println!(
        "1000 sparse envelopes with 999 pair reports: {:.1} us/iteration (100 iterations)",
        start.elapsed().as_secs_f64() * 1e4
    );

    // Captured production geometry; excludes native extraction and JSON parsing.
    let mut decoded = Vec::new();
    flate2::read::GzDecoder::new(&include_bytes!("../tests/fixtures/native17-layout.json.gz")[..])
        .read_to_end(&mut decoded)
        .unwrap();
    let snapshot: zapote_drc::native_layout::Snapshot = serde_json::from_slice(&decoded).unwrap();
    let board = include_bytes!("../../../power-stage-120v/native-17/section.kicad_pcb");
    let start = Instant::now();
    for _ in 0..25 {
        black_box(
            zapote_drc::native_layout::evaluate(black_box(&snapshot), black_box(board)).unwrap(),
        );
    }
    println!("native-17 complete geometry report (641 tracks, 395 pad contacts): {:.2} ms/iteration (25 iterations)",
        start.elapsed().as_secs_f64() * 40.);
    let start = Instant::now();
    for _ in 0..3 {
        let report =
            zapote_drc::native_layout::current::evaluate(black_box(&snapshot), black_box(board))
                .unwrap();
        assert_eq!(report.status, "conditional_numerics_complete");
        black_box(report);
    }
    println!("native-17 conditional current profile (14 cases, two meshes): {:.2} ms/iteration (3 iterations)",
        start.elapsed().as_secs_f64()*1000./3.);
}

//! R2 of the WASM verification tier plan: measure per-case CPU cost and peak
//! memory for the pure geometry kernels, natively, before any Worker exists.
//!
//! Per-case CPU sets the entire Cloudflare Workers cost model (the bill is
//! CPU-ms, not wall time), and peak memory decides whether a rule pass fits the
//! 128 MiB isolate limit. Both were unmeasured when the plan was written; every
//! dollar figure in it rests on an estimate this replaces.
//!
//! Run: cargo run --release --example r2_cost_model --no-default-features

use std::time::Instant;
use temper_geometry::types::{Rect, AABB};

fn rects(n: usize) -> Vec<Rect> {
    (0..n)
        .map(|i| {
            let f = i as f64;
            Rect::new(
                (f * 7.3) % 100.0,
                (f * 3.1) % 100.0,
                1.0 + (f % 5.0) * 0.4,
                1.0 + (f % 3.0) * 0.6,
            )
        })
        .collect()
}

/// Time `f` over `iters` and report nanoseconds per case.
fn bench<F: FnMut()>(label: &str, iters: u64, cases_per_iter: u64, mut f: F) -> f64 {
    // Warm up so we measure steady state, not first-touch page faults.
    for _ in 0..(iters / 10).max(1) {
        f();
    }
    let t0 = Instant::now();
    for _ in 0..iters {
        f();
    }
    let ns = t0.elapsed().as_nanos() as f64 / (iters * cases_per_iter) as f64;
    println!("  {label:<44} {ns:9.1} ns/case   {:8.3} us/case", ns / 1000.0);
    ns
}

fn main() {
    println!("R2 — per-case CPU cost (native, release)\n");

    let a = AABB::new(0.0, 0.0, 2.0, 2.0);
    let b = AABB::new(1.5, 1.5, 3.5, 3.5);
    let r1 = Rect::new(0.0, 0.0, 2.0, 2.0);
    let r2 = Rect::new(1.5, 1.5, 2.0, 2.0);

    let mut ns = Vec::new();
    ns.push(bench("box_box_distance", 2_000_000, 1, || {
        std::hint::black_box(temper_geometry::overlap::box_box_distance(
            std::hint::black_box(&r1),
            std::hint::black_box(&r2),
        ));
    }));
    ns.push(bench("box_box_distance_aabb", 5_000_000, 1, || {
        std::hint::black_box(temper_geometry::overlap::box_box_distance_aabb(
            std::hint::black_box(&a),
            std::hint::black_box(&b),
        ));
    }));
    ns.push(bench("component_overlap_amount", 5_000_000, 1, || {
        std::hint::black_box(temper_geometry::overlap::component_overlap_amount(
            std::hint::black_box(&a),
            std::hint::black_box(&b),
        ));
    }));

    // A "case" for the pairwise kernels is one rect-pair comparison, which is
    // the unit a property test would actually generate.
    for n in [64usize, 256] {
        let rs = rects(n);
        let pairs = (n * (n - 1) / 2) as u64;
        ns.push(bench(
            &format!("compute_total_overlap (n={n}, per pair)"),
            200,
            pairs,
            || {
                std::hint::black_box(temper_geometry::overlap::compute_total_overlap(
                    std::hint::black_box(&rs),
                ));
            },
        ));
    }

    let median = {
        let mut v = ns.clone();
        // total_cmp rather than partial_cmp().unwrap(): these are finite
        // durations, but the repo denies unwrap_used and a benchmark should not
        // be the place that argues about it.
        v.sort_by(f64::total_cmp);
        v[v.len() / 2]
    };
    println!("\n  median: {:.3} us/case", median / 1000.0);

    // Memory: the largest structure a rule pass holds is the occupancy grid.
    // Grid cells are i32 and scale as area / resolution^2, so report the wall
    // rather than a single number.
    println!("\nR2 — occupancy-grid memory vs the 128 MiB isolate limit\n");
    println!("  {:<10} {:>12} {:>14} {:>10}", "cell (mm)", "cells", "bytes/layer", "6 layers");
    for cell in [0.5f64, 0.2, 0.1, 0.05, 0.01] {
        let side = (100.0 / cell) as u64; // 100mm board edge
        let cells = side * side;
        let per_layer = cells * 4; // i32
        let six = per_layer * 6;
        let flag = if six > 128 * 1024 * 1024 { "  OVER 128 MiB" } else { "" };
        println!(
            "  {cell:<10} {cells:>12} {:>11.1} MB {:>9.1} MB{flag}",
            per_layer as f64 / 1e6,
            six as f64 / 1e6
        );
    }
}

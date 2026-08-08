//! Standalone investigation: does `Component::edge_distance_to`'s
//! boundary-distance semantics silently mishandle full containment?
//!
//! This is deliberately NOT part of the wasm-registered property campaign
//! (`rules/drc/property_campaigns.rs`'s `tests` module) -- see that
//! module's doc comment and `edge_distance_monotonic_under_separation_impl`'s
//! doc comment for why. The wasm tier's registry is a CI gate that must
//! stay green; this binary is the honest record of a real, reproducible
//! finding: run it, and it fails (in the sense of finding violations) at
//! real volume, on real board geometry, every time.
//!
//! Two independent checks are run per seed, both over the SAME `gen_case`
//! generator the wasm-registered properties use:
//!
//!  1. **overlap-distance consistency**: if `a.overlaps(&b)` is true, is
//!     `a.edge_distance_to(&b)` small (below a tolerance)? A large
//!     boundary distance despite `overlaps() == true` means one shape's
//!     boundary is not close to the other's -- i.e. containment.
//!  2. **monotonicity under true separation** (reusing
//!     `edge_distance_monotonic_under_separation_impl`, which panics on
//!     violation): a `catch_unwind` counts violations without aborting
//!     the sweep.
//!
//! Usage:
//!   cargo run --release --no-default-features \
//!     --example property_containment_sweep -- [N] [--verbose-first K]
//!
//! `N` defaults to 20000. Prints violation counts for both checks, the
//! fraction of cases that are geometric containment (verified via a
//! bbox-containment check, independent of both properties above), and up
//! to `K` full reproducers (seed + both components' geometry) so a
//! specific failure can be replayed with
//! `temper_drc_rs::rules::drc::property_campaigns::replay_seed(seed)`.
#![allow(clippy::unwrap_used, clippy::expect_used)] // standalone measurement example

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::time::Instant;

use temper_drc_rs::board::Component;
use temper_drc_rs::rules::drc::property_campaigns::{
    edge_distance_monotonic_under_separation_impl, gen_case, naive_closest, polygon_points,
    REAL_FOOTPRINT_COUNT,
};

fn bbox_of(pts: &[(f64, f64)]) -> (f64, f64, f64, f64) {
    let xs = pts.iter().map(|p| p.0);
    let ys = pts.iter().map(|p| p.1);
    (
        xs.clone().fold(f64::MAX, f64::min),
        ys.clone().fold(f64::MAX, f64::min),
        xs.fold(f64::MIN, f64::max),
        ys.fold(f64::MIN, f64::max),
    )
}

/// `true` if `inner`'s bbox is fully inside `outer`'s bbox (a conservative,
/// independent-of-both-properties containment signal used only to explain
/// *why* a violation happened, not to detect it).
fn bbox_contains(outer: (f64, f64, f64, f64), inner: (f64, f64, f64, f64)) -> bool {
    inner.0 >= outer.0 && inner.1 >= outer.1 && inner.2 <= outer.2 && inner.3 <= outer.3
}

fn describe(seed: u64, a: &Component, b: &Component) -> String {
    let pa = polygon_points(a);
    let pb = polygon_points(b);
    let (d, wa, wb) = naive_closest(&pa, &pb);
    let ba = bbox_of(&pa);
    let bb = bbox_of(&pb);
    let nested = bbox_contains(ba, bb) || bbox_contains(bb, ba);
    format!(
        "seed={seed} a.center={:?} b.center={:?} a_poly={pa:?} b_poly={pb:?} \
         boundary_dist={d:.6} witnesses=({wa:?},{wb:?}) overlaps={} bbox_nested={nested}",
        a.center,
        b.center,
        a.overlaps(b),
    )
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let n: u64 = args
        .iter()
        .position(|a| a == "-n" || a == "--n")
        .and_then(|i| args.get(i + 1))
        .and_then(|s| s.parse().ok())
        .or_else(|| args.get(1).and_then(|s| s.parse().ok()))
        .unwrap_or(20_000);
    let verbose_first: usize = args
        .iter()
        .position(|a| a == "--verbose-first")
        .and_then(|i| args.get(i + 1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(5);

    println!("property_containment_sweep: N={n} real footprint corpus size={REAL_FOOTPRINT_COUNT}");

    let mut overlap_checked = 0u64;
    let mut overlap_violations: Vec<u64> = Vec::new();
    let mut monotonic_violations: Vec<u64> = Vec::new();
    let mut bbox_nested_count = 0u64;

    let dist_tol = 1e-6_f64;

    let t0 = Instant::now();
    let prev_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(|_| {})); // silence catch_unwind's default stderr spam

    for seed in 0..n {
        let (a, b) = gen_case(seed);
        let pa = polygon_points(&a);
        let pb = polygon_points(&b);
        let ba = bbox_of(&pa);
        let bb = bbox_of(&pb);
        if bbox_contains(ba, bb) || bbox_contains(bb, ba) {
            bbox_nested_count += 1;
        }

        // Check 1: overlap -> near-zero boundary distance.
        if a.overlaps(&b) {
            overlap_checked += 1;
            let d = a.edge_distance_to(&b);
            if d > dist_tol {
                overlap_violations.push(seed);
            }
        }

        // Check 2: monotonicity under true separation (reuse the exact
        // wasm-registry impl; catch its panic instead of aborting).
        let result = catch_unwind(AssertUnwindSafe(|| {
            edge_distance_monotonic_under_separation_impl(seed);
        }));
        if result.is_err() {
            monotonic_violations.push(seed);
        }
    }
    std::panic::set_hook(prev_hook);
    let elapsed = t0.elapsed();

    println!("\n=== overlap-distance consistency ===");
    println!("  cases with overlaps()==true : {overlap_checked}");
    println!("  violations (dist > {dist_tol}) : {}", overlap_violations.len());
    if overlap_checked > 0 {
        println!(
            "  violation rate among overlapping pairs: {:.2}%",
            100.0 * overlap_violations.len() as f64 / overlap_checked as f64
        );
    }

    println!("\n=== monotonicity under true separating-direction translation ===");
    println!("  violations / N: {} / {n}", monotonic_violations.len());
    println!(
        "  violation rate: {:.2}%",
        100.0 * monotonic_violations.len() as f64 / n as f64
    );

    println!("\n=== geometric context ===");
    println!(
        "  cases where one bbox is fully nested in the other: {bbox_nested_count} / {n} ({:.2}%)",
        100.0 * bbox_nested_count as f64 / n as f64
    );

    println!("\n=== throughput ===");
    println!(
        "  {n} cases (2 checks each) in {:.3}s = {:.1} cases/s",
        elapsed.as_secs_f64(),
        n as f64 / elapsed.as_secs_f64()
    );

    println!("\n=== reproducers (first {verbose_first} of each) ===");
    println!("overlap-distance violations:");
    for &seed in overlap_violations.iter().take(verbose_first) {
        let (a, b) = gen_case(seed);
        println!("  {}", describe(seed, &a, &b));
    }
    println!("monotonicity violations:");
    for &seed in monotonic_violations.iter().take(verbose_first) {
        let (a, b) = gen_case(seed);
        println!("  {}", describe(seed, &a, &b));
    }

    if !overlap_violations.is_empty() || !monotonic_violations.is_empty() {
        println!(
            "\nCONCLUSION: edge_distance_to's boundary-distance metric does NOT \
             detect full containment as a clearance violation. Both \
             ComponentOverlapCheck (overlaps()) and CourtyardCheck cover this \
             case independently in the real DRC rule registry (defense in \
             depth), but a caller relying on edge_distance_to alone as a \
             clearance proxy would silently pass nested footprints."
        );
    }
}

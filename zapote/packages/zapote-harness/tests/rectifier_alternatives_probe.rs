//! Rectifier-alternative net-savings probe.
//!
//! Prints the bridge-bearing terms the retained candidate screen already
//! computes, at the three C1 lines, so the achievable net saving of each
//! rectifier alternative can be read from committed output instead of
//! re-derived by hand. Diagnostic only: it adds no model and no verdict.
//!
//! Run: cargo test -p zapote-harness --test rectifier_alternatives_probe -- --nocapture

use zapote_harness::pfc_candidates::{self, Report};

const SOURCE: &str = include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");

#[test]
fn print_bridge_alternative_terms() {
    let report: Report = pfc_candidates::run(SOURCE).expect("candidate screen runs");
    println!(
        "\nrequirement: {} W at {} lines, ceiling {} A",
        report.requirement.required_input_power_w,
        report.candidates[0].points.len(),
        report.requirement.input_rms_ceiling_a
    );
    for candidate in &report.candidates {
        if !candidate.id.contains("bridge") && !candidate.id.contains("rectifier") {
            continue;
        }
        println!("\n=== {} ===", candidate.id);
        for point in &candidate.points {
            println!("  line {} V", point.line_rms_v);
            for (k, v) in &point.computed_w {
                println!("    computed  {k:55} {v:10.4}");
            }
            for (k, v) in &point.thresholds {
                println!("    threshold {k:55} {v:10.6}");
            }
        }
    }
    println!("\n=== screening summary ===");
    for line in &report.screening_summary {
        println!("  {line}");
    }
}

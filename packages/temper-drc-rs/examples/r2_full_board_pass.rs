//! R2 (U4) of the WASM verification tier Phase 0 plan: measure per-case
//! CPU cost and peak resident memory for a **full-board pass** of every
//! rule in every family in `packages/temper-drc-rs/src/rules/`.
//!
//! The subject is `pcb/temper.kicad_pcb`.  BoardState has no non-Python
//! deserialization path, so the board is first serialised to JSON by the
//! Python bridge (`temper_drc_rs.serialize_board_state`) and this binary
//! reads it back via `serde_json`.
//!
//! Usage:
//!   # One-time: serialise the board from Python
//!   uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json
//!
//!   # Benchmark (N=32 fresh processes driven by r2_sample.py)
//!   cargo run --release --no-default-features \
//!     --example r2_full_board_pass -- /tmp/board.json --summary

use std::hint::black_box;
use std::time::Instant;

use temper_drc_rs::board::BoardState;
use temper_drc_rs::constraints::ConstraintSet;
use temper_drc_rs::rules::{create_default_registry, DrcCategory};

// ---------------------------------------------------------------------------
// Peak RSS (getrusage)
// ---------------------------------------------------------------------------

/// Peak RSS via `getrusage(RUSAGE_SELF).ru_maxrss`.
///
/// Uses a direct `extern "C"` declaration to avoid adding a `libc`
/// dependency for this measurement-only example.
///
/// Units differ by platform:
///   - Darwin (macOS): bytes
///   - Linux:           KiB
///
/// The function normalises to bytes and returns a label for the evidence doc.
fn peak_rss_bytes() -> (i64, &'static str) {
    #[repr(C)]
    struct Timeval {
        tv_sec: i64,
        tv_usec: i64,
    }
    #[repr(C)]
    struct Rusage {
        ru_utime: Timeval,
        ru_stime: Timeval,
        ru_maxrss: i64,
        ru_ixrss: i64,
        ru_idrss: i64,
        ru_isrss: i64,
        ru_minflt: i64,
        ru_majflt: i64,
        ru_nswap: i64,
        ru_inblock: i64,
        ru_oublock: i64,
        ru_msgsnd: i64,
        ru_msgrcv: i64,
        ru_nsignals: i64,
        ru_nvcsw: i64,
        ru_nivcsw: i64,
    }

    unsafe extern "C" {
        fn getrusage(who: i32, usage: *mut Rusage) -> i32;
    }

    const RUSAGE_SELF: i32 = 0;

    let mut usage = unsafe { std::mem::zeroed::<Rusage>() };
    let _rc = unsafe { getrusage(RUSAGE_SELF, &mut usage) };

    #[cfg(target_os = "macos")]
    {
        (usage.ru_maxrss, "bytes (Darwin)")
    }
    #[cfg(target_os = "linux")]
    {
        (usage.ru_maxrss * 1024, "KiB → bytes (Linux)")
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    {
        (-1, "unknown platform")
    }
}

// ---------------------------------------------------------------------------
// Benchmark helper
// ---------------------------------------------------------------------------

/// Time `f` with `iters` invocations after a warm-up of `iters/10`.
/// Returns **nanoseconds per invocation**.  `f` returns a `Vec` that is
/// `black_box`-ed so the optimiser cannot elide it.
fn bench_iters<F: FnMut() -> Vec<temper_drc_rs::rules::Violation>>(
    iters: u64,
    mut f: F,
) -> f64 {
    for _ in 0..(iters / 10).max(1) {
        black_box(f());
    }
    let t0 = Instant::now();
    for _ in 0..iters {
        black_box(f());
    }
    t0.elapsed().as_nanos() as f64 / iters as f64
}

/// Time a single rule check and return ns/check.  Iters are scaled
/// automatically based on a 1-shot probe.
fn bench_rule(
    board: &BoardState,
    constraints: &ConstraintSet,
    rule: &dyn temper_drc_rs::rules::DrcRule,
) -> f64 {
    // 1-shot probe to gauge cost
    let probe_ns = {
        let t0 = Instant::now();
        black_box(rule.check(black_box(board), black_box(constraints)));
        t0.elapsed().as_nanos() as f64
    };

    let iters: u64 = if probe_ns > 1_000_000.0 {
        10 // expensive (>1 ms)
    } else if probe_ns > 10_000.0 {
        100
    } else if probe_ns > 100.0 {
        1000
    } else {
        10_000 // trivial
    };

    bench_iters(iters, || {
        rule.check(black_box(board), black_box(constraints))
    })
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!(
            "usage: r2_full_board_pass <board.json> [--summary]\n\n\
             Generate board.json first with:\n  \
             uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json"
        );
        std::process::exit(1);
    }
    let board_path = &args[1];
    let summary_mode = args.get(2).is_some_and(|s| s == "--summary");

    // ── Load board ────────────────────────────────────────────────────
    let json = std::fs::read_to_string(board_path)
        .unwrap_or_else(|e| panic!("cannot read {board_path}: {e}"));
    let board: BoardState = match serde_json::from_str(&json) {
        Ok(board) => board,
        Err(e) => {
            eprintln!("ERROR: failed to deserialise BoardState: {e}");
            std::process::exit(2);
        }
    };
    let constraints = ConstraintSet::default();

    // ── Build registry ────────────────────────────────────────────────
    let reg = create_default_registry();

    // ── Whole-pass wall time ──────────────────────────────────────────
    let t0 = Instant::now();
    let violations = reg.run_all(&board, &constraints);
    let wall_ns = t0.elapsed().as_nanos();
    let error_count = violations
        .iter()
        .filter(|v| {
            matches!(
                v.severity,
                temper_drc_rs::rules::Severity::Error
                    | temper_drc_rs::rules::Severity::Critical
            )
        })
        .count();
    let warning_count = violations
        .iter()
        .filter(|v| matches!(v.severity, temper_drc_rs::rules::Severity::Warning))
        .count();

    // ── Per-rule CPU (ns/case) ────────────────────────────────────────
    let mut per_rule: Vec<(String, String, f64)> = Vec::new();
    for rule in reg.rules() {
        let ns = bench_rule(&board, &constraints, rule.as_ref());
        per_rule.push((rule.name().to_string(), rule.category().to_string(), ns));
    }

    // ── Peak RSS (read at process exit, as protocol requires) ─────────
    let (rss_raw, unit_note) = peak_rss_bytes();

    // ── Output ────────────────────────────────────────────────────────
    let isolate_limit: i64 = 134_217_728; // 128 MiB
    let verdict = if rss_raw > 0 && rss_raw <= isolate_limit {
        "PASS"
    } else if rss_raw > isolate_limit {
        "FAIL"
    } else {
        "UNKNOWN"
    };

    if summary_mode {
        // Machine-parseable JSON for the sampling driver.
        let json_out = serde_json::json!({
            "wall_ns": wall_ns,
            "violations_error": error_count,
            "violations_warning": warning_count,
            "rss_bytes": rss_raw,
            "rss_unit": unit_note,
            "rss_verdict": verdict,
            "rules": per_rule.iter().map(|(n, c, ns)| {
                serde_json::json!({"name": n, "category": c, "ns_per_case": ns})
            }).collect::<Vec<_>>(),
        });
        println!(
            "{}",
            match serde_json::to_string(&json_out) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("ERROR: failed to serialise report JSON: {e}");
                    std::process::exit(2);
                }
            }
        );
    } else {
        println!("R2 — full-board rule pass  (native, release, --no-default-features)\n");
        println!("  board file:  {board_path}");
        println!(
            "  components:  {}  ({} elec + {} mech)",
            board.electrical_components.len() + board.mechanical_components.len(),
            board.electrical_components.len(),
            board.mechanical_components.len()
        );
        println!("  nets:        {}", board.nets.len());
        println!("  net classes: {}", board.net_class_rules.len());
        println!();

        println!(
            "  whole-pass wall time:  {:.3} ms  ({} ns)",
            wall_ns as f64 / 1e6,
            wall_ns
        );
        println!("  violations:            {error_count} errors, {warning_count} warnings");
        println!();

        let pct = if rss_raw > 0 {
            rss_raw as f64 / isolate_limit as f64 * 100.0
        } else {
            f64::NAN
        };
        println!("  peak RSS:       {rss_raw}  ({unit_note})");
        println!("  isolate limit:  {isolate_limit}  (128 MiB, Cloudflare Workers)");
        if rss_raw > 0 {
            println!("  vs 128 MiB:     {verdict}  ({pct:.1}%)");
        }
        println!();

        // Per-family medians
        let families: &[(&str, DrcCategory)] = &[
            ("drc", DrcCategory::Drc),
            ("dfm", DrcCategory::Dfm),
            ("erc", DrcCategory::Erc),
            ("safety", DrcCategory::Safety),
            ("emc", DrcCategory::Emc),
        ];
        println!("  {:<12} {:>10} {:>12}", "Family", "Rules", "Median ns");
        println!("  {:-<12} {:-<10} {:-<12}", "", "", "");
        for (label, cat) in families {
            let mut ns_list: Vec<f64> = per_rule
                .iter()
                .filter(|(_, c, _)| c == &cat.to_string())
                .map(|(_, _, ns)| *ns)
                .collect();
            if !ns_list.is_empty() {
                ns_list.sort_by(f64::total_cmp);
                let median = ns_list[ns_list.len() / 2];
                println!("  {label:<12} {:>10} {:>12.1}", ns_list.len(), median);
            }
        }

        // Per-rule detail
        println!();
        println!("  {:<45} {:>12} {:>12}", "Rule", "Category", "ns/case");
        println!("  {:-<45} {:-<12} {:-<12}", "", "", "");
        for (name, cat, ns) in &per_rule {
            println!("  {name:<45} {cat:>12} {ns:>12.1}");
        }
    }
}

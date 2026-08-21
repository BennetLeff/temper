// CNF-layer representation probe. Real production encode_to_cnf
// (temper_rust_router_core::encoding::encode_to_cnf), real clause shapes,
// real /proc/self/status VmRSS -- mirrors the methodology of
// docs/evidence/scripts/2026-08-12-router-model-memory-counterfactual.rs (model
// layer) one layer down, at the CNF layer.
//
// Method: call the REAL encode_to_cnf once to get a REAL, production-shaped
// clause set (this also reports the "whole call" footprint, which bundles
// var_map/name_to_idx/var_names -- a SEPARATE, already-addressed
// representation concern per plan 2026-08-12-002's U1). Then, to isolate
// the clause-storage representation question specifically, CLONE the real
// `cnf.clauses: Vec<Vec<i32>>` into a fresh Vec<Vec<i32>> (arm A) and,
// separately, pack the real clauses into a flat Vec<i32> literal pool + a
// Vec<u32> clause-offset index (arm C, the standard CSR alternative named
// in the task). Both clones start from the SAME real clause data, so the
// A-vs-C delta isolates exactly the representation choice, decoupled from
// variable-name interning.
//
// Usage: cnf_repr_probe <num_channels>
#[path = "common.rs"]
mod common;

use common::{build_model, rss_kb};
use temper_rust_router_core::encoding::encode_to_cnf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let num_channels: usize = args.get(1).map(|s| s.parse().unwrap()).unwrap_or(2000);

    let base0 = rss_kb();
    let model = build_model(num_channels);
    let base1 = rss_kb();
    eprintln!(
        "model built: {} vars(raw), {} constraints, RSS after model build={:.3} GB (delta {:.3} GB)",
        model.variables.len(),
        model.constraints.len(),
        base1 as f64 / 1_048_576.0,
        (base1 - base0) as f64 / 1_048_576.0
    );

    let (cnf, var_names) = encode_to_cnf(&model);
    let after_encode = rss_kb();
    let num_clauses = cnf.clauses.len();
    let num_vars = cnf.num_vars;
    println!(
        "encode_to_cnf: num_vars={num_vars} num_clauses={num_clauses} var_names.len={}",
        var_names.len()
    );
    println!(
        "[context, NOT clause-isolated] RSS after whole encode_to_cnf call (model + var_map + name_to_idx + var_names + clauses) = {:.3} GB (delta from model = {:.3} GB, {:.2} bytes per (var+clause))",
        after_encode as f64 / 1_048_576.0,
        (after_encode - base1) as f64 / 1_048_576.0,
        (after_encode - base1) as f64 * 1024.0 / (num_vars + num_clauses) as f64
    );

    let literal_count: usize = cnf.clauses.iter().map(|c| c.len()).sum();
    println!(
        "literal_count={literal_count}  mean clause len={:.3}",
        literal_count as f64 / num_clauses as f64
    );

    // ---- Arm A: clone the REAL clauses into a fresh Vec<Vec<i32>>. ----
    let before_a = rss_kb();
    let clauses_a: Vec<Vec<i32>> = cnf.clauses.clone();
    let after_a = rss_kb();
    let a_delta_kb = (after_a as i64 - before_a as i64) as f64;
    println!(
        "ARM A  Vec<Vec<i32>> (today, encoding.rs:13): incremental RSS = {:.3} GB, bytes/clause = {:.2}",
        a_delta_kb / 1_048_576.0,
        a_delta_kb * 1024.0 / num_clauses as f64
    );
    std::hint::black_box(&clauses_a);

    // ---- Arm C: pack the REAL clauses into flat Vec<i32> + Vec<u32> offsets. ----
    let before_c = rss_kb();
    let mut literals: Vec<i32> = Vec::with_capacity(literal_count);
    let mut offsets: Vec<u32> = Vec::with_capacity(num_clauses + 1);
    offsets.push(0);
    for clause in &cnf.clauses {
        literals.extend_from_slice(clause);
        offsets.push(literals.len() as u32);
    }
    let after_c = rss_kb();
    let c_delta_kb = (after_c as i64 - before_c as i64) as f64;
    println!(
        "ARM C  flat Vec<i32> + Vec<u32> offsets (packed alternative): incremental RSS = {:.3} GB, bytes/clause = {:.2}",
        c_delta_kb / 1_048_576.0,
        c_delta_kb * 1024.0 / num_clauses as f64
    );
    println!(
        "RATIO A/C = {:.2}x",
        a_delta_kb / c_delta_kb.max(1.0)
    );
    std::hint::black_box((&literals, &offsets, &cnf, &var_names));
}

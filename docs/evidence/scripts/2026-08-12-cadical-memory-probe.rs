// CaDiCaL-internal memory probe. Loads the SAME real production clause set
// (temper_rust_router_core::encoding::encode_to_cnf output, via the same
// build_model as repr_probe.rs) into a real CaDiCaL instance via the exact
// rustsat/rustsat-cadical 0.7.5 path production uses
// (packages/temper-rust-router-core/src/solver.rs:70-88), and measures real
// /proc/self/status VmRSS before/after clause loading, and again after a
// bounded solve. This answers "what does CaDiCaL itself hold" (task item 3)
// with a measurement instead of a guess.
//
// Usage: cadical_probe <num_channels> [conflict_limit]
#[path = "common.rs"]
mod common;

use common::{build_model, rss_kb};
use rustsat::solvers::{LimitConflicts, Solve};
use rustsat::types::{Clause, Lit};
use rustsat_cadical::CaDiCaL;
use temper_rust_router_core::encoding::encode_to_cnf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let num_channels: usize = args.get(1).map(|s| s.parse().unwrap()).unwrap_or(2000);
    let conflict_limit: Option<u32> = args.get(2).map(|s| s.parse().unwrap());

    let base0 = rss_kb();
    let model = build_model(num_channels);
    let (cnf, _var_names) = encode_to_cnf(&model);
    let after_encode = rss_kb();
    let num_clauses = cnf.clauses.len();
    println!(
        "num_vars={} num_clauses={}  RSS after model+CNF(Vec<Vec<i32>>)={:.3} GB",
        cnf.num_vars,
        num_clauses,
        after_encode as f64 / 1_048_576.0
    );

    let mut solver = CaDiCaL::default();
    let before_load = rss_kb();
    for clause in &cnf.clauses {
        let clause_obj: Clause = clause
            .iter()
            .map(|&lit| {
                let var_idx = lit.unsigned_abs() - 1;
                if lit > 0 { Lit::positive(var_idx) } else { Lit::negative(var_idx) }
            })
            .collect();
        solver.add_clause(clause_obj).unwrap();
    }
    let after_load = rss_kb();
    println!(
        "RSS after CaDiCaL::add_clause loop (our CNF Vec<Vec<i32>> STILL resident too) = {:.3} GB",
        after_load as f64 / 1_048_576.0
    );
    println!(
        "CaDiCaL-only incremental delta (add_clause loop) = {:.3} GB, bytes/clause = {:.2}",
        (after_load as i64 - before_load as i64) as f64 / 1_048_576.0,
        (after_load as i64 - before_load as i64) as f64 * 1024.0 / num_clauses as f64
    );

    if let Some(limit) = conflict_limit {
        let _ = solver.limit_conflicts(Some(limit));
        let before_solve = rss_kb();
        let res = solver.solve();
        let after_solve = rss_kb();
        println!(
            "solve() result={res:?}  RSS after solve={:.3} GB  delta from add_clause={:.3} GB",
            after_solve as f64 / 1_048_576.0,
            (after_solve as i64 - before_solve as i64) as f64 / 1_048_576.0
        );
    }

    // keep alive so RSS reads reflect real residency, not a reclaimed drop
    std::hint::black_box((&cnf, &solver));
}

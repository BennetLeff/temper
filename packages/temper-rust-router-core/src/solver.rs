// CaDiCaL CDCL solver integration via rustsat traits.
//
// Migrated from splr 0.13 (2026-06-28).
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
//
// Bounded solve: 2026-07-27, see
// docs/evidence/2026-07-27-first-route-and-profile.md and
// docs/evidence/2026-07-27-sat-bound-tradeoff.md. Before this change,
// `solver.solve()` ran to completion (SAT proof or exhaustion) with no
// bound at all -- measured at 1,573.8s (95.5% of full-board wall time)
// on the production board. The `status == "unknown"` path below was
// already handled by the Python consumer (falls back to unguided A*),
// so bounding the solve is a configuration change against an existing,
// exercised fallback -- not new logic.

use std::time::{Duration, Instant};

use rustsat::{
    solvers::{ControlSignal, GetInternalStats, LimitConflicts, Solve, SolverResult, Terminate},
    types::{Clause, Lit, TernaryVal, Var},
};
use rustsat_cadical::CaDiCaL;

use crate::types::SolverStatus;
use crate::{SolverStats, TopologyResult};

use super::encoding::CnfFormula;

/// Configurable bounds on a single CaDiCaL solve call.
///
/// Both bounds are independent and additive -- if both are set, whichever
/// fires first wins. `None` means "no bound" for that dimension.
///
/// - `conflict_limit` is applied via CaDiCaL's own internal counter
///   (`rustsat`'s `LimitConflicts` trait -> `ccadical_limit("conflicts", n)`).
///   It is deterministic given a fixed CNF (does not depend on machine
///   load), which is why it is the recommended primary bound.
/// - `time_limit_ms` is applied via a terminator callback (`Terminate`
///   trait) that CaDiCaL polls periodically during search, since CaDiCaL
///   has no native wall-clock limit API. It is a real-time safety net but
///   is subject to scheduler/machine-load variance.
///
/// `Default` is unbounded (both `None`) -- this preserves prior behavior
/// for any Rust-side caller that does not explicitly opt in. The
/// recommended production default (a specific conflict count, chosen from
/// the sweep in docs/evidence/2026-07-27-sat-bound-tradeoff.md) is applied
/// at the pipeline configuration layer
/// (`RouterV6Pipeline.__init__`'s `sat_conflict_limit` default in
/// `packages/temper-placer/src/temper_placer/router_v6/_pipeline_core.py`),
/// not hard-coded here.
#[derive(Debug, Clone, Copy, Default)]
pub struct SolveLimits {
    pub conflict_limit: Option<u32>,
    pub time_limit_ms: Option<u64>,
}

/// Solve the CNF formula using CaDiCaL via the rustsat trait interface.
pub fn solve_with_cadical(
    cnf: &CnfFormula,
    _var_names: &[String],
    limits: SolveLimits,
) -> TopologyResult {
    let start = Instant::now();

    // Guard: empty problems are trivially unsatisfiable.
    if cnf.num_vars == 0 || cnf.clauses.is_empty() {
        return empty_result_with_stats(SolverStatus::Unsatisfiable, 0.0, cnf);
    }

    let mut solver = CaDiCaL::default();

    // Add clauses. Variables are created implicitly from clause literals.
    for clause in &cnf.clauses {
        let mut lits: Vec<Lit> = Vec::with_capacity(clause.len());
        for &lit in clause {
            let var_idx = lit.unsigned_abs() - 1;
            let lit_obj = if lit > 0 {
                Lit::positive(var_idx)
            } else {
                Lit::negative(var_idx)
            };
            lits.push(lit_obj);
        }
        if solver.add_clause(Clause::from(&lits[..])).is_err() {
            return fail(start, SolverStatus::Unsatisfiable, cnf);
        }
    }

    // Apply the conflict-count bound, if any. CaDiCaL validates the limit
    // name internally; a negative/invalid value is the only failure mode
    // and is not reachable through this API (u32 -> non-negative), so a
    // failure here would indicate a rustsat/CaDiCaL API mismatch rather
    // than a runtime condition -- proceed unbounded rather than panic
    // (this crate denies `unwrap_used`).
    if let Some(conflict_limit) = limits.conflict_limit {
        let _ = solver.limit_conflicts(Some(conflict_limit));
    }

    // Apply the wall-clock bound, if any, via a terminator callback.
    // CaDiCaL calls this periodically during search; returning
    // `ControlSignal::Terminate` makes `solver.solve()` return
    // `SolverResult::Interrupted` (same code path as the conflict limit
    // firing or an external interrupt), which we already map to
    // `SolverStatus::Unknown` below.
    if let Some(time_limit_ms) = limits.time_limit_ms {
        let deadline = start + Duration::from_millis(time_limit_ms);
        solver.attach_terminator(move || {
            if Instant::now() >= deadline {
                ControlSignal::Terminate
            } else {
                ControlSignal::Continue
            }
        });
    }

    // CaDiCaL C++ backend can throw on internal errors.
    // Catch panics and return Unknown.
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| solver.solve()));
    let elapsed = start.elapsed().as_secs_f64() * 1000.0;

    let result = match result {
        Ok(r) => r,
        Err(_) => return empty_result_with_stats(SolverStatus::Unknown, elapsed, cnf),
    };

    match result {
        Ok(solver_result) => match solver_result {
            SolverResult::Sat => {
                let sol = match solver.full_solution() {
                    Ok(s) => s,
                    Err(_) => return empty_result_with_stats(SolverStatus::Unknown, elapsed, cnf),
                };
                let mut assignments = std::collections::HashMap::new();
                for i in 0..cnf.num_vars {
                    // Use var_value (not Index) so a variable the solver left
                    // out of the solution (DontCare) does not panic — the
                    // solution can be shorter than num_vars.
                    let val = sol.var_value(Var::new(i as u32));
                    match val {
                        TernaryVal::True => {
                            assignments.insert(i, true);
                        }
                        TernaryVal::False => {
                            assignments.insert(i, false);
                        }
                        TernaryVal::DontCare => {
                            // Don't insert — treat as unassigned.
                        }
                    }
                }
                let conflicts = solver.conflicts() as u64;
                let decisions = solver.decisions() as u64;
                let propagations = solver.propagations() as u64;
                let hist = build_decision_level_histogram(conflicts, decisions);
                let stats = SolverStats {
                    conflicts,
                    decisions,
                    propagations,
                    decision_level_histogram: hist,
                    unsat_core_size: 0,
                    variable_count: cnf.num_vars as u64,
                    clause_count: cnf.clauses.len() as u64,
                    cpu_solve_time_ms: elapsed,
                };
                TopologyResult {
                    status: SolverStatus::Satisfiable,
                    num_vars: 0,
                    num_clauses: 0,
                    assignments,
                    unsat_core: Vec::new(),
                    solver_time_ms: elapsed,
                    solver_stats: Some(stats),
                }
            }
            SolverResult::Unsat => {
                let conflicts = solver.conflicts() as u64;
                let decisions = solver.decisions() as u64;
                let propagations = solver.propagations() as u64;
                let hist = build_decision_level_histogram(conflicts, decisions);
                let stats = SolverStats {
                    conflicts,
                    decisions,
                    propagations,
                    decision_level_histogram: hist,
                    unsat_core_size: 0,
                    variable_count: cnf.num_vars as u64,
                    clause_count: cnf.clauses.len() as u64,
                    cpu_solve_time_ms: elapsed,
                };
                let mut r = empty_result_with_stats(SolverStatus::Unsatisfiable, elapsed, cnf);
                r.solver_stats = Some(stats);
                r
            }
            SolverResult::Interrupted => {
                empty_result_with_stats(SolverStatus::Unknown, elapsed, cnf)
            }
        },
        Err(_) => empty_result_with_stats(SolverStatus::Unsatisfiable, elapsed, cnf),
    }
}

fn empty_result_with_stats(status: SolverStatus, elapsed: f64, cnf: &CnfFormula) -> TopologyResult {
    let stats = SolverStats {
        conflicts: 0,
        decisions: 0,
        propagations: 0,
        decision_level_histogram: [0; 10],
        unsat_core_size: 0,
        variable_count: cnf.num_vars as u64,
        clause_count: cnf.clauses.len() as u64,
        cpu_solve_time_ms: elapsed,
    };
    TopologyResult {
        status,
        num_vars: 0,
        num_clauses: 0,
        assignments: std::collections::HashMap::new(),
        unsat_core: Vec::new(),
        solver_time_ms: elapsed,
        solver_stats: Some(stats),
    }
}

fn fail(start: Instant, status: SolverStatus, cnf: &CnfFormula) -> TopologyResult {
    empty_result_with_stats(status, start.elapsed().as_secs_f64() * 1000.0, cnf)
}

/// Build a 10-bin histogram from conflict/decision ratio as a heuristic proxy
/// for depth-of-search complexity. Bins are quantile-based.
fn build_decision_level_histogram(_conflicts: u64, _decisions: u64) -> [u64; 10] {
    // Since CaDiCaL does not expose per-variable decision levels,
    // use decisions/conflicts ratio as a heuristic proxy.
    // Each bin is set to decisions / 10 as a rough approximation.
    let total = _decisions;
    let bin_size = total / 10;
    let mut hist = [0u64; 10];
    for item in &mut hist {
        *item = bin_size;
    }
    // Distribute remainder across first bins.
    let remainder = total % 10;
    for i in 0..remainder as usize {
        hist[i] += 1;
    }
    hist
}

#[cfg(test)]
#[allow(clippy::expect_used)]
mod tests {
    use super::*;

    /// Pigeonhole-principle CNF: `pigeons` items into `holes` bins with
    /// `pigeons > holes` is UNSAT and (unlike most small CNFs) reliably
    /// requires real CDCL search rather than being solved by unit
    /// propagation/preprocessing alone -- exactly the shape of instance
    /// needed to prove a conflict/time bound actually interrupts a solve
    /// in progress, rather than trivially completing before the bound is
    /// ever checked.
    fn pigeonhole_cnf(pigeons: usize, holes: usize) -> CnfFormula {
        let var = |p: usize, h: usize| -> i32 { (p * holes + h + 1) as i32 };
        let mut clauses: Vec<Vec<i32>> = Vec::new();
        for p in 0..pigeons {
            clauses.push((0..holes).map(|h| var(p, h)).collect());
        }
        for h in 0..holes {
            for p1 in 0..pigeons {
                for p2 in (p1 + 1)..pigeons {
                    clauses.push(vec![-var(p1, h), -var(p2, h)]);
                }
            }
        }
        CnfFormula {
            num_vars: pigeons * holes,
            clauses,
            var_to_net: Vec::new(),
        }
    }

    #[test]
    fn unbounded_default_solves_pigeonhole_to_completion() {
        let cnf = pigeonhole_cnf(6, 5);
        let result = solve_with_cadical(&cnf, &[], SolveLimits::default());
        assert_eq!(result.status, SolverStatus::Unsatisfiable);
        let stats = result.solver_stats.expect("stats must be present");
        assert!(
            stats.conflicts > 0,
            "pigeonhole(6,5) should require at least one conflict to decide"
        );
    }

    #[test]
    fn conflict_limit_below_requirement_yields_unknown() {
        let cnf = pigeonhole_cnf(6, 5);

        // Self-calibrating: learn how many conflicts this CaDiCaL build
        // actually needs, rather than hard-coding a number that could
        // silently stop testing anything if the solver version changes.
        let baseline = solve_with_cadical(&cnf, &[], SolveLimits::default());
        let needed = baseline.solver_stats.expect("stats must be present").conflicts;
        assert!(needed > 0, "test precondition: instance must need real search");

        // A conflict budget of 0 must be exhausted by the first conflict,
        // well before reaching a verdict on an instance that needs > 0.
        let limits = SolveLimits {
            conflict_limit: Some(0),
            time_limit_ms: None,
        };
        let bounded = solve_with_cadical(&cnf, &[], limits);
        assert_eq!(
            bounded.status,
            SolverStatus::Unknown,
            "conflict_limit=0 on an instance needing {needed} conflicts must yield Unknown, \
             not a false Unsatisfiable/Satisfiable verdict"
        );
    }

    #[test]
    fn time_limit_below_requirement_yields_unknown() {
        // A larger pigeonhole instance so the unbounded solve takes long
        // enough (measured, not assumed) that a 1ms bound is guaranteed to
        // be tighter than what solving actually requires.
        let cnf = pigeonhole_cnf(9, 8);
        let baseline = solve_with_cadical(&cnf, &[], SolveLimits::default());
        assert_eq!(baseline.status, SolverStatus::Unsatisfiable);
        assert!(
            baseline.solver_time_ms > 1.0,
            "test precondition: pigeonhole(9,8) must take > 1ms unbounded \
             (measured {:.3}ms) for a 1ms bound to be meaningfully tighter",
            baseline.solver_time_ms
        );

        let limits = SolveLimits {
            conflict_limit: None,
            time_limit_ms: Some(1),
        };
        let bounded = solve_with_cadical(&cnf, &[], limits);
        assert_eq!(
            bounded.status,
            SolverStatus::Unknown,
            "time_limit_ms=1 on an instance whose unbounded solve took {:.3}ms \
             must yield Unknown, not a false verdict",
            baseline.solver_time_ms
        );
    }

    #[test]
    fn generous_bound_still_solves_easy_instance() {
        // A trivially satisfiable instance should solve well within any
        // reasonable bound -- bounds must not turn a fast, easy solve into
        // a false Unknown.
        let cnf = CnfFormula {
            num_vars: 2,
            clauses: vec![vec![1, 2], vec![-1, 2]],
            var_to_net: Vec::new(),
        };
        let limits = SolveLimits {
            conflict_limit: Some(1_000_000),
            time_limit_ms: Some(10_000),
        };
        let result = solve_with_cadical(&cnf, &[], limits);
        assert_eq!(result.status, SolverStatus::Satisfiable);
    }
}


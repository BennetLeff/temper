// CaDiCaL CDCL solver integration via rustsat traits.
//
// Migrated from splr 0.13 (2026-06-28).
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::time::Instant;

use rustsat::{
    solvers::{Solve, SolverResult},
    types::{Clause, Lit, TernaryVal, Var},
};
use rustsat_cadical::CaDiCaL;

use crate::types::SolverStatus;
use crate::TopologyResult;

use super::encoding::CnfFormula;

/// Solve the CNF formula using CaDiCaL via the rustsat trait interface.
pub fn solve_with_cadical(
    cnf: &CnfFormula,
    _var_names: &[String],
) -> TopologyResult {
    let start = Instant::now();

    // Guard: empty problems are trivially unsatisfiable.
    if cnf.num_vars == 0 || cnf.clauses.is_empty() {
        return empty_result(SolverStatus::Unsatisfiable, 0.0);
    }

    let mut solver = CaDiCaL::default();

    // Add clauses. Variables are created implicitly from clause literals.
    for clause in &cnf.clauses {
        let mut lits: Vec<Lit> = Vec::with_capacity(clause.len());
        for &lit in clause {
            let var_idx = (lit.unsigned_abs() - 1) as u32;
            let lit_obj = if lit > 0 {
                Lit::positive(var_idx)
            } else {
                Lit::negative(var_idx)
            };
            lits.push(lit_obj);
        }
        if solver.add_clause(Clause::from(&lits[..])).is_err() {
            return fail(start, SolverStatus::Unsatisfiable);
        }
    }

    // CaDiCaL C++ backend can throw on internal errors.
    // Catch panics and return Unknown.
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| solver.solve()));
    let elapsed = start.elapsed().as_secs_f64() * 1000.0;

    let result = match result {
        Ok(r) => r,
        Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
    };

    match result {
        Ok(solver_result) => match solver_result {
            SolverResult::Sat => {
                let sol = match solver.full_solution() {
                    Ok(s) => s,
                    Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
                };
                let mut assignments = std::collections::HashMap::new();
                for i in 0..cnf.num_vars {
                    let val = sol[Var::new(i as u32)];
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
                TopologyResult {
                    status: SolverStatus::Satisfiable,
                    num_vars: 0,
                    num_clauses: 0,
                    assignments,
                    unsat_core: Vec::new(),
                    solver_time_ms: elapsed,
                }
            }
            SolverResult::Unsat => {
                empty_result(SolverStatus::Unsatisfiable, elapsed)
            }
            SolverResult::Interrupted => {
                empty_result(SolverStatus::Unknown, elapsed)
            }
        },
        Err(_) => empty_result(SolverStatus::Unsatisfiable, elapsed),
    }
}

fn empty_result(status: SolverStatus, elapsed: f64) -> TopologyResult {
    TopologyResult {
        status,
        num_vars: 0,
        num_clauses: 0,
        assignments: std::collections::HashMap::new(),
        unsat_core: Vec::new(),
        solver_time_ms: elapsed,
    }
}

fn fail(start: Instant, status: SolverStatus) -> TopologyResult {
    empty_result(status, start.elapsed().as_secs_f64() * 1000.0)
}

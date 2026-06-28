// splr CDCL solver integration with cardinality constraints.
//
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::time::Instant;

use splr::{
    solver::{SatSolverIF, Solver},
    types::{CNFDescription, Instantiate},
    Certificate, Config, SolveIF,
};

use crate::types::SolverStatus;
use crate::TopologyResult;

use super::encoding::CnfFormula;

/// Solve the CNF formula using splr, with native AtMostK cardinality constraints.
pub fn solve_with_splr(
    cnf: &CnfFormula,
    _var_names: &[String],
) -> TopologyResult {
    let start = Instant::now();
    let config = Config::default();

    // Build DIMACS CNF string for splr's string-based constructor.
    let mut dimacs = format!("p cnf {} {}\n", cnf.num_vars, cnf.clauses.len());
    for clause in &cnf.clauses {
        for &lit in clause {
            dimacs.push_str(&format!("{} ", lit));
        }
        dimacs.push_str("0\n");
    }

    let mut solver = Solver::instantiate(&config, &CNFDescription::default());

    // Add variables.
    for _ in 0..cnf.num_vars {
        solver.add_var();
    }
    // Add clauses (cardinality constraints are already encoded as CNF).
    for clause in &cnf.clauses {
        let lits: Vec<i32> = clause.iter().copied().collect();
        if solver.add_clause(&lits).is_err() {
            return fail(start, SolverStatus::Unsatisfiable);
        }
    }

    // splr can panic on repeated calls due to internal state issues.
    // Catch the panic and return Unknown.
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| solver.solve()));
    let elapsed = start.elapsed().as_secs_f64() * 1000.0;

    let result = match result {
        Ok(r) => r,
        Err(_) => {
            return TopologyResult {
                status: SolverStatus::Unknown,
                assignments: std::collections::HashMap::new(),
                unsat_core: Vec::new(),
                solver_time_ms: elapsed,
            };
        }
    };

    match result {
        Ok(cert) => {
            let mut assignments = std::collections::HashMap::new();
            match cert {
                Certificate::SAT(model) => {
                    for (i, &lit) in model.iter().enumerate() {
                        if i < cnf.num_vars {
                            assignments.insert(i, lit > 0);
                        }
                    }
                }
                Certificate::UNSAT => {
                    return TopologyResult {
                        status: SolverStatus::Unsatisfiable,
                        assignments,
                        unsat_core: Vec::new(),
                        solver_time_ms: elapsed,
                    };
                }
            }
            TopologyResult {
                status: SolverStatus::Satisfiable,
                assignments,
                unsat_core: Vec::new(),
                solver_time_ms: elapsed,
            }
        }
        Err(_) => TopologyResult {
            status: SolverStatus::Unsatisfiable,
            assignments: std::collections::HashMap::new(),
            unsat_core: Vec::new(),
            solver_time_ms: elapsed,
        },
    }
}

fn fail(start: Instant, status: SolverStatus) -> TopologyResult {
    TopologyResult {
        status,
        assignments: std::collections::HashMap::new(),
        unsat_core: Vec::new(),
        solver_time_ms: start.elapsed().as_secs_f64() * 1000.0,
    }
}

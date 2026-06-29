// CaDiCaL CDCL solver integration via rustsat traits.
//
// Migrated from splr 0.13 (2026-06-28).
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
// Extended: solve_with_cadical_cores — U5 of docs/plans/2026-06-28-003-feat-unsat-provenance-tension-detection-plan.md

use std::time::Instant;

use rustsat::{
    solvers::{FreezeVar, Solve, SolveIncremental, SolverResult},
    types::{Lit, TernaryVal, Var},
};
use rustsat_cadical::CaDiCaL;

use crate::types::SolverStatus;
use crate::TopologyResult;

use super::encoding::CnfFormula;

/// Convert a signed i32 literal to a rustsat `Lit`.
fn lit_from_i32(lit: i32) -> Lit {
    let var_idx = (lit.unsigned_abs() - 1) as u32;
    if lit > 0 {
        Lit::positive(var_idx)
    } else {
        Lit::negative(var_idx)
    }
}

/// Solve the CNF formula using CaDiCaL via the rustsat trait interface
/// (without core extraction). Kept for backward compatibility.
#[allow(dead_code)]
pub fn solve_with_cadical(
    cnf: &CnfFormula,
    _var_names: &[String],
) -> TopologyResult {
    let start = Instant::now();

    if cnf.num_vars == 0 || cnf.clauses.is_empty() {
        return empty_result(SolverStatus::Unsatisfiable, 0.0);
    }

    let mut solver = CaDiCaL::default();

    for clause in &cnf.clauses {
        let lits: Vec<Lit> = clause.iter().map(|&l| lit_from_i32(l)).collect();
        if solver.add_clause_ref(&lits).is_err() {
            return fail(start, SolverStatus::Unsatisfiable);
        }
    }

    solve_inner(&mut solver, cnf, start)
}

/// Solve with selector-literal UNSAT core extraction.
///
/// Each original clause is extended with a fresh selector variable
/// (lit = positive selector). The selector variables are frozen to prevent
/// preprocessor elimination. All selectors are assumed FALSE — on UNSAT,
/// `core()` returns the failed assumption literals whose variables map to
/// the core clause indices.
///
/// On SAT: returns assignments for original variables only (selector
/// variables filtered out).
pub fn solve_with_cadical_cores(
    cnf: &CnfFormula,
    _var_names: &[String],
) -> TopologyResult {
    let start = Instant::now();

    if cnf.num_vars == 0 || cnf.clauses.is_empty() {
        return empty_result(SolverStatus::Unsatisfiable, 0.0);
    }

    let num_clauses = cnf.clauses.len();
    let selector_start = cnf.num_vars;

    let mut solver = CaDiCaL::default();

    // Freeze all selector variables to prevent them from being eliminated.
    for ci in 0..num_clauses {
        let _ = solver.freeze_var(Var::new((selector_start + ci) as u32));
    }

    // Add each clause extended with its selector literal (positive so assuming
    // FALSE satisfies the clause; TRUE propagates the original clause).
    for (ci, clause) in cnf.clauses.iter().enumerate() {
        let mut lits: Vec<Lit> = clause.iter().map(|&l| lit_from_i32(l)).collect();
        lits.push(Lit::positive((selector_start + ci) as u32));
        if solver.add_clause_ref(&lits).is_err() {
            return fail(start, SolverStatus::Unsatisfiable);
        }
    }

    let assumps: Vec<Lit> = (0..num_clauses)
        .map(|ci| Lit::negative((selector_start + ci) as u32))
        .collect();

    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        solver.solve_assumps(&assumps)
    }));
    let elapsed = start.elapsed().as_secs_f64() * 1000.0;

    let result = match result {
        Ok(r) => r,
        Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
    };

    match result {
        Ok(SolverResult::Sat) => {
            let sol = match solver.full_solution() {
                Ok(s) => s,
                Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
            };
            let mut assignments = std::collections::HashMap::new();
            for i in 0..cnf.num_vars {
                let val = sol[Var::new(i as u32)];
                match val {
                    TernaryVal::True => { assignments.insert(i, true); }
                    TernaryVal::False => { assignments.insert(i, false); }
                    TernaryVal::DontCare => {}
                }
            }
            TopologyResult {
                status: SolverStatus::Satisfiable,
                num_vars: 0,
                num_clauses: 0,
                assignments,
                unsat_core: Vec::new(),
                solver_time_ms: elapsed,
                tensions: Vec::new(),
                conflict: None,
            }
        }
        Ok(SolverResult::Unsat) => {
            let core_lits = match solver.core() {
                Ok(lits) => lits,
                Err(_) => return empty_result(SolverStatus::Unsatisfiable, elapsed),
            };
            // core() returns assumption literals — map back to clause indices.
            let core_indices: Vec<usize> = core_lits
                .iter()
                .map(|lit| lit.var().idx32() as usize - selector_start)
                .filter(|&ci| ci < num_clauses)
                .collect();
            TopologyResult {
                status: SolverStatus::Unsatisfiable,
                num_vars: 0,
                num_clauses: 0,
                assignments: std::collections::HashMap::new(),
                unsat_core: core_indices,
                solver_time_ms: elapsed,
                tensions: Vec::new(),
                conflict: None,
            }
        }
        Ok(SolverResult::Interrupted) => empty_result(SolverStatus::Unknown, elapsed),
        Err(_) => empty_result(SolverStatus::Unsatisfiable, elapsed),
    }
}

#[allow(dead_code)]
fn solve_inner(solver: &mut CaDiCaL, cnf: &CnfFormula, start: Instant) -> TopologyResult {
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| solver.solve()));
    let elapsed = start.elapsed().as_secs_f64() * 1000.0;

    let result = match result {
        Ok(r) => r,
        Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
    };

    match result {
        Ok(SolverResult::Sat) => {
            let sol = match solver.full_solution() {
                Ok(s) => s,
                Err(_) => return empty_result(SolverStatus::Unknown, elapsed),
            };
            let mut assignments = std::collections::HashMap::new();
            for i in 0..cnf.num_vars {
                let val = sol[Var::new(i as u32)];
                match val {
                    TernaryVal::True => { assignments.insert(i, true); }
                    TernaryVal::False => { assignments.insert(i, false); }
                    TernaryVal::DontCare => {}
                }
            }
            TopologyResult {
                status: SolverStatus::Satisfiable,
                num_vars: 0,
                num_clauses: 0,
                assignments,
                unsat_core: Vec::new(),
                solver_time_ms: elapsed,
                tensions: Vec::new(),
                conflict: None,
            }
        }
        Ok(SolverResult::Unsat) => empty_result(SolverStatus::Unsatisfiable, elapsed),
        Ok(SolverResult::Interrupted) => empty_result(SolverStatus::Unknown, elapsed),
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
        tensions: Vec::new(),
        conflict: None,
    }
}

fn fail(start: Instant, status: SolverStatus) -> TopologyResult {
    empty_result(status, start.elapsed().as_secs_f64() * 1000.0)
}

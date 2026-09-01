//! Shared native Stage-3 model pipeline.
//!
//! This is deliberately independent of either PyO3 extension.  The design
//! bundle owns the packed model and calls this module directly; the router
//! extension's legacy list bridge remains a compatibility adapter.

use std::collections::HashMap;

#[cfg(feature = "sat")]
use crate::combinator::rewrite::RewriteError;
use crate::types::{InternalConstraintModel, SolverStatus, TopologyResult};
#[cfg(feature = "sat")]
use crate::types::TopologyGraph;

/// Solve one already-built native model, preserving the legacy pipeline's
/// rewrite, encoding, solving, and extraction order.
#[cfg(feature = "sat")]
pub fn solve_model(
    model: InternalConstraintModel,
    net_names: &[String],
    conflict_limit: Option<u32>,
    time_limit_ms: Option<u64>,
) -> Result<(TopologyResult, Vec<String>, TopologyGraph), RewriteError> {
    let model = if std::env::var("TEMPER_SKIP_REWRITE").is_ok() {
        model
    } else {
        crate::combinator::rewrite::rewrite(&model)?
    };
    let (cnf, var_names) = crate::encoding::encode_to_cnf(&model);
    let num_vars = cnf.num_vars;
    let num_clauses = cnf.num_clauses();
    let mut result = crate::solver::solve_with_cadical(
        &cnf,
        crate::solver::SolveLimits {
            conflict_limit,
            time_limit_ms,
        },
    );
    result.num_vars = num_vars;
    result.num_clauses = num_clauses;
    let topology = if result.status == SolverStatus::Satisfiable {
        crate::extraction::extract_topology(&model, &result.assignments, &var_names, net_names)
    } else {
        TopologyGraph {
            net_topologies: HashMap::new(),
        }
    };
    Ok((result, var_names, topology))
}

/// Audit one already-built native model against a solver assignment.
pub fn audit_model(
    model: &InternalConstraintModel,
    assignments: HashMap<usize, bool>,
    var_names: &[String],
) -> Vec<crate::audit::AuditViolation> {
    crate::audit::audit_constraints(
        model,
        &TopologyResult {
            status: SolverStatus::Satisfiable,
            num_vars: 0,
            num_clauses: 0,
            assignments,
            unsat_core: Vec::new(),
            solver_time_ms: 0.0,
            solver_stats: None,
        },
        var_names,
    )
}

// SAT encoding — constraint model → CNF translation.
//
// Origin: U5 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable, SatVariable};

/// A CNF formula: list of clauses (each clause is a list of signed variable indices).
/// Positive index = true literal, negative index = false literal.
pub struct CnfFormula {
    pub num_vars: usize,
    pub clauses: Vec<Vec<i32>>,
    pub var_names: Vec<String>,
}

/// Convert the internal constraint model to CNF.
pub fn encode_to_cnf(model: &InternalConstraintModel) -> (CnfFormula, Vec<String>, Vec<(Vec<usize>, usize)>) {
    let mut var_map: Vec<SatVariable> = Vec::new();
    let mut name_to_idx: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    let mut clauses: Vec<Vec<i32>> = Vec::new();
    let mut cardinality_constraints: Vec<(Vec<usize>, usize)> = Vec::new();

    let mut add_var = |vm: &mut Vec<SatVariable>, nm: &mut std::collections::HashMap<String, usize>, name: &str| -> usize {
        if let Some(&idx) = nm.get(name) {
            idx
        } else {
            let idx = vm.len();
            vm.push(SatVariable::new(name, ""));
            nm.insert(name.to_string(), idx);
            idx
        }
    };

    let mut encode_lit = |idx: usize, pos: bool| -> i32 {
        if pos { (idx + 1) as i32 } else { -((idx + 1) as i32) }
    };

    // Map all internal variables to SAT variable indices.
    for v in &model.variables {
        match v {
            InternalVariable::NetChannel { name, .. } |
            InternalVariable::NetLayer { name, .. } |
            InternalVariable::Via { name, .. } |
            InternalVariable::Ordering { name, .. } => {
                add_var(&mut var_map, &mut name_to_idx, name);
            }
        }
    }

    // Encode constraints.
    for c in &model.constraints {
        match c {
            InternalConstraint::Capacity { channel_id: _ch, capacity: _cap, slack_factor: _sf, terms } => {
                if terms.is_empty() {
                    continue;
                }
                // Compute max_nets = floor(capacity * slack / min_width)
                let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
                let max_nets = ((_cap * _sf) / min_width).floor() as usize;

                let mut var_indices: Vec<usize> = Vec::new();
                for (vname, _w) in terms {
                    if let Some(&idx) = name_to_idx.get(vname) {
                        var_indices.push(idx);
                    }
                }

                if !var_indices.is_empty() && max_nets < var_indices.len() {
                    // Delegate cardinality to the solver (splr natively supports AtMostK).
                    cardinality_constraints.push((var_indices, max_nets));
                }
            }
            InternalConstraint::DiffPair { p_var_name, n_var_name, .. } => {
                if let (Some(&p), Some(&n)) = (name_to_idx.get(p_var_name), name_to_idx.get(n_var_name)) {
                    // p ↔ n: (¬p ∨ n) ∧ (p ∨ ¬n)
                    clauses.push(vec![encode_lit(p, false), encode_lit(n, true)]);
                    clauses.push(vec![encode_lit(p, true), encode_lit(n, false)]);
                }
            }
            InternalConstraint::LayerRestriction { var_name, allowed } => {
                if let Some(&idx) = name_to_idx.get(var_name) {
                    // Unit clause: var = allowed
                    clauses.push(vec![encode_lit(idx, *allowed)]);
                }
            }
        }
    }

    let var_names: Vec<String> = var_map.iter().map(|v| v.name.clone()).collect();

    (
        CnfFormula {
            num_vars: var_map.len(),
            clauses,
            var_names: var_names.clone(),
        },
        var_names,
        cardinality_constraints,
    )
}

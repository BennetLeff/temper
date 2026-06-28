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

/// Encode AtMostK cardinality constraint via Sinz (2005) sequential counter.
///
/// Adds O(n·k) auxiliary variables to `var_map` and O(n·k) clauses to
/// `clauses`.  Variables are referenced by index into `var_map`.
fn encode_at_most_k(
    clauses: &mut Vec<Vec<i32>>,
    var_map: &mut Vec<SatVariable>,
    vars: &[usize],
    k: usize,
) {
    let n = vars.len();
    if k >= n {
        return;
    }
    if k == 0 {
        for &vi in vars {
            clauses.push(vec![-((vi + 1) as i32)]);
        }
        return;
    }

    // Register variables r[i][j] for i=0..n-2, j=0..k-1.
    // r[i][j]: at least j+1 of vars[0..i] are true.
    let r_start = var_map.len();
    for i in 0..(n - 1) {
        for j in 0..k {
            var_map.push(SatVariable::new(
                format!("sc_r{i}_{j}"),
                format!("seq-counter r{i}.{j}"),
            ));
        }
    }

    let r = |i: usize, j: usize| -> i32 {
        ((r_start + i * k + j + 1) as i32)
    };

    let v = |i: usize| -> i32 { ((vars[i] + 1) as i32) };

    // Position 0.
    clauses.push(vec![-v(0), r(0, 0)]);
    for j in 1..k {
        clauses.push(vec![-r(0, j)]);
    }

    // Positions 1..n-2.
    for i in 1..(n - 1) {
        clauses.push(vec![-v(i), r(i, 0)]);
        clauses.push(vec![-r(i - 1, 0), r(i, 0)]);
        for j in 1..k {
            clauses.push(vec![-v(i), -r(i - 1, j - 1), r(i, j)]);
            clauses.push(vec![-r(i - 1, j), r(i, j)]);
        }
    }

    // Exclusion: if count already reaches k, no further variable may be true.
    for i in k..n {
        clauses.push(vec![-v(i), -r(i - 1, k - 1)]);
    }
}

/// Convert the internal constraint model to CNF.
pub fn encode_to_cnf(model: &InternalConstraintModel) -> (CnfFormula, Vec<String>) {
    let mut var_map: Vec<SatVariable> = Vec::new();
    let mut name_to_idx: std::collections::HashMap<String, usize> = std::collections::HashMap::new();
    let mut clauses: Vec<Vec<i32>> = Vec::new();

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
                    // Encode AtMostK as CNF via sequential counter (Sinz 2005),
                    // since splr 0.13 does not expose a native add_atmostk API.
                    let aux_start = var_map.len();
                    encode_at_most_k(&mut clauses, &mut var_map, &var_indices, max_nets);
                    // Track that cardinality was encoded (for solver awareness).
                    let _ = aux_start; // auxiliary vars added to var_map inline
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
    )
}

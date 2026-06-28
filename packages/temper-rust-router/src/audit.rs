// Constraint audit — validate solver output against the constraints themselves.
//
// Unlike golden fixtures (which validate against a known-buggy Python solver),
// this module directly checks that the Rust solver's assignments satisfy every
// constraint in the input model.
//
// Origin: U2 (replaced) of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::collections::{HashMap, HashSet};

use crate::types::{InternalConstraint, InternalConstraintModel, TopologyResult, SolverStatus};

/// Result of auditing a single constraint.
#[derive(Debug, PartialEq)]
pub enum AuditViolation {
    Capacity {
        channel_id: String,
        max_nets: usize,
        actual_count: usize,
        violating_vars: Vec<String>,
    },
    DiffPairMismatch {
        channel_id: String,
        p_var: String,
        n_var: String,
        p_value: bool,
        n_value: bool,
    },
    LayerViolation {
        var_name: String,
        expected: bool,
        actual: bool,
    },
    UnexplainedUnsat,
    NoAssignmentForVar(String),
}

/// Audit a solver result against the original constraint model.
pub fn audit_constraints(
    model: &InternalConstraintModel,
    result: &TopologyResult,
    var_names: &[String],
) -> Vec<AuditViolation> {
    let mut violations = Vec::new();

    // Build name → index map
    let name_to_idx: HashMap<&str, usize> = var_names
        .iter()
        .enumerate()
        .map(|(i, name)| (name.as_str(), i))
        .collect();

    // Helper: get truth value for a variable name
    let get_val = |name: &str, violations: &mut Vec<AuditViolation>| -> Option<bool> {
        match name_to_idx.get(name) {
            Some(&idx) => result.assignments.get(&idx).copied(),
            None => {
                violations.push(AuditViolation::NoAssignmentForVar(name.to_string()));
                None
            }
        }
    };

    if result.status != SolverStatus::Satisfiable {
        // UNSAT: check if the problem is actually unsatisfiable.
        // We can't prove that from the model alone, but we can check for
        // trivial contradictions in the constraint set.
        violations.push(AuditViolation::UnexplainedUnsat);
        return violations;
    }

    for c in &model.constraints {
        match c {
            InternalConstraint::Capacity { channel_id, capacity: _cap, slack_factor: _sf, terms } => {
                if terms.is_empty() {
                    continue;
                }
                let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
                let max_nets = ((_cap * _sf) / min_width).floor() as usize;

                let mut true_vars: Vec<String> = Vec::new();
                for (vname, _w) in terms {
                    if let Some(val) = get_val(vname, &mut violations) {
                        if val {
                            true_vars.push(vname.clone());
                        }
                    }
                }

                if true_vars.len() > max_nets {
                    violations.push(AuditViolation::Capacity {
                        channel_id: channel_id.clone(),
                        max_nets,
                        actual_count: true_vars.len(),
                        violating_vars: true_vars,
                    });
                }
            }
            InternalConstraint::DiffPair { channel_id, p_var_name, n_var_name } => {
                let p_val = get_val(p_var_name, &mut violations);
                let n_val = get_val(n_var_name, &mut violations);
                if let (Some(p), Some(n)) = (p_val, n_val) {
                    if p != n {
                        violations.push(AuditViolation::DiffPairMismatch {
                            channel_id: channel_id.clone(),
                            p_var: p_var_name.clone(),
                            n_var: n_var_name.clone(),
                            p_value: p,
                            n_value: n,
                        });
                    }
                }
            }
            InternalConstraint::LayerRestriction { var_name, allowed } => {
                if let Some(val) = get_val(var_name, &mut violations) {
                    if val != *allowed {
                        violations.push(AuditViolation::LayerViolation {
                            var_name: var_name.clone(),
                            expected: *allowed,
                            actual: val,
                        });
                    }
                }
            }
        }
    }

    violations
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable, SolverStatus, TopologyResult};
    use std::collections::HashMap;

    fn make_result(status: SolverStatus, assignments: HashMap<usize, bool>) -> TopologyResult {
        TopologyResult { status, num_vars: 0, num_clauses: 0, assignments, unsat_core: vec![], solver_time_ms: 0.0 }
    }

    #[test]
    fn capacity_within_bounds() {
        let (model, var_names) = make_self_test_model();
        let mut a = HashMap::new();
        a.insert(0, true); a.insert(1, true);
        a.insert(2, false); a.insert(3, false);
        let r = make_result(SolverStatus::Satisfiable, a);
        assert!(audit_constraints(&model, &r, &var_names).is_empty());
    }

    #[test]
    fn capacity_violation() {
        let (model, var_names) = make_self_test_model();
        let mut a = HashMap::new();
        for i in 0..4 { a.insert(i, i < 3); }
        let r = make_result(SolverStatus::Satisfiable, a);
        let v = audit_constraints(&model, &r, &var_names);
        assert_eq!(v.len(), 1);
        match &v[0] { AuditViolation::Capacity { actual_count, max_nets, .. } => { assert_eq!(*actual_count, 3); assert_eq!(*max_nets, 2); } _ => panic!() }
    }

    #[test]
    fn capacity_exact_limit() {
        let (model, var_names) = make_self_test_model();
        let mut a = HashMap::new();
        a.insert(0, true); a.insert(1, true);
        for i in 2..4 { a.insert(i, false); }
        let r = make_result(SolverStatus::Satisfiable, a);
        assert!(audit_constraints(&model, &r, &var_names).is_empty());
    }

    #[test]
    fn diff_pair_mismatch() {
        let vn = vec!["p_CH1".to_string(), "n_CH1".to_string()];
        let m = InternalConstraintModel {
            variables: vn.iter().enumerate().map(|(i,n)| InternalVariable::NetChannel { name:n.clone(), net_idx:i, channel_id:"CH1".into() }).collect(),
            constraints: vec![InternalConstraint::DiffPair { channel_id:"CH1".into(), p_var_name:"p_CH1".into(), n_var_name:"n_CH1".into() }],
        };
        let mut a = HashMap::new();
        a.insert(0, true); a.insert(1, false);
        let r = make_result(SolverStatus::Satisfiable, a);
        let v = audit_constraints(&m, &r, &vn);
        assert_eq!(v.len(), 1);
        match &v[0] { AuditViolation::DiffPairMismatch { .. } => {} _ => panic!() }
    }

    #[test]
    fn diff_pair_match() {
        let vn = vec!["p_CH1".to_string(), "n_CH1".to_string()];
        let m = InternalConstraintModel {
            variables: vn.iter().enumerate().map(|(i,n)| InternalVariable::NetChannel { name:n.clone(), net_idx:i, channel_id:"CH1".into() }).collect(),
            constraints: vec![InternalConstraint::DiffPair { channel_id:"CH1".into(), p_var_name:"p_CH1".into(), n_var_name:"n_CH1".into() }],
        };
        let mut a = HashMap::new();
        a.insert(0, true); a.insert(1, true);
        let r = make_result(SolverStatus::Satisfiable, a);
        assert!(audit_constraints(&m, &r, &vn).is_empty());
    }

    #[test]
    fn layer_violation() {
        let vn = vec!["uses_N0_L1_E0".to_string()];
        let m = InternalConstraintModel {
            variables: vn.iter().enumerate().map(|(i,n)| InternalVariable::NetChannel { name:n.clone(), net_idx:i, channel_id:"L1_E0".into() }).collect(),
            constraints: vec![InternalConstraint::LayerRestriction { var_name:"uses_N0_L1_E0".into(), allowed:false }],
        };
        let mut a = HashMap::new();
        a.insert(0, true);
        let r = make_result(SolverStatus::Satisfiable, a);
        let v = audit_constraints(&m, &r, &vn);
        assert_eq!(v.len(), 1);
        match &v[0] { AuditViolation::LayerViolation { .. } => {} _ => panic!() }
    }

    #[test]
    fn unsat_flag() {
        let (m, vn) = make_self_test_model();
        let r = make_result(SolverStatus::Unsatisfiable, HashMap::new());
        let v = audit_constraints(&m, &r, &vn);
        assert_eq!(v.len(), 1);
        match &v[0] { AuditViolation::UnexplainedUnsat => {} _ => panic!() }
    }

    /// Brute-force constraint checker for a single assignment.
    fn brute_force_check(model: &InternalConstraintModel, assign: &HashMap<usize, bool>) -> Vec<String> {
        let mut violations = Vec::new();
        for c in &model.constraints {
            match c {
                InternalConstraint::Capacity { channel_id, capacity, slack_factor, terms } => {
                    if terms.is_empty() { continue; }
                    let min_w = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
                    let max_nets = ((capacity * slack_factor) / min_w).floor() as usize;
                    let mut true_count = 0;
                    for (vname, _) in terms {
                        // Find index by searching model variables
                        if let Some(pos) = model.variables.iter().position(|v| match v {
                            InternalVariable::NetChannel { name, .. } => name == vname,
                            InternalVariable::NetLayer { name, .. } => name == vname,
                            InternalVariable::Via { name, .. } => name == vname,
                            InternalVariable::Ordering { name, .. } => name == vname,
                        }) {
                            if assign.get(&pos).copied().unwrap_or(false) { true_count += 1; }
                        }
                    }
                    if true_count > max_nets {
                        violations.push(format!("capacity:{channel_id}:{true_count}>{max_nets}"));
                    }
                }
                InternalConstraint::DiffPair { p_var_name, n_var_name, .. } => {
                    let p_pos = model.variables.iter().position(|v| match v {
                        InternalVariable::NetChannel { name, .. } => name == p_var_name, _ => false,
                    });
                    let n_pos = model.variables.iter().position(|v| match v {
                        InternalVariable::NetChannel { name, .. } => name == n_var_name, _ => false,
                    });
                    if let (Some(p), Some(n)) = (p_pos, n_pos) {
                        let pv = assign.get(&p).copied().unwrap_or(false);
                        let nv = assign.get(&n).copied().unwrap_or(false);
                        if pv != nv { violations.push(format!("diffpair:{p_var_name}!={n_var_name}")); }
                    }
                }
                InternalConstraint::LayerRestriction { var_name, allowed } => {
                    if let Some(pos) = model.variables.iter().position(|v| match v {
                        InternalVariable::NetChannel { name, .. } => name == var_name, _ => false,
                    }) {
                        let val = assign.get(&pos).copied().unwrap_or(false);
                        if val != *allowed { violations.push(format!("layer:{var_name}:{val}!={allowed}")); }
                    }
                }
            }
        }
        violations
    }

    #[test]
    fn audit_completeness_all_n4_combos() {
        // Build a model with 4 vars and all 3 constraint types, then verify
        // the audit matches brute-force for all 2^4 = 16 assignments.
        let vn: Vec<String> = (0..4).map(|i| format!("v{i}")).collect();
        let model = InternalConstraintModel {
            variables: vn.iter().enumerate().map(|(i, n)| InternalVariable::NetChannel {
                name: n.clone(), net_idx: i, channel_id: "CH1".into(),
            }).collect(),
            constraints: vec![
                InternalConstraint::Capacity {
                    channel_id: "CH1".into(), capacity: 2.0, slack_factor: 1.0,
                    terms: vn.iter().map(|n| (n.clone(), 1.0)).collect(),
                },
                InternalConstraint::DiffPair {
                    channel_id: "CH1".into(),
                    p_var_name: "v0".into(), n_var_name: "v1".into(),
                },
                InternalConstraint::LayerRestriction {
                    var_name: "v3".into(), allowed: false,
                },
            ],
        };

        for bits in 0..16u32 {
            let mut assign = HashMap::new();
            for i in 0..4 { assign.insert(i, (bits >> i) & 1 == 1); }

            let result = TopologyResult {
                status: SolverStatus::Satisfiable,
                num_vars: 0,
                num_clauses: 0,
                assignments: assign.clone(),
                unsat_core: vec![],
                solver_time_ms: 0.0,
            };

            let audit_violations = audit_constraints(&model, &result, &vn);
            let brute_violations = brute_force_check(&model, &assign);

            let audit_has = !audit_violations.is_empty();
            let brute_has = !brute_violations.is_empty();

            assert_eq!(audit_has, brute_has,
                "Mismatch for assignment {bits:04b}: audit={audit_has} brute={brute_has} audit_v={audit_violations:?} brute_v={brute_violations:?}"
            );
        }
    }
}

/// Build a small constraint model for self-testing the audit logic.
fn make_self_test_model() -> (InternalConstraintModel, Vec<String>) {
    // 4 nets, channel CH1, capacity 2
    let var_names: Vec<String> = (0..4).map(|i| format!("net{}_CH1", i)).collect();

    let vars: Vec<crate::types::InternalVariable> = var_names
        .iter()
        .enumerate()
        .map(|(i, name)| crate::types::InternalVariable::NetChannel {
            name: name.clone(),
            net_idx: i,
            channel_id: "CH1".into(),
        })
        .collect();

    let constraints = vec![
        InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 2.0,
            slack_factor: 1.0,
            terms: var_names.iter().map(|n| (n.clone(), 1.0)).collect(),
        },
    ];

    (InternalConstraintModel { variables: vars, constraints }, var_names)
}

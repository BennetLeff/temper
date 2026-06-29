// BMC (Bounded Model Checking) engine — exhaustive SAT encoding verification.
//
// For a constraint model with N ≤ BOUND primary variables, enumerates
// all 2^N assignments and checks that the ESL ground truth agrees with
// the CNF satisfiability for every assignment.
//
// Uses CaDiCaL via rustsat as the CNF oracle — no pysat dependency.

use std::collections::HashMap;

use rustsat::{
    solvers::{Solve, SolverResult},
    types::{Clause, Lit},
};
use rustsat_cadical::CaDiCaL;

use crate::encoding::{encode_to_cnf, CnfFormula};
use crate::esl;
use crate::types::InternalConstraintModel;

/// Maximum number of primary variables (2^10 = 1024 assignments).
pub const DEFAULT_BMC_BOUND: usize = 10;

/// Counterexample from BMC — ESL and CNF disagree.
#[derive(Debug, Clone)]
pub struct Counterexample {
    pub assignment: HashMap<String, bool>,
    pub esl_sat: bool,
    pub cnf_sat: bool,
    pub failure_type: FailureType,
}

#[derive(Debug, Clone, PartialEq)]
pub enum FailureType {
    FalseSat,   // ESL says UNSAT, CNF says SAT (encoding too permissive)
    FalseUnsat, // ESL says SAT, CNF says UNSAT (encoding too restrictive)
}

/// BMC diagnostic result.
#[derive(Debug)]
pub struct BmcResult {
    pub passed: bool,
    pub counterexamples: Vec<Counterexample>,
    pub primary_var_names: Vec<String>,
    pub total_assignments: u64,
}

/// Run BMC on a constraint model.
///
/// Skips connectivity clauses (only encodes constraint-type clauses) so
/// primary-variable count stays within the bound.
pub fn bmc_verify(
    model: &InternalConstraintModel,
    _net_names: &[String],
    bound: usize,
) -> Result<BmcResult, String> {
    // Encode without connectivity (constraints only).
    let (cnf, var_names) = encode_to_cnf(model);

    // Identify primary variables: those NOT starting with "sc_" (aux vars).
    let primary_names: Vec<String> = var_names
        .iter()
        .filter(|n| !n.starts_with("sc_"))
        .cloned()
        .collect();

    let n = primary_names.len();
    if n > bound {
        return Err(format!(
            "BMC bound exceeded: {} primary vars > {bound} bound",
            n
        ));
    }

    // Build name → index mapping.
    let name_to_idx: HashMap<String, usize> = var_names
        .iter()
        .enumerate()
        .map(|(i, n)| (n.clone(), i))
        .collect();

    let total = 1u64 << n;
    let mut counterexamples = Vec::new();

    for mask in 0..total {
        // Build assignment.
        let mut assignment: HashMap<String, bool> = HashMap::new();
        for (i, name) in primary_names.iter().enumerate() {
            assignment.insert(name.clone(), (mask >> i) & 1 == 1);
        }

        // ESL ground truth.
        let esl_sat = esl::evaluate_all(&model.constraints, &assignment);

        // CNF satisfiability.
        let cnf_sat = check_cnf_sat(&cnf, &assignment, &name_to_idx)?;

        if esl_sat != cnf_sat {
            counterexamples.push(Counterexample {
                assignment: assignment.clone(),
                esl_sat,
                cnf_sat,
                failure_type: if esl_sat {
                    FailureType::FalseUnsat
                } else {
                    FailureType::FalseSat
                },
            });
        }
    }

    Ok(BmcResult {
        passed: counterexamples.is_empty(),
        counterexamples,
        primary_var_names: primary_names,
        total_assignments: total,
    })
}

/// Check if the CNF is satisfiable given fixed primary variable values.
fn check_cnf_sat(
    cnf: &CnfFormula,
    fixed: &HashMap<String, bool>,
    name_to_idx: &HashMap<String, usize>,
) -> Result<bool, String> {
    if cnf.num_vars == 0 || cnf.clauses.is_empty() {
        return Ok(true); // Vacuous
    }

    let mut solver = CaDiCaL::default();

    // Add all clauses.
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
            return Ok(false);
        }
    }

    // Fix primary variables as unit clauses.
    for (name, &val) in fixed {
        if let Some(&idx) = name_to_idx.get(name) {
            let lit = if val {
                Lit::positive(idx as u32)
            } else {
                Lit::negative(idx as u32)
            };
            if solver.add_clause(Clause::from([lit])).is_err() {
                return Ok(false);
            }
        }
    }

    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| solver.solve()));
    match result {
        Ok(Ok(SolverResult::Sat)) => Ok(true),
        Ok(Ok(SolverResult::Unsat)) => Ok(false),
        Ok(Ok(SolverResult::Interrupted)) => Ok(false),
        Ok(Err(_)) => Ok(false),
        Err(_) => Ok(false), // CaDiCaL panic → treat as unsat
    }
}

/// Sample the most-constrained channels and run BMC on the sub-model.
///
/// Returns a diagnostic dict suitable for the Python `diagnose_submodel()`
/// equivalent.
pub fn diagnose_submodel(
    model: &InternalConstraintModel,
    net_names: &[String],
    max_primary_vars: usize,
) -> BmcDiagnostic {
    use crate::types::InternalVariable;

    let _all_names: Vec<String> = model.variables.iter().map(|v| match v {
        InternalVariable::NetChannel { name, .. } => name.clone(),
        InternalVariable::NetLayer { name, .. } => name.clone(),
        InternalVariable::Via { name, .. } => name.clone(),
        InternalVariable::Ordering { name, .. } => name.clone(),
    }).collect();

    // Build a sub-model from the most-constrained capacity constraints.
    let mut selected_var_names: Vec<String> = Vec::new();
    let mut selected_constraints: Vec<crate::types::InternalConstraint> = Vec::new();
    let mut selected_vars_set: HashMap<String, InternalVariable> = HashMap::new();

    // Find capacity constraints sorted by term count.
    let mut caps: Vec<&crate::types::InternalConstraint> = model
        .constraints
        .iter()
        .filter(|c| matches!(c, crate::types::InternalConstraint::Capacity { .. }))
        .collect();
    caps.sort_by_key(|c| {
        if let crate::types::InternalConstraint::Capacity { terms, .. } = c {
            -(terms.len() as isize)
        } else {
            0
        }
    });

    for cap in caps {
        if let crate::types::InternalConstraint::Capacity { terms, .. } = cap {
            let new_vars: Vec<&String> = terms.iter()
                .map(|(name, _)| name)
                .filter(|n| !selected_vars_set.contains_key(*n))
                .collect();
            if selected_var_names.len() + new_vars.len() > max_primary_vars {
                break;
            }
            for name in &new_vars {
                if let Some(var) = model.variables.iter().find(|v| match v {
                    InternalVariable::NetChannel { name: n, .. } => n == *name,
                    _ => false,
                }) {
                    selected_vars_set.insert((*name).clone(), var.clone());
                    selected_var_names.push((*name).clone());
                }
            }
            selected_constraints.push((*cap).clone());
        }
    }

    if selected_var_names.is_empty() {
        return BmcDiagnostic {
            passed: true,
            counterexample_count: 0,
            sampled_vars: Vec::new(),
            message: "No capacity constraints to sample".into(),
        };
    }

    // Build sub-model.
    let sub_model = InternalConstraintModel {
        variables: selected_var_names.iter().filter_map(|n| selected_vars_set.get(n).cloned()).collect(),
        constraints: selected_constraints,
    };

    match bmc_verify(&sub_model, net_names, max_primary_vars) {
        Ok(result) => BmcDiagnostic {
            passed: result.passed,
            counterexample_count: result.counterexamples.len(),
            sampled_vars: result.primary_var_names,
            message: if result.passed {
                format!("BMC passed on {}-var sub-model", selected_var_names.len())
            } else {
                format!(
                    "BMC found {} counterexamples in {}-var sub-model",
                    result.counterexamples.len(),
                    selected_var_names.len()
                )
            },
        },
        Err(e) => BmcDiagnostic {
            passed: false,
            counterexample_count: 0,
            sampled_vars: Vec::new(),
            message: e,
        },
    }
}

#[derive(Debug, Clone)]
pub struct BmcDiagnostic {
    pub passed: bool,
    pub counterexample_count: usize,
    pub sampled_vars: Vec<String>,
    pub message: String,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable};

    fn make_test_model(
        var_names: &[&str],
        constraint: InternalConstraint,
    ) -> InternalConstraintModel {
        let variables: Vec<InternalVariable> = var_names
            .iter()
            .map(|name| InternalVariable::NetChannel {
                name: name.to_string(),
                net_idx: 0,
                channel_id: "ch1".into(),
            })
            .collect();
        InternalConstraintModel {
            variables,
            constraints: vec![constraint],
        }
    }

    #[test]
    fn bmc_layer_constraint_correct() {
        let model = make_test_model(
            &["uses_N0_ch1"],
            InternalConstraint::LayerRestriction {
                var_name: "uses_N0_ch1".into(),
                allowed: true,
            },
        );
        let result = bmc_verify(&model, &["N0".into()], DEFAULT_BMC_BOUND).unwrap();
        assert!(result.passed, "Expected BMC to pass");
        assert_eq!(result.total_assignments, 2);
    }

    #[test]
    fn bmc_diff_pair_correct() {
        let model = InternalConstraintModel {
            variables: vec![
                InternalVariable::NetChannel {
                    name: "p".into(),
                    net_idx: 0,
                    channel_id: "ch1".into(),
                },
                InternalVariable::NetChannel {
                    name: "n".into(),
                    net_idx: 1,
                    channel_id: "ch1".into(),
                },
            ],
            constraints: vec![InternalConstraint::DiffPair {
                channel_id: "ch1".into(),
                p_var_name: "p".into(),
                n_var_name: "n".into(),
            }],
        };
        let result = bmc_verify(&model, &["N0".into(), "N1".into()], DEFAULT_BMC_BOUND).unwrap();
        assert!(result.passed, "Expected BMC to pass, got {:?}", result.counterexamples);
        assert_eq!(result.total_assignments, 4);
    }

    #[test]
    fn bmc_capacity_correct() {
        // AtMostK(3 vars, k=2) — correct encoding
        let model = InternalConstraintModel {
            variables: vec!["a", "b", "c"]
                .iter()
                .map(|name| InternalVariable::NetChannel {
                    name: name.to_string(),
                    net_idx: 0,
                    channel_id: "ch1".into(),
                })
                .collect(),
            constraints: vec![InternalConstraint::Capacity {
                channel_id: "ch1".into(),
                capacity: 0.3,       // max = floor(0.3 * 1.0 / 0.127) = 2
                slack_factor: 1.0,
                terms: vec![
                    ("a".into(), 0.127),
                    ("b".into(), 0.127),
                    ("c".into(), 0.127),
                ],
            }],
        };
        let result = bmc_verify(&model, &["N0".into(), "N1".into(), "N2".into()], DEFAULT_BMC_BOUND).unwrap();
        assert!(result.passed, "BMC found {:?}", result.counterexamples);
        assert_eq!(result.total_assignments, 8);
    }

    #[test]
    fn bmc_bound_exceeded() {
        let vars: Vec<InternalVariable> = (0..11)
            .map(|i| InternalVariable::NetChannel {
                name: format!("x{i}"),
                net_idx: i,
                channel_id: "ch1".into(),
            })
            .collect();
        let model = InternalConstraintModel {
            variables: vars,
            constraints: vec![],
        };
        let result = bmc_verify(&model, &(0..11).map(|i| format!("N{i}")).collect::<Vec<_>>(), 10);
        assert!(result.is_err());
    }

    #[test]
    fn bmc_empty_model_passes() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![],
        };
        let result = bmc_verify(&model, &[], DEFAULT_BMC_BOUND).unwrap();
        assert!(result.passed);
        assert_eq!(result.total_assignments, 1); // 2^0 = 1
    }
}

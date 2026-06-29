// ESL (Encoder Specification Language) — ground-truth constraint evaluation.
//
// Unlike the Python esl.py which uses a predicate DSL with closures,
// the Rust version implements evaluate() directly on InternalConstraint
// variants. The compiler ensures every variant is handled exhaustively.

use std::collections::HashMap;
use crate::types::InternalConstraint;

/// Evaluate all constraints against a variable assignment.
///
/// Returns true iff the assignment satisfies every constraint in the model.
/// Empty models (no constraints) are vacuously satisfied.
pub fn evaluate_all(
    constraints: &[InternalConstraint],
    assignment: &HashMap<String, bool>,
) -> bool {
    constraints.iter().all(|c| evaluate_one(c, assignment))
}

/// Evaluate a single constraint against a variable assignment.
pub fn evaluate_one(constraint: &InternalConstraint, assignment: &HashMap<String, bool>) -> bool {
    match constraint {
        InternalConstraint::Capacity {
            capacity,
            slack_factor,
            terms,
            ..
        } => {
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
            let true_count = terms
                .iter()
                .filter(|(name, _)| assignment.get(name).copied().unwrap_or(false))
                .count();
            true_count <= max_nets
        }
        InternalConstraint::DiffPair {
            p_var_name,
            n_var_name,
            ..
        } => {
            let p = assignment.get(p_var_name).copied().unwrap_or(false);
            let n = assignment.get(n_var_name).copied().unwrap_or(false);
            p == n
        }
        InternalConstraint::LayerRestriction {
            var_name,
            allowed,
        } => {
            assignment.get(var_name).copied().unwrap_or(false) == *allowed
        }
    }
}

/// Detailed violation information for diagnostic reporting.
#[derive(Debug, Clone)]
pub enum Violation {
    Capacity {
        constraint_name: String,
        channel_id: String,
        max_nets: usize,
        true_count: usize,
    },
    DiffPair {
        constraint_name: String,
        p_val: bool,
        n_val: bool,
    },
    Layer {
        constraint_name: String,
        var_name: String,
        expected: bool,
        actual: bool,
    },
}

/// Audit an assignment against all constraints, returning violations.
pub fn audit(
    constraints: &[InternalConstraint],
    assignment: &HashMap<String, bool>,
) -> Vec<Violation> {
    let mut violations = Vec::new();
    for c in constraints {
        if !evaluate_one(c, assignment) {
            violations.push(match c {
                InternalConstraint::Capacity {
                    channel_id,
                    capacity,
                    slack_factor,
                    terms,
                    ..
                } => {
                    let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
                    let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
                    let true_count = terms
                        .iter()
                        .filter(|(name, _)| assignment.get(name).copied().unwrap_or(false))
                        .count();
                    Violation::Capacity {
                        constraint_name: "Capacity".into(),
                        channel_id: channel_id.clone(),
                        max_nets,
                        true_count,
                    }
                }
                InternalConstraint::DiffPair {
                    p_var_name,
                    n_var_name,
                    ..
                } => {
                    let p = assignment.get(p_var_name).copied().unwrap_or(false);
                    let n = assignment.get(n_var_name).copied().unwrap_or(false);
                    Violation::DiffPair {
                        constraint_name: "DiffPair".into(),
                        p_val: p,
                        n_val: n,
                    }
                }
                InternalConstraint::LayerRestriction {
                    var_name,
                    allowed,
                } => Violation::Layer {
                    constraint_name: "Layer".into(),
                    var_name: var_name.clone(),
                    expected: *allowed,
                    actual: !allowed,
                },
            });
        }
    }
    violations
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::InternalConstraint;

    #[test]
    fn empty_model_is_vacuously_satisfied() {
        assert!(evaluate_all(&[], &HashMap::new()));
    }

    #[test]
    fn layer_restriction_true() {
        let c = InternalConstraint::LayerRestriction {
            var_name: "x0".into(),
            allowed: true,
        };
        let mut ass = HashMap::new();
        ass.insert("x0".into(), true);
        assert!(evaluate_one(&c, &ass));
    }

    #[test]
    fn layer_restriction_false() {
        let c = InternalConstraint::LayerRestriction {
            var_name: "x0".into(),
            allowed: true,
        };
        let mut ass = HashMap::new();
        ass.insert("x0".into(), false);
        assert!(!evaluate_one(&c, &ass));
    }

    #[test]
    fn diff_pair_matches() {
        let c = InternalConstraint::DiffPair {
            channel_id: "ch1".into(),
            p_var_name: "p".into(),
            n_var_name: "n".into(),
        };
        let mut ass = HashMap::new();
        ass.insert("p".into(), true);
        ass.insert("n".into(), true);
        assert!(evaluate_one(&c, &ass));
    }

    #[test]
    fn diff_pair_mismatch() {
        let c = InternalConstraint::DiffPair {
            channel_id: "ch1".into(),
            p_var_name: "p".into(),
            n_var_name: "n".into(),
        };
        let mut ass = HashMap::new();
        ass.insert("p".into(), true);
        ass.insert("n".into(), false);
        assert!(!evaluate_one(&c, &ass));
    }

    #[test]
    fn capacity_within_bounds() {
        // k = floor(0.3 * 1.0 / 0.127) = 2 — at most 2
        let c = InternalConstraint::Capacity {
            channel_id: "ch1".into(),
            capacity: 0.3,
            slack_factor: 1.0,
            terms: vec![
                ("a".into(), 0.127),
                ("b".into(), 0.127),
                ("c".into(), 0.127),
            ],
        };
        let mut ass = HashMap::new();
        ass.insert("a".into(), true);
        ass.insert("b".into(), true);
        ass.insert("c".into(), false);
        assert!(evaluate_one(&c, &ass));
    }

    #[test]
    fn capacity_exceeded() {
        let c = InternalConstraint::Capacity {
            channel_id: "ch1".into(),
            capacity: 0.3,
            slack_factor: 1.0,
            terms: vec![
                ("a".into(), 0.127),
                ("b".into(), 0.127),
                ("c".into(), 0.127),
            ],
        };
        let mut ass = HashMap::new();
        ass.insert("a".into(), true);
        ass.insert("b".into(), true);
        ass.insert("c".into(), true);
        assert!(!evaluate_one(&c, &ass));
    }

    #[test]
    fn audit_reports_violations() {
        let constraints = vec![InternalConstraint::LayerRestriction {
            var_name: "x0".into(),
            allowed: true,
        }];
        let mut ass = HashMap::new();
        ass.insert("x0".into(), false);
        let violations = audit(&constraints, &ass);
        assert_eq!(violations.len(), 1);
    }
}

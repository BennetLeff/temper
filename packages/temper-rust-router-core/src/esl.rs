// ESL (Encoder Specification Language) — ground-truth constraint evaluation.
//
// Unlike the Python esl.py which uses a predicate DSL with closures,
// the Rust version implements evaluate() directly on InternalConstraint
// variants. The compiler ensures every variant is handled exhaustively.

use crate::types::InternalConstraint;
use std::collections::HashMap;

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

/// The assigned value of a variable, defaulting to false when unset — the
/// reference's dict `.get(name, False)`.
fn assignment_value(assignment: &HashMap<String, bool>, name: impl AsRef<str>) -> bool {
    assignment.get(name.as_ref()).copied().unwrap_or(false)
}

/// Capacity-constraint metrics under an assignment: `(min_width, max_nets,
/// true_count)`.  Shared by `evaluate_one` and the audit's violation
/// construction so the two can never drift apart.
fn capacity_metrics(
    terms: &[(String, f64)],
    capacity: f64,
    slack_factor: f64,
    assignment: &HashMap<String, bool>,
) -> (f64, usize, usize) {
    let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
    let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
    let true_count = terms
        .iter()
        .filter(|(name, _)| assignment_value(assignment, name))
        .count();
    (min_width, max_nets, true_count)
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
            let (_, max_nets, true_count) =
                capacity_metrics(terms, *capacity, *slack_factor, assignment);
            true_count <= max_nets
        }
        InternalConstraint::DiffPair {
            p_var_name,
            n_var_name,
            ..
        } => assignment_value(assignment, p_var_name) == assignment_value(assignment, n_var_name),
        InternalConstraint::LayerRestriction { var_name, allowed } => {
            assignment_value(assignment, var_name) == *allowed
        }
        InternalConstraint::ChannelSeparation { .. } => {
            // ChannelSeparation is a structural constraint, not a behavioral one.
            // It is decomposed into sub-constraints before evaluation.
            true
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

/// The violation implied by one constraint under an assignment, or `None`
/// when the constraint is satisfied or structural (ChannelSeparation).
fn violation_for(c: &InternalConstraint, assignment: &HashMap<String, bool>) -> Option<Violation> {
    if evaluate_one(c, assignment) {
        return None;
    }
    Some(match c {
        InternalConstraint::ChannelSeparation { .. } => {
            // Structural — never violates (see `evaluate_one`); kept as an
            // arm for exhaustiveness.
            return None;
        }
        InternalConstraint::Capacity {
            channel_id,
            capacity,
            slack_factor,
            terms,
            ..
        } => {
            let (_, max_nets, true_count) =
                capacity_metrics(terms, *capacity, *slack_factor, assignment);
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
        } => Violation::DiffPair {
            constraint_name: "DiffPair".into(),
            p_val: assignment_value(assignment, p_var_name),
            n_val: assignment_value(assignment, n_var_name),
        },
        InternalConstraint::LayerRestriction { var_name, allowed } => Violation::Layer {
            constraint_name: "Layer".into(),
            var_name: var_name.clone(),
            expected: *allowed,
            // A violation means the assigned value differs from `allowed`.
            actual: assignment_value(assignment, var_name),
        },
    })
}

/// Audit an assignment against all constraints, returning violations.
pub fn audit(
    constraints: &[InternalConstraint],
    assignment: &HashMap<String, bool>,
) -> Vec<Violation> {
    constraints
        .iter()
        .filter_map(|c| violation_for(c, assignment))
        .collect()
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::types::InternalConstraint;

    #[cfg_attr(test, test)]
    fn empty_model_is_vacuously_satisfied() {
        assert!(evaluate_all(&[], &HashMap::new()));
    }

    #[cfg_attr(test, test)]
    fn layer_restriction_true() {
        let c = InternalConstraint::LayerRestriction {
            var_name: "x0".into(),
            allowed: true,
        };
        let mut ass = HashMap::new();
        ass.insert("x0".into(), true);
        assert!(evaluate_one(&c, &ass));
    }

    #[cfg_attr(test, test)]
    fn layer_restriction_false() {
        let c = InternalConstraint::LayerRestriction {
            var_name: "x0".into(),
            allowed: true,
        };
        let mut ass = HashMap::new();
        ass.insert("x0".into(), false);
        assert!(!evaluate_one(&c, &ass));
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("esl::tests::empty_model_is_vacuously_satisfied", empty_model_is_vacuously_satisfied),
        ("esl::tests::layer_restriction_true", layer_restriction_true),
        ("esl::tests::layer_restriction_false", layer_restriction_false),
        ("esl::tests::diff_pair_matches", diff_pair_matches),
        ("esl::tests::diff_pair_mismatch", diff_pair_mismatch),
        ("esl::tests::capacity_within_bounds", capacity_within_bounds),
        ("esl::tests::capacity_exceeded", capacity_exceeded),
        ("esl::tests::audit_reports_violations", audit_reports_violations),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

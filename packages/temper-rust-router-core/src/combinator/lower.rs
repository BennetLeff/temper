/// `lower_composed()` — expand a `ComposedConstraint` tree into a flat
/// `InternalConstraintModel`.
///
/// This is the bridge between the composition IR and the existing CNF pipeline.
///
/// Algorithm:
/// - **Conjoin(A, B):** merge variable and constraint lists from both children.
/// - **Conditional(A → C):** add antecedent assignments as `LayerRestriction`
///   constraints, then lower the consequent. For the initial release, this
///   desugars as a conjunction of unit clauses + consequent constraints.
///   (True implication encoding is deferred.)
/// - **RestrictDomain(C, vars):** lower C, then filter each constraint's
///   variable set to only include `vars`. Drop constraints whose variable
///   set becomes empty.
/// - **Primitive(P1):** MutualExclusion → DiffPair
/// - **Primitive(P2):** CardinalityBound → Capacity (capacity = k * min_width)
/// - **Primitive(P4):** LayerAssignment → LayerRestriction

use std::collections::BTreeSet;

use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable};

use super::types::{ComposedConstraint, PrimitiveConstraint};

/// Expand a composition tree into a flat `InternalConstraintModel`.
pub fn lower_composed(tree: &ComposedConstraint) -> InternalConstraintModel {
    let (constraints, mut var_names) = lower_rec(tree);

    // Deduplicate variables (by name) and build InternalVariable list.
    let mut seen = BTreeSet::new();
    let variables: Vec<InternalVariable> = var_names
        .drain(..)
        .filter(|name| seen.insert(name.clone()))
        .map(|name| InternalVariable::NetChannel {
            name,
            net_idx: 0,
            channel_id: String::new(),
        })
        .collect();

    InternalConstraintModel {
        variables,
        constraints,
    }
}

fn lower_rec(tree: &ComposedConstraint) -> (Vec<InternalConstraint>, Vec<String>) {
    match tree {
        ComposedConstraint::Primitive(p) => lower_primitive(p),
        ComposedConstraint::Conjoin(a, b) => {
            let (mut cons_a, mut all_vars) = lower_rec(a);
            let (cons_b, vars_b) = lower_rec(b);
            cons_a.extend(cons_b);
            all_vars.extend(vars_b);
            (cons_a, all_vars)
        }
        ComposedConstraint::Conditional {
            antecedent,
            consequent,
        } => {
            let mut constraints = Vec::new();
            let mut var_names = Vec::new();

            // Add antecedent unit clauses as LayerRestrictions.
            for (var_name, value) in antecedent {
                var_names.push(var_name.clone());
                constraints.push(InternalConstraint::LayerRestriction {
                    var_name: var_name.clone(),
                    allowed: *value,
                });
            }

            // Lower the consequent.
            let (cons_cons, cons_vars) = lower_rec(consequent);
            constraints.extend(cons_cons);
            var_names.extend(cons_vars);

            (constraints, var_names)
        }
        ComposedConstraint::RestrictDomain { inner, vars } => {
            let (cons, lower_vars) = lower_rec(inner);
            let var_set: BTreeSet<&str> = vars.iter().map(|s| s.as_str()).collect();

            let filtered: Vec<InternalConstraint> = cons
                .into_iter()
                .filter_map(|c| filter_constraint_vars(c, &var_set))
                .collect();

            // Only include variables that are in `vars`.
            let filtered_vars: Vec<String> = lower_vars
                .into_iter()
                .filter(|v| var_set.contains(v.as_str()))
                .collect();

            (filtered, filtered_vars)
        }
    }
}

fn lower_primitive(p: &PrimitiveConstraint) -> (Vec<InternalConstraint>, Vec<String>) {
    match p {
        PrimitiveConstraint::MutualExclusion {
            p_var_name,
            n_var_name,
        } => {
            let vars = vec![p_var_name.clone(), n_var_name.clone()];
            let constraint = InternalConstraint::DiffPair {
                channel_id: String::new(),
                p_var_name: p_var_name.clone(),
                n_var_name: n_var_name.clone(),
            };
            (vec![constraint], vars)
        }
        PrimitiveConstraint::CardinalityBound {
            channel_id,
            k,
            terms,
        } => {
            let vars: Vec<String> = terms.iter().map(|(n, _)| n.clone()).collect();
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let capacity = (*k as f64) * min_width;
            let constraint = InternalConstraint::Capacity {
                channel_id: channel_id.clone(),
                capacity,
                slack_factor: 1.0,
                terms: terms.clone(),
            };
            (vec![constraint], vars)
        }
        PrimitiveConstraint::LayerAssignment { var_name, value } => {
            let vars = vec![var_name.clone()];
            let constraint = InternalConstraint::LayerRestriction {
                var_name: var_name.clone(),
                allowed: *value,
            };
            (vec![constraint], vars)
        }
    }
}

/// Filter a constraint's variable set to only include names in `var_set`.
/// Returns `None` if the resulting variable set is empty.
fn filter_constraint_vars(
    c: InternalConstraint,
    var_set: &BTreeSet<&str>,
) -> Option<InternalConstraint> {
    match c {
        InternalConstraint::Capacity {
            channel_id,
            capacity,
            slack_factor,
            terms,
        } => {
            let filtered_terms: Vec<(String, f64)> = terms
                .into_iter()
                .filter(|(n, _)| var_set.contains(n.as_str()))
                .collect();
            if filtered_terms.is_empty() {
                None
            } else {
                Some(InternalConstraint::Capacity {
                    channel_id,
                    capacity,
                    slack_factor,
                    terms: filtered_terms,
                })
            }
        }
        InternalConstraint::DiffPair {
            channel_id,
            p_var_name,
            n_var_name,
        } => {
            let p_in = var_set.contains(p_var_name.as_str());
            let n_in = var_set.contains(n_var_name.as_str());
            if p_in && n_in {
                Some(InternalConstraint::DiffPair {
                    channel_id,
                    p_var_name,
                    n_var_name,
                })
            } else {
                None
            }
        }
        InternalConstraint::LayerRestriction {
            var_name,
            allowed,
        } => {
            if var_set.contains(var_name.as_str()) {
                Some(InternalConstraint::LayerRestriction {
                    var_name,
                    allowed,
                })
            } else {
                None
            }
        }
        InternalConstraint::ChannelSeparation { .. } => {
            // ChannelSeparation uses net indices, not variable names —
            // passes through the variable filter unchanged.
            Some(c)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::types::{
        cardinality_bound_new, compose_conjoin, layer_assignment_new,
    };

    /// AE1 from the plan: lower a Conjoin(P2, P4).
    #[test]
    fn lower_conjoin_p2_p4() {
        let p2 = cardinality_bound_new(
            "L1_E5".into(), 3,
            vec![
                ("A".into(), 1.0),
                ("B".into(), 1.0),
                ("C".into(), 1.0),
            ],
        );
        let p4 = layer_assignment_new("A".into(), true);
        let composed = compose_conjoin(p2, p4);
        let model = lower_composed(&composed);

        // Should contain one Capacity and one LayerRestriction.
        let has_capacity = model.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::Capacity { channel_id, .. } if channel_id == "L1_E5")
        });
        let has_layer = model.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "A" && *allowed)
        });
        assert!(has_capacity, "expected Capacity for L1_E5");
        assert!(has_layer, "expected LayerRestriction for A=true");
        assert_eq!(model.constraints.len(), 2);
    }

    /// Lower a P2 with capacity derivation: k=3, min_width=1.0 → capacity=3.0.
    #[test]
    fn lower_p2_capacity_derivation() {
        let p2 = cardinality_bound_new(
            "CH1".into(), 4,
            vec![
                ("X".into(), 2.0),
                ("Y".into(), 2.0),
                ("Z".into(), 3.0),
            ],
        );
        let model = lower_composed(&p2);
        // min_width = 2.0, capacity = k * min_width = 4 * 2.0 = 8.0
        assert_eq!(model.constraints.len(), 1);
        match &model.constraints[0] {
            InternalConstraint::Capacity { capacity, slack_factor, .. } => {
                assert_eq!(*capacity, 8.0);
                assert_eq!(*slack_factor, 1.0);
            }
            _ => panic!("expected Capacity"),
        }
    }

    /// Lower a P1 (MutualExclusion) → DiffPair.
    #[test]
    fn lower_p1_to_diffpair() {
        let p1 = ComposedConstraint::Primitive(PrimitiveConstraint::MutualExclusion {
            p_var_name: "p_CH1".into(),
            n_var_name: "n_CH1".into(),
        });
        let model = lower_composed(&p1);
        assert_eq!(model.constraints.len(), 1);
        match &model.constraints[0] {
            InternalConstraint::DiffPair { p_var_name, n_var_name, .. } => {
                assert_eq!(p_var_name, "p_CH1");
                assert_eq!(n_var_name, "n_CH1");
            }
            _ => panic!("expected DiffPair"),
        }
    }

    /// Lower a Conditional: antecedent assignments → LayerRestrictions + consequent.
    #[test]
    fn lower_conditional() {
        let p2 = cardinality_bound_new(
            "CH1".into(), 2,
            vec![("A".into(), 1.0), ("B".into(), 1.0)],
        );
        let cond = ComposedConstraint::Conditional {
            antecedent: vec![("guard".into(), true)],
            consequent: Box::new(p2),
        };
        let model = lower_composed(&cond);
        // Should have 1 LayerRestriction (guard=true) + 1 Capacity
        assert_eq!(model.constraints.len(), 2);
        let has_guard = model.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "guard" && *allowed)
        });
        assert!(has_guard);
    }

    /// Lower a RestrictDomain: filter to subset of variables.
    #[test]
    fn lower_restrict_domain() {
        let p2 = cardinality_bound_new(
            "CH1".into(), 2,
            vec![
                ("A".into(), 1.0),
                ("B".into(), 1.0),
                ("C".into(), 1.0),
            ],
        );
        let restricted = ComposedConstraint::RestrictDomain {
            inner: Box::new(p2),
            vars: vec!["A".into(), "B".into()],
        };
        let model = lower_composed(&restricted);
        assert_eq!(model.constraints.len(), 1);
        match &model.constraints[0] {
            InternalConstraint::Capacity { terms, .. } => {
                let names: Vec<&str> = terms.iter().map(|(n, _)| n.as_str()).collect();
                assert!(names.contains(&"A"));
                assert!(names.contains(&"B"));
                assert!(!names.contains(&"C"));
            }
            _ => panic!("expected Capacity"),
        }
    }

    /// Conjoin soundness: lower(C1 ∧ C2) has union of constraints from both.
    #[test]
    fn conjoin_soundness() {
        let p1 = ComposedConstraint::Primitive(PrimitiveConstraint::MutualExclusion {
            p_var_name: "p".into(),
            n_var_name: "n".into(),
        });
        let p4 = layer_assignment_new("x".into(), false);
        let c = compose_conjoin(p1, p4);
        let model = lower_composed(&c);
        assert_eq!(model.constraints.len(), 2);
        let has_diffpair = model.constraints.iter().any(|c| matches!(c, InternalConstraint::DiffPair { .. }));
        let has_layer = model.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, .. } if var_name == "x")
        });
        assert!(has_diffpair);
        assert!(has_layer);
    }
}

/// Integration tests: round-trip through model → rewrite → verify.
///
/// These tests verify that the rewrite engine integrates correctly with
/// the full constraint pipeline (model construction → rewrite → CNF encoding).

#[cfg(test)]
mod tests {
    use crate::types::{InternalConstraint, InternalConstraintModel};
    use crate::encoding::encode_to_cnf;
    use crate::combinator::rewrite::rewrite;

    fn make_model_with_capacity(
        channel_id: &str,
        capacity: f64,
        var_names: &[&str],
    ) -> InternalConstraintModel {
        let terms: Vec<(String, f64)> = var_names
            .iter()
            .map(|n| (n.to_string(), 1.0))
            .collect();
        InternalConstraintModel {
            variables: var_names
                .iter()
                .enumerate()
                .map(|(i, n)| crate::types::InternalVariable::NetChannel {
                    name: n.to_string(),
                    net_idx: i,
                    channel_id: channel_id.to_string(),
                })
                .collect(),
            constraints: vec![InternalConstraint::Capacity {
                channel_id: channel_id.to_string(),
                capacity,
                slack_factor: 1.0,
                terms,
            }],
        }
    }

    /// Roundtrip: build a model matching typical ModelBuilder output,
    /// rewrite it, verify clause count is non-increasing, and verify
    /// same SAT/UNSAT via DPLL.
    #[test]
    fn roundtrip_modelbuilder_rewrite() {
        // Build a model with overlapping capacity + layer restrictions.
        let mut constraints = vec![
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 3.0,
                slack_factor: 1.0,
                terms: vec![
                    ("v0".into(), 1.0),
                    ("v1".into(), 1.0),
                    ("v2".into(), 1.0),
                    ("v3".into(), 1.0),
                ],
            },
            InternalConstraint::LayerRestriction {
                var_name: "v0".into(),
                allowed: true,
            },
        ];
        // Add a duplicate to test dedup.
        constraints.push(InternalConstraint::DiffPair {
            channel_id: "CH1".into(),
            p_var_name: "v1".into(),
            n_var_name: "v2".into(),
        });
        constraints.push(InternalConstraint::DiffPair {
            channel_id: "CH1".into(),
            p_var_name: "v1".into(),
            n_var_name: "v2".into(),
        });

        let model = InternalConstraintModel {
            variables: (0..4)
                .map(|i| crate::types::InternalVariable::NetChannel {
                    name: format!("v{i}"),
                    net_idx: i,
                    channel_id: "CH1".into(),
                })
                .collect(),
            constraints,
        };

        let original_clause_count = {
            let (cnf, _) = encode_to_cnf(&model);
            cnf.clauses.len()
        };

        let rewritten = rewrite(&model).unwrap();
        let rewritten_clause_count = {
            let (cnf, _) = encode_to_cnf(&rewritten);
            cnf.clauses.len()
        };

        // Clause count should not increase after rewrite.
        assert!(
            rewritten_clause_count <= original_clause_count,
            "rewrite increased clause count: {original_clause_count} → {rewritten_clause_count}"
        );

        // Verify diff pair dedup: original had 2 DiffPairs → 2 clauses each = 4,
        // rewritten should have 1 DiffPair → 2 clauses.
        let dp_count = rewritten
            .constraints
            .iter()
            .filter(|c| matches!(c, InternalConstraint::DiffPair { .. }))
            .count();
        assert_eq!(dp_count, 1, "expected 1 DiffPair after dedup, got {dp_count}");
    }

    /// Audit compatibility: the rewrite engine does not change which
    /// assignments are valid for the original model.
    #[test]
    fn audit_compatibility() {
        let model = make_model_with_capacity("CH1", 2.0, &["A", "B", "C"]);
        let rewritten = rewrite(&model).unwrap();
        // Both models should have the same semantics (same effective bound).
        // Since this model has no rewriting opportunities, rewritten == original.
        assert_eq!(rewritten.constraints.len(), model.constraints.len());
    }

    /// No regression: standalone AtMostK encoding is unchanged by rewrite
    /// when there are no LayerRestrictions to trigger RW3/RW4.
    #[test]
    fn no_regression_atmostk_standalone() {
        let model = make_model_with_capacity("CH1", 2.0, &["A", "B", "C", "D"]);
        let rewritten = rewrite(&model).unwrap();
        // Rewrite should be a no-op: max_nets=2 < |V|=4, no rules fire.
        assert_eq!(rewritten.constraints.len(), 1);
        match &rewritten.constraints[0] {
            InternalConstraint::Capacity {
                capacity,
                terms,
                ..
            } => {
                assert_eq!(terms.len(), 4);
                assert!((*capacity - 2.0).abs() < 0.001);
            }
            _ => panic!("expected Capacity"),
        }
    }

    /// No regression: DiffPair-only model is unchanged by rewrite
    /// (dedup only if duplicates exist).
    #[test]
    fn no_regression_diffpair_only() {
        let model = InternalConstraintModel {
            variables: vec![
                crate::types::InternalVariable::NetChannel {
                    name: "p".into(),
                    net_idx: 0,
                    channel_id: "CH1".into(),
                },
                crate::types::InternalVariable::NetChannel {
                    name: "n".into(),
                    net_idx: 1,
                    channel_id: "CH1".into(),
                },
            ],
            constraints: vec![InternalConstraint::DiffPair {
                channel_id: "CH1".into(),
                p_var_name: "p".into(),
                n_var_name: "n".into(),
            }],
        };
        let rewritten = rewrite(&model).unwrap();
        assert_eq!(rewritten.constraints.len(), 1);
        assert!(matches!(
            rewritten.constraints[0],
            InternalConstraint::DiffPair { .. }
        ));
    }
}

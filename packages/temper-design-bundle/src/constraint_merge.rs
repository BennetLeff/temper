use crate::{
    error::{DesignBundleError, diagnostic},
    model::{Constraint, ConstraintOrigin, ConstraintSet},
};
use std::collections::BTreeMap;
use temper_pcl_ir::{MergeOrder, PclConstraintKind};

/// Merge authored PCL constraints with safety-derived constraints.
///
/// Authored constraints can tighten (but never relax) safety-derived values.
/// Returns the merged constraint set or a list of validation diagnostics.
pub fn merge(
    derived: Vec<Constraint>,
    authored: Vec<Constraint>,
) -> Result<ConstraintSet, DesignBundleError> {
    let mut out = BTreeMap::<String, Constraint>::new();
    for c in derived {
        out.insert(c.subject_metric_key(), c);
    }
    for c in authored {
        let key = c.subject_metric_key();
        let Some(existing) = out.get(&key) else {
            out.insert(key, c);
            continue;
        };
        if existing.kind == c.kind {
            continue;
        }
        if existing.kind.merge_order() != c.kind.merge_order() {
            return Err(diagnostic(
                "constraint_conflict",
                format!(
                    "{} conflicts with {}: incompatible constraint kinds",
                    c.id, existing.id
                ),
                vec![existing.id.clone(), c.id.clone()],
            ));
        }
        match c.kind.merge_order() {
            MergeOrder::Minimum | MergeOrder::Maximum => {
                let authored_value =
                    scalar(&c.kind).ok_or_else(|| conflict(&existing.id, &c.id))?;
                let existing_value =
                    scalar(&existing.kind).ok_or_else(|| conflict(&existing.id, &c.id))?;
                let strengthens = match c.kind.merge_order() {
                    MergeOrder::Minimum => authored_value > existing_value,
                    MergeOrder::Maximum => authored_value < existing_value,
                    MergeOrder::Structural => false,
                };
                let weakens = match c.kind.merge_order() {
                    MergeOrder::Minimum => authored_value < existing_value,
                    MergeOrder::Maximum => authored_value > existing_value,
                    MergeOrder::Structural => false,
                };
                if weakens && existing.origin == ConstraintOrigin::AtopileDerived {
                    return Err(diagnostic(
                        "safety_weakening",
                        format!(
                            "{} weakens {} from {} to {}",
                            c.id, existing.id, existing_value, authored_value
                        ),
                        vec![existing.id.clone(), c.id.clone()],
                    ));
                }
                if strengthens {
                    out.insert(key, c);
                }
            }
            MergeOrder::Structural => {
                return Err(diagnostic(
                    "constraint_conflict",
                    format!("{} conflicts structurally with {}", c.id, existing.id),
                    vec![existing.id.clone(), c.id.clone()],
                ));
            }
        }
    }
    Ok(ConstraintSet {
        constraints: out.into_values().collect(),
    })
}
fn conflict(a: &str, b: &str) -> DesignBundleError {
    diagnostic(
        "constraint_conflict",
        "structural constraints cannot be ordered",
        vec![a.into(), b.into()],
    )
}
fn scalar(kind: &PclConstraintKind) -> Option<f64> {
    match kind {
        PclConstraintKind::Separated {
            min_distance_mm, ..
        } => Some(*min_distance_mm),
        PclConstraintKind::Adjacent {
            max_distance_mm, ..
        } => Some(*max_distance_mm),
        PclConstraintKind::LoopArea { max_area_mm2, .. } => Some(*max_area_mm2),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use temper_pcl_ir::{ConstraintOrigin, ConstraintTier, PclConstraint};
    fn c(kind: PclConstraintKind, id: &str, origin: ConstraintOrigin) -> Constraint {
        PclConstraint {
            schema_version: 1,
            id: id.into(),
            tier: ConstraintTier::Hard,
            because: None,
            origin,
            kind,
            references: vec![],
        }
    }
    #[test]
    fn minimum_rules_accept_stronger_authored_values() {
        let result = merge(
            vec![c(
                PclConstraintKind::Separated {
                    a: "A".into(),
                    b: "B".into(),
                    min_distance_mm: 6.0,
                    metric: "clearance".into(),
                },
                "floor",
                ConstraintOrigin::AtopileDerived,
            )],
            vec![c(
                PclConstraintKind::Separated {
                    a: "A".into(),
                    b: "B".into(),
                    min_distance_mm: 8.0,
                    metric: "clearance".into(),
                },
                "authored",
                ConstraintOrigin::AuthoredPcl,
            )],
        )
        .unwrap();
        assert_eq!(result.constraints.len(), 1);
    }
    #[test]
    fn maximum_rules_reject_weaker_authored_values() {
        let result = merge(
            vec![c(
                PclConstraintKind::Adjacent {
                    a: "A".into(),
                    b: "B".into(),
                    max_distance_mm: 6.0,
                    metric: "edge_to_edge".into(),
                },
                "floor",
                ConstraintOrigin::AtopileDerived,
            )],
            vec![c(
                PclConstraintKind::Adjacent {
                    a: "A".into(),
                    b: "B".into(),
                    max_distance_mm: 8.0,
                    metric: "edge_to_edge".into(),
                },
                "authored",
                ConstraintOrigin::AuthoredPcl,
            )],
        );
        assert!(result.unwrap_err().to_string().contains("safety_weakening"));
    }
}

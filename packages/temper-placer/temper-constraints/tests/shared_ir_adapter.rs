#![allow(clippy::unwrap_used)]

use temper_constraints::constraints::{Constraint, from_shared_ir};
use temper_pcl_ir::{ConstraintOrigin, ConstraintTier, PclConstraint, PclConstraintKind};

fn ir(kind: PclConstraintKind) -> PclConstraint {
    PclConstraint {
        schema_version: 1,
        id: "adapter-test".into(),
        tier: ConstraintTier::Hard,
        because: None,
        origin: ConstraintOrigin::AuthoredPcl,
        kind,
        references: vec![],
    }
}

#[test]
fn shared_adjacent_preserves_legacy_engine_semantics() {
    let adapted = from_shared_ir(&ir(PclConstraintKind::Adjacent {
        a: "Q1".into(),
        b: "Q2".into(),
        max_distance_mm: 10.0,
        metric: "edge_to_edge".into(),
    }))
    .unwrap();
    assert!(matches!(
        adapted,
        Constraint::Adjacent {
            max_distance_mm: 10.0,
            ..
        }
    ));
}

#[test]
fn unsupported_keepout_fails_explicitly() {
    let result = from_shared_ir(&ir(PclConstraintKind::Keepout {
        subject: "Q1".into(),
        bounds_mm: [0.0; 4],
        margin_mm: 1.0,
    }));
    assert!(result.unwrap_err().contains("keepout"));
}

#[test]
fn on_side_without_distance_preserves_edge_and_disables_finite_penalty() {
    let adapted = from_shared_ir(&ir(PclConstraintKind::OnSide {
        components: vec!["Q1".into()],
        side: "top".into(),
        edge: "flush".into(),
        max_distance_mm: None,
    }))
    .unwrap();
    assert!(
        matches!(adapted, Constraint::OnSide { max_distance_mm, edge: temper_constraints::constraints::EdgeType::Flush, .. } if max_distance_mm.is_infinite())
    );
}

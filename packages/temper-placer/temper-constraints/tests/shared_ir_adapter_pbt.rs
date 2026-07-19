//! Property-based tests for `from_shared_ir` — the shared-IR → loss-engine
//! adapter seam.
//!
//! This crate's E0599 (`.unwrap_or()` on the plain-`f64`
//! `Adjacent.max_distance_mm`) broke the Extended CI job for a week
//! (2026-07-11 → 2026-07-18) while `cargo test` was unrunnable locally,
//! so these tests could not exist. The compile error class is caught by
//! compiling; what proptest adds is the *semantic* class underneath it:
//! silent field mismapping, unit confusion, or a variant conversion that
//! drops/defaults a value. Every property asserts exact (bit-level for
//! `f64`) preservation across the seam, plus totality of the error paths.

use proptest::prelude::*;
use temper_constraints::constraints::{
    Axis, BoardSide, Constraint, ConstraintTier, DistanceMetric, EdgeType,
    from_shared_ir,
};
use temper_pcl_ir::{
    ConstraintOrigin, ConstraintTier as IrTier, PclConstraint, PclConstraintKind,
};

// =========================================================================
// Strategies
// =========================================================================

fn arb_name() -> impl Strategy<Value = String> {
    prop::sample::select(vec![
        "Q1".to_string(),
        "Q2".to_string(),
        "D1".to_string(),
        "C1".to_string(),
        "R1".to_string(),
        "MCU".to_string(),
        "CONN1".to_string(),
        "U8".to_string(),
    ])
}

fn arb_mm() -> impl Strategy<Value = f64> {
    // Finite, sign-inclusive: the adapter must not care about semantics,
    // only preserve the value exactly.
    prop_oneof![
        Just(0.0),
        -1.0e6..1.0e6_f64,
        Just(f64::MIN_POSITIVE),
    ]
}

fn arb_tier() -> impl Strategy<Value = IrTier> {
    prop::sample::select(vec![IrTier::Hard, IrTier::Strong, IrTier::Soft])
}

fn arb_metric() -> impl Strategy<Value = &'static str> {
    prop::sample::select(vec!["edge_to_edge", "center_to_center", "pin_to_pin"])
}

fn arb_axis() -> impl Strategy<Value = &'static str> {
    prop::sample::select(vec!["x", "y", "major", "minor"])
}

fn arb_side() -> impl Strategy<Value = &'static str> {
    prop::sample::select(vec!["top", "bottom", "left", "right"])
}

fn arb_edge() -> impl Strategy<Value = &'static str> {
    prop::sample::select(vec!["flush", "near", "overhang"])
}

fn ir(tier: IrTier, kind: PclConstraintKind) -> PclConstraint {
    PclConstraint {
        schema_version: 1,
        id: "pbt".into(),
        tier,
        because: None,
        origin: ConstraintOrigin::AuthoredPcl,
        kind,
        references: vec![],
    }
}

fn expect_tier(ir_tier: &IrTier, engine_tier: &ConstraintTier) -> bool {
    matches!(
        (ir_tier, engine_tier),
        (IrTier::Hard, ConstraintTier::Hard)
            | (IrTier::Strong, ConstraintTier::Strong)
            | (IrTier::Soft, ConstraintTier::Soft)
    )
}

fn expect_metric(s: &str, m: &DistanceMetric) -> bool {
    matches!(
        (s, m),
        ("edge_to_edge", DistanceMetric::EdgeToEdge)
            | ("center_to_center", DistanceMetric::CenterToCenter)
            | ("pin_to_pin", DistanceMetric::PinToPin)
    )
}

// =========================================================================
// Exact field preservation per variant
// =========================================================================

proptest! {
    #[test]
    fn adjacent_preserves_every_field(
        a in arb_name(),
        b in arb_name(),
        d in arb_mm(),
        metric in arb_metric(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::Adjacent {
            a: a.clone(), b: b.clone(), max_distance_mm: d, metric: metric.into(),
        })).unwrap();
        match out {
            Constraint::Adjacent { a: oa, b: ob, max_distance_mm, tier: ot, metric: om, pin_a, pin_b } => {
                prop_assert_eq!(oa, a);
                prop_assert_eq!(ob, b);
                // Bit-exact: this is the field the E0599 sat on. A silent
                // default (e.g. INFINITY) must fail here.
                prop_assert_eq!(max_distance_mm.to_bits(), d.to_bits());
                prop_assert!(expect_tier(&tier, &ot));
                prop_assert!(expect_metric(metric, &om));
                prop_assert!(pin_a.is_none() && pin_b.is_none());
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn separated_preserves_every_field(
        a in arb_name(),
        b in arb_name(),
        d in arb_mm(),
        metric in arb_metric(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::Separated {
            a: a.clone(), b: b.clone(), min_distance_mm: d, metric: metric.into(),
        })).unwrap();
        match out {
            Constraint::Separated { a: oa, b: ob, min_distance_mm, tier: ot, metric: om } => {
                prop_assert_eq!(oa, a);
                prop_assert_eq!(ob, b);
                prop_assert_eq!(min_distance_mm.to_bits(), d.to_bits());
                prop_assert!(expect_tier(&tier, &ot));
                prop_assert!(expect_metric(metric, &om));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn enclosing_preserves_every_field(
        outer in arb_name(),
        inner in prop::collection::vec(arb_name(), 0..4),
        margin in arb_mm(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::Enclosing {
            outer: outer.clone(), inner: inner.clone(), margin_mm: margin,
        })).unwrap();
        match out {
            Constraint::Enclosing { outer: oo, inner: oi, margin_mm, tier: ot } => {
                prop_assert_eq!(oo, outer);
                prop_assert_eq!(oi, inner);
                prop_assert_eq!(margin_mm.to_bits(), margin.to_bits());
                prop_assert!(expect_tier(&tier, &ot));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn aligned_preserves_every_field(
        components in prop::collection::vec(arb_name(), 1..5),
        axis in arb_axis(),
        tol in arb_mm(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::Aligned {
            components: components.clone(), axis: axis.into(), tolerance_mm: tol,
        })).unwrap();
        match out {
            Constraint::Aligned { components: oc, axis: oa, tolerance_mm, tier: ot } => {
                prop_assert_eq!(oc, components);
                prop_assert_eq!(tolerance_mm.to_bits(), tol.to_bits());
                prop_assert!(expect_tier(&tier, &ot));
                prop_assert!(matches!(
                    (axis, &oa),
                    ("x", Axis::X) | ("y", Axis::Y) | ("major", Axis::Major) | ("minor", Axis::Minor)
                ));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn onside_some_distance_is_preserved_none_becomes_infinity(
        components in prop::collection::vec(arb_name(), 1..5),
        side in arb_side(),
        edge in arb_edge(),
        d in prop::option::of(arb_mm()),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::OnSide {
            components: components.clone(), side: side.into(), edge: edge.into(),
            max_distance_mm: d,
        })).unwrap();
        match out {
            Constraint::OnSide { components: oc, side: os, edge: oe, max_distance_mm, tier: ot } => {
                prop_assert_eq!(oc, components);
                match d {
                    // Documented legacy-engine semantics: None disables the
                    // finite-distance penalty via +inf.
                    None => prop_assert!(max_distance_mm.is_infinite() && max_distance_mm > 0.0),
                    Some(v) => prop_assert_eq!(max_distance_mm.to_bits(), v.to_bits()),
                }
                prop_assert!(expect_tier(&tier, &ot));
                prop_assert!(matches!(
                    (side, &os),
                    ("top", BoardSide::Top) | ("bottom", BoardSide::Bottom)
                        | ("left", BoardSide::Left) | ("right", BoardSide::Right)
                ));
                prop_assert!(matches!(
                    (edge, &oe),
                    ("flush", EdgeType::Flush) | ("near", EdgeType::Near)
                        | ("overhang", EdgeType::Overhang)
                ));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn anchored_preserves_region_and_position(
        component in arb_name(),
        region in prop::option::of([arb_mm(), arb_mm(), arb_mm(), arb_mm()]),
        position in prop::option::of([arb_mm(), arb_mm()]),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::Anchored {
            component: component.clone(), region, position,
        })).unwrap();
        match out {
            Constraint::Anchored { component: oc, region: or, position: op, tier: ot } => {
                prop_assert_eq!(oc, component);
                match (region, or) {
                    (None, None) => {}
                    (Some(r), Some((x0, y0, x1, y1))) => {
                        prop_assert_eq!(
                            [x0.to_bits(), y0.to_bits(), x1.to_bits(), y1.to_bits()],
                            [r[0].to_bits(), r[1].to_bits(), r[2].to_bits(), r[3].to_bits()]
                        );
                    }
                    (r, o) => prop_assert!(false, "region mismatch: {r:?} vs {o:?}"),
                }
                match (position, op) {
                    (None, None) => {}
                    (Some(p), Some((x, y))) => {
                        prop_assert_eq!(
                            [x.to_bits(), y.to_bits()],
                            [p[0].to_bits(), p[1].to_bits()]
                        );
                    }
                    (p, o) => prop_assert!(false, "position mismatch: {p:?} vs {o:?}"),
                }
                prop_assert!(expect_tier(&tier, &ot));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }

    #[test]
    fn loop_area_preserves_every_field(
        loop_name in arb_name(),
        area in arb_mm(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier.clone(), PclConstraintKind::LoopArea {
            loop_name: loop_name.clone(), max_area_mm2: area,
        })).unwrap();
        match out {
            Constraint::LoopArea { loop_name: on, max_area_mm2, tier: ot } => {
                prop_assert_eq!(on, loop_name);
                prop_assert_eq!(max_area_mm2.to_bits(), area.to_bits());
                prop_assert!(expect_tier(&tier, &ot));
            }
            other => prop_assert!(false, "wrong variant: {other:?}"),
        }
    }
}

// =========================================================================
// Error-path totality: bad inputs must Err, never panic, never default
// =========================================================================

proptest! {
    #[test]
    fn keepout_always_errs_explicitly(
        subject in arb_name(),
        margin in arb_mm(),
        tier in arb_tier(),
    ) {
        let out = from_shared_ir(&ir(tier, PclConstraintKind::Keepout {
            subject, bounds_mm: [0.0, 0.0, 1.0, 1.0], margin_mm: margin,
        }));
        prop_assert!(out.is_err());
        prop_assert!(out.unwrap_err().contains("keepout"));
    }

    #[test]
    fn invalid_enum_strings_err_not_panic(
        a in arb_name(),
        b in arb_name(),
        bad in "[a-z_]{1,16}",
        tier in arb_tier(),
    ) {
        prop_assume!(!["edge_to_edge", "center_to_center", "pin_to_pin"].contains(&bad.as_str()));
        let out = from_shared_ir(&ir(tier, PclConstraintKind::Adjacent {
            a, b, max_distance_mm: 1.0, metric: bad,
        }));
        prop_assert!(out.is_err());
        prop_assert!(out.unwrap_err().contains("unsupported"));
    }
}

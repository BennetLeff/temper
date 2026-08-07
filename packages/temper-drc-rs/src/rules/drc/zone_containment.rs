// DRC check: zone containment.
//
// For each component, checks whether its center point lies inside any
// copper zone on the board. If the component's net_class is listed in a
// constraint zone's net_classes but the component's center is not inside
// any copper zone polygon, emits DRC_ZON_001 ERROR.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/zone_containment.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};
use geo::{BoundingRect, Contains};

#[derive(Default)]
pub struct ZoneContainmentCheck;

impl ZoneContainmentCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ZoneContainmentCheck {
    fn name(&self) -> &str {
        "drc_zone_containment"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check that components are inside their designated zones."
    }
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Index constraint zones by net class, once. A zone may list several
        // net_classes; each (zone, class) pair is indexed at most once (dedup
        // via ptr equality) so `matching_zones` matches the original per-zone
        // filter exactly, preserving constraint order.
        let mut zones_by_class: HashMap<&str, Vec<&crate::constraints::ZoneDefinition>> =
            HashMap::new();
        for zone in &constraints.zones {
            for nc in &zone.net_classes {
                let entry = zones_by_class.entry(nc.as_str()).or_default();
                if !entry.iter().any(|z| std::ptr::eq(*z, zone)) {
                    entry.push(zone);
                }
            }
        }

        // Bbox per board zone, once. A point outside a polygon's bounding rect
        // cannot be inside the polygon, so this is a sound pre-filter for the
        // point-in-polygon test. Uses inclusive bounds: geo's Rect::contains
        // is strict (> min, < max), but a polygon contains its boundary, so a
        // center exactly on the bbox edge must still fall through to the
        // polygon test.
        let zone_bboxes: Vec<Option<geo::Rect<f64>>> = board
            .zones
            .iter()
            .map(|z| z.polygon.bounding_rect())
            .collect();

        for comp in board.all_components() {
            let matching_zones: &[&crate::constraints::ZoneDefinition] = zones_by_class
                .get(comp.net_class.0.as_str())
                .map(|v| v.as_slice())
                .unwrap_or(&[]);

            if matching_zones.is_empty() {
                continue; // No zone requires this component
            }

            // Check if component center is inside any copper zone polygon on the board
            let center = comp.center;
            let is_inside_any_zone = board.zones.iter().enumerate().any(|(idx, z)| {
                let bbox_ok = match zone_bboxes[idx] {
                    Some(bbox) => {
                        center.x() >= bbox.min().x
                            && center.x() <= bbox.max().x
                            && center.y() >= bbox.min().y
                            && center.y() <= bbox.max().y
                    }
                    // Empty polygon: bounding_rect() is None, and the polygon
                    // contains nothing — fall through to the exact test.
                    None => true,
                };
                bbox_ok && z.polygon.contains(&center)
            });

            if !is_inside_any_zone {
                let zone_names: Vec<String> =
                    matching_zones.iter().map(|z| z.name.clone()).collect();
                violations.push(violation(
                    Severity::Error,
                    "DRC_ZON_001",
                    &format!(
                        "Zone containment violation: {} (net class {}) is not inside any copper zone. Expected zones: {:?}",
                        comp.refdes, comp.net_class, zone_names,
                    ),
                    DrcCategory::Drc,
                    "drc_zone_containment",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(center.x()),
                        y: Some(center.y()),
                        layer: None,
                    }),
                    serde_json::json!({
                        "expected_zones": zone_names,
                        "net_class": comp.net_class.0,
                    }),
                ));
            }
        }
        violations
    }
}

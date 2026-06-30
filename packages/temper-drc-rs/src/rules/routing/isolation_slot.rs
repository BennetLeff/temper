// Routing check: isolation slot — verify slot width >= 2 mm.
//
// For each ZoneDefinition whose name contains "slot" or "isolation",
// locate the corresponding CopperZone polygon and verify the minimum
// slot width (the smaller bounding-box dimension) is >= 2 mm.  If a
// matching CopperZone exists but its polygon does not meet the width
// requirement, emit a WARNING.  If the ZoneDefinition has no matching
// CopperZone polygon at all, emit an INFO advisory.
//
// Degenerate: 0 isolation/slot zones → empty vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Location, Severity, Violation};
use geo::BoundingRect;

/// Minimum required slot width in mm.
const MIN_SLOT_WIDTH_MM: f64 = 2.0;

/// Keywords that identify an isolation / slot zone definition.
const SLOT_KEYWORDS: &[&str] = &["slot", "isolation"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Returns true if the zone name suggests it is an isolation slot.
fn is_isolation_slot(name: &str) -> bool {
    let lc = name.to_lowercase();
    SLOT_KEYWORDS.iter().any(|k| lc.contains(k))
}

/// Compute a rough minimum width for a polygon using its bounding box.
fn polygon_min_width(poly: &geo::Polygon<f64>) -> f64 {
    let bbox = poly.bounding_rect().unwrap_or_else(|| {
        // Fallback: compute bbox from exterior coordinates
        let exterior = poly.exterior();
        if exterior.0.is_empty() {
            return geo::Rect::new(geo::coord! { x: 0.0, y: 0.0 }, geo::coord! { x: 0.0, y: 0.0 });
        }
        let mut min_x = f64::MAX;
        let mut max_x = f64::MIN;
        let mut min_y = f64::MAX;
        let mut max_y = f64::MIN;
        for coord in &exterior.0 {
            if coord.x < min_x {
                min_x = coord.x;
            }
            if coord.x > max_x {
                max_x = coord.x;
            }
            if coord.y < min_y {
                min_y = coord.y;
            }
            if coord.y > max_y {
                max_y = coord.y;
            }
        }
        geo::Rect::new(geo::coord! { x: min_x, y: min_y }, geo::coord! { x: max_x, y: max_y })
    });
    let w = bbox.max().x - bbox.min().x;
    let h = bbox.max().y - bbox.min().y;
    w.min(h)
}

/// Try to find a CopperZone whose net (or parent zone name) matches the
/// given ZoneDefinition name.  Returns the polygon if found.
fn matching_copper_polygon<'a>(
    zone_name: &str,
    board_zones: &'a [crate::board::CopperZone],
) -> Option<&'a geo::Polygon<f64>> {
    let lc_zone = zone_name.to_lowercase();
    for z in board_zones {
        let lc_net = z.net.to_lowercase();
        // Match if the copper zone's net name shares the zone name,
        // or if the zone name appears within the copper zone net.
        if lc_net.contains(&lc_zone) || lc_zone.contains(&lc_net) {
            return Some(&z.polygon);
        }
    }
    None
}

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

pub struct IsolationSlotCheck;

impl IsolationSlotCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for IsolationSlotCheck {
    fn name(&self) -> &str {
        "routing_isolation_slot"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Verify isolation slot (zone name contains 'slot' or 'isolation') has available geometry data and minimum bounds."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // ---- 1. Find isolation/slot zone definitions -----------------------------
        let slot_zones: Vec<&crate::constraints::ZoneDefinition> = constraints
            .zones
            .iter()
            .filter(|z| is_isolation_slot(&z.name))
            .collect();

        if slot_zones.is_empty() {
            return violations;
        }

        // ---- 2. Check each slot zone ----------------------------------------------
        for zone_def in &slot_zones {
            match matching_copper_polygon(&zone_def.name, &board.zones) {
                Some(poly) => {
                    let slot_width = polygon_min_width(poly);
                    if slot_width < MIN_SLOT_WIDTH_MM {
                        let bbox = poly.bounding_rect();
                        let (cx, cy) = bbox
                            .map(|r: geo::Rect<f64>| {
                                (
                                    (r.min().x + r.max().x) / 2.0,
                                    (r.min().y + r.max().y) / 2.0,
                                )
                            })
                            .unwrap_or((0.0, 0.0));

                        violations.push(violation(
                            Severity::Warning,
                            "SAF_SLT_002",
                            &format!(
                                "Isolation slot '{}' width {:.2} mm is below minimum {:.2} mm",
                                zone_def.name, slot_width, MIN_SLOT_WIDTH_MM,
                            ),
                            DrcCategory::Safety,
                            "routing_isolation_slot",
                            vec![zone_def.name.clone()],
                            Some(Location {
                                x: Some(cx),
                                y: Some(cy),
                                layer: None,
                            }),
                            serde_json::json!({
                                "slot_name": zone_def.name,
                                "slot_width_mm": slot_width,
                                "required_width_mm": MIN_SLOT_WIDTH_MM,
                            }),
                        ));
                    }
                }
                None => {
                    // Zone definition exists but no copper zone polygon found
                    violations.push(violation(
                        Severity::Info,
                        "SAF_SLT_001",
                        &format!(
                            "Isolation slot '{}' slot geometry not available: zone is defined in \
                             constraints but has no copper zone polygon on the board",
                            zone_def.name,
                        ),
                        DrcCategory::Safety,
                        "routing_isolation_slot",
                        vec![zone_def.name.clone()],
                        Some(Location {
                            x: None,
                            y: None,
                            layer: None,
                        }),
                        serde_json::json!({
                            "slot_name": zone_def.name,
                            "note": "no copper zone polygon found",
                        }),
                    ));
                }
            }
        }

        violations
    }
}

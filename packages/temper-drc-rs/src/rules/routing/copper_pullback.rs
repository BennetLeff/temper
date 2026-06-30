// Routing check: copper pullback from board edge.
//
// For each copper zone, verifies that the zone polygon is fully contained
// within the board bounds minus an inset of `board.margin_mm` (default 0.5 mm).
// If the zone extends outside the allowed inset region, an ERROR is emitted.
//
// Degenerate case: 0 zones → empty violations vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

use geo::{Centroid, Coord, Point, Rect};

/// Default board-edge margin (mm) used when `board.margin_mm` is zero or
/// unset.
const DEFAULT_MARGIN_MM: f64 = 0.5;

pub struct CopperPullbackCheck;

impl CopperPullbackCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for CopperPullbackCheck {
    fn name(&self) -> &str {
        "routing_copper_pullback"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }

    fn description(&self) -> &str {
        "Ensure copper zones respect board-edge pullback margin."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Degenerate: no zones.
        if board.zones.is_empty() {
            return violations;
        }

        let margin = if board.margin_mm > 0.0 {
            board.margin_mm
        } else {
            DEFAULT_MARGIN_MM
        };

        // Build the inset board rectangle: {margin, margin} to
        // {width - margin, height - margin}.
        let inner_rect = Rect::new(
            Coord {
                x: margin,
                y: margin,
            },
            Coord {
                x: board.width_mm - margin,
                y: board.height_mm - margin,
            },
        );

        for zone in &board.zones {
            // Check if the zone polygon is fully inside the inset rectangle.
            // We approximate by testing that every exterior point of the zone
            // polygon falls within the inner_rect.
            let exterior = &zone.polygon.exterior();
            let mut outside = false;

            for pt in exterior.points() {
                if pt.x() < inner_rect.min().x
                    || pt.x() > inner_rect.max().x
                    || pt.y() < inner_rect.min().y
                    || pt.y() > inner_rect.max().y
                {
                    outside = true;
                    break;
                }
            }

            if outside {
                // Compute zone centroid for the location.
                let centroid = zone.polygon.centroid().unwrap_or(Point::new(0.0, 0.0));
                let (cx, cy) = (centroid.x(), centroid.y());

                violations.push(violation(
                    Severity::Error,
                    "ROUTING_PULLBACK_001",
                    &format!(
                        "Copper zone '{}' on {} extends beyond board-edge pullback margin ({:.2} mm).",
                        zone.net, zone.layer, margin,
                    ),
                    DrcCategory::Drc,
                    "routing_copper_pullback",
                    vec![zone.net.clone()],
                    Some(crate::rules::Location {
                        x: Some(cx),
                        y: Some(cy),
                        layer: Some(zone.layer.clone()),
                    }),
                    serde_json::json!({
                        "margin_mm": margin,
                        "zone_net": zone.net,
                        "zone_layer": zone.layer,
                    }),
                ));
            }
        }

        violations
    }
}

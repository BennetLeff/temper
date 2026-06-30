// Routing check: split-plane crossing — fast digital nets crossing ground
// domain boundaries.
//
// Identify fast digital nets (SPI, I2C, USB in net name).  For each such
// net's traces, check whether any segment crosses a ground-domain boundary
// i.e. the segment's midpoint lies inside a copper zone belonging to one
// ground net while another segment of the same trace lies in a zone of a
// different ground net.  Crossing violations emit WARNING.
//
// Degenerate: 0 fast digital nets → empty vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use geo::{Intersects, Point};

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Location, Severity, Violation};

/// Markers that identify a fast digital net.
const FAST_NET_MARKERS: [&str; 6] = ["SPI", "I2C", "USB", "CLK", "MISO", "MOSI"];

/// Keywords that identify a ground / return net in a copper zone.
const GND_KEYWORDS: [&str; 3] = ["GND", "GROUND", "RETURN"];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Returns true if the net name indicates a fast digital bus.
fn is_fast_digital(net: &str) -> bool {
    let upper = net.to_uppercase();
    FAST_NET_MARKERS.iter().any(|k| upper.contains(k))
}

/// Returns true if the net name indicates a ground / return net.
fn is_ground_net(net: &str) -> bool {
    let upper = net.to_uppercase();
    GND_KEYWORDS.iter().any(|k| upper.contains(k))
}

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

pub struct SplitPlaneCrossingCheck;

impl SplitPlaneCrossingCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for SplitPlaneCrossingCheck {
    fn name(&self) -> &str {
        "routing_split_plane_crossing"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Detect fast digital traces (SPI, I2C, USB, CLK, MISO, MOSI) that cross ground-domain boundaries using constraint-defined zones."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // ---- 1. Identify fast digital nets ----------------------------------------
        let fast_nets: Vec<&str> = board
            .traces
            .iter()
            .filter(|t| is_fast_digital(&t.net))
            .map(|t| t.net.0.as_str())
            .collect();

        if fast_nets.is_empty() {
            return violations;
        }

        // ---- 2. Build ground-domain zone list from constraints ---------------------
        //     Use constraints.zones to find ground-related zone definitions, then
        //     match them against board.zones to get polygons.
        //     Fall back to keyword check on board.zones if constraints.zones is empty.
        let ground_polys: Vec<(&str, &geo::Polygon<f64>)> = if constraints.zones.is_empty() {
            // Fallback: find ground zones via keyword heuristic on board zones
            board
                .zones
                .iter()
                .filter(|z| is_ground_net(&z.net))
                .map(|z| (z.net.0.as_str(), &z.polygon))
                .collect()
        } else {
            // Identify constraint-defined zones that are ground-related
            let ground_zone_names: Vec<&str> = constraints
                .zones
                .iter()
                .filter(|zd| is_ground_net(&zd.name) || zd.net_classes.iter().any(|nc| is_ground_net(nc)))
                .map(|zd| zd.name.as_str())
                .collect();

            // Match constraint zone names to copper zone nets
            board
                .zones
                .iter()
                .filter(|z| {
                    let lc_net = z.net.to_lowercase();
                    ground_zone_names.iter().any(|gzn| lc_net.contains(&gzn.to_lowercase()))
                })
                .map(|z| (z.net.0.as_str(), &z.polygon))
                .collect()
        };

        if ground_polys.is_empty() {
            return violations;
        }

        // ---- 3. Check each trace belonging to a fast net -------------------------
        for trace in &board.traces {
            if !fast_nets.contains(&trace.net.0.as_str()) {
                continue;
            }

            // Collect distinct ground-domain names whose polygons contain
            // segments of this trace.
            let mut domains_hit: Vec<String> = Vec::new();

            for seg in &trace.segments {
                let mid = Point::new(
                    (seg.start.x + seg.end.x) / 2.0,
                    (seg.start.y + seg.end.y) / 2.0,
                );
                for (gnd_name, poly) in &ground_polys {
                    if poly.intersects(&mid) {
                        let name_str = gnd_name.to_string();
                        if !domains_hit.contains(&name_str) {
                            domains_hit.push(name_str);
                        }
                    }
                }
            }

            if domains_hit.len() > 1 {
                let mid = if let Some(seg) = trace.segments.first() {
                    Point::new(
                        (seg.start.x + seg.end.x) / 2.0,
                        (seg.start.y + seg.end.y) / 2.0,
                    )
                } else {
                    Point::new(0.0, 0.0)
                };

                violations.push(violation(
                    Severity::Warning,
                    "EMC_SPC_001",
                    &format!(
                        "Fast digital net {} crosses ground domain boundaries on {}: {}",
                        trace.net,
                        trace.layer,
                        domains_hit.join(" ↔ "),
                    ),
                    DrcCategory::Emc,
                    "routing_split_plane_crossing",
                    vec![trace.net.0.clone()],
                    Some(Location {
                        x: Some(mid.x()),
                        y: Some(mid.y()),
                        layer: Some(trace.layer.clone()),
                    }),
                    serde_json::json!({
                        "crossed_domains": domains_hit,
                        "ground_domains": domains_hit,
                        "trace_net": trace.net,
                        "layer": trace.layer,
                    }),
                ));
            }
        }

        violations
    }
}

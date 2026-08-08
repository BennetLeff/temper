// Safety check: SELV/HV isolation barrier crossing — copper geometry.
//
// For each `IsolationBarrier` in constraints, builds a `geo::Line` from
// `(barrier.x_mm, y_span[0])` to `(barrier.x_mm, y_span[1])`, then checks
// every `TraceSegment` and `CopperZone` (i.e. every zone/pour polygon —
// this is the one check in the engine that inspects copper-fill geometry,
// not just component/pad positions) on a layer the barrier covers for:
//
//   1. Direct intersection with the barrier line ("crossing" — always
//      CRITICAL, `ROUTING_ISO_001`/`ROUTING_ISO_002`).
//   2. Euclidean edge distance below `barrier.clearance_mm`, when that
//      field is set above 0.0 ("clearance violation" — a pour that comes
//      close without literally crossing still bridges the barrier's
//      required creepage margin; CRITICAL, `ROUTING_ISO_003`/`ROUTING_ISO_004`).
//
// Degenerate case: 0 barriers → empty violations vec (this is also the
// state of every real run today — see `constraints::IsolationBarrier`'s
// doc comment: nothing in `temper_constraints.yaml` populates
// `isolation_barriers`, so this check is a no-op against the real
// project config until a barrier is defined and supplied).
//
// Layer scope ("which layer(s)?"): `barrier.layers` is a comma-separated
// KiCad layer list or `"all"` (the default). A pour on an inner layer
// (`In1.Cu`/`In2.Cu`) crossing the barrier is exactly as dangerous as one
// on an outer layer, so `"all"` — checking every layer — is the safe
// default; a barrier is only narrowed to specific layers when the caller
// has a reason to (e.g. a barrier that is physically only relevant on
// certain layers of a given stackup).
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md.
// Hardened (clearance + layer scoping + zone-polygon test coverage):
// SELV/HV pour-crossing-barrier DRC spike, 2026-08-08.

use crate::board::BoardState;
use crate::constraints::{ConstraintSet, IsolationBarrier};
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

use geo::{Centroid, EuclideanDistance, Intersects, Line, Point};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Returns true if `layer` is within the barrier's declared layer scope.
/// `"all"` (case-insensitive) or an empty string covers every layer.
fn barrier_covers_layer(barrier_layers: &str, layer: &str) -> bool {
    let trimmed = barrier_layers.trim();
    if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("all") {
        return true;
    }
    trimmed
        .split(',')
        .any(|candidate| candidate.trim().eq_ignore_ascii_case(layer))
}

/// Minimum Euclidean distance from a polygon's exterior boundary to a
/// line, computed edge-to-edge (mirrors `Component::edge_distance_to`'s
/// approach in `board.rs`, per this crate's K5 convention of using only
/// `geo::algorithm::euclidean_distance`). Returns 0.0 for any polygon
/// that already intersects the line, since the polygon boundary itself
/// then has 0 distance to it — callers should check `intersects` first
/// and treat that as a distinct (crossing) violation.
fn polygon_edge_distance_to_line(polygon: &geo::Polygon<f64>, line: &Line<f64>) -> f64 {
    polygon
        .exterior()
        .lines()
        .map(|edge| edge.euclidean_distance(line))
        .fold(f64::MAX, f64::min)
}

/// Check all trace segments on barrier-covered layers for intersection
/// with, or insufficient clearance to, an isolation barrier line.
fn check_trace_barrier_intersections(
    barrier_line: &Line<f64>,
    barrier: &IsolationBarrier,
    board: &BoardState,
) -> Vec<Violation> {
    let mut violations = Vec::new();
    for trace in &board.traces {
        if !barrier_covers_layer(&barrier.layers, &trace.layer) {
            continue;
        }
        for segment in &trace.segments {
            let mid = geo::Point::new(
                (segment.start.x + segment.end.x) / 2.0,
                (segment.start.y + segment.end.y) / 2.0,
            );
            if segment.intersects(barrier_line) {
                violations.push(violation(
                    Severity::Critical,
                    "ROUTING_ISO_001",
                    &format!(
                        "Trace '{}' crosses isolation barrier '{}' on {}.",
                        trace.net, barrier.name, trace.layer,
                    ),
                    DrcCategory::Safety,
                    "routing_isolation_barrier",
                    vec![trace.net.0.clone(), barrier.name.clone()],
                    Some(crate::rules::Location {
                        x: Some(mid.x()),
                        y: Some(mid.y()),
                        layer: Some(trace.layer.clone()),
                    }),
                    serde_json::json!({
                        "barrier": barrier.name,
                        "barrier_x_mm": barrier.x_mm,
                        "barrier_y_span": barrier.y_span,
                        "trace_net": trace.net,
                        "violation_kind": "crossing",
                    }),
                ));
            } else if barrier.clearance_mm > 0.0 {
                let dist = segment.euclidean_distance(barrier_line);
                if dist < barrier.clearance_mm {
                    violations.push(violation(
                        Severity::Critical,
                        "ROUTING_ISO_003",
                        &format!(
                            "Trace '{}' on {} is {:.3}mm from isolation barrier '{}', \
                             below the required {:.3}mm clearance.",
                            trace.net, trace.layer, dist, barrier.name, barrier.clearance_mm,
                        ),
                        DrcCategory::Safety,
                        "routing_isolation_barrier",
                        vec![trace.net.0.clone(), barrier.name.clone()],
                        Some(crate::rules::Location {
                            x: Some(mid.x()),
                            y: Some(mid.y()),
                            layer: Some(trace.layer.clone()),
                        }),
                        serde_json::json!({
                            "barrier": barrier.name,
                            "barrier_x_mm": barrier.x_mm,
                            "barrier_y_span": barrier.y_span,
                            "trace_net": trace.net,
                            "violation_kind": "clearance",
                            "distance_mm": dist,
                            "required_clearance_mm": barrier.clearance_mm,
                        }),
                    ));
                }
            }
        }
    }
    violations
}

/// Check all copper zones (pours) on barrier-covered layers for
/// intersection with, or insufficient clearance to, an isolation barrier
/// line. This is the load-bearing half of the check: zone/pour polygons
/// were previously invisible to every rule in this engine (see this
/// file's module doc comment and
/// `docs/evidence/2026-08-08-power-plane-spec-readiness.md` §3b).
fn check_zone_barrier_intersections(
    barrier_line: &Line<f64>,
    barrier: &IsolationBarrier,
    board: &BoardState,
) -> Vec<Violation> {
    let mut violations = Vec::new();
    for zone in &board.zones {
        if !barrier_covers_layer(&barrier.layers, &zone.layer) {
            continue;
        }
        let centroid = zone.polygon.centroid().unwrap_or(Point::new(0.0, 0.0));
        if zone.polygon.intersects(barrier_line) {
            violations.push(violation(
                Severity::Critical,
                "ROUTING_ISO_002",
                &format!(
                    "Copper zone '{}' on {} crosses isolation barrier '{}'.",
                    zone.net, zone.layer, barrier.name,
                ),
                DrcCategory::Safety,
                "routing_isolation_barrier",
                vec![zone.net.0.clone(), barrier.name.clone()],
                Some(crate::rules::Location {
                    x: Some(centroid.x()),
                    y: Some(centroid.y()),
                    layer: Some(zone.layer.clone()),
                }),
                serde_json::json!({
                    "barrier": barrier.name,
                    "barrier_x_mm": barrier.x_mm,
                    "barrier_y_span": barrier.y_span,
                    "zone_net": zone.net,
                    "violation_kind": "crossing",
                }),
            ));
        } else if barrier.clearance_mm > 0.0 {
            let dist = polygon_edge_distance_to_line(&zone.polygon, barrier_line);
            if dist < barrier.clearance_mm {
                violations.push(violation(
                    Severity::Critical,
                    "ROUTING_ISO_004",
                    &format!(
                        "Copper zone '{}' on {} is {:.3}mm from isolation barrier '{}', \
                         below the required {:.3}mm clearance.",
                        zone.net, zone.layer, dist, barrier.name, barrier.clearance_mm,
                    ),
                    DrcCategory::Safety,
                    "routing_isolation_barrier",
                    vec![zone.net.0.clone(), barrier.name.clone()],
                    Some(crate::rules::Location {
                        x: Some(centroid.x()),
                        y: Some(centroid.y()),
                        layer: Some(zone.layer.clone()),
                    }),
                    serde_json::json!({
                        "barrier": barrier.name,
                        "barrier_x_mm": barrier.x_mm,
                        "barrier_y_span": barrier.y_span,
                        "zone_net": zone.net,
                        "violation_kind": "clearance",
                        "distance_mm": dist,
                        "required_clearance_mm": barrier.clearance_mm,
                    }),
                ));
            }
        }
    }
    violations
}

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

#[derive(Default)]
pub struct IsolationBarrierCheck;

impl IsolationBarrierCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for IsolationBarrierCheck {
    fn name(&self) -> &str {
        "routing_isolation_barrier"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Verify no copper (trace or zone/pour polygon) crosses or violates \
         clearance to a SELV/HV isolation barrier — critical for safety isolation."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        if constraints.isolation_barriers.is_empty() {
            return violations;
        }

        for barrier in &constraints.isolation_barriers {
            let barrier_line = Line::new(
                geo::Coord {
                    x: barrier.x_mm,
                    y: barrier.y_span[0],
                },
                geo::Coord {
                    x: barrier.x_mm,
                    y: barrier.y_span[1],
                },
            );

            violations.extend(check_trace_barrier_intersections(&barrier_line, barrier, board));
            violations.extend(check_zone_barrier_intersections(&barrier_line, barrier, board));
        }

        violations
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::{LineString, Point, Polygon};
    use std::collections::HashMap;

    /// A 152mm x 234mm board (real board's `Edge.Cuts` extent, per
    /// `docs/evidence/2026-08-08-power-plane-spec-readiness.md`) with the
    /// given zones/traces and nothing else. Other `BoardState` fields are
    /// empty — this check only reads `traces` and `zones`.
    fn make_board(zones: Vec<CopperZone>, traces: Vec<TraceSegment>) -> BoardState {
        BoardState {
            width_mm: 152.0,
            height_mm: 234.0,
            margin_mm: 0.0,
            electrical_components: vec![],
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: HashMap::new(),
            traces,
            vias: vec![],
            zones,
        }
    }

    fn rect_zone(net: &str, layer: &str, x0: f64, y0: f64, x1: f64, y1: f64) -> CopperZone {
        CopperZone {
            net: NetName(net.into()),
            layer: layer.into(),
            polygon: Polygon::new(
                LineString::from(vec![(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]),
                vec![],
            ),
        }
    }

    /// A single-segment trace from (x0,y0) to (x1,y1).
    fn straight_trace(net: &str, layer: &str, x0: f64, y0: f64, x1: f64, y1: f64) -> TraceSegment {
        TraceSegment {
            net: NetName(net.into()),
            layer: layer.into(),
            width: 0.25,
            segments: vec![Line::new(
                geo::Coord { x: x0, y: y0 },
                geo::Coord { x: x1, y: y1 },
            )],
        }
    }

    /// A barrier matching the real board's dimensions and the geometry
    /// used by the (unmerged) `MAINS_SELV_ISOLATION_BARRIER` keepout on
    /// `origin/safety/mains-selv-isolation-barrier`: a vertical line at
    /// x=94.703mm spanning the full board height, all 4 copper layers,
    /// with the REQ-SAFE-01 8.0mm REINFORCED creepage clearance.
    fn real_board_shaped_barrier(clearance_mm: f64) -> IsolationBarrier {
        IsolationBarrier {
            name: "MAINS_SELV_ISOLATION_BARRIER".into(),
            x_mm: 94.703,
            y_span: [0.0, 274.0],
            layers: "all".into(),
            clearance_mm,
        }
    }

    fn constraints_with_barrier(barrier: IsolationBarrier) -> ConstraintSet {
        ConstraintSet {
            isolation_barriers: vec![barrier],
            ..Default::default()
        }
    }

    // -- Degenerate cases -----------------------------------------------

    #[cfg_attr(test, test)]
    fn no_barriers_no_violations() {
        let zone = rect_zone("GND", "F.Cu", 0.0, 0.0, 152.0, 234.0); // spans the whole board
        let board = make_board(vec![zone], vec![]);
        let constraints = ConstraintSet::default(); // isolation_barriers: []
        let violations = IsolationBarrierCheck::new().check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "0 barriers must be a no-op even against a zone spanning the whole board"
        );
    }

    #[cfg_attr(test, test)]
    fn empty_board_no_violations() {
        let board = make_board(vec![], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));
        let violations = IsolationBarrierCheck::new().check(&board, &constraints);
        assert!(violations.is_empty(), "board with no copper must be clean");
    }

    // -- FAIL: a pour that genuinely crosses the barrier -----------------

    #[cfg_attr(test, test)]
    fn zone_pour_crossing_barrier_is_rejected() {
        // A GND pour on the SELV side (x < 94.703) that extends past the
        // barrier line onto the HV side (x > 94.703) — the exact shape of
        // defect this check exists to catch.
        let crossing_zone = rect_zone("gnd", "F.Cu", 60.0, 50.0, 110.0, 90.0);
        let board = make_board(vec![crossing_zone], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert_eq!(
            violations.len(),
            1,
            "a pour that crosses the barrier line must be rejected, got: {:?}",
            violations
        );
        assert_eq!(violations[0].code, "ROUTING_ISO_002");
        assert_eq!(violations[0].severity, Severity::Critical);
        assert_eq!(violations[0].category, DrcCategory::Safety);
    }

    // -- PASS: a pour that respects the barrier with margin --------------

    #[cfg_attr(test, test)]
    fn zone_pour_respecting_barrier_with_margin_is_accepted() {
        // Entirely on the SELV side (x in [10, 60]), 34.7mm clear of the
        // barrier at x=94.703 — well past the 8.0mm REINFORCED clearance.
        let compliant_zone = rect_zone("gnd", "F.Cu", 10.0, 50.0, 60.0, 90.0);
        let board = make_board(vec![compliant_zone], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert!(
            violations.is_empty(),
            "a pour that clears the barrier by a wide margin must be accepted, got: {:?}",
            violations
        );
    }

    // -- Clearance (near-miss) semantics ---------------------------------

    #[cfg_attr(test, test)]
    fn zone_pour_within_clearance_but_not_crossing_is_rejected() {
        // Nearest edge at x=92.0, i.e. 2.703mm from the barrier at
        // x=94.703 — inside the required 8.0mm clearance, but the polygon
        // itself never crosses x=94.703, so this only fires via the
        // clearance path (ROUTING_ISO_004), not the crossing path.
        let near_miss_zone = rect_zone("gnd", "F.Cu", 40.0, 50.0, 92.0, 90.0);
        let board = make_board(vec![near_miss_zone], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert_eq!(
            violations.len(),
            1,
            "a pour inside the clearance margin (but not crossing) must be \
             rejected, got: {:?}",
            violations
        );
        assert_eq!(violations[0].code, "ROUTING_ISO_004");
        let dist = violations[0].details["distance_mm"].as_f64().unwrap();
        assert!(
            (dist - 2.703).abs() < 1e-9,
            "reported distance should be the true edge distance, got {dist}"
        );
    }

    #[cfg_attr(test, test)]
    fn zero_clearance_barrier_only_flags_actual_crossings() {
        // Same near-miss geometry as above, but clearance_mm left at the
        // default 0.0 — pure crossing-only semantics (backward
        // compatible with the pre-hardening behavior).
        let near_miss_zone = rect_zone("gnd", "F.Cu", 40.0, 50.0, 92.0, 90.0);
        let board = make_board(vec![near_miss_zone], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(0.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert!(
            violations.is_empty(),
            "clearance_mm=0.0 must not flag a near-miss that doesn't cross, got: {:?}",
            violations
        );
    }

    // -- Trace (not just zone) crossings ----------------------------------

    #[cfg_attr(test, test)]
    fn trace_crossing_barrier_is_rejected() {
        let crossing_trace = straight_trace("gnd", "F.Cu", 80.0, 100.0, 110.0, 100.0);
        let board = make_board(vec![], vec![crossing_trace]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert_eq!(violations.len(), 1, "got: {:?}", violations);
        assert_eq!(violations[0].code, "ROUTING_ISO_001");
    }

    // -- Layer scope: inner layers are just as dangerous ------------------

    #[cfg_attr(test, test)]
    fn barrier_spanning_all_layers_catches_inner_layer_crossing() {
        // In1.Cu — an inner layer. The real board's In1.Cu/In2.Cu are
        // currently empty (docs/evidence/2026-08-08-power-plane-spec-readiness.md
        // §0), but a future power-plane generator could pour there, and a
        // barrier scoped to "all" (the default) must still catch it.
        let inner_crossing_zone = rect_zone("gnd", "In1.Cu", 60.0, 50.0, 110.0, 90.0);
        let board = make_board(vec![inner_crossing_zone], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert_eq!(
            violations.len(),
            1,
            "an inner-layer (In1.Cu) crossing must be caught exactly like an \
             outer-layer one, got: {:?}",
            violations
        );
        assert_eq!(violations[0].location.as_ref().unwrap().layer.as_deref(), Some("In1.Cu"));
    }

    #[cfg_attr(test, test)]
    fn barrier_scoped_to_outer_layers_ignores_inner_layer_crossing() {
        // Demonstrates the layer-scoping mechanism itself: a barrier
        // explicitly narrowed to F.Cu/B.Cu does not fire on an In1.Cu
        // crossing. (Not the recommended default for a real barrier —
        // see the module doc comment — but the mechanism must work if a
        // caller has a documented reason to scope it.)
        let mut barrier = real_board_shaped_barrier(8.0);
        barrier.layers = "F.Cu,B.Cu".into();
        let inner_crossing_zone = rect_zone("gnd", "In1.Cu", 60.0, 50.0, 110.0, 90.0);
        let board = make_board(vec![inner_crossing_zone], vec![]);
        let constraints = constraints_with_barrier(barrier);

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert!(
            violations.is_empty(),
            "a barrier scoped away from In1.Cu must not fire on an In1.Cu-only \
             crossing, got: {:?}",
            violations
        );
    }

    // -- Historical defect analog: commit 6976ef44 -------------------------
    //
    // commit 6976ef443e819db3466c3d8d2712cce43f6c15f9 removed a *net-topology*
    // defect (`power_return ~ gnd` in `elec/src/main.ato`), which galvanically
    // joined the SELV control-domain ground to the HV-side doubler midpoint,
    // shorting the AuxSupply IRM-10-15's certified 4.2kVAC isolation barrier.
    // That defect never took the form of placed PCB copper — it was a
    // schematic net join, and the real board's inner layers were and remain
    // empty (per docs/evidence/2026-08-08-power-plane-spec-readiness.md §0),
    // so there is no literal artifact to replay through this geometric check.
    //
    // What *is* in scope: the geometric construction a net-topology short
    // like that would produce if it were realized as copper — a single pour
    // (or trace) on a ground/return net physically bridging both sides of
    // the barrier, the same shape "gnd ~ power_return" would draw if someone
    // routed it directly instead of joining it in the netlist. This test
    // constructs that geometric analog and confirms the detector rejects it.
    #[cfg_attr(test, test)]
    fn catches_geometric_analog_of_star_point_ground_bridge_removed_by_6976ef44() {
        // A single GND-net pour spanning from deep in the SELV region
        // (x=20, near the board's real left edge per the Edge.Cuts extent)
        // across the barrier into the HV region (x=140) — the copper-pour
        // shape of "SELV ground galvanically joined to the HV-side return".
        let star_point_bridge_pour = rect_zone("gnd", "In2.Cu", 20.0, 120.0, 140.0, 160.0);
        let board = make_board(vec![star_point_bridge_pour], vec![]);
        let constraints = constraints_with_barrier(real_board_shaped_barrier(8.0));

        let violations = IsolationBarrierCheck::new().check(&board, &constraints);

        assert_eq!(
            violations.len(),
            1,
            "a GND pour bridging the barrier (the geometric analog of the \
             6976ef44 star-point join) must be rejected, got: {:?}",
            violations
        );
        assert_eq!(violations[0].code, "ROUTING_ISO_002");
        assert_eq!(violations[0].severity, Severity::Critical);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::routing::isolation_barrier::tests::no_barriers_no_violations", no_barriers_no_violations),
        ("rules::routing::isolation_barrier::tests::empty_board_no_violations", empty_board_no_violations),
        ("rules::routing::isolation_barrier::tests::zone_pour_crossing_barrier_is_rejected", zone_pour_crossing_barrier_is_rejected),
        ("rules::routing::isolation_barrier::tests::zone_pour_respecting_barrier_with_margin_is_accepted", zone_pour_respecting_barrier_with_margin_is_accepted),
        ("rules::routing::isolation_barrier::tests::zone_pour_within_clearance_but_not_crossing_is_rejected", zone_pour_within_clearance_but_not_crossing_is_rejected),
        ("rules::routing::isolation_barrier::tests::zero_clearance_barrier_only_flags_actual_crossings", zero_clearance_barrier_only_flags_actual_crossings),
        ("rules::routing::isolation_barrier::tests::trace_crossing_barrier_is_rejected", trace_crossing_barrier_is_rejected),
        ("rules::routing::isolation_barrier::tests::barrier_spanning_all_layers_catches_inner_layer_crossing", barrier_spanning_all_layers_catches_inner_layer_crossing),
        ("rules::routing::isolation_barrier::tests::barrier_scoped_to_outer_layers_ignores_inner_layer_crossing", barrier_scoped_to_outer_layers_ignores_inner_layer_crossing),
        ("rules::routing::isolation_barrier::tests::catches_geometric_analog_of_star_point_ground_bridge_removed_by_6976ef44", catches_geometric_analog_of_star_point_ground_bridge_removed_by_6976ef44),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

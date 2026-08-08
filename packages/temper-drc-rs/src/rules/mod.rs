// DRC rule registry and implementations.
//
// Defines:
//   - DrcRule trait + RuleRegistry orchestrator
//   - migrated checks (U4) — see `create_default_registry()` for the live
//     count and rationale for any rule type that exists but is NOT
//     registered (as of 2026-08-08, `erc::PowerDomainCheck` is deliberately
//     excluded; do not trust a stale headline count in this comment, count
//     `create_default_registry()`'s `reg.register(...)` calls directly)
//   - Brute-force completeness oracles (U4)
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

pub mod drc;
pub mod emc;
pub mod erc;
pub mod oracle;
pub mod placement;
pub mod routing;
pub mod safety;

use std::collections::HashMap;

use geo::Rect;
use serde::Serialize;

use crate::board::{BoardState, NetClassRules, NetClassName};
use crate::constraints::ConstraintSet;

// ---------------------------------------------------------------------------
// DrcCategory
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum DrcCategory {
    Drc,
    Erc,
    Safety,
    Emc,
    Dfm,
}

impl std::fmt::Display for DrcCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DrcCategory::Drc => write!(f, "drc"),
            DrcCategory::Erc => write!(f, "erc"),
            DrcCategory::Safety => write!(f, "safety"),
            DrcCategory::Emc => write!(f, "emc"),
            DrcCategory::Dfm => write!(f, "dfm"),
        }
    }
}

// ---------------------------------------------------------------------------
// Severity
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Severity {
    Info,
    Warning,
    Error,
    Critical,
}

impl std::fmt::Display for Severity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Severity::Info => write!(f, "info"),
            Severity::Warning => write!(f, "warning"),
            Severity::Error => write!(f, "error"),
            Severity::Critical => write!(f, "critical"),
        }
    }
}

/// Numeric weight for severity — used for scoring / prioritization.
pub fn severity_weight(sev: Severity) -> f64 {
    match sev {
        Severity::Info => 0.0,
        Severity::Warning => 1.0,
        Severity::Error => 10.0,
        Severity::Critical => 100.0,
    }
}

// ---------------------------------------------------------------------------
// Location
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
pub struct Location {
    pub x: Option<f64>,
    pub y: Option<f64>,
    pub layer: Option<String>,
}

// ---------------------------------------------------------------------------
// Violation
// ---------------------------------------------------------------------------

/// A single DRC violation produced by a rule check.
///
/// Mirrors the Python `Issue` dataclass in `temper_drc.core.result`.
#[derive(Debug, Clone, Serialize)]
pub struct Violation {
    pub severity: Severity,
    pub code: String,
    pub message: String,
    pub category: DrcCategory,
    pub check_name: String,
    pub affected_items: Vec<String>,
    pub location: Option<Location>,
    pub details: serde_json::Value,
}

// ---------------------------------------------------------------------------
// DrcRule trait
// ---------------------------------------------------------------------------

/// A single DRC check rule.
///
/// Each check is one file implementing DrcRule, following the Python
/// original's logic in `packages/temper-drc/src/temper_drc/checks/`.
pub trait DrcRule: Send + Sync {
    /// Human-readable name (e.g., "drc_clearance").
    fn name(&self) -> &str;

    /// Category grouping (Drc, Erc, Safety, Emc, Dfm).
    fn category(&self) -> DrcCategory;

    /// Optional description of what this check validates.
    fn description(&self) -> &str {
        ""
    }

    /// Run the check against the full board state with constraints.
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation>;

    /// Whether this check supports incremental re-checking.
    fn supports_incremental(&self) -> bool {
        false
    }

    /// Re-check only within modified spatial regions.
    ///
    /// Default implementation falls back to full check.
    fn check_incremental(
        &self,
        board: &BoardState,
        constraints: &ConstraintSet,
        _regions: &[Rect<f64>],
    ) -> Vec<Violation> {
        self.check(board, constraints)
    }
}

// ---------------------------------------------------------------------------
// RuleRegistry
// ---------------------------------------------------------------------------

/// Registry of all registered DRC rules.
///
/// Supports running all checks, filtering by category, or running
/// incrementally by spatial region.
pub struct RuleRegistry {
    rules: Vec<Box<dyn DrcRule>>,
}

impl RuleRegistry {
    pub fn new() -> Self {
        Self {
            rules: Vec::new(),
        }
    }

    pub fn register(&mut self, rule: Box<dyn DrcRule>) {
        self.rules.push(rule);
    }

    /// Access the registered rules (for benchmarking / introspection).
    pub fn rules(&self) -> &[Box<dyn DrcRule>] {
        &self.rules
    }

    /// Run all registered checks against the full board.
    pub fn run_all(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        self.rules
            .iter()
            .flat_map(|r| r.check(board, constraints))
            .collect()
    }

    /// Run only checks matching the given categories.
    pub fn run_categories(
        &self,
        board: &BoardState,
        constraints: &ConstraintSet,
        categories: &[DrcCategory],
    ) -> Vec<Violation> {
        self.rules
            .iter()
            .filter(|r| categories.contains(&r.category()))
            .flat_map(|r| r.check(board, constraints))
            .collect()
    }

    /// Run all checks incrementally within the given regions.
    pub fn run_incremental(
        &self,
        board: &BoardState,
        constraints: &ConstraintSet,
        regions: &[Rect<f64>],
    ) -> Vec<Violation> {
        self.rules
            .iter()
            .flat_map(|r| r.check_incremental(board, constraints, regions))
            .collect()
    }
}

impl Default for RuleRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// create_default_registry
// ---------------------------------------------------------------------------

/// Create a RuleRegistry with all migrated checks registered.
///
/// 2026-08-08 vacuity remediation
/// (docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md, Task 1):
/// `erc::PowerDomainCheck` is deliberately NOT registered here. Its `check()`
/// unconditionally returned `vec![]` for any input (an undisguised stub, not
/// a rule that merely finds nothing) — registering it would let a caller
/// mistake "this check never runs" for "this check ran and passed". See the
/// doc comment on `erc::power_domain::PowerDomainCheck` for what a real
/// implementation needs (a `voltage_domain` field the native schema does not
/// currently carry). `erc::NetConnectivityCheck` had the same defect and
/// *is* still registered below — it was implemented for real as part of this
/// remediation instead (see `erc::net_connectivity`).
pub fn create_default_registry() -> RuleRegistry {
    let mut reg = RuleRegistry::new();
    reg.register(Box::new(drc::ClearanceCheck));
    reg.register(Box::new(drc::ComponentOverlapCheck));
    reg.register(Box::new(drc::CourtyardCheck::new(0.05)));
    reg.register(Box::new(drc::ZoneContainmentCheck));
    reg.register(Box::new(drc::TraceClearanceCheck));
    reg.register(Box::new(drc::ViaSpacingCheck));
    reg.register(Box::new(erc::NetConnectivityCheck));
    reg.register(Box::new(erc::FloatingPinsCheck));
    reg.register(Box::new(safety::HVLVSeparationCheck));
    reg.register(Box::new(safety::CreepageCheck::new(6.0)));
    reg.register(Box::new(safety::IsolationCheck));
    reg.register(Box::new(emc::LoopAreaCheck));
    reg.register(Box::new(emc::NoiseCouplingCheck));
    reg.register(Box::new(emc::GroundPlaneCheck));
    reg.register(Box::new(placement::ThermalViaCountCheck));
    reg.register(Box::new(placement::ThermalConstraintCheck));
    reg.register(Box::new(placement::WaveSolderKeepoutCheck));
    reg.register(Box::new(routing::ParallelRunCheck));
    reg.register(Box::new(routing::StitchingViaDensityCheck));
    reg.register(Box::new(routing::CopperPullbackCheck));
    reg.register(Box::new(routing::IsolationBarrierCheck));
    reg.register(Box::new(routing::ThtThermalReliefCheck));
    reg.register(Box::new(routing::PowerPadTeardropCheck));
    reg.register(Box::new(routing::PartialDischargeCheck));
    reg.register(Box::new(routing::PadEntryWidthCheck));
    reg.register(Box::new(routing::SplitPlaneCrossingCheck));
    reg.register(Box::new(routing::IsolationSlotCheck));
    reg
}

// ---------------------------------------------------------------------------
// Shared helper: clearance between two net classes
// ---------------------------------------------------------------------------

/// Net names belonging to net classes whose `max_current_rating` is at or
/// above `min_current` (A).  Shared by the high-current routing rules.
pub(crate) fn high_current_net_names(board: &BoardState, min_current: f64) -> Vec<&str> {
    let class_names: Vec<NetClassName> = board
        .net_class_rules
        .iter()
        .filter(|(_, rules)| rules.max_current_rating.is_some_and(|r| r >= min_current))
        .map(|(name, _)| name)
        .cloned()
        .collect();
    if class_names.is_empty() {
        return Vec::new();
    }
    board
        .nets
        .iter()
        .filter(|n| class_names.contains(&n.class))
        .map(|n| n.name.0.as_str())
        .collect()
}

/// Look up the minimum required clearance between two net classes.
///
/// Checks explicit ClearanceRule entries first, then falls back to
/// the maximum of the two classes' individual clearance_mm values.
pub fn clearance_between(
    constraints: &ConstraintSet,
    net_class_rules: &HashMap<NetClassName, NetClassRules>,
    class_a: &NetClassName,
    class_b: &NetClassName,
) -> f64 {
    // Check explicit pair rules (bidirectional)
    for rule in &constraints.clearances {
        if (rule.from_class == class_a.0 && rule.to_class == class_b.0)
            || (rule.from_class == class_b.0 && rule.to_class == class_a.0)
        {
            return rule.clearance_mm;
        }
    }
    // Fallback: max of individual clearances
    let a_clr = net_class_rules
        .get(class_a)
        .map(|r| r.clearance_mm)
        .unwrap_or(0.0);
    let b_clr = net_class_rules
        .get(class_b)
        .map(|r| r.clearance_mm)
        .unwrap_or(0.0);
    a_clr.max(b_clr)
}

// ---------------------------------------------------------------------------
// Helper: build a Violation struct
// ---------------------------------------------------------------------------

/// Convenience constructor for a Violation.
#[allow(clippy::too_many_arguments)]
pub fn violation(
    severity: Severity,
    code: &str,
    message: &str,
    category: DrcCategory,
    check_name: &str,
    affected_items: Vec<String>,
    location: Option<Location>,
    details: serde_json::Value,
) -> Violation {
    Violation {
        severity,
        code: code.to_string(),
        message: message.to_string(),
        category,
        check_name: check_name.to_string(),
        affected_items,
        location,
        details,
    }
}

/// Build a Location at the midpoint between two Points.
pub fn location_midpoint(
    a: &geo::Point<f64>,
    b: &geo::Point<f64>,
    layer: Option<&str>,
) -> Option<Location> {
    Some(Location {
        x: Some((a.x() + b.x()) / 2.0),
        y: Some((a.y() + b.y()) / 2.0),
        layer: layer.map(|s| s.to_string()),
    })
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod integration_tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::Point;
    use std::collections::HashMap;

    fn empty_board() -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![],
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn empty_constraints() -> ConstraintSet {
        ConstraintSet::default()
    }

    fn make_board(components: Vec<Component>) -> BoardState {
        BoardState {
            electrical_components: components,
            ..empty_board()
        }
    }

    #[cfg_attr(test, test)]
    fn empty_board_zero_violations() {
        let reg = create_default_registry();
        let violations = reg.run_all(&empty_board(), &empty_constraints());
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn incremental_check_equals_full_check_for_same_region() {
        // Build a simple board with two components and a constraint
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![
                Component {
                    refdes: ComponentRef("C1".into()),
                    center: Point::new(0.0, 0.0),
                    rotation: 0.0,
                    side: BoardSide::Top,
                    width: 10.0,
                    height: 10.0,
                    net_class: NetClassName("Signal".into()),
                    power_dissipation_w: None,
                    package_type: PackageType::Smd,
                    is_magnetic: false,
                    is_electrolytic: false,
                    vent_direction: None,
                    footprint_polygon: None,
                },
                Component {
                    refdes: ComponentRef("C2".into()),
                    center: Point::new(50.0, 0.0),
                    rotation: 0.0,
                    side: BoardSide::Top,
                    width: 10.0,
                    height: 10.0,
                    net_class: NetClassName("Signal".into()),
                    power_dissipation_w: None,
                    package_type: PackageType::Smd,
                    is_magnetic: false,
                    is_electrolytic: false,
                    vent_direction: None,
                    footprint_polygon: None,
                },
            ],
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: {
                let mut m = HashMap::new();
                m.insert(
                    NetClassName("Signal".into()),
                    NetClassRules::default(),
                );
                m
            },
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = empty_constraints();
        let reg = create_default_registry();
        let full = reg.run_all(&board, &constraints);
        let inc = reg.run_incremental(&board, &constraints, &[geo::Rect::new(
            (0.0, 0.0),
            (100.0, 100.0),
        )]);
        assert_eq!(
            full.len(),
            inc.len(),
            "incremental with full-board region should match run_all"
        );
    }

    // -----------------------------------------------------------------
    // Anti-vacuity guard (2026-08-08 remediation, Task 1)
    //
    // docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md found
    // `erc::PowerDomainCheck` and `erc::NetConnectivityCheck` registered
    // live while unconditionally returning `vec![]` for any input —
    // indistinguishable from a real "found nothing" pass. This is a
    // general guard against that whole failure class, not just those two:
    // for every rule `create_default_registry()` currently registers,
    // there must exist at least one fixture in this varied set that makes
    // it produce >=1 violation. A rule whose name never appears in the
    // accumulated output — across every fixture below — is either an
    // undisguised stub (the original defect) or has become unreachable by
    // regression, and either way must not ship silently.
    //
    // Each fixture is intentionally scoped to trip exactly one rule (its
    // own doc comment says which and why); the test doesn't assert
    // per-fixture violation counts, only that the full registry run across
    // the whole set eventually exercises every currently-registered check
    // name. Cross-fixture incidental hits (a fixture tripping more than
    // its target rule) are harmless to this test's guarantee.
    // -----------------------------------------------------------------

    use geo::{polygon, Coord, Line};
    use std::collections::HashSet;

    fn comp(refdes: &str, x: f64, y: f64, w: f64, h: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: w,
            height: h,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    /// drc_clearance — two 10x10 components 1mm apart, class clearance_mm=1.0.
    fn fixture_clearance() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(
            NetClassName("Signal".into()),
            NetClassRules { clearance_mm: 1.0, ..NetClassRules::default() },
        );
        let board = BoardState {
            net_class_rules: ncr,
            ..make_board(vec![comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal"), comp("C2", 11.0, 0.0, 10.0, 10.0, "Signal")])
        };
        let constraints = ConstraintSet {
            clearances: vec![ClearanceRule {
                from_class: "Signal".into(),
                to_class: "Signal".into(),
                clearance_mm: 1.0,
                description: String::new(),
            }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// drc_component_overlap — two same-layer components at the same center.
    fn fixture_component_overlap() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![
            comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal"),
            comp("C2", 1.0, 1.0, 10.0, 10.0, "Signal"),
        ]);
        (board, ConstraintSet::default())
    }

    /// drc_courtyard — bboxes 0.08mm apart, under the 0.05mm-per-side margin
    /// (0.1mm combined) but not overlapping (so component_overlap stays out).
    fn fixture_courtyard() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![
            comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal"),
            comp("C2", 10.08, 0.0, 10.0, 10.0, "Signal"),
        ]);
        (board, ConstraintSet::default())
    }

    /// drc_zone_containment — ACMains component outside the only copper
    /// zone that carries its class.
    fn fixture_zone_containment() -> (BoardState, ConstraintSet) {
        let poly = polygon![(x: 0.0, y: 0.0), (x: 10.0, y: 0.0), (x: 10.0, y: 10.0), (x: 0.0, y: 10.0)];
        let zone = CopperZone { net: NetName("ACMains".into()), layer: "F.Cu".into(), polygon: poly };
        let board = BoardState {
            zones: vec![zone],
            ..make_board(vec![comp("T1", 90.0, 90.0, 4.0, 4.0, "ACMains")])
        };
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition { name: "interface_zone".into(), net_classes: vec!["ACMains".into()] }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// drc_trace_clearance — two same-layer, different-net traces 0.05mm
    /// apart, class clearance_mm=1.0.
    fn fixture_trace_clearance() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(
            NetClassName("Signal".into()),
            NetClassRules { clearance_mm: 1.0, ..NetClassRules::default() },
        );
        let net_a = Net { name: NetName("NA".into()), components: vec![], class: NetClassName("Signal".into()), rules: NetClassRules::default() };
        let net_b = Net { name: NetName("NB".into()), components: vec![], class: NetClassName("Signal".into()), rules: NetClassRules::default() };
        let board = BoardState {
            net_class_rules: ncr,
            nets: vec![net_a, net_b],
            traces: vec![
                TraceSegment { net: NetName("NA".into()), layer: "F.Cu".into(), width: 0.2, segments: vec![Line::new(Coord { x: 0.0, y: 0.0 }, Coord { x: 20.0, y: 0.0 })] },
                TraceSegment { net: NetName("NB".into()), layer: "F.Cu".into(), width: 0.2, segments: vec![Line::new(Coord { x: 0.0, y: 0.05 }, Coord { x: 20.0, y: 0.05 })] },
            ],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// drc_via_spacing — two 0.6mm-pad vias 0.2mm apart (center distance).
    fn fixture_via_spacing() -> (BoardState, ConstraintSet) {
        let board = BoardState {
            vias: vec![
                Via { net: NetName("GND".into()), position: Point::new(0.0, 0.0), drill: 0.3, pad: 0.6, from_layer: "F.Cu".into(), to_layer: "B.Cu".into() },
                Via { net: NetName("GND".into()), position: Point::new(0.2, 0.0), drill: 0.3, pad: 0.6, from_layer: "F.Cu".into(), to_layer: "B.Cu".into() },
            ],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// erc_net_connectivity — a net with exactly 1 connected component.
    fn fixture_net_connectivity() -> (BoardState, ConstraintSet) {
        let board = BoardState {
            nets: vec![Net { name: NetName("N1".into()), components: vec![ComponentRef("C1".into())], class: NetClassName("Signal".into()), rules: NetClassRules::default() }],
            ..make_board(vec![comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal")])
        };
        (board, ConstraintSet::default())
    }

    /// erc_floating_pins — a component with no net membership at all.
    fn fixture_floating_pins() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal")]);
        (board, ConstraintSet::default())
    }

    /// safety_hv_lv_separation — HV/LV-keyword pair closer than the default
    /// 10mm hv_clearance_mm.
    fn fixture_hv_lv_separation() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![
            comp("Q1", 0.0, 0.0, 4.0, 4.0, "HV"),
            comp("R1", 2.0, 0.0, 4.0, 4.0, "Signal"),
        ]);
        (board, ConstraintSet::default())
    }

    /// safety_creepage — "opto"-keyword-classed component under 6.0mm width.
    fn fixture_creepage() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![comp("U1", 0.0, 0.0, 2.0, 2.0, "opto")]);
        (board, ConstraintSet::default())
    }

    /// safety_isolation — an "iso"-named zone claims a non-iso-device net
    /// class; string-equality match fires regardless of position (this
    /// rule's independently-documented position-blindness is out of scope
    /// for this remediation — see safety::isolation module doc).
    fn fixture_isolation() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![comp("R1", 0.0, 0.0, 4.0, 4.0, "Signal")]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition { name: "iso_zone".into(), net_classes: vec!["Signal".into()] }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// emc_loop_area — two components on a critical loop's net, 50mm apart,
    /// bbox area over a tight 50mm2 max.
    fn fixture_loop_area() -> (BoardState, ConstraintSet) {
        let board = BoardState {
            nets: vec![Net {
                name: NetName("N1".into()),
                components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
                class: NetClassName("Signal".into()),
                rules: NetClassRules::default(),
            }],
            ..make_board(vec![
                comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal"),
                comp("C2", 50.0, 10.0, 10.0, 10.0, "Signal"),
            ])
        };
        let constraints = ConstraintSet {
            critical_loops: vec![LoopConstraint {
                name: "loop1".into(),
                nets: vec!["N1".into()],
                max_area_mm2: Some(50.0),
                weight: 1.0,
            }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// emc_noise_coupling — "power"/"analog" pair 0.1mm apart, class
    /// clearance_mm=5.0 (> 0 required for the check to engage at all).
    fn fixture_noise_coupling() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(NetClassName("power".into()), NetClassRules { clearance_mm: 5.0, ..NetClassRules::default() });
        let board = BoardState {
            net_class_rules: ncr,
            ..make_board(vec![
                comp("C1", 0.0, 0.0, 4.0, 4.0, "power"),
                comp("C2", 2.1, 0.0, 4.0, 4.0, "analog"),
            ])
        };
        (board, ConstraintSet::default())
    }

    /// emc_ground_plane — noisy "power_switching" component with a
    /// configured gnd zone that doesn't cover its class.
    fn fixture_ground_plane() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![comp("C1", 50.0, 50.0, 10.0, 10.0, "power_switching")]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition { name: "GND_plane".into(), net_classes: vec!["analog".into()] }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// placement_thermal_via_count — 10W component with only 1 via (needs 7).
    fn fixture_thermal_via_count() -> (BoardState, ConstraintSet) {
        let mut c1 = comp("C1", 0.0, 0.0, 20.0, 20.0, "power");
        c1.power_dissipation_w = Some(10.0);
        let board = BoardState {
            nets: vec![Net { name: NetName("power".into()), components: vec![ComponentRef("C1".into())], class: NetClassName("power".into()), rules: NetClassRules::default() }],
            vias: vec![Via { net: NetName("power".into()), position: Point::new(0.0, 0.0), drill: 0.3, pad: 0.6, from_layer: "F.Cu".into(), to_layer: "B.Cu".into() }],
            ..make_board(vec![c1])
        };
        (board, ConstraintSet::default())
    }

    /// placement_thermal_constraint — component 48mm from the nearest edge
    /// of a 100x100 board, max_distance_from_edge_mm=10.
    fn fixture_thermal_constraint() -> (BoardState, ConstraintSet) {
        let board = make_board(vec![comp("Q1", 50.0, 50.0, 4.0, 4.0, "HighCurrent")]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q1".into()],
                prefer_edge: true,
                min_spacing_mm: 0.0,
                max_distance_from_edge_mm: 10.0,
                description: "guard fixture".into(),
            }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// placement_wave_solder_keepout — bottom SMD 8mm from a THT part,
    /// under the 5mm keepout once the SMD's own half-width is subtracted.
    fn fixture_wave_solder_keepout() -> (BoardState, ConstraintSet) {
        let mut smd = comp("C1", 0.0, 0.0, 10.0, 10.0, "Signal");
        smd.side = BoardSide::Bottom;
        let tht = {
            let mut c = comp("C2", 8.0, 0.0, 10.0, 10.0, "Signal");
            c.package_type = PackageType::Tht;
            c
        };
        let board = make_board(vec![smd, tht]);
        (board, ConstraintSet::default())
    }

    /// routing_parallel_run — two parallel 50mm traces 0.1mm apart, noise
    /// domain max_parallel_run_mm=5.0.
    fn fixture_parallel_run() -> (BoardState, ConstraintSet) {
        let board = BoardState {
            traces: vec![
                TraceSegment { net: NetName("AGGR".into()), layer: "F.Cu".into(), width: 0.2, segments: vec![Line::new(Coord { x: 0.0, y: 0.0 }, Coord { x: 50.0, y: 0.0 })] },
                TraceSegment { net: NetName("VICT".into()), layer: "F.Cu".into(), width: 0.2, segments: vec![Line::new(Coord { x: 0.0, y: 0.1 }, Coord { x: 50.0, y: 0.1 })] },
            ],
            ..empty_board()
        };
        let constraints = ConstraintSet {
            noise_domains: vec![NoiseDomain { emitters: vec!["AGGR".into()], victims: vec!["VICT".into()], max_parallel_run_mm: 5.0 }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// routing_stitching_via_density — two GND vias 20mm apart inside a GND
    /// copper zone (over a 15mm max spacing).
    fn fixture_stitching_via_density() -> (BoardState, ConstraintSet) {
        let poly = polygon![(x: -5.0, y: -5.0), (x: 25.0, y: -5.0), (x: 25.0, y: 5.0), (x: -5.0, y: 5.0)];
        let board = BoardState {
            vias: vec![
                Via { net: NetName("GND".into()), position: Point::new(0.0, 0.0), drill: 0.3, pad: 0.6, from_layer: "F.Cu".into(), to_layer: "B.Cu".into() },
                Via { net: NetName("GND".into()), position: Point::new(20.0, 0.0), drill: 0.3, pad: 0.6, from_layer: "F.Cu".into(), to_layer: "B.Cu".into() },
            ],
            zones: vec![CopperZone { net: NetName("GND".into()), layer: "F.Cu".into(), polygon: poly }],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// routing_copper_pullback — a zone extending past the board's margin
    /// inset (margin=3, zone reaches x=-5).
    fn fixture_copper_pullback() -> (BoardState, ConstraintSet) {
        let poly = polygon![(x: -5.0, y: 40.0), (x: 10.0, y: 40.0), (x: 10.0, y: 60.0), (x: -5.0, y: 60.0)];
        let board = BoardState {
            zones: vec![CopperZone { net: NetName("PWR".into()), layer: "F.Cu".into(), polygon: poly }],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// routing_isolation_barrier — a trace segment crossing a configured
    /// vertical isolation barrier line.
    fn fixture_isolation_barrier() -> (BoardState, ConstraintSet) {
        let board = BoardState {
            traces: vec![TraceSegment { net: NetName("HV1".into()), layer: "F.Cu".into(), width: 0.3, segments: vec![Line::new(Coord { x: 40.0, y: 50.0 }, Coord { x: 60.0, y: 50.0 })] }],
            ..empty_board()
        };
        let constraints = ConstraintSet {
            isolation_barriers: vec![IsolationBarrier { name: "main_barrier".into(), x_mm: 50.0, y_span: [0.0, 100.0], layers: "all".into() }],
            ..Default::default()
        };
        (board, constraints)
    }

    /// routing_partial_discharge — an inner-layer HV trace 0.1mm from
    /// another trace, well under the 0.2mm base clearance x 1.5 = 0.3mm
    /// required minimum.
    fn fixture_partial_discharge() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(NetClassName("HighVoltage".into()), NetClassRules { voltage_v: 340.0, clearance_mm: 0.2, ..NetClassRules::default() });
        let board = BoardState {
            net_class_rules: ncr,
            nets: vec![Net {
                name: NetName("HV1".into()),
                components: vec![],
                class: NetClassName("HighVoltage".into()),
                rules: NetClassRules { clearance_mm: 0.2, ..NetClassRules::default() },
            }],
            traces: vec![
                TraceSegment { net: NetName("HV1".into()), layer: "In1.Cu".into(), width: 0.3, segments: vec![Line::new(Coord { x: 0.0, y: 0.0 }, Coord { x: 10.0, y: 0.0 })] },
                TraceSegment { net: NetName("OTHER".into()), layer: "In1.Cu".into(), width: 0.3, segments: vec![Line::new(Coord { x: 0.0, y: 0.1 }, Coord { x: 10.0, y: 0.1 })] },
            ],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// routing_tht_thermal_relief — THT part on a net class rated <= threshold.
    fn fixture_tht_thermal_relief() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(NetClassName("Signal".into()), NetClassRules { max_current_rating: Some(5.0), ..NetClassRules::default() });
        let mut c = comp("D1", 0.0, 0.0, 5.0, 5.0, "Signal");
        c.package_type = PackageType::Tht;
        let board = BoardState { net_class_rules: ncr, ..make_board(vec![c]) };
        (board, ConstraintSet::default())
    }

    /// routing_power_pad_teardrop — narrow trace entering a large pad on a
    /// high-current net.
    fn fixture_power_pad_teardrop() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(NetClassName("Power".into()), NetClassRules { max_current_rating: Some(10.0), ..NetClassRules::default() });
        let board = BoardState {
            net_class_rules: ncr,
            nets: vec![Net { name: NetName("PWR".into()), components: vec![ComponentRef("R1".into())], class: NetClassName("Power".into()), rules: NetClassRules::default() }],
            traces: vec![TraceSegment { net: NetName("PWR".into()), layer: "F.Cu".into(), width: 1.0, segments: vec![Line::new(Coord { x: 5.2, y: 0.0 }, Coord { x: 20.0, y: 0.0 })] }],
            ..make_board(vec![comp("R1", 0.0, 0.0, 10.0, 10.0, "Power")])
        };
        (board, ConstraintSet::default())
    }

    /// routing_pad_entry_width — narrow trace entering a large pad on a
    /// very-high-current net.
    fn fixture_pad_entry_width() -> (BoardState, ConstraintSet) {
        let mut ncr = HashMap::new();
        ncr.insert(NetClassName("HighCurrent".into()), NetClassRules { max_current_rating: Some(25.0), ..NetClassRules::default() });
        let board = BoardState {
            net_class_rules: ncr,
            nets: vec![Net { name: NetName("BUS".into()), components: vec![ComponentRef("Q1".into())], class: NetClassName("HighCurrent".into()), rules: NetClassRules::default() }],
            traces: vec![TraceSegment { net: NetName("BUS".into()), layer: "F.Cu".into(), width: 1.0, segments: vec![Line::new(Coord { x: 5.2, y: 0.0 }, Coord { x: 20.0, y: 0.0 })] }],
            ..make_board(vec![comp("Q1", 0.0, 0.0, 10.0, 10.0, "HighCurrent")])
        };
        (board, ConstraintSet::default())
    }

    /// routing_split_plane_crossing — a trace's two segments sit in two
    /// differently-named copper zones.
    fn fixture_split_plane_crossing() -> (BoardState, ConstraintSet) {
        let poly_a = polygon![(x: 0.0, y: 0.0), (x: 10.0, y: 0.0), (x: 10.0, y: 10.0), (x: 0.0, y: 10.0)];
        let poly_b = polygon![(x: 20.0, y: 0.0), (x: 30.0, y: 0.0), (x: 30.0, y: 10.0), (x: 20.0, y: 10.0)];
        let board = BoardState {
            traces: vec![TraceSegment {
                net: NetName("SPI_CLK".into()),
                layer: "F.Cu".into(),
                width: 0.2,
                segments: vec![
                    Line::new(Coord { x: 0.0, y: 5.0 }, Coord { x: 5.0, y: 5.0 }),
                    Line::new(Coord { x: 25.0, y: 5.0 }, Coord { x: 28.0, y: 5.0 }),
                ],
            }],
            zones: vec![
                CopperZone { net: NetName("GND_A".into()), layer: "F.Cu".into(), polygon: poly_a },
                CopperZone { net: NetName("GND_B".into()), layer: "F.Cu".into(), polygon: poly_b },
            ],
            ..empty_board()
        };
        (board, ConstraintSet::default())
    }

    /// routing_isolation_slot — a zone named "isolation_slot" with a
    /// same-named, too-narrow (1mm) copper polygon.
    fn fixture_isolation_slot() -> (BoardState, ConstraintSet) {
        let poly = polygon![(x: 0.0, y: 0.0), (x: 1.0, y: 0.0), (x: 1.0, y: 10.0), (x: 0.0, y: 10.0)];
        let board = BoardState {
            zones: vec![CopperZone { net: NetName("isolation_slot".into()), layer: "F.Cu".into(), polygon: poly }],
            ..empty_board()
        };
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition { name: "isolation_slot".into(), net_classes: vec![] }],
            ..Default::default()
        };
        (board, constraints)
    }

    #[cfg_attr(test, test)]
    fn no_registered_rule_is_vacuous_across_varied_fixtures() {
        let fixtures: Vec<(&str, (BoardState, ConstraintSet))> = vec![
            ("clearance", fixture_clearance()),
            ("component_overlap", fixture_component_overlap()),
            ("courtyard", fixture_courtyard()),
            ("zone_containment", fixture_zone_containment()),
            ("trace_clearance", fixture_trace_clearance()),
            ("via_spacing", fixture_via_spacing()),
            ("net_connectivity", fixture_net_connectivity()),
            ("floating_pins", fixture_floating_pins()),
            ("hv_lv_separation", fixture_hv_lv_separation()),
            ("creepage", fixture_creepage()),
            ("isolation", fixture_isolation()),
            ("loop_area", fixture_loop_area()),
            ("noise_coupling", fixture_noise_coupling()),
            ("ground_plane", fixture_ground_plane()),
            ("thermal_via_count", fixture_thermal_via_count()),
            ("thermal_constraint", fixture_thermal_constraint()),
            ("wave_solder_keepout", fixture_wave_solder_keepout()),
            ("parallel_run", fixture_parallel_run()),
            ("stitching_via_density", fixture_stitching_via_density()),
            ("copper_pullback", fixture_copper_pullback()),
            ("isolation_barrier", fixture_isolation_barrier()),
            ("partial_discharge", fixture_partial_discharge()),
            ("tht_thermal_relief", fixture_tht_thermal_relief()),
            ("power_pad_teardrop", fixture_power_pad_teardrop()),
            ("pad_entry_width", fixture_pad_entry_width()),
            ("split_plane_crossing", fixture_split_plane_crossing()),
            ("isolation_slot", fixture_isolation_slot()),
        ];

        let reg = create_default_registry();
        let mut covered: HashSet<String> = HashSet::new();
        let mut per_fixture_hit = false;
        for (fixture_name, (board, constraints)) in &fixtures {
            let violations = reg.run_all(board, constraints);
            assert!(
                !violations.is_empty(),
                "fixture '{fixture_name}' was designed to trip a specific rule but produced \
                 0 violations from the whole registry — the fixture itself is broken, not \
                 just under-covering",
            );
            per_fixture_hit = true;
            for v in violations {
                covered.insert(v.check_name);
            }
        }
        assert!(per_fixture_hit, "fixture set must be non-empty");

        let mut vacuous: Vec<&str> = reg
            .rules()
            .iter()
            .map(|r| r.name())
            .filter(|name| !covered.contains(*name))
            .collect();
        vacuous.sort_unstable();
        assert!(
            vacuous.is_empty(),
            "the following registered rule(s) returned EMPTY for every fixture in this varied \
             set — each is either an undisguised vec![] stub (the PowerDomainCheck/\
             NetConnectivityCheck defect class) or has regressed to unreachable: {vacuous:?}. \
             Add a fixture above that trips it, or if it genuinely cannot fire, remove it from \
             create_default_registry() rather than let it masquerade as a passing check.",
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: integration_tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::integration_tests::empty_board_zero_violations", empty_board_zero_violations),
        ("rules::integration_tests::incremental_check_equals_full_check_for_same_region", incremental_check_equals_full_check_for_same_region),
        ("rules::integration_tests::no_registered_rule_is_vacuous_across_varied_fixtures", no_registered_rule_is_vacuous_across_varied_fixtures),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: integration_tests ---
}


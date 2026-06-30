// DRC rule registry and implementations.
//
// Defines:
//   - DrcRule trait + RuleRegistry orchestrator
//   - 15 migrated checks (U4)
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

/// Create a RuleRegistry with all 15 migrated checks registered.
pub fn create_default_registry() -> RuleRegistry {
    let mut reg = RuleRegistry::new();
    reg.register(Box::new(drc::ClearanceCheck::new()));
    reg.register(Box::new(drc::ComponentOverlapCheck::new()));
    reg.register(Box::new(drc::CourtyardCheck::new(0.05)));
    reg.register(Box::new(drc::ZoneContainmentCheck::new()));
    reg.register(Box::new(drc::TraceClearanceCheck::new()));
    reg.register(Box::new(drc::ViaSpacingCheck::new()));
    reg.register(Box::new(erc::NetConnectivityCheck::new()));
    reg.register(Box::new(erc::PowerDomainCheck::new()));
    reg.register(Box::new(erc::FloatingPinsCheck::new()));
    reg.register(Box::new(safety::HVLVSeparationCheck::new()));
    reg.register(Box::new(safety::CreepageCheck::new(6.0)));
    reg.register(Box::new(safety::IsolationCheck::new()));
    reg.register(Box::new(emc::LoopAreaCheck::new()));
    reg.register(Box::new(emc::NoiseCouplingCheck::new()));
    reg.register(Box::new(emc::GroundPlaneCheck::new()));
    reg.register(Box::new(placement::ThermalViaCountCheck::new()));
    reg.register(Box::new(placement::WaveSolderKeepoutCheck::new()));
    reg.register(Box::new(routing::ParallelRunCheck::new()));
    reg.register(Box::new(routing::StitchingViaDensityCheck::new()));
    reg.register(Box::new(routing::CopperPullbackCheck::new()));
    reg.register(Box::new(routing::IsolationBarrierCheck::new()));
    reg.register(Box::new(routing::ThtThermalReliefCheck::new()));
    reg.register(Box::new(routing::PowerPadTeardropCheck::new()));
    reg.register(Box::new(routing::PartialDischargeCheck::new()));
    reg.register(Box::new(routing::PadEntryWidthCheck::new()));
    reg.register(Box::new(routing::SplitPlaneCrossingCheck::new()));
    reg.register(Box::new(routing::IsolationSlotCheck::new()));
    reg
}

// ---------------------------------------------------------------------------
// Shared helper: clearance between two net classes
// ---------------------------------------------------------------------------

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

#[cfg(test)]
mod integration_tests {
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

    #[test]
    fn empty_board_zero_violations() {
        let reg = create_default_registry();
        let violations = reg.run_all(&empty_board(), &empty_constraints());
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[test]
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
}


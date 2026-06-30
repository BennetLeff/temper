// Placeholder — will be implemented in U4 (migrated DRC checks).
use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{DrcCategory, DrcRule, Violation};

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
        "Placeholder — U4"
    }
    fn check(&self, _board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        vec![]
    }
}

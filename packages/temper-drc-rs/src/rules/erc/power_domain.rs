// Placeholder — will be implemented in U4 (migrated DRC checks).
use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{DrcCategory, DrcRule, Violation};

pub struct PowerDomainCheck;
impl PowerDomainCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for PowerDomainCheck {
    fn name(&self) -> &str {
        "erc_power_domain"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Erc
    }
    fn description(&self) -> &str {
        "Placeholder — U4"
    }
    fn check(&self, _board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        vec![]
    }
}

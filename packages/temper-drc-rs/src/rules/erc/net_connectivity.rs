// Placeholder — will be implemented in U4 (migrated DRC checks).
use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{DrcCategory, DrcRule, Violation};

pub struct NetConnectivityCheck;
impl NetConnectivityCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for NetConnectivityCheck {
    fn name(&self) -> &str {
        "erc_net_connectivity"
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

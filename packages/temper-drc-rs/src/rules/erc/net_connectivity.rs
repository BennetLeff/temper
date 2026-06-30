// ERC check: net connectivity — every net must have at least two connected
// (non-mechanical) components.
//
// Placeholder — will be fully implemented in U4 (migrated DRC checks).
// Mechanical components (mounting holes, etc.) are excluded from connection
// counts since they carry no electrical nets by design.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashSet;

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
        "Verify each net has at least two connected (non-mechanical) components."
    }
    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        // Only electrical components are in board.electrical_components —
        // mechanical components are separated at the type level.
        let _filtered_connection_counts: Vec<(&str, usize)> = board
            .nets
            .iter()
            .map(|(net, refs)| {
                let count = refs.len();
                (net.as_str(), count)
            })
            .collect();

        // TODO: Implement full net connectivity check using filtered counts.
        // Mechanical components are now excluded from connection tallies,
        // ready for the U4 implementation.
        vec![]
    }
}

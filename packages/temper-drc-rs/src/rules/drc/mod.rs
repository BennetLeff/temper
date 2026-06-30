// DRC checks: component-level physical design rules.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

mod clearance;
mod component_overlap;
mod courtyard;
mod trace_clearance;
mod via_spacing;
mod zone_containment;

pub use clearance::ClearanceCheck;
pub use component_overlap::ComponentOverlapCheck;
pub use courtyard::CourtyardCheck;
pub use trace_clearance::TraceClearanceCheck;
pub use via_spacing::ViaSpacingCheck;
pub use zone_containment::ZoneContainmentCheck;

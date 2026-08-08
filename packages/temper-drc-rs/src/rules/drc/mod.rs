// DRC checks: component-level physical design rules.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

pub(crate) mod clearance;
mod component_overlap;
mod courtyard;
// Property-based volume campaign (R7) over `Component::edge_distance_to`;
// not a `DrcRule` itself, no `pub use` needed -- see the module doc. `pub`
// (not `pub(crate)`) so `examples/property_containment_sweep.rs` and
// `tests/property_containment_gap.rs` can reuse `gen_case`/`naive_closest`
// rather than re-implementing them.
pub mod property_campaigns;
mod trace_clearance;
mod via_spacing;
pub(crate) mod zone_containment;
pub use clearance::ClearanceCheck;
pub use component_overlap::ComponentOverlapCheck;
pub use courtyard::CourtyardCheck;
pub use trace_clearance::TraceClearanceCheck;
pub use via_spacing::ViaSpacingCheck;
pub use zone_containment::ZoneContainmentCheck;

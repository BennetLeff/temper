// Routing checks: via stitching, copper pullback, isolation barriers,
// parallel-run length, thermal relief, pad teardrop, partial discharge,
// pad entry width, split-plane crossing, and isolation slots.
//
// Origin: U4/U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

mod copper_pullback;
mod isolation_barrier;
mod isolation_slot;
mod pad_entry_width;
mod parallel_run;
mod partial_discharge;
mod power_pad_teardrop;
mod split_plane_crossing;
mod stitching_via_density;
mod tht_thermal_relief;

pub use copper_pullback::CopperPullbackCheck;
pub use isolation_barrier::IsolationBarrierCheck;
pub use isolation_slot::IsolationSlotCheck;
pub use pad_entry_width::PadEntryWidthCheck;
pub use parallel_run::ParallelRunCheck;
pub use partial_discharge::PartialDischargeCheck;
pub use power_pad_teardrop::PowerPadTeardropCheck;
pub use split_plane_crossing::SplitPlaneCrossingCheck;
pub use stitching_via_density::StitchingViaDensityCheck;
pub use tht_thermal_relief::ThtThermalReliefCheck;

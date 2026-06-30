// EMC checks: electromagnetic compatibility rules.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

mod ground_plane;
mod loop_area;
mod noise_coupling;

pub use ground_plane::GroundPlaneCheck;
pub use loop_area::LoopAreaCheck;
pub use noise_coupling::NoiseCouplingCheck;

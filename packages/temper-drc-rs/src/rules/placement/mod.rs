// Placement checks: component-level physical design rules.
//
// Origin: U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

pub mod thermal_via_count;
pub mod wave_solder_keepout;

pub use thermal_via_count::ThermalViaCountCheck;
pub use wave_solder_keepout::WaveSolderKeepoutCheck;

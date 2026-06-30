// Type-level invariants for compile-time DRC checks.
//
// 8 PCB designer constraints enforced at compile time via Rust's type system.
// Components and nets in BoardState carry phantom type parameters or implement
// marker traits based on YAML constraint classification (U3).
//
// Each invariant type has a validate() method returning Result<(), Vec<String>>
// for runtime unit testing — so tests can exercise invariant logic without
// actually failing rustc compilation.
//
// Origin: U5 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

pub mod clock;
pub mod noise;
pub mod magnetic;
pub mod esd;
pub mod guard;
pub mod vent;
pub mod fuse;
pub mod hv_net;

// Allow unused re-exports — these are consumed by external crate users.
// The type-level invariants are designed to be used from `temper_drc_rs::types::*`.
#[allow(unused_imports)]
pub use clock::*;
#[allow(unused_imports)]
pub use noise::*;
#[allow(unused_imports)]
pub use magnetic::*;
#[allow(unused_imports)]
pub use esd::*;
#[allow(unused_imports)]
pub use guard::*;
#[allow(unused_imports)]
pub use vent::*;
#[allow(unused_imports)]
pub use fuse::*;
#[allow(unused_imports)]
pub use hv_net::*;

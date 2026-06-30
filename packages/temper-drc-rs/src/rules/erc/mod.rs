// ERC checks: electrical rule checks.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

mod floating_pins;
mod net_connectivity;
mod power_domain;

pub use floating_pins::FloatingPinsCheck;
pub use net_connectivity::NetConnectivityCheck;
pub use power_domain::PowerDomainCheck;

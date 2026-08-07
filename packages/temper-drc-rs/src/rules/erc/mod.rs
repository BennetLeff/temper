// ERC checks: electrical rule checks.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

pub(crate) mod floating_pins;
pub(crate) mod net_connectivity;
pub(crate) mod power_domain;
pub use floating_pins::FloatingPinsCheck;
pub use net_connectivity::NetConnectivityCheck;
pub use power_domain::PowerDomainCheck;

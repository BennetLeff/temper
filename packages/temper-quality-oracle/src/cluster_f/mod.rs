//! router_v6 **cluster F** — the quality-metric kernels.
//!
//! Three Python modules migrate as one unit because they share one parsed-board
//! fixture, one pinned oracle and one corpus:
//!
//! | Python module | Rust module |
//! |---|---|
//! | `router_v6/metrics/slop_linter.py` | [`slop_linter`] |
//! | `router_v6/quality/corridor.py`    | [`corridor`] |
//! | `router_v6/quality/via_count.py`   | [`via_count`] |
//!
//! The oracle these are pinned against is
//! `packages/temper-placer/tests/router_v6/_quality_metrics_py_oracle.py`, a
//! verbatim extraction from `15110feccc6ec9389f0777d3cff1ce9f81b11068`. It
//! preserves three defects on purpose, and so does this port:
//!
//! 1. `_classify_vias`'s `signal` accumulator is dead code.
//! 2. `corridor` compares board-relative courtyards against page-absolute
//!    traces, which makes both of its scores near-constant on real boards.
//! 3. Both `else` arms of `_identify_channels` are unreachable at any positive
//!    threshold, which makes the score depend on component list order.
//!
//! Reproducing a defect is the contract here. A fix belongs in a separate
//! change that re-pins the oracle first.

pub mod board;
pub mod corridor;
pub mod netclass;
pub mod pyfloat;
pub mod slop_linter;
pub mod via_count;

#[cfg(feature = "python")]
pub mod bindings;

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
#[path = "threshold_tests.rs"]
pub(crate) mod threshold_tests;

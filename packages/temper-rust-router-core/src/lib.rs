#![allow(clippy::collapsible_if)]
#![allow(clippy::empty_line_after_doc_comments)]
#![allow(clippy::type_complexity)]
#![allow(clippy::manual_slice_fill)]
#![allow(clippy::needless_range_loop)]
//! Router V6 core logic — SAT-based topology solving.
//!
//! Many nested if-let chains use || conditions not supported in let-chains.

pub mod astar;
pub mod audit;
pub mod bmc;
pub mod combinator;
pub mod encoding;
pub mod esl;
pub mod extraction;
pub mod loop_extractor;
pub mod provenance;
pub mod solver;
pub mod tension;
pub mod types;
pub mod watchdog;

pub use solver::{solve_with_cadical, SolveLimits};
pub use extraction::{extract_bundled, extract_topology, expand_assignments};
pub use loop_extractor::extract::auto_extract_loops;
pub use types::{
    BundleClass, BundledSolverResult, InternalBundleManifest, InternalConstraint,
    InternalConstraintModel, InternalVariable, SolverStats, SolverStatus, TopologyGraph,
    TopologyResult,
};

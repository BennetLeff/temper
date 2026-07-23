// Internal Rust-only types for the router core.
//
// Contains all types consumed by the solver, encoding, extraction, audit,
// BMC, provenance, tension, and watchdog modules.
//
// Origin: extracted from temper-rust-router/src/types.rs via U1 of
// docs/plans/2026-07-08-002-feat-router-build-unblock-plan.md

use std::collections::HashMap;

// ---------------------------------------------------------------------------
// Internal Rust-only types (not exported to Python)
// ---------------------------------------------------------------------------

/// Internal constraint representation for solver consumption.
#[derive(Clone, Debug)]
pub enum InternalVariable {
    NetChannel {
        name: String,
        net_idx: usize,
        channel_id: String,
    },
    NetLayer {
        name: String,
        net_idx: usize,
        segment_id: String,
    },
    Via {
        name: String,
        net_idx: usize,
        location_id: String,
    },
    Ordering {
        name: String,
        net1_idx: usize,
        net2_idx: usize,
        channel_id: String,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub enum InternalConstraint {
    Capacity {
        channel_id: String,
        capacity: f64,
        slack_factor: f64,
        terms: Vec<(String, f64)>, // (variable_name, width)
    },
    DiffPair {
        channel_id: String,
        p_var_name: String,
        n_var_name: String,
    },
    LayerRestriction {
        var_name: String,
        allowed: bool,
    },
    ChannelSeparation {
        group_a: Vec<usize>,
        group_b: Vec<usize>,
        min_slots: usize,
        channel_id: String,
    },
}

#[derive(Clone, Debug)]
pub struct InternalConstraintModel {
    pub variables: Vec<InternalVariable>,
    pub constraints: Vec<InternalConstraint>,
}

/// SAT variable and clause (internal, not pyclass — passed as data).
#[derive(Clone, Debug)]
pub struct SatVariable {
    pub name: String,
    pub description: String,
}

impl SatVariable {
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct SatClause {
    /// (variable_index, is_positive)
    pub literals: Vec<(usize, bool)>,
}

// ---------------------------------------------------------------------------
// Solver result types
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub enum SolverStatus {
    Satisfiable,
    Unsatisfiable,
    Unknown,
}

#[derive(Clone, Debug)]
pub struct SolverStats {
    pub conflicts: u64,
    pub decisions: u64,
    pub propagations: u64,
    pub decision_level_histogram: [u64; 10],
    pub unsat_core_size: usize,
    pub variable_count: u64,
    pub clause_count: u64,
    pub cpu_solve_time_ms: f64,
}

#[derive(Clone, Debug)]
pub struct TopologyResult {
    pub status: SolverStatus,
    pub num_vars: usize,
    pub num_clauses: usize,
    pub assignments: HashMap<usize, bool>,
    pub unsat_core: Vec<usize>,
    pub solver_time_ms: f64,
    pub solver_stats: Option<SolverStats>,
}

// ---------------------------------------------------------------------------
// Topology extraction types
// ---------------------------------------------------------------------------

/// Channel path for a single net.
#[derive(Clone, Debug)]
pub struct NetTopology {
    pub net_name: String,
    /// List of channel IDs the net is assigned to.
    pub uses_channels: Vec<String>,
    /// Ordered edge walk: (src_channel_id, dst_channel_id) for each hop.
    /// For single-channel nets: [(net_name, channel_id)].
    pub path_graph: Vec<(String, String)>,
    /// Estimated total length in mm.
    pub total_length_estimate: f64,
}

/// Extracted topology graph — returned to Python.
#[derive(Clone, Debug)]
pub struct TopologyGraph {
    pub net_topologies: HashMap<String, NetTopology>,
}

// ---------------------------------------------------------------------------
// Bundle manifest types (U1 / U4)
// ---------------------------------------------------------------------------

/// A single bundle equivalence class.
#[derive(Clone, Debug)]
pub struct BundleClass {
    pub bundle_id: usize,
    pub net_indices: Vec<usize>,
    pub constraint_types: Vec<String>,
    pub is_diff_pair: bool,
}

/// Manifest bridging Python BundleManifest → Rust.
#[derive(Clone, Debug)]
pub struct InternalBundleManifest {
    pub bundles: Vec<BundleClass>,
    pub bundle_id_for_net: HashMap<usize, usize>,
    pub unbundled_net_indices: Vec<usize>,
}

// ---------------------------------------------------------------------------
// Extended solver result with lazy grounding metadata
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct BundledSolverResult {
    pub status: SolverStatus,
    pub assignments: HashMap<usize, bool>,
    pub var_names: Vec<String>,
    pub num_vars: usize,
    pub num_clauses: usize,
    pub solver_time_ms: f64,
    pub cegar_iterations: usize,
    pub budget_used: usize,
    pub degraded_nets: Vec<String>,
}

// ---------------------------------------------------------------------------
// Provenance types (used by provenance.rs)
// ---------------------------------------------------------------------------

/// Role of a clause in the CNF encoding.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClauseRole {
    CardinalityCounter,
    CardinalityExclusion,
    ConstraintLiteral,
    Unit,
}

/// Maps a CNF clause back to the constraint that generated it.
#[derive(Clone, Copy, Debug)]
pub struct ClauseOrigin {
    pub constraint_idx: u8,
    pub role: ClauseRole,
    pub generation: u8,
}

impl ClauseOrigin {
    pub fn new(constraint_idx: u8, role: ClauseRole, generation: u8) -> Self {
        Self {
            constraint_idx,
            role,
            generation,
        }
    }
}

/// Human-readable conflict report from UNSAT core analysis.
#[derive(Clone, Debug)]
pub struct ConflictReport {
    pub conflicting_constraints: Vec<(usize, String)>,
    pub channels_involved: Vec<String>,
    pub explanation: String,
    pub core_clause_count: usize,
}

// ---------------------------------------------------------------------------
// Tension detection types (used by tension.rs)
// ---------------------------------------------------------------------------

/// Severity of a detected tension.
#[derive(Clone, Debug, PartialEq)]
pub enum TensionSeverity {
    HardConflict,
    CapacityWarning,
}

/// A detected pre-solve tension between constraints.
#[derive(Clone, Debug, PartialEq)]
pub struct TensionViolation {
    pub constraint_pair: (usize, usize),
    pub channel_id: String,
    pub explanation: String,
    pub severity: TensionSeverity,
}

// ---------------------------------------------------------------------------
// Conversion trait
// ---------------------------------------------------------------------------

/// Trait for converting Python pyclass types into internal Rust types.
/// Implementations live in the pyo3 wrapper crate.
pub trait IntoInternal {
    type Output;
    fn to_internal(&self) -> Self::Output;
}

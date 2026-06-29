// Constraint model, SAT model, and topology types.
//
// Mirrors the Python dataclasses in:
//   constraint_model.py, sat_model.py, topology_solver.py, topology_extraction.py
//
// Origin: U4 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::collections::HashMap;

use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// Constraint model variables
// ---------------------------------------------------------------------------

/// Base class for routing variables.
#[pyclass(subclass, get_all)]
#[derive(Clone, Debug)]
pub struct Variable {
    pub name: String,
    pub var_type: String, // "bool", "int", "continuous"
}

#[pymethods]
impl Variable {
    #[new]
    fn new(name: String, var_type: String) -> Self {
        Self { name, var_type }
    }
}

/// uses[net_idx, channel_id]
#[pyclass(extends=Variable, get_all)]
#[derive(Clone, Debug)]
pub struct NetChannelVar {
    pub net_idx: usize,
    pub channel_id: String,
}

#[pymethods]
impl NetChannelVar {
    #[new]
    #[pyo3(signature = (name, var_type, net_idx, channel_id))]
    fn new(name: String, var_type: String, net_idx: usize, channel_id: String) -> (Self, Variable) {
        (
            Self {
                net_idx,
                channel_id,
            },
            Variable { name, var_type },
        )
    }
}

/// layer[net_idx, segment_id]
#[pyclass(extends=Variable, get_all)]
#[derive(Clone, Debug)]
pub struct NetLayerVar {
    pub net_idx: usize,
    pub segment_id: String,
}

#[pymethods]
impl NetLayerVar {
    #[new]
    #[pyo3(signature = (name, var_type, net_idx, segment_id))]
    fn new(name: String, var_type: String, net_idx: usize, segment_id: String) -> (Self, Variable) {
        (
            Self {
                net_idx,
                segment_id,
            },
            Variable { name, var_type },
        )
    }
}

/// via[net_idx, location_id]
#[pyclass(extends=Variable, get_all)]
#[derive(Clone, Debug)]
pub struct ViaVar {
    pub net_idx: usize,
    pub location_id: String,
}

#[pymethods]
impl ViaVar {
    #[new]
    #[pyo3(signature = (name, var_type, net_idx, location_id))]
    fn new(name: String, var_type: String, net_idx: usize, location_id: String) -> (Self, Variable) {
        (
            Self {
                net_idx,
                location_id,
            },
            Variable { name, var_type },
        )
    }
}

/// order[net1_idx, net2_idx, channel_id]
#[pyclass(extends=Variable, get_all)]
#[derive(Clone, Debug)]
pub struct OrderVar {
    pub net1_idx: usize,
    pub net2_idx: usize,
    pub channel_id: String,
}

#[pymethods]
impl OrderVar {
    #[new]
    #[pyo3(signature = (name, var_type, net1_idx, net2_idx, channel_id))]
    fn new(
        name: String,
        var_type: String,
        net1_idx: usize,
        net2_idx: usize,
        channel_id: String,
    ) -> (Self, Variable) {
        (
            Self {
                net1_idx,
                net2_idx,
                channel_id,
            },
            Variable { name, var_type },
        )
    }
}

// ---------------------------------------------------------------------------
// Constraints
// ---------------------------------------------------------------------------

/// Base class for routing constraints.
#[pyclass(subclass, get_all)]
#[derive(Clone, Debug)]
pub struct Constraint {
    pub name: String,
    pub description: String,
}

#[pymethods]
impl Constraint {
    #[new]
    #[pyo3(signature = (name, description="".into()))]
    fn new(name: String, description: String) -> Self {
        Self { name, description }
    }
}

/// Capacity: sum(uses[n,c] * width[n]) <= capacity * slack
#[pyclass(extends=Constraint, get_all)]
#[derive(Clone, Debug)]
pub struct CapacityConstraint {
    pub channel_id: String,
    pub capacity: f64,
    pub slack_factor: f64,
    /// Flat list of (net_idx, variable_name, width) tuples.
    pub terms: Vec<(usize, String, f64)>,
}

#[pymethods]
impl CapacityConstraint {
    #[new]
    #[pyo3(signature = (name, description, channel_id, capacity, slack_factor, terms))]
    fn new(
        name: String,
        description: String,
        channel_id: String,
        capacity: f64,
        slack_factor: f64,
        terms: Vec<(usize, String, f64)>,
    ) -> (Self, Constraint) {
        (
            Self {
                channel_id,
                capacity,
                slack_factor,
                terms,
            },
            Constraint { name, description },
        )
    }
}

/// Diff pair: uses[p_net, channel] == uses[n_net, channel]
#[pyclass(extends=Constraint, get_all)]
#[derive(Clone, Debug)]
pub struct DiffPairConstraint {
    pub channel_id: String,
    pub p_net_idx: usize,
    pub n_net_idx: usize,
    pub p_var_name: String,
    pub n_var_name: String,
}

#[pymethods]
impl DiffPairConstraint {
    #[new]
    #[pyo3(signature = (name, description, channel_id, p_net_idx, n_net_idx, p_var_name, n_var_name))]
    fn new(
        name: String,
        description: String,
        channel_id: String,
        p_net_idx: usize,
        n_net_idx: usize,
        p_var_name: String,
        n_var_name: String,
    ) -> (Self, Constraint) {
        (
            Self {
                channel_id,
                p_net_idx,
                n_net_idx,
                p_var_name,
                n_var_name,
            },
            Constraint { name, description },
        )
    }
}

/// Layer restriction: uses[n, c] == allowed
#[pyclass(extends=Constraint, get_all)]
#[derive(Clone, Debug)]
pub struct LayerConstraint {
    pub net_idx: usize,
    pub channel_id: String,
    pub allowed: bool,
    pub var_name: String,
}

#[pymethods]
impl LayerConstraint {
    #[new]
    #[pyo3(signature = (name, description, net_idx, channel_id, allowed, var_name))]
    fn new(
        name: String,
        description: String,
        net_idx: usize,
        channel_id: String,
        allowed: bool,
        var_name: String,
    ) -> (Self, Constraint) {
        (
            Self {
                net_idx,
                channel_id,
                allowed,
                var_name,
            },
            Constraint { name, description },
        )
    }
}

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

#[derive(Clone, Debug)]
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
pub struct BundleClass {
    pub bundle_id: usize,
    pub net_indices: Vec<usize>,
    pub constraint_types: Vec<String>,
    pub is_diff_pair: bool,
}

#[derive(Clone, Debug)]
pub struct InternalBundleManifest {
    pub bundles: Vec<BundleClass>,
    pub bundle_id_for_net: std::collections::HashMap<usize, usize>,
    pub unbundled_net_indices: Vec<usize>,
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
pub struct TopologyResult {
    pub status: SolverStatus,
    pub num_vars: usize,
    pub num_clauses: usize,
    pub assignments: HashMap<usize, bool>,
    pub unsat_core: Vec<usize>,
    pub solver_time_ms: f64,
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
// Conversion from Python objects
// ---------------------------------------------------------------------------

/// Trait for converting Python pyclass types into internal Rust types.
pub trait IntoInternal {
    type Output;
    fn into_internal(&self) -> Self::Output;
}


// pyclass constraint model types exposed to Python.
//
// Mirrors the Python dataclasses in:
//   constraint_model.py, sat_model.py, topology_solver.py, topology_extraction.py
//
// Internal Rust-only types live in temper-rust-router-core; this file holds
// only the pyo3 pyclass wrappers.
//
// Origin: U4 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md,
// slimmed by U2 of docs/plans/2026-07-08-002-feat-router-build-unblock-plan.md

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

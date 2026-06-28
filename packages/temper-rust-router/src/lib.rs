// Router V6 topology stage — PyO3 entry point.
//
// Origin: U3/U4/U7 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

mod encoding;
mod extraction;
mod solver;
pub mod types;
mod types_py_bridge;

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use types::{
    InternalConstraintModel, SolverStatus, TopologyResult,
};

/// Python-callable entry point: solve the topology stage in Rust.
///
/// Accepts a list of variable dicts, constraint dicts, and net names
/// matching the Python `ConstraintModel` shape, and returns a dict with
/// solver status, variable assignments, and topology graph.
#[pyfunction]
fn solve_topology_rust(
    py: Python<'_>,
    variables: &Bound<'_, PyList>,
    constraints: &Bound<'_, PyList>,
    net_names: Vec<String>,
) -> PyResult<PyObject> {
    // Convert Python objects to internal model.
    let py_vars: Vec<PyObject> = variables.iter().map(|v| v.into()).collect();
    let py_cons: Vec<PyObject> = constraints.iter().map(|c| c.into()).collect();

    let model: InternalConstraintModel =
        types_py_bridge::model_from_python(net_names.clone(), py_vars, py_cons)?;

    // Encode to CNF.
    let (cnf, var_names, _cardinality_constraints) =
        encoding::encode_to_cnf(&model);

    // Solve with splr.
    let result: TopologyResult = solver::solve_with_splr(&cnf, &var_names, &model);

    // Extract topology if satisfiable.
    let topology = if result.status == SolverStatus::Satisfiable {
        extraction::extract_topology(&model, &result.assignments, &var_names, &net_names)
    } else {
        types::TopologyGraph {
            net_topologies: HashMap::new(),
        }
    };

    // Build Python return value.
    let d = PyDict::new(py);
    d.set_item(
        "status",
        match result.status {
            SolverStatus::Satisfiable => "sat",
            SolverStatus::Unsatisfiable => "unsat",
            SolverStatus::Unknown => "unknown",
        },
    )?;

    // Variable assignments: name → bool
    let py_assignments = PyDict::new(py);
    for (idx, val) in &result.assignments {
        if *idx < var_names.len() {
            py_assignments.set_item(&var_names[*idx], *val)?;
        }
    }
    d.set_item("assignments", py_assignments)?;

    // Topology graph: net_name → [channel_ids]
    let py_topology = PyDict::new(py);
    for (net_name, net_topo) in &topology.net_topologies {
        let entry = PyDict::new(py);
        entry.set_item("uses_channels", net_topo.uses_channels.clone())?;
        entry.set_item("total_length_estimate", net_topo.total_length_estimate)?;
        py_topology.set_item(net_name, entry)?;
    }
    d.set_item("topology_graph", py_topology)?;

    d.set_item("solver_time_ms", result.solver_time_ms)?;

    // Unsat core
    let py_core = PyList::empty(py);
    for idx in &result.unsat_core {
        py_core.append(idx)?;
    }
    d.set_item("unsat_core", py_core)?;

    Ok(d.into())
}

/// Python module entry point.
#[pymodule]
fn temper_rust_router(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register constraint model types.
    m.add_class::<types::Variable>()?;
    m.add_class::<types::Constraint>()?;
    m.add_class::<types::NetChannelVar>()?;
    m.add_class::<types::NetLayerVar>()?;
    m.add_class::<types::ViaVar>()?;
    m.add_class::<types::OrderVar>()?;
    m.add_class::<types::CapacityConstraint>()?;
    m.add_class::<types::DiffPairConstraint>()?;
    m.add_class::<types::LayerConstraint>()?;

    // Register the solver entry point.
    m.add_function(wrap_pyfunction!(solve_topology_rust, m)?)?;
    Ok(())
}

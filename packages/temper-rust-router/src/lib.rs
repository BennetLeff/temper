// Router V6 topology stage — PyO3 entry point.
//
// Origin: U3/U4/U7 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

pub mod audit;
mod combinator;
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

    // Encode to CNF (cardinality constraints encoded as CNF clauses).
    let (cnf, var_names) = encoding::encode_to_cnf(&model);
    let num_vars = cnf.num_vars;
    let num_clauses = cnf.clauses.len();

    // Solve with CaDiCaL via rustsat traits.
    let mut result: TopologyResult = solver::solve_with_cadical(&cnf, &var_names);
    result.num_vars = num_vars;
    result.num_clauses = num_clauses;

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

    // Topology graph: net_name → {uses_channels, path_graph, total_length_estimate}
    let py_topology = PyDict::new(py);
    for (net_name, net_topo) in &topology.net_topologies {
        let entry = PyDict::new(py);
        entry.set_item("uses_channels", net_topo.uses_channels.clone())?;
        let py_path: Vec<(String, String)> = net_topo.path_graph.clone();
        entry.set_item("path_graph", py_path)?;
        entry.set_item("total_length_estimate", net_topo.total_length_estimate)?;
        py_topology.set_item(net_name, entry)?;
    }
    d.set_item("topology_graph", py_topology)?;

    d.set_item("solver_time_ms", result.solver_time_ms)?;
    d.set_item("num_vars", result.num_vars)?;
    d.set_item("num_clauses", result.num_clauses)?;

    // Unsat core
    let py_core = PyList::empty(py);
    for idx in &result.unsat_core {
        py_core.append(idx)?;
    }
    d.set_item("unsat_core", py_core)?;

    Ok(d.into())
}

/// Audit solver output against the constraint model itself.
///
/// Validates that every CapacityConstraint, DiffPairConstraint, and
/// LayerConstraint in the input model is satisfied by the solver's
/// assignments.  Returns a list of violation dicts (empty = clean).
#[pyfunction]
fn audit_result(
    variables: &Bound<'_, PyList>,
    constraints: &Bound<'_, PyList>,
    assignments: &Bound<'_, PyDict>,
    net_names: Vec<String>,
) -> PyResult<PyObject> {
    let py_vars: Vec<PyObject> = variables.iter().map(|v| v.into()).collect();
    let py_cons: Vec<PyObject> = constraints.iter().map(|c| c.into()).collect();

    let model = types_py_bridge::model_from_python(net_names.clone(), py_vars, py_cons)?;

    // Build var_names from model
    let var_names: Vec<String> = model.variables.iter().map(|v| match v {
        types::InternalVariable::NetChannel { name, .. } => name.clone(),
        types::InternalVariable::NetLayer { name, .. } => name.clone(),
        types::InternalVariable::Via { name, .. } => name.clone(),
        types::InternalVariable::Ordering { name, .. } => name.clone(),
    }).collect();

    let name_to_idx: std::collections::HashMap<String, usize> = var_names
        .iter().enumerate().map(|(i, n)| (n.clone(), i)).collect();

    // Build assignments hashmap from Python dict
    let mut assignment_map: std::collections::HashMap<usize, bool> = std::collections::HashMap::new();
    for (py_name, py_val) in assignments.iter() {
        let name: String = py_name.extract()?;
        let val: bool = py_val.extract()?;
        if let Some(&idx) = name_to_idx.get(&name) {
            assignment_map.insert(idx, val);
        }
    }

    let result = types::TopologyResult {
        status: types::SolverStatus::Satisfiable,
        num_vars: 0,
        num_clauses: 0,
        assignments: assignment_map,
        unsat_core: Vec::new(),
        solver_time_ms: 0.0,
    };

    let violations = audit::audit_constraints(&model, &result, &var_names);

    Python::with_gil(|py| {
        let py_list = PyList::empty(py);
        for v in &violations {
            let d = PyDict::new(py);
            match v {
                audit::AuditViolation::Capacity { channel_id, max_nets, actual_count, violating_vars } => {
                    d.set_item("type", "capacity")?;
                    d.set_item("channel_id", channel_id.clone())?;
                    d.set_item("max_nets", *max_nets)?;
                    d.set_item("actual_count", *actual_count)?;
                    d.set_item("violating_vars", violating_vars.clone())?;
                }
                audit::AuditViolation::DiffPairMismatch { channel_id, p_var, n_var, p_value, n_value } => {
                    d.set_item("type", "diff_pair")?;
                    d.set_item("channel_id", channel_id.clone())?;
                    d.set_item("p_var", p_var.clone())?;
                    d.set_item("n_var", n_var.clone())?;
                    d.set_item("p_value", *p_value)?;
                    d.set_item("n_value", *n_value)?;
                }
                audit::AuditViolation::LayerViolation { var_name, expected, actual } => {
                    d.set_item("type", "layer")?;
                    d.set_item("var_name", var_name.clone())?;
                    d.set_item("expected", *expected)?;
                    d.set_item("actual", *actual)?;
                }
                audit::AuditViolation::UnexplainedUnsat => {
                    d.set_item("type", "unexplained_unsat")?;
                }
                audit::AuditViolation::NoAssignmentForVar(vname) => {
                    d.set_item("type", "no_assignment")?;
                    d.set_item("var_name", vname.clone())?;
                }
            }
            py_list.append(d)?;
        }
        Ok(py_list.into())
    })
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

    // Register the solver entry point and constraint auditor.
    m.add_function(wrap_pyfunction!(solve_topology_rust, m)?)?;
    m.add_function(wrap_pyfunction!(audit_result, m)?)?;
    Ok(())
}

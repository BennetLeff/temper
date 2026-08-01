// Router V6 topology stage — PyO3 entry point.
//
// Origin: U3/U4/U7 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

pub mod loop_extractor;
pub mod types;
mod types_py_bridge;

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use temper_rust_router_core::astar::AstarInput;
use temper_rust_router_core::types as core_types;
use temper_rust_router_core::types::{InternalConstraintModel, SolverStatus, TopologyResult};
use temper_rust_router_core::{audit, combinator, encoding, extraction, solver};

/// Python-callable entry point: solve the topology stage in Rust.
///
/// Accepts a list of variable dicts, constraint dicts, and net names
/// matching the Python `ConstraintModel` shape, and returns a dict with
/// solver status, variable assignments, and topology graph.
///
/// `conflict_limit` and `time_limit_ms` bound the CaDiCaL solve (see
/// `temper_rust_router_core::solver::SolveLimits`). Both default to
/// `None` (unbounded) at this FFI boundary -- the recommended production
/// bound is applied by the caller
/// (`RouterV6Pipeline.sat_conflict_limit` in
/// `packages/temper-placer/src/temper_placer/router_v6/_pipeline_core.py`),
/// not hard-coded here, so any other caller of this function is
/// unaffected unless it opts in.
#[pyfunction]
#[pyo3(signature = (variables, constraints, net_names, conflict_limit=None, time_limit_ms=None))]
fn solve_topology_rust(
    py: Python<'_>,
    variables: &Bound<'_, PyList>,
    constraints: &Bound<'_, PyList>,
    net_names: Vec<String>,
    conflict_limit: Option<u32>,
    time_limit_ms: Option<u64>,
) -> PyResult<Py<PyAny>> {
    // Diagnostic phase timing, enabled by TEMPER_REWRITE_TRACE (same env
    // var the rewrite engine's own instrumentation uses -- see
    // docs/evidence/2026-07-27-stage3-model-and-rewrite.md). Off by
    // default: one env::var() call, no cost otherwise.
    let phase_trace = std::env::var("TEMPER_REWRITE_TRACE").is_ok();
    let t_start = std::time::Instant::now();

    // Convert Python objects to internal model.
    let py_vars: Vec<Py<PyAny>> = variables.iter().map(|v| v.into()).collect();
    let py_cons: Vec<Py<PyAny>> = constraints.iter().map(|c| c.into()).collect();

    let model: InternalConstraintModel =
        types_py_bridge::model_from_python(py_vars, py_cons, py)?;
    if phase_trace {
        eprintln!("[phase-trace t={:.3}s] model_from_python done", t_start.elapsed().as_secs_f64());
    }

    // Apply combinator rewrite engine (RW1-RW7) to simplify the model
    // before CNF encoding.  Detects structural contradictions (RW7) pre-solve.
    //
    // TEMPER_SKIP_REWRITE bypasses this step entirely -- a measurement-only
    // escape hatch (default: unset, rewrite always runs) used to compare
    // "rewrite on" vs "rewrite off" model size / solve time. See
    // docs/evidence/2026-07-27-stage3-model-and-rewrite.md.
    let model = if std::env::var("TEMPER_SKIP_REWRITE").is_ok() {
        model
    } else {
        combinator::rewrite::rewrite(&model)
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{:?}", e)))?
    };
    if phase_trace {
        eprintln!("[phase-trace t={:.3}s] rewrite done, {} constraints", t_start.elapsed().as_secs_f64(), model.constraints.len());
    }

    // Encode to CNF (cardinality constraints encoded as CNF clauses).
    let (cnf, var_names) = encoding::encode_to_cnf(&model);
    let num_vars = cnf.num_vars;
    let num_clauses = cnf.clauses.len();
    if phase_trace {
        eprintln!("[phase-trace t={:.3}s] encode_to_cnf done, {num_vars} vars, {num_clauses} clauses", t_start.elapsed().as_secs_f64());
    }

    // Solve with CaDiCaL via rustsat traits, under the caller-supplied bound.
    let limits = solver::SolveLimits {
        conflict_limit,
        time_limit_ms,
    };
    let mut result: TopologyResult = solver::solve_with_cadical(&cnf, &var_names, limits);
    result.num_vars = num_vars;
    result.num_clauses = num_clauses;
    if phase_trace {
        eprintln!("[phase-trace t={:.3}s] solve done, status={:?}", t_start.elapsed().as_secs_f64(), result.status);
    }

    // Extract topology if satisfiable.
    let topology = if result.status == SolverStatus::Satisfiable {
        extraction::extract_topology(&model, &result.assignments, &var_names, &net_names)
    } else {
        core_types::TopologyGraph {
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
    let py_core = PyList::new(py, Vec::<Py<PyAny>>::new())?;
    for idx in &result.unsat_core {
        py_core.append(idx)?;
    }
    d.set_item("unsat_core", py_core)?;

    // Solver statistics.
    if let Some(ref stats) = result.solver_stats {
        let py_stats = PyDict::new(py);
        py_stats.set_item("conflicts", stats.conflicts)?;
        py_stats.set_item("decisions", stats.decisions)?;
        py_stats.set_item("propagations", stats.propagations)?;
        py_stats.set_item("decision_level_histogram",
            stats.decision_level_histogram.to_vec())?;
        py_stats.set_item("unsat_core_size", stats.unsat_core_size)?;
        py_stats.set_item("variable_count", stats.variable_count)?;
        py_stats.set_item("clause_count", stats.clause_count)?;
        py_stats.set_item("cpu_solve_time_ms", stats.cpu_solve_time_ms)?;
        let clause_to_var_ratio = if stats.variable_count > 0 {
            stats.clause_count as f64 / stats.variable_count as f64
        } else {
            0.0
        };
        py_stats.set_item("clause_to_var_ratio", clause_to_var_ratio)?;
        let solve_throughput = if stats.cpu_solve_time_ms > 0.001 {
            (stats.variable_count * stats.clause_count) as f64 / stats.cpu_solve_time_ms
        } else {
            0.0
        };
        py_stats.set_item("solve_throughput", solve_throughput)?;
        d.set_item("solver_stats", py_stats)?;
    }

    // Var-to-net mapping.
    d.set_item("var_to_net", cnf.var_to_net.clone())?;

    Ok(d.into())
}

/// Audit solver output against the constraint model itself.
///
/// Validates that every CapacityConstraint, DiffPairConstraint, and
/// LayerConstraint in the input model is satisfied by the solver's
/// assignments.  Returns a list of violation dicts (empty = clean).
#[pyfunction]
fn audit_result(
    py: Python<'_>,
    variables: &Bound<'_, PyList>,
    constraints: &Bound<'_, PyList>,
    assignments: &Bound<'_, PyDict>,
    _net_names: Vec<String>,
) -> PyResult<Py<PyAny>> {
    let py_vars: Vec<Py<PyAny>> = variables.iter().map(|v| v.into()).collect();
    let py_cons: Vec<Py<PyAny>> = constraints.iter().map(|c| c.into()).collect();

    let model = types_py_bridge::model_from_python(py_vars, py_cons, py)?;

    // Build var_names from model
    let var_names: Vec<String> = model.variables.iter().map(|v| match v {
        core_types::InternalVariable::NetChannel { name, .. } => name.clone(),
        core_types::InternalVariable::NetLayer { name, .. } => name.clone(),
        core_types::InternalVariable::Via { name, .. } => name.clone(),
        core_types::InternalVariable::Ordering { name, .. } => name.clone(),
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

    let result = core_types::TopologyResult {
        status: core_types::SolverStatus::Satisfiable,
        num_vars: 0,
        num_clauses: 0,
        assignments: assignment_map,
        unsat_core: Vec::new(),
        solver_time_ms: 0.0,
        solver_stats: None,
    };

    let violations = audit::audit_constraints(&model, &result, &var_names);

    let py_list = PyList::new(py, Vec::<Py<PyAny>>::new())?;
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
    m.add_function(wrap_pyfunction!(auto_extract_loops_rust, m)?)?;
    m.add_function(wrap_pyfunction!(astar_kernel_3d_py, m)?)?;
    m.add_function(wrap_pyfunction!(line_of_sight_py, m)?)?;
    Ok(())
}

/// Python-callable A* kernel (U5) — the Rust port of the retired JIT
/// kernel (`_astar_kernel_3d`). Inputs mirror the retired kernel's
/// arguments; congestion/thermal fields are passed as little-
/// endian float32 byte buffers (None = absent). Returns (path, iterations).
#[pyfunction]
#[pyo3(signature = (
    start_idx, goal_idx, rows, cols, validity_bytes, max_iterations,
    congestion_bytes=None, congestion_weight=1.0, max_congestion_cost=100.0,
    thermal_bytes=None, thermal_weight=0.0,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
fn astar_kernel_3d_py(
    start_idx: i64,
    goal_idx: i64,
    rows: usize,
    cols: usize,
    validity_bytes: Vec<u8>,
    max_iterations: u64,
    congestion_bytes: Option<Vec<u8>>,
    congestion_weight: f32,
    max_congestion_cost: f32,
    thermal_bytes: Option<Vec<u8>>,
    thermal_weight: f32,
) -> (Vec<i32>, u64) {
    let n_cells = rows * cols;
    let congestion = congestion_bytes.map(|b| f32s_from_le_bytes(&b, n_cells));
    let thermal = thermal_bytes.map(|b| f32s_from_le_bytes(&b, n_cells));
    let out = temper_rust_router_core::astar::astar_kernel_3d(&AstarInput {
        start_idx,
        goal_idx,
        rows,
        cols,
        validity: &validity_bytes,
        max_iterations,
        congestion: congestion.as_deref(),
        congestion_weight,
        max_congestion_cost,
        thermal: thermal.as_deref(),
        thermal_weight,
    });
    (out.path, out.iterations)
}

/// Python-callable Bresenham line-of-sight check (U5) — the Rust port of
/// the retired JIT LOS kernel. `grid_bytes` is a
/// row-major (height, width) int8 occupancy grid.
#[pyfunction]
#[pyo3(signature = (x0, y0, x1, y1, grid_bytes, width_cells, height_cells, net_id))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
fn line_of_sight_py(
    x0: i64,
    y0: i64,
    x1: i64,
    y1: i64,
    grid_bytes: Vec<u8>,
    width_cells: i64,
    height_cells: i64,
    net_id: i64,
) -> bool {
    let grid = &grid_bytes;
    let (w, h) = (width_cells, height_cells);
    let (mut x, mut y) = (x0, y0);
    let (dx, dy) = ((x1 - x0).abs(), (y1 - y0).abs());
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx - dy;
    loop {
        if x < 0 || x >= w || y < 0 || y >= h {
            return false;
        }
        let cell = grid.get((y * w + x) as usize).copied().unwrap_or(1) as i64;
        if cell != 0 && cell != net_id {
            return false;
        }
        if x == x1 && y == y1 {
            return true;
        }
        let e2 = 2 * err;
        if e2 > -dy {
            err -= dy;
            x += sx;
        }
        if e2 < dx {
            err += dx;
            y += sy;
        }
    }
}

fn f32s_from_le_bytes(bytes: &[u8], expected: usize) -> Vec<f32> {
    debug_assert_eq!(bytes.len() % 4, 0);
    let mut out = Vec::with_capacity(bytes.len() / 4);
    for c in bytes.chunks_exact(4) {
        let mut buf = [0u8; 4];
        buf.copy_from_slice(c);
        out.push(f32::from_le_bytes(buf));
    }
    debug_assert!(expected == 0 || out.len() == expected);
    out
}

/// Python-callable entry point for loop extraction via JSON.
#[pyfunction]
fn auto_extract_loops_rust(
    py: Python<'_>,
    json_str: &str,
) -> PyResult<String> {
    crate::loop_extractor::bridge::auto_extract_loops_rust(py, json_str)
}

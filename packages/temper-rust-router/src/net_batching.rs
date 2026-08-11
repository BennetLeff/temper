//! Phase E batch E5: pyo3 surface for the net-batching batch-loop
//! orchestration primitives.
//!
//! Rust Orchestration Engine plan 2026-08-09-001 Phase E E5 — the PORTABLE
//! batch-loop orchestration of
//! `packages/temper-placer/src/temper_placer/router_v6/net_batching.py`
//! (net grouping, batch construction, budget/capacity accounting) moves to
//! `temper_rust_router_core::net_batching` (pure logic, no pyo3); these
//! functions are the thin FFI delegation surface the Python shim binds.  See
//! the core module docstring for the E5 boundary argument (what stays
//! Python: the subprocess driver, the solve dispatch into Python-only
//! routing glue, `run_net_batched_stage3`, and the evidence records) and for
//! the ported CPython semantics (float `==` key matching, accumulation
//! order, the `max(1, size)` chunk floor).
//!
//! The functions are deliberately NOT Python public API: the Python shim's
//! public names (`order_nets_for_batching`, `_chunks`,
//! `_shrink_channel_widths`, `_consume_capacity`) are unchanged; these are
//! the migration-convention internal entry points the shim delegates to.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use temper_rust_router_core::net_batching::{self as core};

/// One marshalled channel edge: `(u, v, width)` where `u`/`v` are
/// `(x, y)` float tuples (the `edge_widths` dict key + value, flattened).
type EdgeList = Vec<((f64, f64), (f64, f64), f64)>;

/// All of one layer's edges: `(layer_name, EdgeList)`.
type LayerEdges = Vec<(String, EdgeList)>;

/// One `edge_id -> (layer_name, u, v)` lookup row.
type EdgeLookupRow = (String, String, (f64, f64), (f64, f64));

/// `net_batching.order_nets_for_batching` — net grouping.
///
/// `net_names` / `pin_counts` / `hub_flags` are parallel arrays (the shim
/// computes `pin_counts` and `hub_flags` Python-side from `Net.pins` and the
/// raw-PCB `ref_to_block` map); `diff_pairs` is `[(p_net, n_net), ...]` in
/// `infer_differential_pairs` order.  Returns the net-index batching order.
///
/// Raises `ValueError` where the oracle's unprotected `order.index(p_i)`
/// would (only reachable for a degenerate duplicate-net-name input; the
/// error string mirrors CPython's `list.index(x): x not in list` text).
#[pyfunction]
fn net_batch_order_py(
    net_names: Vec<String>,
    pin_counts: Vec<usize>,
    hub_flags: Vec<bool>,
    diff_pairs: Vec<(String, String)>,
) -> PyResult<Vec<usize>> {
    core::order_nets(&net_names, &pin_counts, &hub_flags, &diff_pairs)
        .map_err(PyValueError::new_err)
}

/// `net_batching._chunks` — batch construction.
///
/// `range(0, len(seq), max(1, size))` slicing; `size <= 0` steps by 1.
#[pyfunction]
fn chunk_indices_py(order: Vec<usize>, batch_size: isize) -> Vec<Vec<usize>> {
    core::chunk_indices(&order, batch_size)
}

/// `net_batching._shrink_channel_widths` — budget accounting.
///
/// `layers` is the `channel_widths` dict's `edge_widths`, marshalled in
/// iteration order; `consumed` is the ordered `[(edge_id, amount), ...]`;
/// `edge_lookup` is `[(edge_id, layer_name, u, v), ...]`.  Returns, in
/// `layers` order, only the layers carrying a consumption delta; the shim
/// re-wraps them into fresh `ChannelWidths` dataclasses.
#[pyfunction]
fn shrink_channel_widths_py(
    layers: LayerEdges,
    consumed: Vec<(String, f64)>,
    edge_lookup: Vec<EdgeLookupRow>,
) -> Vec<(String, EdgeList)> {
    core::shrink_channel_widths(&layers, &consumed, &edge_lookup)
}

/// `net_batching._consume_capacity` — budget accounting.
///
/// `net_widths` is `[(net_name, trace_width_mm + clearance_mm), ...]`; the
/// shim computes the widths from `design_rules.get_rules_for_net` and
/// filters `topology` to the batch's `nets_subset`.  Returns the resulting
/// `consumed` dict, in final Python-dict order; the shim applies it with
/// `clear()` + `update()` (object identity preserved for the batch loop).
#[pyfunction]
fn consume_capacity_py(
    net_widths: Vec<(String, f64)>,
    topology: Vec<(String, Vec<String>)>,
    current_consumed: Vec<(String, f64)>,
) -> Vec<(String, f64)> {
    core::consume_capacity(&net_widths, &topology, &current_consumed)
}

/// Register the net-batching pyfunctions on the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(net_batch_order_py, m)?)?;
    m.add_function(wrap_pyfunction!(chunk_indices_py, m)?)?;
    m.add_function(wrap_pyfunction!(shrink_channel_widths_py, m)?)?;
    m.add_function(wrap_pyfunction!(consume_capacity_py, m)?)?;
    Ok(())
}

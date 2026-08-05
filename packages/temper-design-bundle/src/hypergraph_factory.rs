//! PhysicsHypergraph factory — the Wave 4 Phase 4 leftovers slice's
//! `extraction/hypergraph_factory.py` migration.
//!
//! Python reference: `temper_placer/extraction/hypergraph_factory.py`,
//! pinned VERBATIM in
//! `packages/temper-placer/tests/core/_hypergraph_factory_py_oracle.py`
//! (commit `58b302ce8`). The pyo3 pyclasses here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/core/test_hypergraph_factory_rust_differential.py`
//! is the TDD oracle for this file, and the property suite
//! `test_hypergraph_factory_pbt.py` asserts the closed-form invariants
//! independently.
//!
//! Home crate: `temper-design-bundle` — the factory consumes the `Netlist`
//! contract pyclasses (`netlist_contracts.rs`), so the netlist reader and
//! the factory share one crate.
//!
//! ## The KTD9 boundaries (kept Python-side, argued in-source)
//!
//! 1. **scipy**: `coo_matrix((values, (rows, cols)), shape=...)` stays in
//!    the Python shim. scipy's COO construction (duplicate-coordinate
//!    handling, dtype validation, empty-matrix semantics) is a library
//!    semantic, not portable compute.
//! 2. **numpy casts**: every `np.array(..., dtype=np.float32)` stays in
//!    the shim, so int-vs-float leaves convert with numpy's own semantics
//!    (an int `weight=7` reaches numpy as the original Python int, never
//!    through a Rust f64 that would round it).
//! 3. **CPython `set` iteration order**: the oracle's COO triplet ORDER
//!    per net is CPython's small-int set iteration. The Rust side returns
//!    each net's connected component indices in PIN ORDER; the shim builds
//!    `set(connected_indices)` — the identical construction the oracle
//!    performed (same members, same insertion order) — so iteration order,
//!    and therefore the triplet order, is CPython's on both sides.
//! 4. **value arithmetic**: `width * height` (the node weights) is
//!    computed by Python's `__mul__` on the original objects (int × int
//!    stays int), and `max_current`/`weight` pass through as Python
//!    objects — the Rust side never converts them.
//!
//! ## What the Rust side owns (the "hypergraph construction" compute)
//!
//! The valid-nets filter (global-net threshold + the >= 2-pin rule), the
//! ref → index mapping, the HV/width/current physics classification with
//! the oracle's branch order, the per-net connected-index lists in pin
//! order, and the ordered collection of node refs/weights, hyperedge
//! names/weights, and the edge physics arrays.
//!
//! ## Known, documented deviations (see `VERIFICATION.md`)
//!
//! - Component refs and net-pin refs must be `str` (the netlist contract's
//!   `ref` field is a str; every in-repo netlist uses str refs). A
//!   non-str ref raises a pyo3 extraction `TypeError` where the oracle
//!   would hash the object.
//! - `HypergraphFactory` (the Python shim class) remains Python — it owns
//!   the scipy/numpy assembly; the pyclass here is the builder underneath.

use std::collections::HashMap;

use pyo3::basic::CompareOp;
use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::netlist_contracts::unpack2;

// ---------------------------------------------------------------------------
// HypergraphBuildResult — the ordered extraction output the Python shim
// assembles into the scipy COO matrix and the PhysicsHypergraph.
// ---------------------------------------------------------------------------

/// The factory's ordered output (see the module docstring for the split).
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct HypergraphBuildResult {
    #[pyo3(get)]
    pub n_nodes: usize,
    #[pyo3(get)]
    pub n_edges: usize,
    /// Component refs, in component order (original objects, type-preserved).
    #[pyo3(get)]
    pub node_refs: Py<PyAny>,
    /// Valid-net names, in valid-net order (original objects).
    #[pyo3(get)]
    pub hyperedge_names: Py<PyAny>,
    /// 1.0 / 0.0 per valid net (HV flag).
    #[pyo3(get)]
    pub edge_voltages: Py<PyAny>,
    /// Per-valid-net max_current, passthrough (original objects).
    #[pyo3(get)]
    pub edge_currents: Py<PyAny>,
    /// 1.0 / 0.5 / 0.2 per valid net (width classification).
    #[pyo3(get)]
    pub edge_widths: Py<PyAny>,
    /// Per-component width*height, computed by Python `__mul__`.
    #[pyo3(get)]
    pub node_weights: Py<PyAny>,
    /// Per-valid-net weight, passthrough (original objects).
    #[pyo3(get)]
    pub hyperedge_weights: Py<PyAny>,
    /// Per-valid-net connected component indices, in PIN ORDER (duplicates
    /// possible — the shim's `set(...)` collapses them with CPython's own
    /// iteration order).
    #[pyo3(get)]
    pub connected_indices: Py<PyAny>,
}

// ---------------------------------------------------------------------------
// HypergraphFactory — the builder.
// ---------------------------------------------------------------------------

/// Builder for PhysicsHypergraph (mirrors `HypergraphFactory` in
/// `temper_placer/extraction/hypergraph_factory.py`).
// `dict`: the oracle class carries a `__dict__`; pyclass(dict) keeps
// attribute injection working.
#[pyclass(dict, module = "temper_design_bundle_python")]
#[derive(Debug)]
pub struct HypergraphFactory {
    #[pyo3(get, set)]
    pub netlist: Py<PyAny>,
    #[pyo3(get, set)]
    pub ignore_global_nets: bool,
    #[pyo3(get, set)]
    pub global_net_threshold: i64,
}

#[pymethods]
impl HypergraphFactory {
    #[new]
    #[pyo3(signature = (netlist, ignore_global_nets=false, global_net_threshold=50))]
    fn new(
        netlist: &Bound<'_, PyAny>,
        ignore_global_nets: bool,
        global_net_threshold: i64,
    ) -> PyResult<Self> {
        Ok(Self {
            netlist: netlist.clone().unbind(),
            ignore_global_nets,
            global_net_threshold,
        })
    }

    /// Build and return the extraction result the Python shim assembles
    /// into a PhysicsHypergraph (see the module docstring for the split).
    fn build<'py>(&self, py: Python<'py>) -> PyResult<Py<HypergraphBuildResult>> {
        let netlist = self.netlist.bind(py);
        let components = netlist.getattr("components")?;
        let n_nodes = components.len()?;

        // node_ref_to_idx = {c.ref: i for i, c in enumerate(components)} —
        // last duplicate ref wins, exactly like the dict comprehension.
        let mut ref_to_idx: HashMap<String, usize> = HashMap::with_capacity(n_nodes);
        let mut node_refs = Vec::with_capacity(n_nodes);
        let mut node_weights = Vec::with_capacity(n_nodes);
        for (i, comp) in components.try_iter()?.enumerate() {
            let comp = comp?;
            let r#ref = comp.getattr("ref")?;
            node_refs.push(r#ref.clone().unbind());
            let ref_str: String = r#ref.extract()?; // str-ref envelope (documented)
            ref_to_idx.insert(ref_str, i);
            // c.width * c.height — Python's own multiply (int × int stays
            // int; the float32 cast happens numpy-side in the shim).
            let width = comp.getattr("width")?;
            let height = comp.getattr("height")?;
            node_weights.push(width.call_method1("__mul__", (height,))?.unbind());
        }

        // 1. Collect valid edges (Nets).
        let nets = netlist.getattr("nets")?;
        let net_list: Vec<Bound<'py, PyAny>> = nets.try_iter()?.collect::<PyResult<_>>()?;
        let mut valid_indices: Vec<usize> = Vec::new();
        for (i, net) in net_list.iter().enumerate() {
            let n_pins = net.getattr("pins")?.len()?;
            if self.ignore_global_nets && n_pins > self.global_net_threshold as usize {
                continue;
            }
            if n_pins >= 2 {
                valid_indices.push(i);
            }
        }
        let n_edges = valid_indices.len();

        // 2. Physics extraction + connections, in valid-net order.
        let mut edge_voltages: Vec<f64> = Vec::with_capacity(n_edges);
        let mut edge_currents: Vec<Py<PyAny>> = Vec::with_capacity(n_edges);
        let mut edge_widths: Vec<f64> = Vec::with_capacity(n_edges);
        let mut hyperedge_names: Vec<Py<PyAny>> = Vec::with_capacity(n_edges);
        let mut hyperedge_weights: Vec<Py<PyAny>> = Vec::with_capacity(n_edges);
        let mut connected: Vec<Vec<usize>> = Vec::with_capacity(n_edges);

        for net_idx in &valid_indices {
            let net = &net_list[*net_idx];
            // is_hv = 1.0 if net.voltage_class == "HV" or
            //                net.net_class == "HighVoltage" else 0.0
            let voltage_class = net.getattr("voltage_class")?;
            let net_class = net.getattr("net_class")?;
            let is_hv = voltage_class.eq("HV")? || net_class.eq("HighVoltage")?;
            edge_voltages.push(if is_hv { 1.0 } else { 0.0 });

            let max_current = net.getattr("max_current")?;
            edge_currents.push(max_current.clone().unbind());

            // Default width: net_class HighVoltage first, then current.
            let width = if net_class.eq("HighVoltage")? {
                1.0
            } else if max_current.rich_compare(1.0, CompareOp::Gt)?.is_truthy()? {
                0.5
            } else {
                0.2
            };
            edge_widths.push(width);

            // Connections: `for comp_ref, _ in net.pins` with the ref→idx
            // membership check, in PIN ORDER (the set collapse happens
            // Python-side — the shim builds the identical set).
            let pins = net.getattr("pins")?;
            let mut conn: Vec<usize> = Vec::new();
            for item in pins.try_iter()? {
                let item = item?;
                let (comp_ref, _pin_name) = unpack2(&item)?;
                let comp_ref_str: String = comp_ref.extract()?; // str-ref envelope
                if let Some(&node_idx) = ref_to_idx.get(&comp_ref_str) {
                    conn.push(node_idx);
                }
            }
            connected.push(conn);

            hyperedge_weights.push(net.getattr("weight")?.unbind());
            hyperedge_names.push(net.getattr("name")?.unbind());
        }

        // 3. Assemble the result pyclass (plain Python lists — the shim
        //    applies numpy's casts and scipy's COO construction).
        let make_list = |py: Python<'py>, items: Vec<Py<PyAny>>| -> PyResult<Py<PyAny>> {
            let list = PyList::new(py, items.iter().map(|v| v.bind(py)))?;
            Ok(list.into_any().unbind())
        };
        let connected_list = PyList::empty(py);
        for conn in &connected {
            connected_list.append(PyList::new(py, conn)?.into_any())?;
        }

        Py::new(
            py,
            HypergraphBuildResult {
                n_nodes,
                n_edges,
                node_refs: make_list(py, node_refs)?,
                hyperedge_names: make_list(py, hyperedge_names)?,
                edge_voltages: PyList::new(py, edge_voltages)?.into_any().unbind(),
                edge_currents: make_list(py, edge_currents)?,
                edge_widths: PyList::new(py, edge_widths)?.into_any().unbind(),
                node_weights: make_list(py, node_weights)?,
                hyperedge_weights: make_list(py, hyperedge_weights)?,
                connected_indices: connected_list.into_any().unbind(),
            },
        )
    }
}

// ---------------------------------------------------------------------------
// Registration.
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<HypergraphFactory>()?;
    module.add_class::<HypergraphBuildResult>()?;
    Ok(())
}

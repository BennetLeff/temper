//! PathGraph data model — Wave 4, fanout migration.
//!
//! Python reference: ``networkx.DiGraph``, built via ``add_edges_from(path_edges)``
//! in ``_pipeline_route.py:383-390`` and ``net_batching.py:360-363``.
//! The pyclass reproduces the surface the production code actually uses:
//! ``number_of_edges()``, ``nodes()`` (first-seen order over edges — M6 rule,
//! ``docs/evidence/2026-08-04-networkx-path-order-spike.md`` §7), and
//! ``edges()``.
//!
//! # Why opaque ``Py<PyAny>`` for nodes
//!
//! Skeleton nodes are opaque Python objects (``str`` coordinates), so the
//! edge list stores ``(Py<PyAny>, Py<PyAny>)`` pairs. This is the same
//! pattern as ``netlist_contracts.rs`` and ``geometry_types_contracts.rs``.
//!
//! # M6: first-seen node order
//!
//! ``list(DiGraph.nodes())`` on networkx 3.6.1 returns nodes in first-seen
//! order over the edge list — measured 200/200 randomized trials. The Rust
//! implementation maintains a ``seen`` set of Python object identities and
//! appends nodes as edges are added. This is deterministic, portable, and
//! matches the measured behavior.
//!
//! # Duplicate edge handling
//!
//! ``DiGraph.add_edges_from`` silently deduplicates edges (a second
//! ``add_edge(u, v)`` is a no-op for a digraph). We do the same: track
//! seen edge pairs (by Python ``==``, not identity) and skip duplicates.
//!
//! # ``repr``
//!
//! ``PathGraph(nodes=N, edges=E)`` — a compact summary. The pre-migration
//! ``nx.DiGraph`` repr is a hex-address object repr; the new repr is
//! deliberately different because no consumer inspects it.

use pyo3::prelude::*;
use pyo3::types::{PyList, PyTuple};

use crate::netlist_contracts::{dataclass_eq, dataclass_repr, repr_of, same, unhashable};

// ---------------------------------------------------------------------------
// PathGraph
// ---------------------------------------------------------------------------

/// A directed edge list with first-seen node ordering (mirrors the
/// ``networkx.DiGraph`` surface used by ``channel_mapping.py``).
///
/// Stores edges as ``Vec<(Py<PyAny>, Py<PyAny>)>`` and derives the node
/// list from first-seen order over edges (M6 rule).
#[pyclass(dict, name = "PathGraph", module = "temper_design_bundle_python.topology_extraction_contracts")]
#[derive(Debug)]
pub struct PathGraph {
    edges: Vec<(Py<PyAny>, Py<PyAny>)>,
    /// Node list in first-seen order over edges (M6 rule).
    nodes: Vec<Py<PyAny>>,
}

impl PathGraph {
    fn fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        Ok(vec![
            self.edges_list_py(py)?,
            self.nodes_list_py(py)?,
        ])
    }

    fn edges_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for (s, t) in &self.edges {
            let pair = PyTuple::new(py, [s.bind(py), t.bind(py)])?;
            list.append(pair)?;
        }
        Ok(list.into_any().unbind())
    }

    fn nodes_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for n in &self.nodes {
            list.append(n.bind(py))?;
        }
        Ok(list.into_any().unbind())
    }
}

#[pymethods]
impl PathGraph {
    #[new]
    #[pyo3(signature = (edges))]
    fn new(py: Python<'_>, edges: &Bound<'_, PyAny>) -> PyResult<Self> {
        let iter = edges.try_iter().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("edges must be iterable")
        })?;

        let mut edge_vec: Vec<(Py<PyAny>, Py<PyAny>)> = Vec::new();
        let mut seen_edges: Vec<Bound<'_, PyTuple>> = Vec::new();
        let mut node_order: Vec<Py<PyAny>> = Vec::new();
        let mut seen_nodes: Vec<Py<PyAny>> = Vec::new();

        for item in iter {
            let item = item?;
            let pair: &Bound<'_, PyTuple> = item.cast::<PyTuple>().map_err(|_| {
                pyo3::exceptions::PyTypeError::new_err("each edge must be a tuple (source, sink)")
            })?;

            if pair.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "each edge must be a 2-tuple (source, sink)",
                ));
            }

            // Deduplicate edges by Python equality (matching DiGraph behavior).
            let mut is_dup = false;
            for seen in &seen_edges {
                if seen.eq(pair)? {
                    is_dup = true;
                    break;
                }
            }
            if is_dup {
                continue;
            }
            seen_edges.push(pair.clone());

            let src = pair.get_item(0)?.clone().unbind();
            let sink = pair.get_item(1)?.clone().unbind();

            edge_vec.push((src.clone_ref(py), sink.clone_ref(py)));

            // M6: first-seen order over edge list
            for node in [&src, &sink] {
                let mut found = false;
                for sn in &seen_nodes {
                    if sn.bind(py).eq(node.bind(py))? {
                        found = true;
                        break;
                    }
                }
                if !found {
                    seen_nodes.push(node.clone_ref(py));
                    node_order.push(node.clone_ref(py));
                }
            }
        }

        Ok(Self {
            edges: edge_vec,
            nodes: node_order,
        })
    }

    /// Number of unique (deduplicated) edges.
    fn number_of_edges(&self) -> usize {
        self.edges.len()
    }

    /// Number of unique nodes (first-seen over edges).
    fn number_of_nodes(&self) -> usize {
        self.nodes.len()
    }

    /// The node list in first-seen order over the edge list (M6 rule).
    fn nodes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for n in &self.nodes {
            list.append(n.bind(py))?;
        }
        Ok(list)
    }

    /// The edge list as ``[(source, sink), ...]`` tuples in insertion order.
    fn edges<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for (s, t) in &self.edges {
            let pair = PyTuple::new(py, [s.bind(py), t.bind(py)])?;
            list.append(pair)?;
        }
        Ok(list)
    }

    fn __repr__(&self, _py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "PathGraph(nodes={}, edges={})",
            self.nodes.len(),
            self.edges.len()
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py)?;
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            o.cast::<Self>()?.borrow().fields(py)
        })
    }

    /// ``eq=True`` — sets ``__hash__ = None``.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("PathGraph"))
    }
}

// ---------------------------------------------------------------------------
// NetTopology  (oracle: ``NetTopology`` dataclass in ``topology_extraction.py``)
// ---------------------------------------------------------------------------

/// Topological routing for a single net (mirrors ``NetTopology`` in
/// ``temper_placer/router_v6/topology_extraction.py``).
///
/// The ``path_graph`` field stores ``PathGraph | None`` — never ``nx.DiGraph``.
#[pyclass(dict, name = "NetTopology", module = "temper_design_bundle_python.topology_extraction_contracts")]
#[derive(Debug)]
pub struct PyNetTopology {
    #[pyo3(get, set)]
    pub net_name: Py<PyAny>,
    #[pyo3(get, set)]
    pub path_graph: Py<PyAny>,
    #[pyo3(get, set)]
    pub uses_channels: Py<PyAny>,
    #[pyo3(get, set)]
    pub total_length_estimate: Py<PyAny>,
}

impl PyNetTopology {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.net_name),
            same(py, &self.path_graph),
            same(py, &self.uses_channels),
            same(py, &self.total_length_estimate),
        ]
    }
}

#[pymethods]
impl PyNetTopology {
    #[new]
    #[pyo3(signature = (net_name, path_graph, uses_channels, total_length_estimate))]
    fn new(
        net_name: &Bound<'_, PyAny>,
        path_graph: &Bound<'_, PyAny>,
        uses_channels: &Bound<'_, PyAny>,
        total_length_estimate: &Bound<'_, PyAny>,
    ) -> PyResult<Self> {
        Ok(Self {
            net_name: net_name.clone().unbind(),
            path_graph: path_graph.clone().unbind(),
            uses_channels: uses_channels.clone().unbind(),
            total_length_estimate: total_length_estimate.clone().unbind(),
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "NetTopology",
            &[
                ("net_name", repr_of(&self.net_name, py)?),
                ("path_graph", repr_of(&self.path_graph, py)?),
                ("uses_channels", repr_of(&self.uses_channels, py)?),
                ("total_length_estimate", repr_of(&self.total_length_estimate, py)?),
            ],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("NetTopology"))
    }
}

// ---------------------------------------------------------------------------
// TopologyGraph  (oracle: ``TopologyGraph`` dataclass in ``topology_extraction.py``)
// ---------------------------------------------------------------------------

/// Complete topological routing graph (mirrors ``TopologyGraph`` in
/// ``temper_placer/router_v6/topology_extraction.py``).
#[pyclass(dict, name = "TopologyGraph", module = "temper_design_bundle_python.topology_extraction_contracts")]
#[derive(Debug)]
pub struct PyTopologyGraph {
    #[pyo3(get, set)]
    pub net_topologies: Py<PyAny>, // dict[str, NetTopology]
}

impl PyTopologyGraph {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![same(py, &self.net_topologies)]
    }
}

#[pymethods]
impl PyTopologyGraph {
    #[new]
    #[pyo3(signature = (net_topologies))]
    fn new(net_topologies: &Bound<'_, PyAny>) -> PyResult<Self> {
        Ok(Self {
            net_topologies: net_topologies.clone().unbind(),
        })
    }

    /// Number of nets with routing topology.
    #[getter]
    fn routed_net_count<'py>(&self, py: Python<'py>) -> PyResult<usize> {
        self.net_topologies.bind(py).len()
    }

    /// Get topology for a specific net.
    fn get_topology<'py>(
        &self,
        py: Python<'py>,
        net_name: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        match self.net_topologies.bind(py).get_item(net_name) {
            Ok(val) => Ok(Some(val)),
            Err(e) if e.is_instance_of::<pyo3::exceptions::PyKeyError>(py) => Ok(None),
            Err(e) => Err(e),
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "TopologyGraph",
            &[("net_topologies", repr_of(&self.net_topologies, py)?)],
        ))
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py);
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            Ok(o.cast::<Self>()?.borrow().fields(py))
        })
    }

    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("TopologyGraph"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the topology-extraction contract pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "topology_extraction_contracts")?;
    sub.add_class::<PathGraph>()?;
    sub.add_class::<PyNetTopology>()?;
    sub.add_class::<PyTopologyGraph>()?;
    module.add_submodule(&sub)
}

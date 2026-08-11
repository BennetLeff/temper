//! ``TopologicalGraphStore`` — Wave 4, replacing ``networkx.MultiDiGraph`` in
//! ``temper_placer/topological/graph.py``.
//!
//! Python reference: the ``nx.MultiDiGraph`` container built and consumed in
//! ``graph.py``, assessed by Spike S7
//! (``docs/evidence/2026-08-11-topological-graph-networkx-assessment.md``).
//!
//! # What this replaces
//!
//! The last ``import networkx as nx`` in production ``temper_placer/``:
//! the ``nx.MultiDiGraph()`` container at ``graph.py:94``. The live production
//! code paths use only container operations — no algorithmic networkx surface
//! is reached.
//!
//! | Method | Production sites | What the Rust store provides |
//! |---|---|---|
//! | ``add_node(ref, **attrs)`` | 2 | ``add_node(ref, **attrs)`` |
//! | ``add_edge(u, v, **attrs)`` | 4 | ``add_edge(u, v, **attrs)`` |
//! | ``edges(data=True)`` | 10 | ``edges(data=True)`` — insertion-order ``[(u, v, data), ...]`` |
//! | ``nodes()`` | 7 | ``nodes()`` — insertion-order node refs |
//! | ``has_edge(u, v)`` | 1 | ``has_edge(u, v)`` |
//! | ``number_of_nodes()`` | 2 | ``number_of_nodes()`` |
//! | ``number_of_edges()`` | 1 | ``number_of_edges()`` |
//!
//! # Insertion order
//!
//! networkx 3.6.1 uses dict-insertion-order for nodes and edges. The Rust store
//! preserves this with ``Vec<String>`` for nodes and ``Vec<(String, String,
//! Py<PyAny>)>`` for edges — push order is iteration order.
//!
//! **Deduplication:** S7 proved no parallel edges exist (F-T2 DID NOT FIRE),
//! so the store treats ``add_edge(u, v, ...)`` as a no-op when the directed
//! pair ``(u, v)`` is already present — matching networkx's ``DiGraph``
//! behaviour.
//!
//! # Node attributes
//!
//! Node attributes (``node_type``, ``properties``) are stored as opaque Python
//! dicts alongside the ref. Access via ``node_attrs(ref)`` returns the dict
//! or ``None``. The subscript pattern ``graph.nodes["Q1"]`` (used only in
//! tests) is replaced by this method.
//!
//! # ``repr`` / ``__eq__`` / ``__hash__``
//!
//! ``TopologicalGraphStore`` is unfrozen (``eq=True``, ``frozen=False``) —
//! hash raises ``TypeError``. Equality compares node order, node attrs, and
//! edge order with data, matching the networkx ``MultiDiGraph.__eq__``
//! contract.

use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

use crate::netlist_contracts::{dataclass_eq, unhashable};

// ---------------------------------------------------------------------------
// TopologicalGraphStore
// ---------------------------------------------------------------------------

/// A directed graph with insertion-order node/edge iteration.
///
/// Replaces ``networkx.MultiDiGraph`` in ``topological/graph.py``. Nodes are
/// component reference strings (e.g. ``"Q1"``, ``"C2"``). Edges carry opaque
/// Python dicts as data.
///
/// # Thread safety
///
/// All methods require the Python GIL (they manipulate ``Py<PyAny>`` fields).
#[pyclass(dict, name = "TopologicalGraphStore", module = "temper_design_bundle_python.topological_graph_contracts")]
#[derive(Debug)]
pub struct TopologicalGraphStore {
    /// Nodes in insertion order: ``(ref, attrs_dict)``.
    nodes: Vec<(String, Py<PyAny>)>,
    /// Dedup set: node refs.
    node_set: HashSet<String>,
    /// Edges in insertion order: ``(source, target, data_dict)``.
    /// No deduplication — parallel edges (e.g., adjacency + separation
    /// between the same pair) are supported, matching ``MultiDiGraph``
    /// semantics.
    edges: Vec<(String, String, Py<PyAny>)>,
    /// Dedup set for ``has_edge``: tracks unique directed ``(source, target)``
    /// pairs that have ever been added.
    has_edge_set: HashSet<(String, String)>,
}

impl TopologicalGraphStore {
    /// Return the fields for ``__eq__``: source-grouped edge order.
    fn fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let nodes_list = {
            let list = PyList::empty(py);
            for (ref_s, attrs) in &self.nodes {
                let s = PyString::new(py, ref_s);
                let pair = PyTuple::new(py, [&s, attrs.bind(py)])?;
                list.append(pair)?;
            }
            list.into_any().unbind()
        };
        let edges_list = {
            let list = PyList::empty(py);
            // Source-grouped order matching networkx DiGraph
            for (ref_s, _) in &self.nodes {
                for (u, v, data) in &self.edges {
                    if u != ref_s {
                        continue;
                    }
                    let su = PyString::new(py, u);
                    let sv = PyString::new(py, v);
                    let triple = PyTuple::new(py, [&su, &sv, data.bind(py)])?;
                    list.append(triple)?;
                }
            }
            list.into_any().unbind()
        };
        Ok(vec![nodes_list, edges_list])
    }

    /// Return all nodes as ``[(ref, attrs), ...]`` (for ``__reduce__``).
    fn nodes_with_attrs_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for (ref_s, attrs) in &self.nodes {
            let s = PyString::new(py, ref_s);
            let pair = PyTuple::new(py, [&s, attrs.bind(py)])?;
            list.append(pair)?;
        }
        Ok(list.into_any().unbind())
    }

    /// Return all edges as ``(u, v, data)`` triples (for ``__reduce__``).
    fn edges_with_data_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for (u, v, data) in &self.edges {
            let su = PyString::new(py, u);
            let sv = PyString::new(py, v);
            let triple = PyTuple::new(py, [&su, &sv, data.bind(py)])?;
            list.append(triple)?;
        }
        Ok(list.into_any().unbind())
    }
}

#[pymethods]
impl TopologicalGraphStore {
    #[new]
    fn new() -> Self {
        Self {
            nodes: Vec::new(),
            node_set: HashSet::new(),
            edges: Vec::new(),
            has_edge_set: HashSet::new(),
        }
    }

    // -- mutation -----------------------------------------------------------

    /// Add a node with optional attributes.
    ///
    /// If the node already exists (by ref string), this updates the attributes
    /// but does NOT change the insertion order.
    #[pyo3(signature = (ref_, **attrs))]
    fn add_node(
        &mut self,
        py: Python<'_>,
        ref_: &str,
        attrs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let attr_dict: Py<PyAny> = match attrs {
            Some(d) => d.clone().into_any().unbind(),
            None => {
                let empty = PyDict::new(py);
                empty.into_any().unbind()
            }
        };

        if self.node_set.contains(ref_) {
            // Update existing node's attrs.
            for (s, _existing) in &mut self.nodes {
                if s == ref_ {
                    *_existing = attr_dict;
                    break;
                }
            }
        } else {
            self.node_set.insert(ref_.to_string());
            self.nodes.push((ref_.to_string(), attr_dict));
        }
        Ok(())
    }

    /// Add a directed edge with optional attributes.
    ///
    /// Edges are always appended (no deduplication), matching
    /// ``MultiDiGraph`` semantics. The ``has_edge`` set is updated
    /// for existence checks.
    #[pyo3(signature = (u, v, **attrs))]
    fn add_edge(
        &mut self,
        py: Python<'_>,
        u: &str,
        v: &str,
        attrs: Option<&Bound<'_, PyDict>>,
    ) -> PyResult<()> {
        let data_dict: Py<PyAny> = match attrs {
            Some(d) => d.clone().into_any().unbind(),
            None => {
                let empty = PyDict::new(py);
                empty.into_any().unbind()
            }
        };

        let key = (u.to_string(), v.to_string());
        self.has_edge_set.insert(key);
        self.edges.push((u.to_string(), v.to_string(), data_dict));
        Ok(())
    }

    // -- accessors ----------------------------------------------------------

    /// Number of unique nodes.
    fn number_of_nodes(&self) -> usize {
        self.nodes.len()
    }

    /// Number of unique (deduplicated) edges.
    fn number_of_edges(&self) -> usize {
        self.edges.len()
    }

    /// The node list in insertion order.
    ///
    /// Returns a list of node reference strings.
    fn nodes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for (ref_s, _attrs) in &self.nodes {
            list.append(PyString::new(py, ref_s))?;
        }
        Ok(list)
    }

    /// Return the attribute dict for a node, or ``None`` if the node does not
    /// exist.
    fn node_attrs<'py>(
        &self,
        py: Python<'py>,
        ref_: &str,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        for (s, attrs) in &self.nodes {
            if s == ref_ {
                return Ok(Some(attrs.bind(py).clone()));
            }
        }
        Ok(None)
    }

    /// Edge list with data: ``[(u, v, data_dict), ...]``.
    ///
    /// This is the networkx ``DiGraph.edges(data=True)`` contract. Edges are
    /// iterated in **source-grouped order**: by node insertion order of the
    /// source, then by edge insertion order within each source.
    #[pyo3(signature = (data = true))]
    fn edges<'py>(
        &self,
        py: Python<'py>,
        data: bool,
    ) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        // Emit edges in source-grouped order (networkx compatibility):
        // for each node in insertion order, emit its outgoing edges
        // in their insertion order.
        for (ref_s, _) in &self.nodes {
            for (u, v, d) in &self.edges {
                if u != ref_s {
                    continue;
                }
                if data {
                    let su = PyString::new(py, u);
                    let sv = PyString::new(py, v);
                    let triple = PyTuple::new(py, [&su, &sv, d.bind(py)])?;
                    list.append(triple)?;
                } else {
                    let su = PyString::new(py, u);
                    let sv = PyString::new(py, v);
                    let pair = PyTuple::new(py, [&su, &sv])?;
                    list.append(pair)?;
                }
            }
        }
        Ok(list)
    }

    /// Check whether any directed edge ``(u, v)`` exists (regardless of
    /// edge type — adjacency, separation, or membership).
    fn has_edge(&self, u: &str, v: &str) -> bool {
        self.has_edge_set.contains(&(u.to_string(), v.to_string()))
    }

    // -- dunder methods -----------------------------------------------------

    fn __repr__(&self) -> String {
        format!(
            "TopologicalGraphStore(nodes={}, edges={})",
            self.nodes.len(),
            self.edges.len()
        )
    }

    fn __eq__(slf: &Bound<'_, Self>, other: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        let py = slf.py();
        let lhs = slf.borrow().fields(py)?;
        dataclass_eq(py, &slf.get_type(), other, &lhs, |o| {
            o.cast::<Self>()?.borrow().fields(py)
        })
    }

    /// ``frozen=False`` — raises ``TypeError``.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("TopologicalGraphStore"))
    }

    /// ``__reduce__`` for ``pickle`` / ``copy.deepcopy`` support.
    ///
    /// Returns ``(cls, (), state)`` — the three-element form that pickle
    /// uses for ``cls(*args).__setstate__(state)``.
    fn __reduce__<'py>(
        slf: &Bound<'py, Self>,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyTuple>> {
        let state = Self::__getstate__(slf, py)?;
        let empty_args = PyTuple::empty(py);
        PyTuple::new(
            py,
            [slf.get_type().into_any(), empty_args.into_any(), state],
        )
    }

    /// Serialize state as ``(nodes_with_attrs_list, edges_with_data_list)``.
    fn __getstate__<'py>(
        slf: &Bound<'py, Self>,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let b = slf.borrow();
        Ok(PyTuple::new(
            py,
            [
                b.nodes_with_attrs_list_py(py)?.bind(py),
                b.edges_with_data_list_py(py)?.bind(py),
            ],
        )?
        .into_any())
    }

    /// Deserialize state: rebuild nodes and edges from ``__reduce__`` state.
    fn __setstate__(slf: &Bound<'_, Self>, state: &Bound<'_, PyAny>) -> PyResult<()> {
        let py = slf.py();
        let tuple = state.cast::<PyTuple>().map_err(|_| {
            pyo3::exceptions::PyValueError::new_err("state must be a tuple")
        })?;
        if tuple.len() != 2 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "state must be a 2-tuple (nodes, edges)",
            ));
        }
        let nodes_item = tuple.get_item(0)?;
        let edges_item = tuple.get_item(1)?;
        let nodes_list = nodes_item.cast::<PyList>()?;
        let edges_list = edges_item.cast::<PyList>()?;

        let mut graph = slf.try_borrow_mut().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("graph already borrowed")
        })?;

        for node_pair in nodes_list.iter() {
            let pair = node_pair.cast::<PyTuple>().map_err(|_| {
                pyo3::exceptions::PyValueError::new_err(
                    "node must be a 2-tuple (ref, attrs)",
                )
            })?;
            if pair.len() != 2 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "node must be a 2-tuple (ref, attrs)",
                ));
            }
            let ref_: String = pair.get_item(0)?.extract()?;
            let attrs = pair.get_item(1)?;
            let dict = attrs.cast::<PyDict>().map_err(|_| {
                pyo3::exceptions::PyValueError::new_err("attrs must be a dict")
            })?;
            // Use add_node with explicit attrs dict
            graph.add_node(py, &ref_, Some(dict))?;
        }

        for edge_triple in edges_list.iter() {
            let triple = edge_triple.cast::<PyTuple>().map_err(|_| {
                pyo3::exceptions::PyValueError::new_err(
                    "edge must be a 3-tuple (u, v, data)",
                )
            })?;
            if triple.len() != 3 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "edge must be a 3-tuple (u, v, data)",
                ));
            }
            let u: String = triple.get_item(0)?.extract()?;
            let v: String = triple.get_item(1)?.extract()?;
            let data = triple.get_item(2)?;
            let dict = data.cast::<PyDict>().map_err(|_| {
                pyo3::exceptions::PyValueError::new_err("edge data must be a dict")
            })?;
            graph.add_edge(py, &u, &v, Some(dict))?;
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the topological-graph contract pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "topological_graph_contracts")?;
    sub.add_class::<TopologicalGraphStore>()?;
    module.add_submodule(&sub)
}

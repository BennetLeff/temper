//! ``SkeletonGraph`` — Wave 4, replacing ``networkx.Graph`` in
//! ``temper_placer/router_v6/channel_skeleton.py``.
//!
//! Python reference: the ``nx.Graph`` built and consumed in
//! ``channel_skeleton.py``, pinned by the TDD differential oracle
//! ``tests/router_v6/test_channel_skeleton_rust_differential.py`` (G1).
//!
//! # What this replaces
//!
//! The last ``import networkx as nx`` in production ``router_v6/`` --
//! exactly three surfaces:
//!
//! | Line | Call | Replacement |
//! |---|---|---|
//! | 40 | ``nx.is_connected(self.graph)`` | ``self.graph.is_connected()`` |
//! | 79 | ``nx.Graph()`` | ``SkeletonGraph()`` |
//! | 529 | ``nx.connected_components(G)`` | ``G.connected_components()`` |
//!
//! # Insertion order (M6 rule + dedup)
//!
//! ``list(Graph.nodes())`` on networkx returns nodes in **first-seen order
//! over the edge list** (M6,
//! ``docs/evidence/2026-08-04-networkx-path-order-spike.md`` §7). This is
//! load-bearing: the node-index tie-break in ``_ensure_skeleton_connectivity``'s
//! Kruskal sort key ``(distance, i, j)`` depends on the node list order.
//!
//! ``list(Graph.edges)`` returns edges in **insertion order**. This is also
//! load-bearing: ``canonical_channel_edges`` feeds it as a stable-sort
//! tie-break for distinct edges that quantise to identical keys
//! (``constraint_model.py:99-101``).
//!
//! **Deduplication:** The pre-migration code has a duplicate ``add_edge``
//! call (line 115-116). networkx silently treats the second ``add_edge(u, v,
//! weight=length)`` as an attribute update on the existing edge -- the edge
//! list is NOT appended a second time. The Rust graph must replicate this:
//! ``add_edge`` with the same endpoints is a no-op for the edge list (though
//! we do update the weight if it differs -- the production code passes
//! identical weights, so this is academic).
//!
//! # ``connected_components`` order insensitivity
//!
//! Spike S4
//! (``docs/evidence/2026-08-11-channel-skeleton-connectivity-order-spike.md``)
//! proved that ``nx.connected_components`` enumeration order does NOT affect
//! ``_ensure_skeleton_connectivity``'s output (0/120 component-ID
//! permutations differ). The Rust BFS can therefore use any correct
//! component-enumeration order -- it does not need to match networkx's
//! internal DFS tie-breaking.
//!
//! # Edge attributes
//!
//! ``bundle_analyzer.py:186`` reads edge weights via
//! ``skeleton.graph.edges(data=True)``, unpacking
//! ``(u, v, {"weight": w})``. We expose this through a separate
//! ``edges_with_data()`` method rather than making the ``edges`` property
//! polymorphic.
//!
//! # ``repr`` / ``__eq__`` / ``__hash__``
//!
//! ``SkeletonGraph`` is unfrozen (``eq=True``, ``frozen=False``) --
//! hash raises ``TypeError``.  Equality compares node order, edge order,
//! and edge weights, matching the networkx ``Graph.__eq__`` contract that
//! downstream tests rely on.

use std::collections::{BTreeSet, VecDeque};

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods, PyFloat, PyList, PyTuple};

use crate::netlist_contracts::{dataclass_eq, unhashable};

// ---------------------------------------------------------------------------
// SkeletonGraph
// ---------------------------------------------------------------------------

/// An undirected graph with first-seen insertion order for nodes and edges.
///
/// Replaces ``networkx.Graph`` in ``channel_skeleton.py``.  Nodes are opaque
/// Python objects (skeleton coordinates, ``(x, y)`` float tuples).  Edges
/// carry an optional ``weight`` attribute.
///
/// # Thread safety
///
/// All methods require the Python GIL (they manipulate ``Py<PyAny>`` fields).
#[pyclass(dict, name = "SkeletonGraph", module = "temper_design_bundle_python.channel_skeleton_contracts")]
#[derive(Debug)]
pub struct SkeletonGraph {
    /// Nodes in first-seen insertion order: ``(node_obj, pos_obj)``.
    nodes: Vec<(Py<PyAny>, Py<PyAny>)>,
    /// Python ``dict`` mapping node → index (for O(1) lookup by Python equality).
    /// Stored as a Python dict so hashing follows CPython's rules exactly.
    node_index: Py<PyDict>,
    /// Edges in first-seen insertion order: ``(u_idx, v_idx, weight)``.
    /// Indices refer into ``self.nodes``.
    edges: Vec<(usize, usize, f64)>,
    /// Dedup set: sorted ``(u_idx, v_idx)`` integer pairs.
    edge_set: BTreeSet<(usize, usize)>,
    /// Adjacency list (built lazily on component queries).
    adjacency: Option<Vec<Vec<usize>>>,
}

impl SkeletonGraph {
    /// Build (or return) the adjacency list.
    fn ensure_adjacency(&mut self) {
        if self.adjacency.is_some() {
            return;
        }
        let n = self.nodes.len();
        let mut adj: Vec<Vec<usize>> = vec![Vec::new(); n];
        for &(u_idx, v_idx, _weight) in &self.edges {
            adj[u_idx].push(v_idx);
            adj[v_idx].push(u_idx);
        }
        self.adjacency = Some(adj);
    }

    /// Invalidate the adjacency cache (called after adding nodes/edges).
    fn invalidate_adjacency(&mut self) {
        self.adjacency = None;
    }

    /// Return the fields for ``__eq__``: the node list + edge list
    /// (as Python lists so tuple comparison uses Python ``==``).
    fn fields(&self, py: Python<'_>) -> PyResult<Vec<Py<PyAny>>> {
        let nodes_list = {
            let list = PyList::empty(py);
            for (n, _pos) in &self.nodes {
                list.append(n.bind(py))?;
            }
            list.into_any().unbind()
        };
        let edges_list = {
            let list = PyList::empty(py);
            for &(u_idx, v_idx, _w) in &self.edges {
                let u = &self.nodes[u_idx].0;
                let v = &self.nodes[v_idx].0;
                let pair = PyTuple::new(py, [u.bind(py), v.bind(py)])?;
                list.append(pair)?;
            }
            list.into_any().unbind()
        };
        Ok(vec![nodes_list, edges_list])
    }

    /// Return all nodes as a Python list (for __reduce__).
    fn nodes_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for (n, _pos) in &self.nodes {
            list.append(n.bind(py))?;
        }
        Ok(list.into_any().unbind())
    }

    /// Return all edges as Python ``(u, v, weight)`` triples (for __reduce__).
    fn edges_weighted_list_py(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        let list = PyList::empty(py);
        for &(u_idx, v_idx, w) in &self.edges {
            let u = &self.nodes[u_idx].0;
            let v = &self.nodes[v_idx].0;
            let triple =
                PyTuple::new(py, [u.bind(py), v.bind(py), &PyFloat::new(py, w)])?;
            list.append(triple)?;
        }
        Ok(list.into_any().unbind())
    }

    /// Ensure a node exists, returning its index.  If the node is new,
    /// it is added with ``pos=None`` (auto-creation from ``add_edge``).
    fn get_or_create_node(
        &mut self,
        py: Python<'_>,
        node: &Bound<'_, PyAny>,
    ) -> PyResult<usize> {
        let dict = self.node_index.bind(py);
        if let Some(idx_obj) = dict.get_item(node)? {
            let idx: usize = idx_obj.extract()?;
            return Ok(idx);
        }
        let idx = self.nodes.len();
        dict.set_item(node, idx)?;
        self.nodes.push((node.clone().unbind(), py.None()));
        self.invalidate_adjacency();
        Ok(idx)
    }
}

#[pymethods]
impl SkeletonGraph {
    #[new]
    fn new(py: Python<'_>) -> PyResult<Self> {
        Ok(Self {
            nodes: Vec::new(),
            node_index: PyDict::new(py).unbind(),
            edges: Vec::new(),
            edge_set: BTreeSet::new(),
            adjacency: None,
        })
    }

    // -- mutation -----------------------------------------------------------

    /// Add a node with an optional position attribute.
    ///
    /// If the node already exists (by Python equality), this is a no-op
    /// apart from updating the position to the new value.
    fn add_node(
        &mut self,
        py: Python<'_>,
        node: &Bound<'_, PyAny>,
        pos: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        let dict = self.node_index.bind(py);
        if let Some(existing) = dict.get_item(node)? {
            let idx: usize = existing.extract()?;
            self.nodes[idx].1 = pos.clone().unbind();
            return Ok(());
        }
        let idx = self.nodes.len();
        dict.set_item(node, idx)?;
        self.nodes
            .push((node.clone().unbind(), pos.clone().unbind()));
        self.invalidate_adjacency();
        Ok(())
    }

    /// Add an undirected edge with an optional weight.
    ///
    /// **Deduplication:** If an edge between ``u`` and ``v`` already exists
    /// (undirected), this updates the weight but does NOT append a duplicate
    /// entry to the edge list.
    ///
    /// If one or both endpoints do not exist as nodes, they are
    /// auto-created (matching networkx's behaviour) with a ``pos`` of
    /// ``None``.
    fn add_edge(
        &mut self,
        py: Python<'_>,
        u: &Bound<'_, PyAny>,
        v: &Bound<'_, PyAny>,
        weight: Option<f64>,
    ) -> PyResult<()> {
        let w = weight.unwrap_or(1.0);

        let u_idx = self.get_or_create_node(py, u)?;
        let v_idx = self.get_or_create_node(py, v)?;

        // Dedup: sort indices so edge_set is direction-agnostic.
        let key = if u_idx <= v_idx {
            (u_idx, v_idx)
        } else {
            (v_idx, u_idx)
        };

        if self.edge_set.contains(&key) {
            // Edge already exists: update weight in the edge list.
            for (eu, ev, ew) in &mut self.edges {
                let ekey = if *eu <= *ev {
                    (*eu, *ev)
                } else {
                    (*ev, *eu)
                };
                if ekey == key {
                    *ew = w;
                    break;
                }
            }
            return Ok(());
        }

        self.edge_set.insert(key);
        self.edges.push((u_idx, v_idx, w));
        self.invalidate_adjacency();
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

    /// The node list in first-seen insertion order.
    #[getter]
    fn nodes<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for (n, _pos) in &self.nodes {
            list.append(n.bind(py))?;
        }
        Ok(list)
    }

    /// The edge list in first-seen insertion order.
    ///
    /// Returns ``[(u, v), ...]`` tuples (no weight).
    /// Use :meth:`edges_with_data` for the ``data=True`` contract.
    #[getter]
    fn edges<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for &(u_idx, v_idx, _w) in &self.edges {
            let u = &self.nodes[u_idx].0;
            let v = &self.nodes[v_idx].0;
            let pair = PyTuple::new(py, [u.bind(py), v.bind(py)])?;
            list.append(pair)?;
        }
        Ok(list)
    }

    /// Edge list with weight data: ``[(u, v, {"weight": w}), ...]``.
    ///
    /// This is the networkx ``Graph.edges(data=True)`` contract used by
    /// ``bundle_analyzer.py:186``.
    fn edges_with_data<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyList>> {
        let list = PyList::empty(py);
        for &(u_idx, v_idx, w) in &self.edges {
            let u = &self.nodes[u_idx].0;
            let v = &self.nodes[v_idx].0;
            let data = PyDict::new(py);
            data.set_item("weight", w)?;
            let triple = PyTuple::new(py, [u.bind(py), v.bind(py), &data])?;
            list.append(triple)?;
        }
        Ok(list)
    }

    /// Check whether the graph is fully connected.
    ///
    /// An empty graph (0 nodes) is considered connected.
    fn is_connected(&mut self) -> bool {
        let n = self.nodes.len();
        if n <= 1 {
            return true;
        }
        self.ensure_adjacency();
        let adj = match self.adjacency.as_ref() {
            Some(a) => a,
            None => return false,
        };
        let mut visited = vec![false; n];
        let mut queue = VecDeque::new();
        visited[0] = true;
        queue.push_back(0);
        let mut count = 1;
        while let Some(u) = queue.pop_front() {
            for &v in &adj[u] {
                if !visited[v] {
                    visited[v] = true;
                    count += 1;
                    queue.push_back(v);
                }
            }
        }
        count == n
    }

    /// Return the connected components of the graph.
    ///
    /// Each component is a ``list`` of nodes.  The component *order* is
    /// unspecified (BFS internal ordering -- spike S4 proved this does not
    /// affect ``_ensure_skeleton_connectivity``'s output).
    fn connected_components<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyList>> {
        let n = self.nodes.len();
        let outer = PyList::empty(py);

        if n == 0 {
            return Ok(outer);
        }

        self.ensure_adjacency();
        let adj = match self.adjacency.as_ref() {
            Some(a) => a,
            None => return Ok(outer),
        };
        let mut visited = vec![false; n];

        for start in 0..n {
            if visited[start] {
                continue;
            }
            // BFS this component.
            let mut comp_nodes: Vec<usize> = Vec::new();
            let mut queue = VecDeque::new();
            visited[start] = true;
            queue.push_back(start);

            while let Some(u) = queue.pop_front() {
                comp_nodes.push(u);
                for &v in &adj[u] {
                    if !visited[v] {
                        visited[v] = true;
                        queue.push_back(v);
                    }
                }
            }

            let comp_list = PyList::empty(py);
            for idx in comp_nodes {
                comp_list.append(self.nodes[idx].0.bind(py))?;
            }
            outer.append(comp_list)?;
        }

        Ok(outer)
    }

    // -- dunder methods -----------------------------------------------------

    fn __repr__(&self) -> String {
        format!(
            "SkeletonGraph(nodes={}, edges={})",
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
        Err(unhashable("SkeletonGraph"))
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

    /// Serialize state as ``(nodes_list, edges_with_weights_list)``.
    fn __getstate__<'py>(
        slf: &Bound<'py, Self>,
        py: Python<'py>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let b = slf.borrow();
        Ok(PyTuple::new(
            py,
            [b.nodes_list_py(py)?.bind(py), b.edges_weighted_list_py(py)?.bind(py)],
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
        let item0 = tuple.get_item(0)?;
        let item1 = tuple.get_item(1)?;
        let nodes_list = item0.cast::<PyList>()?;
        let edges_list = item1.cast::<PyList>()?;

        // Borrow mutably through the Bound
        let mut graph = slf.try_borrow_mut().map_err(|_| {
            pyo3::exceptions::PyRuntimeError::new_err("graph already borrowed")
        })?;

        let none = py.None().bind(py).clone();
        for node in nodes_list.iter() {
            graph.add_node(py, &node, &none)?;
        }
        for edge in edges_list.iter() {
            let triple = edge.cast::<PyTuple>().map_err(|_| {
                pyo3::exceptions::PyValueError::new_err(
                    "edge must be a 3-tuple (u, v, weight)",
                )
            })?;
            if triple.len() != 3 {
                return Err(pyo3::exceptions::PyValueError::new_err(
                    "edge must be a 3-tuple (u, v, weight)",
                ));
            }
            let u = triple.get_item(0)?;
            let v = triple.get_item(1)?;
            let w: f64 = triple.get_item(2)?.extract()?;
            graph.add_edge(py, &u, &v, Some(w))?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the channel-skeleton contract pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "channel_skeleton_contracts")?;
    sub.add_class::<SkeletonGraph>()?;
    module.add_submodule(&sub)
}

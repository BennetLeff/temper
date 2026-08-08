//! Net-graph data model — Wave 4, Wave C (core contracts migration).
//!
//! Python reference: `temper_placer/core/net_graph.py`, pinned VERBATIM in
//! `packages/temper-placer/tests/core/test_net_graph_and_diff_pair_rust_differential.py`
//! (commit TBD). The pyo3 pyclasses `SubNetEdge` and `NetGraph` must reproduce
//! that implementation bit-identically; the differential test is the TDD oracle
//! for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! Both source classes are plain `@dataclass`es that perform no coercion in
//! `__init__`: `SubNetEdge("A", "B", priority=0)` stores `int` `0`, not
//! `0.0`. A Rust field typed `i64` or `f64` would silently widen every such
//! value and change `repr`, `==` against type-sensitive code, and downstream
//! consumers. Storing each field as the exact Python object the caller passed
//! makes type preservation true by construction.
//!
//! This also preserves **object identity** for the mutable container fields,
//! which the repo depends on: `config_loader.rs:1199` does
//! `graph.edges.append(edge)`, mutating `NetGraph.edges` in place. A getter
//! that rebuilt a fresh list would silently drop those appends.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Rather than re-deriving CPython's `repr(float)`/`repr(str)` rules, these
//! pyclasses call **CPython's own `repr()`** on each stored field object
//! and splice the results into the dataclass layout
//! `Cls(f1=r1, f2=r2, ...)`. Equality builds the same field tuple both sides
//! and defers to Python `==` on tuples, exactly as a generated dataclass
//! `__eq__` does. This is bit-exactness by delegation, not by replication.
//!
//! # Mutability contract (R-A risk)
//!
//! `NetGraph.edges` (list) and `NetGraph.star_nodes` (set) are mutated in
//! place by consumers. The getters MUST return the same Python object
//! (`clone_ref(py)`), and `#[new]` MUST create a fresh empty list/set per
//! instance when the arg is `None` (not a shared default).

use pyo3::prelude::*;
use pyo3::types::{PyList, PySet};
use pyo3::IntoPyObjectExt;

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, list_or_new, opt_or, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// Local helpers
// ---------------------------------------------------------------------------

/// Default a `None` argument to a freshly created empty `set` — what
/// `field(default_factory=set)` does on every construction.
fn set_or_new(py: Python<'_>, value: Option<&Bound<'_, PyAny>>) -> PyResult<Py<PyAny>> {
    match value {
        Some(v) => Ok(v.clone().unbind()),
        None => {
            let empty: std::vec::Vec<&str> = Vec::new();
            PySet::new(py, empty.iter())?.into_py_any(py)
        }
    }
}

// ---------------------------------------------------------------------------
// SubNetEdge
// ---------------------------------------------------------------------------

/// A directed edge within a net graph (mirrors `SubNetEdge` in
/// `temper_placer/core/net_graph.py`).
#[pyclass(dict, module = "temper_design_bundle_python.net_graph_contracts")]
#[derive(Debug)]
pub struct SubNetEdge {
    #[pyo3(get, set)]
    pub source_pin: Py<PyAny>,
    #[pyo3(get, set)]
    pub sink_pin: Py<PyAny>,
    #[pyo3(get, set)]
    pub trace_width_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub clearance_mm: Py<PyAny>,
    #[pyo3(get, set)]
    pub priority: Py<PyAny>,
}

impl SubNetEdge {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.source_pin),
            same(py, &self.sink_pin),
            same(py, &self.trace_width_mm),
            same(py, &self.clearance_mm),
            same(py, &self.priority),
        ]
    }
}

#[pymethods]
impl SubNetEdge {
    #[new]
    #[pyo3(signature = (
        source_pin,
        sink_pin,
        trace_width_mm=None,
        clearance_mm=None,
        priority=None
    ))]
    fn new(
        py: Python<'_>,
        source_pin: &Bound<'_, PyAny>,
        sink_pin: &Bound<'_, PyAny>,
        trace_width_mm: Option<&Bound<'_, PyAny>>,
        clearance_mm: Option<&Bound<'_, PyAny>>,
        priority: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            source_pin: source_pin.clone().unbind(),
            sink_pin: sink_pin.clone().unbind(),
            trace_width_mm: trace_width_mm.map_or_else(|| py.None(), |v| v.clone().unbind()),
            clearance_mm: clearance_mm.map_or_else(|| py.None(), |v| v.clone().unbind()),
            priority: opt_or(py, priority, 0_i64)?,
        })
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "SubNetEdge",
            &[
                ("source_pin", repr_of(&self.source_pin, py)?),
                ("sink_pin", repr_of(&self.sink_pin, py)?),
                ("trace_width_mm", repr_of(&self.trace_width_mm, py)?),
                ("clearance_mm", repr_of(&self.clearance_mm, py)?),
                ("priority", repr_of(&self.priority, py)?),
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

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("SubNetEdge"))
    }
}

// ---------------------------------------------------------------------------
// NetGraph
// ---------------------------------------------------------------------------

/// Topology definition for a single net (mirrors `NetGraph` in
/// `temper_placer/core/net_graph.py`).
///
/// Mutable from Python exactly like the dataclass: `edges` (list) and
/// `star_nodes` (set) are the actual Python objects, and the getters
/// return those same objects (identity-preserving). In-place mutation
/// (`append`, `add`) persists.
#[pyclass(dict, module = "temper_design_bundle_python.net_graph_contracts")]
#[derive(Debug)]
pub struct NetGraph {
    #[pyo3(get, set)]
    pub net_name: Py<PyAny>,
    edges: Py<PyList>,
    star_nodes: Py<PySet>,
}

impl NetGraph {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.net_name),
            self.edges.clone_ref(py).into_any(),
            self.star_nodes.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl NetGraph {
    #[new]
    #[pyo3(signature = (net_name, edges=None, star_nodes=None))]
    fn new(
        py: Python<'_>,
        net_name: &Bound<'_, PyAny>,
        edges: Option<&Bound<'_, PyAny>>,
        star_nodes: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            net_name: net_name.clone().unbind(),
            edges: list_or_new(py, edges)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
            star_nodes: set_or_new(py, star_nodes)?
                .into_bound(py)
                .cast::<PySet>()?
                .clone()
                .unbind(),
        })
    }

    /// The mutable edges list — returns the SAME Python object (identity-preserving).
    #[getter]
    fn edges(&self, py: Python<'_>) -> Py<PyList> {
        self.edges.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the edges list reference
    /// (`graph.edges = [...]`), exactly like the pre-migration dataclass.
    #[setter]
    fn set_edges(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("edges must be a list")
        })?;
        self.edges = list.clone().unbind();
        Ok(())
    }

    /// The mutable star_nodes set — returns the SAME Python object (identity-preserving).
    #[getter]
    fn star_nodes(&self, py: Python<'_>) -> Py<PySet> {
        self.star_nodes.clone_ref(py)
    }

    /// Dataclass-field assignment: replaces the star_nodes set reference
    /// (`graph.star_nodes = {...}`), exactly like the pre-migration dataclass.
    #[setter]
    fn set_star_nodes(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let set = value.cast::<PySet>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("star_nodes must be a set")
        })?;
        self.star_nodes = set.clone().unbind();
        Ok(())
    }

    /// Find an edge by source and sink pins. Linear scan — matches the oracle.
    fn get_edge<'py>(
        &self,
        py: Python<'py>,
        source: &Bound<'py, PyAny>,
        sink: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let edges = self.edges.bind(py);
        for edge in edges.try_iter()? {
            let edge = edge?;
            if edge.getattr("source_pin")?.eq(source)?
                && edge.getattr("sink_pin")?.eq(sink)?
            {
                return Ok(Some(edge));
            }
        }
        Ok(None)
    }

    /// Get all edges starting from a given pin.
    fn get_outgoing_edges<'py>(
        &self,
        py: Python<'py>,
        pin: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        let edges = self.edges.bind(py);
        for edge in edges.try_iter()? {
            let edge = edge?;
            if edge.getattr("source_pin")?.eq(pin)? {
                out.append(edge)?;
            }
        }
        Ok(out)
    }

    /// Get all edges ending at a given pin.
    fn get_incoming_edges<'py>(
        &self,
        py: Python<'py>,
        pin: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let out = PyList::empty(py);
        let edges = self.edges.bind(py);
        for edge in edges.try_iter()? {
            let edge = edge?;
            if edge.getattr("sink_pin")?.eq(pin)? {
                out.append(edge)?;
            }
        }
        Ok(out)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "NetGraph",
            &[
                ("net_name", repr_of(&self.net_name, py)?),
                ("edges", repr_of(&(self.edges.clone_ref(py).into_any()), py)?),
                (
                    "star_nodes",
                    repr_of(&(self.star_nodes.clone_ref(py).into_any()), py)?,
                ),
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

    /// `eq=True, frozen=False` -> the dataclass sets `__hash__ = None`.
    fn __hash__(&self) -> PyResult<isize> {
        Err(unhashable("NetGraph"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the net-graph contracts pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "net_graph_contracts")?;
    sub.add_class::<SubNetEdge>()?;
    sub.add_class::<NetGraph>()?;
    module.add_submodule(&sub)
}

//! Loop ownership data model — Wave 4 migration (fanout/migrate-core-3).
//!
//! Python reference: `temper_placer/core/loop_ownership.py`, pinned VERBATIM
//! in `packages/temper-placer/tests/core/test_loop_ownership_rust_differential.py`.
//! The pyo3 pyclasses `LoopMembership`, `ComponentLoopInfo`, and
//! `LoopOwnershipMap` must reproduce that implementation bit-identically;
//! the differential test is the TDD oracle for this file.
//!
//! # Why every field is an opaque `Py<PyAny>`
//!
//! Both source classes are plain `@dataclass`es that perform no coercion in
//! `__init__`: `LoopMembership("commutation", "switch")` stores the strings as
//! Python `str` objects. Storing each field as the exact Python object the
//! caller passed makes type preservation true by construction.
//!
//! Container fields (`pins_in_loop: list`, `memberships: list`,
//! `component_to_loops: dict`, `loop_to_components: dict`) are stored as
//! `Py<PyList>` / `Py<PyDict>` with identity-preserving getters — mutation
//! in place persists, exactly as the mutable dataclass does.
//!
//! # `repr` / `__eq__` / `__hash__`
//!
//! Rather than re-deriving CPython's `repr(float)`/`repr(str)` rules, these
//! pyclasses call **CPython's own `repr()`** on each stored field object
//! and splice the results into the dataclass layout. Equality builds the same
//! field tuple both sides and defers to Python `==` on tuples. `__hash__`
//! raises `TypeError` (dataclass with `eq=True, frozen=False`).
//!
//! # `get_priority_weight` and `components_share_critical_loop`
//!
//! These two methods accept a `loop_collection` argument (a `LoopCollection`
//! pyclass instance from `loops.rs`). They call `.get_loop(name)` and access
//! `.priority` via Python attribute access — the same way the Python oracle
//! does. `LoopCollection` and `LoopPriority` are already Rust pyclasses in
//! this crate, so the calls go through pyo3's generated bindings.
//!
//! # JUSTIFIED-KEEP (not migrated)
//!
//! `classify_role(component, loop)` and `build_ownership_map(loops, netlist)`
//! are NOT migrated. They depend on `classify_component` from `loop_extractor`
//! (owned by another session's `migrate/loop-extractor` branch) and involve
//! complex imperative orchestration over `Netlist`/`LoopCollection` objects.
//! They stay in `core/loop_ownership.py` as a pure-delegation shim alongside
//! the re-exports of these pyclasses.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use crate::netlist_contracts::{
    dataclass_eq, dataclass_repr, dict_or_new, list_or_new, repr_of, same, unhashable,
};

// ---------------------------------------------------------------------------
// LoopMembership
// ---------------------------------------------------------------------------

/// A component's membership in a single loop (mirrors `LoopMembership` in
/// `temper_placer/core/loop_ownership.py`).
#[pyclass(dict, module = "temper_design_bundle_python.loop_ownership_contracts")]
#[derive(Debug)]
pub struct LoopMembership {
    #[pyo3(get, set)]
    pub loop_name: Py<PyAny>,
    #[pyo3(get, set)]
    pub role: Py<PyAny>,
    pins_in_loop: Py<PyList>,
}

impl LoopMembership {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.loop_name),
            same(py, &self.role),
            self.pins_in_loop.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl LoopMembership {
    #[new]
    #[pyo3(signature = (loop_name, role, pins_in_loop=None))]
    fn new(
        py: Python<'_>,
        loop_name: &Bound<'_, PyAny>,
        role: &Bound<'_, PyAny>,
        pins_in_loop: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            loop_name: loop_name.clone().unbind(),
            role: role.clone().unbind(),
            pins_in_loop: list_or_new(py, pins_in_loop)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
        })
    }

    /// Identity-preserving getter for the mutable pins_in_loop list.
    #[getter]
    fn pins_in_loop(&self, py: Python<'_>) -> Py<PyList> {
        self.pins_in_loop.clone_ref(py)
    }

    /// Dataclass-field assignment: `membership.pins_in_loop = [...]`
    #[setter]
    fn set_pins_in_loop(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("pins_in_loop must be a list")
        })?;
        self.pins_in_loop = list.clone().unbind();
        Ok(())
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "LoopMembership",
            &[
                ("loop_name", repr_of(&self.loop_name, py)?),
                ("role", repr_of(&self.role, py)?),
                (
                    "pins_in_loop",
                    repr_of(&(self.pins_in_loop.clone_ref(py).into_any()), py)?,
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
        Err(unhashable("LoopMembership"))
    }
}

// ---------------------------------------------------------------------------
// ComponentLoopInfo
// ---------------------------------------------------------------------------

/// Complete loop information for a single component (mirrors
/// `ComponentLoopInfo` in `temper_placer/core/loop_ownership.py`).
///
/// A component can participate in multiple loops. The `memberships` list
/// is identity-preserving (mutation in place persists).
#[pyclass(dict, module = "temper_design_bundle_python.loop_ownership_contracts")]
#[derive(Debug)]
pub struct ComponentLoopInfo {
    #[pyo3(get, set)]
    pub component_ref: Py<PyAny>,
    memberships: Py<PyList>,
}

impl ComponentLoopInfo {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            same(py, &self.component_ref),
            self.memberships.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl ComponentLoopInfo {
    #[new]
    #[pyo3(signature = (component_ref, memberships=None))]
    fn new(
        py: Python<'_>,
        component_ref: &Bound<'_, PyAny>,
        memberships: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            component_ref: component_ref.clone().unbind(),
            memberships: list_or_new(py, memberships)?
                .into_bound(py)
                .cast::<PyList>()?
                .clone()
                .unbind(),
        })
    }

    /// Identity-preserving getter for the mutable memberships list.
    #[getter]
    fn memberships(&self, py: Python<'_>) -> Py<PyList> {
        self.memberships.clone_ref(py)
    }

    /// Dataclass-field assignment: `info.memberships = [...]`
    #[setter]
    fn set_memberships(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let list = value.cast::<PyList>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("memberships must be a list")
        })?;
        self.memberships = list.clone().unbind();
        Ok(())
    }

    /// Get list of all loop names this component participates in.
    #[getter]
    fn loop_names(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        let out = PyList::empty(py);
        let memberships = self.memberships.bind(py);
        for m in memberships.try_iter()? {
            let m = m?;
            let name = m.getattr("loop_name")?;
            out.append(name)?;
        }
        Ok(out.unbind())
    }

    /// Check if component is in any critical loop (heuristic based on loop
    /// names: starts with "commutation"/"gate_drive" or contains them
    /// case-insensitively).
    #[getter]
    fn is_in_critical_loop(&self, py: Python<'_>) -> PyResult<bool> {
        let memberships = self.memberships.bind(py);
        for m in memberships.try_iter()? {
            let m = m?;
            let name: String = m.getattr("loop_name")?.extract()?;
            let lower = name.to_lowercase();
            if name.starts_with("commutation")
                || name.starts_with("gate_drive")
                || lower.contains("commutation")
                || lower.contains("gate_drive")
            {
                return Ok(true);
            }
        }
        Ok(false)
    }

    /// Calculate placement priority weight based on loop memberships.
    ///
    /// Components in multiple loops get the maximum priority of all their
    /// loops. Calls `loop_collection.get_loop(name)` and reads
    /// `loop.priority` via Python attribute access.
    #[pyo3(signature = (loop_collection))]
    fn get_priority_weight(
        &self,
        py: Python<'_>,
        loop_collection: &Bound<'_, PyAny>,
    ) -> PyResult<f64> {
        let memberships = self.memberships.bind(py);
        let mut max_weight: f64 = 0.0;
        for m in memberships.try_iter()? {
            let m = m?;
            let name = m.getattr("loop_name")?;
            let loop_obj = loop_collection.call_method1("get_loop", (&name,))?;
            if loop_obj.is_none() {
                continue;
            }
            // loop.priority is a LoopPriority enum; get its name
            let priority_name: String = loop_obj.getattr("priority")?.getattr("name")?.extract()?;
            let weight = match priority_name.as_str() {
                "CRITICAL" => 1.0,
                "HIGH" => 0.7,
                "MEDIUM" => 0.4,
                "LOW" => 0.1,
                _ => 0.0,
            };
            if weight > max_weight {
                max_weight = weight;
            }
        }
        Ok(max_weight)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "ComponentLoopInfo",
            &[
                ("component_ref", repr_of(&self.component_ref, py)?),
                (
                    "memberships",
                    repr_of(&(self.memberships.clone_ref(py).into_any()), py)?,
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
        Err(unhashable("ComponentLoopInfo"))
    }
}

// ---------------------------------------------------------------------------
// LoopOwnershipMap
// ---------------------------------------------------------------------------

/// Bidirectional mapping between components and loops (mirrors
/// `LoopOwnershipMap` in `temper_placer/core/loop_ownership.py`).
///
/// Provides efficient queries for component-loop and loop-component lookups,
/// plus shared-loop detection.
#[pyclass(dict, module = "temper_design_bundle_python.loop_ownership_contracts")]
#[derive(Debug)]
pub struct LoopOwnershipMap {
    component_to_loops: Py<PyDict>,
    loop_to_components: Py<PyDict>,
}

impl LoopOwnershipMap {
    fn fields(&self, py: Python<'_>) -> Vec<Py<PyAny>> {
        vec![
            self.component_to_loops.clone_ref(py).into_any(),
            self.loop_to_components.clone_ref(py).into_any(),
        ]
    }
}

#[pymethods]
impl LoopOwnershipMap {
    #[new]
    #[pyo3(signature = (component_to_loops=None, loop_to_components=None))]
    fn new(
        py: Python<'_>,
        component_to_loops: Option<&Bound<'_, PyAny>>,
        loop_to_components: Option<&Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        Ok(Self {
            component_to_loops: dict_or_new(py, component_to_loops)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
            loop_to_components: dict_or_new(py, loop_to_components)?
                .into_bound(py)
                .cast::<PyDict>()?
                .clone()
                .unbind(),
        })
    }

    /// Identity-preserving getter for component_to_loops dict.
    #[getter]
    fn component_to_loops(&self, py: Python<'_>) -> Py<PyDict> {
        self.component_to_loops.clone_ref(py)
    }

    /// Dataclass-field assignment.
    #[setter]
    fn set_component_to_loops(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let dict = value.cast::<PyDict>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("component_to_loops must be a dict")
        })?;
        self.component_to_loops = dict.clone().unbind();
        Ok(())
    }

    /// Identity-preserving getter for loop_to_components dict.
    #[getter]
    fn loop_to_components(&self, py: Python<'_>) -> Py<PyDict> {
        self.loop_to_components.clone_ref(py)
    }

    /// Dataclass-field assignment.
    #[setter]
    fn set_loop_to_components(&mut self, value: &Bound<'_, PyAny>) -> PyResult<()> {
        let dict = value.cast::<PyDict>().map_err(|_| {
            pyo3::exceptions::PyTypeError::new_err("loop_to_components must be a dict")
        })?;
        self.loop_to_components = dict.clone().unbind();
        Ok(())
    }

    /// Get loop information for a component.
    fn get_component_info<'py>(
        &self,
        py: Python<'py>,
        ref_: &Bound<'py, PyAny>,
    ) -> PyResult<Option<Bound<'py, PyAny>>> {
        let dict = self.component_to_loops.bind(py);
        match dict.get_item(ref_)? {
            Some(v) => Ok(Some(v)),
            None => Ok(None),
        }
    }

    /// Get all components participating in a loop.
    fn get_loop_components<'py>(
        &self,
        py: Python<'py>,
        loop_name: &Bound<'py, PyAny>,
    ) -> PyResult<Py<PyList>> {
        let dict = self.loop_to_components.bind(py);
        match dict.get_item(loop_name)? {
            Some(v) => Ok(v.extract::<Py<PyList>>()?),
            None => Ok(PyList::empty(py).unbind()),
        }
    }

    /// Find loops that contain both components.
    fn get_shared_loops<'py>(
        &self,
        py: Python<'py>,
        ref_a: &Bound<'py, PyAny>,
        ref_b: &Bound<'py, PyAny>,
    ) -> PyResult<Py<PyList>> {
        let dict = self.component_to_loops.bind(py);
        let info_a = dict.get_item(ref_a)?;
        let info_b = dict.get_item(ref_b)?;

        let (info_a, info_b) = match (info_a, info_b) {
            (Some(a), Some(b)) => (a, b),
            _ => return Ok(PyList::empty(py).unbind()),
        };

        // Get loop_names from each info
        let names_a = info_a.getattr("loop_names")?;
        let names_b = info_b.getattr("loop_names")?;

        // Build a set of names from A
        let set_a = py
            .import("builtins")?
            .call_method1("set", (names_a,))?;

        let out = PyList::empty(py);
        // Iterate names from B, check membership in set_a
        for name in names_b.try_iter()? {
            let name = name?;
            if set_a.call_method1("__contains__", (&name,))?.extract::<bool>()? {
                out.append(name)?;
            }
        }
        Ok(out.unbind())
    }

    /// Check if two components share any loop.
    #[pyo3(signature = (ref_a, ref_b, _loop_collection=None))]
    fn components_share_loop<'py>(
        &self,
        py: Python<'py>,
        ref_a: &Bound<'py, PyAny>,
        ref_b: &Bound<'py, PyAny>,
        _loop_collection: Option<&Bound<'py, PyAny>>,
    ) -> PyResult<bool> {
        let shared = self.get_shared_loops(py, ref_a, ref_b)?;
        let shared = shared.bind(py);
        Ok(shared.len() > 0)
    }

    /// Check if two components share a CRITICAL priority loop.
    #[pyo3(signature = (ref_a, ref_b, loop_collection))]
    fn components_share_critical_loop<'py>(
        &self,
        py: Python<'py>,
        ref_a: &Bound<'py, PyAny>,
        ref_b: &Bound<'py, PyAny>,
        loop_collection: &Bound<'py, PyAny>,
    ) -> PyResult<bool> {
        let shared = self.get_shared_loops(py, ref_a, ref_b)?;
        let shared = shared.bind(py);
        for loop_name in shared.try_iter()? {
            let loop_name = loop_name?;
            let loop_obj = loop_collection.call_method1("get_loop", (&loop_name,))?;
            if loop_obj.is_none() {
                continue;
            }
            let priority_name: String =
                loop_obj.getattr("priority")?.getattr("name")?.extract()?;
            if priority_name == "CRITICAL" {
                return Ok(true);
            }
        }
        Ok(false)
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(dataclass_repr(
            "LoopOwnershipMap",
            &[
                (
                    "component_to_loops",
                    repr_of(
                        &(self.component_to_loops.clone_ref(py).into_any()),
                        py,
                    )?,
                ),
                (
                    "loop_to_components",
                    repr_of(
                        &(self.loop_to_components.clone_ref(py).into_any()),
                        py,
                    )?,
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
        Err(unhashable("LoopOwnershipMap"))
    }
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the loop-ownership pyclasses in the given module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "loop_ownership_contracts")?;
    sub.add_class::<LoopMembership>()?;
    sub.add_class::<ComponentLoopInfo>()?;
    sub.add_class::<LoopOwnershipMap>()?;
    module.add_submodule(&sub)
}

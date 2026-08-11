//! Phase-E E1 (rust-orchestration-engine plan): `ModelBuilder::build()` —
//! the constraint-model building orchestration from
//! `router_v6/constraint_model.py` (1,150 LOC), plus the design-bundle
//! contract pyclasses it constructs.
//!
//! | Python surface                    | Rust surface                                      |
//! |-----------------------------------|---------------------------------------------------|
//! | `ModelBuilder` + every `_create_*`| [`ModelBuilder::build`]                            |
//! | `NetChannelVar`/`NetLayerVar`/`ViaVar`/`OrderVar`/`Variable` | the `model_builder` pyclasses |
//! | `CapacityConstraint`/`DiffPairConstraint`/`LayerConstraint`/`ChannelSeparationConstraint`/`Constraint` | the `model_builder` pyclasses |
//! | `ConstraintModel` (registry)      | [`ConstraintModel`]                                |
//! | `ConstraintModelEmptyError`       | `model_builder.ConstraintModelEmptyError`          |
//!
//! The pre-migration implementation is pinned VERBATIM as the oracle
//! `tests/router_v6/_constraint_model_builder_py_oracle.py` (a byte-exact
//! snapshot of `constraint_model.py` as committed at `8dce8f8a^`, the
//! parent of the Wave-4 kernel-migration commit); the differential suite
//! `tests/router_v6/test_constraint_model_builder_rust_differential.py`
//! drives both arms with identical inputs and compares the resulting models
//! field-by-field, bit-exactly (`float.hex()`).
//!
//! # What stays Python, and why
//!
//! The build() orchestration is split at the PCL boundary:
//!
//! - **The `_create_*` loops move to Rust.** Everything that assembles
//!   `NetChannelVar`/`ViaVar`/`CapacityConstraint`/`DiffPairConstraint`/
//!   `LayerConstraint` objects from the skeletons/nets/widths/rules/diff-
//!   pairs/pcb inputs — including the geographic-pruning filter
//!   (`_is_candidate_edge`), the bundle-channel-var path, the
//!   net-index/bundle-id isolation, and the via-anchor node ordering —
//!   is [`ModelBuilder::build`] below.
//! - **The PCL application (`_apply_pcl_constraints`) stays Python.** It
//!   constructs `temper_placer.pcl.constraints.CompilationContext` /
//!   `CompilationTarget` objects and calls `pcl_constraints.compile(...)`
//!   — the PCL compiler is Python-owned (JUSTIFIED-KEEP), and the
//!   exceptions it raises are caught and reported via `warnings.warn`.
//!   The shim's `build()` runs the Rust build, then applies PCL
//!   constraints onto the returned model with the pre-migration code.
//! - **The `TEMPER_MODEL_TRACE` build summary and the R10 non-emptiness
//!   precondition stay Python** (the shim's `build()`): the R10 check and
//!   its message interleave with the PCL step, and the trace summary
//!   counts the *post-PCL* model. The mid-loop `TEMPER_MODEL_TRACE`
//!   progress prints are dropped — they were U5 OOM-instrumentation for a
//!   Python loop; the loop now lives in Rust, so per-iteration progress
//!   output is a Rust concern and the surviving summary line (the one
//!   that records the completed model) is unchanged.
//! - **The ortools boundary stays Python untouched**: `placer/cp_sat/
//!   {model,_encoder_solve,unsat}.py` are not consumed by this module and
//!   are outside Phase E1's file ownership (plan D4 KEEP verdict). The
//!   model this builder returns is consumed by
//!   `temper_rust_router.solve_topology_rust` (the Rust CDCL boundary) —
//!   the `getattr` surface (`name`/`net_idx`/`channel_id`/`capacity`/
//!   `slack_factor`/`terms`/`p_var`/`n_var`/`allowed`/`group_a_indices`/
//!   `group_b_indices`/`min_slots`) is exposed exactly as the bridge
//!   `temper-rust-router/src/types_py_bridge.rs` reads it.
//! - **`ConstraintGenerationStage` / `validate_constraint_generation`** —
//!   `Stage`/`BoardState` pipeline glue — stay Python in the shim.
//! - **The `esl()`/`ESL_REGISTRY` ESL machinery is retired** (documented
//!   in the shim): its only consumers (`router_v6/esl.py`, `bmc.py`) were
//!   deleted before this migration, no caller remains, and the ESL
//!   predicate *closures* cannot be represented as pyclass methods anyway.
//!   The shim keeps the `ESL_REGISTRY` name populated with the three
//!   constraint classes it mapped pre-migration.
//!
//! # Bit-exactness notes
//!
//! - The edge-identity kernel (`canonical_channel_edges`) is the
//!   already-pinned Rust kernel in `constraint_model.rs`; the builder
//!   feeds it the edges in the networkx iteration order (iterating the
//!   live `graph.edges` view, never a copied container).
//! - Iteration order is preserved everywhere the oracle's output depends
//!   on it: `skeletons.items()` and `channel_widths` dict insertion order,
//!   net list order, `bundle_id_for_net` insertion order (for the
//!   left-to-right `sum` of a bundle's member widths), and the stable
//!   `sorted()` of unique bundle ids and of the union of skeleton nodes
//!   (the via-anchor list). The union-node sort uses a stable
//!   `partial_cmp`-with-`Equal` fallback exactly like Python's `sorted`
//!   treats NaN/incomparable elements; the tie-break *input* order can
//!   only differ for NaN or `-0.0`/`0.0` nodes, which real boards never
//!   carry (documented; PBT avoids them).
//! - The via-anchor id `f"VIA_N{i}_{node[0]:.2f}_{node[1]:.2f}"` is
//!   `format!("{:.2}")` — byte-identical over 250,005 adversarial samples
//!   on this host (the B3 argument from `constraint_model.rs`).
//! - `pin_world_position` is NOT reimplemented: the builder calls the
//!   existing `temper_geometry.pin_world_position_at_py` kernel (the same
//!   function `core/pin_geometry.py`'s `pin_world_position` delegates to),
//!   with the same resolved arguments, so the world positions are bit-
//!   identical by construction.
//! - Capacity values come from the live `ChannelWidths.edge_widths` dict
//!   (both orientations, reversed lookup with the `0.0` default); net
//!   widths come from `design_rules.get_rules_for_net(name)` with the
//!   same `trace_width_mm + clearance_mm` addition order.
//!
//! # Panic policy (G7)
//!
//! Every `#[pymethods]` entry point is wrapped in [`guard`] (`catch_unwind`);
//! no `unwrap`/`expect` outside `#[cfg(test)]` (crate clippy lint).

use std::collections::{BTreeSet, HashMap};
use std::panic::AssertUnwindSafe;

use pyo3::create_exception;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyModule, PyTuple};

use crate::constraint_model::{EdgeRow, canonical_channel_edges, is_candidate_edge};

create_exception!(
    temper_design_bundle_python.model_builder,
    ConstraintModelEmptyError,
    PyRuntimeError,
    "ModelBuilder.build() produced a zero-variable model from a non-empty skeleton set."
);

/// Wrap a pyo3 boundary body so a Rust panic surfaces as a Python
/// `RuntimeError` instead of aborting the interpreter (G7 / R1g
/// `catch_unwind` at every pyo3 boundary).
fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match temper_py_bridge::catch_unwind(AssertUnwindSafe(body)) {
        Ok(result) => result,
        Err(payload) => Err(temper_py_bridge::panic_to_err(payload)),
    }
}

/// `_DEFAULT_PRUNE_K_FACTOR` as committed (matches
/// `temper-rust-router-core::pruning::PruningParams::k_factor`).
const PRUNE_K_FACTOR: f64 = 2.0;
/// `_DEFAULT_PRUNE_M_MIN` as committed.
const PRUNE_M_MIN: f64 = 30.0;

// ---------------------------------------------------------------------------
// Variable pyclasses (mirror `Variable` and its subclasses)
// ---------------------------------------------------------------------------

/// `Variable` base: `name` + `var_type`.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct Variable {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub var_type: String,
}

#[pymethods]
impl Variable {
    #[new]
    #[pyo3(signature = (*, name, var_type))]
    fn new(name: String, var_type: String) -> Self {
        Self { name, var_type }
    }
}

/// `NetChannelVar`: `uses[net_id, channel_id]` boolean variable.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct NetChannelVar {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub var_type: String,
    #[pyo3(get)]
    pub net_idx: i64,
    #[pyo3(get)]
    pub channel_id: String,
}

#[pymethods]
impl NetChannelVar {
    #[new]
    #[pyo3(signature = (*, name, net_idx, channel_id, var_type = "bool".to_owned()))]
    fn new(name: String, net_idx: i64, channel_id: String, var_type: String) -> Self {
        Self { name, var_type, net_idx, channel_id }
    }
}

/// `NetLayerVar`: `layer[net_id, segment_id]` integer variable.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct NetLayerVar {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub var_type: String,
    #[pyo3(get)]
    pub net_idx: i64,
    #[pyo3(get)]
    pub segment_id: String,
}

#[pymethods]
impl NetLayerVar {
    #[new]
    #[pyo3(signature = (*, name, net_idx, segment_id, var_type = "int".to_owned()))]
    fn new(name: String, net_idx: i64, segment_id: String, var_type: String) -> Self {
        Self { name, var_type, net_idx, segment_id }
    }
}

/// `ViaVar`: `via[net_id, location_id]` boolean variable. Unconstrained by
/// every consumer (see `enable_via_vars`'s opt-in default).
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct ViaVar {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub var_type: String,
    #[pyo3(get)]
    pub net_idx: i64,
    #[pyo3(get)]
    pub location_id: String,
}

#[pymethods]
impl ViaVar {
    #[new]
    #[pyo3(signature = (*, name, net_idx, location_id, var_type = "bool".to_owned()))]
    fn new(name: String, net_idx: i64, location_id: String, var_type: String) -> Self {
        Self { name, var_type, net_idx, location_id }
    }
}

/// `OrderVar`: `order[net1_idx, net2_idx, channel_id]` boolean variable.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct OrderVar {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub var_type: String,
    #[pyo3(get)]
    pub net1_idx: i64,
    #[pyo3(get)]
    pub net2_idx: i64,
    #[pyo3(get)]
    pub channel_id: String,
}

#[pymethods]
impl OrderVar {
    #[new]
    #[pyo3(signature = (*, name, net1_idx, net2_idx, channel_id, var_type = "bool".to_owned()))]
    fn new(
        name: String,
        net1_idx: i64,
        net2_idx: i64,
        channel_id: String,
        var_type: String,
    ) -> Self {
        Self { name, var_type, net1_idx, net2_idx, channel_id }
    }
}

// ---------------------------------------------------------------------------
// Constraint pyclasses (mirror `Constraint` and its subclasses)
// ---------------------------------------------------------------------------

/// `Constraint` base: `name` + `description`.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct Constraint {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
}

#[pymethods]
impl Constraint {
    #[new]
    #[pyo3(signature = (*, name, description = "".to_owned()))]
    fn new(name: String, description: String) -> Self {
        Self { name, description }
    }
}

/// `CapacityConstraint`: `sum(uses[n, c] * width[n]) <= capacity[c] * slack`.
///
/// The AtMostK sequential-counter soundness proof (R24 item 1, re-homed
/// 2026-08-02 from `docs/solutions/logic-errors/unsound-atmostk-capacity-
/// encoding.md`) is documented in the pre-migration source; this pyclass is
/// the data carrier for that constraint, consumed by
/// `temper_rust_router::solve_topology_rust` (the CNF encoding lives there).
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug)]
pub struct CapacityConstraint {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub channel_id: String,
    #[pyo3(get)]
    pub capacity: f64,
    #[pyo3(get)]
    pub slack_factor: f64,
    terms: Vec<(Py<PyAny>, f64)>,
}

#[pymethods]
impl CapacityConstraint {
    #[new]
    #[pyo3(signature = (*, name, channel_id, capacity, slack_factor, terms, description = "".to_owned()))]
    fn new(
        name: String,
        channel_id: String,
        capacity: f64,
        slack_factor: f64,
        terms: Vec<(Bound<'_, PyAny>, f64)>,
        description: String,
    ) -> Self {
        Self {
            name,
            description,
            channel_id,
            capacity,
            slack_factor,
            terms: terms
                .into_iter()
                .map(|(v, w)| (v.unbind(), w))
                .collect(),
        }
    }

    /// The `(variable, coefficient/width)` term list, as a Python list of
    /// 2-tuples — the exact shape `types_py_bridge.rs` iterates.
    #[getter]
    fn terms(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let list = PyList::empty(py);
            for (var, width) in &self.terms {
                let var_obj = var.clone_ref(py).into_bound(py);
                let width_obj = width.into_pyobject(py)?.into_any();
                let tup = PyTuple::new(py, [var_obj, width_obj])?;
                list.append(tup)?;
            }
            Ok(list.unbind())
        })
    }
}

/// `DiffPairConstraint`: `uses[p_net, c] == uses[n_net, c]`.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug)]
pub struct DiffPairConstraint {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub channel_id: String,
    #[pyo3(get)]
    pub p_net_idx: i64,
    #[pyo3(get)]
    pub n_net_idx: i64,
    p_var: Py<PyAny>,
    n_var: Py<PyAny>,
}

#[pymethods]
impl DiffPairConstraint {
    #[new]
    #[pyo3(signature = (*, name, channel_id, p_net_idx, n_net_idx, p_var, n_var, description = "".to_owned()))]
    fn new(
        name: String,
        channel_id: String,
        p_net_idx: i64,
        n_net_idx: i64,
        p_var: Bound<'_, PyAny>,
        n_var: Bound<'_, PyAny>,
        description: String,
    ) -> Self {
        Self {
            name,
            description,
            channel_id,
            p_net_idx,
            n_net_idx,
            p_var: p_var.unbind(),
            n_var: n_var.unbind(),
        }
    }

    #[getter]
    fn p_var(&self, py: Python<'_>) -> Py<PyAny> {
        self.p_var.clone_ref(py)
    }

    #[getter]
    fn n_var(&self, py: Python<'_>) -> Py<PyAny> {
        self.n_var.clone_ref(py)
    }
}

/// `LayerConstraint`: `uses[n, c] == value` (restrict a net's layer use).
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct LayerConstraint {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub net_idx: i64,
    #[pyo3(get)]
    pub channel_id: String,
    #[pyo3(get)]
    pub allowed: bool,
}

#[pymethods]
impl LayerConstraint {
    #[new]
    #[pyo3(signature = (*, name, net_idx, channel_id, allowed, description = "".to_owned()))]
    fn new(name: String, net_idx: i64, channel_id: String, allowed: bool, description: String) -> Self {
        Self { name, description, net_idx, channel_id, allowed }
    }
}

/// `ChannelSeparationConstraint`: group A / group B must not share channels
/// within `min_slots` of each other.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Clone)]
pub struct ChannelSeparationConstraint {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub channel_id: String,
    #[pyo3(get)]
    pub group_a_indices: Vec<i64>,
    #[pyo3(get)]
    pub group_b_indices: Vec<i64>,
    #[pyo3(get)]
    pub min_slots: i64,
}

#[pymethods]
impl ChannelSeparationConstraint {
    #[new]
    #[pyo3(signature = (
        *,
        name,
        group_a_indices,
        group_b_indices,
        min_slots,
        channel_id,
        description = "".to_owned()
    ))]
    fn new(
        name: String,
        group_a_indices: Vec<i64>,
        group_b_indices: Vec<i64>,
        min_slots: i64,
        channel_id: String,
        description: String,
    ) -> Self {
        Self {
            name,
            description,
            group_a_indices,
            group_b_indices,
            min_slots,
            channel_id,
        }
    }
}

// ---------------------------------------------------------------------------
// ConstraintModel — the variable/constraint registry
// ---------------------------------------------------------------------------

/// `ConstraintModel`: the SAT/SMT constraint model registry.
///
/// `net_channel_vars` and `bundle_channel_vars` are kept SEPARATE (the
/// 2026-08-07 Sec 3.3 net-index/bundle-id collision fix): bundle variables
/// carry `var_type == "bundle"` and are keyed by `(bundle_id, channel_id)`,
/// never by a real net index.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Default)]
pub struct ConstraintModel {
    variables: Vec<Py<PyAny>>,
    constraints: Vec<Py<PyAny>>,
    net_channel_vars: HashMap<(i64, String), Py<PyAny>>,
    bundle_channel_vars: HashMap<(i64, String), Py<PyAny>>,
    via_vars: HashMap<(i64, String), Py<PyAny>>,
}

#[pymethods]
impl ConstraintModel {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    /// `add_variable`: append and route into the type-appropriate dict.
    fn add_variable(&mut self, var: Bound<'_, PyAny>) -> PyResult<()> {
        guard(|| {
            if var.is_instance_of::<NetChannelVar>() {
                let v = var.extract::<PyRef<'_, NetChannelVar>>()?;
                let key = (v.net_idx, v.channel_id.clone());
                if v.var_type == "bundle" {
                    self.bundle_channel_vars.insert(key, var.clone().unbind());
                } else {
                    self.net_channel_vars.insert(key, var.clone().unbind());
                }
            } else if var.is_instance_of::<ViaVar>() {
                let v = var.extract::<PyRef<'_, ViaVar>>()?;
                self.via_vars
                    .insert((v.net_idx, v.location_id.clone()), var.clone().unbind());
            }
            self.variables.push(var.unbind());
            Ok(())
        })
    }

    /// `add_constraint`: append a constraint.
    fn add_constraint(&mut self, constraint: Bound<'_, PyAny>) -> PyResult<()> {
        guard(|| {
            self.constraints.push(constraint.unbind());
            Ok(())
        })
    }

    /// `variable_count`.
    #[getter]
    fn variable_count(&self) -> usize {
        self.variables.len()
    }

    /// `constraint_count`.
    #[getter]
    fn constraint_count(&self) -> usize {
        self.constraints.len()
    }

    /// `variables` — a fresh Python list per access (like the pre-migration
    /// `list[Variable]` field).
    #[getter]
    fn variables(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let list = PyList::empty(py);
            for v in &self.variables {
                list.append(v.clone_ref(py))?;
            }
            Ok(list.unbind())
        })
    }

    /// `constraints` — a fresh Python list per access.
    #[getter]
    fn constraints(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let list = PyList::empty(py);
            for c in &self.constraints {
                list.append(c.clone_ref(py))?;
            }
            Ok(list.unbind())
        })
    }

    #[getter(net_channel_vars)]
    fn net_channel_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| py_dict_from_vars(py, &self.net_channel_vars))
    }

    #[getter(bundle_channel_vars)]
    fn bundle_channel_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| py_dict_from_vars(py, &self.bundle_channel_vars))
    }

    #[getter(via_vars)]
    fn via_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| py_dict_from_vars(py, &self.via_vars))
    }
}

fn py_dict_from_vars(
    py: Python<'_>,
    vars: &HashMap<(i64, String), Py<PyAny>>,
) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    for ((idx, channel), var) in vars {
        let idx_obj = idx.into_pyobject(py)?.into_any();
        let channel_obj = channel.into_pyobject(py)?.into_any();
        let key = PyTuple::new(py, [idx_obj, channel_obj])?;
        d.set_item(key, var)?;
    }
    Ok(d.unbind())
}

// ---------------------------------------------------------------------------
// ModelBuilder — the build() orchestration
// ---------------------------------------------------------------------------

/// `ModelBuilder`: mirror of `router_v6.constraint_model.ModelBuilder`.
///
/// Holds the Python input objects opaquely (`Py<PyDict>`/`Py<PyList>`/
/// `Py<PyAny>`) so iteration order and attribute reads are the live Python
/// ones — the same objects the pre-migration builder read.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
pub struct ModelBuilder {
    skeletons: Py<PyDict>,
    nets: Py<PyList>,
    channel_widths: Py<PyDict>,
    design_rules: Option<Py<PyAny>>,
    diff_pairs: Py<PyList>,
    pcb: Option<Py<PyAny>>,
    _pcl_constraints: Option<Py<PyAny>>,
    enable_bundling: bool,
    bundle_manifest: Option<Py<PyAny>>,
    enable_geographic_pruning: bool,
    enable_via_vars: bool,
    model: Py<ConstraintModel>,
}

impl ModelBuilder {
    fn skeleton_edges(&self, skeleton: &Bound<'_, PyAny>, layer: &str) -> PyResult<Vec<EdgeRow>> {
        let graph = skeleton.getattr("graph")?;
        let edges_view = graph.getattr("edges")?;
        let mut edges: Vec<((f64, f64), (f64, f64))> = Vec::new();
        for item in edges_view.try_iter()? {
            let item = item?;
            let u: (f64, f64) = item.get_item(0)?.extract()?;
            let v: (f64, f64) = item.get_item(1)?.extract()?;
            edges.push((u, v));
        }
        Ok(canonical_channel_edges(layer, &edges))
    }

    /// `_pin_world_positions`: the world position of every pin on `net`,
    /// via the existing `temper_geometry.pin_world_position_at_py` kernel.
    fn pin_world_positions(&self, py: Python<'_>, net: &Bound<'_, PyAny>) -> PyResult<Vec<(f64, f64)>> {
        let net_name: String = net.getattr("name")?.extract()?;
        let mut positions = Vec::new();
        if let Some(pcb) = &self.pcb {
            let pcb = pcb.bind(py);
            let kernel = PyModule::import(py, "temper_geometry")?.getattr("pin_world_position_at_py")?;
            let components = pcb.getattr("components")?;
            for comp in components.try_iter()? {
                let comp = comp?;
                for pin in comp.getattr("pins")?.try_iter()? {
                    let pin = pin?;
                    let pin_net: Option<String> = pin.getattr("net")?.extract()?;
                    if pin_net.as_deref() == Some(net_name.as_str()) {
                        let pos: (f64, f64) = kernel.call1((pin, comp.clone()))?.extract()?;
                        positions.push(pos);
                    }
                }
            }
        }
        Ok(positions)
    }

    /// Pre-computed pin positions per net index (geographic-pruning paths).
    fn net_pins(&self, py: Python<'_>) -> PyResult<Vec<Vec<(f64, f64)>>> {
        let mut out = Vec::new();
        for net in self.nets.bind(py).iter() {
            out.push(self.pin_world_positions(py, &net)?);
        }
        Ok(out)
    }

    /// `net_to_idx`: net name -> index.
    fn net_to_idx(&self, py: Python<'_>) -> PyResult<HashMap<String, i64>> {
        let mut map = HashMap::new();
        for (i, net) in self.nets.bind(py).iter().enumerate() {
            let name: String = net.getattr("name")?.extract()?;
            map.insert(name, i as i64);
        }
        Ok(map)
    }

    /// `_net_width`: `rule.trace_width_mm + rule.clearance_mm`.
    fn net_width(&self, py: Python<'_>, net_idx: usize) -> PyResult<f64> {
        let net = self.nets.bind(py).get_item(net_idx)?;
        let name: String = net.getattr("name")?.extract()?;
        let design_rules = self
            .design_rules
            .as_ref()
            .ok_or_else(|| PyRuntimeError::new_err("design_rules is None"))?;
        let rule = design_rules.bind(py).call_method1("get_rules_for_net", (name,))?;
        let trace_width: f64 = rule.getattr("trace_width_mm")?.extract()?;
        let clearance: f64 = rule.getattr("clearance_mm")?.extract()?;
        Ok(trace_width + clearance)
    }

    fn model_net_var(&self, py: Python<'_>, net_idx: i64, edge_id: &str) -> PyResult<Option<Py<PyAny>>> {
        let m = self.model.bind(py).borrow();
        Ok(m.net_channel_vars.get(&(net_idx, edge_id.to_string())).map(|v| v.clone_ref(py)))
    }

    fn model_bundle_var(&self, py: Python<'_>, bundle_id: i64, edge_id: &str) -> PyResult<Option<Py<PyAny>>> {
        let m = self.model.bind(py).borrow();
        Ok(m.bundle_channel_vars.get(&(bundle_id, edge_id.to_string())).map(|v| v.clone_ref(py)))
    }

    fn push_channel_var(&mut self, py: Python<'_>, var: NetChannelVar) -> PyResult<()> {
        let pyvar = Py::new(py, var)?;
        let (net_idx, channel_id, var_type);
        {
            let r = pyvar.bind(py).borrow();
            net_idx = r.net_idx;
            channel_id = r.channel_id.clone();
            var_type = r.var_type.clone();
        }
        let mut m = self.model.bind(py).borrow_mut();
        m.variables.push(pyvar.clone_ref(py).into_any());
        if var_type == "bundle" {
            m.bundle_channel_vars.insert((net_idx, channel_id), pyvar.into_any());
        } else {
            m.net_channel_vars.insert((net_idx, channel_id), pyvar.into_any());
        }
        Ok(())
    }

    fn push_via_var(&mut self, py: Python<'_>, var: ViaVar) -> PyResult<()> {
        let pyvar = Py::new(py, var)?;
        let (net_idx, location_id);
        {
            let r = pyvar.bind(py).borrow();
            net_idx = r.net_idx;
            location_id = r.location_id.clone();
        }
        let mut m = self.model.bind(py).borrow_mut();
        m.variables.push(pyvar.clone_ref(py).into_any());
        m.via_vars.insert((net_idx, location_id), pyvar.into_any());
        Ok(())
    }

    fn push_constraint(&mut self, py: Python<'_>, constraint: Py<PyAny>) -> PyResult<()> {
        let mut m = self.model.bind(py).borrow_mut();
        m.constraints.push(constraint);
        Ok(())
    }

    /// `_create_channel_vars`.
    fn create_channel_vars(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.enable_bundling && self.bundle_manifest.is_some() {
            self.create_bundle_channel_vars(py)
        } else {
            self.create_per_net_channel_vars(py)
        }
    }

    /// `_create_per_net_channel_vars`: one `NetChannelVar` per (net, edge),
    /// optionally filtered by the geographic-pruning predicate.
    fn create_per_net_channel_vars(&mut self, py: Python<'_>) -> PyResult<()> {
        let pruning = self.enable_geographic_pruning && self.pcb.is_some();
        let net_pins = if pruning { Some(self.net_pins(py)?) } else { None };
        let nets = self.nets.bind(py).clone();
        let skeletons = self.skeletons.bind(py).clone();

        for (net_idx, _net) in nets.iter().enumerate() {
            for (layer_name, skeleton) in skeletons.iter() {
                let layer_name = layer_name.extract::<String>()?;
                for (edge_id, u, v) in self.skeleton_edges(&skeleton, &layer_name)? {
                    if pruning {
                        let pins = net_pins
                            .as_ref()
                            .ok_or_else(|| PyRuntimeError::new_err("net_pins missing"))?
                            .get(net_idx)
                            .ok_or_else(|| {
                                PyRuntimeError::new_err("net_pins index out of range")
                            })?;
                        if !is_candidate_edge(
                            pins, u.0, u.1, v.0, v.1, PRUNE_K_FACTOR, PRUNE_M_MIN,
                        ) {
                            continue;
                        }
                    }
                    let var = NetChannelVar {
                        name: format!("uses_N{net_idx}_{edge_id}"),
                        var_type: "bool".to_string(),
                        net_idx: net_idx as i64,
                        channel_id: edge_id,
                    };
                    self.push_channel_var(py, var)?;
                }
            }
        }
        Ok(())
    }

    /// `_create_bundle_channel_vars`: one shared `NetChannelVar` per
    /// (bundle, edge) with `var_type="bundle"`, plus per-net vars for the
    /// unbundled nets.
    fn create_bundle_channel_vars(&mut self, py: Python<'_>) -> PyResult<()> {
        let manifest = match &self.bundle_manifest {
            Some(m) => m.bind(py),
            None => return Ok(()),
        };
        let bfn = match manifest.getattr("bundle_id_for_net") {
            Ok(v) if !v.is_none() => v.cast::<PyDict>()?.clone(),
            _ => PyDict::new(py),
        };
        // Preserve the insertion order of `bundle_id_for_net` (it drives the
        // bundle_members width-sum order in `_create_capacity_constraints`).
        let mut bundle_id_for_net: Vec<(i64, i64)> = Vec::new();
        for (k, v) in bfn.iter() {
            bundle_id_for_net.push((k.extract()?, v.extract()?));
        }
        let unique_bundle_ids: BTreeSet<i64> =
            bundle_id_for_net.iter().map(|(_, bid)| *bid).collect();
        let nets = self.nets.bind(py).clone();
        let skeletons = self.skeletons.bind(py).clone();

        for bid in &unique_bundle_ids {
            for (layer_name, skeleton) in skeletons.iter() {
                let layer_name = layer_name.extract::<String>()?;
                for (edge_id, _u, _v) in self.skeleton_edges(&skeleton, &layer_name)? {
                    let var = NetChannelVar {
                        name: format!("uses_B{bid}_{edge_id}"),
                        var_type: "bundle".to_string(),
                        net_idx: *bid,
                        channel_id: edge_id,
                    };
                    self.push_channel_var(py, var)?;
                }
            }
        }

        // Per-net vars for nets not in any bundle.
        let bundled_net_indices: std::collections::HashSet<i64> =
            bundle_id_for_net.iter().map(|(net_idx, _)| *net_idx).collect();
        for (net_idx, _net) in nets.iter().enumerate() {
            if bundled_net_indices.contains(&(net_idx as i64)) {
                continue;
            }
            for (layer_name, skeleton) in skeletons.iter() {
                let layer_name = layer_name.extract::<String>()?;
                for (edge_id, _u, _v) in self.skeleton_edges(&skeleton, &layer_name)? {
                    let var = NetChannelVar {
                        name: format!("uses_N{net_idx}_{edge_id}"),
                        var_type: "bool".to_string(),
                        net_idx: net_idx as i64,
                        channel_id: edge_id,
                    };
                    self.push_channel_var(py, var)?;
                }
            }
        }
        Ok(())
    }

    /// `_create_via_vars`: one `ViaVar` per (net, unique node location),
    /// optionally filtered by the pruning predicate with a degenerate
    /// (zero-length) edge at the node.
    fn create_via_vars(&mut self, py: Python<'_>) -> PyResult<()> {
        let skeletons = self.skeletons.bind(py).clone();
        let mut nodes: Vec<(f64, f64)> = Vec::new();
        for (_layer, skeleton) in skeletons.iter() {
            let graph = skeleton.getattr("graph")?;
            let nodes_view = graph.getattr("nodes")?;
            for node in nodes_view.try_iter()? {
                let node = node?;
                nodes.push(node.extract::<(f64, f64)>()?);
            }
        }
        // `sorted(all_nodes)`: stable; NaN/incomparable elements keep input
        // order exactly like Python's Timsort (see module docstring).
        nodes.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        nodes.dedup_by(|a, b| a.0 == b.0 && a.1 == b.1);

        let pruning = self.enable_geographic_pruning && self.pcb.is_some();
        let net_pins = if pruning { Some(self.net_pins(py)?) } else { None };
        let nets = self.nets.bind(py).clone();

        for (net_idx, _net) in nets.iter().enumerate() {
            for (i, node) in nodes.iter().enumerate() {
                if pruning {
                    let pins = net_pins
                        .as_ref()
                        .ok_or_else(|| PyRuntimeError::new_err("net_pins missing"))?
                        .get(net_idx)
                        .ok_or_else(|| {
                            PyRuntimeError::new_err("net_pins index out of range")
                        })?;
                    if !is_candidate_edge(
                        pins, node.0, node.1, node.0, node.1, PRUNE_K_FACTOR, PRUNE_M_MIN,
                    ) {
                        continue;
                    }
                }
                let node_id = format!("VIA_N{i}_{:.2}_{:.2}", node.0, node.1);
                let var = ViaVar {
                    name: format!("via_N{net_idx}_{node_id}"),
                    var_type: "bool".to_string(),
                    net_idx: net_idx as i64,
                    location_id: node_id,
                };
                self.push_via_var(py, var)?;
            }
        }
        Ok(())
    }

    /// `_create_capacity_constraints`: per-channel AtMostK capacity terms.
    fn create_capacity_constraints(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.channel_widths.bind(py).is_empty() || self.design_rules.is_none() {
            return Ok(());
        }
        let slack_factor = 0.8;

        // Bundle membership, in `bundle_id_for_net` insertion order.
        let mut bundle_id_for_net: Vec<(i64, i64)> = Vec::new();
        if self.enable_bundling
            && let Some(manifest) = &self.bundle_manifest
            && let Ok(bfn) = manifest.bind(py).getattr("bundle_id_for_net")
            && !bfn.is_none()
        {
            for (k, v) in bfn.cast::<PyDict>()?.iter() {
                bundle_id_for_net.push((k.extract()?, v.extract()?));
            }
        }
        let mut bundle_members: Vec<(i64, Vec<i64>)> = Vec::new();
        for (net_idx, bid) in &bundle_id_for_net {
            match bundle_members.iter_mut().find(|(b, _)| b == bid) {
                Some((_, members)) => members.push(*net_idx),
                None => bundle_members.push((*bid, vec![*net_idx])),
            }
        }

        let skeletons = self.skeletons.bind(py).clone();
        for (layer_name, skeleton) in skeletons.iter() {
            let layer_name = layer_name.extract::<String>()?;
            let widths = match self.channel_widths.bind(py).get_item(&layer_name)? {
                Some(w) if !w.is_none() => w,
                _ => continue,
            };
            for (edge_id, u, v) in self.skeleton_edges(&skeleton, &layer_name)? {
                let edge_widths = widths.getattr("edge_widths")?;
                let capacity = edge_width_lookup(py, &edge_widths, u, v)?;
                if capacity <= 0.0 {
                    continue;
                }

                let mut terms: Vec<(Py<PyAny>, f64)> = Vec::new();
                for (bid, members) in &bundle_members {
                    let bvar = match self.model_bundle_var(py, *bid, &edge_id)? {
                        Some(v) => v,
                        None => continue,
                    };
                    let mut bundle_width = 0.0;
                    for ni in members {
                        bundle_width += self.net_width(py, *ni as usize)?;
                    }
                    terms.push((bvar, bundle_width));
                }

                for net_idx in 0..self.nets.bind(py).len() {
                    if bundle_id_for_net.iter().any(|(n, _)| *n == net_idx as i64) {
                        continue;
                    }
                    if let Some(var) = self.model_net_var(py, net_idx as i64, &edge_id)? {
                        let width = self.net_width(py, net_idx)?;
                        terms.push((var, width));
                    } else if self.enable_geographic_pruning && self.pcb.is_some() {
                        // Defense-in-depth silence: with pruning active, a
                        // net with no variable on this edge legitimately has
                        // none (the predicate already rejected it).
                    }
                }

                if !terms.is_empty() {
                    let constraint = CapacityConstraint {
                        name: format!("cap_{edge_id}"),
                        description: String::new(),
                        channel_id: edge_id,
                        capacity,
                        slack_factor,
                        terms,
                    };
                    self.push_constraint(py, Py::new(py, constraint)?.into_any())?;
                }
            }
        }
        Ok(())
    }

    /// `_create_diff_pair_constraints`; skipped entirely under bundling.
    fn create_diff_pair_constraints(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.enable_bundling {
            return Ok(());
        }
        let net_to_idx = self.net_to_idx(py)?;
        for pair in self.diff_pairs.bind(py).iter() {
            let p_net: String = pair.getattr("p_net")?.extract()?;
            let n_net: String = pair.getattr("n_net")?.extract()?;
            let (p_idx, n_idx) = match (net_to_idx.get(&p_net), net_to_idx.get(&n_net)) {
                (Some(p), Some(n)) => (*p, *n),
                _ => continue,
            };
            let base_name: String = pair.getattr("base_name")?.extract()?;
            let skeletons = self.skeletons.bind(py).clone();
            for (layer_name, skeleton) in skeletons.iter() {
                let layer_name = layer_name.extract::<String>()?;
                for (edge_id, _u, _v) in self.skeleton_edges(&skeleton, &layer_name)? {
                    if let (Some(p_var), Some(n_var)) = (
                        self.model_net_var(py, p_idx, &edge_id)?,
                        self.model_net_var(py, n_idx, &edge_id)?,
                    ) {
                        let constraint = DiffPairConstraint {
                            name: format!("diff_{base_name}_{edge_id}"),
                            description: String::new(),
                            channel_id: edge_id,
                            p_net_idx: p_idx,
                            n_net_idx: n_idx,
                            p_var,
                            n_var,
                        };
                        self.push_constraint(py, Py::new(py, constraint)?.into_any())?;
                    }
                }
            }
        }
        Ok(())
    }

    /// `_create_layer_constraints`: SMD pins are restricted to their layer;
    /// breakout edges on every OTHER layer get `LayerConstraint(allowed=False)`.
    fn create_layer_constraints(&mut self, py: Python<'_>) -> PyResult<()> {
        let pcb = match &self.pcb {
            Some(p) => p.bind(py),
            None => return Ok(()),
        };
        let net_to_idx = self.net_to_idx(py)?;
        let kernel = PyModule::import(py, "temper_geometry")?.getattr("pin_world_position_at_py")?;

        let components = pcb.getattr("components")?;
        for comp in components.try_iter()? {
            let comp = comp?;
            for pin in comp.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let pin_net: Option<String> = pin.getattr("net")?.extract()?;
                let net_idx = match pin_net.as_deref().and_then(|n| net_to_idx.get(n)) {
                    Some(i) => *i,
                    None => continue,
                };
                let is_pth: bool = pin.getattr("is_pth")?.extract()?;
                if is_pth {
                    continue;
                }
                let target_layer: String = pin.getattr("layer")?.extract()?;
                let pin_pos: (f64, f64) = kernel.call1((pin.clone(), comp.clone()))?.extract()?;

                let skeletons = self.skeletons.bind(py).clone();
                for (layer_name, skeleton) in skeletons.iter() {
                    let layer_name = layer_name.extract::<String>()?;
                    if layer_name == target_layer {
                        continue; // Allowed
                    }
                    for (edge_id, u, v) in self.skeleton_edges(&skeleton, &layer_name)? {
                        let matches = |node: (f64, f64)| {
                            (node.0 - pin_pos.0).abs() < 0.01 && (node.1 - pin_pos.1).abs() < 0.01
                        };
                        if (matches(u) || matches(v))
                            && self.model_net_var(py, net_idx, &edge_id)?.is_some()
                        {
                            let constraint = LayerConstraint {
                                name: format!("layer_restr_N{net_idx}_{edge_id}"),
                                description: String::new(),
                                net_idx,
                                channel_id: edge_id,
                                allowed: false,
                            };
                            self.push_constraint(py, Py::new(py, constraint)?.into_any())?;
                        }
                    }
                }
            }
        }
        Ok(())
    }
}

#[pymethods]
impl ModelBuilder {
    #[new]
    #[allow(clippy::too_many_arguments)]
    #[pyo3(signature = (
        skeletons = None,
        nets = None,
        channel_widths = None,
        design_rules = None,
        diff_pairs = None,
        pcb = None,
        pcl_constraints = None,
        enable_bundling = false,
        bundle_manifest = None,
        enable_geographic_pruning = false,
        enable_via_vars = false
    ))]
    fn new(
        py: Python<'_>,
        skeletons: Option<Bound<'_, PyAny>>,
        nets: Option<Bound<'_, PyAny>>,
        channel_widths: Option<Bound<'_, PyAny>>,
        design_rules: Option<Bound<'_, PyAny>>,
        diff_pairs: Option<Bound<'_, PyAny>>,
        pcb: Option<Bound<'_, PyAny>>,
        pcl_constraints: Option<Bound<'_, PyAny>>,
        enable_bundling: bool,
        bundle_manifest: Option<Bound<'_, PyAny>>,
        enable_geographic_pruning: bool,
        enable_via_vars: bool,
    ) -> PyResult<Self> {
        guard(|| {
            let skeletons = as_dict_or_empty(py, skeletons)?;
            let nets = as_list_or_empty(py, nets)?;
            let channel_widths = as_dict_or_empty(py, channel_widths)?;
            let diff_pairs = as_list_or_empty(py, diff_pairs)?;
            let model = Py::new(py, ConstraintModel::default())?;
            Ok(ModelBuilder {
                skeletons,
                nets,
                channel_widths,
                design_rules: to_option(design_rules)?,
                diff_pairs,
                pcb: to_option(pcb)?,
                _pcl_constraints: to_option(pcl_constraints)?,
                enable_bundling,
                bundle_manifest: to_option(bundle_manifest)?,
                enable_geographic_pruning,
                enable_via_vars,
                model,
            })
        })
    }

    /// `build()`: create all variables and constraints, and return the model.
    ///
    /// Mirrors `ModelBuilder.build()` minus the PCL application (which the
    /// Python shim runs afterwards, since the PCL compiler is Python-owned)
    /// and the R10 emptiness check (also shim-side, where it interleaves
    /// with the PCL step).
    fn build(&mut self, py: Python<'_>) -> PyResult<Py<ConstraintModel>> {
        guard(|| {
            self.create_channel_vars(py)?;
            if self.enable_via_vars {
                self.create_via_vars(py)?;
            }
            self.create_capacity_constraints(py)?;
            self.create_diff_pair_constraints(py)?;
            self.create_layer_constraints(py)?;
            Ok(self.model.clone_ref(py))
        })
    }
}

fn to_option(value: Option<Bound<'_, PyAny>>) -> PyResult<Option<Py<PyAny>>> {
    Ok(match value {
        Some(v) if v.is_none() => None,
        Some(v) => Some(v.unbind()),
        None => None,
    })
}

fn as_dict_or_empty(py: Python<'_>, value: Option<Bound<'_, PyAny>>) -> PyResult<Py<PyDict>> {
    match value {
        Some(v) if !v.is_none() => Ok(v.cast::<PyDict>()?.clone().unbind()),
        _ => Ok(PyDict::new(py).unbind()),
    }
}

fn as_list_or_empty(py: Python<'_>, value: Option<Bound<'_, PyAny>>) -> PyResult<Py<PyList>> {
    match value {
        Some(v) if !v.is_none() => Ok(v.cast::<PyList>()?.clone().unbind()),
        _ => Ok(PyList::empty(py).unbind()),
    }
}

/// `widths.edge_widths.get((u, v)) or .get((v, u), 0.0)` — both
/// orientations, the reversed lookup defaulting to 0.0.
fn edge_width_lookup(
    py: Python<'_>,
    edge_widths: &Bound<'_, PyAny>,
    u: (f64, f64),
    v: (f64, f64),
) -> PyResult<f64> {
    // `widths.edge_widths.get((u, v))` — the dict's own `.get`, so a missing
    // key yields `None` exactly like Python (a missing key must NOT raise).
    let forward: Option<f64> = edge_widths
        .call_method1("get", (tuple_key(py, u, v)?,))?
        .extract()?;
    if let Some(val) = forward {
        return Ok(val);
    }
    let reversed: Option<f64> = edge_widths
        .call_method1("get", (tuple_key(py, v, u)?,))?
        .extract()?;
    Ok(reversed.unwrap_or(0.0))
}

fn tuple_key(py: Python<'_>, a: (f64, f64), b: (f64, f64)) -> PyResult<Py<PyTuple>> {
    let ta = PyTuple::new(py, [a.0, a.1])?;
    let tb = PyTuple::new(py, [b.0, b.1])?;
    Ok(PyTuple::new(py, [ta, tb])?.unbind())
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

/// Registered as the `model_builder` submodule
/// (`temper_design_bundle_python.model_builder`).
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "model_builder")?;
    sub.add_class::<Variable>()?;
    sub.add_class::<NetChannelVar>()?;
    sub.add_class::<NetLayerVar>()?;
    sub.add_class::<ViaVar>()?;
    sub.add_class::<OrderVar>()?;
    sub.add_class::<Constraint>()?;
    sub.add_class::<CapacityConstraint>()?;
    sub.add_class::<DiffPairConstraint>()?;
    sub.add_class::<LayerConstraint>()?;
    sub.add_class::<ChannelSeparationConstraint>()?;
    sub.add_class::<ConstraintModel>()?;
    sub.add_class::<ModelBuilder>()?;
    sub.add(
        "ConstraintModelEmptyError",
        py.get_type::<ConstraintModelEmptyError>(),
    )?;
    module.add_submodule(&sub)
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    #[test]
    fn channel_var_fields() {
        let v = NetChannelVar {
            name: "uses_N0_E".into(),
            var_type: "bool".into(),
            net_idx: 0,
            channel_id: "E".into(),
        };
        assert_eq!(v.name, "uses_N0_E");
        assert_eq!(v.var_type, "bool");
        assert_eq!(v.net_idx, 0);
        assert_eq!(v.channel_id, "E");
    }

    #[test]
    fn via_var_fields() {
        let v = ViaVar {
            name: "via_N0_VIA_N0_0.00_0.00".into(),
            var_type: "bool".into(),
            net_idx: 0,
            location_id: "VIA_N0_0.00_0.00".into(),
        };
        assert_eq!(v.location_id, "VIA_N0_0.00_0.00");
    }

    #[test]
    fn capacity_holds_terms() {
        Python::attach(|py| {
            let v = NetChannelVar {
                name: "uses_N0_E".into(),
                var_type: "bool".into(),
                net_idx: 0,
                channel_id: "E".into(),
            };
            let c = CapacityConstraint {
                name: "cap_E".into(),
                description: String::new(),
                channel_id: "E".into(),
                capacity: 10.0,
                slack_factor: 0.8,
                terms: vec![(Py::new(py, v).unwrap().into_any(), 0.2)],
            };
            assert_eq!(c.terms.len(), 1);
            assert_eq!(c.capacity, 10.0);
        })
    }

    #[test]
    fn model_routes_bundle_and_net_vars() {
        Python::attach(|py| {
            let mut m = ConstraintModel::default();
            let net_var = NetChannelVar {
                name: "uses_N0_E".into(),
                var_type: "bool".into(),
                net_idx: 0,
                channel_id: "E".into(),
            };
            let bundle_var = NetChannelVar {
                name: "uses_B0_E".into(),
                var_type: "bundle".into(),
                net_idx: 0,
                channel_id: "E".into(),
            };
            let _ = m.net_channel_vars.insert(
                (0, "E".into()),
                Py::new(py, net_var).unwrap().into_any(),
            );
            let _ = m.bundle_channel_vars.insert(
                (0, "E".into()),
                Py::new(py, bundle_var).unwrap().into_any(),
            );
            assert_eq!(m.net_channel_vars.len(), 1);
            assert_eq!(m.bundle_channel_vars.len(), 1);
            assert!(m.via_vars.is_empty());
        })
    }
}

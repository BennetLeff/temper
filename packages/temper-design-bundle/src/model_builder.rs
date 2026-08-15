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
//! # Model representation (plan 2026-08-12-002 U1, R1)
//!
//! [`ConstraintModel`] stores variables and constraints **Rust-natively**.
//! Until 2026-08-12 it held `Vec<Py<PyAny>>` — 22,493,900 CPython objects
//! for the production board, each a `#[pyclass]` instance carrying three
//! Rust `String`s, and each variable's `channel_id` stored *twice* (once in
//! the object, once again as a `HashMap<(i64, String), _>` key). MEASURED
//! with `docs/evidence/2026-08-12-router-model-memory-probe.py`: **326.7
//! bytes per variable, 7.35 GB for the full model.**
//!
//! What replaces it:
//!
//! - [`PackedVar`] — 8 bytes: a `u32` net index and a `u32` that packs a
//!   2-bit kind tag with a 30-bit interned-string id.
//! - [`Interner`] — every `channel_id` / `location_id` / diff-pair
//!   `base_name` stored once (204,490 distinct edge ids, not 22.5M copies),
//!   as `Arc<str>` shared between the table and its reverse index.
//! - [`PackedConstraint`] — the three shapes the builder emits, with
//!   capacity terms in a flat `(u32 variable index, f64 width)` arena.
//! - Names are **derived**, not stored: `uses_N{net}_{edge}` /
//!   `uses_B{bundle}_{edge}` / `via_N{net}_{node}` / `cap_{edge}` /
//!   `diff_{base}_{edge}` / `layer_restr_N{net}_{edge}` are exactly what the
//!   builder formats, so the packed fields reproduce them byte-for-byte.
//!
//! **This is a representation change and nothing else.** No algorithm
//! moves, no output moves, and every pyo3 getter keeps its signature and
//! its semantics — `variables` / `constraints` / `net_channel_vars` /
//! `terms` / `p_var` still hand back the same pyclass instances with the
//! same field values in the same order, rebuilt on demand (they already
//! rebuilt a fresh `PyList` on every access). Two escape hatches keep that
//! promise total rather than approximate:
//!
//! - Anything `add_variable` cannot reproduce from packed fields — a
//!   `net_idx` outside `u32`, an unexpected `var_type`, a hand-written
//!   name such as `NetChannelVar(name="BOGUS", …)` — is retained as the
//!   caller's original object (`VarKind::Foreign`) and still routed into
//!   the same dict. No production path takes it.
//! - `add_constraint` always retains the caller's object verbatim: its two
//!   users are the PCL lowering paths, which hand over constraints
//!   referencing objects the model knows nothing about (a
//!   `DiffPairConstraint` whose `p_var` is a bare `str`, for one).
//!
//! The one observable difference is object *identity*: two reads of
//! `.variables` used to yield the same instances and now yield
//! equal-valued fresh ones. Nothing in the tree compares model variables
//! by identity or uses one as a dict key, and these pyclasses define
//! neither `__eq__` nor `__hash__` for such a comparison to have been
//! meaningful through.
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

use std::collections::{BTreeSet, HashMap, HashSet};
use std::panic::AssertUnwindSafe;
use std::sync::Arc;

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
    terms: CapacityTerms,
}

/// Where a `CapacityConstraint`'s `(variable, width)` terms live.
///
/// A constraint built from Python owns its terms as the Python objects the
/// caller passed (`Owned`, the pre-U1 shape, byte-for-byte). A constraint
/// *reconstructed from the model* borrows them (`Packed`): the model holds
/// the terms as `(u32 variable index, f64 width)` in a flat arena and the
/// `terms` getter materialises the 2-tuples on demand. That laziness is
/// load-bearing — materialising `list(model.constraints)` would otherwise
/// build one Python variable object per term, i.e. exactly the 22.5M
/// objects U1 exists to delete.
#[derive(Debug)]
enum CapacityTerms {
    Owned(Vec<(Py<PyAny>, f64)>),
    Packed { model: Py<ConstraintModel>, start: u32, len: u32 },
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
            terms: CapacityTerms::Owned(
                terms.into_iter().map(|(v, w)| (v.unbind(), w)).collect(),
            ),
        }
    }

    /// The `(variable, coefficient/width)` term list, as a Python list of
    /// 2-tuples — the exact shape `types_py_bridge.rs` iterates.
    #[getter]
    fn terms(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let list = PyList::empty(py);
            match &self.terms {
                CapacityTerms::Owned(terms) => {
                    for (var, width) in terms {
                        append_term(py, &list, var.clone_ref(py), *width)?;
                    }
                }
                CapacityTerms::Packed { model, start, len } => {
                    let m = model.bind(py).borrow();
                    for offset in 0..*len {
                        let (var_idx, width) = m.term(*start + offset)?;
                        let var = m.variable_object(py, var_idx)?;
                        append_term(py, &list, var, width)?;
                    }
                }
            }
            Ok(list.unbind())
        })
    }
}

fn append_term(
    py: Python<'_>,
    list: &Bound<'_, PyList>,
    var: Py<PyAny>,
    width: f64,
) -> PyResult<()> {
    let width_obj = width.into_pyobject(py)?.into_any();
    list.append(PyTuple::new(py, [var.into_bound(py), width_obj])?)
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
    p_var: VarSlot,
    n_var: VarSlot,
}

/// Where a `DiffPairConstraint`'s `p_var`/`n_var` live — the same
/// owned-vs-borrowed split as [`CapacityTerms`], for the same reason.
///
/// Note the `Owned` arm carries an arbitrary object, not necessarily a
/// variable: `_pipeline_route._augment_with_pcl_constraints` constructs
/// `DiffPairConstraint(p_var=<str>, n_var=<str>)` from the PCL compiler's
/// lowered output.
#[derive(Debug)]
enum VarSlot {
    Owned(Py<PyAny>),
    Packed { model: Py<ConstraintModel>, idx: u32 },
}

impl VarSlot {
    fn resolve(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        match self {
            VarSlot::Owned(obj) => Ok(obj.clone_ref(py)),
            VarSlot::Packed { model, idx } => {
                model.bind(py).borrow().variable_object(py, *idx)
            }
        }
    }
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
            p_var: VarSlot::Owned(p_var.unbind()),
            n_var: VarSlot::Owned(n_var.unbind()),
        }
    }

    #[getter]
    fn p_var(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        guard(|| self.p_var.resolve(py))
    }

    #[getter]
    fn n_var(&self, py: Python<'_>) -> PyResult<Py<PyAny>> {
        guard(|| self.n_var.resolve(py))
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

// ---------------------------------------------------------------------------
// The Rust-native model representation (plan 2026-08-12-002 U1, R1)
// ---------------------------------------------------------------------------

/// Append-only string interner.
///
/// Every SAT variable's `channel_id` is one of the skeleton's edge ids
/// (204,490 of them on the production board) and every via var's
/// `location_id` is one of the skeleton's node ids — so the *distinct*
/// string count is four orders of magnitude below the *variable* count
/// (22,493,900). Pre-U1 each of those strings was stored twice per
/// variable: once inside the `NetChannelVar` CPython object and once again
/// as the `HashMap<(i64, String), _>` key.
///
/// `Arc<str>` rather than `String` so the table and its reverse index share
/// one allocation per distinct string instead of two.
#[derive(Debug, Default)]
struct Interner {
    values: Vec<Arc<str>>,
    index: HashMap<Arc<str>, u32>,
}

impl Interner {
    /// Interned id for `s`, inserting it if new.
    fn intern(&mut self, s: &str) -> PyResult<u32> {
        if let Some(id) = self.index.get(s) {
            return Ok(*id);
        }
        let id = u32::try_from(self.values.len())
            .ok()
            .filter(|id| *id <= MAX_INTERNED_ID)
            .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: interner exhausted"))?;
        let shared: Arc<str> = Arc::from(s);
        self.values.push(Arc::clone(&shared));
        let _ = self.index.insert(shared, id);
        Ok(id)
    }

    /// Interned id for `s` if it is already present. Never inserts — the
    /// builder's lookups (`model_net_var_idx` and friends) must not grow the
    /// table with edge ids that own no variable.
    fn lookup(&self, s: &str) -> Option<u32> {
        self.index.get(s).copied()
    }

    fn get(&self, id: u32) -> PyResult<&str> {
        self.values
            .get(id as usize)
            .map(|s| &**s)
            .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: bad interned id"))
    }
}

/// Which shape a [`PackedVar`] carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum VarKind {
    /// `NetChannelVar`, `var_type == "bool"`; key is the interned `channel_id`.
    NetChannel = 0,
    /// `NetChannelVar`, `var_type == "bundle"`; key is the interned `channel_id`.
    Bundle = 1,
    /// `ViaVar`, `var_type == "bool"`; key is the interned `location_id`.
    Via = 2,
    /// Anything else `add_variable` was handed: key indexes `foreign_vars`
    /// and the original Python object is retained verbatim.
    Foreign = 3,
}

const VAR_KIND_SHIFT: u32 = 30;
const MAX_INTERNED_ID: u32 = (1 << VAR_KIND_SHIFT) - 1;

/// One SAT variable, in **8 bytes**.
///
/// Pre-U1 this was a `Py<PyAny>` pointing at a `#[pyclass]` instance holding
/// three Rust `String`s: 326.7 bytes/variable measured
/// (`docs/evidence/2026-08-12-router-model-memory-probe.py`), 7.35 GB for
/// the full 22,493,900-variable model.
///
/// The kind lives in the top two bits of `kind_key` so the record stays at
/// two `u32`s with no padding; the remaining 30 bits index the interner (or
/// `foreign_vars`), which is why [`Interner::intern`] caps at
/// [`MAX_INTERNED_ID`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PackedVar {
    net_idx: u32,
    kind_key: u32,
}

impl PackedVar {
    fn new(kind: VarKind, net_idx: u32, key: u32) -> PyResult<Self> {
        if key > MAX_INTERNED_ID {
            return Err(PyRuntimeError::new_err("ConstraintModel: variable key overflow"));
        }
        Ok(Self { net_idx, kind_key: ((kind as u32) << VAR_KIND_SHIFT) | key })
    }

    fn kind(self) -> VarKind {
        match self.kind_key >> VAR_KIND_SHIFT {
            0 => VarKind::NetChannel,
            1 => VarKind::Bundle,
            2 => VarKind::Via,
            _ => VarKind::Foreign,
        }
    }

    fn key(self) -> u32 {
        self.kind_key & MAX_INTERNED_ID
    }
}

/// Marks a free slot in a [`VarIndex`]. `u32::MAX` can never be a valid
/// variable index — [`ConstraintModel::insert_variable`] refuses a model
/// that large.
const EMPTY_SLOT: u32 = u32::MAX;

/// The `(net_idx, interned key) -> variable index` reverse index behind
/// `net_channel_vars` / `bundle_channel_vars` / `via_vars`, at **4 bytes
/// per slot**.
///
/// A `HashMap<(i64, u32), u32>` costs 21 bytes per *bucket* — a 16-byte
/// padded key, a 4-byte value, a 1-byte control word — and rounds its
/// bucket count up to a power of two. At 2,044,900 entries (the production
/// per-batch model: `DEFAULT_BATCH_SIZE = 10` nets over the board's
/// 204,490-edge skeleton) that is 4,194,304 buckets and 88 MB. MEASURED:
/// with the variables already packed, the `HashMap` index was 53 of the
/// remaining 74.9 bytes per variable — more than the variables themselves.
///
/// This table stores only the 4-byte variable index and **re-derives** each
/// occupied slot's key from the variable it points at
/// ([`ConstraintModel::dict_key_of`]), so no key is stored twice. Open
/// addressing, linear probing, 0.75 load factor; entries are only ever
/// inserted or overwritten, never removed, so there are no tombstones.
#[derive(Debug, Default)]
struct VarIndex {
    /// Power-of-two sized, or empty. `EMPTY_SLOT` marks a free slot.
    slots: Vec<u32>,
    len: usize,
}

/// Hash of a `(net_idx, interned key)` dict key: a 64-bit mix followed by
/// the SplitMix64 finalizer, so the low bits — which select the slot —
/// depend on every input bit.
fn dict_hash(net_idx: i64, key: u32) -> u64 {
    let mut h = (net_idx as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    h ^= u64::from(key).wrapping_mul(0xC2B2_AE3D_27D4_EB4F);
    h ^= h >> 30;
    h = h.wrapping_mul(0xBF58_476D_1CE4_E5B9);
    h ^= h >> 27;
    h = h.wrapping_mul(0x94D0_49BB_1331_11EB);
    h ^ (h >> 31)
}

impl VarIndex {
    #[cfg(test)]
    fn len(&self) -> usize {
        self.len
    }

    /// Variable index registered for `wanted`, if any.
    ///
    /// `key_of` maps a variable index back to its dict key.
    fn get(&self, wanted: (i64, u32), key_of: &impl Fn(u32) -> Option<(i64, u32)>) -> Option<u32> {
        if self.slots.is_empty() {
            return None;
        }
        let mask = self.slots.len() - 1;
        let mut probe = (dict_hash(wanted.0, wanted.1) as usize) & mask;
        loop {
            let slot = self.slots[probe];
            if slot == EMPTY_SLOT {
                return None;
            }
            if key_of(slot) == Some(wanted) {
                return Some(slot);
            }
            probe = (probe + 1) & mask;
        }
    }

    /// Register `var_idx` under `key`, replacing whatever was registered
    /// under it before — the `HashMap::insert` last-writer-wins semantics
    /// this replaced.
    fn insert(
        &mut self,
        key: (i64, u32),
        var_idx: u32,
        key_of: &impl Fn(u32) -> Option<(i64, u32)>,
    ) {
        if (self.len + 1) * 4 > self.slots.len() * 3 {
            self.grow(key_of);
        }
        let mask = self.slots.len() - 1;
        let mut probe = (dict_hash(key.0, key.1) as usize) & mask;
        loop {
            let slot = self.slots[probe];
            if slot == EMPTY_SLOT {
                self.slots[probe] = var_idx;
                self.len += 1;
                return;
            }
            if key_of(slot) == Some(key) {
                self.slots[probe] = var_idx;
                return;
            }
            probe = (probe + 1) & mask;
        }
    }

    fn grow(&mut self, key_of: &impl Fn(u32) -> Option<(i64, u32)>) {
        let new_len = if self.slots.is_empty() { 16 } else { self.slots.len() * 2 };
        let old = std::mem::replace(&mut self.slots, vec![EMPTY_SLOT; new_len]);
        let mask = new_len - 1;
        for slot in old {
            if slot == EMPTY_SLOT {
                continue;
            }
            let Some(key) = key_of(slot) else { continue };
            let mut probe = (dict_hash(key.0, key.1) as usize) & mask;
            while self.slots[probe] != EMPTY_SLOT {
                probe = (probe + 1) & mask;
            }
            self.slots[probe] = slot;
        }
    }

    /// Every `(dict key, variable index)` pair, for rebuilding the Python
    /// dict. Slot order — arbitrary, exactly as the `HashMap` iteration
    /// order it replaced was arbitrary.
    fn iter<'a>(
        &'a self,
        key_of: &'a impl Fn(u32) -> Option<(i64, u32)>,
    ) -> impl Iterator<Item = ((i64, u32), u32)> + 'a {
        self.slots
            .iter()
            .copied()
            .filter(|slot| *slot != EMPTY_SLOT)
            .filter_map(move |slot| key_of(slot).map(|key| (key, slot)))
    }
}

/// One constraint, in Rust-native form.
///
/// The builder only ever emits the first three; `add_constraint` (the
/// Python-facing entry point, used by the PCL lowering paths) always takes
/// `Foreign` and keeps the caller's object exactly as it was handed over.
#[derive(Debug, Clone, Copy)]
enum PackedConstraint {
    /// `cap_{channel_id}`; terms are `[term_start, term_start + term_len)`
    /// of the model's flat term arena.
    Capacity { channel: u32, capacity: f64, slack_factor: f64, term_start: u32, term_len: u32 },
    /// `diff_{base_name}_{channel_id}`; `p_var`/`n_var` index `vars`.
    DiffPair { channel: u32, base: u32, p_net_idx: i64, n_net_idx: i64, p_var: u32, n_var: u32 },
    /// `layer_restr_N{net_idx}_{channel_id}`.
    Layer { channel: u32, net_idx: i64, allowed: bool },
    /// Index into `foreign_cons`.
    Foreign(u32),
}

/// `ConstraintModel`: the SAT/SMT constraint model registry.
///
/// `net_channel_vars` and `bundle_channel_vars` are kept SEPARATE (the
/// 2026-08-07 Sec 3.3 net-index/bundle-id collision fix): bundle variables
/// carry `var_type == "bundle"` and are keyed by `(bundle_id, channel_id)`,
/// never by a real net index.
///
/// **Representation (plan 2026-08-12-002 U1).** Variables and constraints
/// are stored as the packed Rust records above, never as CPython objects.
/// Every Python-facing getter keeps its exact pre-U1 signature and
/// semantics — it rebuilds the objects on demand, exactly as it already
/// rebuilt a fresh `PyList` on demand. The only observable difference is
/// object *identity*: two reads of `.variables` used to hand back the same
/// instances and now hand back equal-valued fresh ones. Nothing in the
/// tree compares model variables by identity or uses one as a dict key
/// (`types_py_bridge.rs` reads `.name`; `pipeline_route.rs`'s clause-origin
/// walk reads attributes; the differential suite canonicalises by field
/// value), and there is no `__hash__`/`__eq__` on these pyclasses for such
/// a comparison to have been meaningful through.
#[pyclass(module = "temper_design_bundle_python.model_builder", skip_from_py_object)]
#[derive(Debug, Default)]
pub struct ConstraintModel {
    /// `channel_id` / `location_id` / diff-pair `base_name` strings, once each.
    ids: Interner,
    /// One record per variable, in insertion order.
    vars: Vec<PackedVar>,
    /// Verbatim Python objects for variables that do not fit the packed
    /// shapes (see [`ConstraintModel::pack_variable`]). Empty on every
    /// production path.
    foreign_vars: Vec<Py<PyAny>>,
    /// The `(net_idx, interned key)` each `foreign_vars` entry is
    /// registered under, or `None` for one registered in no dict. Parallel
    /// to `foreign_vars`; a packed variable's key comes from the variable
    /// itself, which is why only this arm needs a side table.
    foreign_var_keys: Vec<Option<(i64, u32)>>,
    /// One record per constraint, in insertion order.
    cons: Vec<PackedConstraint>,
    /// Verbatim Python objects for constraints added via `add_constraint`.
    foreign_cons: Vec<Py<PyAny>>,
    /// Flat `(variable index, width)` arena for `Capacity` terms, held as
    /// two parallel vectors so a term costs 12 bytes rather than the 16 a
    /// `Vec<(u32, f64)>` would pad to.
    term_vars: Vec<u32>,
    term_widths: Vec<f64>,
    net_channel_vars: VarIndex,
    bundle_channel_vars: VarIndex,
    via_vars: VarIndex,
}

impl ConstraintModel {
    /// The `(net_idx, interned key)` variable `idx` is registered under, or
    /// `None` if it is registered in no dict. This is what lets [`VarIndex`]
    /// store a bare variable index per slot instead of the key as well.
    fn dict_key_of(
        vars: &[PackedVar],
        foreign_var_keys: &[Option<(i64, u32)>],
        idx: u32,
    ) -> Option<(i64, u32)> {
        let packed = *vars.get(idx as usize)?;
        match packed.kind() {
            VarKind::Foreign => *foreign_var_keys.get(packed.key() as usize)?,
            _ => Some((i64::from(packed.net_idx), packed.key())),
        }
    }

    /// `dict_key_of` bound to a pair of tables. Takes the two slices rather
    /// than `&self` so a caller can hold it across a `&mut` borrow of one of
    /// the three [`VarIndex`] fields.
    fn key_resolver_for<'a>(
        vars: &'a [PackedVar],
        foreign_var_keys: &'a [Option<(i64, u32)>],
    ) -> impl Fn(u32) -> Option<(i64, u32)> + 'a {
        move |idx| Self::dict_key_of(vars, foreign_var_keys, idx)
    }

    /// `dict_key_of` bound to this model's own tables.
    fn key_resolver(&self) -> impl Fn(u32) -> Option<(i64, u32)> + '_ {
        Self::key_resolver_for(&self.vars, &self.foreign_var_keys)
    }

    /// `(variable index, width)` for term slot `i` of the arena.
    fn term(&self, i: u32) -> PyResult<(u32, f64)> {
        let i = i as usize;
        match (self.term_vars.get(i), self.term_widths.get(i)) {
            (Some(v), Some(w)) => Ok((*v, *w)),
            _ => Err(PyRuntimeError::new_err("ConstraintModel: term index out of range")),
        }
    }

    /// Rebuild variable `idx` as the Python object the pre-U1 model stored.
    fn variable_object(&self, py: Python<'_>, idx: u32) -> PyResult<Py<PyAny>> {
        let packed = *self
            .vars
            .get(idx as usize)
            .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: variable index out of range"))?;
        match packed.kind() {
            VarKind::Foreign => self
                .foreign_vars
                .get(packed.key() as usize)
                .map(|v| v.clone_ref(py))
                .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: foreign var missing")),
            VarKind::NetChannel | VarKind::Bundle => {
                let bundle = packed.kind() == VarKind::Bundle;
                let channel_id = self.ids.get(packed.key())?;
                let prefix = if bundle { 'B' } else { 'N' };
                let var = NetChannelVar {
                    name: format!("uses_{prefix}{}_{channel_id}", packed.net_idx),
                    var_type: if bundle { "bundle" } else { "bool" }.to_string(),
                    net_idx: i64::from(packed.net_idx),
                    channel_id: channel_id.to_string(),
                };
                Ok(Py::new(py, var)?.into_any())
            }
            VarKind::Via => {
                let location_id = self.ids.get(packed.key())?;
                let var = ViaVar {
                    name: format!("via_N{}_{location_id}", packed.net_idx),
                    var_type: "bool".to_string(),
                    net_idx: i64::from(packed.net_idx),
                    location_id: location_id.to_string(),
                };
                Ok(Py::new(py, var)?.into_any())
            }
        }
    }

    /// Rebuild constraint `i` as the Python object the pre-U1 model stored.
    ///
    /// `model` is this model's own handle, threaded in so the rebuilt
    /// `CapacityConstraint`/`DiffPairConstraint` can resolve their variable
    /// references lazily instead of materialising them here.
    fn constraint_object(
        &self,
        py: Python<'_>,
        model: &Py<ConstraintModel>,
        i: usize,
    ) -> PyResult<Py<PyAny>> {
        let packed = *self
            .cons
            .get(i)
            .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: constraint index out of range"))?;
        match packed {
            PackedConstraint::Foreign(key) => self
                .foreign_cons
                .get(key as usize)
                .map(|c| c.clone_ref(py))
                .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: foreign constraint missing")),
            PackedConstraint::Capacity { channel, capacity, slack_factor, term_start, term_len } => {
                let channel_id = self.ids.get(channel)?;
                let c = CapacityConstraint {
                    name: format!("cap_{channel_id}"),
                    description: String::new(),
                    channel_id: channel_id.to_string(),
                    capacity,
                    slack_factor,
                    terms: CapacityTerms::Packed {
                        model: model.clone_ref(py),
                        start: term_start,
                        len: term_len,
                    },
                };
                Ok(Py::new(py, c)?.into_any())
            }
            PackedConstraint::DiffPair { channel, base, p_net_idx, n_net_idx, p_var, n_var } => {
                let channel_id = self.ids.get(channel)?;
                let base_name = self.ids.get(base)?;
                let c = DiffPairConstraint {
                    name: format!("diff_{base_name}_{channel_id}"),
                    description: String::new(),
                    channel_id: channel_id.to_string(),
                    p_net_idx,
                    n_net_idx,
                    p_var: VarSlot::Packed { model: model.clone_ref(py), idx: p_var },
                    n_var: VarSlot::Packed { model: model.clone_ref(py), idx: n_var },
                };
                Ok(Py::new(py, c)?.into_any())
            }
            PackedConstraint::Layer { channel, net_idx, allowed } => {
                let channel_id = self.ids.get(channel)?;
                let c = LayerConstraint {
                    name: format!("layer_restr_N{net_idx}_{channel_id}"),
                    description: String::new(),
                    net_idx,
                    channel_id: channel_id.to_string(),
                    allowed,
                };
                Ok(Py::new(py, c)?.into_any())
            }
        }
    }

    /// Try to express `(name, var_type, net_idx, key)` as a [`PackedVar`].
    ///
    /// Returns `None` when the object cannot be reconstructed byte-for-byte
    /// from the packed fields — a `net_idx` outside `u32`, an unexpected
    /// `var_type`, or a `name` that is not the canonical rendering. The
    /// caller then retains the original Python object as `Foreign`, so a
    /// hand-built variable such as `NetChannelVar(name="BOGUS", net_idx=0,
    /// channel_id="EDGE")` keeps its name exactly.
    fn pack_variable(
        kind: VarKind,
        name: &str,
        var_type: &str,
        net_idx: i64,
        key_value: &str,
        key: u32,
    ) -> PyResult<Option<PackedVar>> {
        let expected_type = if kind == VarKind::Bundle { "bundle" } else { "bool" };
        if var_type != expected_type {
            return Ok(None);
        }
        let Ok(net_idx_u32) = u32::try_from(net_idx) else {
            return Ok(None);
        };
        let expected_name = match kind {
            VarKind::NetChannel => format!("uses_N{net_idx_u32}_{key_value}"),
            VarKind::Bundle => format!("uses_B{net_idx_u32}_{key_value}"),
            VarKind::Via => format!("via_N{net_idx_u32}_{key_value}"),
            VarKind::Foreign => return Ok(None),
        };
        if name != expected_name {
            return Ok(None);
        }
        PackedVar::new(kind, net_idx_u32, key).map(Some)
    }

    /// Append a variable and route it into the type-appropriate dict.
    ///
    /// `original` is only consulted when the variable cannot be packed.
    /// `kind` must be one of the three packed kinds; use
    /// [`ConstraintModel::insert_foreign_variable`] for anything else.
    fn insert_variable(
        &mut self,
        kind: VarKind,
        name: &str,
        var_type: &str,
        net_idx: i64,
        key_value: &str,
        original: impl FnOnce() -> PyResult<Py<PyAny>>,
    ) -> PyResult<()> {
        let key = self.ids.intern(key_value)?;
        let dict_key = match kind {
            VarKind::Foreign => None,
            _ => Some((net_idx, key)),
        };
        let packed = match Self::pack_variable(kind, name, var_type, net_idx, key_value, key)? {
            Some(packed) => packed,
            None => self.take_foreign_var(original()?, dict_key)?,
        };
        let idx = self.push_var(packed)?;
        let Some(dict_key) = dict_key else { return Ok(()) };
        let resolver = Self::key_resolver_for(&self.vars, &self.foreign_var_keys);
        match kind {
            VarKind::NetChannel => self.net_channel_vars.insert(dict_key, idx, &resolver),
            VarKind::Bundle => self.bundle_channel_vars.insert(dict_key, idx, &resolver),
            VarKind::Via => self.via_vars.insert(dict_key, idx, &resolver),
            VarKind::Foreign => {}
        }
        Ok(())
    }

    /// Append a variable of a shape the model does not index — retained
    /// verbatim, in insertion order, and routed into no dict (exactly what
    /// the pre-U1 `add_variable` did for anything that was neither a
    /// `NetChannelVar` nor a `ViaVar`).
    fn insert_foreign_variable(&mut self, var: Py<PyAny>) -> PyResult<()> {
        let packed = self.take_foreign_var(var, None)?;
        let _ = self.push_var(packed)?;
        Ok(())
    }

    fn push_var(&mut self, packed: PackedVar) -> PyResult<u32> {
        let idx = u32::try_from(self.vars.len())
            .ok()
            .filter(|idx| *idx != EMPTY_SLOT)
            .ok_or_else(|| PyRuntimeError::new_err("ConstraintModel: too many variables"))?;
        self.vars.push(packed);
        Ok(idx)
    }

    fn take_foreign_var(
        &mut self,
        var: Py<PyAny>,
        dict_key: Option<(i64, u32)>,
    ) -> PyResult<PackedVar> {
        let key = u32::try_from(self.foreign_vars.len()).map_err(|_| {
            PyRuntimeError::new_err("ConstraintModel: too many unpacked variables")
        })?;
        self.foreign_vars.push(var);
        self.foreign_var_keys.push(dict_key);
        PackedVar::new(VarKind::Foreign, 0, key)
    }

    /// Index of the variable registered for `(net_idx, key_value)`, if any.
    fn lookup_var(&self, dict: &VarIndex, net_idx: i64, key_value: &str) -> Option<u32> {
        let key = self.ids.lookup(key_value)?;
        dict.get((net_idx, key), &self.key_resolver())
    }

    fn rebuild_dict(&self, py: Python<'_>, dict: &VarIndex) -> PyResult<Py<PyDict>> {
        let d = PyDict::new(py);
        let resolver = self.key_resolver();
        for ((net_idx, key), var_idx) in dict.iter(&resolver) {
            let net_obj = net_idx.into_pyobject(py)?.into_any();
            let key_obj = self.ids.get(key)?.into_pyobject(py)?.into_any();
            let tuple_key = PyTuple::new(py, [net_obj, key_obj])?;
            d.set_item(tuple_key, self.variable_object(py, var_idx)?)?;
        }
        Ok(d.unbind())
    }
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
                let kind =
                    if v.var_type == "bundle" { VarKind::Bundle } else { VarKind::NetChannel };
                let (name, var_type, net_idx, channel_id) =
                    (v.name.clone(), v.var_type.clone(), v.net_idx, v.channel_id.clone());
                drop(v);
                self.insert_variable(kind, &name, &var_type, net_idx, &channel_id, || {
                    Ok(var.clone().unbind())
                })
            } else if var.is_instance_of::<ViaVar>() {
                let v = var.extract::<PyRef<'_, ViaVar>>()?;
                let (name, var_type, net_idx, location_id) =
                    (v.name.clone(), v.var_type.clone(), v.net_idx, v.location_id.clone());
                drop(v);
                self.insert_variable(VarKind::Via, &name, &var_type, net_idx, &location_id, || {
                    Ok(var.clone().unbind())
                })
            } else {
                // Not one of the two shapes the model routes into a dict:
                // keep the object verbatim, in insertion order.
                self.insert_foreign_variable(var.unbind())
            }
        })
    }

    /// `add_constraint`: append a constraint.
    ///
    /// Always retained verbatim. The Python-facing entry point exists for
    /// the two PCL lowering paths, which add a handful of constraints
    /// carrying objects the model knows nothing about (a
    /// `DiffPairConstraint` whose `p_var` is a bare `str`, for one); the
    /// builder's own 200k-odd constraints never come through here.
    fn add_constraint(&mut self, constraint: Bound<'_, PyAny>) -> PyResult<()> {
        guard(|| {
            let key = u32::try_from(self.foreign_cons.len())
                .map_err(|_| PyRuntimeError::new_err("ConstraintModel: too many constraints"))?;
            self.foreign_cons.push(constraint.unbind());
            self.cons.push(PackedConstraint::Foreign(key));
            Ok(())
        })
    }

    /// `variable_count`.
    #[getter]
    fn variable_count(&self) -> usize {
        self.vars.len()
    }

    /// `constraint_count`.
    #[getter]
    fn constraint_count(&self) -> usize {
        self.cons.len()
    }

    /// `variables` — a fresh Python list per access (like the pre-migration
    /// `list[Variable]` field).
    #[getter]
    fn variables(&self, py: Python<'_>) -> PyResult<Py<PyList>> {
        guard(|| {
            let list = PyList::empty(py);
            for idx in 0..self.vars.len() {
                let idx = u32::try_from(idx)
                    .map_err(|_| PyRuntimeError::new_err("ConstraintModel: too many variables"))?;
                list.append(self.variable_object(py, idx)?)?;
            }
            Ok(list.unbind())
        })
    }

    /// `constraints` — a fresh Python list per access.
    #[getter]
    fn constraints(slf: &Bound<'_, Self>) -> PyResult<Py<PyList>> {
        guard(|| {
            let py = slf.py();
            let model = slf.clone().unbind();
            let m = slf.borrow();
            let list = PyList::empty(py);
            for i in 0..m.cons.len() {
                list.append(m.constraint_object(py, &model, i)?)?;
            }
            Ok(list.unbind())
        })
    }

    #[getter(net_channel_vars)]
    fn net_channel_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| self.rebuild_dict(py, &self.net_channel_vars))
    }

    #[getter(bundle_channel_vars)]
    fn bundle_channel_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| self.rebuild_dict(py, &self.bundle_channel_vars))
    }

    #[getter(via_vars)]
    fn via_vars_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        guard(|| self.rebuild_dict(py, &self.via_vars))
    }
}

// ---------------------------------------------------------------------------
// ModelBuilder — the build() orchestration
// ---------------------------------------------------------------------------

/// `ModelBuilder`: mirror of `router_v6.constraint_model.ModelBuilder`.
///
/// Holds the Python input objects opaquely (`Py<PyDict>`/`Py<PyList>`/
/// `Py<PyAny>`) so iteration order and attribute reads are the live Python
/// ones — the same objects the pre-migration builder read.
///
/// `net_filter`: optional set of net *names*. When present, only the named
/// nets get `NetChannelVar`/`ViaVar` variables, capacity-constraint terms,
/// and layer constraints — every per-net loop skips the rest. Net indices
/// are NOT renumbered: a filtered model keeps the original `pcb.nets`
/// indices, so variable names (`uses_N{idx}_...`) and the downstream
/// index-based consumers (`extract_topology`'s `net_names.get(ni)`,
/// `var_to_net`) stay consistent. This is the "selective SAT" the
/// `max_sat_nets` pipeline option promises
/// (`router_v6._pipeline_route._select_sat_nets`): the option used to be
/// print-only, and the Stage 3 CNF encoded every net regardless (the
/// `|nets| × |edges|` Sinz term — measured 182-200 GB monolith demand,
/// see docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md).
/// Nets not in the filter get no SAT topology and fall through to Stage
/// 4's existing `fallback_channel_path` A* path, exactly like nets the
/// solver leaves unassigned.
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
    net_filter: Option<HashSet<String>>,
    model: Py<ConstraintModel>,
}

impl ModelBuilder {
    /// Is `net_name` inside the selective-SAT filter (or is there no
    /// filter)? Everything the builder creates per net consults this.
    fn net_is_selected(&self, net_name: &str) -> bool {
        self.net_filter.as_ref().is_none_or(|f| f.contains(net_name))
    }
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

    /// Index of the `(net_idx, edge_id)` per-net channel variable, if the
    /// model carries one. Pre-U1 this handed back the variable's Python
    /// object; every caller only ever needed its identity within the model,
    /// which an index carries exactly.
    fn model_net_var(&self, py: Python<'_>, net_idx: i64, edge_id: &str) -> PyResult<Option<u32>> {
        let m = self.model.bind(py).borrow();
        Ok(m.lookup_var(&m.net_channel_vars, net_idx, edge_id))
    }

    fn model_bundle_var(&self, py: Python<'_>, bundle_id: i64, edge_id: &str) -> PyResult<Option<u32>> {
        let m = self.model.bind(py).borrow();
        Ok(m.lookup_var(&m.bundle_channel_vars, bundle_id, edge_id))
    }

    fn push_channel_var(&mut self, py: Python<'_>, var: NetChannelVar) -> PyResult<()> {
        let kind = if var.var_type == "bundle" { VarKind::Bundle } else { VarKind::NetChannel };
        let mut m = self.model.bind(py).borrow_mut();
        m.insert_variable(kind, &var.name, &var.var_type, var.net_idx, &var.channel_id, || {
            Ok(Py::new(py, var.clone())?.into_any())
        })
    }

    fn push_via_var(&mut self, py: Python<'_>, var: ViaVar) -> PyResult<()> {
        let mut m = self.model.bind(py).borrow_mut();
        m.insert_variable(
            VarKind::Via,
            &var.name,
            &var.var_type,
            var.net_idx,
            &var.location_id,
            || Ok(Py::new(py, var.clone())?.into_any()),
        )
    }

    fn push_constraint(&mut self, py: Python<'_>, constraint: PackedConstraint) -> PyResult<()> {
        let mut m = self.model.bind(py).borrow_mut();
        m.cons.push(constraint);
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

        for (net_idx, net) in nets.iter().enumerate() {
            let net_name: String = net.getattr("name")?.extract()?;
            if !self.net_is_selected(&net_name) {
                continue;
            }
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
        for (net_idx, net) in nets.iter().enumerate() {
            if bundled_net_indices.contains(&(net_idx as i64)) {
                continue;
            }
            let net_name: String = net.getattr("name")?.extract()?;
            if !self.net_is_selected(&net_name) {
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

        for (net_idx, net) in nets.iter().enumerate() {
            let net_name: String = net.getattr("name")?.extract()?;
            if !self.net_is_selected(&net_name) {
                continue;
            }
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

        // Per-net selective-SAT membership, computed ONCE (110 attribute
        // reads) instead of once per (edge, net) -- the capacity loop below
        // is the |edges| x |nets| hot path.
        let nets = self.nets.bind(py).clone();
        let mut net_selected: Vec<bool> = Vec::with_capacity(nets.len());
        for net in nets.iter() {
            let net_name: String = net.getattr("name")?.extract()?;
            net_selected.push(self.net_is_selected(&net_name));
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

                let mut terms: Vec<(u32, f64)> = Vec::new();
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

                for (net_idx, selected) in net_selected.iter().enumerate() {
                    if bundle_id_for_net.iter().any(|(n, _)| *n == net_idx as i64) {
                        continue;
                    }
                    if !selected {
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
                    let mut m = self.model.bind(py).borrow_mut();
                    let channel = m.ids.intern(&edge_id)?;
                    let term_start = u32::try_from(m.term_vars.len()).map_err(|_| {
                        PyRuntimeError::new_err("ConstraintModel: capacity term arena overflow")
                    })?;
                    let term_len = u32::try_from(terms.len()).map_err(|_| {
                        PyRuntimeError::new_err("ConstraintModel: capacity term count overflow")
                    })?;
                    for (var_idx, width) in terms {
                        m.term_vars.push(var_idx);
                        m.term_widths.push(width);
                    }
                    m.cons.push(PackedConstraint::Capacity {
                        channel,
                        capacity,
                        slack_factor,
                        term_start,
                        term_len,
                    });
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
                        let (channel, base) = {
                            let mut m = self.model.bind(py).borrow_mut();
                            (m.ids.intern(&edge_id)?, m.ids.intern(&base_name)?)
                        };
                        self.push_constraint(
                            py,
                            PackedConstraint::DiffPair {
                                channel,
                                base,
                                p_net_idx: p_idx,
                                n_net_idx: n_idx,
                                p_var,
                                n_var,
                            },
                        )?;
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
                if !self.net_is_selected(pin_net.as_deref().unwrap_or("")) {
                    continue;
                }
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
                            let channel = self.model.bind(py).borrow_mut().ids.intern(&edge_id)?;
                            self.push_constraint(
                                py,
                                PackedConstraint::Layer { channel, net_idx, allowed: false },
                            )?;
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
        enable_via_vars = false,
        net_filter = None
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
        net_filter: Option<Bound<'_, PyAny>>,
    ) -> PyResult<Self> {
        guard(|| {
            let skeletons = as_dict_or_empty(py, skeletons)?;
            let nets = as_list_or_empty(py, nets)?;
            let channel_widths = as_dict_or_empty(py, channel_widths)?;
            let diff_pairs = as_list_or_empty(py, diff_pairs)?;
            let model = Py::new(py, ConstraintModel::default())?;
            // `net_filter`: a list of net names, or None. Deduplicated into a
            // set for O(1) membership; an empty list is honored as "select
            // nothing" (the pipeline never sends one -- `_select_sat_nets`
            // returns None for max_sat_nets >= net count, and
            // `max_sat_nets=0` short-circuits to None at the call site).
            let net_filter = match net_filter {
                Some(f) if !f.is_none() => {
                    let names: Vec<String> = f.try_iter()?.map(|n| n?.extract()).collect::<PyResult<_>>()?;
                    Some(names.into_iter().collect::<HashSet<_>>())
                }
                _ => None,
            };
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
                net_filter,
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
                terms: CapacityTerms::Owned(vec![(Py::new(py, v).unwrap().into_any(), 0.2)]),
            };
            assert_eq!(c.terms(py).unwrap().bind(py).len(), 1);
            assert_eq!(c.capacity, 10.0);
        })
    }

    fn net_channel(name: &str, var_type: &str, net_idx: i64, channel_id: &str) -> NetChannelVar {
        NetChannelVar {
            name: name.into(),
            var_type: var_type.into(),
            net_idx,
            channel_id: channel_id.into(),
        }
    }

    #[test]
    fn model_routes_bundle_and_net_vars() {
        Python::attach(|py| {
            let mut m = ConstraintModel::default();
            let net_var = net_channel("uses_N0_E", "bool", 0, "E");
            let bundle_var = net_channel("uses_B0_E", "bundle", 0, "E");
            m.insert_variable(VarKind::NetChannel, "uses_N0_E", "bool", 0, "E", || {
                Ok(Py::new(py, net_var).unwrap().into_any())
            })
            .unwrap();
            m.insert_variable(VarKind::Bundle, "uses_B0_E", "bundle", 0, "E", || {
                Ok(Py::new(py, bundle_var).unwrap().into_any())
            })
            .unwrap();
            assert_eq!(m.net_channel_vars.len(), 1);
            assert_eq!(m.bundle_channel_vars.len(), 1);
            assert_eq!(m.via_vars.len(), 0);
            // Both packed: the channel id is interned once, and no CPython
            // object was created for either variable.
            assert_eq!(m.ids.values.len(), 1);
            assert!(m.foreign_vars.is_empty());
            assert_eq!(m.vars[0].kind(), VarKind::NetChannel);
            assert_eq!(m.vars[1].kind(), VarKind::Bundle);
        })
    }

    #[test]
    fn packed_variables_rebuild_their_python_objects_exactly() {
        Python::attach(|py| {
            let mut m = ConstraintModel::default();
            m.insert_variable(VarKind::NetChannel, "uses_N7_EDGE", "bool", 7, "EDGE", || {
                unreachable!("packable variable must not fall back")
            })
            .unwrap();
            m.insert_variable(VarKind::Via, "via_N7_LOC", "bool", 7, "LOC", || {
                unreachable!("packable variable must not fall back")
            })
            .unwrap();
            let v0 = m.variable_object(py, 0).unwrap();
            let v0 = v0.bind(py).extract::<PyRef<'_, NetChannelVar>>().unwrap();
            assert_eq!(v0.name, "uses_N7_EDGE");
            assert_eq!(v0.var_type, "bool");
            assert_eq!(v0.net_idx, 7);
            assert_eq!(v0.channel_id, "EDGE");
            let v1 = m.variable_object(py, 1).unwrap();
            let v1 = v1.bind(py).extract::<PyRef<'_, ViaVar>>().unwrap();
            assert_eq!(v1.name, "via_N7_LOC");
            assert_eq!(v1.location_id, "LOC");
        })
    }

    #[test]
    fn non_canonical_name_falls_back_to_the_original_object() {
        Python::attach(|py| {
            let mut m = ConstraintModel::default();
            let bogus = net_channel("BOGUS", "bool", 0, "EDGE");
            m.insert_variable(VarKind::NetChannel, "BOGUS", "bool", 0, "EDGE", || {
                Ok(Py::new(py, bogus).unwrap().into_any())
            })
            .unwrap();
            assert_eq!(m.vars[0].kind(), VarKind::Foreign);
            assert_eq!(m.foreign_vars.len(), 1);
            let v = m.variable_object(py, 0).unwrap();
            let v = v.bind(py).extract::<PyRef<'_, NetChannelVar>>().unwrap();
            assert_eq!(v.name, "BOGUS");
            // Still routed into the dict, exactly as pre-U1.
            assert_eq!(m.lookup_var(&m.net_channel_vars, 0, "EDGE"), Some(0));
        })
    }

    #[test]
    fn last_writer_wins_on_a_duplicate_dict_key() {
        Python::attach(|py| {
            let mut m = ConstraintModel::default();
            m.insert_variable(VarKind::NetChannel, "uses_N0_EDGE", "bool", 0, "EDGE", || {
                unreachable!()
            })
            .unwrap();
            let bogus = net_channel("BOGUS", "bool", 0, "EDGE");
            m.insert_variable(VarKind::NetChannel, "BOGUS", "bool", 0, "EDGE", || {
                Ok(Py::new(py, bogus).unwrap().into_any())
            })
            .unwrap();
            assert_eq!(m.vars.len(), 2);
            assert_eq!(m.net_channel_vars.len(), 1);
            // The dict points at the SECOND variable, and the packed first
            // one is still there in insertion order.
            assert_eq!(m.lookup_var(&m.net_channel_vars, 0, "EDGE"), Some(1));
            let v = m.variable_object(py, 1).unwrap();
            assert_eq!(
                v.bind(py).extract::<PyRef<'_, NetChannelVar>>().unwrap().name,
                "BOGUS"
            );
        })
    }

    /// The reverse index must agree with a `HashMap` on the same operation
    /// sequence — the structure it replaced, at the same semantics
    /// (insert-or-overwrite, no removal).
    #[test]
    fn var_index_agrees_with_a_hashmap_over_a_mixed_workload() {
        let mut vars: Vec<PackedVar> = Vec::new();
        let mut index = VarIndex::default();
        let mut reference: HashMap<(i64, u32), u32> = HashMap::new();

        // Deterministic pseudo-random keys, including deliberate duplicates
        // (`% 37` and `% 53` cycle far faster than the 4,000 insertions) so
        // the overwrite path is exercised heavily.
        for i in 0..4_000u32 {
            let net_idx = i64::from(i.wrapping_mul(2_654_435_761) % 37);
            let key = i.wrapping_mul(40_503) % 53;
            let idx = u32::try_from(vars.len()).unwrap();
            vars.push(PackedVar::new(VarKind::NetChannel, net_idx as u32, key).unwrap());
            let resolver = ConstraintModel::key_resolver_for(&vars, &[]);
            index.insert((net_idx, key), idx, &resolver);
            let _ = reference.insert((net_idx, key), idx);
        }

        let resolver = ConstraintModel::key_resolver_for(&vars, &[]);
        assert_eq!(index.len(), reference.len());
        for (key, want) in &reference {
            assert_eq!(index.get(*key, &resolver), Some(*want), "key {key:?}");
        }
        // Absent keys miss rather than probing forever.
        for key in [(999_i64, 0_u32), (0, 999), (-1, 0)] {
            assert!(!reference.contains_key(&key));
            assert_eq!(index.get(key, &resolver), None);
        }
        // `iter` yields exactly the reference's contents.
        let mut got: Vec<_> = index.iter(&resolver).collect();
        let mut expected: Vec<_> = reference.into_iter().collect();
        got.sort_unstable();
        expected.sort_unstable();
        assert_eq!(got, expected);
    }

    #[test]
    fn var_index_resolves_foreign_variables_through_the_side_table() {
        let vars = vec![PackedVar::new(VarKind::Foreign, 0, 0).unwrap()];
        let foreign_keys = vec![Some((-9_i64, 3_u32))];
        let resolver = ConstraintModel::key_resolver_for(&vars, &foreign_keys);
        let mut index = VarIndex::default();
        index.insert((-9, 3), 0, &resolver);
        assert_eq!(index.get((-9, 3), &resolver), Some(0));
        assert_eq!(index.get((-9, 4), &resolver), None);
    }

    #[test]
    fn packed_var_round_trips_kind_and_key() {
        for (kind, key) in [
            (VarKind::NetChannel, 0u32),
            (VarKind::Bundle, 1),
            (VarKind::Via, MAX_INTERNED_ID),
            (VarKind::Foreign, 12345),
        ] {
            let pv = PackedVar::new(kind, 4242, key).unwrap();
            assert_eq!(pv.kind(), kind);
            assert_eq!(pv.key(), key);
            assert_eq!(pv.net_idx, 4242);
        }
        assert!(PackedVar::new(VarKind::NetChannel, 0, MAX_INTERNED_ID + 1).is_err());
    }

    #[test]
    fn packed_var_is_eight_bytes() {
        assert_eq!(std::mem::size_of::<PackedVar>(), 8);
    }

    #[test]
    fn interner_shares_one_allocation_per_distinct_string() {
        let mut ids = Interner::default();
        let a = ids.intern("F.Cu_E1").unwrap();
        let b = ids.intern("F.Cu_E1").unwrap();
        let c = ids.intern("F.Cu_E2").unwrap();
        assert_eq!(a, b);
        assert_ne!(a, c);
        assert_eq!(ids.values.len(), 2);
        assert_eq!(ids.get(a).unwrap(), "F.Cu_E1");
        assert_eq!(ids.lookup("F.Cu_E2"), Some(c));
        assert_eq!(ids.lookup("nope"), None);
    }
}

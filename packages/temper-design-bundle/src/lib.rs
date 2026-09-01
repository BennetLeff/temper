// Production extension builds enable this pyo3 surface explicitly.
#[cfg(feature = "python")]
mod net_types;

// Typed physical-pad identity: `(pad_number, occurrence)`, see its module
// doc for the duplicate-pad-number footgun this removes. Pure Rust, no
// pyo3 dependency, so it is unconditional like `rotation_quadrant` is in
// `temper-geometry` -- see that module's own precedent for this pattern.
pub mod pad_occurrence;

// Wave 4 Phase 3 (formats/IO): the two numeric kernels ported out of
// temper_placer/io/_write_board.py (_reorient_pads's per-pad angle update,
// state_to_placements's original-angle offset preservation) — see
// write_board_geometry.rs's module docstring for the full triage of what
// was and was not ported.
#[cfg(feature = "python")]
mod write_board_geometry;

// Wave 4: the router_v6/constraint_model.py compute kernels (edge-identity,
// point-to-segment / pin-span / pruning-predicate geometry) — see
// constraint_model.rs's module docstring for the full triage.
#[cfg(feature = "python")]
mod constraint_model;

// Orchestration plan Phase E batch E1: the ModelBuilder build() orchestration
// and the constraint-model contract pyclasses (router_v6/constraint_model.py)
// — see model_builder.rs's module docstring for the Python-side split.
#[cfg(feature = "python")]
mod model_builder;

// Orchestration plan Phase E batch E2: the fixed-copper build orchestration
// and the contract pyclasses (placer/cp_sat/fixed_copper.py) — see
// fixed_copper_builder.rs's module docstring for the Python-side split.
#[cfg(feature = "python")]
mod fixed_copper_builder;

// Wave 4 follow-up: the HV/LV guard-strip partitioning decision kernels
// (safety-category classification + creepage max / width resolution /
// bucket-area decision) — see hv_lv_partition.rs.
#[cfg(feature = "python")]
mod hv_lv_partition;

#[cfg(feature = "python")]
mod deterministic_stages;

// Wave 4 Phase 5 batch 2 — deterministic leaf stages (remaining slice):
// component-assignment / layer-assignment / power-plane / fine-pitch /
// slot-grid kernels + leaf data contracts (see deterministic_leaves.rs).
#[cfg(feature = "python")]
mod deterministic_leaves;

// Wave 4 Phase 5 final leaves — the remaining unowned deterministic
// helper/stage compute (phase mixin kernels + zone-aware slot geometry; see
// deterministic_phase.rs).
#[cfg(feature = "python")]
mod deterministic_phase;

// Wave 4 Phase 5 batch 2 — host-libm helpers (pow/sqrt/hypot via dlsym)
// for the deterministic leaf kernels (see host_math.rs).
#[cfg(feature = "python")]
mod host_math;

#[cfg(feature = "python")]
mod loops;

#[cfg(feature = "python")]
mod design_rules;

#[cfg(feature = "python")]
mod gates;

#[cfg(feature = "python")]
mod priority;

#[cfg(feature = "python")]
mod netlist_contracts;

// Wave C core-contracts migration: net_graph + differential_pair pyclasses
// (see docs/plans/2026-08-08-001-feat-wavec-core-contracts-migration-plan.md).
#[cfg(feature = "python")]
mod bus_cohort_contracts;
#[cfg(feature = "python")]
mod decision_contracts;
#[cfg(feature = "python")]
mod differential_pair_contracts;
#[cfg(feature = "python")]
mod net_graph_contracts;

// Orchestration plan Phase A unit U7: the typed terminal-extraction wire
// format (router_v6/terminal_extraction.py -> PinWire/ComponentWire/
// StackupLayerWire) and the typed COO-triplet I/O boundary of the
// hypergraph_coo_matvec kernel (core/hypergraph.py -> hypergraph_contracts::Coo)
// -- see docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md.
#[cfg(feature = "python")]
mod hypergraph_contracts;
#[cfg(feature = "python")]
mod terminal_wire_contracts;

// Orchestration plan Phase A unit U9: the typed loop-extraction marshalling
// boundary (core/loop_extractor_rs.py -> LoopExtractionInput /
// LoopExtractionOutput -- the wire format of the
// temper_rust_router.auto_extract_loops_rust bridge).
#[cfg(feature = "python")]
mod loop_extraction_contracts;

// Wave C core-contracts migration: geometry_types pyclasses
// (Point, Track, Via, Pad) — see geometry_types_contracts.rs.
#[cfg(feature = "python")]
mod geometry_types_contracts;

// Wave 4 fanout: path_graph + NetTopology + TopologyGraph pyclasses
// (replaces networkx.DiGraph surface in router_v6) — see
// topology_extraction_contracts.rs.
#[cfg(feature = "python")]
mod topology_extraction_contracts;

// Wave 4 fanout: SkeletonGraph pyclass (replaces networkx.Graph surface
// in router_v6/channel_skeleton.py) — see channel_skeleton_contracts.rs.
#[cfg(feature = "python")]
mod channel_skeleton_contracts;

// Wave 4 fanout: TopologicalGraphStore pyclass (replaces networkx.MultiDiGraph
// surface in topological/graph.py) — see topological_graph_contracts.rs.
#[cfg(feature = "python")]
mod topological_graph_contracts;

// Wave 4 fan-out migration: loop_ownership data contracts
// (see fanout/migrate-core-3 branch).
#[cfg(feature = "python")]
mod loop_ownership_contracts;

// Wave 4 fan-out: specification dataclasses (ThermalSpec, EMISpec,
// SignalIntegritySpec, SafetySpec, PcbSpecification) — see
// specification_contracts.rs.
#[cfg(feature = "python")]
mod specification_contracts;

#[cfg(feature = "python")]
mod board_contracts;

#[cfg(feature = "python")]
mod config_loader;

#[cfg(feature = "python")]
mod reference_loader;

#[cfg(feature = "python")]
mod loaders;
pub(crate) mod parse_engine;
pub mod regional_topology;
pub mod safety_value_authority;
#[cfg(feature = "python")]
mod sexpr_writer;

#[cfg(feature = "python")]
mod pcl_parse;

#[cfg(feature = "python")]
mod pcl_tags;

// Wave 4 Phase 5 (deterministic hubs slice): the deterministic hub kernels
// (channels penalty, bottleneck score, seed filter, feedback mapper/adjuster/
// parser). Registered as the `deterministic_hubs` submodule (see lib.rs's
// `python` module). Kept separate from the leaf-stages slice's
// `deterministic_stages` submodule (owned by the parallel branch
// feat/wave4-phase5-deterministic-stages-rust) so the two branches' lib.rs
// additions merge cleanly.
#[cfg(feature = "python")]
mod deterministic_hubs;

// Wave 4 Phase 4 — regression slice: the measure-closure /
// cp_sat_comparison / fingerprint / schema_validator kernels (see the
// module docstrings and packages/temper-design-bundle/VERIFICATION.md).
#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod cp_sat_comparison;
#[cfg(feature = "python")]
mod fingerprint;
#[cfg(feature = "python")]
mod measure_closure;
#[cfg(feature = "python")]
mod schema_validator;

mod atopile;
pub(crate) mod constraint_merge;
mod error;
pub(crate) mod identity;
pub(crate) mod kicad_pcb;
mod model;
#[cfg(feature = "python")]
mod validation;
// Not gated on `python`: pure resolve()/format_unresolved() logic, unit
// tested directly (see the module docstring). netlist_contracts.rs's
// python-gated `apply_net_class_mapping_strict` is the only pyo3-facing
// consumer.
pub(crate) mod net_class_validation;
pub(crate) mod netlist;
pub(crate) mod pcl;
// Safety-critical values with provenance: the recovered IEC 60335-1
// Table 16/17/18 const tables plus the Derived/Fabricated/Unobtainable
// provenance vocabulary (see safety_value.rs's module docstring). NOT gated
// on `python` — the wasm32 tier and the coverage gate both build the
// `--no-default-features` configuration, and the tables are pure const data
// with no pyo3 dependency. The pyo3 surface inside the module is itself
// `#[cfg(feature = "python")]`-gated.
pub mod safety_value;
mod serialize;
mod sexpr;

// NOT gated on `python`. The wasm32 tier builds with --no-default-features,
// so an added `python` gate here would silently exclude the registry and the
// runner would fail to compile against it. `wasm-registry` is implied by every
// per-family feature and by `wasm-test-registry`, so any wasm build compiles
// this module.
// Generated by `scripts/gen_wasm_test_registry.py --crate temper-design-bundle`.
//
// Proptest-mirroring audit (2026-08-10): this crate has 28 `proptest!`
// invocations (29 individual property fns) across three modules --
// `gates.rs::proptests` (6 invocations / 8 fns), `host_math.rs::proptests`
// (21 invocations / 21 fns), and `fixed_copper_builder.rs::tests` (1
// invocation / 2 fns, `net_display_round_trips` + `net_display_never_panics`).
// All three modules are declared `#[cfg(feature = "python")]` above (`mod
// gates;`, `mod host_math;`, `mod fixed_copper_builder;`) and confirmed
// `[python-gated]` by `--census`, so all 28 are structurally absent from a
// `--no-default-features` build -- same exclusion class as every other pyo3
// module here, just also carrying `proptest`. Checked whether any target
// kernel is reachable outside the gate regardless (`py_str_repr`/
// `py_float_str` in gates.rs, `pow`/`sqrt`/`hypot`/`py_max`/`py_min`/
// `py_round`/`py_float_mod`/`py_log` in host_math.rs, `net_display` in
// fixed_copper_builder.rs): none is used by, or duplicated in, any of the
// five non-gated modules registered above (`constraint_merge`, `identity`,
// `kicad_pcb`, `netlist`, `pcl`) -- `grep` across those five for every kernel
// name returns nothing. So none of the 28 can be mirrored as a deterministic
// campaign here; doing so would require first un-gating the module, which is
// a structural change outside this audit's scope. Zero campaigns added.
#[cfg(feature = "wasm-registry")]
pub mod wasm_test_registry;

pub use atopile::{
    AtopileComponent, AtopileExport, AtopileNet, MappingEntry, NetMapping, SafetyRule,
};
pub use error::{DesignBundleError, Diagnostic};
pub use identity::{BoardIdentityOptions, validate_board_identity};
pub use kicad_pcb::extract_footprint_references;
pub use model::*;
pub use netlist::extract_component_references;
pub use pcl::{PclDocument, PclInputConstraint};
// Non-pyo3 parse-core entry point + the raw board model it returns. The
// pyo3 wrapper (`parse_kicad_pcb_impl`) calls the same `parse_kicad_document`;
// exposing it here lets the `temper` binary and other non-Python consumers
// parse a `.kicad_pcb` without an interpreter. `RawBoard` and its constituent
// types are pub so the returned value is fully inspectable; they are the
// faithful kiutils-model shapes, not a stable long-term API (the CLI driver
// consumes them read-only).
pub use parse_engine::{
    parse_board_summary, parse_kicad_document, BoardSummary, Num, RawBoard, RawFootprint,
    RawPad, RawPos, RawTraceItem, RawZone,
};

/// Constructs the canonical boundary from already-read source documents.
pub fn build_bundle(
    atopile: AtopileExport,
    mapping: NetMapping,
    pcl: PclDocument,
    board: BoardSpec,
    hashes: Provenance,
) -> Result<DesignBundle, DesignBundleError> {
    identity::validate(&atopile, &mapping, &board)?;
    let derived = atopile.derived_constraints();
    let authored = pcl.into_constraints(&atopile)?;
    let constraints = constraint_merge::merge(derived, authored)?;
    Ok(DesignBundle {
        schema_version: 1,
        board,
        components: atopile.components,
        nets: atopile.nets,
        net_classes: atopile.net_classes,
        safety_domains: atopile.safety_domains,
        stackup: atopile.stackup,
        constraints,
        provenance: hashes,
    })
}

/// Serialize a [`DesignBundle`] to normalized JSON.
pub fn normalized_json(bundle: &DesignBundle) -> Result<String, DesignBundleError> {
    serialize::normalized_json(bundle)
}

/// Compute the SHA-256 hash of arbitrary bytes.
pub fn sha256(bytes: &[u8]) -> String {
    serialize::sha256(bytes)
}

/// Parse an atopile export from JSON bytes.
pub fn parse_atopile(bytes: &[u8]) -> Result<AtopileExport, DesignBundleError> {
    serde_json::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

/// Parse a net-to-footprint mapping from YAML bytes.
pub fn parse_mapping(bytes: &[u8]) -> Result<NetMapping, DesignBundleError> {
    serde_yaml::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

/// Parse a PCL constraint document from YAML bytes.
pub fn parse_pcl(bytes: &[u8]) -> Result<PclDocument, DesignBundleError> {
    serde_yaml::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::{
        BoardIdentityOptions, BoardRole, extract_component_references,
        extract_footprint_references, sha256, validate_board_identity,
    };

    fn value_error(error: impl std::fmt::Display) -> PyErr {
        PyValueError::new_err(error.to_string())
    }

    /// Exposes the crate's canonical SHA-256 (used internally for
    /// `Provenance`) across the boundary so pipeline code hashes inputs the
    /// same way the bundle itself does, rather than re-implementing hashing
    /// in Python with `hashlib` directly.
    #[pyfunction]
    fn sha256_hex(bytes: &[u8]) -> String {
        sha256(bytes)
    }

    /// Fail-closed board/netlist identity preflight. Raises `ValueError` on
    /// any mismatch or role violation -- never returns a warning or a bool,
    /// per the identity-provenance plan's hard-fail requirement. Callers
    /// (`InputStage`, `scripts/ci_closure_test.py`) read files themselves and
    /// pass bytes across the boundary; `pcb_path` is used only to infer the
    /// board's role from its path (a `benchmarks` path component means
    /// `Fixture`), never to re-read the file on the Rust side.
    #[pyfunction]
    #[pyo3(signature = (pcb_path, pcb_bytes, netlist_bytes, min_overlap=0.95, bring_up=false))]
    fn preflight_identity(
        pcb_path: &str,
        pcb_bytes: &[u8],
        netlist_bytes: &[u8],
        min_overlap: f64,
        bring_up: bool,
    ) -> PyResult<()> {
        let pcb_text = std::str::from_utf8(pcb_bytes).map_err(value_error)?;
        let netlist_text = std::str::from_utf8(netlist_bytes).map_err(value_error)?;
        let board_refs = extract_footprint_references(pcb_text).map_err(value_error)?;
        let netlist_refs = extract_component_references(netlist_text).map_err(value_error)?;
        let role = BoardRole::from_path(std::path::Path::new(pcb_path));
        let opts = BoardIdentityOptions {
            min_overlap,
            bring_up,
        };
        validate_board_identity(&board_refs, &netlist_refs, role, true, &opts).map_err(value_error)
    }

    #[pymodule]
    fn temper_design_bundle_python(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add_function(wrap_pyfunction!(preflight_identity, module)?)?;
        module.add_function(wrap_pyfunction!(sha256_hex, module)?)?;

        // Wave 4 Phase 3 (formats/IO): _write_board.py's numeric kernels
        // (see write_board_geometry.rs).
        crate::write_board_geometry::register(module)?;

        // Wave 4 Phase 2 contracts-as-pyclasses: the net-types data model
        // ported from temper_placer/core/net_types.py (see net_types.rs),
        // then the loop-centric data model ported from
        // temper_placer/core/loop.py (see loops.rs), then the design-rules
        // data model ported from temper_placer/core/design_rules.py (see
        // design_rules.rs), then the gate-contract data model ported from
        // temper_placer/placer/cp_sat/gates.py (see gates.rs).
        crate::net_types::register(module)?;
        crate::loops::register(module)?;
        crate::design_rules::register(module)?;
        crate::gates::register(module)?;
        crate::priority::register(module)?;

        // Wave 4 Phase 5 first slice: deterministic leaf-stage compute
        // (slot_generation / zone_geometry / zone_assignment kernels) ported
        // from temper_placer/deterministic/stages/ (see deterministic_stages.rs).
        crate::deterministic_stages::register(module)?;
        crate::deterministic_leaves::register(module)?;
        crate::deterministic_phase::register(module)?;

        // Wave 4 Phase 3 candidate 1: the parse-target contracts ported from
        // temper_placer/core/netlist.py (see netlist_contracts.rs) and
        // temper_placer/core/board.py (see board_contracts.rs). Both are
        // registered under `Netlist*`/`Board*`-prefixed names because the two
        // source modules each define a DIFFERENT class called `Component`;
        // flattening them into one namespace would silently alias them.
        crate::netlist_contracts::register(module)?;
        crate::net_graph_contracts::register(module)?;
        crate::differential_pair_contracts::register(module)?;
        crate::bus_cohort_contracts::register(module)?;
        crate::decision_contracts::register(module)?;
        crate::geometry_types_contracts::register(module)?;
        crate::topology_extraction_contracts::register(module)?;
        crate::channel_skeleton_contracts::register(module)?;
        crate::topological_graph_contracts::register(module)?;
        crate::loop_ownership_contracts::register(module)?;
        crate::specification_contracts::register(module)?;
        crate::board_contracts::register(module)?;

        // Orchestration plan Phase A unit U7: the typed terminal-extraction
        // wire format and the typed Coo container (see the module docstrings
        // and packages/temper-design-bundle/VERIFICATION.md).
        crate::terminal_wire_contracts::register(module)?;
        crate::hypergraph_contracts::register(module)?;

        // Orchestration plan Phase A unit U9: the typed loop-extraction
        // wire marshalers (see loop_extraction_contracts.rs and
        // packages/temper-design-bundle/VERIFICATION.md).
        crate::loop_extraction_contracts::register(module)?;

        // Wave 4 Phase 3 candidate 5: the config/reference loaders. The
        // preprocess transform, the load chain, and the downstream helpers
        // (see config_loader.rs / reference_loader.rs) — PyYAML + pydantic are
        // called back across the boundary.
        module.add_function(wrap_pyfunction!(
            crate::config_loader::preprocess_config,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::config_loader::load_constraints,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(crate::config_loader::infer_rjc, module)?)?;
        module.add_function(wrap_pyfunction!(
            crate::config_loader::create_board_from_constraints,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::config_loader::constraints_to_design_rules,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::config_loader::apply_zones_to_netlist,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::config_loader::apply_fixed_components_to_netlist,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::reference_loader::compute_design_stats,
            module
        )?)?;
        module.add_function(wrap_pyfunction!(
            crate::reference_loader::infer_quality_config,
            module
        )?)?;
        crate::parse_engine::register(module)?;

        // Wave 4 Phase 3 candidate 2: the YAML loaders ported from
        // temper_placer/io/netclass_loader.py and
        // temper_placer/io/loop_loader.py (see loaders.rs). They bind onto
        // the Phase-2 contracts registered above, which is why they are the
        // phase's opportunistic first pull.
        crate::loaders::register(module)?;

        // Wave 4 Phase 5 (deterministic hubs slice): the deterministic hub
        // kernels. See deterministic_hubs.rs; registered after loaders so the
        // leaf-stages branch's deterministic_stages registration (appended on
        // its own branch) merges without textual conflict.
        crate::deterministic_hubs::register(module)?;

        // Wave 4 Phase 4: the validation-remainder decision kernels
        // (validation/preflight.py, netlist_reconciliation.py,
        // placement_roundtrip.py, prereg/schema.py) registered as the
        // `validation` submodule (see validation.rs).
        crate::validation::register(module)?;

        // Wave 4 Phase 4 — regression slice: the measure-closure /
        // cp_sat_comparison / fingerprint / schema_validator kernels (see
        // the module docstrings and VERIFICATION.md).
        crate::measure_closure::register(module)?;
        crate::fingerprint::register(module)?;
        crate::schema_validator::register(module)?;

        // ...and then the PCL contract layer: the tag-expression algebra
        // ported from temper_placer/pcl/tag_dispatch.py (see pcl_tags.rs)
        // plus the parse primitives from temper_placer/pcl/_parse_utils.py
        // (see pcl_parse.rs).
        crate::pcl_tags::register(module)?;
        crate::pcl_parse::register(module)?;

        // Wave 4: the router_v6/constraint_model.py compute kernels (see
        // constraint_model.rs). Registered last so the append conflicts with
        // no parallel wave-4 branch.
        crate::constraint_model::register(module)?;
        // Orchestration plan Phase E batch E1: the constraint-model builder
        // orchestration + contract pyclasses (see model_builder.rs).
        crate::model_builder::register(module)?;
        // Orchestration plan Phase E batch E2: the fixed-copper builder
        // orchestration + contract pyclasses (see fixed_copper_builder.rs).
        crate::fixed_copper_builder::register(module)?;
        // Wave 4 follow-up: the hv_lv_partition stage's decision kernels
        // (see hv_lv_partition.rs). Registered after constraint_model.
        crate::hv_lv_partition::register(module)?;

        // Safety-critical values with provenance: the recovered
        // IEC 60335-1 Table 16/17/18 lookups (see safety_value.rs).
        crate::safety_value::register(module)?;
        crate::safety_value_authority::register(module)?;
        crate::regional_topology::register(module)?;
        Ok(())
    }
}

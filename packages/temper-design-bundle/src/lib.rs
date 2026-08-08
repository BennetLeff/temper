#[cfg(feature = "python")]
mod net_types;

// Wave 4 Phase 3 (formats/IO): the two GEOMETRY/matching kernels ported out
// of temper_placer/io/kicad_exporter.py (snap_to_nearest_pad,
// _generate_connector_segments) — see kicad_exporter_geometry.rs's module
// docstring for the full triage of what was and was not ported.
#[cfg(feature = "python")]
mod kicad_exporter_geometry;

// Wave 4 Phase 3 (formats/IO): the two numeric kernels ported out of
// temper_placer/io/_write_board.py (_reorient_pads's per-pad angle update,
// state_to_placements's original-angle offset preservation) — see
// write_board_geometry.rs's module docstring for the full triage of what
// was and was not ported.
#[cfg(feature = "python")]
mod write_board_geometry;

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
mod net_graph_contracts;
#[cfg(feature = "python")]
mod differential_pair_contracts;

#[cfg(feature = "python")]
mod board_contracts;

#[cfg(feature = "python")]
mod config_loader;

#[cfg(feature = "python")]
mod reference_loader;

#[cfg(feature = "python")]
mod parse_engine;
#[cfg(feature = "python")]
mod manufacturing_tolerances;
#[cfg(feature = "python")]
mod manufacturing_monte_carlo;
#[cfg(feature = "python")]
mod hypergraph_factory;

#[cfg(feature = "python")]
mod loaders;

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
#[cfg(feature = "python")]
mod cp_sat_comparison;
#[cfg(feature = "python")]
mod fingerprint;
#[cfg(feature = "python")]
mod measure_closure;
#[cfg(feature = "python")]
mod schema_validator;

#[cfg(feature = "python")]
mod validation;
mod atopile;
mod constraint_merge;
mod error;
mod identity;
mod kicad_pcb;
mod model;
mod netlist;
mod pcl;
mod serialize;
mod sexpr;

pub use atopile::{
    AtopileComponent, AtopileExport, AtopileNet, MappingEntry, NetMapping, SafetyRule,
};
pub use error::{DesignBundleError, Diagnostic};
pub use identity::{BoardIdentityOptions, validate_board_identity};
pub use kicad_pcb::extract_footprint_references;
pub use model::*;
pub use netlist::extract_component_references;
pub use pcl::{PclDocument, PclInputConstraint};

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
        BoardIdentityOptions, BoardRole, Provenance, build_bundle, extract_component_references,
        extract_footprint_references, normalized_json, parse_atopile, parse_mapping, parse_pcl,
        sha256, validate_board_identity,
    };

    fn value_error(error: impl std::fmt::Display) -> PyErr {
        PyValueError::new_err(error.to_string())
    }

    #[pyfunction]
    fn normalized_bundle_json(
        atopile_json: &[u8],
        mapping_yaml: &[u8],
        pcl_yaml: &[u8],
        board_bytes: &[u8],
    ) -> PyResult<String> {
        let atopile = parse_atopile(atopile_json).map_err(value_error)?;
        let board = atopile.board.clone();
        let provenance = Provenance {
            atopile_sha256: sha256(atopile_json),
            mapping_sha256: sha256(mapping_yaml),
            pcl_sha256: sha256(pcl_yaml),
            board_sha256: sha256(board_bytes),
        };
        let bundle = build_bundle(
            atopile,
            parse_mapping(mapping_yaml).map_err(value_error)?,
            parse_pcl(pcl_yaml).map_err(value_error)?,
            board,
            provenance,
        )
        .map_err(value_error)?;
        normalized_json(&bundle).map_err(value_error)
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
        module.add_function(wrap_pyfunction!(normalized_bundle_json, module)?)?;
        module.add_function(wrap_pyfunction!(preflight_identity, module)?)?;
        module.add_function(wrap_pyfunction!(sha256_hex, module)?)?;

        // Wave 4 Phase 3 (formats/IO): kicad_exporter.py's geometry kernels
        // (see kicad_exporter_geometry.rs). Registered early since it has no
        // dependency on the contracts pyclasses below.
        crate::kicad_exporter_geometry::register(module)?;

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
        crate::board_contracts::register(module)?;

        // Wave 4 Phase 3 candidate 5: the config/reference loaders. The
        // preprocess transform, the load chain, and the downstream helpers
        // (see config_loader.rs / reference_loader.rs) — PyYAML + pydantic are
        // called back across the boundary.
        module.add_function(wrap_pyfunction!(crate::config_loader::preprocess_config, module)?)?;
        module.add_function(wrap_pyfunction!(crate::config_loader::load_constraints, module)?)?;
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

        // Wave 4 Phase 4 leftovers slice: the manufacturing tolerance model
        // ported from temper_placer/manufacturing/tolerances.py (see
        // manufacturing_tolerances.rs).
        crate::manufacturing_tolerances::register(module)?;

        // Wave 4 Phase 4 leftovers slice: the Monte-Carlo tolerance
        // simulator ported from temper_placer/manufacturing/monte_carlo.py
        // (see manufacturing_monte_carlo.rs — the numpy RNG/aggregation
        // boundary is argued in that module's docstring).
        crate::manufacturing_monte_carlo::register(module)?;

        // Wave 4 Phase 4 leftovers slice: the hypergraph factory ported
        // from temper_placer/extraction/hypergraph_factory.py (see
        // hypergraph_factory.rs — scipy/numpy/set-iteration stay Python).
        crate::hypergraph_factory::register(module)?;

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
        crate::cp_sat_comparison::register(module)?;
        crate::fingerprint::register(module)?;
        crate::schema_validator::register(module)?;

        // ...and then the PCL contract layer: the tag-expression algebra
        // ported from temper_placer/pcl/tag_dispatch.py (see pcl_tags.rs)
        // plus the parse primitives from temper_placer/pcl/_parse_utils.py
        // (see pcl_parse.rs).
        crate::pcl_tags::register(module)?;
        crate::pcl_parse::register(module)
    }
}
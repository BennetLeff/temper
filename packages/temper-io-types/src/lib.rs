// temper-io-types: KiCad PCB IO types (trace segments, vias, golden
// diff/serializers, reference aliases, stackup validation).
//
// This crate is split into a pure Rust core — plain structs and free
// functions with no pyo3 dependency, compiling for `wasm32-unknown-unknown`
// — and a thin `#[cfg(feature = "python")]` pyo3 boundary that adapts
// those types to/from Python objects. `python` is a default feature so
// every existing Python consumer (`temper_placer.io.*`) builds unchanged;
// wasm/other pure-Rust consumers build with `--no-default-features`.
//
// What's genuinely pure now (see each module for detail):
//   - export_types:      TraceSegment, TraceVia, ExportResult (data only)
//   - isolation:          isolation_slot_aabb (pure geometry)
//   - dsn_types:          DSN S-expression formatting (DsnArg/DsnExpressionData)
//   - footprint_spec:     FootprintSpec (data only)
//
// What stays pyo3-only, and why (no pure core to extract):
//   - zone_filler — shells out to a live Python interpreter + KiCad's
//     `pcbnew` C++ extension via `subprocess`; there is no kernel to make
//     pure, and wasm32 has neither a filesystem nor process spawning.

// WASM tier R1 (plan 2026-08-03-002): with `--no-default-features` the whole
// pyo3 surface (`explain`, `report`, `reference_aliases`, `footprint_library`,
// `dsn_pyo3`, `zone_filler` and each module's `*_py` bridges) is not compiled,
// so the pure helpers those bridges call look unused to rustc -- it cannot see
// past the cfg gate.  Allow dead_code in that configuration only, exactly as
// `temper-geometry` and `temper-thermal` do; the default (python) build keeps
// the lint.
#![cfg_attr(not(feature = "python"), allow(dead_code))]

pub mod dag_expr;
pub mod dsn;
pub mod dsn_exporter;
pub mod dsn_types;
// Wholly a pyo3 surface: every item in `explain` takes or returns a
// `Bound<'_, PyAny>` — the migration deliberately left the dataclass,
// `str()`, `set`-iteration and `json.dumps` semantics on the Python side
// (see the module doc), so there is no kernel underneath the bridge to
// compile without pyo3.  WASM tier R1 (plan 2026-08-03-002).
#[cfg(feature = "python")]
pub mod explain;
pub mod export_types;
// Wholly a pyo3 surface: `FootprintLibrary` is a `#[pyclass]` holding a
// `Py<PyDict>` and `load_footprint_library` reads YAML by calling back into
// Python's `yaml.safe_load`.  Nothing here exists without pyo3.
#[cfg(feature = "python")]
pub mod footprint_library;
pub mod footprint_spec;
pub mod isolation;
pub mod kicad_write_geometry;
// Wave-4 tail-tooling migration: the regression golden-manifest path sets
// and validation (temper_placer/regression/manifest.py) — the path-set
// rules (resolve_path / baseline_yaml_path / baseline_pcb_path) and the
// missing-PCB validation. Pure core (wasm32-safe); the pyo3 boundary lives
// behind the python feature. See the module doc for the migrated-vs-kept
// split (YAML ingestion and get_board stay Python).
pub mod manifest;
// Wave-4 Phase 2: the placer's core/ CONTRACT layer (Rect, PinInfo,
// PlacementViolation, FabPreset + the pure kernels of units,
// net_classification, manufacturing, placement_drc and the netlist
// adjacency builder). See placer_core/mod.rs for what is deliberately
// not here and why.
pub mod placer_core;
// Property campaign (R7 / WASM-tier volume): metamorphic/invariant
// properties over three pure, deterministic kernels -- placer_core::netclass's
// classification precedence and case-folding contract,
// placer_core::adjacency's build_adjacency_matrix, and
// placer_core::pyrepr's CPython-exact float repr(). See that module's doc
// comment. Declared after placer_core (which it depends on).
pub mod property_campaigns;
pub mod provenance;
pub mod pyfmt;
// Wave-4 tail-tooling migration: the dead-letter quarantine compute
// (temper_placer/testing/quarantine.py) — `classify_error`, the
// `compute_stack_hash` SHA-256 prefix and the `compute_fingerprint` content
// kernels. Pure core (wasm32-safe); the pyo3 boundary and the fs-backed
// fingerprint read live behind the python feature. See the module doc for
// the migrated-vs-kept-Python split.
pub mod quarantine;
// Wholly a pyo3 surface: `ReferenceAliasManifest` is a `#[pyclass]` and the
// loader reads its manifest through Python's `yaml.safe_load` and compares
// names with Python `str.strip` semantics (the M4 divergence its own test
// documents), so the module cannot exist without the interpreter.
#[cfg(feature = "python")]
pub mod reference_aliases;
// Wholly a pyo3 surface: every entry point takes the optimiser's Python
// result objects and reads their attributes across the boundary (`str()`,
// `.get(k, default)`, `history[-1]`), by design — see the module doc.
#[cfg(feature = "python")]
pub mod report;

pub mod stackup_validator;

// NOT gated on `python`. The wasm32 tier builds with --no-default-features,
// so an added `python` gate here would silently exclude the registry and the
// runner would fail to compile against it. `wasm-registry` is implied by every
// per-family feature and by `wasm-test-registry`, so any wasm build compiles
// this module.
// Generated by `scripts/gen_wasm_test_registry.py --crate temper-io-types`.
#[cfg(feature = "wasm-registry")]
pub mod wasm_test_registry;

#[cfg(feature = "python")]
pub mod zone_filler;

// Wave 4, Phase 3 tail: DSN (Specctra) format utilities, consolidated from the
// deleted temper-dsn crate. `dsn` (declared above with the other modules)
// holds the pure kernels and their unit tests; `dsn_pyo3` is the wholly-pyo3
// surface (see its module doc).
#[cfg(feature = "python")]
pub mod dsn_pyo3;
// Pure-Rust paren-balanced removal of committed copper s-expression blocks
// (segment/via/zone) from KiCad board content -- the
// router_v6/_strip_copper.py migration (see VERIFICATION.md). Pure core
// (wasm32-safe) with a thin pyo3 boundary, following the `isolation` shape.
pub mod strip_copper;
// Tolerance-aware golden-output comparison kernels (DSN place/net parse +
// diff, SES wire parse + diff, recursive tolerance JSON diff) -- the
// testing/golden_diff.py migration (see VERIFICATION.md). Pure core
// (wasm32-safe) with a thin pyo3 boundary, following the `strip_copper`
// shape. The three `golden_diff_*` pyfunctions return
// `(entries, passed, summary)` for the Python shim's `DiffEntry(**e)`.
pub mod golden_diff;

#[cfg(feature = "python")]
mod pymodule_def {
    use pyo3::prelude::*;

    #[pymodule]
    fn temper_io_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
        // Which Cargo profile this extension was built with. The dag_expr
        // performance A/B reads it: an unoptimised build of the same code
        // measured 0.51x vs Python where the release build measures 2.70x,
        // so a debug .so silently turns a speed-up into a apparent
        // regression. Better to say so than to publish the wrong number.
        m.add(
            "BUILD_PROFILE",
            if cfg!(debug_assertions) { "debug" } else { "release" },
        )?;

        m.add(
            "DagExprSyntaxError",
            m.py().get_type::<crate::dag_expr::DagExprSyntaxError>(),
        )?;
        m.add("DagExprError", m.py().get_type::<crate::dag_expr::DagExprError>())?;

        // Classes
        m.add_class::<crate::dag_expr::PySkipExpr>()?;
        m.add_class::<crate::export_types::PyTraceSegment>()?;
        m.add_class::<crate::export_types::PyTraceVia>()?;
        m.add_class::<crate::export_types::PyExportResult>()?;
        m.add_class::<crate::dsn_types::DSNExpression>()?;
        m.add_class::<crate::dsn_exporter::PyDsnExporterCore>()?;
        m.add_class::<crate::dsn_types::PyDsnRect>()?;
        m.add_class::<crate::dsn_types::PyDsnCircle>()?;
        m.add_class::<crate::dsn_types::PyDsnPath>()?;
        m.add_class::<crate::footprint_spec::PyFootprintSpec>()?;
        m.add_class::<crate::footprint_library::PyFootprintLibrary>()?;
        m.add_class::<crate::reference_aliases::PyReferenceAliasManifest>()?;

        // Functions
        m.add_function(wrap_pyfunction!(crate::dag_expr::parse_skip_expr_rs, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::isolation::isolation_slot_aabb_py,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::dsn_types::dsn_list, m)?)?;
        // Wave-4 tail-tooling — quarantine compute (testing/quarantine.py).
        m.add_function(wrap_pyfunction!(crate::quarantine::classify_error, m)?)?;
        m.add_function(wrap_pyfunction!(crate::quarantine::compute_stack_hash, m)?)?;
        m.add_function(wrap_pyfunction!(crate::quarantine::compute_fingerprint, m)?)?;
        // Wave-4 tail-tooling — regression golden-manifest path sets
        // (regression/manifest.py).
        m.add_function(wrap_pyfunction!(crate::manifest::resolve_board_path_py, m)?)?;
        m.add_function(wrap_pyfunction!(crate::manifest::baseline_yaml_path_py, m)?)?;
        m.add_function(wrap_pyfunction!(crate::manifest::baseline_pcb_path_py, m)?)?;
        m.add_function(wrap_pyfunction!(crate::manifest::validate_board_paths, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::footprint_library::load_footprint_library,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::reference_aliases::load_reference_alias_manifest,
            m
        )?)?;
        // Wave-4 Phase 2 contract layer.
        crate::placer_core::pybridge::register(m)?;

        // Wave 4 Phase 5 — report surface (report.rs).
        m.add_function(wrap_pyfunction!(crate::report::report_format_text, m)?)?;
        m.add_function(wrap_pyfunction!(crate::report::report_format_json_data, m)?)?;
        m.add_function(wrap_pyfunction!(crate::report::report_format_html, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::report::report_calculate_benchmark_result,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::report::report_benchmark_json_data,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::report::report_generate_summary,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::report::report_extract_key_metrics,
            m
        )?)?;
        // Wave 4 Phase 5 — explainability surface (explain.rs).
        m.add_function(wrap_pyfunction!(crate::explain::explain_trace_why, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_decision_trace_why,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_decision_trace_why_not,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_decision_trace_history,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_decision_trace_summary,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::explain::explain_should_log, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_significant_change,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::explain::explain_log_position, m)?)?;
        m.add_function(wrap_pyfunction!(crate::explain::explain_log_rotation, m)?)?;
        m.add_function(wrap_pyfunction!(crate::explain::explain_log_heuristic, m)?)?;
        m.add_function(wrap_pyfunction!(crate::explain::explain_log_constraint, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_render_markdown_report,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_render_component_report,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_serialize_value,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_deserialize_value,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_serialize_alternative,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_serialize_decision,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_serialize_trace,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_constraint_subject,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_trace_threshold,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::explain::explain_compose_traces,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::zone_filler::fill_zones_pcbnew, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::zone_filler::fill_zones_if_present,
            m
        )?)?;

        // Wave 4 Phase 4 leftovers slice: the stackup validator ported from
        // temper_placer/manufacturing/stackup_validator.py (see
        // stackup_validator.rs).
        crate::stackup_validator::register(m)?;

        // Wave 4 — kicad-write geometry kernels (io/_write_* + placement_exporter).
        crate::kicad_write_geometry::register(m)?;

        // Wave 4 Phase 3 tail — DSN format utilities (from temper-dsn).
        crate::dsn_pyo3::register(m)?;

        // Wave 4 — paren-balanced copper/zone strip kernels
        // (router_v6/_strip_copper.py migration).
        crate::strip_copper::register(m)?;

        // Wave 4 — tolerance-aware golden-diff kernels
        // (testing/golden_diff.py migration).
        crate::golden_diff::register(m)?;

        Ok(())
    }
}

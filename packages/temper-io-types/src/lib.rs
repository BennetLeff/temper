// temper-io-types: KiCad PCB IO types (trace segments, vias, footprint
// parsing, golden serializers).
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
//   - footprint:          FootprintBounds + regex-based courtyard parsing
//   - isolation:          isolation_slot_aabb (pure geometry)
//   - golden_serializers: format_float/round6, SES text, violations/
//                         connectivity JSON (via serde_json)
//   - dsn_types:          DSN S-expression formatting (DsnArg/DsnExpressionData)
//   - footprint_spec:     FootprintSpec (data only)
//   - provenance:         Provenance + sha256_hex (via sha2)
//   - config_binding:     extract_config_refs / missing-ref diff (via
//                         serde_json::Value in place of PyDict/PyList/PyTuple)
//
// What stays pyo3-only, and why (no pure core to extract):
//   - golden_serializers::serialize_boardstate_to_dsn — calls back into a
//     real Python class (`DSNExporter`) that implements the export
//     algorithm itself; nothing in Python even imports the Rust
//     DSNExpression/DSNRect/DSNCircle/DSNPath types instead.
//   - zone_filler — shells out to a live Python interpreter + KiCad's
//     `pcbnew` C++ extension via `subprocess`; there is no kernel to make
//     pure, and wasm32 has neither a filesystem nor process spawning.
//   - footprint::parse_footprint_directory / the file-reading half of
//     parse_footprint_courtyard — `std::fs`, gated `not(target_arch =
//     "wasm32")` rather than pure logic; the parsing itself
//     (`parse_footprint_courtyard_str`) is pure and wasm32-exported.

pub mod config_binding;
pub mod dsn_types;
pub mod export_types;
pub mod footprint;
pub mod footprint_library;
pub mod footprint_spec;
pub mod golden_serializers;
pub mod isolation;
pub mod kicad_write;
pub mod provenance;
pub mod reference_aliases;
#[cfg(feature = "python")]
pub mod zone_filler;

#[cfg(feature = "python")]
mod pymodule_def {
    use pyo3::prelude::*;
    use pyo3::types::PyDict;

    #[pymodule]
    fn temper_io_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add(
            "CURRENT_FORMAT_VERSION",
            crate::golden_serializers::CURRENT_FORMAT_VERSION,
        )?;

        // Exceptions
        m.add(
            "FootprintParseError",
            m.py().get_type::<crate::footprint::FootprintParseError>(),
        )?;
        m.add(
            "ConfigBoardMismatchError",
            m.py()
                .get_type::<crate::config_binding::ConfigBoardMismatchError>(),
        )?;

        // Classes
        m.add_class::<crate::export_types::PyTraceSegment>()?;
        m.add_class::<crate::export_types::PyTraceVia>()?;
        m.add_class::<crate::export_types::PyExportResult>()?;
        m.add_class::<crate::footprint::PyFootprintBounds>()?;
        m.add_class::<crate::dsn_types::DSNExpression>()?;
        m.add_class::<crate::dsn_types::PyDsnRect>()?;
        m.add_class::<crate::dsn_types::PyDsnCircle>()?;
        m.add_class::<crate::dsn_types::PyDsnPath>()?;
        m.add_class::<crate::footprint_spec::PyFootprintSpec>()?;
        m.add_class::<crate::footprint_library::PyFootprintLibrary>()?;
        m.add_class::<crate::provenance::PyProvenance>()?;
        m.add_class::<crate::kicad_write::PyPlacementUpdate>()?;
        m.add_class::<crate::kicad_write::PyWriteResult>()?;
        m.add_class::<crate::kicad_write::PyStrippingResult>()?;
        m.add_class::<crate::kicad_write::PyIsolationSlotResult>()?;
        m.add_class::<crate::reference_aliases::PyReferenceAliasManifest>()?;
        // Functions
        m.add_function(wrap_pyfunction!(
            crate::footprint::parse_footprint_courtyard,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::footprint::parse_footprint_directory,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::isolation::isolation_slot_aabb_py,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::golden_serializers::serialize_boardstate_to_dsn,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::golden_serializers::serialize_boardstate_to_ses,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::golden_serializers::serialize_violations_to_json,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::golden_serializers::serialize_connectivity_to_json,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::dsn_types::dsn_list, m)?)?;
        m.add_function(wrap_pyfunction!(crate::provenance::sha256_hex_py, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::footprint_library::load_footprint_library,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::reference_aliases::load_reference_alias_manifest,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::config_binding::extract_config_refs_py,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::config_binding::verify_config_matches_netlist,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::zone_filler::fill_zones_pcbnew, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::zone_filler::fill_zones_if_present,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::path_to_segments,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::kicad_write::path_to_vias, m)?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::extract_pad_centers,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::snap_to_nearest_pad_py,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::generate_connector_segments,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::validate_4_layer_output,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::state_to_placements,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::extract_original_angles,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::extract_center_offsets,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::positions_to_placements,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::rotation_index_to_degrees,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::reorient_pad_angle,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::placements_to_json,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::placements_from_json,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::compute_to247_isolation_slots,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::get_footprint_reference,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::compute_pad_bounds,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::get_routing_statistics,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::net_name_to_index_map,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::export_route_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::export_board_state_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::strip_routing_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::write_routes_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::write_zones_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::write_placements_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::add_isolation_slots_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(
            crate::kicad_write::export_from_geometry_plan,
            m
        )?)?;
        m.add_function(wrap_pyfunction!(crate::kicad_write::fp_annotations, m)?)?;

        // SERIALIZER_REGISTRY
        let registry = PyDict::new(m.py());
        registry.set_item(
            "serialize_boardstate_to_dsn",
            m.getattr("serialize_boardstate_to_dsn")?,
        )?;
        registry.set_item(
            "serialize_boardstate_to_ses",
            m.getattr("serialize_boardstate_to_ses")?,
        )?;
        registry.set_item(
            "serialize_violations_to_json",
            m.getattr("serialize_violations_to_json")?,
        )?;
        registry.set_item(
            "serialize_connectivity_to_json",
            m.getattr("serialize_connectivity_to_json")?,
        )?;
        m.add("SERIALIZER_REGISTRY", registry)?;

        Ok(())
    }
}

mod atopile;
mod constraint_merge;
mod error;
mod identity;
mod kicad_pcb;
mod model;
mod pcl;
mod serialize;

pub use atopile::{
    AtopileComponent, AtopileExport, AtopileNet, MappingEntry, NetMapping, SafetyRule,
};
pub use error::{DesignBundleError, Diagnostic};
pub use identity::{BoardIdentityOptions, validate_board_identity};
pub use kicad_pcb::extract_footprint_references;
pub use model::*;
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

pub fn normalized_json(bundle: &DesignBundle) -> Result<String, DesignBundleError> {
    serialize::normalized_json(bundle)
}

pub fn sha256(bytes: &[u8]) -> String {
    serialize::sha256(bytes)
}

pub fn parse_atopile(bytes: &[u8]) -> Result<AtopileExport, DesignBundleError> {
    serde_json::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

pub fn parse_mapping(bytes: &[u8]) -> Result<NetMapping, DesignBundleError> {
    serde_yaml::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

pub fn parse_pcl(bytes: &[u8]) -> Result<PclDocument, DesignBundleError> {
    serde_yaml::from_slice(bytes).map_err(|e| DesignBundleError::Document(e.to_string()))
}

#[cfg(feature = "python")]
mod python {
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    use crate::{
        Provenance, build_bundle, normalized_json, parse_atopile, parse_mapping, parse_pcl, sha256,
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

    #[pymodule]
    fn temper_design_bundle_python(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module.add_function(wrap_pyfunction!(normalized_bundle_json, module)?)
    }
}

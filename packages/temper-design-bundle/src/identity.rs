use crate::{
    BoardSpec,
    atopile::{AtopileExport, NetMapping},
    error::{DesignBundleError, diagnostic},
};
use std::collections::HashSet;

pub fn validate(
    atopile: &AtopileExport,
    mapping: &NetMapping,
    board: &BoardSpec,
) -> Result<(), DesignBundleError> {
    if atopile.schema_version != 1 || mapping.schema_version != 1 {
        return Err(diagnostic(
            "unsupported_schema",
            "only schema version 1 is supported",
            vec![],
        ));
    }
    if !atopile.board.validate()
        || !board.validate()
        || atopile.board.width_mm != board.width_mm
        || atopile.board.height_mm != board.height_mm
    {
        return Err(diagnostic(
            "board_geometry",
            "Atopile and KiCad board geometry differs or is invalid",
            vec![],
        ));
    }

    let mut ids = HashSet::new();
    for component in &atopile.components {
        if !ids.insert(component.id.clone()) {
            return Err(diagnostic(
                "duplicate_component",
                format!("duplicate component '{}'", component.id),
                vec![component.id.clone()],
            ));
        }
    }
    for net in &atopile.nets {
        if !ids.insert(net.id.clone()) {
            return Err(diagnostic(
                "duplicate_net",
                format!("duplicate canonical net '{}'", net.id),
                vec![net.id.clone()],
            ));
        }
    }
    for net_class in &atopile.net_classes {
        if !net_class.clearance_mm.is_finite()
            || net_class.clearance_mm < 0.0
            || net_class
                .creepage_mm
                .is_some_and(|value| !value.is_finite() || value < 0.0)
        {
            return Err(diagnostic(
                "invalid_unit",
                format!("net class '{}' has invalid dimensions", net_class.id),
                vec![net_class.id.clone()],
            ));
        }
    }

    let known_references: HashSet<_> = atopile
        .components
        .iter()
        .map(|component| component.id.as_str())
        .chain(atopile.nets.iter().map(|net| net.id.as_str()))
        .chain(atopile.zones.iter().map(String::as_str))
        .chain(atopile.loops.iter().map(String::as_str))
        .collect();
    for rule in &atopile.safety {
        if !rule.value_mm.is_finite() || rule.value_mm < 0.0 {
            return Err(diagnostic(
                "invalid_unit",
                format!("safety rule '{}' has invalid millimetres", rule.id),
                vec![rule.id.clone()],
            ));
        }
        if !known_references.contains(rule.subject.as_str()) {
            return Err(diagnostic(
                "unresolved_reference",
                format!("safety rule '{}' references {}", rule.id, rule.subject),
                vec![rule.id.clone(), rule.subject.clone()],
            ));
        }
    }

    let names: HashSet<_> = atopile.nets.iter().map(|net| net.name.as_str()).collect();
    let mut signals = HashSet::new();
    for entry in &mapping.entries {
        if !signals.insert(entry.atopile_signal.clone()) {
            return Err(diagnostic(
                "ambiguous_mapping",
                format!(
                    "Atopile signal '{}' is mapped more than once",
                    entry.atopile_signal
                ),
                vec![entry.atopile_signal.clone()],
            ));
        }
        if !names.contains(entry.kicad_net.as_str()) {
            return Err(diagnostic(
                "unknown_mapping",
                format!(
                    "{} maps to missing KiCad net {}",
                    entry.atopile_signal, entry.kicad_net
                ),
                vec![entry.atopile_signal.clone(), entry.kicad_net.clone()],
            ));
        }
    }
    Ok(())
}

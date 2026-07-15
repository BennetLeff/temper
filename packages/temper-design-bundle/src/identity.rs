use crate::{
    BoardSpec,
    atopile::{AtopileExport, NetMapping},
    error::{DesignBundleError, diagnostic},
    model::BoardRole,
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

/// Construction-time parameters for [`validate_board_identity`]. A threshold
/// is a policy decision (not derivable from the files), so it lives here as
/// an explicit parameter with a safe default -- never as a hand-typed
/// per-board number.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BoardIdentityOptions {
    /// Minimum fraction of netlist refs that must also appear on the board
    /// for a `Production`-role board to pass.
    pub min_overlap: f64,
    /// Explicit opt-in for boards under active bring-up, where a
    /// partially-populated board is expected to fall below `min_overlap`.
    /// Off by default; must be set deliberately, never inferred.
    pub bring_up: bool,
}

impl Default for BoardIdentityOptions {
    fn default() -> Self {
        Self {
            min_overlap: 0.95,
            bring_up: false,
        }
    }
}

const MAX_DISJOINT_REFS_SAMPLE: usize = 20;

/// Verifies a KiCad board's footprint reference designators correspond to the
/// netlist's component references, deriving both sets from the files rather
/// than any declared count. Fails closed:
/// - A `Fixture`-role board (path-derived, see [`BoardRole::from_path`]) can
///   never construct a production bundle, regardless of ref overlap.
/// - A `Production`-role board must clear `opts.min_overlap` unless
///   `opts.bring_up` is explicitly set.
pub fn validate_board_identity(
    board_refs: &HashSet<String>,
    netlist_refs: &HashSet<String>,
    role: BoardRole,
    building_production: bool,
    opts: &BoardIdentityOptions,
) -> Result<(), DesignBundleError> {
    if role == BoardRole::Fixture && building_production {
        return Err(diagnostic(
            "role_violation",
            "board path is a quarantined fixture and cannot construct a production bundle",
            vec![],
        ));
    }

    if !building_production {
        return Ok(());
    }

    if netlist_refs.is_empty() {
        return Err(diagnostic(
            "identity_mismatch",
            "netlist has no component references to validate against",
            vec![],
        ));
    }

    let overlap_count = board_refs.intersection(netlist_refs).count();
    let ratio = overlap_count as f64 / netlist_refs.len() as f64;

    if ratio < opts.min_overlap && !opts.bring_up {
        let mut only_in_board: Vec<String> = board_refs.difference(netlist_refs).cloned().collect();
        let mut only_in_netlist: Vec<String> =
            netlist_refs.difference(board_refs).cloned().collect();
        only_in_board.sort();
        only_in_netlist.sort();
        let total_only_in_board = only_in_board.len();
        let total_only_in_netlist = only_in_netlist.len();
        only_in_board.truncate(MAX_DISJOINT_REFS_SAMPLE);
        only_in_netlist.truncate(MAX_DISJOINT_REFS_SAMPLE);

        let mut references = only_in_board;
        references.extend(only_in_netlist);

        return Err(diagnostic(
            "identity_mismatch",
            format!(
                "board/netlist ref overlap {:.1}% is below the required {:.1}% \
                 ({total_only_in_board} refs only in board, {total_only_in_netlist} \
                 refs only in netlist; sample below)",
                ratio * 100.0,
                opts.min_overlap * 100.0,
            ),
            references,
        ));
    }

    Ok(())
}

#[cfg(test)]
mod board_identity_tests {
    use super::*;
    use std::path::Path;

    fn refs(values: &[&str]) -> HashSet<String> {
        values.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn full_overlap_production_board_passes() {
        let board = refs(&["U1", "U2", "U3"]);
        let netlist = refs(&["U1", "U2", "U3"]);
        let result = validate_board_identity(
            &board,
            &netlist,
            BoardRole::Production,
            true,
            &BoardIdentityOptions::default(),
        );
        assert!(result.is_ok());
    }

    #[test]
    fn mismatched_fixture_ratio_fails_closed() {
        // The exact bug this closes: a 33-ref fixture against a 100-ref
        // netlist, ~4% overlap.
        let board: HashSet<String> = (1..=33).map(|n| format!("U{n}")).collect();
        let netlist: HashSet<String> = (1..=100).map(|n| format!("U{n}")).collect();
        let err = validate_board_identity(
            &board,
            &netlist,
            BoardRole::Production,
            true,
            &BoardIdentityOptions::default(),
        )
        .unwrap_err();
        match err {
            DesignBundleError::Validation(diags) => {
                assert_eq!(diags[0].code, "identity_mismatch");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn fixture_role_path_rejects_production_bundle_regardless_of_overlap() {
        let board = refs(&["U1", "U2", "U3"]);
        let netlist = refs(&["U1", "U2", "U3"]);
        let role = BoardRole::from_path(Path::new("pcb/benchmarks/temper_fixture_33.kicad_pcb"));
        assert_eq!(role, BoardRole::Fixture);
        let err = validate_board_identity(
            &board,
            &netlist,
            role,
            true,
            &BoardIdentityOptions::default(),
        )
        .unwrap_err();
        match err {
            DesignBundleError::Validation(diags) => {
                assert_eq!(diags[0].code, "role_violation");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn non_benchmarks_path_is_production_role() {
        let role = BoardRole::from_path(Path::new("pcb/temper.kicad_pcb"));
        assert_eq!(role, BoardRole::Production);
    }

    #[test]
    fn bring_up_mode_permits_partial_overlap_explicitly() {
        let board = refs(&["U1", "U2"]);
        let netlist: HashSet<String> = (1..=100).map(|n| format!("U{n}")).collect();
        let opts = BoardIdentityOptions {
            min_overlap: 0.95,
            bring_up: true,
        };
        let result = validate_board_identity(&board, &netlist, BoardRole::Production, true, &opts);
        assert!(result.is_ok());
    }

    #[test]
    fn bring_up_mode_off_by_default_still_fails_on_partial_overlap() {
        let board = refs(&["U1", "U2"]);
        let netlist: HashSet<String> = (1..=100).map(|n| format!("U{n}")).collect();
        let result = validate_board_identity(
            &board,
            &netlist,
            BoardRole::Production,
            true,
            &BoardIdentityOptions::default(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn empty_netlist_is_a_deterministic_error_not_a_divide_by_zero() {
        let board = refs(&["U1"]);
        let netlist: HashSet<String> = HashSet::new();
        let err = validate_board_identity(
            &board,
            &netlist,
            BoardRole::Production,
            true,
            &BoardIdentityOptions::default(),
        )
        .unwrap_err();
        match err {
            DesignBundleError::Validation(diags) => {
                assert_eq!(diags[0].code, "identity_mismatch");
            }
            other => panic!("expected Validation error, got {other:?}"),
        }
    }

    #[test]
    fn non_production_construction_skips_the_check_entirely() {
        // A fixture bundle explicitly requested (building_production=false)
        // is not held to the production overlap bar.
        let board = refs(&["U1"]);
        let netlist: HashSet<String> = (1..=100).map(|n| format!("U{n}")).collect();
        let result = validate_board_identity(
            &board,
            &netlist,
            BoardRole::Fixture,
            false,
            &BoardIdentityOptions::default(),
        );
        assert!(result.is_ok());
    }
}

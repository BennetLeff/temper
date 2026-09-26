use crate::{
    BoardSpec,
    atopile::{AtopileExport, NetMapping},
    error::{DesignBundleError, diagnostic},
    model::BoardRole,
};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

/// Validate that the board identity (atopile, netlist, footprint refs)
/// is consistent and internally coherent.
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

    let mut ids: HashSet<&str> = HashSet::new();
    for component in &atopile.components {
        if !ids.insert(component.id.as_str()) {
            return Err(diagnostic(
                "duplicate_component",
                format!("duplicate component '{}'", component.id),
                vec![component.id.clone()],
            ));
        }
    }
    for net in &atopile.nets {
        if !ids.insert(net.id.as_str()) {
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
    let mut signals: HashSet<&str> = HashSet::new();
    for entry in &mapping.entries {
        if !signals.insert(entry.atopile_signal.as_str()) {
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

// ---------------------------------------------------------------------------
// Strict source-to-board pin map (P1 U2, MCU candidate profile).
//
// Every required compiled pin must map to the actual numbered footprint pad,
// using an explicit reviewed alias note where names differ. The positional
// pad fallback the legacy skeleton generator applies (mapping by pad order
// when numbers differ) is forbidden here: it is unverifiable against the
// manufacturer pin table and normalizes both sides of the comparison through
// the same guess. Omitted components, unintended opens, extra connectivity,
// and unreviewed aliases all fail admission.
// ---------------------------------------------------------------------------

/// One reviewed pin-to-pad assignment. `pin` is the compiled netlist pin
/// number; `pad` is the actual numbered pad in the resolved library bytes.
/// `pin != pad` is allowed only with a non-empty `alias_note` naming the
/// review (e.g. manufacturer-table alias). `positional = true` marks an
/// order-based guess and is always rejected.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrictPinMapEntry {
    pub instance_path: String,
    pub reference: String,
    pub pin: String,
    pub pad: String,
    #[serde(default)]
    pub alias_note: String,
    #[serde(default)]
    pub positional: bool,
}

/// Fail-closed strict map validation.
///
/// - `entries`: the explicit reviewed map, one per required `(ref, pin)`.
/// - `footprint_pads`: `reference ->` actual pad numbers in library-byte
///   order; repeats are allowed (a footprint may expose the same number
///   twice) and must share one pin/net.
/// - `netlist_pins`: `reference ->` compiled pins.
/// - `unconnected_pads`: explicit `(reference, pad)` pairs with no
///   connection; anything else unmapped fails as an unintended open.
pub fn validate_strict_pin_map(
    entries: &[StrictPinMapEntry],
    footprint_pads: &HashMap<String, Vec<String>>,
    netlist_pins: &HashMap<String, Vec<String>>,
    unconnected_pads: &HashSet<(String, String)>,
) -> Result<(), DesignBundleError> {
    let mut seen_pin: HashSet<(&str, &str)> = HashSet::new();
    for entry in entries {
        if !seen_pin.insert((entry.reference.as_str(), entry.pin.as_str())) {
            return Err(diagnostic(
                "duplicate_map",
                format!(
                    "map covers {}.{} more than once",
                    entry.reference, entry.pin
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            ));
        }
        if entry.positional {
            return Err(diagnostic(
                "positional_fallback",
                format!(
                    "map entry {}.{} is positional-only; exact pad numbers are required",
                    entry.reference, entry.pin
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            ));
        }
        let pins = netlist_pins.get(&entry.reference).ok_or_else(|| {
            diagnostic(
                "extra_map",
                format!(
                    "map entry {}.{} names a reference absent from the compiled netlist",
                    entry.reference, entry.pin
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            )
        })?;
        if !pins.iter().any(|p| p == &entry.pin) {
            return Err(diagnostic(
                "extra_map",
                format!(
                    "map entry {}.{} names a pin absent from the compiled netlist",
                    entry.reference, entry.pin
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            ));
        }
        let pads = footprint_pads.get(&entry.reference).ok_or_else(|| {
            diagnostic(
                "unknown_pad",
                format!(
                    "map entry {}.{} names a reference with no resolved footprint pads",
                    entry.reference, entry.pin
                ),
                vec![entry.reference.clone()],
            )
        })?;
        if !pads.iter().any(|p| p == &entry.pad) {
            return Err(diagnostic(
                "unknown_pad",
                format!(
                    "map entry {}.{} targets pad '{}' absent from the resolved footprint",
                    entry.reference, entry.pin, entry.pad
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            ));
        }
        if entry.pin != entry.pad && entry.alias_note.trim().is_empty() {
            return Err(diagnostic(
                "unreviewed_alias",
                format!(
                    "map entry {}.{} -> pad '{}' differs without a reviewed alias note",
                    entry.reference, entry.pin, entry.pad
                ),
                vec![entry.reference.clone(), entry.pin.clone()],
            ));
        }
        if unconnected_pads.contains(&(entry.reference.clone(), entry.pad.clone())) {
            return Err(diagnostic(
                "contradictory_pad",
                format!(
                    "pad '{}' on {} is both mapped and listed unconnected",
                    entry.pad, entry.reference
                ),
                vec![entry.reference.clone(), entry.pad.clone()],
            ));
        }
    }
    // One pad number claimed by two different pins is a split identity,
    // even when the footprint repeats the number: repeated same-number pads
    // must share one pin/net.
    let mut pad_owner: HashMap<(&str, &str), &str> = HashMap::new();
    for entry in entries {
        let key = (entry.reference.as_str(), entry.pad.as_str());
        match pad_owner.get(&key) {
            Some(owner) if *owner != entry.pin.as_str() => {
                return Err(diagnostic(
                    "split_pad",
                    format!(
                        "pad '{}' on {} is claimed by pins '{owner}' and '{}'",
                        entry.pad, entry.reference, entry.pin
                    ),
                    vec![entry.reference.clone(), entry.pad.clone()],
                ));
            }
            _ => {
                pad_owner.insert(key, entry.pin.as_str());
            }
        }
    }
    // Every compiled pin must be mapped: an omitted component or pin is an
    // unintended open, never a silent spare.
    for (reference, pins) in netlist_pins {
        for pin in pins {
            if !seen_pin.contains(&(reference.as_str(), pin.as_str())) {
                return Err(diagnostic(
                    "missing_map",
                    format!("compiled pin {reference}.{pin} has no map entry"),
                    vec![reference.clone(), pin.clone()],
                ));
            }
        }
    }
    // Every actual pad must be mapped or explicitly unconnected.
    for (reference, pads) in footprint_pads {
        for pad in pads {
            let mapped = pad_owner.contains_key(&(reference.as_str(), pad.as_str()));
            let listed = unconnected_pads.contains(&(reference.clone(), pad.clone()));
            if mapped && listed {
                return Err(diagnostic(
                    "contradictory_pad",
                    format!("pad '{pad}' on {reference} is both mapped and listed unconnected"),
                    vec![reference.clone(), pad.clone()],
                ));
            }
            if !mapped && !listed {
                return Err(diagnostic(
                    "unmapped_pad",
                    format!(
                        "footprint pad '{pad}' on {reference} is neither mapped nor explicitly unconnected"
                    ),
                    vec![reference.clone(), pad.clone()],
                ));
            }
            if listed {
                // An explicitly unconnected pad must not carry a compiled
                // pin of the same number: that pin would be an open the
                // listing hides.
                if netlist_pins
                    .get(reference)
                    .is_some_and(|pins| pins.iter().any(|p| p == pad))
                {
                    return Err(diagnostic(
                        "false_unconnected",
                        format!(
                            "pad '{pad}' on {reference} is listed unconnected but carries compiled pin '{pad}'"
                        ),
                        vec![reference.clone(), pad.clone()],
                    ));
                }
            }
        }
    }
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod strict_pin_map_tests {
    use super::*;

    fn entry(reference: &str, pin: &str, pad: &str) -> StrictPinMapEntry {
        StrictPinMapEntry {
            instance_path: format!("m.{reference}"),
            reference: reference.to_string(),
            pin: pin.to_string(),
            pad: pad.to_string(),
            alias_note: String::new(),
            positional: false,
        }
    }

    fn case() -> (
        Vec<StrictPinMapEntry>,
        HashMap<String, Vec<String>>,
        HashMap<String, Vec<String>>,
        HashSet<(String, String)>,
    ) {
        (
            vec![entry("U1", "1", "1"), entry("U1", "2", "2")],
            HashMap::from([("U1".to_string(), vec!["1".to_string(), "2".to_string()])]),
            HashMap::from([("U1".to_string(), vec!["1".to_string(), "2".to_string()])]),
            HashSet::new(),
        )
    }

    fn code(err: &DesignBundleError) -> String {
        match err {
            DesignBundleError::Validation(diags) => diags[0].code.clone(),
            other => panic!("expected Validation, got {other:?}"),
        }
    }

    #[cfg_attr(test, test)]
    fn exact_map_passes() {
        let (entries, pads, pins, unconnected) = case();
        validate_strict_pin_map(&entries, &pads, &pins, &unconnected).expect("exact map passes");
    }

    #[cfg_attr(test, test)]
    fn repeated_same_number_pads_share_one_pin() {
        let (_, mut pads, pins, unconnected) = case();
        pads.get_mut("U1").expect("U1 pads").push("1".to_string());
        // The repeated pad number is covered by the single pin-1 entry: no
        // second entry is needed and none is allowed to split the net.
        let entries = vec![entry("U1", "1", "1"), entry("U1", "2", "2")];
        validate_strict_pin_map(&entries, &pads, &pins, &unconnected)
            .expect("repeated same-number pads on one pin pass");
    }

    #[cfg_attr(test, test)]
    fn split_pad_number_fails() {
        let (mut entries, pads, mut pins, unconnected) = case();
        pins.get_mut("U1").expect("U1 pins").push("3".to_string());
        let mut aliased = entry("U1", "3", "1");
        aliased.alias_note = "reviewed".to_string();
        entries.push(aliased);
        let err = validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err();
        assert_eq!(code(&err), "split_pad");
    }

    #[cfg_attr(test, test)]
    fn positional_missing_unreviewed_and_unmapped_fail() {
        let (mut entries, pads, pins, unconnected) = case();
        entries[0].positional = true;
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "positional_fallback"
        );
        let (mut entries, pads, pins, unconnected) = case();
        entries.pop();
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "missing_map"
        );
        let (mut entries, pads, pins, unconnected) = case();
        entries[0].pad = "2".to_string();
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "unreviewed_alias"
        );
        let (entries, mut pads, pins, unconnected) = case();
        pads.get_mut("U1").expect("U1 pads").push("3".to_string());
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "unmapped_pad"
        );
    }

    #[cfg_attr(test, test)]
    fn explicit_unconnected_pad_passes_but_hiding_a_pin_fails() {
        let (entries, mut pads, pins, mut unconnected) = case();
        pads.get_mut("U1").expect("U1 pads").push("9".to_string());
        unconnected.insert(("U1".to_string(), "9".to_string()));
        validate_strict_pin_map(&entries, &pads, &pins, &unconnected)
            .expect("explicit unconnected pad passes");

        // Same listing, but pin 9 is compiled and unmapped: missing_map
        // fires (the open is named, never hidden by the listing).
        let (entries, _, mut pins, mut unconnected) = case();
        pins.get_mut("U1").expect("U1 pins").push("9".to_string());
        let pads2: HashMap<String, Vec<String>> = HashMap::from([(
            "U1".to_string(),
            vec!["1".to_string(), "2".to_string(), "9".to_string()],
        )]);
        unconnected.insert(("U1".to_string(), "9".to_string()));
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads2, &pins, &unconnected).unwrap_err()),
            "missing_map"
        );
    }

    #[cfg_attr(test, test)]
    fn duplicate_and_extra_entries_fail() {
        let (mut entries, pads, pins, unconnected) = case();
        entries.push(entry("U1", "1", "1"));
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "duplicate_map"
        );
        let (mut entries, pads, pins, unconnected) = case();
        entries.push(entry("U1", "7", "2"));
        assert_eq!(
            code(&validate_strict_pin_map(&entries, &pads, &pins, &unconnected).unwrap_err()),
            "extra_map"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: strict_pin_map_tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("identity::strict_pin_map_tests::exact_map_passes", exact_map_passes),
        ("identity::strict_pin_map_tests::repeated_same_number_pads_share_one_pin", repeated_same_number_pads_share_one_pin),
        ("identity::strict_pin_map_tests::split_pad_number_fails", split_pad_number_fails),
        ("identity::strict_pin_map_tests::positional_missing_unreviewed_and_unmapped_fail", positional_missing_unreviewed_and_unmapped_fail),
        ("identity::strict_pin_map_tests::explicit_unconnected_pad_passes_but_hiding_a_pin_fails", explicit_unconnected_pad_passes_but_hiding_a_pin_fails),
        ("identity::strict_pin_map_tests::duplicate_and_extra_entries_fail", duplicate_and_extra_entries_fail),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: strict_pin_map_tests ---
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod board_identity_tests {
    use super::*;
    use std::path::Path;

    fn refs(values: &[&str]) -> HashSet<String> {
        values.iter().map(|s| s.to_string()).collect()
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn non_benchmarks_path_is_production_role() {
        let role = BoardRole::from_path(Path::new("pcb/temper.kicad_pcb"));
        assert_eq!(role, BoardRole::Production);
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: board_identity_tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("identity::board_identity_tests::full_overlap_production_board_passes", full_overlap_production_board_passes),
        ("identity::board_identity_tests::mismatched_fixture_ratio_fails_closed", mismatched_fixture_ratio_fails_closed),
        ("identity::board_identity_tests::fixture_role_path_rejects_production_bundle_regardless_of_overlap", fixture_role_path_rejects_production_bundle_regardless_of_overlap),
        ("identity::board_identity_tests::non_benchmarks_path_is_production_role", non_benchmarks_path_is_production_role),
        ("identity::board_identity_tests::bring_up_mode_permits_partial_overlap_explicitly", bring_up_mode_permits_partial_overlap_explicitly),
        ("identity::board_identity_tests::bring_up_mode_off_by_default_still_fails_on_partial_overlap", bring_up_mode_off_by_default_still_fails_on_partial_overlap),
        ("identity::board_identity_tests::empty_netlist_is_a_deterministic_error_not_a_divide_by_zero", empty_netlist_is_a_deterministic_error_not_a_divide_by_zero),
        ("identity::board_identity_tests::non_production_construction_skips_the_check_entirely", non_production_construction_skips_the_check_entirely),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: board_identity_tests ---
}

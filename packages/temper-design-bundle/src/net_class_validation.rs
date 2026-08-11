//! Parse-don't-validate `net_classes` mapping: makes an unresolvable
//! `net_name -> net_class` key structurally impossible to carry forward.
//!
//! Motivating defect (2026-08-11): 31 `net_classes` keys across 4 config
//! files name no real net on `pcb/temper.kicad_pcb` (e.g. `AC_L`/`AC_N` vs.
//! the board's `ac_l`/`ac_n`, `PE` vs. no such net at all). The production
//! consumer, `Netlist::apply_net_class_mapping` (`netlist_contracts.rs`),
//! does an exact-key `dict`-style lookup and silently skips a miss --
//! by design, since it must stay bit-identical to the pinned Python oracle
//! (`packages/temper-placer/tests/core/_netlist_py_oracle.py`). A mains-live,
//! mains-neutral, or protective-earth net can silently keep the lowest-
//! clearance default class this way, with no error and no log line.
//!
//! `ValidatedNetClassMap::resolve` is the boundary fix: it is the only way
//! to obtain a `ValidatedNetClassMap`, and it can only be obtained when
//! *every* key in the raw mapping names a real net. A raw mapping with even
//! one unresolvable key produces `Err` with every unresolved key listed (not
//! just the first) -- never a partially-resolved value. See
//! `docs/evidence/2026-08-11-typed-net-refs-spike.md` for the design
//! rationale (case-sensitivity, why this boundary and not a handle-based
//! `NetId`, and what the pyo3 crossing does and does not preserve).

use std::collections::{BTreeMap, BTreeSet};

/// A net name that has been checked against a real net table. The inner
/// field is private -- the only way to produce one is
/// `ValidatedNetClassMap::resolve` succeeding, which requires the exact
/// (case-sensitive) string to already be present in the table of real net
/// names. There is no public constructor that skips that check.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NetName(String);

// Lets `ValidatedNetClassMap::get` look a `NetName`-keyed `BTreeMap` up by
// `&str` directly, without allocating a throwaway `NetName` per lookup.
impl std::borrow::Borrow<str> for NetName {
    fn borrow(&self) -> &str {
        &self.0
    }
}

/// One `net_classes` key that names no real net, carried alongside the
/// class name it was trying to assign -- enough to reproduce the exact
/// VIOLATION line `check_netclass_map_board_correspondence.py` prints.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnresolvedNetClassKey {
    pub raw_key: String,
    pub class_name: String,
}

/// A `net_name -> net_class` mapping in which every key has already been
/// checked, exactly, against a real net table.
///
/// There is no `From<HashMap<String, String>>`, no public field, and no
/// constructor other than `resolve`. A `ValidatedNetClassMap` that contains
/// an unresolvable key is not a bug to catch at review time -- it is a
/// value the type does not admit.
#[derive(Debug, Clone, Default)]
pub struct ValidatedNetClassMap(BTreeMap<NetName, String>);

impl ValidatedNetClassMap {
    /// Check `raw` against `known_nets`, case-sensitive exact match.
    ///
    /// All-or-nothing: `Ok` only when every key resolves. `Err` carries
    /// *every* unresolved key (not just the first), matching
    /// `check_netclass_map_board_correspondence.py`'s "report everything in
    /// one pass" behavior -- an operator fixing 4 typos should not have to
    /// re-run this 4 times to discover them one at a time.
    pub fn resolve(
        known_nets: &BTreeSet<String>,
        raw: &BTreeMap<String, String>,
    ) -> Result<Self, Vec<UnresolvedNetClassKey>> {
        let mut resolved = BTreeMap::new();
        let mut errors = Vec::new();
        for (key, class_name) in raw {
            if known_nets.contains(key) {
                resolved.insert(NetName(key.clone()), class_name.clone());
            } else {
                errors.push(UnresolvedNetClassKey {
                    raw_key: key.clone(),
                    class_name: class_name.clone(),
                });
            }
        }
        if errors.is_empty() {
            Ok(Self(resolved))
        } else {
            Err(errors)
        }
    }

    /// The class assigned to `net_name`, if `net_name` was a key of the
    /// mapping this was resolved from.
    pub fn get(&self, net_name: &str) -> Option<&str> {
        self.0.get(net_name).map(String::as_str)
    }

    #[cfg(any(test, feature = "wasm-registry"))]
    fn len(&self) -> usize {
        self.0.len()
    }

    #[cfg(any(test, feature = "wasm-registry"))]
    fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

/// Render the same shape of message
/// `check_netclass_map_board_correspondence.py` prints per violation, joined
/// into one error so a `PyValueError` surfaces every broken key at once.
pub fn format_unresolved(errors: &[UnresolvedNetClassKey]) -> String {
    let mut out = format!(
        "{} net_classes key(s) do not match any real net on this Netlist \
         (case-sensitive exact match) -- each assignment would otherwise be \
         a silent no-op:\n",
        errors.len()
    );
    for e in errors {
        out.push_str(&format!(
            "  net_classes[{:?}] = {:?} -- {:?} is not a real net name\n",
            e.raw_key, e.class_name, e.raw_key
        ));
    }
    out
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn nets(names: &[&str]) -> BTreeSet<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    fn mapping(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[cfg_attr(test, test)]
    fn exact_match_resolves() {
        let known = nets(&["ac_l", "ac_n", "gnd"]);
        let raw = mapping(&[("ac_l", "ACMains"), ("gnd", "Ground")]);
        let resolved = ValidatedNetClassMap::resolve(&known, &raw).expect("should resolve");
        assert_eq!(resolved.len(), 2);
        assert_eq!(resolved.get("ac_l"), Some("ACMains"));
        assert_eq!(resolved.get("gnd"), Some("Ground"));
    }

    #[cfg_attr(test, test)]
    fn unknown_net_is_rejected() {
        let known = nets(&["ac_l", "ac_n", "gnd"]);
        let raw = mapping(&[("PE", "ACMains")]);
        let errors = ValidatedNetClassMap::resolve(&known, &raw).unwrap_err();
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0].raw_key, "PE");
        assert_eq!(errors[0].class_name, "ACMains");
    }

    /// The safety-critical case: `AC_L` vs. the board's real `ac_l` must be
    /// a hard error, not a case-normalized match. See the spike doc's
    /// case-sensitivity section for why normalizing would be less safe.
    #[cfg_attr(test, test)]
    fn case_mismatch_is_a_hard_error_not_a_silent_fold() {
        let known = nets(&["ac_l"]);
        let raw = mapping(&[("AC_L", "ACMains")]);
        let errors = ValidatedNetClassMap::resolve(&known, &raw).unwrap_err();
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0].raw_key, "AC_L");
    }

    #[cfg_attr(test, test)]
    fn all_unresolved_keys_are_reported_not_just_the_first() {
        let known = nets(&["gnd"]);
        let raw = mapping(&[
            ("AC_L", "ACMains"),
            ("AC_N", "ACMains"),
            ("PE", "ACMains"),
            ("GND", "Ground"),
        ]);
        let errors = ValidatedNetClassMap::resolve(&known, &raw).unwrap_err();
        assert_eq!(errors.len(), 4);
    }

    #[cfg_attr(test, test)]
    fn one_bad_key_rejects_the_whole_mapping_not_just_that_key() {
        // All-or-nothing: a caller must never be able to observe a
        // "mostly resolved" ValidatedNetClassMap.
        let known = nets(&["ac_l", "gnd"]);
        let raw = mapping(&[("ac_l", "ACMains"), ("PE", "ACMains")]);
        assert!(ValidatedNetClassMap::resolve(&known, &raw).is_err());
    }

    #[cfg_attr(test, test)]
    fn empty_mapping_is_trivially_valid() {
        let known = nets(&["ac_l"]);
        let resolved = ValidatedNetClassMap::resolve(&known, &BTreeMap::new()).unwrap();
        assert!(resolved.is_empty());
    }

    #[cfg_attr(test, test)]
    fn empty_net_table_rejects_any_nonempty_mapping() {
        let known = BTreeSet::new();
        let raw = mapping(&[("ac_l", "ACMains")]);
        let errors = ValidatedNetClassMap::resolve(&known, &raw).unwrap_err();
        assert_eq!(errors.len(), 1);
    }

    /// Reproduces the real 2026-08-11 defect shape (four of the actual
    /// broken keys from `packages/temper-placer/configs/temper_constraints.yaml`
    /// against the board's real net names) without depending on either
    /// file's current, possibly-since-fixed content.
    #[cfg_attr(test, test)]
    fn reproduces_the_real_defect_shape() {
        let known = nets(&["ac_l", "ac_n", "gnd", "gate_hs", "gate_ls", "+170v_bus"]);
        let raw = mapping(&[
            ("AC_L", "ACMains"),
            ("AC_N", "ACMains"),
            ("GND", "Ground"),
            ("PE", "ACMains"),
        ]);
        let errors = ValidatedNetClassMap::resolve(&known, &raw).unwrap_err();
        assert_eq!(errors.len(), 4);
        let msg = format_unresolved(&errors);
        assert!(msg.contains("4 net_classes key(s)"));
        assert!(msg.contains("\"PE\""));
    }

    #[cfg_attr(test, test)]
    fn format_unresolved_names_every_key() {
        let errors = vec![
            UnresolvedNetClassKey { raw_key: "AC_L".into(), class_name: "ACMains".into() },
            UnresolvedNetClassKey { raw_key: "PE".into(), class_name: "ACMains".into() },
        ];
        let msg = format_unresolved(&errors);
        assert!(msg.contains("AC_L"));
        assert!(msg.contains("PE"));
        assert!(msg.starts_with("2 net_classes key(s)"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("net_class_validation::tests::exact_match_resolves", exact_match_resolves),
        ("net_class_validation::tests::unknown_net_is_rejected", unknown_net_is_rejected),
        ("net_class_validation::tests::case_mismatch_is_a_hard_error_not_a_silent_fold", case_mismatch_is_a_hard_error_not_a_silent_fold),
        ("net_class_validation::tests::all_unresolved_keys_are_reported_not_just_the_first", all_unresolved_keys_are_reported_not_just_the_first),
        ("net_class_validation::tests::one_bad_key_rejects_the_whole_mapping_not_just_that_key", one_bad_key_rejects_the_whole_mapping_not_just_that_key),
        ("net_class_validation::tests::empty_mapping_is_trivially_valid", empty_mapping_is_trivially_valid),
        ("net_class_validation::tests::empty_net_table_rejects_any_nonempty_mapping", empty_net_table_rejects_any_nonempty_mapping),
        ("net_class_validation::tests::reproduces_the_real_defect_shape", reproduces_the_real_defect_shape),
        ("net_class_validation::tests::format_unresolved_names_every_key", format_unresolved_names_every_key),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

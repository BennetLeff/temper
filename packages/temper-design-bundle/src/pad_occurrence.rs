//! `PadOccurrence` -- a typed, unambiguous physical-pad identity.
//!
//! # The footgun this exists to remove
//!
//! `(component_ref, pad_number)` reads exactly like a unique key for "the
//! physical pad" everywhere in this codebase -- `Net.pins`,
//! `Component.get_pin`, dozens of `for comp_ref, pin_name in net.pins:`
//! loops. It is not one. A footprint can fabricate more than one physical
//! solder pad under the same pad number/name, and this board does: K2/K3
//! (`temper:Relay_SPDT_Schrack-RT314012`) have pads "1", "3", and "4" each
//! duplicated -- two physical holes 7.5mm apart per logical contact, wired
//! in parallel for 16A current sharing. `Component.get_pin(name)` (the
//! pyo3 method, `netlist_contracts.rs`) always returns its FIRST
//! name/number match; calling it once per `net.pins` occurrence silently
//! collapses two distinct physical terminals onto one coordinate. That
//! exact mechanism made the router print "routed successfully" for
//! `discharge.k_dis1-no`/`discharge.k_dis2-no` while writing zero
//! connecting copper (see `_pipeline_grid._nth_matching_pin`'s docstring
//! for the full incident, and this crate's own `get_pin` doc).
//!
//! # What makes wrong usage fail
//!
//! A pad number alone is not enough to build a `PadOccurrence` -- there is
//! deliberately no `From<&str>` / `From<String>` impl. The `occurrence`
//! index (0-based, in a component's own pin-list encounter order among
//! pins sharing that number) must be named explicitly at construction.
//! "I want pad 3" without saying which of the (possibly several) physical
//! pad-3 holes is meant does not compile. See the `compile_fail` doctest
//! below (`cargo test --doc -p temper-design-bundle`, green).
//!
//! # Why this is additive, not a retrofit
//!
//! The actual disambiguation logic today lives in Python
//! (`temper_placer.core.pad_identity`, calling the new
//! `Component.get_pin_occurrences` pyo3 method added alongside this type)
//! because every current consumer of pad identity is Python: `grep -rn
//! "\.get_pin("` across every `*.rs` in this workspace finds zero real
//! Rust call sites, only comments describing the Python method of the
//! same name. This type exists so that if/when pad resolution migrates to
//! Rust (this repo's established Wave-4 pattern for other subsystems), the
//! ambiguous-by-construction shape cannot be reintroduced silently -- it
//! is infrastructure for that future code, not a change in behavior for
//! any code that exists today. Mirrors `temper-geometry::rotation_quadrant
//! ::RotationQuadrant`'s own "additive, not a retrofit" judgment call
//! exactly (see that module's doc for the precedent).

/// Identifies exactly one physical pad on one component: a pad `number`
/// (KiCad's pad name/number string, e.g. `"3"`) plus which `occurrence`
/// (0-based) among a component's own pins sharing that number -- 0 unless
/// the footprint duplicates the number, in which case every occurrence
/// must be named to be distinguishable at all.
///
/// # Example
///
/// ```
/// use temper_design_bundle::pad_occurrence::PadOccurrence;
///
/// // K2's two physical pad-"3" holes, 7.5mm apart, are two DIFFERENT
/// // PadOccurrence values -- not the same key twice.
/// let first = PadOccurrence::new("3", 0);
/// let second = PadOccurrence::new("3", 1);
/// assert_ne!(first, second);
/// assert_eq!(first.pin_number(), "3");
/// assert_eq!(second.occurrence(), 1);
/// ```
///
/// # The footgun, made a compile error
///
/// ```compile_fail
/// use temper_design_bundle::pad_occurrence::PadOccurrence;
///
/// // Must NOT compile: there is no From<&str> for PadOccurrence, so a
/// // bare pad number cannot silently stand in for "the" pad -- the exact
/// // defect class this type exists to prevent (get_pin's first-match
/// // shortcut, applied to a footprint with duplicate pad numbers) is a
/// // compile error here instead of a silent wrong answer.
/// let _bad: PadOccurrence = "3".into();
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PadOccurrence {
    pin_number: String,
    occurrence: usize,
}

impl PadOccurrence {
    /// Build a `PadOccurrence` naming both the pad number and which
    /// occurrence of it is meant. `occurrence = 0` is the common,
    /// unambiguous case (a footprint with no duplicate pad numbers for
    /// this number has exactly one occurrence); the caller still writes
    /// it explicitly, never implicitly.
    pub fn new(pin_number: impl Into<String>, occurrence: usize) -> Self {
        Self {
            pin_number: pin_number.into(),
            occurrence,
        }
    }

    /// The pad number/name (KiCad's pad identifier string).
    pub fn pin_number(&self) -> &str {
        &self.pin_number
    }

    /// The 0-based occurrence index among same-numbered pins.
    pub fn occurrence(&self) -> usize {
        self.occurrence
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distinct_occurrences_of_the_same_pad_number_are_unequal() {
        assert_ne!(PadOccurrence::new("3", 0), PadOccurrence::new("3", 1));
    }

    #[test]
    fn same_pad_number_and_occurrence_are_equal() {
        assert_eq!(PadOccurrence::new("3", 0), PadOccurrence::new("3", 0));
    }

    #[test]
    fn different_pad_numbers_at_the_same_occurrence_are_unequal() {
        assert_ne!(PadOccurrence::new("3", 0), PadOccurrence::new("4", 0));
    }

    #[test]
    fn accessors_round_trip_the_constructor_arguments() {
        let pad = PadOccurrence::new("3", 1);
        assert_eq!(pad.pin_number(), "3");
        assert_eq!(pad.occurrence(), 1);
    }

    #[test]
    fn is_hashable_so_it_can_key_a_map_of_resolved_pads() {
        use std::collections::HashSet;
        let mut set = HashSet::new();
        set.insert(PadOccurrence::new("3", 0));
        set.insert(PadOccurrence::new("3", 1));
        assert_eq!(set.len(), 2);
    }
}

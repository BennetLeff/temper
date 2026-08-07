//! Wave-4 Phase 3: the `router_v6/layer_assignment` kernel in Rust.
//!
//! Mirrors `assign_layers(netlist, constraints=None, component_positions=None)`
//! from the pinned oracle
//! `packages/temper-placer/tests/router_v6/_layer_assignment_py_oracle.py` --
//! a verbatim extraction of `router_v6/layer_assignment.py` at
//! `550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5` (`origin/main`, 2026-08-06).
//!
//! Scope (see the oracle module docstring for the full grep evidence)
//! --------------------------------------------------------------------
//! `assign_layers` has exactly one production caller
//! (`router_v6/verifier.py`), and it is always called as `assign_layers(netlist)`
//! -- no `constraints` override, no `component_positions`. No test in the
//! repository exercises either optional argument on THIS `assign_layers`
//! either. Under that one reachable configuration the function collapses to:
//! walk `DEFAULT_LAYER_CONSTRAINTS` in order and take the first
//! `re.fullmatch`. That is what this module ports. `_get_net_dominant_direction`
//! and the geometric-fallback branches inside `assign_layers` stay Python --
//! porting unreachable code would build a second implementation with no
//! caller and no test to pin its behaviour against.
//!
//! `matches_pattern` is `bool(re.fullmatch(pattern, net_name))`. Every
//! `DEFAULT_LAYER_CONSTRAINTS` pattern is ASCII with no groups, no
//! backreferences, no flags -- literal alternatives glued to a trailing
//! `.*`, plus the terminal `r".*"` catch-all -- so the `regex` crate
//! reproduces it exactly, anchored with `\A...\z` (NOT `^...$`: Rust's `$`
//! without the multi-line flag already means true end-of-haystack, but `\A`/
//! `\z` make that independent of flag state rather than relying on it, and
//! match CPython's `fullmatch` implementation -- `\A(?:pattern)\Z` with
//! Python's `\Z` documented as "matches only at the end of the string", the
//! same true-end semantics as Rust's `\z`, not Perl's "or before a trailing
//! newline" `\Z`).
//!
//! The non-obvious edge case (why the "no constraint matched" branch is
//! real, not dead)
//! ------------------------------------------------------------------------
//! Python's `.` does not match `\n` (no `re.DOTALL`). A net name with an
//! embedded newline can therefore defeat every pattern INCLUDING the `r".*"`
//! catch-all -- `.*` must consume the entire string to fullmatch, and `.`
//! cannot consume a `\n`. When that happens the oracle's `matched_constraint`
//! stays `None` after the loop, and `assign_layers` falls back to a
//! DIFFERENT, hand-built constraint: `allowed_layers={L1_TOP, L4_BOT}` (two
//! layers, not four) and `reason="No matching constraint, using default"`
//! (not the catch-all's "Default signal routing prefers bottom layer").
//! `assign_one` reproduces this by falling through the loop rather than
//! assuming the catch-all always matches.
//!
//! `vias_required` is `len(allowed_layers) > 1` (then forced `False` if
//! `len == 1`) in the oracle. Every `DEFAULT_LAYER_CONSTRAINTS` entry lists
//! all four layers and the newline-fallback lists two, so `vias_required` is
//! always `True` on every path this kernel can reach -- computed from the
//! allowed-layers list here, not hardcoded, so a future edit to either list
//! is caught by the differential rather than silently miscompiled.
//!
//! Determinism: the oracle builds a `dict` keyed by `net.name` in
//! `netlist.nets` iteration order. This kernel takes and returns a plain
//! `Vec` in the caller-supplied order -- no sorting, no `HashMap` iteration
//! reaching the boundary -- so the Python wiring layer can rebuild that same
//! dict with `dict(zip(net_names, rows))`, which has identical last-write-
//! wins-but-first-position semantics to the oracle's repeated `dict[key] =`
//! assignment.

use std::sync::OnceLock;

use pyo3::prelude::*;
use regex::Regex;

/// One `DEFAULT_LAYER_CONSTRAINTS` entry. `allowed_layers` is not stored here
/// -- every entry's is the same four-layer set, asserted by
/// [`tests::every_default_constraint_allows_all_four_layers`] rather than
/// hand-copied seven times.
struct ConstraintDef {
    pattern: &'static str,
    preferred_layer: i64,
    reason: &'static str,
}

/// Verbatim copy of `DEFAULT_LAYER_CONSTRAINTS`'s pattern/preferred_layer/
/// reason fields, in source order -- "first match wins" IS this order.
const DEFAULT_LAYER_CONSTRAINTS: [ConstraintDef; 7] = [
    ConstraintDef {
        pattern: r"DC_BUS_.*|HV_.*|SW_NODE|AC_L|AC_N|RECT_.*",
        preferred_layer: 1,
        reason: "High-voltage power distribution prefers Top layer (2oz copper)",
    },
    ConstraintDef {
        pattern: r"GATE_.*|DRV_.*|DRIVER_.*",
        preferred_layer: 1,
        reason: "Gate drive signals prefer L1 for tight coupling to L2 ground",
    },
    ConstraintDef {
        pattern: r"SENSE_.*|ADC_.*|TEMP_.*|ANALOG_.*|I_SENSE",
        preferred_layer: 1,
        reason: "Analog signals prefer Top layer, vias allowed for routing flexibility",
    },
    ConstraintDef {
        pattern: r"SPI_.*",
        preferred_layer: 4,
        // "visas" is the oracle's typo, kept verbatim -- the reason string is
        // part of the pinned contract.
        reason: "SPI prefers Bottom layer, visas allowed for pad access",
    },
    ConstraintDef {
        pattern: r"USB_.*|PWM_.*|DIGITAL_.*",
        preferred_layer: 4,
        reason: "General digital signals prefer bottom layer",
    },
    ConstraintDef {
        pattern: r"GND|PGND|CGND|ISOGND|AGND|DGND|.*_GND",
        preferred_layer: 4,
        reason: "Ground connections prefer bottom layer",
    },
    ConstraintDef {
        pattern: r".*",
        preferred_layer: 4,
        reason: "Default signal routing prefers bottom layer",
    },
];

/// The four `DEFAULT_LAYER_CONSTRAINTS` allowed layers, shared by every entry.
const ALL_FOUR_LAYERS: [i64; 4] = [1, 2, 3, 4];

/// The oracle's newline-fallback `allowed_layers` -- `{L1_TOP, L4_BOT}`, NOT
/// the four-layer set. See the module docstring's edge-case note.
const FALLBACK_LAYERS: [i64; 2] = [1, 4];

fn compiled() -> &'static [Regex; 7] {
    static CELL: OnceLock<[Regex; 7]> = OnceLock::new();
    CELL.get_or_init(|| {
        DEFAULT_LAYER_CONSTRAINTS.map(|c| match Regex::new(&format!("\\A(?:{})\\z", c.pattern)) {
            Ok(r) => r,
            // Every pattern is a `'static` literal copied from the pinned
            // oracle; a compile failure here is a programming error in this
            // file, not a runtime condition, and is caught immediately by
            // `tests::all_seven_patterns_compile`.
            Err(e) => unreachable!("DEFAULT_LAYER_CONSTRAINTS pattern {:?}: {e}", c.pattern),
        })
    })
}

/// `matches_pattern(net_name, DEFAULT_LAYER_CONSTRAINTS[idx].net_pattern)`.
fn matches_pattern(net_name: &str, idx: usize) -> bool {
    compiled()[idx].is_match(net_name)
}

/// One `LayerAssignment`'s fields, minus `net` (the caller already has the
/// name it looked this up with).
struct Assignment {
    primary_layer: i64,
    allowed_layers: Vec<i64>,
    vias_required: bool,
    reason: String,
}

/// The constraint-matching body of `assign_layers` under
/// `constraints=None, component_positions=None` -- first `fullmatch` in
/// `DEFAULT_LAYER_CONSTRAINTS` order wins; if none matches (only reachable
/// via an embedded `\n`), the oracle's untaken-catch-all fallback fires.
fn assign_one(net_name: &str) -> Assignment {
    for (idx, c) in DEFAULT_LAYER_CONSTRAINTS.iter().enumerate() {
        if matches_pattern(net_name, idx) {
            let allowed_layers = ALL_FOUR_LAYERS.to_vec();
            let vias_required = allowed_layers.len() > 1;
            return Assignment {
                primary_layer: c.preferred_layer,
                allowed_layers,
                vias_required,
                reason: c.reason.to_string(),
            };
        }
    }
    let allowed_layers = FALLBACK_LAYERS.to_vec();
    let vias_required = allowed_layers.len() > 1;
    Assignment {
        primary_layer: 4, // Layer.L4_BOT: geometric_preferred_layer is always
        // None here (component_positions is never passed on the reachable
        // path), so the oracle's `preferred = ... if ... else Layer.L4_BOT`
        // always takes the else branch.
        allowed_layers,
        vias_required,
        reason: "No matching constraint, using default".to_string(),
    }
}

/// `(primary_layer, allowed_layers, vias_required, reason)`, matching
/// `LayerAssignment`'s field order minus `net`.
type AssignRow = (i64, Vec<i64>, bool, String);

/// `{n.name: assign_layers(netlist)[n.name] for n in netlist.nets}`,
/// restricted to `constraints=None, component_positions=None` -- returned as
/// a `Vec` in input order; see the module docstring for why the caller's
/// `dict(zip(net_names, rows))` reproduces the oracle's dict exactly.
#[pyfunction]
pub fn assign_layers_py(net_names: Vec<String>) -> Vec<AssignRow> {
    net_names
        .iter()
        .map(|n| {
            let a = assign_one(n);
            (a.primary_layer, a.allowed_layers, a.vias_required, a.reason)
        })
        .collect()
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(assign_layers_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_seven_patterns_compile() {
        assert_eq!(compiled().len(), 7);
    }

    #[test]
    fn every_default_constraint_allows_all_four_layers() {
        // Not asserting a hardcoded True for vias_required elsewhere in this
        // file -- this is the fact that makes it always true on the matched
        // path, checked once here rather than assumed.
        for name in ["DC_BUS_P", "GATE_H", "SENSE_1", "SPI_CLK", "USB_DP", "GND", "RANDOM"] {
            let a = assign_one(name);
            assert_eq!(a.allowed_layers, ALL_FOUR_LAYERS.to_vec(), "{name}");
            assert!(a.vias_required, "{name}");
        }
    }

    #[test]
    fn first_match_wins_order_is_source_order() {
        // "GATE_GND" matches both constraint 1 (GATE_.*) and constraint 5
        // (.*_GND) -- constraint 1 must win because it is earlier in
        // DEFAULT_LAYER_CONSTRAINTS.
        let a = assign_one("GATE_GND");
        assert_eq!(a.primary_layer, 1, "GATE_.* (index 1) must win over .*_GND (index 5)");
        assert_eq!(a.reason, "Gate drive signals prefer L1 for tight coupling to L2 ground");
    }

    #[test]
    fn exact_literal_alternatives_do_not_prefix_match() {
        // "SW_NODE" is an exact alternative, not SW_NODE.* -- "SW_NODE2"
        // must NOT match constraint 0 and instead falls through to the
        // catch-all.
        assert!(matches_pattern("SW_NODE", 0));
        assert!(!matches_pattern("SW_NODE2", 0));
        let a = assign_one("SW_NODE2");
        assert_eq!(a.reason, "Default signal routing prefers bottom layer");
    }

    #[test]
    fn embedded_newline_defeats_even_the_catch_all() {
        // Python's `.` does not match `\n`; `.*` must consume the WHOLE
        // string to fullmatch, so a net name with an embedded newline
        // defeats every DEFAULT_LAYER_CONSTRAINTS pattern including the
        // r".*" catch-all, and the oracle's `matched_constraint is None`
        // fallback fires: a DIFFERENT two-layer allowed set and reason.
        let name = "WEIRD\nNET";
        for idx in 0..7 {
            assert!(!matches_pattern(name, idx), "pattern {idx} must not match {name:?}");
        }
        let a = assign_one(name);
        assert_eq!(a.allowed_layers, FALLBACK_LAYERS.to_vec());
        assert_eq!(a.reason, "No matching constraint, using default");
        assert_eq!(a.primary_layer, 4);
    }

    #[test]
    fn ordinary_names_are_unaffected_by_the_newline_case() {
        // A plain name (the overwhelming common case) still hits the
        // catch-all with the FOUR-layer set, not the newline fallback.
        let a = assign_one("MYSTERY_NET");
        assert_eq!(a.allowed_layers, ALL_FOUR_LAYERS.to_vec());
        assert_eq!(a.reason, "Default signal routing prefers bottom layer");
    }

    #[test]
    fn ground_suffix_pattern_is_a_true_suffix_not_a_substring_match() {
        assert!(matches_pattern("PGND", 5));
        assert!(matches_pattern("SENSOR_GND", 5)); // .*_GND
        assert!(!matches_pattern("GNDX", 5)); // suffix, not substring
    }

    #[test]
    fn assign_layers_py_preserves_input_order_and_duplicates() {
        let rows = assign_layers_py(vec!["GND".to_string(), "SPI_CLK".to_string(), "GND".to_string()]);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0].0, 4); // GND -> L4_BOT
        assert_eq!(rows[1].0, 4); // SPI_CLK -> L4_BOT
        assert_eq!(rows[2].0, 4); // GND again -> same answer, order preserved
    }
}

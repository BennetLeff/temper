/// Net-name classification — maps net names to NetClass variants.
///
/// Uses the canonical pattern-matching rules from
/// `router_v6/net_classification.py` with precedence order:
/// Ground > Power > HighVoltage > Differential > HighCurrent > GateDrive > Signal.
use crate::types::{NetClass, NetClassification, Netlist};

const GROUND_PATTERNS: &[&str] = &["GND", "PGND", "CGND", "AGND", "DGND", "VSS"];
const POWER_PATTERNS: &[&str] = &["+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"];

/// Exact HV-domain net names from `elec/domain_manifest.yaml`'s `HV` domain
/// -- this project's hand-reviewed, netlist-traced SSOT for which
/// conductors are mains/HV.
///
/// FIXED (net-current/classification reconciliation): `HV_PATTERNS` used to
/// be `["AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"]`. Only
/// `SW_NODE` is a net on this board. The board spells its mains nets
/// `ac_l`/`ac_n` and its bus nets `+170V_BUS`/`DC_BUS_RTN`; `PE`,
/// `DC_BUS+` and `DC_BUS-` name no conductor at all. Measured consequence:
/// `+170V_BUS` (the live 170V DC bus), `DC_BUS_RTN`, `PWR_RTN` (the
/// doubler midpoint), `tank-out`, `tank.c_tank1-p2` (the resonant tank,
/// 570 Vrms), `w1_1`/`w1_2` (the CMC line windings) and `hb-gnd` all
/// classified as `NetClass::Signal` -- the fallback at the bottom of the
/// precedence chain -- on a mains-powered board.
///
/// Matched EXACTLY (case-insensitively), not by substring: `PE` as a plain
/// `contains` test is precisely the unanchored shape
/// `scripts/check_net_classification.py` exists to catch, and which this
/// repo has now fixed five separate times in other files
/// (docs/evidence/2026-07-27-net-classification-gate.md).
const HV_EXACT_NETS: &[&str] = &[
    "ac_l",
    "ac_n",
    "+170V_BUS",
    "DC_BUS_RTN",
    "PWR_RTN",
    "w1_1",
    "w1_2",
    "+15V_LS",
    "SW_NODE",
    "GATE_HS",
    "GATE_LS",
    "tank-out",
    "tank.c_tank1-p2",
    "power_in.ntc-no",
    "hb-gnd",
    "hb.power_loop.q_high-g",
    "hb.gate_hs.driver-p1-1",
    "hb.gate_hs.driver-p2",
    "input",
    "discharge.k_dis1-nc",
    "discharge.k_dis2-nc",
    "discharge.k_dis1-no",
    "discharge.k_dis2-no",
    "discharge.r_dis1a-p2",
    "discharge.r_dis2a-p2",
    "discharge.r_snub1-p2",
    "discharge.r_snub2-p2",
];

/// Legacy HV name fragments, kept for net names this crate may see from
/// boards OTHER than `pcb/temper.kicad_pcb` (fixtures, the DFM corpus).
/// `PE` is deliberately NOT carried over: as a bare substring it matched
/// any name containing those two letters.
const HV_PATTERNS: &[&str] = &["AC_L", "AC_N", "DC_BUS+", "DC_BUS-", "SW_NODE"];
const DIFFERENTIAL_PATTERNS: &[&str] = &["DIFF", "USB_D", "LVDS", "ETH_"];
const HIGH_CURRENT_PATTERNS: &[&str] = &["HC_", "HIGH_CURRENT", "PWR_RAIL", "BUS_BAR"];
const GATE_DRIVE_PATTERNS: &[&str] = &["GATE", "DRV", "DRIVE"];

fn matches_any(upper: &str, patterns: &[&str]) -> bool {
    patterns.iter().any(|p| upper.contains(*p))
}

// `pub(crate)`, not private: the wasm32-tier deterministic campaign in
// `property_campaigns.rs` mirrors this file's `proptests` module (which
// reaches it via `use super::*` from inside this same file) and needs to
// call it from a sibling module.
pub(crate) fn classify_net_name(name: &str) -> NetClass {
    // Uppercase once per net name, not once per pattern group below.
    let upper = name.to_uppercase();
    // The manifest's exact HV net list wins over every keyword rule below.
    // Checked FIRST, above Ground, because several real HV-domain nets are
    // spelled in ways the keyword rules misread: `hb-gnd` contains "GND"
    // (it is the half-bridge low-side RETURN, ~-170V to signal ground, not
    // a ground net), and `+15V_LS` contains "+15V".
    if HV_EXACT_NETS.iter().any(|n| n.eq_ignore_ascii_case(name)) {
        return NetClass::HighVoltage;
    }
    if matches_any(&upper, GROUND_PATTERNS) {
        NetClass::Ground
    } else if matches_any(&upper, POWER_PATTERNS) {
        NetClass::Power
    } else if matches_any(&upper, HV_PATTERNS) {
        NetClass::HighVoltage
    } else if matches_any(&upper, DIFFERENTIAL_PATTERNS) {
        NetClass::Differential
    } else if matches_any(&upper, HIGH_CURRENT_PATTERNS) {
        NetClass::HighCurrent
    } else if matches_any(&upper, GATE_DRIVE_PATTERNS) {
        NetClass::GateDrive
    } else {
        NetClass::Signal
    }
}

pub fn classify_nets(netlist: &Netlist) -> Vec<NetClassification> {
    netlist
        .nets
        .iter()
        .map(|net| NetClassification {
            net_name: net.name.clone(),
            class: classify_net_name(&net.name),
        })
        .collect()
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::types::NetInfo;

    #[cfg_attr(test, test)]
    fn test_ground_nets() {
        assert_eq!(classify_net_name("GND"), NetClass::Ground);
        assert_eq!(classify_net_name("PGND"), NetClass::Ground);
        assert_eq!(classify_net_name("AGND"), NetClass::Ground);
        assert_eq!(classify_net_name("VSS"), NetClass::Ground);
    }

    #[cfg_attr(test, test)]
    fn test_power_nets() {
        assert_eq!(classify_net_name("+12V"), NetClass::Power);
        assert_eq!(classify_net_name("VCC"), NetClass::Power);
        assert_eq!(classify_net_name("VDD"), NetClass::Power);
    }

    #[cfg_attr(test, test)]
    fn test_hv_nets() {
        assert_eq!(classify_net_name("AC_L"), NetClass::HighVoltage);
        assert_eq!(classify_net_name("DC_BUS+"), NetClass::HighVoltage);
        assert_eq!(classify_net_name("SW_NODE"), NetClass::HighVoltage);
    }

    #[cfg_attr(test, test)]
    fn test_gate_drive_nets() {
        assert_eq!(classify_net_name("GATE_H"), NetClass::GateDrive);
        assert_eq!(classify_net_name("DRV_LO"), NetClass::GateDrive);
        assert_eq!(classify_net_name("DRIVE_A"), NetClass::GateDrive);
    }

    /// REGRESSION GUARD. Every one of these is a REAL net on
    /// `pcb/temper.kicad_pcb` that classified as `NetClass::Signal` before
    /// the HV list was keyed on the domain manifest instead of a ghost
    /// vocabulary -- on a mains-powered board.
    #[cfg_attr(test, test)]
    fn test_real_board_hv_nets_are_not_signal() {
        for net in [
            "+170V_BUS",
            "DC_BUS_RTN",
            "PWR_RTN",
            "tank-out",
            "tank.c_tank1-p2",
            "w1_1",
            "w1_2",
            "hb-gnd",
            "power_in.ntc-no",
            "ac_l",
            "ac_n",
        ] {
            assert_eq!(
                classify_net_name(net),
                NetClass::HighVoltage,
                "real HV-domain board net {net} must not classify as Signal"
            );
        }
    }

    /// `hb-gnd` contains "GND" and `+15V_LS` contains "+15V", so the
    /// keyword rules would claim them for Ground/Power. The manifest's
    /// exact list is checked first precisely so it wins.
    #[cfg_attr(test, test)]
    fn test_hv_exact_list_beats_misleading_keywords() {
        assert_eq!(classify_net_name("hb-gnd"), NetClass::HighVoltage);
        assert_eq!(classify_net_name("+15V_LS"), NetClass::HighVoltage);
        // A genuine ground net is still Ground.
        assert_eq!(classify_net_name("gnd"), NetClass::Ground);
    }

    /// "PE" was a plain-substring HV pattern -- the unanchored shape
    /// scripts/check_net_classification.py exists to catch. It is gone.
    #[cfg_attr(test, test)]
    fn test_bare_pe_substring_no_longer_forces_high_voltage() {
        assert_ne!(classify_net_name("SPEED_SENSE"), NetClass::HighVoltage);
        assert_ne!(classify_net_name("TYPE_SEL"), NetClass::HighVoltage);
    }

    #[cfg_attr(test, test)]
    fn test_signal_fallback() {
        assert_eq!(classify_net_name("SENSOR_1"), NetClass::Signal);
        assert_eq!(classify_net_name("LED_RED"), NetClass::Signal);
        assert_eq!(classify_net_name("UNKNOWN_NET_XYZ"), NetClass::Signal);
    }

    #[cfg_attr(test, test)]
    fn test_precedence_ground_over_power() {
        assert_eq!(classify_net_name("GND_PWR"), NetClass::Ground);
    }

    #[cfg_attr(test, test)]
    fn test_precedence_hv_over_gate_drive() {
        assert_eq!(classify_net_name("AC_L_GATE"), NetClass::HighVoltage);
    }

    #[cfg_attr(test, test)]
    fn test_deterministic() {
        for _ in 0..10 {
            assert_eq!(classify_net_name("GND"), NetClass::Ground);
            assert_eq!(classify_net_name("VCC"), NetClass::Power);
            assert_eq!(classify_net_name("SW_NODE"), NetClass::HighVoltage);
            assert_eq!(classify_net_name("GATE_H"), NetClass::GateDrive);
            assert_eq!(classify_net_name("SIG1"), NetClass::Signal);
        }
    }

    #[cfg_attr(test, test)]
    fn test_classify_nets_from_netlist() {
        let netlist = Netlist {
            nets: vec![
                NetInfo { name: "GND".into(), pins: vec![] },
                NetInfo { name: "+5V".into(), pins: vec![] },
                NetInfo { name: "SIG1".into(), pins: vec![] },
            ],
            components: vec![],
        };
        let classes = classify_nets(&netlist);
        assert_eq!(classes.len(), 3);
        assert_eq!(classes[0].class, NetClass::Ground);
        assert_eq!(classes[1].class, NetClass::Power);
        assert_eq!(classes[2].class, NetClass::Signal);
    }

    // --- proptest: classification structural properties ---

    // Carries its own `#[cfg(test)]`, redundant under `cargo test` (the parent
    // `tests` module already has one) but load-bearing for the wasm32 tier: it
    // makes `scripts/gen_wasm_test_registry.py` census this module separately,
    // so the `proptest` dev-dependency -- absent from the non-test build the
    // registry compiles into -- excludes only these properties and not the
    // parent module's plain `#[test]`s.  Same shape as `temper-thermal`'s.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        use super::*;
        use proptest::prelude::*;

        proptest! {
            // --------------------------------------------------------------
            // Property C1: classify_net_name always returns a valid NetClass
            // for any string input (the function never panics).
            // --------------------------------------------------------------
            #[test]
            fn prop_classify_net_name_never_panics(name in ".*") {
                let class = classify_net_name(&name);
                // The returned class should be one of the 7 variants.
                // This implicitly validates that the function doesn't panic.
                let _ = class.as_str(); // would panic if not a valid variant
            }

            // --------------------------------------------------------------
            // Property C2: classify_nets preserves input length.
            // --------------------------------------------------------------
            #[test]
            fn prop_classify_nets_preserves_length(
                names in proptest::collection::vec(".*", 0..=20),
            ) {
                let netlist = Netlist {
                    nets: names.iter().map(|n| NetInfo {
                        name: n.clone(),
                        pins: vec![],
                    }).collect(),
                    components: vec![],
                };
                let classes = classify_nets(&netlist);
                prop_assert_eq!(classes.len(), names.len());
            }

            // --------------------------------------------------------------
            // Property C3: classify_nets preserves net names.
            // --------------------------------------------------------------
            #[test]
            fn prop_classify_nets_preserves_names(
                names in proptest::collection::vec(".*", 0..=10),
            ) {
                let netlist = Netlist {
                    nets: names.iter().map(|n| NetInfo {
                        name: n.clone(),
                        pins: vec![],
                    }).collect(),
                    components: vec![],
                };
                let classes = classify_nets(&netlist);
                for (i, c) in classes.iter().enumerate() {
                    prop_assert_eq!(&c.net_name, &names[i]);
                }
            }

            // --------------------------------------------------------------
            // Property C4: Deterministic — same input gives same output.
            // --------------------------------------------------------------
            #[test]
            fn prop_classify_deterministic(
                names in proptest::collection::vec(".*", 0..=10),
            ) {
                let netlist = Netlist {
                    nets: names.iter().map(|n| NetInfo {
                        name: n.clone(),
                        pins: vec![],
                    }).collect(),
                    components: vec![],
                };
                let a = classify_nets(&netlist);
                let b = classify_nets(&netlist);
                prop_assert_eq!(a.len(), b.len());
                for (ac, bc) in a.iter().zip(b.iter()) {
                    prop_assert_eq!(ac.class, bc.class);
                    prop_assert_eq!(&ac.net_name, &bc.net_name);
                }
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("classification::tests::test_ground_nets", test_ground_nets),
        ("classification::tests::test_power_nets", test_power_nets),
        ("classification::tests::test_hv_nets", test_hv_nets),
        ("classification::tests::test_gate_drive_nets", test_gate_drive_nets),
        ("classification::tests::test_signal_fallback", test_signal_fallback),
        ("classification::tests::test_precedence_ground_over_power", test_precedence_ground_over_power),
        ("classification::tests::test_precedence_hv_over_gate_drive", test_precedence_hv_over_gate_drive),
        ("classification::tests::test_deterministic", test_deterministic),
        ("classification::tests::test_classify_nets_from_netlist", test_classify_nets_from_netlist),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

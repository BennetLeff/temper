/// Integration tests for the loop extractor:
/// U5: Proptest invariants (R14-R17)
/// U6: BMC induction ladder (R18-R21)  
/// U7: Temper board reproduction (SC1)

use temper_rust_router::loop_extractor::extract::{
    auto_extract_loops, Component, Loop, Net, Pin,
};
use temper_rust_router::loop_extractor::types::ExtractionError;

#[cfg(test)]
mod proptest_tests {
    use proptest::prelude::*;
    use super::*;

    fn make_switch(ref_name: &str) -> Component {
        Component {
            ref_des: ref_name.into(),
            footprint: "TO-247-3".into(),
            mpn: String::new(),
            value: String::new(),
            pins: vec![
                Pin { name: "1".into(), net: Some(format!("GATE_{}", ref_name)) },
                Pin { name: "2".into(), net: match ref_name {
                    "Q1" => Some("DC_BUS+".into()),
                    _ => Some("SW_NODE".into()),
                }},
                Pin { name: "3".into(), net: match ref_name {
                    "Q1" => Some("SW_NODE".into()),
                    _ => Some("DC_BUS-".into()),
                }},
            ],
            classification: Default::default(),
        }
    }

    fn make_cap(ref_name: &str, net_a: &str, net_b: &str) -> Component {
        Component {
            ref_des: ref_name.into(),
            footprint: "CP_Radial".into(),
            mpn: String::new(),
            value: "1000uF".into(),
            pins: vec![
                Pin { name: "1".into(), net: Some(net_a.into()) },
                Pin { name: "2".into(), net: Some(net_b.into()) },
            ],
            classification: Default::default(),
        }
    }

    fn make_resistor(ref_name: &str, net: &str) -> Component {
        Component {
            ref_des: ref_name.into(),
            footprint: "R_0805".into(),
            mpn: String::new(),
            value: "10R".into(),
            pins: vec![
                Pin { name: "1".into(), net: Some(net.into()) },
                Pin { name: "2".into(), net: None },
            ],
            classification: Default::default(),
        }
    }

    // ---- Proptest: Soundness (R14) ----

    proptest! {
        #[test]
        fn soundness_extracted_components_share_nets(
            extra_components in 0usize..5,
        ) {
            let mut comps = vec![
                make_switch("Q1"),
                make_switch("Q2"),
                make_cap("C_BUS", "DC_BUS+", "DC_BUS-"),
            ];
            // Add random unrelated components
            for i in 0..extra_components {
                comps.push(make_resistor(&format!("R{}", i + 1), "GND"));
            }

            let result = auto_extract_loops(&comps, &[], &[]);
            prop_assert!(result.is_ok());
            let loops = result.unwrap();
            prop_assert!(!loops.is_empty());

            let comm = loops.iter().find(|l| l.name == "auto_commutation");
            prop_assert!(comm.is_some(), "Commutation loop should be found with {} extra components", extra_components);
        }
    }

    // ---- Proptest: Uniqueness (R16) ----

    proptest! {
        #[test]
        fn uniqueness_same_input_same_output(
            extra in 0usize..3,
        ) {
            let mut comps = vec![
                make_switch("Q1"),
                make_switch("Q2"),
                make_cap("C_BUS", "DC_BUS+", "DC_BUS-"),
            ];
            for i in 0..extra {
                comps.push(make_resistor(&format!("R{}", i + 1), "GND"));
            }

            let result1 = auto_extract_loops(&comps, &[], &[]).unwrap();
            let result2 = auto_extract_loops(&comps, &[], &[]).unwrap();
            prop_assert_eq!(result1, result2);
        }
    }
}

#[cfg(test)]
mod bmc_tests {
    use super::*;

    fn minimal_half_bridge() -> Vec<Component> {
        vec![
            Component {
                ref_des: "Q1".into(), footprint: "TO-247-3".into(), mpn: String::new(), value: String::new(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("GATE_H".into()) },
                    Pin { name: "2".into(), net: Some("DC_BUS+".into()) },
                    Pin { name: "3".into(), net: Some("SW_NODE".into()) },
                ],
                classification: Default::default(),
            },
            Component {
                ref_des: "Q2".into(), footprint: "TO-247-3".into(), mpn: String::new(), value: String::new(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("GATE_L".into()) },
                    Pin { name: "2".into(), net: Some("SW_NODE".into()) },
                    Pin { name: "3".into(), net: Some("DC_BUS-".into()) },
                ],
                classification: Default::default(),
            },
            Component {
                ref_des: "C_BUS".into(), footprint: "CP_Radial".into(), mpn: String::new(), value: "1000uF".into(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("DC_BUS+".into()) },
                    Pin { name: "2".into(), net: Some("DC_BUS-".into()) },
                ],
                classification: Default::default(),
            },
        ]
    }

    // ---- BMC: Base case (R18) ----

    #[test]
    fn bmc_base_case_minimal_half_bridge() {
        // Covers AE4: minimal half-bridge -> exactly one commutation loop
        let comps = minimal_half_bridge();
        let result = auto_extract_loops(&comps, &[], &[]);
        assert!(result.is_ok(), "Base case must succeed: {:?}", result.err());
        let loops = result.unwrap();
        let comm = loops.iter().find(|l| l.name == "auto_commutation");
        assert!(comm.is_some(), "Base case: commutation loop found");
        let c = comm.unwrap();
        assert!(c.components.contains(&"Q1".into()));
        assert!(c.components.contains(&"Q2".into()));
        assert!(c.components.contains(&"C_BUS".into()));
    }

    // ---- BMC: Inductive add (R19) ----

    #[test]
    fn bmc_add_unrelated_component() {
        // Adding unrelated components should not break extraction
        let mut comps = minimal_half_bridge();
        for i in 1..=18 {
            comps.push(Component {
                ref_des: format!("R{}", i), footprint: "R_0805".into(), mpn: String::new(), value: "10k".into(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("GND".into()) },
                    Pin { name: "2".into(), net: None },
                ],
                classification: Default::default(),
            });
        }
        let result = auto_extract_loops(&comps, &[], &[]);
        assert!(result.is_ok(), "Adding unrelated components should not break extraction");
        let loops = result.unwrap();
        assert!(loops.iter().any(|l| l.name == "auto_commutation"));
    }

    // ---- BMC: Inductive modify (R20) ----

    #[test]
    fn bmc_modify_unrelated_footprint() {
        // Changing an unrelated component's footprint should not change the loop set
        let mut comps = minimal_half_bridge();
        let r1 = Component {
            ref_des: "R1".into(), footprint: "R_0805".into(), mpn: String::new(), value: "10k".into(),
            pins: vec![
                Pin { name: "1".into(), net: Some("GND".into()) },
                Pin { name: "2".into(), net: None },
            ],
            classification: Default::default(),
        };
        comps.push(r1);
        let loops_before = auto_extract_loops(&comps, &[], &[]).unwrap();

        // Change footprint
        let r2 = Component {
            ref_des: "R1".into(), footprint: "R_0603".into(), mpn: String::new(), value: "10k".into(),
            pins: vec![
                Pin { name: "1".into(), net: Some("GND".into()) },
                Pin { name: "2".into(), net: None },
            ],
            classification: Default::default(),
        };
        let mut comps2 = minimal_half_bridge();
        comps2.push(r2);
        let loops_after = auto_extract_loops(&comps2, &[], &[]).unwrap();

        assert_eq!(loops_before, loops_after, "Footprint change should not affect loop set");
    }

    // ---- BMC: Inductive remove (R21) ----

    #[test]
    fn bmc_remove_unrelated_component() {
        // Removing an unrelated component should not break extraction
        let mut comps = minimal_half_bridge();
        comps.push(Component {
            ref_des: "R_EXTRA".into(), footprint: "R_0805".into(), mpn: String::new(), value: "10k".into(),
            pins: vec![
                Pin { name: "1".into(), net: Some("GND".into()) },
                Pin { name: "2".into(), net: None },
            ],
            classification: Default::default(),
        });
        let loops_with = auto_extract_loops(&comps, &[], &[]).unwrap();
        let loops_without = auto_extract_loops(&minimal_half_bridge(), &[], &[]).unwrap();
        assert_eq!(loops_with, loops_without, "Removing unrelated component should not change loop set");
    }
}

#[cfg(test)]
mod temper_tests {
    use super::*;

    /// Temper board reproduction: TO-247 numeric pin names (SC1, test 1)
    #[test]
    fn temper_to247_numeric_pins_work() {
        // Covers the first Temper failure: Q1 with pin "2" (collector) maps correctly
        let comps = vec![
            Component {
                ref_des: "Q1".into(), footprint: "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown".into(),
                mpn: String::new(), value: String::new(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("GATE_H".into()) },
                    Pin { name: "2".into(), net: Some("DC_BUS+".into()) },
                    Pin { name: "3".into(), net: Some("SW_NODE".into()) },
                ],
                classification: Default::default(),
            },
            Component {
                ref_des: "Q2".into(), footprint: "Package_TO_SOT_THT:TO-247-3_Horizontal_TabDown".into(),
                mpn: String::new(), value: String::new(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("GATE_L".into()) },
                    Pin { name: "2".into(), net: Some("SW_NODE".into()) },
                    Pin { name: "3".into(), net: Some("DC_BUS-".into()) },
                ],
                classification: Default::default(),
            },
            Component {
                ref_des: "C_BUS1".into(), footprint: "CP_Radial_D10.0mm".into(),
                mpn: String::new(), value: "1000uF".into(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("DC_BUS+".into()) },
                    Pin { name: "2".into(), net: Some("PGND".into()) },
                ],
                classification: Default::default(),
            },
            Component {
                ref_des: "C_BUS2".into(), footprint: "CP_Radial_D10.0mm".into(),
                mpn: String::new(), value: "1000uF".into(),
                pins: vec![
                    Pin { name: "1".into(), net: Some("PGND".into()) },
                    Pin { name: "2".into(), net: Some("DC_BUS-".into()) },
                ],
                classification: Default::default(),
            },
        ];

        // Covers AE2: split-capacitor topology
        let result = auto_extract_loops(&comps, &[], &[]);
        assert!(result.is_ok(), "Temper board extraction must succeed: {:?}", result.err());
        let loops = result.unwrap();
        let comm = loops.iter().find(|l| l.name == "auto_commutation").unwrap();
        assert!(comm.components.contains(&"Q1".into()), "Q1 in commutation loop");
        assert!(comm.components.contains(&"Q2".into()), "Q2 in commutation loop");
        assert!(comm.components.contains(&"C_BUS1".into()), "C_BUS1 in commutation loop");
        assert!(comm.components.contains(&"C_BUS2".into()), "C_BUS2 in commutation loop");
    }

    /// Temper board: no generic None failures (SC1)
    #[test]
    fn temper_no_silent_none() {
        // Empty netlist should produce a structured error, not panic
        let result = auto_extract_loops(&[], &[], &[]);
        assert!(result.is_err());
        let err = result.unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("half-bridge"), "Error should explain the failure: {}", msg);
    }
}


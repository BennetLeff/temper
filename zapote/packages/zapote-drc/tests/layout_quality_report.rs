use zapote_drc::layout_quality::{coupling::InductiveTerm, report::*};
fn input() -> Input {
    Input {
        schema_version: 1,
        board_sha256: "a".repeat(64),
        source_revision: "fixture".into(),
        required_checks: vec![Family::GateCoupling],
        cases: vec![Case {
            id: "gate-A".into(),
            basis: "analytic fixture".into(),
            assumptions: vec!["unit-slew sensitivity; not VGS".into()],
            scenario: Scenario::GateCoupling(vec![InductiveTerm {
                object: "P1->P3".into(),
                mutual_nh: 2.0,
                slew_a_per_ns: 1.0,
            }]),
            budgets: vec![],
        }],
    }
}
#[test]
fn no_budget_is_unscored_and_missing_family_is_explicit() {
    let mut i = input();
    i.required_checks.push(Family::KelvinSense);
    let r = run(&i).unwrap();
    assert_eq!(r.cases[0].status, Status::Unscored);
    assert_eq!(r.missing_checks, vec![Family::KelvinSense]);
}
#[test]
fn invalid_case_cannot_cover_a_required_family() {
    let mut i = input();
    i.cases[0].scenario = Scenario::GateCoupling(vec![]);
    let r = run(&i).unwrap();
    assert_eq!(r.cases[0].status, Status::Invalid);
    assert_eq!(r.missing_checks, vec![Family::GateCoupling]);
}
#[test]
fn budget_typo_is_an_error_and_cannot_silently_skip_comparison() {
    let mut i = input();
    i.cases[0].budgets.push(Budget {
        metric: "wrong".into(),
        direction: Direction::Maximum,
        limit: 10.0,
    });
    assert_eq!(run(&i).unwrap().cases[0].status, Status::Invalid);
}
#[test]
fn budget_margin_boundary_and_failure_are_preserved() {
    let mut i = input();
    i.cases[0].budgets.push(Budget {
        metric: "pickup_magnitude_v".into(),
        direction: Direction::Maximum,
        limit: 2.0,
    });
    assert_eq!(run(&i).unwrap().cases[0].status, Status::WithinBudgets);
    i.cases[0].budgets[0].limit = 1.0;
    let r = run(&i).unwrap();
    assert_eq!(r.cases[0].status, Status::OutsideBudgets);
    assert_eq!(r.cases[0].metrics[0].margin, Some(-1.0));
}
#[test]
fn batch_rejects_bad_identity_unknown_schema_and_duplicate_cases() {
    let mut i = input();
    i.board_sha256 = "abcd".into();
    assert!(run(&i).is_err());
    i = input();
    i.schema_version = 2;
    assert!(run(&i).is_err());
    i = input();
    i.cases.push(i.cases[0].clone());
    assert!(run(&i).is_err());
}
#[test]
fn serde_rejects_unknown_fields_and_roundtrips_typed_input() {
    let i = input();
    let mut v = serde_json::to_value(&i).unwrap();
    v["surprise"] = true.into();
    assert!(serde_json::from_value::<Input>(v).is_err());
    let text = serde_json::to_string(&i).unwrap();
    let decoded: Input = serde_json::from_str(&text).unwrap();
    assert_eq!(run(&decoded).unwrap().cases[0].metrics[0].value, 2.0);
}

#[test]
fn all_nine_families_are_evaluated_through_the_public_batch_api() {
    use zapote_drc::layout_quality::{
        assembly, capacitance, copper, coupling, decoupling, returns, thermal,
    };
    let magnetic = vec![coupling::InductiveTerm {
        object: "P1->gate".into(),
        mutual_nh: 1.0,
        slew_a_per_ns: 1.0,
    }];
    let electric = vec![coupling::CapacitiveTerm {
        object: "SW->sense".into(),
        capacitance_pf: 1.0,
        slew_v_per_ns: 1.0,
    }];
    let shared = vec![coupling::SharedImpedance {
        object: "return".into(),
        resistance_ohm: 0.001,
        inductance_nh: 1.0,
        current_a: 1.0,
        slew_a_per_ns: 1.0,
    }];
    let scenarios = vec![
        Scenario::GateCoupling(magnetic.clone()),
        Scenario::KelvinSense(coupling::KelvinInput {
            shared: shared.clone(),
            magnetic: magnetic.clone(),
            positive_pickup: electric.clone(),
            negative_pickup: electric.clone(),
            positive_transfer_ohm: 1.0,
            negative_transfer_ohm: 1.0,
            shunt_ohm: 0.001,
        }),
        Scenario::SwitchCoupling {
            aggressors: vec![capacitance::Patch {
                object: "SW".into(),
                rect_mm: [0.0, 0.0, 1.0, 1.0],
                z_mm: 0.0,
            }],
            victims: vec![capacitance::Patch {
                object: "sense".into(),
                rect_mm: [0.0, 0.0, 1.0, 1.0],
                z_mm: 0.2,
            }],
            relative_permittivity: 4.0,
            slew_v_per_ns: 1.0,
        },
        Scenario::Decoupling {
            branches: vec![decoupling::Branch {
                object: "C38".into(),
                capacitance_f: 1e-6,
                resistance_ohm: 0.1,
                inductance_h: 1e-8,
            }],
            frequencies_hz: vec![1e6],
        },
        Scenario::ReturnPath(returns::Input {
            object: "return".into(),
            points_mm: vec![[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            shared,
        }),
        Scenario::CopperDistribution {
            nodes: 2,
            ground: 1,
            edges: vec![copper::Edge {
                object: "trace".into(),
                from: 0,
                to: 1,
                resistance_ohm: 0.01,
                area_mm2: 0.1,
            }],
            injections_a: vec![1.0, -1.0],
        },
        Scenario::EmiBypass {
            magnetic,
            electric,
            transfer_ohm: 50.0,
        },
        Scenario::ThermalInfluence(thermal::Input {
            object: "REF25".into(),
            ambient_c: 25.0,
            reference_c: 25.0,
            coefficient_ppm_per_k: 10.0,
            valid_temperature_c: [-40.0, 85.0],
            influences: vec![thermal::Influence {
                object: "Q2".into(),
                power_w: 1.0,
                transfer_k_per_w: 2.0,
            }],
        }),
        Scenario::AssemblyMargin {
            envelopes: vec![
                assembly::Envelope {
                    object: "a".into(),
                    min_mm: [0.0; 3],
                    max_mm: [1.0; 3],
                    tolerance_mm: [0.0; 3],
                    access_mm: [0.0; 3],
                },
                assembly::Envelope {
                    object: "b".into(),
                    min_mm: [2.0; 3],
                    max_mm: [3.0; 3],
                    tolerance_mm: [0.0; 3],
                    access_mm: [0.0; 3],
                },
            ],
            search_distance_mm: 5.0,
        },
    ];
    let mut i = input();
    i.required_checks = scenarios.iter().map(Scenario::family).collect();
    i.cases = scenarios
        .into_iter()
        .enumerate()
        .map(|(n, scenario)| Case {
            id: format!("analytic-{n}"),
            basis: "closed-form fixture; not a board assessment".into(),
            assumptions: vec!["explicit simplified model".into()],
            scenario,
            budgets: vec![],
        })
        .collect();
    let encoded = serde_json::to_string(&i).unwrap();
    let roundtrip: Input = serde_json::from_str(&encoded).unwrap();
    let result = run(&roundtrip).unwrap();
    assert!(result.missing_checks.is_empty());
    assert_eq!(result.cases.len(), 9);
    assert!(result
        .cases
        .iter()
        .all(|c| c.status == Status::Unscored && !c.metrics.is_empty()));
    assert!(serde_json::to_string(&result).is_ok());
}

#[test]
fn lower_bound_clearance_cannot_claim_an_upper_bound() {
    use zapote_drc::layout_quality::assembly::Envelope;
    let mut i = input();
    i.required_checks = vec![Family::AssemblyMargin];
    i.cases[0].scenario = Scenario::AssemblyMargin {
        envelopes: vec![
            Envelope {
                object: "a".into(),
                min_mm: [0.0; 3],
                max_mm: [1.0; 3],
                tolerance_mm: [0.0; 3],
                access_mm: [0.0; 3],
            },
            Envelope {
                object: "b".into(),
                min_mm: [100.0; 3],
                max_mm: [101.0; 3],
                tolerance_mm: [0.0; 3],
                access_mm: [0.0; 3],
            },
        ],
        search_distance_mm: 1.0,
    };
    i.cases[0].budgets = vec![Budget {
        metric: "minimum_gap_lower_bound_mm".into(),
        direction: Direction::Maximum,
        limit: 2.0,
    }];
    assert_eq!(run(&i).unwrap().cases[0].status, Status::Invalid);
    i.cases[0].budgets[0].direction = Direction::Minimum;
    i.cases[0].budgets[0].limit = 0.5;
    assert_eq!(run(&i).unwrap().cases[0].status, Status::WithinBudgets);
}

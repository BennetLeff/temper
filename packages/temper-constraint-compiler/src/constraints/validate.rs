//! Validation and serialization-shape compute: `ConstraintCompiler.validate()`,
//! `ConstraintBuilder.validate()`, `_find_similar`, and the `to_yaml()` dict
//! assembly (PyYAML itself stays on the Python side — see VERIFICATION.md).
//!
//! Iteration-order contract: `component_refs` and `zone_names` are passed in
//! the ORDER the Python set iterates them in the same process, so
//! `find_similar`'s first-match and the `Available zones: ...` join are
//! bit-identical to the oracle for every permutation.

use crate::constraints::{py_lower, ConstraintData};

/// One `ValidationError` — all four fields, plus the `__str__` rendering stays
/// on the Python dataclass (the shim reconstructs it).
#[derive(Debug, Clone)]
pub struct ValidationErrorData {
    pub constraint_type: String,
    pub message: String,
    pub component: Option<String>,
    pub suggestion: Option<String>,
}

/// `ConstraintCompiler._find_similar`: prefix match (case-insensitive, first
/// match wins in set-iteration order), then `_`-suffix match.
pub fn find_similar(name: &str, options: &[String]) -> Option<String> {
    if name.is_empty() || name.chars().count() < 2 {
        return None;
    }
    let prefix_len = 3.min(name.chars().count());
    let name_prefix = py_lower(&name.chars().take(prefix_len).collect::<String>());
    for opt in options {
        if opt.chars().count() < prefix_len {
            continue;
        }
        if py_lower(&opt.chars().take(prefix_len).collect::<String>()) == name_prefix {
            return Some(opt.clone());
        }
    }
    // Suffix matching (component number after the last underscore).
    if let Some(idx) = name.rfind('_') {
        let suffix = &name[idx + 1..];
        for opt in options {
            if let Some(oi) = opt.rfind('_')
                && &opt[oi + 1..] == suffix
            {
                return Some(opt.clone());
            }
        }
    }
    None
}

/// `ConstraintCompiler.validate(board, netlist)` — error order follows the
/// source: escapes, corridors (from then to), spacing (a then b), zone
/// assignments, groups.
pub fn validate_constraints(
    data: &ConstraintData,
    component_refs: &[String],
    zone_names: &[String],
) -> Vec<ValidationErrorData> {
    let mut errors = Vec::new();

    let ref_missing = |ref_: &str| !component_refs.iter().any(|r| r == ref_);

    // Escape clearances reference valid components.
    for ec in &data.escape_clearances {
        if ref_missing(&ec.component) {
            let similar = find_similar(&ec.component, component_refs);
            errors.push(ValidationErrorData {
                constraint_type: "EscapeClearance".to_string(),
                message: format!("Component '{}' not found in netlist", ec.component),
                component: Some(ec.component.clone()),
                suggestion: similar.map(|s| format!("Did you mean: {s}?")),
            });
        }
    }

    // Routing corridors.
    for corridor in &data.corridors {
        if ref_missing(&corridor.from_component) {
            let similar = find_similar(&corridor.from_component, component_refs);
            errors.push(ValidationErrorData {
                constraint_type: "RoutingCorridor".to_string(),
                message: format!("from_component '{}' not found", corridor.from_component),
                component: Some(corridor.from_component.clone()),
                suggestion: similar.map(|s| format!("Did you mean: {s}?")),
            });
        }
        if ref_missing(&corridor.to_component) {
            let similar = find_similar(&corridor.to_component, component_refs);
            errors.push(ValidationErrorData {
                constraint_type: "RoutingCorridor".to_string(),
                message: format!("to_component '{}' not found", corridor.to_component),
                component: Some(corridor.to_component.clone()),
                suggestion: similar.map(|s| format!("Did you mean: {s}?")),
            });
        }
    }

    // Component spacing rules.
    for rule in &data.spacing_rules {
        if ref_missing(&rule.a) {
            errors.push(ValidationErrorData {
                constraint_type: "ComponentSpacingRule".to_string(),
                message: format!("component_a '{}' not found", rule.a),
                component: Some(rule.a.clone()),
                suggestion: None,
            });
        }
        if ref_missing(&rule.b) {
            errors.push(ValidationErrorData {
                constraint_type: "ComponentSpacingRule".to_string(),
                message: format!("component_b '{}' not found", rule.b),
                component: Some(rule.b.clone()),
                suggestion: None,
            });
        }
    }

    // Zone assignments (dict insertion order preserved in `zone_assignments`).
    for (comp_ref, zone_name) in &data.zone_assignments {
        if ref_missing(comp_ref) {
            errors.push(ValidationErrorData {
                constraint_type: "ZoneAssignment".to_string(),
                message: format!("Component '{comp_ref}' assigned to zone but not in netlist"),
                component: Some(comp_ref.clone()),
                suggestion: None,
            });
        }
        if !zone_names.iter().any(|z| z == zone_name) {
            errors.push(ValidationErrorData {
                constraint_type: "ZoneAssignment".to_string(),
                message: format!("Zone '{zone_name}' not defined"),
                component: Some(comp_ref.clone()),
                suggestion: Some(format!("Available zones: {}", zone_names.join(", "))),
            });
        }
    }

    // Component groups.
    for group in &data.groups {
        for comp_ref in &group.components {
            if ref_missing(comp_ref) {
                errors.push(ValidationErrorData {
                    constraint_type: "ComponentGroup".to_string(),
                    message: format!(
                        "Component '{comp_ref}' in group '{}' not in netlist",
                        group.name
                    ),
                    component: Some(comp_ref.clone()),
                    suggestion: None,
                });
            }
        }
    }

    errors
}

/// `ConstraintBuilder.validate(board_w, board_h, available_components,
/// available_zones)` — error message strings, in the source's category order.
pub fn builder_validate(
    data: &ConstraintData,
    available_components: &[String],
    available_zones: Option<&[String]>,
) -> Vec<String> {
    let mut errors = Vec::new();
    let comp_missing = |ref_: &str| !available_components.iter().any(|c| c == ref_);

    // Component spacing rules.
    for rule in &data.spacing_rules {
        if comp_missing(&rule.a) {
            errors.push(format!(
                "ComponentSpacing: component '{}' not found",
                rule.a
            ));
        }
        if comp_missing(&rule.b) {
            errors.push(format!(
                "ComponentSpacing: component '{}' not found",
                rule.b
            ));
        }
    }

    // Proximity rules in groups.
    for group in &data.groups {
        for comp in &group.components {
            if comp_missing(comp) {
                errors.push(format!(
                    "ComponentGroup '{}': component '{comp}' not found",
                    group.name
                ));
            }
        }
        // `if group.zone and group.zone not in zone_set and available_zones is not None`
        if let Some(zone) = &group.zone
            && !zone.is_empty()
            && let Some(zone_set) = available_zones
            && !zone_set.iter().any(|z| z == zone)
        {
            errors.push(format!(
                "ComponentGroup '{}': zone '{zone}' not found",
                group.name
            ));
        }
    }

    // Escape clearances.
    for escape in &data.escape_clearances {
        if comp_missing(&escape.component) {
            errors.push(format!(
                "EscapeClearance: component '{}' not found",
                escape.component
            ));
        }
    }

    // Routing corridors.
    for corridor in &data.corridors {
        if comp_missing(&corridor.from_component) {
            errors.push(format!(
                "RoutingCorridor '{}': from_component '{}' not found",
                corridor.name, corridor.from_component
            ));
        }
        if comp_missing(&corridor.to_component) {
            errors.push(format!(
                "RoutingCorridor '{}': to_component '{}' not found",
                corridor.name, corridor.to_component
            ));
        }
    }

    // Thermal constraints.
    for thermal in &data.thermals {
        for comp in &thermal.components {
            if comp_missing(comp) {
                errors.push(format!("ThermalConstraint: component '{comp}' not found"));
            }
        }
    }

    errors
}

// ---------------------------------------------------------------------------
// to_yaml() data shape — a tiny ordered JSON-like value so the shape logic
// (conditional keys, dict insertion order) is pure Rust and unit-testable;
// the pyo3 layer converts it to Python objects and the shim calls PyYAML.
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub enum YamlValue {
    Null,
    Bool(bool),
    Float(f64),
    Str(String),
    List(Vec<YamlValue>),
    Dict(Vec<(String, YamlValue)>),
}

/// `ConstraintBuilder.to_yaml()` data assembly — dict keys in the exact
/// insertion order `yaml.dump(..., sort_keys=False)` will emit.
pub fn builder_to_yaml_data(data: &ConstraintData) -> YamlValue {
    let mut root: Vec<(String, YamlValue)> = Vec::new();

    if !data.spacing_rules.is_empty() {
        let list = data
            .spacing_rules
            .iter()
            .map(|r| {
                YamlValue::Dict(vec![
                    ("components".to_string(), YamlValue::List(vec![
                        YamlValue::Str(r.a.clone()),
                        YamlValue::Str(r.b.clone()),
                    ])),
                    ("min_separation_mm".to_string(), YamlValue::Float(r.min_separation_mm)),
                    ("tier".to_string(), YamlValue::Str(r.tier.clone())),
                    ("weight".to_string(), YamlValue::Float(r.weight)),
                    ("description".to_string(), YamlValue::Str(r.description.clone())),
                ])
            })
            .collect();
        root.push(("minimum_spacing".to_string(), YamlValue::List(list)));
    }

    if !data.groups.is_empty() {
        let list = data
            .groups
            .iter()
            .map(|g| {
                let mut d: Vec<(String, YamlValue)> = vec![
                    ("name".to_string(), YamlValue::Str(g.name.clone())),
                    (
                        "components".to_string(),
                        YamlValue::List(
                            g.components.iter().map(|c| YamlValue::Str(c.clone())).collect(),
                        ),
                    ),
                    ("max_spread_mm".to_string(), YamlValue::Float(g.max_spread_mm)),
                ];
                // `if group.zone:` — an empty-string zone is falsy in Python
                // and must omit the key exactly like zone=None.
                if let Some(zone) = &g.zone
                    && !zone.is_empty()
                {
                    d.push(("zone".to_string(), YamlValue::Str(zone.clone())));
                }
                if g.weight != 1.0 {
                    d.push(("weight".to_string(), YamlValue::Float(g.weight)));
                }
                if !g.description.is_empty() {
                    d.push(("description".to_string(), YamlValue::Str(g.description.clone())));
                }
                if !g.proximity_rules.is_empty() {
                    let prox = g
                        .proximity_rules
                        .iter()
                        .map(|pr| {
                            YamlValue::Dict(vec![
                                (
                                    "pair".to_string(),
                                    YamlValue::List(vec![
                                        YamlValue::Str(pr.a.clone()),
                                        YamlValue::Str(pr.b.clone()),
                                    ]),
                                ),
                                ("max_distance_mm".to_string(), YamlValue::Float(pr.max_distance_mm)),
                                ("tier".to_string(), YamlValue::Str(pr.tier.clone())),
                            ])
                        })
                        .collect();
                    d.push(("proximity".to_string(), YamlValue::List(prox)));
                }
                YamlValue::Dict(d)
            })
            .collect();
        root.push(("groups".to_string(), YamlValue::List(list)));
    }

    if !data.escape_clearances.is_empty() {
        let list = data
            .escape_clearances
            .iter()
            .map(|ec| {
                YamlValue::Dict(vec![
                    ("component".to_string(), YamlValue::Str(ec.component.clone())),
                    (
                        "clearance_mm".to_string(),
                        match ec.clearance_mm {
                            Some(c) => YamlValue::Float(c),
                            None => YamlValue::Null,
                        },
                    ),
                    (
                        "priority_sides".to_string(),
                        YamlValue::List(
                            ec.priority_sides.iter().map(|s| YamlValue::Str(s.clone())).collect(),
                        ),
                    ),
                    ("tier".to_string(), YamlValue::Str(ec.tier.clone())),
                    ("description".to_string(), YamlValue::Str(ec.description.clone())),
                ])
            })
            .collect();
        root.push(("escape_clearances".to_string(), YamlValue::List(list)));
    }

    if !data.corridors.is_empty() {
        let list = data
            .corridors
            .iter()
            .map(|rc| {
                YamlValue::Dict(vec![
                    ("name".to_string(), YamlValue::Str(rc.name.clone())),
                    ("from_component".to_string(), YamlValue::Str(rc.from_component.clone())),
                    ("to_component".to_string(), YamlValue::Str(rc.to_component.clone())),
                    ("width_mm".to_string(), YamlValue::Float(rc.width_mm)),
                    ("keep_clear".to_string(), YamlValue::Bool(rc.keep_clear)),
                    (
                        "nets".to_string(),
                        YamlValue::List(rc.nets.iter().map(|n| YamlValue::Str(n.clone())).collect()),
                    ),
                    ("tier".to_string(), YamlValue::Str(rc.tier.clone())),
                ])
            })
            .collect();
        root.push(("routing_corridors".to_string(), YamlValue::List(list)));
    }

    if !data.thermals.is_empty() {
        let list = data
            .thermals
            .iter()
            .map(|tc| {
                YamlValue::Dict(vec![
                    (
                        "components".to_string(),
                        YamlValue::List(
                            tc.components.iter().map(|c| YamlValue::Str(c.clone())).collect(),
                        ),
                    ),
                    ("prefer_edge".to_string(), YamlValue::Bool(tc.prefer_edge)),
                    (
                        "max_distance_from_edge_mm".to_string(),
                        YamlValue::Float(tc.max_distance_from_edge_mm),
                    ),
                    ("min_spacing_mm".to_string(), YamlValue::Float(tc.min_spacing_mm)),
                    ("description".to_string(), YamlValue::Str(tc.description.clone())),
                ])
            })
            .collect();
        root.push(("thermal_constraints".to_string(), YamlValue::List(list)));
    }

    YamlValue::Dict(root)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::constraints::SpacingRule;

    #[cfg_attr(test, test)]
    fn find_similar_prefix_and_suffix() {
        let opts = vec![
            "U_MCU".to_string(),
            "U_GATE".to_string(),
            "C1".to_string(),
            "R5".to_string(),
        ];
        assert_eq!(find_similar("U_MC", &opts), Some("U_MCU".to_string()));
        assert_eq!(find_similar("X_GATE", &opts), Some("U_GATE".to_string()));
        assert_eq!(find_similar("MISSING", &opts), None);
        assert_eq!(find_similar("C", &opts), None);
        assert_eq!(find_similar("", &opts), None);
    }

    #[cfg_attr(test, test)]
    fn builder_validate_empty_and_missing() {
        let data = ConstraintData {
            board_bounds: None,
            spacing_rules: vec![SpacingRule {
                a: "A".into(),
                b: "B".into(),
                min_separation_mm: 10.0,
                tier: "soft".into(),
                weight: 1.0,
                description: String::new(),
            }],
            groups: vec![],
            escape_clearances: vec![],
            corridors: vec![],
            thermals: vec![],
            zones: vec![],
            zone_assignments: vec![],
        };
        assert_eq!(builder_validate(&data, &[], None), vec![
            "ComponentSpacing: component 'A' not found",
            "ComponentSpacing: component 'B' not found",
        ]);
        assert!(builder_validate(&data, &["A".to_string(), "B".to_string()], None).is_empty());
    }

    #[cfg_attr(test, test)]
    fn yaml_data_conditional_keys() {
        let data = ConstraintData {
            board_bounds: None,
            spacing_rules: vec![],
            groups: vec![crate::constraints::Group {
                name: "g".into(),
                components: vec!["A".into(), "B".into()],
                max_spread_mm: 30.0,
                zone: None,
                weight: 1.0,
                description: String::new(),
                proximity_rules: vec![],
            }],
            escape_clearances: vec![],
            corridors: vec![],
            thermals: vec![],
            zones: vec![],
            zone_assignments: vec![],
        };
        match builder_to_yaml_data(&data) {
            YamlValue::Dict(root) => {
                let YamlValue::List(groups) = &root[0].1 else {
                    panic!("expected groups list");
                };
                let YamlValue::Dict(g) = &groups[0] else {
                    panic!("expected group dict");
                };
                let keys: Vec<&str> = g.iter().map(|(k, _)| k.as_str()).collect();
                assert_eq!(keys, vec!["name", "components", "max_spread_mm"]);
            }
            other => panic!("expected dict, got {other:?}"),
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("constraints::validate::tests::find_similar_prefix_and_suffix", find_similar_prefix_and_suffix),
        ("constraints::validate::tests::builder_validate_empty_and_missing", builder_validate_empty_and_missing),
        ("constraints::validate::tests::yaml_data_conditional_keys", yaml_data_conditional_keys),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

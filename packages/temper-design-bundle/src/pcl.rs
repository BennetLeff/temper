use crate::{atopile::AtopileExport, error::diagnostic, model::Constraint};
use serde::Deserialize;
use temper_pcl_ir::{ConstraintOrigin, ConstraintTier, PclConstraintKind};

#[derive(Debug, Clone, Deserialize)]
pub struct PclDocument {
    #[serde(default)]
    pub constraints: Vec<PclInputConstraint>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PclInputConstraint {
    #[serde(default)]
    pub id: Option<String>,
    pub r#type: String,
    #[serde(default)]
    pub source_location: Option<String>,
    #[serde(default)]
    pub subject: Option<String>,
    #[serde(default)]
    pub metric: Option<String>,
    #[serde(default)]
    pub value_mm: Option<f64>,
    #[serde(default)]
    pub max_distance_mm: Option<f64>,
    #[serde(default)]
    pub min_distance_mm: Option<f64>,
    #[serde(default)]
    pub margin_mm: Option<f64>,
    #[serde(default)]
    pub max_area_mm2: Option<f64>,
    #[serde(default)]
    pub a: Option<String>,
    #[serde(default)]
    pub b: Option<String>,
    #[serde(default)]
    pub outer: Option<String>,
    #[serde(default)]
    pub inner: Vec<String>,
    #[serde(default)]
    pub components: Vec<String>,
    #[serde(default)]
    pub axis: Option<String>,
    #[serde(default)]
    pub tolerance_mm: Option<f64>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub edge: Option<String>,
    #[serde(default)]
    pub bounds_mm: Option<[f64; 4]>,
    #[serde(default)]
    pub region: Option<[f64; 4]>,
    #[serde(default)]
    pub position: Option<[f64; 2]>,
    #[serde(default)]
    pub component: Option<String>,
    #[serde(default)]
    pub loop_name: Option<String>,
    #[serde(default = "default_tier")]
    pub tier: u8,
    #[serde(default)]
    pub because: Option<String>,
}

fn default_tier() -> u8 {
    1
}

impl PclDocument {
    pub fn into_constraints(
        self,
        a: &AtopileExport,
    ) -> Result<Vec<Constraint>, crate::DesignBundleError> {
        let ids: std::collections::HashSet<_> = a
            .components
            .iter()
            .map(|c| c.id.as_str())
            .chain(a.nets.iter().map(|n| n.id.as_str()))
            .chain(a.zones.iter().map(String::as_str))
            .chain(a.loops.iter().map(String::as_str))
            .collect();
        self.constraints
            .into_iter()
            .enumerate()
            .map(|(index, c)| convert(c, index, &ids))
            .collect()
    }
}

fn convert(
    c: PclInputConstraint,
    index: usize,
    ids: &std::collections::HashSet<&str>,
) -> Result<Constraint, crate::DesignBundleError> {
    let id =
        c.id.clone()
            .unwrap_or_else(|| format!("pcl-{index}-{}", c.r#type));
    let location = c
        .source_location
        .clone()
        .unwrap_or_else(|| "<unknown source>".into());
    let unsupported = || {
        diagnostic(
            "unsupported_constraint_type",
            format!(
                "PCL constraint {id} has unsupported type '{}' at {location}",
                c.r#type
            ),
            vec![id.clone(), c.r#type.clone(), location.clone()],
        )
    };
    let tier = ConstraintTier::try_from(c.tier).map_err(|_| {
        diagnostic(
            "invalid_tier",
            format!("constraint {id} has invalid tier"),
            vec![id.clone(), location.clone()],
        )
    })?;
    let (kind, references) = match c.r#type.as_str() {
        "adjacent" => {
            let a = required(c.a.or(c.subject), "a", &id, &location)?;
            let b = required(c.b, "b", &id, &location)?;
            let max = required_value(c.max_distance_mm.or(c.value_mm), &id, &location)?;
            let metric = c.metric.unwrap_or_else(|| "edge_to_edge".into());
            (
                PclConstraintKind::Adjacent {
                    a: a.clone(),
                    b: b.clone(),
                    max_distance_mm: max,
                    metric,
                },
                vec![a, b],
            )
        }
        "separated" => {
            let a = required(c.a.or(c.subject), "a", &id, &location)?;
            let b = required(c.b, "b", &id, &location)?;
            let min = required_value(c.min_distance_mm.or(c.value_mm), &id, &location)?;
            let metric = c.metric.unwrap_or_else(|| "edge_to_edge".into());
            (
                PclConstraintKind::Separated {
                    a: a.clone(),
                    b: b.clone(),
                    min_distance_mm: min,
                    metric,
                },
                vec![a, b],
            )
        }
        "enclosing" => {
            let outer = required(c.outer.or(c.subject), "outer", &id, &location)?;
            if c.inner.is_empty() {
                return Err(diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires non-empty inner"),
                    vec![id, location],
                ));
            }
            let margin = required_value(c.margin_mm.or(c.value_mm), &id, &location)?;
            let mut refs = vec![outer.clone()];
            refs.extend(c.inner.iter().cloned());
            (
                PclConstraintKind::Enclosing {
                    outer,
                    inner: c.inner,
                    margin_mm: margin,
                },
                refs,
            )
        }
        "keepout" => {
            let subject = required(c.subject, "subject", &id, &location)?;
            let bounds = c.bounds_mm.ok_or_else(|| {
                diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires bounds_mm"),
                    vec![id.clone(), location.clone()],
                )
            })?;
            let margin = required_value(c.margin_mm.or(c.value_mm), &id, &location)?;
            (
                PclConstraintKind::Keepout {
                    subject: subject.clone(),
                    bounds_mm: bounds,
                    margin_mm: margin,
                },
                vec![subject],
            )
        }
        "aligned" => {
            if c.components.len() < 2 {
                return Err(diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires at least two components"),
                    vec![id.clone(), location],
                ));
            }
            let axis = required(c.axis, "axis", &id, &location)?;
            let tolerance = required_value(
                c.tolerance_mm.or(c.value_mm).or(c.margin_mm),
                &id,
                &location,
            )?;
            (
                PclConstraintKind::Aligned {
                    components: c.components.clone(),
                    axis,
                    tolerance_mm: tolerance,
                },
                c.components,
            )
        }
        "on_side" => {
            if c.components.is_empty() {
                return Err(diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires components"),
                    vec![id.clone(), location],
                ));
            }
            let side = required(c.side, "side", &id, &location)?;
            let edge = required(c.edge, "edge", &id, &location)?;
            let max = match c.max_distance_mm.or(c.value_mm) {
                Some(value) => {
                    validate_value(value, &id, &location)?;
                    Some(value)
                }
                None => None,
            };
            (
                PclConstraintKind::OnSide {
                    components: c.components.clone(),
                    side,
                    edge,
                    max_distance_mm: max,
                },
                c.components,
            )
        }
        "anchored" => {
            let component = required(c.component.or(c.subject), "component", &id, &location)?;
            if c.region.is_none() && c.position.is_none() {
                return Err(diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires region or position"),
                    vec![id.clone(), location],
                ));
            }
            (
                PclConstraintKind::Anchored {
                    component: component.clone(),
                    region: c.region,
                    position: c.position,
                },
                vec![component],
            )
        }
        "loop_area" => {
            let loop_name = required(c.loop_name.or(c.subject), "loop_name", &id, &location)?;
            let area = c.max_area_mm2.ok_or_else(|| {
                diagnostic(
                    "missing_field",
                    format!("PCL constraint {id} requires max_area_mm2"),
                    vec![id.clone(), location.clone()],
                )
            })?;
            validate_value(area, &id, &location)?;
            (
                PclConstraintKind::LoopArea {
                    loop_name: loop_name.clone(),
                    max_area_mm2: area,
                },
                vec![loop_name],
            )
        }
        _ => return Err(unsupported()),
    };
    for reference in &references {
        if !ids.contains(reference.as_str()) {
            return Err(diagnostic(
                "unresolved_reference",
                format!("PCL constraint {id} references {reference} at {location}"),
                vec![id.clone(), reference.clone(), location.clone()],
            ));
        }
    }
    Ok(Constraint {
        schema_version: 1,
        id,
        tier,
        because: c.because,
        origin: ConstraintOrigin::AuthoredPcl,
        kind,
        references,
    })
}

fn required(
    value: Option<String>,
    field: &str,
    id: &str,
    location: &str,
) -> Result<String, crate::DesignBundleError> {
    value.filter(|v| !v.is_empty()).ok_or_else(|| {
        diagnostic(
            "missing_field",
            format!("PCL constraint {id} requires {field} at {location}"),
            vec![id.into(), field.into(), location.into()],
        )
    })
}
fn required_value(
    value: Option<f64>,
    id: &str,
    location: &str,
) -> Result<f64, crate::DesignBundleError> {
    let value = value.ok_or_else(|| {
        diagnostic(
            "missing_field",
            format!("PCL constraint {id} requires a dimensional value at {location}"),
            vec![id.into(), location.into()],
        )
    })?;
    validate_value(value, id, location)?;
    Ok(value)
}
fn validate_value(value: f64, id: &str, location: &str) -> Result<(), crate::DesignBundleError> {
    if !value.is_finite() || value < 0.0 {
        Err(diagnostic(
            "invalid_unit",
            format!("constraint {id} has invalid value at {location}"),
            vec![id.into(), location.into()],
        ))
    } else {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        atopile::AtopileExport,
        model::{BoardSpec, Component},
    };
    fn export() -> AtopileExport {
        AtopileExport {
            schema_version: 1,
            board: BoardSpec {
                width_mm: 1.0,
                height_mm: 1.0,
                thickness_mm: 1.0,
            },
            components: vec![
                Component {
                    id: "A".into(),
                    reference: None,
                },
                Component {
                    id: "B".into(),
                    reference: None,
                },
            ],
            nets: vec![],
            net_classes: vec![],
            safety_domains: vec![],
            stackup: None,
            zones: vec!["Z".into()],
            loops: vec!["L".into()],
            safety: vec![],
        }
    }
    #[test]
    fn unknown_type_is_fatal() {
        let result: PclDocument =
            serde_yaml::from_str("constraints:\n- id: x\n  type: future_type\n").unwrap();
        let error = result.into_constraints(&export()).unwrap_err();
        assert!(error.to_string().contains("unsupported_constraint_type"));
    }
    #[test]
    fn pair_without_b_is_fatal() {
        let result: PclDocument = serde_yaml::from_str(
            "constraints:\n- id: x\n  type: adjacent\n  a: A\n  max_distance_mm: 1\n",
        )
        .unwrap();
        let error = result.into_constraints(&export()).unwrap_err();
        assert!(error.to_string().contains("requires b"));
    }
    #[test]
    fn variants_preserve_structural_fields() {
        let yaml = "constraints:\n- id: e\n  type: enclosing\n  outer: Z\n  inner: [A, B]\n  margin_mm: 1\n- id: k\n  type: keepout\n  subject: A\n  bounds_mm: [1, 2, 3, 4]\n  margin_mm: 1\n- id: a\n  type: aligned\n  components: [A, B]\n  axis: x\n  value_mm: 1\n- id: s\n  type: on_side\n  components: [A, B]\n  side: left\n  edge: flush\n  max_distance_mm: 1\n- id: n\n  type: anchored\n  component: A\n  region: [1, 2, 3, 4]\n";
        let result: PclDocument = serde_yaml::from_str(yaml).unwrap();
        let constraints = result.into_constraints(&export()).unwrap();
        assert_eq!(constraints.len(), 5);
        assert!(matches!(
            constraints[1].kind,
            PclConstraintKind::Keepout {
                bounds_mm: [1.0, 2.0, 3.0, 4.0],
                ..
            }
        ));
    }
}

#[cfg(test)]
mod real_pcl_tests {
    use super::*;
    use crate::{
        atopile::AtopileExport,
        model::{BoardSpec, Component},
    };
    #[test]
    fn full_temper_pcl_has_no_unsupported_types_and_on_side_needs_no_distance() {
        let bytes =
            include_bytes!("../../../packages/temper-placer/configs/pcl/temper_induction.yaml");
        let document: PclDocument = serde_yaml::from_slice(bytes).unwrap();
        assert!(document.constraints.iter().any(|c| c.r#type == "on_side"));
        // Derived, not declared: into_constraints maps 1:1 (see its
        // `.map` over `self.constraints`, no filtering), so the only
        // thing worth asserting is that conversion doesn't drop, add, or
        // panic on any constraint in the real production file -- not a
        // literal count, which would itself be a hand-maintained number
        // that drifts every time this live-edited YAML legitimately
        // gains a constraint (as it just did: 8 -> 9).
        let expected_constraint_count = document.constraints.len();
        let no_distance: PclDocument = serde_yaml::from_str("constraints:\n- type: on_side\n  components: [A, B]\n  side: top\n  edge: flush\n  tier: 1\n  because: edge placement\n").unwrap();
        let no_distance_export = AtopileExport {
            schema_version: 1,
            board: BoardSpec {
                width_mm: 1.0,
                height_mm: 1.0,
                thickness_mm: 1.0,
            },
            components: vec![
                Component {
                    id: "A".into(),
                    reference: None,
                },
                Component {
                    id: "B".into(),
                    reference: None,
                },
            ],
            nets: vec![],
            net_classes: vec![],
            safety_domains: vec![],
            stackup: None,
            zones: vec![],
            loops: vec![],
            safety: vec![],
        };
        assert!(matches!(
            no_distance.into_constraints(&no_distance_export).unwrap()[0].kind,
            temper_pcl_ir::PclConstraintKind::OnSide {
                max_distance_mm: None,
                ..
            }
        ));
        let mut names = std::collections::BTreeSet::new();
        for c in &document.constraints {
            for value in [&c.a, &c.b, &c.subject, &c.outer, &c.component, &c.loop_name]
                .into_iter()
                .flatten()
            {
                names.insert(value.clone());
            }
            names.extend(c.inner.iter().cloned());
            names.extend(c.components.iter().cloned());
        }
        let a = AtopileExport {
            schema_version: 1,
            board: BoardSpec {
                width_mm: 100.0,
                height_mm: 150.0,
                thickness_mm: 1.6,
            },
            components: names
                .iter()
                .map(|id| Component {
                    id: id.clone(),
                    reference: None,
                })
                .collect(),
            nets: vec![],
            net_classes: vec![],
            safety_domains: vec![],
            stackup: None,
            zones: vec![],
            loops: vec![],
            safety: vec![],
        };
        let result = document.into_constraints(&a).unwrap();
        assert_eq!(result.len(), expected_constraint_count);
    }
}

use crate::{
    atopile::AtopileExport,
    error::diagnostic,
    model::{Constraint, ConstraintOrigin},
};
use serde::Deserialize;
#[derive(Debug, Clone, Deserialize)]
pub struct PclDocument {
    #[serde(default)]
    pub constraints: Vec<PclConstraint>,
}
#[derive(Debug, Clone, Deserialize)]
pub struct PclConstraint {
    #[serde(default)]
    pub id: Option<String>,
    pub r#type: String,
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
            .map(|(index, c)| {
                let subject = c
                    .subject
                    .clone()
                    .or(c.a.clone())
                    .or(c.component.clone())
                    .or(c.loop_name.clone())
                    .ok_or_else(|| {
                        diagnostic("invalid_constraint", "constraint has no subject", vec![])
                    })?;
                let value = c
                    .value_mm
                    .or(c.max_distance_mm)
                    .or(c.min_distance_mm)
                    .or(c.margin_mm)
                    .or(c.max_area_mm2)
                    .ok_or_else(|| {
                        diagnostic(
                            "invalid_unit",
                            format!(
                                "constraint {} has no dimensional value",
                                c.id.as_deref().unwrap_or("<unnamed>")
                            ),
                            vec![],
                        )
                    })?;
                let id =
                    c.id.unwrap_or_else(|| format!("pcl-{}-{}", index, c.r#type));
                if !value.is_finite() || value < 0.0 {
                    return Err(diagnostic(
                        "invalid_unit",
                        format!("constraint {id} has invalid millimetres",),
                        vec![id],
                    ));
                }
                for reference in [Some(subject.as_str()), c.b.as_deref()]
                    .into_iter()
                    .flatten()
                {
                    if !ids.contains(reference) {
                        return Err(diagnostic(
                            "unresolved_reference",
                            format!("PCL constraint {id} references {reference}"),
                            vec![id.clone(), reference.into()],
                        ));
                    }
                }
                Ok(Constraint {
                    id,
                    subject,
                    metric: c.metric.unwrap_or(c.r#type),
                    value_mm: value,
                    tier: c.tier,
                    because: c.because,
                    origin: ConstraintOrigin::AuthoredPcl,
                })
            })
            .collect()
    }
}

use crate::model::{Component, Constraint, ConstraintOrigin, Net, NetClass, SafetyDomain, Stackup};
use serde::{Deserialize, Serialize};
use temper_pcl_ir::{ConstraintTier, PclConstraintKind};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileExport {
    pub schema_version: u32,
    pub board: crate::model::BoardSpec,
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
    #[serde(default)]
    pub net_classes: Vec<NetClass>,
    #[serde(default)]
    pub safety_domains: Vec<SafetyDomain>,
    #[serde(default)]
    pub stackup: Option<Stackup>,
    #[serde(default)]
    pub zones: Vec<String>,
    #[serde(default)]
    pub loops: Vec<String>,
    #[serde(default)]
    pub safety: Vec<SafetyRule>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileNet {
    pub signal: String,
    pub canonical_name: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtopileComponent {
    pub id: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyRule {
    pub id: String,
    pub subject: String,
    pub metric: String,
    pub value_mm: f64,
    #[serde(default)]
    pub because: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MappingEntry {
    pub atopile_signal: String,
    pub kicad_net: String,
    #[serde(default)]
    pub aliases: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetMapping {
    pub schema_version: u32,
    pub entries: Vec<MappingEntry>,
}
impl AtopileExport {
    pub fn derived_constraints(&self) -> Vec<Constraint> {
        self.safety
            .iter()
            .map(|r| Constraint {
                schema_version: 1,
                id: r.id.clone(),
                tier: ConstraintTier::Hard,
                because: r.because.clone(),
                origin: ConstraintOrigin::AtopileDerived,
                references: vec![r.subject.clone()],
                kind: PclConstraintKind::Separated {
                    a: r.subject.clone(),
                    b: r.subject.clone(),
                    min_distance_mm: r.value_mm,
                    metric: r.metric.clone(),
                },
            })
            .collect()
    }
}

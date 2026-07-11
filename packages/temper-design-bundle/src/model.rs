use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BoardSpec {
    pub width_mm: f64,
    pub height_mm: f64,
    #[serde(default)]
    pub thickness_mm: f64,
}
impl BoardSpec {
    pub fn validate(&self) -> bool {
        self.width_mm.is_finite()
            && self.height_mm.is_finite()
            && self.width_mm > 0.0
            && self.height_mm > 0.0
            && self.thickness_mm.is_finite()
            && self.thickness_mm >= 0.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Component {
    pub id: String,
    #[serde(default)]
    pub reference: Option<String>,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Net {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub net_class: Option<String>,
    #[serde(default)]
    pub safety_domain: Option<String>,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NetClass {
    pub id: String,
    pub clearance_mm: f64,
    #[serde(default)]
    pub creepage_mm: Option<f64>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SafetyDomain {
    pub id: String,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Stackup {
    pub layers: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ConstraintOrigin {
    AtopileDerived,
    AuthoredPcl,
    DerivedValidation,
    RouterFeedback,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Constraint {
    pub id: String,
    pub subject: String,
    pub metric: String,
    pub value_mm: f64,
    pub tier: u8,
    pub because: Option<String>,
    pub origin: ConstraintOrigin,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ConstraintSet {
    pub constraints: Vec<Constraint>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Provenance {
    pub atopile_sha256: String,
    pub pcl_sha256: String,
    pub board_sha256: String,
    pub mapping_sha256: String,
}
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DesignBundle {
    pub schema_version: u32,
    pub board: BoardSpec,
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
    pub net_classes: Vec<NetClass>,
    pub safety_domains: Vec<SafetyDomain>,
    pub stackup: Option<Stackup>,
    pub constraints: ConstraintSet,
    pub provenance: Provenance,
}

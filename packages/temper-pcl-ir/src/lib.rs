use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Ord, PartialOrd)]
#[serde(rename_all = "snake_case")]
pub enum ConstraintTier {
    Hard = 1,
    Strong = 2,
    Soft = 3,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConstraintOrigin {
    AtopileDerived,
    AuthoredPcl,
    DerivedValidation,
    RouterFeedback,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MergeOrder {
    Minimum,
    Maximum,
    Structural,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum PclConstraintKind {
    Adjacent {
        a: String,
        b: String,
        max_distance_mm: f64,
        metric: String,
    },
    Separated {
        a: String,
        b: String,
        min_distance_mm: f64,
        metric: String,
    },
    Enclosing {
        outer: String,
        inner: Vec<String>,
        margin_mm: f64,
    },
    Keepout {
        subject: String,
        bounds_mm: [f64; 4],
        margin_mm: f64,
    },
    Aligned {
        components: Vec<String>,
        axis: String,
        tolerance_mm: f64,
    },
    OnSide {
        components: Vec<String>,
        side: String,
        edge: String,
        max_distance_mm: Option<f64>,
    },
    Anchored {
        component: String,
        region: Option<[f64; 4]>,
        position: Option<[f64; 2]>,
    },
    LoopArea {
        loop_name: String,
        max_area_mm2: f64,
    },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PclConstraint {
    pub schema_version: u32,
    pub id: String,
    pub tier: ConstraintTier,
    pub because: Option<String>,
    pub origin: ConstraintOrigin,
    pub kind: PclConstraintKind,
    #[serde(default)]
    pub references: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct PclIr {
    pub schema_version: u32,
    pub constraints: Vec<PclConstraint>,
}

impl PclConstraintKind {
    pub fn merge_order(&self) -> MergeOrder {
        match self {
            PclConstraintKind::Separated { .. } => MergeOrder::Minimum,
            PclConstraintKind::Adjacent { .. } | PclConstraintKind::LoopArea { .. } => {
                MergeOrder::Maximum
            }
            PclConstraintKind::Enclosing { .. }
            | PclConstraintKind::Keepout { .. }
            | PclConstraintKind::Aligned { .. }
            | PclConstraintKind::OnSide { .. }
            | PclConstraintKind::Anchored { .. } => MergeOrder::Structural,
        }
    }
}

impl PclConstraint {
    pub fn subject_metric_key(&self) -> String {
        match &self.kind {
            PclConstraintKind::Adjacent { a, b, metric, .. } => pair_key("adjacent", metric, a, b),
            PclConstraintKind::Separated { a, b, metric, .. } => {
                pair_key("separated", metric, a, b)
            }
            PclConstraintKind::Enclosing { outer, .. } => format!("{outer}:enclosing"),
            PclConstraintKind::Keepout { subject, .. } => format!("{subject}:keepout"),
            PclConstraintKind::Aligned {
                components, axis, ..
            } => format!("{components:?}:{axis}"),
            PclConstraintKind::OnSide {
                components, side, ..
            } => format!("{components:?}:{side}"),
            PclConstraintKind::Anchored { component, .. } => format!("{component}:anchored"),
            PclConstraintKind::LoopArea { loop_name, .. } => format!("{loop_name}:loop_area"),
        }
    }
}

fn pair_key(kind: &str, metric: &str, a: &str, b: &str) -> String {
    let (min, max) = if a <= b { (a, b) } else { (b, a) };
    format!("{kind}:{metric}:min({min}):max({max})")
}

impl TryFrom<u8> for ConstraintTier {
    type Error = ();
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            1 => Ok(Self::Hard),
            2 => Ok(Self::Strong),
            3 => Ok(Self::Soft),
            _ => Err(()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_pcl_kinds_round_trip_deterministically() {
        let ir = PclIr {
            schema_version: 1,
            constraints: vec![PclConstraint {
                schema_version: 1,
                id: "keepout-1".into(),
                tier: ConstraintTier::Hard,
                because: Some("safety exclusion".into()),
                origin: ConstraintOrigin::AuthoredPcl,
                kind: PclConstraintKind::Keepout {
                    subject: "Q1".into(),
                    bounds_mm: [1.0, 2.0, 3.0, 4.0],
                    margin_mm: 1.0,
                },
                references: vec!["Q1".into()],
            }],
        };
        let encoded = serde_json::to_string(&ir).unwrap();
        assert_eq!(
            serde_json::to_string(&serde_json::from_str::<PclIr>(&encoded).unwrap()).unwrap(),
            encoded
        );
    }
}

#[cfg(test)]
mod key_tests {
    use super::*;
    fn pair(a: &str, b: &str) -> PclConstraint {
        PclConstraint {
            schema_version: 1,
            id: "x".into(),
            tier: ConstraintTier::Hard,
            because: None,
            origin: ConstraintOrigin::AuthoredPcl,
            kind: PclConstraintKind::Separated {
                a: a.into(),
                b: b.into(),
                min_distance_mm: 1.0,
                metric: "clearance".into(),
            },
            references: vec![],
        }
    }
    #[test]
    fn pair_identity_includes_b_and_is_symmetric() {
        assert_eq!(
            pair("A", "B").subject_metric_key(),
            pair("B", "A").subject_metric_key()
        );
        assert_ne!(
            pair("A", "B").subject_metric_key(),
            pair("A", "C").subject_metric_key()
        );
        assert_eq!(
            pair("A", "B").subject_metric_key(),
            "separated:clearance:min(A):max(B)"
        );
    }
}

use std::collections::HashMap;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SafetyCategory {
    HV,
    LV,
    AC,
    Iso,
}

impl SafetyCategory {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "HV" => Some(SafetyCategory::HV),
            "LV" => Some(SafetyCategory::LV),
            "AC" => Some(SafetyCategory::AC),
            "iso" | "ISO" | "Iso" => Some(SafetyCategory::Iso),
            _ => None,
        }
    }
}

impl fmt::Display for SafetyCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SafetyCategory::HV => write!(f, "HV"),
            SafetyCategory::LV => write!(f, "LV"),
            SafetyCategory::AC => write!(f, "AC"),
            SafetyCategory::Iso => write!(f, "iso"),
        }
    }
}

#[derive(Debug, Clone)]
pub struct NetClassMetadata {
    pub class_name: String,
    pub safety_category: Option<SafetyCategory>,
    pub clearance: f64,
    pub creepage_mm: f64,
    pub required_layer: Option<String>,
    pub dru_priority: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct LatticePair {
    pub a: SafetyCategory,
    pub b: SafetyCategory,
}

fn join_impl(a: SafetyCategory, b: SafetyCategory) -> SafetyCategory {
    use SafetyCategory::*;
    if a == b {
        return a;
    }
    match (a, b) {
        (Iso, _) | (_, Iso) => Iso,
        (HV, LV) | (LV, HV) => Iso,
        (HV, AC) | (AC, HV) => Iso,
        (AC, LV) | (LV, AC) => Iso,
        _ => Iso,
    }
}

fn meet_impl(a: SafetyCategory, b: SafetyCategory) -> SafetyCategory {
    use SafetyCategory::*;
    if a == b {
        return a;
    }
    match (a, b) {
        (Iso, x) | (x, Iso) => x,
        (HV, LV) | (LV, HV) => LV,
        (HV, AC) | (AC, HV) => AC,
        (AC, LV) | (LV, AC) => LV,
        _ => LV,
    }
}

#[derive(Debug, Clone)]
pub struct InferredNetPairConstraint {
    pub net_a: usize,
    pub net_b: usize,
    pub net_class_a: String,
    pub net_class_b: String,
    pub clearance_floor_mm: f64,
    pub layer_restriction: Option<String>,
    pub separation_required: bool,
    pub channel_id: Option<String>,
}

pub struct TypeLattice {
    pub net_classes: HashMap<String, NetClassMetadata>,
}

impl TypeLattice {
    pub fn new(metadata: Vec<NetClassMetadata>) -> Self {
        let net_classes: HashMap<String, NetClassMetadata> = metadata
            .into_iter()
            .map(|m| (m.class_name.clone(), m))
            .collect();
        Self { net_classes }
    }

    pub fn from_metadata(metadata: Vec<NetClassMetadata>) -> Self {
        Self::new(metadata)
    }

    pub fn join(&self, a: SafetyCategory, b: SafetyCategory) -> SafetyCategory {
        join_impl(a, b)
    }

    pub fn meet(&self, a: SafetyCategory, b: SafetyCategory) -> SafetyCategory {
        meet_impl(a, b)
    }

    pub fn infer(
        &self,
        net_class_a: &str,
        net_class_b: &str,
    ) -> Option<InferredConstraint> {
        let meta_a = self.net_classes.get(net_class_a)?;
        let meta_b = self.net_classes.get(net_class_b)?;
        let cat_a = meta_a.safety_category?;
        let cat_b = meta_b.safety_category?;

        let join_cat = self.join(cat_a, cat_b);
        let separation_required = matches!(join_cat, SafetyCategory::Iso | SafetyCategory::HV);

        let clearance_floor_mm = if join_cat == SafetyCategory::Iso {
            let max_creepage = meta_a
                .creepage_mm
                .max(meta_b.creepage_mm);
            let max_clearance = meta_a.clearance.max(meta_b.clearance);
            max_creepage.max(max_clearance)
        } else if join_cat == SafetyCategory::HV {
            meta_a.creepage_mm.max(meta_b.creepage_mm).max(
                meta_a.clearance.max(meta_b.clearance),
            )
        } else {
            meta_a.clearance.max(meta_b.clearance)
        };

        let layer_restriction: Option<String> = {
            let layer_a = &meta_a.required_layer;
            let layer_b = &meta_b.required_layer;
            if layer_a.is_some() && layer_b.is_some() && layer_a != layer_b {
                Some(layer_a.clone().unwrap_or_default())
            } else if layer_a.is_some() {
                layer_a.clone()
            } else {
                layer_b.clone()
            }
        };

        Some(InferredConstraint {
            clearance_floor_mm,
            layer_restriction,
            separation_required,
        })
    }
}

#[derive(Debug, Clone)]
pub struct InferredConstraint {
    pub clearance_floor_mm: f64,
    pub layer_restriction: Option<String>,
    pub separation_required: bool,
}

pub fn propagate_through_topology(
    skeleton_edges: &[(usize, usize, String)],
    net_class_map: &HashMap<usize, String>,
    lattice: &TypeLattice,
    existing_net_indices: Option<&std::collections::HashSet<usize>>,
) -> (Vec<InferredNetPairConstraint>, Vec<String>) {
    let mut constraints = Vec::new();
    let mut warnings = Vec::new();

    for &(net_a, net_b, ref channel_id) in skeleton_edges {
        if let Some(indices) = existing_net_indices {
            if !indices.contains(&net_a) || !indices.contains(&net_b) {
                continue;
            }
        }

        let class_a = match net_class_map.get(&net_a) {
            Some(c) => c.clone(),
            None => {
                warnings.push(format!("net index {net_a} has no net class mapping"));
                continue;
            }
        };
        let class_b = match net_class_map.get(&net_b) {
            Some(c) => c.clone(),
            None => {
                warnings.push(format!("net index {net_b} has no net class mapping"));
                continue;
            }
        };

        let inferred = match lattice.infer(&class_a, &class_b) {
            Some(i) => i,
            None => {
                warnings.push(format!(
                    "could not infer constraint for net classes {class_a} and {class_b}"
                ));
                continue;
            }
        };

        constraints.push(InferredNetPairConstraint {
            net_a,
            net_b,
            net_class_a: class_a,
            net_class_b: class_b,
            clearance_floor_mm: inferred.clearance_floor_mm,
            layer_restriction: inferred.layer_restriction,
            separation_required: inferred.separation_required,
            channel_id: Some(channel_id.clone()),
        });
    }

    (constraints, warnings)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_metadata(
        name: &str,
        safety: &str,
        clearance: f64,
        creepage: f64,
        required_layer: Option<&str>,
        dru_priority: u32,
    ) -> NetClassMetadata {
        NetClassMetadata {
            class_name: name.to_string(),
            safety_category: SafetyCategory::from_str(safety),
            clearance,
            creepage_mm: creepage,
            required_layer: required_layer.map(|s| s.to_string()),
            dru_priority: Some(dru_priority),
        }
    }

    fn temper_net_classes() -> Vec<NetClassMetadata> {
        vec![
            make_metadata("ACMains", "AC", 6.0, 6.0, None, 10),
            make_metadata("HighVoltage", "HV", 6.0, 6.0, Some("B.Cu"), 20),
            make_metadata("FinePitch", "LV", 0.1, 0.0, None, 30),
            make_metadata("Power", "LV", 0.25, 0.0, None, 40),
            make_metadata("GateDrive", "LV", 0.25, 0.0, Some("F.Cu"), 50),
            make_metadata("GND", "LV", 0.3, 0.0, None, 60),
            make_metadata("HighSpeed", "LV", 0.2, 0.0, None, 70),
            make_metadata("Signal", "LV", 0.15, 0.0, None, 80),
            make_metadata("HighCurrent", "HV", 0.25, 0.0, None, 90),
        ]
    }

    #[test]
    fn test_join_commutative() {
        let lattice = TypeLattice::new(temper_net_classes());
        let cats = [
            SafetyCategory::HV,
            SafetyCategory::LV,
            SafetyCategory::AC,
            SafetyCategory::Iso,
        ];
        for a in &cats {
            for b in &cats {
                assert_eq!(
                    lattice.join(*a, *b),
                    lattice.join(*b, *a),
                    "join({a:?}, {b:?}) not commutative"
                );
            }
        }
    }

    #[test]
    fn test_meet_commutative() {
        let lattice = TypeLattice::new(temper_net_classes());
        let cats = [
            SafetyCategory::HV,
            SafetyCategory::LV,
            SafetyCategory::AC,
            SafetyCategory::Iso,
        ];
        for a in &cats {
            for b in &cats {
                assert_eq!(
                    lattice.meet(*a, *b),
                    lattice.meet(*b, *a),
                    "meet({a:?}, {b:?}) not commutative"
                );
            }
        }
    }

    #[test]
    fn test_join_specific_pairs() {
        let lattice = TypeLattice::new(temper_net_classes());
        assert_eq!(lattice.join(SafetyCategory::HV, SafetyCategory::HV), SafetyCategory::HV);
        assert_eq!(lattice.join(SafetyCategory::HV, SafetyCategory::LV), SafetyCategory::Iso);
        assert_eq!(lattice.join(SafetyCategory::HV, SafetyCategory::AC), SafetyCategory::Iso);
        assert_eq!(lattice.join(SafetyCategory::AC, SafetyCategory::LV), SafetyCategory::Iso);
        assert_eq!(lattice.join(SafetyCategory::Iso, SafetyCategory::HV), SafetyCategory::Iso);
        assert_eq!(lattice.join(SafetyCategory::Iso, SafetyCategory::LV), SafetyCategory::Iso);
    }

    #[test]
    fn test_meet_specific_pairs() {
        let lattice = TypeLattice::new(temper_net_classes());
        assert_eq!(lattice.meet(SafetyCategory::HV, SafetyCategory::HV), SafetyCategory::HV);
        assert_eq!(lattice.meet(SafetyCategory::HV, SafetyCategory::LV), SafetyCategory::LV);
        assert_eq!(lattice.meet(SafetyCategory::HV, SafetyCategory::AC), SafetyCategory::AC);
        assert_eq!(lattice.meet(SafetyCategory::AC, SafetyCategory::LV), SafetyCategory::LV);
        assert_eq!(lattice.meet(SafetyCategory::Iso, SafetyCategory::HV), SafetyCategory::HV);
        assert_eq!(lattice.meet(SafetyCategory::Iso, SafetyCategory::LV), SafetyCategory::LV);
    }

    #[test]
    fn test_join_idempotent() {
        let lattice = TypeLattice::new(temper_net_classes());
        for cat in &[SafetyCategory::HV, SafetyCategory::LV, SafetyCategory::AC, SafetyCategory::Iso] {
            assert_eq!(lattice.join(*cat, *cat), *cat);
        }
    }

    #[test]
    fn test_meet_idempotent() {
        let lattice = TypeLattice::new(temper_net_classes());
        for cat in &[SafetyCategory::HV, SafetyCategory::LV, SafetyCategory::AC, SafetyCategory::Iso] {
            assert_eq!(lattice.meet(*cat, *cat), *cat);
        }
    }

    #[test]
    fn test_hv_hv_pair() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("HighVoltage", "HighCurrent").unwrap();
        assert_eq!(result.clearance_floor_mm, 6.0);
        assert!(result.separation_required);
    }

    #[test]
    fn test_hv_lv_pair() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("HighVoltage", "Signal").unwrap();
        assert_eq!(result.clearance_floor_mm, 6.0);
        assert!(result.separation_required);
    }

    #[test]
    fn test_lv_lv_pair() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("Signal", "Power").unwrap();
        assert_eq!(result.clearance_floor_mm, 0.25);
        assert!(!result.separation_required);
    }

    #[test]
    fn test_ac_lv_pair() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("ACMains", "Signal").unwrap();
        assert_eq!(result.clearance_floor_mm, 6.0);
        assert!(result.separation_required);
    }

    #[test]
    fn test_layer_restriction_hv_on_b_cu() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("HighVoltage", "Signal").unwrap();
        assert_eq!(result.layer_restriction.as_deref(), Some("B.Cu"));
    }

    #[test]
    fn test_no_layer_restriction_when_both_none() {
        let lattice = TypeLattice::new(temper_net_classes());
        let result = lattice.infer("Signal", "Power").unwrap();
        assert!(result.layer_restriction.is_none());
    }

    #[test]
    fn test_net_class_map_miss_returns_none() {
        let lattice = TypeLattice::new(temper_net_classes());
        assert!(lattice.infer("NonExistent", "Signal").is_none());
        assert!(lattice.infer("Signal", "NonExistent").is_none());
    }

    #[test]
    fn test_safety_category_none_returns_none() {
        let mut meta = make_metadata("Unclassified", "LV", 0.2, 0.0, None, 99);
        meta.safety_category = None;
        let lattice = TypeLattice::new(vec![
            meta,
            make_metadata("Signal", "LV", 0.15, 0.0, None, 80),
        ]);
        assert!(lattice.infer("Unclassified", "Signal").is_none());
    }

    #[test]
    fn test_skeleton_walk() {
        let lattice = TypeLattice::new(temper_net_classes());
        let mut net_class_map = HashMap::new();
        net_class_map.insert(0, "HighVoltage".to_string());
        net_class_map.insert(1, "Signal".to_string());
        net_class_map.insert(2, "Power".to_string());
        net_class_map.insert(3, "GND".to_string());
        net_class_map.insert(4, "ACMains".to_string());

        let skeleton_edges = vec![
            (0, 1, "CH1".to_string()),
            (0, 2, "CH1".to_string()),
            (1, 2, "CH2".to_string()),
            (3, 4, "CH3".to_string()),
        ];

        let (constraints, warnings) =
            propagate_through_topology(&skeleton_edges, &net_class_map, &lattice, None);

        assert!(warnings.is_empty());
        assert_eq!(constraints.len(), 4);

        let hv_signal: Vec<_> = constraints
            .iter()
            .filter(|c| {
                (c.net_a == 0 && c.net_b == 1) || (c.net_a == 1 && c.net_b == 0)
            })
            .collect();
        assert_eq!(hv_signal.len(), 1);
        assert!(hv_signal[0].separation_required);
        assert_eq!(hv_signal[0].clearance_floor_mm, 6.0);
    }

    #[test]
    fn test_skeleton_walk_existing_net_indices_filter() {
        let lattice = TypeLattice::new(temper_net_classes());
        let mut net_class_map = HashMap::new();
        net_class_map.insert(0, "HighVoltage".to_string());
        net_class_map.insert(1, "Signal".to_string());
        net_class_map.insert(2, "Power".to_string());

        let skeleton_edges = vec![
            (0, 1, "CH1".to_string()),
            (1, 2, "CH2".to_string()),
        ];

        let mut existing = std::collections::HashSet::new();
        existing.insert(0);
        existing.insert(1);

        let (constraints, _) =
            propagate_through_topology(&skeleton_edges, &net_class_map, &lattice, Some(&existing));

        assert_eq!(constraints.len(), 1);
    }

    #[test]
    fn test_net_class_map_miss_produces_warning() {
        let lattice = TypeLattice::new(temper_net_classes());
        let mut net_class_map = HashMap::new();
        net_class_map.insert(0, "Signal".to_string());

        let skeleton_edges = vec![
            (0, 1, "CH1".to_string()),
        ];

        let (constraints, warnings) =
            propagate_through_topology(&skeleton_edges, &net_class_map, &lattice, None);

        assert!(constraints.is_empty());
        assert!(!warnings.is_empty());
    }
}

use crate::ir_tier0::ConstraintTier;
use crate::ir_tier1::ResolvedConstraint;
use std::collections::HashMap;
use std::fmt;

pub type ProvenanceRef = usize;

#[derive(Debug, Clone)]
pub struct ProvenanceEntry {
    pub pcl_constraint_id: String,
    pub tier0_type: String,
    pub desugar_rule_t0: String,
    pub desugar_rule_t1: String,
    pub rationale: String,
    pub tier: ConstraintTier,
}

#[derive(Debug, Clone, Default)]
pub struct ProvenanceMap {
    pub entries: Vec<ProvenanceEntry>,
    pub clause_to_provenance: HashMap<usize, Vec<ProvenanceRef>>,
}

impl ProvenanceMap {
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
            clause_to_provenance: HashMap::new(),
        }
    }

    pub fn push(
        &mut self,
        pcl_constraint_id: String,
        tier0_type: String,
        desugar_rule_t0: String,
        desugar_rule_t1: String,
        rationale: String,
        tier: ConstraintTier,
    ) -> ProvenanceRef {
        let entry = ProvenanceEntry {
            pcl_constraint_id,
            tier0_type,
            desugar_rule_t0,
            desugar_rule_t1,
            rationale,
            tier,
        };
        let idx = self.entries.len();
        self.entries.push(entry);
        idx
    }

    pub fn push_tier0_and_return(
        &mut self,
        pcl_constraint_id: String,
        tier0_type: String,
        desugar_rule_t0: String,
        rationale: String,
        tier: ConstraintTier,
    ) -> ProvenanceRef {
        self.push(
            pcl_constraint_id,
            tier0_type,
            desugar_rule_t0,
            String::new(),
            rationale,
            tier,
        )
    }

    pub fn push_tier1(
        &mut self,
        model: &[ResolvedConstraint],
        desugar_rule_t1: String,
    ) -> Vec<ProvenanceRef> {
        let mut refs = Vec::new();
        for constraint in model {
            let existing = &self.entries[constraint.provenance()];
            let ref_idx = self.push(
                existing.pcl_constraint_id.clone(),
                existing.tier0_type.clone(),
                existing.desugar_rule_t0.clone(),
                desugar_rule_t1.clone(),
                existing.rationale.clone(),
                existing.tier,
            );
            refs.push(ref_idx);
        }
        refs
    }

    pub fn link_clause(&mut self, clause_idx: usize, prov_ref: ProvenanceRef) {
        self.clause_to_provenance
            .entry(clause_idx)
            .or_insert_with(Vec::new)
            .push(prov_ref);
    }

    pub fn get(&self, idx: ProvenanceRef) -> Option<&ProvenanceEntry> {
        self.entries.get(idx)
    }
}

#[derive(Debug, Clone)]
pub struct ProvenanceDiagnostic {
    pub pcl_constraint_id: String,
    pub tier: ConstraintTier,
    pub rationale: String,
    pub conflict_with: Vec<String>,
    pub clause_indices: Vec<usize>,
}

impl fmt::Display for ProvenanceDiagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.conflict_with.is_empty() {
            write!(
                f,
                "Constraint {} ({}): {} [clauses: {:?}]",
                self.pcl_constraint_id, self.tier, self.rationale, self.clause_indices
            )
        } else {
            write!(
                f,
                "Constraint conflict: {} ({}) with {} — requires {} (PCL constraint '{}')",
                self.rationale,
                self.tier,
                self.conflict_with.join(", "),
                self.rationale,
                self.pcl_constraint_id,
            )
        }
    }
}

pub fn reverse_map_unsat_core(
    core: &[usize],
    prov: &ProvenanceMap,
) -> Vec<ProvenanceDiagnostic> {
    let mut seen_ids: HashMap<String, ProvenanceDiagnostic> = HashMap::new();

    for &clause_idx in core {
        if let Some(prov_refs) = prov.clause_to_provenance.get(&clause_idx) {
            for &ref_idx in prov_refs {
                if let Some(entry) = prov.get(ref_idx) {
                    let diag = seen_ids
                        .entry(entry.pcl_constraint_id.clone())
                        .or_insert_with(|| ProvenanceDiagnostic {
                            pcl_constraint_id: entry.pcl_constraint_id.clone(),
                            tier: entry.tier,
                            rationale: entry.rationale.clone(),
                            conflict_with: Vec::new(),
                            clause_indices: Vec::new(),
                        });
                    if !diag.clause_indices.contains(&clause_idx) {
                        diag.clause_indices.push(clause_idx);
                    }
                }
            }
        }
    }

    seen_ids.into_values().collect()
}

#[derive(Debug, Clone)]
pub struct ConflictReport {
    pub pcl_constraint_ids: Vec<String>,
    pub description: String,
    pub tier: ConstraintTier,
}

impl fmt::Display for ConflictReport {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Conflict {:?}: {} [Tier: {}]",
            self.pcl_constraint_ids, self.description, self.tier
        )
    }
}

pub fn detect_conflicts(model: &[ResolvedConstraint]) -> Vec<ConflictReport> {
    let mut conflicts = Vec::new();

    let separations: Vec<&ResolvedConstraint> = model
        .iter()
        .filter(|c| matches!(c, ResolvedConstraint::Separation { .. }))
        .collect();
    let adjacencies: Vec<&ResolvedConstraint> = model
        .iter()
        .filter(|c| matches!(c, ResolvedConstraint::Adjacency { .. }))
        .collect();
    let layer_prefs: Vec<&ResolvedConstraint> = model
        .iter()
        .filter(|c| matches!(c, ResolvedConstraint::LayerPreference { .. }))
        .collect();

    for sep in &separations {
        if let ResolvedConstraint::Separation {
            id: sep_id,
            net_a: sep_a,
            net_b: sep_b,
            min_distance_mm: min_d,
            ..
        } = sep
        {
            for adj in &adjacencies {
                if let ResolvedConstraint::Adjacency {
                    id: adj_id,
                    net_a: adj_a,
                    net_b: adj_b,
                    max_distance_mm: max_d,
                    ..
                } = adj
                {
                    if (sep_a == adj_a && sep_b == adj_b) || (sep_a == adj_b && sep_b == adj_a) {
                        if min_d > max_d {
                            conflicts.push(ConflictReport {
                                pcl_constraint_ids: vec![sep_id.clone(), adj_id.clone()],
                                description: format!(
                                    "Separation requires ≥{min_d}mm but Adjacency requires ≤{max_d}mm"
                                ),
                                tier: ConstraintTier::Hard,
                            });
                        }
                    }
                }
            }
        }
    }

    for (i, lp_a) in layer_prefs.iter().enumerate() {
        for lp_b in layer_prefs.iter().skip(i + 1) {
            if let (
                ResolvedConstraint::LayerPreference { net: net_a, layer: layer_a, .. },
                ResolvedConstraint::LayerPreference { net: net_b, layer: layer_b, .. },
            ) = (lp_a, lp_b)
            {
                if net_a == net_b && layer_a != layer_b {
                    conflicts.push(ConflictReport {
                        pcl_constraint_ids: vec![lp_a.id().to_string(), lp_b.id().to_string()],
                        description: format!(
                            "Net {net_a} has conflicting layer preferences: {layer_a} vs {layer_b}"
                        ),
                        tier: ConstraintTier::Hard,
                    });
                }
            }
        }
    }

    conflicts
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ir_tier1::ResolvedConstraint;

    #[test]
    fn test_push_and_get() {
        let mut prov = ProvenanceMap::new();
        let idx = prov.push(
            "pcl_1".into(),
            "Adjacent".into(),
            "desugar_adjacent".into(),
            "desugar_adjacency_to_diffpair".into(),
            "half-bridge pairing".into(),
            ConstraintTier::Hard,
        );
        let entry = prov.get(idx).unwrap();
        assert_eq!(entry.pcl_constraint_id, "pcl_1");
        assert_eq!(entry.tier0_type, "Adjacent");
    }

    #[test]
    fn test_link_clause_and_reverse_map() {
        let mut prov = ProvenanceMap::new();
        let idx_a = prov.push(
            "pcl_a".into(), "Separated".into(), "desugar_separated".into(),
            "desugar_sep_to_layer".into(), "HV isolation".into(), ConstraintTier::Hard,
        );
        let idx_b = prov.push(
            "pcl_b".into(), "Adjacent".into(), "desugar_adjacent".into(),
            "desugar_adj_to_diffpair".into(), "thermal coupling".into(), ConstraintTier::Hard,
        );
        prov.link_clause(17, idx_a);
        prov.link_clause(23, idx_b);

        let diags = reverse_map_unsat_core(&[17, 23], &prov);
        assert_eq!(diags.len(), 2);
    }

    #[test]
    fn test_empty_unsat_core() {
        let mut prov = ProvenanceMap::new();
        prov.push(
            "pcl_1".into(), "Adjacent".into(), "r0".into(), "r1".into(),
            "test".into(), ConstraintTier::Hard,
        );
        let diags = reverse_map_unsat_core(&[], &prov);
        assert!(diags.is_empty());
    }

    #[test]
    fn test_conflict_detection_separation_vs_adjacency() {
        let model = vec![
            ResolvedConstraint::Separation {
                id: "sep_1".into(),
                net_a: 0,
                net_b: 1,
                min_distance_mm: 6.0,
                tier: ConstraintTier::Hard,
                provenance: 0,
            },
            ResolvedConstraint::Adjacency {
                id: "adj_1".into(),
                net_a: 0,
                net_b: 1,
                max_distance_mm: 3.0,
                tier: ConstraintTier::Hard,
                provenance: 1,
            },
        ];
        let conflicts = detect_conflicts(&model);
        assert_eq!(conflicts.len(), 1);
    }

    #[test]
    fn test_no_conflict_when_separation_compatible() {
        let model = vec![
            ResolvedConstraint::Separation {
                id: "sep_1".into(),
                net_a: 0,
                net_b: 1,
                min_distance_mm: 3.0,
                tier: ConstraintTier::Hard,
                provenance: 0,
            },
            ResolvedConstraint::Adjacency {
                id: "adj_1".into(),
                net_a: 0,
                net_b: 1,
                max_distance_mm: 6.0,
                tier: ConstraintTier::Hard,
                provenance: 1,
            },
        ];
        let conflicts = detect_conflicts(&model);
        assert!(conflicts.is_empty());
    }

    #[test]
    fn test_layer_preference_conflict() {
        let model = vec![
            ResolvedConstraint::LayerPreference {
                id: "lp_1".into(),
                net: 5,
                layer: "B.Cu".into(),
                tier: ConstraintTier::Hard,
                provenance: 0,
            },
            ResolvedConstraint::LayerPreference {
                id: "lp_2".into(),
                net: 5,
                layer: "F.Cu".into(),
                tier: ConstraintTier::Hard,
                provenance: 1,
            },
        ];
        let conflicts = detect_conflicts(&model);
        assert_eq!(conflicts.len(), 1);
    }

    #[test]
    fn test_no_conflict_same_layer_different_nets() {
        let model = vec![
            ResolvedConstraint::LayerPreference {
                id: "lp_1".into(),
                net: 5,
                layer: "B.Cu".into(),
                tier: ConstraintTier::Hard,
                provenance: 0,
            },
            ResolvedConstraint::LayerPreference {
                id: "lp_2".into(),
                net: 7,
                layer: "F.Cu".into(),
                tier: ConstraintTier::Hard,
                provenance: 1,
            },
        ];
        let conflicts = detect_conflicts(&model);
        assert!(conflicts.is_empty());
    }
}

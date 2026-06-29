// UNSAT core reverse-mapping — clause indices → structured ConflictReport.
//
// Origin: U4 of docs/plans/2026-06-28-003-feat-unsat-provenance-tension-detection-plan.md

use std::collections::BTreeSet;

use crate::types::{
    ClauseOrigin, ConflictReport, InternalConstraint, InternalConstraintModel,
    SatVariable,
};

/// Build a human-readable conflict report from UNSAT core clause indices.
///
/// Reverse-maps `core_indices` through the `provenance` table to identify
/// which constraints generated the conflicting clauses, which channels
/// are involved, and produce a human-readable explanation.
pub fn build_conflict_report(
    core_indices: &[usize],
    provenance: &[ClauseOrigin],
    model: &InternalConstraintModel,
    _var_map: &[SatVariable],
) -> ConflictReport {
    if core_indices.is_empty() {
        return ConflictReport {
            conflicting_constraints: Vec::new(),
            channels_involved: Vec::new(),
            explanation: "UNSAT core extraction failed — no clause-level diagnostics available"
                .to_string(),
            core_clause_count: 0,
        };
    }

    // Deduplicate constraints referenced by core clauses.
    let mut unique_constraints: BTreeSet<usize> = BTreeSet::new();
    for &ci in core_indices {
        if ci >= provenance.len() {
            continue;
        }
        let origin = provenance[ci];
        unique_constraints.insert(origin.constraint_idx as usize);
    }

    // Build conflicting_constraints list with labels.
    let mut conflicting_constraints: Vec<(usize, String)> = Vec::new();
    let mut channels_involved: Vec<String> = Vec::new();
    let mut channel_set: std::collections::HashSet<String> = std::collections::HashSet::new();

    for idx in &unique_constraints {
        if *idx >= model.constraints.len() {
            continue;
        }
        let label = constraint_label(*idx, &model.constraints[*idx]);
        conflicting_constraints.push((*idx, label));

        let ch = constraint_channel(&model.constraints[*idx]);
        if !ch.is_empty() && channel_set.insert(ch.clone()) {
            channels_involved.push(ch);
        }
    }

    let explanation = explain_core(&unique_constraints, model);

    ConflictReport {
        conflicting_constraints,
        channels_involved,
        explanation,
        core_clause_count: core_indices.len(),
    }
}

/// Produce a human-readable label for a constraint.
fn constraint_label(idx: usize, c: &InternalConstraint) -> String {
    match c {
        InternalConstraint::Capacity {
            channel_id,
            capacity,
            slack_factor,
            terms,
        } => {
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
            format!("Capacity[{idx}]:{channel_id}≤{max_nets}")
        }
        InternalConstraint::DiffPair {
            channel_id,
            p_var_name,
            n_var_name,
        } => {
            format!("DiffPair[{idx}]:{p_var_name},{n_var_name}@{channel_id}")
        }
        InternalConstraint::LayerRestriction { var_name, allowed } => {
            let ch = parse_channel_id(var_name).unwrap_or("?");
            format!("LayerRestriction[{idx}]:{ch}:{allowed}")
        }
    }
}

/// Extract the channel_id from a constraint (for the channels_involved field).
fn constraint_channel(c: &InternalConstraint) -> String {
    match c {
        InternalConstraint::Capacity { channel_id, .. } => channel_id.clone(),
        InternalConstraint::DiffPair { channel_id, .. } => channel_id.clone(),
        InternalConstraint::LayerRestriction { var_name, .. } => {
            parse_channel_id(var_name).unwrap_or("?").to_string()
        }
    }
}

/// Parse channel_id from a var_name of the form `uses_N{net_idx}_{channel_id}`.
fn parse_channel_id(var_name: &str) -> Option<&str> {
    if !var_name.starts_with("uses_N") {
        return None;
    }
    let after_uses_n = &var_name[5..];
    after_uses_n.find('_').map(|uscore_pos| &after_uses_n[uscore_pos + 1..])
}

/// Generate a human-readable explanation from the set of conflicting constraints.
fn explain_core(
    unique_constraints: &BTreeSet<usize>,
    model: &InternalConstraintModel,
) -> String {
    if unique_constraints.is_empty() {
        return "UNSAT core contains no recognized constraints".to_string();
    }

    let mut has_capacity = false;
    let mut has_diffpair = false;
    let mut has_layer = false;
    let mut capacity_constraints: Vec<&InternalConstraint> = Vec::new();
    let mut diffpair_constraints: Vec<&InternalConstraint> = Vec::new();

    for idx in unique_constraints {
        if *idx >= model.constraints.len() {
            continue;
        }
        match &model.constraints[*idx] {
            InternalConstraint::Capacity { .. } => {
                has_capacity = true;
                capacity_constraints.push(&model.constraints[*idx]);
            }
            InternalConstraint::DiffPair { .. } => {
                has_diffpair = true;
                diffpair_constraints.push(&model.constraints[*idx]);
            }
            InternalConstraint::LayerRestriction { .. } => {
                has_layer = true;
            }
        }
    }

    if has_diffpair && has_capacity {
        let dp = &diffpair_constraints[0];
        let cap = &capacity_constraints[0];
        if let (
            InternalConstraint::DiffPair {
                p_var_name,
                n_var_name,
                channel_id,
            },
            InternalConstraint::Capacity {
                channel_id: cap_ch,
                capacity,
                slack_factor,
                terms,
            },
        ) = (dp, cap)
        {
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
            return format!(
                "Diff pair requires both {p_var_name} and {n_var_name} on channel {channel_id}, \
                 but capacity '{cap_ch}' limits {channel_id} to {max_nets} nets"
            );
        }
        return format!(
            "Diff pair requires both nets on the same channel, but channel capacity is insufficient"
        );
    }

    if has_capacity && has_layer {
        if let Some(InternalConstraint::Capacity {
            channel_id, capacity, slack_factor, terms,
        }) = capacity_constraints.first()
        {
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
            return format!(
                "Capacity constraint limits channel {channel_id} to {max_nets} nets, but layer \
                 restrictions force additional nets to use {channel_id} — capacity exceeded"
            );
        }
    }

    if has_capacity {
        if let Some(InternalConstraint::Capacity {
            channel_id, capacity, slack_factor, terms,
        }) = capacity_constraints.first()
        {
            let min_width = terms
                .iter()
                .map(|(_, w)| *w)
                .fold(f64::INFINITY, f64::min);
            let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
            return format!(
                "Channel {channel_id} capacity ({max_nets}) exceeded — core contains \
                 {} clauses",
                unique_constraints.len()
            );
        }
        return format!("Capacity exceeded (core contains {} clauses)", unique_constraints.len());
    }

    if has_diffpair && unique_constraints.len() == 1 {
        return "Diff pair mismatch — the two nets must share the same channel assignment"
            .to_string();
    }

    format!(
        "UNSAT core involves {} constraints across {} channels",
        unique_constraints.len(),
        {
            let mut chs: std::collections::HashSet<String> = std::collections::HashSet::new();
            for idx in unique_constraints {
                if *idx < model.constraints.len() {
                    let ch = constraint_channel(&model.constraints[*idx]);
                    if !ch.is_empty() {
                        chs.insert(ch);
                    }
                }
            }
            chs.len()
        }
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{ClauseOrigin, ClauseRole, InternalConstraint, InternalConstraintModel, InternalVariable, SatVariable};

    fn make_model(
        vars: Vec<InternalVariable>,
        constraints: Vec<InternalConstraint>,
    ) -> InternalConstraintModel {
        InternalConstraintModel {
            variables: vars,
            constraints,
        }
    }

    fn make_var(name: &str, idx: usize, ch: &str) -> InternalVariable {
        InternalVariable::NetChannel {
            name: name.to_string(),
            net_idx: idx,
            channel_id: ch.to_string(),
        }
    }

    #[test]
    fn empty_core_returns_extraction_failed() {
        let vars = vec![make_var("x", 0, "CH1")];
        let cons = vec![InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 1.0,
            slack_factor: 1.0,
            terms: vec![("x".into(), 1.0)],
        }];
        let model = make_model(vars, cons);
        let var_map = vec![SatVariable::new("x", "")];
        let report = build_conflict_report(&[], &[], &model, &var_map);
        assert_eq!(report.core_clause_count, 0);
        assert!(report.explanation.contains("failed"));
    }

    #[test]
    fn single_capacity_core_maps_correctly() {
        let vars = vec![make_var("x", 0, "CH1")];
        let cons = vec![InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 1.0,
            slack_factor: 1.0,
            terms: vec![("x".into(), 1.0)],
        }];
        let model = make_model(vars, cons);
        let var_map = vec![SatVariable::new("x", "")];
        let provenance = vec![ClauseOrigin::new(0, ClauseRole::CardinalityCounter, 0)];
        let report = build_conflict_report(&[0], &provenance, &model, &var_map);
        assert_eq!(report.conflicting_constraints.len(), 1);
        assert_eq!(report.core_clause_count, 1);
        assert_eq!(report.channels_involved.len(), 1);
        assert_eq!(report.channels_involved[0], "CH1");
    }

    #[test]
    fn core_spanning_capacity_and_diffpair() {
        let vars = vec![
            make_var("p_CH1", 0, "CH1"),
            make_var("n_CH1", 1, "CH1"),
        ];
        let cons = vec![
            InternalConstraint::DiffPair {
                channel_id: "CH1".into(),
                p_var_name: "p_CH1".into(),
                n_var_name: "n_CH1".into(),
            },
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 1.0,
                slack_factor: 1.0,
                terms: vec![("p_CH1".into(), 1.0), ("n_CH1".into(), 1.0)],
            },
        ];
        let model = make_model(vars, cons);
        let var_map = vec![
            SatVariable::new("p_CH1", ""),
            SatVariable::new("n_CH1", ""),
        ];
        let provenance = vec![
            ClauseOrigin::new(0, ClauseRole::ConstraintLiteral, 255),
            ClauseOrigin::new(0, ClauseRole::ConstraintLiteral, 255),
            ClauseOrigin::new(1, ClauseRole::CardinalityExclusion, 0),
            ClauseOrigin::new(1, ClauseRole::CardinalityCounter, 0),
        ];
        let report = build_conflict_report(&[0, 2, 3], &provenance, &model, &var_map);
        assert_eq!(report.conflicting_constraints.len(), 2);
        assert!(report.explanation.contains("Diff pair"));
        assert!(report.explanation.contains("capacity"));
        assert_eq!(report.channels_involved.len(), 1);
        assert_eq!(report.channels_involved[0], "CH1");
    }

    #[test]
    fn core_index_out_of_bounds_skipped_gracefully() {
        let vars = vec![make_var("x", 0, "CH1")];
        let cons = vec![InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 1.0,
            slack_factor: 1.0,
            terms: vec![("x".into(), 1.0)],
        }];
        let model = make_model(vars, cons);
        let var_map = vec![SatVariable::new("x", "")];
        let provenance = vec![ClauseOrigin::new(0, ClauseRole::Unit, 255)];
        let report = build_conflict_report(&[0, 999], &provenance, &model, &var_map);
        assert_eq!(report.conflicting_constraints.len(), 1);
    }

    #[test]
    fn layer_restriction_in_core() {
        let vars = vec![make_var("uses_N0_L1", 0, "L1")];
        let cons = vec![InternalConstraint::LayerRestriction {
            var_name: "uses_N0_L1".into(),
            allowed: false,
        }];
        let model = make_model(vars, cons);
        let var_map = vec![SatVariable::new("uses_N0_L1", "")];
        let provenance = vec![ClauseOrigin::new(0, ClauseRole::Unit, 255)];
        let report = build_conflict_report(&[0], &provenance, &model, &var_map);
        assert_eq!(report.conflicting_constraints.len(), 1);
        assert_eq!(report.channels_involved.len(), 1);
        assert!(report.channels_involved[0].contains("L1"));
    }
}

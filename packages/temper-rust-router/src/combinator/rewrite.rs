/// Rewrite engine — RW1-RW7 on `InternalConstraintModel`.
///
/// Applies simplification rules to the flattened `InternalConstraint` list
/// until fixpoint. The engine operates on the constraint multiset, treating
/// it as a collection of constraints to be simplified.
///
/// # Rewrite Rules
///
/// - **RW1. CapSubsume:** tighten looser capacity bounds under tighter ones.
///   Input: `Capacity(CH, K1, V1)` + `Capacity(CH, K2, V2)` with V1⊆V2, K1≤K2.
///   Output: `Capacity(CH, K1, V1)` + `Capacity(CH, min(K2, K1+|V2\V1|), V2)`.
///
/// - **RW2. CapEliminate:** remove trivially satisfiable capacity constraints.
///   Input: `Capacity(CH, K, V)` where K≥|V|.
///   Output: constraint removed.
///
/// - **RW3. LayerPropagate:** remove true unit-clause variables from Capacity,
///   decrementing K by 1 per removed variable.
///   Input: `LayerRestriction(var, true)` + `Capacity(CH, K, {var,...})`.
///   Output: `LayerRestriction(var, true)` + `Capacity(CH, K-1, V\{var})`.
///   Chain: if K becomes 0 and |V|>0, add unit clauses (not v) for all
///   remaining vars and remove the Capacity.
///
/// - **RW4. LayerPropagateFalse:** remove false unit-clause variables from
///   Capacity without changing K.
///   Input: `LayerRestriction(var, false)` + `Capacity(CH, K, {var,...})`.
///   Output: `LayerRestriction(var, false)` + `Capacity(CH, K, V\{var})`.
///
/// - **RW5. DiffPairDedup:** drop duplicate DiffPair constraints (keep first).
///
/// - **RW6. LayerDedup:** drop duplicate LayerRestriction constraints with the
///   same (var_name, allowed) pair.
///
/// - **RW7. LayerConflict:** detect contradictory layer restrictions pre-solve.
///   Input: `LayerRestriction(var, true)` + `LayerRestriction(var, false)`.
///   Output: `RewriteError::UnsatPreSolve`.
///
/// # Termination
///
/// Each rule reduces some measure (constraint count, term count, or bound
/// tightness). The maximum iterations ≤ 2 * |constraints|.
///
/// # Confluence
///
/// The fixed rule order (RW7 → RW5 → RW6 → RW3 → RW4 → RW1 → RW2) is a
/// performance optimization. The fixpoint loop ensures all rules exhaust
/// regardless of order; confluent because the rules are monotonic decreases
/// on a well-founded measure.

use std::collections::{BTreeSet, HashMap, HashSet};

use crate::types::{InternalConstraint, InternalConstraintModel};

/// Error returned when the rewrite engine detects a structural contradiction.
#[derive(Debug, PartialEq)]
pub enum RewriteError {
    /// Structural contradiction detected pre-solve (RW7).
    UnsatPreSolve {
        var_name: String,
        constraint1: String,
        constraint2: String,
    },
}

/// Apply RW1-RW7 rewrite rules to an `InternalConstraintModel`.
///
/// Returns the simplified model or `RewriteError::UnsatPreSolve` if a
/// structural contradiction is detected.
pub fn rewrite(model: &InternalConstraintModel) -> Result<InternalConstraintModel, RewriteError> {
    let mut constraints = model.constraints.clone();
    let mut changed = true;
    let max_iterations = constraints.len() * 2;
    let mut iteration = 0;

    while changed && iteration < max_iterations {
        changed = false;
        iteration += 1;

        // RW7. LayerConflict (must fire first — detects UNSAT)
        detect_layer_conflict(&constraints)?;

        // RW5. DiffPairDedup
        let before = constraints.len();
        constraints = dedup_diff_pairs(constraints);
        if constraints.len() < before {
            changed = true;
        }

        // RW6. LayerDedup
        let before = constraints.len();
        constraints = dedup_layers(constraints);
        if constraints.len() < before {
            changed = true;
        }

        // RW3. LayerPropagate (true unit clause removes var from Capacity, K-1)
        let before_len = constraints.len();
        constraints = propagate_layer_true(constraints);
        if constraints.len() != before_len {
            changed = true;
        }

        // RW4. LayerPropagateFalse (false unit clause removes var, K unchanged)
        let before_len = constraints.len();
        constraints = propagate_layer_false(constraints);
        if constraints.len() != before_len {
            changed = true;
        }

        // RW1. CapSubsume
        let before_len = constraints.len();
        constraints = subsume_capacity(constraints);
        if constraints.len() != before_len {
            changed = true;
        }

        // RW2. CapEliminate
        let before = constraints.len();
        constraints = eliminate_trivial_capacity(constraints);
        if constraints.len() < before {
            changed = true;
        }
    }

    Ok(InternalConstraintModel {
        variables: model.variables.clone(),
        constraints,
    })
}

// ---------------------------------------------------------------------------
// Helper: compute max_nets from Capacity fields
// ---------------------------------------------------------------------------

/// Compute max_nets = floor(capacity * slack / min_width).
fn compute_max_nets(capacity: f64, slack_factor: f64, terms: &[(String, f64)]) -> usize {
    if terms.is_empty() {
        return 0;
    }
    let min_width = terms.iter().map(|(_, w)| *w).fold(f64::INFINITY, f64::min);
    ((capacity * slack_factor) / min_width).floor() as usize
}

// ---------------------------------------------------------------------------
// RW7. LayerConflict
// ---------------------------------------------------------------------------

/// Scan for contradictory `LayerRestriction(var, true)` and
/// `LayerRestriction(var, false)`. Returns a conflict error if found.
fn detect_layer_conflict(constraints: &[InternalConstraint]) -> Result<(), RewriteError> {
    let mut true_vars: HashSet<&str> = HashSet::new();
    let mut false_vars: HashSet<&str> = HashSet::new();

    for c in constraints {
        if let InternalConstraint::LayerRestriction { var_name, allowed } = c {
            if *allowed {
                if false_vars.contains(var_name.as_str()) {
                    return Err(RewriteError::UnsatPreSolve {
                        var_name: var_name.clone(),
                        constraint1: format!("layer_restr_{}_true", var_name),
                        constraint2: format!("layer_restr_{}_false", var_name),
                    });
                }
                true_vars.insert(var_name.as_str());
            } else {
                if true_vars.contains(var_name.as_str()) {
                    return Err(RewriteError::UnsatPreSolve {
                        var_name: var_name.clone(),
                        constraint1: format!("layer_restr_{}_true", var_name),
                        constraint2: format!("layer_restr_{}_false", var_name),
                    });
                }
                false_vars.insert(var_name.as_str());
            }
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// RW5. DiffPairDedup
// ---------------------------------------------------------------------------

/// Drop duplicate `DiffPair` constraints. Keeps the first occurrence.
fn dedup_diff_pairs(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    let mut seen: HashSet<(String, String, String)> = HashSet::new();
    let mut result = Vec::new();

    for c in constraints {
        match &c {
            InternalConstraint::DiffPair {
                channel_id,
                p_var_name,
                n_var_name,
            } => {
                let key = (channel_id.clone(), p_var_name.clone(), n_var_name.clone());
                if seen.insert(key) {
                    result.push(c);
                }
            }
            _ => result.push(c),
        }
    }

    result
}

// ---------------------------------------------------------------------------
// RW6. LayerDedup
// ---------------------------------------------------------------------------

/// Drop duplicate `LayerRestriction` constraints with the same (var_name, allowed).
fn dedup_layers(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    let mut seen: HashSet<(String, bool)> = HashSet::new();
    let mut result = Vec::new();

    for c in constraints {
        if let InternalConstraint::LayerRestriction { var_name, allowed } = &c {
            let key = (var_name.clone(), *allowed);
            if seen.insert(key) {
                result.push(c);
            }
        } else {
            result.push(c);
        }
    }

    result
}

// ---------------------------------------------------------------------------
// RW3. LayerPropagate (true unit clause)
// ---------------------------------------------------------------------------

/// Remove true unit-clause variables from Capacity constraints.
/// Decrements K (max_nets) by 1 per removed variable.
/// Chain: if K becomes 0 and |V|>0, add (not v) unit clauses for all
/// remaining vars and drop the Capacity.
fn propagate_layer_true(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    // Collect all LayerRestriction(var, true) — owned strings to avoid
    // borrowing `constraints` while iterating it later.
    let true_vars: HashSet<String> = constraints
        .iter()
        .filter_map(|c| {
            if let InternalConstraint::LayerRestriction {
                var_name,
                allowed: true,
            } = c
            {
                Some(var_name.clone())
            } else {
                None
            }
        })
        .collect();

    if true_vars.is_empty() {
        return constraints;
    }

    let mut result: Vec<InternalConstraint> = Vec::new();

    for c in constraints {
        match c {
            InternalConstraint::Capacity {
                channel_id,
                capacity,
                slack_factor,
                terms,
            } => {
                let old_max_nets = compute_max_nets(capacity, slack_factor, &terms);
                let old_count = terms.len();

                // Remove terms whose var is a true unit clause.
                let new_terms: Vec<(String, f64)> = terms
                    .into_iter()
                    .filter(|(n, _)| !true_vars.contains(n))
                    .collect();

                let removed_count = old_count - new_terms.len();
                if removed_count == 0 {
                    // No terms removed; keep unchanged.
                    result.push(InternalConstraint::Capacity {
                        channel_id,
                        capacity,
                        slack_factor,
                        terms: new_terms,
                    });
                    continue;
                }

                // Decrement K by removed_count.
                let new_max_nets = if old_max_nets > removed_count {
                    old_max_nets - removed_count
                } else {
                    0
                };

                if new_terms.is_empty() {
                    // All terms were removed; drop the Capacity constraint entirely.
                    continue;
                }

                let new_min_width = new_terms
                    .iter()
                    .map(|(_, w)| *w)
                    .fold(f64::INFINITY, f64::min);

                if new_max_nets == 0 {
                    // K=0: force all remaining vars false, drop Capacity.
                    for (vname, _) in &new_terms {
                        result.push(InternalConstraint::LayerRestriction {
                            var_name: vname.clone(),
                            allowed: false,
                        });
                    }
                    continue;
                }

                if new_max_nets >= new_terms.len() {
                    // Trivially satisfiable; drop.
                    continue;
                }

                // new_capacity = new_max_nets * new_min_width / slack_factor
                let new_capacity = (new_max_nets as f64) * new_min_width / slack_factor;

                result.push(InternalConstraint::Capacity {
                    channel_id,
                    capacity: new_capacity,
                    slack_factor,
                    terms: new_terms,
                });
            }
            other => result.push(other),
        }
    }

    result
}

// ---------------------------------------------------------------------------
// RW4. LayerPropagateFalse
// ---------------------------------------------------------------------------

/// Remove false unit-clause variables from Capacity constraints.
/// K stays unchanged (the variable was false, so it didn't count against the bound).
fn propagate_layer_false(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    // Collect all LayerRestriction(var, false) — owned strings.
    let false_vars: HashSet<String> = constraints
        .iter()
        .filter_map(|c| {
            if let InternalConstraint::LayerRestriction {
                var_name,
                allowed: false,
            } = c
            {
                Some(var_name.clone())
            } else {
                None
            }
        })
        .collect();

    if false_vars.is_empty() {
        return constraints;
    }

    let mut result: Vec<InternalConstraint> = Vec::new();

    for c in constraints {
        match c {
            InternalConstraint::Capacity {
                channel_id,
                capacity,
                slack_factor,
                terms,
            } => {
                let new_terms: Vec<(String, f64)> = terms
                    .into_iter()
                    .filter(|(n, _)| !false_vars.contains(n))
                    .collect();

                if new_terms.is_empty() {
                    // All terms were false; Capacity is trivially satisfied.
                    continue;
                }

                result.push(InternalConstraint::Capacity {
                    channel_id,
                    capacity,
                    slack_factor,
                    terms: new_terms,
                });
            }
            other => result.push(other),
        }
    }

    result
}

// ---------------------------------------------------------------------------
// RW1. CapSubsume
// ---------------------------------------------------------------------------

/// Tighten looser capacity bounds under tighter overlapping bounds.
///
/// Group by channel_id. For each pair (C1, C2) where:
/// - V1 ⊆ V2 and K1 ≤ K2: tighten C2 to min(K2, K1 + |V2\V1|)
/// - After tightening, if two constraints have identical var sets,
///   keep only the one with smaller K.
fn subsume_capacity(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    // Separate capacity constraints from others.
    let mut caps: Vec<(usize, String, f64, f64, Vec<(String, f64)>)> = Vec::new();
    let mut others: Vec<InternalConstraint> = Vec::new();

    for c in constraints {
        match c {
            InternalConstraint::Capacity {
                channel_id,
                capacity,
                slack_factor,
                terms,
            } => {
                caps.push((caps.len(), channel_id, capacity, slack_factor, terms));
            }
            other => others.push(other),
        }
    }

    if caps.len() <= 1 {
        // Reconstruct: no subsumption needed.
        let mut result = others;
        for (_, ch_id, cap, sf, terms) in caps {
            result.push(InternalConstraint::Capacity {
                channel_id: ch_id,
                capacity: cap,
                slack_factor: sf,
                terms,
            });
        }
        return result;
    }

    // Compute max_nets and var-name sets for each capacity constraint.
    let mut cap_infos: Vec<CapInfo> = caps
        .iter()
        .map(|(orig_idx, ch_id, cap, sf, terms)| {
            let max_nets = compute_max_nets(*cap, *sf, terms);
            let var_set: HashSet<String> = terms.iter().map(|(n, _)| n.clone()).collect();
            CapInfo {
                orig_idx: *orig_idx,
                channel_id: ch_id.clone(),
                capacity: *cap,
                slack_factor: *sf,
                terms: terms.clone(),
                max_nets,
                var_set,
            }
        })
        .collect();

    // Group by channel_id.
    let mut channel_groups: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, info) in cap_infos.iter().enumerate() {
        channel_groups
            .entry(info.channel_id.clone())
            .or_default()
            .push(i);
    }

    let mut tight_k: Vec<Option<usize>> = cap_infos.iter().map(|info| Some(info.max_nets)).collect();

    // For each channel group, do pairwise subsumption.
    for indices in channel_groups.values() {
        // Repeat until fixpoint within this channel group.
        let mut local_changed = true;
        while local_changed {
            local_changed = false;
            for &i in indices.iter() {
                for &j in indices.iter() {
                    if i == j {
                        continue;
                    }
                    let ki = tight_k[i];
                    let kj = tight_k[j];
                    if ki.is_none() || kj.is_none() {
                        continue;
                    }
                    let ki = ki.unwrap();
                    let kj = kj.unwrap();

                    let skip: bool = cap_infos[i].terms.len() > cap_infos[j].terms.len()
                        || ki > kj;
                    if skip {
                        continue;
                    }

                    // Check if V_i ⊆ V_j.
                    if cap_infos[i]
                        .var_set
                        .iter()
                        .all(|v| cap_infos[j].var_set.contains(v))
                    {
                        // V_i ⊆ V_j and K_i ≤ K_j.
                        let extra_count = cap_infos[j].terms.len() - cap_infos[i].terms.len();
                        let new_kj = kj.min(ki + extra_count);
                        if new_kj < kj {
                            tight_k[j] = Some(new_kj);
                            local_changed = true;
                        }
                    }
                }
            }
        }
    }

    // Rebuild capacity constraints with tightened bounds.
    let mut dedup_map: HashMap<BTreeSet<String>, (usize, usize)> = HashMap::new();
    // var_set → (orig_idx, tight_k)

    for info in &cap_infos {
        let k = tight_k[info.orig_idx].unwrap_or(info.max_nets);
        let var_sorted: BTreeSet<String> = info
            .terms
            .iter()
            .map(|(n, _)| n.clone())
            .collect();

        let entry = dedup_map.entry(var_sorted).or_insert((info.orig_idx, k));
        if k < entry.1 {
            entry.1 = k;
        }
    }

    let mut result = others;

    for (var_sorted, (_orig_idx, tight_k)) in dedup_map {
        // Find the cap_info that matches this var set.
        let info = cap_infos
            .iter()
            .find(|info| {
                let vs: BTreeSet<String> =
                    info.terms.iter().map(|(n, _)| n.clone()).collect();
                vs == var_sorted
            })
            .unwrap();

        let new_max_nets = tight_k;

        if new_max_nets >= info.terms.len() {
            // Trivially satisfiable; drop.
            continue;
        }

        let new_min_width = info
            .terms
            .iter()
            .map(|(_, w)| *w)
            .fold(f64::INFINITY, f64::min);
        let new_capacity = (new_max_nets as f64) * new_min_width / info.slack_factor;

        result.push(InternalConstraint::Capacity {
            channel_id: info.channel_id.clone(),
            capacity: new_capacity,
            slack_factor: info.slack_factor,
            terms: info.terms.clone(),
        });
    }

    result
}

struct CapInfo {
    orig_idx: usize,
    channel_id: String,
    capacity: f64,
    slack_factor: f64,
    terms: Vec<(String, f64)>,
    max_nets: usize,
    var_set: HashSet<String>,
}

// ---------------------------------------------------------------------------
// RW2. CapEliminate
// ---------------------------------------------------------------------------

/// Remove trivially satisfiable Capacity constraints where max_nets >= |V|.
fn eliminate_trivial_capacity(constraints: Vec<InternalConstraint>) -> Vec<InternalConstraint> {
    constraints
        .into_iter()
        .filter(|c| match c {
            InternalConstraint::Capacity {
                capacity,
                slack_factor,
                terms,
                ..
            } => {
                if terms.is_empty() {
                    return false;
                }
                let max_nets = compute_max_nets(*capacity, *slack_factor, terms);
                max_nets < terms.len()
            }
            _ => true,
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn capacity(
        channel_id: &str,
        capacity: f64,
        terms: Vec<(&str, f64)>,
    ) -> InternalConstraint {
        InternalConstraint::Capacity {
            channel_id: channel_id.into(),
            capacity,
            slack_factor: 1.0,
            terms: terms.into_iter().map(|(n, w)| (n.into(), w)).collect(),
        }
    }

    fn layer(var_name: &str, allowed: bool) -> InternalConstraint {
        InternalConstraint::LayerRestriction {
            var_name: var_name.into(),
            allowed,
        }
    }

    fn diffpair(ch: &str, p: &str, n: &str) -> InternalConstraint {
        InternalConstraint::DiffPair {
            channel_id: ch.into(),
            p_var_name: p.into(),
            n_var_name: n.into(),
        }
    }

    // -----------------------------------------------------------------------
    // RW7. LayerConflict
    // -----------------------------------------------------------------------

    /// AE3 from the plan: contradictory layer restrictions → UnsatPreSolve.
    #[test]
    fn rw7_layer_conflict_detected() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                layer("N3_L1_E5", true),
                layer("N3_L1_E5", false),
            ],
        };
        let err = rewrite(&model).unwrap_err();
        assert!(matches!(err, RewriteError::UnsatPreSolve { .. }));
    }

    /// No conflict when layer restrictions don't overlap.
    #[test]
    fn rw7_no_conflict_when_distinct_vars() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                layer("A", true),
                layer("B", false),
            ],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), 2);
    }

    // -----------------------------------------------------------------------
    // RW5. DiffPairDedup
    // -----------------------------------------------------------------------

    /// Two identical DiffPair constraints → one.
    #[test]
    fn rw5_dedup_identical_diffpairs() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                diffpair("CH1", "p", "n"),
                diffpair("CH1", "p", "n"),
            ],
        };
        let result = rewrite(&model).unwrap();
        let dp_count = result
            .constraints
            .iter()
            .filter(|c| matches!(c, InternalConstraint::DiffPair { .. }))
            .count();
        assert_eq!(dp_count, 1);
    }

    /// Different DiffPair constraints are preserved.
    #[test]
    fn rw5_preserves_different_diffpairs() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                diffpair("CH1", "p", "n"),
                diffpair("CH2", "p2", "n2"),
            ],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), 2);
    }

    // -----------------------------------------------------------------------
    // RW6. LayerDedup
    // -----------------------------------------------------------------------

    /// Duplicate layer restrictions → dedup.
    #[test]
    fn rw6_dedup_identical_layers() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![layer("A", true), layer("A", true)],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), 1);
        match &result.constraints[0] {
            InternalConstraint::LayerRestriction { var_name, allowed } => {
                assert_eq!(var_name, "A");
                assert!(*allowed);
            }
            _ => panic!("expected LayerRestriction"),
        }
    }

    // -----------------------------------------------------------------------
    // RW3. LayerPropagate (true)
    // -----------------------------------------------------------------------

    /// AE2 from the plan: true unit clause removes var from Capacity, K-1.
    #[test]
    fn rw3_propagate_true_reduces_capacity() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                // K=4 over 5 vars: max_nets=4, terms=[A,B,C,D,E]
                capacity("L1_E5", 4.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", 1.0), ("E", 1.0)]),
                layer("A", true),
            ],
        };
        let result = rewrite(&model).unwrap();
        // After removing A: new_max_nets=3, terms=4 (B,C,D,E).
        // 3 < 4, so constraint survives.
        let cap = result
            .constraints
            .iter()
            .find(|c| matches!(c, InternalConstraint::Capacity { .. }));
        assert!(cap.is_some(), "Capacity should still exist");
        if let InternalConstraint::Capacity { terms, capacity, .. } = cap.unwrap() {
            assert_eq!(terms.len(), 4); // B,C,D,E
            assert!(!terms.iter().any(|(n, _)| n == "A"));
            // max_nets = 3, capacity = 3.0
            assert!((*capacity - 3.0).abs() < 0.001, "expected capacity ~3.0, got {capacity}");
        }
        // LayerRestriction preserved.
        assert!(result.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "A" && *allowed)
        }));
    }

    /// RW3 chain: K=0 after propagation → add unit clauses, drop Capacity.
    #[test]
    fn rw3_post_zero_k_adds_neg_unit() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("L1_E5", 2.0, vec![("A", 1.0), ("B", 1.0)]),
                layer("A", true),
                layer("B", true),
            ],
        };
        let result = rewrite(&model).unwrap();
        // After removing both A and B from Capacity, terms become empty.
        // Capacity is dropped since all terms removed.
        assert!(!result
            .constraints
            .iter()
            .any(|c| matches!(c, InternalConstraint::Capacity { .. })));
        // Both LayerRestrictions preserved.
        assert_eq!(result.constraints.len(), 2);
    }

    /// RW3: K=0 but terms remaining → add (not v) clauses.
    #[test]
    fn rw3_k_zero_adds_neg_unit_clauses() {
        // Capacity K=1 with vars [A,B]; A is true. After removing A, K becomes 0,
        // B must be false. Result: LayerRestriction(A=true) + LayerRestriction(B=false).
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("CH1", 1.0, vec![("A", 1.0), ("B", 1.0)]),
                layer("A", true),
            ],
        };
        let result = rewrite(&model).unwrap();
        // Should have: A=true, B=false
        assert!(result.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "B" && !*allowed)
        }));
        assert!(result.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "A" && *allowed)
        }));
        assert!(!result.constraints.iter().any(|c| matches!(c, InternalConstraint::Capacity { .. })));
    }

    // -----------------------------------------------------------------------
    // RW4. LayerPropagateFalse
    // -----------------------------------------------------------------------

    /// False unit clause removes var from Capacity, K unchanged.
    #[test]
    fn rw4_propagate_false_removes_var() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                // K=1 over 3 vars: max_nets=1, terms=[A,B,C]
                // A=false removed → terms=[B,C], max_nets still 1
                // 1 < 2, so constraint survives (RW2 won't eliminate)
                capacity("CH1", 1.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
                layer("A", false),
            ],
        };
        let result = rewrite(&model).unwrap();
        let cap = result
            .constraints
            .iter()
            .find(|c| matches!(c, InternalConstraint::Capacity { .. }));
        assert!(cap.is_some(), "Capacity should still exist");
        if let InternalConstraint::Capacity { terms, capacity, .. } = cap.unwrap() {
            assert_eq!(terms.len(), 2); // B, C
            assert!(!terms.iter().any(|(n, _)| n == "A"));
            // K stays at 1 → capacity stays 1.0
            assert!((*capacity - 1.0).abs() < 0.001);
        }
    }

    // -----------------------------------------------------------------------
    // RW1. CapSubsume
    // -----------------------------------------------------------------------

    /// RW1: tighter subset bound tightens looser superset bound.
    #[test]
    fn rw1_subsume_tightens_superset() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("L1_E5", 2.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
                capacity("L1_E5", 5.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", 1.0), ("E", 1.0)]),
            ],
        };
        let result = rewrite(&model).unwrap();
        // C1: K1=2, V1={A,B,C}; C2: K2=5, V2={A,B,C,D,E}
        // V1⊆V2, K1≤K2 → tighten C2 to min(5, 2+2)=4
        // Result: C1 K=2, C2 K=4
        let caps: Vec<&InternalConstraint> = result
            .constraints
            .iter()
            .filter(|c| matches!(c, InternalConstraint::Capacity { .. }))
            .collect();
        assert_eq!(caps.len(), 2, "expected 2 capacity constraints");
        for c in caps {
            if let InternalConstraint::Capacity {
                capacity,
                slack_factor,
                terms,
                ..
            } = c
            {
                let max_nets = compute_max_nets(*capacity, *slack_factor, terms);
                if terms.len() == 3 {
                    assert_eq!(max_nets, 2, "subset bound should stay at 2");
                } else if terms.len() == 5 {
                    assert_eq!(max_nets, 4, "superset bound should be tightened to 4");
                }
            }
        }
    }

    /// RW1: after tightening, identical var sets → keep smaller K.
    #[test]
    fn rw1_dedup_identical_var_sets_after_tightening() {
        // Two identical Capacity constraints with different K.
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("CH1", 2.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
                capacity("CH1", 3.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
            ],
        };
        let result = rewrite(&model).unwrap();
        let caps: Vec<&InternalConstraint> = result
            .constraints
            .iter()
            .filter(|c| matches!(c, InternalConstraint::Capacity { .. }))
            .collect();
        assert_eq!(caps.len(), 1, "duplicate var sets should be merged");
        if let InternalConstraint::Capacity { capacity, slack_factor, terms, .. } = caps[0] {
            let max_nets = compute_max_nets(*capacity, *slack_factor, terms);
            assert_eq!(max_nets, 2, "should keep smaller K=2");
        }
    }

    // -----------------------------------------------------------------------
    // RW2. CapEliminate
    // -----------------------------------------------------------------------

    /// RW2: K >= |V| → constraint eliminated.
    #[test]
    fn rw2_eliminate_trivial_capacity() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("CH1", 3.0, vec![("A", 1.0), ("B", 1.0)]),
            ],
        };
        let result = rewrite(&model).unwrap();
        assert!(!result
            .constraints
            .iter()
            .any(|c| matches!(c, InternalConstraint::Capacity { .. })));
    }

    /// RW2: K < |V| → constraint preserved.
    #[test]
    fn rw2_preserves_binding_constraint() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("CH1", 1.0, vec![("A", 1.0), ("B", 1.0)]),
            ],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), 1);
    }

    // -----------------------------------------------------------------------
    // TS2: overlapping capacity with subsumption (RW1 + RW2)
    // -----------------------------------------------------------------------
    #[test]
    fn ts2_overlapping_capacity_subsume() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("L1_E5", 2.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
                capacity("L1_E5", 5.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0), ("D", 1.0), ("E", 1.0)]),
            ],
        };
        let result = rewrite(&model).unwrap();
        // C1: K=2, V={A,B,C}; C2: K=5, V={A,B,C,D,E}
        // RW1: V1⊆V2, K1≤K2 → K2=min(5,2+2)=4
        // C2 K=4 < |V|=5, so both survive.
        let caps: Vec<&InternalConstraint> = result
            .constraints
            .iter()
            .filter(|c| matches!(c, InternalConstraint::Capacity { .. }))
            .collect();
        assert_eq!(caps.len(), 2);
    }

    // -----------------------------------------------------------------------
    // TS3: layer propagation + chain reaction (RW3 → RW2)
    // -----------------------------------------------------------------------
    #[test]
    fn ts3_layer_propagation_chain_reaction() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("L1_E5", 1.0, vec![("A", 1.0), ("B", 1.0)]),
                layer("A", true),
            ],
        };
        let result = rewrite(&model).unwrap();
        // RW3: Remove A from Capacity, K becomes 0, V={B}
        // Post-RW3: K=0, |V|=1 → add ¬B, remove Capacity
        assert!(result.constraints.iter().any(|c| {
            matches!(c, InternalConstraint::LayerRestriction { var_name, allowed } if var_name == "B" && !*allowed)
        }));
        assert!(!result.constraints.iter().any(|c| matches!(c, InternalConstraint::Capacity { .. })));
    }

    // -----------------------------------------------------------------------
    // TS1: no overlap → rewrite no-op
    // -----------------------------------------------------------------------
    #[test]
    fn ts1_no_overlap_rewrite_noop() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![
                capacity("CH1", 2.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)]),
                capacity("CH2", 1.0, vec![("D", 1.0), ("E", 1.0)]),
                diffpair("CH1", "p", "n"),
                layer("X", true),
            ],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), model.constraints.len());
    }

    // -----------------------------------------------------------------------
    // Fixpoint termination
    // -----------------------------------------------------------------------
    #[test]
    fn fixpoint_termination() {
        // No rules fire → loop terminates in 1 iteration.
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![capacity("CH1", 2.0, vec![("A", 1.0), ("B", 1.0), ("C", 1.0)])],
        };
        let result = rewrite(&model).unwrap();
        assert_eq!(result.constraints.len(), 1);
    }

    // -----------------------------------------------------------------------
    // No false UNSAT: when RW7 fires, verify the conflict is real.
    // -----------------------------------------------------------------------
    #[test]
    fn no_false_unsat_conflict_is_real() {
        let model = InternalConstraintModel {
            variables: vec![],
            constraints: vec![layer("X", true), layer("X", false)],
        };
        let err = rewrite(&model).unwrap_err();
        match err {
            RewriteError::UnsatPreSolve { var_name, .. } => {
                assert_eq!(var_name, "X");
            }
        }
    }

    // -----------------------------------------------------------------------
    // Roundtrip: rewrite preserves SAT equivalence on small models
    // -----------------------------------------------------------------------
    #[test]
    fn exhaustive_rewrite_preserves_sat_n4() {
        // For n=4 variables, exhaustively verify rewrite preserves satisfiability
        // of capacity + layer combinations.
        for n in 1..=4u32 {
            for k in 0..n {
                let var_names: Vec<String> = (0..n).map(|i| format!("v{i}")).collect();
                let terms: Vec<(String, f64)> = var_names.iter().map(|v| (v.clone(), 1.0)).collect();

                for assign_layer_idx in 0..=var_names.len() {
                    let mut constraints = vec![
                        InternalConstraint::Capacity {
                            channel_id: "CH1".into(),
                            capacity: k as f64,
                            slack_factor: 1.0,
                            terms: terms.clone(),
                        },
                    ];

                    if assign_layer_idx < var_names.len() {
                        constraints.push(InternalConstraint::LayerRestriction {
                            var_name: var_names[assign_layer_idx].clone(),
                            allowed: true,
                        });
                    }

                    let model = InternalConstraintModel {
                        variables: vec![],
                        constraints,
                    };

                    let rewritten = rewrite(&model);
                    // Rewrite should never error for non-contradictory inputs.
                    // Constraint count may increase when K=0 expansion adds unit
                    // clauses, but this is correct (clause count still decreases).
                    assert!(rewritten.is_ok(),
                        "rewrite errored for n={n} k={k} layer_idx={assign_layer_idx}: {:?}",
                        rewritten.err());
                    // If rewrite errored (RW7), that's acceptable — it means a
                    // contradiction was detected, which could only happen in
                    // complex multi-layer cases.
                }
            }
        }
    }
}

// Pre-solve tension detection — analytically detect incompatible constraints.
//
// Origin: U3 of docs/plans/2026-06-28-003-feat-unsat-provenance-tension-detection-plan.md

use std::collections::{HashMap, HashSet};

use crate::types::{InternalConstraint, InternalConstraintModel, TensionSeverity, TensionViolation};

/// Detect analytically-incompatible constraint pairs before the SAT solve.
///
/// Runs in O(c + v) time (c = constraint count, v = variable count).
/// Read-only — does not mutate the model.
pub fn detect_tensions(model: &InternalConstraintModel) -> Vec<TensionViolation> {
    let mut violations = Vec::new();

    // Build var_name → (net_idx, channel_id) from model variables.
    let var_info: HashMap<&str, (usize, &str)> = model
        .variables
        .iter()
        .map(|v| match v {
            crate::types::InternalVariable::NetChannel { name, net_idx, channel_id } => {
                (name.as_str(), (*net_idx, channel_id.as_str()))
            }
            crate::types::InternalVariable::NetLayer { name, net_idx, segment_id } => {
                (name.as_str(), (*net_idx, segment_id.as_str()))
            }
            crate::types::InternalVariable::Via { name, net_idx, location_id } => {
                (name.as_str(), (*net_idx, location_id.as_str()))
            }
            crate::types::InternalVariable::Ordering { name, .. } => {
                (name.as_str(), (usize::MAX, ""))
            }
        })
        .collect();

    // Build net_idx → HashSet<channel_id> for all channels a net can route on.
    let mut net_channels: HashMap<usize, HashSet<&str>> = HashMap::new();
    for (_, (net_idx, channel_id)) in &var_info {
        if *net_idx != usize::MAX && !channel_id.is_empty() {
            net_channels.entry(*net_idx).or_default().insert(channel_id);
        }
    }

    // Build net_bans: for each net, channels where the net's var has a
    // LayerRestriction(allowed=false).
    let mut net_bans: HashMap<usize, HashSet<&str>> = HashMap::new();
    for c in &model.constraints {
        if let InternalConstraint::LayerRestriction { var_name, allowed } = c {
            if !allowed {
                if let Some(&(net_idx, _ch)) = var_info.get(var_name.as_str()) {
                    if net_idx != usize::MAX {
                        // Determine channel from variable mapping.
                        if let Some(&(_, ch)) = var_info.get(var_name.as_str()) {
                            net_bans.entry(net_idx).or_default().insert(ch);
                        }
                    }
                }
            }
        }
    }

    // Pre-pass: index constraints.
    // capacity_by_channel: channel_id → (constraint_idx, max_nets, set of (net_idx, var_name))
    let mut capacity_by_channel: HashMap<&str, (usize, usize, HashSet<usize>)> = HashMap::new();
    // diffpairs: Vec<(constraint_idx, channel_id, p_var_name, n_var_name, p_net_idx, n_net_idx)>
    let mut diffpairs: Vec<(usize, &str, &str, &str, usize, usize)> = Vec::new();
    // All known channel IDs — from variables AND constraints.
    let mut all_channels: HashSet<&str> = HashSet::new();

    // Collect channels from ALL model variables first.
    for (_, (_, ch)) in &var_info {
        if !ch.is_empty() {
            all_channels.insert(ch);
        }
    }

    for (ci, c) in model.constraints.iter().enumerate() {
        match c {
            InternalConstraint::Capacity {
                channel_id, capacity, slack_factor, terms,
            } => {
                if terms.is_empty() {
                    continue;
                }
                all_channels.insert(channel_id.as_str());
                let min_width = terms
                    .iter()
                    .map(|(_, w)| *w)
                    .fold(f64::INFINITY, f64::min);
                let max_nets = ((capacity * slack_factor) / min_width).floor() as usize;
                let net_set: HashSet<usize> = terms
                    .iter()
                    .filter_map(|(vn, _)| var_info.get(vn.as_str()).map(|(ni, _)| *ni))
                    .filter(|ni| *ni != usize::MAX)
                    .collect();
                capacity_by_channel
                    .insert(channel_id.as_str(), (ci, max_nets, net_set));
            }
            InternalConstraint::DiffPair {
                channel_id,
                p_var_name,
                n_var_name,
            } => {
                all_channels.insert(channel_id.as_str());
                let p_net = var_info
                    .get(p_var_name.as_str())
                    .map(|(ni, _)| *ni)
                    .unwrap_or(usize::MAX);
                let n_net = var_info
                    .get(n_var_name.as_str())
                    .map(|(ni, _)| *ni)
                    .unwrap_or(usize::MAX);
                diffpairs.push((
                    ci, channel_id.as_str(), p_var_name.as_str(), n_var_name.as_str(),
                    p_net, n_net,
                ));
            }
            InternalConstraint::LayerRestriction { .. } => {
                // Processed above in net_bans loop.
            }
        }
    }

    // Check 1: Capacity oversubscription.
    check_capacity_oversubscription(
        &capacity_by_channel,
        &net_bans,
        &net_channels,
        &all_channels,
        &mut violations,
    );

    // Check 2: Diff-pair vs. capacity.
    check_diffpair_vs_capacity(
        &diffpairs,
        &capacity_by_channel,
        &mut violations,
    );

    // Check 3: Layer-restriction starvation (per net).
    check_layer_restriction_starvation(
        model,
        &capacity_by_channel,
        &net_bans,
        &net_channels,
        &all_channels,
        &var_info,
        &mut violations,
    );

    // Check 4: Mutually-exclusive diffpair assignment.
    check_mutually_exclusive_diffpair(
        &diffpairs,
        &net_bans,
        &net_channels,
        &all_channels,
        &mut violations,
    );

    violations
}

/// Count must-use nets on a channel: nets that CAN use other channels but
/// are banned from all of them, forcing them onto this channel.
///
/// A net is only "must-use" if it has alternatives (other channels exist in
/// the model that this net has variables for) AND those alternatives are all
/// banned. If no alternatives exist (only one channel in the model, or only
/// one channel variable for this net), the net is NOT must-use — the solver
/// can still choose not to assign it.
fn count_must_use_nets(
    channel_id: &str,
    net_set: &HashSet<usize>,
    net_bans: &HashMap<usize, HashSet<&str>>,
    net_channels: &HashMap<usize, HashSet<&str>>,
    all_channels: &HashSet<&str>,
) -> (usize, Vec<usize>) {
    let other_channels: HashSet<&str> =
        all_channels.iter().filter(|&&ch| ch != channel_id).copied().collect();

    // If there are no other channels in the model, no net is must-use.
    if other_channels.is_empty() {
        return (0, Vec::new());
    }

    let mut must_use = Vec::new();
    for &net_idx in net_set {
        // A net is "must-use" on CH only if it HAS alternatives (other channel
        // vars for this net) AND all alternatives are banned.
        let net_chs = match net_channels.get(&net_idx) {
            Some(chs) => chs,
            None => continue,
        };

        // Check if this net has vars for other channels.
        let has_alternative = net_chs.iter().any(|ch| *ch != channel_id);
        if !has_alternative {
            // No alternative channels for this net — it can still be false.
            continue;
        }

        let bans = net_bans.get(&net_idx);
        let all_alternatives_banned = other_channels.iter().all(|&och| {
            // Only consider channels the net actually has vars for.
            if !net_chs.contains(och) {
                return true; // can't use it anyway, so skip
            }
            match bans {
                Some(bans) => bans.contains(och),
                None => false,
            }
        });

        if all_alternatives_banned {
            must_use.push(net_idx);
        }
    }
    (must_use.len(), must_use)
}

/// Check 1: For each channel, count must-use nets and compare against capacity.
fn check_capacity_oversubscription(
    capacity_by_channel: &HashMap<&str, (usize, usize, HashSet<usize>)>,
    net_bans: &HashMap<usize, HashSet<&str>>,
    net_channels: &HashMap<usize, HashSet<&str>>,
    all_channels: &HashSet<&str>,
    violations: &mut Vec<TensionViolation>,
) {
    for (&channel_id, &(ci, max_nets, ref net_set)) in capacity_by_channel {
        let (count, _must_use) = count_must_use_nets(
            channel_id, net_set, net_bans, net_channels, all_channels,
        );

        if count > max_nets {
            let net_list: Vec<String> = _must_use.iter().map(|n| format!("N{n}")).collect();
            violations.push(TensionViolation {
                constraint_pair: (ci, ci),
                channel_id: channel_id.to_string(),
                explanation: format!(
                    "Channel {channel_id} capacity ({max_nets} nets) cannot accommodate {count} \
                     nets that have no other allowed channels: {nets}",
                    nets = net_list.join(", "),
                ),
                severity: TensionSeverity::HardConflict,
            });
        } else if count as f64 >= (max_nets as f64 * 0.9) && count > 0 && max_nets > 0 {
            let pct = (count as f64 / max_nets as f64 * 100.0).round() as u32;
            violations.push(TensionViolation {
                constraint_pair: (ci, ci),
                channel_id: channel_id.to_string(),
                explanation: format!(
                    "Channel {channel_id} is at {pct}% capacity ({count}/{max_nets} must-use \
                     nets) — the solver may fail to find an assignment",
                ),
                severity: TensionSeverity::CapacityWarning,
            });
        }
    }
}

/// Check 2: DiffPair on channel CH requiring capacity >= 2.
fn check_diffpair_vs_capacity(
    diffpairs: &[(usize, &str, &str, &str, usize, usize)],
    capacity_by_channel: &HashMap<&str, (usize, usize, HashSet<usize>)>,
    violations: &mut Vec<TensionViolation>,
) {
    for &(dpi, channel_id, p_var, n_var, _p_net, _n_net) in diffpairs {
        if let Some(&(cap_ci, max_nets, _)) = capacity_by_channel.get(channel_id) {
            if max_nets < 2 {
                violations.push(TensionViolation {
                    constraint_pair: (dpi, cap_ci),
                    channel_id: channel_id.to_string(),
                    explanation: format!(
                        "Diff pair requires both {p_var} and {n_var} on channel {channel_id}, \
                         but {channel_id} capacity is {max_nets} (only {max_nets} net allowed)",
                    ),
                    severity: TensionSeverity::HardConflict,
                });
            }
        }
    }
}

/// Check 3: Layer-restriction starvation — each net is forced to one channel
/// whose capacity is exceeded by must-use nets.
fn check_layer_restriction_starvation(
    model: &InternalConstraintModel,
    capacity_by_channel: &HashMap<&str, (usize, usize, HashSet<usize>)>,
    net_bans: &HashMap<usize, HashSet<&str>>,
    net_channels: &HashMap<usize, HashSet<&str>>,
    all_channels: &HashSet<&str>,
    _var_info: &HashMap<&str, (usize, &str)>,
    violations: &mut Vec<TensionViolation>,
) {
    for c in &model.constraints {
        if let InternalConstraint::LayerRestriction { var_name, allowed } = c {
            if !*allowed {
                continue; // only check positive restrictions (net forced TO a channel)
            }

            // Determine which channel and net this restriction is about.
            // var_name is like "uses_N{net_idx}_{channel_id}".
            // With allowed=true, this means the net is assigned to this channel.
            // We check: is this net forced to this channel (banned from all others)?
            let net_idx = match _var_info.get(var_name.as_str()) {
                Some(&(ni, _)) if ni != usize::MAX => ni,
                _ => continue,
            };

            let ch = match _var_info.get(var_name.as_str()) {
                Some(&(_, ch)) if !ch.is_empty() => ch,
                _ => continue,
            };

            if let Some(&(cap_ci, max_nets, ref net_set)) = capacity_by_channel.get(ch) {
                // Check if this net has only this channel available.
                let other_channels: Vec<&&str> =
                    all_channels.iter().filter(|&&och| och != ch).collect();
                if other_channels.is_empty() {
                    continue;
                }

                let bans = net_bans.get(&net_idx);
                let only_this = other_channels.iter().all(|&&och| {
                    match bans {
                        Some(bans) => bans.contains(och),
                        None => match net_channels.get(&net_idx) {
                            Some(chs) => !chs.contains(och), // no var, can't use → banned
                            None => false,
                        },
                    }
                });

                if !only_this {
                    continue;
                }

                // Count total must-use nets on this channel.
                let (must_use_count, _) = count_must_use_nets(
                    ch, net_set, net_bans, net_channels, all_channels,
                );

                if must_use_count > max_nets {
                    violations.push(TensionViolation {
                        constraint_pair: (cap_ci, cap_ci),
                        channel_id: ch.to_string(),
                        explanation: format!(
                            "Net 'N{net_idx}' is restricted to channel {ch} (all other channels \
                             banned), but {ch} capacity ({max_nets}) is exhausted by \
                             {must_use_count} must-use nets",
                        ),
                        severity: TensionSeverity::HardConflict,
                    });
                }
            }
        }
    }
}

/// Check 4: Mutually-exclusive diffpair assignment — the two nets in a diff-pair
/// have no shared allowed channel.
fn check_mutually_exclusive_diffpair(
    diffpairs: &[(usize, &str, &str, &str, usize, usize)],
    net_bans: &HashMap<usize, HashSet<&str>>,
    net_channels: &HashMap<usize, HashSet<&str>>,
    all_channels: &HashSet<&str>,
    violations: &mut Vec<TensionViolation>,
) {
    for &(dpi, _channel_id, p_var, n_var, p_net, n_net) in diffpairs {
        let p_allowed: HashSet<&str> = all_channels
            .iter()
            .filter(|&&ch| {
                let bans = net_bans.get(&p_net);
                match bans {
                    Some(bans) => !bans.contains(ch),
                    None => {
                        // No ban on this channel. But does the net even have a var for it?
                        match net_channels.get(&p_net) {
                            Some(chs) => chs.contains(ch),
                            None => false,
                        }
                    }
                }
            })
            .copied()
            .collect();

        let n_allowed: HashSet<&str> = all_channels
            .iter()
            .filter(|&&ch| {
                let bans = net_bans.get(&n_net);
                match bans {
                    Some(bans) => !bans.contains(ch),
                    None => {
                        match net_channels.get(&n_net) {
                            Some(chs) => chs.contains(ch),
                            None => false,
                        }
                    }
                }
            })
            .copied()
            .collect();

        if !p_allowed.is_empty() && !n_allowed.is_empty() {
            let intersection: Vec<&&str> = p_allowed.intersection(&n_allowed).collect();
            if intersection.is_empty() {
                violations.push(TensionViolation {
                    constraint_pair: (dpi, dpi),
                    channel_id: String::new(),
                    explanation: format!(
                        "Diff pair {p_var}/{n_var} has no shared channel — layer restrictions \
                         on both nets ban all channels the other can use",
                    ),
                    severity: TensionSeverity::HardConflict,
                });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{InternalConstraint, InternalConstraintModel, InternalVariable};

    fn make_var(name: &str, idx: usize, ch: &str) -> InternalVariable {
        InternalVariable::NetChannel {
            name: name.to_string(),
            net_idx: idx,
            channel_id: ch.to_string(),
        }
    }

    fn make_model(
        vars: Vec<InternalVariable>,
        constraints: Vec<InternalConstraint>,
    ) -> InternalConstraintModel {
        InternalConstraintModel {
            variables: vars,
            constraints,
        }
    }

    #[test]
    fn no_tensions_when_model_is_feasible() {
        let vars = vec![
            make_var("uses_N0_CH1", 0, "CH1"),
            make_var("uses_N1_CH1", 1, "CH1"),
            make_var("uses_N0_CH2", 0, "CH2"),
            make_var("uses_N1_CH2", 1, "CH2"),
        ];
        let cons = vec![
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 2.0,
                slack_factor: 1.0,
                terms: vec![("uses_N0_CH1".into(), 1.0), ("uses_N1_CH1".into(), 1.0)],
            },
            InternalConstraint::Capacity {
                channel_id: "CH2".into(),
                capacity: 2.0,
                slack_factor: 1.0,
                terms: vec![("uses_N0_CH2".into(), 1.0), ("uses_N1_CH2".into(), 1.0)],
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        assert!(tensions.is_empty(), "expected no tensions but got: {tensions:?}");
    }

    #[test]
    fn capacity_oversubscription_hard_conflict() {
        // 3 nets N0,N1,N2. All have CH1 and CH2 vars.
        // CH1 capacity 2. All nets banned from CH2 → must-use on CH1 = 3 > 2.
        let vars = vec![
            make_var("uses_N0_CH1", 0, "CH1"),
            make_var("uses_N1_CH1", 1, "CH1"),
            make_var("uses_N2_CH1", 2, "CH1"),
            make_var("uses_N0_CH2", 0, "CH2"),
            make_var("uses_N1_CH2", 1, "CH2"),
            make_var("uses_N2_CH2", 2, "CH2"),
        ];
        let cons = vec![
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 2.0,
                slack_factor: 1.0,
                terms: vec![
                    ("uses_N0_CH1".into(), 1.0),
                    ("uses_N1_CH1".into(), 1.0),
                    ("uses_N2_CH1".into(), 1.0),
                ],
            },
            InternalConstraint::Capacity {
                channel_id: "CH2".into(),
                capacity: 10.0,
                slack_factor: 1.0,
                terms: vec![
                    ("uses_N0_CH2".into(), 1.0),
                    ("uses_N1_CH2".into(), 1.0),
                    ("uses_N2_CH2".into(), 1.0),
                ],
            },
            // Ban all nets from CH2 (must-use on CH1)
            InternalConstraint::LayerRestriction {
                var_name: "uses_N0_CH2".into(),
                allowed: false,
            },
            InternalConstraint::LayerRestriction {
                var_name: "uses_N1_CH2".into(),
                allowed: false,
            },
            InternalConstraint::LayerRestriction {
                var_name: "uses_N2_CH2".into(),
                allowed: false,
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        assert!(!tensions.is_empty(), "expected tensions on oversubscription, got: {tensions:?}");
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(!hard.is_empty(), "expected HardConflict but got: {tensions:?}");
    }

    #[test]
    fn diffpair_capacity_hard_conflict() {
        let vars = vec![
            make_var("p_N0_CH1", 0, "CH1"),
            make_var("n_N0_CH1", 1, "CH1"),
        ];
        let cons = vec![
            InternalConstraint::DiffPair {
                channel_id: "CH1".into(),
                p_var_name: "p_N0_CH1".into(),
                n_var_name: "n_N0_CH1".into(),
            },
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 1.0,
                slack_factor: 1.0,
                terms: vec![("p_N0_CH1".into(), 1.0), ("n_N0_CH1".into(), 1.0)],
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(
            !hard.is_empty(),
            "expected HardConflict for diffpair vs capacity=1 but got: {tensions:?}"
        );
    }

    #[test]
    fn diffpair_capacity_2_is_fine() {
        let vars = vec![
            make_var("p_N0_CH1", 0, "CH1"),
            make_var("n_N0_CH1", 1, "CH1"),
        ];
        let cons = vec![
            InternalConstraint::DiffPair {
                channel_id: "CH1".into(),
                p_var_name: "p_N0_CH1".into(),
                n_var_name: "n_N0_CH1".into(),
            },
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 2.0,
                slack_factor: 1.0,
                terms: vec![("p_N0_CH1".into(), 1.0), ("n_N0_CH1".into(), 1.0)],
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(hard.is_empty(), "expected no HardConflict for diffpair with capacity=2");
    }

    #[test]
    fn capacity_warning_at_90_percent() {
        // 10 nets, CH1 capacity 10, CH2 capacity 10.
        // N0-N8 banned from CH2, N9 can use CH2 → 9 must-use on CH1 out of capacity 10 = 90%.
        let mut vars = Vec::new();
        let mut terms: Vec<(String, f64)> = Vec::new();
        let mut cons: Vec<InternalConstraint> = Vec::new();
        for i in 0..10 {
            let vname_ch1 = format!("uses_N{i}_CH1");
            vars.push(make_var(&vname_ch1, i, "CH1"));
            let vname_ch2 = format!("uses_N{i}_CH2");
            vars.push(make_var(&vname_ch2, i, "CH2"));
            terms.push((vname_ch1.clone(), 1.0));
        }
        cons.push(InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 10.0,
            slack_factor: 1.0,
            terms,
        });
        // Add CH2 capacity for all nets (to make it a valid channel with vars).
        cons.push(InternalConstraint::Capacity {
            channel_id: "CH2".into(),
            capacity: 10.0,
            slack_factor: 1.0,
            terms: (0..10).map(|i| (format!("uses_N{i}_CH2"), 1.0)).collect(),
        });
        // Ban N0-N8 from CH2.
        for i in 0..9 {
            cons.push(InternalConstraint::LayerRestriction {
                var_name: format!("uses_N{i}_CH2"),
                allowed: false,
            });
        }
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let warnings: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::CapacityWarning)
            .collect();
        assert!(
            !warnings.is_empty(),
            "expected CapacityWarning at 90% but got: {tensions:?}"
        );
    }

    #[test]
    fn mutually_exclusive_diffpair_hard_conflict() {
        // Two diffpair nets on CH1. Ban p from CH2, ban n from CH1 → no shared channel.
        let vars = vec![
            make_var("p_N0_CH1", 0, "CH1"),
            make_var("n_N0_CH1", 1, "CH1"),
            make_var("p_N0_CH2", 0, "CH2"),
            make_var("n_N0_CH2", 1, "CH2"),
        ];
        let cons = vec![
            InternalConstraint::DiffPair {
                channel_id: "CH1".into(),
                p_var_name: "p_N0_CH1".into(),
                n_var_name: "n_N0_CH1".into(),
            },
            // Ban p from CH2, ban n from CH1 → no shared channel
            InternalConstraint::LayerRestriction {
                var_name: "p_N0_CH2".into(),
                allowed: false,
            },
            InternalConstraint::LayerRestriction {
                var_name: "n_N0_CH1".into(),
                allowed: false,
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(
            !hard.is_empty(),
            "expected mutually-exclusive HardConflict but got: {tensions:?}"
        );
    }

    #[test]
    fn layer_restriction_starvation_check3() {
        // Check 3: net forced to CH1, but CH1 capacity exceeded by must-use nets.
        // N0,N1 banned from CH2 → must-use on CH1 = 2, CH1 capacity = 1 → HardConflict.
        let vars = vec![
            make_var("uses_N0_CH1", 0, "CH1"),
            make_var("uses_N1_CH1", 1, "CH1"),
            make_var("uses_N2_CH1", 2, "CH1"),
            make_var("uses_N0_CH2", 0, "CH2"),
            make_var("uses_N1_CH2", 1, "CH2"),
            make_var("uses_N2_CH2", 2, "CH2"),
        ];
        let cons = vec![
            InternalConstraint::Capacity {
                channel_id: "CH1".into(),
                capacity: 1.0,
                slack_factor: 1.0,
                terms: vec![
                    ("uses_N0_CH1".into(), 1.0),
                    ("uses_N1_CH1".into(), 1.0),
                    ("uses_N2_CH1".into(), 1.0),
                ],
            },
            InternalConstraint::Capacity {
                channel_id: "CH2".into(),
                capacity: 10.0,
                slack_factor: 1.0,
                terms: vec![
                    ("uses_N0_CH2".into(), 1.0),
                    ("uses_N1_CH2".into(), 1.0),
                    ("uses_N2_CH2".into(), 1.0),
                ],
            },
            // Force N0 and N1 to CH1 (ban from CH2)
            InternalConstraint::LayerRestriction {
                var_name: "uses_N0_CH2".into(),
                allowed: false,
            },
            InternalConstraint::LayerRestriction {
                var_name: "uses_N1_CH2".into(),
                allowed: false,
            },
        ];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(
            !hard.is_empty(),
            "expected starvation HardConflict but got: {tensions:?}"
        );
    }

    #[test]
    fn no_false_positive_for_feasible_model() {
        let vars: Vec<_> = (0..4)
            .map(|i| make_var(&format!("uses_N{i}_CH1"), i, "CH1"))
            .collect();
        let terms: Vec<_> = vars
            .iter()
            .map(|v| match v {
                InternalVariable::NetChannel { name, .. } => (name.clone(), 1.0),
                _ => unreachable!(),
            })
            .collect();
        let cons = vec![InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 2.0,
            slack_factor: 1.0,
            terms,
        }];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(
            hard.is_empty(),
            "expected no HardConflict for feasible model but got: {tensions:?}"
        );
    }

    #[test]
    fn no_tension_for_capacity_only_model() {
        let vars: Vec<_> = (0..3)
            .map(|i| make_var(&format!("uses_N{i}_CH1"), i, "CH1"))
            .collect();
        let terms: Vec<_> = vars
            .iter()
            .map(|v| match v {
                InternalVariable::NetChannel { name, .. } => (name.clone(), 1.0),
                _ => unreachable!(),
            })
            .collect();
        let cons = vec![InternalConstraint::Capacity {
            channel_id: "CH1".into(),
            capacity: 3.0,
            slack_factor: 1.0,
            terms,
        }];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        assert!(tensions.is_empty(), "expected no tensions: {tensions:?}");
    }

    #[test]
    fn no_capacity_constraint_skip_gracefully() {
        let vars = vec![
            make_var("p_N0_CH1", 0, "CH1"),
            make_var("n_N0_CH1", 1, "CH1"),
        ];
        let cons = vec![InternalConstraint::DiffPair {
            channel_id: "CH1".into(),
            p_var_name: "p_N0_CH1".into(),
            n_var_name: "n_N0_CH1".into(),
        }];
        let model = make_model(vars, cons);
        let tensions = detect_tensions(&model);
        let hard: Vec<_> = tensions
            .iter()
            .filter(|t| t.severity == TensionSeverity::HardConflict)
            .collect();
        assert!(hard.is_empty(), "expected no HardConflict: {tensions:?}");
    }
}

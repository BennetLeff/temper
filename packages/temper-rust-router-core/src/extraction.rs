// Topology extraction — solver assignments → TopologyGraph channel paths.
//
// Origin: U6 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
//
// Extended U5: bundle-variable homomorphism expansion per
// docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md

use std::collections::HashMap;

use crate::types::{
    BundleClass, InternalBundleManifest, InternalConstraintModel, NetTopology, TopologyGraph,
};

/// Convert solver variable assignments into a TopologyGraph of channel paths.
///
/// Parses variable names matching the Python convention `uses_{net_name}_{channel_id}`
/// and groups true variables by net name.
pub fn extract_topology(
    _model: &InternalConstraintModel,
    assignments: &HashMap<usize, bool>,
    var_names: &[String],
    net_names: &[String],
) -> TopologyGraph {
    // Longest-prefix matching: sort net names by descending length so the
    // first prefix match in the assignment loop below is the longest one,
    // and the scan can `break` immediately (F2).
    let mut nets_by_len: Vec<&str> = net_names.iter().map(|s| s.as_str()).collect();
    nets_by_len.sort_unstable_by_key(|s| std::cmp::Reverse(s.len()));

    // net_name → Vec<channel_id>
    let mut net_channels: HashMap<String, Vec<String>> = HashMap::new();

    for (idx, val) in assignments {
        if !val {
            continue;
        }
        if *idx >= var_names.len() {
            continue;
        }
        let var_name = &var_names[*idx];

        // Parse variable names of the form `uses_{net_name}_{channel_id}`.
        // Net names can contain underscores, so we try suffix splitting.
        if let Some(rest) = var_name.strip_prefix("uses_") {
            // Try each known net name as a prefix of `rest`, longest first.
            // `break` is safe: remaining candidates are all shorter, so the
            // first match (with the '_' separator) is the longest prefix.
            for net in &nets_by_len {
                if rest.starts_with(*net) {
                    // The character after the net name must be '_' (separator to channel_id).
                    let after = &rest[net.len()..];
                    if after.starts_with('_') {
                        let channel_id = &rest[net.len() + 1..]; // skip net_name + '_'
                        if !channel_id.is_empty() {
                            net_channels
                                .entry((*net).to_string())
                                .or_default()
                                .push(channel_id.to_string());
                        }
                        break;
                    }
                }
            }
        }
    }

    // Build NetTopology for each net.
    let mut net_topologies: HashMap<String, NetTopology> = HashMap::new();

    for net_name in net_names {
        let channels = net_channels.remove(net_name.as_str()).unwrap_or_default();
        let path_graph = build_path_graph(net_name, &channels);
        net_topologies.insert(
            net_name.clone(),
            NetTopology {
                net_name: net_name.clone(),
                uses_channels: channels.clone(),
                path_graph,
                total_length_estimate: channels.len() as f64 * 10.0,
            },
        );
    }

    for (net_name, channels) in net_channels {
        let path_graph = build_path_graph(&net_name, &channels);
        net_topologies.insert(
            net_name.clone(),
            NetTopology {
                net_name,
                uses_channels: channels.clone(),
                path_graph,
                total_length_estimate: channels.len() as f64 * 10.0,
            },
        );
    }

    TopologyGraph { net_topologies }
}

// ---------------------------------------------------------------------------
// Homomorphism — class-variable ↔ per-net variable mapping (U5 / R8)
// ---------------------------------------------------------------------------

/// Expand class-level assignments to per-net assignments via the homomorphism.
///
/// For each bundle, a class var `uses_B{bid}_{ch} = true` is expanded to
/// `uses_N{net_idx}_{ch} = true` for every net in the bundle. Explicitly
/// instantiated per-net variables override the expansion.
pub fn expand_assignments(
    assignments: &HashMap<usize, bool>,
    var_names: &[String],
    manifest: &InternalBundleManifest,
) -> HashMap<usize, bool> {
    let mut expanded = assignments.clone();

    // Build name-to-index map.
    let name_to_idx: HashMap<&str, usize> =
        var_names.iter().enumerate().map(|(i, n)| (n.as_str(), i)).collect();

    // Build bundle_id → (channel_id → true/false) from class vars.
    let mut bundle_ch_vals: HashMap<usize, HashMap<String, bool>> = HashMap::new();
    for name in var_names {
        #[allow(clippy::collapsible_if)]
        if let Some(rest) = name.strip_prefix("uses_B") {
            if let Some(underscore_pos) = rest.find('_') {
                let bid_str = &rest[..underscore_pos];
                let ch = &rest[underscore_pos + 1..];
                if let Ok(bid) = bid_str.parse::<usize>()
                    && let Some(&idx) = name_to_idx.get(name.as_str())
                    && let Some(&val) = assignments.get(&idx)
                {
                    bundle_ch_vals.entry(bid).or_default().insert(ch.to_string(), val);
                }
            }
        }
    }

    // Add per-net variables for each bundle member.
    for bundle in &manifest.bundles {
        if let Some(ch_vals) = bundle_ch_vals.get(&bundle.bundle_id) {
            for ch in ch_vals.keys() {
                for &ni in &bundle.net_indices {
                    let pn_name = format!("uses_N{ni}_{ch}");
                    // Only add if not already explicitly assigned; skip for now.
                    if let Some(&pn_idx) = name_to_idx.get(pn_name.as_str())
                        && !expanded.contains_key(&pn_idx)
                    {
                        expanded.insert(pn_idx, true);
                    }
                }
            }
        }
    }

    expanded
}

/// Extract topology from bundled solver results using the homomorphism.
///
/// Parses both `uses_B` (class-level) and `uses_N` (per-net) variable names
/// and expands class assignments to per-net channel lists.
pub fn extract_bundled(
    _model: &InternalConstraintModel,
    assignments: &HashMap<usize, bool>,
    var_names: &[String],
    net_names: &[String],
    manifest: &InternalBundleManifest,
) -> TopologyGraph {
    // Build name-to-index map for class vars.
    let name_to_idx: HashMap<&str, usize> =
        var_names.iter().enumerate().map(|(i, n)| (n.as_str(), i)).collect();

    // Expand class-variable assignments to per-net assignments.
    let mut expanded = assignments.clone();
    let mut all_var_names = var_names.to_vec();

    // Index bundles by id once (F3) — previously a linear scan over
    // `manifest.bundles` ran inside the per-class-var loop below.
    let bundle_by_id: HashMap<usize, &BundleClass> = manifest
        .bundles
        .iter()
        .map(|b| (b.bundle_id, b))
        .collect();

    for name in var_names {
        if !name.starts_with("uses_B") {
            continue;
        }
        let rest = &name[6..]; // strip "uses_B"
        if let Some(underscore_pos) = rest.find('_') {
            let bid_str = &rest[..underscore_pos];
            let ch = &rest[underscore_pos + 1..];
            if let Ok(bid) = bid_str.parse::<usize>() {
                // Look up class var assignment.
                let class_val = name_to_idx.get(name.as_str()).and_then(|&idx| assignments.get(&idx).copied());
                if class_val != Some(true) {
                    continue;
                }
                // Find the bundle and expand.
                if let Some(bundle) = bundle_by_id.get(&bid) {
                    for &ni in &bundle.net_indices {
                        let pn_name = format!("uses_N{ni}_{ch}");
                        let pn_idx = if let Some(&idx) = name_to_idx.get(pn_name.as_str()) {
                            idx
                        } else {
                            let new_idx = all_var_names.len();
                            all_var_names.push(pn_name);
                            new_idx
                        };
                        expanded.entry(pn_idx).or_insert(true);
                    }
                }
            }
        }
    }

    // Now use standard extraction on the expanded set.
    let mut net_channels: HashMap<String, Vec<String>> = HashMap::new();

    for (idx, val) in &expanded {
        if !val || *idx >= all_var_names.len() {
            continue;
        }
        let var_name = &all_var_names[*idx];
        #[allow(clippy::collapsible_if)]
        if let Some(rest) = var_name.strip_prefix("uses_N") {
            if let Some(underscore_pos) = rest.find('_') {
                let ni_str = &rest[..underscore_pos];
                let ch = &rest[underscore_pos + 1..];
                if let Ok(ni) = ni_str.parse::<usize>()
                    && let Some(net_name) = net_names.get(ni)
                    && !ch.is_empty()
                {
                    net_channels
                        .entry(net_name.clone())
                        .or_default()
                        .push(ch.to_string());
                }
            }
        }
    }

    // Build NetTopology for each net.
    let mut net_topologies: HashMap<String, NetTopology> = HashMap::new();
    for net_name in net_names {
        let channels = net_channels.remove(net_name.as_str()).unwrap_or_default();
        let path_graph = build_path_graph(net_name, &channels);
        net_topologies.insert(
            net_name.clone(),
            NetTopology {
                net_name: net_name.clone(),
                uses_channels: channels.clone(),
                path_graph,
                total_length_estimate: channels.len() as f64 * 10.0,
            },
        );
    }
    for (net_name, channels) in net_channels {
        let path_graph = build_path_graph(&net_name, &channels);
        net_topologies.insert(
            net_name.clone(),
            NetTopology {
                net_name,
                uses_channels: channels.clone(),
                path_graph,
                total_length_estimate: channels.len() as f64 * 10.0,
            },
        );
    }

    TopologyGraph { net_topologies }
}

/// Build an ordered edge walk from a list of channel IDs.
///
/// For single-channel: [(net_name, channel_id)].
/// For multi-channel: [(ch0, ch1), (ch1, ch2), ...].
fn build_path_graph(net_name: &str, channels: &[String]) -> Vec<(String, String)> {
    if channels.is_empty() {
        return Vec::new();
    }
    if channels.len() == 1 {
        return vec![(net_name.to_string(), channels[0].clone())];
    }
    channels
        .windows(2)
        .map(|w| (w[0].clone(), w[1].clone()))
        .collect()
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use crate::types::{
        BundleClass, InternalBundleManifest,
    };

    fn make_test_manifest() -> InternalBundleManifest {
        InternalBundleManifest {
            bundles: vec![
                BundleClass {
                    bundle_id: 0,
                    net_indices: vec![0, 1],
                    constraint_types: vec!["safety".to_string(), "performance".to_string()],
                    is_diff_pair: false,
                },
            ],
            bundle_id_for_net: {
                let mut m = HashMap::new();
                m.insert(0, 0);
                m.insert(1, 0);
                m
            },
            unbundled_net_indices: vec![],
        }
    }

    #[test]
    fn test_expand_assignments_singleton_bundle() {
        let manifest = make_test_manifest();
        let var_names = vec![
            "uses_B0_CH1".to_string(),
            "uses_B0_CH2".to_string(),
        ];
        let mut assignments = HashMap::new();
        assignments.insert(0, true); // uses_B0_CH1

        let expanded = expand_assignments(&assignments, &var_names, &manifest);

        assert!(expanded.get(&0).copied().unwrap_or(false));
    }

    #[test]
    fn test_expand_assignments_false_class_var() {
        let manifest = make_test_manifest();
        let var_names = vec![
            "uses_B0_CH1".to_string(),
        ];
        let mut assignments = HashMap::new();
        assignments.insert(0, false);

        let expanded = expand_assignments(&assignments, &var_names, &manifest);
        // Only the original false assignment should be present
        assert_eq!(expanded.len(), 1);
        assert!(!expanded.get(&0).copied().unwrap_or(true));
    }
}


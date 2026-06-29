// Topology extraction — solver assignments → TopologyGraph channel paths.
//
// Origin: U6 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
//
// Extended U5: bundle-variable homomorphism expansion per
// docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md

use std::collections::{HashMap, HashSet};

use crate::types::{InternalBundleManifest, InternalConstraintModel, NetTopology, TopologyGraph};

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
    // Build a set of net names for fast prefix matching.
    let net_name_set: HashSet<&str> = net_names.iter().map(|s| s.as_str()).collect();

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
        if var_name.starts_with("uses_") {
            let rest = &var_name[5..]; // strip "uses_"
            // Try each known net name as a prefix of `rest`.
            let mut best_net: Option<&str> = None;
            let mut best_len: usize = 0;
            for net in &net_name_set {
                if rest.starts_with(*net) && net.len() > best_len {
                    // The character after the net name must be '_' (separator to channel_id).
                    let after = &rest[net.len()..];
                    if after.starts_with('_') {
                        best_net = Some(net);
                        best_len = net.len();
                    }
                }
            }
            if let Some(net) = best_net {
                let channel_id = &rest[best_len + 1..]; // skip net_name + '_'
                if !channel_id.is_empty() {
                    net_channels
                        .entry(net.to_string())
                        .or_default()
                        .push(channel_id.to_string());
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
        if name.starts_with("uses_B") {
            let rest = &name[6..]; // strip "uses_B"
            if let Some(underscore_pos) = rest.find('_') {
                let bid_str = &rest[..underscore_pos];
                let ch = &rest[underscore_pos + 1..];
                if let Ok(bid) = bid_str.parse::<usize>() {
                    if let Some(&idx) = name_to_idx.get(name.as_str()) {
                        if let Some(&val) = assignments.get(&idx) {
                            bundle_ch_vals.entry(bid).or_default().insert(ch.to_string(), val);
                        }
                    }
                }
            }
        }
    }

    // Add per-net variables for each bundle member.
    for bundle in &manifest.bundles {
        if let Some(ch_vals) = bundle_ch_vals.get(&bundle.bundle_id) {
            for (ch, _val) in ch_vals {
                for &ni in &bundle.net_indices {
                    let pn_name = format!("uses_N{ni}_{ch}");
                    // Only add if not already explicitly assigned.
                    if !name_to_idx.contains_key(pn_name.as_str()) {
                        // Need to add to the var list — but we can only
                        // operate on existing indices. Skip for now.
                        let _ = pn_name;
                    }
                    if let Some(&pn_idx) = name_to_idx.get(pn_name.as_str()) {
                        if !expanded.contains_key(&pn_idx) {
                            expanded.insert(pn_idx, true);
                        }
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
                if let Some(bundle) = manifest.bundles.iter().find(|b| b.bundle_id == bid) {
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
        if var_name.starts_with("uses_N") {
            // Format: uses_N{net_idx}_{channel_id}
            let rest = &var_name[6..];
            if let Some(underscore_pos) = rest.find('_') {
                let ni_str = &rest[..underscore_pos];
                let ch = &rest[underscore_pos + 1..];
                if let Ok(ni) = ni_str.parse::<usize>() {
                    if let Some(net_name) = net_names.get(ni) {
                        if !ch.is_empty() {
                            net_channels
                                .entry(net_name.clone())
                                .or_default()
                                .push(ch.to_string());
                        }
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


// Topology extraction — solver assignments → TopologyGraph channel paths.
//
// Origin: U6 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md

use std::collections::{HashMap, HashSet};

use crate::types::{InternalConstraintModel, InternalVariable, NetTopology, TopologyGraph};

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

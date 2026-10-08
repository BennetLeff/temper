//! Current envelopes for a power-branch graph.
//!
//! A bridge has one physically determined current: KCL over either side of
//! the cut gives its signed value.  An edge in a cycle has no determined
//! sharing from nodal injections alone. Under the explicit model assumption
//! that there is no internal circulating current, this module reports the
//! envelope obtained by allowing all positive injection in the component to
//! flow through that edge. `exact` distinguishes those cases; callers must
//! not treat a capacity failure against this model envelope as a definite
//! physical failure.

use std::collections::VecDeque;

/// An undirected copper edge.  `from` and `to` only establish a sign
/// convention for the internal bridge calculation.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Edge {
    pub id: String,
    pub net: String,
    pub from: usize,
    pub to: usize,
}

/// The nodes and edges of one or more same-net connected components.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Graph {
    pub node_count: usize,
    pub edges: Vec<Edge>,
}

/// One waveform sample of nodal injections. Positive values inject current.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Sample {
    pub weight: f64,
    pub injections_a: Vec<f64>,
}

/// RMS and peak current envelope for one edge.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct BranchCurrent {
    pub id: String,
    pub rms_a: f64,
    pub peak_a: f64,
    pub exact: bool,
}

/// Analyze bridge currents and conservative cycle-edge envelopes.
pub fn analyze(graph: &Graph, samples: &[Sample]) -> Result<Vec<BranchCurrent>, String> {
    validate(graph, samples)?;
    let adjacency = adjacency(graph);
    let (component_of, component_nodes) = component_data(graph.node_count, &adjacency);
    let TreeTopology {
        bridges,
        bridge_children,
        order,
        parent,
    } = find_bridges(graph.node_count, &adjacency);
    let mut rms_squared = vec![0.0; graph.edges.len()];
    let mut peak_a = vec![0.0_f64; graph.edges.len()];
    let mut component_positive = vec![0.0; component_nodes.len()];
    for sample in samples {
        let mut subtree = sample.injections_a.clone();
        for &node in order.iter().rev() {
            if let Some(parent_node) = parent[node] {
                subtree[parent_node] += subtree[node];
            }
        }
        for (component_index, nodes) in component_nodes.iter().enumerate() {
            component_positive[component_index] = nodes
                .iter()
                .map(|&node| sample.injections_a[node])
                .filter(|value| *value > 0.0)
                .sum();
        }
        for (edge_index, edge) in graph.edges.iter().enumerate() {
            let current = if let Some(child) = bridge_children[edge_index] {
                subtree[child].abs()
            } else {
                component_positive[component_of[edge.from]]
            };
            rms_squared[edge_index] += sample.weight * current * current;
            peak_a[edge_index] = peak_a[edge_index].max(current);
        }
    }
    Ok(graph
        .edges
        .iter()
        .enumerate()
        .map(|(edge_index, edge)| BranchCurrent {
            id: edge.id.clone(),
            rms_a: rms_squared[edge_index].sqrt(),
            peak_a: peak_a[edge_index],
            exact: bridges[edge_index],
        })
        .collect())
}

fn validate(graph: &Graph, samples: &[Sample]) -> Result<(), String> {
    if graph.node_count == 0 {
        return Err("graph must contain at least one node".into());
    }
    const MAX_NODES: usize = 1_000_000;
    const MAX_EDGES: usize = 2_000_000;
    const MAX_SAMPLES: usize = 100_000;
    const MAX_WORK: usize = 100_000_000;
    if graph.node_count > MAX_NODES || graph.edges.len() > MAX_EDGES || samples.len() > MAX_SAMPLES
    {
        return Err("graph or sample count exceeds analysis bounds".into());
    }
    if graph
        .edges
        .len()
        .saturating_add(graph.node_count)
        .checked_mul(samples.len())
        .is_none_or(|work| work > MAX_WORK)
    {
        return Err("node-and-edge/sample analysis work exceeds bound".into());
    }
    let mut ids = std::collections::HashSet::new();
    for edge in &graph.edges {
        if edge.id.trim().is_empty() || !ids.insert(edge.id.as_str()) {
            return Err("edge IDs must be nonempty and unique".into());
        }
        if edge.net.trim().is_empty() {
            return Err(format!("edge {} has an empty net", edge.id));
        }
        if edge.from >= graph.node_count || edge.to >= graph.node_count {
            return Err(format!("edge {} has an out-of-range node", edge.id));
        }
        if edge.from == edge.to {
            return Err(format!("edge {} is a self-loop", edge.id));
        }
    }
    if samples.is_empty() {
        return Err("at least one sample is required".into());
    }
    let weight_sum: f64 = samples.iter().map(|sample| sample.weight).sum();
    if !weight_sum.is_finite() || (weight_sum - 1.0).abs() > 1e-9 {
        return Err("sample weights must be finite, nonnegative, and sum to one".into());
    }
    for sample in samples {
        if !sample.weight.is_finite() || sample.weight < 0.0 {
            return Err("sample weights must be finite and nonnegative".into());
        }
        if sample.injections_a.len() != graph.node_count {
            return Err("each injection vector must match node_count".into());
        }
        if sample.injections_a.iter().any(|value| !value.is_finite()) {
            return Err("injections must be finite".into());
        }
    }
    let adjacency = adjacency(graph);
    let (component_of, component_nodes) = component_data(graph.node_count, &adjacency);
    let mut component_net: Vec<Option<&str>> = vec![None; component_nodes.len()];
    for edge in graph.edges.iter() {
        let component = component_of[edge.from];
        if component_of[edge.to] != component {
            return Err("edge endpoints have inconsistent component data".into());
        }
        match component_net[component] {
            Some(net) if net != edge.net => {
                return Err(format!("connected component {component} mixes nets"));
            }
            None => component_net[component] = Some(edge.net.as_str()),
            _ => {}
        }
    }
    for (component_index, component) in component_nodes.iter().enumerate() {
        for sample in samples {
            let total: f64 = component
                .iter()
                .map(|&node| sample.injections_a[node])
                .sum();
            let scale: f64 = component
                .iter()
                .map(|&node| sample.injections_a[node].abs())
                .sum();
            if total.abs() > 1e-9 * scale.max(1.0) {
                return Err(format!(
                    "sample injections do not satisfy KCL in component {component_index} on {:?}: residual {total} A, nodes {component:?}", component_net[component_index]
                ));
            }
        }
    }
    Ok(())
}

fn adjacency(graph: &Graph) -> Vec<Vec<(usize, usize)>> {
    let mut result = vec![Vec::new(); graph.node_count];
    for (index, edge) in graph.edges.iter().enumerate() {
        result[edge.from].push((edge.to, index));
        result[edge.to].push((edge.from, index));
    }
    result
}

fn component_data(
    node_count: usize,
    adjacency: &[Vec<(usize, usize)>],
) -> (Vec<usize>, Vec<Vec<usize>>) {
    let mut component_of = vec![0; node_count];
    let mut result = Vec::new();
    let mut seen = vec![false; node_count];
    for start in 0..node_count {
        if seen[start] {
            continue;
        }
        let mut queue = VecDeque::from([start]);
        seen[start] = true;
        let mut component = Vec::new();
        while let Some(node) = queue.pop_front() {
            component.push(node);
            for &(next, _) in &adjacency[node] {
                if !seen[next] {
                    seen[next] = true;
                    queue.push_back(next);
                }
            }
        }
        let index = result.len();
        for &node in &component {
            component_of[node] = index;
        }
        result.push(component);
    }
    (component_of, result)
}

struct TreeTopology {
    bridges: Vec<bool>,
    bridge_children: Vec<Option<usize>>,
    order: Vec<usize>,
    parent: Vec<Option<usize>>,
}
fn find_bridges(node_count: usize, adjacency: &[Vec<(usize, usize)>]) -> TreeTopology {
    let mut discovery = vec![0; node_count];
    let mut low = vec![0; node_count];
    let mut bridges = vec![false; adjacency.iter().flatten().count() / 2];
    let mut bridge_children = vec![None; bridges.len()];
    let mut parent = vec![None; node_count];
    let mut parent_edge = vec![None; node_count];
    let mut order = Vec::with_capacity(node_count);
    let mut clock = 0;
    for node in 0..node_count {
        if discovery[node] != 0 {
            continue;
        }
        clock += 1;
        discovery[node] = clock;
        low[node] = clock;
        order.push(node);
        let mut stack = vec![(node, 0_usize)];
        while let Some((current, next_index)) = stack.last_mut() {
            if *next_index < adjacency[*current].len() {
                let (next, edge) = adjacency[*current][*next_index];
                *next_index += 1;
                if parent_edge[*current] == Some(edge) {
                    continue;
                }
                if discovery[next] == 0 {
                    parent[next] = Some(*current);
                    parent_edge[next] = Some(edge);
                    clock += 1;
                    discovery[next] = clock;
                    low[next] = clock;
                    order.push(next);
                    stack.push((next, 0));
                } else {
                    low[*current] = low[*current].min(discovery[next]);
                }
            } else {
                let (finished, _) = stack.pop().expect("stack is nonempty");
                if let (Some(parent_node), Some(edge)) = (parent[finished], parent_edge[finished]) {
                    low[parent_node] = low[parent_node].min(low[finished]);
                    if low[finished] > discovery[parent_node] {
                        bridges[edge] = true;
                        bridge_children[edge] = Some(finished);
                    }
                }
            }
        }
    }
    TreeTopology {
        bridges,
        bridge_children,
        order,
        parent,
    }
}

#[cfg(test)]
mod tests;

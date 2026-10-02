//! Shortest routed centreline paths through tracks, vias and native pad contacts.
//! Zone interiors are deliberately not replaced with straight-line conductors.
use super::{geometry::distance, require, Result, Snapshot};
use crate::stackup::LayoutStack;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
struct Edge {
    to: usize,
    length: f64,
    resistance: f64,
    object: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Route {
    pub length_mm: f64,
    pub direct_mm: f64,
    pub track_resistance_ohm_20c: f64,
    pub track_objects: Vec<String>,
    pub points_mm: Vec<[f64; 3]>,
}
/// Nodes use KiCad integer nanometres; no proximity merging across gaps.
pub(super) struct Graph {
    positions: Vec<[f64; 3]>,
    edges: Vec<Vec<Edge>>,
    pads: BTreeMap<(String, String), Vec<usize>>,
}
impl Graph {
    pub fn new(snapshot: &Snapshot, stack: &LayoutStack) -> Result<Self> {
        let layers: BTreeMap<_, _> = stack
            .copper
            .iter()
            .enumerate()
            .map(|(i, l)| (l.name.as_str(), (i, l)))
            .collect();
        let mut graph = Self {
            positions: vec![],
            edges: vec![],
            pads: BTreeMap::new(),
        };
        let mut nodes = BTreeMap::new();
        let mut pad_nodes = BTreeMap::new();
        let mut pads: Vec<_> = snapshot.pads.iter().collect();
        pads.sort_by_key(|pad| &pad.uuid);
        for pad in pads {
            for layer in &pad.layers {
                let (_, l) = layers
                    .get(layer.as_str())
                    .ok_or("pad layer absent from stackup")?;
                // Different pads stay distinct even when they share a logical pin.
                let id = graph.add_node([pad.position_mm[0], pad.position_mm[1], l.center_z_mm]);
                graph
                    .pads
                    .entry((pad.reference.clone(), pad.number.clone()))
                    .or_default()
                    .push(id);
                pad_nodes.insert((pad.uuid.as_str(), layer.as_str()), (id, pad));
            }
        }
        let mut tracks: Vec<_> = snapshot.tracks.iter().collect();
        tracks.sort_by_key(|track| &track.uuid);
        for track in tracks {
            let (layer_index, layer) = layers
                .get(track.layer.as_str())
                .ok_or("track layer absent from stackup")?;
            let mut ends = vec![];
            for (position, contacts) in [
                (track.start_mm, &track.start_contacts),
                (track.end_mm, &track.end_contacts),
            ] {
                let key = (
                    track.net.as_str(),
                    *layer_index,
                    nm(position[0])?,
                    nm(position[1])?,
                );
                let node = *nodes.entry(key).or_insert_with(|| {
                    graph.add_node([position[0], position[1], layer.center_z_mm])
                });
                for contact in contacts {
                    let (pad_node, pad) = pad_nodes
                        .get(&(contact.as_str(), track.layer.as_str()))
                        .ok_or("track contact has no flashed pad on its layer")?;
                    require(pad.net == track.net, "native contact crosses net labels")?;
                    graph.connect(
                        node,
                        *pad_node,
                        distance(position, pad.position_mm),
                        0.0,
                        format!("pad:{}", pad.uuid),
                    );
                }
                ends.push(node);
            }
            let resistance = crate::layout_quality::copper::resistance_ohm(
                track.length_mm,
                track.width_mm * layer.thickness_mm,
                1.724e-8,
            )
            .map_err(|e| e.to_string())?;
            graph.connect(
                ends[0],
                ends[1],
                track.length_mm,
                resistance,
                track.uuid.clone(),
            );
        }
        let mut vias: Vec<_> = snapshot.vias.iter().collect();
        vias.sort_by_key(|via| &via.uuid);
        for via in vias {
            let mut attached = vec![];
            for name in &via.layers {
                let (index, layer) = layers
                    .get(name.as_str())
                    .ok_or("via layer absent from stackup")?;
                let key = (
                    via.net.as_str(),
                    *index,
                    nm(via.position_mm[0])?,
                    nm(via.position_mm[1])?,
                );
                let node = *nodes.entry(key).or_insert_with(|| {
                    graph.add_node([via.position_mm[0], via.position_mm[1], layer.center_z_mm])
                });
                attached.push(node);
            }
            attached.sort_by(|a, b| graph.positions[*a][2].total_cmp(&graph.positions[*b][2]));
            for pair in attached.windows(2) {
                let length = (graph.positions[pair[0]][2] - graph.positions[pair[1]][2]).abs();
                graph.connect(pair[0], pair[1], length, 0.0, format!("via:{}", via.uuid));
            }
        }
        Ok(graph)
    }
    fn add_node(&mut self, position: [f64; 3]) -> usize {
        let id = self.positions.len();
        self.positions.push(position);
        self.edges.push(vec![]);
        id
    }
    fn connect(&mut self, a: usize, b: usize, length: f64, resistance: f64, object: String) {
        self.edges[a].push(Edge {
            to: b,
            length,
            resistance,
            object: object.clone(),
        });
        self.edges[b].push(Edge {
            to: a,
            length,
            resistance,
            object,
        });
    }
    pub fn route(&self, from: (&str, &str), to: (&str, &str)) -> Result<Route> {
        let starts = self
            .pads
            .get(&(from.0.into(), from.1.into()))
            .ok_or("source pad absent")?;
        let ends: BTreeSet<_> = self
            .pads
            .get(&(to.0.into(), to.1.into()))
            .ok_or("destination pad absent")?
            .iter()
            .copied()
            .collect();
        require(
            !starts.is_empty() && !ends.is_empty(),
            "endpoint has no flashed layer",
        )?;
        let mut distances = vec![f64::INFINITY; self.edges.len()];
        let mut previous: Vec<Option<(usize, &Edge)>> = vec![None; self.edges.len()];
        let mut queue = std::collections::BinaryHeap::new();
        for &start in starts {
            distances[start] = 0.0;
            queue.push(Visit {
                distance: 0.0,
                node: start,
            });
        }
        while let Some(Visit { distance, node }) = queue.pop() {
            if distance > distances[node] {
                continue;
            }
            if ends.contains(&node) {
                let end = node;
                let mut cursor = node;
                let mut objects = vec![];
                let mut points = vec![self.positions[node]];
                let mut resistance = 0.0;
                while let Some((parent, edge)) = previous[cursor] {
                    resistance += edge.resistance;
                    objects.push(edge.object.clone());
                    points.push(self.positions[parent]);
                    cursor = parent;
                }
                points.reverse();
                objects.reverse();
                let a = self.positions[cursor];
                let b = self.positions[end];
                return Ok(Route {
                    length_mm: distance,
                    direct_mm: (a[0] - b[0]).hypot(a[1] - b[1]).hypot(a[2] - b[2]),
                    track_resistance_ohm_20c: resistance,
                    track_objects: objects,
                    points_mm: points,
                });
            }
            for edge in &self.edges[node] {
                let next = distance + edge.length;
                if next < distances[edge.to] {
                    distances[edge.to] = next;
                    previous[edge.to] = Some((node, edge));
                    queue.push(Visit {
                        distance: next,
                        node: edge.to,
                    });
                }
            }
        }
        Err("no track/via centreline path; zones, interior T-junctions and pad barrels require a fuller conductor model".into())
    }
}
fn nm(v: f64) -> Result<i64> {
    require(
        v.is_finite() && v.abs() < 1e9,
        "native coordinate outside integer key range",
    )?;
    Ok((v * 1e6).round() as i64)
}
#[derive(PartialEq)]
struct Visit {
    distance: f64,
    node: usize,
}
impl Eq for Visit {}
impl Ord for Visit {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        other
            .distance
            .total_cmp(&self.distance)
            .then(other.node.cmp(&self.node))
    }
}
impl PartialOrd for Visit {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

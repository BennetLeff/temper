//! Paths through existing copper, not proposed routing. Triangle edges lie in
//! the filled conductor; reported lengths depend on the mesh and are not L/R.
use super::{geometry::distance, mesh, require, Result, Snapshot};
use crate::stackup::LayoutStack;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CopperPath {
    pub length_mm: f64,
    pub points_mm: Vec<[f64; 3]>,
    pub layers: Vec<String>,
    pub interpretation: String,
}
pub(super) struct Conductors {
    points: Vec<[f64; 3]>,
    layers: Vec<String>,
    adjacency: Vec<Vec<usize>>,
    pads: BTreeMap<(String, String), Vec<usize>>,
}
impl Conductors {
    pub fn new(snapshot: &Snapshot, stack: &LayoutStack) -> Result<Self> {
        let nets: BTreeSet<_> = snapshot
            .pads
            .iter()
            .map(|p| p.net.as_str())
            .filter(|n| !n.is_empty())
            .collect();
        let surfaces = mesh::build(snapshot, &nets.into_iter().collect::<Vec<_>>(), None)?;
        let mut result = Self {
            points: vec![],
            layers: vec![],
            adjacency: vec![],
            pads: BTreeMap::new(),
        };
        let mut contacts: BTreeMap<&str, Vec<Vec<usize>>> = BTreeMap::new();
        let pads: BTreeMap<_, _> = snapshot.pads.iter().map(|p| (p.uuid.as_str(), p)).collect();
        let vias: BTreeMap<_, _> = snapshot.vias.iter().map(|v| (v.uuid.as_str(), v)).collect();
        for surface in &surfaces {
            let z = stack
                .copper
                .iter()
                .find(|l| l.name == surface.layer)
                .ok_or("mesh layer absent")?
                .center_z_mm;
            let offset = result.points.len();
            for p in &surface.vertices {
                result.points.push([p[0], p[1], z]);
                result.layers.push(surface.layer.clone());
                result.adjacency.push(vec![]);
            }
            for t in &surface.triangles {
                for [a, b] in [[t[0], t[1]], [t[1], t[2]], [t[2], t[0]]] {
                    result.connect(offset + a, offset + b);
                }
            }
            for (id, nodes) in &surface.contacts {
                let nodes = nodes.iter().map(|n| n + offset).collect::<Vec<_>>();
                if let Some(pad) = pads.get(id.as_str()) {
                    result
                        .pads
                        .entry((pad.reference.clone(), pad.number.clone()))
                        .or_default()
                        .extend(&nodes);
                    if pad.plated_through {
                        contacts.entry(pad.uuid.as_str()).or_default().push(nodes);
                    }
                } else if let Some(via) = vias.get(id.as_str()) {
                    contacts.entry(via.uuid.as_str()).or_default().push(nodes);
                }
            }
        }
        // Barrel links join contacts on adjacent flashed layers. Their geometry
        // is a centreline witness only, with no assumed barrel resistance.
        for layers in contacts.values_mut() {
            layers.retain(|nodes| !nodes.is_empty());
            layers.sort_by(|a, b| result.points[a[0]][2].total_cmp(&result.points[b[0]][2]));
            for pair in layers.windows(2) {
                let a = pair[0][0];
                let b = *pair[1]
                    .iter()
                    .min_by(|x, y| {
                        let p = result.points[a];
                        distance([p[0], p[1]], [result.points[**x][0], result.points[**x][1]])
                            .total_cmp(&distance(
                                [p[0], p[1]],
                                [result.points[**y][0], result.points[**y][1]],
                            ))
                    })
                    .ok_or("empty barrel layer")?;
                result.connect(a, b);
            }
        }
        for neighbours in &mut result.adjacency {
            neighbours.sort_unstable();
            neighbours.dedup();
        }
        Ok(result)
    }
    fn connect(&mut self, a: usize, b: usize) {
        self.adjacency[a].push(b);
        self.adjacency[b].push(a);
    }
    pub fn route(&self, from: (&str, &str), to: (&str, &str)) -> Result<CopperPath> {
        let starts = self
            .pads
            .get(&(from.0.into(), from.1.into()))
            .ok_or("mesh source pad absent")?;
        let ends: BTreeSet<_> = self
            .pads
            .get(&(to.0.into(), to.1.into()))
            .ok_or("mesh sink pad absent")?
            .iter()
            .copied()
            .collect();
        let mut parent = vec![usize::MAX; self.points.len()];
        let mut queue = VecDeque::new();
        for &n in starts {
            parent[n] = n;
            queue.push_back(n);
        }
        while let Some(n) = queue.pop_front() {
            if ends.contains(&n) {
                let mut nodes = vec![n];
                let mut at = n;
                while parent[at] != at {
                    at = parent[at];
                    nodes.push(at);
                }
                nodes.reverse();
                let points: Vec<_> = nodes.iter().map(|n| self.points[*n]).collect();
                let length = points
                    .windows(2)
                    .map(|p| {
                        (p[0][0] - p[1][0])
                            .hypot(p[0][1] - p[1][1])
                            .hypot(p[0][2] - p[1][2])
                    })
                    .sum();
                require(f64::is_finite(length), "non-finite copper path")?;
                return Ok(CopperPath {
                    length_mm: length,
                    points_mm: points,
                    layers: nodes.iter().map(|n| self.layers[*n].clone()).collect(),
                    interpretation: concat!(
                        "Planar paths on filled-copper triangle edges with abstract barrel ",
                        "links between flashed annuli. Barrel segments are connectivity ",
                        "links, not traced barrel-wall geometry. Mesh-dependent witness, ",
                        "not shortest route, current flow, inductance or resistance."
                    )
                    .into(),
                });
            }
            for &next in &self.adjacency[n] {
                if parent[next] == usize::MAX {
                    parent[next] = n;
                    queue.push_back(next);
                }
            }
        }
        Err("no continuous filled-copper path between physical pad contacts".into())
    }
}

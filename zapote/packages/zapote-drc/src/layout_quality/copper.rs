//! DC current distribution in an explicit lumped copper-resistance graph.
//!
//! Factor once, solve many operating points. This resolves unequal parallel
//! sharing; it does not infer current crowding inside an unmeshed conductor.
//! Skin/proximity effects and temperatures need separate extracted models.
use super::{ensure, finite, identities, positive, Error};
use serde::{Deserialize, Serialize};

/// One uniform conductor section or externally discretized mesh edge.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Edge {
    /// Native copper section identity.
    pub object: String,
    /// Starting node; positive current flows from here to `to`.
    pub from: usize,
    /// Ending node.
    pub to: usize,
    /// Resistance at the specified operating temperature, ohms.
    pub resistance_ohm: f64,
    /// Conducting cross-sectional area, mm², excluding holes.
    pub area_mm2: f64,
}

/// Reusable grounded, diagonally scaled Cholesky factorization.
#[derive(Debug)]
pub struct Network {
    nodes: usize,
    ground: usize,
    edges: Vec<Edge>,
    lower: Vec<f64>,
    scale: Vec<f64>,
}

/// Current, current density and loss in one declared section.
#[derive(Debug, Clone, Serialize)]
pub struct Branch {
    /// Native copper identity.
    pub object: String,
    /// Signed current, A.
    pub current_a: f64,
    /// Magnitude of uniform-section current density, A/mm².
    pub current_density_a_per_mm2: f64,
    /// Resistive loss, W.
    pub loss_w: f64,
}

/// A numerically checked network solution.
#[derive(Debug, Clone, Serialize)]
pub struct Solution {
    /// Node voltages relative to the chosen ground, V.
    pub voltage_v: Vec<f64>,
    /// Branch outputs in input order.
    pub branches: Vec<Branch>,
    /// Sum of branch I²R loss, W.
    pub total_loss_w: f64,
    /// Maximum absolute node KCL residual, including ground, A.
    pub max_kcl_residual_a: f64,
}

fn reduced(node: usize, ground: usize) -> usize {
    node - usize::from(node > ground)
}

impl Network {
    /// Build a connected resistive network. Parallel edges are supported.
    ///
    /// Construction costs O(V³ + E), storage O(V² + E); each solve O(V² + E).
    /// Supports 2..=512 nodes for compact path networks. Larger copper meshes
    /// belong in the existing field-solver pipeline, not a dense factorization.
    ///
    /// # Errors
    /// Rejects missing/duplicate edges, disconnected or numerically singular
    /// graphs, invalid indices, self-loops, nonpositive R/area and overflow.
    pub fn new(nodes: usize, ground: usize, edges: &[Edge]) -> Result<Self, Error> {
        ensure((2..=512).contains(&nodes), "network needs 2..=512 nodes")?;
        ensure(ground < nodes, "ground node is out of range")?;
        ensure(!edges.is_empty(), "copper edge population is empty")?;
        identities(edges.iter().map(|e| e.object.as_str()))?;
        let n = nodes - 1;
        let mut matrix = vec![0.0; n * n];
        let mut adjacency = vec![Vec::new(); nodes];
        for e in edges {
            ensure(
                e.from < nodes && e.to < nodes && e.from != e.to,
                "invalid copper edge endpoints",
            )?;
            let g = finite(
                1.0 / positive(e.resistance_ohm, "resistance_ohm")?,
                "conductance",
            )?;
            positive(e.area_mm2, "area_mm2")?;
            adjacency[e.from].push(e.to);
            adjacency[e.to].push(e.from);
            for (a, b) in [(e.from, e.to), (e.to, e.from)] {
                if a != ground {
                    let i = reduced(a, ground);
                    matrix[i * n + i] += g;
                    if b != ground {
                        matrix[i * n + reduced(b, ground)] -= g;
                    }
                }
            }
        }
        let mut seen = vec![false; nodes];
        let mut queue = vec![ground];
        seen[ground] = true;
        while let Some(node) = queue.pop() {
            for &next in &adjacency[node] {
                if !seen[next] {
                    seen[next] = true;
                    queue.push(next);
                }
            }
        }
        ensure(seen.iter().all(|v| *v), "copper network is disconnected")?;
        let scale: Vec<_> = (0..n).map(|i| matrix[i * n + i].sqrt()).collect();
        for &s in &scale {
            positive(s, "conductance scale")?;
        }
        for i in 0..n {
            for j in 0..n {
                matrix[i * n + j] = finite(
                    matrix[i * n + j] / scale[i] / scale[j],
                    "scaled conductance",
                )?;
            }
        }
        // The lower triangle overwrites the matrix; the upper half is unused.
        for i in 0..n {
            for j in 0..=i {
                let mut value = matrix[i * n + j];
                for k in 0..j {
                    value -= matrix[i * n + k] * matrix[j * n + k];
                }
                matrix[i * n + j] = if i == j {
                    ensure(
                        value > 1e-14,
                        "copper network is numerically ill-conditioned",
                    )?;
                    value.sqrt()
                } else {
                    finite(value / matrix[j * n + j], "factorization")?
                };
            }
        }
        Ok(Self {
            nodes,
            ground,
            edges: edges.to_vec(),
            lower: matrix,
            scale,
        })
    }

    /// Solve one signed current-injection vector (positive means injection).
    /// Currents must sum to zero, including the ground terminal. KCL residuals
    /// are checked at every node with a relative tolerance of 1e-9 of total
    /// absolute injected current; an all-zero load must have zero residual.
    ///
    /// # Errors
    /// Rejects unbalanced/malformed injections, arithmetic overflow, or a solution
    /// whose residual exceeds the stated tolerance.
    pub fn solve(&self, injections_a: &[f64]) -> Result<Solution, Error> {
        ensure(
            injections_a.len() == self.nodes,
            "injection count differs from node count",
        )?;
        for &i in injections_a {
            finite(i, "injection")?;
        }
        let magnitude = finite(
            injections_a.iter().map(|i| i.abs()).sum(),
            "total injected magnitude",
        )?;
        let imbalance = finite(injections_a.iter().sum::<f64>(), "injection sum")?;
        ensure(
            imbalance.abs() <= magnitude * 1e-12,
            "current injections do not balance",
        )?;
        let n = self.nodes - 1;
        let mut x: Vec<_> = injections_a
            .iter()
            .enumerate()
            .filter(|(i, _)| *i != self.ground)
            .map(|(_, v)| *v)
            .collect();
        for i in 0..n {
            x[i] /= self.scale[i];
            for j in 0..i {
                x[i] -= self.lower[i * n + j] * x[j];
            }
            x[i] /= self.lower[i * n + i];
        }
        for i in (0..n).rev() {
            for j in i + 1..n {
                x[i] -= self.lower[j * n + i] * x[j];
            }
            x[i] /= self.lower[i * n + i];
        }
        let mut voltage = vec![0.0; self.nodes];
        for (node, v) in voltage.iter_mut().enumerate() {
            if node != self.ground {
                let i = reduced(node, self.ground);
                *v = finite(x[i] / self.scale[i], "node voltage")?;
            }
        }
        let mut residual: Vec<_> = injections_a.iter().map(|i| -i).collect();
        let mut loss = 0.0;
        let mut branches = Vec::with_capacity(self.edges.len());
        for e in &self.edges {
            let current = finite(
                (voltage[e.from] - voltage[e.to]) / e.resistance_ohm,
                "branch current",
            )?;
            let power = finite(current * current * e.resistance_ohm, "branch loss")?;
            residual[e.from] += current;
            residual[e.to] -= current;
            loss += power;
            branches.push(Branch {
                object: e.object.clone(),
                current_a: current,
                current_density_a_per_mm2: finite(current.abs() / e.area_mm2, "current density")?,
                loss_w: power,
            });
        }
        let mut max_residual: f64 = 0.0;
        for r in residual {
            max_residual = max_residual.max(finite(r, "KCL residual")?.abs());
        }
        ensure(
            max_residual <= magnitude * 1e-9,
            "network solution failed KCL residual check",
        )?;
        Ok(Solution {
            voltage_v: voltage,
            branches,
            total_loss_w: finite(loss, "total loss")?,
            max_kcl_residual_a: max_residual,
        })
    }
}

/// Uniform conductor DC resistance, ρl/A, in ohms. The resistivity must already
/// include the chosen temperature. No skin/proximity or spreading correction.
///
/// # Errors
/// All dimensions and resistivity must be finite and positive.
pub fn resistance_ohm(length_mm: f64, area_mm2: f64, resistivity_ohm_m: f64) -> Result<f64, Error> {
    let r = positive(resistivity_ohm_m, "resistivity_ohm_m")? * positive(length_mm, "length_mm")?
        / positive(area_mm2, "area_mm2")?
        * 1e3;
    positive(r, "conductor resistance")
}

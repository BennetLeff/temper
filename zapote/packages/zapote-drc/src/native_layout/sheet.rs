//! Linear triangular sheet FEM and finite-resistance barrel links. Contacts are
//! ideal equipotential electrodes on each flashed pad/via annulus. This explicit
//! approximation excludes lead/contact resistance and within-annulus crowding.
use super::{mesh::Surface, require, Result, Snapshot};
use crate::stackup::LayoutStack;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Debug, Serialize)]
pub struct SheetSolution {
    pub resistance_ohm: f64,
    pub imposed_current_a: f64,
    pub loss_w: f64,
    pub max_kcl_residual_a: f64,
    pub relative_energy_error: f64,
    pub solver: &'static str,
    pub active_nodes: usize,
    pub unused_nodes: usize,
    pub triangles: usize,
    pub layer_peaks: BTreeMap<String, SheetPeak>,
    pub barrels: Vec<BarrelCurrent>,
}
#[derive(Debug, Serialize)]
pub struct SheetPeak {
    pub current_density_a_per_mm2: f64,
    pub sheet_current_a_per_mm: f64,
    pub location_mm: [f64; 2],
}
#[derive(Debug, Serialize)]
pub struct BarrelCurrent {
    pub uuid: String,
    pub position_mm: [f64; 2],
    pub pad: Option<String>,
    pub from_layer: String,
    pub to_layer: String,
    pub resistance_ohm: f64,
    pub current_a: Option<f64>,
    pub loss_w: Option<f64>,
}
struct UnionFind(Vec<usize>);
impl UnionFind {
    fn root(&mut self, mut n: usize) -> usize {
        while self.0[n] != n {
            self.0[n] = self.0[self.0[n]];
            n = self.0[n];
        }
        n
    }
    fn join(&mut self, a: usize, b: usize) {
        let a = self.root(a);
        let b = self.root(b);
        self.0[a.max(b)] = a.min(b);
    }
    fn electrode(&mut self, nodes: &[usize]) {
        if let Some(&first) = nodes.first() {
            for &n in nodes {
                self.join(first, n);
            }
        }
    }
}
struct Element {
    nodes: [usize; 3],
    b: [f64; 3],
    c: [f64; 3],
    area: f64,
    sheet_s: f64,
    surface: usize,
    center: [f64; 2],
}
type Matrix = Vec<BTreeMap<usize, f64>>;

/// Solve a conditional two-terminal imposed-current experiment on actual copper.
/// Resistivity and plating are supplied assumptions, never inferred fabrication
/// minima. Separate same-net islands are left unused, never joined by net label.
pub(super) fn solve(
    snapshot: &Snapshot,
    stack: &LayoutStack,
    surfaces: &[Surface],
    terminals: [(&str, &str); 2],
    current: f64,
    plating_mm: f64,
    rho: f64,
) -> Result<SheetSolution> {
    require(
        [current, plating_mm, rho]
            .iter()
            .all(|x| x.is_finite() && *x > 0.),
        "invalid current model assumptions",
    )?;
    let mut offsets = vec![];
    let mut n = 0;
    for s in surfaces {
        offsets.push(n);
        n += s.vertices.len();
    }
    require(
        n > 1 && n <= 300_000,
        "sheet node budget exceeded or empty mesh",
    )?;
    let mut uf = UnionFind((0..n).collect());
    let mut contacts: BTreeMap<&str, Vec<(usize, Vec<usize>)>> = BTreeMap::new();
    for (si, s) in surfaces.iter().enumerate() {
        for (uuid, nodes) in &s.contacts {
            let nodes: Vec<_> = nodes.iter().map(|v| v + offsets[si]).collect();
            uf.electrode(&nodes);
            if !nodes.is_empty() {
                contacts.entry(uuid).or_default().push((si, nodes));
            }
        }
    }
    let endpoint = |reference: &str, pin: &str| -> Result<Vec<usize>> {
        let mut nodes = vec![];
        for pad in snapshot
            .pads
            .iter()
            .filter(|p| p.reference == reference && p.number == pin)
        {
            if let Some(layers) = contacts.get(pad.uuid.as_str()) {
                for (_, vertices) in layers {
                    nodes.extend(vertices);
                }
            }
        }
        require(
            !nodes.is_empty(),
            format!("no copper mesh electrode for {reference}.{pin}"),
        )?;
        Ok(nodes)
    };
    let [from, to] = terminals;
    let source = endpoint(from.0, from.1)?;
    let sink = endpoint(to.0, to.1)?;
    uf.electrode(&source);
    uf.electrode(&sink);
    let roots: Vec<_> = (0..n).map(|i| uf.root(i)).collect();
    let mut compact = BTreeMap::new();
    for &root in &roots {
        let next = compact.len();
        compact.entry(root).or_insert(next);
    }
    let ids: Vec<_> = roots.iter().map(|r| compact[r]).collect();
    let source = ids[source[0]];
    let sink = ids[sink[0]];
    require(source != sink, "source and sink electrodes overlap")?;
    let mut matrix: Matrix = vec![BTreeMap::new(); compact.len()];
    let mut elements = vec![];
    for (si, s) in surfaces.iter().enumerate() {
        let thickness = stack
            .copper
            .iter()
            .find(|l| l.name == s.layer)
            .ok_or("sheet layer absent")?
            .thickness_mm;
        let sheet_s = thickness * 1e-3 / rho;
        for &t in &s.triangles {
            let p = t.map(|i| s.vertices[i]);
            let area = ((p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
                - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1]))
                .abs()
                / 2.;
            require(area.is_finite() && area > 0., "degenerate sheet triangle")?;
            let b = [p[1][1] - p[2][1], p[2][1] - p[0][1], p[0][1] - p[1][1]];
            let c = [p[2][0] - p[1][0], p[0][0] - p[2][0], p[1][0] - p[0][0]];
            let nodes = t.map(|i| ids[offsets[si] + i]);
            for i in 0..3 {
                for j in (i + 1)..3 {
                    if nodes[i] == nodes[j] {
                        continue;
                    }
                    let g = -sheet_s * (b[i] * b[j] + c[i] * c[j]) / (4. * area);
                    for (a, z) in [(nodes[i], nodes[j]), (nodes[j], nodes[i])] {
                        *matrix[a].entry(a).or_default() += g;
                        *matrix[a].entry(z).or_default() -= g;
                    }
                }
            }
            elements.push(Element {
                nodes,
                b,
                c,
                area,
                sheet_s,
                surface: si,
                center: [
                    p.iter().map(|v| v[0]).sum::<f64>() / 3.,
                    p.iter().map(|v| v[1]).sum::<f64>() / 3.,
                ],
            });
        }
    }
    let drills: BTreeMap<_, _> = snapshot
        .pads
        .iter()
        .filter(|p| p.plated_through)
        .map(|p| {
            (
                p.uuid.as_str(),
                (
                    p.drill_mm,
                    p.position_mm,
                    Some(format!("{}.{}", p.reference, p.number)),
                ),
            )
        })
        .chain(
            snapshot
                .vias
                .iter()
                .map(|v| (v.uuid.as_str(), ([v.drill_mm; 2], v.position_mm, None))),
        )
        .collect();
    let mut barrel_edges = vec![];
    for (uuid, mut layers) in contacts {
        let Some((drill, position, pad)) = drills.get(uuid) else {
            continue;
        };
        let z = |si: usize| -> f64 {
            stack
                .copper
                .iter()
                .find(|l| l.name == surfaces[si].layer)
                .map_or(f64::NAN, |l| l.center_z_mm)
        };
        layers.sort_by(|a, b| z(a.0).total_cmp(&z(b.0)));
        let perimeter =
            std::f64::consts::PI * drill[0].min(drill[1]) + 2. * (drill[0] - drill[1]).abs();
        let area = plating_mm * perimeter + std::f64::consts::PI * plating_mm * plating_mm;
        for pair in layers.windows(2) {
            let (a, b) = (ids[pair[0].1[0]], ids[pair[1].1[0]]);
            let resistance = crate::layout_quality::copper::resistance_ohm(
                (z(pair[0].0) - z(pair[1].0)).abs(),
                area,
                rho,
            )
            .map_err(|e| e.to_string())?;
            if a != b {
                for (i, j) in [(a, b), (b, a)] {
                    *matrix[i].entry(i).or_default() += 1. / resistance;
                    *matrix[i].entry(j).or_default() -= 1. / resistance;
                }
            }
            barrel_edges.push((
                a,
                b,
                BarrelCurrent {
                    uuid: uuid.into(),
                    position_mm: *position,
                    pad: pad.clone(),
                    from_layer: surfaces[pair[0].0].layer.clone(),
                    to_layer: surfaces[pair[1].0].layer.clone(),
                    resistance_ohm: resistance,
                    current_a: None,
                    loss_w: None,
                },
            ));
        }
    }
    let mut active = BTreeSet::from([sink]);
    let mut queue = VecDeque::from([sink]);
    while let Some(i) = queue.pop_front() {
        for (&j, &g) in &matrix[i] {
            if g != 0. && active.insert(j) {
                queue.push_back(j);
            }
        }
    }
    require(
        active.contains(&source),
        "current source and sink are on disconnected copper islands",
    )?;
    let unit_voltage = dirichlet(&matrix, &active, source, sink)?;
    let boundary_current: f64 = matrix[source]
        .iter()
        .filter(|(j, _)| **j != source)
        .map(|(&j, &g)| g * (unit_voltage[j] - unit_voltage[source]))
        .sum();
    require(
        boundary_current.is_finite() && boundary_current > 0.,
        "nonpositive sheet boundary current",
    )?;
    let scale = current / boundary_current;
    let voltage: Vec<_> = unit_voltage.iter().map(|v| v * scale).collect();
    let mut max_residual = 0_f64;
    for &i in &active {
        let expected = if i == source {
            current
        } else if i == sink {
            -current
        } else {
            0.
        };
        let measured = row_current(&matrix[i], i, &voltage);
        max_residual = max_residual.max((measured - expected).abs());
    }
    require(
        max_residual <= current * 1e-6,
        format!("sheet solution failed true KCL residual check: {max_residual} A at {current} A"),
    )?;
    let mut loss = 0.;
    let mut peaks: BTreeMap<String, SheetPeak> = BTreeMap::new();
    for e in &elements {
        if !active.contains(&e.nodes[0]) {
            continue;
        }
        let gradient = [
            (1..3)
                .map(|i| (voltage[e.nodes[i]] - voltage[e.nodes[0]]) * e.b[i])
                .sum::<f64>()
                / (2. * e.area),
            (1..3)
                .map(|i| (voltage[e.nodes[i]] - voltage[e.nodes[0]]) * e.c[i])
                .sum::<f64>()
                / (2. * e.area),
        ];
        let norm = gradient[0].hypot(gradient[1]);
        loss += e.sheet_s * e.area * norm * norm;
        let density = norm / (rho * 1e3);
        let s = &surfaces[e.surface];
        let peak = peaks.entry(s.layer.clone()).or_insert(SheetPeak {
            current_density_a_per_mm2: 0.,
            sheet_current_a_per_mm: 0.,
            location_mm: [0.; 2],
        });
        if density > peak.current_density_a_per_mm2 {
            peak.current_density_a_per_mm2 = density;
            peak.sheet_current_a_per_mm = norm * e.sheet_s;
            peak.location_mm = e.center;
        }
    }
    let mut barrels = vec![];
    for (a, b, mut barrel) in barrel_edges {
        if active.contains(&a) {
            let i = (voltage[a] - voltage[b]) / barrel.resistance_ohm;
            barrel.current_a = Some(i);
            barrel.loss_w = Some(i * i * barrel.resistance_ohm);
            loss += i * i * barrel.resistance_ohm;
        }
        barrels.push(barrel);
    }
    let source_power = current * scale;
    let energy_error = (loss - source_power).abs() / source_power;
    require(
        energy_error.is_finite() && energy_error < 1e-6,
        "sheet solution failed energy balance",
    )?;
    Ok(SheetSolution {
        resistance_ohm: scale / current,
        imposed_current_a: current,
        loss_w: loss,
        max_kcl_residual_a: max_residual,
        relative_energy_error: energy_error,
        solver: "faer sparse Cholesky, diagonally equilibrated",
        active_nodes: active.len(),
        unused_nodes: matrix.len() - active.len(),
        triangles: elements.len(),
        layer_peaks: peaks,
        barrels,
    })
}

fn dirichlet(
    matrix: &Matrix,
    active: &BTreeSet<usize>,
    source: usize,
    sink: usize,
) -> Result<Vec<f64>> {
    use faer::{
        prelude::Solve,
        sparse::{SparseColMat, Triplet},
        Mat, Side,
    };
    let unknown: Vec<_> = active
        .iter()
        .copied()
        .filter(|i| *i != source && *i != sink)
        .collect();
    let mut voltage = vec![0.; matrix.len()];
    voltage[source] = 1.;
    if unknown.is_empty() {
        return Ok(voltage);
    }
    let mut ids = vec![usize::MAX; matrix.len()];
    for (i, &node) in unknown.iter().enumerate() {
        ids[node] = i;
    }
    let scale: Vec<_> = unknown
        .iter()
        .map(|&i| matrix[i].get(&i).copied().unwrap_or(0.).sqrt())
        .collect();
    require(
        scale.iter().all(|v| v.is_finite() && *v > 0.),
        "invalid sheet diagonal",
    )?;
    let mut triplets = vec![];
    for (i, &node) in unknown.iter().enumerate() {
        for (&other, &g) in &matrix[node] {
            let j = ids[other];
            if j != usize::MAX {
                triplets.push(Triplet::new(i, j, g / (scale[i] * scale[j])));
            }
        }
    }
    let a =
        SparseColMat::<usize, f64>::try_new_from_triplets(unknown.len(), unknown.len(), &triplets)
            .map_err(|e| format!("sheet sparse matrix: {e}"))?;
    let factor = a
        .sp_cholesky(Side::Lower)
        .map_err(|e| format!("sheet Cholesky: {e}"))?;
    let rhs = Mat::from_fn(unknown.len(), 1, |i, _| {
        -matrix[unknown[i]].get(&source).copied().unwrap_or(0.) / scale[i]
    });
    let x = factor.solve(&rhs);
    for (i, &node) in unknown.iter().enumerate() {
        voltage[node] = x[(i, 0)] / scale[i];
    }
    // Refine against the original row-difference operator, avoiding subtraction
    // of large absolute nodal currents near short, high-conductance edges.
    for _ in 0..5 {
        let residual = Mat::from_fn(unknown.len(), 1, |i, _| {
            -row_current(&matrix[unknown[i]], unknown[i], &voltage) / scale[i]
        });
        let correction = factor.solve(&residual);
        for (i, &node) in unknown.iter().enumerate() {
            voltage[node] += correction[(i, 0)] / scale[i];
        }
    }
    require(
        voltage.iter().all(|v| v.is_finite()),
        "non-finite sheet solution",
    )?;
    Ok(voltage)
}

fn row_current(row: &BTreeMap<usize, f64>, node: usize, voltage: &[f64]) -> f64 {
    row.iter()
        .filter(|(other, _)| **other != node)
        .map(|(&other, &g)| g * (voltage[other] - voltage[node]))
        .sum()
}

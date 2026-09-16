//! Independent material/port integration against native geometric primitives.
use crate::shunt_assembly::{Geometry, Scenario};
use anyhow::{ensure, Context, Result};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};
type P = [f64; 3];
fn sub(a: P, b: P) -> P {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn cross(a: P, b: P) -> P {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn dot(a: P, b: P) -> f64 {
    a.into_iter().zip(b).map(|(a, b)| a * b).sum()
}
fn section<'a>(ls: &'a [&str], name: &str) -> Result<&'a [&'a str]> {
    let pos = ls
        .iter()
        .position(|l| *l == format!("${name}"))
        .context("missing mesh section")?;
    let count: usize = ls.get(pos + 1).context("count")?.parse()?;
    let end = pos
        .checked_add(2)
        .and_then(|x| x.checked_add(count))
        .context("count overflow")?;
    ensure!(
        ls.get(end) == Some(&format!("$End{name}").as_str()),
        "mesh section length"
    );
    ls.get(pos + 2..end).context("mesh rows")
}
fn track_distance(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let d = [b[0] - a[0], b[1] - a[1]];
    let t =
        (((p[0] - a[0]) * d[0] + (p[1] - a[1]) * d[1]) / (d[0] * d[0] + d[1] * d[1])).clamp(0., 1.);
    (p[0] - a[0] - t * d[0]).hypot(p[1] - a[1] - t * d[1])
}
fn copper(g: &Geometry, p: [f64; 2], front: bool, tol: f64) -> bool {
    let drilled = g
        .vias
        .iter()
        .any(|v| (p[0] - v.centre[0]).hypot(p[1] - v.centre[1]) < v.drill / 2. - tol);
    !drilled
        && ((!front
            && g.zones
                .iter()
                .zip(&g.zone_bounds)
                .any(|(z, [x0, x1, y0, y1])| {
                    p[0] >= x0 - tol
                        && p[0] <= x1 + tol
                        && p[1] >= y0 - tol
                        && p[1] <= y1 + tol
                        && (crate::shunt_assembly::in_poly(p, z)
                            || z.iter()
                                .zip(z.iter().cycle().skip(1))
                                .take(z.len())
                                .any(|(a, b)| track_distance(p, *a, *b) <= tol))
                }))
            || (front
                && g.local.pad_centres_mm.iter().any(|c| {
                    (p[0] - c[0]).abs() <= 1.75 + tol && (p[1] - c[1]).abs() <= 2.65 + tol
                }))
            || g.tracks
                .iter()
                .filter(|t| t.front == front)
                .any(|t| track_distance(p, t.ends[0], t.ends[1]) <= t.width / 2. + tol)
            || g.vias
                .iter()
                .any(|v| (p[0] - v.centre[0]).hypot(p[1] - v.centre[1]) <= v.diameter / 2. + tol))
}
fn material_at(g: &Geometry, s: &Scenario, p: P, mat: usize) -> bool {
    let [x, y, z] = p.map(|v| v * 1000.);
    let [x0, x1, y0, y1] = g.crop;
    let e = 0.004;
    if x < x0 - e || x > x1 + e || y < y0 - e || y > y1 + e {
        return false;
    }
    let tc = g.local.copper_mm;
    let h = g.board_mm;
    match mat {
        1 => {
            (z >= -1e-6 && z <= tc + 1e-6 && copper(g, [x, y], false, e))
                || (z >= h - tc - 1e-6 && z <= h + 1e-6 && copper(g, [x, y], true, e))
        }
        2 => {
            z >= tc - 1e-6
                && z <= h - tc + 1e-6
                && g.vias.iter().any(|v| {
                    let r = (x - v.centre[0]).hypot(y - v.centre[1]);
                    r >= v.drill / 2. - e && r <= v.drill / 2. + s.plating_mm + e
                })
        }
        3 => {
            z >= tc - 1e-6
                && z <= h - tc + 1e-6
                && !g.vias.iter().any(|v| {
                    (x - v.centre[0]).hypot(y - v.centre[1]) < v.drill / 2. + s.plating_mm - e
                })
        }
        4 | 5 => {
            (x - [80.125, 75.875][mat - 4]).abs() <= 1.45 + 1e-6
                && (y - 132.).abs() <= 2.475 + 1e-6
                && z >= h - 1e-6
                && z <= h + s.solder_mm + 1e-6
        }
        _ => false,
    }
}
fn expected_volumes(g: &Geometry, s: &Scenario) -> [f64; 5] {
    let [x0, x1, y0, y1] = g.crop;
    let dx = (x1 - x0) / 800.;
    let dy = (y1 - y0) / 400.;
    let mut area = 0.;
    for i in 0..800 {
        for j in 0..400 {
            let p = [x0 + (i as f64 + 0.5) * dx, y0 + (j as f64 + 0.5) * dy];
            for front in [false, true] {
                if copper(g, p, front, 0.) {
                    area += dx * dy;
                }
            }
        }
    }
    let tc = g.local.copper_mm;
    let z = g.board_mm - 2. * tc;
    let barrel: f64 = g
        .vias
        .iter()
        .map(|v| {
            std::f64::consts::PI
                * ((v.drill / 2. + s.plating_mm).powi(2) - (v.drill / 2.).powi(2))
                * z
        })
        .sum();
    let holes: f64 = g
        .vias
        .iter()
        .map(|v| std::f64::consts::PI * (v.drill / 2. + s.plating_mm).powi(2) * z)
        .sum();
    [
        area * tc,
        barrel,
        (x1 - x0) * (y1 - y0) * z - holes,
        2.9 * 4.95 * s.solder_mm,
        2.9 * 4.95 * s.solder_mm,
    ]
    .map(|x| x * 1e-9)
}
pub fn validate_elmer(dir: &Path, g: &Geometry, p: &Scenario) -> Result<usize> {
    let converted = crate::shunt_mesh::elmer_as_msh_with(dir, crate::shunt_assembly::read_text)?;
    let original = crate::shunt_assembly::read_text(
        &dir.parent().context("case directory")?.join("local.msh"),
    )?;
    crate::shunt_mesh::assert_same_mesh(&original, &converted)?;
    validate(&converted, g, p)
}
fn projected_distance(p: [f64; 2], ps: [P; 4]) -> f64 {
    let points = ps.map(|p| [p[0] * 1000., p[1] * 1000.]);
    let orient = |a: [f64; 2], b: [f64; 2], c: [f64; 2]| {
        (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    };
    for [i, j, k] in [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]] {
        let [a, b, c] = [points[i], points[j], points[k]];
        if orient(a, b, c).abs() > 1e-18 {
            let v = [orient(a, b, p), orient(b, c, p), orient(c, a, p)];
            if v.iter().all(|v| *v >= 0.) || v.iter().all(|v| *v <= 0.) {
                return 0.;
            }
        }
    }
    let mut d = f64::INFINITY;
    for i in 0..4 {
        for j in i + 1..4 {
            let a = points[i];
            let b = points[j];
            let v = if a == b {
                (p[0] - a[0]).hypot(p[1] - a[1])
            } else {
                track_distance(p, a, b)
            };
            d = d.min(v);
        }
    }
    d
}
fn excludes_drills(ps: [P; 4], mat: usize, g: &Geometry, s: &Scenario) -> bool {
    if mat > 3 {
        return true;
    }
    g.vias.iter().all(|v| {
        let r = v.drill / 2. + if mat == 3 { s.plating_mm } else { 0. };
        // The same 4 um chordal tolerance as the curved-surface transfer.
        let r = r - 0.004;
        let [x, y] = v.centre;
        if ps.iter().all(|p| p[0] * 1000. < x - r)
            || ps.iter().all(|p| p[0] * 1000. > x + r)
            || ps.iter().all(|p| p[1] * 1000. < y - r)
            || ps.iter().all(|p| p[1] * 1000. > y + r)
        {
            return true;
        }
        projected_distance(v.centre, ps) >= r
    })
}
pub fn validate(mesh: &str, g: &Geometry, s: &Scenario) -> Result<usize> {
    ensure!(
        mesh.starts_with("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"),
        "MSH2 ASCII required"
    );
    let ls: Vec<_> = mesh.lines().collect();
    let mut nodes = BTreeMap::<u64, P>::new();
    for row in section(&ls, "Nodes")? {
        let vs: Vec<_> = row.split_whitespace().collect();
        ensure!(vs.len() == 4, "node shape");
        let p = [vs[1].parse()?, vs[2].parse()?, vs[3].parse()?];
        ensure!(p.iter().all(|x: &f64| x.is_finite()), "nonfinite node");
        ensure!(nodes.insert(vs[0].parse()?, p).is_none(), "duplicate node");
    }
    let point = |id: &u64| nodes.get(id).copied().context("missing node");
    let mut faces = BTreeMap::<[u64; 3], Vec<usize>>::new();
    let mut mats = Vec::new();
    let mut vol = [0.; 5];
    let mut cuts = BTreeMap::new();
    let mut tetkeys = BTreeSet::new();
    let mut elemids = BTreeSet::new();
    for row in section(&ls, "Elements")? {
        let f = row
            .split_whitespace()
            .map(str::parse::<u64>)
            .collect::<std::result::Result<Vec<_>, _>>()?;
        ensure!(
            f.len() >= 4 && elemids.insert(f[0]),
            "duplicate/invalid element"
        );
        let tags = usize::try_from(f[2])?;
        ensure!(tags >= 1 && tags <= f.len() - 3, "tags");
        let ns = &f[3 + tags..];
        if f[1] == 4 {
            ensure!(
                ns.len() == 4 && (1..=5).contains(&f[3]),
                "material/tetrahedron census"
            );
            let mat = f[3] as usize;
            let mut key = [ns[0], ns[1], ns[2], ns[3]];
            key.sort_unstable();
            ensure!(
                key.windows(2).all(|x| x[0] != x[1]) && tetkeys.insert(key),
                "duplicate tetrahedron"
            );
            let ps = [
                point(&ns[0])?,
                point(&ns[1])?,
                point(&ns[2])?,
                point(&ns[3])?,
            ];
            let v = dot(
                sub(ps[1], ps[0]),
                cross(sub(ps[2], ps[0]), sub(ps[3], ps[0])),
            )
            .abs()
                / 6.;
            ensure!(v > 1e-24, "degenerate cell");
            vol[mat - 1] += v;
            ensure!(
                excludes_drills(ps, mat, g, s),
                "tetrahedron interior crosses native drilled void"
            );
            if mat == 1 {
                ensure!(
                    ps.iter().all(|p| p[0] < 78.125e-3) || ps.iter().all(|p| p[0] > 78.125e-3),
                    "copper tetrahedron bridges native inter-terminal gap"
                );
            }
            let centroid = std::array::from_fn(|axis| ps.iter().map(|p| p[axis]).sum::<f64>() / 4.);
            ensure!(
                material_at(g, s, centroid, mat),
                "element assigned to wrong physical material {mat} at {centroid:?}"
            );
            for p in ps {
                ensure!(
                    material_at(g, s, p, mat),
                    "node outside physical material {mat} at {p:?}"
                );
            }
            let index = mats.len();
            mats.push(mat);
            for abc in [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]] {
                let mut face = [ns[abc[0]], ns[abc[1]], ns[abc[2]]];
                face.sort_unstable();
                let ad = faces.entry(face).or_default();
                ad.push(index);
                ensure!(ad.len() <= 2, "nonmanifold mesh");
            }
        } else {
            ensure!(
                f[1] == 2 && (13..=15).contains(&f[3]) && ns.len() == 3,
                "unknown boundary"
            );
            let mut face = [ns[0], ns[1], ns[2]];
            face.sort_unstable();
            ensure!(cuts.insert(face, f[3]).is_none(), "duplicate boundary");
        }
    }
    for (i, (actual, expected)) in vol.into_iter().zip(expected_volumes(g, s)).enumerate() {
        ensure!(
            actual > 0. && (actual / expected - 1.).abs() < [0.015, 0.025, 0.001, 1e-6, 1e-6][i],
            "material {} volume {} differs from independent {}",
            i + 1,
            actual,
            expected
        );
    }
    let mut adjacent = vec![Vec::new(); mats.len()];
    let mut interface = BTreeMap::<(usize, usize), f64>::new();
    for (face, ad) in &faces {
        if ad.len() == 2 {
            adjacent[ad[0]].push(ad[1]);
            adjacent[ad[1]].push(ad[0]);
            let a = mats[ad[0]];
            let b = mats[ad[1]];
            if a != b {
                let ps = [point(&face[0])?, point(&face[1])?, point(&face[2])?];
                let c = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]));
                *interface.entry((a.min(b), a.max(b))).or_default() += dot(c, c).sqrt() / 2.;
            }
        }
    }
    for pair in [(1, 2), (1, 3), (1, 4), (1, 5), (2, 3)] {
        ensure!(
            interface.get(&pair).is_some_and(|a| *a > 1e-10),
            "missing shared interface {pair:?}"
        );
    }
    let expected_barrel_contact: f64 = g
        .vias
        .iter()
        .map(|v| {
            2. * std::f64::consts::PI
                * ((v.drill / 2. + s.plating_mm).powi(2) - (v.drill / 2.).powi(2))
                * 1e-6
        })
        .sum();
    ensure!(
        (interface[&(1, 2)] / expected_barrel_contact - 1.).abs() < 0.025,
        "barrel-to-outer-copper contact area differs"
    );
    // All exterior cut faces must be cooled, not only whichever faces the
    // mesher happened to label. Energy balance alone cannot detect missing BCs.
    for (face, ad) in &faces {
        if ad.len() != 1 || ![1, 3].contains(&mats[ad[0]]) {
            continue;
        }
        let ps = [point(&face[0])?, point(&face[1])?, point(&face[2])?];
        if [
            (0, g.crop[0]),
            (0, g.crop[1]),
            (1, g.crop[2]),
            (1, g.crop[3]),
        ]
        .iter()
        .any(|(axis, v)| ps.iter().all(|p| (p[*axis] - v * 1e-3).abs() < 1e-10))
        {
            ensure!(
                cuts.get(face) == Some(&13),
                "unlabeled exterior cooling face"
            );
        }
    }
    for pair in [(1, 4), (1, 5)] {
        ensure!(
            (interface[&pair] / (2.9 * 4.95 * 1e-6) - 1.).abs() < 1e-6,
            "solder contact area differs"
        );
    }
    let mut heat_area = [0.; 2];
    let mut substrate_cut = [0.; 4];
    let mut cooled = BTreeSet::new();
    for (face, tag) in cuts {
        let ad = faces.get(&face).context("detached boundary")?;
        ensure!(ad.len() == 1, "internal cooling boundary");
        let ps = [point(&face[0])?, point(&face[1])?, point(&face[2])?];
        if tag != 13 {
            let i = (tag - 14) as usize;
            ensure!(
                mats[ad[0]] == i + 4
                    && ps
                        .iter()
                        .all(|p| (p[2] - (g.board_mm + s.solder_mm) * 1e-3).abs() < 1e-10),
                "heat injection not on exterior solder top"
            );
            let c = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]));
            heat_area[i] += dot(c, c).sqrt() / 2.;
            continue;
        }
        cooled.insert(ad[0]);
        let side = [
            (0, g.crop[0]),
            (0, g.crop[1]),
            (1, g.crop[2]),
            (1, g.crop[3]),
        ]
        .iter()
        .position(|(axis, v)| ps.iter().all(|p| (p[*axis] - v * 1e-3).abs() < 1e-10))
        .context("cooling boundary away from crop face")?;
        ensure!(
            mats[ad[0]] == 1 || mats[ad[0]] == 3,
            "unexpected cooled material"
        );
        if mats[ad[0]] == 3 {
            let c = cross(sub(ps[1], ps[0]), sub(ps[2], ps[0]));
            substrate_cut[side] += dot(c, c).sqrt() / 2.;
        }
    }
    for a in heat_area {
        ensure!(
            (a / (2.9 * 4.95 * 1e-6) - 1.).abs() < 1e-6,
            "heat injection area mismatch"
        );
    }
    let z = g.board_mm - 2. * g.local.copper_mm;
    for (i, a) in substrate_cut.into_iter().enumerate() {
        let length = if i < 2 {
            g.crop[3] - g.crop[2]
        } else {
            g.crop[1] - g.crop[0]
        };
        ensure!(
            (a / (length * z * 1e-6) - 1.).abs() < 1e-6,
            "incomplete board cooling face"
        );
    }
    let mut visited = BTreeSet::new();
    let mut stack = vec![0];
    while let Some(i) = stack.pop() {
        if visited.insert(i) {
            stack.extend(adjacent[i].iter().copied());
        }
    }
    ensure!(
        visited.len() == mats.len() && !cooled.is_empty(),
        "disconnected or uncooled solid"
    );
    Ok(nodes.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    fn reference() -> (String, Geometry, Scenario) {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power-entry");
        let native = fs::read(root.join("shunt-repair/evidence/native-04.json")).unwrap();
        let g = crate::shunt_assembly::geometry(&native, false).unwrap();
        let p = crate::shunt_assembly::scenarios().remove(0);
        let mesh = crate::shunt_assembly::read_text(
            &root.join("shunt-assembly/run-15/nominal-100/local.msh"),
        )
        .unwrap();
        (mesh, g, p)
    }
    fn mutate_tag(mesh: &str, kind: &str, old: &str, new: &str) -> String {
        let mut in_elements = false;
        let mut changed = false;
        let out = mesh
            .lines()
            .map(|line| {
                if line == "$Elements" {
                    in_elements = true;
                    return line.to_owned();
                }
                if line == "$EndElements" {
                    in_elements = false;
                }
                let mut f: Vec<_> = line.split_whitespace().collect();
                if in_elements && !changed && f.len() > 4 && f[1] == kind && f[3] == old {
                    f[3] = new;
                    changed = true;
                    f.join(" ")
                } else {
                    line.to_owned()
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
            + "\n";
        assert!(changed);
        out
    }
    #[test]
    fn real_solver_mesh_has_correct_materials_and_exterior_ports() {
        let (m, g, p) = reference();
        assert!(validate(&m, &g, &p).unwrap() > 10000);
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../power-entry/shunt-assembly/run-15/nominal-100/mesh");
        validate_elmer(&path, &g, &p).unwrap();
        assert!(crate::shunt_mesh::assert_same_mesh(&m, &mutate_tag(&m, "4", "2", "3")).is_err());
    }
    #[test]
    fn wrong_material_or_misplaced_heat_port_is_rejected() {
        let (m, g, p) = reference();
        for (kind, old, new) in [
            ("4", "2", "3"),
            ("4", "4", "1"),
            ("2", "13", "14"),
            ("2", "14", "13"),
        ] {
            assert!(
                validate(&mutate_tag(&m, kind, old, new), &g, &p).is_err(),
                "{kind}/{old}/{new}"
            );
        }
    }
    #[test]
    fn native_drill_and_plating_change_invalidates_retained_mesh() {
        let (m, mut g, mut p) = reference();
        g.vias[0].drill = 0.6;
        assert!(validate(&m, &g, &p).is_err());
        let (_, g, _) = reference();
        p.plating_mm = 0.05;
        assert!(validate(&m, &g, &p).is_err());
    }
    #[test]
    fn historical_mesh_that_treated_mask_as_substrate_is_rejected() {
        let (_, g, p) = reference();
        let old = crate::shunt_assembly::read_text(
            &Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../power-entry/shunt-assembly/run-06/nominal-800/local.msh"),
        )
        .unwrap();
        assert!(validate(&old, &g, &p).is_err());
    }
    #[test]
    fn convex_tetrahedron_crossing_hole_fails_even_when_vertices_and_centroid_are_outside() {
        let (_, g, p) = reference();
        let [x, y] = g.vias[0].centre;
        let points = [
            [x - 1., y + 0.2, 0.3],
            [x + 1., y + 0.2, 0.3],
            [x, y + 1., 0.3],
            [x, y + 1., 1.],
        ]
        .map(|p| p.map(|v| v * 1e-3));
        let centroid = std::array::from_fn(|axis| points.iter().map(|p| p[axis]).sum::<f64>() / 4.);
        assert!(points.iter().all(|pt| material_at(&g, &p, *pt, 3)));
        assert!(material_at(&g, &p, centroid, 3));
        assert!(!excludes_drills(points, 3, &g, &p));
    }
}

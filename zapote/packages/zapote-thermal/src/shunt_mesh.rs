//! Independent integration of linear mesh cells, checked against native lands.
use crate::shunt_local::Geometry;
use anyhow::{ensure, Context, Result};
use std::collections::{BTreeMap, BTreeSet};
use std::{fs, path::Path};

/// Validate the actual solver mesh too: conversion is part of the apparatus.
pub fn validate_elmer(dir: &Path, g: &Geometry) -> Result<usize> {
    validate(&elmer_as_msh(dir)?, g)
}

pub(crate) fn elmer_as_msh(dir: &Path) -> Result<String> {
    elmer_as_msh_with(dir, |p| Ok(fs::read_to_string(p)?))
}

pub(crate) fn elmer_as_msh_with(
    dir: &Path,
    read: impl Fn(&Path) -> Result<String>,
) -> Result<String> {
    let header = read(&dir.join("mesh.header"))?;
    let counts: Vec<usize> = header
        .lines()
        .next()
        .context("mesh header")?
        .split_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<_, _>>()?;
    ensure!(counts.len() == 3, "Elmer mesh header census");
    let mut nodes = Vec::new();
    for row in read(&dir.join("mesh.nodes"))?.lines() {
        let f: Vec<_> = row.split_whitespace().collect();
        ensure!(f.len() == 5, "Elmer node columns");
        nodes.push(format!("{} {} {} {}", f[0], f[2], f[3], f[4]));
    }
    let mut cells = Vec::new();
    for row in read(&dir.join("mesh.elements"))?.lines() {
        let f: Vec<_> = row.split_whitespace().collect();
        ensure!(
            f.len() == 7 && f[2] == "504",
            "linear Elmer tetrahedron required"
        );
        cells.push(format!(
            "{} 4 1 {} {}",
            cells.len() + 1,
            f[1],
            f[3..].join(" ")
        ));
    }
    let bulk_count = cells.len();
    for row in read(&dir.join("mesh.boundary"))?.lines() {
        let f: Vec<_> = row.split_whitespace().collect();
        ensure!(
            f.len() == 8 && f[4] == "303",
            "linear Elmer boundary required"
        );
        cells.push(format!(
            "{} 2 1 {} {}",
            cells.len() + 1,
            f[1],
            f[5..].join(" ")
        ));
    }
    ensure!(
        counts == [nodes.len(), bulk_count, cells.len() - bulk_count],
        "Elmer mesh header differs from actual files"
    );
    let mesh=format!("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n{}\n{}\n$EndNodes\n$Elements\n{}\n{}\n$EndElements\n",nodes.len(),nodes.join("\n"),cells.len(),cells.join("\n"));
    Ok(mesh)
}

type Point = [f64; 3];
/// ElmerGrid's pinned conversion preserves node IDs. Compare coordinates and
/// complete material/port connectivity, allowing only ASCII rounding and
/// element/vertex reordering. Two independently plausible meshes are not enough.
pub(crate) fn assert_same_mesh(source: &str, converted: &str) -> Result<()> {
    type MeshIdentity = (BTreeMap<u64, Point>, Vec<Vec<u64>>);
    fn identity(text: &str) -> Result<MeshIdentity> {
        let lines: Vec<_> = text.lines().collect();
        let mut nodes = BTreeMap::new();
        for line in section(&lines, "Nodes")? {
            let f: Vec<_> = line.split_whitespace().collect();
            ensure!(f.len() == 4, "node identity shape");
            ensure!(
                nodes
                    .insert(f[0].parse()?, [f[1].parse()?, f[2].parse()?, f[3].parse()?])
                    .is_none(),
                "duplicate identity node"
            );
        }
        let mut cells = Vec::new();
        for line in section(&lines, "Elements")? {
            let f: Vec<u64> = line
                .split_whitespace()
                .map(str::parse)
                .collect::<std::result::Result<_, _>>()?;
            ensure!(
                f.len() >= 4 && f[2] >= 1 && f[2] as usize <= f.len() - 3,
                "element identity shape"
            );
            let mut ids = f[3 + f[2] as usize..].to_vec();
            ids.sort_unstable();
            let mut key = vec![f[1], f[3]];
            key.extend(ids);
            cells.push(key);
        }
        cells.sort_unstable();
        Ok((nodes, cells))
    }
    let (a, ac) = identity(source)?;
    let (b, bc) = identity(converted)?;
    ensure!(
        a.len() == b.len() && ac == bc,
        "Elmer mesh topology/materials/ports differ from Gmsh"
    );
    for (id, p) in a {
        let q = b.get(&id).context("Elmer node ID differs")?;
        ensure!(
            p.iter()
                .zip(q)
                // ElmerGrid writes these metre coordinates to 12 decimal
                // places: allow at most one picometre of ASCII rounding.
                .all(|(a, b)| a.is_finite() && b.is_finite() && (a - b).abs() < 1e-12),
            "Elmer node coordinates differ from Gmsh"
        );
    }
    Ok(())
}
fn sub(a: Point, b: Point) -> Point {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn cross(a: Point, b: Point) -> Point {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}
fn dot(a: Point, b: Point) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}
fn section<'a>(lines: &'a [&str], name: &str) -> Result<&'a [&'a str]> {
    let at = lines
        .iter()
        .position(|l| *l == format!("${name}"))
        .context("missing section")?;
    let n: usize = lines.get(at + 1).context("missing count")?.parse()?;
    let end = at
        .checked_add(2)
        .and_then(|s| s.checked_add(n))
        .context("count overflow")?;
    ensure!(
        lines.get(end) == Some(&format!("$End{name}").as_str()),
        "section count mismatch"
    );
    lines.get(at + 2..end).context("truncated section")
}
fn close(a: f64, b: f64, t: f64) -> Result<()> {
    ensure!(
        a.is_finite() && b > 0. && (a / b - 1.).abs() < t,
        "mesh measure {a:e} differs from expected {b:e}"
    );
    Ok(())
}
// Numerical quadrature of native rectangle/capsule unions, independent of
// the mesher's Boolean operations. This is a transfer check, not thermal FEM.
fn expected_total(g: &Geometry) -> f64 {
    (0..2)
        .map(|i| {
            let c = g.pad_centres_mm[i][0];
            let [a, b] = g.tracks_mm[i];
            let r = g.widths_mm[i] / 2.;
            let lo = (c - 1.75).min(a[0]).min(b[0] - r);
            let hi = (c + 1.75).max(a[0]).max(b[0] + r);
            let dx = (hi - lo) / 20000.;
            (0..20000)
                .map(|j| {
                    let x = lo + (j as f64 + 0.5) * dx;
                    let pad = if (x - c).abs() <= 1.75 { 2.65_f64 } else { 0. };
                    let rect = if x >= a[0].min(b[0]) && x <= a[0].max(b[0]) {
                        r
                    } else {
                        0.
                    };
                    let cap = (r * r - (x - b[0]).powi(2)).max(0.).sqrt();
                    2. * pad.max(rect).max(cap) * dx * g.copper_mm * 1e-9
                })
                .sum::<f64>()
        })
        .sum()
}

pub fn validate(mesh: &str, g: &Geometry) -> Result<usize> {
    ensure!(
        mesh.starts_with("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"),
        "ASCII linear MSH2 required"
    );
    let lines: Vec<_> = mesh.lines().collect();
    let mut nodes = BTreeMap::<u64, Point>::new();
    for row in section(&lines, "Nodes")? {
        let v: Vec<_> = row.split_whitespace().collect();
        ensure!(v.len() == 4, "node columns");
        let p = [v[1].parse()?, v[2].parse()?, v[3].parse()?];
        ensure!(p.iter().all(|x: &f64| x.is_finite()), "nonfinite node");
        ensure!(nodes.insert(v[0].parse()?, p).is_none(), "duplicate node");
    }
    ensure!(!nodes.is_empty(), "empty mesh");
    let point = |id: &u64| nodes.get(id).copied().context("missing node");
    let mut ids = BTreeSet::new();
    let mut tets = BTreeSet::new();
    let mut faces = BTreeMap::<[u64; 3], Vec<usize>>::new();
    let mut boundaries = BTreeSet::new();
    let mut volumes = [0.; 3];
    let mut tet_sides = Vec::new();
    for row in section(&lines, "Elements")? {
        let f: Vec<_> = row
            .split_whitespace()
            .map(str::parse::<u64>)
            .collect::<std::result::Result<_, _>>()?;
        ensure!(f.len() >= 4 && ids.insert(f[0]), "bad/duplicate element");
        let tags = usize::try_from(f[2])?;
        ensure!(tags >= 1 && tags <= f.len() - 3, "bad tags");
        let n = &f[3 + tags..];
        if f[1] == 4 {
            ensure!(
                n.len() == 4 && (1..=3).contains(&f[3]),
                "tetrahedron/material required"
            );
            let mut key = [n[0], n[1], n[2], n[3]];
            key.sort_unstable();
            ensure!(
                key.windows(2).all(|p| p[0] != p[1]) && tets.insert(key),
                "duplicate/degenerate tet"
            );
            let p = [point(&n[0])?, point(&n[1])?, point(&n[2])?, point(&n[3])?];
            let v = dot(sub(p[1], p[0]), cross(sub(p[2], p[0]), sub(p[3], p[0]))).abs() / 6.;
            ensure!(v > 1e-24, "zero volume");
            volumes[f[3] as usize - 1] += v;
            let side =
                if p.iter().all(|p| {
                    p[0] >= (g.pad_centres_mm[0][0] + g.pad_centres_mm[1][0]) / 2000. - 1e-10
                }) {
                    0
                } else if p.iter().all(|p| {
                    p[0] <= (g.pad_centres_mm[0][0] + g.pad_centres_mm[1][0]) / 2000. + 1e-10
                }) {
                    1
                } else {
                    anyhow::bail!("mesh bridges shunt gap")
                };
            // Coordinates are checked against actual copper primitives, not
            // merely a domain bounding box which could contain filled gaps.
            for p in p {
                let x = p[0] * 1000.;
                let y = p[1] * 1000.;
                let c = g.pad_centres_mm[side];
                let [a, b] = g.tracks_mm[side];
                let r = g.widths_mm[side] / 2.;
                let e = 1e-6;
                let pad = (x - c[0]).abs() <= 1.75 + e && (y - c[1]).abs() <= 2.65 + e;
                let track = (x >= a[0].min(b[0]) - e
                    && x <= a[0].max(b[0]) + e
                    && (y - c[1]).abs() <= r + e)
                    || ((x - b[0]).hypot(y - b[1]) <= r + e);
                ensure!(
                    (pad || track) && p[2] >= -1e-12 && p[2] <= g.copper_mm / 1000. + 1e-12,
                    "node outside copper"
                );
                if f[3] < 3 {
                    ensure!(
                        f[3] as usize == side + 1 && pad,
                        "heat source outside assigned pad"
                    );
                }
            }
            let id = tet_sides.len();
            tet_sides.push(side);
            for a in [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]] {
                let mut face = [n[a[0]], n[a[1]], n[a[2]]];
                face.sort_unstable();
                let adjacent = faces.entry(face).or_default();
                adjacent.push(id);
                ensure!(adjacent.len() <= 2, "nonmanifold mesh");
            }
        } else {
            ensure!(
                f[1] == 2 && f[3] == 13 && n.len() == 3,
                "unexpected boundary element"
            );
            let mut face = [n[0], n[1], n[2]];
            face.sort_unstable();
            ensure!(boundaries.insert(face), "duplicate boundary");
        }
    }
    let pad_vol = 3.5 * 5.3 * g.copper_mm * 1e-9;
    close(volumes[0], pad_vol, 1e-7)?;
    close(volumes[1], pad_vol, 1e-7)?;
    ensure!(volumes[2] > 0., "missing trace copper");
    close(volumes.iter().sum(), expected_total(g), 0.015)?;
    let mut areas = [0.; 2];
    let mut cut_tets = BTreeSet::new();
    for face in boundaries {
        let incident = faces.get(&face).context("detached boundary")?;
        ensure!(incident.len() == 1, "internal boundary clamp");
        let side = tet_sides[incident[0]];
        cut_tets.insert(incident[0]);
        let p = [point(&face[0])?, point(&face[1])?, point(&face[2])?];
        ensure!(
            p.iter()
                .all(|p| (p[0] - g.tracks_mm[side][0][0] / 1000.).abs() < 1e-10),
            "boundary not at native cut"
        );
        let a = cross(sub(p[1], p[0]), sub(p[2], p[0]));
        areas[side] += dot(a, a).sqrt() / 2.;
    }
    for (i, area) in areas.iter().enumerate() {
        close(*area, g.widths_mm[i] * g.copper_mm * 1e-6, 1e-7)?;
    }
    let mut adjacent = vec![Vec::new(); tet_sides.len()];
    for v in faces.values().filter(|v| v.len() == 2) {
        adjacent[v[0]].push(v[1]);
        adjacent[v[1]].push(v[0]);
    }
    let mut visited = BTreeSet::new();
    let mut domains = 0;
    for start in 0..tet_sides.len() {
        if visited.contains(&start) {
            continue;
        }
        domains += 1;
        let mut stack = vec![start];
        let mut cut = false;
        while let Some(id) = stack.pop() {
            if !visited.insert(id) {
                continue;
            }
            cut |= cut_tets.contains(&id);
            stack.extend(adjacent[id].iter().copied());
        }
        ensure!(cut, "uncooled disconnected domain");
    }
    ensure!(domains == 2, "expected two separate copper domains");
    Ok(nodes.len())
}

//! Fail-closed proof that Gmsh topology survived the ElmerGrid transfer.
//!
//! ElmerGrid's native mesh files are intentionally checked against the source
//! Gmsh 2.2 file as multisets, rather than trusting element counts alone.  A
//! renumbered node, changed material tag, or boundary attached to the wrong
//! parent therefore cannot reach the solver unnoticed.

use anyhow::{bail, ensure, Context, Result};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

type Point = [f64; 3];
type Tet = (usize, [u64; 4]);
type Tri = (usize, [u64; 3]);
type Boundary = (usize, usize, usize, usize, [u64; 3]);

/// Verify a Gmsh 2.2 mesh against an ElmerGrid directory.
///
/// The directory must contain `mesh.header`, `mesh.nodes`, `mesh.elements`,
/// and `mesh.boundary`.  Gmsh physical volume tags 1/2 and boundary tags
/// 11/12/13 are retained as Elmer body/boundary tags.  All source IDs and
/// coordinates are preserved exactly (coordinates allow only `1e-12` roundoff).
pub fn verify(gmsh: &str, elmer_dir: &Path) -> Result<()> {
    let source = parse_gmsh(gmsh)?;
    let header = read_required(elmer_dir.join("mesh.header"))?;
    let nodes = read_required(elmer_dir.join("mesh.nodes"))?;
    let elements = read_required(elmer_dir.join("mesh.elements"))?;
    let boundary = read_required(elmer_dir.join("mesh.boundary"))?;
    let (node_count, element_count, boundary_count) = parse_header(&header)?;
    let target_nodes = parse_elmer_nodes(&nodes)?;
    let target_elements = parse_elmer_elements(&elements)?;
    let target_boundary = parse_elmer_boundary(&boundary)?;
    ensure!(
        target_nodes.len() == node_count,
        "Elmer node count differs from mesh.header"
    );
    ensure!(
        target_elements.len() == element_count,
        "Elmer element count differs from mesh.header"
    );
    ensure!(
        target_boundary.len() == boundary_count,
        "Elmer boundary count differs from mesh.header"
    );
    ensure!(
        target_nodes.len() == source.nodes.len(),
        "Gmsh/Elmer node count differs"
    );
    for (id, point) in &source.nodes {
        let Some(target) = target_nodes.get(id) else {
            bail!("ElmerGrid renumbered or dropped Gmsh node {id}")
        };
        ensure!(
            point
                .iter()
                .zip(target)
                .all(|(a, b)| (a - b).abs() <= 1e-12),
            "ElmerGrid changed coordinates for node {id}"
        );
    }
    ensure!(
        source.nodes.keys().eq(target_nodes.keys()),
        "Elmer node ID set differs from Gmsh"
    );
    ensure!(
        same_multiset(&source.tets, &target_elements),
        "Elmer volume topology/material tags differ from Gmsh"
    );
    ensure!(
        same_boundary_multiset(&source.tris, &target_boundary),
        "Elmer boundary topology/tags differ from Gmsh"
    );
    let element_ids: BTreeSet<usize> = target_elements.iter().map(|(id, _, _)| *id).collect();
    let parents: BTreeMap<_, _> = target_elements
        .iter()
        .map(|(id, _, tet)| (*id, *tet))
        .collect();
    ensure!(
        element_ids.len() == target_elements.len(),
        "Elmer element IDs are not unique"
    );
    let mut source_faces = BTreeMap::<[u64; 3], usize>::new();
    for (_, _, tet) in &target_elements {
        for face in tet_faces(*tet) {
            let mut key = face;
            key.sort_unstable();
            *source_faces.entry(key).or_default() += 1;
        }
    }
    let mut boundary_ids = BTreeSet::new();
    for (id, tag, parent, second_parent, tri) in target_boundary {
        ensure!(boundary_ids.insert(id), "Elmer boundary IDs are not unique");
        ensure!(
            (11..=13).contains(&tag),
            "unexpected Elmer boundary tag {tag}"
        );
        ensure!(
            second_parent == 0,
            "exterior boundary {id} has a second parent"
        );
        ensure!(
            element_ids.contains(&parent),
            "boundary {id} references missing parent element {parent}"
        );
        ensure!(
            tri.iter().all(|node| parents[&parent].contains(node)),
            "boundary {id} triangle is not a face of its claimed parent"
        );
        let mut key = tri;
        key.sort_unstable();
        ensure!(
            source_faces.get(&key) == Some(&1),
            "boundary {id} is not a unique exterior face of its parent"
        );
    }
    Ok(())
}

#[derive(Debug)]
struct GmshMesh {
    nodes: BTreeMap<u64, Point>,
    tets: Vec<Tet>,
    tris: Vec<Tri>,
}

fn parse_gmsh(text: &str) -> Result<GmshMesh> {
    let lines: Vec<&str> = text.lines().collect();
    let nodes_pos = lines
        .iter()
        .position(|line| line.trim() == "$Nodes")
        .context("Gmsh $Nodes missing")?;
    let node_count: usize = lines
        .get(nodes_pos + 1)
        .context("Gmsh node count missing")?
        .trim()
        .parse()?;
    let mut nodes = BTreeMap::new();
    for line in lines.iter().skip(nodes_pos + 2).take(node_count) {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(fields.len() == 4, "malformed Gmsh node row");
        let id: u64 = fields[0].parse()?;
        ensure!(
            nodes
                .insert(
                    id,
                    [fields[1].parse()?, fields[2].parse()?, fields[3].parse()?]
                )
                .is_none(),
            "duplicate Gmsh node ID {id}"
        );
    }
    let elem_pos = lines
        .iter()
        .position(|line| line.trim() == "$Elements")
        .context("Gmsh $Elements missing")?;
    let elem_count: usize = lines
        .get(elem_pos + 1)
        .context("Gmsh element count missing")?
        .trim()
        .parse()?;
    let mut tets = Vec::new();
    let mut tris = Vec::new();
    for line in lines.iter().skip(elem_pos + 2).take(elem_count) {
        let fields: Vec<_> = line.split_whitespace().collect();
        ensure!(fields.len() >= 3, "malformed Gmsh element row");
        let id: usize = fields[0].parse()?;
        let kind: usize = fields[1].parse()?;
        let tags: usize = fields[2].parse()?;
        ensure!(tags > 0, "Gmsh element has no physical tag");
        ensure!(fields.len() >= 3 + tags, "truncated Gmsh element tags");
        let physical: usize = fields
            .get(3)
            .context("Gmsh element has no physical tag")?
            .parse()?;
        let nodes = &fields[3 + tags..];
        match kind {
            4 => {
                ensure!(
                    nodes.len() == 4,
                    "Gmsh tetrahedron does not have four nodes"
                );
                let mut tet = [
                    nodes[0].parse()?,
                    nodes[1].parse()?,
                    nodes[2].parse()?,
                    nodes[3].parse()?,
                ];
                tet.sort_unstable();
                ensure!(
                    matches!(physical, 1 | 2),
                    "unexpected Gmsh volume tag {physical}"
                );
                tets.push((physical, tet));
            }
            2 => {
                ensure!(nodes.len() == 3, "Gmsh triangle does not have three nodes");
                let mut tri = [nodes[0].parse()?, nodes[1].parse()?, nodes[2].parse()?];
                tri.sort_unstable();
                ensure!(
                    (11..=13).contains(&physical),
                    "unexpected Gmsh boundary tag {physical}"
                );
                tris.push((physical, tri));
            }
            _ => {}
        }
        let _ = id;
    }
    ensure!(
        !tets.is_empty() && !tris.is_empty(),
        "Gmsh mesh has no tetrahedra or boundary triangles"
    );
    Ok(GmshMesh { nodes, tets, tris })
}

fn parse_header(text: &str) -> Result<(usize, usize, usize)> {
    let fields: Vec<_> = text.split_whitespace().collect();
    ensure!(fields.len() >= 3, "Elmer mesh.header requires three counts");
    Ok((fields[0].parse()?, fields[1].parse()?, fields[2].parse()?))
}

fn parse_elmer_nodes(text: &str) -> Result<BTreeMap<u64, Point>> {
    let mut result = BTreeMap::new();
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let f: Vec<_> = line.split_whitespace().collect();
        ensure!(f.len() == 5, "malformed Elmer mesh.nodes row");
        let id: u64 = f[0].parse()?;
        ensure!(f[1] == "-1", "unexpected Elmer node marker");
        ensure!(
            result
                .insert(id, [f[2].parse()?, f[3].parse()?, f[4].parse()?])
                .is_none(),
            "duplicate Elmer node ID {id}"
        );
    }
    Ok(result)
}

fn parse_elmer_elements(text: &str) -> Result<Vec<(usize, usize, [u64; 4])>> {
    let mut result = Vec::new();
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let f: Vec<_> = line.split_whitespace().collect();
        ensure!(f.len() == 7, "malformed Elmer mesh.elements row");
        let id: usize = f[0].parse()?;
        let body: usize = f[1].parse()?;
        ensure!(f[2] == "504", "unexpected Elmer volume element type");
        let mut tet = [f[3].parse()?, f[4].parse()?, f[5].parse()?, f[6].parse()?];
        tet.sort_unstable();
        result.push((id, body, tet));
    }
    Ok(result)
}

fn parse_elmer_boundary(text: &str) -> Result<Vec<Boundary>> {
    let mut result = Vec::new();
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        let f: Vec<_> = line.split_whitespace().collect();
        ensure!(f.len() == 8, "malformed Elmer mesh.boundary row");
        let id: usize = f[0].parse()?;
        let tag: usize = f[1].parse()?;
        let parent: usize = f[2].parse()?;
        let second_parent: usize = f[3].parse()?;
        ensure!(f[4] == "303", "unexpected Elmer boundary element type");
        let mut tri = [f[5].parse()?, f[6].parse()?, f[7].parse()?];
        tri.sort_unstable();
        result.push((id, tag, parent, second_parent, tri));
    }
    Ok(result)
}

fn read_required(path: impl AsRef<Path>) -> Result<String> {
    let path = path.as_ref();
    std::fs::read_to_string(path).with_context(|| format!("read {}", path.display()))
}

fn same_multiset(source: &[Tet], target: &[(usize, usize, [u64; 4])]) -> bool {
    let mut a = source.to_vec();
    let mut b = target
        .iter()
        .map(|(_, body, tet)| (*body, *tet))
        .collect::<Vec<_>>();
    a.sort_unstable();
    b.sort_unstable();
    a == b
}

fn same_boundary_multiset(source: &[Tri], target: &[Boundary]) -> bool {
    let mut a = source
        .iter()
        .map(|(tag, tri)| (*tag, *tri))
        .collect::<Vec<_>>();
    let mut b = target
        .iter()
        .map(|(_, tag, _, _, tri)| (*tag, *tri))
        .collect::<Vec<_>>();
    a.sort_unstable();
    b.sort_unstable();
    a == b
}

fn tet_faces(tet: [u64; 4]) -> [[u64; 3]; 4] {
    [
        [tet[0], tet[1], tet[2]],
        [tet[0], tet[1], tet[3]],
        [tet[0], tet[2], tet[3]],
        [tet[1], tet[2], tet[3]],
    ]
}

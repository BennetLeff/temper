//! Independent dimensional and topological checks on the joint's linear mesh.
use crate::joint_fem::{JointInput, MeshStats, PadShape};
use anyhow::{ensure, Context, Result};
use std::collections::{BTreeMap, BTreeSet};

type Point = [f64; 3];
type Face = [u64; 3];

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
    let start = lines
        .iter()
        .position(|s| *s == format!("${name}"))
        .context("missing mesh section")?;
    let n: usize = lines
        .get(start + 1)
        .context("missing section count")?
        .parse()?;
    let end = start
        .checked_add(2)
        .and_then(|s| s.checked_add(n))
        .context("section count overflow")?;
    ensure!(
        lines.get(end) == Some(&format!("$End{name}").as_str()),
        "truncated or inconsistent {name} section"
    );
    lines
        .get(start + 2..end)
        .context("invalid mesh section range")
}
fn relative(actual: f64, expected: f64, tolerance: f64, name: &str) -> Result<()> {
    ensure!(
        actual.is_finite()
            && expected.is_finite()
            && expected > 0.0
            && (actual / expected - 1.0).abs() <= tolerance,
        "{name}: actual {actual:e}, expected {expected:e}"
    );
    Ok(())
}

/// Analytic solid volumes, independent of the Gmsh Boolean construction.
pub fn expected_volumes(i: &JointInput) -> [f64; 4] {
    let (w, l, tc, h) = (
        i.trace_width_m,
        i.trace_length_m,
        i.copper_thickness_m,
        i.board_thickness_m,
    );
    let (pw, pl) = (i.pad_width_m, i.pad_length_m);
    let ri = i.drill_diameter_m / 2.0;
    let ro = ri + i.barrel_plating_m;
    let (pad, overlap) = match i.pad_shape {
        PadShape::Rectangle => (pw * pl, w.min(pw) * pl / 2.0),
        PadShape::VerticalObround => {
            let r = pw / 2.0;
            let a = w.min(pw) / 2.0;
            let t = (r * r - a * a).max(0.0).sqrt();
            (
                pw * (pl - pw) + std::f64::consts::PI * r * r,
                w.min(pw) * (pl - pw) / 2.0 + a * t + r * r * (a / r).asin(),
            )
        }
        PadShape::Round => {
            let r = pw / 2.0;
            let a = w.min(pw) / 2.0;
            let t = (r * r - a * a).max(0.0).sqrt();
            (std::f64::consts::PI * r * r, a * t + r * r * (a / r).asin())
        }
    };
    let bore = std::f64::consts::PI * ri * ri;
    let outer = std::f64::consts::PI * ro * ro;
    let lead = i.lead_width_m * i.lead_length_m;
    [
        (w * l + pad - overlap - outer) * tc + (pad - outer) * tc + (outer - bore) * (h + 2.0 * tc),
        (2.0 * i.substrate_half_width_m * (l + i.substrate_back_margin_m) - outer) * h,
        (bore - lead) * (h + 2.0 * tc) + (pad - lead) * i.solder_thickness_m,
        lead * (i.lead_top_z_m + h + tc),
    ]
}

/// Reject missing ports/materials, internal boundary clamps and geometric drift.
pub fn parse(mesh: &str, input: &JointInput) -> Result<MeshStats> {
    input.validate()?;
    ensure!(
        mesh.starts_with("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n"),
        "expected ASCII MSH 2.2"
    );
    let lines: Vec<_> = mesh.lines().collect();
    let mut nodes = BTreeMap::<u64, Point>::new();
    for row in section(&lines, "Nodes")? {
        let f: Vec<_> = row.split_whitespace().collect();
        ensure!(f.len() == 4, "malformed node");
        let id = f[0].parse()?;
        let p: Point = [f[1].parse()?, f[2].parse()?, f[3].parse()?];
        ensure!(p.iter().all(|v| v.is_finite()), "nonfinite node");
        let e = 1e-8;
        ensure!(
            p[0].abs() <= input.substrate_half_width_m + e
                && p[1] >= -input.substrate_back_margin_m - e
                && p[1] <= input.trace_length_m + e
                && p[2] >= -input.board_thickness_m - input.copper_thickness_m - e
                && p[2] <= input.lead_top_z_m + e,
            "node outside declared local domain"
        );
        ensure!(nodes.insert(id, p).is_none(), "duplicate node id");
    }
    ensure!(!nodes.is_empty(), "empty mesh");
    let point = |id: &u64| {
        nodes
            .get(id)
            .copied()
            .context("element references missing node")
    };
    let mut ids = BTreeSet::new();
    let mut faces = BTreeMap::<Face, Vec<u8>>::new();
    let mut triangles = BTreeMap::<Face, u8>::new();
    let mut tetra_ids = BTreeSet::new();
    let mut volumes = BTreeMap::<u8, f64>::new();
    for row in section(&lines, "Elements")? {
        let f: Vec<_> = row.split_whitespace().collect();
        ensure!(f.len() >= 4, "truncated element");
        ensure!(ids.insert(f[0].parse::<u64>()?), "duplicate element id");
        let kind: u8 = f[1].parse()?;
        let tags: usize = f[2].parse()?;
        ensure!(tags >= 1 && tags <= f.len() - 3, "invalid element tags");
        let material: u8 = f[3].parse()?;
        let n = f[3 + tags..]
            .iter()
            .map(|v| v.parse::<u64>())
            .collect::<std::result::Result<Vec<_>, _>>()?;
        if kind == 4 {
            ensure!(
                n.len() == 4 && (1..=4).contains(&material),
                "unexpected tetrahedron/material"
            );
            let mut unique = [n[0], n[1], n[2], n[3]];
            unique.sort_unstable();
            ensure!(
                unique.windows(2).all(|v| v[0] != v[1]) && tetra_ids.insert(unique),
                "degenerate or duplicate tetrahedron"
            );
            let (a, b, c, d) = (point(&n[0])?, point(&n[1])?, point(&n[2])?, point(&n[3])?);
            let volume = dot(sub(b, a), cross(sub(c, a), sub(d, a))).abs() / 6.0;
            ensure!(
                volume.is_finite() && volume > 1e-24,
                "zero-volume tetrahedron"
            );
            *volumes.entry(material).or_default() += volume;
            for index in [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]] {
                let mut face = [n[index[0]], n[index[1]], n[index[2]]];
                face.sort_unstable();
                let incident = faces.entry(face).or_default();
                incident.push(material);
                ensure!(incident.len() <= 2, "non-manifold/overlapping tetrahedra");
            }
        } else if kind == 2 {
            ensure!(
                n.len() == 3 && [11, 12, 14].contains(&material),
                "unexpected triangle/port"
            );
            let mut face = [n[0], n[1], n[2]];
            face.sort_unstable();
            ensure!(
                face.windows(2).all(|v| v[0] != v[1]) && triangles.insert(face, material).is_none(),
                "duplicate or degenerate boundary triangle"
            );
        } else {
            anyhow::bail!("unsupported element kind {kind}");
        }
    }
    let mut interfaces = BTreeMap::<String, usize>::new();
    for m in faces.values().filter(|m| m.len() == 2 && m[0] != m[1]) {
        *interfaces
            .entry(format!("{}:{}", m[0].min(m[1]), m[0].max(m[1])))
            .or_default() += 1;
    }
    ensure!(
        interfaces
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            == BTreeSet::from(["1:2", "1:3", "3:4"]),
        "joint must have exactly Cu/FR4, Cu/solder and solder/lead material interfaces"
    );
    let mut counts = BTreeMap::<u8, usize>::new();
    let mut areas = BTreeMap::<u8, f64>::new();
    for (face, tag) in &triangles {
        let incident = faces
            .get(face)
            .context("port is detached from volume mesh")?;
        let expected_material = match tag {
            11 => 4,
            12 => 2,
            14 => 1,
            _ => unreachable!(),
        };
        ensure!(
            incident.as_slice() == [expected_material],
            "port must be exterior and on its declared material"
        );
        let [a, b, c] = [point(&face[0])?, point(&face[1])?, point(&face[2])?];
        let e = 1e-9;
        for p in [a, b, c] {
            let valid = match tag {
                11 => {
                    (p[2] - input.lead_top_z_m).abs() < e
                        && p[0].abs() <= input.lead_width_m / 2.0 + e
                        && p[1].abs() <= input.lead_length_m / 2.0 + e
                }
                12 => {
                    (p[1] - input.trace_length_m).abs() < e
                        && p[0].abs() <= input.substrate_half_width_m + e
                        && p[2] >= -input.board_thickness_m - e
                        && p[2] <= e
                }
                14 => {
                    (p[1] - input.trace_length_m).abs() < e
                        && p[0].abs() <= input.trace_width_m / 2.0 + e
                        && if input.trace_on_back {
                            p[2] >= -input.board_thickness_m - input.copper_thickness_m - e
                                && p[2] <= -input.board_thickness_m + e
                        } else {
                            p[2] >= -e && p[2] <= input.copper_thickness_m + e
                        }
                }
                _ => false,
            };
            ensure!(
                valid,
                "port {tag} contains a surface outside its specified cut face"
            );
        }
        let v = cross(sub(b, a), sub(c, a));
        *areas.entry(*tag).or_default() += dot(v, v).sqrt() / 2.0;
        *counts.entry(*tag).or_default() += 1;
    }
    for (id, area) in [
        (11, input.lead_width_m * input.lead_length_m),
        (
            12,
            2.0 * input.substrate_half_width_m * input.board_thickness_m,
        ),
        (14, input.trace_width_m * input.copper_thickness_m),
    ] {
        relative(
            *areas.get(&id).context("missing required port")?,
            area,
            1e-7,
            "port area",
        )?;
    }
    for (id, volume) in (1..=4).zip(expected_volumes(input)) {
        // Linear facets approximate cylinders; 64 points/circle stay below 0.5%.
        relative(
            *volumes.get(&id).context("missing required material")?,
            volume,
            0.005,
            "material volume",
        )?;
    }
    Ok(MeshStats {
        nodes: nodes.len(),
        tetrahedra: tetra_ids.len(),
        triangles: triangles.len(),
        material_volumes_m3: volumes,
        interface_triangles: interfaces,
        port_triangles: counts,
        port_areas_m2: areas,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn reference() -> String {
        std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../thermal/physical-model/joint-fem/reference-rect/joint.msh"),
        )
        .unwrap()
    }
    fn rewrite_elements(mesh: &str, mut change: impl FnMut(&str) -> Option<String>) -> String {
        let (before, rest) = mesh.split_once("$Elements\n").unwrap();
        let (_, rest) = rest.split_once('\n').unwrap();
        let (rows, after) = rest.split_once("$EndElements").unwrap();
        let rows = rows.lines().filter_map(&mut change).collect::<Vec<_>>();
        format!(
            "{before}$Elements\n{}\n{}\n$EndElements{after}",
            rows.len(),
            rows.join("\n")
        )
    }
    #[test]
    fn independent_reference_has_four_materials_and_three_true_ports() {
        let stats = parse(&reference(), &JointInput::default()).unwrap();
        assert_eq!(stats.material_volumes_m3.len(), 4);
        assert_eq!(
            stats.port_triangles.keys().copied().collect::<Vec<_>>(),
            vec![11, 12, 14]
        );
    }
    #[test]
    fn mesh_with_no_boundary_triangles_is_rejected_even_if_solver_exits_zero() {
        let mesh = rewrite_elements(&reference(), |row| {
            if row.split_whitespace().nth(1) == Some("2") {
                None
            } else {
                Some(row.to_owned())
            }
        });
        assert!(parse(&mesh, &JointInput::default())
            .unwrap_err()
            .to_string()
            .contains("missing required port"));
    }
    #[test]
    fn aggregate_copper_material_cannot_represent_the_joint() {
        let mesh = rewrite_elements(&reference(), |row| {
            let mut f = row
                .split_whitespace()
                .map(str::to_owned)
                .collect::<Vec<_>>();
            if f[1] == "4" {
                f[3] = "1".into();
            }
            Some(f.join(" "))
        });
        assert!(parse(&mesh, &JointInput::default()).is_err());
    }
    #[test]
    fn internal_interface_cannot_be_declared_a_reservoir_port() {
        let original = reference();
        let lines: Vec<_> = original.lines().collect();
        let mut seen = BTreeSet::new();
        let mut internal = None;
        for row in section(&lines, "Elements").unwrap() {
            let f: Vec<_> = row.split_whitespace().collect();
            if f[1] != "4" {
                continue;
            }
            let tags: usize = f[2].parse().unwrap();
            let n = f[3 + tags..]
                .iter()
                .map(|v| v.parse::<u64>().unwrap())
                .collect::<Vec<_>>();
            for index in [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]] {
                let mut face = [n[index[0]], n[index[1]], n[index[2]]];
                face.sort_unstable();
                if !seen.insert(face) {
                    internal = Some(face);
                    break;
                }
            }
            if internal.is_some() {
                break;
            }
        }
        let face = internal.unwrap();
        let mut changed = false;
        let mesh = rewrite_elements(&original, |row| {
            let f: Vec<_> = row.split_whitespace().collect();
            if !changed && f[1] == "2" {
                changed = true;
                Some(format!(
                    "{} 2 2 11 1 {} {} {}",
                    f[0], face[0], face[1], face[2]
                ))
            } else {
                Some(row.to_owned())
            }
        });
        assert!(parse(&mesh, &JointInput::default())
            .unwrap_err()
            .to_string()
            .contains("must be exterior"));
    }
    #[test]
    fn changed_dimension_and_truncated_input_fail_closed() {
        let mut input = JointInput::default();
        input.trace_length_m *= 1.5;
        assert!(parse(&reference(), &input).is_err());
        assert!(parse(
            "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n100000\n",
            &JointInput::default()
        )
        .is_err());
    }
}

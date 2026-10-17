use super::*;
use geo::{Area, BooleanOps};
use proptest::prelude::*;
use std::collections::BTreeMap;

fn rect(x: f64, y: f64, w: f64, h: f64) -> Polygon {
    Polygon {
        shell: vec![[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        holes: vec![],
    }
}
#[test]
fn triangulation_preserves_voids_area_and_disconnected_islands() {
    let mut p = rect(0., 0., 10., 10.);
    p.holes.push(rect(3., 3., 4., 4.).shell);
    let domain = geometry::shape(&[p, rect(20., 0., 2., 2.)]).unwrap();
    let mesh = mesh::triangulate(&domain, &[], Some(2.)).unwrap();
    assert!((mesh.area_mm2 - 88.).abs() < 1e-10);
    for &t in &mesh.triangles {
        let triangle = mesh.triangle(t).to_polygon();
        assert!(triangle.difference(&domain).unsigned_area() < 1e-10);
    }
}

fn strip(length: f64, width: f64) -> (Snapshot, crate::stackup::LayoutStack, mesh::Surface) {
    let pad = |id: &str, r: &str, x| Pad {
        uuid: id.into(),
        reference: r.into(),
        number: "1".into(),
        net: "signal".into(),
        position_mm: [x, 0.],
        layers: vec!["F.Cu".into()],
        plated_through: false,
        drill_mm: [0.; 2],
    };
    let snapshot = Snapshot {
        schema: String::new(),
        board_sha256: String::new(),
        extractor_sha256: String::new(),
        tool_version: String::new(),
        polygon_error_mm: 0.001,
        layers: vec!["F.Cu".into()],
        components: vec![],
        pads: vec![pad("p0", "P0", 0.), pad("p1", "P1", length)],
        tracks: vec![],
        vias: vec![],
        copper: vec![],
        zone_count: 0,
        gaps: vec![],
    };
    let stack = crate::stackup::LayoutStack {
        copper: vec![crate::stackup::LayoutLayer {
            name: "F.Cu".into(),
            center_z_mm: 0.,
            thickness_mm: 0.07,
        }],
        adjacent_dielectrics: vec![],
    };
    let surface = mesh::Surface {
        net: "signal".into(),
        layer: "F.Cu".into(),
        vertices: vec![[0., 0.], [length, 0.], [length, width], [0., width]],
        triangles: vec![[0, 1, 2], [0, 2, 3]],
        contacts: BTreeMap::from([("p0".into(), vec![0, 3]), ("p1".into(), vec![1, 2])]),
        area_mm2: length * width,
    };
    (snapshot, stack, surface)
}
#[test]
fn sheet_barrel_sheet_matches_independent_series_circuit() {
    let (mut snapshot, mut stack, mut a) = strip(10., 2.);
    let (_, _, mut b) = strip(10., 2.);
    b.layer = "B.Cu".into();
    for p in &mut b.vertices {
        p[0] += 10.;
    }
    a.contacts.remove("p1");
    a.contacts.insert("via".into(), vec![1, 2]);
    b.contacts.remove("p0");
    b.contacts.insert("via".into(), vec![0, 3]);
    stack.copper.push(crate::stackup::LayoutLayer {
        name: "B.Cu".into(),
        center_z_mm: 1.5,
        thickness_mm: 0.07,
    });
    snapshot.vias.push(Via {
        uuid: "via".into(),
        net: "signal".into(),
        position_mm: [10., 0.],
        layers: vec!["F.Cu".into(), "B.Cu".into()],
        drill_mm: 0.3,
    });
    let expected = 2. * 1.724e-8 * 0.01 / (0.002 * 0.00007)
        + 1.724e-8 * 0.0015 / (std::f64::consts::PI * (0.000168_f64.powi(2) - 0.00015_f64.powi(2)));
    let result = sheet::solve(
        &snapshot,
        &stack,
        &[a, b],
        [("P0", "1"), ("P1", "1")],
        15.,
        0.018,
        1.724e-8,
    )
    .unwrap();
    assert!((result.resistance_ohm / expected - 1.).abs() < 1e-10);
    assert!((result.barrels[0].current_a.unwrap().abs() - 15.).abs() < 1e-9);
    assert!((result.loss_w - 225. * expected).abs() < 1e-10);
}
#[test]
fn two_parallel_layers_solve_sharing_instead_of_adding_nominal_capacities() {
    let (snapshot, mut stack, a) = strip(20., 2.);
    let (_, _, mut b) = strip(20., 2.);
    b.layer = "B.Cu".into();
    stack.copper.push(crate::stackup::LayoutLayer {
        name: "B.Cu".into(),
        center_z_mm: 1.5,
        thickness_mm: 0.035,
    });
    let r = sheet::solve(
        &snapshot,
        &stack,
        &[a, b],
        [("P0", "1"), ("P1", "1")],
        3.,
        0.018,
        1.724e-8,
    )
    .unwrap();
    let front = r.layer_peaks["F.Cu"].sheet_current_a_per_mm;
    let back = r.layer_peaks["B.Cu"].sheet_current_a_per_mm;
    assert!((front - 1.).abs() < 1e-10);
    assert!((back - 0.5).abs() < 1e-10);
}
proptest! {
    #[test]
    fn uniform_strip_matches_ohms_law(length in 1u32..200,width in 1u32..30,current in 1u32..40) {
        let (length,width,current)=(f64::from(length),f64::from(width),f64::from(current));
        let (snapshot,stack,surface)=strip(length,width);
        let r=sheet::solve(&snapshot,&stack,&[surface],[("P0", "1"), ("P1", "1")],current,0.018,1.724e-8).unwrap();
        let expected=1.724e-8*length/(width*0.07)*1000.;
        prop_assert!((r.resistance_ohm/expected-1.).abs()<1e-10);
        prop_assert!((r.loss_w/(expected*current*current)-1.).abs()<1e-10);
        prop_assert!((r.layer_peaks["F.Cu"].current_density_a_per_mm2-current/(width*0.07)).abs()<1e-8);
    }
}

// Multiple unconstrained interior nodes exercise the sparse solve, rather than
// a two-triangle fixture whose entire boundary is prescribed.
fn refined_strip(
    length: f64,
    width: f64,
    subdivisions: usize,
) -> (Snapshot, crate::stackup::LayoutStack, mesh::Surface) {
    let (snapshot, stack, mut surface) = strip(length, width);
    surface.vertices.clear();
    surface.triangles.clear();
    surface.contacts.clear();
    for i in 0..=subdivisions {
        surface
            .vertices
            .push([length * i as f64 / subdivisions as f64, 0.]);
        surface
            .vertices
            .push([length * i as f64 / subdivisions as f64, width]);
        if i != subdivisions {
            let k = i * 2;
            surface
                .triangles
                .extend([[k, k + 2, k + 3], [k, k + 3, k + 1]]);
        }
    }
    surface.contacts.insert("p0".into(), vec![0, 1]);
    surface
        .contacts
        .insert("p1".into(), vec![2 * subdivisions, 2 * subdivisions + 1]);
    (snapshot, stack, surface)
}
proptest! {
    #[test]
    fn subdivision_preserves_resistance_and_current_scaling(n in 2usize..45, length in 2u32..100, width in 1u32..10, current in 1u32..30) {
        let (length,width,current)=(f64::from(length),f64::from(width),f64::from(current));
        let (snapshot,stack,surface)=refined_strip(length,width,n);
        let result=sheet::solve(&snapshot,&stack,&[surface],[("P0", "1"), ("P1", "1")],current,0.018,1.724e-8).unwrap();
        let expected=1.724e-8*length/(width*0.07)*1000.;
        prop_assert!(result.active_nodes>2);
        prop_assert!((result.resistance_ohm/expected-1.).abs()<1e-8);
        prop_assert!((result.loss_w/(expected*current*current)-1.).abs()<1e-8);
        prop_assert!(result.max_kcl_residual_a<current*1e-7);
    }
}
#[test]
fn removing_one_strip_cell_produces_an_open_not_zero_resistance() {
    let (snapshot, stack, mut surface) = refined_strip(20., 2., 8);
    surface.triangles.drain(6..8);
    let error = sheet::solve(
        &snapshot,
        &stack,
        &[surface],
        [("P0", "1"), ("P1", "1")],
        15.,
        0.018,
        1.724e-8,
    )
    .unwrap_err();
    assert!(error.contains("disconnected copper islands"), "{error}");
}
#[test]
fn floating_copper_does_not_change_the_connected_solution() {
    let (snapshot, stack, mut surface) = refined_strip(20., 2., 8);
    let first = surface.vertices.len();
    surface.vertices.extend([[50., 0.], [51., 0.], [50., 1.]]);
    surface.triangles.push([first, first + 1, first + 2]);
    let result = sheet::solve(
        &snapshot,
        &stack,
        &[surface],
        [("P0", "1"), ("P1", "1")],
        15.,
        0.018,
        1.724e-8,
    )
    .unwrap();
    assert_eq!(result.unused_nodes, 3);
    assert!((result.resistance_ohm / (1.724e-8 * 20. / (2. * 0.07) * 1000.) - 1.).abs() < 1e-10);
}
#[test]
fn negative_or_nonfinite_mesh_and_material_inputs_fail_closed() {
    let domain = geometry::shape(&[rect(0., 0., 10., 2.)]).unwrap();
    for area in [0., -1., f64::NAN, f64::INFINITY] {
        assert!(mesh::triangulate(&domain, &[], Some(area)).is_err());
    }
    let (snapshot, stack, surface) = strip(20., 2.);
    for (i, p, r) in [
        (0., 0.018, 1.724e-8),
        (1., 0., 1.724e-8),
        (1., 0.018, f64::NAN),
    ] {
        assert!(sheet::solve(
            &snapshot,
            &stack,
            std::slice::from_ref(&surface),
            [("P0", "1"), ("P1", "1")],
            i,
            p,
            r
        )
        .is_err());
    }
}

#[test]
fn annular_sheet_converges_to_independent_logarithmic_solution() {
    // Laplace's radial solution V(r) ~ ln(r) gives R = rho*ln(b/a)/(2*pi*t).
    // Unlike the linear strip, this cannot be represented exactly by linear
    // triangles, so it also tests convergence of the discretization itself.
    let (snapshot, stack, _) = strip(1., 1.);
    let expected = 1.724e-8 * 4_f64.ln() / (2. * std::f64::consts::PI * 0.00007);
    let mut errors = vec![];
    for radial in [4, 8, 16] {
        let angular = 256;
        let mut surface = mesh::Surface {
            net: "signal".into(),
            layer: "F.Cu".into(),
            vertices: vec![],
            triangles: vec![],
            contacts: BTreeMap::new(),
            area_mm2: 0.,
        };
        for ring in 0..=radial {
            let radius = 1. + 3. * ring as f64 / radial as f64;
            for j in 0..angular {
                let angle = std::f64::consts::TAU * j as f64 / angular as f64;
                surface
                    .vertices
                    .push([radius * angle.cos(), radius * angle.sin()]);
                if ring < radial {
                    let a = ring * angular + j;
                    let b = ring * angular + (j + 1) % angular;
                    surface
                        .triangles
                        .extend([[a, b, b + angular], [a, b + angular, a + angular]]);
                }
            }
        }
        surface.contacts.insert("p0".into(), (0..angular).collect());
        surface.contacts.insert(
            "p1".into(),
            (radial * angular..(radial + 1) * angular).collect(),
        );
        let result = sheet::solve(
            &snapshot,
            &stack,
            &[surface],
            [("P0", "1"), ("P1", "1")],
            1.,
            0.018,
            1.724e-8,
        )
        .unwrap();
        errors.push((result.resistance_ohm / expected - 1.).abs());
    }
    assert!(errors.windows(2).all(|e| e[1] < e[0] / 2.), "{errors:?}");
    assert!(errors[2] < 0.002, "{errors:?}");
}

#[test]
fn one_nanometre_same_net_gap_never_becomes_a_current_link() {
    let gap = 1e-6; // mm: one native coordinate quantum
    let (snapshot, stack, _) = strip(2. + gap, 1.);
    let domain = geometry::shape(&[rect(0., 0., 1., 1.), rect(1. + gap, 0., 1., 1.)]).unwrap();
    let contacts = [
        ("p0", geometry::shape(&[rect(0., 0., 0.1, 1.)]).unwrap()),
        (
            "p1",
            geometry::shape(&[rect(1.9 + gap, 0., 0.1, 1.)]).unwrap(),
        ),
    ];
    let mut surface = mesh::triangulate(&domain, &contacts, Some(0.1)).unwrap();
    surface.layer = "F.Cu".into();
    surface.net = "signal".into();
    let result = sheet::solve(
        &snapshot,
        &stack,
        &[surface],
        [("P0", "1"), ("P1", "1")],
        1.,
        0.018,
        1.724e-8,
    );
    assert!(result.unwrap_err().contains("disconnected copper islands"));
}

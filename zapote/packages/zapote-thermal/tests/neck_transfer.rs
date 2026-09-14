use zapote_thermal::{
    neck_geometry::{self, NeckGeometry},
    neck_transfer,
};

use std::{fs, path::Path};

const CASE: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/neck-mesh-fixture");

#[test]
fn genuine_gmsh_elmergrid_transfer_preserves_topology() {
    let gmsh = fs::read_to_string(format!("{CASE}/neck.msh")).unwrap();
    neck_transfer::verify(&gmsh, Path::new(&format!("{CASE}/neck"))).unwrap();
}

#[test]
fn changed_node_coordinate_is_rejected() {
    let mut gmsh = fs::read_to_string(format!("{CASE}/neck.msh")).unwrap();
    gmsh = gmsh.replacen("1 -0.0015 0.0016 0.00144", "1 -0.0015 0.0016 0.00145", 1);
    let error = neck_transfer::verify(&gmsh, Path::new(&format!("{CASE}/neck"))).unwrap_err();
    assert!(error.to_string().contains("coordinates"));
}

#[test]
fn changed_source_material_tag_is_rejected() {
    let mut gmsh = fs::read_to_string(format!("{CASE}/neck.msh")).unwrap();
    // Alter the first tetrahedral physical tag (2 -> 1) while retaining shape.
    gmsh = gmsh.replacen("2707 4 2 1 1 ", "2707 4 2 2 1 ", 1);
    let error = neck_transfer::verify(&gmsh, Path::new(&format!("{CASE}/neck"))).unwrap_err();
    assert!(error.to_string().contains("topology/material"));
}

#[test]
fn missing_parent_is_rejected() {
    let mut boundary = fs::read_to_string(format!("{CASE}/neck/mesh.boundary")).unwrap();
    boundary = boundary.replacen("1 13 711 0 303", "1 13 999999 0 303", 1);
    let temp = std::env::temp_dir().join(format!("zapote-transfer-test-{}", std::process::id()));
    fs::create_dir_all(&temp).unwrap();
    for name in ["mesh.header", "mesh.nodes", "mesh.elements"] {
        fs::copy(format!("{CASE}/neck/{name}"), temp.join(name)).unwrap();
    }
    fs::write(temp.join("mesh.boundary"), boundary).unwrap();
    let gmsh = fs::read_to_string(format!("{CASE}/neck.msh")).unwrap();
    let error = neck_transfer::verify(&gmsh, &temp).unwrap_err();
    let _ = fs::remove_dir_all(temp);
    assert!(error.to_string().contains("missing parent"));
}

#[test]
fn existing_but_unrelated_boundary_parent_is_rejected() {
    let boundary = fs::read_to_string(format!("{CASE}/neck/mesh.boundary"))
        .unwrap()
        .replacen("1 13 711 0 303", "1 13 1 0 303", 1);
    let temp = std::env::temp_dir().join(format!(
        "zapote-transfer-wrong-parent-{}",
        std::process::id()
    ));
    fs::create_dir(&temp).unwrap();
    for name in ["mesh.header", "mesh.nodes", "mesh.elements"] {
        fs::copy(format!("{CASE}/neck/{name}"), temp.join(name)).unwrap();
    }
    fs::write(temp.join("mesh.boundary"), boundary).unwrap();
    let result = neck_transfer::verify(
        &fs::read_to_string(format!("{CASE}/neck.msh")).unwrap(),
        &temp,
    );
    fs::remove_dir_all(temp).unwrap();
    assert!(result.unwrap_err().to_string().contains("claimed parent"));
}

fn neck() -> NeckGeometry {
    NeckGeometry {
        net: "minus".into(),
        pad_number: "1".into(),
        pad_uuid: "fixture".into(),
        trace_uuid: "fixture".into(),
        trace_layer: "B.Cu".into(),
        trace_length_mm: 8.5,
        trace_width_mm: 2.5,
        pad_size_mm: [3.0, 3.2],
        drill_mm: 1.6,
        pad_shape: 1,
        reversed_native_trace: false,
    }
}

#[test]
fn mesh_geometry_rejects_wrong_boundary_material_and_nonfinite_coordinate() {
    let original = fs::read_to_string(format!("{CASE}/neck.msh")).unwrap();
    neck_geometry::verify_mesh(&original, &neck(), 70.0).unwrap();
    for (old, new) in [
        (" 2 2 11 ", " 2 2 13 "),
        ("2707 4 2 1 1 ", "2707 4 2 2 1 "),
        ("1 -0.0015 0.0016 0.00144", "1 NaN 0.0016 0.00144"),
    ] {
        let mutant = original.replacen(old, new, 1);
        assert_ne!(mutant, original, "mutation must apply");
        assert!(neck_geometry::verify_mesh(&mutant, &neck(), 70.0).is_err());
    }
}

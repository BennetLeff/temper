use std::{fs, path::Path};
use zapote_thermal::joint_fem::{self, JointInput, PadShape};

const REF: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../thermal/physical-model/joint-fem/reference-rect"
);

#[test]
fn working_reference_has_four_materials_interfaces_and_ports() {
    let input = JointInput::default();
    let mesh = fs::read_to_string(format!("{REF}/joint.msh")).unwrap();
    let stats = joint_fem::parse_msh2(&mesh, &input).unwrap();
    assert_eq!(stats.material_volumes_m3.len(), 4);
    for pair in ["1:2", "1:3", "3:4"] {
        assert!(stats.interface_triangles.get(pair).copied().unwrap_or(0) > 0);
    }
    for port in [11, 12, 14] {
        assert!(stats.port_triangles.get(&port).copied().unwrap_or(0) > 0);
    }
}

#[test]
fn working_reference_solver_conserves_power() {
    let m = joint_fem::validate_outputs(
        &fs::read_to_string(format!("{REF}/elmersolver.log")).unwrap(),
        &fs::read_to_string(format!("{REF}/scalars.dat")).unwrap(),
        &fs::read_to_string(format!("{REF}/scalars.dat.names")).unwrap(),
        &JointInput::default(),
        &joint_fem::parse_msh2(
            &fs::read_to_string(format!("{REF}/joint.msh")).unwrap(),
            &JointInput::default(),
        )
        .unwrap(),
    )
    .unwrap();
    assert!(m.joule_w > 0.0);
    assert!((m.joule_w - 0.2819166834546).abs() < 1e-8);
}

#[test]
fn geometry_is_deterministic_and_supports_obround() {
    let input = JointInput::default();
    assert_eq!(
        joint_fem::generate_geometry(&input, 0.0006).unwrap(),
        joint_fem::generate_geometry(&input, 0.0006).unwrap()
    );
    let mut oval = input;
    oval.pad_width_m = 0.003;
    oval.pad_length_m = 0.0032;
    oval.solder_width_m = 0.003;
    oval.solder_length_m = 0.0032;
    oval.pad_shape = PadShape::VerticalObround;
    assert!(joint_fem::generate_geometry(&oval, 0.0006)
        .unwrap()
        .contains("Cylinder(301)"));
}

#[test]
fn parser_rejects_empty_ports_and_material_mutations() {
    let input = JointInput::default();
    let mesh = fs::read_to_string(format!("{REF}/joint.msh")).unwrap();
    let no_port = mesh.replace(" 2 2 11 ", " 2 2 12 ");
    assert!(joint_fem::parse_msh2(&no_port, &input).is_err());
    let bad_material = mesh.replace(" 4 2 1 1 ", " 4 2 4 1 ");
    assert!(joint_fem::parse_msh2(&bad_material, &input).is_err());
}

#[test]
fn solver_rejects_changed_scalars_or_missing_completion() {
    let names = fs::read_to_string(format!("{REF}/scalars.dat.names")).unwrap();
    let scalars = fs::read_to_string(format!("{REF}/scalars.dat")).unwrap();
    let log = fs::read_to_string(format!("{REF}/elmersolver.log")).unwrap();
    let mesh = joint_fem::parse_msh2(
        &fs::read_to_string(format!("{REF}/joint.msh")).unwrap(),
        &JointInput::default(),
    )
    .unwrap();
    assert!(joint_fem::validate_outputs(
        &log.replace("ALL DONE", "NOT DONE"),
        &scalars,
        &names,
        &JointInput::default(),
        &mesh
    )
    .is_err());
    assert!(joint_fem::validate_outputs(
        &log,
        &scalars.replace("2.819166834546", "1.819166834546"),
        &names,
        &JointInput::default(),
        &mesh
    )
    .is_err());
}

#[test]
fn zero_current_is_accepted_only_for_zero_heating() {
    let input = JointInput {
        current_a: 0.0,
        ..JointInput::default()
    };
    assert!(input.validate().is_ok());
    let mut bad = fs::read_to_string(format!("{REF}/scalars.dat")).unwrap();
    bad = bad.replace("2.819166834546", "0.000000000000");
    let mesh = joint_fem::parse_msh2(
        &fs::read_to_string(format!("{REF}/joint.msh")).unwrap(),
        &input,
    )
    .unwrap();
    assert!(joint_fem::validate_outputs(
        &fs::read_to_string(format!("{REF}/elmersolver.log")).unwrap(),
        &bad,
        &fs::read_to_string(format!("{REF}/scalars.dat.names")).unwrap(),
        &input,
        &mesh
    )
    .is_err());
    let _ = Path::new(REF);
}

#[test]
fn native_replay_rejects_modified_summary_physics_and_mesh_even_with_updated_hashes() {
    use sha2::{Digest, Sha256};
    let source = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../thermal/physical-model/joint-fem/reference-native");
    let original = joint_fem::replay(&source).unwrap();
    let temp = std::env::temp_dir().join(format!("zapote-joint-mutations-{}", std::process::id()));
    fs::create_dir(&temp).unwrap();
    for name in original
        .artifacts
        .keys()
        .map(String::as_str)
        .chain(["report.json"])
    {
        let out = temp.join(name);
        fs::create_dir_all(out.parent().unwrap()).unwrap();
        fs::copy(source.join(name), out).unwrap();
    }
    let original_report = fs::read(temp.join("report.json")).unwrap();
    let mut report: serde_json::Value = serde_json::from_slice(&original_report).unwrap();
    report["cases"][0]["measurement"]["max_temperature_k"] = 300.0.into();
    fs::write(
        temp.join("report.json"),
        serde_json::to_vec(&report).unwrap(),
    )
    .unwrap();
    assert!(joint_fem::replay(&temp).is_err());
    fs::write(temp.join("report.json"), &original_report).unwrap();
    for name in ["mesh-0/case.sif", "mesh-0/joint.msh", "mesh-0/scalars.dat"] {
        let before = fs::read(temp.join(name)).unwrap();
        let text = String::from_utf8(before.clone()).unwrap();
        let changed = match name {
            "mesh-0/case.sif" => text.replace("Joule Heat = True", "Joule Heat = False"),
            "mesh-0/joint.msh" => text.replace(" 2 2 11 ", " 2 2 12 "),
            _ => text
                .split_whitespace()
                .map(|v| (v.parse::<f64>().unwrap() * 2.0).to_string())
                .collect::<Vec<_>>()
                .join(" "),
        };
        assert!(changed.as_bytes() != before, "mutation must change {name}");
        fs::write(temp.join(name), changed.as_bytes()).unwrap();
        let mut report: serde_json::Value = serde_json::from_slice(&original_report).unwrap();
        report["artifacts"][name] = format!("{:x}", Sha256::digest(changed.as_bytes())).into();
        fs::write(
            temp.join("report.json"),
            serde_json::to_vec(&report).unwrap(),
        )
        .unwrap();
        assert!(
            joint_fem::replay(&temp).is_err(),
            "{name} must be checked beyond its producer hash"
        );
        fs::write(temp.join(name), before).unwrap();
        fs::write(temp.join("report.json"), &original_report).unwrap();
    }
    assert!(joint_fem::replay(&temp).is_ok());
    // Lossless archival preserves raw identity; dual copies are ambiguous.
    use std::io::Write;
    let mesh_path = temp.join("mesh-0/joint.msh");
    let bytes = fs::read(&mesh_path).unwrap();
    let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
    encoder.write_all(&bytes).unwrap();
    let compressed = encoder.finish().unwrap();
    fs::write(temp.join("mesh-0/joint.msh.gz"), &compressed).unwrap();
    assert!(joint_fem::replay(&temp).is_err());
    fs::remove_file(mesh_path).unwrap();
    assert!(joint_fem::replay(&temp).is_ok());
    fs::write(
        temp.join("mesh-0/joint.msh.gz"),
        &compressed[..compressed.len() / 2],
    )
    .unwrap();
    assert!(joint_fem::replay(&temp).is_err());
    fs::remove_dir_all(temp).unwrap();
}

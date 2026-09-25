use std::fs;
use zapote_thermal::joint_fem::{self, JointInput, PadShape};
use zapote_thermal::neck_geometry::build_gbj_neck_model;

#[test]
fn captured_gbj2510f_builds_in_native_pin_order() {
    let root = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../power-entry/bridge-redesign/variants/alternate-gbj/evidence/"
    );
    let model = build_gbj_neck_model(
        &fs::read(format!("{root}native-fresh.json")).unwrap(),
        &fs::read(format!("{root}manufacturing-fresh.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(model.bridge_mpn, "GBJ2510-F");
    assert_eq!(
        model
            .necks
            .iter()
            .map(|n| n.net.as_str())
            .collect::<Vec<_>>(),
        ["plus", "ac1", "ac2", "minus"]
    );
    assert!(model
        .necks
        .iter()
        .all(|n| n.pad_size_mm == [4.0, 4.0] && n.trace_width_mm > 4.0));
    assert_eq!(model.necks[3].trace_layer, "F.Cu");
    assert_eq!(model.necks[2].trace_layer, "B.Cu");
}

#[test]
fn gbj_rejects_pin_net_swap_even_when_geometry_matches() {
    let root = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../power-entry/bridge-redesign/variants/alternate-gbj/evidence/"
    );
    let mut native: serde_json::Value =
        serde_json::from_slice(&fs::read(format!("{root}native-fresh.json")).unwrap()).unwrap();
    let bridge = native["components"]
        .as_array()
        .unwrap()
        .iter()
        .position(|c| c["id"] == "bridge")
        .unwrap();
    native["components"][bridge]["footprint_pads"][0]["net"] =
        serde_json::Value::String("minus".into());
    let err = build_gbj_neck_model(
        &serde_json::to_vec(&native).unwrap(),
        &fs::read(format!("{root}manufacturing-fresh.json")).unwrap(),
    )
    .unwrap_err();
    assert!(err.to_string().contains("native geometry differs"));
}

#[test]
#[ignore = "live Gmsh check; retained FEM replay runs without an installed mesher"]
fn round_back_trace_gmsh_mesh_has_independent_materials_and_ports() {
    let input = JointInput {
        pad_shape: PadShape::Round,
        pad_width_m: 0.004,
        pad_length_m: 0.004,
        solder_width_m: 0.004,
        solder_length_m: 0.004,
        trace_width_m: 0.0042,
        trace_length_m: 0.009,
        trace_on_back: true,
        ..JointInput::default()
    };
    let geo = joint_fem::generate_geometry(&input, 0.0006).unwrap();
    let dir = std::env::temp_dir().join(format!("gbj-round-{}", std::process::id()));
    let _ = fs::create_dir_all(&dir);
    fs::write(dir.join("joint.geo"), geo).unwrap();
    let status = std::process::Command::new("/opt/homebrew/bin/gmsh")
        .args(["-3", "joint.geo", "-format", "msh2", "-o", "joint.msh"])
        .current_dir(&dir)
        .status()
        .unwrap();
    assert!(status.success());
    let stats =
        joint_fem::parse_msh2(&fs::read_to_string(dir.join("joint.msh")).unwrap(), &input).unwrap();
    assert_eq!(stats.material_volumes_m3.len(), 4);
    for port in [11, 12, 14] {
        assert!(stats.port_triangles.get(&port).copied().unwrap_or(0) > 0);
    }
}

#[test]
fn saved_back_copper_mesh_rejects_front_side_reinterpretation() {
    use std::io::Read;
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../thermal/gbj-study/evidence-01/nominal-coarse/iteration-2/lead-2");
    let input: JointInput =
        serde_json::from_slice(&fs::read(root.join("input.json")).unwrap()).unwrap();
    assert!(input.trace_on_back);
    let path = root.join("mesh-0/joint.msh");
    let mesh = if path.exists() {
        fs::read_to_string(&path).unwrap()
    } else {
        let mut text = String::new();
        flate2::read::GzDecoder::new(fs::File::open(path.with_extension("msh.gz")).unwrap())
            .read_to_string(&mut text)
            .unwrap();
        text
    };
    joint_fem::parse_msh2(&mesh, &input).unwrap();
    let mut wrong = input;
    wrong.trace_on_back = false;
    assert!(joint_fem::parse_msh2(&mesh, &wrong).is_err());
}

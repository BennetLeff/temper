use zapote_thermal::lead_fem::{self, PhysicalModelInput};

#[test]
fn retained_physical_input_has_four_nonoverlapping_domains() {
    let bytes = include_bytes!("../../../thermal/physical-model/fem/input.json");
    let input: PhysicalModelInput = serde_json::from_slice(bytes).unwrap();
    let receipt = lead_fem::geometry_receipt(&input).unwrap();
    assert_eq!(receipt.domains.len(), 4);
    assert!(receipt.total_copper_joule_w > 0.0);
    assert_eq!(
        receipt.applicability,
        "indeterminate-until-lead-solder-barrel-assembly-is-characterized"
    );
}

#[test]
fn geo_and_sif_keep_same_physics_across_three_meshes() {
    let input: PhysicalModelInput = serde_json::from_slice(include_bytes!(
        "../../../thermal/physical-model/fem/input.json"
    ))
    .unwrap();
    let receipt = lead_fem::geometry_receipt(&input).unwrap();
    let sources =
        [0.001, 0.0005, 0.00025].map(|mesh| lead_fem::generate_geo(&input, mesh).unwrap());
    assert!(sources.windows(2).all(|pair| {
        pair[0].contains("Physical Volume(1)")
            && pair[1].contains("Physical Volume(1)")
            && pair[0].contains("BooleanFragments")
            && pair[1].contains("BooleanFragments")
    }));
    let sif = lead_fem::generate_sif(&input, &receipt, input.ambient_k).unwrap();
    assert!(sif.contains("Heat Source ="));
}

#[test]
fn changed_board_identity_is_still_bound_to_input() {
    let mut input: PhysicalModelInput = serde_json::from_slice(include_bytes!(
        "../../../thermal/physical-model/fem/input.json"
    ))
    .unwrap();
    input.board_sha256.replace_range(..1, "b");
    assert!(lead_fem::geometry_receipt(&input).is_ok());
    assert_ne!(
        input.board_sha256,
        "84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317"
    );
}

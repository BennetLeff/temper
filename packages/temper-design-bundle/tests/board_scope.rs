use temper_design_bundle::{
    AssemblyOnlyPart, ConvertedCandidate, DesignBundleError, select_board_scope,
};

fn candidate() -> ConvertedCandidate {
    serde_json::from_value(serde_json::json!({
        "entry": "PowerEntryIntegrated38",
        "components": [
            {"instance_path": "pfc_power.f2", "reference": "U226",
             "mpn": "A70QS50-14F", "footprint": "TBD_REVIEW_ONLY:PFC_F2_OFFBOARD_ASSEMBLY",
             "value": null, "origins": {}},
            {"instance_path": "pfc_power.f2_board", "reference": "U227",
             "mpn": "1017526", "footprint": "TBD_REVIEW_ONLY:PFC_F2_BOARD_TERMINAL_1017526",
             "value": null, "origins": {}}
        ],
        "nets": [],
        "empty_reference_nets": []
    }))
    .expect("valid converted candidate fixture")
}

fn fuse() -> AssemblyOnlyPart {
    AssemblyOnlyPart {
        instance_path: "pfc_power.f2".into(),
        mpn: "A70QS50-14F".into(),
        footprint: "TBD_REVIEW_ONLY:PFC_F2_OFFBOARD_ASSEMBLY".into(),
    }
}

fn code(error: DesignBundleError) -> String {
    match error {
        DesignBundleError::Validation(diagnostics) => diagnostics[0].code.clone(),
        other => panic!("expected validation error, got {other:?}"),
    }
}

#[test]
fn exact_fuse_declaration_keeps_terminal_on_board() {
    let scope = select_board_scope(&candidate(), &[fuse()]).expect("exact exclusion passes");
    assert_eq!(scope.board_references, ["U227"]);
    assert_eq!(scope.assembly_only_components[0].reference, "U226");
}

#[test]
fn stale_assembly_path_cannot_silently_remove_another_part() {
    let mut declaration = fuse();
    declaration.instance_path = "pfc_power.old_f2".into();
    assert_eq!(
        code(select_board_scope(&candidate(), &[declaration]).unwrap_err()),
        "missing_assembly_part"
    );
}

#[test]
fn changed_fuse_identity_needs_a_new_review() {
    let mut declaration = fuse();
    declaration.mpn = "OTHER".into();
    assert_eq!(
        code(select_board_scope(&candidate(), &[declaration]).unwrap_err()),
        "assembly_identity_mismatch"
    );
}

#[test]
fn changed_fuse_footprint_marker_needs_a_new_review() {
    let mut declaration = fuse();
    declaration.footprint = "TBD_REVIEW_ONLY:OTHER".into();
    assert_eq!(
        code(select_board_scope(&candidate(), &[declaration]).unwrap_err()),
        "assembly_identity_mismatch"
    );
}

#[test]
fn duplicate_assembly_declaration_fails() {
    assert_eq!(
        code(select_board_scope(&candidate(), &[fuse(), fuse()]).unwrap_err()),
        "duplicate_assembly_part"
    );
}

#[test]
fn cannot_exclude_every_compiled_part() {
    let terminal = AssemblyOnlyPart {
        instance_path: "pfc_power.f2_board".into(),
        mpn: "1017526".into(),
        footprint: "TBD_REVIEW_ONLY:PFC_F2_BOARD_TERMINAL_1017526".into(),
    };
    assert_eq!(
        code(select_board_scope(&candidate(), &[fuse(), terminal]).unwrap_err()),
        "empty_board_scope"
    );
}

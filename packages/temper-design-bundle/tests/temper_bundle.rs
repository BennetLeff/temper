use temper_design_bundle::*;

#[test]
fn temper_fixture_is_valid_and_deterministic() {
    let atopile = include_bytes!("../../../elec/exports/temper.design-input.v1.json");
    let mapping = include_bytes!("../../../elec/exports/net-name-mapping.v1.yaml");
    let pcl = include_bytes!("fixtures/temper.pcl.yaml");
    let a = parse_atopile(atopile).unwrap();
    let b = parse_mapping(mapping).unwrap();
    let p = parse_pcl(pcl).unwrap();
    let board = a.board.clone();
    let provenance = Provenance {
        atopile_sha256: sha256(atopile),
        mapping_sha256: sha256(mapping),
        pcl_sha256: sha256(pcl),
        board_sha256: sha256(b"temper-board"),
    };
    let bundle = build_bundle(a, b, p, board, provenance).unwrap();
    let normalized = normalized_json(&bundle).unwrap();
    assert_eq!(
        normalized,
        include_str!("golden/temper.design-bundle.json").trim_end()
    );
    assert_eq!(
        bundle
            .constraints
            .constraints
            .iter()
            .find(|c| c.metric == "clearance")
            .unwrap()
            .value_mm,
        8.0
    );
}

#[test]
fn authored_safety_weakening_is_fatal() {
    let a = AtopileExport {
        schema_version: 1,
        board: BoardSpec {
            width_mm: 1.0,
            height_mm: 1.0,
            thickness_mm: 1.0,
        },
        components: vec![Component {
            id: "component".into(),
            reference: None,
        }],
        nets: vec![Net {
            id: "n".into(),
            name: "N".into(),
            net_class: None,
            safety_domain: None,
        }],
        net_classes: vec![],
        safety_domains: vec![],
        stackup: None,
        zones: vec![],
        loops: vec![],
        safety: vec![SafetyRule {
            id: "floor".into(),
            subject: "n".into(),
            metric: "clearance".into(),
            value_mm: 6.0,
            because: None,
        }],
    };
    let p = PclDocument {
        constraints: vec![PclConstraint {
            id: Some("weaken".into()),
            r#type: "separated".into(),
            subject: Some("n".into()),
            metric: Some("clearance".into()),
            value_mm: Some(4.0),
            max_distance_mm: None,
            min_distance_mm: None,
            margin_mm: None,
            max_area_mm2: None,
            a: None,
            b: None,
            component: None,
            loop_name: None,
            tier: 1,
            because: None,
        }],
    };
    let err = build_bundle(
        a.clone(),
        NetMapping {
            schema_version: 1,
            entries: vec![MappingEntry {
                atopile_signal: "n".into(),
                kicad_net: "N".into(),
                aliases: vec![],
            }],
        },
        p,
        a.board,
        Provenance {
            atopile_sha256: String::new(),
            pcl_sha256: String::new(),
            board_sha256: String::new(),
            mapping_sha256: String::new(),
        },
    )
    .unwrap_err();
    assert!(err.to_string().contains("safety_weakening"));
}

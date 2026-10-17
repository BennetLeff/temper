use serde_json::json;
use zapote_core::Status;
use zapote_drc::native_binding::validate;

fn evidence() -> serde_json::Value {
    json!({"board_file_utf8":r#"(kicad_pcb
      (footprint "relay" (property "SourceInstance" "relay") (property "MPN" "RT33K012")
        (pad "3" thru_hole circle (net "NO") (uuid "a"))
        (pad "3" thru_hole circle (net "NO") (uuid "b"))
        (pad "4" thru_hole circle (net "COM") (uuid "c"))
        (pad "4" thru_hole circle (net "COM") (uuid "d"))))"#,
      "components":[{"id":"relay","mpn":"RT33K012","footprint_pads":[
        {"pad":"3","net":"NO","uuid":"a"},{"pad":"3","net":"NO","uuid":"b"},
        {"pad":"4","net":"COM","uuid":"c"},{"pad":"4","net":"COM","uuid":"d"}]}],
      "traces":[],"vias":[]})
}

#[test]
fn declared_kicad_net_ids_bind_pads_and_tracks_by_name() {
    let board = r#"(kicad_pcb
      (net 1 "SELV") (net 2 "HOT")
      (footprint "test" (property "SourceInstance" "part") (property "MPN" "P")
        (pad "1" smd rect (net 1 "SELV") (uuid "pad-1"))
        (pad "2" smd rect (net 2 "HOT") (uuid "pad-2")))
      (segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu")
        (net 1) (uuid "trace-1")))"#;
    let native = json!({
        "board_file_utf8": board,
        "components": [{"id":"part","mpn":"P","footprint_pads":[
            {"pad":"1","net":"SELV","uuid":"pad-1"},
            {"pad":"2","net":"HOT","uuid":"pad-2"}]}],
        "traces":[{"uuid":"trace-1","net":"SELV","layer":"F.Cu",
                   "width_mm":0.2,"points_mm":[[0.0,0.0],[1.0,0.0]]}],
        "vias":[]
    });
    assert_eq!(validate(&native.to_string()).status, Status::Pass);
    for changed in [
        board.replace(
            "(net 1 \"SELV\") (uuid \"pad-1\")",
            "(net 1 \"HOT\") (uuid \"pad-1\")",
        ),
        board.replace("(net 1) (uuid \"trace-1\")", "(net 2) (uuid \"trace-1\")"),
    ] {
        let mut mutated = native.clone();
        mutated["board_file_utf8"] = json!(changed);
        assert_eq!(validate(&mutated.to_string()).status, Status::Fail);
    }
}
#[test]
fn physical_relay_contacts_bind_to_their_saved_uuids() {
    assert_eq!(validate(&evidence().to_string()).status, Status::Pass);
}

fn npth_evidence() -> serde_json::Value {
    json!({"board_file_utf8":r#"(kicad_pcb
      (footprint "choke" (property "SourceInstance" "choke") (property "MPN" "T75")
        (pad "1" thru_hole rect (net "HOT") (uuid "p1"))
        (pad "2" thru_hole circle (net "SW") (uuid "p2"))
        (pad "" np_thru_hole circle (uuid "mount"))))"#,
      "components":[{"id":"choke","mpn":"T75","footprint_pads":[
        {"pad":"1","net":"HOT","uuid":"p1"},
        {"pad":"2","net":"SW","uuid":"p2"},
        {"pad":"","net":"","uuid":"mount","pad_type":"np_thru_hole"}]}],
      "traces":[],"vias":[]})
}

#[test]
fn mechanical_npth_hole_is_accepted_without_electrical_assignment() {
    assert_eq!(validate(&npth_evidence().to_string()).status, Status::Pass);
}

#[test]
fn mechanical_npth_mutations_fail_closed() {
    let e = npth_evidence();
    let mut missing = e.clone();
    missing["components"][0]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .pop();
    assert_eq!(validate(&missing.to_string()).status, Status::Fail);

    let mut extra = e.clone();
    extra["components"][0]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .push(json!({"pad":"","net":"","uuid":"extra","pad_type":"np_thru_hole"}));
    assert_eq!(validate(&extra.to_string()).status, Status::Fail);

    let mut assigned = e.clone();
    assigned["components"][0]["footprint_pads"][2]["net"] = json!("HOT");
    assert_eq!(validate(&assigned.to_string()).status, Status::Fail);

    let mut typed = e;
    typed["components"][0]["footprint_pads"][2]["pad_type"] = json!("thru_hole");
    assert_eq!(validate(&typed.to_string()).status, Status::Fail);
}
#[test]
fn repeated_uuid_missing_pad_and_changed_net_fail() {
    let e = evidence();
    for bad_board in [
        e["board_file_utf8"]
            .as_str()
            .unwrap()
            .replace("(uuid \"b\")", "(uuid \"a\")"),
        e["board_file_utf8"]
            .as_str()
            .unwrap()
            .replace("(uuid \"b\")", ""),
        e["board_file_utf8"]
            .as_str()
            .unwrap()
            .replace("(uuid \"b\")", "(uuid \"c\")"),
    ] {
        let mut bad = e.clone();
        bad["board_file_utf8"] = json!(bad_board);
        assert_eq!(validate(&bad.to_string()).status, Status::Fail);
    }
    let mut bad = e.clone();
    bad["components"][0]["footprint_pads"][1]["uuid"] = json!("a");
    assert_eq!(validate(&bad.to_string()).status, Status::Fail);
    let mut bad = e.clone();
    bad["components"][0]["footprint_pads"]
        .as_array_mut()
        .unwrap()
        .pop();
    assert_eq!(validate(&bad.to_string()).status, Status::Fail);
    let mut bad = e;
    bad["components"][0]["footprint_pads"][0]["net"] = json!("COM");
    assert_eq!(validate(&bad.to_string()).status, Status::Fail);
}

use zapote_thermal::shunt_model::{cases, ShuntGeometry, QUALIFIED_MPN};
use sha2::Digest;

fn native(mpn: &str) -> Vec<u8> {
    let board = "(kicad_pcb (version 20240108))";
    let digest = format!("{:x}", sha2::Sha256::digest(board.as_bytes()));
    serde_json::json!({"board_file_utf8":board,"board_sha256":digest, "components":[{"id":"shunt","mpn":mpn,"position_mm":[1.0,2.0],"footprint_pads":[
      {"pad":"1","uuid":"p1","net":"A","position_mm":[0.,2.],"size_mm":[3.,4.],"orientation_deg":0.,"layers":["F.Cu"]},
      {"pad":"2","uuid":"p2","net":"B","position_mm":[2.,2.],"size_mm":[3.,4.],"orientation_deg":0.,"layers":["F.Cu"]}]}],
      "traces":[{"uuid":"t1","net":"A","points_mm":[[0.,2.],[0.,12.]],"layer":"F.Cu","width_mm":6.0}]})
    .to_string().into_bytes()
}

#[test]
fn legacy_two_pad_fixture_is_rejected() {
    let err = ShuntGeometry::from_native(&native("WSL2726R0100FEA")).unwrap_err().to_string();
    assert!(err.contains(QUALIFIED_MPN));
}

#[test]
fn qualified_geometry_is_source_bound() {
    let g = ShuntGeometry::from_native(&native(QUALIFIED_MPN)).unwrap();
    assert_eq!(g.pads.len(), 2);
    assert_eq!(g.crop_bounds_mm, [-14.0, 16.0, -13.0, 17.0]);
    assert_eq!(g.attached_traces[0].length_mm, 10.0);
}

#[test]
fn thermal_cases_cover_heat_split_sensitivities() {
    let c = cases(15.0).unwrap();
    assert_eq!(c.len(), 3);
    assert!((c[0].power_w - 2.2725).abs() < 1e-12);
    assert_eq!(c[1].heat_split, [1.0, 0.0]);
    assert!(c.iter().all(|x| x.status == "INDETERMINATE_BODY_THERMAL_DATA"));
}

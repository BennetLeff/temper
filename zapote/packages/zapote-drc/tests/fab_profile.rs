//! Vendor fab profiles: every limit is backed by a verbatim quote.
use zapote_drc::fab_profile::parse_profile;

const TWO_LAYER_2OZ: &str = include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json");
const FOUR_LAYER_1OZ: &str = include_str!("../../../fab-profiles/jlcpcb-4layer-1oz.json");
const FOUR_LAYER_2OZ: &str = include_str!("../../../fab-profiles/jlcpcb-4layer-2oz.json");

#[test]
fn shipped_profiles_load_with_vendor_values() {
    let two = parse_profile(TWO_LAYER_2OZ).expect("2-layer 2 oz");
    assert_eq!(two.minimum_annular_ring_mm, 0.254);
    assert_eq!(two.minimum_via_annular_ring_mm, Some(0.05));
    assert_eq!(two.minimum_track_width_mm, Some(0.16));
    assert_eq!(two.maximum_board_mm, Some([670.0, 600.0]));
    assert!(two.qualified);
    assert!(two.source.contains("jlcpcb.com") && two.source.contains("2026-10-08"));
    let four = parse_profile(FOUR_LAYER_1OZ).expect("4-layer 1 oz");
    assert_eq!(four.minimum_annular_ring_mm, 0.15);
    assert_eq!(four.minimum_track_width_mm, Some(0.09));
    assert_eq!(four.maximum_board_mm, Some([663.0, 593.0]));
    let four2 = parse_profile(FOUR_LAYER_2OZ).expect("4-layer 2 oz");
    assert_eq!(four2.minimum_annular_ring_mm, 0.254);
    assert_eq!(four2.minimum_track_width_mm, Some(0.15));
}

#[test]
fn a_limit_without_a_quote_is_rejected() {
    let mut v: serde_json::Value = serde_json::from_str(TWO_LAYER_2OZ).unwrap();
    v["quotes"].as_object_mut().unwrap().remove("minimum_track_width_mm");
    let err = parse_profile(&v.to_string()).unwrap_err();
    assert!(err.contains("minimum_track_width_mm"), "{err}");
}

#[test]
fn unknown_fields_and_schemas_are_rejected() {
    let mut v: serde_json::Value = serde_json::from_str(TWO_LAYER_2OZ).unwrap();
    v["limits"]["minimum_trace_width_mm"] = serde_json::json!(0.1); // typo of a real key
    assert!(parse_profile(&v.to_string()).is_err());
    let mut v: serde_json::Value = serde_json::from_str(TWO_LAYER_2OZ).unwrap();
    v["schema"] = serde_json::json!("zapote.fab-profile.v0");
    assert!(parse_profile(&v.to_string()).is_err());
}

#[test]
fn a_quote_must_contain_the_number_it_backs() {
    let mut v: serde_json::Value = serde_json::from_str(TWO_LAYER_2OZ).unwrap();
    v["limits"]["minimum_annular_ring_mm"] = serde_json::json!(0.2);
    let err = parse_profile(&v.to_string()).unwrap_err();
    assert!(err.contains("minimum_annular_ring_mm"), "{err}");
}

#[test]
fn conditional_figures_in_parentheses_do_not_back_a_limit() {
    // JLC: "Min. Via hole size/diameter: 0.15/0.25mm (0.1mm/0.2mm only available
    // for board thickness <=1mm ...)". 0.1 is a conditional exception, not the rule.
    let mut v: serde_json::Value = serde_json::from_str(TWO_LAYER_2OZ).unwrap();
    v["limits"]["minimum_via_drill_mm"] = serde_json::json!(0.1);
    let err = parse_profile(&v.to_string()).unwrap_err();
    assert!(err.contains("minimum_via_drill_mm"), "{err}");
}

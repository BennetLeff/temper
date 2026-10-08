//! KiCad custom rules generated from a vendor fab profile (the fab pass).
use zapote_drc::fab_profile::parse_profile;
use zapote_drc::fab_rules::{kicad_rules, RULE_PREFIX};
use zapote_drc::manufacturing::FabricationLimits;

const TWO_LAYER_2OZ: &str = include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json");

#[test]
fn profile_becomes_named_kicad_rules() {
    let text = kicad_rules(&parse_profile(TWO_LAYER_2OZ).unwrap()).expect("rules");
    assert!(text.starts_with("(version 1)\n"));
    for expected in [
        "(rule \"zapote fab copper clearance\" (constraint clearance (min 0.16mm)))",
        "(rule \"zapote fab via hole to copper\" (condition \"A.Type == 'Via'\") (constraint hole_clearance (min 0.2mm)))",
        "(rule \"zapote fab PTH hole to copper\" (condition \"A.Type == 'Pad' && A.Pad_Type == 'Through-hole'\") (constraint hole_clearance (min 0.28mm)))",
        "(rule \"zapote fab NPTH hole to copper\" (condition \"A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'\") (constraint hole_clearance (min 0.2mm)))",
        "(rule \"zapote fab silk text height\" (layer \"F.SilkS\") (constraint text_height (min 1mm)))",
        "(rule \"zapote fab silk text height B\" (layer \"B.SilkS\") (constraint text_height (min 1mm)))",
        "(rule \"zapote fab silk text thickness\" (layer \"F.SilkS\") (constraint text_thickness (min 0.15mm)))",
    ] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
    assert!(
        text.lines().skip(1).all(|l| l.contains(RULE_PREFIX)),
        "{text}"
    );
}

#[test]
fn unset_limits_emit_nothing() {
    let mut limits = FabricationLimits::default();
    assert!(kicad_rules(&limits).is_none());
    limits.minimum_via_hole_to_copper_mm = Some(0.25);
    let text = kicad_rules(&limits).unwrap();
    assert_eq!(text.lines().count(), 2, "{text}");
    assert!(text.contains("(min 0.25mm)"));
}

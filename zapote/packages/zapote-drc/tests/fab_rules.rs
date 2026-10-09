use zapote_drc::fab_profile::parse_profile;
use zapote_drc::fab_rules::{kicad_rules, rules, RULE_PREFIX};
use zapote_drc::manufacturing::FabricationLimits;

const TWO_LAYER_2OZ: &str = include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json");
const FOUR_LAYER_1OZ: &str = include_str!("../../../fab-profiles/jlcpcb-4layer-1oz.json");

#[test]
fn profile_becomes_named_kicad_rules() {
    let text = kicad_rules(&parse_profile(TWO_LAYER_2OZ).unwrap()).expect("rules");
    assert!(text.starts_with("(version 1)\n"));
    let via = "(condition \"A.Type == 'Via'\")";
    let pth = "(condition \"A.Type == 'Pad' && A.Pad_Type == 'Through-hole'\")";
    let npth = "(condition \"A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'\")";
    for expected in [
        "(rule \"zapote fab copper clearance\" (constraint clearance (min 0.16mm)))".to_string(),
        format!("(rule \"zapote fab via hole to copper\" {via} (constraint hole_clearance (min 0.2mm)))"),
        format!("(rule \"zapote fab PTH hole to copper\" {pth} (constraint hole_clearance (min 0.28mm)))"),
        format!("(rule \"zapote fab NPTH hole to copper\" {npth} (constraint hole_clearance (min 0.2mm)))"),
        "(rule \"zapote fab silk text height\" (layer \"F.SilkS\") (constraint text_height (min 1mm)))".into(),
        "(rule \"zapote fab silk text height B\" (layer \"B.SilkS\") (constraint text_height (min 1mm)))".into(),
        "(rule \"zapote fab silk text thickness\" (layer \"F.SilkS\") (constraint text_thickness (min 0.15mm)))"
            .into(),
        "(rule \"zapote fab silk text thickness B\" (layer \"B.SilkS\") (constraint text_thickness (min 0.15mm)))"
            .into(),
    ] {
        assert!(text.contains(&expected), "missing {expected}\n{text}");
    }
    assert!(text.lines().skip(1).all(|l| l.contains(RULE_PREFIX)), "{text}");
}

#[test]
fn structured_rules_match_the_text_one_to_one() {
    let limits = parse_profile(TWO_LAYER_2OZ).unwrap();
    let list = rules(&limits);
    let text = kicad_rules(&limits).unwrap();
    assert_eq!(list.len(), 9);
    assert_eq!(text.lines().count(), list.len() + 1);
    for r in &list {
        assert!(r.name.starts_with(RULE_PREFIX) && text.contains(&r.text), "{r:?}");
        assert!(r.text.contains(&format!("(constraint {} ", r.constraint)), "{r:?}");
    }
}

#[test]
fn the_strictest_hole_rule_comes_last() {
    // KiCad applies the last matching rule, and a via beside a PTH pad
    // matches both hole rules: the larger limit must win, never the looser.
    let limits = FabricationLimits {
        minimum_via_hole_to_copper_mm: Some(0.3),
        minimum_pth_hole_to_copper_mm: Some(0.28),
        minimum_npth_hole_to_copper_mm: Some(0.2),
        ..Default::default()
    };
    let names: Vec<_> = rules(&limits).into_iter().map(|r| r.name).collect();
    assert_eq!(
        names,
        ["zapote fab NPTH hole to copper", "zapote fab PTH hole to copper", "zapote fab via hole to copper"]
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

#[test]
fn pad_and_inner_layer_rules_follow_the_general_ones() {
    // KiCad applies the last matching rule: the vendor's pad-specific rows
    // must come after the general spacing they refine.
    let list = rules(&parse_profile(FOUR_LAYER_1OZ).unwrap());
    let names: Vec<_> = list.iter().map(|r| r.name.trim_start_matches("zapote fab ")).collect();
    assert_eq!(
        names[..7],
        [
            "copper clearance",
            "pad to track",
            "SMD pad to pad",
            "via hole to copper",
            "NPTH hole to copper",
            "PTH hole to copper",
            "inner PTH hole to copper",
        ]
    );
    let text = |n: &str| list.iter().find(|r| r.name.ends_with(n)).unwrap().text.clone();
    assert_eq!(
        text("pad to track"),
        "(rule \"zapote fab pad to track\" (condition \"A.Type == 'Pad' && B.Type == 'Track'\") \
         (constraint clearance (min 0.1mm)))"
    );
    assert_eq!(
        text("SMD pad to pad"),
        "(rule \"zapote fab SMD pad to pad\" (condition \"A.Type == 'Pad' && A.Pad_Type == 'SMD' && \
         B.Type == 'Pad' && B.Pad_Type == 'SMD'\") (constraint clearance (min 0.15mm)))"
    );
    assert_eq!(
        text("inner PTH hole to copper"),
        "(rule \"zapote fab inner PTH hole to copper\" (layer inner) (condition \"A.Type == 'Pad' && \
         A.Pad_Type == 'Through-hole'\") (constraint hole_clearance (min 0.3mm)))"
    );
}

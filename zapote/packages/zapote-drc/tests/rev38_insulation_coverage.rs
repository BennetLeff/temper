//! Rev38 /03 insulation coverage receipt. This is an intentionally open gate:
//! topology can be counted, but electrical classes and construction limits
//! have not been approved. The 16 mm cross-domain check is diagnostic only.

use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{Status, Trace};
use zapote_drc::{domain_clearance, native_binding};

#[path = "../src/donor_sexpr.rs"]
mod donor_sexpr;
use donor_sexpr::{parse_document, unquote, Sexpr};

const BOARD: &str = include_str!(concat!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/03/native-diagnostic/",
    "section.kicad_pcb"
));
const EXPORT: &str = include_str!(concat!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/03/native-diagnostic/",
    "native-export.json"
));
const MANIFEST: &str = include_str!(concat!(
    "../../../power-entry/passive-reva/protection/interface-integration-38/placement-review/03/native-diagnostic/",
    "source-manifest.json"
));
const BOARD_SHA256: &str = "c277e9cae08213557f8bed43253253966229c695a9e754474d229babcf786ff5";
const EXPORT_SHA256: &str = "3c539845b5e6e7b841d2450732d9ac6bc25b8b64d0abe9d24637ce9fd651b56e";
const MANIFEST_SHA256: &str = "46bd18598f2717da1891d0398639a60bebc798e13bfecb529ac60cbe05de4798";

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum Side {
    Selv,
    Live,
    Pe,
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
enum PairClass {
    SelvInternal,
    LiveInternal,
    SelvLiveReinforcedCandidate,
    SelvPePending,
    LivePePending,
}

fn sha256(text: &str) -> String {
    format!("{:x}", Sha256::digest(text.as_bytes()))
}

fn list(node: &Sexpr) -> &[Sexpr] {
    match node {
        Sexpr::List(items) => items,
        _ => panic!("expected KiCad list"),
    }
}

fn word(node: &Sexpr) -> String {
    match node {
        Sexpr::Atom(value) => unquote(value),
        _ => panic!("expected KiCad atom"),
    }
}

fn children<'a>(node: &'a Sexpr, key: &str) -> Vec<&'a Sexpr> {
    list(node)
        .iter()
        .filter(|child| {
            matches!(child, Sexpr::List(items) if items.first().is_some_and(|first| word(first) == key))
        })
        .collect()
}

fn empty_pad_specs(exported: &serde_json::Value) -> Result<(), String> {
    // The document binder checks pad identity/net but not pad layers.
    let board = parse_document(BOARD, "Rev38 KiCad board")?;
    let mut board_specs = BTreeMap::new();
    for footprint in children(&board, "footprint") {
        for pad in children(footprint, "pad") {
            if !children(pad, "net").is_empty() {
                continue;
            }
            let fields = list(pad);
            let kind = word(&fields[2]);
            let uuid = word(&list(children(pad, "uuid")[0])[1]);
            let layers: Vec<String> = if kind == "np_thru_hole" {
                Vec::new() // pcbnew expands KiCad's wildcard NPTH layers.
            } else {
                list(children(pad, "layers")[0])
                    .iter()
                    .skip(1)
                    .map(word)
                    .collect()
            };
            let kind = if kind == "np_thru_hole" {
                "np_thru_hole"
            } else {
                "electrical"
            };
            if board_specs
                .insert(uuid, (kind.to_owned(), layers))
                .is_some()
            {
                return Err("duplicate saved empty-net pad UUID".into());
            }
        }
    }
    let mut exported_specs = BTreeMap::new();
    for component in exported["components"]
        .as_array()
        .ok_or("missing components")?
    {
        for pad in component["footprint_pads"]
            .as_array()
            .ok_or("missing pads")?
        {
            if pad["net"].as_str() != Some("") {
                continue;
            }
            let uuid = pad["uuid"].as_str().ok_or("missing pad UUID")?;
            let kind = pad["pad_type"].as_str().ok_or("missing pad type")?;
            let layers = if kind == "np_thru_hole" {
                Vec::new()
            } else {
                pad["layers"]
                    .as_array()
                    .ok_or("missing pad layers")?
                    .iter()
                    .map(|layer| layer.as_str().ok_or("invalid pad layer").map(str::to_owned))
                    .collect::<Result<Vec<_>, _>>()?
            };
            if exported_specs
                .insert(uuid.to_owned(), (kind.to_owned(), layers))
                .is_some()
            {
                return Err("duplicate exported empty-net pad UUID".into());
            }
        }
    }
    if board_specs != exported_specs {
        return Err("empty-net pad types/layers differ from KiCad board".into());
    }
    if board_specs.len() != 19 {
        return Err("unexpected empty-net pad census".into());
    }
    Ok(())
}

fn fixture() -> UnitNativeEvidence {
    assert_eq!(sha256(BOARD), BOARD_SHA256);
    assert_eq!(sha256(EXPORT), EXPORT_SHA256);
    assert_eq!(sha256(MANIFEST), MANIFEST_SHA256);
    let source: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
    let exported: serde_json::Value = serde_json::from_str(EXPORT).unwrap();
    assert_eq!(source["board_sha256"], BOARD_SHA256);
    assert_eq!(exported["board_sha256"], BOARD_SHA256);
    assert_eq!(exported["board_file_utf8"], BOARD);
    empty_pad_specs(&exported).unwrap();
    assert_eq!(native_binding::validate(EXPORT).status, Status::Pass);
    serde_json::from_str(EXPORT).unwrap()
}

// Physical side only. This does not infer voltage, insulation grade, or a
// permitted PE bond from a net name or from a symbol marked GND.
fn pad_side(component: &str, pin: &str) -> Result<Side, String> {
    if matches!(
        (component, pin),
        ("ac_input.board_input", "3") | ("ac_input.y1", "2")
    ) {
        return Ok(Side::Pe);
    }
    if component.starts_with("source.") || component.starts_with("source_mcu.") {
        return Ok(Side::Selv);
    }
    if matches!(component, "receiver.iso_protocol" | "receiver.iso_feedback") {
        let pin: u8 = pin
            .parse()
            .map_err(|_| format!("non-numeric isolator pin {pin}"))?;
        return match pin {
            1..=8 => Ok(Side::Selv),
            9..=16 => Ok(Side::Live),
            _ => Err(format!("unknown isolator pin {pin}")),
        };
    }
    if matches!(
        component,
        "receiver.c_iso1_selv"
            | "receiver.c_iso2_selv"
            | "receiver.source_permit_fb_pd"
            | "receiver.source_session_fb_pd"
    ) {
        return Ok(Side::Selv);
    }
    let root = component.split('.').next().unwrap_or("");
    if matches!(
        root,
        "ac_input"
            | "aux_cutoff"
            | "aux_window"
            | "driver"
            | "f2_detector"
            | "hot15_converter"
            | "hot_logic5_converter"
            | "hot_rails"
            | "hot_watchdog"
            | "pfc_control"
            | "pfc_power"
            | "receiver"
    ) {
        Ok(Side::Live)
    } else {
        Err(format!("unclassified component {component}"))
    }
}

fn classify_nets(
    native: &UnitNativeEvidence,
    manifest: &serde_json::Value,
) -> Result<BTreeMap<String, Side>, String> {
    let source_components: BTreeSet<String> = manifest["bridge"]["components"]
        .as_array()
        .ok_or("missing source components")?
        .iter()
        .map(|c| {
            c["instance_path"]
                .as_str()
                .ok_or("unnamed source component")
                .map(str::to_owned)
        })
        .collect::<Result<_, _>>()?;
    let native_components: BTreeSet<String> =
        native.components.iter().map(|c| c.id.clone()).collect();
    if source_components != native_components || native_components.len() != native.components.len()
    {
        return Err("source/native component census differs".into());
    }
    let source_nets: BTreeSet<String> = manifest["bridge"]["nets"]
        .as_array()
        .ok_or("missing source nets")?
        .iter()
        .map(|n| {
            n["name"]
                .as_str()
                .ok_or("unnamed source net")
                .map(str::to_owned)
        })
        .collect::<Result<_, _>>()?;
    let mut native_sides: BTreeMap<String, Side> = BTreeMap::new();
    let mut artwork_pads = 0;
    let mut npth_holes = 0;
    for component in &native.components {
        for pad in &component.footprint_pads {
            if pad.net.is_empty() {
                // No unassigned copper land may disappear from the census.
                if pad.pad.is_empty() && pad.drill_mm[0] > 0.0 {
                    npth_holes += 1;
                } else if pad.pad.is_empty()
                    && !pad.layers.is_empty()
                    && pad.layers.iter().all(|layer| {
                        matches!(layer.as_str(), "F.Paste" | "F.Mask" | "B.Paste" | "B.Mask")
                    })
                    && pad.drill_mm == [0.0, 0.0]
                {
                    artwork_pads += 1;
                } else {
                    return Err(format!(
                        "unassigned copper or unknown pad {}.{}",
                        component.id, pad.pad
                    ));
                }
                continue;
            }
            let side = pad_side(&component.id, &pad.pad)?;
            if let Some(old) = native_sides.insert(pad.net.clone(), side) {
                if old != side {
                    return Err(format!("net {} spans {:?} and {:?}", pad.net, old, side));
                }
            }
        }
    }
    if (artwork_pads, npth_holes) != (16, 3) {
        return Err(format!(
            "unassigned pad census changed: artwork={artwork_pads} npth={npth_holes}"
        ));
    }
    let native_nets: BTreeSet<_> = native_sides.keys().cloned().collect();
    if source_nets != native_nets {
        let missing = source_nets.difference(&native_nets).collect::<Vec<_>>();
        let extra = native_nets.difference(&source_nets).collect::<Vec<_>>();
        return Err(format!(
            "source/native net census differs: missing={missing:?} extra={extra:?}"
        ));
    }
    if native_sides.get("pe") != Some(&Side::Pe) {
        return Err("PE net is absent or misclassified".into());
    }
    for trace in &native.traces {
        if !native_sides.contains_key(&trace.net) {
            return Err(format!("trace has unclassified net {}", trace.net));
        }
    }
    for via in &native.vias {
        if !native_sides.contains_key(&via.net) {
            return Err(format!("via has unclassified net {}", via.net));
        }
    }
    for zone in &native.zones {
        if !native_sides.contains_key(&zone.net) {
            return Err(format!("zone has unclassified net {}", zone.net));
        }
    }
    Ok(native_sides)
}

fn pair_class(a: Side, b: Side) -> PairClass {
    match (a, b) {
        (Side::Selv, Side::Selv) => PairClass::SelvInternal,
        (Side::Live, Side::Live) => PairClass::LiveInternal,
        (Side::Selv, Side::Live) | (Side::Live, Side::Selv) => {
            PairClass::SelvLiveReinforcedCandidate
        }
        (Side::Selv, Side::Pe) | (Side::Pe, Side::Selv) => PairClass::SelvPePending,
        (Side::Live, Side::Pe) | (Side::Pe, Side::Live) => PairClass::LivePePending,
        (Side::Pe, Side::Pe) => unreachable!("only one PE net in frozen source"),
    }
}

type PairKey = (String, String);

fn pair_classes(sides: &BTreeMap<String, Side>) -> BTreeMap<PairKey, PairClass> {
    let entries = sides.iter().collect::<Vec<_>>();
    let mut pairs = BTreeMap::new();
    for (i, (name_a, a)) in entries.iter().enumerate() {
        for (name_b, b) in entries.iter().skip(i + 1) {
            assert!(pairs
                .insert(((*name_a).clone(), (*name_b).clone()), pair_class(**a, **b))
                .is_none());
        }
    }
    pairs
}

fn pair_census(pairs: &BTreeMap<PairKey, PairClass>) -> BTreeMap<PairClass, usize> {
    let mut census = BTreeMap::new();
    for class in pairs.values() {
        *census.entry(*class).or_insert(0) += 1;
    }
    census
}

#[derive(Clone)]
struct DiagnosticRule {
    id: &'static str,
    class: PairClass,
    minimum_mm: f64,
}

fn diagnostic_rule_coverage(
    rules: &[DiagnosticRule],
    census: &BTreeMap<PairClass, usize>,
) -> Result<(), String> {
    let required = PairClass::SelvLiveReinforcedCandidate;
    let matching = rules
        .iter()
        .filter(|r| r.class == required)
        .collect::<Vec<_>>();
    if matching.len() != 1 {
        return Err(format!(
            "expected one provisional SELV/live rule; found {}",
            matching.len()
        ));
    }
    let rule = matching[0];
    if rule.id != "REV38.PROVISIONAL.FR4_SELV_LIVE" || rule.minimum_mm != 16.0 {
        return Err("provisional SELV/live rule was reduced or replaced".into());
    }
    if census.get(&required) != Some(&11_346) {
        return Err("SELV/live pair coverage changed".into());
    }
    Ok(())
}

fn provisional_rule() -> DiagnosticRule {
    DiagnosticRule {
        id: "REV38.PROVISIONAL.FR4_SELV_LIVE",
        class: PairClass::SelvLiveReinforcedCandidate,
        minimum_mm: 16.0,
    }
}

// A diagnostic rule never counts as a release rule. An approved schedule must
// eventually supply a reviewed rule for every classified pair, including PE.
fn missing_release_pairs(
    pairs: &BTreeMap<PairKey, PairClass>,
    approved_pairs: &BTreeSet<PairKey>,
) -> usize {
    pairs
        .iter()
        .filter(|(pair, _)| !approved_pairs.contains(*pair))
        .count()
}

#[test]
fn every_named_source_net_has_one_native_side_and_every_pair_is_counted() {
    let native = fixture();
    let manifest: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
    let sides = classify_nets(&native, &manifest).unwrap();
    assert_eq!(sides.len(), 246);
    assert_eq!(sides.values().filter(|s| **s == Side::Selv).count(), 62);
    assert_eq!(sides.values().filter(|s| **s == Side::Live).count(), 183);
    assert_eq!(sides.values().filter(|s| **s == Side::Pe).count(), 1);

    let pairs = pair_classes(&sides);
    let census = pair_census(&pairs);
    assert_eq!(census.get(&PairClass::SelvInternal), Some(&1_891));
    assert_eq!(census.get(&PairClass::LiveInternal), Some(&16_653));
    assert_eq!(
        census.get(&PairClass::SelvLiveReinforcedCandidate),
        Some(&11_346)
    );
    assert_eq!(census.get(&PairClass::SelvPePending), Some(&62));
    assert_eq!(census.get(&PairClass::LivePePending), Some(&183));
    assert_eq!(pairs.len(), 30_135);
    assert_eq!(census.values().sum::<usize>(), pairs.len());
    assert_eq!(
        pairs.get(&(String::from("hot0"), String::from("selv3v3"))),
        Some(&PairClass::SelvLiveReinforcedCandidate)
    );

    diagnostic_rule_coverage(&[provisional_rule()], &census).unwrap();
    // This check is deliberately not an insulation PASS. No approved pair
    // voltage, air clearance, creepage, solid-insulation or PE schedule exists.
    assert_eq!(missing_release_pairs(&pairs, &BTreeSet::new()), 30_135);
}

#[test]
fn missing_unclassified_and_reduced_provisional_rule_fail_closed() {
    let native = fixture();
    assert!(pad_side("future_domain.unknown", "1")
        .unwrap_err()
        .contains("unclassified component"));
    let mut manifest: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
    let sides = classify_nets(&native, &manifest).unwrap();
    let census = pair_census(&pair_classes(&sides));
    assert!(diagnostic_rule_coverage(&[], &census)
        .unwrap_err()
        .contains("found 0"));
    let mut reduced = provisional_rule();
    reduced.minimum_mm = 15.0;
    assert!(diagnostic_rule_coverage(&[reduced], &census)
        .unwrap_err()
        .contains("reduced"));

    manifest["bridge"]["nets"].as_array_mut().unwrap().pop();
    assert!(classify_nets(&native, &manifest)
        .unwrap_err()
        .contains("net census differs"));
    let mut with_extra_net = native.clone();
    with_extra_net.components[0].footprint_pads[0].net = "unclassified_added_net".into();
    assert!(
        classify_nets(&with_extra_net, &serde_json::from_str(MANIFEST).unwrap())
            .unwrap_err()
            .contains("net census differs")
    );

    let mut with_unassigned_copper = native.clone();
    let unassigned = with_unassigned_copper
        .components
        .iter_mut()
        .flat_map(|c| &mut c.footprint_pads)
        .find(|pad| pad.net.is_empty() && pad.drill_mm == [0.0, 0.0])
        .unwrap();
    unassigned.layers = vec!["F.Cu".into()];
    assert!(classify_nets(
        &with_unassigned_copper,
        &serde_json::from_str(MANIFEST).unwrap()
    )
    .unwrap_err()
    .contains("unassigned copper"));

    let mut wrong_export_layers: serde_json::Value = serde_json::from_str(EXPORT).unwrap();
    let wrong_pad = wrong_export_layers["components"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .flat_map(|component| component["footprint_pads"].as_array_mut().unwrap())
        .find(|pad| pad["net"].as_str() == Some("") && pad["pad_type"] == "electrical")
        .unwrap();
    wrong_pad["layers"] = serde_json::json!(["F.Cu"]);
    assert!(empty_pad_specs(&wrong_export_layers)
        .unwrap_err()
        .contains("differ"));

    let mut miswired_isolator = native.clone();
    let isolator = miswired_isolator
        .components
        .iter_mut()
        .find(|c| c.id == "receiver.iso_protocol")
        .unwrap();
    isolator
        .footprint_pads
        .iter_mut()
        .find(|p| p.pad == "9")
        .unwrap()
        .net = "selv3v3".into();
    assert!(
        classify_nets(&miswired_isolator, &serde_json::from_str(MANIFEST).unwrap())
            .unwrap_err()
            .contains("spans")
    );

    let mut miswired_pe = native;
    let inlet = miswired_pe
        .components
        .iter_mut()
        .find(|c| c.id == "ac_input.board_input")
        .unwrap();
    inlet
        .footprint_pads
        .iter_mut()
        .find(|p| p.pad == "3")
        .unwrap()
        .net = "hot0".into();
    assert!(
        classify_nets(&miswired_pe, &serde_json::from_str(MANIFEST).unwrap())
            .unwrap_err()
            .contains("spans")
    );
}

#[test]
fn injected_selv_to_live_copper_bridge_is_detected_by_native_geometry() {
    let mut native = fixture();
    let manifest: serde_json::Value = serde_json::from_str(MANIFEST).unwrap();
    let sides = classify_nets(&native, &manifest).unwrap();
    let isolator = native
        .components
        .iter()
        .find(|c| c.id == "receiver.iso_protocol")
        .unwrap();
    let selv_pad = isolator
        .footprint_pads
        .iter()
        .find(|p| p.pad == "1")
        .unwrap();
    let live_pad = isolator
        .footprint_pads
        .iter()
        .find(|p| p.pad == "16")
        .unwrap();
    native.traces.push(Trace {
        id: "injected-selv-live-bridge".into(),
        net: selv_pad.net.clone(),
        points_mm: vec![selv_pad.position_mm, live_pad.position_mm],
        layer: "F.Cu".into(),
        width_mm: 0.4,
    });
    let selv = sides
        .iter()
        .filter(|(_, s)| **s == Side::Selv)
        .map(|(n, _)| n.clone())
        .collect();
    let live = sides
        .iter()
        .filter(|(_, s)| **s == Side::Live)
        .map(|(n, _)| n.clone())
        .collect();
    let report = domain_clearance::validate(&native, &selv, &live, 16.0);
    assert_eq!(report.status, Status::Fail);
    assert!(report
        .findings
        .iter()
        .any(|f| f.status == Status::Fail && f.object.contains("injected-selv-live-bridge")));
    let mut exported: serde_json::Value = serde_json::from_str(EXPORT).unwrap();
    exported["traces"] = serde_json::to_value(&native.traces).unwrap();
    assert_eq!(
        native_binding::validate(&exported.to_string()).status,
        Status::Fail
    );
}

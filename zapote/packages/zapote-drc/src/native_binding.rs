//! Corroborate native-export identities against the saved KiCad 10 document.
//! World pad geometry and connectivity remain outputs of the pinned KiCad extractor.
use crate::donor_sexpr::{parse_document, unquote, Sexpr};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};
const RULE: &str = "DRC.NATIVE.DOCUMENT_BINDING";
fn items(n: &Sexpr) -> Result<&[Sexpr], String> {
    if let Sexpr::List(v) = n {
        Ok(v)
    } else {
        Err("expected list".into())
    }
}
fn atom(n: Option<&Sexpr>) -> Result<String, String> {
    if let Some(Sexpr::Atom(s)) = n {
        Ok(unquote(s))
    } else {
        Err("expected atom".into())
    }
}
fn children<'a>(n: &'a Sexpr, key: &str) -> Result<Vec<&'a Sexpr>, String> {
    Ok(items(n)?
        .iter()
        .filter(|n| items(n).is_ok_and(|v| atom(v.first()).is_ok_and(|s| s == key)))
        .collect())
}
fn one<'a>(n: &'a Sexpr, key: &str) -> Result<&'a Sexpr, String> {
    let matches = children(n, key)?;
    if matches.len() != 1 {
        return Err(format!("expected one {key}"));
    }
    Ok(matches[0])
}
fn field(n: &Sexpr, key: &str) -> Result<Vec<String>, String> {
    let v = children(n, key)?;
    if v.len() != 1 {
        return Err(format!("expected one {key}"));
    }
    items(v[0])?.iter().skip(1).map(|n| atom(Some(n))).collect()
}
fn scalar(n: &Sexpr, key: &str) -> Result<String, String> {
    let v = field(n, key)?;
    if v.len() != 1 {
        return Err(format!("expected scalar {key}"));
    }
    Ok(v[0].clone())
}
fn numbers(n: &Sexpr, key: &str) -> Result<Vec<f64>, String> {
    field(n, key)?
        .iter()
        .map(|s| s.parse::<f64>().map_err(|_| format!("invalid {key}")))
        .collect()
}
fn property(n: &Sexpr, name: &str) -> Result<String, String> {
    let found: Vec<_> = children(n, "property")?
        .into_iter()
        .filter(|p| items(p).is_ok_and(|v| atom(v.get(1)).is_ok_and(|s| s == name)))
        .collect();
    if found.len() != 1 {
        return Err(format!("expected one property {name}"));
    }
    atom(items(found[0])?.get(2))
}
fn put(m: &mut BTreeMap<String, Value>, id: String, v: Value) -> Result<(), String> {
    if m.insert(id.clone(), v).is_some() {
        return Err(format!("duplicate {id}"));
    }
    Ok(())
}
fn inspect(n: &Value) -> Result<(), String> {
    let board = parse_document(
        n["board_file_utf8"].as_str().ok_or("missing board bytes")?,
        "KiCad board",
    )?;
    if atom(items(&board)?.first())? != "kicad_pcb" {
        return Err("not a board".into());
    }
    let mut saved = BTreeMap::new();
    let mut exported = BTreeMap::new();
    let mut saved_holes = BTreeMap::new();
    let mut exported_holes = BTreeMap::new();
    let mut saved_uuids = BTreeSet::new();
    let mut exported_uuids = BTreeSet::new();
    for fp in children(&board, "footprint")? {
        let id = property(fp, "SourceInstance")?;
        let mut pins = BTreeMap::new();
        let pads = children(fp, "pad")?;
        let mut counts = BTreeMap::<String, usize>::new();
        for pad in &pads {
            *counts.entry(atom(items(pad)?.get(1))?).or_default() += 1;
        }
        for pad in pads {
            let pin = atom(items(pad)?.get(1))?;
            let uuid_nodes = children(pad, "uuid")?;
            if uuid_nodes.len() > 1 {
                return Err("duplicate pad UUID field".into());
            }
            let uuid = uuid_nodes
                .first()
                .map(|_| scalar(pad, "uuid"))
                .transpose()?;
            if let Some(uuid) = &uuid {
                if uuid.trim().is_empty() || !saved_uuids.insert(uuid.clone()) {
                    return Err("empty or duplicate saved pad UUID".into());
                }
            }
            if atom(items(pad)?.get(2))? == "np_thru_hole" {
                if !pin.is_empty() || !children(pad, "net")?.is_empty() {
                    return Err("mechanical hole has electrical pin/net".into());
                }
                put(
                    &mut saved_holes,
                    uuid.ok_or("mechanical hole requires UUID")?,
                    json!({"component":id}),
                )?;
                continue;
            }
            let key = if counts[&pin] > 1 {
                format!(
                    "{}#{}",
                    pin,
                    uuid.ok_or("repeated physical pin requires UUID")?
                )
            } else {
                pin.clone()
            };
            let net = scalar(pad, "net")?;
            let value = if counts[&pin] > 1 {
                json!({"pin":pin,"net":net})
            } else {
                json!(net)
            };
            put(&mut pins, key, value)?;
        }
        put(
            &mut saved,
            id,
            json!({"mpn":property(fp,"MPN")?,"pins":pins}),
        )?;
    }
    for c in n["components"].as_array().ok_or("missing components")? {
        let mut pins = BTreeMap::new();
        let pads = c["footprint_pads"].as_array().ok_or("missing pads")?;
        let mut counts = BTreeMap::<&str, usize>::new();
        for p in pads {
            *counts
                .entry(p["pad"].as_str().ok_or("missing pin")?)
                .or_default() += 1;
        }
        for p in pads {
            let pin = p["pad"].as_str().ok_or("missing pin")?;
            if let Some(uuid) = p["uuid"].as_str() {
                if uuid.trim().is_empty() || !exported_uuids.insert(uuid.to_owned()) {
                    return Err("empty or duplicate exported pad UUID".into());
                }
            }
            if p["pad_type"].as_str() == Some("np_thru_hole") {
                if !pin.is_empty() || p["net"].as_str() != Some("") {
                    return Err("exported mechanical hole has electrical pin/net".into());
                }
                put(
                    &mut exported_holes,
                    p["uuid"]
                        .as_str()
                        .ok_or("mechanical hole requires UUID")?
                        .to_owned(),
                    json!({"component":c["id"]}),
                )?;
                continue;
            }
            let key = if counts[pin] > 1 {
                format!(
                    "{}#{}",
                    pin,
                    p["uuid"]
                        .as_str()
                        .ok_or("duplicate physical pin requires UUID")?
                )
            } else {
                pin.to_owned()
            };
            let value = if counts[pin] > 1 {
                json!({"pin":pin,"net":p["net"]})
            } else {
                p["net"].clone()
            };
            put(&mut pins, key, value)?;
        }
        put(
            &mut exported,
            c["id"].as_str().ok_or("missing id")?.into(),
            json!({"mpn":c["mpn"],"pins":pins}),
        )?;
    }
    if saved != exported || saved_holes != exported_holes {
        return Err("exported component/MPN/pad nets differ from saved board".into());
    }
    saved.clear();
    exported.clear();
    for t in children(&board, "segment")? {
        put(
            &mut saved,
            scalar(t, "uuid")?,
            json!({"net":scalar(t,"net")?,"layer":scalar(t,"layer")?,"width":numbers(t,"width")?,"points":[numbers(t,"start")?,numbers(t,"end")?]}),
        )?;
    }
    if !children(&board, "arc")?.is_empty() {
        return Err("arc binding is not supported by this entrypoint".into());
    }
    for t in n["traces"].as_array().ok_or("missing traces")? {
        put(
            &mut exported,
            t["uuid"].as_str().ok_or("missing trace UUID")?.into(),
            json!({"net":t["net"],"layer":t["layer"],"width":[t["width_mm"]],"points":t["points_mm"]}),
        )?;
    }
    if saved != exported {
        return Err("exported traces differ from saved board".into());
    }
    saved.clear();
    exported.clear();
    for v in children(&board, "via")? {
        put(
            &mut saved,
            scalar(v, "uuid")?,
            json!({"net":scalar(v,"net")?,"position":numbers(v,"at")?,"size":numbers(v,"size")?,"drill":numbers(v,"drill")?,"layers":field(v,"layers")?}),
        )?;
    }
    for v in n["vias"].as_array().ok_or("missing vias")? {
        put(
            &mut exported,
            v["uuid"].as_str().ok_or("missing via UUID")?.into(),
            json!({"net":v["net"],"position":v["position_mm"],"size":[v["diameter_mm"]],"drill":[v["drill_mm"]],"layers":[v["from_layer"],v["to_layer"]]}),
        )?;
    }
    if saved != exported {
        return Err("exported vias differ from saved board".into());
    }
    Ok(())
}
pub fn validate(native: &str) -> CheckReport {
    let result = serde_json::from_str(native)
        .map_err(|e| e.to_string())
        .and_then(|n| inspect(&n));
    let finding = match result {
        Ok(()) => Finding::pass(
            RULE,
            "component/MPN/pad-net, straight trace and via census match saved board bytes",
            "native",
        ),
        Err(e) => Finding::fail(RULE, e, "native"),
    };
    CheckReport::from_findings(vec![finding], vec![RULE.into()], vec![])
}

const BRIDGE_RULE: &str = "DRC.NATIVE.BRIDGE_NECK_GEOMETRY";

fn approx(actual: f64, expected: f64) -> bool {
    (actual - expected).abs() <= 1.0e-9_f64.max(expected.abs() * 1.0e-9)
}

fn json_pair(value: Option<&Value>, name: &str) -> Result<[f64; 2], String> {
    let values = value
        .and_then(Value::as_array)
        .ok_or_else(|| format!("missing {name}"))?;
    if values.len() != 2 {
        return Err(format!("{name} must contain two values"));
    }
    let pair = values
        .iter()
        .map(|value| {
            value
                .as_f64()
                .ok_or_else(|| format!("{name} is not numeric"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let pair: [f64; 2] = pair.try_into().map_err(|_| format!("invalid {name}"))?;
    if pair.iter().any(|value| !value.is_finite()) {
        return Err(format!("{name} is non-finite"));
    }
    Ok(pair)
}

fn inspect_bridge_neck(native: &Value) -> Result<String, String> {
    let board_text = native["board_file_utf8"]
        .as_str()
        .ok_or("missing board_file_utf8")?;
    let board = parse_document(board_text, "KiCad board").map_err(|e| e.to_string())?;
    if atom(items(&board)?.first())? != "kicad_pcb" {
        return Err("not a KiCad board".into());
    }
    let components = native["components"]
        .as_array()
        .ok_or("missing components")?;
    let saved = components
        .iter()
        .find(|component| component["id"].as_str() == Some("bridge"))
        .ok_or("missing bridge component")?;
    if saved["mpn"].as_str() != Some("GBU2510A") {
        return Err("bridge component MPN is not GBU2510A".into());
    }
    let saved_position = json_pair(Some(&saved["position_mm"]), "bridge position")?;
    let saved_pads = saved["footprint_pads"]
        .as_array()
        .ok_or("bridge footprint pads are missing")?;
    if saved_pads.len() != 4 {
        return Err(format!(
            "bridge requires four saved pads, found {}",
            saved_pads.len()
        ));
    }
    let mut saved_pins = BTreeSet::new();
    for pad in saved_pads {
        let pin = pad["pad"]
            .as_str()
            .ok_or("saved bridge pad number missing")?;
        if !saved_pins.insert(pin) || !matches!(pin, "1" | "2" | "3" | "4") {
            return Err("saved bridge pads must contain unique pins 1-4".into());
        }
        if pad["pad_type"].as_str() != Some("electrical") {
            return Err(format!("saved bridge pad {pin} is not electrical"));
        }
    }
    let footprint_matches = children(&board, "footprint")?
        .into_iter()
        .filter(|footprint| property(footprint, "SourceInstance").is_ok_and(|id| id == "bridge"))
        .collect::<Vec<_>>();
    if footprint_matches.len() != 1 {
        return Err(format!(
            "expected one native bridge footprint, found {}",
            footprint_matches.len()
        ));
    }
    let footprint = footprint_matches[0];
    if scalar(footprint, "layer")? != "F.Cu" {
        return Err("bridge footprint must be on F.Cu".into());
    }
    if property(footprint, "MPN")? != "GBU2510A" {
        return Err("native bridge footprint MPN is not GBU2510A".into());
    }
    let footprint_at = numbers(footprint, "at")?;
    if footprint_at.len() != 2 && footprint_at.len() != 3 {
        return Err("bridge footprint at must have x/y and optional zero rotation".into());
    }
    if footprint_at
        .get(2)
        .is_some_and(|rotation| !approx(*rotation, 0.0))
    {
        return Err("bridge footprint rotation is unsupported".into());
    }
    if !approx(footprint_at[0], saved_position[0]) || !approx(footprint_at[1], saved_position[1]) {
        return Err("bridge footprint position differs from saved component position".into());
    }
    let native_pads = children(footprint, "pad")?;
    if native_pads.len() != 4 {
        return Err(format!(
            "bridge requires four native pads, found {}",
            native_pads.len()
        ));
    }
    let mut native_pins = BTreeSet::new();
    for pad in &native_pads {
        let pin = atom(items(pad)?.get(1))?;
        if !native_pins.insert(pin) {
            return Err("native bridge pads contain duplicate pin numbers".into());
        }
    }
    for saved_pad in saved_pads {
        if !saved_pad["orientation_deg"]
            .as_f64()
            .is_some_and(|v| approx(v, 0.0))
        {
            return Err("exported bridge pad rotation must be zero".into());
        }
        let pin = saved_pad["pad"]
            .as_str()
            .ok_or("saved bridge pad number missing")?;
        let native_pad = native_pads
            .iter()
            .find(|pad| {
                atom(items(pad).ok().and_then(|fields| fields.get(1)))
                    .ok()
                    .as_deref()
                    == Some(pin)
            })
            .ok_or_else(|| format!("native bridge pad {pin} is missing"))?;
        let fields = items(native_pad)?;
        if atom(fields.get(2))? != "thru_hole" {
            return Err(format!("bridge pad {pin} is not through-hole"));
        }
        let expected_shape = if pin == "1" { "rect" } else { "oval" };
        if atom(fields.get(3))? != expected_shape {
            return Err(format!("bridge pad {pin} shape is not {expected_shape}"));
        }
        let native_uuid = scalar(native_pad, "uuid")?;
        if native_uuid != saved_pad["uuid"].as_str().ok_or("saved pad UUID missing")? {
            return Err(format!("bridge pad {pin} UUID differs"));
        }
        let native_at = numbers(native_pad, "at")?;
        if native_at.len() != 2 && native_at.len() != 3 {
            return Err(format!("bridge pad {pin} at is malformed"));
        }
        if native_at
            .get(2)
            .is_some_and(|rotation| !approx(*rotation, 0.0))
        {
            return Err(format!("bridge pad {pin} rotation is unsupported"));
        }
        let world = [
            footprint_at[0] + native_at[0],
            footprint_at[1] + native_at[1],
        ];
        let saved_world = json_pair(Some(&saved_pad["position_mm"]), "saved pad position")?;
        if world
            .iter()
            .zip(saved_world)
            .any(|(actual, expected)| !approx(*actual, expected))
        {
            return Err(format!("bridge pad {pin} world position differs"));
        }
        let size = numbers(native_pad, "size")?;
        let saved_size = json_pair(Some(&saved_pad["size_mm"]), "saved pad size")?;
        if size.len() != 2
            || size
                .iter()
                .zip(saved_size)
                .any(|(actual, expected)| !approx(*actual, expected))
        {
            return Err(format!("bridge pad {pin} size differs"));
        }
        let drill = numbers(native_pad, "drill")?;
        let saved_drill = json_pair(Some(&saved_pad["drill_mm"]), "saved pad drill")?;
        if drill.len() != 1
            || drill[0] <= 0.0
            || saved_drill[0] != saved_drill[1]
            || !approx(drill[0], saved_drill[0])
        {
            return Err(format!("bridge pad {pin} circular drill differs"));
        }
        let expected_enum = if pin == "1" { 1 } else { 2 };
        if saved_pad["shape"].as_u64() != Some(expected_enum) {
            return Err(format!("saved bridge pad {pin} has unexpected shape enum"));
        }
    }
    let stackup = one(one(&board, "setup")?, "stackup")?;
    let mut copper = 0;
    let mut copper_names = BTreeSet::new();
    let mut cores = 0;
    let mut found_core = false;
    for layer in children(stackup, "layer")? {
        let kind = scalar(layer, "type")?;
        let thickness = scalar(layer, "thickness")
            .ok()
            .and_then(|value| value.parse::<f64>().ok());
        let name = atom(items(layer)?.get(1))?;
        if kind == "copper" {
            copper += 1;
            copper_names.insert(name.clone());
            if !thickness.is_some_and(|value| approx(value, 0.07)) {
                return Err(format!("copper layer {name} is not 70 um"));
            }
        }
        if kind == "core" {
            cores += 1;
        }
        if kind == "prepreg" {
            return Err("additional dielectric layer is unsupported".into());
        }
        if kind == "core"
            && thickness.is_some_and(|value| approx(value, 1.44))
            && scalar(layer, "material").ok().as_deref() == Some("FR4")
        {
            found_core = true;
        }
    }
    if copper != 2 || copper_names != BTreeSet::from(["F.Cu".to_owned(), "B.Cu".to_owned()]) {
        return Err(format!("expected two copper layers, found {copper}"));
    }
    if !found_core || cores != 1 {
        return Err("missing 1.44 mm FR-4 core".into());
    }
    Ok(
        "bridge footprint pad UUIDs, shape, size, drill, world positions and 2-layer stackup bind"
            .into(),
    )
}

/// Validate bridge-neck geometry required by the thermal model.
pub fn validate_bridge_neck_geometry(native: &str) -> CheckReport {
    let result = serde_json::from_str(native)
        .map_err(|e| e.to_string())
        .and_then(|native| inspect_bridge_neck(&native));
    let finding = match result {
        Ok(message) => Finding::pass(BRIDGE_RULE, message, "bridge"),
        Err(message) => Finding::fail(BRIDGE_RULE, message, "bridge"),
    };
    CheckReport::from_findings(vec![finding], vec![BRIDGE_RULE.into()], vec![])
}

#[cfg(test)]
mod bridge_tests {
    use super::validate_bridge_neck_geometry;
    use serde_json::{json, Value};
    use zapote_core::Status;

    fn evidence() -> Value {
        let board = r#"(kicad_pcb
          (setup (stackup
            (layer "F.Cu" (type "copper") (thickness 0.07))
            (layer "dielectric 1" (type "core") (thickness 1.44) (material "FR4"))
            (layer "B.Cu" (type "copper") (thickness 0.07))))
          (footprint "Diode_THT:Diode_Bridge_GBU2510"
            (layer "F.Cu")
            (at 30 115)
            (property "SourceInstance" "bridge")
            (property "MPN" "GBU2510A")
            (pad "1" thru_hole rect (at 0 0) (size 3 3.2) (drill 1.6) (uuid "p1"))
            (pad "2" thru_hole oval (at 5.08 0) (size 3 3.2) (drill 1.6) (uuid "p2"))
            (pad "3" thru_hole oval (at 10.16 0) (size 3 3.2) (drill 1.6) (uuid "p3"))
            (pad "4" thru_hole oval (at 15.24 0) (size 3 3.2) (drill 1.6) (uuid "p4")))
        )"#;
        json!({
            "board_file_utf8": board,
            "components": [{
                "id": "bridge", "mpn": "GBU2510A", "position_mm": [30.0, 115.0],
                "footprint_pads": [
                    {"pad":"1","orientation_deg":0.0,"pad_type":"electrical","uuid":"p1","position_mm":[30.0,115.0],"size_mm":[3.0,3.2],"drill_mm":[1.6,1.6],"shape":1},
                    {"pad":"2","orientation_deg":0.0,"pad_type":"electrical","uuid":"p2","position_mm":[35.08,115.0],"size_mm":[3.0,3.2],"drill_mm":[1.6,1.6],"shape":2},
                    {"pad":"3","orientation_deg":0.0,"pad_type":"electrical","uuid":"p3","position_mm":[40.16,115.0],"size_mm":[3.0,3.2],"drill_mm":[1.6,1.6],"shape":2},
                    {"pad":"4","orientation_deg":0.0,"pad_type":"electrical","uuid":"p4","position_mm":[45.24,115.0],"size_mm":[3.0,3.2],"drill_mm":[1.6,1.6],"shape":2}
                ]
            }]
        })
    }

    #[test]
    fn bridge_geometry_passes_against_native_fixture() {
        assert_eq!(
            validate_bridge_neck_geometry(&evidence().to_string()).status,
            Status::Pass
        );
    }

    #[test]
    fn actual_power_entry_geometry_binds() {
        assert_eq!(
            validate_bridge_neck_geometry(include_str!(
                "../../../power-entry/evidence/native-copper-12.json"
            ))
            .status,
            Status::Pass
        );
    }

    #[test]
    fn bridge_geometry_mutations_fail_closed() {
        let original = evidence();
        let board = original["board_file_utf8"].as_str().unwrap();
        for replacement in [
            board.replace("(size 3 3.2)", "(size 3.1 3.2)"),
            board.replace("(drill 1.6)", "(drill 1.5)"),
            board.replace("(pad \"1\" thru_hole rect", "(pad \"1\" thru_hole oval"),
            board.replace("(at 30 115)", "(at 31 115)"),
            board.replace("(thickness 1.44)", "(thickness 1.20)"),
        ] {
            let mut mutated = original.clone();
            mutated["board_file_utf8"] = json!(replacement);
            assert_eq!(
                validate_bridge_neck_geometry(&mutated.to_string()).status,
                Status::Fail
            );
        }
    }
}

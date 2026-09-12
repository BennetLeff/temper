//! Corroborate native-export identities against the saved KiCad 10 document.
//! World pad geometry and connectivity remain outputs of the pinned KiCad extractor.
use crate::donor_sexpr::{parse_document, unquote, Sexpr};
use serde_json::{json, Value};
use std::collections::BTreeMap;
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
    for fp in children(&board, "footprint")? {
        let id = property(fp, "SourceInstance")?;
        let mut pins = BTreeMap::new();
        for pad in children(fp, "pad")? {
            let pin = atom(items(pad)?.get(1))?;
            put(&mut pins, pin, json!(scalar(pad, "net")?))?;
        }
        put(
            &mut saved,
            id,
            json!({"mpn":property(fp,"MPN")?,"pins":pins}),
        )?;
    }
    for c in n["components"].as_array().ok_or("missing components")? {
        let mut pins = BTreeMap::new();
        for p in c["footprint_pads"].as_array().ok_or("missing pads")? {
            put(
                &mut pins,
                p["pad"].as_str().ok_or("missing pin")?.into(),
                p["net"].clone(),
            )?;
        }
        put(
            &mut exported,
            c["id"].as_str().ok_or("missing id")?.into(),
            json!({"mpn":c["mpn"],"pins":pins}),
        )?;
    }
    if saved != exported {
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

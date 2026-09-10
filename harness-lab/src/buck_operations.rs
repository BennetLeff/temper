//! Rust-owned schema and policy for the complete buck operation boundary.
//!
//! The Python host only owns file I/O and KiCad invocation. All request
//! shape, numeric limits, and admitted domain values live here.
use anyhow::{ensure, Result};
use serde_json::{json, Map, Value};

pub const MAX_ACTIONS: u64 = 200;
pub const MAX_SECONDS: f64 = 1200.0;
pub const MAX_OBJECTS: usize = 512;
pub const MAX_COORD_MM: f64 = 100.0;
pub const MAX_EXECUTE_BYTES: usize = 65_536;
const REFS: &[&str] = &["U3", "L2", "C9", "C10", "C11", "C12", "C13", "R16", "R17"];
const NETS: &[&str] = &["+15V", "gnd", "sw", "boot", "fb", "+3V3"];
const LAYERS: &[&str] = &["F.Cu", "B.Cu"];

fn finite(v: &Value) -> bool {
    v.as_f64().is_some_and(f64::is_finite)
}

fn point(v: &Value) -> bool {
    v.as_array().is_some_and(|a| {
        a.len() == 2
            && a.iter().all(|coordinate| {
                finite(coordinate) && coordinate.as_f64().unwrap().abs() <= MAX_COORD_MM
            })
    })
}

fn exact_keys(object: &Map<String, Value>, keys: &[&str], message: &str) -> Result<()> {
    ensure!(
        object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key)),
        "{message}"
    );
    Ok(())
}

fn schema() -> Value {
    let coordinate = json!({"type":"number", "minimum":-100.0, "maximum":100.0});
    let width = json!({"type":"number", "minimum":0.2, "maximum":2.0});
    let point = json!({"type":"array", "minItems":2, "maxItems":2, "items":coordinate});
    json!({
        "max_actions": MAX_ACTIONS, "max_seconds": MAX_SECONDS,
        "max_objects": MAX_OBJECTS, "max_execute_bytes": MAX_EXECUTE_BYTES,
        "tools": [
            {"name":"inspect", "description":"Inspect the saved buck board.", "inputSchema":{"type":"object","properties":{},"additionalProperties":false}},
            {"name":"check", "description":"Reload and independently evaluate the board.", "inputSchema":{"type":"object","properties":{},"additionalProperties":false}},
            {"name":"place", "description":"Place one functional buck footprint; copper remains stationary.", "inputSchema":{"type":"object","properties":{"reference":{"type":"string","enum":REFS},"x_mm":coordinate,"y_mm":coordinate,"angle_deg":{"type":"integer","enum":[0,90,180,270]}},"required":["reference","x_mm","y_mm","angle_deg"],"additionalProperties":false}},
            {"name":"replace_copper", "description":"Atomically replace all mutable copper for one admitted net.", "inputSchema":{"type":"object","properties":{"net":{"type":"string","enum":NETS},"segments":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"start_mm":point,"end_mm":point,"layer":{"type":"string","enum":LAYERS},"width_mm":width},"required":["start_mm","end_mm","layer","width_mm"],"additionalProperties":false}},"vias":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"position_mm":point,"diameter_mm":{"type":"number","const":0.8},"drill_mm":{"type":"number","const":0.4}},"required":["position_mm","diameter_mm","drill_mm"],"additionalProperties":false}},"zones":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"layer":{"type":"string","enum":LAYERS},"outline_mm":{"type":"array","minItems":3,"maxItems":64,"items":point}},"required":["layer","outline_mm"],"additionalProperties":false}}},"required":["net","segments","vias","zones"],"additionalProperties":false}},
            {"name":"execute", "description":"Reserved for the P2 persistent interpreter boundary.", "inputSchema":{"type":"object","properties":{"code":{"type":"string","maxLength":MAX_EXECUTE_BYTES}},"required":["code"],"additionalProperties":false}}
        ]
    })
}

fn context_outline(input: &Value) -> Option<[f64; 4]> {
    input
        .get("context")?
        .get("outline_mm")?
        .as_array()
        .and_then(|a| {
            if a.len() != 4 {
                return None;
            }
            Some([
                a[0].as_f64()?,
                a[1].as_f64()?,
                a[2].as_f64()?,
                a[3].as_f64()?,
            ])
        })
}

pub fn validate(input: Value) -> Result<Value> {
    let operation = input
        .get("operation")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing operation"))?;
    let args = input
        .get("arguments")
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow::anyhow!("arguments must be an object"))?;
    if operation == "schema" {
        ensure!(args.is_empty(), "schema takes no arguments");
        return Ok(schema());
    }
    match operation {
        "inspect" | "check" => ensure!(args.is_empty(), "{operation} takes no arguments"),
        "execute" => {
            exact_keys(args, &["code"], "execute requires exact keys")?;
            ensure!(
                args["code"]
                    .as_str()
                    .is_some_and(|code| code.len() <= MAX_EXECUTE_BYTES),
                "code must be a UTF-8 string of at most 65536 bytes"
            );
            ensure!(false, "execute is reserved for P2");
        }
        "place" => {
            exact_keys(
                args,
                &["reference", "x_mm", "y_mm", "angle_deg"],
                "place requires exact keys",
            )?;
            let reference = args["reference"]
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("reference must be a string"))?;
            ensure!(
                REFS.contains(&reference),
                "reference is protected or unknown"
            );
            ensure!(
                finite(&args["x_mm"]) && finite(&args["y_mm"]),
                "coordinates must be finite"
            );
            ensure!(
                args["x_mm"].as_f64().unwrap().abs() <= MAX_COORD_MM
                    && args["y_mm"].as_f64().unwrap().abs() <= MAX_COORD_MM,
                "coordinates exceed native range"
            );
            let angle = args["angle_deg"]
                .as_i64()
                .ok_or_else(|| anyhow::anyhow!("angle must be an integer"))?;
            ensure!(
                [0, 90, 180, 270].contains(&angle),
                "angle must be 0, 90, 180, or 270"
            );
            if let Some([x0, y0, x1, y1]) = context_outline(&input) {
                ensure!(
                    x0.is_finite()
                        && y0.is_finite()
                        && x1.is_finite()
                        && y1.is_finite()
                        && x0 <= x1
                        && y0 <= y1,
                    "invalid outline context"
                );
                let x = args["x_mm"].as_f64().unwrap();
                let y = args["y_mm"].as_f64().unwrap();
                ensure!(
                    (x0..=x1).contains(&x) && (y0..=y1).contains(&y),
                    "footprint origin must be inside the outline"
                );
            }
        }
        "replace_copper" => {
            exact_keys(
                args,
                &["net", "segments", "vias", "zones"],
                "replace_copper requires exact keys",
            )?;
            let net = args["net"]
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("net must be a string"))?;
            ensure!(NETS.contains(&net), "unknown net");
            let segments = args["segments"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("segments must be an array"))?;
            let vias = args["vias"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("vias must be an array"))?;
            let zones = args["zones"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("zones must be an array"))?;
            ensure!(
                segments.len() <= MAX_OBJECTS
                    && vias.len() <= MAX_OBJECTS
                    && zones.len() <= MAX_OBJECTS,
                "object limit exceeded"
            );
            for segment in segments {
                let object = segment
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("segment must be an object"))?;
                exact_keys(
                    object,
                    &["start_mm", "end_mm", "layer", "width_mm"],
                    "invalid segment keys",
                )?;
                ensure!(
                    point(&object["start_mm"]) && point(&object["end_mm"]),
                    "invalid segment points"
                );
                ensure!(
                    LAYERS.contains(&object["layer"].as_str().unwrap_or("")),
                    "invalid segment layer"
                );
                ensure!(
                    finite(&object["width_mm"])
                        && (0.2..=2.0).contains(&object["width_mm"].as_f64().unwrap()),
                    "invalid segment width"
                );
            }
            for via in vias {
                let object = via
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("via must be an object"))?;
                exact_keys(
                    object,
                    &["position_mm", "diameter_mm", "drill_mm"],
                    "invalid via keys",
                )?;
                ensure!(point(&object["position_mm"]), "invalid via position");
                ensure!(
                    object["diameter_mm"].as_f64() == Some(0.8)
                        && object["drill_mm"].as_f64() == Some(0.4),
                    "vias must use frozen 0.8/0.4 mm dimensions"
                );
            }
            for zone in zones {
                let object = zone
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("zone must be an object"))?;
                exact_keys(object, &["layer", "outline_mm"], "invalid zone keys")?;
                ensure!(
                    net == "gnd" && LAYERS.contains(&object["layer"].as_str().unwrap_or("")),
                    "only gnd zones on admitted layers are allowed"
                );
                let outline = object["outline_mm"]
                    .as_array()
                    .ok_or_else(|| anyhow::anyhow!("invalid zone outline"))?;
                ensure!(
                    (3..=64).contains(&outline.len()) && outline.iter().all(point),
                    "invalid zone outline"
                );
            }
        }
        _ => ensure!(false, "unknown operation"),
    }
    Ok(
        json!({"status":"pass", "operation":operation, "max_actions":MAX_ACTIONS, "max_seconds":MAX_SECONDS, "max_objects":MAX_OBJECTS}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn place_rejects_protected_reference() {
        assert!(validate(json!({"operation":"place","arguments":{"reference":"J1","x_mm":1,"y_mm":1,"angle_deg":0}})).is_err());
    }
    #[test]
    fn replace_copper_rejects_nested_unknown_key() {
        assert!(validate(json!({"operation":"replace_copper","arguments":{"net":"gnd","segments":[{"start_mm":[0,0],"end_mm":[1,1],"layer":"F.Cu","width_mm":0.5,"extra":1}],"vias":[],"zones":[]}})).is_err());
    }
    #[test]
    fn replace_copper_rejects_non_ground_zone() {
        assert!(validate(json!({"operation":"replace_copper","arguments":{"net":"sw","segments":[],"vias":[],"zones":[{"layer":"F.Cu","outline_mm":[[0,0],[1,0],[0,1]]}]}})).is_err());
    }
    #[test]
    fn schema_contains_nested_shapes() {
        let value = validate(json!({"operation":"schema","arguments":{}})).unwrap();
        assert_eq!(value["tools"].as_array().unwrap().len(), 5);
        assert!(value.to_string().contains("start_mm"));
    }
}

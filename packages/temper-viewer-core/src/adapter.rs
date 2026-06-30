use crate::model::*;
use crate::types::*;
use serde_json::Value;

pub fn from_visualization_state(json: &str) -> Result<Board, String> {
    let value: Value = serde_json::from_str(json).map_err(|e| format!("JSON parse error: {}", e))?;
    from_viz_state_value(&value)
}

pub fn from_viz_state_value(value: &Value) -> Result<Board, String> {
    let board_value = value.get("board").ok_or_else(|| "Missing 'board' field".to_string())?;
    from_board_value(board_value)
}

pub fn from_board_value(value: &Value) -> Result<Board, String> {
    let width = value.get("width").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let height = value.get("height").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let title = value.get("title").and_then(|v| v.as_str()).map(|s| s.to_string());

    let components = value.get("components")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_component).collect::<Result<Vec<_>, _>>())
        .unwrap_or(Ok(vec![]))?;

    let traces = value.get("traces")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_trace).collect::<Result<Vec<_>, _>>())
        .unwrap_or(Ok(vec![]))?;

    let pads = value.get("pads")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_pad).collect::<Result<Vec<_>, _>>())
        .unwrap_or(Ok(vec![]))?;

    let zones = value.get("zones")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_zone).collect::<Result<Vec<_>, _>>())
        .unwrap_or(Ok(vec![]))?;

    Ok(Board { width, height, components, traces, pads, zones, title })
}

fn parse_point(value: &Value) -> Result<Point, String> {
    if let Some(arr) = value.as_array()
        && arr.len() >= 2 {
            let x = arr[0].as_f64().unwrap_or(0.0) as f32;
            let y = arr[1].as_f64().unwrap_or(0.0) as f32;
            return Ok(Point::new(x, y));
        }
    if let Some(obj) = value.as_object() {
        let x = obj.get("x").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
        let y = obj.get("y").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
        return Ok(Point::new(x, y));
    }
    Ok(Point::new(0.0, 0.0))
}

fn parse_component(value: &Value) -> Result<Component, String> {
    let ref_ = value.get("ref")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "Component missing 'ref' field".to_string())?
        .to_string();
    let position = value.get("position").map(parse_point).unwrap_or(Ok(Point::new(0.0, 0.0)))?;
    let rotation = value.get("rotation").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let width = value.get("width").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let height = value.get("height").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let status = value.get("status").and_then(|v| v.as_str()).map(|s| match s {
        "ok" => ComponentStatus::Ok,
        "warning" => ComponentStatus::Warning,
        "error" => ComponentStatus::Error,
        "fixed" => ComponentStatus::Fixed,
        _ => ComponentStatus::Ok,
    }).unwrap_or_default();
    let zone = value.get("zone").and_then(|v| v.as_str()).map(|s| s.to_string());
    let footprint = value.get("footprint").and_then(|v| v.as_str()).map(|s| s.to_string());
    let value_str = value.get("value").and_then(|v| v.as_str()).map(|s| s.to_string());
    let violations = value.get("violations").and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_default();
    let component_type = ComponentType::from_ref_designator(&ref_);
    let loss_contribution = value.get("loss_contribution").and_then(|v| v.as_f64()).map(|f| f as f32);
    let loss_breakdown = value.get("loss_breakdown").and_then(|v| v.as_object())
        .map(|obj| obj.iter().filter_map(|(k, v)| v.as_f64().map(|f| (k.clone(), f as f32))).collect());
    let active_constraints = value.get("active_constraints").and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(parse_constraint_info).collect())
        .unwrap_or_default();
    let last_gradient = value.get("last_gradient").and_then(|v| v.as_array())
        .and_then(|arr| if arr.len() >= 2 { Some((arr[0].as_f64().unwrap_or(0.0) as f32, arr[1].as_f64().unwrap_or(0.0) as f32)) } else { None });
    let last_movement = value.get("last_movement").and_then(|v| v.as_array())
        .and_then(|arr| if arr.len() >= 2 { Some((arr[0].as_f64().unwrap_or(0.0) as f32, arr[1].as_f64().unwrap_or(0.0) as f32)) } else { None });
    let last_movement_reason = value.get("last_movement_reason").and_then(|v| v.as_str()).map(|s| s.to_string());

    Ok(Component {
        ref_, position, rotation, width, height, status, zone, footprint,
        value: value_str, violations, component_type,
        loss_contribution, loss_breakdown, active_constraints,
        last_gradient, last_movement, last_movement_reason,
    })
}

fn parse_constraint_info(value: &Value) -> Option<ConstraintInfo> {
    let obj = value.as_object()?;
    let constraint_type = obj.get("constraint_type").or(obj.get("type")).and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
    let status = obj.get("status").and_then(|v| v.as_str()).map(|s| match s {
        "ok" => ConstraintBinding::Ok,
        "warning" => ConstraintBinding::Warning,
        "error" => ConstraintBinding::Error,
        _ => ConstraintBinding::Ok,
    }).unwrap_or(ConstraintBinding::Ok);
    let message = obj.get("message").and_then(|v| v.as_str()).map(|s| s.to_string());
    Some(ConstraintInfo { constraint_type, status, message })
}

fn parse_trace(value: &Value) -> Result<Trace, String> {
    let start = value.get("start").map(parse_point).unwrap_or(Ok(Point::new(0.0, 0.0)))?;
    let end = value.get("end").map(parse_point).unwrap_or(Ok(Point::new(0.0, 0.0)))?;
    let width = value.get("width").and_then(|v| v.as_f64()).unwrap_or(0.25) as f32;
    let layer = value.get("layer").and_then(|v| v.as_str()).unwrap_or("F.Cu").to_string();
    let net = value.get("net").and_then(|v| v.as_str()).map(|s| s.to_string());
    Ok(Trace { start, end, width, layer, net })
}

fn parse_pad(value: &Value) -> Result<Pad, String> {
    let position = value.get("position").map(parse_point).unwrap_or(Ok(Point::new(0.0, 0.0)))?;
    let size = value.get("size").and_then(|v| v.as_array())
        .and_then(|arr| if arr.len() >= 2 {
            Some((arr[0].as_f64().unwrap_or(0.0) as f32, arr[1].as_f64().unwrap_or(0.0) as f32))
        } else { None })
        .unwrap_or((0.0, 0.0));
    let shape = value.get("shape").and_then(|v| v.as_str()).map(|s| match s {
        "circle" => PadShape::Circle,
        "oval" => PadShape::Oval,
        "roundrect" => PadShape::RoundRect,
        "custom" => PadShape::Custom,
        _ => PadShape::Rect,
    }).unwrap_or_default();
    let rotation = value.get("rotation").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
    let layer = value.get("layer").and_then(|v| v.as_str()).unwrap_or("F.Cu").to_string();
    let number = value.get("number").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let net = value.get("net").and_then(|v| v.as_str()).map(|s| s.to_string());
    let component_ref = value.get("component_ref").and_then(|v| v.as_str()).map(|s| s.to_string());
    Ok(Pad { position, size, shape, rotation, layer, number, net, component_ref })
}

fn parse_zone(value: &Value) -> Result<Zone, String> {
    let name = value.get("name").and_then(|v| v.as_str()).unwrap_or("?").to_string();
    let polygon = value.get("polygon").and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_point).collect::<Result<Vec<_>, _>>())
        .unwrap_or(Ok(vec![]))?;
    let zone_type = value.get("zone_type").and_then(|v| v.as_str()).unwrap_or("generic").to_string();
    let color = value.get("color").and_then(|v| v.as_str()).map(|s| s.to_string());
    Ok(Zone { name, polygon, zone_type, color })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_minimal_board() {
        let json = r#"{"board": {"width": 100.0, "height": 150.0}}"#;
        let board = from_visualization_state(json).unwrap();
        assert_eq!(board.width, 100.0);
        assert_eq!(board.height, 150.0);
        assert!(board.components.is_empty());
    }

    #[test]
    fn parse_full_visualization_state() {
        let json = r###"{
            "board": {
                "width": 100.0,
                "height": 150.0,
                "components": [
                    {"ref": "U1", "position": [50.0, 75.0], "rotation": 0.0, "width": 10.0, "height": 5.0, "footprint": "SOIC-8", "value": "LM358", "zone": "control_zone", "status": "ok", "loss_contribution": 2.5, "loss_breakdown": {"overlap": 1.0, "wirelength": 1.5}},
                    {"ref": "C1", "position": [30.0, 60.0], "rotation": 90.0, "width": 2.0, "height": 1.0, "footprint": "0805", "value": "100uF", "status": "warning"}
                ],
                "traces": [
                    {"start": [0.0, 0.0], "end": [10.0, 20.0], "width": 0.5, "layer": "F.Cu", "net": "VCC"},
                    {"start": [10.0, 20.0], "end": [30.0, 40.0], "width": 0.3, "layer": "In1.Cu"}
                ],
                "pads": [
                    {"position": [48.0, 75.0], "size": [1.5, 0.6], "shape": "rect", "layer": "F.Cu", "number": "1", "net": "VCC", "component_ref": "U1"},
                    {"position": [52.0, 75.0], "size": [1.2, 1.2], "shape": "circle", "layer": "F.Cu", "number": "2", "net": "GND", "component_ref": "U1"}
                ],
                "zones": [
                    {"name": "power_zone", "polygon": [[0.0, 0.0], [50.0, 0.0], [50.0, 75.0], [0.0, 75.0]], "zone_type": "power_zone", "color": "#ff0000"}
                ]
            },
            "epoch": 42,
            "loss_history": {"epochs": 42, "total_loss": [3.1]}
        }"###;
        let board = from_visualization_state(json).unwrap();
        assert_eq!(board.width, 100.0);
        assert_eq!(board.height, 150.0);
        assert_eq!(board.components.len(), 2);
        assert_eq!(board.traces.len(), 2);
        assert_eq!(board.pads.len(), 2);
        assert_eq!(board.zones.len(), 1);

        let u1 = &board.components[0];
        assert_eq!(u1.ref_, "U1");
        assert_eq!(u1.component_type, ComponentType::Ic);
        assert!((u1.position.x - 50.0).abs() < 0.01);
        assert!((u1.position.y - 75.0).abs() < 0.01);
        assert_eq!(u1.rotation, 0.0);
        assert_eq!(u1.footprint.as_deref(), Some("SOIC-8"));
        assert_eq!(u1.loss_contribution, Some(2.5));
        let breakdown = u1.loss_breakdown.as_ref().unwrap();
        assert_eq!(breakdown.get("overlap"), Some(&1.0));
        assert_eq!(breakdown.get("wirelength"), Some(&1.5));

        let c1 = &board.components[1];
        assert_eq!(c1.ref_, "C1");
        assert_eq!(c1.component_type, ComponentType::Capacitor);
        assert_eq!(c1.rotation, 90.0);
        assert_eq!(c1.status, ComponentStatus::Warning);

        let trace = &board.traces[0];
        assert_eq!(trace.width, 0.5);
        assert_eq!(trace.layer, "F.Cu");
        assert_eq!(trace.net.as_deref(), Some("VCC"));

        let pad = &board.pads[1];
        assert_eq!(pad.shape, PadShape::Circle);
        assert_eq!(pad.number, "2");
        assert_eq!(pad.component_ref.as_deref(), Some("U1"));

        let zone = &board.zones[0];
        assert_eq!(zone.name, "power_zone");
        assert_eq!(zone.polygon.len(), 4);
        assert!((zone.area() - 3750.0).abs() < 1.0);
    }

    #[test]
    fn parse_missing_optional_fields() {
        let json = r#"{"board": {"width": 50.0, "height": 50.0, "components": [{"ref": "R1", "position": [10.0, 10.0], "rotation": 0.0, "width": 2.0, "height": 1.0}]}}"#;
        let board = from_visualization_state(json).unwrap();
        let r1 = &board.components[0];
        assert_eq!(r1.value, None);
        assert_eq!(r1.zone, None);
        assert!(r1.violations.is_empty());
        assert_eq!(r1.loss_contribution, None);
        assert!(r1.active_constraints.is_empty());
    }

    #[test]
    fn parse_empty_arrays() {
        let json = r#"{"board": {"width": 100.0, "height": 100.0, "components": [], "traces": [], "pads": [], "zones": []}}"#;
        let board = from_visualization_state(json).unwrap();
        assert!(board.components.is_empty());
        assert!(board.traces.is_empty());
    }

    #[test]
    fn parse_missing_ref_is_error() {
        let json = r#"{"board": {"width": 50.0, "height": 50.0, "components": [{"position": [10.0, 10.0], "rotation": 0.0, "width": 2.0, "height": 1.0}]}}"#;
        let result = from_visualization_state(json);
        assert!(result.is_err());
    }

    #[test]
    fn parse_empty_ref_is_error() {
        let json = r#"{"board": {"width": 50.0, "height": 50.0, "components": [{"ref": "", "position": [10.0, 10.0], "rotation": 0.0, "width": 2.0, "height": 1.0}]}}"#;
        let result = from_visualization_state(json);
        assert!(result.is_err());
    }

    #[test]
    fn parse_missing_board_field() {
        let json = r#"{"epoch": 1}"#;
        let result = from_visualization_state(json);
        assert!(result.is_err());
    }
}

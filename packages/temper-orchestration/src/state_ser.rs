// Option-E subprocess serialization: `NativeBoardState` <-> JSON.
//
// The Rust CLI driver (crates/temper-cli `pipeline-run`) owns the pipeline
// loop over `PipelineRunner<NativeBoardState>`; each stage shells out to a
// Python subprocess (`scripts/_stage_subprocess.py`) that materializes the
// Python-side `deterministic.state.BoardState`, runs the stage's
// already-migrated Rust pyfunction, and serializes the mutated state back.
// This module is the wire codec both sides agree on.
//
// # What is serialized
//
// Only what crosses the process boundary and survives it:
//
// - `net_order` — the one plain typed field.
// - the eleven OWNED collection/list fields (`temper-data-model` types) —
//   these are pure data, so JSON round-trips them exactly. Element shapes
//   mirror the Python shapes `netlist_owned.rs`'s `Marshal` impls read
//   (attribute names match 1:1), so the Python side can rebuild objects the
//   pyfunctions' `d1_bridge::from_python` accepts.
// - OPAQUE fields (`Option<Box<dyn Any + Send + Sync>>`) are NOT serialized.
//   They hold interpreter-shaped values (the parsed `Board`, the constraints
//   object, ...) with no owned representation; every subprocess invocation
//   re-bootstraps them from `--pcb` / `--config` instead of threading them
//   through JSON. A non-None opaque that is not a `serde_json::Value` is a
//   LOUD error naming the field (never a silent drop).
//
// # The int-vs-float canon (`Val`)
//
// `Val::Int`/`Val::Float` are tagged `{"int": i}` / `{"float": f}` — the
// same concrete-Python-type hazard `marshal.rs`'s `Val` documents: `2` must
// not widen to `2.0` across the boundary.

use std::collections::HashSet;

use serde_json::{Map, Value, json};

use temper_data_model::{
    ConnectivityViolation, ConnectivityViolationList, LayerAssignment, LayerAssignmentSet,
    Placement, PlacementSet, PlacementViolation, PlacementViolationList, Route, RouteSet, SlotPos,
    StrPairSet, Val, Via, ViaSet, Violation, ViolationList, Zone, ZoneSet, ZoneSlots, ZoneSlotsSet,
};

use crate::board_state::{NativeBoardState, SlotId};
use crate::stage::{StageError, StageErrorKind};

fn err(stage: &str, message: String) -> StageError {
    StageError::new(stage, message, StageErrorKind::Fatal)
}

const SER_STAGE: &str = "state_ser";

// ---------------------------------------------------------------------------
// Val — the int-or-float tagged encoding
// ---------------------------------------------------------------------------

fn val_to_json(v: &Val) -> Value {
    match v {
        Val::Int(i) => json!({ "int": i }),
        Val::Float(f) => json!({ "float": f }),
    }
}

fn val_from_json(v: &Value) -> Result<Val, String> {
    let obj = v
        .as_object()
        .ok_or("expected {\"int\": ..} or {\"float\": ..}")?;
    if let Some(i) = obj.get("int") {
        return Ok(Val::Int(
            i.as_i64().ok_or("\"int\" tag value must be an integer")?,
        ));
    }
    if let Some(f) = obj.get("float") {
        return Ok(Val::Float(
            f.as_f64().ok_or("\"float\" tag value must be a number")?,
        ));
    }
    Err("expected {\"int\": ..} or {\"float\": ..}".to_string())
}

/// JSON cannot carry NaN/inf; the state fields this codec serves never hold
/// them in production data, and a surprise NaN is a loud error rather than a
/// silent null.
fn finite(f: f64, field: &str) -> Result<Value, String> {
    if f.is_finite() {
        Ok(json!(f))
    } else {
        Err(format!(
            "{field}: non-finite float {f} is not JSON-representable"
        ))
    }
}

fn f64_from(v: &Value, field: &str) -> Result<f64, String> {
    let f = v
        .as_f64()
        .ok_or_else(|| format!("{field}: expected a number"))?;
    if f.is_finite() {
        Ok(f)
    } else {
        Err(format!("{field}: non-finite float"))
    }
}

// ---------------------------------------------------------------------------
// Element codecs — shapes mirror netlist_owned.rs's Marshal attribute names
// ---------------------------------------------------------------------------

fn zone_to_json(z: &Zone) -> Result<Value, String> {
    let ((x0, y0), (x1, y1)) = &z.bounds;
    Ok(json!({
        "name": z.name,
        "bounds": [[val_to_json(x0), val_to_json(y0)], [val_to_json(x1), val_to_json(y1)]],
    }))
}

fn zone_from_json(v: &Value) -> Result<Zone, String> {
    let name = v
        .get("name")
        .and_then(Value::as_str)
        .ok_or("zone: missing \"name\"")?
        .to_string();
    let bounds = v
        .get("bounds")
        .and_then(Value::as_array)
        .ok_or("zone: missing \"bounds\"")?;
    if bounds.len() != 2 {
        return Err(format!("zone {name}: bounds must be [[min],[max]]"));
    }
    let pair = |a: &Value| -> Result<(Val, Val), String> {
        let arr = a.as_array().ok_or("zone bounds corner: expected [x, y]")?;
        if arr.len() != 2 {
            return Err("zone bounds corner: expected [x, y]".to_string());
        }
        Ok((val_from_json(&arr[0])?, val_from_json(&arr[1])?))
    };
    Ok(Zone {
        name,
        bounds: (pair(&bounds[0])?, pair(&bounds[1])?),
    })
}

fn route_to_json(r: &Route) -> Result<Value, String> {
    Ok(json!({
        "start": [finite(r.start.0, "route.start")?, finite(r.start.1, "route.start")?],
        "end": [finite(r.end.0, "route.end")?, finite(r.end.1, "route.end")?],
        "width": finite(r.width, "route.width")?,
        "layer": r.layer,
        "net": r.net,
    }))
}

fn route_from_json(v: &Value) -> Result<Route, String> {
    let coord = |v: &Value, what: &str| -> Result<(f64, f64), String> {
        let a = v
            .as_array()
            .ok_or_else(|| format!("route.{what}: expected [x, y]"))?;
        if a.len() != 2 {
            return Err(format!("route.{what}: expected [x, y]"));
        }
        Ok((f64_from(&a[0], what)?, f64_from(&a[1], what)?))
    };
    let start = coord(v.get("start").ok_or("route: missing \"start\"")?, "start")?;
    let end = coord(v.get("end").ok_or("route: missing \"end\"")?, "end")?;
    Ok(Route {
        start,
        end,
        width: f64_from(
            v.get("width").ok_or("route: missing \"width\"")?,
            "route.width",
        )?,
        layer: v
            .get("layer")
            .and_then(Value::as_str)
            .ok_or("route: missing \"layer\"")?
            .to_string(),
        net: v
            .get("net")
            .ok_or("route: missing \"net\"")?
            .as_str()
            .map(str::to_string),
    })
}

fn via_to_json(via: &Via) -> Result<Value, String> {
    Ok(json!({
        "position": [finite(via.position.0, "via.position")?, finite(via.position.1, "via.position")?],
        "drill": finite(via.drill, "via.drill")?,
        "width": finite(via.width, "via.width")?,
        "layers": [via.layers.0, via.layers.1],
        "net": via.net,
        "is_diff_pair": via.is_diff_pair,
    }))
}

fn via_from_json(v: &Value) -> Result<Via, String> {
    let pos = v
        .get("position")
        .and_then(Value::as_array)
        .ok_or("via: missing \"position\"")?;
    if pos.len() != 2 {
        return Err("via.position: expected [x, y]".to_string());
    }
    let layers = v
        .get("layers")
        .and_then(Value::as_array)
        .ok_or("via: missing \"layers\"")?;
    if layers.len() != 2 {
        return Err("via.layers: expected a 2-tuple shape".to_string());
    }
    Ok(Via {
        position: (
            f64_from(&pos[0], "via.position")?,
            f64_from(&pos[1], "via.position")?,
        ),
        drill: f64_from(v.get("drill").ok_or("via: missing \"drill\"")?, "via.drill")?,
        width: f64_from(v.get("width").ok_or("via: missing \"width\"")?, "via.width")?,
        layers: (
            layers[0]
                .as_str()
                .ok_or("via.layers[0]: expected a string")?
                .to_string(),
            layers[1]
                .as_str()
                .ok_or("via.layers[1]: expected a string")?
                .to_string(),
        ),
        net: v
            .get("net")
            .ok_or("via: missing \"net\"")?
            .as_str()
            .map(str::to_string),
        is_diff_pair: v
            .get("is_diff_pair")
            .and_then(Value::as_bool)
            .ok_or("via: missing \"is_diff_pair\"")?,
    })
}

fn layer_assignment_to_json(la: &LayerAssignment) -> Result<Value, String> {
    Ok(json!({
        "net_name": la.net_name,
        "layer": val_to_json(&la.layer),
        "allow_layer_change": la.allow_layer_change,
        "is_plane": la.is_plane,
    }))
}

fn layer_assignment_from_json(v: &Value) -> Result<LayerAssignment, String> {
    Ok(LayerAssignment {
        net_name: v
            .get("net_name")
            .and_then(Value::as_str)
            .ok_or("layer_assignment: missing \"net_name\"")?
            .to_string(),
        layer: val_from_json(
            v.get("layer")
                .ok_or("layer_assignment: missing \"layer\"")?,
        )?,
        allow_layer_change: v
            .get("allow_layer_change")
            .and_then(Value::as_bool)
            .ok_or("layer_assignment: missing \"allow_layer_change\"")?,
        is_plane: v
            .get("is_plane")
            .and_then(Value::as_bool)
            .ok_or("layer_assignment: missing \"is_plane\"")?,
    })
}

fn placement_to_json(p: &Placement) -> Value {
    json!({ "ref": p.ref_, "position": [p.position.0, p.position.1] })
}

fn placement_from_json(v: &Value) -> Result<Placement, String> {
    let pos = v
        .get("position")
        .and_then(Value::as_array)
        .ok_or("placement: missing \"position\"")?;
    if pos.len() != 2 {
        return Err("placement.position: expected [x, y]".to_string());
    }
    Ok(Placement {
        ref_: v
            .get("ref")
            .and_then(Value::as_str)
            .ok_or("placement: missing \"ref\"")?
            .to_string(),
        position: (
            f64_from(&pos[0], "placement.position")?,
            f64_from(&pos[1], "placement.position")?,
        ),
    })
}

fn violation_to_json(v: &Violation) -> Result<Value, String> {
    Ok(json!({
        "type": v.type_,
        "geometry_a_id": v.geometry_a_id,
        "geometry_b_id": v.geometry_b_id,
        "net_a": v.net_a,
        "net_b": v.net_b,
        "clearance_actual": finite(v.clearance_actual, "violation.clearance_actual")?,
        "clearance_required": finite(v.clearance_required, "violation.clearance_required")?,
        "location": [finite(v.location.0, "violation.location")?, finite(v.location.1, "violation.location")?],
    }))
}

fn violation_from_json(v: &Value) -> Result<Violation, String> {
    let loc = v
        .get("location")
        .and_then(Value::as_array)
        .ok_or("violation: missing \"location\"")?;
    if loc.len() != 2 {
        return Err("violation.location: expected [x, y]".to_string());
    }
    let s = |k: &str| -> Result<String, String> {
        v.get(k)
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| format!("violation: missing \"{k}\""))
    };
    let f = |k: &str| -> Result<f64, String> {
        f64_from(
            v.get(k)
                .ok_or_else(|| format!("violation: missing \"{k}\""))?,
            k,
        )
    };
    Ok(Violation {
        type_: s("type")?,
        geometry_a_id: s("geometry_a_id")?,
        geometry_b_id: s("geometry_b_id")?,
        net_a: s("net_a")?,
        net_b: s("net_b")?,
        clearance_actual: f("clearance_actual")?,
        clearance_required: f("clearance_required")?,
        location: (
            f64_from(&loc[0], "violation.location")?,
            f64_from(&loc[1], "violation.location")?,
        ),
    })
}

fn connectivity_violation_to_json(v: &ConnectivityViolation) -> Result<Value, String> {
    Ok(json!({
        "type": v.type_,
        "net": v.net,
        "location": [finite(v.location.0, "connectivity.location")?, finite(v.location.1, "connectivity.location")?],
        "description": v.description,
    }))
}

fn connectivity_violation_from_json(v: &Value) -> Result<ConnectivityViolation, String> {
    let loc = v
        .get("location")
        .and_then(Value::as_array)
        .ok_or("connectivity_violation: missing \"location\"")?;
    if loc.len() != 2 {
        return Err("connectivity_violation.location: expected [x, y]".to_string());
    }
    Ok(ConnectivityViolation {
        type_: v
            .get("type")
            .and_then(Value::as_str)
            .ok_or("connectivity_violation: missing \"type\"")?
            .to_string(),
        net: v
            .get("net")
            .and_then(Value::as_str)
            .ok_or("connectivity_violation: missing \"net\"")?
            .to_string(),
        location: (
            f64_from(&loc[0], "connectivity_violation.location")?,
            f64_from(&loc[1], "connectivity_violation.location")?,
        ),
        description: v
            .get("description")
            .and_then(Value::as_str)
            .ok_or("connectivity_violation: missing \"description\"")?
            .to_string(),
    })
}

fn placement_violation_to_json(v: &PlacementViolation) -> Result<Value, String> {
    Ok(json!({
        "constraint_name": v.constraint_name,
        "violation_type": v.violation_type,
        "message": v.message,
        "severity": v.severity,
        "component_a": v.component_a,
        "component_b": v.component_b,
        "actual_distance_mm": opt_finite(v.actual_distance_mm, "placement_violation.actual_distance_mm")?,
        "required_distance_mm": opt_finite(v.required_distance_mm, "placement_violation.required_distance_mm")?,
    }))
}

fn opt_finite(v: Option<f64>, field: &str) -> Result<Value, String> {
    match v {
        None => Ok(Value::Null),
        Some(f) => finite(f, field),
    }
}

fn placement_violation_from_json(v: &Value) -> Result<PlacementViolation, String> {
    let s = |k: &str| -> Result<String, String> {
        v.get(k)
            .and_then(Value::as_str)
            .map(str::to_string)
            .ok_or_else(|| format!("placement_violation: missing \"{k}\""))
    };
    let opt_f = |k: &str| -> Result<Option<f64>, String> {
        match v
            .get(k)
            .ok_or_else(|| format!("placement_violation: missing \"{k}\""))?
        {
            Value::Null => Ok(None),
            x => Ok(Some(f64_from(x, k)?)),
        }
    };
    Ok(PlacementViolation {
        constraint_name: s("constraint_name")?,
        violation_type: s("violation_type")?,
        message: s("message")?,
        severity: s("severity")?,
        component_a: v
            .get("component_a")
            .ok_or("placement_violation: missing \"component_a\"")?
            .as_str()
            .map(str::to_string),
        component_b: v
            .get("component_b")
            .ok_or("placement_violation: missing \"component_b\"")?
            .as_str()
            .map(str::to_string),
        actual_distance_mm: opt_f("actual_distance_mm")?,
        required_distance_mm: opt_f("required_distance_mm")?,
    })
}

// ---------------------------------------------------------------------------
// Collection helpers
// ---------------------------------------------------------------------------

/// Sets serialize as SORTED arrays: a `HashSet` iterates in salted-hash
/// order, and this repo has a standing gate against letting that order reach
/// an output (see crates/temper-cli/src/main.rs `footprints`). Sorting by the
/// JSON rendering makes the encoded form a deterministic function of the
/// values.
fn set_to_json<T, F>(set: &HashSet<T>, enc: F) -> Result<Vec<Value>, String>
where
    F: Fn(&T) -> Result<Value, String>,
{
    let mut items: Vec<Value> = Vec::with_capacity(set.len());
    for t in set {
        items.push(enc(t)?);
    }
    items.sort_by_key(|v| v.to_string());
    Ok(items)
}

// ---------------------------------------------------------------------------
// Top-level codec
// ---------------------------------------------------------------------------

/// Serialize a [`NativeBoardState`] to the subprocess JSON schema.
///
/// # Errors
///
/// A non-None opaque field that does not hold a `serde_json::Value` is a
/// fatal `StageError` naming the field (opaque values have no owned
/// representation — see the module doc for why they are not threaded
/// through JSON).
pub fn native_to_json(state: &NativeBoardState) -> Result<String, StageError> {
    let opaque_names = [
        ("board", &state.board),
        ("netlist", &state.netlist),
        ("loops", &state.loops),
        ("grid", &state.grid),
        ("drc_oracle", &state.drc_oracle),
        ("design_rules", &state.design_rules),
        ("config", &state.config),
        ("component_domain_map", &state.component_domain_map),
        ("routing_corridors", &state.routing_corridors),
        ("domain_regions", &state.domain_regions),
        ("violations", &state.violations),
        ("reclaim_by_pin_pair", &state.reclaim_by_pin_pair),
    ];
    let mut opaque = Map::new();
    for (name, field) in opaque_names {
        let Some(any) = field.as_ref() else {
            continue;
        };
        match any.downcast_ref::<Value>() {
            Some(v) => {
                opaque.insert((*name).to_string(), v.clone());
            }
            None => {
                return Err(err(
                    SER_STAGE,
                    format!(
                        "opaque field {name:?} holds a non-JSON value; opaque fields are \
                         re-bootstrapped per subprocess invocation (--pcb/--config), they are \
                         never threaded through the state JSON"
                    ),
                ));
            }
        }
    }

    let doc = json!({
        "schema": 1,
        "net_order": state.net_order,
        "opaque": Value::Object(opaque),
        "typed": {
            "drc_violations": list_opt_json(
                state.drc_violations.as_ref().map(|n| n.0.as_slice()),
                violation_to_json,
            )?,
            "connectivity_violations": list_opt_json(
                state.connectivity_violations.as_ref().map(|n| n.0.as_slice()),
                connectivity_violation_to_json,
            )?,
            "placement_violations": list_opt_json(
                state.placement_violations.as_ref().map(|n| n.0.as_slice()),
                placement_violation_to_json,
            )?,
            "placements": set_opt_json(state.placements.as_deref(), |p| Ok(placement_to_json(p)))?,
            "used_slots": slots_opt_json(state.used_slots.as_ref())?,
            "routes": set_opt_json(state.routes.as_deref(), route_to_json)?,
            "vias": set_opt_json(state.vias.as_deref(), via_to_json)?,
            "zones": set_opt_json(state.zones.as_deref(), zone_to_json)?,
            "component_zone_map": pairs_opt_json(state.component_zone_map.as_ref())?,
            "zone_slots": set_opt_json(state.zone_slots.as_deref(), zone_slots_to_json)?,
            "layer_assignments": set_opt_json(
                state.layer_assignments.as_deref(),
                layer_assignment_to_json,
            )?,
        },
    });
    serde_json::to_string(&doc)
        .map_err(|e| err(SER_STAGE, format!("serializing NativeBoardState: {e}")))
}

fn zone_slots_to_json(zs: &ZoneSlots) -> Result<Value, String> {
    let mut slots = Vec::with_capacity(zs.slots.len());
    for s in &zs.slots {
        slots.push(json!([
            finite(s.0, "zone_slots.x")?,
            finite(s.1, "zone_slots.y")?
        ]));
    }
    Ok(json!({ "zone": zs.zone, "slots": slots }))
}

fn zone_slots_from_json(v: &Value) -> Result<ZoneSlots, String> {
    let raw = v
        .get("slots")
        .and_then(Value::as_array)
        .ok_or("zone_slots: missing \"slots\"")?;
    let mut slots = Vec::with_capacity(raw.len());
    for item in raw {
        let a = item.as_array().ok_or("zone_slots slot: expected [x, y]")?;
        if a.len() != 2 {
            return Err("zone_slots slot: expected [x, y]".to_string());
        }
        slots.push(SlotPos(
            f64_from(&a[0], "zone_slots slot")?,
            f64_from(&a[1], "zone_slots slot")?,
        ));
    }
    Ok(ZoneSlots {
        zone: v
            .get("zone")
            .and_then(Value::as_str)
            .ok_or("zone_slots: missing \"zone\"")?
            .to_string(),
        slots,
    })
}

fn list_opt_json<T, F>(list: Option<&[T]>, enc: F) -> Result<Value, StageError>
where
    F: Fn(&T) -> Result<Value, String>,
{
    match list {
        None => Ok(Value::Null),
        Some(items) => {
            let mut out = Vec::with_capacity(items.len());
            for t in items {
                out.push(enc(t).map_err(|e| err(SER_STAGE, e))?);
            }
            Ok(Value::Array(out))
        }
    }
}

fn set_opt_json<T, F>(set: Option<&HashSet<T>>, enc: F) -> Result<Value, StageError>
where
    F: Fn(&T) -> Result<Value, String> + Clone,
{
    match set {
        None => Ok(Value::Null),
        Some(s) => Ok(Value::Array(
            set_to_json(s, enc).map_err(|e| err(SER_STAGE, e))?,
        )),
    }
}

fn slots_opt_json(slots: Option<&HashSet<SlotId>>) -> Result<Value, StageError> {
    match slots {
        None => Ok(Value::Null),
        Some(s) => {
            let mut items: Vec<[f64; 2]> = Vec::with_capacity(s.len());
            for slot in s {
                items.push([slot.0, slot.1]);
            }
            items.sort_by(|a, b| {
                a[0].partial_cmp(&b[0])
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then(a[1].partial_cmp(&b[1]).unwrap_or(std::cmp::Ordering::Equal))
            });
            Ok(json!(items))
        }
    }
}

fn pairs_opt_json(set: Option<&StrPairSet>) -> Result<Value, StageError> {
    match set {
        None => Ok(Value::Null),
        Some(s) => {
            let mut items: Vec<Vec<String>> =
                s.iter().map(|(a, b)| vec![a.clone(), b.clone()]).collect();
            items.sort();
            Ok(json!(items))
        }
    }
}

/// Deserialize a [`NativeBoardState`] from the subprocess JSON schema.
///
/// Fields absent from (or null within) the document deserialize to `None` /
/// empty, matching a fresh `NativeBoardState::new()`.
///
/// # Errors
///
/// Malformed JSON or an element shape that violates the schema — a LOUD
/// fatal `StageError`, never a silent default.
pub fn native_from_json(json_str: &str) -> Result<NativeBoardState, StageError> {
    let doc: Value = serde_json::from_str(json_str)
        .map_err(|e| err(SER_STAGE, format!("parsing state JSON: {e}")))?;
    let obj = doc.as_object().ok_or_else(|| {
        err(
            SER_STAGE,
            "state document: expected a JSON object".to_string(),
        )
    })?;

    let mut state = NativeBoardState::new();

    if let Some(net_order) = obj.get("net_order") {
        state.net_order = net_order
            .as_array()
            .ok_or_else(|| err(SER_STAGE, "net_order: expected an array".to_string()))?
            .iter()
            .map(|v| {
                v.as_str().map(str::to_string).ok_or_else(|| {
                    err(
                        SER_STAGE,
                        "net_order element: expected a string".to_string(),
                    )
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
    }

    if let Some(opaque) = obj.get("opaque").and_then(Value::as_object) {
        for (name, value) in opaque {
            insert_opaque(&mut state, name, value.clone())?;
        }
    }

    let typed = obj.get("typed").and_then(Value::as_object).ok_or_else(|| {
        err(
            SER_STAGE,
            "state document: missing \"typed\" object".to_string(),
        )
    })?;

    let get = |name: &str| typed.get(name).unwrap_or(&Value::Null);

    state.drc_violations = violation_list_from(get("drc_violations"))?;
    state.connectivity_violations =
        connectivity_violation_list_from(get("connectivity_violations"))?;
    state.placement_violations = placement_violation_list_from(get("placement_violations"))?;

    state.placements = set_from(get("placements"), placement_from_json)?.map(PlacementSet);
    state.used_slots = slots_from(get("used_slots"))?;
    state.routes = set_from(get("routes"), route_from_json)?.map(RouteSet);
    state.vias = set_from(get("vias"), via_from_json)?.map(ViaSet);
    state.zones = set_from(get("zones"), zone_from_json)?.map(ZoneSet);
    state.component_zone_map = pairs_from(get("component_zone_map"))?;
    state.zone_slots = set_from(get("zone_slots"), zone_slots_from_json)?.map(ZoneSlotsSet);
    state.layer_assignments =
        set_from(get("layer_assignments"), layer_assignment_from_json)?.map(LayerAssignmentSet);

    Ok(state)
}

fn insert_opaque(state: &mut NativeBoardState, name: &str, value: Value) -> Result<(), StageError> {
    let boxed: Box<dyn std::any::Any + Send + Sync> = Box::new(value);
    match name {
        "board" => state.board = Some(boxed),
        "netlist" => state.netlist = Some(boxed),
        "loops" => state.loops = Some(boxed),
        "grid" => state.grid = Some(boxed),
        "drc_oracle" => state.drc_oracle = Some(boxed),
        "design_rules" => state.design_rules = Some(boxed),
        "config" => state.config = Some(boxed),
        "component_domain_map" => state.component_domain_map = Some(boxed),
        "routing_corridors" => state.routing_corridors = Some(boxed),
        "domain_regions" => state.domain_regions = Some(boxed),
        "violations" => state.violations = Some(boxed),
        "reclaim_by_pin_pair" => state.reclaim_by_pin_pair = Some(boxed),
        other => {
            return Err(err(
                SER_STAGE,
                format!("unknown opaque field {other:?} in state document"),
            ));
        }
    }
    Ok(())
}

/// `null` → `None` (the pre-population Python default); an array → the owned
/// list newtype (order-preserving — the tuple order is load-bearing).
fn violation_list_from(v: &Value) -> Result<Option<ViolationList>, StageError> {
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "drc_violations: expected an array or null".to_string(),
        )
    })?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        out.push(violation_from_json(item).map_err(|e| err(SER_STAGE, e))?);
    }
    Ok(Some(ViolationList(out)))
}

fn connectivity_violation_list_from(
    v: &Value,
) -> Result<Option<ConnectivityViolationList>, StageError> {
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "connectivity_violations: expected an array or null".to_string(),
        )
    })?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        out.push(connectivity_violation_from_json(item).map_err(|e| err(SER_STAGE, e))?);
    }
    Ok(Some(ConnectivityViolationList(out)))
}

fn placement_violation_list_from(v: &Value) -> Result<Option<PlacementViolationList>, StageError> {
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "placement_violations: expected an array or null".to_string(),
        )
    })?;
    let mut out = Vec::with_capacity(arr.len());
    for item in arr {
        out.push(placement_violation_from_json(item).map_err(|e| err(SER_STAGE, e))?);
    }
    Ok(Some(PlacementViolationList(out)))
}

/// `null` → `None`; an array → the owned set newtype.
fn set_from<T, F>(v: &Value, dec: F) -> Result<Option<HashSet<T>>, StageError>
where
    F: Fn(&Value) -> Result<T, String>,
    T: Eq + std::hash::Hash,
{
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "collection field: expected an array or null".to_string(),
        )
    })?;
    let mut set = HashSet::with_capacity(arr.len());
    for item in arr {
        set.insert(dec(item).map_err(|e| err(SER_STAGE, e))?);
    }
    Ok(Some(set))
}

fn slots_from(v: &Value) -> Result<Option<HashSet<SlotId>>, StageError> {
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "used_slots: expected an array or null".to_string(),
        )
    })?;
    let mut set = HashSet::with_capacity(arr.len());
    for item in arr {
        let pair = item
            .as_array()
            .ok_or_else(|| err(SER_STAGE, "used_slots element: expected [x, y]".to_string()))?;
        if pair.len() != 2 {
            return Err(err(
                SER_STAGE,
                "used_slots element: expected [x, y]".to_string(),
            ));
        }
        set.insert(SlotId(
            f64_from(&pair[0], "used_slots.x").map_err(|e| err(SER_STAGE, e))?,
            f64_from(&pair[1], "used_slots.y").map_err(|e| err(SER_STAGE, e))?,
        ));
    }
    Ok(Some(set))
}

fn pairs_from(v: &Value) -> Result<Option<StrPairSet>, StageError> {
    if v.is_null() {
        return Ok(None);
    }
    let arr = v.as_array().ok_or_else(|| {
        err(
            SER_STAGE,
            "component_zone_map: expected an array or null".to_string(),
        )
    })?;
    let mut set = HashSet::with_capacity(arr.len());
    for item in arr {
        let pair = item.as_array().ok_or_else(|| {
            err(
                SER_STAGE,
                "component_zone_map element: expected [ref, zone]".to_string(),
            )
        })?;
        if pair.len() != 2 {
            return Err(err(
                SER_STAGE,
                "component_zone_map element: expected [ref, zone]".to_string(),
            ));
        }
        let s = |i: usize| -> Result<String, StageError> {
            pair[i].as_str().map(str::to_string).ok_or_else(|| {
                err(
                    SER_STAGE,
                    "component_zone_map element: expected strings".to_string(),
                )
            })
        };
        set.insert((s(0)?, s(1)?));
    }
    Ok(Some(StrPairSet(set)))
}

// ---------------------------------------------------------------------------
// Tests — the JSON round-trip gate (pure Rust, no interpreter)
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// Build a state with every owned field populated — the maximal
    /// round-trip fixture.
    fn full_state() -> NativeBoardState {
        let mut s = NativeBoardState::new();
        s.net_order = vec!["Net_A".into(), "GND".into()];
        s.drc_violations = Some(ViolationList(vec![Violation {
            type_: "clearance".into(),
            geometry_a_id: "t1".into(),
            geometry_b_id: "t2".into(),
            net_a: "Net_A".into(),
            net_b: "GND".into(),
            clearance_actual: 0.15,
            clearance_required: 0.2,
            location: (1.0, 2.5),
        }]));
        s.connectivity_violations = Some(ConnectivityViolationList(vec![ConnectivityViolation {
            type_: "open".into(),
            net: "Net_B".into(),
            location: (3.0, 4.0),
            description: "unrouted".into(),
        }]));
        s.placement_violations = Some(PlacementViolationList(vec![PlacementViolation {
            constraint_name: "signal_hv".into(),
            violation_type: "proximity".into(),
            message: "too close".into(),
            severity: "error".into(),
            component_a: Some("R1".into()),
            component_b: None,
            actual_distance_mm: None,
            required_distance_mm: Some(2.0),
        }]));
        let mut placements = HashSet::new();
        placements.insert(Placement {
            ref_: "U1".into(),
            position: (10.5, -20.25),
        });
        placements.insert(Placement {
            ref_: "R1".into(),
            position: (0.0, 5.0),
        });
        s.placements = Some(PlacementSet(placements));
        let mut slots = HashSet::new();
        slots.insert(SlotId(-0.0, 5.0));
        slots.insert(SlotId(1.5, 2.5));
        s.used_slots = Some(slots);
        let mut routes = HashSet::new();
        routes.insert(Route {
            start: (0.0, 0.0),
            end: (1.0, 1.0),
            width: 0.2,
            layer: "F.Cu".into(),
            net: Some("Net_A".into()),
        });
        s.routes = Some(RouteSet(routes));
        let mut vias = HashSet::new();
        vias.insert(Via {
            position: (2.0, 3.0),
            drill: 0.3,
            width: 0.6,
            layers: ("F.Cu".into(), "B.Cu".into()),
            net: None,
            is_diff_pair: false,
        });
        s.vias = Some(ViaSet(vias));
        let mut zones = HashSet::new();
        zones.insert(Zone {
            name: "HV_edge".into(),
            bounds: (
                (Val::Int(0), Val::Int(0)),
                (Val::Float(40.0), Val::Float(30.0)),
            ),
        });
        s.zones = Some(ZoneSet(zones));
        let mut pairs = HashSet::new();
        pairs.insert(("U1".to_string(), "HV_edge".to_string()));
        s.component_zone_map = Some(StrPairSet(pairs));
        let mut zone_slots = HashSet::new();
        zone_slots.insert(ZoneSlots {
            zone: "HV_edge".into(),
            slots: vec![SlotPos(1.0, 1.0), SlotPos(2.0, 2.0)],
        });
        s.zone_slots = Some(ZoneSlotsSet(zone_slots));
        let mut las = HashSet::new();
        las.insert(LayerAssignment {
            net_name: "Net_A".into(),
            layer: Val::Int(2),
            allow_layer_change: true,
            is_plane: false,
        });
        s.layer_assignments = Some(LayerAssignmentSet(las));
        s
    }

    #[cfg_attr(test, test)]
    fn empty_state_round_trips() {
        let s = NativeBoardState::new();
        let json = native_to_json(&s).unwrap();
        let back = native_from_json(&json).unwrap();
        assert_eq!(back.net_order, Vec::<String>::new());
        assert!(back.placements.is_none());
        assert!(back.used_slots.is_none());
        assert!(back.zones.is_none());
        assert!(back.drc_violations.is_none());
    }

    #[cfg_attr(test, test)]
    fn full_state_round_trips_field_for_field() {
        let s = full_state();
        let json = native_to_json(&s).unwrap();
        let back = native_from_json(&json).unwrap();
        assert_eq!(back.net_order, s.net_order);
        assert_eq!(back.drc_violations, s.drc_violations);
        assert_eq!(back.connectivity_violations, s.connectivity_violations);
        assert_eq!(back.placement_violations, s.placement_violations);
        assert_eq!(back.placements, s.placements);
        // -0.0 normalizes to 0.0 in SlotId equality (Python set semantics).
        assert_eq!(back.used_slots, s.used_slots);
        assert_eq!(back.routes, s.routes);
        assert_eq!(back.vias, s.vias);
        assert_eq!(back.zones, s.zones);
        assert_eq!(back.component_zone_map, s.component_zone_map);
        assert_eq!(back.zone_slots, s.zone_slots);
        assert_eq!(back.layer_assignments, s.layer_assignments);
    }

    #[cfg_attr(test, test)]
    fn double_round_trip_is_stable() {
        let s = full_state();
        let once = native_from_json(&native_to_json(&s).unwrap()).unwrap();
        let twice = native_from_json(&native_to_json(&once).unwrap()).unwrap();
        let j1 = native_to_json(&once).unwrap();
        let j2 = native_to_json(&twice).unwrap();
        assert_eq!(j1, j2, "the encoding must be a fixed point after one pass");
    }

    #[cfg_attr(test, test)]
    fn val_int_and_float_do_not_merge() {
        let mut s = NativeBoardState::new();
        let mut zones = HashSet::new();
        zones.insert(Zone {
            name: "z".into(),
            bounds: (
                (Val::Int(0), Val::Float(0.0)),
                (Val::Int(1), Val::Float(1.0)),
            ),
        });
        s.zones = Some(ZoneSet(zones));
        let json = native_to_json(&s).unwrap();
        assert!(json.contains("\"int\":0") && json.contains("\"float\":0.0"));
        let back = native_from_json(&json).unwrap();
        match back.zones.unwrap().iter().next().unwrap().bounds {
            ((Val::Int(a), Val::Float(b)), _) => {
                assert_eq!(a, 0);
                assert_eq!(b, 0.0);
            }
            _ => panic!("Val tags lost across the round trip"),
        }
    }

    #[cfg_attr(test, test)]
    fn non_value_opaque_is_a_loud_error() {
        let mut s = NativeBoardState::new();
        s.board = Some(Box::new(42_u32));
        let e = native_to_json(&s).unwrap_err();
        assert!(e.message.contains("board"), "error must name the field");
    }

    #[cfg_attr(test, test)]
    fn value_opaque_passes_through() {
        let mut s = NativeBoardState::new();
        s.config = Some(Box::new(
            json!({ "placer": { "use_isolation_slots": true } }),
        ));
        let back = native_from_json(&native_to_json(&s).unwrap()).unwrap();
        let cfg = back
            .config
            .as_ref()
            .unwrap()
            .downcast_ref::<Value>()
            .unwrap();
        assert_eq!(
            cfg.get("placer")
                .unwrap()
                .get("use_isolation_slots")
                .unwrap(),
            &json!(true)
        );
    }

    #[cfg_attr(test, test)]
    fn malformed_json_is_a_loud_error() {
        let e = native_from_json("{not json").unwrap_err();
        assert_eq!(e.kind, StageErrorKind::Fatal);
        let e = native_from_json("{\"typed\": null}").unwrap_err();
        assert!(e.message.contains("typed"));
        let e = native_from_json("{\"typed\": {\"used_slots\": [[\"a\"]]}}").unwrap_err();
        assert!(e.message.contains("used_slots"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "state_ser::tests::empty_state_round_trips",
            empty_state_round_trips,
        ),
        (
            "state_ser::tests::full_state_round_trips_field_for_field",
            full_state_round_trips_field_for_field,
        ),
        (
            "state_ser::tests::double_round_trip_is_stable",
            double_round_trip_is_stable,
        ),
        (
            "state_ser::tests::val_int_and_float_do_not_merge",
            val_int_and_float_do_not_merge,
        ),
        (
            "state_ser::tests::non_value_opaque_is_a_loud_error",
            non_value_opaque_is_a_loud_error,
        ),
        (
            "state_ser::tests::value_opaque_passes_through",
            value_opaque_passes_through,
        ),
        (
            "state_ser::tests::malformed_json_is_a_loud_error",
            malformed_json_is_a_loud_error,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

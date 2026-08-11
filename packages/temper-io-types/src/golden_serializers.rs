// golden_serializers: serialize_boardstate_to_dsn, serialize_boardstate_to_ses,
// serialize_violations_to_json, serialize_connectivity_to_json.
//
// `serialize_boardstate_to_ses`, `serialize_violations_to_json` and
// `serialize_connectivity_to_json` are split into a pure core (operating on
// plain Rust structs, using `serde_json` in place of `py.import("json")`)
// plus a thin pyo3 boundary that walks the duck-typed `BoardState` /
// `Violation` Python objects into those structs.
//
// `serialize_boardstate_to_dsn` is different in kind: it does not merely
// read fields off a Python object, it calls back into a *real* Python
// class (`temper_placer.io.dsn_exporter.DSNExporter`) that implements the
// DSN export algorithm itself. Making that pure would mean re-implementing
// `DSNExporter` in Rust, which is out of scope here — it stays entirely
// behind the `python` feature and is not exported on wasm32. (Nothing in
// the Python codebase actually imports the Rust `DSNExpression`/`DSNRect`/
// `DSNCircle`/`DSNPath` types either — `temper_placer/io/dsn.py` has its
// own pure-Python implementation that `dsn_exporter.py` uses instead.)

#[cfg(feature = "python")]
use pyo3::prelude::*;

pub const CURRENT_FORMAT_VERSION: i64 = 1;

/// Format a float the way the Python golden serializers historically did:
/// fixed 6 decimal places. Used by the DSN/SES text serializers (not the
/// JSON ones, which round instead — see [`round6`]).
pub fn format_float(val: f64) -> String {
    format!("{:.6}", val)
}

/// Round to 6 decimal places, matching the Python
/// `round(val, 6)`-via-multiply idiom used before violations are embedded
/// in JSON.
pub fn round6(val: f64) -> f64 {
    (val * 1_000_000.0).round() / 1_000_000.0
}

// ---------------------------------------------------------------------------
// SES serialization
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub struct RouteEntry {
    pub net_name: String,
    pub layer: i64,
    pub start: (f64, f64),
    pub end: (f64, f64),
    pub width: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ViaEntry {
    pub net_name: String,
    pub center: (f64, f64),
}

/// Pure core of `serialize_boardstate_to_ses`.
pub fn serialize_ses(routes: &[RouteEntry], vias: &[ViaEntry]) -> String {
    let mut route_entries: Vec<(String, (String, i64))> = routes
        .iter()
        .map(|r| {
            let line = format!(
                "(wire {} (path {} {} {} {} {} {}))",
                r.net_name,
                r.layer,
                format_float(r.width),
                format_float(r.start.0),
                format_float(r.start.1),
                format_float(r.end.0),
                format_float(r.end.1),
            );
            (line, (r.net_name.clone(), r.layer))
        })
        .collect();

    route_entries.sort_by(|a, b| a.1.cmp(&b.1));
    let mut route_lines: Vec<String> = route_entries.into_iter().map(|(line, _)| line).collect();
    route_lines.sort();

    let mut via_lines: Vec<String> = vias
        .iter()
        .map(|v| {
            format!(
                "(via {} {} {})",
                v.net_name,
                format_float(v.center.0),
                format_float(v.center.1),
            )
        })
        .collect();
    via_lines.sort();

    let mut result = String::from("(session\n(resolution um 10)\n(unit mm)\n\n");

    if route_lines.is_empty() {
        result.push_str("(routes)\n)");
        return result;
    }

    result.push_str("(routes)\n");
    for rl in &route_lines {
        result.push_str(rl);
        result.push('\n');
    }

    if !via_lines.is_empty() {
        result.push_str("(vias)\n");
        for vl in &via_lines {
            result.push_str(vl);
            result.push('\n');
        }
    }

    result.push(')');
    result
}

// ---------------------------------------------------------------------------
// Violations / connectivity JSON serialization
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq)]
pub struct ViolationEntry {
    pub vtype: String,
    pub net_a: String,
    pub net_b: String,
    pub geometry_a_id: String,
    pub geometry_b_id: String,
    pub clearance_actual: f64,
    pub clearance_required: f64,
    pub location: Option<(f64, f64)>,
    pub severity: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ConnectivityEntry {
    pub vtype: String,
    pub net: String,
    pub description: String,
    pub location: Option<(f64, f64)>,
}

fn location_json(loc: Option<(f64, f64)>) -> serde_json::Value {
    match loc {
        Some((x, y)) => serde_json::json!({ "x": round6(x), "y": round6(y) }),
        None => serde_json::Value::Null,
    }
}

/// Pretty-print a `serde_json::Value` the same way Python's
/// `json.dumps(obj, indent=2, sort_keys=True)` does. `serde_json::Value`'s
/// `Map` is a `BTreeMap` by default (the `preserve_order` feature is not
/// enabled anywhere in this workspace), so keys already come out sorted;
/// `to_string_pretty`'s 2-space indent and separator choices match
/// Python's `indent=2` output byte-for-byte (see crate tests).
fn to_python_style_json(value: &serde_json::Value) -> Result<String, serde_json::Error> {
    serde_json::to_string_pretty(value)
}

/// Pure core of `serialize_violations_to_json`.
pub fn serialize_violations_json(
    format_version: i64,
    entries: &[ViolationEntry],
) -> Result<String, serde_json::Error> {
    let mut sorted: Vec<&ViolationEntry> = entries.iter().collect();
    sorted.sort_by(|a, b| {
        let ka = (a.net_a.as_str(), a.net_b.as_str(), a.vtype.as_str());
        let kb = (b.net_a.as_str(), b.net_b.as_str(), b.vtype.as_str());
        let key_a = format!("{}|{}|{}", ka.0, ka.1, ka.2);
        let key_b = format!("{}|{}|{}", kb.0, kb.1, kb.2);
        key_a.cmp(&key_b)
    });

    let violations: Vec<serde_json::Value> = sorted
        .into_iter()
        .map(|v| {
            serde_json::json!({
                "type": v.vtype,
                "net_a": v.net_a,
                "net_b": v.net_b,
                "geometry_a_id": v.geometry_a_id,
                "geometry_b_id": v.geometry_b_id,
                "clearance_actual": round6(v.clearance_actual),
                "clearance_required": round6(v.clearance_required),
                "location": location_json(v.location),
                "severity": round6(v.severity),
            })
        })
        .collect();

    let outer = serde_json::json!({
        "format_version": format_version,
        "violations": violations,
    });

    to_python_style_json(&outer)
}

/// Pure core of `serialize_connectivity_to_json`.
pub fn serialize_connectivity_json(
    format_version: i64,
    entries: &[ConnectivityEntry],
) -> Result<String, serde_json::Error> {
    let mut sorted: Vec<&ConnectivityEntry> = entries.iter().collect();
    sorted.sort_by(|a, b| {
        let key_a = format!("{}|{}", a.net, a.vtype);
        let key_b = format!("{}|{}", b.net, b.vtype);
        key_a.cmp(&key_b)
    });

    let violations: Vec<serde_json::Value> = sorted
        .into_iter()
        .map(|v| {
            serde_json::json!({
                "type": v.vtype,
                "net": v.net,
                "description": v.description,
                "location": location_json(v.location),
            })
        })
        .collect();

    let outer = serde_json::json!({
        "format_version": format_version,
        "violations": violations,
    });

    to_python_style_json(&outer)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;

    fn get_attr_str(obj: &Bound<'_, PyAny>, name: &str, default: &str) -> String {
        obj.getattr(name)
            .ok()
            .and_then(|v| v.extract::<String>().ok())
            .unwrap_or_else(|| default.to_string())
    }

    fn get_attr_f64(obj: &Bound<'_, PyAny>, name: &str, default: f64) -> f64 {
        obj.getattr(name)
            .ok()
            .and_then(|v| v.extract::<f64>().ok())
            .unwrap_or(default)
    }

    fn get_attr_i64(obj: &Bound<'_, PyAny>, name: &str, default: i64) -> i64 {
        obj.getattr(name)
            .ok()
            .and_then(|v| v.extract::<i64>().ok())
            .unwrap_or(default)
    }

    fn get_attr_tuple(obj: &Bound<'_, PyAny>, name: &str, default: (f64, f64)) -> (f64, f64) {
        obj.getattr(name)
            .ok()
            .and_then(|v| v.extract::<(f64, f64)>().ok())
            .unwrap_or(default)
    }

    fn get_attr_str_or(v: &Bound<'_, PyAny>, name: &str) -> String {
        get_attr_str(v, name, "")
    }

    fn get_attr_f64_or(v: &Bound<'_, PyAny>, name: &str) -> f64 {
        get_attr_f64(v, name, 0.0)
    }

    fn maybe_loc(v: &Bound<'_, PyAny>) -> Option<(f64, f64)> {
        let loc = v.getattr("location").ok()?;
        if loc.is_none() {
            return None;
        }
        let x = loc
            .getattr("x")
            .ok()
            .and_then(|v| v.extract::<f64>().ok())
            .unwrap_or(0.0);
        let y = loc
            .getattr("y")
            .ok()
            .and_then(|v| v.extract::<f64>().ok())
            .unwrap_or(0.0);
        Some((x, y))
    }

    fn get_iterable_or_empty<'py>(
        py: Python<'py>,
        state: &Bound<'py, PyAny>,
        attr: &str,
    ) -> PyResult<Bound<'py, PyAny>> {
        if let Ok(v) = state.getattr(attr)
            && !v.is_none()
        {
            return Ok(v);
        }
        py.eval(c"()", None, None)
    }

    #[pyfunction]
    pub fn serialize_boardstate_to_ses(
        py: Python<'_>,
        state: Bound<'_, PyAny>,
    ) -> PyResult<String> {
        let routes = get_iterable_or_empty(py, &state, "routes")?;
        let vias = get_iterable_or_empty(py, &state, "vias")?;

        let mut route_entries: Vec<RouteEntry> = Vec::new();
        for item in routes.try_iter()? {
            let route = item?;
            route_entries.push(RouteEntry {
                net_name: get_attr_str(&route, "net_name", "unnamed"),
                layer: get_attr_i64(&route, "layer", 0),
                start: get_attr_tuple(&route, "start", (0.0, 0.0)),
                end: get_attr_tuple(&route, "end", (0.0, 0.0)),
                width: get_attr_f64(&route, "width", 0.25),
            });
        }

        let mut via_entries: Vec<ViaEntry> = Vec::new();
        for item in vias.try_iter()? {
            let via = item?;
            via_entries.push(ViaEntry {
                net_name: get_attr_str(&via, "net_name", "unnamed"),
                center: get_attr_tuple(&via, "center", (0.0, 0.0)),
            });
        }

        Ok(serialize_ses(&route_entries, &via_entries))
    }

    #[pyfunction]
    pub fn serialize_violations_to_json(
        py: Python<'_>,
        state: Bound<'_, PyAny>,
    ) -> PyResult<String> {
        let violations = get_iterable_or_empty(py, &state, "drc_violations")?;

        let mut entries: Vec<ViolationEntry> = Vec::new();
        for item in violations.try_iter()? {
            let v = item?;
            entries.push(ViolationEntry {
                vtype: get_attr_str_or(&v, "type"),
                net_a: get_attr_str_or(&v, "net_a"),
                net_b: get_attr_str_or(&v, "net_b"),
                geometry_a_id: get_attr_str_or(&v, "geometry_a_id"),
                geometry_b_id: get_attr_str_or(&v, "geometry_b_id"),
                clearance_actual: get_attr_f64_or(&v, "clearance_actual"),
                clearance_required: get_attr_f64_or(&v, "clearance_required"),
                location: maybe_loc(&v),
                severity: get_attr_f64_or(&v, "severity"),
            });
        }

        serialize_violations_json(CURRENT_FORMAT_VERSION, &entries)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
    }

    #[pyfunction]
    pub fn serialize_connectivity_to_json(
        py: Python<'_>,
        state: Bound<'_, PyAny>,
    ) -> PyResult<String> {
        let violations = get_iterable_or_empty(py, &state, "connectivity_violations")?;

        let mut entries: Vec<ConnectivityEntry> = Vec::new();
        for item in violations.try_iter()? {
            let v = item?;
            entries.push(ConnectivityEntry {
                vtype: get_attr_str_or(&v, "type"),
                net: get_attr_str_or(&v, "net"),
                description: get_attr_str_or(&v, "description"),
                location: maybe_loc(&v),
            });
        }

        serialize_connectivity_json(CURRENT_FORMAT_VERSION, &entries)
            .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))
    }

    #[pyfunction]
    pub fn serialize_boardstate_to_dsn(
        py: Python<'_>,
        state: Bound<'_, PyAny>,
    ) -> PyResult<String> {
        let board = state.getattr("board")?;
        if board.is_none() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "BoardState.board is None; cannot serialize to DSN",
            ));
        }
        let netlist = state.getattr("netlist")?;
        if netlist.is_none() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "BoardState.netlist is None; cannot serialize to DSN",
            ));
        }

        let dsn_mod = py.import("temper_placer.io.dsn_exporter")?;
        let dsn_exporter_class = dsn_mod.getattr("DSNExporter")?;

        let kwargs = pyo3::types::PyDict::new(py);
        kwargs.set_item("board", board)?;
        kwargs.set_item("netlist", netlist)?;
        let exporter = dsn_exporter_class.call((), Some(&kwargs))?;

        let dsn_expr = exporter.call_method1("export_pcb", ("temper",))?;
        let result: String = dsn_expr.str()?.extract()?;
        Ok(result)
    }
}

#[cfg(feature = "python")]
pub use py_bridge::{
    serialize_boardstate_to_dsn, serialize_boardstate_to_ses, serialize_connectivity_to_json,
    serialize_violations_to_json,
};

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn format_float_matches_python_format_spec() {
        assert_eq!(format_float(1.5), "1.500000");
        assert_eq!(format_float(0.0), "0.000000");
        assert_eq!(format_float(-2.25), "-2.250000");
    }

    #[cfg_attr(test, test)]
    fn round6_rounds_to_six_decimals() {
        assert_eq!(round6(0.123456789), 0.123457);
        assert_eq!(round6(1.0), 1.0);
    }

    #[cfg_attr(test, test)]
    fn ses_empty_routes_and_vias() {
        let s = serialize_ses(&[], &[]);
        assert_eq!(s, "(session\n(resolution um 10)\n(unit mm)\n\n(routes)\n)");
    }

    #[cfg_attr(test, test)]
    fn ses_with_route_and_via() {
        let routes = vec![RouteEntry {
            net_name: "GND".into(),
            layer: 0,
            start: (0.0, 0.0),
            end: (1.0, 1.0),
            width: 0.25,
        }];
        let vias = vec![ViaEntry {
            net_name: "GND".into(),
            center: (0.5, 0.5),
        }];
        let s = serialize_ses(&routes, &vias);
        assert!(s.starts_with("(session"));
        assert!(s.contains("(routes)"));
        assert!(s.contains("(wire GND (path 0 0.250000 0.000000 0.000000 1.000000 1.000000))"));
        assert!(s.contains("(vias)"));
        assert!(s.contains("(via GND 0.500000 0.500000)"));
    }

    #[cfg_attr(test, test)]
    fn violations_json_matches_python_json_dumps_shape() {
        // This exact string was independently produced by CPython's
        // `json.dumps(obj, indent=2, sort_keys=True)` on the equivalent
        // dict (see PR description / task notes) — asserting against it
        // byte-for-byte is the differential check for this migration.
        let entries = vec![ViolationEntry {
            vtype: "CLR".into(),
            net_a: "N1".into(),
            net_b: "N2".into(),
            geometry_a_id: "g1".into(),
            geometry_b_id: "g2".into(),
            clearance_actual: 0.1,
            clearance_required: 0.2,
            location: Some((1.5, -2.25)),
            severity: 3.0,
        }];
        let json = serialize_violations_json(1, &entries).expect("serializes");
        let expected = "{\n  \"format_version\": 1,\n  \"violations\": [\n    {\n      \"clearance_actual\": 0.1,\n      \"clearance_required\": 0.2,\n      \"geometry_a_id\": \"g1\",\n      \"geometry_b_id\": \"g2\",\n      \"location\": {\n        \"x\": 1.5,\n        \"y\": -2.25\n      },\n      \"net_a\": \"N1\",\n      \"net_b\": \"N2\",\n      \"severity\": 3.0,\n      \"type\": \"CLR\"\n    }\n  ]\n}";
        assert_eq!(json, expected);
    }

    #[cfg_attr(test, test)]
    fn violations_json_empty() {
        let json = serialize_violations_json(1, &[]).expect("serializes");
        assert_eq!(json, "{\n  \"format_version\": 1,\n  \"violations\": []\n}");
    }

    #[cfg_attr(test, test)]
    fn violations_json_sorted_keys_and_order() {
        let entries = vec![
            ViolationEntry {
                vtype: "CLR".into(),
                net_a: "B".into(),
                net_b: "A".into(),
                geometry_a_id: String::new(),
                geometry_b_id: String::new(),
                clearance_actual: 0.0,
                clearance_required: 0.0,
                location: None,
                severity: 0.0,
            },
            ViolationEntry {
                vtype: "CLR".into(),
                net_a: "A".into(),
                net_b: "B".into(),
                geometry_a_id: String::new(),
                geometry_b_id: String::new(),
                clearance_actual: 0.0,
                clearance_required: 0.0,
                location: None,
                severity: 0.0,
            },
        ];
        let json = serialize_violations_json(1, &entries).expect("serializes");
        let a_idx = json.find("\"net_a\": \"A\"").expect("A entry present");
        let b_idx = json.find("\"net_a\": \"B\"").expect("B entry present");
        assert!(a_idx < b_idx, "entries must sort by net_a|net_b|type");
    }

    #[cfg_attr(test, test)]
    fn connectivity_json_empty() {
        let json = serialize_connectivity_json(1, &[]).expect("serializes");
        assert_eq!(json, "{\n  \"format_version\": 1,\n  \"violations\": []\n}");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("golden_serializers::tests::format_float_matches_python_format_spec", format_float_matches_python_format_spec),
        ("golden_serializers::tests::round6_rounds_to_six_decimals", round6_rounds_to_six_decimals),
        ("golden_serializers::tests::ses_empty_routes_and_vias", ses_empty_routes_and_vias),
        ("golden_serializers::tests::ses_with_route_and_via", ses_with_route_and_via),
        ("golden_serializers::tests::violations_json_matches_python_json_dumps_shape", violations_json_matches_python_json_dumps_shape),
        ("golden_serializers::tests::violations_json_empty", violations_json_empty),
        ("golden_serializers::tests::violations_json_sorted_keys_and_order", violations_json_sorted_keys_and_order),
        ("golden_serializers::tests::connectivity_json_empty", connectivity_json_empty),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

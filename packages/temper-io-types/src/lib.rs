use pyo3::create_exception;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

create_exception!(temper_io_types, FootprintParseError, pyo3::exceptions::PyException);

// ---------------------------------------------------------------------------
// export_types: TraceSegment
// ---------------------------------------------------------------------------

#[pyclass(from_py_object)]
#[derive(Clone)]
struct TraceSegment {
    #[pyo3(get, set)]
    net: String,
    #[pyo3(get, set)]
    start: (f64, f64),
    #[pyo3(get, set)]
    end: (f64, f64),
    #[pyo3(get, set)]
    width: f64,
    #[pyo3(get, set)]
    layer: String,
}

#[pymethods]
impl TraceSegment {
    #[new]
    fn new(
        net: String,
        start: (f64, f64),
        end: (f64, f64),
        width: f64,
        layer: String,
    ) -> Self {
        TraceSegment {
            net,
            start,
            end,
            width,
            layer,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "TraceSegment(net={:?}, start={:?}, end={:?}, width={}, layer={:?})",
            self.net, self.start, self.end, self.width, self.layer
        )
    }
}

// ---------------------------------------------------------------------------
// export_types: TraceVia
// ---------------------------------------------------------------------------

#[pyclass(from_py_object)]
#[derive(Clone)]
struct TraceVia {
    #[pyo3(get, set)]
    net: String,
    #[pyo3(get, set)]
    position: (f64, f64),
    #[pyo3(get, set)]
    size: f64,
    #[pyo3(get, set)]
    drill: f64,
    #[pyo3(get, set)]
    layers: Vec<String>,
}

#[pymethods]
impl TraceVia {
    #[new]
    fn new(
        net: String,
        position: (f64, f64),
        size: f64,
        drill: f64,
        layers: Vec<String>,
    ) -> Self {
        TraceVia {
            net,
            position,
            size,
            drill,
            layers,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "TraceVia(net={:?}, position={:?}, size={}, drill={}, layers={:?})",
            self.net, self.position, self.size, self.drill, self.layers
        )
    }
}

// ---------------------------------------------------------------------------
// export_types: ExportResult
// ---------------------------------------------------------------------------

#[pyclass]
struct ExportResult {
    #[pyo3(get, set)]
    output_path: PathBuf,
    #[pyo3(get, set)]
    segments_added: usize,
    #[pyo3(get, set)]
    vias_added: usize,
    #[pyo3(get, set)]
    nets_exported: usize,
    #[pyo3(get, set)]
    nets_failed: usize,
    #[pyo3(get, set)]
    warnings: Vec<String>,
}

#[pymethods]
impl ExportResult {
    #[new]
    fn new(
        output_path: PathBuf,
        segments_added: usize,
        vias_added: usize,
        nets_exported: usize,
        nets_failed: usize,
        warnings: Vec<String>,
    ) -> Self {
        ExportResult {
            output_path,
            segments_added,
            vias_added,
            nets_exported,
            nets_failed,
            warnings,
        }
    }

    fn __str__(&self) -> String {
        format!(
            "Export complete: {} nets, {} segments, {} vias -> {}",
            self.nets_exported,
            self.segments_added,
            self.vias_added,
            self.output_path.display(),
        )
    }

    fn __repr__(&self) -> String {
        self.__str__()
    }
}

// ---------------------------------------------------------------------------
// footprint_parser: FootprintBounds
// ---------------------------------------------------------------------------

#[pyclass(from_py_object)]
#[derive(Clone)]
struct FootprintBounds {
    #[pyo3(get, set)]
    width: f64,
    #[pyo3(get, set)]
    height: f64,
    #[pyo3(get, set)]
    center_offset: (f64, f64),
}

#[pymethods]
impl FootprintBounds {
    #[new]
    #[pyo3(signature = (width, height, center_offset = (0.0, 0.0)))]
    fn new(width: f64, height: f64, center_offset: (f64, f64)) -> Self {
        FootprintBounds {
            width,
            height,
            center_offset,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "FootprintBounds(width={}, height={}, center_offset={:?})",
            self.width, self.height, self.center_offset
        )
    }
}

// ---------------------------------------------------------------------------
// footprint_parser: parse_footprint_courtyard
// ---------------------------------------------------------------------------

#[pyfunction]
fn parse_footprint_courtyard(py: Python<'_>, path: PathBuf) -> PyResult<FootprintBounds> {
    let pathlib = py.import("pathlib")?;
    let path_class = pathlib.getattr("Path")?;
    let path_obj = path_class.call1((path,))?;

    let exists: bool = path_obj.call_method0("exists")?.extract()?;
    if !exists {
        let path_str: String = path_obj.str()?.extract()?;
        return Err(pyo3::exceptions::PyFileNotFoundError::new_err(format!(
            "Footprint file not found: {}",
            path_str
        )));
    }

    let content: String = path_obj
        .call_method0("read_text")?
        .extract()
        .map_err(        |e| {
            let path_str: String = path_obj.str().and_then(|s| s.extract()).unwrap_or_else(|_| "?".to_string());
            FootprintParseError::new_err(format!(
                "Error reading {}: {}",
                path_str, e
            ))
        })?;

    let re_mod = py.import("re")?;

    let fp_line_pattern = re_mod.call_method1(
        "compile",
        (concat!(
            r"(?m)\(fp_line\s+",
            r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r#"\(layer\s+"([FB]\.CrtYd)"\)"#
        ),),
    )?;

    let fp_rect_pattern = re_mod.call_method1(
        "compile",
        (concat!(
            r"(?m)\(fp_rect\s+",
            r"\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r"\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+",
            r#"\(layer\s+"([FB]\.CrtYd)"\)"#
        ),),
    )?;

    let mut x_coords: Vec<f64> = Vec::new();
    let mut y_coords: Vec<f64> = Vec::new();

    // Parse fp_line elements
    for m in fp_line_pattern
        .call_method1("finditer", (content.as_str(),))?
        .try_iter()?
    {
        let m = m?;
        let groups: Vec<String> = m.call_method0("groups")?.extract()?;
        let x1: f64 = groups[0].parse().unwrap_or(0.0);
        let y1: f64 = groups[1].parse().unwrap_or(0.0);
        let x2: f64 = groups[2].parse().unwrap_or(0.0);
        let y2: f64 = groups[3].parse().unwrap_or(0.0);
        x_coords.push(x1);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y2);
    }

    // Parse fp_rect elements
    for m in fp_rect_pattern
        .call_method1("finditer", (content.as_str(),))?
        .try_iter()?
    {
        let m = m?;
        let groups: Vec<String> = m.call_method0("groups")?.extract()?;
        let x1: f64 = groups[0].parse().unwrap_or(0.0);
        let y1: f64 = groups[1].parse().unwrap_or(0.0);
        let x2: f64 = groups[2].parse().unwrap_or(0.0);
        let y2: f64 = groups[3].parse().unwrap_or(0.0);
        x_coords.push(x1);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y1);
        x_coords.push(x2);
        y_coords.push(y2);
        x_coords.push(x1);
        y_coords.push(y2);
    }

    if x_coords.is_empty() {
        let path_str: String = path_obj.str()?.extract()?;
        return Err(FootprintParseError::new_err(format!(
            "No courtyard (F.CrtYd or B.CrtYd) found in {}. \
             Footprint must have courtyard lines to extract bounds.",
            path_str
        )));
    }

    let min_x = x_coords.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_x = x_coords.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_y = y_coords.iter().cloned().fold(f64::INFINITY, f64::min);
    let max_y = y_coords.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    let width = max_x - min_x;
    let height = max_y - min_y;
    let center_x = (min_x + max_x) / 2.0;
    let center_y = (min_y + max_y) / 2.0;

    Ok(FootprintBounds {
        width,
        height,
        center_offset: (center_x, center_y),
    })
}

// ---------------------------------------------------------------------------
// footprint_parser: parse_footprint_directory
// ---------------------------------------------------------------------------

#[pyfunction]
fn parse_footprint_directory(
    py: Python<'_>,
    directory: PathBuf,
) -> PyResult<HashMap<String, FootprintBounds>> {
    let pathlib = py.import("pathlib")?;
    let path_class = pathlib.getattr("Path")?;
    let dir_obj = path_class.call1((directory,))?;

    let glob_iter = dir_obj.call_method1("glob", ("*.kicad_mod",))?;
    let mut results: HashMap<String, FootprintBounds> = HashMap::new();

    for item in glob_iter.try_iter()? {
        let fp_file = item?;
        let name: String = fp_file.getattr("stem")?.extract()?;
        let path_str: String = fp_file.str()?.extract()?;
        let path = PathBuf::from(&path_str);
        match parse_footprint_courtyard(py, path) {
            Ok(bounds) => {
                results.insert(name, bounds);
            }
            Err(_) => {
                continue;
            }
        }
    }

    Ok(results)
}

// ---------------------------------------------------------------------------
// isolation_slot_geometry: isolation_slot_aabb
// ---------------------------------------------------------------------------

#[pyfunction]
fn isolation_slot_aabb(
    slot: Bound<'_, PyAny>,
    component_xy: (f64, f64),
) -> PyResult<((f64, f64), (f64, f64))> {
    let (cx, cy) = component_xy;

    let (sx, sy): (f64, f64) = slot.getattr("start_offset")?.extract()?;
    let (ex, ey): (f64, f64) = slot.getattr("end_offset")?.extract()?;
    let width_mm: f64 = slot.getattr("width_mm")?.extract()?;

    let mut x_lo = sx.min(ex);
    let mut x_hi = sx.max(ex);
    let mut y_lo = sy.min(ey);
    let mut y_hi = sy.max(ey);

    let dx = ex - sx;
    let dy = ey - sy;
    let half_w = width_mm / 2.0;

    if dx.abs() >= dy.abs() {
        y_lo -= half_w;
        y_hi += half_w;
    } else {
        x_lo -= half_w;
        x_hi += half_w;
    }

    Ok(((cx + x_lo, cy + y_lo), (cx + x_hi, cy + y_hi)))
}

// ---------------------------------------------------------------------------
// golden_serializers: constants
// ---------------------------------------------------------------------------

const CURRENT_FORMAT_VERSION: i32 = 1;

fn format_float(val: f64) -> String {
    format!("{:.6}", val)
}

// ---------------------------------------------------------------------------
// golden_serializers: serialize_boardstate_to_dsn
// ---------------------------------------------------------------------------

#[pyfunction]
fn serialize_boardstate_to_dsn(
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

    let kwargs = PyDict::new(py);
    kwargs.set_item("board", board)?;
    kwargs.set_item("netlist", netlist)?;
    let exporter = dsn_exporter_class.call((), Some(&kwargs))?;

    let dsn_expr = exporter.call_method1("export_pcb", ("temper",))?;
    let result: String = dsn_expr.str()?.extract()?;
    Ok(result)
}

// ---------------------------------------------------------------------------
// golden_serializers: serialize_boardstate_to_ses
// ---------------------------------------------------------------------------

fn get_routes<'py>(py: Python<'py>, state: &Bound<'py, PyAny>) -> Bound<'py, PyAny> {
    if let Ok(r) = state.getattr("routes") {
        if !r.is_none() {
            return r;
        }
    }
    py.eval(c"frozenset()", None, None).unwrap().into()
}

fn get_vias<'py>(py: Python<'py>, state: &Bound<'py, PyAny>) -> Bound<'py, PyAny> {
    if let Ok(v) = state.getattr("vias") {
        if !v.is_none() {
            return v;
        }
    }
    py.eval(c"frozenset()", None, None).unwrap().into()
}

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

#[pyfunction]
fn serialize_boardstate_to_ses(
    py: Python<'_>,
    state: Bound<'_, PyAny>,
) -> PyResult<String> {
    let routes = get_routes(py, &state);
    let vias = get_vias(py, &state);

    let mut route_entries: Vec<(String, (String, i64))> = Vec::new();

    for item in routes.try_iter()? {
        let route = item?;
        let net_name = get_attr_str(&route, "net_name", "unnamed");
        let layer = get_attr_i64(&route, "layer", 0);
        let start = get_attr_tuple(&route, "start", (0.0, 0.0));
        let end = get_attr_tuple(&route, "end", (0.0, 0.0));
        let width = get_attr_f64(&route, "width", 0.25);

        let line = format!(
            "(wire {} (path {} {} {} {} {} {}))",
            net_name,
            layer,
            format_float(width),
            format_float(start.0),
            format_float(start.1),
            format_float(end.0),
            format_float(end.1),
        );
        route_entries.push((line, (net_name, layer)));
    }

    route_entries.sort_by(|a, b| a.1.cmp(&b.1));
    let mut route_lines: Vec<String> = route_entries
        .into_iter()
        .map(|(line, _)| line)
        .collect();
    route_lines.sort();

    let mut via_lines: Vec<String> = Vec::new();
    for item in vias.try_iter()? {
        let via = item?;
        let net_name = get_attr_str(&via, "net_name", "unnamed");
        let center = get_attr_tuple(&via, "center", (0.0, 0.0));
        via_lines.push(format!(
            "(via {} {} {})",
            net_name,
            format_float(center.0),
            format_float(center.1),
        ));
    }
    via_lines.sort();

    let mut result = String::from("(session\n(resolution um 10)\n(unit mm)\n\n");

    if route_lines.is_empty() {
        result.push_str("(routes)\n)\n");
        return Ok(result);
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

    result.push_str(")\n");
    Ok(result)
}

// ---------------------------------------------------------------------------
// golden_serializers: serialize_violations_to_json
// ---------------------------------------------------------------------------

fn get_violations_or_empty<'py>(
    py: Python<'py>,
    state: &Bound<'py, PyAny>,
    attr: &str,
) -> Bound<'py, PyAny> {
    if let Ok(v) = state.getattr(attr) {
        if !v.is_none() {
            return v;
        }
    }
    py.eval(c"()", None, None).unwrap().into()
}

fn get_attr_str_or(v: &Bound<'_, PyAny>, name: &str) -> String {
    v.getattr(name)
        .ok()
        .and_then(|val| val.extract::<String>().ok())
        .unwrap_or_default()
}

fn get_attr_f64_or(v: &Bound<'_, PyAny>, name: &str) -> f64 {
    v.getattr(name)
        .ok()
        .and_then(|val| val.extract::<f64>().ok())
        .unwrap_or(0.0)
}

fn round6(val: f64) -> f64 {
    (val * 1_000_000.0).round() / 1_000_000.0
}

fn maybe_loc(py: Python<'_>, v: &Bound<'_, PyAny>) -> Option<Py<PyAny>> {
    let loc = v.getattr("location").ok()?;
    if loc.is_none() {
        return None;
    }
    let x = loc.getattr("x").ok().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
    let y = loc.getattr("y").ok().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
    let d = PyDict::new(py);
    d.set_item("x", round6(x)).ok()?;
    d.set_item("y", round6(y)).ok()?;
    Some(d.into())
}

#[pyfunction]
fn serialize_violations_to_json(
    py: Python<'_>,
    state: Bound<'_, PyAny>,
) -> PyResult<String> {
    let violations = get_violations_or_empty(py, &state, "drc_violations");

    let mut entries: Vec<(String, Py<PyAny>)> = Vec::new();

    for item in violations.try_iter()? {
        let v = item?;
        let net_a = get_attr_str_or(&v, "net_a");
        let net_b = get_attr_str_or(&v, "net_b");
        let vtype = get_attr_str_or(&v, "type");

        let entry = PyDict::new(py);
        entry.set_item("type", vtype.as_str())?;
        entry.set_item("net_a", net_a.as_str())?;
        entry.set_item("net_b", net_b.as_str())?;
        entry.set_item("geometry_a_id", get_attr_str_or(&v, "geometry_a_id"))?;
        entry.set_item("geometry_b_id", get_attr_str_or(&v, "geometry_b_id"))?;
        entry.set_item(
            "clearance_actual",
            round6(get_attr_f64_or(&v, "clearance_actual")),
        )?;
        entry.set_item(
            "clearance_required",
            round6(get_attr_f64_or(&v, "clearance_required")),
        )?;
        entry.set_item("location", maybe_loc(py, &v))?;
        entry.set_item(
            "severity",
            round6(get_attr_f64_or(&v, "severity")),
        )?;

        let key = format!("{}|{}|{}", net_a, net_b, vtype);
        entries.push((key, entry.into()));
    }

    entries.sort_by(|a, b| a.0.cmp(&b.0));

    let outer = PyDict::new(py);
    outer.set_item("format_version", CURRENT_FORMAT_VERSION)?;
    let viol_list = PyList::new(py, entries.into_iter().map(|(_, obj)| obj))?;
    outer.set_item("violations", viol_list)?;

    let json_mod = py.import("json")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("indent", 2)?;
    kwargs.set_item("sort_keys", true)?;
    let result: String = json_mod
        .call_method("dumps", (outer,), Some(&kwargs))?
        .extract()?;
    Ok(result)
}

// ---------------------------------------------------------------------------
// golden_serializers: serialize_connectivity_to_json
// ---------------------------------------------------------------------------

#[pyfunction]
fn serialize_connectivity_to_json(
    py: Python<'_>,
    state: Bound<'_, PyAny>,
) -> PyResult<String> {
    let violations = get_violations_or_empty(py, &state, "connectivity_violations");

    let mut entries: Vec<(String, Py<PyAny>)> = Vec::new();

    for item in violations.try_iter()? {
        let v = item?;
        let net = get_attr_str_or(&v, "net");
        let vtype = get_attr_str_or(&v, "type");

        let entry = PyDict::new(py);
        entry.set_item("type", vtype.as_str())?;
        entry.set_item("net", net.as_str())?;
        entry.set_item("description", get_attr_str_or(&v, "description"))?;
        entry.set_item("location", maybe_loc(py, &v))?;

        let key = format!("{}|{}", net, vtype);
        entries.push((key, entry.into()));
    }

    entries.sort_by(|a, b| a.0.cmp(&b.0));

    let outer = PyDict::new(py);
    outer.set_item("format_version", CURRENT_FORMAT_VERSION)?;
    let viol_list = PyList::new(py, entries.into_iter().map(|(_, obj)| obj))?;
    outer.set_item("violations", viol_list)?;

    let json_mod = py.import("json")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("indent", 2)?;
    kwargs.set_item("sort_keys", true)?;
    let result: String = json_mod
        .call_method("dumps", (outer,), Some(&kwargs))?
        .extract()?;
    Ok(result)
}

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

#[pymodule]
fn temper_io_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("CURRENT_FORMAT_VERSION", CURRENT_FORMAT_VERSION)?;

    // Exceptions
    m.add("FootprintParseError", m.py().get_type::<FootprintParseError>())?;

    // Classes
    m.add_class::<TraceSegment>()?;
    m.add_class::<TraceVia>()?;
    m.add_class::<ExportResult>()?;
    m.add_class::<FootprintBounds>()?;

    // Functions
    m.add_function(wrap_pyfunction!(parse_footprint_courtyard, m)?)?;
    m.add_function(wrap_pyfunction!(parse_footprint_directory, m)?)?;
    m.add_function(wrap_pyfunction!(isolation_slot_aabb, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_boardstate_to_dsn, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_boardstate_to_ses, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_violations_to_json, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_connectivity_to_json, m)?)?;

    // SERIALIZER_REGISTRY
    let registry = PyDict::new(m.py());
    registry.set_item(
        "serialize_boardstate_to_dsn",
        m.getattr("serialize_boardstate_to_dsn")?,
    )?;
    registry.set_item(
        "serialize_boardstate_to_ses",
        m.getattr("serialize_boardstate_to_ses")?,
    )?;
    registry.set_item(
        "serialize_violations_to_json",
        m.getattr("serialize_violations_to_json")?,
    )?;
    registry.set_item(
        "serialize_connectivity_to_json",
        m.getattr("serialize_connectivity_to_json")?,
    )?;
    m.add("SERIALIZER_REGISTRY", registry)?;

    Ok(())
}

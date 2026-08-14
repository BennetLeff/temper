//! Marshalling boundary: pydantic→plain conversion + K1-schema dict builders.
//!
//! Migrated from `temper_placer/validation/drc_oracle.py` (Wave 4, marshalling
//! boundary fanout). These functions accept the Python netlist/context/pydantic
//! objects that the placer-path `DRCOracle.evaluate()` used to marshal into K1
//! dicts in Python, and produce the same K1 dicts from Rust.
//!
//! The pydantic `PlacementConstraints` model stays Python (JUSTIFIED-KEEP);
//! only the conversion of its values to the flat wire format migrates here.
//!
//! ## Functions
//!
//! | Python function | Rust pyfunction |
//! |---|---|
//! | `_constraint_value_to_plain` | [`constraint_value_to_plain_py`] |
//! | `DRCOracle._build_board_dict` | [`build_board_dict_py`] |
//! | `DRCOracle._build_board_dict_from_parsed_pcb` | [`build_board_dict_from_parsed_pcb_py`] |
//! | `DRCOracle._build_constraints_dict` | [`build_constraints_dict_py`] |

use std::panic::AssertUnwindSafe;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------------
// Guard — catch_unwind at the pyo3 boundary (G7)
// ---------------------------------------------------------------------------

fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match std::panic::catch_unwind(AssertUnwindSafe(body)) {
        Ok(r) => r,
        Err(_) => Err(pyo3::exceptions::PyRuntimeError::new_err(
            "panic in drc_oracle_marshal kernel",
        )),
    }
}

// ---------------------------------------------------------------------------
// _constraint_value_to_plain — recursive pydantic→plain converter
// ---------------------------------------------------------------------------

/// Recursively convert a Python value (which may be a pydantic `BaseModel`
/// instance, a list, or a scalar) into a plain dict/list/scalar suitable for
/// the K1 constraints schema consumed by `build_constraint_set`.
///
/// Python original (verbatim from `drc_oracle.py` line 77–90):
///
/// ```python
/// if isinstance(value, BaseModel):
///     return value.model_dump(mode="json")
/// if isinstance(value, (list, tuple)):
///     return [_constraint_value_to_plain(v) for v in value]
/// return value
/// ```
///
/// The `mode="json"` is load-bearing: pydantic fields typed as `tuple[...]`
/// (the project's immutable-field convention) are coerced to `list` so the
/// PyO3 JSON bridge on the Rust side (which only recognizes `list`, not
/// `tuple`) can consume them.
#[pyfunction]
fn constraint_value_to_plain_py<'py>(
    py: Python<'py>,
    value: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    guard(|| {
        // Check if value is a pydantic BaseModel (duck-typed: has model_dump)
        if let Ok(true) = value.hasattr("model_dump") {
            // Call model_dump(mode="json") — kwargs via dict
            let kwargs = PyDict::new(py);
            kwargs.set_item("mode", "json")?;
            return value.call_method("model_dump", (), Some(&kwargs));
        }

        // Check if value is a list or tuple → recursively convert
        if value.is_instance_of::<PyList>() {
            let list: Bound<'_, PyList> = value.extract()?;
            let out = PyList::empty(py);
            for item in list.iter() {
                let converted = constraint_value_to_plain_py(py, item)?;
                out.append(converted)?;
            }
            return Ok(out.into_any());
        }
        if value.is_instance_of::<pyo3::types::PyTuple>() {
            let tup: Bound<'_, pyo3::types::PyTuple> = value.extract()?;
            let out = PyList::empty(py);
            for item in tup.iter() {
                let converted = constraint_value_to_plain_py(py, item)?;
                out.append(converted)?;
            }
            return Ok(out.into_any());
        }

        // Scalar: return as-is
        Ok(value)
    })
}

// ---------------------------------------------------------------------------
// infer_package_type — footprint → package-type classification
// (verbatim port from the Python drc_oracle.py)
// ---------------------------------------------------------------------------

/// Infer SMD package type from footprint name.
///
/// This is already available as `temper_drc_rs.infer_package_type` (the
/// Phase 4 migration), but the dict builders need it internally and calling
/// back into the module from Rust is unnecessary indirection.  The body here
/// is the same keyword-first-match, case-insensitive substring search.
///
/// `pub(crate)` since Phase-A U5 (`drc_marshal.rs`) reuses it for the typed
/// `DrcBoardSnapshot` constructors.
pub(crate) fn infer_package_type(footprint: Option<&str>) -> &'static str {
    let fp_lower = footprint.unwrap_or("").to_lowercase();
    let fp = fp_lower.as_str();
    if fp.contains("tht") || fp.contains("through") || fp.contains("pin") || fp.contains("dip") {
        return "tht";
    }
    if fp.contains("to-247") || fp.contains("to247") {
        return "to247";
    }
    if fp.contains("to-220") || fp.contains("to220") {
        return "to220";
    }
    if fp.contains("bga") {
        return "bga";
    }
    if fp.contains("qfn") {
        return "qfn";
    }
    if fp.contains("qfp") || fp.contains("tqfp") {
        return "qfp";
    }
    if fp.contains("dpak") || fp.contains("d2pak") {
        return "dpak";
    }
    "smd"
}

// ---------------------------------------------------------------------------
// Helpers: extract Python object attributes
// ---------------------------------------------------------------------------

/// Get a required float attribute from a Python object.
pub(crate) fn get_attr_f64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<f64> {
    obj.getattr(name)?
        .extract::<f64>()
        .map_err(|e| PyValueError::new_err(format!(".{name} is not a float: {e}")))
}

/// Get an optional float attribute (None if absent or None).
pub(crate) fn get_attr_opt_f64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<f64>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: f64 = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not a float: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Get a required string attribute.
pub(crate) fn get_attr_str(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    obj.getattr(name)?
        .extract::<String>()
        .map_err(|e| PyValueError::new_err(format!(".{name} is not a string: {e}")))
}

/// Get an optional string attribute.
pub(crate) fn get_attr_opt_str(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<String>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: String = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not a string: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Get an optional int attribute.
pub(crate) fn get_attr_opt_i64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<i64>> {
    match obj.getattr(name) {
        Ok(val) if !val.is_none() => {
            let v: i64 = val.extract().map_err(|e| {
                PyValueError::new_err(format!(".{name} is not an int: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

// ---------------------------------------------------------------------------
// _build_board_dict — placer-path K1 board dict builder
// ---------------------------------------------------------------------------

/// Build a K1-schema board dict from the placer's positions array + netlist
/// context (the path `DRCOracle.evaluate()` takes).
///
/// Returns a Python dict with keys: `board`, `components`, `nets`,
/// `net_classes`, `net_class_rules`.
///
/// The `positions` array is a numpy array of shape (N, 2); each component
/// at index `i` is at `(positions[i, 0], positions[i, 1])`.
///
/// # Parameters
/// - `positions`: numpy ndarray, shape (N, 2), dtype float64
/// - `netlist`: Python object with `.components` (list of Component) and
///   `.nets` (list of Net)
/// - `board_width`: board width in mm
/// - `board_height`: board height in mm
/// - `board_margin`: board margin in mm
/// - `clearance_rules`: Python list of ClearanceRule objects
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn build_board_dict_py<'py>(
    py: Python<'py>,
    positions: Bound<'py, PyAny>,
    netlist: Bound<'py, PyAny>,
    board_width: f64,
    board_height: f64,
    board_margin: f64,
    clearance_rules: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    guard(|| {
        let out = PyDict::new(py);

        // --- Board dimensions ---
        let board = PyDict::new(py);
        board.set_item("width_mm", board_width)?;
        board.set_item("height_mm", board_height)?;
        board.set_item("margin_mm", board_margin)?;
        out.set_item("board", board)?;

        // --- Components ---
        let comps_py = netlist.getattr("components")?;
        let comps_list: Bound<'_, PyList> = comps_py
            .cast_into::<PyList>()
            .map_err(|e| PyValueError::new_err(format!(".components is not a list: {e}")))?;

        let components_out = PyList::empty(py);
        for (i, comp) in comps_list.iter().enumerate() {
            // positions[i, 0] and positions[i, 1] via numpy indexing
            let x = positions.call_method1("__getitem__", ((i as i64, 0i64),))?.extract::<f64>()?;
            let y = positions.call_method1("__getitem__", ((i as i64, 1i64),))?.extract::<f64>()?;

            let footprint = get_attr_opt_str(&comp, "footprint")?;
            let rotation = get_attr_opt_i64(&comp, "initial_rotation_quadrant")?
                .map(|r| r as f64 * 90.0)
                .unwrap_or(0.0);
            let side = get_attr_opt_i64(&comp, "initial_side")?;
            let side_str = if side == Some(1) { "bottom" } else { "top" };
            let pkg = infer_package_type(footprint.as_deref());
            let refdes = get_attr_str(&comp, "ref")?;
            let is_mechanical = refdes.starts_with("MH") || pkg == "MECHANICAL";
            let width = get_attr_opt_f64(&comp, "width")?.unwrap_or(0.0);
            let height = get_attr_opt_f64(&comp, "height")?.unwrap_or(0.0);
            let net_class = get_attr_str(&comp, "net_class")?;

            let comp_dict = PyDict::new(py);
            comp_dict.set_item("ref", &refdes)?;
            comp_dict.set_item("x", x)?;
            comp_dict.set_item("y", y)?;
            comp_dict.set_item("rot", rotation)?;
            comp_dict.set_item("side", side_str)?;
            comp_dict.set_item("width", width)?;
            comp_dict.set_item("height", height)?;
            comp_dict.set_item("net_class", &net_class)?;
            comp_dict.set_item("package_type", pkg)?;
            comp_dict.set_item("power_dissipation_w", py.None())?;
            comp_dict.set_item("is_magnetic", false)?;
            comp_dict.set_item("is_electrolytic", false)?;
            comp_dict.set_item("is_mechanical", is_mechanical)?;
            comp_dict.set_item("vent_direction", py.None())?;
            comp_dict.set_item("footprint_polygon", py.None())?;
            components_out.append(comp_dict)?;
        }
        out.set_item("components", components_out)?;

        // --- Nets ---
        let nets_py = netlist.getattr("nets")?;
        let nets_list: Bound<'_, PyList> = nets_py
            .cast_into::<PyList>()
            .map_err(|e| PyValueError::new_err(format!(".nets is not a list: {e}")))?;

        let nets_dict = PyDict::new(py);
        let net_classes_dict = PyDict::new(py);
        for net in nets_list.iter() {
            let net_name = get_attr_str(&net, "name")?;
            let net_class = get_attr_str(&net, "net_class")?;
            let pins = net.getattr("pins")?;
            let pins_list: Bound<'_, PyList> = pins
                .cast_into::<PyList>()
                .map_err(|e| PyValueError::new_err(format!(".pins is not a list: {e}")))?;

            // Deduplicate component refs (matching Python's set comprehension)
            let mut seen = std::collections::HashSet::new();
            let refs = PyList::empty(py);
            for pin in pins_list.iter() {
                // Each pin is a tuple (ref, pin_number)
                let ref_val: String = pin.get_item(0)?.extract()?;
                if seen.insert(ref_val.clone()) {
                    refs.append(ref_val)?;
                }
            }
            nets_dict.set_item(&net_name, refs)?;
            net_classes_dict.set_item(&net_name, &net_class)?;
        }
        out.set_item("nets", nets_dict)?;
        out.set_item("net_classes", net_classes_dict)?;

        // --- Net class rules ---
        let rules_list: Bound<'_, PyList> = clearance_rules
            .cast_into::<PyList>()
            .map_err(|e| PyValueError::new_err(format!("clearance_rules is not a list: {e}")))?;

        let ncr_dict = PyDict::new(py);
        for rule in rules_list.iter() {
            let a = get_attr_str(&rule, "net_class_a")?;
            let b = get_attr_str(&rule, "net_class_b")?;
            let min_clearance = get_attr_f64(&rule, "min_clearance")?;
            for nc in [&a, &b] {
                if !ncr_dict.contains(nc.as_str())? {
                    let entry = PyDict::new(py);
                    entry.set_item("trace_width_mm", 0.2)?;
                    entry.set_item("clearance_mm", min_clearance)?;
                    entry.set_item("creepage_mm", py.None())?;
                    entry.set_item("voltage_v", py.None())?;
                    entry.set_item("max_current_rating", py.None())?;
                    entry.set_item("safety_category", py.None())?;
                    entry.set_item("required_layer", py.None())?;
                    entry.set_item("routing_strategy", py.None())?;
                    ncr_dict.set_item(nc.as_str(), entry)?;
                }
            }
        }
        out.set_item("net_class_rules", ncr_dict)?;

        Ok(out)
    })
}

// ---------------------------------------------------------------------------
// _build_board_dict_from_parsed_pcb — parsed-PCB-path K1 board dict builder
// ---------------------------------------------------------------------------

/// Build a K1-schema board dict from a `ParsedPCB` object.
///
/// Used by `ci_closure_test.py` and other callers that have a parsed
/// `.kicad_pcb` rather than a placer positions array.
#[pyfunction]
fn build_board_dict_from_parsed_pcb_py<'py>(
    py: Python<'py>,
    parsed_pcb: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    guard(|| {
        let out = PyDict::new(py);

        // --- Components ---
        let comps_py = parsed_pcb.getattr("components")?;
        let comps_list: Bound<'_, PyList> = comps_py
            .cast_into::<PyList>()
            .map_err(|e| PyValueError::new_err(format!(".components is not a list: {e}")))?;

        let components_out = PyList::empty(py);
        for comp in comps_list.iter() {
            let initial_pos = comp.getattr("initial_position")?;
            let (x, y) = if initial_pos.is_none() {
                (0.0, 0.0)
            } else {
                let tup: Bound<'_, pyo3::types::PyTuple> =
                    initial_pos.cast_into::<pyo3::types::PyTuple>().map_err(|e| {
                        PyValueError::new_err(format!(".initial_position is not a tuple: {e}"))
                    })?;
                let x: f64 = tup.get_item(0)?.extract()?;
                let y: f64 = tup.get_item(1)?.extract()?;
                (x, y)
            };

            let footprint = get_attr_opt_str(&comp, "footprint")?;
            let rotation = get_attr_opt_i64(&comp, "initial_rotation_quadrant")?
                .map(|r| r as f64 * 90.0)
                .unwrap_or(0.0);
            let side = get_attr_opt_i64(&comp, "initial_side")?;
            let side_str = if side == Some(1) { "bottom" } else { "top" };
            let pkg = infer_package_type(footprint.as_deref());
            let refdes = get_attr_str(&comp, "ref")?;
            let is_mechanical = refdes.starts_with("MH") || pkg == "MECHANICAL";
            let width = get_attr_opt_f64(&comp, "width")?.unwrap_or(0.0);
            let height = get_attr_opt_f64(&comp, "height")?.unwrap_or(0.0);
            let net_class = get_attr_str(&comp, "net_class")?;

            let comp_dict = PyDict::new(py);
            comp_dict.set_item("ref", &refdes)?;
            comp_dict.set_item("x", x)?;
            comp_dict.set_item("y", y)?;
            comp_dict.set_item("rot", rotation)?;
            comp_dict.set_item("side", side_str)?;
            comp_dict.set_item("width", width)?;
            comp_dict.set_item("height", height)?;
            comp_dict.set_item("net_class", &net_class)?;
            comp_dict.set_item("package_type", pkg)?;
            comp_dict.set_item("power_dissipation_w", py.None())?;
            comp_dict.set_item("is_magnetic", false)?;
            comp_dict.set_item("is_electrolytic", false)?;
            comp_dict.set_item("is_mechanical", is_mechanical)?;
            comp_dict.set_item("vent_direction", py.None())?;
            comp_dict.set_item("footprint_polygon", py.None())?;
            components_out.append(comp_dict)?;
        }
        out.set_item("components", components_out)?;

        // --- Nets ---
        let nets_py = parsed_pcb.getattr("nets")?;
        let nets_list: Bound<'_, PyList> = nets_py
            .cast_into::<PyList>()
            .map_err(|e| PyValueError::new_err(format!(".nets is not a list: {e}")))?;

        let nets_dict = PyDict::new(py);
        let net_classes_dict = PyDict::new(py);
        for net in nets_list.iter() {
            let net_name = get_attr_str(&net, "name")?;
            let net_class = get_attr_str(&net, "net_class")?;
            let pins = net.getattr("pins")?;
            let pins_list: Bound<'_, PyList> = pins
                .cast_into::<PyList>()
                .map_err(|e| PyValueError::new_err(format!(".pins is not a list: {e}")))?;

            let mut seen = std::collections::HashSet::new();
            let refs = PyList::empty(py);
            for pin in pins_list.iter() {
                let ref_val: String = pin.get_item(0)?.extract()?;
                if seen.insert(ref_val.clone()) {
                    refs.append(ref_val)?;
                }
            }
            nets_dict.set_item(&net_name, refs)?;
            net_classes_dict.set_item(&net_name, &net_class)?;
        }
        out.set_item("nets", nets_dict)?;
        out.set_item("net_classes", net_classes_dict)?;

        // --- Net class rules from parsed DesignRules ---
        let design_rules = parsed_pcb.getattr("design_rules")?;
        let net_classes = design_rules.getattr("net_classes")?;
        let nc_dict: Bound<'_, PyDict> = net_classes
            .cast_into::<PyDict>()
            .map_err(|e| PyValueError::new_err(format!(".design_rules.net_classes is not a dict: {e}")))?;

        let ncr_dict = PyDict::new(py);
        for (class_name, rules_val) in nc_dict.iter() {
            let rules: Bound<'_, PyAny> = rules_val;
            let entry = PyDict::new(py);
            entry.set_item("trace_width_mm", get_attr_f64(&rules, "trace_width_mm").unwrap_or(0.2))?;
            entry.set_item("clearance_mm", get_attr_f64(&rules, "clearance_mm").unwrap_or(0.2))?;
            entry.set_item("creepage_mm", py.None())?;
            entry.set_item("voltage_v", py.None())?;
            entry.set_item("max_current_rating", py.None())?;
            entry.set_item("safety_category", py.None())?;
            entry.set_item("required_layer", py.None())?;
            entry.set_item("routing_strategy", py.None())?;
            ncr_dict.set_item(class_name, entry)?;
        }
        out.set_item("net_class_rules", ncr_dict)?;

        // --- Board dimensions ---
        let board_obj = parsed_pcb.getattr("board")?;
        let board = PyDict::new(py);
        board.set_item("width_mm", get_attr_f64(&board_obj, "width").unwrap_or(0.0))?;
        board.set_item("height_mm", get_attr_f64(&board_obj, "height").unwrap_or(0.0))?;
        board.set_item("margin_mm", 3.0)?;
        out.set_item("board", board)?;

        Ok(out)
    })
}

// ---------------------------------------------------------------------------
// _build_constraints_dict — K1 constraints dict builder
// ---------------------------------------------------------------------------

const CONSTRAINTS_CONFIG_KEYS: &[&str] = &[
    "zones",
    "critical_loops",
    "noise_domains",
    "isolation_barriers",
    "thermal_properties",
    "matched_length_groups",
    "snubber_requirements",
    "bleed_resistor",
    "skin_effect_derating",
];

/// Build a K1-schema constraints dict from clearance rules + optional
/// constraints_config (PlacementConstraints).
///
/// The constraints_config carries YAML-derived values that override the
/// defaults (noise_domains, isolation_barriers, etc.).  The values may
/// be pydantic `BaseModel` instances, which are converted via
/// [`constraint_value_to_plain_py`].
#[pyfunction]
fn build_constraints_dict_py<'py>(
    py: Python<'py>,
    clearance_rules: Bound<'py, PyAny>,
    constraints_config: Option<Bound<'py, PyAny>>,
    board_width: f64,
    board_height: f64,
) -> PyResult<Bound<'py, PyDict>> {
    guard(|| {
        let out = PyDict::new(py);

        // --- Defaults ---
        for key in CONSTRAINTS_CONFIG_KEYS {
            if *key == "bleed_resistor" || *key == "skin_effect_derating" {
                out.set_item(*key, py.None())?;
            } else {
                out.set_item(*key, PyList::empty(py))?;
            }
        }
        out.set_item("clearances", PyList::empty(py))?;
        out.set_item("hv_clearance_mm", 10.0)?;
        out.set_item("board_width", board_width)?;
        out.set_item("board_height", board_height)?;

        // --- Clearance rules ---
        if let Ok(rules_list) = clearance_rules.cast_into::<PyList>() {
            let clearances = PyList::empty(py);
            for rule in rules_list.iter() {
                let entry = PyDict::new(py);
                entry.set_item("from_class", get_attr_str(&rule, "net_class_a")?)?;
                entry.set_item("to_class", get_attr_str(&rule, "net_class_b")?)?;
                entry.set_item("clearance_mm", get_attr_f64(&rule, "min_clearance")?)?;
                entry.set_item(
                    "description",
                    get_attr_opt_str(&rule, "because")?.unwrap_or_default(),
                )?;
                clearances.append(entry)?;
            }
            out.set_item("clearances", clearances)?;
        }

        // --- Merge constraints_config if present ---
        if let Some(config) = constraints_config {
            for key in CONSTRAINTS_CONFIG_KEYS {
                // Match Python's `getattr(config, key, None)` — gracefully
                // return None for missing attributes.
                let val = match config.getattr(*key) {
                    Ok(v) => v,
                    Err(_) => continue,
                };
                if !val.is_none() {
                    let plain = constraint_value_to_plain_py(py, val)?;
                    out.set_item(*key, plain)?;
                }
            }
        }

        Ok(out)
    })
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

/// Register the drc_oracle marshal kernels on the `temper_drc_rs` module.
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(constraint_value_to_plain_py, module)?)?;
    module.add_function(wrap_pyfunction!(build_board_dict_py, module)?)?;
    module.add_function(wrap_pyfunction!(build_board_dict_from_parsed_pcb_py, module)?)?;
    module.add_function(wrap_pyfunction!(build_constraints_dict_py, module)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Rust unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn infer_package_type_basics() {
        assert_eq!(infer_package_type(Some("Resistor_SMD:R_0603")), "smd");
        assert_eq!(infer_package_type(None), "smd");
        assert_eq!(infer_package_type(Some("")), "smd");
        assert_eq!(infer_package_type(Some("TO-247")), "to247");
        assert_eq!(infer_package_type(Some("BGA-100")), "bga");
        assert_eq!(infer_package_type(Some("QFN-32")), "qfn");
        assert_eq!(infer_package_type(Some("TQFP-64")), "qfp");
        assert_eq!(infer_package_type(Some("DPAK")), "dpak");
        assert_eq!(infer_package_type(Some("THT_HEADER")), "tht");
        // precedence: tht beats to-247
        assert_eq!(infer_package_type(Some("TO-247-THT")), "tht");
        // first-match: qfn beats dpak
        assert_eq!(infer_package_type(Some("QFN_DPAK")), "qfn");
        // case insensitivity
        assert_eq!(infer_package_type(Some("TqFp")), "qfp");
    }
}

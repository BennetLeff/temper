//! pyo3 surface for router_v6 cluster F.
//!
//! The 15 exports named in
//! `tests/router_v6/test_quality_metrics_rust_differential.py::REQUIRED_RUST_SYMBOLS`.
//!
//! Two conventions the differential's `sig()` comparator forces:
//!
//! * **Container and scalar types are part of the value.** `sig` records
//!   `type(v).__name__` at every leaf, so a `tuple` never matches a `list` and
//!   an `int` never matches a `float`. `_vector`, `_overlap` and `_gap` are
//!   therefore evaluated on the Python objects themselves — `_vector((0,0),
//!   (3,4))` is `(3, 4)`, two *ints*, and returning `(3.0, 4.0)` would fail.
//!   Every other kernel returns a float or a bool in Python for every input,
//!   so those extract to `f64` up front.
//! * **Dict and list order is part of the value.** `sig` does not sort, so the
//!   finding order and the `_load_traces_by_net` key order are compared
//!   directly.
//!
//! A "board source" argument is either a scenario `dict` from
//! `_quality_metrics_cases` or a path to a `.kicad_pcb`. A path is resolved by
//! calling the same `parse_kicad_pcb` the oracle's `_parse_pcb` calls: the
//! parser is shared I/O, already migrated separately, and is the reason the
//! oracle omits the `_parse_pcb` copies as "pure I/O delegation".

use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

use super::board::{Board, Component, Num, ParseView, Point, Trace, Via};
use super::slop_linter::{self, Finding};
use super::via_count;

// ---------------------------------------------------------------------------
// Board-source extraction
// ---------------------------------------------------------------------------

/// `router_v6.net_classification._SINGLE_LAYER_MODE`, read at call time.
///
/// It is a module global that `is_ground_net` branches on, i.e. a hidden input
/// to `_classify_vias`. Sampling it per call is what makes the Rust arm track
/// `set_single_layer_mode` the way the Python arm does.
fn read_single_layer_mode(py: Python<'_>) -> bool {
    py.import("temper_placer.router_v6.net_classification")
        .and_then(|m| m.getattr("_SINGLE_LAYER_MODE"))
        .and_then(|v| v.extract::<bool>())
        .unwrap_or(false)
}

/// Extract a coordinate while keeping its Python type.
///
/// `sig()` compares `type(v).__name__` at every leaf, and the real parser
/// emits a mix of `int` and `float` coordinates, so an `int` that is widened
/// here comes back as a `float` in an echoed `position` and fails the
/// differential. Exact type checks are used so a `bool` (a Python `int`
/// subclass) is not silently rendered as an `int`.
fn extract_num(value: &Bound<'_, PyAny>) -> PyResult<Num> {
    if value.is_exact_instance_of::<PyFloat>() {
        Ok(Num::Float(value.extract()?))
    } else if value.is_exact_instance_of::<PyInt>() {
        Ok(Num::Int(value.extract()?))
    } else {
        Ok(Num::Float(value.extract()?))
    }
}

fn extract_point(value: &Bound<'_, PyAny>) -> PyResult<Point> {
    let tup: Bound<'_, PyTuple> = value.clone().cast_into::<PyTuple>()?;
    Ok((
        extract_num(&tup.get_item(0)?)?,
        extract_num(&tup.get_item(1)?)?,
    ))
}

fn num_to_py<'py>(py: Python<'py>, n: Num) -> PyResult<Bound<'py, PyAny>> {
    Ok(match n {
        Num::Int(i) => i.into_pyobject(py)?.into_any(),
        Num::Float(x) => x.into_pyobject(py)?.into_any(),
    })
}

fn point_to_py<'py>(py: Python<'py>, p: Point) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, [num_to_py(py, p.0)?, num_to_py(py, p.1)?])
}

fn opt_string(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(value.extract::<String>()?))
    }
}

fn view_from_scenario(scenario: &Bound<'_, PyDict>, single_layer_mode: bool) -> PyResult<ParseView> {
    let mut view = ParseView {
        single_layer_mode,
        ..Default::default()
    };

    if let Some(items) = scenario.get_item("traces")? {
        for item in items.try_iter()? {
            let t = item?;
            let tup: Bound<'_, PyTuple> = t.cast_into::<PyTuple>()?;
            view.traces.push(Trace {
                start: (
                    extract_num(&tup.get_item(0)?)?,
                    extract_num(&tup.get_item(1)?)?,
                ),
                end: (
                    extract_num(&tup.get_item(2)?)?,
                    extract_num(&tup.get_item(3)?)?,
                ),
                width: extract_num(&tup.get_item(4)?)?,
                layer: tup.get_item(5)?.extract()?,
                net: opt_string(&tup.get_item(6)?)?,
            });
        }
    }

    if let Some(items) = scenario.get_item("vias")? {
        for item in items.try_iter()? {
            let v = item?;
            let tup: Bound<'_, PyTuple> = v.cast_into::<PyTuple>()?;
            view.vias.push(Via {
                position: extract_point(&tup.get_item(0)?)?,
                net: opt_string(&tup.get_item(1)?)?,
            });
        }
    }

    if let Some(items) = scenario.get_item("components")? {
        for item in items.try_iter()? {
            let c = item?;
            let tup: Bound<'_, PyTuple> = c.cast_into::<PyTuple>()?;
            let pos_obj = tup.get_item(1)?;
            let initial_position = if pos_obj.is_none() {
                None
            } else {
                Some(pos_obj.extract::<(f64, f64)>()?)
            };
            view.components.push(Component {
                reference: tup.get_item(0)?.extract()?,
                initial_position,
                width: tup.get_item(2)?.extract()?,
                height: tup.get_item(3)?.extract()?,
            });
        }
    }

    if let Some(board) = scenario.get_item("board")?
        && !board.is_none()
    {
        let (width, height): (f64, f64) = board.extract()?;
        view.board = Some(Board { width, height });
    }

    Ok(view)
}

fn view_from_parse_result(result: &Bound<'_, PyAny>, single_layer_mode: bool) -> PyResult<ParseView> {
    let mut view = ParseView {
        single_layer_mode,
        ..Default::default()
    };

    for item in result.getattr("traces")?.try_iter()? {
        let t = item?;
        view.traces.push(Trace {
            start: extract_point(&t.getattr("start")?)?,
            end: extract_point(&t.getattr("end")?)?,
            width: extract_num(&t.getattr("width")?)?,
            layer: t.getattr("layer")?.extract()?,
            net: opt_string(&t.getattr("net")?)?,
        });
    }

    for item in result.getattr("vias")?.try_iter()? {
        let v = item?;
        view.vias.push(Via {
            position: extract_point(&v.getattr("position")?)?,
            net: opt_string(&v.getattr("net")?)?,
        });
    }

    for item in result.getattr("netlist")?.getattr("components")?.try_iter()? {
        let c = item?;
        let pos_obj = c.getattr("initial_position")?;
        let initial_position = if pos_obj.is_none() {
            None
        } else {
            Some(pos_obj.extract::<(f64, f64)>()?)
        };
        view.components.push(Component {
            reference: c.getattr("ref")?.extract()?,
            initial_position,
            width: c.getattr("width")?.extract()?,
            height: c.getattr("height")?.extract()?,
        });
    }

    let board = result.getattr("board")?;
    if !board.is_none() {
        view.board = Some(Board {
            width: board.getattr("width")?.extract()?,
            height: board.getattr("height")?.extract()?,
        });
    }

    Ok(view)
}

/// Turn a scenario dict or a `.kicad_pcb` path into the parsed-board view.
fn build_view(py: Python<'_>, source: &Bound<'_, PyAny>) -> PyResult<ParseView> {
    let single_layer_mode = read_single_layer_mode(py);
    if let Ok(dict) = source.clone().cast_into::<PyDict>() {
        return view_from_scenario(&dict, single_layer_mode);
    }
    if source.is_instance_of::<PyString>() || source.hasattr("__fspath__")? {
        let parser = py.import("temper_placer.io.kicad_parser")?;
        let result = parser.call_method1("parse_kicad_pcb", (source,))?;
        return view_from_parse_result(&result, single_layer_mode);
    }
    Err(PyTypeError::new_err(
        "board source must be a scenario dict or a .kicad_pcb path",
    ))
}

// ---------------------------------------------------------------------------
// Conversion helpers
// ---------------------------------------------------------------------------

fn finding_to_dict<'py>(py: Python<'py>, f: &Finding) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("type", f.kind)?;
    d.set_item("net_name", &f.net_name)?;
    d.set_item("position", point_to_py(py, f.position)?)?;
    d.set_item("severity", f.severity)?;
    d.set_item("description", &f.description)?;
    Ok(d)
}

fn findings_to_list<'py>(py: Python<'py>, findings: &[Finding]) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    for f in findings {
        out.append(finding_to_dict(py, f)?)?;
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// metrics/slop_linter
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn slop_lint_hairpin_turns_py<'py>(
    py: Python<'py>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let view = build_view(py, source)?;
    findings_to_list(py, &slop_linter::lint_hairpin_turns(&view))
}

#[pyfunction]
pub fn slop_lint_zigzag_patterns_py<'py>(
    py: Python<'py>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let view = build_view(py, source)?;
    findings_to_list(py, &slop_linter::lint_zigzag_patterns(&view))
}

#[pyfunction]
pub fn slop_lint_isolated_vias_py<'py>(
    py: Python<'py>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let view = build_view(py, source)?;
    findings_to_list(py, &slop_linter::lint_isolated_vias(&view))
}

#[pyfunction]
#[pyo3(signature = (source, max_ratio = 1.5))]
pub fn slop_lint_single_net_detours_py<'py>(
    py: Python<'py>,
    source: &Bound<'py, PyAny>,
    max_ratio: f64,
) -> PyResult<Bound<'py, PyList>> {
    let view = build_view(py, source)?;
    findings_to_list(py, &slop_linter::lint_single_net_detours(&view, max_ratio))
}

#[pyfunction]
pub fn slop_lint_all_py<'py>(
    py: Python<'py>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let view = build_view(py, source)?;
    findings_to_list(py, &slop_linter::lint_all(&view))
}

// ---------------------------------------------------------------------------
// quality/via_count
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn via_count_get_component_bboxes_py(
    py: Python<'_>,
    source: &Bound<'_, PyAny>,
    refs: Vec<String>,
) -> PyResult<Vec<(f64, f64, f64, f64)>> {
    let view = build_view(py, source)?;
    Ok(via_count::get_component_bboxes(&view, &refs))
}

#[pyfunction]
pub fn via_count_get_board_bbox_py(
    py: Python<'_>,
    source: &Bound<'_, PyAny>,
) -> PyResult<Option<(f64, f64, f64, f64)>> {
    let view = build_view(py, source)?;
    Ok(via_count::get_board_bbox(&view))
}

#[pyfunction]
pub fn via_count_is_via_in_bbox_py(
    x: f64,
    y: f64,
    bboxes: Vec<(f64, f64, f64, f64)>,
) -> bool {
    via_count::is_via_in_bbox(x, y, &bboxes)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn via_count_is_via_near_board_edge_py(
    vx: f64,
    vy: f64,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    margin_mm: f64,
) -> bool {
    via_count::is_via_near_board_edge(vx, vy, (x_min, y_min, x_max, y_max), margin_mm)
}

#[pyfunction]
pub fn via_count_classify_vias_py(
    py: Python<'_>,
    source: &Bound<'_, PyAny>,
) -> PyResult<(i64, i64, i64, i64)> {
    let view = build_view(py, source)?;
    let counts = via_count::classify_vias(&view);
    Ok((counts.signal, counts.thermal, counts.stitching, counts.total))
}

/// Register every cluster-F export on the extension module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(slop_lint_hairpin_turns_py, m)?)?;
    m.add_function(wrap_pyfunction!(slop_lint_zigzag_patterns_py, m)?)?;
    m.add_function(wrap_pyfunction!(slop_lint_isolated_vias_py, m)?)?;
    m.add_function(wrap_pyfunction!(slop_lint_single_net_detours_py, m)?)?;
    m.add_function(wrap_pyfunction!(slop_lint_all_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_count_get_component_bboxes_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_count_get_board_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_count_is_via_in_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_count_is_via_near_board_edge_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_count_classify_vias_py, m)?)?;
    Ok(())
}

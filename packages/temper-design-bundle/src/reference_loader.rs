//! Reference-loader kernels — Wave 4 Phase 3, candidate 5 (config/reference
//! loaders).
//!
//! Python reference: `temper_placer/io/reference_loader.py`, pinned VERBATIM
//! in `packages/temper-placer/tests/io/_reference_loader_py_oracle.py`
//! (commit `79ab9bd0e`). Only the two pure kernels are migrated here:
//! `compute_design_stats` and `infer_quality_config`.
//!
//! R3-style boundary decision (argued in this crate's VERIFICATION.md): the
//! rest of `reference_loader.py` — `load_reference_pcb` (calls the KiCad
//! parse engine, candidate 3, built in parallel), `filter_components`
//! (numpy fancy indexing + `ParseResult` construction), and
//! `netlist_to_placement_state` (numpy `PlacementState`, a Phase 4/5 surface)
//! — stays Python until those surfaces land. Migrating kernels that read
//! the *parse output* now is sound because `Netlist`/`Net`/`Board` are
//! already Rust pyclasses (candidate 1); the kernels are pure over those
//! objects.
//!
//! Numerical notes:
//! - `round()` is called *back* into CPython (banker's rounding on the exact
//!   binary value — the candidate-6 trap; Rust `f64::round` rounds half away
//!   from zero).
//! - All arithmetic (`w * h`, `total_comp_area += ...`, `total_pins /
//!   n_nets`, `board.width * board.height`) goes through Python's own
//!   operators, so `int`-vs-`float` outcomes are CPython's (a `(1, 1)` int
//!   bounds tuple contributes `int` area, exactly as the oracle).
//! - `str.lower()` / `.upper()` / `.split()` are called back (CPython
//!   lower/upper semantics).

use pyo3::prelude::*;
use pyo3::IntoPyObjectExt;
use pyo3::types::{PyAny, PyDict, PyFloat, PyList, PySet};

/// `builtins.round(value, ndigits)` — CPython's own round (half-to-even).
fn py_round<'py>(
    py: Python<'py>,
    value: &Bound<'py, PyAny>,
    ndigits: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let round_fn = PyModule::import(py, "builtins")?.getattr("round")?;
    round_fn.call1((value, ndigits))
}

/// `builtins.sorted(iterable)` — CPython's own sort.
fn py_sorted<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let sorted_fn = PyModule::import(py, "builtins")?.getattr("sorted")?;
    sorted_fn.call1((value,))
}

/// `compute_design_stats(result)` — stats over a ParseResult-like object.
/// `result.netlist`/`result.board`/`result.warnings` are read duck-typed;
/// the netlist/board are the Rust candidate-1 pyclasses.
#[pyfunction]
#[pyo3(name = "compute_design_stats")]
pub fn compute_design_stats<'py>(
    py: Python<'py>,
    result: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let netlist = result.getattr("netlist")?;
    let board_attr = result.getattr("board")?;
    let has_board = board_attr.is_truthy()?;

    // Component area + footprint types.
    let mut total_comp_area: Bound<'py, PyAny> = PyFloat::new(py, 0.0).into_any();
    let footprint_types = PySet::empty(py)?;
    for entry in netlist.getattr("components")?.try_iter()? {
        let comp = entry?;
        let bounds = comp.getattr("bounds")?;
        let w = bounds.get_item(0)?;
        let h = bounds.get_item(1)?;
        let area = w.mul(&h)?;
        total_comp_area = total_comp_area.add(&area)?;
        // `fp_parts = comp.footprint.split(":")` — CPython str.split.
        let fp = comp.getattr("footprint")?;
        let fp_parts = fp.call_method("split", (":",), None)?;
        let fp_type = if fp_parts.len()? > 0 {
            fp_parts.get_item(fp_parts.len()? - 1)?
        } else {
            fp
        };
        footprint_types.add(fp_type)?;
    }

    // Board area — `board.width * board.height if board else 0.0`.
    let board_area = if has_board {
        let width = board_attr.getattr("width")?;
        let height = board_attr.getattr("height")?;
        width.mul(&height)?
    } else {
        PyFloat::new(py, 0.0).into_any()
    };

    // Net stats.
    let nets = netlist.getattr("nets")?;
    let n_nets = nets.len()?;
    let mut avg_pins: Bound<'py, PyAny> = PyFloat::new(py, 0.0).into_any();
    if n_nets > 0 {
        // `total_pins = sum(len(net.pins) for net in netlist.nets)` — a plain
        // Python int sum (no numpy/pairwise semantics).
        let mut total_pins = 0i64;
        for entry in nets.try_iter()? {
            let net = entry?;
            let pins = net.getattr("pins")?;
            total_pins += pins.len()? as i64;
        }
        avg_pins = total_pins
            .into_py_any(py)?
            .into_bound(py)
            .div(n_nets)?;
    }

    let density = if board_area.gt(0)? {
        // `round(total_comp_area / board_area, 3)` — Python division, Python
        // round.
        let ratio = total_comp_area.div(&board_area)?;
        py_round(py, &ratio, 3)?
    } else {
        0i64.into_py_any(py)?.into_bound(py)
    };

    let stats = PyDict::new(py);
    stats.set_item("n_components", netlist.getattr("n_components")?)?;
    stats.set_item("n_nets", n_nets)?;
    stats.set_item("n_pins_per_net", py_round(py, &avg_pins, 2)?)?;
    if has_board {
        stats.set_item("board_width_mm", board_attr.getattr("width")?)?;
        stats.set_item("board_height_mm", board_attr.getattr("height")?)?;
    } else {
        stats.set_item("board_width_mm", 0i64)?;
        stats.set_item("board_height_mm", 0i64)?;
    }
    stats.set_item("board_area_mm2", py_round(py, &board_area, 1)?)?;
    stats.set_item("component_area_mm2", py_round(py, &total_comp_area, 1)?)?;
    stats.set_item("density", density)?;
    stats.set_item("footprint_types", py_sorted(py, &footprint_types.into_any())?)?;
    stats.set_item("n_warnings", result.getattr("warnings")?.len()?)?;
    Ok(stats.into_any())
}

/// `infer_quality_config(design)` — the thermal/HV/LV classification + gate
/// loop inference, with the oracle's `loops[:3]` cap.
#[pyfunction]
#[pyo3(name = "infer_quality_config")]
pub fn infer_quality_config<'py>(
    py: Python<'py>,
    design: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let thermal = PySet::empty(py)?;
    let hv = PySet::empty(py)?;
    let lv = PySet::empty(py)?;

    const THERMAL_PKGS: [&str; 5] = ["to-247", "to-220", "d2pak", "module", "heatsink"];
    const LV_PKGS: [&str; 5] = ["soic", "qfp", "bga", "qfn", "sot"];

    for entry in design.getattr("netlist")?.getattr("components")?.try_iter()? {
        let comp = entry?;
        let fp_lower: String = comp.getattr("footprint")?.call_method("lower", (), None)?.extract()?;
        let ref_upper: String = comp.getattr("ref")?.call_method("upper", (), None)?.extract()?;
        let bounds = comp.getattr("bounds")?;
        let area = bounds.get_item(0)?.mul(&bounds.get_item(1)?)?;
        let area_gt_100 = area.gt(100)?;

        // Thermal: any package keyword or area > 100.
        let is_thermal = THERMAL_PKGS.iter().any(|pkg| fp_lower.contains(pkg)) || area_gt_100;
        if is_thermal {
            thermal.add(comp.getattr("ref")?)?;
        }
        // HV: (ref prefix and area > 50) or igbt/mosfet in footprint.
        // Operator precedence: `A and B or C or D` == `(A and B) or C or D`.
        let prefix_hv = ref_upper.starts_with("Q")
            || ref_upper.starts_with("D")
            || ref_upper.starts_with("TR")
            || ref_upper.starts_with("U");
        let is_hv = (prefix_hv && area.gt(50)?)
            || fp_lower.contains("igbt")
            || fp_lower.contains("mosfet");
        if is_hv {
            hv.add(comp.getattr("ref")?)?;
        }
        // LV: any package keyword and area < 100.
        let is_lv = LV_PKGS.iter().any(|pkg| fp_lower.contains(pkg)) && area.lt(100)?;
        if is_lv {
            lv.add(comp.getattr("ref")?)?;
        }
    }

    // Infer loops from gate-drive nets (first 3 pins of each qualifying net,
    // then cap the whole list at 3).
    let mut loops: Vec<Bound<'py, PyAny>> = Vec::new();
    'nets: for entry in design.getattr("netlist")?.getattr("nets")?.try_iter()? {
        let net = entry?;
        let net_upper: String = net.getattr("name")?.call_method("upper", (), None)?.extract()?;
        let pins = net.getattr("pins")?;
        let qualifies = (net_upper.contains("GATE") || net_upper.contains("DRV") || net_upper.contains("DRIVE"))
            && pins.len()? >= 2;
        if !qualifies {
            continue;
        }
        let loop_refs = PyList::empty(py);
        for pin in pins.try_iter()?.take(3) {
            let pin = pin?;
            loop_refs.append(pin.get_item(0)?)?;
        }
        if loop_refs.len() >= 2 {
            loops.push(loop_refs.into_any());
            if loops.len() >= 3 {
                break 'nets;
            }
        }
    }
    let loop_components = PyList::new(py, &loops)?;

    let cfg = PyDict::new(py);
    cfg.set_item("thermal_components", thermal)?;
    cfg.set_item("hv_components", hv)?;
    cfg.set_item("lv_components", lv)?;
    cfg.set_item("zone_assignments", PyDict::new(py))?;
    cfg.set_item("loop_components", loop_components)?;
    cfg.set_item("min_hv_lv_clearance", 4.0f64)?;
    Ok(cfg.into_any())
}

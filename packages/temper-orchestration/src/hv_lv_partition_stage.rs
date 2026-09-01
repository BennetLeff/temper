// The D7 `HvLvPartitionStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D7): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/hv_lv_partition.py`.
//
// The run() orchestration moves to Rust: the config load + enabled/board/
// netlist guards, the `_rules_by_net` reading (inlined -- the D6
// `_get_component_positions` precedent; the method is a state-dependent
// duck-typed read that cannot be called back without the Python state, and
// the differential pins the two agree), the `rules_marshalled` /
// `components_nets` marshalling, the design-bundle `hv_lv_classify` /
// `hv_lv_area_check` kernel calls, the decision dispatch (dual / skip_empty
// / skip_zero warnings + identity returns, the below-creepage width warning,
// the fallback warning + identity return), the `PartitionError` raise
// decisions and the `component_domain_map` / `routing_corridors` /
// `domain_regions` write. The classification / area kernels stay
// single-source in `temper_design_bundle_python.hv_lv_partition`; the
// pydantic `load_guard_config`, the shapely `_outline` +
// `compute_guard_strip` GEOS surface and the `_nets` / `_area` duck-typed
// readers stay Python and are CALLED BACK from the module (the D5/D6
// mixin-helper boundary).
//
// The `PartitionError` exception class stays Python. The two raise points
// construct the ORIGINAL exception through the module class (its
// `__init__` renders the `{:.2f}` message via CPython), so the message is
// bit-exact by identity and `pytest.raises(PartitionError)` sees the real
// class: `run_guarded` threads the raw `PyErr` (the D3
// `FenceViolation`/`ConfigError` pattern) instead of converting to a
// `StageError`.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::pyerr_stage;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "hv_lv_partition";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.hv_lv_partition";

/// The HV/LV partition stage: netlist + config + board -> the
/// `component_domain_map` / `routing_corridors` / `domain_regions` writes,
/// raising `PartitionError` on the geometry / insufficient-area paths.
#[derive(Debug, Clone, Default)]
pub struct HvLvPartitionStage;

#[cfg(feature = "python")]
impl Stage<BoardState> for HvLvPartitionStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        self.run_guarded(state)
            .map_err(|e| pyerr_stage(STAGE_NAME, e))
    }
}

#[cfg(feature = "python")]
impl HvLvPartitionStage {
    /// Panic-guarded `run_inner`: a Rust panic becomes a Python RuntimeError;
    /// the inner result carries the ORIGINAL Python `PyErr` so the
    /// `PartitionError` raise paths propagate by TYPE through the FFI wrapper
    /// (the D3 `run_guarded` pattern).
    fn run_guarded(&self, state: BoardState) -> Result<BoardState, PyErr> {
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.run_inner(state))) {
            Ok(result) => result,
            Err(_) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
                "{STAGE_NAME}: stage panicked"
            ))),
        }
    }

    fn run_inner(&self, state: BoardState) -> Result<BoardState, PyErr> {
        Python::attach(|py| {
            let module = py.import("temper_placer.deterministic.stages.hv_lv_partition")?;

            // `cfg = load_guard_config(state.config)` -- pydantic, called back.
            let config_obj: Py<PyAny> = match &state.config {
                Some(c) => c.clone_ref(py),
                None => py.None(),
            };
            let cfg = module.call_method1("load_guard_config", (config_obj,))?;
            let enabled: bool = cfg.getattr("enabled")?.extract()?;
            let width_mm: Option<f64> = cfg.getattr("width_mm")?.extract()?;
            let fallback_to_unconstrained: bool =
                cfg.getattr("fallback_to_unconstrained")?.extract()?;

            // `if not cfg.enabled or state.board is None or state.netlist is
            // None: return state`.
            if !enabled || state.board.is_none() || state.netlist.is_none() {
                return Ok(state);
            }
            let board = state
                .board
                .as_ref()
                .map(|b| b.bind(py).clone())
                .unwrap_or_else(|| py.None().into_bound(py));
            let netlist = state
                .netlist
                .as_ref()
                .map(|n| n.bind(py).clone())
                .unwrap_or_else(|| py.None().into_bound(py));

            // `rules = _rules_by_net(state)` -- inlined duck-typed read.
            let rules = rules_by_net(py, &state)?;

            // `rules_marshalled = {name: (safety_category or "", float(
            // creepage_mm or 0.0)) for name, r in rules.items()}`.
            let rules_marshalled = PyDict::new(py);
            let builtins_float = py.import("builtins")?.getattr("float")?;
            for item in rules.call_method0("items")?.try_iter()? {
                let item = item?;
                let name = item.get_item(0)?;
                let r = item.get_item(1)?;
                let cat_raw = r.getattr("safety_category")?;
                let cat = if cat_raw.is_truthy()? {
                    cat_raw
                } else {
                    PyString::new(py, "").into_any()
                };
                let creep_raw = r.getattr("creepage_mm")?;
                let creep_src = if creep_raw.is_truthy()? {
                    creep_raw
                } else {
                    0.0f64.into_pyobject(py)?.into_any()
                };
                let creep = builtins_float.call1((creep_src,))?;
                let tup = PyTuple::new(py, [cat, creep])?;
                rules_marshalled.set_item(&name, tup)?;
            }

            // `components_nets = [(c.ref, _nets(state.netlist, c.ref)) for c
            // in state.netlist.components]` -- `_nets` called back.
            let components_nets = PyList::empty(py);
            for component in netlist.getattr("components")?.try_iter()? {
                let component = component?;
                let ref_ = component.getattr("ref")?;
                let nets = module.call_method1("_nets", (&netlist, &ref_))?;
                let tup = PyTuple::new(py, [ref_, nets])?;
                components_nets.append(tup)?;
            }

            // `decision, hv, lv, creepage, width, dual =
            // hv_lv_classify(components_nets, rules_marshalled,
            // cfg.width_mm)` -- the design-bundle kernel.
            let tdb_partition = py
                .import("temper_design_bundle_python")?
                .getattr("hv_lv_partition")?;
            let classify = tdb_partition.call_method1(
                "hv_lv_classify",
                (&components_nets, &rules_marshalled, width_mm),
            )?;
            let decision: String = classify.get_item(0)?.extract()?;
            let hv: Vec<String> = classify.get_item(1)?.extract()?;
            let lv: Vec<String> = classify.get_item(2)?.extract()?;
            let creepage: f64 = classify.get_item(3)?.extract()?;
            let width: f64 = classify.get_item(4)?.extract()?;
            let dual: Vec<String> = classify.get_item(5)?.extract()?;

            // `for ref in dual: logger.warning("dual-domain %s -> LV bucket", ref)`.
            for ref_ in &dual {
                let msg = d6_util::py_format(
                    py,
                    "dual-domain {} -> LV bucket",
                    &[PyString::new(py, ref_).into_any()],
                )?;
                d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
            }

            if decision == "skip_empty" {
                let msg = d6_util::py_format(
                    py,
                    "empty HV/LV bucket (hv={} lv={}); skipping",
                    &[
                        hv.len().into_pyobject(py)?.into_any(),
                        lv.len().into_pyobject(py)?.into_any(),
                    ],
                )?;
                d6_util::log_msg(py, LOGGER_NAME, "info", &msg)?;
                return Ok(state);
            }
            if decision == "skip_zero" {
                return Ok(state);
            }

            // `if cfg.width_mm is not None and cfg.width_mm < creepage:
            // logger.warning(...)`.
            if let Some(w) = width_mm
                && w < creepage
            {
                let msg = d6_util::py_format(
                    py,
                    "hv_lv_guard_strip.width_mm={} below creepage {}, using creepage",
                    &[
                        w.into_pyobject(py)?.into_any(),
                        creepage.into_pyobject(py)?.into_any(),
                    ],
                )?;
                d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
            }

            // `outline = _outline(state.board)` -- shapely, called back.
            let outline = module.call_method1("_outline", (&board,))?;
            let exterior = outline.getattr("exterior")?;
            let bad_outline =
                exterior.is_none() || !exterior.getattr("is_closed")?.extract::<bool>()?;
            if bad_outline {
                return Err(partition_geometry_error(&module));
            }

            // `try: hv_poly, lv_poly, corridor = compute_guard_strip(outline,
            // width) except ValueError as exc: raise PartitionError(...)`.
            let guard_strip = py.import("temper_placer.deterministic.geometry.guard_strip")?;
            let strip = guard_strip.call_method1("compute_guard_strip", (&outline, width));
            let (hv_poly, lv_poly, corridor) = match strip {
                Ok(r) => (r.get_item(0)?, r.get_item(1)?, r.get_item(2)?),
                Err(e) if e.is_instance_of::<pyo3::exceptions::PyValueError>(py) => {
                    return Err(partition_geometry_error(&module));
                }
                Err(e) => return Err(e),
            };

            // `comp = {c.ref: c for c in state.netlist.components}`.
            let comp = PyDict::new(py);
            for c in netlist.getattr("components")?.try_iter()? {
                let c = c?;
                comp.set_item(c.getattr("ref")?, &c)?;
            }

            // `areas = {ref: _area(comp[ref]) for ref in hv + lv}` -- `_area`
            // called back.
            let areas = PyDict::new(py);
            for ref_ in hv.iter().chain(lv.iter()) {
                let c = match comp.get_item(ref_)? {
                    Some(c) => c,
                    None => continue, // unreachable: hv/lv refs come from the components
                };
                let a = module.call_method1("_area", (&c,))?;
                areas.set_item(ref_, a)?;
            }

            // `hv_lv_area_check(hv, lv, areas, float(hv_poly.area),
            // bool(hv_poly.is_empty), ...)`.
            let hv_list = PyList::new(py, hv.iter().map(|s| PyString::new(py, s)))?;
            let lv_list = PyList::new(py, lv.iter().map(|s| PyString::new(py, s)))?;
            let hv_region_area: f64 = hv_poly.getattr("area")?.extract()?;
            let hv_region_empty: bool = hv_poly.getattr("is_empty")?.extract()?;
            let lv_region_area: f64 = lv_poly.getattr("area")?.extract()?;
            let lv_region_empty: bool = lv_poly.getattr("is_empty")?.extract()?;
            let area_check = tdb_partition.call_method1(
                "hv_lv_area_check",
                (
                    &hv_list,
                    &lv_list,
                    &areas,
                    hv_region_area,
                    hv_region_empty,
                    lv_region_area,
                    lv_region_empty,
                    fallback_to_unconstrained,
                ),
            )?;
            let outcome: String = area_check.get_item(0)?.extract()?;
            let bucket: Option<String> = area_check.get_item(1)?.extract()?;
            let largest: Option<String> = area_check.get_item(2)?.extract()?;
            let region_area: Option<f64> = area_check.get_item(3)?.extract()?;
            let required_area: Option<f64> = area_check.get_item(4)?.extract()?;

            if outcome == "fallback" {
                let msg = d6_util::py_format(
                    py,
                    "insufficient {} bucket area: {} requires {:.2f}mm^2, region has {:.2f}mm^2",
                    &[
                        PyString::new(py, bucket.as_deref().unwrap_or("")).into_any(),
                        PyString::new(py, largest.as_deref().unwrap_or("")).into_any(),
                        required_area.unwrap_or(0.0).into_pyobject(py)?.into_any(),
                        region_area.unwrap_or(0.0).into_pyobject(py)?.into_any(),
                    ],
                )?;
                d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
                return Ok(state);
            }
            if outcome == "raise" {
                let exc = module.getattr("PartitionError")?.call1((
                    bucket.as_deref().unwrap_or(""),
                    largest.as_deref().unwrap_or(""),
                    region_area.unwrap_or(0.0),
                    required_area.unwrap_or(0.0),
                ))?;
                return Err(PyErr::from_value(exc));
            }

            // `domain = [(r, "HV_edge") for r in hv] + [(r, "LV_interior")
            // for r in lv]`; `frozenset(domain)`.
            let domain = PyList::empty(py);
            for r in &hv {
                domain.append(PyTuple::new(
                    py,
                    [
                        PyString::new(py, r).into_any(),
                        PyString::new(py, "HV_edge").into_any(),
                    ],
                )?)?;
            }
            for r in &lv {
                domain.append(PyTuple::new(
                    py,
                    [
                        PyString::new(py, r).into_any(),
                        PyString::new(py, "LV_interior").into_any(),
                    ],
                )?)?;
            }
            let frozenset_ = py.import("builtins")?.getattr("frozenset")?;
            let fs = frozenset_.call1((domain,))?;
            let corridors = PyTuple::new(py, [corridor])?;
            let regions = PyTuple::new(py, [hv_poly, lv_poly])?;

            let mut new_state = state;
            new_state.component_domain_map = Some(fs.into_any().unbind());
            new_state.routing_corridors = Some(corridors.into_any().unbind());
            new_state.domain_regions = Some(regions.into_any().unbind());
            Ok(new_state)
        })
    }
}

#[cfg(feature = "python")]
/// `raise PartitionError("geometry", "outline", 0.0, 0.0)` -- constructed
/// through the Python class so the message is bit-exact by identity.
fn partition_geometry_error(module: &Bound<'_, PyAny>) -> PyErr {
    match module
        .getattr("PartitionError")
        .and_then(|cls| cls.call1(("geometry", "outline", 0.0f64, 0.0f64)))
    {
        Ok(exc) => PyErr::from_value(exc),
        Err(e) => e,
    }
}

#[cfg(feature = "python")]
/// `_rules_by_net(state)` inlined: the `state.drc_oracle.design_rules`
/// net-class / net-class-assignment / `get_rules_for_net` resolution over
/// `state.netlist.nets`. The differential pins this against the Python
/// method.
fn rules_by_net<'py>(py: Python<'py>, state: &BoardState) -> PyResult<Bound<'py, PyAny>> {
    let out = PyDict::new(py);
    let dr = match &state.drc_oracle {
        Some(o) => match o.bind(py).getattr("design_rules") {
            Ok(v) if !v.is_none() => v,
            _ => return Ok(out.into_any()),
        },
        None => return Ok(out.into_any()),
    };
    let classes = attr_or_empty(py, &dr, "net_classes")?;
    let assigns = attr_or_empty(py, &dr, "net_class_assignments")?;
    let gr = dr.getattr("get_rules_for_net").ok();
    let nets = match &state.netlist {
        Some(nl) => nl.bind(py).getattr("nets")?,
        None => return Ok(out.into_any()),
    };
    for net in nets.try_iter()? {
        let net = net?;
        let name = net.getattr("name")?;
        if !name.is_truthy()? {
            continue;
        }
        let nc = net.getattr("net_class")?;
        if nc.is_truthy()? && classes.contains(&nc)? {
            let rules = classes.get_item(&nc)?;
            out.set_item(&name, rules)?;
        } else if assigns.contains(&name)? {
            let cls = assigns.get_item(&name)?;
            if classes.contains(&cls)? {
                out.set_item(&name, classes.get_item(&cls)?)?;
            }
        } else if let Some(gr) = &gr
            && gr.is_callable()
        {
            let r = gr.call1((&name, &nc))?;
            out.set_item(&name, r)?;
        }
    }
    Ok(out.into_any())
}

#[cfg(feature = "python")]
/// `getattr(obj, name, {}) or {}` -- missing or falsy -> a fresh empty dict.
fn attr_or_empty<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let v = match obj.getattr(name) {
        Ok(v) => v,
        Err(_) => PyDict::new(py).into_any(),
    };
    if v.is_truthy()? {
        Ok(v)
    } else {
        Ok(PyDict::new(py).into_any())
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_hv_lv_partition(state)`.
#[pyfunction]
pub fn run_hv_lv_partition(py: Python<'_>, state: Py<PyAny>) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}")))?;
    let stage = HvLvPartitionStage;
    // `run_guarded` threads the raw `PyErr`: the `PartitionError` raise
    // paths propagate by TYPE (the D3 pattern); a Rust panic becomes a
    // RuntimeError.
    let out = stage.run_guarded(rust_state)?;
    crate::d1_bridge::to_python(
        py,
        state.bind(py),
        &out,
        &[
            "component_domain_map",
            "routing_corridors",
            "domain_regions",
        ],
    )
}

// The U4 preflight stage of the Rust Orchestration Engine plan
// (2026-08-09-001): wrap the Wave-4 preflight compute (the
// `component_area_ratio` / `proximity_rule_impossible` /
// `zone_over_capacity` / `loop_area_violation` /
// `isolation_barrier_too_large` kernels in `feasibility.rs`) as a
// `Stage<BoardState>` implementor.
//
// The stage mirrors `pipeline/preflight.py::PreflightChecker.run` for the
// five kernel-backed checks. It reads `board` from `BoardState.board`,
// `netlist` from `BoardState.netlist` and the constraints object
// (`component_groups` / `critical_loops`) from `BoardState.config` (the
// deterministic pipeline's configuration block — the same carrier the
// preflight checks' constraint surface lives on), delegates each check's
// compute to the feasibility kernels, and writes a plain-data report dict
// (the PreflightReport shape: `checks` + `overall` + `total_time_ms`) back
// into `BoardState.violations`. The report is plain data because the
// Python `PreflightCheck`/`PreflightReport` object construction is
// marshalling that the Phase-C Python `run()` shim performs (the plan's
// boundary: Rust stages write typed results, the Python layer converts).
//
// The Python `run()` returns the report even when checks FAIL — the FAIL is
// IN the report (`overall`), it is not a raised error. The stage matches
// that: it returns `Ok(state)` with the report written; the plan's
// `StageErrorKind::Infeasible` sketch for "the preflight FAIL result" is NOT
// adopted because it would diverge from the module's actual semantics
// (recorded in VERIFICATION.md).
//
// The BoardState field mapping is a Phase-C-pending placeholder contract
// (recorded in VERIFICATION.md): `config` is the constraints carrier,
// `violations` the report carrier. Field types are NOT tightened (D2).

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::time::Instant;

#[cfg(feature = "python")]
use pyo3::exceptions::PyAttributeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PyString};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::derivation_stage::{missing_field, pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::feasibility;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

/// The preflight stage: board + netlist + constraints -> preflight report.
#[derive(Debug, Clone, Copy, Default)]
pub struct PreflightStage;

#[cfg(feature = "python")]
impl Stage<BoardState> for PreflightStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("preflight")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("preflight", || {
            Python::attach(|py| {
                let board = state
                    .board
                    .as_ref()
                    .ok_or_else(|| missing_field("preflight", "board"))?;
                let netlist = state
                    .netlist
                    .as_ref()
                    .ok_or_else(|| missing_field("preflight", "netlist"))?;
                let constraints = state
                    .config
                    .as_ref()
                    .ok_or_else(|| missing_field("preflight", "config"))?;

                let start = Instant::now();
                let mut checks: Vec<Py<PyAny>> = Vec::new();
                let to_stage = |e: PyErr| pyerr_stage("preflight", e);
                checks.push(component_area_check(py, board.bind(py), netlist.bind(py)).map_err(to_stage)?);
                checks.push(
                    constraint_satisfiability_check(py, netlist.bind(py), constraints.bind(py))
                        .map_err(to_stage)?,
                );
                checks.push(zone_capacity_check(py, board.bind(py), netlist.bind(py)).map_err(to_stage)?);
                checks.push(
                    loop_area_feasibility_check(py, netlist.bind(py), constraints.bind(py))
                        .map_err(to_stage)?,
                );
                checks.push(
                    isolation_feasibility_check(py, board.bind(py), netlist.bind(py))
                        .map_err(to_stage)?,
                );
                let total_time_ms = start.elapsed().as_secs_f64() * 1000.0;

                let report = build_report(py, checks, total_time_ms).map_err(to_stage)?;
                let mut new_state = state.clone();
                new_state.violations = Some(report);
                Ok(new_state)
            })
        })
    }
}

// ---------------------------------------------------------------------------
// the five kernel-backed checks (each returns a report-check dict)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_check_component_area`: the `component_area_ratio` kernel + the Python
/// message f-string (`Fill ratio {ratio:.1%}`, rendered by calling CPython's
/// `format()` — parity by identity).
fn component_area_check(
    py: Python<'_>,
    board: &Bound<'_, PyAny>,
    netlist: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let start = Instant::now();
    let comp_dims = component_dims(py, netlist)?;
    let keepout_dims = keepout_dims(py, board)?;
    let width: f64 = board.getattr("width")?.extract()?;
    let height: f64 = board.getattr("height")?.extract()?;
    let (ratio, code) = feasibility::component_area_ratio(comp_dims, width, height, keepout_dims);
    let result = match code {
        2 => "fail",
        1 => "warn",
        _ => "pass",
    };
    let ratio_str = py_format(py, ratio, ".1%")?;
    let message = format!("Fill ratio {ratio_str}");
    check_dict(
        py,
        "Component Area",
        result,
        &message,
        None,
        start.elapsed().as_secs_f64() * 1000.0,
    )
}

#[cfg(feature = "python")]
/// `_check_constraint_satisfiability`: the `proximity_rule_impossible`
/// kernel + the Python message/issue f-strings (CPython `str()` /
/// `format()` for parity by identity).
fn constraint_satisfiability_check(
    py: Python<'_>,
    netlist: &Bound<'_, PyAny>,
    constraints: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let start = Instant::now();
    let comp_map = PyDict::new(py);
    for comp in as_vec(&netlist.getattr("components")?)? {
        comp_map.set_item(comp.bind(py).getattr("ref")?, &comp)?;
    }

    let mut impossible: Vec<String> = Vec::new();
    if let Some(groups) = opt_getattr(py, constraints, "component_groups")? {
        for group in as_vec(groups.bind(py))? {
            let rules = group.bind(py).getattr("proximity_rules")?;
            for rule in as_vec(&rules)? {
                let a = opt_getattr_default(py, rule.bind(py), "component_a", py_string(py, ""))?;
                let b = opt_getattr_default(py, rule.bind(py), "component_b", py_string(py, ""))?;
                let max_d = opt_getattr_default(py, rule.bind(py), "max_distance_mm", py_float(py, f64::INFINITY))?;
                let a_in = comp_map.get_item(a.bind(py))?;
                let b_in = comp_map.get_item(b.bind(py))?;
                if let (Some(ca), Some(cb)) = (a_in, b_in) {
                    let min_d;
                    let imp;
                    {
                        let min_d_;
                        let imp_;
                        (min_d_, imp_) = feasibility::proximity_rule_impossible(
                            ca.getattr("width")?.extract()?,
                            ca.getattr("height")?.extract()?,
                            cb.getattr("width")?.extract()?,
                            cb.getattr("height")?.extract()?,
                            max_d.bind(py).extract::<f64>()?,
                        );
                        min_d = min_d_;
                        imp = imp_;
                    }
                    if imp {
                        let max_d_str = py_str(max_d.bind(py))?;
                        let min_d_str = py_format(py, min_d, ".1f")?;
                        impossible.push(format!(
                            "{}-{}: max {}mm < min {}mm",
                            py_str(a.bind(py))?,
                            py_str(b.bind(py))?,
                            max_d_str,
                            min_d_str
                        ));
                    }
                }
            }
        }
    }

    let result = if impossible.is_empty() { "pass" } else { "fail" };
    let message = if impossible.is_empty() {
        "No issues".to_string()
    } else {
        format!("Found {} issues", impossible.len())
    };
    let details = PyDict::new(py);
    details.set_item("impossible", impossible)?;
    check_dict(
        py,
        "Constraint Satisfiability",
        result,
        &message,
        Some(details.into_any().unbind()),
        start.elapsed().as_secs_f64() * 1000.0,
    )
}

#[cfg(feature = "python")]
/// `_check_zone_capacity`: the `zone_over_capacity` kernel per zone.
fn zone_capacity_check(
    py: Python<'_>,
    board: &Bound<'_, PyAny>,
    netlist: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let start = Instant::now();
    let zones = opt_getattr(py, board, "zones")?;
    let Some(zones) = zones else {
        return check_dict(py, "Zone Capacity", "pass", "No zones", None,
                          start.elapsed().as_secs_f64() * 1000.0);
    };
    if !zones.bind(py).is_truthy()? {
        return check_dict(py, "Zone Capacity", "pass", "No zones", None,
                          start.elapsed().as_secs_f64() * 1000.0);
    }
    let mut violations: Vec<String> = Vec::new();
    for zone in as_vec(zones.bind(py))? {
        let content_dims = zone_content_dims(py, netlist, zone.bind(py))?;
        let over = feasibility::zone_over_capacity(
            zone.bind(py).getattr("width")?.extract()?,
            zone.bind(py).getattr("height")?.extract()?,
            content_dims,
        );
        if over {
            violations.push(format!(
                "Zone {} over cap",
                py_str(&zone.bind(py).getattr("name")?)?
            ));
        }
    }
    let result = if violations.is_empty() { "pass" } else { "fail" };
    let message = violations
        .first()
        .cloned()
        .unwrap_or_else(|| "OK".to_string());
    check_dict(
        py,
        "Zone Capacity",
        result,
        &message,
        None,
        start.elapsed().as_secs_f64() * 1000.0,
    )
}

#[cfg(feature = "python")]
/// `_check_loop_area_feasibility`: the `loop_area_violation` kernel per
/// critical loop (WARN class, like the Python module).
fn loop_area_feasibility_check(
    py: Python<'_>,
    netlist: &Bound<'_, PyAny>,
    constraints: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let start = Instant::now();
    let comp_map = PyDict::new(py);
    for comp in as_vec(&netlist.getattr("components")?)? {
        comp_map.set_item(comp.bind(py).getattr("ref")?, &comp)?;
    }

    let mut violations: Vec<String> = Vec::new();
    let loops = opt_getattr_default(py, constraints, "critical_loops", py_list(py))?;
    for loop_ in as_vec(loops.bind(py))? {
        let max_a = opt_getattr_default(py, loop_.bind(py), "max_area_mm2", py_float(py, f64::INFINITY))?;
        // `pins` truthy -> refs from pin tuples; elif `nets` truthy ->
        // skip (no pin info). hasattr semantics via opt_getattr.
        let pins = opt_getattr(py, loop_.bind(py), "pins")?;
        let mut refs: Vec<Py<PyAny>> = Vec::new();
        match pins {
            Some(p) if p.bind(py).is_truthy()? => {
                for pin in as_vec(p.bind(py))? {
                    refs.push(pin.bind(py).get_item(0)?.unbind());
                }
            }
            Some(_) => {}
            None => {
                let nets_truthy = match opt_getattr(py, loop_.bind(py), "nets")? {
                    Some(n) => n.bind(py).is_truthy()?,
                    None => false,
                };
                if nets_truthy {
                    continue;
                }
            }
        }
        if refs.is_empty() {
            continue;
        }
        let content_dims = ref_content_dims(py, &comp_map, &refs)?;
        let truthy = max_a.bind(py).is_truthy()?;
        let max_a_f: f64 = if truthy {
            max_a.bind(py).extract()?
        } else {
            0.0
        };
        if feasibility::loop_area_violation(max_a_f, truthy, content_dims) {
            let name = opt_getattr_default(py, loop_.bind(py), "name", py_string(py, "unknown"))?;
            violations.push(format!(
                "Loop {} too small",
                py_str(name.bind(py))?
            ));
        }
    }
    let result = if violations.is_empty() { "pass" } else { "warn" };
    let message = violations
        .first()
        .cloned()
        .unwrap_or_else(|| "OK".to_string());
    check_dict(
        py,
        "Loop Area Feasibility",
        result,
        &message,
        None,
        start.elapsed().as_secs_f64() * 1000.0,
    )
}

#[cfg(feature = "python")]
/// `_check_isolation_feasibility`: the `isolation_barrier_too_large` kernel
/// behind the HV-present gate.
fn isolation_feasibility_check(
    py: Python<'_>,
    board: &Bound<'_, PyAny>,
    netlist: &Bound<'_, PyAny>,
) -> PyResult<Py<PyAny>> {
    let start = Instant::now();
    let iso = 6.5_f64;
    let components = as_vec(&netlist.getattr("components")?)?;
    let mut hv = 0_usize;
    for comp in &components {
        let net_class = opt_getattr_default(py, comp.bind(py), "net_class", py_string(py, ""))?;
        if net_class.bind(py).eq(PyString::new(py, "HighVoltage").into_any())? {
            hv += 1;
        }
    }
    if hv > 0 {
        let comp_dims: Vec<(f64, f64)> = components
            .iter()
            .map(|c| -> PyResult<(f64, f64)> {
                Ok((
                    c.bind(py).getattr("width")?.extract()?,
                    c.bind(py).getattr("height")?.extract()?,
                ))
            })
            .collect::<PyResult<_>>()?;
        let width: f64 = board.getattr("width")?.extract()?;
        let height: f64 = board.getattr("height")?.extract()?;
        if feasibility::isolation_barrier_too_large(comp_dims, width, height, iso) {
            return check_dict(
                py,
                "Isolation Feasibility",
                "fail",
                "Barrier too large",
                None,
                start.elapsed().as_secs_f64() * 1000.0,
            );
        }
    }
    check_dict(
        py,
        "Isolation Feasibility",
        "pass",
        "Feasible",
        None,
        start.elapsed().as_secs_f64() * 1000.0,
    )
}

// ---------------------------------------------------------------------------
// marshalling helpers (Python-object semantics preserved by identity)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Build a check dict: `{name, result, message, details, time_ms}`.
fn check_dict(
    py: Python<'_>,
    name: &str,
    result: &str,
    message: &str,
    details: Option<Py<PyAny>>,
    time_ms: f64,
) -> PyResult<Py<PyAny>> {
    let check = PyDict::new(py);
    check.set_item("name", name)?;
    check.set_item("result", result)?;
    check.set_item("message", message)?;
    match details {
        Some(d) => check.set_item("details", d)?,
        None => check.set_item("details", py.None())?,
    }
    check.set_item("time_ms", time_ms)?;
    Ok(check.into_any().unbind())
}

#[cfg(feature = "python")]
/// Assemble the PreflightReport-shaped dict and compute the overall verdict
/// (FAIL if any FAIL, elif any WARN -> WARN, else PASS).
fn build_report(py: Python<'_>, checks: Vec<Py<PyAny>>, total_time_ms: f64) -> PyResult<Py<PyAny>> {
    let checks_list = PyList::empty(py);
    let mut overall = "pass";
    for check in &checks {
        let result: String = check.bind(py).get_item("result")?.extract()?;
        if result == "fail" {
            overall = "fail";
        } else if overall == "pass" && result == "warn" {
            overall = "warn";
        }
        checks_list.append(check)?;
    }
    let report = PyDict::new(py);
    report.set_item("checks", checks_list)?;
    report.set_item("overall", overall)?;
    report.set_item("total_time_ms", total_time_ms)?;
    Ok(report.into_any().unbind())
}

#[cfg(feature = "python")]
/// All component (width, height) dims, in netlist order.
fn component_dims(py: Python<'_>, netlist: &Bound<'_, PyAny>) -> PyResult<Vec<(f64, f64)>> {
    let components = as_vec(&netlist.getattr("components")?)?;
    components
        .iter()
        .map(|c| -> PyResult<(f64, f64)> {
            Ok((
                c.bind(py).getattr("width")?.extract()?,
                c.bind(py).getattr("height")?.extract()?,
            ))
        })
        .collect()
}

#[cfg(feature = "python")]
/// Length-4 keepout dims (the `len(k) == 4` filter stays here — Python
/// object marshalling).
fn keepout_dims(py: Python<'_>, board: &Bound<'_, PyAny>) -> PyResult<Vec<(f64, f64)>> {
    let keepouts = opt_getattr_default(py, board, "keepouts", py_list(py))?;
    let mut out = Vec::new();
    for k in as_vec(keepouts.bind(py))? {
        let kb = k.bind(py);
        if kb.len()? == 4 {
            out.push((kb.get_item(2)?.extract()?, kb.get_item(3)?.extract()?));
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// Component dims whose zone attribute equals `zone`'s name (the Python
/// `getattr(c, "zone", "") == zone.name` filter).
fn zone_content_dims(
    py: Python<'_>,
    netlist: &Bound<'_, PyAny>,
    zone: &Bound<'_, PyAny>,
) -> PyResult<Vec<(f64, f64)>> {
    let zone_name = zone.getattr("name")?;
    let mut out = Vec::new();
    for comp in as_vec(&netlist.getattr("components")?)? {
        let comp_zone = opt_getattr_default(py, comp.bind(py), "zone", py_string(py, ""))?;
        if comp_zone.bind(py).eq(&zone_name)? {
            out.push((
                comp.bind(py).getattr("width")?.extract()?,
                comp.bind(py).getattr("height")?.extract()?,
            ));
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// Component dims for refs present in the comp map (the Python
/// `[comp_map[r] for r in refs if r in comp_map]` filter).
fn ref_content_dims(
    py: Python<'_>,
    comp_map: &Bound<'_, PyDict>,
    refs: &[Py<PyAny>],
) -> PyResult<Vec<(f64, f64)>> {
    let mut out = Vec::new();
    for r in refs {
        if let Some(comp) = comp_map.get_item(r.bind(py))? {
            out.push((
                comp.getattr("width")?.extract()?,
                comp.getattr("height")?.extract()?,
            ));
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// Python iterable -> Vec of owned objects.
fn as_vec(obj: &Bound<'_, PyAny>) -> PyResult<Vec<Py<PyAny>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(item?.unbind());
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `hasattr`-flavoured getattr: `None` when the attribute is missing.
fn opt_getattr<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Option<Py<PyAny>>> {
    match obj.getattr(name) {
        Ok(v) => Ok(Some(v.unbind())),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(None),
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
/// `getattr(obj, name, default)` — the Python defaulting.
fn opt_getattr_default<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    match obj.getattr(name) {
        Ok(v) => Ok(v.unbind()),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(default),
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
fn py_string(py: Python<'_>, s: &str) -> Py<PyAny> {
    PyString::new(py, s).into_any().unbind()
}

#[cfg(feature = "python")]
fn py_float(py: Python<'_>, f: f64) -> Py<PyAny> {
    PyFloat::new(py, f).into_any().unbind()
}

#[cfg(feature = "python")]
/// CPython `str(value)` — the f-string `{value}` rendering.
fn py_str(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.str()?.extract::<String>()
}

#[cfg(feature = "python")]
/// CPython `format(value, spec)` — the exact `f"{value:.1%}"` / `:.1f`
/// rendering (David-Gay semantics that Rust's `{:.N}` does not reproduce).
fn py_format(py: Python<'_>, value: f64, spec: &str) -> PyResult<String> {
    let builtins = py.import("builtins")?;
    builtins
        .getattr("format")?
        .call1((value, spec))?
        .extract::<String>()
}

#[cfg(feature = "python")]
fn py_list(py: Python<'_>) -> Py<PyAny> {
    PyList::empty(py).into_any().unbind()
}

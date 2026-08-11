// The D6 `ConnectivityValidationStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D6): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/connectivity_validation.py`.
//
// The whole run() orchestration moves to Rust: the no-oracle guard, the
// drc-oracle geometry extraction, the per-net grouping (insertion order =
// first-seen net order), the plane-net / empty-net / NoNet skips, the
// `_validate_net_connectivity` marshalling + kernel call, the
// `ConnectivityViolation` construction, the `_log_summary` counting (descending
// count sort, ties in first-seen type order) and the `connectivity_violations`
// write. The `ConnectivityValidationError` raise decision (message text) is the
// migrated orchestration; the exception class stays Python (the shim raises it).
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the drc-oracle `.geometry` (pads/tracks/vias) call-back,
// - the `connectivity_validate_net_py` UnionFind kernel in temper-drc-rs,
// - the `ConnectivityViolation` dataclass and the router_v6 `Point` class,
// - `logging` for the summary lines.

use std::borrow::Cow;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::board_state::BoardState;
use crate::d6_util;
use crate::derivation_stage::stage_guard;
use crate::stage::{Stage, StageError, StageErrorKind};

const STAGE_NAME: &str = "connectivity_validation";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.connectivity_validation";

/// A fresh `{"pads": [], "tracks": [], "vias": []}` per-net sub-dict (the
/// oracle's grouping value).
fn empty_sub<'py>(py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    let d = PyDict::new(py);
    d.set_item("pads", PyList::empty(py))?;
    d.set_item("tracks", PyList::empty(py))?;
    d.set_item("vias", PyList::empty(py))?;
    Ok(d.into_any())
}

/// The net-connectivity validation stage: oracle geometry -> per-net
/// connectivity violations, raising `ConnectivityValidationError` on demand.
#[derive(Debug, Clone)]
pub struct ConnectivityValidationStage {
    pub fail_on_violations: bool,
}

impl Stage<BoardState> for ConnectivityValidationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || Python::attach(|py| self.run_inner(py, state)))
    }
}

impl ConnectivityValidationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> Result<BoardState, StageError> {
        let oracle = match &state.drc_oracle {
            Some(o) if o.bind(py).is_truthy()? => o.bind(py).clone(),
            _ => {
                // `logger.warning("No DRCOracle in state, skipping connectivity validation")`
                d6_util::log_msg(
                    py,
                    LOGGER_NAME,
                    "warning",
                    &pyo3::types::PyString::new(
                        py,
                        "No DRCOracle in state, skipping connectivity validation",
                    )
                    .into_any(),
                )?;
                return Ok(state);
            }
        };

        let geom = oracle.getattr("geometry")?;
        let nets = PyDict::new(py);

        for pad in geom.getattr("pads")?.try_iter()? {
            let pad = pad?;
            let net = pad.getattr("net")?;
            let sub = if nets.contains(&net)? {
                nets.as_any().get_item(&net)?
            } else {
                let fresh = empty_sub(py)?;
                nets.set_item(&net, &fresh)?;
                fresh
            };
            sub.get_item("pads")?.call_method1("append", (&pad,))?;
        }
        for track in geom.getattr("tracks")?.try_iter()? {
            let track = track?;
            let net = track.getattr("net")?;
            let sub = if nets.contains(&net)? {
                nets.as_any().get_item(&net)?
            } else {
                let fresh = empty_sub(py)?;
                nets.set_item(&net, &fresh)?;
                fresh
            };
            sub.get_item("tracks")?.call_method1("append", (&track,))?;
        }
        for via in geom.getattr("vias")?.try_iter()? {
            let via = via?;
            let net = via.getattr("net")?;
            let sub = if nets.contains(&net)? {
                nets.as_any().get_item(&net)?
            } else {
                let fresh = empty_sub(py)?;
                nets.set_item(&net, &fresh)?;
                fresh
            };
            sub.get_item("vias")?.call_method1("append", (&via,))?;
        }

        let plane_nets: Vec<Py<PyAny>> = match &state.layer_assignments {
            Some(la) if la.bind(py).is_truthy()? => {
                let mut out = Vec::new();
                for assignment in la.bind(py).try_iter()? {
                    let assignment = assignment?;
                    let is_plane: bool = assignment.getattr("is_plane")?.extract()?;
                    if is_plane {
                        out.push(assignment.getattr("net_name")?.unbind());
                    }
                }
                out
            }
            _ => Vec::new(),
        };

        let violation_cls = py
            .import("temper_placer.deterministic.stages.connectivity_validation")?
            .getattr("ConnectivityViolation")?;
        let point_cls = py
            .import("temper_placer.router_v6.constraints_geometry")?
            .getattr("Point")?;
        let drc = py.import("temper_drc_rs")?;

        let violations = PyList::empty(py);
        for (net_name, net_items) in nets.iter() {
            let net_name = net_name;
            if net_name.is_none() {
                continue;
            }
            let net_str: String = net_name.str()?.to_string();
            if net_str.is_empty() || net_str == "NoNet" {
                continue;
            }
            let is_plane: bool = plane_nets.iter().any(|pn| {
                pn.bind(py)
                    .eq(&net_name)
                    .unwrap_or(false)
            });
            if is_plane {
                continue;
            }
            let net_violations = self.validate_net_connectivity(
                py, &net_str, &net_items, &violation_cls, &point_cls, &drc,
            )?;
            violations.call_method1("extend", (&net_violations,))?;
        }

        self.log_summary(py, &violations)?;

        if self.fail_on_violations && violations.len() > 0 {
            let count = violations.len();
            let message = format!("{count} connectivity violations found");
            return Err(StageError::new(
                STAGE_NAME,
                message,
                StageErrorKind::Infeasible,
            ));
        }

        let tuple = py.import("builtins")?.getattr("tuple")?.call1((&violations,))?;
        let mut new_state = state;
        new_state.connectivity_violations = Some(tuple.into_any().unbind());
        Ok(new_state)
    }

    /// `_validate_net_connectivity`: marshal the flat pad/track/via lists,
    /// run the UnionFind kernel, wrap each row in a `ConnectivityViolation`.
    #[allow(clippy::too_many_arguments)]
    fn validate_net_connectivity<'py>(
        &self,
        py: Python<'py>,
        net_name: &str,
        net_items: &Bound<'py, PyAny>,
        violation_cls: &Bound<'py, PyAny>,
        point_cls: &Bound<'py, PyAny>,
        drc: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyList>> {
        let flat_pads = PyList::empty(py);
        for p in net_items.get_item("pads")?.try_iter()? {
            let p = p?;
            let center = p.getattr("center")?;
            let size = p.getattr("size")?;
            let row = PyTuple::new(
                py,
                [
                    center.getattr("x")?.into_any(),
                    center.getattr("y")?.into_any(),
                    p.getattr("layer")?.into_any(),
                    p.getattr("id")?.into_any(),
                    size.get_item(0)?.into_any(),
                    size.get_item(1)?.into_any(),
                    p.getattr("rotation")?.into_any(),
                ],
            )?;
            flat_pads.append(row)?;
        }
        let flat_tracks = PyList::empty(py);
        for t in net_items.get_item("tracks")?.try_iter()? {
            let t = t?;
            let start = t.getattr("start")?;
            let end = t.getattr("end")?;
            let row = PyTuple::new(
                py,
                [
                    start.getattr("x")?.into_any(),
                    start.getattr("y")?.into_any(),
                    end.getattr("x")?.into_any(),
                    end.getattr("y")?.into_any(),
                    t.getattr("layer")?.into_any(),
                ],
            )?;
            flat_tracks.append(row)?;
        }
        let flat_vias = PyList::empty(py);
        for v in net_items.get_item("vias")?.try_iter()? {
            let v = v?;
            let center = v.getattr("center")?;
            let row = PyTuple::new(
                py,
                [center.getattr("x")?.into_any(), center.getattr("y")?.into_any()],
            )?;
            flat_vias.append(row)?;
        }

        let rows = drc.call_method1(
            "connectivity_validate_net_py",
            (net_name, &flat_pads, &flat_tracks, &flat_vias),
        )?;
        let out = PyList::empty(py);
        for row in rows.try_iter()? {
            let row = row?;
            let point = point_cls.call1((row.get_item(1)?, row.get_item(2)?))?;
            let kwargs = PyDict::new(py);
            kwargs.set_item("type", row.get_item(0)?)?;
            kwargs.set_item("net", net_name)?;
            kwargs.set_item("location", &point)?;
            kwargs.set_item("description", row.get_item(3)?)?;
            out.append(violation_cls.call((), Some(&kwargs))?)?;
        }
        Ok(out)
    }

    /// `_log_summary`: count by type, rows sorted by descending count (ties in
    /// first-seen type order -- the Python `sorted(key=lambda x: -x[1])`).
    fn log_summary(&self, py: Python<'_>, violations: &Bound<'_, PyAny>) -> PyResult<()> {
        if violations.len()? == 0 {
            d6_util::log_msg(
                py,
                LOGGER_NAME,
                "info",
                &"Connectivity validation passed: 0 violations".into_pyobject(py)?.into_any(),
            )?;
            return Ok(());
        }
        let by_type: Vec<(String, usize)> = {
            let mut order: Vec<(String, usize)> = Vec::new();
            for v in violations.try_iter()? {
                let v = v?;
                let vtype: String = v.getattr("type")?.str()?.to_string();
                match order.iter_mut().find(|(k, _)| *k == vtype) {
                    Some(entry) => entry.1 += 1,
                    None => order.push((vtype, 1)),
                }
            }
            // Descending by count, ties in first-seen type order (a stable
            // sort -- `sort_by_key(Reverse(..))` keeps insertion order on
            // ties exactly like Python's `sorted(..., reverse=True)`).
            order.sort_by_key(|x| std::cmp::Reverse(x.1));
            order
        };
        let count = violations.len()?;
        let msg = d6_util::py_format(
            py,
            "Connectivity validation: {} violations",
            &[count.into_pyobject(py)?.into_any()],
        )?;
        d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
        for (vtype, c) in &by_type {
            let msg = d6_util::py_format(
                py,
                "  {}: {}",
                &[
                    vtype.into_pyobject(py)?.into_any(),
                    (*c).into_pyobject(py)?.into_any(),
                ],
            )?;
            d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
        }
        Ok(())
    }
}

/// FFI entry for the Python shim: `run_connectivity_validation(state,
/// fail_on_violations)` -> `(state, message)`.
#[pyfunction]
pub fn run_connectivity_validation(
    py: Python<'_>,
    state: Py<PyAny>,
    fail_on_violations: bool,
) -> PyResult<(Py<PyAny>, Option<String>)> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let stage = ConnectivityValidationStage { fail_on_violations };
    let result = stage.run(rust_state);
    crate::d6_util::write_back_or_raise(py, state.bind(py), result, &["connectivity_violations"])
}

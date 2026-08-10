//! Phase-A U6 (rust-orchestration-engine plan) typed marshalling boundary for
//! the human-reference quality-oracle marshalers.
//!
//! Migrated from `temper_placer/validation/human_reference_extractor.py`
//! (`_netlist_to_oracle_dict` / `_placement_to_oracle_dict`), per the plan's
//! Phase-A table:
//!
//! | Python marshaler                | Rust type      | Python name   |
//! |---------------------------------|----------------|---------------|
//! | `_netlist_to_oracle_dict`       | [`OracleInput`]  | `OracleInput`  |
//! | `_placement_to_oracle_dict`     | [`OracleOutput`] | `OracleOutput` |
//!
//! These two marshalers build the flat dicts that
//! `temper_quality_oracle.prepare_quality_py` / `evaluate_prepared_py`
//! consume. After Phase A the Python shim body collapses to
//! `OracleInput.from_netlist(...).to_dict()` — the dict-building tax moves to
//! Rust, exactly the U5 `DrcBoardSnapshot` pattern in `drc_marshal.rs`. The
//! kernel-signature tightening (the quality-oracle pyfunctions taking the
//! typed struct directly) is a later phase: the crate that owns those
//! pyfunctions is outside this unit's file ownership.
//!
//! # Bit-exactness notes
//!
//! - `_placement_to_oracle_dict` runs `np.asarray(state.positions,
//!   dtype=np.float64).reshape(-1).tolist()`. This port calls the identical
//!   numpy operations from Rust rather than reimplementing them, so the
//!   float32→float64 upcast, the row-major reshape order, and the scalar
//!   conversion are numpy's own — bit-identical by construction.
//! - `float(comp.bounds[0])` / `float(comp.bounds[1])` are reproduced by
//!   extracting the bounds elements as `f64` (pyo3's `PyFloat_AsDouble` is
//!   the same `__float__`-driven conversion Python's `float()` performs).
//! - `float(board.width)` / `float(board.height)` — identity on the pyclass
//!   float fields.
//!
//! # R19-style retained-oracle rule
//!
//! The pre-migration Python marshaler bodies are NOT kept here. They live
//! verbatim in `tests/validation/test_oracle_marshal_rust_differential.py`
//! (`_oracle_*` blocks).
//!
//! # Panic policy (R1g)
//!
//! Every `#[pymethods]` entry point is wrapped in [`guard`]
//! (`catch_unwind`); no `unwrap`/`expect` outside `#[cfg(test)]` (crate
//! clippy lint).

use std::panic::AssertUnwindSafe;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

// ---------------------------------------------------------------------------
// Guard — catch_unwind at the pyo3 boundary (G7)
// ---------------------------------------------------------------------------

fn guard<R>(body: impl FnOnce() -> PyResult<R>) -> PyResult<R> {
    match std::panic::catch_unwind(AssertUnwindSafe(body)) {
        Ok(r) => r,
        Err(_) => Err(PyRuntimeError::new_err("panic in oracle_marshal kernel")),
    }
}

fn err_attr(name: &str, e: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(format!(".{name}: {e}"))
}

// ---------------------------------------------------------------------------
// OracleInput — _netlist_to_oracle_dict
// ---------------------------------------------------------------------------

/// One net in the oracle-input wire shape: `{name, pins}` where `pins` is
/// `[ref for ref, _ in net.pins]` — the pin-number half is stripped and
/// duplicates are preserved (unlike the DRC `nets_from_list`, the oracle
/// marshaler does NOT dedup).
#[derive(Debug, Clone)]
struct OracleNet {
    name: String,
    pins: Vec<String>,
}

/// One component in the oracle-input wire shape: `{ref, footprint, width,
/// height}` from the placer `Component` (`bounds[0]` = width, `bounds[1]` =
/// height).
#[derive(Debug, Clone)]
struct OracleComponent {
    ref_: String,
    footprint: String,
    width: f64,
    height: f64,
}

/// The typed netlist marshaler for the quality-oracle input (Phase-A U6).
///
/// Python name `OracleInput` (no conflict — the plan's name lands as-is,
/// unlike U5's `TypedConstraintSet` deviation). Replaces
/// `_netlist_to_oracle_dict`; `to_dict()` reproduces the pre-migration dict
/// bit-for-bit.
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Debug)]
pub struct OracleInput {
    nets: Vec<OracleNet>,
    components: Vec<OracleComponent>,
}

#[pymethods]
impl OracleInput {
    /// `temper_drc_rs.OracleInput.from_netlist(netlist)` — the typed
    /// marshaler for `_netlist_to_oracle_dict`.
    #[staticmethod]
    fn from_netlist(netlist: &Bound<'_, PyAny>) -> PyResult<OracleInput> {
        guard(|| {
            let nets_list = netlist
                .getattr("nets")?
                .cast_into::<PyList>()
                .map_err(|e| err_attr("netlist.nets is not a list", e))?;
            let mut nets = Vec::with_capacity(nets_list.len());
            for net in nets_list.iter() {
                let name = crate::drc_oracle_marshal::get_attr_str(&net, "name")?;
                let pins_list = net
                    .getattr("pins")?
                    .cast_into::<PyList>()
                    .map_err(|e| err_attr("net.pins is not a list", e))?;
                let mut pins = Vec::with_capacity(pins_list.len());
                for pin in pins_list.iter() {
                    let ref_ = pin
                        .get_item(0)?
                        .extract::<String>()
                        .map_err(|e| err_attr("net.pin ref", e))?;
                    pins.push(ref_);
                }
                nets.push(OracleNet { name, pins });
            }

            let comps_list = netlist
                .getattr("components")?
                .cast_into::<PyList>()
                .map_err(|e| err_attr("netlist.components is not a list", e))?;
            let mut components = Vec::with_capacity(comps_list.len());
            for comp in comps_list.iter() {
                let ref_ = crate::drc_oracle_marshal::get_attr_str(&comp, "ref")?;
                let footprint = crate::drc_oracle_marshal::get_attr_str(&comp, "footprint")?;
                let bounds = comp.getattr("bounds")?;
                let width = bounds
                    .get_item(0)?
                    .extract::<f64>()
                    .map_err(|e| err_attr("component.bounds[0]", e))?;
                let height = bounds
                    .get_item(1)?
                    .extract::<f64>()
                    .map_err(|e| err_attr("component.bounds[1]", e))?;
                components.push(OracleComponent { ref_, footprint, width, height });
            }

            Ok(OracleInput { nets, components })
        })
    }

    /// Reproduce the pre-migration netlist dict (the exact shape
    /// `temper_quality_oracle.prepare_quality_py` reads).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let d = PyDict::new(py);

        let nets = PyList::empty(py);
        for net in &self.nets {
            let nd = PyDict::new(py);
            nd.set_item("name", &net.name)?;
            let pins = PyList::empty(py);
            for p in &net.pins {
                pins.append(p)?;
            }
            nd.set_item("pins", pins)?;
            nets.append(nd)?;
        }
        d.set_item("nets", nets)?;

        let comps = PyList::empty(py);
        for c in &self.components {
            let cd = PyDict::new(py);
            cd.set_item("ref", &c.ref_)?;
            cd.set_item("footprint", &c.footprint)?;
            cd.set_item("width", c.width)?;
            cd.set_item("height", c.height)?;
            comps.append(cd)?;
        }
        d.set_item("components", comps)?;

        Ok(d.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "OracleInput(nets={}, components={})",
            self.nets.len(),
            self.components.len()
        )
    }
}

// ---------------------------------------------------------------------------
// OracleOutput — _placement_to_oracle_dict
// ---------------------------------------------------------------------------

/// The typed placement marshaler for the quality-oracle input (Phase-A U6).
///
/// Replaces `_placement_to_oracle_dict`; `to_dict()` reproduces the
/// pre-migration dict bit-for-bit.
#[pyclass(dict, module = "temper_drc_rs", skip_from_py_object)]
#[derive(Debug)]
pub struct OracleOutput {
    /// The flattened row-major position list
    /// (`positions.reshape(-1).tolist()`).
    positions: Vec<f64>,
    /// The component refs in netlist order
    /// (`[c.ref for c in netlist.components]`).
    component_refs: Vec<String>,
    board_width_mm: f64,
    board_height_mm: f64,
}

/// Reproduce `np.asarray(positions, dtype=np.float64).reshape(-1).tolist()`
/// by calling the identical numpy operations — the float32→float64 upcast,
/// the row-major reshape order, and the scalar conversion are numpy's own,
/// so the result is bit-identical by construction.
fn positions_to_flat_f64(py: Python<'_>, positions: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    let np = py
        .import("numpy")
        .map_err(|e| PyValueError::new_err(format!("numpy import failed: {e}")))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", np.getattr("float64")?)?;
    let arr = np.call_method("asarray", (positions,), Some(&kwargs))?;
    let flat = arr.call_method1("reshape", (-1,))?;
    let list = flat
        .call_method0("tolist")?
        .cast_into::<PyList>()
        .map_err(|e| err_attr("positions.tolist() is not a list", e))?;
    let mut out = Vec::with_capacity(list.len());
    for item in list.iter() {
        out.push(item.extract::<f64>().map_err(|e| err_attr("position element", e))?);
    }
    Ok(out)
}

#[pymethods]
impl OracleOutput {
    /// `temper_drc_rs.OracleOutput.from_state(state, netlist, board)` — the
    /// typed marshaler for `_placement_to_oracle_dict`.
    #[staticmethod]
    fn from_state(
        py: Python<'_>,
        state: &Bound<'_, PyAny>,
        netlist: &Bound<'_, PyAny>,
        board: &Bound<'_, PyAny>,
    ) -> PyResult<OracleOutput> {
        guard(|| {
            let positions_any = state
                .getattr("positions")
                .map_err(|e| err_attr("state.positions", e))?;
            let positions = positions_to_flat_f64(py, &positions_any)?;

            let comps_list = netlist
                .getattr("components")?
                .cast_into::<PyList>()
                .map_err(|e| err_attr("netlist.components is not a list", e))?;
            let mut component_refs = Vec::with_capacity(comps_list.len());
            for comp in comps_list.iter() {
                component_refs.push(crate::drc_oracle_marshal::get_attr_str(&comp, "ref")?);
            }

            let board_width_mm = crate::drc_oracle_marshal::get_attr_f64(board, "width")?;
            let board_height_mm = crate::drc_oracle_marshal::get_attr_f64(board, "height")?;

            Ok(OracleOutput {
                positions,
                component_refs,
                board_width_mm,
                board_height_mm,
            })
        })
    }

    /// Reproduce the pre-migration placement dict (the exact shape
    /// `temper_quality_oracle.evaluate_prepared_py` reads).
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let d = PyDict::new(py);

        let positions = PyList::empty(py);
        for p in &self.positions {
            positions.append(p)?;
        }
        d.set_item("positions", positions)?;

        let refs = PyList::empty(py);
        for r in &self.component_refs {
            refs.append(r)?;
        }
        d.set_item("component_refs", refs)?;

        d.set_item("board_width_mm", self.board_width_mm)?;
        d.set_item("board_height_mm", self.board_height_mm)?;

        Ok(d.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "OracleOutput(positions={}, component_refs={}, board={}x{})",
            self.positions.len(),
            self.component_refs.len(),
            self.board_width_mm,
            self.board_height_mm,
        )
    }
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<OracleInput>()?;
    m.add_class::<OracleOutput>()?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Rust unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn oracle_input_holds_nets_and_components() {
        let input = OracleInput {
            nets: vec![OracleNet {
                name: "VCC".into(),
                pins: vec!["C1".into(), "C1".into()],
            }],
            components: vec![OracleComponent {
                ref_: "C1".into(),
                footprint: "0805".into(),
                width: 2.0,
                height: 1.5,
            }],
        };
        assert_eq!(input.nets.len(), 1);
        assert_eq!(input.nets[0].name, "VCC");
        // Duplicate pin refs are preserved (the oracle marshaler does not
        // dedup, unlike the DRC nets_from_list).
        assert_eq!(input.nets[0].pins, vec!["C1".to_string(), "C1".to_string()]);
        assert_eq!(input.components[0].ref_, "C1");
        assert_eq!(input.components[0].width, 2.0);
        assert_eq!(input.components[0].height, 1.5);
    }

    #[test]
    fn oracle_output_holds_flat_positions() {
        let out = OracleOutput {
            positions: vec![1.0, 2.0, 3.0, 4.0],
            component_refs: vec!["C1".into(), "R1".into()],
            board_width_mm: 100.0,
            board_height_mm: 80.0,
        };
        assert_eq!(out.positions.len(), 4);
        assert_eq!(out.component_refs, vec!["C1".to_string(), "R1".to_string()]);
        assert_eq!(out.board_width_mm, 100.0);
        assert_eq!(out.board_height_mm, 80.0);
    }
}

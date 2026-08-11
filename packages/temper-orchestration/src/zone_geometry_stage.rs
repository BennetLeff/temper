// The D2 `ZoneGeometryStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D2): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/zone_geometry.py`.
//
// stage reads `BoardState.board`, dispatches on the config
// (`zone_config` truthiness — the config-vs-default branches), delegates
// the layout math to the already-Rust leaf kernels
// (`temper_design_bundle_python.deterministic_stages.define_zone_layout` /
// `scale_zone_bounds` — the Phase-5 first-slice migration), constructs the
// `Zone` objects (imported from the Python shim, which keeps the dataclass),
// wraps them in a `frozenset`, and writes the result into
// `BoardState.zones`. The `state.board` guard returns the state unchanged
// (identity preserved).
//
// The `_define_zones_from_config` config branch is reproduced exactly:
// the `hasattr(name)/hasattr(bounds)` Zone-object passthrough (the
// 4-tuple `(x_min, y_min, x_max, y_max)` core/board.py bounds are nested
// when `len(b) == 4`), the dict branch (`z["name"]`, the
// `z.get("bounds_ratio", [0, 0, 1, 1])` default, then `scale_zone_bounds`),
// and the unknown-format `print(f"WARNING: Unknown zone format: {type(z)}")`
// warning reproduced by calling the builtin `print` with the identical
// string (type-str is identical to CPython's f-string `{type(z)}`).
//
// Bit-exactness: the Zone bounds are rebuilt from the leaf kernels' output
// PyTuples, so the int-vs-float type-carrying canon (HV `x_min`/every
// `y_min` are Python `int` `0`, board-dims pass through with their original
// type) is preserved exactly as the oracle stores it.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
/// The zone-geometry stage: board -> `zones` (frozenset of Zone objects).
#[derive(Debug, Clone)]
pub struct ZoneGeometryStage {
    pub zone_config: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ZoneGeometryStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("zone_geometry")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("zone_geometry", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("zone_geometry", e);
                let board = match &state.board {
                    Some(b) if b.bind(py).is_truthy().map_err(to_stage)? => b.clone_ref(py),
                    _ => return Ok(state),
                };
                let board_width = board.bind(py).getattr("width").map_err(to_stage)?;
                let board_height = board.bind(py).getattr("height").map_err(to_stage)?;
                let tdb = py
                    .import("temper_design_bundle_python")
                    .map_err(to_stage)?
                    .getattr("deterministic_stages")
                    .map_err(to_stage)?;
                let zone_cls = py
                    .import("temper_placer.deterministic.stages.zone_geometry")
                    .map_err(to_stage)?
                    .getattr("Zone")
                    .map_err(to_stage)?;

                // `if self.zone_config:` -- the config list's truthiness.
                let zones_fs: Py<PyAny> = match &self.zone_config {
                    Some(cfg) if cfg.bind(py).len().map_err(to_stage)? > 0 => {
                        define_zones_from_config(
                            py,
                            cfg.bind(py),
                            &board_width,
                            &board_height,
                            &tdb,
                            &zone_cls,
                        )
                        .map_err(to_stage)?
                    }
                    _ => define_zone_layout_zones(py, &board_width, &board_height, &tdb, &zone_cls)
                        .map_err(to_stage)?,
                };

                let mut new_state = state;
                new_state.zones = Some(zones_fs);
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_zone_geometry(state, zone_config)`.
#[pyfunction]
#[pyo3(signature = (state, zone_config=None))]
pub fn run_zone_geometry(
    py: Python<'_>,
    state: Py<PyAny>,
    zone_config: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("zone_geometry: {e}"))
    })?;
    let stage = ZoneGeometryStage { zone_config };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["zones"])
}

// ---------------------------------------------------------------------------
// Zone construction
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The `_define_zone_layout` branch: `define_zone_layout(board_width,
/// board_height)` rows are unpacked (`name, x_min, y_min, x_max, y_max`)
/// and each becomes `Zone(name=name, bounds=((x_min, y_min),
/// (x_max, y_max)))`; the list is wrapped in a `frozenset` exactly like the
/// oracle's `frozenset(zones)`.
fn define_zone_layout_zones<'py>(
    py: Python<'py>,
    board_width: &Bound<'py, PyAny>,
    board_height: &Bound<'py, PyAny>,
    tdb: &Bound<'py, PyAny>,
    zone_cls: &Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    let rows = tdb.call_method1("define_zone_layout", (board_width, board_height))?;
    let zones = PyList::empty(py);
    for row in rows.try_iter()? {
        let row = row?;
        let name = row.get_item(0)?;
        let bounds = nested_bounds(
            py,
            row.get_item(1)?,
            row.get_item(2)?,
            row.get_item(3)?,
            row.get_item(4)?,
        )?;
        zones.append(zone_cls.call1((name, bounds))?)?;
    }
    frozenset_of(py, &zones)
}

#[cfg(feature = "python")]
/// The `_define_zones_from_config` branch: for each config entry, the
/// Zone-object passthrough, the dict `bounds_ratio` scaling, or the
/// unknown-format warning; the list is wrapped in a `frozenset`.
fn define_zones_from_config<'py>(
    py: Python<'py>,
    cfg: &Bound<'py, PyAny>,
    board_width: &Bound<'py, PyAny>,
    board_height: &Bound<'py, PyAny>,
    tdb: &Bound<'py, PyAny>,
    zone_cls: &Bound<'py, PyAny>,
) -> PyResult<Py<PyAny>> {
    let builtins = py.import("builtins")?;
    let default_ratio = PyList::new(py, [0i64, 0i64, 1i64, 1i64])?;
    let zones = PyList::empty(py);
    for z in cfg.try_iter()? {
        let z = z?;
        if z.hasattr("name")? && z.hasattr("bounds")? {
            // `Zone` object (core/board.py): nested only when the flat
            // 4-tuple `(x_min, y_min, x_max, y_max)` shape is present.
            let b = z.getattr("bounds")?;
            let bounds: Bound<'py, PyAny> = if b.len()? == 4 {
                nested_bounds(py, b.get_item(0)?, b.get_item(1)?, b.get_item(2)?, b.get_item(3)?)?
                    .into_any()
            } else {
                b
            };
            zones.append(zone_cls.call1((z.getattr("name")?, bounds))?)?;
        } else if z.is_instance_of::<PyDict>() {
            let name: String = z.call_method1("__getitem__", ("name",))?.extract()?;
            let ratio = z.call_method1("get", ("bounds_ratio", &default_ratio))?;
            let r0: f64 = ratio.get_item(0)?.extract()?;
            let r1: f64 = ratio.get_item(1)?.extract()?;
            let r2: f64 = ratio.get_item(2)?.extract()?;
            let r3: f64 = ratio.get_item(3)?.extract()?;
            let scaled = tdb.call_method1(
                "scale_zone_bounds",
                (name.clone(), r0, r1, r2, r3, board_width, board_height),
            )?;
            let bounds = nested_bounds(
                py,
                scaled.get_item(0)?,
                scaled.get_item(1)?,
                scaled.get_item(2)?,
                scaled.get_item(3)?,
            )?;
            zones.append(zone_cls.call1((name, bounds))?)?;
        } else {
            // `print(f"WARNING: Unknown zone format: {type(z)}")` -- the
            // builtin print with the identical message (a type's `str()`
            // renders `<class 'int'>` exactly like the f-string).
            let msg = format!("WARNING: Unknown zone format: {}", z.get_type().str()?);
            builtins.getattr("print")?.call1((msg,))?;
        }
    }
    frozenset_of(py, &zones)
}

#[cfg(feature = "python")]
/// `((x_min, y_min), (x_max, y_max))` from the four scalar values (their
/// concrete Python types — int vs float — pass through untouched).
fn nested_bounds<'py>(
    py: Python<'py>,
    x_min: Bound<'py, PyAny>,
    y_min: Bound<'py, PyAny>,
    x_max: Bound<'py, PyAny>,
    y_max: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let lo = PyTuple::new(py, [x_min, y_min])?;
    let hi = PyTuple::new(py, [x_max, y_max])?;
    PyTuple::new(py, [lo.into_any(), hi.into_any()])
}

#[cfg(feature = "python")]
/// `frozenset(list)` — the oracle's wrap.
fn frozenset_of<'py>(
    py: Python<'py>,
    list: &Bound<'py, PyList>,
) -> PyResult<Py<PyAny>> {
    let builtins = py.import("builtins")?;
    Ok(builtins
        .getattr("frozenset")?
        .call1((list,))?
        .into_any()
        .unbind())
}

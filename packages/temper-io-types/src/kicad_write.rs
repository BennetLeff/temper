//! KiCad write/export engine kernels.
//!
//! Wave 4, Phase 3, candidate 4 of
//! `docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`: the
//! write/export engine (`temper_placer/io/kicad_exporter.py`,
//! `_write_board.py`, `_write_tracks.py`, `_write_zones.py`,
//! `_write_modules.py`, `_write_types.py`, `kicad_writer.py`,
//! `placement_exporter.py`) migrates its transformation/decision layer here.
//!
//! Boundary shape (plan D5 / Q1, the `from_py_object` precedent set by
//! `golden_serializers::serialize_boardstate_to_dsn`): the engine reads its
//! unmigrated inputs (kiutils `Board` objects, router_v6 `RoutePath`s,
//! `PlacementState`, `BoardState`, numpy arrays) **duck-typed** through the
//! pyo3 boundary, computes every geometry/decision/count, and returns
//! mutation *plans* (plain tuples/lists/dicts plus the result pyclasses). The
//! Python shims keep only the kiutils object I/O (`KiBoard.from_file` /
//! `board.to_file`), kiutils item construction (`Segment`, `Via`, `Zone`,
//! `GrLine`, `GrRect`, `GrText`, `Position`), and the numpy-array extraction
//! (`state.positions[i]`, `np.argmax`) — the R3-style boundary notes naming
//! each blocker are recorded in
//! `packages/temper-io-types/VERIFICATION.md`.
//!
//! Determinism pins (inherited from candidate 6's findings):
//! - `round()` is half-to-EVEN: `f64::round` breaks ties away from zero and
//!   shifts geometry by one unit on every `.5` tick. `py_round_ties_even` /
//!   `py_round_ndigits` reproduce CPython's `round(float)` /
//!   `round(float, ndigits)` (`_Py_round_half_even`, then divide by the
//!   `10 ** ndigits` power).
//! - Python `%` on floats is fmod-then-adjust (result takes the divisor's
//!   sign); Rust `%` keeps the dividend's sign. `py_mod` reproduces it — a
//!   negative `(rotation_deg + offset)` would otherwise land in the wrong
//!   quadrant.
//! - `str::to_lowercase` applies the Greek final-sigma rule CPython's
//!   `str.lower()` does not; component references are ASCII by construction,
//!   so `to_ascii_lowercase` is used where a sort/name key is built.
//! - dict **insertion** order is the contract where the verbatim Python
//!   builds a dict and iterates it (pad centers, net maps, placements);
//!   iteration here always walks the Python object's own order, never a
//!   `HashMap`.
//! - bool-vs-int rendering and empty-comment truthiness are write-engine
//!   hazards only in the serializers; this module's surface is
//!   value-producing, so they are pinned via the concrete-type-carrying
//!   canonicalizer in the differential instead.
//!
//! R1h: this is a serialization/transformation surface, not a physics-gated
//! one — no clearance/creepage/thermal margin is computed or asserted, so the
//! R24 state gate is N/A (recorded in VERIFICATION.md).

// The plan-producing pyfunctions mirror the pinned Python entry points'
// parameter lists (up to 10 args: `export_routed_pcb(template_pcb, routes,
// output_pcb, trace_widths, default_trace_width, via_size, via_drill, origin,
// cell_size, layer_map)`), and their return types are the duck-typed plan
// tuples the shims consume. `#[allow]` here, not a restructure: the arity and
// tuple shapes are dictated by the API being pinned, not by taste.
#![allow(clippy::too_many_arguments, clippy::type_complexity)]

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

// =============================================================================
// Pure helpers — reproduced operation-for-operation from the pinned Python.
// =============================================================================

/// CPython `round(x)` for a float: nearest integer, ties to EVEN. For the
/// integer case the f64's exact value IS the value being rounded, so
/// `f64::round_ties_even` is exact (CPython's `_Py_round_half_even`).
fn py_round_ties_even(x: f64) -> f64 {
    x.round_ties_even()
}

/// CPython `round(x, ndigits)` for `ndigits >= 0`.
///
/// This is NOT `(x * 10^n).round_ties_even() / 10^n`: CPython's
/// `float_round` renders the exact binary value to `ndigits` decimal digits
/// with `_Py_dg_dtoa` and parses the result back (correctly rounded). The
/// multiply-then-divide shortcut is wrong whenever `x * 10^n` lands exactly
/// on a half-integer while the exact value is on the other side — measured:
/// `2.675 * 100.0 == 267.5` exactly, but `round(2.675, 2) == 2.67`, not
/// 2.68. A naive port silently shifts every such via-dedup key by one
/// 1e-3 mm unit.
///
/// This port rounds the EXACT rational `x * 10^ndigits` to an integer
/// (half-to-even) using integer arithmetic, then divides by `10^ndigits`
/// with a correctly-rounded f64 division — matching CPython for every finite
/// `x` with `|x * 10^ndigits| < 2^53` (all real board coordinates; the
/// differential pins the domain and the via-dedup keys it feeds).
fn py_round_ndigits(x: f64, ndigits: i32) -> f64 {
    if !x.is_finite() {
        return x; // round(inf, n) == inf; round(nan, n) == nan
    }
    if x == 0.0 {
        return x; // preserves -0.0
    }
    if x.abs() >= 9007199254740992.0 {
        return x; // |x| >= 2^53 is already an exact integer
    }
    let sign = if x.is_sign_negative() { -1.0 } else { 1.0 };
    let bits = x.to_bits();
    let exp_field = ((bits >> 52) & 0x7ff) as i32;
    let (m, e) = if exp_field == 0 {
        // subnormal: no implicit leading bit
        ((bits & ((1u64 << 52) - 1)) as i128, -1074i32)
    } else {
        (
            ((bits & ((1u64 << 52) - 1)) as i128) | (1i128 << 52),
            exp_field - 1075,
        )
    };
    if m == 0 {
        return x;
    }
    // x == m * 2^e exactly. x * 10^ndigits == m * 5^ndigits * 2^(e+ndigits).
    let p5 = 5i128.pow(ndigits as u32);
    let s = m * p5;
    let k = e + ndigits;
    let q: i128 = if k >= 0 {
        s << k
    } else {
        round_half_even_shift(s, (-k) as u32)
    };
    let pow10 = 10f64.powi(ndigits);
    sign * (q as f64) / pow10
}

/// Rounds the exact rational `s / 2^k` (s, k integers, k >= 1) to the
/// nearest integer, ties to EVEN, in exact integer arithmetic.
fn round_half_even_shift(s: i128, k: u32) -> i128 {
    if k == 0 {
        return s;
    }
    let q = s >> k;
    let rem_mask = (1i128 << k) - 1;
    let rem = s & rem_mask;
    let half = 1i128 << (k - 1);
    if rem > half {
        q + 1
    } else if rem < half {
        q
    } else if q & 1 == 1 {
        q + 1
    } else {
        q
    }
}

/// Python `%` for floats: C `fmod`, then add the divisor when the remainder
/// is non-zero and has the opposite sign to the divisor (CPython
/// `float_rem`). Rust's `%` keeps the dividend's sign, so it is not a
/// substitute for negative operands.
fn py_mod(a: f64, b: f64) -> f64 {
    let r = a % b;
    if r != 0.0 && (r < 0.0) != (b < 0.0) {
        r + b
    } else {
        r
    }
}

/// CPython `math.radians(x)` = `x * (M_PI / 180.0)`. `std::f64::consts::PI`
/// is the same double as `M_PI`, so the compile-time division is the same
/// correctly-rounded constant Python computes at runtime, and the multiply is
/// the same IEEE operation.
fn radians(x: f64) -> f64 {
    x * (std::f64::consts::PI / 180.0)
}

/// KiCad's footprint-child rotation convention, R(-theta), the single
/// sanctioned formula in `temper_placer/geometry/kicad_transform.py`
/// (rotation-sign evidence in
/// `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`):
/// `(x * c + y * s, -x * s + y * c)` — the operation order is preserved so
/// the result is bit-identical to the Python arm. The repo's rule is "do not
/// reimplement it"; this is the write engine's own copy of the same two-line
/// formula (as `temper-geometry` carries one), pinned by the differential's
/// discriminating rotation cases.
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let c = theta_rad.cos();
    let s = theta_rad.sin();
    (x * c + y * s, -x * s + y * c)
}

/// `grid_converter.grid_to_world`: cell-center world coordinates.
/// `x = origin[0] + cell.x * cell_size + cell_size / 2` (left-to-right).
fn grid_to_world(cell_x: i64, cell_y: i64, origin: (f64, f64), cell_size: f64) -> (f64, f64) {
    let x = origin.0 + cell_x as f64 * cell_size + cell_size / 2.0;
    let y = origin.1 + cell_y as f64 * cell_size + cell_size / 2.0;
    (x, y)
}

/// `path_simplify.is_collinear` for axis-aligned grid cells.
fn is_collinear(p1: (i64, i64, i64), p2: (i64, i64, i64), p3: (i64, i64, i64)) -> bool {
    if !(p1.2 == p2.2 && p2.2 == p3.2) {
        return false;
    }
    if p1.1 == p2.1 && p2.1 == p3.1 {
        return true;
    }
    p1.0 == p2.0 && p2.0 == p3.0
}

/// `path_simplify.simplify_path`: remove collinear waypoints, always keep
/// layer transitions and the endpoints.
fn simplify_path(cells: &[(i64, i64, i64)]) -> Vec<(i64, i64, i64)> {
    if cells.len() <= 2 {
        return cells.to_vec();
    }
    let mut simplified = vec![cells[0]];
    for i in 1..cells.len() - 1 {
        let prev = cells[i - 1];
        let curr = cells[i];
        let next_cell = cells[i + 1];
        if curr.2 != prev.2 || curr.2 != next_cell.2 {
            simplified.push(curr);
            continue;
        }
        if !is_collinear(prev, curr, next_cell) {
            simplified.push(curr);
        }
    }
    simplified.push(cells[cells.len() - 1]);
    simplified
}

/// `snap_to_nearest_pad`: nearest pad center within `tolerance`, else the
/// original point. Strict `<` on the distance (a pad exactly at the tolerance
/// boundary does not snap).
fn snap_to_nearest_pad(x: f64, y: f64, pads: &[(f64, f64)], tolerance: f64) -> (f64, f64) {
    let mut best_dist = tolerance;
    let mut best_pos = (x, y);
    for &(px, py) in pads {
        let dx = x - px;
        let dy = y - py;
        let dist = (dx * dx + dy * dy).sqrt();
        if dist < best_dist {
            best_dist = dist;
            best_pos = (px, py);
        }
    }
    best_pos
}

/// The canonical 4-layer stackup's copper names (`LayerIndex.__str__` values;
/// `CANONICAL_4LAYER_LAYER_NAMES` in `core/board.py`).
const CANONICAL_4LAYER_LAYER_NAMES: [&str; 4] = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"];

/// `LAYER_MAP` in `kicad_exporter.py` (grid layer index -> KiCad layer name).
const LAYER_MAP: [(i64, &str); 4] = [
    (0, "F.Cu"),
    (1, "In1.Cu"),
    (2, "In2.Cu"),
    (3, "B.Cu"),
];

fn layer_map_lookup(layer_map: Option<&Bound<'_, PyDict>>, layer: i64) -> PyResult<String> {
    if let Some(map) = layer_map
        && !map.is_empty()
    {
        if let Some(v) = map.get_item(layer)?
            && let Ok(s) = v.extract::<String>() {
                return Ok(s);
            }
        return Ok("F.Cu".to_string());
    }
    for (k, name) in LAYER_MAP {
        if k == layer {
            return Ok(name.to_string());
        }
    }
    Ok("F.Cu".to_string())
}

// =============================================================================
// Duck-typed attribute readers (the `from_py_object` boundary).
// =============================================================================

fn get_attr_str(obj: &Bound<'_, PyAny>, name: &str, default: &str) -> String {
    obj.getattr(name)
        .ok()
        .and_then(|v| v.extract::<String>().ok())
        .unwrap_or_else(|| default.to_string())
}

fn get_attr_opt_str(obj: &Bound<'_, PyAny>, name: &str) -> Option<String> {
    obj.getattr(name).ok().and_then(|v| v.extract::<String>().ok())
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

/// Reads a 2-D point from an object that is either a 2-tuple, a
/// two-element sequence, or a `.x`/`.y` pair.
fn get_xy(obj: &Bound<'_, PyAny>) -> Option<(f64, f64)> {
    if let Ok((x, y)) = obj.extract::<(f64, f64)>() {
        return Some((x, y));
    }
    if let Ok(seq) = obj.try_iter() {
        let items: Vec<Bound<'_, PyAny>> = seq.filter_map(|i| i.ok()).collect();
        if items.len() >= 2
            && let (Ok(x), Ok(y)) = (items[0].extract::<f64>(), items[1].extract::<f64>()) {
                return Some((x, y));
            }
    }
    let x = obj.getattr("x").ok()?.extract::<f64>().ok()?;
    let y = obj.getattr("y").ok()?.extract::<f64>().ok()?;
    Some((x, y))
}

/// Python truthiness of a value (an empty string / None / empty collection is
/// falsy).
fn is_truthy(v: &Bound<'_, PyAny>) -> PyResult<bool> {
    v.is_truthy()
}

/// `float(value)` semantics. CPython's `float()` special-cases strings
/// (parses them) before falling back to the `__float__` protocol; `str` has
/// no `__float__` method, so calling it directly raises AttributeError while
/// `float("10")` returns 10.0. Rust `str::parse::<f64>()` is IEEE-correctly
/// rounded like CPython's parse (the phase plan's Q2 assumption); values that
/// are not strings go through `__float__` (numbers, bools, numpy scalars).
fn py_float(v: &Bound<'_, PyAny>) -> PyResult<f64> {
    if let Ok(s) = v.extract::<String>() {
        return s
            .parse::<f64>()
            .map_err(|_| PyValueError::new_err("could not convert string to float"));
    }
    let f = v.call_method0("__float__")?;
    f.extract::<f64>()
}

/// `type(obj).__name__` — the string the verbatim Python compares against
/// `("Segment", "Arc")` / `"Via"`.
fn type_name(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    let ty = obj.get_type();
    let name = ty.getattr("__name__")?;
    name.extract::<String>()
}

fn value_error(msg: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(msg.to_string())
}

/// catch_unwind at the pyo3 boundary: a Rust panic must never unwind across
/// the FFI frame and abort the interpreter.
fn guarded<T>(f: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(res) => res,
        Err(_) => Err(PyRuntimeError::new_err(
            "panic inside temper_io_types.kicad_write",
        )),
    }
}

// =============================================================================
// Pyclasses — the `_write_types` dataclasses.
// =============================================================================

/// `_write_types.PlacementUpdate` — placement update for a single component.
#[pyclass(name = "PlacementUpdate", module = "temper_io_types", from_py_object)]
#[derive(Clone)]
pub struct PyPlacementUpdate {
    #[pyo3(get, set, name = "ref")]
    pub ref_: String,
    #[pyo3(get, set)]
    pub x: f64,
    #[pyo3(get, set)]
    pub y: f64,
    #[pyo3(get, set)]
    pub rotation: f64,
}

#[pymethods]
impl PyPlacementUpdate {
    #[new]
    #[pyo3(signature = (r#ref, x, y, rotation))]
    fn new(r#ref: String, x: f64, y: f64, rotation: f64) -> Self {
        PyPlacementUpdate {
            ref_: r#ref,
            x,
            y,
            rotation,
        }
    }

    fn __repr__(&self) -> String {
        // mirrors the dataclass repr: single-quoted ref, shortest round-trip
        // floats (Rust's Debug for f64 is the same shortest algorithm as
        // Python's repr(float)).
        format!(
            "PlacementUpdate(ref='{}', x={:?}, y={:?}, rotation={:?})",
            self.ref_, self.x, self.y, self.rotation
        )
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        if let Ok(o) = other.extract::<PyRef<'_, PyPlacementUpdate>>() {
            Ok(self.ref_ == o.ref_ && self.x == o.x && self.y == o.y && self.rotation == o.rotation)
        } else {
            Ok(false)
        }
    }
}

/// `_write_types.WriteResult` — result of writing placement to a KiCad file.
#[pyclass(name = "WriteResult", module = "temper_io_types", skip_from_py_object)]

pub struct PyWriteResult {
    #[pyo3(get, set)]
    pub output_path: Py<PyAny>,
    #[pyo3(get, set)]
    pub components_updated: usize,
    #[pyo3(get, set)]
    pub components_skipped: usize,
    #[pyo3(get, set)]
    pub warnings: Py<PyAny>,
}

#[pymethods]
impl PyWriteResult {
    #[new]
    #[pyo3(signature = (output_path, components_updated, components_skipped, warnings))]
    fn new(
        output_path: Py<PyAny>,
        components_updated: usize,
        components_skipped: usize,
        warnings: Py<PyAny>,
    ) -> Self {
        PyWriteResult {
            output_path,
            components_updated,
            components_skipped,
            warnings,
        }
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> PyResult<bool> {
        let w = self.warnings.bind(py);
        Ok(w.len()? > 0)
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        format!(
            "WriteResult(output_path={}, components_updated={}, components_skipped={}, warnings={})",
            self.output_path.bind(py).repr().map(|r| r.to_string()).unwrap_or_default(),
            self.components_updated,
            self.components_skipped,
            self.warnings.bind(py).repr().map(|r| r.to_string()).unwrap_or_default(),
        )
    }
}

/// `_write_types.StrippingResult` — result of stripping routing.
#[pyclass(name = "StrippingResult", module = "temper_io_types", skip_from_py_object)]
pub struct PyStrippingResult {
    #[pyo3(get, set)]
    pub output_path: Py<PyAny>,
    #[pyo3(get, set)]
    pub traces_removed: usize,
    #[pyo3(get, set)]
    pub vias_removed: usize,
    #[pyo3(get, set)]
    pub zones_removed: usize,
    #[pyo3(get, set)]
    pub components_preserved: usize,
    #[pyo3(get, set)]
    pub warnings: Py<PyAny>,
}

#[pymethods]
impl PyStrippingResult {
    #[new]
    #[pyo3(signature = (output_path, traces_removed, vias_removed, zones_removed, components_preserved, warnings))]
    fn new(
        output_path: Py<PyAny>,
        traces_removed: usize,
        vias_removed: usize,
        zones_removed: usize,
        components_preserved: usize,
        warnings: Py<PyAny>,
    ) -> Self {
        PyStrippingResult {
            output_path,
            traces_removed,
            vias_removed,
            zones_removed,
            components_preserved,
            warnings,
        }
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> PyResult<bool> {
        Ok(self.warnings.bind(py).len()? > 0)
    }
}

/// `_write_types.IsolationSlotResult` — result of adding isolation slots.
#[pyclass(name = "IsolationSlotResult", module = "temper_io_types", skip_from_py_object)]
pub struct PyIsolationSlotResult {
    #[pyo3(get, set)]
    pub output_path: Py<PyAny>,
    #[pyo3(get, set)]
    pub slots_added: usize,
    #[pyo3(get, set)]
    pub slots_skipped: usize,
    #[pyo3(get, set)]
    pub warnings: Py<PyAny>,
}

#[pymethods]
impl PyIsolationSlotResult {
    #[new]
    #[pyo3(signature = (output_path, slots_added, slots_skipped, warnings))]
    fn new(
        output_path: Py<PyAny>,
        slots_added: usize,
        slots_skipped: usize,
        warnings: Py<PyAny>,
    ) -> Self {
        PyIsolationSlotResult {
            output_path,
            slots_added,
            slots_skipped,
            warnings,
        }
    }

    #[getter]
    fn has_warnings(&self, py: Python<'_>) -> PyResult<bool> {
        Ok(self.warnings.bind(py).len()? > 0)
    }
}

// =============================================================================
// Pyfunctions
// =============================================================================

// ---------------------------------------------------------------------------
// Group A — route -> geometry (duck-typed RoutePath).
// ---------------------------------------------------------------------------

/// A resolved path coordinate: world (x, y) plus an explicit layer (from the
/// cells/segments branches) or `None` (fall back to the path's default).
type Coord = (f64, f64, Option<String>);

/// Builds the `coords` list from a duck-typed path, mirroring
/// `kicad_exporter.path_to_segments`'s branch order (cells first, then
/// segments, then coordinates).
///
/// Returns `(coords, default_layer, net)`.
fn path_coords<'py>(
    py: Python<'py>,
    path: &Bound<'py, PyAny>,
    origin: (f64, f64),
    cell_size: f64,
    layer_map: Option<&Bound<'py, PyDict>>,
) -> PyResult<(Vec<Coord>, String, String)> {
    let default_layer = get_attr_str(path, "layer_name", "F.Cu");
    let net_name = get_attr_opt_str(path, "net_name").filter(|s| !s.is_empty());
    let net = net_name
        .or_else(|| get_attr_opt_str(path, "net").filter(|s| !s.is_empty()))
        .unwrap_or_else(|| "unknown".to_string());

    let mut coords: Vec<Coord> = Vec::new();

    // cells branch (with simplify + grid_to_world)
    let cells_attr = path.getattr("cells").ok();
    let has_cells = cells_attr
        .as_ref()
        .map(|c| is_truthy(c).unwrap_or(false))
        .unwrap_or(false);
    if has_cells {
        let cells = cells_attr.unwrap_or_else(|| py.None().into_bound(py));
        let path_cell_size = get_attr_f64(path, "cell_size", cell_size);
        let mut grid_cells: Vec<(i64, i64, i64)> = Vec::new();
        for item in cells.try_iter()? {
            let c = item?;
            grid_cells.push((
                get_attr_i64(&c, "x", 0),
                get_attr_i64(&c, "y", 0),
                get_attr_i64(&c, "layer", 0),
            ));
        }
        for c in simplify_path(&grid_cells) {
            let (x, y) = grid_to_world(c.0, c.1, origin, path_cell_size);
            let layer_name = layer_map_lookup(layer_map, c.2)?;
            coords.push((x, y, Some(layer_name)));
        }
    } else {
        let segs_attr = path.getattr("segments").ok();
        let has_segs = segs_attr
            .as_ref()
            .map(|s| is_truthy(s).unwrap_or(false))
            .unwrap_or(false);
        if has_segs {
            let segs = segs_attr.unwrap_or_else(|| py.None().into_bound(py));
            for item in segs.try_iter()? {
                let t = item?;
                let tuple = t.cast::<PyTuple>().map_err(|_| {
                    value_error("path.segments entries must be tuples")
                })?;
                if tuple.len() == 3 {
                    let x: f64 = tuple.get_item(0)?.extract()?;
                    let y: f64 = tuple.get_item(1)?.extract()?;
                    let l: String = tuple.get_item(2)?.extract()?;
                    coords.push((x, y, Some(l)));
                } else {
                    let x: f64 = tuple.get_item(0)?.extract()?;
                    let y: f64 = tuple.get_item(1)?.extract()?;
                    coords.push((x, y, None));
                }
            }
        } else {
            let cs_attr = path.getattr("coordinates").ok();
            let has_cs = cs_attr
                .as_ref()
                .map(|c| is_truthy(c).unwrap_or(false))
                .unwrap_or(false);
            if has_cs {
                let cs = cs_attr.unwrap_or_else(|| py.None().into_bound(py));
                for item in cs.try_iter()? {
                    let t = item?;
                    let tuple = t.cast::<PyTuple>().map_err(|_| {
                        value_error("path.coordinates entries must be tuples")
                    })?;
                    if tuple.len() == 3 {
                        let x: f64 = tuple.get_item(0)?.extract()?;
                        let y: f64 = tuple.get_item(1)?.extract()?;
                        let l: String = tuple.get_item(2)?.extract()?;
                        coords.push((x, y, Some(l)));
                    } else {
                        let x: f64 = tuple.get_item(0)?.extract()?;
                        let y: f64 = tuple.get_item(1)?.extract()?;
                        coords.push((x, y, None));
                    }
                }
            }
        }
    }

    Ok((coords, default_layer, net))
}

/// `kicad_exporter.path_to_segments` — converts a path to trace segments.
#[pyfunction]
#[pyo3(signature = (path, origin, cell_size, trace_width, layer_map=None))]
pub fn path_to_segments(
    py: Python<'_>,
    path: Bound<'_, PyAny>,
    origin: (f64, f64),
    cell_size: f64,
    trace_width: f64,
    layer_map: Option<Bound<'_, PyDict>>,
) -> PyResult<Py<PyList>> {
    guarded(move || {
        let (coords, default_layer, net) = path_coords(py, &path, origin, cell_size, layer_map.as_ref())?;
        let mut segments: Vec<Py<PyAny>> = Vec::new();
        for i in 0..coords.len().saturating_sub(1) {
            let p1 = &coords[i];
            let p2 = &coords[i + 1];
            let (x1, y1, l1) = match &p1.2 {
                Some(l) => (p1.0, p1.1, l.clone()),
                None => (p1.0, p1.1, default_layer.clone()),
            };
            let (x2, y2, l2) = match &p2.2 {
                Some(l) => (p2.0, p2.1, l.clone()),
                None => (p2.0, p2.1, default_layer.clone()),
            };
            if l1 != l2 {
                continue;
            }
            let seg = Py::new(
                py,
                crate::export_types::PyTraceSegment {
                    net: net.clone(),
                    start: (x1, y1),
                    end: (x2, y2),
                    width: trace_width,
                    layer: l1,
                },
            )?;
            segments.push(seg.into_any());
        }
        Ok(PyList::new(py, segments)?.unbind())
    })
}

/// `kicad_exporter.path_to_vias` — extracts vias from layer transitions.
#[pyfunction]
#[pyo3(signature = (path, origin, cell_size, via_size, via_drill, layer_map=None))]
pub fn path_to_vias(
    py: Python<'_>,
    path: Bound<'_, PyAny>,
    origin: (f64, f64),
    cell_size: f64,
    via_size: f64,
    via_drill: f64,
    layer_map: Option<Bound<'_, PyDict>>,
) -> PyResult<Py<PyList>> {
    guarded(move || {
        let default_layer = get_attr_str(&path, "layer_name", "F.Cu");
        let net_name = get_attr_opt_str(&path, "net_name").filter(|s| !s.is_empty());
        let net = net_name
            .or_else(|| get_attr_opt_str(&path, "net").filter(|s| !s.is_empty()))
            .unwrap_or_else(|| "unknown".to_string());

        let mut coords: Vec<Coord> = Vec::new();

        // cells branch — NOTE: no simplify_path here (verbatim difference
        // from path_to_segments).
        let cells_attr = path.getattr("cells").ok();
        let has_cells = cells_attr
            .as_ref()
            .map(|c| is_truthy(c).unwrap_or(false))
            .unwrap_or(false);
        if has_cells {
            let cells = cells_attr.unwrap_or_else(|| py.None().into_bound(py));
            let path_cell_size = get_attr_f64(&path, "cell_size", cell_size);
            for item in cells.try_iter()? {
                let c = item?;
                let cx = get_attr_i64(&c, "x", 0);
                let cy = get_attr_i64(&c, "y", 0);
                let cl = get_attr_i64(&c, "layer", 0);
                let (x, y) = grid_to_world(cx, cy, origin, path_cell_size);
                let layer_name = layer_map_lookup(layer_map.as_ref(), cl)?;
                coords.push((x, y, Some(layer_name)));
            }
        } else {
            let segs_attr = path.getattr("segments").ok();
            let has_segs = segs_attr
                .as_ref()
                .map(|s| is_truthy(s).unwrap_or(false))
                .unwrap_or(false);
            if has_segs {
                let segs = segs_attr.unwrap_or_else(|| py.None().into_bound(py));
                for item in segs.try_iter()? {
                    let t = item?;
                    let tuple = t
                        .cast::<PyTuple>()
                        .map_err(|_| value_error("path.segments entries must be tuples"))?;
                    if tuple.len() >= 3 {
                        let x: f64 = tuple.get_item(0)?.extract()?;
                        let y: f64 = tuple.get_item(1)?.extract()?;
                        let l: String = tuple.get_item(2)?.extract()?;
                        coords.push((x, y, Some(l)));
                    } else {
                        let x: f64 = tuple.get_item(0)?.extract()?;
                        let y: f64 = tuple.get_item(1)?.extract()?;
                        coords.push((x, y, None));
                    }
                }
            } else {
                let cs_attr = path.getattr("coordinates").ok();
                let has_cs = cs_attr
                    .as_ref()
                    .map(|c| is_truthy(c).unwrap_or(false))
                    .unwrap_or(false);
                if has_cs {
                    let cs = cs_attr.unwrap_or_else(|| py.None().into_bound(py));
                    for item in cs.try_iter()? {
                        let t = item?;
                        let tuple = t
                            .cast::<PyTuple>()
                            .map_err(|_| value_error("path.coordinates entries must be tuples"))?;
                        if tuple.len() >= 3 {
                            let x: f64 = tuple.get_item(0)?.extract()?;
                            let y: f64 = tuple.get_item(1)?.extract()?;
                            let l: String = tuple.get_item(2)?.extract()?;
                            coords.push((x, y, Some(l)));
                        } else {
                            let x: f64 = tuple.get_item(0)?.extract()?;
                            let y: f64 = tuple.get_item(1)?.extract()?;
                            coords.push((x, y, None));
                        }
                    }
                }
            }
        }

        let mut vias: Vec<Py<PyAny>> = Vec::new();
        for i in 1..coords.len() {
            let p1 = &coords[i - 1];
            let p2 = &coords[i];
            let (l1, l2) = match (p1.2.as_ref(), p2.2.as_ref()) {
                (Some(l1), Some(l2)) => (l1.clone(), l2.clone()),
                _ => (default_layer.clone(), default_layer.clone()),
            };
            if l1 != l2 {
                let pos = (p2.0, p2.1);
                let mut all_layers = vec![l1, l2];
                all_layers.sort();
                let via = Py::new(
                    py,
                    crate::export_types::PyTraceVia {
                        net: net.clone(),
                        position: pos,
                        size: via_size,
                        drill: via_drill,
                        layers: all_layers,
                    },
                )?;
                vias.push(via.into_any());
            }
        }
        Ok(PyList::new(py, vias)?.unbind())
    })
}

// ---------------------------------------------------------------------------
// Group B — pad geometry.
// ---------------------------------------------------------------------------

/// `kicad_exporter.extract_pad_centers` — pad centers grouped by net name
/// (footprint rotation applied via R(-theta); iteration order = board
/// footprint/pad order, dict insertion order preserved).
#[pyfunction]
pub fn extract_pad_centers(py: Python<'_>, board: Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        let footprints = board.getattr("footprints").map_err(|_| {
            value_error("board has no footprints attribute")
        })?;
        for item in footprints.try_iter()? {
            let fp = item?;
            let (fp_x, fp_y, fp_angle) = match fp.getattr("position").ok().filter(|p| !p.is_none()) {
                Some(pos) => (
                    get_attr_f64(&pos, "X", 0.0),
                    get_attr_f64(&pos, "Y", 0.0),
                    pos.getattr("angle")
                        .ok()
                        .and_then(|a| a.extract::<f64>().ok())
                        .unwrap_or(0.0),
                ),
                None => (0.0, 0.0, 0.0),
            };
            let rad = radians(fp_angle);
            let pads = match fp.getattr("pads").ok() {
                Some(p) => p,
                None => continue,
            };
            for pitem in pads.try_iter()? {
                let pad = pitem?;
                // net name resolution: pad.net.name if available, else
                // str(pad.net), else "".
                let net_name: String = match pad.getattr("net").ok().filter(|n| !n.is_none()) {
                    Some(net) => {
                        if let Ok(name) = net.getattr("name") {
                            if let Ok(s) = name.extract::<String>() {
                                s
                            } else {
                                continue; // `if not net_name: continue`
                            }
                        } else {
                            net.str()?.to_string()
                        }
                    }
                    None => String::new(),
                };
                if net_name.is_empty() {
                    continue;
                }
                let (rel_x, rel_y) = match pad.getattr("position").ok().filter(|p| !p.is_none()) {
                    Some(pos) => (get_attr_f64(&pos, "X", 0.0), get_attr_f64(&pos, "Y", 0.0)),
                    None => (0.0, 0.0),
                };
                let (rot_x, rot_y) = rotate_local_to_world(rel_x, rel_y, rad);
                let abs_x = fp_x + rot_x;
                let abs_y = fp_y + rot_y;
                match out.get_item(net_name.as_str())? {
                    Some(list) => {
                        let tuple = PyTuple::new(py, [abs_x, abs_y])?;
                        list.call_method1("append", (tuple,))?;
                    }
                    None => {
                        let list = PyList::empty(py);
                        let tuple = PyTuple::new(py, [abs_x, abs_y])?;
                        list.append(tuple)?;
                        out.set_item(net_name.as_str(), list)?;
                    }
                }
            }
        }
        Ok(out.unbind())
    })
}

/// `kicad_exporter.snap_to_nearest_pad`.
#[pyfunction]
#[pyo3(name = "snap_to_nearest_pad", signature = (x, y, pads, tolerance=0.15))]
pub fn snap_to_nearest_pad_py(
    x: f64,
    y: f64,
    pads: Vec<(f64, f64)>,
    tolerance: f64,
) -> PyResult<(f64, f64)> {
    guarded(move || Ok(snap_to_nearest_pad(x, y, &pads, tolerance)))
}

/// `kicad_exporter._generate_connector_segments` — bridge gaps between track
/// endpoints and pad centers. Iteration order = pad_centers dict order then
/// per-net segment order, matching the pinned Python.
#[pyfunction]
#[pyo3(signature = (segments, pad_centers, max_dist=2.0))]
pub fn generate_connector_segments(
    py: Python<'_>,
    segments: Bound<'_, PyAny>,
    pad_centers: Bound<'_, PyDict>,
    max_dist: f64,
) -> PyResult<Py<PyList>> {
    guarded(move || {
        // net -> list of (start, end, width, layer) in first-appearance order.
        let mut segs_by_net: Vec<(String, Vec<(f64, f64, f64, f64, f64, String)>)> = Vec::new();
        for item in segments.try_iter()? {
            let seg = item?;
            let net: String = get_attr_str(&seg, "net", "");
            let start = get_xy(&seg.getattr("start")?).unwrap_or((0.0, 0.0));
            let end = get_xy(&seg.getattr("end")?).unwrap_or((0.0, 0.0));
            let width = get_attr_f64(&seg, "width", 0.0);
            let layer = get_attr_str(&seg, "layer", "F.Cu");
            match segs_by_net.iter_mut().find(|(n, _)| n == &net) {
                Some((_, list)) => list.push((start.0, start.1, end.0, end.1, width, layer)),
                None => {
                    segs_by_net.push((net, vec![(start.0, start.1, end.0, end.1, width, layer)]));
                }
            }
        }

        let mut connectors: Vec<Py<PyAny>> = Vec::new();
        for (net, pads) in pad_centers.iter() {
            let net_str: String = net.extract()?;
            let net_segs = match segs_by_net.iter().find(|(n, _)| n == &net_str) {
                Some((_, l)) => l,
                None => continue,
            };
            // endpoints set (bit-exact tuple membership)
            let mut endpoints: Vec<(f64, f64)> = Vec::new();
            for s in net_segs {
                let st = (s.0, s.1);
                let en = (s.2, s.3);
                if !endpoints.contains(&st) {
                    endpoints.push(st);
                }
                if !endpoints.contains(&en) {
                    endpoints.push(en);
                }
            }
            for pitem in pads.try_iter()? {
                let pad = pitem?;
                let (px_, py_): (f64, f64) = pad.extract()?;
                // Already connected? (abs < 0.01 on both axes)
                let mut is_connected = false;
                for &(ex, ey) in &endpoints {
                    if (ex - px_).abs() < 0.01 && (ey - py_).abs() < 0.01 {
                        is_connected = true;
                        break;
                    }
                }
                if is_connected {
                    continue;
                }
                // Nearest endpoint
                let mut nearest_ep: Option<(f64, f64)> = None;
                let mut min_dist = f64::INFINITY;
                for &(ex, ey) in &endpoints {
                    let dx = ex - px_;
                    let dy = ey - py_;
                    let dist = (dx * dx + dy * dy).sqrt();
                    if dist < min_dist {
                        min_dist = dist;
                        nearest_ep = Some((ex, ey));
                    }
                }
                if let Some(nearest) = nearest_ep
                    && min_dist < max_dist
                {
                    // First segment in list order having this endpoint.
                    let ref_seg = net_segs.iter().find(|s| {
                        ((s.0, s.1) == nearest) || ((s.2, s.3) == nearest)
                    });
                    if let Some(rs) = ref_seg {
                        let seg = Py::new(
                            py,
                            crate::export_types::PyTraceSegment {
                                net: net_str.clone(),
                                start: nearest,
                                end: (px_, py_),
                                width: rs.4,
                                layer: rs.5.clone(),
                            },
                        )?;
                        connectors.push(seg.into_any());
                        endpoints.push((px_, py_));
                    }
                }
            }
        }
        Ok(PyList::new(py, connectors)?.unbind())
    })
}

// ---------------------------------------------------------------------------
// Group C — layer validation.
// ---------------------------------------------------------------------------

/// `kicad_exporter._validate_4_layer_output` decision: returns
/// `("ok"|"warn"|"raise", message)`. The shim performs the Python-side
/// `logging.warning` / `RuntimeError` raising using the returned decision and
/// message (both formatted here so the strings match the pinned Python).
#[pyfunction]
pub fn validate_4_layer_output(_py: Python<'_>, board: Bound<'_, PyAny>) -> PyResult<(String, String)> {
    guarded(move || {
        let layers = board
            .getattr("layers")
            .map_err(|_| PyRuntimeError::new_err("KiCad board has no layers attribute — cannot validate layer count"))?;
        let mut copper_names: Vec<String> = Vec::new();
        for item in layers.try_iter()? {
            let ly = item?;
            if let Ok(name) = ly.getattr("name")
                && let Ok(s) = name.extract::<String>()
                    && s.ends_with(".Cu") {
                        copper_names.push(s);
                    }
        }
        if copper_names.len() != 4 {
            let canonical_sorted = "['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu']";
            let msg = format!(
                "Board has {} copper layers (canonical 4-layer stackup: {}). Proceeding — non-4-layer boards are valid for test fixtures and prototypes.",
                copper_names.len(),
                canonical_sorted
            );
            return Ok(("warn".to_string(), msg));
        }
        let mut sorted_names = copper_names.clone();
        sorted_names.sort();
        sorted_names.dedup();
        let mut canonical = CANONICAL_4LAYER_LAYER_NAMES.to_vec();
        canonical.sort();
        if sorted_names != canonical {
            let got = sorted_names
                .iter()
                .map(|s| format!("'{}'", s))
                .collect::<Vec<_>>()
                .join(", ");
            let msg = format!(
                "Copper layer names must match canonical set ['B.Cu', 'F.Cu', 'In1.Cu', 'In2.Cu'], got [{}]",
                got
            );
            return Ok(("raise".to_string(), msg));
        }
        Ok(("ok".to_string(), String::new()))
    })
}

// ---------------------------------------------------------------------------
// Group D — placements.
// ---------------------------------------------------------------------------

/// `_write_board.state_to_placements` kernel. `positions`/`rotation_indices`
/// are extracted by the shim from the (numpy-backed) `PlacementState`; the
/// rotation/center-offset math runs here.
#[pyfunction]
#[pyo3(signature = (positions, rotation_indices, component_refs, origin, center_offsets=None, original_angles=None))]
pub fn state_to_placements(
    py: Python<'_>,
    positions: Vec<(f64, f64)>,
    rotation_indices: Vec<i64>,
    component_refs: Vec<String>,
    origin: (f64, f64),
    center_offsets: Option<Bound<'_, PyDict>>,
    original_angles: Option<Bound<'_, PyDict>>,
) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for (i, ref_) in component_refs.iter().enumerate() {
            let rot_idx = *rotation_indices.get(i).unwrap_or(&0);
            let mut rotation_deg = rot_idx as f64 * 90.0;
            if let Some(angles) = original_angles.as_ref()
                && !angles.is_empty()
                && angles.contains(ref_.as_str())?
            {
                let original: f64 = match angles.get_item(ref_.as_str())? {
                    Some(v) => v.extract()?,
                    None => continue,
                };
                let quantized = py_round_ties_even(original / 90.0) * 90.0;
                let offset = original - quantized;
                if offset.abs() > 0.1 {
                    rotation_deg = py_mod(rotation_deg + offset, 360.0);
                }
            }
            let (px, py_) = *positions.get(i).unwrap_or(&(0.0, 0.0));
            let mut x = px + origin.0;
            let mut y = py_ + origin.1;
            if let Some(offsets) = center_offsets.as_ref()
                && offsets.contains(ref_.as_str())?
            {
                let (cx, cy): (f64, f64) = match offsets.get_item(ref_.as_str())? {
                    Some(v) => v.extract()?,
                    None => continue,
                };
                let rot_rad = radians(rotation_deg);
                let (rotated_cx, rotated_cy) = rotate_local_to_world(cx, cy, rot_rad);
                x -= rotated_cx;
                y -= rotated_cy;
            }
            let update = Py::new(
                py,
                PyPlacementUpdate {
                    ref_: ref_.clone(),
                    x,
                    y,
                    rotation: rotation_deg,
                },
            )?;
            out.set_item(ref_.as_str(), update)?;
        }
        Ok(out.unbind())
    })
}

/// `_write_board.extract_original_angles` — reads `_original_angle` off
/// component attribute dicts (`float()` with `ValueError`/`TypeError`
/// suppressed).
#[pyfunction]
pub fn extract_original_angles(
    py: Python<'_>,
    components: Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for item in components.try_iter()? {
            let comp = item?;
            if let Ok(attrs) = comp.getattr("attributes") {
                // `"_original_angle" in comp.attributes` — Python `in`.
                let contains = attrs
                    .contains("_original_angle")
                    .map_err(|_| value_error("attributes does not support __contains__"))?;
                if contains {
                    let key = comp.getattr("ref").and_then(|r| r.extract::<String>());
                    if let Ok(ref_) = key
                        && let Ok(v) = attrs.get_item("_original_angle")
                            && let Ok(f) = py_float(&v) {
                                out.set_item(ref_.as_str(), f)?;
                            }
                }
            }
        }
        Ok(out.unbind())
    })
}

/// `_write_board.state_to_placements`'s (and `write_placements_to_pcb`'s)
/// center-offset map builder: `ref -> (cx, cy)` for components whose
/// `_center_offset_x`/`_center_offset_y` attributes are non-zero (float()
/// semantics; a missing key defaults to "0", a non-numeric value raises
/// ValueError exactly like the pinned Python).
#[pyfunction]
pub fn extract_center_offsets(
    py: Python<'_>,
    components: Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for item in components.try_iter()? {
            let comp = item?;
            let attrs_ok = comp.getattr("attributes").ok();
            let attrs_truthy = attrs_ok
                .as_ref()
                .map(|a| is_truthy(a).unwrap_or(false))
                .unwrap_or(false);
            if attrs_truthy {
                let attrs = attrs_ok.unwrap_or_else(|| py.None().into_bound(py));
                let ref_: String = match comp.getattr("ref").and_then(|r| r.extract::<String>()) {
                    Ok(r) => r,
                    Err(_) => continue,
                };
                let cx = match attrs.get_item("_center_offset_x") {
                    Ok(v) => py_float(&v)?,
                    Err(_) => 0.0,
                };
                let cy = match attrs.get_item("_center_offset_y") {
                    Ok(v) => py_float(&v)?,
                    Err(_) => 0.0,
                };
                if cx != 0.0 || cy != 0.0 {
                    out.set_item(ref_.as_str(), (cx, cy))?;
                }
            }
        }
        Ok(out.unbind())
    })
}

/// `placement_exporter.positions_to_placements` kernel (rotation indices
/// pre-computed by `np.argmax` on the shim side).
#[pyfunction]
#[pyo3(signature = (positions, rotation_indices, component_refs, origin))]
pub fn positions_to_placements(
    py: Python<'_>,
    positions: Vec<(f64, f64)>,
    rotation_indices: Vec<i64>,
    component_refs: Vec<String>,
    origin: (f64, f64),
) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for (i, ref_) in component_refs.iter().enumerate() {
            let rot_idx = *rotation_indices.get(i).unwrap_or(&0);
            let rotation_deg = rot_idx as f64 * 90.0;
            let (px, py_) = *positions.get(i).unwrap_or(&(0.0, 0.0));
            let x = px + origin.0;
            let y = py_ + origin.1;
            let update = Py::new(
                py,
                PyPlacementUpdate {
                    ref_: ref_.clone(),
                    x,
                    y,
                    rotation: rotation_deg,
                },
            )?;
            out.set_item(ref_.as_str(), update)?;
        }
        Ok(out.unbind())
    })
}

/// `placement_exporter.rotation_index_to_degrees`: `float(index) * 90.0`.
#[pyfunction]
pub fn rotation_index_to_degrees(index: i64) -> PyResult<f64> {
    guarded(move || Ok(index as f64 * 90.0))
}

/// `_write_board._reorient_pads` per-pad kernel: a pad's absolute angle is
/// its current angle plus the footprint's rotation delta, modulo 360; a
/// result of exactly 0.0 is written as `None` (kiutils omits the angle
/// token; an absent angle means 0 in KiCad).
#[pyfunction]
#[pyo3(signature = (current_angle, delta_deg))]
pub fn reorient_pad_angle(current_angle: Option<f64>, delta_deg: f64) -> PyResult<Option<f64>> {
    guarded(move || {
        let current = current_angle.unwrap_or(0.0);
        let new_angle = py_mod(current + delta_deg, 360.0);
        Ok(if new_angle == 0.0 { None } else { Some(new_angle) })
    })
}

// ---------------------------------------------------------------------------
// Group E — JSON helpers / isolation slots.
// ---------------------------------------------------------------------------

/// `kicad_writer.placements_to_json`: each `update`'s `x`/`y`/`rotation`
/// values are passed through as the SAME Python objects (no float coercion,
/// so an int `x` stays an int in the JSON dict — bit/type parity with the
/// pinned Python).
#[pyfunction]
pub fn placements_to_json(py: Python<'_>, placements: Bound<'_, PyDict>) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for (ref_, update) in placements.iter() {
            let inner = PyDict::new(py);
            let x = update.getattr("x")?;
            let y = update.getattr("y")?;
            let rotation = update.getattr("rotation")?;
            inner.set_item("x", x)?;
            inner.set_item("y", y)?;
            inner.set_item("rotation", rotation)?;
            out.set_item(ref_, inner)?;
        }
        Ok(out.unbind())
    })
}

/// `kicad_writer.placements_from_json`: `float()` each value and build
/// `PlacementUpdate`s.
#[pyfunction]
pub fn placements_from_json(py: Python<'_>, data: Bound<'_, PyDict>) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for (ref_, values) in data.iter() {
            let v = values.cast::<PyDict>().map_err(|_| {
                value_error("placements_from_json entries must be dicts")
            })?;
            let x = py_float(&v.get_item("x")?.ok_or_else(|| value_error("missing 'x'"))?)?;
            let y = py_float(&v.get_item("y")?.ok_or_else(|| value_error("missing 'y'"))?)?;
            let rotation = py_float(
                &v.get_item("rotation")?
                    .ok_or_else(|| value_error("missing 'rotation'"))?,
            )?;
            let ref_str: String = ref_.extract()?;
            let update = Py::new(
                py,
                PyPlacementUpdate {
                    ref_: ref_str,
                    x,
                    y,
                    rotation,
                },
            )?;
            out.set_item(ref_, update)?;
        }
        Ok(out.unbind())
    })
}

/// `_write_board.compute_to247_isolation_slots` kernel — returns raw slot
/// specs; the shim constructs the `config_loader.IsolationSlot` objects.
#[pyfunction]
#[pyo3(signature = (component_refs, slot_width_mm=1.5, slot_length_mm=10.0))]
pub fn compute_to247_isolation_slots(
    py: Python<'_>,
    component_refs: Vec<String>,
    slot_width_mm: f64,
    slot_length_mm: f64,
) -> PyResult<Py<PyList>> {
    guarded(move || {
        // TO-247 pin geometry: pin 1 to pin 2 center-to-center 5.45 mm.
        let slot_x_offset = -5.45 / 2.0;
        let mut slots: Vec<Py<PyAny>> = Vec::new();
        for ref_ in &component_refs {
            let name = format!("{}_gate_isolation", ref_.to_ascii_lowercase());
            let start = (slot_x_offset, -slot_length_mm / 2.0);
            let end = (slot_x_offset, slot_length_mm / 2.0);
            let spec = PyTuple::new(
                py,
                [
                    name.into_pyobject(py)?.into_any(),
                    ref_.clone().into_pyobject(py)?.into_any(),
                    PyTuple::new(py, [start.0, start.1])?.into_any(),
                    PyTuple::new(py, [end.0, end.1])?.into_any(),
                    slot_width_mm.into_pyobject(py)?.into_any(),
                    "1".into_pyobject(py)?.into_any(),
                    "2".into_pyobject(py)?.into_any(),
                    format!("IEC 60335-1 creepage isolation for {} gate", ref_)
                        .into_pyobject(py)?
                        .into_any(),
                ],
            )?;
            slots.push(spec.into_any().unbind());
        }
        Ok(PyList::new(py, slots)?.unbind())
    })
}

// ---------------------------------------------------------------------------
// Group F — footprint / statistics readers.
// ---------------------------------------------------------------------------

/// `_write_types._get_footprint_reference`: extract the reference designator
/// from a footprint's properties (dict or list) or graphic items.
#[pyfunction]
pub fn get_footprint_reference(py: Python<'_>, fp: Bound<'_, PyAny>) -> PyResult<Option<String>> {
    guarded(move || {
        let props = fp
            .getattr("properties")
            .ok()
            .filter(|p| !p.is_none())
            .unwrap_or_else(|| py.None().into_bound(py));
        if let Ok(d) = props.cast::<PyDict>() {
            let ref_val = d.get_item("Reference")?;
            let ref_truthy = ref_val
                .as_ref()
                .map(|r| is_truthy(r).unwrap_or(false))
                .unwrap_or(false);
            if ref_truthy {
                let ref_ = ref_val.unwrap_or_else(|| py.None().into_bound(py));
                if let Ok(s) = ref_.extract::<String>() {
                    return Ok(Some(s));
                }
                return Ok(Some(ref_.str()?.to_string()));
            }
        } else if let Ok(list) = props.try_iter() {
            for item in list {
                let prop = item?;
                if let Ok(key) = prop.getattr("key")
                    && key.eq("Reference")?
                        && let Ok(v) = prop.getattr("value")
                            && let Ok(s) = v.extract::<String>() {
                                return Ok(Some(s));
                            }
            }
        }
        if let Ok(items) = fp.getattr("graphicItems") {
            for item in items.try_iter()? {
                let g = item?;
                if let Ok(ty) = g.getattr("type")
                    && ty.eq("reference")?
                        && let Ok(text) = g.getattr("text")
                            && let Ok(s) = text.extract::<String>() {
                                return Ok(Some(s));
                            }
            }
        }
        Ok(None)
    })
}

/// The shared pad-bounds kernel behind `add_bounding_boxes_to_pcb` and
/// `add_silkscreen_labels` (identical loops in the pinned Python): absolute
/// (x_min, y_min, x_max, y_max) over a footprint's pads, rotating local pad
/// offsets by the footprint angle when `abs(angle) > 0.1`.
#[pyfunction]
pub fn compute_pad_bounds(_py: Python<'_>, fp: Bound<'_, PyAny>) -> PyResult<Option<(f64, f64, f64, f64)>> {
    guarded(move || {
        let fp_x = match fp.getattr("position").ok().filter(|p| !p.is_none()) {
            Some(pos) => get_attr_f64(&pos, "X", 0.0),
            None => 0.0,
        };
        let fp_y = match fp.getattr("position").ok().filter(|p| !p.is_none()) {
            Some(pos) => get_attr_f64(&pos, "Y", 0.0),
            None => 0.0,
        };
        let fp_angle = match fp.getattr("position").ok().filter(|p| !p.is_none()) {
            Some(pos) => pos
                .getattr("angle")
                .ok()
                .and_then(|a| a.extract::<f64>().ok())
                .unwrap_or(0.0),
            None => 0.0,
        };
        let angle_rad = radians(fp_angle);
        let pads = match fp.getattr("pads").ok() {
            Some(p) => p,
            None => return Ok(None),
        };
        let mut x_min = f64::INFINITY;
        let mut y_min = f64::INFINITY;
        let mut x_max = f64::NEG_INFINITY;
        let mut y_max = f64::NEG_INFINITY;
        let mut any = false;
        for item in pads.try_iter()? {
            let pad = item?;
            any = true;
            let local_x = match pad.getattr("position").ok().filter(|p| !p.is_none()) {
                Some(pos) => get_attr_f64(&pos, "X", 0.0),
                None => 0.0,
            };
            let local_y = match pad.getattr("position").ok().filter(|p| !p.is_none()) {
                Some(pos) => get_attr_f64(&pos, "Y", 0.0),
                None => 0.0,
            };
            let (rotated_x, rotated_y) = if fp_angle.abs() > 0.1 {
                rotate_local_to_world(local_x, local_y, angle_rad)
            } else {
                (local_x, local_y)
            };
            let pad_w = match pad.getattr("size").ok().filter(|s| !s.is_none()) {
                Some(size) => get_attr_f64(&size, "X", 1.0),
                None => 1.0,
            };
            let pad_h = match pad.getattr("size").ok().filter(|s| !s.is_none()) {
                Some(size) => get_attr_f64(&size, "Y", 1.0),
                None => 1.0,
            };
            let abs_x = fp_x + rotated_x;
            let abs_y = fp_y + rotated_y;
            x_min = x_min.min(abs_x - pad_w / 2.0);
            y_min = y_min.min(abs_y - pad_h / 2.0);
            x_max = x_max.max(abs_x + pad_w / 2.0);
            y_max = y_max.max(abs_y + pad_h / 2.0);
        }
        if !any {
            return Ok(None);
        }
        Ok(Some((x_min, y_min, x_max, y_max)))
    })
}

/// `_write_tracks.get_routing_statistics`: trace/via/zone/component/net counts
/// with `type(item).__name__` classification.
#[pyfunction]
pub fn get_routing_statistics(py: Python<'_>, board: Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        let mut trace_count: usize = 0;
        let mut via_count: usize = 0;
        if let Ok(items) = board.getattr("traceItems")
            && is_truthy(&items)?
        {
            for item in items.try_iter()? {
                let it = item?;
                let name = type_name(&it)?;
                if name == "Segment" || name == "Arc" {
                    trace_count += 1;
                } else if name == "Via" {
                    via_count += 1;
                }
            }
        }
        let zones_len = board
            .getattr("zones")
            .ok()
            .filter(|z| is_truthy(z).unwrap_or(false))
            .map(|z| z.len().unwrap_or(0))
            .unwrap_or(0);
        let footprints_len = board
            .getattr("footprints")
            .ok()
            .filter(|z| is_truthy(z).unwrap_or(false))
            .map(|z| z.len().unwrap_or(0))
            .unwrap_or(0);
        let nets_len = board
            .getattr("nets")
            .ok()
            .filter(|z| is_truthy(z).unwrap_or(false))
            .map(|z| z.len().unwrap_or(0))
            .unwrap_or(0);
        out.set_item("traces", trace_count)?;
        out.set_item("vias", via_count)?;
        out.set_item("zones", zones_len)?;
        out.set_item("components", footprints_len)?;
        out.set_item("nets", nets_len)?;
        Ok(out.unbind())
    })
}

/// `_write_zones.build_net_name_to_index_map` (also the inline net-map build
/// in `write_routes_to_pcb`): net name -> net number for nets exposing both.
#[pyfunction]
pub fn net_name_to_index_map(py: Python<'_>, nets: Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    guarded(move || {
        let out = PyDict::new(py);
        for item in nets.try_iter()? {
            let net = item?;
            if let (Ok(name), Ok(number)) = (net.getattr("name"), net.getattr("number"))
                && let (Ok(ns), Ok(ni)) = (name.extract::<String>(), number.extract::<i64>()) {
                    out.set_item(ns, ni)?;
                }
        }
        Ok(out.unbind())
    })
}

// ---------------------------------------------------------------------------
// Group G — orchestration plans (full-function differentials).
// ---------------------------------------------------------------------------

/// `kicad_exporter.export_routed_pcb` kernel: per-net segment/via generation
/// (with `explicit_vias` passthrough), via dedup on the
/// `(round(x,3), round(y,3), sorted(layers))` key (first wins, order
/// preserved), pad-center extraction and connector generation. Returns
/// `(segments, unique_vias, connectors, nets_exported, nets_failed,
/// warnings)`.
#[pyfunction]
#[pyo3(signature = (board, routes, trace_widths=None, default_trace_width=0.25, via_size=0.8, via_drill=0.4, origin=(0.0,0.0), cell_size=1.0, layer_map=None))]
pub fn export_route_plan(
    py: Python<'_>,
    board: Bound<'_, PyAny>,
    routes: Bound<'_, PyDict>,
    trace_widths: Option<Bound<'_, PyDict>>,
    default_trace_width: f64,
    via_size: f64,
    via_drill: f64,
    origin: (f64, f64),
    cell_size: f64,
    layer_map: Option<Bound<'_, PyDict>>,
) -> PyResult<(Py<PyList>, Py<PyList>, Py<PyList>, usize, usize, Py<PyList>)> {
    guarded(move || {
        let mut all_segments: Vec<Py<PyAny>> = Vec::new();
        let mut all_vias: Vec<Py<PyAny>> = Vec::new();
        let mut nets_exported: usize = 0;
        let mut nets_failed: usize = 0;
        let warnings = PyList::empty(py);

        for (net_name, path) in routes.iter() {
            let net_str: String = net_name.extract()?;
            // `if hasattr(path, "success") and not path.success`
            let failed = path
                .getattr("success")
                .ok()
                .map(|s| is_truthy(&s).unwrap_or(true))
                .map(|v| !v)
                .unwrap_or(false);
            if failed {
                nets_failed += 1;
                let reason = get_attr_str(&path, "failure_reason", "unknown");
                warnings.append(format!("Net {} routing failed: {}", net_str, reason))?;
                continue;
            }
            let trace_width = match trace_widths.as_ref() {
                Some(tw) if !tw.is_empty() => tw
                    .get_item(net_str.as_str())?
                    .map(|v| v.extract::<f64>().unwrap_or(default_trace_width))
                    .unwrap_or(default_trace_width),
                _ => default_trace_width,
            };
            let current_cell_size = get_attr_f64(&path, "cell_size", cell_size);
            let segments = path_to_segments(
                py,
                path.clone(),
                origin,
                current_cell_size,
                trace_width,
                layer_map.clone(),
            )?;
            // `if hasattr(path, "explicit_vias") and path.explicit_vias`
            let explicit = path
                .getattr("explicit_vias")
                .ok()
                .filter(|v| is_truthy(v).unwrap_or(false));
            let vias: Py<PyList> = if let Some(ev) = explicit {
                ev.cast::<PyList>()
                    .map_err(|_| value_error("explicit_vias must be a list"))?
                    .clone()
                    .unbind()
            } else {
                path_to_vias(
                    py,
                    path.clone(),
                    origin,
                    current_cell_size,
                    via_size,
                    via_drill,
                    layer_map.clone(),
                )?
            };
            for item in segments.bind(py).try_iter()? {
                all_segments.push(item?.unbind());
            }
            for item in vias.bind(py).try_iter()? {
                all_vias.push(item?.unbind());
            }
            nets_exported += 1;
        }

        // Via dedup: key = (round(x, 3), round(y, 3), sorted(layers)), first
        // wins, insertion order preserved. f64 equality in the key (not raw
        // bits) matches Python tuple equality: -0.0 == 0.0, and hash(-0.0) ==
        // hash(0.0), so a -0.0 and 0.0 key are the SAME key in Python.
        let mut unique_vias: Vec<Py<PyAny>> = Vec::new();
        let mut seen: Vec<(f64, f64, Vec<String>)> = Vec::new();
        for v in &all_vias {
            let v = v.bind(py).clone();
            let pos = get_xy(&v.getattr("position")?).unwrap_or((0.0, 0.0));
            let key_x = py_round_ndigits(pos.0, 3);
            let key_y = py_round_ndigits(pos.1, 3);
            let mut layers: Vec<String> = Vec::new();
            if let Ok(ls) = v.getattr("layers") {
                for l in ls.try_iter()? {
                    if let Ok(s) = l?.extract::<String>() {
                        layers.push(s);
                    }
                }
            }
            layers.sort();
            let key = (key_x, key_y, layers.clone());
            if !seen.contains(&key) {
                seen.push(key);
                unique_vias.push(v.clone().unbind());
            }
        }

        let pad_centers = extract_pad_centers(py, board.clone())?;
        let connectors = generate_connector_segments(
            py,
            PyList::new(py, all_segments.iter().map(|s| s.bind(py).clone()).collect::<Vec<_>>())?
                .into_any(),
            pad_centers.bind(py).clone(),
            2.0,
        )?;

        Ok((
            PyList::new(py, all_segments)?.unbind(),
            PyList::new(py, unique_vias)?.unbind(),
            connectors,
            nets_exported,
            nets_failed,
            warnings.unbind(),
        ))
    })
}

/// `kicad_exporter.export_board_state` kernel: zero-length-trace rejection,
/// pad-center snapping, via conversion + dedup on the via_dedup key
/// (`round(x/0.001)*0.001`). Returns `(clean_traces, snapped_count,
/// unique_vias, nets_exported)`.
#[pyfunction]
pub fn export_board_state_plan(
    py: Python<'_>,
    board: Bound<'_, PyAny>,
    traces: Bound<'_, PyAny>,
    vias: Bound<'_, PyAny>,
) -> PyResult<(Py<PyList>, usize, Py<PyList>, usize)> {
    guarded(move || {
        let pad_centers = extract_pad_centers(py, board)?;

        let mut clean_traces: Vec<Py<PyAny>> = Vec::new();
        let mut snapped_count: usize = 0;
        for item in traces.try_iter()? {
            let t = item?;
            let start = get_xy(&t.getattr("start")?).unwrap_or((0.0, 0.0));
            let end = get_xy(&t.getattr("end")?).unwrap_or((0.0, 0.0));
            let dx = start.0 - end.0;
            let dy = start.1 - end.1;
            let length = (dx * dx + dy * dy).sqrt();
            if length <= 0.001 {
                continue;
            }
            let net: String = get_attr_str(&t, "net", "");
            let width = get_attr_f64(&t, "width", 0.0);
            let layer = get_attr_str(&t, "layer", "F.Cu");
            let mut new_start = start;
            let mut new_end = end;
            if let Some(pads) = pad_centers.bind(py).get_item(net.as_str())? {
                let pads_vec: Vec<(f64, f64)> = pads
                    .try_iter()?
                    .filter_map(|p| p.ok().and_then(|v| v.extract::<(f64, f64)>().ok()))
                    .collect();
                new_start = snap_to_nearest_pad(start.0, start.1, &pads_vec, 0.15);
                new_end = snap_to_nearest_pad(end.0, end.1, &pads_vec, 0.15);
                if new_start != start || new_end != end {
                    snapped_count += 1;
                }
            }
            let seg = Py::new(
                py,
                crate::export_types::PyTraceSegment {
                    net: net.clone(),
                    start: new_start,
                    end: new_end,
                    width,
                    layer,
                },
            )?;
            clean_traces.push(seg.into_any());
        }

        // via conversion + dedup (via_dedup.deduplicate_vias semantics:
        // key = (round(x/0.001)*0.001, round(y/0.001)*0.001), first wins).
        let mut unique_vias: Vec<Py<PyAny>> = Vec::new();
        let mut seen: Vec<(f64, f64)> = Vec::new();
        for item in vias.try_iter()? {
            let v = item?;
            let net: String = get_attr_str(&v, "net", "");
            let pos = get_xy(&v.getattr("position")?).unwrap_or((0.0, 0.0));
            let width = get_attr_f64(&v, "width", 0.0);
            let drill = get_attr_f64(&v, "drill", 0.0);
            let mut layers: Vec<String> = Vec::new();
            if let Ok(ls) = v.getattr("layers") {
                for l in ls.try_iter()? {
                    if let Ok(s) = l?.extract::<String>() {
                        layers.push(s);
                    }
                }
            }
            let key = (
                py_round_ties_even(pos.0 / 0.001) * 0.001,
                py_round_ties_even(pos.1 / 0.001) * 0.001,
            );
            if !seen.contains(&key) {
                seen.push(key);
                let via = Py::new(
                    py,
                    crate::export_types::PyTraceVia {
                        net,
                        position: pos,
                        size: width,
                        drill,
                        layers,
                    },
                )?;
                unique_vias.push(via.into_any());
            }
        }

        // nets_exported = len({t.net for t in clean_traces})
        let mut nets: Vec<String> = Vec::new();
        for t in &clean_traces {
            let net = get_attr_str(t.bind(py), "net", "");
            if !nets.contains(&net) {
                nets.push(net);
            }
        }

        Ok((
            PyList::new(py, clean_traces)?.unbind(),
            snapped_count,
            PyList::new(py, unique_vias)?.unbind(),
            nets.len(),
        ))
    })
}

/// `_write_tracks.strip_routing` kernel: classify trace items by type name,
/// decide zone handling. Returns `(traces_removed, vias_removed,
/// zones_removed, keep_indices, clear_fills, warnings)` — the shim rebuilds
/// `traceItems` from `keep_indices` and clears `filledPolygons` when
/// `clear_fills`.
#[pyfunction]
#[pyo3(signature = (trace_items, zones, keep_zones=true, keep_fills=false))]
pub fn strip_routing_plan(
    py: Python<'_>,
    trace_items: Bound<'_, PyAny>,
    zones: Bound<'_, PyAny>,
    keep_zones: bool,
    keep_fills: bool,
) -> PyResult<(usize, usize, usize, Py<PyList>, bool, Py<PyList>)> {
    guarded(move || {
        let mut traces_removed: usize = 0;
        let mut vias_removed: usize = 0;
        let warnings = PyList::empty(py);
        let mut keep_indices: Vec<usize> = Vec::new();
        if is_truthy(&trace_items)? {
            for (idx, item) in trace_items.try_iter()?.enumerate() {
                let it = item?;
                let name = type_name(&it)?;
                if name == "Segment" || name == "Arc" {
                    traces_removed += 1;
                } else if name == "Via" {
                    vias_removed += 1;
                } else {
                    warnings.append(format!("Unknown traceItem type preserved: {}", name))?;
                    keep_indices.push(idx);
                }
            }
        }
        let mut zones_removed: usize = 0;
        let mut clear_fills = false;
        if is_truthy(&zones)? {
            if !keep_zones {
                zones_removed = zones.len()?;
            } else if !keep_fills {
                clear_fills = true;
            }
        }
        Ok((
            traces_removed,
            vias_removed,
            zones_removed,
            PyList::new(py, keep_indices)?.unbind(),
            clear_fills,
            warnings.unbind(),
        ))
    })
}

/// `_write_tracks.write_routes_to_pcb` kernel: net-index resolution,
/// per-route warning generation, and Segment/Via specs. Returns
/// `(net_name_to_index, segment_specs, via_specs, warnings)` where each spec
/// is a 5-tuple `(net, x1, y1, x2, y2, width, layer, net_index)` — the shim
/// constructs the kiutils items.
#[pyfunction]
#[pyo3(signature = (nets, routes, vias=None, net_name_to_index=None, clear_existing=false, original_trace_count=0))]
pub fn write_routes_plan(
    py: Python<'_>,
    nets: Bound<'_, PyAny>,
    routes: Bound<'_, PyAny>,
    vias: Option<Bound<'_, PyAny>>,
    net_name_to_index: Option<Bound<'_, PyDict>>,
    clear_existing: bool,
    original_trace_count: usize,
) -> PyResult<(Py<PyDict>, Py<PyList>, Py<PyList>, Py<PyList>)> {
    guarded(move || {
        let warnings = PyList::empty(py);
        let net_map = match net_name_to_index {
            Some(m) if !m.is_empty() => m,
            _ => net_name_to_index_map(py, nets)?.bind(py).clone(),
        };

        if clear_existing && original_trace_count > 0 {
            warnings.append(format!(
                "Cleared {} existing trace items",
                original_trace_count
            ))?;
        }

        let mut segment_specs: Vec<Py<PyAny>> = Vec::new();
        for item in routes.try_iter()? {
            let route = item?;
            let net: String = get_attr_str(&route, "net", "");
            let mut net_index: i64 = 0;
            if !net.is_empty() {
                if let Some(v) = net_map.get_item(net.as_str())? {
                    net_index = v.extract::<i64>().unwrap_or(0);
                } else {
                    warnings.append(format!("Net '{}' not found in board, using index 0", net))?;
                }
            }
            let start = get_xy(&route.getattr("start")?).unwrap_or((0.0, 0.0));
            let end = get_xy(&route.getattr("end")?).unwrap_or((0.0, 0.0));
            let width = get_attr_f64(&route, "width", 0.0);
            let layer = get_attr_str(&route, "layer", "F.Cu");
            let spec = PyTuple::new(
                py,
                [
                    net.into_pyobject(py)?.into_any(),
                    start.0.into_pyobject(py)?.into_any(),
                    start.1.into_pyobject(py)?.into_any(),
                    end.0.into_pyobject(py)?.into_any(),
                    end.1.into_pyobject(py)?.into_any(),
                    width.into_pyobject(py)?.into_any(),
                    layer.into_pyobject(py)?.into_any(),
                    net_index.into_pyobject(py)?.into_any(),
                ],
            )?;
            segment_specs.push(spec.into_any().unbind());
        }

        let mut via_specs: Vec<Py<PyAny>> = Vec::new();
        if let Some(vs) = vias {
            for item in vs.try_iter()? {
                let via = item?;
                let net: String = get_attr_str(&via, "net", "");
                let mut net_index: i64 = 0;
                if !net.is_empty()
                    && let Some(v) = net_map.get_item(net.as_str())? {
                        net_index = v.extract::<i64>().unwrap_or(0);
                    }
                let pos = get_xy(&via.getattr("position")?).unwrap_or((0.0, 0.0));
                let width = get_attr_f64(&via, "width", 0.0);
                let drill = get_attr_f64(&via, "drill", 0.0);
                let mut layers: Vec<String> = Vec::new();
                if let Ok(ls) = via.getattr("layers") {
                    for l in ls.try_iter()? {
                        if let Ok(s) = l?.extract::<String>() {
                            layers.push(s);
                        }
                    }
                }
                let layers_list = PyList::new(py, layers)?;
                let spec = PyTuple::new(
                    py,
                    [
                        net.into_pyobject(py)?.into_any(),
                        pos.0.into_pyobject(py)?.into_any(),
                        pos.1.into_pyobject(py)?.into_any(),
                        width.into_pyobject(py)?.into_any(),
                        drill.into_pyobject(py)?.into_any(),
                        layers_list.into_any(),
                        net_index.into_pyobject(py)?.into_any(),
                    ],
                )?;
                via_specs.push(spec.into_any().unbind());
            }
        }

        Ok((
            net_map.unbind(),
            PyList::new(py, segment_specs)?.unbind(),
            PyList::new(py, via_specs)?.unbind(),
            warnings.unbind(),
        ))
    })
}

/// `_write_zones.write_zones_to_pcb` kernel: net-index resolution + zone
/// specs `(net_name, net_index, layer, pts, min_thickness)`; the shim builds
/// the kiutils `Zone` items.
#[pyfunction]
pub fn write_zones_plan(
    py: Python<'_>,
    zones: Bound<'_, PyAny>,
    net_name_to_index: Bound<'_, PyDict>,
) -> PyResult<(Py<PyList>, usize, Py<PyList>)> {
    guarded(move || {
        let warnings = PyList::empty(py);
        let mut specs: Vec<Py<PyAny>> = Vec::new();
        for item in zones.try_iter()? {
            let zone_def = item?;
            let d = zone_def
                .cast::<PyDict>()
                .map_err(|_| value_error("zones entries must be dicts"))?;
            let net_name: String = d
                .get_item("net_name")?
                .ok_or_else(|| value_error("zone missing 'net_name'"))?
                .extract()?;
            let layer: String = d
                .get_item("layer")?
                .ok_or_else(|| value_error("zone missing 'layer'"))?
                .extract()?;
            let pts: Vec<(f64, f64)> = d
                .get_item("polygon_pts")?
                .ok_or_else(|| value_error("zone missing 'polygon_pts'"))?
                .extract()?;
            let net_index: i64 = net_name_to_index
                .get_item(net_name.as_str())?
                .map(|v| v.extract::<i64>().unwrap_or(0))
                .unwrap_or(0);
            let pts_list = PyList::new(
                py,
                pts.iter()
                    .map(|&(x, y)| PyTuple::new(py, [x, y]).map(|t| t.into_any()))
                    .collect::<PyResult<Vec<_>>>()?,
            )?;
            let spec = PyTuple::new(
                py,
                [
                    net_name.into_pyobject(py)?.into_any(),
                    net_index.into_pyobject(py)?.into_any(),
                    layer.into_pyobject(py)?.into_any(),
                    pts_list.into_any(),
                    0.254f64.into_pyobject(py)?.into_any(),
                ],
            )?;
            specs.push(spec.into_any().unbind());
        }
        let n = specs.len();
        Ok((PyList::new(py, specs)?.unbind(), n, warnings.unbind()))
    })
}

/// `_write_board.write_placements_to_pcb` kernel: center-offset extraction
/// from components, per-footprint match/skip decisions, position + pad-angle
/// computation. Returns `(updates, components_updated, components_skipped,
/// warnings)` where each update is
/// `(fp_index, ref, x, y, angle, had_position, pad_updates)` with
/// `pad_updates` = `[(pad_index, angle_or_none), ...]`.
#[pyfunction]
#[pyo3(signature = (placements, components, footprints, preserve_unmatched=true))]
pub fn write_placements_plan(
    py: Python<'_>,
    placements: Bound<'_, PyDict>,
    components: Option<Bound<'_, PyAny>>,
    footprints: Bound<'_, PyAny>,
    preserve_unmatched: bool,
) -> PyResult<(Py<PyList>, usize, usize, Py<PyList>)> {
    guarded(move || {
        let warnings = PyList::empty(py);
        // center offsets from components (float() of "_center_offset_*",
        // default "0"; only non-zero offsets recorded).
        let mut center_offsets: Vec<(String, (f64, f64))> = Vec::new();
        if let Some(comps) = components {
            for item in comps.try_iter()? {
                let comp = item?;
                let attrs_ok = comp.getattr("attributes").ok();
                let attrs_truthy = attrs_ok
                    .as_ref()
                    .map(|a| is_truthy(a).unwrap_or(false))
                    .unwrap_or(false);
                if attrs_truthy {
                    let attrs = attrs_ok.unwrap_or_else(|| py.None().into_bound(py));
                    let ref_: String = comp.getattr("ref")?.extract()?;
                    // `float(comp.attributes.get("_center_offset_x", "0"))` —
                    // a missing key defaults to "0"; a non-numeric value
                    // raises ValueError exactly like the pinned Python.
                    let cx = match attrs.get_item("_center_offset_x") {
                        Ok(v) => py_float(&v)?,
                        Err(_) => 0.0,
                    };
                    let cy = match attrs.get_item("_center_offset_y") {
                        Ok(v) => py_float(&v)?,
                        Err(_) => 0.0,
                    };
                    if cx != 0.0 || cy != 0.0 {
                        center_offsets.push((ref_, (cx, cy)));
                    }
                }
            }
        }

        let mut updates: Vec<Py<PyAny>> = Vec::new();
        let mut components_updated: usize = 0;
        let mut components_skipped: usize = 0;
        let mut fp_index = 0usize;
        for item in footprints.try_iter()? {
            let fp = item?;
            let ref_ = get_footprint_reference(py, fp.clone())?;
            let ref_ = match ref_ {
                Some(r) if !r.is_empty() => r,
                _ => {
                    let lib_id = get_attr_str(&fp, "libId", "");
                    warnings.append(format!("Skipping footprint with no reference: {}", lib_id))?;
                    components_skipped += 1;
                    fp_index += 1;
                    continue;
                }
            };
            let in_placements = placements.contains(ref_.as_str())?;
            if !in_placements {
                if !preserve_unmatched {
                    warnings.append(format!(
                        "Component {} not in placements, keeping original position",
                        ref_
                    ))?;
                }
                components_skipped += 1;
                fp_index += 1;
                continue;
            }
            let update = match placements.get_item(ref_.as_str())? {
                Some(u) => u,
                None => continue,
            };
            let x: f64 = update.getattr("x")?.extract()?;
            let y: f64 = update.getattr("y")?.extract()?;
            let rotation_deg: f64 = update.getattr("rotation")?.extract()?;

            let mut new_x = x;
            let mut new_y = y;
            if let Some((_, (cx, cy))) = center_offsets.iter().find(|(r, _)| r == &ref_) {
                let rot_rad = radians(rotation_deg);
                let (rotated_cx, rotated_cy) = rotate_local_to_world(*cx, *cy, rot_rad);
                new_x -= rotated_cx;
                new_y -= rotated_cy;
            }

            let had_position = fp
                .getattr("position")
                .ok()
                .map(|p| !p.is_none())
                .unwrap_or(false);
            let old_angle = if had_position {
                fp.getattr("position")?
                    .getattr("angle")
                    .ok()
                    .and_then(|a| a.extract::<f64>().ok())
                    .unwrap_or(0.0)
            } else {
                0.0
            };
            let delta = rotation_deg - old_angle;

            // pad reorientation plan (skipped entirely when delta % 360 == 0,
            // matching the verbatim early return).
            let mut pad_updates: Vec<(usize, Option<f64>)> = Vec::new();
            if py_mod(delta, 360.0) != 0.0
                && let Ok(pads) = fp.getattr("pads")
            {
                for (pad_index, pitem) in pads.try_iter()?.enumerate() {
                    let pad = pitem?;
                    if pad
                        .getattr("position")
                        .ok()
                        .map(|p| !p.is_none())
                        .unwrap_or(false)
                    {
                        let current = pad
                            .getattr("position")?
                            .getattr("angle")
                            .ok()
                            .and_then(|a| a.extract::<f64>().ok())
                            .unwrap_or(0.0);
                        let new_angle = py_mod(current + delta, 360.0);
                        pad_updates
                            .push((pad_index, if new_angle == 0.0 { None } else { Some(new_angle) }));
                    }
                }
            }

            let mut pad_items: Vec<Bound<'_, PyAny>> = Vec::new();
            for &(i, a) in &pad_updates {
                let idx = i.into_pyobject(py)?.into_any();
                let angle = match a {
                    Some(v) => v.into_pyobject(py)?.into_any(),
                    None => py.None().into_bound(py).into_any(),
                };
                pad_items.push(PyTuple::new(py, [idx, angle])?.into_any());
            }
            let update_spec = PyTuple::new(
                py,
                [
                    fp_index.into_pyobject(py)?.into_any(),
                    ref_.clone().into_pyobject(py)?.into_any(),
                    new_x.into_pyobject(py)?.into_any(),
                    new_y.into_pyobject(py)?.into_any(),
                    rotation_deg.into_pyobject(py)?.into_any(),
                    had_position.into_pyobject(py)?.to_owned().into_any(),
                    PyList::new(py, pad_items)?.into_any(),
                ],
            )?;
            updates.push(update_spec.into_any().unbind());
            components_updated += 1;
            fp_index += 1;
        }

        Ok((
            PyList::new(py, updates)?.unbind(),
            components_updated,
            components_skipped,
            warnings.unbind(),
        ))
    })
}

/// `_write_board.add_isolation_slots_to_pcb` kernel: component-position map +
/// per-slot offset rotation into absolute coordinates. Returns
/// `(line_specs, slots_added, slots_skipped, warnings)` where each spec is
/// `(name, start_x, start_y, end_x, end_y, width_mm)`.
#[pyfunction]
pub fn add_isolation_slots_plan(
    py: Python<'_>,
    footprints: Bound<'_, PyAny>,
    slots: Bound<'_, PyAny>,
) -> PyResult<(Py<PyList>, usize, usize, Py<PyList>)> {
    guarded(move || {
        let warnings = PyList::empty(py);
        let mut component_positions: Vec<(String, (f64, f64, f64))> = Vec::new();
        for item in footprints.try_iter()? {
            let fp = item?;
            if let Some(ref_) = get_footprint_reference(py, fp.clone())?
                && let Ok(pos) = fp.getattr("position")
                    && !pos.is_none()
                {
                    let x = pos.getattr("X").ok().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                    let y = pos.getattr("Y").ok().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                    let angle = pos.getattr("angle").ok().and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0);
                    component_positions.push((ref_, (x, y, angle)));
                }
        }

        let mut line_specs: Vec<Py<PyAny>> = Vec::new();
        let mut slots_added: usize = 0;
        let mut slots_skipped: usize = 0;
        for item in slots.try_iter()? {
            let slot = item?;
            let comp_ref: String = get_attr_str(&slot, "component_ref", "");
            let slot_name: String = get_attr_str(&slot, "name", "");
            let (comp_x, comp_y, comp_angle) = match component_positions.iter().find(|(r, _)| r == &comp_ref) {
                Some((_, p)) => *p,
                None => {
                    warnings.append(format!(
                        "Component '{}' not found for slot '{}'",
                        comp_ref, slot_name
                    ))?;
                    slots_skipped += 1;
                    continue;
                }
            };
            let angle_rad = radians(comp_angle);
            let (dx_start, dy_start): (f64, f64) = slot.getattr("start_offset")?.extract()?;
            let (dx_end, dy_end): (f64, f64) = slot.getattr("end_offset")?.extract()?;
            let (rot_start_x, rot_start_y) = if comp_angle != 0.0 {
                rotate_local_to_world(dx_start, dy_start, angle_rad)
            } else {
                (dx_start, dy_start)
            };
            let (rot_end_x, rot_end_y) = if comp_angle != 0.0 {
                rotate_local_to_world(dx_end, dy_end, angle_rad)
            } else {
                (dx_end, dy_end)
            };
            let abs_start_x = comp_x + rot_start_x;
            let abs_start_y = comp_y + rot_start_y;
            let abs_end_x = comp_x + rot_end_x;
            let abs_end_y = comp_y + rot_end_y;
            let width_mm = get_attr_f64(&slot, "width_mm", 0.0);
            let spec = PyTuple::new(
                py,
                [
                    slot_name.into_pyobject(py)?.into_any(),
                    abs_start_x.into_pyobject(py)?.into_any(),
                    abs_start_y.into_pyobject(py)?.into_any(),
                    abs_end_x.into_pyobject(py)?.into_any(),
                    abs_end_y.into_pyobject(py)?.into_any(),
                    width_mm.into_pyobject(py)?.into_any(),
                ],
            )?;
            line_specs.push(spec.into_any().unbind());
            slots_added += 1;
        }

        Ok((
            PyList::new(py, line_specs)?.unbind(),
            slots_added,
            slots_skipped,
            warnings.unbind(),
        ))
    })
}

/// `kicad_exporter.export_from_geometry` kernel: net-code resolution + layer
/// mapping for geometry tracks/vias. Returns `(segment_specs, via_specs,
/// nets_exported)`.
#[pyfunction]
#[pyo3(signature = (nets, tracks, vias, layer_map=None))]
pub fn export_from_geometry_plan(
    py: Python<'_>,
    nets: Bound<'_, PyAny>,
    tracks: Bound<'_, PyAny>,
    vias: Bound<'_, PyAny>,
    layer_map: Option<Bound<'_, PyDict>>,
) -> PyResult<(Py<PyList>, Py<PyList>, usize)> {
    guarded(move || {
        let mut net_codes: Vec<(String, i64)> = Vec::new();
        for item in nets.try_iter()? {
            let net = item?;
            if let (Ok(name), Ok(number)) = (net.getattr("name"), net.getattr("number"))
                && let (Ok(ns), Ok(ni)) = (name.extract::<String>(), number.extract::<i64>()) {
                    net_codes.push((ns, ni));
                }
        }
        let get_net_code = |net_name: &str| -> i64 {
            net_codes
                .iter()
                .find(|(n, _)| n == net_name)
                .map(|(_, c)| *c)
                .unwrap_or(0)
        };

        let mut segment_specs: Vec<Py<PyAny>> = Vec::new();
        let mut nets_used: Vec<String> = Vec::new();
        for item in tracks.try_iter()? {
            let track = item?;
            let layer_idx = get_attr_i64(&track, "layer", 0);
            let layer_name = layer_map_lookup(layer_map.as_ref(), layer_idx)?;
            let net: String = get_attr_str(&track, "net", "");
            let net_code = get_net_code(&net);
            let start = get_xy(&track.getattr("start")?).unwrap_or((0.0, 0.0));
            let end = get_xy(&track.getattr("end")?).unwrap_or((0.0, 0.0));
            let width = get_attr_f64(&track, "width", 0.0);
            let spec = PyTuple::new(
                py,
                [
                    net.clone().into_pyobject(py)?.into_any(),
                    start.0.into_pyobject(py)?.into_any(),
                    start.1.into_pyobject(py)?.into_any(),
                    end.0.into_pyobject(py)?.into_any(),
                    end.1.into_pyobject(py)?.into_any(),
                    width.into_pyobject(py)?.into_any(),
                    layer_name.into_pyobject(py)?.into_any(),
                    net_code.into_pyobject(py)?.into_any(),
                ],
            )?;
            segment_specs.push(spec.into_any().unbind());
            if !nets_used.contains(&net) {
                nets_used.push(net);
            }
        }

        let mut via_specs: Vec<Py<PyAny>> = Vec::new();
        for item in vias.try_iter()? {
            let via = item?;
            let net: String = get_attr_str(&via, "net", "");
            let net_code = get_net_code(&net);
            let center = get_xy(&via.getattr("center")?).unwrap_or((0.0, 0.0));
            let diameter = get_attr_f64(&via, "diameter", 0.0);
            let drill = get_attr_f64(&via, "drill", 0.0);
            let layers = PyList::new(py, ["F.Cu", "B.Cu"])?;
            let spec = PyTuple::new(
                py,
                [
                    net.into_pyobject(py)?.into_any(),
                    center.0.into_pyobject(py)?.into_any(),
                    center.1.into_pyobject(py)?.into_any(),
                    diameter.into_pyobject(py)?.into_any(),
                    drill.into_pyobject(py)?.into_any(),
                    layers.into_any(),
                    net_code.into_pyobject(py)?.into_any(),
                ],
            )?;
            via_specs.push(spec.into_any().unbind());
        }

        Ok((
            PyList::new(py, segment_specs)?.unbind(),
            PyList::new(py, via_specs)?.unbind(),
            nets_used.len(),
        ))
    })
}

/// The `add_bounding_boxes_to_pcb` / `add_silkscreen_labels` annotation
/// kernel: per-footprint pad bounds, value extraction, and the silkscreen
/// text geometry. Returns a list parallel to `footprints` of
/// `(ref, x_min, y_min, x_max, y_max, value_or_none, comp_cx, scaled_height,
/// ref_y, val_y)` or `None`.
#[pyfunction]
pub fn fp_annotations(py: Python<'_>, footprints: Bound<'_, PyAny>) -> PyResult<Py<PyList>> {
    guarded(move || {
        let mut out_items: Vec<Py<PyAny>> = Vec::new();
        for item in footprints.try_iter()? {
            let fp = item?;
            let ref_ = get_footprint_reference(py, fp.clone())?;
            let ref_ = match ref_ {
                Some(r) if !r.is_empty() => r,
                _ => {
                    out_items.push(py.None().into_bound(py).unbind());
                    continue;
                }
            };
            let bounds = match compute_pad_bounds(py, fp.clone())? {
                Some(b) => b,
                None => {
                    out_items.push(py.None().into_bound(py).unbind());
                    continue;
                }
            };
            let (x_min, y_min, x_max, y_max) = bounds;
            // value extraction (properties dict or list)
            let mut value: Option<String> = None;
            let props = fp
                .getattr("properties")
                .ok()
                .filter(|p| !p.is_none())
                .unwrap_or_else(|| py.None().into_bound(py));
            if let Ok(d) = props.cast::<PyDict>() {
                if let Some(v) = d.get_item("Value")?
                    && let Ok(s) = v.extract::<String>() {
                        value = Some(s);
                    }
            } else if let Ok(list) = props.try_iter() {
                for pit in list {
                    let prop = pit?;
                    if let Ok(key) = prop.getattr("key")
                        && key.eq("Value")?
                            && let Ok(v) = prop.getattr("value")
                                && let Ok(s) = v.extract::<String>() {
                                    value = Some(s);
                                    break;
                                }
                }
            }
            let comp_width = x_max - x_min;
            let comp_height = y_max - y_min;
            let comp_cx = (x_min + x_max) / 2.0;
            let scaled_height = (0.8f64).max((1.5f64).min(comp_width.min(comp_height) / 4.0));
            let ref_y = y_min - scaled_height - 0.5;
            let val_y = y_min - 2.0 * scaled_height - 1.0;
            let spec = PyTuple::new(
                py,
                [
                    ref_.into_pyobject(py)?.into_any(),
                    x_min.into_pyobject(py)?.into_any(),
                    y_min.into_pyobject(py)?.into_any(),
                    x_max.into_pyobject(py)?.into_any(),
                    y_max.into_pyobject(py)?.into_any(),
                    value
                        .map(|v| v.into_pyobject(py).map(|v| v.into_any()))
                        .transpose()?
                        .unwrap_or_else(|| py.None().into_bound(py).into_any()),
                    comp_cx.into_pyobject(py)?.into_any(),
                    scaled_height.into_pyobject(py)?.into_any(),
                    ref_y.into_pyobject(py)?.into_any(),
                    val_y.into_pyobject(py)?.into_any(),
                ],
            )?;
            out_items.push(spec.into_any().unbind());
        }
        Ok(PyList::new(py, out_items)?.unbind())
    })
}

// =============================================================================
// Tests — pure-kernel unit tests (the differential suite carries the parity
// evidence; these pin the helper semantics in-crate).
// =============================================================================

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    fn assert_bits(a: f64, b: f64) {
        assert_eq!(a.to_bits(), b.to_bits(), "{} vs {}", a, b);
    }

    #[test]
    fn round_half_even_matches_cpython() {
        // Python: round(2.5)=2, round(3.5)=4, round(-2.5)=-2, round(1.25,1)=1.2
        assert_bits(py_round_ties_even(2.5), 2.0);
        assert_bits(py_round_ties_even(3.5), 4.0);
        assert_bits(py_round_ties_even(-2.5), -2.0);
        assert_bits(py_round_ndigits(1.25, 1), 1.2);
        // Python round(2.675, 2) == 2.67: 2.675*100 == 267.5 exactly, yet the
        // exact binary value sits just BELOW the 2.675 tie point, so the
        // decimal-aware rounding lands at 2.67. The multiply-then-round
        // shortcut gives 2.68 — this test pins the decimal-aware behaviour.
        assert_bits(py_round_ndigits(2.675, 2), 2.67);
        assert_bits(py_round_ndigits(1.2345, 3), 1.234);
        assert_bits(py_round_ndigits(10.0005, 3), 10.001);
        assert_bits(py_round_ndigits(0.0005, 3), 0.001);
        assert_bits(py_round_ndigits(-0.0001, 3), -0.0);
        assert!(py_round_ndigits(-0.0001, 3).is_sign_negative());
    }

    #[test]
    fn py_mod_takes_divisor_sign() {
        assert_bits(py_mod(-45.0, 360.0), 315.0);
        assert_bits(py_mod(380.0, 360.0), 20.0);
        assert_bits(py_mod(-360.0, 360.0), -0.0);
        assert_bits(py_mod(0.0, 360.0), 0.0);
    }

    #[test]
    fn rotate_is_r_minus_theta() {
        // R(-90).(1, 0) = (cos(pi/2), -1) = (6.12e-17, -1.0); R(+90) would
        // give y = +1.0. The sign of y is the discriminator.
        let (x, y) = rotate_local_to_world(1.0, 0.0, std::f64::consts::FRAC_PI_2);
        assert_bits(x, 6.123233995736766e-17);
        assert_bits(y, -1.0);
        let (x2, y2) = rotate_local_to_world(10.0, 4.0, radians(37.0));
        // verified against math.cos/math.sin in CPython
        assert_bits(x2, 10.393615193081121);
        assert_bits(y2, -2.823608191331312);
    }

    #[test]
    fn simplify_path_keeps_endpoints_and_turns() {
        let cells = vec![(0, 0, 0), (1, 0, 0), (2, 0, 0)];
        assert_eq!(simplify_path(&cells), vec![(0, 0, 0), (2, 0, 0)]);
        let l = vec![(0, 0, 0), (1, 0, 0), (1, 1, 0)];
        assert_eq!(simplify_path(&l), vec![(0, 0, 0), (1, 0, 0), (1, 1, 0)]);
        let layer_change = vec![(0, 0, 0), (1, 0, 0), (1, 0, 1)];
        assert_eq!(simplify_path(&layer_change), layer_change);
    }

    #[test]
    fn snap_uses_strict_lt() {
        // pad exactly at tolerance: does NOT snap
        let (x, y) = snap_to_nearest_pad(0.0, 0.0, &[(0.15, 0.0)], 0.15);
        assert_bits(x, 0.0);
        assert_bits(y, 0.0);
        let (x2, y2) = snap_to_nearest_pad(0.0, 0.0, &[(0.14, 0.0)], 0.15);
        assert_bits(x2, 0.14);
        assert_bits(y2, 0.0);
    }

    #[test]
    fn grid_to_world_center() {
        let (x, y) = grid_to_world(10, 20, (0.0, 0.0), 0.5);
        assert_bits(x, 5.25);
        assert_bits(y, 10.25);
    }
}

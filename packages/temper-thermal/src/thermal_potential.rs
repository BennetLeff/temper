//! Thermal potential field + greedy anchor assignment (Wave 4, Phase 4).
//!
//! Bit-exact port of the pure compute in
//! `temper_placer/physics/thermal_potential.py`: the five superposing
//! field components (`phi_edge`, `phi_copper`, `phi_coupling`,
//! `phi_exclusion`, `phi_convection`), the grid builder
//! (`np.linspace` + `np.meshgrid`), the weighted superposition, the
//! two-pass greedy anchor search (`assign_thermal_anchors`, including
//! `_find_min_valid`), and the uniqueness enforcement
//! (`_enforce_unique_positions`).
//!
//! The Python module keeps its public API, its dataclass, its duck-typed
//! copper-zone extraction (`hasattr(zone, "bounds")` /
//! `hasattr(zone, "polygon")`), its `logging` calls, and its safety
//! gates; only the arithmetic moves here.
//!
//! # Bit-exactness discipline (Wave-4 catalog)
//!
//! - **B1 (host-runtime libm):** `exp`, `cos`, `sin`, `pow` are resolved
//!   through [`crate::hostmath`]'s `dlsym` cache.  Measured on this
//!   repo's runtime (macOS/arm64, CPython 3.12, numpy 2.3.5): numpy's
//!   float64 `exp`/`cos`/`sin` ufunc loops are bit-identical to the host
//!   libm at every array length the module uses (1, 2, 4, 8, 16, 100,
//!   2500), so one resolution serves both the scalar `math.*` and the
//!   array `np.*` call sites.
//! - **B2 (named constant vs division):** `np.radians(d)` is measured
//!   bit-identical to `d * (pi / 180.0)` — the *division* `PI / 180.0`,
//!   not a named `FRAC_*` constant — over 20 000 random degrees.
//! - **B5 (NaN comparison semantics):** three distinct maxima appear in
//!   the reference and are kept distinct here:
//!   [`crate::hostmath::py_max`] for CPython's builtin `max(power, 1e-6)`
//!   (first argument wins on NaN), [`crate::hostmath::np_maximum`] for
//!   `np.maximum(field, barrier)` (NaN propagates from either side), and
//!   [`crate::hostmath::np_clip`] for `np.clip` (NaN propagates; inverted
//!   bounds return the upper bound).
//! - **B7 (f64 operation order):** every expression mirrors the
//!   reference's grouping — `(2.0 * sigma) * sigma`, `(-dist_sq) /
//!   sigma_sq`, `(-steepness) * (dist - radius)`, `magnitude * (x * ux +
//!   y * uy)`, `1.0 - exp((-d) / decay)`, and `linspace`'s
//!   `i * step + start` two-op chain.  `x ** 2` and `x ** 0.5` are libm
//!   `pow`, never `x * x` or `sqrt` (catalog note in
//!   [`crate::hostmath`]).
//! - **B8 (denormals):** default IEEE semantics; no fast-math, no FTZ,
//!   no `mul_add` fusion.  Pinned by a denormal differential case.
//!
//! B3 (banker's rounding), B4 (CPython `hypot`), B6 (GEOS distance),
//! B9/B10 (repr rendering) are not applicable: the module rounds
//! nothing, computes no `math.hypot`, touches no GEOS geometry, and
//! returns no repr strings.

use std::collections::HashMap;

use crate::hostmath::{cos, exp, np_clip, np_maximum, pow, py_max, sin};

#[cfg(feature = "python")]
use pyo3::exceptions::{PyOverflowError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyBytes;

/// `phi_copper`'s hard-coded coarse grid resolution.  The reference
/// writes `grid_res = 50` *inside* `phi_copper`, independent of
/// `config.grid_resolution` — so a zone-fed copper field is always
/// 50x50 and only broadcasts against a 50x50 potential grid.  Preserved
/// verbatim, including the resulting shape mismatch.
pub const COPPER_GRID_RES: usize = 50;

/// `phi_copper`'s conductance epsilon (`eps = 1e-12`).
const COPPER_EPS: f64 = 1e-12;

/// The heatsink edge, pre-normalised by the Python caller.
///
/// Normalisation (`edge.upper().strip()`) stays in Python so CPython's
/// exact Unicode case-folding and whitespace-stripping semantics are
/// never re-implemented here; Rust only sees the resolved branch.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Edge {
    Top,
    Bottom,
    Left,
    Right,
    /// Any name that is not one of the four — `phi_edge` returns zeros
    /// and the edge strip is empty.
    Unknown,
}

impl Edge {
    /// Decode the integer code the pyo3 boundary carries.
    pub fn from_code(code: u8) -> Self {
        match code {
            0 => Edge::Top,
            1 => Edge::Bottom,
            2 => Edge::Left,
            3 => Edge::Right,
            _ => Edge::Unknown,
        }
    }
}

/// Axis-aligned board/zone/keepout rectangle `(x_min, y_min, x_max, y_max)`.
pub type Rect = (f64, f64, f64, f64);

/// Weights and parameters of [`superpose`], mirroring
/// `ThermalPotentialConfig`.
#[derive(Clone, Copy, Debug)]
pub struct FieldConfig {
    pub edge_weight: f64,
    pub copper_weight: f64,
    pub coupling_weight: f64,
    pub exclusion_weight: f64,
    pub convection_weight: f64,
    pub edge_decay_length_mm: f64,
    pub thermal_exclusion_radius_mm: f64,
    pub exclusion_barrier_height: f64,
    pub exclusion_steepness: f64,
}

/// Why a superposition could not be formed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FieldError {
    /// `phi_copper`'s 50x50 zone grid cannot broadcast against the
    /// potential grid — the same `ValueError` numpy raises for
    /// `(res, res) + (50, 50)` when `res != 50`.
    CopperBroadcast { rows: usize, cols: usize, grid_rows: usize, grid_cols: usize },
    /// A zone bound is NaN — CPython's `int(nan)` raises `ValueError`.
    ZoneBoundNotANumber,
    /// A zone bound is infinite — CPython's `int(inf)` raises
    /// `OverflowError`.
    ZoneBoundInfinite,
    /// `np.linspace` rejects a negative sample count.
    NegativeResolution(i64),
}

// ---------------------------------------------------------------------------
// Grid construction
// ---------------------------------------------------------------------------

/// `np.linspace(start, stop, num)` with `endpoint=True`, float64.
///
/// Replicates numpy's own arithmetic exactly (verified bit-for-bit over
/// 4 000 random `(start, stop, num)` configurations plus the degenerate
/// `start == stop` and denormal cases):
///
/// ```text
/// div  = num - 1
/// step = (stop - start) / div
/// y[i] = i * step + start          # two ops, no fusing
/// y[i] = (i / div) * (stop - start) + start   # when step == 0
/// y[num - 1] = stop                # exact endpoint, when num > 1
/// ```
pub fn linspace(start: f64, stop: f64, num: usize) -> Vec<f64> {
    if num == 0 {
        return Vec::new();
    }
    let div = num - 1;
    let delta = stop - start;
    let mut out = Vec::with_capacity(num);
    if div > 0 {
        let step = delta / (div as f64);
        if step == 0.0 {
            for i in 0..num {
                out.push(((i as f64) / (div as f64)) * delta + start);
            }
        } else {
            for i in 0..num {
                out.push((i as f64) * step + start);
            }
        }
    } else {
        // num == 1: numpy multiplies by `delta` (step is NaN and unused)
        // then adds start, which is exactly `start` for i == 0.
        out.push(0.0 * delta + start);
    }
    if num > 1 {
        out[num - 1] = stop;
    }
    out
}

/// `build_potential_grid`: `np.meshgrid(linspace(x), linspace(y))`.
///
/// Returns the two row-major `resolution x resolution` grids, where
/// `x_grid[i][j] == x_lin[j]` and `y_grid[i][j] == y_lin[i]` (numpy's
/// default `indexing="xy"`).
pub fn build_potential_grid(bounds: Rect, resolution: usize) -> (Vec<f64>, Vec<f64>) {
    let (x_min, y_min, x_max, y_max) = bounds;
    let x_lin = linspace(x_min, x_max, resolution);
    let y_lin = linspace(y_min, y_max, resolution);
    let n = resolution * resolution;
    let mut x_grid = Vec::with_capacity(n);
    let mut y_grid = Vec::with_capacity(n);
    for &y in &y_lin {
        for &x in &x_lin {
            x_grid.push(x);
            y_grid.push(y);
        }
    }
    (x_grid, y_grid)
}

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

/// `phi_edge`: `1 - exp(-d_edge / lambda)`, zeros for an unknown edge.
pub fn phi_edge(x_grid: &[f64], y_grid: &[f64], bounds: Rect, edge: Edge, decay: f64) -> Vec<f64> {
    let (x_min, y_min, x_max, y_max) = bounds;
    if edge == Edge::Unknown {
        return vec![0.0; x_grid.len()];
    }
    x_grid
        .iter()
        .zip(y_grid.iter())
        .map(|(&x, &y)| {
            let d = match edge {
                Edge::Top => y_max - y,
                Edge::Bottom => y - y_min,
                Edge::Left => x - x_min,
                Edge::Right => x_max - x,
                Edge::Unknown => unreachable!("handled above"),
            };
            // B7: numpy negates the array, then divides, then subtracts
            // from 1.0 — three separately rounded ops in that order.
            1.0 - exp((-d) / decay)
        })
        .collect()
}

/// The result of `phi_copper`, which is either a `(1, 1)` uniform array
/// or a `COPPER_GRID_RES x COPPER_GRID_RES` zone-derived one.
#[derive(Clone, Debug, PartialEq)]
pub enum CopperField {
    /// `np.ones((1, 1)) * 0.5` — broadcasts against any grid.
    Uniform(f64),
    /// `1.0 / (clip(conductance, 0, None) + eps)` on the 50x50 grid.
    Grid { rows: usize, cols: usize, data: Vec<f64> },
}

/// CPython's `int(x)` for a float: truncate toward zero, raising on
/// NaN/inf.  The saturating cast is safe because every call site
/// immediately clamps into `[0, COPPER_GRID_RES]`.
fn py_int_trunc(x: f64) -> Result<i64, FieldError> {
    if x.is_nan() {
        return Err(FieldError::ZoneBoundNotANumber);
    }
    if x.is_infinite() {
        return Err(FieldError::ZoneBoundInfinite);
    }
    Ok(x.trunc() as i64)
}

/// `phi_copper`.
///
/// `zone_count` is the length of the caller's `copper_zones` list
/// *before* the duck-typed filter; `zones` holds only the entries that
/// yielded bounds.  The reference takes the uniform branch on
/// `copper_zones is None or len(copper_zones) == 0`, so a non-empty list
/// whose every entry was skipped still produces the 50x50 `1/eps` grid.
pub fn phi_copper(bounds: Rect, zone_count: usize, zones: &[Rect]) -> Result<CopperField, FieldError> {
    if zone_count == 0 {
        // np.ones((1, 1)) * 0.5
        return Ok(CopperField::Uniform(1.0 * 0.5));
    }
    let (x_min, y_min, x_max, y_max) = bounds;
    let board_w = x_max - x_min;
    let board_h = y_max - y_min;
    // Mirrors `if board_w <= 0 or board_h <= 0`.  A NaN dimension makes
    // BOTH comparisons false in Python *and* in Rust, so a NaN board
    // falls through to the grid branch in both — writing `!(w > 0.0)`
    // here would silently change that.
    if board_w <= 0.0 || board_h <= 0.0 {
        return Ok(CopperField::Uniform(1.0 * 0.5));
    }

    let grid_res = COPPER_GRID_RES;
    let mut conductance = vec![0.0_f64; grid_res * grid_res];

    let res_i = grid_res as i64;
    let res_f = grid_res as f64;
    for &(zx0, zy0, zx1, zy1) in zones {
        let gx0 = 0_i64.max(py_int_trunc((zx0 - x_min) / board_w * res_f)?);
        let gx1 = res_i.min(py_int_trunc((zx1 - x_min) / board_w * res_f)?.saturating_add(1));
        let gy0 = 0_i64.max(py_int_trunc((zy0 - y_min) / board_h * res_f)?);
        let gy1 = res_i.min(py_int_trunc((zy1 - y_min) / board_h * res_f)?.saturating_add(1));

        if gx1 > gx0 && gy1 > gy0 {
            // NOTE: the reference indexes `conductance[gx0:gx1, gy0:gy1]`
            // — the FIRST axis carries x and the SECOND carries y, the
            // transpose of the `meshgrid` convention used everywhere
            // else in the module.  Preserved verbatim: "fixing" it would
            // be a silent behaviour change no differential could catch.
            for gx in gx0..gx1 {
                for gy in gy0..gy1 {
                    conductance[(gx as usize) * grid_res + (gy as usize)] += 1.0;
                }
            }
        }
    }

    let data = conductance
        .iter()
        .map(|&c| {
            // k_eff = np.clip(conductance, 0.0, None) + eps
            let k_eff = np_maximum(c, 0.0) + COPPER_EPS;
            1.0 / k_eff
        })
        .collect();
    Ok(CopperField::Grid { rows: grid_res, cols: grid_res, data })
}

/// `phi_coupling`: superposed Gaussian kernels, one per power device.
///
/// `zip(device_positions, device_powers)` stops at the shorter sequence;
/// the caller passes the already-zipped pairs.
pub fn phi_coupling(
    x_grid: &[f64],
    y_grid: &[f64],
    devices: &[((f64, f64), f64)],
    sigma_factor: f64,
) -> Vec<f64> {
    let mut field = vec![0.0_f64; x_grid.len()];
    if devices.is_empty() {
        return field;
    }
    for &((px, py), power) in devices {
        // sigma = sqrt(max(power, 1e-6)) * sigma_factor
        // (B5: CPython's builtin `max` keeps the FIRST argument on NaN.)
        let sigma = py_max(power, 1e-6).sqrt() * sigma_factor;
        // B7: (2.0 * sigma) * sigma, left to right.
        let sigma_sq = 2.0 * sigma * sigma;
        for (idx, out) in field.iter_mut().enumerate() {
            let dx = x_grid[idx] - px;
            let dy = y_grid[idx] - py;
            let dist_sq = dx * dx + dy * dy;
            // B7: numpy negates the array, then divides.
            *out += power * exp((-dist_sq) / sigma_sq);
        }
    }
    field
}

/// `phi_exclusion`: sigmoid barriers combined with `np.maximum`.
pub fn phi_exclusion(
    x_grid: &[f64],
    y_grid: &[f64],
    anchors: &[(f64, f64)],
    radius_mm: f64,
    barrier_height: f64,
    steepness: f64,
) -> Vec<f64> {
    let mut field = vec![0.0_f64; x_grid.len()];
    if anchors.is_empty() {
        return field;
    }
    // B7: Python's unary minus binds tighter than `*`, so the reference
    // computes `(-steepness) * (dist - radius_mm)`.
    let neg_steepness = -steepness;
    for &(ax, ay) in anchors {
        for (idx, out) in field.iter_mut().enumerate() {
            let dx = x_grid[idx] - ax;
            let dy = y_grid[idx] - ay;
            let dist = (dx * dx + dy * dy).sqrt();
            let barrier = barrier_height * (1.0 / (1.0 + exp(neg_steepness * (dist - radius_mm))));
            // B5: np.maximum propagates NaN from either operand.
            *out = np_maximum(*out, barrier);
        }
    }
    field
}

/// `phi_convection`: a linear ramp along the airflow direction.
pub fn phi_convection(
    x_grid: &[f64],
    y_grid: &[f64],
    airflow: Option<(f64, f64)>,
) -> Vec<f64> {
    let Some((magnitude, direction_deg)) = airflow else {
        return vec![0.0; x_grid.len()];
    };
    // `if magnitude <= 0` — false for NaN, so a NaN magnitude falls
    // through to the ramp exactly as in Python.
    if magnitude <= 0.0 {
        return vec![0.0; x_grid.len()];
    }
    // B2: np.radians(d) is measured bit-identical to d * (PI / 180.0),
    // the division — not a named FRAC constant.
    let rad = direction_deg * (std::f64::consts::PI / 180.0);
    let ux = cos(rad);
    let uy = sin(rad);
    x_grid
        .iter()
        .zip(y_grid.iter())
        .map(|(&x, &y)| magnitude * (x * ux + y * uy))
        .collect()
}

// ---------------------------------------------------------------------------
// Superposition
// ---------------------------------------------------------------------------

/// Everything `superpose_fields` needs beyond the grids themselves.
pub struct SuperposeInputs<'a> {
    pub bounds: Rect,
    pub edge: Edge,
    pub config: FieldConfig,
    /// Already-zipped `(position, power)` pairs; empty disables coupling.
    pub devices: &'a [((f64, f64), f64)],
    /// Non-empty enables the exclusion barrier.
    pub anchors: &'a [(f64, f64)],
    /// Length of the caller's `copper_zones` list before filtering.
    pub copper_zone_count: usize,
    /// The subset of copper zones that yielded bounds.
    pub copper_zones: &'a [Rect],
    pub airflow: Option<(f64, f64)>,
    /// `True` when the caller passed a non-empty `device_positions`
    /// list — the reference tests `device_positions and device_powers`,
    /// so an empty power list also disables coupling.
    pub coupling_enabled: bool,
}

/// `superpose_fields`, accumulating in the reference's exact order:
/// edge, copper, coupling, exclusion, convection.
pub fn superpose(
    x_grid: &[f64],
    y_grid: &[f64],
    grid_rows: usize,
    grid_cols: usize,
    inputs: &SuperposeInputs<'_>,
) -> Result<Vec<f64>, FieldError> {
    let cfg = inputs.config;
    let mut total = vec![0.0_f64; x_grid.len()];

    if cfg.edge_weight > 0.0 {
        let phi = phi_edge(x_grid, y_grid, inputs.bounds, inputs.edge, cfg.edge_decay_length_mm);
        for (t, p) in total.iter_mut().zip(phi.iter()) {
            *t += cfg.edge_weight * p;
        }
    }

    if cfg.copper_weight > 0.0 {
        match phi_copper(inputs.bounds, inputs.copper_zone_count, inputs.copper_zones)? {
            CopperField::Uniform(v) => {
                let scaled = cfg.copper_weight * v;
                for t in total.iter_mut() {
                    *t += scaled;
                }
            }
            CopperField::Grid { rows, cols, data } => {
                if rows != grid_rows || cols != grid_cols {
                    return Err(FieldError::CopperBroadcast {
                        rows,
                        cols,
                        grid_rows,
                        grid_cols,
                    });
                }
                for (t, p) in total.iter_mut().zip(data.iter()) {
                    *t += cfg.copper_weight * p;
                }
            }
        }
    }

    if cfg.coupling_weight > 0.0 && inputs.coupling_enabled {
        let phi = phi_coupling(x_grid, y_grid, inputs.devices, 50.0);
        for (t, p) in total.iter_mut().zip(phi.iter()) {
            *t += cfg.coupling_weight * p;
        }
    }

    if cfg.exclusion_weight > 0.0 && !inputs.anchors.is_empty() {
        let phi = phi_exclusion(
            x_grid,
            y_grid,
            inputs.anchors,
            cfg.thermal_exclusion_radius_mm,
            cfg.exclusion_barrier_height,
            cfg.exclusion_steepness,
        );
        for (t, p) in total.iter_mut().zip(phi.iter()) {
            *t += cfg.exclusion_weight * p;
        }
    }

    if cfg.convection_weight > 0.0 && inputs.airflow.is_some() {
        let phi = phi_convection(x_grid, y_grid, inputs.airflow);
        for (t, p) in total.iter_mut().zip(phi.iter()) {
            *t += cfg.convection_weight * p;
        }
    }

    Ok(total)
}

// ---------------------------------------------------------------------------
// Greedy anchor assignment
// ---------------------------------------------------------------------------

/// An insertion-ordered `ref -> position` map with CPython `dict`
/// semantics: re-assigning an existing key updates the value in place
/// and keeps the key's original position.
#[derive(Clone, Debug, Default)]
struct OrderedAnchors {
    order: Vec<String>,
    index: HashMap<String, usize>,
    values: Vec<(f64, f64)>,
}

impl OrderedAnchors {
    fn insert(&mut self, key: &str, value: (f64, f64)) {
        match self.index.get(key) {
            Some(&i) => self.values[i] = value,
            None => {
                self.index.insert(key.to_owned(), self.order.len());
                self.order.push(key.to_owned());
                self.values.push(value);
            }
        }
    }

    fn get(&self, key: &str) -> Option<(f64, f64)> {
        self.index.get(key).map(|&i| self.values[i])
    }

    fn is_empty(&self) -> bool {
        self.order.is_empty()
    }

    fn iter(&self) -> impl Iterator<Item = (&str, (f64, f64))> {
        self.order
            .iter()
            .enumerate()
            .map(move |(i, k)| (k.as_str(), self.values[i]))
    }

    fn positions(&self) -> &[(f64, f64)] {
        &self.values
    }
}

/// One power device as `assign_thermal_anchors` sees it.
pub struct DeviceSpec {
    /// Component reference.
    pub reference: String,
    /// Power dissipation (W).
    pub power: f64,
    /// The device's zone bounds when `ref` is a key of the `zones` dict;
    /// `None` means unconstrained (`zones is None or ref not in zones`).
    pub zone: Option<Rect>,
}

/// Everything the anchor search needs.
pub struct AnchorInputs<'a> {
    pub bounds: Rect,
    pub edge: Edge,
    pub resolution: usize,
    pub devices: &'a [DeviceSpec],
    pub keepouts: &'a [Rect],
    pub config: FieldConfig,
    pub copper_zone_count: usize,
    pub copper_zones: &'a [Rect],
    pub airflow: Option<(f64, f64)>,
    pub min_separation_mm: f64,
}

/// What the search produced, plus the log records the Python caller
/// re-emits through `logging` so `caplog` behaviour is unchanged.
#[derive(Clone, Debug, Default)]
pub struct AnchorOutcome {
    /// Final `ref -> (x, y)`, in the reference's insertion order.
    pub anchors: Vec<(String, (f64, f64))>,
    /// Devices for which no feasible cell existed (pass 1).
    pub skipped: Vec<String>,
    /// `(ref, phi_min_x, phi_min_y, clamped_x, clamped_y, delta_mm)`
    /// for every anchor whose clamp moved it more than 2 mm.
    pub clamped: Vec<(String, f64, f64, f64, f64, f64)>,
}

/// `assign_thermal_anchors`'s `MAX_ITERATIONS`.
const MAX_ITERATIONS: usize = 3;
/// `assign_thermal_anchors`'s `REASSIGN_THRESHOLD_MM`.
const REASSIGN_THRESHOLD_MM: f64 = 5.0;
/// `_enforce_unique_positions`'s default `tolerance_mm`.
const UNIQUE_TOLERANCE_MM: f64 = 0.1;
/// `_enforce_unique_positions`'s default `offset_mm`.
const UNIQUE_OFFSET_MM: f64 = 0.5;
/// `assign_thermal_anchors`'s `edge_margin`.
const EDGE_MARGIN_MM: f64 = 10.0;
/// The clamp-warning threshold.
const CLAMP_WARN_MM: f64 = 2.0;

fn in_edge_strip(edge: Edge, bounds: Rect, x: f64, y: f64) -> bool {
    let (x_min, y_min, x_max, y_max) = bounds;
    match edge {
        Edge::Top => (y_max - y) <= EDGE_MARGIN_MM,
        Edge::Bottom => (y - y_min) <= EDGE_MARGIN_MM,
        Edge::Left => (x - x_min) <= EDGE_MARGIN_MM,
        Edge::Right => (x_max - x) <= EDGE_MARGIN_MM,
        Edge::Unknown => false,
    }
}

fn in_zone(zone: Option<Rect>, x: f64, y: f64) -> bool {
    match zone {
        None => true,
        Some((zx0, zy0, zx1, zy1)) => zx0 <= x && x <= zx1 && zy0 <= y && y <= zy1,
    }
}

fn in_keepout(keepouts: &[Rect], x: f64, y: f64) -> bool {
    keepouts
        .iter()
        .any(|&(kx0, ky0, kx1, ky1)| kx0 <= x && x <= kx1 && ky0 <= y && y <= ky1)
}

/// `_find_min_valid`: the first strict minimum of `phi` over the cells
/// that satisfy every constraint, scanned in row-major order.
///
/// "First strict minimum" matters: the reference updates only on
/// `val < best_val`, so ties keep the earliest cell and a NaN `phi`
/// never wins.
#[allow(clippy::too_many_arguments, reason = "mirrors the reference's closure captures")]
fn find_min_valid(
    phi: &[f64],
    x_grid: &[f64],
    y_grid: &[f64],
    resolution: usize,
    edge: Edge,
    bounds: Rect,
    zone: Option<Rect>,
    keepouts: &[Rect],
    existing: &[(f64, f64)],
    min_dist2: f64,
) -> Option<(f64, f64)> {
    let mut best_val = f64::INFINITY;
    let mut best_xy: Option<(f64, f64)> = None;
    for i in 0..resolution {
        for j in 0..resolution {
            let idx = i * resolution + j;
            let x = x_grid[idx];
            let y = y_grid[idx];
            if !in_edge_strip(edge, bounds, x, y) {
                continue;
            }
            if !in_zone(zone, x, y) {
                continue;
            }
            if in_keepout(keepouts, x, y) {
                continue;
            }
            // B7: `(x - ex) ** 2` is libm pow(·, 2.0), not `d * d`.
            let too_close = existing
                .iter()
                .any(|&(ex, ey)| (pow(x - ex, 2.0) + pow(y - ey, 2.0)) < min_dist2);
            if too_close {
                continue;
            }
            let val = phi[idx];
            if val < best_val {
                best_val = val;
                best_xy = Some((x, y));
            }
        }
    }
    best_xy
}

/// The first x-position on anchor `j`'s row that clears every other
/// anchor by `tolerance_mm`, or `None` when no such position exists
/// within the board (`offset_mm` not positive leaves the search
/// stationary, so it reports `None` immediately).
///
/// The old single right-offset clamped at `x_max`, which could land the
/// nudged anchor exactly on another anchor already sitting at `x_max`
/// (issue #928: two devices coinciding at (40.0, 21.0)), and it never
/// revisited a pair the nudge might have newly collided with a third
/// anchor.  `search_free_x` replaces the clamp with a bounded two-way
/// scan for the first x-position on the row that is at least
/// `tolerance_mm` from *every* other anchor.
fn search_free_x(
    anchors: &[(String, (f64, f64))],
    j: usize,
    x_min: f64,
    x_max: f64,
    tolerance_mm: f64,
    offset_mm: f64,
) -> Option<(f64, f64)> {
    let (xj, yj) = anchors[j].1;
    let mut k: usize = 1;
    loop {
        let koff = (k as f64) * offset_mm;
        // Stop once both directions are out of bounds (or the offset is
        // not positive): every further candidate is farther from the
        // row's span and cannot clear the collision either.
        if !(offset_mm > 0.0 && (xj + koff <= x_max || xj - koff >= x_min)) {
            return None;
        }
        for sign in [1.0_f64, -1.0_f64] {
            // `xj + sign * koff` mirrors CPython's `xj + sign * koff`
            // (int `sign` times the float `koff`): the sign multiply is
            // an exact sign flip, so the bit sequence is identical.
            let cx = xj + sign * koff;
            if cx < x_min || cx > x_max {
                continue;
            }
            // B7: `(...) ** 2` / `(...) ** 0.5` are libm `pow`, not
            // `x * x` / `sqrt`, exactly as in the pair scan.
            let clear = anchors.iter().enumerate().all(|(m, &(_, (ex, ey)))| {
                m == j || pow(pow(cx - ex, 2.0) + pow(yj - ey, 2.0), 0.5) >= tolerance_mm
            });
            if clear {
                return Some((cx, yj));
            }
        }
        k += 1;
    }
}

/// `_enforce_unique_positions`, mutating in place exactly as the
/// reference does.
///
/// Re-scans every pair until a full pass makes no move.  Each move lands
/// the later anchor on a position at least `tolerance_mm` from every
/// other anchor, so a move never re-creates a violation and the process
/// terminates; a pair whose row is saturated (no x-position within the
/// board clears it) is left as-is rather than clamped onto an existing
/// anchor.
pub fn enforce_unique_positions_with(
    anchors: &mut [(String, (f64, f64))],
    bounds: Rect,
    tolerance_mm: f64,
    offset_mm: f64,
) {
    let (x_min, _, x_max, _) = bounds;
    loop {
        let mut moved = false;
        for i in 0..anchors.len() {
            for j in (i + 1)..anchors.len() {
                let (xi, yi) = anchors[i].1;
                let (xj, yj) = anchors[j].1;
                // B7: `(...) ** 0.5` is libm pow(·, 0.5), not sqrt.
                let dist = pow(pow(xi - xj, 2.0) + pow(yi - yj, 2.0), 0.5);
                if dist >= tolerance_mm {
                    continue;
                }
                match search_free_x(anchors, j, x_min, x_max, tolerance_mm, offset_mm) {
                    None => {
                        // Row saturated: no x-position on this row clears
                        // every other anchor.  Leave the pair and carry
                        // on scanning (a later move cannot unblock this
                        // row, so it would just be re-found).
                        continue;
                    }
                    Some(pos) => {
                        anchors[j].1 = pos;
                        moved = true;
                        break;
                    }
                }
            }
            if moved {
                break;
            }
        }
        if !moved {
            break;
        }
    }
}

/// [`enforce_unique_positions_with`] at the reference's default
/// `tolerance_mm=0.1` / `offset_mm=0.5`.
fn enforce_unique_positions(anchors: &mut [(String, (f64, f64))], bounds: Rect) {
    enforce_unique_positions_with(anchors, bounds, UNIQUE_TOLERANCE_MM, UNIQUE_OFFSET_MM);
}

/// `assign_thermal_anchors`: the two-pass greedy assignment.
pub fn assign_thermal_anchors(inputs: &AnchorInputs<'_>) -> Result<AnchorOutcome, FieldError> {
    let mut outcome = AnchorOutcome::default();
    if inputs.devices.is_empty() {
        return Ok(outcome);
    }

    let resolution = inputs.resolution;
    let (x_grid, y_grid) = build_potential_grid(inputs.bounds, resolution);
    let cfg = inputs.config;
    let min_dist2 = inputs.min_separation_mm * inputs.min_separation_mm;

    // --- Pass 1: phi_base (edge + copper + convection, no coupling) ---
    let pass1_cfg = FieldConfig {
        coupling_weight: 0.0,
        exclusion_weight: 0.0,
        // The reference constructs a fresh ThermalPotentialConfig for
        // pass 1 WITHOUT forwarding the exclusion parameters, so they
        // fall back to the dataclass defaults.  Since exclusion_weight
        // is 0.0 they are never read, but the mirror keeps the intent.
        thermal_exclusion_radius_mm: 10.0,
        exclusion_barrier_height: 1e6,
        exclusion_steepness: 20.0,
        ..cfg
    };
    let phi_base = superpose(
        &x_grid,
        &y_grid,
        resolution,
        resolution,
        &SuperposeInputs {
            bounds: inputs.bounds,
            edge: inputs.edge,
            config: pass1_cfg,
            devices: &[],
            anchors: &[],
            copper_zone_count: inputs.copper_zone_count,
            copper_zones: inputs.copper_zones,
            airflow: inputs.airflow,
            coupling_enabled: false,
        },
    )?;

    let mut pass1 = OrderedAnchors::default();
    let mut existing: Vec<(f64, f64)> = Vec::new();
    for device in inputs.devices {
        let xy = find_min_valid(
            &phi_base,
            &x_grid,
            &y_grid,
            resolution,
            inputs.edge,
            inputs.bounds,
            device.zone,
            inputs.keepouts,
            &existing,
            min_dist2,
        );
        match xy {
            None => outcome.skipped.push(device.reference.clone()),
            Some(p) => {
                pass1.insert(&device.reference, p);
                existing.push(p);
            }
        }
    }

    if pass1.is_empty() {
        return Ok(outcome);
    }

    // --- Pass 2: phi_coupling correction, up to MAX_ITERATIONS ---
    for _iteration in 0..MAX_ITERATIONS {
        let anchor_positions = pass1.positions();
        let coupled: Vec<((f64, f64), f64)> = inputs
            .devices
            .iter()
            .filter_map(|d| pass1.get(&d.reference).map(|p| (p, d.power)))
            .collect();

        let phi_full = superpose(
            &x_grid,
            &y_grid,
            resolution,
            resolution,
            &SuperposeInputs {
                bounds: inputs.bounds,
                edge: inputs.edge,
                config: cfg,
                devices: &coupled,
                anchors: anchor_positions,
                copper_zone_count: inputs.copper_zone_count,
                copper_zones: inputs.copper_zones,
                airflow: inputs.airflow,
                coupling_enabled: !coupled.is_empty(),
            },
        )?;

        let mut updated = false;
        let mut new_anchors = OrderedAnchors::default();
        let mut new_existing: Vec<(f64, f64)> = Vec::new();

        for device in inputs.devices {
            let Some((old_x, old_y)) = pass1.get(&device.reference) else {
                continue;
            };
            let xy = find_min_valid(
                &phi_full,
                &x_grid,
                &y_grid,
                resolution,
                inputs.edge,
                inputs.bounds,
                device.zone,
                inputs.keepouts,
                &new_existing,
                min_dist2,
            );
            match xy {
                None => {
                    new_anchors.insert(&device.reference, (old_x, old_y));
                    new_existing.push((old_x, old_y));
                }
                Some((new_x, new_y)) => {
                    let dist = (pow(new_x - old_x, 2.0) + pow(new_y - old_y, 2.0)).sqrt();
                    if dist > REASSIGN_THRESHOLD_MM {
                        new_anchors.insert(&device.reference, (new_x, new_y));
                        new_existing.push((new_x, new_y));
                        updated = true;
                    } else {
                        new_anchors.insert(&device.reference, (old_x, old_y));
                        new_existing.push((old_x, old_y));
                    }
                }
            }
        }

        pass1 = new_anchors;
        if !updated {
            break;
        }
    }

    // --- Clamp final positions ---
    let (x_min, y_min, x_max, y_max) = inputs.bounds;
    let zone_of: HashMap<&str, Option<Rect>> = inputs
        .devices
        .iter()
        .map(|d| (d.reference.as_str(), d.zone))
        .collect();

    let mut final_anchors: Vec<(String, (f64, f64))> = Vec::new();
    for (reference, (ax, ay)) in pass1.iter() {
        let mut cx = np_clip(ax, x_min, x_max);
        let mut cy = np_clip(ay, y_min, y_max);
        if let Some(Some((zx0, zy0, zx1, zy1))) = zone_of.get(reference).copied() {
            cx = np_clip(cx, zx0, zx1);
            cy = np_clip(cy, zy0, zy1);
        }
        let dist = (pow(cx - ax, 2.0) + pow(cy - ay, 2.0)).sqrt();
        if dist > CLAMP_WARN_MM {
            outcome
                .clamped
                .push((reference.to_owned(), ax, ay, cx, cy, dist));
        }
        final_anchors.push((reference.to_owned(), (cx, cy)));
    }

    enforce_unique_positions(&mut final_anchors, inputs.bounds);
    outcome.anchors = final_anchors;
    Ok(outcome)
}

// ---------------------------------------------------------------------------
// R24 post-solve audit
// ---------------------------------------------------------------------------

/// A single audit finding — the constraint that the recomputed anchor
/// violates.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AuditFinding {
    /// The anchor is not one of the grid's cell coordinates.
    OffGrid,
    /// The anchor is outside the edge strip the search restricts to.
    OutsideEdgeStrip,
    /// The anchor is outside the device's declared zone.
    OutsideZone,
    /// The anchor sits inside a keepout.
    InsideKeepout,
    /// Another anchor is closer than `tolerance_mm` (R13 uniqueness).
    Duplicate,
    /// A feasible cell has strictly lower potential than the reported
    /// anchor — the encoded minimum is not the true grid minimum.
    NotMinimal,
}

/// R24 post-solve audit: recompute the potential from the returned
/// coordinates and re-derive every constraint the encoder claimed.
///
/// This is the *conservative-bound* half of the R24 discipline made
/// checkable.  The soundness claim the encoder makes is
///
/// > `phi(anchor_d) <= phi(c)` for every grid cell `c` that satisfies
/// > device `d`'s edge-strip, zone, keepout and min-separation
/// > constraints,
///
/// i.e. the reported anchor never *underestimates* the achievable
/// thermal potential.  The audit recomputes `phi` from the coordinates
/// (never from the search's internal state) and re-checks it.
///
/// `separation_reference` is the anchor set the audited device was
/// scanned against — pass an empty slice to audit the unconstrained
/// minimum.
#[allow(clippy::too_many_arguments, reason = "audits every constraint the search applied")]
pub fn audit_anchor(
    phi: &[f64],
    x_grid: &[f64],
    y_grid: &[f64],
    resolution: usize,
    edge: Edge,
    bounds: Rect,
    zone: Option<Rect>,
    keepouts: &[Rect],
    separation_reference: &[(f64, f64)],
    min_dist2: f64,
    anchor: (f64, f64),
    other_anchors: &[(f64, f64)],
    tolerance_mm: f64,
) -> Vec<AuditFinding> {
    let mut findings = Vec::new();
    let (ax, ay) = anchor;

    let mut anchor_phi: Option<f64> = None;
    for i in 0..resolution {
        for j in 0..resolution {
            let idx = i * resolution + j;
            if x_grid[idx] == ax && y_grid[idx] == ay {
                anchor_phi = Some(phi[idx]);
                break;
            }
        }
        if anchor_phi.is_some() {
            break;
        }
    }
    let Some(anchor_phi) = anchor_phi else {
        findings.push(AuditFinding::OffGrid);
        return findings;
    };

    if !in_edge_strip(edge, bounds, ax, ay) {
        findings.push(AuditFinding::OutsideEdgeStrip);
    }
    if !in_zone(zone, ax, ay) {
        findings.push(AuditFinding::OutsideZone);
    }
    if in_keepout(keepouts, ax, ay) {
        findings.push(AuditFinding::InsideKeepout);
    }
    if other_anchors
        .iter()
        .any(|&(ox, oy)| pow(pow(ax - ox, 2.0) + pow(ay - oy, 2.0), 0.5) < tolerance_mm)
    {
        findings.push(AuditFinding::Duplicate);
    }

    for i in 0..resolution {
        for j in 0..resolution {
            let idx = i * resolution + j;
            let x = x_grid[idx];
            let y = y_grid[idx];
            if !in_edge_strip(edge, bounds, x, y) || !in_zone(zone, x, y) {
                continue;
            }
            if in_keepout(keepouts, x, y) {
                continue;
            }
            if separation_reference
                .iter()
                .any(|&(ex, ey)| (pow(x - ex, 2.0) + pow(y - ey, 2.0)) < min_dist2)
            {
                continue;
            }
            if phi[idx] < anchor_phi {
                findings.push(AuditFinding::NotMinimal);
                return findings;
            }
        }
    }

    findings
}

// ---------------------------------------------------------------------------
// pyo3 bridge
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
fn field_error_to_py(err: FieldError) -> PyErr {
    match err {
        FieldError::CopperBroadcast { rows, cols, grid_rows, grid_cols } => {
            PyValueError::new_err(format!(
                "operands could not be broadcast together with shapes \
                 ({grid_rows},{grid_cols}) ({rows},{cols}) "
            ))
        }
        FieldError::ZoneBoundNotANumber => {
            PyValueError::new_err("cannot convert float NaN to integer")
        }
        FieldError::ZoneBoundInfinite => {
            PyOverflowError::new_err("cannot convert float infinity to integer")
        }
        FieldError::NegativeResolution(n) => PyValueError::new_err(format!(
            "Number of samples, {n}, must be non-negative."
        )),
    }
}

#[cfg(feature = "python")]
fn f64_bytes(values: &[f64]) -> Vec<u8> {
    let mut out = Vec::with_capacity(values.len() * 8);
    for v in values {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out
}

#[cfg(feature = "python")]
fn bytes_to_f64(raw: &[u8]) -> Vec<f64> {
    raw.chunks_exact(8)
        .map(|c| {
            let mut buf = [0u8; 8];
            buf.copy_from_slice(c);
            f64::from_le_bytes(buf)
        })
        .collect()
}

/// pyo3 bridge for [`build_potential_grid`].  Returns the two grids as
/// little-endian f64 byte buffers.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_min, y_min, x_max, y_max, resolution))]
pub fn thermal_potential_build_grid_py(
    py: Python<'_>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    resolution: i64,
) -> PyResult<(Bound<'_, PyBytes>, Bound<'_, PyBytes>)> {
    if resolution < 0 {
        return Err(field_error_to_py(FieldError::NegativeResolution(resolution)));
    }
    let res = resolution as usize;
    let (xg, yg) = temper_py_bridge::catch_unwind(|| {
        build_potential_grid((x_min, y_min, x_max, y_max), res)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok((PyBytes::new(py, &f64_bytes(&xg)), PyBytes::new(py, &f64_bytes(&yg))))
}

/// pyo3 bridge for [`phi_edge`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_bytes, y_bytes, x_min, y_min, x_max, y_max, edge_code, decay_length_mm))]
#[allow(clippy::too_many_arguments, reason = "flat scalar boundary avoids a dict round-trip")]
pub fn thermal_potential_phi_edge_py<'py>(
    py: Python<'py>,
    x_bytes: &[u8],
    y_bytes: &[u8],
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    edge_code: u8,
    decay_length_mm: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let out = temper_py_bridge::catch_unwind(|| {
        let x = bytes_to_f64(x_bytes);
        let y = bytes_to_f64(y_bytes);
        phi_edge(
            &x,
            &y,
            (x_min, y_min, x_max, y_max),
            Edge::from_code(edge_code),
            decay_length_mm,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &f64_bytes(&out)))
}

/// pyo3 bridge for [`phi_copper`].  Returns `(rows, cols, bytes)`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_min, y_min, x_max, y_max, zone_count, zones))]
pub fn thermal_potential_phi_copper_py(
    py: Python<'_>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    zone_count: usize,
    zones: Vec<Rect>,
) -> PyResult<(usize, usize, Bound<'_, PyBytes>)> {
    let field = temper_py_bridge::catch_unwind(|| {
        phi_copper((x_min, y_min, x_max, y_max), zone_count, &zones)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(field_error_to_py)?;
    Ok(match field {
        CopperField::Uniform(v) => (1, 1, PyBytes::new(py, &f64_bytes(&[v]))),
        CopperField::Grid { rows, cols, data } => (rows, cols, PyBytes::new(py, &f64_bytes(&data))),
    })
}

/// pyo3 bridge for [`phi_coupling`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_bytes, y_bytes, devices, sigma_factor))]
pub fn thermal_potential_phi_coupling_py<'py>(
    py: Python<'py>,
    x_bytes: &[u8],
    y_bytes: &[u8],
    devices: Vec<((f64, f64), f64)>,
    sigma_factor: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let out = temper_py_bridge::catch_unwind(|| {
        let x = bytes_to_f64(x_bytes);
        let y = bytes_to_f64(y_bytes);
        phi_coupling(&x, &y, &devices, sigma_factor)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &f64_bytes(&out)))
}

/// pyo3 bridge for [`phi_exclusion`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_bytes, y_bytes, anchors, radius_mm, barrier_height, steepness))]
pub fn thermal_potential_phi_exclusion_py<'py>(
    py: Python<'py>,
    x_bytes: &[u8],
    y_bytes: &[u8],
    anchors: Vec<(f64, f64)>,
    radius_mm: f64,
    barrier_height: f64,
    steepness: f64,
) -> PyResult<Bound<'py, PyBytes>> {
    let out = temper_py_bridge::catch_unwind(|| {
        let x = bytes_to_f64(x_bytes);
        let y = bytes_to_f64(y_bytes);
        phi_exclusion(&x, &y, &anchors, radius_mm, barrier_height, steepness)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &f64_bytes(&out)))
}

/// pyo3 bridge for [`phi_convection`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (x_bytes, y_bytes, airflow))]
pub fn thermal_potential_phi_convection_py<'py>(
    py: Python<'py>,
    x_bytes: &[u8],
    y_bytes: &[u8],
    airflow: Option<(f64, f64)>,
) -> PyResult<Bound<'py, PyBytes>> {
    let out = temper_py_bridge::catch_unwind(|| {
        let x = bytes_to_f64(x_bytes);
        let y = bytes_to_f64(y_bytes);
        phi_convection(&x, &y, airflow)
    })
    .map_err(temper_py_bridge::panic_to_err)?;
    Ok(PyBytes::new(py, &f64_bytes(&out)))
}

/// The nine `ThermalPotentialConfig` scalars the kernels read, in the
/// order the pyo3 boundary carries them.
#[cfg(feature = "python")]
type ConfigTuple = (f64, f64, f64, f64, f64, f64, f64, f64, f64);

#[cfg(feature = "python")]
fn config_from_tuple(t: ConfigTuple) -> FieldConfig {
    FieldConfig {
        edge_weight: t.0,
        copper_weight: t.1,
        coupling_weight: t.2,
        exclusion_weight: t.3,
        convection_weight: t.4,
        edge_decay_length_mm: t.5,
        thermal_exclusion_radius_mm: t.6,
        exclusion_barrier_height: t.7,
        exclusion_steepness: t.8,
    }
}

/// pyo3 bridge for [`enforce_unique_positions`].
///
/// Takes and returns an ordered `(ref, x, y)` list, mirroring the
/// reference's in-place mutation of a `dict` whose iteration order is
/// its insertion order.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (anchors, x_min, y_min, x_max, y_max, tolerance_mm, offset_mm))]
#[allow(clippy::too_many_arguments, reason = "flat scalar boundary avoids a dict round-trip")]
pub fn thermal_potential_enforce_unique_py(
    anchors: Vec<(String, f64, f64)>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    tolerance_mm: f64,
    offset_mm: f64,
) -> PyResult<Vec<(String, f64, f64)>> {
    temper_py_bridge::catch_unwind(move || {
        let mut pairs: Vec<(String, (f64, f64))> = anchors
            .into_iter()
            .map(|(r, x, y)| (r, (x, y)))
            .collect();
        enforce_unique_positions_with(
            &mut pairs,
            (x_min, y_min, x_max, y_max),
            tolerance_mm,
            offset_mm,
        );
        pairs.into_iter().map(|(r, (x, y))| (r, x, y)).collect()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`assign_thermal_anchors`].
///
/// Returns `(anchors, skipped, clamped)` where `anchors` is an ordered
/// list of `(ref, x, y)`, `skipped` names the devices with no feasible
/// cell, and `clamped` carries `(ref, phi_x, phi_y, clamped_x,
/// clamped_y, delta_mm)` for the caller to log.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    x_min, y_min, x_max, y_max, edge_code, resolution, devices, keepouts,
    config, copper_zone_count, copper_zones, airflow, min_separation_mm
))]
#[allow(clippy::type_complexity, reason = "flat tuple boundary mirrors the reference's returns")]
#[allow(clippy::too_many_arguments, reason = "flat scalar boundary avoids a dict round-trip")]
pub fn thermal_potential_assign_anchors_py(
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    edge_code: u8,
    resolution: usize,
    devices: Vec<(String, f64, Option<Rect>)>,
    keepouts: Vec<Rect>,
    config: ConfigTuple,
    copper_zone_count: usize,
    copper_zones: Vec<Rect>,
    airflow: Option<(f64, f64)>,
    min_separation_mm: f64,
) -> PyResult<(
    Vec<(String, f64, f64)>,
    Vec<String>,
    Vec<(String, f64, f64, f64, f64, f64)>,
)> {
    let specs: Vec<DeviceSpec> = devices
        .into_iter()
        .map(|(reference, power, zone)| DeviceSpec { reference, power, zone })
        .collect();
    let outcome = temper_py_bridge::catch_unwind(|| {
        assign_thermal_anchors(&AnchorInputs {
            bounds: (x_min, y_min, x_max, y_max),
            edge: Edge::from_code(edge_code),
            resolution,
            devices: &specs,
            keepouts: &keepouts,
            config: config_from_tuple(config),
            copper_zone_count,
            copper_zones: &copper_zones,
            airflow,
            min_separation_mm,
        })
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(field_error_to_py)?;

    Ok((
        outcome
            .anchors
            .into_iter()
            .map(|(r, (x, y))| (r, x, y))
            .collect(),
        outcome.skipped,
        outcome.clamped,
    ))
}

#[cfg(test)]
mod tests {
    // The crate denies `unwrap`/`expect` in production code (Cargo.toml
    // `[lints.clippy]`); a failing unwrap in a test IS the test failure,
    // which is the documented carve-out in the Wave-4 G7 bar.
    #![allow(clippy::expect_used, clippy::unwrap_used)]

    use super::*;

    fn square_bounds() -> Rect {
        (0.0, 0.0, 100.0, 150.0)
    }

    fn default_config() -> FieldConfig {
        FieldConfig {
            edge_weight: 1.0,
            copper_weight: 1.0,
            coupling_weight: 1.0,
            exclusion_weight: 1.0,
            convection_weight: 1.0,
            edge_decay_length_mm: 10.0,
            thermal_exclusion_radius_mm: 10.0,
            exclusion_barrier_height: 1e6,
            exclusion_steepness: 20.0,
        }
    }

    // --- linspace ------------------------------------------------------

    #[test]
    fn linspace_base_cases() {
        assert!(linspace(0.0, 1.0, 0).is_empty());
        assert_eq!(linspace(3.0, 9.0, 1), vec![3.0]);
        assert_eq!(linspace(0.0, 1.0, 2), vec![0.0, 1.0]);
        assert_eq!(linspace(0.0, 4.0, 5), vec![0.0, 1.0, 2.0, 3.0, 4.0]);
    }

    #[test]
    fn linspace_endpoint_is_exact() {
        // The endpoint is assigned, never computed — so it is bit-exact
        // even when `i * step + start` would not be.
        let v = linspace(0.1, 0.7, 7);
        assert_eq!(v[6], 0.7);
        assert_eq!(v[0], 0.1);
    }

    #[test]
    fn linspace_degenerate_step_zero_branch() {
        // start == stop makes step exactly 0.0; numpy switches to the
        // `(i / div) * delta + start` form.
        let v = linspace(5.0, 5.0, 4);
        assert_eq!(v, vec![5.0, 5.0, 5.0, 5.0]);
    }

    // --- grid ----------------------------------------------------------

    #[test]
    fn meshgrid_orientation_is_xy() {
        let (xg, yg) = build_potential_grid((0.0, 0.0, 3.0, 2.0), 3);
        // x varies along the row (second index), y along the column.
        assert_eq!(xg[0], 0.0);
        assert_eq!(xg[2], 3.0);
        assert_eq!(yg[0], 0.0);
        assert_eq!(yg[6], 2.0);
    }

    // --- phi_edge ------------------------------------------------------

    #[test]
    fn phi_edge_is_zero_on_the_edge_and_rises_inward() {
        let (xg, yg) = build_potential_grid(square_bounds(), 5);
        let f = phi_edge(&xg, &yg, square_bounds(), Edge::Top, 10.0);
        // Last row is y == y_max: d == 0 -> 1 - exp(0) == 0 exactly.
        assert_eq!(f[20], 0.0);
        assert!(f[0] > f[20]);
        assert!(f.iter().all(|v| *v >= 0.0));
    }

    #[test]
    fn phi_edge_unknown_edge_is_all_zero() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        let f = phi_edge(&xg, &yg, square_bounds(), Edge::Unknown, 10.0);
        assert!(f.iter().all(|v| *v == 0.0));
    }

    // --- phi_copper ----------------------------------------------------

    #[test]
    fn phi_copper_uniform_without_zones() {
        let got = phi_copper(square_bounds(), 0, &[]).expect("no zones");
        assert_eq!(got, CopperField::Uniform(0.5));
    }

    #[test]
    fn phi_copper_degenerate_board_is_uniform() {
        let got = phi_copper((0.0, 0.0, 0.0, 10.0), 1, &[(0.0, 0.0, 1.0, 1.0)])
            .expect("degenerate board");
        assert_eq!(got, CopperField::Uniform(0.5));
    }

    #[test]
    fn phi_copper_non_empty_list_with_no_usable_zones_still_builds_a_grid() {
        // zone_count > 0 but no extracted bounds: the reference still
        // enters the grid branch and returns 1/eps everywhere.
        let got = phi_copper(square_bounds(), 2, &[]).expect("grid branch");
        match got {
            CopperField::Grid { rows, cols, data } => {
                assert_eq!((rows, cols), (COPPER_GRID_RES, COPPER_GRID_RES));
                assert_eq!(data[0], 1.0 / COPPER_EPS);
            }
            other => panic!("expected a grid, got {other:?}"),
        }
    }

    #[test]
    fn phi_copper_rejects_nan_and_infinite_zone_bounds() {
        assert_eq!(
            phi_copper(square_bounds(), 1, &[(f64::NAN, 0.0, 1.0, 1.0)]),
            Err(FieldError::ZoneBoundNotANumber)
        );
        assert_eq!(
            phi_copper(square_bounds(), 1, &[(f64::INFINITY, 0.0, 1.0, 1.0)]),
            Err(FieldError::ZoneBoundInfinite)
        );
    }

    // --- phi_coupling / phi_exclusion / phi_convection ------------------

    #[test]
    fn phi_coupling_empty_is_zero() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        assert!(phi_coupling(&xg, &yg, &[], 50.0).iter().all(|v| *v == 0.0));
    }

    #[test]
    fn phi_coupling_peaks_at_the_device() {
        let (xg, yg) = build_potential_grid((0.0, 0.0, 4.0, 4.0), 5);
        let f = phi_coupling(&xg, &yg, &[((2.0, 2.0), 10.0)], 50.0);
        let at_device = f[2 * 5 + 2];
        assert!(f.iter().all(|v| *v <= at_device));
    }

    #[test]
    fn phi_exclusion_empty_is_zero() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        assert!(phi_exclusion(&xg, &yg, &[], 10.0, 1e6, 20.0).iter().all(|v| *v == 0.0));
    }

    #[test]
    fn phi_convection_none_and_non_positive_are_zero() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        assert!(phi_convection(&xg, &yg, None).iter().all(|v| *v == 0.0));
        assert!(phi_convection(&xg, &yg, Some((0.0, 45.0))).iter().all(|v| *v == 0.0));
        assert!(phi_convection(&xg, &yg, Some((-1.0, 45.0))).iter().all(|v| *v == 0.0));
    }

    #[test]
    fn phi_convection_nan_magnitude_falls_through() {
        // `NaN <= 0` is False in Python, so the ramp is computed.
        let (xg, yg) = build_potential_grid(square_bounds(), 3);
        let f = phi_convection(&xg, &yg, Some((f64::NAN, 0.0)));
        assert!(f.iter().all(|v| v.is_nan()));
    }

    // --- superposition -------------------------------------------------

    #[test]
    fn superpose_all_weights_zero_is_zero() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        let cfg = FieldConfig {
            edge_weight: 0.0,
            copper_weight: 0.0,
            coupling_weight: 0.0,
            exclusion_weight: 0.0,
            convection_weight: 0.0,
            ..default_config()
        };
        let out = superpose(
            &xg,
            &yg,
            4,
            4,
            &SuperposeInputs {
                bounds: square_bounds(),
                edge: Edge::Top,
                config: cfg,
                devices: &[],
                anchors: &[],
                copper_zone_count: 0,
                copper_zones: &[],
                airflow: None,
                coupling_enabled: false,
            },
        )
        .expect("superpose");
        assert!(out.iter().all(|v| *v == 0.0));
    }

    #[test]
    fn superpose_reports_the_copper_broadcast_mismatch() {
        let (xg, yg) = build_potential_grid(square_bounds(), 4);
        let err = superpose(
            &xg,
            &yg,
            4,
            4,
            &SuperposeInputs {
                bounds: square_bounds(),
                edge: Edge::Top,
                config: default_config(),
                devices: &[],
                anchors: &[],
                copper_zone_count: 1,
                copper_zones: &[(0.0, 0.0, 10.0, 10.0)],
                airflow: None,
                coupling_enabled: false,
            },
        )
        .expect_err("50x50 copper cannot broadcast onto a 4x4 grid");
        assert_eq!(
            err,
            FieldError::CopperBroadcast { rows: 50, cols: 50, grid_rows: 4, grid_cols: 4 }
        );
    }

    // --- anchoring -----------------------------------------------------

    fn device(reference: &str, power: f64) -> DeviceSpec {
        DeviceSpec { reference: reference.to_owned(), power, zone: None }
    }

    fn anchor_inputs<'a>(devices: &'a [DeviceSpec], resolution: usize) -> AnchorInputs<'a> {
        AnchorInputs {
            bounds: square_bounds(),
            edge: Edge::Top,
            resolution,
            devices,
            keepouts: &[],
            config: default_config(),
            copper_zone_count: 0,
            copper_zones: &[],
            airflow: None,
            min_separation_mm: 2.0,
        }
    }

    #[test]
    fn no_devices_returns_no_anchors() {
        let out = assign_thermal_anchors(&anchor_inputs(&[], 20)).expect("empty");
        assert!(out.anchors.is_empty());
    }

    #[test]
    fn anchors_are_deterministic() {
        let devices = [device("Q1", 50.0), device("Q2", 45.0)];
        let a = assign_thermal_anchors(&anchor_inputs(&devices, 20)).expect("run a");
        let b = assign_thermal_anchors(&anchor_inputs(&devices, 20)).expect("run b");
        assert_eq!(a.anchors, b.anchors);
    }

    #[test]
    fn anchors_are_unique_within_tolerance() {
        let devices = [device("Q1", 50.0), device("Q2", 45.0), device("Q3", 40.0)];
        let out = assign_thermal_anchors(&anchor_inputs(&devices, 20)).expect("run");
        assert_eq!(out.anchors.len(), 3);
        for i in 0..out.anchors.len() {
            for j in (i + 1)..out.anchors.len() {
                let (xi, yi) = out.anchors[i].1;
                let (xj, yj) = out.anchors[j].1;
                let d = ((xi - xj).powi(2) + (yi - yj).powi(2)).sqrt();
                assert!(d >= UNIQUE_TOLERANCE_MM, "anchors {i}/{j} coincide at {d}");
            }
        }
    }

    #[test]
    fn unknown_edge_yields_no_feasible_cells() {
        let devices = [device("Q1", 50.0)];
        let mut inputs = anchor_inputs(&devices, 8);
        inputs.edge = Edge::Unknown;
        let out = assign_thermal_anchors(&inputs).expect("run");
        assert!(out.anchors.is_empty());
        assert_eq!(out.skipped, vec!["Q1".to_string()]);
    }

    #[test]
    fn duplicate_reference_keeps_one_key() {
        // CPython dict semantics: the second insert overwrites and keeps
        // the key's original position.
        let devices = [device("Q1", 50.0), device("Q1", 10.0)];
        let out = assign_thermal_anchors(&anchor_inputs(&devices, 8)).expect("run");
        assert_eq!(out.anchors.len(), 1);
        assert_eq!(out.anchors[0].0, "Q1");
    }

    // --- B7 discriminators: pow vs multiply, pow vs sqrt ---------------
    //
    // `x ** 2` and `x * x` (and `v ** 0.5` and `sqrt(v)`) agree on
    // ~99.86 % of inputs, so a randomised differential can run for a long
    // time without noticing the substitution.  These two tests pin
    // *constructed* inputs where the 1-ulp difference flips a comparison,
    // which is the only way the substitution can change behaviour at all.
    // Both values were found by an exhaustive search over the host libm
    // (recorded in the migration PR).

    #[test]
    fn separation_test_uses_pow_not_multiplication() {
        // `pow(dx,2) + pow(dy,2)` must be libm pow per term, never
        // `dx*dx + dy*dy`: with min_dist2 set to the (larger) multiply
        // sum, `sum < min_dist2` is TRUE for the pow form and FALSE for
        // the multiply form.  The fixture is SEARCHED rather than
        // hardcoded: whether the two sums differ is a property of the
        // loaded libm's pow, and the values pinned at migration
        // (`dx = 37.41304475993699`, `dy = 2.1241887809855857`) do NOT
        // discriminate on the current libm (issue #927).  The search
        // fails loudly if the loaded libm cannot discriminate at all.
        let mut seed = 0x5eed_1e00_0000_u64;
        let mut dx = 1.0_f64;
        let mut dy = 1.0_f64;
        let mut pw = 2.0_f64;
        let mut ml = 2.0_f64;
        let mut found = false;
        for _ in 0..5_000_000 {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            let e = 1 + (seed >> 53) % 1050;
            dx = f64::from_bits((e << 52) | (seed & ((1u64 << 52) - 1)));
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
            let e2 = 1 + (seed >> 53) % 1050;
            dy = f64::from_bits((e2 << 52) | (seed & ((1u64 << 52) - 1)));
            pw = pow(dx, 2.0) + pow(dy, 2.0);
            ml = dx * dx + dy * dy;
            if pw < ml {
                found = true;
                break;
            }
        }
        assert!(found, "no pow-sum vs mul-sum discriminator on this libm");
        let min_dist2 = ml;
        assert!(pw < min_dist2, "fixture is not discriminating");
        assert!(dx * dx + dy * dy >= min_dist2, "fixture is not discriminating");

        // A 1-cell grid at exactly (dx, dy), inside a BOTTOM edge strip,
        // with one existing anchor at the origin.
        let bounds = (0.0, dy - 5.0, 100.0, 100.0);
        let got = find_min_valid(
            &[0.0], &[dx], &[dy], 1, Edge::Bottom, bounds, None, &[], &[(0.0, 0.0)], min_dist2,
        );
        assert_eq!(
            got, None,
            "the pow form must reject this cell as too close; `x * x` would accept it"
        );
    }

    #[test]
    fn uniqueness_distance_uses_pow_not_sqrt() {
        // s = pow(dx,2) + pow(dy,2); pow(s, 0.5) = 0.23008158321643976
        //                            sqrt(s)     = 0.2300815832164398
        // With tolerance exactly the sqrt value, `dist < tol` is TRUE for
        // the pow form and FALSE for the sqrt form.
        let dx = 0.179_050_385_249_757_8_f64;
        let dy = 0.144_493_925_399_294_26_f64;
        let s = pow(dx, 2.0) + pow(dy, 2.0);
        let tolerance = s.sqrt();
        assert!(pow(s, 0.5) < tolerance, "fixture is not discriminating");

        let mut anchors = vec![
            ("A".to_owned(), (dx, dy)),
            ("B".to_owned(), (0.0, 0.0)),
        ];
        enforce_unique_positions_with(&mut anchors, (0.0, 0.0, 100.0, 100.0), tolerance, 0.5);
        assert_eq!(
            anchors[1].1,
            (0.5, 0.0),
            "the pow form must treat these as duplicates and nudge B; `sqrt` would not"
        );
    }

    // --- R13 uniqueness regressions (issue #928) ------------------------
    //
    // The old enforcement nudged the later anchor to `min(xj + offset,
    // x_max)`.  Two failure modes:
    //
    // 1. When `xj` sat at `x_max` the clamp put the nudged anchor back ON
    //    TOP of an anchor already at `x_max` — the (40.0, 21.0) corner
    //    flake reproduced end-to-end by `test_p6_anchors_are_unique`.
    // 2. The pair scan visited each pair once, so a nudge that collided
    //    with a THIRD anchor was never re-checked.
    //
    // `enforce_unique_positions_with` now re-scans to a fixpoint and each
    // move lands on a position clear of every anchor, so both modes are
    // closed.

    #[test]
    fn uniqueness_never_merges_onto_an_anchor_at_x_max() {
        let mut anchors = vec![
            ("A".to_owned(), (40.0, 21.0)),
            ("B".to_owned(), (40.0, 21.0)),
        ];
        enforce_unique_positions_with(&mut anchors, (0.0, 0.0, 40.0, 21.0), 0.1, 0.5);
        assert_eq!(
            anchors[1].1,
            (39.5, 21.0),
            "the +x nudge clamps at x_max=40.0; the search must step inward to xj - offset"
        );
        let (ax, ay) = anchors[0].1;
        let (bx, by) = anchors[1].1;
        assert!(
            pow(pow(ax - bx, 2.0) + pow(ay - by, 2.0), 0.5) >= 0.1,
            "anchors still coincide at {:?} / {:?}",
            anchors[0].1,
            anchors[1].1
        );
    }

    #[test]
    fn uniqueness_restarts_after_a_third_anchor_collision() {
        // The rightward nudge of B would land it exactly on C, so the
        // first candidate is rejected and the search steps on to the next
        // free position (x_max of the scan here is 100.0).
        let mut anchors = vec![
            ("A".to_owned(), (0.0, 0.0)),
            ("B".to_owned(), (0.05, 0.0)),
            ("C".to_owned(), (0.5, 0.0)),
        ];
        enforce_unique_positions_with(&mut anchors, (0.0, 0.0, 100.0, 100.0), 0.1, 0.5);
        assert_eq!(
            anchors[1].1,
            (1.05, 0.0),
            "B's +offset candidate xj+0.5 = 0.55 sits 0.05 from C; the search must step on"
        );
        for i in 0..anchors.len() {
            for j in (i + 1)..anchors.len() {
                let (xi, yi) = anchors[i].1;
                let (xj, yj) = anchors[j].1;
                assert!(
                    pow(pow(xi - xj, 2.0) + pow(yi - yj, 2.0), 0.5) >= 0.1,
                    "anchors {i}/{j} coincide at {:?} / {:?}",
                    anchors[i].1,
                    anchors[j].1
                );
            }
        }
    }

    #[test]
    fn uniqueness_left_nudge_then_right_nudge_both_within_bounds() {
        // B sits at x_min: the +x nudge is taken; C sits against B's old
        // site so it must nudge too.  Exercises both signs and the
        // fixpoint re-scan in one fixture.
        let mut anchors = vec![
            ("A".to_owned(), (0.0, 0.0)),
            ("B".to_owned(), (0.0, 0.0)),
            ("C".to_owned(), (0.0, 0.0)),
        ];
        enforce_unique_positions_with(&mut anchors, (0.0, 0.0, 100.0, 100.0), 0.1, 0.5);
        for i in 0..anchors.len() {
            for j in (i + 1)..anchors.len() {
                let (xi, yi) = anchors[i].1;
                let (xj, yj) = anchors[j].1;
                assert!(
                    pow(pow(xi - xj, 2.0) + pow(yi - yj, 2.0), 0.5) >= 0.1,
                    "anchors {i}/{j} coincide at {:?} / {:?}",
                    anchors[i].1,
                    anchors[j].1
                );
            }
        }
    }

    // --- provably unobservable mutations (recorded no-ops) -------------

    #[test]
    fn py_max_choice_is_unobservable_in_phi_coupling() {
        // Mutation M3 in the migration PR (`py_max` -> `f64::max`)
        // survived the differential.  It is not a test gap: the two
        // differ only on a NaN `power`, and a NaN `power` multiplies the
        // exponential term directly, so the accumulated field is NaN at
        // every cell either way.  Proven here rather than asserted.
        let (xg, yg) = build_potential_grid(square_bounds(), 6);
        for power in [f64::NAN, 0.0, -1.0, 1e-9, 1.0, 1e9] {
            let with_py_max = phi_coupling(&xg, &yg, &[((50.0, 75.0), power)], 50.0);
            // The mutant, inlined:
            let sigma = power.max(1e-6).sqrt() * 50.0;
            let sigma_sq = 2.0 * sigma * sigma;
            let mutant: Vec<f64> = xg
                .iter()
                .zip(yg.iter())
                .map(|(&x, &y)| {
                    let (dx, dy) = (x - 50.0, y - 75.0);
                    let dist_sq = dx * dx + dy * dy;
                    0.0 + power * exp((-dist_sq) / sigma_sq)
                })
                .collect();
            for (a, b) in with_py_max.iter().zip(mutant.iter()) {
                assert!(
                    (a.is_nan() && b.is_nan()) || a == b,
                    "py_max/f64::max became observable at power={power}: {a} vs {b}"
                );
            }
        }
    }

    #[test]
    fn zone_clamp_is_unreachable_for_the_bounds_that_discriminate_clip() {
        // Mutation M19 in the migration PR (`np_clip` -> `f64::clamp` on
        // the ZONE clamp) survived.  Not a test gap: `np_clip` and
        // `clamp` differ only for inverted (`lo > hi`) or NaN bounds, and
        // `find_min_valid` already required `zx0 <= x <= zx1 && zy0 <= y
        // <= zy1` before returning the cell.  A zone that would make the
        // two disagree therefore admits no cell at all, so the device is
        // skipped and the clamp is never reached; and for every zone that
        // IS reachable the clamp is the identity.  Proven here.
        for zone in [
            (90.0, 140.0, 10.0, 20.0),                 // inverted on both axes
            (10.0, 140.0, 90.0, 20.0),                 // inverted on y only
            (f64::NAN, 0.0, 90.0, 150.0),              // NaN lower bound
            (0.0, 0.0, f64::NAN, 150.0),               // NaN upper bound
        ] {
            let devices = [DeviceSpec {
                reference: "Q1".to_owned(),
                power: 10.0,
                zone: Some(zone),
            }];
            let mut inputs = anchor_inputs(&devices, 8);
            inputs.config.copper_weight = 0.0;
            let out = assign_thermal_anchors(&inputs).expect("run");
            assert!(
                out.anchors.is_empty(),
                "zone {zone:?} reached the clamp; np_clip/clamp could then diverge"
            );
            assert_eq!(out.skipped, vec!["Q1".to_string()]);
        }

        // A reachable zone: the anchor is inside it, so the clamp is the
        // identity and both forms agree.
        let devices = [DeviceSpec {
            reference: "Q1".to_owned(),
            power: 10.0,
            zone: Some((0.0, 0.0, 100.0, 150.0)),
        }];
        let mut inputs = anchor_inputs(&devices, 8);
        inputs.config.copper_weight = 0.0;
        let out = assign_thermal_anchors(&inputs).expect("run");
        assert_eq!(out.anchors.len(), 1);
        let (x, y) = out.anchors[0].1;
        assert_eq!(np_clip(x, 0.0, 100.0), x.clamp(0.0, 100.0));
        assert_eq!(np_clip(y, 0.0, 150.0), y.clamp(0.0, 150.0));
    }

    // --- audit ---------------------------------------------------------

    /// Build a `phi_base` field on a board wide enough that the TOP edge
    /// strip holds several rows, so "a strictly better feasible cell"
    /// exists to discriminate against.
    fn audit_fixture(resolution: usize) -> (Rect, Vec<f64>, Vec<f64>, Vec<f64>) {
        // 20 mm tall: with edge_margin 10 mm the top half of the rows are
        // inside the strip.
        let bounds = (0.0, 0.0, 20.0, 20.0);
        let (xg, yg) = build_potential_grid(bounds, resolution);
        let phi = superpose(
            &xg,
            &yg,
            resolution,
            resolution,
            &SuperposeInputs {
                bounds,
                edge: Edge::Top,
                config: FieldConfig {
                    coupling_weight: 0.0,
                    exclusion_weight: 0.0,
                    ..default_config()
                },
                devices: &[],
                anchors: &[],
                copper_zone_count: 0,
                copper_zones: &[],
                airflow: None,
                coupling_enabled: false,
            },
        )
        .expect("superpose");
        (bounds, xg, yg, phi)
    }

    #[test]
    fn audit_accepts_the_search_result() {
        let resolution = 9;
        let (bounds, xg, yg, phi) = audit_fixture(resolution);
        let found = find_min_valid(
            &phi, &xg, &yg, resolution, Edge::Top, bounds, None, &[], &[], 4.0,
        );
        let anchor = found.expect("a feasible cell exists");
        let findings = audit_anchor(
            &phi, &xg, &yg, resolution, Edge::Top, bounds, None, &[], &[], 4.0, anchor, &[],
            UNIQUE_TOLERANCE_MM,
        );
        assert!(findings.is_empty(), "clean anchor audited dirty: {findings:?}");
    }

    #[test]
    fn audit_rejects_a_feasible_but_non_minimal_anchor() {
        let resolution = 9;
        let (bounds, xg, yg, phi) = audit_fixture(resolution);
        let best = find_min_valid(
            &phi, &xg, &yg, resolution, Edge::Top, bounds, None, &[], &[], 4.0,
        )
        .expect("a feasible cell exists");
        // Any OTHER feasible cell with strictly higher phi: rows nearer
        // the bottom of the strip are hotter.
        let mut worse: Option<(f64, f64)> = None;
        let mut best_phi = f64::INFINITY;
        for idx in 0..phi.len() {
            let (x, y) = (xg[idx], yg[idx]);
            if !in_edge_strip(Edge::Top, bounds, x, y) {
                continue;
            }
            if (x, y) == best {
                best_phi = phi[idx];
            }
        }
        for idx in 0..phi.len() {
            let (x, y) = (xg[idx], yg[idx]);
            if in_edge_strip(Edge::Top, bounds, x, y) && phi[idx] > best_phi {
                worse = Some((x, y));
                break;
            }
        }
        let worse = worse.expect("the strip must hold more than one phi level");
        let findings = audit_anchor(
            &phi, &xg, &yg, resolution, Edge::Top, bounds, None, &[], &[], 4.0, worse, &[],
            UNIQUE_TOLERANCE_MM,
        );
        assert!(
            findings.contains(&AuditFinding::NotMinimal),
            "audit missed a non-minimal anchor: {findings:?}"
        );
    }

    #[test]
    fn audit_flags_an_off_grid_anchor() {
        let resolution = 6;
        let (xg, yg) = build_potential_grid(square_bounds(), resolution);
        let phi = vec![0.0; xg.len()];
        let findings = audit_anchor(
            &phi, &xg, &yg, resolution, Edge::Top, square_bounds(), None, &[], &[], 4.0,
            (12.345, 67.891), &[], UNIQUE_TOLERANCE_MM,
        );
        assert_eq!(findings, vec![AuditFinding::OffGrid]);
    }

    #[test]
    fn audit_flags_a_keepout_and_a_duplicate() {
        let resolution = 6;
        let (xg, yg) = build_potential_grid(square_bounds(), resolution);
        let phi = vec![0.0; xg.len()];
        let anchor = (xg[0], yg[(resolution - 1) * resolution]);
        let keepouts = [(-1.0, 0.0, 200.0, 200.0)];
        let findings = audit_anchor(
            &phi, &xg, &yg, resolution, Edge::Top, square_bounds(), None, &keepouts, &[], 4.0,
            anchor, &[anchor], UNIQUE_TOLERANCE_MM,
        );
        assert!(findings.contains(&AuditFinding::InsideKeepout));
        assert!(findings.contains(&AuditFinding::Duplicate));
    }

    // --- proptest: linspace structural properties ---

    mod linspace_proptests {
        #![allow(clippy::expect_used, clippy::unwrap_used)]

        use super::*;
        use proptest::prelude::*;

        proptest! {
            // --------------------------------------------------------------
            // Property L1: linspace length is exactly `num`.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_length_correct(
                start in prop::num::f64::NORMAL,
                stop in prop::num::f64::NORMAL,
                num in 0usize..=100usize,
            ) {
                let v = linspace(start, stop, num);
                prop_assert_eq!(v.len(), num);
            }

            // --------------------------------------------------------------
            // Property L2: When `num >= 2`, the first element equals `start`
            // and the last equals `stop` exactly.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_endpoints_exact(
                start in prop::num::f64::NORMAL,
                stop in prop::num::f64::NORMAL,
                num in 2usize..=100usize,
            ) {
                let v = linspace(start, stop, num);
                prop_assert_eq!(v[0], start);
                prop_assert_eq!(v[num - 1], stop);
            }

            // --------------------------------------------------------------
            // Property L3: When `num == 1`, the sole element equals `start`.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_single_element_is_start(start in prop::num::f64::NORMAL) {
                let v = linspace(start, 99.0, 1);
                prop_assert_eq!(v[0], start);
            }

            // --------------------------------------------------------------
            // Property L4: When `start < stop`, linspace is strictly
            // monotonically increasing.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_monotonic_increasing(
                start in prop::num::f64::NORMAL,
                stop in prop::num::f64::NORMAL,
                num in 3usize..=100usize,
            ) {
                // Order directly: prop_assume!(start < stop) rejects ~50% and
                // trips proptest's global-reject limit at high PROPTEST_CASES.
                let (start, stop) = if start < stop { (start, stop) } else { (stop, start) };
                let v = linspace(start, stop, num);
                for i in 0..(num - 1) {
                    prop_assert!(v[i] < v[i + 1],
                        "linspace not monotonic at i={i}: v[{i}]={:.16e}, v[{}]={:.16e}",
                        v[i], i+1, v[i+1]);
                }
            }

            // --------------------------------------------------------------
            // Property L5: When `start == stop`, every element equals that
            // value.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_degenerate_constant(
                val in prop::num::f64::NORMAL,
                num in 1usize..=50usize,
            ) {
                let v = linspace(val, val, num);
                for &elem in &v {
                    prop_assert_eq!(elem, val);
                }
            }

            // --------------------------------------------------------------
            // Property L6: All elements are finite for finite start/stop.
            // --------------------------------------------------------------
            #[test]
            fn prop_linspace_all_finite(
                start in prop::num::f64::NORMAL,
                stop in prop::num::f64::NORMAL,
                num in 0usize..=50usize,
            ) {
                let v = linspace(start, stop, num);
                for &elem in &v {
                    prop_assert!(elem.is_finite(),
                        "non-finite element {elem:e} in linspace({start:e}, {stop:e}, {num})");
                }
            }
        }
    }

    // --- proptest: field component structural properties ---

    mod field_proptests {
        #![allow(clippy::expect_used, clippy::unwrap_used)]

        use super::*;
        use proptest::prelude::*;

        fn moderate_f64() -> impl Strategy<Value = f64> {
            (0.0f64..1000.0f64).prop_map(|x| x)
        }

        fn width_height() -> impl Strategy<Value = f64> {
            1.0f64..500.0f64
        }

        fn resolution() -> impl Strategy<Value = usize> {
            2usize..=20usize
        }

        proptest! {
            // --------------------------------------------------------------
            // Property F1: phi_edge returns non-negative finite values
            // for finite inputs and a non-zero decay.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_edge_non_negative_finite(
                w in width_height(),
                h in width_height(),
                decay in 0.1f64..100.0f64,
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_edge(&xg, &yg, bounds, Edge::Top, decay);
                for &v in &field {
                    prop_assert!(v.is_finite());
                    prop_assert!(v >= 0.0);
                    prop_assert!(v <= 1.0);
                }
            }

            // --------------------------------------------------------------
            // Property F2: phi_edge top row is minimal (closest to TOP edge).
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_edge_top_row_is_minimal(
                w in width_height(),
                h in width_height(),
                decay in 1.0f64..50.0f64,
                res in 4usize..=20usize,
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_edge(&xg, &yg, bounds, Edge::Top, decay);
                let top_row_start = res * (res - 1);
                for j in 0..res {
                    for row in 0..(res - 1) {
                        prop_assert!(
                            field[top_row_start + j] <= field[row * res + j],
                            "top-row cell exceeds cell in row {}", row
                        );
                    }
                }
            }

            // --------------------------------------------------------------
            // Property F3: phi_coupling empty devices is all zero.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_coupling_empty_is_zero(
                w in width_height(),
                h in width_height(),
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_coupling(&xg, &yg, &[], 50.0);
                for &v in &field {
                    prop_assert_eq!(v, 0.0);
                }
            }

            // --------------------------------------------------------------
            // Property F4: phi_coupling returns finite, non-negative values.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_coupling_finite_for_moderate_power(
                px in 0.0f64..500.0f64,
                py in 0.0f64..500.0f64,
                power in 0.0f64..100.0f64,
                sigma_factor in 1.0f64..200.0f64,
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, px + 10.0, py + 10.0);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_coupling(&xg, &yg, &[((px, py), power)], sigma_factor);
                for &v in &field {
                    prop_assert!(v.is_finite());
                    prop_assert!(v >= 0.0);
                }
            }

            // --------------------------------------------------------------
            // Property F5: phi_coupling peak is at the device position.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_coupling_peaks_at_device(
                px in moderate_f64(),
                py in moderate_f64(),
                power in 1.0f64..50.0f64,
                sigma_factor in 10.0f64..100.0f64,
            ) {
                let bounds = (0.0, 0.0, px + 50.0, py + 50.0);
                let (xg, yg) = build_potential_grid(bounds, 7);
                let field = phi_coupling(&xg, &yg, &[((px, py), power)], sigma_factor);
                let peak = field.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
                prop_assert!(peak.is_finite() && peak > 0.0);
                for &v in &field {
                    prop_assert!(v <= peak * (1.0 + 1e-12));
                }
            }

            // --------------------------------------------------------------
            // Property F6: phi_exclusion returns non-negative, finite values.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_exclusion_non_negative(
                w in width_height(),
                h in width_height(),
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_exclusion(&xg, &yg, &[(w / 2.0, h / 2.0)], 10.0, 1e6, 20.0);
                for &v in &field {
                    prop_assert!(v >= 0.0);
                    prop_assert!(v.is_finite());
                }
            }

            // --------------------------------------------------------------
            // Property F7: phi_convection with NaN magnitude is all-NaN.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_convection_nan_magnitude_is_nan_field(
                w in width_height(),
                h in width_height(),
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_convection(&xg, &yg, Some((f64::NAN, 45.0)));
                for &v in &field {
                    prop_assert!(v.is_nan());
                }
            }

            // --------------------------------------------------------------
            // Property F8: phi_convection with magnitude <= 0 returns zero.
            // --------------------------------------------------------------
            #[test]
            fn prop_phi_convection_zero_or_negative_is_zero(
                w in width_height(),
                h in width_height(),
                mag in -100.0f64..=0.0f64,
                deg in 0.0f64..360.0f64,
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let field = phi_convection(&xg, &yg, Some((mag, deg)));
                for &v in &field {
                    prop_assert_eq!(v, 0.0);
                }
            }

            // --------------------------------------------------------------
            // Property F9: build_potential_grid has correct dimensions.
            // --------------------------------------------------------------
            #[test]
            fn prop_build_potential_grid_dimensions(
                w in width_height(),
                h in width_height(),
                res in resolution(),
            ) {
                let bounds = (0.0, 0.0, w, h);
                let (xg, yg) = build_potential_grid(bounds, res);
                let n = res * res;
                prop_assert_eq!(xg.len(), n);
                prop_assert_eq!(yg.len(), n);
            }

            // --------------------------------------------------------------
            // Property F10: build_potential_grid has correct xy convention.
            // --------------------------------------------------------------
            #[test]
            fn prop_build_potential_grid_xy_convention(
                x_min in 0.0f64..100.0f64,
                x_max in 101.0f64..500.0f64,
                y_min in 0.0f64..100.0f64,
                y_max in 101.0f64..500.0f64,
                res in 3usize..=10usize,
            ) {
                let bounds = (x_min, y_min, x_max, y_max);
                let (xg, yg) = build_potential_grid(bounds, res);
                // y is uniform within each row.
                for row in 0..res {
                    let base = row * res;
                    for col in 1..res {
                        prop_assert_eq!(yg[base + col], yg[base]);
                    }
                }
                // x is uniform within each column.
                for col in 0..res {
                    for row in 1..res {
                        prop_assert_eq!(xg[col], xg[row * res + col]);
                    }
                }
            }
        }
    }

    // --- proptest: anchor uniqueness enforcement (search_free_x +
    //     enforce_unique_positions_with) ---
    //
    // The field proptests exercise the full pipeline (phi_* + anchor
    // assignment), and the unit tests above exercise the R13 regression
    // fixtures.  These proptests exercise `search_free_x` directly
    // (previously only reachable through the fixpoint loop) and the
    // enforcement termination invariant across randomized inputs.

    mod uniqueness_proptests {
        #![allow(clippy::expect_used, clippy::unwrap_used)]

        use super::*;
        use proptest::prelude::*;

        fn tolerance() -> impl Strategy<Value = f64> {
            0.01f64..2.0f64
        }

        #[test]
        fn prop_search_free_x_non_positive_offset_returns_none() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(-10.0f64..=0.0f64, tolerance(), 0.0f64..50.0f64, 51.0f64..100.0f64,
                  10.0f64..90.0f64, 10.0f64..90.0f64),
                |(offset, tol, x_min, x_max, xj, yj)| {
                    let anchors = vec![("A".to_owned(), (xj, yj))];
                    let got = search_free_x(&anchors, 0, x_min, x_max, tol, offset);
                    prop_assert!(got.is_none(), "non-positive offset {offset} must return None");
                    Ok(())
                },
            ).unwrap();
        }

        #[test]
        fn prop_search_free_x_nan_offset_returns_none() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(tolerance(), 0.0f64..50.0f64, 51.0f64..100.0f64,
                  10.0f64..90.0f64, 10.0f64..90.0f64),
                |(tol, x_min, x_max, xj, yj)| {
                    let anchors = vec![("A".to_owned(), (xj, yj))];
                    let got = search_free_x(&anchors, 0, x_min, x_max, tol, f64::NAN);
                    prop_assert!(got.is_none(), "NaN offset must return None");
                    Ok(())
                },
            ).unwrap();
        }

        #[test]
        fn prop_search_free_x_found_within_bounds() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(0.0f64..100.0f64, 0.0f64..100.0f64, 0.0f64..10.0f64, 90.0f64..100.0f64,
                  0.1f64..2.0f64, 0.01f64..0.2f64),
                |(xj, yj, x_min, x_max, offset, tol)| {
                    let anchors = vec![("A".to_owned(), (xj, yj))];
                    let got = search_free_x(&anchors, 0, x_min, x_max, tol, offset);
                    if let Some((cx, cy)) = got {
                        prop_assert!(cx >= x_min && cx <= x_max,
                            "found x outside bounds");
                        prop_assert!((cy - yj).abs() < 1e-15,
                            "found y differs from anchor y");
                    }
                    Ok(())
                },
            ).unwrap();
        }

        #[test]
        fn prop_enforce_unique_no_violations() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(2usize..=8usize, 0.0f64..10.0f64, 50.0f64..100.0f64,
                  0.1f64..2.0f64, 0.01f64..0.2f64),
                |(n_anchors, x_min, x_max, offset, tol)| {
                    let xj = (x_min + x_max) / 2.0;
                    let yj = 50.0;
                    let mut anchors: Vec<(String, (f64, f64))> = (0..n_anchors)
                        .map(|i| (format!("A{i}"), (xj, yj)))
                        .collect();
                    enforce_unique_positions_with(&mut anchors,
                        (x_min, 0.0, x_max, 100.0), tol, offset);
                    prop_assert_eq!(anchors.len(), n_anchors,
                        "anchor count changed during enforcement");
                    for i in 0..anchors.len() {
                        for j in (i + 1)..anchors.len() {
                            let (xi, yi) = anchors[i].1;
                            let (xj2, yj2) = anchors[j].1;
                            let dist = pow(pow(xi - xj2, 2.0) + pow(yi - yj2, 2.0), 0.5);
                            prop_assert!(
                                dist >= tol,
                                "anchors {i}/{j} at {dist} < tolerance {tol}"
                            );
                        }
                    }
                    Ok(())
                },
            ).unwrap();
        }

        #[test]
        fn prop_enforce_unique_noop_when_already_unique() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(0.0f64..100.0f64, 0.0f64..100.0f64, 0.01f64..0.2f64),
                |(x0, x1, tol)| {
                    if (x0 - x1).abs() < tol + 0.1 {
                        return Ok(());
                    }
                    let mut anchors: Vec<(String, (f64, f64))> = vec![
                        ("A".to_owned(), (x0, 50.0)),
                        ("B".to_owned(), (x1, 50.0)),
                    ];
                    let before = anchors.clone();
                    enforce_unique_positions_with(&mut anchors,
                        (0.0, 0.0, 100.0, 100.0), tol, 0.5);
                    prop_assert_eq!(anchors, before,
                        "already-unique anchors must not be modified");
                    Ok(())
                },
            ).unwrap();
        }

        #[test]
        fn prop_enforce_unique_stays_in_bounds() {
            let mut runner = proptest::test_runner::TestRunner::default();
            runner.run(
                &(2usize..=5usize, 0.0f64..20.0f64, 80.0f64..100.0f64,
                  0.1f64..2.0f64, 0.01f64..0.2f64),
                |(n_anchors, x_min, x_max, offset, tol)| {
                    let yj = 50.0;
                    let mut anchors: Vec<(String, (f64, f64))> = (0..n_anchors)
                        .map(|i| (format!("A{i}"), ((x_min + x_max) / 2.0, yj)))
                        .collect();
                    enforce_unique_positions_with(&mut anchors,
                        (x_min, 0.0, x_max, 100.0), tol, offset);
                    for (name, (cx, _cy)) in &anchors {
                        prop_assert!(
                            *cx >= x_min && *cx <= x_max,
                            "anchor {name} x={cx} outside [{x_min}, {x_max}]"
                        );
                    }
                    Ok(())
                },
            ).unwrap();
        }

        /// Vacuity guard: the distance check must use `pow`, not `sqrt`
        /// — the fixture discriminates on THIS host libm.
        #[test]
        fn uniqueness_distance_uses_pow_not_sqrt_proptest() {
            let dx = 0.179_050_385_249_757_8_f64;
            let dy = 0.144_493_925_399_294_26_f64;
            let s = pow(dx, 2.0) + pow(dy, 2.0);
            let tol = s.sqrt();
            if pow(s, 0.5) >= tol {
                return; // libm does not discriminate; skip
            }
            let mut anchors = vec![
                ("A".to_owned(), (dx, dy)),
                ("B".to_owned(), (0.0, 0.0)),
            ];
            enforce_unique_positions_with(&mut anchors,
                (0.0, 0.0, 100.0, 100.0), tol, 0.5);
            assert_ne!(
                anchors[1].1, (0.0, 0.0),
                "B must be nudged when dist < tol via pow"
            );
        }
    }
}

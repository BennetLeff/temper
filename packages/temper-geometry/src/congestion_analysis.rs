//! Wave-4 Phase B: the `router_v6` congestion cluster in Rust, continued.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_congestion_py_oracle.py`
//! (`congestion.analyze_congestion` and `congestion_analysis`'s
//! `identify_congested_regions` / `_classify_congestion`).
//!
//! # Scope
//!
//! `congestion_analyze_py`, `congestion_identify_regions_py` and
//! `congestion_classify_severity_py`. This module is the sibling of
//! `congestion.rs` (slices 1-3 of the cluster: `CongestionGrid`,
//! `Bottleneck`/`CongestionResult`, `estimate_net_demand`) -- separated only
//! because Phase B splits the cluster's twenty-two symbols across parallel
//! kernels, not because the semantics differ.
//!
//! `congestion_analyze_py`'s test call
//! (`test_analyze_congestion_bit_exact`) never passes `positions=` or
//! `layer_assignments=` -- the differential's adapter binds it as
//! `fn(components, nets, board, cell, capacity, layers)`, six positional
//! arguments, matching `ANALYZE_DESIGNS`'s dict shape exactly. Those two
//! optional oracle parameters are therefore not part of this kernel's
//! contract: every call in the corpus behaves as `positions=None,
//! layer_assignments=None`, which collapses `_get_pin_positions`'s
//! `pos_override` to always-`None` (component's own `initial_position`
//! wins) and pins every net's `layer` to `0`. D1's `positions=` override and
//! D2's `layer_assignments=` promotion are exercised by
//! `test_repaired_d1_positions_argument_is_honoured` and
//! `test_repaired_d2_layer_assignments_path_is_reachable` directly against
//! the oracle (ast + behavioural), never through a Rust symbol -- see the
//! oracle header and the differential's own docstring.
//!
//! # Host libm, not Rust intrinsics, for the rotation trig
//!
//! `analyze_congestion` -> `_get_pin_positions` -> `pin_world_position_at`
//! -> `geometry.kicad_transform.rotate_local_to_world` calls `math.cos`
//! and `math.sin` -- the *host* Python runtime's libm, which
//! `escape_via.rs`'s module doc measured up to 1 ulp away from a statically
//! bound `f64::cos`/`f64::sin` on the uv standalone build (B1). The
//! `rotated_components` corpus row exercises a non-zero rotation, so this
//! kernel resolves the same two calls through [`crate::host_math`] rather
//! than reaching for `crate::transform::transform_pin_position` (which uses
//! the `f64` intrinsics and would reintroduce exactly that ulp gap).
//!
//! # Everything else delegates to numpy
//!
//! `CongestionGrid.get_overflow`/`get_utilization` are `np.maximum`/`np.sum`
//! calls (B12, B7 -- see `congestion.rs`'s module doc for the measurements);
//! this kernel builds `demand`/`supply` as real numpy arrays via
//! `np.zeros`/`np.full` and mutates `demand` in place through the same
//! slice-`get_item`/`add`/`set_item` sequence `congestion_estimate_net_demand_py`
//! uses, so the two arms start from, and stay, bit-identical objects.
//!
//! `identify_congested_regions` iterates a Python `dict` of compiled routes
//! (`routing_results.compiled_routes.items()`), and the corpus's
//! `multi_net_same_cell` row exists specifically because repeated `+= 0.1`
//! into the same grid cell across multiple nets is order-sensitive
//! (floating-point addition is not associative). The `routes` parameter is
//! therefore accepted as a `Bound<'py, PyDict>` and walked with
//! `PyDictMethods::iter`, which preserves Python's insertion-order
//! iteration, rather than collected into a `HashMap` first.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyDictMethods};

use crate::congestion::{ceil_to_int, cpython_max, cpython_min, cpython_min2, int_trunc};
use crate::kicad_transform::rotate_local_to_world;

// `rotate_local_to_world` (KiCad R(-theta) footprint-child rotation,
// `geometry.kicad_transform.rotate_local_to_world`) consolidated onto the
// crate's single sanctioned implementation in `kicad_transform.rs`: this
// file's former private copy used `host_math::cos`/`host_math::sin`
// directly, the SSOT uses `pad_geometry::math_cos_sin`, which itself
// resolves through the same dlsym'd host libm (`host_cos()`/`host_sin()`)
// -- bit-identical, behavior-preserving.

/// `core.pin_geometry._normalize_rotation`'s integer-index branch.
///
/// `Component.initial_rotation` is a rotation *index* (0-3 -> 0/90/180/270
/// deg); `None` is "no rotation".
fn normalize_rotation(rotation: Option<i64>) -> f64 {
    match rotation {
        None => 0.0,
        Some(r) => (r as f64) * std::f64::consts::PI / 2.0,
    }
}

/// `core.pin_geometry.pin_world_position_at`, with `pos_override=None` and
/// `rotation_override=None` always (this kernel's contract -- see module doc).
///
/// This previously omitted the bottom-side X mirror, justified by "the
/// corpus's component tuples carry no `initial_side`, so `side` is always its
/// default `0`". That was a property of the FIXTURES, not of the domain --
/// the same reasoning produced defects in escape_via.rs and net_ordering.rs,
/// both fixed 2026-08-06. Real boards carry back-side components, and the
/// shipped `pin_world_position_at` mirrors X BEFORE rotation for them.
fn pin_world_position(
    pin_offset: (f64, f64),
    comp_position: Option<(f64, f64)>,
    comp_rotation: Option<i64>,
    comp_side: Option<i64>,
) -> (f64, f64) {
    let rotation_rad = normalize_rotation(comp_rotation);
    let (mut px, py) = pin_offset;
    // `side = comp.initial_side or 0`; mirror BEFORE rotation. Order matters:
    // mirroring afterwards gives a different point for any non-zero rotation.
    if comp_side.unwrap_or(0) == 1 {
        px = -px;
    }
    let (rx, ry) = rotate_local_to_world(px, py, rotation_rad);
    // `comp.initial_position or (0.0, 0.0)` -- only `None` falls back; a
    // `(0.0, 0.0)` tuple is itself truthy.
    let cpos = comp_position.unwrap_or((0.0, 0.0));
    (cpos.0 + rx, cpos.1 + ry)
}

/// One `components` row: `(ref, initial_position, initial_rotation,
/// [(pin_number, (px, py), net), ...])` -- `_congestion_builders.build_netlist`'s
/// tuple shape.
type ComponentRow = (String, Option<(f64, f64)>, Option<i64>, Vec<(String, (f64, f64), String)>);

/// One `nets` row: `(name, [(comp_ref, pin_name), ...])`.
type NetRow = (String, Vec<(String, String)>);

/// One `CongestedRegion`, flattened to the tuple the differential projects:
/// `(center, radius, severity, failed_net_count, bottleneck_score)`.
type RegionRow = ((f64, f64), f64, String, i64, f64);

/// `congestion._get_pin_positions`, restricted to this kernel's contract
/// (`positions=None` always, so `pos_override` is always `None`).
///
/// Mirrors the reference's own re-lookup-by-name inside the helper (rather
/// than reusing the caller's loop variable), which matters only if `nets`
/// ever carries a duplicate name -- not exercised by the corpus, kept for
/// fidelity to the pinned source.
fn get_pin_positions(
    components: &[ComponentRow],
    sides: &[Option<i64>],
    comp_by_ref: &std::collections::HashMap<&str, usize>,
    nets: &[NetRow],
    net_name: &str,
) -> Vec<(f64, f64)> {
    let mut pin_positions = Vec::new();
    let Some((_, net_pins)) = nets.iter().find(|(n, _)| n == net_name) else {
        return pin_positions;
    };
    for (comp_ref, pin_name) in net_pins {
        let Some(&idx) = comp_by_ref.get(comp_ref.as_str()) else {
            continue;
        };
        let (_, position, rotation, pins) = &components[idx];
        let side = sides.get(idx).copied().flatten();
        // `pin.name == pin_name or pin.number == pin_name` -- the builder
        // sets `name = number = pin_number`, so a single equality check on
        // the stored pin number covers both.
        if let Some((_, offset, _net)) = pins.iter().find(|(num, _, _)| num == pin_name) {
            pin_positions.push(pin_world_position(*offset, *position, *rotation, side));
        }
    }
    pin_positions
}

/// `congestion.analyze_congestion`, restricted to this kernel's contract:
/// `positions=None`, `layer_assignments=None` always (see module doc).
///
/// Returns the 5-tuple the differential projects: `(demand, supply,
/// total_overflow, max_utilization, bottlenecks)`, where each bottleneck is
/// `(x, y, utilization, overflow, layer)`.
#[pyfunction]
#[pyo3(signature = (components_any, nets, board, cell_size_mm, capacity_per_cell, num_layers))]
pub fn congestion_analyze_py<'py>(
    py: Python<'py>,
    components_any: &Bound<'py, PyAny>,
    nets: Vec<NetRow>,
    board: (f64, f64),
    cell_size_mm: f64,
    capacity_per_cell: f64,
    num_layers: i64,
) -> PyResult<Bound<'py, PyAny>> {
    // Parse element-wise rather than as a fixed-arity tuple: pyo3 tuple
    // extraction demands EXACT arity, so a `Vec<ComponentRow>` of 5-tuples
    // would reject every pre-existing 4-tuple corpus row. The optional 5th
    // element is `initial_side`.
    let mut components: Vec<ComponentRow> = Vec::new();
    let mut sides: Vec<Option<i64>> = Vec::new();
    for row in components_any.try_iter()? {
        let row = row?;
        components.push((
            row.get_item(0)?.extract()?,
            row.get_item(1)?.extract()?,
            row.get_item(2)?.extract()?,
            row.get_item(3)?.extract()?,
        ));
        sides.push(match row.get_item(4) {
            Ok(v) => v.extract().ok(),
            Err(_) => None,
        });
    }

    let (board_width, board_height) = board;
    let width_cells = ceil_to_int(board_width / cell_size_mm)?;
    let height_cells = ceil_to_int(board_height / cell_size_mm)?;

    let np = py.import("numpy")?;
    let (demand, supply) = if num_layers == 1 {
        let shape = (height_cells, width_cells);
        (
            np.call_method1("zeros", (shape,))?,
            np.call_method1("full", (shape, capacity_per_cell))?,
        )
    } else {
        let shape = (num_layers, height_cells, width_cells);
        (
            np.call_method1("zeros", (shape,))?,
            np.call_method1("full", (shape, capacity_per_cell))?,
        )
    };

    // `comp_by_ref = {c.ref: (i, c) for i, c in enumerate(netlist.components)}`
    // -- a later duplicate ref overwrites an earlier one, matching a dict
    // comprehension's own last-write-wins semantics.
    let mut comp_by_ref: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    for (i, c) in components.iter().enumerate() {
        comp_by_ref.insert(c.0.as_str(), i);
    }

    let py_slice = py.import("builtins")?.getattr("slice")?;

    for (net_name, _net_pins) in &nets {
        let pin_positions =
            get_pin_positions(&components, &sides, &comp_by_ref, &nets, net_name);
        if pin_positions.len() < 2 {
            continue;
        }

        // `estimate_net_demand`, `layer=0` always (no `layer_assignments`).
        let xs: Vec<f64> = pin_positions.iter().map(|p| p.0).collect();
        let ys: Vec<f64> = pin_positions.iter().map(|p| p.1).collect();
        let (min_x, max_x) = (cpython_min(&xs), cpython_max(&xs));
        let (min_y, max_y) = (cpython_min(&ys), cpython_max(&ys));

        // `grid.origin` is always `(0.0, 0.0)` here -- `Board`'s own default,
        // and `design["board"]` in the corpus is always a bare (width,
        // height) 2-tuple, never overriding it.
        let col_min = 0i64.max(int_trunc(min_x / cell_size_mm)?);
        let col_max = (width_cells - 1).min(int_trunc(max_x / cell_size_mm)?);
        let row_min = 0i64.max(int_trunc(min_y / cell_size_mm)?);
        let row_max = (height_cells - 1).min(int_trunc(max_y / cell_size_mm)?);

        // D3's repaired guard: BOTH pairs, not one side (see `congestion.rs`).
        if col_max < col_min || row_max < row_min {
            continue;
        }

        let rows = py_slice.call1((row_min, row_max + 1))?;
        let cols = py_slice.call1((col_min, col_max + 1))?;
        let current = if num_layers == 1 {
            demand.get_item((&rows, &cols))?
        } else {
            demand.get_item((0i64, &rows, &cols))?
        };
        let updated = current.add(1.0f64)?;
        if num_layers == 1 {
            demand.set_item((&rows, &cols), updated)?;
        } else {
            demand.set_item((0i64, &rows, &cols), updated)?;
        }
    }

    // `grid.get_overflow()` / `grid.get_utilization()` -- `np.maximum`
    // propagates NaN from either operand (B12); see `congestion.rs`.
    let diff = demand.sub(&supply)?;
    let overflow = np.call_method1("maximum", (diff, 0.0f64))?;
    let floored_supply = np.call_method1("maximum", (&supply, 1e-6f64))?;
    let utilization = demand.div(floored_supply)?;

    let builtins = py.import("builtins")?;
    let max_utilization: f64 = builtins
        .call_method1("float", (utilization.call_method0("max")?,))?
        .extract()?;
    let total_overflow: f64 = builtins
        .call_method1("float", (overflow.call_method0("sum")?,))?
        .extract()?;

    // Bottlenecks: `np.where(overflow > 0)` iterates row-major (C order),
    // which a `demand`/`supply` array built by `np.zeros`/`np.full` always
    // is, so a plain nested loop over the extracted values reproduces its
    // enumeration order exactly.
    let mut bottlenecks: Vec<(i64, i64, f64, f64, i64)> = Vec::new();
    if num_layers == 1 {
        let overflow_rows: Vec<Vec<f64>> = overflow.call_method0("tolist")?.extract()?;
        let util_rows: Vec<Vec<f64>> = utilization.call_method0("tolist")?.extract()?;
        for (r, (ov_row, ut_row)) in overflow_rows.iter().zip(util_rows.iter()).enumerate() {
            for (c, (&ov, &ut)) in ov_row.iter().zip(ut_row.iter()).enumerate() {
                if ov > 0.0 {
                    bottlenecks.push((c as i64, r as i64, ut, ov, 0));
                }
            }
        }
    } else {
        let overflow_layers: Vec<Vec<Vec<f64>>> = overflow.call_method0("tolist")?.extract()?;
        let util_layers: Vec<Vec<Vec<f64>>> = utilization.call_method0("tolist")?.extract()?;
        for (layer_idx, (ov_layer, ut_layer)) in
            overflow_layers.iter().zip(util_layers.iter()).enumerate()
        {
            for (r, (ov_row, ut_row)) in ov_layer.iter().zip(ut_layer.iter()).enumerate() {
                for (c, (&ov, &ut)) in ov_row.iter().zip(ut_row.iter()).enumerate() {
                    if ov > 0.0 {
                        bottlenecks.push((c as i64, r as i64, ut, ov, layer_idx as i64));
                    }
                }
            }
        }
    }

    let out = (demand, supply, total_overflow, max_utilization, bottlenecks);
    Ok(out.into_pyobject(py)?.into_any())
}

/// `congestion_analysis._classify_congestion`, returning the enum's
/// `.value` string directly (`"none"`/`"low"`/`"medium"`/`"high"`/`"critical"`).
fn classify_congestion(congestion_score: f64, failed_net_count: i64) -> String {
    if failed_net_count >= 3 {
        return "critical".to_string();
    }
    if failed_net_count >= 1 {
        return "high".to_string();
    }
    // Every `>` compares false against NaN, matching CPython's float
    // comparison exactly, so a NaN `congestion_score` falls through to
    // `"none"` with no special-casing needed.
    if congestion_score > 5.0 {
        "high".to_string()
    } else if congestion_score > 3.0 {
        "medium".to_string()
    } else if congestion_score > 1.0 {
        "low".to_string()
    } else {
        "none".to_string()
    }
}

#[pyfunction]
pub fn congestion_classify_severity_py(congestion_score: f64, failed_net_count: i64) -> String {
    classify_congestion(congestion_score, failed_net_count)
}

/// `congestion_analysis.identify_congested_regions`.
///
/// `_use_segments` is accepted to match the differential's call arity but
/// not read: `RouteStub` builds either `path.segments` (3-tuples, sliced to
/// `[:2]`) or `path.coordinates` (2-tuples) from the *same* coordinate list,
/// so both of the oracle's `hasattr` branches yield identical `(x, y)`
/// pairs and this kernel receives `routes` already reduced to that shape.
///
/// `routes` is a `dict`, walked in insertion order (`PyDictMethods::iter`)
/// rather than collected into a `HashMap` first -- seed
/// `multi_net_same_cell`. Repeated `+= 0.1` into the same grid cell across
/// several nets is order-sensitive under floating point, and only dict
/// order preserves the reference's accumulation order.
#[pyfunction]
#[pyo3(signature = (failed_nets, routes, board_width, board_height, grid_size, _use_segments))]
#[allow(clippy::too_many_arguments)]
pub fn congestion_identify_regions_py(
    failed_nets: Vec<String>,
    routes: Bound<'_, PyDict>,
    board_width: f64,
    board_height: f64,
    grid_size: f64,
    _use_segments: bool,
) -> PyResult<Vec<RegionRow>> {
    let grid_cells_x = int_trunc(board_width / grid_size)? + 1;
    let grid_cells_y = int_trunc(board_height / grid_size)? + 1;

    // The corpus never drives `grid_cells_x`/`grid_cells_y` non-positive
    // (`board_width`/`board_height`/`grid_size` are always positive), so
    // this guard is defensive rather than a modelled Python behaviour: it
    // avoids an invalid Vec allocation size rather than reproducing
    // CPython's `[x] * negative == []` list-repeat semantics, which the
    // differential does not exercise.
    if grid_cells_x <= 0 || grid_cells_y <= 0 {
        return Ok(Vec::new());
    }
    let (gx, gy) = (grid_cells_x as usize, grid_cells_y as usize);

    let mut congestion_grid = vec![vec![0.0f64; gx]; gy];
    let mut failed_net_grid = vec![vec![0i64; gx]; gy];

    // Failed nets: "simplified: assume center of board" -- every failed net
    // contributes to the SAME cell, `failed_nets.len()` times. Processed
    // BEFORE route density: the reference's own statement order, and load-
    // bearing -- `+= 0.5` then `+= 0.1` x N is not bit-identical to the
    // reverse for the same set of additions (floating-point addition is not
    // associative across different-magnitude terms; measured on
    // `failed_and_dense`, see this function's own mutation notes).
    let cx = int_trunc(board_width / 2.0 / grid_size)?;
    let cy = int_trunc(board_height / 2.0 / grid_size)?;
    if cx >= 0 && cx < grid_cells_x && cy >= 0 && cy < grid_cells_y {
        let (cxu, cyu) = (cx as usize, cy as usize);
        for _failed_net in &failed_nets {
            failed_net_grid[cyu][cxu] += 1;
            congestion_grid[cyu][cxu] += 0.5;
        }
    }

    // Route density -- dict insertion order, see module/function doc.
    for (key, value) in routes.iter() {
        let _net_name: String = key.extract()?;
        let coords: Vec<(f64, f64)> = value.extract()?;
        for (x, y) in coords {
            let cell_x = int_trunc(x / grid_size)?;
            let cell_y = int_trunc(y / grid_size)?;
            if cell_x >= 0 && cell_x < grid_cells_x && cell_y >= 0 && cell_y < grid_cells_y {
                congestion_grid[cell_y as usize][cell_x as usize] += 0.1;
            }
        }
    }

    let mut regions = Vec::new();
    for (y, (cong_row, failed_row)) in congestion_grid.iter().zip(failed_net_grid.iter()).enumerate() {
        for (x, (&congestion, &failed)) in cong_row.iter().zip(failed_row.iter()).enumerate() {
            if congestion > 0.5 || failed > 0 {
                let severity = classify_congestion(congestion, failed);
                let center_x = (x as f64 + 0.5) * grid_size;
                let center_y = (y as f64 + 0.5) * grid_size;
                // `min(1.0, congestion / 10.0)` -- NaN is the SECOND
                // argument here, opposite of `overflow_ratio` (B5); see
                // `congestion.rs::cpython_min2`.
                let score = cpython_min2(1.0, congestion / 10.0);
                regions.push(((center_x, center_y), grid_size / 2.0, severity, failed, score));
            }
        }
    }

    Ok(regions)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(congestion_analyze_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_identify_regions_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_classify_severity_py, m)?)?;
    Ok(())
}

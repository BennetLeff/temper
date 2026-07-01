// temper-constraints: Rust PCL constraint engine.
//
// Exposes constraint type enums and loss computation functions
// via PyO3 bindings.  All functions catch panics via
// std::panic::catch_unwind and convert to Python RuntimeError (R14).
//
// R4: Constraint types as Rust enums with exhaustive match
// R5: Loss functions exposed as callable Python functions
// R9: Integration test proves Rust backend is wired
// R14: Never abort Python process; catch_unwind + Python exceptions

pub mod constraints;
pub mod loss;

use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyList;
use std::panic::{self};

use crate::constraints::*;
use crate::loss::*;

fn catch_unwind_f64(
    f: impl FnOnce() -> PyResult<f64>,
) -> PyResult<f64> {
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(panic_info) => {
            let msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic in Rust constraint engine".to_string()
            };
            Err(PyRuntimeError::new_err(format!("temper_constraints panic: {msg}")))
        }
    }
}

// Tier-to-weight mapping (exposed for Python fallback parity)
#[pyfunction]
fn tier_to_weight_py(_py: Python<'_>, tier: u8) -> PyResult<f64> {
    let t = ConstraintTier::from_int(tier).map_err(|e| PyValueError::new_err(e))?;
    Ok(tier_to_weight(&t))
}

// Adjacent loss
#[pyfunction]
#[pyo3(signature = (positions, idx_a, idx_b, max_distance_mm, weight, metric = "center_to_center", pin_a_x = None, pin_a_y = None, pin_b_x = None, pin_b_y = None))]
fn compute_adjacent_loss_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    idx_a: usize,
    idx_b: usize,
    max_distance_mm: f64,
    weight: f64,
    metric: &str,
    pin_a_x: Option<f64>,
    pin_a_y: Option<f64>,
    pin_b_x: Option<f64>,
    pin_b_y: Option<f64>,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        let m = match metric {
            "edge_to_edge" => DistanceMetric::EdgeToEdge,
            "center_to_center" => DistanceMetric::CenterToCenter,
            "pin_to_pin" => DistanceMetric::PinToPin,
            _ => return Err(PyValueError::new_err(format!("Unknown metric: {metric}"))),
        };
        let pin_a = match (pin_a_x, pin_a_y) {
            (Some(x), Some(y)) => Some((x, y)),
            _ => None,
        };
        let pin_b = match (pin_b_x, pin_b_y) {
            (Some(x), Some(y)) => Some((x, y)),
            _ => None,
        };
        Ok(compute_adjacent_loss(&positions, idx_a, idx_b, max_distance_mm, weight, m, pin_a, pin_b))
    })
}

// Separation loss (batch group-to-group)
#[pyfunction]
fn compute_separation_loss_py(
    _py: Python<'_>,
    positions_a: Vec<f64>,
    positions_b: Vec<f64>,
    min_distance_mm: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        Ok(compute_separation_loss_batch(&positions_a, &positions_b, min_distance_mm, weight))
    })
}

// Zone membership loss
#[pyfunction]
fn compute_enclosing_loss_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    margin_mm: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        Ok(compute_zone_membership_loss(
            &positions,
            (x_min, y_min, x_max, y_max),
            margin_mm,
            weight,
        ))
    })
}

// Alignment loss
#[pyfunction]
fn compute_alignment_loss_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    axis: &str,
    tolerance_mm: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        let a = match axis {
            "x" => Axis::X,
            "y" => Axis::Y,
            "major" => Axis::Major,
            "minor" => Axis::Minor,
            _ => return Err(PyValueError::new_err(format!("Unknown axis: {axis}"))),
        };
        Ok(compute_alignment_loss(&positions, a, tolerance_mm, weight))
    })
}

// Edge preference loss
#[pyfunction]
fn compute_edge_loss_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    side: &str,
    board_width: f64,
    board_height: f64,
    max_distance_mm: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        let s = match side {
            "top" => BoardSide::Top,
            "bottom" => BoardSide::Bottom,
            "left" => BoardSide::Left,
            "right" => BoardSide::Right,
            _ => return Err(PyValueError::new_err(format!("Unknown side: {side}"))),
        };
        Ok(compute_edge_preference_loss(
            &positions, s, board_width, board_height, max_distance_mm, weight,
        ))
    })
}

// Anchored loss (position variant)
#[pyfunction]
fn compute_anchored_loss_position_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    target_x: f64,
    target_y: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        Ok(compute_anchored_loss_position(&positions, 0, target_x, target_y, weight))
    })
}

// Anchored loss (region variant)
#[pyfunction]
fn compute_anchored_loss_region_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        Ok(compute_anchored_loss_region(
            &positions, 0, (x_min, y_min, x_max, y_max), weight,
        ))
    })
}

// Loop area loss
#[pyfunction]
fn compute_loop_area_loss_py(
    _py: Python<'_>,
    positions: Vec<f64>,
    max_area_mm2: f64,
    weight: f64,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        Ok(compute_loop_area_loss(&positions, max_area_mm2, weight))
    })
}

// Constraint type enum (Python-visible)
#[pyclass(name = "ConstraintType", eq, eq_int)]
#[derive(Clone, PartialEq)]
enum PyConstraintType {
    Adjacent = 1,
    Separated = 2,
    Enclosing = 3,
    Aligned = 4,
    OnSide = 5,
    Anchored = 6,
    LoopArea = 7,
}

// Unified dispatch: takes constraint type + args as a Python list and computes loss
#[pyfunction]
#[pyo3(signature = (constraint_type, args, positions))]
fn compute_constraint_loss_py(
    _py: Python<'_>,
    constraint_type: u8,
    args: Vec<f64>,
    positions: Vec<f64>,
) -> PyResult<f64> {
    catch_unwind_f64(|| {
        match constraint_type {
            1 => {
                // args: [idx_a, idx_b, max_distance, weight]
                if args.len() < 4 {
                    return Err(PyValueError::new_err("adjacent needs at least 4 args"));
                }
                Ok(compute_adjacent_loss(
                    &positions,
                    args[0] as usize,
                    args[1] as usize,
                    args[2],
                    args[3],
                    DistanceMetric::CenterToCenter,
                    None,
                    None,
                ))
            }
            2 => {
                // args: [n_a, n_b_items..., n_a_skip, min_distance, weight]
                // positions slice is shared; separation uses two groups from same array
                if args.len() < 2 {
                    return Err(PyValueError::new_err("separated needs at least 2 args"));
                }
                let n_a = args[0] as usize;
                let n_b = args[1] as usize;
                let min_dist = args[2];
                let weight = args[3];

                let pos_a: Vec<f64> = positions[..n_a * 2].to_vec();
                let pos_b: Vec<f64> = positions[n_a * 2..(n_a + n_b) * 2].to_vec();
                Ok(compute_separation_loss_batch(
                    &pos_a, &pos_b, min_dist, weight,
                ))
            }
            3 => {
                // args: [x_min, y_min, x_max, y_max, margin_mm, weight]
                if args.len() < 6 {
                    return Err(PyValueError::new_err("enclosing needs at least 6 args"));
                }
                Ok(compute_zone_membership_loss(
                    &positions,
                    (args[0], args[1], args[2], args[3]),
                    args[4],
                    args[5],
                ))
            }
            4 => {
                // args: [axis_int, tolerance_mm, weight]
                // axis: 0=X, 1=Y, 2=MAJOR, 3=MINOR
                if args.len() < 3 {
                    return Err(PyValueError::new_err("aligned needs at least 3 args"));
                }
                let axis = match args[0] as u8 {
                    0 => Axis::X,
                    1 => Axis::Y,
                    2 => Axis::Major,
                    3 => Axis::Minor,
                    _ => return Err(PyValueError::new_err(format!("invalid axis: {}", args[0]))),
                };
                Ok(compute_alignment_loss(&positions, axis, args[1], args[2]))
            }
            5 => {
                // args: [side_int, board_width, board_height, max_dist, weight]
                if args.len() < 5 {
                    return Err(PyValueError::new_err("on_side needs at least 5 args"));
                }
                let side = match args[0] as u8 {
                    0 => BoardSide::Top,
                    1 => BoardSide::Bottom,
                    2 => BoardSide::Left,
                    3 => BoardSide::Right,
                    _ => return Err(PyValueError::new_err(format!("invalid side: {}", args[0]))),
                };
                Ok(compute_edge_preference_loss(
                    &positions, side, args[1], args[2], args[3], args[4],
                ))
            }
            6 => {
                // args: [is_region, x_min/pos_x, y_min/pos_y, x_max/0, y_max/0, weight]
                if args.len() < 6 {
                    return Err(PyValueError::new_err("anchored needs at least 6 args"));
                }
                if args[0] > 0.0 {
                    // Region mode
                    Ok(compute_anchored_loss_region(
                        &positions, 0, (args[1], args[2], args[3], args[4]), args[5],
                    ))
                } else {
                    // Position mode
                    Ok(compute_anchored_loss_position(
                        &positions, 0, args[1], args[2], args[5],
                    ))
                }
            }
            7 => {
                // args: [max_area_mm2, weight]
                if args.len() < 2 {
                    return Err(PyValueError::new_err("loop_area needs at least 2 args"));
                }
                Ok(compute_loop_area_loss(&positions, args[0], args[1]))
            }
            t => Err(PyValueError::new_err(format!(
                "Unknown constraint type: {t}. Supported: 1=adjacent, 2=separated, 3=enclosing, 4=aligned, 5=on_side, 6=anchored, 7=loop_area"
            ))),
        }
    })
}

// Module metadata: list of supported constraint types (R12: test detects unknown types)
#[pyfunction]
fn supported_constraint_types_py(py: Python<'_>) -> PyResult<PyObject> {
    let list = PyList::new(
        py,
        [
            "adjacent", "separated", "enclosing", "aligned",
            "on_side", "anchored", "loop_area",
        ],
    )?;
    Ok(list.into())
}

// Version / health check
#[pyfunction]
fn is_available_py() -> bool {
    true
}

#[pyfunction]
fn version_py() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[pymodule]
fn temper_constraints(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tier_to_weight_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_adjacent_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_separation_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_enclosing_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_alignment_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_edge_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_anchored_loss_position_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_anchored_loss_region_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_loop_area_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_constraint_loss_py, m)?)?;
    m.add_function(wrap_pyfunction!(supported_constraint_types_py, m)?)?;
    m.add_function(wrap_pyfunction!(is_available_py, m)?)?;
    m.add_function(wrap_pyfunction!(version_py, m)?)?;
    m.add_class::<PyConstraintType>()?;
    Ok(())
}

//! PyO3 bridge for the Theta* / Lazy Theta* search kernels (Wave-4 port of
//! `router_v6/_astar_theta_star.py`).
//!
//! The pure kernels live in `temper-rust-router-core` (`theta_star.rs`);
//! this module only converts the Python grid bytes and cell indices to the
//! core input shape and back, guarding every exported function with
//! `catch_unwind` so a panic cannot unwind across the FFI boundary.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use temper_rust_router_core::theta_star::{ThetaStarInput, ThetaStarKind};

/// Convert a panic payload into a PyRuntimeError with a descriptive message
/// (local mirror of `temper_py_bridge::panic_to_err`, avoiding a new crate
/// dependency for one function).
fn panic_to_err(e: Box<dyn std::any::Any + Send>) -> PyErr {
    let msg = if let Some(s) = e.downcast_ref::<String>() {
        s.clone()
    } else if let Some(s) = e.downcast_ref::<&str>() {
        s.to_string()
    } else {
        "unknown panic".to_string()
    };
    PyRuntimeError::new_err(msg)
}

/// Python-callable Theta* / Lazy Theta* search.
///
/// Mirrors `_astar_search_theta_star` / `_astar_search_lazy_theta_star`:
/// ``grid_bytes`` is a row-major ``(height, width)`` int8 occupancy buffer;
/// ``start_idx``/``goal_idx`` are flat ``row * width + col`` indices;
/// ``came_from_init`` is a list of ``(child_idx, parent_idx)`` warm-start
/// pairs (or ``None``); ``max_iter`` is ``None`` for unlimited.
///
/// Returns the path as flat cell indices (empty list when no path exists).
#[pyfunction]
#[pyo3(signature = (
    grid_bytes,
    width_cells,
    height_cells,
    start_idx,
    goal_idx,
    net_id,
    came_from_init=None,
    max_iter=None,
    enable_congestion_derivative=true,
    lazy=false,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
fn theta_star_search_py(
    grid_bytes: Vec<u8>,
    width_cells: usize,
    height_cells: usize,
    start_idx: i64,
    goal_idx: i64,
    net_id: i64,
    came_from_init: Option<Vec<(i64, i64)>>,
    max_iter: Option<u64>,
    enable_congestion_derivative: bool,
    lazy: bool,
) -> PyResult<Vec<i64>> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        // Interpret the bytes as int8 (the grid's CellState dtype); -1
        // sentinels must keep their sign.
        let grid: Vec<i8> = grid_bytes.into_iter().map(|b| b as i8).collect();
        let init: Vec<(usize, usize)> = came_from_init
            .map(|pairs| {
                pairs
                    .into_iter()
                    .map(|(c, p)| (c.max(0) as usize, p.max(0) as usize))
                    .collect()
            })
            .unwrap_or_default();
        let kind = if lazy {
            ThetaStarKind::LazyThetaStar
        } else {
            ThetaStarKind::ThetaStar
        };
        let input = ThetaStarInput {
            grid: &grid,
            width: width_cells,
            height: height_cells,
            start: start_idx.max(0) as usize,
            goal: goal_idx.max(0) as usize,
            net_id,
            came_from_init: if init.is_empty() { None } else { Some(&init) },
            max_iter,
            enable_congestion_derivative,
        };
        let out = match kind {
            ThetaStarKind::ThetaStar => {
                temper_rust_router_core::theta_star::theta_star_search(&input)
            }
            ThetaStarKind::LazyThetaStar => {
                temper_rust_router_core::theta_star::lazy_theta_star_search(&input)
            }
        };
        out.unwrap_or_default().into_iter().map(|i| i as i64).collect()
    }))
    .map_err(panic_to_err)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(theta_star_search_py, m)?)?;
    Ok(())
}

//! The U4 (O-C3) owned `ClearanceGrid` core: the scalar dims + the net-id
//! registry of the numpy-backed `ClearanceGrid` data type
//! (`temper_placer/deterministic/stages/_grid_core.py`).
//!
//! # Owned vs keep
//!
//! The `ClearanceGrid` dataclass holds two kinds of state: four scalar dims
//! plus a net-id registry (portable), and the numpy `int32` cell arrays
//! `_trace_net_ids` / `_pad_net_ids` (NOT portable — see below). The owned
//! struct here holds the portable half; the arrays are the
//! orchestration-side `Marshal`'s `Plain::Opaque` keeps (identity
//! passthrough), exactly like U3's `OwnedBoard` foreign-pyclass keeps.
//!
//! # Why the cell arrays are a keep (the U4 hard-blocker answer)
//!
//! The cell arrays are numpy `int32` ndarrays. Their DATA is portable — the
//! dtype is CONSTANT `int32` on every construction path
//! (`np.zeros((rows, cols), dtype=np.int32)`; there is no float grid), so a
//! typed `Vec<i32>` with an implicit constant dtype would be a faithful
//! representation of the *values* (no dtype tag is needed, and the
//! "int32 vs float" widening hazard the U0 doc flags cannot occur here,
//! because there is no float grid to widen). The CONTAINER is not portable:
//!
//! 1. **Zero-copy in-place mutation contract.** The rasterisation kernels
//!    (`grid_raster.rs`'s `block_circle_into_grid_py` etc.) mutate the
//!    arrays IN PLACE through pyo3's `PyBuffer<i32>` — the Rust kernel
//!    writes straight into the numpy buffer. Owning the cells as `Vec<i32>`
//!    would force `Vec → numpy → mutate → copy back` on every kernel call,
//!    an O(rows·cols) copy per call that destroys the established zero-copy
//!    design (the grids are mutated hundreds of times per stage run).
//! 2. **numpy is its own serialization.** Array identity (dtype, C-order,
//!    strides, buffer layout) is numpy's, not a Rust type's. This crate is
//!    pyo3-free and wasm32-compiled — it cannot express or hold a numpy
//!    array. The U0 convention already routes numpy through `Plain::Opaque`.
//! 3. **Downstream Python consumers demand real arrays.** The Cython A*
//!    consumes `occupancy_grid` (`np.stack(self._trace_net_ids)`) and
//!    `occupancy_bitmap` (uint64 words) — both must be real numpy arrays at
//!    the Python boundary.
//!
//! The marshalling cost of owning the cells (if one ignored 1–3): a
//! `Vec<i32> → np.array(..., dtype=np.int32)` reconstruction is an
//! O(rows·cols) copy through numpy's own constructor per round-trip, plus a
//! Rust-side `import numpy` in the pyo3 half — for a container that is
//! mutated in place by Rust kernels anyway. Keeping it Opaque is zero-copy
//! by construction: the SAME array objects are returned, so dtype/order/
//! bytes are unchanged because nothing is reconstructed.
//!
//! # The dims are `Val`
//!
//! `ClearanceGrid(width_mm, height_mm, cell_size_mm, layer_count)` performs
//! no `__init__` coercion, and the D3 stage passes `board.width` /
//! `board.height` (which are `Val`-shaped — `Board(100, 80)` keeps int
//! width) straight into the constructor, so `width_mm` / `height_mm` can be
//! int OR float; `cell_size_mm` has the same no-coercion contract. All three
//! are [`Val`]-shaped so `100` stays `100` and `100.0` stays `100.0`.
//! `layer_count` is the concrete `int` (dataclass default `2`).

use crate::Val;

/// The owned half of `deterministic/stages/_grid_core.py::ClearanceGrid`:
/// the four scalar dims + the net-id registry. The numpy `int32` cell arrays
/// are the pyo3-side `Plain::Opaque` keeps (see the module doc for why).
///
/// `rows`/`cols` and the three caches (`_occupancy_grid_cache`,
/// `_bitmap_cache`, `_bitmap_stride_cache`) are DERIVED, not stored: the
/// constructor's `__post_init__` recomputes `rows = int(height / cell)` /
/// `cols = int(width / cell)` and resets the caches to `None` on every
/// write-back, exactly like the Netlist index dicts in U3.
#[derive(Clone, Debug, PartialEq)]
pub struct ClearanceGrid {
    pub width_mm: Val,
    pub height_mm: Val,
    pub cell_size_mm: Val,
    pub layer_count: i64,
    /// `_net_to_id` in insertion order — the net-id ASSIGNMENT order,
    /// which the D3 differential pins as load-bearing.
    pub net_to_id: Vec<(String, i64)>,
    /// `_id_to_net` in insertion order (the inverse map, also stored).
    pub id_to_net: Vec<(i64, String)>,
    /// `_next_net_id` (the monotonically-increasing id counter).
    pub next_net_id: i64,
}

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// The owned grid records the int-vs-float distinction at the dim level
    /// exactly like `Board.width`/`height`: `ClearanceGrid(100, 80, 0.5)`
    /// keeps int width/height, and the `Val` fields must record which.
    #[test]
    fn grid_dims_distinguish_int_from_float() {
        let int_grid = ClearanceGrid {
            width_mm: Val::Int(100),
            height_mm: Val::Int(80),
            cell_size_mm: Val::Float(0.5),
            layer_count: 2,
            net_to_id: vec![("GND".into(), 1)],
            id_to_net: vec![(1, "GND".into())],
            next_net_id: 2,
        };
        let float_grid = ClearanceGrid {
            width_mm: Val::Float(100.0),
            height_mm: Val::Float(80.0),
            cell_size_mm: Val::Float(0.5),
            layer_count: 2,
            net_to_id: vec![("GND".into(), 1)],
            id_to_net: vec![(1, "GND".into())],
            next_net_id: 2,
        };
        assert_ne!(int_grid, float_grid, "int 100 must not equal float 100.0");
        assert_eq!(int_grid, int_grid.clone());
        assert_eq!(float_grid, float_grid.clone());
    }

    /// The registry is the net-id assignment order: `net_to_id` must hold
    /// names in first-seen order (the load-bearing property the D3
    /// differential pins), with `next_net_id` one past the last assigned id.
    #[test]
    fn registry_holds_assignment_order_and_counter() {
        let grid = ClearanceGrid {
            width_mm: Val::Float(100.0),
            height_mm: Val::Float(80.0),
            cell_size_mm: Val::Float(0.5),
            layer_count: 2,
            net_to_id: vec![("VCC".into(), 1), ("GND".into(), 2), ("SIG".into(), 3)],
            id_to_net: vec![(1, "VCC".into()), (2, "GND".into()), (3, "SIG".into())],
            next_net_id: 4,
        };
        assert_eq!(grid.net_to_id[0], ("VCC".to_string(), 1));
        assert_eq!(grid.net_to_id[2], ("SIG".to_string(), 3));
        assert_eq!(grid.id_to_net[1], (2, "GND".to_string()));
        assert_eq!(grid.next_net_id, 4);
    }
}

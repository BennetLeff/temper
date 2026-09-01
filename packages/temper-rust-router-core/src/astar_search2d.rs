//! Faithful f64 port of `router_v6/astar_core.py`'s `_astar_search`.
//!
//! This is a **separate kernel from [`crate::astar::astar_kernel_3d`]** and
//! deliberately so. `astar_kernel_3d` is the live 2D primary search for every
//! net, and it is not a faithful base to copy from for this port:
//!
//! * it maintains a **closed set** and skips re-expansion, while
//!   `_astar_search` has none — a node whose `cost_so_far` improves after it
//!   was already popped is popped and expanded again, and stale heap entries
//!   are fully re-processed;
//! * it computes in **f32** (octile heuristic evaluated in f64 then cast),
//!   while `_astar_search` is f64 throughout;
//! * it hardcodes `std::f32::consts::SQRT_2` as the diagonal step cost, with
//!   no counterpart to `astar_core.DIAGONAL_COST_FACTOR` — a module attribute
//!   the Python multiplies in on every diagonal expansion and which callers
//!   are documented to be able to reassign at runtime.
//!
//! Any of those three differences can change which cell an argmin lands on, so
//! `astar_kernel_3d` is left untouched and this module mirrors the Python
//! statement for statement instead.
//!
//! # Float fidelity
//!
//! Every arithmetic site below is the same operation, in the same order, on
//! the same widths as the Python:
//!
//! * `OCTILE_DIAG` is `math.sqrt(2.0) - 1.0` and `BASE_DIAGONAL_COST` is
//!   `math.sqrt(2.0)`. IEEE-754 requires `sqrt` to be correctly rounded, and
//!   `std::f64::consts::SQRT_2` is the correctly-rounded double nearest √2, so
//!   the two agree bit for bit. (`_astar_search` never spells a square root as
//!   `x ** 0.5` and never squares with `**`, so neither of the two known
//!   `pow`-vs-`sqrt`/`mul` divergences in this repo is reachable from here.)
//! * the heuristic is `hi + OCTILE_DIAG * lo` with `hi`/`lo` exact small
//!   integers widened to f64 — one multiply, one add, no fused operation.
//! * the same-net discount is applied as a **second, separate** multiply after
//!   the diagonal factor, never folded into one constant.
//! * the thermal term widens an f32 cell value to f64 before multiplying,
//!   matching Python's `float(thermal_flat[n_idx])`.
//!
//! # Tie-breaking
//!
//! Python pushes `(priority, (x, y))` onto a `heapq` min-heap, so ties on
//! `priority` break lexicographically on the `(x, y)` **integer** tuple.
//! [`HeapKey`] below orders on exactly that triple. Two heap entries can only
//! compare equal when their priority *and* their cell are equal, i.e. when the
//! entries are indistinguishable, so the pop **sequence** is fully determined
//! by the comparison alone and does not depend on either implementation's
//! internal sift order.
//!
//! # Failure
//!
//! An exhausted frontier returns [`None`] — the Python's `None`, not an empty
//! path. There is no iteration cap; the Python has none either.

use std::cmp::Ordering;
use std::collections::BinaryHeap;

/// `math.sqrt(2.0) - 1.0` — `astar_core.OCTILE_DIAG`.
pub const OCTILE_DIAG: f64 = std::f64::consts::SQRT_2 - 1.0;

/// `math.sqrt(2.0)` — `astar_core._BASE_DIAGONAL_COST`.
pub const BASE_DIAGONAL_COST: f64 = std::f64::consts::SQRT_2;

/// `astar_core._SAME_NET_COST_DISCOUNT`.
pub const SAME_NET_COST_DISCOUNT: f64 = 0.25;

/// `astar_core._DIRS_8` — E, SE, S, SW, W, NW, N, NE.
pub const DIRS_8: [(i64, i64); 8] = [
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
];

/// Inputs to [`astar_search_2d`], one field per `_astar_search` parameter.
pub struct Astar2dInput<'a> {
    pub start: (i64, i64),
    pub goal: (i64, i64),
    pub width_cells: i64,
    pub height_cells: i64,
    /// `(height_cells * width_cells,)` int8 occupancy, row-major.
    /// Read only on the `net_id >= 0` branch.
    pub grid: &'a [i8],
    /// `(height_cells * width_cells * 8,)` neighbour-validity bits, one byte
    /// per `(row, col, dir)`. Read only on the `net_id < 0` branch, which is
    /// the branch that consults the pre-baked tensor.
    pub neighbor_tensor: Option<&'a [u8]>,
    /// `(height_cells * width_cells,)` float32 thermal cost field.
    pub thermal_flat: Option<&'a [f32]>,
    pub thermal_weight: f64,
    pub net_id: i64,
    /// `(height_cells * width_cells,)` corridor mask, 0 = outside.
    pub corridor_mask: Option<&'a [u8]>,
    /// `astar_core.DIAGONAL_COST_FACTOR`, read from the live module at call
    /// time rather than baked in — it is a plain module attribute callers are
    /// documented to be able to reassign.
    pub diagonal_cost_factor: f64,
}

/// Heap key ordering `(priority, x, y)` exactly as Python's
/// `(priority, (x, y))` tuple does. `f64` here is never NaN: every priority is
/// a finite sum of finite costs.
#[derive(PartialEq)]
struct HeapKey {
    priority: f64,
    x: i64,
    y: i64,
}

impl Eq for HeapKey {}

impl Ord for HeapKey {
    fn cmp(&self, other: &Self) -> Ordering {
        // `partial_cmp` cannot be None here (no NaN priorities); the fallback
        // keeps the impl total rather than panicking if that ever changed.
        self.priority
            .partial_cmp(&other.priority)
            .unwrap_or(Ordering::Equal)
            .then(self.x.cmp(&other.x))
            .then(self.y.cmp(&other.y))
    }
}

impl PartialOrd for HeapKey {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// `BinaryHeap` is a max-heap; invert so the smallest key pops first, as
/// `heapq` does.
struct MinKey(HeapKey);

impl PartialEq for MinKey {
    fn eq(&self, other: &Self) -> bool {
        self.0 == other.0
    }
}
impl Eq for MinKey {}
impl Ord for MinKey {
    fn cmp(&self, other: &Self) -> Ordering {
        other.0.cmp(&self.0)
    }
}
impl PartialOrd for MinKey {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

/// `astar_core.octile_distance` / `_heuristic`.
#[inline]
pub fn octile_distance(a: (i64, i64), b: (i64, i64)) -> f64 {
    let dx = (a.0 - b.0).abs();
    let dy = (a.1 - b.1).abs();
    let hi = dx.max(dy) as f64;
    let lo = dx.min(dy) as f64;
    hi + OCTILE_DIAG * lo
}

/// `astar_core.in_bounds`.
#[inline]
fn in_bounds(x: i64, y: i64, width_cells: i64, height_cells: i64) -> bool {
    0 <= x && x < width_cells && 0 <= y && y < height_cells
}

/// Faithful port of `astar_core._astar_search`.
///
/// Returns the cell sequence from `start` to `goal` inclusive, or `None` when
/// the frontier empties without reaching the goal.
pub fn astar_search_2d(input: &Astar2dInput) -> Option<Vec<(i64, i64)>> {
    let cols = input.width_cells;
    let rows = input.height_cells;
    if cols <= 0 || rows <= 0 {
        return None;
    }
    let n_cells = (cols as usize) * (rows as usize);

    let use_thermal = input.thermal_flat.is_some() && input.thermal_weight > 0.0;

    // `came_from`/`cost_so_far` are Python dicts keyed by cell; flat arrays
    // with an explicit presence bit reproduce `in cost_so_far` exactly.
    let mut cost_so_far = vec![0.0f64; n_cells];
    let mut has_cost = vec![false; n_cells];
    // -1 == the Python's `came_from[start] = None`; -2 == "no entry yet".
    let mut came_from = vec![-2i64; n_cells];

    let idx = |x: i64, y: i64| -> usize { (y as usize) * (cols as usize) + (x as usize) };

    if !in_bounds(input.start.0, input.start.1, cols, rows) {
        // Python would raise IndexError on the first grid read instead of
        // returning; callers (`route_edge_astar`) bounds-check both terminals
        // before calling, so this branch is unreachable from production. Fail
        // closed rather than invent a path.
        return None;
    }

    let start_i = idx(input.start.0, input.start.1);
    cost_so_far[start_i] = 0.0;
    has_cost[start_i] = true;
    came_from[start_i] = -1;

    let mut frontier: BinaryHeap<MinKey> = BinaryHeap::new();
    // Python: `heappush(frontier, (0, start))` — an int 0, numerically equal
    // to 0.0 and comparing identically against every later float priority.
    frontier.push(MinKey(HeapKey {
        priority: 0.0,
        x: input.start.0,
        y: input.start.1,
    }));

    // Precomputed once; `factor * BASE_DIAGONAL_COST` is a single deterministic
    // multiply, so hoisting it out of the loop is bit-identical to Python
    // re-evaluating it per expansion.
    let diagonal_cost = input.diagonal_cost_factor * BASE_DIAGONAL_COST;

    while let Some(MinKey(HeapKey { x: cx, y: cy, .. })) = frontier.pop() {
        if (cx, cy) == input.goal {
            let mut path = Vec::new();
            let mut cur = (cx, cy);
            loop {
                path.push(cur);
                let p = came_from[idx(cur.0, cur.1)];
                if p == -1 {
                    break;
                }
                debug_assert!(p >= 0, "came_from hole during reconstruction");
                let pu = p as usize;
                cur = ((pu % (cols as usize)) as i64, (pu / (cols as usize)) as i64);
            }
            path.reverse();
            return Some(path);
        }

        let current_cost = cost_so_far[idx(cx, cy)];

        for (dir_idx, (dx, dy)) in DIRS_8.iter().enumerate() {
            let nx = cx + dx;
            let ny = cy + dy;
            let mut is_same_net = false;

            if input.net_id >= 0 {
                if !in_bounds(nx, ny, cols, rows) {
                    continue;
                }
                let n_i = idx(nx, ny);
                if let Some(mask) = input.corridor_mask {
                    if mask[n_i] == 0 {
                        continue;
                    }
                }
                let cell_value = input.grid[n_i] as i64;
                if cell_value != 0 && cell_value != input.net_id {
                    continue;
                }
                is_same_net = cell_value == input.net_id;
            } else {
                // Mirrors the Python's `assert neighbor_tensor is not None`
                // on this branch: no tensor means there is nothing to consult,
                // so there is no path to report.
                let tensor = input.neighbor_tensor?;
                let t_i = (idx(cx, cy)) * 8 + dir_idx;
                if tensor.get(t_i).copied().unwrap_or(0) == 0 {
                    continue;
                }
                if !in_bounds(nx, ny, cols, rows) {
                    // The tensor already encodes bounds; this only guards the
                    // indexing below.
                    continue;
                }
            }

            let mut move_cost = if *dx != 0 && *dy != 0 {
                diagonal_cost
            } else {
                1.0
            };
            if is_same_net {
                move_cost *= SAME_NET_COST_DISCOUNT;
            }
            if use_thermal {
                if let Some(thermal) = input.thermal_flat {
                    let n_idx = (ny as usize) * (cols as usize) + (nx as usize);
                    move_cost += input.thermal_weight * (thermal[n_idx] as f64);
                }
            }
            let new_cost = current_cost + move_cost;
            let n_i = idx(nx, ny);

            if !has_cost[n_i] || new_cost < cost_so_far[n_i] {
                cost_so_far[n_i] = new_cost;
                has_cost[n_i] = true;
                let priority = new_cost + octile_distance((nx, ny), input.goal);
                frontier.push(MinKey(HeapKey {
                    priority,
                    x: nx,
                    y: ny,
                }));
                came_from[n_i] = idx(cx, cy) as i64;
            }
        }
    }

    None
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn open_grid(w: i64, h: i64) -> Vec<i8> {
        vec![0i8; (w * h) as usize]
    }

    fn run(
        start: (i64, i64),
        goal: (i64, i64),
        w: i64,
        h: i64,
        grid: &[i8],
        mask: Option<&[u8]>,
    ) -> Option<Vec<(i64, i64)>> {
        astar_search_2d(&Astar2dInput {
            start,
            goal,
            width_cells: w,
            height_cells: h,
            grid,
            neighbor_tensor: None,
            thermal_flat: None,
            thermal_weight: 0.0,
            net_id: 1,
            corridor_mask: mask,
            diagonal_cost_factor: 1.0,
        })
    }

    #[cfg_attr(test, test)]
    fn sqrt2_constants_match_the_python_spelling() {
        // `math.sqrt(2.0)` is correctly rounded, and so is this constant.
        assert_eq!(BASE_DIAGONAL_COST.to_bits(), 4609047870845172685u64);
        assert_eq!(OCTILE_DIAG, BASE_DIAGONAL_COST - 1.0);
    }

    #[cfg_attr(test, test)]
    fn trivial_and_adjacent_paths() {
        let g = open_grid(5, 5);
        assert_eq!(run((0, 0), (0, 0), 5, 5, &g, None), Some(vec![(0, 0)]));
        assert_eq!(
            run((0, 0), (1, 0), 5, 5, &g, None),
            Some(vec![(0, 0), (1, 0)])
        );
    }

    #[cfg_attr(test, test)]
    fn blocked_goal_returns_none_not_empty() {
        let mut g = open_grid(5, 5);
        for y in 0..5 {
            g[(y * 5 + 2) as usize] = -1;
        }
        assert_eq!(run((0, 0), (4, 4), 5, 5, &g, None), None);
    }

    #[cfg_attr(test, test)]
    fn corridor_mask_blocks_independently_of_occupancy() {
        let g = open_grid(7, 3);
        let mut mask = vec![1u8; 21];
        for y in 0..3 {
            mask[(y * 7 + 3) as usize] = 0;
        }
        assert_eq!(run((0, 1), (6, 1), 7, 3, &g, Some(&mask)), None);
    }

    #[cfg_attr(test, test)]
    fn ties_break_lexicographically_on_x_then_y() {
        // On an open plane every octile-optimal route ties; the emitted path
        // is whichever the (priority, x, y) ordering reaches first.
        let g = open_grid(4, 4);
        assert_eq!(
            run((0, 0), (3, 3), 4, 4, &g, None),
            Some(vec![(0, 0), (1, 1), (2, 2), (3, 3)]),
            "the pure diagonal is the octile optimum, and the (priority, x, y) \
             ordering is what picks it out of the tie"
        );
    }

    #[cfg_attr(test, test)]
    fn same_net_cells_are_traversable_and_discounted() {
        let mut g = open_grid(5, 1);
        g[2] = 1; // same net as net_id
        let p = run((0, 0), (4, 0), 5, 1, &g, None);
        assert_eq!(
            p,
            Some(vec![(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]),
            "a same-net cell must not block"
        );
    }

    #[cfg_attr(test, test)]
    fn foreign_net_cells_block() {
        let mut g = open_grid(5, 1);
        g[2] = 7;
        assert_eq!(run((0, 0), (4, 0), 5, 1, &g, None), None);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("astar_search2d::tests::sqrt2_constants_match_the_python_spelling", sqrt2_constants_match_the_python_spelling),
        ("astar_search2d::tests::trivial_and_adjacent_paths", trivial_and_adjacent_paths),
        ("astar_search2d::tests::blocked_goal_returns_none_not_empty", blocked_goal_returns_none_not_empty),
        ("astar_search2d::tests::corridor_mask_blocks_independently_of_occupancy", corridor_mask_blocks_independently_of_occupancy),
        ("astar_search2d::tests::ties_break_lexicographically_on_x_then_y", ties_break_lexicographically_on_x_then_y),
        ("astar_search2d::tests::same_net_cells_are_traversable_and_discounted", same_net_cells_are_traversable_and_discounted),
        ("astar_search2d::tests::foreign_net_cells_block", foreign_net_cells_block),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

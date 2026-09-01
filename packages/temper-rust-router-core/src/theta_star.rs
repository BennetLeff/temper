//! Theta* / Lazy Theta* search kernels — Wave-4 port of
//! `router_v6/_astar_theta_star.py`.
//!
//! Faithful mirror of the pinned Python reference: same min-heap ordering
//! (priority `(f_score, counter)` with a per-push integer counter — the
//! exact tie-break that makes the Python heapq search deterministic), same
//! 8-connected neighbor order (`_SAME_LAYER_DELTAS` = E, S, W, N, SE, SW,
//! NW, NE), same Euclidean step cost computed from exact integer cell
//! deltas, same congestion-derivative early-abort constants, and the same
//! LOS-at-pop (Lazy) / LOS-at-push (Standard) split over a Bresenham
//! line-of-sight check that is boolean-identical to the Python reference.
//!
//! Path identity is asserted as cell-sequence equality by the differential
//! suite (KTD7 convention); the searches expose no floating-point result,
//! so there is nothing to compare via `float.hex()` — the only floats are
//! integer-derived Euclidean distances (catalog class B7: exact integer
//! operands, exact double conversion below 2^53).

/// The oracle's `astar_core._SAME_LAYER_DELTAS` iteration order: E, S, W,
/// N, SE, SW, NW, NE.  Load-bearing: it fixes the order in which neighbors
/// are pushed, which fixes the `counter` sequence, which fixes tie-breaking.
const SAME_LAYER_DELTAS: [(i64, i64); 8] = [
    (0, 1),
    (1, 0),
    (0, -1),
    (-1, 0),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];

/// `_astar_theta_star._CONGESTION_*` early-abort constants.
const CONGESTION_CHECK_INTERVAL: usize = 1000;
const CONGESTION_GROWTH_THRESHOLD: usize = 5;
const CONGESTION_PLATEAU_STRIKES: usize = 3;

/// Which Theta* variant a search runs.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum ThetaStarKind {
    /// Standard Theta*: line-of-sight is checked at push time
    /// (parent -> neighbor shortcut).
    ThetaStar,
    /// Lazy Theta*: line-of-sight is checked at pop time
    /// (parent -> current), with the closed-neighbor parent correction.
    LazyThetaStar,
}

/// Inputs to a Theta*-family search — the mirror of the Python signature
/// `_astar_search_theta_star(grid, start_grid, goal_grid, net_id,
/// came_from_init, max_iter, enable_congestion_derivative)`.
pub struct ThetaStarInput<'a> {
    /// Row-major `(height, width)` int8 occupancy: 0 = free, >0 =
    /// net-owned, <0 = static-obstacle sentinel.
    pub grid: &'a [i8],
    pub width: usize,
    pub height: usize,
    /// Start cell as a flat `row * width + col` index.
    pub start: usize,
    /// Goal cell as a flat `row * width + col` index.
    pub goal: usize,
    /// Net id whose cells are treated as traversable (`cell == net_id`).
    pub net_id: i64,
    /// Optional warm-start `came_from`: `(child, parent)` cell-index pairs.
    /// Mirrors `came_from_init.copy()` — seeds only the came_from map;
    /// `g_score` still starts with only the start cell.
    pub came_from_init: Option<&'a [(usize, usize)]>,
    /// `max_iter` frontier-pop cap (None = unlimited).
    pub max_iter: Option<u64>,
    /// Early-abort when frontier growth plateaus
    /// (`enable_congestion_derivative`).
    pub enable_congestion_derivative: bool,
}

/// Standard Theta* search (LOS at push time).  `None` when no path is found
/// (or the search is aborted by `max_iter` / the congestion-derivative
/// plateau check).
pub fn theta_star_search(input: &ThetaStarInput<'_>) -> Option<Vec<usize>> {
    search(input, ThetaStarKind::ThetaStar)
}

/// Lazy Theta* search (LOS at pop time).  `None` when no path is found.
pub fn lazy_theta_star_search(input: &ThetaStarInput<'_>) -> Option<Vec<usize>> {
    search(input, ThetaStarKind::LazyThetaStar)
}

/// Bresenham line-of-sight between two grid cells — boolean-identical to
/// the pure-Python `_line_of_sight` reference (the BB-shortcut fast path is
/// omitted; it is boolean-neutral).
#[expect(
    clippy::too_many_arguments,
    reason = "mirrors the Python LOS signature 1:1; a config struct would not be a bit-exact mirror"
)]
pub fn line_of_sight(
    grid: &[i8],
    width: usize,
    height: usize,
    x0: i64,
    y0: i64,
    x1: i64,
    y1: i64,
    net_id: i64,
) -> bool {
    let (dx, dy) = ((x1 - x0).abs(), (y1 - y0).abs());
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx - dy;
    let (mut x, mut y) = (x0, y0);
    loop {
        if x < 0 || x >= width as i64 || y < 0 || y >= height as i64 {
            return false;
        }
        let cell = grid[(y * width as i64 + x) as usize] as i64;
        if cell != 0 && cell != net_id {
            return false;
        }
        if x == x1 && y == y1 {
            return true;
        }
        let e2 = 2 * err;
        if e2 > -dy {
            err -= dy;
            x += sx;
        }
        if e2 < dx {
            err += dx;
            y += sy;
        }
    }
}

fn line_of_sight_cells(input: &ThetaStarInput<'_>, a: usize, b: usize) -> bool {
    let (x0, y0) = ((a % input.width) as i64, (a / input.width) as i64);
    let (x1, y1) = ((b % input.width) as i64, (b / input.width) as i64);
    line_of_sight(
        input.grid,
        input.width,
        input.height,
        x0,
        y0,
        x1,
        y1,
        input.net_id,
    )
}

fn in_bounds(x: i64, y: i64, width: usize, height: usize) -> bool {
    x >= 0 && y >= 0 && (x as usize) < width && (y as usize) < height
}

/// `math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)` over integer
/// cell coordinates.  The Python operands are Python ints, so the sum is
/// computed exactly and converted to double for `sqrt`; the Rust form
/// computes the same exact integer and converts it exactly (values < 2^53).
fn euclidean_dist(a: usize, b: usize, width: usize) -> f64 {
    let ax = (a % width) as i64;
    let ay = (a / width) as i64;
    let bx = (b % width) as i64;
    let by = (b / width) as i64;
    let dx = ax - bx;
    let dy = ay - by;
    ((dx * dx + dy * dy) as f64).sqrt()
}

/// Heap priority: `(f_score, counter)`.  `counter` is a per-push incrementing
/// integer, so no two live heap entries share a key — pop order is the
/// sorted key order, identical to Python's heapq over `(f, counter, node)`.
type HeapKey = (f64, u64);

/// Strict `key < key` in Python's tuple order (f, counter).
fn key_lt(a: &HeapKey, b: &HeapKey) -> bool {
    a.0 < b.0 || (a.0 == b.0 && a.1 < b.1)
}

/// Binary min-heap push — same sift logic as CPython `heapq._siftdown` (and
/// the already-validated `astar.rs` heap): swap while the new item is
/// strictly less than its parent.
fn heap_push(pri: &mut Vec<HeapKey>, cells: &mut Vec<usize>, key: HeapKey, cell: usize) {
    pri.push(key);
    cells.push(cell);
    let mut i = pri.len() - 1;
    while i > 0 {
        let parent = (i - 1) >> 1;
        if !key_lt(&pri[i], &pri[parent]) {
            break;
        }
        pri.swap(parent, i);
        cells.swap(parent, i);
        i = parent;
    }
}

/// Binary min-heap pop: move the last element to the root and sift it down,
/// choosing the smaller child on each step (strict `<`, like CPython's
/// `_siftup`; with unique keys the left/right tie rule is moot).
fn heap_pop(pri: &mut Vec<HeapKey>, cells: &mut Vec<usize>) -> (HeapKey, usize) {
    let key = pri[0];
    let cell = cells[0];
    let last = pri.len() - 1;
    pri[0] = pri[last];
    cells[0] = cells[last];
    pri.pop();
    cells.pop();
    let size = pri.len();
    if size > 0 {
        let mut i = 0usize;
        loop {
            let left = 2 * i + 1;
            let right = 2 * i + 2;
            let mut smallest = i;
            if left < size && key_lt(&pri[left], &pri[smallest]) {
                smallest = left;
            }
            if right < size && key_lt(&pri[right], &pri[smallest]) {
                smallest = right;
            }
            if smallest == i {
                break;
            }
            pri.swap(i, smallest);
            cells.swap(i, smallest);
            i = smallest;
        }
    }
    (key, cell)
}

/// Standard-Theta* reconstruction: walk `came_from` until a key is absent.
fn reconstruct_standard(mut cell: usize, parent: &[i64]) -> Vec<usize> {
    let mut path = vec![cell];
    while parent[cell] >= 0 {
        cell = parent[cell] as usize;
        path.push(cell);
    }
    path.reverse();
    path
}

/// Lazy-Theta* reconstruction: walk `came_from`, stopping at the start cell
/// WITHOUT appending it (the pre-migration oracle's distinctive behaviour).
fn reconstruct_lazy(mut cell: usize, parent: &[i64], start: usize) -> Vec<usize> {
    let mut path = vec![cell];
    while parent[cell] >= 0 {
        cell = parent[cell] as usize;
        if cell == start {
            break;
        }
        path.push(cell);
    }
    path.reverse();
    path
}

fn search(input: &ThetaStarInput<'_>, kind: ThetaStarKind) -> Option<Vec<usize>> {
    let n_cells = input.width * input.height;
    let start = input.start;
    let goal = input.goal;
    // Defensive bounds guard: the Python reference never bounds-checks its
    // start/goal (callers pre-check via `_segment_search`), and a flat-array
    // implementation cannot represent an out-of-range cell.  No production
    // caller produces one; returning None is the safe behaviour.
    if start >= n_cells || goal >= n_cells {
        return None;
    }

    // came_from: cell -> parent cell, -1 = key absent from the Python dict.
    let mut parent = vec![-1i64; n_cells];
    if let Some(init) = input.came_from_init {
        for &(child, par) in init {
            if child < n_cells {
                parent[child] = par as i64;
            }
        }
    }

    // g_score / "neighbor not in g_score": flat array + presence flag.
    let mut g_score = vec![f64::INFINITY; n_cells];
    let mut g_set = vec![false; n_cells];
    let mut closed = vec![false; n_cells];
    let mut closed_count: usize = 0;

    g_score[start] = 0.0;
    g_set[start] = true;
    // Mirrors `len(g_score)` in the Python (`g_score = {start: 0.0}`).
    let mut g_count: usize = 1;

    let mut pri: Vec<HeapKey> = Vec::with_capacity(1024);
    let mut cells: Vec<usize> = Vec::with_capacity(1024);
    let mut counter: u64 = 0;
    heap_push(&mut pri, &mut cells, (0.0, counter), start);

    let mut g_score_size_prev: usize = 1;
    let mut plateau_count: usize = 0;

    while !pri.is_empty() {
        let (_, current) = heap_pop(&mut pri, &mut cells);

        if closed[current] {
            continue;
        }

        if kind == ThetaStarKind::LazyThetaStar {
            let p = parent[current];
            if p >= 0 && !line_of_sight_cells(input, p as usize, current) {
                // LOS failed at pop time: re-evaluate the parent from the
                // closed 8-connected neighbours, choosing the cheapest
                // (`if new_g < best_g` keeps the first minimal — same
                // iteration order, same strict comparison).
                let cx = (current % input.width) as i64;
                let cy = (current / input.width) as i64;
                let mut best_parent: Option<usize> = None;
                let mut best_g = f64::INFINITY;
                for (dx, dy) in SAME_LAYER_DELTAS {
                    let nx = cx + dx;
                    let ny = cy + dy;
                    if !in_bounds(nx, ny, input.width, input.height) {
                        continue;
                    }
                    let nb = (ny * input.width as i64 + nx) as usize;
                    if closed[nb] && g_set[nb] {
                        let step_cost = euclidean_dist(nb, current, input.width);
                        let new_g = g_score[nb] + step_cost;
                        if new_g < best_g {
                            best_g = new_g;
                            best_parent = Some(nb);
                        }
                    }
                }
                match best_parent {
                    Some(bp) => {
                        parent[current] = bp as i64;
                        g_score[current] = best_g;
                    }
                    // No valid parent: drop the node — not closed, not
                    // goal-checked — exactly like the oracle's `continue`.
                    None => continue,
                }
            }
        }

        if current == goal {
            return Some(match kind {
                ThetaStarKind::ThetaStar => reconstruct_standard(current, &parent),
                ThetaStarKind::LazyThetaStar => reconstruct_lazy(current, &parent, start),
            });
        }

        closed[current] = true;
        closed_count += 1;

        if let Some(max_iter) = input.max_iter {
            if closed_count as u64 >= max_iter {
                return None;
            }
        }

        if input.enable_congestion_derivative
            && closed_count.is_multiple_of(CONGESTION_CHECK_INTERVAL)
        {
            let new_cells = g_count - g_score_size_prev;
            if new_cells < CONGESTION_GROWTH_THRESHOLD {
                plateau_count += 1;
                if plateau_count >= CONGESTION_PLATEAU_STRIKES {
                    return None;
                }
            } else {
                plateau_count = 0;
            }
            g_score_size_prev = g_count;
        }

        let cx = (current % input.width) as i64;
        let cy = (current / input.width) as i64;
        for (dx, dy) in SAME_LAYER_DELTAS {
            let nx = cx + dx;
            let ny = cy + dy;
            if !in_bounds(nx, ny, input.width, input.height) {
                continue;
            }
            let nb = (ny * input.width as i64 + nx) as usize;
            let cell_value = input.grid[nb] as i64;
            if cell_value != 0 && cell_value != input.net_id {
                continue;
            }
            if closed[nb] {
                continue;
            }

            let (tentative_g, source) = match kind {
                ThetaStarKind::ThetaStar => {
                    let p = parent[current];
                    if p >= 0 && line_of_sight_cells(input, p as usize, nb) {
                        // Parent -> neighbor any-angle shortcut.
                        (
                            g_score[p as usize] + euclidean_dist(p as usize, nb, input.width),
                            p as usize,
                        )
                    } else {
                        // Standard A* step through `current`.
                        (
                            g_score[current] + euclidean_dist(current, nb, input.width),
                            current,
                        )
                    }
                }
                ThetaStarKind::LazyThetaStar => {
                    let grandparent = parent[current];
                    if grandparent >= 0 {
                        let tentative_g_lazy = g_score[grandparent as usize]
                            + euclidean_dist(grandparent as usize, nb, input.width);
                        let tentative_g_astar =
                            g_score[current] + euclidean_dist(current, nb, input.width);
                        if tentative_g_lazy < tentative_g_astar {
                            (tentative_g_lazy, grandparent as usize)
                        } else {
                            (tentative_g_astar, current)
                        }
                    } else {
                        (
                            g_score[current] + euclidean_dist(current, nb, input.width),
                            current,
                        )
                    }
                }
            };

            if !g_set[nb] || tentative_g < g_score[nb] {
                parent[nb] = source as i64;
                if !g_set[nb] {
                    g_set[nb] = true;
                    g_count += 1;
                }
                g_score[nb] = tentative_g;
                let f_score = tentative_g + euclidean_dist(nb, goal, input.width);
                counter += 1;
                heap_push(&mut pri, &mut cells, (f_score, counter), nb);
            }
        }
    }

    None
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn input_for(
        rows: usize,
        cols: usize,
        blocked: &[usize],
        start: usize,
        goal: usize,
    ) -> ThetaStarInput<'static> {
        let mut grid = vec![0i8; rows * cols];
        for &b in blocked {
            grid[b] = 1;
        }
        ThetaStarInput {
            grid: Box::leak(grid.into_boxed_slice()),
            width: cols,
            height: rows,
            start,
            goal,
            net_id: 0,
            came_from_init: None,
            max_iter: None,
            enable_congestion_derivative: true,
        }
    }

    #[cfg_attr(test, test)]
    fn theta_star_finds_open_grid_path() {
        let input = input_for(10, 10, &[], 0, 99);
        let out = theta_star_search(&input).unwrap();
        assert_eq!(*out.first().unwrap(), 0);
        assert_eq!(*out.last().unwrap(), 99);
    }

    #[cfg_attr(test, test)]
    fn lazy_theta_star_finds_open_grid_path() {
        let input = input_for(10, 10, &[], 0, 99);
        let out = lazy_theta_star_search(&input).unwrap();
        assert_eq!(*out.last().unwrap(), 99);
    }

    #[cfg_attr(test, test)]
    fn lazy_theta_star_drops_start_from_path() {
        // The lazy reconstruction stops at the start cell WITHOUT appending
        // it (pre-migration oracle behaviour).
        let input = input_for(10, 10, &[], 0, 99);
        let out = lazy_theta_star_search(&input).unwrap();
        assert!(
            !out.contains(&0),
            "lazy path must not contain the start cell"
        );
        let input_std = input_for(10, 10, &[], 0, 99);
        let out_std = theta_star_search(&input_std).unwrap();
        assert!(
            out_std.contains(&0),
            "standard path must contain the start cell"
        );
    }

    #[cfg_attr(test, test)]
    fn blocked_grid_returns_none() {
        let mut blocked: Vec<usize> = Vec::new();
        for r in 0..10 {
            blocked.push(r * 10 + 5);
        }
        let input = input_for(10, 10, &blocked, 0, 99);
        assert!(theta_star_search(&input).is_none());
        assert!(lazy_theta_star_search(&input).is_none());
    }

    #[cfg_attr(test, test)]
    fn start_equals_goal_returns_single_cell() {
        let input = input_for(8, 8, &[], 33, 33);
        assert_eq!(theta_star_search(&input).unwrap(), vec![33]);
        assert_eq!(lazy_theta_star_search(&input).unwrap(), vec![33]);
    }

    #[cfg_attr(test, test)]
    fn max_iter_cap_respected() {
        let input = ThetaStarInput {
            grid: Box::leak(vec![0i8; 30 * 30].into_boxed_slice()),
            width: 30,
            height: 30,
            start: 0,
            goal: 899,
            net_id: 0,
            came_from_init: None,
            max_iter: Some(10),
            enable_congestion_derivative: true,
        };
        assert!(theta_star_search(&input).is_none());
        assert!(lazy_theta_star_search(&input).is_none());
    }

    #[cfg_attr(test, test)]
    fn line_of_sight_matches_bresenham_reference() {
        // Same-cell and adjacent cases (mirror of the retired LOS parity pins).
        assert!(line_of_sight(&[0i8; 25], 5, 5, 0, 0, 0, 0, 0));
        assert!(line_of_sight(&[0i8; 25], 5, 5, 0, 0, 4, 4, 0));
        let mut grid = vec![0i8; 25];
        grid[2 * 5 + 2] = 1;
        assert!(!line_of_sight(&grid, 5, 5, 0, 0, 4, 4, 0));
        // Net ownership opens the line.
        let mut owned = vec![0i8; 25];
        owned[2 * 5 + 2] = 7;
        assert!(line_of_sight(&owned, 5, 5, 0, 0, 4, 4, 7));
        assert!(!line_of_sight(&owned, 5, 5, 0, 0, 4, 4, 0));
        // Out-of-bounds endpoint -> false.
        assert!(!line_of_sight(&[0i8; 25], 5, 5, 0, 0, 0, -1, 0));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("theta_star::tests::theta_star_finds_open_grid_path", theta_star_finds_open_grid_path),
        ("theta_star::tests::lazy_theta_star_finds_open_grid_path", lazy_theta_star_finds_open_grid_path),
        ("theta_star::tests::lazy_theta_star_drops_start_from_path", lazy_theta_star_drops_start_from_path),
        ("theta_star::tests::blocked_grid_returns_none", blocked_grid_returns_none),
        ("theta_star::tests::start_equals_goal_returns_single_cell", start_equals_goal_returns_single_cell),
        ("theta_star::tests::max_iter_cap_respected", max_iter_cap_respected),
        ("theta_star::tests::line_of_sight_matches_bresenham_reference", line_of_sight_matches_bresenham_reference),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

//! A* kernel — U5 port of `astar_core_numba.py::_astar_kernel_3d`.
//!
//! Faithful mirror of the Numba kernel: same binary-heap sift logic
//! (strict `<` in sift-down, `<=` break in sift-up), same 8-connected
//! neighbor order (E, SE, S, SW, W, NW, N, NE), same f32 arithmetic
//! order (octile heuristic computed in f64 then cast to f32; congestion
//! cost `1 + log(1 + raw)` with an f32 cap; thermal additive). Path
//! identity acceptance per the roadmap's KTD7: cell-sequence equality
//! with bit-identical output where float evaluation order is preserved.

/// `math.sqrt(2.0) - 1.0` — the octile heuristic diagonal weight.
pub const HEURISTIC_OCTILE_DIAG: f64 = std::f64::consts::SQRT_2 - 1.0;

pub struct AstarInput<'a> {
    pub start_idx: i64,
    pub goal_idx: i64,
    pub rows: usize,
    pub cols: usize,
    /// (rows*cols*8,) uint8 neighbor-validity tensor.
    pub validity: &'a [u8],
    pub max_iterations: u64,
    /// (rows*cols,) float32 per-cell usage counts.
    pub congestion: Option<&'a [f32]>,
    pub congestion_weight: f32,
    pub max_congestion_cost: f32,
    /// (rows*cols,) float32 thermal cost field.
    pub thermal: Option<&'a [f32]>,
    pub thermal_weight: f32,
}

pub struct AstarOutput {
    /// Cell indices from start to goal inclusive; empty if no path.
    pub path: Vec<i32>,
    pub iterations: u64,
}

fn octile_heuristic_f32(dx: i64, dy: i64) -> f32 {
    let (dx, dy) = (dx.unsigned_abs(), dy.unsigned_abs());
    let (hi, lo) = (dx.max(dy) as f64, dx.min(dy) as f64);
    (hi + HEURISTIC_OCTILE_DIAG * lo) as f32
}

pub fn astar_kernel_3d(input: &AstarInput) -> AstarOutput {
    const INF: f32 = 1.0e30;
    let n_cells = input.rows * input.cols;
    let use_congestion = input.congestion.is_some() && input.congestion_weight > 0.0;
    let use_thermal = input.thermal.is_some() && input.thermal_weight > 0.0;

    let mut g_score = vec![INF; n_cells];
    let start = input.start_idx as usize;
    if start >= n_cells {
        return AstarOutput { path: Vec::new(), iterations: 0 };
    }
    g_score[start] = 0.0f32;
    let mut came_from = vec![-1i32; n_cells];
    let mut closed = vec![0u8; n_cells];

    // Binary min-heap, parallel (priority, cell) arrays — same sift
    // logic as the Numba kernel (and Python's heapq).
    let mut heap_pri: Vec<f32> = Vec::with_capacity(4096);
    let mut heap_idx: Vec<i32> = Vec::with_capacity(4096);

    let (sr, sc) = (input.start_idx / input.cols as i64, input.start_idx % input.cols as i64);
    let (gr, gc) = (input.goal_idx / input.cols as i64, input.goal_idx % input.cols as i64);
    heap_push(&mut heap_pri, &mut heap_idx, octile_heuristic_f32((sc - gc).abs(), (sr - gr).abs()), input.start_idx as i32);

    let mut iterations: u64 = 0;
    while !heap_pri.is_empty() && iterations < input.max_iterations {
        iterations += 1;
        let (_, cur) = heap_pop(&mut heap_pri, &mut heap_idx);
        let cur_i = cur as usize;

        if cur as i64 == input.goal_idx {
            // Reconstruct path from came_from (goal back to start).
            let mut back_list = Vec::new();
            let mut c = cur as i64;
            while c != -1 {
                back_list.push(c as i32);
                c = came_from[c as usize] as i64;
            }
            back_list.reverse();
            return AstarOutput { path: back_list, iterations };
        }

        if closed[cur_i] != 0 {
            continue;
        }
        closed[cur_i] = 1;

        let cur_r = cur as i64 / input.cols as i64;
        let cur_c = cur as i64 - cur_r * input.cols as i64;

        let base = cur_i * 8;
        for d in 0..8usize {
            if input.validity.get(base + d).copied().unwrap_or(0) == 0 {
                continue;
            }
            // Direction table (E, SE, S, SW, W, NW, N, NE)
            let (ndc, ndr) = match d {
                0 => (cur_c + 1, cur_r),
                1 => (cur_c + 1, cur_r + 1),
                2 => (cur_c, cur_r + 1),
                3 => (cur_c - 1, cur_r + 1),
                4 => (cur_c - 1, cur_r),
                5 => (cur_c - 1, cur_r - 1),
                6 => (cur_c, cur_r - 1),
                _ => (cur_c + 1, cur_r - 1),
            };
            if ndc < 0 || ndr < 0 || ndc >= input.cols as i64 || ndr >= input.rows as i64 {
                continue;
            }
            let n_idx = (ndr * input.cols as i64 + ndc) as usize;

            // Octile step cost: straight 1.0, diagonal 1.4142135 (f32).
            let mut step: f32 = if d % 2 == 0 { 1.0 } else { std::f32::consts::SQRT_2 };

            // U7/R11 congestion penalty — f32 log(1+raw), capped.
            if use_congestion {
                if let Some(cong) = input.congestion {
                    let raw = cong[n_idx];
                    if raw > 0.0f32 {
                        let cong_cost = 1.0f32 + (1.0f32 + raw).ln();
                        let cong_cost = if cong_cost > input.max_congestion_cost {
                            input.max_congestion_cost
                        } else {
                            cong_cost
                        };
                        step += input.congestion_weight * cong_cost;
                    }
                }
            }
            // U8 additive thermal penalty.
            if use_thermal {
                if let Some(th) = input.thermal {
                    let t_val = th[n_idx];
                    if t_val > 0.0f32 {
                        step += input.thermal_weight * t_val;
                    }
                }
            }

            let tentative = g_score[cur_i] + step;
            if tentative < g_score[n_idx] {
                g_score[n_idx] = tentative;
                came_from[n_idx] = cur;
                let gdx = (ndc - gc).abs();
                let gdy = (ndr - gr).abs();
                let h = octile_heuristic_f32(gdx, gdy);
                heap_push(&mut heap_pri, &mut heap_idx, tentative + h, n_idx as i32);
            }
        }
    }

    AstarOutput { path: Vec::new(), iterations }
}

fn heap_push(heap_pri: &mut Vec<f32>, heap_idx: &mut Vec<i32>, pri: f32, idx: i32) {
    heap_pri.push(pri);
    heap_idx.push(idx);
    let mut i = heap_pri.len() - 1;
    while i > 0 {
        let parent = (i - 1) >> 1;
        if heap_pri[parent] <= heap_pri[i] {
            break;
        }
        heap_pri.swap(parent, i);
        heap_idx.swap(parent, i);
        i = parent;
    }
}

fn heap_pop(heap_pri: &mut Vec<f32>, heap_idx: &mut Vec<i32>) -> (f32, i32) {
    let pri = heap_pri[0];
    let idx = heap_idx[0];
    let last = heap_pri.len() - 1;
    heap_pri[0] = heap_pri[last];
    heap_idx[0] = heap_idx[last];
    heap_pri.pop();
    heap_idx.pop();
    let size = heap_pri.len();
    if size > 0 {
        let mut i = 0usize;
        loop {
            let left = 2 * i + 1;
            let right = 2 * i + 2;
            let mut smallest = i;
            if left < size && heap_pri[left] < heap_pri[smallest] {
                smallest = left;
            }
            if right < size && heap_pri[right] < heap_pri[smallest] {
                smallest = right;
            }
            if smallest == i {
                break;
            }
            heap_pri.swap(i, smallest);
            heap_idx.swap(i, smallest);
            i = smallest;
        }
    }
    (pri, idx)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_validity(rows: usize, cols: usize, blocked: &[usize]) -> Vec<u8> {
        let mut validity = vec![1u8; rows * cols * 8];
        for &b in blocked {
            for d in 0..8 {
                validity[b * 8 + d] = 0;
            }
        }
        validity
    }

    fn input_for<'a>(
        rows: usize,
        cols: usize,
        validity: &'a [u8],
        start: i64,
        goal: i64,
    ) -> AstarInput<'a> {
        AstarInput {
            start_idx: start,
            goal_idx: goal,
            rows,
            cols,
            validity,
            max_iterations: 1_000_000,
            congestion: None,
            congestion_weight: 1.0,
            max_congestion_cost: 100.0,
            thermal: None,
            thermal_weight: 0.0,
        }
    }

    #[test]
    fn test_finds_path_on_open_grid() {
        let validity = make_validity(5, 5, &[]);
        let input = input_for(5, 5, &validity, 0, 24);
        let out = astar_kernel_3d(&input);
        assert!(!out.path.is_empty());
        assert_eq!(*out.path.first().unwrap(), 0);
        assert_eq!(*out.path.last().unwrap(), 24);
    }

    #[test]
    fn test_path_is_connected_and_acyclic() {
        let validity = make_validity(8, 8, &[]);
        let input = input_for(8, 8, &validity, 0, 63);
        let out = astar_kernel_3d(&input);
        let mut seen = std::collections::HashSet::new();
        for w in out.path.windows(2) {
            let (a, b) = (w[0], w[1]);
            let (ar, ac) = (a / 8, a % 8);
            let (br, bc) = (b / 8, b % 8);
            assert!(ar.abs_diff(br) <= 1 && ac.abs_diff(bc) <= 1);
            assert!(seen.insert(b), "cell revisited");
        }
    }

    #[test]
    fn test_blocked_grid_returns_empty() {
        // Block everything except the start cell.
        let mut validity = vec![0u8; 4 * 4 * 8];
        for d in 0..8 {
            validity[0 * 8 + d] = 0;
        }
        let input = input_for(4, 4, &validity, 0, 15);
        let out = astar_kernel_3d(&input);
        assert!(out.path.is_empty());
    }

    #[test]
    fn test_iteration_cap_respected() {
        let validity = make_validity(30, 30, &[]);
        let mut input = input_for(30, 30, &validity, 0, 899);
        input.max_iterations = 10;
        let out = astar_kernel_3d(&input);
        assert!(out.path.is_empty());
        assert!(out.iterations <= 10);
    }

    #[test]
    fn test_congestion_changes_path() {
        // A congested blob at the route centre should push the path
        // around it (log cost 1+ln(501)≈7.2 per cell vs ~2.8 detour).
        let validity = make_validity(9, 9, &[]);
        let mut cong = vec![0.0f32; 81];
        cong[4 * 9 + 4] = 500.0;
        cong[4 * 9 + 5] = 500.0;
        let mut input = input_for(9, 9, &validity, 0, 80);
        input.congestion = Some(&cong);
        let with_cong = astar_kernel_3d(&input);
        let plain = astar_kernel_3d(&input_for(9, 9, &validity, 0, 80));
        assert!(!with_cong.path.is_empty());
        assert_eq!(*with_cong.path.first().unwrap(), 0);
        assert_eq!(*with_cong.path.last().unwrap(), 80);
        // The direct route through the blob must be abandoned.
        assert_ne!(with_cong.path, plain.path);
    }

    #[test]
    fn test_octile_heuristic_values() {
        // h = max(dx,dy) + (sqrt2-1)*min(dx,dy), computed in f64 then
        // cast to f32 (bit-exact mirror of the Python reference).
        assert_eq!(octile_heuristic_f32(0, 0), 0.0);
        assert_eq!(octile_heuristic_f32(2, 0), 2.0);
        assert!((octile_heuristic_f32(2, 2) - (2.0 * 2.0f64.sqrt()) as f32).abs() < 1e-6);
        let h31 = octile_heuristic_f32(3, 1);
        assert!((h31 - (3.0 + (2.0f64.sqrt() - 1.0)) as f32).abs() < 1e-6);
    }
}

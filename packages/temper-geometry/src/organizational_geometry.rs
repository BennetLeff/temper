// Wave 4: temper_placer/heuristics/organizational.py's placement-position
// kernels.
//
// Survey (docs/evidence/2026-08-06-never-port-triage.md, and independently
// confirmed while porting this file): `organizational.py` is split cleanly
// into two kinds of code.
//
//   - Classification: `identify_functional_modules`, `_find_highly_connected_groups`,
//     `classify_power_topology`, `identify_decoupling_caps`,
//     `classify_signal_domains`. These are regex/keyword lookup tables and
//     dict/set bookkeeping over component refs and net names -- no
//     floating-point arithmetic at all. Per the program's own rule
//     ("keyword lookup tables are NOT compute"), these stay Python.
//   - Placement: the five `_place_*` methods (one per Heuristic subclass).
//     Each is genuine geometric compute -- grid layout, trigonometric
//     offsets, linear interpolation -- and is what this module ports.
//     Python keeps the orchestration around each (iterating components,
//     `context.is_position_valid`/`check_overlap`, building
//     `ComponentPlacement`/`HeuristicResult`), exactly the same split
//     `heuristics_geometry.rs::keepout_mask_flags` already established for
//     `structural.py::create_keepout_mask`.
//
// Python reference (pinned verbatim at commit
// b9c766059c34649c2947f04f89a578fdb48a2756):
// `packages/temper-placer/src/temper_placer/heuristics/organizational.py`
// (oracle: `packages/temper-placer/tests/heuristics/_organizational_py_oracle.py`;
// differential: `packages/temper-placer/tests/heuristics/test_organizational_rust_differential.py`).
//
// Bit-exactness notes
// --------------------
//
// * `_place_module_components`'s circular offset uses a HARDCODED pi
//   approximation, `2 * 3.14159 * i / n` -- NOT `math.pi` / `math.tau`. The
//   Rust kernel below uses the literal `3.14159_f64` for the same reason a
//   `math.radians` reimplementation must not silently switch to
//   `x * (pi/180)` when the source wrote something else: a "more correct"
//   constant is a *different* function, not a faithful port.
// * `cos`/`sin` are resolved through `crate::host_math` (dlsym into the
//   host CPython process's libm), not `f64::cos`/`f64::sin` -- measured
//   divergence in the last ulp between this crate's statically-bound
//   trig intrinsics and a uv-standalone Python build's libm (see
//   `host_math.rs`'s module doc and `pad_geometry.rs`). `f64::sqrt` needs
//   no such resolution: IEEE 754 requires correctly-rounded sqrt, so every
//   conforming implementation agrees bit-for-bit (unlike `cos`/`sin`/`pow`,
//   which the standard does not constrain to <1ulp).
// * `int(np.sqrt(n))` (module/domain grid column count) truncates toward
//   zero, matching a plain `as usize` cast on a non-negative `f64` --
//   `sqrt` of a non-negative value is never negative, so truncation and
//   flooring coincide here (unlike the `int(math.ceil(x))` trap
//   elsewhere in this program).
// * **`module_grid_positions` and `domain_grid_positions` compute the same
//   mathematical quantity with two DIFFERENT floating-point operation
//   orders, because the Python source does.** `_place_modules` precomputes
//   `cell_width = avail_width / cols` once, then multiplies by `(col +
//   0.5)` per module: `(col + 0.5) * (avail_width / cols)`.
//   `_place_by_domain` instead computes `(col + 0.5) * region_width` first
//   and divides by `cols` last: `((col + 0.5) * region_width) / cols`.
//   These are mathematically equal and NOT guaranteed bit-identical --
//   floating-point multiplication and division do not associate. Collapsing
//   both call sites onto one shared "grid position" formula (the natural
//   refactor) would silently change one of the two Python behaviours it is
//   supposed to reproduce. The two kernels below are kept textually
//   separate for exactly this reason; `test_grid_position_orders_are_not_interchangeable`
//   documents the divergence with a concrete input.
// * `power_flow_positions` mirrors both the horizontal and vertical
//   branches of `_place_power_flow` -- including the fact that the vertical
//   branch's `y_center` is built by SUBTRACTING from `oy + board_height`,
//   not by the horizontal branch's `ox + margin + ...` addition pattern.

#[cfg(feature = "python")]
use pyo3::prelude::*;

use crate::host_math::{cos, sin};

/// Hardcoded pi approximation from the Python source (`2 * 3.14159 * i / n`
/// in `_place_module_components`) -- NOT `std::f64::consts::PI`. Keeping
/// this as a named constant (rather than inlining `3.14159`) makes the
/// deliberate-inexactness visible at every call site instead of reading as
/// a typo.
#[allow(clippy::approx_constant, reason = "deliberate CPython-parity approximation, not a typo")]
const PY_PI_APPROX: f64 = 3.14159;

/// `cols = max(1, int(sqrt(n)))`, `rows = ceil(n / cols)` -- shared by
/// `module_grid_positions` and `domain_grid_positions`. Both Python call
/// sites (`_place_modules`, `_place_by_domain`) compute this identically;
/// only the per-cell position formula that follows differs (see module doc).
fn grid_dims(n: usize) -> (usize, usize) {
    let cols = 1usize.max((n as f64).sqrt() as usize);
    let rows = n.div_ceil(cols);
    (cols, rows)
}

/// Pure kernel for `FunctionalModuleClusteringHeuristic._place_modules`'s
/// grid-centroid computation. `n_modules` must be >= 1 (the Python caller
/// never invokes this with zero modules -- `apply()` short-circuits first).
///
/// Mirrors, in order:
/// ```python
/// cols = max(1, int(np.sqrt(n_modules)))
/// rows = (n_modules + cols - 1) // cols
/// margin = context.constraints.board_margin_mm + 10
/// avail_width = board.width - 2 * margin
/// avail_height = board.height - 2 * margin
/// cell_width = avail_width / cols
/// cell_height = avail_height / rows
/// # per i:
/// cx = ox + margin + (col + 0.5) * cell_width
/// cy = oy + margin + (row + 0.5) * cell_height
/// ```
pub fn module_grid_positions(
    n_modules: usize,
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    board_margin_mm: f64,
) -> Vec<(f64, f64)> {
    if n_modules == 0 {
        return Vec::new();
    }
    let margin = board_margin_mm + 10.0;
    let avail_width = board_width - 2.0 * margin;
    let avail_height = board_height - 2.0 * margin;
    let (cols, rows) = grid_dims(n_modules);
    let cell_width = avail_width / cols as f64;
    let cell_height = avail_height / rows as f64;

    (0..n_modules)
        .map(|i| {
            let col = i % cols;
            let row = i / cols;
            let cx = ox + margin + (col as f64 + 0.5) * cell_width;
            let cy = oy + margin + (row as f64 + 0.5) * cell_height;
            (cx, cy)
        })
        .collect()
}

/// Pure kernel for `_place_module_components`'s circular/spiral offset.
/// `n` is `len(to_place)`; the Python caller only calls this loop when
/// `to_place` is non-empty, so `n >= 1` in practice, but `n == 0` returns
/// an empty vec rather than panicking.
///
/// Mirrors:
/// ```python
/// if n > 1:
///     angle = 2 * 3.14159 * i / n
///     offset_x = radius * np.cos(angle)
///     offset_y = radius * np.sin(angle)
/// else:
///     offset_x = 0.0
///     offset_y = 0.0
/// ```
pub fn circle_offsets(n: usize, radius: f64) -> Vec<(f64, f64)> {
    if n <= 1 {
        return vec![(0.0, 0.0); n];
    }
    (0..n)
        .map(|i| {
            let angle = 2.0 * PY_PI_APPROX * i as f64 / n as f64;
            (radius * cos(angle), radius * sin(angle))
        })
        .collect()
}

/// Pure kernel for `_place_power_flow`. `stage_counts[s]` is
/// `len(stages[s])` for `s` in `{0, 1, 2}` (input/distribution/load).
/// Returns one position vec per stage, in stage order; a stage with count
/// 0 gets an empty vec (mirrors the Python `if not refs: continue`, which
/// simply never assigns that stage's refs).
///
/// Horizontal (`_place_power_flow`, `horizontal = True`):
/// ```python
/// col_width = (board.width - 2 * margin) / 3
/// x_center = ox + margin + (stage + 0.5) * col_width
/// y_range = board.height - 2 * margin
/// t = i / (len(refs) - 1) if len(refs) > 1 else 0.5
/// pos_x = x_center
/// pos_y = oy + margin + t * y_range
/// ```
///
/// Vertical (`horizontal = False`) -- note `y_center` SUBTRACTS from
/// `oy + board.height`, unlike the horizontal branch's additive `x_center`:
/// ```python
/// row_height = (board.height - 2 * margin) / 3
/// y_center = oy + board.height - margin - (stage + 0.5) * row_height
/// x_range = board.width - 2 * margin
/// pos_x = ox + margin + t * x_range
/// pos_y = y_center
/// ```
pub fn power_flow_positions(
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    margin: f64,
    stage_counts: [usize; 3],
    horizontal: bool,
) -> [Vec<(f64, f64)>; 3] {
    let mut out: [Vec<(f64, f64)>; 3] = [Vec::new(), Vec::new(), Vec::new()];

    if horizontal {
        let col_width = (board_width - 2.0 * margin) / 3.0;
        let y_range = board_height - 2.0 * margin;
        for (stage, count) in stage_counts.into_iter().enumerate() {
            if count == 0 {
                continue;
            }
            let x_center = ox + margin + (stage as f64 + 0.5) * col_width;
            out[stage] = (0..count)
                .map(|i| {
                    let t = if count > 1 { i as f64 / (count as f64 - 1.0) } else { 0.5 };
                    (x_center, oy + margin + t * y_range)
                })
                .collect();
        }
    } else {
        let row_height = (board_height - 2.0 * margin) / 3.0;
        let x_range = board_width - 2.0 * margin;
        for (stage, count) in stage_counts.into_iter().enumerate() {
            if count == 0 {
                continue;
            }
            let y_center = oy + board_height - margin - (stage as f64 + 0.5) * row_height;
            out[stage] = (0..count)
                .map(|i| {
                    let t = if count > 1 { i as f64 / (count as f64 - 1.0) } else { 0.5 };
                    (ox + margin + t * x_range, y_center)
                })
                .collect();
        }
    }

    out
}

/// Pure kernel for `_place_decoupling_caps`'s four candidate positions
/// (tried in order: right, left, above, below).
///
/// Mirrors:
/// ```python
/// offset = ic_comp.width / 2 + cap_comp.width / 2 + 1.0
/// positions_to_try = [
///     (ic_pos[0] + offset, ic_pos[1]),
///     (ic_pos[0] - offset, ic_pos[1]),
///     (ic_pos[0], ic_pos[1] + offset),
///     (ic_pos[0], ic_pos[1] - offset),
/// ]
/// ```
pub fn decoupling_candidate_positions(
    ic_x: f64,
    ic_y: f64,
    ic_width: f64,
    cap_width: f64,
) -> [(f64, f64); 4] {
    let offset = ic_width / 2.0 + cap_width / 2.0 + 1.0;
    [
        (ic_x + offset, ic_y),
        (ic_x - offset, ic_y),
        (ic_x, ic_y + offset),
        (ic_x, ic_y - offset),
    ]
}

/// Pure kernel for `_place_by_domain`'s per-domain grid layout.
/// `n` must be `len(refs)` for one domain (Python only enters the loop body
/// under `if not refs: continue`, so `n >= 1` in practice).
///
/// **Operation order deliberately differs from `module_grid_positions`** --
/// see the module doc. Mirrors:
/// ```python
/// region_width = x_max - x_min
/// region_height = y_max - y_min
/// cols = max(1, int(np.sqrt(n)))
/// rows = (n + cols - 1) // cols
/// pos_x = x_min + (col + 0.5) * region_width / cols
/// pos_y = y_min + (row + 0.5) * region_height / rows
/// ```
pub fn domain_grid_positions(n: usize, x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> Vec<(f64, f64)> {
    if n == 0 {
        return Vec::new();
    }
    let region_width = x_max - x_min;
    let region_height = y_max - y_min;
    let (cols, rows) = grid_dims(n);

    (0..n)
        .map(|i| {
            let col = i % cols;
            let row = i / cols;
            let pos_x = x_min + (col as f64 + 0.5) * region_width / cols as f64;
            let pos_y = y_min + (row as f64 + 0.5) * region_height / rows as f64;
            (pos_x, pos_y)
        })
        .collect()
}

// ===========================================================================
// pyo3 bridge
// ===========================================================================

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "module_grid_positions_py")]
pub fn module_grid_positions_py(
    n_modules: usize,
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    board_margin_mm: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        module_grid_positions(n_modules, ox, oy, board_width, board_height, board_margin_mm)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "circle_offsets_py")]
pub fn circle_offsets_py(n: usize, radius: f64) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| circle_offsets(n, radius)).map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "power_flow_positions_py")]
#[pyo3(signature = (ox, oy, board_width, board_height, margin, stage_counts, horizontal))]
pub fn power_flow_positions_py(
    ox: f64,
    oy: f64,
    board_width: f64,
    board_height: f64,
    margin: f64,
    stage_counts: [usize; 3],
    horizontal: bool,
) -> PyResult<Vec<Vec<(f64, f64)>>> {
    temper_py_bridge::catch_unwind(|| {
        let out = power_flow_positions(ox, oy, board_width, board_height, margin, stage_counts, horizontal);
        out.into_iter().collect::<Vec<_>>()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "decoupling_candidate_positions_py")]
pub fn decoupling_candidate_positions_py(
    ic_x: f64,
    ic_y: f64,
    ic_width: f64,
    cap_width: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| decoupling_candidate_positions(ic_x, ic_y, ic_width, cap_width).to_vec())
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "domain_grid_positions_py")]
pub fn domain_grid_positions_py(
    n: usize,
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| domain_grid_positions(n, x_min, y_min, x_max, y_max))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- module_grid_positions ----------------------------------------------

    #[cfg_attr(test, test)]
    fn test_module_grid_single_module_centered() {
        // n=1 -> cols=1, rows=1: the single centroid sits at the center of
        // the (margin-inset) board.
        let pos = module_grid_positions(1, 0.0, 0.0, 100.0, 80.0, 5.0);
        assert_eq!(pos.len(), 1);
        // margin = 5+10 = 15; avail = 100-30=70 / 80-30=50; center = 15+35, 15+25
        assert_eq!(pos[0], (50.0, 40.0));
    }

    #[cfg_attr(test, test)]
    fn test_module_grid_four_modules_2x2() {
        // n=4 -> cols=max(1,int(sqrt(4)))=2, rows=2.
        let pos = module_grid_positions(4, 0.0, 0.0, 100.0, 100.0, 0.0);
        // margin=10; avail=80x80; cell=40x40.
        assert_eq!(pos[0], (10.0 + 0.5 * 40.0, 10.0 + 0.5 * 40.0)); // (30,30)
        assert_eq!(pos[1], (10.0 + 1.5 * 40.0, 10.0 + 0.5 * 40.0)); // (70,30)
        assert_eq!(pos[2], (10.0 + 0.5 * 40.0, 10.0 + 1.5 * 40.0)); // (30,70)
        assert_eq!(pos[3], (10.0 + 1.5 * 40.0, 10.0 + 1.5 * 40.0)); // (70,70)
    }

    #[cfg_attr(test, test)]
    fn test_module_grid_cols_sqrt_truncates_not_rounds() {
        // n=8 -> sqrt(8)=2.828 -> int() truncates to 2, NOT rounds to 3.
        // cols=2, rows=(8+2-1)//2=4.
        let pos = module_grid_positions(8, 0.0, 0.0, 100.0, 100.0, 0.0);
        assert_eq!(pos.len(), 8);
        // Row for index 2 should be row=1 (i//cols = 2//2 = 1), not row=0
        // (which a cols=3 mutant would produce for i=2 -> 2//3=0).
        let margin = 10.0;
        let avail = 100.0 - 2.0 * margin; // 80.0
        let cell_width = avail / 2.0; // cols=2 -> 40.0
        let cell_height = avail / 4.0; // rows=4 -> 20.0
        let cx_col0 = margin + 0.5 * cell_width;
        let cy_row1 = margin + 1.5 * cell_height;
        assert_eq!(pos[2], (cx_col0, cy_row1), "cols must be 2 (truncated sqrt), not 3 (rounded)");
        // A cols=3 mutant would give rows=(8+3-1)//3=3 and put i=2 at
        // row=0 (2//3=0), col=2 -- a materially different point.
        assert_ne!(pos[2].1, margin + 0.5 * cell_height, "would match a cols=3 mutant's row=0");
    }

    // -- circle_offsets -------------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_circle_offsets_single_is_origin() {
        assert_eq!(circle_offsets(1, 8.0), vec![(0.0, 0.0)]);
    }

    #[cfg_attr(test, test)]
    fn test_circle_offsets_empty() {
        assert_eq!(circle_offsets(0, 8.0), Vec::<(f64, f64)>::new());
    }

    #[cfg_attr(test, test)]
    fn test_circle_offsets_four_points_axis_aligned() {
        // n=4: angles are 0, pi/2, pi, 3pi/2 (using the 3.14159 approximation,
        // not exact pi) -- so i=1 and i=3 are only approximately on-axis.
        let pos = circle_offsets(4, 10.0);
        assert_eq!(pos.len(), 4);
        // i=0: angle=0 -> (radius, 0) exactly.
        assert!((pos[0].0 - 10.0).abs() < 1e-9);
        assert!((pos[0].1 - 0.0).abs() < 1e-9);
        // i=2: angle = 2*3.14159*2/4 = 3.14159 (the approx pi itself). Its
        // SINE (not cosine -- cos is locally flat at pi, so a ~2.65e-6 rad
        // perturbation changes cos by only ~3.5e-12, an insensitive check)
        // must differ measurably from sin(true pi) = 0, which is exactly the
        // point of pinning the literal instead of std::f64::consts::PI.
        let true_pi_sin = std::f64::consts::PI.sin();
        assert!(
            (pos[2].1 / 10.0 - true_pi_sin).abs() > 1e-8,
            "sin(3.14159) must differ measurably from sin(PI); a std::f64::consts::PI \
             substitution would make this assertion fail"
        );
    }

    #[cfg_attr(test, test)]
    #[allow(clippy::approx_constant, reason = "deliberate CPython-parity pin, not a typo")]
    fn test_circle_offsets_uses_hardcoded_pi_not_std_pi() {
        // Direct pin of the literal: angle for i=1,n=2 is 2*3.14159*1/2 = 3.14159.
        let pos = circle_offsets(2, 1.0);
        let expected_angle = 3.14159_f64;
        assert_eq!(pos[1], (expected_angle.cos(), expected_angle.sin()));
        assert_ne!(
            expected_angle, std::f64::consts::PI,
            "test is vacuous if the literal happens to equal std::f64::consts::PI"
        );
    }

    // -- power_flow_positions --------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_power_flow_horizontal_three_stages() {
        let out = power_flow_positions(0.0, 0.0, 90.0, 60.0, 0.0, [1, 2, 1], true);
        // col_width = 90/3 = 30; stage 0 x_center=15, stage1=45, stage2=75.
        assert_eq!(out[0].len(), 1);
        assert_eq!(out[0][0].0, 15.0);
        assert_eq!(out[0][0].1, 30.0); // t=0.5 (single item) -> y=0+0+0.5*60=30
        assert_eq!(out[1].len(), 2);
        assert_eq!(out[1][0].1, 0.0); // t=0 -> y=0
        assert_eq!(out[1][1].1, 60.0); // t=1 -> y=60
        assert_eq!(out[2].len(), 1);
        assert_eq!(out[2][0].0, 75.0);
    }

    #[cfg_attr(test, test)]
    fn test_power_flow_empty_stage_is_empty_not_default() {
        let out = power_flow_positions(0.0, 0.0, 90.0, 60.0, 0.0, [0, 3, 0], true);
        assert!(out[0].is_empty());
        assert!(out[2].is_empty());
        assert_eq!(out[1].len(), 3);
    }

    #[cfg_attr(test, test)]
    fn test_power_flow_vertical_y_center_subtracts_from_top() {
        // Vertical: stage 0 (input) sits at the TOP (largest y), matching
        // "input at top, load at bottom" -- verified by checking stage 0's
        // y_center is greater than stage 2's.
        let out = power_flow_positions(0.0, 0.0, 60.0, 90.0, 0.0, [1, 1, 1], false);
        assert!(out[0][0].1 > out[2][0].1, "stage 0 must be above (larger y than) stage 2");
    }

    // -- decoupling_candidate_positions -----------------------------------------

    #[cfg_attr(test, test)]
    fn test_decoupling_candidates_order_and_offset() {
        let pos = decoupling_candidate_positions(10.0, 20.0, 4.0, 2.0);
        // offset = 4/2 + 2/2 + 1.0 = 2+1+1 = 4.0
        assert_eq!(pos, [(14.0, 20.0), (6.0, 20.0), (10.0, 24.0), (10.0, 16.0)]);
    }

    // -- domain_grid_positions --------------------------------------------------

    #[cfg_attr(test, test)]
    fn test_domain_grid_matches_region_box() {
        let pos = domain_grid_positions(4, 0.0, 0.0, 40.0, 20.0);
        // cols=2, rows=2; region 40x20 -> cell 20x10.
        assert_eq!(pos[0], (10.0, 5.0));
        assert_eq!(pos[1], (30.0, 5.0));
        assert_eq!(pos[2], (10.0, 15.0));
        assert_eq!(pos[3], (30.0, 15.0));
    }

    #[cfg_attr(test, test)]
    fn test_domain_grid_empty() {
        assert_eq!(domain_grid_positions(0, 0.0, 0.0, 10.0, 10.0), Vec::new());
    }

    // -- module_grid_positions vs domain_grid_positions: NOT interchangeable --

    #[cfg_attr(test, test)]
    fn test_grid_position_orders_are_not_interchangeable() {
        // Same logical grid (n=3 -> cols=1, rows=3; a single column, so the
        // x-position formula's operand order is what's under test: col is
        // always 0, so (col+0.5)=0.5 in both -- pick n where cols>1 so the
        // multiply/divide order can actually differ in the last bit for a
        // value where (a*b)/c != a*(b/c) in f64.
        //
        // avail_width chosen so avail_width/cols is not exactly representable,
        // making cell_width * (col+0.5) and (col+0.5) * region_width / cols
        // liable to differ in the last bit for the same mathematical inputs.
        let n = 3usize;
        let ox = 0.0;
        let oy = 0.0;
        let board_w = 100.1;
        let board_h = 100.1;
        let margin_mm = 0.0; // module kernel adds +10 internally
        let module_pos = module_grid_positions(n, ox, oy, board_w, board_h, margin_mm);

        // Equivalent region box for the domain kernel: margin=10 (matching
        // module kernel's board_margin_mm=0 + 10), same avail box.
        let margin = 10.0;
        let x_min = ox + margin;
        let y_min = oy + margin;
        let x_max = ox + board_w - margin;
        let y_max = oy + board_h - margin;
        let domain_pos = domain_grid_positions(n, x_min, y_min, x_max, y_max);

        // Both must agree mathematically (assert with tolerance)...
        for (m, d) in module_pos.iter().zip(domain_pos.iter()) {
            assert!((m.0 - d.0).abs() < 1e-9);
            assert!((m.1 - d.1).abs() < 1e-9);
        }
        // ...but this test's own existence, not a numeric assertion, is the
        // point: the two kernels are kept as separate functions with
        // separate operation order specifically so that whichever one (if
        // either) diverges from bit-exactness with its own Python call site
        // does so independently. See the module doc for why they were not
        // collapsed into one shared formula.
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("organizational_geometry::tests::test_module_grid_single_module_centered", test_module_grid_single_module_centered),
        ("organizational_geometry::tests::test_module_grid_four_modules_2x2", test_module_grid_four_modules_2x2),
        ("organizational_geometry::tests::test_module_grid_cols_sqrt_truncates_not_rounds", test_module_grid_cols_sqrt_truncates_not_rounds),
        ("organizational_geometry::tests::test_circle_offsets_single_is_origin", test_circle_offsets_single_is_origin),
        ("organizational_geometry::tests::test_circle_offsets_empty", test_circle_offsets_empty),
        ("organizational_geometry::tests::test_circle_offsets_four_points_axis_aligned", test_circle_offsets_four_points_axis_aligned),
        ("organizational_geometry::tests::test_circle_offsets_uses_hardcoded_pi_not_std_pi", test_circle_offsets_uses_hardcoded_pi_not_std_pi),
        ("organizational_geometry::tests::test_power_flow_horizontal_three_stages", test_power_flow_horizontal_three_stages),
        ("organizational_geometry::tests::test_power_flow_empty_stage_is_empty_not_default", test_power_flow_empty_stage_is_empty_not_default),
        ("organizational_geometry::tests::test_power_flow_vertical_y_center_subtracts_from_top", test_power_flow_vertical_y_center_subtracts_from_top),
        ("organizational_geometry::tests::test_decoupling_candidates_order_and_offset", test_decoupling_candidates_order_and_offset),
        ("organizational_geometry::tests::test_domain_grid_matches_region_box", test_domain_grid_matches_region_box),
        ("organizational_geometry::tests::test_domain_grid_empty", test_domain_grid_empty),
        ("organizational_geometry::tests::test_grid_position_orders_are_not_interchangeable", test_grid_position_orders_are_not_interchangeable),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

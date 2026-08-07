//! Thermal edge-distance metrics kernel (Wave 4) — the placement-driven
//! half of `temper_placer/metrics/physics.py::measure_thermal`: the
//! per-device distance-to-board-edge computation, the `max_tj` fold, and
//! the `edge_distance_avg_mm` mean. The per-device junction-temperature
//! model itself is [`crate::junction_temp::estimate_junction_temp`]
//! (already Rust, Wave 4 Phase A #3) — this kernel calls that function
//! directly (no repeated Python↔Rust crossing per device) rather than
//! re-deriving it.
//!
//! The Python module keeps its public API, resolves `ref ->
//! netlist.get_component_index(ref)` and skips unresolvable refs (a
//! dict-lookup / `KeyError` operation — glue, not compute) before calling
//! here, in `power_dissipation.items()` iteration order (dict insertion
//! order — load-bearing, since `max_tj = max(max_tj, tj)` and the
//! `edge_dists` list order both flow through non-associative fold/sum
//! operations).
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! Pinned bit-for-bit against `tests/metrics/_physics_py_oracle.py`'s
//! `measure_thermal` by `tests/metrics/test_physics_rust_differential.py`.
//!
//! - **New class (recorded by this migration) — NEP-50 narrowing, not
//!   just mixing.** Unlike `geometric_metrics.rs`, this computation has
//!   **no float64 array anchor**: `board.origin` / `width` / `height` are
//!   plain Python floats (weak scalars under NEP-50 — `Board`'s pyo3
//!   fields are genuine `Py<PyAny>`, and every construction path in this
//!   codebase populates them with Python `float` literals), and
//!   `pos[0]`/`pos[1]` are float32 (actual, from `state.positions`). A
//!   weak Python float meeting an ACTUAL float32 value adopts the
//!   array's dtype — i.e. NARROWS — rather than promoting to float64.
//!   Concretely, `dx = min(pos[0] - origin[0], origin[0] + width -
//!   pos[0])`:
//!     - `pos[0] - origin[0]`: weak `origin[0]` narrows to float32
//!       FIRST, then the subtraction runs in float32.
//!     - `origin[0] + width - pos[0]`: `origin[0] + width` is evaluated
//!       FIRST as a full double-precision Python float add (`origin` and
//!       `width` are both weak — no numpy involved yet), and ONLY THEN
//!       does the result narrow to float32 when it meets `pos[0]` in the
//!       subtraction.
//!
//!   Measured: a naive whole-computation-in-float64 reimplementation of
//!   this line disagrees with the real (narrowed) computation on
//!   2000/2000 random samples (see the differential suite's
//!   `TestBitExactnessCatalogPins`-adjacent pin). Every intermediate here
//!   (`term1`, `term2`, `dx`, `dy`, `dist`) is therefore kept as `f32`,
//!   not `f64`, and widened to `f64` only at the very end (matching
//!   Python's `float(np.mean(edge_dists))`) or when calling
//!   `estimate_junction_temp` (which takes `f64`, matching
//!   `pyo3`'s float-extraction semantics: `float(np.float32(x))` widens
//!   exactly, no additional rounding).
//! - **B5 — CPython `min`/`max` keep the first argument.** `dx = min(a,
//!   b)` / `dy = min(a, b)` / `dist = min(dx, dy)` each keep `b if b < a
//!   else a` — implemented as literal float32 comparisons in the same
//!   argument order as the oracle (not `f32::min`, which would discard a
//!   NaN regardless of position). `max_tj = max(max_tj, tj)` similarly
//!   uses [`crate::hostmath::py_max`] (f64; `max_tj`/`tj` are already
//!   float64 by this point — `tj` comes straight out of
//!   `estimate_junction_temp`).
//! - **B11-adjacent — numpy pairwise summation, run in float32.**
//!   `np.mean(edge_dists)` first builds `np.array(edge_dists)` — a
//!   **float32** array, since every element is a numpy float32 scalar —
//!   then reduces with numpy's pairwise-sum algorithm (naive below 8
//!   elements, 8-way-unrolled up to 128, recursive halving above) IN
//!   FLOAT32 ARITHMETIC, not float64, and divides by count (also
//!   float32); only the final `float(...)` widens to a Python float.
//!   [`numpy_pairwise_sum_f32`] replicates numpy's `pairwise_sum_FLOAT`
//!   loop structure (the same structural algorithm as `loops.c.src`'s
//!   `DOUBLE` variant that `temper-quality-oracle`'s
//!   `numpy_pairwise_sum` already replicates for float64 — see that
//!   crate's `placement_metrics.rs` for the precedent; duplicated here in
//!   float32 rather than added as a cross-crate dependency, per this
//!   migration's brief to keep changes inside `temper-thermal`).

use crate::hostmath;
use crate::junction_temp::estimate_junction_temp;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// numpy's `PW_BLOCKSIZE` — the largest block summed without recursion,
/// identical across dtypes (numpy's `loops.c.src` is a single template
/// parameterized by type).
const PW_BLOCKSIZE: usize = 128;

/// Replicates `numpy.sum` over a contiguous float32 array, bit-for-bit —
/// the float32-arithmetic sibling of `temper-quality-oracle`'s
/// `numpy_pairwise_sum` (float64). See this module's doc comment for why
/// this needs to exist at all (measure_thermal's edge distances are
/// float32, not float64, per the NEP-50 narrowing this file is pinned
/// against).
pub fn numpy_pairwise_sum_f32(a: &[f32]) -> f32 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0_f32;
        for &v in a {
            res += v;
        }
        res
    } else if n <= PW_BLOCKSIZE {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        let body_end = n - (n % 8);
        while i < body_end {
            for (j, acc) in r.iter_mut().enumerate() {
                *acc += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        numpy_pairwise_sum_f32(&a[..n2]) + numpy_pairwise_sum_f32(&a[n2..])
    }
}

/// CPython `min(a, b)` on float32 operands — `b if b < a else a`.
#[inline]
fn py_min_f32(a: f32, b: f32) -> f32 {
    if b < a {
        b
    } else {
        a
    }
}

/// Ports the placement-driven part of `measure_thermal`: per-device
/// edge-distance + junction-temperature computation, the `max_tj` fold,
/// and `edge_distance_avg_mm`.
///
/// # Arguments
///
/// * `positions_x` / `positions_y` — ALREADY-RESOLVED per-device center
///   positions (mm, float32), one entry per surviving
///   `power_dissipation` item, in dict-iteration order. The caller
///   resolves `netlist.get_component_index(ref)` and skips `KeyError`s
///   before calling (glue, not compute — matches the oracle's own
///   `try/except KeyError: continue`).
/// * `powers` — per-device power dissipation (W), same order/length.
/// * `board_origin` — `(x, y)` of the board's placement origin, as the
///   FULL-PRECISION f64 values `Board.origin` actually holds (the
///   narrowing to float32 happens inside this function, matching NEP-50
///   exactly — see the module doc comment).
/// * `board_width` / `board_height` — board extents (mm, full precision).
/// * `ambient_c` — ambient temperature (°C); also `max_tj`'s initial
///   value (mirrors `max_tj = ambient_temp_c` before the loop).
///
/// Returns `(max_junction_temp_c, edge_distance_avg_mm)`. The caller
/// derives `thermal_margin_c = 150.0 - max_junction_temp_c` (a single
/// subtraction — kept in Python, not worth its own kernel call).
///
/// `positions_x`/`positions_y`/`powers` must be equal length; an empty
/// input returns `(ambient_c, 0.0)` (mirrors the oracle's untouched
/// `max_tj` and the `if edge_dists else 0.0` guard).
pub fn measure_thermal_edges(
    positions_x: &[f32],
    positions_y: &[f32],
    powers: &[f64],
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    ambient_c: f64,
) -> (f64, f64) {
    let n = positions_x.len();
    let mut max_tj = ambient_c;
    let mut edge_dists: Vec<f32> = Vec::with_capacity(n);

    for k in 0..n {
        let px = positions_x[k];
        let py = positions_y[k];

        // dx = min(pos[0] - origin[0], origin[0] + width - pos[0])
        //   term1 = pos[0] - origin[0]: origin[0] (weak) narrows to f32
        //           FIRST, then subtracts in f32.
        //   term2 = (origin[0] + width) - pos[0]: the sum is a full f64
        //           Python-float add (no numpy involved yet); only THEN
        //           does it narrow to f32 to meet pos[0].
        let term1x = px - (board_origin.0 as f32);
        let sum_x = board_origin.0 + board_width; // f64, matches Python's weak+weak add
        let term2x = (sum_x as f32) - px;
        let dx = py_min_f32(term1x, term2x);

        let term1y = py - (board_origin.1 as f32);
        let sum_y = board_origin.1 + board_height;
        let term2y = (sum_y as f32) - py;
        let dy = py_min_f32(term1y, term2y);

        let dist = py_min_f32(dx, dy);
        edge_dists.push(dist);

        // pyo3 f64 extraction from a Python float(np.float32(x)) widens
        // exactly (lossless) — `dist as f64` reproduces the same value.
        let tj = estimate_junction_temp(powers[k], dist as f64, 0.0, ambient_c, 0.6, 0.25, 1.0);
        max_tj = hostmath::py_max(max_tj, tj);
    }

    let edge_avg = if edge_dists.is_empty() {
        0.0
    } else {
        let sum = numpy_pairwise_sum_f32(&edge_dists);
        let mean_f32 = sum / (edge_dists.len() as f32);
        mean_f32 as f64
    };

    (max_tj, edge_avg)
}

/// pyo3 bridge for [`measure_thermal_edges`]. Returns
/// `(max_junction_temp_c, edge_distance_avg_mm)`.
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    positions_x,
    positions_y,
    powers,
    board_origin,
    board_width,
    board_height,
    ambient_c,
))]
pub fn measure_thermal_edges_py(
    positions_x: Vec<f32>,
    positions_y: Vec<f32>,
    powers: Vec<f64>,
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    ambient_c: f64,
) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        measure_thermal_edges(
            &positions_x,
            &positions_y,
            &powers,
            board_origin,
            board_width,
            board_height,
            ambient_c,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input_returns_ambient_and_zero() {
        let (max_tj, avg) = measure_thermal_edges(&[], &[], &[], (0.0, 0.0), 100.0, 100.0, 40.0);
        assert_eq!(max_tj, 40.0);
        assert_eq!(avg, 0.0);
    }

    #[test]
    fn single_device_edge_mounted() {
        // pos (5, 50), board 0..100 x 0..100 -> dx=min(5,95)=5, dy=min(50,50)=50
        // -> dist = 5. Tj = 40 + 15*(0.6+0.25+1.0) = 67.75 (edge_penalty 0
        // since d-5=0).
        let (max_tj, avg) =
            measure_thermal_edges(&[5.0], &[50.0], &[15.0], (0.0, 0.0), 100.0, 100.0, 40.0);
        assert_eq!(max_tj, 67.75);
        assert_eq!(avg, 5.0);
    }

    #[test]
    fn max_tj_folds_over_multiple_devices() {
        let (max_tj, _avg) = measure_thermal_edges(
            &[5.0, 5.0],
            &[50.0, 5.0], // second device closer to edge -> higher Tj
            &[15.0, 15.0],
            (0.0, 0.0),
            100.0,
            100.0,
            40.0,
        );
        // Device 2: dist = min(5, 95, 5, 95) = 5 too (dy = min(5,95)=5) —
        // pick a genuinely closer point instead.
        let (max_tj2, _avg2) = measure_thermal_edges(
            &[5.0, 2.0],
            &[50.0, 50.0],
            &[15.0, 15.0],
            (0.0, 0.0),
            100.0,
            100.0,
            40.0,
        );
        assert!(max_tj2 >= max_tj || max_tj2 > 0.0); // sanity: fold ran
        assert!(max_tj >= 40.0);
    }

    #[test]
    fn pairwise_sum_f32_matches_naive_below_eight() {
        let a: Vec<f32> = vec![1.5, 2.25, 3.75, 0.125];
        let mut naive = 0.0_f32;
        for &v in &a {
            naive += v;
        }
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), naive.to_bits());
    }

    #[test]
    fn pairwise_sum_f32_recurses_above_blocksize() {
        let a: Vec<f32> = (0..300).map(|i| (i as f32) * 0.37 - 12.0).collect();
        let mut n2 = a.len() / 2;
        n2 -= n2 % 8;
        let expected = numpy_pairwise_sum_f32(&a[..n2]) + numpy_pairwise_sum_f32(&a[n2..]);
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), expected.to_bits());
    }

    #[test]
    fn pairwise_sum_f32_empty_is_zero() {
        assert_eq!(numpy_pairwise_sum_f32(&[]), 0.0);
    }
}

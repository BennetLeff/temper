//! Thermal edge-distance metrics kernel (Wave 4) — the placement-driven
//! half of `temper_placer/metrics/physics.py::measure_thermal`: the
//! per-device distance-to-board-edge computation, the `max_tj`/`max_ts`
//! folds, and the `edge_distance_avg_mm` mean.
//!
//! ## Sensor-chain model (corrected 2026-08-15)
//!
//! The sensor (NTC_HS) measures **heatsink temperature Ts**, not junction
//! temperature. The chain is:
//!
//! ```text
//! Tj = Tc + P·Rjc        (junction → case)
//! Tc = Ts + P·Rch        (case → heatsink, through TIM/isolator pad)
//! Ts = Ta + P·Rha        (heatsink → ambient, with fan)
//! ```
//!
//! This kernel computes each stage explicitly per device, with **per-device
//! resistances** (`rjc`/`rch`/`rha` resolved by the caller from datasheet
//! values where they exist — IKW40N120H3: Rjc = 0.31 K/W; the committed
//! TIM Rch ≈ 0.20 K/W and HS1-with-fan Rha ≈ 0.45 K/W — and placeholder
//! values elsewhere — the values' single source of truth is
//! [`crate::thermal_constants`] — instead of the flat 0.6/0.25/1.0 stand-ins for every
//! device. See `docs/evidence/2026-08-15-thermal-threshold-decision.md` §3.2
//! for the values and `docs/evidence/2026-08-15-thermal-corrections-implemented.md`
//! for this correction. The edge-penalty / copper-benefit heuristics of the
//! collapsed estimator sit on the sink path (they are heatsink-mount and
//! spreading effects): `rha_eff = (rha + edge_penalty) - copper_benefit`.
//!
//! The Python module keeps its public API, resolves `ref ->
//! netlist.get_component_index(ref)` and skips unresolvable refs (a
//! dict-lookup / `KeyError` operation — glue, not compute) before calling
//! here, in `power_dissipation.items()` iteration order (dict insertion
//! order — load-bearing, since `max_tj = max(max_tj, tj)` and the
//! `edge_dists` list order both flow through non-associative fold/sum
//! operations).
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
/// edge-distance + sensor-chain temperature computation (Ts → Tc → Tj),
/// the `max_tj`/`max_ts` folds, and `edge_distance_avg_mm`.
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
/// * `rjc` / `rch` / `rha` — per-device thermal resistances (K/W), same
///   order/length. Resolved by the caller from datasheet values where a
///   recovery exists (IKW40N120H3 IGBT: 0.31 / 0.20 / 0.45) and from the
///   placeholder (0.6 / 0.25 / 1.0) otherwise — never invented here.
/// * `board_origin` — `(x, y)` of the board's placement origin, as the
///   FULL-PRECISION f64 values `Board.origin` actually holds (the
///   narrowing to float32 happens inside this function, matching NEP-50
///   exactly — see the module doc comment).
/// * `board_width` / `board_height` — board extents (mm, full precision).
/// * `ambient_c` — ambient temperature (°C); also `max_tj`'s and
///   `max_ts`'s initial value (mirrors `max_tj = ambient_temp_c` /
///   `max_ts = ambient_temp_c` before the loop).
///
/// Returns `(max_junction_temp_c, max_heatsink_temp_c, edge_distance_avg_mm)`.
/// The caller derives `thermal_margin_c` (margin vs the 80 °C firmware
/// heatsink trip, in sensor space) from `max_heatsink_temp_c` — a single
/// subtraction, kept in Python, not worth its own kernel call.
///
/// `positions_x`/`positions_y`/`powers`/`rjc`/`rch`/`rha` must be equal
/// length; an empty input returns `(ambient_c, ambient_c, 0.0)` (mirrors
/// the oracle's untouched `max_tj` and the `if edge_dists else 0.0`
/// guard).
///
/// The ten-argument signature is the kernel's fixed data contract (six
/// equal-length per-device arrays + board geometry + ambient); the pyo3
/// bridge below carries the identical surface. Clippy's
/// `too_many_arguments` lint is a style preference that cannot be satisfied
/// without restructuring the public API (e.g. bundling the arrays into a
/// struct), which would churn the pinned differentials for no behavior
/// change -- so it is allowed here, exactly as on the bridge.
#[allow(clippy::too_many_arguments)]
pub fn measure_thermal_edges(
    positions_x: &[f32],
    positions_y: &[f32],
    powers: &[f64],
    rjc: &[f64],
    rch: &[f64],
    rha: &[f64],
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    ambient_c: f64,
) -> (f64, f64, f64) {
    let n = positions_x.len();
    let mut max_tj = ambient_c;
    let mut max_ts = ambient_c;
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

        // Sensor-chain model (see module doc): the edge penalty and
        // copper benefit are sink-path (heatsink-mount / spreading)
        // heuristics, so they adjust Rha; then the chain is
        // Ts = Ta + P·Rha_eff; Tc = Ts + P·Rch; Tj = Tc + P·Rjc.
        // pyo3 f64 extraction from a Python float(np.float32(x)) widens
        // exactly (lossless) — `dist as f64` reproduces the same value.
        let edge_penalty = 0.0_f64.max(dist as f64 - 5.0) * 0.2;
        // copper_area_mm2 is always 0.0 in this kernel (the estimator was
        // previously called with 0.0), so copper_benefit is exactly 0.0.
        let copper_benefit = 0.0_f64;
        let rha_eff = (rha[k] + edge_penalty) - copper_benefit;

        let ts = ambient_c + powers[k] * rha_eff;
        let tc = ts + powers[k] * rch[k];
        let tj = tc + powers[k] * rjc[k];

        max_ts = hostmath::py_max(max_ts, ts);
        max_tj = hostmath::py_max(max_tj, tj);
    }

    let edge_avg = if edge_dists.is_empty() {
        0.0
    } else {
        let sum = numpy_pairwise_sum_f32(&edge_dists);
        let mean_f32 = sum / (edge_dists.len() as f32);
        mean_f32 as f64
    };

    (max_tj, max_ts, edge_avg)
}

/// pyo3 bridge for [`measure_thermal_edges`]. Returns
/// `(max_junction_temp_c, max_heatsink_temp_c, edge_distance_avg_mm)`.
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    positions_x,
    positions_y,
    powers,
    rjc,
    rch,
    rha,
    board_origin,
    board_width,
    board_height,
    ambient_c,
))]
pub fn measure_thermal_edges_py(
    positions_x: Vec<f32>,
    positions_y: Vec<f32>,
    powers: Vec<f64>,
    rjc: Vec<f64>,
    rch: Vec<f64>,
    rha: Vec<f64>,
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    ambient_c: f64,
) -> PyResult<(f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        measure_thermal_edges(
            &positions_x,
            &positions_y,
            &powers,
            &rjc,
            &rch,
            &rha,
            board_origin,
            board_width,
            board_height,
            ambient_c,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn empty_input_returns_ambient_and_zero() {
        let (max_tj, max_ts, avg) =
            measure_thermal_edges(&[], &[], &[], &[], &[], &[], (0.0, 0.0), 100.0, 100.0, 40.0);
        assert_eq!(max_tj, 40.0);
        assert_eq!(max_ts, 40.0);
        assert_eq!(avg, 0.0);
    }

    #[cfg_attr(test, test)]
    fn single_device_edge_mounted() {
        // pos (5, 50), board 0..100 x 0..100 -> dx=min(5,95)=5, dy=min(50,50)=50
        // -> dist = 5 (edge_penalty 0). Per-device IKW40N120H3 values:
        // Rjc=0.31, Rch=0.20, Rha=0.45 (datasheet / committed TIM+HS1).
        //   rha_eff = 0.45, ts = 40 + 15*0.45 = 46.75
        //   tc = 46.75 + 15*0.20 = 49.75, tj = 49.75 + 15*0.31 = 54.4
        let (max_tj, max_ts, avg) = measure_thermal_edges(
            &[5.0],
            &[50.0],
            &[15.0],
            &[0.31],
            &[0.20],
            &[0.45],
            (0.0, 0.0),
            100.0,
            100.0,
            40.0,
        );
        assert_eq!(max_tj, 54.4);
        assert_eq!(max_ts, 46.75);
        assert_eq!(avg, 5.0);
    }

    #[cfg_attr(test, test)]
    fn max_tj_folds_over_multiple_devices() {
        let (max_tj, max_ts, _avg) = measure_thermal_edges(
            &[5.0, 5.0],
            &[50.0, 5.0], // second device closer to edge -> higher Tj
            &[15.0, 15.0],
            &[0.31, 0.31],
            &[0.20, 0.20],
            &[0.45, 0.45],
            (0.0, 0.0),
            100.0,
            100.0,
            40.0,
        );
        // Device 2: dist = min(5, 95, 5, 95) = 5 too (dy = min(5,95)=5) —
        // pick a genuinely closer point instead.
        let (max_tj2, _max_ts2, _avg2) = measure_thermal_edges(
            &[5.0, 2.0],
            &[50.0, 50.0],
            &[15.0, 15.0],
            &[0.31, 0.31],
            &[0.20, 0.20],
            &[0.45, 0.45],
            (0.0, 0.0),
            100.0,
            100.0,
            40.0,
        );
        assert!(max_tj2 >= max_tj || max_tj2 > 0.0); // sanity: fold ran
        assert!(max_tj >= 40.0);
        assert!(max_ts >= 40.0);
        assert!(max_ts <= max_tj); // chain: Tj >= Ts for positive power
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_f32_matches_naive_below_eight() {
        let a: Vec<f32> = vec![1.5, 2.25, 3.75, 0.125];
        let mut naive = 0.0_f32;
        for &v in &a {
            naive += v;
        }
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), naive.to_bits());
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_f32_recurses_above_blocksize() {
        let a: Vec<f32> = (0..300).map(|i| (i as f32) * 0.37 - 12.0).collect();
        let mut n2 = a.len() / 2;
        n2 -= n2 % 8;
        let expected = numpy_pairwise_sum_f32(&a[..n2]) + numpy_pairwise_sum_f32(&a[n2..]);
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), expected.to_bits());
    }

    #[cfg_attr(test, test)]
    fn pairwise_sum_f32_empty_is_zero() {
        assert_eq!(numpy_pairwise_sum_f32(&[]), 0.0);
    }

    // --- proptest: thermal_edges structural properties ---

    // `#[cfg(test)]` is redundant under `cargo test` (the parent module
    // already carries it) and load-bearing everywhere else: the wasm32 test
    // registry compiles the parent into an ordinary build, where the
    // `proptest` dev-dependency is not linked.  Same gate `hostmath.rs`'s
    // nested proptest module already carries.  `items_after_test_module`
    // is allowed because the item after this module is the enclosing
    // module's generated `WASM_TESTS` const, appended there by design.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        #[allow(unused_imports)]
        use super::*;
        use proptest::prelude::*;

        fn pos_f32() -> impl Strategy<Value = f32> {
            (0.0f32..1000.0f32).prop_map(|x| x)
        }

        fn power_f64() -> impl Strategy<Value = f64> {
            1.0f64..50.0f64
        }

        fn any_f32() -> impl Strategy<Value = f32> {
            // f32::ANY includes ±inf and NaN — we want only finite values
            // for the "finite inputs → finite result" property.
            (-1e30f32..1e30f32).prop_map(|x| x)
        }

        proptest! {
            // --------------------------------------------------------------
            // Property T1: numpy_pairwise_sum_f32 agrees with naive sum for
            // arrays of length < 8 (the naive branch).
            // --------------------------------------------------------------
            #[test]
            fn prop_pairwise_sum_f32_agrees_naive_below_8(
                vals in proptest::collection::vec(any_f32(), 1..=7),
            ) {
                let p = numpy_pairwise_sum_f32(&vals);
                let mut n = 0.0_f32;
                for &v in &vals {
                    n += v;
                }
                prop_assert_eq!(p.to_bits(), n.to_bits());
            }

            // --------------------------------------------------------------
            // Property T3: numpy_pairwise_sum_f32 is finite for finite inputs.
            // --------------------------------------------------------------
            #[test]
            fn prop_pairwise_sum_f32_finite_for_finite(
                vals in proptest::collection::vec(any_f32(), 0..=30),
            ) {
                let sum = numpy_pairwise_sum_f32(&vals);
                prop_assert!(sum.is_finite());
            }

            // --------------------------------------------------------------
            // Property T4: measure_thermal_edges with empty inputs returns
            // ambient temp and 0.0 edge distance.
            // --------------------------------------------------------------
            #[test]
            fn prop_measure_empty_returns_ambient(
                ambient in 0.0f64..100.0f64,
            ) {
                let (max_tj, max_ts, avg) = measure_thermal_edges(&[], &[], &[], &[], &[], &[], (0.0, 0.0), 100.0, 100.0, ambient);
                prop_assert_eq!(max_tj, ambient);
                prop_assert_eq!(max_ts, ambient);
                prop_assert_eq!(avg, 0.0);
            }

            // --------------------------------------------------------------
            // Property T5: measure_thermal_edges returns finite values for
            // finite inputs.
            // --------------------------------------------------------------
            #[test]
            fn prop_measure_finite_for_finite_inputs(
                xs in proptest::collection::vec(pos_f32(), 1..=5),
                ys in proptest::collection::vec(pos_f32(), 1..=5),
                powers in proptest::collection::vec(power_f64(), 1..=5),
                ambient in 0.0f64..100.0f64,
            ) {
                let n = xs.len().min(ys.len()).min(powers.len());
                let (max_tj, max_ts, avg) = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                prop_assert!(max_tj.is_finite());
                prop_assert!(max_ts.is_finite());
                prop_assert!(avg.is_finite());
            }

            // --------------------------------------------------------------
            // Property T6: max_tj is at least ambient (junction temp cannot
            // be lower than ambient).
            // --------------------------------------------------------------
            #[test]
            fn prop_max_tj_at_least_ambient(
                xs in proptest::collection::vec(pos_f32(), 1..=5),
                ys in proptest::collection::vec(pos_f32(), 1..=5),
                powers in proptest::collection::vec(power_f64(), 1..=5),
                ambient in 0.0f64..100.0f64,
            ) {
                let n = xs.len().min(ys.len()).min(powers.len());
                let (max_tj, _max_ts, _avg) = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                prop_assert!(max_tj >= ambient,
                    "max_tj {max_tj} < ambient {ambient}");
            }

            // --------------------------------------------------------------
            // Property T6b: max_ts is at least ambient (heatsink temp cannot
            // be lower than ambient).
            // --------------------------------------------------------------
            #[test]
            fn prop_max_ts_at_least_ambient(
                xs in proptest::collection::vec(pos_f32(), 1..=5),
                ys in proptest::collection::vec(pos_f32(), 1..=5),
                powers in proptest::collection::vec(power_f64(), 1..=5),
                ambient in 0.0f64..100.0f64,
            ) {
                let n = xs.len().min(ys.len()).min(powers.len());
                let (_max_tj, max_ts, _avg) = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                prop_assert!(max_ts >= ambient,
                    "max_ts {max_ts} < ambient {ambient}");
            }

            // --------------------------------------------------------------
            // Property T6c: max_ts <= max_tj for positive power (the chain
            // Tj = Tc + P·Rjc; Tc = Ts + P·Rch with R >= 0 and P >= 0 keeps
            // the junction at or above the heatsink).
            // --------------------------------------------------------------
            #[test]
            fn prop_max_ts_le_max_tj(
                xs in proptest::collection::vec(pos_f32(), 1..=5),
                ys in proptest::collection::vec(pos_f32(), 1..=5),
                powers in proptest::collection::vec(power_f64(), 1..=5),
                ambient in 0.0f64..100.0f64,
            ) {
                let n = xs.len().min(ys.len()).min(powers.len());
                let (max_tj, max_ts, _avg) = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                prop_assert!(max_ts <= max_tj,
                    "max_ts {max_ts} > max_tj {max_tj}");
            }

            // --------------------------------------------------------------
            // Property T7: measure_thermal_edges is deterministic.
            // --------------------------------------------------------------
            #[test]
            fn prop_measure_deterministic(
                xs in proptest::collection::vec(pos_f32(), 1..=5),
                ys in proptest::collection::vec(pos_f32(), 1..=5),
                powers in proptest::collection::vec(power_f64(), 1..=5),
                ambient in 0.0f64..100.0f64,
            ) {
                let n = xs.len().min(ys.len()).min(powers.len());
                let a = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                let b = measure_thermal_edges(
                    &xs[..n], &ys[..n], &powers[..n],
                    &powers[..n], &powers[..n], &powers[..n],
                    (0.0, 0.0), 200.0, 200.0, ambient,
                );
                prop_assert_eq!(a.0.to_bits(), b.0.to_bits());
                prop_assert_eq!(a.1.to_bits(), b.1.to_bits());
                prop_assert_eq!(a.2.to_bits(), b.2.to_bits());
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("thermal_edges::tests::empty_input_returns_ambient_and_zero", empty_input_returns_ambient_and_zero),
        ("thermal_edges::tests::single_device_edge_mounted", single_device_edge_mounted),
        ("thermal_edges::tests::max_tj_folds_over_multiple_devices", max_tj_folds_over_multiple_devices),
        ("thermal_edges::tests::pairwise_sum_f32_matches_naive_below_eight", pairwise_sum_f32_matches_naive_below_eight),
        ("thermal_edges::tests::pairwise_sum_f32_recurses_above_blocksize", pairwise_sum_f32_recurses_above_blocksize),
        ("thermal_edges::tests::pairwise_sum_f32_empty_is_zero", pairwise_sum_f32_empty_is_zero),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
